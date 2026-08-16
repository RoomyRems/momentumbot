from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from momentumbot.historical_data import asset_master_fingerprint
from momentumbot.snapshot import SnapshotError, load_indicator_warmup, load_snapshot


class SnapshotTests(unittest.TestCase):
    def _write_base(
        self,
        root: Path,
        *,
        universe_complete=True,
        conditional_universe=False,
        float_asof="2026-08-11T12:00:00-04:00",
        manifest_overrides=None,
    ):
        (root / "bars").mkdir()
        manifest = {"snapshot_id": "test", "universe_complete": universe_complete}
        if conditional_universe:
            assets = [
                {
                    "asset_class": "us_equity",
                    "asset_id": "test-id",
                    "attributes": [],
                    "exchange": "NASDAQ",
                    "name": "Test Corp",
                    "status": "active",
                    "symbol": "TEST",
                    "tradable": True,
                }
            ]
            asset_master_sha256 = asset_master_fingerprint(assets)
            (root / "asset_master.json").write_text(
                json.dumps(
                    {
                        "point_in_time_membership": False,
                        "sha256": asset_master_sha256,
                        "assets": assets,
                    }
                ),
                encoding="utf-8",
            )
            manifest.update(
                {
                    "universe_complete": False,
                    "point_in_time_universe_complete": False,
                    "universe_complete_relative_to_asset_master": True,
                    "universe_membership": {
                        "source_artifact": "asset_master.json",
                        "source_sha256": asset_master_sha256,
                    },
                    "evaluation_eligibility": {
                        "conditional_diagnostic": True,
                        "full_scanner_walk_forward": False,
                        "policy_promotion": False,
                    },
                }
            )
        if manifest_overrides:
            manifest.update(manifest_overrides)
        (root / "manifest.json").write_text(
            json.dumps(manifest),
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

    def test_conditional_asset_master_universe_is_rejected_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_base(root, conditional_universe=True)
            with self.assertRaisesRegex(SnapshotError, "allow_conditional_universe"):
                load_snapshot(root)

    def test_conditional_asset_master_universe_requires_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_base(root, conditional_universe=True)
            bars, contexts, news, manifest = load_snapshot(
                root,
                allow_conditional_universe=True,
            )
            self.assertEqual(set(bars), {"TEST"})
            self.assertEqual(set(contexts), {"TEST"})
            self.assertEqual(news, ())
            self.assertFalse(manifest["evaluation_eligibility"]["policy_promotion"])

    def test_conditional_universe_must_prohibit_policy_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_base(
                root,
                conditional_universe=True,
                manifest_overrides={
                    "evaluation_eligibility": {
                        "conditional_diagnostic": True,
                        "full_scanner_walk_forward": False,
                        "policy_promotion": True,
                    }
                },
            )
            with self.assertRaisesRegex(SnapshotError, "prohibit policy promotion"):
                load_snapshot(root, allow_conditional_universe=True)

    def test_conditional_universe_asset_master_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_base(root, conditional_universe=True)
            asset_master = json.loads(
                (root / "asset_master.json").read_text(encoding="utf-8")
            )
            asset_master["assets"][0]["symbol"] = "ALTERED"
            (root / "asset_master.json").write_text(
                json.dumps(asset_master),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SnapshotError, "fingerprint mismatch"):
                load_snapshot(root, allow_conditional_universe=True)

    def test_contradictory_universe_claim_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_base(
                root,
                manifest_overrides={"point_in_time_universe_complete": False},
            )
            with self.assertRaisesRegex(SnapshotError, "cannot declare"):
                load_snapshot(root, allow_conditional_universe=True)

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
