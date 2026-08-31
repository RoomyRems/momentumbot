from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Mapping

from momentumbot.research.sealed_historical_availability import (
    load_authorization as load_v01_authorization,
)
from momentumbot.research.sealed_historical_availability_v02 import (
    AUTHORIZATION_CONTENT_SHA256,
    AUTHORIZATION_ID,
    build_probe_plan,
    load_authorization,
    run_probe,
    validate_report,
    write_json_once,
)
from momentumbot.research.sealed_historical_walk_forward import load_json_object


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUTHORIZATION = (
    ROOT
    / "research"
    / "strategy"
    / "sealed-historical-provider-availability-v0.2-authorization.json"
)
DEFAULT_REGISTRATION = (
    ROOT / "research" / "strategy" / "sealed-historical-walk-forward-v0.1.json"
)
DEFAULT_V01_AUTHORIZATION = (
    ROOT
    / "research"
    / "strategy"
    / "sealed-historical-provider-availability-v0.1-authorization.json"
)
DEFAULT_V01_REPORT = (
    ROOT
    / "research"
    / "data-audits"
    / "sealed-historical-provider-availability-v0.1-report-2026-08-31.json"
)
DEFAULT_V01_FAILURE_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "sealed-historical-provider-availability-v0.1-failure-2026-08-31.json"
)
ALPACA_URL = "https://data.alpaca.markets/v2/stocks/bars"
TIMEOUT_SECONDS = 30
USER_AGENT = "MomentumBot/0.2 sealed-historical-provider-availability-v0.2"


def request_json(
    parameters: Mapping[str, object], key: str, secret: str
) -> dict[str, object]:
    query = urllib.parse.urlencode(parameters)
    request = urllib.request.Request(
        f"{ALPACA_URL}?{query}",
        headers={
            "User-Agent": USER_AGENT,
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            try:
                payload = json.loads(response.read())
            except (UnicodeDecodeError, json.JSONDecodeError):
                return {
                    "ok": False,
                    "status": response.status,
                    "error_kind": "non_json_response",
                }
            return {"ok": True, "status": response.status, "payload": payload}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "error_kind": "http_error"}
    except Exception as exc:
        return {"ok": False, "status": None, "error_kind": type(exc).__name__}


def _assert_sanitized(rendered: str, secrets: tuple[str, str]) -> None:
    for secret in secrets:
        if secret in rendered or urllib.parse.quote(secret, safe="") in rendered:
            raise ValueError("an Alpaca credential reached the sanitized repair report")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the one-call sealed historical credential-routing repair."
    )
    parser.add_argument("--authorization", type=Path, default=DEFAULT_AUTHORIZATION)
    parser.add_argument("--registration", type=Path, default=DEFAULT_REGISTRATION)
    parser.add_argument(
        "--v01-authorization", type=Path, default=DEFAULT_V01_AUTHORIZATION
    )
    parser.add_argument("--v01-report", type=Path, default=DEFAULT_V01_REPORT)
    parser.add_argument(
        "--v01-failure-audit", type=Path, default=DEFAULT_V01_FAILURE_AUDIT
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repository", default=os.getenv("GITHUB_REPOSITORY", ""))
    parser.add_argument(
        "--authorization-commit-sha", default=os.getenv("GITHUB_SHA", "")
    )
    parser.add_argument("--workflow-run-id", default=os.getenv("GITHUB_RUN_ID", ""))
    parser.add_argument(
        "--workflow-run-attempt",
        type=int,
        default=int(os.getenv("GITHUB_RUN_ATTEMPT", "0")),
    )
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)

    authorization = load_authorization(args.authorization)
    registration = load_json_object(args.registration)
    v01_authorization = load_v01_authorization(args.v01_authorization)
    v01_report = load_json_object(args.v01_report)
    v01_failure_audit = load_json_object(args.v01_failure_audit)
    plan = build_probe_plan(
        authorization=authorization,
        registration=registration,
        v01_authorization=v01_authorization,
        v01_report=v01_report,
        v01_failure_audit=v01_failure_audit,
    )
    if args.validate_only:
        print(
            json.dumps(
                {
                    "authorization_id": AUTHORIZATION_ID,
                    "authorization_content_sha256": AUTHORIZATION_CONTENT_SHA256,
                    "maximum_total_calls": plan["maximum_total_calls"],
                    "provider_calls": 0,
                    "validated": True,
                },
                sort_keys=True,
            )
        )
        return 0
    if args.output is None:
        parser.error("--output is required unless --validate-only is used")
    key = os.getenv("ALPACA_API_KEY")
    secret = os.getenv("ALPACA_API_SECRET")
    if not key or not secret:
        raise RuntimeError("validated main Alpaca credential aliases are unavailable")
    report = run_probe(
        authorization=authorization,
        registration=registration,
        v01_authorization=v01_authorization,
        v01_report=v01_report,
        v01_failure_audit=v01_failure_audit,
        alpaca_request=lambda parameters: request_json(parameters, key, secret),
        repository=args.repository,
        authorization_commit_sha=args.authorization_commit_sha,
        workflow_run_id=args.workflow_run_id,
        workflow_run_attempt=args.workflow_run_attempt,
    )
    validate_report(report, authorization)
    rendered = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    _assert_sanitized(rendered, (key, secret))
    write_json_once(args.output, report)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
