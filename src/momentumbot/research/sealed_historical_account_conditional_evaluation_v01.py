"""Conditional accounting of one accepted replay; no market replay or labels.

Strict observed-update withholds are bound to the unchanged unavailable runtime
entries before any results are released. Alternative paths are never pooled.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

import verify_sealed_historical_account_hosted_acceptance_v01 as accepted
from momentumbot.research import sealed_historical_entry_reference_evidence_v01 as evidence

ID = "sealed-historical-account-conditional-evaluation-v0.1"
PARENT = "d9b2bd3cb5164c651acc8f24a6eddcaf4d935ac8"
PARENT_TREE = "8acce39b1df31c64c2a4b19a1fc67ac498affb5f"
EVIDENCE_CONTRACT = "6025d10ad774b1edd9dc2101241efe4df575b9a329ce042ebe58739d5e4b9a62"
EVIDENCE_RESULT = "b47ba35fa6bed02db623faa6ded834447557d776fc3b35cd506632218d8760ce"
BASE = f"research/data-audits/{accepted.ID}"
OBSERVATIONS = f"research/data-audits/{evidence.ID}/report.json"
OWN_FILES = (
    "src/momentumbot/research/sealed_historical_account_conditional_evaluation_v01.py",
    "scripts/evaluate_sealed_historical_account_conditional_v01.py",
    "tests/test_sealed_historical_account_conditional_evaluation_v01.py",
)
DATES = ("2025-05-30", "2025-06-02", "2025-06-03", "2025-06-04", "2025-06-05",
    "2025-06-06", "2025-06-09", "2025-06-10", "2025-06-11", "2025-06-12",
    "2025-06-13", "2025-06-16", "2025-06-17", "2025-06-18", "2025-06-20",
    "2025-06-23", "2025-06-24", "2025-06-25", "2025-06-26", "2025-06-27",
    "2025-07-01", "2025-07-02", "2025-07-07", "2025-07-08", "2025-07-10",
    "2025-07-11", "2025-07-14", "2025-07-15", "2025-07-16", "2025-07-17")
CELLS = [(account, horizon, scenario) for account in ("main_account", "small_account")
    for horizon in (1, 5, 10) for scenario in ("l1-conservative-v0.1", "l1-stress-v0.1")]
SEEDS = {"main_account": "30000", "small_account": "2000"}
BOUNDARY = {
    "conditional_financial_metrics_eligible": True,
    "full_input_coverage_complete": False,
    "account_backtest_complete": False,
    "original_financial_metrics_flag_changed": False,
    "original_unavailable_inputs_reclassified": False,
    "original_runtime_changed": False,
    "historical_replay_executed": False,
    "full_local_reproduction_verified": False,
    "provider_requests_authorized": False,
    "retrospective_labels_opened": False,
    "broker_orders_authorized": False,
    "policy_promotion_eligible": False,
}
METRICS = {
    "arithmetic": "Decimal precision 60; exact money; ratios rounded half-even to 6 decimal places",
    "population": "all original 12 alternative paths, each with all 30 selected dates and once-only seed",
    "net_pnl": "confirmed sell proceeds minus confirmed buy costs minus all original incremental fees",
    "return_pct": "100 * net P&L / original account seed; not annualized",
    "equity_curve": "seed followed by all 30 flat session closes; nonconsecutive research dates",
    "max_drawdown": "largest seed-or-session-close peak to later session-close decline; USD and percent computed separately",
    "drawdown_exclusion": "not intraday mark-to-market drawdown; no unobserved prices inferred",
    "episode": "one confirmed entry fill to flat; partial exits combined; re-entry is a new episode",
    "episode_fees": "original causal incremental charges on entry and all its exits; fees subtracted once",
    "win_rate_pct": "100 * net-positive closed episodes / all closed episodes including flats; null if no episodes",
    "profit_factor": "sum positive episode NET P&L / abs(sum negative episode NET P&L); null if no losses",
    "expectancy_usd": "mean net P&L per closed episode; null if no episodes",
    "average_win_loss": "mean net-positive episode P&L and mean net-negative episode P&L; null for empty group",
    "entry_fill_rate_pct": "100 * confirmed buy shares / shares requested in submitted entry orders; null if no orders",
    "aggregation": "never sum overlapping paths into a portfolio, select a winner, or annualize selected dates",
}
require, seal, encoded = accepted.require, accepted.seal, accepted.encoded
number, checked, fingerprint = accepted.number, accepted.checked, accepted.fingerprint
ZERO = Decimal(0)


def money(value):
    """Lossless fixed-point strings; do not inherit Decimal.normalize rounding."""
    result = format(value, "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    return "0" if value == 0 else result


def ratio(numerator, denominator, multiplier=1):
    if denominator == 0:
        return None
    with localcontext() as ctx:
        ctx.prec = 60
        return format((numerator * multiplier / denominator).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_EVEN), "f")


def positive_int(value):
    require(type(value) is int and value > 0, "quantity must be a positive whole share count")
    return value


def timestamp_ns(value):
    require(isinstance(value, str) and value.endswith("+00:00"), "decision must be UTC")
    whole, _, fraction = value[:-6].partition(".")
    require(len(fraction) <= 9 and (not fraction or fraction.isdigit()), "invalid timestamp fraction")
    delta = datetime.fromisoformat(whole + "+00:00") - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 1_000_000_000 + int(fraction.ljust(9, "0"))


def registration(root):
    evidence.check_registration(root, EVIDENCE_CONTRACT)
    evidence.document((root / OBSERVATIONS).read_bytes(), EVIDENCE_RESULT)
    inputs = [f"research/strategy/{accepted.ID}.json", f"{BASE}/acceptance-report.json",
        f"research/strategy/{evidence.ID}.json", OBSERVATIONS]
    return seal({"contract_id": ID, "artifact_type": "conditional_post_result_evaluation_registration",
        "parent_commit_sha": PARENT, "parent_tree_sha": PARENT_TREE,
        "question": "what are the unchanged hosted accounts' results conditional on the strict observed-update entry policy",
        "runtime_and_source_availability_known_before_evaluation": True,
        "unseen_data_strategy_test": False,
        "entry_policy_id": evidence.POLICY_ID, "entry_evidence_content_sha256": EVIDENCE_RESULT,
        "accepted_runtime_content_sha256": accepted.RUNTIME,
        "accepted_checker_content_sha256": accepted.CHECKER,
        "source_bindings_content_sha256": accepted.BINDING,
        "archive_specs": {k: accepted.ARCHIVES[k] for k in ("hosted", "binding")},
        "selected_dates": list(DATES), "account_seeds_usd": SEEDS,
        "alternative_cells": [{"account_key": a, "horizon_seconds": h, "scenario_id": s}
            for a, h, s in CELLS],
        "metric_definitions": METRICS,
        "input_file_specs": {p: accepted.file_spec(root / p) for p in inputs},
        "implementation_file_specs": {p: accepted.file_spec(root / p) for p in OWN_FILES},
        "historical_replay_required": False, **BOUNDARY})


def check_registration(root, expected):
    current = registration(root)
    require(current["content_sha256"] == expected, "external evaluation commitment differs")
    require((root / f"research/strategy/{ID}.json").read_bytes() == encoded(current),
        "registered evaluation code or inputs differ")
    return current


def bind_session(runtime, observations):
    """Require every entry event/journal row to respect the observed-update gate."""
    dispositions = runtime["opportunity_dispositions"]
    by_id = {r["opportunity_id"]: r for r in dispositions}
    require(len(by_id) == len(dispositions), "duplicate opportunity disposition")
    for oid, row in by_id.items():
        require(oid in observations, "unbound runtime opportunity")
        obs = observations[oid]
        require(all(row[k] == obs["original_" + k] for k in
            ("input_status", "reason", "availability_content_sha256")), "original entry evidence changed")
        require(obs["order_authorized"] is False and obs["policy_id"] == evidence.POLICY_ID,
            "observation policy or order boundary differs")
        if obs["entry_gate"] == "withhold_entry_under_observed_update_policy":
            require(row["input_status"] == "unavailable" and row["disposition"] == "unavailable_input",
                "withhold must preserve original unavailable disposition")
        else:
            require(obs["entry_gate"] == "reference_present_requires_remaining_entry_checks"
                and row["input_status"] == "available"
                and row["disposition"] in accepted.AVAILABLE_DISPOSITIONS, "unresolved entry gate")
    outer, fills = {}, {}
    for event in runtime["events"]:
        oid = event["opportunity_id"]
        require(oid in by_id and by_id[oid]["input_status"] == "available",
            "withheld or unbound opportunity has execution events")
        if event["event_type"] == "opportunity_disposition":
            require(oid not in outer and event["disposition"] == by_id[oid]["disposition"],
                "outer entry disposition differs or repeats")
            require((event["order"] is not None) == (event["disposition"] == "entry_submitted"),
                "entry order/disposition differs")
            outer[oid] = event
        if event["event_type"] in {"entry_fill_confirmed", "sell_fill_confirmed"}:
            index = event["journal_index"]
            require(type(index) is int and index not in fills, "duplicate or invalid journal event index")
            fills[index] = event
    require(set(outer) == {k for k, v in by_id.items() if v["input_status"] == "available"},
        "available disposition event missing")
    journal = runtime["reconciliation_snapshot"]["journal"]
    require(set(fills) == set(range(len(journal))), "journal and confirmed events differ")
    for index, row in enumerate(journal):
        event, trade, receipt = fills[index], row["fee_application"]["trade"], row["execution_evidence"]
        require(trade["side"] in {"buy", "sell"}, "unknown trade side")
        require(event["event_type"] == ("entry_fill_confirmed" if trade["side"] == "buy" else "sell_fill_confirmed")
            and event["at_ns"] == row["known_at_ns"], "fill event side or clock differs")
        if trade["side"] == "buy":
            require(receipt["opportunity_id"] == event["opportunity_id"]
                and outer[event["opportunity_id"]]["disposition"] == "entry_submitted"
                and receipt["order"] == {k: outer[event["opportunity_id"]]["order"][k]
                    for k in ("order_id", "quantity", "limit_price")}, "entry does not bind submitted opportunity")
            require(positive_int(trade["quantity"]) <= positive_int(receipt["order"]["quantity"]),
                "entry exceeds requested shares")
    return outer, fills


def bind_observations(runtime, binding, report):
    rows = report["rows"]
    require([r["opportunity_id"] for r in rows] == [o["opportunity_id"] for o in binding["opportunities"]],
        "observation opportunity population or order differs")
    observations = {r["opportunity_id"]: r for r in rows}
    require(len(observations) == len(rows) == 109, "observation count differs")
    for obs, source in zip(rows, binding["opportunities"]):
        entry, identity = source["entry"], source["window"]["opportunity"]
        require(all(obs[k] == identity[k] for k in ("opportunity_id", "symbol", "trading_date"))
            and obs["decision_ts_ns"] == timestamp_ns(source["source_decision"]["decision_at"]),
            "decision identity differs")
        require(all(obs["original_" + k] == entry[k] for k in
            ("input_status", "reason", "availability_content_sha256"))
            and all(obs[k] == entry[k] for k in
                ("quote_request_evidence_sha256", "status_request_evidence_sha256")), "observation/source binding differs")
        require(obs["source_state"] in {"complete", "verified_empty"}
            and obs["causal_status_coverage_complete"] is True, "unverified source cannot support conditional metrics")
    refs = defaultdict(list)
    counts = Counter()
    for path in runtime["paths"]:
        for pair in path["sessions"]:
            r, c = pair["runtime"], pair["close"]
            bind_session(r, observations)
            for row in r["opportunity_dispositions"]:
                counts[row["disposition"]] += 1
                if row["input_status"] == "unavailable":
                    refs[row["opportunity_id"]].append({"path_id": path["path_id"], "session_id": c["session_id"]})
    withheld = {k for k, v in observations.items() if v["entry_gate"] == "withhold_entry_under_observed_update_policy"}
    require(set(refs) == withheld and len(withheld) == 23 and sum(map(len, refs.values())) == 162,
        "withheld opportunity population differs")
    for oid, actual in refs.items():
        require(actual == observations[oid]["original_unavailable_references"]
            and len(actual) == observations[oid]["original_unavailable_path_references"], "unavailable history references differ")
    return observations, {"all_109_observations_bound": True, "withheld_opportunities": len(refs),
        "withheld_path_references": sum(map(len, refs.values())),
        "original_disposition_counts": dict(sorted(counts.items())),
        "withheld_entries_submitted_or_filled": 0, "unresolved_observations": 0}


def reconcile_journal(journal, opening_cash):
    """Recompute exact cash flows and closed episodes from accepted fill receipts."""
    with localcontext() as ctx:
        ctx.prec = 60
        cash, gross, fees, high = number(opening_cash), ZERO, ZERO, ZERO
        active, episodes, previous, clock = None, [], None, None
        fill_ids, totals = set(), Counter()
        for index, row in enumerate(journal):
            checked(row)
            require(row["sequence"] == index and row["previous_event_sha256"] == previous, "journal chain differs")
            receipt, app = checked(row["execution_evidence"]), row["fee_application"]
            trade = app["trade"]
            qty, price, charge = positive_int(trade["quantity"]), number(trade["price"]), number(app["incremental_charge"]["total"])
            require(price > 0 and charge >= 0, "invalid execution price or fee")
            require(sum((number(app["incremental_charge"][k]) for k in ("commission", "sec", "taf", "cat")), ZERO) == charge,
                "incremental fee components differ")
            require(trade["fill_id"] not in fill_ids, "duplicate confirmed fill")
            require(qty == receipt["quantity"] and price == number(receipt["fill_price"])
                and trade["timestamp_ns"] == receipt["fill_time_ns"] <= row["known_at_ns"]
                and (clock is None or row["known_at_ns"] >= clock), "confirmed receipt/clock differs")
            fill_ids.add(trade["fill_id"])
            if trade["side"] == "buy":
                require(active is None and trade["fill_id"] == receipt["fill_id"]
                    and row["activation_id"] == receipt["activation_id"]
                    and trade["order_id"] == receipt["order"]["order_id"], "overlapping or mismatched entry episode")
                active = {"entry_fill_id": trade["fill_id"], "entry_content_sha256": receipt["content_sha256"],
                    "opportunity_id": receipt["opportunity_id"], "activation_id": row["activation_id"],
                    "symbol": receipt["symbol"], "entry_at_ns": trade["timestamp_ns"],
                    "entry_price_usd": money(price), "entry_quantity": qty,
                    "remaining_quantity": qty, "gross": ZERO, "fees": ZERO, "sell_fill_count": 0,
                    "exit_fill_ids": []}
                delta = ZERO
                cash -= price * qty + charge
                totals["buy_shares"] += qty
            elif trade["side"] == "sell":
                require(active is not None and row["activation_id"] == active["activation_id"]
                    and receipt["entry_fill_id"] == active["entry_fill_id"]
                    and trade["fill_id"] == "sell-fill-" + receipt["content_sha256"]
                    and trade["order_id"] == receipt["order_id"], "sell has no matching entry episode")
                require(qty <= active["remaining_quantity"], "sell exceeds confirmed position")
                delta = (price - number(active["entry_price_usd"])) * qty
                active["remaining_quantity"] -= qty
                active["sell_fill_count"] += 1
                active["exit_fill_ids"].append(trade["fill_id"])
                cash += price * qty - charge
                gross += delta
                totals["sell_shares"] += qty
            else:
                raise ValueError("unknown trade side")
            fees += charge
            active["gross"] += delta
            active["fees"] += charge
            net = gross - fees
            high = max(high, net)
            require(number(app["cumulative_fees"]["total_charged"]) == fees
                and number(row["gross_realized_delta"]) == delta
                and number(row["gross_realized_after"]) == gross
                and number(row["net_realized_after"]) == net
                and number(row["net_high_water_after"]) == high
                and number(row["cash_after"]) == cash
                and row["remaining_quantity"] == active["remaining_quantity"], "journal cash, fees, shares or P&L does not reconcile")
            if active["remaining_quantity"] == 0:
                g, f = active.pop("gross"), active.pop("fees")
                episodes.append({**active, "closed_at_ns": trade["timestamp_ns"], "close_known_at_ns": row["known_at_ns"],
                    "gross_pnl_usd": money(g), "fees_usd": money(f), "net_pnl_usd": money(g - f)})
                active = None
            previous, clock = row["content_sha256"], row["known_at_ns"]
        require(active is None, "open position cannot be treated as a closed trade")
        require(cash == number(opening_cash) + gross - fees
            and sum((number(e["net_pnl_usd"]) for e in episodes), ZERO) == gross - fees,
            "closed episode/account totals differ")
        return {"cash_usd": money(cash), "gross_pnl_usd": money(gross), "fees_usd": money(fees),
            "net_pnl_usd": money(gross - fees), "net_high_water_pnl_usd": money(high),
            "buy_shares": totals["buy_shares"], "sell_shares": totals["sell_shares"],
            "confirmed_fill_count": len(journal), "episodes": episodes}


def episode_metrics(episodes):
    with localcontext() as ctx:
        ctx.prec = 60
        values = [number(e["net_pnl_usd"]) for e in episodes]
        wins, losses = [v for v in values if v > 0], [v for v in values if v < 0]
        gain, loss = sum(wins, ZERO), sum(losses, ZERO)
        return {"closed_episodes": len(values), "winning_episodes": len(wins), "losing_episodes": len(losses),
            "flat_episodes": len(values) - len(wins) - len(losses),
            "net_win_rate_pct": ratio(Decimal(len(wins)), Decimal(len(values)), 100),
            "net_profit_factor": ratio(gain, -loss),
            "profit_factor_undefined_reason": "no_closed_episodes" if not values else "no_net_losses" if not losses else None,
            "net_expectancy_usd": ratio(gain + loss, Decimal(len(values))),
            "average_net_win_usd": ratio(gain, Decimal(len(wins))),
            "average_net_loss_usd": ratio(loss, Decimal(len(losses)))}


def equity_metrics(seed, daily):
    """Keep every selected date, including zero-trade and original gap dates."""
    with localcontext() as ctx:
        ctx.prec = 60
        initial = number(seed)
        require(initial > 0, "seed must be positive")
        equity = peak = initial
        max_usd = max_pct = ZERO
        curve = []
        for day in daily:
            require(number(day["opening_equity_usd"]) == equity, "daily equity does not carry")
            equity += number(day["net_pnl_usd"])
            require(number(day["closing_equity_usd"]) == equity, "session equity does not reconcile")
            peak = max(peak, equity)
            drawdown = peak - equity
            pct = drawdown * 100 / peak
            max_usd, max_pct = max(max_usd, drawdown), max(max_pct, pct)
            curve.append({"trading_date": day["trading_date"], "equity_usd": money(equity),
                "high_water_equity_usd": money(peak), "drawdown_usd": money(drawdown),
                "drawdown_pct": ratio(drawdown, peak, 100)})
        return {"seed_usd": money(initial), "ending_equity_usd": money(equity),
            "net_pnl_usd": money(equity - initial), "net_return_pct": ratio(equity - initial, initial, 100),
            "max_session_close_drawdown_usd": money(max_usd),
            "max_session_close_drawdown_pct": ratio(max_pct, Decimal(1)), "equity_curve": curve}


def evaluate_path(path, catalog, observations):
    with localcontext() as ctx:
        ctx.prec = 60
        first = catalog["sessions"][0]
        account, horizon, scenario = (first[k] for k in ("account_key", "behavioral_horizon_seconds", "execution_scenario_id"))
        require((account, horizon, scenario) in CELLS
            and [s["trading_date"] for s in catalog["sessions"]] == list(DATES), "evaluation cohort differs")
        opening = path["initial_account_state"]
        require(number(opening["equity_usd"]) == number(SEEDS[account])
            and number(opening["buying_power_usd"]) == number(SEEDS[account])
            and number(opening["cumulative_fees_usd"]) == number(opening["cumulative_realized_pnl_usd"]) == 0,
            "once-only account seed differs")
        daily, episodes = [], []
        for pair, slot in zip(path["sessions"], catalog["sessions"]):
            r, close = pair["runtime"], pair["close"]
            snapshot = checked(r["reconciliation_snapshot"])
            outer, fills = bind_session(r, observations)
            result = reconcile_journal(snapshot["journal"], opening["buying_power_usd"])
            require(snapshot["fee_book"]["trades"] == [j["fee_application"]["trade"] for j in snapshot["journal"]],
                "fee book trade population differs")
            for output, source in (("gross_pnl_usd", "session_gross_realized_pnl_usd"),
                    ("fees_usd", "session_fees_usd"), ("net_pnl_usd", "session_net_realized_pnl_usd")):
                require(number(result[output]) == number(r[source]), "session financial total differs")
            require(number(snapshot["fee_book"]["fees"]["total_charged"]) == number(result["fees_usd"]),
                "fee book total differs")
            for out, key in (("cash_usd", "remaining_buying_power"), ("gross_pnl_usd", "gross_realized_pnl"),
                    ("net_pnl_usd", "net_realized_pnl"), ("net_high_water_pnl_usd", "net_high_water_pnl")):
                require(number(snapshot["exact_account"][key]) == number(result[out]), "exact snapshot total differs")
            receipts = snapshot["completed_positions"]
            require(len(receipts) == len(result["episodes"]), "closed episode receipt population differs")
            require([e["receipt"] for e in r["events"] if e["event_type"] == "capacity_released"] == receipts,
                "capacity release receipts differ")
            for ep, receipt in zip(result["episodes"], receipts):
                checked(receipt)
                require(receipt["entry_content_sha256"] == ep["entry_content_sha256"]
                    and receipt["confirmed_position_shares_closed"] is True
                    and receipt["released_at_ns"] >= ep["close_known_at_ns"], "episode not confirmed flat and released")
                # Sell events must refer to the same original opportunity as their bound entry.
                require(all(fills[i]["opportunity_id"] == ep["opportunity_id"] for i, j in enumerate(snapshot["journal"])
                    if j["fee_application"]["trade"]["fill_id"] in ep["exit_fill_ids"]), "sell opportunity differs from entry")
                episodes.append({"path_id": path["path_id"], "session_id": close["session_id"],
                    "trading_date": close["trading_date"], **ep})
            orders = [e["order"] for e in outer.values() if e["order"] is not None]
            withheld = [d["opportunity_id"] for d in r["opportunity_dispositions"] if d["input_status"] == "unavailable"]
            daily.append({"session_id": close["session_id"], "trading_date": close["trading_date"],
                "session_index": close["session_index"], "source_runtime_content_sha256": r["content_sha256"],
                "source_close_content_sha256": close["content_sha256"], "original_runtime_status": r["status"],
                "original_unavailable_opportunity_ids": withheld,
                "carried_original_unavailable_reference_count": len(close["account_state"]["unresolved_inputs"]),
                "source_date_has_no_micro_decisions": slot["source_date_has_no_micro_decisions"],
                "opening_equity_usd": opening["equity_usd"], "closing_equity_usd": close["account_state"]["equity_usd"],
                **{k: result[k] for k in ("gross_pnl_usd", "fees_usd", "net_pnl_usd", "buy_shares", "sell_shares", "confirmed_fill_count")},
                "closed_episodes": len(result["episodes"]), "submitted_entry_orders": len(orders),
                "requested_entry_shares": sum(positive_int(o["quantity"]) for o in orders)})
            opening = close["account_state"]
        curve = equity_metrics(SEEDS[account], daily)
        totals = {k: sum(d[k] for d in daily) for k in
            ("buy_shares", "sell_shares", "confirmed_fill_count", "submitted_entry_orders", "requested_entry_shares")}
        gross, fees = (sum((number(d[k]) for d in daily), ZERO) for k in ("gross_pnl_usd", "fees_usd"))
        require(gross - fees == number(curve["net_pnl_usd"]) == number(opening["cumulative_realized_pnl_usd"])
            and fees == number(opening["cumulative_fees_usd"]), "final account P&L or fee carry differs")
        return {"path_id": path["path_id"], "account_key": account, "horizon_seconds": horizon,
            "scenario_id": scenario, "original_path_complete": path["path_complete"],
            "session_count": len(daily), "active_sessions": sum(d["closed_episodes"] > 0 for d in daily),
            "original_unavailable_references": sum(len(d["original_unavailable_opportunity_ids"]) for d in daily),
            **curve, "gross_pnl_usd": money(gross), "fees_usd": money(fees), **totals,
            "entry_share_fill_rate_pct": ratio(Decimal(totals["buy_shares"]), Decimal(totals["requested_entry_shares"]), 100),
            **episode_metrics(episodes), "daily": daily, "episodes": episodes}


def evaluate(root, expected):
    contract = check_registration(root, expected)
    old = evidence.document((root / f"{BASE}/acceptance-report.json").read_bytes(), evidence.REPORT_SHA)
    obs = evidence.document((root / OBSERVATIONS).read_bytes(), EVIDENCE_RESULT)
    hosted = accepted.verified_zip(root / f"{BASE}/hosted-runtime-original.zip", accepted.ARCHIVES["hosted"])
    original = accepted.verified_zip(root / f"{BASE}/source-binding-original.zip", accepted.ARCHIVES["binding"])
    runtime = accepted.read_json(hosted["account-replay/account-replay.json"])
    checker = accepted.read_json(hosted["account-replay/independent-verification.json"])
    binding = accepted.read_json(original["source-bindings.json"])
    require(runtime["content_sha256"] == accepted.RUNTIME and binding["content_sha256"] == accepted.BINDING
        and checker["content_sha256"] == accepted.CHECKER
        and checker["runtime_content_sha256"] == accepted.RUNTIME and checker["verification_passed"] is True,
        "accepted runtime, binding or independent check differs")
    require(runtime["financial_metrics_eligible"] is False and checker["financial_metrics_eligible"] is False,
        "original financial boundary changed")
    coverage = accepted.audit_panel(runtime, binding)
    require(all(old[k] == v for k, v in coverage.items()), "accepted coverage audit differs")
    observations, gate = bind_observations(runtime, binding, obs)
    paths = [evaluate_path(p, c, observations) for p, c in zip(runtime["paths"], binding["paths"])]
    require([(p["account_key"], p["horizon_seconds"], p["scenario_id"]) for p in paths] == CELLS,
        "alternative evaluation cells differ")
    return seal({"contract_id": ID, "artifact_type": "conditional_account_performance_report",
        "contract_content_sha256": contract["content_sha256"], "metric_definitions": METRICS,
        "runtime_content_sha256": accepted.RUNTIME, "independent_checker_content_sha256": accepted.CHECKER,
        "source_bindings_content_sha256": accepted.BINDING,
        "entry_evidence_content_sha256": EVIDENCE_RESULT, "entry_policy_id": evidence.POLICY_ID,
        "accepted_hosted_run_id": accepted.HOSTED_RUN, "source_acceptance_content_sha256": old["content_sha256"],
        "selected_dates": list(DATES), "population": coverage["population"],
        "gate_binding": gate, "all_fills_fees_episodes_and_account_carry_reconciled": True,
        "paths": paths, "paths_are_alternatives_not_a_combined_portfolio": True,
        "interpretation": "descriptive conditional results on selected historical dates; not full market coverage or evidence of a live trading edge",
        **BOUNDARY})


def render_markdown(report):
    checked(report)
    lines = ["# Conditional account results — strict observed-update policy v0.1", "",
        "These results use the unchanged accepted hosted replay and all 30 selected dates",
        "from May 30 to July 17, 2025. Each row is a separate account history. Seeds are",
        "$30,000 and $2,000, applied once. No return is annualized or combined across rows.", "",
        "| Account | Horizon | Execution | Final equity ($) | Gross P&L ($) | Fees ($) | Net P&L ($) | Return (%) | Max close drawdown ($) | Max close drawdown (%) |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|"]
    for p in report["paths"]:
        lines.append("| " + " | ".join(str(v) for v in (p["account_key"], str(p["horizon_seconds"]) + "s",
            p["scenario_id"], *(p[k] for k in ("ending_equity_usd", "gross_pnl_usd", "fees_usd", "net_pnl_usd",
                "net_return_pct", "max_session_close_drawdown_usd", "max_session_close_drawdown_pct")))) + " |")
    lines += ["", "| Account | Horizon | Execution | Closed positions | Active dates | Net win rate (%) | Net profit factor | Net expectancy ($) | Entry shares filled/requested | Share fill rate (%) |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|"]
    for p in report["paths"]:
        lines.append("| " + " | ".join("—" if v is None else str(v) for v in (p["account_key"], str(p["horizon_seconds"]) + "s",
            p["scenario_id"], *(p[k] for k in ("closed_episodes", "active_sessions", "net_win_rate_pct",
                "net_profit_factor", "net_expectancy_usd")), f'{p["buy_shares"]}/{p["requested_entry_shares"]}',
            p["entry_share_fill_rate_pct"])) + " |")
    lines += ["", "## Scope and interpretation", "",
        "- All 109 opportunity observations bind to the original sources. The 23 strict-policy",
        "  withhold decisions match all 162 original unavailable path references, with no entry",
        "  submitted or filled for those decisions. Original gap history remains unchanged.",
        "- All 360 session slots remain, including dates with no decisions or no filled trades.",
        "- Position statistics combine partial exits; a later re-entry starts a new position.",
        "  Win rate, profit factor and expectancy use P&L after the original charged fees.",
        "- Drawdown measures seed/session-close equity only. It is not intraday mark-to-market risk.",
        "- This evaluates a single-venue observed-update policy. No standing BBO or NBBO is inferred.",
        "  Source availability was known when this conditional scope was specified. These are",
        "  descriptive research results, not an unseen-data validation or evidence of a live edge.",
        "- Captured positions and orders finish flat; full market-input coverage and the original",
        "  account-backtest-complete flags remain false. No runtime, source window or threshold changed.",
        "- No historical replay, provider request, Ross-label access or broker order was executed.", "",
        "[Machine-readable results, all daily equity histories and closed positions](report.json).", "",
        f'Contract: `{report["contract_content_sha256"]}`.  ',
        f'Report: `{report["content_sha256"]}`.  ',
        f'Runtime: `{report["runtime_content_sha256"]}`.', ""]
    return "\n".join(lines)
