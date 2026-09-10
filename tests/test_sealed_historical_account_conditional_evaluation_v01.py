from copy import deepcopy
from decimal import Decimal, localcontext
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from momentumbot.research import sealed_historical_account_conditional_evaluation_v01 as m


def journal_fixture():
    # Hand-calculated cash states: partial exits lose $2.20 net; same-activation
    # re-entry wins $3.96. Five fills comprise TWO episodes, net +$1.76.
    specs = [
        ("buy", 10, "5", ".10", ".10", "49.90", "0", "0", "-.10", "0", 10),
        ("sell", 4, "6", ".04", ".14", "73.86", "4", "4", "3.86", "3.86", 6),
        ("sell", 6, "4", ".06", ".20", "97.80", "-6", "-2", "-2.20", "3.86", 0),
        ("buy", 2, "5", ".02", ".22", "87.78", "0", "-2", "-2.22", "3.86", 2),
        ("sell", 2, "7", ".02", ".24", "101.76", "4", "2", "1.76", "3.86", 0),
    ]
    rows, entry_id = [], None
    for i, (side, qty, price, fee, total, cash, delta, gross, net, high, remaining) in enumerate(specs):
        receipt = {"fill_price": price, "quantity": qty, "fill_time_ns": 100 + i}
        if side == "buy":
            entry_id = f"entry-{i}"
            receipt.update({"fill_id": entry_id, "opportunity_id": f"opportunity-{i}",
                "activation_id": "activation-A", "symbol": "TEST",
                "order": {"order_id": f"order-{i}", "quantity": qty, "limit_price": price}})
        else:
            receipt.update({"entry_fill_id": entry_id, "order_id": f"order-{i}"})
        receipt = m.seal(receipt)
        trade = {"fill_id": entry_id if side == "buy" else "sell-fill-" + receipt["content_sha256"],
            "order_id": f"order-{i}", "price": price, "quantity": qty, "side": side, "timestamp_ns": 100 + i}
        row = {"sequence": i, "previous_event_sha256": rows[-1]["content_sha256"] if rows else None,
            "activation_id": "activation-A", "execution_evidence": receipt,
            "fee_application": {"trade": trade, "incremental_charge":
                {"commission": fee, "sec": "0", "taf": "0", "cat": "0", "total": fee},
                "cumulative_fees": {"total_charged": total}},
            "known_at_ns": 100 + i, "clock_phase": 2, "gross_realized_delta": delta,
            "gross_realized_after": gross, "net_realized_after": net, "net_high_water_after": high,
            "cash_after": cash, "remaining_quantity": remaining}
        rows.append(m.seal(row))
    return rows


def reseal_journal(rows):
    for i, row in enumerate(rows):
        row["previous_event_sha256"] = rows[i - 1]["content_sha256"] if i else None
        rows[i] = m.seal(row)
    return rows


def gate_fixture():
    journal = journal_fixture()[:1]
    row = {"opportunity_id": "opportunity-0", "input_status": "available",
        "reason": "causal_reference_and_window_available", "availability_content_sha256": "a" * 64,
        "disposition": "entry_submitted"}
    gap = {"opportunity_id": "withheld", "input_status": "unavailable",
        "reason": "unavailable_no_fresh_decision_quote", "availability_content_sha256": "b" * 64,
        "disposition": "unavailable_input"}
    observations = {d["opportunity_id"]: {"original_" + k: d[k] for k in
        ("input_status", "reason", "availability_content_sha256")} for d in (row, gap)}
    for oid, obs in observations.items():
        obs.update({"policy_id": m.evidence.POLICY_ID, "order_authorized": False,
            "entry_gate": "withhold_entry_under_observed_update_policy" if oid == "withheld"
                else "reference_present_requires_remaining_entry_checks"})
    events = [{"event_type": "opportunity_disposition", "opportunity_id": "opportunity-0",
        "disposition": "entry_submitted", "order": journal[0]["execution_evidence"]["order"]},
        {"event_type": "entry_fill_confirmed", "opportunity_id": "opportunity-0", "at_ns": 100, "journal_index": 0}]
    return {"opportunity_dispositions": [row, gap], "events": events,
        "reconciliation_snapshot": {"journal": journal}}, observations


class CashFlowTests(unittest.TestCase):
    def test_partial_exits_and_reentry_are_two_net_episodes(self):
        result = m.reconcile_journal(journal_fixture(), "100")
        self.assertEqual(result["cash_usd"], "101.76")
        self.assertEqual(result["gross_pnl_usd"], "2")
        self.assertEqual(result["fees_usd"], "0.24")
        self.assertEqual(result["net_pnl_usd"], "1.76")
        self.assertEqual(result["buy_shares"], 12)
        self.assertEqual(result["sell_shares"], 12)
        self.assertEqual([e["sell_fill_count"] for e in result["episodes"]], [2, 1])
        self.assertEqual([e["net_pnl_usd"] for e in result["episodes"]], ["-2.2", "3.96"])
        metrics = m.episode_metrics(result["episodes"])
        self.assertEqual(metrics["net_profit_factor"], "1.800000")
        self.assertEqual(metrics["net_win_rate_pct"], "50.000000")
        self.assertEqual(metrics["net_expectancy_usd"], "0.880000")

    def test_empty_session_has_no_phantom_trade_or_fee(self):
        result = m.reconcile_journal([], "100")
        self.assertEqual(result["cash_usd"], "100")
        self.assertEqual(result["net_pnl_usd"], "0")
        self.assertEqual(result["episodes"], [])
        self.assertIsNone(m.episode_metrics([])["net_profit_factor"])
        self.assertIsNone(m.episode_metrics([])["net_win_rate_pct"])

    def test_outer_decimal_precision_cannot_change_money(self):
        expected = m.reconcile_journal(journal_fixture(), "100")
        with localcontext() as ctx:
            ctx.prec = 2
            self.assertEqual(m.reconcile_journal(journal_fixture(), "100"), expected)
            self.assertEqual(m.money(Decimal("123456789.123456789")), "123456789.123456789")

    def test_open_position_is_not_closed_trade(self):
        with self.assertRaisesRegex(ValueError, "open position"):
            m.reconcile_journal(journal_fixture()[:2], "100")

    def test_cash_fee_pnl_and_share_mutations_rejected(self):
        for key in ("cash_after", "gross_realized_delta", "gross_realized_after", "net_realized_after",
                    "net_high_water_after", "remaining_quantity"):
            rows = journal_fixture()
            rows[-1][key] = 5 if key == "remaining_quantity" else "999"
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "reconcile"):
                m.reconcile_journal(reseal_journal(rows), "100")

    def test_sell_must_bind_exact_entry(self):
        rows = journal_fixture()
        rows[1]["execution_evidence"]["entry_fill_id"] = "wrong-entry"
        rows[1]["execution_evidence"] = m.seal(rows[1]["execution_evidence"])
        with self.assertRaisesRegex(ValueError, "matching entry"):
            m.reconcile_journal(reseal_journal(rows), "100")

    def test_confirmed_fill_cannot_be_known_in_future(self):
        rows = journal_fixture()
        rows[0]["known_at_ns"] = 99
        with self.assertRaisesRegex(ValueError, "clock"):
            m.reconcile_journal(reseal_journal(rows), "100")

    def test_unknown_side_rejected(self):
        rows = journal_fixture()
        rows[0]["fee_application"]["trade"]["side"] = "short"
        with self.assertRaisesRegex(ValueError, "side"):
            m.reconcile_journal(reseal_journal(rows), "100")

    def test_fee_component_and_accumulation_mismatches_rejected(self):
        for field in ("incremental_charge", "cumulative_fees"):
            rows = journal_fixture()
            rows[-1]["fee_application"][field]["commission" if field == "incremental_charge" else "total_charged"] = "9"
            with self.subTest(field=field), self.assertRaises(ValueError):
                m.reconcile_journal(reseal_journal(rows), "100")

    def test_invalid_monetary_and_share_inputs_rejected(self):
        for val in ("NaN", "Infinity", 100.0):
            with self.subTest(value=val), self.assertRaises(ValueError):
                m.reconcile_journal([], val)
        for val in (True, 0, -1, 1.5):
            with self.subTest(value=val), self.assertRaises(ValueError):
                m.positive_int(val)

    def test_unsealed_journal_tampering_rejected(self):
        rows = journal_fixture()
        rows[0]["cash_after"] = "999"
        with self.assertRaisesRegex(ValueError, "seal"):
            m.reconcile_journal(rows, "100")


class MetricTests(unittest.TestCase):
    def test_zero_loss_profit_factor_is_null_and_flats_in_win_denominator(self):
        stats = m.episode_metrics([{"net_pnl_usd": "3"}, {"net_pnl_usd": "0"}])
        self.assertIsNone(stats["net_profit_factor"])
        self.assertEqual(stats["profit_factor_undefined_reason"], "no_net_losses")
        self.assertEqual(stats["net_win_rate_pct"], "50.000000")
        self.assertEqual(stats["flat_episodes"], 1)
        self.assertIsNone(stats["average_net_loss_usd"])

    def test_all_losses_profit_factor_is_zero(self):
        stats = m.episode_metrics([{"net_pnl_usd": "-3"}, {"net_pnl_usd": "-1"}])
        self.assertEqual(stats["net_profit_factor"], "0.000000")
        self.assertEqual(stats["net_expectancy_usd"], "-2.000000")
        self.assertIsNone(stats["average_net_win_usd"])

    def test_seed_highwater_and_zero_trade_dates_preserved(self):
        rows = [{"trading_date": day, "opening_equity_usd": op, "closing_equity_usd": cl, "net_pnl_usd": net}
            for day, op, cl, net in (("2025-05-30", "100", "90", "-10"),
                ("2025-06-02", "90", "90", "0"), ("2025-06-03", "90", "120", "30"),
                ("2025-06-04", "120", "105", "-15"))]
        result = m.equity_metrics("100", rows)
        self.assertEqual(result["max_session_close_drawdown_usd"], "15")
        self.assertEqual(result["max_session_close_drawdown_pct"], "12.500000")
        self.assertEqual(result["net_return_pct"], "5.000000")
        self.assertEqual(len(result["equity_curve"]), 4)
        self.assertEqual(result["equity_curve"][0]["drawdown_usd"], "10")

    def test_account_reseed_cannot_hide_loss(self):
        rows = [{"trading_date": "2025-05-30", "opening_equity_usd": "100",
                 "closing_equity_usd": "90", "net_pnl_usd": "-10"},
                {"trading_date": "2025-06-02", "opening_equity_usd": "100",
                 "closing_equity_usd": "100", "net_pnl_usd": "0"}]
        with self.assertRaisesRegex(ValueError, "carry"):
            m.equity_metrics("100", rows)

    def test_exact_nanosecond_identity(self):
        self.assertEqual(m.timestamp_ns("2025-05-30T12:57:03.147734566+00:00"), 1748609823147734566)
        self.assertEqual(m.timestamp_ns("1970-01-01T00:00:00+00:00"), 0)
        self.assertEqual(m.timestamp_ns("1970-01-01T00:00:00.1+00:00"), 100_000_000)

    def test_null_ratio_and_deterministic_rounding(self):
        self.assertIsNone(m.ratio(Decimal(0), Decimal(0)))
        self.assertEqual(m.ratio(Decimal(1), Decimal(6)), "0.166667")
        self.assertEqual(m.ratio(Decimal("1.2345665"), Decimal(1)), "1.234566")


class EntryBindingTests(unittest.TestCase):
    def test_withhold_preserved_and_available_fill_bound(self):
        runtime, observations = gate_fixture()
        before = deepcopy(runtime)
        outer, fills = m.bind_session(runtime, observations)
        self.assertEqual(set(outer), {"opportunity-0"})
        self.assertEqual(set(fills), {0})
        self.assertEqual(runtime, before)

    def test_withheld_opportunity_cannot_have_any_execution_event(self):
        runtime, observations = gate_fixture()
        runtime["events"][0]["opportunity_id"] = "withheld"
        with self.assertRaisesRegex(ValueError, "withheld"):
            m.bind_session(runtime, observations)

    def test_unavailable_cannot_be_relabelled(self):
        runtime, observations = gate_fixture()
        runtime["opportunity_dispositions"][1]["disposition"] = "no_trade"
        with self.assertRaisesRegex(ValueError, "preserve"):
            m.bind_session(runtime, observations)

    def test_missing_fill_event_is_rejected(self):
        runtime, observations = gate_fixture()
        runtime["events"].pop()
        with self.assertRaisesRegex(ValueError, "confirmed events"):
            m.bind_session(runtime, observations)

    def test_changed_source_evidence_is_rejected(self):
        runtime, observations = gate_fixture()
        observations["opportunity-0"]["original_availability_content_sha256"] = "wrong"
        with self.assertRaisesRegex(ValueError, "evidence"):
            m.bind_session(runtime, observations)

    def test_unverified_observation_is_not_known_abstention(self):
        runtime, observations = gate_fixture()
        observations["withheld"]["entry_gate"] = "unresolved"
        with self.assertRaisesRegex(ValueError, "unresolved"):
            m.bind_session(runtime, observations)

    def test_wrong_opportunity_fill_cannot_bypass_gate(self):
        runtime, observations = gate_fixture()
        runtime["reconciliation_snapshot"]["journal"][0]["execution_evidence"]["opportunity_id"] = "withheld"
        with self.assertRaisesRegex(ValueError, "submitted opportunity"):
            m.bind_session(runtime, observations)


class FrozenScopeTests(unittest.TestCase):
    def test_saved_report_reproduces_from_saved_artifacts_without_replay(self):
        saved = m.accepted.read_json((ROOT / f"research/data-audits/{m.ID}/report.json").read_bytes())
        self.assertEqual(m.evaluate(ROOT, saved["contract_content_sha256"]), saved)
        self.assertEqual(sum(p["closed_episodes"] for p in saved["paths"]), 300)
        self.assertEqual(sum(p["confirmed_fill_count"] for p in saved["paths"]), 969)
        self.assertTrue(all(p["session_count"] == 30 for p in saved["paths"]))

    def test_registered_code_and_scope(self):
        frozen = m.accepted.read_json((ROOT / f"research/strategy/{m.ID}.json").read_bytes())
        self.assertEqual(m.check_registration(ROOT, frozen["content_sha256"]), frozen)
        self.assertEqual(len(frozen["alternative_cells"]), 12)
        self.assertEqual(len(frozen["selected_dates"]), 30)
        self.assertFalse(frozen["historical_replay_required"])
        self.assertFalse(frozen["policy_promotion_eligible"])

    def test_wrong_external_registration_rejected(self):
        with self.assertRaisesRegex(ValueError, "external evaluation"):
            m.check_registration(ROOT, "0" * 64)


if __name__ == "__main__":
    unittest.main()
