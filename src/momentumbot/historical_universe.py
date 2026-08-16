"""Frozen research contract for a provisional point-in-time stock universe.

This contract translates a fully fetched Massive ticker census into one
decision per ticker.  It consumes only provider metadata and market-data
availability.  It never consumes benchmark labels, modeled trades, or future
outcomes, and it deliberately keeps the resulting universe non-promotable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Mapping

from .instrument_metadata import (
    COMMON_TYPE_FAMILY,
    InstrumentMetadataStatus,
    audit_instrument_metadata,
    instrument_metadata_audit_manifest,
)
from .providers.massive import normalize_reference_tickers


HISTORICAL_UNIVERSE_POLICY_ID = "massive-common-equity-v0.1"
HISTORICAL_UNIVERSE_POLICY_STATUS = (
    "frozen_research_data_contract_not_promotable"
)
ALLOWED_PRIMARY_EXCHANGES = ("ARCX", "BATS", "XASE", "XNAS", "XNYS")


class UniverseDecisionReason(str, Enum):
    INCLUDED = "included_provisional_common_equity"
    OUTSIDE_COMMON_TYPE_FAMILY = "outside_common_type_family"
    INSTRUMENT_METADATA_CONFLICT = "instrument_metadata_conflict"
    INSTRUMENT_STRUCTURE_REVIEW = "instrument_structure_review"
    MISSING_INSTRUMENT_NAME_REVIEW = "missing_instrument_name_review"
    DISALLOWED_PRIMARY_EXCHANGE = "disallowed_primary_exchange"
    MULTIPLE_ELIGIBLE_IDENTITIES = "multiple_semantically_eligible_identities"
    COVERAGE_RECORD_MISSING = "coverage_record_missing"
    INVALID_MARKET_SYMBOL = "invalid_market_symbol"
    RAW_SPLIT_COVERAGE_MISMATCH = "raw_split_coverage_mismatch"
    NO_DAILY_BARS_IN_WINDOW = "no_daily_bars_in_window"
    MISSING_PRIOR_SESSION = "missing_prior_session"
    MISSING_TARGET_SESSION = "missing_target_session"


@dataclass(frozen=True, slots=True)
class FrozenHistoricalUniversePolicy:
    policy_id: str
    status: str
    common_type_family: tuple[str, ...]
    allowed_primary_exchanges: tuple[str, ...]
    required_metadata_status: str
    metadata_audit_fingerprint: str
    identity_rule: str
    market_data_rule: str

    def payload(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "status": self.status,
            "common_type_family": list(self.common_type_family),
            "allowed_primary_exchanges": list(self.allowed_primary_exchanges),
            "required_metadata_status": self.required_metadata_status,
            "metadata_audit_fingerprint": self.metadata_audit_fingerprint,
            "identity_rule": self.identity_rule,
            "market_data_rule": self.market_data_rule,
        }

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.payload(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class HistoricalUniverseDecision:
    ticker: str
    included: bool
    reason: UniverseDecisionReason
    security_record_count: int
    common_type_record_count: int
    accepted_identity_count: int
    metadata_statuses: tuple[str, ...]
    selected_security_type: str = ""
    selected_primary_exchange: str = ""
    selected_cik: str = ""
    selected_composite_figi: str = ""

    def payload(self) -> dict[str, object]:
        return {
            "ticker": self.ticker,
            "included": self.included,
            "reason": self.reason.value,
            "security_record_count": self.security_record_count,
            "common_type_record_count": self.common_type_record_count,
            "accepted_identity_count": self.accepted_identity_count,
            "metadata_statuses": list(self.metadata_statuses),
            "selected_security_type": self.selected_security_type,
            "selected_primary_exchange": self.selected_primary_exchange,
            "selected_cik": self.selected_cik,
            "selected_composite_figi": self.selected_composite_figi,
        }


def historical_universe_v0_1_policy() -> FrozenHistoricalUniversePolicy:
    metadata_manifest = instrument_metadata_audit_manifest()
    return FrozenHistoricalUniversePolicy(
        policy_id=HISTORICAL_UNIVERSE_POLICY_ID,
        status=HISTORICAL_UNIVERSE_POLICY_STATUS,
        common_type_family=COMMON_TYPE_FAMILY,
        allowed_primary_exchanges=ALLOWED_PRIMARY_EXCHANGES,
        required_metadata_status=(
            InstrumentMetadataStatus.NO_NAME_CONFLICT_DETECTED.value
        ),
        metadata_audit_fingerprint=str(metadata_manifest["fingerprint"]),
        identity_rule="exactly_one_semantically_accepted_identity_per_ticker",
        market_data_rule=(
            "raw_and_split_daily_series_require_prior_and_target_sessions"
        ),
    )


def historical_universe_v0_1_manifest() -> dict[str, object]:
    policy = historical_universe_v0_1_policy()
    return {**policy.payload(), "fingerprint": policy.fingerprint}


def _coverage_failure_reason(
    coverage: Mapping[str, object] | None,
) -> UniverseDecisionReason | None:
    if coverage is None:
        return UniverseDecisionReason.COVERAGE_RECORD_MISSING
    if bool(coverage.get("invalid_symbol")):
        return UniverseDecisionReason.INVALID_MARKET_SYMBOL
    raw_prior = bool(coverage.get("raw_prior_session_present"))
    raw_target = bool(coverage.get("raw_target_session_present"))
    split_prior = bool(coverage.get("split_prior_session_present"))
    split_target = bool(coverage.get("split_target_session_present"))
    if raw_prior != split_prior or raw_target != split_target:
        return UniverseDecisionReason.RAW_SPLIT_COVERAGE_MISMATCH
    prior = raw_prior and split_prior
    target = raw_target and split_target
    if prior and target and bool(coverage.get("coverage_pass")):
        return None
    if not prior and not target:
        return UniverseDecisionReason.NO_DAILY_BARS_IN_WINDOW
    if not prior:
        return UniverseDecisionReason.MISSING_PRIOR_SESSION
    if not target:
        return UniverseDecisionReason.MISSING_TARGET_SESSION
    return UniverseDecisionReason.RAW_SPLIT_COVERAGE_MISMATCH


def classify_ticker_group(
    rows: list[dict[str, object]] | tuple[dict[str, object], ...],
    coverage: Mapping[str, object] | None,
    *,
    policy: FrozenHistoricalUniversePolicy | None = None,
) -> HistoricalUniverseDecision:
    policy = policy or historical_universe_v0_1_policy()
    normalized = normalize_reference_tickers(rows)
    if not normalized:
        raise ValueError("ticker group cannot be empty")
    tickers = {str(row["ticker"]) for row in normalized}
    if len(tickers) != 1:
        raise ValueError("ticker group must contain exactly one ticker")
    ticker = next(iter(tickers))
    audited = [(row, audit_instrument_metadata(row)) for row in normalized]
    metadata_statuses = tuple(sorted({audit.status.value for _, audit in audited}))
    common_rows = [
        (row, audit)
        for row, audit in audited
        if audit.security_type in policy.common_type_family
    ]
    accepted = [
        row
        for row, audit in common_rows
        if audit.status.value == policy.required_metadata_status
        and str(row["primary_exchange"]) in policy.allowed_primary_exchanges
    ]

    base = {
        "ticker": ticker,
        "security_record_count": len(normalized),
        "common_type_record_count": len(common_rows),
        "accepted_identity_count": len(accepted),
        "metadata_statuses": metadata_statuses,
    }
    if not common_rows:
        return HistoricalUniverseDecision(
            included=False,
            reason=UniverseDecisionReason.OUTSIDE_COMMON_TYPE_FAMILY,
            **base,
        )
    if not any(
        audit.status is InstrumentMetadataStatus.NO_NAME_CONFLICT_DETECTED
        for _, audit in common_rows
    ):
        statuses = {audit.status for _, audit in common_rows}
        if InstrumentMetadataStatus.EXPLICIT_NON_COMMON_CONFLICT in statuses:
            reason = UniverseDecisionReason.INSTRUMENT_METADATA_CONFLICT
        elif InstrumentMetadataStatus.STRUCTURE_REVIEW in statuses:
            reason = UniverseDecisionReason.INSTRUMENT_STRUCTURE_REVIEW
        else:
            reason = UniverseDecisionReason.MISSING_INSTRUMENT_NAME_REVIEW
        return HistoricalUniverseDecision(included=False, reason=reason, **base)
    if not accepted:
        return HistoricalUniverseDecision(
            included=False,
            reason=UniverseDecisionReason.DISALLOWED_PRIMARY_EXCHANGE,
            **base,
        )
    if len(accepted) != 1:
        return HistoricalUniverseDecision(
            included=False,
            reason=UniverseDecisionReason.MULTIPLE_ELIGIBLE_IDENTITIES,
            **base,
        )

    selected = accepted[0]
    coverage_failure = _coverage_failure_reason(coverage)
    selected_fields = {
        "selected_security_type": str(selected["type"]),
        "selected_primary_exchange": str(selected["primary_exchange"]),
        "selected_cik": str(selected["cik"]),
        "selected_composite_figi": str(selected["composite_figi"]),
    }
    if coverage_failure is not None:
        return HistoricalUniverseDecision(
            included=False,
            reason=coverage_failure,
            **base,
            **selected_fields,
        )
    return HistoricalUniverseDecision(
        included=True,
        reason=UniverseDecisionReason.INCLUDED,
        **base,
        **selected_fields,
    )
