"""Bounded exit-source acquisition, preserving original entry availability.

The frozen 80 requests are separate from original entry tapes and verified XAGE
reuse. Native decoding, normalization and HTTP mechanics are inherited unchanged.
"""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import tempfile

from momentumbot.research import sealed_historical_management_exit_quote_v01 as quote
from momentumbot.research import sealed_historical_execution_acquisition_v03 as native_parent
from momentumbot.research import sealed_historical_execution_acquisition_v02 as parent
from momentumbot.research.prospective_market_input_acquisition import _normalize_store

CONTRACT_ID = "sealed-historical-management-exit-acquisition-v0.1"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
EXECUTION_PATH = f"research/strategy/{CONTRACT_ID}-execution.json"
WORKFLOW_PATH = ".github/workflows/sealed-historical-management-exit-acquisition-v01.yml"
LIMITS_PATH = f"research/runtime/{CONTRACT_ID}/request-limits.json"
CONSUMPTION_REF = f"refs/tags/{CONTRACT_ID}-consumed"
PARENT_COMMIT = "0d36c619dc1d3ac8c50bf7fa91201114255e696c"
PARENT_TREE = "2b81488d219cc9c50147c5617003e07ab95d9d19"
QUOTE_AUDIT_PATH = "research/data-audits/sealed-historical-management-exit-quote-v0.1-independent-verification-34169338681.json"
QUOTE_REPORT_PATH = "research/data-audits/sealed-historical-management-exit-quote-v0.1-report-34169338681.json"
QUOTE_REPORT_CONTENT_SHA = "ad28f542b6497b6a63e6d4a5aa50d15092f2b8e2472474beecde8e884f11812d"
REQUEST_LIST_SHA = quote.REQUEST_LIST_SHA256
MAX_BILLABLE_BYTES = 209_898_320
MAX_COST_USD = "0.234732925899"
MAX_NATIVE_BYTES = native_parent.MAX_NATIVE_BYTES
MAX_RETAINED_BYTES = parent.MAX_RETAINED_BYTES
MAX_NORMALIZED_BYTES = parent.MAX_UNCOMPRESSED_NORMALIZED_BYTES
METADATA_RESERVE_BYTES = 16_000_000
NEXT_GATE = "independent_exact_exit_capture_verification_then_registered_source_composition_preserving_unavailable_entries"
seal, frozen, file_sha, write_json = quote.seal, quote.frozen, quote.file_sha, quote.write_json
diagnostic = native_parent.diagnostic
native_summary = native_parent.native_summary
validate_native_observation = native_parent.validate_native_observation
tape_records = native_parent.tape_records
extract_exact_zip = native_parent.extract_exact_zip
error_code, SAFE_ERRORS = native_parent.error_code, native_parent.SAFE_ERRORS
environment = parent.environment
collect_quote = quote.collect_quote
FALSE_FLAGS = {k: False for k in ("acquisition_gate_passed", "runtime_input_eligible",
    "account_or_fill_simulation_executed", "backtesting_executed", "retrospective_inputs_loaded",
    "policy_changed", "consumed_parent_rerun", "raw_dbn_retained", "actual_billing_known",
    "historical_execution_authorized", "original_entry_inputs_changed")}

FROZEN_FILES = {'requirements-sealed-execution-quote-v01.txt': '03f4da335027e4c83bcf38e523c2e11aeaae49778f5bd6caa47e4703348b31b4',
 'research/data-audits/sealed-historical-management-exit-quote-v0.1-independent-verification-34169338681.json': '1423e00a1feced569a54a9078190410f6786188d2a24866718823978c90ace8a',
 'research/data-audits/sealed-historical-management-exit-quote-v0.1-report-34169338681.json': '85c4989a32ddb325ea70e280a43bdc31cc6e8e5f82eb41a10586901ee388196a',
 'research/data-audits/sealed-historical-management-exit-quote-v0.1-xage-reuse.json': '799d8664916eb89f713dec276134400e87434251ff97ea5c0b0a29219983e75b',
 'research/runtime/sealed-historical-management-runner-v0.1/exit-input-request-plan.json': '562ed42e20c7021eecf384e3a22aed5f5ce25ae15926dd93072a0313d0e6f461',
 'research/strategy/sealed-historical-management-exit-quote-v0.1-execution.json': '26876f023f4256a8b6136103417cd7a162f743b5c53e6e887e7f7ba24d74e706',
 'research/strategy/sealed-historical-management-exit-quote-v0.1.json': 'e4698c20ccf5b78195ea1d2a713de1c6d4d0a1e0c624b8b7e3e446441a1b899e',
 'src/momentumbot/research/sealed_historical_execution_acquisition_v02.py': '92877530ccbea68c1842e76e2438806db935ccad9cad326a119e1cda7065628f',
 'src/momentumbot/research/sealed_historical_execution_acquisition_v03.py': 'cb75e8648fbd333aa578c4045c778377a9eddfba4cf4b2de9ed1cdd5367fa8a8',
 'src/momentumbot/research/sealed_historical_execution_transport_v01.py': '3df2150f8970d1a6199cdf2bfcd5bcdfc35970e4257c90b54b8754218bdd91a3',
 'src/momentumbot/research/sealed_historical_management_exit_metadata_transport_v01.py': 'c3d9f032f9f39c536d4b2a5ce17bac2fdbaf923be2c36fbaa230b33f35dddf6a',
 'src/momentumbot/research/sealed_historical_management_exit_quote_v01.py': '079200a3d0dededb5a3b775f46330ce3558d98fc8c1b67b10b2ce246cf8549f7',
 'src/momentumbot/research/sealed_historical_record_order_v01.py': '407e02fc6fe908e26715fac2799f0debf356e96336b640e795b50287762dec6b'}

PARENT_ARTIFACTS = {'quote-consumption.zip': {'bytes': 14586,
                           'conclusion': 'success',
                           'execution_commit_sha': 'fde309481843b7c2613d9a673f888f488a1ee795',
                           'file_count': 10,
                           'id': 10035216510,
                           'kind': 'consumption',
                           'name': 'sealed-historical-management-exit-quote-v01-consumption-34169338681-1',
                           'run_id': 34169338681,
                           'sha256': '2eecb6ddaa076ade83de301989365ce9d6d23fe5b4ae42636a2f2659a9ef655c',
                           'workflow_path': '.github/workflows/sealed-historical-management-exit-quote-v01.yml'},
 'quote-result.zip': {'bytes': 23885,
                      'conclusion': 'success',
                      'execution_commit_sha': 'fde309481843b7c2613d9a673f888f488a1ee795',
                      'file_count': 9,
                      'id': 10035254551,
                      'kind': 'result',
                      'name': 'sealed-historical-management-exit-quote-v01-result-34169338681-1',
                      'run_id': 34169338681,
                      'sha256': '993e5d6a17512c5383ee2f23a298db3a22e68dc73eefb624e5f675a39bf38b65',
                      'workflow_path': '.github/workflows/sealed-historical-management-exit-quote-v01.yml'}}

IMMUTABLE_REFS = {'heads/main': 'de24eb17316191da69d92e61f6843af25e9c22d0',
 'tags/sealed-historical-execution-input-acquisition-v0.1-consumed': '5a375f86e951b1e9eeb6c010995c9b57025913b7',
 'tags/sealed-historical-execution-input-acquisition-v0.2-consumed': 'e2c250367895d209ec4706288a22655636298685',
 'tags/sealed-historical-execution-input-acquisition-v0.3-consumed': '0c4010044ee8557136b3c119c6350e134bba46d2',
 'tags/sealed-historical-execution-input-diagnostic-v0.1-consumed': 'e1aece08a44ccf9add0157a1657d08a809687e85',
 'tags/sealed-historical-execution-input-empty-diagnostic-v0.1-consumed': '8854bb2e63dc3961d98c5d8827f857ef85ccb341',
 'tags/sealed-historical-execution-input-quote-v0.1-consumed': 'dd295304dcc5e7cc0ebd300d094ab20636a72b92',
 'tags/sealed-historical-management-exit-quote-v0.1-consumed': 'fde309481843b7c2613d9a673f888f488a1ee795',
 'tags/sealed-historical-management-missing-input-acquisition-v0.1-consumed': 'eeec1ea234214a9d4a449e774fe3fa29aefea025',
 'tags/sealed-historical-micro-input-acquisition-v0.1-consumed': '5cab2eb3aa2b73a2cbf1d57575519a7b99961e24',
 'tags/sealed-historical-micro-session-input-acquisition-v0.2-consumed': 'bf5863a7115abef9e22c4f527448cd9c20084f47',
 'tags/sealed-historical-source-acquisition-v04-consumed-bbe51f4483a73f92b1f58c9f6c2085d8a47505346c2d340fbe59c0421f3f31b7': 'ae55aabd3963a9d2764b19a759efd271c723a83a',
 'tags/sealed-historical-source-acquisition-v05-consumed-23ad997837490c14c200c10b34c8285db7b18ddebca131e6299a8cd70b3bbc49': '12d3c08dcfa042f785c6e35060916cfbd47a1df8',
 'tags/sealed-historical-source-acquisition-v06-consumed-0343efff8ceb49b7c3ae2e589029cf4cf0b02d72c1961f85807913f67385202e': '0d231ffecb6d4104aad53dec0b7499a16d8943f6',
 'tags/sealed-historical-source-acquisition-v09-consumed-447c11b09206b4c19ccade6c1aae70ce5bb17e4a483db6f9581d14ee3f5f862f': '92d8b4deceae5c2bb6edfb10016a0e05c33c8bfa',
 'tags/sealed-historical-source-acquisition-v10-consumed-a6519754147c39273a25b2ea818b1906dfa93ea5018edac831e2a0a7052463c7': '652db5675a35b6f455aa0d924aa50428dd995280'}


def contract() -> dict:
    return seal({"contract_id": CONTRACT_ID,
        "artifact_type": "registered_quote_bound_management_exit_acquisition",
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "hypothesis": "exact_missing_exit_sources_can_be_captured_without_replacing_entry_evidence_or_reacquiring_XAGE",
        "parent_artifacts": PARENT_ARTIFACTS, "frozen_file_sha256": FROZEN_FILES,
        "request_list_sha256": REQUEST_LIST_SHA, "new_request_count": 80,
        "new_request_indices": list(range(80)), "new_symbol_date_count": 40,
        "common_symbol_date_count": 41, "verified_reuse_request_count": 2,
        "opportunity_count": 109, "unavailable_entry_count": 23, "original_date_count": 30,
        "account_path_count": 12, "account_session_slot_count": 360,
        "quote_report_content_sha256": QUOTE_REPORT_CONTENT_SHA,
        "maximum_billable_bytes": MAX_BILLABLE_BYTES, "maximum_quoted_cost_usd": MAX_COST_USD,
        "per_request_ceiling": "each_exact_verified_exit_quote_size_and_cost",
        "maximum_metadata_attempts": 160, "maximum_timeseries_attempts": 80, "maximum_http_attempts": 240,
        "wire_ceiling": "original_per_request_billable_bytes_plus_65536",
        "maximum_decompressed_native_bytes_per_request": MAX_NATIVE_BYTES,
        "maximum_retained_bytes": MAX_RETAINED_BYTES, "maximum_normalized_bytes": MAX_NORMALIZED_BYTES,
        "metadata_and_parent_archive_reserve_bytes": METADATA_RESERVE_BYTES,
        "normalizer": "unchanged_v02_lossless_record_order_adapter",
        "native_decoder": "unchanged_v03_complete_native_stream_and_exact_session_mapping",
        "metadata_only_rule": "zero_native_and_normalized_records_with_complete_metadata_emit_unavailable_receipt_no_empty_tape",
        "failure_rule": "stop_on_transport_truncation_metadata_mapping_normalization_or_write_failure_retain_partial_evidence",
        "continue_after": "only_complete_nonempty_tape_or_verified_metadata_only_unavailable_receipt",
        "raw_dbn_retention": "hash_then_delete_in_finally_never_artifact",
        "temporary_cleanup_attestation": "true_only_after_temporary_directory_exit_succeeds",
        "entry_availability": "all_original_109_entries_and_23_unavailable_classifications_preserved_no_rescue_or_price_replacement",
        "reuse": "exact_XAGE_byte_receipt_and_original_request_identity_preserved_no_new_provider_call",
        "evidence_complete_is_runtime_eligibility": False,
        "original_source_provider_request_total": 30522, "new_provider_ledger_is_separate": True,
        "consumption_ref": CONSUMPTION_REF, "immutable_refs": IMMUTABLE_REFS,
        "sdk_version": quote.SDK_VERSION, "python_version": "3.12.14",
        "requirements_path": quote.LOCK_PATH, "requirements_sha256": quote.LOCK_SHA256,
        "automatic_retry_count": 0, "redirects_allowed": False,
        "durable_consumption_before_provider_required": True,
        "execution_record_required_for_provider_access": True,
        **FALSE_FLAGS, "next_gate": NEXT_GATE})


def validate_requests(requests: list[dict]) -> None:
    quote.validate_requests(requests)


def request_limits(requests: list[dict], quoted: dict) -> dict:
    validate_requests(requests)
    if quoted["content_sha256"] != QUOTE_REPORT_CONTENT_SHA:
        raise ValueError("exact verified exit quote required")
    quote.require_exact(quoted, seal({k:v for k,v in quoted.items() if k != "content_sha256"}), "quote seal")
    rows = []
    for i, (request, row) in enumerate(zip(requests, quoted["quote_rows"], strict=True)):
        if request["request_id"] != row["request_id"] or row["schema"] != request["schema"]:
            raise ValueError("exact quote/request identity differs")
        rows.append({"exit_request_index": i, "request": request,
            "request_content_sha256": quote.canonical_fingerprint(request),
            "maximum_billable_bytes": row["billable_size_bytes"],
            "maximum_quoted_cost_usd": row["quoted_cost_usd"],
            "maximum_wire_bytes": row["billable_size_bytes"] + 65536})
    if (sum(r["maximum_billable_bytes"] for r in rows) != MAX_BILLABLE_BYTES
        or sum((Decimal(r["maximum_quoted_cost_usd"]) for r in rows), Decimal(0)) != Decimal(MAX_COST_USD)):
        raise ValueError("exact aggregate quote ceilings differ")
    return seal({"contract_id": CONTRACT_ID, "request_list_sha256": REQUEST_LIST_SHA,
        "quote_report_content_sha256": QUOTE_REPORT_CONTENT_SHA,
        "reuse_evidence_file_sha256": quote.REUSE_FILE_SHA256,
        "maximum_billable_bytes": MAX_BILLABLE_BYTES, "maximum_quoted_cost_usd": MAX_COST_USD,
        "request_limits": rows, "provider_calls": 0, "execution_record_required": True})


def validate_inputs(root: Path) -> tuple[list[dict], dict]:
    for name, expected in FROZEN_FILES.items():
        quote.availability._regular(root / name)
        if file_sha(root / name) != expected:
            raise ValueError("frozen acquisition parent differs: " + name)
    requests = quote.validate_inputs(root)
    quoted = frozen(root / QUOTE_REPORT_PATH)
    audit = frozen(root / QUOTE_AUDIT_PATH)
    quote.validate_report(quoted, requests, audit["primary_quote_verification"]["provenance"])
    if quoted["metadata_quote_gate_passed"] is not True:
        raise ValueError("successful parent exit quote required")
    quote.require_exact(frozen(root / LIMITS_PATH), request_limits(requests, quoted), "per-request acquisition limits")
    quote.require_exact(frozen(root / CONTRACT_PATH), contract(), "exit acquisition registration")
    return requests, quoted


def verify_parents(evidence: Path, root: Path) -> dict:
    """Check both exact quote ZIPs against all independently measured members."""
    requests, quoted = validate_inputs(root)
    audit = frozen(root / QUOTE_AUDIT_PATH)
    observed = {}
    with tempfile.TemporaryDirectory(prefix="exit-acquisition-quote-check-") as tmp:
        for name, spec in PARENT_ARTIFACTS.items():
            path = evidence / name
            quote.availability._regular(path)
            if path.stat().st_size != spec["bytes"]:
                raise ValueError("exact quote ZIP size differs")
            destination = Path(tmp) / spec["kind"]
            extract_exact_zip(path, destination, spec["sha256"])
            inventory = quote.availability._inventory(destination)
            expected = audit["independent_quote_verification"]["archives"][spec["kind"]]
            if len(inventory) != spec["file_count"]:
                raise ValueError("exact quote ZIP member count differs")
            quote.require_exact(inventory, expected["files"], "complete quote ZIP inventory")
            for member, source in (("contract.json", quote.CONTRACT_PATH), ("execution.json", quote.EXECUTION_PATH),
                ("request-manifest.json", quote.PLAN_PATH + "/request-manifest.json"), ("xage-reuse.json", quote.REUSE_PATH)):
                if (destination / member).read_bytes() != (root / source).read_bytes():
                    raise ValueError("original quote bound metadata differs")
            if spec["kind"] == "result":
                if (destination / "quote-report.json").read_bytes() != (root / QUOTE_REPORT_PATH).read_bytes():
                    raise ValueError("original quote report bytes differ")
                quote.validate_report(frozen(destination / "quote-report.json"), requests,
                    audit["primary_quote_verification"]["provenance"])
            observed[name] = {"bytes": spec["bytes"], "sha256": spec["sha256"], "file_count": len(inventory)}
    return seal({"verification_passed": True, "parent_archives": observed,
        "quote_report_content_sha256": QUOTE_REPORT_CONTENT_SHA,
        "reuse_evidence_file_sha256": quote.REUSE_FILE_SHA256,
        "original_source_provider_requests": 30522, "new_provider_calls": 0})


def coverage(rows: list[dict], root: Path) -> list[dict]:
    requests = frozen(root / quote.PLAN_PATH / "request-manifest.json")["requests"]
    result = []
    for i, request in enumerate(requests):
        status = rows[i]["status"] if i < len(rows) else "unattempted"
        result.append({"exit_request_index": i, "request_id": request["request_id"],
            "request_content_sha256": quote.canonical_fingerprint(request), "status": status,
            "evidence": f"receipts/request-{i:03d}.json" if status in {"complete", "unavailable"}
                else ("download-ledger.json" if status == "failed" else None),
            "runtime_input_eligible": False})
    return result


def execution_payload(*, code_commit: str, code_tree: str, workflow_sha256: str,
                      ci_run_id: str, validation_run_id: str) -> dict:
    quote.execution_payload(code_commit=code_commit, code_tree=code_tree, workflow_sha256=workflow_sha256,
        ci_run_id=ci_run_id, validation_run_id=validation_run_id)
    return seal({"execution_id": CONTRACT_ID+"-execution", "contract_content_sha256": contract()["content_sha256"],
        "code_commit_sha": code_commit, "code_tree_sha": code_tree, "workflow_file_sha256": workflow_sha256,
        "workflow_path": WORKFLOW_PATH, "code_ci_run_id": ci_run_id, "code_validation_run_id": validation_run_id,
        "repository": "RoomyRems/momentumbot", "branch": "phase-3-historical-snapshot", "event": "push", "run_attempt": 1,
        "consumption_ref": CONSUMPTION_REF, "request_list_sha256": REQUEST_LIST_SHA,
        "parent_artifacts": PARENT_ARTIFACTS, "maximum_http_attempts": 240,
        "maximum_billable_bytes": MAX_BILLABLE_BYTES, "maximum_quoted_cost_usd": MAX_COST_USD,
        "authority": "user_authorized_continued_development_and_operational_steps_2026-09-07",
        "exact_management_exit_acquisition_authorized": True, "account_or_order_authority": False})


def validate_execution(root: Path, env: dict) -> dict:
    value = frozen(root/EXECUTION_PATH)
    quote.require_exact(value, execution_payload(code_commit=env.get("EXECUTION_CODE_COMMIT_SHA", ""),
        code_tree=env.get("EXECUTION_CODE_TREE_SHA", ""), workflow_sha256=file_sha(root/WORKFLOW_PATH),
        ci_run_id=value["code_ci_run_id"], validation_run_id=value["code_validation_run_id"]), "sole execution child")
    for key, expected in {"GITHUB_REPOSITORY": "RoomyRems/momentumbot", "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": "refs/heads/phase-3-historical-snapshot", "GITHUB_RUN_ATTEMPT": "1"}.items():
        if env.get(key) != expected: raise ValueError("exact first research push required")
    if not re.fullmatch("[0-9a-f]{40}", env.get("GITHUB_SHA", "")) or not re.fullmatch("[1-9][0-9]+", env.get("GITHUB_RUN_ID", "")):
        raise ValueError("exact execution provenance required")
    return value


def consumption(execution: dict, env: dict) -> dict:
    return seal({"execution_content_sha256": execution["content_sha256"], "consumption_ref": CONSUMPTION_REF,
        "execution_commit_sha": env["GITHUB_SHA"], "workflow_run_id": env["GITHUB_RUN_ID"], "workflow_run_attempt": 1,
        "request_list_sha256": REQUEST_LIST_SHA, "parent_artifacts": PARENT_ARTIFACTS})


def preflight(requests: list[dict], quoted: dict, calls: list[dict], http_attempts: int, blocked_attempts: int) -> dict:
    validate_requests(requests)
    request_limits(requests, quoted)
    if quoted["content_sha256"] != QUOTE_REPORT_CONTENT_SHA:
        raise ValueError("exact original quote required")
    quote.require_exact(quoted, seal({k:v for k,v in quoted.items() if k != "content_sha256"}), "quote seal")
    if (len(calls) > 160 or type(http_attempts) is not int or not 0 <= http_attempts <= len(calls)
        or type(blocked_attempts) is not int or blocked_attempts < 0):
        raise ValueError("metadata attempt ceiling or accounting differs")
    for i, entry in enumerate(calls):
        request, method = requests[i//2], quote.METHODS[i%2]
        identity = {"ordinal": i+1, "request_id": request["request_id"],
            "request_content_sha256": quote.canonical_fingerprint(request), "method": method}
        if set(entry) != set(identity)|{"status", "value", "error"}: raise ValueError("metadata fields differ")
        quote.require_exact({k:entry[k] for k in identity}, identity, "metadata request prefix")
        if entry["status"] == "success":
            if entry["error"] is not None or quote._value(method, entry["value"]) != entry["value"]:
                raise ValueError("metadata value differs")
        elif entry["status"] not in {"error", "pending"} or entry["value"] is not None:
            raise ValueError("invalid metadata result")
        elif entry["status"] == "pending" and entry["error"] is not None:
            raise ValueError("pending metadata error must be null")
        elif entry["status"] == "error" and entry["error"] not in quote.SAFE_ERRORS:
            raise ValueError("unsanitized metadata error")
    ready = len(calls) == http_attempts == 160 and blocked_attempts == 0 and all(c["status"] == "success" for c in calls)
    rows = []
    if ready:
        for i, request in enumerate(requests):
            size, cost = calls[2*i]["value"], calls[2*i+1]["value"]
            limit = quoted["quote_rows"][i]
            available = (0 < size <= limit["billable_size_bytes"] and Decimal(0) <= Decimal(cost) <= Decimal(limit["quoted_cost_usd"]))
            rows.append({"request_id": request["request_id"], "billable_size_bytes": size, "quoted_cost_usd": cost,
                "within_original_ceiling": available})
        ready = all(r["within_original_ceiling"] for r in rows)
    size_total = sum(row["billable_size_bytes"] for row in rows) if rows else None
    cost_total = format(sum((Decimal(row["quoted_cost_usd"]) for row in rows), Decimal(0)), "f") if rows else None
    ready = ready and size_total <= MAX_BILLABLE_BYTES and Decimal(cost_total) <= Decimal(MAX_COST_USD)
    return seal({"contract_id": CONTRACT_ID, "request_list_sha256": REQUEST_LIST_SHA, "calls": calls,
        "http_attempts": http_attempts, "blocked_attempts": blocked_attempts, "quote_rows": rows,
        "total_billable_bytes": size_total, "total_quoted_cost_usd": cost_total, "preflight_passed": ready})


def download_ledger(rows: list[dict]) -> dict:
    return seal({"requests": rows, "evidence_complete": len(rows) == 80 and all(r["status"] in {"complete", "unavailable"} for r in rows)})


def acquire_tapes(requests: list[dict], quoted: dict, requote: dict, *, client, output: Path,
                  temporary_root: Path, progress=None) -> list[dict]:
    validate_requests(requests)
    quote.require_exact(requote, preflight(requests, quoted, requote["calls"], requote["http_attempts"], requote["blocked_attempts"]), "complete exit requote")
    if not requote["preflight_passed"]: raise ValueError("complete bounded requote required")
    rows, normalized, retained = [], 0, METADATA_RESERVE_BYTES
    for i, request in enumerate(requests):
        original = i; stem = f"request-{original:03d}"
        raw = temporary_root/f"request-{i:03d}.dbn.zst"
        tape, receipt = output/"tapes"/(stem+".jsonl.gz"), output/"receipts"/(stem+".json")
        tape.parent.mkdir(exist_ok=True); receipt.parent.mkdir(exist_ok=True)
        row = {"ordinal": i+1, "exit_request_index": original, "request_id": request["request_id"],
            "request_content_sha256": quote.canonical_fingerprint(request), "schema": request["schema"],
            "status": "failed", "error": None, "failure_stage": None, "native": None,
            "tape": None, "normalization": None, "unavailable": None, "partial": []}
        rows.append(row); store = None; stage = "download"
        try:
            if progress: progress(download_ledger(rows))
            store = client.get_range(**quote.request_kwargs(request), path=raw)
            stage = "native_validation"
            row["native"] = native_summary(raw, request, quoted["quote_rows"][original]["billable_size_bytes"]+65536)
            stage = "normalization"
            try:
                records = parent.normalize(store, request)
            except ValueError as exc:
                if diagnostic.error_code(exc) != "empty_exact_request": raise
                if row["native"]["native_record_count"] != 0 or _normalize_store(store, request) != []:
                    raise ValueError("native and normalized emptiness differ") from None
                row.update(status="unavailable", unavailable={"code": "metadata_only_exact_request",
                    "native_record_count": 0, "normalized_row_count": 0, "runtime_input_eligible": False,
                    "resting_quote_or_trading_status_inferred": False})
            else:
                if len(records) != row["native"]["native_record_count"]:
                    raise ValueError("native mapped row count differs")
                row["normalization"] = parent.normalization_summary(records, request)
                stage = "normalized_tape_write"
                info = parent.write_tape(tape, records, maximum_file_bytes=MAX_RETAINED_BYTES-retained,
                    maximum_normalized_bytes=MAX_NORMALIZED_BYTES-normalized)
                row["tape"] = {"path": tape.relative_to(output).as_posix(), **info}
                normalized += info["normalized_bytes"]; retained += info["file_bytes"]
                row["status"] = "complete"
            stage = "receipt_write"
            write_json(receipt, seal({"contract_id": CONTRACT_ID, "request": request, "completion": row,
                "raw_dbn_persisted": False, "record_order_adapter_sha256": parent.ADAPTER_CONTRACT_SHA}))
        except Exception as exc:
            row.update(status="failed", error=error_code(exc), failure_stage=stage, tape=None,
                normalization=None, unavailable=None)
            for path in (tape, receipt):
                if path.exists():
                    dest = output/"partial"/(path.name+".partial"); dest.parent.mkdir(exist_ok=True)
                    path.replace(dest)
                    row["partial"].append({"path": dest.relative_to(output).as_posix(), "bytes": dest.stat().st_size,
                        "sha256": file_sha(dest), "runtime_input_eligible": False})
        finally:
            try:
                if store is not None:
                    reader = getattr(store, "reader", None)
                    if reader is not None: reader.close()
            finally:
                raw.unlink(missing_ok=True)
                if progress: progress(download_ledger(rows))
        if row["status"] == "failed": break
    return rows


def build_report(rows: list[dict], metadata_http: dict, timeseries: dict, requote: dict | None,
                 provenance: dict, root: Path, error: str | None, *, raw_temp_removed: bool = True) -> dict:
    if type(raw_temp_removed) is not bool:
        raise ValueError("explicit temporary cleanup state required")
    complete = (len(rows) == 80 and all(r["status"] in {"complete", "unavailable"} for r in rows)
        and metadata_http["http_attempts"] == 160 and timeseries["http_attempts"] == 80
        and metadata_http["blocked_attempts"] == timeseries["blocked_attempts"] == 0
        and requote is not None and requote["preflight_passed"] and error is None and raw_temp_removed)
    return seal({"contract_id": CONTRACT_ID, "artifact_type": "historical_management_exit_input_evidence_report",
        "provenance": provenance, "requests": rows, "coverage": coverage(rows, root),
        "verified_reuse_request_count": 2, "unavailable_entry_count": 23,
        "original_opportunities": frozen(root / quote.EXIT_PLAN_PATH)["opportunities"],
        "reuse_evidence_file_sha256": quote.REUSE_FILE_SHA256,
        "new_complete_count": sum(r["status"] == "complete" for r in rows),
        "new_unavailable_count": sum(r["status"] == "unavailable" for r in rows),
        "unattempted_count": 80-len(rows), "new_normalized_row_count": sum(r["tape"]["row_count"] for r in rows if r["tape"]),
        "original_date_count": 30, "opportunity_count": 109, "new_symbol_date_count": 40,
        "common_symbol_date_count": 41,
        "metadata_http_attempts": metadata_http["http_attempts"], "timeseries_http_attempts": timeseries["http_attempts"],
        "http_attempts": metadata_http["http_attempts"]+timeseries["http_attempts"],
        "blocked_attempts": metadata_http["blocked_attempts"]+timeseries["blocked_attempts"],
        "request_evidence_complete": bool(complete), "requote": requote, "error": error,
        "original_source_provider_requests": 30522, "raw_temp_directory_removed": raw_temp_removed,
        **FALSE_FLAGS, "next_gate": NEXT_GATE})


def write_inventory(output: Path, report: dict, *, replace=False) -> None:
    files = {p.relative_to(output).as_posix(): {"sha256": file_sha(p), "bytes": p.stat().st_size}
        for p in sorted(output.rglob("*")) if p.is_file() and p != output/"capture-inventory.json"}
    write_json(output/"capture-inventory.json", seal({"contract_id": CONTRACT_ID, "files": files,
        "provenance": report["provenance"], "request_evidence_complete": report["request_evidence_complete"],
        "acquisition_gate_passed": False}), replace=replace)


def validate_http_ledger(ledger: dict, *, metadata: bool) -> None:
    """Retain failed attempts while rejecting rehashed type/field substitutions."""
    ceiling = 160 if metadata else 80
    forbidden = "non_metadata_calls" if metadata else "unregistered_endpoint_calls"
    fields = {"http_attempts", "blocked_attempts", "attempts", "automatic_retries",
        "redirects_followed", forbidden, "content_sha256"}
    if set(ledger) != fields or type(ledger["attempts"]) is not list:
        raise ValueError("HTTP ledger fields differ")
    quote.require_exact(ledger, seal({k:v for k,v in ledger.items() if k != "content_sha256"}), "HTTP ledger seal")
    for field in ("http_attempts", "blocked_attempts", "automatic_retries", "redirects_followed", forbidden):
        if type(ledger[field]) is not int or ledger[field] < 0:
            raise ValueError("HTTP ledger counters must be integers")
    if (ledger["http_attempts"] != len(ledger["attempts"]) or ledger["http_attempts"] > ceiling
        or any(ledger[k] != 0 for k in ("automatic_retries", "redirects_followed", forbidden))):
        raise ValueError("separate ledger boundary differs")
    for i, attempt in enumerate(ledger["attempts"]):
        expected = {"ordinal", "request_id", "method", "status", "http_status"}
        if not metadata:
            expected |= {"request_content_sha256", "wire_bytes", "maximum_wire_bytes"}
        if set(attempt) != expected or type(attempt["ordinal"]) is not int or attempt["ordinal"] != i+1:
            raise ValueError("HTTP attempt fields or ordinal differ")
        if attempt["http_status"] is not None and (type(attempt["http_status"]) is not int
            or not 100 <= attempt["http_status"] <= 599):
            raise ValueError("HTTP status must be a bounded integer or null")
        if attempt["status"] not in ({"pending", "success", "error"} if metadata else {"pending", "complete", "failed"}):
            raise ValueError("HTTP attempt status differs")
        if attempt["status"] in {"success", "complete"} and attempt["http_status"] != 200:
            raise ValueError("successful HTTP attempt requires status 200")
        if not metadata:
            for field, minimum in (("wire_bytes", 0), ("maximum_wire_bytes", 1)):
                if type(attempt[field]) is not int or attempt[field] < minimum:
                    raise ValueError("wire accounting must use bounded integers")
            if attempt["status"] == "complete" and not 0 < attempt["wire_bytes"] <= attempt["maximum_wire_bytes"]:
                raise ValueError("completed wire transfer exceeds its bound")


def verify_capture(output: Path, root: Path, *, require_complete=False) -> dict:
    requests, quoted = validate_inputs(root)
    inherited = verify_parents(output, root)
    report, inv = frozen(output/"capture-report.json"), frozen(output/"capture-inventory.json")
    actual = {}
    for path in sorted(output.rglob("*")):
        if path.is_symlink(): raise ValueError("symlink in capture")
        if path.is_file() and path != output/"capture-inventory.json":
            actual[path.relative_to(output).as_posix()] = {"sha256": file_sha(path), "bytes": path.stat().st_size}
    quote.require_exact(actual, inv["files"], "complete retained inventory")
    if sum(x["bytes"] for x in actual.values()) > MAX_RETAINED_BYTES: raise ValueError("retention ceiling exceeded")
    for name in actual:
        if name.endswith(".json"): frozen(output/name)
    expected = {*PARENT_ARTIFACTS, "contract.json", "execution.json", "consumption.json",
        "environment.json", "parent-verification.json", "metadata-http-ledger.json", "timeseries-http-ledger.json",
        "metadata-ledger.json", "download-ledger.json", "capture-report.json"}
    for captured, source in (("contract.json", CONTRACT_PATH), ("execution.json", EXECUTION_PATH)):
        if (output/captured).read_bytes() != (root/source).read_bytes(): raise ValueError("frozen source bytes differ")
    quote.require_exact(frozen(output/"parent-verification.json"), inherited, "inherited byte verification")
    execution, marker = frozen(output/"execution.json"), frozen(output/"consumption.json")
    quote.require_exact(execution, execution_payload(code_commit=execution["code_commit_sha"], code_tree=execution["code_tree_sha"],
        workflow_sha256=file_sha(root/WORKFLOW_PATH), ci_run_id=execution["code_ci_run_id"],
        validation_run_id=execution["code_validation_run_id"]), "captured execution")
    quote.require_exact(marker, consumption(execution, {"GITHUB_SHA": marker["execution_commit_sha"],
        "GITHUB_RUN_ID": marker["workflow_run_id"]}), "captured consumption")
    provenance = {"execution_commit_sha": marker["execution_commit_sha"], "workflow_run_id": marker["workflow_run_id"],
        "workflow_run_attempt": 1, "execution_content_sha256": execution["content_sha256"],
        "consumption_content_sha256": marker["content_sha256"], "code_commit_sha": execution["code_commit_sha"],
        "code_tree_sha": execution["code_tree_sha"]}
    pins = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", (root/quote.LOCK_PATH).read_text(), re.M))
    quote.require_exact(frozen(output/"environment.json"), seal({"implementation": "CPython", "python_version": "3.12.14",
        "requirements_sha256": quote.LOCK_SHA256, "package_versions": pins}), "pinned environment")
    metadata_http, timeseries = (frozen(output/name) for name in ("metadata-http-ledger.json", "timeseries-http-ledger.json"))
    validate_http_ledger(metadata_http, metadata=True)
    validate_http_ledger(timeseries, metadata=False)
    metadata_ledger = frozen(output/"metadata-ledger.json")
    calls = metadata_ledger["calls"]
    preflight(requests, quoted, calls, metadata_http["http_attempts"], metadata_http["blocked_attempts"])
    quote.require_exact(metadata_ledger, seal({"calls": calls, "call_count": len(calls),
        "complete": len(calls) == 160 and calls[-1]["status"] != "pending"}), "complete or partial metadata journal")
    requote = frozen(output/"requote-report.json") if (output/"requote-report.json").exists() else None
    if requote is not None:
        expected.add("requote-report.json")
        quote.require_exact(requote, preflight(requests, quoted, calls, metadata_http["http_attempts"], metadata_http["blocked_attempts"]), "independent requote")
    for i, attempt in enumerate(metadata_http["attempts"]):
        if (attempt["ordinal"] != i+1 or attempt["request_id"] != requests[i//2]["request_id"]
            or attempt["method"] != quote.METHODS[i%2]): raise ValueError("metadata prefix differs")
        if requote is not None and requote["preflight_passed"] and (attempt["status"] != "success" or attempt["http_status"] != 200):
            raise ValueError("metadata success lacks HTTP evidence")
    rows = report["requests"]
    quote.require_exact(frozen(output/"download-ledger.json"), download_ledger(rows), "durable request ledger")
    if len(rows) > 80 or len(timeseries["attempts"]) > len(rows): raise ValueError("download prefix differs")
    if rows and (requote is None or requote["preflight_passed"] is not True): raise ValueError("downloads preceded complete requote")
    normalized = 0; schema_rows = {"mbp-1": 0, "status": 0}
    for i, row in enumerate(rows):
        request = requests[i]; original = i; sha = quote.canonical_fingerprint(request)
        identity = {"ordinal": i+1, "exit_request_index": original, "request_id": request["request_id"],
            "request_content_sha256": sha, "schema": request["schema"]}
        quote.require_exact({k:row[k] for k in identity}, identity, "request identity")
        if set(row) != set(identity)|{"status", "error", "failure_stage", "native", "tape", "normalization", "unavailable", "partial"}:
            raise ValueError("request fields differ")
        maximum = quoted["quote_rows"][original]["billable_size_bytes"]+65536
        if i < len(timeseries["attempts"]):
            attempt = timeseries["attempts"][i]
            if any(attempt[k] != row[k] for k in ("ordinal", "request_id", "request_content_sha256")) or attempt["method"] != "timeseries.get_range" or attempt["maximum_wire_bytes"] != maximum:
                raise ValueError("download attempt identity differs")
        elif row["status"] != "failed": raise ValueError("completed evidence lacks provider attempt")
        if row["status"] == "failed":
            if (i != len(rows)-1 or row["error"] not in SAFE_ERRORS or row["tape"] is not None
                or row["normalization"] is not None or row["unavailable"] is not None
                or row["failure_stage"] not in {"download", "native_validation", "normalization", "normalized_tape_write", "receipt_write"}):
                raise ValueError("invalid stopped failure")
            if row["native"] is not None:
                validate_native_observation(row["native"], request, maximum)
            for partial in row["partial"]:
                name = partial["path"]
                if (name not in {f"partial/request-{original:03d}.jsonl.gz.partial", f"partial/request-{original:03d}.json.partial"}
                    or partial["runtime_input_eligible"] is not False or actual.get(name) != {"sha256": partial["sha256"], "bytes": partial["bytes"]}):
                    raise ValueError("partial evidence differs")
                expected.add(name)
            continue
        if row["status"] not in {"complete", "unavailable"} or row["error"] is not None or row["failure_stage"] is not None or row["partial"]:
            raise ValueError("terminal classification differs")
        native = row["native"]
        validate_native_observation(native, request, maximum)
        if attempt["status"] != "complete" or attempt["http_status"] != 200 or attempt["wire_bytes"] != native["wire_bytes"]:
            raise ValueError("bounded completed native evidence differs")
        receipt = f"receipts/request-{original:03d}.json"
        quote.require_exact(frozen(output/receipt), seal({"contract_id": CONTRACT_ID, "request": request, "completion": row,
            "raw_dbn_persisted": False, "record_order_adapter_sha256": parent.ADAPTER_CONTRACT_SHA}), "exact terminal receipt")
        expected.add(receipt)
        if row["status"] == "unavailable":
            quote.require_exact(row["unavailable"], {"code": "metadata_only_exact_request", "native_record_count": 0,
                "normalized_row_count": 0, "runtime_input_eligible": False, "resting_quote_or_trading_status_inferred": False}, "explicit unavailable outcome")
            if (row["tape"] is not None or row["normalization"] is not None or native["native_record_count"] != 0
                or native["decoded_v3_record_bytes_sha256"] != hashlib.sha256(b"").hexdigest()):
                raise ValueError("unavailable evidence cannot become an empty tape")
        else:
            name = f"tapes/request-{original:03d}.jsonl.gz"
            records, info = tape_records(output/name)
            quote.require_exact(row["tape"], {"path": name, **info}, "full decompressed tape")
            quote.require_exact(row["normalization"], parent.normalization_summary(records, request), "frozen normalized semantics")
            if not records or native["native_record_count"] != len(records) or row["unavailable"] is not None:
                raise ValueError("native normalized population differs")
            normalized += info["normalized_bytes"]; schema_rows[request["schema"]] += len(records); expected.add(name)
    if normalized > MAX_NORMALIZED_BYTES or set(actual) != expected: raise ValueError("complete bounded inventory differs")
    if report["error"] not in {None, "credential_missing", "requote_unavailable_or_ceiling_exceeded", "download_or_normalization_failed", "acquisition_runtime_failed", "post_capture_verification_failed"}:
        raise ValueError("unsanitized report error")
    rebuilt = build_report(rows, metadata_http, timeseries, requote, provenance, root, report["error"],
        raw_temp_removed=report["raw_temp_directory_removed"])
    quote.require_exact(report, rebuilt, "independent report reconstruction")
    quote.require_exact(inv, seal({"contract_id": CONTRACT_ID, "files": actual, "provenance": provenance,
        "request_evidence_complete": report["request_evidence_complete"], "acquisition_gate_passed": False}), "inventory boundaries")
    if require_complete and not report["request_evidence_complete"]: raise ValueError("request evidence incomplete")
    return seal({"verification_passed": True, "file_count": len(actual)+1, "parent_file_count": 19,
        "report_file_sha256": file_sha(output/"capture-report.json"), "report_content_sha256": report["content_sha256"],
        "inventory_content_sha256": inv["content_sha256"], "new_normalized_bytes": normalized,
        "new_schema_row_counts": schema_rows, **{k:report[k] for k in ("request_evidence_complete", "new_complete_count",
            "new_unavailable_count", "unattempted_count", "http_attempts", "blocked_attempts", "acquisition_gate_passed")}})
