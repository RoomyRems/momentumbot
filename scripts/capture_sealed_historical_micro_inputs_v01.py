"""Validate or execute the separately consumed historical Micro-input capture."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys

from run_offline_python_v13 import deny_external_io
from momentumbot.research.sealed_historical_micro_inputs_v01 import (
    BoundedHTTP, CaptureError, CONTRACT_ID, CONTRACT_RELATIVE, CONSUMPTION_REF,
    EXECUTION_RELATIVE, PLAN_RELATIVE, acquire, derive_requests, file_sha,
    frozen, seal, validate_contract, write_json,
)
from momentumbot.research.sealed_historical_scanner_micro_runtime_v02 import MISSING_MICRO_INPUTS, validate_final_snapshot

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ".github/workflows/sealed-historical-micro-input-acquisition-v01.yml"


def expected_source_receipt(contract: dict) -> dict:
    return seal({"contract_content_sha256": contract["content_sha256"],
                 "source_validation": {"schema_version": 1, "source_verified": True,
                     "scanner_snapshot_ready": True, "micro_v0_1_runtime_ready": False,
                     "missing_required_inputs": list(MISSING_MICRO_INPUTS),
                     "provider_calls": 0, "runtime_started": False}})


def execution_payload(contract: dict, *, code_commit: str, code_tree: str, workflow_sha256: str) -> dict:
    for value, length in ((code_commit, 40), (code_tree, 40), (workflow_sha256, 64)):
        if not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
            raise ValueError("execution provenance must contain exact full hashes")
    return seal({
        "schema_version": 1, "execution_id": CONTRACT_ID + "-execution",
        "contract_content_sha256": contract["content_sha256"],
        "code_commit_sha": code_commit, "code_tree_sha": code_tree,
        "workflow_file_sha256": workflow_sha256,
        "workflow_path": WORKFLOW, "repository": "RoomyRems/momentumbot",
        "branch": "phase-3-historical-snapshot", "event": "push", "run_attempt": 1,
        "consumption_ref": CONSUMPTION_REF,
        "authority": "user_authorized_continued_development_and_operational_steps_2026-09-06",
        "market_data_capture_authorized": True, "incremental_provider_cost_usd": "0",
        "broker_or_order_authority": False, "policy_change_authority": False,
        "retrospective_input_authority": False,
    })


def validate_execution(contract: dict) -> dict:
    observed = frozen(ROOT / EXECUTION_RELATIVE)
    expected = execution_payload(
        contract, code_commit=os.environ.get("EXECUTION_CODE_COMMIT_SHA", ""),
        code_tree=os.environ.get("EXECUTION_CODE_TREE_SHA", ""),
        workflow_sha256=file_sha(ROOT / WORKFLOW),
    )
    if observed != expected:
        raise ValueError("execution child differs from the tested code or workflow")
    if (os.environ.get("GITHUB_REPOSITORY") != expected["repository"]
            or os.environ.get("GITHUB_EVENT_NAME") != "push"
            or os.environ.get("GITHUB_REF") != "refs/heads/phase-3-historical-snapshot"
            or os.environ.get("GITHUB_RUN_ATTEMPT") != "1"
            or not re.fullmatch(r"[0-9]+", os.environ.get("GITHUB_RUN_ID", ""))
            or not re.fullmatch(r"[0-9a-f]{40}", os.environ.get("GITHUB_SHA", ""))):
        raise ValueError("capture requires the exact first-attempt research push")
    return observed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-only", action="store_true")
    mode.add_argument("--verify-source", type=Path)
    mode.add_argument("--acquire", action="store_true")
    parser.add_argument("--check-execution", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--consumption-marker", type=Path)
    parser.add_argument("--source-receipt", type=Path)
    args = parser.parse_args()
    if not args.acquire:
        sys.addaudithook(deny_external_io)
    contract = validate_contract(ROOT)
    if args.check_execution or args.acquire:
        authorization = validate_execution(contract)
    if args.validate_only:
        print(json.dumps({"contract_id": CONTRACT_ID, "contract_valid": True, "provider_calls": 0}))
        return 0
    if args.verify_source:
        source = validate_final_snapshot(args.verify_source)
        receipt = expected_source_receipt(contract)
        if source != receipt["source_validation"]:
            raise CaptureError("full source validation differs from the registered gate")
        print(json.dumps(receipt, sort_keys=True))
        return 0
    if args.output is None or args.consumption_marker is None or args.source_receipt is None:
        parser.error("capture requires output, consumption marker, and verified source receipt")
    marker = frozen(args.consumption_marker)
    source = frozen(args.source_receipt)
    expected_marker = seal({"execution_content_sha256": authorization["content_sha256"],
                            "consumption_ref": CONSUMPTION_REF,
                            "execution_commit_sha": os.environ["GITHUB_SHA"],
                            "workflow_run_id": os.environ["GITHUB_RUN_ID"], "workflow_run_attempt": 1})
    if marker != expected_marker or source != expected_source_receipt(contract):
        raise CaptureError("source or durable consumption receipt differs")
    if args.output.exists() and (not args.output.is_dir() or any(args.output.iterdir())):
        raise CaptureError("capture output must be new and empty")
    fetch = BoundedHTTP(args.output, key=os.environ.get("ALPACA_API_KEY", ""), secret=os.environ.get("ALPACA_API_SECRET", ""))
    provenance = {"execution_content_sha256": authorization["content_sha256"],
                  "execution_commit_sha": os.environ["GITHUB_SHA"],
                  "code_commit_sha": authorization["code_commit_sha"],
                  "code_tree_sha": authorization["code_tree_sha"],
                  "workflow_run_id": os.environ["GITHUB_RUN_ID"], "workflow_run_attempt": 1,
                  "consumption_marker_content_sha256": marker["content_sha256"],
                  "source_validation_content_sha256": source["content_sha256"]}
    try:
        report = acquire(derive_requests(ROOT / PLAN_RELATIVE), args.output, fetch, contract=contract, provenance=provenance)
        print(json.dumps({"status": report["status"], "logical_requests_completed": report["logical_requests_completed"], "provider_attempts": fetch.attempts}))
    finally:
        if args.output.is_dir():
            fetch.save_ledger()
            for source_path, name in [(args.consumption_marker, "consumption.json"), (args.source_receipt, "source-validation.json"), (ROOT / EXECUTION_RELATIVE, "execution.json"), (ROOT / CONTRACT_RELATIVE, "contract.json")]:
                shutil.copyfile(source_path, args.output / name)
            files = {p.relative_to(args.output).as_posix(): file_sha(p) for p in sorted(args.output.rglob("*")) if p.is_file()}
            write_json(args.output / "capture-inventory.json", seal({"files": files, "provenance": provenance,
                        "complete": (args.output / "capture-report.json").exists(),
                        "provider_attempts": fetch.attempts, "blocked_attempts": fetch.blocked,
                        "micro_runtime_executed": False, "backtesting_executed": False}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status": "failed", "exception_class": type(exc).__name__,
                          "sanitized_error": str(exc) if isinstance(exc, CaptureError) else "capture preflight or validation failed"}), file=sys.stderr)
        raise SystemExit(1) from None
