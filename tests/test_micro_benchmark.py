import unittest

from momentumbot.micro_benchmark import compare_micro_runtime_to_label


RUNTIME_POLICY = "runtime_market_data_only_no_retrospective_labels"
LABEL_POLICY = "ground_truth_label_only_never_runtime_context"


def runtime_artifact():
    return {
        "artifact_type": "micro_candidate_runtime_replay",
        "schema_version": 1,
        "knowledge_policy": RUNTIME_POLICY,
        "symbol": "VRAX",
        "policy_name": "canonical-micro-current-2026",
        "filled_pullback_numbers": [2],
        "steps": [
            {
                "pullback_number": 1,
                "plan": {"minimum_new_high_price": 5.32},
                "outcome": {
                    "status": "not_triggered",
                    "fill_price": None,
                },
            },
            {
                "pullback_number": 2,
                "plan": {"minimum_new_high_price": 5.25},
                "outcome": {
                    "status": "filled_open",
                    "fill_price": 5.25,
                },
            },
        ],
    }


def vrax_label():
    return {
        "benchmark_id": "ross-vrax-2026-07-09-micro-01",
        "symbol": "VRAX",
        "knowledge_policy": LABEL_POLICY,
        "observed_human_behavior": {
            "setup_type": "micro_pullback",
            "first_pullback_taken": False,
            "pullback_ordinal": 2,
            "intended_break_level": 6.0,
            "reported_fill_approx": 6.3,
        },
    }


class MicroBenchmarkTests(unittest.TestCase):
    def test_comparison_reports_matches_and_price_mismatches_without_selecting_variant(self):
        comparison = compare_micro_runtime_to_label(runtime_artifact(), vrax_label())

        self.assertTrue(comparison.setup_family_match)
        self.assertTrue(comparison.pullback_ordinal_match)
        self.assertTrue(comparison.first_pullback_taken_match)
        self.assertEqual(comparison.comparable_fields, 3)
        self.assertEqual(comparison.matching_fields, 3)
        self.assertEqual(comparison.runtime_filled_pullback_numbers, (2,))
        self.assertEqual(comparison.runtime_plan_trigger_prices, (5.32, 5.25))
        self.assertEqual(comparison.runtime_filled_trigger_prices, (5.25,))
        self.assertEqual(comparison.observed_trigger_references, (6.0,))
        self.assertAlmostEqual(comparison.trigger_reference_absolute_differences[0][0], 0.68)
        self.assertAlmostEqual(comparison.trigger_reference_absolute_differences[1][0], 0.75)
        self.assertEqual(comparison.runtime_fill_prices, (5.25,))
        self.assertEqual(comparison.reported_fill_references, (6.3,))
        self.assertAlmostEqual(comparison.fill_absolute_differences[0][0], 1.05)

    def test_dsy_style_fill_list_is_preserved_as_all_references(self):
        runtime = runtime_artifact()
        runtime["symbol"] = "DSY"
        runtime["filled_pullback_numbers"] = []
        runtime["steps"] = []
        label = {
            "benchmark_id": "ross-dsy-2026-06-10-micro-01",
            "symbol": "DSY",
            "knowledge_policy": LABEL_POLICY,
            "observed_human_behavior": {
                "setup_type": "micro_pullback",
                "reported_entry_fills_approx": [3.07, 3.11],
            },
        }
        comparison = compare_micro_runtime_to_label(runtime, label)
        self.assertEqual(comparison.reported_fill_references, (3.07, 3.11))
        self.assertIsNone(comparison.pullback_ordinal_match)
        self.assertIsNone(comparison.first_pullback_taken_match)

    def test_runtime_knowledge_policy_is_enforced(self):
        runtime = runtime_artifact()
        runtime["knowledge_policy"] = "ground_truth_label_only_never_runtime_context"
        with self.assertRaises(ValueError):
            compare_micro_runtime_to_label(runtime, vrax_label())

    def test_label_knowledge_policy_is_enforced(self):
        label = vrax_label()
        label["knowledge_policy"] = "runtime_market_data_only_no_retrospective_labels"
        with self.assertRaises(ValueError):
            compare_micro_runtime_to_label(runtime_artifact(), label)

    def test_runtime_and_label_symbols_must_match(self):
        label = vrax_label()
        label["symbol"] = "DSY"
        with self.assertRaises(ValueError):
            compare_micro_runtime_to_label(runtime_artifact(), label)


if __name__ == "__main__":
    unittest.main()
