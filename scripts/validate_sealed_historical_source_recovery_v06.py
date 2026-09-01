"""Validate and materialize the exact v0.5 failure checkpoint provider-free."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from momentumbot.research.sealed_historical_source_recovery_v06 import (
    materialize_parent_recovery,
    validate_parent_failure_checkpoint,
    validate_recovery_environment_pair,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--parent-root", type=Path, required=True)
    result.add_argument("--validate-only", action="store_true")
    result.add_argument("--source-output", type=Path)
    result.add_argument("--recovery-receipt-output", type=Path)
    result.add_argument("--request-budget-output", type=Path)
    result.add_argument("--blocked-attempt-output", type=Path)
    result.add_argument("--child-environment-freeze", type=Path)
    result.add_argument("--expected-child-commit-sha")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    environment_values = (
        args.child_environment_freeze,
        args.expected_child_commit_sha,
    )
    if any(value is None for value in environment_values) != all(
        value is None for value in environment_values
    ):
        raise ValueError("child environment validation requires both inputs")
    if args.child_environment_freeze is not None:
        validate_recovery_environment_pair(
            parent_environment_freeze_path=(
                args.parent_root
                / "provider-checkpoint/environment/pip-freeze.txt"
            ),
            child_environment_freeze_path=args.child_environment_freeze,
            expected_child_commit_sha=args.expected_child_commit_sha,
        )
    if args.validate_only:
        if any(
            value is not None
            for value in (
                args.source_output,
                args.recovery_receipt_output,
                args.request_budget_output,
                args.blocked_attempt_output,
            )
        ):
            raise ValueError("validate-only recovery may not write outputs")
        result = validate_parent_failure_checkpoint(args.parent_root)
    else:
        required = (
            args.source_output,
            args.recovery_receipt_output,
            args.request_budget_output,
            args.blocked_attempt_output,
        )
        if any(value is None for value in required):
            raise ValueError("recovery materialization requires every output")
        result = materialize_parent_recovery(
            args.parent_root,
            source_output=args.source_output,
            recovery_receipt_output=args.recovery_receipt_output,
            request_budget_output=args.request_budget_output,
            blocked_attempt_output=args.blocked_attempt_output,
        )
    print(
        json.dumps(
            {
                "artifact_id": result["artifact_id"],
                "candidate_count": result["candidate_count"],
                "content_sha256": result["content_sha256"],
                "dates": len(result["dates"]),
                "provider_calls": 0,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
