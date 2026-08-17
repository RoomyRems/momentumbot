import json
import unittest

import pandas as pd

from momentumbot.micro_replay import replay_micro_candidate
from momentumbot.micro_setup import geometry_only_micro_research_policy
from momentumbot.research.micro_impulse_base_ablation import (
    evaluate_micro_pullback_plan_with_qualification_base,
    impulse_base_runtime_artifact,
    micro_v0_2e_impulse_base_ablation,
    replay_micro_candidate_with_qualification_base,
)


def _extended_impulse() -> pd.DataFrame:
    index = pd.date_range("2026-01-02T11:00:00Z", periods=8, freq="10s")
    return pd.DataFrame(
        [
            (4.00, 4.20, 4.00, 4.15, 100),
            (4.15, 4.70, 4.40, 4.65, 150),
            (4.65, 5.20, 5.00, 5.15, 200),
            (5.15, 5.40, 5.10, 5.35, 250),
            (5.35, 5.65, 5.20, 5.60, 300),
            (5.60, 5.85, 5.40, 5.80, 350),
            (5.80, 6.00, 5.60, 5.95, 400),
            (5.90, 5.90, 5.40, 5.60, 50),
        ],
        columns=["open", "high", "low", "close", "volume"],
        index=index,
    )


class QualificationAnchoredImpulseBaseTests(unittest.TestCase):
    def test_spec_changes_no_threshold_or_peak_rule(self):
        spec = micro_v0_2e_impulse_base_ablation()
        self.assertEqual(
            spec.ablation_id,
            "micro-v0.2e-qualification-anchored-impulse-base",
        )
        self.assertEqual(spec.parent_policy_id, "micro-v0.1")
        self.assertEqual(spec.parent_impulse_lookback_bars, 5)
        self.assertEqual(spec.peak_rule, "strict_running_high_parent_v0_1")
        self.assertEqual(
            spec.impulse_base_rule,
            "minimum_postqualification_low_through_selected_peak",
        )
        self.assertEqual(len(spec.fingerprint), 64)

    def test_only_qualification_base_changes_retrace_decision(self):
        bars = _extended_impulse()
        policy = geometry_only_micro_research_policy()
        parent = replay_micro_candidate(
            "ABC",
            bars,
            pd.DataFrame(
                columns=["price", "size", "conditions", "tape"],
                index=pd.DatetimeIndex([], tz="UTC"),
            ),
            candidate_qualified_at=bars.index[0],
            policy=policy,
        )
        self.assertFalse(any(step.plan is not None for step in parent.steps))
        self.assertEqual(parent.steps[-1].reason, "micro_retrace_above_half")

        evaluation = evaluate_micro_pullback_plan_with_qualification_base(
            "ABC",
            bars,
            candidate_qualified_at=bars.index[0],
            policy=policy,
            pullback_number=1,
        )
        self.assertEqual(evaluation.reason, "plan")
        assert evaluation.features is not None
        self.assertEqual(evaluation.features.impulse_base, 4.00)
        self.assertAlmostEqual(evaluation.features.retrace_fraction, 0.30)
        self.assertAlmostEqual(evaluation.features.impulse_mean_volume, 300.0)

    def test_prequalification_low_is_never_used(self):
        bars = _extended_impulse()
        result = evaluate_micro_pullback_plan_with_qualification_base(
            "ABC",
            bars,
            candidate_qualified_at=bars.index[2],
            policy=geometry_only_micro_research_policy(),
        )
        self.assertEqual(result.reason, "micro_retrace_above_half")
        self.assertIsNone(result.plan)

    def test_replay_and_runtime_artifact_remain_label_blind(self):
        bars = _extended_impulse()
        trades = pd.DataFrame(
            [{"price": 5.91, "size": 100, "conditions": ("@",), "tape": "C"}],
            index=pd.to_datetime(["2026-01-02T11:01:21Z"], utc=True),
        )
        result = replay_micro_candidate_with_qualification_base(
            "ABC",
            bars,
            trades,
            candidate_qualified_at=bars.index[0],
            policy=geometry_only_micro_research_policy(),
            exit_until=pd.Timestamp("2026-01-02T11:01:30Z"),
        )
        self.assertEqual(result.replay.plan_count, 1)
        self.assertEqual(result.replay.filled_count, 1)
        payload = impulse_base_runtime_artifact(result)
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
        self.assertEqual(payload["parent_frozen_policy_id"], "micro-v0.1")
        self.assertEqual(payload["impulse_volume_rule"], "parent_five_bar_impulse_window_unchanged")
        self.assertNotIn("benchmark_id", encoded)
        self.assertNotIn("reported_fill", encoded)
        self.assertNotIn("observed_human_behavior", encoded)


if __name__ == "__main__":
    unittest.main()
