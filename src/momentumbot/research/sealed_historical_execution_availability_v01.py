"""Provider-free availability and quote windows for every frozen opportunity.

This child consumes only the independently verified v0.3 artifact chain. It
does not acquire data, simulate an order, infer a missing quote, or open labels.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import gzip
import io
import json
from pathlib import Path
import tempfile

from momentumbot.research import sealed_historical_execution_acquisition_v03 as acquisition
from momentumbot.research import sealed_historical_execution_inputs_v01 as plan
from momentumbot.research import sealed_historical_record_order_v01 as adapter
from momentumbot.research.prospective_daily_account_runtime import _decision_quote
from momentumbot.research.sealed_historical_execution_quote_v01 import (
    PLAN_PATH, REQUEST_LIST_SHA256, canonical_fingerprint, file_sha, frozen,
    require_exact, seal,
)

CONTRACT_ID = "sealed-historical-execution-input-availability-v0.1"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
OUTPUT_PATH = "research/runtime/sealed-historical-execution-availability-v0.1"
MODULE_PATH = "src/momentumbot/research/sealed_historical_execution_availability_v01.py"
SCRIPT_PATH = "scripts/compose_sealed_historical_execution_availability_v01.py"
WORKFLOW_PATH = ".github/workflows/sealed-historical-execution-availability-v01.yml"
AUDIT_PATH = "research/data-audits/sealed-historical-execution-input-acquisition-v0.3-independent-verification-34084113393.json"
PARENT_COMMIT = "24aaa19c50a39bce43ef9491f7630e2a81e330f8"
PARENT_TREE = "fe4e82282cf50eeb855937f27a6222e80fd2aec6"
JVA_REQUEST = "2025-06-13-JVA-mbp-1"
JVA_OPPORTUNITY = "opportunity-584abfa60e5a82b205ac89afb352068295e49e833f930caf9d60018d1e1b694a"
ARTIFACTS = {
    "result": {"run_id": 34084113393, "artifact_id": 10004782232,
        "bytes": 13700990, "file_count": 144,
        "sha256": "1fe68f4e526caa6ce0ee8f8845248e5ef3039f3e3ffbce370020162add3b99d6"},
    "consumption": {"run_id": 34084113393, "artifact_id": 10004656665,
        "bytes": 1137522, "file_count": 17,
        "sha256": "105e3b93fb7be691d330e4e35451455352c5e64fc914ede3e7a253d4f769154a"},
}
# Frozen at preparation, never recalculated from runtime files.
FROZEN_FILES = {'.github/workflows/sealed-historical-execution-input-acquisition-v03.yml': '8ce7bebd7a4a745ad72bf3913f1fed2f626a8608406f5b89f1b1b2e931f20b87',
 'requirements-sealed-execution-quote-v01.txt': '03f4da335027e4c83bcf38e523c2e11aeaae49778f5bd6caa47e4703348b31b4',
 'research/data-audits/sealed-historical-execution-input-acquisition-v0.3-independent-verification-34084113393.json': '004c730b006e44232431a3a2be0b6e2468f543ac00d352cab3dcb41461e1fb9e',
 'research/runtime/sealed-historical-execution-input-plan-v0.1/freeze-manifest.json': '867ffa66b94890ba06d73e0e70d82058793d8cea76eb3eef44bfb828fdd2df9a',
 'research/runtime/sealed-historical-execution-input-plan-v0.1/opportunity-manifest.json': 'e784f26b3e0fcabd465feb49f4fa7ca0f4444cff737f04d4e0455df64a03469c',
 'research/runtime/sealed-historical-execution-input-plan-v0.1/request-manifest.json': 'ee0701cfbe81bfb546c1fb2d2573cf824b434d3a34ff6f1dffdd8cec5435a2e3',
 'research/strategy/sealed-historical-execution-input-acquisition-v0.3-execution.json': 'ad1fac5f5cd59f61266fea4b3ba41cb54481f3f673b0c260b118163c0847d95f',
 'research/strategy/sealed-historical-execution-input-acquisition-v0.3.json': '1835692c703420dabb9d298ca38592b4e1ff15a133078eacaf28076bceb7b1bc',
 'scripts/run_offline_python_v13.py': 'fd28ca7e4a27832721a890a1a41af36863a7f13568ca9e85e17c2d5f35e0627d',
 'src/momentumbot/research/execution_realism.py': '446509405e3f44e3924c852569c5b06a096f61330552ede850a55c3da5794177',
 'src/momentumbot/research/prospective_daily_account_runtime.py': '45473afe1b947d56fd794ca80a9f72cc7934ca446a161ecb3c7f6ab1e4080d2a',
 'src/momentumbot/research/prospective_market_input_capture.py': '7b736e329a9d12eb2dfdeb09473fd04fc1caa0416eb1cb84ff2db7f4819ae9ee',
 'src/momentumbot/research/sealed_historical_execution_acquisition_v02.py': '92877530ccbea68c1842e76e2438806db935ccad9cad326a119e1cda7065628f',
 'src/momentumbot/research/sealed_historical_execution_acquisition_v03.py': 'cb75e8648fbd333aa578c4045c778377a9eddfba4cf4b2de9ed1cdd5367fa8a8',
 'src/momentumbot/research/sealed_historical_execution_empty_diagnostic_v01.py': 'c638fe8c2580eed70790a399e71afea5cc3246aa3ad7b33c9e92a4573cd14219',
 'src/momentumbot/research/sealed_historical_execution_inputs_v01.py': 'f100c220ed4fe5a6511d854599d8ed1494aaf554540a4fcabf6646f856b2a40f',
 'src/momentumbot/research/sealed_historical_execution_quote_v01.py': 'be5d81c039ba0256b2622ea65d2f966f56fa2f9a87b77f2e39485d92c6464383',
 'src/momentumbot/research/sealed_historical_record_order_registration_v01.py': '4fed4b93ee0bd5fbe2767134b5b007a2e18ed151f1b3d9617241103630fee4da',
 'src/momentumbot/research/sealed_historical_record_order_v01.py': '407e02fc6fe908e26715fac2799f0debf356e96336b640e795b50287762dec6b'}
REASONS = (
    "causal_reference_and_window_available",
    "known_halted_decision_reference",
    "unavailable_exact_quote_request",
    "unavailable_exact_status_request",
    "unavailable_status_not_causally_known",
    "unavailable_no_fresh_decision_quote",
)
BOUNDARY = {
    "provider_calls": 0, "provider_purchase_authorized_usd": "0",
    "micro_reexecuted": False, "account_or_fill_simulation_executed": False,
    "backtesting_executed": False, "retrospective_inputs_loaded": False,
    "policy_changed": False, "acquisition_gate_passed": False,
    "runtime_input_eligible": False, "historical_execution_authorized": False,
    "management_input_gate_passed": False, "account_input_gate_passed": False,
    "paper_or_live_orders_authorized": False,
}
NEXT_GATE = "registered_historical_account_and_management_input_resolution_preserving_all_unavailable_opportunities"


def contract() -> dict:
    return seal({
        "schema_version": 1, "contract_id": CONTRACT_ID,
        "artifact_type": "registered_provider_free_historical_input_availability",
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "artifacts": ARTIFACTS, "frozen_parent_file_sha256": FROZEN_FILES,
        "request_list_content_sha256": REQUEST_LIST_SHA256,
        "dates": list(plan.EXPECTED_DATES), "opportunity_count": 109,
        "request_count": 90, "symbol_date_count": 45,
        "inherited_complete_tape_count": 89,
        "unavailable_request": JVA_REQUEST, "unavailable_opportunity": JVA_OPPORTUNITY,
        "hypothesis": "exact_retained_evidence_can_be_composed_without_substitution_or_policy_change",
        "window_before_decision_ns": adapter.PRE_DECISION_QUOTE_NS,
        "window_after_decision_ns": adapter.POST_DECISION_CAPTURE_NS,
        "request_end_exclusive_pad_ns": 1,
        "quote_order": "unchanged_native_receive_time_sequence_and_original_request_ordinal",
        "window_mechanics": "unchanged_record_order_adapter_capture_window",
        "decision_reference": "unchanged_daily_account_runtime_decision_quote_latest_inclusive_100ms",
        "reference_halt_state": "unchanged_frozen_quote_associated_status_no_new_status_inference",
        "cross_schema_ties": "unchanged_unavailable_quote_status_receive_time_ambiguity",
        "unknown_status": "unchanged_fail_closed_full_window",
        "missing_input": "explicit_unavailable_no_empty_tape_resting_quote_or_no_trade_inference",
        "reason_codes": list(REASONS), "all_profiles_and_no_decision_dates_preserved": True,
        "request_evidence_complete_implies_all_opportunities_available": False,
        "availability_implies_trade_or_order_eligibility": False,
        "output": "30_deterministic_gzip_date_documents_and_one_manifest_write_once",
        "boundary": BOUNDARY, "next_gate": NEXT_GATE,
    })


def _regular(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("regular nonsymlink file required")
    if any(parent.is_symlink() for parent in path.parents):
        raise ValueError("symlink file ancestor rejected")


def validate_registration(root: Path) -> dict:
    for name, sha in FROZEN_FILES.items():
        _regular(root / name)
        if file_sha(root / name) != sha:
            raise ValueError("frozen availability parent differs: " + name)
    require_exact(frozen(root / CONTRACT_PATH), contract(), "availability registration")
    acquisition.validate_inputs(root)
    plan.validate_registration(
        repo_root=root, micro_root=root / "research/runtime/sealed-historical-micro-v0.1",
        scanner_root=root / "research/runtime/sealed-historical-scanner-activation-v0.2",
        output_root=root / PLAN_PATH,
    )
    return seal({"contract_content_sha256": contract()["content_sha256"],
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "verification_passed": True, **BOUNDARY})


def _inventory(root: Path) -> dict:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("regular evidence directory required")
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError("nonregular evidence member")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = {
                "sha256": file_sha(path), "bytes": path.stat().st_size}
    return result


def verify_artifacts(root: Path, *, result_zip: Path, consumption_zip: Path,
                     workspace: Path) -> tuple[Path, Path, dict]:
    """Verify both original ZIPs and re-run the frozen full capture verifier."""
    validate_registration(root)
    audit = frozen(root / AUDIT_PATH)
    extracted = {}
    for kind, path in (("result", result_zip), ("consumption", consumption_zip)):
        _regular(path)
        spec = ARTIFACTS[kind]
        if path.stat().st_size != spec["bytes"]:
            raise ValueError("exact acquisition ZIP size differs")
        dest = workspace / kind
        acquisition.extract_exact_zip(path, dest, spec["sha256"])
        inventory = _inventory(dest)
        if len(inventory) != spec["file_count"]:
            raise ValueError("exact acquisition file population differs")
        extracted[kind] = dest
    result = extracted["result"]
    verified = acquisition.verify_capture(result, root, require_complete=True)
    require_exact(verified, audit["frozen_verifier_confirmation"], "independent capture verification")
    for name in ("consumption.json", "contract.json", "execution.json", "environment.json",
                 "parent-verification.json", *acquisition.PARENT_ARTIFACTS):
        if (result / name).read_bytes() != (extracted["consumption"] / name).read_bytes():
            raise ValueError("consumption/result shared evidence differs")
    parent = workspace / "prefix"
    acquisition.extract_exact_zip(result / "parent-v02-result.zip", parent,
        acquisition.PARENT_ARTIFACTS["parent-v02-result.zip"]["sha256"])
    return result, parent, verified


@dataclass(frozen=True)
class RequestInput:
    request: dict
    evidence: dict
    records: list[dict] | None


def _complete_input(request: dict, receipt: Path, tape_root: Path, archive_sha: str) -> RequestInput:
    payload = frozen(receipt)
    require_exact(payload["request"], request, "request receipt")
    completion = payload["completion"]
    if completion["status"] != "complete":
        raise ValueError("exact complete source receipt required")
    tape = completion["tape"]
    rows, info = acquisition.tape_records(tape_root / tape["path"])
    require_exact(tape, {"path": tape["path"], **info}, "full input tape")
    evidence = seal({"request_id": request["request_id"],
        "request_content_sha256": canonical_fingerprint(request), "classification": "complete",
        "archive_sha256": archive_sha, "receipt_path": receipt.relative_to(tape_root).as_posix(),
        "receipt_file_sha256": file_sha(receipt), "tape": tape,
        "records_content_sha256": canonical_fingerprint(rows), "unavailable_code": None})
    return RequestInput(request, evidence, rows)


def load_request_inputs(root: Path, result: Path, prefix: Path) -> list[RequestInput]:
    requests = frozen(root / PLAN_PATH / "request-manifest.json")["requests"]
    inputs = []
    for i, request in enumerate(requests):
        if i == 24:
            if request["request_id"] != JVA_REQUEST:
                raise ValueError("frozen unavailable request identity differs")
            audit = frozen(root / AUDIT_PATH)
            require_exact(audit["remaining_unavailable_opportunity"], next(
                row for row in frozen(root / PLAN_PATH / "opportunity-manifest.json")["opportunities"]
                if row["opportunity_id"] == JVA_OPPORTUNITY), "unavailable opportunity")
            inputs.append(RequestInput(request, seal({"request_id": JVA_REQUEST,
                "request_content_sha256": canonical_fingerprint(request), "classification": "unavailable",
                "archive_sha256": acquisition.JVA_ZIP_SHA,
                "receipt_path": "diagnostic-report.json",
                "receipt_content_sha256": acquisition.JVA_REPORT_SHA,
                "tape": None, "records_content_sha256": None,
                "unavailable_code": "metadata_only_exact_request"}), None))
        else:
            parent = i < 24
            source = prefix if parent else result
            archive_sha = acquisition.PARENT_ARTIFACTS["parent-v02-result.zip"]["sha256"] if parent else ARTIFACTS["result"]["sha256"]
            inputs.append(_complete_input(request, source / "receipts" / f"request-{i:03d}.json", source, archive_sha))
    return inputs


def _validate_request_input(value: RequestInput, schema: str) -> None:
    sha = adapter._request(value.request, schema)
    evidence = value.evidence
    require_exact(evidence, seal({k: v for k, v in evidence.items() if k != "content_sha256"}), "source evidence seal")
    if evidence["request_content_sha256"] != sha or evidence["request_id"] != value.request["request_id"]:
        raise ValueError("request/evidence identity differs")
    if evidence["classification"] == "complete":
        if value.records is None or not value.records or evidence["records_content_sha256"] != canonical_fingerprint(value.records):
            raise ValueError("complete request requires its exact nonempty records")
        (adapter.quote_events if schema == "mbp-1" else adapter.status_events)(value.records, value.request)
    elif evidence["classification"] == "unavailable":
        if value.records is not None or evidence["tape"] is not None or evidence["records_content_sha256"] is not None:
            raise ValueError("unavailable request cannot contain an empty or substituted tape")
    else:
        raise ValueError("unclassified source input")


def compose_opportunity(opportunity: dict, quotes: RequestInput, statuses: RequestInput) -> dict:
    """Apply frozen mechanics to one already-bound input pair; no order sizing."""
    identity = adapter.WindowIdentity(**{k: opportunity[k] for k in (
        "opportunity_id", "trading_date", "symbol", "decision_ts_ns")})
    for source, schema in ((quotes, "mbp-1"), (statuses, "status")):
        _validate_request_input(source, schema)
        if source.request["trading_date"] != identity.trading_date or source.request["symbols"] != [identity.symbol]:
            raise ValueError("opportunity/source symbol or date differs")
        start = identity.decision_ts_ns - adapter.PRE_DECISION_QUOTE_NS
        end = identity.decision_ts_ns + adapter.POST_DECISION_CAPTURE_NS
        if not source.request["start_ns"] <= start < end < source.request["end_ns"]:
            raise ValueError("opportunity window not covered by exact request")
    if quotes.request["end_ns"] != statuses.request["end_ns"]:
        raise ValueError("quote/status exact request ends differ")
    window = reference = None
    state = "unavailable"
    if quotes.evidence["classification"] == "unavailable":
        reason = "unavailable_exact_quote_request"
    elif statuses.evidence["classification"] == "unavailable":
        reason = "unavailable_exact_status_request"
    else:
        window = adapter.capture_window(identity, quotes.request, quotes.records, statuses.request, statuses.records)
        events = tuple(adapter.RecordOrderedTopOfBook(**{k: row[k] for k in (
            "symbol", "ts_recv_ns", "sequence", "bid_price", "bid_size", "ask_price",
            "ask_size", "halted", "source_request_sha256", "source_record_index")}) for row in window["quotes"])
        adapter._validate_record_order_stream(identity.symbol, events)
        chosen = _decision_quote(events, identity.decision_ts_ns)
        if not window["status_coverage_complete"]:
            reason = "unavailable_status_not_causally_known"
        elif chosen is None:
            reason = "unavailable_no_fresh_decision_quote"
        else:
            reference = next(dict(row) for row in window["quotes"] if row["source_record_index"] == chosen.source_record_index)
            reason = "known_halted_decision_reference" if chosen.halted else "causal_reference_and_window_available"
            state = "halted" if chosen.halted else "available"
    return seal({"opportunity": opportunity, "input_status": state, "reason": reason,
        "quote_request_evidence_sha256": quotes.evidence["content_sha256"],
        "status_request_evidence_sha256": statuses.evidence["content_sha256"],
        "capture": window, "decision_reference": reference,
        "decision_reference_age_ns": None if reference is None else identity.decision_ts_ns - reference["ts_recv_ns"],
        "availability_is_trade_or_order_eligibility": False, **BOUNDARY})


def _summary(rows: list[dict]) -> dict:
    counts = Counter(row["input_status"] for row in rows)
    reasons = Counter(row["reason"] for row in rows)
    return {"opportunity_count": len(rows),
        "input_status_counts": {key: counts[key] for key in ("available", "halted", "unavailable")},
        "reason_counts": {key: reasons[key] for key in REASONS},
        "quote_occurrence_count": sum(len(row["capture"]["quotes"]) for row in rows if row["capture"] is not None)}


def _build_dates(opportunities: dict, inputs: list[RequestInput]) -> tuple[dict[str, dict], dict]:
    request_list = [source.request for source in inputs]
    if canonical_fingerprint(request_list) != REQUEST_LIST_SHA256:
        raise ValueError("complete original request order differs")
    index = {source.request["request_id"]: source for source in inputs}
    if len(index) != 90:
        raise ValueError("missing or duplicate source request")
    for source in inputs:
        _validate_request_input(source, source.request["schema"])
    if [v.request["request_id"] for v in inputs if v.evidence["classification"] == "unavailable"] != [JVA_REQUEST]:
        raise ValueError("verified request classifications changed")
    rows = opportunities["opportunities"]
    if len(rows) != 109 or len({r["opportunity_id"] for r in rows}) != 109:
        raise ValueError("complete unique opportunity population required")
    days, all_rows = {}, []
    for day in opportunities["dates"]:
        date = day["trading_date"]
        daily = []
        for opportunity in rows:
            if opportunity["trading_date"] != date:
                continue
            stem = f"{date}-{opportunity['symbol']}"
            daily.append(compose_opportunity(opportunity, index[stem + "-mbp-1"], index[stem + "-status"]))
        if len(daily) != day["decision_count"]:
            raise ValueError("date decision population differs")
        days[date] = seal({"schema_version": 1, "contract_id": CONTRACT_ID,
            "artifact_type": "historical_execution_input_availability_date",
            "trading_date": date, "source_date": day,
            "opportunity_manifest_content_sha256": opportunities["content_sha256"],
            "date_status": "not_applicable_no_micro_decisions" if not daily else "opportunities_classified",
            "summary": _summary(daily), "opportunities": daily, **BOUNDARY})
        all_rows.extend(daily)
    if list(days) != list(plan.EXPECTED_DATES) or len(all_rows) != 109:
        raise ValueError("exact 30-session population required")
    return days, _summary(all_rows)


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _gzip_bytes(value: dict) -> bytes:
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0, compresslevel=9) as handle:
        handle.write(_json_bytes(value))
    return output.getvalue()


def build_bundle(root: Path, *, result_zip: Path, consumption_zip: Path) -> dict[str, bytes]:
    with tempfile.TemporaryDirectory(prefix="historical-availability-inputs-") as temporary:
        result, prefix, verified = verify_artifacts(root, result_zip=result_zip,
            consumption_zip=consumption_zip, workspace=Path(temporary))
        inputs = load_request_inputs(root, result, prefix)
        opportunities = frozen(root / PLAN_PATH / "opportunity-manifest.json")
        days, summary = _build_dates(opportunities, inputs)
        request_evidence = [source.evidence for source in inputs]
    import hashlib
    files = {f"dates/{date}.json.gz": _gzip_bytes(payload) for date, payload in days.items()}
    file_info = {name: {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)} for name, raw in files.items()}
    implementation = {name: file_sha(root / name) for name in (MODULE_PATH, SCRIPT_PATH, WORKFLOW_PATH, CONTRACT_PATH)}
    manifest = seal({"schema_version": 1, "contract_id": CONTRACT_ID,
        "artifact_type": "frozen_provider_free_historical_execution_input_availability",
        "contract_content_sha256": contract()["content_sha256"],
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "implementation_file_sha256": implementation, "source_artifacts": ARTIFACTS,
        "verified_capture": verified, "opportunity_manifest_content_sha256": opportunities["content_sha256"],
        "request_list_content_sha256": REQUEST_LIST_SHA256, "request_evidence": request_evidence,
        "request_evidence_complete": True, "complete_request_count": 89, "unavailable_request_count": 1,
        "dates": list(days), "date_file_inventory": file_info,
        "date_content_sha256": {date: payload["content_sha256"] for date, payload in days.items()},
        "summary": summary, "all_109_opportunities_classified": True,
        "all_opportunity_inputs_available": summary["input_status_counts"]["available"] == 109,
        "profile_decision_counts": opportunities["profile_decision_counts"],
        "explicit_no_decision_dates": [date for date, payload in days.items() if payload["summary"]["opportunity_count"] == 0],
        "next_gate": NEXT_GATE, **BOUNDARY})
    files["manifest.json"] = _json_bytes(manifest)
    # Recheck immutable local parents after reading all artifacts.
    validate_registration(root)
    return files


def _safe_output(root: Path, output: Path) -> None:
    if output.is_symlink() or any(parent.is_symlink() for parent in output.parents):
        raise ValueError("output cannot use symlinks")
    if output.resolve().is_relative_to(root.resolve()) and output.resolve() != (root / OUTPUT_PATH).resolve():
        raise ValueError("output cannot overwrite frozen repository inputs")


def write_bundle(root: Path, *, output: Path, result_zip: Path, consumption_zip: Path) -> dict:
    _safe_output(root, output)
    if output.exists():
        raise FileExistsError("availability output is write-once; existing evidence retained")
    files = build_bundle(root, result_zip=result_zip, consumption_zip=consumption_zip)
    output.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(raw)
    return _verify_written(output, files)


def _verify_written(output: Path, expected: dict[str, bytes]) -> dict:
    actual = _inventory(output)
    if set(actual) != set(expected):
        raise ValueError("complete availability inventory differs")
    for name, raw in expected.items():
        if (output / name).read_bytes() != raw:
            raise ValueError("availability bytes differ from source reconstruction: " + name)
    manifest = frozen(output / "manifest.json")
    return seal({"verification_passed": True, "contract_id": CONTRACT_ID,
        "manifest_file_sha256": file_sha(output / "manifest.json"),
        "manifest_content_sha256": manifest["content_sha256"],
        "file_count": len(actual), "file_inventory": actual,
        "summary": manifest["summary"], "request_evidence_complete": True,
        "all_109_opportunities_classified": True, **BOUNDARY})


def verify_bundle(root: Path, *, output: Path, result_zip: Path, consumption_zip: Path) -> dict:
    """Rebuild all windows from the original exact artifacts, not a rehashed output."""
    _safe_output(root, output)
    return _verify_written(output, build_bundle(root, result_zip=result_zip, consumption_zip=consumption_zip))
