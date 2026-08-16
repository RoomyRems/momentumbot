from __future__ import annotations

import unittest

from momentumbot.historical_universe import classify_ticker_group
from scripts.build_massive_provisional_universe import (
    build_date_manifest,
    summarize_decisions,
)


def _row(ticker: str, name: str, *, security_type: str = "CS") -> dict[str, object]:
    return {
        "ticker": ticker,
        "active": True,
        "market": "stocks",
        "locale": "us",
        "primary_exchange": "XNAS",
        "type": security_type,
        "name": name,
        "cik": "1",
        "composite_figi": f"FIGI-{ticker}",
    }


def _coverage(passing: bool = True) -> dict[str, object]:
    return {
        "invalid_symbol": False,
        "raw_prior_session_present": True,
        "raw_target_session_present": passing,
        "split_prior_session_present": True,
        "split_target_session_present": passing,
        "coverage_pass": passing,
    }


class BuildMassiveProvisionalUniverseTests(unittest.TestCase):
    def test_summary_fingerprints_included_membership_and_reasons(self) -> None:
        decisions = [
            classify_ticker_group(
                [_row("AAA", "AAA Incorporated Common Stock")],
                _coverage(),
            ),
            classify_ticker_group(
                [_row("BBB", "BBB 7.50% Senior Notes due 2030")],
                _coverage(),
            ),
            classify_ticker_group(
                [_row("CCC", "CCC Incorporated Common Stock")],
                _coverage(False),
            ),
        ]

        summary = summarize_decisions(decisions)

        self.assertEqual(summary["decision_count"], 3)
        self.assertEqual(summary["included_ticker_count"], 1)
        self.assertEqual(summary["excluded_ticker_count"], 2)
        self.assertEqual(
            summary["reason_counts"]["instrument_metadata_conflict"],
            1,
        )
        self.assertEqual(summary["reason_counts"]["missing_target_session"], 1)
        self.assertEqual(len(summary["decisions_sha256"]), 64)
        self.assertEqual(len(summary["included_membership_sha256"]), 64)

    def test_date_manifest_is_complete_relative_only_and_never_promotable(self) -> None:
        summary = {
            "decision_count": 2,
            "included_ticker_count": 1,
            "excluded_ticker_count": 1,
            "included_membership_sha256": "included",
        }
        manifest = build_date_manifest(
            trading_date="2025-04-03",
            census_manifest={
                "census_content_sha256": "content",
                "membership_sha256": "membership",
                "census_summary": {"unique_ticker_count": 2},
            },
            metadata_manifest={"summary": {"records_sha256": "metadata"}},
            coverage_manifest={"summary": {"records_sha256": "coverage"}},
            summary=summary,
        )

        self.assertTrue(manifest["eligibility"]["complete_relative_to_census"])
        self.assertTrue(
            manifest["eligibility"]["point_in_time_membership_translated"]
        )
        self.assertFalse(manifest["eligibility"]["universe_complete"])
        self.assertFalse(manifest["eligibility"]["full_walk_forward_eligible"])
        self.assertFalse(manifest["eligibility"]["policy_promotion_eligible"])


if __name__ == "__main__":
    unittest.main()
