from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from momentumbot.research.sealed_historical_availability import SELECTED_DATES
from momentumbot.research.sealed_historical_source_acquisition import (
    expected_authorization_body as expected_v01_authorization_body,
    write_json_once,
)
from momentumbot.research.sealed_historical_source_acquisition_v02 import (
    AUTHORIZATION_CONTENT_SHA256,
    AUTHORIZATION_ID,
    MAX_HTTP_ATTEMPTS,
    V01_FAILURE_AUDIT_CONTENT_SHA256,
    V01_FAILURE_REPORT_FILE_SHA256,
    build_acquisition_report,
    expected_authorization_body,
    load_authorization,
    validate_acquisition_report,
    validate_authorization,
    validate_parent_bundle,
)
from momentumbot.research.sealed_historical_walk_forward import (
    canonical_fingerprint,
    load_json_object,
)


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = ROOT / "research/strategy/sealed-historical-source-acquisition-v0.2.json"
V01_AUTHORIZATION = ROOT / "research/strategy/sealed-historical-source-acquisition-v0.1.json"
CONTRACT = ROOT / "research/strategy/sealed-historical-walk-forward-v0.1.json"
AVAILABILITY_REPORT = ROOT / "research/data-audits/sealed-historical-provider-availability-v0.2-report-2026-08-31.json"
AVAILABILITY_AUDIT = ROOT / "research/data-audits/sealed-historical-provider-availability-v0.2-success-2026-08-31.json"
FAILURE_REPORT = ROOT / "research/data-audits/sealed-historical-source-acquisition-v0.1-failure-report-2026-08-31.json"
FAILURE_AUDIT = ROOT / "research/data-audits/sealed-historical-source-acquisition-v0.1-failure-2026-08-31.json"
WORKFLOW = ROOT / ".github/workflows/sealed-historical-source-acquisition-v02.yml"
REGISTRATION_AUDIT = ROOT / "research/data-audits/sealed-historical-source-acquisition-v0.2-registration-2026-08-31.json"
REGISTRATION_AUDIT_CONTENT_SHA256 = (
    "c1f7da2cd288900a02019fca4f8d091611a3b0f5254c39d893638a99a11bcbd5"
)


class SealedHistoricalSourceAcquisitionV02Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.authorization = load_authorization(str(AUTHORIZATION))

    def _summary(self) -> dict[str, object]:
        return {
            "dates": list(SELECTED_DATES),
            "census_page_counts": {value: 12 for value in SELECTED_DATES},
            "census_row_counts": {value: 11_500 for value in SELECTED_DATES},
            "candidate_counts": {value: 12 for value in SELECTED_DATES},
            "canonical_source_input_compressed_bytes": {
                value: 1_000 for value in SELECTED_DATES
            },
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

    def _report(self, total: int = 30_000) -> dict[str, object]:
        return build_acquisition_report(
            authorization=self.authorization,
            source_summary=self._summary(),
            request_budget={
                "schema_version": 1,
                "total_attempts": total,
                "by_host": {"data.alpaca.markets": total},
            },
            retained_bytes=700_000_000,
            repository="RoomyRems/momentumbot",
            authorization_commit_sha="a" * 40,
            workflow_run_id="123",
            workflow_run_attempt=1,
        )

    def test_authorization_is_exact_and_only_repairs_request_ceiling(self) -> None:
        self.assertEqual(self.authorization["authorization_id"], AUTHORIZATION_ID)
        self.assertEqual(
            self.authorization["content_sha256"], AUTHORIZATION_CONTENT_SHA256
        )
        self.assertEqual(self.authorization["request_budget"]["maximum_total_http_attempts_including_retries"], 40_000)
        self.assertEqual(dict(self.authorization, content_sha256=None).keys(), dict(expected_authorization_body(), content_sha256=None).keys())

        child = expected_authorization_body()
        parent = expected_v01_authorization_body()
        self.assertEqual(child["causal_boundary"], parent["causal_boundary"])
        self.assertEqual(child["cost_ceiling"], parent["cost_ceiling"])
        self.assertEqual(child["credential_routing"], parent["credential_routing"])
        self.assertEqual(child["retention_budget"], parent["retention_budget"])
        child_budget = copy.deepcopy(child["request_budget"])
        parent_budget = copy.deepcopy(parent["request_budget"])
        child_budget.pop("maximum_total_http_attempts_including_retries")
        parent_budget.pop("maximum_total_http_attempts_including_retries")
        self.assertEqual(child_budget, parent_budget)
        self.assertTrue(child["repair_boundary"]["request_ceiling_only_change"])

    def test_failure_parent_and_original_artifact_bytes_are_exact(self) -> None:
        self.assertEqual(
            hashlib.sha256(FAILURE_REPORT.read_bytes()).hexdigest(),
            V01_FAILURE_REPORT_FILE_SHA256,
        )
        failure_audit = load_json_object(FAILURE_AUDIT)
        body = dict(failure_audit)
        claimed = body.pop("content_sha256")
        self.assertEqual(claimed, V01_FAILURE_AUDIT_CONTENT_SHA256)
        self.assertEqual(canonical_fingerprint(body), claimed)
        validate_parent_bundle(
            contract=load_json_object(CONTRACT),
            availability_report=load_json_object(AVAILABILITY_REPORT),
            availability_success_audit=load_json_object(AVAILABILITY_AUDIT),
            v01_authorization=load_json_object(V01_AUTHORIZATION),
            failure_report=load_json_object(FAILURE_REPORT),
            failure_audit=failure_audit,
        )

    def test_report_accepts_repaired_ceiling_and_preserves_boundaries(self) -> None:
        report = self._report()
        validate_acquisition_report(report, self.authorization)
        self.assertEqual(report["request_budget"]["maximum_total_http_attempts"], MAX_HTTP_ATTEMPTS)
        self.assertEqual(report["request_budget"]["observed_total_http_attempts"], 30_000)
        self.assertFalse(report["cost"]["databento_called"])
        self.assertFalse(report["workflow_provenance"]["v0_1_workflow_run_rerun"])
        self.assertFalse(report["causal_attestation"]["strategy_or_account_policy_changed"])

    def test_repaired_ceiling_still_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "HTTP attempt budget"):
            self._report(MAX_HTTP_ATTEMPTS + 1)
        with self.assertRaisesRegex(ValueError, "one attempt"):
            build_acquisition_report(
                authorization=self.authorization,
                source_summary=self._summary(),
                request_budget={"total_attempts": 1, "by_host": {"data.alpaca.markets": 1}},
                retained_bytes=1,
                repository="RoomyRems/momentumbot",
                authorization_commit_sha="a" * 40,
                workflow_run_id="1",
                workflow_run_attempt=2,
            )

    def test_rehashed_child_cannot_change_strategy_or_provider_scope(self) -> None:
        changed = copy.deepcopy(self.authorization)
        changed["causal_boundary"]["strategy_threshold_or_setup_changes_allowed"] = True
        body = dict(changed)
        body.pop("content_sha256")
        changed["content_sha256"] = canonical_fingerprint(body)
        with self.assertRaisesRegex(ValueError, "frozen hash"):
            validate_authorization(changed)

    def test_workflow_is_new_one_shot_and_does_not_mutate_v0_1(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("ALPACA_API_KEY: ${{ secrets.ALPACA_MAIN_API_KEY }}", text)
        self.assertIn("ALPACA_API_SECRET: ${{ secrets.ALPACA_MAIN_API_SECRET }}", text)
        self.assertIn('MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_LIMIT: "40000"', text)
        self.assertIn("sealed-historical-source-acquisition-v0.2.json", text)
        self.assertIn("sealed-historical-source-acquisition-v02-consumed-", text)
        self.assertIn("github.run_attempt == 1", text)
        self.assertIn("v0_1_rerun", (ROOT / "scripts/run_sealed_historical_source_acquisition_v02.py").read_text())
        self.assertNotIn("DATABENTO_API_KEY", text)
        self.assertNotIn("schedule:", text)
        self.assertNotIn("ALPACA_API_KEY: ${{ secrets.ALPACA_API_KEY }}", text)
        self.assertLess(text.index("Consume authorization before provider access"), text.index("Acquire point-in-time Massive membership"))

    def test_write_once_and_registration_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "report.json"
            report = self._report()
            write_json_once(path, report)
            with self.assertRaises(FileExistsError):
                write_json_once(path, report)

        audit = load_json_object(REGISTRATION_AUDIT)
        body = dict(audit)
        claimed = body.pop("content_sha256")
        self.assertEqual(claimed, REGISTRATION_AUDIT_CONTENT_SHA256)
        self.assertEqual(canonical_fingerprint(body), claimed)
        self.assertEqual(audit["causal_attestation"]["provider_calls"], 0)
        for row in audit["artifacts"].values():
            self.assertEqual(
                hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest(),
                row["file_sha256"],
            )


if __name__ == "__main__":
    unittest.main()
