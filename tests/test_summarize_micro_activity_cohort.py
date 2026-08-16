import json
import tempfile
import unittest
from pathlib import Path

from scripts.summarize_micro_activity_cohort import build_activity_summary


class MicroActivityCohortSummaryTests(unittest.TestCase):
    def _case(self, case_id: str, offset: int) -> dict[str, object]:
        cells = {}
        identities = {
            "baseline": ("micro-v0.1", "a" * 64),
            "context_only": ("micro-v0.2a-prequalification-context", "b" * 64),
            "volume_only": ("micro-v0.2c-no-hard-volume-gate", "c" * 64),
            "context_plus_volume": (
                "micro-v0.2d-context-no-hard-volume-gate",
                "d" * 64,
            ),
        }
        counts = {
            "baseline": (1 + offset, offset),
            "context_only": (1 + offset, offset),
            "volume_only": (3 + offset, 1 + offset),
            "context_plus_volume": (4 + offset, 1 + offset),
        }
        for cell, (plans, fills) in counts.items():
            cells[cell] = {
                "policy_id": identities[cell][0],
                "policy_fingerprint": identities[cell][1],
                "plan_count": plans,
                "filled_count": fills,
                "first_plan_latency_seconds": 30.0,
                "first_fill_latency_seconds": 40.0 if fills else None,
                "first_plan_pullback_number": 1,
                "first_filled_pullback_number": 1 if fills else None,
                "first_fill_price": 3.0 if fills else None,
            }
        paired = {
            "volume_only_vs_baseline": {
                "plan_count_delta": 2,
                "filled_count_delta": 1,
                "first_plan_shift_seconds": -10.0,
                "first_fill_shift_seconds": None,
                "first_fill_state": "gained_first_fill" if offset == 0 else "both_filled",
            },
            "context_plus_volume_vs_context_only": {
                "plan_count_delta": 3,
                "filled_count_delta": 1,
                "first_plan_shift_seconds": -10.0,
                "first_fill_shift_seconds": None,
                "first_fill_state": "gained_first_fill" if offset == 0 else "both_filled",
            },
            "context_only_vs_baseline": {
                "plan_count_delta": 0,
                "filled_count_delta": 0,
                "first_plan_shift_seconds": 0.0,
                "first_fill_shift_seconds": 0.0 if offset else None,
                "first_fill_state": "both_filled" if offset else "neither_filled",
            },
            "context_plus_volume_vs_volume_only": {
                "plan_count_delta": 1,
                "filled_count_delta": 0,
                "first_plan_shift_seconds": 0.0,
                "first_fill_shift_seconds": 0.0,
                "first_fill_state": "both_filled",
            },
        }
        return {
            "artifact_type": "micro_volume_activity_cohort_case_comparison",
            "knowledge_policy": "runtime_market_data_only_no_retrospective_labels",
            "policy_promotion_eligible": False,
            "cohort_design_id": "test-design",
            "cohort_selection_sha256": "e" * 64,
            "case_id": case_id,
            "symbol": case_id.upper(),
            "trading_date": "2025-02-12",
            "selection_rank_within_date": offset + 1,
            "candidate_qualified_at": "2025-02-12T12:00:00+00:00",
            "cells": cells,
            "paired_deltas": paired,
        }

    def _write(self, root: Path, case_id: str, offset: int) -> None:
        path = root / case_id / "case-comparison.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(self._case(case_id, offset)), encoding="utf-8")

    def test_aggregates_predeclared_paired_activity_deltas(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "one", 0)
            self._write(root, "two", 1)
            payload = build_activity_summary(root)

        self.assertEqual(payload["case_count"], 2)
        self.assertEqual(payload["cell_summary"]["baseline"]["total_plan_count"], 3)
        volume = payload["paired_summary"]["volume_only_vs_baseline"]
        self.assertEqual(volume["aggregate_plan_count_delta"], 4)
        self.assertEqual(volume["aggregate_filled_count_delta"], 2)
        self.assertEqual(volume["plan_count_delta_cases"]["positive"], 2)
        self.assertFalse(payload["policy_promotion_eligible"])

    def test_rejects_mixed_selection_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "one", 0)
            self._write(root, "two", 1)
            path = root / "two" / "case-comparison.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["cohort_selection_sha256"] = "f" * 64
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "different cohort selections"):
                build_activity_summary(root)


if __name__ == "__main__":
    unittest.main()
