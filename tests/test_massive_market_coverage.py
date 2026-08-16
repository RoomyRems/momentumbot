from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from scripts.audit_massive_alpaca_market_coverage import (
    build_coverage_manifest,
    evaluate_ticker_coverage,
    group_security_records,
    summarize_coverage,
)


def _frame(timestamps: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {"close": [1.0] * len(timestamps)},
        index=pd.DatetimeIndex(timestamps, tz="UTC", name="timestamp"),
    )


class MassiveMarketCoverageTests(unittest.TestCase):
    def test_groups_colliding_security_records_into_one_market_query(self) -> None:
        rows = [
            {
                "ticker": "AAA",
                "active": True,
                "market": "stocks",
                "locale": "us",
                "primary_exchange": "XNAS",
                "type": "CS",
            },
            {
                "ticker": "AAA",
                "active": True,
                "market": "stocks",
                "locale": "us",
                "primary_exchange": "XNYS",
                "type": "PFD",
            },
        ]

        grouped = group_security_records(rows)

        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["security_record_count"], 2)
        self.assertEqual(grouped[0]["security_types"], ("CS", "PFD"))

    def test_requires_prior_and_target_in_both_adjustment_series(self) -> None:
        security = {
            "ticker": "AAA",
            "security_record_count": 1,
            "primary_exchanges": ("XNAS",),
            "security_types": ("CS",),
        }
        complete = _frame(["2025-04-02T14:00:00Z", "2025-04-03T14:00:00Z"])

        passing = evaluate_ticker_coverage(
            security,
            trading_date=date(2025, 4, 3),
            raw_frame=complete,
            split_frame=complete,
            invalid_symbol=False,
        )
        failing = evaluate_ticker_coverage(
            security,
            trading_date=date(2025, 4, 3),
            raw_frame=_frame(["2025-04-02T14:00:00Z"]),
            split_frame=complete,
            invalid_symbol=False,
        )

        self.assertTrue(passing["coverage_pass"])
        self.assertFalse(failing["coverage_pass"])
        self.assertFalse(failing["raw_target_session_present"])

    def test_summary_preserves_type_and_exchange_failure_rates(self) -> None:
        records = [
            {
                "ticker": "AAA",
                "security_types": "CS",
                "primary_exchanges": "XNAS",
                "invalid_symbol": False,
                "raw_prior_session_present": True,
                "raw_target_session_present": True,
                "split_prior_session_present": True,
                "split_target_session_present": True,
                "coverage_pass": True,
            },
            {
                "ticker": "BBB",
                "security_types": "ETF",
                "primary_exchanges": "ARCX",
                "invalid_symbol": True,
                "raw_prior_session_present": False,
                "raw_target_session_present": False,
                "split_prior_session_present": False,
                "split_target_session_present": False,
                "coverage_pass": False,
            },
        ]

        summary = summarize_coverage(records)

        self.assertEqual(summary["coverage_ratio"], 0.5)
        self.assertEqual(summary["by_security_type"]["CS"]["coverage_ratio"], 1.0)
        self.assertEqual(summary["by_security_type"]["ETF"]["coverage_ratio"], 0.0)
        self.assertEqual(summary["failure_reason_counts"]["invalid_symbol"], 1)

    def test_coverage_manifest_is_never_policy_promotable(self) -> None:
        manifest = build_coverage_manifest(
            trading_date=date(2025, 4, 3),
            census_manifest={
                "census_content_sha256": "content",
                "membership_sha256": "membership",
            },
            summary={
                "unique_ticker_count": 1,
                "coverage_pass_count": 1,
                "coverage_fail_count": 0,
                "coverage_ratio": 1.0,
            },
            started_at_utc="2026-08-16T18:00:00+00:00",
            completed_at_utc="2026-08-16T18:01:00+00:00",
        )

        self.assertTrue(
            manifest["eligibility"]["all_census_tickers_market_data_covered"]
        )
        self.assertFalse(manifest["eligibility"]["universe_complete"])
        self.assertFalse(manifest["eligibility"]["policy_promotion_eligible"])


if __name__ == "__main__":
    unittest.main()
