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

from scripts import run_databento_fill_cancel_repaired_feature_v01 as runner

from momentumbot.research import databento_fill_cancel_repaired_feature_v01 as repaired
from momentumbot.research.databento_fill_cancel_repair_v01 import (
    load_parent_success_audit,
    load_repair_contract,
)
from momentumbot.research.databento_fill_cancel_repaired_feature_v01 import (
    CONTRACT_CONTENT_SHA256,
    DIAGNOSTIC_CONTRACT_ID,
    EXECUTION_AUTHORIZATION_ID,
    REQUEST,
    extract_repaired_feature_diagnostic,
    load_diagnostic_contract,
    run_repaired_feature_diagnostic,
    validate_execution_authorization,
    validate_repaired_feature_report,
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
    / "databento-microstructure-fill-cancel-repaired-feature-v0.1.json"
)
PARENT_SUCCESS = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-fill-cancel-classifier-v0.1-"
    "run-32512602607-success-2026-08-21.json"
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
    / "databento-microstructure-fill-cancel-repaired-feature-v0.1-execution.json"
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
    / "databento-fill-cancel-repaired-feature-v01.yml"
)
SCRIPT = ROOT / "scripts" / "run_databento_fill_cancel_repaired_feature_v01.py"
REGISTRATION_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-fill-cancel-repaired-feature-v0.1-"
    "registration-2026-08-21.json"
)
GENERATED_AT = datetime(2026, 8, 21, 19, tzinfo=UTC)


def _authorization() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "execution_authorization_id": EXECUTION_AUTHORIZATION_ID,
        "artifact_type": (
            "explicit_one_shot_databento_eqpt_repaired_feature_authorization"
        ),
        "diagnostic_contract_id": DIAGNOSTIC_CONTRACT_ID,
        "diagnostic_contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "authorized_push_parent_sha": "a" * 40,
        "explicit_user_authorization": (
            "Synthetic deterministic unit-test authorization; no provider call."
        ),
        "provider_purchase_authorized": True,
        "exact_request_count_authorized": 1,
        "hard_preflight_cost_ceiling_usd": "0.003",
        "hard_preflight_billable_size_ceiling_bytes": 3_000_000,
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
    def __init__(self, *, cost: float = 0.0027, size: int = 2_500_000) -> None:
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
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, object]] = []

    def get_range(self, **kwargs: object) -> FakeStore:
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("licensed provider detail must not persist")
        Path(str(kwargs["path"])).write_bytes(b"synthetic DBN placeholder")
        return FakeStore(_price_mismatch_records())


class FakeClient:
    def __init__(
        self,
        *,
        cost: float = 0.0027,
        size: int = 2_500_000,
        fail: bool = False,
    ) -> None:
        self.metadata = FakeMetadata(cost=cost, size=size)
        self.timeseries = FakeTimeseries(fail=fail)


class DatabentoFillCancelRepairedFeatureV01Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parent_success = load_parent_success_audit(PARENT_SUCCESS)
        cls.repair_contract = load_repair_contract(
            REPAIR_CONTRACT,
            parent_success_audit=cls.parent_success,
        )
        cls.contract = load_diagnostic_contract(
            CONTRACT,
            parent_success_audit=cls.parent_success,
            repair_contract=cls.repair_contract,
        )
        cls.authorization = _authorization()
        validate_execution_authorization(cls.authorization)

    def run_gate(self, client: FakeClient) -> dict[str, object]:
        return run_repaired_feature_diagnostic(
            self.contract,
            self.parent_success,
            self.repair_contract,
            self.authorization,
            client,
            generated_at=GENERATED_AT,
            sdk_version=SDK_VERSION,
            runtime=RUNTIME,
        )

    def test_contract_is_hash_bound_to_published_repair_and_unarmed(self):
        self.assertEqual(self.contract["content_sha256"], CONTRACT_CONTENT_SHA256)
        unsigned = {
            key: value
            for key, value in self.contract.items()
            if key != "content_sha256"
        }
        self.assertEqual(canonical_fingerprint(unsigned), CONTRACT_CONTENT_SHA256)
        parent = self.contract["frozen_parent_repair"]
        self.assertEqual(
            parent["published_commit_sha"],
            "5db47089adc62a5df46fa85e41f3cc3eb26495c2",
        )
        self.assertFalse(self.contract["provider_purchase_authorized"])
        self.assertFalse(self.contract["execution_authorization_file_present"])
        self.assertFalse(FUTURE_AUTHORIZATION.exists())

    def test_exact_eqpt_request_and_caps_are_frozen(self):
        self.assertEqual(
            (REQUEST.trading_date, REQUEST.symbol),
            ("2026-07-10", "EQPT"),
        )
        self.assertEqual(REQUEST.schema, "mbo")
        gate = self.contract["future_execution_gate"]
        self.assertEqual(gate["exact_request_count_authorized"], 0)
        self.assertEqual(gate["hard_preflight_cost_ceiling_usd"], "0.003")
        self.assertEqual(
            gate["hard_preflight_billable_size_ceiling_bytes"],
            3_000_000,
        )

    def test_frozen_repair_and_feature_engine_hashes_are_unchanged(self):
        self.assertEqual(
            hashlib.sha256(REPAIR_SOURCE.read_bytes()).hexdigest(),
            repaired.REPAIR_SOURCE_FILE_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(FEATURE_ENGINE.read_bytes()).hexdigest(),
            repaired.FEATURE_ENGINE_SOURCE_FILE_SHA256,
        )

    def test_price_mismatch_fails_old_identity_but_replays_under_repair(self):
        records = _price_mismatch_records()
        groups = list(
            repaired.v03.iter_instrument_mbo_events(records, runtime=RUNTIME)
        )
        with self.assertRaises(SafeDiagnosticFailure) as caught:
            repaired.v03.translate_xnas_instrument_event(
                groups[1],
                symbol=REQUEST.symbol,
                runtime=RUNTIME,
            )
        self.assertEqual(caught.exception.code, "fill_cancel_unmatched")
        metrics = extract_repaired_feature_diagnostic(
            records,
            request=REQUEST,
            runtime=RUNTIME,
        )
        self.assertEqual(metrics["matched_executed_removal_count"], 1)
        self.assertEqual(metrics["ignored_fill_marker_count"], 1)
        self.assertGreater(metrics["sampled_snapshot_count"], 0)
        self.assertTrue(metrics["independent_feature_replay_exact"])
        self.assertFalse(metrics["feature_threshold_selected"])

    def test_one_request_replay_is_exact_threshold_free_and_sanitized(self):
        client = FakeClient()
        report = self.run_gate(client)
        validate_repaired_feature_report(report)
        self.assertEqual(len(client.metadata.calls), 2)
        self.assertEqual(len(client.timeseries.calls), 1)
        self.assertEqual(report["timeseries_request_count"], 1)
        self.assertTrue(report["diagnostic_observation_complete"])
        self.assertTrue(report["repaired_feature_replay_succeeded"])
        self.assertFalse(report["safe_failure_classified"])
        metrics = report["download"]["metrics"]
        self.assertTrue(metrics["independent_feature_replay_exact"])
        self.assertFalse(metrics["feature_threshold_selected"])
        self.assertFalse(metrics["feature_horizon_selected"])
        self.assertFalse(metrics["runtime_authority_created"])
        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn("licensed provider detail", rendered)
        self.assertNotIn("feature_snapshots", rendered)
        self.assertNotIn(".dbn", rendered)

    def test_budget_rejection_makes_zero_timeseries_calls(self):
        client = FakeClient(cost=0.0031)
        report = self.run_gate(client)
        validate_repaired_feature_report(report)
        self.assertEqual(len(client.metadata.calls), 2)
        self.assertEqual(client.timeseries.calls, [])
        self.assertFalse(report["preflight"]["preflight_passed"])
        self.assertEqual(
            report["errors"][0]["safe_error_code"],
            "preflight_budget_rejected",
        )

    def test_provider_failure_stops_without_retry(self):
        client = FakeClient(fail=True)
        report = self.run_gate(client)
        validate_repaired_feature_report(report)
        self.assertEqual(len(client.timeseries.calls), 1)
        self.assertEqual(report["timeseries_request_count"], 1)
        self.assertIsNone(report["download"])
        self.assertEqual(
            report["errors"][0]["safe_error_code"],
            "provider_download_failed",
        )
        self.assertTrue(report["safe_failure_classified"])
        self.assertFalse(report["automatic_retry_attempted"])

    def test_authorization_overclaim_fails_closed(self):
        changed = copy.deepcopy(self.authorization)
        changed["exact_request_count_authorized"] = 2
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
                        str(ROOT / "missing-repaired-feature-authorization.json"),
                        "--output",
                        str(ROOT / "unused-repaired-feature-report.json"),
                    ]
                )
        self.assertFalse(any(name == "databento" for name in imported))

    def test_workflow_is_disjoint_from_unarmed_bundle(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        script = SCRIPT.read_text(encoding="utf-8")
        trigger = workflow.split("permissions:", 1)[0]
        self.assertIn(
            "databento-microstructure-fill-cancel-repaired-feature-v0.1-"
            "execution.json",
            trigger,
        )
        self.assertNotIn(
            "databento-microstructure-fill-cancel-repaired-feature-v0.1.json",
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
        status = audit["execution_status"]
        self.assertFalse(status["execution_authorization_present"])
        self.assertFalse(status["provider_call_run"])
        self.assertFalse(status["databento_credit_used"])


if __name__ == "__main__":
    unittest.main()
