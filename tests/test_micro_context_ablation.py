import json
import unittest

import pandas as pd

from momentumbot.micro_replay import replay_micro_candidate
from momentumbot.micro_setup import geometry_only_micro_research_policy
from momentumbot.research.micro_context_ablation import (
    completed_prequalification_context_start,
    micro_v0_2a_context_ablation,
    prequalification_context_runtime_artifact,
    replay_micro_candidate_with_prequalification_context,
)


def _bars() -> pd.DataFrame:
    index = pd.date_range("2026-01-02T11:00:00Z", periods=6, freq="10s")
    return pd.DataFrame(
        [
            (4.00, 4.25, 3.95, 4.20, 1000),
            (4.20, 4.50, 4.15, 4.48, 1200),
            (4.48, 4.48, 4.35, 4.38, 400),
            (4.38, 4.42, 4.32, 4.36, 350),
            (4.36, 4.40, 4.34, 4.39, 300),
            (4.39, 4.45, 4.38, 4.44, 600),
        ],
        columns=["open", "high", "low", "close", "volume"],
        index=index,
    )


def _trades() -> pd.DataFrame:
    index = pd.to_datetime(["2026-01-02T11:00:51Z"], utc=True)
    return pd.DataFrame(
        [
            {
                "price": 4.41,
                "size": 100,
                "conditions": ("@",),
                "tape": "C",
            }
        ],
        index=index,
    )


class PrequalificationContextAblationTests(unittest.TestCase):
    def test_context_bound_is_derived_from_parent_geometry(self):
        spec = micro_v0_2a_context_ablation()
        self.assertEqual(spec.ablation_id, "micro-v0.2a-prequalification-context")
        self.assertEqual(spec.parent_policy_id, "micro-v0.1")
        self.assertEqual(spec.context_bars, 10)
        self.assertEqual(spec.bar_interval_seconds, 10)
        self.assertEqual(spec.context_seconds, 100)
        self.assertEqual(spec.pullback_ordinal_rule, "actual_candidate_qualification")
        self.assertEqual(len(spec.fingerprint), 64)

    def test_context_start_uses_only_bars_completed_before_qualification(self):
        bars = _bars()
        qualified = pd.Timestamp("2026-01-02T11:00:35Z")
        start, available = completed_prequalification_context_start(
            bars,
            candidate_qualified_at=qualified,
            context_bars=10,
            bar_interval_seconds=10,
        )
        self.assertEqual(start, bars.index[0])
        self.assertEqual(available, 3)

    def test_context_can_recognize_existing_pullback_without_prequal_action(self):
        bars = _bars()
        trades = _trades()
        qualified = pd.Timestamp("2026-01-02T11:00:35Z")
        policy = geometry_only_micro_research_policy()

        baseline = replay_micro_candidate(
            "ABC",
            bars,
            trades,
            candidate_qualified_at=qualified,
            policy=policy,
            exit_until=pd.Timestamp("2026-01-02T11:01:10Z"),
        )
        self.assertEqual(baseline.filled_count, 0)

        result = replay_micro_candidate_with_prequalification_context(
            "ABC",
            bars,
            trades,
            candidate_qualified_at=qualified,
            policy=policy,
            exit_until=pd.Timestamp("2026-01-02T11:01:10Z"),
        )
        replay = result.replay
        self.assertEqual(result.available_prequalification_context_bars, 3)
        self.assertEqual(replay.filled_count, 1)
        self.assertEqual(replay.filled_steps[0].outcome.fill_price, 4.41)
        self.assertEqual(replay.filled_pullback_numbers, (1,))
        self.assertTrue(
            all(
                step.plan is None
                or pd.Timestamp(step.plan.armed_at) >= qualified
                for step in replay.steps
            )
        )
        self.assertTrue(
            all(pd.Timestamp(step.evaluated_at) >= qualified for step in replay.steps)
        )

    def test_ablation_artifact_is_label_blind_and_parent_provenanced(self):
        result = replay_micro_candidate_with_prequalification_context(
            "ABC",
            _bars(),
            _trades(),
            candidate_qualified_at=pd.Timestamp("2026-01-02T11:00:35Z"),
            policy=geometry_only_micro_research_policy(),
            exit_until=pd.Timestamp("2026-01-02T11:01:10Z"),
        )
        payload = prequalification_context_runtime_artifact(result)
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False)

        self.assertEqual(
            payload["artifact_type"], "micro_candidate_runtime_replay_ablation"
        )
        self.assertEqual(payload["ablation_id"], "micro-v0.2a-prequalification-context")
        self.assertEqual(payload["parent_frozen_policy_id"], "micro-v0.1")
        self.assertEqual(payload["structural_context_bars_requested"], 10)
        self.assertEqual(payload["pullback_ordinal_rule"], "actual_candidate_qualification")
        self.assertEqual(payload["filled_count"], 1)
        self.assertNotIn("benchmark_id", encoded)
        self.assertNotIn("reported_fill", encoded)
        self.assertNotIn("observed_human_behavior", encoded)


if __name__ == "__main__":
    unittest.main()
