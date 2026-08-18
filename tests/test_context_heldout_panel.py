import copy
import hashlib
import json
import unittest
from pathlib import Path

from momentumbot.research.context_heldout_panel import (
    CONTRACT_ID,
    EXCLUDED_PILOT_COMPARISON_SHA256,
    PRIOR_REVIEW_CUTOFF,
    REGISTERED_DATES,
    canonical_fingerprint,
    load_context_heldout_panel_contract,
    validate_context_heldout_panel_contract,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research" / "strategy" / "context-heldout-panel-v0.1.json"
AUDIT = ROOT / "research" / "data-audits" / "context-heldout-panel-v0.1.json"


class ContextHeldoutPanelTests(unittest.TestCase):
    def setUp(self):
        self.payload = load_context_heldout_panel_contract(CONTRACT)

    def test_dates_are_next_ten_calendar_only_sessions(self):
        self.assertEqual(self.payload["contract_id"], CONTRACT_ID)
        self.assertEqual(
            REGISTERED_DATES,
            (
                "2026-07-24",
                "2026-07-27",
                "2026-07-28",
                "2026-07-29",
                "2026-07-30",
                "2026-07-31",
                "2026-08-03",
                "2026-08-04",
                "2026-08-05",
                "2026-08-06",
            ),
        )
        self.assertTrue(all(value > PRIOR_REVIEW_CUTOFF.isoformat() for value in REGISTERED_DATES))
        sampling = self.payload["sampling_contract"]
        self.assertFalse(sampling["date_selection_uses_source_inventory"])
        self.assertFalse(sampling["date_selection_uses_source_content"])
        self.assertFalse(sampling["date_selection_uses_symbols"])
        self.assertFalse(sampling["date_selection_uses_ross_actions"])
        self.assertFalse(self.payload["source_inventory_started"])
        self.assertFalse(self.payload["label_content_review_started"])

    def test_dates_cannot_be_replaced_after_registration(self):
        changed = copy.deepcopy(self.payload)
        changed["sampling_contract"]["registered_dates"][-1] = "2026-08-07"
        with self.assertRaisesRegex(ValueError, "registered_dates differs"):
            validate_context_heldout_panel_contract(changed)

        changed = copy.deepcopy(self.payload)
        changed["dates_may_be_replaced"] = True
        with self.assertRaisesRegex(ValueError, "dates_may_be_replaced must be false"):
            validate_context_heldout_panel_contract(changed)

    def test_source_or_behavior_information_cannot_enter_registration(self):
        for key, value in (
            ("source_id", "youtube:future"),
            ("ross_action", "participated"),
            ("reported_fill", 5.25),
            ("trade_outcome", "winner"),
        ):
            changed = copy.deepcopy(self.payload)
            changed["sampling_contract"][key] = value
            with self.assertRaisesRegex(ValueError, "source or retrospective keys"):
                validate_context_heldout_panel_contract(changed)

    def test_missing_source_date_cannot_be_substituted_or_called_skip(self):
        changed = copy.deepcopy(self.payload)
        changed["sampling_contract"]["missing_source_date_replaced"] = True
        with self.assertRaisesRegex(ValueError, "missing_source_date_replaced"):
            validate_context_heldout_panel_contract(changed)

        changed = copy.deepcopy(self.payload)
        changed["human_evidence_policy"]["source_unavailable_counts_as_skip"] = True
        with self.assertRaisesRegex(ValueError, "source_unavailable_counts_as_skip"):
            validate_context_heldout_panel_contract(changed)

    def test_reviewed_pilot_is_excluded_from_fit_and_evaluation(self):
        excluded = self.payload["excluded_fit_evidence"]
        self.assertEqual(
            excluded["comparison_content_sha256"],
            EXCLUDED_PILOT_COMPARISON_SHA256,
        )
        self.assertFalse(excluded["threshold_fit_allowed"])
        self.assertFalse(excluded["protocol_evaluation_allowed"])
        self.assertFalse(
            self.payload["evaluation_contract"][
                "component_thresholds_may_be_fit_on_panel"
            ]
        )
        self.assertFalse(
            self.payload["evaluation_contract"]["policy_promotion_allowed"]
        )

    def test_registration_has_no_runtime_or_semantic_result(self):
        status = self.payload["execution_status"]
        self.assertEqual(status["deterministic_runtime"], "not_started")
        self.assertEqual(status["semantic_shadow"], "not_started")
        self.assertEqual(status["source_inventory"], "not_started")
        self.assertEqual(status["human_label_review"], "not_started")
        self.assertIsNone(status["runtime_artifact_sha256"])
        self.assertIsNone(status["semantic_shadow_artifact_sha256"])
        self.assertIsNone(status["label_artifact_sha256"])

    def test_registration_audit_binds_exact_contract(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(audit["contract_id"], CONTRACT_ID)
        self.assertEqual(
            audit["contract_file_sha256"],
            hashlib.sha256(CONTRACT.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            audit["contract_content_sha256"],
            canonical_fingerprint(self.payload),
        )
        self.assertFalse(audit["decision"]["start_source_inventory"])
        self.assertFalse(audit["decision"]["start_human_label_review"])
        self.assertFalse(audit["policy_promotion_eligible"])


if __name__ == "__main__":
    unittest.main()
