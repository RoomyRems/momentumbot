"""Independent stdlib checks of retained XAGE bytes and terminal quote artifacts.

No research implementation imports, provider clients, extraction, or replay.
"""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CID = "sealed-historical-management-exit-quote-v0.1"
REUSE = f"research/data-audits/{CID}-xage-reuse.json"
PLAN = "research/runtime/sealed-historical-management-runner-v0.1/exit-input-request-plan.json"
PLAN_FILE_SHA = "562ed42e20c7021eecf384e3a22aed5f5ce25ae15926dd93072a0313d0e6f461"
REQUEST_SHA = "973a926e063fda7ec76883dd4297b88c77a06af22fe3bc0618330e98e28825b4"
ARCHIVES = {
    "result": (13700990, "1fe68f4e526caa6ce0ee8f8845248e5ef3039f3e3ffbce370020162add3b99d6", 144),
    "consumption": (1137522, "105e3b93fb7be691d330e4e35451455352c5e64fc914ede3e7a253d4f769154a", 17),
}


def check(ok, message):
    if not ok:
        raise ValueError(message)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fingerprint(value):
    return sha(encoded(value))


def sealed(raw):
    value = json.loads(raw)
    check(value["content_sha256"] == fingerprint({k:v for k,v in value.items() if k != "content_sha256"}), "content seal differs")
    return value


def archive(path, expected=None):
    raw = path.read_bytes()
    if expected:
        check((len(raw), sha(raw)) == expected[:2], "exact original ZIP bytes differ")
    files = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for member in z.infolist():
            name = member.filename
            check(not member.is_dir() and name not in files and not PurePosixPath(name).is_absolute()
                  and ".." not in PurePosixPath(name).parts and "\\" not in name, "unsafe or duplicate ZIP member")
            check((member.external_attr >> 16) & 0o170000 != 0o120000, "symlink ZIP member")
            files[name] = z.read(member)  # Read every byte and validate every member's CRC.
    if expected:
        check(len(files) == expected[2], "exact original ZIP population differs")
    info = {"bytes": len(raw), "sha256": sha(raw), "file_count": len(files),
            "files": {n:{"bytes":len(b), "sha256":sha(b)} for n,b in sorted(files.items())}}
    return files, info


def registration(root):
    check(sha((root / PLAN).read_bytes()) == PLAN_FILE_SHA, "frozen exit plan bytes differ")
    plan = sealed((root / PLAN).read_bytes())
    manifest = sealed((root / f"research/runtime/{CID}/request-manifest.json").read_bytes())
    contract = sealed((root / f"research/strategy/{CID}.json").read_bytes())
    proof = sealed((root / REUSE).read_bytes())
    check(contract["reuse_evidence_file_sha256"] == sha((root / REUSE).read_bytes()), "bound reuse evidence differs")
    check(manifest["reuse_evidence_file_sha256"] == contract["reuse_evidence_file_sha256"], "manifest reuse binding differs")
    requests = manifest["requests"]
    check(fingerprint(requests) == REQUEST_SHA == fingerprint(plan["new_requests"]) and len(requests) == 80, "exact 80 requests differ")
    check(Counter(r["schema"] for r in requests) == {"mbp-1":40, "status":40}, "schema population differs")
    check(len(plan["groups"]) == 41 and len(plan["opportunities"]) == 109, "original population differs")
    check(Counter(r["entry_input_status"] for r in plan["opportunities"]) == {"available":86, "unavailable":23}, "availability population differs")
    check(manifest["all_original_opportunities_content_sha256"] == fingerprint(plan["opportunities"]), "original opportunity commitment differs")
    group = next(g for g in plan["groups"] if g["group_id"] == "2025-07-15-XAGE-common-management-exit")
    check(fingerprint(group) == fingerprint(proof["original_group"]), "reuse group differs")
    check(group["requests"] == plan["reuse_candidate_requests"], "reuse pair differs")
    check(not {r["request_id"] for r in group["requests"]} & {r["request_id"] for r in requests}, "reuse pair requoted")
    return plan, manifest, contract, proof


def verify_reuse(root, result_zip, consumption_zip):
    plan, manifest, contract, proof = registration(root)
    result, ri = archive(result_zip, ARCHIVES["result"])
    consumption, ci = archive(consumption_zip, ARCHIVES["consumption"])
    shared = sorted(set(result) & set(consumption))
    for name in shared:
        check(result[name] == consumption[name], "original shared evidence differs: " + name)
    original = sealed((root / "research/runtime/sealed-historical-execution-input-plan-v0.1/request-manifest.json").read_bytes())["requests"]
    check(len(proof["sources"]) == 2, "exact source pair required")
    counts = []
    for position, source in enumerate(proof["sources"]):
        index = 78 + position
        request = original[index]
        evidence = source["source_evidence"]
        check(source["request"] == request == proof["original_group"]["requests"][position], "original request identity differs")
        receipt_name = f"receipts/request-{index:03d}.json"
        receipt = sealed(result[receipt_name])
        check(evidence["receipt_path"] == receipt_name and evidence["receipt_file_sha256"] == sha(result[receipt_name]), "receipt binding differs")
        check(receipt["request"] == request and receipt["completion"]["status"] == "complete", "complete exact receipt required")
        tape = evidence["tape"]
        check(tape == receipt["completion"]["tape"], "receipt tape binding differs")
        raw = result[tape["path"]]
        check((len(raw), sha(raw)) == (tape["file_bytes"], tape["file_sha256"]), "compressed tape bytes differ")
        digest, list_digest = hashlib.sha256(), hashlib.sha256(b"[")
        count, length, previous, first, last = 0, 0, None, None, None
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as handle:
            for line in handle:
                row = json.loads(line)
                canonical = encoded(row)
                check(line == canonical + b"\n", "normalized canonical row differs")
                digest.update(line); length += len(line)
                if count:
                    list_digest.update(b",")
                list_digest.update(canonical)
                ts = row["ts_recv_ns"]
                check(type(ts) is int and request["start_ns"] <= ts < request["end_ns"], "row outside original request")
                check(row["symbol"] == "XAGE", "source symbol differs")
                if position == 0:
                    check(set(row) == {"symbol", "ts_recv_ns", "sequence", "bid_px_nanos", "bid_size", "ask_px_nanos", "ask_size", "source_request_sha256", "source_record_index"}, "quote fields differ")
                    check(row["source_request_sha256"] == fingerprint(request) and type(row["source_record_index"]) is int and row["source_record_index"] == count, "original ordinal differs")
                    for field in ("sequence", "bid_px_nanos", "bid_size", "ask_px_nanos", "ask_size"):
                        check(type(row[field]) is int and row[field] >= 0, "quote numeric field differs")
                    key = ts, row["sequence"]
                    check(previous is None or key >= previous, "quote native order reversed")
                else:
                    check(set(row) == {"symbol", "ts_recv_ns", "action", "is_trading"}, "status fields differ")
                    check(type(row["action"]) is int and 0 <= row["action"] <= 14 and row["is_trading"] in {"Y", "N", "~"}, "status vocabulary differs")
                    key = ts, count
                    check(previous is None or key > previous, "status native order reversed")
                previous = key
                if first is None:
                    first = ts
                last = ts
                count += 1
        list_digest.update(b"]")
        check((length, digest.hexdigest(), count) == (tape["normalized_bytes"], tape["normalized_sha256"], tape["row_count"]), "complete normalized tape differs")
        check(list_digest.hexdigest() == evidence["records_content_sha256"], "complete record list differs")
        check((first, last) == (source["first_record_ts_recv_ns"], source["last_record_ts_recv_ns"]), "source endpoint record times differ")
        need = proof["original_group"]["required_quote_start_ns"] if position == 0 else request["start_ns"]
        check(request["start_ns"] <= need < proof["original_group"]["required_end_ns"] <= request["end_ns"], "required interval not contained")
        counts.append(count)
    check(counts == [230703, 4], "exact retained XAGE population differs")
    return {"verification_passed": True, "mode": "reuse", "archives": {"result":ri, "consumption":ci},
        "quote_rows":counts[0], "status_rows":counts[1], "required_intervals_contained":True,
        "reuse_evidence_file_sha256":sha((root / REUSE).read_bytes()),
        "remaining_requests":80, "provider_calls":0, "historical_execution_authorized":False}


def verify_quote(root, result_zip, consumption_zip):
    plan, manifest, contract, proof = registration(root)
    result, ri = archive(result_zip)
    consumption, ci = archive(consumption_zip)
    check(set(result) == {"contract.json", "execution.json", "consumption.json", "request-manifest.json", "xage-reuse.json", "http-ledger.json", "metadata-ledger.json", "quote-report.json", "quote-inventory.json"}, "complete quote inventory differs")
    for name, path in {"contract.json":f"research/strategy/{CID}.json", "execution.json":f"research/strategy/{CID}-execution.json", "request-manifest.json":f"research/runtime/{CID}/request-manifest.json", "xage-reuse.json":REUSE}.items():
        check(result[name] == consumption[name] == (root / path).read_bytes(), "quote bound file differs: " + name)
    check(result["consumption.json"] == consumption["consumption.json"], "consumption marker differs")
    marker, execution = sealed(result["consumption.json"]), sealed(result["execution.json"])
    ref = json.loads(consumption["consumption-ref.json"])
    check(ref["ref"] == marker["consumption_ref"] == contract["consumption_ref"] and ref["object"]["sha"] == marker["execution_commit_sha"], "atomic consumption differs")
    check(marker["execution_content_sha256"] == execution["content_sha256"] and marker["workflow_run_attempt"] == 1, "execution consumption differs")
    for field, path in (("code_ci_run_id", ".github/workflows/ci.yml"), ("code_validation_run_id", ".github/workflows/sealed-historical-management-exit-quote-v01.yml")):
        run = json.loads(consumption[field + ".json"])
        expected = {"id":int(execution[field]), "head_sha":execution["code_commit_sha"], "head_branch":"phase-3-historical-snapshot", "event":"push", "run_attempt":1, "status":"completed", "conclusion":"success", "path":path}
        check(all(run[k] == v for k,v in expected.items()), "successful parent run differs")
    inv, report = sealed(result["quote-inventory.json"]), sealed(result["quote-report.json"])
    check(inv["files"] == {n:sha(b) for n,b in result.items() if n != "quote-inventory.json"}, "quote byte inventory differs")
    metadata, http = sealed(result["metadata-ledger.json"]), sealed(result["http-ledger.json"])
    calls = report["calls"]
    check(calls == metadata["calls"] and metadata["complete"] is True and metadata["call_count"] == 160, "complete metadata ledger differs")
    check(len(calls) == len(http["attempts"]) == http["http_attempts"] == 160 and http["blocked_attempts"] == 0, "complete HTTP accounting differs")
    check(all(http[k] == 0 for k in ("automatic_retries", "redirects_followed", "non_metadata_calls")), "unexpected transport authority")
    total_size, total_cost = 0, Decimal(0)
    expected_rows = []
    for i, request in enumerate(manifest["requests"]):
        pair = calls[2*i:2*i+2]
        for j, method in enumerate(("get_billable_size", "get_cost")):
            ordinal = 2*i+j+1
            call, attempt = pair[j], http["attempts"][ordinal-1]
            identity = {"ordinal":ordinal, "request_id":request["request_id"], "method":method}
            check(all(call[k] == v for k,v in identity.items()) and call["request_content_sha256"] == fingerprint(request), "metadata request order differs")
            check(call["status"] == "success" and call["error"] is None, "metadata call unsuccessful")
            check(attempt == {**identity, "status":"success", "http_status":200}, "HTTP result/order differs")
        size, cost = pair[0]["value"], pair[1]["value"]
        check(type(size) is int and size > 0 and type(cost) is str, "positive billable size or exact cost missing")
        amount = Decimal(cost)
        check(amount.is_finite() and amount >= 0, "quoted cost invalid")
        total_size += size; total_cost += amount
        expected_rows.append({"request_id":request["request_id"], "schema":request["schema"], "billable_size_bytes":size,
            "quoted_cost_usd":cost, "quote_complete":True, "available":True, "status":"available"})
    check(report["quote_rows"] == expected_rows, "terminal per-request values differ")
    check(report["total_billable_size_bytes"] == total_size and Decimal(report["total_quoted_cost_usd"]) == total_cost, "aggregate quote differs")
    check(report["metadata_quote_gate_passed"] is True and report["status"] == "complete" and report["available_request_count"] == report["complete_request_count"] == 80, "terminal quote gate differs")
    provenance = {"execution_content_sha256":execution["content_sha256"], "execution_commit_sha":marker["execution_commit_sha"],
        "code_commit_sha":execution["code_commit_sha"], "code_tree_sha":execution["code_tree_sha"],
        "workflow_run_id":marker["workflow_run_id"], "workflow_run_attempt":1, "consumption_content_sha256":marker["content_sha256"],
        "reuse_evidence_file_sha256":sha((root / REUSE).read_bytes())}
    check(report["provenance"] == inv["provenance"] == provenance, "quote provenance differs")
    check(report["contract_content_sha256"] == contract["content_sha256"] and report["request_list_content_sha256"] == REQUEST_SHA, "quote scope differs")
    for key in ("timeseries_acquired", "account_or_fill_simulation_executed", "backtesting_executed", "retrospective_inputs_loaded", "policy_changed", "download_authorized_by_this_artifact"):
        check(report[key] is False, "quote boundary differs")
    return {"verification_passed": True, "mode":"quote", "archives":{"result":ri, "consumption":ci},
        "request_count":80, "metadata_calls":160, "http_attempts":160, "total_billable_size_bytes":total_size,
        "total_quoted_cost_usd":format(total_cost, "f"), "quote_report_content_sha256":report["content_sha256"],
        "provenance":provenance, "metadata_quote_gate_passed":True, "acquisition_authorized":False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("reuse", "quote"))
    parser.add_argument("--result-zip", type=Path, required=True)
    parser.add_argument("--consumption-zip", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = (verify_reuse if args.mode == "reuse" else verify_quote)(args.repo_root, args.result_zip, args.consumption_zip)
    print(json.dumps({**result, "content_sha256":fingerprint(result)}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
