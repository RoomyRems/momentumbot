from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping

from momentumbot.research import databento_feature_diagnostic_v03 as v03
from momentumbot.research.databento_quote import QuoteRequest
from momentumbot.research.databento_smoke import RuntimeConstants, _char, _integer
from momentumbot.research.microstructure_contract import canonical_fingerprint


SCHEMA_VERSION = 1
CLASSIFIER_CONTRACT_ID = (
    "databento-microstructure-fill-cancel-classifier-v0.1"
)
ARTIFACT_TYPE = (
    "preregistered_unarmed_databento_fill_cancel_structure_classifier"
)
CONTRACT_CONTENT_SHA256 = (
    "88a7373d70bacbad2418d900abc0fcce45e3f927d54a88275091bed05c9e44c0"
)
PARENT_FAILURE_AUDIT_ID = (
    "databento-microstructure-feature-coverage-v0.1-"
    "run-32501827997-safe-failure-2026-08-21"
)
PARENT_FAILURE_CONTENT_SHA256 = (
    "10b8d05287947a3d334b7a0dda26f89549501287bb58fd7d4a06f6db3ebb5bad"
)
PARENT_REPORT_CONTENT_SHA256 = (
    "1322a2707549f6133dc2dc973abd8ca329f4aa42babe7168020e96efe483ce10"
)
REQUEST = QuoteRequest(
    trading_date="2026-07-10",
    symbol="EQPT",
    dataset="XNAS.ITCH",
    schema="mbo",
    start="2026-07-10T00:00:00Z",
    end="2026-07-10T14:10:00Z",
    stype_in="raw_symbol",
)

_PROJECTION_FIELDS = (
    ("sequence", "order_id", "side", "price", "size"),
    ("order_id", "side", "price", "size"),
    ("sequence", "order_id", "side", "price"),
    ("order_id", "side", "price"),
    ("order_id", "side"),
    ("order_id",),
)
_PROJECTION_INDEXES = {
    "exact": (0, 1, 2, 3, 4),
    "without_sequence": (1, 2, 3, 4),
    "without_size": (0, 1, 2, 3),
    "without_sequence_and_size": (1, 2, 3),
    "order_id_and_side": (1, 2),
    "order_id_only": (1,),
}
_REGISTERED_OUTPUTS = (
    "instrument_event_count",
    "fill_bearing_event_count",
    "fill_record_count",
    "cancel_record_count_in_fill_bearing_events",
    "fill_last_record_count",
    "fill_event_without_cancel_count",
    "multi_sequence_fill_event_count",
    "projection_overlap_counts",
    "projection_full_match_event_counts",
)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def validate_parent_failure_audit(payload: Mapping[str, object]) -> None:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "audit_id": PARENT_FAILURE_AUDIT_ID,
        "artifact_type": (
            "independently_verified_sanitized_databento_feature_coverage_"
            "safe_failure"
        ),
        "content_sha256": PARENT_FAILURE_CONTENT_SHA256,
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise ValueError(f"parent failure audit {field} changed")
    unsigned = {
        key: value for key, value in payload.items() if key != "content_sha256"
    }
    if canonical_fingerprint(unsigned) != PARENT_FAILURE_CONTENT_SHA256:
        raise ValueError("parent failure audit fingerprint mismatch")

    actions = _mapping(payload.get("github_actions"), "github_actions")
    expected_actions = {
        "workflow_run_id": 32501827997,
        "workflow_run_attempt": 1,
        "workflow_conclusion": "success",
        "workflow_head_sha": "53aef4f3858f182529bd22b361c23d1d7f059d26",
        "artifact_id": 9453800579,
        "sanitized_report_content_sha256": PARENT_REPORT_CONTENT_SHA256,
    }
    for field, expected_value in expected_actions.items():
        if actions.get(field) != expected_value:
            raise ValueError(f"parent github_actions.{field} changed")

    attempt = _mapping(
        payload.get("verified_preflight_and_attempt"),
        "verified_preflight_and_attempt",
    )
    expected_attempt = {
        "timeseries_request_count": 1,
        "successful_download_summary_count": 0,
        "automatic_retry_attempted": False,
        "first_attempt_only_observed": True,
    }
    for field, expected_value in expected_attempt.items():
        if attempt.get(field) != expected_value:
            raise ValueError(f"parent verified_preflight_and_attempt.{field} changed")

    failure = _mapping(payload.get("classified_failure"), "classified_failure")
    expected_failure = {
        "diagnostic_observation_complete": True,
        "safe_failure_classified": True,
        "all_cases_succeeded": False,
        "failure_phase": "normalize",
        "safe_error_code": "fill_cancel_unmatched",
        "exact_failing_guard_identified": True,
    }
    for field, expected_value in expected_failure.items():
        if failure.get(field) != expected_value:
            raise ValueError(f"parent classified_failure.{field} changed")

    safety = _mapping(payload.get("safety_verification"), "safety_verification")
    for field in (
        "provider_credential_persisted",
        "raw_market_data_persisted",
        "raw_market_data_uploaded",
        "feature_snapshot_values_persisted",
        "runtime_authority_created",
        "broker_or_order_change_made",
        "strategy_or_threshold_change_made",
    ):
        if safety.get(field) is not False:
            raise ValueError(f"parent safety_verification.{field} changed")


def load_parent_failure_audit(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("parent failure audit root must be an object")
    validate_parent_failure_audit(payload)
    return payload


def validate_classifier_contract(
    payload: Mapping[str, object],
    *,
    parent_failure_audit: Mapping[str, object],
) -> None:
    validate_parent_failure_audit(parent_failure_audit)
    expected = {
        "schema_version": SCHEMA_VERSION,
        "classifier_contract_id": CLASSIFIER_CONTRACT_ID,
        "artifact_type": ARTIFACT_TYPE,
        "runtime_strategy_effect": "none",
        "policy_promotion_eligible": False,
        "profitability_claim_eligible": False,
        "provider_purchase_authorized": False,
        "execution_authorization_file_present": False,
        "content_sha256": CONTRACT_CONTENT_SHA256,
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise ValueError(f"classifier contract {field} changed")
    unsigned = {
        key: value for key, value in payload.items() if key != "content_sha256"
    }
    if canonical_fingerprint(unsigned) != CONTRACT_CONTENT_SHA256:
        raise ValueError("classifier contract fingerprint mismatch")

    parent = _mapping(payload.get("frozen_parent_failure"), "frozen_parent_failure")
    expected_parent = {
        "audit_id": PARENT_FAILURE_AUDIT_ID,
        "content_sha256": PARENT_FAILURE_CONTENT_SHA256,
        "workflow_run_id": 32501827997,
        "workflow_run_attempt": 1,
        "sanitized_report_content_sha256": PARENT_REPORT_CONTENT_SHA256,
        "failure_phase": "normalize",
        "safe_error_code": "fill_cancel_unmatched",
    }
    for field, expected_value in expected_parent.items():
        if parent.get(field) != expected_value:
            raise ValueError(f"classifier frozen_parent_failure.{field} changed")

    frozen_request = _mapping(payload.get("frozen_request"), "frozen_request")
    for field, expected_value in REQUEST.mapping().items():
        if frozen_request.get(field) != expected_value:
            raise ValueError(f"classifier frozen_request.{field} changed")
    if frozen_request.get("observed_quote_usd") != "0.002689146996":
        raise ValueError("classifier observed EQPT quote changed")
    if frozen_request.get("observed_billable_size_bytes") != 2_406_208:
        raise ValueError("classifier observed EQPT billable size changed")

    if payload.get("registered_identity_projections") != [
        list(fields) for fields in _PROJECTION_FIELDS
    ]:
        raise ValueError("classifier identity projections changed")
    if payload.get("registered_aggregate_outputs") != list(_REGISTERED_OUTPUTS):
        raise ValueError("classifier aggregate outputs changed")

    gate = _mapping(payload.get("future_execution_gate"), "future_execution_gate")
    expected_gate = {
        "new_explicit_user_authorization_required": True,
        "future_authorization_must_bind_published_parent_sha": True,
        "authorization_only_direct_child_required": True,
        "first_github_actions_attempt_only": True,
        "exact_request_count_authorized": 0,
        "hard_preflight_cost_ceiling_usd": "0.003",
        "hard_preflight_billable_size_ceiling_bytes": 3_000_000,
        "automatic_retry_authorized": False,
        "batch_or_live_endpoint_authorized": False,
        "raw_market_data_publication_authorized": False,
        "broker_or_order_change_authorized": False,
        "strategy_or_threshold_change_authorized": False,
    }
    for field, expected_value in expected_gate.items():
        if gate.get(field) != expected_value:
            raise ValueError(f"classifier future_execution_gate.{field} changed")


def load_classifier_contract(
    path: str | Path,
    *,
    parent_failure_audit: Mapping[str, object],
) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("classifier contract root must be an object")
    validate_classifier_contract(payload, parent_failure_audit=parent_failure_audit)
    return payload


def _projection(
    identity: tuple[int, int, str, int, int],
    indexes: tuple[int, ...],
) -> tuple[object, ...]:
    return tuple(identity[index] for index in indexes)


def classify_fill_cancel_structure(
    store: Iterable[object],
    *,
    request: QuoteRequest,
    runtime: RuntimeConstants,
) -> dict[str, object]:
    if request != REQUEST:
        raise ValueError("classifier requires the exact frozen EQPT request")

    result: dict[str, object] = {
        "instrument_event_count": 0,
        "fill_bearing_event_count": 0,
        "fill_record_count": 0,
        "cancel_record_count_in_fill_bearing_events": 0,
        "fill_last_record_count": 0,
        "fill_event_without_cancel_count": 0,
        "multi_sequence_fill_event_count": 0,
        "projection_overlap_counts": {
            name: 0 for name in _PROJECTION_INDEXES
        },
        "projection_full_match_event_counts": {
            name: 0 for name in _PROJECTION_INDEXES
        },
    }
    overlap_counts = result["projection_overlap_counts"]
    full_match_counts = result["projection_full_match_event_counts"]
    assert isinstance(overlap_counts, dict)
    assert isinstance(full_match_counts, dict)

    for records in v03.iter_instrument_mbo_events(store, runtime=runtime):
        result["instrument_event_count"] += 1
        actions = tuple(_char(getattr(record, "action")) for record in records)
        fill_records = tuple(
            record for record, action in zip(records, actions) if action == "F"
        )
        if not fill_records:
            continue
        cancel_records = tuple(
            record for record, action in zip(records, actions) if action == "C"
        )
        result["fill_bearing_event_count"] += 1
        result["fill_record_count"] += len(fill_records)
        result["cancel_record_count_in_fill_bearing_events"] += len(cancel_records)
        result["fill_last_record_count"] += sum(
            bool(_integer(getattr(record, "flags"), "flags") & runtime.f_last)
            for record in fill_records
        )
        if not cancel_records:
            result["fill_event_without_cancel_count"] += 1
        sequences = {
            _integer(getattr(record, "sequence"), "sequence")
            for record in records
        }
        if len(sequences) > 1:
            result["multi_sequence_fill_event_count"] += 1

        fill_identities = tuple(
            v03._execution_identity(record) for record in fill_records
        )
        cancel_identities = tuple(
            v03._execution_identity(record) for record in cancel_records
        )
        for name, indexes in _PROJECTION_INDEXES.items():
            fills = Counter(
                _projection(identity, indexes) for identity in fill_identities
            )
            cancels = Counter(
                _projection(identity, indexes) for identity in cancel_identities
            )
            overlap = sum((fills & cancels).values())
            overlap_counts[name] += overlap
            if overlap == len(fill_records):
                full_match_counts[name] += 1

    result.update(
        {
            "raw_record_values_persisted": False,
            "feature_values_persisted": False,
            "runtime_authority_created": False,
        }
    )
    return result


__all__ = [
    "ARTIFACT_TYPE",
    "CLASSIFIER_CONTRACT_ID",
    "CONTRACT_CONTENT_SHA256",
    "PARENT_FAILURE_AUDIT_ID",
    "PARENT_FAILURE_CONTENT_SHA256",
    "PARENT_REPORT_CONTENT_SHA256",
    "REQUEST",
    "classify_fill_cancel_structure",
    "load_classifier_contract",
    "load_parent_failure_audit",
    "validate_classifier_contract",
    "validate_parent_failure_audit",
]
