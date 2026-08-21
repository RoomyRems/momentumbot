from __future__ import annotations

import builtins
import copy
import hashlib
import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from scripts import run_databento_microstructure_feature_coverage_v02 as runner

from momentumbot.research import databento_feature_coverage_v02 as coverage
from momentumbot.research.databento_feature_coverage_v02 import (
    CASE_KEYS,
    CONTRACT_CONTENT_SHA256,
    COVERAGE_CONTRACT_ID,
    EXECUTION_AUTHORIZATION_ID,
    REQUESTS,
    extract_case_feature_diagnostic,
    load_coverage_contract,
    load_eqpt_success_audit,
    load_intj_success_audit,
    load_repair_contract,
    run_feature_coverage_diagnostic,
    validate_coverage_report,
    validate_execution_authorization,
)
from momentumbot.research.databento_quote import SDK_VERSION
from momentumbot.research.databento_feature_diagnostic_v03 import (
    SafeDiagnosticFailure,
)
from momentumbot.research.microstructure_contract import canonical_fingerprint
from tests.test_databento_feature_diagnostic_v01 import RUNTIME
from tests.test_databento_feature_diagnostic_v03 import FakeStore, _record


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-feature-coverage-v0.2.json"
)
INTJ_SUCCESS = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-feature-diagnostic-v0.3-"
    "run-32483408413-success-2026-08-21.json"
)
EQPT_SUCCESS = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-fill-cancel-repaired-feature-v0.1-"
    "run-32520311940-success-2026-08-21.json"
)
REPAIR_CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-fill-cancel-repair-v0.1.json"
)
FUTURE_AUTHORIZATION = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-feature-coverage-v0.2-execution.json"
)
REPAIR_SOURCE = (
    ROOT
    / "src"
    / "momentumbot"
    / "research"
    / "databento_fill_cancel_repair_v01.py"
)
FEATURE_ENGINE = ROOT / "src" / "momentumbot" / "research" / "microstructure_features.py"
WORKFLOW = (
    ROOT
    / ".github"
    / "workflows"
    / "databento-microstructure-feature-coverage-v02.yml"
)
SCRIPT = ROOT / "scripts" / "run_databento_microstructure_feature_coverage_v02.py"
REGISTRATION_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-feature-coverage-v0.2-registration-"
    "2026-08-21.json"
)
GENERATED_AT = datetime(2026, 8, 21, 21, tzinfo=UTC)


def _authorization() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "execution_authorization_id": EXECUTION_AUTHORIZATION_ID,
        "artifact_type": (
            "explicit_one_shot_databento_amc_gmm_repaired_feature_authorization"
        ),
        "coverage_contract_id": COVERAGE_CONTRACT_ID,
        "coverage_contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "authorized_push_parent_sha": "a" * 40,
        "explicit_user_authorization": (
            "Synthetic deterministic unit-test authorization; no provider call."
        ),
        "provider_purchase_authorized": True,
        "exact_request_count_authorized": 2,
        "hard_preflight_cost_ceiling_usd": "0.07",
        "hard_preflight_billable_size_ceiling_bytes": 65_000_000,
        "first_github_actions_attempt_only": True,
        "automatic_retry_authorized": False,
        "batch_or_live_endpoint_authorized": False,
        "mbp10_redownload_authorized": False,
        "raw_market_data_publication_authorized": False,
        "broker_or_order_change_authorized": False,
        "strategy_or_threshold_change_authorized": False,
    }
    payload["content_sha256"] = canonical_fingerprint(payload)
    return payload


def _price_mismatch_records() -> list[object]:
    return [
        _record(
            sequence=0,
            action="R",
            side="N",
            ts_recv=900_000_000,
            flags=0,
        ),
        _record(
            sequence=1,
            action="A",
            side="A",
            ts_recv=1_000_000_000,
            flags=RUNTIME.f_last,
            price=100,
            size=100,
            order_id=7,
        ),
        _record(
            sequence=2,
            action="F",
            side="A",
            ts_recv=2_000_000_000,
            flags=0,
            price=101,
            size=100,
            order_id=7,
        ),
        _record(
            sequence=2,
            action="C",
            side="A",
            ts_recv=2_000_000_001,
            flags=RUNTIME.f_last,
            price=100,
            size=100,
            order_id=7,
        ),
    ]


class FakeMetadata:
    def __init__(self, *, cost: float = 0.034, size: int = 30_000_000) -> None:
        self.cost = cost
        self.size = size
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get_billable_size(self, **kwargs: object) -> int:
        self.calls.append(("get_billable_size", kwargs))
        return self.size

    def get_cost(self, **kwargs: object) -> float:
        self.calls.append(("get_cost", kwargs))
        return self.cost


class FakeTimeseries:
    def __init__(self, *, fail_at: int | None = None) -> None:
        self.fail_at = fail_at
        self.calls: list[dict[str, object]] = []

    def get_range(self, **kwargs: object) -> FakeStore:
        index = len(self.calls)
        self.calls.append(kwargs)
        if index == self.fail_at:
            raise RuntimeError("licensed provider detail must not persist")
        Path(str(kwargs["path"])).write_bytes(b"synthetic DBN placeholder")
        return FakeStore(_price_mismatch_records())


class FakeClient:
    def __init__(
        self,
        *,
        cost: float = 0.034,
        size: int = 30_000_000,
        fail_at: int | None = None,
    ) -> None:
        self.metadata = FakeMetadata(cost=cost, size=size)
        self.timeseries = FakeTimeseries(fail_at=fail_at)


class DatabentoFeatureCoverageV02Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.intj_success = load_intj_success_audit(INTJ_SUCCESS)
        cls.eqpt_success = load_eqpt_success_audit(EQPT_SUCCESS)
        cls.repair_contract = load_repair_contract(REPAIR_CONTRACT)
        cls.contract = load_coverage_contract(
            CONTRACT,
            intj_success_audit=cls.intj_success,
            eqpt_success_audit=cls.eqpt_success,
            repair_contract=cls.repair_contract,
        )
        cls.authorization = _authorization()
        validate_execution_authorization(cls.authorization)

    def run_gate(self, client: FakeClient) -> dict[str, object]:
        return run_feature_coverage_diagnostic(
            self.contract,
            self.intj_success,
            self.eqpt_success,
            self.repair_contract,
            self.authorization,
            client,
            generated_at=GENERATED_AT,
            sdk_version=SDK_VERSION,
            runtime=RUNTIME,
        )

    def test_contract_is_hash_bound_to_verified_parents_and_unarmed(self):
        self.assertEqual(self.contract["content_sha256"], CONTRACT_CONTENT_SHA256)
        unsigned = {
            key: value
            for key, value in self.contract.items()
            if key != "content_sha256"
        }
        self.assertEqual(canonical_fingerprint(unsigned), CONTRACT_CONTENT_SHA256)
        self.assertEqual(
            self.contract["published_checkpoint"]["commit_sha"],
            "a8e683465ac680ea233414455f8da568e0e6656c",
        )
        self.assertFalse(self.contract["provider_purchase_authorized"])
        self.assertFalse(self.contract["execution_authorization_file_present"])
        if FUTURE_AUTHORIZATION.exists():
            validate_execution_authorization(
                json.loads(FUTURE_AUTHORIZATION.read_text(encoding="utf-8"))
            )

    def test_exact_amc_gmm_order_caps_and_prior_quote_evidence_are_frozen(self):
        self.assertEqual(
            CASE_KEYS,
            (("2026-07-20", "AMC"), ("2026-07-10", "GMM")),
        )
        self.assertEqual(len(REQUESTS), 2)
        self.assertTrue(all(request.schema == "mbo" for request in REQUESTS))
        gate = self.contract["future_execution_gate"]
        self.assertEqual(gate["exact_request_count_authorized"], 0)
        self.assertEqual(gate["hard_preflight_cost_ceiling_usd"], "0.07")
        self.assertEqual(
            gate["hard_preflight_billable_size_ceiling_bytes"],
            65_000_000,
        )
        evidence = self.contract["prior_preflight_evidence"]
        self.assertEqual(evidence["derived_amc_gmm_quoted_cost_usd"], "0.069315630197")
        self.assertEqual(evidence["derived_amc_gmm_billable_size_bytes"], 62_022_576)

    def test_frozen_repair_and_feature_engine_hashes_are_unchanged(self):
        self.assertEqual(
            hashlib.sha256(REPAIR_SOURCE.read_bytes()).hexdigest(),
            coverage.REPAIR_SOURCE_FILE_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(FEATURE_ENGINE.read_bytes()).hexdigest(),
            coverage.FEATURE_ENGINE_SOURCE_FILE_SHA256,
        )

    def test_price_mismatch_replays_under_registered_repair_without_thresholds(self):
        records = _price_mismatch_records()
        groups = list(coverage.eqpt.v03.iter_instrument_mbo_events(records, runtime=RUNTIME))
        with self.assertRaises(SafeDiagnosticFailure) as caught:
            coverage.eqpt.v03.translate_xnas_instrument_event(
                groups[1],
                symbol=REQUESTS[0].symbol,
                runtime=RUNTIME,
            )
        self.assertEqual(caught.exception.code, "fill_cancel_unmatched")
        metrics = extract_case_feature_diagnostic(
            records,
            request=REQUESTS[0],
            runtime=RUNTIME,
        )
        self.assertEqual(metrics["matched_executed_removal_count"], 1)
        self.assertEqual(metrics["ignored_fill_marker_count"], 1)
        self.assertGreater(metrics["sampled_snapshot_count"], 0)
        self.assertTrue(metrics["independent_feature_replay_exact"])
        self.assertFalse(metrics["feature_threshold_selected"])
        self.assertFalse(metrics["feature_horizon_selected"])

    def test_two_request_replay_is_ordered_exact_and_sanitized(self):
        client = FakeClient()
        report = self.run_gate(client)
        validate_coverage_report(report)
        self.assertEqual(len(client.metadata.calls), 4)
        self.assertEqual(len(client.timeseries.calls), 2)
        self.assertEqual(report["timeseries_request_count"], 2)
        self.assertTrue(report["diagnostic_observation_complete"])
        self.assertTrue(report["all_cases_succeeded"])
        self.assertFalse(report["safe_failure_classified"])
        self.assertEqual(
            [(row["trading_date"], row["symbol"]) for row in report["downloads"]],
            list(CASE_KEYS),
        )
        for row in report["downloads"]:
            metrics = row["metrics"]
            self.assertTrue(metrics["independent_feature_replay_exact"])
            self.assertFalse(metrics["feature_threshold_selected"])
            self.assertFalse(metrics["runtime_authority_created"])
        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn("licensed provider detail", rendered)
        self.assertNotIn("feature_snapshots", rendered)
        self.assertNotIn(".dbn", rendered)

    def test_aggregate_budget_rejection_makes_zero_timeseries_calls(self):
        client = FakeClient(cost=0.036)
        report = self.run_gate(client)
        validate_coverage_report(report)
        self.assertEqual(len(client.metadata.calls), 4)
        self.assertEqual(client.timeseries.calls, [])
        self.assertFalse(report["preflight"]["preflight_passed"])
        self.assertEqual(
            report["errors"][0]["safe_error_code"],
            "preflight_budget_rejected",
        )

    def test_first_provider_failure_stops_without_retry(self):
        client = FakeClient(fail_at=0)
        report = self.run_gate(client)
        validate_coverage_report(report)
        self.assertEqual(len(client.timeseries.calls), 1)
        self.assertEqual(report["timeseries_request_count"], 1)
        self.assertEqual(report["downloads"], [])
        self.assertEqual(report["errors"][0]["symbol"], "AMC")
        self.assertTrue(report["safe_failure_classified"])
        self.assertFalse(report["automatic_retry_attempted"])

    def test_second_provider_failure_preserves_amc_and_stops_without_retry(self):
        client = FakeClient(fail_at=1)
        report = self.run_gate(client)
        validate_coverage_report(report)
        self.assertEqual(len(client.timeseries.calls), 2)
        self.assertEqual(report["timeseries_request_count"], 2)
        self.assertEqual(len(report["downloads"]), 1)
        self.assertEqual(report["downloads"][0]["symbol"], "AMC")
        self.assertEqual(report["errors"][0]["symbol"], "GMM")
        self.assertFalse(report["automatic_retry_attempted"])

    def test_authorization_overclaim_fails_closed(self):
        changed = copy.deepcopy(self.authorization)
        changed["exact_request_count_authorized"] = 3
        changed["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in changed.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "request_count"):
            validate_execution_authorization(changed)

    def test_runner_rejects_absent_authorization_before_sdk_import(self):
        imported = []
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            imported.append(name)
            if name == "databento" or name.startswith("databento."):
                raise AssertionError("provider SDK imported before authorization")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=guarded_import):
            with self.assertRaisesRegex(ValueError, "authorization file is required"):
                runner.main(
                    [
                        "--authorization",
                        str(ROOT / "missing-feature-coverage-v02-authorization.json"),
                        "--output",
                        str(ROOT / "unused-feature-coverage-v02-report.json"),
                    ]
                )
        self.assertFalse(any(name == "databento" for name in imported))

    def test_workflow_is_disjoint_parent_bound_and_first_attempt_only(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        script = SCRIPT.read_text(encoding="utf-8")
        trigger = workflow.split("permissions:", 1)[0]
        self.assertIn(
            "databento-microstructure-feature-coverage-v0.2-execution.json",
            trigger,
        )
        self.assertNotIn(
            "databento-microstructure-feature-coverage-v0.2.json",
            trigger,
        )
        self.assertNotIn("workflow_dispatch", workflow)
        self.assertNotIn("*.dbn", workflow)
        self.assertNotIn("batch.submit_job", workflow)
        self.assertNotIn("live.subscribe", workflow)
        self.assertIn("databento==0.83.0", workflow)
        self.assertIn('run_attempt = os.getenv("GITHUB_RUN_ATTEMPT")', script)
        self.assertIn('authorization["authorized_push_parent_sha"]', script)

    def test_registration_audit_binds_unarmed_bundle(self):
        audit = json.loads(REGISTRATION_AUDIT.read_text(encoding="utf-8"))
        claimed = audit["content_sha256"]
        unsigned = {
            key: value for key, value in audit.items() if key != "content_sha256"
        }
        self.assertEqual(canonical_fingerprint(unsigned), claimed)
        self.assertEqual(audit["contract"]["content_sha256"], CONTRACT_CONTENT_SHA256)
        for row in audit["bound_files"]:
            self.assertEqual(
                hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest(),
                row["file_sha256"],
            )
        status = audit["execution_status"]
        self.assertFalse(status["execution_authorization_present"])
        self.assertFalse(status["provider_call_run"])
        self.assertFalse(status["databento_credit_used"])

    def test_contract_and_reports_exclude_retrospective_authority_inputs(self):
        prohibited = json.dumps(self.contract, sort_keys=True).lower()
        self.assertIn("ross action", prohibited)
        self.assertIn("trade p&l", prohibited)
        report = self.run_gate(FakeClient())
        validate_coverage_report(report)
        keys = set(coverage._walk_keys(report))
        self.assertFalse(
            keys
            & {
                "ross_action",
                "ross_label",
                "pnl",
                "later_price",
                "feature_snapshots",
                "order_id",
            }
        )


if __name__ == "__main__":
    unittest.main()
