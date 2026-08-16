from __future__ import annotations

import unittest
import json
from pathlib import Path
import tempfile

from momentumbot.identity_resolved_universe import (
    identity_resolved_membership_fingerprint,
    identity_resolved_universe_v0_1_manifest,
    json_fingerprint,
    load_identity_resolved_universe,
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

    def test_loader_verifies_complete_bundle_before_returning_rows(self) -> None:
        row = _row("AAA", cik="1", figi="FIGI-AAA")
        row.update(
            {
                "identity_identifier_kind": "composite_figi",
                "identity_identifier": "FIGI-AAA",
            }
        )
        policy = identity_resolved_universe_v0_1_manifest()
        source = {
            "provisional_universe_policy_fingerprint": "source-policy",
            "provisional_membership_sha256_by_date": {
                "2025-04-03": "membership"
            },
            "identity_audit_id": "audit-v0.1",
            "identity_audit_content_sha256": "audit-content",
            "identity_bridge_sha256": "bridge",
        }
        summary = {
            "provisional_ticker_count": 1,
            "identity_accepted_ticker_count": 1,
            "identity_quarantine_count": 0,
            "identity_quarantine_tickers": [],
            "membership_sha256": identity_resolved_membership_fingerprint([row]),
        }
        payload = {
            "schema_version": 1,
            "artifact_id": "identity-resolved-universe-v0.1",
            "trading_date": "2025-04-03",
            "policy_fingerprint": policy["fingerprint"],
            "source_artifacts": {
                "provisional_policy_fingerprint": "source-policy",
                "provisional_membership_sha256": "membership",
                "identity_audit_id": "audit-v0.1",
                "identity_audit_content_sha256": "audit-content",
                "identity_bridge_sha256": "bridge",
            },
            "summary": summary,
            "eligibility": {
                "complete_relative_to_provisional_membership": True,
                "identity_gate_pass": True,
                "full_feature_snapshot_candidate": True,
                "universe_complete": False,
                "full_walk_forward_eligible": False,
                "policy_promotion_eligible": False,
            },
            "knowledge_policy": {
                "uses_benchmark_labels": False,
                "uses_future_market_outcomes": False,
                "membership_change": "explicit_identity_quarantine_only",
            },
            "rows": [row],
        }
        manifest = {
            "schema_version": 1,
            "artifact_id": "identity-resolved-universe-v0.1",
            "dates": ["2025-04-03"],
            "universe_policy": policy,
            "source_artifacts": source,
            "date_summaries": {"2025-04-03": summary},
            "eligibility": {
                "complete_relative_to_provisional_membership": True,
                "identity_gate_pass": True,
                "full_feature_snapshot_candidate": True,
                "universe_complete": False,
            },
            "knowledge_policy": {
                "uses_benchmark_labels": False,
                "uses_future_market_outcomes": False,
            },
        }
        manifest["content_sha256"] = json_fingerprint(
            {
                "universe_policy": policy,
                "source_artifacts": source,
                "date_payloads": [payload],
            }
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            member_path = root / "2025-04-03-included.json"
            member_path.write_text(json.dumps(payload), encoding="utf-8")

            rows, loaded_payload, loaded_manifest = load_identity_resolved_universe(
                root,
                trading_date="2025-04-03",
            )

            self.assertEqual(rows, [row])
            self.assertEqual(loaded_payload, payload)
            self.assertEqual(loaded_manifest, manifest)
            payload["rows"][0]["identity_identifier"] = "TAMPERED"
            member_path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "membership hash"):
                load_identity_resolved_universe(
                    root,
                    trading_date="2025-04-03",
                )


if __name__ == "__main__":
    unittest.main()
