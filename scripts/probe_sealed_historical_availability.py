from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from momentumbot.research.sealed_historical_availability import (
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
    / "sealed-historical-provider-availability-v0.1-authorization.json"
)
DEFAULT_REGISTRATION = (
    ROOT / "research" / "strategy" / "sealed-historical-walk-forward-v0.1.json"
)
ALPACA_URL = "https://data.alpaca.markets/v2/stocks/bars"
MASSIVE_URL = "https://api.massive.com/v3/reference/tickers"
POLYGON_URL = "https://api.polygon.io/v3/reference/tickers"
TIMEOUT_SECONDS = 30
USER_AGENT = "MomentumBot/0.2 sealed-historical-provider-availability-v0.1"


def _request_json(
    url: str,
    *,
    parameters: Mapping[str, object],
    headers: Mapping[str, str],
) -> dict[str, object]:
    query = urllib.parse.urlencode(parameters)
    request = urllib.request.Request(
        f"{url}?{query}",
        headers={"User-Agent": USER_AGENT, **headers},
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
        return {
            "ok": False,
            "status": None,
            "error_kind": type(exc).__name__,
        }


def _secrets() -> dict[str, str]:
    names = (
        "ALPACA_API_KEY",
        "ALPACA_API_SECRET",
        "DATABENTO_API_KEY",
        "MASSIVE_API_KEY",
        "POLYGON_API_KEY",
    )
    return {name: value for name in names if (value := os.getenv(name))}


def _validate_credentials(secrets: Mapping[str, str]) -> None:
    required = {"ALPACA_API_KEY", "ALPACA_API_SECRET", "DATABENTO_API_KEY"}
    missing = sorted(required - set(secrets))
    if not ({"MASSIVE_API_KEY", "POLYGON_API_KEY"} & set(secrets)):
        missing.append("MASSIVE_API_KEY_or_POLYGON_API_KEY")
    if missing:
        raise RuntimeError(f"missing required provider credential names: {missing}")


def _assert_sanitized(rendered: str, secrets: Mapping[str, str]) -> None:
    for secret in secrets.values():
        if secret in rendered or urllib.parse.quote(secret, safe="") in rendered:
            raise ValueError("a provider credential reached the sanitized report")


def _build_requests(
    secrets: Mapping[str, str],
) -> tuple[Any, Any]:
    def alpaca(parameters: Mapping[str, object]) -> dict[str, object]:
        return _request_json(
            ALPACA_URL,
            parameters=parameters,
            headers={
                "APCA-API-KEY-ID": secrets["ALPACA_API_KEY"],
                "APCA-API-SECRET-KEY": secrets["ALPACA_API_SECRET"],
            },
        )

    massive_key = secrets.get("MASSIVE_API_KEY")
    massive_url = MASSIVE_URL if massive_key else POLYGON_URL
    key = massive_key or secrets["POLYGON_API_KEY"]

    def massive(parameters: Mapping[str, object]) -> dict[str, object]:
        return _request_json(
            massive_url,
            parameters={**parameters, "apiKey": key},
            headers={},
        )

    return alpaca, massive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the four-call sealed historical provider availability gate."
    )
    parser.add_argument("--authorization", type=Path, default=DEFAULT_AUTHORIZATION)
    parser.add_argument("--registration", type=Path, default=DEFAULT_REGISTRATION)
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
    plan = build_probe_plan(registration, authorization)
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

    secrets = _secrets()
    _validate_credentials(secrets)
    alpaca_request, massive_request = _build_requests(secrets)
    try:
        import databento as db
    except Exception as exc:
        raise RuntimeError("Databento SDK import failed") from exc
    if str(getattr(db, "__version__", "unknown")) != "0.83.0":
        raise RuntimeError("Databento SDK must be exactly 0.83.0")
    client = db.Historical()
    report = run_probe(
        registration=registration,
        authorization=authorization,
        alpaca_request=alpaca_request,
        massive_request=massive_request,
        databento_client=client,
        repository=args.repository,
        authorization_commit_sha=args.authorization_commit_sha,
        workflow_run_id=args.workflow_run_id,
        workflow_run_attempt=args.workflow_run_attempt,
    )
    validate_report(report, authorization, registration)
    rendered = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    _assert_sanitized(rendered, secrets)
    write_json_once(args.output, report)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
