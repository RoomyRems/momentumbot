"""Validation for the unarmed Micro-v0.1 behavioral cohort registration."""

from __future__ import annotations

import calendar
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Mapping

from momentumbot.research.microstructure_contract import canonical_fingerprint


SCHEMA_VERSION = 1
COHORT_ID = "microstructure-behavioral-cohort-v0.1"
COHORT_CONTENT_SHA256 = (
    "2f97f8f2916113cf3e29fe398da7f38d72c1db0b79704cadb0b635ea062a939e"
)
PARENT_PROTOCOL_CONTENT_SHA256 = (
    "7409973d369876d29a020785cc2f48bc945129d705648f793d693667dcdd3802"
)
HISTORICAL_ACCOUNT_MANIFEST_CONTENT_SHA256 = (
    "e9dd428d30790dcbf9cd2d171cc2c86ef41a71e4c9a2463d24bfaa34d7048a48"
)
MICRO_RUNTIME_ARTIFACT_ZIP_SHA256 = (
    "3b59e4b1a69e268158f6ccbead1fe9abae425fc249e72b34f466e53ebba56b20"
)
REGISTERED_HORIZON_MAX_NS = 10_000_000_000
EXPECTED_OPPORTUNITY_COUNT = 10
EXPECTED_REQUEST_COUNT = 5
EXPECTED_SYMBOL_DATE_COUNT = 7
EXPECTED_QUANTITY_TOTAL = 5_558
HARD_COST_CEILING_USD = Decimal("0.25")
HARD_SIZE_CEILING_BYTES = 225_000_000

_TIMESTAMP = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})T"
    r"(?P<clock>\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<fraction>\d{1,9}))?(?:Z|\+00:00)$"
)


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object in {path}")
    return payload


def _text(mapping: Mapping[str, object], field: str) -> str:
    value = mapping.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be nonempty text")
    return value


def timestamp_ns(value: object) -> int:
    if not isinstance(value, str):
        raise ValueError("timestamp must be text")
    match = _TIMESTAMP.fullmatch(value)
    if match is None:
        raise ValueError(f"timestamp is not canonical UTC: {value}")
    base = datetime.strptime(
        f"{match.group('date')}T{match.group('clock')}",
        "%Y-%m-%dT%H:%M:%S",
    )
    fraction = (match.group("fraction") or "").ljust(9, "0")
    return calendar.timegm(base.timetuple()) * 1_000_000_000 + int(fraction or 0)


def _canonical_timestamp(value_ns: int) -> str:
    seconds, nanos = divmod(value_ns, 1_000_000_000)
    base = datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%S")
    if nanos == 0:
        return f"{base}Z"
    return f"{base}.{nanos:09d}Z"


def _validate_opportunities(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    rows = payload.get("opportunities")
    if not isinstance(rows, list) or len(rows) != EXPECTED_OPPORTUNITY_COUNT:
        raise ValueError("cohort must contain exactly ten opportunities")
    if not all(isinstance(row, Mapping) for row in rows):
        raise ValueError("every opportunity must be an object")
    opportunities: list[Mapping[str, object]] = list(rows)

    opportunity_ids: set[str] = set()
    plan_ids: set[str] = set()
    sort_keys: list[tuple[str, int, str, str]] = []
    forbidden = {"exit_price", "exit_time", "pnl", "target_touched", "ross_action"}
    for row in opportunities:
        if forbidden.intersection(row):
            raise ValueError("cohort opportunities cannot carry retrospective outcomes")
        date = _text(row, "trading_date")
        symbol = _text(row, "symbol")
        if symbol != symbol.upper():
            raise ValueError("symbols must be uppercase")
        if row.get("account_class") != "main":
            raise ValueError("only the frozen main-account cohort is registered")
        if row.get("role") not in {"starter", "reentry"}:
            raise ValueError("unexpected opportunity role")
        opportunity_id = _text(row, "opportunity_id")
        plan_id = _text(row, "plan_id")
        if opportunity_id in opportunity_ids or plan_id in plan_ids:
            raise ValueError("opportunity and plan identities must be unique")
        opportunity_ids.add(opportunity_id)
        plan_ids.add(plan_id)
        quantity = row.get("prospective_order_quantity")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("prospective quantity must be a positive whole share count")

        anchor = timestamp_ns(row.get("anchor_receive_time"))
        armed = timestamp_ns(row.get("armed_at"))
        expires = timestamp_ns(row.get("expires_at"))
        source_bar = timestamp_ns(row.get("source_bar_start"))
        if not source_bar < armed <= anchor < expires:
            raise ValueError("causal plan timestamps are inconsistent")
        if not _text(row, "anchor_receive_time").startswith(date):
            raise ValueError("anchor date differs from trading date")
        for field in (
            "trigger_print_price",
            "breakout_level",
            "minimum_new_high_price",
            "stop_price",
        ):
            value = row.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ValueError(f"{field} must be positive")
        if row["minimum_new_high_price"] <= row["breakout_level"]:  # type: ignore[operator]
            raise ValueError("minimum new high must exceed the breakout level")
        if row["trigger_print_price"] < row["minimum_new_high_price"]:  # type: ignore[operator]
            raise ValueError("trigger print cannot be below the plan trigger")
        if not isinstance(row.get("trigger_via_odd_lot"), bool):
            raise ValueError("odd-lot trigger flag must be boolean")
        if not _text(row, "micro_runtime_path").endswith("/runtime-replay.json"):
            raise ValueError("opportunity must bind a runtime replay")
        if len(_text(row, "micro_runtime_content_sha256")) != 64:
            raise ValueError("runtime content hash must be SHA-256 text")
        sort_keys.append((date, anchor, symbol, plan_id))

    if sort_keys != sorted(sort_keys):
        raise ValueError("opportunities are not in their frozen causal order")
    return opportunities


def _validate_request_surface(
    payload: Mapping[str, object], opportunities: list[Mapping[str, object]]
) -> None:
    surface = payload.get("request_surface")
    if not isinstance(surface, Mapping):
        raise ValueError("exact request surface is required")
    requests = surface.get("requests")
    if not isinstance(requests, list) or len(requests) != EXPECTED_REQUEST_COUNT:
        raise ValueError("exactly five date-grouped requests are required")
    if surface.get("exact_request_count") != EXPECTED_REQUEST_COUNT:
        raise ValueError("request count summary changed")
    if surface.get("exact_symbol_date_count") != EXPECTED_SYMBOL_DATE_COUNT:
        raise ValueError("symbol-date count summary changed")

    opportunities_by_date: dict[str, list[Mapping[str, object]]] = {}
    for row in opportunities:
        opportunities_by_date.setdefault(str(row["trading_date"]), []).append(row)
    if len(opportunities_by_date) != EXPECTED_REQUEST_COUNT:
        raise ValueError("request count must equal selected trading-date count")

    request_ids: set[str] = set()
    request_dates: list[str] = []
    for item in requests:
        if not isinstance(item, Mapping):
            raise ValueError("request must be an object")
        request_id = _text(item, "request_id")
        date = _text(item, "trading_date")
        if request_id in request_ids or date in request_dates:
            raise ValueError("request IDs and dates must be unique")
        request_ids.add(request_id)
        request_dates.append(date)
        if item.get("dataset") != "XNAS.ITCH" or item.get("schema") != "mbo":
            raise ValueError("request dataset or schema changed")
        if item.get("stype_in") != "raw_symbol":
            raise ValueError("request symbol type changed")
        expected_rows = opportunities_by_date.get(date)
        if expected_rows is None:
            raise ValueError("request date has no opportunity")
        expected_symbols = sorted({str(row["symbol"]) for row in expected_rows})
        if item.get("symbols") != expected_symbols:
            raise ValueError("request symbols do not exactly cover the cohort date")
        if item.get("start") != f"{date}T00:00:00Z":
            raise ValueError("request must begin at midnight UTC")
        latest_anchor = max(timestamp_ns(row["anchor_receive_time"]) for row in expected_rows)
        expected_end = _canonical_timestamp(
            latest_anchor + REGISTERED_HORIZON_MAX_NS + 1
        )
        if item.get("end") != expected_end:
            raise ValueError("request end is not the minimum exact inclusive-window bound")
    if request_dates != sorted(request_dates):
        raise ValueError("requests must be ordered by trading date")


def validate_behavioral_cohort(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported behavioral-cohort schema")
    if payload.get("cohort_id") != COHORT_ID:
        raise ValueError("unexpected behavioral cohort")
    if payload.get("artifact_type") != (
        "preregistered_unarmed_label_blind_microstructure_behavioral_cohort"
    ):
        raise ValueError("unexpected behavioral-cohort artifact type")
    if payload.get("registration_status") != (
        "frozen_before_cohort_microstructure_values_outcomes_or_provider_quotes"
    ):
        raise ValueError("cohort timing boundary changed")
    if payload.get("runtime_strategy_effect") != "none_shadow_only":
        raise ValueError("cohort cannot affect runtime strategy")
    for field in (
        "provider_request_authorized",
        "provider_purchase_authorized",
        "execution_file_present",
        "policy_promotion_eligible",
        "profitability_claim_eligible",
        "feature_threshold_selection_permitted",
        "horizon_selection_permitted",
        "retrospective_labels_allowed_in_runtime",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must remain false")

    claimed = payload.get("content_sha256")
    if claimed != COHORT_CONTENT_SHA256:
        raise ValueError("behavioral-cohort content hash changed")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("behavioral-cohort content fingerprint mismatch")

    parents = payload.get("frozen_parents")
    if not isinstance(parents, Mapping):
        raise ValueError("frozen parents are required")
    if parents.get("behavioral_protocol_content_sha256") != PARENT_PROTOCOL_CONTENT_SHA256:
        raise ValueError("behavioral protocol parent changed")
    if (
        parents.get("historical_account_manifest_content_sha256")
        != HISTORICAL_ACCOUNT_MANIFEST_CONTENT_SHA256
    ):
        raise ValueError("historical account parent changed")
    if parents.get("micro_runtime_artifact_zip_sha256") != MICRO_RUNTIME_ARTIFACT_ZIP_SHA256:
        raise ValueError("Micro runtime artifact changed")

    selection = payload.get("selection_rule")
    if not isinstance(selection, Mapping):
        raise ValueError("selection rule is required")
    for field in (
        "uses_microstructure_feature_values",
        "uses_retrospective_outcomes",
        "uses_ross_actions_or_labels",
        "uses_pnl_or_later_prices",
        "uses_case_sampling_or_favorable_selection",
    ):
        if selection.get(field) is not False:
            raise ValueError(f"selection field {field} must be false")
    if selection.get("include") != (
        "every entry_accepted event in every frozen main-account session"
    ):
        raise ValueError("cohort is no longer exhaustive within its registered slice")

    opportunities = _validate_opportunities(payload)
    summary = payload.get("cohort_summary")
    if not isinstance(summary, Mapping):
        raise ValueError("cohort summary is required")
    expected_summary = {
        "opportunity_count": len(opportunities),
        "starter_count": sum(row["role"] == "starter" for row in opportunities),
        "reentry_count": sum(row["role"] == "reentry" for row in opportunities),
        "trading_date_count": len({row["trading_date"] for row in opportunities}),
        "symbol_count": len({row["symbol"] for row in opportunities}),
        "prospective_quantity_total": sum(
            int(row["prospective_order_quantity"]) for row in opportunities
        ),
    }
    if dict(summary) != expected_summary:
        raise ValueError("cohort summary differs from exact opportunities")
    if expected_summary["prospective_quantity_total"] != EXPECTED_QUANTITY_TOTAL:
        raise ValueError("prospective quantity total changed")

    quantity = payload.get("quantity_contract")
    if not isinstance(quantity, Mapping):
        raise ValueError("quantity contract is required")
    if quantity.get("same_quantity_for_pre_and_post_depth_walks") is not True:
        raise ValueError("pre/post quantities must be identical")
    if quantity.get("same_quantity_for_primary_and_stress_execution_scenarios") is not True:
        raise ValueError("scenario quantities must be identical")
    if quantity.get("quantity_optimization_permitted") is not False:
        raise ValueError("quantity optimization is prohibited")
    if quantity.get("fallback_or_resizing_permitted") is not False:
        raise ValueError("fallback resizing is prohibited")

    _validate_request_surface(payload, opportunities)

    gate = payload.get("future_execution_gate")
    if not isinstance(gate, Mapping):
        raise ValueError("future execution gate is required")
    if gate.get("exact_request_count_authorized_now") != 0:
        raise ValueError("registration cannot authorize a request")
    if gate.get("provider_cost_authorized_now_usd") != "0":
        raise ValueError("registration cannot authorize provider cost")
    if gate.get("provider_bytes_authorized_now") != 0:
        raise ValueError("registration cannot authorize provider bytes")
    if Decimal(str(gate.get("hard_preflight_cost_ceiling_usd"))) != HARD_COST_CEILING_USD:
        raise ValueError("future hard cost ceiling changed")
    if gate.get("hard_preflight_billable_size_ceiling_bytes") != HARD_SIZE_CEILING_BYTES:
        raise ValueError("future hard size ceiling changed")
    if gate.get("all_five_requests_quoted_before_first_timeseries_call") is not True:
        raise ValueError("all quotes must precede any time-series call")
    if gate.get("zero_timeseries_calls_if_either_aggregate_ceiling_exceeded") is not True:
        raise ValueError("preflight must fail closed")
    if gate.get("automatic_retry_authorized") is not False:
        raise ValueError("automatic retry is prohibited")


def load_and_validate_behavioral_cohort(path: Path) -> dict[str, object]:
    payload = _load_json(path)
    validate_behavioral_cohort(payload)
    return payload


def cohort_request_for_opportunity(
    payload: Mapping[str, object], opportunity_id: str
) -> Mapping[str, object]:
    """Return the sole frozen date request covering an exact opportunity."""
    validate_behavioral_cohort(payload)
    rows = payload["opportunities"]
    opportunity = next(
        (row for row in rows if row["opportunity_id"] == opportunity_id),  # type: ignore[index]
        None,
    )
    if opportunity is None:
        raise KeyError(opportunity_id)
    requests = payload["request_surface"]["requests"]  # type: ignore[index]
    matches = [
        request
        for request in requests
        if request["trading_date"] == opportunity["trading_date"]
        and opportunity["symbol"] in request["symbols"]
    ]
    if len(matches) != 1:
        raise ValueError("opportunity does not map to exactly one frozen request")
    return matches[0]
