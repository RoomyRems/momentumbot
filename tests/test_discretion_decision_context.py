import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS = ROOT / "research" / "benchmarks"


def _load(filename):
    return json.loads((BENCHMARKS / filename).read_text(encoding="utf-8"))


class DiscretionDecisionContextTests(unittest.TestCase):
    def test_dsy_context_preserves_theme_attention_and_cushion_without_runtime_use(self):
        payload = _load("2026-06-10-dsy.json")
        extraction = payload["decision_context_extraction"]
        self.assertFalse(extraction["verbatim_transcript_persisted"])
        self.assertFalse(extraction["runtime_eligible"])
        self.assertFalse(extraction["pre_entry_video_timestamp_verified"])
        self.assertFalse(extraction["complete_alternative_candidate_set"])

        context = payload["observed_human_decision_context"]
        self.assertTrue(context["active_theme"]["theme_overrode_simple_news_presence_preference"])
        self.assertEqual(context["attention_transfer"]["prior_leader_symbol"], "VSME")
        self.assertTrue(context["attention_transfer"]["dsy_became_attention_successor"])
        self.assertEqual(len(context["partial_alternative_candidates"]), 3)
        self.assertTrue(context["session_state"]["larger_position_enabled_by_prior_profit_cushion"])

    def test_vrax_context_preserves_comparison_skip_and_risk_reassessment(self):
        payload = _load("2026-07-09-vrax.json")
        extraction = payload["decision_context_extraction"]
        self.assertFalse(extraction["runtime_eligible"])
        self.assertFalse(extraction["pre_entry_video_timestamp_verified"])
        self.assertFalse(extraction["complete_alternative_candidate_set"])

        context = payload["observed_human_decision_context"]
        self.assertEqual(
            [row["symbol"] for row in context["partial_alternative_candidates"]],
            ["PMA", "RPGL", "SOT"],
        )
        self.assertTrue(context["entry_discretion"]["first_pullback_skipped"])
        self.assertTrue(context["entry_discretion"]["second_micro_pullback_taken"])
        self.assertFalse(
            context["catalyst_and_discovery"]["catalyst_substance_beyond_headline_assessed"]
        )
        risk = context["execution_risk_reassessment"]
        self.assertEqual(risk["planned_risk_per_share_cents_approx"], 15)
        self.assertEqual(risk["post_slippage_risk_per_share_cents_approx_range"], [35, 40])
        self.assertEqual(risk["two_to_one_target_required_cents_approx"], 80)


if __name__ == "__main__":
    unittest.main()
