"""One-shot acquisition of the ten frozen missing management resources.

This child does not compose management windows or run trading/account logic.
Empty, exhausted requests are source evidence, never inferred trade outcomes.
"""
from __future__ import annotations

from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import pandas as pd

from momentumbot.research import sealed_historical_management_reuse_v01 as reuse
from momentumbot.research import sealed_historical_micro_inputs_v01 as source
from momentumbot.research.sealed_historical_execution_quote_v01 import (
    canonical_fingerprint, file_sha, frozen, require_exact, seal,
)

CaptureError = source.CaptureError
write_json = source.write_json
CONTRACT_ID = "sealed-historical-management-missing-input-acquisition-v0.1"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
EXECUTION_PATH = f"research/strategy/{CONTRACT_ID}-execution.json"
CONSUMPTION_REF = f"refs/tags/{CONTRACT_ID}-consumed"
MODULE_PATH = "src/momentumbot/research/sealed_historical_management_capture_v01.py"
SCRIPT_PATH = "scripts/capture_sealed_historical_management_inputs_v01.py"
WORKFLOW_PATH = ".github/workflows/sealed-historical-management-input-acquisition-v01.yml"
VALIDATION_PATH = ".github/workflows/sealed-historical-management-capture-validation-v01.yml"
TEST_PATH = "tests/test_sealed_historical_management_capture_v01.py"
PARENT_COMMIT = "813960e42a96edd40983bc3e414743c0bf67452d"
PARENT_TREE = "49b7c0d4d71d5ce2adc452bfa3d64216903556cf"
REUSE_AUDIT = "research/data-audits/sealed-historical-management-source-reuse-v0.1-independent-verification.json"
REUSE_AUDIT_SHA = "4afb466b9137f9d6b36955cd0b6e6b4b8f28fcc3cddd088dd40eae22674023d5"
REUSE_MANIFEST_SHA = "89e765d9cf0ee40193eb1f9549674f1d534dde717c4e702bfd1b62ed906617cf"
MAX_ATTEMPTS = 512
MAX_RETAINED_BYTES = 100_000_000
MAX_RESPONSE_BYTES = 16_000_000
PAGE_LIMIT = 10_000
REQUEST_INTERVAL = 0.35
BOUNDARY = dict(reuse.BOUNDARY)
NEXT_GATE = "independently_verify_missing_capture_then_provider_free_management_source_composition"


def verify_reuse_result(root: Path) -> dict:
    """Revalidate exact committed audited evidence, without redownloading sources."""
    for name, expected in ((REUSE_AUDIT, REUSE_AUDIT_SHA),
                           (reuse.OUTPUT_PATH + "/freeze-manifest.json", REUSE_MANIFEST_SHA)):
        reuse.accounts.availability._regular(root / name)
        if file_sha(root / name) != expected:
            raise ValueError("verified reuse parent differs: " + name)
    audit = frozen(root / REUSE_AUDIT)
    manifest = frozen(root / reuse.OUTPUT_PATH / "freeze-manifest.json")
    for name, expected in manifest["implementation_file_sha256"].items():
        reuse.accounts.availability._regular(root / name)
        if file_sha(root / name) != expected:
            raise ValueError("reuse implementation differs: " + name)
    reuse.validate_registration(root)
    inventory = audit["independent_verification"]["file_inventory"]
    files = {p.relative_to(root / reuse.OUTPUT_PATH).as_posix()
             for p in (root / reuse.OUTPUT_PATH).rglob("*") if p.is_file() or p.is_symlink()}
    if files != set(inventory):
        raise ValueError("reuse result file set differs")
    for name, expected in inventory.items():
        path = root / reuse.OUTPUT_PATH / name
        reuse.accounts.availability._regular(path)
        require_exact({"bytes": path.stat().st_size, "sha256": file_sha(path)}, expected, "reuse output bytes")
        document = frozen(path)
        if name != "freeze-manifest.json" and document["content_sha256"] != manifest["document_content_sha256"][name]:
            raise ValueError("reuse document seal differs")
    if (audit["verification_passed"] is not True or audit["full_source_reconstruction_identical"] is not True
            or audit["independent_verification"]["verification_passed"] is not True
            or audit["freeze_manifest_content_sha256"] != manifest["content_sha256"]):
        raise ValueError("prior independent verification gate differs")
    return seal({"schema_version": 1, "verified_reuse_result": True,
        "verification_basis": "exact_committed_independently_verified_reuse_result_and_all_frozen_parents",
        "original_source_archives_reopened_in_this_preflight": False,
        "reuse_parent_commit_sha": PARENT_COMMIT, "reuse_parent_tree_sha": PARENT_TREE,
        "reuse_audit_file_sha256": REUSE_AUDIT_SHA,
        "reuse_manifest_content_sha256": manifest["content_sha256"],
        "reuse_result_file_inventory": inventory,
        "missing_requirements_content_sha256": frozen(root / reuse.MISSING_PATH)["content_sha256"],
        "provider_calls": 0, **BOUNDARY})


def expected_contract(root: Path) -> dict:
    requirements = frozen(root / reuse.MISSING_PATH)
    return seal({"schema_version": 1, "contract_id": CONTRACT_ID,
        "artifact_type": "separately_consumed_exact_missing_management_capture",
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "reuse_audit_file_sha256": REUSE_AUDIT_SHA,
        "missing_requirements_path": reuse.MISSING_PATH,
        "missing_requirements_content_sha256": requirements["content_sha256"],
        "requests": requirements["requests"], "request_manifest_sha256": requirements["request_manifest_sha256"],
        "logical_request_count": 10,
        "maximum_http_attempts": MAX_ATTEMPTS, "maximum_normalized_compressed_bytes": MAX_RETAINED_BYTES,
        "maximum_response_bytes": MAX_RESPONSE_BYTES, "page_limit": PAGE_LIMIT,
        "minimum_request_interval_seconds": REQUEST_INTERVAL,
        "allowed_host": "data.alpaca.markets", "allowed_method": "GET",
        "allowed_paths": ["/v2/stocks/bars", "/v2/stocks/trades"],
        "automatic_retries_allowed": False, "redirects_allowed": False, "workflow_reruns_allowed": False,
        "source_normalizer": "unchanged_sealed_historical_micro_inputs_v01.normalized_row",
        "source_order": "zero_based_file_line_ordinal_no_sort_or_deduplication",
        "empty_exhausted_segment": requirements["empty_exhausted_segment"],
        "separate_durable_attempt_ledger_before_network": True,
        "compressed_byte_ceiling_enforced_before_every_file_write": True,
        "partial_failure_evidence_retained": True,
        "execution_child_required": True, "durable_consumption_before_provider_access_required": True,
        "consumption_ref": CONSUMPTION_REF, "provider_access_authorized_by_this_registration": False,
        "provider": requirements["provider"], "incremental_provider_cost_usd": "0",
        "implementation_file_sha256": {p: file_sha(root / p) for p in
            (MODULE_PATH, SCRIPT_PATH, WORKFLOW_PATH, VALIDATION_PATH, TEST_PATH,
             "requirements-sealed-execution-quote-v01.txt", "scripts/run_offline_python_v13.py")},
        "hypothesis": "exact_missing_tail_envelopes_can_be_exhausted_without_repeating_retained_sources",
        "next_gate": NEXT_GATE, **BOUNDARY})


def validate_contract(root: Path) -> dict:
    verify_reuse_result(root)
    observed = frozen(root / CONTRACT_PATH)
    require_exact(observed, expected_contract(root), "missing management capture registration")
    return observed


def execution_payload(contract: dict, *, code_commit: str, code_tree: str, workflow_sha256: str) -> dict:
    for value, length in ((code_commit, 40), (code_tree, 40), (workflow_sha256, 64)):
        if not isinstance(value, str) or not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
            raise ValueError("execution provenance requires exact full hashes")
    return seal({"schema_version": 1, "execution_id": CONTRACT_ID + "-execution",
        "contract_content_sha256": contract["content_sha256"],
        "code_commit_sha": code_commit, "code_tree_sha": code_tree,
        "workflow_file_sha256": workflow_sha256, "workflow_path": WORKFLOW_PATH,
        "repository": "RoomyRems/momentumbot", "branch": "phase-3-historical-snapshot",
        "event": "push", "run_attempt": 1, "consumption_ref": CONSUMPTION_REF,
        "authority": "user_authorized_next_bounded_management_capture_step_2026-09-07",
        "market_data_capture_authorized": True, "incremental_provider_cost_usd": "0",
        "broker_or_order_authority": False, "policy_change_authority": False,
        "retrospective_input_authority": False})


def validate_execution(root: Path, contract: dict, env: dict) -> dict:
    observed = frozen(root / EXECUTION_PATH)
    expected = execution_payload(contract, code_commit=env.get("EXECUTION_CODE_COMMIT_SHA", ""),
        code_tree=env.get("EXECUTION_CODE_TREE_SHA", ""), workflow_sha256=file_sha(root / WORKFLOW_PATH))
    require_exact(observed, expected, "exact execution child")
    if (env.get("GITHUB_REPOSITORY") != expected["repository"] or env.get("GITHUB_EVENT_NAME") != "push"
            or env.get("GITHUB_REF") != "refs/heads/phase-3-historical-snapshot"
            or env.get("GITHUB_RUN_ATTEMPT") != "1"
            or not re.fullmatch(r"[0-9]+", env.get("GITHUB_RUN_ID", ""))
            or not re.fullmatch(r"[0-9a-f]{40}", env.get("GITHUB_SHA", ""))):
        raise ValueError("capture requires the exact first-attempt research push")
    return observed


def consumption_payload(execution: dict, *, commit: str, run_id: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or not re.fullmatch(r"[0-9]+", run_id):
        raise ValueError("invalid durable consumption identity")
    return seal({"execution_content_sha256": execution["content_sha256"], "consumption_ref": CONSUMPTION_REF,
        "execution_commit_sha": commit, "workflow_run_id": run_id, "workflow_run_attempt": 1})


def request_url(request: dict, token: str | None, *, requests: list[dict]) -> str:
    matches = [r for r in requests if r["request_id"] == request.get("request_id")]
    if len(matches) != 1:
        raise CaptureError("unregistered management request")
    require_exact(request, matches[0], "registered management request")
    if token is not None and (not isinstance(token, str) or not token or len(token) > 16_384):
        raise CaptureError("invalid opaque page token")
    query = {"symbols": request["symbol"],
        "start": pd.Timestamp(request["start_ns"], unit="ns", tz="UTC").isoformat(),
        "end": pd.Timestamp(request["end_ns"] - 1, unit="ns", tz="UTC").isoformat(),
        "feed": "sip", "asof": request["trading_date"], "sort": "asc", "limit": PAGE_LIMIT}
    route = "trades"
    if request["kind"] == "session_1m_raw":
        route = "bars"
        query.update(timeframe="1Min", adjustment="raw")
    elif request["kind"] != "sip_trades":
        raise CaptureError("unregistered resource kind")
    if token is not None:
        query["page_token"] = token
    return "https://data.alpaca.markets/v2/stocks/" + route + "?" + urllib.parse.urlencode(query)


class BoundedHTTP:
    """Exactly one HTTP attempt per registered page; failures never retry."""
    def __init__(self, output: Path, *, requests: list[dict], key: str, secret: str):
        if not key or not secret:
            raise CaptureError("required market-data environment is missing")
        self.output, self.requests = output, json.loads(json.dumps(requests))
        self.headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        self.opener = urllib.request.build_opener(source.NoRedirect())
        self.attempts = self.blocked = 0
        self.last_attempt = None
        self.by_request: Counter[str] = Counter()
        self.pages: set[tuple[str, str | None]] = set()
        self.events: list[dict] = []

    def save_ledger(self):
        value = {"schema_version": 1, "contract_id": CONTRACT_ID,
            "total_attempts": self.attempts, "by_host": {"data.alpaca.markets": self.attempts},
            "blocked_attempts": self.blocked, "by_request": dict(self.by_request), "attempt_events": self.events}
        temporary = self.output / "request-ledger.tmp"
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(value, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.output / "request-ledger.json")

    def __call__(self, request: dict, token: str | None) -> dict:
        try:
            url = request_url(request, token, requests=self.requests)
            identity = (request["request_id"], token)
            retained = sum(p.stat().st_size for p in self.output.rglob("*.gz"))
            if identity in self.pages or self.attempts >= MAX_ATTEMPTS or retained >= MAX_RETAINED_BYTES:
                raise CaptureError("registered page, request or retention ceiling reached before network")
        except (ValueError, CaptureError):
            self.blocked += 1
            self.save_ledger()
            raise CaptureError("unregistered or exhausted page blocked before network") from None
        if self.last_attempt is not None:
            delay = REQUEST_INTERVAL - (time.monotonic() - self.last_attempt)
            if delay > 0:
                time.sleep(delay)
        self.attempts += 1
        self.by_request[request["request_id"]] += 1
        self.pages.add(identity)
        self.events.append({"attempt": self.attempts, "request_id": request["request_id"]})
        self.save_ledger()
        self.last_attempt = time.monotonic()
        try:
            call = urllib.request.Request(url, headers=self.headers, method="GET")
            with self.opener.open(call, timeout=30) as response:
                if response.status != 200:
                    raise CaptureError("unexpected market-data HTTP status")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise CaptureError("provider response exceeded registered byte ceiling")
            return reuse._json(raw)
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
            raise CaptureError(f"market-data HTTP status {status}; no retry") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise CaptureError("market-data transport unavailable; no retry") from None
        except (ValueError, UnicodeError):
            raise CaptureError("provider response JSON is invalid; no retry") from None


class CompressedBudget:
    def __init__(self):
        self.written = 0

    def writer(self, raw):
        budget = self

        class Writer:
            def write(self, data):
                if budget.written + len(data) > MAX_RETAINED_BYTES:
                    raise CaptureError("normalized compressed byte ceiling reached")
                size = raw.write(data)
                budget.written += size
                return size

            def flush(self):
                raw.flush()

            def tell(self):
                return raw.tell()

        return Writer()


def normalizer_request(request: dict) -> dict:
    return {**request, "start_inclusive": pd.Timestamp(request["start_ns"], unit="ns", tz="UTC").isoformat(),
        "end_exclusive": pd.Timestamp(request["end_ns"], unit="ns", tz="UTC").isoformat()}


def tape_path(request: dict) -> str:
    return f"dates/{request['trading_date']}/{request['symbol']}-{request['kind']}.jsonl.gz"


def checked_record(row: dict, request: dict, previous: int | None, tied: set[bytes]) -> tuple[bytes, int]:
    record = source.normalized_row(row, normalizer_request(request))
    stamp = int(pd.Timestamp(record["t"]).value)
    if previous is not None and stamp < previous:
        raise CaptureError("provider pages are not chronological")
    if request["kind"] == "session_1m_raw" and (stamp % 60_000_000_000 or stamp == previous):
        raise CaptureError("raw minute bar identity is not unique and minute-aligned")
    encoded = reuse._canonical_line(record)
    if len(encoded) > 1000:
        raise CaptureError("normalized provider row exceeds size ceiling")
    if stamp != previous:
        tied.clear()
    if encoded in tied:
        raise CaptureError("provider pages repeat the same normalized record")
    tied.add(encoded)
    return encoded, stamp


def capture_request(request: dict, output: Path, fetch, budget: CompressedBudget) -> dict:
    relative = tape_path(request)
    path = output / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    token, previous = None, None
    tokens, tied = set(), set()
    count = pages = 0
    logical = hashlib.sha256()
    with path.open("xb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=budget.writer(raw), mtime=0) as tape:
        while True:
            payload = fetch(request, token)
            key = "trades" if request["kind"] == "sip_trades" else "bars"
            if not isinstance(payload, dict) or not isinstance(payload.get(key), dict) or "next_page_token" not in payload:
                raise CaptureError("provider response identity or record field differs")
            if set(payload[key]) - {request["symbol"]}:
                raise CaptureError("provider response contains an unrequested symbol")
            rows = payload[key].get(request["symbol"], [])
            rows = [] if rows is None else rows
            if not isinstance(rows, list) or len(rows) > PAGE_LIMIT:
                raise CaptureError("provider page has invalid rows")
            for row in rows:
                encoded, previous = checked_record(row, request, previous, tied)
                tape.write(encoded)
                logical.update(encoded)
                count += 1
            tape.flush()
            pages += 1
            next_token = payload["next_page_token"]
            if next_token is None:
                break
            if not isinstance(next_token, str) or not next_token or len(next_token) > 16_384 or next_token in tokens:
                raise CaptureError("provider pagination token is invalid or repeated")
            tokens.add(next_token)
            token = next_token
    return {"request_id": request["request_id"], "path": relative, "record_count": count,
        "pages": pages, "complete": True, "empty_exhausted_segment": count == 0,
        "logical_sha256": logical.hexdigest(), "file_sha256": file_sha(path), "retained_bytes": path.stat().st_size}


def acquire(requests: list[dict], output: Path, fetch, *, contract: dict, provenance: dict) -> dict:
    if output.is_symlink() or any(p.is_symlink() for p in output.parents):
        raise CaptureError("capture output cannot use symbolic links")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise CaptureError("capture output must be new and empty")
    require_exact({"requests": requests}, {"requests": contract["requests"]}, "complete capture request set")
    if len(requests) != 10 or canonical_fingerprint(requests) != contract["request_manifest_sha256"]:
        raise CaptureError("capture request manifest differs")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "requests.json", seal({"requests": requests}))
    receipts, budget, current = [], CompressedBudget(), None
    try:
        for current in requests:
            receipt = capture_request(current, output, fetch, budget)
            receipts.append(receipt)
            write_json(output / "receipts" / (current["request_id"] + ".json"), seal(receipt))
        report = seal({"schema_version": 1, "contract_id": CONTRACT_ID, "status": "complete",
            "contract_content_sha256": contract["content_sha256"], "provenance": provenance,
            "logical_requests_completed": len(receipts), "receipts": receipts,
            "normalized_compressed_bytes": budget.written, "next_gate": NEXT_GATE, **BOUNDARY})
        write_json(output / "capture-report.json", report)
        return report
    except Exception as exc:
        write_json(output / "capture-failure.json", seal({"schema_version": 1, "contract_id": CONTRACT_ID,
            "status": "failed", "contract_content_sha256": contract["content_sha256"], "provenance": provenance,
            "failed_request_id": current["request_id"] if current else None, "completed_receipts": receipts,
            "exception_class": type(exc).__name__, "sanitized_error": "bounded management input capture failed",
            "normalized_compressed_bytes": budget.written, **BOUNDARY}))
        raise CaptureError("management input capture failed; partial evidence retained; no retry") from None


def verify_archive(root: Path, path: Path, *, execution_commit: str, run_id: str) -> dict:
    """Verify the complete retained archive and every normalized row offline."""
    contract = validate_contract(root)
    execution = frozen(root / EXECUTION_PATH)
    require_exact(execution, execution_payload(contract, code_commit=execution["code_commit_sha"],
        code_tree=execution["code_tree_sha"], workflow_sha256=file_sha(root / WORKFLOW_PATH)), "capture execution")
    marker = consumption_payload(execution, commit=execution_commit, run_id=run_id)
    source_receipt = verify_reuse_result(root)
    provenance = {"execution_content_sha256": execution["content_sha256"], "execution_commit_sha": execution_commit,
        "code_commit_sha": execution["code_commit_sha"], "code_tree_sha": execution["code_tree_sha"],
        "workflow_run_id": run_id, "workflow_run_attempt": 1,
        "consumption_marker_content_sha256": marker["content_sha256"],
        "source_validation_content_sha256": source_receipt["content_sha256"]}
    with zipfile.ZipFile(path) as archive:
        members = reuse._safe_members(archive, 28)
        inventory = reuse._sealed(archive.read("capture-inventory.json"))
        expected_names = {"contract.json", "execution.json", "consumption.json", "source-validation.json",
            "requests.json", "capture-report.json", "request-ledger.json", "capture-inventory.json"}
        expected_names.update(tape_path(r) for r in contract["requests"])
        expected_names.update("receipts/" + r["request_id"] + ".json" for r in contract["requests"])
        if set(members) != expected_names or set(inventory["files"]) != expected_names - {"capture-inventory.json"}:
            raise ValueError("capture archive inventory differs")
        for name, expected in inventory["files"].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError("capture member bytes differ: " + name)
        for name, expected in (("contract.json", contract), ("execution.json", execution),
                ("consumption.json", marker), ("source-validation.json", source_receipt),
                ("requests.json", seal({"requests": contract["requests"]}))):
            require_exact(reuse._sealed(archive.read(name)), expected, name)
        receipts, total_bytes, events, by_request = [], 0, [], {}
        for request in contract["requests"]:
            receipt = reuse._sealed(archive.read("receipts/" + request["request_id"] + ".json"))
            pages = receipt["pages"]
            if type(pages) is not int or not 1 <= pages <= MAX_ATTEMPTS:
                raise ValueError("invalid exhausted page count")
            compressed = archive.read(tape_path(request))
            total_bytes += len(compressed)
            if total_bytes > MAX_RETAINED_BYTES:
                raise ValueError("capture compressed byte ceiling exceeded")
            count, previous, tied, logical = 0, None, set(), hashlib.sha256()
            with archive.open(tape_path(request)) as raw, gzip.GzipFile(fileobj=raw) as tape:
                while True:
                    line = tape.readline(1001)
                    if not line:
                        break
                    if len(line) > 1000 or not line.endswith(b"\n") or count >= pages * PAGE_LIMIT:
                        raise ValueError("capture tape row or page ceiling exceeded")
                    encoded, previous = checked_record(reuse._json(line), request, previous, tied)
                    if encoded != line:
                        raise ValueError("capture normalized source bytes differ")
                    logical.update(line)
                    count += 1
            expected = {"request_id": request["request_id"], "path": tape_path(request), "record_count": count,
                "pages": pages, "complete": True, "empty_exhausted_segment": count == 0,
                "logical_sha256": logical.hexdigest(), "file_sha256": hashlib.sha256(compressed).hexdigest(),
                "retained_bytes": len(compressed)}
            require_exact(receipt, seal(expected), "capture receipt")
            receipts.append(expected)
            by_request[request["request_id"]] = pages
            for _ in range(pages):
                events.append({"attempt": len(events) + 1, "request_id": request["request_id"]})
        attempts = len(events)
        if attempts > MAX_ATTEMPTS:
            raise ValueError("capture HTTP attempt ceiling exceeded")
        ledger = reuse._json(archive.read("request-ledger.json"))
        require_exact(ledger, {"schema_version": 1, "contract_id": CONTRACT_ID, "total_attempts": attempts,
            "by_host": {"data.alpaca.markets": attempts}, "blocked_attempts": 0,
            "by_request": by_request, "attempt_events": events}, "separate capture attempt ledger")
        report = seal({"schema_version": 1, "contract_id": CONTRACT_ID, "status": "complete",
            "contract_content_sha256": contract["content_sha256"], "provenance": provenance,
            "logical_requests_completed": 10, "receipts": receipts, "normalized_compressed_bytes": total_bytes,
            "next_gate": NEXT_GATE, **BOUNDARY})
        require_exact(reuse._sealed(archive.read("capture-report.json")), report, "complete capture report")
        require_exact(inventory, seal({"files": inventory["files"], "provenance": provenance,
            "complete": True, "provider_attempts": attempts, "blocked_attempts": 0, **BOUNDARY}), "capture inventory")
    return seal({"schema_version": 1, "verification_passed": True, "contract_id": CONTRACT_ID,
        "capture_zip_sha256": file_sha(path), "capture_zip_bytes": path.stat().st_size,
        "verified_file_count": 28, "verified_logical_requests": 10,
        "provider_attempts": attempts, "blocked_attempts": 0, "normalized_compressed_bytes": total_bytes,
        "normalized_row_count": sum(r["record_count"] for r in receipts),
        "empty_exhausted_segments": sum(r["empty_exhausted_segment"] for r in receipts),
        "receipts": receipts, "file_inventory": inventory["files"], "provenance": provenance,
        "unavailable_entry_opportunities_preserved": 23, "next_gate": NEXT_GATE, **BOUNDARY})
