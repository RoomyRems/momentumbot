from __future__ import annotations

import unittest

from momentumbot.providers.massive import MassiveTickerCensus, MassiveTickerPage
from scripts.build_massive_historical_census import (
    build_date_manifest,
    build_reconciliation,
    summarize_census,
)


def _massive(ticker: str, *, exchange: str = "XNAS", security_type: str = "CS") -> dict:
    return {
        "ticker": ticker,
        "active": True,
        "market": "stocks",
        "locale": "us",
        "primary_exchange": exchange,
        "type": security_type,
        "cik": "1",
        "composite_figi": f"FIGI-{ticker}",
    }


def _alpaca(symbol: str, *, status: str = "active") -> dict:
    return {
        "id": f"asset-{symbol}",
        "class": "us_equity",
        "exchange": "NASDAQ",
        "symbol": symbol,
        "name": f"{symbol} Corp",
        "status": status,
        "tradable": True,
        "attributes": [],
    }


class MassiveHistoricalCensusBuilderTests(unittest.TestCase):
    def test_summary_preserves_missing_field_counts(self) -> None:
        summary = summarize_census(
            [_massive("AAA"), _massive("BBB", exchange="", security_type="")]
        )

        self.assertEqual(summary["row_count"], 2)
        self.assertEqual(summary["missing_primary_exchange_count"], 1)
        self.assertEqual(summary["missing_security_type_count"], 1)
        self.assertTrue(summary["all_rows_active"])
        self.assertTrue(summary["all_rows_us_stocks"])

    def test_summary_distinguishes_ticker_collision_from_identity_duplicate(self) -> None:
        common = _massive("AAA")
        preferred = _massive("AAA", exchange="XNYS", security_type="PFD")
        preferred["composite_figi"] = "FIGI-PREFERRED"

        summary = summarize_census([common, preferred])

        self.assertEqual(summary["duplicate_ticker_count"], 1)
        self.assertEqual(summary["ticker_collision_group_count"], 1)
        self.assertEqual(summary["duplicate_membership_identity_count"], 0)

    def test_reconciliation_is_explicitly_current_only(self) -> None:
        records, summary = build_reconciliation(
            [_massive("AAA"), _massive("PAST")],
            [_alpaca("AAA"), _alpaca("CURRENT")],
        )

        self.assertEqual(summary["overlap_count"], 1)
        self.assertEqual(summary["massive_not_in_alpaca_current_count"], 1)
        self.assertEqual(summary["alpaca_current_not_in_massive_asof_count"], 1)
        self.assertFalse(summary["alpaca_comparison_is_point_in_time"])
        self.assertEqual([row["ticker"] for row in records], ["AAA", "CURRENT", "PAST"])

    def test_completed_pagination_still_cannot_promote_universe(self) -> None:
        rows = (_massive("AAA"), _massive("BBB"))
        census = MassiveTickerCensus(
            as_of="2025-04-03",
            query={"date": "2025-04-03", "active": "true"},
            pages=(
                MassiveTickerPage(
                    page_number=1,
                    row_count=2,
                    first_ticker="AAA",
                    last_ticker="BBB",
                    next_page_present=False,
                ),
            ),
            rows=rows,
        )
        manifest = build_date_manifest(
            census,
            census_summary=summarize_census(rows),
            reconciliation_summary={"alpaca_comparison_is_point_in_time": False},
            retrieved_at_utc="2026-08-16T18:00:00+00:00",
            completed_at_utc="2026-08-16T18:01:00+00:00",
            credential_name="MASSIVE_API_KEY",
        )

        self.assertTrue(manifest["fetch_complete"])
        self.assertEqual(manifest["page_order_regression_count"], 0)
        self.assertTrue(manifest["eligibility"]["point_in_time_membership_candidate"])
        self.assertFalse(manifest["eligibility"]["universe_complete"])
        self.assertFalse(manifest["eligibility"]["full_walk_forward_eligible"])
        self.assertFalse(manifest["eligibility"]["policy_promotion_eligible"])


if __name__ == "__main__":
    unittest.main()
