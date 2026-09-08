"""Independent stdlib-only accounting and account-checkpoint verifier.

Recomputes confirmed journal money, daily fees/guards and cross-session carry.
The frozen independent fee checker supplies only Decimal arithmetic and hash
helpers. No production module is imported. Source execution is separately
recomputed by verify_path; this checker is not a market-source authenticator.
"""
import argparse
from copy import deepcopy
from decimal import Decimal, localcontext
import hashlib
import json
import os
from pathlib import Path

from verify_sealed_historical_management_fee_reconciliation_v01 import (
    digest, checked, read, require, number, fees, money_equal, application)

ID = "sealed-historical-account-state-producer-v0.1"
CLOSED = ("retrospective_inputs_read", "historical_runtime_authorized", "historical_producer_authenticated",
          "financial_metrics_eligible", "account_close_evidence", "broker_statement_equivalence_verified",
          "policy_promotion_eligible", "original_market_source_provenance_authenticated",
          "continuous_account_order_integration_verified", "next_session_open_position_valuation_verified")
STATE_KEYS = {"equity_usd", "buying_power_usd", "cumulative_realized_pnl_usd", "cumulative_fees_usd",
              "positions", "pending_orders", "campaigns", "unresolved_inputs"}


def sealed(value):
    value = {k: v for k, v in value.items() if k != "content_sha256"}
    return dict(value, content_sha256=digest(value))


def boundary(value):
    require(value["provider_calls"] == 0 and all(value[k] is False for k in CLOSED), "producer boundary differs")


def checked_tree(value):
    if isinstance(value, dict):
        if "content_sha256" in value:
            checked(value)
        for child in value.values():
            checked_tree(child)
    elif isinstance(value, list):
        for child in value:
            checked_tree(child)


def exact_money(value):
    number = Decimal(value)
    if number == 0:
        return "0.00"
    integer, _, fraction = format(number, "f").partition(".")
    return integer + "." + fraction.rstrip("0").ljust(2, "0")


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
            require(activation not in positions and evidence["activation_id"] == activation, "duplicate or foreign entry")
            require(not locked, "entry after account lock")
            require(evidence["account_id"] == identity["account_id"] and evidence["path_id"] == identity["path_id"]
                    and evidence["scenario_id"] == identity["scenario_id"], "foreign entry context")
            require(trade["order_id"] == evidence["order"]["order_id"] and trade["fill_id"] == evidence["fill_id"], "buy identity differs")
            positions[activation] = {"quantity": qty, "entry": price, "gross": Decimal(0), "fees": Decimal(0), "fill_id": evidence["fill_id"]}
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
        require(campaign["quantity"] == position["quantity"] == exact["positions"][activation]["quantity"], "ledger shares differ")
        require(Decimal(str(campaign["realized_pnl"])) == position["gross"] - position["fees"], "campaign net differs")
    if state["management"] is None:
        require(not any(p["quantity"] for p in positions.values()), "open shares lost on release")
        require(ledger["total_open_risk"] == 0, "flat account risk differs")
        return len(trades)
    engine = checked(state["management"])
    activation = engine["entry"]["activation_id"]
    require(engine["remaining_quantity"] == positions[activation]["quantity"], "management shares differ")
    confirmed = [r["execution_evidence"] for r in state["journal"] if r["activation_id"] == activation and r["fee_application"]["trade"]["side"] == "sell"]
    require(engine["fills"] == confirmed, "unconfirmed or omitted sell execution")
    expected_risk = Decimal(0)
    for key, position in positions.items():
        if position["quantity"]:
            require(key == activation, "overlapping position not supported")
            expected_risk += max(Decimal(0), position["entry"] - Decimal(str(engine["active_stop_price"]))) * position["quantity"]
    require(Decimal(str(ledger["total_open_risk"])) == expected_risk, "confirmed stop risk differs")
    return len(trades)


def public_collections(snapshot):
    engine = snapshot["management"]
    if engine is None:
        return [], [], []
    entry = engine["entry"]
    positions, pending, unresolved = [], [], []
    if engine["remaining_quantity"]:
        positions.append({"activation_id": entry["activation_id"], "symbol": entry["symbol"],
            "entry_fill_id": entry["fill_id"], "quantity": engine["remaining_quantity"], "entry_price": entry["fill_price"],
            "active_stop_price": str(engine["active_stop_price"]), "target_quantity": engine["target_quantity"],
            "target_filled_quantity": engine["target_filled_quantity"], "management_status": engine["status"],
            "source_management_content_sha256": engine["content_sha256"], "valuation_usd": None})
    if (entry["entry_cancel_ack_ns"], 2) > (engine["clock_ns"], engine["clock_phase"]):
        pending.append({"kind": "entry_cancel_pending", "order_id": entry["order"]["order_id"],
            "quantity": entry["order"]["quantity"], "confirmed_filled_quantity": entry["quantity"],
            "remaining_order_quantity": entry["order"]["quantity"] - entry["quantity"],
            "cancel_ack_ts_ns": entry["entry_cancel_ack_ns"]})
    if engine["pending_order"]:
        order = next(e["order"] for e in reversed(engine["events"]) if e["event_type"] == "sell_submitted")
        pending.append({"kind": "sell_cancel_pending", **deepcopy(order),
            "confirmed_filled_quantity": sum(f["quantity"] for f in engine["fills"] if f["order_id"] == order["order_id"]),
            "remaining_order_quantity": engine["reserved_sell_quantity"]})
    if engine["outstanding_intent"] is not None:
        unresolved.append({"kind": "unsubmitted_exit_intent", "blocks_next_session": True,
                           "intent": deepcopy(engine["outstanding_intent"])})
    return positions, pending, unresolved


def ready(state):
    return (not state["positions"] and not state["pending_orders"]
        and not any(v["blocks_next_session"] for v in state["unresolved_inputs"])
        and all(state[k] is not None and number(state[k]) > 0 for k in ("equity_usd", "buying_power_usd")))


def verify_vector(vector, original_paths):
    program, result, verification = (checked(vector[k]) for k in ("program", "result", "verification"))
    checked_tree(result)
    require(set(program) == {"contract_id", "artifact_type", "input_scope", "path_id", "slots", "sessions", "content_sha256"}, "program fields differ")
    require(program["contract_id"] == result["contract_id"] == ID and program["input_scope"] == "synthetic_component_fixture", "program scope differs")
    original = original_paths[program["path_id"]]
    slots = program["slots"]
    require(len(slots) == 30 and 1 <= len(program["sessions"]) <= 30, "path prefix length differs")
    for slot, expected in zip(slots, original["sessions"]):
        checked(slot)
        keys = set(expected) - {"content_sha256", "opportunity_inputs", "unavailable_opportunity_count", "source_date_has_no_micro_decisions"}
        require(set(slot) == set(expected) and all(slot[k] == expected[k] for k in keys), "slot identity differs")
        refs = slot["opportunity_inputs"]
        require(len({v["opportunity_id"] for v in refs}) == len(refs), "duplicate opportunity")
        require(slot["unavailable_opportunity_count"] == sum(r["input_status"] == "unavailable" for r in refs), "unavailable count differs")
    capital = "30000.00" if slots[0]["account_key"] == "main_account" else "2000.00"
    opening = {"equity_usd": capital, "buying_power_usd": capital, "cumulative_realized_pnl_usd": "0.00",
               "cumulative_fees_usd": "0.00", "positions": [], "pending_orders": [], "campaigns": [], "unresolved_inputs": []}
    require(result["initial_account_state"] == opening and result["seed_application_count"] == 1, "once-only seed differs")
    require(result["program_content_sha256"] == program["content_sha256"] and result["slot_catalog_sha256"] == digest(slots), "external program binding differs")
    require(result["path_id"] == program["path_id"] and result["seed_content_sha256"] == slots[0]["seed_content_sha256"], "path/seed differs")
    require(result["session_count"] == len(result["sessions"]) == len(program["sessions"]), "session count differs")
    previous_sha, fills = None, 0
    for index, (source, pair) in enumerate(zip(program["sessions"], result["sessions"])):
        slot, runtime, close = slots[index], checked(pair["runtime"]), checked(pair["close"])
        boundary(runtime); boundary(close)
        require(set(source) == {"session_id", "positions"}, "source session fields differ")
        require(source["session_id"] == runtime["session_id"] == close["session_id"] == slot["session_id"], "session identity differs")
        require(close["path_id"] == runtime["path_id"] == program["path_id"] and close["trading_date"] == slot["trading_date"], "session path/date differs")
        require(close["session_index"] == index and close["seed_applied"] is (index == 0), "session seed/index differs")
        require(close["previous_close_content_sha256"] == previous_sha and close["source_runtime_content_sha256"] == runtime["content_sha256"], "close chain differs")
        require(close["source_slot_content_sha256"] == runtime["source_slot_content_sha256"] == slot["content_sha256"], "source slot differs")
        require(runtime["opening_account_state_sha256"] == digest(opening) and runtime["session_program_sha256"] == digest(source), "opening/program differs")
        blocked = not ready(opening)
        require(runtime["blocked_before_execution"] == blocked, "blocked state differs")
        require(len(runtime["position_results"]) == len(source["positions"]), "position results missing")
        dispositions = [{**r, "disposition": "unavailable_input"} for r in slot["opportunity_inputs"] if r["input_status"] == "unavailable"]
        refs = {r["opportunity_id"]: r for r in slot["opportunity_inputs"]}
        seen, failures = set(), []
        previous_journal = []
        for spec, output in zip(source["positions"], runtime["position_results"]):
            checked(output); boundary(output)
            oid = spec["entry_input"]["window"]["opportunity"]["opportunity_id"]
            require(not blocked and not failures and oid not in seen and refs[oid]["input_status"] == "available", "invalid position execution")
            require(output["position_program_sha256"] == digest(spec), "position source commitment differs")
            seen.add(oid)
            disposition = "executed_source_program" if output["status"] == "complete" else "input_failure"
            require(output["complete_streams_verified"] is (output["status"] == "complete"), "stream completion differs")
            if output["status"] == "complete":
                for name, resource in (("bars", "raw_sip_1m_bars"), ("trades", "sip_transactions")):
                    raw = b"".join(json.dumps(v, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n" for v in spec[name])
                    require(spec["expected_streams"][resource] == {"rows": len(spec[name]), "sha256": hashlib.sha256(raw).hexdigest()}, "complete stream differs")
            else:
                require(output["status"] == "input_failure", "position status differs")
                failures.append({"kind": "position_input_failure", "opportunity_id": oid, "blocks_next_session": True,
                    "position_result_content_sha256": output["content_sha256"], "stage": output["stage"]})
            snapshot = output["account_snapshot"]
            account_state(snapshot)
            require(snapshot["journal"][:len(previous_journal)] == previous_journal, "session journal reset")
            previous_journal = snapshot["journal"]
            dispositions.append({**refs[oid], "disposition": disposition, "position_result_content_sha256": output["content_sha256"]})
        dispositions += [{**r, "disposition": "unprocessed_available_input"} for r in refs.values()
                         if r["input_status"] == "available" and r["opportunity_id"] not in seen]
        require(dispositions == runtime["opportunity_dispositions"], "opportunity disposition differs")
        gaps = [{"kind": d["disposition"], "opportunity_id": d["opportunity_id"],
            "availability_content_sha256": d["availability_content_sha256"], "reason": d["reason"],
            "blocks_next_session": d["disposition"] == "unprocessed_available_input"}
            for d in dispositions if d["disposition"] in ("unavailable_input", "unprocessed_available_input")]
        snapshot = runtime["reconciliation_snapshot"]
        if blocked:
            require(snapshot is None and not source["positions"], "blocked state was executed")
            expected = deepcopy(opening)
            expected["unresolved_inputs"] += gaps + [{"kind": "preceding_state_blocks_execution",
                "blocks_next_session": True, "previous_close_content_sha256": previous_sha}]
            gross = net = charged = Decimal(0)
        else:
            fills += account_state(snapshot)
            ledger = snapshot["ledger"]["account"]
            require(Decimal(str(ledger["starting_equity"])) == number(opening["equity_usd"])
                and Decimal(str(ledger["starting_buying_power"])) == number(opening["buying_power_usd"]), "opening capital reset")
            require(snapshot["journal"] == previous_journal, "final journal differs")
            require(snapshot["identity"]["path_id"] == slot["path_id"] and snapshot["identity"]["trading_date"] == slot["trading_date"]
                and snapshot["identity"]["scenario_id"] == slot["execution_scenario_id"], "account-day identity differs")
            positions, pending, extra = public_collections(snapshot)
            exact = snapshot["exact_account"]
            gross, net = number(exact["gross_realized_pnl"]), number(exact["net_realized_pnl"])
            charged = fees(snapshot["fee_book"]["trades"], slot["trading_date"])["total_charged"]
            expected = {"equity_usd": None if positions else exact_money(number(opening["equity_usd"]) + net),
                "buying_power_usd": exact_money(number(exact["remaining_buying_power"])),
                "cumulative_realized_pnl_usd": exact_money(number(opening["cumulative_realized_pnl_usd"]) + net),
                "cumulative_fees_usd": exact_money(number(opening["cumulative_fees_usd"]) + charged),
                "positions": positions, "pending_orders": pending, "campaigns": opening["campaigns"] + snapshot["ledger"]["campaigns"],
                "unresolved_inputs": opening["unresolved_inputs"] + gaps + failures + extra}
        require(set(close["account_state"]) == STATE_KEYS and close["account_state"] == expected, "derived account state differs")
        for key, value in (("session_gross_realized_pnl_usd", gross), ("session_net_realized_pnl_usd", net), ("session_fees_usd", charged)):
            require(runtime[key] == exact_money(value), "session delta differs")
        require(close["next_session_flat_cash_execution_ready"] is ready(expected), "handoff readiness differs")
        status = "blocked_prior_state" if blocked else "open_requires_valuation" if expected["positions"] else "flat_state_ready" if ready(expected) else "incomplete_or_unfunded"
        require(close["checkpoint_status"] == status, "checkpoint status differs")
        cent_exact = all(expected[k] is None or number(expected[k]) == number(expected[k]).quantize(Decimal(".01"))
                         for k in ("equity_usd", "buying_power_usd", "cumulative_realized_pnl_usd", "cumulative_fees_usd"))
        transport = sealed({"session_id": slot["session_id"], "path_id": slot["path_id"], "trading_date": slot["trading_date"],
                           "source_runtime_content_sha256": runtime["content_sha256"], "account_state": expected}) if cent_exact else None
        require(close["frozen_cent_transport"] == transport, "exact cent compatibility differs")
        opening, previous_sha = expected, close["content_sha256"]
    require(result["last_close_content_sha256"] == verification["last_close_content_sha256"] == previous_sha, "final close pin differs")
    require(verification["verification_passed"] is True and verification["producer_state_authenticated_by_replay"] is True, "replay verification absent")
    require(verification["program_content_sha256"] == program["content_sha256"] and verification["result_content_sha256"] == result["content_sha256"], "verification pins differ")
    boundary(result); boundary(verification)
    return fills


def verify(root, bundle, vectors_path):
    contract = read(root / f"research/strategy/{ID}.json")
    boundary(contract)
    for path, expected in {**contract["frozen_parent_file_sha256"], **contract["implementation_file_sha256"]}.items():
        file = root / path
        require(file.is_file() and not file.is_symlink() and not any(p.is_symlink() for p in file.parents), "regular source required")
        require(hashlib.sha256(file.read_bytes()).hexdigest() == expected, "code/parent file differs: " + path)
    manifest = read(bundle / "freeze-manifest.json")
    require(manifest["contract_content_sha256"] == contract["content_sha256"], "registration freeze differs")
    require({p.name for p in bundle.iterdir()} == {*manifest["file_inventory"], "freeze-manifest.json"}, "bundle inventory differs")
    for name, spec in manifest["file_inventory"].items():
        payload = read(bundle / name); boundary(payload)
        raw = (bundle / name).read_bytes()
        require(len(raw) == spec["bytes"] and hashlib.sha256(raw).hexdigest() == spec["sha256"], "metadata bytes differ")
        require(payload["content_sha256"] == manifest["document_content_sha256"][name], "metadata content differs")
    plan = read(root / "research/runtime/sealed-historical-account-management-inputs-v0.1/account-session-input-plan.json")
    dependency = read(bundle / "account-state-dependencies.json")
    expected = [{"path_id": p["path_id"], "session_id": s["session_id"], "trading_date": s["trading_date"],
        "session_index": s["session_index"], "previous_session_id": s["previous_session_id"],
        "source_slot_content_sha256": s["content_sha256"], "seed_applied": s["seed_applied"], "opportunity_inputs": s["opportunity_inputs"]}
        for p in plan["paths"] for s in p["sessions"]]
    require(dependency["slots"] == expected and dependency["account_plan_content_sha256"] == plan["content_sha256"], "original dependencies differ")
    require((dependency["path_count"], dependency["session_count"], dependency["seed_applications"], dependency["previous_close_dependencies"]) == (12, 360, 12, 348), "dependency counts differ")
    require(sum(len(s["opportunity_inputs"]) for s in expected) == 744 and sum(r["input_status"] == "unavailable" for s in expected for r in s["opportunity_inputs"]) == 162, "original population differs")
    vectors = read(vectors_path); boundary(vectors)
    names = {"profit_continuity", "subcent_continuity", "partial_position", "pending_input_failure", "unavailable_retained",
             "available_omitted", "small_loss_day_reset", "serial_positions"} | {"empty_" + p["path_id"] for p in plan["paths"]}
    require(len(vectors["vectors"]) == len(names) == 20 and {v["name"] for v in vectors["vectors"]} == names, "vector population differs")
    paths = {p["path_id"]: p for p in plan["paths"]}
    with localcontext() as ctx:
        ctx.prec = 60
        fills = sum(verify_vector(v, paths) for v in vectors["vectors"])
    by_name = {v["name"]: v["result"] for v in vectors["vectors"]}
    golden = {"profit_continuity": ("30019.96", "19.96", "0.04"), "subcent_continuity": ("30004.995", "4.995", "0.02"),
        "partial_position": ("29950.98", "0.98", "0.02"), "pending_input_failure": ("29899.99", "-0.01", "0.01"),
        "unavailable_retained": ("30000.00", "0.00", "0.00"), "available_omitted": ("30000.00", "0.00", "0.00"),
        "small_loss_day_reset": ("1980.00", "-20.00", "0.02"), "serial_positions": ("30029.98", "29.98", "0.02")}
    for name, values in golden.items():
        state = by_name[name]["sessions"][-1]["close"]["account_state"]
        require(tuple(state[k] for k in ("buying_power_usd", "cumulative_realized_pnl_usd", "cumulative_fees_usd")) == values, "golden accounting differs: " + name)
    return sealed({"contract_id": ID, "verification_passed": True, "stdlib_only": True, "synthetic_only": True,
        "contract_content_sha256": contract["content_sha256"], "freeze_content_sha256": manifest["content_sha256"],
        "synthetic_vectors_content_sha256": vectors["content_sha256"], "case_count": 20,
        "session_checkpoints_checked": sum(v["result"]["session_count"] for v in vectors["vectors"]),
        "confirmed_journal_fills_checked": fills, "registered_paths": 12, "registered_sessions": 360,
        "once_only_seeds": 12, "previous_close_dependencies": 348, "historical_execution_count": 0,
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
            if handle.write(raw) != len(raw):
                raise OSError("short independent verification write")
            handle.flush(); os.fsync(handle.fileno())
    print(raw.decode(), end="")


if __name__ == "__main__":
    main()
