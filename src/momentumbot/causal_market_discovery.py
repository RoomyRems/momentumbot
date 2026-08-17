"""Contracts for label-blind market discovery from historical membership."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
import hashlib
import json
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from .historical_data import DiscoveryResult, asset_master_fingerprint
from .identity_resolved_universe import (
    IDENTITY_RESOLVED_UNIVERSE_POLICY_ID,
    identity_resolved_membership_fingerprint,
)
from .models import StrategyProfile


CAUSAL_MARKET_DISCOVERY_V0_1_POLICY_ID = "causal-market-discovery-v0.1"
CAUSAL_MARKET_DISCOVERY_POLICY_ID = "causal-market-discovery-v0.2"
CAUSAL_MARKET_DISCOVERY_POLICY_STATUS = (
    "frozen_research_acquisition_contract_not_promotable"
)
CAUSAL_MARKET_CANDIDATES_ARTIFACT_ID = "causal-market-candidates-v0.2"
ET = ZoneInfo("America/New_York")
_EXCHANGE_MAP = {
    "ARCX": "ARCA",
    "BATS": "BATS",
    "XASE": "AMEX",
    "XNAS": "NASDAQ",
    "XNYS": "NYSE",
}


def _json_fingerprint(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def strategy_profile_manifest(profile: StrategyProfile) -> dict[str, object]:
    payload = asdict(profile)
    for key, value in tuple(payload.items()):
        if isinstance(value, time):
            payload[key] = value.isoformat()
    return {**payload, "fingerprint": _json_fingerprint(payload)}


@dataclass(frozen=True, slots=True)
class FrozenCausalMarketDiscoveryPolicy:
    policy_id: str
    status: str
    source_universe_policy_id: str
    daily_history_calendar_days: int
    exact_rvol_prior_sessions: int
    exact_rvol_bar_size: str
    coarse_rvol_bar_size: str
    acquisition_prefilter_rule: str
    strategy_input_rule: str
    minute_bar_timestamp_semantics: str | None = None
    decision_availability_rule: str | None = None
    scan_window_timestamp_rule: str | None = None
    supersedes_policy_id: str | None = None
    supersedes_policy_fingerprint: str | None = None

    def payload(self) -> dict[str, object]:
        # Omitting absent extension fields preserves the already-frozen v0.1
        # payload byte-for-byte while allowing v0.2 to state its timing model.
        return {
            key: value
            for key, value in asdict(self).items()
            if value is not None
        }

    @property
    def fingerprint(self) -> str:
        return _json_fingerprint(self.payload())


def causal_market_discovery_v0_1_policy(
) -> FrozenCausalMarketDiscoveryPolicy:
    return FrozenCausalMarketDiscoveryPolicy(
        policy_id=CAUSAL_MARKET_DISCOVERY_V0_1_POLICY_ID,
        status=CAUSAL_MARKET_DISCOVERY_POLICY_STATUS,
        source_universe_policy_id=IDENTITY_RESOLVED_UNIVERSE_POLICY_ID,
        daily_history_calendar_days=120,
        exact_rvol_prior_sessions=50,
        exact_rvol_bar_size="1Min",
        coarse_rvol_bar_size="15Min",
        acquisition_prefilter_rule=(
            "full_day_high_and_coarse_rvol_upper_bound_may_reduce_downloads_only"
        ),
        strategy_input_rule=(
            "only_completed_raw_target_bars_and_exact_same_time_split_rvol"
        ),
    )


def causal_market_discovery_v0_1_manifest() -> dict[str, object]:
    policy = causal_market_discovery_v0_1_policy()
    return {**policy.payload(), "fingerprint": policy.fingerprint}


def causal_market_discovery_v0_2_policy(
) -> FrozenCausalMarketDiscoveryPolicy:
    return FrozenCausalMarketDiscoveryPolicy(
        policy_id=CAUSAL_MARKET_DISCOVERY_POLICY_ID,
        status=CAUSAL_MARKET_DISCOVERY_POLICY_STATUS,
        source_universe_policy_id=IDENTITY_RESOLVED_UNIVERSE_POLICY_ID,
        daily_history_calendar_days=120,
        exact_rvol_prior_sessions=50,
        exact_rvol_bar_size="1Min",
        coarse_rvol_bar_size="15Min",
        acquisition_prefilter_rule=(
            "full_day_high_and_coarse_rvol_upper_bound_may_reduce_downloads_only"
        ),
        strategy_input_rule=(
            "only_completed_raw_target_1min_bars_and_exact_same_time_split_rvol_"
            "at_decision_availability"
        ),
        minute_bar_timestamp_semantics="alpaca_1min_timestamp_is_bar_start",
        decision_availability_rule=(
            "bar_close_and_same_time_rvol_available_at_bar_start_plus_1_minute"
        ),
        scan_window_timestamp_rule=(
            "session_bounds_apply_to_decision_availability_timestamp"
        ),
        supersedes_policy_id=CAUSAL_MARKET_DISCOVERY_V0_1_POLICY_ID,
        supersedes_policy_fingerprint=causal_market_discovery_v0_1_manifest()[
            "fingerprint"
        ],
    )


def causal_market_discovery_v0_2_manifest() -> dict[str, object]:
    policy = causal_market_discovery_v0_2_policy()
    return {**policy.payload(), "fingerprint": policy.fingerprint}


def _qualification_timestamps(
    bar_started_at: object,
    qualified_at: object,
    *,
    context: str,
) -> tuple[datetime, datetime] | None:
    if bar_started_at is None and qualified_at is None:
        return None
    if bar_started_at is None or qualified_at is None:
        raise ValueError(f"{context} qualification timing fields must appear together")
    try:
        bar_started = datetime.fromisoformat(str(bar_started_at))
        decision = datetime.fromisoformat(str(qualified_at))
    except ValueError as error:
        raise ValueError(f"{context} qualification timestamps are invalid") from error
    if bar_started.tzinfo is None or decision.tzinfo is None:
        raise ValueError(f"{context} qualification timestamps must be timezone-aware")
    if decision - bar_started != timedelta(minutes=1):
        raise ValueError(
            f"{context} decision timestamp must equal bar start plus one minute"
        )
    return bar_started, decision


def _validate_decision_scan_window(
    decision: datetime,
    *,
    trading_date: str,
    session_start: time,
    no_new_entries_after: time,
    context: str,
) -> None:
    local = decision.astimezone(ET)
    if local.date().isoformat() != trading_date:
        raise ValueError(f"{context} decision timestamp has the wrong trading date")
    local_time = local.timetz().replace(tzinfo=None)
    if not session_start <= local_time < no_new_entries_after:
        raise ValueError(f"{context} decision timestamp is outside the scan window")


def identity_membership_as_acquisition_assets(
    rows: Iterable[dict[str, object]],
) -> list[dict[str, object]]:
    """Translate frozen Massive/MIC membership into the existing Alpaca fetch shape."""

    output: list[dict[str, object]] = []
    seen: set[str] = set()
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        mic = str(row.get("selected_primary_exchange") or "").strip().upper()
        identifier = str(row.get("identity_identifier") or "").strip()
        if not ticker or not identifier:
            raise ValueError("identity-resolved acquisition row is incomplete")
        if ticker in seen:
            raise ValueError(f"identity-resolved acquisition repeats {ticker}")
        if mic not in _EXCHANGE_MAP:
            raise ValueError(f"unsupported primary exchange {mic!r} for {ticker}")
        seen.add(ticker)
        output.append(
            {
                "class": "us_equity",
                "id": identifier,
                "attributes": [],
                "exchange": _EXCHANGE_MAP[mic],
                "name": "",
                "status": "active",
                "symbol": ticker,
                "tradable": None,
            }
        )
    return sorted(output, key=lambda row: str(row["symbol"]))


def discovery_records_fingerprint(result: DiscoveryResult) -> str:
    rows = sorted(
        (asdict(row) for row in result.rows),
        key=lambda row: str(row["symbol"]),
    )
    return _json_fingerprint(rows)


def discovery_audit_fingerprint(result: DiscoveryResult) -> str:
    rows = sorted(
        (asdict(row) for row in result.acquisition_audit),
        key=lambda row: str(row["symbol"]),
    )
    return _json_fingerprint(rows)


def build_market_candidate_payload(
    *,
    trading_date: str,
    membership_rows: list[dict[str, object]],
    result: DiscoveryResult,
) -> dict[str, object]:
    membership = {str(row["ticker"]): row for row in membership_rows}
    candidates: list[dict[str, object]] = []
    for row in sorted(result.rows, key=lambda item: item.symbol):
        timing = _qualification_timestamps(
            row.first_market_qualified_bar_started_at,
            row.first_market_qualified_at,
            context=f"market candidate {row.symbol}",
        )
        if timing is None:
            continue
        source = membership.get(row.symbol)
        if source is None:
            raise ValueError(f"market candidate {row.symbol} is absent from membership")
        candidates.append(
            {
                "symbol": row.symbol,
                "first_market_qualified_bar_started_at": (
                    row.first_market_qualified_bar_started_at
                ),
                "first_market_qualified_at": row.first_market_qualified_at,
                "previous_close": row.previous_close,
                "average_daily_volume_50": row.average_daily_volume_50,
                "rvol_history_sessions": row.rvol_history_sessions,
                "selected_cik": source.get("selected_cik", ""),
                "selected_composite_figi": source.get(
                    "selected_composite_figi", ""
                ),
                "identity_identifier_kind": source.get(
                    "identity_identifier_kind", ""
                ),
                "identity_identifier": source.get("identity_identifier", ""),
            }
        )
    payload: dict[str, object] = {
        "schema_version": 2,
        "artifact_id": CAUSAL_MARKET_CANDIDATES_ARTIFACT_ID,
        "trading_date": trading_date,
        "source_discovery_policy_fingerprint": (
            causal_market_discovery_v0_2_manifest()["fingerprint"]
        ),
        "source_discovery_records_sha256": discovery_records_fingerprint(result),
        "knowledge_policy": {
            "uses_benchmark_labels": False,
            "uses_retrospective_trade_outcomes": False,
            "selection_applied": False,
        },
        "candidate_count": len(candidates),
        "rows": candidates,
    }
    payload["content_sha256"] = _json_fingerprint(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )
    return payload


def load_market_candidate_payload(
    date_root: str | Path,
) -> tuple[list[dict[str, object]], dict[str, object], dict[str, object]]:
    root = Path(date_root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("market discovery manifest must be an object")
    if manifest.get("artifact_id") != CAUSAL_MARKET_DISCOVERY_POLICY_ID:
        raise ValueError("unsupported market discovery artifact")
    if manifest.get("schema_version") != 2:
        raise ValueError("unsupported market discovery schema")
    if manifest.get("discovery_policy") != causal_market_discovery_v0_2_manifest():
        raise ValueError("market discovery policy mismatch")
    if manifest.get("eligibility", {}).get(
        "causal_market_discovery_complete"
    ) is not True:
        raise ValueError("market discovery is incomplete")
    if manifest.get("knowledge_policy", {}).get("uses_benchmark_labels") is not False:
        raise ValueError("market discovery must be label-blind")
    relative = manifest.get("files", {}).get("market_candidates")
    if not isinstance(relative, str) or not relative:
        raise ValueError("market discovery lacks candidate artifact")
    candidate_path = Path(relative)
    if candidate_path.is_absolute() or ".." in candidate_path.parts:
        raise ValueError("market candidate path must stay inside discovery artifact")
    payload = json.loads((root / candidate_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("market candidate payload must be an object")
    if payload.get("schema_version") != 2:
        raise ValueError("unsupported market candidate schema")
    if payload.get("artifact_id") != CAUSAL_MARKET_CANDIDATES_ARTIFACT_ID:
        raise ValueError("unsupported market candidate artifact")
    claimed = payload.get("content_sha256")
    actual = _json_fingerprint(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )
    if claimed != actual:
        raise ValueError("market candidate payload fingerprint mismatch")
    if claimed != manifest.get("summary", {}).get(
        "causal_market_candidate_set_sha256"
    ):
        raise ValueError("market discovery candidate summary mismatch")
    if payload.get("source_discovery_policy_fingerprint") != manifest.get(
        "discovery_policy", {}
    ).get("fingerprint"):
        raise ValueError("market candidate source policy mismatch")
    if payload.get("source_discovery_records_sha256") != manifest.get(
        "summary", {}
    ).get("discovery_records_sha256"):
        raise ValueError("market candidate discovery fingerprint mismatch")
    if payload.get("trading_date") != manifest.get("trading_date"):
        raise ValueError("market candidate date mismatch")
    if payload.get("knowledge_policy", {}).get("uses_benchmark_labels") is not False:
        raise ValueError("market candidates must be label-blind")
    rows = payload.get("rows")
    if not isinstance(rows, list) or payload.get("candidate_count") != len(rows):
        raise ValueError("market candidate count mismatch")
    if payload.get("candidate_count") != manifest.get("summary", {}).get(
        "causal_market_candidate_count"
    ):
        raise ValueError("market candidate manifest count mismatch")
    profile = manifest.get("strategy_profile")
    if not isinstance(profile, dict):
        raise ValueError("market discovery lacks strategy profile")
    profile_fingerprint = profile.get("fingerprint")
    if profile_fingerprint != _json_fingerprint(
        {key: value for key, value in profile.items() if key != "fingerprint"}
    ):
        raise ValueError("market discovery strategy profile fingerprint mismatch")
    try:
        session_start = time.fromisoformat(str(profile["session_start"]))
        no_new_entries_after = time.fromisoformat(
            str(profile["no_new_entries_after"])
        )
    except (KeyError, ValueError) as error:
        raise ValueError("market discovery scan window is invalid") from error
    symbols: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("market candidate row must be an object")
        symbol = str(row.get("symbol") or "")
        if not symbol or symbol in symbols:
            raise ValueError("market candidate symbols must be unique and nonblank")
        symbols.add(symbol)
        timing = _qualification_timestamps(
            row.get("first_market_qualified_bar_started_at"),
            row.get("first_market_qualified_at"),
            context=f"market candidate {symbol}",
        )
        if timing is None:
            raise ValueError("market candidate must have qualification timing")
        _, decision = timing
        _validate_decision_scan_window(
            decision,
            trading_date=str(manifest.get("trading_date") or ""),
            session_start=session_start,
            no_new_entries_after=no_new_entries_after,
            context=f"market candidate {symbol}",
        )
    return rows, payload, manifest


def build_causal_market_discovery_manifest(
    *,
    trading_date: str,
    membership_rows: list[dict[str, object]],
    membership_payload: dict[str, object],
    membership_bundle_manifest: dict[str, object],
    result: DiscoveryResult,
    profile: StrategyProfile,
) -> dict[str, object]:
    policy = causal_market_discovery_v0_2_policy()
    if profile.rvol_lookback_sessions != policy.exact_rvol_prior_sessions:
        raise ValueError("strategy profile RVOL history differs from discovery policy")
    if membership_payload.get("trading_date") != trading_date:
        raise ValueError("membership date does not match discovery date")
    if len(membership_rows) != membership_payload.get("summary", {}).get(
        "identity_accepted_ticker_count"
    ):
        raise ValueError("membership count does not match its manifest")
    membership_hash = identity_resolved_membership_fingerprint(membership_rows)
    if membership_hash != membership_payload.get("summary", {}).get(
        "membership_sha256"
    ):
        raise ValueError("membership fingerprint does not match its manifest")
    assets = identity_membership_as_acquisition_assets(membership_rows)
    acquisition_hash = asset_master_fingerprint(assets)
    if result.asset_count != len(membership_rows):
        raise ValueError("market discovery did not consume every membership row")
    if result.listed_asset_count != len(membership_rows):
        raise ValueError("market discovery dropped a primary exchange")
    if result.asset_master_sha256 != acquisition_hash:
        raise ValueError("market discovery acquisition fingerprint mismatch")
    result_timings: dict[str, tuple[str, str]] = {}
    result_symbols: set[str] = set()
    for row in result.rows:
        if row.symbol in result_symbols:
            raise ValueError("market discovery records repeat a symbol")
        result_symbols.add(row.symbol)
        timing = _qualification_timestamps(
            row.first_market_qualified_bar_started_at,
            row.first_market_qualified_at,
            context=f"discovery record {row.symbol}",
        )
        if timing is None:
            continue
        _, decision = timing
        _validate_decision_scan_window(
            decision,
            trading_date=trading_date,
            session_start=profile.session_start,
            no_new_entries_after=profile.no_new_entries_after,
            context=f"discovery record {row.symbol}",
        )
        result_timings[row.symbol] = (
            str(row.first_market_qualified_bar_started_at),
            str(row.first_market_qualified_at),
        )
    if result.market_candidate_count != len(result_timings):
        raise ValueError("market discovery candidate count mismatch")
    audit_symbols = [row.symbol for row in result.acquisition_audit]
    membership_symbols = sorted(str(row["ticker"]) for row in membership_rows)
    if len(audit_symbols) != len(set(audit_symbols)):
        raise ValueError("market discovery audit repeats a symbol")
    if sorted(audit_symbols) != membership_symbols:
        raise ValueError("market discovery audit does not decide every member")
    audit_timings: dict[str, tuple[str, str]] = {}
    for row in result.acquisition_audit:
        timing = _qualification_timestamps(
            row.first_market_qualified_bar_started_at,
            row.first_market_qualified_at,
            context=f"acquisition audit {row.symbol}",
        )
        if row.causal_market_qualified != (timing is not None):
            raise ValueError(
                "market discovery audit qualification flag disagrees with timing"
            )
        if timing is None:
            continue
        _, decision = timing
        _validate_decision_scan_window(
            decision,
            trading_date=trading_date,
            session_start=profile.session_start,
            no_new_entries_after=profile.no_new_entries_after,
            context=f"acquisition audit {row.symbol}",
        )
        audit_timings[row.symbol] = (
            str(row.first_market_qualified_bar_started_at),
            str(row.first_market_qualified_at),
        )
    if audit_timings != result_timings:
        raise ValueError("market discovery audit candidates disagree with results")
    missing_daily_basis = [
        row.symbol
        for row in result.acquisition_audit
        if not row.daily_scan_basis_available
    ]
    split_minute_mismatches = [
        row.symbol
        for row in result.acquisition_audit
        if row.raw_target_minute_bars_present
        and not row.split_target_minute_bars_present
    ]
    missing_exact_observations = [
        row.symbol
        for row in result.acquisition_audit
        if row.exact_rvol_evaluated
        and not row.exact_rvol_observation_available
    ]
    if missing_daily_basis:
        raise ValueError(
            "identity-resolved members lost required daily scan basis: "
            f"{missing_daily_basis}"
        )
    if split_minute_mismatches:
        raise ValueError(
            "raw/split target minute coverage disagrees: "
            f"{split_minute_mismatches}"
        )
    if missing_exact_observations:
        raise ValueError(
            "exact RVOL acquisition returned no usable observation: "
            f"{missing_exact_observations}"
        )
    disposition_counts = Counter(
        row.disposition for row in result.acquisition_audit
    )
    candidate_payload = build_market_candidate_payload(
        trading_date=trading_date,
        membership_rows=membership_rows,
        result=result,
    )

    return {
        "schema_version": 2,
        "artifact_id": CAUSAL_MARKET_DISCOVERY_POLICY_ID,
        "trading_date": trading_date,
        "discovery_policy": causal_market_discovery_v0_2_manifest(),
        "strategy_profile": strategy_profile_manifest(profile),
        "source_membership": {
            "artifact_id": membership_payload["artifact_id"],
            "policy_fingerprint": membership_payload["policy_fingerprint"],
            "membership_sha256": membership_hash,
            "membership_payload_sha256": _json_fingerprint(membership_payload),
            "membership_bundle_sha256": membership_bundle_manifest[
                "content_sha256"
            ],
            "ticker_count": len(membership_rows),
        },
        "acquisition": {
            "translated_asset_sha256": acquisition_hash,
            "translated_asset_count": len(assets),
            "full_day_high_used_for_download_filter_only": True,
            "coarse_rvol_used_for_download_filter_only": True,
            "prefilter_values_exposed_to_runtime_strategy": False,
            "target_price_adjustment": "raw",
            "prior_close_and_rvol_adjustment": "split",
            "provider_symbol_mapping_asof": trading_date,
            "minute_bar_timestamp_semantics": "bar_start",
            "decision_availability_offset_seconds": 60,
            "scan_window_applies_to": "decision_availability_timestamp",
        },
        "summary": {
            "identity_resolved_ticker_count": len(membership_rows),
            "daily_price_superset_count": result.daily_superset_count,
            "coarse_rvol_prefilter_count": result.rvol_prefilter_count,
            "causal_market_candidate_count": result.market_candidate_count,
            "causal_market_candidate_set_sha256": candidate_payload[
                "content_sha256"
            ],
            "discovery_record_count": len(result.rows),
            "discovery_records_sha256": discovery_records_fingerprint(result),
            "acquisition_decision_count": len(result.acquisition_audit),
            "acquisition_disposition_counts": dict(
                sorted(disposition_counts.items())
            ),
            "acquisition_audit_sha256": discovery_audit_fingerprint(result),
            "required_daily_scan_basis_missing_count": 0,
            "raw_split_target_minute_mismatch_count": 0,
            "exact_rvol_observation_missing_count": 0,
        },
        "eligibility": {
            "complete_relative_to_identity_resolved_membership": True,
            "causal_market_discovery_complete": True,
            "point_in_time_float_complete": False,
            "publication_timed_news_complete": False,
            "full_feature_snapshot_complete": False,
            "universe_complete": False,
            "full_walk_forward_eligible": False,
            "policy_promotion_eligible": False,
        },
        "knowledge_policy": {
            "uses_benchmark_labels": False,
            "uses_retrospective_trade_outcomes": False,
            "future_session_extrema_used_by_strategy": False,
            "selection_applied": False,
        },
    }
