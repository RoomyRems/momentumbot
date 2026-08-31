from __future__ import annotations

import copy
import hashlib
import unittest
from pathlib import Path

from momentumbot.research.sealed_historical_availability import SELECTED_DATES
from momentumbot.research.sealed_historical_source_acquisition_v02 import (
    expected_authorization_body as expected_v02_authorization_body,
)
from momentumbot.research.sealed_historical_source_acquisition_v03 import (
    AUTHORIZATION_CONTENT_SHA256,
    AUTHORIZATION_ID,
    build_acquisition_report,
    expected_authorization_body,
    load_authorization,
    validate_parent_bundle,
)
from momentumbot.research.sealed_historical_walk_forward import load_json_object


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = ROOT / "research/strategy/sealed-historical-source-acquisition-v0.3.json"
V02_AUTHORIZATION = ROOT / "research/strategy/sealed-historical-source-acquisition-v0.2.json"
V02_SUCCESS = ROOT / "research/data-audits/sealed-historical-source-acquisition-v0.2-run-33389380992-success-2026-08-31.json"
SCANNER_FAILURE = ROOT / "research/data-audits/sealed-historical-scanner-runtime-v0.1-normalization-failure-2026-08-31.json"
WORKFLOW = ROOT / ".github/workflows/sealed-historical-source-acquisition-v03.yml"
REGISTRATION_AUDIT = ROOT / "research/data-audits/sealed-historical-source-acquisition-v0.3-registration-2026-08-31.json"
REGISTRATION_AUDIT_CONTENT_SHA256 = (
    "2177a8e867668a45c78b661c971429ff0bbda0fd6aa967d060be02a8e164d3f8"
)


class SealedHistoricalSourceAcquisitionV03Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.authorization = load_authorization(str(AUTHORIZATION))

    def _summary(self) -> dict[str, object]:
        return {
            "dates": list(SELECTED_DATES),
            "census_page_counts": {value: 12 for value in SELECTED_DATES},
            "census_row_counts": {value: 11_500 for value in SELECTED_DATES},
            "candidate_counts": {value: 12 for value in SELECTED_DATES},
            "canonical_source_input_compressed_bytes": {value: 1_000 for value in SELECTED_DATES},
            "source_hashes": {"source": "a" * 64},
            "gates": {
                "census_complete": True,
                "identity_complete": True,
                "market_discovery_complete": True,
                "float_complete": True,
                "news_complete": True,
                "scanner_snapshot_complete": True,
                "canonical_scanner_inputs_complete": True,
                "present_day_asset_master_skipped": True,
            },
        }

    def test_authorization_changes_only_the_normalization_child(self) -> None:
        self.assertEqual(self.authorization["authorization_id"], AUTHORIZATION_ID)
        self.assertEqual(self.authorization["content_sha256"], AUTHORIZATION_CONTENT_SHA256)
        child = expected_authorization_body()
        parent = expected_v02_authorization_body()
        for key in (
            "authority_boundary",
            "causal_boundary",
            "cost_ceiling",
            "credential_routing",
            "request_budget",
            "retention_budget",
        ):
            self.assertEqual(child[key], parent[key])
        self.assertTrue(child["repair_boundary"]["normalization_only_change"])
        self.assertEqual(
            child["normalization_contract"]["percent_gain_target_minute_adjustment"],
            "split",
        )
        self.assertEqual(
            child["normalization_contract"]["actual_price_and_volume_adjustment"],
            "raw",
        )

    def test_exact_success_and_failure_parents_are_required(self) -> None:
        validate_parent_bundle(
            v02_authorization=load_json_object(V02_AUTHORIZATION),
            v02_success_audit=load_json_object(V02_SUCCESS),
            scanner_failure_audit=load_json_object(SCANNER_FAILURE),
        )
        changed = copy.deepcopy(load_json_object(SCANNER_FAILURE))
        changed["diagnostic_result"]["scanner_row_count"] = 1
        with self.assertRaisesRegex(ValueError, "scanner failure audit hash"):
            validate_parent_bundle(
                v02_authorization=load_json_object(V02_AUTHORIZATION),
                v02_success_audit=load_json_object(V02_SUCCESS),
                scanner_failure_audit=changed,
            )

    def test_report_preserves_cost_causal_and_attempt_boundaries(self) -> None:
        report = build_acquisition_report(
            authorization=self.authorization,
            source_summary=self._summary(),
            request_budget={"total_attempts": 25_000, "by_host": {"data.alpaca.markets": 25_000}},
            retained_bytes=700_000_000,
            repository="RoomyRems/momentumbot",
            authorization_commit_sha="a" * 40,
            workflow_run_id="123",
            workflow_run_attempt=1,
        )
        self.assertTrue(report["source_acquisition_gate_passed"])
        self.assertFalse(report["cost"]["databento_called"])
        self.assertFalse(report["causal_attestation"]["transcript_record_values_read"])
        self.assertFalse(report["causal_attestation"]["order_submitted"])

    def test_workflow_is_unarmed_on_push_and_uses_consistent_basis(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("github.event_name == 'workflow_dispatch'", text)
        self.assertIn("--gain-basis split_previous_close_split_target_close", text)
        self.assertIn("--market-discovery-id causal-market-discovery-v0.3", text)
        self.assertIn('MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_LIMIT: "40000"', text)
        self.assertIn("github.run_attempt == 1", text)
        self.assertNotIn("DATABENTO_API_KEY", text)
        self.assertNotIn("schedule:", text)
        self.assertLess(
            text.index("Consume authorization before provider access"),
            text.index("Acquire point-in-time Massive membership"),
        )

    def test_registration_audit_binds_versioned_files_provider_free(self) -> None:
        audit = load_json_object(REGISTRATION_AUDIT)
        body = dict(audit)
        claimed = body.pop("content_sha256")
        from momentumbot.research.sealed_historical_walk_forward import canonical_fingerprint
        self.assertEqual(canonical_fingerprint(body), claimed)
        self.assertEqual(claimed, REGISTRATION_AUDIT_CONTENT_SHA256)
        self.assertEqual(audit["causal_attestation"]["provider_calls"], 0)
        for row in audit["artifacts"].values():
            self.assertEqual(
                hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest(),
                row["file_sha256"],
            )


if __name__ == "__main__":
    unittest.main()
