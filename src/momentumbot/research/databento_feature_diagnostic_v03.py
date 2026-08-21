from __future__ import annotations

import hashlib
import json
import re
import tempfile
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

from momentumbot.research import databento_feature_diagnostic_v01 as v01
from momentumbot.research import databento_feature_diagnostic_v02 as v02
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
    CausalMicrostructureFeatureEngine,
    FEATURE_SET_CONTENT_SHA256,
)


SCHEMA_VERSION = 1
DIAGNOSTIC_CONTRACT_ID = "databento-microstructure-feature-diagnostic-v0.3"
EXECUTION_AUTHORIZATION_ID = (
    "databento-microstructure-feature-diagnostic-v0.3-execution"
)
ARTIFACT_TYPE = "sanitized_databento_instrument_event_repair_diagnostic"
CONTRACT_CONTENT_SHA256 = (
    "51733fcf3f060e80f928017eb82e410a828a4e31550bb27dcc18bead151fe62c"
)
PARENT_FAILURE_AUDIT_ID = (
    "databento-microstructure-feature-diagnostic-v0.2-"
    "run-32478204001-failure-2026-08-21"
)
PARENT_FAILURE_CONTENT_SHA256 = (
    "2f04264b6b4b68fb24f4920adcf9f09ca3f181186f945a4a3d06e39022516ac3"
)
PARENT_FAILURE_REPORT_CONTENT_SHA256 = (
    "d26ff22373d368fa8c6beaeddf98f79f9e493f57ecacd1de645904860fabdfbb"
)
V01_ADAPTER_FILE_SHA256 = (
    "3c0c5ac0d18ffc3d72c1a18da9758ac33a269e3c074bac35fefb1528a99e1919"
)
V02_CLASSIFIER_FILE_SHA256 = (
    "25b8153a0dfe6dc6ccd62ba947516827ef1e399a2af03b1aabf7dada53327d09"
)
FEATURE_ENGINE_SOURCE_FILE_SHA256 = v01.FEATURE_ENGINE_SOURCE_FILE_SHA256
MAX_PREFLIGHT_COST_USD = Decimal("0.001")
MAX_PREFLIGHT_BILLABLE_SIZE_BYTES = 1_000_000
REQUEST = v01.REQUESTS[0]
REQUESTS = (REQUEST,)
SAMPLE_INTERVAL_NS = v01.SAMPLE_INTERVAL_NS
FIXED_HYPOTHETICAL_ORDER_SIZES = v01.FIXED_HYPOTHETICAL_ORDER_SIZES
SAFE_ERROR_CODES = v02.SAFE_ERROR_CODES
SafeDiagnosticFailure = v02.SafeDiagnosticFailure

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


def _verify_frozen_sources() -> None:
    expected = (
        (Path(str(v01.__file__)), V01_ADAPTER_FILE_SHA256),
        (Path(str(v02.__file__)), V02_CLASSIFIER_FILE_SHA256),
    )
    for path, digest in expected:
        if path.suffix != ".py" or file_sha256(path) != digest:
            raise ValueError("frozen feature diagnostic source changed")
    v01._verify_feature_engine_source()


def validate_parent_failure_audit(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported v0.2 feature failure audit schema")
    if payload.get("audit_id") != PARENT_FAILURE_AUDIT_ID:
        raise ValueError("unexpected v0.2 feature failure audit")
    if payload.get("artifact_type") != (
        "independently_verified_sanitized_databento_safe_failure_classification"
    ):
        raise ValueError("unexpected v0.2 feature failure audit type")
    claimed = payload.get("content_sha256")
    if claimed != PARENT_FAILURE_CONTENT_SHA256:
        raise ValueError("v0.2 feature failure content hash changed")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("v0.2 feature failure fingerprint mismatch")
    actions = _mapping(payload.get("github_actions"), "github_actions")
    expected_actions = {
        "workflow_run_id": 32478204001,
        "workflow_run_attempt": 1,
        "workflow_conclusion": "success",
        "workflow_head_sha": "b5f6db2ebbfdf3dd73a78fe9db978819e97f62c8",
        "workflow_head_tree_sha": "27b7d77837238929783dc366f92001ced377a0b4",
        "artifact_id": 9445082857,
        "artifact_zip_sha256": (
            "c828cb5518f9f647c832f211869d18cc7589b7f0246cb260460d728a5ec69878"
        ),
        "sanitized_report_content_sha256": (
            PARENT_FAILURE_REPORT_CONTENT_SHA256
        ),
    }
    for field, expected in expected_actions.items():
        if actions.get(field) != expected:
            raise ValueError(f"v0.2 github_actions.{field} changed")
    classified = _mapping(payload.get("classified_failure"), "classified_failure")
    expected_classified = {
        "diagnostic_observation_complete": True,
        "safe_failure_classified": True,
        "feature_replay_succeeded": False,
        "failure_phase": "atomic_group",
        "safe_error_code": "atomic_key_change_before_last",
        "exact_failing_guard_identified": True,
    }
    for field, expected in expected_classified.items():
        if classified.get(field) != expected:
            raise ValueError(f"v0.2 classified_failure.{field} changed")
    interpretation = _mapping(
        payload.get("corrective_interpretation"),
        "corrective_interpretation",
    )
    if interpretation.get("policy_promotion_allowed") is not False:
        raise ValueError("v0.2 failure cannot promote policy")


def load_parent_failure_audit(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("v0.2 feature failure audit root must be an object")
    validate_parent_failure_audit(payload)
    return payload


def validate_repair_contract(
    payload: Mapping[str, object],
    *,
    parent_failure_audit: Mapping[str, object],
) -> None:
    validate_parent_failure_audit(parent_failure_audit)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported v0.3 repair contract schema")
    if payload.get("diagnostic_contract_id") != DIAGNOSTIC_CONTRACT_ID:
        raise ValueError("unexpected v0.3 repair contract")
    if payload.get("artifact_type") != (
        "preregistered_unarmed_databento_instrument_event_repair"
    ):
        raise ValueError("unexpected v0.3 repair contract type")
    claimed = payload.get("content_sha256")
    if claimed != CONTRACT_CONTENT_SHA256:
        raise ValueError("v0.3 repair contract content hash changed")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("v0.3 repair contract fingerprint mismatch")
    parent = _mapping(payload.get("frozen_parent_failure"), "frozen_parent_failure")
    expected_parent = {
        "audit_id": PARENT_FAILURE_AUDIT_ID,
        "content_sha256": PARENT_FAILURE_CONTENT_SHA256,
        "workflow_run_id": 32478204001,
        "workflow_run_attempt": 1,
        "sanitized_report_content_sha256": PARENT_FAILURE_REPORT_CONTENT_SHA256,
        "failure_phase": "atomic_group",
        "safe_error_code": "atomic_key_change_before_last",
        "exact_failing_guard_identified": True,
    }
    for field, expected in expected_parent.items():
        if parent.get(field) != expected:
            raise ValueError(f"v0.3 frozen_parent_failure.{field} changed")
    frozen = _mapping(payload.get("frozen_mechanics"), "frozen_mechanics")
    expected_frozen = {
        "v0_1_adapter_file_sha256": V01_ADAPTER_FILE_SHA256,
        "v0_2_classifier_file_sha256": V02_CLASSIFIER_FILE_SHA256,
        "feature_set_content_sha256": FEATURE_SET_CONTENT_SHA256,
        "feature_engine_file_sha256": FEATURE_ENGINE_SOURCE_FILE_SHA256,
        "feature_mechanics_changed": False,
        "feature_windows_or_thresholds_changed": False,
        "strategy_or_broker_behavior_changed": False,
    }
    for field, expected in expected_frozen.items():
        if frozen.get(field) != expected:
            raise ValueError(f"v0.3 frozen_mechanics.{field} changed")
    repair = _mapping(payload.get("registered_repair"), "registered_repair")
    if repair.get("event_scope") != ["publisher_id", "instrument_id"]:
        raise ValueError("v0.3 event scope changed")
    if repair.get("sequence_equality_required_across_entire_f_last_event") is not False:
        raise ValueError("v0.3 must not restore the rejected sequence invariant")
    if repair.get("fill_cancel_match_fields") != [
        "sequence",
        "order_id",
        "side",
        "price",
        "size",
    ]:
        raise ValueError("v0.3 Fill/Cancel identity changed")
    for field in (
        "pending_buffer_per_scope",
        "record_order_within_scope_preserved",
        "sequence_retained_on_every_canonical_event",
        "independent_feature_engine_per_scope",
        "receive_time_reversal_policy_unchanged",
    ):
        if repair.get(field) is not True:
            raise ValueError(f"v0.3 registered_repair.{field} changed")
    gate = _mapping(payload.get("future_execution_gate"), "future_execution_gate")
    expected_gate = {
        "provider_purchase_authorized": False,
        "execution_authorization_file_present": False,
        "new_explicit_user_authorization_required": True,
        "future_authorization_must_bind_published_parent_sha": True,
        "first_github_actions_attempt_only": True,
        "exact_request_count_authorized": 0,
        "hard_preflight_cost_ceiling_usd": "0.001",
        "hard_preflight_billable_size_ceiling_bytes": 1_000_000,
        "automatic_retry_authorized": False,
        "batch_or_live_endpoint_authorized": False,
        "mbp10_redownload_authorized": False,
        "raw_market_data_publication_authorized": False,
        "broker_or_order_change_authorized": False,
        "strategy_or_threshold_change_authorized": False,
    }
    for field, expected in expected_gate.items():
        if gate.get(field) != expected:
            raise ValueError(f"v0.3 future_execution_gate.{field} changed")


def load_repair_contract(
    path: str | Path,
    *,
    parent_failure_audit: Mapping[str, object],
) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("v0.3 repair contract root must be an object")
    validate_repair_contract(payload, parent_failure_audit=parent_failure_audit)
    return payload


def validate_execution_authorization(payload: Mapping[str, object]) -> None:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "execution_authorization_id": EXECUTION_AUTHORIZATION_ID,
        "artifact_type": (
            "explicit_one_shot_databento_instrument_event_repair_authorization"
        ),
        "diagnostic_contract_id": DIAGNOSTIC_CONTRACT_ID,
        "diagnostic_contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "provider_purchase_authorized": True,
        "exact_request_count_authorized": 1,
        "hard_preflight_cost_ceiling_usd": "0.001",
        "hard_preflight_billable_size_ceiling_bytes": 1_000_000,
        "first_github_actions_attempt_only": True,
        "automatic_retry_authorized": False,
        "batch_or_live_endpoint_authorized": False,
        "mbp10_redownload_authorized": False,
        "raw_market_data_publication_authorized": False,
        "broker_or_order_change_authorized": False,
        "strategy_or_threshold_change_authorized": False,
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise ValueError(f"v0.3 execution authorization {field} changed")
    parent_sha = payload.get("authorized_push_parent_sha")
    if not isinstance(parent_sha, str) or not _SHA40.fullmatch(parent_sha):
        raise ValueError("v0.3 authorization parent SHA is invalid")
    statement = payload.get("explicit_user_authorization")
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError("v0.3 explicit user authorization is required")
    claimed = payload.get("content_sha256")
    if not isinstance(claimed, str) or not _SHA64.fullmatch(claimed):
        raise ValueError("v0.3 execution authorization hash is invalid")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("v0.3 execution authorization fingerprint mismatch")


def load_execution_authorization(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("v0.3 execution authorization root must be an object")
    validate_execution_authorization(payload)
    return payload


def _classified(phase: str, code: str, exc: Exception) -> SafeDiagnosticFailure:
    return v02._classified_from_exception(phase=phase, code=code, exc=exc)


def _event_scope(record: object) -> tuple[int, int]:
    try:
        return (
            _integer(getattr(record, "publisher_id"), "publisher_id"),
            _integer(getattr(record, "instrument_id"), "instrument_id"),
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise _classified("record", "record_payload_invalid", exc) from None


def iter_instrument_mbo_events(
    store: Iterable[object],
    *,
    runtime: RuntimeConstants,
) -> Iterator[tuple[object, ...]]:
    pending: dict[tuple[int, int], list[object]] = {}
    previous_ts_recv = -1
    yielded = False
    for record in store:
        if not _has_fields(record, _REQUIRED_MBO_FIELDS):
            raise SafeDiagnosticFailure("record", "required_field_missing")
        try:
            ts_recv = _integer(getattr(record, "ts_recv"), "ts_recv", minimum=1)
            flags = _integer(getattr(record, "flags"), "flags")
        except (AttributeError, TypeError, ValueError) as exc:
            raise _classified("record", "record_payload_invalid", exc) from None
        if ts_recv < previous_ts_recv and not flags & runtime.f_bad_ts_recv:
            raise SafeDiagnosticFailure("record", "receive_time_invalid")
        previous_ts_recv = max(previous_ts_recv, ts_recv)
        scope = _event_scope(record)
        pending.setdefault(scope, []).append(record)
        if flags & runtime.f_last:
            yielded = True
            yield tuple(pending.pop(scope))
    if pending:
        raise SafeDiagnosticFailure("atomic_group", "atomic_eof_before_last")
    if not yielded:
        raise SafeDiagnosticFailure("completion", "stream_empty")


def _book_side(value: str) -> BookSide:
    if value == "B":
        return BookSide.BID
    if value == "A":
        return BookSide.ASK
    if value == "N":
        return BookSide.NONE
    raise SafeDiagnosticFailure("normalize", "unsupported_action_or_side")


def _aggressor_side(value: str) -> AggressorSide:
    if value == "B":
        return AggressorSide.BUY
    if value == "A":
        return AggressorSide.SELL
    if value == "N":
        return AggressorSide.UNKNOWN
    raise SafeDiagnosticFailure("normalize", "unsupported_action_or_side")


def _execution_identity(record: object) -> tuple[int, int, str, int, int]:
    try:
        return (
            _integer(getattr(record, "sequence"), "sequence"),
            _integer(getattr(record, "order_id"), "order_id", minimum=1),
            _char(getattr(record, "side")),
            _integer(getattr(record, "price"), "price", minimum=1),
            _integer(getattr(record, "size"), "size", minimum=1),
        )
    except (AttributeError, TypeError, UnicodeError, ValueError) as exc:
        raise _classified("normalize", "mutation_payload_invalid", exc) from None


def translate_xnas_instrument_event(
    records: Sequence[object],
    *,
    symbol: str,
    runtime: RuntimeConstants,
) -> v01.TranslatedAtomicGroup:
    if not records:
        raise SafeDiagnosticFailure("atomic_group", "atomic_scope_invalid")
    scopes = {_event_scope(record) for record in records}
    if len(scopes) != 1:
        raise SafeDiagnosticFailure("atomic_group", "atomic_scope_invalid")
    try:
        final_flags = _integer(getattr(records[-1], "flags"), "flags")
    except (AttributeError, TypeError, ValueError) as exc:
        raise _classified("record", "record_payload_invalid", exc) from None
    if not final_flags & runtime.f_last:
        raise SafeDiagnosticFailure("atomic_group", "atomic_eof_before_last")

    fills: Counter[tuple[int, int, str, int, int]] = Counter()
    for record in records:
        try:
            action = _char(getattr(record, "action"))
        except (AttributeError, UnicodeError) as exc:
            raise _classified("record", "record_payload_invalid", exc) from None
        if action == "F":
            fills[_execution_identity(record)] += 1

    depth_events: list[CanonicalDepthEvent] = []
    tape_events: list[CanonicalTapeEvent] = []
    ordered_events: list[CanonicalDepthEvent | CanonicalTapeEvent] = []
    action_counts: Counter[str] = Counter()
    matched_fills = 0
    ignored_fill_markers = 0
    ignored_none = 0

    for index, record in enumerate(records):
        try:
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
        except (AttributeError, TypeError, UnicodeError, ValueError) as exc:
            raise _classified("record", "record_payload_invalid", exc) from None
        if action not in {"A", "C", "M", "R", "T", "F", "N"}:
            raise SafeDiagnosticFailure("normalize", "unsupported_action_or_side")
        if side not in {"A", "B", "N"}:
            raise SafeDiagnosticFailure("normalize", "unsupported_action_or_side")
        action_counts[action] += 1
        # Preserve the frozen v0.1 canonical identity for every previously
        # valid single-sequence event. The per-scope F_LAST repair changes the
        # grouping boundary, not the event identity or feature mechanics.
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
        try:
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
            if raw_price == runtime.undef_price or (action == "M" and size == 0):
                raise SafeDiagnosticFailure("normalize", "mutation_payload_invalid")
            canonical_action = {
                "A": DepthAction.ADD,
                "C": DepthAction.CANCEL,
                "M": DepthAction.MODIFY,
            }[action]
            if action == "C":
                identity = (sequence, raw_order_id, side, raw_price, size)
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
        except SafeDiagnosticFailure:
            raise
        except Exception as exc:
            raise _classified(
                "normalize",
                "canonical_event_rejected",
                exc,
            ) from None
    if any(fills.values()):
        raise SafeDiagnosticFailure("normalize", "fill_cancel_unmatched")
    return v01.TranslatedAtomicGroup(
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
            for window in v01.REGISTERED_WINDOWS_NS
        },
    }


def extract_repaired_feature_diagnostic(
    store: Iterable[object],
    *,
    request: QuoteRequest,
    runtime: RuntimeConstants,
) -> dict[str, object]:
    if request != REQUEST:
        raise ValueError("v0.3 repair requires the exact frozen INTJ request")
    engines: dict[
        tuple[int, int],
        tuple[CausalMicrostructureFeatureEngine, CausalMicrostructureFeatureEngine],
    ] = {}
    current_bucket: dict[tuple[int, int], int] = {}
    last_complete_ts_recv: dict[tuple[int, int], int] = {}
    ingested: set[tuple[int, int]] = set()
    digest = hashlib.sha256()
    summary = _snapshot_summary_template()
    action_counts: Counter[str] = Counter()
    record_count = 0
    event_count = 0
    depth_event_count = 0
    tape_event_count = 0
    matched_fill_count = 0
    ignored_fill_count = 0
    ignored_none_count = 0
    within_event_sequence_transition_count = 0

    def sample(scope: tuple[int, int], as_of_ts_recv_ns: int) -> None:
        pair = engines[scope]
        try:
            snapshots = tuple(
                engine.snapshot(
                    as_of_ts_recv_ns=as_of_ts_recv_ns,
                    hypothetical_order_sizes=FIXED_HYPOTHETICAL_ORDER_SIZES,
                )
                for engine in pair
            )
        except Exception as exc:
            raise _classified(
                "feature_snapshot",
                "feature_snapshot_invariant",
                exc,
            ) from None
        if snapshots[0] != snapshots[1]:
            raise SafeDiagnosticFailure(
                "completion",
                "independent_replay_diverged",
            )
        snapshot = snapshots[0]
        if snapshot.get("thresholds_applied") is not False:
            raise SafeDiagnosticFailure("completion", "feature_output_invariant")
        if snapshot.get("runtime_authority") != "none_shadow_only":
            raise SafeDiagnosticFailure("completion", "feature_output_invariant")
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
            raise SafeDiagnosticFailure("completion", "feature_output_invariant")
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
        if not isinstance(windows, list) or len(windows) != len(
            v01.REGISTERED_WINDOWS_NS
        ):
            raise SafeDiagnosticFailure("completion", "feature_output_invariant")
        availability = _mapping(summary["window_availability"], "window availability")
        for row in windows:
            window = _mapping(row, "feature window")
            counter = _mapping(
                availability.get(str(window.get("window_ns"))),
                "window counter",
            )
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
                window.get("breakout_progress_context"),
                "breakout context",
            )
            summary["breakout_context_available_count"] = int(
                summary["breakout_context_available_count"]
            ) + int(breakout.get("available") is True)

    for records in iter_instrument_mbo_events(store, runtime=runtime):
        scope = _event_scope(records[0])
        sequences = [
            _integer(getattr(record, "sequence"), "sequence") for record in records
        ]
        within_event_sequence_transition_count += sum(
            int(left != right) for left, right in zip(sequences, sequences[1:])
        )
        translated = translate_xnas_instrument_event(
            records,
            symbol=request.symbol,
            runtime=runtime,
        )
        pair = engines.setdefault(
            scope,
            (CausalMicrostructureFeatureEngine(), CausalMicrostructureFeatureEngine()),
        )
        bucket = translated.ts_recv_ns // SAMPLE_INTERVAL_NS
        if (
            scope in current_bucket
            and bucket != current_bucket[scope]
            and scope in last_complete_ts_recv
            and scope in ingested
        ):
            sample(scope, last_complete_ts_recv[scope])
        current_bucket[scope] = bucket
        last_complete_ts_recv[scope] = translated.ts_recv_ns
        event_count += 1
        record_count += len(records)
        action_counts.update(translated.action_counts)
        matched_fill_count += translated.matched_executed_removal_count
        ignored_fill_count += translated.ignored_fill_marker_count
        ignored_none_count += translated.ignored_none_count
        depth_event_count += len(translated.depth_events)
        tape_event_count += len(translated.tape_events)
        try:
            for engine in pair:
                for event in translated.ordered_events:
                    if isinstance(event, CanonicalDepthEvent):
                        engine.ingest_depth(event)
                    else:
                        engine.ingest_tape(event)
        except Exception as exc:
            raise _classified("book_replay", "book_state_invariant", exc) from None
        if translated.ordered_events:
            ingested.add(scope)

    for scope in sorted(
        ingested,
        key=lambda item: (last_complete_ts_recv[item], item),
    ):
        sample(scope, last_complete_ts_recv[scope])
    if event_count == 0:
        raise SafeDiagnosticFailure("completion", "stream_empty")
    if int(summary["sampled_snapshot_count"]) == 0:
        raise SafeDiagnosticFailure("completion", "no_complete_snapshot")
    return {
        "record_count": record_count,
        "instrument_event_count": event_count,
        "event_scope_count": len(engines),
        "within_event_sequence_transition_count": (
            within_event_sequence_transition_count
        ),
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
    try:
        kwargs = _request_kwargs(REQUEST)
        size = _integer(client.metadata.get_billable_size(**kwargs), "billable size")
        cost = _decimal(client.metadata.get_cost(**kwargs), "quoted cost")
    except Exception:
        return (
            {
                "request_count_expected": 1,
                "request_count_quoted": 0,
                "quote_rows": [],
                "total_quoted_cost_usd": None,
                "total_billable_size_bytes": None,
                "hard_cost_ceiling_usd": format(MAX_PREFLIGHT_COST_USD, "f"),
                "hard_billable_size_ceiling_bytes": (
                    MAX_PREFLIGHT_BILLABLE_SIZE_BYTES
                ),
                "preflight_passed": False,
            },
            [{"failure_phase": "preflight", "safe_error_code": "preflight_metadata_query_failed"}],
        )
    passed = cost <= MAX_PREFLIGHT_COST_USD and size <= MAX_PREFLIGHT_BILLABLE_SIZE_BYTES
    row: dict[str, object] = REQUEST.mapping()
    row.update({"quoted_cost_usd": format(cost, "f"), "billable_size_bytes": size})
    errors = [] if passed else [
        {"failure_phase": "preflight", "safe_error_code": "preflight_budget_rejected"}
    ]
    return (
        {
            "request_count_expected": 1,
            "request_count_quoted": 1,
            "quote_rows": [row],
            "total_quoted_cost_usd": format(cost, "f"),
            "total_billable_size_bytes": size,
            "hard_cost_ceiling_usd": format(MAX_PREFLIGHT_COST_USD, "f"),
            "hard_billable_size_ceiling_bytes": MAX_PREFLIGHT_BILLABLE_SIZE_BYTES,
            "preflight_passed": passed,
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
        "parent_failure_audit_id": PARENT_FAILURE_AUDIT_ID,
        "parent_failure_audit_content_sha256": PARENT_FAILURE_CONTENT_SHA256,
        "parent_failure_report_content_sha256": PARENT_FAILURE_REPORT_CONTENT_SHA256,
        "v01_adapter_file_sha256": V01_ADAPTER_FILE_SHA256,
        "v02_classifier_file_sha256": V02_CLASSIFIER_FILE_SHA256,
        "feature_engine_source_file_sha256": FEATURE_ENGINE_SOURCE_FILE_SHA256,
        "artifact_type": ARTIFACT_TYPE,
        "generated_at": _iso_z(generated_at),
        "provider": "databento",
        "dataset": DATASET,
        "schema": "mbo",
        "venue": "XNAS",
        "sdk_version": sdk_version,
        "provider_credential_persisted": False,
        "raw_market_data_persisted": False,
        "raw_market_data_uploaded": False,
        "feature_snapshot_values_persisted": False,
        "batch_or_live_endpoint_called": False,
        "automatic_retry_attempted": False,
        "mbp10_redownloaded": False,
        "retrospective_labels_loaded": False,
        "registered_adapter_repair_applied": True,
        "feature_mechanics_changed": False,
        "strategy_or_threshold_change_made": False,
        "broker_or_order_change_made": False,
        "actual_billing_known": False,
        "billing_note": (
            "Preflight quotes are not represented as actual billed charges; "
            "a completed time-series request may be billable."
        ),
    }


def build_unavailable_report(
    contract: Mapping[str, object],
    parent_failure_audit: Mapping[str, object],
    authorization: Mapping[str, object],
    *,
    generated_at: datetime,
    sdk_version: str,
    failure_phase: str,
    safe_error_code: str,
) -> dict[str, object]:
    validate_repair_contract(contract, parent_failure_audit=parent_failure_audit)
    validate_execution_authorization(authorization)
    failure = SafeDiagnosticFailure(failure_phase, safe_error_code)
    report = _base_report(
        authorization=authorization,
        generated_at=generated_at,
        sdk_version=sdk_version,
    )
    report.update(
        {
            "preflight": {
                "request_count_expected": 1,
                "request_count_quoted": 0,
                "quote_rows": [],
                "total_quoted_cost_usd": None,
                "total_billable_size_bytes": None,
                "hard_cost_ceiling_usd": format(MAX_PREFLIGHT_COST_USD, "f"),
                "hard_billable_size_ceiling_bytes": MAX_PREFLIGHT_BILLABLE_SIZE_BYTES,
                "preflight_passed": False,
            },
            "timeseries_request_count": 0,
            "downloads": [],
            "errors": [failure.mapping()],
            "raw_temp_directory_empty_before_cleanup": True,
            "raw_temp_directory_removed": True,
            "diagnostic_observation_complete": False,
            "feature_replay_succeeded": False,
            "safe_failure_classified": True,
            "runtime_authority_created": False,
            "policy_promotion_eligible": False,
        }
    )
    return _finish_report(report)


def _download_and_replay(
    client: HistoricalClient,
    path: Path,
    runtime: RuntimeConstants,
) -> dict[str, object]:
    try:
        store = client.timeseries.get_range(path=str(path), **_request_kwargs(REQUEST))
    except Exception:
        raise SafeDiagnosticFailure("provider_download", "provider_download_failed") from None
    try:
        file_nonempty = path.is_file() and path.stat().st_size > 0
    except OSError as exc:
        raise _classified("downloaded_file", "download_empty", exc) from None
    if not file_nonempty:
        raise SafeDiagnosticFailure("downloaded_file", "download_empty")
    try:
        dataset = _metadata_value(getattr(store, "metadata", None), "dataset")
        schema = _metadata_value(getattr(store, "metadata", None), "schema")
    except Exception as exc:
        raise _classified("metadata", "metadata_mismatch", exc) from None
    if dataset != DATASET.lower() or schema != "mbo":
        raise SafeDiagnosticFailure("metadata", "metadata_mismatch")
    metrics = extract_repaired_feature_diagnostic(
        store,
        request=REQUEST,
        runtime=runtime,
    )
    return {
        "trading_date": REQUEST.trading_date,
        "symbol": REQUEST.symbol,
        "schema": REQUEST.schema,
        "ephemeral_file_sha256": file_sha256(path),
        "file_nonempty": True,
        "metadata_matches_request": True,
        "metrics": metrics,
    }


def run_instrument_event_repair_diagnostic(
    contract: Mapping[str, object],
    parent_failure_audit: Mapping[str, object],
    authorization: Mapping[str, object],
    client: HistoricalClient,
    *,
    generated_at: datetime,
    sdk_version: str,
    runtime: RuntimeConstants,
) -> dict[str, object]:
    validate_repair_contract(contract, parent_failure_audit=parent_failure_audit)
    validate_execution_authorization(authorization)
    _verify_frozen_sources()
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
                "diagnostic_observation_complete": False,
                "feature_replay_succeeded": False,
                "safe_failure_classified": bool(errors),
                "runtime_authority_created": False,
                "policy_promotion_eligible": False,
            }
        )
        return _finish_report(report)

    temp = tempfile.TemporaryDirectory(prefix="momentumbot-databento-features-v03-")
    temp_path = Path(temp.name)
    path = temp_path / "request-00.dbn.zst"
    try:
        try:
            report["timeseries_request_count"] = 1
            report["downloads"].append(_download_and_replay(client, path, runtime))
        except SafeDiagnosticFailure as exc:
            errors.append(exc.mapping())
        except Exception as exc:
            errors.append(
                _classified(
                    "completion",
                    "unclassified_fail_closed",
                    exc,
                ).mapping()
            )
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
    observation_complete = (
        report["timeseries_request_count"] == 1
        and report["raw_temp_directory_empty_before_cleanup"] is True
        and report["raw_temp_directory_removed"] is True
        and (
            (len(downloads) == 1 and not errors)
            or (not downloads and len(errors) == 1)
        )
    )
    report.update(
        {
            "diagnostic_observation_complete": observation_complete,
            "feature_replay_succeeded": len(downloads) == 1 and not errors,
            "safe_failure_classified": bool(errors)
            and all(
                isinstance(row, Mapping)
                and row.get("safe_error_code") in SAFE_ERROR_CODES
                for row in errors
            ),
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


def validate_repair_report(payload: Mapping[str, object]) -> None:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "diagnostic_contract_id": DIAGNOSTIC_CONTRACT_ID,
        "diagnostic_contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "artifact_type": ARTIFACT_TYPE,
        "parent_failure_audit_content_sha256": PARENT_FAILURE_CONTENT_SHA256,
        "parent_failure_report_content_sha256": PARENT_FAILURE_REPORT_CONTENT_SHA256,
        "v01_adapter_file_sha256": V01_ADAPTER_FILE_SHA256,
        "v02_classifier_file_sha256": V02_CLASSIFIER_FILE_SHA256,
        "feature_engine_source_file_sha256": FEATURE_ENGINE_SOURCE_FILE_SHA256,
        "registered_adapter_repair_applied": True,
        "feature_mechanics_changed": False,
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise ValueError(f"v0.3 repair report {field} changed")
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
            raise ValueError(f"v0.3 repair report {field} must remain false")
    request_count = int(payload.get("timeseries_request_count", 0))
    if request_count not in {0, 1}:
        raise ValueError("v0.3 repair request count exceeded one")
    if payload.get("raw_temp_directory_empty_before_cleanup") is not True:
        raise ValueError("v0.3 temporary directory was not empty")
    if payload.get("raw_temp_directory_removed") is not True:
        raise ValueError("v0.3 temporary directory was not removed")
    forbidden_keys = {
        "raw_records",
        "record_values",
        "order_id",
        "instrument_id",
        "publisher_id",
        "price",
        "size",
        "levels",
        "feature_snapshots",
        "temporary_path",
        "provider_error_message",
        "exception_message",
        "error_message",
        "error_signature_sha256",
        "record_index",
        "ross_action",
        "ross_label",
        "pnl",
        "later_price",
    }
    if set(_walk_keys(payload)) & forbidden_keys:
        raise ValueError("v0.3 repair report contains a prohibited field")
    errors = payload.get("errors")
    if not isinstance(errors, list) or len(errors) > 1:
        raise ValueError("v0.3 repair errors must be a list")
    for row in errors:
        if not isinstance(row, Mapping):
            raise ValueError("v0.3 repair failure row must be an object")
        if set(row) - {"failure_phase", "safe_error_code", "exception_kind"}:
            raise ValueError("v0.3 repair failure row contains an unregistered field")
        if row.get("failure_phase") not in {
            "authorization",
            "credential",
            "sdk",
            "preflight",
            "provider_download",
            "downloaded_file",
            "metadata",
            "record",
            "atomic_group",
            "normalize",
            "book_replay",
            "feature_snapshot",
            "completion",
        }:
            raise ValueError("v0.3 repair failure phase is not allowlisted")
        if row.get("safe_error_code") not in SAFE_ERROR_CODES:
            raise ValueError("v0.3 repair failure code is not allowlisted")
        if row.get("exception_kind") not in {
            None,
            "AttributeError",
            "Exception",
            "OSError",
            "RuntimeError",
            "TypeError",
            "UnicodeError",
            "ValueError",
        }:
            raise ValueError("v0.3 repair exception kind is not allowlisted")
    downloads = payload.get("downloads")
    if not isinstance(downloads, list) or len(downloads) > 1:
        raise ValueError("v0.3 repair downloads must contain at most one row")
    replay_succeeded = payload.get("feature_replay_succeeded") is True
    classified = payload.get("safe_failure_classified") is True
    if replay_succeeded == classified:
        raise ValueError("v0.3 report must record exactly one terminal outcome")
    if replay_succeeded:
        if request_count != 1 or len(downloads) != 1 or errors:
            raise ValueError("successful v0.3 repair report is inconsistent")
        metrics = _mapping(downloads[0].get("metrics"), "v0.3 metrics")
        if metrics.get("independent_feature_replay_exact") is not True:
            raise ValueError("v0.3 independent replay must remain exact")
        for field in (
            "feature_threshold_selected",
            "feature_horizon_selected",
            "runtime_authority_created",
        ):
            if metrics.get(field) is not False:
                raise ValueError(f"v0.3 metrics {field} must remain false")
    elif len(errors) != 1 or downloads:
        raise ValueError("classified v0.3 repair report is inconsistent")
    claimed = payload.get("content_sha256")
    if not isinstance(claimed, str) or not _SHA64.fullmatch(claimed):
        raise ValueError("v0.3 repair report content hash is invalid")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("v0.3 repair report fingerprint mismatch")


__all__ = [
    "ARTIFACT_TYPE",
    "CONTRACT_CONTENT_SHA256",
    "DIAGNOSTIC_CONTRACT_ID",
    "EXECUTION_AUTHORIZATION_ID",
    "FEATURE_ENGINE_SOURCE_FILE_SHA256",
    "MAX_PREFLIGHT_BILLABLE_SIZE_BYTES",
    "MAX_PREFLIGHT_COST_USD",
    "PARENT_FAILURE_AUDIT_ID",
    "PARENT_FAILURE_CONTENT_SHA256",
    "REQUEST",
    "REQUESTS",
    "RuntimeConstants",
    "SAFE_ERROR_CODES",
    "SafeDiagnosticFailure",
    "build_unavailable_report",
    "extract_repaired_feature_diagnostic",
    "iter_instrument_mbo_events",
    "load_execution_authorization",
    "load_parent_failure_audit",
    "load_repair_contract",
    "run_instrument_event_repair_diagnostic",
    "translate_xnas_instrument_event",
    "validate_execution_authorization",
    "validate_parent_failure_audit",
    "validate_repair_contract",
    "validate_repair_report",
]
