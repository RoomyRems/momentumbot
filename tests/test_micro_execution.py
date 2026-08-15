import unittest

import pandas as pd

from momentumbot.micro_execution import (
    MicroEntryPlan,
    MicroExecutionStatus,
    MicroTriggerMode,
    build_completed_bar_breakout_plan,
    execution_eligible_trades,
    price_eligible_trades,
    simulate_micro_entries,
    simulate_micro_entry,
)


def trade_frame(rows):
    index = pd.to_datetime([row.pop("timestamp") for row in rows], utc=True)
    return pd.DataFrame(rows, index=index)


class MicroExecutionTests(unittest.TestCase):
    def test_completed_bar_arms_only_after_close_and_for_one_next_bar(self):
        start = pd.Timestamp("2026-06-10T11:44:50Z")
        bar = pd.Series(
            {
                "high": 3.10,
                "low": 2.82,
                "close": 3.06,
                "high_time": pd.Timestamp("2026-06-10T11:44:55.455Z"),
                "close_time": pd.Timestamp("2026-06-10T11:44:59.900Z"),
            }
        )
        plan = build_completed_bar_breakout_plan("DSY", start, bar)
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.armed_at, pd.Timestamp("2026-06-10T11:45:00Z"))
        self.assertEqual(plan.expires_at, pd.Timestamp("2026-06-10T11:45:10Z"))
        self.assertEqual(plan.breakout_level, 3.10)
        self.assertEqual(plan.minimum_new_high_price, 3.11)
        self.assertEqual(plan.stop_price, 2.82)

    def test_bar_that_finishes_at_high_does_not_arm(self):
        start = pd.Timestamp("2026-06-10T11:44:40Z")
        bar = pd.Series(
            {
                "high": 2.85,
                "low": 2.46,
                "close": 2.85,
                "high_time": pd.Timestamp("2026-06-10T11:44:49.9Z"),
                "close_time": pd.Timestamp("2026-06-10T11:44:49.9Z"),
            }
        )
        self.assertIsNone(build_completed_bar_breakout_plan("DSY", start, bar))

    def test_clean_odd_lot_is_execution_visible_but_not_chart_visible(self):
        plan = MicroEntryPlan(
            symbol="ABC",
            source_bar_start=pd.Timestamp("2026-01-02T12:00:00Z"),
            armed_at=pd.Timestamp("2026-01-02T12:00:10Z"),
            expires_at=pd.Timestamp("2026-01-02T12:00:20Z"),
            breakout_level=5.00,
            minimum_new_high_price=5.01,
            stop_price=4.80,
        )
        trades = trade_frame(
            [
                {
                    "timestamp": "2026-01-02T12:00:11Z",
                    "price": 5.05,
                    "size": 5,
                    "conditions": ("@", "I"),
                    "tape": "C",
                },
                {
                    "timestamp": "2026-01-02T12:00:12Z",
                    "price": 5.02,
                    "size": 100,
                    "conditions": ("@",),
                    "tape": "C",
                },
            ]
        )
        chart_path = price_eligible_trades(trades)
        execution_path = execution_eligible_trades(trades)
        self.assertEqual(len(chart_path), 1)
        self.assertEqual(float(chart_path.iloc[0]["price"]), 5.02)
        self.assertEqual(len(execution_path), 2)
        self.assertTrue(bool(execution_path.iloc[0]["_execution_via_odd_lot"]))

        canonical = simulate_micro_entry(plan, trades)
        self.assertEqual(canonical.trigger_mode, MicroTriggerMode.CHART_PRICE)
        self.assertEqual(canonical.trigger_time, pd.Timestamp("2026-01-02T12:00:12Z"))
        self.assertEqual(canonical.fill_price, 5.02)
        self.assertFalse(canonical.trigger_via_odd_lot)
        self.assertFalse(canonical.fill_via_odd_lot)

        sensitivity = simulate_micro_entry(
            plan,
            trades,
            trigger_mode=MicroTriggerMode.EXECUTION_PROXY,
        )
        self.assertEqual(sensitivity.trigger_time, pd.Timestamp("2026-01-02T12:00:11Z"))
        self.assertEqual(sensitivity.fill_price, 5.05)
        self.assertTrue(sensitivity.trigger_via_odd_lot)
        self.assertTrue(sensitivity.fill_via_odd_lot)

    def test_odd_lot_does_not_override_another_disqualifying_condition(self):
        trades = trade_frame(
            [
                {
                    "timestamp": "2026-01-02T12:00:11Z",
                    "price": 5.20,
                    "size": 7,
                    "conditions": ("B", "I"),
                    "tape": "A",
                },
                {
                    "timestamp": "2026-01-02T12:00:12Z",
                    "price": 5.10,
                    "size": 100,
                    "conditions": ("@",),
                    "tape": "A",
                },
            ]
        )
        execution_path = execution_eligible_trades(trades)
        self.assertEqual(len(execution_path), 1)
        self.assertEqual(float(execution_path.iloc[0]["price"]), 5.10)
        self.assertFalse(bool(execution_path.iloc[0]["_execution_via_odd_lot"]))

    def test_dsy_shaped_trigger_modes_bracket_observed_price_path(self):
        plan = MicroEntryPlan(
            symbol="DSY",
            source_bar_start=pd.Timestamp("2026-06-10T11:44:50Z"),
            armed_at=pd.Timestamp("2026-06-10T11:45:00Z"),
            expires_at=pd.Timestamp("2026-06-10T11:45:10Z"),
            breakout_level=3.10,
            minimum_new_high_price=3.11,
            stop_price=2.82,
        )
        trades = trade_frame(
            [
                {
                    "timestamp": "2026-06-10T11:45:04.159Z",
                    "price": 3.10,
                    "size": 100,
                    "conditions": ("@", "T"),
                    "tape": "C",
                },
                {
                    "timestamp": "2026-06-10T11:45:04.165425Z",
                    "price": 3.12,
                    "size": 98,
                    "conditions": ("@", "T", "I"),
                    "tape": "C",
                },
                {
                    "timestamp": "2026-06-10T11:45:04.211Z",
                    "price": 3.15,
                    "size": 163,
                    "conditions": ("@", "T"),
                    "tape": "C",
                },
            ]
        )
        canonical = simulate_micro_entry(plan, trades)
        self.assertEqual(canonical.trigger_print_price, 3.15)
        self.assertEqual(canonical.fill_price, 3.15)
        self.assertFalse(canonical.trigger_via_odd_lot)
        self.assertFalse(canonical.fill_via_odd_lot)

        sensitivity = simulate_micro_entry(
            plan,
            trades,
            trigger_mode=MicroTriggerMode.EXECUTION_PROXY,
        )
        self.assertEqual(sensitivity.trigger_print_price, 3.12)
        self.assertEqual(sensitivity.fill_price, 3.12)
        self.assertTrue(sensitivity.trigger_via_odd_lot)
        self.assertTrue(sensitivity.fill_via_odd_lot)

    def test_entry_latency_delays_fill_without_changing_trigger(self):
        plan = MicroEntryPlan(
            symbol="ABC",
            source_bar_start=pd.Timestamp("2026-01-02T12:00:00Z"),
            armed_at=pd.Timestamp("2026-01-02T12:00:10Z"),
            expires_at=pd.Timestamp("2026-01-02T12:00:20Z"),
            breakout_level=5.00,
            minimum_new_high_price=5.01,
            stop_price=4.80,
        )
        trades = trade_frame(
            [
                {
                    "timestamp": "2026-01-02T12:00:11.000Z",
                    "price": 5.02,
                    "size": 100,
                    "conditions": ("@",),
                    "tape": "C",
                },
                {
                    "timestamp": "2026-01-02T12:00:11.020Z",
                    "price": 5.05,
                    "size": 20,
                    "conditions": ("@", "I"),
                    "tape": "C",
                },
                {
                    "timestamp": "2026-01-02T12:00:11.060Z",
                    "price": 5.10,
                    "size": 100,
                    "conditions": ("@",),
                    "tape": "C",
                },
            ]
        )
        zero = simulate_micro_entry(plan, trades, entry_latency_ms=0)
        delayed = simulate_micro_entry(plan, trades, entry_latency_ms=50)
        self.assertEqual(zero.trigger_time, delayed.trigger_time)
        self.assertEqual(zero.fill_price, 5.02)
        self.assertEqual(delayed.fill_time, pd.Timestamp("2026-01-02T12:00:11.060Z"))
        self.assertEqual(delayed.fill_price, 5.10)
        self.assertEqual(delayed.entry_latency_ms, 50)

    def test_gap_above_trigger_is_recorded_as_entry_slippage(self):
        plan = MicroEntryPlan(
            symbol="DSY",
            source_bar_start=pd.Timestamp("2026-06-10T11:44:50Z"),
            armed_at=pd.Timestamp("2026-06-10T11:45:00Z"),
            expires_at=pd.Timestamp("2026-06-10T11:45:10Z"),
            breakout_level=3.10,
            minimum_new_high_price=3.11,
            stop_price=2.82,
        )
        trades = trade_frame(
            [
                {
                    "timestamp": "2026-06-10T11:45:04.012Z",
                    "price": 3.10,
                    "size": 100,
                    "conditions": ("@", "T"),
                    "tape": "C",
                },
                {
                    "timestamp": "2026-06-10T11:45:04.211Z",
                    "price": 3.15,
                    "size": 163,
                    "conditions": ("@", "T"),
                    "tape": "C",
                },
            ]
        )
        outcome = simulate_micro_entry(plan, trades)
        self.assertEqual(outcome.fill_price, 3.15)
        self.assertAlmostEqual(outcome.entry_slippage or 0.0, 0.04)
        self.assertFalse(outcome.trigger_via_odd_lot)

    def test_plan_expires_before_late_breakout(self):
        plan = MicroEntryPlan(
            symbol="ABC",
            source_bar_start=pd.Timestamp("2026-01-02T12:00:00Z"),
            armed_at=pd.Timestamp("2026-01-02T12:00:10Z"),
            expires_at=pd.Timestamp("2026-01-02T12:00:20Z"),
            breakout_level=5.00,
            minimum_new_high_price=5.01,
            stop_price=4.80,
        )
        trades = trade_frame(
            [
                {
                    "timestamp": "2026-01-02T12:00:20Z",
                    "price": 5.20,
                    "size": 100,
                    "conditions": ("@",),
                    "tape": "C",
                }
            ]
        )
        self.assertEqual(
            simulate_micro_entry(plan, trades).status,
            MicroExecutionStatus.NOT_TRIGGERED,
        )

    def test_stop_and_target_use_ordered_post_fill_prints(self):
        plan = MicroEntryPlan(
            symbol="ABC",
            source_bar_start=pd.Timestamp("2026-01-02T12:00:00Z"),
            armed_at=pd.Timestamp("2026-01-02T12:00:10Z"),
            expires_at=pd.Timestamp("2026-01-02T12:00:20Z"),
            breakout_level=5.00,
            minimum_new_high_price=5.01,
            stop_price=4.80,
        )
        stop_first = trade_frame(
            [
                {
                    "timestamp": "2026-01-02T12:00:11Z",
                    "price": 5.02,
                    "size": 100,
                    "conditions": ("@",),
                    "tape": "C",
                },
                {
                    "timestamp": "2026-01-02T12:00:12Z",
                    "price": 4.75,
                    "size": 100,
                    "conditions": ("@",),
                    "tape": "C",
                },
                {
                    "timestamp": "2026-01-02T12:00:13Z",
                    "price": 5.50,
                    "size": 100,
                    "conditions": ("@",),
                    "tape": "C",
                },
            ]
        )
        stopped = simulate_micro_entry(plan, stop_first, target_price=5.40)
        self.assertEqual(stopped.status, MicroExecutionStatus.STOPPED)
        self.assertEqual(stopped.exit_price, 4.75)
        self.assertLess(stopped.realized_r or 0.0, -1.0)

        target_first = trade_frame(
            [
                {
                    "timestamp": "2026-01-02T12:00:11Z",
                    "price": 5.02,
                    "size": 100,
                    "conditions": ("@",),
                    "tape": "C",
                },
                {
                    "timestamp": "2026-01-02T12:00:12Z",
                    "price": 5.45,
                    "size": 100,
                    "conditions": ("@",),
                    "tape": "C",
                },
                {
                    "timestamp": "2026-01-02T12:00:13Z",
                    "price": 4.70,
                    "size": 100,
                    "conditions": ("@",),
                    "tape": "C",
                },
            ]
        )
        targeted = simulate_micro_entry(plan, target_first, target_price=5.40)
        self.assertEqual(targeted.status, MicroExecutionStatus.TARGET_HIT)
        self.assertEqual(targeted.exit_price, 5.40)

    def test_batch_execution_matches_single_plan_semantics(self):
        plans = (
            MicroEntryPlan(
                symbol="ABC",
                source_bar_start=pd.Timestamp("2026-01-02T12:00:00Z"),
                armed_at=pd.Timestamp("2026-01-02T12:00:10Z"),
                expires_at=pd.Timestamp("2026-01-02T12:00:20Z"),
                breakout_level=5.00,
                minimum_new_high_price=5.01,
                stop_price=4.80,
            ),
            MicroEntryPlan(
                symbol="ABC",
                source_bar_start=pd.Timestamp("2026-01-02T12:00:10Z"),
                armed_at=pd.Timestamp("2026-01-02T12:00:20Z"),
                expires_at=pd.Timestamp("2026-01-02T12:00:30Z"),
                breakout_level=5.30,
                minimum_new_high_price=5.31,
                stop_price=5.00,
            ),
        )
        trades = trade_frame(
            [
                {
                    "timestamp": "2026-01-02T12:00:12Z",
                    "price": 5.02,
                    "size": 100,
                    "conditions": ("@",),
                    "tape": "C",
                },
                {
                    "timestamp": "2026-01-02T12:00:22Z",
                    "price": 5.35,
                    "size": 100,
                    "conditions": ("@",),
                    "tape": "C",
                },
            ]
        )
        batch = simulate_micro_entries(plans, trades)
        singles = tuple(simulate_micro_entry(plan, trades) for plan in plans)
        self.assertEqual(batch, singles)


if __name__ == "__main__":
    unittest.main()
