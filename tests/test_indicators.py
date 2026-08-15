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
        self.assertFalse(
            pd.isna(support.loc[pd.Timestamp("2026-08-12 11:01:00+00:00"), "vwap"])
        )
        self.assertTrue(
            support.loc[: pd.Timestamp("2026-08-12 11:08:59.999999+00:00"), "ema"]
            .dropna()
            .empty
        )
        self.assertFalse(
            pd.isna(support.loc[pd.Timestamp("2026-08-12 11:09:00+00:00"), "ema"])
        )

    def test_prior_bars_warm_ema_without_changing_session_vwap(self):
        warmup_rows = []
        price = 8.0
        for _ in range(8):
            warmup_rows.append((price, price + 0.10, price - 0.05, price + 0.05, 100))
            price += 0.05
        warmup = frame(warmup_rows, start="2026-08-11 19:52:00+00:00")
        session = frame(
            [(4.00, 4.10, 3.95, 4.05, 200), (4.05, 4.20, 4.00, 4.15, 300)],
            start="2026-08-12 08:00:00+00:00",
        )

        without_warmup = completed_bar_support_series(session, ema_span=9)
        with_warmup = completed_bar_support_series(
            session,
            ema_span=9,
            ema_warmup=warmup,
        )

        self.assertTrue(without_warmup["ema"].dropna().empty)
        self.assertFalse(pd.isna(with_warmup.iloc[0]["ema"]))
        self.assertAlmostEqual(with_warmup.iloc[0]["vwap"], without_warmup.iloc[0]["vwap"])
        self.assertAlmostEqual(with_warmup.iloc[1]["vwap"], without_warmup.iloc[1]["vwap"])

    def test_ema_warmup_uses_only_bars_before_session_start(self):
        warmup = frame(
            [
                (8.0, 8.1, 7.9, 8.05, 100),
                (8.1, 8.2, 8.0, 8.15, 100),
                (8.2, 8.3, 8.1, 8.25, 100),
                (8.3, 8.4, 8.2, 8.35, 100),
                (8.4, 8.5, 8.3, 8.45, 100),
                (8.5, 8.6, 8.4, 8.55, 100),
                (8.6, 8.7, 8.5, 8.65, 100),
                (8.7, 8.8, 8.6, 8.75, 100),
                (20.0, 20.1, 19.9, 20.05, 100),
            ],
            start="2026-08-12 07:52:00+00:00",
        )
        session = frame(
            [(4.0, 4.1, 3.9, 4.05, 200)],
            start="2026-08-12 08:00:00+00:00",
        )
        support = completed_bar_support_series(session, ema_span=9, ema_warmup=warmup)
        expected_prior_only = completed_bar_support_series(
            session,
            ema_span=9,
            ema_warmup=warmup.loc[warmup.index < session.index[0]],
        )
        self.assertAlmostEqual(support.iloc[0]["ema"], expected_prior_only.iloc[0]["ema"])

    def test_completed_bar_support_requires_timezone_aware_bars(self):
        bars = frame([(1, 2, 1, 2, 100)]).copy()
        bars.index = bars.index.tz_localize(None)
        with self.assertRaises(ValueError):
            completed_bar_support_series(bars)

    def test_ema_warmup_requires_timezone_aware_bars(self):
        session = frame([(4.0, 4.1, 3.9, 4.05, 100)])
        warmup = frame([(3.0, 3.1, 2.9, 3.05, 100)]).copy()
        warmup.index = warmup.index.tz_localize(None)
        with self.assertRaises(ValueError):
            completed_bar_support_series(session, ema_warmup=warmup)

    def test_upper_wick_fraction(self):
        bars = frame([(10, 12, 9, 11, 100)])
        self.assertAlmostEqual(upper_wick_fraction(bars.iloc[0]), 1 / 3)

    def test_standard_macd_is_positive_on_strong_rise(self):
        values = macd(strong_pullback_bars()["close"])
        self.assertGreater(values.iloc[-1]["macd"], values.iloc[-1]["signal"])


if __name__ == "__main__":
    unittest.main()
