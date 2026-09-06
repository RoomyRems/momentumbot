from __future__ import annotations

import unittest

from momentumbot.indicators import macd, session_vwap, upper_wick_fraction
from tests.helpers import frame, strong_pullback_bars


class IndicatorTests(unittest.TestCase):
    def test_vwap_is_causal(self):
        bars = frame([(1, 2, 1, 2, 100), (2, 3, 2, 3, 100), (3, 4, 3, 4, 100)])
        before = session_vwap(bars.iloc[:2]).iloc[-1]
        after = session_vwap(bars).iloc[1]
        self.assertAlmostEqual(before, after)

    def test_upper_wick_fraction(self):
        bars = frame([(10, 12, 9, 11, 100)])
        self.assertAlmostEqual(upper_wick_fraction(bars.iloc[0]), 1 / 3)

    def test_standard_macd_is_positive_on_strong_rise(self):
        values = macd(strong_pullback_bars()["close"])
        self.assertGreater(values.iloc[-1]["macd"], values.iloc[-1]["signal"])


if __name__ == "__main__":
    unittest.main()
