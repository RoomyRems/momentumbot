from __future__ import annotations

import unittest

from momentumbot.identity_resolved_universe import (
    identity_resolved_membership_fingerprint,
    identity_resolved_universe_v0_1_manifest,
    provisional_membership_fingerprint,
    resolve_identity_membership,
)


def _row(
    ticker: str,
    *,
    cik: str,
    figi: str,
) -> dict[str, object]:
    return {
        "ticker": ticker,
        "included": True,
        "reason": "included_provisional_common_equity",
        "security_record_count": 1,
        "common_type_record_count": 1,
        "accepted_identity_count": 1,
        "metadata_statuses": ["no_name_conflict_detected"],
        "selected_security_type": "CS",
        "selected_primary_exchange": "XNAS",
        "selected_cik": cik,
        "selected_composite_figi": figi,
    }


class IdentityResolvedUniverseTests(unittest.TestCase):
    def test_policy_is_fingerprinted_and_non_promotable(self) -> None:
        manifest = identity_resolved_universe_v0_1_manifest()

        self.assertEqual(len(manifest["fingerprint"]), 64)
        self.assertEqual(
            manifest["status"],
            "frozen_research_data_contract_not_promotable",
        )

    def test_resolution_removes_only_quarantine_and_attaches_identity(self) -> None:
        rows = [
            _row("AAA", cik="1", figi="FIGI-AAA"),
            _row("BBB", cik="2", figi=""),
            _row("CCC", cik="2", figi=""),
        ]
        resolved = resolve_identity_membership(
            rows,
            [
                {
                    "ticker": "AAA",
                    "identifier_kind": "composite_figi",
                    "identifier": "FIGI-AAA",
                }
            ],
            [
                {
                    "ticker": "BBB",
                    "cik": "2",
                    "composite_figi": "",
                    "reason": "nonunique_cik_without_composite_figi",
                },
                {
                    "ticker": "CCC",
                    "cik": "2",
                    "composite_figi": "",
                    "reason": "nonunique_cik_without_composite_figi",
                },
            ],
        )

        self.assertEqual([row["ticker"] for row in resolved], ["AAA"])
        self.assertEqual(
            resolved[0]["identity_identifier_kind"], "composite_figi"
        )
        self.assertEqual(resolved[0]["identity_identifier"], "FIGI-AAA")
        self.assertEqual(len(identity_resolved_membership_fingerprint(resolved)), 64)

    def test_unique_cik_fallback_requires_missing_figi(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique CIK fallback mismatch"):
            resolve_identity_membership(
                [_row("AAA", cik="1", figi="FIGI-AAA")],
                [
                    {
                        "ticker": "AAA",
                        "identifier_kind": "unique_cik_fallback",
                        "identifier": "1",
                    }
                ],
                [],
            )

    def test_statuses_must_cover_every_provisional_ticker(self) -> None:
        with self.assertRaisesRegex(ValueError, "do not cover"):
            resolve_identity_membership(
                [
                    _row("AAA", cik="1", figi="FIGI-AAA"),
                    _row("BBB", cik="2", figi="FIGI-BBB"),
                ],
                [
                    {
                        "ticker": "AAA",
                        "identifier_kind": "composite_figi",
                        "identifier": "FIGI-AAA",
                    }
                ],
                [],
            )

    def test_provisional_membership_fingerprint_is_order_invariant(self) -> None:
        first = _row("AAA", cik="1", figi="FIGI-AAA")
        second = _row("BBB", cik="2", figi="FIGI-BBB")

        self.assertEqual(
            provisional_membership_fingerprint([first, second]),
            provisional_membership_fingerprint([second, first]),
        )


if __name__ == "__main__":
    unittest.main()
