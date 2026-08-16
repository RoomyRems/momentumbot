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


BASE_URL = "https://financialmodelingprep.com"
TIMEOUT_SECONDS = 30
USER_AGENT = "MomentumBot/0.2 fmp-universe-capability-audit"

ENDPOINTS: dict[str, tuple[str, dict[str, Any]]] = {
    "current_actively_trading": ("/stable/actively-trading-list", {}),
    "delisted_page_0": (
        "/stable/delisted-companies",
        {"page": 0, "limit": 100},
    ),
    "symbol_changes": ("/stable/symbol-change", {}),
}

OFFICIAL_DOCS = {
    "current_actively_trading": (
        "https://site.financialmodelingprep.com/developer/docs/stable/"
        "actively-trading-list"
    ),
    "delisted_page_0": (
        "https://site.financialmodelingprep.com/developer/docs/stable/"
        "delisted-companies"
    ),
    "symbol_changes": (
        "https://site.financialmodelingprep.com/developer/docs/stable/"
        "symbol-changes-list"
    ),
}


def _normalized_field(field: str) -> str:
    return "".join(character for character in field.lower() if character.isalnum())


def _is_date_field(field: str) -> bool:
    normalized = _normalized_field(field)
    return "date" in normalized or normalized in {"ipo", "delisted", "listed"}


def _is_exchange_field(field: str) -> bool:
    return "exchange" in _normalized_field(field)


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


def request_json(path: str, parameters: dict[str, Any], api_key: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({**parameters, "apikey": api_key})
    request = urllib.request.Request(
        f"{BASE_URL}{path}?{query}",
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
        # Do not persist provider error bodies. They are unnecessary for the
        # capability decision and may echo request details.
        return {"ok": False, "status": exc.code, "error_kind": "http_error"}
    except Exception as exc:
        return {
            "ok": False,
            "status": None,
            "error_kind": type(exc).__name__,
        }


def summarize_response(response: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "ok": bool(response.get("ok")),
        "status": response.get("status"),
    }
    if not summary["ok"]:
        summary["error_kind"] = response.get("error_kind", "provider_request_failed")
        return summary

    payload = response.get("payload")
    if not isinstance(payload, list):
        summary["payload_shape"] = type(payload).__name__
        if isinstance(payload, dict):
            summary["top_level_fields"] = sorted(str(field) for field in payload)
        return summary

    rows = [row for row in payload if isinstance(row, dict)]
    fields = sorted({str(field) for row in rows for field in row})
    summary.update(
        {
            "payload_shape": "list",
            "row_count": len(payload),
            "object_row_count": len(rows),
            "fields": fields,
        }
    )

    date_fields: dict[str, dict[str, Any]] = {}
    exchange_fields: dict[str, dict[str, int]] = {}
    for field in fields:
        values = [row.get(field) for row in rows]
        present = [value for value in values if value not in (None, "")]
        if _is_date_field(field):
            parsed = [parsed for value in present if (parsed := _parse_date(value))]
            date_fields[field] = {
                "present_count": len(present),
                "parseable_count": len(parsed),
                "minimum": min(parsed).isoformat() if parsed else None,
                "maximum": max(parsed).isoformat() if parsed else None,
            }
        if _is_exchange_field(field):
            exchange_fields[field] = {
                "present_count": len(present),
                "distinct_count": len({str(value) for value in present}),
            }

    summary["date_fields"] = date_fields
    summary["exchange_fields"] = exchange_fields
    return summary


def _field_set(summary: dict[str, Any]) -> set[str]:
    fields = summary.get("fields", [])
    return {_normalized_field(str(field)) for field in fields}


def _has_any(fields: set[str], alternatives: set[str]) -> bool:
    return bool(fields & alternatives)


def assess_capability(datasets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    active = datasets.get("current_actively_trading", {})
    delisted = datasets.get("delisted_page_0", {})
    changes = datasets.get("symbol_changes", {})
    active_fields = _field_set(active)
    delisted_fields = _field_set(delisted)
    change_fields = _field_set(changes)

    checks = {
        "current_census_observed": bool(active.get("ok") and active.get("row_count", 0)),
        "current_symbol_field_observed": _has_any(active_fields, {"symbol", "ticker"}),
        "current_exchange_field_observed": any(
            "exchange" in field for field in active_fields
        ),
        "current_listing_date_observed": _has_any(
            active_fields, {"ipodate", "listingdate", "listeddate"}
        ),
        "delisted_rows_observed": bool(delisted.get("ok") and delisted.get("row_count", 0)),
        "delisted_symbol_field_observed": _has_any(delisted_fields, {"symbol", "ticker"}),
        "delisted_ipo_date_observed": _has_any(
            delisted_fields, {"ipodate", "listingdate", "listeddate"}
        ),
        "delisted_exit_date_observed": _has_any(
            delisted_fields, {"delisteddate", "delistingdate"}
        ),
        "delisted_exchange_field_observed": any(
            "exchange" in field for field in delisted_fields
        ),
        "symbol_change_rows_observed": bool(changes.get("ok") and changes.get("row_count", 0)),
        "symbol_change_old_symbol_observed": _has_any(
            change_fields, {"oldsymbol", "fromsymbol", "previoussymbol"}
        ),
        "symbol_change_new_symbol_observed": _has_any(
            change_fields, {"newsymbol", "tosymbol", "symbol"}
        ),
        "symbol_change_date_observed": any(
            _is_date_field(field) for field in changes.get("fields", [])
        ),
    }
    reconstruction_fields_observed = all(checks.values())

    return {
        "checks": checks,
        "reconstruction_fields_observed": reconstruction_fields_observed,
        "eligible_for_reconstruction_prototype": reconstruction_fields_observed,
        "coverage_audit_required": True,
        "point_in_time_universe_complete": False,
        "full_walk_forward_eligible": False,
        "policy_promotion_eligible": False,
        "interpretation": (
            "A successful schema probe can justify a bounded reconstruction prototype only. "
            "It cannot establish historical universe completeness; pagination, exchange/type "
            "coverage, lifecycle gaps, symbol lineage and cross-provider reconciliation must "
            "still be measured."
        ),
    }


def run(api_key: str | None = None) -> dict[str, Any]:
    key = api_key or os.getenv("FMP_API_KEY")
    datasets: dict[str, dict[str, Any]] = {}
    if key:
        for name, (path, parameters) in ENDPOINTS.items():
            datasets[name] = summarize_response(request_json(path, parameters, key))

    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "sanitized FMP historical-universe capability discovery",
        "knowledge_policy": "provider_schema_only_no_benchmark_labels_no_strategy_feedback",
        "raw_provider_rows_persisted": False,
        "provider": "financialmodelingprep",
        "official_docs": OFFICIAL_DOCS,
        "available": bool(key),
        "datasets": datasets,
    }
    if not key:
        report["unavailable_reason"] = "missing FMP_API_KEY"
    report["assessment"] = assess_capability(datasets)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    key = os.getenv("FMP_API_KEY")
    report = run(key)
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
