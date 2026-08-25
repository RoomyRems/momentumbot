"""Causal prospective scanner/Micro decision-source production.

The producer has two deliberately separated phases.  A pre-session phase
freezes the current Alpaca asset census and SEC ticker/CIK crosswalk before the
07:00 New York strategy start.  A post-session phase may then acquire the
registered date's market data, reconstruct every union-profile scanner state,
and emit only Micro trigger decisions.  Account state, execution scenarios,
fills, exits, later outcomes, and retrospective labels never enter this module.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime, time, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time as clock
from typing import Callable, Iterable, Mapping, Sequence
import urllib.error
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.causal_market_discovery import (
    build_market_candidate_payload,
    discovery_audit_fingerprint,
    discovery_records_fingerprint,
    strategy_profile_manifest,
)
from momentumbot.causal_scanner_snapshot import (
    RANK_HISTORICAL_FEED,
    RANK_MINUTE_ADJUSTMENT,
    RANK_MINUTE_TIMEFRAME,
    RANK_PREVIOUS_CLOSE_ADJUSTMENT,
    RANK_PREVIOUS_CLOSE_TIMEFRAME,
    RANK_PRIOR_CLOSE_LOOKBACK_CALENDAR_DAYS,
    UPSTREAM_MARKET_ACQUISITION_TAIL_END,
    bind_candidate_frames_to_reacquired_rank_frames,
    build_scanner_snapshot_rows,
    market_inputs_fingerprint,
    ordered_snapshot_records_fingerprint,
    trim_scanner_bar_frame,
    trim_scanner_rvol_series,
)
from momentumbot.historical_data import (
    DiscoveryResult,
    asset_master_fingerprint,
    discover_market_day,
    normalize_asset_master,
)
from momentumbot.historical_float import (
    BasisObservation,
    build_causal_float_record,
    causal_float_records_fingerprint,
    causal_float_v0_1_manifest,
    observe_basis,
    select_float_evidence,
)
from momentumbot.historical_news import (
    build_news_candidate_statuses,
    causal_news_v0_2_manifest,
    news_events_fingerprint,
    news_statuses_fingerprint,
    normalize_alpaca_news,
    prior_regular_session_date,
    publication_window,
    validate_publication_timed_news,
)
from momentumbot.indicators import completed_bar_support_series, validate_bars
from momentumbot.micro_bars import aggregate_trade_bars
from momentumbot.micro_execution import price_eligible_trades
from momentumbot.micro_policy import micro_v0_1_policy
from momentumbot.micro_replay import causal_active_pullback_number
from momentumbot.micro_setup import evaluate_micro_pullback_plan
from momentumbot.models import (
    CandidateQuality,
    StrategyProfile,
    current_general_2026,
    current_small_account_2026,
)
from momentumbot.providers.alpaca import AlpacaDataClient, chunked
from momentumbot.providers.alpaca_trades import historical_trades
from momentumbot.providers.sec_edgar import (
    ParsedCompanyFacts,
    SecEdgarClient,
    normalize_cik,
    parse_companyfacts,
    parse_submission_acceptance_times,
)
from momentumbot.research.account_chronological_integration import (
    MICRO_POLICY_FINGERPRINT,
    PANEL_ID,
    REGISTERED_DATES,
)
from momentumbot.research.account_priority_policy import (
    GENERAL_PROFILE_FINGERPRINT,
    SMALL_PROFILE_FINGERPRINT,
    strategy_profile_fingerprint,
)
from momentumbot.research.microstructure_contract import canonical_fingerprint
from momentumbot.research.prospective_opportunity_freeze import (
    CONTRACT_CONTENT_SHA256 as OPPORTUNITY_FREEZE_CONTRACT_CONTENT_SHA256,
    GENERAL_PROFILE_ID,
    SMALL_PROFILE_ID,
    STRATEGY_PROFILE_IDS,
    build_daily_decision_source,
    validate_daily_decision_source,
)


SCHEMA_VERSION = 1
CONTRACT_ID = "prospective-daily-scanner-micro-source-v0.1"
# Filled after the preregistration JSON is finalized.  The validator refuses a
# different value, so an edit cannot silently expand the registered producer.
CONTRACT_CONTENT_SHA256 = (
    "99ba9f54ac50a913e64d78bb727351b67f8182818c54519f7d8be428651d6f38"
)
PARENT_CHECKPOINT_SHA = "8f8faf3ab551e6774ad677a842cea87ccb183238"
PARENT_CHECKPOINT_TREE_SHA = "e70f3adfc628cb053af14a1355035325b03ccf8b"

PREREQUISITE_ARTIFACT_TYPE = "prospective_pre_session_scanner_prerequisites"
SCANNER_ARTIFACT_TYPE = "prospective_causal_union_scanner_runtime"
MICRO_ARTIFACT_TYPE = "prospective_causal_micro_trigger_runtime"
PRODUCER_ARTIFACT_TYPE = "prospective_daily_scanner_micro_source_bundle"
SOURCE_FILE = "prospective-daily-micro-decision-source.json"
PREREQUISITE_FILE = "pre-session-prerequisites.json"
SCANNER_FILE = "scanner-runtime.json"
MICRO_FILE = "micro-trigger-runtime.json"
MANIFEST_FILE = "producer-manifest.json"

SESSION_TIMEZONE = "America/New_York"
ET = ZoneInfo(SESSION_TIMEZONE)
STRATEGY_START = time(7, 0)
ENTRY_CUTOFF = time(10, 0)
HISTORICAL_SIP_END = time(10, 1)
PRODUCTION_NOT_BEFORE = time(10, 20)
VOLUME_FEATURE_START = time(4, 0)
EMA_WARMUP_CALENDAR_DAYS = 7
_ALLOWED_EXCHANGES = {"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS", "NYSEARCA"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


@dataclass(frozen=True, slots=True)
class ProfileActivation:
    activation_id: str
    symbol: str
    candidate_qualified_at: str
    scanner_record_content_sha256: str
    eligible_strategy_profile_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MicroTriggerDecision:
    activation_id: str
    plan_id: str
    symbol: str
    candidate_qualified_at: str
    decision_at: str
    micro_runtime_content_sha256: str
    eligible_strategy_profile_ids: tuple[str, ...]
    plan: dict[str, object]


@dataclass(frozen=True, slots=True)
class ProspectiveDailyArtifacts:
    scanner_runtime: dict[str, object]
    micro_runtime: dict[str, object]
    decision_source: dict[str, object]
    producer_manifest: dict[str, object]


def _fingerprinted(payload: Mapping[str, object]) -> dict[str, object]:
    value = dict(payload)
    value["content_sha256"] = canonical_fingerprint(value)
    return value


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _aware(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} must be a valid timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed


def _registered_date(value: str | date) -> date:
    parsed = value if isinstance(value, date) else date.fromisoformat(str(value))
    if parsed.isoformat() not in REGISTERED_DATES:
        raise ValueError("trading date is outside the registered prospective panel")
    return parsed


def _local_date(value: datetime) -> date:
    return value.astimezone(ET).date()


def _local_time(value: datetime) -> time:
    return value.astimezone(ET).timetz().replace(tzinfo=None)


def _same_date_historical_sip_end(trading_date: date) -> datetime:
    """Return the deterministic end bound for same-date historical SIP reads.

    The source reconstructs decisions only through the registered 10:00 New
    York entry cutoff.  The final 09:59 one-minute aggregate is available at
    10:00, and the existing acquisition path uses an exclusive 10:01 bound.
    Keeping every same-date daily-bar request at that same bound avoids asking
    Alpaca for future/recent SIP data while retaining every causal candidate.
    """

    return datetime.combine(
        trading_date,
        HISTORICAL_SIP_END,
        ET,
    ).astimezone(timezone.utc)


def union_acquisition_profile() -> StrategyProfile:
    """Return the fixed superset profile covering both account screens."""

    general = current_general_2026()
    return replace(
        general,
        name="prospective-union-acquisition-v0.1",
        min_price=1.50,
        max_price=20.0,
        preferred_min_price=1.50,
        preferred_max_price=20.0,
        min_percent_gain=10.0,
        min_relative_volume=5.0,
        require_top_gainer_rank=None,
    )


def validate_daily_source_contract(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported daily source contract schema")
    if payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected daily source contract")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if payload.get("content_sha256") != canonical_fingerprint(unsigned):
        raise ValueError("daily source contract content hash mismatch")
    if payload.get("content_sha256") != CONTRACT_CONTENT_SHA256:
        raise ValueError("daily source contract differs from its registration")
    if payload.get("registered_dates") != list(REGISTERED_DATES):
        raise ValueError("daily source registered dates changed")
    parents = payload.get("frozen_parents")
    if not isinstance(parents, Mapping) or parents != {
        "parent_checkpoint_sha": PARENT_CHECKPOINT_SHA,
        "parent_checkpoint_tree_sha": PARENT_CHECKPOINT_TREE_SHA,
        "opportunity_freeze_contract_id": "prospective-opportunity-freeze-v0.1",
        "opportunity_freeze_contract_content_sha256": (
            OPPORTUNITY_FREEZE_CONTRACT_CONTENT_SHA256
        ),
        "account_panel_id": PANEL_ID,
        "account_integration_contract_content_sha256": (
            "64489aa27fec5eaf8ca12c94f4aeb47344d49a79b14df1bdda706cd23cc9ce73"
        ),
        "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
        "general_strategy_profile_fingerprint": GENERAL_PROFILE_FINGERPRINT,
        "small_strategy_profile_fingerprint": SMALL_PROFILE_FINGERPRINT,
    }:
        raise ValueError("daily source frozen parents changed")
    scanner = payload.get("union_scanner_contract")
    if not isinstance(scanner, Mapping):
        raise ValueError("daily source scanner contract is missing")
    if scanner.get("union_acquisition_profile_fingerprint") != (
        strategy_profile_fingerprint(union_acquisition_profile())
    ):
        raise ValueError("daily source union acquisition profile changed")
    if scanner.get("first_qualifying_minute_retained_per_profile") is not True:
        raise ValueError("daily source profile activation rule changed")
    if scanner.get("same_profile_activation_minute_unioned_once") is not True:
        raise ValueError("daily source profile union rule changed")
    micro = payload.get("micro_trigger_contract")
    if not isinstance(micro, Mapping):
        raise ValueError("daily source Micro contract is missing")
    if micro.get("fill_simulation_allowed") is not False:
        raise ValueError("daily source fill authority changed")
    if micro.get("exit_simulation_allowed") is not False:
        raise ValueError("daily source exit authority changed")
    authority = payload.get("provider_authority")
    if not isinstance(authority, Mapping):
        raise ValueError("daily source provider authority is missing")
    if authority.get("provider_reads_authorized") is not True:
        raise ValueError("daily source provider reads are not registered")
    for field in (
        "provider_writes_authorized",
        "databento_metadata_quote_authorized",
        "databento_request_authorized",
        "paper_order_authorized",
        "live_order_authorized",
    ):
        if authority.get(field) is not False:
            raise ValueError("daily source authority boundary changed")
    if authority.get("incremental_purchase_authorized_usd") != "0":
        raise ValueError("daily source incremental purchase cap changed")
    if authority.get("databento_credit_authorized_usd") != "0":
        raise ValueError("daily source Databento credit cap changed")
    output = payload.get("output_contract")
    if not isinstance(output, Mapping):
        raise ValueError("daily source output contract is missing")
    if output.get("files") != [SCANNER_FILE, MICRO_FILE, SOURCE_FILE, MANIFEST_FILE]:
        raise ValueError("daily source output files changed")
    if output.get("write_once_output_directory") is not True:
        raise ValueError("daily source write-once rule changed")
    knowledge = payload.get("knowledge_boundary")
    if not isinstance(knowledge, Mapping):
        raise ValueError("daily source knowledge boundary is missing")
    for field in (
        "raw_transcripts_allowed",
        "Ross_actions_recaps_or_labels_allowed",
        "later_prices_or_pnl_allowed_for_selection",
        "account_snapshots_or_balances_allowed",
        "account_scarcity_allowed",
        "execution_scenario_selection_allowed",
        "threshold_tuning_allowed",
    ):
        if knowledge.get(field) is not False:
            raise ValueError("daily source knowledge boundary changed")
    if payload.get("policy_promotion_eligible") is not False:
        raise ValueError("daily source cannot promote policy")
    if payload.get("profitability_claim_eligible") is not False:
        raise ValueError("daily source cannot support profitability claims")


def load_daily_source_contract(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("daily source contract root must be an object")
    validate_daily_source_contract(payload)
    return payload


def build_pre_session_prerequisites(
    *,
    trading_date: str | date,
    capture_started_at: datetime,
    capture_completed_at: datetime,
    runtime_head_sha: str,
    asset_rows: Sequence[Mapping[str, object]],
    sec_ticker_rows: Sequence[Mapping[str, object]],
    workflow_context: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Freeze the only mutable membership references before strategy start."""

    session = _registered_date(trading_date)
    for value, field in (
        (capture_started_at, "capture_started_at"),
        (capture_completed_at, "capture_completed_at"),
    ):
        if value.tzinfo is None:
            raise ValueError(f"{field} must be timezone-aware")
        if _local_date(value) != session:
            raise ValueError(f"{field} must belong to the registered New York date")
        if _local_time(value) >= STRATEGY_START:
            raise ValueError(f"{field} must precede the 07:00 strategy start")
    if capture_completed_at < capture_started_at:
        raise ValueError("pre-session capture completion precedes its start")
    if not _GIT_SHA.fullmatch(runtime_head_sha):
        raise ValueError("runtime head must be a full lowercase Git SHA")

    assets = [dict(row) for row in normalize_asset_master([dict(row) for row in asset_rows])]
    if not assets:
        raise ValueError("pre-session Alpaca asset census is empty")
    ticker_map: dict[str, dict[str, str]] = {}
    for source in sec_ticker_rows:
        ticker = str(source.get("ticker") or "").strip().upper()
        if not _SYMBOL.fullmatch(ticker):
            raise ValueError("SEC crosswalk contains an invalid ticker")
        row = {
            "ticker": ticker,
            "cik": normalize_cik(str(source.get("cik") or "")),
            "name": str(source.get("name") or "").strip(),
            "exchange": str(source.get("exchange") or "").strip().upper(),
        }
        prior = ticker_map.get(ticker)
        if prior is not None and prior != row:
            raise ValueError(f"SEC crosswalk repeats ticker {ticker}")
        ticker_map[ticker] = row
    if not ticker_map:
        raise ValueError("pre-session SEC ticker crosswalk is empty")

    context = dict(sorted((workflow_context or {}).items()))
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in context.items()):
        raise ValueError("workflow context must contain strings")
    payload = _fingerprinted(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_id": f"prospective-pre-session-prerequisites-{session.isoformat()}",
            "artifact_type": PREREQUISITE_ARTIFACT_TYPE,
            "contract_id": CONTRACT_ID,
            "trading_date": session.isoformat(),
            "session_timezone": SESSION_TIMEZONE,
            "strategy_start_deadline": STRATEGY_START.isoformat(),
            "capture_started_at": capture_started_at.astimezone(UTC).isoformat(),
            "capture_completed_at": capture_completed_at.astimezone(UTC).isoformat(),
            "runtime_head_sha": runtime_head_sha,
            "asset_census": assets,
            "asset_count": len(assets),
            "sec_ticker_crosswalk": [ticker_map[key] for key in sorted(ticker_map)],
            "sec_ticker_count": len(ticker_map),
            "workflow_context": context,
            "provider_reads": [
                "alpaca_paper_v2_assets_current_census",
                "sec_company_tickers_exchange_current_crosswalk",
            ],
            "account_snapshot_loaded": False,
            "account_scarcity_applied": False,
            "execution_scenario_applied": False,
            "retrospective_labels_loaded": False,
            "later_prices_or_pnl_loaded": False,
            "broker_order_made": False,
        }
    )
    validate_pre_session_prerequisites(payload)
    return payload


def validate_pre_session_prerequisites(
    payload: Mapping[str, object],
) -> dict[str, object]:
    expected = {
        "schema_version",
        "artifact_id",
        "artifact_type",
        "contract_id",
        "trading_date",
        "session_timezone",
        "strategy_start_deadline",
        "capture_started_at",
        "capture_completed_at",
        "runtime_head_sha",
        "asset_census",
        "asset_count",
        "sec_ticker_crosswalk",
        "sec_ticker_count",
        "workflow_context",
        "provider_reads",
        "account_snapshot_loaded",
        "account_scarcity_applied",
        "execution_scenario_applied",
        "retrospective_labels_loaded",
        "later_prices_or_pnl_loaded",
        "broker_order_made",
        "content_sha256",
    }
    if set(payload) != expected:
        raise ValueError("pre-session prerequisite fields changed")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported prerequisite schema")
    if payload.get("artifact_type") != PREREQUISITE_ARTIFACT_TYPE:
        raise ValueError("unexpected prerequisite artifact type")
    if payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("prerequisite contract changed")
    session = _registered_date(str(payload.get("trading_date") or ""))
    if payload.get("artifact_id") != f"prospective-pre-session-prerequisites-{session.isoformat()}":
        raise ValueError("prerequisite artifact identity changed")
    if payload.get("session_timezone") != SESSION_TIMEZONE:
        raise ValueError("prerequisite timezone changed")
    if payload.get("strategy_start_deadline") != STRATEGY_START.isoformat():
        raise ValueError("prerequisite strategy deadline changed")
    started = _aware(payload.get("capture_started_at"), "capture_started_at")
    completed = _aware(payload.get("capture_completed_at"), "capture_completed_at")
    if completed < started or _local_date(started) != session or _local_date(completed) != session:
        raise ValueError("prerequisite capture chronology changed")
    if (
        _local_time(started) >= STRATEGY_START
        or _local_time(completed) >= STRATEGY_START
    ):
        raise ValueError("prerequisite capture did not precede strategy start")
    if not _GIT_SHA.fullmatch(str(payload.get("runtime_head_sha") or "")):
        raise ValueError("prerequisite runtime head is invalid")
    assets = payload.get("asset_census")
    tickers = payload.get("sec_ticker_crosswalk")
    if not isinstance(assets, list) or payload.get("asset_count") != len(assets) or not assets:
        raise ValueError("prerequisite asset census count changed")
    normalized_assets = [dict(row) for row in normalize_asset_master([dict(row) for row in assets if isinstance(row, Mapping)])]
    if normalized_assets != assets:
        raise ValueError("prerequisite asset census is not canonical")
    if not isinstance(tickers, list) or payload.get("sec_ticker_count") != len(tickers) or not tickers:
        raise ValueError("prerequisite SEC crosswalk count changed")
    canonical_tickers: list[dict[str, str]] = []
    for row in tickers:
        if not isinstance(row, Mapping) or set(row) != {
            "ticker",
            "cik",
            "name",
            "exchange",
        }:
            raise ValueError("prerequisite SEC crosswalk row changed")
        ticker = str(row.get("ticker") or "")
        cik = str(row.get("cik") or "")
        name = str(row.get("name") or "")
        exchange = str(row.get("exchange") or "")
        if not _SYMBOL.fullmatch(ticker):
            raise ValueError("prerequisite SEC crosswalk ticker is invalid")
        if cik != normalize_cik(cik):
            raise ValueError("prerequisite SEC crosswalk CIK is not canonical")
        if name != name.strip() or exchange != exchange.strip().upper():
            raise ValueError("prerequisite SEC crosswalk text is not canonical")
        canonical_tickers.append(
            {
                "ticker": ticker,
                "cik": cik,
                "name": name,
                "exchange": exchange,
            }
        )
    if canonical_tickers != sorted(
        canonical_tickers, key=lambda row: row["ticker"]
    ) or len({row["ticker"] for row in canonical_tickers}) != len(
        canonical_tickers
    ):
        raise ValueError("prerequisite SEC crosswalk is not canonical")
    workflow_context = payload.get("workflow_context")
    if not isinstance(workflow_context, Mapping) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in workflow_context.items()
    ):
        raise ValueError("prerequisite workflow context changed")
    if dict(sorted(workflow_context.items())) != workflow_context:
        raise ValueError("prerequisite workflow context is not canonical")
    if payload.get("provider_reads") != [
        "alpaca_paper_v2_assets_current_census",
        "sec_company_tickers_exchange_current_crosswalk",
    ]:
        raise ValueError("prerequisite provider scope changed")
    for field in (
        "account_snapshot_loaded",
        "account_scarcity_applied",
        "execution_scenario_applied",
        "retrospective_labels_loaded",
        "later_prices_or_pnl_loaded",
        "broker_order_made",
    ):
        if payload.get(field) is not False:
            raise ValueError("pre-session prerequisite crossed a prohibited boundary")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if payload.get("content_sha256") != canonical_fingerprint(unsigned):
        raise ValueError("pre-session prerequisite content hash mismatch")
    return dict(payload)


def profile_eligibility(
    row: Mapping[str, object],
    profile: StrategyProfile,
) -> dict[str, object]:
    """Reapply one frozen profile to one exact causal scanner minute."""

    if row.get("candidate_completed_bar_present") is not True:
        return {
            "quality": CandidateQuality.REJECT.value,
            "pillars": {},
            "reasons": ["missing candidate completed bar"],
        }
    try:
        price = float(row["price"])
        percent_gain = float(row["percent_gain"])
        relative_volume = float(row["exact_same_time_rvol"])
    except (KeyError, TypeError, ValueError):
        return {
            "quality": CandidateQuality.REJECT.value,
            "pillars": {},
            "reasons": ["non-numeric scanner feature"],
        }
    float_value = row.get("estimated_float_shares")
    float_shares = (
        int(float_value)
        if isinstance(float_value, int) and not isinstance(float_value, bool) and float_value > 0
        else None
    )
    has_news = row.get("has_provider_news_as_of")
    rank_value = row.get("top_gainer_rank")
    top_rank = (
        int(rank_value)
        if isinstance(rank_value, int) and not isinstance(rank_value, bool) and rank_value > 0
        else None
    )
    pillars = {
        "percent_gain": percent_gain >= profile.min_percent_gain,
        "relative_volume": relative_volume >= profile.min_relative_volume,
        "fresh_news": has_news is True if profile.require_fresh_news_for_a_quality else True,
        "price": profile.min_price <= price <= profile.max_price,
        "float": float_shares is not None and float_shares < profile.max_float_shares,
    }
    missing = [name for name, passed in pillars.items() if not passed]
    rank_ok = profile.require_top_gainer_rank is None or (
        top_rank is not None and top_rank <= profile.require_top_gainer_rank
    )
    reasons: list[str] = []
    if not missing and rank_ok:
        quality = CandidateQuality.A_QUALITY
    elif (
        missing == ["fresh_news"]
        and profile.allow_obvious_no_news_exception
        and top_rank == 1
        and rank_ok
    ):
        quality = CandidateQuality.CONDITIONAL
        reasons.append("provider-relative no-news allowed only for current rank one")
    else:
        quality = CandidateQuality.REJECT
        reasons.extend(f"failed pillar: {name}" for name in missing)
        if not rank_ok:
            reasons.append("outside required top-gainer rank")
    return {
        "quality": quality.value,
        "pillars": pillars,
        "reasons": reasons,
    }


def build_profile_activations(
    *,
    scanner_runtime_content_sha256: str,
    scanner_rows: Sequence[Mapping[str, object]],
) -> tuple[list[ProfileActivation], list[dict[str, object]]]:
    """Find the first qualifying minute for each profile and union exact ties."""

    if not _is_sha256(scanner_runtime_content_sha256):
        raise ValueError("scanner runtime hash is invalid")
    profiles = {
        GENERAL_PROFILE_ID: current_general_2026(),
        SMALL_PROFILE_ID: current_small_account_2026(),
    }
    ordered = sorted(
        (dict(row) for row in scanner_rows),
        key=lambda row: (str(row.get("decision_time")), str(row.get("symbol"))),
    )
    if list(scanner_rows) != ordered:
        raise ValueError("scanner rows must be in canonical chronological order")
    first: dict[tuple[str, str], tuple[dict[str, object], dict[str, object]]] = {}
    annotated: list[dict[str, object]] = []
    for row in ordered:
        symbol = str(row.get("symbol") or "")
        decision = _aware(row.get("decision_time"), "scanner decision_time")
        if not _SYMBOL.fullmatch(symbol):
            raise ValueError("scanner runtime contains an invalid symbol")
        states: dict[str, object] = {}
        for profile_id in STRATEGY_PROFILE_IDS:
            state = profile_eligibility(row, profiles[profile_id])
            states[profile_id] = state
            if state["quality"] != CandidateQuality.REJECT.value:
                first.setdefault((symbol, profile_id), (row, state))
        annotated.append({**row, "profile_eligibility": states})

    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for (symbol, profile_id), (row, _state) in first.items():
        decision = str(row["decision_time"])
        grouped.setdefault(
            (symbol, decision),
            {
                "symbol": symbol,
                "candidate_qualified_at": decision,
                "scanner_record_content_sha256": canonical_fingerprint(row),
                "profiles": [],
            },
        )["profiles"].append(profile_id)  # type: ignore[index]
    activations: list[ProfileActivation] = []
    for (_symbol, _decision), value in sorted(
        grouped.items(), key=lambda item: (item[0][1], item[0][0])
    ):
        profiles_for_activation = tuple(
            profile_id
            for profile_id in STRATEGY_PROFILE_IDS
            if profile_id in value["profiles"]
        )
        identity = canonical_fingerprint(
            {
                "panel_id": PANEL_ID,
                "scanner_runtime_content_sha256": scanner_runtime_content_sha256,
                "symbol": value["symbol"],
                "candidate_qualified_at": value["candidate_qualified_at"],
                "scanner_record_content_sha256": value[
                    "scanner_record_content_sha256"
                ],
            }
        )
        activations.append(
            ProfileActivation(
                activation_id=f"activation-{identity}",
                symbol=str(value["symbol"]),
                candidate_qualified_at=str(value["candidate_qualified_at"]),
                scanner_record_content_sha256=str(
                    value["scanner_record_content_sha256"]
                ),
                eligible_strategy_profile_ids=profiles_for_activation,
            )
        )
    return activations, annotated


def _json_value(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return "positive_infinity" if value > 0 else "negative_infinity"
        return value
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    if hasattr(value, "item"):
        return _json_value(value.item())
    return str(value)


def _frame_prefix(frame: pd.DataFrame, *, through: pd.Timestamp) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for timestamp, source in frame.loc[:through].iterrows():
        rows.append(
            {
                "timestamp": pd.Timestamp(timestamp).isoformat(),
                **{str(key): _json_value(value) for key, value in source.items()},
            }
        )
    return rows


def build_micro_trigger_decisions(
    activation: ProfileActivation,
    *,
    bars: pd.DataFrame,
    trades: pd.DataFrame,
    support: pd.DataFrame,
    replay_end: pd.Timestamp,
) -> list[MicroTriggerDecision]:
    """Emit trigger-time decisions without simulating a fill or later outcome."""

    policy = micro_v0_1_policy()
    if policy.fingerprint != MICRO_POLICY_FINGERPRINT:
        raise RuntimeError("Micro v0.1 differs from the registered fingerprint")
    qualified = pd.Timestamp(activation.candidate_qualified_at)
    if qualified.tzinfo is None or replay_end.tzinfo is None:
        raise ValueError("Micro replay timestamps must be timezone-aware")
    if qualified >= replay_end:
        raise ValueError("Micro activation must precede the entry cutoff")
    validate_bars(bars)
    if not isinstance(trades.index, pd.DatetimeIndex) or trades.index.tz is None:
        raise ValueError("Micro trades must use a timezone-aware DatetimeIndex")
    if not isinstance(support.index, pd.DatetimeIndex) or support.index.tz is None:
        raise ValueError("Micro support must use a timezone-aware DatetimeIndex")
    chart = price_eligible_trades(trades)
    outputs: list[MicroTriggerDecision] = []
    action_bars = bars.loc[
        (bars.index >= qualified)
        & (bars.index + pd.Timedelta(seconds=policy.micro_bar_interval_seconds) < replay_end)
    ]
    for timestamp in action_bars.index:
        prefix = action_bars.loc[:timestamp]
        pullback_number = causal_active_pullback_number(
            prefix,
            candidate_qualified_at=qualified,
        )
        evaluation = evaluate_micro_pullback_plan(
            activation.symbol,
            prefix,
            candidate_qualified_at=qualified,
            policy=policy.setup,
            pullback_number=pullback_number,
            vwap_available=support["vwap"],
            ema9_available=support["ema"],
        )
        plan = evaluation.plan
        if plan is None:
            continue
        window = chart.loc[
            (chart.index >= plan.armed_at)
            & (chart.index < plan.expires_at)
            & (chart.index < replay_end)
        ]
        prices = pd.to_numeric(window.get("price"), errors="coerce")
        crossing = window.loc[prices >= plan.minimum_new_high_price]
        if crossing.empty:
            continue
        decision_at = pd.Timestamp(crossing.index[0])
        plan_payload = {
            "symbol": plan.symbol,
            "source_bar_start": plan.source_bar_start.isoformat(),
            "armed_at": plan.armed_at.isoformat(),
            "expires_at": plan.expires_at.isoformat(),
            "breakout_level": plan.breakout_level,
            "minimum_new_high_price": plan.minimum_new_high_price,
            "stop_price": plan.stop_price,
            "pullback_number": pullback_number,
        }
        plan_id = f"plan-{canonical_fingerprint({'activation_id': activation.activation_id, 'plan': plan_payload})}"
        causal_prefix = {
            "activation_id": activation.activation_id,
            "candidate_qualified_at": activation.candidate_qualified_at,
            "policy_fingerprint": policy.fingerprint,
            "plan_id": plan_id,
            "plan": plan_payload,
            "micro_bars_through_plan": _frame_prefix(prefix, through=timestamp),
            "support_through_plan": _frame_prefix(
                support.loc[support.index <= timestamp], through=timestamp
            ),
            "chart_trades_through_trigger": _frame_prefix(
                chart.loc[
                    (chart.index >= qualified) & (chart.index <= decision_at)
                ],
                through=decision_at,
            ),
            "decision_at": decision_at.isoformat(),
        }
        outputs.append(
            MicroTriggerDecision(
                activation_id=activation.activation_id,
                plan_id=plan_id,
                symbol=activation.symbol,
                candidate_qualified_at=activation.candidate_qualified_at,
                decision_at=decision_at.isoformat(),
                micro_runtime_content_sha256=canonical_fingerprint(causal_prefix),
                eligible_strategy_profile_ids=(
                    activation.eligible_strategy_profile_ids
                ),
                plan=plan_payload,
            )
        )
    ordered = sorted(
        outputs,
        key=lambda row: (row.decision_at, row.symbol, row.plan_id),
    )
    seen: set[tuple[str, str, str]] = set()
    for row in ordered:
        key = (row.activation_id, row.plan_id, row.decision_at)
        if key in seen:
            raise ValueError("Micro trigger runtime repeats a decision")
        seen.add(key)
    return ordered


def build_scanner_runtime(
    *,
    trading_date: str,
    prerequisite_content_sha256: str,
    scanner_rows: Sequence[Mapping[str, object]],
    scanner_lineage: Mapping[str, object],
) -> dict[str, object]:
    """Freeze the complete account-neutral union scanner minute ledger."""

    session = _registered_date(trading_date)
    if not _is_sha256(prerequisite_content_sha256):
        raise ValueError("prerequisite content hash is invalid")
    ordered_rows = sorted(
        (dict(row) for row in scanner_rows),
        key=lambda row: (str(row.get("decision_time")), str(row.get("symbol"))),
    )
    if list(scanner_rows) != ordered_rows:
        raise ValueError("scanner rows are not in canonical order")
    return _fingerprinted(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_id": f"prospective-causal-union-scanner-{trading_date}",
            "artifact_type": SCANNER_ARTIFACT_TYPE,
            "contract_id": CONTRACT_ID,
            "panel_id": PANEL_ID,
            "trading_date": trading_date,
            "prerequisite_content_sha256": prerequisite_content_sha256,
            "union_acquisition_profile": strategy_profile_manifest(
                union_acquisition_profile()
            ),
            "general_profile_fingerprint": GENERAL_PROFILE_FINGERPRINT,
            "small_profile_fingerprint": SMALL_PROFILE_FINGERPRINT,
            "row_count": len(ordered_rows),
            "ordered_records_sha256": ordered_snapshot_records_fingerprint(
                ordered_rows
            ),
            "lineage": dict(sorted(scanner_lineage.items())),
            "rows": ordered_rows,
            "account_snapshot_loaded": False,
            "account_scarcity_applied": False,
            "retrospective_labels_loaded": False,
            "later_prices_or_pnl_loaded": False,
        }
    )


def build_daily_artifacts(
    *,
    scanner_runtime: Mapping[str, object],
    trigger_decisions: Sequence[MicroTriggerDecision],
) -> ProspectiveDailyArtifacts:
    """Bind a frozen scanner runtime, Micro triggers, and the source schema."""

    if scanner_runtime.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported scanner runtime schema")
    if scanner_runtime.get("artifact_type") != SCANNER_ARTIFACT_TYPE:
        raise ValueError("unexpected scanner runtime artifact")
    trading_date = str(scanner_runtime.get("trading_date") or "")
    session = _registered_date(trading_date)
    unsigned_scanner = {
        key: value
        for key, value in scanner_runtime.items()
        if key != "content_sha256"
    }
    scanner_hash = str(scanner_runtime.get("content_sha256") or "")
    if scanner_hash != canonical_fingerprint(unsigned_scanner):
        raise ValueError("scanner runtime content hash mismatch")
    prerequisite_content_sha256 = str(
        scanner_runtime.get("prerequisite_content_sha256") or ""
    )
    if not _is_sha256(prerequisite_content_sha256):
        raise ValueError("scanner prerequisite hash is invalid")
    raw_rows = scanner_runtime.get("rows")
    if not isinstance(raw_rows, list) or not all(
        isinstance(row, Mapping) for row in raw_rows
    ):
        raise ValueError("scanner runtime rows are invalid")
    ordered_rows = [dict(row) for row in raw_rows]
    activations, annotated_rows = build_profile_activations(
        scanner_runtime_content_sha256=scanner_hash,
        scanner_rows=ordered_rows,
    )
    del annotated_rows
    activation_index = {row.activation_id: row for row in activations}
    ordered_triggers = sorted(
        trigger_decisions,
        key=lambda row: (row.decision_at, row.symbol, row.plan_id),
    )
    for row in ordered_triggers:
        activation = activation_index.get(row.activation_id)
        if activation is None:
            raise ValueError("Micro trigger does not bind a frozen profile activation")
        if (
            row.symbol != activation.symbol
            or row.candidate_qualified_at != activation.candidate_qualified_at
            or row.eligible_strategy_profile_ids
            != activation.eligible_strategy_profile_ids
        ):
            raise ValueError("Micro trigger activation binding changed")
    micro_runtime = _fingerprinted(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_id": f"prospective-causal-micro-triggers-{trading_date}",
            "artifact_type": MICRO_ARTIFACT_TYPE,
            "contract_id": CONTRACT_ID,
            "panel_id": PANEL_ID,
            "trading_date": trading_date,
            "scanner_runtime_content_sha256": scanner_hash,
            "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
            "activation_count": len(activations),
            "activations": [asdict(row) for row in activations],
            "decision_count": len(ordered_triggers),
            "decisions": [asdict(row) for row in ordered_triggers],
            "decision_semantics": (
                "first_chart_price_crossing_inside_each_causal_armed_plan_window"
            ),
            "fills_simulated": False,
            "exits_simulated": False,
            "account_snapshot_loaded": False,
            "account_scarcity_applied": False,
            "execution_scenario_applied": False,
            "retrospective_labels_loaded": False,
            "later_outcomes_loaded": False,
        }
    )
    source_inputs = [
        {
            "activation_id": row.activation_id,
            "plan_id": row.plan_id,
            "symbol": row.symbol,
            "candidate_qualified_ts_ns": int(
                _aware(row.candidate_qualified_at, "candidate_qualified_at")
                .astimezone(UTC)
                .timestamp()
                * 1_000_000_000
            ),
            "decision_ts_ns": int(
                _aware(row.decision_at, "decision_at")
                .astimezone(UTC)
                .timestamp()
                * 1_000_000_000
            ),
            "micro_runtime_content_sha256": row.micro_runtime_content_sha256,
            "eligible_strategy_profile_ids": list(
                row.eligible_strategy_profile_ids
            ),
        }
        for row in ordered_triggers
    ]
    decision_source = build_daily_decision_source(
        trading_date=session.isoformat(),
        scanner_runtime_content_sha256=scanner_hash,
        micro_runtime_manifest_content_sha256=str(
            micro_runtime["content_sha256"]
        ),
        candidate_count=len(activations),
        decisions=source_inputs,
    )
    validate_daily_decision_source(decision_source)
    producer_manifest = _fingerprinted(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_id": f"prospective-daily-source-bundle-{trading_date}",
            "artifact_type": PRODUCER_ARTIFACT_TYPE,
            "contract_id": CONTRACT_ID,
            "trading_date": trading_date,
            "prerequisite_content_sha256": prerequisite_content_sha256,
            "scanner_runtime_content_sha256": scanner_hash,
            "micro_runtime_content_sha256": micro_runtime["content_sha256"],
            "decision_source_content_sha256": decision_source[
                "content_sha256"
            ],
            "profile_activation_count": len(activations),
            "decision_count": len(ordered_triggers),
            "zero_opportunity_date": len(ordered_triggers) == 0,
            "opportunity_freeze_contract_content_sha256": (
                OPPORTUNITY_FREEZE_CONTRACT_CONTENT_SHA256
            ),
            "provider_quote_made": False,
            "databento_request_made": False,
            "broker_order_made": False,
            "paper_order_made": False,
            "retrospective_labels_loaded": False,
            "later_prices_or_pnl_used_for_selection": False,
        }
    )
    return ProspectiveDailyArtifacts(
        scanner_runtime=dict(scanner_runtime),
        micro_runtime=micro_runtime,
        decision_source=decision_source,
        producer_manifest=producer_manifest,
    )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _empty_output_directory(path: Path) -> None:
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise FileExistsError("prospective source output must be absent or empty")
    else:
        path.mkdir(parents=True)


def write_pre_session_prerequisites(
    path: str | Path,
    payload: Mapping[str, object],
) -> None:
    validate_pre_session_prerequisites(payload)
    target = Path(path)
    _empty_output_directory(target)
    _write_json(target / PREREQUISITE_FILE, payload)


def load_pre_session_prerequisites(path: str | Path) -> dict[str, object]:
    source = Path(path)
    if source.is_dir():
        source = source / PREREQUISITE_FILE
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("pre-session prerequisite root must be an object")
    return validate_pre_session_prerequisites(payload)


def write_daily_artifacts(
    path: str | Path,
    artifacts: ProspectiveDailyArtifacts,
) -> None:
    target = Path(path)
    _empty_output_directory(target)
    _write_json(target / SCANNER_FILE, artifacts.scanner_runtime)
    _write_json(target / MICRO_FILE, artifacts.micro_runtime)
    _write_json(target / SOURCE_FILE, artifacts.decision_source)
    _write_json(target / MANIFEST_FILE, artifacts.producer_manifest)


def capture_pre_session_from_providers(
    *,
    trading_date: str,
    alpaca: AlpacaDataClient,
    sec: SecEdgarClient,
    runtime_head_sha: str,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    workflow_context: Mapping[str, str] | None = None,
) -> dict[str, object]:
    started = now()
    session = _registered_date(trading_date)
    if started.tzinfo is None:
        raise ValueError("pre-session capture clock must be timezone-aware")
    if _local_date(started) != session:
        raise ValueError("pre-session capture must run on its New York date")
    if _local_time(started) >= STRATEGY_START:
        raise ValueError("pre-session capture must start before 07:00 New York")
    assets = alpaca.assets()
    ticker_rows = sec.company_tickers_exchange()
    completed = now()
    return build_pre_session_prerequisites(
        trading_date=trading_date,
        capture_started_at=started,
        capture_completed_at=completed,
        runtime_head_sha=runtime_head_sha,
        asset_rows=assets,
        sec_ticker_rows=ticker_rows,
        workflow_context=workflow_context,
    )


def _active_membership(
    prerequisite: Mapping[str, object],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    assets_raw = prerequisite.get("asset_census")
    tickers_raw = prerequisite.get("sec_ticker_crosswalk")
    if not isinstance(assets_raw, list) or not isinstance(tickers_raw, list):
        raise ValueError("prerequisite membership inputs are missing")
    cik_by_ticker = {
        str(row["ticker"]): str(row["cik"])
        for row in tickers_raw
        if isinstance(row, Mapping)
    }
    assets = [
        dict(row)
        for row in assets_raw
        if isinstance(row, Mapping)
        and str(row.get("status") or "").lower() == "active"
        and row.get("tradable") is True
        and str(row.get("exchange") or "").upper() in _ALLOWED_EXCHANGES
        and _SYMBOL.fullmatch(str(row.get("symbol") or ""))
    ]
    assets.sort(key=lambda row: (str(row["symbol"]), str(row["asset_id"])))
    symbols = [str(row["symbol"]) for row in assets]
    if not symbols or len(symbols) != len(set(symbols)):
        raise ValueError("active prospective membership is empty or repeats a symbol")
    membership = [
        {
            "ticker": str(row["symbol"]),
            "selected_cik": cik_by_ticker.get(str(row["symbol"]), ""),
            "selected_composite_figi": "",
            "identity_identifier_kind": "alpaca_asset_id_pre_session",
            "identity_identifier": str(row["asset_id"]),
        }
        for row in assets
    ]
    return assets, membership


def _previous_split_close(
    frame: pd.DataFrame,
    *,
    trading_date: date,
) -> float | None:
    if frame.empty or frame.index.tz is None:
        return None
    local_dates = frame.index.tz_convert(ET).date
    eligible = frame.loc[local_dates < trading_date]
    if eligible.empty or "close" not in eligible:
        return None
    try:
        value = float(eligible.iloc[-1]["close"])
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def reacquire_rank_inputs(
    alpaca: AlpacaDataClient,
    *,
    trading_date: date,
    membership_symbols: Sequence[str],
    profile: StrategyProfile,
    asset_batch_size: int,
) -> tuple[dict[str, float], dict[str, pd.DataFrame]]:
    if asset_batch_size <= 0:
        raise ValueError("asset batch size must be positive")
    symbols = sorted(str(value).strip().upper() for value in membership_symbols)
    daily_start = datetime.combine(
        trading_date - timedelta(days=RANK_PRIOR_CLOSE_LOOKBACK_CALENDAR_DAYS),
        time(0),
        timezone.utc,
    )
    daily_end = _same_date_historical_sip_end(trading_date)
    daily = alpaca.bars_batched(
        symbols,
        batch_size=asset_batch_size,
        timeframe=RANK_PREVIOUS_CLOSE_TIMEFRAME,
        start=daily_start,
        end=daily_end,
        feed=RANK_HISTORICAL_FEED,
        adjustment=RANK_PREVIOUS_CLOSE_ADJUSTMENT,
        asof=trading_date,
    )
    feature_start = datetime.combine(
        trading_date, profile.volume_feature_start, ET
    ).astimezone(timezone.utc)
    cutoff = datetime.combine(
        trading_date, profile.no_new_entries_after, ET
    ).astimezone(timezone.utc)
    minutes = alpaca.bars_batched(
        symbols,
        batch_size=asset_batch_size,
        timeframe=RANK_MINUTE_TIMEFRAME,
        start=feature_start,
        end=cutoff,
        feed=RANK_HISTORICAL_FEED,
        adjustment=RANK_MINUTE_ADJUSTMENT,
        asof=trading_date,
    )
    quarantined = sorted(set(symbols) & set(alpaca.invalid_symbols))
    if quarantined:
        raise RuntimeError(
            "rank acquisition rejected frozen membership symbols: "
            + ",".join(quarantined)
        )
    previous = {
        symbol: close
        for symbol in symbols
        if (
            close := _previous_split_close(
                daily.get(symbol, pd.DataFrame()), trading_date=trading_date
            )
        )
        is not None
    }
    trimmed = {
        symbol: trim_scanner_bar_frame(
            frame,
            trading_date=trading_date,
            start=profile.volume_feature_start,
            cutoff=profile.no_new_entries_after,
            label=f"rank bars for {symbol}",
        )
        for symbol, frame in minutes.items()
    }
    return previous, trimmed


def _empty_float_record(
    candidate: Mapping[str, object],
    *,
    cik: str,
    status: str,
) -> dict[str, object]:
    selected = {
        "symbol": candidate["symbol"],
        "cik": cik,
        "first_market_qualified_bar_started_at": candidate[
            "first_market_qualified_bar_started_at"
        ],
        "first_market_qualified_at": candidate["first_market_qualified_at"],
        "public_float": None,
        "anchor_outstanding": None,
        "current_outstanding": None,
    }
    return build_causal_float_record(selected, {}, sec_status=status)


def _sec_payload(
    function: Callable[[], dict[str, object]],
    *,
    missing_status: str,
) -> tuple[dict[str, object] | None, str]:
    try:
        return function(), "success"
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None, missing_status
        raise RuntimeError(f"SEC provider HTTP error {error.code}") from error
    except Exception as error:
        raise RuntimeError(f"SEC provider error: {type(error).__name__}") from error


def _basis_query_window(
    requested_dates: Sequence[date],
    *,
    trading_date: date,
) -> tuple[datetime, datetime]:
    start = datetime.combine(
        min(requested_dates) - timedelta(days=14), time(0), timezone.utc
    )
    desired_end = datetime.combine(
        max(requested_dates) + timedelta(days=15), time(0), timezone.utc
    )
    causal_end = _same_date_historical_sip_end(trading_date)
    return start, min(desired_end, causal_end)


def build_float_records_from_providers(
    *,
    candidates: Sequence[Mapping[str, object]],
    trading_date: date,
    alpaca: AlpacaDataClient,
    sec: SecEdgarClient,
    minimum_sec_request_interval: float = 0.2,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for candidate in candidates:
        symbol = str(candidate["symbol"])
        raw_cik = str(candidate.get("selected_cik") or "")
        try:
            cik = normalize_cik(raw_cik)
        except ValueError:
            records.append(
                _empty_float_record(
                    candidate, cik=raw_cik, status="missing_sec_ticker_identity"
                )
            )
            continue
        submissions, submissions_status = _sec_payload(
            lambda cik=cik: sec.submissions(cik),
            missing_status="submissions_not_found",
        )
        clock.sleep(max(0.0, minimum_sec_request_interval))
        facts_payload, facts_status = _sec_payload(
            lambda cik=cik: sec.companyfacts(cik),
            missing_status="companyfacts_not_found",
        )
        clock.sleep(max(0.0, minimum_sec_request_interval))
        if facts_payload is None:
            records.append(
                _empty_float_record(candidate, cik=cik, status=facts_status)
            )
            continue
        try:
            if normalize_cik(facts_payload.get("cik", "")) != cik:
                raise ValueError("companyfacts CIK mismatch")
            if submissions is not None and normalize_cik(
                submissions.get("cik", "")
            ) != cik:
                raise ValueError("submissions CIK mismatch")
            acceptance = (
                parse_submission_acceptance_times(submissions)
                if submissions is not None
                else {}
            )
            facts = parse_companyfacts(
                facts_payload, acceptance_times=acceptance
            )
            qualified = _aware(
                candidate["first_market_qualified_at"],
                "candidate qualification",
            )
            bar_started = _aware(
                candidate["first_market_qualified_bar_started_at"],
                "candidate qualification bar",
            )
            selected = select_float_evidence(
                facts,
                symbol=symbol,
                cik=cik,
                first_market_qualified_at=qualified,
                first_market_qualified_bar_started_at=bar_started,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError(f"invalid SEC payload for {symbol}") from error
        tagged: list[tuple[str, date]] = []
        for tag, key in (
            ("public", "public_float"),
            ("anchor", "anchor_outstanding"),
            ("current", "current_outstanding"),
        ):
            disclosure = selected.get(key)
            if isinstance(disclosure, Mapping):
                tagged.append((tag, date.fromisoformat(str(disclosure["measure_date"]))))
        observations: dict[str, BasisObservation] = {}
        if tagged:
            start, end = _basis_query_window(
                [value for _tag, value in tagged], trading_date=trading_date
            )
            raw = alpaca.bars(
                [symbol],
                timeframe="1Day",
                start=start,
                end=end,
                feed="sip",
                adjustment="raw",
                asof=trading_date,
            ).get(symbol, pd.DataFrame())
            split = alpaca.bars(
                [symbol],
                timeframe="1Day",
                start=start,
                end=end,
                feed="sip",
                adjustment="split",
                asof=trading_date,
            ).get(symbol, pd.DataFrame())
            for tag, requested in tagged:
                observations[f"{tag}:{requested.isoformat()}"] = observe_basis(
                    raw, split, requested
                )
        status = "success_exact_or_conservative_availability"
        if submissions_status != "success":
            status = "success_companyfacts_with_conservative_availability"
        records.append(
            build_causal_float_record(
                selected,
                observations,
                sec_status=status,
            )
        )
    return sorted(records, key=lambda row: str(row["symbol"]))


def _validate_discovery_completeness(
    result: DiscoveryResult,
    *,
    trading_date: date,
    assets: Sequence[Mapping[str, object]],
    membership_symbols: Sequence[str],
    profile: StrategyProfile,
) -> None:
    """Require one internally consistent acquisition decision per member."""

    symbols = sorted(str(value) for value in membership_symbols)
    if result.asset_count != len(symbols) or result.listed_asset_count != len(
        symbols
    ):
        raise RuntimeError("market discovery did not consume complete membership")
    if result.asset_master_sha256 != asset_master_fingerprint(
        [dict(row) for row in assets]
    ):
        raise RuntimeError("market discovery asset census fingerprint changed")
    audit_symbols = [row.symbol for row in result.acquisition_audit]
    if len(audit_symbols) != len(set(audit_symbols)) or sorted(
        audit_symbols
    ) != symbols:
        raise RuntimeError("market discovery did not decide every frozen member")

    def timing(
        bar_started_at: str | None,
        decision_at: str | None,
        *,
        context: str,
    ) -> tuple[str, str] | None:
        if bar_started_at is None and decision_at is None:
            return None
        if bar_started_at is None or decision_at is None:
            raise RuntimeError(f"{context} has incomplete qualification timing")
        bar = _aware(bar_started_at, f"{context} bar")
        decision = _aware(decision_at, f"{context} decision")
        if decision != bar + timedelta(minutes=1):
            raise RuntimeError(f"{context} decision availability changed")
        if _local_date(decision) != trading_date or not (
            profile.session_start
            <= _local_time(decision)
            < profile.no_new_entries_after
        ):
            raise RuntimeError(f"{context} falls outside the scan window")
        return (
            bar.astimezone(UTC).isoformat(),
            decision.astimezone(UTC).isoformat(),
        )

    result_timings: dict[str, tuple[str, str]] = {}
    seen_rows: set[str] = set()
    for row in result.rows:
        if row.symbol not in symbols or row.symbol in seen_rows:
            raise RuntimeError(
                "market discovery records changed membership identity"
            )
        seen_rows.add(row.symbol)
        pair = timing(
            row.first_market_qualified_bar_started_at,
            row.first_market_qualified_at,
            context=f"market discovery record {row.symbol}",
        )
        if pair is not None:
            result_timings[row.symbol] = pair
    if result.market_candidate_count != len(result_timings):
        raise RuntimeError("market discovery candidate count is inconsistent")

    audit_timings: dict[str, tuple[str, str]] = {}
    for row in result.acquisition_audit:
        pair = timing(
            row.first_market_qualified_bar_started_at,
            row.first_market_qualified_at,
            context=f"market discovery audit {row.symbol}",
        )
        if row.causal_market_qualified != (pair is not None):
            raise RuntimeError("market discovery audit qualification changed")
        if pair is not None:
            audit_timings[row.symbol] = pair
        if not row.daily_scan_basis_available:
            raise RuntimeError(
                f"market discovery lacks daily scan basis for {row.symbol}"
            )
        if (
            row.raw_target_minute_bars_present
            and not row.split_target_minute_bars_present
        ):
            raise RuntimeError(
                "market discovery raw/split minute coverage differs for "
                + row.symbol
            )
        if (
            row.exact_rvol_evaluated
            and not row.exact_rvol_observation_available
        ):
            raise RuntimeError(
                f"market discovery lacks exact RVOL observation for {row.symbol}"
            )
    if audit_timings != result_timings:
        raise RuntimeError(
            "market discovery audit and candidate records disagree"
        )


def build_news_records_from_provider(
    *,
    candidates: Sequence[Mapping[str, object]],
    trading_date: date,
    alpaca: AlpacaDataClient,
    batch_size: int = 50,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    calendar_start = datetime.combine(
        trading_date - timedelta(days=14), time(0), timezone.utc
    )
    calendar_end = _same_date_historical_sip_end(trading_date)
    calendar = alpaca.bars(
        ["SPY"],
        timeframe="1Day",
        start=calendar_start,
        end=calendar_end,
        feed="sip",
        adjustment="raw",
        asof=trading_date,
    ).get("SPY", pd.DataFrame())
    prior = prior_regular_session_date(calendar, trading_date=trading_date)
    window_start, window_end = publication_window(
        trading_date=trading_date, prior_session=prior
    )
    symbols = sorted(str(row["symbol"]) for row in candidates)
    raw: list[dict[str, object]] = []
    for batch in chunked(symbols, batch_size):
        try:
            raw.extend(
                alpaca.news(
                    batch,
                    start=window_start,
                    end=window_end,
                    include_content=False,
                )
            )
        except Exception as error:
            raise RuntimeError(
                "Alpaca news acquisition failed; date cannot emit a source"
            ) from error
    events, dispositions = normalize_alpaca_news(
        raw,
        candidate_symbols=set(symbols),
        window_start=window_start,
        window_end=window_end,
    )
    statuses = build_news_candidate_statuses(
        candidates,
        events,
        provider_status_by_symbol={symbol: "success" for symbol in symbols},
    )
    validate_publication_timed_news(
        candidates,
        events,
        statuses,
        window_start=window_start,
        window_end=window_end,
    )
    manifest = _fingerprinted(
        {
            "policy": causal_news_v0_2_manifest(),
            "trading_date": trading_date.isoformat(),
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "raw_provider_row_count": len(raw),
            "normalization_dispositions": dispositions,
            "event_count": len(events),
            "event_sha256": news_events_fingerprint(events),
            "status_sha256": news_statuses_fingerprint(statuses),
        }
    )
    return events, statuses, manifest


def produce_daily_source_from_providers(
    *,
    prerequisite: Mapping[str, object],
    alpaca: AlpacaDataClient,
    sec: SecEdgarClient,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    asset_batch_size: int = 250,
    news_batch_size: int = 50,
    minimum_sec_request_interval: float = 0.2,
) -> ProspectiveDailyArtifacts:
    """Run one post-session, label-blind causal scanner/Micro reconstruction."""

    frozen = validate_pre_session_prerequisites(prerequisite)
    session = _registered_date(str(frozen["trading_date"]))
    current = now()
    if current.tzinfo is None:
        raise ValueError("producer clock must be timezone-aware")
    if _local_date(current) != session:
        raise ValueError("daily source production must run on its New York date")
    if _local_time(current) < PRODUCTION_NOT_BEFORE:
        raise ValueError("daily source production cannot run before 10:20 New York")
    if asset_batch_size <= 0 or news_batch_size <= 0:
        raise ValueError("provider batch sizes must be positive")
    if minimum_sec_request_interval < 0:
        raise ValueError("SEC request interval cannot be negative")

    profile = union_acquisition_profile()
    assets, membership = _active_membership(frozen)
    membership_symbols = [str(row["ticker"]) for row in membership]
    result = discover_market_day(
        alpaca,
        trading_date=session,
        profile=profile,
        asset_batch_size=asset_batch_size,
        assets=assets,
        daily_bar_end=_same_date_historical_sip_end(session),
    )
    quarantined = sorted(
        set(membership_symbols)
        & set(getattr(alpaca, "invalid_symbols", ()))
    )
    if quarantined:
        raise RuntimeError(
            "market discovery rejected frozen membership symbols: "
            + ",".join(quarantined)
        )
    _validate_discovery_completeness(
        result,
        trading_date=session,
        assets=assets,
        membership_symbols=membership_symbols,
        profile=profile,
    )
    candidate_payload = build_market_candidate_payload(
        trading_date=session.isoformat(),
        membership_rows=membership,
        result=result,
    )
    candidates_raw = candidate_payload.get("rows")
    if not isinstance(candidates_raw, list) or not all(
        isinstance(row, Mapping) for row in candidates_raw
    ):
        raise RuntimeError("market discovery candidate payload is invalid")
    candidates = [dict(row) for row in candidates_raw]
    discovery_manifest = _fingerprinted(
        {
            "trading_date": session.isoformat(),
            "prerequisite_content_sha256": frozen["content_sha256"],
            "union_acquisition_profile": strategy_profile_manifest(profile),
            "active_membership_count": len(membership),
            "active_membership_sha256": canonical_fingerprint(membership),
            "discovery_record_count": len(result.rows),
            "discovery_records_sha256": discovery_records_fingerprint(result),
            "acquisition_decision_count": len(result.acquisition_audit),
            "acquisition_disposition_counts": dict(
                sorted(
                    Counter(
                        row.disposition for row in result.acquisition_audit
                    ).items()
                )
            ),
            "acquisition_audit_sha256": discovery_audit_fingerprint(result),
            "candidate_count": len(candidates),
            "candidate_payload_sha256": candidate_payload["content_sha256"],
            "full_day_high_used_for_acquisition_only": False,
            "same_date_daily_bar_end": _same_date_historical_sip_end(
                session
            ).isoformat(),
            "daily_extrema_after_same_date_daily_bar_end_loaded": False,
            "future_session_extrema_used_by_strategy": False,
        }
    )

    if candidates:
        float_records = build_float_records_from_providers(
            candidates=candidates,
            trading_date=session,
            alpaca=alpaca,
            sec=sec,
            minimum_sec_request_interval=minimum_sec_request_interval,
        )
        events, statuses, news_manifest = build_news_records_from_provider(
            candidates=candidates,
            trading_date=session,
            alpaca=alpaca,
            batch_size=news_batch_size,
        )
        previous, rank_frames = reacquire_rank_inputs(
            alpaca,
            trading_date=session,
            membership_symbols=membership_symbols,
            profile=profile,
            asset_batch_size=asset_batch_size,
        )
        candidate_frames = {
            symbol: trim_scanner_bar_frame(
                frame,
                trading_date=session,
                start=profile.volume_feature_start,
                cutoff=profile.no_new_entries_after,
                acquisition_end=UPSTREAM_MARKET_ACQUISITION_TAIL_END,
                label=f"candidate bars for {symbol}",
            )
            for symbol, frame in result.minutes.items()
        }
        candidate_rvol = {
            symbol: trim_scanner_rvol_series(
                series,
                trading_date=session,
                start=profile.volume_feature_start,
                cutoff=profile.no_new_entries_after,
                acquisition_end=UPSTREAM_MARKET_ACQUISITION_TAIL_END,
                label=f"candidate RVOL for {symbol}",
            )
            for symbol, series in result.rvol_curves.items()
        }
        bound_candidate_frames = bind_candidate_frames_to_reacquired_rank_frames(
            membership_symbols=membership_symbols,
            reacquired_rank_frames=rank_frames,
            authoritative_candidate_frames=candidate_frames,
        )
        scanner_rows = build_scanner_snapshot_rows(
            trading_date=session,
            profile=profile,
            candidate_rows=candidates,
            float_records=float_records,
            news_events=events,
            news_statuses=statuses,
            membership_symbols=membership_symbols,
            previous_close_by_symbol=previous,
            rank_raw_minute_bars_by_symbol=rank_frames,
            candidate_raw_minute_bars_by_symbol=bound_candidate_frames,
            candidate_exact_rvol_by_symbol=candidate_rvol,
        )
        market_inputs_sha = market_inputs_fingerprint(
            trading_date=session,
            profile=profile,
            membership_symbols=membership_symbols,
            previous_close_by_symbol=previous,
            rank_raw_minute_bars_by_symbol=rank_frames,
            candidate_raw_minute_bars_by_symbol=bound_candidate_frames,
            candidate_exact_rvol_by_symbol=candidate_rvol,
        )
        float_manifest = _fingerprinted(
            {
                "policy": causal_float_v0_1_manifest(),
                "trading_date": session.isoformat(),
                "candidate_count": len(candidates),
                "records_sha256": causal_float_records_fingerprint(
                    float_records
                ),
                "classification_counts": dict(
                    sorted(
                        Counter(
                            str(row["float_classification"])
                            for row in float_records
                        ).items()
                    )
                ),
            }
        )
        scanner_lineage: dict[str, object] = {
            "active_membership_sha256": discovery_manifest[
                "active_membership_sha256"
            ],
            "market_candidates_content_sha256": candidate_payload[
                "content_sha256"
            ],
            "market_discovery_content_sha256": discovery_manifest[
                "content_sha256"
            ],
            "float_records_sha256": float_manifest["records_sha256"],
            "float_manifest_content_sha256": float_manifest["content_sha256"],
            "news_events_sha256": news_manifest["event_sha256"],
            "news_statuses_sha256": news_manifest["status_sha256"],
            "news_manifest_content_sha256": news_manifest["content_sha256"],
            "market_inputs_sha256": market_inputs_sha,
            "broad_market_candidate_count": len(candidates),
        }
    else:
        scanner_rows = []
        bound_candidate_frames = {}
        scanner_lineage = {
            "active_membership_sha256": discovery_manifest[
                "active_membership_sha256"
            ],
            "market_candidates_content_sha256": candidate_payload[
                "content_sha256"
            ],
            "market_discovery_content_sha256": discovery_manifest[
                "content_sha256"
            ],
            "float_records_sha256": canonical_fingerprint([]),
            "float_manifest_content_sha256": canonical_fingerprint(
                {"policy": causal_float_v0_1_manifest(), "records": []}
            ),
            "news_events_sha256": canonical_fingerprint([]),
            "news_statuses_sha256": canonical_fingerprint([]),
            "news_manifest_content_sha256": canonical_fingerprint(
                {"policy": causal_news_v0_2_manifest(), "events": []}
            ),
            "market_inputs_sha256": canonical_fingerprint(
                {"membership": membership_symbols, "candidates": []}
            ),
            "broad_market_candidate_count": 0,
        }

    scanner_runtime = build_scanner_runtime(
        trading_date=session.isoformat(),
        prerequisite_content_sha256=str(frozen["content_sha256"]),
        scanner_rows=scanner_rows,
        scanner_lineage=scanner_lineage,
    )
    activations, _annotated = build_profile_activations(
        scanner_runtime_content_sha256=str(scanner_runtime["content_sha256"]),
        scanner_rows=scanner_rows,
    )
    triggers: list[MicroTriggerDecision] = []
    if activations:
        by_symbol: dict[str, list[ProfileActivation]] = {}
        for activation in activations:
            by_symbol.setdefault(activation.symbol, []).append(activation)
        symbols = sorted(by_symbol)
        session_start = datetime.combine(
            session, VOLUME_FEATURE_START, ET
        ).astimezone(timezone.utc)
        replay_end = pd.Timestamp(
            datetime.combine(session, ENTRY_CUTOFF, ET).astimezone(timezone.utc)
        )
        warmup_start = session_start - timedelta(days=EMA_WARMUP_CALENDAR_DAYS)
        warmup_frames = alpaca.bars_batched(
            symbols,
            batch_size=min(asset_batch_size, 100),
            timeframe="1Min",
            start=warmup_start,
            end=session_start,
            feed="sip",
            adjustment="split",
            asof=session,
        )
        quarantined = sorted(
            set(symbols) & set(getattr(alpaca, "invalid_symbols", ()))
        )
        if quarantined:
            raise RuntimeError(
                "Micro warmup rejected eligible symbols: "
                + ",".join(quarantined)
            )
        for symbol in symbols:
            session_frame = bound_candidate_frames.get(symbol, pd.DataFrame())
            if session_frame.empty:
                raise RuntimeError(
                    f"eligible scanner activation lacks session bars for {symbol}"
                )
            support = completed_bar_support_series(
                session_frame,
                ema_span=current_general_2026().ema_span,
                bar_duration="1min",
                ema_warmup=warmup_frames.get(symbol, pd.DataFrame()),
            )
            earliest = min(
                _aware(row.candidate_qualified_at, "activation")
                for row in by_symbol[symbol]
            )
            trades = historical_trades(
                alpaca,
                symbol,
                start=earliest,
                end=replay_end.to_pydatetime(),
                feed="sip",
                asof=session,
            )
            if trades.empty:
                raise RuntimeError(
                    f"eligible scanner activation lacks SIP trades for {symbol}"
                )
            bars = aggregate_trade_bars(
                trades, f"{micro_v0_1_policy().micro_bar_interval_seconds}s"
            )
            for activation in by_symbol[symbol]:
                triggers.extend(
                    build_micro_trigger_decisions(
                        activation,
                        bars=bars,
                        trades=trades,
                        support=support,
                        replay_end=replay_end,
                    )
                )
    return build_daily_artifacts(
        scanner_runtime=scanner_runtime,
        trigger_decisions=triggers,
    )
