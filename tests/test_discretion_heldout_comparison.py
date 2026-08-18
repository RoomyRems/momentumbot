import copy
import json
import unittest
from pathlib import Path

from momentumbot.research.discretion_heldout_comparison import (
    load_discretion_heldout_comparison,
    validate_discretion_heldout_comparison,
)
from momentumbot.research.discretion_heldout_panel import canonical_fingerprint


ROOT = Path(__file__).resolve().parents[1]
RESULT = (
    ROOT
    / "research"
    / "data-audits"
    / "discretion-heldout-comparison-v0.1-2026-08-18.json"
)
LABELS = (
    ROOT
    / "research"
    / "data-audits"
    / "discretion-heldout-labels-v0.1-2026-08-18.json"
)


def _rehash(payload):
    payload["content_sha256"] = canonical_fingerprint(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )


class DiscretionHeldoutComparisonTests(unittest.TestCase):
    def setUp(self):
        self.payload = load_discretion_heldout_comparison(RESULT)

    def test_result_is_bound_to_frozen_labels_and_components(self):
        labels = json.loads(LABELS.read_text(encoding="utf-8"))
        self.assertEqual(
            self.payload["source_content_sha256s"],
            {
                "labels": labels["content_sha256"],
                "scanner_runtime": labels["frozen_runtime"]["scanner_runtime"][
                    "content_sha256"
                ],
                "micro_runtime": labels["frozen_runtime"]["micro_runtime"][
                    "content_sha256"
                ],
                "shadow_runtime": labels["frozen_runtime"]["shadow_runtime"][
                    "content_sha256"
                ],
            },
        )
        self.assertEqual(len(self.payload["candidate_decisions"]), 31)
        self.assertEqual(len(self.payload["off_candidate_decisions"]), 6)

    def test_micro_contingencies_are_account_scoped(self):
        self.assertEqual(
            self.payload["technical_contingency_counts"],
            {
                "main_account": {
                    "modeled_fill_on_participation": 6,
                    "no_modeled_fill_on_participation": 3,
                    "modeled_fill_on_explicit_skip": 2,
                    "no_modeled_fill_on_explicit_skip": 5,
                    "runtime_unavailable": 0,
                },
                "small_account": {
                    "modeled_fill_on_participation": 6,
                    "no_modeled_fill_on_participation": 3,
                    "modeled_fill_on_explicit_skip": 0,
                    "no_modeled_fill_on_explicit_skip": 2,
                    "runtime_unavailable": 0,
                },
            },
        )

    def test_scanner_acquisition_reports_known_misses_without_scoring(self):
        scanner = self.payload["scanner_acquisition"]
        self.assertEqual(
            scanner["main_account"]["descriptive_acquisition_fraction"], 9 / 11
        )
        self.assertEqual(
            scanner["small_account"]["descriptive_acquisition_fraction"], 9 / 10
        )
        self.assertEqual(
            scanner["unique_symbol_dates"]["descriptive_acquisition_fraction"],
            11 / 13,
        )
        self.assertFalse(self.payload["overall_imitation_score_allowed"])
        self.assertFalse(self.payload["policy_promotion_eligible"])
        self.assertNotIn("overall_score", self.payload)

    def test_unclear_actions_are_not_forced_into_trade_skip_contingencies(self):
        gmm_small = next(
            row
            for row in self.payload["candidate_decisions"]
            if row["trading_date"] == "2026-07-10"
            and row["symbol"] == "GMM"
            and row["account"] == "small_account"
        )
        self.assertEqual(gmm_small["human_state"], "discussed_but_action_unclear")
        self.assertEqual(
            gmm_small["technical_relation"], "excluded_unclear_or_unknown"
        )

    def test_off_candidate_participations_do_not_claim_runtime_features(self):
        participated = [
            row
            for row in self.payload["off_candidate_decisions"]
            if row["human_state"] == "participated"
        ]
        self.assertEqual(
            {(row["trading_date"], row["symbol"]) for row in participated},
            {("2026-07-14", "JTAI"), ("2026-07-15", "VIVS")},
        )
        self.assertTrue(
            all(row["micro"] is None and row["shadow"] is None for row in participated)
        )

    def test_first_fills_remain_descriptive_not_targets(self):
        gmm = next(
            row
            for row in self.payload["candidate_decisions"]
            if row["trading_date"] == "2026-07-10"
            and row["symbol"] == "GMM"
            and row["account"] == "main_account"
        )
        self.assertEqual(gmm["micro"]["first_fill_price"], 3.92)
        self.assertEqual(gmm["micro"]["first_fill_pullback_number"], 2)
        self.assertTrue(
            self.payload["comparison_scope"]["first_fill_price_is_descriptive_only"]
        )

    def test_self_rehashed_relation_tamper_fails(self):
        changed = copy.deepcopy(self.payload)
        changed["candidate_decisions"][0]["technical_relation"] = (
            "no_modeled_fill_on_participation"
        )
        _rehash(changed)
        with self.assertRaisesRegex(ValueError, "technical relation"):
            validate_discretion_heldout_comparison(changed)

    def test_self_rehashed_aggregate_tamper_fails(self):
        changed = copy.deepcopy(self.payload)
        changed["technical_contingency_counts"]["main_account"][
            "modeled_fill_on_participation"
        ] = 7
        _rehash(changed)
        with self.assertRaisesRegex(ValueError, "technical contingency"):
            validate_discretion_heldout_comparison(changed)

    def test_self_rehashed_trade_completion_tamper_fails(self):
        changed = copy.deepcopy(self.payload)
        trade = next(
            row
            for row in changed["candidate_decisions"]
            if row["human_state"] == "participated"
        )
        trade["trade_completion"] = "unknown"
        _rehash(changed)
        with self.assertRaisesRegex(ValueError, "requires a completed trade"):
            validate_discretion_heldout_comparison(changed)


if __name__ == "__main__":
    unittest.main()
