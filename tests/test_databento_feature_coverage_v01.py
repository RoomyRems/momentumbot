from __future__ import annotations

import builtins
import copy
import hashlib
import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import run_databento_microstructure_feature_coverage_v01 as runner

from momentumbot.research import databento_feature_coverage_v01 as coverage
from momentumbot.research.databento_feature_coverage_v01 import (
    CASE_KEYS,
    CONTRACT_CONTENT_SHA256,
    COVERAGE_CONTRACT_ID,
    EXECUTION_AUTHORIZATION_ID,
    REQUESTS,
    extract_case_feature_diagnostic,
    load_coverage_contract,
    load_parent_success_audit,
    run_feature_coverage_diagnostic,
    validate_coverage_report,
    validate_execution_authorization,
)
from momentumbot.research.databento_quote import SDK_VERSION
from momentumbot.research.databento_feature_diagnostic_v03 import (
    REQUEST as INTJ_REQUEST,
    extract_repaired_feature_diagnostic,
)
from momentumbot.research.microstructure_contract import canonical_fingerprint
from tests.test_databento_feature_diagnostic_v01 import RUNTIME, _records
from tests.test_databento_feature_diagnostic_v03 import FakeStore


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-feature-coverage-v0.1.json"
)
PARENT_SUCCESS = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-feature-diagnostic-v0.3-"
    "run-32483408413-success-2026-08-21.json"
)
FUTURE_AUTHORIZATION = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-feature-coverage-v0.1-execution.json"
)
V03_REPAIR = (
    ROOT
    / "src"
    / "momentumbot"
    / "research"
    / "databento_feature_diagnostic_v03.py"
)
FEATURE_ENGINE = ROOT / "src" / "momentumbot" / "research" / "microstructure_features.py"
WORKFLOW = (
    ROOT
    / ".github"
    / "workflows"
    / "databento-microstructure-feature-coverage-v01.yml"
)
SCRIPT = ROOT / "scripts" / "run_databento_microstructure_feature_coverage_v01.py"
REGISTRATION_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-feature-coverage-v0.1-registration-2026-08-21.json"
)
ACTIVATION_READINESS_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-feature-coverage-v0.1-activation-readiness-"
    "2026-08-21.json"
)
GENERATED_AT = datetime(2026, 8, 21, 15, tzinfo=UTC)


def _authorization() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "execution_authorization_id": EXECUTION_AUTHORIZATION_ID,
        "artifact_type": (
            "explicit_one_shot_databento_three_case_feature_coverage_authorization"
        ),
        "coverage_contract_id": COVERAGE_CONTRACT_ID,
        "coverage_contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "authorized_push_parent_sha": "a" * 40,
        "explicit_user_authorization": (
            "Synthetic deterministic unit-test authorization; no provider call."
        ),
        "provider_purchase_authorized": True,
        "exact_request_count_authorized": 3,
        "hard_preflight_cost_ceiling_usd": "0.08",
        "hard_preflight_billable_size_ceiling_bytes": 80_000_000,
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


class FakeMetadata:
    def __init__(self, *, cost: float = 0.02, size: int = 20_000_000) -> None:
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
        return FakeStore(_records())


class FakeClient:
    def __init__(
        self,
        *,
        cost: float = 0.02,
        size: int = 20_000_000,
        fail_at: int | None = None,
    ) -> None:
        self.metadata = FakeMetadata(cost=cost, size=size)
        self.timeseries = FakeTimeseries(fail_at=fail_at)


class DatabentoFeatureCoverageV01Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parent_success = load_parent_success_audit(PARENT_SUCCESS)
        cls.contract = load_coverage_contract(
            CONTRACT,
            parent_success_audit=cls.parent_success,
        )
        cls.authorization = _authorization()
        validate_execution_authorization(cls.authorization)

    def run_gate(self, client: FakeClient) -> dict[str, object]:
        return run_feature_coverage_diagnostic(
            self.contract,
            self.parent_success,
            self.authorization,
            client,
            generated_at=GENERATED_AT,
            sdk_version=SDK_VERSION,
            runtime=RUNTIME,
        )

    def test_contract_is_hash_bound_to_verified_parent_and_unarmed(self):
        self.assertEqual(self.contract["content_sha256"], CONTRACT_CONTENT_SHA256)
        self.assertEqual(
            canonical_fingerprint(
                {
                    key: value
                    for key, value in self.contract.items()
                    if key != "content_sha256"
                }
            ),
            CONTRACT_CONTENT_SHA256,
        )
        self.assertFalse(self.contract["provider_purchase_authorized"])
        self.assertFalse(self.contract["execution_authorization_file_present"])
        if FUTURE_AUTHORIZATION.exists():
            future_authorization = coverage.load_execution_authorization(
                FUTURE_AUTHORIZATION
            )
            self.assertTrue(future_authorization["provider_purchase_authorized"])
            self.assertEqual(
                future_authorization["exact_request_count_authorized"],
                3,
            )
        else:
            self.assertFalse(FUTURE_AUTHORIZATION.exists())

    def test_fixed_remaining_case_order_excludes_only_verified_intj(self):
        self.assertEqual(
            CASE_KEYS,
            (
                ("2026-07-10", "EQPT"),
                ("2026-07-20", "AMC"),
                ("2026-07-10", "GMM"),
            ),
        )
        self.assertEqual(len(REQUESTS), 3)
        self.assertNotIn("INTJ", {request.symbol for request in REQUESTS})

    def test_frozen_repair_and_feature_engine_hashes_are_unchanged(self):
        self.assertEqual(
            hashlib.sha256(V03_REPAIR.read_bytes()).hexdigest(),
            coverage.V03_REPAIR_SOURCE_FILE_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(FEATURE_ENGINE.read_bytes()).hexdigest(),
            coverage.FEATURE_ENGINE_SOURCE_FILE_SHA256,
        )

    def test_generalized_case_extractor_is_identical_on_frozen_intj_fixture(self):
        frozen = extract_repaired_feature_diagnostic(
            _records(),
            request=INTJ_REQUEST,
            runtime=RUNTIME,
        )
        generalized = extract_case_feature_diagnostic(
            _records(),
            request=INTJ_REQUEST,
            runtime=RUNTIME,
        )
        self.assertEqual(generalized, frozen)

    def test_three_case_replay_is_exact_threshold_free_and_sanitized(self):
        client = FakeClient()
        report = self.run_gate(client)
        validate_coverage_report(report)
        self.assertEqual(len(client.metadata.calls), 6)
        self.assertEqual(len(client.timeseries.calls), 3)
        self.assertEqual(report["timeseries_request_count"], 3)
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
            self.assertFalse(metrics["feature_horizon_selected"])
            self.assertFalse(metrics["runtime_authority_created"])
        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn("licensed provider detail", rendered)
        self.assertNotIn("feature_snapshots", rendered)
        self.assertNotIn(".dbn", rendered)

    def test_aggregate_budget_rejection_makes_zero_timeseries_calls(self):
        client = FakeClient(cost=0.03, size=20_000_000)
        report = self.run_gate(client)
        validate_coverage_report(report)
        self.assertEqual(len(client.metadata.calls), 6)
        self.assertEqual(client.timeseries.calls, [])
        self.assertFalse(report["preflight"]["preflight_passed"])
        self.assertEqual(report["errors"][0]["safe_error_code"], "preflight_budget_rejected")

    def test_first_provider_failure_stops_without_retry(self):
        client = FakeClient(fail_at=1)
        report = self.run_gate(client)
        validate_coverage_report(report)
        self.assertEqual(len(client.timeseries.calls), 2)
        self.assertEqual(report["timeseries_request_count"], 2)
        self.assertEqual(len(report["downloads"]), 1)
        self.assertEqual(report["downloads"][0]["symbol"], "EQPT")
        self.assertEqual(report["errors"][0]["symbol"], "AMC")
        self.assertEqual(
            report["errors"][0]["safe_error_code"],
            "provider_download_failed",
        )
        self.assertTrue(report["diagnostic_observation_complete"])
        self.assertTrue(report["safe_failure_classified"])
        self.assertFalse(report["automatic_retry_attempted"])

    def test_authorization_overclaim_fails_closed(self):
        changed = copy.deepcopy(self.authorization)
        changed["exact_request_count_authorized"] = 4
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
                        str(ROOT / "missing-feature-coverage-authorization.json"),
                        "--output",
                        str(ROOT / "unused-feature-coverage-report.json"),
                    ]
                )
        self.assertFalse(any(name == "databento" for name in imported))

    def test_workflow_is_disjoint_from_unarmed_bundle(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        script = SCRIPT.read_text(encoding="utf-8")
        trigger = workflow.split("permissions:", 1)[0]
        self.assertIn(
            "databento-microstructure-feature-coverage-v0.1-execution.json",
            trigger,
        )
        self.assertNotIn(
            "databento-microstructure-feature-coverage-v0.1.json",
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
        self.assertEqual(
            audit["contract"]["content_sha256"],
            CONTRACT_CONTENT_SHA256,
        )
        for row in audit["bound_files"]:
            self.assertEqual(
                hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest(),
                row["file_sha256"],
            )
        self.assertFalse(audit["execution_status"]["execution_authorization_present"])
        self.assertFalse(audit["execution_status"]["provider_call_run"])
        self.assertFalse(audit["execution_status"]["databento_credit_used"])

    def test_activation_readiness_audit_binds_corrected_test_harness(self):
        audit = json.loads(
            ACTIVATION_READINESS_AUDIT.read_text(encoding="utf-8")
        )
        claimed = audit["content_sha256"]
        unsigned = {
            key: value for key, value in audit.items() if key != "content_sha256"
        }
        self.assertEqual(canonical_fingerprint(unsigned), claimed)
        self.assertEqual(
            audit["published_parent"]["commit_sha"],
            "4017d02284e87729856633071115ae61ae1f27a5",
        )
        self.assertFalse(
            audit["corrective_scope"]["future_authorization_file_present"]
        )
        self.assertFalse(audit["corrective_scope"]["provider_call_run"])
        self.assertFalse(audit["corrective_scope"]["databento_credit_used"])
        for row in audit["bound_files"]:
            path = ROOT / row["path"]
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                row["file_sha256"],
            )


if __name__ == "__main__":
    unittest.main()
