"""Bounded SIP-print and EMA-warmup capture after the frozen scanner activation gate.

Acquisition retains normalized provider inputs. It does not evaluate Micro,
simulate executions, mutate the v0.13 source, or read retrospective evidence.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time as clock
from typing import Callable, Mapping
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.research.sealed_historical_scanner_micro_runtime_v02 import (
    EXPECTED_DATES, SOURCE_ARTIFACT_ID, SOURCE_ZIP_SHA256,
    SOURCE_REPORT_FILE_SHA256, SOURCE_REPORT_CONTENT_SHA256, SOURCE_TREE_SHA256,
    validate_frozen_policies,
)
from momentumbot.research.sealed_historical_source_checkpoint_v01 import canonical_fingerprint

CONTRACT_ID = "sealed-historical-micro-input-acquisition-v0.1"
PLAN_CONTENT_SHA256 = "764354afcd61c180bc332d247f3bf2035254142006011eeb562bedda86fa704d"
PLAN_FILE_SHA256 = "efcfcb7575ca61d5d03c0d0a9cdb5d27348c8699c04d236e77c436024c6f51bb"
PLAN_RELATIVE = "research/runtime/sealed-historical-scanner-activation-v0.2"
CONTRACT_RELATIVE = "research/strategy/sealed-historical-micro-input-acquisition-v0.1.json"
EXECUTION_RELATIVE = "research/strategy/sealed-historical-micro-input-acquisition-v0.1-execution.json"
CONSUMPTION_REF = "refs/tags/sealed-historical-micro-input-acquisition-v0.1-consumed"
MAX_REQUESTS = 18_000
MAX_RETAINED_BYTES = 4_000_000_000
MAX_RESPONSE_BYTES = 16_000_000
REQUEST_INTERVAL_SECONDS = 0.35
ET = ZoneInfo("America/New_York")
SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9._-]{0,19}\Z")


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def frozen(path: Path) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    value = json.loads(path.read_text(), object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError("frozen object required")
    body = dict(value)
    claimed = body.pop("content_sha256", None)
    if canonical_fingerprint(body) != claimed:
        raise ValueError("frozen content hash mismatch")
    return value


def seal(value: dict) -> dict:
    return {**value, "content_sha256": canonical_fingerprint(value)}


def write_json(path: Path, value: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def derive_requests(plan_root: Path) -> list[dict]:
    manifest = frozen(plan_root / "manifest.json")
    if file_sha(plan_root / "manifest.json") != PLAN_FILE_SHA256 or manifest["content_sha256"] != PLAN_CONTENT_SHA256:
        raise ValueError("exact scanner activation manifest required")
    if manifest["dates"] != list(EXPECTED_DATES):
        raise ValueError("frozen date panel changed")
    requests = []
    for day in EXPECTED_DATES:
        path = plan_root / "dates" / f"{day}.json"
        if file_sha(path) != manifest["date_file_sha256"][day]:
            raise ValueError("activation date file changed")
        payload = frozen(path)
        by_symbol: dict[str, list[dict]] = {}
        for activation in payload["activations"]:
            symbol = activation["symbol"]
            if not SYMBOL.fullmatch(symbol):
                raise ValueError("invalid frozen symbol")
            by_symbol.setdefault(symbol, []).append(activation)
        start = datetime.combine(date.fromisoformat(day), time(4), ET).astimezone(timezone.utc)
        end = datetime.combine(date.fromisoformat(day), time(10), ET).astimezone(timezone.utc)
        for symbol, activations in sorted(by_symbol.items()):
            qualified = min(pd.Timestamp(row["candidate_qualified_at"]) for row in activations)
            if qualified.tzinfo is None or not start <= qualified < end:
                raise ValueError("activation outside the frozen causal session")
            for kind, lower, upper, adjustment in [
                ("sip_trades", qualified.isoformat(), end.isoformat(), None),
                ("ema_warmup_1m_split", (start - timedelta(days=7)).isoformat(), start.isoformat(), "split"),
            ]:
                request = {
                    "trading_date": day, "symbol": symbol, "kind": kind,
                    "start_inclusive": lower, "end_exclusive": upper,
                    "feed": "sip", "asof": day, "adjustment": adjustment,
                    "activation_ids": sorted(row["activation_id"] for row in activations),
                }
                request["request_id"] = canonical_fingerprint(request)
                requests.append(request)
    if len(requests) != 340:
        raise ValueError("expected exactly 170 symbol/date pairs and 340 logical requests")
    return requests


def expected_contract(plan_root: Path) -> dict:
    validate_frozen_policies()
    requests = derive_requests(plan_root)
    return seal({
        "schema_version": 1, "contract_id": CONTRACT_ID,
        "parent_scanner_plan_content_sha256": PLAN_CONTENT_SHA256,
        "parent_scanner_plan_file_sha256": PLAN_FILE_SHA256,
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
        "same_session_minute_source": "reuse_exact_v0.13_candidate_raw_and_rank_split_bars",
        "warmup_basis": "split_provider_bars_require_causal_raw_session_basis_normalization_before_micro",
        "micro_bar_source": "derive_completed_10_second_bars_from_normalized_sip_prints_only",
        "failure_behavior": "retain_completed_and_partial_evidence_stop_without_retrying_the_workflow",
        "micro_replay_executed_by_acquisition": False, "fills_or_accounts_simulated": False,
        "labels_or_transcripts_read": False, "databento_access": False,
        "broker_or_order_access": False, "policy_changed": False,
    })


def validate_contract(root: Path) -> dict:
    expected = expected_contract(root / PLAN_RELATIVE)
    observed = frozen(root / CONTRACT_RELATIVE)
    if observed != expected:
        raise ValueError("Micro input contract differs from exact registered requests or limits")
    return observed


def request_url(request: Mapping, page_token: str | None = None) -> str:
    symbol = request["symbol"]
    if not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol):
        raise ValueError("invalid requested symbol")
    kind = request["kind"]
    if kind not in {"sip_trades", "ema_warmup_1m_split"}:
        raise ValueError("provider route is not authorized")
    if request["feed"] != "sip" or request["asof"] != request["trading_date"]:
        raise ValueError("SIP identity date changed")
    lower = pd.Timestamp(request["start_inclusive"])
    upper = pd.Timestamp(request["end_exclusive"])
    if lower.tzinfo is None or upper.tzinfo is None or lower >= upper:
        raise ValueError("invalid provider time bounds")
    params = {
        "start": lower.isoformat(), "end": (upper - pd.Timedelta(nanoseconds=1)).isoformat(),
        "symbols": symbol, "feed": "sip", "asof": request["asof"], "limit": 10_000, "sort": "asc",
    }
    route = "trades"
    if kind == "ema_warmup_1m_split":
        if request["adjustment"] != "split":
            raise ValueError("warmup adjustment changed")
        route = "bars"
        params.update(timeframe="1Min", adjustment="split")
    elif request["adjustment"] is not None:
        raise ValueError("trade prices must remain raw")
    if page_token is not None:
        params["page_token"] = page_token
    return f"https://data.alpaca.markets/v2/stocks/{route}?{urllib.parse.urlencode(params)}"


class CaptureError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CaptureError("provider redirect is forbidden")


class BoundedHTTP:
    def __init__(self, output: Path, *, key: str, secret: str):
        if not key or not secret:
            raise CaptureError("required market-data environment is missing")
        self.output = output
        self.headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        self.opener = urllib.request.build_opener(NoRedirect())
        self.attempts = 0
        self.blocked = 0
        self.last_attempt = 0.0
        self.by_request: Counter[str] = Counter()

    def save_ledger(self):
        value = {"schema_version": 1, "total_attempts": self.attempts,
                 "by_host": {"data.alpaca.markets": self.attempts},
                 "blocked_attempts": self.blocked, "by_request": dict(self.by_request)}
        temporary = self.output / "request-ledger.tmp"
        temporary.write_text(json.dumps(value, sort_keys=True) + "\n")
        os.replace(temporary, self.output / "request-ledger.json")

    def __call__(self, request: dict, token: str | None) -> dict:
        url = request_url(request, token)
        retained = sum(path.stat().st_size for path in self.output.rglob("*.gz"))
        for retry in range(4):
            if self.attempts >= MAX_REQUESTS or retained > MAX_RETAINED_BYTES - 2 * MAX_RESPONSE_BYTES:
                self.blocked += 1
                self.save_ledger()
                raise CaptureError("registered request or retention ceiling reached before network access")
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
                    raise CaptureError("provider response exceeded registered byte ceiling")
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise CaptureError("provider response is not an object")
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
        raise CaptureError("provider retry limit reached")


def normalized_row(row: Mapping, request: Mapping) -> dict:
    if not isinstance(row, Mapping):
        raise CaptureError("provider record is not an object")
    stamp = pd.Timestamp(row.get("t"))
    if pd.isna(stamp) or stamp.tzinfo is None:
        raise CaptureError("provider record lacks an aware timestamp")
    if not pd.Timestamp(request["start_inclusive"]) <= stamp < pd.Timestamp(request["end_exclusive"]):
        raise CaptureError("provider record falls outside its exact requested interval")
    output = {"t": stamp.tz_convert("UTC").isoformat()}
    def number(key, *, integer=False, positive=False):
        value = row.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise CaptureError("provider numeric field is invalid")
        if value < 0 or (positive and value == 0) or (integer and int(value) != value):
            raise CaptureError("provider numeric field is invalid")
        return int(value) if integer else float(value)
    if request["kind"] == "sip_trades":
        conditions = row.get("c")
        if not isinstance(conditions, list) or any(not isinstance(x, str) or len(x) > 2 for x in conditions):
            raise CaptureError("SIP condition list is invalid")
        if row.get("z") not in {"A", "B", "C"} or not isinstance(row.get("x"), str) or len(row["x"]) != 1:
            raise CaptureError("SIP tape or exchange is invalid")
        output.update(p=number("p", positive=True), s=number("s", integer=True),
                      i=number("i", integer=True), x=row["x"], z=row["z"], c=conditions)
    else:
        output.update({key: number(key, positive=True) for key in ("o", "h", "l", "c")})
        output.update(v=number("v", integer=True), n=number("n", integer=True), vw=number("vw", positive=True))
        if not output["l"] <= min(output["o"], output["c"]) <= max(output["o"], output["c"]) <= output["h"]:
            raise CaptureError("warmup OHLC ordering is invalid")
    return output


def capture_request(request: dict, output: Path, fetch: Callable) -> dict:
    """Exhaust one exact logical request; retain a partial tape on failure."""
    relative = f"dates/{request['trading_date']}/{request['symbol']}-{request['kind']}.jsonl.gz"
    path = output / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    token = None
    tokens: set[str] = set()
    count = 0
    pages = 0
    logical = hashlib.sha256()
    previous = None
    same_timestamp_records: set[bytes] = set()
    with path.open("xb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as tape:
            while True:
                payload = fetch(request, token)
                key = "trades" if request["kind"] == "sip_trades" else "bars"
                if key not in payload or not isinstance(payload[key], dict) or "next_page_token" not in payload:
                    raise CaptureError("provider response identity or record field differs")
                if set(payload[key]) - {request["symbol"]}:
                    raise CaptureError("provider response contains an unrequested symbol")
                rows = payload[key].get(request["symbol"], [])
                if rows is None:
                    rows = []
                if not isinstance(rows, list) or len(rows) > 10_000:
                    raise CaptureError("provider page has invalid rows")
                for row in rows:
                    record = normalized_row(row, request)
                    stamp = pd.Timestamp(record["t"])
                    if previous is not None and stamp < previous:
                        raise CaptureError("provider pages are not chronological")
                    encoded = (json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
                    if len(encoded) > 1000:
                        raise CaptureError("normalized provider row exceeds size ceiling")
                    if previous != stamp:
                        same_timestamp_records.clear()
                    if encoded in same_timestamp_records:
                        raise CaptureError("provider pages repeat the same normalized record")
                    same_timestamp_records.add(encoded)
                    previous = stamp
                    tape.write(encoded)
                    logical.update(encoded)
                    count += 1
                tape.flush()
                pages += 1
                next_token = payload.get("next_page_token")
                if next_token is None:
                    break
                if not isinstance(next_token, str) or not next_token or next_token in tokens:
                    raise CaptureError("provider pagination token is invalid or repeated")
                tokens.add(next_token)
                token = next_token
    if count == 0:
        raise CaptureError("required candidate input is unavailable; it is not a zero-trigger result")
    return {"request_id": request["request_id"], "path": relative,
            "record_count": count, "pages": pages, "complete": True,
            "logical_sha256": logical.hexdigest(), "file_sha256": file_sha(path),
            "retained_bytes": path.stat().st_size}


def acquire(requests: list[dict], output: Path, fetch: Callable, *, contract: dict, provenance: dict) -> dict:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("capture output must be new and empty")
    if len(requests) != contract.get("logical_request_count") or canonical_fingerprint(requests) != contract.get("request_manifest_sha256"):
        raise ValueError("capture requests differ from the registered complete request set")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "requests.json", seal({"requests": requests}))
    receipts = []
    current = None
    try:
        for current in requests:
            receipt = capture_request(current, output, fetch)
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
        failure = seal({"schema_version": 1, "contract_id": CONTRACT_ID, "status": "failed",
                        "contract_content_sha256": contract["content_sha256"], "provenance": provenance,
                        "failed_request_id": current["request_id"] if current else None,
                        "completed_receipts": receipts, "exception_class": type(exc).__name__,
                        "sanitized_error": str(exc) if isinstance(exc, CaptureError) else "input capture failed",
                        "micro_runtime_executed": False, "backtesting_executed": False,
                        "source_ledger_mutated": False})
        write_json(output / "capture-failure.json", failure)
        raise CaptureError("Micro input capture failed; see the retained sanitized failure receipt") from None
