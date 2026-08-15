import json
import unittest

import pandas as pd

from momentumbot.micro_replay import (
    causal_active_pullback_number,
    micro_replay_runtime_artifact,
    replay_micro_candidate,
)
from momentumbot.micro_setup import geometry_only_micro_research_policy


def _trade_frame(rows):
    index = pd.to_datetime([row.pop("timestamp") for row in rows], utc=True)
    return pd.DataFrame(rows, index=index)


def _vrax_like_bars() -> pd.DataFrame:
    index = pd.date_range("2026-07-09T11:31:00Z", periods=9, freq="10s")
    return pd.DataFrame(
        [
            (4.20, 5.33, 4.08, 5.30, 1000),
            (5.20, 5.31, 4.73, 5.00, 700),
            (5.00, 5.04, 4.58, 4.80, 500),
            (4.80, 5.27, 4.76, 5.20, 450),
            (5.20, 5.41, 5.04, 5.35, 900),
            (5.35, 5.28, 5.08, 5.15, 400),
            (5.15, 5.41, 5.09, 5.30, 350),
            (5.30, 5.28, 4.94, 5.00, 300),
            (5.00, 5.24, 4.96, 5.10, 250),
        ],
        columns=["open", "high", "low", "close", "volume"],
        index=index,
    )


def _filled_replay():
    bars = _vrax_like_bars()
    trades = _trade_frame(
        [
            {
                "timestamp": "2026-07-09T11:32:31Z",
                "price": 5.25,
                "size": 100,
                "conditions": ("@",),
                "tape": "C",
            }
        ]
    )
    return replay_micro_candidate(
        "ABC",
        bars,
        trades,
        candidate_qualified_at=bars.index[0],
        policy=geometry_only_micro_research_policy(),
        exit_until=pd.Timestamp("2026-07-09T11:33:00Z"),
    )


class MicroReplayTests(unittest.TestCase):
    def test_active_pullback_number_advances_only_after_confirmed_resumption(self):
        bars = _vrax_like_bars()
        self.assertEqual(
            causal_active_pullback_number(
                bars.iloc[:4], candidate_qualified_at=bars.index[0]
            ),
            1,
        )
        self.assertEqual(
            causal_active_pullback_number(
                bars.iloc[:6], candidate_qualified_at=bars.index[0]
            ),
            2,
        )
        self.assertEqual(
            causal_active_pullback_number(
                bars, candidate_qualified_at=bars.index[0]
            ),
            2,
        )

    def test_replay_attaches_only_second_pullback_fill_without_labels(self):
        replay = _filled_replay()

        self.assertGreaterEqual(replay.plan_count, 2)
        self.assertEqual(replay.filled_count, 1)
        self.assertEqual(replay.filled_pullback_numbers, (2,))
        filled = replay.filled_steps[0]
        self.assertEqual(filled.pullback_number, 2)
        self.assertEqual(filled.plan.minimum_new_high_price, 5.25)
        self.assertEqual(filled.outcome.fill_price, 5.25)

        first_pullback_plans = [
            step for step in replay.steps
            if step.pullback_number == 1 and step.plan is not None
        ]
        self.assertTrue(first_pullback_plans)
        self.assertTrue(all(not step.filled for step in first_pullback_plans))

    def test_runtime_artifact_is_json_safe_and_label_blind(self):
        payload = micro_replay_runtime_artifact(_filled_replay())
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False)

        self.assertEqual(payload["artifact_type"], "micro_candidate_runtime_replay")
        self.assertEqual(
            payload["knowledge_policy"],
            "runtime_market_data_only_no_retrospective_labels",
        )
        self.assertEqual(payload["filled_pullback_numbers"], [2])
        self.assertIn('"fill_price": 5.25', encoded)
        self.assertNotIn("benchmark_id", encoded)
        self.assertNotIn("reported_fill", encoded)
        self.assertNotIn("observed_human_behavior", encoded)

    def test_replay_rejects_timezone_naive_candidate_anchor(self):
        bars = _vrax_like_bars()
        trades = _trade_frame(
            [
                {
                    "timestamp": "2026-07-09T11:32:31Z",
                    "price": 5.25,
                    "size": 100,
                    "conditions": ("@",),
                    "tape": "C",
                }
            ]
        )
        with self.assertRaises(ValueError):
            replay_micro_candidate(
                "ABC",
                bars,
                trades,
                candidate_qualified_at=pd.Timestamp("2026-07-09 11:31:00"),
                policy=geometry_only_micro_research_policy(),
            )


if __name__ == "__main__":
    unittest.main()
