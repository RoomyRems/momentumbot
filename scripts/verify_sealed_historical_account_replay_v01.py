"""Stdlib-only original account identity, chronology and accounting verifier.

Uses frozen independent arithmetic/clock verifiers, never production account,
strategy or fill simulation imports. The previously verified original binding
artifact is pinned by whole bytes and content. This checker does not claim an
independent second fill simulator or repair missing overnight evidence.
"""
from copy import deepcopy
from decimal import Decimal, localcontext
import argparse
import hashlib
import json
from pathlib import Path

from verify_sealed_historical_account_continuity_v01 import account_state, verify_events
from verify_sealed_historical_account_state_producer_v01 import public_collections, ready, exact_money, checked_tree
from verify_sealed_historical_management_fee_reconciliation_v01 import checked, read, require, digest, number

ID = "sealed-historical-account-replay-v0.1"
BOUND = "9bb780dcbfbec3ef1b4e437cc3dc76e1528897956490d4ddd32d399ed5f683cd"
BOUND_FILE = "dbaeb9265d37872b04c554143490cdc2e023311468d1f1ba4aa2fbf8b9b67e9a"


def seal(value):
    return dict(value, content_sha256=digest(value))


def boundaries(value):
    for name in ("historical_runtime_authorized", "historical_producer_authenticated", "original_market_source_provenance_authenticated"):
        require(value[name] is True, "historical provenance boundary differs")
    for name in ("financial_metrics_eligible", "account_close_evidence", "policy_promotion_eligible", "retrospective_labels_opened",
                 "provider_requests_authorized", "broker_orders_authorized", "overnight_execution_authorized", "broker_statement_equivalence_verified"):
        require(value[name] is False, "closed completion boundary differs")


def source_for_events(source, slot, bindings):
    return {"session_id": source["session_id"], "opportunities": [
        {"candidate": bindings[r["opportunity_id"]]["candidates"][slot["profile_id"]],
         "position": {"entry_input": {"window": bindings[r["opportunity_id"]]["window"]}}}
        for r in source["opportunities"] if r["input_status"] == "available"]}


def verify_path(program, result, manifest):
    checked(program)
    checked_tree(result)
    boundaries(result)
    require(program["contract_id"] == result["contract_id"] == ID, "contract identity differs")
    require(program["input_scope"] == "authenticated_original_historical_sources", "source scope differs")
    require(program["source_bindings_content_sha256"] == BOUND, "bound manifest reference differs")
    originals = {p["path_id"]: p for p in manifest["paths"]}
    require(program["path_id"] == result["path_id"] and program["slots"] == originals[result["path_id"]]["sessions"], "original path catalog differs")
    require(result["program_content_sha256"] == program["content_sha256"], "program pin differs")
    require(len(program["slots"]) == len(program["sessions"]) == len(result["sessions"]) == result["session_count"] == 30, "all original slots required")
    bindings = {b["opportunity_id"]: b for b in manifest["opportunities"]}
    dependencies = {d["next_session_id"]: d for d in manifest["carry_dependencies"]}
    capital = "30000.00" if program["slots"][0]["account_key"] == "main_account" else "2000.00"
    opening = {"equity_usd": capital, "buying_power_usd": capital, "cumulative_realized_pnl_usd": "0.00",
        "cumulative_fees_usd": "0.00", "positions": [], "pending_orders": [], "campaigns": [], "unresolved_inputs": []}
    require(result["initial_account_state"] == opening and result["seed_application_count"] == 1, "once-only seed differs")
    previous, counts = None, {"sessions": 0, "executed_sessions": 0, "blocked_sessions": 0, "input_failure_sessions": 0,
        "unavailable_references": 0, "opportunity_references": 0, "events": 0, "confirmed_fills": 0,
        "confirmed_entries": 0, "confirmed_sells": 0, "completed_streams": 0}
    for index, (slot, source, pair) in enumerate(zip(program["slots"], program["sessions"], result["sessions"])):
        runtime, close = checked(pair["runtime"]), checked(pair["close"])
        boundaries(runtime)
        boundaries(close)
        require(source == {"session_id": slot["session_id"], "opportunities": slot["opportunity_inputs"]}, "original session references differ")
        require(runtime["contract_id"] == close["contract_id"] == ID and runtime["path_id"] == close["path_id"] == result["path_id"], "runtime identity differs")
        require(runtime["session_id"] == close["session_id"] == slot["session_id"], "session identity differs")
        require(close["trading_date"] == slot["trading_date"] and close["session_index"] == index and close["seed_applied"] is (index == 0), "date/index/seed differs")
        require(runtime["source_slot_content_sha256"] == close["source_slot_content_sha256"] == slot["content_sha256"], "slot pin differs")
        require(close["previous_close_content_sha256"] == previous and close["source_runtime_content_sha256"] == runtime["content_sha256"], "close chain differs")
        require(runtime["session_program_sha256"] == digest(source) and runtime["opening_account_state_sha256"] == digest(opening), "source or preceding account state differs")
        require(runtime["source_bindings_content_sha256"] == BOUND, "source binding pin differs")
        snapshot, failure, blocked = runtime["reconciliation_snapshot"], runtime["failure"], runtime["blocked_before_execution"]
        projection_failure = failure is not None and failure["kind"] == "opening_ledger_projection_unavailable"
        require(blocked == (not ready(opening) or projection_failure), "opening readiness differs")
        if projection_failure:
            require(ready(opening) and any(Decimal(str(float(number(opening[k])))) != number(opening[k]) for k in ("equity_usd", "buying_power_usd")), "unsupported opening projection failure")
        require(runtime["historical_session_scheduler_executed"] == (snapshot is not None), "execution marker differs")
        counts["confirmed_fills"] += verify_events(source_for_events(source, slot, bindings), runtime)
        counts["events"] += len(runtime["events"])
        seen = {e["opportunity_id"]: e["disposition"] for e in runtime["events"] if e["event_type"] == "opportunity_disposition"}
        dispositions = [{**r, "disposition": "unavailable_input" if r["input_status"] == "unavailable" else
            seen.get(r["opportunity_id"], "blocked_prior_state" if blocked else "unprocessed_available_input")}
            for r in slot["opportunity_inputs"]]
        require(runtime["opportunity_dispositions"] == dispositions, "lost or invented opportunity disposition")
        gaps = [{"kind": d["disposition"], "opportunity_id": d["opportunity_id"], "availability_content_sha256": d["availability_content_sha256"],
            "reason": d["reason"], "blocks_next_session": d["disposition"] != "unavailable_input"} for d in dispositions
            if d["disposition"] in {"unavailable_input", "unprocessed_available_input", "blocked_prior_state"}]
        failures = [] if failure is None else [failure]
        if blocked:
            require(snapshot is None and not runtime["events"] and not runtime["processed_streams"] and runtime["unconfirmed_entry_order"] is None, "blocked state executed")
            expected = deepcopy(opening)
            expected["unresolved_inputs"] += gaps + failures + [{"kind": "preceding_state_blocks_execution", "blocks_next_session": True,
                "previous_close_content_sha256": previous}]
            net = gross = charged = Decimal(0)
        else:
            account_state(snapshot)
            require(number(str(snapshot["ledger"]["account"]["starting_equity"])) == number(opening["equity_usd"])
                and number(str(snapshot["ledger"]["account"]["starting_buying_power"])) == number(opening["buying_power_usd"]), "daily capital reset")
            positions, pending, extra = public_collections(snapshot)
            if runtime["unconfirmed_entry_order"] is not None:
                pending.append(runtime["unconfirmed_entry_order"])
            gross, net = number(snapshot["exact_account"]["gross_realized_pnl"]), number(snapshot["exact_account"]["net_realized_pnl"])
            charged = number(snapshot["fee_book"]["fees"]["total_charged"])
            expected = {"equity_usd": None if positions or pending else exact_money(number(opening["equity_usd"]) + net),
                "buying_power_usd": exact_money(number(snapshot["exact_account"]["remaining_buying_power"])),
                "cumulative_realized_pnl_usd": exact_money(number(opening["cumulative_realized_pnl_usd"]) + net),
                "cumulative_fees_usd": exact_money(number(opening["cumulative_fees_usd"]) + charged),
                "positions": positions, "pending_orders": pending, "campaigns": opening["campaigns"] + snapshot["ledger"]["campaigns"],
                "unresolved_inputs": opening["unresolved_inputs"] + gaps + failures + extra}
            trades = [r["fee_application"]["trade"] for r in snapshot["journal"]]
            counts["confirmed_entries"] += sum(t["side"] == "buy" for t in trades)
            counts["confirmed_sells"] += sum(t["side"] == "sell" for t in trades)
        require(close["account_state"] == expected and close["next_session_flat_cash_execution_ready"] == ready(expected), "derived exact close differs")
        for key, value in (("session_gross_realized_pnl_usd", gross), ("session_net_realized_pnl_usd", net), ("session_fees_usd", charged)):
            require(runtime[key] == exact_money(value), "session delta differs")
        complete = snapshot is not None and failure is None
        require(runtime["complete_streams_verified"] == complete, "stream completion flag differs")
        progress = runtime["processed_streams"]
        require(len({(p["opportunity_id"], p["resource"]) for p in progress}) == len(progress), "duplicate stream progress")
        for row in progress:
            require(row["opportunity_id"] in {r["opportunity_id"] for r in source["opportunities"] if r["input_status"] == "available"}, "foreign or unavailable stream")
            commitment = bindings[row["opportunity_id"]]["management_streams"][row["resource"]]
            require(type(row["rows"]) is int and 0 <= row["rows"] <= commitment["rows"], "stream progress exceeds registered source")
            if complete:
                require({k: row[k] for k in ("rows", "sha256")} == commitment, "complete stream differs from original binding")
        if complete:
            require(len(progress) == 2 * sum(r["input_status"] == "available" for r in source["opportunities"]), "complete session omitted original streams")
            counts["completed_streams"] += len(progress)
        active = runtime["active_original_window"]
        if active is not None:
            oid = active["opportunity"]["opportunity_id"]
            require(active == bindings[oid]["window"] and snapshot is not None and snapshot["management"] is not None, "active original window differs")
            require(snapshot["management"]["entry"]["opportunity_id"] == oid, "active window detached from retained management")
        elif snapshot is not None:
            require(snapshot["management"] is None, "active original window lost")
        dependency = dependencies.get(slot["session_id"])
        carry = None if dependency is None else seal({"dependency": dependency,
            "previous_close_content_sha256": previous, "opening_account_state_sha256": digest(opening),
            "status": "blocked_preserved_prior_state" if blocked else "flat_cash_no_share_mark_or_adjustment_required",
            "prior_state_preserved": True, "new_source_evidence_inferred": False})
        require(runtime["carry_dependency"] == carry, "carry source/state dependency differs")
        status = "blocked_prior_state" if blocked else "input_failure" if failure else "original_window_exhausted_with_unresolved_state" if not ready(expected) else "flat_complete_with_unavailable_inputs" if gaps else "flat_complete"
        require(runtime["status"] == status, "session completion status differs")
        counts["sessions"] += 1
        counts["executed_sessions"] += not blocked
        counts["blocked_sessions"] += blocked
        counts["input_failure_sessions"] += failure is not None
        counts["unavailable_references"] += sum(r["input_status"] == "unavailable" for r in source["opportunities"])
        counts["opportunity_references"] += len(dispositions)
        opening, previous = expected, close["content_sha256"]
    require(result["last_close_content_sha256"] == previous, "final close differs")
    require(result["path_complete"] == all(p["runtime"]["status"] == "flat_complete" for p in result["sessions"]), "path completion differs")
    return counts


def verify(root, runtime_root, binding_root, expected_runtime_sha):
    contract = checked(read(root / f"research/strategy/{ID}.json"))
    for path, sha in {**contract["frozen_parent_file_sha256"], **contract["implementation_file_sha256"]}.items():
        require(hashlib.sha256((root / path).read_bytes()).hexdigest() == sha, "frozen code/parent differs: " + path)
    registration = checked(read(root / f"research/runtime/{ID}/freeze-manifest.json"))
    require(registration["contract_content_sha256"] == contract["content_sha256"], "registration contract differs")
    for name, spec in registration["file_inventory"].items():
        raw = (root / f"research/runtime/{ID}" / name).read_bytes()
        require(len(raw) == spec["bytes"] and hashlib.sha256(raw).hexdigest() == spec["sha256"], "registration file differs")
    raw = (binding_root / "source-bindings.json").read_bytes()
    require(hashlib.sha256(raw).hexdigest() == BOUND_FILE, "independently verified source-binding bytes differ")
    manifest = checked(json.loads(raw))
    require(manifest["content_sha256"] == BOUND, "original bound manifest differs")
    frozen = checked(read(runtime_root / "freeze-manifest.json"))
    boundaries(frozen)
    require(frozen["contract_content_sha256"] == contract["content_sha256"] and set(frozen["file_inventory"]) == {"account-replay.json"}, "runtime freeze scope differs")
    raw = (runtime_root / "account-replay.json").read_bytes()
    spec = frozen["file_inventory"]["account-replay.json"]
    require(len(raw) == spec["bytes"] and hashlib.sha256(raw).hexdigest() == spec["sha256"], "runtime bytes differ")
    result = checked(json.loads(raw))
    require(result["content_sha256"] == expected_runtime_sha == frozen["document_content_sha256"]["account-replay.json"], "independent runtime pin differs")
    require(result["registration_freeze_content_sha256"] == registration["content_sha256"], "runtime registration differs")
    require(result["source_bindings_content_sha256"] == BOUND and result["source_archives"] == manifest["source_archives"], "runtime source authority differs")
    boundaries(result)
    programs = checked(read(root / f"research/runtime/{ID}/source-programs.json"))["programs"]
    require(len(programs) == len(result["paths"]) == 12, "all paths required")
    counts = []
    with localcontext() as context:
        context.prec = 60
        for program, path in zip(programs, result["paths"]):
            counts.append({"path_id": path["path_id"], **verify_path(program, path, manifest)})
    totals = {k: sum(c[k] for c in counts) for k in counts[0] if k != "path_id"}
    require((totals["sessions"], totals["opportunity_references"], totals["unavailable_references"]) == (360, 744, 162), "original panel population differs")
    return seal({"contract_id": ID, "verification_passed": True,
        "runtime_content_sha256": expected_runtime_sha, "source_bindings_content_sha256": BOUND,
        "registration_freeze_content_sha256": registration["content_sha256"],
        "paths": counts, "totals": totals, "independent_fill_simulation": False,
        "original_binding_evidence_reused_by_exact_bytes": True,
        "financial_metrics_eligible": False, "retrospective_labels_opened": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--binding-root", type=Path, required=True)
    parser.add_argument("--expected-runtime-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import sys
    from run_offline_python_v13 import deny_external_io
    sys.addaudithook(deny_external_io)
    result = verify(Path(__file__).resolve().parents[1], args.runtime_root, args.binding_root, args.expected_runtime_sha256)
    with args.output.open("xb") as handle:
        handle.write((json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
