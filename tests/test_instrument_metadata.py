from __future__ import annotations

import unittest

from momentumbot.instrument_metadata import (
    InstrumentMetadataStatus,
    audit_instrument_metadata,
    instrument_metadata_audit_manifest,
)
from scripts.audit_massive_instrument_metadata import (
    audit_records,
    build_date_manifest,
    summarize_records,
)


def _row(
    ticker: str,
    name: str,
    *,
    security_type: str = "CS",
) -> dict[str, object]:
    return {
        "ticker": ticker,
        "active": True,
        "market": "stocks",
        "locale": "us",
        "primary_exchange": "XNAS",
        "type": security_type,
        "name": name,
    }


class InstrumentMetadataTests(unittest.TestCase):
    def test_explicit_preferred_debt_and_rights_fail_closed(self) -> None:
        cases = [
            (
                _row(
                    "PREF",
                    "Issuer Depositary Shares representing Preferred Stock",
                ),
                "explicit_preferred",
            ),
            (_row("DEBT", "Issuer 8.25% Senior Notes due 2030"), "explicit_debt"),
            (
                _row("RGHT", "Acquisition Corporation Rights that convert"),
                "explicit_rights",
            ),
        ]

        for row, expected_flag in cases:
            with self.subTest(expected_flag=expected_flag):
                result = audit_instrument_metadata(row)
                self.assertEqual(
                    result.status,
                    InstrumentMetadataStatus.EXPLICIT_NON_COMMON_CONFLICT,
                )
                self.assertIn(expected_flag, result.flags)

    def test_company_names_do_not_trigger_broad_keyword_false_positives(self) -> None:
        preferred_bank = audit_instrument_metadata(
            _row("PFBC", "Preferred Bank")
        )
        our_bond = audit_instrument_metadata(
            _row("OBAI", "Our Bond, Inc. Common Stock")
        )
        adrc_right = audit_instrument_metadata(
            _row(
                "ADRC",
                "Issuer ADS, each representing the right to receive one ordinary share",
                security_type="ADRC",
            )
        )

        self.assertEqual(
            preferred_bank.status,
            InstrumentMetadataStatus.NO_NAME_CONFLICT_DETECTED,
        )
        self.assertEqual(
            our_bond.status,
            InstrumentMetadataStatus.NO_NAME_CONFLICT_DETECTED,
        )
        self.assertEqual(
            adrc_right.status,
            InstrumentMetadataStatus.NO_NAME_CONFLICT_DETECTED,
        )

    def test_units_are_quarantined_for_review_not_called_debt(self) -> None:
        result = audit_instrument_metadata(
            _row("LP", "Issuer L.P. Common Units representing partner interests")
        )

        self.assertEqual(
            result.status,
            InstrumentMetadataStatus.UNIT_STRUCTURE_REVIEW,
        )
        self.assertEqual(result.flags, ("unit_structure_review",))

    def test_non_common_provider_type_stays_outside_common_family(self) -> None:
        result = audit_instrument_metadata(
            _row("ETF", "Example Exchange Traded Fund", security_type="ETF")
        )

        self.assertEqual(
            result.status,
            InstrumentMetadataStatus.OUTSIDE_COMMON_TYPE_FAMILY,
        )

    def test_manifest_is_deterministic_and_explicitly_not_eligibility(self) -> None:
        first = instrument_metadata_audit_manifest()
        second = instrument_metadata_audit_manifest()

        self.assertEqual(first, second)
        self.assertEqual(len(first["fingerprint"]), 64)
        self.assertEqual(first["common_type_family"], ["ADRC", "CS"])
        self.assertEqual(first["status"], "frozen_research_audit_not_eligibility")

    def test_summary_and_date_manifest_remain_non_promotable(self) -> None:
        records = audit_records(
            [
                _row("AAA", "AAA Incorporated Common Stock"),
                _row("BBB", "BBB 7.50% Notes due 2030"),
                _row("CCC", "CCC Exchange Traded Fund", security_type="ETF"),
            ]
        )
        summary = summarize_records(records)
        manifest = build_date_manifest(
            census_manifest={
                "requested_asof_date": "2025-04-03",
                "census_content_sha256": "content",
                "membership_sha256": "membership",
            },
            summary=summary,
        )

        self.assertEqual(summary["security_record_count"], 3)
        self.assertEqual(
            summary["status_counts"]["explicit_non_common_name_conflict"],
            1,
        )
        self.assertEqual(
            summary["common_type_family_flag_counts"]["explicit_debt"],
            1,
        )
        self.assertNotIn(
            "unit_structure_review",
            summary["common_type_family_flag_counts"],
        )
        self.assertFalse(manifest["eligibility"]["instrument_translation_frozen"])
        self.assertFalse(manifest["eligibility"]["universe_complete"])
        self.assertFalse(manifest["eligibility"]["policy_promotion_eligible"])


if __name__ == "__main__":
    unittest.main()
