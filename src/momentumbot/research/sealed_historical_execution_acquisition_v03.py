"""One-shot acquisition of the 65 unattempted requests; empty evidence stays unavailable."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile

from momentumbot.research import sealed_historical_execution_acquisition_v02 as parent
from momentumbot.research import sealed_historical_execution_empty_diagnostic_v01 as diagnostic
from momentumbot.research import sealed_historical_execution_quote_v01 as quote
from momentumbot.research.prospective_market_input_acquisition import (
    _metadata_field, _metadata_value, _metadata_timestamp_ns, _normalize_store,
)

CONTRACT_ID = "sealed-historical-execution-input-acquisition-v0.3"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
EXECUTION_PATH = f"research/strategy/{CONTRACT_ID}-execution.json"
WORKFLOW_PATH = ".github/workflows/sealed-historical-execution-input-acquisition-v03.yml"
CONSUMPTION_REF = f"refs/tags/{CONTRACT_ID}-consumed"
PARENT_COMMIT = "b0bd86a49cd04225ee88740f9cc10ece83e33ec7"
PARENT_TREE = "d3efc3ef0719a3957759d1e3b13cb4ac8d97692e"
REQUEST_LIST_SHA = "9f96fe77746cd08fbbb6174bb2bea8baa3529a0cf3d71ab036abbf01aa75acae"
JVA_ZIP_SHA = "246ab302c949f22af2907fecba9e024b0c30b6901c91446f4401fab5627e91ea"
JVA_REPORT_SHA = "b7324d1e6f123a2adca163f8d8e609db6a173f200c36a180396b8dad734c7da7"
MAX_BILLABLE_BYTES = 131_758_640
MAX_COST_USD = "0.147390693429"
MAX_NATIVE_BYTES = 400_000_000
MAX_RETAINED_BYTES = parent.MAX_RETAINED_BYTES
MAX_NORMALIZED_BYTES = parent.MAX_UNCOMPRESSED_NORMALIZED_BYTES
METADATA_RESERVE_BYTES = 16_000_000
NEXT_GATE = "independent_complete_request_evidence_verification_then_registered_unavailable_input_resolution"
seal, frozen, file_sha, write_json = quote.seal, quote.frozen, quote.file_sha, quote.write_json
IMMUTABLE_REFS = {**diagnostic.IMMUTABLE_REFS,
    "tags/sealed-historical-execution-input-empty-diagnostic-v0.1-consumed":
        "8854bb2e63dc3961d98c5d8827f857ef85ccb341"}
FROZEN_FILES = {'.github/workflows/sealed-historical-execution-input-empty-diagnostic-v01.yml': '0a2e636a50782d3b7650f0781b20632ebfda7c2d2bc69b7d0ca6fd8e1b29e255',
 'research/data-audits/sealed-historical-execution-input-empty-diagnostic-v0.1-independent-verification-34079022132.json': 'd5a4091de7b99b6d02d6e4bee7d8ae445c7f8b2ac684df35b3313dd1887dc934',
 'research/data-audits/sealed-historical-execution-input-empty-diagnostic-v0.1-inventory-34079022132.json': '1ae5b32bc24cc126abd66a589b521d5a85cf6b7eb326dbe4cf390287d35842a0',
 'research/data-audits/sealed-historical-execution-input-empty-diagnostic-v0.1-native-observation-34079022132.json': '86614bdc373e4c9df45aadfe4deceea6bf075dacac048e413f621ead95433994',
 'research/data-audits/sealed-historical-execution-input-empty-diagnostic-v0.1-report-34079022132.json': 'e106fdd8a2293294636d73eed94774ea37178ce259141ae0fe6983df1f593bf9',
 'research/strategy/sealed-historical-execution-input-empty-diagnostic-v0.1-execution.json': '6420db933812ff3b47105cde660bc443e19c8d48d2b79f9356d4bef1bab0c248',
 'research/strategy/sealed-historical-execution-input-empty-diagnostic-v0.1.json': 'eff4879dd429f8eaee4e459d105f6ac388083522f0b40732a174d4ecec33430a',
 'scripts/diagnose_sealed_historical_execution_empty_input_v01.py': '64d22a54bf1b868d377e9d0886a15dab847af5e0b44a64fcb3232731c716e83c',
 'src/momentumbot/research/sealed_historical_execution_empty_diagnostic_transport_v01.py': '73a803c86d9c3b6d087d466703fef2aeffb9e504e0d091625ab2d1ac2f3dc3a8',
 'src/momentumbot/research/sealed_historical_execution_empty_diagnostic_v01.py': 'c638fe8c2580eed70790a399e71afea5cc3246aa3ad7b33c9e92a4573cd14219'}
PARENT_ARTIFACTS = {
    "parent-v02-result.zip": {"id": 10002303908, "run_id": 34076412463,
        "name": "sealed-historical-execution-input-v02-result-34076412463-1",
        "sha256": diagnostic.FAILURE_ZIP_SHA, "bytes": 1082253,
        "execution_commit_sha": "e2c250367895d209ec4706288a22655636298685",
        "workflow_path": parent.WORKFLOW_PATH, "conclusion": "failure"},
    "jva-empty-diagnostic.zip": {"id": 10003079091, "run_id": 34079022132,
        "name": "sealed-historical-execution-empty-diagnostic-v01-result-34079022132-1",
        "sha256": JVA_ZIP_SHA, "bytes": 45440,
        "execution_commit_sha": "8854bb2e63dc3961d98c5d8827f857ef85ccb341",
        "workflow_path": diagnostic.WORKFLOW_PATH, "conclusion": "success"},
}
NATIVE_ERRORS = {
    "invalid native byte bound": "native_wire_bound_failed",
    "native decompression ceiling exceeded": "native_decompression_ceiling",
    "unexpected native record type": "unexpected_native_record_type",
    "incomplete native stream": "incomplete_native_stream",
    "exact complete native metadata required": "native_metadata_mismatch",
    "exact symbol mapping required": "native_symbol_mapping_missing",
    "bounded native mapping required": "native_mapping_invalid",
    "complete session mapping required": "native_session_mapping_invalid",
    "native and normalized emptiness differ": "native_normalized_empty_mismatch",
    "native mapped row count differs": "native_normalized_count_mismatch",
}
SAFE_ERRORS = parent.SAFE_CAPTURE_ERRORS | frozenset(NATIVE_ERRORS.values())


def error_code(exc: Exception) -> str:
    return NATIVE_ERRORS.get(str(exc), parent.error_code(exc)) if type(exc) is ValueError else parent.error_code(exc)


FALSE_FLAGS = {k: False for k in ("acquisition_gate_passed", "runtime_input_eligible",
    "account_or_fill_simulation_executed", "backtesting_executed", "retrospective_inputs_loaded",
    "policy_changed", "consumed_parent_rerun", "raw_dbn_retained", "actual_billing_known")}


def contract() -> dict:
    return seal({"contract_id": CONTRACT_ID, "artifact_type": "registered_remaining_exact_input_acquisition",
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "hypothesis": "the_unattempted_suffix_can_be_classified_without_reacquiring_or_substituting_prior_inputs",
        "parent_artifacts": PARENT_ARTIFACTS, "frozen_file_sha256": FROZEN_FILES,
        "original_request_list_sha256": quote.REQUEST_LIST_SHA256, "request_list_sha256": REQUEST_LIST_SHA,
        "original_request_indices": list(range(25, 90)), "new_request_count": 65,
        "inherited_complete_indices": list(range(24)), "inherited_unavailable_index": 24,
        "inherited_jva_report_content_sha256": JVA_REPORT_SHA,
        "opportunity_count": 109, "original_date_count": 30, "original_symbol_date_count": 45,
        "maximum_billable_bytes": MAX_BILLABLE_BYTES, "maximum_quoted_cost_usd": MAX_COST_USD,
        "per_request_ceiling": "original_exact_quote_size_and_cost",
        "maximum_metadata_attempts": 130, "maximum_timeseries_attempts": 65, "maximum_http_attempts": 195,
        "wire_ceiling": "original_per_request_billable_bytes_plus_65536",
        "maximum_decompressed_native_bytes_per_request": MAX_NATIVE_BYTES,
        "maximum_retained_bytes": MAX_RETAINED_BYTES, "maximum_normalized_bytes": MAX_NORMALIZED_BYTES,
        "metadata_and_parent_archive_reserve_bytes": METADATA_RESERVE_BYTES,
        "normalizer": "unchanged_v02_lossless_record_order_adapter",
        "metadata_only_rule": "complete_native_stream_exact_metadata_valid_mapping_zero_native_and_normalized_records_is_unavailable_not_tape",
        "failure_rule": "stop_on_transport_truncation_metadata_mapping_normalization_or_write_failure_retain_partial_evidence",
        "continue_after": "only_complete_nonempty_tape_or_verified_metadata_only_unavailable_receipt",
        "raw_dbn_retention": "hash_then_delete_in_finally_never_artifact",
        "original_source_provider_request_total": 30522, "new_provider_ledger_is_separate": True,
        "consumption_ref": CONSUMPTION_REF, "immutable_refs": IMMUTABLE_REFS,
        "sdk_version": quote.SDK_VERSION, "python_version": "3.12.14",
        "requirements_path": quote.LOCK_PATH, "requirements_sha256": quote.LOCK_SHA256,
        "automatic_retry_count": 0, "redirects_allowed": False,
        "durable_consumption_before_provider_required": True,
        "source_windows_symbols_dates_and_policies_changed": False,
        **FALSE_FLAGS, "next_gate": NEXT_GATE})


def validate_requests(requests: list[dict]) -> None:
    if len(requests) != 65 or quote.canonical_fingerprint(requests) != REQUEST_LIST_SHA:
        raise ValueError("exact previously unattempted 65-request suffix required")


def validate_inputs(root: Path) -> tuple[list[dict], dict]:
    requests, quoted = parent.validate_inputs(root)
    diagnostic.validate_inputs(root)
    for name, sha in FROZEN_FILES.items():
        if file_sha(root/name) != sha: raise ValueError("immutable diagnostic bytes differ")
    validate_requests(requests[25:])
    if (sum(row["billable_size_bytes"] for row in quoted["quote_rows"][25:]) != MAX_BILLABLE_BYTES
        or sum((Decimal(row["quoted_cost_usd"]) for row in quoted["quote_rows"][25:]), Decimal(0)) != Decimal(MAX_COST_USD)):
        raise ValueError("original suffix quote ceilings differ")
    quote.require_exact(frozen(root/CONTRACT_PATH), contract(), "v0.3 registration")
    return requests[25:], quoted


def extract_exact_zip(path: Path, destination: Path, expected_sha: str) -> None:
    if path.is_symlink() or file_sha(path) != expected_sha: raise ValueError("exact parent ZIP differs")
    if destination.exists(): raise ValueError("new extraction directory required")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)): raise ValueError("duplicate archive member")
        for info in archive.infolist():
            name = PurePosixPath(info.filename)
            if (name.is_absolute() or ".." in name.parts or str(name) != info.filename
                or info.is_dir() or (info.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("unsafe archive member")
        archive.extractall(destination)


def verify_parents(evidence: Path, root: Path) -> dict:
    for name, spec in PARENT_ARTIFACTS.items():
        if (evidence/name).stat().st_size != spec["bytes"] or file_sha(evidence/name) != spec["sha256"]:
            raise ValueError("exact retained parent ZIP differs")
    diagnostic.verify_failure_zip(evidence/"parent-v02-result.zip", root)
    with tempfile.TemporaryDirectory(prefix="execution-v03-parent-check-") as temp:
        temp = Path(temp)
        extract_exact_zip(evidence/"parent-v02-result.zip", temp/"parent", diagnostic.FAILURE_ZIP_SHA)
        extract_exact_zip(evidence/"jva-empty-diagnostic.zip", temp/"jva", JVA_ZIP_SHA)
        inherited = parent.verify_capture(temp/"parent", root, require_success=False)
        empty = diagnostic.verify_result(temp/"jva", root)
    if (inherited["completed_request_count"] != 24 or inherited["normalized_row_count"] != 73614
        or empty["report_content_sha256"] != JVA_REPORT_SHA or empty["native_record_count"] != 0):
        raise ValueError("inherited complete and unavailable evidence differs")
    return seal({"parent_v02": inherited, "jva_diagnostic": empty,
        "original_source_provider_requests": 30522, "new_provider_calls": 0})


def execution_payload(*, code_commit: str, code_tree: str, workflow_sha256: str,
                      ci_run_id: str, validation_run_id: str) -> dict:
    quote.execution_payload(code_commit=code_commit, code_tree=code_tree, workflow_sha256=workflow_sha256,
        ci_run_id=ci_run_id, validation_run_id=validation_run_id)
    return seal({"execution_id": CONTRACT_ID+"-execution", "contract_content_sha256": contract()["content_sha256"],
        "code_commit_sha": code_commit, "code_tree_sha": code_tree, "workflow_file_sha256": workflow_sha256,
        "workflow_path": WORKFLOW_PATH, "code_ci_run_id": ci_run_id, "code_validation_run_id": validation_run_id,
        "repository": "RoomyRems/momentumbot", "branch": "phase-3-historical-snapshot", "event": "push", "run_attempt": 1,
        "consumption_ref": CONSUMPTION_REF, "request_list_sha256": REQUEST_LIST_SHA,
        "parent_artifacts": PARENT_ARTIFACTS, "maximum_http_attempts": 195,
        "maximum_billable_bytes": MAX_BILLABLE_BYTES, "maximum_quoted_cost_usd": MAX_COST_USD,
        "authority": "user_authorized_continued_development_and_operational_steps_2026-09-06",
        "remaining_exact_acquisition_authorized": True, "account_or_order_authority": False})


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


def collect_quote(requests: list[dict], metadata, progress=None) -> list[dict]:
    validate_requests(requests)
    calls = []
    for request in requests:
        for method in quote.METHODS:
            entry = {"ordinal": len(calls)+1, "request_id": request["request_id"],
                "request_content_sha256": quote.canonical_fingerprint(request), "method": method,
                "status": "pending", "value": None, "error": None}
            calls.append(entry)
            if progress: progress(seal({"calls": calls}))
            try:
                entry.update(status="success", value=quote._value(method, getattr(metadata, method)(**quote.request_kwargs(request))))
            except quote.MetadataFailure as exc:
                entry.update(status="error", error=exc.code)
            except Exception:
                entry.update(status="error", error="provider_error")
            if progress: progress(seal({"calls": calls}))
    return calls


def preflight(requests: list[dict], quoted: dict, calls: list[dict], http_attempts: int, blocked_attempts: int) -> dict:
    validate_requests(requests)
    if quoted["content_sha256"] != parent.parent.QUOTE_REPORT_CONTENT_SHA:
        raise ValueError("exact original quote required")
    quote.require_exact(quoted, seal({k:v for k,v in quoted.items() if k != "content_sha256"}), "quote seal")
    if (len(calls) > 130 or type(http_attempts) is not int or not 0 <= http_attempts <= len(calls)
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
        elif entry["status"] == "error" and entry["error"] not in quote.SAFE_ERRORS:
            raise ValueError("unsanitized metadata error")
    ready = len(calls) == http_attempts == 130 and blocked_attempts == 0 and all(c["status"] == "success" for c in calls)
    rows = []
    if ready:
        for i, request in enumerate(requests):
            size, cost = calls[2*i]["value"], calls[2*i+1]["value"]
            limit = quoted["quote_rows"][25+i]
            available = (0 < size <= limit["billable_size_bytes"] and Decimal(0) < Decimal(cost) <= Decimal(limit["quoted_cost_usd"]))
            rows.append({"request_id": request["request_id"], "billable_size_bytes": size, "quoted_cost_usd": cost,
                "within_original_ceiling": available})
        ready = all(r["within_original_ceiling"] for r in rows)
    size_total = sum(row["billable_size_bytes"] for row in rows) if rows else None
    cost_total = format(sum((Decimal(row["quoted_cost_usd"]) for row in rows), Decimal(0)), "f") if rows else None
    ready = ready and size_total <= MAX_BILLABLE_BYTES and Decimal(cost_total) <= Decimal(MAX_COST_USD)
    return seal({"contract_id": CONTRACT_ID, "request_list_sha256": REQUEST_LIST_SHA, "calls": calls,
        "http_attempts": http_attempts, "blocked_attempts": blocked_attempts, "quote_rows": rows,
        "total_billable_bytes": size_total, "total_quoted_cost_usd": cost_total, "preflight_passed": ready})


def native_summary(path: Path, request: dict, maximum_wire_bytes: int) -> dict:
    """Exhaust the complete native stream before interpreting mapped records."""
    import databento_dbn as dbn
    import zstandard
    if path.is_symlink() or not 0 < path.stat().st_size <= maximum_wire_bytes:
        raise ValueError("invalid native byte bound")
    wire = path.read_bytes()
    if wire[:4] == b"\x28\xb5\x2f\xfd":
        size = zstandard.frame_content_size(wire)
        if size not in (zstandard.CONTENTSIZE_UNKNOWN, zstandard.CONTENTSIZE_ERROR) and size > MAX_NATIVE_BYTES:
            raise ValueError("native decompression ceiling exceeded")
        raw = zstandard.ZstdDecompressor().decompress(wire, max_output_size=MAX_NATIVE_BYTES, allow_extra_data=False)
    else:
        raw = wire
    if len(raw) > MAX_NATIVE_BYTES: raise ValueError("native decompression ceiling exceeded")
    decoder = dbn.DBNDecoder(upgrade_policy=dbn.VersionUpgradePolicy.UPGRADE_TO_V3)
    metadata, count, digest = [], 0, hashlib.sha256()
    expected_type = dbn.MBP1Msg if request["schema"] == "mbp-1" else dbn.StatusMsg
    def accept(records):
        nonlocal count
        for row in records:
            if isinstance(row, dbn.Metadata): metadata.append(row)
            elif isinstance(row, expected_type): count += 1; digest.update(bytes(row))
            else: raise ValueError("unexpected native record type")
    for i in range(0, len(raw), 65536): accept(decoder.write_and_decode(raw[i:i+65536]))
    accept(decoder.decode())
    if decoder.buffer() or len(metadata) != 1: raise ValueError("incomplete native stream")
    m = metadata[0]
    if (_metadata_value(m, "dataset") != "xnas.itch" or _metadata_value(m, "schema") != request["schema"]
        or _metadata_value(m, "stype_in") != "raw-symbol" or _metadata_value(m, "stype_out") != "instrument-id"
        or list(_metadata_field(m, "symbols") or ()) != request["symbols"]
        or _metadata_timestamp_ns(m, "start") != request["start_ns"]
        or _metadata_timestamp_ns(m, "end") != request["end_ns"]
        or _metadata_field(m, "partial") or _metadata_field(m, "not_found")
        or _metadata_field(m, "limit") not in (None, 0) or _metadata_field(m, "ts_out") is not False):
        raise ValueError("exact complete native metadata required")
    mappings = _metadata_field(m, "mappings")
    symbol = request["symbols"][0]; day = date.fromisoformat(request["trading_date"])
    if not isinstance(mappings, dict) or set(mappings) != {symbol}: raise ValueError("exact symbol mapping required")
    intervals = []
    for row in mappings[symbol]:
        if (set(row) != {"start_date", "end_date", "symbol"} or type(row["start_date"]) is not date
            or type(row["end_date"]) is not date or not re.fullmatch("[0-9]{1,10}", str(row["symbol"]))):
            raise ValueError("bounded native mapping required")
        intervals.append({"start_date": row["start_date"].isoformat(), "end_date": row["end_date"].isoformat(),
            "instrument_id": int(row["symbol"])})
    if len(intervals) != 1 or not mappings[symbol][0]["start_date"] <= day < mappings[symbol][0]["end_date"]:
        raise ValueError("complete session mapping required")
    result = seal({"request_content_sha256": quote.canonical_fingerprint(request), "decoding_complete": True,
        "exact_metadata": True, "mapping_intervals": intervals, "native_record_count": count,
        "wire_bytes": len(wire), "wire_sha256": hashlib.sha256(wire).hexdigest(),
        "decompressed_bytes": len(raw), "decompressed_sha256": hashlib.sha256(raw).hexdigest(),
        "decoded_v3_record_bytes_sha256": digest.hexdigest()})
    validate_native_observation(result, request, maximum_wire_bytes)
    return result


def validate_native_observation(native: dict, request: dict, maximum: int) -> None:
    fields = {"request_content_sha256", "decoding_complete", "exact_metadata", "mapping_intervals",
        "native_record_count", "wire_bytes", "wire_sha256", "decompressed_bytes", "decompressed_sha256",
        "decoded_v3_record_bytes_sha256", "content_sha256"}
    if set(native) != fields: raise ValueError("native observation fields differ")
    quote.require_exact(native, seal({k:v for k,v in native.items() if k != "content_sha256"}), "native observation seal")
    if (native["request_content_sha256"] != quote.canonical_fingerprint(request)
        or native["decoding_complete"] is not True or native["exact_metadata"] is not True
        or type(native["native_record_count"]) is not int or native["native_record_count"] < 0
        or type(native["wire_bytes"]) is not int or not 0 < native["wire_bytes"] <= maximum
        or type(native["decompressed_bytes"]) is not int or not 0 < native["decompressed_bytes"] <= MAX_NATIVE_BYTES):
        raise ValueError("bounded native observation differs")
    for field in ("wire_sha256", "decompressed_sha256", "decoded_v3_record_bytes_sha256"):
        if not isinstance(native[field], str) or not re.fullmatch("[0-9a-f]{64}", native[field]):
            raise ValueError("native hash missing")
    intervals = native["mapping_intervals"]
    if not isinstance(intervals, list) or len(intervals) != 1: raise ValueError("complete mapping required")
    row = intervals[0]
    if (set(row) != {"start_date", "end_date", "instrument_id"} or type(row["instrument_id"]) is not int
        or not 0 < row["instrument_id"] <= 4294967295
        or not date.fromisoformat(row["start_date"]) <= date.fromisoformat(request["trading_date"]) < date.fromisoformat(row["end_date"])):
        raise ValueError("exact session mapping differs")


def tape_records(path: Path) -> tuple[list[dict], dict]:
    records, digest, count = [], hashlib.sha256(), 0
    with gzip.open(path, "rb") as stream:
        for line in stream:
            count += len(line)
            if count > MAX_NORMALIZED_BYTES: raise ValueError("normalized ceiling exceeded")
            value = json.loads(line)
            if line != (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode():
                raise ValueError("canonical normalized serialization required")
            records.append(value); digest.update(line)
    return records, {"row_count": len(records), "normalized_bytes": count, "normalized_sha256": digest.hexdigest(),
        "file_bytes": path.stat().st_size, "file_sha256": file_sha(path)}


def download_ledger(rows: list[dict]) -> dict:
    return seal({"requests": rows, "evidence_complete": len(rows) == 65 and all(r["status"] in {"complete", "unavailable"} for r in rows)})


def acquire_tapes(requests: list[dict], quoted: dict, requote: dict, *, client, output: Path,
                  temporary_root: Path, progress=None) -> list[dict]:
    validate_requests(requests)
    quote.require_exact(requote, preflight(requests, quoted, requote["calls"], requote["http_attempts"], requote["blocked_attempts"]), "complete suffix requote")
    if not requote["preflight_passed"]: raise ValueError("complete bounded requote required")
    rows, normalized, retained = [], 19983803, METADATA_RESERVE_BYTES
    for i, request in enumerate(requests):
        original = i+25; stem = f"request-{original:03d}"
        raw = temporary_root/f"request-{i:03d}.dbn.zst"
        tape, receipt = output/"tapes"/(stem+".jsonl.gz"), output/"receipts"/(stem+".json")
        tape.parent.mkdir(exist_ok=True); receipt.parent.mkdir(exist_ok=True)
        row = {"ordinal": i+1, "original_request_index": original, "request_id": request["request_id"],
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


def coverage(rows: list[dict], root: Path) -> list[dict]:
    requests = frozen(root/quote.PLAN_PATH/"request-manifest.json")["requests"]
    result = []
    for i, request in enumerate(requests):
        row = {"original_request_index": i, "request_id": request["request_id"],
            "request_content_sha256": quote.canonical_fingerprint(request)}
        if i < 24:
            row.update(status="inherited_complete", evidence="parent-v02-result.zip::receipts/"+f"request-{i:03d}.json")
        elif i == 24:
            row.update(status="inherited_unavailable", evidence="jva-empty-diagnostic.zip::diagnostic-report.json",
                runtime_input_eligible=False)
        elif i-25 < len(rows):
            item = rows[i-25]
            row.update(status=item["status"], evidence=("receipts/"+f"request-{i:03d}.json") if item["status"] != "failed" else "download-ledger.json")
            if item["status"] != "complete": row["runtime_input_eligible"] = False
        else: row.update(status="unattempted", evidence=None, runtime_input_eligible=False)
        result.append(row)
    return result


def build_report(rows: list[dict], metadata_http: dict, timeseries: dict, requote: dict | None,
                 provenance: dict, root: Path, error: str | None) -> dict:
    complete = (len(rows) == 65 and all(r["status"] in {"complete", "unavailable"} for r in rows)
        and metadata_http["http_attempts"] == 130 and timeseries["http_attempts"] == 65
        and metadata_http["blocked_attempts"] == timeseries["blocked_attempts"] == 0
        and requote is not None and requote["preflight_passed"] and error is None)
    return seal({"contract_id": CONTRACT_ID, "artifact_type": "historical_remaining_input_evidence_report",
        "provenance": provenance, "requests": rows, "coverage": coverage(rows, root),
        "inherited_complete_count": 24, "inherited_unavailable_count": 1,
        "new_complete_count": sum(r["status"] == "complete" for r in rows),
        "new_unavailable_count": sum(r["status"] == "unavailable" for r in rows),
        "unattempted_count": 65-len(rows), "new_normalized_row_count": sum(r["tape"]["row_count"] for r in rows if r["tape"]),
        "date_count": 30, "opportunity_count": 109, "symbol_date_count": 45,
        "metadata_http_attempts": metadata_http["http_attempts"], "timeseries_http_attempts": timeseries["http_attempts"],
        "http_attempts": metadata_http["http_attempts"]+timeseries["http_attempts"],
        "blocked_attempts": metadata_http["blocked_attempts"]+timeseries["blocked_attempts"],
        "request_evidence_complete": bool(complete), "requote": requote, "error": error,
        "original_source_provider_requests": 30522, "raw_temp_directory_removed": True,
        **FALSE_FLAGS, "next_gate": NEXT_GATE})


def write_inventory(output: Path, report: dict, *, replace=False) -> None:
    files = {p.relative_to(output).as_posix(): {"sha256": file_sha(p), "bytes": p.stat().st_size}
        for p in sorted(output.rglob("*")) if p.is_file() and p != output/"capture-inventory.json"}
    write_json(output/"capture-inventory.json", seal({"contract_id": CONTRACT_ID, "files": files,
        "provenance": report["provenance"], "request_evidence_complete": report["request_evidence_complete"],
        "acquisition_gate_passed": False}), replace=replace)


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
    expected = {"parent-v02-result.zip", "jva-empty-diagnostic.zip", "contract.json", "execution.json", "consumption.json",
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
    for ledger, ceiling, forbidden in ((metadata_http, 130, "non_metadata_calls"), (timeseries, 65, "unregistered_endpoint_calls")):
        if (ledger["http_attempts"] != len(ledger["attempts"]) or not 0 <= ledger["http_attempts"] <= ceiling
            or type(ledger["blocked_attempts"]) is not int or ledger["blocked_attempts"] < 0
            or any(ledger[k] != 0 for k in ("automatic_retries", "redirects_followed", forbidden))):
            raise ValueError("separate ledger boundary differs")
    calls = frozen(output/"metadata-ledger.json")["calls"]
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
    if len(rows) > 65 or len(timeseries["attempts"]) > len(rows): raise ValueError("download prefix differs")
    if rows and (requote is None or requote["preflight_passed"] is not True): raise ValueError("downloads preceded complete requote")
    normalized = 19983803; schema_rows = {"mbp-1": 0, "status": 0}
    for i, row in enumerate(rows):
        request = requests[i]; original = i+25; sha = quote.canonical_fingerprint(request)
        identity = {"ordinal": i+1, "original_request_index": original, "request_id": request["request_id"],
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
    rebuilt = build_report(rows, metadata_http, timeseries, requote, provenance, root, report["error"])
    quote.require_exact(report, rebuilt, "independent report reconstruction")
    quote.require_exact(inv, seal({"contract_id": CONTRACT_ID, "files": actual, "provenance": provenance,
        "request_evidence_complete": report["request_evidence_complete"], "acquisition_gate_passed": False}), "inventory boundaries")
    if require_complete and not report["request_evidence_complete"]: raise ValueError("request evidence incomplete")
    return seal({"verification_passed": True, "file_count": len(actual)+1, "parent_file_count": 79,
        "report_file_sha256": file_sha(output/"capture-report.json"), "report_content_sha256": report["content_sha256"],
        "inventory_content_sha256": inv["content_sha256"], "normalized_bytes_including_parent": normalized,
        "new_schema_row_counts": schema_rows, **{k:report[k] for k in ("request_evidence_complete", "new_complete_count",
            "new_unavailable_count", "unattempted_count", "http_attempts", "blocked_attempts", "acquisition_gate_passed")}})
