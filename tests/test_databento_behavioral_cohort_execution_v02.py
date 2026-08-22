from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from momentumbot.research import databento_behavioral_cohort_execution_v01 as v01
from momentumbot.research.databento_behavioral_cohort_execution_v02 import (
    ARTIFACT_TYPE,
    EXECUTION_AUTHORIZATION_ID,
    EXECUTION_CONTRACT_CONTENT_SHA256,
    EXECUTION_CONTRACT_ID,
    PARENT_SAFE_FAILURE_CONTENT_SHA256,
    load_cohort,
    load_execution_contract,
    load_parent_safe_failure,
    load_protocol,
    run_behavioral_cohort_diagnostic,
    validate_behavioral_cohort_report,
    validate_execution_authorization,
    validate_execution_contract,
)
from momentumbot.research.databento_quote import SDK_VERSION
from momentumbot.research.microstructure_contract import (
    canonical_fingerprint,
    file_sha256,
)
from tests.test_databento_behavioral_cohort_execution_v01 import (
    COHORT,
    GENERATED_AT,
    PROTOCOL,
    RUNTIME,
    FakeClient,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT / "research/strategy/databento-microstructure-behavioral-cohort-v0.2.json"
)
PARENT_FAILURE = (
    ROOT
    / "research/data-audits/"
    "databento-microstructure-behavioral-cohort-v0.1-"
    "run-32550318387-safe-failure-2026-08-21.json"
)
FUTURE_AUTHORIZATION = (
    ROOT / "research/strategy/microstructure-behavioral-cohort-v0.2-execution.json"
)
WORKFLOW = (
    ROOT / ".github/workflows/databento-microstructure-behavioral-cohort-v02.yml"
)
SCRIPT = ROOT / "scripts/run_databento_microstructure_behavioral_cohort_v02.py"
REGISTRATION_AUDIT = (
    ROOT
    / "research/data-audits/"
    "databento-microstructure-behavioral-cohort-v0.2-"
    "registration-2026-08-21.json"
)


def _authorization(parent: str = "a" * 40) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "execution_authorization_id": EXECUTION_AUTHORIZATION_ID,
        "artifact_type": (
            "explicit_one_shot_databento_behavioral_cohort_v0.2_authorization"
        ),
        "execution_contract_id": EXECUTION_CONTRACT_ID,
        "execution_contract_content_sha256": EXECUTION_CONTRACT_CONTENT_SHA256,
        "parent_safe_failure_content_sha256": PARENT_SAFE_FAILURE_CONTENT_SHA256,
        "cohort_id": v01.COHORT_ID,
        "cohort_content_sha256": v01.COHORT_CONTENT_SHA256,
        "behavioral_protocol_content_sha256": v01.PROTOCOL_CONTENT_SHA256,
        "authorized_push_parent_sha": parent,
        "explicit_user_authorization": (
            "Synthetic deterministic v0.2 unit-test authorization; no provider call."
        ),
        "provider_purchase_authorized": True,
        "exact_request_count_authorized": 5,
        "hard_preflight_cost_ceiling_usd": "0.25",
        "hard_preflight_billable_size_ceiling_bytes": 225_000_000,
        "all_requests_quoted_before_first_download": True,
        "first_github_actions_attempt_only": True,
        "automatic_retry_authorized": False,
        "partial_cohort_substitution_authorized": False,
        "batch_or_live_endpoint_authorized": False,
        "raw_market_data_publication_authorized": False,
        "feature_value_publication_authorized": False,
        "broker_or_order_change_authorized": False,
        "strategy_or_threshold_change_authorized": False,
    }
    payload["content_sha256"] = canonical_fingerprint(payload)
    return payload


class DatabentoBehavioralCohortExecutionV02Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cohort = load_cohort(COHORT)
        cls.protocol = load_protocol(PROTOCOL)
        cls.contract = load_execution_contract(CONTRACT)
        cls.parent_failure = load_parent_safe_failure(PARENT_FAILURE)
        cls.authorization = _authorization()
        validate_execution_authorization(cls.authorization)

    def run_gate(self, client: FakeClient) -> dict[str, object]:
        return run_behavioral_cohort_diagnostic(
            self.cohort,
            self.protocol,
            self.contract,
            self.parent_failure,
            self.authorization,
            client,
            generated_at=GENERATED_AT,
            sdk_version=SDK_VERSION,
            runtime=RUNTIME,
        )

    def test_contract_is_hash_bound_unarmed_and_future_authorization_is_valid(self):
        self.assertEqual(
            self.contract["content_sha256"], EXECUTION_CONTRACT_CONTENT_SHA256
        )
        self.assertFalse(self.contract["provider_purchase_authorized"])
        self.assertFalse(self.contract["execution_authorization_file_present"])
        gate = self.contract["future_execution_gate"]
        self.assertEqual(gate["exact_request_count_authorized_now"], 0)
        self.assertEqual(gate["provider_cost_authorized_now_usd"], "0")
        self.assertEqual(gate["provider_bytes_authorized_now"], 0)
        if FUTURE_AUTHORIZATION.exists():
            validate_execution_authorization(
                json.loads(FUTURE_AUTHORIZATION.read_text(encoding="utf-8"))
            )

    def test_contract_binds_safe_failure_and_exact_dataframe_repair(self):
        self.assertEqual(
            self.parent_failure["content_sha256"],
            PARENT_SAFE_FAILURE_CONTENT_SHA256,
        )
        self.assertEqual(
            self.contract["registered_dataframe_repair"]["keyword_arguments"],
            {
                "map_symbols": True,
                "pretty_ts": False,
                "price_type": "fixed",
            },
        )
        self.assertEqual(
            self.contract["frozen_parent_failure"]["workflow_run_id"], 32550318387
        )
        self.assertEqual(
            file_sha256(
                ROOT
                / self.contract["frozen_inputs"]["cohort_execution_source_path"]
            ),
            self.contract["frozen_inputs"]["cohort_execution_source_file_sha256"],
        )

    def test_contract_and_authorization_drift_fail_closed(self):
        contract = copy.deepcopy(self.contract)
        contract["registered_dataframe_repair"]["keyword_arguments"][
            "price_type"
        ] = "float"
        contract["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in contract.items() if key != "content_sha256"}
        )
        with self.assertRaises(ValueError):
            validate_execution_contract(contract)
        for field, value in (
            ("exact_request_count_authorized", 4),
            ("hard_preflight_cost_ceiling_usd", "0.26"),
            ("automatic_retry_authorized", True),
            ("execution_contract_content_sha256", "0" * 64),
        ):
            authorization = copy.deepcopy(self.authorization)
            authorization[field] = value
            authorization["content_sha256"] = canonical_fingerprint(
                {
                    key: item
                    for key, item in authorization.items()
                    if key != "content_sha256"
                }
            )
            with self.assertRaises(ValueError):
                validate_execution_authorization(authorization)

    def test_repaired_success_delegates_exactly_and_versions_report(self):
        client = FakeClient(self.cohort["opportunities"])
        report = self.run_gate(client)
        validate_behavioral_cohort_report(report)
        self.assertEqual(report["artifact_type"], ARTIFACT_TYPE)
        self.assertEqual(report["execution_contract_id"], EXECUTION_CONTRACT_ID)
        self.assertEqual(len(client.metadata.calls), 10)
        self.assertEqual(len(client.timeseries.calls), 5)
        self.assertEqual(len(client.timeseries.stores), 5)
        for store in client.timeseries.stores:
            self.assertEqual(
                store.to_df_calls,
                [{
                    "map_symbols": True,
                    "pretty_ts": False,
                    "price_type": "fixed",
                }],
            )
        self.assertTrue(report["all_requests_succeeded"])
        self.assertEqual(report["cohort_aggregate"]["opportunity_count"], 10)
        self.assertTrue(
            report["cohort_aggregate"]["independent_feature_replay_exact"]
        )

    def test_budget_rejection_makes_zero_timeseries_calls(self):
        client = FakeClient(self.cohort["opportunities"], cost=0.051)
        report = self.run_gate(client)
        validate_behavioral_cohort_report(report)
        self.assertEqual(len(client.metadata.calls), 10)
        self.assertEqual(client.timeseries.calls, [])
        self.assertEqual(
            report["errors"][0]["safe_error_code"], "preflight_budget_rejected"
        )

    def test_first_provider_failure_stops_without_retry(self):
        client = FakeClient(self.cohort["opportunities"], fail_at=0)
        report = self.run_gate(client)
        validate_behavioral_cohort_report(report)
        self.assertEqual(len(client.timeseries.calls), 1)
        self.assertEqual(report["downloads"], [])
        self.assertFalse(report["automatic_retry_attempted"])
        self.assertFalse(report["partial_cohort_substitution_attempted"])

    def test_consumed_v01_authorization_cannot_validate_as_v02(self):
        with self.assertRaises(ValueError):
            validate_execution_authorization(
                json.loads(
                    (
                        ROOT
                        / "research/strategy/"
                        "microstructure-behavioral-cohort-v0.1-execution.json"
                    ).read_text(encoding="utf-8")
                )
            )

    def test_workflow_is_v02_authorization_only_first_attempt_and_pinned(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("microstructure-behavioral-cohort-v0.2-execution.json", workflow)
        self.assertNotIn("microstructure-behavioral-cohort-v0.1-execution.json", workflow)
        self.assertIn("assert changed == [expected]", workflow)
        self.assertIn("assert parent == before", workflow)
        self.assertIn("databento==0.83.0", workflow)
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("GITHUB_RUN_ATTEMPT", script)
        self.assertIn("load_execution_contract", script)
        self.assertIn("load_parent_safe_failure", script)

    def test_registration_audit_binds_unarmed_v02_files(self):
        audit = json.loads(REGISTRATION_AUDIT.read_text(encoding="utf-8"))
        self.assertFalse(audit["provider_request_made"])
        self.assertFalse(audit["provider_quote_made"])
        self.assertFalse(audit["execution_authorization_file_present"])
        for bound in audit["bound_files"]:
            self.assertEqual(file_sha256(ROOT / bound["path"]), bound["file_sha256"])
        unsigned = {key: value for key, value in audit.items() if key != "content_sha256"}
        self.assertEqual(canonical_fingerprint(unsigned), audit["content_sha256"])


if __name__ == "__main__":
    unittest.main()
