from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from momentumbot.causal_market_discovery_v03 import CAUSAL_MARKET_DISCOVERY_V0_3_POLICY_ID
from momentumbot.causal_scanner_snapshot_v02 import CAUSAL_SCANNER_SNAPSHOT_V0_2_ARTIFACT_ID
from momentumbot.providers.request_budget import load_provider_request_budget
from momentumbot.research.sealed_historical_source_acquisition import (
    retained_tree_bytes,
    write_json_once,
)
from momentumbot.research.sealed_historical_source_acquisition_v03 import (
    build_acquisition_report,
    load_authorization,
    summarize_source_root_v03,
    validate_parent_bundle,
)
from momentumbot.research.sealed_historical_walk_forward import load_json_object


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUTHORIZATION = ROOT / "research/strategy/sealed-historical-source-acquisition-v0.3.json"
DEFAULT_V02_AUTHORIZATION = ROOT / "research/strategy/sealed-historical-source-acquisition-v0.2.json"
DEFAULT_V02_SUCCESS = ROOT / "research/data-audits/sealed-historical-source-acquisition-v0.2-run-33389380992-success-2026-08-31.json"
DEFAULT_SCANNER_FAILURE = ROOT / "research/data-audits/sealed-historical-scanner-runtime-v0.1-normalization-failure-2026-08-31.json"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--authorization", type=Path, default=DEFAULT_AUTHORIZATION)
    result.add_argument("--v0-2-authorization", type=Path, default=DEFAULT_V02_AUTHORIZATION)
    result.add_argument("--v0-2-success-audit", type=Path, default=DEFAULT_V02_SUCCESS)
    result.add_argument("--scanner-failure-audit", type=Path, default=DEFAULT_SCANNER_FAILURE)
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
        v02_authorization=load_json_object(args.v0_2_authorization),
        v02_success_audit=load_json_object(args.v0_2_success_audit),
        scanner_failure_audit=load_json_object(args.scanner_failure_audit),
    )
    if args.validate_only:
        print(json.dumps({
            "authorization_id": authorization["authorization_id"],
            "authorization_content_sha256": authorization["content_sha256"],
            "selected_date_count": len(authorization["frozen_parent"]["selected_dates"]),
            "market_discovery_policy": CAUSAL_MARKET_DISCOVERY_V0_3_POLICY_ID,
            "scanner_policy": CAUSAL_SCANNER_SNAPSHOT_V0_2_ARTIFACT_ID,
            "provider_calls": 0,
            "v0_2_rerun": False,
        }, indent=2, sort_keys=True))
        return
    required = (args.source_root, args.request_budget, args.authorization_commit_sha, args.output)
    if any(value is None for value in required):
        raise SystemExit("report mode requires source, budget, commit, and output")
    summary = summarize_source_root_v03(args.source_root)
    report = build_acquisition_report(
        authorization=authorization,
        source_summary=summary,
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
