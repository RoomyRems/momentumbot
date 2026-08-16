from __future__ import annotations

import json
import unittest

from scripts.audit_fmp_universe_capability import assess_capability, summarize_response


class FmpUniverseCapabilityAuditTests(unittest.TestCase):
    def test_summary_exposes_schema_and_ranges_without_raw_rows(self) -> None:
        response = {
            "ok": True,
            "status": 200,
            "payload": [
                {
                    "symbol": "DO_NOT_PERSIST_ONE",
                    "companyName": "Private Example One",
                    "exchange": "SECRET_EXCHANGE_A",
                    "ipoDate": "2020-01-02",
                    "delistedDate": "2025-04-03",
                },
                {
                    "symbol": "DO_NOT_PERSIST_TWO",
                    "companyName": "Private Example Two",
                    "exchange": "SECRET_EXCHANGE_B",
                    "ipoDate": "2019-03-04",
                    "delistedDate": "2026-05-06",
                },
            ],
        }

        summary = summarize_response(response)
        rendered = json.dumps(summary, sort_keys=True)

        self.assertEqual(summary["row_count"], 2)
        self.assertEqual(summary["date_fields"]["ipoDate"]["minimum"], "2019-03-04")
        self.assertEqual(summary["date_fields"]["delistedDate"]["maximum"], "2026-05-06")
        self.assertEqual(summary["exchange_fields"]["exchange"]["distinct_count"], 2)
        self.assertNotIn("DO_NOT_PERSIST", rendered)
        self.assertNotIn("Private Example", rendered)
        self.assertNotIn("SECRET_EXCHANGE", rendered)

    def test_error_body_is_not_propagated(self) -> None:
        summary = summarize_response(
            {
                "ok": False,
                "status": 403,
                "error_kind": "http_error",
                "error": "do not print provider body or API key",
            }
        )

        self.assertEqual(
            summary,
            {"ok": False, "status": 403, "error_kind": "http_error"},
        )

    def test_schema_probe_never_grants_historical_completeness(self) -> None:
        datasets = {
            "current_actively_trading": {
                "ok": True,
                "row_count": 5,
                "fields": ["symbol", "exchange", "ipoDate"],
            },
            "delisted_page_0": {
                "ok": True,
                "row_count": 5,
                "fields": ["symbol", "exchange", "ipoDate", "delistedDate"],
            },
            "symbol_changes": {
                "ok": True,
                "row_count": 5,
                "fields": ["oldSymbol", "newSymbol", "date"],
            },
        }

        assessment = assess_capability(datasets)

        self.assertTrue(assessment["eligible_for_reconstruction_prototype"])
        self.assertTrue(assessment["coverage_audit_required"])
        self.assertFalse(assessment["point_in_time_universe_complete"])
        self.assertFalse(assessment["full_walk_forward_eligible"])
        self.assertFalse(assessment["policy_promotion_eligible"])

    def test_missing_active_listing_date_blocks_prototype(self) -> None:
        datasets = {
            "current_actively_trading": {
                "ok": True,
                "row_count": 5,
                "fields": ["symbol", "exchange"],
            },
            "delisted_page_0": {
                "ok": True,
                "row_count": 5,
                "fields": ["symbol", "exchange", "ipoDate", "delistedDate"],
            },
            "symbol_changes": {
                "ok": True,
                "row_count": 5,
                "fields": ["oldSymbol", "newSymbol", "date"],
            },
        }

        assessment = assess_capability(datasets)

        self.assertFalse(assessment["checks"]["current_listing_date_observed"])
        self.assertFalse(assessment["eligible_for_reconstruction_prototype"])


if __name__ == "__main__":
    unittest.main()
