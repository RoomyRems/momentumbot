import json
import tempfile
import unittest
from pathlib import Path

from momentumbot.research.benchmark_suite import (
    BenchmarkCaseRole,
    load_benchmark_suite,
    validate_suite_references,
)


class BenchmarkSuiteTests(unittest.TestCase):
    def test_seed_suite_loads_and_has_balanced_roles(self):
        suite = load_benchmark_suite(
            Path("research/benchmarks/suites/micro-v0.1-seed.json")
        )
        self.assertEqual(suite.policy_id, "micro-v0.1")
        self.assertEqual(len(suite.cases), 10)
        self.assertEqual(suite.primary_scored_count, 4)
        self.assertEqual(suite.partial_scored_count, 1)
        self.assertEqual(
            sum(case.role is BenchmarkCaseRole.BOUNDARY for case in suite.cases),
            3,
        )
        self.assertEqual(
            sum(case.role is BenchmarkCaseRole.AMBIGUOUS for case in suite.cases),
            2,
        )

        artl = next(
            case
            for case in suite.cases
            if case.benchmark_id == "ross-artl-2026-03-27-micro-01"
        )
        self.assertIs(artl.role, BenchmarkCaseRole.AMBIGUOUS)
        self.assertEqual(artl.scored_dimensions, ())
        self.assertIn("source_label_retracted", artl.tags)

    def test_seed_suite_references_existing_safe_benchmarks(self):
        suite = load_benchmark_suite(
            Path("research/benchmarks/suites/micro-v0.1-seed.json")
        )
        validate_suite_references(suite, repo_root=Path("."))

    def test_artl_source_correction_supersedes_historical_scores(self):
        audit_path = Path(
            "research/data-audits/artl-source-label-correction-v0.1.json"
        )
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        self.assertTrue(audit["benchmark_action"]["retire_from_scored_micro_seed"])
        self.assertEqual(audit["finding"]["corrected_artl_first_entry_approx"], 6.34)

        result_paths = [
            Path("research/benchmarks/results/micro-v0.1-seed-summary.json"),
            Path("research/benchmarks/results/micro-v0.2a-context-comparison.json"),
            Path("research/benchmarks/results/micro-v0.2b-local-peak-comparison.json"),
            Path("research/benchmarks/results/micro-volume-factorial-comparison.json"),
            Path(
                "research/benchmarks/results/"
                "micro-v0.2e-qualification-base-comparison.json"
            ),
        ]
        for path in result_paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            correction = payload["retrospective_source_correction"]
            self.assertEqual(correction["audit_path"], audit_path.as_posix())
            self.assertTrue(correction["historical_values_preserved"])
            self.assertFalse(correction["policy_decision_changed"])

        baseline = json.loads(result_paths[0].read_text(encoding="utf-8"))
        valid_cases = [case for case in baseline["cases"] if case["symbol"] != "ARTL"]
        self.assertEqual(sum(case["comparable_dimensions"] for case in valid_cases), 10)
        self.assertEqual(sum(case["matching_dimensions"] for case in valid_cases), 8)

    def test_boundary_cases_cannot_be_accidentally_scored(self):
        payload = {
            "suite_id": "bad",
            "policy_id": "micro-v0.1",
            "knowledge_policy": "ground_truth_label_only_never_runtime_context",
            "status": "test",
            "cases": [
                {
                    "benchmark_id": "x",
                    "benchmark_path": "research/benchmarks/x.json",
                    "role": "boundary_context_only",
                    "tags": [],
                    "scored_dimensions": ["entry"],
                    "rationale": "invalid",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "suite.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_benchmark_suite(path)

    def test_unsafe_knowledge_policy_is_rejected(self):
        payload = {
            "suite_id": "bad",
            "policy_id": "micro-v0.1",
            "knowledge_policy": "runtime_can_read_labels",
            "status": "test",
            "cases": [
                {
                    "benchmark_id": "x",
                    "benchmark_path": "research/benchmarks/x.json",
                    "role": "ambiguous_excluded",
                    "tags": [],
                    "scored_dimensions": [],
                    "rationale": "invalid",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "suite.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_benchmark_suite(path)


if __name__ == "__main__":
    unittest.main()
