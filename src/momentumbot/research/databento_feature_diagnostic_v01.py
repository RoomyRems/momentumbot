from __future__ import annotations

import hashlib
import json
import re
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

from momentumbot.research import microstructure_features as feature_engine_module
from momentumbot.research.databento_quote import DATASET, SDK_VERSION, QuoteRequest
from momentumbot.research.databento_smoke import (
    HistoricalClient,
    RuntimeConstants,
    _char,
    _decimal,
    _finish_report,
    _has_fields,
    _integer,
    _iso_z,
    _metadata_value,
    _request_kwargs,
)
from momentumbot.research.microstructure_contract import (
    AggressorSide,
    BookSide,
    CanonicalDepthEvent,
    CanonicalTapeEvent,
    DepthAction,
    canonical_fingerprint,
    file_sha256,
)
from momentumbot.research.microstructure_features import (
    FEATURE_SET_CONTENT_SHA256,
    FEATURE_SET_ID,
    REGISTERED_WINDOWS_NS,
    CausalMicrostructureFeatureEngine,
)


SCHEMA_VERSION = 1
DIAGNOSTIC_CONTRACT_ID = "databento-microstructure-feature-diagnostic-v0.1"
EXECUTION_AUTHORIZATION_ID = (
    "databento-microstructure-feature-diagnostic-v0.1-execution"
)
ARTIFACT_TYPE = "sanitized_ephemeral_databento_threshold_free_feature_diagnostic"
CONTRACT_CONTENT_SHA256 = (
    "996e987f04cd14a87eb8ad56b5dfce9c84fcfbef1bc3af7b44919be0ec00e180"
)
FEATURE_ENGINE_SOURCE_FILE_SHA256 = (
    "07e2db045c9187e4bab46e7d25c546668c2c7b8d01f78c58ec36e88e48f1628e"
)
REPLICATION_AUDIT_CONTENT_SHA256 = (
    "66e16d7481afceaf38dacdf78c0f1974532cdb31f24cf50252ad3c914c8338a3"
)
MAX_PREFLIGHT_COST_USD = Decimal("0.08")
MAX_PREFLIGHT_BILLABLE_SIZE_BYTES = 80_000_000
SAMPLE_INTERVAL_NS = 1_000_000_000
FIXED_HYPOTHETICAL_ORDER_SIZES = (100, 500, 1000)
FEATURE_CASES = (
    ("2026-07-10", "INTJ"),
    ("2026-07-10", "EQPT"),
    ("2026-07-20", "AMC"),
    ("2026-07-10", "GMM"),
)
REQUESTS = (
    QuoteRequest(
        trading_date="2026-07-10",
        symbol="INTJ",
        dataset=DATASET,
        schema="mbo",
        start="2026-07-10T00:00:00Z",
        end="2026-07-10T14:10:00Z",
    ),
    QuoteRequest(
        trading_date="2026-07-10",
        symbol="EQPT",
        dataset=DATASET,
        schema="mbo",
        start="2026-07-10T00:00:00Z",
        end="2026-07-10T14:10:00Z",
    ),
    QuoteRequest(
        trading_date="2026-07-20",
        symbol="AMC",
        dataset=DATASET,
        schema="mbo",
        start="2026-07-20T00:00:00Z",
        end="2026-07-20T14:10:00Z",
    ),
    QuoteRequest(
        trading_date="2026-07-10",
        symbol="GMM",
        dataset=DATASET,
        schema="mbo",
        start="2026-07-10T00:00:00Z",
        end="2026-07-10T14:10:00Z",
    ),
)

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_MBO_FIELDS = (
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


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _verify_feature_engine_source() -> None:
    source_path = Path(str(feature_engine_module.__file__))
    if source_path.suffix != ".py":
        raise ValueError("feature diagnostic requires the frozen Python source file")
    if file_sha256(source_path) != FEATURE_ENGINE_SOURCE_FILE_SHA256:
        raise ValueError("frozen feature engine source changed")


def validate_diagnostic_contract(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported feature diagnostic contract schema")
    if payload.get("diagnostic_contract_id") != DIAGNOSTIC_CONTRACT_ID:
        raise ValueError("unexpected feature diagnostic contract")
    if payload.get("artifact_type") != (
        "preregistered_unarmed_bounded_ephemeral_databento_"
        "threshold_free_feature_diagnostic"
    ):
        raise ValueError("unexpected feature diagnostic contract type")
    claimed = payload.get("content_sha256")
    if claimed != CONTRACT_CONTENT_SHA256:
        raise ValueError("feature diagnostic contract content hash changed")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("feature diagnostic contract fingerprint mismatch")

    parents = _mapping(payload.get("frozen_parents"), "frozen_parents")
    expected_parents = {
        "feature_set_id": FEATURE_SET_ID,
        "feature_set_content_sha256": FEATURE_SET_CONTENT_SHA256,
        "feature_engine_file_sha256": FEATURE_ENGINE_SOURCE_FILE_SHA256,
        "replication_audit_content_sha256": REPLICATION_AUDIT_CONTENT_SHA256,
        "verified_mbo_to_mbp10_samples": 612,
        "verified_mbo_to_mbp10_exact_matches": 612,
        "feature_engine_mutation_allowed": False,
        "four_case_results_may_select_horizon_or_threshold": False,
    }
    for field, expected in expected_parents.items():
        if parents.get(field) != expected:
            raise ValueError(f"frozen_parents.{field} changed")

    provider = _mapping(payload.get("provider"), "provider")
    expected_provider = {
        "provider_id": "databento",
        "dataset": DATASET,
        "schema": "mbo",
        "venue": "XNAS",
        "venue_scope": "single_venue_nasdaq_not_consolidated_national_depth",
        "sdk_package": "databento",
        "sdk_version": SDK_VERSION,
        "secret_name": "DATABENTO_API_KEY",
    }
    for field, expected in expected_provider.items():
        if provider.get(field) != expected:
            raise ValueError(f"provider.{field} changed")

    normalization = _mapping(
        payload.get("provider_normalization"), "provider_normalization"
    )
    if normalization.get("xnas_executed_order_sequence") != [
        "Trade",
        "Fill",
        "Cancel",
    ]:
        raise ValueError("XNAS executed-order normalization changed")
    for field in (
        "same_native_message_records_share_sequence",
        "trade_side_is_aggressor_side",
        "fill_side_is_resting_side",
        "matching_cancel_is_classified_as_executed_removal",
        "non_displayed_trade_side_is_unknown",
        "f_last_defines_atomic_instrument_event_boundary",
    ):
        if normalization.get(field) is not True:
            raise ValueError(f"provider_normalization.{field} changed")
    if normalization.get("fill_record_alone_mutates_book") is not False:
        raise ValueError("Fill records cannot mutate the book by themselves")
    if normalization.get("broken_or_corrected_trade_output_available_in_xnas_mbo") is not False:
        raise ValueError("XNAS correction availability changed")

    surface = _mapping(payload.get("request_surface"), "request_surface")
    observed_cases = tuple(
        (
            str(_mapping(row, "case").get("trading_date")),
            str(_mapping(row, "case").get("symbol")),
        )
        for row in surface.get("cases", [])
    )
    if observed_cases != FEATURE_CASES:
        raise ValueError("feature diagnostic cases changed")
    observed_requests = tuple(
        QuoteRequest(
            trading_date=str(_mapping(row, "request").get("trading_date")),
            symbol=str(_mapping(row, "request").get("symbol")),
            dataset=str(_mapping(row, "request").get("dataset")),
            schema=str(_mapping(row, "request").get("schema")),
            start=str(_mapping(row, "request").get("start")),
            end=str(_mapping(row, "request").get("end")),
            stype_in=str(_mapping(row, "request").get("stype_in")),
        )
        for row in surface.get("requests", [])
    )
    if observed_requests != REQUESTS:
        raise ValueError("feature diagnostic exact request surface changed")
    if surface.get("exact_request_count") != 4:
        raise ValueError("feature diagnostic request count changed")

    sampling = _mapping(
        payload.get("sampling_and_feature_policy"), "sampling_and_feature_policy"
    )
    expected_sampling = {
        "sample_interval_ns": SAMPLE_INTERVAL_NS,
        "feature_windows_ns": list(REGISTERED_WINDOWS_NS),
        "all_registered_windows_emitted_together": True,
        "fixed_hypothetical_order_sizes": list(FIXED_HYPOTHETICAL_ORDER_SIZES),
        "causal_breakout_level_supplied": False,
        "feature_thresholds": [],
        "threshold_or_horizon_selection_allowed": False,
        "intent_or_spoofing_classification_allowed": False,
        "retrospective_label_access_allowed": False,
        "ross_action_or_fill_access_allowed": False,
        "later_price_access_allowed": False,
    }
    for field, expected in expected_sampling.items():
        if sampling.get(field) != expected:
            raise ValueError(f"sampling_and_feature_policy.{field} changed")

    gate = _mapping(
        payload.get("execution_authorization_gate"), "execution_authorization_gate"
    )
    expected_gate = {
        "provider_purchase_authorized": False,
        "execution_authorization_file_present": False,
        "new_explicit_user_authorization_required": True,
        "future_authorization_must_bind_published_parent_sha": True,
        "first_github_actions_attempt_only": True,
        "automatic_retry_allowed": False,
        "hard_preflight_cost_ceiling_usd": "0.08",
        "hard_preflight_billable_size_ceiling_bytes": 80_000_000,
        "mbp10_redownload_allowed": False,
        "broad_history_download_allowed": False,
        "broker_or_order_change_allowed": False,
    }
    for field, expected in expected_gate.items():
        if gate.get(field) != expected:
            raise ValueError(f"execution_authorization_gate.{field} changed")
    _verify_feature_engine_source()


def load_diagnostic_contract(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("feature diagnostic contract root must be an object")
    validate_diagnostic_contract(payload)
    return payload


def validate_execution_authorization(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported feature execution authorization schema")
    if payload.get("execution_authorization_id") != EXECUTION_AUTHORIZATION_ID:
        raise ValueError("unexpected feature execution authorization")
    if payload.get("artifact_type") != (
        "explicit_one_shot_databento_feature_diagnostic_authorization"
    ):
        raise ValueError("unexpected feature execution authorization type")
    if payload.get("diagnostic_contract_id") != DIAGNOSTIC_CONTRACT_ID:
        raise ValueError("feature execution authorization contract ID changed")
    claimed = payload.get("content_sha256")
    if not isinstance(claimed, str) or not _SHA64.fullmatch(claimed):
        raise ValueError("feature execution authorization hash is invalid")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("feature execution authorization fingerprint mismatch")
    if payload.get("diagnostic_contract_content_sha256") != CONTRACT_CONTENT_SHA256:
        raise ValueError("feature execution authorization contract binding changed")
    if payload.get("provider_purchase_authorized") is not True:
        raise ValueError("provider purchase is not authorized")
    if payload.get("first_github_actions_attempt_only") is not True:
        raise ValueError("feature execution authorization must be one shot")
    if payload.get("exact_request_count_authorized") != 4:
        raise ValueError("execution authorization request count changed")
    if payload.get("hard_preflight_cost_ceiling_usd") != "0.08":
        raise ValueError("execution authorization cost ceiling changed")
    if payload.get("hard_preflight_billable_size_ceiling_bytes") != 80_000_000:
        raise ValueError("execution authorization size ceiling changed")
    parent = payload.get("authorized_push_parent_sha")
    if not isinstance(parent, str) or not _SHA40.fullmatch(parent):
        raise ValueError("execution authorization parent SHA is invalid")
    statement = payload.get("explicit_user_authorization")
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError("explicit user authorization statement is required")
    for field in (
        "automatic_retry_authorized",
        "batch_or_live_endpoint_authorized",
        "mbp10_redownload_authorized",
        "raw_market_data_publication_authorized",
        "broker_or_order_change_authorized",
        "strategy_or_threshold_change_authorized",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"execution authorization {field} must remain false")


def load_execution_authorization(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("feature execution authorization root must be an object")
    validate_execution_authorization(payload)
    return payload


@dataclass(frozen=True, slots=True)
class TranslatedAtomicGroup:
    ts_recv_ns: int
    ordered_events: tuple[CanonicalDepthEvent | CanonicalTapeEvent, ...]
    depth_events: tuple[CanonicalDepthEvent, ...]
    tape_events: tuple[CanonicalTapeEvent, ...]
    action_counts: Mapping[str, int]
    matched_executed_removal_count: int
    ignored_fill_marker_count: int
    ignored_none_count: int


def _record_key(record: object) -> tuple[int, int, int]:
    return (
        _integer(getattr(record, "publisher_id"), "publisher_id"),
        _integer(getattr(record, "instrument_id"), "instrument_id"),
        _integer(getattr(record, "sequence"), "sequence"),
    )


def iter_atomic_mbo_groups(
    store: Iterable[object],
    *,
    runtime: RuntimeConstants,
) -> Iterator[tuple[object, ...]]:
    current: list[object] = []
    current_key: tuple[int, int, int] | None = None
    previous_ts_recv = -1
    for record in store:
        if not _has_fields(record, _REQUIRED_MBO_FIELDS):
            raise ValueError("MBO record is missing a required field")
        ts_recv = _integer(getattr(record, "ts_recv"), "ts_recv", minimum=1)
        flags = _integer(getattr(record, "flags"), "flags")
        if ts_recv < previous_ts_recv and not flags & runtime.f_bad_ts_recv:
            raise ValueError("unflagged MBO receive timestamp reversal")
        previous_ts_recv = max(previous_ts_recv, ts_recv)
        key = _record_key(record)
        if current_key is None:
            current_key = key
        elif key != current_key:
            raise ValueError("MBO atomic group changed before F_LAST")
        current.append(record)
        if flags & runtime.f_last:
            yield tuple(current)
            current = []
            current_key = None
    if current:
        raise ValueError("MBO stream ended before F_LAST")


def _book_side(value: str) -> BookSide:
    if value == "B":
        return BookSide.BID
    if value == "A":
        return BookSide.ASK
    if value == "N":
        return BookSide.NONE
    raise ValueError("unsupported Databento MBO side")


def _aggressor_side(value: str) -> AggressorSide:
    if value == "B":
        return AggressorSide.BUY
    if value == "A":
        return AggressorSide.SELL
    if value == "N":
        return AggressorSide.UNKNOWN
    raise ValueError("unsupported Databento trade side")


def _fill_identity(record: object) -> tuple[int, str, int, int]:
    return (
        _integer(getattr(record, "order_id"), "order_id", minimum=1),
        _char(getattr(record, "side")),
        _integer(getattr(record, "price"), "price", minimum=1),
        _integer(getattr(record, "size"), "size", minimum=1),
    )


def translate_xnas_atomic_group(
    records: Sequence[object],
    *,
    symbol: str,
    runtime: RuntimeConstants,
) -> TranslatedAtomicGroup:
    if not records:
        raise ValueError("MBO atomic group must not be empty")
    keys = {_record_key(record) for record in records}
    if len(keys) != 1:
        raise ValueError("MBO atomic group scope is inconsistent")
    final_flags = _integer(getattr(records[-1], "flags"), "flags")
    if not final_flags & runtime.f_last:
        raise ValueError("MBO atomic group does not end with F_LAST")

    fills: Counter[tuple[int, str, int, int]] = Counter()
    for record in records:
        if _char(getattr(record, "action")) == "F":
            fills[_fill_identity(record)] += 1

    depth_events: list[CanonicalDepthEvent] = []
    tape_events: list[CanonicalTapeEvent] = []
    ordered_events: list[CanonicalDepthEvent | CanonicalTapeEvent] = []
    action_counts: Counter[str] = Counter()
    matched_fills = 0
    ignored_fill_markers = 0
    ignored_none = 0

    for index, record in enumerate(records):
        flags = _integer(getattr(record, "flags"), "flags")
        publisher_id = _integer(getattr(record, "publisher_id"), "publisher_id")
        instrument_id = _integer(getattr(record, "instrument_id"), "instrument_id")
        channel_id = _integer(getattr(record, "channel_id"), "channel_id")
        sequence = _integer(getattr(record, "sequence"), "sequence")
        ts_event = _integer(getattr(record, "ts_event"), "ts_event", minimum=1)
        ts_recv = _integer(getattr(record, "ts_recv"), "ts_recv", minimum=1)
        action = _char(getattr(record, "action"))
        side = _char(getattr(record, "side"))
        raw_price = _integer(getattr(record, "price"), "price")
        size = _integer(getattr(record, "size"), "size")
        raw_order_id = _integer(getattr(record, "order_id"), "order_id")
        action_counts[action] += 1
        event_id = f"{publisher_id}:{instrument_id}:{sequence}:{index}:{action}"
        common = {
            "event_id": event_id,
            "provider": "databento",
            "dataset": DATASET,
            "venue": "XNAS",
            "symbol": symbol,
            "instrument_id": str(instrument_id),
            "publisher_id": publisher_id,
            "channel_id": channel_id,
            "ts_event_ns": ts_event,
            "ts_recv_ns": ts_recv,
            "sequence": sequence,
            "is_snapshot": bool(flags & runtime.f_snapshot),
            "is_last": bool(flags & runtime.f_last),
            "bad_ts_recv": bool(flags & runtime.f_bad_ts_recv),
        }

        if action == "F":
            ignored_fill_markers += 1
            continue
        if action == "N":
            ignored_none += 1
            continue
        if action == "R":
            event = CanonicalDepthEvent.from_mapping(
                {
                    **common,
                    "action": DepthAction.CLEAR.value,
                    "side": BookSide.NONE.value,
                    "price_nanos": None,
                    "size": 0,
                    "order_id": None,
                }
            )
            depth_events.append(event)
            ordered_events.append(event)
            continue
        if action == "T":
            depth_event = CanonicalDepthEvent.from_mapping(
                {
                    **common,
                    "action": DepthAction.TRADE.value,
                    "side": BookSide.NONE.value,
                    "price_nanos": raw_price,
                    "size": size,
                    "order_id": None,
                }
            )
            tape_event = CanonicalTapeEvent.from_mapping(
                {
                    "event_id": event_id,
                    "provider": "databento",
                    "dataset": DATASET,
                    "venue": "XNAS",
                    "symbol": symbol,
                    "instrument_id": str(instrument_id),
                    "ts_event_ns": ts_event,
                    "ts_recv_ns": ts_recv,
                    "sequence": sequence,
                    "price_nanos": raw_price,
                    "size": size,
                    "aggressor_side": _aggressor_side(side).value,
                    "correction_or_cancel": False,
                }
            )
            depth_events.append(depth_event)
            tape_events.append(tape_event)
            ordered_events.extend((depth_event, tape_event))
            continue
        if action not in {"A", "C", "M"}:
            raise ValueError("unsupported Databento XNAS MBO action")
        if raw_price == runtime.undef_price:
            raise ValueError("book mutation has undefined price")
        if action == "M" and size == 0:
            raise ValueError("zero-size modify is unavailable in the canonical adapter")

        canonical_action = {
            "A": DepthAction.ADD,
            "C": DepthAction.CANCEL,
            "M": DepthAction.MODIFY,
        }[action]
        if action == "C":
            identity = (raw_order_id, side, raw_price, size)
            if fills[identity]:
                fills[identity] -= 1
                matched_fills += 1
                canonical_action = DepthAction.FILL
        event = CanonicalDepthEvent.from_mapping(
            {
                **common,
                "action": canonical_action.value,
                "side": _book_side(side).value,
                "price_nanos": raw_price,
                "size": size,
                "order_id": raw_order_id,
            }
        )
        depth_events.append(event)
        ordered_events.append(event)

    if any(fills.values()):
        raise ValueError("XNAS Fill marker has no matching Cancel removal")
    return TranslatedAtomicGroup(
        ts_recv_ns=max(
            _integer(getattr(record, "ts_recv"), "ts_recv", minimum=1)
            for record in records
        ),
        ordered_events=tuple(ordered_events),
        depth_events=tuple(depth_events),
        tape_events=tuple(tape_events),
        action_counts=dict(sorted(action_counts.items())),
        matched_executed_removal_count=matched_fills,
        ignored_fill_marker_count=ignored_fill_markers,
        ignored_none_count=ignored_none,
    )


def _snapshot_summary_template() -> dict[str, object]:
    return {
        "sampled_snapshot_count": 0,
        "book_available_count": 0,
        "two_sided_book_count": 0,
        "threshold_applied_count": 0,
        "runtime_authority_count": 0,
        "breakout_context_available_count": 0,
        "depth_walk_scenario_count": 0,
        "depth_walk_available_count": 0,
        "window_availability": {
            str(window): {
                "sample_count": 0,
                "signed_tape_available_count": 0,
                "signed_tape_unavailable_count": 0,
                "correction_fail_closed_count": 0,
            }
            for window in REGISTERED_WINDOWS_NS
        },
    }


def extract_case_feature_diagnostic(
    store: Iterable[object],
    *,
    request: QuoteRequest,
    runtime: RuntimeConstants,
) -> dict[str, object]:
    if request.schema != "mbo" or request.dataset != DATASET:
        raise ValueError("feature diagnostic requires the exact XNAS.ITCH MBO request")
    engines = (CausalMicrostructureFeatureEngine(), CausalMicrostructureFeatureEngine())
    digest = hashlib.sha256()
    summary = _snapshot_summary_template()
    action_counts: Counter[str] = Counter()
    record_count = 0
    group_count = 0
    depth_event_count = 0
    tape_event_count = 0
    matched_fill_count = 0
    ignored_fill_count = 0
    ignored_none_count = 0
    current_bucket: int | None = None
    last_complete_ts_recv: int | None = None
    ingested_any = False

    def sample(as_of_ts_recv_ns: int) -> None:
        snapshots = tuple(
            engine.snapshot(
                as_of_ts_recv_ns=as_of_ts_recv_ns,
                hypothetical_order_sizes=FIXED_HYPOTHETICAL_ORDER_SIZES,
            )
            for engine in engines
        )
        if snapshots[0] != snapshots[1]:
            raise ValueError("independent feature replays diverged")
        snapshot = snapshots[0]
        if snapshot.get("thresholds_applied") is not False:
            raise ValueError("feature snapshot applied an unregistered threshold")
        if snapshot.get("runtime_authority") != "none_shadow_only":
            raise ValueError("feature snapshot created runtime authority")
        digest.update(str(snapshot["content_sha256"]).encode("ascii"))
        digest.update(b"\n")
        summary["sampled_snapshot_count"] = int(summary["sampled_snapshot_count"]) + 1
        book = _mapping(snapshot.get("book"), "feature book")
        summary["book_available_count"] = int(summary["book_available_count"]) + int(
            book.get("available") is True
        )
        summary["two_sided_book_count"] = int(summary["two_sided_book_count"]) + int(
            book.get("two_sided") is True
        )
        depth_walks = snapshot.get("depth_constrained_slippage")
        if not isinstance(depth_walks, list):
            raise ValueError("feature depth walks must be a list")
        summary["depth_walk_scenario_count"] = int(
            summary["depth_walk_scenario_count"]
        ) + len(depth_walks)
        summary["depth_walk_available_count"] = int(
            summary["depth_walk_available_count"]
        ) + sum(
            int(isinstance(row, Mapping) and row.get("available") is True)
            for row in depth_walks
        )
        windows = snapshot.get("windows")
        if not isinstance(windows, list) or len(windows) != len(REGISTERED_WINDOWS_NS):
            raise ValueError("feature snapshot windows changed")
        availability = _mapping(summary["window_availability"], "window availability")
        for row in windows:
            window = _mapping(row, "feature window")
            key = str(window.get("window_ns"))
            counter = _mapping(availability.get(key), "window counter")
            counter["sample_count"] = int(counter["sample_count"]) + 1
            tape = _mapping(window.get("signed_trade_velocity"), "signed tape")
            available = tape.get("available") is True
            counter["signed_tape_available_count"] = int(
                counter["signed_tape_available_count"]
            ) + int(available)
            counter["signed_tape_unavailable_count"] = int(
                counter["signed_tape_unavailable_count"]
            ) + int(not available)
            counter["correction_fail_closed_count"] = int(
                counter["correction_fail_closed_count"]
            ) + int(tape.get("unavailable_reason") == "correction_or_cancel_in_window")
            breakout = _mapping(
                window.get("breakout_progress_context"), "breakout context"
            )
            summary["breakout_context_available_count"] = int(
                summary["breakout_context_available_count"]
            ) + int(breakout.get("available") is True)

    for records in iter_atomic_mbo_groups(store, runtime=runtime):
        group = translate_xnas_atomic_group(
            records,
            symbol=request.symbol,
            runtime=runtime,
        )
        bucket = group.ts_recv_ns // SAMPLE_INTERVAL_NS
        if (
            current_bucket is not None
            and bucket != current_bucket
            and last_complete_ts_recv is not None
            and ingested_any
        ):
            sample(last_complete_ts_recv)
        current_bucket = bucket
        last_complete_ts_recv = group.ts_recv_ns
        group_count += 1
        record_count += len(records)
        action_counts.update(group.action_counts)
        matched_fill_count += group.matched_executed_removal_count
        ignored_fill_count += group.ignored_fill_marker_count
        ignored_none_count += group.ignored_none_count
        depth_event_count += len(group.depth_events)
        tape_event_count += len(group.tape_events)
        for engine in engines:
            for event in group.ordered_events:
                if isinstance(event, CanonicalDepthEvent):
                    engine.ingest_depth(event)
                else:
                    engine.ingest_tape(event)
        ingested_any = ingested_any or bool(group.ordered_events)

    if last_complete_ts_recv is not None and ingested_any:
        sample(last_complete_ts_recv)
    if group_count == 0:
        raise ValueError("MBO feature diagnostic stream was empty")
    if int(summary["sampled_snapshot_count"]) == 0:
        raise ValueError("MBO feature diagnostic produced no complete snapshot")
    return {
        "record_count": record_count,
        "atomic_group_count": group_count,
        "canonical_depth_event_count": depth_event_count,
        "canonical_tape_event_count": tape_event_count,
        "provider_action_counts": {
            key: action_counts.get(key, 0)
            for key in ("A", "C", "M", "R", "T", "F", "N")
        },
        "matched_executed_removal_count": matched_fill_count,
        "ignored_fill_marker_count": ignored_fill_count,
        "ignored_none_boundary_count": ignored_none_count,
        **summary,
        "independent_feature_replay_exact": True,
        "full_snapshot_sequence_digest_sha256": digest.hexdigest(),
        "feature_threshold_selected": False,
        "feature_horizon_selected": False,
        "runtime_authority_created": False,
    }


def _run_preflight(
    client: HistoricalClient,
) -> tuple[dict[str, object], list[dict[str, str]]]:
    rows: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    total_cost = Decimal("0")
    total_size = 0
    for request in REQUESTS:
        stage = f"preflight:{request.trading_date}:{request.symbol}:mbo"
        try:
            kwargs = _request_kwargs(request)
            size = _integer(client.metadata.get_billable_size(**kwargs), "billable size")
            cost = _decimal(client.metadata.get_cost(**kwargs), "quoted cost")
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
    complete = len(rows) == len(REQUESTS) == 4 and not errors
    within_cost = complete and total_cost <= MAX_PREFLIGHT_COST_USD
    within_size = complete and total_size <= MAX_PREFLIGHT_BILLABLE_SIZE_BYTES
    return (
        {
            "request_count_expected": 4,
            "request_count_quoted": len(rows),
            "quote_rows": rows,
            "total_quoted_cost_usd": format(total_cost, "f") if complete else None,
            "total_billable_size_bytes": total_size if complete else None,
            "hard_cost_ceiling_usd": format(MAX_PREFLIGHT_COST_USD, "f"),
            "hard_billable_size_ceiling_bytes": MAX_PREFLIGHT_BILLABLE_SIZE_BYTES,
            "all_four_quotes_complete": complete,
            "cost_within_ceiling": within_cost,
            "billable_size_within_ceiling": within_size,
            "preflight_passed": complete and within_cost and within_size,
        },
        errors,
    )


def _base_report(
    *,
    authorization: Mapping[str, object],
    generated_at: datetime,
    sdk_version: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "diagnostic_contract_id": DIAGNOSTIC_CONTRACT_ID,
        "diagnostic_contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "execution_authorization_id": EXECUTION_AUTHORIZATION_ID,
        "execution_authorization_content_sha256": authorization["content_sha256"],
        "artifact_type": ARTIFACT_TYPE,
        "generated_at": _iso_z(generated_at),
        "feature_set_id": FEATURE_SET_ID,
        "feature_set_content_sha256": FEATURE_SET_CONTENT_SHA256,
        "feature_engine_source_file_sha256": FEATURE_ENGINE_SOURCE_FILE_SHA256,
        "replication_audit_content_sha256": REPLICATION_AUDIT_CONTENT_SHA256,
        "provider": "databento",
        "dataset": DATASET,
        "schema": "mbo",
        "venue": "XNAS",
        "venue_scope": "single_venue_nasdaq_not_consolidated_national_depth",
        "sdk_version": sdk_version,
        "sample_interval_ns": SAMPLE_INTERVAL_NS,
        "registered_windows_ns": list(REGISTERED_WINDOWS_NS),
        "fixed_hypothetical_order_size_scenario_count": len(
            FIXED_HYPOTHETICAL_ORDER_SIZES
        ),
        "provider_credential_persisted": False,
        "raw_market_data_persisted": False,
        "raw_market_data_uploaded": False,
        "feature_snapshot_values_persisted": False,
        "batch_or_live_endpoint_called": False,
        "automatic_retry_attempted": False,
        "mbp10_redownloaded": False,
        "retrospective_labels_loaded": False,
        "strategy_or_threshold_change_made": False,
        "broker_or_order_change_made": False,
        "actual_billing_known": False,
        "billing_note": (
            "Preflight quotes are not represented as actual billed charges; "
            "completed downloads may be billable."
        ),
    }


def build_unavailable_report(
    contract: Mapping[str, object],
    authorization: Mapping[str, object],
    *,
    generated_at: datetime,
    sdk_version: str,
    error_stage: str,
    error_kind: str,
) -> dict[str, object]:
    validate_diagnostic_contract(contract)
    validate_execution_authorization(authorization)
    report = _base_report(
        authorization=authorization,
        generated_at=generated_at,
        sdk_version=sdk_version,
    )
    report.update(
        {
            "preflight": {
                "request_count_expected": 4,
                "request_count_quoted": 0,
                "quote_rows": [],
                "total_quoted_cost_usd": None,
                "total_billable_size_bytes": None,
                "hard_cost_ceiling_usd": format(MAX_PREFLIGHT_COST_USD, "f"),
                "hard_billable_size_ceiling_bytes": MAX_PREFLIGHT_BILLABLE_SIZE_BYTES,
                "all_four_quotes_complete": False,
                "cost_within_ceiling": False,
                "billable_size_within_ceiling": False,
                "preflight_passed": False,
            },
            "timeseries_request_count": 0,
            "downloads": [],
            "errors": [{"stage": error_stage, "error_kind": error_kind}],
            "raw_temp_directory_empty_before_cleanup": True,
            "raw_temp_directory_removed": True,
            "g3_feature_diagnostic_passed": False,
            "runtime_authority_created": False,
            "policy_promotion_eligible": False,
        }
    )
    return _finish_report(report)


def _download_and_extract(
    client: HistoricalClient,
    request: QuoteRequest,
    path: Path,
    runtime: RuntimeConstants,
) -> dict[str, object]:
    store = client.timeseries.get_range(path=str(path), **_request_kwargs(request))
    if not path.exists() or path.stat().st_size <= 0:
        raise ValueError("Databento MBO download is empty")
    dataset = _metadata_value(getattr(store, "metadata", None), "dataset")
    schema = _metadata_value(getattr(store, "metadata", None), "schema")
    if dataset != DATASET.lower() or schema != "mbo":
        raise ValueError("Databento MBO metadata does not match the request")
    metrics = extract_case_feature_diagnostic(store, request=request, runtime=runtime)
    return {
        "trading_date": request.trading_date,
        "symbol": request.symbol,
        "schema": request.schema,
        "ephemeral_file_sha256": file_sha256(path),
        "file_nonempty": True,
        "metadata_matches_request": True,
        "metrics": metrics,
    }


def run_feature_diagnostic(
    contract: Mapping[str, object],
    authorization: Mapping[str, object],
    client: HistoricalClient,
    *,
    generated_at: datetime,
    sdk_version: str,
    runtime: RuntimeConstants,
) -> dict[str, object]:
    validate_diagnostic_contract(contract)
    validate_execution_authorization(authorization)
    _verify_feature_engine_source()
    if sdk_version != SDK_VERSION:
        raise ValueError(f"Databento SDK version must be {SDK_VERSION}")
    preflight, errors = _run_preflight(client)
    report = _base_report(
        authorization=authorization,
        generated_at=generated_at,
        sdk_version=sdk_version,
    )
    report.update(
        {
            "preflight": preflight,
            "timeseries_request_count": 0,
            "downloads": [],
            "errors": errors,
            "raw_temp_directory_empty_before_cleanup": True,
            "raw_temp_directory_removed": True,
        }
    )
    if preflight.get("preflight_passed") is not True:
        report.update(
            {
                "g3_feature_diagnostic_passed": False,
                "runtime_authority_created": False,
                "policy_promotion_eligible": False,
            }
        )
        return _finish_report(report)

    temp = tempfile.TemporaryDirectory(prefix="momentumbot-databento-features-v01-")
    temp_path = Path(temp.name)
    try:
        for index, request in enumerate(REQUESTS):
            path = temp_path / f"request-{index:02d}.dbn.zst"
            stage = f"download_or_extract:{request.trading_date}:{request.symbol}:mbo"
            try:
                report["timeseries_request_count"] = int(
                    report["timeseries_request_count"]
                ) + 1
                row = _download_and_extract(client, request, path, runtime)
                report["downloads"].append(row)
            except Exception as exc:
                errors.append({"stage": stage, "error_kind": type(exc).__name__})
                break
            finally:
                path.unlink(missing_ok=True)
    finally:
        report["raw_temp_directory_empty_before_cleanup"] = not any(
            temp_path.iterdir()
        )
        temp_name = temp.name
        temp.cleanup()
        report["raw_temp_directory_removed"] = not Path(temp_name).exists()

    downloads = report["downloads"] if isinstance(report["downloads"], list) else []
    passed = (
        not errors
        and len(downloads) == 4
        and report["timeseries_request_count"] == 4
        and report["raw_temp_directory_empty_before_cleanup"] is True
        and report["raw_temp_directory_removed"] is True
        and all(
            isinstance(row, Mapping)
            and _mapping(row.get("metrics"), "feature metrics").get(
                "independent_feature_replay_exact"
            )
            is True
            and int(
                _mapping(row.get("metrics"), "feature metrics").get(
                    "sampled_snapshot_count", 0
                )
            )
            > 0
            for row in downloads
        )
    )
    report.update(
        {
            "g3_feature_diagnostic_passed": passed,
            "runtime_authority_created": False,
            "policy_promotion_eligible": False,
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


def validate_feature_diagnostic_report(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported feature diagnostic report schema")
    if payload.get("diagnostic_contract_id") != DIAGNOSTIC_CONTRACT_ID:
        raise ValueError("unexpected feature diagnostic report contract")
    if payload.get("diagnostic_contract_content_sha256") != CONTRACT_CONTENT_SHA256:
        raise ValueError("feature diagnostic report contract binding changed")
    if payload.get("artifact_type") != ARTIFACT_TYPE:
        raise ValueError("unexpected feature diagnostic report type")
    if payload.get("feature_set_content_sha256") != FEATURE_SET_CONTENT_SHA256:
        raise ValueError("feature diagnostic report feature binding changed")
    if payload.get("feature_engine_source_file_sha256") != (
        FEATURE_ENGINE_SOURCE_FILE_SHA256
    ):
        raise ValueError("feature diagnostic report engine binding changed")
    for field in (
        "provider_credential_persisted",
        "raw_market_data_persisted",
        "raw_market_data_uploaded",
        "feature_snapshot_values_persisted",
        "batch_or_live_endpoint_called",
        "automatic_retry_attempted",
        "mbp10_redownloaded",
        "retrospective_labels_loaded",
        "strategy_or_threshold_change_made",
        "broker_or_order_change_made",
        "actual_billing_known",
        "runtime_authority_created",
        "policy_promotion_eligible",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must remain false")
    if int(payload.get("timeseries_request_count", 0)) > 4:
        raise ValueError("feature diagnostic request count exceeded authorization")
    if payload.get("raw_temp_directory_empty_before_cleanup") is not True:
        raise ValueError("feature diagnostic temporary directory was not empty")
    if payload.get("raw_temp_directory_removed") is not True:
        raise ValueError("feature diagnostic temporary directory was not removed")
    forbidden_keys = {
        "raw_records",
        "record_values",
        "order_id",
        "instrument_id",
        "price",
        "size",
        "levels",
        "feature_snapshots",
        "temporary_path",
        "provider_error_message",
        "exception_message",
        "ross_action",
        "ross_label",
        "pnl",
        "later_price",
    }
    if set(_walk_keys(payload)) & forbidden_keys:
        raise ValueError("sanitized feature diagnostic contains a prohibited field")
    downloads = payload.get("downloads")
    if not isinstance(downloads, list):
        raise ValueError("feature diagnostic downloads must be a list")
    for row in downloads:
        if not isinstance(row, Mapping):
            raise ValueError("feature diagnostic download summary must be an object")
        digest = row.get("ephemeral_file_sha256")
        if not isinstance(digest, str) or not _SHA64.fullmatch(digest):
            raise ValueError("feature diagnostic file hash is invalid")
        metrics = _mapping(row.get("metrics"), "feature diagnostic metrics")
        feature_digest = metrics.get("full_snapshot_sequence_digest_sha256")
        if not isinstance(feature_digest, str) or not _SHA64.fullmatch(feature_digest):
            raise ValueError("feature diagnostic snapshot digest is invalid")
    claimed = payload.get("content_sha256")
    if not isinstance(claimed, str) or not _SHA64.fullmatch(claimed):
        raise ValueError("feature diagnostic report content hash is invalid")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("feature diagnostic report fingerprint mismatch")


__all__ = [
    "ARTIFACT_TYPE",
    "CONTRACT_CONTENT_SHA256",
    "DIAGNOSTIC_CONTRACT_ID",
    "EXECUTION_AUTHORIZATION_ID",
    "FEATURE_CASES",
    "FEATURE_ENGINE_SOURCE_FILE_SHA256",
    "FIXED_HYPOTHETICAL_ORDER_SIZES",
    "MAX_PREFLIGHT_BILLABLE_SIZE_BYTES",
    "MAX_PREFLIGHT_COST_USD",
    "REQUESTS",
    "RuntimeConstants",
    "SAMPLE_INTERVAL_NS",
    "TranslatedAtomicGroup",
    "build_unavailable_report",
    "extract_case_feature_diagnostic",
    "iter_atomic_mbo_groups",
    "load_diagnostic_contract",
    "load_execution_authorization",
    "run_feature_diagnostic",
    "translate_xnas_atomic_group",
    "validate_diagnostic_contract",
    "validate_execution_authorization",
    "validate_feature_diagnostic_report",
]
