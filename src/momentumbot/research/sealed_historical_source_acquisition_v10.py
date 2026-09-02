"""Strict provider-free final report for sealed source recovery v0.10."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Mapping

from momentumbot.research.sealed_historical_availability import SELECTED_DATES
from momentumbot.research.sealed_historical_source_acquisition_v04 import (
    expected_manifest_paths_v04,
    validate_source_summary_v04,
)
from momentumbot.research.sealed_historical_source_checkpoint_v10 import (
    AUTHORIZATION_ID,
    EXPECTED_POST_SCANNER_FILE_COUNT,
    EXPECTED_REPOSITORY,
    EXPECTED_WORKFLOW_REF,
    MAX_HTTP_ATTEMPTS,
    MAX_RETAINED_BYTES,
    canonical_fingerprint,
    normalize_composite_request_budget,
    validate_post_scanner_checkpoint_binding_v10,
)


SCHEMA_VERSION = 1
ARTIFACT_TYPE = "sealed_historical_source_recovery_v0_10_result"
EXPECTED_DATES = tuple(SELECTED_DATES)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_RUN_ID = re.compile(r"^[1-9][0-9]*$")


def _frozen_authorization_content_sha256() -> str:
    from momentumbot.research.sealed_historical_source_authorization_v10 import (
        AUTHORIZATION_CONTENT_SHA256,
    )

    if _SHA256.fullmatch(AUTHORIZATION_CONTENT_SHA256) is None:
        raise ValueError("frozen v0.10 authorization hash is invalid")
    return AUTHORIZATION_CONTENT_SHA256


def _strict_int(value: object, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _workflow_provenance_v10(
    *,
    repository: str,
    authorization_commit_sha: str,
    authorization_tree_sha: str,
    dispatcher_workflow_sha: str,
    dispatcher_workflow_ref: str,
    workflow_run_id: str,
    workflow_run_attempt: int,
) -> dict[str, object]:
    if repository != EXPECTED_REPOSITORY:
        raise ValueError("v0.10 repository changed")
    for label, value in (
        ("authorization commit", authorization_commit_sha),
        ("authorization tree", authorization_tree_sha),
        ("dispatcher workflow", dispatcher_workflow_sha),
    ):
        if not isinstance(value, str) or _GIT_SHA.fullmatch(value) is None:
            raise ValueError(f"{label} must be a full lowercase Git SHA")
    if dispatcher_workflow_ref != EXPECTED_WORKFLOW_REF:
        raise ValueError("v0.10 dispatcher workflow ref changed")
    if not isinstance(workflow_run_id, str) or _RUN_ID.fullmatch(workflow_run_id) is None:
        raise ValueError("v0.10 workflow run ID must be a positive decimal")
    if isinstance(workflow_run_attempt, bool) or workflow_run_attempt != 1:
        raise ValueError("v0.10 acquisition is attempt 1 only")
    return {
        "repository": repository,
        "authorization_commit_sha": authorization_commit_sha,
        "authorization_tree_sha": authorization_tree_sha,
        "dispatcher_workflow_sha": dispatcher_workflow_sha,
        "dispatcher_workflow_ref": dispatcher_workflow_ref,
        "workflow_run_id": workflow_run_id,
        "workflow_run_attempt": workflow_run_attempt,
    }


def build_acquisition_report_v10(
    *,
    authorization_id: str,
    authorization_content_sha256: str,
    source_checkpoint_binding: Mapping[str, object],
    source_summary: Mapping[str, object],
    request_budget: Mapping[str, object],
    retained_bytes: int,
    repository: str,
    authorization_commit_sha: str,
    authorization_tree_sha: str,
    dispatcher_workflow_sha: str,
    dispatcher_workflow_ref: str,
    workflow_run_id: str,
    workflow_run_attempt: int,
) -> dict[str, object]:
    if (
        authorization_id != AUTHORIZATION_ID
        or authorization_content_sha256 != _frozen_authorization_content_sha256()
    ):
        raise ValueError("report authority is not the frozen v0.10 child")
    checkpoint = validate_post_scanner_checkpoint_binding_v10(
        source_checkpoint_binding
    )
    validate_source_summary_v04(
        source_summary,
        expected_manifest_paths=expected_manifest_paths_v04(),
        expected_source_file_count=EXPECTED_POST_SCANNER_FILE_COUNT,
    )
    budget = normalize_composite_request_budget(request_budget)
    retained = _strict_int(retained_bytes, label="retained bytes", minimum=1)
    if retained > MAX_RETAINED_BYTES:
        raise ValueError("v0.10 retained-byte ceiling exceeded")
    provenance = _workflow_provenance_v10(
        repository=repository,
        authorization_commit_sha=authorization_commit_sha,
        authorization_tree_sha=authorization_tree_sha,
        dispatcher_workflow_sha=dispatcher_workflow_sha,
        dispatcher_workflow_ref=dispatcher_workflow_ref,
        workflow_run_id=workflow_run_id,
        workflow_run_attempt=workflow_run_attempt,
    )
    if checkpoint.get("authorization") != {
        "authorization_id": authorization_id,
        "authorization_content_sha256": authorization_content_sha256,
    }:
        raise ValueError("v0.10 checkpoint is bound to another authorization")
    if checkpoint.get("request_budget") != budget:
        raise ValueError("v0.10 checkpoint request accounting differs from report")
    if checkpoint.get("provenance") != provenance:
        raise ValueError("v0.10 checkpoint provenance differs from report")
    if (
        checkpoint.get("post_scanner_tree_content_sha256")
        != source_summary.get("source_tree_content_sha256")
        or checkpoint.get("post_scanner_file_count")
        != source_summary.get("source_file_count")
        or checkpoint.get("post_scanner_retained_file_bytes") != retained
        or retained != source_summary.get("source_retained_file_bytes")
    ):
        raise ValueError("v0.10 checkpoint final tree differs from source summary")
    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "authorization_id": authorization_id,
        "authorization_content_sha256": authorization_content_sha256,
        "selected_dates": list(EXPECTED_DATES),
        "parent_recovery": checkpoint["recovery"],
        "normalization_diagnostics": checkpoint["normalization_diagnostics"],
        "source_checkpoint": checkpoint,
        "source_summary": dict(source_summary),
        "request_budget": budget,
        "retention": {
            "maximum_retained_bytes": MAX_RETAINED_BYTES,
            "observed_retained_bytes": retained,
        },
        "workflow_provenance": provenance,
        "cost": {
            "incremental_provider_cost_usd": "0",
            "databento_called": False,
        },
        "causal_attestation": {
            "account_or_order_endpoint_called": False,
            "all_recovered_candidates_and_float_records_preflighted": True,
            "authoritative_identity_kinds": [
                "composite_figi",
                "unique_cik_fallback",
            ],
            "candidate_identity_values_rewritten": False,
            "complete_parent_news_reused": True,
            "exact_rvol_fill_or_interpolation_used": False,
            "exact_rvol_missing_raw_timestamps_allowed": False,
            "exact_rvol_values_changed": False,
            "exact_rvol_projected_to_raw_bar_index": True,
            "float_records_rewritten": False,
            "order_submitted": False,
            "parent_massive_identity_market_sec_float_or_news_requests_repeated": False,
            "partial_parent_scanner_tape_reused": False,
            "raw_provider_http_responses_persisted": False,
            "ross_labels_or_outcomes_read": False,
            "strategy_micro_or_account_policy_changed": False,
            "transcript_record_values_read": False,
        },
        "source_acquisition_gate_passed": True,
        "next_gate": "provider_free_label_blind_scanner_and_micro_runtime_freeze",
    }
    report["content_sha256"] = canonical_fingerprint(report)
    validate_acquisition_report_v10(report)
    return report


def validate_acquisition_report_v10(report: Mapping[str, object]) -> None:
    expected_keys = {
        "schema_version",
        "artifact_type",
        "authorization_id",
        "authorization_content_sha256",
        "selected_dates",
        "parent_recovery",
        "normalization_diagnostics",
        "source_checkpoint",
        "source_summary",
        "request_budget",
        "retention",
        "workflow_provenance",
        "cost",
        "causal_attestation",
        "source_acquisition_gate_passed",
        "next_gate",
        "content_sha256",
    }
    if set(report) != expected_keys:
        raise ValueError("v0.10 acquisition report fields changed")
    claimed = report.get("content_sha256")
    unsigned = {key: value for key, value in report.items() if key != "content_sha256"}
    if not isinstance(claimed, str) or _SHA256.fullmatch(claimed) is None or claimed != canonical_fingerprint(unsigned):
        raise ValueError("v0.10 acquisition report hash mismatch")
    if (
        report.get("schema_version") != SCHEMA_VERSION
        or report.get("artifact_type") != ARTIFACT_TYPE
        or report.get("authorization_id") != AUTHORIZATION_ID
        or report.get("authorization_content_sha256")
        != _frozen_authorization_content_sha256()
        or report.get("selected_dates") != list(EXPECTED_DATES)
    ):
        raise ValueError("unsupported v0.10 acquisition report")
    checkpoint = report.get("source_checkpoint")
    if not isinstance(checkpoint, Mapping):
        raise ValueError("v0.10 acquisition checkpoint binding is missing")
    checkpoint = validate_post_scanner_checkpoint_binding_v10(checkpoint)
    if report.get("parent_recovery") != checkpoint.get("recovery"):
        raise ValueError("v0.10 parent recovery binding differs from checkpoint")
    if report.get("normalization_diagnostics") != checkpoint.get(
        "normalization_diagnostics"
    ):
        raise ValueError("v0.10 normalization diagnostics differ from checkpoint")
    summary = report.get("source_summary")
    if not isinstance(summary, Mapping):
        raise ValueError("v0.10 source summary is missing")
    validate_source_summary_v04(
        summary,
        expected_manifest_paths=expected_manifest_paths_v04(),
        expected_source_file_count=EXPECTED_POST_SCANNER_FILE_COUNT,
    )
    budget = report.get("request_budget")
    if not isinstance(budget, Mapping):
        raise ValueError("v0.10 request budget is missing")
    normalized_budget = normalize_composite_request_budget(
        {
            "schema_version": budget.get("schema_version"),
            "total_attempts": budget.get("total_attempts"),
            "by_host": budget.get("by_host"),
        }
    )
    if dict(budget) != normalized_budget or checkpoint.get("request_budget") != budget:
        raise ValueError("v0.10 composite request accounting differs")
    retention = report.get("retention")
    if not isinstance(retention, Mapping) or set(retention) != {
        "maximum_retained_bytes",
        "observed_retained_bytes",
    } or retention.get("maximum_retained_bytes") != MAX_RETAINED_BYTES:
        raise ValueError("v0.10 retention boundary changed")
    retained = _strict_int(
        retention.get("observed_retained_bytes"), label="retained bytes", minimum=1
    )
    if retained > MAX_RETAINED_BYTES:
        raise ValueError("v0.10 retained-byte ceiling exceeded")
    provenance = report.get("workflow_provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("v0.10 workflow provenance is missing")
    normalized_provenance = _workflow_provenance_v10(**dict(provenance))  # type: ignore[arg-type]
    if checkpoint.get("provenance") != normalized_provenance:
        raise ValueError("v0.10 checkpoint provenance differs from report")
    if (
        checkpoint.get("post_scanner_tree_content_sha256")
        != summary.get("source_tree_content_sha256")
        or checkpoint.get("post_scanner_file_count") != summary.get("source_file_count")
        or checkpoint.get("post_scanner_retained_file_bytes") != retained
        or retained != summary.get("source_retained_file_bytes")
    ):
        raise ValueError("v0.10 report final source commitment differs")
    if report.get("cost") != {
        "incremental_provider_cost_usd": "0",
        "databento_called": False,
    }:
        raise ValueError("v0.10 cost boundary changed")
    if report.get("causal_attestation") != {
        "account_or_order_endpoint_called": False,
        "all_recovered_candidates_and_float_records_preflighted": True,
        "authoritative_identity_kinds": [
            "composite_figi",
            "unique_cik_fallback",
        ],
        "candidate_identity_values_rewritten": False,
        "complete_parent_news_reused": True,
        "exact_rvol_fill_or_interpolation_used": False,
        "exact_rvol_missing_raw_timestamps_allowed": False,
        "exact_rvol_values_changed": False,
        "exact_rvol_projected_to_raw_bar_index": True,
        "float_records_rewritten": False,
        "order_submitted": False,
        "parent_massive_identity_market_sec_float_or_news_requests_repeated": False,
        "partial_parent_scanner_tape_reused": False,
        "raw_provider_http_responses_persisted": False,
        "ross_labels_or_outcomes_read": False,
        "strategy_micro_or_account_policy_changed": False,
        "transcript_record_values_read": False,
    }:
        raise ValueError("v0.10 causal attestation changed")
    if (
        report.get("source_acquisition_gate_passed") is not True
        or report.get("next_gate")
        != "provider_free_label_blind_scanner_and_micro_runtime_freeze"
    ):
        raise ValueError("v0.10 final gate changed")


def load_acquisition_report_v10(path: str | Path) -> dict[str, object]:
    from momentumbot.research.sealed_historical_source_checkpoint_v01 import (
        load_json_object,
    )

    payload = load_json_object(Path(path))
    validate_acquisition_report_v10(payload)
    return payload


__all__ = [
    "ARTIFACT_TYPE",
    "build_acquisition_report_v10",
    "load_acquisition_report_v10",
    "validate_acquisition_report_v10",
]
