"""Build or revalidate the provider-free v0.6 pre-scanner checkpoint."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from momentumbot.research.sealed_historical_source_checkpoint_v01 import (
    load_json_object,
)
from momentumbot.research.sealed_historical_source_checkpoint_v06 import (
    build_source_checkpoint_v06,
    load_authorization_envelope_v06,
    normalize_blocked_attempt_ledger,
    normalize_composite_request_budget,
    output_is_outside_source_root,
    validate_source_checkpoint_v06,
    write_checkpoint_once,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUTHORIZATION = (
    ROOT / "research/strategy/sealed-historical-source-acquisition-v0.6.json"
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--source-root", type=Path, required=True)
    result.add_argument("--parent-recovery-receipt", type=Path, required=True)
    result.add_argument("--normalization-diagnostics", type=Path, required=True)
    result.add_argument("--request-budget", type=Path, required=True)
    result.add_argument("--blocked-attempt-ledger", type=Path, required=True)
    result.add_argument("--environment-freeze", type=Path, required=True)
    result.add_argument("--requirements", type=Path, required=True)
    result.add_argument("--authorization", type=Path, default=DEFAULT_AUTHORIZATION)
    result.add_argument("--authorization-commit-sha", required=True)
    result.add_argument("--authorization-tree-sha", required=True)
    result.add_argument("--dispatcher-workflow-sha", required=True)
    result.add_argument("--dispatcher-workflow-ref", required=True)
    result.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    result.add_argument("--workflow-run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    result.add_argument(
        "--workflow-run-attempt",
        type=int,
        default=int(os.environ.get("GITHUB_RUN_ATTEMPT", "0")),
    )
    result.add_argument("--validate-existing", action="store_true")
    result.add_argument("--output", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not output_is_outside_source_root(args.output, args.source_root):
        raise ValueError("checkpoint output must be outside the source root")
    authorization = load_authorization_envelope_v06(args.authorization)
    request_budget = load_json_object(args.request_budget)
    blocked = load_json_object(args.blocked_attempt_ledger)
    provenance = {
        "repository": args.repository,
        "authorization_commit_sha": args.authorization_commit_sha,
        "authorization_tree_sha": args.authorization_tree_sha,
        "dispatcher_workflow_sha": args.dispatcher_workflow_sha,
        "dispatcher_workflow_ref": args.dispatcher_workflow_ref,
        "workflow_run_id": args.workflow_run_id,
        "workflow_run_attempt": args.workflow_run_attempt,
    }
    if args.validate_existing:
        checkpoint = load_json_object(args.output)
        validate_source_checkpoint_v06(
            checkpoint,
            recovery_receipt_path=args.parent_recovery_receipt,
            normalization_diagnostic_path=args.normalization_diagnostics,
            environment_freeze_path=args.environment_freeze,
            requirements_path=args.requirements,
            checkpoint_output_path=args.output,
            source_root=args.source_root,
            authorization=authorization,
            expected_provenance=provenance,
        )
        if checkpoint.get("request_budget") != normalize_composite_request_budget(
            request_budget
        ):
            raise ValueError("external composite request ledger differs from checkpoint")
        if checkpoint.get("blocked_attempts") != normalize_blocked_attempt_ledger(
            blocked,
            require_zero=True,
        ):
            raise ValueError("external blocked-attempt ledger differs from checkpoint")
        print(
            json.dumps(
                {
                    "artifact_id": checkpoint["artifact_id"],
                    "content_sha256": checkpoint["content_sha256"],
                    "provider_calls": 0,
                    "validated_existing": True,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    checkpoint = build_source_checkpoint_v06(
        source_root=args.source_root,
        authorization=authorization,
        recovery_receipt_path=args.parent_recovery_receipt,
        normalization_diagnostic_path=args.normalization_diagnostics,
        request_budget=request_budget,
        blocked_attempt_ledger=blocked,
        environment_freeze_path=args.environment_freeze,
        requirements_path=args.requirements,
        checkpoint_output_path=args.output,
        **provenance,
    )
    write_checkpoint_once(args.output, checkpoint)
    print(
        json.dumps(
            {
                "artifact_id": checkpoint["artifact_id"],
                "authorization": checkpoint["authorization"],
                "content_sha256": checkpoint["content_sha256"],
                "file_count": checkpoint["inventory"]["file_count"],
                "provider_calls": 0,
                "total_retained_bytes": checkpoint["total_retained_bytes"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
