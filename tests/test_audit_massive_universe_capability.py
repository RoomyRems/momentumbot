from __future__ import annotations

import json
import unittest

from scripts.audit_massive_universe_capability import assess_capability, summarize_response


class MassiveUniverseCapabilityAuditTests(unittest.TestCase):
    def test_summary_exposes_counts_and_schema_without_identifiers(self) -> None:
        response = {
            "ok": True,
            "status": 200,
            "payload": {
                "count": 2,
                "next_url": "https://example.invalid/SECRET_PAGE_TOKEN",
                "request_id": "SECRET_REQUEST_ID",
                "results": [
                    {
                        "ticker": "DO_NOT_PERSIST_ONE",
                        "name": "Private Example One",
                        "active": True,
                        "market": "stocks",
                        "locale": "us",
                        "primary_exchange": "SECRET_EXCHANGE_A",
                        "type": "CS",
                        "last_updated_utc": "2025-04-03T12:00:00Z",
                    },
                    {
                        "ticker": "DO_NOT_PERSIST_TWO",
                        "name": "Private Example Two",
                        "active": True,
                        "market": "stocks",
                        "locale": "us",
                        "primary_exchange": "SECRET_EXCHANGE_B",
                        "type": "CS",
                        "last_updated_utc": "2025-04-03T13:00:00Z",
                    },
                ],
            },
        }

        summary = summarize_response(response, "2025-04-03")
        rendered = json.dumps(summary, sort_keys=True)

        self.assertEqual(summary["result_count"], 2)
        self.assertEqual(summary["active_true_count"], 2)
        self.assertTrue(summary["next_page_present"])
        self.assertNotIn("DO_NOT_PERSIST", rendered)
        self.assertNotIn("Private Example", rendered)
        self.assertNotIn("SECRET_EXCHANGE", rendered)
        self.assertNotIn("SECRET_PAGE_TOKEN", rendered)
        self.assertNotIn("SECRET_REQUEST_ID", rendered)

    def test_error_body_is_not_propagated(self) -> None:
        summary = summarize_response(
            {
                "ok": False,
                "status": 401,
                "error_kind": "http_error",
                "error": "do not print provider body or API key",
            },
            "2025-04-03",
        )

        self.assertNotIn("do not print", json.dumps(summary, sort_keys=True))
        self.assertEqual(summary["error_kind"], "http_error")

    def test_successful_samples_authorize_only_paginated_prototype(self) -> None:
        snapshots = {}
        for target_date in ("2025-04-03", "2026-07-09"):
            snapshots[target_date] = {
                "ok": True,
                "result_count": 10,
                "result_fields": ["ticker", "active", "primary_exchange", "type"],
                "active_true_count": 10,
                "active_false_count": 0,
            }

        assessment = assess_capability(snapshots)

        self.assertTrue(assessment["eligible_for_paginated_fetch_prototype"])
        self.assertFalse(assessment["point_in_time_universe_complete"])
        self.assertFalse(assessment["full_walk_forward_eligible"])
        self.assertFalse(assessment["policy_promotion_eligible"])

    def test_missing_exchange_field_blocks_prototype(self) -> None:
        assessment = assess_capability(
            {
                "2025-04-03": {
                    "ok": True,
                    "result_count": 10,
                    "result_fields": ["ticker", "active", "type"],
                    "active_true_count": 10,
                    "active_false_count": 0,
                }
            }
        )

        self.assertFalse(assessment["eligible_for_paginated_fetch_prototype"])


if __name__ == "__main__":
    unittest.main()
