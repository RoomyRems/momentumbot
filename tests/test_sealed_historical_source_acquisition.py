from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from momentumbot.research.sealed_historical_availability import SELECTED_DATES
from momentumbot.research.sealed_historical_source_acquisition import (
    AUTHORIZATION_CONTENT_SHA256,
    AUTHORIZATION_ID,
    MAX_CANDIDATES_PER_DATE,
    MAX_CENSUS_PAGES_PER_DATE,
    MAX_HTTP_ATTEMPTS,
    MAX_RETAINED_BYTES,
    build_acquisition_report,
    load_authorization,
    validate_acquisition_report,
    validate_authorization,
    validate_parent_bundle,
    write_json_once,
)
from momentumbot.research.sealed_historical_walk_forward import (
    canonical_fingerprint,
    load_json_object,
)


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = (
    ROOT
    / "research"
    / "strategy"
    / "sealed-historical-source-acquisition-v0.1.json"
)
CONTRACT = ROOT / "research/strategy/sealed-historical-walk-forward-v0.1.json"
AVAILABILITY_REPORT = (
    ROOT
    / "research/data-audits"
    / "sealed-historical-provider-availability-v0.2-report-2026-08-31.json"
)
AVAILABILITY_AUDIT = (
    ROOT
    / "research/data-audits"
    / "sealed-historical-provider-availability-v0.2-success-2026-08-31.json"
)
WORKFLOW = ROOT / ".github/workflows/sealed-historical-source-acquisition.yml"
REGISTRATION_AUDIT = (
    ROOT
    / "research/data-audits"
    / "sealed-historical-source-acquisition-v0.1-registration-2026-08-31.json"
)
REGISTRATION_AUDIT_CONTENT_SHA256 = "6a5b8a41d624859987adc2d556030ef33295ac94e1a2bf7e14acc8f994fda1e3"


class SealedHistoricalSourceAcquisitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.authorization = load_authorization(AUTHORIZATION)
        self.contract = load_json_object(CONTRACT)
        self.availability_report = load_json_object(AVAILABILITY_REPORT)
        self.availability_audit = load_json_object(AVAILABILITY_AUDIT)

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

    def _report(self) -> dict[str, object]:
        return build_acquisition_report(
            authorization=self.authorization,
            source_summary=self._summary(),
            request_budget={
                "schema_version": 1,
                "total_attempts": 3,
                "by_host": {
                    "api.massive.com": 1,
                    "data.alpaca.markets": 1,
                    "data.sec.gov": 1,
                },
            },
            retained_bytes=30_000,
            repository="RoomyRems/momentumbot",
            authorization_commit_sha="a" * 40,
            workflow_run_id="123",
            workflow_run_attempt=1,
        )

    def test_authorization_and_passed_parent_bundle_are_exact(self) -> None:
        self.assertEqual(
            self.authorization["content_sha256"], AUTHORIZATION_CONTENT_SHA256
        )
        self.assertEqual(self.authorization["authorization_id"], AUTHORIZATION_ID)
        self.assertEqual(
            self.authorization["request_budget"][
                "maximum_total_http_attempts_including_retries"
            ],
            MAX_HTTP_ATTEMPTS,
        )
        validate_parent_bundle(
            contract=self.contract,
            availability_report=self.availability_report,
            availability_success_audit=self.availability_audit,
        )

    def test_success_report_preserves_zero_cost_and_causal_boundaries(self) -> None:
        report = self._report()
        validate_acquisition_report(report, self.authorization)
        self.assertTrue(report["source_acquisition_gate_passed"])
        self.assertEqual(report["cost"]["incremental_provider_cost_usd"], "0")
        self.assertFalse(report["cost"]["databento_called"])
        self.assertFalse(report["causal_attestation"]["transcript_record_values_read"])
        self.assertFalse(
            report["causal_attestation"]["present_day_alpaca_asset_master_called"]
        )

    def test_page_candidate_request_and_byte_ceilings_fail_closed(self) -> None:
        summary = self._summary()
        summary["census_page_counts"][SELECTED_DATES[0]] = (
            MAX_CENSUS_PAGES_PER_DATE + 1
        )
        with self.assertRaisesRegex(ValueError, "census page ceiling"):
            build_acquisition_report(
                authorization=self.authorization,
                source_summary=summary,
                request_budget={"total_attempts": 1, "by_host": {"api.massive.com": 1}},
                retained_bytes=1,
                repository="RoomyRems/momentumbot",
                authorization_commit_sha="a" * 40,
                workflow_run_id="1",
                workflow_run_attempt=1,
            )

        summary = self._summary()
        summary["candidate_counts"][SELECTED_DATES[-1]] = (
            MAX_CANDIDATES_PER_DATE + 1
        )
        with self.assertRaisesRegex(ValueError, "candidate ceiling"):
            build_acquisition_report(
                authorization=self.authorization,
                source_summary=summary,
                request_budget={"total_attempts": 1, "by_host": {"api.massive.com": 1}},
                retained_bytes=1,
                repository="RoomyRems/momentumbot",
                authorization_commit_sha="a" * 40,
                workflow_run_id="1",
                workflow_run_attempt=1,
            )

        with self.assertRaisesRegex(ValueError, "HTTP attempt budget"):
            build_acquisition_report(
                authorization=self.authorization,
                source_summary=self._summary(),
                request_budget={
                    "total_attempts": MAX_HTTP_ATTEMPTS + 1,
                    "by_host": {"api.massive.com": MAX_HTTP_ATTEMPTS + 1},
                },
                retained_bytes=1,
                repository="RoomyRems/momentumbot",
                authorization_commit_sha="a" * 40,
                workflow_run_id="1",
                workflow_run_attempt=1,
            )

        with self.assertRaisesRegex(ValueError, "retained-byte ceiling"):
            build_acquisition_report(
                authorization=self.authorization,
                source_summary=self._summary(),
                request_budget={"total_attempts": 1, "by_host": {"api.massive.com": 1}},
                retained_bytes=MAX_RETAINED_BYTES + 1,
                repository="RoomyRems/momentumbot",
                authorization_commit_sha="a" * 40,
                workflow_run_id="1",
                workflow_run_attempt=1,
            )

    def test_rehashed_authorization_cannot_expand_authority(self) -> None:
        changed = copy.deepcopy(self.authorization)
        changed["cost_ceiling"]["databento_calls_authorized"] = 1
        body = dict(changed)
        body.pop("content_sha256")
        changed["content_sha256"] = canonical_fingerprint(body)
        with self.assertRaisesRegex(ValueError, "frozen hash"):
            validate_authorization(changed)

    def test_workflow_uses_validated_main_credentials_and_consumes_first(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("ALPACA_API_KEY: ${{ secrets.ALPACA_MAIN_API_KEY }}", text)
        self.assertIn(
            "ALPACA_API_SECRET: ${{ secrets.ALPACA_MAIN_API_SECRET }}", text
        )
        self.assertNotIn("ALPACA_API_KEY: ${{ secrets.ALPACA_API_KEY }}", text)
        self.assertNotIn("ALPACA_API_SECRET: ${{ secrets.ALPACA_API_SECRET }}", text)
        self.assertNotIn("DATABENTO_API_KEY", text)
        self.assertIn("MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_LIMIT: \"20000\"", text)
        self.assertIn("${RUNNER_TEMP}/sealed-historical-source-request-budget.json", text)
        self.assertNotIn("${{ runner.temp }}", text)
        self.assertIn("--skip-current-alpaca-reconciliation", text)
        self.assertIn("--persist-source-inputs", text)
        self.assertNotIn("schedule:", text)
        consume = text.index("Consume authorization before provider access")
        provider = text.index("Acquire point-in-time Massive membership")
        self.assertLess(consume, provider)
        self.assertNotIn("actions/checkout@v", text)
        self.assertNotIn("actions/setup-python@v", text)
        self.assertNotIn("actions/upload-artifact@v", text)

    def test_write_once_refuses_overwrite(self) -> None:
        report = self._report()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "report.json"
            write_json_once(path, report)
            with self.assertRaises(FileExistsError):
                write_json_once(path, report)

    def test_registration_audit_binds_exact_bundle(self) -> None:
        audit = load_json_object(REGISTRATION_AUDIT)
        body = dict(audit)
        claimed = body.pop("content_sha256")
        self.assertEqual(canonical_fingerprint(body), claimed)
        self.assertEqual(claimed, REGISTRATION_AUDIT_CONTENT_SHA256)
        self.assertEqual(audit["causal_attestation"]["provider_calls"], 0)
        for row in audit["artifacts"].values():
            path = ROOT / row["path"]
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), row["file_sha256"]
            )


if __name__ == "__main__":
    unittest.main()
