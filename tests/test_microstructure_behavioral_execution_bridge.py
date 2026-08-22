import copy
import hashlib
import json
import unittest
from pathlib import Path

from momentumbot.research.microstructure_behavioral_execution_bridge import (
    BEHAVIORAL_SUCCESS_AUDIT_CONTENT_SHA256,
    CONTRACT_CONTENT_SHA256,
    EXECUTION_SCENARIO_IDS,
    HORIZONS_NS,
    PENDING_EXECUTION_STATUS,
    build_behavioral_execution_bridge,
    load_behavioral_success_audit,
    load_bridge_contract,
    load_prospective_contract,
    validate_bridge_contract,
)
from momentumbot.research.microstructure_contract import canonical_fingerprint


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "microstructure-behavioral-execution-bridge-v0.1.json"
)
SUCCESS_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-behavioral-cohort-v0.2-run-32575593240-"
    "success-2026-08-22.json"
)
PROSPECTIVE_CONTRACT = (
    ROOT / "research" / "strategy" / "prospective-management-execution-v0.1.json"
)
REGISTRATION_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "microstructure-behavioral-execution-bridge-v0.1-registration-"
    "2026-08-22.json"
)


class MicrostructureBehavioralExecutionBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load_bridge_contract(CONTRACT)
        cls.success = load_behavioral_success_audit(SUCCESS_AUDIT)
        cls.prospective = load_prospective_contract(PROSPECTIVE_CONTRACT)

    def test_contract_binds_success_and_remains_unarmed(self):
        self.assertEqual(self.contract["content_sha256"], CONTRACT_CONTENT_SHA256)
        self.assertEqual(
            self.contract["frozen_parents"][
                "behavioral_success_audit_content_sha256"
            ],
            BEHAVIORAL_SUCCESS_AUDIT_CONTENT_SHA256,
        )
        authority = self.contract["authority_boundary"]
        self.assertFalse(authority["provider_request_authorized"])
        self.assertEqual(authority["databento_credit_authorized_usd"], "0")
        self.assertFalse(authority["paper_order_authorized"])
        self.assertFalse(authority["runtime_authority_created"])
        self.assertFalse(authority["policy_promotion_eligible"])

    def test_bridge_reports_complete_six_cell_pending_matrix(self):
        report = build_behavioral_execution_bridge(
            self.contract,
            self.success,
            self.prospective,
        )
        matrix = report["matrix"]
        self.assertEqual(matrix["horizons_ns"], list(HORIZONS_NS))
        self.assertEqual(
            matrix["execution_scenario_ids"],
            list(EXECUTION_SCENARIO_IDS),
        )
        self.assertEqual(matrix["cell_count"], 6)
        self.assertEqual(
            [
                (cell["horizon_ns"], cell["execution_scenario_id"])
                for cell in matrix["cells"]
            ],
            [
                (horizon, scenario)
                for horizon in HORIZONS_NS
                for scenario in EXECUTION_SCENARIO_IDS
            ],
        )
        self.assertTrue(
            all(
                cell["prospective_execution_status"] == PENDING_EXECUTION_STATUS
                and not cell["comparable_execution_outcome_available"]
                for cell in matrix["cells"]
            )
        )
        self.assertFalse(report["provider_request_made"])
        self.assertFalse(report["broker_order_submitted"])
        self.assertFalse(report["threshold_or_score_applied"])
        self.assertFalse(report["horizon_or_scenario_selected"])
        claimed = report.pop("content_sha256")
        self.assertEqual(canonical_fingerprint(report), claimed)

    def test_each_scenario_reuses_the_same_aggregate_for_each_horizon(self):
        report = build_behavioral_execution_bridge(
            self.contract,
            self.success,
            self.prospective,
        )
        cells = report["matrix"]["cells"]
        for horizon in HORIZONS_NS:
            pair = [cell for cell in cells if cell["horizon_ns"] == horizon]
            self.assertEqual(len(pair), 2)
            self.assertEqual(
                pair[0]["behavioral_metric_direction_totals"],
                pair[1]["behavioral_metric_direction_totals"],
            )
            self.assertEqual(
                pair[0]["behavioral_depth_walk_direction_totals"],
                pair[1]["behavioral_depth_walk_direction_totals"],
            )

    def test_contract_mutation_cannot_enable_selection_or_authority(self):
        raw = json.loads(CONTRACT.read_text(encoding="utf-8"))
        mutations = (
            ("readiness_matrix", "best_horizon_selection_allowed", True),
            ("readiness_matrix", "score_or_rank_allowed", True),
            ("authority_boundary", "provider_request_authorized", True),
            ("authority_boundary", "paper_order_authorized", True),
            ("knowledge_boundary", "later_prices_or_pnl_allowed", True),
        )
        for section, field, value in mutations:
            changed = copy.deepcopy(raw)
            changed[section][field] = value
            unsigned = {
                key: item for key, item in changed.items() if key != "content_sha256"
            }
            changed["content_sha256"] = canonical_fingerprint(unsigned)
            with self.assertRaises(ValueError):
                validate_bridge_contract(changed)

    def test_registration_audit_is_hash_bound_and_provider_inert(self):
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
        self.assertFalse(audit["authority_boundary"]["provider_request_made"])
        self.assertFalse(audit["authority_boundary"]["broker_order_submitted"])
        self.assertFalse(audit["authority_boundary"]["runtime_authority_created"])


if __name__ == "__main__":
    unittest.main()
