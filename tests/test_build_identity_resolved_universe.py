from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from momentumbot.historical_universe import historical_universe_v0_1_manifest
from momentumbot.identity_resolved_universe import (
    json_fingerprint,
    provisional_membership_fingerprint,
)
from scripts.build_identity_resolved_universe import (
    build_panel_identity_statuses,
    build_date_payload,
    main,
    validate_expected_audit_result,
    validate_identity_audit_bundle,
)


def _row(ticker: str = "AAA") -> dict[str, object]:
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
        "selected_cik": "1",
        "selected_composite_figi": f"FIGI-{ticker}",
    }


def _bundle(root: Path) -> tuple[dict[str, object], dict[str, object]]:
    bridge: dict[str, object] = {
        "schema_version": 1,
        "identity_policy_id": "historical-identity-continuity-v0.1",
        "earlier_date": "2025-04-03",
        "later_date": "2026-07-09",
        "date_identity_status": {
            "2025-04-03": {
                "accepted": [
                    {
                        "ticker": "AAA",
                        "identifier_kind": "composite_figi",
                        "identifier": "FIGI-AAA",
                    }
                ],
                "quarantined": [],
            },
            "2026-07-09": {
                "accepted": [
                    {
                        "ticker": "AAA",
                        "identifier_kind": "composite_figi",
                        "identifier": "FIGI-AAA",
                    }
                ],
                "quarantined": [],
            },
        },
    }
    bridge["bridge_sha256"] = json_fingerprint(bridge)
    payloads: dict[str, object] = {
        "bridge": bridge,
        "alias_validation": {"records": []},
        "transition_resolution": {"records": []},
        "action_windows": {"2025-04-03": {}, "2026-07-09": {}},
        "ticker_event_sample": {"records": []},
    }
    filenames = {
        "bridge": "identity-bridge.json",
        "alias_validation": "alias-validation.json",
        "transition_resolution": "transition-name-change-resolution.json",
        "action_windows": "corporate-action-windows.json",
        "ticker_event_sample": "massive-ticker-event-sample.json",
    }
    for key, filename in filenames.items():
        (root / filename).write_text(json.dumps(payloads[key]), encoding="utf-8")

    source = {
        "2025-04-03": {
            "included_membership_sha256": "membership-early",
            "policy_fingerprint": "source-policy",
        },
        "2026-07-09": {
            "included_membership_sha256": "membership-late",
            "policy_fingerprint": "source-policy",
        },
    }
    manifest: dict[str, object] = {
        "schema_version": 1,
        "audit_id": "historical-identity-corporate-action-audit-v0.1",
        "knowledge_policy": {
            "uses_benchmark_labels": False,
            "runtime_strategy_inputs_created": False,
        },
        "source_artifacts": source,
        "scope": {
            "dates": ["2025-04-03", "2026-07-09"],
            "corporate_action_lookback_days": 120,
        },
        "summary": {
            "alias_mapping_gate_pass": True,
            "bulk_corporate_action_gate_pass": True,
            "earlier_identity_quarantine_tickers": [],
            "later_identity_quarantine_tickers": [],
            "earlier_identity_accepted_count": 1,
            "later_identity_accepted_count": 1,
        },
        "eligibility": {
            "identity_gate_passes_after_explicit_quarantine": True,
            "full_feature_snapshot_candidate": True,
            "universe_complete": False,
        },
        "files": {
            "identity_bridge": filenames["bridge"],
            "alias_validation": filenames["alias_validation"],
            "transition_name_change_resolution": filenames[
                "transition_resolution"
            ],
            "corporate_action_windows": filenames["action_windows"],
            "massive_ticker_event_sample": filenames["ticker_event_sample"],
        },
        "content_sha256": json_fingerprint(payloads),
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest, bridge


class BuildIdentityResolvedUniverseTests(unittest.TestCase):
    def test_main_emits_every_panel_date_from_endpoint_audit(self) -> None:
        dates = ["2025-04-03", "2025-10-01", "2026-07-09"]
        source_policy = historical_universe_v0_1_manifest()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            provisional = root / "provisional-universe-v0.1"
            provisional.mkdir()
            date_manifests = []
            memberships = {}
            for value in dates:
                row = _row()
                membership = provisional_membership_fingerprint([row])
                memberships[value] = membership
                (provisional / f"{value}-included.json").write_text(
                    json.dumps(
                        {
                            "trading_date": value,
                            "membership_sha256": membership,
                            "policy_fingerprint": source_policy["fingerprint"],
                            "rows": [row],
                        }
                    ),
                    encoding="utf-8",
                )
                date_manifests.append(
                    {
                        "trading_date": value,
                        "summary": {
                            "included_membership_sha256": membership,
                        },
                    }
                )
            (provisional / "manifest.json").write_text(
                json.dumps(
                    {
                        "dates": dates,
                        "universe_policy": source_policy,
                        "date_manifests": date_manifests,
                        "complete_relative_to_census": True,
                        "universe_complete": False,
                    }
                ),
                encoding="utf-8",
            )
            audit_root = root / "identity-continuity-v0.1"
            audit_root.mkdir()
            _bundle(audit_root)
            audit_manifest = json.loads(
                (audit_root / "manifest.json").read_text(encoding="utf-8")
            )
            audit_manifest["source_artifacts"] = {
                value: {
                    "included_membership_sha256": memberships[value],
                    "policy_fingerprint": source_policy["fingerprint"],
                }
                for value in (dates[0], dates[-1])
            }
            (audit_root / "manifest.json").write_text(
                json.dumps(audit_manifest),
                encoding="utf-8",
            )

            result = main(["--census-root", str(root)])

            self.assertEqual(result, 0)
            output = json.loads(
                (root / "identity-resolved-universe-v0.1" / "manifest.json")
                .read_text(encoding="utf-8")
            )
            self.assertEqual(output["dates"], dates)
            self.assertEqual(
                output["source_artifacts"]["identity_audit_scope_dates"],
                [dates[0], dates[-1]],
            )
            self.assertEqual(set(output["date_summaries"]), set(dates))

    def test_panel_resolves_intermediate_date_and_binds_endpoints(self) -> None:
        payloads = {
            "2026-07-10": {"rows": [_row("AAA")]},
            "2026-07-13": {"rows": [_row("MID")]},
            "2026-07-23": {"rows": [_row("ZZZ")]},
        }
        endpoint_status = {
            value: {
                "accepted": [
                    {
                        "ticker": ticker,
                        "identifier_kind": "composite_figi",
                        "identifier": f"FIGI-{ticker}",
                    }
                ],
                "quarantined": [],
            }
            for value, ticker in (
                ("2026-07-10", "AAA"),
                ("2026-07-23", "ZZZ"),
            )
        }

        statuses = build_panel_identity_statuses(
            payloads,
            audit_dates=["2026-07-10", "2026-07-23"],
            bridge={"date_identity_status": endpoint_status},
        )

        self.assertEqual(
            statuses["2026-07-13"]["accepted"][0]["ticker"],
            "MID",
        )
        changed = json.loads(json.dumps(endpoint_status))
        changed["2026-07-23"]["accepted"][0]["identifier"] = "WRONG"
        with self.assertRaisesRegex(RuntimeError, "disagrees with audit"):
            build_panel_identity_statuses(
                payloads,
                audit_dates=["2026-07-10", "2026-07-23"],
                bridge={"date_identity_status": changed},
            )

    def test_intermediate_date_pins_provisional_root_without_audit_row(self) -> None:
        row = _row("MID")
        source_hash = provisional_membership_fingerprint([row])
        payload = build_date_payload(
            trading_date="2026-07-13",
            provisional_payload={
                "trading_date": "2026-07-13",
                "membership_sha256": source_hash,
                "policy_fingerprint": "source-policy",
                "rows": [row],
            },
            accepted_statuses=[
                {
                    "ticker": "MID",
                    "identifier_kind": "composite_figi",
                    "identifier": "FIGI-MID",
                }
            ],
            quarantined_statuses=[],
            identity_manifest={
                "audit_id": "historical-identity-corporate-action-audit-v0.1",
                "content_sha256": "audit-content",
                "source_artifacts": {},
            },
            bridge={"bridge_sha256": "bridge"},
            expected_source_policy_fingerprint="source-policy",
            expected_source_membership_sha256=source_hash,
        )

        self.assertEqual(payload["summary"]["identity_accepted_ticker_count"], 1)

    def test_bundle_fingerprints_every_audit_component(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            expected_manifest, expected_bridge = _bundle(root)

            manifest, bridge = validate_identity_audit_bundle(root)

            self.assertEqual(manifest, expected_manifest)
            self.assertEqual(bridge, expected_bridge)
            (root / "alias-validation.json").write_text(
                json.dumps({"records": [{"changed": True}]}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "content fingerprint"):
                validate_identity_audit_bundle(root)

    def test_date_payload_pins_source_and_remains_non_promotable(self) -> None:
        row = _row()
        source_hash = provisional_membership_fingerprint([row])
        identity_manifest = {
            "audit_id": "historical-identity-corporate-action-audit-v0.1",
            "content_sha256": "audit-content",
            "source_artifacts": {
                "2025-04-03": {
                    "included_membership_sha256": source_hash,
                    "policy_fingerprint": "source-policy",
                }
            },
        }
        payload = build_date_payload(
            trading_date="2025-04-03",
            provisional_payload={
                "trading_date": "2025-04-03",
                "membership_sha256": source_hash,
                "policy_fingerprint": "source-policy",
                "rows": [row],
            },
            accepted_statuses=[
                {
                    "ticker": "AAA",
                    "identifier_kind": "composite_figi",
                    "identifier": "FIGI-AAA",
                }
            ],
            quarantined_statuses=[],
            identity_manifest=identity_manifest,
            bridge={"bridge_sha256": "bridge"},
        )

        self.assertEqual(payload["summary"]["identity_accepted_ticker_count"], 1)
        self.assertTrue(
            payload["eligibility"]["complete_relative_to_provisional_membership"]
        )
        self.assertFalse(payload["eligibility"]["universe_complete"])
        self.assertFalse(payload["eligibility"]["policy_promotion_eligible"])

    def test_expected_result_rejects_changed_provider_content(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest, bridge = _bundle(Path(raw))
        expected = {
            "audit_id": manifest["audit_id"],
            "final_artifact": {"audit_content_sha256": "different"},
            "identity_contract": {"snapshot_feature_lookback_days": 120},
            "results": {
                "cross_date_bridge": {
                    "bridge_sha256": bridge["bridge_sha256"]
                },
                "source_provisional_universe": manifest["source_artifacts"],
                "explicit_identity_quarantine": {},
            },
        }

        with self.assertRaisesRegex(RuntimeError, "frozen audit content"):
            validate_expected_audit_result(expected, manifest, bridge)


if __name__ == "__main__":
    unittest.main()
