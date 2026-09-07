"""Validate, consume, or quote the exact historical management exit request plan."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys

from run_offline_python_v13 import deny_external_io
from momentumbot.research.sealed_historical_management_exit_quote_v01 import (
    CONTRACT_PATH, EXECUTION_PATH, LOCK_PATH, PLAN_PATH, REUSE_PATH, REUSE_FILE_SHA256, SDK_VERSION,
    build_report, collect_quote, consumption_payload, file_sha, frozen, require_exact,
    seal, validate_execution, validate_inputs, validate_report, write_json,
)
from momentumbot.research.sealed_historical_management_exit_metadata_transport_v01 import MetadataOnlyHTTP, sdk_metadata

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--validate-only", action="store_true")
    modes.add_argument("--consume", action="store_true")
    modes.add_argument("--quote", action="store_true")
    parser.add_argument("--check-execution", action="store_true")
    parser.add_argument("--preflight-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    if not args.quote:
        sys.addaudithook(deny_external_io)
    requests = validate_inputs(ROOT)
    if args.check_execution or args.consume or args.quote:
        execution = validate_execution(ROOT, os.environ)
    if args.validate_only:
        print(json.dumps({"valid": True, "request_count": len(requests), "provider_calls": 0}))
        return 0
    if args.preflight_root is None:
        parser.error("consumption evidence directory is required")
    expected_marker = consumption_payload(execution, os.environ)
    if args.consume:
        ref = json.loads((args.preflight_root / "consumption-ref.json").read_text())
        if ref.get("ref") != expected_marker["consumption_ref"] or ref.get("object", {}).get("sha") != os.environ["GITHUB_SHA"]:
            raise ValueError("exact atomic consumption ref is required")
        write_json(args.preflight_root / "consumption.json", expected_marker)
        for path, name in ((ROOT / EXECUTION_PATH, "execution.json"), (ROOT / CONTRACT_PATH, "contract.json"),
                           (ROOT / LOCK_PATH, LOCK_PATH),
                           (ROOT / PLAN_PATH / "request-manifest.json", "request-manifest.json"),
                           (ROOT / REUSE_PATH, "xage-reuse.json")):
            shutil.copyfile(path, args.preflight_root / name)
        return 0
    marker = frozen(args.preflight_root / "consumption.json")
    require_exact(marker, expected_marker, "durable consumption")
    if args.output_root is None:
        parser.error("quote output directory is required")
    output = args.output_root
    if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
        raise ValueError("quote output must be new and empty")
    output.mkdir(parents=True, exist_ok=True)
    for path, name in ((args.preflight_root / "consumption.json", "consumption.json"),
                       (ROOT / EXECUTION_PATH, "execution.json"), (ROOT / CONTRACT_PATH, "contract.json"),
                       (ROOT / PLAN_PATH / "request-manifest.json", "request-manifest.json"),
                       (ROOT / REUSE_PATH, "xage-reuse.json")):
        shutil.copyfile(path, output / name)
    provenance = {"execution_content_sha256": execution["content_sha256"],
                  "execution_commit_sha": os.environ["GITHUB_SHA"],
                  "code_commit_sha": execution["code_commit_sha"], "code_tree_sha": execution["code_tree_sha"],
                  "workflow_run_id": os.environ["GITHUB_RUN_ID"], "workflow_run_attempt": 1,
                  "consumption_content_sha256": marker["content_sha256"],
                  "reuse_evidence_file_sha256": REUSE_FILE_SHA256}
    key = os.environ.get("DATABENTO_API_KEY", "")
    preflight_error, transport, calls = None, None, []
    session = None
    if not key:
        preflight_error = "credential_missing"
    else:
        try:
            import databento
            import requests as http
        except Exception:
            preflight_error = "sdk_unavailable"
        else:
            if databento.__version__ != SDK_VERSION:
                preflight_error = "sdk_version_mismatch"
            else:
                try:
                    session = http.Session()
                    session.trust_env = False
                    transport = MetadataOnlyHTTP(requests, session=session, key=key,
                        progress=lambda value: write_json(output / "http-ledger.json", value, replace=True))
                    metadata = sdk_metadata(transport)
                except Exception:
                    preflight_error = "client_initialization_failed"
    try:
        if preflight_error is None:
            calls = collect_quote(requests, metadata,
                progress=lambda value: write_json(output / "metadata-ledger.json", value, replace=True))
        report = build_report(requests, calls, provenance=provenance,
                              http_attempts=len(transport.attempts) if transport else 0,
                              blocked_attempts=transport.blocked if transport else 0,
                              preflight_error=preflight_error)
        validate_report(report, requests, provenance)
        if key and key in json.dumps(report, sort_keys=True):
            raise ValueError("sanitized quote serialization rejected")
        write_json(output / "quote-report.json", report)
    finally:
        if session is not None:
            session.close()
        if transport is not None:
            transport.save()
        files = {p.relative_to(output).as_posix(): file_sha(p) for p in sorted(output.rglob("*")) if p.is_file()}
        write_json(output / "quote-inventory.json", seal({"files": files, "provenance": provenance,
                    "terminal_report_retained": (output / "quote-report.json").is_file(),
                    "timeseries_acquired": False, "account_or_fill_simulation_executed": False}))
    print(json.dumps({"status": report["status"], "metadata_calls": report["metadata_call_count"],
                      "http_attempts": report["http_attempts"], "available_requests": report["available_request_count"],
                      "total_quoted_cost_usd": report["total_quoted_cost_usd"]}))
    return 0 if report["metadata_quote_gate_passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print('{"status":"failed","sanitized_error":"metadata quote preflight or validation failed"}', file=sys.stderr)
        raise SystemExit(1) from None
