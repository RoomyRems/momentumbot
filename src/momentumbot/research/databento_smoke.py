from __future__ import annotations

import hashlib
import json
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from momentumbot.research.databento_quote import (
    DATASET,
    REQUIRED_SCHEMAS,
    SDK_VERSION,
    SMOKE_CASES,
    HistoricalClient as QuoteHistoricalClient,
    QuoteRequest,
    build_quote_requests,
    validate_quote_contract,
)
from momentumbot.research.microstructure_contract import canonical_fingerprint


SCHEMA_VERSION = 1
ACQUISITION_CONTRACT_ID = "databento-microstructure-smoke-acquisition-v0.1"
ARTIFACT_TYPE = "sanitized_ephemeral_databento_smoke_acquisition"
ACQUISITION_CONTENT_SHA256 = (
    "d4b38436ef3b5fc08e853b5205c34df930de8abe88ffd36979dcc0e4e166115c"
)
AUTHORIZED_PUSH_PARENT_SHA = "cfe6b00692feea250856afef7a3e1164f178a6e6"
PARENT_LEVEL2_CONTENT_SHA256 = (
    "6d3a41d6bde3844900bc880632d8bc9d6c5f7b787edd5f0c302a709dcb9c1bf1"
)
PARENT_QUOTE_CONTENT_SHA256 = (
    "1c9401e49d500c38715dd61c7f180e3eb868d71b9a28926caa4b399d335f45b1"
)
VERIFIED_QUOTE_REPORT_CONTENT_SHA256 = (
    "67ebcec306b8f930c70ba573cf088468aa827264aedff1d0321957d7067ca256"
)
MAX_PREFLIGHT_COST_USD = Decimal("0.50")
MAX_PREFLIGHT_BILLABLE_SIZE_BYTES = 500_000_000
MIN_REFERENCE_ALIGNMENT_RATIO = Decimal("0.95")
SAMPLE_BUCKET_NS = 60_000_000_000
DOWNLOAD_SCHEMA_ORDER = ("mbp-10", "mbo", "trades", "definition", "status")

Level = tuple[int, int, int]
BookState = tuple[tuple[Level, ...], tuple[Level, ...]]


class TimeseriesAPI(Protocol):
    def get_range(
        self,
        *,
        dataset: str,
        start: str,
        end: str,
        symbols: list[str],
        schema: str,
        stype_in: str,
        path: str,
    ) -> Iterable[object]: ...


class HistoricalClient(QuoteHistoricalClient, Protocol):
    timeseries: TimeseriesAPI


@dataclass(frozen=True, slots=True)
class RuntimeConstants:
    f_last: int
    f_tob: int
    f_snapshot: int
    f_bad_ts_recv: int
    undef_price: int


@dataclass(frozen=True, slots=True)
class Order:
    side: str
    price: int
    size: int


@dataclass(frozen=True, slots=True)
class ReferenceSample:
    publisher_id: int
    instrument_id: int
    sequence: int
    ts_recv: int
    state: BookState


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite non-negative number")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a finite non-negative number") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{field} must be a finite non-negative number")
    return parsed


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer >= {minimum}")
    try:
        parsed = int(value)  # numpy integer fields are common in provider records
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer >= {minimum}") from exc
    if parsed < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return parsed


def _iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _finish_report(report: dict[str, object]) -> dict[str, object]:
    unsigned = {key: value for key, value in report.items() if key != "content_sha256"}
    report["content_sha256"] = canonical_fingerprint(unsigned)
    return report


def validate_acquisition_contract(
    payload: Mapping[str, object],
    *,
    quote_contract: Mapping[str, object] | None = None,
) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported Databento acquisition schema")
    if payload.get("acquisition_contract_id") != ACQUISITION_CONTRACT_ID:
        raise ValueError("unexpected Databento acquisition contract")
    if payload.get("artifact_type") != (
        "preregistered_bounded_ephemeral_databento_acquisition"
    ):
        raise ValueError("unexpected Databento acquisition artifact type")

    claimed = payload.get("content_sha256")
    if claimed != ACQUISITION_CONTENT_SHA256:
        raise ValueError("Databento acquisition content hash changed")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("Databento acquisition content fingerprint mismatch")

    level2 = _mapping(payload.get("parent_level2_contract"), "parent_level2_contract")
    if level2.get("content_sha256") != PARENT_LEVEL2_CONTENT_SHA256:
        raise ValueError("Level 2 parent content hash changed")
    quote = _mapping(payload.get("parent_quote_contract"), "parent_quote_contract")
    if quote.get("content_sha256") != PARENT_QUOTE_CONTENT_SHA256:
        raise ValueError("quote parent content hash changed")
    if quote_contract is not None:
        validate_quote_contract(quote_contract)
        if quote_contract.get("content_sha256") != PARENT_QUOTE_CONTENT_SHA256:
            raise ValueError("loaded quote parent content hash changed")

    verified = _mapping(payload.get("verified_quote"), "verified_quote")
    expected_verified = {
        "workflow_run_id": 32418655472,
        "workflow_run_attempt": 1,
        "artifact_id": 9424913731,
        "quote_report_content_sha256": VERIFIED_QUOTE_REPORT_CONTENT_SHA256,
        "request_count": 20,
        "conservative_total_quoted_cost_usd": "0.207468646765",
        "total_billable_size_bytes": 379772560,
        "g0_quote_passed": True,
        "raw_market_data_persisted": False,
    }
    for field, expected in expected_verified.items():
        if verified.get(field) != expected:
            raise ValueError(f"verified_quote.{field} changed")

    authorization = _mapping(payload.get("authorization"), "authorization")
    expected_authorization = {
        "metadata_requote_authorized": True,
        "historical_timeseries_download_authorized": True,
        "exact_request_count_authorized": 20,
        "authorized_push_parent_sha": AUTHORIZED_PUSH_PARENT_SHA,
        "batch_job_authorized": False,
        "live_subscription_authorized": False,
        "broad_history_download_authorized": False,
        "automatic_retry_authorized": False,
        "broker_or_order_change_authorized": False,
        "reported_new_user_credit_usd": "125",
        "hard_preflight_cost_ceiling_usd": "0.50",
        "hard_preflight_billable_size_ceiling_bytes": 500000000,
    }
    for field, expected in expected_authorization.items():
        if authorization.get(field) != expected:
            raise ValueError(f"authorization.{field} changed")

    provider = _mapping(payload.get("provider"), "provider")
    expected_provider = {
        "provider_id": "databento",
        "dataset": DATASET,
        "venue_scope": "single_venue_nasdaq_not_consolidated_national_depth",
        "sdk_package": "databento",
        "sdk_version": SDK_VERSION,
        "secret_name": "DATABENTO_API_KEY",
    }
    for field, expected in expected_provider.items():
        if provider.get(field) != expected:
            raise ValueError(f"provider.{field} changed")

    surface = _mapping(payload.get("request_surface"), "request_surface")
    observed_cases = tuple(
        (
            str(_mapping(item, "smoke case").get("trading_date")),
            str(_mapping(item, "smoke case").get("symbol")),
        )
        for item in surface.get("smoke_cases", [])
    )
    if observed_cases != SMOKE_CASES:
        raise ValueError("smoke cases changed")
    if surface.get("schemas") != list(REQUIRED_SCHEMAS):
        raise ValueError("required schemas changed")
    if surface.get("allowed_calls") != [
        "historical.metadata.get_billable_size",
        "historical.metadata.get_cost",
        "historical.timeseries.get_range",
    ]:
        raise ValueError("allowed provider call surface changed")
    if surface.get("prohibited_calls") != [
        "historical.batch.submit_job",
        "historical.batch.download",
        "live.subscribe",
    ]:
        raise ValueError("prohibited provider call surface changed")

    storage = _mapping(payload.get("storage_and_licensing"), "storage_and_licensing")
    if storage.get("public_repository_raw_data") is not False:
        raise ValueError("public raw-data repository policy changed")
    if storage.get("github_artifact_raw_data") is not False:
        raise ValueError("raw-data artifact policy changed")


def load_acquisition_contract(
    path: str | Path,
    *,
    quote_contract: Mapping[str, object],
) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Databento acquisition contract root must be an object")
    validate_acquisition_contract(payload, quote_contract=quote_contract)
    return payload


def _request_kwargs(request: QuoteRequest) -> dict[str, object]:
    return {
        "dataset": request.dataset,
        "start": request.start,
        "end": request.end,
        "symbols": [request.symbol],
        "schema": request.schema,
        "stype_in": request.stype_in,
    }


def _run_preflight(
    client: HistoricalClient,
    requests: tuple[QuoteRequest, ...],
) -> tuple[dict[str, object], list[dict[str, str]]]:
    rows: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    total_cost = Decimal("0")
    total_size = 0
    for request in requests:
        kwargs = _request_kwargs(request)
        stage = f"preflight:{request.trading_date}:{request.symbol}:{request.schema}"
        try:
            raw_size = client.metadata.get_billable_size(**kwargs)
            raw_cost = client.metadata.get_cost(**kwargs)
            size = _integer(raw_size, "billable size")
            cost = _decimal(raw_cost, "quoted cost")
        except Exception as exc:
            errors.append({"stage": stage, "error_kind": type(exc).__name__})
            break
        total_size += size
        total_cost += cost
        row: dict[str, object] = request.mapping()
        row.update(
            {
                "billable_size_bytes": size,
                "quoted_cost_usd": format(cost, "f"),
            }
        )
        rows.append(row)

    complete = len(rows) == len(requests) == 20 and not errors
    within_cost = complete and total_cost <= MAX_PREFLIGHT_COST_USD
    within_size = complete and total_size <= MAX_PREFLIGHT_BILLABLE_SIZE_BYTES
    passed = complete and within_cost and within_size
    return (
        {
            "request_count_expected": 20,
            "request_count_quoted": len(rows),
            "quote_rows": rows,
            "total_quoted_cost_usd": format(total_cost, "f") if complete else None,
            "total_billable_size_bytes": total_size if complete else None,
            "hard_cost_ceiling_usd": format(MAX_PREFLIGHT_COST_USD, "f"),
            "hard_billable_size_ceiling_bytes": MAX_PREFLIGHT_BILLABLE_SIZE_BYTES,
            "all_twenty_quotes_complete": complete,
            "cost_within_ceiling": within_cost,
            "billable_size_within_ceiling": within_size,
            "preflight_passed": passed,
        },
        errors,
    )


def _char(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("ascii")
    enum_value = getattr(value, "value", value)
    if isinstance(enum_value, bytes):
        return enum_value.decode("ascii")
    return str(enum_value)


def _metadata_value(metadata: object, field: str) -> str | None:
    value = getattr(metadata, field, None)
    if value is None and isinstance(metadata, Mapping):
        value = metadata.get(field)
    if value is None:
        return None
    value = getattr(value, "value", value)
    return str(value).lower().replace("_", "-")


def _record_int(record: object, field: str) -> int:
    return _integer(getattr(record, field), field)


def _has_fields(record: object, fields: tuple[str, ...]) -> bool:
    return all(hasattr(record, field) for field in fields)


def _unflagged_time_inversion(record: object, flags: int, runtime: RuntimeConstants) -> bool:
    if not hasattr(record, "ts_recv") or not hasattr(record, "ts_event"):
        return False
    return (
        _record_int(record, "ts_recv") < _record_int(record, "ts_event")
        and not flags & runtime.f_bad_ts_recv
    )


def _state_is_crossed(state: BookState, undef_price: int) -> bool:
    bids, asks = state
    best_bid = bids[0][0]
    best_ask = asks[0][0]
    return (
        best_bid != undef_price
        and best_ask != undef_price
        and best_bid >= best_ask
    )


def _state_component_matches(left: BookState, right: BookState) -> tuple[bool, bool, bool]:
    left_levels = left[0] + left[1]
    right_levels = right[0] + right[1]
    return (
        all(a[0] == b[0] for a, b in zip(left_levels, right_levels, strict=True)),
        all(a[1] == b[1] for a, b in zip(left_levels, right_levels, strict=True)),
        all(a[2] == b[2] for a, b in zip(left_levels, right_levels, strict=True)),
    )


class IncrementalBook:
    def __init__(self) -> None:
        self.orders: dict[int, Order] = {}
        self.levels: dict[str, dict[int, list[int]]] = {"B": {}, "A": {}}

    def _remove(self, order_id: int) -> list[str]:
        issues: list[str] = []
        order = self.orders.pop(order_id)
        level = self.levels[order.side].get(order.price)
        if level is None:
            return ["level_underflow"]
        level[0] -= order.size
        level[1] -= 1
        if level[0] < 0 or level[1] < 0:
            issues.append("level_underflow")
        if level[0] <= 0 or level[1] <= 0:
            self.levels[order.side].pop(order.price, None)
        return issues

    def _insert(self, order_id: int, order: Order) -> None:
        self.orders[order_id] = order
        level = self.levels[order.side].setdefault(order.price, [0, 0])
        level[0] += order.size
        level[1] += 1

    def _clear_side(self, side: str) -> None:
        self.orders = {
            order_id: order
            for order_id, order in self.orders.items()
            if order.side != side
        }
        self.levels[side].clear()

    def apply(
        self,
        *,
        action: str,
        side: str,
        order_id: int,
        price: int,
        size: int,
        flags: int,
        runtime: RuntimeConstants,
    ) -> list[str]:
        issues: list[str] = []
        if action in {"T", "F", "N"}:
            return issues
        if action == "R":
            self.orders.clear()
            self.levels["B"].clear()
            self.levels["A"].clear()
            return issues
        if action not in {"A", "C", "M"}:
            return ["invalid_action"]
        if side not in {"A", "B"}:
            return ["invalid_side"]

        if flags & runtime.f_tob:
            if action != "A":
                issues.append("invalid_action")
            self._clear_side(side)
            if price == runtime.undef_price:
                return issues
            if size <= 0:
                issues.append("invalid_size")
                return issues
            if order_id <= 0:
                issues.append("invalid_order_id")
                return issues
            self._insert(order_id, Order(side, price, size))
            return issues

        if price == runtime.undef_price or price <= 0:
            return ["invalid_price"]
        if order_id <= 0:
            return ["invalid_order_id"]

        if action == "A":
            if size <= 0:
                return ["invalid_size"]
            if order_id in self.orders:
                issues.append("duplicate_add")
                issues.extend(self._remove(order_id))
            self._insert(order_id, Order(side, price, size))
            return issues

        existing = self.orders.get(order_id)
        if action == "C":
            if size <= 0:
                return ["invalid_size"]
            if existing is None:
                return ["orphan_cancel"]
            if existing.side != side or existing.price != price:
                issues.append("cancel_identity_mismatch")
            if size > existing.size:
                issues.append("cancel_exceeds_resting_size")
                issues.extend(self._remove(order_id))
                return issues
            level = self.levels[existing.side][existing.price]
            level[0] -= size
            remaining = existing.size - size
            if remaining == 0:
                self.orders.pop(order_id)
                level[1] -= 1
                if level[1] == 0:
                    self.levels[existing.side].pop(existing.price)
            else:
                self.orders[order_id] = Order(existing.side, existing.price, remaining)
            return issues

        if existing is None:
            issues.append("missing_modify")
            if size > 0:
                self._insert(order_id, Order(side, price, size))
            return issues
        if existing.side != side:
            issues.append("modify_identity_mismatch")
        issues.extend(self._remove(order_id))
        if size > 0:
            self._insert(order_id, Order(side, price, size))
        return issues

    def top_ten(self, undef_price: int) -> BookState:
        bids = sorted(self.levels["B"], reverse=True)[:10]
        asks = sorted(self.levels["A"])[:10]

        def render(side: str, prices: list[int]) -> tuple[Level, ...]:
            values = [
                (price, self.levels[side][price][0], self.levels[side][price][1])
                for price in prices
            ]
            values.extend([(undef_price, 0, 0)] * (10 - len(values)))
            return tuple(values)

        return render("B", bids), render("A", asks)


class IndependentOrderMap:
    """A deliberately separate order-only implementation used as a replay check."""

    def __init__(self) -> None:
        self.orders: dict[int, Order] = {}

    def apply(
        self,
        *,
        action: str,
        side: str,
        order_id: int,
        price: int,
        size: int,
        flags: int,
        runtime: RuntimeConstants,
    ) -> list[str]:
        issues: list[str] = []
        if action in {"T", "F", "N"}:
            return issues
        if action == "R":
            self.orders.clear()
            return issues
        if action not in {"A", "C", "M"}:
            return ["invalid_action"]
        if side not in {"A", "B"}:
            return ["invalid_side"]

        if flags & runtime.f_tob:
            if action != "A":
                issues.append("invalid_action")
            self.orders = {
                key: order for key, order in self.orders.items() if order.side != side
            }
            if price == runtime.undef_price:
                return issues
            if size <= 0:
                issues.append("invalid_size")
                return issues
            if order_id <= 0:
                issues.append("invalid_order_id")
                return issues
            self.orders[order_id] = Order(side, price, size)
            return issues

        if price == runtime.undef_price or price <= 0:
            return ["invalid_price"]
        if order_id <= 0:
            return ["invalid_order_id"]

        if action == "A":
            if size <= 0:
                return ["invalid_size"]
            if order_id in self.orders:
                issues.append("duplicate_add")
            self.orders[order_id] = Order(side, price, size)
            return issues

        existing = self.orders.get(order_id)
        if action == "C":
            if size <= 0:
                return ["invalid_size"]
            if existing is None:
                return ["orphan_cancel"]
            if existing.side != side or existing.price != price:
                issues.append("cancel_identity_mismatch")
            if size > existing.size:
                issues.append("cancel_exceeds_resting_size")
                self.orders.pop(order_id)
            elif size == existing.size:
                self.orders.pop(order_id)
            else:
                self.orders[order_id] = Order(
                    existing.side,
                    existing.price,
                    existing.size - size,
                )
            return issues

        if existing is None:
            issues.append("missing_modify")
        elif existing.side != side:
            issues.append("modify_identity_mismatch")
        if size == 0:
            self.orders.pop(order_id, None)
        else:
            self.orders[order_id] = Order(side, price, size)
        return issues

    def top_ten(self, undef_price: int) -> BookState:
        levels: dict[str, dict[int, list[int]]] = {
            "B": defaultdict(lambda: [0, 0]),
            "A": defaultdict(lambda: [0, 0]),
        }
        for order in self.orders.values():
            level = levels[order.side][order.price]
            level[0] += order.size
            level[1] += 1
        bids = sorted(levels["B"], reverse=True)[:10]
        asks = sorted(levels["A"])[:10]

        def render(side: str, prices: list[int]) -> tuple[Level, ...]:
            values = [
                (price, levels[side][price][0], levels[side][price][1])
                for price in prices
            ]
            values.extend([(undef_price, 0, 0)] * (10 - len(values)))
            return tuple(values)

        return render("B", bids), render("A", asks)


def _mbp_state(record: object, runtime: RuntimeConstants) -> BookState:
    levels = getattr(record, "levels")
    values = list(levels)
    if len(values) < 10:
        raise ValueError("MBP-10 record contained fewer than ten levels")

    def side_values(prefix: str) -> tuple[Level, ...]:
        rendered: list[Level] = []
        for level in values[:10]:
            rendered.append(
                (
                    _integer(getattr(level, f"{prefix}_px"), f"{prefix}_px"),
                    _integer(getattr(level, f"{prefix}_sz"), f"{prefix}_sz"),
                    _integer(getattr(level, f"{prefix}_ct"), f"{prefix}_ct"),
                )
            )
        return tuple(rendered)

    state = side_values("bid"), side_values("ask")
    for side in state:
        for price, size, count in side:
            if price == runtime.undef_price and (size != 0 or count != 0):
                raise ValueError("undefined MBP-10 level carried size or count")
    return state


def _process_mbp10(
    store: Iterable[object],
    runtime: RuntimeConstants,
) -> tuple[dict[str, object], dict[tuple[int, int, int], ReferenceSample]]:
    required = (
        "ts_recv",
        "ts_event",
        "publisher_id",
        "instrument_id",
        "sequence",
        "flags",
        "levels",
    )
    record_count = 0
    fields_observed = True
    inversions = 0
    receive_reversals = 0
    last_receive: dict[tuple[int, int], int] = {}
    bucket_samples: dict[tuple[int, int, int], ReferenceSample] = {}
    for record in store:
        record_count += 1
        if not _has_fields(record, required):
            fields_observed = False
            continue
        flags = _record_int(record, "flags")
        if _unflagged_time_inversion(record, flags, runtime):
            inversions += 1
        publisher_id = _record_int(record, "publisher_id")
        instrument_id = _record_int(record, "instrument_id")
        ts_recv = _record_int(record, "ts_recv")
        key = (publisher_id, instrument_id)
        if key in last_receive and ts_recv < last_receive[key]:
            receive_reversals += 1
        last_receive[key] = ts_recv
        sample = ReferenceSample(
            publisher_id=publisher_id,
            instrument_id=instrument_id,
            sequence=_record_int(record, "sequence"),
            ts_recv=ts_recv,
            state=_mbp_state(record, runtime),
        )
        bucket_samples[(publisher_id, instrument_id, ts_recv // SAMPLE_BUCKET_NS)] = sample

    samples: dict[tuple[int, int, int], ReferenceSample] = {}
    collisions = 0
    valid_two_sided = 0
    crossed = 0
    for sample in bucket_samples.values():
        key = (sample.publisher_id, sample.instrument_id, sample.sequence)
        if key in samples:
            collisions += 1
        samples[key] = sample
        bids, asks = sample.state
        if bids[0][0] != runtime.undef_price and asks[0][0] != runtime.undef_price:
            valid_two_sided += 1
        if _state_is_crossed(sample.state, runtime.undef_price):
            crossed += 1

    return (
        {
            "record_count": record_count,
            "required_fields_observed": fields_observed and record_count > 0,
            "reference_sample_count": len(samples),
            "reference_key_collision_count": collisions,
            "valid_two_sided_sample_count": valid_two_sided,
            "crossed_reference_sample_count": crossed,
            "unflagged_timestamp_inversion_count": inversions,
            "receive_timestamp_reversal_count": receive_reversals,
        },
        samples,
    )


def _digest_state(
    digest: Any,
    publisher_id: int,
    instrument_id: int,
    sequence: int,
    state: BookState,
) -> None:
    encoded = json.dumps(
        [publisher_id, instrument_id, sequence, state],
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    digest.update(len(encoded).to_bytes(8, "big"))
    digest.update(encoded)


def _process_mbo(
    store: Iterable[object],
    runtime: RuntimeConstants,
    references: Mapping[tuple[int, int, int], ReferenceSample],
) -> dict[str, object]:
    required = (
        "ts_recv",
        "ts_event",
        "publisher_id",
        "instrument_id",
        "channel_id",
        "sequence",
        "action",
        "side",
        "price",
        "size",
        "order_id",
        "flags",
    )
    record_count = 0
    fields_observed = True
    action_counts: Counter[str] = Counter()
    issue_counts: Counter[str] = Counter()
    unflagged_inversions = 0
    receive_reversals = 0
    sequence_reversals = 0
    sequence_gaps = 0
    last_receive: dict[tuple[int, int], int] = {}
    last_sequence: dict[tuple[int, int], int] = {}
    incremental: dict[tuple[int, int], IncrementalBook] = {}
    independent: dict[tuple[int, int], IndependentOrderMap] = {}
    snapshot_clear_seen: set[tuple[int, int]] = set()
    ready: set[tuple[int, int]] = set()
    matched_reference_keys: set[tuple[int, int, int]] = set()
    aligned = 0
    independent_matches = 0
    reference_exact_matches = 0
    price_matches = 0
    size_matches = 0
    count_matches = 0
    crossed_samples = 0
    top_of_book_events = 0
    zero_size_modifies = 0
    incremental_digest = hashlib.sha256()
    independent_digest = hashlib.sha256()
    reference_digest = hashlib.sha256()

    for record in store:
        record_count += 1
        if not _has_fields(record, required):
            fields_observed = False
            continue
        flags = _record_int(record, "flags")
        publisher_id = _record_int(record, "publisher_id")
        instrument_id = _record_int(record, "instrument_id")
        channel_id = _record_int(record, "channel_id")
        sequence = _record_int(record, "sequence")
        ts_recv = _record_int(record, "ts_recv")
        action = _char(getattr(record, "action"))
        side = _char(getattr(record, "side"))
        price = int(getattr(record, "price"))
        size = _record_int(record, "size")
        order_id = _record_int(record, "order_id")
        action_counts[action if action in {"A", "C", "M", "R", "T", "F", "N"} else "unknown"] += 1

        channel_key = (publisher_id, channel_id)
        if _unflagged_time_inversion(record, flags, runtime):
            unflagged_inversions += 1
        if channel_key in last_receive and ts_recv < last_receive[channel_key]:
            if not flags & runtime.f_bad_ts_recv:
                receive_reversals += 1
        last_receive[channel_key] = ts_recv
        if sequence > 0:
            previous = last_sequence.get(channel_key)
            if previous is not None and sequence < previous:
                sequence_reversals += 1
            elif previous is not None and sequence > previous + 1:
                sequence_gaps += 1
            last_sequence[channel_key] = sequence

        book_key = (publisher_id, instrument_id)
        first = incremental.setdefault(book_key, IncrementalBook())
        second = independent.setdefault(book_key, IndependentOrderMap())
        kwargs = {
            "action": action,
            "side": side,
            "order_id": order_id,
            "price": price,
            "size": size,
            "flags": flags,
            "runtime": runtime,
        }
        first_issues = first.apply(**kwargs)
        second_issues = second.apply(**kwargs)
        issue_counts.update(first_issues)
        if sorted(first_issues) != sorted(second_issues):
            issue_counts["independent_apply_issue_mismatch"] += 1
        if flags & runtime.f_tob:
            top_of_book_events += 1
        if action == "M" and size == 0:
            zero_size_modifies += 1
        if action == "R" and flags & runtime.f_snapshot:
            snapshot_clear_seen.add(book_key)
        if (
            book_key in snapshot_clear_seen
            and not flags & runtime.f_snapshot
            and flags & runtime.f_last
        ):
            ready.add(book_key)

        reference_key = (publisher_id, instrument_id, sequence)
        if (
            flags & runtime.f_last
            and book_key in ready
            and reference_key in references
            and reference_key not in matched_reference_keys
        ):
            matched_reference_keys.add(reference_key)
            aligned += 1
            first_state = first.top_ten(runtime.undef_price)
            second_state = second.top_ten(runtime.undef_price)
            reference_state = references[reference_key].state
            if first_state == second_state:
                independent_matches += 1
            if first_state == reference_state:
                reference_exact_matches += 1
            price_match, size_match, count_match = _state_component_matches(
                first_state,
                reference_state,
            )
            price_matches += int(price_match)
            size_matches += int(size_match)
            count_matches += int(count_match)
            crossed_samples += int(_state_is_crossed(first_state, runtime.undef_price))
            _digest_state(
                incremental_digest,
                publisher_id,
                instrument_id,
                sequence,
                first_state,
            )
            _digest_state(
                independent_digest,
                publisher_id,
                instrument_id,
                sequence,
                second_state,
            )
            _digest_state(
                reference_digest,
                publisher_id,
                instrument_id,
                sequence,
                reference_state,
            )

    reference_count = len(references)
    coverage = Decimal(aligned) / Decimal(reference_count) if reference_count else Decimal("0")
    return {
        "record_count": record_count,
        "required_fields_observed": fields_observed and record_count > 0,
        "book_count": len(incremental),
        "synthetic_snapshot_clear_count": len(snapshot_clear_seen),
        "ready_book_count": len(ready),
        "action_counts": {
            key: action_counts.get(key, 0)
            for key in ("A", "C", "M", "R", "T", "F", "N", "unknown")
        },
        "issue_counts": {
            key: issue_counts.get(key, 0)
            for key in (
                "duplicate_add",
                "orphan_cancel",
                "cancel_identity_mismatch",
                "cancel_exceeds_resting_size",
                "missing_modify",
                "modify_identity_mismatch",
                "invalid_action",
                "invalid_side",
                "invalid_size",
                "invalid_price",
                "invalid_order_id",
                "level_underflow",
                "independent_apply_issue_mismatch",
            )
        },
        "top_of_book_event_count": top_of_book_events,
        "zero_size_modify_count": zero_size_modifies,
        "unflagged_timestamp_inversion_count": unflagged_inversions,
        "receive_timestamp_reversal_count": receive_reversals,
        "sequence_reversal_count": sequence_reversals,
        "symbol_filtered_forward_sequence_gap_count": sequence_gaps,
        "comparison_metrics": {
            "reference_sample_count": reference_count,
            "aligned_sample_count": aligned,
            "reference_alignment_ratio": format(coverage, "f"),
            "independent_replay_exact_match_count": independent_matches,
            "mbp10_exact_match_count": reference_exact_matches,
            "mbp10_price_match_count": price_matches,
            "mbp10_size_match_count": size_matches,
            "mbp10_order_count_match_count": count_matches,
            "crossed_reconstructed_sample_count": crossed_samples,
            "incremental_replay_digest_sha256": incremental_digest.hexdigest(),
            "independent_replay_digest_sha256": independent_digest.hexdigest(),
            "mbp10_reference_digest_sha256": reference_digest.hexdigest(),
        },
    }


def _process_simple_schema(
    store: Iterable[object],
    *,
    schema: str,
    runtime: RuntimeConstants,
) -> dict[str, object]:
    required = {
        "trades": (
            "ts_recv",
            "ts_event",
            "publisher_id",
            "instrument_id",
            "sequence",
            "action",
            "side",
            "price",
            "size",
        ),
        "definition": ("ts_event", "publisher_id", "instrument_id"),
        "status": ("ts_event", "publisher_id", "instrument_id"),
    }[schema]
    record_count = 0
    fields_observed = True
    inversions = 0
    for record in store:
        record_count += 1
        if not _has_fields(record, required):
            fields_observed = False
            continue
        flags = int(getattr(record, "flags", 0))
        inversions += int(_unflagged_time_inversion(record, flags, runtime))
    return {
        "record_count": record_count,
        "required_fields_observed": fields_observed and (
            record_count > 0 or schema == "status"
        ),
        "unflagged_timestamp_inversion_count": inversions,
    }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_and_process(
    client: HistoricalClient,
    request: QuoteRequest,
    path: Path,
    runtime: RuntimeConstants,
    references: Mapping[tuple[int, int, int], ReferenceSample] | None,
) -> tuple[dict[str, object], dict[tuple[int, int, int], ReferenceSample] | None]:
    store = client.timeseries.get_range(path=str(path), **_request_kwargs(request))
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError("Databento DBN file was not created or was empty")
    metadata = getattr(store, "metadata", None)
    dataset_matches = _metadata_value(metadata, "dataset") == DATASET.lower()
    schema_matches = _metadata_value(metadata, "schema") == request.schema

    if request.schema == "mbp-10":
        metrics, samples = _process_mbp10(store, runtime)
    elif request.schema == "mbo":
        if references is None:
            raise ValueError("MBO processing requires ephemeral MBP-10 references")
        metrics = _process_mbo(store, runtime, references)
        samples = None
    else:
        metrics = _process_simple_schema(store, schema=request.schema, runtime=runtime)
        samples = None

    row: dict[str, object] = request.mapping()
    row.update(
        {
            "compressed_file_size_bytes": path.stat().st_size,
            "ephemeral_file_sha256": _file_sha256(path),
            "dataset_metadata_matches": dataset_matches,
            "schema_metadata_matches": schema_matches,
            "metrics": metrics,
        }
    )
    return row, samples


def _case_gate(case: Mapping[str, object]) -> tuple[bool, bool, dict[str, bool]]:
    downloads = case.get("downloads")
    rows = downloads if isinstance(downloads, list) else []
    by_schema = {
        str(row.get("schema")): row
        for row in rows
        if isinstance(row, Mapping)
    }
    required_records = {"mbo", "mbp-10", "trades", "definition"}
    all_schemas = set(by_schema) == set(REQUIRED_SCHEMAS)
    metadata_matches = all(
        row.get("dataset_metadata_matches") is True
        and row.get("schema_metadata_matches") is True
        for row in by_schema.values()
    )
    fields_observed = all(
        _mapping(row.get("metrics"), "download metrics").get(
            "required_fields_observed"
        )
        is True
        for row in by_schema.values()
    ) if all_schemas else False
    required_nonempty = all(
        int(
            _mapping(by_schema[schema].get("metrics"), "download metrics").get(
                "record_count", 0
            )
        )
        > 0
        for schema in required_records
        if schema in by_schema
    ) and required_records.issubset(by_schema)
    mbo_metrics = (
        _mapping(by_schema["mbo"].get("metrics"), "MBO metrics")
        if "mbo" in by_schema
        else {}
    )
    snapshot_seen = int(mbo_metrics.get("synthetic_snapshot_clear_count", 0)) > 0
    g1_conditions = {
        "all_five_exact_schemas_downloaded": all_schemas,
        "dataset_and_schema_metadata_match": metadata_matches,
        "required_fields_observed": fields_observed,
        "required_event_schemas_nonempty": required_nonempty,
        "synthetic_snapshot_clear_observed": snapshot_seen,
    }
    g1 = all(g1_conditions.values())

    comparison = _mapping(mbo_metrics.get("comparison_metrics", {}), "comparison metrics")
    aligned = int(comparison.get("aligned_sample_count", 0))
    reference_count = int(comparison.get("reference_sample_count", 0))
    ratio = _decimal(comparison.get("reference_alignment_ratio", "0"), "alignment ratio")
    issue_counts = _mapping(mbo_metrics.get("issue_counts", {}), "issue counts")
    no_issues = all(int(value) == 0 for value in issue_counts.values())
    mbp_metrics = (
        _mapping(by_schema["mbp-10"].get("metrics"), "MBP-10 metrics")
        if "mbp-10" in by_schema
        else {}
    )
    g2_conditions = {
        "aligned_sample_exists": aligned > 0,
        "reference_alignment_at_least_95_percent": (
            reference_count > 0 and ratio >= MIN_REFERENCE_ALIGNMENT_RATIO
        ),
        "independent_replays_match_every_aligned_sample": (
            int(comparison.get("independent_replay_exact_match_count", -1)) == aligned
        ),
        "mbp10_exactly_matches_every_aligned_sample": (
            int(comparison.get("mbp10_exact_match_count", -1)) == aligned
        ),
        "mbp10_prices_match_every_aligned_sample": (
            int(comparison.get("mbp10_price_match_count", -1)) == aligned
        ),
        "mbp10_sizes_match_every_aligned_sample": (
            int(comparison.get("mbp10_size_match_count", -1)) == aligned
        ),
        "mbp10_order_counts_match_every_aligned_sample": (
            int(comparison.get("mbp10_order_count_match_count", -1)) == aligned
        ),
        "replay_digests_match": (
            comparison.get("incremental_replay_digest_sha256")
            == comparison.get("independent_replay_digest_sha256")
            == comparison.get("mbp10_reference_digest_sha256")
        ),
        "no_book_mutation_issue": no_issues,
        "no_unflagged_timestamp_inversion": (
            int(mbo_metrics.get("unflagged_timestamp_inversion_count", -1)) == 0
            and int(mbp_metrics.get("unflagged_timestamp_inversion_count", -1)) == 0
        ),
        "no_receive_timestamp_reversal": (
            int(mbo_metrics.get("receive_timestamp_reversal_count", -1)) == 0
            and int(mbp_metrics.get("receive_timestamp_reversal_count", -1)) == 0
        ),
        "no_sequence_reversal": int(mbo_metrics.get("sequence_reversal_count", -1)) == 0,
        "no_crossed_sampled_book": (
            int(comparison.get("crossed_reconstructed_sample_count", -1)) == 0
            and int(mbp_metrics.get("crossed_reference_sample_count", -1)) == 0
        ),
        "no_reference_key_collision": (
            int(mbp_metrics.get("reference_key_collision_count", -1)) == 0
        ),
    }
    g2 = g1 and all(g2_conditions.values())
    return g1, g2, {**g1_conditions, **g2_conditions}


def _base_report(
    *,
    generated_at: datetime,
    sdk_version: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "acquisition_contract_id": ACQUISITION_CONTRACT_ID,
        "acquisition_contract_content_sha256": ACQUISITION_CONTENT_SHA256,
        "artifact_type": ARTIFACT_TYPE,
        "generated_at": _iso_z(generated_at),
        "parent_level2_content_sha256": PARENT_LEVEL2_CONTENT_SHA256,
        "parent_quote_content_sha256": PARENT_QUOTE_CONTENT_SHA256,
        "verified_quote_report_content_sha256": VERIFIED_QUOTE_REPORT_CONTENT_SHA256,
        "provider": "databento",
        "dataset": DATASET,
        "venue_scope": "single_venue_nasdaq_not_consolidated_national_depth",
        "sdk_version": sdk_version,
        "provider_credential_persisted": False,
        "raw_market_data_persisted": False,
        "raw_market_data_uploaded": False,
        "batch_or_live_endpoint_called": False,
        "automatic_retry_attempted": False,
        "broker_or_order_change_made": False,
        "strategy_or_threshold_change_made": False,
        "actual_billing_known": False,
        "billing_note": (
            "Preflight quotes are not represented as actual billed charges; "
            "completed downloads may be billable."
        ),
    }


def build_unavailable_report(
    contract: Mapping[str, object],
    quote_contract: Mapping[str, object],
    *,
    generated_at: datetime,
    sdk_version: str,
    error_stage: str,
    error_kind: str,
) -> dict[str, object]:
    validate_acquisition_contract(contract, quote_contract=quote_contract)
    report = _base_report(generated_at=generated_at, sdk_version=sdk_version)
    report.update(
        {
            "preflight": {
                "request_count_expected": 20,
                "request_count_quoted": 0,
                "quote_rows": [],
                "total_quoted_cost_usd": None,
                "total_billable_size_bytes": None,
                "hard_cost_ceiling_usd": format(MAX_PREFLIGHT_COST_USD, "f"),
                "hard_billable_size_ceiling_bytes": MAX_PREFLIGHT_BILLABLE_SIZE_BYTES,
                "all_twenty_quotes_complete": False,
                "cost_within_ceiling": False,
                "billable_size_within_ceiling": False,
                "preflight_passed": False,
            },
            "timeseries_request_count": 0,
            "downloads": [],
            "cases": [],
            "errors": [{"stage": error_stage, "error_kind": error_kind}],
            "raw_temp_directory_empty_before_cleanup": True,
            "raw_temp_directory_removed": True,
            "g1_schema_and_integrity_passed": False,
            "g2_reconstruction_passed": False,
            "smoke_acquisition_passed": False,
            "runtime_authority_created": False,
        }
    )
    return _finish_report(report)


def run_smoke_acquisition(
    contract: Mapping[str, object],
    quote_contract: Mapping[str, object],
    client: HistoricalClient,
    *,
    generated_at: datetime,
    sdk_version: str,
    runtime: RuntimeConstants,
) -> dict[str, object]:
    validate_acquisition_contract(contract, quote_contract=quote_contract)
    if sdk_version != SDK_VERSION:
        raise ValueError(f"Databento SDK version must be {SDK_VERSION}")
    requests = build_quote_requests(quote_contract)
    preflight, errors = _run_preflight(client, requests)
    report = _base_report(generated_at=generated_at, sdk_version=sdk_version)
    report["preflight"] = preflight
    report["timeseries_request_count"] = 0
    report["downloads"] = []
    report["cases"] = []
    report["errors"] = errors
    report["raw_temp_directory_empty_before_cleanup"] = True
    report["raw_temp_directory_removed"] = True

    if preflight.get("preflight_passed") is not True:
        report.update(
            {
                "g1_schema_and_integrity_passed": False,
                "g2_reconstruction_passed": False,
                "smoke_acquisition_passed": False,
                "runtime_authority_created": False,
            }
        )
        return _finish_report(report)

    request_lookup = {
        (request.trading_date, request.symbol, request.schema): request
        for request in requests
    }
    temp = tempfile.TemporaryDirectory(prefix="momentumbot-databento-")
    temp_path = Path(temp.name)
    halted = False
    try:
        for trading_date, symbol in SMOKE_CASES:
            case_downloads: list[dict[str, object]] = []
            references: dict[tuple[int, int, int], ReferenceSample] | None = None
            for schema in DOWNLOAD_SCHEMA_ORDER:
                request = request_lookup[(trading_date, symbol, schema)]
                raw_path = temp_path / f"request-{len(report['downloads']):02d}.dbn.zst"
                stage = f"download_or_parse:{trading_date}:{symbol}:{schema}"
                try:
                    report["timeseries_request_count"] = int(
                        report["timeseries_request_count"]
                    ) + 1
                    row, new_references = _download_and_process(
                        client,
                        request,
                        raw_path,
                        runtime,
                        references,
                    )
                    if new_references is not None:
                        references = new_references
                    case_downloads.append(row)
                    report["downloads"].append(row)
                except Exception as exc:
                    errors.append({"stage": stage, "error_kind": type(exc).__name__})
                    halted = True
                    break
                finally:
                    raw_path.unlink(missing_ok=True)
            case: dict[str, object] = {
                "trading_date": trading_date,
                "symbol": symbol,
                "downloads": case_downloads,
            }
            g1, g2, conditions = _case_gate(case)
            case.update(
                {
                    "gate_conditions": conditions,
                    "g1_schema_and_integrity_passed": g1,
                    "g2_reconstruction_passed": g2,
                }
            )
            report["cases"].append(case)
            references = None
            if halted:
                break
    finally:
        report["raw_temp_directory_empty_before_cleanup"] = not any(
            temp_path.iterdir()
        )
        temp_name = temp.name
        temp.cleanup()
        report["raw_temp_directory_removed"] = not Path(temp_name).exists()

    cases = report["cases"] if isinstance(report["cases"], list) else []
    complete_cases = len(cases) == len(SMOKE_CASES)
    g1 = (
        complete_cases
        and not errors
        and len(report["downloads"]) == 20
        and all(
            isinstance(case, Mapping)
            and case.get("g1_schema_and_integrity_passed") is True
            for case in cases
        )
        and report["raw_temp_directory_empty_before_cleanup"] is True
        and report["raw_temp_directory_removed"] is True
    )
    g2 = g1 and all(
        isinstance(case, Mapping) and case.get("g2_reconstruction_passed") is True
        for case in cases
    )
    report.update(
        {
            "g1_schema_and_integrity_passed": g1,
            "g2_reconstruction_passed": g2,
            "smoke_acquisition_passed": g1 and g2,
            "runtime_authority_created": False,
        }
    )
    return _finish_report(report)


def _walk_keys(value: object) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def validate_smoke_report(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported Databento smoke report schema")
    if payload.get("acquisition_contract_id") != ACQUISITION_CONTRACT_ID:
        raise ValueError("unexpected Databento smoke report contract")
    if payload.get("acquisition_contract_content_sha256") != ACQUISITION_CONTENT_SHA256:
        raise ValueError("smoke report acquisition binding changed")
    if payload.get("artifact_type") != ARTIFACT_TYPE:
        raise ValueError("unexpected Databento smoke report artifact type")
    for field in (
        "provider_credential_persisted",
        "raw_market_data_persisted",
        "raw_market_data_uploaded",
        "batch_or_live_endpoint_called",
        "automatic_retry_attempted",
        "broker_or_order_change_made",
        "strategy_or_threshold_change_made",
        "actual_billing_known",
        "runtime_authority_created",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must remain false")
    if payload.get("raw_temp_directory_empty_before_cleanup") is not True:
        raise ValueError("raw temporary directory was not empty before cleanup")
    if payload.get("raw_temp_directory_removed") is not True:
        raise ValueError("raw temporary directory was not removed")
    if int(payload.get("timeseries_request_count", 0)) > 20:
        raise ValueError("timeseries request count exceeded authorization")
    forbidden_keys = {
        "raw_records",
        "record_values",
        "order_id",
        "instrument_id",
        "price",
        "size",
        "levels",
        "temporary_path",
        "provider_error_message",
        "exception_message",
    }
    observed = set(_walk_keys(payload))
    if observed & forbidden_keys:
        raise ValueError("sanitized smoke report contains a prohibited field")
    for row in payload.get("downloads", []):
        if not isinstance(row, Mapping):
            raise ValueError("download summary must be an object")
        digest = row.get("ephemeral_file_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("download summary file hash is invalid")
    claimed = payload.get("content_sha256")
    if not isinstance(claimed, str) or len(claimed) != 64:
        raise ValueError("smoke report content hash is invalid")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("smoke report content fingerprint mismatch")


__all__ = [
    "ACQUISITION_CONTENT_SHA256",
    "ACQUISITION_CONTRACT_ID",
    "ARTIFACT_TYPE",
    "AUTHORIZED_PUSH_PARENT_SHA",
    "DOWNLOAD_SCHEMA_ORDER",
    "MAX_PREFLIGHT_BILLABLE_SIZE_BYTES",
    "MAX_PREFLIGHT_COST_USD",
    "MIN_REFERENCE_ALIGNMENT_RATIO",
    "RuntimeConstants",
    "build_unavailable_report",
    "load_acquisition_contract",
    "run_smoke_acquisition",
    "validate_acquisition_contract",
    "validate_smoke_report",
]
