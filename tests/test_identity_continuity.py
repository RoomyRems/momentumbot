from __future__ import annotations

import unittest

from momentumbot.identity_continuity import build_cross_date_identity_bridge


def _row(ticker: str, *, figi: str = "", cik: str = "") -> dict[str, object]:
    return {
        "ticker": ticker,
        "included": True,
        "selected_cik": cik,
        "selected_composite_figi": figi,
        "selected_primary_exchange": "XNAS",
        "selected_security_type": "CS",
    }


class IdentityContinuityTests(unittest.TestCase):
    def test_figi_primary_cik_fallback_and_symbol_reuse_are_explicit(self) -> None:
        earlier = [
            _row("AAA", figi="FIGI-1", cik="1"),
            _row("BBB", figi="FIGI-2", cik="2"),
            _row("OLD", cik="3"),
        ]
        later = [
            _row("BBB", figi="FIGI-1", cik="1"),
            _row("CCC", figi="FIGI-2", cik="2"),
            _row("NEW", cik="3"),
        ]

        result = build_cross_date_identity_bridge(
            earlier,
            later,
            earlier_date="2025-04-03",
            later_date="2026-07-09",
        )

        self.assertEqual(result["summary"]["cross_date_transition_count"], 3)
        self.assertEqual(result["summary"]["changed_ticker_exact_figi_count"], 2)
        self.assertEqual(
            result["summary"]["changed_ticker_unique_cik_fallback_count"], 1
        )
        by_identifier = {row["identifier"]: row for row in result["transitions"]}
        self.assertTrue(by_identifier["FIGI-1"]["symbol_reuse_involved"])
        self.assertEqual(by_identifier["3"]["identifier_kind"], "unique_cik_fallback")

    def test_different_nonblank_figis_are_not_collapsed_by_cik(self) -> None:
        result = build_cross_date_identity_bridge(
            [_row("SAME", figi="OLD-FIGI", cik="1")],
            [_row("SAME", figi="NEW-FIGI", cik="1")],
            earlier_date="2025-04-03",
            later_date="2026-07-09",
        )

        self.assertEqual(result["summary"]["cross_date_transition_count"], 0)
        self.assertEqual(result["summary"]["same_ticker_different_figi_count"], 1)

    def test_nonunique_cik_without_figi_is_quarantined(self) -> None:
        result = build_cross_date_identity_bridge(
            [
                _row("CLASSA", cik="1"),
                _row("CLASSB", cik="1"),
                _row("NOID"),
            ],
            [
                _row("CLASSA", cik="1"),
                _row("CLASSB", cik="1"),
                _row("NOID"),
            ],
            earlier_date="2025-04-03",
            later_date="2026-07-09",
        )

        status = result["date_identity_status"]["2025-04-03"]
        self.assertEqual(len(status["accepted"]), 0)
        self.assertEqual(len(status["quarantined"]), 3)
        reasons = {row["reason"] for row in status["quarantined"]}
        self.assertEqual(
            reasons,
            {"nonunique_cik_without_composite_figi", "missing_stable_identifier"},
        )

    def test_bridge_fingerprint_is_input_order_independent(self) -> None:
        earlier = [
            _row("AAA", figi="FIGI-1", cik="1"),
            _row("BBB", figi="FIGI-2", cik="2"),
        ]
        later = [
            _row("CCC", figi="FIGI-1", cik="1"),
            _row("DDD", figi="FIGI-2", cik="2"),
        ]
        first = build_cross_date_identity_bridge(
            earlier,
            later,
            earlier_date="2025-04-03",
            later_date="2026-07-09",
        )
        second = build_cross_date_identity_bridge(
            list(reversed(earlier)),
            list(reversed(later)),
            earlier_date="2025-04-03",
            later_date="2026-07-09",
        )

        self.assertEqual(first["bridge_sha256"], second["bridge_sha256"])


if __name__ == "__main__":
    unittest.main()

