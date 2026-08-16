import unittest
from datetime import date

import pandas as pd

from momentumbot.historical_data import (
    _daily_scan_basis,
    asset_master_fingerprint,
    asset_master_status_counts,
    normalize_asset_master,
)


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

    def test_asset_master_fingerprint_is_order_independent(self):
        first = [
            {
                "id": "2",
                "class": "us_equity",
                "exchange": "nyse",
                "symbol": "BBB",
                "name": "Beta",
                "status": "inactive",
                "tradable": False,
                "attributes": ["z", "a"],
            },
            {
                "id": "1",
                "class": "us_equity",
                "exchange": "nasdaq",
                "symbol": "AAA",
                "name": "Alpha",
                "status": "active",
                "tradable": True,
                "attributes": [],
            },
        ]
        second = [dict(first[1]), dict(first[0], attributes=["a", "z"])]

        self.assertEqual(asset_master_fingerprint(first), asset_master_fingerprint(second))
        self.assertEqual(
            [row["symbol"] for row in normalize_asset_master(first)],
            ["AAA", "BBB"],
        )

    def test_asset_master_status_counts_preserve_inactive_members(self):
        rows = [
            {"symbol": "AAA", "status": "active"},
            {"symbol": "BBB", "status": "inactive"},
            {"symbol": "CCC", "status": "inactive"},
        ]
        self.assertEqual(
            asset_master_status_counts(rows),
            {"active": 1, "inactive": 2},
        )


if __name__ == "__main__":
    unittest.main()
