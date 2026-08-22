import json
import unittest
from pathlib import Path

from momentumbot.research.databento_feature_coverage_v02 import (
    CONTRACT_CONTENT_SHA256,
    canonical_fingerprint,
)


ROOT = Path(__file__).resolve().parents[1]
SUCCESS_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-feature-coverage-v0.2-run-32544425875-"
    "success-2026-08-21.json"
)


class DatabentoFeatureCoverageV02SuccessAuditTests(unittest.TestCase):
    def test_permanent_success_audit_binds_verified_four_case_coverage(self):
        audit = json.loads(SUCCESS_AUDIT.read_text(encoding="utf-8"))
        claimed = audit["content_sha256"]
        unsigned = {
            key: value for key, value in audit.items() if key != "content_sha256"
        }
        self.assertEqual(canonical_fingerprint(unsigned), claimed)
        self.assertEqual(
            audit["contract"]["content_sha256"],
            CONTRACT_CONTENT_SHA256,
        )
        self.assertEqual(
            audit["github_actions"]["workflow_head_sha"],
            "1f6407508a30b507754eb9ccaf7516e4398d6a7e",
        )
        self.assertEqual(
            audit["verified_preflight_and_attempt"]["timeseries_request_count"],
            2,
        )
        self.assertEqual(
            [row["symbol"] for row in audit["verified_cases"]],
            ["AMC", "GMM"],
        )
        self.assertTrue(
            all(
                row["independent_feature_replay_exact"]
                and not row["feature_threshold_selected"]
                and not row["runtime_authority_created"]
                for row in audit["verified_cases"]
            )
        )
        safety = audit["safety_verification"]
        self.assertTrue(safety["sanitized_report_validator_passed"])
        self.assertFalse(safety["raw_market_data_persisted"])
        self.assertFalse(safety["strategy_or_threshold_change_made"])


if __name__ == "__main__":
    unittest.main()
