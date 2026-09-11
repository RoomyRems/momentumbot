"""Unarmed, provider-free early-pullback experiment and causal shadow selector.

This is not an order adapter or a historical account runner. Selection evidence
is meaningful only for an otherwise valid, independently authenticated original
Micro trigger. No existing source, setup, execution or account policy is edited.
"""
from __future__ import annotations

from datetime import date
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
from typing import Iterable
import zipfile

import pandas as pd

from momentumbot.micro_replay import causal_active_pullback_number
from momentumbot.research.sealed_historical_walk_forward import (
    CALENDAR_ID, CANDIDATE_START, CANDIDATE_END, MICRO_POLICY_FINGERPRINT,
    bounded_full_sessions, canonical_fingerprint, freeze,
)

ID = "early-pullback-selection-v0.1"
PARENT = "b37c75a04057ba51e2fefde93e31f61239aa2455"
PARENT_TREE = "ac2d6c16b02c72ffa619c5a94ced7d9bdaaa4e25"
BASE = f"research/data-audits/{ID}"
CONTRACT_PATH = f"research/strategy/{ID}.json"
EXCLUSION_PATH = f"{BASE}/date-exclusions.json"
EXCLUSION_CONTENT_SHA256 = "b9318eabcf7acca2831fc88a7935eeb6854b52992f1689a512fbdfbec3cf2276"
OWN_FILES = (
    "src/momentumbot/research/early_pullback_selection_v01.py",
    "scripts/register_early_pullback_selection_v01.py",
    "tests/test_early_pullback_selection_v01.py",
)
MAX_PULLBACK_NUMBER = 2
BLOCK_SIZE = 30
DATE_BYTES = re.compile(rb"(?<!\d)(20\d{2}-\d{2}-\d{2})(?!\d)")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def verify_frozen(value):
    require(isinstance(value, dict), "frozen object required")
    body = dict(value)
    observed = body.pop("content_sha256", None)
    require(observed == canonical_fingerprint(body), "content hash mismatch")


def _dated_streams(name: str, raw: bytes, depth=0):
    """Read date-shaped bytes only; never deserialize record values or extract files."""
    require(depth <= 8, "archive nesting limit exceeded")
    yield name.encode()
    if name.endswith(".gz"):
        yield from _dated_streams(name[:-3], gzip.decompress(raw), depth + 1)
    elif name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            require(len(names) == len(set(names)), "duplicate archive member")
            for member in sorted(names):
                if not member.endswith("/"):
                    yield from _dated_streams(member, archive.read(member), depth + 1)
    else:
        yield raw


def build_exclusions(files: Iterable[tuple[str, bytes]]):
    """Conservatively exclude dates anywhere in the immutable parent's tracked files.

    Synthetic, calendar and administrative mentions also count. This inventory
    cannot certify what somebody may have inspected outside the repository.
    """
    inventory, dates, seen = [], set(), set()
    for path, raw in sorted(files):
        require(path not in seen, "duplicate parent path")
        seen.add(path)
        inventory.append({"path": path, "bytes": len(raw),
                          "sha256": hashlib.sha256(raw).hexdigest()})
        for stream in _dated_streams(path, raw):
            for match in DATE_BYTES.finditer(stream):
                try:
                    observed = date.fromisoformat(match.group(1).decode("ascii"))
                except ValueError:
                    continue
                if CANDIDATE_START <= observed <= CANDIDATE_END:
                    dates.add(observed.isoformat())
    require(bool(inventory), "empty parent inventory")
    return freeze({
        "artifact_type": "parent_tracked_byte_date_exclusions",
        "contract_id": ID, "parent_commit": PARENT, "parent_tree": PARENT_TREE,
        "inventory_file_count": len(inventory),
        "inventory_sha256": canonical_fingerprint(inventory),
        "excluded_dates": sorted(dates),
        "rule": "all valid interval ISO dates in tracked paths and bytes, recursively including gzip and ZIP members",
        "decoded_transcript_record_values": False,
        "outside_repository_exposure_certified": False,
    })


def select_panel(exclusions):
    verify_frozen(exclusions)
    require(exclusions["parent_commit"] == PARENT and
            exclusions["parent_tree"] == PARENT_TREE, "exclusion parent mismatch")
    dates = exclusions["excluded_dates"]
    require(dates == sorted(set(dates)), "exclusions must be sorted and unique")
    for value in dates:
        require(CANDIDATE_START <= date.fromisoformat(value) <= CANDIDATE_END,
                "exclusion outside candidate interval")
    excluded = set(dates)
    eligible = [value for value in bounded_full_sessions() if value not in excluded]
    count = len(eligible) // BLOCK_SIZE
    require(count > 0, "no complete fresh historical block; do not relax exclusions")
    seed_inputs = {"contract_id": ID, "parent_commit": PARENT,
                   "calendar_id": CALENDAR_ID,
                   "exclusion_content_sha256": exclusions["content_sha256"]}
    seed = canonical_fingerprint(seed_inputs)
    index = int(seed, 16) % count
    return {
        "candidate_start": CANDIDATE_START.isoformat(),
        "candidate_end": CANDIDATE_END.isoformat(), "calendar_id": CALENDAR_ID,
        "block_size": BLOCK_SIZE, "eligible_session_count": len(eligible),
        "complete_block_count": count, "discarded_tail_count": len(eligible) % BLOCK_SIZE,
        "seed_inputs": seed_inputs, "seed_sha256": seed, "block_index": index,
        "selected_dates": eligible[index * BLOCK_SIZE:(index + 1) * BLOCK_SIZE],
        "date_replacement_allowed": False, "seed_retry_allowed": False,
        "status": "repository_unreferenced_not_certified_unseen_outside_repository",
        "provider_calendar_confirmation_required": True,
        "contamination_response": "invalidate and preserve entire registration; no automatic replacement or re-selection",
    }


def _aware(value):
    stamp = pd.Timestamp(value)
    require(not pd.isna(stamp) and stamp.tzinfo is not None,
            "valid timezone-aware timestamp required")
    return stamp


def select_causal_prefix(bars, *, candidate_qualified_at, source_bar_start, decision_at):
    """Shadow gate on exactly the original activation's completed plan prefix.

    Receives no symbol, fill, P&L, transcript, quote or retrospective ordinal.
    Rejects future/extra columns instead of silently slicing them away. Invalid
    evidence raises; it is never reclassified as a valid strategy withhold.
    """
    qualified, source, decision = map(
        _aware, (candidate_qualified_at, source_bar_start, decision_at))
    require(isinstance(bars, pd.DataFrame), "bar DataFrame required")
    require(list(bars.columns) == ["high", "low", "volume"],
            "only ordered high/low/volume inputs allowed")
    require(isinstance(bars.index, pd.DatetimeIndex) and bars.index.tz is not None,
            "timezone-aware bar index required")
    require(not bars.empty and not bars.index.hasnans and bars.index.is_unique and
            bars.index.is_monotonic_increasing, "nonempty unique ordered prefix required")
    require(qualified <= bars.index[0] and bars.index[-1] == source,
            "prefix must begin after qualification and end at original source bar")
    require(all(stamp == stamp.floor("10s") for stamp in bars.index),
            "bars must start on the original ten-second grid")
    require(source + pd.Timedelta(seconds=10) <= decision < source + pd.Timedelta(seconds=20),
            "decision must be inside original armed/expiry interval")
    rows = []
    for stamp, high, low, volume in bars.itertuples(index=True, name=None):
        require(all(not isinstance(value, (bool, str)) and math.isfinite(float(value))
                    for value in (high, low, volume)), "finite numeric bar values required")
        high, low, volume = map(float, (high, low, volume))
        require(high >= low > 0 and volume >= 0, "invalid high/low/volume")
        rows.append({"timestamp": stamp.isoformat(), "high": high, "low": low, "volume": volume})
    ordinal = causal_active_pullback_number(bars, candidate_qualified_at=qualified)
    return freeze({
        "artifact_type": "early_pullback_shadow_selection", "contract_id": ID,
        "candidate_qualified_at": qualified.isoformat(), "source_bar_start": source.isoformat(),
        "decision_at": decision.isoformat(), "pullback_number": ordinal,
        "maximum_pullback_number": MAX_PULLBACK_NUMBER,
        "selected": ordinal <= MAX_PULLBACK_NUMBER,
        "reason": "early_pullback" if ordinal <= MAX_PULLBACK_NUMBER else "late_pullback_withheld",
        "ordinal_prefix_sha256": canonical_fingerprint(rows),
        "original_trigger_authenticated_by_this_helper": False,
        "order_authorized": False,
    })


def build_contract(root: Path, exclusions):
    panel = select_panel(exclusions)
    bindings = {}
    paths = [*OWN_FILES, "src/momentumbot/micro_replay.py", "src/momentumbot/micro_setup.py",
             "src/momentumbot/research/sealed_historical_walk_forward.py",
             "research/rules/current/entries.json",
             "research/strategy/sealed-historical-setup-stop-audit-v0.1.json",
             "research/strategy/sealed-historical-account-conditional-evaluation-v0.1.json"]
    for path in paths:
        raw = (root / path).read_bytes()
        bindings[path] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    return freeze({
        "schema_version": 1, "contract_id": ID, "registration_date": "2026-09-11",
        "artifact_type": "unarmed_setup_selection_experiment_registration",
        "parent_commit": PARENT, "parent_tree": PARENT_TREE,
        "parent_micro_fingerprint": MICRO_POLICY_FINGERPRINT,
        "parent_setup_audit_report_sha256": "879890004b3ea3fbcd5c6ef2b4330aa8f2660059252c855959408acfa811e9b5",
        "file_bindings": bindings, "exclusion_content_sha256": exclusions["content_sha256"],
        "sampling": panel,
        "hypothesis": "Restricting otherwise valid Micro entries to causal pullbacks one and two improves paired net P&L versus unchanged Micro on the fixed new panel.",
        "rationale": "MB-ENT-006 prefers early pullbacks; a hard cap of two is an experimental translation, not an exact source-authored threshold.",
        "prior_outcomes_already_known": "All 30 baseline dates and ordinal cohorts were inspected; first and second cohorts also lost. They are not holdout evidence.",
        "one_change": {
            "component": "entry eligibility only", "maximum_pullback_number": MAX_PULLBACK_NUMBER,
            "ordinal": "unchanged causal_active_pullback_number at original completed plan prefix",
            "anchor": "original profile-union activation qualification; no reset on withheld triggers, fills, re-entry, or a new peak",
            "unchanged": ["scanner profiles", "Micro geometry and support", "stops and targets", "quote freshness and clocks", "fees", "position sizing and risk", "management and continuation", "two-entry campaigns"],
            "no_macd_or_room_gate": True, "no_symbol_exceptions_or_threshold_search": True,
            "all_source_triggers_retained_with_dispositions": True,
        },
        "causal_protocol": {
            "input": "exact original activation completed bars, independently authenticated plan and trigger, and original causal-prefix hash",
            "availability": "ten-second bar available at start plus ten seconds; source prefix frozen before trigger; original minute support clocks unchanged",
            "forbidden": ["Ross actions/fills/ordinals/recap labels", "later prices or final volume", "retrospective P&L", "present-day reference data backfilled into history"],
            "runtime_order": ["verify point-in-time source and session evidence", "freeze common label-blind triggers", "bind recomputed ordinal and both-arm dispositions to every original trigger", "independently replay all paired account paths", "freeze both runtime chains", "evaluate"],
            "source_authentication_adapter_implemented": False,
            "paired_historical_account_runner_implemented": False,
            "missing_or_invalid_prefix": "fail unresolved; never convert to strategy withhold",
        },
        "evaluation": {
            "arms": ["unchanged_micro_v0.1", "early_pullbacks_one_and_two"],
            "accounts_once_only_usd": {"main_account": "30000", "small_account": "2000"},
            "horizons_seconds": [1, 5, 10], "scenarios": ["baseline_conservative", "stress"],
            "paths_per_arm": 12, "dated_records_both_arms": 720,
            "primary": "main_account baseline_conservative horizon_1s: child terminal net P&L minus control terminal net P&L after frozen fees",
            "support": "positive primary difference with at least one closed child entry is descriptive directional support only; zero or negative difference does not support the hypothesis; zero child entries is inconclusive",
            "profitability": "positive difference with negative child P&L is loss reduction, not profitability",
            "report_all": ["all 24 paths separately, no best-cell selection", "absolute and paired net P&L", "all source/withheld/entered/unavailable counts", "entry exposure, fill fractions and fees", "session-close drawdown, win rate and profit factor with undefined values explicit", "gross and net exit-reason attribution", "paired per-date deltas", "best closed trade removed per arm without rerunning or reselection"],
            "no_pooling": "accounts/scenarios/horizons share dates and opportunities; not independent samples",
            "counterfactual": "independent once-seeded chronological account replay for each arm; never subtract filtered saved fills or reuse control balances",
            "complete_gate": "all dates retained and all paired paths verifiable/flat complete under unchanged strict observed-update policy; unresolved source/account gaps block aggregate financial conclusion",
            "missing_dates": "retain unavailable; never replace, treat as zero, or silently omit; verified zero-opportunity dates remain",
            "strict_quote_withholds": "require complete original stream evidence under the separately registered strict observed-update policy; keep unavailable-source history visible",
            "formal_significance_claim": False, "ross_label_evaluation_authorized": False,
        },
        "authority": {"provider_calls": False, "paid_acquisition": False,
                      "historical_account_runtime": False, "paper_orders": False,
                      "live_orders": False, "policy_promotion": False},
        "status": "registered_synthetic_mechanics_only_no_market_evaluation",
        "next_gate": "verify repository date exclusions and parent integrity; freeze a separate paired-runner/source-binding implementation and bounded provider availability/cost plan before any acquisition or evaluation",
    })


def validate_registration(root: Path):
    exclusions = json.loads((root / EXCLUSION_PATH).read_bytes())
    contract = json.loads((root / CONTRACT_PATH).read_bytes())
    verify_frozen(exclusions)
    require(exclusions["content_sha256"] == EXCLUSION_CONTENT_SHA256,
            "exclusions differ from first committed selection inventory")
    verify_frozen(contract)
    require(contract == build_contract(root, exclusions), "registration or implementation binding differs")
    return contract
