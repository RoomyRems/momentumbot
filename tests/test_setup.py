from __future__ import annotations

import unittest

import pandas as pd

from momentumbot.models import MomentumPhase, current_general_2026
from momentumbot.setup import build_first_pullback_plan, evaluate_first_pullback_plan
from tests.helpers import frame, strong_pullback_bars


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.profile = current_general_2026()
        self.bars = strong_pullback_bars()

    def test_valid_pullback_builds_next_bar_plan(self):
        plan = build_first_pullback_plan("TEST", self.bars, self.profile, pullback_number=1)
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertAlmostEqual(plan.trigger_price, 6.14)
        self.assertAlmostEqual(plan.stop_price, 6.02)
        self.assertGreaterEqual(plan.reward_r_to_prior_high, 2.0)
        self.assertEqual(plan.features.momentum_phase, MomentumPhase.FRONT_SIDE)
        evaluation = evaluate_first_pullback_plan(
            "TEST", self.bars, self.profile, pullback_number=1
        )
        self.assertEqual(evaluation.reason, "plan")
        self.assertEqual(evaluation.plan, plan)

    def test_deep_retrace_rejected(self):
        bars = self.bars.copy()
        bars.iloc[-1, bars.columns.get_loc("low")] = 5.3
        bars.iloc[-1, bars.columns.get_loc("close")] = 5.4
        self.assertIsNone(build_first_pullback_plan("TEST", bars, self.profile))
        self.assertEqual(
            evaluate_first_pullback_plan("TEST", bars, self.profile).reason,
            "retrace_above_half",
        )

    def test_heavy_pullback_volume_rejected(self):
        bars = self.bars.copy()
        bars.iloc[-2:, bars.columns.get_loc("volume")] = 2_000_000
        self.assertIsNone(build_first_pullback_plan("TEST", bars, self.profile))
        self.assertEqual(
            evaluate_first_pullback_plan("TEST", bars, self.profile).reason,
            "pullback_volume_not_lower",
        )

    def test_break_below_vwap_or_ema_rejected(self):
        bars = self.bars.copy()
        bars.iloc[-1, bars.columns.get_loc("low")] = 4.2
        bars.iloc[-1, bars.columns.get_loc("close")] = 6.08
        self.assertIsNone(build_first_pullback_plan("TEST", bars, self.profile))

    def test_future_bar_does_not_change_existing_plan(self):
        first = build_first_pullback_plan("TEST", self.bars, self.profile)
        future = frame(
            [(6.08, 20.0, 1.0, 10.0, 9_000_000)],
            start=str(self.bars.index[-1] + pd.Timedelta(minutes=1)),
        )
        combined = pd.concat([self.bars, future])
        second = build_first_pullback_plan(
            "TEST", combined.loc[: self.bars.index[-1]], self.profile
        )
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
