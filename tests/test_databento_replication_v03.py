from __future__ import annotations

import copy
import hashlib
import json
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from momentumbot.research.databento_quote import SDK_VERSION
from momentumbot.research.databento_replication_v03 import (
    AUTHORIZED_PUSH_PARENT_SHA,
    MAX_PREFLIGHT_BILLABLE_SIZE_BYTES,
    MAX_PREFLIGHT_COST_USD,
    PARENT_SUCCESS_CONTENT_SHA256,
    REPLICATION_CASES,
    REPLICATION_CONTENT_SHA256,
    REQUESTS,
    RESET_ENGINE_SOURCE_FILE_SHA256,
    RuntimeConstants,
    build_unavailable_report,
    load_parent_success_audit,
    load_replication_contract,
    run_replication,
    validate_parent_success_audit,
    validate_replication_contract,
    validate_replication_report,
)
from momentumbot.research.microstructure_contract import canonical_fingerprint
from tests.test_databento_smoke_v02 import FakeClient


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-replication-v0.3.json"
)
PARENT_SUCCESS = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-smoke-acquisition-v0.2-"
    "run-32435988929-success-2026-08-20.json"
)
RESET_ENGINE = ROOT / "src" / "momentumbot" / "research" / "databento_smoke_v02.py"
REGISTRATION_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-replication-v0.3-registration-2026-08-20.json"
)
WORKFLOW = (
    ROOT / ".github" / "workflows" / "databento-microstructure-replication-v03.yml"
)
SCRIPT = ROOT / "scripts" / "run_databento_microstructure_replication_v03.py"
RUNTIME = RuntimeConstants(
    f_last=128,
    f_tob=64,
    f_snapshot=32,
    f_bad_ts_recv=8,
    undef_price=9_223_372_036_854_775_807,
)


class DatabentoReplicationV03Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parent_success = load_parent_success_audit(PARENT_SUCCESS)
        cls.contract = load_replication_contract(
            CONTRACT,
            parent_success_audit=cls.parent_success,
        )

    def run_gate(self, client: FakeClient) -> dict[str, object]:
        return run_replication(
            self.contract,
            client,
            parent_success_audit=self.parent_success,
            generated_at=datetime(2026, 8, 20, 15, tzinfo=UTC),
            sdk_version=SDK_VERSION,
            runtime=RUNTIME,
        )

    def test_parent_success_contract_and_engine_are_hash_bound(self):
        self.assertEqual(
            self.parent_success["content_sha256"],
            PARENT_SUCCESS_CONTENT_SHA256,
        )
        validate_parent_success_audit(self.parent_success)
        self.assertEqual(self.contract["content_sha256"], REPLICATION_CONTENT_SHA256)
        self.assertEqual(
            canonical_fingerprint(
                {
                    key: value
                    for key, value in self.contract.items()
                    if key != "content_sha256"
                }
            ),
            REPLICATION_CONTENT_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(RESET_ENGINE.read_bytes()).hexdigest(),
            RESET_ENGINE_SOURCE_FILE_SHA256,
        )
        self.assertEqual(
            self.contract["authorization"]["authorized_push_parent_sha"],
            AUTHORIZED_PUSH_PARENT_SHA,
        )

        changed = copy.deepcopy(self.contract)
        changed["request_surface"]["cases"] = changed["request_surface"]["cases"][:2]
        changed["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in changed.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "content hash changed"):
            validate_replication_contract(
                changed,
                parent_success_audit=self.parent_success,
            )

    def test_exact_six_request_surface_and_ceilings_are_frozen(self):
        self.assertEqual(len(REPLICATION_CASES), 3)
        self.assertEqual(len(REQUESTS), 6)
        self.assertEqual(
            tuple((row.trading_date, row.symbol) for row in REQUESTS[::2]),
            REPLICATION_CASES,
        )
        self.assertEqual(tuple(row.schema for row in REQUESTS), (
            "mbp-10",
            "mbo",
            "mbp-10",
            "mbo",
            "mbp-10",
            "mbo",
        ))
        self.assertEqual(MAX_PREFLIGHT_COST_USD, Decimal("0.20"))
        self.assertEqual(MAX_PREFLIGHT_BILLABLE_SIZE_BYTES, 380_000_000)

    def test_registration_audit_binds_the_exact_v03_bundle(self):
        audit = json.loads(REGISTRATION_AUDIT.read_text(encoding="utf-8"))
        claimed = audit["content_sha256"]
        unsigned = {key: value for key, value in audit.items() if key != "content_sha256"}
        self.assertEqual(canonical_fingerprint(unsigned), claimed)
        self.assertEqual(
            audit["contract"]["content_sha256"],
            REPLICATION_CONTENT_SHA256,
        )
        self.assertEqual(
            audit["parent_success"]["content_sha256"],
            PARENT_SUCCESS_CONTENT_SHA256,
        )
        for row in audit["bound_files"]:
            self.assertEqual(
                hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest(),
                row["file_sha256"],
            )
        self.assertFalse(audit["execution_status"]["provider_timeseries_request_run"])
        self.assertFalse(audit["authority_boundary"]["runtime_feature_authority_created"])
        self.assertFalse(audit["authority_boundary"]["paper_or_live_order_submitted"])

    def test_preflight_cost_or_size_failure_makes_zero_timeseries_calls(self):
        for client in (
            FakeClient(per_request_cost=0.034),
            FakeClient(per_request_size=63_333_334),
        ):
            with self.subTest(client=client):
                report = self.run_gate(client)
                validate_replication_report(report)
                self.assertFalse(report["preflight"]["preflight_passed"])
                self.assertEqual(report["preflight"]["request_count_quoted"], 6)
                self.assertEqual(report["timeseries_request_count"], 0)
                self.assertEqual(client.timeseries.calls, [])

    def test_all_three_cases_pass_the_unchanged_exact_replay(self):
        client = FakeClient()
        report = self.run_gate(client)
        validate_replication_report(report)
        self.assertEqual(report["preflight"]["request_count_quoted"], 6)
        self.assertEqual(report["timeseries_request_count"], 6)
        self.assertEqual(len(report["downloads"]), 6)
        self.assertEqual(
            tuple((row["trading_date"], row["symbol"]) for row in report["cases"]),
            REPLICATION_CASES,
        )
        self.assertTrue(report["g1_schema_and_integrity_passed"])
        self.assertTrue(report["g2_reconstruction_passed"])
        self.assertTrue(report["replication_passed"])
        for case in report["cases"]:
            self.assertTrue(case["g1_schema_and_integrity_passed"])
            self.assertTrue(case["g2_reconstruction_passed"])
            mbo = case["downloads"][1]["metrics"]
            self.assertEqual(mbo["session_initialization_clear_count"], 1)
            self.assertEqual(mbo["comparison_metrics"]["aligned_sample_count"], 1)
            self.assertEqual(mbo["comparison_metrics"]["mbp10_exact_match_count"], 1)
        self.assertTrue(all(not path.exists() for path in client.timeseries.paths))

    def test_completed_mismatch_does_not_truncate_registered_cohort(self):
        client = FakeClient(mismatch=True)
        report = self.run_gate(client)
        validate_replication_report(report)
        self.assertEqual(report["timeseries_request_count"], 6)
        self.assertEqual(len(report["cases"]), 3)
        self.assertTrue(report["g1_schema_and_integrity_passed"])
        self.assertFalse(report["g2_reconstruction_passed"])
        self.assertFalse(report["replication_passed"])
        self.assertTrue(all(not path.exists() for path in client.timeseries.paths))

    def test_provider_or_parser_failure_is_sanitized_without_retry(self):
        for client in (
            FakeClient(fail_on_call=2),
            FakeClient(malformed=True),
        ):
            with self.subTest(client=client):
                report = self.run_gate(client)
                validate_replication_report(report)
                self.assertLess(report["timeseries_request_count"], 6)
                self.assertFalse(report["automatic_retry_attempted"])
                self.assertFalse(report["replication_passed"])
                self.assertNotIn("provider detail", json.dumps(report, sort_keys=True))
                self.assertTrue(all(not path.exists() for path in client.timeseries.paths))

    def test_unavailable_report_has_no_market_data_or_runtime_authority(self):
        report = build_unavailable_report(
            self.contract,
            parent_success_audit=self.parent_success,
            generated_at=datetime(2026, 8, 20, 15, tzinfo=UTC),
            sdk_version="not_loaded",
            error_stage="credential",
            error_kind="missing_DATABENTO_API_KEY",
        )
        validate_replication_report(report)
        self.assertEqual(report["timeseries_request_count"], 0)
        self.assertFalse(report["runtime_authority_created"])

        contaminated = copy.deepcopy(report)
        contaminated["downloads"] = [{"order_id": 123}]
        contaminated["content_sha256"] = canonical_fingerprint(
            {
                key: value
                for key, value in contaminated.items()
                if key != "content_sha256"
            }
        )
        with self.assertRaisesRegex(ValueError, "prohibited field"):
            validate_replication_report(contaminated)

    def test_workflow_is_one_shot_bounded_and_sanitized(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("databento==0.83.0", workflow)
        self.assertIn("DATABENTO_API_KEY: ${{ secrets.DATABENTO_API_KEY }}", workflow)
        self.assertIn("MOMENTUMBOT_PUSH_BEFORE: ${{ github.event.before }}", workflow)
        self.assertIn("run_databento_microstructure_replication_v03.py", workflow)
        self.assertIn("<= 0.20", workflow)
        self.assertIn("<= 380000000", workflow)
        self.assertNotIn("workflow_dispatch", workflow)
        self.assertNotIn("*.dbn", workflow)
        self.assertNotIn(".dbn.zst", workflow)
        self.assertNotIn("batch.submit_job", workflow)
        self.assertNotIn("live.subscribe", workflow)
        self.assertIn('run_attempt = os.getenv("GITHUB_RUN_ATTEMPT", "1")', script)
        self.assertIn("github_actions_rerun_blocked", script)
        self.assertIn("unauthorized_push_parent", script)
        self.assertEqual(workflow.count("DATABENTO_API_KEY"), 2)


if __name__ == "__main__":
    unittest.main()
