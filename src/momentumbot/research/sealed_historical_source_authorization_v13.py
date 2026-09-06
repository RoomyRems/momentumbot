"""Exact provider-free child of failed v0.12; old contracts stay immutable."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Mapping

from momentumbot.research import sealed_historical_source_authorization_v12 as parent


ROOT = parent.ROOT
AUTHORIZATION_ID = "sealed-historical-source-acquisition-v0.13"
AUTHORIZATION_CONTENT_SHA256 = "e075fa7bb99a55ca3b55f88673c3509f02886b139f1980fcf8dfd6a606d397a6"
AUTHORIZATION_PATH = Path("research/strategy/sealed-historical-source-acquisition-v0.13.json")
EXPECTED_DISPATCHER_WORKFLOW_REF = (
    "RoomyRems/momentumbot/.github/workflows/"
    "sealed-historical-source-acquisition-v13.yml@refs/heads/main"
)
FAILED_EXECUTION_AUDIT_PATH = Path(
    "research/data-audits/sealed-historical-source-acquisition-v0.12-"
    "run-33929860053-failure-2026-09-06.json"
)
FAILED_EXECUTION_AUDIT_CONTENT_SHA256 = (
    "1fa5c8b1d16442f177b4f22565c9edbc063a869330f23b2febb290d9ececeb60"
)
FAILED_WORKFLOW_FILE_SHA256 = (
    "7a6ec6eb3c8031bc022340a73408b837d75e03b20338845787f6b87df0679f39"
)
REGISTRATION_AUDIT_PATH = Path(
    "research/data-audits/sealed-historical-source-acquisition-v0.13-"
    "registration-2026-09-06.json"
)
canonical_fingerprint = parent.canonical_fingerprint
load_json_object = parent._load_json_object
file_sha256 = parent._file_sha256
REGISTRATION_ARTIFACT_PATHS = {
    "authorization": AUTHORIZATION_PATH,
    "authorization_validator": Path("src/momentumbot/research/sealed_historical_source_authorization_v13.py"),
    "failed_execution_audit": FAILED_EXECUTION_AUDIT_PATH,
    "failed_execution_workflow": Path(".github/workflows/sealed-historical-source-acquisition-v12.yml"),
    "final_report": Path("src/momentumbot/research/sealed_historical_source_acquisition_v13.py"),
    "runner": Path("scripts/run_sealed_historical_source_acquisition_v13.py"),
    "offline_guard": Path("scripts/run_offline_python_v13.py"),
    "undefined_name_gate": Path("scripts/check_recovery_entrypoints_v13.py"),
    "workflow": Path(".github/workflows/sealed-historical-source-acquisition-v13.yml"),
    "prelaunch_verification_workflow": Path(".github/workflows/sealed-historical-source-recovery-v13-e2e.yml"),
    "final_identity_adapter": Path("src/momentumbot/historical_float_identity_v11.py"),
    "parent_scanner_adapter": Path("scripts/build_causal_scanner_snapshot_v10.py"),
    "parent_checkpoint_validator": Path("src/momentumbot/research/sealed_historical_source_checkpoint_v10.py"),
    "requirements": Path("requirements-sealed-source-v04.txt"),
    "runner_regression_tests": Path("tests/test_sealed_historical_source_runner_v13.py"),
    "workflow_regression_tests": Path("tests/test_sealed_historical_source_workflow_v13.py"),
    "authorization_regression_tests": Path("tests/test_sealed_historical_source_authorization_v13.py"),
    "documentation": Path("docs/research/sealed_historical_source_acquisition_v13.md"),
}


def validate_parent_bundle() -> dict[str, object]:
    previous = parent.load_authorization(ROOT / parent.AUTHORIZATION_PATH)
    failure = load_json_object(ROOT / FAILED_EXECUTION_AUDIT_PATH)
    parent._validate_self_hash(
        failure, expected=FAILED_EXECUTION_AUDIT_CONTENT_SHA256,
        label="v0.12 terminal failure audit",
    )
    if (
        failure.get("conclusion") != "fail_closed_final_runner_missing_parent_request_budget_import"
        or failure.get("workflow", {}).get("run_id") != 33_929_860_053
        or failure.get("failure_artifact", {}).get("artifact_id") != 9_960_256_394
        or file_sha256(ROOT / ".github/workflows/sealed-historical-source-acquisition-v12.yml")
        != FAILED_WORKFLOW_FILE_SHA256
    ):
        raise ValueError("v0.12 failure provenance changed")
    return {"v0_12_authorization": previous, "v0_12_failure_audit": failure}


def expected_authorization_body() -> dict[str, object]:
    """Allow only the declared child deltas; inherit every other boundary."""
    parents = validate_parent_bundle()
    body = deepcopy(parents["v0_12_authorization"])
    body.pop("content_sha256")
    body["artifact_type"] = "preregistered_sealed_historical_source_freeze_recovery_v0_13"
    body["authorization_id"] = AUTHORIZATION_ID
    body["registered_at_date"] = "2026-09-06"
    body["dispatcher_contract"]["workflow_ref"] = EXPECTED_DISPATCHER_WORKFLOW_REF
    body["failed_execution"] = {
        "authorization_id": "sealed-historical-source-acquisition-v0.12",
        "authorization_content_sha256": parent.AUTHORIZATION_CONTENT_SHA256,
        "authorization_commit_sha": "dbe3abf2bf320fb014d76a34f3bf790d2d343deb",
        "authorization_tree_sha": "ce9f6dd6f66b2bbf4cc39748f6f5af6a8a3d3782",
        "dispatcher_workflow_sha": "070efdff977a637c60afff0b8826134ab31f92d4",
        "workflow_run_id": 33_929_860_053,
        "workflow_run_attempt": 1,
        "failure_artifact_id": 9_960_256_394,
        "failure_artifact_zip_sha256": "15587131e4eb2cf07a17ec4222aad81a1e6d9c428154bf834aa6dad1f1f4ac76",
        "safe_failure_content_sha256": "6d1f21a5c9868a3021f36c3979e1d6f841f8fc44ba8b551b6e28f524a16d2ab5",
        "failure_audit_content_sha256": FAILED_EXECUTION_AUDIT_CONTENT_SHA256,
        "provider_calls": 0,
        "scanner_freeze_completed_dates": 30,
        "scanner_snapshot_uploaded": False,
        "final_report_completed": False,
        "rerun_allowed": False,
    }
    repair = body["repair_boundary"]
    repair.pop("same_step_environment_comparison_uses_explicit_v0_12_interpreter")
    repair.update({
        "same_step_environment_comparison_uses_explicit_child_interpreter": True,
        "final_runner_imports_frozen_parent_request_budget": True,
        "frozen_ledger_and_identity_preflight_precedes_long_scanner_freeze": True,
        "intermediate_checkpoint_uploaded_before_final_deep_replay": True,
        "intermediate_checkpoint_is_not_a_completed_snapshot": True,
        "scientific_commands_deny_network_and_child_processes": True,
    })
    body["execution_order_contract"] = [
        "validate_v0_13_authorization_and_exact_v0_12_failure_provider_free",
        "pass_undefined_name_and_cli_success_failure_regressions",
        "complete_exact_checkpoint_end_to_end_verification_before_final_launch",
        "fetch_exact_v0_10_provider_checkpoint_metadata_once",
        "download_exact_v0_10_provider_checkpoint",
        "recreate_hash_pinned_environment_with_explicit_child_interpreter",
        "rehash_and_deeply_validate_all_706_checkpoint_source_files",
        "preflight_frozen_ledger_and_all_946_identities_before_long_freeze",
        "freeze_all_30_scanner_snapshots_from_canonical_inputs_provider_free",
        "bind_and_upload_hash_verified_767_file_intermediate_not_final",
        "scope_identity_compatibility_only_around_final_source_deep_replay",
        "restore_legacy_identity_validator",
        "require_final_report_to_match_the_intermediate_tree_commitment",
        "upload_completed_767_file_label_blind_source_bundle",
    ]
    return body


def validate_authorization(payload: Mapping[str, object]) -> None:
    parent._validate_self_hash(
        payload, expected=AUTHORIZATION_CONTENT_SHA256, label="v0.13 authorization",
    )
    body = dict(payload)
    body.pop("content_sha256")
    if body != expected_authorization_body():
        raise ValueError("v0.13 inherited authority or repair boundary changed")


def validate_registration_bundle() -> dict[str, object]:
    audit = load_json_object(ROOT / REGISTRATION_AUDIT_PATH)
    body = dict(audit)
    claimed = body.pop("content_sha256", None)
    if claimed != canonical_fingerprint(body):
        raise ValueError("v0.13 registration self-hash changed")
    if set(body) != {
        "schema_version", "artifact_type", "authorization_id",
        "authorization_content_sha256", "status", "launch_allowed",
        "provider_calls_authorized", "artifacts",
    } or (
        body.get("schema_version") != 1
        or body.get("artifact_type") != "provider_free_source_recovery_v0_13_registration"
        or body.get("authorization_id") != AUTHORIZATION_ID
        or body.get("authorization_content_sha256") != AUTHORIZATION_CONTENT_SHA256
        or body.get("status") != "unarmed_pending_completed_e2e_and_exact_manual_authorization"
        or body.get("launch_allowed") is not False
        or type(body.get("provider_calls_authorized")) is not int
        or body.get("provider_calls_authorized") != 0
    ):
        raise ValueError("v0.13 registration authority changed")
    artifacts = body.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(REGISTRATION_ARTIFACT_PATHS):
        raise ValueError("v0.13 registration artifact census changed")
    for label, relative in REGISTRATION_ARTIFACT_PATHS.items():
        path = ROOT / relative
        if path.is_symlink() or not path.is_file() or artifacts[label] != {
            "path": relative.as_posix(), "file_sha256": file_sha256(path),
        }:
            raise ValueError(f"v0.13 registration artifact {label} changed")
    return audit


def load_authorization(path: str | Path) -> dict[str, object]:
    payload = load_json_object(path)
    validate_authorization(payload)
    validate_registration_bundle()
    return payload
