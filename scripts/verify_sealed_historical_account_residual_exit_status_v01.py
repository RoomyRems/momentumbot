"""Registered verifier-only correction for preserved residual cancellation statuses.

The original failed checker and all runtime/producer inputs remain immutable.
Only the zero-fill status expectation changes, using original native evidence.
This does not simulate fills or reproduce the account runtime.
"""
import argparse
import hashlib
import json
from decimal import localcontext
from pathlib import Path

import verify_sealed_historical_account_residual_exit_v01 as frozen
from diagnose_sealed_historical_account_residual_exit_v01 import (
    RUNTIME, RUNTIME_FILE, cancellations, quote_lifecycle,
)
from verify_sealed_historical_account_residual_exit_v01 import (
    ID, PARENT_RUNTIME, PARENT_FILE, TAIL, MINUTE, parent, References,
    OriginalEvidence, checked, read, require, digest, _pinned_file,
    verify_decimal_snapshot, verify_path, verify_waiting, verify_parent_prefix,
    eligible, evidence, terminal_reason,
)

CHILD_ID = "sealed-historical-account-residual-exit-status-verification-v0.1"
PARENT_COMMIT = "89c83f04de92cff6d7ce8d38ee30b9b280dabf56"
PARENT_TREE = "334eadc8380301f613945c1d6a8a35e4bbcfa121"
ORIGINAL_CONTRACT = "2f73c36939cd418b781838772cc2d9a792ce7df49a190f209edbec9c2dbdbd1b"
ORIGINAL_REGISTRATION = "33ced4d6e2069f36a277b3b2025f38e07e2d7a3e9eeecd031345400ed6b54dae"
RUNTIME_FREEZE_FILE = "cbd3ed8693ec54febaa9855b64d8869413605bffce5291d67c69ba8686caff0b"
OWN_FILES = (
    "scripts/verify_sealed_historical_account_residual_exit_status_v01.py",
    "tests/test_sealed_historical_account_residual_exit_status_v01.py",
    ".github/workflows/sealed-historical-account-residual-exit-status-v01.yml",
)
ADDITIONAL_PARENTS = (
    f"research/strategy/{ID}.json",
    f"research/runtime/{ID}/freeze-manifest.json",
    f"research/runtime/{ID}/residual-exit-mechanics.json",
    "scripts/diagnose_sealed_historical_account_residual_exit_v01.py",
    "tests/test_sealed_historical_account_residual_exit_diagnostic_v01.py",
    "docs/research/sealed_historical_account_residual_exit_cancellation_diagnostic_v01.md",
    "research/data-audits/sealed-historical-account-residual-exit-v0.1-cancellation-diagnosis.json",
    "research/data-audits/sealed-historical-account-residual-exit-v0.1-verification-failure-diagnosis.json",
    "scripts/run_offline_python_v13.py",
)
ARCHIVES = {
    "runtime": {"artifact_id": 10085178783, "run_id": 34295994393, "bytes": 1119624,
        "sha256": "079bb67f53d4fe9151522d995c127da109c11e19d1a1638be3e53fffbdb0eb76"},
    "binding": {"artifact_id": 10060984490, "bytes": 377229,
        "sha256": "2577dfdccdee948c9241d3489737e0dac40cf3c97ad826ead9500c095e55d94a"},
    "parent": {"artifact_id": 10080992514, "bytes": 1027787,
        "sha256": "39c6a09db77889dc28968121458a03154261880ca24d408e940f63c27cac7c8a"},
    "management": {"artifact_id": 10028253493, "bytes": 43591721,
        "sha256": "e6ae822301440e3c0d183546b472e5b6f4e0f50d6e4f1b67178ba6bf46e382e0"},
    "exit": {"artifact_id": 10037358910, "bytes": 30747584,
        "sha256": "94877d03a9e91372f9a36d68275b6c44421139bc5c4eab0f26403c26f26aed80"},
}
BOUNDARIES = {
    "historical_replay_rerun": False,
    "account_runtime_reproduced": False,
    "independent_fill_simulation": False,
    "original_code_or_artifacts_modified": False,
    "provider_requests_authorized": False,
    "broker_orders_authorized": False,
    "financial_metrics_eligible": False,
    "account_backtest_complete": False,
    "retrospective_labels_opened": False,
    "policy_promotion_eligible": False,
    "overnight_execution_authorized": False,
}


def cancellation_status(entry, order, filled, data):
    """Classify recorded cancellation; positive fills retain the original rule."""
    require(type(filled) is int and 0 <= filled < order["quantity"],
        "cancellation filled quantity differs")
    if filled:
        return "partially_filled_cancelled"
    proof = quote_lifecycle(data["tape"], data["window"], order, entry["scenario_id"])
    if proof["active_candidate_count"] == 0:
        return "unavailable_no_fresh_quote"
    if proof["active_nonhalted_candidate_count"] == 0:
        return "halted_cancelled"
    return "cancelled_unfilled"


def verify_residual(runtime, resolve):
    snapshot = runtime["reconciliation_snapshot"]
    counts = {"residual_ready": 0, "residual_proposals": 0, "residual_submissions": 0,
        "residual_expiries": 0, "residual_budget_exhaustions": 0}
    if snapshot is None:
        return counts
    entries = {j["execution_evidence"]["content_sha256"]: j["execution_evidence"]
        for j in snapshot["journal"] if j["fee_application"]["trade"]["side"] == "buy"}
    by_oid = {e["opportunity_id"]: e for e in entries.values()}
    orders = {}
    for event in runtime["events"]:
        if event["event_type"] == "sell_submitted":
            orders.setdefault(event["opportunity_id"], []).append(event)
    sells = [j["execution_evidence"] for j in snapshot["journal"]
        if j["fee_application"]["trade"]["side"] == "sell"]
    def sold(entry, at):
        return [s for s in sells if s["entry_fill_id"] == entry["fill_id"] and s["fill_time_ns"] <= at]
    def quantity(entry, at):
        return entry["quantity"] - sum(s["quantity"] for s in sold(entry, at))
    def cancel(entry, order, ack):
        checked(ack)
        fills = [s for s in sold(entry, order["cancel_ack_ts_ns"]) if s["order_id"] == order["order_id"]]
        filled = sum(s["quantity"] for s in fills)
        require(ack["event_type"] == "sell_cancel_acknowledged" and ack["order_id"] == order["order_id"]
            and ack["timestamp_ns"] == order["cancel_ack_ts_ns"]
            and ack["cancelled_quantity"] == order["quantity"] - filled > 0
            and ack["execution_status"] == cancellation_status(entry, order, filled, resolve(entry["opportunity_id"])),
            "residual cancellation witness differs")
    chains, states = {}, {}
    for event in snapshot.get("exit_residual_events", []):
        checked(event)
        eid, at, kind = event["entry_content_sha256"], event["timestamp_ns"], event["event_type"]
        require(eid in entries, "residual event has no confirmed entry")
        entry = entries[eid]
        chain = chains.setdefault(eid, [])
        require(event["contract_id"] == ID and event["opportunity_id"] == entry["opportunity_id"]
            and event["sequence"] == len(chain) and event["previous_event_sha256"] == (chain[-1]["content_sha256"] if chain else None)
            and (not chain or at >= chain[-1]["timestamp_ns"]), "residual event chain differs")
        chain.append(event)
        data = resolve(entry["opportunity_id"])
        window = data["window"]
        require(entry["fill_time_ns"] < at < window["end_ns"], "residual clock outside entry/window")
        remaining = quantity(entry, at - int(kind in {"residual_proposed", "residual_submitted"}))
        target = entry["quantity"] // 2
        target_filled = sum(s["quantity"] for s in sold(entry, at - 1) if s["reason"] == "first_target")
        stop = float(entry["fill_price"]) if target and target == target_filled else entry["initial_stop_price"]
        require(event["remaining_quantity"] == remaining > 0 and event["active_stop_price"] == stop
            and event["full_exit_attempted"] is True, "residual confirmed shares or stop differs")
        terminal = [e for e in orders.get(entry["opportunity_id"], []) if e["reason"] != "first_target"]
        require(1 <= len(terminal) <= 2, "residual terminal order budget differs")
        if kind == "residual_ready":
            require(eid not in states and event["residual_attempts"] == 0, "duplicate or consumed residual authority")
            context = checked(event["context"])
            require(set(context) == {"prior_submission_intent", "prior_order_id", "cancel_acknowledgement", "terminal_attempt_number", "content_sha256"}
                and context["terminal_attempt_number"] == 2, "residual context scope differs")
            intent = checked(context["prior_submission_intent"])
            prior = terminal[0]
            require(context["prior_order_id"] == prior["order"]["order_id"] == "exit-" + intent["content_sha256"]
                and intent["entry_content_sha256"] == eid and intent["decision_ts_ns"] == prior["at_ns"]
                and intent["reason"] == prior["reason"] and intent["quantity"] == prior["order"]["quantity"]
                and "residual_exit" not in intent, "residual prior submitted signal differs")
            cancel(entry, prior["order"], context["cancel_acknowledgement"])
            require(at == context["cancel_acknowledgement"]["timestamp_ns"]
                and (event["known_at_ns"] > at or (event["known_at_ns"] == at and event["clock_phase"] == 2)),
                "residual acknowledged before feedback")
            states[eid] = {"context": context, "events": [], "data": data, "entry": entry}
            counts["residual_ready"] += 1
            continue
        require(eid in states, "residual event without acknowledged authority")
        state = states[eid]
        state["events"].append(event)
        if kind == "residual_budget_exhausted":
            require(len(terminal) == 2 and event["residual_attempts"] == 1, "residual budget exhaustion differs")
            cancel(entry, terminal[1]["order"], event["cancel_acknowledgement"])
            require(at == terminal[1]["order"]["cancel_ack_ts_ns"]
                and (event["known_at_ns"] > at or (event["known_at_ns"] == at and event["clock_phase"] == 2)),
                "residual budget exhausted before acknowledgement")
            counts["residual_budget_exhaustions"] += 1
            continue
        require(event["context"] == state["context"], "residual authority changed")
        if kind == "residual_proposed":
            require(event["residual_attempts"] == 0, "residual proposal consumed budget")
            counts["residual_proposals"] += 1
        elif kind == "residual_submitted":
            require(event["residual_attempts"] == 1 and len(terminal) == 2
                and event["order"] == terminal[1]["order"], "residual submission order or count differs")
            intent = checked(event["intent"])
            require(intent["residual_exit"] == state["context"] and intent["decision_ts_ns"] == at
                and event["order"]["order_id"] == "exit-" + intent["content_sha256"]
                and intent["quantity"] == remaining == event["order"]["quantity"], "residual order signal or quantity differs")
            require(References(data["tape"]).at(window, at) is not None, "residual submitted without fresh reference")
            counts["residual_submissions"] += 1
        else:
            require(kind == "residual_expired" and event["residual_attempts"] == 0
                and at + TAIL >= window["end_ns"] and event["original_window_end_ns"] == window["end_ns"],
                "residual expiry differs")
            counts["residual_expiries"] += 1
    for eid, state in states.items():
        entry, data, context = state["entry"], state["data"], state["context"]
        events = state["events"]
        proposals = [e for e in events if e["event_type"] == "residual_proposed"]
        submissions = [e for e in events if e["event_type"] == "residual_submitted"]
        expiries = [e for e in events if e["event_type"] == "residual_expired"]
        exhausted = [e for e in events if e["event_type"] == "residual_budget_exhausted"]
        require(len(proposals) <= 1 and len(submissions) <= 1 and len(expiries) <= 1 and len(exhausted) <= 1,
            "repeated residual transition")
        ack = context["cancel_acknowledgement"]["timestamp_ns"]
        first = next((r for r in data["trades"] if ack < r["timestamp_ns"]
            and r["timestamp_ns"] + TAIL < data["window"]["end_ns"] and eligible(r["record"])), None)
        if proposals:
            proposal = proposals[0]
            intent = checked(proposal["intent"])
            require(first is not None and proposal["timestamp_ns"] == first["timestamp_ns"]
                and intent["trade_evidence"] == evidence(first, "sip_transactions"), "not first eligible post-ack residual print")
            reason = terminal_reason(entry, data, runtime, first)
            red = next(({"signal_ts_ns": b["timestamp_ns"] + MINUTE, "evidence": evidence(b, "raw_sip_1m_bars")}
                for b in data["bars"] if entry["fill_time_ns"] < b["timestamp_ns"] + MINUTE <= min(first["timestamp_ns"], data["window"]["signal_end_ns"])
                and b["record"]["c"] < b["record"]["o"]), None)
            expected = parent.seal({**{k: entry[k] for k in ("opportunity_id", "path_id", "session_id", "scenario_id")},
                "entry_content_sha256": eid, "decision_ts_ns": first["timestamp_ns"], "reason": reason,
                "quantity": proposal["remaining_quantity"], "trade_evidence": evidence(first, "sip_transactions"),
                "red_signal": red if reason == "first_red_candle" else None, "residual_exit": context})
            require(intent == expected and reason is not None, "residual signal priority or identity differs")
            if submissions:
                actual = submissions[0]
                if actual["intent"] != intent:
                    require(any(w["event_type"] == "wait_submitted" and w["submission_intent"] == actual["intent"]
                        and w["original_signal_content_sha256"] == intent["content_sha256"]
                        for w in snapshot.get("exit_wait_events", [])), "delayed residual order is not bound to wait evidence")
            else:
                require(runtime["failure"] is not None or any(w["event_type"] == "wait_expired"
                    and w["original_signal_content_sha256"] == intent["content_sha256"]
                    for w in snapshot.get("exit_wait_events", [])), "residual proposal omitted submission or preserved wait")
        else:
            require(not submissions and (runtime["failure"] is not None or (first is None and len(expiries) == 1)),
                "eligible residual proposal omitted")
        if submissions:
            order = submissions[0]["order"]
            if runtime["complete_streams_verified"] and quantity(entry, order["cancel_ack_ts_ns"]) > 0:
                require(len(exhausted) == 1, "residual exhausted remainder not recorded")
    # Omitting the entire audit must not conceal either authority or replacement.
    for oid, entry in by_oid.items():
        terminal = [e for e in orders.get(oid, []) if e["reason"] != "first_target"]
        if terminal:
            ack = terminal[0]["order"]["cancel_ack_ts_ns"]
            if runtime["complete_streams_verified"] and quantity(entry, ack) > 0:
                require(entry["content_sha256"] in states, "acknowledged residual authority omitted")
            if len(terminal) == 2:
                require(entry["content_sha256"] in states and any(e["event_type"] == "residual_submitted"
                    for e in states[entry["content_sha256"]]["events"]), "second terminal lacks residual authority")
    return counts


def verify_original_runtime(root, runtime_root, binding_root, parent_runtime_root, expected_runtime_sha, paths):
    contract = read(root / f"research/strategy/{ID}.json")
    require(contract["contract_id"] == ID and contract["parent_runtime_content_sha256"] == PARENT_RUNTIME
        and contract["parent_runtime_file_sha256"] == PARENT_FILE, "residual parent identity differs")
    for path, sha in {**contract["frozen_parent_file_sha256"], **contract["implementation_file_sha256"]}.items():
        require(hashlib.sha256((root / path).read_bytes()).hexdigest() == sha, "frozen implementation/parent differs: " + path)
    registration_root = root / f"research/runtime/{ID}"
    registration = read(registration_root / "freeze-manifest.json")
    require(registration["contract_id"] == ID and registration["contract_content_sha256"] == contract["content_sha256"], "registration identity differs")
    for name, spec in registration["file_inventory"].items():
        value = _pinned_file(registration_root / name, spec["sha256"])
        require((registration_root / name).stat().st_size == spec["bytes"]
            and value["content_sha256"] == registration["document_content_sha256"][name], "registration inventory differs")
    manifest = _pinned_file(binding_root / "source-bindings.json", parent.BOUND_FILE)
    require(manifest["content_sha256"] == parent.BOUND, "original binding differs")
    old = _pinned_file(parent_runtime_root / "account-replay.json", PARENT_FILE)
    require(old["content_sha256"] == PARENT_RUNTIME, "parent runtime differs")
    frozen = read(runtime_root / "freeze-manifest.json")
    parent.boundaries(frozen)
    require(frozen["contract_id"] == ID and frozen["contract_content_sha256"] == contract["content_sha256"]
        and set(frozen["file_inventory"]) == {"account-replay.json"}, "runtime freeze scope differs")
    spec = frozen["file_inventory"]["account-replay.json"]
    result = _pinned_file(runtime_root / "account-replay.json", spec["sha256"])
    require((runtime_root / "account-replay.json").stat().st_size == spec["bytes"], "runtime byte length differs")
    require(result["content_sha256"] == expected_runtime_sha == frozen["document_content_sha256"]["account-replay.json"], "runtime commitment differs")
    require(result["contract_id"] == ID and result["parent_runtime_content_sha256"] == PARENT_RUNTIME
        and result["registration_freeze_content_sha256"] == registration["content_sha256"], "runtime authority differs")
    require(result["source_bindings_content_sha256"] == parent.BOUND and result["source_archives"] == manifest["source_archives"], "source authority differs")
    parent.boundaries(result)
    programs = read(root / f"research/runtime/{parent.ID}/source-programs.json")["programs"]
    require(len(programs) == len(result["paths"]) == len(old["paths"]) == 12, "all original paths required")
    counts = []
    sources = OriginalEvidence(root, manifest, paths, contract["source_archives"])
    try:
        with localcontext() as context:
            context.prec = 60
            for program, before, after in zip(programs, old["paths"], result["paths"]):
                totals = {"path_id": after["path_id"], **verify_path(program, after, manifest)}
                verify_parent_prefix(before, after)
                for pair in after["sessions"]:
                    runtime = pair["runtime"]
                    if runtime["reconciliation_snapshot"] is not None:
                        verify_decimal_snapshot(runtime["reconciliation_snapshot"])
                    for key, count in verify_residual(runtime, sources).items():
                        totals[key] = totals.get(key, 0) + count
                    for key, count in verify_waiting(runtime, sources).items():
                        totals[key] = totals.get(key, 0) + count
                counts.append(totals)
    finally:
        sources.close()
    totals = {k: sum(c[k] for c in counts) for k in counts[0] if k != "path_id"}
    require((totals["sessions"], totals["opportunity_references"], totals["unavailable_references"]) == (360, 744, 162), "original population differs")
    return parent.seal({"contract_id": ID, "verification_passed": True,
        "runtime_content_sha256": expected_runtime_sha, "source_bindings_content_sha256": parent.BOUND,
        "parent_runtime_content_sha256": PARENT_RUNTIME, "registration_freeze_content_sha256": registration["content_sha256"],
        "paths": counts, "totals": totals, "parent_chronology_checks_preserved_except_registered_two_terminal_ceiling": True,
        "original_waiting_signals_and_first_eligible_fresh_prints_verified": True,
        "pre_residual_parent_event_prefix_unchanged": True,
        "bounded_residual_cancel_signal_quantity_and_earliest_print_verified": True, "independent_fill_simulation": False,
        "financial_metrics_eligible": False, "account_backtest_complete": False, "retrospective_labels_opened": False})


def encoded_document(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def file_spec(path):
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def contract_path(root):
    return root / f"research/strategy/{CHILD_ID}.json"


def freeze_path(root):
    return root / f"research/runtime/{CHILD_ID}/freeze-manifest.json"


def registration_documents(root):
    original = read(root / f"research/strategy/{ID}.json")
    original_freeze = read(root / f"research/runtime/{ID}/freeze-manifest.json")
    require(original["content_sha256"] == ORIGINAL_CONTRACT
        and original_freeze["content_sha256"] == ORIGINAL_REGISTRATION,
        "consumed original registration differs")
    pins = {**original["frozen_parent_file_sha256"], **original["implementation_file_sha256"]}
    require(len(pins) == 270, "consumed original pin inventory differs")
    for path, sha in pins.items():
        require(file_spec(root / path)["sha256"] == sha, "consumed parent differs: " + path)
    for path in ADDITIONAL_PARENTS:
        sha = file_spec(root / path)["sha256"]
        require(path not in pins or pins[path] == sha, "conflicting parent pin")
        pins[path] = sha
    contract = parent.seal({
        "schema_version": 1, "contract_id": CHILD_ID,
        "artifact_type": "post_diagnosis_verifier_only_registration",
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "runtime_contract_id": ID, "original_contract_content_sha256": ORIGINAL_CONTRACT,
        "original_registration_freeze_content_sha256": ORIGINAL_REGISTRATION,
        "runtime_content_sha256": RUNTIME, "runtime_file_sha256": RUNTIME_FILE,
        "runtime_freeze_file_sha256": RUNTIME_FREEZE_FILE,
        "parent_runtime_content_sha256": PARENT_RUNTIME, "parent_runtime_file_sha256": PARENT_FILE,
        "source_bindings_content_sha256": parent.BOUND,
        "source_archives": ARCHIVES, "frozen_parent_file_sha256": pins,
        "implementation_file_sha256": {path: file_spec(root / path)["sha256"] for path in OWN_FILES},
        "hypothesis": "derive_zero_fill_cancellation_status_from_original_active_quote_lifecycle",
        "scope": "same_stored_runtime_with_all_other_frozen_checker_predicates_preserved",
        "prior_failure_known_before_registration": True,
        "original_checker_failure_preserved": "residual cancellation witness differs",
        "required_population": {"paths": 12, "sessions": 360,
            "opportunity_references": 744, "unavailable_references": 162},
        "status_rules": {
            "positive_confirmed_fills": "partially_filled_cancelled",
            "zero_fills_no_fresh_active_quote": "unavailable_no_fresh_quote",
            "zero_fills_all_active_quotes_halted": "halted_cancelled",
            "zero_fills_with_active_nonhalted_quote": "cancelled_unfilled",
        },
        "attempt_policy": "publish_before_historical_verification_preserve_every_attempt_and_new_failure",
        "next_gate": "verify_stored_runtime_locally_and_hosted_then_register_remaining_blockers",
        **BOUNDARIES,
    })
    raw = encoded_document(contract)
    freeze = parent.seal({
        "contract_id": CHILD_ID, "artifact_type": "verifier_registration_freeze",
        "contract_content_sha256": contract["content_sha256"],
        "file_inventory": {f"research/strategy/{CHILD_ID}.json":
            {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}},
        **BOUNDARIES,
    })
    return contract, freeze


def build_registration(root):
    contract, freeze = registration_documents(root)
    contract_path(root).parent.mkdir(parents=True, exist_ok=True)
    freeze_path(root).parent.mkdir(parents=True, exist_ok=True)
    # Draft-only writer: an existing registration is never overwritten.
    with contract_path(root).open("xb") as handle:
        handle.write(encoded_document(contract))
    with freeze_path(root).open("xb") as handle:
        handle.write(encoded_document(freeze))
    return freeze


def check_registration(root, expected_sha):
    contract, freeze = registration_documents(root)
    require(freeze["content_sha256"] == expected_sha, "external registration commitment differs")
    require(contract_path(root).read_bytes() == encoded_document(contract)
        and freeze_path(root).read_bytes() == encoded_document(freeze),
        "registered verifier files or metadata differ")
    return contract, freeze


def verify_registered(root, runtime_root, binding_root, parent_runtime_root, paths, expected_sha):
    _, registration = check_registration(root, expected_sha)
    result = _pinned_file(runtime_root / "account-replay.json", RUNTIME_FILE)
    require(result["content_sha256"] == RUNTIME, "fixed stored runtime differs")
    _pinned_file(runtime_root / "freeze-manifest.json", RUNTIME_FREEZE_FILE)
    report = verify_original_runtime(root, runtime_root, binding_root, parent_runtime_root, RUNTIME, paths)
    status_counts = {}
    for row in cancellations(result):
        status = row["acknowledgement"]["execution_status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    return parent.seal({
        **{k: v for k, v in report.items() if k not in {"content_sha256", "contract_id",
            "registration_freeze_content_sha256"}},
        "contract_id": CHILD_ID, "artifact_type": "stored_runtime_verification",
        "runtime_contract_id": ID,
        "registration_freeze_content_sha256": registration["content_sha256"],
        "original_registration_freeze_content_sha256": ORIGINAL_REGISTRATION,
        "runtime_file_sha256": RUNTIME_FILE,
        "all_original_checks_preserved_except_source_derived_zero_fill_status": True,
        "source_derived_cancellation_status_verified": True,
        "cancellation_status_counts": status_counts,
        **BOUNDARIES,
    })


def run_attempt(root, runtime_root, binding_root, parent_runtime_root, paths, expected_sha, output_root):
    check_registration(root, expected_sha)
    output_root.mkdir(parents=True, exist_ok=False)
    receipt = parent.seal({
        "contract_id": CHILD_ID, "artifact_type": "stored_runtime_verification_attempt",
        "registration_freeze_content_sha256": expected_sha,
        "runtime_content_sha256": RUNTIME, "runtime_file_sha256": RUNTIME_FILE,
        "source_archives": ARCHIVES, "existing_output_root_must_not_be_reused": True,
        **BOUNDARIES,
    })
    with (output_root / "attempt.json").open("xb") as handle:
        handle.write(encoded_document(receipt))
    try:
        report = verify_registered(root, runtime_root, binding_root, parent_runtime_root, paths, expected_sha)
        with (output_root / "verification.json").open("xb") as handle:
            handle.write(encoded_document(report))
        freeze = parent.seal({
            "contract_id": CHILD_ID, "artifact_type": "stored_runtime_verification_freeze",
            "registration_freeze_content_sha256": expected_sha,
            "runtime_content_sha256": RUNTIME, "verification_passed": True,
            "document_content_sha256": {"attempt.json": receipt["content_sha256"],
                "verification.json": report["content_sha256"]},
            "file_inventory": {name: file_spec(output_root / name)
                for name in ("attempt.json", "verification.json")},
            **BOUNDARIES,
        })
        with (output_root / "freeze-manifest.json").open("xb") as handle:
            handle.write(encoded_document(freeze))
        return report
    except BaseException as exc:
        failure = parent.seal({
            "contract_id": CHILD_ID, "artifact_type": "stored_runtime_verification_failure",
            "attempt_content_sha256": receipt["content_sha256"],
            "registration_freeze_content_sha256": expected_sha,
            "runtime_content_sha256": RUNTIME, "verification_passed": False,
            "error_type": type(exc).__name__, "error": str(exc), **BOUNDARIES,
        })
        with (output_root / "failure.json").open("xb") as handle:
            handle.write(encoded_document(failure))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--build-registration", action="store_true")
    mode.add_argument("--check-registration", action="store_true")
    parser.add_argument("--expected-registration-sha256")
    for key in ("runtime-root", "binding-root", "parent-runtime-root",
                "management-zip", "exit-zip", "output-root"):
        parser.add_argument("--" + key, type=Path)
    args = parser.parse_args()
    import sys
    from run_offline_python_v13 import deny_external_io
    sys.addaudithook(deny_external_io)
    root = Path(__file__).resolve().parents[1]
    if args.build_registration:
        print(json.dumps(build_registration(root), indent=2, sort_keys=True))
        return
    expected = args.expected_registration_sha256
    if args.check_registration:
        if expected is None:
            expected = read(freeze_path(root))["content_sha256"]
        _, freeze = check_registration(root, expected)
        print(json.dumps({"registration_verified": True,
            "registration_freeze_content_sha256": freeze["content_sha256"],
            **BOUNDARIES}, indent=2, sort_keys=True))
        return
    require(expected is not None, "external registration commitment required")
    require(all(getattr(args, key) is not None for key in (
        "runtime_root", "binding_root", "parent_runtime_root",
        "management_zip", "exit_zip", "output_root")), "original evidence and new output root required")
    report = run_attempt(root, args.runtime_root, args.binding_root, args.parent_runtime_root,
        {"management": args.management_zip, "exit": args.exit_zip}, expected, args.output_root)
    print(json.dumps({k: v for k, v in report.items() if k != "paths"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
