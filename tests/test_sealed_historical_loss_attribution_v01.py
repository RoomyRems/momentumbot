from copy import deepcopy
from decimal import Decimal, localcontext
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from momentumbot.research import sealed_historical_loss_attribution_v01 as m


def order_fixture():
    events = []
    for i, reason in enumerate(("first_target", "initial_stop", "initial_stop", "initial_stop")):
        events.append({"event_type": "sell_submitted", "reason": reason, "opportunity_id": "op-1",
            "order": {"order_id": f"order-{i}", "decision_ts_ns": 10 + 10 * i, "quantity": 1}})
    snapshot = {"exit_residual_events": [], "exit_continuation_events": [], "exit_wait_events": []}
    for i, key, kind, number in ((2, "exit_residual_events", "residual_submitted", 2),
            (3, "exit_continuation_events", "continuation_submitted", 3)):
        snapshot[key].append(m.seal({"event_type": kind, "order": deepcopy(events[i]["order"]),
            "opportunity_id": "op-1", "intent": {"reason": "initial_stop"},
            "context": {"terminal_attempt_number": number}}))
    snapshot["exit_wait_events"].append(m.seal({"event_type": "wait_submitted", "order": deepcopy(events[3]["order"]),
        "opportunity_id": "op-1", "signal": {"decision_ts_ns": 35, "reason": "initial_stop"}}))
    return {"events": events, "reconciliation_snapshot": snapshot}


def sell_fixture():
    return [{"quantity": 1, "fill_price_usd": "11", "exit_fee_usd": ".01"},
            {"quantity": 1, "fill_price_usd": "9", "exit_fee_usd": ".01"}]


class PriceTests(unittest.TestCase):
    def test_exact_bridge_separates_entry_shortfall_and_fees(self):
        result = m.price_bridge("10", "9.90", 2, sell_fixture(), ".10")
        self.assertEqual(result, {"reference_to_actual_exits_component_usd": "0.2",
            "entry_execution_shortfall_usd": "0.2", "gross_pnl_usd": "0",
            "fees_usd": "0.12", "net_pnl_usd": "-0.12"})

    def test_price_improvement_is_signed_not_clipped(self):
        result = m.price_bridge("9.80", "10", 2, sell_fixture(), ".10")
        self.assertEqual(result["entry_execution_shortfall_usd"], "-0.4")
        self.assertEqual(result["net_pnl_usd"], "0.28")
        self.assertEqual(result["reference_to_actual_exits_component_usd"], "0")

    def test_exact_filled_size_not_requested_size_used(self):
        with self.assertRaisesRegex(ValueError, "exact entry"):
            m.price_bridge("10", "9.90", 100, sell_fixture(), ".10")

    def test_partial_exits_all_required(self):
        with self.assertRaisesRegex(ValueError, "exact entry"):
            m.price_bridge("10", "9.90", 2, sell_fixture()[:1], ".10")

    def test_float_stop_uses_serialized_decimal_not_binary_expansion(self):
        self.assertEqual(m.source_price(3.35), Decimal("3.35"))

    def test_invalid_or_nonfinite_price_rejected(self):
        for value in (True, 0, "-1", "NaN", float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                m.source_price(value)

    def test_outer_decimal_context_does_not_change_bridge(self):
        expected = m.price_bridge("10", "9.90", 2, sell_fixture(), ".10")
        with localcontext() as ctx:
            ctx.prec = 2
            self.assertEqual(m.price_bridge("10", "9.90", 2, sell_fixture(), ".10"), expected)


class OrderTests(unittest.TestCase):
    def test_targets_replacements_and_waiting_are_separate_dimensions(self):
        runtime = order_fixture();before = deepcopy(runtime)
        orders = m.index_orders(runtime)
        self.assertEqual([o["stage"] for o in orders.values()], list(m.STAGES))
        self.assertEqual(orders["order-3"]["wait_ns"], 5)
        self.assertTrue(orders["order-3"]["waited"])
        self.assertEqual(runtime, before)

    def test_unfilled_order_is_retained_without_a_fill(self):
        self.assertEqual(len(m.index_orders(order_fixture())), 4)

    def test_missing_replacement_authority_not_treated_as_first_terminal(self):
        runtime = order_fixture();runtime["reconciliation_snapshot"]["exit_residual_events"] = []
        with self.assertRaisesRegex(ValueError, "terminal order sequence"):
            m.index_orders(runtime)

    def test_wrong_sidecar_order_is_rejected(self):
        runtime = order_fixture();event = runtime["reconciliation_snapshot"]["exit_residual_events"][0]
        event["order"]["quantity"] = 2
        runtime["reconciliation_snapshot"]["exit_residual_events"][0] = m.seal(event)
        with self.assertRaisesRegex(ValueError, "order binding"):
            m.index_orders(runtime)

    def test_reused_replacement_evidence_is_rejected(self):
        runtime = order_fixture();rows = runtime["reconciliation_snapshot"]["exit_residual_events"]
        rows.append(deepcopy(rows[0]))
        with self.assertRaisesRegex(ValueError, "unique"):
            m.index_orders(runtime)

    def test_wrong_terminal_attempt_number_rejected(self):
        runtime = order_fixture();event = runtime["reconciliation_snapshot"]["exit_continuation_events"][0]
        event["context"]["terminal_attempt_number"] = 4
        runtime["reconciliation_snapshot"]["exit_continuation_events"][0] = m.seal(event)
        with self.assertRaisesRegex(ValueError, "terminal order sequence"):
            m.index_orders(runtime)

    def test_duplicate_order_id_rejected(self):
        runtime = order_fixture();runtime["events"].append(deepcopy(runtime["events"][0]))
        with self.assertRaisesRegex(ValueError, "repeated"):
            m.index_orders(runtime)

    def test_negative_wait_rejected(self):
        runtime = order_fixture();event = runtime["reconciliation_snapshot"]["exit_wait_events"][0]
        event["signal"]["decision_ts_ns"] = 99
        runtime["reconciliation_snapshot"]["exit_wait_events"][0] = m.seal(event)
        with self.assertRaisesRegex(ValueError, "negative"):
            m.index_orders(runtime)

    def test_unknown_exit_reason_rejected(self):
        runtime = order_fixture();runtime["events"][0]["reason"] = "invented"
        with self.assertRaisesRegex(ValueError, "unknown"):
            m.index_orders(runtime)


class GroupTests(unittest.TestCase):
    def test_exit_groups_do_not_double_debit_entry_fees(self):
        rows = [{"entry_fill_id": "entry-A", "reason": reason, "quantity": 1, "gross_pnl_usd": gross, "exit_fee_usd": ".01"}
                for reason, gross in (("first_target", "1"), ("initial_stop", "-1"))]
        result = m.group_exits(rows, "reason", m.REASONS)
        self.assertEqual(len(result), 5)
        self.assertEqual(m.sum_money(result, "pnl_after_exit_fees_before_entry_fees_usd"), Decimal("-.02"))
        self.assertEqual(m.sum_money(result, "exit_fees_usd"), Decimal(".02"))
        self.assertEqual(sum(g["episodes_touched"] for g in result), 2)  # same episode touches two reasons

    def test_zero_groups_and_no_trade_population_are_explicit(self):
        result = m.group_exits([], "stage", m.STAGES)
        self.assertEqual(len(result), 4)
        self.assertTrue(all(r["sold_shares"] == r["sell_fills"] == 0 and r["gross_pnl_usd"] == "0" for r in result))

    def test_unknown_group_cannot_silently_drop_losses(self):
        with self.assertRaisesRegex(ValueError, "unregistered"):
            m.group_exits([{"reason": "invented"}], "reason", m.REASONS)


class FrozenEvidenceTests(unittest.TestCase):
    def test_registration_preserves_baseline_and_closes_counterfactual_claims(self):
        contract = m.baseline.accepted.read_json((ROOT / f"research/strategy/{m.ID}.json").read_bytes())
        self.assertEqual(m.check_registration(ROOT, contract["content_sha256"]), contract)
        self.assertTrue(contract["baseline_financial_outcomes_known_before_registration"])
        self.assertFalse(contract["runtime_or_strategy_thresholds_changed"])
        self.assertFalse(contract["counterfactual_performance_established"])

    def test_report_reproduces_exactly_from_saved_evidence(self):
        saved = m.baseline.accepted.read_json((ROOT / f"research/data-audits/{m.ID}/report.json").read_bytes())
        self.assertEqual(m.analyze(ROOT, saved["contract_content_sha256"]), saved)
        self.assertEqual(len(saved["paths"]), 12)
        self.assertEqual(sum(len(p["daily"]) for p in saved["paths"]), 360)
        self.assertEqual(sum(len(p["decisions"]) for p in saved["paths"]), 744)

    def test_wrong_external_registration_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "external diagnostic"):
            m.check_registration(ROOT, "0" * 64)


if __name__ == "__main__":
    unittest.main()
