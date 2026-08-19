import copy
import json
import unittest
from pathlib import Path

from momentumbot.research.context_heldout_comparison import (
    load_context_heldout_comparison,
    validate_context_heldout_comparison,
)
from momentumbot.research.context_heldout_panel import canonical_fingerprint


ROOT = Path(__file__).resolve().parents[1]
RESULT = (
    ROOT
    / "research"
    / "data-audits"
    / "context-heldout-comparison-v0.1-2026-08-19.json"
)
LABELS = (
    ROOT
    / "research"
    / "data-audits"
    / "context-heldout-labels-v0.1-2026-08-19.json"
)


def _rehash(payload):
    payload["content_sha256"] = canonical_fingerprint(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )


class ContextHeldoutComparisonTests(unittest.TestCase):
    def setUp(self):
        self.payload = load_context_heldout_comparison(RESULT)

    def test_result_is_bound_to_all_three_frozen_parents(self):
        labels = json.loads(LABELS.read_text(encoding="utf-8"))
        parents = labels["frozen_parents"]
        self.assertEqual(
            self.payload["source_content_sha256s"],
            {
                "labels": labels["content_sha256"],
                "deterministic_runtime_zip": parents["deterministic_runtime"][
                    "zip_sha256"
                ],
                "deterministic_runtime_manifest": parents["deterministic_runtime"][
                    "runtime_manifest_content_sha256"
                ],
                "deterministic_snapshot_runtime": parents["deterministic_runtime"][
                    "snapshot_runtime_content_sha256"
                ],
                "semantic_manifest": parents["semantic_shadow"][
                    "manifest_content_sha256"
                ],
                "semantic_rubric": parents["semantic_shadow"][
                    "rubric_content_sha256"
                ],
            },
        )

    def test_every_frozen_semantic_record_is_bound_to_its_exact_snapshot(self):
        pairing = self.payload["frozen_component_pairing"]
        self.assertEqual(pairing["exact_key_pair_count"], 314)
        self.assertEqual(pairing["exact_source_snapshot_hash_match_count"], 314)
        self.assertEqual(pairing["semantic_axis_instance_count"], 1884)
        self.assertEqual(pairing["semantic_evidence_reference_count"], 2545)
        self.assertEqual(
            pairing["references_resolved_to_exact_snapshot_count"], 2545
        )
        self.assertTrue(pairing["all_semantic_citations_resolve_to_exact_snapshot"])

    def test_activation_is_the_only_action_anchor_and_not_claimed_trade_time(self):
        scope = self.payload["comparison_scope"]
        self.assertEqual(scope["paired_snapshot_rule"], "candidate_activation")
        self.assertFalse(scope["later_source_change_snapshots_used_for_action_comparison"])
        self.assertFalse(scope["exact_human_decision_time_claimed"])
        self.assertFalse(scope["activation_anchor_is_trade_time_proxy"])
        self.assertTrue(
            all(
                row["comparison_snapshot_role"]
                == "candidate_activation_neutral_anchor_not_claimed_trade_time"
                for row in self.payload["candidate_actions"]
            )
        )

    def test_deterministic_coverage_reports_missing_domains_without_imputation(self):
        scopes = self.payload["deterministic_component_descriptives"]
        all_rows = scopes["all_frozen_snapshots"]
        activation = scopes["candidate_activation_snapshots"]
        explicit = scopes["explicit_candidate_symbol_dates_at_activation"]
        self.assertEqual(all_rows["record_count"], 314)
        self.assertEqual(all_rows["domains"]["daily_chart"], {"present": 285, "missing": 29})
        self.assertEqual(
            activation["domains"]["daily_chart"], {"present": 195, "missing": 0}
        )
        self.assertEqual(
            explicit["domains"]["catalyst_headline"], {"present": 14, "missing": 4}
        )
        for domain in (
            "account_state",
            "filing_corroboration",
            "issuer_event_history",
            "liquidity",
            "portfolio_attention",
        ):
            self.assertEqual(
                activation["domains"][domain], {"present": 0, "missing": 195}
            )

    def test_semantic_abstention_and_confidence_remain_component_scoped(self):
        axes = self.payload["semantic_component_descriptives"][
            "candidate_activation_snapshots"
        ]["axes"]
        self.assertEqual(
            axes["catalyst_credibility_repetition"]["states"], {"abstained": 195}
        )
        self.assertEqual(
            axes["theme_fit_no_news_acceptance"]["states"], {"abstained": 195}
        )
        self.assertEqual(
            axes["catalyst_commitment_stage"]["states"],
            {"abstained": 60, "assessed": 135},
        )
        self.assertEqual(
            axes["chart_context_cleanliness"]["states"], {"assessed": 195}
        )

    def test_account_action_groups_are_separate_and_descriptive(self):
        groups = self.payload["action_group_descriptives"]
        self.assertEqual(groups["main_account:participated"]["decision_count"], 11)
        self.assertEqual(
            groups["main_account:explicitly_skipped_or_rejected"]["decision_count"],
            4,
        )
        self.assertEqual(groups["small_account:participated"]["decision_count"], 6)
        self.assertEqual(
            groups["small_account:explicitly_skipped_or_rejected"][
                "decision_count"
            ],
            8,
        )
        main_trade_chart = groups["main_account:participated"][
            "semantic_axis_descriptives"
        ]["axes"]["chart_context_cleanliness"]["values"]
        self.assertEqual(
            main_trade_chart,
            {
                "clear_room_and_clean_history": 5,
                "mixed_chart_context": 1,
                "near_resistance_or_failed_pop_history": 5,
            },
        )
        small_skip_chart = groups["small_account:explicitly_skipped_or_rejected"][
            "semantic_axis_descriptives"
        ]["axes"]["chart_context_cleanliness"]["values"]
        self.assertEqual(small_skip_chart["near_resistance_or_failed_pop_history"], 7)

    def test_candidate_acquisition_is_a_separate_gate(self):
        acquisition = self.payload["candidate_acquisition"]
        self.assertEqual(
            acquisition["main_account"]["descriptive_acquisition_fraction"], 11 / 17
        )
        self.assertEqual(
            acquisition["small_account"]["descriptive_acquisition_fraction"], 6 / 9
        )
        self.assertEqual(
            acquisition["unique_symbol_dates"]["descriptive_acquisition_fraction"],
            12 / 18,
        )

    def test_off_candidate_actions_do_not_claim_context_components(self):
        self.assertEqual(len(self.payload["off_candidate_actions"]), 11)
        self.assertTrue(
            all(
                row["deterministic_components"] is None
                and row["semantic_axes"] is None
                for row in self.payload["off_candidate_actions"]
            )
        )

    def test_no_score_threshold_or_policy_output_exists(self):
        self.assertFalse(self.payload["aggregate_context_score_allowed"])
        self.assertFalse(self.payload["selection_threshold_fitting_allowed"])
        self.assertFalse(self.payload["technical_rule_retuning_allowed"])
        self.assertFalse(self.payload["policy_promotion_eligible"])
        self.assertNotIn("overall_score", self.payload)

    def test_self_rehashed_action_coverage_tamper_fails(self):
        changed = copy.deepcopy(self.payload)
        changed["candidate_actions"][0]["deterministic_components"][
            "evidence_coverage"
        ]["daily_chart"] = False
        _rehash(changed)
        with self.assertRaisesRegex(ValueError, "action-group descriptives"):
            validate_context_heldout_comparison(changed)

    def test_self_rehashed_semantic_value_tamper_fails(self):
        changed = copy.deepcopy(self.payload)
        changed["candidate_actions"][0]["semantic_axes"][
            "chart_context_cleanliness"
        ]["value"] = "mixed_chart_context"
        _rehash(changed)
        with self.assertRaisesRegex(ValueError, "action-group descriptives"):
            validate_context_heldout_comparison(changed)

    def test_self_rehashed_parent_tamper_fails(self):
        changed = copy.deepcopy(self.payload)
        changed["source_content_sha256s"]["labels"] = "0" * 64
        _rehash(changed)
        with self.assertRaisesRegex(ValueError, "labels parent changed"):
            validate_context_heldout_comparison(changed)


if __name__ == "__main__":
    unittest.main()
