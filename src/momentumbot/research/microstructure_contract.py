from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
import re
import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA_VERSION = 1
CONTRACT_ID = "level2-tape-feasibility-v0.1"
ARTIFACT_TYPE = "preregistered_provider_neutral_microstructure_capability"
DEPTH_SCHEMA_ID = "canonical-depth-event-v0.1"
TAPE_SCHEMA_ID = "canonical-tape-event-v0.1"
MICRO_RUNTIME_ZIP_SHA256 = (
    "3b59e4b1a69e268158f6ccbead1fe9abae425fc249e72b34f466e53ebba56b20"
)
STRATEGY_COVERAGE_CONTENT_SHA256 = (
    "3507642f70bbb8f4551238bc09242dd8c31474b463bf9a4e88f03a7894d97fe3"
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,31}$")
_PROHIBITED_SELECTION_KEYS = frozenset(
    {
        "ross_action",
        "ross_label",
        "retrospective_label",
        "recap_judgment",
        "pnl",
        "profit",
        "trade_outcome",
        "later_price",
    }
)


class DepthAction(str, Enum):
    CLEAR = "clear"
    ADD = "add"
    CANCEL = "cancel"
    MODIFY = "modify"
    TRADE = "trade"
    FILL = "fill"


class BookSide(str, Enum):
    BID = "bid"
    ASK = "ask"
    NONE = "none"


class AggressorSide(str, Enum):
    BUY = "buy"
    SELL = "sell"
    UNKNOWN = "unknown"


def canonical_fingerprint(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


@dataclass(frozen=True, slots=True)
class CanonicalDepthEvent:
    event_id: str
    provider: str
    dataset: str
    venue: str
    symbol: str
    instrument_id: str
    publisher_id: int
    channel_id: int
    ts_event_ns: int
    ts_recv_ns: int
    sequence: int
    action: DepthAction
    side: BookSide
    price_nanos: int | None
    size: int
    order_id: int | None
    is_snapshot: bool
    is_last: bool
    bad_ts_recv: bool

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "CanonicalDepthEvent":
        event_id = _string(value.get("event_id"), "event_id")
        symbol = _string(value.get("symbol"), "symbol")
        if not _SYMBOL.fullmatch(symbol):
            raise ValueError("symbol must be canonical uppercase US-equity notation")
        action = DepthAction(value.get("action"))
        side = BookSide(value.get("side"))
        price_value = value.get("price_nanos")
        price_nanos = None if price_value is None else _integer(
            price_value, "price_nanos", minimum=1
        )
        order_value = value.get("order_id")
        order_id = None if order_value is None else _integer(
            order_value, "order_id", minimum=1
        )
        size = _integer(value.get("size"), "size")
        ts_event_ns = _integer(value.get("ts_event_ns"), "ts_event_ns", minimum=1)
        ts_recv_ns = _integer(value.get("ts_recv_ns"), "ts_recv_ns", minimum=1)
        is_snapshot = value.get("is_snapshot")
        is_last = value.get("is_last")
        bad_ts_recv = value.get("bad_ts_recv")
        if not all(isinstance(item, bool) for item in (is_snapshot, is_last, bad_ts_recv)):
            raise ValueError("snapshot, last, and bad timestamp flags must be booleans")
        if ts_recv_ns < ts_event_ns and not bad_ts_recv:
            raise ValueError("receive timestamp precedes event timestamp without a data-quality flag")

        if action is DepthAction.CLEAR:
            if side is not BookSide.NONE or price_nanos is not None or size != 0 or order_id is not None:
                raise ValueError("clear events must carry no side, price, size, or order ID")
        else:
            if price_nanos is None:
                raise ValueError("non-clear depth events require a positive price")
            if action in {DepthAction.ADD, DepthAction.MODIFY, DepthAction.FILL} and size <= 0:
                raise ValueError(f"{action.value} events require positive size")
            if action in {DepthAction.ADD, DepthAction.CANCEL, DepthAction.MODIFY, DepthAction.FILL}:
                if order_id is None:
                    raise ValueError(f"{action.value} events require an order ID")
                if side is BookSide.NONE:
                    raise ValueError(f"{action.value} events require a book side")
            if action is DepthAction.TRADE and size <= 0:
                raise ValueError("trade events require positive size")

        return cls(
            event_id=event_id,
            provider=_string(value.get("provider"), "provider"),
            dataset=_string(value.get("dataset"), "dataset"),
            venue=_string(value.get("venue"), "venue"),
            symbol=symbol,
            instrument_id=_string(value.get("instrument_id"), "instrument_id"),
            publisher_id=_integer(value.get("publisher_id"), "publisher_id"),
            channel_id=_integer(value.get("channel_id"), "channel_id"),
            ts_event_ns=ts_event_ns,
            ts_recv_ns=ts_recv_ns,
            sequence=_integer(value.get("sequence"), "sequence"),
            action=action,
            side=side,
            price_nanos=price_nanos,
            size=size,
            order_id=order_id,
            is_snapshot=is_snapshot,
            is_last=is_last,
            bad_ts_recv=bad_ts_recv,
        )


@dataclass(frozen=True, slots=True)
class CanonicalTapeEvent:
    event_id: str
    provider: str
    dataset: str
    venue: str
    symbol: str
    instrument_id: str
    ts_event_ns: int
    ts_recv_ns: int
    sequence: int
    price_nanos: int
    size: int
    aggressor_side: AggressorSide
    correction_or_cancel: bool

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "CanonicalTapeEvent":
        symbol = _string(value.get("symbol"), "symbol")
        if not _SYMBOL.fullmatch(symbol):
            raise ValueError("symbol must be canonical uppercase US-equity notation")
        correction = value.get("correction_or_cancel")
        if not isinstance(correction, bool):
            raise ValueError("correction_or_cancel must be boolean")
        ts_event_ns = _integer(value.get("ts_event_ns"), "ts_event_ns", minimum=1)
        ts_recv_ns = _integer(value.get("ts_recv_ns"), "ts_recv_ns", minimum=1)
        if ts_recv_ns < ts_event_ns:
            raise ValueError("tape receive timestamp cannot precede event timestamp")
        return cls(
            event_id=_string(value.get("event_id"), "event_id"),
            provider=_string(value.get("provider"), "provider"),
            dataset=_string(value.get("dataset"), "dataset"),
            venue=_string(value.get("venue"), "venue"),
            symbol=symbol,
            instrument_id=_string(value.get("instrument_id"), "instrument_id"),
            ts_event_ns=ts_event_ns,
            ts_recv_ns=ts_recv_ns,
            sequence=_integer(value.get("sequence"), "sequence"),
            price_nanos=_integer(value.get("price_nanos"), "price_nanos", minimum=1),
            size=_integer(value.get("size"), "size", minimum=1),
            aggressor_side=AggressorSide(value.get("aggressor_side")),
            correction_or_cancel=correction,
        )


def validate_depth_stream(
    values: Sequence[Mapping[str, object]],
    *,
    require_complete_initial_state: bool,
) -> tuple[CanonicalDepthEvent, ...]:
    if not values:
        raise ValueError("depth stream must not be empty")
    events = tuple(CanonicalDepthEvent.from_mapping(value) for value in values)
    event_ids = [event.event_id for event in events]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("depth event IDs must be unique")

    previous_recv = -1
    previous_sequence: dict[tuple[str, str, int, int], int] = {}
    initialized: set[tuple[str, str]] = set()
    open_snapshot: set[tuple[str, str]] = set()
    for event in events:
        if event.ts_recv_ns < previous_recv:
            raise ValueError("depth stream must be ordered by receive timestamp")
        previous_recv = event.ts_recv_ns
        channel = (event.provider, event.dataset, event.publisher_id, event.channel_id)
        if not event.is_snapshot and event.sequence > 0:
            prior = previous_sequence.get(channel)
            if prior is not None and event.sequence <= prior:
                raise ValueError("non-snapshot sequence must increase within each channel")
            previous_sequence[channel] = event.sequence

        instrument = (event.dataset, event.instrument_id)
        if event.action is DepthAction.CLEAR:
            initialized.add(instrument)
            if event.is_snapshot and not event.is_last:
                open_snapshot.add(instrument)
            else:
                open_snapshot.discard(instrument)
        elif require_complete_initial_state and instrument not in initialized:
            raise ValueError("book mutation observed before an initial clear")

        if instrument in open_snapshot:
            if not event.is_snapshot:
                raise ValueError("live event arrived before snapshot completion")
            if event.is_last:
                open_snapshot.remove(instrument)
        elif event.is_snapshot and event.action is not DepthAction.CLEAR:
            raise ValueError("snapshot record observed without an open snapshot")

    if open_snapshot:
        raise ValueError("depth snapshot is incomplete")
    return events


def validate_tape_stream(
    values: Sequence[Mapping[str, object]],
) -> tuple[CanonicalTapeEvent, ...]:
    if not values:
        raise ValueError("tape stream must not be empty")
    events = tuple(CanonicalTapeEvent.from_mapping(value) for value in values)
    event_ids = [event.event_id for event in events]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("tape event IDs must be unique")
    if any(right.ts_recv_ns < left.ts_recv_ns for left, right in zip(events, events[1:])):
        raise ValueError("tape stream must be ordered by receive timestamp")
    return events


def select_activity_spread_smoke_cohort(
    values: Sequence[Mapping[str, object]],
    *,
    sample_count: int = 4,
) -> list[dict[str, object]]:
    """Select deterministic activity-spread cases without trade labels or P&L."""

    if sample_count < 2:
        raise ValueError("sample_count must be at least two")
    rows: list[dict[str, object]] = []
    keys: set[tuple[str, str]] = set()
    for index, value in enumerate(values):
        prohibited = _PROHIBITED_SELECTION_KEYS.intersection(value)
        if prohibited:
            raise ValueError(f"selection row {index} contains prohibited keys: {sorted(prohibited)}")
        trading_date = _string(value.get("trading_date"), "trading_date")
        symbol = _string(value.get("symbol"), "symbol")
        if not _SYMBOL.fullmatch(symbol):
            raise ValueError("selection symbol must be canonical")
        key = (trading_date, symbol)
        if key in keys:
            raise ValueError("selection symbol-date rows must be unique")
        keys.add(key)
        filled_count = _integer(value.get("filled_count"), "filled_count", minimum=1)
        plan_count = _integer(value.get("plan_count"), "plan_count", minimum=1)
        if filled_count > plan_count:
            raise ValueError("filled_count cannot exceed plan_count")
        rows.append(
            {
                "trading_date": trading_date,
                "symbol": symbol,
                "trade_row_count": _integer(
                    value.get("trade_row_count"), "trade_row_count", minimum=1
                ),
                "plan_count": plan_count,
                "filled_count": filled_count,
            }
        )
    if len(rows) < sample_count:
        raise ValueError("not enough rows for requested activity-spread sample")
    rows.sort(key=lambda row: (row["trade_row_count"], row["trading_date"], row["symbol"]))
    indices = [math.floor(index * (len(rows) - 1) / (sample_count - 1)) for index in range(sample_count)]
    if len(indices) != len(set(indices)):
        raise ValueError("activity-spread selection produced duplicate ranks")
    return [{**rows[index], "activity_rank_zero_based": index} for index in indices]


def inspect_filled_micro_symbol_dates(
    zip_path: str | Path,
    *,
    expected_zip_sha256: str = MICRO_RUNTIME_ZIP_SHA256,
) -> list[dict[str, object]]:
    """Read only label-blind runtime metadata and causal trade row counts from a frozen ZIP."""

    path = Path(zip_path)
    if not _SHA256.fullmatch(expected_zip_sha256):
        raise ValueError("expected Micro runtime ZIP fingerprint is invalid")
    if file_sha256(path) != expected_zip_sha256:
        raise ValueError("Micro runtime ZIP fingerprint changed")
    rows: list[dict[str, object]] = []
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        for name in sorted(names):
            if not name.endswith("/runtime-replay.json"):
                continue
            value = json.loads(archive.read(name))
            if not isinstance(value, dict):
                raise ValueError(f"runtime replay is not an object: {name}")
            filled_count = value.get("filled_count")
            if filled_count is None or filled_count == 0:
                continue
            if value.get("retrospective_behavior_labels_loaded") is not False:
                raise ValueError(f"runtime replay was not label-blind: {name}")
            base = name.rsplit("/", 1)[0]
            trades_name = f"{base}/trades.csv.gz"
            if trades_name not in names:
                raise ValueError(f"filled runtime lacks causal trades: {name}")
            with gzip.GzipFile(fileobj=io.BytesIO(archive.read(trades_name))) as handle:
                trade_row_count = sum(1 for _ in handle) - 1
            rows.append(
                {
                    "trading_date": _string(value.get("trading_date"), "trading_date"),
                    "symbol": _string(value.get("symbol"), "symbol"),
                    "trade_row_count": trade_row_count,
                    "plan_count": _integer(value.get("plan_count"), "plan_count", minimum=1),
                    "filled_count": _integer(filled_count, "filled_count", minimum=1),
                }
            )
    rows.sort(key=lambda row: (row["trading_date"], row["symbol"]))
    return rows


def validate_level2_registration(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported Level 2 feasibility schema")
    if payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected Level 2 feasibility contract")
    if payload.get("artifact_type") != ARTIFACT_TYPE:
        raise ValueError("unexpected Level 2 feasibility artifact type")
    if payload.get("runtime_strategy_effect") != "none_shadow_only":
        raise ValueError("Level 2 capability registration cannot affect runtime")
    for field in (
        "policy_promotion_eligible",
        "profitability_claim_eligible",
        "exact_ross_replication_claim_eligible",
        "broker_change_authorized",
        "data_purchase_authorized",
        "provider_download_started",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must be false")

    claimed = _string(payload.get("content_sha256"), "content_sha256")
    if not _SHA256.fullmatch(claimed):
        raise ValueError("content_sha256 must be a lowercase SHA-256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("Level 2 feasibility content fingerprint mismatch")

    parents = _mapping(payload.get("frozen_parents"), "frozen_parents")
    if parents.get("micro_runtime_zip_sha256") != MICRO_RUNTIME_ZIP_SHA256:
        raise ValueError("Micro runtime parent changed")
    if parents.get("strategy_coverage_content_sha256") != STRATEGY_COVERAGE_CONTENT_SHA256:
        raise ValueError("strategy coverage parent changed")
    if parents.get("retrospective_labels_used_for_cohort_selection") is not False:
        raise ValueError("source cohort must remain label-blind")

    event_contract = _mapping(payload.get("canonical_event_contract"), "canonical_event_contract")
    if event_contract.get("depth_schema_id") != DEPTH_SCHEMA_ID:
        raise ValueError("depth schema ID changed")
    if event_contract.get("tape_schema_id") != TAPE_SCHEMA_ID:
        raise ValueError("tape schema ID changed")
    if event_contract.get("missing_or_incomplete_behavior") != "fail_closed_unavailable":
        raise ValueError("incomplete microstructure data must fail closed")

    cohort = _mapping(payload.get("engineering_cohort"), "engineering_cohort")
    rows = cohort.get("filled_symbol_dates")
    if not isinstance(rows, list):
        raise ValueError("engineering filled_symbol_dates must be a list")
    if cohort.get("symbol_date_count") != len(rows) or len(rows) != 36:
        raise ValueError("engineering cohort must retain all 36 filled symbol-dates")
    unique_symbols = {_string(row.get("symbol"), "cohort symbol") for row in rows if isinstance(row, Mapping)}
    if cohort.get("unique_symbol_count") != len(unique_symbols) or len(unique_symbols) != 35:
        raise ValueError("engineering cohort unique symbol count does not recompute")
    expected_smoke = select_activity_spread_smoke_cohort(rows, sample_count=4)
    if cohort.get("smoke_symbol_dates") != expected_smoke:
        raise ValueError("smoke cohort is not the registered deterministic activity spread")

    evaluation = _mapping(payload.get("prospective_evaluation_cohort"), "prospective_evaluation_cohort")
    expected_dates = [
        "2026-08-24",
        "2026-08-25",
        "2026-08-26",
        "2026-08-27",
        "2026-08-28",
        "2026-08-31",
        "2026-09-01",
        "2026-09-02",
        "2026-09-03",
        "2026-09-04",
    ]
    if evaluation.get("dates") != expected_dates:
        raise ValueError("prospective evaluation dates changed")
    if evaluation.get("symbol_selection_rule") != "every_symbol_date_with_at_least_one_frozen_micro_v0_1_fill":
        raise ValueError("prospective symbol selection rule changed")
    if evaluation.get("results_opened_before_feature_policy_freeze") is not False:
        raise ValueError("feature policy must precede prospective results")

    providers = payload.get("provider_capability_candidates")
    if not isinstance(providers, list) or not providers:
        raise ValueError("provider capability candidates must be non-empty")
    primary = _mapping(providers[0], "primary provider candidate")
    if primary.get("provider_id") != "databento":
        raise ValueError("first bounded provider candidate must remain Databento")
    if primary.get("first_depth_dataset") != "XNAS.ITCH":
        raise ValueError("first depth dataset changed")
    if primary.get("venue_scope") != "single_venue_not_consolidated_national_depth":
        raise ValueError("Nasdaq depth scope must remain explicit")

    features = payload.get("registered_feature_hypotheses")
    if not isinstance(features, list) or not features:
        raise ValueError("registered feature hypotheses must be non-empty")
    feature_ids: set[str] = set()
    for index, value in enumerate(features):
        item = _mapping(value, f"registered_feature_hypotheses[{index}]")
        feature_id = _string(item.get("feature_id"), "feature_id")
        if feature_id in feature_ids:
            raise ValueError("feature hypothesis IDs must be unique")
        feature_ids.add(feature_id)
        if item.get("threshold") is not None:
            raise ValueError("capability registration cannot fit feature thresholds")
        if item.get("runtime_authority") != "none":
            raise ValueError("feature hypotheses cannot have runtime authority")


def load_level2_registration(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Level 2 registration root must be an object")
    validate_level2_registration(payload)
    return payload
