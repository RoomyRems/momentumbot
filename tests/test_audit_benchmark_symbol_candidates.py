from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from scripts.audit_benchmark_symbol_candidates import (
    PricePathCriteria,
    build_candidate_records,
)


def _frame(rows: list[tuple[str, float, float, float, float, int]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [row[1] for row in rows],
            "high": [row[2] for row in rows],
            "low": [row[3] for row in rows],
            "close": [row[4] for row in rows],
            "volume": [row[5] for row in rows],
        },
        index=pd.DatetimeIndex([row[0] for row in rows], tz="UTC", name="timestamp"),
    )


class BenchmarkSymbolCandidateAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.criteria = PricePathCriteria(
            trading_date=date(2025, 9, 9),
            rejection_level=5.20,
            rejection_tolerance=0.20,
            later_high=8.00,
            later_high_tolerance=1.25,
            coarse_max_high=20.0,
            minimum_volume=100_000,
        )

    def test_ranks_ordered_rejection_then_later_high_first(self) -> None:
        bars = {
            "MATCH": _frame(
                [
                    ("2025-09-08T14:00:00Z", 3.9, 4.1, 3.8, 4.0, 50_000),
                    ("2025-09-09T13:30:00Z", 4.9, 5.22, 4.85, 5.02, 80_000),
                    ("2025-09-09T13:31:00Z", 5.0, 5.08, 4.95, 5.04, 50_000),
                    ("2025-09-09T14:00:00Z", 6.8, 8.05, 6.7, 7.9, 200_000),
                ]
            ),
            "NOSEQ": _frame(
                [
                    ("2025-09-08T14:00:00Z", 3.9, 4.1, 3.8, 4.0, 50_000),
                    ("2025-09-09T13:30:00Z", 7.0, 8.1, 6.8, 7.8, 200_000),
                    ("2025-09-09T14:00:00Z", 5.0, 5.21, 4.9, 5.0, 100_000),
                ]
            ),
        }
        assets = [
            {"symbol": "MATCH", "name": "Matching Corp"},
            {"symbol": "NOSEQ", "name": "Wrong Sequence Corp"},
        ]

        records = build_candidate_records(assets, bars, self.criteria)

        self.assertEqual([record["symbol"] for record in records], ["MATCH", "NOSEQ"])
        self.assertTrue(records[0]["ordered_rejection_then_later_high"])
        self.assertFalse(records[1]["ordered_rejection_then_later_high"])
        self.assertEqual(records[0]["previous_regular_close"], 4.0)

    def test_requires_timezone_aware_bars(self) -> None:
        frame = pd.DataFrame(
            {
                "open": [5.0],
                "high": [8.0],
                "low": [4.8],
                "close": [7.5],
                "volume": [200_000],
            },
            index=pd.DatetimeIndex(["2025-09-09T13:30:00"]),
        )

        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            build_candidate_records([{"symbol": "BAD"}], {"BAD": frame}, self.criteria)


if __name__ == "__main__":
    unittest.main()
