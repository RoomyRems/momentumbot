from __future__ import annotations

import unittest
import urllib.error
from datetime import date, datetime, timezone

from scripts.build_causal_float_enrichment import (
    _basis_query_window,
    _sec_call,
    _selected_evidence_status,
    _validate_sec_entity,
)


class BuildCausalFloatEnrichmentTests(unittest.TestCase):
    def test_recent_basis_window_cannot_query_after_trading_date(self) -> None:
        start, end = _basis_query_window(
            [date(2026, 8, 6)],
            trading_date=date(2026, 8, 6),
        )

        self.assertEqual(start, datetime(2026, 7, 23, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 8, 7, tzinfo=timezone.utc))

    def test_old_basis_window_preserves_calendar_gap_buffer(self) -> None:
        start, end = _basis_query_window(
            [date(2026, 6, 1)],
            trading_date=date(2026, 8, 6),
        )

        self.assertEqual(start, datetime(2026, 5, 18, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 6, 16, tzinfo=timezone.utc))

    def test_future_basis_date_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "causal trading date"):
            _basis_query_window(
                [date(2026, 8, 7)],
                trading_date=date(2026, 8, 6),
            )

    def test_sec_call_retries_transient_failure(self) -> None:
        calls = 0

        def request() -> dict[str, object]:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError("temporary")
            return {"ok": True}

        payload, status, error = _sec_call(
            request,
            attempts=2,
            retry_delay_seconds=0,
        )

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(status, "success")
        self.assertIsNone(error)
        self.assertEqual(calls, 2)

    def test_sec_call_treats_not_found_as_fail_closed_data_absence(self) -> None:
        def request() -> dict[str, object]:
            raise urllib.error.HTTPError(
                "https://data.sec.gov/example",
                404,
                "not found",
                hdrs=None,
                fp=None,
            )

        payload, status, error = _sec_call(
            request,
            attempts=3,
            retry_delay_seconds=0,
        )

        self.assertIsNone(payload)
        self.assertEqual(status, "not_found")
        self.assertIsNone(error)

    def test_sec_call_preserves_exhausted_provider_error(self) -> None:
        payload, status, error = _sec_call(
            lambda: (_ for _ in ()).throw(ConnectionError("offline")),
            attempts=2,
            retry_delay_seconds=0,
        )

        self.assertIsNone(payload)
        self.assertEqual(status, "provider_error")
        self.assertEqual(error, "ConnectionError")

    def test_evidence_status_does_not_overclaim_acceptance_precision(self) -> None:
        selected = {
            "public_float": {
                "accession": "annual",
            },
            "anchor_outstanding": None,
            "current_outstanding": {
                "accession": "quarterly",
            },
        }
        acceptance = {
            "annual": datetime(2025, 3, 1, tzinfo=timezone.utc),
        }

        status = _selected_evidence_status(
            selected,
            submissions_available=True,
            acceptance_times=acceptance,
        )

        self.assertEqual(
            status,
            "success_selected_evidence_includes_conservative_fallback",
        )

    def test_sec_payload_must_match_frozen_candidate_cik(self) -> None:
        _validate_sec_entity(
            {"cik": 1},
            expected_cik="0000000001",
            label="companyfacts",
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            _validate_sec_entity(
                {"cik": 2},
                expected_cik="0000000001",
                label="companyfacts",
            )


if __name__ == "__main__":
    unittest.main()
