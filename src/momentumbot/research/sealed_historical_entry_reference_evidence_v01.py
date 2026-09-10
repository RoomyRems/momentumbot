"""Source-backed entry observations; no account replay or standing-quote inference.

The observation policy requires a usable quote update in the frozen inclusive
100 ms lookback. A verified absence withholds entry under that explicit policy;
it does not turn the original unavailable input into a complete market history.
"""
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from contextlib import ExitStack
import gzip
import hashlib
import io
import json
from pathlib import Path
import zipfile

from momentumbot.research import sealed_historical_execution_availability_v01 as availability
from momentumbot.research import sealed_historical_record_order_v01 as adapter

ID = "sealed-historical-entry-reference-evidence-v0.1"
PARENT = "ae3711e8f248e28754166ba580d9c7b6bfd3e8ef"
PARENT_TREE = "c5b31a3536422d0092dfeafdd322d4e76e83bac8"
POLICY_ID = "strict-observed-quote-entry-gate-v0.1"
LOOKBACK_NS = 100_000_000
ACCEPTANCE_ID = "sealed-historical-account-hosted-acceptance-v0.1"
ACCEPTANCE_SHA = "c22f691546c5370525a32eca00436f3ebbf812c56f45e058b24aea22854a3657"
REPORT_SHA = "d876c42cc079360b2af2173094446620df5e1e4944323c8f14b2c51b53b94d13"
AVAILABILITY_SHA = "9fd935aa16caef6a823ab6a44c4f7e864e47231cf7189b7feb4069ac179bb6d4"
JVA_SHA = "b7324d1e6f123a2adca163f8d8e609db6a173f200c36a180396b8dad734c7da7"
JVA_REPORT = "research/data-audits/sealed-historical-execution-input-empty-diagnostic-v0.1-report-34079022132.json"
OWN_FILES = (
    "src/momentumbot/research/sealed_historical_entry_reference_evidence_v01.py",
    "scripts/audit_sealed_historical_entry_reference_evidence_v01.py",
    "tests/test_sealed_historical_entry_reference_evidence_v01.py",
)
BOUNDARY = {
    "original_unavailable_inputs_reclassified": False,
    "original_runtime_changed": False,
    "standing_quote_reconstruction_established": False,
    "full_market_input_coverage_established": False,
    "account_backtest_complete": False,
    "financial_metrics_eligible": False,
    "historical_replay_executed": False,
    "provider_requests_authorized": False,
    "retrospective_labels_opened": False,
    "broker_orders_authorized": False,
    "policy_promoted": False,
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def seal(value):
    body = {k: v for k, v in value.items() if k != "content_sha256"}
    return {**body, "content_sha256": fingerprint(body)}


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False,
        allow_nan=False) + "\n").encode()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def document(raw, expected=None):
    value = json.loads(raw, object_pairs_hook=unique_object)
    require(value == seal(value), "document content seal differs")
    if expected is not None:
        require(value["content_sha256"] == expected, "frozen document identity differs")
    return value


def file_spec(path):
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def registration(root):
    # Reuse the parent registration check, not its historical runtime/checker.
    import verify_sealed_historical_account_hosted_acceptance_v01 as accepted
    accepted.check_registration(root, ACCEPTANCE_SHA)
    manifest_path = root / "research/runtime/sealed-historical-execution-availability-v0.1/manifest.json"
    manifest = document(manifest_path.read_bytes(), AVAILABILITY_SHA)
    report_path = root / f"research/data-audits/{ACCEPTANCE_ID}/acceptance-report.json"
    document(report_path.read_bytes(), REPORT_SHA)
    document((root / JVA_REPORT).read_bytes(), JVA_SHA)
    require(adapter.PRE_DECISION_QUOTE_NS == LOOKBACK_NS, "frozen lookback differs")
    sources = [manifest_path, report_path, root / JVA_REPORT,
        root / f"research/strategy/{ACCEPTANCE_ID}.json",
        root / availability.PLAN_PATH / "opportunity-manifest.json",
        root / availability.PLAN_PATH / "request-manifest.json"]
    sources += [manifest_path.parent / path for path in manifest["date_file_inventory"]]
    return seal({"contract_id": ID, "parent_commit_sha": PARENT, "parent_tree_sha": PARENT_TREE,
        "artifact_type": "source_backed_entry_observation_policy_registration",
        "hypothesis": "complete_original_streams_distinguish_no_fresh_update_from_unverified_source",
        "source_diagnosis_known_before_registration": True,
        "policy_id": POLICY_ID, "inclusive_quote_lookback_ns": LOOKBACK_NS,
        "policy_scope": "withhold_entry_without_a_qualifying_observed_update_on_the_original_XNAS_ITCH_feed",
        "reference_present_is_order_authorization": False,
        "unverified_source_is_known_abstention": False,
        "standing_quote_age_limit_relaxed": False, "future_quote_borrowing_allowed": False,
        "capture_windows_extended": False,
        "full_local_replay_required": False,
        "source_artifacts": availability.ARTIFACTS,
        "input_file_specs": {str(p.relative_to(root)): file_spec(p) for p in sources},
        "implementation_file_specs": {p: file_spec(root / p) for p in OWN_FILES},
        "next_gate": "separately_bound_conditional_evaluation_of_the_strict_observed_update_policy",
        **BOUNDARY})


def check_registration(root, expected):
    current = registration(root)
    require(current["content_sha256"] == expected, "external registration differs")
    require((root / f"research/strategy/{ID}.json").read_bytes() == encoded(current),
        "registered implementation or inputs differ")
    return current


def entry_observation(opportunity, quote_request, quotes, status_request, statuses, *, source_state):
    """Classify already verified original records using only the decision prefix.

    The archive loader supplies the source state. Empty data without a verified
    empty-response receipt stays unresolved. This helper cannot authorize orders.
    """
    require(source_state in {"complete", "verified_empty", "unverified"}, "unknown source state")
    identity = adapter.WindowIdentity(**{k: opportunity[k] for k in
        ("opportunity_id", "trading_date", "symbol", "decision_ts_ns")})
    decision = identity.decision_ts_ns
    start = decision - LOOKBACK_NS
    for req, schema in ((quote_request, "mbp-1"), (status_request, "status")):
        adapter._request(req, schema)
        require(req["symbols"] == [identity.symbol] and req["trading_date"] == identity.trading_date,
            "opportunity/source identity differs")
        require(req["start_ns"] <= start <= decision < req["end_ns"], "source does not cover decision lookback")
    result = {"source_state": source_state, "decision_ts_ns": decision,
        "lookback_start_ns": start, "policy_id": POLICY_ID, "order_authorized": False}
    if source_state == "unverified" or statuses is None:
        return {**result, "observation": "unverified_source", "entry_gate": "unresolved"}
    require(quotes is not None, "verified source records missing")
    require(bool(quotes) == (source_state == "complete"), "empty source requires exact empty-response evidence")
    # The loader validated entire tapes. Enforce their typed order here as well.
    adapter._ordered(quotes, identity.symbol, fingerprint(quote_request), contiguous=True)
    require(all(quote_request["start_ns"] <= q.ts_recv_ns < quote_request["end_ns"] for q in quotes),
        "quote outside exact request")
    status_times = [q.ts_recv_ns for q in statuses]
    require(status_times == sorted(status_times) and all(q.symbol == identity.symbol for q in statuses),
        "status source identity/order differs")
    require(all(status_request["start_ns"] <= t < status_request["end_ns"] for t in status_times),
        "status outside exact request")
    initial_index = bisect_right(status_times, start) - 1
    causal_statuses = statuses[initial_index + 1:bisect_right(status_times, decision)]
    status_known = (initial_index >= 0 and statuses[initial_index].is_trading in {"Y", "N"}
        and all(s.is_trading in {"Y", "N"} for s in causal_statuses))
    times = [q.ts_recv_ns for q in quotes]
    lo, hi = bisect_left(times, start), bisect_right(times, decision)
    window = quotes[lo:hi]
    selected = None
    filtered = Counter()
    status_time_set = set(status_times)
    for quote in window:
        idx = bisect_right(status_times, quote.ts_recv_ns) - 1
        if not quote.usable:
            filtered["invalid_book"] += 1
        elif quote.ts_recv_ns in status_time_set:
            filtered["ambiguous_status_time"] += 1
        elif idx < 0 or statuses[idx].is_trading not in {"Y", "N"}:
            filtered["unknown_status"] += 1
        else:
            selected = quote
    result.update({"raw_quote_updates_in_lookback": len(window),
        "older_quote_updates_in_original_request": lo,
        "latest_original_prior_update_age_ns": None if hi == 0 else decision - quotes[hi - 1].ts_recv_ns,
        "causal_status_coverage_complete": status_known,
        "filtered_update_counts": dict(sorted(filtered.items())),
        "reference_source_record_index": None, "reference_age_ns": None,
        "reference_record_sha256": None})
    if not status_known:
        return {**result, "observation": "unknown_causal_status", "entry_gate": "unresolved"}
    if selected is None:
        return {**result, "observation": "no_quote_update_observed" if not window else "no_usable_quote_update",
            "entry_gate": "withhold_entry_under_observed_update_policy"}
    result.update({"reference_source_record_index": selected.source_record_index,
        "reference_age_ns": decision - selected.ts_recv_ns,
        "reference_record_sha256": fingerprint({k: getattr(selected, k)
            for k in adapter.QUOTE_FIELDS | adapter.ORDER_FIELDS})})
    return {**result, "observation": "reference_observed",
        "entry_gate": "reference_present_requires_remaining_entry_checks"}


def open_archive(stack, raw, spec):
    require(len(raw) == spec["bytes"] and hashlib.sha256(raw).hexdigest() == spec["sha256"],
        "original archive bytes differ")
    archive = stack.enter_context(zipfile.ZipFile(io.BytesIO(raw)))
    names = archive.namelist()
    require(len(names) == len(set(names)), "duplicate archive member")
    require(all(not p.startswith("/") and ".." not in Path(p).parts for p in names), "unsafe archive member")
    if "file_count" in spec:
        require(len(names) == spec["file_count"], "archive population differs")
    require(archive.testzip() is None, "archive CRC differs")
    return archive


def request_records(archive, request, evidence):
    document(encoded(evidence))
    require(evidence["classification"] == "complete", "nonempty request not complete")
    require(evidence["request_content_sha256"] == fingerprint(request)
        and evidence["request_id"] == request["request_id"], "source/request binding differs")
    raw_receipt = archive.read(evidence["receipt_path"])
    require(hashlib.sha256(raw_receipt).hexdigest() == evidence["receipt_file_sha256"], "receipt bytes differ")
    receipt = document(raw_receipt)
    require(receipt["request"] == request, "receipt request differs")
    completion = receipt["completion"]
    require(completion["status"] == "complete" and completion["error"] is None
        and completion["failure_stage"] is None, "incomplete or failed source")
    for key in ("partial", "partial_receipt", "partial_tape"):
        require(not completion.get(key), "partial evidence cannot prove absence")
    spec = evidence["tape"]
    require(completion["tape"] == spec, "receipt/tape binding differs")
    raw = archive.read(spec["path"])
    require(len(raw) == spec["file_bytes"] and hashlib.sha256(raw).hexdigest() == spec["file_sha256"],
        "tape file bytes differ")
    decoded = gzip.decompress(raw)
    require(len(decoded) == spec["normalized_bytes"]
        and hashlib.sha256(decoded).hexdigest() == spec["normalized_sha256"], "normalized tape bytes differ")
    rows = [json.loads(line, object_pairs_hook=unique_object) for line in decoded.splitlines()]
    require(len(rows) == spec["row_count"] == completion["normalization"]["row_count"]
        and fingerprint(rows) == evidence["records_content_sha256"], "source row inventory differs")
    reader = adapter.quote_events if request["schema"] == "mbp-1" else adapter.status_events
    return reader(rows, request)


def verify_empty_quote(report, request):
    require(report["diagnostic_evidence_complete"] is True and report["error"] is None,
        "empty-response diagnostic incomplete")
    native = report["native_observation"]
    require(native["decoding_complete"] is True and native["native_record_count"] == 0
        and native["native_mbp1_count"] == 0 and native["record_types"] == {}, "native stream is not verified empty")
    require(native["decoded_v3_record_bytes_sha256"] == hashlib.sha256(b"").hexdigest(), "empty native bytes differ")
    meta = native["metadata"]
    require(meta["exact_request_metadata"] is True and not meta["not_found"] and not meta["partial"],
        "metadata/mapping incomplete")
    require(meta["dataset"]["value"] == request["dataset"] and meta["schema"]["value"] == 1
        and [s["value"] for s in meta["symbols"]] == request["symbols"]
        and meta["start"]["value"] == request["start_ns"] and meta["end"]["value"] == request["end_ns"]
        and meta["limit"]["kind"] == "null", "empty request bounds or scope differ")
    require(meta["mapping_interval_count"] == 1 and len(meta["mappings"]) == 1,
        "empty request mapping missing")
    mapping = meta["mappings"][0]
    require(mapping["raw_symbol"]["value"] == request["symbols"][0] and len(mapping["intervals"]) == 1,
        "empty request mapping identity differs")
    interval = mapping["intervals"][0]
    require(interval["start_date"] <= request["trading_date"] < interval["end_date"]
        and isinstance(interval["instrument_id"], int) and interval["instrument_id"] > 0,
        "empty request mapping does not cover date")


def audit(root, *, result_zip, consumption_zip, expected_contract):
    contract = check_registration(root, expected_contract)
    directory = root / "research/runtime/sealed-historical-execution-availability-v0.1"
    manifest = document((directory / "manifest.json").read_bytes(), AVAILABILITY_SHA)
    opportunities = document((root / availability.PLAN_PATH / "opportunity-manifest.json").read_bytes())
    requests = document((root / availability.PLAN_PATH / "request-manifest.json").read_bytes())["requests"]
    require(fingerprint(requests) == manifest["request_list_content_sha256"], "request list differs")
    original = {}
    for path, spec in manifest["date_file_inventory"].items():
        require(file_spec(directory / path) == spec, "original date bytes differ")
        day = document(gzip.decompress((directory / path).read_bytes()))
        require(day["content_sha256"] == manifest["date_content_sha256"][day["trading_date"]], "date binding differs")
        for row in day["opportunities"]:
            document(encoded(row))
            oid = row["opportunity"]["opportunity_id"]
            require(oid not in original, "duplicate original opportunity")
            original[oid] = row
    ordered = opportunities["opportunities"]
    require(len(original) == len(ordered) == 109 and set(original) == {o["opportunity_id"] for o in ordered},
        "original opportunity population differs")
    evidence = {e["request_id"]: e for e in manifest["request_evidence"]}
    require(len(evidence) == len(requests) == 90, "original request population differs")
    by_pair = defaultdict(list)
    for o in ordered:
        require(original[o["opportunity_id"]]["opportunity"] == o, "original opportunity identity differs")
        by_pair[(o["trading_date"], o["symbol"])].append(o)
    request_by_id = {r["request_id"]: r for r in requests}
    results = {}
    with ExitStack() as stack:
        result = open_archive(stack, result_zip.read_bytes(), availability.ARTIFACTS["result"])
        consumption = open_archive(stack, consumption_zip.read_bytes(), availability.ARTIFACTS["consumption"])
        for name in ("consumption.json", "contract.json", "execution.json", "environment.json",
                     "parent-verification.json", *availability.acquisition.PARENT_ARTIFACTS):
            require(result.read(name) == consumption.read(name), "original consumption/result binding differs")
        prefix_spec = availability.acquisition.PARENT_ARTIFACTS["parent-v02-result.zip"]
        prefix = open_archive(stack, result.read("parent-v02-result.zip"), prefix_spec)
        sources = {availability.ARTIFACTS["result"]["sha256"]: result, prefix_spec["sha256"]: prefix}
        jva_spec = availability.acquisition.PARENT_ARTIFACTS["jva-empty-diagnostic.zip"]
        jva = open_archive(stack, result.read("jva-empty-diagnostic.zip"), jva_spec)
        empty_raw = jva.read("diagnostic-report.json")
        require(empty_raw == (root / JVA_REPORT).read_bytes(), "original empty diagnostic bytes differ")
        empty = document(empty_raw, JVA_SHA)
        for (day, symbol), group in sorted(by_pair.items()):
            qr, sr = (request_by_id[f"{day}-{symbol}-{s}"] for s in ("mbp-1", "status"))
            qe, se = evidence[qr["request_id"]], evidence[sr["request_id"]]
            statuses = request_records(sources[se["archive_sha256"]], sr, se)
            if qe["classification"] == "complete":
                quotes = request_records(sources[qe["archive_sha256"]], qr, qe)
                state = "complete"
            else:
                require(qr["request_id"] == availability.JVA_REQUEST
                    and qe["receipt_content_sha256"] == JVA_SHA and qe["tape"] is None,
                    "unexpected unavailable request")
                verify_empty_quote(empty, qr)
                quotes, state = (), "verified_empty"
            for o in group:
                prior = original[o["opportunity_id"]]
                require(prior["quote_request_evidence_sha256"] == qe["content_sha256"]
                    and prior["status_request_evidence_sha256"] == se["content_sha256"], "opportunity evidence differs")
                observed = entry_observation(o, qr, quotes, sr, statuses, source_state=state)
                chosen = prior["decision_reference"]
                if chosen is not None:
                    require(observed["reference_source_record_index"] == chosen["source_record_index"]
                        and observed["reference_age_ns"] == prior["decision_reference_age_ns"],
                        "original available reference selection differs")
                else:
                    require(observed["reference_source_record_index"] is None, "new reference would change original mechanics")
                results[o["opportunity_id"]] = {"opportunity_id": o["opportunity_id"],
                    "trading_date": day, "symbol": symbol,
                    "original_availability_content_sha256": prior["content_sha256"],
                    "original_input_status": prior["input_status"], "original_reason": prior["reason"],
                    "quote_request_evidence_sha256": qe["content_sha256"],
                    "status_request_evidence_sha256": se["content_sha256"], **observed}
    accepted = document((root / f"research/data-audits/{ACCEPTANCE_ID}/acceptance-report.json").read_bytes(), REPORT_SHA)
    unavailable = {r["opportunity_id"]: r for r in accepted["unavailable_opportunities"]}
    require(set(unavailable) == {k for k, r in results.items() if r["original_input_status"] == "unavailable"},
        "accepted unavailable population differs")
    for oid, prior in unavailable.items():
        row = results[oid]
        require(row["original_availability_content_sha256"] == prior["availability_content_sha256"]
            and row["original_reason"] == prior["reason"], "accepted unavailable evidence differs")
        row["original_unavailable_path_references"] = prior["reference_count"]
        row["original_unavailable_references"] = prior["references"]
    rows = [results[o["opportunity_id"]] for o in ordered]
    return seal({"contract_id": ID, "contract_content_sha256": contract["content_sha256"],
        "artifact_type": "verified_entry_observation_policy_sidecar",
        "parent_acceptance_report_content_sha256": REPORT_SHA,
        "all_original_opportunities_retained": True, "opportunity_count": len(rows),
        "source_artifacts": availability.ARTIFACTS,
        "observation_counts": dict(sorted(Counter(r["observation"] for r in rows).items())),
        "entry_gate_counts": dict(sorted(Counter(r["entry_gate"] for r in rows).items())),
        "no_update_cases_with_older_retained_quotes": sum(r["observation"] == "no_quote_update_observed"
            and r["older_quote_updates_in_original_request"] > 0 for r in rows),
        "original_unavailable_opportunities": len(unavailable),
        "original_unavailable_path_references": sum(r["reference_count"] for r in unavailable.values()),
        "rows": rows, "next_gate": contract["next_gate"], **BOUNDARY})


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(encoded(value))
