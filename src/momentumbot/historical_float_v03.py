"""Causal SEC float evidence selection and split-basis normalization."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd

from .causal_market_discovery_v03 import (
    CAUSAL_MARKET_CANDIDATES_ARTIFACT_ID,
    CAUSAL_MARKET_CANDIDATES_V0_3_ARTIFACT_ID,
)
from .providers.sec_edgar import ParsedCompanyFacts


ET = ZoneInfo("America/New_York")
FLOAT_LIMIT = 10_000_000
CAUSAL_FLOAT_POLICY_ID = "causal-sec-float-v0.1"


def _json_fingerprint(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def causal_float_v0_1_manifest() -> dict[str, object]:
    payload: dict[str, object] = {
        "policy_id": CAUSAL_FLOAT_POLICY_ID,
        "status": "frozen_research_feature_contract_not_promotable",
        "max_float_shares_exclusive": FLOAT_LIMIT,
        "source": "sec_companyfacts_and_submissions",
        "availability_rule": (
            "filing_acceptance_timestamp_else_conservative_next_session_fallback"
        ),
        "public_float_rule": (
            "sec_public_float_usd_div_split_adjusted_historical_close"
        ),
        "share_basis_rule": (
            "raw_to_split_price_ratio_normalizes_disclosed_shares_to_target_basis"
        ),
        "rollforward_rule": (
            "net_issuance_increases_estimate_buybacks_do_not_reduce_anchor_float"
        ),
        "deterministic_upper_bound_rule": (
            "target_basis_total_outstanding_below_limit_proves_float_pass"
        ),
        "unknown_rule": "missing_or_insufficient_evidence_fails_scanner_float_closed",
    }
    return {**payload, "fingerprint": _json_fingerprint(payload)}


@dataclass(frozen=True, slots=True)
class BasisObservation:
    requested_date: str
    observed_date: str | None
    raw_close: float | None
    split_close: float | None
    share_factor_to_target_basis: float | None


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
    public_float_usd: float | None
    public_float_measure_date: str | None
    public_float_accession: str | None
    public_float_price_used: float | None
    public_float_price_date: str | None
    anchor_outstanding_target_basis: int | None
    current_outstanding_accession: str | None
    current_outstanding_measure_date: str | None
    notes: tuple[str, ...]


def _local_dates(frame: pd.DataFrame) -> list[date]:
    return list(frame.index.tz_convert(ET).date)


def observe_basis(
    raw: pd.DataFrame,
    split: pd.DataFrame,
    requested: date,
) -> BasisObservation:
    if raw.empty or split.empty:
        return BasisObservation(requested.isoformat(), None, None, None, None)
    raw_dates = _local_dates(raw)
    split_dates = _local_dates(split)
    common = sorted(set(raw_dates) & set(split_dates))
    if not common:
        return BasisObservation(requested.isoformat(), None, None, None, None)
    prior = [value for value in common if value <= requested]
    if not prior:
        return BasisObservation(requested.isoformat(), None, None, None, None)
    observed = prior[-1]
    raw_row = raw.iloc[raw_dates.index(observed)]
    split_row = split.iloc[split_dates.index(observed)]
    raw_close = float(raw_row["close"])
    split_close = float(split_row["close"])
    factor = None
    if raw_close > 0 and split_close > 0:
        factor = raw_close / split_close
    return BasisObservation(
        requested.isoformat(),
        observed.isoformat(),
        raw_close,
        split_close,
        factor,
    )


def normalize_shares(
    shares: int,
    basis: BasisObservation,
) -> int | None:
    if basis.share_factor_to_target_basis is None:
        return None
    return max(1, int(round(shares * basis.share_factor_to_target_basis)))


def _row(
    candidate: dict[str, object],
    *,
    method: str,
    estimated_float_shares: int | None,
    current_norm: int | None,
    float_pillar_pass: bool | None,
    public: dict[str, object] | None,
    public_basis: BasisObservation | None,
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
            float(public["public_float_usd"]) if public else None
        ),
        public_float_measure_date=(str(public["measure_date"]) if public else None),
        public_float_accession=(str(public["accession"]) if public else None),
        public_float_price_used=(public_basis.split_close if public_basis else None),
        public_float_price_date=(public_basis.observed_date if public_basis else None),
        anchor_outstanding_target_basis=anchor_norm,
        current_outstanding_accession=(
            str(current["accession"]) if current else None
        ),
        current_outstanding_measure_date=(
            str(current["measure_date"]) if current else None
        ),
        notes=tuple(notes),
    )


def estimate_float_row(
    candidate: dict[str, object],
    observations: dict[str, BasisObservation],
) -> FloatJoinRow:
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
        if current_basis:
            current_norm = normalize_shares(int(current["shares"]), current_basis)
        if current_norm is None:
            notes.append(
                "current outstanding share basis could not be normalized from market data"
            )

    if not public:
        if current_norm is not None and current_norm < FLOAT_LIMIT:
            return _row(
                candidate,
                method="sec_outstanding_shares_upper_bound",
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
    if not public_basis or not public_basis.split_close or public_basis.split_close <= 0:
        notes.append(
            "historical split-adjusted price unavailable for public-float measure date"
        )
        if current_norm is not None and current_norm < FLOAT_LIMIT:
            notes.append(
                "float still passes because total common shares outstanding are below the limit"
            )
            return _row(
                candidate,
                method="sec_outstanding_shares_upper_bound",
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
            method="unknown_missing_public_float_price",
            estimated_float_shares=None,
            current_norm=current_norm,
            float_pillar_pass=None,
            public=public,
            public_basis=None,
            anchor_norm=None,
            notes=notes,
        )

    anchor_float = max(
        1,
        int(round(float(public["public_float_usd"]) / public_basis.split_close)),
    )
    estimated = anchor_float
    anchor_norm = None
    method = "sec_public_float_usd_div_split_adjusted_historical_price"

    if anchor and current:
        anchor_basis = observations.get(f"anchor:{anchor['measure_date']}")
        if anchor_basis:
            anchor_norm = normalize_shares(int(anchor["shares"]), anchor_basis)
        if anchor_norm is not None and current_norm is not None:
            if anchor_float > anchor_norm:
                notes.append(
                    "implied public float exceeds anchor outstanding shares; "
                    "historical-price inversion is noisy"
                )
            else:
                affiliate = anchor_norm - anchor_float
                estimated = max(anchor_float, current_norm - affiliate)
                method = (
                    "sec_public_float_anchor_plus_split_normalized_"
                    "outstanding_rollforward"
                )
        else:
            notes.append(
                "outstanding-share roll-forward skipped because a share basis was unavailable"
            )

    if current_norm is not None and current_norm < FLOAT_LIMIT:
        if estimated > current_norm:
            notes.append(
                "public-float estimate exceeds current outstanding; current total "
                "outstanding is used as the deterministic upper bound"
            )
        else:
            notes.append(
                "total common shares outstanding independently prove float below the limit"
            )
        return _row(
            candidate,
            method="sec_outstanding_shares_upper_bound",
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


def _public_payload(item: object) -> dict[str, object]:
    return {
        "public_float_usd": float(getattr(item, "public_float_usd")),
        "measure_date": getattr(item, "measure_date").isoformat(),
        "available_at": getattr(item, "available_at").isoformat(),
        "accession": str(getattr(item, "accession")),
        "form": str(getattr(item, "form")),
    }


def _outstanding_payload(item: object) -> dict[str, object]:
    return {
        "shares": int(getattr(item, "shares")),
        "measure_date": getattr(item, "measure_date").isoformat(),
        "available_at": getattr(item, "available_at").isoformat(),
        "accession": str(getattr(item, "accession")),
        "form": str(getattr(item, "form")),
    }


def select_float_evidence(
    facts: ParsedCompanyFacts,
    *,
    symbol: str,
    cik: str,
    first_market_qualified_at: datetime,
    first_market_qualified_bar_started_at: datetime | None = None,
) -> dict[str, object]:
    if first_market_qualified_at.tzinfo is None:
        raise ValueError("first market qualification must be timezone-aware")
    if first_market_qualified_bar_started_at is None:
        first_market_qualified_bar_started_at = (
            first_market_qualified_at - timedelta(minutes=1)
        )
    if first_market_qualified_bar_started_at.tzinfo is None:
        raise ValueError("market qualification bar start must be timezone-aware")
    if (
        first_market_qualified_at - first_market_qualified_bar_started_at
        != timedelta(minutes=1)
    ):
        raise ValueError(
            "first market qualification must equal bar start plus one minute"
        )
    eligible_public = [
        item
        for item in facts.public_float
        if item.available_at <= first_market_qualified_at
    ]
    eligible_outstanding = [
        item
        for item in facts.outstanding_shares
        if item.available_at <= first_market_qualified_at
    ]
    public = (
        max(
            eligible_public,
            key=lambda item: (item.measure_date, item.available_at, item.accession),
        )
        if eligible_public
        else None
    )
    current = (
        max(
            eligible_outstanding,
            key=lambda item: (item.measure_date, item.available_at, item.accession),
        )
        if eligible_outstanding
        else None
    )
    anchor = None
    if public and eligible_outstanding:
        anchor = min(
            eligible_outstanding,
            key=lambda item: (
                abs((item.measure_date - public.measure_date).days),
                -item.available_at.timestamp(),
                item.accession,
            ),
        )
    return {
        "symbol": symbol,
        "cik": cik,
        "first_market_qualified_bar_started_at": (
            first_market_qualified_bar_started_at.isoformat()
        ),
        "first_market_qualified_at": first_market_qualified_at.isoformat(),
        "public_float": _public_payload(public) if public else None,
        "anchor_outstanding": _outstanding_payload(anchor) if anchor else None,
        "current_outstanding": _outstanding_payload(current) if current else None,
    }


def float_evidence_available_at(candidate: dict[str, object]) -> str | None:
    values: list[datetime] = []
    for key in ("public_float", "anchor_outstanding", "current_outstanding"):
        disclosure = candidate.get(key)
        if isinstance(disclosure, dict) and disclosure.get("available_at"):
            value = datetime.fromisoformat(str(disclosure["available_at"]))
            if value.tzinfo is None:
                raise ValueError("SEC evidence availability must be timezone-aware")
            values.append(value)
    return max(values).isoformat() if values else None


def validate_selected_float_evidence(candidate: dict[str, object]) -> None:
    """Reject incomplete or future SEC evidence before an artifact is frozen."""

    symbol = str(candidate.get("symbol") or "")
    cik = str(candidate.get("cik") or "")
    if not symbol:
        raise ValueError("selected float evidence requires a symbol")
    _, qualified_at = _market_qualification_timestamps(
        candidate,
        context="selected float evidence",
    )
    for key in ("public_float", "anchor_outstanding", "current_outstanding"):
        disclosure = candidate.get(key)
        if disclosure is None:
            continue
        if not cik:
            raise ValueError("SEC disclosure evidence requires a CIK")
        if not isinstance(disclosure, dict):
            raise ValueError(f"{key} evidence must be an object")
        available_at = datetime.fromisoformat(
            str(disclosure.get("available_at") or "")
        )
        if available_at.tzinfo is None:
            raise ValueError(f"{key} availability must be timezone-aware")
        if available_at > qualified_at:
            raise ValueError(f"future {key} evidence escaped causal selection")
        date.fromisoformat(str(disclosure.get("measure_date") or ""))
        if not str(disclosure.get("accession") or ""):
            raise ValueError(f"{key} evidence requires an accession")


def _market_qualification_timestamps(
    candidate: dict[str, object],
    *,
    context: str,
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
        raise ValueError(
            f"{context} decision timestamp must equal bar start plus one minute"
        )
    return bar_started_at, qualified_at


def selected_float_evidence_fingerprint(candidate: dict[str, object]) -> str:
    validate_selected_float_evidence(candidate)
    return _json_fingerprint(candidate)


def build_causal_float_record(
    selected: dict[str, object],
    observations: dict[str, BasisObservation],
    *,
    sec_status: str,
    sec_provider_error: str | None = None,
) -> dict[str, object]:
    """Build one fail-closed float decision from already-causal evidence."""

    validate_selected_float_evidence(selected)
    row = estimate_float_row(selected, observations)
    classification = "unknown_fail_closed"
    if row.float_pillar_pass is True:
        classification = "pass"
    elif row.float_pillar_pass is False:
        classification = "fail"
    record = {
        **asdict(row),
        "notes": list(row.notes),
        "float_asof": float_evidence_available_at(selected),
        "float_classification": classification,
        "selected_evidence": selected,
        "selected_evidence_sha256": selected_float_evidence_fingerprint(selected),
        "basis_observations": {
            key: asdict(observation)
            for key, observation in sorted(observations.items())
        },
        "sec_status": sec_status,
        "sec_provider_error": sec_provider_error,
    }
    return record


def validate_causal_float_records(
    candidate_rows: Iterable[dict[str, object]],
    records: Iterable[dict[str, object]],
) -> None:
    """Require exactly one internally consistent float disposition per candidate."""

    candidate_list = list(candidate_rows)
    candidate_symbols = [str(row.get("symbol") or "") for row in candidate_list]
    if "" in candidate_symbols:
        raise ValueError("market candidate is missing a symbol")
    if len(candidate_symbols) != len(set(candidate_symbols)):
        raise ValueError("market candidates repeat a symbol")
    candidates = dict(zip(candidate_symbols, candidate_list, strict=True))
    for symbol, candidate in candidates.items():
        _market_qualification_timestamps(
            candidate,
            context=f"market candidate {symbol}",
        )
    materialized = list(records)
    record_symbols = [str(row.get("symbol") or "") for row in materialized]
    if len(record_symbols) != len(set(record_symbols)):
        raise ValueError("float records repeat a symbol")
    if set(record_symbols) != set(candidates):
        raise ValueError("float records do not decide every market candidate")
    for record in materialized:
        symbol = str(record["symbol"])
        candidate = candidates[symbol]
        selected = record.get("selected_evidence")
        if not isinstance(selected, dict):
            raise ValueError(f"float record {symbol} lacks selected evidence")
        validate_selected_float_evidence(selected)
        if selected.get("symbol") != symbol:
            raise ValueError(f"float record {symbol} selected-evidence mismatch")
        for key in (
            "first_market_qualified_bar_started_at",
            "first_market_qualified_at",
        ):
            if selected.get(key) != candidate.get(key):
                raise ValueError(f"float record {symbol} qualification mismatch")
            if record.get(key) != candidate.get(key):
                raise ValueError(f"float record {symbol} qualification mismatch")
        selected_cik = str(selected.get("cik") or "").lstrip("0")
        candidate_cik = str(candidate.get("selected_cik") or "").lstrip("0")
        if selected_cik != candidate_cik:
            raise ValueError(f"float record {symbol} CIK mismatch")
        if record.get("selected_evidence_sha256") != _json_fingerprint(selected):
            raise ValueError(f"float record {symbol} evidence fingerprint mismatch")
        basis = record.get("basis_observations")
        if not isinstance(basis, dict):
            raise ValueError(f"float record {symbol} basis audit is invalid")
        expected_basis_keys = {
            f"{tag}:{disclosure['measure_date']}"
            for tag, evidence_key in (
                ("public", "public_float"),
                ("anchor", "anchor_outstanding"),
                ("current", "current_outstanding"),
            )
            if isinstance((disclosure := selected.get(evidence_key)), dict)
        }
        if set(basis) != expected_basis_keys:
            raise ValueError(f"float record {symbol} basis audit keys mismatch")
        observations: dict[str, BasisObservation] = {}
        for key, observation in basis.items():
            if not isinstance(key, str) or not isinstance(observation, dict):
                raise ValueError(f"float record {symbol} basis audit is invalid")
            try:
                parsed_observation = BasisObservation(**observation)
            except TypeError as error:
                raise ValueError(
                    f"float record {symbol} basis audit is invalid"
                ) from error
            _, expected_requested_text = key.split(":", 1)
            if parsed_observation.requested_date != expected_requested_text:
                raise ValueError(
                    f"float record {symbol} basis requested-date mismatch"
                )
            requested = date.fromisoformat(parsed_observation.requested_date)
            if (
                parsed_observation.observed_date
                and date.fromisoformat(parsed_observation.observed_date) > requested
            ):
                raise ValueError(f"float record {symbol} used a forward basis price")
            raw_close = parsed_observation.raw_close
            split_close = parsed_observation.split_close
            factor = parsed_observation.share_factor_to_target_basis
            if any(
                value is not None
                and (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                )
                for value in (raw_close, split_close, factor)
            ):
                raise ValueError(f"float record {symbol} basis values are invalid")
            if parsed_observation.observed_date is None:
                if any(value is not None for value in (raw_close, split_close, factor)):
                    raise ValueError(
                        f"float record {symbol} empty basis observation is inconsistent"
                    )
            else:
                if raw_close is None or split_close is None:
                    raise ValueError(
                        f"float record {symbol} observed basis lacks close prices"
                    )
                expected_factor = (
                    float(raw_close) / float(split_close)
                    if raw_close > 0 and split_close > 0
                    else None
                )
                if expected_factor is None:
                    if factor is not None:
                        raise ValueError(
                            f"float record {symbol} basis factor is inconsistent"
                        )
                elif factor is None or not math.isclose(
                    float(factor),
                    expected_factor,
                    rel_tol=1e-12,
                    abs_tol=0.0,
                ):
                    raise ValueError(
                        f"float record {symbol} basis factor is inconsistent"
                    )
            observations[key] = parsed_observation
        expected_row = estimate_float_row(selected, observations)
        expected_fields = {**asdict(expected_row), "notes": list(expected_row.notes)}
        for key, expected in expected_fields.items():
            if record.get(key) != expected:
                raise ValueError(f"float record {symbol} derived decision mismatch")
        pillar = record.get("float_pillar_pass")
        if pillar is True:
            expected_classification = "pass"
        elif pillar is False:
            expected_classification = "fail"
        elif pillar is None:
            expected_classification = "unknown_fail_closed"
        else:
            raise ValueError(f"float record {symbol} has invalid pillar decision")
        if record.get("float_classification") != expected_classification:
            raise ValueError(f"float record {symbol} classification mismatch")
        if record.get("float_asof") != float_evidence_available_at(selected):
            raise ValueError(f"float record {symbol} as-of mismatch")
        if record.get("sec_status") == "provider_error":
            if not record.get("sec_provider_error"):
                raise ValueError(f"float record {symbol} lost provider error")
            if record.get("float_classification") != "unknown_fail_closed":
                raise ValueError(f"provider error for {symbol} did not fail closed")


def causal_float_records_fingerprint(records: Iterable[dict[str, object]]) -> str:
    materialized = sorted(records, key=lambda row: str(row.get("symbol") or ""))
    return _json_fingerprint(materialized)


def load_causal_float_records(
    date_root: str | Path,
    *,
    candidate_rows: list[dict[str, object]],
    candidate_payload: dict[str, object],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Load float decisions only after verifying their causal source and contents."""

    root = Path(date_root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("causal float manifest must be an object")
    if manifest.get("artifact_id") != CAUSAL_FLOAT_POLICY_ID:
        raise ValueError("unsupported causal float artifact")
    if manifest.get("schema_version") != 2:
        raise ValueError("unsupported causal float schema")
    if manifest.get("float_policy") != causal_float_v0_1_manifest():
        raise ValueError("causal float policy mismatch")
    candidate_artifact_id = candidate_payload.get("artifact_id")
    if candidate_payload.get("schema_version") != 2 or candidate_artifact_id not in {
        CAUSAL_MARKET_CANDIDATES_ARTIFACT_ID,
        CAUSAL_MARKET_CANDIDATES_V0_3_ARTIFACT_ID,
    }:
        raise ValueError("causal float requires v0.2 or v0.3 market candidates")
    if manifest.get("source_market_candidates_artifact_id") != candidate_artifact_id:
        raise ValueError("causal float source candidate artifact mismatch")
    if manifest.get("source_market_candidates_sha256") != candidate_payload.get(
        "content_sha256"
    ):
        raise ValueError("causal float source candidate mismatch")
    eligibility = manifest.get("eligibility", {})
    if eligibility.get("complete_relative_to_market_candidates") is not True:
        raise ValueError("causal float enrichment is incomplete")
    if eligibility.get("point_in_time_float_decisions_frozen") is not True:
        raise ValueError("causal float decisions are not frozen")
    if eligibility.get("full_feature_snapshot_complete") is not False:
        raise ValueError("causal float artifact overclaims feature completeness")
    knowledge = manifest.get("knowledge_policy", {})
    if knowledge.get("uses_benchmark_labels") is not False:
        raise ValueError("causal float artifact must be label-blind")
    if knowledge.get("uses_future_filings") is not False:
        raise ValueError("causal float artifact used future filings")
    if knowledge.get("raw_future_disclosures_persisted") is not False:
        raise ValueError("causal float artifact persisted future disclosures")
    if knowledge.get("unknown_float_fails_closed") is not True:
        raise ValueError("causal float artifact does not fail unknown float closed")

    relative = manifest.get("files", {}).get("float_records")
    if not isinstance(relative, str) or not relative:
        raise ValueError("causal float artifact lacks records")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("causal float record path must stay inside its artifact")
    payload = json.loads((root / path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        raise ValueError("causal float records payload is invalid")
    records = payload["rows"]
    if not all(isinstance(row, dict) for row in records):
        raise ValueError("causal float record must be an object")
    validate_causal_float_records(candidate_rows, records)
    summary = manifest.get("summary", {})
    if summary.get("market_candidate_count") != len(candidate_rows):
        raise ValueError("causal float source count mismatch")
    if summary.get("float_decision_count") != len(records):
        raise ValueError("causal float decision count mismatch")
    if summary.get("records_sha256") != causal_float_records_fingerprint(records):
        raise ValueError("causal float record fingerprint mismatch")
    expected_counts = {
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
    }
    for key, expected in expected_counts.items():
        if summary.get(key) != expected:
            raise ValueError(f"causal float {key} mismatch")
    return records, manifest
