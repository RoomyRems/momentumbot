"""New-panel catalogue and byte-bound scanner/Micro source reconstruction.

Synthetic source adapter only: no provider transport or account execution.
Ancestor date validators are never modified, substituted or monkeypatched.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import date
import hashlib
import json
from pathlib import Path

import pandas as pd

from momentumbot import causal_scanner_snapshot_v03 as scanner
from momentumbot.historical_profile_union_v01 import historical_profile_union_v0_1
from momentumbot.research import early_pullback_paired_adapter_v01 as parent
from momentumbot.research import sealed_historical_micro_runtime_v01 as micro
from momentumbot.research import sealed_historical_source_binding_v01 as original

ID = "early-pullback-panel-sources-v0.1"
PARENT = "d6dc01cddaf681b62f82dc2a46aae6fa2a1bfaa5"
PARENT_TREE = "dfb901b810e68ac4b5e577684952fde00ce6cc75"
PARENT_SHA = "989cd51227088010ad1c95db028bb9f876ee23fed94aeb62bcf038af584e8b6c"
CONTRACT_PATH = f"research/strategy/{ID}.json"
BASE = f"research/data-audits/{ID}"
OWN_FILES = ("src/momentumbot/research/early_pullback_panel_sources_v01.py",
             "scripts/build_early_pullback_panel_sources_v01.py",
             "tests/test_early_pullback_panel_sources_v01.py")
DATES = ("2026-03-04", "2026-03-05", "2026-03-06", "2026-03-09", "2026-03-10",
         "2026-03-12", "2026-03-13", "2026-03-18", "2026-03-19", "2026-03-25",
         "2026-03-30", "2026-04-02", "2026-04-06", "2026-04-10", "2026-04-13",
         "2026-04-14", "2026-04-15", "2026-04-16", "2026-04-17", "2026-04-20",
         "2026-04-21", "2026-04-23", "2026-04-24", "2026-04-27", "2026-04-28",
         "2026-04-29", "2026-04-30", "2026-05-04", "2026-05-08", "2026-05-19")
SCOPE = "synthetic_component_fixture"
BOUNDARY = dict(parent.BOUNDARY, provider_origin_authenticated=False,
                point_in_time_universe_provenance_authenticated=False,
                historical_account_context_adapter_integrated=False,
                market_candidate_discovery_recomputed=False,
                provider_request_exhaustion_verified=False,
                historical_zero_opportunity_claim=False)
require, seal, fingerprint = parent.require, parent.seal, parent.fingerprint
OHLCV = {"open", "high", "low", "close", "volume"}
SCANNER_FIELDS = {"candidate_rows", "float_records", "news_events", "news_statuses",
                  "membership_symbols", "previous_close_by_symbol",
                  "rank_split_minute_bars_by_symbol", "candidate_raw_minute_bars_by_symbol",
                  "candidate_exact_rvol_by_symbol"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _exact(value, keys, label):
    require(isinstance(value, dict) and set(value) == set(keys), "exact fields required: " + label)
    parent.scheduler._without_labels(value)
    fingerprint(value)


def _local(day, hours=0, minutes=0):
    return pd.Timestamp(day, tz="America/New_York") + pd.Timedelta(hours=hours, minutes=minutes)


def _pack(frame):
    return {"columns": list(frame.columns), "index": [t.isoformat() for t in frame.index],
            "data": parent.json_safe(frame.values.tolist())}


def _frame(value, fields, *, ties=False, empty=False):
    result = parent._frame(value, fields, empty=empty, ties=ties)
    if not ties:
        require(all(t == t.floor("1min") for t in result.index), "completed-minute grid required")
    return result


def _prices(frame):
    require((frame[["open", "high", "low", "close"]] > 0).all().all()
            and (frame["volume"] >= 0).all()
            and (frame["high"] >= frame[["open", "low", "close"]].max(axis=1)).all()
            and (frame["low"] <= frame[["open", "high", "close"]].min(axis=1)).all(),
            "invalid raw OHLCV")


def calendar_rows():
    """Expected schema, not an observed provider calendar or availability claim."""
    return [{"date": d, "open": _local(d, 9, 30).isoformat(), "close": _local(d, 16).isoformat()} for d in DATES]


def build_catalogue(calendar, *, expected_calendar_sha256):
    parent._pin(calendar, expected_calendar_sha256, "calendar evidence")
    _exact(calendar, {"scope", "sessions"}, "calendar")
    require(calendar["scope"] == SCOPE, "synthetic calendar evidence only")
    rows = calendar["sessions"]
    require(isinstance(rows, list) and len(rows) == len(DATES), "all exact selected sessions required")
    for day, row in zip(DATES, rows):
        _exact(row, {"date", "open", "close"}, "calendar session")
        require(row["date"] == day and parent.selection._aware(row["open"]) == _local(day, 9, 30)
                and parent.selection._aware(row["close"]) == _local(day, 16),
                "selected date/full-session calendar mismatch; do not replace dates")
    paths = []
    for arm in parent.ARMS:
        for account, amount in parent.accounts.ACCOUNT_SEEDS.items():
            for horizon, scenario in parent.accounts.registered_cells():
                cell = parent.accounts._path_id(account, horizon, scenario)
                path_id = "panel-path-" + fingerprint({"contract_id": ID, "arm": arm, "cell_id": cell})
                seed = seal({"account_id": path_id, "equity_usd": amount, "buying_power_usd": amount,
                    "effective_trading_date": DATES[0], "applied_once_per_path": True,
                    "broker_snapshot_claim": False})
                session_ids = ["panel-session-" + fingerprint({"path_id": path_id, "trading_date": d}) for d in DATES]
                slots = [seal({"contract_id": ID, "path_id": path_id, "session_id": session_ids[i],
                    "trading_date": d, "session_index": i,
                    "previous_session_id": None if i == 0 else session_ids[i - 1],
                    "seed_content_sha256": seed["content_sha256"], "seed_applied": i == 0,
                    "source_state": "not_bound", "opportunity_ids": None,
                    "source_date_has_no_micro_decisions": None}) for i, d in enumerate(DATES)]
                paths.append({"path_id": path_id, "cell_id": cell, "arm": arm, "account_key": account,
                    "profile_id": parent.daily.GENERAL_PROFILE_ID if account == "main_account" else parent.daily.SMALL_PROFILE_ID,
                    "behavioral_horizon_seconds": horizon, "execution_scenario_id": scenario,
                    "seed": seed, "sessions": slots})
    return seal({"contract_id": ID, "artifact_type": "new_panel_source_catalogue",
        "calendar_content_sha256": expected_calendar_sha256, "calendar": deepcopy(calendar),
        "selection_registration_sha256": parent.SELECTION_SHA, "selected_dates": list(DATES),
        "path_count": 24, "session_slot_count": 720, "paths": paths, **BOUNDARY})


def validate_catalogue(value, *, expected_catalogue_sha256):
    parent._pin(value, expected_catalogue_sha256, "new-panel catalogue")
    require(value == build_catalogue(value["calendar"], expected_calendar_sha256=value["calendar_content_sha256"]),
            "catalogue identity, calendar, seed or ancestry differs")
    return value


class SourceArchive:
    """Verify outer bytes and every declared member before deserializing a day.

    The two expected pins must come from an independent frozen capture record.
    A matching archive cannot by itself prove vendor origin, census completeness,
    SEC identity/as-of provenance, news receipt time or request exhaustion.
    """
    def __init__(self, path, *, expected_archive, expected_manifest_sha256):
        _exact(expected_archive, {"bytes", "sha256"}, "external archive commitment")
        require(type(expected_archive["bytes"]) is int and expected_archive["bytes"] > 0,
                "positive archive byte count required")
        self.archive = original.checked_archive(Path(path), expected_archive)
        try:
            self.manifest = original._json(self.archive.read("manifest.json"))
            parent._pin(self.manifest, expected_manifest_sha256, "capture manifest")
            _exact(self.manifest, {"contract_id", "scope", "selected_dates", "files"}, "capture manifest")
            require(self.manifest["contract_id"] == ID and self.manifest["scope"] == SCOPE
                    and self.manifest["selected_dates"] == list(DATES), "synthetic exact-panel capture only")
            files = self.manifest["files"]
            wanted = {"calendar.json"} | {f"dates/{day}.json" for day in DATES}
            require(isinstance(files, dict) and set(files) == wanted
                    and set(self.archive.namelist()) == wanted | {"manifest.json"},
                    "complete exact source file population required; missing is not empty")
            for name, spec in files.items():
                _exact(spec, {"bytes", "sha256"}, "member commitment")
                info = self.archive.getinfo(name)
                require(type(spec["bytes"]) is int and spec["bytes"] == info.file_size,
                        "uncompressed member size differs")
                with self.archive.open(name) as stream:
                    digest, count = hashlib.sha256(), 0
                    while chunk := stream.read(1024 * 1024):
                        count += len(chunk)
                        digest.update(chunk)
                require(count == spec["bytes"] and digest.hexdigest() == spec["sha256"], "source member bytes differ")
            self.archive_spec = deepcopy(expected_archive)
            self.manifest_sha = expected_manifest_sha256
            calendar = self.read("calendar.json")
            self.catalogue = build_catalogue(calendar, expected_calendar_sha256=fingerprint(calendar))
        except BaseException:
            self.archive.close()
            raise

    def read(self, name):
        parent._pin(self.manifest, self.manifest_sha, "unchanged capture manifest")
        require(name in self.manifest["files"], "unregistered source member")
        raw = self.archive.read(name)
        require(sha(raw) == self.manifest["files"][name]["sha256"], "source changed during read")
        return original._json(raw)

    def close(self):
        self.archive.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def bind_day(self, day):
        require(day in DATES, "date outside unchanged panel")
        value = self.read(f"dates/{day}.json")
        trace = {"archive": self.archive_spec, "manifest_sha256": self.manifest_sha,
                 "member": f"dates/{day}.json", "member_sha256": self.manifest["files"][f"dates/{day}.json"]["sha256"]}
        result = bind_day(value, expected_source_sha256=fingerprint(value), expected_day=day)
        return seal({**{k: v for k, v in result.items() if k != "content_sha256"},
                     "capture_trace": trace, "archive_bytes_verified": True})


def scanner_inputs(value, day):
    _exact(value, SCANNER_FIELDS, "scanner source")
    members = value["membership_symbols"]
    require(isinstance(members, list) and members == sorted(set(members)) and members
            and all(isinstance(s, str) and s.startswith("SYNTHETIC") for s in members),
            "complete ordered synthetic membership required")
    record_fields = {
        "candidate_rows": {"symbol", "previous_close", "first_market_qualified_bar_started_at", "first_market_qualified_at"},
        "float_records": {"symbol", "float_classification", "float_pillar_pass", "estimated_float_shares", "float_asof", "method", "sec_status"},
        "news_statuses": {"symbol", "provider_status"},
        "news_events": {"symbol", "published_at", "headline_id"},
    }
    for key, fields in record_fields.items():
        require(isinstance(value[key], list), "exact scanner record collection required")
        for row in value[key]:
            _exact(row, fields, key)
    candidates = [r["symbol"] for r in value["candidate_rows"]]
    require(candidates == sorted(set(candidates)) and set(candidates) <= set(members), "unique canonical candidate union required")
    for key in ("previous_close_by_symbol", "rank_split_minute_bars_by_symbol"):
        require(set(value[key]) == set(members), "full committed membership source required")
    for key in ("candidate_raw_minute_bars_by_symbol", "candidate_exact_rvol_by_symbol"):
        require(set(value[key]) == set(candidates), "exact candidate source population required")
    result = deepcopy(value)
    for key, fields in (("rank_split_minute_bars_by_symbol", {"close"}),
                        ("candidate_raw_minute_bars_by_symbol", {"close", "volume"}),
                        ("candidate_exact_rvol_by_symbol", {"relative_volume"})):
        frames = {}
        for symbol, raw in value[key].items():
            frame = _frame(raw, fields, empty=True)
            require(frame.empty or (frame.index[0] >= _local(day, 4) and frame.index[-1] < _local(day, 10)),
                    "scanner bars outside source session")
            frames[symbol] = frame["relative_volume"] if key == "candidate_exact_rvol_by_symbol" else frame
        result[key] = frames
    return result


def activation_rows(rows, day):
    """Unchanged first-qualifying profile grouping, with child source identities."""
    first = {}
    profiles = {parent.daily.GENERAL_PROFILE_ID: original.PROFILES[parent.daily.GENERAL_PROFILE_ID](),
                parent.daily.SMALL_PROFILE_ID: original.PROFILES[parent.daily.SMALL_PROFILE_ID]()}
    for row in rows:
        require(_local(day, 7) <= parent.selection._aware(row["decision_time"]) < _local(day, 10),
                "scanner activation outside original strategy clock")
        for profile_id, profile in profiles.items():
            if parent.daily.profile_eligibility(row, profile)["quality"] != "reject":
                first.setdefault((row["symbol"], profile_id), row)
    grouped = {}
    for (symbol, profile), row in first.items():
        key = (symbol, row["decision_time"])
        grouped.setdefault(key, {"row": row, "profiles": []})["profiles"].append(profile)
    result = []
    for (symbol, at), item in sorted(grouped.items(), key=lambda item: (item[0][1], item[0][0])):
        activation = {"symbol": symbol, "candidate_qualified_at": at,
            "scanner_record_content_sha256": fingerprint(item["row"]),
            "eligible_strategy_profile_ids": [p for p in profiles if p in item["profiles"]]}
        activation["activation_id"] = "activation-" + fingerprint({"contract_id": ID, "trading_date": day, **activation})
        result.append(activation)
    return result


def bind_day(value, *, expected_source_sha256, expected_day):
    parent._pin(value, expected_source_sha256, "complete day source")
    _exact(value, {"scope", "trading_date", "scanner", "micro_by_symbol"}, "day source")
    require(value["scope"] == SCOPE and expected_day in DATES and value["trading_date"] == expected_day,
            "synthetic exact-panel day required")
    day = expected_day
    inputs = scanner_inputs(value["scanner"], day)
    rows = scanner.build_scanner_snapshot_rows(trading_date=date.fromisoformat(day),
        profile=historical_profile_union_v0_1(), **inputs)
    activations = activation_rows(rows, day)
    symbols = {a["symbol"] for a in activations}
    require(isinstance(value["micro_by_symbol"], dict) and set(value["micro_by_symbol"]) == symbols,
            "exact activated-symbol Micro source union required; missing is not no-trigger")
    decisions, sources, basis = [], {}, {}
    for symbol in sorted(symbols):
        raw = value["micro_by_symbol"][symbol]
        _exact(raw, {"trades", "session_minutes_raw", "ema_warmup_split"}, "Micro source")
        trades = _frame(raw["trades"], {"price", "size", "conditions", "tape"}, ties=True, empty=True)
        minutes = _frame(raw["session_minutes_raw"], OHLCV)
        warmup = _frame(raw["ema_warmup_split"], OHLCV | {"vwap"})
        _prices(minutes)
        _prices(warmup)
        require(minutes.index[0] >= _local(day, 4) and minutes.index[-1] + pd.Timedelta(minutes=1) <= _local(day, 10)
                and warmup.index[-1] < _local(day), "raw minutes or prior warmup outside source clock")
        qualified = min(parent.selection._aware(a["candidate_qualified_at"]) for a in activations if a["symbol"] == symbol)
        require(trades.empty or (trades.index[0] >= qualified and trades.index[-1] < _local(day, 10)),
                "SIP source outside activation/session bounds")
        raw_scanner = inputs["candidate_raw_minute_bars_by_symbol"][symbol]
        split = inputs["rank_split_minute_bars_by_symbol"][symbol]["close"]
        require(raw_scanner.index.equals(split.index), "complete raw/split timestamp pairs required")
        factor, evidence = micro.causal_raw_to_split_factor(raw_scanner["close"], split, qualified_at=qualified)
        prior = raw_scanner.loc[raw_scanner.index + pd.Timedelta(minutes=1) <= qualified]
        require(set(prior.index) <= set(minutes.index), "preactivation raw-minute bridge missing")
        require((prior[["close", "volume"]].to_numpy() == minutes.loc[prior.index, ["close", "volume"]].to_numpy()).all(),
                "raw scanner and Micro support source bridge differs")
        normalized = micro.normalize_warmup_to_raw(warmup, factor)[sorted(OHLCV)]
        support = parent.indicators.completed_bar_support_series(minutes, ema_warmup=normalized)
        bars = parent.micro_bars.aggregate_trade_bars(trades) if not trades.empty else None
        basis[symbol] = evidence
        for activation in (a for a in activations if a["symbol"] == symbol):
            if bars is None:
                continue
            built = parent.daily.build_micro_trigger_decisions(parent.daily.ProfileActivation(**activation),
                bars=bars, trades=trades, support=support, replay_end=_local(day, 10))
            for item in built:
                decision = parent.json_safe(asdict(item))
                at, start = pd.Timestamp(decision["decision_at"]), pd.Timestamp(decision["plan"]["source_bar_start"])
                source = {"activation": deepcopy(activation), "decision": decision,
                    "trades": _pack(trades.loc[(trades.index >= pd.Timestamp(activation["candidate_qualified_at"])) & (trades.index <= at)]),
                    "session_minutes": _pack(minutes.loc[minutes.index + pd.Timedelta(minutes=1) <= start]),
                    "ema_warmup": _pack(normalized)}
                binding = parent.authenticate_trigger(source, expected_source_sha256=fingerprint(source),
                    expected_decision_sha256=fingerprint(decision), expected_activation_sha256=fingerprint(activation))
                require(decision["plan_id"] not in sources, "duplicate reconstructed plan")
                sources[decision["plan_id"]] = {"source": source, "binding": binding}
                decisions.append(decision)
    decisions.sort(key=lambda row: (row["decision_at"], row["symbol"], row["plan_id"]))
    return seal({"contract_id": ID, "artifact_type": "reconstructed_synthetic_panel_day", "trading_date": day,
        "source_content_sha256": expected_source_sha256, "capture_trace": None,
        "scanner_rows_sha256": fingerprint(rows), "scanner_row_count": len(rows),
        "membership_count": len(inputs["membership_symbols"]), "activations": activations,
        "normalization_evidence": basis, "decisions": decisions, "sources": sources,
        "no_micro_decisions": not decisions, "source_semantics_recomputed": True,
        "archive_bytes_verified": False, **BOUNDARY})


def bind_panel(archive):
    require(type(archive) is SourceArchive, "verified source archive required")
    catalogue = archive.catalogue
    calendar = archive.read("calendar.json")
    require(catalogue == build_catalogue(calendar, expected_calendar_sha256=fingerprint(calendar)),
            "catalogue differs from verified calendar source")
    validate_catalogue(catalogue, expected_catalogue_sha256=fingerprint(catalogue))
    days = {d: archive.bind_day(d) for d in DATES}
    paths = deepcopy(catalogue["paths"])
    for path in paths:
        for i, slot in enumerate(path["sessions"]):
            day = days[slot["trading_date"]]
            selected = [d for d in day["decisions"] if path["profile_id"] in d["eligible_strategy_profile_ids"]]
            body = {k: v for k, v in slot.items() if k != "content_sha256"}
            path["sessions"][i] = seal({**body, "source_state": "synthetic_source_verified",
                "source_day_content_sha256": day["content_sha256"], "opportunity_ids": [d["plan_id"] for d in selected],
                "source_date_has_no_micro_decisions": day["no_micro_decisions"],
                "execution_input_status": "not_acquired", "account_runtime_executed": False})
    return seal({"contract_id": ID, "artifact_type": "bound_synthetic_new_panel_sources",
        "catalogue_content_sha256": catalogue["content_sha256"], "source_archive": archive.archive_spec,
        "capture_manifest_sha256": archive.manifest_sha, "selected_dates": list(DATES),
        "days": days, "paths": paths, "source_dates": 30, "paired_session_slots": 720, **BOUNDARY})


def registration(root):
    inherited = parent.validate_registration(root)
    require(inherited["content_sha256"] == PARENT_SHA, "paired adapter parent differs")
    selected = parent.selection.validate_registration(root)
    require(selected["sampling"]["selected_dates"] == list(DATES), "fixed dates differ")
    protected = set(inherited["file_bindings"]) | set(OWN_FILES) | {parent.CONTRACT_PATH,
        f"{parent.BASE}/data-plan.json", "src/momentumbot/causal_scanner_snapshot_v03.py",
        "src/momentumbot/historical_profile_union_v01.py", "src/momentumbot/research/sealed_historical_micro_runtime_v01.py"}
    files = {p: {"bytes": (root / p).stat().st_size, "sha256": sha((root / p).read_bytes())} for p in sorted(protected)}
    return seal({"contract_id": ID, "parent_commit": PARENT, "parent_tree": PARENT_TREE,
        "parent_registration_sha256": PARENT_SHA, "file_bindings": files, "selected_dates": list(DATES),
        "hypothesis": "fixed new catalogue and externally pinned capture bytes reproduce causal scanner activations, normalization and every Micro trigger without changing parent policies",
        "archive_schema": "manifest.json plus calendar.json and exactly 30 dates/YYYY-MM-DD.json members; every byte pinned before day deserialization",
        "calendar": "synthetic exact 09:30-16:00 New York sessions; original provider confirmation still required",
        "source_semantics": "unchanged scanner v0.3 and profile union; first qualifying profile activations; earliest-activation causal raw/split factor; original Micro and causal-prefix checks",
        "provenance_limits": "archive-to-feature integrity is not provider HTTP provenance, census exhaustion, point-in-time identity/SEC/news verification or an independently observed calendar",
        "account_limit": "24 new path identities and 720 slots; no relaxation of original dated validators and no new-date account execution",
        "unchanged": "first-two experiment, dates, parent policies, fee assumptions, original baseline and hosted-only replay waiver",
        "next_gate": "separately bounded availability, capture/request provenance and new-catalogue engine-context integration before historical account activation",
        **BOUNDARY})


def validate_registration(root):
    saved = original._json((root / CONTRACT_PATH).read_bytes())
    require(saved == registration(root), "new-panel source registration differs")
    return saved
