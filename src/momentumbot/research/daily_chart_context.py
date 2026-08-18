from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Mapping
from zoneinfo import ZoneInfo

import pandas as pd


SCHEMA_VERSION = 1
CONTRACT_ID = "daily-chart-context-shadow-v0.1"
RECORD_TYPE = "causal_daily_chart_evidence"

SESSION_TIMEZONE = "America/New_York"
SOURCE_PROVIDER = "alpaca"
SOURCE_FEED = "sip"
SOURCE_TIMEFRAME = "1Day"
SOURCE_ADJUSTMENT = "split"
REQUESTED_PRIOR_SESSIONS = 60
MOVING_AVERAGE_WINDOWS = (20, 50)
TRAILING_LEVEL_WINDOWS = (5, 20, 50)
RECENT_SESSION_METRIC_WINDOW = 20

CONTEXT_ASSESSMENT_CONTRACT_ID = "discretion-context-assessment-shadow-v0.1"
CONTEXT_HELDOUT_PANEL_ID = "ross-context-heldout-panel-v0.1"
CONTEXT_HELDOUT_PANEL_CONTENT_SHA256 = (
    "d227792368b3bff5c3c2365cacd204c11b7991daeb557efba450c22f076d8898"
)

IDENTITY_IDENTIFIER_KINDS = ("composite_figi", "unique_cik_fallback")
PROHIBITED_OUTPUT_FIELDS = (
    "chart_quality_score",
    "failed_pop_classification",
    "candidate_priority",
    "selection_action",
    "trade_recommendation",
    "order_action",
    "position_size",
    "risk_action",
)

_ET = ZoneInfo(SESSION_TIMEZONE)
_LOWER_HEX = frozenset("0123456789abcdef")
_BAR_COLUMNS = ("open", "high", "low", "close", "volume")
_PROHIBITED_OUTPUTS = {field: None for field in PROHIBITED_OUTPUT_FIELDS}


def canonical_fingerprint(payload: object) -> str:
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("payload must be canonical finite JSON data") from exc
    return hashlib.sha256(encoded).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _LOWER_HEX for character in value)
    )


def _timestamp(value: object, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO timestamp") from exc
    else:
        raise ValueError(f"{field} must be an ISO timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed


def _date(value: object, field: str) -> date:
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO date") from exc
    else:
        raise ValueError(f"{field} must be an ISO date")
    return parsed


def _positive_finite(value: object, field: str) -> float:
    try:
        rendered = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(rendered) or rendered <= 0:
        raise ValueError(f"{field} must be positive and finite")
    return rendered


def _require_exact_keys(
    payload: Mapping[str, object], expected: Iterable[str], field: str
) -> None:
    expected_set = set(expected)
    actual = set(payload)
    if actual != expected_set:
        missing = sorted(expected_set - actual)
        extra = sorted(actual - expected_set)
        raise ValueError(f"{field} fields differ; missing={missing}, extra={extra}")


def validate_daily_chart_context_contract(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported daily-chart context schema")
    if payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected daily-chart context contract ID")
    if payload.get("artifact_type") != "causal_daily_chart_evidence_contract":
        raise ValueError("unexpected daily-chart context artifact type")
    if payload.get("status") != "frozen_schema_builder_no_heldout_runtime_artifact":
        raise ValueError("unexpected daily-chart context status")
    if payload.get("runtime_strategy_effect") != "none":
        raise ValueError("daily-chart context must remain shadow-only")
    for field in (
        "policy_promotion_eligible",
        "ai_order_authority",
        "ai_risk_authority",
        "chart_threshold_frozen",
        "failed_pop_classifier_frozen",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must be false")

    source = payload.get("source_acquisition")
    if not isinstance(source, Mapping):
        raise ValueError("source_acquisition must be an object")
    expected_source = {
        "provider": SOURCE_PROVIDER,
        "feed": SOURCE_FEED,
        "timeframe": SOURCE_TIMEFRAME,
        "adjustment": SOURCE_ADJUSTMENT,
        "adjustment_asof": "decision_session_date",
        "requested_prior_completed_sessions": REQUESTED_PRIOR_SESSIONS,
        "current_session_complete_bar_allowed": False,
        "future_session_bar_allowed": False,
        "provider_error_becomes_empty_evidence": False,
    }
    if dict(source) != expected_source:
        raise ValueError("source acquisition differs from the frozen contract")

    identity = payload.get("identity_boundary")
    if not isinstance(identity, Mapping):
        raise ValueError("identity_boundary must be an object")
    expected_identity = {
        "accepted_identifier_kinds": list(IDENTITY_IDENTIFIER_KINDS),
        "evidence_emission_requires_verified_continuity_window": True,
        "minimum_existing_verified_lookback_calendar_days": 120,
        "moving_average_200_deferred": True,
        "moving_average_200_deferred_reason": (
            "existing_identity_continuity_is_not_frozen_for_a_200_session_window"
        ),
    }
    if dict(identity) != expected_identity:
        raise ValueError("identity boundary differs from the frozen contract")

    features = payload.get("feature_protocol")
    if not isinstance(features, Mapping):
        raise ValueError("feature_protocol must be an object")
    if features.get("moving_average_windows_sessions") != list(
        MOVING_AVERAGE_WINDOWS
    ):
        raise ValueError("moving-average windows differ from the contract")
    if features.get("trailing_level_windows_sessions") != list(
        TRAILING_LEVEL_WINDOWS
    ):
        raise ValueError("trailing-level windows differ from the contract")
    if features.get("recent_session_metric_window") != RECENT_SESSION_METRIC_WINDOW:
        raise ValueError("recent-session metric window differs from the contract")
    expected_formulas = {
        "simple_moving_average": "mean(close over trailing completed sessions)",
        "open_gap_pct": "(open / previous_close - 1) * 100",
        "high_excursion_pct": "(high / previous_close - 1) * 100",
        "close_change_pct": "(close / previous_close - 1) * 100",
        "high_to_close_fade_pct": "(high - close) / high * 100",
        "upper_wick_fraction": "(high - max(open, close)) / (high - low)",
        "volume_multiple_to_prior_20_mean": (
            "volume / mean(volume of 20 completed sessions preceding that session)"
        ),
        "overhead_distance_pct": "(level_price / decision_price - 1) * 100",
    }
    if features.get("formulas") != expected_formulas:
        raise ValueError("daily-chart formulas differ from the contract")
    if features.get("failed_pop_threshold") is not None:
        raise ValueError("failed-pop threshold must remain unfrozen")
    if features.get("chart_quality_score") is not None:
        raise ValueError("chart quality score must remain unfrozen")
    if features.get("insufficient_history_is_explicit") is not True:
        raise ValueError("insufficient history must remain explicit")

    binding = payload.get("context_binding")
    expected_binding = {
        "context_assessment_contract_id": CONTEXT_ASSESSMENT_CONTRACT_ID,
        "evidence_domain": "daily_chart",
        "record_type": RECORD_TYPE,
        "source_artifact_hash_required_before_snapshot_binding": True,
    }
    if binding != expected_binding:
        raise ValueError("context binding differs from the frozen contract")
    if payload.get("prohibited_outputs") != list(PROHIBITED_OUTPUT_FIELDS):
        raise ValueError("prohibited outputs differ from the frozen contract")

    evaluation = payload.get("evaluation_boundary")
    expected_evaluation = {
        "registered_panel_id": CONTEXT_HELDOUT_PANEL_ID,
        "registered_panel_content_sha256": CONTEXT_HELDOUT_PANEL_CONTENT_SHA256,
        "runtime_frozen_before_recap_review": True,
        "raw_transcripts_allowed_in_runtime": False,
        "retrospective_labels_allowed_in_runtime": False,
        "policy_promotion_from_this_contract_allowed": False,
    }
    if evaluation != expected_evaluation:
        raise ValueError("evaluation boundary differs from the frozen contract")


def load_daily_chart_context_contract(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("daily-chart context contract root must be an object")
    validate_daily_chart_context_contract(payload)
    return payload


def _canonical_source_rows(
    bars: pd.DataFrame,
    *,
    decision_session_date: date,
) -> list[dict[str, object]]:
    if not isinstance(bars, pd.DataFrame) or bars.empty:
        raise ValueError("daily-chart evidence requires at least one source bar")
    missing = [column for column in _BAR_COLUMNS if column not in bars.columns]
    if missing:
        raise ValueError(f"daily source bars are missing columns: {missing}")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("daily source bar timestamps must be timezone-aware")
    if bars.index.has_duplicates:
        raise ValueError("daily source bars repeat a timestamp")
    if not bars.index.is_monotonic_increasing:
        raise ValueError("daily source bars must be ordered")

    selected = bars.tail(REQUESTED_PRIOR_SESSIONS)
    rows: list[dict[str, object]] = []
    seen_session_dates: set[str] = set()
    for timestamp, source in selected.iterrows():
        session_date = timestamp.tz_convert(_ET).date()
        if session_date >= decision_session_date:
            raise ValueError(
                "daily source bars must be strictly before the decision session"
            )
        rendered_date = session_date.isoformat()
        if rendered_date in seen_session_dates:
            raise ValueError("daily source bars repeat a session date")
        seen_session_dates.add(rendered_date)

        values = {
            column: _positive_finite(source[column], f"daily bar {column}")
            for column in ("open", "high", "low", "close")
        }
        if values["low"] > min(values["open"], values["close"], values["high"]):
            raise ValueError("daily bar low exceeds another price")
        if values["high"] < max(values["open"], values["close"], values["low"]):
            raise ValueError("daily bar high is below another price")
        try:
            volume_number = float(source["volume"])
        except (TypeError, ValueError) as exc:
            raise ValueError("daily bar volume must be numeric") from exc
        if (
            not math.isfinite(volume_number)
            or volume_number < 0
            or not volume_number.is_integer()
        ):
            raise ValueError("daily bar volume must be a nonnegative integer")
        rows.append(
            {
                "source_timestamp": timestamp.isoformat(),
                "session_date": rendered_date,
                **values,
                "volume": int(volume_number),
            }
        )
    return rows


def _availability(value: float | None, *, window: int, count: int) -> dict[str, object]:
    return {
        "window_sessions": window,
        "sessions_available": min(count, window),
        "state": "available" if value is not None else "insufficient_history",
        "value": value,
    }


def _moving_averages(rows: list[dict[str, object]]) -> dict[str, object]:
    output: dict[str, object] = {}
    for window in MOVING_AVERAGE_WINDOWS:
        value = None
        if len(rows) >= window:
            value = sum(float(row["close"]) for row in rows[-window:]) / window
        output[f"sma_{window}"] = _availability(
            value,
            window=window,
            count=len(rows),
        )
    return output


def _trailing_levels(rows: list[dict[str, object]]) -> dict[str, object]:
    output: dict[str, object] = {}
    for window in TRAILING_LEVEL_WINDOWS:
        if len(rows) < window:
            output[f"sessions_{window}"] = {
                "window_sessions": window,
                "sessions_available": len(rows),
                "state": "insufficient_history",
                "highest_high": None,
                "highest_high_session_date": None,
                "lowest_low": None,
                "lowest_low_session_date": None,
            }
            continue
        selected = rows[-window:]
        highest = max(float(row["high"]) for row in selected)
        lowest = min(float(row["low"]) for row in selected)
        highest_date = next(
            str(row["session_date"])
            for row in reversed(selected)
            if float(row["high"]) == highest
        )
        lowest_date = next(
            str(row["session_date"])
            for row in reversed(selected)
            if float(row["low"]) == lowest
        )
        output[f"sessions_{window}"] = {
            "window_sessions": window,
            "sessions_available": window,
            "state": "available",
            "highest_high": highest,
            "highest_high_session_date": highest_date,
            "lowest_low": lowest,
            "lowest_low_session_date": lowest_date,
        }
    return output


def _recent_session_metrics(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    first_index = max(1, len(rows) - RECENT_SESSION_METRIC_WINDOW)
    for index in range(first_index, len(rows)):
        row = rows[index]
        previous_close = float(rows[index - 1]["close"])
        open_price = float(row["open"])
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        volume = int(row["volume"])
        prior_volume_mean = None
        volume_multiple = None
        if index >= 20:
            prior_volume_mean = sum(
                int(value["volume"]) for value in rows[index - 20 : index]
            ) / 20
            if prior_volume_mean > 0:
                volume_multiple = volume / prior_volume_mean
        session_range = high - low
        output.append(
            {
                "session_date": row["session_date"],
                "previous_close": previous_close,
                "open_gap_pct": (open_price / previous_close - 1.0) * 100.0,
                "high_excursion_pct": (high / previous_close - 1.0) * 100.0,
                "close_change_pct": (close / previous_close - 1.0) * 100.0,
                "high_to_close_fade_pct": (high - close) / high * 100.0,
                "upper_wick_fraction": (
                    (high - max(open_price, close)) / session_range
                    if session_range > 0
                    else 0.0
                ),
                "volume": volume,
                "prior_20_session_mean_volume": prior_volume_mean,
                "volume_multiple_to_prior_20_mean": volume_multiple,
            }
        )
    return output


def _overhead_references(
    *,
    decision_price: float,
    moving_averages: Mapping[str, object],
    trailing_levels: Mapping[str, object],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for window in MOVING_AVERAGE_WINDOWS:
        source = moving_averages[f"sma_{window}"]
        if not isinstance(source, Mapping) or source.get("state") != "available":
            continue
        price = float(source["value"])
        if price > decision_price:
            rows.append(
                {
                    "source_type": "simple_moving_average",
                    "window_sessions": window,
                    "level_price": price,
                    "distance_pct": (price / decision_price - 1.0) * 100.0,
                }
            )
    for window in TRAILING_LEVEL_WINDOWS:
        source = trailing_levels[f"sessions_{window}"]
        if not isinstance(source, Mapping) or source.get("state") != "available":
            continue
        price = float(source["highest_high"])
        if price > decision_price:
            rows.append(
                {
                    "source_type": "trailing_high",
                    "window_sessions": window,
                    "level_price": price,
                    "distance_pct": (price / decision_price - 1.0) * 100.0,
                }
            )
    return sorted(
        rows,
        key=lambda row: (
            float(row["distance_pct"]),
            str(row["source_type"]),
            int(row["window_sessions"]),
        ),
    )


def _materialize_record(
    *,
    rows: list[dict[str, object]],
    symbol: str,
    decision_time: datetime,
    decision_price: float,
    identity_identifier_kind: str,
    identity_identifier: str,
    identity_verified_start_date: date,
    identity_verified_through_date: date,
) -> dict[str, object]:
    decision_session_date = decision_time.astimezone(_ET).date()
    earliest = _date(rows[0]["session_date"], "first source session")
    if identity_verified_start_date > earliest:
        raise ValueError("identity verification does not cover the source-bar window")
    if identity_verified_through_date < decision_session_date:
        raise ValueError("identity verification does not reach the decision session")

    moving_averages = _moving_averages(rows)
    trailing_levels = _trailing_levels(rows)
    overhead = _overhead_references(
        decision_price=decision_price,
        moving_averages=moving_averages,
        trailing_levels=trailing_levels,
    )
    latest_date = str(rows[-1]["session_date"])
    record: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "record_type": RECORD_TYPE,
        "contract_id": CONTRACT_ID,
        "symbol": symbol,
        "decision_time": decision_time.isoformat(),
        "decision_session_date": decision_session_date.isoformat(),
        "decision_price": decision_price,
        "evidence_available_at": decision_time.isoformat(),
        "identity_continuity": {
            "identifier_kind": identity_identifier_kind,
            "identifier": identity_identifier,
            "verified_start_date": identity_verified_start_date.isoformat(),
            "verified_through_date": identity_verified_through_date.isoformat(),
            "covers_included_source_window": True,
        },
        "source_request": {
            "provider": SOURCE_PROVIDER,
            "feed": SOURCE_FEED,
            "timeframe": SOURCE_TIMEFRAME,
            "adjustment": SOURCE_ADJUSTMENT,
            "adjustment_asof": decision_session_date.isoformat(),
        },
        "causal_cutoff": {
            "decision_session_bar_used": False,
            "future_session_bar_used": False,
            "latest_completed_session_date": latest_date,
            "all_source_sessions_precede_decision_session": True,
        },
        "coverage": {
            "requested_prior_completed_sessions": REQUESTED_PRIOR_SESSIONS,
            "included_prior_completed_sessions": len(rows),
            "history_complete_for_requested_window": (
                len(rows) == REQUESTED_PRIOR_SESSIONS
            ),
            "earliest_included_session_date": rows[0]["session_date"],
            "latest_included_session_date": latest_date,
            "moving_average_200_available": False,
            "moving_average_200_status": "deferred_identity_window_not_frozen",
        },
        "source_bar_rows": rows,
        "source_bar_rows_content_sha256": canonical_fingerprint(rows),
        "features": {
            "prior_completed_session": dict(rows[-1]),
            "moving_averages": moving_averages,
            "trailing_levels": trailing_levels,
            "recent_session_metrics": _recent_session_metrics(rows),
            "overhead_reference_levels": overhead,
            "nearest_overhead_reference": dict(overhead[0]) if overhead else None,
        },
        "prohibited_outputs": dict(_PROHIBITED_OUTPUTS),
    }
    record["record_content_sha256"] = canonical_fingerprint(record)
    return record


def build_daily_chart_evidence(
    bars: pd.DataFrame,
    *,
    symbol: str,
    decision_time: datetime | str,
    decision_price: float,
    identity_identifier_kind: str,
    identity_identifier: str,
    identity_verified_start_date: date | str,
    identity_verified_through_date: date | str,
) -> dict[str, object]:
    """Build deterministic daily-chart evidence with no selection authority."""

    rendered_symbol = str(symbol).strip().upper()
    if not rendered_symbol:
        raise ValueError("symbol is required")
    rendered_decision = _timestamp(decision_time, "decision_time")
    rendered_price = _positive_finite(decision_price, "decision_price")
    if identity_identifier_kind not in IDENTITY_IDENTIFIER_KINDS:
        raise ValueError("identity identifier kind is not accepted")
    rendered_identifier = str(identity_identifier).strip().upper()
    if not rendered_identifier:
        raise ValueError("identity identifier is required")
    verified_start = _date(identity_verified_start_date, "identity_verified_start_date")
    verified_through = _date(
        identity_verified_through_date,
        "identity_verified_through_date",
    )
    if verified_start > verified_through:
        raise ValueError("identity verification start follows its end")
    decision_session_date = rendered_decision.astimezone(_ET).date()
    rows = _canonical_source_rows(
        bars,
        decision_session_date=decision_session_date,
    )
    record = _materialize_record(
        rows=rows,
        symbol=rendered_symbol,
        decision_time=rendered_decision,
        decision_price=rendered_price,
        identity_identifier_kind=identity_identifier_kind,
        identity_identifier=rendered_identifier,
        identity_verified_start_date=verified_start,
        identity_verified_through_date=verified_through,
    )
    validate_daily_chart_evidence(record)
    return record


def validate_daily_chart_evidence(record: Mapping[str, object]) -> None:
    expected_keys = {
        "schema_version",
        "record_type",
        "contract_id",
        "symbol",
        "decision_time",
        "decision_session_date",
        "decision_price",
        "evidence_available_at",
        "identity_continuity",
        "source_request",
        "causal_cutoff",
        "coverage",
        "source_bar_rows",
        "source_bar_rows_content_sha256",
        "features",
        "prohibited_outputs",
        "record_content_sha256",
    }
    _require_exact_keys(record, expected_keys, "daily_chart_evidence")
    if record.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported daily-chart evidence schema")
    if record.get("record_type") != RECORD_TYPE or record.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected daily-chart evidence identity")
    if record.get("prohibited_outputs") != _PROHIBITED_OUTPUTS:
        raise ValueError("daily-chart prohibited outputs must remain null")
    supplied_hash = record.get("record_content_sha256")
    if not _is_sha256(supplied_hash):
        raise ValueError("daily-chart evidence hash must be lowercase SHA-256")
    unhashed = dict(record)
    unhashed.pop("record_content_sha256")
    if canonical_fingerprint(unhashed) != supplied_hash:
        raise ValueError("daily-chart evidence fingerprint mismatch")

    rows = record.get("source_bar_rows")
    if not isinstance(rows, list) or not rows or len(rows) > REQUESTED_PRIOR_SESSIONS:
        raise ValueError("daily-chart source rows have invalid coverage")
    if canonical_fingerprint(rows) != record.get("source_bar_rows_content_sha256"):
        raise ValueError("daily-chart source-row fingerprint mismatch")
    frame = pd.DataFrame(rows)
    if "source_timestamp" not in frame:
        raise ValueError("daily-chart source rows lack timestamps")
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame.pop("source_timestamp")))
    decision = _timestamp(record.get("decision_time"), "decision_time")
    decision_session_date = decision.astimezone(_ET).date()
    if record.get("decision_session_date") != decision_session_date.isoformat():
        raise ValueError("daily-chart decision session date mismatch")
    if record.get("evidence_available_at") != decision.isoformat():
        raise ValueError("daily-chart evidence availability mismatch")
    canonical_rows = _canonical_source_rows(
        frame,
        decision_session_date=decision_session_date,
    )
    if canonical_rows != rows:
        raise ValueError("daily-chart source rows are not canonical")

    identity = record.get("identity_continuity")
    if not isinstance(identity, Mapping):
        raise ValueError("daily-chart identity continuity must be an object")
    _require_exact_keys(
        identity,
        {
            "identifier_kind",
            "identifier",
            "verified_start_date",
            "verified_through_date",
            "covers_included_source_window",
        },
        "identity_continuity",
    )
    if identity.get("covers_included_source_window") is not True:
        raise ValueError("daily-chart identity continuity must cover the source window")
    if identity.get("identifier_kind") not in IDENTITY_IDENTIFIER_KINDS:
        raise ValueError("daily-chart identity identifier kind is not accepted")
    if not str(identity.get("identifier") or "").strip():
        raise ValueError("daily-chart identity identifier is required")
    symbol = str(record.get("symbol") or "").strip().upper()
    if not symbol or record.get("symbol") != symbol:
        raise ValueError("daily-chart symbol must be canonical uppercase")
    expected = _materialize_record(
        rows=canonical_rows,
        symbol=symbol,
        decision_time=decision,
        decision_price=_positive_finite(record.get("decision_price"), "decision_price"),
        identity_identifier_kind=str(identity.get("identifier_kind") or ""),
        identity_identifier=str(identity.get("identifier") or ""),
        identity_verified_start_date=_date(
            identity.get("verified_start_date"),
            "identity verified start",
        ),
        identity_verified_through_date=_date(
            identity.get("verified_through_date"),
            "identity verified through",
        ),
    )
    if dict(record) != expected:
        raise ValueError("daily-chart evidence differs from deterministic reconstruction")


def daily_chart_supplemental_evidence(
    record: Mapping[str, object],
    *,
    source_artifact_content_sha256: str,
) -> dict[str, object]:
    """Bind a frozen daily-chart record to a context snapshot evidence item."""

    validate_daily_chart_evidence(record)
    if not _is_sha256(source_artifact_content_sha256):
        raise ValueError("source artifact hash must be lowercase SHA-256")
    return {
        "evidence_id": (
            f"daily-chart:{record['symbol']}:{record['record_content_sha256']}"
        ),
        "domain": "daily_chart",
        "available_at": record["evidence_available_at"],
        "source_contract_id": CONTRACT_ID,
        "source_artifact_content_sha256": source_artifact_content_sha256,
        "payload": dict(record),
    }
