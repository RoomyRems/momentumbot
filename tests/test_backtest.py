from __future__ import annotations

import unittest
from dataclasses import replace

import pandas as pd

from momentumbot.backtest import Backtester, NewsEvent
from momentumbot.models import RiskPolicy, SymbolContext, current_general_2026
from tests.helpers import frame, strong_pullback_bars


class BacktestTests(unittest.TestCase):
    def setUp(self):
        self.profile = current_general_2026()
        self.risk = RiskPolicy(
            name="test",
            risk_per_trade_fraction=0.0025,
            max_daily_loss_fraction=0.10,
            giveback_fraction=0.50,
            max_position_fraction_of_equity=1.0,
            slippage_bps=0,
        )
        self.context = SymbolContext("TEST", 4.0, 200_000, 5_000_000)
        self.news = [
            NewsEvent("TEST", pd.Timestamp("2026-08-12 11:00:00+00:00").to_pydatetime(), "n1")
        ]

    def _bars_with_trigger_and_exit(self):
        bars = strong_pullback_bars()
        continuation = frame(
            [
                (6.08, 6.30, 6.07, 6.25, 450_000),
                (6.25, 6.42, 6.22, 6.38, 500_000),
                (6.38, 6.40, 6.20, 6.22, 400_000),
                (6.22, 6.25, 6.10, 6.15, 300_000),
            ],
            start=str(bars.index[-1] + pd.Timedelta(minutes=1)),
        )
        return pd.concat([bars, continuation])

    def test_entry_occurs_after_plan_bar(self):
        bars = self._bars_with_trigger_and_exit()
        result = Backtester(self.profile, self.risk).run_day(
            {"TEST": bars}, {"TEST": self.context}, self.news
        )
        self.assertTrue(result.trades)
        self.assertGreater(
            result.trades[0].entry_time,
            strong_pullback_bars().index[-1].to_pydatetime(),
        )

    def test_same_bar_trigger_and_stop_assumes_adverse_sequence(self):
        bars = strong_pullback_bars()
        continuation = frame(
            [(6.08, 6.25, 5.95, 6.20, 500_000)],
            start=str(bars.index[-1] + pd.Timedelta(minutes=1)),
        )
        result = Backtester(self.profile, self.risk).run_day(
            {"TEST": pd.concat([bars, continuation])}, {"TEST": self.context}, self.news
        )
        self.assertTrue(result.trades)
        self.assertEqual(result.trades[0].exit_reason.value, "stop")
        self.assertLess(result.trades[0].realized_r, 0)

    def test_bad_gap_fill_rejected_when_two_r_no_longer_exists(self):
        bars = strong_pullback_bars()
        continuation = frame(
            [(6.45, 6.55, 6.40, 6.50, 500_000)],
            start=str(bars.index[-1] + pd.Timedelta(minutes=1)),
        )
        result = Backtester(self.profile, self.risk).run_day(
            {"TEST": pd.concat([bars, continuation])}, {"TEST": self.context}, self.news
        )
        self.assertEqual(len(result.trades), 0)
        self.assertGreaterEqual(result.rejected_for_fill_slippage, 1)

    def test_future_news_cannot_qualify_earlier_bars(self):
        bars = self._bars_with_trigger_and_exit()
        future_news = [
            NewsEvent("TEST", (bars.index[-1] + pd.Timedelta(hours=1)).to_pydatetime(), "future")
        ]
        profile = replace(self.profile, allow_obvious_no_news_exception=False)
        result = Backtester(profile, self.risk).run_day(
            {"TEST": bars}, {"TEST": self.context}, future_news
        )
        self.assertEqual(result.candidate_events, 0)
        self.assertEqual(len(result.trades), 0)


if __name__ == "__main__":
    unittest.main()
