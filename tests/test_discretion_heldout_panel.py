import copy
import hashlib
import json
import unittest
from pathlib import Path

from momentumbot.research.discretion_heldout_panel import (
    CONTRACT_ID,
    DEVELOPMENT_EVIDENCE_CUTOFF,
    REGISTERED_DATES,
    canonical_fingerprint,
    load_discretion_heldout_panel_contract,
    validate_discretion_heldout_panel_contract,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research" / "strategy" / "discretion-heldout-panel-v0.1.json"
AUDIT = ROOT / "research" / "data-audits" / "discretion-heldout-panel-v0.1.json"


class DiscretionHeldoutPanelTests(unittest.TestCase):
    def setUp(self):
        self.payload = load_discretion_heldout_panel_contract(CONTRACT)

    def test_registration_is_chronological_unlabeled_and_disjoint(self):
        self.assertEqual(self.payload["contract_id"], CONTRACT_ID)
        sampling = self.payload["sampling_contract"]
        self.assertEqual(tuple(sampling["registered_dates"]), REGISTERED_DATES)
        self.assertTrue(
            all(item > DEVELOPMENT_EVIDENCE_CUTOFF.isoformat() for item in REGISTERED_DATES)
        )
        self.assertTrue(
            set(sampling["registered_dates"]).isdisjoint(
                sampling["development_benchmark_dates"]
            )
        )
        self.assertFalse(self.payload["label_content_review_started"])
        self.assertEqual(self.payload["execution_status"]["runtime_replay"], "not_started")

    def test_a_known_trade_or_fill_label_cannot_enter_registration(self):
        changed = copy.deepcopy(self.payload)
        changed["sampling_contract"]["ross_action"] = "participated"
        with self.assertRaisesRegex(ValueError, "retrospective label keys"):
            validate_discretion_heldout_panel_contract(changed)

        changed = copy.deepcopy(self.payload)
        changed["entry_price"] = 6.34
        with self.assertRaisesRegex(ValueError, "retrospective label keys"):
            validate_discretion_heldout_panel_contract(changed)

    def test_fixed_dates_cannot_be_swapped_after_source_review(self):
        changed = copy.deepcopy(self.payload)
        changed["sampling_contract"]["registered_dates"][-1] = "2026-07-24"
        with self.assertRaisesRegex(ValueError, "registered_dates differs"):
            validate_discretion_heldout_panel_contract(changed)

        changed = copy.deepcopy(self.payload)
        changed["dates_may_be_replaced"] = True
        with self.assertRaisesRegex(ValueError, "dates_may_be_replaced must be false"):
            validate_discretion_heldout_panel_contract(changed)

    def test_unknown_or_missing_source_cannot_be_relabeled_as_skip(self):
        changed = copy.deepcopy(self.payload)
        changed["human_evidence_policy"]["not_mentioned_counts_as_skip"] = True
        with self.assertRaisesRegex(ValueError, "not_mentioned_counts_as_skip must be False"):
            validate_discretion_heldout_panel_contract(changed)

        changed = copy.deepcopy(self.payload)
        changed["human_evidence_policy"]["source_unavailable_counts_as_skip"] = True
        with self.assertRaisesRegex(ValueError, "source_unavailable_counts_as_skip must be False"):
            validate_discretion_heldout_panel_contract(changed)

    def test_account_scopes_must_remain_separate(self):
        changed = copy.deepcopy(self.payload)
        changed["human_evidence_policy"]["small_and_main_accounts_may_be_merged"] = True
        with self.assertRaisesRegex(ValueError, "small_and_main_accounts_may_be_merged"):
            validate_discretion_heldout_panel_contract(changed)

    def test_panel_cannot_be_used_to_fit_or_promote_a_rule(self):
        changed = copy.deepcopy(self.payload)
        changed["evaluation_contract"]["technical_rules_may_be_retuned_on_panel"] = True
        with self.assertRaisesRegex(ValueError, "technical_rules_may_be_retuned_on_panel"):
            validate_discretion_heldout_panel_contract(changed)

        changed = copy.deepcopy(self.payload)
        changed["policy_promotion_eligible"] = True
        with self.assertRaisesRegex(ValueError, "policy_promotion_eligible must be false"):
            validate_discretion_heldout_panel_contract(changed)

    def test_fingerprint_is_stable_across_mapping_order(self):
        self.assertEqual(
            canonical_fingerprint({"b": 2, "a": {"d": 4, "c": 3}}),
            canonical_fingerprint({"a": {"c": 3, "d": 4}, "b": 2}),
        )

    def test_registration_audit_binds_the_exact_contract(self):
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
        self.assertFalse(audit["decision"]["start_human_label_review"])
        self.assertFalse(audit["policy_promotion_eligible"])


if __name__ == "__main__":
    unittest.main()
