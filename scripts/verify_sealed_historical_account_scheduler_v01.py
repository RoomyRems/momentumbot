"""Independent stdlib-only scheduler/account evidence verification.

Recomputes candidate priority, public reservation chronology, capital carry,
fee/share/P&L arithmetic and immutable metadata. It does not import production
code, authenticate original market sources or independently simulate all fills.
"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, localcontext
import argparse
import hashlib
import json
from pathlib import Path
import re

from verify_sealed_historical_account_state_producer_v01 import account_state, public_collections, ready, exact_money, checked_tree
from verify_sealed_historical_management_fee_reconciliation_v01 import checked, read, require, digest, number

ID = "sealed-historical-account-scheduler-v0.1"
PARENT_CONTENT = "0e21c52ce104c96ac1dc6737291557f4adcbf0a4b54917efdfab10134406d7f5"


def stamp_ns(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(stamp.tzinfo is not None, "aware candidate time required")
    fraction = re.search(r":\d{2}\.(\d{1,9})(?:Z|[+-])", value)
    return int(stamp.replace(microsecond=0).timestamp()) * 10**9 + (int(fraction[1].ljust(9, "0")) if fraction else 0)


def priority(item):
    row, op = item["candidate"], item["position"]["entry_input"]["window"]["opportunity"]
    require(stamp_ns(row["timestamp"]) == op["candidate_qualified_ts_ns"] <= op["decision_ts_ns"], "candidate is not original causal activation")
    return (op["decision_ts_ns"], -{"a_quality": 2, "conditional": 1}[row["quality"]],
        row["top_gainer_rank"] or 1_000_000, -row["percent_gain"], -row["relative_volume"],
        -row["cumulative_volume"], row["float_shares"] or 10**12, stamp_ns(row["timestamp"]),
        row["symbol"], op["plan_id"], op["opportunity_id"])


def verify_events(source, runtime):
    snapshot = runtime["reconciliation_snapshot"]
    if snapshot is None:
        require(not runtime["events"], "blocked opening executed events")
        return 0
    journal = snapshot["journal"]
    cash = Decimal(str(snapshot["ledger"]["account"]["starting_buying_power"]))
    max_loss = Decimal(str(snapshot["ledger"]["account"]["starting_equity"])) * Decimal(".01")
    pending, active, quantity, locked = None, None, 0, False
    previous, last_clock, consumed, decisions = None, (-1, -1), set(), []
    ordered = sorted(source["opportunities"], key=priority)
    expected_ids = [i["position"]["entry_input"]["window"]["opportunity"]["opportunity_id"] for i in ordered]
    source_by_id = {i["position"]["entry_input"]["window"]["opportunity"]["opportunity_id"]: i for i in ordered}
    exit_orders, terminal, targets, used_liquidity = {}, set(), set(), set()
    arrival_ms, cancel_ms, ack_ms = {"l1-conservative-v0.1": (100, 250, 100), "l1-stress-v0.1": (250, 150, 150)}[snapshot["identity"]["scenario_id"]]
    def lifecycle(order, at):
        require(order["arrival_ts_ns"] == at + arrival_ms * 1_000_000
            and order["cancel_requested_ts_ns"] == at + (arrival_ms + cancel_ms) * 1_000_000
            and order["cancel_ack_ts_ns"] == at + (arrival_ms + cancel_ms + ack_ms) * 1_000_000,
            "frozen execution latency changed")
    def view():
        return {"cash_usd": exact_money(cash), "confirmed_quantity": quantity,
            "capacity_reserved": pending is not None or active is not None, "account_locked": locked}
    for index, event in enumerate(runtime["events"]):
        checked(event)
        require(event["sequence"] == index and event["previous_event_sha256"] == previous, "event hash chain differs")
        previous = event["content_sha256"]
        clock = (event["at_ns"], event["phase"])
        require(clock >= last_clock, "global account event clock reversed")
        last_clock = clock
        at, phase, kind, oid = *clock, event["event_type"], event["opportunity_id"]
        require(oid in source_by_id, "foreign opportunity event")
        op = source_by_id[oid]["position"]["entry_input"]["window"]["opportunity"]
        if kind == "opportunity_disposition":
            require(phase == 1 and at == op["decision_ts_ns"], "decision time differs")
            require(event["account_before"] == view(), "decision saw incorrect cash, inventory, reservation or lock")
            decisions.append(oid)
            require(decisions == expected_ids[:len(decisions)], "frozen causal scarcity order differs")
            disposition = event["disposition"]
            if view()["capacity_reserved"]:
                require(disposition == "blocked_capacity", "reserved account was reused")
            elif locked:
                require(disposition == "blocked_account_lock", "locked account submitted")
            else:
                require(disposition in {"entry_submitted", "no_whole_share_capacity", "unsupported_same_symbol_reentry"}, "unsupported entry disposition")
            if disposition == "entry_submitted":
                require(pending is None and active is None and not locked, "overlapping or locked submission")
                order = event["order"]
                lifecycle(order, at)
                require(set(order) == {"order_id", "quantity", "limit_price", "decision_ts_ns", "arrival_ts_ns", "cancel_requested_ts_ns", "cancel_ack_ts_ns", "capture_content_sha256"}, "entry exposes private future execution")
                require(order["decision_ts_ns"] == at < order["arrival_ts_ns"] <= order["cancel_requested_ts_ns"] < order["cancel_ack_ts_ns"], "entry order lifecycle differs")
                pending = {"oid": oid, "order": order, "filled": 0}
            else:
                require(event["order"] is None, "rejected opportunity invented order")
        elif kind in {"entry_fill_confirmed", "sell_fill_confirmed"}:
            require(phase == 3 and event["journal_index"] not in consumed, "duplicate or early fill feedback")
            j = event["journal_index"]
            require(j == len(consumed) and j < len(journal), "missing or reordered confirmed fill")
            consumed.add(j)
            row = journal[j]
            trade, evidence = row["fee_application"]["trade"], row["execution_evidence"]
            require(at == trade["timestamp_ns"] == row["known_at_ns"], "fill exposed outside actual feedback clock")
            require(evidence["activation_id"] == op["activation_id"] if kind == "entry_fill_confirmed" else row["activation_id"] == op["activation_id"], "fill belongs to another activation")
            if kind == "entry_fill_confirmed":
                require(trade["side"] == "buy" and active is None and pending is not None and pending["oid"] == oid, "entry without reservation")
                require(pending["order"]["arrival_ts_ns"] <= at < pending["order"]["cancel_ack_ts_ns"], "entry outside lifecycle")
                require(trade["order_id"] == pending["order"]["order_id"] and 0 < trade["quantity"] <= pending["order"]["quantity"], "entry quantity/order differs")
                quantity, active, pending["filled"] = trade["quantity"], oid, trade["quantity"]
            else:
                require(trade["side"] == "sell" and active == oid and trade["order_id"] in exit_orders, "sell without active order")
                order = exit_orders[trade["order_id"]]
                require(order["arrival_ts_ns"] <= at < order["cancel_ack_ts_ns"] and 0 < trade["quantity"] <= min(quantity, order["quantity"]), "sell exceeds reservation or lifecycle")
                liquidity = (evidence["source_request_sha256"], evidence["source_record_index"])
                require(liquidity not in used_liquidity, "displayed liquidity reused")
                used_liquidity.add(liquidity)
                quantity -= trade["quantity"]
            cash = number(row["cash_after"])
            net, high = number(row["net_realized_after"]), number(row["net_high_water_after"])
            locked = locked or net <= -max_loss or (high > 0 and net <= high / 2)
            require(event["account_after"] == view(), "fill public account projection differs")
        elif kind == "entry_cancel_acknowledged":
            require(phase == 3 and pending is not None and pending["oid"] == oid, "entry ack has no pending order")
            require(at == pending["order"]["cancel_ack_ts_ns"] and event["order_id"] == pending["order"]["order_id"], "early or foreign entry ack")
            require(event["confirmed_quantity"] == pending["filled"] and event["cancelled_quantity"] == pending["order"]["quantity"] - pending["filled"], "entry cancel quantity differs")
            pending = None
        elif kind == "sell_submitted":
            order = event["order"]
            lifecycle(order, at)
            require(phase == 2 and active == oid and at == order["decision_ts_ns"], "sell decision before confirmed entry or wrong phase")
            require(all(o["cancel_ack_ts_ns"] < at for o in exit_orders.values()), "sell reservation reused before acknowledgment")
            require(order["order_id"] not in exit_orders and 0 < order["quantity"] <= quantity, "invalid sell reservation")
            if event["reason"] == "first_target":
                require(oid not in targets, "target attempt retried")
                targets.add(oid)
            else:
                require(oid not in terminal and order["quantity"] == quantity, "terminal attempt retried or wrong quantity")
                terminal.add(oid)
            if event["reason"] == "account_risk_flatten":
                require(locked, "risk flatten without known account lock")
            end = source_by_id[oid]["position"]["entry_input"]["window"]["end_ns"]
            require(at < order["arrival_ts_ns"] <= order["cancel_requested_ts_ns"] < order["cancel_ack_ts_ns"] < end, "sell extends original window")
            exit_orders[order["order_id"]] = order
        elif kind == "capacity_released":
            require(phase in (3, 4) and active == oid and quantity == 0 and pending is None, "capacity released with shares or entry reservation")
            require(all(o["cancel_ack_ts_ns"] <= at for o in exit_orders.values()), "capacity released before sell acknowledgment")
            active = None
            require(event["account_after"] == view(), "released account view differs")
        else:
            raise ValueError("unknown scheduler event")
    require(consumed == set(range(len(journal))), "journal fill not exposed by scheduler")
    if runtime["complete_streams_verified"]:
        require(decisions == expected_ids and runtime["failure"] is None, "complete session missed decisions")
    return len(consumed)


def verify_vector(vector, originals):
    p, r = checked(vector["program"]), checked(vector["result"])
    checked_tree(r)
    require(p["contract_id"] == r["contract_id"] == ID and p["input_scope"] == "synthetic_component_fixture", "synthetic scope differs")
    require(r["historical_execution_count"] == 0 and not r["financial_metrics_eligible"] and not r["historical_runtime_authorized"], "historical boundary changed")
    require(r["program_content_sha256"] == p["content_sha256"] and r["slot_catalog_sha256"] == digest(p["slots"]), "program identity differs")
    original = originals[p["path_id"]]
    require(len(p["slots"]) == 30 and r["session_count"] == len(p["sessions"]) == len(r["sessions"]), "path dimensions differ")
    for actual, expected in zip(p["slots"], original["sessions"]):
        keys = set(expected) - {"content_sha256", "opportunity_inputs", "unavailable_opportunity_count", "source_date_has_no_micro_decisions"}
        require(set(actual) == set(expected) and all(actual[k] == expected[k] for k in keys), "original slot identity differs")
    capital = "30000.00" if p["slots"][0]["account_key"] == "main_account" else "2000.00"
    opening = {"equity_usd": capital, "buying_power_usd": capital, "cumulative_realized_pnl_usd": "0.00",
        "cumulative_fees_usd": "0.00", "positions": [], "pending_orders": [], "campaigns": [], "unresolved_inputs": []}
    require(r["initial_account_state"] == opening and r["seed_application_count"] == 1, "once-only seed differs")
    previous, fills, event_count = None, 0, 0
    for index, (slot, source, pair) in enumerate(zip(p["slots"], p["sessions"], r["sessions"])):
        runtime, close = checked(pair["runtime"]), checked(pair["close"])
        require(runtime["session_id"] == close["session_id"] == source["session_id"] == slot["session_id"], "session identity differs")
        require(close["previous_close_content_sha256"] == previous and close["source_runtime_content_sha256"] == runtime["content_sha256"], "close chain differs")
        require(close["session_index"] == index and close["seed_applied"] is (index == 0), "session index/seed differs")
        require(runtime["source_slot_content_sha256"] == close["source_slot_content_sha256"] == slot["content_sha256"], "source slot commitment differs")
        require(runtime["opening_account_state_sha256"] == digest(opening) and runtime["session_program_sha256"] == digest(source), "opening or session source differs")
        require(runtime["blocked_before_execution"] == (not ready(opening)), "opening readiness differs")
        fills += verify_events(source, runtime)
        event_count += len(runtime["events"])
        seen = {e["opportunity_id"]: e["disposition"] for e in runtime["events"] if e["event_type"] == "opportunity_disposition"}
        blocked = runtime["blocked_before_execution"]
        dispositions = [{**ref, "disposition": "unavailable_input" if ref["input_status"] == "unavailable" else seen.get(ref["opportunity_id"], "blocked_prior_state" if blocked else "unprocessed_available_input")} for ref in slot["opportunity_inputs"]]
        require(runtime["opportunity_dispositions"] == dispositions, "lost opportunity disposition")
        gaps = [{"kind": d["disposition"], "opportunity_id": d["opportunity_id"], "availability_content_sha256": d["availability_content_sha256"],
            "reason": d["reason"], "blocks_next_session": d["disposition"] != "unavailable_input"} for d in dispositions
            if d["disposition"] in {"unavailable_input", "unprocessed_available_input", "blocked_prior_state", "unsupported_same_symbol_reentry"}]
        snapshot = runtime["reconciliation_snapshot"]
        failures = [] if runtime["failure"] is None else [runtime["failure"]]
        if blocked:
            require(snapshot is None and not runtime["events"], "blocked state executed")
            expected = deepcopy(opening)
            expected["unresolved_inputs"] += gaps + [{"kind": "preceding_state_blocks_execution", "blocks_next_session": True, "previous_close_content_sha256": previous}]
            net = gross = charged = Decimal(0)
        else:
            account_state(snapshot)
            require(Decimal(str(snapshot["ledger"]["account"]["starting_equity"])) == number(opening["equity_usd"])
                and Decimal(str(snapshot["ledger"]["account"]["starting_buying_power"])) == number(opening["buying_power_usd"]), "daily capital reset")
            positions, pending, extra = public_collections(snapshot)
            if runtime["unconfirmed_entry_order"] is not None: pending.append(runtime["unconfirmed_entry_order"])
            gross, net = number(snapshot["exact_account"]["gross_realized_pnl"]), number(snapshot["exact_account"]["net_realized_pnl"])
            charged = number(snapshot["fee_book"]["fees"]["total_charged"])
            expected = {"equity_usd": None if positions or pending else exact_money(number(opening["equity_usd"]) + net),
                "buying_power_usd": exact_money(number(snapshot["exact_account"]["remaining_buying_power"])),
                "cumulative_realized_pnl_usd": exact_money(number(opening["cumulative_realized_pnl_usd"]) + net),
                "cumulative_fees_usd": exact_money(number(opening["cumulative_fees_usd"]) + charged),
                "positions": positions, "pending_orders": pending, "campaigns": opening["campaigns"] + snapshot["ledger"]["campaigns"],
                "unresolved_inputs": opening["unresolved_inputs"] + gaps + failures + extra}
            if runtime["complete_streams_verified"]:
                for item in source["opportunities"]:
                    spec = item["position"]
                    for name, resource in (("bars", "raw_sip_1m_bars"), ("trades", "sip_transactions")):
                        raw = b"".join(json.dumps(v, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n" for v in spec[name])
                        require(spec["expected_streams"][resource] == {"rows": len(spec[name]), "sha256": hashlib.sha256(raw).hexdigest()}, "trailing source commitment differs")
        require(close["account_state"] == expected and close["next_session_flat_cash_execution_ready"] == ready(expected), "derived close differs")
        for key, value in (("session_gross_realized_pnl_usd", gross), ("session_net_realized_pnl_usd", net), ("session_fees_usd", charged)):
            require(runtime[key] == exact_money(value), "session accounting delta differs")
        previous, opening = close["content_sha256"], expected
    require(r["last_close_content_sha256"] == previous, "last checkpoint differs")
    return fills, event_count, len(r["sessions"])


def verify(root, bundle, vectors_path):
    contract = read(root / f"research/strategy/{ID}.json")
    require(read(root / "research/strategy/sealed-historical-account-valuation-v0.1.json")["content_sha256"] == PARENT_CONTENT, "frozen valuation parent differs")
    for path, sha in {**contract["frozen_parent_file_sha256"], **contract["implementation_file_sha256"]}.items():
        require(hashlib.sha256((root / path).read_bytes()).hexdigest() == sha, "code or parent bytes differ: " + path)
    manifest = read(bundle / "freeze-manifest.json")
    require(manifest["contract_content_sha256"] == contract["content_sha256"], "registration freeze differs")
    require({p.name for p in bundle.iterdir()} == {*manifest["file_inventory"], "freeze-manifest.json"}, "metadata inventory differs")
    for name, expected in manifest["file_inventory"].items():
        path = bundle / name
        require(path.stat().st_size == expected["bytes"] and hashlib.sha256(path.read_bytes()).hexdigest() == expected["sha256"], "metadata bytes differ")
        require(read(path)["content_sha256"] == manifest["document_content_sha256"][name], "metadata content differs")
    mapping = read(bundle / "scheduler-dependencies.json")
    original = read(root / "research/runtime/sealed-historical-account-state-producer-v0.1/account-state-dependencies.json")
    require(mapping["slots"] == original["slots"] and mapping["account_plan_content_sha256"] == original["account_plan_content_sha256"], "original opportunity plan changed")
    require(mapping["session_count"] == 360 and mapping["path_count"] == 12 and mapping["seed_applications"] == 12 and mapping["previous_close_dependencies"] == 348, "original dimensions differ")
    plan = read(root / "research/runtime/sealed-historical-account-management-inputs-v0.1/account-session-input-plan.json")
    paths = {p["path_id"]: p for p in plan["paths"]}
    vectors = read(vectors_path)
    require(vectors["contract_id"] == ID and vectors["synthetic_only"] is True and vectors["historical_execution_count"] == 0, "evidence scope differs")
    required = {"collision", "delayed", "unfilled", "partial_carry", "reentry_unresolved", "pending_input_failure", "omitted", "unavailable", "risk_flatten", "l1-conservative-v0.1-overlap", "l1-stress-v0.1-overlap"} | {"empty-" + p for p in paths}
    require(len(vectors["vectors"]) == len(required) and {v["name"] for v in vectors["vectors"]} == required, "synthetic coverage differs")
    fills = events = sessions = 0
    with localcontext() as context:
        context.prec = 60
        for vector in vectors["vectors"]:
            f, e, s = verify_vector(vector, paths)
            fills += f; events += e; sessions += s
    report = {"verification_passed": True, "contract_id": ID, "contract_content_sha256": contract["content_sha256"],
        "freeze_content_sha256": manifest["content_sha256"], "vectors_content_sha256": vectors["content_sha256"],
        "case_count": len(required), "session_checkpoints": sessions, "confirmed_journal_fills": fills, "scheduler_events": events,
        "independent_scarcity_order_and_reservation_chronology_verified": True, "independent_fee_share_cash_and_net_guards_verified": True,
        "production_modules_imported": False, "market_fill_simulation_independently_reimplemented": False,
        "historical_execution_count": 0, "historical_market_source_provenance_verified": False}
    return {**report, "content_sha256": digest(report)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--vectors", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.root, args.bundle or args.root / "research/runtime" / ID, args.vectors)
    with args.output.open("x") as handle:
        handle.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
