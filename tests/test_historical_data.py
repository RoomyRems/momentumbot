import unittest
from datetime import date

import pandas as pd

from momentumbot.historical_data import _daily_scan_basis


class HistoricalDataTests(unittest.TestCase):
    def _frame(self, rows):
        frame = pd.DataFrame(rows)
        frame["timestamp"] = pd.to_datetime(frame.pop("timestamp"), utc=True)
        return frame.set_index("timestamp")

    def test_daily_scan_basis_normalizes_same_day_reverse_split(self):
        raw = self._frame(
            [
                {
                    "timestamp": "2026-07-08T04:00:00Z",
                    "close": 0.4805,
                    "high": 0.4989,
                    "low": 0.4277,
                },
                {
                    "timestamp": "2026-07-09T04:00:00Z",
                    "close": 7.40,
                    "high": 7.6399,
                    "low": 6.80,
                },
            ]
        )
        split = self._frame(
            [
                {
                    "timestamp": "2026-07-08T04:00:00Z",
                    "close": 7.208,
                    "high": 7.484,
                    "low": 6.416,
                },
                {
                    "timestamp": "2026-07-09T04:00:00Z",
                    "close": 7.40,
                    "high": 7.6399,
                    "low": 6.80,
                },
            ]
        )

        basis = _daily_scan_basis(raw, split, date(2026, 7, 9))
        self.assertIsNotNone(basis)
        prior_close, high, low = basis

        self.assertAlmostEqual(prior_close, 7.208)
        self.assertAlmostEqual(high, 7.6399)
        self.assertAlmostEqual(low, 6.80)
        normalized_gain = (high / prior_close - 1.0) * 100.0
        naive_raw_gain = (high / 0.4805 - 1.0) * 100.0
        self.assertLess(normalized_gain, 10.0)
        self.assertGreater(naive_raw_gain, 1000.0)

    def test_daily_scan_basis_is_unchanged_without_split(self):
        raw = self._frame(
            [
                {
                    "timestamp": "2026-07-08T04:00:00Z",
                    "close": 5.00,
                    "high": 5.20,
                    "low": 4.80,
                },
                {
                    "timestamp": "2026-07-09T04:00:00Z",
                    "close": 6.00,
                    "high": 6.50,
                    "low": 5.50,
                },
            ]
        )

        basis = _daily_scan_basis(raw, raw, date(2026, 7, 9))
        self.assertIsNotNone(basis)
        prior_close, high, low = basis

        self.assertEqual(prior_close, 5.00)
        self.assertEqual(high, 6.50)
        self.assertEqual(low, 5.50)


if __name__ == "__main__":
    unittest.main()
