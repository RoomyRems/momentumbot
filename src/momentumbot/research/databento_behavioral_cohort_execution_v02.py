"""Unarmed v0.2 gate for the repaired behavioral-cohort diagnostic.

The v0.1 authorization was consumed by an immutable safe failure.  This module
creates a new authorization namespace, binds that failure and the sole
DataFrame conversion repair, and delegates the unchanged causal replay to the
already tested v0.1 mechanics.  It is inert without a separately published
v0.2 authorization file.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Mapping

from momentumbot.research import databento_behavioral_cohort_execution_v01 as v01
from momentumbot.research.microstructure_contract import (
    canonical_fingerprint,
    file_sha256,
)


SCHEMA_VERSION = 1
EXECUTION_CONTRACT_ID = "databento-microstructure-behavioral-cohort-v0.2"
EXECUTION_CONTRACT_CONTENT_SHA256 = (
    "885d8395839d45b772905a56f9261385a26127ed787f419074073f496d364a2a"
)
EXECUTION_CONTRACT_FILE_SHA256 = (
    "16084adf76ef7a59510a4872c6f13e4e8c3cf29ebb9fcbe526205f9f9c679ae1"
)
PARENT_SAFE_FAILURE_CONTENT_SHA256 = (
    "724a081a2e282f3e5e988dd971ec18fb00b42139feacb150e55bbb91324cc860"
)
PARENT_SAFE_FAILURE_FILE_SHA256 = (
    "11a36aa744134e61e0618276e87c287844dccbf81b225ea21fe07f6cfd7c6b81"
)
REPAIRED_ENGINE_FILE_SHA256 = (
    "d77e44f60a171b10d2a0a556a891a753876b7b85bf7bc5f7a2b6fda95c8c4fe4"
)
PUBLISHED_REPAIR_COMMIT_SHA = "3f5ec5d85b32029e35c4cad371ca5c5a886b9e76"
PUBLISHED_REPAIR_TREE_SHA = "1bd96b0cea82693d3700feec76dd3ece8d9e0e24"
EXECUTION_AUTHORIZATION_ID = "microstructure-behavioral-cohort-v0.2-execution"
ARTIFACT_TYPE = "sanitized_databento_microstructure_behavioral_cohort_v0.2"
REQUEST_COUNT = v01.REQUEST_COUNT
OPPORTUNITY_COUNT = v01.OPPORTUNITY_COUNT
MAX_PREFLIGHT_COST_USD = v01.MAX_PREFLIGHT_COST_USD
MAX_PREFLIGHT_BILLABLE_SIZE_BYTES = v01.MAX_PREFLIGHT_BILLABLE_SIZE_BYTES
_ROOT = Path(__file__).resolve().parents[3]
_CONTRACT_PATH = (
    _ROOT / "research/strategy/databento-microstructure-behavioral-cohort-v0.2.json"
)
_PARENT_FAILURE_PATH = (
    _ROOT
    / "research/data-audits/"
    "databento-microstructure-behavioral-cohort-v0.1-"
    "run-32550318387-safe-failure-2026-08-21.json"
)
_REPAIRED_ENGINE_PATH = (
    _ROOT / "src/momentumbot/research/databento_behavioral_cohort_execution_v01.py"
)
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")


RuntimeConstants = v01.RuntimeConstants
SafeDiagnosticFailure = v01.SafeDiagnosticFailure
load_cohort = v01.load_cohort
load_protocol = v01.load_protocol


def _load_object(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def validate_parent_safe_failure(payload: Mapping[str, object]) -> None:
    expected = {
        "schema_version": 1,
        "audit_id": (
            "databento-microstructure-behavioral-cohort-v0.1-"
            "run-32550318387-safe-failure-2026-08-21"
        ),
        "artifact_type": (
            "independently_verified_sanitized_databento_behavioral_cohort_safe_failure"
        ),
        "content_sha256": PARENT_SAFE_FAILURE_CONTENT_SHA256,
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise ValueError(f"parent behavioral safe failure {field} changed")
    attempt = payload.get("verified_preflight_and_attempt")
    failure = payload.get("classified_failure")
    correction = payload.get("corrective_interpretation")
    if not isinstance(attempt, Mapping) or not isinstance(failure, Mapping):
        raise ValueError("parent behavioral safe failure shape changed")
    if not isinstance(correction, Mapping):
        raise ValueError("parent behavioral corrective interpretation changed")
    if (
        attempt.get("request_count_quoted") != REQUEST_COUNT
        or attempt.get("timeseries_request_count") != 1
        or attempt.get("automatic_retry_attempted") is not False
        or failure.get("failure_request_id") != "2026-07-10-GMM"
        or failure.get("failure_phase") != "record"
        or failure.get("safe_error_code") != "record_payload_invalid"
        or failure.get("all_requests_succeeded") is not False
        or correction.get("provider_rerun_authorized") is not False
        or correction.get("new_execution_authorization_required_for_any_later_attempt")
        is not True
    ):
        raise ValueError("parent behavioral safe failure evidence changed")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != PARENT_SAFE_FAILURE_CONTENT_SHA256:
        raise ValueError("parent behavioral safe failure fingerprint mismatch")


def load_parent_safe_failure(path: str | Path = _PARENT_FAILURE_PATH) -> dict[str, object]:
    source = Path(path)
    if file_sha256(source) != PARENT_SAFE_FAILURE_FILE_SHA256:
        raise ValueError("parent behavioral safe failure file hash changed")
    payload = _load_object(source)
    validate_parent_safe_failure(payload)
    return payload


def validate_execution_contract(payload: Mapping[str, object]) -> None:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "execution_contract_id": EXECUTION_CONTRACT_ID,
        "artifact_type": (
            "preregistered_unarmed_databento_behavioral_cohort_dataframe_repair_execution"
        ),
        "provider_purchase_authorized": False,
        "execution_authorization_file_present": False,
        "content_sha256": EXECUTION_CONTRACT_CONTENT_SHA256,
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise ValueError(f"behavioral cohort v0.2 contract {field} changed")
    repair = payload.get("published_repair_checkpoint")
    parent = payload.get("frozen_parent_failure")
    inputs = payload.get("frozen_inputs")
    frame = payload.get("registered_dataframe_repair")
    surface = payload.get("request_surface")
    gate = payload.get("future_execution_gate")
    if not all(
        isinstance(value, Mapping)
        for value in (repair, parent, inputs, frame, surface, gate)
    ):
        raise ValueError("behavioral cohort v0.2 contract shape changed")
    assert isinstance(repair, Mapping)
    assert isinstance(parent, Mapping)
    assert isinstance(inputs, Mapping)
    assert isinstance(frame, Mapping)
    assert isinstance(surface, Mapping)
    assert isinstance(gate, Mapping)
    if (
        repair.get("commit_sha") != PUBLISHED_REPAIR_COMMIT_SHA
        or repair.get("tree_sha") != PUBLISHED_REPAIR_TREE_SHA
        or parent.get("file_sha256") != PARENT_SAFE_FAILURE_FILE_SHA256
        or parent.get("content_sha256") != PARENT_SAFE_FAILURE_CONTENT_SHA256
        or parent.get("workflow_run_id") != 32550318387
        or parent.get("timeseries_request_count") != 1
        or parent.get("automatic_retry_attempted") is not False
        or inputs.get("cohort_content_sha256") != v01.COHORT_CONTENT_SHA256
        or inputs.get("behavioral_protocol_content_sha256")
        != v01.PROTOCOL_CONTENT_SHA256
        or inputs.get("cohort_execution_source_file_sha256")
        != REPAIRED_ENGINE_FILE_SHA256
    ):
        raise ValueError("behavioral cohort v0.2 provenance changed")
    if frame.get("keyword_arguments") != {
        "map_symbols": True,
        "pretty_ts": False,
        "price_type": "fixed",
    } or frame.get("prohibited_removed_keyword") != "pretty_px":
        raise ValueError("behavioral cohort v0.2 DataFrame repair changed")
    if (
        surface.get("exact_request_count") != REQUEST_COUNT
        or surface.get("opportunity_count") != OPPORTUNITY_COUNT
        or surface.get("prospective_quantity_shares") != 5558
        or gate.get("authorization_path")
        != "research/strategy/microstructure-behavioral-cohort-v0.2-execution.json"
        or gate.get("exact_request_count_authorized_now") != 0
        or gate.get("provider_cost_authorized_now_usd") != "0"
        or gate.get("provider_bytes_authorized_now") != 0
        or gate.get("hard_preflight_cost_ceiling_usd") != "0.25"
        or gate.get("hard_preflight_billable_size_ceiling_bytes")
        != MAX_PREFLIGHT_BILLABLE_SIZE_BYTES
        or gate.get("automatic_retry_authorized") is not False
        or gate.get("partial_cohort_substitution_authorized") is not False
        or gate.get("v0_1_authorization_reuse_authorized") is not False
    ):
        raise ValueError("behavioral cohort v0.2 execution surface changed")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != EXECUTION_CONTRACT_CONTENT_SHA256:
        raise ValueError("behavioral cohort v0.2 contract fingerprint mismatch")
    if file_sha256(_REPAIRED_ENGINE_PATH) != REPAIRED_ENGINE_FILE_SHA256:
        raise ValueError("repaired behavioral cohort engine changed")
    load_parent_safe_failure()


def load_execution_contract(path: str | Path = _CONTRACT_PATH) -> dict[str, object]:
    source = Path(path)
    if file_sha256(source) != EXECUTION_CONTRACT_FILE_SHA256:
        raise ValueError("behavioral cohort v0.2 contract file hash changed")
    payload = _load_object(source)
    validate_execution_contract(payload)
    return payload


def validate_execution_authorization(payload: Mapping[str, object]) -> None:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "execution_authorization_id": EXECUTION_AUTHORIZATION_ID,
        "artifact_type": (
            "explicit_one_shot_databento_behavioral_cohort_v0.2_authorization"
        ),
        "execution_contract_id": EXECUTION_CONTRACT_ID,
        "execution_contract_content_sha256": EXECUTION_CONTRACT_CONTENT_SHA256,
        "parent_safe_failure_content_sha256": PARENT_SAFE_FAILURE_CONTENT_SHA256,
        "cohort_id": v01.COHORT_ID,
        "cohort_content_sha256": v01.COHORT_CONTENT_SHA256,
        "behavioral_protocol_content_sha256": v01.PROTOCOL_CONTENT_SHA256,
        "provider_purchase_authorized": True,
        "exact_request_count_authorized": REQUEST_COUNT,
        "hard_preflight_cost_ceiling_usd": "0.25",
        "hard_preflight_billable_size_ceiling_bytes": (
            MAX_PREFLIGHT_BILLABLE_SIZE_BYTES
        ),
        "all_requests_quoted_before_first_download": True,
        "first_github_actions_attempt_only": True,
        "automatic_retry_authorized": False,
        "partial_cohort_substitution_authorized": False,
        "batch_or_live_endpoint_authorized": False,
        "raw_market_data_publication_authorized": False,
        "feature_value_publication_authorized": False,
        "broker_or_order_change_authorized": False,
        "strategy_or_threshold_change_authorized": False,
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise ValueError(f"behavioral cohort v0.2 authorization {field} changed")
    parent = payload.get("authorized_push_parent_sha")
    statement = payload.get("explicit_user_authorization")
    if not isinstance(parent, str) or _SHA40.fullmatch(parent) is None:
        raise ValueError("behavioral cohort v0.2 authorization parent SHA is invalid")
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError("explicit v0.2 user authorization is required")
    claimed = payload.get("content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if (
        not isinstance(claimed, str)
        or _SHA64.fullmatch(claimed) is None
        or canonical_fingerprint(unsigned) != claimed
    ):
        raise ValueError("behavioral cohort v0.2 authorization fingerprint mismatch")
    load_execution_contract()


def load_execution_authorization(path: str | Path) -> dict[str, object]:
    payload = _load_object(path)
    validate_execution_authorization(payload)
    return payload


def _legacy_authorization(payload: Mapping[str, object]) -> dict[str, object]:
    legacy: dict[str, object] = {
        "schema_version": 1,
        "execution_authorization_id": v01.EXECUTION_AUTHORIZATION_ID,
        "artifact_type": "explicit_one_shot_databento_behavioral_cohort_authorization",
        "cohort_id": v01.COHORT_ID,
        "cohort_content_sha256": v01.COHORT_CONTENT_SHA256,
        "behavioral_protocol_content_sha256": v01.PROTOCOL_CONTENT_SHA256,
        "authorized_push_parent_sha": payload["authorized_push_parent_sha"],
        "explicit_user_authorization": payload["explicit_user_authorization"],
        "provider_purchase_authorized": True,
        "exact_request_count_authorized": REQUEST_COUNT,
        "hard_preflight_cost_ceiling_usd": "0.25",
        "hard_preflight_billable_size_ceiling_bytes": (
            MAX_PREFLIGHT_BILLABLE_SIZE_BYTES
        ),
        "all_requests_quoted_before_first_download": True,
        "first_github_actions_attempt_only": True,
        "automatic_retry_authorized": False,
        "partial_cohort_substitution_authorized": False,
        "batch_or_live_endpoint_authorized": False,
        "raw_market_data_publication_authorized": False,
        "feature_value_publication_authorized": False,
        "broker_or_order_change_authorized": False,
        "strategy_or_threshold_change_authorized": False,
    }
    legacy["content_sha256"] = canonical_fingerprint(legacy)
    v01.validate_execution_authorization(legacy)
    return legacy


def _version_report(
    report: Mapping[str, object], authorization: Mapping[str, object]
) -> dict[str, object]:
    versioned = dict(report)
    versioned.update(
        {
            "artifact_type": ARTIFACT_TYPE,
            "execution_authorization_id": EXECUTION_AUTHORIZATION_ID,
            "execution_authorization_content_sha256": authorization["content_sha256"],
            "execution_contract_id": EXECUTION_CONTRACT_ID,
            "execution_contract_content_sha256": EXECUTION_CONTRACT_CONTENT_SHA256,
            "parent_safe_failure_content_sha256": PARENT_SAFE_FAILURE_CONTENT_SHA256,
            "cohort_execution_source_file_sha256": REPAIRED_ENGINE_FILE_SHA256,
            "published_repair_commit_sha": PUBLISHED_REPAIR_COMMIT_SHA,
            "published_repair_tree_sha": PUBLISHED_REPAIR_TREE_SHA,
        }
    )
    versioned.pop("content_sha256", None)
    versioned["content_sha256"] = canonical_fingerprint(versioned)
    return versioned


def build_unavailable_report(
    cohort: Mapping[str, object],
    protocol: Mapping[str, object],
    contract: Mapping[str, object],
    parent_failure: Mapping[str, object],
    authorization: Mapping[str, object],
    *,
    generated_at: datetime,
    sdk_version: str,
    failure_phase: str,
    safe_error_code: str,
) -> dict[str, object]:
    validate_execution_contract(contract)
    validate_parent_safe_failure(parent_failure)
    validate_execution_authorization(authorization)
    report = v01.build_unavailable_report(
        cohort,
        protocol,
        _legacy_authorization(authorization),
        generated_at=generated_at,
        sdk_version=sdk_version,
        failure_phase=failure_phase,
        safe_error_code=safe_error_code,
    )
    return _version_report(report, authorization)


def run_behavioral_cohort_diagnostic(
    cohort: Mapping[str, object],
    protocol: Mapping[str, object],
    contract: Mapping[str, object],
    parent_failure: Mapping[str, object],
    authorization: Mapping[str, object],
    client: v01.HistoricalClient,
    *,
    generated_at: datetime,
    sdk_version: str,
    runtime: RuntimeConstants,
) -> dict[str, object]:
    validate_execution_contract(contract)
    validate_parent_safe_failure(parent_failure)
    validate_execution_authorization(authorization)
    report = v01.run_behavioral_cohort_diagnostic(
        cohort,
        protocol,
        _legacy_authorization(authorization),
        client,
        generated_at=generated_at,
        sdk_version=sdk_version,
        runtime=runtime,
    )
    return _version_report(report, authorization)


def validate_behavioral_cohort_report(payload: Mapping[str, object]) -> None:
    expected = {
        "artifact_type": ARTIFACT_TYPE,
        "execution_authorization_id": EXECUTION_AUTHORIZATION_ID,
        "execution_contract_id": EXECUTION_CONTRACT_ID,
        "execution_contract_content_sha256": EXECUTION_CONTRACT_CONTENT_SHA256,
        "parent_safe_failure_content_sha256": PARENT_SAFE_FAILURE_CONTENT_SHA256,
        "cohort_execution_source_file_sha256": REPAIRED_ENGINE_FILE_SHA256,
        "published_repair_commit_sha": PUBLISHED_REPAIR_COMMIT_SHA,
        "published_repair_tree_sha": PUBLISHED_REPAIR_TREE_SHA,
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise ValueError(f"behavioral cohort v0.2 report {field} changed")
    claimed = payload.get("content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if not isinstance(claimed, str) or canonical_fingerprint(unsigned) != claimed:
        raise ValueError("behavioral cohort v0.2 report fingerprint mismatch")
    proxy = dict(payload)
    for field in (
        "execution_contract_id",
        "execution_contract_content_sha256",
        "parent_safe_failure_content_sha256",
        "cohort_execution_source_file_sha256",
        "published_repair_commit_sha",
        "published_repair_tree_sha",
    ):
        proxy.pop(field, None)
    proxy["artifact_type"] = v01.ARTIFACT_TYPE
    proxy["execution_authorization_id"] = v01.EXECUTION_AUTHORIZATION_ID
    proxy["execution_authorization_content_sha256"] = "0" * 64
    proxy.pop("content_sha256", None)
    proxy["content_sha256"] = canonical_fingerprint(proxy)
    v01.validate_behavioral_cohort_report(proxy)
    load_execution_contract()


__all__ = [
    "ARTIFACT_TYPE",
    "EXECUTION_AUTHORIZATION_ID",
    "EXECUTION_CONTRACT_CONTENT_SHA256",
    "EXECUTION_CONTRACT_ID",
    "MAX_PREFLIGHT_BILLABLE_SIZE_BYTES",
    "MAX_PREFLIGHT_COST_USD",
    "OPPORTUNITY_COUNT",
    "REQUEST_COUNT",
    "RuntimeConstants",
    "SafeDiagnosticFailure",
    "build_unavailable_report",
    "load_cohort",
    "load_execution_authorization",
    "load_execution_contract",
    "load_parent_safe_failure",
    "load_protocol",
    "run_behavioral_cohort_diagnostic",
    "validate_behavioral_cohort_report",
    "validate_execution_authorization",
    "validate_execution_contract",
    "validate_parent_safe_failure",
]
