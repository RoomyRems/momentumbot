import json
import unittest

import pandas as pd

from momentumbot.micro_replay import replay_micro_candidate
from momentumbot.micro_setup import geometry_only_micro_research_policy
from momentumbot.research.micro_local_peak_ablation import (
    evaluate_micro_pullback_plan_local_peak,
    local_peak_runtime_artifact,
    micro_v0_2b_local_peak_ablation,
    replay_micro_candidate_with_local_peak,
)


def _bars_with_lower_local_impulse() -> pd.DataFrame:
    index = pd.date_range("2026-01-02T11:00:00Z", periods=8, freq="10s")
    return pd.DataFrame(
        [
            (4.80, 5.00, 4.70, 4.90, 1000),
            (4.42, 4.50, 4.30, 4.40, 800),
            (4.40, 4.45, 4.35, 4.42, 700),
            (4.42, 4.55, 4.40, 4.52, 800),
            (4.52, 4.65, 4.50, 4.62, 1000),
            (4.62, 4.80, 4.60, 4.76, 1200),
            (4.76, 4.76, 4.68, 4.70, 400),
            (4.70, 4.85, 4.70, 4.82, 900),
        ],
        columns=["open", "high", "low", "close", "volume"],
        index=index,
    )


def _trades() -> pd.DataFrame:
    index = pd.to_datetime(["2026-01-02T11:01:11Z"], utc=True)
    return pd.DataFrame(
        [
            {
                "price": 4.77,
                "size": 100,
                "conditions": ("@",),
                "tape": "C",
            }
        ],
        index=index,
    )


class LocalImpulsePeakAblationTests(unittest.TestCase):
    def test_spec_uses_parent_impulse_lookback_without_new_constant(self):
        spec = micro_v0_2b_local_peak_ablation()
        self.assertEqual(spec.ablation_id, "micro-v0.2b-local-impulse-peak")
        self.assertEqual(spec.parent_policy_id, "micro-v0.1")
        self.assertEqual(spec.peak_scope_bars, 5)
        self.assertEqual(spec.peak_rule, "strict_high_over_parent_impulse_lookback")
        self.assertEqual(spec.structural_context_rule, "postqualification_only_parent_v0_1")
        self.assertEqual(len(spec.fingerprint), 64)

    def test_local_peak_accepts_lower_impulse_that_parent_running_high_rejects(self):
        bars = _bars_with_lower_local_impulse()
        policy = geometry_only_micro_research_policy()
        evaluation = evaluate_micro_pullback_plan_local_peak(
            "ABC",
            bars.iloc[:7],
            candidate_qualified_at=bars.index[0],
            policy=policy,
            pullback_number=1,
        )
        self.assertEqual(evaluation.reason, "plan")
        self.assertIsNotNone(evaluation.plan)
        self.assertIsNotNone(evaluation.features)
        self.assertEqual(evaluation.features.peak_high, 4.80)
        self.assertEqual(evaluation.features.peak_time, bars.index[5].to_pydatetime())
        self.assertEqual(evaluation.plan.minimum_new_high_price, 4.77)

    def test_replay_changes_only_peak_scope_and_fills_postqualification(self):
        bars = _bars_with_lower_local_impulse()
        trades = _trades()
        qualified = bars.index[0]
        policy = geometry_only_micro_research_policy()

        baseline = replay_micro_candidate(
            "ABC",
            bars,
            trades,
            candidate_qualified_at=qualified,
            policy=policy,
            exit_until=pd.Timestamp("2026-01-02T11:01:30Z"),
        )
        self.assertEqual(baseline.filled_count, 0)

        result = replay_micro_candidate_with_local_peak(
            "ABC",
            bars,
            trades,
            candidate_qualified_at=qualified,
            policy=policy,
            exit_until=pd.Timestamp("2026-01-02T11:01:30Z"),
        )
        replay = result.replay
        self.assertEqual(replay.filled_count, 1)
        self.assertEqual(replay.filled_pullback_numbers, (1,))
        filled = replay.filled_steps[0]
        self.assertEqual(filled.outcome.fill_price, 4.77)
        self.assertEqual(filled.plan.minimum_new_high_price, 4.77)
        self.assertGreaterEqual(pd.Timestamp(filled.plan.armed_at), qualified)

    def test_runtime_artifact_is_label_blind_and_parent_provenanced(self):
        result = replay_micro_candidate_with_local_peak(
            "ABC",
            _bars_with_lower_local_impulse(),
            _trades(),
            candidate_qualified_at=pd.Timestamp("2026-01-02T11:00:00Z"),
            policy=geometry_only_micro_research_policy(),
            exit_until=pd.Timestamp("2026-01-02T11:01:30Z"),
        )
        payload = local_peak_runtime_artifact(result)
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False)

        self.assertEqual(
            payload["artifact_type"], "micro_candidate_runtime_replay_ablation"
        )
        self.assertEqual(payload["ablation_id"], "micro-v0.2b-local-impulse-peak")
        self.assertEqual(payload["parent_frozen_policy_id"], "micro-v0.1")
        self.assertEqual(payload["peak_scope_bars"], 5)
        self.assertEqual(payload["filled_count"], 1)
        self.assertNotIn("benchmark_id", encoded)
        self.assertNotIn("reported_fill", encoded)
        self.assertNotIn("observed_human_behavior", encoded)


if __name__ == "__main__":
    unittest.main()
