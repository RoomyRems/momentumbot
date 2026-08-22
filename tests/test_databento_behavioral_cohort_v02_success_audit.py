import json
import unittest
from pathlib import Path

from momentumbot.research.databento_behavioral_cohort_execution_v02 import (
    EXECUTION_CONTRACT_CONTENT_SHA256,
)
from momentumbot.research.microstructure_contract import canonical_fingerprint


ROOT = Path(__file__).resolve().parents[1]
SUCCESS_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-behavioral-cohort-v0.2-run-32575593240-"
    "success-2026-08-22.json"
)


class DatabentoBehavioralCohortV02SuccessAuditTests(unittest.TestCase):
    def test_permanent_success_audit_binds_consumed_first_attempt(self):
        audit = json.loads(SUCCESS_AUDIT.read_text(encoding="utf-8"))
        claimed = audit["content_sha256"]
        unsigned = {
            key: value for key, value in audit.items() if key != "content_sha256"
        }
        self.assertEqual(canonical_fingerprint(unsigned), claimed)
        self.assertEqual(
            audit["contract"]["execution_contract_content_sha256"],
            EXECUTION_CONTRACT_CONTENT_SHA256,
        )
        actions = audit["github_actions"]
        self.assertEqual(actions["workflow_run_id"], 32575593240)
        self.assertEqual(actions["workflow_run_attempt"], 1)
        self.assertEqual(
            actions["workflow_head_sha"],
            "0687093a778bd6ac0973889e788886df8cd48cbf",
        )
        self.assertEqual(
            actions["workflow_parent_sha"],
            audit["contract"]["authorized_push_parent_sha"],
        )

    def test_success_is_complete_exact_and_not_a_policy_promotion(self):
        audit = json.loads(SUCCESS_AUDIT.read_text(encoding="utf-8"))
        attempt = audit["verified_preflight_and_attempt"]
        self.assertTrue(attempt["preflight_passed"])
        self.assertEqual(attempt["request_count_expected"], 5)
        self.assertEqual(attempt["request_count_quoted"], 5)
        self.assertEqual(attempt["timeseries_request_count"], 5)
        self.assertEqual(attempt["successful_download_summary_count"], 5)
        self.assertFalse(attempt["automatic_retry_attempted"])
        self.assertTrue(attempt["first_attempt_only_observed"])
        self.assertTrue(
            all(
                row["independent_feature_replay_exact"]
                for row in audit["verified_downloads"]
            )
        )
        aggregate = audit["verified_cohort_aggregate"]
        self.assertEqual(aggregate["opportunity_count"], 10)
        self.assertEqual(aggregate["horizon_count"], 3)
        self.assertTrue(aggregate["all_horizons_reported_together"])
        self.assertTrue(aggregate["independent_feature_replay_exact"])
        self.assertFalse(aggregate["feature_horizon_selected"])
        self.assertFalse(aggregate["feature_threshold_selected"])
        self.assertFalse(aggregate["policy_promotion_eligible"])

    def test_sanitization_and_causality_guards_remained_closed(self):
        audit = json.loads(SUCCESS_AUDIT.read_text(encoding="utf-8"))
        safety = audit["safety_verification"]
        self.assertTrue(safety["sanitized_report_validator_passed"])
        self.assertTrue(safety["raw_temp_directory_removed"])
        self.assertFalse(safety["raw_market_data_persisted"])
        self.assertFalse(safety["retrospective_labels_loaded"])
        self.assertFalse(safety["ross_actions_or_labels_loaded"])
        self.assertFalse(safety["pnl_or_later_prices_loaded"])
        self.assertFalse(safety["per_opportunity_feature_values_persisted"])
        self.assertFalse(safety["runtime_authority_created"])
        self.assertFalse(safety["strategy_or_threshold_change_made"])


if __name__ == "__main__":
    unittest.main()
