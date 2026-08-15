from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

USER_AGENT = "MomentumBot/0.2 provider-coverage-smoke"
TIMEOUT_SECONDS = 25


def _secrets() -> list[str]:
    return [
        value
        for name in (
            "ALPACA_API_KEY",
            "ALPACA_API_SECRET",
            "ALPACA_PAPER_ENDPOINT",
            "FMP_API_KEY",
            "MARKETAUX_API_KEY",
            "SEC_API_D2V_KEY",
        )
        if (value := os.getenv(name))
    ]


def redact(text: str) -> str:
    result = text
    for secret in _secrets():
        result = result.replace(secret, "***")
        result = result.replace(urllib.parse.quote(secret, safe=""), "***")
    return result


def _safe_error_body(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")[:800]
    return redact(text)


def request_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, **(headers or {})},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                return {
                    "ok": False,
                    "status": response.status,
                    "error": "non-JSON response",
                }
            return {"ok": True, "status": response.status, "payload": payload}
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status": exc.code,
            "error": _safe_error_body(exc.read()),
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": None,
            "error": redact(f"{type(exc).__name__}: {exc}"),
        }


def _alpaca_headers() -> dict[str, str] | None:
    key = os.getenv("ALPACA_API_KEY")
    secret = os.getenv("ALPACA_API_SECRET")
    if not key or not secret:
        return None
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}


def _safe_paper_endpoint() -> str:
    endpoint = os.getenv("ALPACA_PAPER_ENDPOINT", "https://paper-api.alpaca.markets").rstrip("/")
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme != "https" or parsed.hostname not in {
        "paper-api.alpaca.markets",
        "api.alpaca.markets",
    }:
        raise ValueError("ALPACA_PAPER_ENDPOINT must be an official Alpaca HTTPS API host")
    return endpoint


def _summarize_alpaca_bars(result: dict[str, Any]) -> dict[str, Any]:
    summary = {"ok": result["ok"], "status": result["status"]}
    if not result["ok"]:
        summary["error"] = result.get("error")
        return summary
    payload = result["payload"]
    bars = payload.get("bars", []) if isinstance(payload, dict) else []
    summary["bar_count"] = len(bars) if isinstance(bars, list) else None
    if isinstance(bars, list) and bars:
        summary["first_timestamp"] = bars[0].get("t")
        summary["last_timestamp"] = bars[-1].get("t")
        summary["sample_volume_positive"] = any((bar.get("v") or 0) > 0 for bar in bars)
    summary["next_page_present"] = (
        bool(payload.get("next_page_token")) if isinstance(payload, dict) else False
    )
    return summary


def probe_alpaca() -> dict[str, Any]:
    headers = _alpaca_headers()
    if headers is None:
        return {"available": False, "reason": "missing Alpaca key/secret"}

    base = "https://data.alpaca.markets"
    windows = {
        "historical_sip_premarket_1m": (
            "2026-08-12T11:00:00Z",
            "2026-08-12T12:00:00Z",
        ),
        "historical_sip_regular_1m": (
            "2026-08-12T13:30:00Z",
            "2026-08-12T14:00:00Z",
        ),
    }
    result: dict[str, Any] = {"available": True}
    for name, (start, end) in windows.items():
        query = urllib.parse.urlencode(
            {
                "timeframe": "1Min",
                "start": start,
                "end": end,
                "feed": "sip",
                "adjustment": "split",
                "limit": 1000,
            }
        )
        response = request_json(f"{base}/v2/stocks/AAPL/bars?{query}", headers=headers)
        result[name] = _summarize_alpaca_bars(response)

    try:
        paper_endpoint = _safe_paper_endpoint()
        asset_response = request_json(
            f"{paper_endpoint}/v2/assets?status=active&asset_class=us_equity",
            headers=headers,
        )
        asset_summary: dict[str, Any] = {
            "ok": asset_response["ok"],
            "status": asset_response["status"],
        }
        if asset_response["ok"]:
            payload = asset_response["payload"]
            asset_summary["active_us_equity_count"] = (
                len(payload) if isinstance(payload, list) else None
            )
            if isinstance(payload, list):
                exchanges = sorted(
                    {str(row.get("exchange")) for row in payload if row.get("exchange")}
                )
                asset_summary["exchanges"] = exchanges[:20]
        else:
            asset_summary["error"] = asset_response.get("error")
        result["current_asset_master"] = asset_summary
    except ValueError as exc:
        result["current_asset_master"] = {"ok": False, "status": None, "error": str(exc)}

    ca_query = urllib.parse.urlencode(
        {
            "types": "forward_split,reverse_split,name_change",
            "start": "2026-07-01",
            "end": "2026-08-12",
            "region": "us",
            "limit": 5,
        }
    )
    ca_response = request_json(f"{base}/v1/corporate-actions?{ca_query}", headers=headers)
    ca_summary: dict[str, Any] = {"ok": ca_response["ok"], "status": ca_response["status"]}
    if ca_response["ok"]:
        payload = ca_response["payload"]
        ca_summary["top_level_keys"] = sorted(payload) if isinstance(payload, dict) else []
        if isinstance(payload, dict):
            ca_summary["nonempty_action_groups"] = sorted(
                key for key, value in payload.items() if isinstance(value, list) and value
            )
            ca_summary["next_page_present"] = bool(payload.get("next_page_token"))
    else:
        ca_summary["error"] = ca_response.get("error")
    result["corporate_actions"] = ca_summary
    return result


def _summarize_generic_list(result: dict[str, Any]) -> dict[str, Any]:
    summary = {"ok": result["ok"], "status": result["status"]}
    if not result["ok"]:
        summary["error"] = result.get("error")
        return summary
    payload = result["payload"]
    if isinstance(payload, list):
        summary["row_count"] = len(payload)
        summary["fields"] = sorted(payload[0]) if payload and isinstance(payload[0], dict) else []
    elif isinstance(payload, dict):
        summary["top_level_keys"] = sorted(payload)
    return summary


def probe_fmp() -> dict[str, Any]:
    key = os.getenv("FMP_API_KEY")
    if not key:
        return {"available": False, "reason": "missing FMP key"}
    base = "https://financialmodelingprep.com"
    current_query = urllib.parse.urlencode({"symbol": "AAPL", "apikey": key})
    current = request_json(f"{base}/stable/shares-float?{current_query}")

    historical = request_json(f"{base}/stable/historical/shares-float?{current_query}")
    return {
        "available": True,
        "current_share_float": _summarize_generic_list(current),
        "historical_share_float_discovery_probe": _summarize_generic_list(historical),
    }


def probe_marketaux() -> dict[str, Any]:
    key = os.getenv("MARKETAUX_API_KEY")
    if not key:
        return {"available": False, "reason": "missing MarketAux key"}
    query = urllib.parse.urlencode(
        {
            "symbols": "AAPL",
            "published_after": "2026-08-12T00:00",
            "published_before": "2026-08-13T00:00",
            "limit": 3,
            "api_token": key,
        }
    )
    response = request_json(f"https://api.marketaux.com/v1/news/all?{query}")
    summary: dict[str, Any] = {"ok": response["ok"], "status": response["status"]}
    if not response["ok"]:
        summary["error"] = response.get("error")
        return {"available": True, "historical_news": summary}
    payload = response["payload"]
    data = payload.get("data", []) if isinstance(payload, dict) else []
    summary["row_count"] = len(data) if isinstance(data, list) else None
    if isinstance(payload, dict) and isinstance(payload.get("meta"), dict):
        meta = payload["meta"]
        summary["meta_returned"] = meta.get("returned")
        summary["meta_found"] = meta.get("found")
    if isinstance(data, list) and data:
        published = sorted(str(row.get("published_at")) for row in data if row.get("published_at"))
        if published:
            summary["first_published_at"] = published[0]
            summary["last_published_at"] = published[-1]
        summary["sample_fields"] = sorted(data[0]) if isinstance(data[0], dict) else []
    return {"available": True, "historical_news": summary}


def probe_sec_api() -> dict[str, Any]:
    """Spend exactly one SEC-API trial call to validate its historical float dataset."""
    key = os.getenv("SEC_API_D2V_KEY")
    if not key:
        return {"available": False, "reason": "missing SEC-API key"}
    query = urllib.parse.urlencode({"ticker": "AAPL"})
    response = request_json(
        f"https://api.sec-api.io/float?{query}",
        headers={"Authorization": key},
    )
    summary: dict[str, Any] = {
        "available": True,
        "trial_calls_consumed_by_this_probe": 1,
        "historical_outstanding_and_public_float": {
            "ok": response["ok"],
            "status": response["status"],
        },
    }
    target = summary["historical_outstanding_and_public_float"]
    if not response["ok"]:
        target["error"] = response.get("error")
        return summary

    payload = response["payload"]
    data = payload.get("data", []) if isinstance(payload, dict) else []
    if not isinstance(data, list):
        target["error"] = "unexpected data shape"
        return summary

    reported = sorted(
        str(row.get("reportedAt"))
        for row in data
        if isinstance(row, dict) and row.get("reportedAt")
    )
    outstanding_points = 0
    public_float_points = 0
    source_filings: set[str] = set()
    for row in data:
        if not isinstance(row, dict):
            continue
        float_data = row.get("float") if isinstance(row.get("float"), dict) else {}
        outstanding = float_data.get("outstandingShares", [])
        public_float = float_data.get("publicFloat", [])
        if isinstance(outstanding, list):
            outstanding_points += len(outstanding)
        if isinstance(public_float, list):
            public_float_points += len(public_float)
        if row.get("sourceFilingAccessionNo"):
            source_filings.add(str(row["sourceFilingAccessionNo"]))

    target["record_count"] = len(data)
    target["reported_at_first"] = reported[0] if reported else None
    target["reported_at_last"] = reported[-1] if reported else None
    target["outstanding_share_points"] = outstanding_points
    target["public_float_dollar_points"] = public_float_points
    target["distinct_source_filings"] = len(source_filings)
    target["public_float_unit"] = "USD, not shares"
    target["notes"] = (
        "SEC-API returns all issuer history in one lookup. Public-float disclosures are "
        "dollar market value; MomentumBot must convert them to implied non-affiliate "
        "shares using causal historical price data and preserve that value as an estimate."
    )
    return summary


def run() -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "sanitized provider entitlement and coverage smoke; no trading requests",
        "alpaca": probe_alpaca(),
        "fmp": probe_fmp(),
        "marketaux": probe_marketaux(),
        "sec_api": probe_sec_api(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run()
    rendered = json.dumps(report, indent=2, sort_keys=True)
    rendered = redact(rendered)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
