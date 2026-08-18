from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from momentumbot.identity_resolved_universe import json_fingerprint
from momentumbot.micro_policy import micro_v0_1_policy
from scripts.summarize_discretion_heldout_micro_runtime import (
    DATE_ARTIFACT_ID,
    SOURCE_MANIFEST_CONTENT_SHA256,
    build_panel_manifest,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["content_sha256"] = json_fingerprint(payload)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


class SummarizeDiscretionHeldoutMicroRuntimeTests(unittest.TestCase):
    def _date(
        self,
        root: Path,
        trading_date: str,
        *,
        symbol: str,
        plans: int | None,
        fills: int | None,
    ) -> None:
        policy = micro_v0_1_policy()
        symbol_root = root / trading_date / symbol
        activation = f"{trading_date}T11:00:00+00:00"
        common: dict[str, object] = {
            "schema_version": 1,
            "symbol": symbol,
            "trading_date": trading_date,
            "candidate_qualified_at": activation,
            "plan_count": plans,
            "filled_count": fills,
            "frozen_policy_id": policy.policy_id,
            "frozen_policy_fingerprint": policy.fingerprint,
            "source_hashes": {
                "heldout_runtime": SOURCE_MANIFEST_CONTENT_SHA256,
            },
            "policy_promotion_eligible": False,
        }
        if plans is None:
            common.update(
                {
                    "artifact_type": "micro_candidate_runtime_replay_unavailable",
                    "status": "missing_current_session_minute_support_input",
                    "knowledge_policy": {
                        "uses_benchmark_labels": False,
                        "uses_later_price_outcomes": False,
                        "uses_retrospective_trade_outcomes": False,
                        "uses_ross_actions": False,
                    },
                }
            )
            status = common["status"]
        else:
            inputs = {}
            for name in (
                "trades",
                "bars_10s",
                "support",
                "session_1m",
                "ema_warmup_1m",
            ):
                filename = f"{name}.csv.gz"
                path = symbol_root / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                with gzip.GzipFile(filename=str(path), mode="wb", mtime=0) as handle:
                    handle.write(b"timestamp,value\n")
                inputs[name] = {
                    "path": filename,
                    "row_count": 0,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            common.update(
                {
                    "artifact_type": "micro_candidate_runtime_replay",
                    "knowledge_policy": (
                        "runtime_market_data_only_no_retrospective_labels"
                    ),
                    "retrospective_behavior_labels_loaded": False,
                    "input_files": inputs,
                }
            )
            status = "replayed"
        _write_json(symbol_root / "runtime-replay.json", common)
        runtime_hash = json.loads(
            (symbol_root / "runtime-replay.json").read_text()
        )["content_sha256"]
        manifest = {
            "schema_version": 1,
            "artifact_id": DATE_ARTIFACT_ID,
            "trading_date": trading_date,
            "source_heldout_runtime_content_sha256": (
                SOURCE_MANIFEST_CONTENT_SHA256
            ),
            "frozen_micro_policy": {
                "policy_id": policy.policy_id,
                "fingerprint": policy.fingerprint,
                "status": policy.status,
            },
            "candidate_count": 1,
            "replayed_candidate_count": int(plans is not None),
            "unavailable_candidate_count": int(plans is None),
            "total_plan_count": plans or 0,
            "total_filled_count": fills or 0,
            "candidate_results": {
                symbol: {
                    "status": status,
                    "candidate_qualified_at": activation,
                    "plan_count": plans,
                    "filled_count": fills,
                    "runtime_content_sha256": runtime_hash,
                }
            },
            "knowledge_policy": {
                "uses_ross_actions": False,
                "uses_benchmark_labels": False,
                "uses_retrospective_trade_outcomes": False,
                "uses_later_price_outcomes": False,
                "all_causal_market_candidates_retained": True,
            },
            "eligibility": {"policy_promotion_eligible": False},
        }
        _write_json(root / trading_date / "manifest.json", manifest)

    def test_panel_separates_zero_activity_from_unavailable_data(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self._date(
                root,
                "2026-07-10",
                symbol="AAA",
                plans=0,
                fills=0,
            )
            self._date(
                root,
                "2026-07-13",
                symbol="BBB",
                plans=None,
                fills=None,
            )
            payload = build_panel_manifest(
                root, dates=("2026-07-10", "2026-07-13")
            )
            self.assertEqual(payload["totals"]["candidate_count"], 2)
            self.assertEqual(payload["totals"]["replayed_candidate_count"], 1)
            self.assertEqual(payload["totals"]["unavailable_candidate_count"], 1)
            self.assertEqual(payload["totals"]["candidates_with_zero_plans"], 1)
            self.assertEqual(payload["totals"]["total_plan_emission_count"], 0)
            claimed = payload.pop("content_sha256")
            self.assertEqual(claimed, json_fingerprint(payload))

    def test_tampered_frozen_input_fails_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self._date(
                root,
                "2026-07-10",
                symbol="AAA",
                plans=1,
                fills=1,
            )
            path = root / "2026-07-10" / "AAA" / "trades.csv.gz"
            path.write_bytes(path.read_bytes() + b"tamper")
            with self.assertRaisesRegex(ValueError, "frozen input file mismatch"):
                build_panel_manifest(root, dates=("2026-07-10",))


if __name__ == "__main__":
    unittest.main()
