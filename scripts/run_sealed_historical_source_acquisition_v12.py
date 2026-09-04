"""Provider-free final-freeze recovery runner for v0.12."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

from momentumbot.historical_float_identity_v11 import (
    summarize_source_root_identity_compatible_v11,
)
from momentumbot.historical_profile_union_v01 import historical_profile_union_v0_1
from momentumbot.research.sealed_historical_source_acquisition import (
    retained_tree_bytes,
    write_json_once,
)
from momentumbot.research.sealed_historical_source_acquisition_v12 import (
    PARENT_CHECKPOINT_FILE_SHA256,
    PARENT_PROVENANCE,
    build_recovery_report_v12,
    file_sha256,
    validate_recovery_environment_pair_v12,
)
from momentumbot.research.sealed_historical_source_authorization_v12 import (
    AUTHORIZATION_CONTENT_SHA256,
    AUTHORIZATION_ID,
    AUTHORIZATION_PATH,
    EXPECTED_DISPATCHER_WORKFLOW_REF,
    ROOT,
    canonical_fingerprint,
    load_authorization,
)
from momentumbot.research.sealed_historical_source_checkpoint_v01 import (
    load_json_object,
)
from momentumbot.research.sealed_historical_source_checkpoint_v10 import (
    build_post_scanner_checkpoint_binding_v10,
    load_authorization_envelope_v10,
    normalize_blocked_attempt_ledger,
    normalize_composite_request_budget,
    output_is_outside_source_root,
)


EXPECTED_REPOSITORY = "RoomyRems/momentumbot"
EXPECTED_AUTHORIZATION_PATH = AUTHORIZATION_PATH.as_posix()
EXPECTED_BRANCH = "phase-3-historical-snapshot"
EXPECTED_WORKFLOW_PATH = (
    ".github/workflows/sealed-historical-source-acquisition-v12.yml"
)
PARENT_AUTHORIZATION = (
    ROOT / "research/strategy/sealed-historical-source-acquisition-v0.10.json"
)
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_RUN_ID = re.compile(r"^[1-9][0-9]*$")


def _strict_provenance(
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
        raise ValueError("v0.12 repository changed")
    for label, value in (
        ("authorization commit", authorization_commit_sha),
        ("authorization tree", authorization_tree_sha),
        ("dispatcher workflow", dispatcher_workflow_sha),
    ):
        if _GIT_SHA.fullmatch(value) is None:
            raise ValueError(f"{label} must be a canonical Git SHA")
    if dispatcher_workflow_ref != EXPECTED_DISPATCHER_WORKFLOW_REF:
        raise ValueError("v0.12 dispatcher workflow ref changed")
    if _RUN_ID.fullmatch(workflow_run_id) is None:
        raise ValueError("v0.12 workflow run ID is invalid")
    if isinstance(workflow_run_attempt, bool) or workflow_run_attempt != 1:
        raise ValueError("v0.12 is attempt 1 only")
    return {
        "repository": repository,
        "authorization_commit_sha": authorization_commit_sha,
        "authorization_tree_sha": authorization_tree_sha,
        "dispatcher_workflow_sha": dispatcher_workflow_sha,
        "dispatcher_workflow_ref": dispatcher_workflow_ref,
        "workflow_run_id": workflow_run_id,
        "workflow_run_attempt": workflow_run_attempt,
    }


def build_safe_failure_v12(
    *,
    provenance: dict[str, object],
    scanner_snapshot_present: bool,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "artifact_type": "sealed_historical_source_recovery_v0_12_safe_failure",
        "authorization": {
            "authorization_id": AUTHORIZATION_ID,
            "authorization_content_sha256": AUTHORIZATION_CONTENT_SHA256,
        },
        "parent_provider_checkpoint": {
            "artifact_id": 9_877_181_150,
            "zip_sha256": (
                "b13bb68c5c231ba51b73c63d2a0d7e73fa78a0a837d4e35b94a55ddf5006b3b3"
            ),
            "remains_immutable": True,
        },
        "failed_execution_parent": {
            "authorization_id": "sealed-historical-source-acquisition-v0.11",
            "failure_artifact_id": 9_957_636_441,
            "failure_audit_content_sha256": (
                "c901ff41eda568af3941d4e91adac65b4d7e9d519d2377a8a96e161c734b4a82"
            ),
            "rerun_allowed": False,
            "workflow_run_id": 33_928_334_660,
        },
        "workflow_provenance": provenance,
        "progress": {
            "scanner_snapshot_present": scanner_snapshot_present,
            "final_report_completed": False,
        },
        "causal_attestation": {
            "account_or_order_endpoint_called": False,
            "automatic_rerun_allowed": False,
            "databento_called": False,
            "order_submitted": False,
            "provider_calls": 0,
            "ross_labels_or_outcomes_read": False,
            "transcript_record_values_read": False,
        },
    }
    payload["content_sha256"] = canonical_fingerprint(payload)
    return payload


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--authorization", type=Path, default=ROOT / AUTHORIZATION_PATH)
    result.add_argument("--validate-only", action="store_true")
    result.add_argument("--write-safe-failure", action="store_true")
    result.add_argument("--source-root", type=Path)
    result.add_argument("--source-checkpoint", type=Path)
    result.add_argument("--parent-recovery-receipt", type=Path)
    result.add_argument("--normalization-diagnostics", type=Path)
    result.add_argument("--request-budget", type=Path)
    result.add_argument("--blocked-attempt-ledger", type=Path)
    result.add_argument("--parent-environment-freeze", type=Path)
    result.add_argument("--child-environment-freeze", type=Path)
    result.add_argument("--requirements", type=Path)
    result.add_argument("--authorization-commit-sha", default="")
    result.add_argument("--authorization-tree-sha", default="")
    result.add_argument("--dispatcher-workflow-sha", default="")
    result.add_argument("--dispatcher-workflow-ref", default="")
    result.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    result.add_argument("--workflow-run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    result.add_argument(
        "--workflow-run-attempt",
        type=int,
        default=int(os.environ.get("GITHUB_RUN_ATTEMPT", "0")),
    )
    result.add_argument("--output", type=Path)
    return result


def _required_path(value: Path | None, *, label: str) -> Path:
    if value is None:
        raise SystemExit(f"{label} is required in this mode")
    if value.is_symlink() or not value.is_file():
        raise ValueError(f"{label} must be a regular file")
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    authorization = load_authorization(args.authorization)
    if authorization.get("content_sha256") != AUTHORIZATION_CONTENT_SHA256:
        raise ValueError("v0.12 authorization constants disagree")
    if args.validate_only:
        print(
            json.dumps(
                {
                    "authorization_id": AUTHORIZATION_ID,
                    "authorization_content_sha256": AUTHORIZATION_CONTENT_SHA256,
                    "additional_provider_calls_authorized": 0,
                    "parent_provider_checkpoint_artifact_id": 9_877_181_150,
                    "v0_10_rerun": False,
                    "v0_11_rerun": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    provenance = _strict_provenance(
        repository=args.repository,
        authorization_commit_sha=args.authorization_commit_sha,
        authorization_tree_sha=args.authorization_tree_sha,
        dispatcher_workflow_sha=args.dispatcher_workflow_sha,
        dispatcher_workflow_ref=args.dispatcher_workflow_ref,
        workflow_run_id=args.workflow_run_id,
        workflow_run_attempt=args.workflow_run_attempt,
    )
    if args.output is None:
        raise SystemExit("output is required in this mode")
    if args.write_safe_failure:
        scanner_present = bool(
            args.source_root
            and (args.source_root / "causal-scanner-snapshot-v0.3/manifest.json").is_file()
        )
        write_json_once(
            args.output,
            build_safe_failure_v12(
                provenance=provenance,
                scanner_snapshot_present=scanner_present,
            ),
        )
        return 0
    if args.source_root is None or args.source_root.is_symlink() or not args.source_root.is_dir():
        raise ValueError("source root must be a regular directory")
    if not output_is_outside_source_root(args.output, args.source_root):
        raise ValueError("v0.12 report must stay outside the source root")
    source_checkpoint = _required_path(
        args.source_checkpoint, label="source checkpoint"
    )
    recovery = _required_path(
        args.parent_recovery_receipt, label="parent recovery receipt"
    )
    diagnostics = _required_path(
        args.normalization_diagnostics, label="normalization diagnostics"
    )
    request_budget = _required_path(args.request_budget, label="request budget")
    blocked = _required_path(
        args.blocked_attempt_ledger, label="blocked-attempt ledger"
    )
    parent_environment = _required_path(
        args.parent_environment_freeze, label="parent environment freeze"
    )
    child_environment = _required_path(
        args.child_environment_freeze, label="child environment freeze"
    )
    requirements = _required_path(args.requirements, label="requirements")
    if file_sha256(source_checkpoint) != PARENT_CHECKPOINT_FILE_SHA256:
        raise ValueError("v0.10 source checkpoint file hash changed")
    environment = validate_recovery_environment_pair_v12(
        parent_environment_freeze_path=parent_environment,
        child_environment_freeze_path=child_environment,
        expected_child_commit_sha=args.authorization_commit_sha,
    )
    checkpoint = load_json_object(source_checkpoint)
    request_payload = load_json_object(request_budget)
    blocked_payload = load_json_object(blocked)
    if request_payload != PARENT_REQUEST_BUDGET:
        raise ValueError("external request ledger differs from frozen v0.10 ledger")
    if normalize_composite_request_budget(request_payload) != checkpoint.get(
        "request_budget"
    ):
        raise ValueError("external request ledger differs from v0.10 checkpoint")
    if normalize_blocked_attempt_ledger(
        blocked_payload, require_zero=True
    ) != checkpoint.get("blocked_attempts"):
        raise ValueError("external blocked-attempt ledger differs from checkpoint")
    parent_authorization = load_authorization_envelope_v10(PARENT_AUTHORIZATION)
    binding = build_post_scanner_checkpoint_binding_v10(
        checkpoint,
        checkpoint_file_sha256=file_sha256(source_checkpoint),
        checkpoint_output_path=source_checkpoint,
        source_root=args.source_root,
        authorization=parent_authorization,
        recovery_receipt_path=recovery,
        normalization_diagnostic_path=diagnostics,
        expected_provenance=PARENT_PROVENANCE,
        environment_freeze_path=parent_environment,
        requirements_path=requirements,
    )
    summary, preflight = summarize_source_root_identity_compatible_v11(
        args.source_root,
        profile=historical_profile_union_v0_1(),
    )
    report = build_recovery_report_v12(
        authorization_id=AUTHORIZATION_ID,
        authorization_content_sha256=AUTHORIZATION_CONTENT_SHA256,
        parent_checkpoint_binding=binding,
        source_summary=summary,
        identity_preflight=preflight,
        environment_comparison=environment,
        retained_bytes=retained_tree_bytes(args.source_root),
        **provenance,
    )
    write_json_once(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
