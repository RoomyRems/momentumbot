from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from momentumbot.snapshot import SnapshotError, load_indicator_warmup, load_snapshot


class SnapshotTests(unittest.TestCase):
    def _write_base(
        self,
        root: Path,
        *,
        universe_complete=True,
        float_asof="2026-08-11T12:00:00-04:00",
    ):
        (root / "bars").mkdir()
        (root / "manifest.json").write_text(
            json.dumps({"snapshot_id": "test", "universe_complete": universe_complete}),
            encoding="utf-8",
        )
        pd.DataFrame(
            [{
                "symbol": "TEST",
                "previous_close": 4.0,
                "average_daily_volume_50": 100_000,
                "float_shares": 5_000_000,
                "float_asof": float_asof,
            }]
        ).to_csv(root / "contexts.csv", index=False)
        pd.DataFrame(
            [{
                "timestamp": "2026-08-12T11:00:00Z",
                "open": 4.0,
                "high": 4.2,
                "low": 3.9,
                "close": 4.1,
                "volume": 100_000,
            }]
        ).to_csv(root / "bars" / "TEST.csv", index=False)

    def test_snapshot_requires_explicit_complete_universe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_base(root, universe_complete=False)
            with self.assertRaisesRegex(SnapshotError, "universe_complete"):
                load_snapshot(root)

    def test_point_in_time_float_and_news_are_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_base(root)
            pd.DataFrame(
                [{"symbol":"TEST","published_at":"2026-08-12T11:05:00Z","headline_id":"n1"}]
            ).to_csv(root / "news.csv", index=False)
            bars, contexts, news, manifest = load_snapshot(root)
            self.assertEqual(manifest["snapshot_id"], "test")
            self.assertIsNotNone(contexts["TEST"].float_asof)
            self.assertEqual(news[0].headline_id, "n1")
            self.assertIsNotNone(bars["TEST"].index.tz)

    def test_float_without_asof_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_base(root, float_asof="")
            with self.assertRaisesRegex(SnapshotError, "float_asof"):
                load_snapshot(root)

    def test_missing_structure_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SnapshotError):
                load_snapshot(tmp)

    def test_indicator_warmup_is_optional_and_loaded_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_base(root)
            self.assertEqual(load_indicator_warmup(root), {})
            (root / "warmup").mkdir()
            pd.DataFrame(
                [{
                    "timestamp": "2026-08-11T19:59:00Z",
                    "open": 3.8,
                    "high": 3.9,
                    "low": 3.7,
                    "close": 3.85,
                    "volume": 90_000,
                }]
            ).to_csv(root / "warmup" / "TEST.csv", index=False)
            warmup = load_indicator_warmup(root)
            self.assertEqual(set(warmup), {"TEST"})
            self.assertEqual(float(warmup["TEST"].iloc[0]["close"]), 3.85)
            self.assertIsNotNone(warmup["TEST"].index.tz)


if __name__ == "__main__":
    unittest.main()
