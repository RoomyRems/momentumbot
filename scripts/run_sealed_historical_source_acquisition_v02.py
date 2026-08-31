from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from momentumbot.providers.request_budget import load_provider_request_budget
from momentumbot.research.sealed_historical_source_acquisition import (
    retained_tree_bytes,
    summarize_source_root,
    write_json_once,
)
from momentumbot.research.sealed_historical_source_acquisition_v02 import (
    build_acquisition_report,
    load_authorization,
    validate_parent_bundle,
)
from momentumbot.research.sealed_historical_walk_forward import load_json_object


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUTHORIZATION = ROOT / "research/strategy/sealed-historical-source-acquisition-v0.2.json"
DEFAULT_CONTRACT = ROOT / "research/strategy/sealed-historical-walk-forward-v0.1.json"
DEFAULT_AVAILABILITY_REPORT = ROOT / "research/data-audits/sealed-historical-provider-availability-v0.2-report-2026-08-31.json"
DEFAULT_AVAILABILITY_AUDIT = ROOT / "research/data-audits/sealed-historical-provider-availability-v0.2-success-2026-08-31.json"
DEFAULT_V01_AUTHORIZATION = ROOT / "research/strategy/sealed-historical-source-acquisition-v0.1.json"
DEFAULT_V01_FAILURE_REPORT = ROOT / "research/data-audits/sealed-historical-source-acquisition-v0.1-failure-report-2026-08-31.json"
DEFAULT_V01_FAILURE_AUDIT = ROOT / "research/data-audits/sealed-historical-source-acquisition-v0.1-failure-2026-08-31.json"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--authorization", type=Path, default=DEFAULT_AUTHORIZATION)
    result.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    result.add_argument("--availability-report", type=Path, default=DEFAULT_AVAILABILITY_REPORT)
    result.add_argument("--availability-success-audit", type=Path, default=DEFAULT_AVAILABILITY_AUDIT)
    result.add_argument("--v0-1-authorization", type=Path, default=DEFAULT_V01_AUTHORIZATION)
    result.add_argument("--v0-1-failure-report", type=Path, default=DEFAULT_V01_FAILURE_REPORT)
    result.add_argument("--v0-1-failure-audit", type=Path, default=DEFAULT_V01_FAILURE_AUDIT)
    result.add_argument("--validate-only", action="store_true")
    result.add_argument("--source-root", type=Path)
    result.add_argument("--request-budget", type=Path)
    result.add_argument("--authorization-commit-sha")
    result.add_argument("--output", type=Path)
    return result


def main() -> None:
    args = parser().parse_args()
    authorization = load_authorization(str(args.authorization))
    validate_parent_bundle(
        contract=load_json_object(args.contract),
        availability_report=load_json_object(args.availability_report),
        availability_success_audit=load_json_object(args.availability_success_audit),
        v01_authorization=load_json_object(args.v0_1_authorization),
        failure_report=load_json_object(args.v0_1_failure_report),
        failure_audit=load_json_object(args.v0_1_failure_audit),
    )
    if args.validate_only:
        print(
            json.dumps(
                {
                    "authorization_id": authorization["authorization_id"],
                    "authorization_content_sha256": authorization["content_sha256"],
                    "selected_date_count": len(authorization["frozen_parent"]["selected_dates"]),
                    "maximum_total_http_attempts": authorization["request_budget"]["maximum_total_http_attempts_including_retries"],
                    "maximum_retained_bytes": authorization["retention_budget"]["maximum_retained_bytes"],
                    "provider_calls": 0,
                    "v0_1_rerun": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return
    required = (
        args.source_root,
        args.request_budget,
        args.authorization_commit_sha,
        args.output,
    )
    if any(value is None for value in required):
        raise SystemExit("report mode requires source, budget, commit, and output")
    report = build_acquisition_report(
        authorization=authorization,
        source_summary=summarize_source_root(args.source_root),
        request_budget=load_provider_request_budget(args.request_budget),
        retained_bytes=retained_tree_bytes(args.source_root),
        repository=os.environ.get("GITHUB_REPOSITORY", ""),
        authorization_commit_sha=str(args.authorization_commit_sha),
        workflow_run_id=os.environ.get("GITHUB_RUN_ID", ""),
        workflow_run_attempt=int(os.environ.get("GITHUB_RUN_ATTEMPT", "0")),
    )
    write_json_once(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
