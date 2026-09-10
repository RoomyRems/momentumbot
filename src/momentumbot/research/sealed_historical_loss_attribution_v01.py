"""Accounting attribution of saved conditional results, not a policy experiment."""
from collections import Counter, defaultdict
from decimal import Decimal, localcontext
import gzip
from pathlib import Path

from momentumbot.research import sealed_historical_account_conditional_evaluation_v01 as baseline

ID = "sealed-historical-loss-attribution-v0.1"
PARENT = "78050eacc330b82387e0b292479e5e576ea0b19a"
PARENT_TREE = "c05a3915e6a3b17946425a43fb6ada774324720a"
BASELINE_CONTRACT = "aac233a9b18eb5145c2c0bf8f6ab50f5bb72636afd1c748bd9edf94ce91ec2f1"
BASELINE_REPORT = "23fb88bcb2a8cb95dafe7059e0d99c54deed423c7d30a24b280b95d6b00144d8"
BASELINE_PATH = f"research/data-audits/{baseline.ID}/report.json"
AVAILABILITY_PATH = "research/runtime/sealed-historical-execution-availability-v0.1"
OWN_FILES = ("src/momentumbot/research/sealed_historical_loss_attribution_v01.py",
    "scripts/attribute_sealed_historical_losses_v01.py", "tests/test_sealed_historical_loss_attribution_v01.py")
REASONS = ("initial_stop", "breakeven_stop", "first_target", "first_red_candle", "account_risk_flatten")
STAGES = ("profit_target", "terminal_initial_1", "terminal_residual_2", "terminal_continuation_3_plus")
DEFINITIONS = {
    "scope": "post-result diagnostic; baseline losses already known; no threshold or policy change",
    "reason_attribution": "sum realized sell P&L by recorded reason; exit fees shown separately; entry fees remain a separate debit",
    "stage_attribution": "mutually exclusive profit-target, first terminal, second residual, third-or-later continuation orders; includes unfilled orders",
    "waiting": "orthogonal annotation from original wait_submitted evidence; never added to reason/stage totals",
    "entry_shortfall": "confirmed quantity * (actual entry price - original decision ask); positive is an adverse price difference",
    "price_bridge": "reference-to-actual-exit price component minus entry shortfall minus all fees equals actual net P&L",
    "bridge_limit": "accounting identity at actual sizes/exits; reference quote is not a simulated alternative fill or an attainable profit claim",
    "initial_risk": "confirmed entry shares * (recorded entry price - recorded initial stop); not guaranteed maximum loss",
    "stop_shortfall": "for initial_stop sells only: quantity * (initial stop - actual sell); signed difference, not a causal effect of waiting",
    "sizing": "requested/filled/cancelled shares, notional and initial stop risk relative to that session's opening equity",
    "reentry": "second confirmed entry for the same activation in a path; aggregate whole episodes including all fees",
    "unfilled_or_blocked": "retain all original decisions; no hypothetical P&L or lost-profit estimate",
    "population": "all 12 alternative paths and all 30 dates; never pool horizons/accounts into independent observations",
    "arithmetic": "Decimal precision 60, lossless money, ratios half-even to six places; serialized float stops use Decimal(str(value))",
}
BOUNDARY = {**baseline.BOUNDARY, "counterfactual_performance_established": False,
    "causal_effect_of_entry_sizing_or_exit_change_established": False,
    "runtime_or_strategy_thresholds_changed": False, "diagnostic_only": True}
require, checked, seal = baseline.require, baseline.checked, baseline.seal
money, number, ratio = baseline.money, baseline.number, baseline.ratio
encoded, fingerprint = baseline.encoded, baseline.fingerprint
ZERO = Decimal(0)


def source_price(value):
    require(type(value) in (str, int, float), "invalid recorded price type")
    result = number(str(value))
    require(result > 0, "recorded price must be positive")
    return result


def registration(root):
    baseline.check_registration(root, BASELINE_CONTRACT)
    baseline.evidence.document((root / BASELINE_PATH).read_bytes(), BASELINE_REPORT)
    manifest = baseline.evidence.document((root / AVAILABILITY_PATH / "manifest.json").read_bytes(), baseline.evidence.AVAILABILITY_SHA)
    inputs = [f"research/strategy/{baseline.ID}.json", BASELINE_PATH,
        f"{AVAILABILITY_PATH}/manifest.json", *[f"{AVAILABILITY_PATH}/{p}" for p in manifest["date_file_inventory"]]]
    return seal({"contract_id": ID, "artifact_type": "post_result_loss_attribution_registration",
        "parent_commit_sha": PARENT, "parent_tree_sha": PARENT_TREE,
        "baseline_contract_content_sha256": BASELINE_CONTRACT, "baseline_report_content_sha256": BASELINE_REPORT,
        "baseline_financial_outcomes_known_before_registration": True,
        "question": "which recorded entry price differences, exit reasons, execution stages and sizes account for the fixed losses",
        "metric_definitions": DEFINITIONS, "selected_dates": list(baseline.DATES),
        "input_file_specs": {p: baseline.accepted.file_spec(root / p) for p in inputs},
        "implementation_file_specs": {p: baseline.accepted.file_spec(root / p) for p in OWN_FILES},
        **BOUNDARY})


def check_registration(root, expected):
    current = registration(root)
    require(current["content_sha256"] == expected, "external diagnostic commitment differs")
    require((root / f"research/strategy/{ID}.json").read_bytes() == encoded(current), "diagnostic code or inputs differ")
    return current


def decision_references(root, observations):
    """Read only the existing selected decision reference; never choose a new quote."""
    manifest = baseline.evidence.document((root / AVAILABILITY_PATH / "manifest.json").read_bytes(), baseline.evidence.AVAILABILITY_SHA)
    result = {}
    for name in manifest["date_file_inventory"]:
        date = baseline.evidence.document(gzip.decompress((root / AVAILABILITY_PATH / name).read_bytes()))
        for row in date["opportunities"]:
            checked(row)
            oid = row["opportunity"]["opportunity_id"]
            require(oid in observations and oid not in result, "availability opportunity differs")
            obs = observations[oid]
            require(row["content_sha256"] == obs["original_availability_content_sha256"], "availability commitment differs")
            ref = row.get("decision_reference")
            if row["input_status"] == "available":
                require(ref is not None and ref["source_record_index"] == obs["reference_source_record_index"]
                    and obs["decision_ts_ns"] - ref["ts_recv_ns"] == obs["reference_age_ns"]
                    and ref["symbol"] == obs["symbol"] and 0 <= obs["reference_age_ns"] <= 100_000_000,
                    "original reference identity or clock differs")
                require(ref in row["capture"]["quotes"], "reference absent from original capture")
                source_price(ref["ask_price"])
            else:
                require(ref is None and obs["entry_gate"] == "withhold_entry_under_observed_update_policy",
                    "withheld entry gained a reference")
            result[oid] = ref
    require(set(result) == set(observations), "original opportunity coverage differs")
    return result


def index_orders(runtime):
    """Bind replacement and waiting annotations to actual submitted orders."""
    orders = {}
    for event in runtime["events"]:
        if event["event_type"] == "sell_submitted":
            order = event["order"]
            require(order["order_id"] not in orders and event["reason"] in REASONS, "unknown or repeated sell order")
            orders[order["order_id"]] = {"order": order, "reason": event["reason"],
                "opportunity_id": event["opportunity_id"], "stage": "profit_target" if event["reason"] == "first_target" else "terminal_initial_1",
                "waited": False, "wait_ns": 0, "terminal_attempt_number": None}
    snapshot = runtime["reconciliation_snapshot"]
    assigned = set()
    for key, kind, stage in (("exit_residual_events", "residual_submitted", "terminal_residual_2"),
            ("exit_continuation_events", "continuation_submitted", "terminal_continuation_3_plus")):
        for event in snapshot.get(key, []):
            if event["event_type"] != kind:
                continue
            checked(event)
            oid = event["order"]["order_id"]
            require(oid in orders and oid not in assigned, "replacement has no unique submitted order")
            item = orders[oid]
            require(event["order"] == item["order"] and event["opportunity_id"] == item["opportunity_id"]
                and event["intent"]["reason"] == item["reason"] != "first_target", "replacement order binding differs")
            number_ = event["context"]["terminal_attempt_number"]
            require(type(number_) is int and (number_ == 2 if stage == "terminal_residual_2" else number_ >= 3),
                "replacement attempt number differs")
            item.update(stage=stage, terminal_attempt_number=number_)
            assigned.add(oid)
    for event in snapshot.get("exit_wait_events", []):
        if event["event_type"] != "wait_submitted":
            continue
        checked(event)
        oid = event["order"]["order_id"]
        require(oid in orders and not orders[oid]["waited"], "wait has no unique submitted order")
        item = orders[oid]
        require(event["order"] == item["order"] and event["opportunity_id"] == item["opportunity_id"]
            and event["signal"]["reason"] == item["reason"], "waiting order binding differs")
        elapsed = event["order"]["decision_ts_ns"] - event["signal"]["decision_ts_ns"]
        require(elapsed >= 0, "negative pre-submission waiting interval")
        item.update(waited=True, wait_ns=elapsed)
    attempts = Counter()
    for item in orders.values():
        if item["stage"] == "profit_target":
            continue
        attempts[item["opportunity_id"]] += 1
        n = attempts[item["opportunity_id"]]
        require((n == 1 and item["stage"] == "terminal_initial_1") or item["terminal_attempt_number"] == n,
            "terminal order sequence differs from retained authority")
        item["terminal_attempt_number"] = n
    return orders


def price_bridge(entry_price, decision_ask, quantity, sells, entry_fee):
    """Algebra at ACTUAL quantities/exits, never a hypothetical account run."""
    with localcontext() as ctx:
        ctx.prec = 60
        p, ref = source_price(entry_price), source_price(decision_ask)
        q = baseline.positive_int(quantity)
        require(sum(baseline.positive_int(s["quantity"]) for s in sells) == q, "exit shares do not close exact entry")
        gross = sum(((source_price(s["fill_price_usd"]) - p) * s["quantity"] for s in sells), ZERO)
        ref_component = sum(((source_price(s["fill_price_usd"]) - ref) * s["quantity"] for s in sells), ZERO)
        shortfall = (p - ref) * q
        fees = number(entry_fee) + sum((number(s["exit_fee_usd"]) for s in sells), ZERO)
        require(fees >= 0 and ref_component - shortfall == gross, "price bridge does not reconcile")
        return {"reference_to_actual_exits_component_usd": money(ref_component),
            "entry_execution_shortfall_usd": money(shortfall), "gross_pnl_usd": money(gross),
            "fees_usd": money(fees), "net_pnl_usd": money(gross - fees)}


def group_exits(rows, key, categories):
    """Reasons and stages are separate views of the same sell fills."""
    result = []
    with localcontext() as ctx:
        ctx.prec = 60
        require(all(r[key] in categories for r in rows), "unregistered exit category")
        for category in categories:
            selected = [r for r in rows if r[key] == category]
            gross = sum((number(r["gross_pnl_usd"]) for r in selected), ZERO)
            fees = sum((number(r["exit_fee_usd"]) for r in selected), ZERO)
            result.append({key: category, "sell_fills": len(selected),
                "episodes_touched": len({r["entry_fill_id"] for r in selected}),
                "sold_shares": sum(r["quantity"] for r in selected),
                "gross_pnl_usd": money(gross), "exit_fees_usd": money(fees),
                "pnl_after_exit_fees_before_entry_fees_usd": money(gross - fees)})
    return result


def sum_money(rows, key):
    return sum((number(r[key]) for r in rows), ZERO)


def analyze_path(path, previous, references, sources):
    with localcontext() as ctx:
        ctx.prec = 60
        episodes, exits, decisions, order_rows, daily = [], [], [], [], []
        activation_counts = Counter()
        original_episodes = {e["entry_fill_id"]: e for e in previous["episodes"]}
        for pair, day in zip(path["sessions"], previous["daily"]):
            runtime, close = pair["runtime"], pair["close"]
            require(close["session_id"] == day["session_id"] and close["trading_date"] == day["trading_date"], "daily identity differs")
            orders = index_orders(runtime)
            submitted_entries = {e["opportunity_id"]: e for e in runtime["events"]
                if e["event_type"] == "opportunity_disposition" and e["order"] is not None}
            cancel_acks = {e["opportunity_id"]: e for e in runtime["events"] if e["event_type"] == "entry_cancel_acknowledged"}
            require(set(submitted_entries) == set(cancel_acks), "entry cancellation acknowledgements differ")
            journal = runtime["reconciliation_snapshot"]["journal"]
            buys = {j["execution_evidence"]["fill_id"]: j for j in journal if j["fee_application"]["trade"]["side"] == "buy"}
            buys_by_op = {j["execution_evidence"]["opportunity_id"]: j for j in buys.values()}
            require(len(buys) == len(buys_by_op), "more than one filled entry for an opportunity")
            local_exits, local_eps = [], []
            for j in journal:
                if j["fee_application"]["trade"]["side"] != "sell":
                    continue
                receipt = j["execution_evidence"]
                require(receipt["entry_fill_id"] in buys and receipt["order_id"] in orders, "sell lacks entry or order binding")
                entry = buys[receipt["entry_fill_id"]]["execution_evidence"]
                item = orders[receipt["order_id"]]
                require(receipt["reason"] == item["reason"] and entry["opportunity_id"] == item["opportunity_id"], "sell reason/opportunity differs")
                p, stop, sell = source_price(entry["fill_price"]), source_price(entry["initial_stop_price"]), source_price(receipt["fill_price"])
                qty = baseline.positive_int(receipt["quantity"])
                gross = (sell - p) * qty
                require(gross == number(j["gross_realized_delta"]), "sell P&L differs from accepted journal")
                row = {"entry_fill_id": entry["fill_id"], "opportunity_id": entry["opportunity_id"],
                    "trading_date": close["trading_date"], "symbol": entry["symbol"],
                    "fill_content_sha256": receipt["content_sha256"], "order_id": receipt["order_id"],
                    "reason": receipt["reason"], "stage": item["stage"], "waited_before_submission": item["waited"],
                    "fill_at_ns": receipt["fill_time_ns"], "quantity": qty, "fill_price_usd": money(sell),
                    "gross_pnl_usd": money(gross), "exit_fee_usd": j["fee_application"]["incremental_charge"]["total"],
                    "initial_stop_shortfall_usd": money((stop - sell) * qty) if receipt["reason"] == "initial_stop" else None}
                local_exits.append(row)
            for fill_id, j in buys.items():
                entry = j["execution_evidence"]
                require(fill_id in original_episodes, "entry absent from frozen conditional report")
                old = original_episodes[fill_id]
                ref = references[entry["opportunity_id"]]
                require(ref is not None and entry["content_sha256"] == old["entry_content_sha256"], "entry reference or receipt differs")
                require(source_price(entry["initial_stop_price"]) == source_price(sources[entry["opportunity_id"]]["source_decision"]["plan"]["stop_price"]), "initial stop differs from original plan")
                sold = [s for s in local_exits if s["entry_fill_id"] == fill_id]
                fee = j["fee_application"]["incremental_charge"]["total"]
                bridge = price_bridge(entry["fill_price"], ref["ask_price"], entry["quantity"], sold, fee)
                require(all(number(bridge[k]) == number(old[k]) for k in ("gross_pnl_usd", "fees_usd", "net_pnl_usd")), "episode accounting differs from frozen result")
                p, stop, q = source_price(entry["fill_price"]), source_price(entry["initial_stop_price"]), entry["quantity"]
                risk, notional = (p - stop) * q, p * q
                require(risk > 0, "entry has no positive initial stop risk")
                activation_counts[entry["activation_id"]] += 1
                ordinal = activation_counts[entry["activation_id"]]
                require(ordinal in (1, 2), "unexpected campaign entry count")
                own_orders = [o for o in orders.values() if o["opportunity_id"] == entry["opportunity_id"]]
                row = {"entry_fill_id": fill_id, "entry_content_sha256": entry["content_sha256"],
                    "opportunity_id": entry["opportunity_id"], "activation_id": entry["activation_id"],
                    "trading_date": close["trading_date"], "symbol": entry["symbol"],
                    "campaign_entry_ordinal": ordinal, "entry_quantity": q, "requested_entry_shares": entry["order"]["quantity"],
                    "decision_ask_usd": ref["ask_price"], "decision_reference_source_record_index": ref["source_record_index"],
                    "decision_reference_ts_recv_ns": ref["ts_recv_ns"], "entry_price_usd": entry["fill_price"],
                    "initial_stop_usd": money(stop), "entry_notional_usd": money(notional), "initial_stop_risk_usd": money(risk),
                    "entry_notional_pct_of_session_equity": ratio(notional, number(day["opening_equity_usd"]), 100),
                    "initial_stop_risk_pct_of_session_equity": ratio(risk, number(day["opening_equity_usd"]), 100),
                    "net_pnl_in_initial_risk_units": ratio(number(bridge["net_pnl_usd"]), risk),
                    "entry_fee_usd": fee, **bridge, "exit_reason_at_close": sold[-1]["reason"],
                    "exit_stage_at_close": sold[-1]["stage"], "sell_orders": len(own_orders), "sell_fills": len(sold),
                    "waited_sell_orders": sum(o["waited"] for o in own_orders),
                    "hold_time_ns": old["closed_at_ns"] - old["entry_at_ns"]}
                local_eps.append(row)
            local_decisions = []
            for d in runtime["opportunity_dispositions"]:
                oid = d["opportunity_id"]
                order = submitted_entries.get(oid, {}).get("order")
                request = 0 if order is None else baseline.positive_int(order["quantity"])
                filled = 0 if oid not in buys_by_op else buys_by_op[oid]["execution_evidence"]["quantity"]
                cancelled = 0 if oid not in cancel_acks else cancel_acks[oid]["cancelled_quantity"]
                require(request == filled + cancelled, "entry share accounting differs")
                if oid in cancel_acks:
                    require(cancel_acks[oid]["confirmed_quantity"] == filled, "confirmed entry quantity differs")
                local_decisions.append({**d, "trading_date": close["trading_date"], "symbol": sources[oid]["activation"]["symbol"],
                    "requested_shares": request, "filled_shares": filled, "cancelled_shares": cancelled,
                    "untraded_opportunity_profit_estimated": False})
            for oid, item in orders.items():
                fills = [s for s in local_exits if s["order_id"] == oid]
                quantity = sum(s["quantity"] for s in fills)
                require(quantity <= item["order"]["quantity"], "sell fills exceed submitted order")
                order_rows.append({"order_id": oid, "opportunity_id": item["opportunity_id"], "trading_date": close["trading_date"],
                    "reason": item["reason"], "stage": item["stage"], "terminal_attempt_number": item["terminal_attempt_number"],
                    "requested_shares": item["order"]["quantity"], "filled_shares": quantity,
                    "waited_before_submission": item["waited"], "wait_before_submission_ns": item["wait_ns"],
                    "gross_pnl_usd": money(sum_money(fills, "gross_pnl_usd"))})
            require(sum_money(local_eps, "net_pnl_usd") == number(day["net_pnl_usd"]), "daily net P&L differs")
            daily.append({"trading_date": close["trading_date"], "session_id": close["session_id"],
                "source_runtime_content_sha256": runtime["content_sha256"], "opening_equity_usd": day["opening_equity_usd"],
                "closing_equity_usd": day["closing_equity_usd"], "net_pnl_usd": day["net_pnl_usd"],
                "closed_episodes": len(local_eps), "original_status": runtime["status"],
                "original_unavailable_opportunity_ids": day["original_unavailable_opportunity_ids"],
                "original_disposition_counts": dict(sorted(Counter(d["disposition"] for d in local_decisions).items()))})
            episodes.extend(local_eps);exits.extend(local_exits);decisions.extend(local_decisions)
        require(len(episodes) == len(original_episodes) and len(daily) == 30
            and [d["trading_date"] for d in daily] == list(baseline.DATES), "episode/date population differs")
        totals = {k: money(sum_money(episodes, k)) for k in ("net_pnl_usd", "gross_pnl_usd", "fees_usd",
            "reference_to_actual_exits_component_usd", "entry_execution_shortfall_usd", "initial_stop_risk_usd", "entry_notional_usd", "entry_fee_usd")}
        require(all(number(totals[k]) == number(previous[k]) for k in ("net_pnl_usd", "gross_pnl_usd", "fees_usd")), "path results differ")
        require(number(totals["reference_to_actual_exits_component_usd"]) - number(totals["entry_execution_shortfall_usd"]) - number(totals["fees_usd"]) == number(totals["net_pnl_usd"]), "aggregate price bridge differs")
        reasons = group_exits(exits, "reason", REASONS)
        stages = group_exits(exits, "stage", STAGES)
        for groups in (reasons, stages):
            require(sum_money(groups, "pnl_after_exit_fees_before_entry_fees_usd") - number(totals["entry_fee_usd"]) == number(totals["net_pnl_usd"]), "exit attribution does not reconcile")
        cohorts = []
        for ordinal in (1, 2):
            rows = [e for e in episodes if e["campaign_entry_ordinal"] == ordinal]
            cohorts.append({"campaign_entry_ordinal": ordinal, **baseline.episode_metrics(rows),
                "net_pnl_usd": money(sum_money(rows, "net_pnl_usd"))})
        symbol_rows = [{"symbol": symbol, "closed_episodes": len(rows), "net_pnl_usd": money(sum_money(rows, "net_pnl_usd"))}
            for symbol in sorted({e["symbol"] for e in episodes}) if (rows := [e for e in episodes if e["symbol"] == symbol])]
        fills = sum(d["filled_shares"] for d in decisions)
        requests = sum(d["requested_shares"] for d in decisions)
        stop_sells = [s for s in exits if s["reason"] == "initial_stop"]
        return {**{k: previous[k] for k in ("path_id", "account_key", "horizon_seconds", "scenario_id", "closed_episodes", "original_path_complete")},
            "totals": totals, "exit_reasons": reasons, "exit_stages": stages, "entry_cohorts": cohorts, "symbols": symbol_rows,
            "sizing": {"requested_entry_shares": requests, "filled_entry_shares": fills,
                "cancelled_entry_shares": requests - fills, "entry_share_fill_rate_pct": ratio(Decimal(fills), Decimal(requests), 100),
                "submitted_entry_orders": sum(d["requested_shares"] > 0 for d in decisions),
                "unfilled_entry_orders": sum(d["requested_shares"] > 0 and d["filled_shares"] == 0 for d in decisions),
                "max_entry_notional_pct_of_session_equity": max((number(e["entry_notional_pct_of_session_equity"]) for e in episodes), default=ZERO).to_eng_string(),
                "max_initial_risk_pct_of_session_equity": max((number(e["initial_stop_risk_pct_of_session_equity"]) for e in episodes), default=ZERO).to_eng_string(),
                "aggregate_net_pnl_per_initial_risk_unit": ratio(number(totals["net_pnl_usd"]), number(totals["initial_stop_risk_usd"]))},
            "initial_stop_execution": {"sold_shares": sum(s["quantity"] for s in stop_sells),
                "signed_shortfall_from_initial_stop_usd": money(sum_money(stop_sells, "initial_stop_shortfall_usd"))},
            "original_disposition_counts": dict(sorted(Counter(d["disposition"] for d in decisions).items())),
            "sell_execution": {"submitted_orders": len(order_rows), "filled_orders": sum(o["filled_shares"] > 0 for o in order_rows),
                "unfilled_orders": sum(o["filled_shares"] == 0 for o in order_rows),
                "waited_orders": sum(o["waited_before_submission"] for o in order_rows),
                "max_wait_before_submission_ns": max((o["wait_before_submission_ns"] for o in order_rows), default=0),
                "stage_order_counts": dict(sorted(Counter(o["stage"] for o in order_rows).items()))},
            "daily": daily, "decisions": decisions, "episodes": episodes, "sell_fills": exits, "sell_orders": order_rows}


def analyze(root, expected):
    contract = check_registration(root, expected)
    previous = baseline.evidence.document((root / BASELINE_PATH).read_bytes(), BASELINE_REPORT)
    require(baseline.evaluate(root, BASELINE_CONTRACT) == previous, "fixed conditional report no longer reproduces from saved artifacts")
    original = baseline.accepted.verified_zip(root / f"{baseline.BASE}/source-binding-original.zip", baseline.accepted.ARCHIVES["binding"])
    hosted = baseline.accepted.verified_zip(root / f"{baseline.BASE}/hosted-runtime-original.zip", baseline.accepted.ARCHIVES["hosted"])
    runtime = baseline.accepted.read_json(hosted["account-replay/account-replay.json"])
    binding = baseline.accepted.read_json(original["source-bindings.json"])
    obs = baseline.evidence.document((root / baseline.OBSERVATIONS).read_bytes(), baseline.EVIDENCE_RESULT)
    observations = {o["opportunity_id"]: o for o in obs["rows"]}
    references = decision_references(root, observations)
    sources = {o["opportunity_id"]: o for o in binding["opportunities"]}
    require([p["path_id"] for p in runtime["paths"]] == [p["path_id"] for p in previous["paths"]], "path population/order differs")
    paths = [analyze_path(p, old, references, sources) for p, old in zip(runtime["paths"], previous["paths"])]
    require(sum(len(p["decisions"]) for p in paths) == 744 and sum(len(p["sell_fills"]) for p in paths) == 669
        and sum(len(p["episodes"]) for p in paths) == 300, "diagnostic population differs")
    return seal({"contract_id": ID, "artifact_type": "saved_execution_loss_attribution_diagnostic",
        "contract_content_sha256": contract["content_sha256"], "baseline_report_content_sha256": BASELINE_REPORT,
        "runtime_content_sha256": baseline.accepted.RUNTIME, "metric_definitions": DEFINITIONS,
        "population": previous["population"], "gate_binding": previous["gate_binding"],
        "original_decision_references_verified": 86, "all_account_results_unchanged": True,
        "all_reason_stage_and_entry_bridges_reconcile": True, "paths": paths, **BOUNDARY})


def render_markdown(report):
    checked(report)
    lines = ["# Loss attribution from the saved conditional replay", "",
        "All rows describe separate original account paths. Reasons and stages are alternative views",
        "of the same exits; they must not be added together. All 30 dates and unavailable histories remain.", "",
        "## Entry price accounting bridge", "",
        "The reference component uses actual exit prices and actual quantities with the original decision ask.",
        "It is an algebraic benchmark, not an alternative execution result or attainable profit estimate.", "",
        "| Path | Reference-to-actual-exit component ($) | Entry shortfall debit ($) | Fees ($) | Actual net P&L ($) |",
        "|---|---:|---:|---:|---:|"]
    for p in report["paths"]:
        t = p["totals"]
        lines.append("| " + " | ".join([p["path_id"], *(t[k] for k in ("reference_to_actual_exits_component_usd", "entry_execution_shortfall_usd", "fees_usd", "net_pnl_usd"))]) + " |")
    lines += ["", "## Gross P&L recorded at each exit reason", "",
        "Entry and exit fees are excluded from this table; the price bridge above includes all fees.", "",
        "| Path | Initial stop ($) | Breakeven stop ($) | First target ($) | First red candle ($) | Account risk ($) |",
        "|---|---:|---:|---:|---:|---:|"]
    for p in report["paths"]:
        lines.append("| " + " | ".join([p["path_id"], *(g["gross_pnl_usd"] for g in p["exit_reasons"])]) + " |")
    lines += ["", "## Sizing and execution", "",
        "| Path | Entry shares filled/requested | First-entry net ($) | Re-entry net ($) | Initial-stop signed shortfall ($) | Unfilled sell orders |",
        "|---|---:|---:|---:|---:|---:|"]
    for p in report["paths"]:
        lines.append("| " + " | ".join(map(str,[p["path_id"], f'{p["sizing"]["filled_entry_shares"]}/{p["sizing"]["requested_entry_shares"]}',
            *(g["net_pnl_usd"] for g in p["entry_cohorts"]), p["initial_stop_execution"]["signed_shortfall_from_initial_stop_usd"], p["sell_execution"]["unfilled_orders"]])) + " |")
    lines += ["", "[All daily records, decisions, position episodes, sell orders and sell fills](report.json).", "",
        "Attribution identifies where P&L was booked; it does not establish the causal effect of changing an entry,",
        "size, stop, wait or continuation rule. Blocked/unfilled entries receive no hypothetical P&L.",
        "The original single-venue quote policy, zero-commission fee assumptions and conditional coverage limits apply.",
        "No historical replay, market request, Ross-label access or policy promotion occurred.", "",
        f'Contract: `{report["contract_content_sha256"]}`.  ', f'Report: `{report["content_sha256"]}`.', ""]
    return "\n".join(lines)
