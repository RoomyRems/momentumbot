import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.select_micro_activity_cohort import build_selection


class MicroActivityCohortSelectionTests(unittest.TestCase):
    def _design(self, root: Path) -> Path:
        path = root / "design.json"
        path.write_text(
            json.dumps(
                {
                    "artifact_type": "micro_volume_activity_cohort_design",
                    "design_id": "test-design",
                    "status": "precommitted_before_market_discovery",
                    "knowledge_policy": "market_data_only_no_retrospective_behavior_labels",
                    "factorial_cells": [
                        "baseline",
                        "context_only",
                        "volume_only",
                        "context_plus_volume",
                    ],
                    "trading_dates": ["2025-02-12"],
                    "candidates_per_date": 2,
                    "candidate_selection_rule": "earliest qualification then symbol",
                }
            ),
            encoding="utf-8",
        )
        return path

    def _discovery(self, root: Path, future_scale: float = 1.0) -> Path:
        date_root = root / "discovery" / "2025-02-12"
        date_root.mkdir(parents=True)
        pd.DataFrame(
            [
                {
                    "symbol": "LATE",
                    "previous_close": 2.0,
                    "first_market_qualified_bar_started_at": (
                        "2025-02-12T12:04:00+00:00"
                    ),
                    "first_market_qualified_at": "2025-02-12T12:05:00+00:00",
                    "target_high": 999.0 * future_scale,
                    "max_session_gain_pct": 999.0 * future_scale,
                    "max_session_rvol": 999.0 * future_scale,
                },
                {
                    "symbol": "BETA",
                    "previous_close": 3.0,
                    "first_market_qualified_bar_started_at": (
                        "2025-02-12T12:00:00+00:00"
                    ),
                    "first_market_qualified_at": "2025-02-12T12:01:00+00:00",
                    "target_high": 2.0 * future_scale,
                    "max_session_gain_pct": 2.0 * future_scale,
                    "max_session_rvol": 2.0 * future_scale,
                },
                {
                    "symbol": "ALFA",
                    "previous_close": 4.0,
                    "first_market_qualified_bar_started_at": (
                        "2025-02-12T12:00:00+00:00"
                    ),
                    "first_market_qualified_at": "2025-02-12T12:01:00+00:00",
                    "target_high": 1.0 * future_scale,
                    "max_session_gain_pct": 1.0 * future_scale,
                    "max_session_rvol": 1.0 * future_scale,
                },
                {
                    "symbol": "NONE",
                    "previous_close": 5.0,
                    "first_market_qualified_bar_started_at": None,
                    "first_market_qualified_at": None,
                    "target_high": 5000.0,
                    "max_session_gain_pct": 5000.0,
                    "max_session_rvol": 5000.0,
                },
            ]
        ).to_csv(date_root / "discovery.csv", index=False)
        (date_root / "manifest.json").write_text(
            json.dumps(
                {
                    "kind": "market_day_discovery",
                    "trading_date": "2025-02-12",
                }
            ),
            encoding="utf-8",
        )
        return root / "discovery"

    def test_selects_earliest_qualification_with_symbol_tie_break(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = build_selection(self._design(root), self._discovery(root))

        self.assertEqual([case["symbol"] for case in payload["cases"]], ["ALFA", "BETA"])
        self.assertEqual(
            payload["selection_columns_used"],
            ["first_market_qualified_at", "symbol"],
        )
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(
            payload["cases"][0]["first_market_qualified_bar_started_at"],
            "2025-02-12T12:00:00+00:00",
        )
        self.assertFalse(payload["policy_promotion_eligible"])

    def test_future_outcome_columns_cannot_change_selection(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            root_a = Path(first)
            root_b = Path(second)
            result_a = build_selection(
                self._design(root_a), self._discovery(root_a, future_scale=1.0)
            )
            result_b = build_selection(
                self._design(root_b), self._discovery(root_b, future_scale=-1000.0)
            )

        identity = lambda result: [
            (case["symbol"], case["first_market_qualified_at"])
            for case in result["cases"]
        ]
        self.assertEqual(identity(result_a), identity(result_b))

    def test_rejects_bar_start_masquerading_as_decision_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            discovery = self._discovery(root)
            path = discovery / "2025-02-12" / "discovery.csv"
            frame = pd.read_csv(path)
            frame.loc[
                frame["symbol"] == "ALFA",
                "first_market_qualified_bar_started_at",
            ] = "2025-02-12T12:01:00+00:00"
            frame.to_csv(path, index=False)

            with self.assertRaisesRegex(ValueError, "plus one minute"):
                build_selection(self._design(root), discovery)


if __name__ == "__main__":
    unittest.main()
