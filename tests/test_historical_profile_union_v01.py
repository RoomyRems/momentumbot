from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date, datetime, time, timezone
import unittest
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.causal_market_discovery_v03 import (
    CAUSAL_MARKET_CANDIDATES_V0_3_ARTIFACT_ID,
    CAUSAL_MARKET_DISCOVERY_V0_3_POLICY_ID,
    strategy_profile_manifest,
)
from momentumbot.historical_data_v03 import (
    LEGACY_MIXED_GAIN_BASIS,
    SPLIT_CONSISTENT_GAIN_BASIS,
    discover_market_day,
)
from momentumbot.historical_profile_union_v01 import (
    GENERAL_PROFILE_FINGERPRINT,
    HISTORICAL_PROFILE_UNION_V0_1_FINGERPRINT,
    HISTORICAL_PROFILE_UNION_V0_1_ID,
    SMALL_ACCOUNT_PROFILE_FINGERPRINT,
    derive_historical_profile_union_v0_1,
    historical_profile_union_v0_1,
    historical_profile_union_v0_1_manifest,
    profile_union_coverage_failures,
    profile_union_covers,
    validate_historical_profile_union_v0_1,
)
from momentumbot.models import (
    StrategyProfile,
    current_general_2026,
    current_small_account_2026,
)
from scripts.build_identity_resolved_market_discovery_v04 import (
    main as build_market_discovery,
    validate_fixed_acquisition_mode,
)


ET = ZoneInfo("America/New_York")


def _market_timestamp(day: date, at: time) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(day, at, ET)).tz_convert("UTC")


class _LowPriceDiscoveryClient:
    """Provider-free bars for one $1.75 small-account-only opportunity."""

    def __init__(self, target: date) -> None:
        prior = [stamp.date() for stamp in pd.bdate_range(end=target, periods=61)][:-1]
        daily_rows = [
            {
                "timestamp": pd.Timestamp(
                    datetime.combine(day, time(20), timezone.utc)
                ),
                "open": 1.0,
                "high": 1.05,
                "low": 0.95,
                "close": 1.0,
                "volume": 100_000,
            }
            for day in prior
        ]
        daily_rows.append(
            {
                "timestamp": pd.Timestamp(
                    datetime.combine(target, time(20), timezone.utc)
                ),
                "open": 1.60,
                "high": 1.80,
                "low": 1.55,
                "close": 1.75,
                "volume": 1_000_000,
            }
        )
        self.daily = pd.DataFrame(daily_rows).set_index("timestamp")
        current_timestamp = _market_timestamp(target, time(7, 0))
        self.current = pd.DataFrame(
            [
                {
                    "timestamp": current_timestamp,
                    "open": 1.70,
                    "high": 1.80,
                    "low": 1.65,
                    "close": 1.75,
                    "volume": 1_000,
                }
            ]
        ).set_index("timestamp")
        history_rows = [
            {
                "timestamp": _market_timestamp(day, time(7, 0)),
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
                "volume": 100,
            }
            for day in prior[-50:]
        ]
        self.coarse = pd.DataFrame(history_rows).set_index("timestamp")
        self.exact = pd.concat([self.coarse, self.current]).sort_index()

    def bars_batched(
        self,
        symbols: list[str],
        **kwargs: object,
    ) -> dict[str, pd.DataFrame]:
        timeframe = kwargs["timeframe"]
        if timeframe == "1Day":
            frame = self.daily
        elif timeframe == "15Min":
            frame = self.coarse
        elif timeframe == "1Min":
            start = pd.Timestamp(kwargs["start"])
            end = pd.Timestamp(kwargs["end"])
            frame = self.exact if end - start > pd.Timedelta(days=1) else self.current
        else:
            raise AssertionError(f"unexpected timeframe: {timeframe}")
        return {symbol: frame.copy() for symbol in symbols}


class HistoricalProfileUnionV01Tests(unittest.TestCase):
    def test_union_is_exactly_derived_without_mutating_strategy_profiles(self) -> None:
        general = current_general_2026()
        small = current_small_account_2026()
        before = (asdict(general), asdict(small))

        union = derive_historical_profile_union_v0_1(general, small)

        self.assertEqual((asdict(general), asdict(small)), before)
        self.assertEqual(union.name, HISTORICAL_PROFILE_UNION_V0_1_ID)
        self.assertEqual(union.min_price, 1.50)
        self.assertEqual(union.max_price, 20.0)
        self.assertEqual(union.min_percent_gain, 10.0)
        self.assertEqual(union.min_relative_volume, 5.0)
        self.assertEqual(union.max_float_shares, 10_000_000)
        self.assertIsNone(union.require_top_gainer_rank)
        self.assertEqual(
            strategy_profile_manifest(general)["fingerprint"],
            GENERAL_PROFILE_FINGERPRINT,
        )
        self.assertEqual(
            strategy_profile_manifest(small)["fingerprint"],
            SMALL_ACCOUNT_PROFILE_FINGERPRINT,
        )
        self.assertEqual(
            strategy_profile_manifest(union)["fingerprint"],
            HISTORICAL_PROFILE_UNION_V0_1_FINGERPRINT,
        )

    def test_union_proves_coverage_of_both_frozen_profiles(self) -> None:
        union = historical_profile_union_v0_1()
        general = current_general_2026()
        small = current_small_account_2026()

        self.assertTrue(profile_union_covers(union, general))
        self.assertTrue(profile_union_covers(union, small))
        self.assertEqual(profile_union_coverage_failures(union, general), ())
        self.assertEqual(profile_union_coverage_failures(union, small), ())
        self.assertIn(
            "minimum price",
            profile_union_coverage_failures(general, small),
        )
        manifest = historical_profile_union_v0_1_manifest()
        self.assertEqual(
            manifest["coverage"],
            {
                "current-general-2026": True,
                "current-small-account-2026": True,
            },
        )
        self.assertFalse(manifest["strategy_profiles_modified"])

    def test_union_rejects_changed_parent_or_changed_union(self) -> None:
        changed_parent = replace(current_small_account_2026(), min_price=1.49)
        with self.assertRaisesRegex(ValueError, "frozen strategy profile changed"):
            derive_historical_profile_union_v0_1(
                current_general_2026(),
                changed_parent,
            )
        changed_union = replace(historical_profile_union_v0_1(), min_price=1.49)
        with self.assertRaisesRegex(ValueError, "not the frozen union"):
            validate_historical_profile_union_v0_1(changed_union)

    def test_v04_mode_is_fixed_before_any_provider_or_file_access(self) -> None:
        valid = {
            "gain_basis": SPLIT_CONSISTENT_GAIN_BASIS,
            "market_discovery_id": CAUSAL_MARKET_DISCOVERY_V0_3_POLICY_ID,
            "candidate_artifact_id": CAUSAL_MARKET_CANDIDATES_V0_3_ARTIFACT_ID,
            "profile_mode": HISTORICAL_PROFILE_UNION_V0_1_ID,
        }
        validate_fixed_acquisition_mode(**valid)
        invalid_values = {
            "gain_basis": LEGACY_MIXED_GAIN_BASIS,
            "market_discovery_id": "causal-market-discovery-v0.2",
            "candidate_artifact_id": "causal-market-candidates-v0.2",
            "profile_mode": "current-general-2026",
        }
        for field, value in invalid_values.items():
            with self.subTest(field=field):
                changed = dict(valid, **{field: value})
                with self.assertRaises(ValueError):
                    validate_fixed_acquisition_mode(**changed)

        with self.assertRaisesRegex(ValueError, "split-consistent"):
            build_market_discovery(
                [
                    "--census-root",
                    "/path-that-must-not-be-read",
                    "--gain-basis",
                    LEGACY_MIXED_GAIN_BASIS,
                ]
            )

    def test_low_price_small_account_candidate_is_retained_by_union(self) -> None:
        trading_date = date(2025, 6, 3)
        assets: list[dict[str, object]] = [
            {
                "id": "low-price-test",
                "class": "us_equity",
                "exchange": "NASDAQ",
                "symbol": "LOW",
                "name": "Low Price Test",
                "status": "active",
                "tradable": True,
                "attributes": [],
            }
        ]

        def discover(profile: StrategyProfile):
            return discover_market_day(
                _LowPriceDiscoveryClient(trading_date),
                trading_date=trading_date,
                profile=profile,
                assets=assets,
                gain_basis=SPLIT_CONSISTENT_GAIN_BASIS,
            )

        general_result = discover(current_general_2026())
        small_result = discover(current_small_account_2026())
        union_result = discover(historical_profile_union_v0_1())

        self.assertEqual(general_result.market_candidate_count, 0)
        self.assertEqual(small_result.market_candidate_count, 1)
        self.assertEqual(union_result.market_candidate_count, 1)
        self.assertEqual(set(union_result.minutes), {"LOW"})
        qualified_at = pd.Timestamp(
            union_result.rows[0].first_market_qualified_at
        ).tz_convert(ET)
        self.assertEqual(qualified_at.time(), time(7, 1))


if __name__ == "__main__":
    unittest.main()
