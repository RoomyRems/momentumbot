"""Accept one frozen hosted replay and audit coverage; never execute a replay.

This is a post-result, user-authorized validation-plan amendment. It reuses the
original hosted independent check, preserves incomplete local evidence, and
does not reinterpret unavailable inputs or release financial results.
"""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ID = "sealed-historical-account-hosted-acceptance-v0.1"
PARENT_ID = "sealed-historical-account-terminal-continuation-v0.1"
PARENT_COMMIT = "ffa97914add1882b376460b2d41fcc9491873a35"
IMPLEMENTATION = "0f057039e00480f3b0275d0bcd0bdabd23da7a96"
REGISTRATION = "0f2570ba5b71783c3d27b47f2718217d7331bba8a2e8f7f09527c097fdf4a3fb"
RUNTIME = "a429f6723668fe9614ba6366de44b27d016ef939a5361d323bf58dceef250e91"
CHECKER = "d1eb98692d4795ff6985bf19683505ad7f8d9d2a14f019f0790ac723fff390d6"
BINDING = "9bb780dcbfbec3ef1b4e437cc3dc76e1528897956490d4ddd32d399ed5f683cd"
HOSTED_RUN = 34362104473
HOSTED_ARTIFACT = 10120239248
OWN_FILES = ("scripts/verify_sealed_historical_account_hosted_acceptance_v01.py",
             "tests/test_sealed_historical_account_hosted_acceptance_v01.py")
PROVENANCE = f"research/data-audits/{ID}/hosted-provenance.json"
LOCAL_EVIDENCE = (f"research/data-audits/{PARENT_ID}/"
                  "local-incomplete-evidence-20260909T183834Z.zip")
ARCHIVES = {
    "hosted": {"bytes": 5733269,
        "sha256": "4683050552fe81e68b9bbaf7ecdd154bb90fdec50c5baeecf9439ff38c28b014",
        "members": ["account-replay-attempt.json", "account-replay-progress.jsonl",
            "account-replay/account-replay.json", "account-replay/freeze-manifest.json",
            "account-replay/independent-verification.json"]},
    "binding": {"bytes": 377229,
        "sha256": "2577dfdccdee948c9241d3489737e0dac40cf3c97ad826ead9500c095e55d94a",
        "members": ["context-access-verification.json", "freeze-manifest.json",
            "independent-verification.json", "source-bindings.json"]},
    "local": {"bytes": 153980,
        "sha256": "4521c53c74b35a2cefee030e39ab74e1d031c5f6e982ddaf016bd3b35a70aa0c",
        "members": ["account-replay-attempt.json", "account-replay-progress.jsonl",
            "account-replay.log", "status-observation.json", "verification-follower-start.json",
            "verification-follower.log"]},
}
CLOSED = {"full_local_reproduction_verified": False, "replay_executed": False,
    "provider_requests_authorized": False, "broker_orders_authorized": False,
    "financial_metrics_eligible": False, "retrospective_labels_opened": False,
    "policy_promotion_eligible": False, "original_attempts_overwritten": False,
    "runtime_mechanics_changed": False, "unavailable_inputs_reclassified": False}
REASONS = {
    "unavailable_no_fresh_decision_quote": "no_reference_meeting_frozen_freshness_rule",
    "unavailable_exact_quote_request": "original_exact_quote_request_unavailable",
}
AVAILABLE_DISPOSITIONS = {"entry_submitted", "blocked_capacity",
    "blocked_campaign_entry_limit", "blocked_account_lock"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def seal(value):
    body = {k: v for k, v in value.items() if k != "content_sha256"}
    return {**body, "content_sha256": fingerprint(body)}


def checked(value):
    require(isinstance(value, dict) and value == seal(value), "content seal differs")
    return value


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False,
        allow_nan=False) + "\n").encode()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def read_json(raw, *, canonical=True, sealed=True):
    value = json.loads(raw, object_pairs_hook=unique_object)
    if sealed:
        checked(value)
    if canonical:
        require(encoded(value) == raw, "canonical document bytes differ")
    return value


def file_spec(path):
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def verified_zip(path, spec):
    require(file_spec(path) == {k: spec[k] for k in ("bytes", "sha256")},
        "archive bytes differ: " + path.name)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) and sorted(names) == sorted(spec["members"]),
            "archive member inventory differs")
        require(all(not n.startswith("/") and ".." not in Path(n).parts for n in names),
            "unsafe archive member")
        require(sum(i.file_size for i in archive.infolist()) <= 80_000_000,
            "unexpected uncompressed archive size")
        require(archive.testzip() is None, "archive CRC differs")
        return {name: archive.read(name) for name in names}


def registration(root):
    parent_path = root / f"research/strategy/{PARENT_ID}.json"
    parent = read_json(parent_path.read_bytes())
    parent_freeze = root / f"research/runtime/{PARENT_ID}/freeze-manifest.json"
    require(read_json(parent_freeze.read_bytes())["content_sha256"] == REGISTRATION,
        "original registration differs")
    pins = {**parent["frozen_parent_file_sha256"], **parent["implementation_file_sha256"]}
    for path, expected in pins.items():
        require(file_spec(root / path)["sha256"] == expected, "frozen parent file differs: " + path)
    return seal({"contract_id": ID, "artifact_type": "post_result_validation_plan_amendment",
        "parent_checkpoint_commit_sha": PARENT_COMMIT, "original_implementation_commit_sha": IMPLEMENTATION,
        "original_registration_content_sha256": REGISTRATION,
        "expected_runtime_content_sha256": RUNTIME, "expected_checker_content_sha256": CHECKER,
        "expected_binding_content_sha256": BINDING, "hosted_run_id": HOSTED_RUN,
        "hosted_artifact_id": HOSTED_ARTIFACT, "hosted_attempt": 1,
        "user_authorization": "Okay you may proceed with the next step without the local replay",
        "scope": "accept_existing_hosted_mechanical_replay_and_audit_input_coverage_only",
        "full_local_replay_required": False, "original_contract_rewritten": False,
        "hosted_success_known_before_amendment": True,
        "independent_checker_reused_not_reexecuted": True,
        "independent_fill_simulator_claimed": False,
        "required_population": {"paths": 12, "sessions": 360, "opportunity_references": 744,
            "unavailable_references": 162, "unique_unavailable_opportunities": 23},
        "required_saved_local_prefix_records": 20,
        "archive_specs": ARCHIVES,
        "input_file_specs": {str(p.relative_to(root)): file_spec(p) for p in
            (parent_path, parent_freeze, root / PROVENANCE, root / LOCAL_EVIDENCE)},
        "implementation_file_specs": {p: file_spec(root / p) for p in OWN_FILES},
        "next_gate": "separately_scope_unavailable_entry_reference_resolution_or_conditional_evaluation",
        **CLOSED})


def check_registration(root, external_sha):
    expected = registration(root)
    require(expected["content_sha256"] == external_sha, "external acceptance commitment differs")
    path = root / f"research/strategy/{ID}.json"
    require(path.read_bytes() == encoded(expected), "acceptance registration bytes differ")
    return expected


def number(value):
    require(isinstance(value, str), "exact account number must be a string")
    result = Decimal(value)
    require(result.is_finite(), "nonfinite account number")
    return result


def reconcile_close(opening, runtime, close, expected_gaps):
    state = close["account_state"]
    require(not opening["positions"] and not opening["pending_orders"]
        and not state["positions"] and not state["pending_orders"], "nonflat account state")
    require(runtime["unconfirmed_entry_order"] is None and runtime["active_original_window"] is None,
        "unfinished execution state")
    require(close["next_session_flat_cash_execution_ready"] is True,
        "next-session execution not ready")
    require(state["unresolved_inputs"] == opening["unresolved_inputs"] + expected_gaps
        and not any(g["blocks_next_session"] for g in state["unresolved_inputs"]),
        "unavailable history lost or blocking state present")
    gross, net, fees = (number(runtime[k]) for k in
        ("session_gross_realized_pnl_usd", "session_net_realized_pnl_usd", "session_fees_usd"))
    require(gross - fees == net and fees >= 0, "session net/fee arithmetic differs")
    for key, delta in (("equity_usd", net), ("buying_power_usd", net),
            ("cumulative_realized_pnl_usd", net), ("cumulative_fees_usd", fees)):
        require(number(state[key]) == number(opening[key]) + delta, "account carry differs: " + key)
    require(number(state["equity_usd"]) > 0 and number(state["buying_power_usd"]) > 0,
        "flat-cash continuation requires positive balances")


def audit_panel(runtime, binding):
    """Inspect already frozen results; emit counts and provenance, never P&L."""
    checked(runtime)
    checked(binding)
    require(runtime["source_bindings_content_sha256"] == binding["content_sha256"], "binding identity differs")
    paths, catalogs = runtime["paths"], binding["paths"]
    require([p["path_id"] for p in paths] == [p["path_id"] for p in catalogs]
        and len({p["path_id"] for p in paths}) == len(paths), "path catalog differs")
    opportunities = {o["opportunity_id"]: checked(o) for o in binding["opportunities"]}
    require(len(opportunities) == len(binding["opportunities"]), "duplicate source opportunity")
    totals, statuses, references, path_reports = Counter(), Counter(), defaultdict(list), []
    with localcontext() as context:
        context.prec = 60
        for path, catalog in zip(paths, catalogs):
            checked(path)
            sessions, slots = path["sessions"], catalog["sessions"]
            require(type(path["seed_application_count"]) is int and path["seed_application_count"] == 1,
                "account seed count differs")
            require(path["session_count"] == len(sessions) == len(slots), "session catalog differs")
            opening, previous, seen_gap, prefix, day_reports = path["initial_account_state"], None, False, 0, []
            require(opening["unresolved_inputs"] == [], "initial state already has unavailable history")
            for i, (pair, slot) in enumerate(zip(sessions, slots)):
                r, c = checked(pair["runtime"]), checked(pair["close"])
                checked(slot)
                require(r["path_id"] == c["path_id"] == path["path_id"] == slot["path_id"]
                    and r["session_id"] == c["session_id"] == slot["session_id"]
                    and c["session_index"] == slot["session_index"] == i
                    and c["trading_date"] == slot["trading_date"], "session identity or ordering differs")
                require(r["source_slot_content_sha256"] == c["source_slot_content_sha256"] == slot["content_sha256"]
                    and c["source_runtime_content_sha256"] == r["content_sha256"]
                    and c["previous_close_content_sha256"] == previous
                    and r["opening_account_state_sha256"] == fingerprint(opening), "close-chain commitment differs")
                require(c["seed_applied"] is (i == 0) and slot["seed_applied"] is (i == 0), "account reseeded")
                require(r["failure"] is None and r["blocked_before_execution"] is False
                    and r["complete_streams_verified"] is True
                    and r["historical_session_scheduler_executed"] is True, "incomplete or blocked runtime")
                expected = slot["opportunity_inputs"]
                require(len({o["opportunity_id"] for o in expected}) == len(expected), "duplicate slot opportunity")
                actual = r["opportunity_dispositions"]
                require([{k: v for k, v in o.items() if k != "disposition"} for o in actual] == expected,
                    "opportunity population, order or availability differs")
                gaps = []
                for o in actual:
                    require(o["opportunity_id"] in opportunities, "opportunity has no original binding")
                    entry = opportunities[o["opportunity_id"]]["entry"]
                    require(all(o[k] == entry[k] for k in
                        ("input_status", "reason", "availability_content_sha256")), "source availability differs")
                    require(o["input_status"] in {"available", "unavailable"}, "unsupported availability state")
                    if o["input_status"] == "unavailable":
                        require(o["disposition"] == "unavailable_input" and o["reason"] in REASONS,
                            "unavailable input reclassified")
                        gaps.append({"kind": "unavailable_input", **{k: o[k] for k in
                            ("opportunity_id", "availability_content_sha256", "reason")}, "blocks_next_session": False})
                        references[o["opportunity_id"]].append({"path_id": path["path_id"], "session_id": c["session_id"]})
                    else:
                        require(o["disposition"] in AVAILABLE_DISPOSITIONS,
                            "available input not processed with a frozen disposition")
                require(r["status"] == ("flat_complete_with_unavailable_inputs" if gaps else "flat_complete"),
                    "session completeness claim differs")
                reconcile_close(opening, r, c, gaps)
                if not seen_gap and not gaps:
                    prefix += 1
                day_reports.append({"session_id": c["session_id"], "trading_date": c["trading_date"],
                    "session_index": i, "status": r["status"], "opportunity_references": len(actual),
                    "unavailable_opportunity_ids": [g["opportunity_id"] for g in gaps],
                    "prior_unavailable_history_present": seen_gap,
                    "full_input_history_complete": not seen_gap and not gaps})
                seen_gap = seen_gap or bool(gaps)
                totals.update({"sessions": 1, "opportunity_references": len(actual), "unavailable_references": len(gaps)})
                statuses[r["status"]] += 1
                opening, previous = c["account_state"], c["content_sha256"]
            require(path["last_close_content_sha256"] == previous and path["path_complete"] is (not seen_gap),
                "path completion claim differs")
            path_reports.append({"path_id": path["path_id"], "sessions": day_reports,
                "session_count": len(sessions), "captured_execution_complete": True,
                "full_input_coverage_complete": not seen_gap, "full_coverage_prefix_sessions": prefix,
                "sessions_with_unavailable_inputs": sum(bool(s["unavailable_opportunity_ids"]) for s in day_reports),
                "unavailable_references": sum(len(s["unavailable_opportunity_ids"]) for s in day_reports),
                "first_unavailable_date": next((s["trading_date"] for s in day_reports if s["unavailable_opportunity_ids"]), None),
                "financial_metrics_eligible": False})
    gap_details = []
    for oid, refs in sorted(references.items()):
        source = opportunities[oid]
        gap_details.append({"opportunity_id": oid, "symbol": source["activation"]["symbol"],
            "decision_at": source["source_decision"]["decision_at"], "reason": source["entry"]["reason"],
            "category": REASONS[source["entry"]["reason"]], "reference_count": len(refs), "references": refs,
            "availability_content_sha256": source["entry"]["availability_content_sha256"],
            "quote_request_evidence_sha256": source["entry"]["quote_request_evidence_sha256"],
            "status_request_evidence_sha256": source["entry"]["status_request_evidence_sha256"],
            "no_trade_inferred": False, "new_source_request_authorized": False})
    return {"paths": path_reports, "unavailable_opportunities": gap_details,
        "population": {"paths": len(paths), **dict(totals), "unique_unavailable_opportunities": len(gap_details)},
        "session_status_counts": dict(sorted(statuses.items())),
        "reason_unique_opportunity_counts": dict(sorted(Counter(g["reason"] for g in gap_details).items())),
        "reason_reference_counts": dict(sorted(Counter({reason: sum(g["reference_count"] for g in gap_details
            if g["reason"] == reason) for reason in REASONS}).items())),
        "captured_execution_complete": True, "full_input_coverage_complete": not gap_details,
        "account_backtest_complete": False, "cash_fee_and_carry_reconciled": True}


def verify(root, hosted_zip, binding_zip, external_sha):
    contract = check_registration(root, external_sha)
    provenance = json.loads((root / PROVENANCE).read_bytes(), object_pairs_hook=unique_object)
    run, jobs, artifacts = provenance["run"], provenance["jobs"], provenance["artifacts"]
    require(run["id"] == HOSTED_RUN and run["head_sha"] == IMPLEMENTATION and run["run_attempt"] == 1
        and run["status"] == "completed" and run["conclusion"] == "success", "hosted run differs")
    require(len(jobs) == 1 and jobs[0]["id"] == 102501424811 and jobs[0]["conclusion"] == "success"
        and all(s["status"] == "completed" and s["conclusion"] == "success" for s in jobs[0]["steps"]),
        "hosted job/steps incomplete")
    require(len(artifacts) == 1 and artifacts[0]["id"] == HOSTED_ARTIFACT
        and artifacts[0]["digest"] == "sha256:" + ARCHIVES["hosted"]["sha256"], "hosted artifact differs")
    hosted = verified_zip(hosted_zip, ARCHIVES["hosted"])
    original = verified_zip(binding_zip, ARCHIVES["binding"])
    local = verified_zip(root / LOCAL_EVIDENCE, ARCHIVES["local"])
    docs = {name: read_json(raw) for name, raw in hosted.items() if name.endswith(".json")}
    runtime, report, freeze = (docs["account-replay/" + name] for name in
        ("account-replay.json", "independent-verification.json", "freeze-manifest.json"))
    require(runtime["content_sha256"] == RUNTIME and report["content_sha256"] == CHECKER
        and report["runtime_content_sha256"] == RUNTIME and report["verification_passed"] is True,
        "original independent report does not accept expected runtime")
    require(runtime["registration_freeze_content_sha256"] == report["registration_freeze_content_sha256"] == REGISTRATION,
        "runtime/checker registration differs")
    require(report["account_backtest_complete"] is False and report["financial_metrics_eligible"] is False
        and report["retrospective_labels_opened"] is False, "parent financial boundary differs")
    spec = freeze["file_inventory"]["account-replay.json"]
    require(spec == {"bytes": len(hosted["account-replay/account-replay.json"]),
        "sha256": hashlib.sha256(hosted["account-replay/account-replay.json"]).hexdigest()}
        and freeze["document_content_sha256"] == {"account-replay.json": RUNTIME}, "native freeze differs")
    binding = read_json(original["source-bindings.json"])
    require(binding["content_sha256"] == BINDING, "original binding differs")
    coverage = audit_panel(runtime, binding)
    require(coverage["population"] == contract["required_population"], "registered population differs")
    require(report["totals"]["blocked_sessions"] == report["totals"]["input_failure_sessions"] == 0
        and report["totals"]["executed_sessions"] == contract["required_population"]["sessions"],
        "checker completion summary differs")
    rows = hosted["account-replay-progress.jsonl"].splitlines(keepends=True)
    pairs = [(p["path_id"], s) for p in runtime["paths"] for s in p["sessions"]]
    require(len(rows) == len(pairs), "progress population differs")
    for raw, (path_id, pair) in zip(rows, pairs):
        row = read_json(raw, canonical=False)
        require(row["path_id"] == path_id and row["session"] == pair and row["final_panel"] is False
            and row["registration_freeze_content_sha256"] == REGISTRATION, "progress differs from final runtime")
    prefix = local["account-replay-progress.jsonl"].splitlines(keepends=True)
    prefix_count = contract["required_saved_local_prefix_records"]
    require(len(prefix) == prefix_count and prefix == rows[:prefix_count]
        and local["account-replay-attempt.json"] == hosted["account-replay-attempt.json"], "saved local prefix differs")
    return seal({"contract_id": ID, "artifact_type": "hosted_acceptance_and_input_coverage_audit",
        "acceptance_contract_content_sha256": external_sha, "runtime_content_sha256": RUNTIME,
        "original_independent_checker_content_sha256": CHECKER,
        "source_bindings_content_sha256": BINDING, "hosted_run_id": HOSTED_RUN,
        "hosted_artifact_id": HOSTED_ARTIFACT, "hosted_runtime_accepted": True,
        "full_local_replay_required": False, "local_attempt_status": "preserved_incomplete",
        "local_saved_records_byte_identical_to_hosted_prefix": prefix_count,
        "exact_archive_inventory_crc_and_bytes_verified": True,
        "original_independent_checker_passed": True, "independent_fill_simulation": False,
        "original_frozen_boundary_flags_preserved": True,
        "archive_specs": ARCHIVES, "native_file_inventory": {n: {"bytes": len(b),
            "sha256": hashlib.sha256(b).hexdigest()} for n, b in sorted(hosted.items())},
        **coverage, "next_gate": contract["next_gate"], **CLOSED})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--build-registration", action="store_true")
    modes.add_argument("--check-registration", action="store_true")
    parser.add_argument("--hosted-zip", type=Path)
    parser.add_argument("--binding-zip", type=Path)
    parser.add_argument("--expected-contract-sha256")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    from run_offline_python_v13 import deny_external_io
    sys.addaudithook(deny_external_io)
    root = Path(__file__).resolve().parents[1]
    if args.build_registration or args.check_registration:
        require(args.hosted_zip is None and args.binding_zip is None and args.output is None,
            "archive and output arguments require artifact verification")
    if args.build_registration:
        result = registration(root)
        with (root / f"research/strategy/{ID}.json").open("xb") as handle:
            handle.write(encoded(result))
    elif args.check_registration:
        result = check_registration(root, args.expected_contract_sha256)
    else:
        require(args.output is not None and not args.output.exists(), "new output file required")
        require(args.hosted_zip is not None and args.binding_zip is not None, "both immutable archives required")
        result = verify(root, args.hosted_zip, args.binding_zip, args.expected_contract_sha256)
        with args.output.open("xb") as handle:
            handle.write(encoded(result))
    print(json.dumps({"contract_id": ID, "content_sha256": result["content_sha256"],
        "hosted_runtime_accepted": result.get("hosted_runtime_accepted", False),
        "financial_metrics_eligible": False, "replay_executed": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
