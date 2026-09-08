"""Independent stdlib-only metadata and synthetic accounting verifier.

No project modules, provider clients, source tapes or retrospective datasets are
imported/read. Execution lineage remains the frozen simulator's responsibility;
this checker independently recomputes fees, journal cash, shares and net guards.
"""
import argparse
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_CEILING, localcontext
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ID = "sealed-historical-management-fee-reconciliation-v0.1"
TYPES = ("sec", "taf", "cat", "commission")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def checked(value):
    if not isinstance(value, dict) or value.get("content_sha256") != digest({k: v for k, v in value.items() if k != "content_sha256"}):
        raise ValueError("content commitment differs")
    return value


def read(path):
    if path.is_symlink() or not path.is_file() or any(p.is_symlink() for p in path.parents):
        raise ValueError("regular nonsymlink evidence file required")
    return checked(json.loads(path.read_text()))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    require(isinstance(value, str), "exact decimal string required")
    result = Decimal(value)
    require(result.is_finite(), "nonfinite money")
    return result


def fees(trades, day):
    require("2025-05-30" <= day <= "2025-07-17", "unregistered date")
    rate = Decimal("0.000035" if day < "2025-07-01" else "0.000022")
    exact = dict.fromkeys(TYPES, Decimal(0))
    seen_fills, seen_orders = set(), set()
    previous = -1
    for trade in trades:
        require(trade["fill_id"] not in seen_fills and trade["order_id"] not in seen_orders, "duplicate execution identity")
        seen_fills.add(trade["fill_id"]); seen_orders.add(trade["order_id"])
        qty, at = trade["quantity"], trade["timestamp_ns"]
        require(type(qty) is int and qty > 0 and type(at) is int and at >= previous, "invalid shares or time")
        require(datetime.fromtimestamp(at // 10**9, timezone.utc).astimezone(ZoneInfo("America/New_York")).date().isoformat() == day, "fee trading date differs")
        require(number(trade["price"]) > 0 and trade["side"] in ("buy", "sell"), "invalid price or side")
        previous = at
        exact["cat"] += rate * qty
        if trade["side"] == "sell":
            exact["taf"] += min(Decimal("0.000166") * qty, Decimal("8.30"))
    result = {kind + "_exact": value for kind, value in exact.items()}
    result.update({kind + "_charged": value.quantize(Decimal(".01"), rounding=ROUND_CEILING) for kind, value in exact.items()})
    result["total_charged"] = sum((result[kind + "_charged"] for kind in TYPES), Decimal(0))
    return result


def money_equal(actual, expected, label):
    require(set(actual) == set(expected), label + " fields differ")
    require(all(number(actual[k]) == v for k, v in expected.items()), label + " values differ")


def application(row, trades, day):
    before = fees(trades, day)
    trades.append(row["trade"])
    after = fees(trades, day)
    money_equal(row["cumulative_fees"], after, "cumulative fees")
    delta = {k: after[k + "_charged"] - before[k + "_charged"] for k in TYPES}
    delta["total"] = sum(delta.values(), Decimal(0))
    money_equal(row["incremental_charge"], delta, "incremental fees")
    return delta["total"]


def account_state(state):
    checked(state)
    checked(state["fee_book"])
    identity = state["identity"]
    require(state["fee_book"]["identity"] == identity, "cross-account fee book")
    for flag in ("historical_runtime_authorized", "historical_producer_authenticated", "financial_metrics_eligible", "account_close_evidence", "broker_statement_equivalence_verified"):
        require(state[flag] is False, "closed authority boundary changed")
    ledger = state["ledger"]["account"]
    cash = Decimal(str(ledger["starting_buying_power"]))
    gross = high = Decimal(0)
    positions, trades = {}, []
    previous_hash, previous_clock = None, (-1, -1)
    locked = False
    reason = None
    max_loss = Decimal("300" if ledger["account_class"] == "main" else "20")
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


def verify(root, bundle, vectors_path):
    contract = read(root / f"research/strategy/{ID}.json")
    for path, expected in {**contract["frozen_parent_file_sha256"], **contract["implementation_file_sha256"]}.items():
        require(hashlib.sha256((root / path).read_bytes()).hexdigest() == expected, "code/parent file differs: " + path)
    sources = read(root / f"research/strategy/{ID}-fee-sources.json")
    require(sources["content_sha256"] == contract["fee_sources_content_sha256"], "fee sources differ")
    manifest = read(bundle / "freeze-manifest.json")
    require(manifest["contract_content_sha256"] == contract["content_sha256"], "registration freeze differs")
    require({p.name for p in bundle.iterdir()} == {*manifest["file_inventory"], "freeze-manifest.json"}, "bundle inventory differs")
    for name, spec in manifest["file_inventory"].items():
        payload = read(bundle / name)
        raw = (bundle / name).read_bytes()
        require(len(raw) == spec["bytes"] and hashlib.sha256(raw).hexdigest() == spec["sha256"], "metadata bytes differ")
        require(payload["content_sha256"] == manifest["document_content_sha256"][name], "metadata content differs")
    mapping = read(bundle / "fee-session-map.json")
    plan = read(root / "research/runtime/sealed-historical-account-management-inputs-v0.1/account-session-input-plan.json")
    require(mapping["account_plan_content_sha256"] == plan["content_sha256"], "account plan differs")
    expected_paths = [{"path_id": p["path_id"], "sessions": [{"session_id": s["session_id"], "trading_date": s["trading_date"],
        "session_input_content_sha256": s["content_sha256"], "fee_period": "2025-1" if s["trading_date"] < "2025-07-01" else "2025-2"}
        for s in p["sessions"]]} for p in plan["paths"]]
    require(mapping["paths"] == expected_paths and len(expected_paths) == 12
            and sum(len(p["sessions"]) for p in expected_paths) == 360, "complete session map differs")
    vectors = read(vectors_path)
    require(vectors["synthetic_only"] is True and vectors["historical_execution_count"] == 0, "synthetic scope differs")
    expected_cases = {f"l1-{policy}-v0.1:{kind}" for policy in ("conservative", "stress") for kind in ("full", "partial", "zero")}
    expected_cases |= {"above_net_giveback", "equal_net_giveback", "small_net_loss_limit", "two_sequential_positions"}
    require(len(vectors["account_cases"]) == 10 and {c["case_id"] for c in vectors["account_cases"]} == expected_cases, "synthetic cases missing or duplicated")
    fills = 0
    with localcontext() as ctx:
        ctx.prec = 60
        for case in vectors["account_cases"]:
            account_state(case["initial"])
            fills += account_state(case["final"])
            require(case["final"]["journal"][:1] == case["initial"]["journal"], "entry prefix changed")
            key = case["case_id"]
            quantities_and_net = {"full": (0, "4.98"), "partial": (5, "0.98"), "zero": (10, "-0.01"),
                "above_net_giveback": (0, "4.995"), "equal_net_giveback": (0, "4.99"),
                "small_net_loss_limit": (0, "-20.00"), "two_sequential_positions": (0, "19.98")}
            quantity, net = quantities_and_net[key.split(":")[-1]]
            require(case["final"]["management"]["remaining_quantity"] == quantity
                    and number(case["final"]["exact_account"]["net_realized_pnl"]) == Decimal(net), "literal synthetic result differs")
        require(fills == 28, "confirmed synthetic execution population differs")
        require([c["day"] for c in vectors["fee_cases"]] == ["2025-06-30", "2025-07-01"], "fee boundary vectors missing")
        for case in vectors["fee_cases"]:
            trades = []
            for row in case["applications"]:
                application(row, trades, case["day"])
            require(trades == case["state"]["trades"], "fee vector journal differs")
            checked(case["state"])
            money_equal(case["state"]["fees"], fees(trades, case["day"]), "fee vector result")
    result = {"contract_id": ID, "verification_passed": True, "stdlib_only": True, "synthetic_only": True,
        "account_cases_verified": 10, "confirmed_execution_rows_verified": fills, "fee_boundary_cases_verified": 2,
        "paths_verified": 12, "session_slots_verified": 360,
        "contract_content_sha256": contract["content_sha256"], "freeze_content_sha256": manifest["content_sha256"],
        "synthetic_vectors_content_sha256": vectors["content_sha256"],
        "synthetic_vectors_file_sha256": hashlib.sha256(vectors_path.read_bytes()).hexdigest(),
        "historical_runtime_authorized": False, "broker_statement_equivalence_verified": False,
        "financial_metrics_eligible": False, "provider_calls": 0, "retrospective_inputs_read": False}
    return {**result, "content_sha256": digest(result)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--vectors", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.root, args.bundle or args.root / f"research/runtime/{ID}", args.vectors)
    raw = json.dumps(result, sort_keys=True, indent=2).encode() + b"\n"
    if args.output:
        if args.output.is_symlink() or any(p.is_symlink() for p in args.output.parents):
            raise ValueError("symlink output rejected")
        with args.output.open("xb") as handle:
            if handle.write(raw) != len(raw):
                raise OSError("short verification write")
    print(raw.decode(), end="")


if __name__ == "__main__":
    main()
