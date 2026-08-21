from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from momentumbot.research import databento_feature_diagnostic_v01 as v01
from momentumbot.research import databento_feature_diagnostic_v03 as v03
from momentumbot.research.databento_quote import DATASET
from momentumbot.research.databento_smoke import RuntimeConstants, _char, _integer
from momentumbot.research.microstructure_contract import (
    BookSide,
    CanonicalDepthEvent,
    CanonicalTapeEvent,
    DepthAction,
    canonical_fingerprint,
    file_sha256,
)


SCHEMA_VERSION = 1
REPAIR_CONTRACT_ID = "databento-microstructure-fill-cancel-repair-v0.1"
ARTIFACT_TYPE = "preregistered_unarmed_databento_fill_cancel_identity_repair"
REPAIR_CONTRACT_CONTENT_SHA256 = (
    "a5e8e0381e893610b641ce9a41d31138c1bde2134614efe7ebce725383b6abf0"
)
PARENT_SUCCESS_AUDIT_ID = (
    "databento-microstructure-fill-cancel-classifier-v0.1-"
    "run-32512602607-success-2026-08-21"
)
PARENT_SUCCESS_CONTENT_SHA256 = (
    "a1a4b72301f78b6c06811d810a15ecd830559d5db52dc9187ae00d8973fc983f"
)
PARENT_REPORT_CONTENT_SHA256 = (
    "ef79553321d9746ed6393ae77501dbacd71fcff1d5416842dab7da598d93b7b6"
)
V03_SOURCE_FILE_SHA256 = (
    "0a5e704c6a77483cbe051ce56fee77b273dbb9894bde3a4e299a510de6249340"
)
CLASSIFIER_SOURCE_FILE_SHA256 = (
    "0b8e3d258a7bc5ca90efbd7ef1e1011a5e281678c974b6dde43ca25fd405e14d"
)
CLASSIFIER_CONTRACT_CONTENT_SHA256 = (
    "88a7373d70bacbad2418d900abc0fcce45e3f927d54a88275091bed05c9e44c0"
)


@dataclass(frozen=True)
class FillCancelPairingPlan:
    matched_cancel_indexes: tuple[int, ...]
    fill_marker_count: int
    cancel_record_count: int
    exact_match_count: int
    coarse_only_match_count: int
    extra_cancel_count: int


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _verify_frozen_sources() -> None:
    expected = (
        (Path(str(v03.__file__)), V03_SOURCE_FILE_SHA256),
        (
            Path(str(v03.__file__)).with_name(
                "databento_fill_cancel_classifier_v01.py"
            ),
            CLASSIFIER_SOURCE_FILE_SHA256,
        ),
    )
    for path, digest in expected:
        if path.suffix != ".py" or file_sha256(path) != digest:
            raise ValueError("frozen Fill/Cancel evidence source changed")


def validate_parent_success_audit(payload: Mapping[str, object]) -> None:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "audit_id": PARENT_SUCCESS_AUDIT_ID,
        "artifact_type": (
            "independently_verified_sanitized_databento_"
            "fill_cancel_classifier_success"
        ),
        "content_sha256": PARENT_SUCCESS_CONTENT_SHA256,
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise ValueError(f"Fill/Cancel success audit {field} changed")
    unsigned = {
        key: value for key, value in payload.items() if key != "content_sha256"
    }
    if canonical_fingerprint(unsigned) != PARENT_SUCCESS_CONTENT_SHA256:
        raise ValueError("Fill/Cancel success audit fingerprint mismatch")

    actions = _mapping(payload.get("github_actions"), "github_actions")
    expected_actions = {
        "workflow_run_id": 32512602607,
        "workflow_run_attempt": 1,
        "workflow_conclusion": "success",
        "workflow_head_sha": "2ea5ffb6925fb8f045c6980eae5d0fec668ad1f2",
        "workflow_parent_sha": "8ac472cdae517011fe367f70eba38087e085dbd8",
        "sanitized_report_content_sha256": PARENT_REPORT_CONTENT_SHA256,
    }
    for field, expected_value in expected_actions.items():
        if actions.get(field) != expected_value:
            raise ValueError(f"Fill/Cancel success github_actions.{field} changed")

    result = _mapping(
        payload.get("verified_classifier_result"),
        "verified_classifier_result",
    )
    expected_result = {
        "diagnostic_observation_complete": True,
        "classifier_succeeded": True,
        "instrument_event_count": 29_159,
        "fill_bearing_event_count": 1_020,
        "fill_record_count": 1_346,
        "cancel_record_count_in_fill_bearing_events": 1_382,
    }
    for field, expected_value in expected_result.items():
        if result.get(field) != expected_value:
            raise ValueError(f"Fill/Cancel success result {field} changed")
    overlap = _mapping(
        result.get("projection_overlap_counts"),
        "projection_overlap_counts",
    )
    full = _mapping(
        result.get("projection_full_match_event_counts"),
        "projection_full_match_event_counts",
    )
    if overlap.get("exact") != 1_331 or overlap.get("order_id_and_side") != 1_346:
        raise ValueError("Fill/Cancel success overlap evidence changed")
    if full.get("exact") != 1_007 or full.get("order_id_and_side") != 1_020:
        raise ValueError("Fill/Cancel success event evidence changed")
    interpretation = _mapping(
        payload.get("repair_interpretation"),
        "repair_interpretation",
    )
    if interpretation.get("coarse_only_match_fill_record_count") != 15:
        raise ValueError("Fill/Cancel coarse-only record count changed")
    if interpretation.get("coarse_only_full_match_event_count") != 13:
        raise ValueError("Fill/Cancel coarse-only event count changed")
    if interpretation.get("policy_promotion_allowed") is not False:
        raise ValueError("Fill/Cancel engineering evidence cannot promote policy")


def load_parent_success_audit(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Fill/Cancel success audit root must be an object")
    validate_parent_success_audit(payload)
    return payload


def validate_repair_contract(
    payload: Mapping[str, object],
    *,
    parent_success_audit: Mapping[str, object],
) -> None:
    validate_parent_success_audit(parent_success_audit)
    expected = {
        "schema_version": SCHEMA_VERSION,
        "repair_contract_id": REPAIR_CONTRACT_ID,
        "artifact_type": ARTIFACT_TYPE,
        "runtime_strategy_effect": "none",
        "policy_promotion_eligible": False,
        "profitability_claim_eligible": False,
        "provider_purchase_authorized": False,
        "execution_authorization_file_present": False,
        "content_sha256": REPAIR_CONTRACT_CONTENT_SHA256,
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise ValueError(f"Fill/Cancel repair contract {field} changed")
    unsigned = {
        key: value for key, value in payload.items() if key != "content_sha256"
    }
    if canonical_fingerprint(unsigned) != REPAIR_CONTRACT_CONTENT_SHA256:
        raise ValueError("Fill/Cancel repair contract fingerprint mismatch")

    parent = _mapping(payload.get("frozen_parent_success"), "frozen_parent_success")
    expected_parent = {
        "audit_id": PARENT_SUCCESS_AUDIT_ID,
        "content_sha256": PARENT_SUCCESS_CONTENT_SHA256,
        "workflow_run_id": 32512602607,
        "workflow_run_attempt": 1,
        "sanitized_report_content_sha256": PARENT_REPORT_CONTENT_SHA256,
        "exact_match_fill_record_count": 1_331,
        "coarse_only_match_fill_record_count": 15,
        "exact_full_match_event_count": 1_007,
        "coarse_only_full_match_event_count": 13,
    }
    for field, expected_value in expected_parent.items():
        if parent.get(field) != expected_value:
            raise ValueError(f"Fill/Cancel repair parent {field} changed")

    frozen = _mapping(payload.get("frozen_mechanics"), "frozen_mechanics")
    expected_frozen = {
        "v0_3_instrument_event_source_file_sha256": V03_SOURCE_FILE_SHA256,
        "classifier_source_file_sha256": CLASSIFIER_SOURCE_FILE_SHA256,
        "classifier_contract_content_sha256": CLASSIFIER_CONTRACT_CONTENT_SHA256,
        "event_grouping_changed": False,
        "feature_mechanics_changed": False,
        "feature_windows_or_thresholds_changed": False,
        "strategy_or_broker_behavior_changed": False,
    }
    for field, expected_value in expected_frozen.items():
        if frozen.get(field) != expected_value:
            raise ValueError(f"Fill/Cancel frozen_mechanics.{field} changed")

    repair = _mapping(payload.get("registered_repair"), "registered_repair")
    expected_repair = {
        "event_scope": ["publisher_id", "instrument_id"],
        "event_boundary": "F_LAST",
        "fill_cancel_match_fields": ["order_id", "side"],
        "exact_five_field_match_preferred": True,
        "multiset_counts_preserved": True,
        "deterministic_cancel_selection": (
            "stable_record_order_after_maximizing_exact_five_field_matches"
        ),
        "fill_marker_book_effect": "none",
        "matched_cancel_canonical_action": "fill",
        "canonical_removal_payload_source": "matched_cancel_record",
        "extra_cancel_canonical_action": "cancel",
        "unmatched_fill_policy": "fail_closed",
        "raw_mismatch_values_persisted": False,
        "feature_values_persisted": False,
        "runtime_authority_created": False,
    }
    for field, expected_value in expected_repair.items():
        if repair.get(field) != expected_value:
            raise ValueError(f"Fill/Cancel registered_repair.{field} changed")

    gate = _mapping(payload.get("future_execution_gate"), "future_execution_gate")
    if gate.get("exact_request_count_authorized") != 0:
        raise ValueError("Fill/Cancel repair cannot authorize a provider request")
    for field in (
        "automatic_retry_authorized",
        "batch_or_live_endpoint_authorized",
        "raw_market_data_publication_authorized",
        "broker_or_order_change_authorized",
        "strategy_or_threshold_change_authorized",
    ):
        if gate.get(field) is not False:
            raise ValueError(f"Fill/Cancel repair gate {field} changed")
    _verify_frozen_sources()


def load_repair_contract(
    path: str | Path,
    *,
    parent_success_audit: Mapping[str, object],
) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Fill/Cancel repair contract root must be an object")
    validate_repair_contract(payload, parent_success_audit=parent_success_audit)
    return payload


def _coarse_identity(identity: tuple[int, int, str, int, int]) -> tuple[int, str]:
    return identity[1], identity[2]


def build_fill_cancel_pairing(
    records: Sequence[object],
) -> FillCancelPairingPlan:
    """Match event-local Fill markers to Cancel records without exposing values."""
    fills_exact: Counter[tuple[int, int, str, int, int]] = Counter()
    fills_coarse: Counter[tuple[int, str]] = Counter()
    cancel_rows: list[
        tuple[int, tuple[int, int, str, int, int], tuple[int, str]]
    ] = []

    for index, record in enumerate(records):
        try:
            action = _char(getattr(record, "action"))
        except (AttributeError, UnicodeError) as exc:
            raise v03._classified("record", "record_payload_invalid", exc) from None
        if action not in {"F", "C"}:
            continue
        identity = v03._execution_identity(record)
        coarse = _coarse_identity(identity)
        if action == "F":
            fills_exact[identity] += 1
            fills_coarse[coarse] += 1
        else:
            cancel_rows.append((index, identity, coarse))

    remaining_exact = fills_exact.copy()
    remaining_coarse = fills_coarse.copy()
    matched: set[int] = set()
    exact_match_count = 0

    # Maximize already-valid exact matches first so the repair is a strict
    # extension of the frozen five-field behavior.
    for index, identity, coarse in cancel_rows:
        if remaining_exact[identity] <= 0:
            continue
        remaining_exact[identity] -= 1
        remaining_coarse[coarse] -= 1
        matched.add(index)
        exact_match_count += 1

    coarse_only_match_count = 0
    for index, _identity, coarse in cancel_rows:
        if index in matched or remaining_coarse[coarse] <= 0:
            continue
        remaining_coarse[coarse] -= 1
        matched.add(index)
        coarse_only_match_count += 1

    if any(remaining_coarse.values()):
        raise v03.SafeDiagnosticFailure("normalize", "fill_cancel_unmatched")

    return FillCancelPairingPlan(
        matched_cancel_indexes=tuple(sorted(matched)),
        fill_marker_count=sum(fills_coarse.values()),
        cancel_record_count=len(cancel_rows),
        exact_match_count=exact_match_count,
        coarse_only_match_count=coarse_only_match_count,
        extra_cancel_count=len(cancel_rows) - len(matched),
    )


def translate_xnas_instrument_event(
    records: Sequence[object],
    *,
    symbol: str,
    runtime: RuntimeConstants,
) -> v01.TranslatedAtomicGroup:
    """Translate one completed XNAS event with the registered repair only."""
    if not records:
        raise v03.SafeDiagnosticFailure("atomic_group", "atomic_scope_invalid")
    scopes = {v03._event_scope(record) for record in records}
    if len(scopes) != 1:
        raise v03.SafeDiagnosticFailure("atomic_group", "atomic_scope_invalid")
    try:
        final_flags = _integer(getattr(records[-1], "flags"), "flags")
    except (AttributeError, TypeError, ValueError) as exc:
        raise v03._classified("record", "record_payload_invalid", exc) from None
    if not final_flags & runtime.f_last:
        raise v03.SafeDiagnosticFailure("atomic_group", "atomic_eof_before_last")

    pairing = build_fill_cancel_pairing(records)
    matched_cancel_indexes = set(pairing.matched_cancel_indexes)
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
            raise v03._classified("record", "record_payload_invalid", exc) from None
        if action not in {"A", "C", "M", "R", "T", "F", "N"}:
            raise v03.SafeDiagnosticFailure(
                "normalize", "unsupported_action_or_side"
            )
        if side not in {"A", "B", "N"}:
            raise v03.SafeDiagnosticFailure(
                "normalize", "unsupported_action_or_side"
            )
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
                        "aggressor_side": v03._aggressor_side(side).value,
                        "correction_or_cancel": False,
                    }
                )
                depth_events.append(depth_event)
                tape_events.append(tape_event)
                ordered_events.extend((depth_event, tape_event))
                continue
            if raw_price == runtime.undef_price or (action == "M" and size == 0):
                raise v03.SafeDiagnosticFailure(
                    "normalize", "mutation_payload_invalid"
                )
            canonical_action = {
                "A": DepthAction.ADD,
                "C": DepthAction.CANCEL,
                "M": DepthAction.MODIFY,
            }[action]
            if action == "C" and index in matched_cancel_indexes:
                canonical_action = DepthAction.FILL
                matched_fills += 1
            event = CanonicalDepthEvent.from_mapping(
                {
                    **common,
                    "action": canonical_action.value,
                    "side": v03._book_side(side).value,
                    "price_nanos": raw_price,
                    "size": size,
                    "order_id": raw_order_id,
                }
            )
            depth_events.append(event)
            ordered_events.append(event)
        except v03.SafeDiagnosticFailure:
            raise
        except Exception as exc:
            raise v03._classified(
                "normalize", "canonical_event_rejected", exc
            ) from None

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


__all__ = [
    "ARTIFACT_TYPE",
    "FillCancelPairingPlan",
    "PARENT_SUCCESS_AUDIT_ID",
    "PARENT_SUCCESS_CONTENT_SHA256",
    "REPAIR_CONTRACT_CONTENT_SHA256",
    "REPAIR_CONTRACT_ID",
    "build_fill_cancel_pairing",
    "load_parent_success_audit",
    "load_repair_contract",
    "translate_xnas_instrument_event",
    "validate_parent_success_audit",
    "validate_repair_contract",
]
