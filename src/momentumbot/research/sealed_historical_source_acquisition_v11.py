"""Strict provider-free final report for sealed source recovery v0.11."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Mapping

from momentumbot.historical_float_identity_v11 import (
    validate_final_identity_preflight_receipt,
)
from momentumbot.research.sealed_historical_source_acquisition_v04 import (
    expected_manifest_paths_v04,
    validate_source_summary_v04,
)
from momentumbot.research.sealed_historical_source_authorization_v11 import (
    AUTHORIZATION_CONTENT_SHA256,
    AUTHORIZATION_ID,
    EXPECTED_DISPATCHER_WORKFLOW_REF,
)
from momentumbot.research.sealed_historical_source_checkpoint_v10 import (
    EXPECTED_POST_SCANNER_FILE_COUNT,
    MAX_RETAINED_BYTES,
    canonical_fingerprint,
    normalize_composite_request_budget,
    validate_post_scanner_checkpoint_binding_v10,
)


SCHEMA_VERSION = 1
ARTIFACT_TYPE = "sealed_historical_source_freeze_recovery_v0_11_result"
EXPECTED_REPOSITORY = "RoomyRems/momentumbot"
EXPECTED_DATES = (
    "2025-05-30", "2025-06-02", "2025-06-03", "2025-06-04",
    "2025-06-05", "2025-06-06", "2025-06-09", "2025-06-10",
    "2025-06-11", "2025-06-12", "2025-06-13", "2025-06-16",
    "2025-06-17", "2025-06-18", "2025-06-20", "2025-06-23",
    "2025-06-24", "2025-06-25", "2025-06-26", "2025-06-27",
    "2025-07-01", "2025-07-02", "2025-07-07", "2025-07-08",
    "2025-07-10", "2025-07-11", "2025-07-14", "2025-07-15",
    "2025-07-16", "2025-07-17",
)
PARENT_CHECKPOINT_FILE_SHA256 = (
    "7d1f6858fa669af9de467c36c11e5aff0f3e7af99c0e65bbffcb2814c1040711"
)
PARENT_CHECKPOINT_CONTENT_SHA256 = (
    "fef36fbcf2844f1da8510572a95c2f2978509bd2b021d2227c03c5ba5f3466f9"
)
PARENT_CHECKPOINT_ZIP_SHA256 = (
    "b13bb68c5c231ba51b73c63d2a0d7e73fa78a0a837d4e35b94a55ddf5006b3b3"
)
PARENT_ENVIRONMENT_FREEZE_SHA256 = (
    "580a7b8d85d8a925c4c7fa979fda816cb9f907bab9542ed793b3091ed9301dd7"
)
PARENT_PROJECT_COMMIT_SHA = "652db5675a35b6f455aa0d924aa50428dd995280"
PARENT_REQUEST_BUDGET = {
    "schema_version": 1,
    "total_attempts": 30_522,
    "by_host": {
        "api.massive.com": 363,
        "data.alpaca.markets": 28_831,
        "data.sec.gov": 1_328,
    },
}
PARENT_PROVENANCE = {
    "repository": EXPECTED_REPOSITORY,
    "authorization_commit_sha": PARENT_PROJECT_COMMIT_SHA,
    "authorization_tree_sha": "48092229da6a5cf2dd24de6fe4f98584e6de68e3",
    "dispatcher_workflow_sha": "8b920876d9a513f31d6fdb6795c4155a2c1a1519",
    "dispatcher_workflow_ref": (
        "RoomyRems/momentumbot/.github/workflows/"
        "sealed-historical-source-acquisition-v10.yml@refs/heads/main"
    ),
    "workflow_run_id": "33706372901",
    "workflow_run_attempt": 1,
}
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_RUN_ID = re.compile(r"^[1-9][0-9]*$")
_EDITABLE_PROJECT = re.compile(
    r"^-e git\+https://github\.com/RoomyRems/momentumbot(?:\.git)?@"
    r"([0-9a-f]{40})#egg=momentumbot$"
)


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _environment_parts(
    path: str | Path,
    *,
    expected_commit_sha: str,
    label: str,
) -> tuple[str, ...]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"{label} environment freeze must be a regular file")
    raw = source.read_bytes()
    if not raw or not raw.endswith(b"\n") or b"\r" in raw:
        raise ValueError(f"{label} environment freeze is not canonical")
    lines = raw.decode("utf-8").splitlines()
    if not lines or any(not line for line in lines) or len(lines) != len(set(lines)):
        raise ValueError(f"{label} environment freeze lines are invalid")
    editable = [
        match for line in lines if (match := _EDITABLE_PROJECT.fullmatch(line))
    ]
    if len(editable) != 1 or editable[0].group(1) != expected_commit_sha:
        raise ValueError(f"{label} editable project commit changed")
    return tuple(line for line in lines if _EDITABLE_PROJECT.fullmatch(line) is None)


def validate_recovery_environment_pair_v11(
    *,
    parent_environment_freeze_path: str | Path,
    child_environment_freeze_path: str | Path,
    expected_child_commit_sha: str,
) -> dict[str, object]:
    if _GIT_SHA.fullmatch(expected_child_commit_sha) is None:
        raise ValueError("child project commit is not canonical")
    parent_path = Path(parent_environment_freeze_path)
    if file_sha256(parent_path) != PARENT_ENVIRONMENT_FREEZE_SHA256:
        raise ValueError("v0.10 environment freeze hash changed")
    parent = _environment_parts(
        parent_path,
        expected_commit_sha=PARENT_PROJECT_COMMIT_SHA,
        label="v0.10",
    )
    child = _environment_parts(
        child_environment_freeze_path,
        expected_commit_sha=expected_child_commit_sha,
        label="v0.11",
    )
    if child != parent:
        raise ValueError("v0.11 third-party environment differs from v0.10")
    return {
        "schema_version": 1,
        "parent_environment_freeze_sha256": file_sha256(parent_path),
        "child_environment_freeze_sha256": file_sha256(
            child_environment_freeze_path
        ),
        "parent_project_commit_sha": PARENT_PROJECT_COMMIT_SHA,
        "child_project_commit_sha": expected_child_commit_sha,
        "third_party_environment_sha256": canonical_fingerprint(
            {"lines": list(parent)}
        ),
    }


def _workflow_provenance_v11(
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
        raise ValueError("v0.11 repository changed")
    for label, value in (
        ("authorization commit", authorization_commit_sha),
        ("authorization tree", authorization_tree_sha),
        ("dispatcher workflow", dispatcher_workflow_sha),
    ):
        if _GIT_SHA.fullmatch(value) is None:
            raise ValueError(f"{label} must be a canonical Git SHA")
    if dispatcher_workflow_ref != EXPECTED_DISPATCHER_WORKFLOW_REF:
        raise ValueError("v0.11 dispatcher workflow ref changed")
    if _RUN_ID.fullmatch(workflow_run_id) is None:
        raise ValueError("v0.11 workflow run ID is invalid")
    if isinstance(workflow_run_attempt, bool) or workflow_run_attempt != 1:
        raise ValueError("v0.11 is attempt 1 only")
    return {
        "repository": repository,
        "authorization_commit_sha": authorization_commit_sha,
        "authorization_tree_sha": authorization_tree_sha,
        "dispatcher_workflow_sha": dispatcher_workflow_sha,
        "dispatcher_workflow_ref": dispatcher_workflow_ref,
        "workflow_run_id": workflow_run_id,
        "workflow_run_attempt": workflow_run_attempt,
    }


def _validate_environment_comparison(
    value: Mapping[str, object],
) -> dict[str, object]:
    expected_keys = {
        "schema_version",
        "parent_environment_freeze_sha256",
        "child_environment_freeze_sha256",
        "parent_project_commit_sha",
        "child_project_commit_sha",
        "third_party_environment_sha256",
    }
    if set(value) != expected_keys:
        raise ValueError("v0.11 environment comparison fields changed")
    if (
        value.get("schema_version") != 1
        or value.get("parent_environment_freeze_sha256")
        != PARENT_ENVIRONMENT_FREEZE_SHA256
        or value.get("parent_project_commit_sha") != PARENT_PROJECT_COMMIT_SHA
    ):
        raise ValueError("v0.11 parent environment comparison changed")
    for field in (
        "child_environment_freeze_sha256",
        "third_party_environment_sha256",
    ):
        observed = value.get(field)
        if not isinstance(observed, str) or re.fullmatch(r"[0-9a-f]{64}", observed) is None:
            raise ValueError(f"v0.11 environment {field} is invalid")
    child_commit = value.get("child_project_commit_sha")
    if not isinstance(child_commit, str) or _GIT_SHA.fullmatch(child_commit) is None:
        raise ValueError("v0.11 child environment commit is invalid")
    return dict(value)


def build_recovery_report_v11(
    *,
    authorization_id: str,
    authorization_content_sha256: str,
    parent_checkpoint_binding: Mapping[str, object],
    source_summary: Mapping[str, object],
    identity_preflight: Mapping[str, object],
    environment_comparison: Mapping[str, object],
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
        or authorization_content_sha256 != AUTHORIZATION_CONTENT_SHA256
    ):
        raise ValueError("report authority is not the frozen v0.11 child")
    binding = validate_post_scanner_checkpoint_binding_v10(
        parent_checkpoint_binding
    )
    if (
        binding.get("checkpoint_file_sha256")
        != PARENT_CHECKPOINT_FILE_SHA256
        or binding.get("checkpoint_content_sha256")
        != PARENT_CHECKPOINT_CONTENT_SHA256
        or binding.get("provenance") != PARENT_PROVENANCE
        or binding.get("request_budget")
        != normalize_composite_request_budget(PARENT_REQUEST_BUDGET)
    ):
        raise ValueError("v0.11 parent checkpoint binding changed")
    validate_source_summary_v04(
        source_summary,
        expected_manifest_paths=expected_manifest_paths_v04(),
        expected_source_file_count=EXPECTED_POST_SCANNER_FILE_COUNT,
    )
    preflight = validate_final_identity_preflight_receipt(
        dict(identity_preflight)
    )
    environment = _validate_environment_comparison(environment_comparison)
    retained = retained_bytes
    if (
        isinstance(retained, bool)
        or not isinstance(retained, int)
        or retained <= 0
        or retained > MAX_RETAINED_BYTES
    ):
        raise ValueError("v0.11 retained bytes are invalid")
    if (
        binding.get("post_scanner_tree_content_sha256")
        != source_summary.get("source_tree_content_sha256")
        or binding.get("post_scanner_file_count")
        != source_summary.get("source_file_count")
        or binding.get("post_scanner_retained_file_bytes") != retained
        or source_summary.get("source_retained_file_bytes") != retained
    ):
        raise ValueError("v0.11 final source differs from parent binding")
    provenance = _workflow_provenance_v11(
        repository=repository,
        authorization_commit_sha=authorization_commit_sha,
        authorization_tree_sha=authorization_tree_sha,
        dispatcher_workflow_sha=dispatcher_workflow_sha,
        dispatcher_workflow_ref=dispatcher_workflow_ref,
        workflow_run_id=workflow_run_id,
        workflow_run_attempt=workflow_run_attempt,
    )
    if environment.get("child_project_commit_sha") != provenance.get(
        "authorization_commit_sha"
    ):
        raise ValueError("v0.11 environment commit differs from authorization")
    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "authorization_id": authorization_id,
        "authorization_content_sha256": authorization_content_sha256,
        "selected_dates": list(EXPECTED_DATES),
        "parent_provider_checkpoint": {
            "artifact_id": 9_877_181_150,
            "zip_sha256": PARENT_CHECKPOINT_ZIP_SHA256,
            "binding": binding,
        },
        "final_identity_preflight": preflight,
        "source_summary": dict(source_summary),
        "request_budget": normalize_composite_request_budget(
            PARENT_REQUEST_BUDGET
        ),
        "environment_comparison": environment,
        "retention": {
            "maximum_retained_bytes": MAX_RETAINED_BYTES,
            "observed_retained_bytes": retained,
        },
        "workflow_provenance": provenance,
        "cost": {
            "incremental_provider_cost_usd": "0",
            "provider_calls": 0,
            "databento_called": False,
        },
        "causal_attestation": {
            "account_or_order_endpoint_called": False,
            "all_candidates_and_float_records_preflighted": True,
            "authoritative_identity_kinds": [
                "composite_figi",
                "unique_cik_fallback",
            ],
            "candidate_identity_values_rewritten": False,
            "final_summarizer_identity_scope_restored": True,
            "float_records_rewritten": False,
            "order_submitted": False,
            "parent_provider_checkpoint_reused_exactly": True,
            "provider_requests_repeated": False,
            "ross_labels_or_outcomes_read": False,
            "scanner_snapshots_rebuilt_from_frozen_inputs_only": True,
            "strategy_micro_or_account_policy_changed": False,
            "transcript_record_values_read": False,
        },
        "source_acquisition_gate_passed": True,
        "next_gate": "provider_free_label_blind_scanner_and_micro_runtime_freeze",
    }
    report["content_sha256"] = canonical_fingerprint(report)
    validate_recovery_report_v11(report)
    return report


def validate_recovery_report_v11(report: Mapping[str, object]) -> None:
    expected_keys = {
        "schema_version",
        "artifact_type",
        "authorization_id",
        "authorization_content_sha256",
        "selected_dates",
        "parent_provider_checkpoint",
        "final_identity_preflight",
        "source_summary",
        "request_budget",
        "environment_comparison",
        "retention",
        "workflow_provenance",
        "cost",
        "causal_attestation",
        "source_acquisition_gate_passed",
        "next_gate",
        "content_sha256",
    }
    if set(report) != expected_keys:
        raise ValueError("v0.11 recovery report fields changed")
    body = dict(report)
    claimed = body.pop("content_sha256", None)
    if claimed != canonical_fingerprint(body):
        raise ValueError("v0.11 recovery report hash mismatch")
    if (
        report.get("schema_version") != SCHEMA_VERSION
        or report.get("artifact_type") != ARTIFACT_TYPE
        or report.get("authorization_id") != AUTHORIZATION_ID
        or report.get("authorization_content_sha256")
        != AUTHORIZATION_CONTENT_SHA256
        or report.get("selected_dates") != list(EXPECTED_DATES)
    ):
        raise ValueError("unsupported v0.11 recovery report")
    parent = report.get("parent_provider_checkpoint")
    if (
        not isinstance(parent, Mapping)
        or set(parent) != {"artifact_id", "zip_sha256", "binding"}
        or parent.get("artifact_id") != 9_877_181_150
        or parent.get("zip_sha256") != PARENT_CHECKPOINT_ZIP_SHA256
    ):
        raise ValueError("v0.11 parent checkpoint is missing")
    binding = parent.get("binding")
    if not isinstance(binding, Mapping):
        raise ValueError("v0.11 parent checkpoint binding is missing")
    binding = validate_post_scanner_checkpoint_binding_v10(binding)
    if (
        binding.get("checkpoint_file_sha256")
        != PARENT_CHECKPOINT_FILE_SHA256
        or binding.get("checkpoint_content_sha256")
        != PARENT_CHECKPOINT_CONTENT_SHA256
        or binding.get("provenance") != PARENT_PROVENANCE
        or binding.get("request_budget")
        != normalize_composite_request_budget(PARENT_REQUEST_BUDGET)
    ):
        raise ValueError("v0.11 parent checkpoint binding changed")
    preflight = report.get("final_identity_preflight")
    if not isinstance(preflight, Mapping):
        raise ValueError("v0.11 identity preflight is missing")
    validate_final_identity_preflight_receipt(dict(preflight))
    summary = report.get("source_summary")
    if not isinstance(summary, Mapping):
        raise ValueError("v0.11 source summary is missing")
    validate_source_summary_v04(
        summary,
        expected_manifest_paths=expected_manifest_paths_v04(),
        expected_source_file_count=EXPECTED_POST_SCANNER_FILE_COUNT,
    )
    environment = report.get("environment_comparison")
    if not isinstance(environment, Mapping):
        raise ValueError("v0.11 environment comparison is missing")
    _validate_environment_comparison(environment)
    retention = report.get("retention")
    if not isinstance(retention, Mapping) or set(retention) != {
        "maximum_retained_bytes",
        "observed_retained_bytes",
    }:
        raise ValueError("v0.11 retention boundary changed")
    retained = retention.get("observed_retained_bytes")
    if (
        retention.get("maximum_retained_bytes") != MAX_RETAINED_BYTES
        or isinstance(retained, bool)
        or not isinstance(retained, int)
        or retained <= 0
        or retained > MAX_RETAINED_BYTES
        or binding.get("post_scanner_tree_content_sha256")
        != summary.get("source_tree_content_sha256")
        or binding.get("post_scanner_file_count")
        != summary.get("source_file_count")
        or binding.get("post_scanner_retained_file_bytes") != retained
        or summary.get("source_retained_file_bytes") != retained
    ):
        raise ValueError("v0.11 final source retention changed")
    provenance = report.get("workflow_provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("v0.11 workflow provenance is missing")
    _workflow_provenance_v11(**dict(provenance))  # type: ignore[arg-type]
    if environment.get("child_project_commit_sha") != provenance.get(
        "authorization_commit_sha"
    ):
        raise ValueError("v0.11 environment commit differs from authorization")
    if report.get("request_budget") != normalize_composite_request_budget(
        PARENT_REQUEST_BUDGET
    ):
        raise ValueError("v0.11 request accounting changed")
    if report.get("cost") != {
        "incremental_provider_cost_usd": "0",
        "provider_calls": 0,
        "databento_called": False,
    }:
        raise ValueError("v0.11 cost boundary changed")
    if report.get("causal_attestation") != {
        "account_or_order_endpoint_called": False,
        "all_candidates_and_float_records_preflighted": True,
        "authoritative_identity_kinds": [
            "composite_figi",
            "unique_cik_fallback",
        ],
        "candidate_identity_values_rewritten": False,
        "final_summarizer_identity_scope_restored": True,
        "float_records_rewritten": False,
        "order_submitted": False,
        "parent_provider_checkpoint_reused_exactly": True,
        "provider_requests_repeated": False,
        "ross_labels_or_outcomes_read": False,
        "scanner_snapshots_rebuilt_from_frozen_inputs_only": True,
        "strategy_micro_or_account_policy_changed": False,
        "transcript_record_values_read": False,
    }:
        raise ValueError("v0.11 causal attestation changed")
    if (
        report.get("source_acquisition_gate_passed") is not True
        or report.get("next_gate")
        != "provider_free_label_blind_scanner_and_micro_runtime_freeze"
    ):
        raise ValueError("v0.11 final gate changed")


__all__ = [
    "ARTIFACT_TYPE",
    "PARENT_CHECKPOINT_CONTENT_SHA256",
    "PARENT_CHECKPOINT_FILE_SHA256",
    "PARENT_PROVENANCE",
    "PARENT_REQUEST_BUDGET",
    "build_recovery_report_v11",
    "file_sha256",
    "validate_recovery_environment_pair_v11",
    "validate_recovery_report_v11",
]
