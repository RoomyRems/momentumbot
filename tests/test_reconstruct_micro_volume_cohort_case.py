import unittest
from types import SimpleNamespace

import pandas as pd

from scripts.reconstruct_micro_volume_cohort_case import (
    _causal_refined_qualification,
    _cell_summary,
    _paired_delta,
    _qualification_anchors,
)


class MicroVolumeCohortCaseTests(unittest.TestCase):
    def test_refinement_cannot_backdate_the_0700_strategy_boundary(self):
        qualified_at, source = _causal_refined_qualification(
            "2025-02-12T11:59:40+00:00",
            bar_started_at=pd.Timestamp("2025-02-12T11:59:00+00:00"),
            completed_bar_decision_at=pd.Timestamp(
                "2025-02-12T12:00:00+00:00"
            ),
            strategy_session_start=pd.Timestamp("2025-02-12T12:00:00+00:00"),
        )

        self.assertEqual(qualified_at.isoformat(), "2025-02-12T12:00:00+00:00")
        self.assertEqual(
            source,
            "completed_acquisition_minute_fallback_outside_strategy_window",
        )

    def test_refinement_inside_strategy_window_is_retained(self):
        qualified_at, source = _causal_refined_qualification(
            "2025-02-12T12:00:40+00:00",
            bar_started_at=pd.Timestamp("2025-02-12T12:00:00+00:00"),
            completed_bar_decision_at=pd.Timestamp(
                "2025-02-12T12:01:00+00:00"
            ),
            strategy_session_start=pd.Timestamp("2025-02-12T12:00:00+00:00"),
        )

        self.assertEqual(qualified_at.isoformat(), "2025-02-12T12:00:40+00:00")
        self.assertEqual(source, "sip_intraminute_refinement")

    def test_qualification_anchors_separate_bar_start_from_decision_time(self):
        bar_started_at, qualified_at = _qualification_anchors(
            {
                "first_market_qualified_bar_started_at": (
                    "2025-02-12T12:00:00+00:00"
                ),
                "first_market_qualified_at": "2025-02-12T12:01:00+00:00",
            }
        )

        self.assertEqual(bar_started_at.isoformat(), "2025-02-12T12:00:00+00:00")
        self.assertEqual(qualified_at.isoformat(), "2025-02-12T12:01:00+00:00")

    def test_qualification_anchors_reject_bar_start_as_decision_time(self):
        with self.assertRaisesRegex(ValueError, "plus one minute"):
            _qualification_anchors(
                {
                    "first_market_qualified_bar_started_at": (
                        "2025-02-12T12:00:00+00:00"
                    ),
                    "first_market_qualified_at": "2025-02-12T12:00:00+00:00",
                }
            )

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
