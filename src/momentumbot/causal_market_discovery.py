"""Contracts for label-blind market discovery from historical membership."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import time
import hashlib
import json
from typing import Iterable

from .historical_data import DiscoveryResult, asset_master_fingerprint
from .identity_resolved_universe import (
    IDENTITY_RESOLVED_UNIVERSE_POLICY_ID,
    identity_resolved_membership_fingerprint,
)
from .models import StrategyProfile


CAUSAL_MARKET_DISCOVERY_POLICY_ID = "causal-market-discovery-v0.1"
CAUSAL_MARKET_DISCOVERY_POLICY_STATUS = (
    "frozen_research_acquisition_contract_not_promotable"
)
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

    def payload(self) -> dict[str, object]:
        return asdict(self)

    @property
    def fingerprint(self) -> str:
        return _json_fingerprint(self.payload())


def causal_market_discovery_v0_1_policy(
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
            "only_completed_raw_target_bars_and_exact_same_time_split_rvol"
        ),
    )


def causal_market_discovery_v0_1_manifest() -> dict[str, object]:
    policy = causal_market_discovery_v0_1_policy()
    return {**policy.payload(), "fingerprint": policy.fingerprint}


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


def build_causal_market_discovery_manifest(
    *,
    trading_date: str,
    membership_rows: list[dict[str, object]],
    membership_payload: dict[str, object],
    membership_bundle_manifest: dict[str, object],
    result: DiscoveryResult,
    profile: StrategyProfile,
) -> dict[str, object]:
    policy = causal_market_discovery_v0_1_policy()
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
    if result.market_candidate_count != sum(
        row.first_market_qualified_at is not None for row in result.rows
    ):
        raise ValueError("market discovery candidate count mismatch")
    audit_symbols = [row.symbol for row in result.acquisition_audit]
    membership_symbols = sorted(str(row["ticker"]) for row in membership_rows)
    if len(audit_symbols) != len(set(audit_symbols)):
        raise ValueError("market discovery audit repeats a symbol")
    if sorted(audit_symbols) != membership_symbols:
        raise ValueError("market discovery audit does not decide every member")
    audit_candidates = {
        row.symbol for row in result.acquisition_audit if row.causal_market_qualified
    }
    result_candidates = {
        row.symbol for row in result.rows if row.first_market_qualified_at is not None
    }
    if audit_candidates != result_candidates:
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

    return {
        "schema_version": 1,
        "artifact_id": CAUSAL_MARKET_DISCOVERY_POLICY_ID,
        "trading_date": trading_date,
        "discovery_policy": causal_market_discovery_v0_1_manifest(),
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
        },
        "summary": {
            "identity_resolved_ticker_count": len(membership_rows),
            "daily_price_superset_count": result.daily_superset_count,
            "coarse_rvol_prefilter_count": result.rvol_prefilter_count,
            "causal_market_candidate_count": result.market_candidate_count,
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
