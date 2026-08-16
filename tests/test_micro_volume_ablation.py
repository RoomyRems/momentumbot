import unittest
from dataclasses import asdict

import pandas as pd

from momentumbot.micro_policy import micro_v0_1_policy
from momentumbot.micro_replay import replay_micro_candidate
from momentumbot.research.micro_volume_ablation import (
    micro_v0_2c_volume_ablation,
    micro_v0_2d_context_volume_ablation,
    parent_setup_without_hard_volume_gate,
    replay_micro_candidate_with_context_without_hard_volume_gate,
    replay_micro_candidate_without_hard_volume_gate,
)


def _support(timestamp):
    index = pd.DatetimeIndex([pd.Timestamp(timestamp)])
    return pd.Series([3.0], index=index, dtype=float)


class MicroVolumeAblationTests(unittest.TestCase):
    def test_specs_and_child_policy_are_isolated(self):
        c = micro_v0_2c_volume_ablation()
        d = micro_v0_2d_context_volume_ablation()
        self.assertFalse(c.prequalification_context_enabled)
        self.assertTrue(d.prequalification_context_enabled)
        self.assertEqual(c.context_bars, 0)
        self.assertEqual(d.context_bars, 10)
        self.assertEqual(len(c.fingerprint), 64)
        self.assertEqual(len(d.fingerprint), 64)

        parent = micro_v0_1_policy().setup
        child = parent_setup_without_hard_volume_gate()
        parent_payload = asdict(parent)
        child_payload = asdict(child)
        self.assertTrue(parent_payload.pop("require_lower_pullback_volume"))
        self.assertFalse(child_payload.pop("require_lower_pullback_volume"))
        parent_payload.pop("name")
        child_payload.pop("name")
        self.assertEqual(parent_payload, child_payload)

    def test_volume_gate_off_can_admit_same_geometry(self):
        index = pd.date_range("2026-01-02T11:00:00Z", periods=4, freq="10s")
        bars = pd.DataFrame(
            [
                (4.00, 4.25, 3.95, 4.20, 100),
                (4.20, 4.50, 4.15, 4.48, 100),
                (4.48, 4.49, 4.35, 4.38, 300),
                (4.38, 4.60, 4.38, 4.55, 200),
            ],
            columns=["open", "high", "low", "close", "volume"],
            index=index,
        )
        trades = pd.DataFrame(
            [{"price": 4.50, "size": 100, "conditions": ("@",), "tape": "C"}],
            index=pd.to_datetime(["2026-01-02T11:00:31Z"], utc=True),
        )
        support = _support("2026-01-02T11:00:00Z")
        baseline = replay_micro_candidate(
            "ABC", bars, trades,
            candidate_qualified_at=bars.index[0],
            policy=micro_v0_1_policy().setup,
            vwap_available=support,
            ema9_available=support,
        )
        self.assertEqual(baseline.filled_count, 0)
        self.assertIn("micro_pullback_volume_not_lower", baseline.reason_counts)

        result = replay_micro_candidate_without_hard_volume_gate(
            "ABC", bars, trades,
            candidate_qualified_at=bars.index[0],
            vwap_available=support,
            ema9_available=support,
        )
        self.assertEqual(result.replay.filled_count, 1)

    def test_context_volume_cell_can_use_completed_prequalification_structure(self):
        index = pd.date_range("2026-01-02T12:00:00Z", periods=6, freq="10s")
        bars = pd.DataFrame(
            [
                (4.00, 4.20, 3.95, 4.18, 100),
                (4.18, 4.45, 4.15, 4.43, 100),
                (4.43, 4.60, 4.40, 4.58, 120),
                (4.58, 4.59, 4.46, 4.50, 300),
                (4.50, 4.55, 4.44, 4.48, 280),
                (4.48, 4.65, 4.48, 4.62, 200),
            ],
            columns=["open", "high", "low", "close", "volume"],
            index=index,
        )
        trades = pd.DataFrame(
            [{"price": 4.56, "size": 100, "conditions": ("@",), "tape": "C"}],
            index=pd.to_datetime(["2026-01-02T12:00:51Z"], utc=True),
        )
        qualified = pd.Timestamp("2026-01-02T12:00:35Z")
        support = _support("2026-01-02T12:00:00Z")

        no_context = replay_micro_candidate_without_hard_volume_gate(
            "ABC", bars, trades,
            candidate_qualified_at=qualified,
            vwap_available=support,
            ema9_available=support,
        )
        self.assertEqual(no_context.replay.filled_count, 0)

        context = replay_micro_candidate_with_context_without_hard_volume_gate(
            "ABC", bars, trades,
            candidate_qualified_at=qualified,
            vwap_available=support,
            ema9_available=support,
        )
        self.assertEqual(context.replay.filled_count, 1)
        self.assertGreater(context.available_prequalification_context_bars, 0)
        self.assertTrue(all(
            step.plan is None or pd.Timestamp(step.plan.armed_at) >= qualified
            for step in context.replay.steps
        ))


if __name__ == "__main__":
    unittest.main()
