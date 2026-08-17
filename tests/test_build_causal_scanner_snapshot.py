from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, time, timezone
from pathlib import Path
import sys
import unittest

import pandas as pd

from momentumbot.historical_data import DiscoveryResult, DiscoveryRow
from momentumbot.causal_market_discovery import (
    CAUSAL_MARKET_CANDIDATES_ARTIFACT_ID,
    CAUSAL_MARKET_DISCOVERY_POLICY_ID,
    strategy_profile_manifest,
)
from momentumbot.causal_scanner_snapshot import (
    overlay_authoritative_candidate_rank_frames,
)
from momentumbot.historical_float import CAUSAL_FLOAT_POLICY_ID
from momentumbot.historical_news import CAUSAL_NEWS_POLICY_ID
from momentumbot.identity_resolved_universe import (
    IDENTITY_RESOLVED_UNIVERSE_POLICY_ID,
    json_fingerprint,
)
from momentumbot.models import current_general_2026


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_causal_scanner_snapshot import (  # noqa: E402
    _previous_split_close,
    reacquire_rank_market_inputs,
    validate_cross_artifact_lineage,
    verify_reconstructed_market_candidates,
)


class FakeBarsProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def bars_batched(self, symbols, *, batch_size, **kwargs):
        self.calls.append(
            {"symbols": list(symbols), "batch_size": batch_size, **kwargs}
        )
        if kwargs["timeframe"] == "1Day":
            index = pd.DatetimeIndex(["2025-04-02T04:00:00Z"])
            return {
                "AAA": pd.DataFrame({"close": [1.0]}, index=index),
                "BBB": pd.DataFrame({"close": [2.0]}, index=index),
            }
        index = pd.DatetimeIndex(
            ["2025-04-03T11:00:00Z", "2025-04-03T11:01:00Z"]
        )
        return {
            "AAA": pd.DataFrame(
                {"close": [2.0, 2.1], "volume": [100, 200]},
                index=index,
            ),
            "BBB": pd.DataFrame(
                {"close": [5.0, 5.1], "volume": [300, 400]},
                index=index,
            ),
        }


class FailingBarsProvider:
    def bars_batched(self, symbols, *, batch_size, **kwargs):
        raise RuntimeError("provider_unavailable")


class QuarantiningBarsProvider(FakeBarsProvider):
    def __init__(self) -> None:
        super().__init__()
        self.invalid_symbols: set[str] = set()

    def bars_batched(self, symbols, *, batch_size, **kwargs):
        result = super().bars_batched(
            symbols,
            batch_size=batch_size,
            **kwargs,
        )
        self.invalid_symbols.add("BBB")
        return {symbol: frame for symbol, frame in result.items() if symbol != "BBB"}


def _source_candidate() -> dict[str, object]:
    return {
        "symbol": "AAA",
        "previous_close": 1.0,
        "first_market_qualified_bar_started_at": (
            "2025-04-03T11:00:00+00:00"
        ),
        "first_market_qualified_at": "2025-04-03T11:01:00+00:00",
    }


def _reconstructed() -> DiscoveryResult:
    minute_index = pd.DatetimeIndex(["2025-04-03T11:00:00Z"])
    minutes = pd.DataFrame(
        {"close": [2.0], "volume": [100]},
        index=minute_index,
    )
    return DiscoveryResult(
        asset_count=2,
        listed_asset_count=2,
        daily_superset_count=1,
        rvol_prefilter_count=1,
        market_candidate_count=1,
        asset_master_sha256="assets",
        asset_status_counts={"active": 2},
        rows=(
            DiscoveryRow(
                symbol="AAA",
                status="active",
                exchange="NASDAQ",
                previous_close=1.0,
                target_high=2.0,
                max_session_gain_pct=100.0,
                max_session_rvol_upper_bound=6.0,
                max_session_rvol=6.0,
                rvol_history_sessions=50,
                average_daily_volume_50=100_000.0,
                first_market_qualified_at="2025-04-03T11:01:00+00:00",
                minute_bars=1,
                first_market_qualified_bar_started_at=(
                    "2025-04-03T11:00:00+00:00"
                ),
            ),
        ),
        minutes={"AAA": minutes},
        contexts={},
        rvol_curves={"AAA": pd.Series([6.0], index=minute_index)},
    )


def _lineage_fixture() -> dict[str, dict[str, object]]:
    membership_root = {
        "artifact_id": IDENTITY_RESOLVED_UNIVERSE_POLICY_ID,
        "content_sha256": "1" * 64,
    }
    membership_payload = {
        "artifact_id": IDENTITY_RESOLVED_UNIVERSE_POLICY_ID,
        "trading_date": "2025-04-03",
        "summary": {"membership_sha256": "2" * 64},
    }
    candidate_payload = {
        "artifact_id": CAUSAL_MARKET_CANDIDATES_ARTIFACT_ID,
        "trading_date": "2025-04-03",
        "content_sha256": "3" * 64,
    }
    market_date = {
        "artifact_id": CAUSAL_MARKET_DISCOVERY_POLICY_ID,
        "trading_date": "2025-04-03",
        "source_membership": {
            "membership_sha256": "2" * 64,
            "membership_bundle_sha256": "1" * 64,
            "membership_payload_sha256": json_fingerprint(
                membership_payload
            ),
        },
        "strategy_profile": strategy_profile_manifest(current_general_2026()),
        "summary": {"causal_market_candidate_set_sha256": "3" * 64},
    }
    market_root = {
        "artifact_id": CAUSAL_MARKET_DISCOVERY_POLICY_ID,
        "discovery_policy": {"policy": "market"},
        "source_membership_bundle_sha256": "1" * 64,
        "date_manifests": [market_date],
    }
    market_root["content_sha256"] = json_fingerprint(
        {
            "discovery_policy": market_root["discovery_policy"],
            "source_membership_bundle_sha256": market_root[
                "source_membership_bundle_sha256"
            ],
            "date_manifests": market_root["date_manifests"],
        }
    )
    float_date = {
        "artifact_id": CAUSAL_FLOAT_POLICY_ID,
        "trading_date": "2025-04-03",
        "source_market_candidates_sha256": "3" * 64,
        "source_market_discovery_manifest_sha256": json_fingerprint(
            market_date
        ),
        "summary": {"records_sha256": "4" * 64},
    }
    float_root = {
        "artifact_id": CAUSAL_FLOAT_POLICY_ID,
        "float_policy": {"policy": "float"},
        "source_market_discovery_bundle_sha256": market_root[
            "content_sha256"
        ],
        "date_manifests": [float_date],
    }
    float_root["content_sha256"] = json_fingerprint(
        {
            "float_policy": float_root["float_policy"],
            "source_market_discovery_bundle_sha256": float_root[
                "source_market_discovery_bundle_sha256"
            ],
            "date_manifests": float_root["date_manifests"],
        }
    )
    news_date = {
        "artifact_id": CAUSAL_NEWS_POLICY_ID,
        "trading_date": "2025-04-03",
        "source_market_candidates_sha256": "3" * 64,
        "source_market_discovery_manifest_sha256": json_fingerprint(
            market_date
        ),
        "source_float_records_sha256": "4" * 64,
    }
    news_root = {
        "artifact_id": CAUSAL_NEWS_POLICY_ID,
        "news_policy": {"policy": "news"},
        "temporal_boundary": {"as_of": True},
        "source_market_discovery_bundle_sha256": market_root[
            "content_sha256"
        ],
        "source_float_bundle_sha256": float_root["content_sha256"],
        "date_manifests": [news_date],
    }
    news_root["content_sha256"] = json_fingerprint(
        {
            "news_policy": news_root["news_policy"],
            "temporal_boundary": news_root["temporal_boundary"],
            "source_market_discovery_bundle_sha256": news_root[
                "source_market_discovery_bundle_sha256"
            ],
            "source_float_bundle_sha256": news_root[
                "source_float_bundle_sha256"
            ],
            "date_manifests": news_root["date_manifests"],
        }
    )
    return {
        "membership_root_manifest": membership_root,
        "market_root_manifest": market_root,
        "float_root_manifest": float_root,
        "news_root_manifest": news_root,
        "membership_payload": membership_payload,
        "candidate_payload": candidate_payload,
        "market_date_manifest": market_date,
        "float_date_manifest": float_date,
        "news_date_manifest": news_date,
    }
class BuildCausalScannerSnapshotTests(unittest.TestCase):
    def test_previous_close_rejects_unordered_daily_bars(self) -> None:
        frame = pd.DataFrame(
            {"close": [1.0, 2.0]},
            index=pd.DatetimeIndex(
                ["2025-04-02T04:00:00Z", "2025-04-01T04:00:00Z"]
            ),
        )
        with self.assertRaisesRegex(ValueError, "must be ordered"):
            _previous_split_close(frame, trading_date=date(2025, 4, 3))

    def test_candidate_rank_overlay_blocks_mismatch_and_shares_source(self) -> None:
        authoritative = pd.DataFrame(
            {"close": [2.0], "volume": [100]},
            index=pd.DatetimeIndex(["2025-04-03T11:00:00Z"]),
        )
        mismatched = pd.DataFrame(
            {"close": [9.0], "volume": [100]},
            index=authoritative.index,
        )
        with self.assertRaisesRegex(ValueError, "close mismatch"):
            overlay_authoritative_candidate_rank_frames(
                membership_symbols=["AAA"],
                reacquired_rank_frames={"AAA": mismatched},
                authoritative_candidate_frames={"AAA": authoritative},
            )

        matching_copy = authoritative.copy()
        overlaid = overlay_authoritative_candidate_rank_frames(
            membership_symbols=["AAA", "BBB"],
            reacquired_rank_frames={
                "AAA": matching_copy,
                "BBB": matching_copy,
            },
            authoritative_candidate_frames={"AAA": authoritative},
        )
        self.assertIs(overlaid["AAA"], authoritative)
        self.assertIs(overlaid["BBB"], matching_copy)

    def test_fake_provider_reacquires_all_members_on_causal_bases(self) -> None:
        provider = FakeBarsProvider()
        profile = replace(
            current_general_2026(),
            no_new_entries_after=time(7, 3),
        )

        previous, minutes = reacquire_rank_market_inputs(
            provider,
            trading_date=date(2025, 4, 3),
            membership_symbols=["BBB", "AAA"],
            profile=profile,
            asset_batch_size=20,
        )

        self.assertEqual(previous, {"AAA": 1.0, "BBB": 2.0})
        self.assertEqual(set(minutes), {"AAA", "BBB"})
        self.assertEqual(len(provider.calls), 2)
        daily, intraday = provider.calls
        self.assertEqual(daily["symbols"], ["AAA", "BBB"])
        self.assertEqual(daily["timeframe"], "1Day")
        self.assertEqual(
            daily["start"], datetime(2025, 3, 13, tzinfo=timezone.utc)
        )
        self.assertEqual(
            daily["end"], datetime(2025, 4, 4, tzinfo=timezone.utc)
        )
        self.assertEqual(daily["feed"], "sip")
        self.assertEqual(daily["adjustment"], "split")
        self.assertEqual(intraday["timeframe"], "1Min")
        self.assertEqual(intraday["feed"], "sip")
        self.assertEqual(intraday["adjustment"], "raw")
        self.assertEqual(daily["asof"], date(2025, 4, 3))
        self.assertEqual(intraday["asof"], date(2025, 4, 3))

    def test_reconstruction_requires_exact_candidate_set_and_first_time(self) -> None:
        source = [_source_candidate()]
        result = _reconstructed()

        verify_reconstructed_market_candidates(source, result)

        wrong_time = replace(
            result.rows[0],
            first_market_qualified_bar_started_at=(
                "2025-04-03T11:01:00+00:00"
            ),
            first_market_qualified_at="2025-04-03T11:02:00+00:00",
        )
        with self.assertRaisesRegex(ValueError, "timestamp mismatch"):
            verify_reconstructed_market_candidates(
                source,
                replace(result, rows=(wrong_time,)),
            )

        extra = replace(
            result.rows[0],
            symbol="BBB",
        )
        with self.assertRaisesRegex(ValueError, "candidate set mismatch"):
            verify_reconstructed_market_candidates(
                source,
                replace(
                    result,
                    market_candidate_count=2,
                    rows=(result.rows[0], extra),
                    minutes={**result.minutes, "BBB": result.minutes["AAA"]},
                    rvol_curves={
                        **result.rvol_curves,
                        "BBB": result.rvol_curves["AAA"],
                    },
                ),
            )

    def test_provider_failure_is_a_blocker_not_empty_rank_data(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "provider_unavailable"):
            reacquire_rank_market_inputs(
                FailingBarsProvider(),
                trading_date=date(2025, 4, 3),
                membership_symbols=["AAA"],
                profile=current_general_2026(),
                asset_batch_size=20,
            )

        with self.assertRaisesRegex(
            RuntimeError, "rejected frozen membership symbols: BBB"
        ):
            reacquire_rank_market_inputs(
                QuarantiningBarsProvider(),
                trading_date=date(2025, 4, 3),
                membership_symbols=["AAA", "BBB"],
                profile=current_general_2026(),
                asset_batch_size=20,
            )

    def test_root_and_date_lineage_hashes_are_explicitly_enforced(self) -> None:
        lineage = _lineage_fixture()
        validate_cross_artifact_lineage(
            trading_date="2025-04-03",
            profile=current_general_2026(),
            **lineage,
        )

        bad_root = deepcopy(lineage)
        bad_root["news_root_manifest"]["source_float_bundle_sha256"] = "f" * 64
        news_root = bad_root["news_root_manifest"]
        news_root["content_sha256"] = json_fingerprint(
            {
                "news_policy": news_root["news_policy"],
                "temporal_boundary": news_root["temporal_boundary"],
                "source_market_discovery_bundle_sha256": news_root[
                    "source_market_discovery_bundle_sha256"
                ],
                "source_float_bundle_sha256": news_root[
                    "source_float_bundle_sha256"
                ],
                "date_manifests": news_root["date_manifests"],
            }
        )
        with self.assertRaisesRegex(ValueError, "does not descend from float"):
            validate_cross_artifact_lineage(
                trading_date="2025-04-03",
                profile=current_general_2026(),
                **bad_root,
            )

        bad_date = deepcopy(lineage)
        changed = bad_date["news_date_manifest"]
        changed["source_float_records_sha256"] = "e" * 64
        bad_date["news_root_manifest"]["date_manifests"] = [changed]
        news_root = bad_date["news_root_manifest"]
        news_root["content_sha256"] = json_fingerprint(
            {
                "news_policy": news_root["news_policy"],
                "temporal_boundary": news_root["temporal_boundary"],
                "source_market_discovery_bundle_sha256": news_root[
                    "source_market_discovery_bundle_sha256"
                ],
                "source_float_bundle_sha256": news_root[
                    "source_float_bundle_sha256"
                ],
                "date_manifests": news_root["date_manifests"],
            }
        )
        with self.assertRaisesRegex(ValueError, "float-record hash mismatch"):
            validate_cross_artifact_lineage(
                trading_date="2025-04-03",
                profile=current_general_2026(),
                **bad_date,
            )

        bad_membership_payload = deepcopy(lineage)
        bad_membership_payload["membership_payload"]["tampered"] = True
        with self.assertRaisesRegex(ValueError, "membership payload hash mismatch"):
            validate_cross_artifact_lineage(
                trading_date="2025-04-03",
                profile=current_general_2026(),
                **bad_membership_payload,
            )

        with self.assertRaisesRegex(ValueError, "strategy profile mismatch"):
            validate_cross_artifact_lineage(
                trading_date="2025-04-03",
                profile=replace(current_general_2026(), min_percent_gain=11.0),
                **lineage,
            )


if __name__ == "__main__":
    unittest.main()
