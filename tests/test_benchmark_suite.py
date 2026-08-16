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
        self.assertEqual(suite.primary_scored_count, 5)
        self.assertEqual(suite.partial_scored_count, 1)
        self.assertEqual(
            sum(case.role is BenchmarkCaseRole.BOUNDARY for case in suite.cases),
            3,
        )
        self.assertEqual(
            sum(case.role is BenchmarkCaseRole.AMBIGUOUS for case in suite.cases),
            1,
        )

    def test_seed_suite_references_existing_safe_benchmarks(self):
        suite = load_benchmark_suite(
            Path("research/benchmarks/suites/micro-v0.1-seed.json")
        )
        validate_suite_references(suite, repo_root=Path("."))

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
