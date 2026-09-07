"""Validate, capture once, or verify the exact missing management inputs."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from run_offline_python_v13 import deny_external_io

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-only", action="store_true")
    mode.add_argument("--verify-reuse", action="store_true")
    mode.add_argument("--acquire", action="store_true")
    mode.add_argument("--verify-archive", type=Path)
    parser.add_argument("--check-execution", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--consumption-marker", type=Path)
    parser.add_argument("--source-receipt", type=Path)
    parser.add_argument("--execution-commit")
    parser.add_argument("--run-id")
    args = parser.parse_args()
    if not args.acquire:
        sys.addaudithook(deny_external_io)
    from momentumbot.research import sealed_historical_management_capture_v01 as m

    contract = m.validate_contract(ROOT)
    if args.check_execution or args.acquire:
        execution = m.validate_execution(ROOT, contract, dict(os.environ))
    if args.validate_only:
        print(json.dumps({"contract_id": m.CONTRACT_ID, "contract_valid": True, "provider_calls": 0}))
        return 0
    if args.verify_reuse:
        print(json.dumps(m.verify_reuse_result(ROOT), sort_keys=True))
        return 0
    if args.verify_archive:
        if not args.execution_commit or not args.run_id:
            parser.error("archive verification requires exact execution commit and run ID")
        print(json.dumps(m.verify_archive(ROOT, args.verify_archive,
            execution_commit=args.execution_commit, run_id=args.run_id), sort_keys=True))
        return 0
    if args.output is None or args.consumption_marker is None or args.source_receipt is None:
        parser.error("capture requires output, consumption marker and verified reuse receipt")
    marker, source_receipt = m.frozen(args.consumption_marker), m.frozen(args.source_receipt)
    m.require_exact(marker, m.consumption_payload(execution, commit=os.environ["GITHUB_SHA"],
        run_id=os.environ["GITHUB_RUN_ID"]), "durable consumption receipt")
    m.require_exact(source_receipt, m.verify_reuse_result(ROOT), "verified reuse receipt")
    if args.output.is_symlink() or any(p.is_symlink() for p in args.output.parents):
        raise m.CaptureError("capture output cannot use symbolic links")
    if args.output.exists() and (not args.output.is_dir() or any(args.output.iterdir())):
        raise m.CaptureError("capture output must be new and empty")
    fetch = m.BoundedHTTP(args.output, requests=contract["requests"],
        key=os.environ.get("ALPACA_API_KEY", ""), secret=os.environ.get("ALPACA_API_SECRET", ""))
    provenance = {"execution_content_sha256": execution["content_sha256"],
        "execution_commit_sha": os.environ["GITHUB_SHA"], "code_commit_sha": execution["code_commit_sha"],
        "code_tree_sha": execution["code_tree_sha"], "workflow_run_id": os.environ["GITHUB_RUN_ID"],
        "workflow_run_attempt": 1, "consumption_marker_content_sha256": marker["content_sha256"],
        "source_validation_content_sha256": source_receipt["content_sha256"]}
    try:
        report = m.acquire(contract["requests"], args.output, fetch, contract=contract, provenance=provenance)
        print(json.dumps({"status": report["status"], "logical_requests_completed": 10,
            "provider_attempts": fetch.attempts, "normalized_compressed_bytes": report["normalized_compressed_bytes"]}))
    finally:
        if args.output.is_dir():
            fetch.save_ledger()
            for name, value in (("consumption.json", marker), ("source-validation.json", source_receipt),
                                ("execution.json", execution), ("contract.json", contract)):
                m.write_json(args.output / name, value)
            files = {p.relative_to(args.output).as_posix(): m.file_sha(p)
                     for p in sorted(args.output.rglob("*")) if p.is_file()}
            m.write_json(args.output / "capture-inventory.json", m.seal({"files": files, "provenance": provenance,
                "complete": (args.output / "capture-report.json").exists(), "provider_attempts": fetch.attempts,
                "blocked_attempts": fetch.blocked, **m.BOUNDARY}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status": "failed", "exception_class": type(exc).__name__,
            "sanitized_error": "management capture or verification failed; no retry"}), file=sys.stderr)
        raise SystemExit(1) from None
