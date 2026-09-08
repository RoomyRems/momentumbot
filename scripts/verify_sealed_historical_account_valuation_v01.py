"""Stdlib-only independent verification of causal marks and preserved state.

The frozen independent producer checker verifies source account arithmetic.
This checker separately selects quote/status evidence and recomputes equity.
No production module, provider client or historical tape is imported/opened.
"""
import argparse
from datetime import date, datetime, time
from decimal import Decimal, localcontext
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from verify_sealed_historical_account_state_producer_v01 import (
    CLOSED as PARENT_CLOSED, checked_tree, exact_money, sealed, verify_vector, account_state)
from verify_sealed_historical_management_fee_reconciliation_v01 import digest, checked, read, require

ID = "sealed-historical-account-valuation-v0.1"
CLOSED = PARENT_CLOSED + ("corporate_action_source_provenance_verified", "mark_is_executable_proceeds",
                         "continuous_position_order_execution_authorized")
REQUEST_KEYS = {"request_id", "trading_date", "dataset", "schema", "symbols", "stype_in", "start_ns", "end_ns", "end_exclusive"}
QUOTE_KEYS = {"symbol", "ts_recv_ns", "sequence", "bid_px_nanos", "bid_size", "ask_px_nanos", "ask_size", "source_request_sha256", "source_record_index"}


def boundary(value):
    require(value["provider_calls"] == 0 and all(value[k] is False for k in CLOSED), "valuation authority boundary differs")


def start_ns(slot):
    return int(datetime.combine(date.fromisoformat(slot["trading_date"]), time(7), ZoneInfo("America/New_York")).timestamp()) * 10**9


def positive_int(value):
    require(type(value) is int and value > 0, "positive integer required")
    return value


def reference_mark(position, supplied, slot, close_sha, at):
    if supplied is None:
        return "unavailable", "missing_position_inputs", None, None
    try:
        require(supplied["position_content_sha256"] == digest(position), "position pin differs")
        units = supplied["units_evidence"]
        if units is None:
            return "unavailable", "missing_share_unit_continuity", None, None
        require(set(units) == {"status", "source_id", "known_at_ns", "from_close_content_sha256", "through_ns"}, "unit fields differ")
        require(units["source_id"].startswith("synthetic-") and units["from_close_content_sha256"] == close_sha
                and positive_int(units["through_ns"]) == at, "unit scope differs")
        if positive_int(units["known_at_ns"]) > at:
            return "unavailable", "share_unit_evidence_not_yet_known", None, None
        require(units["status"] in {"unchanged_raw_units", "adjustment_required", "unavailable"}, "unit status differs")
        if units["status"] != "unchanged_raw_units":
            return "unavailable", "share_unit_" + units["status"], None, None
        tape = supplied["tape"]
        if tape is None:
            require(supplied["expected_tape_sha256"] is None, "missing tape has pin")
            return "unavailable", "missing_quote_status_inputs", None, None
        require(set(tape) == {"quote_request", "quote_records", "status_request", "status_records"}, "tape fields differ")
        require(digest(tape) == supplied["expected_tape_sha256"], "tape pin differs")
        symbol, day = position["symbol"], slot["trading_date"]
        age = (100 if slot["execution_scenario_id"] == "l1-conservative-v0.1" else 50) * 10**6
        midnight = int(datetime.combine(date.fromisoformat(day), time(), ZoneInfo("UTC")).timestamp()) * 10**9
        for kind, schema in (("quote", "mbp-1"), ("status", "status")):
            req = tape[kind + "_request"]
            require(set(req) == REQUEST_KEYS and req["symbols"] == [symbol] and req["trading_date"] == day, "request identity differs")
            require(req["request_id"] == f"{day}-{symbol}-{schema}" and req["schema"] == schema
                    and req["dataset"] == "XNAS.ITCH" and req["stype_in"] == "raw_symbol" and req["end_exclusive"] is True, "request convention differs")
            require(midnight <= positive_int(req["start_ns"]) <= at - age < at < positive_int(req["end_ns"]) <= midnight + 86400 * 10**9, "request bounds differ")
            if kind == "status": require(req["start_ns"] == midnight, "status origin differs")
        require(tape["quote_request"]["end_ns"] == tape["status_request"]["end_ns"], "request ends differ")
        quotes, statuses = tape["quote_records"], tape["status_records"]
        require(bool(quotes) and bool(statuses), "complete nonempty source tapes required")
        previous = (-1, -1)
        for index, quote in enumerate(quotes):
            require(set(quote) == QUOTE_KEYS and quote["symbol"] == symbol, "quote fields differ")
            require(all(type(quote[k]) is int and quote[k] >= 0 for k in ("ts_recv_ns", "sequence", "bid_px_nanos", "ask_px_nanos", "bid_size", "ask_size", "source_record_index")), "quote numbers differ")
            key = (quote["ts_recv_ns"], quote["sequence"])
            require(key >= previous and quote["source_record_index"] == index and quote["source_request_sha256"] == digest(tape["quote_request"]), "native quote order/provenance differs")
            require(tape["quote_request"]["start_ns"] <= key[0] < tape["quote_request"]["end_ns"], "quote outside request")
            previous = key
        previous = -1
        for status in statuses:
            require(set(status) == {"symbol", "ts_recv_ns", "action", "is_trading"} and status["symbol"] == symbol, "status fields differ")
            require(type(status["action"]) is int and 0 <= status["action"] <= 14 and status["is_trading"] in {"Y", "N", "~"}, "status vocabulary differs")
            at_status = positive_int(status["ts_recv_ns"])
            require(previous <= at_status and tape["status_request"]["start_ns"] <= at_status < tape["status_request"]["end_ns"], "status order/bounds differ")
            previous = at_status
        past_quotes = [(q["ts_recv_ns"], q["sequence"], q["source_record_index"], q) for q in quotes if q["ts_recv_ns"] <= at]
        past_statuses = [(s["ts_recv_ns"], i, s) for i, s in enumerate(statuses) if s["ts_recv_ns"] <= at]
        if not past_quotes: return "unavailable", "no_quote_known_by_session_start", None, None
        quote = max(past_quotes, key=lambda row: row[:3])[-1]
        if at - quote["ts_recv_ns"] > age: return "unavailable", "stale_quote", None, None
        if not (0 < quote["bid_px_nanos"] < quote["ask_px_nanos"] < 9223372036854775807 and quote["bid_size"] > 0 and quote["ask_size"] > 0):
            return "unavailable", "latest_book_unusable", None, None
        if not past_statuses or past_statuses[-1][-1]["is_trading"] == "~":
            return "unavailable", "trading_status_unknown", None, None
        status = max(past_statuses, key=lambda row: row[:2])[-1]
        if status["is_trading"] == "N": return "unavailable", "trading_halted", None, None
        if any(s[0] == quote["ts_recv_ns"] for s in past_statuses):
            return "unavailable", "same_receive_time_status_quote_ambiguity", None, None
        if status["ts_recv_ns"] > quote["ts_recv_ns"]:
            return "unavailable", "quote_precedes_latest_status_transition", None, None
        return "valued", "fresh_causal_bid_and_unchanged_raw_share_units", quote, status
    except (ValueError, KeyError, TypeError, OverflowError):
        return "input_failure", "invalid_valuation_evidence", None, None


def verify_case(case, original_paths):
    program, result, inputs, value, verification = (checked(case[k]) for k in ("program", "result", "inputs", "valuation", "verification"))
    checked_tree(value); boundary(value); boundary(verification)
    verify_vector({"program": program, "result": result, "verification": value["producer_replay_verification"]}, original_paths)
    index = result["session_count"]
    require(index < 30, "no next session")
    slot, close = program["slots"][index], result["sessions"][-1]["close"]
    at, state = start_ns(slot), close["account_state"]
    require(inputs["contract_id"] == value["contract_id"] == ID and inputs["input_scope"] == "synthetic_component_fixture", "valuation scope differs")
    for key, expected in (("producer_program_content_sha256", program["content_sha256"]), ("producer_result_content_sha256", result["content_sha256"]),
                          ("previous_close_content_sha256", close["content_sha256"]), ("valuation_at_ns", at)):
        require(inputs[key] == value[key] == expected, "valuation binding differs: " + key)
    require(inputs["next_session_id"] == slot["session_id"] and value["next_slot_content_sha256"] == slot["content_sha256"] and value["path_id"] == slot["path_id"], "next slot differs")
    require(value["valuation_inputs_content_sha256"] == inputs["content_sha256"] and value["source_account_state"] == state, "source state or input pin differs")
    by_id = {p["activation_id"]: p for p in inputs["position_inputs"]}
    require(len(by_id) == len(inputs["position_inputs"]) and set(by_id) <= {p["activation_id"] for p in state["positions"]}, "position input inventory differs")
    require(len(value["position_valuations"]) == len(state["positions"]), "position valuation inventory differs")
    total, cost, complete, count = Decimal(0), Decimal(0), True, 0
    for position, mark in zip(state["positions"], value["position_valuations"]):
        checked(mark); boundary(mark)
        supplied = by_id.get(position["activation_id"])
        status, reason, quote, market_status = reference_mark(position, supplied, slot, close["content_sha256"], at)
        basis = Decimal(position["entry_price"]) * position["quantity"]
        cost += basis
        require(mark["valuation_status"] == status and mark["reason"] == reason, "causal mark disposition differs")
        for key, expected in (("activation_id", position["activation_id"]), ("symbol", position["symbol"]), ("quantity", position["quantity"]),
            ("position_content_sha256", digest(position)), ("valuation_at_ns", at), ("carried_cost_basis_usd", exact_money(basis)),
            ("input_content_sha256", None if supplied is None else digest(supplied)), ("basis", "fresh_raw_bid_reference_mark")):
            require(mark[key] == expected, "position evidence differs: " + key)
        if quote is None:
            complete = False
            require(all(mark[k] is None for k in ("mark_price_usd", "market_value_usd", "opening_unrealized_pnl_usd", "quote_source", "status_source")), "unknown mark fabricated")
        else:
            price = Decimal(quote["bid_px_nanos"]) / 10**9
            market_value = price * position["quantity"]
            total += market_value; count += 1
            require(mark["mark_price_usd"] == exact_money(price) and mark["market_value_usd"] == exact_money(market_value)
                and mark["opening_unrealized_pnl_usd"] == exact_money(market_value - basis), "bid mark arithmetic differs")
            require(mark["quote_source"] == {k: quote[k] for k in ("source_request_sha256", "source_record_index", "ts_recv_ns", "sequence", "bid_px_nanos", "bid_size")}, "selected quote differs")
            require(mark["status_source"] == {"source_request_sha256": digest(supplied["tape"]["status_request"]),
                **{k: market_status[k] for k in ("ts_recv_ns", "action", "is_trading")}}, "selected status differs")
    inventory = not state["pending_orders"] and not any(p["blocks_next_session"] for p in state["unresolved_inputs"])
    cash = Decimal(state["buying_power_usd"])
    expected = {"cash_usd": exact_money(cash), "position_cost_basis_usd": exact_money(cost),
        "position_market_value_usd": exact_money(total) if complete else None,
        "opening_unrealized_pnl_usd": exact_money(total - cost) if complete else None,
        "equity_usd": exact_money(cash + total) if complete and inventory else None,
        "all_position_marks_complete": complete, "confirmed_inventory_complete": inventory, "valuation_complete": complete and inventory,
        "cumulative_realized_pnl_usd": state["cumulative_realized_pnl_usd"], "cumulative_fees_usd": state["cumulative_fees_usd"]}
    require(value["account_valuation"] == expected, "account valuation differs")
    context = value["continuation_context"]
    require(context["next_session_id"] == slot["session_id"] and context["trading_date"] == slot["trading_date"], "continuation session differs")
    require(context["opening_equity_anchor_usd"] == expected["equity_usd"] and context["cash_usd"] == state["buying_power_usd"], "continuation capital differs")
    require(context["source_session_runtime_content_sha256"] == close["source_runtime_content_sha256"], "continuation runtime differs")
    require(all(context[k] == state[k] for k in ("positions", "pending_orders", "campaigns", "unresolved_inputs")), "carried account state changed")
    require(context["opening_marks"] == value["position_valuations"], "opening mark anchor differs")
    require(context["new_entry_or_exit_executed"] is False and context["pending_order_cancelled_by_valuation"] is False, "valuation executed an order")
    blockers = [{"kind": "position_valuation_unavailable", "activation_id": p["activation_id"], "reason": p["reason"]}
                for p in value["position_valuations"] if p["valuation_status"] != "valued"]
    if not inventory: blockers.append({"kind": "unresolved_order_or_account_inputs"})
    if state["positions"]: blockers.append({"kind": "continuous_carried_position_execution_not_integrated"})
    if complete and inventory and (cash + total <= 0 or cash <= 0): blockers.append({"kind": "nonpositive_equity_or_cash"})
    require(context["blockers"] == blockers and context["can_initialize_flat_session_ledger"] is (not blockers), "continuation blockers differ")
    if blockers:
        require(context["flat_session_ledger"] is None, "blocked account reset")
    else:
        ledger = context["flat_session_ledger"]
        account_state(ledger)
        require(not ledger["journal"] and ledger["identity"]["path_id"] == slot["path_id"] and ledger["identity"]["trading_date"] == slot["trading_date"], "flat day identity/reset differs")
        account = ledger["ledger"]["account"]
        require(Decimal(str(account["starting_equity"])) == cash + total and Decimal(str(account["starting_buying_power"])) == cash, "flat day capital reset")
    require(verification["verification_passed"] is True and verification["valuation_content_sha256"] == value["content_sha256"]
            and verification["valuation_inputs_content_sha256"] == inputs["content_sha256"], "valuation verification pins differ")
    return count


def verify(root, bundle, vectors_path):
    contract = read(root / f"research/strategy/{ID}.json"); boundary(contract)
    for path, sha in {**contract["frozen_parent_file_sha256"], **contract["implementation_file_sha256"]}.items():
        file = root / path
        require(file.is_file() and not file.is_symlink() and not any(p.is_symlink() for p in file.parents), "regular source required")
        require(hashlib.sha256(file.read_bytes()).hexdigest() == sha, "code/parent file differs: " + path)
    manifest = read(bundle / "freeze-manifest.json")
    require(manifest["contract_content_sha256"] == contract["content_sha256"], "registration freeze differs")
    require({p.name for p in bundle.iterdir()} == {*manifest["file_inventory"], "freeze-manifest.json"}, "bundle inventory differs")
    for name, spec in manifest["file_inventory"].items():
        payload = read(bundle / name); boundary(payload)
        raw = (bundle / name).read_bytes()
        require(len(raw) == spec["bytes"] and hashlib.sha256(raw).hexdigest() == spec["sha256"], "metadata bytes differ")
        require(payload["content_sha256"] == manifest["document_content_sha256"][name], "metadata content differs")
    plan = read(root / "research/runtime/sealed-historical-account-management-inputs-v0.1/account-session-input-plan.json")
    deps = read(bundle / "valuation-dependencies.json")
    expected = [{"path_id": p["path_id"], "previous_session_id": s["previous_session_id"], "next_session_id": s["session_id"],
        "next_slot_content_sha256": s["content_sha256"], "valuation_at_ns": start_ns(s),
        "position_inputs": "conditional_on_replay_derived_carried_positions_no_source_request_authorized"}
        for p in plan["paths"] for s in p["sessions"][1:]]
    require(deps["transitions"] == expected and len(expected) == deps["valuation_transition_count"] == 348, "original valuation transitions differ")
    require(deps["account_plan_content_sha256"] == plan["content_sha256"] and deps["path_count"] == 12 and deps["session_count"] == 360, "original plan differs")
    vectors = read(vectors_path); boundary(vectors)
    names = {"open_bid_mark", "flat_profit", "pending_order", "omitted_input", "unavailable_input", "subcent_mark", "stale", "halted", "unknown_status",
        "unusable_latest", "missing_units", "adjustment_required", "future_units", "missing_tape", "missing_position", "bad_tape_pin", "same_time_status"}
    names |= {"flat_" + p["path_id"] for p in plan["paths"]}
    require(len(vectors["vectors"]) == len(names) == 29 and {v["name"] for v in vectors["vectors"]} == names, "valuation vector population differs")
    with localcontext() as ctx:
        ctx.prec = 60
        marks = sum(verify_case(v, {p["path_id"]: p for p in plan["paths"]}) for v in vectors["vectors"])
    golden = {"open_bid_mark": "29990.98", "flat_profit": "30014.98", "subcent_mark": "29990.995",
              "pending_order": None, "omitted_input": None, "unavailable_input": "30000.00"}
    for vector in vectors["vectors"]:
        if vector["name"] in golden:
            require(vector["valuation"]["account_valuation"]["equity_usd"] == golden[vector["name"]], "golden equity differs")
    return sealed({"contract_id": ID, "verification_passed": True, "stdlib_only": True, "synthetic_only": True,
        "contract_content_sha256": contract["content_sha256"], "freeze_content_sha256": manifest["content_sha256"],
        "synthetic_vectors_content_sha256": vectors["content_sha256"], "case_count": 29, "independently_selected_marks": marks,
        "registered_paths": 12, "registered_sessions": 360, "valuation_transitions": 348, "historical_execution_count": 0,
        "source_execution_recomputed_by_independent_checker": False, "provider_calls": 0, **dict.fromkeys(CLOSED, False)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--vectors", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify(args.root, args.bundle or args.root / f"research/runtime/{ID}", args.vectors)
    raw = json.dumps(report, sort_keys=True, indent=2).encode() + b"\n"
    if args.output:
        require(not args.output.is_symlink() and not any(p.is_symlink() for p in args.output.parents), "symlink output rejected")
        with args.output.open("xb") as handle:
            if handle.write(raw) != len(raw): raise OSError("short independent verification write")
            handle.flush(); os.fsync(handle.fileno())
    print(raw.decode(), end="")


if __name__ == "__main__":
    main()
