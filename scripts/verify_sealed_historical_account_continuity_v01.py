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

from verify_sealed_historical_account_state_producer_v01 import public_collections, ready, exact_money, checked_tree
from verify_sealed_historical_management_fee_reconciliation_v01 import checked, read, require, digest, number, application, fees, money_equal

ID = "sealed-historical-account-continuity-v0.1"
PARENT_CONTENT = "5e38846fd38ab2da86c7d97bfed55d080f9adfe6f1f7387f1132e177c5159a66"


def account_state(state):
    checked(state)
    checked(state["fee_book"])
    identity = state["identity"]
    require(state["fee_book"]["identity"] == identity, "cross-account fee book")
    for flag in ("historical_runtime_authorized", "historical_producer_authenticated", "financial_metrics_eligible", "account_close_evidence", "broker_statement_equivalence_verified"):
        require(state[flag] is False, "closed authority boundary changed")
    ledger = state["ledger"]["account"]
    cash = Decimal(str(ledger["starting_buying_power"]))
    gross = net = high = Decimal(0)
    positions, trades = {}, []
    previous_hash, previous_clock = None, (-1, -1)
    locked = False
    reason = None
    max_loss = Decimal(str(ledger["starting_equity"])) * Decimal(".01")
    for index, row in enumerate(state["journal"]):
        checked(row)
        require(row["sequence"] == index and row["previous_event_sha256"] == previous_hash, "journal hash chain differs")
        previous_hash = row["content_sha256"]
        clock = (row["known_at_ns"], row["clock_phase"])
        require(clock >= previous_clock, "journal causal order reversed")
        previous_clock = clock
        evidence = checked(row["execution_evidence"])
        fee = row["fee_application"]
        trade = fee["trade"]
        require(trade["quantity"] == evidence["quantity"] and trade["price"] == evidence["fill_price"]
                and trade["timestamp_ns"] == evidence["fill_time_ns"], "fee does not match confirmed execution")
        qty, price = trade["quantity"], number(trade["price"])
        require(trade["timestamp_ns"] <= clock[0], "future execution booked")
        charge = application(fee, trades, identity["trading_date"])
        activation = row["activation_id"]
        if trade["side"] == "buy":
            old = positions.get(activation)
            require(evidence["activation_id"] == activation and (old is None or not old["quantity"]), "entry overlaps campaign shares")
            require(old is None or old["entries"] < 2, "campaign entry ceiling exceeded")
            role = "starter" if old is None else "reentry"
            require(evidence["entry_role"] == evidence["accepted_ledger_event"]["role"] == role, "campaign entry role differs")
            require(old is None or evidence["plan_id"] not in old["plans"], "re-entry reused a plan")
            require(not locked, "entry after account lock")
            require(evidence["account_id"] == identity["account_id"] and evidence["path_id"] == identity["path_id"]
                    and evidence["scenario_id"] == identity["scenario_id"], "foreign entry context")
            require(trade["order_id"] == evidence["order"]["order_id"] and trade["fill_id"] == evidence["fill_id"], "buy identity differs")
            positions[activation] = {"quantity": qty, "entry": price, "gross": Decimal(0) if old is None else old["gross"],
                "fees": Decimal(0) if old is None else old["fees"], "fill_id": evidence["fill_id"],
                "entries": 1 if old is None else old["entries"] + 1,
                "ids": ([] if old is None else old["ids"]) + [evidence["fill_id"]],
                "plans": ([] if old is None else old["plans"]) + [evidence["plan_id"]]}
            cash -= price * qty + charge
            delta = Decimal(0)
        else:
            require(trade["timestamp_ns"] < clock[0] or clock[1] == 2, "equal-time feedback applied before market input")
            require(trade["order_id"] == evidence["order_id"] and trade["fill_id"] == "sell-fill-" + evidence["content_sha256"], "sell identity differs")
            position = positions[activation]
            require(position["fill_id"] == evidence["entry_fill_id"] and qty <= position["quantity"], "sell exceeds entry shares")
            position["quantity"] -= qty
            require(position["quantity"] == evidence["remaining_quantity"], "receipt remaining shares differ")
            delta = (price - position["entry"]) * qty
            gross += delta
            cash += price * qty - charge
        position = positions[activation]
        position["gross"] += delta
        position["fees"] += charge
        net = gross - fees(trades, identity["trading_date"])["total_charged"]
        high = max(high, net)
        if not locked:
            if net <= -max_loss:
                locked, reason = True, "daily_max_loss"
            elif high > 0 and net <= high / 2:
                locked, reason = True, "profit_giveback"
        require(number(row["gross_realized_delta"]) == delta and row["remaining_quantity"] == position["quantity"], "fill quantity/P&L differs")
        for key, expected in (("cash_after", cash), ("gross_realized_after", gross), ("net_realized_after", net), ("net_high_water_after", high)):
            require(number(row[key]) == expected, key + " differs")
    require(state["fee_book"]["trades"] == trades, "fee book journal differs")
    money_equal(state["fee_book"]["fees"], fees(trades, identity["trading_date"]), "final fees")
    exact = state["exact_account"]
    for key, expected in (("remaining_buying_power", cash), ("gross_realized_pnl", gross), ("net_realized_pnl", net), ("net_high_water_pnl", high), ("cash_shortfall", max(Decimal(0), -cash))):
        require(number(exact[key]) == expected, "final " + key + " differs")
    for key, expected in (("remaining_buying_power", cash), ("realized_pnl", net), ("high_water_pnl", high)):
        require(Decimal(str(ledger[key])) == expected, "net ledger " + key + " differs")
    require(ledger["locked"] == locked and ledger["lock_reason"] == reason, "net account guard differs")
    require(ledger["flatten_required"] == (locked and any(p["quantity"] for p in positions.values())), "flatten flag differs")
    require(set(exact["positions"]) == set(positions), "position inventory differs")
    for campaign in state["ledger"]["campaigns"]:
        activation = campaign["activation_id"]
        position = positions[activation]
        require(campaign["entry_fill_count"] == position["entries"] and campaign["reentry_count"] == position["entries"] - 1, "campaign counters reset")
        actual = exact["positions"][activation]
        require(actual["entry_fill_ids"] == position["ids"] and actual["entry_fill_id"] == position["fill_id"], "campaign fill history differs")
        require(number(actual["entry_price"]) == position["entry"] and number(actual["gross_realized_pnl"]) == position["gross"]
            and number(actual["fees_charged"]) == position["fees"], "campaign basis or totals differ")
        require(campaign["quantity"] == position["quantity"] == exact["positions"][activation]["quantity"], "ledger shares differ")
        require(Decimal(str(campaign["realized_pnl"])) == position["gross"] - position["fees"], "campaign net differs")
    sells = [r["execution_evidence"] for r in state["journal"] if r["fee_application"]["trade"]["side"] == "sell"]
    liquidity = [(r["source_request_sha256"], r["source_record_index"]) for r in sells]
    require(len(liquidity) == len(set(liquidity)), "sell liquidity reused")
    require(state["consumed_sell_liquidity"] == [list(k) for k in sorted(liquidity)], "consumed liquidity lost on resume/re-entry")
    if state["management"] is None:
        require(not any(p["quantity"] for p in positions.values()), "open shares lost on release")
        require(ledger["total_open_risk"] == 0, "flat account risk differs")
        return len(trades)
    engine = checked(state["management"])
    activation = engine["entry"]["activation_id"]
    require(engine["remaining_quantity"] == positions[activation]["quantity"], "management shares differ")
    confirmed = [r["execution_evidence"] for r in state["journal"] if r["fee_application"]["trade"]["side"] == "sell" and r["execution_evidence"]["entry_fill_id"] == engine["entry"]["fill_id"]]
    require(engine["fills"] == confirmed, "unconfirmed or omitted sell execution")
    expected_risk = Decimal(0)
    for key, position in positions.items():
        if position["quantity"]:
            require(key == activation, "overlapping position not supported")
            expected_risk += max(Decimal(0), position["entry"] - Decimal(str(engine["active_stop_price"]))) * position["quantity"]
    require(Decimal(str(ledger["total_open_risk"])) == expected_risk, "confirmed stop risk differs")
    return len(trades)


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
    campaign_entries = {}
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
                count = campaign_entries.get(op["activation_id"], 0)
                if count >= 2:
                    require(disposition == "blocked_campaign_entry_limit", "third campaign entry not blocked")
                else:
                    require(disposition in {"entry_submitted", "no_whole_share_capacity"}, "unsupported entry disposition")
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
                count = campaign_entries.get(op["activation_id"], 0)
                require(count < 2 and evidence["entry_role"] == ("starter" if count == 0 else "reentry"), "invalid campaign entry role/count")
                campaign_entries[op["activation_id"]] = count + 1
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
            if d["disposition"] in {"unavailable_input", "unprocessed_available_input", "blocked_prior_state"}]
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


def verify_checkpoint(item, originals):
    p, c, full = checked(item["program"]), checked(item["checkpoint"]), checked(item["uninterrupted_result"])
    checked_tree(c)
    verify_vector({"program": p, "result": full}, originals)
    require(item["resumed_result_content_sha256"] == full["content_sha256"], "resumed result differs from uninterrupted commitment")
    index, at = len(p["sessions"]) - 1, c["through_ns"]
    slot, source = p["slots"][index], p["sessions"][index]
    require(c["contract_id"] == ID and c["program_content_sha256"] == p["content_sha256"]
        and c["path_id"] == p["path_id"] and c["session_id"] == slot["session_id"]
        and c["session_index"] == index and c["seed_application_count"] == 1
        and c["source_slot_content_sha256"] == slot["content_sha256"], "checkpoint identity or seed differs")
    require(c["prior_completed_sessions"] == full["sessions"][:index], "checkpoint preceding history differs")
    opening = full["initial_account_state"] if index == 0 else full["sessions"][index - 1]["close"]["account_state"]
    prior = None if index == 0 else full["sessions"][index - 1]["close"]["content_sha256"]
    require(c["opening_account_state"] == opening and c["previous_close_content_sha256"] == prior, "checkpoint opening state differs")
    runtime = full["sessions"][index]["runtime"]
    expected_events = [e for e in runtime["events"] if e["at_ns"] <= at]
    require(c["events"] == expected_events, "checkpoint event prefix differs")
    require(c["opportunity_dispositions"] == [{"opportunity_id": e["opportunity_id"], "disposition": e["disposition"]}
        for e in expected_events if e["event_type"] == "opportunity_disposition"], "checkpoint decisions differ")
    require(c["failure"] is None, "checkpoint vectors require valid source streams")
    current = c["reconciliation_snapshot"]
    account_state(current)
    expected_journal = [j for j in runtime["reconciliation_snapshot"]["journal"] if j["known_at_ns"] <= at]
    require(current["journal"] == expected_journal, "checkpoint contains future or missing fills")
    active, pending = None, None
    for event in expected_events:
        kind, oid = event["event_type"], event["opportunity_id"]
        if kind == "opportunity_disposition" and event["disposition"] == "entry_submitted":
            pending = {"opportunity_id": oid, **event["order"], "confirmed_filled_quantity": 0, "unreconciled_execution_feedback": None}
        elif kind == "entry_fill_confirmed":
            active = oid
            pending["confirmed_filled_quantity"] = expected_journal[event["journal_index"]]["execution_evidence"]["quantity"]
        elif kind == "entry_cancel_acknowledged":
            pending = None
        elif kind == "capacity_released":
            active = None
    require(c["active_opportunity_id"] == active and c["pending_entry_reservation"] == pending, "checkpoint active or pending reservation differs")
    specs = {i["position"]["entry_input"]["window"]["opportunity"]["opportunity_id"]: i["position"] for i in source["opportunities"]}
    window = None if active is None else specs[active]["entry_input"]["window"]
    require(c["active_original_window"] == window, "checkpoint extended or changed original window")
    progress = []
    final_clock = 0
    for oid in sorted(specs):
        spec = specs[oid]
        final_clock = max(final_clock, spec["entry_input"]["window"]["end_ns"] - 1)
        for name, resource in (("bars", "raw_sip_1m_bars"), ("trades", "sip_transactions")):
            records = [r for r in spec[name] if r["timestamp_ns"] + (60 * 10**9 if name == "bars" else 0) <= at]
            raw = b"".join(json.dumps(r, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n" for r in records)
            progress.append({"opportunity_id": oid, "resource": resource, "rows": len(records), "sha256": hashlib.sha256(raw).hexdigest()})
    require(c["processed_streams"] == sorted(progress, key=lambda r: (r["opportunity_id"], r["resource"])), "processed source prefix differs")
    complete = at >= final_clock
    require(c["complete_streams_verified"] == complete, "unfinished source stream declared complete")
    status = ("original_window_exhausted" if window is not None and at >= window["end_ns"] - 1
        else "session_streams_complete" if complete else "continuable_original_window")
    require(c["status"] == status, "checkpoint continuation status differs")
    engine = current["management"]
    if active is None:
        require(engine is None, "released checkpoint kept a management engine")
    else:
        require(engine["entry"]["opportunity_id"] == active, "checkpoint carries another entry")
        entry = engine["entry"]
        orders = [e for e in expected_events if e["event_type"] == "sell_submitted" and e["opportunity_id"] == active]
        target_quantity = entry["quantity"] // 2
        target_filled = sum(f["quantity"] for f in engine["fills"] if f["reason"] == "first_target")
        breakeven = target_quantity > 0 and target_filled == target_quantity
        require(engine["target_quantity"] == target_quantity and engine["target_filled_quantity"] == target_filled
            and engine["breakeven_active"] == breakeven, "target confirmation lost or invented")
        require(number(str(engine["active_stop_price"])) == number(entry["fill_price"] if breakeven else str(entry["initial_stop_price"])), "checkpoint stop reset or moved early")
        require(engine["target_attempted"] == any(e["reason"] == "first_target" for e in orders)
            and engine["full_exit_attempted"] == any(e["reason"] != "first_target" for e in orders), "attempt history reset")
        outstanding = [e["order"] for e in orders if e["order"]["cancel_ack_ts_ns"] > at]
        require(len(outstanding) <= 1 and engine["pending_order"] == bool(outstanding), "sell cancellation fabricated")
        reserved = 0 if not outstanding else outstanding[0]["quantity"] - sum(f["quantity"] for f in engine["fills"] if f["order_id"] == outstanding[0]["order_id"])
        require(engine["reserved_sell_quantity"] == reserved, "checkpoint sell reservation differs")
    return 1


def verify(root, bundle, vectors_path):
    contract = read(root / f"research/strategy/{ID}.json")
    require(read(root / "research/strategy/sealed-historical-account-scheduler-v0.1.json")["content_sha256"] == PARENT_CONTENT, "frozen scheduler parent differs")
    for path, sha in {**contract["frozen_parent_file_sha256"], **contract["implementation_file_sha256"]}.items():
        require(hashlib.sha256((root / path).read_bytes()).hexdigest() == sha, "code or parent bytes differ: " + path)
    manifest = read(bundle / "freeze-manifest.json")
    require(manifest["contract_content_sha256"] == contract["content_sha256"], "registration freeze differs")
    require({p.name for p in bundle.iterdir()} == {*manifest["file_inventory"], "freeze-manifest.json"}, "metadata inventory differs")
    for name, expected in manifest["file_inventory"].items():
        path = bundle / name
        require(path.stat().st_size == expected["bytes"] and hashlib.sha256(path.read_bytes()).hexdigest() == expected["sha256"], "metadata bytes differ")
        require(read(path)["content_sha256"] == manifest["document_content_sha256"][name], "metadata content differs")
    mapping = read(bundle / "continuity-dependencies.json")
    original = read(root / "research/runtime/sealed-historical-account-state-producer-v0.1/account-state-dependencies.json")
    require(mapping["slots"] == original["slots"] and mapping["account_plan_content_sha256"] == original["account_plan_content_sha256"], "original opportunity plan changed")
    require(mapping["session_count"] == 360 and mapping["path_count"] == 12 and mapping["seed_applications"] == 12 and mapping["previous_close_dependencies"] == 348, "original dimensions differ")
    plan = read(root / "research/runtime/sealed-historical-account-management-inputs-v0.1/account-session-input-plan.json")
    paths = {p["path_id"]: p for p in plan["paths"]}
    vectors = read(vectors_path)
    require(vectors["contract_id"] == ID and vectors["synthetic_only"] is True and vectors["historical_execution_count"] == 0, "evidence scope differs")
    required = {"collision", "delayed", "unfilled", "partial_carry", "pending_input_failure", "omitted", "unavailable", "risk_flatten",
        "l1-conservative-v0.1-reentry", "l1-stress-v0.1-reentry", "small-reentry", "reentry-open", "reentry-cash-carry", "new-activation"} | {"empty-" + p for p in paths}
    require(len(vectors["vectors"]) == len(required) and {v["name"] for v in vectors["vectors"]} == required, "synthetic coverage differs")
    fills = events = sessions = checkpoints = 0
    with localcontext() as context:
        context.prec = 60
        for vector in vectors["vectors"]:
            f, e, s = verify_vector(vector, paths)
            fills += f; events += e; sessions += s
            for item in vector["checkpoints"]:
                checkpoints += verify_checkpoint(item, paths)
    require(checkpoints == 40, "continuation checkpoint coverage differs")
    report = {"verification_passed": True, "contract_id": ID, "contract_content_sha256": contract["content_sha256"],
        "freeze_content_sha256": manifest["content_sha256"], "vectors_content_sha256": vectors["content_sha256"],
        "case_count": len(required), "continuation_checkpoints": checkpoints, "session_checkpoints": sessions, "confirmed_journal_fills": fills, "scheduler_events": events,
        "independent_scarcity_order_and_reservation_chronology_verified": True, "independent_fee_share_cash_and_net_guards_verified": True,
        "independent_campaign_reentry_and_checkpoint_accounting_verified": True, "production_modules_imported": False, "market_fill_simulation_independently_reimplemented": False,
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
