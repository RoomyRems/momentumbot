import unittest

import pandas as pd

from momentumbot.micro_setup import (
    canonical_micro_setup_policy,
    detect_running_high_pullbacks,
    evaluate_micro_pullback_plan,
    geometry_only_micro_research_policy,
)


class MicroSetupTests(unittest.TestCase):
    def test_pullbacks_are_counted_only_after_candidate_start(self):
        index = pd.date_range("2026-07-09T11:31:00Z", periods=10, freq="10s")
        bars = pd.DataFrame(
            [
                (5.33, 4.08, 1000),
                (5.31, 4.73, 700),
                (5.04, 4.58, 500),
                (5.27, 4.76, 450),
                (5.41, 5.04, 900),
                (5.28, 5.08, 400),
                (5.41, 5.09, 350),
                (5.28, 4.94, 300),
                (5.24, 4.96, 250),
                (6.04, 5.24, 1500),
            ],
            columns=["high", "low", "volume"],
            index=index,
        )
        observations = detect_running_high_pullbacks(bars, start_at=index[0])
        self.assertEqual(len(observations), 2)
        self.assertEqual(observations[0].ordinal, 1)
        self.assertEqual(observations[0].pullback_bars, 3)
        self.assertEqual(observations[0].resumption_time, index[4].to_pydatetime())
        self.assertEqual(observations[1].ordinal, 2)
        self.assertEqual(observations[1].pullback_bars, 4)
        self.assertEqual(observations[1].trough_low, 4.94)
        self.assertEqual(observations[1].resumption_time, index[9].to_pydatetime())

    def test_unconfirmed_pullback_is_not_reported(self):
        index = pd.date_range("2026-07-09T11:31:00Z", periods=3, freq="10s")
        bars = pd.DataFrame(
            [(5.0, 4.8, 100), (4.9, 4.6, 80), (4.8, 4.5, 60)],
            columns=["high", "low", "volume"],
            index=index,
        )
        self.assertEqual(detect_running_high_pullbacks(bars, start_at=index[0]), ())

    @staticmethod
    def strong_micro_pullback() -> pd.DataFrame:
        index = pd.date_range("2026-08-12T11:00:00Z", periods=6, freq="10s")
        return pd.DataFrame(
            [
                (4.00, 4.10, 3.98, 4.08, 100),
                (4.08, 4.30, 4.05, 4.28, 200),
                (4.28, 4.55, 4.25, 4.52, 300),
                (4.52, 4.80, 4.50, 4.75, 400),
                (4.75, 4.76, 4.62, 4.65, 100),
                (4.65, 4.70, 4.60, 4.68, 80),
            ],
            columns=["open", "high", "low", "close", "volume"],
            index=index,
        )

    def test_canonical_micro_plan_uses_last_pullback_high_and_pullback_low(self):
        bars = self.strong_micro_pullback()
        vwap = pd.Series([4.40], index=pd.DatetimeIndex([bars.index[4]]))
        ema9 = pd.Series([4.50], index=pd.DatetimeIndex([bars.index[4]]))
        result = evaluate_micro_pullback_plan(
            "ABC",
            bars,
            candidate_qualified_at=bars.index[0],
            policy=canonical_micro_setup_policy(),
            pullback_number=1,
            vwap_available=vwap,
            ema9_available=ema9,
        )
        self.assertEqual(result.reason, "plan")
        self.assertIsNotNone(result.plan)
        self.assertIsNotNone(result.features)
        assert result.plan is not None
        assert result.features is not None
        self.assertEqual(result.plan.breakout_level, 4.70)
        self.assertEqual(result.plan.minimum_new_high_price, 4.71)
        self.assertEqual(result.plan.stop_price, 4.60)
        self.assertEqual(result.features.pullback_bars, 2)
        self.assertLess(result.features.retrace_fraction, 0.50)
        self.assertLess(
            result.features.pullback_mean_volume,
            result.features.impulse_mean_volume,
        )

    def test_equal_high_retest_does_not_replace_strict_running_high_peak(self):
        index = pd.date_range("2026-08-12T11:00:00Z", periods=6, freq="10s")
        bars = pd.DataFrame(
            [
                (4.00, 4.20, 4.00, 4.15, 100),
                (4.15, 4.50, 4.10, 4.45, 200),
                (4.45, 4.80, 4.40, 4.75, 300),
                (4.75, 4.70, 4.60, 4.65, 100),
                (4.65, 4.80, 4.62, 4.70, 90),
                (4.70, 4.72, 4.58, 4.60, 80),
            ],
            columns=["open", "high", "low", "close", "volume"],
            index=index,
        )
        result = evaluate_micro_pullback_plan(
            "ABC",
            bars,
            candidate_qualified_at=index[0],
            policy=geometry_only_micro_research_policy(),
        )
        self.assertEqual(result.reason, "plan")
        self.assertIsNotNone(result.features)
        assert result.features is not None
        self.assertEqual(result.features.peak_time, index[2].to_pydatetime())
        self.assertEqual(result.features.peak_high, 4.80)
        self.assertEqual(result.features.pullback_bars, 3)
        self.assertEqual(result.features.pullback_start, index[3].to_pydatetime())

    def test_canonical_policy_fails_closed_without_support_context(self):
        bars = self.strong_micro_pullback()
        result = evaluate_micro_pullback_plan(
            "ABC",
            bars,
            candidate_qualified_at=bars.index[0],
            policy=canonical_micro_setup_policy(),
        )
        self.assertEqual(result.reason, "micro_vwap_context_unavailable")
        self.assertIsNone(result.plan)

    def test_geometry_research_policy_can_run_without_support_series(self):
        bars = self.strong_micro_pullback()
        result = evaluate_micro_pullback_plan(
            "ABC",
            bars,
            candidate_qualified_at=bars.index[0],
            policy=geometry_only_micro_research_policy(),
        )
        self.assertEqual(result.reason, "plan")
        self.assertIsNotNone(result.plan)

    def test_support_series_does_not_read_future_values(self):
        bars = self.strong_micro_pullback()
        future = bars.index[-1] + pd.Timedelta(seconds=10)
        vwap = pd.Series([4.00], index=pd.DatetimeIndex([future]))
        ema9 = pd.Series([4.00], index=pd.DatetimeIndex([future]))
        result = evaluate_micro_pullback_plan(
            "ABC",
            bars,
            candidate_qualified_at=bars.index[0],
            policy=canonical_micro_setup_policy(),
            vwap_available=vwap,
            ema9_available=ema9,
        )
        self.assertEqual(result.reason, "micro_vwap_context_unavailable")

    def test_retrace_above_half_is_rejected(self):
        bars = self.strong_micro_pullback()
        bars.loc[bars.index[-1], "low"] = 4.20
        result = evaluate_micro_pullback_plan(
            "ABC",
            bars,
            candidate_qualified_at=bars.index[0],
            policy=geometry_only_micro_research_policy(),
        )
        self.assertEqual(result.reason, "micro_retrace_above_half")

    def test_pullback_volume_must_be_lighter(self):
        bars = self.strong_micro_pullback()
        bars.loc[bars.index[-2]:, "volume"] = 600
        result = evaluate_micro_pullback_plan(
            "ABC",
            bars,
            candidate_qualified_at=bars.index[0],
            policy=geometry_only_micro_research_policy(),
        )
        self.assertEqual(result.reason, "micro_pullback_volume_not_lower")

    def test_pullback_below_support_is_rejected(self):
        bars = self.strong_micro_pullback()
        available_at = bars.index[4]
        vwap = pd.Series([4.61], index=pd.DatetimeIndex([available_at]))
        ema9 = pd.Series([4.50], index=pd.DatetimeIndex([available_at]))
        result = evaluate_micro_pullback_plan(
            "ABC",
            bars,
            candidate_qualified_at=bars.index[0],
            policy=canonical_micro_setup_policy(),
            vwap_available=vwap,
            ema9_available=ema9,
        )
        self.assertEqual(result.reason, "micro_pullback_below_vwap")


if __name__ == "__main__":
    unittest.main()
