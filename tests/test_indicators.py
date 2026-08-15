from __future__ import annotations

import unittest

import pandas as pd

from momentumbot.indicators import (
    completed_bar_support_series,
    macd,
    session_vwap,
    upper_wick_fraction,
)
from tests.helpers import frame, strong_pullback_bars


class IndicatorTests(unittest.TestCase):
    def test_vwap_is_causal(self):
        bars = frame([(1, 2, 1, 2, 100), (2, 3, 2, 3, 100), (3, 4, 3, 4, 100)])
        before = session_vwap(bars.iloc[:2]).iloc[-1]
        after = session_vwap(bars).iloc[1]
        self.assertAlmostEqual(before, after)

    def test_completed_bar_support_is_timestamped_when_bar_closes(self):
        rows = []
        price = 4.0
        for _ in range(10):
            rows.append((price, price + 0.10, price - 0.05, price + 0.05, 100))
            price += 0.05
        bars = frame(rows, start="2026-08-12 11:00:00+00:00")
        support = completed_bar_support_series(bars, ema_span=9, bar_duration="1min")

        self.assertEqual(support.index[0], pd.Timestamp("2026-08-12 11:01:00+00:00"))
        self.assertEqual(support.index.name, "available_at")
        self.assertEqual(
            support.loc[: pd.Timestamp("2026-08-12 11:00:59.999999+00:00")].shape[0],
            0,
        )
        self.assertFalse(pd.isna(support.loc[pd.Timestamp("2026-08-12 11:01:00+00:00"), "vwap"]))
        self.assertTrue(
            support.loc[: pd.Timestamp("2026-08-12 11:08:59.999999+00:00"), "ema"]
            .dropna()
            .empty
        )
        self.assertFalse(pd.isna(support.loc[pd.Timestamp("2026-08-12 11:09:00+00:00"), "ema"]))

    def test_completed_bar_support_requires_timezone_aware_bars(self):
        bars = frame([(1, 2, 1, 2, 100)]).copy()
        bars.index = bars.index.tz_localize(None)
        with self.assertRaises(ValueError):
            completed_bar_support_series(bars)

    def test_upper_wick_fraction(self):
        bars = frame([(10, 12, 9, 11, 100)])
        self.assertAlmostEqual(upper_wick_fraction(bars.iloc[0]), 1 / 3)

    def test_standard_macd_is_positive_on_strong_rise(self):
        values = macd(strong_pullback_bars()["close"])
        self.assertGreater(values.iloc[-1]["macd"], values.iloc[-1]["signal"])


if __name__ == "__main__":
    unittest.main()
