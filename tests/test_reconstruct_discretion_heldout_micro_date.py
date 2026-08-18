from __future__ import annotations

from datetime import date, time
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from momentumbot.identity_resolved_universe import json_fingerprint
from momentumbot.research.discretion_heldout_panel import REGISTERED_DATES
from scripts.reconstruct_discretion_heldout_micro_date import (
    FROZEN_MICRO_POLICY_FINGERPRINT,
    SOURCE_ARTIFACT_ID,
    _bind_session_support_to_frozen_scanner_bars,
    _causal_action_bars,
    _qualification_anchor,
    _unavailable_runtime,
    _validate_source_runtime,
    _write_deterministic_gzip_csv,
)


class ReconstructDiscretionHeldoutMicroDateTests(unittest.TestCase):
    def test_replay_is_pinned_to_the_registered_micro_policy(self):
        from momentumbot.micro_policy import micro_v0_1_policy

        self.assertEqual(
            micro_v0_1_policy().fingerprint,
            FROZEN_MICRO_POLICY_FINGERPRINT,
        )

    def _source(self):
        payload = {
            "schema_version": 1,
            "artifact_id": SOURCE_ARTIFACT_ID,
            "dates": list(REGISTERED_DATES),
            "registration": {"label_content_review_started": False},
            "causal_boundary": {
                "uses_benchmark_labels": False,
                "uses_ross_actions": False,
                "uses_retrospective_trade_outcomes": False,
                "uses_later_price_outcomes": False,
                "top_n_selection_applied": False,
                "all_market_candidates_retained": True,
                "provider_independent_scanner_replay_validated": True,
            },
        }
        payload["content_sha256"] = json_fingerprint(payload)
        return payload

    def test_source_requires_frozen_unlabeled_all_candidate_runtime(self):
        payload = self._source()
        _validate_source_runtime(
            payload, expected_content_sha256=payload["content_sha256"]
        )

        labeled = self._source()
        labeled["registration"]["label_content_review_started"] = True
        labeled["content_sha256"] = json_fingerprint(
            {key: value for key, value in labeled.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "labels were opened"):
            _validate_source_runtime(
                labeled, expected_content_sha256=labeled["content_sha256"]
            )

        filtered = self._source()
        filtered["causal_boundary"]["top_n_selection_applied"] = True
        filtered["content_sha256"] = json_fingerprint(
            {key: value for key, value in filtered.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "top_n_selection_applied"):
            _validate_source_runtime(
                filtered, expected_content_sha256=filtered["content_sha256"]
            )

    def test_anchor_uses_completed_bar_decision_without_intraminute_backdating(self):
        candidate = {
            "first_market_qualified_bar_started_at": "2026-07-10T10:59:00+00:00",
            "first_market_qualified_at": "2026-07-10T11:00:00+00:00",
        }
        bar_start, decision = _qualification_anchor(
            candidate,
            trading_date=date(2026, 7, 10),
            session_start=time(7, 0),
            entry_cutoff=time(10, 0),
        )
        self.assertEqual((decision - bar_start).total_seconds(), 60)
        self.assertEqual(decision.isoformat(), "2026-07-10T11:00:00+00:00")

        changed = dict(candidate)
        changed["first_market_qualified_at"] = "2026-07-10T10:59:30+00:00"
        with self.assertRaisesRegex(ValueError, "plus one minute"):
            _qualification_anchor(
                changed,
                trading_date=date(2026, 7, 10),
                session_start=time(7, 0),
                entry_cutoff=time(10, 0),
            )

    def test_deterministic_gzip_and_unavailable_state_are_hash_bound(self):
        frame = pd.DataFrame(
            {"price": [2.0], "size": [100]},
            index=pd.DatetimeIndex(
                ["2026-07-10T11:00:00Z"], name="timestamp"
            ),
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            first = _write_deterministic_gzip_csv(frame, root / "first.csv.gz")
            second = _write_deterministic_gzip_csv(frame, root / "second.csv.gz")
            self.assertEqual(first["sha256"], second["sha256"])
            with gzip.open(root / "first.csv.gz", "rt", encoding="utf-8") as handle:
                self.assertEqual(
                    handle.read(),
                    "timestamp,price,size\n2026-07-10 11:00:00+00:00,2.0,100\n",
                )

        runtime = _unavailable_runtime(
            symbol="AAA",
            trading_date=date(2026, 7, 10),
            qualified_at=pd.Timestamp("2026-07-10T11:00:00Z"),
            reason="no_sip_trades_after_candidate_activation",
            policy_id="micro-v0.1",
            policy_fingerprint="a" * 64,
            source_hashes={"heldout_runtime": "b" * 64},
        )
        claimed = runtime.pop("content_sha256")
        self.assertEqual(claimed, json_fingerprint(runtime))
        self.assertIsNone(runtime["plan_count"])
        self.assertFalse(runtime["policy_promotion_eligible"])

    def test_action_bars_require_completion_before_entry_cutoff(self):
        bars = pd.DataFrame(
            {"close": [2.0, 2.1, 2.2]},
            index=pd.DatetimeIndex(
                [
                    "2026-07-10T13:59:40Z",
                    "2026-07-10T13:59:50Z",
                    "2026-07-10T14:00:00Z",
                ],
                name="timestamp",
            ),
        )
        kept = _causal_action_bars(
            bars,
            qualified_at=pd.Timestamp("2026-07-10T13:59:40Z"),
            replay_end=pd.Timestamp("2026-07-10T14:00:00Z"),
            bar_interval_seconds=10,
        )
        self.assertEqual(
            list(kept.index),
            [pd.Timestamp("2026-07-10T13:59:40Z")],
        )

    def test_session_support_uses_frozen_bar_grid_and_blocks_drift(self):
        index = pd.DatetimeIndex(
            ["2026-07-10T11:00:00Z", "2026-07-10T11:01:00Z"],
            name="timestamp",
        )
        session = pd.DataFrame(
            {
                "open": [2.0, 2.1],
                "high": [2.2, 2.3],
                "low": [1.9, 2.0],
                "close": [2.1, 2.2],
                "volume": [100, 200],
            },
            index=index,
        )
        frozen = pd.DataFrame(
            {"close": [2.1], "volume": [100]},
            index=index[:1],
        )
        bound = _bind_session_support_to_frozen_scanner_bars(
            session, frozen, symbol="AAA"
        )
        self.assertEqual(list(bound.index), list(index[:1]))
        self.assertEqual(float(bound.iloc[0]["high"]), 2.2)

        drifted = frozen.copy()
        drifted.loc[index[0], "close"] = 2.11
        with self.assertRaisesRegex(ValueError, "close drifted"):
            _bind_session_support_to_frozen_scanner_bars(
                session, drifted, symbol="AAA"
            )


if __name__ == "__main__":
    unittest.main()
