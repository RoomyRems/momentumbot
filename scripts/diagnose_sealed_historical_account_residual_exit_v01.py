"""Post-outcome diagnosis of the preserved residual cancellation-check failure.

This is an evidence diagnostic, not a repaired verifier or a replay runner.
It preserves the original failure and independently checks the native quote gap
behind the rejected no-fresh-quote cancellation status. It cannot open any gate.
"""
import argparse
from bisect import bisect_left, bisect_right
from collections import Counter
import json
from pathlib import Path

import verify_sealed_historical_account_residual_exit_v01 as frozen

ID = "sealed-historical-account-residual-exit-cancellation-diagnostic-v0.1"
RUNTIME = "21bd9efa65c5c5776242bb9a6a53d28c134aefe31ed7da00d389402e29f3efba"
RUNTIME_FILE = "90f5a02dacc26eec03e8aacb5758150c0efc8b6a9b56d9c1d4eb7f5d7287c716"
EXPECTED_ERROR = "residual cancellation witness differs"
MS = 1_000_000
# Exact frozen execution policies; no alternative parameter is accepted.
POLICIES = {
    "l1-conservative-v0.1": (100, 100, 250, 100),
    "l1-stress-v0.1": (250, 50, 150, 150),
}


def quote_lifecycle(tape, window, order, scenario):
    """Reconstruct quote eligibility only; do not simulate or validate fills."""
    delay, max_age, lifetime, cancel_delay = POLICIES[scenario]
    decision = order["decision_ts_ns"]
    arrival = decision + delay * MS
    requested, ack = arrival + lifetime * MS, arrival + (lifetime + cancel_delay) * MS
    frozen.require((order["arrival_ts_ns"], order["cancel_requested_ts_ns"], order["cancel_ack_ts_ns"])
        == (arrival, requested, ack), "order clocks differ from frozen policy")
    start, end = decision - frozen.PRE, decision + frozen.TAIL
    frozen.require(end < window["end_ns"], "capture outside original window")
    for name in ("quote_request", "status_request"):
        request = tape[name]
        frozen.require(request["start_ns"] <= start < end < request["end_ns"], "source coverage differs")
    statuses = tape["status_records"]
    times = [s["ts_recv_ns"] for s in statuses]
    first, stop = bisect_right(times, start) - 1, bisect_right(times, end)
    frozen.require(first >= 0 and statuses[first]["is_trading"] in {"Y", "N"}
        and all(s["is_trading"] in {"Y", "N"} for s in statuses[first + 1:stop]),
        "source status coverage is not known")
    quote_times = [q["ts_recv_ns"] for q in tape["quote_records"]]
    capture = tape["quote_records"][bisect_left(quote_times, start):bisect_right(quote_times, end)]
    usable = []
    for q in capture:
        at = q["ts_recv_ns"]
        index = bisect_right(times, at) - 1
        if (index < 0 or times[index] == at or statuses[index]["is_trading"] not in {"Y", "N"}
                or not 0 < q["bid_px_nanos"] < q["ask_px_nanos"] < frozen.UNDEF
                or q["bid_size"] <= 0 or q["ask_size"] <= 0):
            continue
        usable.append({**q, "halted": statuses[index]["is_trading"] != "Y",
            "status_ts_recv_ns": times[index], "status_record_index": index})
    decision_quotes = [q for q in usable if q["ts_recv_ns"] <= decision]
    before = [q for q in usable if q["ts_recv_ns"] <= arrival]
    last = before[-1] if before else None
    age = arrival - last["ts_recv_ns"] if last else None
    carried = before[-1:] if last is not None and age <= max_age * MS else []
    later = [q for q in usable if arrival < q["ts_recv_ns"] < ack]
    candidates = carried + later
    return {
        "decision_ts_ns": decision, "arrival_ts_ns": arrival,
        "cancel_requested_ts_ns": requested, "cancel_ack_ts_ns": ack,
        "capture_start_ns": start, "capture_end_inclusive_ns": end,
        "max_quote_age_ns": max_age * MS,
        "decision_reference": decision_quotes[-1] if decision_quotes else None,
        "last_usable_quote_at_or_before_arrival": last,
        "last_quote_age_at_arrival_ns": age,
        "native_capture_quote_count": len(capture), "usable_capture_quote_count": len(usable),
        "carried_fresh_quote_count": len(carried), "later_active_quote_count": len(later),
        "active_candidate_count": len(candidates),
        "active_nonhalted_candidate_count": sum(not q["halted"] for q in candidates),
        "active_candidates_content_sha256": frozen.digest(candidates),
        "no_fresh_quote_status_supported": not candidates,
        "fill_simulation_performed": False,
    }


def cancellations(result):
    """Enumerate every residual authority/exhaustion acknowledgement, without filtering symbols."""
    for path in result["paths"]:
        for pair in path["sessions"]:
            runtime = pair["runtime"]
            snapshot = runtime["reconciliation_snapshot"]
            if snapshot is None:
                continue
            entries = {j["execution_evidence"]["content_sha256"]: j["execution_evidence"]
                for j in snapshot["journal"] if j["fee_application"]["trade"]["side"] == "buy"}
            sells = [j["execution_evidence"] for j in snapshot["journal"]
                if j["fee_application"]["trade"]["side"] == "sell"]
            orders = {e["order"]["order_id"]: e["order"] for e in runtime["events"]
                if e["event_type"] == "sell_submitted"}
            for event in snapshot.get("exit_residual_events", []):
                if event["event_type"] not in {"residual_ready", "residual_budget_exhausted"}:
                    continue
                frozen.checked(event)
                entry = frozen.checked(entries[event["entry_content_sha256"]])
                acknowledgement = frozen.checked(event["context"]["cancel_acknowledgement"]
                    if event["event_type"] == "residual_ready" else event["cancel_acknowledgement"])
                order = orders[acknowledgement["order_id"]]
                fills = [s for s in sells if s["entry_fill_id"] == entry["fill_id"]
                    and s["order_id"] == order["order_id"] and s["fill_time_ns"] <= order["cancel_ack_ts_ns"]]
                filled = sum(s["quantity"] for s in fills)
                frozen.require(acknowledgement["event_type"] == "sell_cancel_acknowledged"
                    and acknowledgement["order_id"] == order["order_id"]
                    and acknowledgement["timestamp_ns"] == order["cancel_ack_ts_ns"]
                    and acknowledgement["cancelled_quantity"] == order["quantity"] - filled > 0,
                    "cancellation differs beyond the status classification")
                yield {
                    "path_id": path["path_id"], "trading_date": pair["close"]["trading_date"],
                    "symbol": entry["symbol"], "entry": entry, "order": order,
                    "event_type": event["event_type"], "acknowledgement": acknowledgement,
                    "confirmed_order_filled_quantity": filled,
                    "frozen_checker_expected_status": "partially_filled_cancelled" if filled else "cancelled_unfilled",
                }


def diagnose(root, runtime_root, binding_root, parent_runtime_root, paths):
    result = frozen._pinned_file(runtime_root / "account-replay.json", RUNTIME_FILE)
    frozen.require(result["content_sha256"] == RUNTIME, "diagnostic runtime differs")
    try:
        frozen.verify(root, runtime_root, binding_root, parent_runtime_root, RUNTIME, paths)
    except ValueError as exc:
        frozen.require(str(exc) == EXPECTED_ERROR, "original checker failed at a different gate")
    else:
        raise ValueError("preserved original checker unexpectedly passed")
    contract = frozen.read(root / f"research/strategy/{frozen.ID}.json")
    binding = frozen._pinned_file(binding_root / "source-bindings.json", frozen.parent.BOUND_FILE)
    records = list(cancellations(result))
    statuses = Counter(row["acknowledgement"]["execution_status"] for row in records)
    mismatches = []
    sources = frozen.OriginalEvidence(root, binding, paths, contract["source_archives"])
    try:
        for row in records:
            actual = row["acknowledgement"]["execution_status"]
            if actual == row["frozen_checker_expected_status"]:
                continue
            frozen.require(actual == "unavailable_no_fresh_quote" and row["confirmed_order_filled_quantity"] == 0,
                "additional mismatch requires separate diagnosis")
            entry = row["entry"]
            data = sources(entry["opportunity_id"])
            proof = quote_lifecycle(data["tape"], data["window"], row["order"], entry["scenario_id"])
            frozen.require(proof["no_fresh_quote_status_supported"], "native tape contradicts no-fresh-quote status")
            reference = frozen.References(data["tape"]).at(data["window"], row["order"]["decision_ts_ns"])
            frozen.require(reference is not None, "original decision lacked a valid submission reference")
            mismatches.append({**row, "native_quote_lifecycle": proof,
                "frozen_decision_reference": reference,
                "execution_tape_content_sha256": frozen.digest(data["tape"]),
                "original_window_content_sha256": frozen.digest(data["window"]),
                "native_evidence_supports_runtime_status": True})
    finally:
        sources.close()
    return frozen.parent.seal({
        "contract_id": ID, "artifact_type": "post_outcome_failure_diagnosis",
        "runtime_content_sha256": RUNTIME, "runtime_file_sha256": RUNTIME_FILE,
        "original_registration_freeze_content_sha256": result["registration_freeze_content_sha256"],
        "original_checker_failure_reproduced": True, "original_checker_error": EXPECTED_ERROR,
        "cancellations_examined": len(records), "cancellation_status_counts": dict(statuses),
        "all_examined_acknowledgement_ids_times_and_quantities_match": True,
        "status_mismatch_count": len(mismatches), "status_mismatches": mismatches,
        "diagnosis": "zero_fill_checker_collapses_distinct_frozen_execution_statuses",
        "required_correction": "separate_verifier_child_reconstructs_status_from_original_active_quote_lifecycle_without_weakening_checks",
        "historical_replay_rerun": False, "original_code_or_artifacts_modified": False,
        "complete_runtime_verified": False, "independent_fill_simulation": False,
        "financial_metrics_eligible": False, "account_backtest_complete": False,
        "retrospective_labels_opened": False, "policy_promotion_eligible": False,
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("runtime-root", "binding-root", "parent-runtime-root", "management-zip", "exit-zip", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    import sys
    from run_offline_python_v13 import deny_external_io
    sys.addaudithook(deny_external_io)
    report = diagnose(Path(__file__).resolve().parents[1], args.runtime_root, args.binding_root,
        args.parent_runtime_root, {"management": args.management_zip, "exit": args.exit_zip})
    with args.output.open("xb") as handle:
        handle.write((json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
    print(json.dumps({k: v for k, v in report.items() if k != "status_mismatches"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
