import unittest
from dataclasses import replace
from datetime import date, datetime, time, timezone
import json
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.historical_data import (
    _daily_scan_basis,
    _discovery_disposition,
    _scan_values,
    asset_master_fingerprint,
    asset_master_status_counts,
    discover_market_day,
    normalize_asset_master,
    write_discovery,
)
from momentumbot.models import current_general_2026


ET = ZoneInfo("America/New_York")


def _market_timestamp(day: date, at: time) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(day, at, ET)).tz_convert("UTC")


class _CompleteDiscoveryClient:
    def __init__(self, target: date) -> None:
        prior = [stamp.date() for stamp in pd.bdate_range(end=target, periods=61)][:-1]
        daily_rows = []
        for day in prior:
            daily_rows.append(
                {
                    "timestamp": pd.Timestamp(datetime.combine(day, time(20), timezone.utc)),
                    "open": 2.0,
                    "high": 2.1,
                    "low": 1.9,
                    "close": 2.0,
                    "volume": 100_000,
                }
            )
        daily_rows.append(
            {
                "timestamp": pd.Timestamp(datetime.combine(target, time(20), timezone.utc)),
                "open": 2.2,
                "high": 3.0,
                "low": 2.1,
                "close": 2.8,
                "volume": 1_000_000,
            }
        )
        self.daily = pd.DataFrame(daily_rows).set_index("timestamp")
        current_timestamp = _market_timestamp(target, time(7, 0))
        self.current = pd.DataFrame(
            [
                {
                    "timestamp": current_timestamp,
                    "open": 2.4,
                    "high": 2.6,
                    "low": 2.3,
                    "close": 2.5,
                    "volume": 1_000,
                }
            ]
        ).set_index("timestamp")
        history_rows = [
            {
                "timestamp": _market_timestamp(day, time(7, 0)),
                "open": 2.0,
                "high": 2.0,
                "low": 2.0,
                "close": 2.0,
                "volume": 100,
            }
            for day in prior[-50:]
        ]
        self.exact = pd.concat(
            [pd.DataFrame(history_rows).set_index("timestamp"), self.current]
        ).sort_index()
        self.coarse = pd.DataFrame(history_rows).set_index("timestamp")

    def bars_batched(self, symbols, **kwargs):
        timeframe = kwargs["timeframe"]
        if timeframe == "1Day":
            frame = self.daily
        elif timeframe == "15Min":
            frame = self.coarse
        elif timeframe == "1Min":
            start = pd.Timestamp(kwargs["start"])
            end = pd.Timestamp(kwargs["end"])
            frame = self.exact if (end - start).days > 1 else self.current
        else:
            raise AssertionError(timeframe)
        return {symbol: frame.copy() for symbol in symbols}


class HistoricalDataTests(unittest.TestCase):
    def _frame(self, rows):
        frame = pd.DataFrame(rows)
        frame["timestamp"] = pd.to_datetime(frame.pop("timestamp"), utc=True)
        return frame.set_index("timestamp")

    def test_daily_scan_basis_normalizes_same_day_reverse_split(self):
        raw = self._frame(
            [
                {
                    "timestamp": "2026-07-08T04:00:00Z",
                    "close": 0.4805,
                    "high": 0.4989,
                    "low": 0.4277,
                },
                {
                    "timestamp": "2026-07-09T04:00:00Z",
                    "close": 7.40,
                    "high": 7.6399,
                    "low": 6.80,
                },
            ]
        )
        split = self._frame(
            [
                {
                    "timestamp": "2026-07-08T04:00:00Z",
                    "close": 7.208,
                    "high": 7.484,
                    "low": 6.416,
                },
                {
                    "timestamp": "2026-07-09T04:00:00Z",
                    "close": 7.40,
                    "high": 7.6399,
                    "low": 6.80,
                },
            ]
        )

        basis = _daily_scan_basis(raw, split, date(2026, 7, 9))
        self.assertIsNotNone(basis)
        prior_close, high, low = basis

        self.assertAlmostEqual(prior_close, 7.208)
        self.assertAlmostEqual(high, 7.6399)
        self.assertAlmostEqual(low, 6.80)
        normalized_gain = (high / prior_close - 1.0) * 100.0
        naive_raw_gain = (high / 0.4805 - 1.0) * 100.0
        self.assertLess(normalized_gain, 10.0)
        self.assertGreater(naive_raw_gain, 1000.0)

    def test_daily_scan_basis_is_unchanged_without_split(self):
        raw = self._frame(
            [
                {
                    "timestamp": "2026-07-08T04:00:00Z",
                    "close": 5.00,
                    "high": 5.20,
                    "low": 4.80,
                },
                {
                    "timestamp": "2026-07-09T04:00:00Z",
                    "close": 6.00,
                    "high": 6.50,
                    "low": 5.50,
                },
            ]
        )

        basis = _daily_scan_basis(raw, raw, date(2026, 7, 9))
        self.assertIsNotNone(basis)
        prior_close, high, low = basis

        self.assertEqual(prior_close, 5.00)
        self.assertEqual(high, 6.50)
        self.assertEqual(low, 5.50)

    def test_asset_master_fingerprint_is_order_independent(self):
        first = [
            {
                "id": "2",
                "class": "us_equity",
                "exchange": "nyse",
                "symbol": "BBB",
                "name": "Beta",
                "status": "inactive",
                "tradable": False,
                "attributes": ["z", "a"],
            },
            {
                "id": "1",
                "class": "us_equity",
                "exchange": "nasdaq",
                "symbol": "AAA",
                "name": "Alpha",
                "status": "active",
                "tradable": True,
                "attributes": [],
            },
        ]
        second = [dict(first[1]), dict(first[0], attributes=["a", "z"])]

        self.assertEqual(asset_master_fingerprint(first), asset_master_fingerprint(second))
        self.assertEqual(
            [row["symbol"] for row in normalize_asset_master(first)],
            ["AAA", "BBB"],
        )

    def test_asset_master_status_counts_preserve_inactive_members(self):
        rows = [
            {"symbol": "AAA", "status": "active"},
            {"symbol": "BBB", "status": "inactive"},
            {"symbol": "CCC", "status": "inactive"},
        ]
        self.assertEqual(
            asset_master_status_counts(rows),
            {"active": 1, "inactive": 2},
        )

    def test_discovery_disposition_fails_closed_at_first_missing_stage(self):
        complete = {
            "daily_scan_basis_available": True,
            "daily_price_gain_prefilter_pass": True,
            "average_daily_volume_50_available": True,
            "raw_target_minute_bars_present": True,
            "split_target_minute_bars_present": True,
            "rvol_history_sessions": 50,
            "coarse_rvol_prefilter_pass": True,
            "causal_market_qualified": True,
        }
        self.assertEqual(
            _discovery_disposition(complete, required_rvol_sessions=50),
            "causal_market_candidate",
        )
        missing = dict(complete, raw_target_minute_bars_present=False)
        self.assertEqual(
            _discovery_disposition(missing, required_rvol_sessions=50),
            "excluded_missing_raw_target_minute_bars",
        )
        insufficient = dict(complete, rvol_history_sessions=49)
        self.assertEqual(
            _discovery_disposition(insufficient, required_rvol_sessions=50),
            "excluded_insufficient_rvol_history_sessions",
        )

    def test_discovery_audit_accounts_for_complete_candidate_path(self):
        target = date(2025, 4, 3)
        result = discover_market_day(
            _CompleteDiscoveryClient(target),
            trading_date=target,
            profile=current_general_2026(),
            assets=[
                {
                    "id": "FIGI-AAA",
                    "class": "us_equity",
                    "exchange": "NASDAQ",
                    "symbol": "AAA",
                    "name": "AAA Incorporated",
                    "status": "active",
                    "tradable": True,
                    "attributes": [],
                }
            ],
        )

        self.assertEqual(result.market_candidate_count, 1)
        self.assertEqual(len(result.acquisition_audit), 1)
        audit = result.acquisition_audit[0]
        self.assertEqual(audit.symbol, "AAA")
        self.assertEqual(audit.disposition, "causal_market_candidate")
        self.assertTrue(audit.daily_scan_basis_available)
        self.assertTrue(audit.coarse_rvol_prefilter_pass)
        self.assertTrue(audit.exact_rvol_observation_available)
        self.assertTrue(audit.causal_market_qualified)
        self.assertEqual(
            audit.first_market_qualified_bar_started_at,
            "2025-04-03T11:00:00+00:00",
        )
        self.assertEqual(
            audit.first_market_qualified_at,
            "2025-04-03T11:01:00+00:00",
        )
        row = result.rows[0]
        self.assertEqual(
            row.first_market_qualified_bar_started_at,
            audit.first_market_qualified_bar_started_at,
        )
        self.assertEqual(row.first_market_qualified_at, audit.first_market_qualified_at)
        with tempfile.TemporaryDirectory() as raw:
            write_discovery(result, Path(raw), trading_date=target)
            manifest = json.loads(
                (Path(raw) / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["schema_version"], 4)
            self.assertEqual(manifest["decision_availability_offset_seconds"], 60)
            self.assertEqual(
                manifest["candidate_bar_start_field"],
                "first_market_qualified_bar_started_at",
            )
            self.assertTrue(manifest["qualification_timing_validated"])
            self.assertEqual(manifest["dual_timestamp_candidate_count"], 1)
        invalid_row = replace(
            row,
            first_market_qualified_at=row.first_market_qualified_bar_started_at,
        )
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(ValueError, "plus one minute"):
                write_discovery(
                    replace(result, rows=(invalid_row,)),
                    Path(raw),
                    trading_date=target,
                )

    def test_scan_cutoff_is_applied_when_one_minute_bar_is_available(self):
        target = date(2025, 4, 3)
        index = pd.DatetimeIndex(
            [
                _market_timestamp(target, time(9, 58)),
                _market_timestamp(target, time(9, 59)),
            ]
        )
        frame = pd.DataFrame(
            {
                "close": [3.0, 3.0],
                "volume": [1_000, 1_000],
            },
            index=index,
        )
        rvol = pd.Series([6.0, 6.0], index=index)

        _, _, _, mask = _scan_values(
            frame,
            previous_close=2.0,
            rvol_curve=rvol,
            profile=current_general_2026(),
        )

        self.assertTrue(bool(mask.iloc[0]))  # 09:58 bar is known at 09:59.
        self.assertFalse(bool(mask.iloc[1]))  # 09:59 bar is known at 10:00.


if __name__ == "__main__":
    unittest.main()
