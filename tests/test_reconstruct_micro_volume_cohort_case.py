import unittest
from types import SimpleNamespace

import pandas as pd

from scripts.reconstruct_micro_volume_cohort_case import _cell_summary, _paired_delta


class MicroVolumeCohortCaseTests(unittest.TestCase):
    def test_paired_delta_reports_activity_and_earlier_onset(self):
        before = {
            "plan_count": 1,
            "filled_count": 0,
            "first_plan_armed_at": "2025-02-12T12:10:10+00:00",
            "first_fill_at": None,
            "first_plan_pullback_number": 3,
            "first_filled_pullback_number": None,
        }
        after = {
            "plan_count": 4,
            "filled_count": 1,
            "first_plan_armed_at": "2025-02-12T12:08:10+00:00",
            "first_fill_at": "2025-02-12T12:08:30+00:00",
            "first_plan_pullback_number": 2,
            "first_filled_pullback_number": 2,
        }

        delta = _paired_delta(after, before)

        self.assertEqual(delta["plan_count_delta"], 3)
        self.assertEqual(delta["filled_count_delta"], 1)
        self.assertEqual(delta["first_plan_shift_seconds"], -120.0)
        self.assertEqual(delta["first_plan_pullback_ordinal_delta"], -1)
        self.assertEqual(delta["first_fill_state"], "gained_first_fill")

    def test_cell_summary_measures_first_plan_latency_when_plan_is_armed(self):
        plan = SimpleNamespace(
            armed_at=pd.Timestamp("2025-02-12T12:10:10+00:00"),
            minimum_new_high_price=3.25,
        )
        step = SimpleNamespace(
            evaluated_at=pd.Timestamp("2025-02-12T12:10:00+00:00"),
            pullback_number=3,
            plan=plan,
            outcome=None,
        )
        replay = SimpleNamespace(
            steps=(step,),
            plan_count=1,
            filled_count=0,
            filled_pullback_numbers=(),
            reason_counts={"plan": 1},
        )

        summary = _cell_summary(
            replay,
            pd.Timestamp("2025-02-12T12:09:00+00:00"),
        )

        self.assertEqual(
            summary["first_plan_evaluated_at"],
            "2025-02-12T12:10:00+00:00",
        )
        self.assertEqual(
            summary["first_plan_armed_at"],
            "2025-02-12T12:10:10+00:00",
        )
        self.assertEqual(summary["first_plan_latency_seconds"], 70.0)


if __name__ == "__main__":
    unittest.main()
