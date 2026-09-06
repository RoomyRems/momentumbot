from __future__ import annotations

from contextlib import ExitStack
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from momentumbot.research.prospective_daily_source import MicroTriggerDecision
from momentumbot.research.sealed_historical_source_checkpoint_v01 import canonical_fingerprint
from momentumbot.research import sealed_historical_micro_runtime_v01 as runtime

ROOT = Path(__file__).resolve().parents[1]


def frozen_write(path: Path, body: dict) -> dict:
    value = {**body, "content_sha256": canonical_fingerprint(body)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n")
    return value


class SealedHistoricalMicroRuntimeV01Tests(unittest.TestCase):
    def test_registered_contract_is_exact_and_narrow(self):
        contract = runtime.validate_runtime_contract(
            ROOT / "research/strategy/sealed-historical-micro-runtime-v0.1.json"
        )
        self.assertTrue(contract["execution_boundary"]["micro_runtime_execution_authorized"])
        self.assertFalse(contract["execution_boundary"]["backtesting_authorized"])
        self.assertFalse(contract["execution_boundary"]["retrospective_labels_or_transcripts"])
        self.assertFalse(contract["execution_boundary"]["market_provider_access"])

    def test_causal_basis_uses_only_completed_preactivation_pairs(self):
        index = pd.DatetimeIndex([
            "2025-06-10T11:00:00Z", "2025-06-10T11:01:00Z", "2025-06-10T11:02:00Z"
        ])
        raw = pd.Series([2.0, 2.2, 99.0], index=index)
        split = pd.Series([100.0, 110.0, 1.0], index=index)
        factor, evidence = runtime.causal_raw_to_split_factor(
            raw, split, qualified_at=pd.Timestamp("2025-06-10T11:02:00Z")
        )
        self.assertEqual(factor, 0.02)
        self.assertEqual(evidence["pair_count"], 2)
        self.assertEqual(evidence["last_pair_available_at"], "2025-06-10T11:02:00+00:00")

    def test_causal_basis_fails_when_missing_or_unstable(self):
        index = pd.DatetimeIndex(["2025-06-10T11:00:00Z", "2025-06-10T11:01:00Z"])
        with self.assertRaisesRegex(ValueError, "unavailable"):
            runtime.causal_raw_to_split_factor(
                pd.Series([2.0, 2.1], index=index), pd.Series([2.0, 2.1], index=index),
                qualified_at=pd.Timestamp("2025-06-10T11:00:30Z"),
            )
        with self.assertRaisesRegex(ValueError, "stable"):
            runtime.causal_raw_to_split_factor(
                pd.Series([2.0, 4.0], index=index), pd.Series([2.0, 2.0], index=index),
                qualified_at=pd.Timestamp("2025-06-10T11:03:00Z"),
            )

    def test_warmup_normalization_changes_prices_not_volume(self):
        index = pd.DatetimeIndex(["2025-06-09T12:00:00Z"])
        frame = pd.DataFrame({
            "open": [100.0], "high": [110.0], "low": [90.0], "close": [105.0],
            "volume": [123], "vwap": [102.0],
        }, index=index)
        observed = runtime.normalize_warmup_to_raw(frame, 0.02)
        self.assertEqual(observed.loc[index[0], "close"], 2.1)
        self.assertEqual(observed.loc[index[0], "volume"], 123)

    def test_historical_adapter_preserves_activation_and_explicit_no_trigger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = root / "plan"
            output = root / "out"
            micro = root / "micro"
            session = root / "session"
            day = "2025-05-30"
            activation = {
                "activation_id": "activation-" + "a" * 64,
                "symbol": "TEST", "candidate_qualified_at": "2025-05-30T11:02:00+00:00",
                "scanner_record_content_sha256": "b" * 64,
                "scanner_snapshot_content_sha256": "c" * 64,
                "eligible_strategy_profile_ids": ["current-general-2026", "current-small-account-2026"],
            }
            day_plan = frozen_write(plan / "dates" / f"{day}.json", {"activations": [activation]})
            trade_path = micro / "dates" / day / "TEST-sip_trades.jsonl.gz"
            warmup_path = micro / "dates" / day / "TEST-ema_warmup_1m_split.jsonl.gz"
            session_path = session / "dates" / day / "TEST-session_1m_raw.jsonl.gz"
            for path, rows in (
                (trade_path, [{"t": "2025-05-30T11:02:01+00:00", "p": 2.1, "s": 100, "i": 1, "x": "Q", "z": "C", "c": []}]),
                (warmup_path, [{"t": "2025-05-29T20:00:00+00:00", "o": 100, "h": 101, "l": 99, "c": 100, "v": 10, "n": 1, "vw": 100}]),
                (session_path, [{"t": "2025-05-30T11:00:00+00:00", "o": 2, "h": 2.2, "l": 1.9, "c": 2, "v": 100, "n": 2, "vw": 2}]),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                with gzip.open(path, "wt") as handle:
                    for row in rows:
                        handle.write(json.dumps(row) + "\n")
            receipts = {
                "t": {"path": f"dates/{day}/TEST-sip_trades.jsonl.gz", "logical_sha256": "d" * 64},
                "w": {"path": f"dates/{day}/TEST-ema_warmup_1m_split.jsonl.gz", "logical_sha256": "e" * 64},
                "s": {"path": f"dates/{day}/TEST-session_1m_raw.jsonl.gz", "logical_sha256": "f" * 64},
            }
            index = pd.DatetimeIndex(["2025-05-30T11:00:00Z"])
            source = type("Source", (), {
                "candidate_raw_minute_bars_by_symbol": {"TEST": pd.DataFrame({"close": [2.0], "volume": [100.0]}, index=index)},
                "rank_split_minute_bars_by_symbol": {"TEST": pd.DataFrame({"close": [100.0]}, index=index)},
            })()
            validated = {"micro_receipts": receipts, "session_receipts": receipts}
            support = pd.DataFrame({"vwap": [2.0], "ema": [2.0]}, index=pd.DatetimeIndex(["2025-05-30T11:01:00Z"]))
            with ExitStack() as stack:
                stack.enter_context(patch.object(runtime, "EXPECTED_DATES", (day,)))
                stack.enter_context(patch.object(runtime, "validate_runtime_inputs", return_value=validated))
                stack.enter_context(patch.object(runtime, "load_scanner_source_input_bundle", return_value=(source, {"content_sha256": "1" * 64})))
                aggregate = stack.enter_context(patch.object(runtime, "aggregate_trade_bars", return_value=pd.DataFrame()))
                completed = stack.enter_context(patch.object(runtime, "completed_bar_support_series", return_value=support))
                triggers = stack.enter_context(patch.object(runtime, "build_micro_trigger_decisions", return_value=[]))
                result = runtime.execute_runtime(
                    snapshot_root=root / "snapshot", micro_input_root=micro, micro_input_zip=root / "micro.zip",
                    session_input_root=session, session_input_zip=root / "session.zip", plan_root=plan,
                    contract_path=root / "contract.json", output_root=output,
                )
            self.assertEqual(result["activation_count"], 1)
            self.assertEqual(result["decision_count"], 0)
            self.assertEqual(result["no_trigger_activation_count"], 1)
            daily = json.loads((output / "dates" / f"{day}.json").read_text())
            self.assertEqual(daily["activations"], [activation])
            self.assertEqual(daily["outcomes"][0]["status"], "no_trigger")
            with patch.object(runtime, "EXPECTED_DATES", (day,)):
                observed = runtime.validate_runtime_output(output_root=output, plan_root=plan)
            self.assertEqual(observed["activation_count"], 1)
            aggregate.assert_called_once()
            completed.assert_called_once()
            triggers.assert_called_once()

    def test_output_validator_rejects_missing_date_and_future_basis(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "out"
            plan = root / "plan"
            output.mkdir()
            frozen_write(output / "manifest.json", {})
            with self.assertRaisesRegex(ValueError, "inventory"):
                runtime.validate_runtime_output(output_root=output, plan_root=plan)

    def test_source_contains_no_provider_or_retrospective_entrypoint(self):
        text = (ROOT / "src/momentumbot/research/sealed_historical_micro_runtime_v01.py").read_text()
        self.assertNotIn("urllib", text)
        self.assertNotIn("ALPACA_API", text)
        self.assertNotIn("transcript", text.lower().replace("retrospective_labels_or_transcripts", ""))
        self.assertIn("aggregate_trade_bars", text)
        self.assertIn("completed_bar_support_series", text)
        self.assertIn("build_micro_trigger_decisions", text)


if __name__ == "__main__":
    unittest.main()
