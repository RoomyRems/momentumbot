from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


TIMEOUT_SECONDS = 30
USER_AGENT = "MomentumBot/0.2 massive-universe-capability-audit"
OFFICIAL_DOC = "https://massive.com/docs/rest/stocks/tickers/all-tickers"
TARGET_DATES = ("2025-04-03", "2026-07-09")


def _credential() -> tuple[str | None, str | None, str]:
    if key := os.getenv("MASSIVE_API_KEY"):
        return key, "MASSIVE_API_KEY", "https://api.massive.com"
    if key := os.getenv("POLYGON_API_KEY"):
        return key, "POLYGON_API_KEY", "https://api.polygon.io"
    return None, None, "https://api.massive.com"


def request_json(
    base_url: str,
    parameters: dict[str, Any],
    api_key: str,
) -> dict[str, Any]:
    query = urllib.parse.urlencode({**parameters, "apiKey": api_key})
    request = urllib.request.Request(
        f"{base_url}/v3/reference/tickers?{query}",
        headers={"User-Agent": USER_AGENT},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            try:
                payload = json.loads(response.read())
            except json.JSONDecodeError:
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


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    try:
        return date.fromisoformat(candidate[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(candidate.replace("Z", "+00:00")).date()
        except ValueError:
            return None


def summarize_response(response: dict[str, Any], requested_date: str) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "requested_date": requested_date,
        "point_in_time_parameter_used": True,
        "ok": bool(response.get("ok")),
        "status": response.get("status"),
    }
    if not summary["ok"]:
        summary["error_kind"] = response.get("error_kind", "provider_request_failed")
        return summary

    payload = response.get("payload")
    if not isinstance(payload, dict):
        summary["payload_shape"] = type(payload).__name__
        return summary

    results = payload.get("results")
    rows = [row for row in results if isinstance(row, dict)] if isinstance(results, list) else []
    fields = sorted({str(field) for row in rows for field in row})
    summary.update(
        {
            "payload_shape": "object",
            "top_level_fields": sorted(str(field) for field in payload),
            "reported_count": payload.get("count") if isinstance(payload.get("count"), int) else None,
            "result_count": len(results) if isinstance(results, list) else None,
            "object_result_count": len(rows),
            "result_fields": fields,
            "next_page_present": bool(payload.get("next_url")),
        }
    )

    field_presence: dict[str, int] = {}
    for field in ("ticker", "active", "market", "locale", "primary_exchange", "type"):
        if field in fields:
            field_presence[field] = sum(
                row.get(field) not in (None, "") for row in rows
            )
    summary["field_presence"] = field_presence
    summary["active_true_count"] = sum(row.get("active") is True for row in rows)
    summary["active_false_count"] = sum(row.get("active") is False for row in rows)

    date_fields: dict[str, dict[str, Any]] = {}
    for field in ("delisted_utc", "last_updated_utc"):
        if field not in fields:
            continue
        present = [row.get(field) for row in rows if row.get(field) not in (None, "")]
        parsed = [parsed for value in present if (parsed := _parse_date(value))]
        date_fields[field] = {
            "present_count": len(present),
            "parseable_count": len(parsed),
            "minimum": min(parsed).isoformat() if parsed else None,
            "maximum": max(parsed).isoformat() if parsed else None,
        }
    summary["date_fields"] = date_fields
    return summary


def assess_capability(snapshots: dict[str, dict[str, Any]]) -> dict[str, Any]:
    checks: dict[str, dict[str, bool]] = {}
    for requested_date, snapshot in snapshots.items():
        fields = set(snapshot.get("result_fields", []))
        result_count = snapshot.get("result_count")
        checks[requested_date] = {
            "request_succeeded": bool(snapshot.get("ok")),
            "rows_observed": isinstance(result_count, int) and result_count > 0,
            "ticker_field_observed": "ticker" in fields,
            "active_field_observed": "active" in fields,
            "primary_exchange_field_observed": "primary_exchange" in fields,
            "type_field_observed": "type" in fields,
            "active_filter_respected_on_sample": bool(
                isinstance(result_count, int)
                and result_count > 0
                and snapshot.get("active_true_count") == result_count
                and snapshot.get("active_false_count") == 0
            ),
        }

    prototype_eligible = bool(checks) and all(
        all(date_checks.values()) for date_checks in checks.values()
    )
    return {
        "checks_by_date": checks,
        "eligible_for_paginated_fetch_prototype": prototype_eligible,
        "full_pagination_audit_required": True,
        "cross_provider_reconciliation_required": True,
        "point_in_time_universe_complete": False,
        "full_walk_forward_eligible": False,
        "policy_promotion_eligible": False,
        "interpretation": (
            "The provider contract and successful samples can authorize a label-blind, "
            "paginated census prototype. Historical completeness is not established until "
            "every page is frozen, typed, fingerprinted and reconciled against independent "
            "membership and market-data evidence."
        ),
    }


def run(
    *,
    api_key: str | None = None,
    credential_name: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    discovered_key, discovered_name, discovered_base = _credential()
    key = api_key or discovered_key
    name = credential_name or discovered_name
    api_base = base_url or discovered_base
    snapshots: dict[str, dict[str, Any]] = {}
    if key:
        for target_date in TARGET_DATES:
            parameters = {
                "market": "stocks",
                "locale": "us",
                "active": "true",
                "date": target_date,
                "order": "asc",
                "sort": "ticker",
                "limit": 10,
            }
            snapshots[target_date] = summarize_response(
                request_json(api_base, parameters, key),
                target_date,
            )

    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "sanitized point-in-time all-tickers capability discovery",
        "knowledge_policy": "provider_schema_only_no_benchmark_labels_no_strategy_feedback",
        "raw_provider_rows_persisted": False,
        "provider": "massive_polygon_reference_tickers",
        "official_doc": OFFICIAL_DOC,
        "credential_name": name,
        "available": bool(key),
        "target_dates": list(TARGET_DATES),
        "snapshots": snapshots,
    }
    if not key:
        report["unavailable_reason"] = "missing MASSIVE_API_KEY or POLYGON_API_KEY"
    report["assessment"] = assess_capability(snapshots)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    key, name, base_url = _credential()
    report = run(api_key=key, credential_name=name, base_url=base_url)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if key:
        rendered = rendered.replace(key, "***")
        rendered = rendered.replace(urllib.parse.quote(key, safe=""), "***")
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
