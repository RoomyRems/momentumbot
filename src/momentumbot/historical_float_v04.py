"""Causal SEC float normalization on the exact target-session share basis.

The legacy float contract inferred a target-basis share factor from one
``raw / split`` observation.  Provider split adjustment is not bounded by the
bars request's ``asof`` symbol-mapping date, so that factor can include splits
after the historical target session.  This version cancels those later events
by comparing the provider ratio at the disclosure session with the same ratio
at the exact target session::

    factor(measure -> target) = A(measure) / A(target)
    A(session) = raw_close(session) / split_close(session)

All persisted prices and rational factors use canonical decimal/integer text.
No binary floating-point value participates in a share decision.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd

from .causal_market_discovery_v03 import (
    CAUSAL_MARKET_CANDIDATES_V0_3_ARTIFACT_ID,
)
from .historical_float_v03 import (
    causal_float_v0_1_manifest,
    float_evidence_available_at,
    select_float_evidence,
    validate_selected_float_evidence,
)


ET = ZoneInfo("America/New_York")
FLOAT_LIMIT = 10_000_000
CAUSAL_FLOAT_V0_1_POLICY_ID = "causal-sec-float-v0.1"
CAUSAL_FLOAT_V0_2_POLICY_ID = "causal-sec-float-v0.2"
CAUSAL_FLOAT_POLICY_ID = CAUSAL_FLOAT_V0_2_POLICY_ID
CAUSAL_FLOAT_SCHEMA_VERSION = 3
FLOAT_TARGET_BASIS_ARTIFACT_ID = "causal-float-target-basis-v0.1"
FLOAT_TARGET_BASIS_SCHEMA_VERSION = 1
_SHA256_LENGTH = 64


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _no_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> object:
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=_reject_json_constant,
        object_pairs_hook=_no_duplicate_json_keys,
    )


def _json_fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _with_content_sha256(payload: dict[str, object]) -> dict[str, object]:
    if "content_sha256" in payload:
        raise ValueError("content hash must not be supplied by the caller")
    return {**payload, "content_sha256": _json_fingerprint(payload)}


def _validate_content_sha256(payload: dict[str, object], *, label: str) -> None:
    observed = payload.get("content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if observed != _json_fingerprint(unsigned):
        raise ValueError(f"{label} content fingerprint mismatch")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _SHA256_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _safe_child(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("artifact path must stay inside its root")
    resolved_root = root.resolve()
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("artifact path escaped its root")
    return resolved


def _canonical_decimal(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite() or parsed <= 0:
        return None
    rendered = format(parsed, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _positive_fraction(value: object) -> Fraction | None:
    rendered = _canonical_decimal(value)
    if rendered is None:
        return None
    return Fraction(Decimal(rendered))


def _ceil_positive(value: Fraction) -> int:
    if value <= 0:
        raise ValueError("share estimate must be positive")
    return (value.numerator + value.denominator - 1) // value.denominator


def causal_float_v0_2_manifest() -> dict[str, object]:
    parent = causal_float_v0_1_manifest()
    payload: dict[str, object] = {
        "policy_id": CAUSAL_FLOAT_POLICY_ID,
        "status": "frozen_research_feature_contract_not_promotable",
        "supersedes_policy_id": CAUSAL_FLOAT_V0_1_POLICY_ID,
        "supersedes_policy_fingerprint": parent["fingerprint"],
        "max_float_shares_exclusive": FLOAT_LIMIT,
        "source": (
            "sec_companyfacts_submissions_alpaca_raw_split_measure_daily_bars_"
            "and_market_qualification_minute_target_basis"
        ),
        "availability_rule": (
            "filing_acceptance_timestamp_else_conservative_next_session_fallback"
        ),
        "measure_session_rule": (
            "latest_raw_and_split_daily_bar_with_identical_timestamp_on_or_before_measure_date"
        ),
        "target_session_rule": (
            "raw_and_split_one_minute_bars_must_match_the_exact_completed_market_qualification_bar"
        ),
        "provider_adjustment_ratio_rule": "A_x_equals_raw_close_x_div_split_close_x",
        "share_basis_rule": "measure_to_target_factor_equals_A_measure_div_A_target",
        "public_float_rule": (
            "sec_public_float_usd_div_raw_measure_close_times_measure_to_target_factor"
        ),
        "post_target_split_rule": "provider_factors_after_target_cancel_exactly",
        "later_target_session_price_rule": "forbidden_target_pair_is_qualification_time_only",
        "numeric_rule": "canonical_decimal_strings_and_exact_reduced_rationals",
        "rounding_rule": "positive_fractional_share_estimates_ceiling_before_threshold",
        "rollforward_rule": (
            "net_issuance_increases_estimate_buybacks_do_not_reduce_anchor_float"
        ),
        "deterministic_upper_bound_rule": (
            "target_basis_total_outstanding_below_limit_proves_float_pass"
        ),
        "unknown_rule": "missing_malformed_or_misaligned_basis_fails_scanner_float_closed",
        "provider_route_change": False,
    }
    return {**payload, "fingerprint": _json_fingerprint(payload)}


@dataclass(frozen=True, slots=True)
class TargetBasisObservation:
    requested_date: str
    observed_date: str | None
    measure_raw_timestamp: str | None
    measure_split_timestamp: str | None
    measure_raw_close: str | None
    measure_split_close: str | None
    target_date: str
    target_raw_timestamp: str | None
    target_split_timestamp: str | None
    target_raw_close: str | None
    target_split_close: str | None
    target_source_artifact_id: str | None
    target_source_content_sha256: str | None
    share_factor_numerator: str | None
    share_factor_denominator: str | None
    status: str
    lineage_sha256: str


@dataclass(frozen=True, slots=True)
class TargetSessionPair:
    symbol: str
    target_date: str
    first_market_qualified_bar_started_at: str
    first_market_qualified_at: str
    raw_timestamp: str
    split_timestamp: str
    raw_close: str
    split_close: str
    source_artifact_id: str
    source_content_sha256: str


@dataclass(frozen=True, slots=True)
class FloatJoinRow:
    symbol: str
    cik: str
    first_market_qualified_at: str
    first_market_qualified_bar_started_at: str | None
    method: str
    estimated_float_shares: int | None
    current_outstanding_target_basis: int | None
    float_pillar_pass: bool | None
    public_float_usd: str | None
    public_float_measure_date: str | None
    public_float_accession: str | None
    public_float_price_used: str | None
    public_float_price_date: str | None
    anchor_outstanding_target_basis: int | None
    current_outstanding_accession: str | None
    current_outstanding_measure_date: str | None
    notes: tuple[str, ...]


_SELECTED_EVIDENCE_KEYS = {
    "symbol",
    "cik",
    "first_market_qualified_bar_started_at",
    "first_market_qualified_at",
    "public_float",
    "anchor_outstanding",
    "current_outstanding",
}
_PUBLIC_EVIDENCE_KEYS = {
    "public_float_usd",
    "measure_date",
    "available_at",
    "accession",
    "form",
}
_OUTSTANDING_EVIDENCE_KEYS = {
    "shares",
    "measure_date",
    "available_at",
    "accession",
    "form",
}
_SEC_STATUSES = {
    "missing_or_invalid_identity_cik",
    "provider_error",
    "sec_companyfacts_not_found",
    "success_no_eligible_sec_evidence",
    "success_selected_evidence_conservative_filing_date_fallback",
    "success_selected_evidence_exact_acceptance",
    "success_selected_evidence_includes_conservative_fallback",
}
_FLOAT_RECORD_KEYS = {field.name for field in fields(FloatJoinRow)} | {
    "float_asof",
    "float_classification",
    "target_basis_date",
    "selected_evidence",
    "selected_evidence_sha256",
    "candidate_identity",
    "candidate_identity_sha256",
    "basis_observations",
    "basis_lineage_sha256",
    "target_basis_source_artifact_id",
    "target_basis_source_sha256",
    "sec_status",
    "sec_provider_error",
}


def _candidate_identity(candidate: dict[str, object]) -> dict[str, str]:
    identity = {
        "symbol": str(candidate.get("symbol") or ""),
        "selected_cik": str(candidate.get("selected_cik") or ""),
        "selected_composite_figi": str(
            candidate.get("selected_composite_figi") or ""
        ),
        "identity_identifier_kind": str(
            candidate.get("identity_identifier_kind") or ""
        ),
        "identity_identifier": str(candidate.get("identity_identifier") or ""),
    }
    if not identity["symbol"]:
        raise ValueError("float candidate identity lacks a symbol")
    if not identity["identity_identifier_kind"] or not identity["identity_identifier"]:
        raise ValueError("float candidate lacks a stable identity")
    if identity["identity_identifier_kind"] not in {"composite_figi", "cik"}:
        raise ValueError("float candidate identity kind is unsupported")
    if identity["identity_identifier_kind"] == "composite_figi":
        if identity["identity_identifier"] != identity["selected_composite_figi"]:
            raise ValueError("float candidate Composite FIGI identity mismatch")
    elif identity["identity_identifier"].lstrip("0") != identity["selected_cik"].lstrip(
        "0"
    ):
        raise ValueError("float candidate CIK identity mismatch")
    return identity


def validate_selected_float_evidence_v02(candidate: dict[str, object]) -> None:
    """Tighten the inherited causal timing contract with numeric/schema checks."""

    validate_selected_float_evidence(candidate)
    if set(candidate) != _SELECTED_EVIDENCE_KEYS:
        raise ValueError("selected float evidence fields are invalid")
    _, qualified_at = _market_qualification_timestamps(
        candidate, context="selected float evidence v0.2"
    )
    public = candidate.get("public_float")
    if public is not None:
        if not isinstance(public, dict) or set(public) != _PUBLIC_EVIDENCE_KEYS:
            raise ValueError("public float evidence fields are invalid")
        if _positive_fraction(public.get("public_float_usd")) is None:
            raise ValueError("public float USD must be finite and positive")
        if not str(public.get("form") or ""):
            raise ValueError("public float evidence requires a form")
        if date.fromisoformat(str(public["measure_date"])) > qualified_at.date():
            raise ValueError("public float measure date follows qualification")
    for key in ("anchor_outstanding", "current_outstanding"):
        disclosure = candidate.get(key)
        if disclosure is None:
            continue
        if not isinstance(disclosure, dict) or set(disclosure) != _OUTSTANDING_EVIDENCE_KEYS:
            raise ValueError(f"{key} evidence fields are invalid")
        shares = disclosure.get("shares")
        if isinstance(shares, bool) or not isinstance(shares, int) or shares <= 0:
            raise ValueError(f"{key} shares must be a positive integer")
        if not str(disclosure.get("form") or ""):
            raise ValueError(f"{key} evidence requires a form")
        if date.fromisoformat(str(disclosure["measure_date"])) > qualified_at.date():
            raise ValueError(f"{key} measure date follows qualification")


def _target_provider_manifest(trading_date: date) -> dict[str, object]:
    return {
        "provider": "alpaca_historical_stock_bars",
        "feed": "sip",
        "timeframe": "1Min",
        "adjustments": ["raw", "split"],
        "asof": trading_date.isoformat(),
        "timestamp_rule": "exact_first_market_qualified_bar_started_at",
        "availability_rule": "completed_bar_available_at_bar_start_plus_one_minute",
    }


def _exact_frame_close(frame: pd.DataFrame, timestamp: datetime) -> str:
    if (
        frame.empty
        or not isinstance(frame.index, pd.DatetimeIndex)
        or frame.index.tz is None
        or frame.index.has_duplicates
        or "close" not in frame
    ):
        raise ValueError("target basis frame is malformed")
    target = pd.Timestamp(timestamp)
    if target not in frame.index:
        raise ValueError("target basis frame lacks the qualification bar")
    close = frame.loc[target, "close"]
    if isinstance(close, pd.Series):
        raise ValueError("target basis frame repeats the qualification bar")
    rendered = _canonical_decimal(close)
    if rendered is None:
        raise ValueError("target basis qualification close is invalid")
    return rendered


def build_float_target_basis_payload(
    *,
    trading_date: date,
    candidate_rows: list[dict[str, object]],
    candidate_payload: dict[str, object],
    raw_minutes_by_symbol: dict[str, pd.DataFrame],
    split_minutes_by_symbol: dict[str, pd.DataFrame],
) -> dict[str, object]:
    """Freeze the causal qualification-minute A(T) input for every candidate."""

    _validate_candidate_payload(
        candidate_payload,
        candidate_rows=candidate_rows,
        trading_date=trading_date,
    )
    symbols = [str(row.get("symbol") or "") for row in candidate_rows]
    if "" in symbols or len(symbols) != len(set(symbols)):
        raise ValueError("target basis candidates are invalid")
    expected_symbols = set(symbols)
    if set(raw_minutes_by_symbol) != expected_symbols:
        raise ValueError("target raw minute candidate set mismatch")
    if set(split_minutes_by_symbol) != expected_symbols:
        raise ValueError("target split minute candidate set mismatch")
    candidates = {str(row["symbol"]): row for row in candidate_rows}
    rows: list[dict[str, object]] = []
    for symbol in sorted(expected_symbols):
        candidate = candidates[symbol]
        bar_started_at, qualified_at = _market_qualification_timestamps(
            candidate,
            context=f"target basis candidate {symbol}",
        )
        if qualified_at.astimezone(ET).date() != trading_date:
            raise ValueError("target basis candidate escaped the trading date")
        raw_close = _exact_frame_close(raw_minutes_by_symbol[symbol], bar_started_at)
        split_close = _exact_frame_close(split_minutes_by_symbol[symbol], bar_started_at)
        timestamp_text = bar_started_at.isoformat()
        rows.append(
            {
                "symbol": symbol,
                "first_market_qualified_bar_started_at": timestamp_text,
                "first_market_qualified_at": qualified_at.isoformat(),
                "raw_timestamp": timestamp_text,
                "split_timestamp": timestamp_text,
                "raw_close": raw_close,
                "split_close": split_close,
            }
        )
    payload: dict[str, object] = {
        "schema_version": FLOAT_TARGET_BASIS_SCHEMA_VERSION,
        "artifact_id": FLOAT_TARGET_BASIS_ARTIFACT_ID,
        "trading_date": trading_date.isoformat(),
        "source_market_candidates_artifact_id": candidate_payload["artifact_id"],
        "source_market_candidates_sha256": candidate_payload["content_sha256"],
        "provider": _target_provider_manifest(trading_date),
        "candidate_count": len(rows),
        "rows": rows,
    }
    result = _with_content_sha256(payload)
    validate_float_target_basis_payload(
        result,
        candidate_rows=candidate_rows,
        candidate_payload=candidate_payload,
        expected_trading_date=trading_date,
    )
    return result


def validate_float_target_basis_payload(
    payload: dict[str, object],
    *,
    candidate_rows: list[dict[str, object]],
    candidate_payload: dict[str, object],
    expected_trading_date: date | str,
) -> None:
    expected_keys = {
        "schema_version",
        "artifact_id",
        "trading_date",
        "source_market_candidates_artifact_id",
        "source_market_candidates_sha256",
        "provider",
        "candidate_count",
        "rows",
        "content_sha256",
    }
    if set(payload) != expected_keys:
        raise ValueError("target basis payload fields are invalid")
    if payload.get("schema_version") != FLOAT_TARGET_BASIS_SCHEMA_VERSION:
        raise ValueError("unsupported target basis schema")
    if payload.get("artifact_id") != FLOAT_TARGET_BASIS_ARTIFACT_ID:
        raise ValueError("unsupported target basis artifact")
    _validate_content_sha256(payload, label="target basis payload")
    trading_date = (
        date.fromisoformat(expected_trading_date)
        if isinstance(expected_trading_date, str)
        else expected_trading_date
    )
    if payload.get("trading_date") != trading_date.isoformat():
        raise ValueError("target basis trading date mismatch")
    _validate_candidate_payload(
        candidate_payload,
        candidate_rows=candidate_rows,
        trading_date=trading_date,
    )
    if payload.get("source_market_candidates_artifact_id") != candidate_payload.get(
        "artifact_id"
    ):
        raise ValueError("target basis candidate artifact mismatch")
    if payload.get("source_market_candidates_sha256") != candidate_payload.get(
        "content_sha256"
    ):
        raise ValueError("target basis candidate fingerprint mismatch")
    if payload.get("provider") != _target_provider_manifest(trading_date):
        raise ValueError("target basis provider contract mismatch")
    rows = payload.get("rows")
    if not isinstance(rows, list) or payload.get("candidate_count") != len(rows):
        raise ValueError("target basis candidate count mismatch")
    candidates = {str(row.get("symbol") or ""): row for row in candidate_rows}
    if [row.get("symbol") for row in rows if isinstance(row, dict)] != sorted(candidates):
        raise ValueError("target basis candidate set or order mismatch")
    row_keys = {
        "symbol",
        "first_market_qualified_bar_started_at",
        "first_market_qualified_at",
        "raw_timestamp",
        "split_timestamp",
        "raw_close",
        "split_close",
    }
    for row in rows:
        if not isinstance(row, dict) or set(row) != row_keys:
            raise ValueError("target basis row fields are invalid")
        symbol = str(row["symbol"])
        candidate = candidates[symbol]
        bar_started_at, qualified_at = _market_qualification_timestamps(
            candidate,
            context=f"target basis candidate {symbol}",
        )
        if row["first_market_qualified_bar_started_at"] != candidate.get(
            "first_market_qualified_bar_started_at"
        ):
            raise ValueError("target basis candidate bar-start mismatch")
        if row["first_market_qualified_at"] != candidate.get(
            "first_market_qualified_at"
        ):
            raise ValueError("target basis candidate qualification mismatch")
        if row["raw_timestamp"] != row["split_timestamp"]:
            raise ValueError("target basis raw/split timestamp mismatch")
        if row["raw_timestamp"] != bar_started_at.isoformat():
            raise ValueError("target basis did not use the qualification bar")
        if qualified_at - bar_started_at != timedelta(minutes=1):
            raise ValueError("target basis qualification timing mismatch")
        if bar_started_at.astimezone(ET).date() != trading_date:
            raise ValueError("target basis timestamp escaped the trading date")
        for key in ("raw_close", "split_close"):
            if _canonical_decimal(row[key]) != row[key]:
                raise ValueError("target basis close is not canonical and positive")


def load_float_target_basis(
    path: str | Path,
    *,
    candidate_rows: list[dict[str, object]],
    candidate_payload: dict[str, object],
    expected_trading_date: date | str,
) -> tuple[dict[str, TargetSessionPair], dict[str, object]]:
    payload = _load_json(Path(path))
    if not isinstance(payload, dict):
        raise ValueError("target basis payload must be an object")
    validate_float_target_basis_payload(
        payload,
        candidate_rows=candidate_rows,
        candidate_payload=candidate_payload,
        expected_trading_date=expected_trading_date,
    )
    pairs = {
        str(row["symbol"]): TargetSessionPair(
            symbol=str(row["symbol"]),
            target_date=str(payload["trading_date"]),
            first_market_qualified_bar_started_at=str(
                row["first_market_qualified_bar_started_at"]
            ),
            first_market_qualified_at=str(row["first_market_qualified_at"]),
            raw_timestamp=str(row["raw_timestamp"]),
            split_timestamp=str(row["split_timestamp"]),
            raw_close=str(row["raw_close"]),
            split_close=str(row["split_close"]),
            source_artifact_id=FLOAT_TARGET_BASIS_ARTIFACT_ID,
            source_content_sha256=str(payload["content_sha256"]),
        )
        for row in payload["rows"]
    }
    return pairs, payload


def validate_target_session_pair(pair: TargetSessionPair) -> None:
    if not pair.symbol:
        raise ValueError("target session pair lacks a symbol")
    target_date = date.fromisoformat(pair.target_date)
    bar_started_at = datetime.fromisoformat(
        pair.first_market_qualified_bar_started_at
    )
    qualified_at = datetime.fromisoformat(pair.first_market_qualified_at)
    raw_timestamp = datetime.fromisoformat(pair.raw_timestamp)
    split_timestamp = datetime.fromisoformat(pair.split_timestamp)
    if any(
        value.tzinfo is None
        for value in (bar_started_at, qualified_at, raw_timestamp, split_timestamp)
    ):
        raise ValueError("target session pair timestamps must be timezone-aware")
    if qualified_at - bar_started_at != timedelta(minutes=1):
        raise ValueError("target session pair qualification timing mismatch")
    if raw_timestamp != split_timestamp or raw_timestamp != bar_started_at:
        raise ValueError("target session pair timestamp mismatch")
    if bar_started_at.astimezone(ET).date() != target_date:
        raise ValueError("target session pair escaped its target date")
    if _canonical_decimal(pair.raw_close) != pair.raw_close:
        raise ValueError("target session raw close is invalid")
    if _canonical_decimal(pair.split_close) != pair.split_close:
        raise ValueError("target session split close is invalid")
    if pair.source_artifact_id != FLOAT_TARGET_BASIS_ARTIFACT_ID:
        raise ValueError("target session source artifact mismatch")
    if not _is_sha256(pair.source_content_sha256):
        raise ValueError("target session source fingerprint is invalid")


def _basis_unsigned_payload(observation: TargetBasisObservation) -> dict[str, object]:
    return {
        key: value
        for key, value in asdict(observation).items()
        if key != "lineage_sha256"
    }


def _timestamp_text(value: object) -> str | None:
    if not isinstance(value, pd.Timestamp):
        try:
            value = pd.Timestamp(value)
        except (TypeError, ValueError):
            return None
    if value.tzinfo is None:
        return None
    return value.isoformat()


def _selected_session(
    frame: pd.DataFrame,
    requested: date,
    *,
    exact: bool,
) -> tuple[str | None, str | None]:
    """Return one timestamp and canonical close, preserving malformed absence."""

    if frame.empty or not isinstance(frame.index, pd.DatetimeIndex):
        return None, None
    if frame.index.tz is None or frame.index.has_duplicates or "close" not in frame:
        return None, None
    eligible: list[pd.Timestamp] = []
    for raw_timestamp in frame.index:
        timestamp = pd.Timestamp(raw_timestamp)
        local_date = timestamp.tz_convert(ET).date()
        if (local_date == requested) if exact else (local_date <= requested):
            eligible.append(timestamp)
    if not eligible:
        return None, None
    selected = max(eligible)
    value = frame.loc[selected, "close"]
    if isinstance(value, pd.Series):
        return None, None
    return _timestamp_text(selected), _canonical_decimal(value)


def _observation_status(payload: dict[str, object]) -> str:
    measure_raw_timestamp = payload.get("measure_raw_timestamp")
    measure_split_timestamp = payload.get("measure_split_timestamp")
    if measure_raw_timestamp is None or measure_split_timestamp is None:
        return "missing_measure_pair"
    if measure_raw_timestamp != measure_split_timestamp:
        return "measure_timestamp_mismatch"
    if payload.get("measure_raw_close") is None or payload.get("measure_split_close") is None:
        return "invalid_measure_close"
    target_raw_timestamp = payload.get("target_raw_timestamp")
    target_split_timestamp = payload.get("target_split_timestamp")
    if target_raw_timestamp is None or target_split_timestamp is None:
        return "missing_target_pair"
    if target_raw_timestamp != target_split_timestamp:
        return "target_timestamp_mismatch"
    if payload.get("target_raw_close") is None or payload.get("target_split_close") is None:
        return "invalid_target_close"
    if (
        payload.get("target_source_artifact_id") != FLOAT_TARGET_BASIS_ARTIFACT_ID
        or not _is_sha256(payload.get("target_source_content_sha256"))
    ):
        return "invalid_target_source"
    return "complete"


def _build_observation(payload: dict[str, object]) -> TargetBasisObservation:
    status = _observation_status(payload)
    factor_numerator: str | None = None
    factor_denominator: str | None = None
    if status == "complete":
        measure_raw = _positive_fraction(payload["measure_raw_close"])
        measure_split = _positive_fraction(payload["measure_split_close"])
        target_raw = _positive_fraction(payload["target_raw_close"])
        target_split = _positive_fraction(payload["target_split_close"])
        if None in {measure_raw, measure_split, target_raw, target_split}:
            raise AssertionError("complete observation lacks a positive close")
        factor = (measure_raw / measure_split) / (target_raw / target_split)
        factor_numerator = str(factor.numerator)
        factor_denominator = str(factor.denominator)
    unsigned = {
        **payload,
        "share_factor_numerator": factor_numerator,
        "share_factor_denominator": factor_denominator,
        "status": status,
    }
    return TargetBasisObservation(
        **unsigned,
        lineage_sha256=_json_fingerprint(unsigned),
    )


def observe_target_basis(
    raw: pd.DataFrame,
    split: pd.DataFrame,
    requested: date,
    *,
    target_pair: TargetSessionPair,
) -> TargetBasisObservation:
    """Pair measure daily bars with the causal qualification-minute A(T)."""

    validate_target_session_pair(target_pair)
    target = date.fromisoformat(target_pair.target_date)
    if requested > target:
        raise ValueError("basis date cannot follow the causal target date")
    measure_raw_timestamp, measure_raw_close = _selected_session(
        raw, requested, exact=False
    )
    measure_split_timestamp, measure_split_close = _selected_session(
        split, requested, exact=False
    )
    observed_date: str | None = None
    if (
        measure_raw_timestamp is not None
        and measure_raw_timestamp == measure_split_timestamp
    ):
        observed_date = (
            datetime.fromisoformat(measure_raw_timestamp).astimezone(ET).date().isoformat()
        )
    return _build_observation(
        {
            "requested_date": requested.isoformat(),
            "observed_date": observed_date,
            "measure_raw_timestamp": measure_raw_timestamp,
            "measure_split_timestamp": measure_split_timestamp,
            "measure_raw_close": measure_raw_close,
            "measure_split_close": measure_split_close,
            "target_date": target.isoformat(),
            "target_raw_timestamp": target_pair.raw_timestamp,
            "target_split_timestamp": target_pair.split_timestamp,
            "target_raw_close": target_pair.raw_close,
            "target_split_close": target_pair.split_close,
            "target_source_artifact_id": target_pair.source_artifact_id,
            "target_source_content_sha256": target_pair.source_content_sha256,
        }
    )


def validate_target_basis_observation(observation: TargetBasisObservation) -> None:
    requested = date.fromisoformat(observation.requested_date)
    target = date.fromisoformat(observation.target_date)
    if requested > target:
        raise ValueError("basis observation follows its target date")
    payload = _basis_unsigned_payload(observation)
    if observation.lineage_sha256 != _json_fingerprint(payload):
        raise ValueError("basis observation lineage fingerprint mismatch")
    for key in (
        "measure_raw_close",
        "measure_split_close",
        "target_raw_close",
        "target_split_close",
    ):
        value = payload[key]
        if value is not None and _canonical_decimal(value) != value:
            raise ValueError("basis observation close is not canonical and positive")
    for key in (
        "measure_raw_timestamp",
        "measure_split_timestamp",
        "target_raw_timestamp",
        "target_split_timestamp",
    ):
        value = payload[key]
        if value is None:
            continue
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None or parsed.isoformat() != value:
            raise ValueError("basis observation timestamp is invalid")
    if observation.observed_date is not None:
        observed = date.fromisoformat(observation.observed_date)
        if observed > requested:
            raise ValueError("basis observation used a forward measure session")
        if observation.measure_raw_timestamp is None:
            raise ValueError("basis observation date lacks a measure timestamp")
        timestamp_date = (
            datetime.fromisoformat(observation.measure_raw_timestamp)
            .astimezone(ET)
            .date()
        )
        if timestamp_date != observed:
            raise ValueError("basis observation measure date mismatch")
    for key in ("target_raw_timestamp", "target_split_timestamp"):
        value = payload[key]
        if value is not None:
            timestamp_date = datetime.fromisoformat(str(value)).astimezone(ET).date()
            if timestamp_date != target:
                raise ValueError("basis observation did not use the exact target session")
    expected_status = _observation_status(payload)
    if observation.status != expected_status:
        raise ValueError("basis observation status mismatch")
    numerator = observation.share_factor_numerator
    denominator = observation.share_factor_denominator
    if observation.status != "complete":
        if numerator is not None or denominator is not None:
            raise ValueError("incomplete basis observation carries a share factor")
        return
    if observation.observed_date is None:
        raise ValueError("complete basis observation lacks its observed date")
    try:
        supplied = Fraction(int(str(numerator)), int(str(denominator)))
    except (TypeError, ValueError, ZeroDivisionError) as error:
        raise ValueError("basis observation factor is invalid") from error
    if supplied <= 0:
        raise ValueError("basis observation factor must be positive")
    if str(supplied.numerator) != numerator or str(supplied.denominator) != denominator:
        raise ValueError("basis observation factor is not a reduced rational")
    measure_raw = _positive_fraction(observation.measure_raw_close)
    measure_split = _positive_fraction(observation.measure_split_close)
    target_raw = _positive_fraction(observation.target_raw_close)
    target_split = _positive_fraction(observation.target_split_close)
    if None in {measure_raw, measure_split, target_raw, target_split}:
        raise ValueError("complete basis observation has an invalid close")
    expected = (measure_raw / measure_split) / (target_raw / target_split)
    if supplied != expected:
        raise ValueError("basis observation share factor mismatch")


def _share_factor(observation: TargetBasisObservation | None) -> Fraction | None:
    if observation is None:
        return None
    validate_target_basis_observation(observation)
    if observation.status != "complete":
        return None
    return Fraction(
        int(observation.share_factor_numerator or "0"),
        int(observation.share_factor_denominator or "1"),
    )


def normalize_reported_shares(
    shares: int,
    observation: TargetBasisObservation | None,
) -> int | None:
    if isinstance(shares, bool) or not isinstance(shares, int) or shares <= 0:
        raise ValueError("reported shares must be a positive integer")
    factor = _share_factor(observation)
    if factor is None:
        return None
    return _ceil_positive(Fraction(shares) * factor)


def infer_public_float_shares(
    public_float_usd: object,
    observation: TargetBasisObservation | None,
) -> int | None:
    factor = _share_factor(observation)
    if factor is None or observation is None:
        return None
    value = _positive_fraction(public_float_usd)
    raw_close = _positive_fraction(observation.measure_raw_close)
    if value is None or raw_close is None:
        return None
    return _ceil_positive((value / raw_close) * factor)


def _row(
    candidate: dict[str, object],
    *,
    method: str,
    estimated_float_shares: int | None,
    current_norm: int | None,
    float_pillar_pass: bool | None,
    public: dict[str, object] | None,
    public_basis: TargetBasisObservation | None,
    anchor_norm: int | None,
    notes: list[str],
) -> FloatJoinRow:
    current = candidate.get("current_outstanding")
    if current is not None and not isinstance(current, dict):
        raise ValueError("current outstanding evidence must be an object")
    return FloatJoinRow(
        symbol=str(candidate["symbol"]),
        cik=str(candidate["cik"]),
        first_market_qualified_at=str(candidate["first_market_qualified_at"]),
        first_market_qualified_bar_started_at=(
            str(candidate["first_market_qualified_bar_started_at"])
            if candidate.get("first_market_qualified_bar_started_at") is not None
            else None
        ),
        method=method,
        estimated_float_shares=estimated_float_shares,
        current_outstanding_target_basis=current_norm,
        float_pillar_pass=float_pillar_pass,
        public_float_usd=(
            _canonical_decimal(public["public_float_usd"]) if public else None
        ),
        public_float_measure_date=str(public["measure_date"]) if public else None,
        public_float_accession=str(public["accession"]) if public else None,
        public_float_price_used=(
            public_basis.measure_raw_close if public_basis is not None else None
        ),
        public_float_price_date=(
            public_basis.observed_date if public_basis is not None else None
        ),
        anchor_outstanding_target_basis=anchor_norm,
        current_outstanding_accession=(str(current["accession"]) if current else None),
        current_outstanding_measure_date=(
            str(current["measure_date"]) if current else None
        ),
        notes=tuple(notes),
    )


def estimate_float_row(
    candidate: dict[str, object],
    observations: dict[str, TargetBasisObservation],
) -> FloatJoinRow:
    validate_selected_float_evidence_v02(candidate)
    notes: list[str] = []
    public = candidate.get("public_float")
    anchor = candidate.get("anchor_outstanding")
    current = candidate.get("current_outstanding")
    if public is not None and not isinstance(public, dict):
        raise ValueError("public float evidence must be an object")
    if anchor is not None and not isinstance(anchor, dict):
        raise ValueError("anchor outstanding evidence must be an object")
    if current is not None and not isinstance(current, dict):
        raise ValueError("current outstanding evidence must be an object")

    current_norm = None
    if current:
        current_basis = observations.get(f"current:{current['measure_date']}")
        current_norm = normalize_reported_shares(current["shares"], current_basis)
        if current_norm is None:
            notes.append(
                "current outstanding share basis could not be normalized to the exact target session"
            )

    if not public:
        if current_norm is not None and current_norm < FLOAT_LIMIT:
            return _row(
                candidate,
                method="sec_outstanding_shares_target_basis_upper_bound",
                estimated_float_shares=current_norm,
                current_norm=current_norm,
                float_pillar_pass=True,
                public=None,
                public_basis=None,
                anchor_norm=None,
                notes=notes + ["float is at most total common shares outstanding"],
            )
        notes.append("no eligible SEC EntityPublicFloat disclosure before qualification")
        return _row(
            candidate,
            method="unknown_missing_public_float",
            estimated_float_shares=None,
            current_norm=current_norm,
            float_pillar_pass=None,
            public=None,
            public_basis=None,
            anchor_norm=None,
            notes=notes,
        )

    public_basis = observations.get(f"public:{public['measure_date']}")
    anchor_float = infer_public_float_shares(public["public_float_usd"], public_basis)
    if anchor_float is None:
        notes.append("complete measure/target price basis unavailable for public float")
        if current_norm is not None and current_norm < FLOAT_LIMIT:
            notes.append(
                "float still passes because target-basis total outstanding is below the limit"
            )
            return _row(
                candidate,
                method="sec_outstanding_shares_target_basis_upper_bound",
                estimated_float_shares=current_norm,
                current_norm=current_norm,
                float_pillar_pass=True,
                public=public,
                public_basis=None,
                anchor_norm=None,
                notes=notes,
            )
        return _row(
            candidate,
            method="unknown_missing_public_float_price_basis",
            estimated_float_shares=None,
            current_norm=current_norm,
            float_pillar_pass=None,
            public=public,
            public_basis=None,
            anchor_norm=None,
            notes=notes,
        )

    estimated = anchor_float
    anchor_norm = None
    method = "sec_public_float_usd_raw_price_exact_target_basis"
    if anchor and current:
        anchor_basis = observations.get(f"anchor:{anchor['measure_date']}")
        anchor_norm = normalize_reported_shares(anchor["shares"], anchor_basis)
        if anchor_norm is not None and current_norm is not None:
            if anchor_float > anchor_norm:
                notes.append(
                    "implied public float exceeds anchor outstanding shares; historical-price inversion is noisy"
                )
            else:
                affiliate = anchor_norm - anchor_float
                estimated = max(anchor_float, current_norm - affiliate)
                method = "sec_public_float_exact_target_basis_outstanding_rollforward"
        else:
            notes.append(
                "outstanding-share roll-forward skipped because an exact target basis was unavailable"
            )

    if current_norm is not None and current_norm < FLOAT_LIMIT:
        if estimated > current_norm:
            notes.append(
                "public-float estimate exceeds current outstanding; current total outstanding is the deterministic upper bound"
            )
        else:
            notes.append(
                "target-basis total common shares outstanding independently prove float below the limit"
            )
        return _row(
            candidate,
            method="sec_outstanding_shares_target_basis_upper_bound",
            estimated_float_shares=current_norm,
            current_norm=current_norm,
            float_pillar_pass=True,
            public=public,
            public_basis=public_basis,
            anchor_norm=anchor_norm,
            notes=notes,
        )

    return _row(
        candidate,
        method=method,
        estimated_float_shares=estimated,
        current_norm=current_norm,
        float_pillar_pass=estimated < FLOAT_LIMIT,
        public=public,
        public_basis=public_basis,
        anchor_norm=anchor_norm,
        notes=notes,
    )


def _market_qualification_timestamps(
    candidate: dict[str, object], *, context: str
) -> tuple[datetime, datetime]:
    try:
        bar_started_at = datetime.fromisoformat(
            str(candidate.get("first_market_qualified_bar_started_at") or "")
        )
        qualified_at = datetime.fromisoformat(
            str(candidate.get("first_market_qualified_at") or "")
        )
    except ValueError as error:
        raise ValueError(f"{context} qualification timestamps are invalid") from error
    if bar_started_at.tzinfo is None or qualified_at.tzinfo is None:
        raise ValueError(f"{context} qualification timestamps must be timezone-aware")
    if qualified_at - bar_started_at != timedelta(minutes=1):
        raise ValueError(f"{context} decision timestamp must equal bar start plus one minute")
    return bar_started_at, qualified_at


def _candidate_target_date(candidate: dict[str, object]) -> date:
    _, qualified_at = _market_qualification_timestamps(
        candidate, context="float candidate"
    )
    return qualified_at.astimezone(ET).date()


def _expected_basis_keys(selected: dict[str, object]) -> set[str]:
    return {
        f"{tag}:{disclosure['measure_date']}"
        for tag, evidence_key in (
            ("public", "public_float"),
            ("anchor", "anchor_outstanding"),
            ("current", "current_outstanding"),
        )
        if isinstance((disclosure := selected.get(evidence_key)), dict)
    }


def basis_lineage_fingerprint(
    observations: dict[str, TargetBasisObservation],
    *,
    target_date: date,
    selected_evidence: dict[str, object],
    candidate_identity: dict[str, str],
    target_basis_content_sha256: str,
) -> str:
    payload = {
        "float_policy_fingerprint": causal_float_v0_2_manifest()["fingerprint"],
        "identity": {
            "symbol": selected_evidence["symbol"],
            "cik": selected_evidence["cik"],
            **candidate_identity,
        },
        "target_date": target_date.isoformat(),
        "target_basis_source": {
            "artifact_id": FLOAT_TARGET_BASIS_ARTIFACT_ID,
            "content_sha256": target_basis_content_sha256,
        },
        "acquisition_basis": {
            "provider": "alpaca_historical_stock_bars",
            "feed": "sip",
            "measure_timeframe": "1Day",
            "target_timeframe": "1Min",
            "measure_adjustments": ["raw", "split"],
            "target_adjustments": ["raw", "split"],
            "asof": target_date.isoformat(),
            "target_pair_rule": "exact_completed_first_market_qualified_bar",
            "later_target_session_price_used": False,
        },
        "basis_observations": {
            key: asdict(value) for key, value in sorted(observations.items())
        },
    }
    return _json_fingerprint(payload)


def build_causal_float_record(
    selected: dict[str, object],
    observations: dict[str, TargetBasisObservation],
    *,
    candidate: dict[str, object],
    target_date: date,
    target_basis_content_sha256: str,
    sec_status: str,
    sec_provider_error: str | None = None,
) -> dict[str, object]:
    validate_selected_float_evidence_v02(selected)
    identity = _candidate_identity(candidate)
    if identity["symbol"] != selected.get("symbol"):
        raise ValueError("float candidate identity symbol mismatch")
    if identity["selected_cik"].lstrip("0") != str(selected.get("cik") or "").lstrip(
        "0"
    ):
        raise ValueError("float candidate identity CIK mismatch")
    if _candidate_target_date(selected) != target_date:
        raise ValueError("float target date does not match market qualification")
    if not _is_sha256(target_basis_content_sha256):
        raise ValueError("float target-basis source hash is invalid")
    if set(observations) != _expected_basis_keys(selected):
        raise ValueError("float basis observations do not cover selected evidence")
    for observation in observations.values():
        validate_target_basis_observation(observation)
        if observation.target_date != target_date.isoformat():
            raise ValueError("float basis observation target date mismatch")
        if observation.target_source_content_sha256 != target_basis_content_sha256:
            raise ValueError("float observation target-basis source mismatch")
    if sec_status not in _SEC_STATUSES:
        raise ValueError("float SEC status is unsupported")
    if sec_status == "provider_error":
        if not isinstance(sec_provider_error, str) or not sec_provider_error:
            raise ValueError("float provider error status requires an error")
    elif sec_provider_error is not None:
        raise ValueError("float provider error is inconsistent with SEC status")
    row = estimate_float_row(selected, observations)
    classification = "unknown_fail_closed"
    if row.float_pillar_pass is True:
        classification = "pass"
    elif row.float_pillar_pass is False:
        classification = "fail"
    basis_payload = {
        key: asdict(observation) for key, observation in sorted(observations.items())
    }
    return {
        **asdict(row),
        "notes": list(row.notes),
        "float_asof": float_evidence_available_at(selected),
        "float_classification": classification,
        "target_basis_date": target_date.isoformat(),
        "selected_evidence": selected,
        "selected_evidence_sha256": _json_fingerprint(selected),
        "candidate_identity": identity,
        "candidate_identity_sha256": _json_fingerprint(identity),
        "basis_observations": basis_payload,
        "basis_lineage_sha256": basis_lineage_fingerprint(
            observations,
            target_date=target_date,
            selected_evidence=selected,
            candidate_identity=identity,
            target_basis_content_sha256=target_basis_content_sha256,
        ),
        "target_basis_source_artifact_id": FLOAT_TARGET_BASIS_ARTIFACT_ID,
        "target_basis_source_sha256": target_basis_content_sha256,
        "sec_status": sec_status,
        "sec_provider_error": sec_provider_error,
    }


def validate_causal_float_records(
    candidate_rows: Iterable[dict[str, object]],
    records: Iterable[dict[str, object]],
    *,
    expected_trading_date: date | str | None = None,
) -> None:
    candidate_list = list(candidate_rows)
    candidate_symbols = [str(row.get("symbol") or "") for row in candidate_list]
    if "" in candidate_symbols:
        raise ValueError("market candidate is missing a symbol")
    if len(candidate_symbols) != len(set(candidate_symbols)):
        raise ValueError("market candidates repeat a symbol")
    candidates = dict(zip(candidate_symbols, candidate_list, strict=True))
    expected_date = (
        date.fromisoformat(expected_trading_date)
        if isinstance(expected_trading_date, str)
        else expected_trading_date
    )
    for symbol, candidate in candidates.items():
        _market_qualification_timestamps(candidate, context=f"market candidate {symbol}")
        if expected_date is not None and _candidate_target_date(candidate) != expected_date:
            raise ValueError(f"market candidate {symbol} escaped the trading date")

    materialized = list(records)
    record_symbols = [str(row.get("symbol") or "") for row in materialized]
    if len(record_symbols) != len(set(record_symbols)):
        raise ValueError("float records repeat a symbol")
    if set(record_symbols) != set(candidates):
        raise ValueError("float records do not decide every market candidate")
    for record in materialized:
        symbol = str(record["symbol"])
        candidate = candidates[symbol]
        if set(record) != _FLOAT_RECORD_KEYS:
            raise ValueError(f"float record {symbol} fields are invalid")
        target_date = expected_date or _candidate_target_date(candidate)
        if record.get("target_basis_date") != target_date.isoformat():
            raise ValueError(f"float record {symbol} target basis mismatch")
        if record.get("target_basis_source_artifact_id") != FLOAT_TARGET_BASIS_ARTIFACT_ID:
            raise ValueError(f"float record {symbol} target basis artifact mismatch")
        target_basis_content_sha256 = record.get("target_basis_source_sha256")
        if not _is_sha256(target_basis_content_sha256):
            raise ValueError(f"float record {symbol} target basis hash is invalid")
        selected = record.get("selected_evidence")
        if not isinstance(selected, dict):
            raise ValueError(f"float record {symbol} lacks selected evidence")
        validate_selected_float_evidence_v02(selected)
        if selected.get("symbol") != symbol:
            raise ValueError(f"float record {symbol} selected-evidence mismatch")
        for key in (
            "first_market_qualified_bar_started_at",
            "first_market_qualified_at",
        ):
            if selected.get(key) != candidate.get(key) or record.get(key) != candidate.get(key):
                raise ValueError(f"float record {symbol} qualification mismatch")
        selected_cik = str(selected.get("cik") or "").lstrip("0")
        candidate_cik = str(candidate.get("selected_cik") or "").lstrip("0")
        if selected_cik != candidate_cik:
            raise ValueError(f"float record {symbol} CIK mismatch")
        if record.get("selected_evidence_sha256") != _json_fingerprint(selected):
            raise ValueError(f"float record {symbol} evidence fingerprint mismatch")
        identity = record.get("candidate_identity")
        expected_identity = _candidate_identity(candidate)
        if identity != expected_identity:
            raise ValueError(f"float record {symbol} candidate identity mismatch")
        if record.get("candidate_identity_sha256") != _json_fingerprint(
            expected_identity
        ):
            raise ValueError(f"float record {symbol} identity fingerprint mismatch")

        basis = record.get("basis_observations")
        if not isinstance(basis, dict) or set(basis) != _expected_basis_keys(selected):
            raise ValueError(f"float record {symbol} basis audit keys mismatch")
        observations: dict[str, TargetBasisObservation] = {}
        for key, payload in basis.items():
            if not isinstance(key, str) or not isinstance(payload, dict):
                raise ValueError(f"float record {symbol} basis audit is invalid")
            try:
                observation = TargetBasisObservation(**payload)
            except TypeError as error:
                raise ValueError(f"float record {symbol} basis audit is invalid") from error
            _, requested_text = key.split(":", 1)
            if observation.requested_date != requested_text:
                raise ValueError(f"float record {symbol} basis requested-date mismatch")
            if observation.target_date != target_date.isoformat():
                raise ValueError(f"float record {symbol} basis target-date mismatch")
            if observation.target_source_content_sha256 != target_basis_content_sha256:
                raise ValueError(f"float record {symbol} target-basis lineage mismatch")
            validate_target_basis_observation(observation)
            observations[key] = observation
        expected_lineage = basis_lineage_fingerprint(
            observations,
            target_date=target_date,
            selected_evidence=selected,
            candidate_identity=expected_identity,
            target_basis_content_sha256=str(target_basis_content_sha256),
        )
        if record.get("basis_lineage_sha256") != expected_lineage:
            raise ValueError(f"float record {symbol} basis lineage mismatch")

        expected_row = estimate_float_row(selected, observations)
        expected_fields = {**asdict(expected_row), "notes": list(expected_row.notes)}
        for key, expected in expected_fields.items():
            if record.get(key) != expected:
                raise ValueError(f"float record {symbol} derived decision mismatch")
        pillar = record.get("float_pillar_pass")
        if pillar is True:
            classification = "pass"
        elif pillar is False:
            classification = "fail"
        elif pillar is None:
            classification = "unknown_fail_closed"
        else:
            raise ValueError(f"float record {symbol} has invalid pillar decision")
        if record.get("float_classification") != classification:
            raise ValueError(f"float record {symbol} classification mismatch")
        if record.get("float_asof") != float_evidence_available_at(selected):
            raise ValueError(f"float record {symbol} as-of mismatch")
        sec_status = record.get("sec_status")
        if sec_status not in _SEC_STATUSES:
            raise ValueError(f"float record {symbol} SEC status is unsupported")
        if sec_status == "provider_error":
            if not record.get("sec_provider_error"):
                raise ValueError(f"float record {symbol} lost provider error")
            if classification != "unknown_fail_closed":
                raise ValueError(f"provider error for {symbol} did not fail closed")
        elif record.get("sec_provider_error") is not None:
            raise ValueError(f"float record {symbol} has an inconsistent provider error")


def causal_float_records_fingerprint(records: Iterable[dict[str, object]]) -> str:
    return _json_fingerprint(
        sorted(records, key=lambda row: str(row.get("symbol") or ""))
    )


def _validate_candidate_payload(
    candidate_payload: dict[str, object],
    *,
    candidate_rows: list[dict[str, object]],
    trading_date: date,
) -> None:
    if candidate_payload.get("schema_version") != 2:
        raise ValueError("causal float requires market candidate schema v2")
    if candidate_payload.get("artifact_id") != CAUSAL_MARKET_CANDIDATES_V0_3_ARTIFACT_ID:
        raise ValueError("v0.2 float requires v0.3 market candidates")
    if candidate_payload.get("trading_date") != trading_date.isoformat():
        raise ValueError("causal float market candidate date mismatch")
    if candidate_payload.get("rows") != candidate_rows:
        raise ValueError("causal float candidate rows differ from their payload")
    if candidate_payload.get("candidate_count") != len(candidate_rows):
        raise ValueError("causal float candidate payload count mismatch")
    claimed = candidate_payload.get("content_sha256")
    actual = _json_fingerprint(
        {
            key: value
            for key, value in candidate_payload.items()
            if key != "content_sha256"
        }
    )
    if claimed != actual:
        raise ValueError("causal float candidate payload fingerprint mismatch")


def build_causal_float_date_manifest(
    *,
    trading_date: date,
    candidate_rows: list[dict[str, object]],
    candidate_payload: dict[str, object],
    source_market_discovery_manifest_sha256: str,
    source_float_target_basis_sha256: str,
    records: list[dict[str, object]],
    records_file_sha256: str,
    provider_error_count: int,
) -> dict[str, object]:
    _validate_candidate_payload(
        candidate_payload,
        candidate_rows=candidate_rows,
        trading_date=trading_date,
    )
    if not _is_sha256(records_file_sha256):
        raise ValueError("float records file hash is invalid")
    if not _is_sha256(source_market_discovery_manifest_sha256):
        raise ValueError("source market discovery manifest hash is invalid")
    if not _is_sha256(source_float_target_basis_sha256):
        raise ValueError("source float target-basis hash is invalid")
    validate_causal_float_records(
        candidate_rows, records, expected_trading_date=trading_date
    )
    pass_count = sum(row["float_classification"] == "pass" for row in records)
    fail_count = sum(row["float_classification"] == "fail" for row in records)
    unknown_count = sum(
        row["float_classification"] == "unknown_fail_closed" for row in records
    )
    observed_provider_error_count = sum(
        record.get("sec_status") == "provider_error" for record in records
    )
    if provider_error_count != observed_provider_error_count:
        raise ValueError("causal float provider error count mismatch")
    if any(
        record.get("target_basis_source_sha256") != source_float_target_basis_sha256
        for record in records
    ):
        raise ValueError("causal float records use the wrong target-basis source")
    status_counts: dict[str, int] = {}
    method_counts: dict[str, int] = {}
    sec_status_counts: dict[str, int] = {}
    for record in records:
        method = str(record["method"])
        method_counts[method] = method_counts.get(method, 0) + 1
        sec_status = str(record["sec_status"])
        sec_status_counts[sec_status] = sec_status_counts.get(sec_status, 0) + 1
        for observation in record["basis_observations"].values():
            status = str(observation["status"])
            status_counts[status] = status_counts.get(status, 0) + 1
    payload: dict[str, object] = {
        "schema_version": CAUSAL_FLOAT_SCHEMA_VERSION,
        "artifact_id": CAUSAL_FLOAT_POLICY_ID,
        "trading_date": trading_date.isoformat(),
        "float_policy": causal_float_v0_2_manifest(),
        "source_market_candidates_artifact_id": candidate_payload["artifact_id"],
        "source_market_candidates_sha256": candidate_payload["content_sha256"],
        "source_market_discovery_manifest_sha256": source_market_discovery_manifest_sha256,
        "source_float_target_basis_artifact_id": FLOAT_TARGET_BASIS_ARTIFACT_ID,
        "source_float_target_basis_sha256": source_float_target_basis_sha256,
        "summary": {
            "market_candidate_count": len(candidate_rows),
            "float_decision_count": len(records),
            "float_pass_count": pass_count,
            "float_fail_count": fail_count,
            "float_unknown_fail_closed_count": unknown_count,
            "provider_error_count": provider_error_count,
            "float_method_counts": dict(sorted(method_counts.items())),
            "sec_status_counts": dict(sorted(sec_status_counts.items())),
            "basis_status_counts": dict(sorted(status_counts.items())),
            "records_sha256": causal_float_records_fingerprint(records),
        },
        "eligibility": {
            "complete_relative_to_market_candidates": provider_error_count == 0,
            "point_in_time_float_decisions_frozen": provider_error_count == 0,
            "publication_timed_news_complete": False,
            "full_feature_snapshot_complete": False,
            "universe_complete": False,
            "full_walk_forward_eligible": False,
            "policy_promotion_eligible": False,
        },
        "knowledge_policy": {
            "uses_benchmark_labels": False,
            "uses_future_filings": False,
            "raw_future_disclosures_persisted": False,
            "unknown_float_fails_closed": True,
            "post_target_split_factor_cancels": True,
        },
        "files": {
            "float_records": "float-records.json",
            "float_records_file_sha256": records_file_sha256,
        },
    }
    return _with_content_sha256(payload)


def validate_causal_float_date_manifest(
    manifest: dict[str, object],
    *,
    expected_trading_date: date | str | None = None,
    candidate_payload: dict[str, object] | None = None,
    expected_source_market_discovery_manifest_sha256: str | None = None,
    expected_source_float_target_basis_sha256: str | None = None,
) -> None:
    expected_manifest_keys = {
        "schema_version",
        "artifact_id",
        "trading_date",
        "float_policy",
        "source_market_candidates_artifact_id",
        "source_market_candidates_sha256",
        "source_market_discovery_manifest_sha256",
        "source_float_target_basis_artifact_id",
        "source_float_target_basis_sha256",
        "summary",
        "eligibility",
        "knowledge_policy",
        "files",
        "content_sha256",
    }
    if set(manifest) != expected_manifest_keys:
        raise ValueError("causal float date manifest fields are invalid")
    if manifest.get("schema_version") != CAUSAL_FLOAT_SCHEMA_VERSION:
        raise ValueError("unsupported causal float date schema")
    if manifest.get("artifact_id") != CAUSAL_FLOAT_POLICY_ID:
        raise ValueError("unsupported causal float artifact")
    if manifest.get("float_policy") != causal_float_v0_2_manifest():
        raise ValueError("causal float policy mismatch")
    _validate_content_sha256(manifest, label="causal float date manifest")
    try:
        trading_date = date.fromisoformat(str(manifest.get("trading_date") or ""))
    except ValueError as error:
        raise ValueError("causal float date is invalid") from error
    expected = (
        date.fromisoformat(expected_trading_date)
        if isinstance(expected_trading_date, str)
        else expected_trading_date
    )
    if expected is not None and trading_date != expected:
        raise ValueError("causal float date mismatch")
    if manifest.get("source_market_candidates_artifact_id") != (
        CAUSAL_MARKET_CANDIDATES_V0_3_ARTIFACT_ID
    ):
        raise ValueError("v0.2 float requires v0.3 market candidates")
    if candidate_payload is not None:
        candidate_rows = candidate_payload.get("rows")
        if not isinstance(candidate_rows, list) or not all(
            isinstance(row, dict) for row in candidate_rows
        ):
            raise ValueError("causal float candidate payload rows are invalid")
        _validate_candidate_payload(
            candidate_payload,
            candidate_rows=candidate_rows,
            trading_date=trading_date,
        )
        if manifest.get("source_market_candidates_sha256") != candidate_payload.get(
            "content_sha256"
        ):
            raise ValueError("causal float source candidate mismatch")
    source_market_hash = manifest.get("source_market_discovery_manifest_sha256")
    if not _is_sha256(source_market_hash):
        raise ValueError("causal float source market manifest hash is invalid")
    if (
        expected_source_market_discovery_manifest_sha256 is not None
        and source_market_hash != expected_source_market_discovery_manifest_sha256
    ):
        raise ValueError("causal float source market manifest mismatch")
    if manifest.get("source_float_target_basis_artifact_id") != (
        FLOAT_TARGET_BASIS_ARTIFACT_ID
    ):
        raise ValueError("causal float target-basis artifact mismatch")
    target_basis_hash = manifest.get("source_float_target_basis_sha256")
    if not _is_sha256(target_basis_hash):
        raise ValueError("causal float target-basis hash is invalid")
    if (
        expected_source_float_target_basis_sha256 is not None
        and target_basis_hash != expected_source_float_target_basis_sha256
    ):
        raise ValueError("causal float target-basis source mismatch")
    summary = manifest.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("causal float summary is invalid")
    expected_summary_keys = {
        "market_candidate_count",
        "float_decision_count",
        "float_pass_count",
        "float_fail_count",
        "float_unknown_fail_closed_count",
        "provider_error_count",
        "float_method_counts",
        "sec_status_counts",
        "basis_status_counts",
        "records_sha256",
    }
    if set(summary) != expected_summary_keys:
        raise ValueError("causal float summary fields are invalid")
    for key in (
        "market_candidate_count",
        "float_decision_count",
        "float_pass_count",
        "float_fail_count",
        "float_unknown_fail_closed_count",
        "provider_error_count",
    ):
        value = summary.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"causal float {key} is invalid")
    if summary["float_decision_count"] != (
        summary["float_pass_count"]
        + summary["float_fail_count"]
        + summary["float_unknown_fail_closed_count"]
    ):
        raise ValueError("causal float classification counts mismatch")
    if not _is_sha256(summary.get("records_sha256")):
        raise ValueError("causal float records fingerprint is invalid")
    eligibility = manifest.get("eligibility")
    if not isinstance(eligibility, dict):
        raise ValueError("causal float eligibility is invalid")
    expected_eligibility_keys = {
        "complete_relative_to_market_candidates",
        "point_in_time_float_decisions_frozen",
        "publication_timed_news_complete",
        "full_feature_snapshot_complete",
        "universe_complete",
        "full_walk_forward_eligible",
        "policy_promotion_eligible",
    }
    if set(eligibility) != expected_eligibility_keys:
        raise ValueError("causal float eligibility fields are invalid")
    complete = summary["provider_error_count"] == 0
    if eligibility.get("complete_relative_to_market_candidates") is not complete:
        raise ValueError("causal float completeness mismatch")
    if eligibility.get("point_in_time_float_decisions_frozen") is not complete:
        raise ValueError("causal float frozen-decision state mismatch")
    if eligibility.get("full_feature_snapshot_complete") is not False:
        raise ValueError("causal float artifact overclaims feature completeness")
    knowledge = manifest.get("knowledge_policy")
    if not isinstance(knowledge, dict):
        raise ValueError("causal float knowledge policy is invalid")
    required_knowledge = {
        "uses_benchmark_labels": False,
        "uses_future_filings": False,
        "raw_future_disclosures_persisted": False,
        "unknown_float_fails_closed": True,
        "post_target_split_factor_cancels": True,
    }
    if set(knowledge) != set(required_knowledge):
        raise ValueError("causal float knowledge-policy fields are invalid")
    if any(knowledge.get(key) is not value for key, value in required_knowledge.items()):
        raise ValueError("causal float knowledge policy mismatch")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("causal float files are invalid")
    if set(files) != {"float_records", "float_records_file_sha256"}:
        raise ValueError("causal float file fields are invalid")
    relative = files.get("float_records")
    if not isinstance(relative, str) or not relative:
        raise ValueError("causal float artifact lacks records")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("causal float record path must stay inside its artifact")
    if not _is_sha256(files.get("float_records_file_sha256")):
        raise ValueError("causal float records file hash is invalid")


def load_causal_float_records(
    date_root: str | Path,
    *,
    candidate_rows: list[dict[str, object]],
    candidate_payload: dict[str, object],
    expected_trading_date: date | str | None = None,
    expected_source_market_discovery_manifest_sha256: str | None = None,
    expected_source_float_target_basis_sha256: str | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    root = Path(date_root)
    manifest = _load_json(_safe_child(root, "manifest.json"))
    if not isinstance(manifest, dict):
        raise ValueError("causal float manifest must be an object")
    validate_causal_float_date_manifest(
        manifest,
        expected_trading_date=expected_trading_date,
        candidate_payload=candidate_payload,
        expected_source_market_discovery_manifest_sha256=(
            expected_source_market_discovery_manifest_sha256
        ),
        expected_source_float_target_basis_sha256=(
            expected_source_float_target_basis_sha256
        ),
    )
    trading_date = date.fromisoformat(str(manifest["trading_date"]))
    if root.name != trading_date.isoformat():
        raise ValueError("causal float directory date mismatch")
    _validate_candidate_payload(
        candidate_payload,
        candidate_rows=candidate_rows,
        trading_date=trading_date,
    )
    relative = str(manifest["files"]["float_records"])
    records_path = _safe_child(root, relative)
    if file_sha256(records_path) != manifest["files"]["float_records_file_sha256"]:
        raise ValueError("causal float records file fingerprint mismatch")
    payload = _load_json(records_path)
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "artifact_id", "trading_date", "rows"}
        or payload.get("schema_version") != CAUSAL_FLOAT_SCHEMA_VERSION
        or payload.get("artifact_id") != CAUSAL_FLOAT_POLICY_ID
        or payload.get("trading_date") != trading_date.isoformat()
        or not isinstance(payload.get("rows"), list)
        or not all(isinstance(row, dict) for row in payload["rows"])
    ):
        raise ValueError("causal float records payload is invalid")
    records = payload["rows"]
    if [str(row.get("symbol") or "") for row in records] != sorted(
        str(row.get("symbol") or "") for row in records
    ):
        raise ValueError("causal float records are not symbol-sorted")
    validate_causal_float_records(
        candidate_rows, records, expected_trading_date=trading_date
    )
    summary = manifest["summary"]
    expected_counts = {
        "market_candidate_count": len(candidate_rows),
        "float_decision_count": len(records),
        "float_pass_count": sum(
            row.get("float_classification") == "pass" for row in records
        ),
        "float_fail_count": sum(
            row.get("float_classification") == "fail" for row in records
        ),
        "float_unknown_fail_closed_count": sum(
            row.get("float_classification") == "unknown_fail_closed"
            for row in records
        ),
        "provider_error_count": sum(
            row.get("sec_status") == "provider_error" for row in records
        ),
        "float_method_counts": {},
        "sec_status_counts": {},
        "basis_status_counts": {},
    }
    for record in records:
        method = str(record["method"])
        expected_counts["float_method_counts"][method] = (
            expected_counts["float_method_counts"].get(method, 0) + 1
        )
        status = str(record["sec_status"])
        expected_counts["sec_status_counts"][status] = (
            expected_counts["sec_status_counts"].get(status, 0) + 1
        )
        for observation in record["basis_observations"].values():
            basis_status = str(observation["status"])
            expected_counts["basis_status_counts"][basis_status] = (
                expected_counts["basis_status_counts"].get(basis_status, 0) + 1
            )
    for key in ("float_method_counts", "sec_status_counts", "basis_status_counts"):
        expected_counts[key] = dict(sorted(expected_counts[key].items()))
    for key, expected in expected_counts.items():
        if summary.get(key) != expected:
            raise ValueError(f"causal float {key} mismatch")
    if summary.get("records_sha256") != causal_float_records_fingerprint(records):
        raise ValueError("causal float record fingerprint mismatch")
    if any(
        row.get("target_basis_source_sha256")
        != manifest["source_float_target_basis_sha256"]
        for row in records
    ):
        raise ValueError("causal float record target-basis source mismatch")
    return records, manifest


def build_causal_float_root_manifest(
    *,
    dates: list[str],
    source_market_discovery_bundle_sha256: str,
    date_manifest_commitments: list[dict[str, object]],
    fatal_provider_errors: list[dict[str, str]],
    sec_acquisition: dict[str, object],
) -> dict[str, object]:
    if len(dates) != len(set(dates)) or not dates:
        raise ValueError("causal float root dates must be non-empty and unique")
    for value in dates:
        date.fromisoformat(value)
    if [item.get("trading_date") for item in date_manifest_commitments] != dates:
        raise ValueError("causal float date commitments do not match root dates")
    normalized_errors = sorted(
        fatal_provider_errors,
        key=lambda item: (
            str(item.get("trading_date") or ""),
            str(item.get("symbol") or ""),
            str(item.get("error") or ""),
        ),
    )
    payload: dict[str, object] = {
        "schema_version": CAUSAL_FLOAT_SCHEMA_VERSION,
        "artifact_id": CAUSAL_FLOAT_POLICY_ID,
        "dates": dates,
        "float_policy": causal_float_v0_2_manifest(),
        "source_market_discovery_bundle_sha256": source_market_discovery_bundle_sha256,
        "date_manifests": date_manifest_commitments,
        "fatal_provider_errors": normalized_errors,
        "sec_acquisition": sec_acquisition,
        "eligibility": {
            "complete_relative_to_market_candidates": not normalized_errors,
            "point_in_time_float_decisions_frozen": not normalized_errors,
            "publication_timed_news_complete": False,
            "full_feature_snapshot_complete": False,
            "universe_complete": False,
            "full_walk_forward_eligible": False,
            "policy_promotion_eligible": False,
        },
        "knowledge_policy": {
            "uses_benchmark_labels": False,
            "uses_future_filings": False,
            "raw_future_disclosures_persisted": False,
            "unknown_float_fails_closed": True,
            "post_target_split_factor_cancels": True,
        },
    }
    result = _with_content_sha256(payload)
    validate_causal_float_root_manifest(result, expected_dates=dates)
    return result


def validate_causal_float_root_manifest(
    manifest: dict[str, object],
    *,
    expected_dates: Iterable[str] | None = None,
    expected_source_market_discovery_bundle_sha256: str | None = None,
) -> None:
    expected_root_keys = {
        "schema_version",
        "artifact_id",
        "dates",
        "float_policy",
        "source_market_discovery_bundle_sha256",
        "date_manifests",
        "fatal_provider_errors",
        "sec_acquisition",
        "eligibility",
        "knowledge_policy",
        "content_sha256",
    }
    if set(manifest) != expected_root_keys:
        raise ValueError("causal float root fields are invalid")
    if manifest.get("schema_version") != CAUSAL_FLOAT_SCHEMA_VERSION:
        raise ValueError("unsupported causal float root schema")
    if manifest.get("artifact_id") != CAUSAL_FLOAT_POLICY_ID:
        raise ValueError("unsupported causal float root artifact")
    if manifest.get("float_policy") != causal_float_v0_2_manifest():
        raise ValueError("causal float root policy mismatch")
    _validate_content_sha256(manifest, label="causal float root manifest")
    dates = manifest.get("dates")
    if (
        not isinstance(dates, list)
        or not dates
        or not all(isinstance(value, str) for value in dates)
        or len(dates) != len(set(dates))
    ):
        raise ValueError("causal float root dates are invalid")
    for value in dates:
        date.fromisoformat(value)
    if expected_dates is not None and dates != list(expected_dates):
        raise ValueError("causal float root date set mismatch")
    source_hash = manifest.get("source_market_discovery_bundle_sha256")
    if not _is_sha256(source_hash):
        raise ValueError("causal float source discovery hash is invalid")
    if (
        expected_source_market_discovery_bundle_sha256 is not None
        and source_hash != expected_source_market_discovery_bundle_sha256
    ):
        raise ValueError("causal float source discovery bundle mismatch")
    commitments = manifest.get("date_manifests")
    if not isinstance(commitments, list) or len(commitments) != len(dates):
        raise ValueError("causal float root date commitments are invalid")
    if [item.get("trading_date") for item in commitments if isinstance(item, dict)] != dates:
        raise ValueError("causal float root date commitment order mismatch")
    for item in commitments:
        if not isinstance(item, dict):
            raise ValueError("causal float root date commitment is invalid")
        relative = item.get("manifest")
        path = Path(str(relative)) if isinstance(relative, str) else Path("/")
        if (
            set(item)
            != {
                "trading_date",
                "manifest",
                "manifest_file_sha256",
                "manifest_content_sha256",
            }
            or
            not isinstance(relative, str)
            or path.is_absolute()
            or ".." in path.parts
            or not _is_sha256(item.get("manifest_file_sha256"))
            or not _is_sha256(item.get("manifest_content_sha256"))
        ):
            raise ValueError("causal float root date commitment is invalid")
    fatal = manifest.get("fatal_provider_errors")
    if not isinstance(fatal, list) or not all(isinstance(item, dict) for item in fatal):
        raise ValueError("causal float root provider errors are invalid")
    for item in fatal:
        if set(item) != {"trading_date", "symbol", "error"}:
            raise ValueError("causal float root provider error fields are invalid")
        date.fromisoformat(str(item["trading_date"]))
        if item["trading_date"] not in dates or not str(item["symbol"]) or not str(
            item["error"]
        ):
            raise ValueError("causal float root provider error is invalid")
    if fatal != sorted(
        fatal,
        key=lambda item: (item["trading_date"], item["symbol"], item["error"]),
    ):
        raise ValueError("causal float root provider errors are not ordered")
    sec_acquisition = manifest.get("sec_acquisition")
    expected_sec_keys = {
        "unique_successfully_cached_cik_count",
        "cache_hit_count",
        "endpoint_request_count",
        "minimum_request_interval_seconds",
        "attempts_per_endpoint",
    }
    if not isinstance(sec_acquisition, dict) or set(sec_acquisition) != expected_sec_keys:
        raise ValueError("causal float SEC acquisition accounting is invalid")
    for key in (
        "unique_successfully_cached_cik_count",
        "cache_hit_count",
        "endpoint_request_count",
        "attempts_per_endpoint",
    ):
        value = sec_acquisition[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("causal float SEC acquisition count is invalid")
    if sec_acquisition["attempts_per_endpoint"] <= 0:
        raise ValueError("causal float SEC attempts must be positive")
    interval = sec_acquisition["minimum_request_interval_seconds"]
    if (
        isinstance(interval, bool)
        or not isinstance(interval, (int, float))
        or not Decimal(str(interval)).is_finite()
        or Decimal(str(interval)) < 0
    ):
        raise ValueError("causal float SEC request interval is invalid")
    eligibility = manifest.get("eligibility")
    if not isinstance(eligibility, dict):
        raise ValueError("causal float root eligibility is invalid")
    complete = not fatal
    expected_eligibility_keys = {
        "complete_relative_to_market_candidates",
        "point_in_time_float_decisions_frozen",
        "publication_timed_news_complete",
        "full_feature_snapshot_complete",
        "universe_complete",
        "full_walk_forward_eligible",
        "policy_promotion_eligible",
    }
    if set(eligibility) != expected_eligibility_keys:
        raise ValueError("causal float root eligibility fields are invalid")
    if eligibility.get("complete_relative_to_market_candidates") is not complete:
        raise ValueError("causal float root completeness mismatch")
    if eligibility.get("point_in_time_float_decisions_frozen") is not complete:
        raise ValueError("causal float root frozen state mismatch")
    knowledge = manifest.get("knowledge_policy")
    expected_knowledge = {
        "uses_benchmark_labels": False,
        "uses_future_filings": False,
        "raw_future_disclosures_persisted": False,
        "unknown_float_fails_closed": True,
        "post_target_split_factor_cancels": True,
    }
    if not isinstance(knowledge, dict) or knowledge != expected_knowledge:
        raise ValueError("causal float root knowledge policy mismatch")


def load_causal_float_root(
    root: str | Path,
    *,
    expected_dates: Iterable[str] | None = None,
    expected_source_market_discovery_bundle_sha256: str | None = None,
) -> dict[str, object]:
    root_path = Path(root)
    manifest = _load_json(_safe_child(root_path, "manifest.json"))
    if not isinstance(manifest, dict):
        raise ValueError("causal float root manifest must be an object")
    validate_causal_float_root_manifest(
        manifest,
        expected_dates=expected_dates,
        expected_source_market_discovery_bundle_sha256=(
            expected_source_market_discovery_bundle_sha256
        ),
    )
    dates = list(manifest["dates"])
    root_files = sorted(path.name for path in root_path.iterdir() if path.is_file())
    if root_files != ["manifest.json"]:
        raise ValueError("causal float root files mismatch")
    if any(path.is_symlink() for path in root_path.iterdir() if path.is_dir()):
        raise ValueError("causal float root date directory may not be a symlink")
    observed_directories = sorted(
        path.name for path in root_path.iterdir() if path.is_dir()
    )
    if observed_directories != sorted(dates):
        raise ValueError("causal float root date directories mismatch")
    observed_fatal_errors: list[dict[str, str]] = []
    for commitment in manifest["date_manifests"]:
        relative = Path(str(commitment["manifest"]))
        trading_date = str(commitment["trading_date"])
        if relative.as_posix() != f"{trading_date}/manifest.json":
            raise ValueError("causal float date manifest path mismatch")
        manifest_path = _safe_child(root_path, relative.as_posix())
        if file_sha256(manifest_path) != commitment["manifest_file_sha256"]:
            raise ValueError("causal float date manifest file fingerprint mismatch")
        child = _load_json(manifest_path)
        if not isinstance(child, dict):
            raise ValueError("causal float date manifest must be an object")
        validate_causal_float_date_manifest(
            child, expected_trading_date=trading_date
        )
        if child.get("content_sha256") != commitment["manifest_content_sha256"]:
            raise ValueError("causal float date manifest commitment mismatch")
        records_path = _safe_child(
            manifest_path.parent, str(child["files"]["float_records"])
        )
        if file_sha256(records_path) != child["files"]["float_records_file_sha256"]:
            raise ValueError("causal float date records file fingerprint mismatch")
        records_payload = _load_json(records_path)
        if (
            not isinstance(records_payload, dict)
            or set(records_payload)
            != {"schema_version", "artifact_id", "trading_date", "rows"}
            or records_payload.get("schema_version") != CAUSAL_FLOAT_SCHEMA_VERSION
            or records_payload.get("artifact_id") != CAUSAL_FLOAT_POLICY_ID
            or records_payload.get("trading_date") != trading_date
            or not isinstance(records_payload.get("rows"), list)
        ):
            raise ValueError("causal float root records payload is invalid")
        rows = records_payload["rows"]
        if not all(isinstance(row, dict) for row in rows):
            raise ValueError("causal float root record is invalid")
        if [str(row.get("symbol") or "") for row in rows] != sorted(
            str(row.get("symbol") or "") for row in rows
        ):
            raise ValueError("causal float root records are not symbol-sorted")
        synthetic_candidates: list[dict[str, object]] = []
        for row in rows:
            identity = row.get("candidate_identity")
            if not isinstance(identity, dict):
                raise ValueError("causal float root record lacks candidate identity")
            synthetic_candidates.append(
                {
                    **identity,
                    "first_market_qualified_bar_started_at": row.get(
                        "first_market_qualified_bar_started_at"
                    ),
                    "first_market_qualified_at": row.get(
                        "first_market_qualified_at"
                    ),
                }
            )
        validate_causal_float_records(
            synthetic_candidates,
            rows,
            expected_trading_date=trading_date,
        )
        if child["summary"].get("records_sha256") != causal_float_records_fingerprint(rows):
            raise ValueError("causal float root records fingerprint mismatch")
        expected_summary = {
            "market_candidate_count": len(rows),
            "float_decision_count": len(rows),
            "float_pass_count": sum(
                row.get("float_classification") == "pass" for row in rows
            ),
            "float_fail_count": sum(
                row.get("float_classification") == "fail" for row in rows
            ),
            "float_unknown_fail_closed_count": sum(
                row.get("float_classification") == "unknown_fail_closed"
                for row in rows
            ),
            "provider_error_count": sum(
                row.get("sec_status") == "provider_error" for row in rows
            ),
            "float_method_counts": {},
            "sec_status_counts": {},
            "basis_status_counts": {},
            "records_sha256": causal_float_records_fingerprint(rows),
        }
        for row in rows:
            method = str(row["method"])
            expected_summary["float_method_counts"][method] = (
                expected_summary["float_method_counts"].get(method, 0) + 1
            )
            status = str(row["sec_status"])
            expected_summary["sec_status_counts"][status] = (
                expected_summary["sec_status_counts"].get(status, 0) + 1
            )
            for observation in row["basis_observations"].values():
                basis_status = str(observation["status"])
                expected_summary["basis_status_counts"][basis_status] = (
                    expected_summary["basis_status_counts"].get(basis_status, 0) + 1
                )
            if row.get("sec_status") == "provider_error":
                observed_fatal_errors.append(
                    {
                        "trading_date": trading_date,
                        "symbol": str(row["symbol"]),
                        "error": str(row["sec_provider_error"]),
                    }
                )
        for key in ("float_method_counts", "sec_status_counts", "basis_status_counts"):
            expected_summary[key] = dict(sorted(expected_summary[key].items()))
        if child["summary"] != expected_summary:
            raise ValueError("causal float date summary mismatch")
    observed_fatal_errors.sort(
        key=lambda item: (item["trading_date"], item["symbol"], item["error"])
    )
    if manifest["fatal_provider_errors"] != observed_fatal_errors:
        raise ValueError("causal float root provider-error accounting mismatch")
    return manifest


__all__ = [
    "CAUSAL_FLOAT_POLICY_ID",
    "CAUSAL_FLOAT_V0_2_POLICY_ID",
    "CAUSAL_FLOAT_SCHEMA_VERSION",
    "FLOAT_TARGET_BASIS_ARTIFACT_ID",
    "FLOAT_TARGET_BASIS_SCHEMA_VERSION",
    "FLOAT_LIMIT",
    "FloatJoinRow",
    "TargetBasisObservation",
    "TargetSessionPair",
    "basis_lineage_fingerprint",
    "build_causal_float_date_manifest",
    "build_causal_float_record",
    "build_causal_float_root_manifest",
    "build_float_target_basis_payload",
    "causal_float_records_fingerprint",
    "causal_float_v0_2_manifest",
    "estimate_float_row",
    "file_sha256",
    "float_evidence_available_at",
    "infer_public_float_shares",
    "load_causal_float_records",
    "load_causal_float_root",
    "load_float_target_basis",
    "normalize_reported_shares",
    "observe_target_basis",
    "select_float_evidence",
    "validate_causal_float_date_manifest",
    "validate_causal_float_records",
    "validate_causal_float_root_manifest",
    "validate_selected_float_evidence",
    "validate_selected_float_evidence_v02",
    "validate_float_target_basis_payload",
    "validate_target_basis_observation",
    "validate_target_session_pair",
]
