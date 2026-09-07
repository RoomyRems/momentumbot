"""Separate bounded historical acquisition using the frozen record-order adapter.

The original failed acquisition, diagnostic, transport, policies and inputs
remain immutable. This child has its own exact execution and consumption.
"""
from __future__ import annotations

import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re

from momentumbot.research import sealed_historical_execution_acquisition_v01 as parent
from momentumbot.research import sealed_historical_execution_diagnostic_v01 as diagnostic
from momentumbot.research import sealed_historical_execution_quote_v01 as quote
from momentumbot.research import sealed_historical_record_order_v01 as adapter
from momentumbot.research import sealed_historical_record_order_registration_v01 as registration

CONTRACT_ID = "sealed-historical-execution-input-acquisition-v0.2"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
EXECUTION_PATH = f"research/strategy/{CONTRACT_ID}-execution.json"
WORKFLOW_PATH = ".github/workflows/sealed-historical-execution-input-acquisition-v02.yml"
CONSUMPTION_REF = f"refs/tags/{CONTRACT_ID}-consumed"
PARENT_COMMIT = "45f24e880ef6cc1f3eadd490ca5aa59e5ee94c71"
PARENT_TREE = "8f0727234c6d9634b6a789da04a4b19445ae7f41"
ADAPTER_CONTRACT_SHA = "d66a2ff55dbba8497567ac3ffa0694272a30135b2e11710d683626e95291c0e9"
ADAPTER_REPORT_PATH = "research/data-audits/sealed-historical-record-order-adapter-v0.1-offline-verification-2026-09-07.json"
ADAPTER_REPORT_SHA = "0de8afbcad725c6d80f6ed9b6f6d9c54b62ec7b35d7dcc38dff24942919b8683"
MAX_BILLABLE_BYTES = parent.MAX_BILLABLE_BYTES
MAX_COST_USD = parent.MAX_COST_USD
MAX_RETAINED_BYTES = parent.MAX_RETAINED_BYTES
MAX_UNCOMPRESSED_NORMALIZED_BYTES = parent.MAX_UNCOMPRESSED_NORMALIZED_BYTES
NEXT_GATE = "independent_normalized_input_verification_then_provider_free_historical_capture_composition"
seal, write_json, file_sha, frozen = quote.seal, quote.write_json, quote.file_sha, quote.frozen
verify_quote_zip = parent.verify_quote_zip
FROZEN_FILES = {'.github/workflows/ci.yml': '4f8ecbfd548b86e4bb66e81d1716de0e01abdf72cd6aa9ecade24ce03c329784',
 '.github/workflows/sealed-historical-execution-input-acquisition-v01.yml': '5b0f85f776de813862e53cdf3335815a3a0b554e5f3aa375aecbec8f78750c02',
 '.github/workflows/sealed-historical-record-order-v01.yml': '698a0dffea091f7eb3a7954b28dfd0ea672aee23bc750e9c51f176f7fc86aa69',
 'research/data-audits/sealed-historical-record-order-adapter-v0.1-offline-verification-2026-09-07.json': 'ea6b8061ebd64aa316d3eeeea9e1f90185546b85d6c12c08d1556b266e493904',
 'research/data-audits/sealed-historical-record-order-adapter-v0.1-registration-2026-09-07.json': '9c7db1076337b4ee262740d54795e0987ae819821f6b15d64383ea3a56f3d418',
 'research/strategy/sealed-historical-execution-input-acquisition-v0.1-execution.json': 'c751ab5610f51332a7eb6745f30550dd5ed8b8cced4fb1ef09549df0ebfff5d1',
 'research/strategy/sealed-historical-execution-input-diagnostic-v0.1-execution.json': '637fc1f5e79d4299c19359568796017393a7f5be771524cc5f9c43245c3a2aad',
 'research/strategy/sealed-historical-record-order-adapter-v0.1.json': '06587aa36944e7ebc5b39ae8bc278cb39f287900755257b7c9a460b17b497797',
 'scripts/acquire_sealed_historical_execution_inputs_v01.py': 'ec4ccb7b73065717be85e4d0af9cbbfc4d704872555b3d167c87c55b2a784841',
 'src/momentumbot/research/sealed_historical_execution_acquisition_v01.py': 'ca57499aee9c5ebd7b53230c04574257cfef9b0586859e1c7ecd529871638f05',
 'src/momentumbot/research/sealed_historical_execution_transport_v01.py': '3df2150f8970d1a6199cdf2bfcd5bcdfc35970e4257c90b54b8754218bdd91a3',
 'src/momentumbot/research/sealed_historical_metadata_transport_v01.py': '0d3665043c805d661ecc2bd76e646ccfbb068d7f5e3e0d56419b4155a2fe893d',
 'src/momentumbot/research/sealed_historical_record_order_registration_v01.py': '4fed4b93ee0bd5fbe2767134b5b007a2e18ed151f1b3d9617241103630fee4da',
 'src/momentumbot/research/sealed_historical_record_order_v01.py': '407e02fc6fe908e26715fac2799f0debf356e96336b640e795b50287762dec6b'}
IMMUTABLE_REFS = {
    "heads/main": "de24eb17316191da69d92e61f6843af25e9c22d0",
    "tags/sealed-historical-execution-input-quote-v0.1-consumed": "dd295304dcc5e7cc0ebd300d094ab20636a72b92",
    "tags/sealed-historical-execution-input-acquisition-v0.1-consumed": "5a375f86e951b1e9eeb6c010995c9b57025913b7",
    "tags/sealed-historical-execution-input-diagnostic-v0.1-consumed": "e1aece08a44ccf9add0157a1657d08a809687e85",
    "tags/sealed-historical-micro-input-acquisition-v0.1-consumed": "5cab2eb3aa2b73a2cbf1d57575519a7b99961e24",
    "tags/sealed-historical-micro-session-input-acquisition-v0.2-consumed": "bf5863a7115abef9e22c4f527448cd9c20084f47",
}


def contract() -> dict:
    previous = {k: v for k, v in parent.contract().items() if k != "content_sha256"}
    previous.update({
        "contract_id": CONTRACT_ID,
        "artifact_type": "registered_record_order_repair_historical_input_acquisition",
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "consumption_ref": CONSUMPTION_REF,
        "normalization": "frozen_record_order_adapter_v01_preserve_native_fields_and_original_per_request_ordinal",
        "adapter_contract_content_sha256": ADAPTER_CONTRACT_SHA,
        "adapter_offline_report_content_sha256": ADAPTER_REPORT_SHA,
        "adapter_code_ci_run_id": 34073929422,
        "adapter_code_validation_run_id": 34073929465,
        "failed_parent_run_id": diagnostic.FAILURE_RUN_ID,
        "failed_parent_artifact_id": diagnostic.FAILURE_ARTIFACT_ID,
        "failed_parent_zip_sha256": diagnostic.FAILURE_ZIP_SHA,
        "diagnostic_run_id": 34069896968,
        "diagnostic_result_artifact_id": 10000122082,
        "diagnostic_result_zip_sha256": registration.RESULT_ZIP_SHA,
        "frozen_parent_file_sha256": FROZEN_FILES,
        "immutable_refs": IMMUTABLE_REFS,
        "partial_evidence": "retain_bounded_partial_normalized_bytes_and_receipt_prefix_as_ineligible_evidence_and_stop",
        "failure_diagnostics": "fixed_error_codes_only_no_provider_exception_text_or_raw_response_values",
        "diagnostic_fixture_may_substitute_for_provider_inputs": False,
        "first_request_native_content_sha256": registration.NORMALIZED_SHA,
        "original_source_provider_request_total": 30522,
        "new_provider_ledger": "separate_metadata_and_timeseries_ledgers_maximum_270_attempts",
        "next_gate": NEXT_GATE,
    })
    return seal(previous)


def validate_inputs(root: Path) -> tuple[list[dict], dict]:
    requests, quoted = parent.validate_inputs(root)
    report = registration.verify_diagnostic_adapter(root)
    quote.require_exact(report, frozen(root / ADAPTER_REPORT_PATH), "verified adapter regression")
    if report["content_sha256"] != ADAPTER_REPORT_SHA or registration.contract()["content_sha256"] != ADAPTER_CONTRACT_SHA:
        raise ValueError("exact record-order adapter prerequisite differs")
    for path, sha in FROZEN_FILES.items():
        if file_sha(root / path) != sha:
            raise ValueError("immutable parent bytes differ")
    quote.require_exact(frozen(root / CONTRACT_PATH), contract(), "v0.2 acquisition registration")
    return requests, quoted


def environment(root: Path) -> dict:
    if platform.python_implementation() != "CPython" or platform.python_version() != "3.12.14":
        raise ValueError("exact CPython 3.12.14 required")
    raw = (root / quote.LOCK_PATH).read_bytes()
    if hashlib.sha256(raw).hexdigest() != quote.LOCK_SHA256:
        raise ValueError("exact hash-locked requirements required")
    pins = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", raw.decode(), re.M))
    if len(pins) != 29:
        raise ValueError("exact 29 dependency pins required")
    observed = {name: importlib.metadata.version(name) for name in pins}
    if observed != pins:
        raise ValueError("installed package versions differ from lock")
    return seal({"implementation": "CPython", "python_version": "3.12.14",
                 "requirements_sha256": quote.LOCK_SHA256, "package_versions": observed})


def execution_payload(*, code_commit: str, code_tree: str, workflow_sha256: str,
                      ci_run_id: str, validation_run_id: str) -> dict:
    value = parent.execution_payload(code_commit=code_commit, code_tree=code_tree,
        workflow_sha256=workflow_sha256, ci_run_id=ci_run_id, validation_run_id=validation_run_id)
    value = {k: v for k, v in value.items() if k != "content_sha256"}
    value.update({"execution_id": CONTRACT_ID + "-execution", "contract_content_sha256": contract()["content_sha256"],
        "workflow_path": WORKFLOW_PATH, "consumption_ref": CONSUMPTION_REF,
        "adapter_parent_commit_sha": PARENT_COMMIT, "adapter_parent_tree_sha": PARENT_TREE,
        "adapter_contract_content_sha256": ADAPTER_CONTRACT_SHA,
        "request_list_content_sha256": quote.REQUEST_LIST_SHA256})
    return seal(value)


def validate_execution(root: Path, env: dict) -> dict:
    value = frozen(root / EXECUTION_PATH)
    expected = execution_payload(code_commit=env.get("EXECUTION_CODE_COMMIT_SHA", ""),
        code_tree=env.get("EXECUTION_CODE_TREE_SHA", ""), workflow_sha256=file_sha(root / WORKFLOW_PATH),
        ci_run_id=value["code_ci_run_id"], validation_run_id=value["code_validation_run_id"])
    quote.require_exact(value, expected, "v0.2 sole execution child")
    for key, item in {"GITHUB_REPOSITORY": "RoomyRems/momentumbot", "GITHUB_EVENT_NAME": "push",
                      "GITHUB_REF": "refs/heads/phase-3-historical-snapshot", "GITHUB_RUN_ATTEMPT": "1"}.items():
        if env.get(key) != item:
            raise ValueError("v0.2 requires exact first research push")
    if not re.fullmatch("[0-9a-f]{40}", env.get("GITHUB_SHA", "")) or not re.fullmatch("[1-9][0-9]+", env.get("GITHUB_RUN_ID", "")):
        raise ValueError("exact v0.2 execution provenance required")
    return value


def consumption(execution: dict, env: dict) -> dict:
    return seal({"execution_content_sha256": execution["content_sha256"], "consumption_ref": CONSUMPTION_REF,
        "execution_commit_sha": env["GITHUB_SHA"], "workflow_run_id": env["GITHUB_RUN_ID"], "workflow_run_attempt": 1,
        "quote_zip_sha256": parent.QUOTE_ZIP_SHA, "quote_report_content_sha256": parent.QUOTE_REPORT_CONTENT_SHA,
        "adapter_contract_content_sha256": ADAPTER_CONTRACT_SHA,
        "request_list_content_sha256": quote.REQUEST_LIST_SHA256})


def preflight(requests: list[dict], calls: list[dict], *, provenance: dict,
              http_attempts: int, blocked_attempts: int) -> dict:
    value = parent.preflight(requests, calls, provenance=provenance,
                            http_attempts=http_attempts, blocked_attempts=blocked_attempts)
    return seal({**{k: v for k, v in value.items() if k != "content_sha256"}, "contract_id": CONTRACT_ID})


normalize = adapter.normalize_store
ERROR_CODES = {
    **diagnostic.ERROR_CODES,
    "native receive-time/sequence order reversed": "native_key_order_reversed",
    "record source request or symbol differs": "record_source_identity_mismatch",
    "source record order reversed or duplicated": "source_ordinal_order_invalid",
    "complete tape ordinals must be contiguous from zero": "source_ordinal_gap",
    "quote outside exact request": "quote_outside_exact_request",
    "status outside exact request or symbol": "status_outside_exact_request",
    "status.action must be a registered Databento status action": "status_action_outside_frozen_vocabulary",
    "status.is_trading must be Y, N, or ~": "status_trading_flag_outside_frozen_vocabulary",
    "status records must remain in receive-time order": "status_receive_time_order_reversed",
    "missing exact request records": "empty_exact_request",
    "first request differs from verified diagnostic native rows": "diagnostic_native_rows_differ",
}
SAFE_CAPTURE_ERRORS = frozenset(ERROR_CODES.values()) | {
    "normalized_byte_ceiling", "retained_byte_ceiling", "missing_ephemeral_dbn",
    "unclassified_validation_exception", "capture_stage_failed",
} | quote.SAFE_ERRORS


class CaptureFailure(Exception):
    def __init__(self, code: str):
        self.code = code if code in SAFE_CAPTURE_ERRORS else "capture_stage_failed"
        super().__init__(self.code)


def error_code(exc: Exception) -> str:
    if isinstance(exc, (CaptureFailure, quote.MetadataFailure)):
        return exc.code
    if type(exc) is ValueError:
        return ERROR_CODES.get(str(exc), "unclassified_validation_exception")
    return "capture_stage_failed"


class _BoundedStream:
    def __init__(self, stream, maximum: int):
        self.stream, self.maximum, self.written = stream, maximum, 0

    def write(self, data: bytes) -> int:
        if self.written + len(data) > self.maximum:
            raise CaptureFailure("retained_byte_ceiling")
        size = self.stream.write(data)
        self.written += size
        return size

    def flush(self) -> None:
        self.stream.flush()


def write_tape(path: Path, records: list[dict], *, maximum_file_bytes: int = MAX_RETAINED_BYTES,
               maximum_normalized_bytes: int = MAX_UNCOMPRESSED_NORMALIZED_BYTES) -> dict:
    digest = hashlib.sha256()
    count = byte_count = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        with gzip.GzipFile(filename="", mode="wb", fileobj=_BoundedStream(stream, maximum_file_bytes), mtime=0) as zipped:
            for record in records:
                raw = (json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
                if byte_count + len(raw) > maximum_normalized_bytes:
                    raise CaptureFailure("normalized_byte_ceiling")
                zipped.write(raw)
                byte_count += len(raw)
                digest.update(raw)
                count += 1
    return {"row_count": count, "normalized_bytes": byte_count, "normalized_sha256": digest.hexdigest(),
            "file_bytes": path.stat().st_size, "file_sha256": file_sha(path)}


def normalization_summary(records: list[dict], request: dict) -> dict:
    if request["schema"] == "mbp-1":
        events = adapter.quote_events(records, request)
        tied = sum((a.ts_recv_ns, a.sequence) == (b.ts_recv_ns, b.sequence)
                   for a, b in zip(events, events[1:]))
    else:
        events = adapter.status_events(records, request)
        tied = 0
    return {"row_count": len(events), "native_key_adjacent_ties": tied,
            "record_order_adapter_contract_sha256": ADAPTER_CONTRACT_SHA}


def acquire_tapes(requests: list[dict], preflight_result: dict, *, client, output: Path,
                  temporary_root: Path, progress=None) -> list[dict]:
    quote.validate_requests(requests)
    expected = preflight(requests, preflight_result["metadata_result"]["calls"],
        provenance=preflight_result["metadata_result"]["provenance"],
        http_attempts=preflight_result["metadata_result"]["http_attempts"],
        blocked_attempts=preflight_result["metadata_result"]["blocked_attempts"])
    quote.require_exact(preflight_result, expected, "complete v0.2 preflight")
    if preflight_result["preflight_passed"] is not True:
        raise ValueError("quote or byte/cost ceiling blocks every download")
    rows = []
    retained = normalized = 0
    for index, request in enumerate(requests):
        raw_path = temporary_root / f"request-{index:03d}.dbn.zst"
        tape = output / "tapes" / f"request-{index:03d}.jsonl.gz"
        receipt_path = output / "receipts" / f"request-{index:03d}.json"
        row = {"ordinal": index + 1, "request_id": request["request_id"],
               "request_content_sha256": quote.canonical_fingerprint(request), "schema": request["schema"],
               "status": "pending", "error": None, "failure_stage": None,
               "tape": None, "partial_tape": None, "partial_receipt": None,
               "ephemeral_dbn_sha256": None, "normalization": None}
        rows.append(row)
        if progress: progress(seal({"requests": rows, "complete": False}))
        stage = "timeseries_request"
        try:
            store = client.get_range(path=str(raw_path), **quote.request_kwargs(request))
            stage = "ephemeral_dbn_validation"
            if not raw_path.is_file() or raw_path.stat().st_size == 0:
                raise CaptureFailure("missing_ephemeral_dbn")
            row["ephemeral_dbn_sha256"] = file_sha(raw_path)
            stage = "normalization"
            records = normalize(store, request)
            if index == 0:
                native = [{k: row[k] for k in adapter.QUOTE_FIELDS} for row in records]
                if quote.canonical_fingerprint(native) != registration.NORMALIZED_SHA:
                    raise ValueError("first request differs from verified diagnostic native rows")
            row["normalization"] = normalization_summary(records, request)
            stage = "normalized_tape_write"
            tape_result = write_tape(tape, records, maximum_file_bytes=MAX_RETAINED_BYTES - retained,
                                     maximum_normalized_bytes=MAX_UNCOMPRESSED_NORMALIZED_BYTES - normalized)
            retained += tape_result["file_bytes"]
            normalized += tape_result["normalized_bytes"]
            row.update(status="complete", tape={"path": tape.relative_to(output).as_posix(), **tape_result})
            stage = "completion_receipt_write"
            write_json(receipt_path, seal({
                "contract_id": CONTRACT_ID, "request": request, "completion": row,
                "metadata_verified": True, "raw_dbn_persisted": False,
                "record_order_adapter_contract_sha256": ADAPTER_CONTRACT_SHA}))
        except Exception as exc:
            row.update(status="failed", error=error_code(exc), failure_stage=stage)
            if tape.exists():
                partial = output / "partial_tapes" / f"request-{index:03d}.jsonl.gz.partial"
                partial.parent.mkdir(parents=True, exist_ok=True)
                tape.rename(partial)
                row["partial_tape"] = {"path": partial.relative_to(output).as_posix(),
                    "file_bytes": partial.stat().st_size, "file_sha256": file_sha(partial),
                    "runtime_input_eligible": False, "may_be_incomplete_gzip": True}
            if receipt_path.exists():
                partial = output / "partial_receipts" / f"request-{index:03d}.json.partial"
                partial.parent.mkdir(parents=True, exist_ok=True)
                receipt_path.rename(partial)
                row["partial_receipt"] = {"path": partial.relative_to(output).as_posix(),
                    "file_bytes": partial.stat().st_size, "file_sha256": file_sha(partial),
                    "runtime_input_eligible": False}
            row["tape"] = None
        finally:
            raw_path.unlink(missing_ok=True)
            if progress: progress(seal({"requests": rows, "complete": len(rows) == 90 and all(r["status"] == "complete" for r in rows)}))
        if row["status"] != "complete":
            break
    return rows


CAPTURE_METADATA = frozenset({
    "consumption.json", "execution.json", "contract.json", "request-manifest.json",
    "parent-quote-report.json", "adapter-verification.json", "environment.json",
    "metadata-http-ledger.json", "metadata-ledger.json", "requote-report.json",
    "timeseries-http-ledger.json", "download-ledger.json", "capture-report.json", "capture-inventory.json",
})


def verify_capture(output: Path, root: Path, *, require_success: bool = True) -> dict:
    """Recompute every retained byte, tape row, receipt, request and ledger."""
    requests, quoted = validate_inputs(root)
    report = frozen(output / "capture-report.json")
    inventory = frozen(output / "capture-inventory.json")
    actual = {}
    for path in sorted(output.rglob("*")):
        if path.is_symlink(): raise ValueError("capture cannot contain symlinks")
        if path.is_file():
            name = path.relative_to(output).as_posix()
            if name != "capture-inventory.json":
                actual[name] = {"sha256": file_sha(path), "bytes": path.stat().st_size}
    quote.require_exact(inventory["files"], actual, "complete capture inventory")
    if inventory["contract_id"] != CONTRACT_ID or report["contract_id"] != CONTRACT_ID:
        raise ValueError("v0.2 report identity differs")
    if inventory["acquisition_gate_passed"] is not report["acquisition_gate_passed"]:
        raise ValueError("inventory acquisition gate differs")
    for captured, source in (("contract.json", CONTRACT_PATH), ("execution.json", EXECUTION_PATH),
        ("request-manifest.json", quote.PLAN_PATH + "/request-manifest.json"),
        ("parent-quote-report.json", parent.QUOTE_REPORT_PATH), ("adapter-verification.json", ADAPTER_REPORT_PATH)):
        if (output / captured).read_bytes() != (root / source).read_bytes():
            raise ValueError("capture frozen input bytes differ")
    execution = frozen(output / "execution.json")
    marker = frozen(output / "consumption.json")
    provenance = report["provenance"]
    expected_execution = execution_payload(code_commit=execution["code_commit_sha"], code_tree=execution["code_tree_sha"],
        workflow_sha256=file_sha(root / WORKFLOW_PATH), ci_run_id=execution["code_ci_run_id"],
        validation_run_id=execution["code_validation_run_id"])
    quote.require_exact(execution, expected_execution, "capture execution")
    expected_marker = consumption(execution, {"GITHUB_SHA": provenance["execution_commit_sha"],
        "GITHUB_RUN_ID": provenance["workflow_run_id"]})
    quote.require_exact(marker, expected_marker, "capture consumption")
    expected_provenance = {"execution_commit_sha": marker["execution_commit_sha"],
        "workflow_run_id": marker["workflow_run_id"], "workflow_run_attempt": 1,
        "code_commit_sha": execution["code_commit_sha"], "code_tree_sha": execution["code_tree_sha"],
        "execution_content_sha256": execution["content_sha256"], "consumption_content_sha256": marker["content_sha256"]}
    quote.require_exact(provenance, expected_provenance, "capture provenance")
    quote.require_exact(inventory["provenance"], provenance, "inventory provenance")
    observed_environment = frozen(output / "environment.json")
    pins = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", (root / quote.LOCK_PATH).read_text(), re.M))
    quote.require_exact(observed_environment, seal({"implementation": "CPython", "python_version": "3.12.14",
        "requirements_sha256": quote.LOCK_SHA256, "package_versions": pins}), "capture pinned environment")

    requote = frozen(output / "requote-report.json") if (output / "requote-report.json").exists() else None
    metadata_http = frozen(output / "metadata-http-ledger.json") if (output / "metadata-http-ledger.json").exists() else None
    metadata = frozen(output / "metadata-ledger.json") if (output / "metadata-ledger.json").exists() else None
    timeseries = frozen(output / "timeseries-http-ledger.json") if (output / "timeseries-http-ledger.json").exists() else None
    downloads = frozen(output / "download-ledger.json") if (output / "download-ledger.json").exists() else None
    quote.require_exact(report["requote"], requote, "report requote")
    for ledger, forbidden in ((metadata_http, "non_metadata_calls"), (timeseries, "unregistered_endpoint_calls")):
        if ledger is not None:
            if ledger["http_attempts"] != len(ledger["attempts"]) or any(ledger.get(k) != 0 for k in
                ("automatic_retries", "redirects_followed", forbidden)):
                raise ValueError("HTTP ledger authority or accounting differs")
    if requote is not None:
        if metadata is None or metadata_http is None:
            raise ValueError("requote supporting ledgers missing")
        expected = preflight(requests, metadata["calls"], provenance=provenance,
            http_attempts=metadata_http["http_attempts"], blocked_attempts=metadata_http["blocked_attempts"])
        quote.require_exact(requote, expected, "requote reconstructed from ledgers")
        if metadata["call_count"] != len(metadata["calls"]) or metadata["complete"] is not True:
            raise ValueError("logical metadata ledger incomplete")
        for i, attempt in enumerate(metadata_http["attempts"]):
            if attempt["ordinal"] != i+1 or attempt["request_id"] != requests[i//2]["request_id"]:
                raise ValueError("metadata attempt identity differs")
            if attempt["method"] != quote.METHODS[i % 2]:
                raise ValueError("metadata method differs")
            if requote["preflight_passed"] and (attempt["status"] != "success" or attempt["http_status"] != 200):
                raise ValueError("successful requote lacks successful HTTP evidence")
    rows = report["requests"]
    if downloads is not None:
        quote.require_exact(downloads["requests"], rows, "durable download ledger")
        if downloads["complete"] is not (len(rows) == 90 and all(row["status"] == "complete" for row in rows)):
            raise ValueError("download ledger completeness differs")
    elif rows:
        raise ValueError("download ledger missing")
    attempts = timeseries["attempts"] if timeseries else []
    if len(rows) > 90 or len(attempts) > len(rows):
        raise ValueError("download attempt ceiling or prefix differs")
    expected_names = set(CAPTURE_METADATA) & (set(actual) | {"capture-inventory.json"})
    retained = normalized_bytes = total_rows = completed = ties = 0
    schema_rows = {"mbp-1": 0, "status": 0}
    for i, row in enumerate(rows):
        if set(row) != {"ordinal", "request_id", "request_content_sha256", "schema", "status", "error",
                "failure_stage", "tape", "partial_tape", "partial_receipt", "ephemeral_dbn_sha256", "normalization"}:
            raise ValueError("download row schema differs")
        request = requests[i]
        if (row["ordinal"] != i+1 or row["request_id"] != request["request_id"]
                or row["schema"] != request["schema"]
                or row["request_content_sha256"] != quote.canonical_fingerprint(request)):
            raise ValueError("download request prefix differs")
        if i < len(attempts):
            attempt = attempts[i]
            if any(attempt[k] != row[k] for k in ("ordinal", "request_id", "request_content_sha256")):
                raise ValueError("time-series attempt differs from request")
            if attempt["method"] != "timeseries.get_range" or attempt["maximum_wire_bytes"] != quoted["quote_rows"][i]["billable_size_bytes"] + 65536:
                raise ValueError("time-series method or wire ceiling differs")
            if row["status"] == "complete" and (attempt["status"] != "complete" or attempt["http_status"] != 200
                    or not 0 < attempt["wire_bytes"] <= attempt["maximum_wire_bytes"]):
                raise ValueError("completed tape lacks completed bounded HTTP request")
        elif row["status"] == "complete":
            raise ValueError("completed tape has no provider attempt")
        if row["status"] == "failed":
            if i != len(rows)-1 or row["error"] not in SAFE_CAPTURE_ERRORS or row["tape"] is not None:
                raise ValueError("failure must stop the exact request prefix")
            partial = row["partial_tape"]
            if partial is not None:
                name = f"partial_tapes/request-{i:03d}.jsonl.gz.partial"
                if (set(partial) != {"path", "file_bytes", "file_sha256", "runtime_input_eligible", "may_be_incomplete_gzip"}
                        or partial["path"] != name or partial["runtime_input_eligible"] is not False
                        or partial["may_be_incomplete_gzip"] is not True):
                    raise ValueError("partial tape must remain ineligible")
                if actual.get(name) != {"sha256": partial["file_sha256"], "bytes": partial["file_bytes"]}:
                    raise ValueError("partial tape bytes differ")
                retained += partial["file_bytes"]
                expected_names.add(name)
            partial_receipt = row["partial_receipt"]
            if partial_receipt is not None:
                name = f"partial_receipts/request-{i:03d}.json.partial"
                if (set(partial_receipt) != {"path", "file_bytes", "file_sha256", "runtime_input_eligible"}
                        or row["failure_stage"] != "completion_receipt_write" or partial_receipt["path"] != name
                        or partial_receipt["runtime_input_eligible"] is not False
                        or actual.get(name) != {"sha256": partial_receipt["file_sha256"], "bytes": partial_receipt["file_bytes"]}):
                    raise ValueError("partial receipt provenance or bytes differ")
                expected_names.add(name)
            continue
        if (row["status"] != "complete" or row["error"] is not None or row["failure_stage"] is not None
                or row["partial_tape"] is not None or row["partial_receipt"] is not None):
            raise ValueError("invalid terminal request status")
        if not re.fullmatch("[0-9a-f]{64}", row["ephemeral_dbn_sha256"] or ""):
            raise ValueError("completed request lacks ephemeral DBN hash")
        name = f"tapes/request-{i:03d}.jsonl.gz"
        receipt_name = f"receipts/request-{i:03d}.json"
        tape = row["tape"]
        if tape["path"] != name or actual.get(name) != {"sha256": tape["file_sha256"], "bytes": tape["file_bytes"]}:
            raise ValueError("normalized tape file hash differs")
        records, digest, byte_count = [], hashlib.sha256(), 0
        with gzip.open(output / name, "rb") as stream:
            for line in stream:
                byte_count += len(line)
                if byte_count + normalized_bytes > MAX_UNCOMPRESSED_NORMALIZED_BYTES:
                    raise ValueError("decompressed aggregate exceeds ceiling")
                value = json.loads(line)
                canonical = (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
                if line != canonical: raise ValueError("normalized row serialization differs")
                digest.update(line); records.append(value)
        summary = normalization_summary(records, request)
        quote.require_exact(summary, row["normalization"], "all tape row semantics")
        if tape["row_count"] != len(records) or tape["normalized_bytes"] != byte_count or tape["normalized_sha256"] != digest.hexdigest():
            raise ValueError("full decompressed tape commitment differs")
        if i == 0 and quote.canonical_fingerprint([{k: value[k] for k in adapter.QUOTE_FIELDS} for value in records]) != registration.NORMALIZED_SHA:
            raise ValueError("first request differs from verified diagnostic native rows")
        receipt = frozen(output / receipt_name)
        quote.require_exact(receipt, seal({"contract_id": CONTRACT_ID, "request": request, "completion": row,
            "metadata_verified": True, "raw_dbn_persisted": False,
            "record_order_adapter_contract_sha256": ADAPTER_CONTRACT_SHA}), "complete request receipt")
        retained += tape["file_bytes"]; normalized_bytes += byte_count; total_rows += len(records)
        schema_rows[request["schema"]] += len(records)
        ties += summary["native_key_adjacent_ties"]; completed += 1
        expected_names.update((name, receipt_name))
    if set(actual) | {"capture-inventory.json"} != expected_names:
        raise ValueError("unexpected or missing retained capture member")
    if retained > MAX_RETAINED_BYTES:
        raise ValueError("retained normalized bytes exceed ceiling")
    counts = {"completed_request_count": completed, "normalized_row_count": total_rows,
        "metadata_http_attempts": metadata_http["http_attempts"] if metadata_http else 0,
        "timeseries_http_attempts": len(attempts),
        "blocked_attempts": sum(value["blocked_attempts"] for value in (metadata_http, timeseries) if value)}
    counts["http_attempts"] = counts["metadata_http_attempts"] + counts["timeseries_http_attempts"]
    for key, expected in counts.items():
        if report[key] != expected: raise ValueError("capture report count differs: " + key)
    if counts["http_attempts"] > 270: raise ValueError("aggregate HTTP attempt ceiling exceeded")
    expected_flags = {"request_count": 90, "date_count": 30, "opportunity_count": 109, "symbol_date_count": 45,
        "raw_dbn_retained": False, "raw_temp_directory_removed": True, "account_or_fill_simulation_executed": False,
        "backtesting_executed": False, "retrospective_inputs_loaded": False, "policy_changed": False,
        "automatic_retry_attempted": False, "quote_or_prior_acquisition_rerun": False, "actual_billing_known": False,
        "parent_quote_report_content_sha256": parent.QUOTE_REPORT_CONTENT_SHA,
        "adapter_contract_content_sha256": ADAPTER_CONTRACT_SHA, "next_gate": NEXT_GATE}
    quote.require_exact({k: report[k] for k in expected_flags}, expected_flags, "capture boundaries")
    fields = set(expected_flags) | set(counts) | {"contract_id", "artifact_type", "provenance", "requests",
        "requote", "error", "acquisition_gate_passed", "content_sha256"}
    if set(report) != fields or report["artifact_type"] != "historical_record_order_input_acquisition_report":
        raise ValueError("capture report schema differs")
    passed = (completed == 90 and len(rows) == len(attempts) == 90 and counts["http_attempts"] == 270
        and counts["blocked_attempts"] == 0 and requote is not None and requote["preflight_passed"] is True
        and report["error"] is None and set(actual) | {"capture-inventory.json"} ==
        set(CAPTURE_METADATA) | {f"{kind}/request-{i:03d}.{suffix}" for i in range(90)
                               for kind, suffix in (("tapes", "jsonl.gz"), ("receipts", "json"))})
    if report["acquisition_gate_passed"] is not passed or (require_success and not passed):
        raise ValueError("complete v0.2 acquisition gate did not pass")
    return seal({"contract_id": CONTRACT_ID, "verification_passed": True, "acquisition_gate_passed": passed,
        "capture_report_file_sha256": file_sha(output / "capture-report.json"),
        "capture_report_content_sha256": report["content_sha256"], "inventory_content_sha256": inventory["content_sha256"],
        "file_count": len(actual) + 1, "completed_request_count": completed, "normalized_row_count": total_rows,
        "schema_row_counts": schema_rows, "native_key_adjacent_ties": ties,
        "retained_tape_bytes": retained, "normalized_bytes": normalized_bytes, **counts,
        "date_count": 30, "opportunity_count": 109, "symbol_date_count": 45,
        "account_or_fill_simulation_executed": False, "next_gate": NEXT_GATE})
