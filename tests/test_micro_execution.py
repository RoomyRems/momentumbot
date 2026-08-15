import unittest

import pandas as pd

from momentumbot.micro_execution import (
    MicroEntryPlan,
    MicroExecutionStatus,
    build_completed_bar_breakout_plan,
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

    def test_odd_lot_can_add_volume_but_cannot_trigger_price_entry(self):
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
        eligible = price_eligible_trades(trades)
        self.assertEqual(len(eligible), 1)
        outcome = simulate_micro_entry(plan, trades)
        self.assertEqual(outcome.status, MicroExecutionStatus.FILLED_OPEN)
        self.assertEqual(outcome.fill_time, pd.Timestamp("2026-01-02T12:00:12Z"))
        self.assertEqual(outcome.fill_price, 5.02)

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
