"""Bounded raw minute OHLC supplement for the frozen historical Micro plan.

The immutable scanner stream contains close/volume, not high/low. This child
captures the missing minute fields; it never runs Micro or alters a parent.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
import json
from pathlib import Path
import time as clock
from typing import Callable, Mapping
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

from momentumbot.research.sealed_historical_micro_inputs_v01 import (
    BoundedHTTP as ParentHTTP, CaptureError, ET, PLAN_RELATIVE, SYMBOL,
    capture_request, derive_requests as parent_requests, file_sha, frozen,
    seal, write_json,
)
from momentumbot.research.sealed_historical_source_checkpoint_v01 import canonical_fingerprint
from momentumbot.research.sealed_historical_scanner_micro_runtime_v02 import (
    EXPECTED_DATES, SOURCE_ARTIFACT_ID, SOURCE_ZIP_SHA256,
    SOURCE_REPORT_FILE_SHA256, SOURCE_REPORT_CONTENT_SHA256, SOURCE_TREE_SHA256,
    validate_frozen_policies,
)

CONTRACT_ID = "sealed-historical-micro-session-input-acquisition-v0.2"
CONTRACT_RELATIVE = "research/strategy/sealed-historical-micro-session-input-acquisition-v0.2.json"
EXECUTION_RELATIVE = "research/strategy/sealed-historical-micro-session-input-acquisition-v0.2-execution.json"
CONSUMPTION_REF = "refs/tags/sealed-historical-micro-session-input-acquisition-v0.2-consumed"
MAX_REQUESTS = 680
MAX_RETAINED_BYTES = 100_000_000
MAX_RESPONSE_BYTES = 4_000_000
REQUEST_INTERVAL_SECONDS = 0.35


def derive_requests(plan_root: Path) -> list[dict]:
    requests = []
    for parent in parent_requests(plan_root):
        if parent["kind"] != "sip_trades":
            continue
        lower = datetime.combine(date.fromisoformat(parent["trading_date"]), time(4), ET).astimezone(timezone.utc)
        body = {key: value for key, value in parent.items() if key != "request_id"}
        body.update(kind="session_1m_raw", start_inclusive=lower.isoformat(), adjustment="raw")
        body["request_id"] = canonical_fingerprint(body)
        requests.append(body)
    if len(requests) != 170:
        raise ValueError("the raw minute supplement must bind all 170 frozen symbol/date pairs")
    return requests


def expected_contract(plan_root: Path) -> dict:
    validate_frozen_policies()
    requests = derive_requests(plan_root)
    return seal({
        "schema_version": 1, "contract_id": CONTRACT_ID,
        "parent_scanner_plan_content_sha256": frozen(plan_root / "manifest.json")["content_sha256"],
        "source_artifact_id": SOURCE_ARTIFACT_ID, "source_zip_sha256": SOURCE_ZIP_SHA256,
        "source_report_file_sha256": SOURCE_REPORT_FILE_SHA256,
        "source_report_content_sha256": SOURCE_REPORT_CONTENT_SHA256,
        "source_tree_sha256": SOURCE_TREE_SHA256,
        "dates": list(EXPECTED_DATES), "logical_request_count": len(requests),
        "request_manifest_sha256": canonical_fingerprint(requests),
        "maximum_http_attempts": MAX_REQUESTS, "maximum_normalized_retained_bytes": MAX_RETAINED_BYTES,
        "page_limit": 10_000, "max_response_bytes": MAX_RESPONSE_BYTES,
        "minimum_request_interval_seconds": REQUEST_INTERVAL_SECONDS,
        "incremental_provider_cost_usd": "0", "provider": "existing_alpaca_market_data_subscription",
        "allowed_host": "data.alpaca.markets", "allowed_method": "GET",
        "source_request_ledger_is_immutable": True,
        "one_shot_consumption_ref": CONSUMPTION_REF,
        "workflow_reruns_allowed": False, "provider_substitution_allowed": False,
        "required_dependency": "raw_minute_high_low_for_unchanged_session_typical_price_vwap",
        "requested_interval": "04:00_inclusive_to_10:00_exclusive_America_New_York",
        "same_session_close_volume": "must_exactly_match_frozen_v0.13_before_micro",
        "failure_behavior": "retain_partial_evidence_and_stop_without_workflow_rerun",
        "micro_replay_executed_by_acquisition": False, "fills_or_accounts_simulated": False,
        "labels_or_transcripts_read": False, "databento_access": False,
        "broker_or_order_access": False, "policy_changed": False,
    })


def validate_contract(root: Path) -> dict:
    expected = expected_contract(root / PLAN_RELATIVE)
    observed = frozen(root / CONTRACT_RELATIVE)
    if observed != expected:
        raise ValueError("raw minute contract differs from the exact frozen request set")
    return observed


def request_url(request: Mapping, token: str | None = None) -> str:
    day = request.get("trading_date")
    symbol = request.get("symbol")
    if day not in EXPECTED_DATES or not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol):
        raise CaptureError("raw minute request identity is invalid")
    start = pd.Timestamp(datetime.combine(date.fromisoformat(day), time(4), ET))
    end = pd.Timestamp(datetime.combine(date.fromisoformat(day), time(10), ET))
    if (request.get("kind") != "session_1m_raw" or request.get("adjustment") != "raw"
            or request.get("feed") != "sip" or request.get("asof") != day
            or pd.Timestamp(request.get("start_inclusive")) != start
            or pd.Timestamp(request.get("end_exclusive")) != end):
        raise CaptureError("raw minute request scope changed")
    params = {"symbols": symbol, "start": start.tz_convert("UTC").isoformat(),
              "end": (end.tz_convert("UTC") - pd.Timedelta(nanoseconds=1)).isoformat(),
              "feed": "sip", "asof": day, "timeframe": "1Min", "adjustment": "raw",
              "limit": 10_000, "sort": "asc"}
    if token is not None:
        params["page_token"] = token
    return "https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(params)


class BoundedHTTP(ParentHTTP):
    """Reuse only the no-redirect constructor and separate-ledger serializer."""

    def __call__(self, request: dict, token: str | None) -> dict:
        url = request_url(request, token)
        for retry in range(4):
            retained = sum(path.stat().st_size for path in self.output.rglob("*.gz"))
            if self.attempts >= MAX_REQUESTS or retained > MAX_RETAINED_BYTES - 2 * MAX_RESPONSE_BYTES:
                self.blocked += 1
                self.save_ledger()
                raise CaptureError("raw minute request or retention ceiling reached before network access")
            delay = REQUEST_INTERVAL_SECONDS - (clock.monotonic() - self.last_attempt)
            if delay > 0:
                clock.sleep(delay)
            self.attempts += 1
            self.by_request[request["request_id"]] += 1
            self.save_ledger()
            self.last_attempt = clock.monotonic()
            try:
                call = urllib.request.Request(url, headers=self.headers, method="GET")
                with self.opener.open(call, timeout=60) as response:
                    raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise CaptureError("raw minute response exceeded the byte ceiling")
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise CaptureError("raw minute response is not an object")
                return value
            except urllib.error.HTTPError as exc:
                status = exc.code
                exc.close()
                if status in {429, 500, 502, 503, 504} and retry < 3:
                    clock.sleep(min(2 ** retry, 8))
                    continue
                raise CaptureError(f"market-data HTTP status {status}") from None
            except (urllib.error.URLError, TimeoutError):
                if retry < 3:
                    clock.sleep(min(2 ** retry, 8))
                    continue
                raise CaptureError("market-data transport unavailable") from None
        raise CaptureError("raw minute provider retry limit reached")


def acquire(requests: list[dict], output: Path, fetch: Callable, *, contract: dict, provenance: dict) -> dict:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("raw minute capture output must be new and empty")
    if len(requests) != contract.get("logical_request_count") or canonical_fingerprint(requests) != contract.get("request_manifest_sha256"):
        raise ValueError("raw minute requests differ from the registered complete request set")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "requests.json", seal({"requests": requests}))
    receipts = []
    current = None
    try:
        for current in requests:
            receipt = capture_request(current, output, fetch)
            if receipt["record_count"] > 360:
                raise CaptureError("raw minute capture exceeds the six-hour session bound")
            receipts.append(receipt)
            write_json(output / "receipts" / f"{current['request_id']}.json", seal(receipt))
        report = seal({"schema_version": 1, "contract_id": CONTRACT_ID, "status": "complete",
                       "contract_content_sha256": contract["content_sha256"], "provenance": provenance,
                       "logical_requests_completed": len(receipts), "receipts": receipts,
                       "micro_runtime_executed": False, "backtesting_executed": False,
                       "source_ledger_mutated": False, "next_gate": "provider_free_micro_input_validation_and_runtime"})
        write_json(output / "capture-report.json", report)
        return report
    except Exception as exc:
        write_json(output / "capture-failure.json", seal({
            "schema_version": 1, "contract_id": CONTRACT_ID, "status": "failed",
            "contract_content_sha256": contract["content_sha256"], "provenance": provenance,
            "failed_request_id": current["request_id"] if current else None,
            "completed_receipts": receipts, "exception_class": type(exc).__name__,
            "sanitized_error": str(exc) if isinstance(exc, CaptureError) else "raw minute capture failed",
            "micro_runtime_executed": False, "backtesting_executed": False, "source_ledger_mutated": False,
        }))
        raise CaptureError("raw minute capture failed; see the retained sanitized failure receipt") from None
