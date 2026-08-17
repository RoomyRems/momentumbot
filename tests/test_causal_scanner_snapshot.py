from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, time, timezone
import hashlib
import unittest

import pandas as pd

from momentumbot.causal_scanner_snapshot import (
    SNAPSHOT_ROW_FIELDS,
    UPSTREAM_MARKET_ACQUISITION_TAIL_END,
    build_causal_scanner_snapshot_artifacts,
    build_scanner_snapshot_rows,
    causal_scanner_snapshot_v0_1_manifest,
    cross_sectional_rank_state,
    market_inputs_fingerprint,
    trim_scanner_bar_frame,
    trim_scanner_rvol_series,
    validate_causal_scanner_snapshot,
)
from momentumbot.models import current_general_2026
from momentumbot.identity_resolved_universe import json_fingerprint


def _profile(cutoff: time = time(7, 4)):
    return replace(current_general_2026(), no_new_entries_after=cutoff)


def _candidate(symbol: str = "AAA") -> dict[str, object]:
    return {
        "symbol": symbol,
        "previous_close": 1.0,
        "first_market_qualified_bar_started_at": (
            "2025-04-03T11:00:00+00:00"
        ),
        "first_market_qualified_at": "2025-04-03T11:01:00+00:00",
    }


def _bars(
    closes: list[float],
    *,
    start: str = "2025-04-03T11:00:00Z",
) -> pd.DataFrame:
    index = pd.date_range(start, periods=len(closes), freq="1min")
    return pd.DataFrame(
        {
            "close": closes,
            "volume": [100 * (offset + 1) for offset in range(len(closes))],
        },
        index=index,
    )


def _rvol(values: list[float]) -> pd.Series:
    index = pd.date_range(
        "2025-04-03T11:00:00Z",
        periods=len(values),
        freq="1min",
    )
    return pd.Series(values, index=index)


def _float_record(
    *,
    symbol: str = "AAA",
    classification: str = "pass",
    sec_status: str = "success",
) -> dict[str, object]:
    pillar = True if classification == "pass" else (
        False if classification == "fail" else None
    )
    return {
        "symbol": symbol,
        "float_classification": classification,
        "float_pillar_pass": pillar,
        "estimated_float_shares": 5_000_000 if pillar is not None else None,
        "float_asof": (
            "2025-04-01T12:00:00+00:00" if pillar is not None else None
        ),
        "method": "test-causal-float",
        "sec_status": sec_status,
    }


def _news_status(
    *,
    symbol: str = "AAA",
    provider_status: str = "success",
) -> dict[str, object]:
    return {"symbol": symbol, "provider_status": provider_status}


def _event(published_at: str) -> dict[str, object]:
    return {
        "symbol": "AAA",
        "published_at": published_at,
        "headline_id": "provider:test-1",
    }


def _source_hashes() -> dict[str, str]:
    names = (
        "identity_resolved_membership",
        "market_candidates",
        "market_discovery_manifest",
        "causal_float_records",
        "causal_float_manifest",
        "publication_timed_news_events",
        "publication_timed_news_statuses",
        "publication_timed_news_manifest",
        "reacquired_market_inputs",
    )
    return {
        name: hashlib.sha256(name.encode("ascii")).hexdigest()
        for name in names
    }


class CausalScannerSnapshotTests(unittest.TestCase):
    def test_later_news_changes_disposition_only_at_publication(self) -> None:
        candidate_bars = _bars([2.0, 2.1, 2.2])
        rows = build_scanner_snapshot_rows(
            trading_date=date(2025, 4, 3),
            profile=_profile(),
            candidate_rows=[_candidate()],
            float_records=[_float_record()],
            news_events=[_event("2025-04-03T11:02:00+00:00")],
            news_statuses=[_news_status()],
            membership_symbols=["AAA"],
            previous_close_by_symbol={"AAA": 1.0},
            rank_raw_minute_bars_by_symbol={"AAA": candidate_bars},
            candidate_raw_minute_bars_by_symbol={"AAA": candidate_bars},
            candidate_exact_rvol_by_symbol={"AAA": _rvol([6.0, 6.1, 6.2])},
        )

        self.assertEqual(len(rows), 3)
        self.assertEqual(
            [row["decision_time"] for row in rows],
            [
                "2025-04-03T11:01:00+00:00",
                "2025-04-03T11:02:00+00:00",
                "2025-04-03T11:03:00+00:00",
            ],
        )
        self.assertEqual(
            [row["disposition"] for row in rows],
            [
                "feature_state_provider_relative_no_news_unclassified",
                "feature_state_provider_news_present_unclassified",
                "feature_state_provider_news_present_unclassified",
            ],
        )
        self.assertEqual(
            [row["provider_news_event_count_as_of"] for row in rows],
            [0, 1, 1],
        )
        self.assertTrue(all(set(row) == SNAPSHOT_ROW_FIELDS for row in rows))
        self.assertEqual(
            rows[0]["required_source_bar_started_at"],
            "2025-04-03T11:00:00+00:00",
        )
        self.assertEqual(rows[0]["candidate_bar_available_at"], rows[0]["decision_time"])

    def test_rank_includes_higher_gain_noncandidate_and_breaks_ties_by_symbol(self) -> None:
        bars = {
            "AAA": _bars([2.0]),
            "BBB": _bars([3.0]),
            "CCC": _bars([2.0]),
        }
        rank = cross_sectional_rank_state(
            decision_time=datetime(2025, 4, 3, 11, 1, tzinfo=timezone.utc),
            membership_symbols=["AAA", "BBB", "CCC"],
            previous_close_by_symbol={"AAA": 1.0, "BBB": 1.0, "CCC": 1.0},
            raw_minute_bars_by_symbol=bars,
        )

        self.assertEqual(rank.ranks, {"BBB": 1, "AAA": 2, "CCC": 3})
        self.assertEqual(rank.leader_symbol, "BBB")
        self.assertTrue(rank.rank_input_complete_for_members_with_completed_bars)

        rows = build_scanner_snapshot_rows(
            trading_date=date(2025, 4, 3),
            profile=_profile(time(7, 2)),
            candidate_rows=[_candidate()],
            float_records=[_float_record()],
            news_events=[_event("2025-04-03T10:30:00+00:00")],
            news_statuses=[_news_status()],
            membership_symbols=["AAA", "BBB", "CCC"],
            previous_close_by_symbol={"AAA": 1.0, "BBB": 1.0, "CCC": 1.0},
            rank_raw_minute_bars_by_symbol=bars,
            candidate_raw_minute_bars_by_symbol={"AAA": bars["AAA"]},
            candidate_exact_rvol_by_symbol={"AAA": _rvol([6.0])},
        )
        self.assertEqual(rows[0]["top_gainer_rank"], 2)
        self.assertEqual(rows[0]["rank_leader_symbol"], "BBB")
        self.assertEqual(
            rows[0]["disposition"],
            "feature_state_provider_news_present_unclassified",
        )

    def test_core_uses_uniform_reacquired_candidate_previous_close(self) -> None:
        candidate_bars = _bars([2.0])
        reacquired_previous = 1.00000000000075
        rows = build_scanner_snapshot_rows(
            trading_date=date(2025, 4, 3),
            profile=_profile(time(7, 2)),
            candidate_rows=[_candidate()],
            float_records=[_float_record()],
            news_events=[],
            news_statuses=[_news_status()],
            membership_symbols=["AAA"],
            previous_close_by_symbol={"AAA": reacquired_previous},
            rank_raw_minute_bars_by_symbol={"AAA": candidate_bars},
            candidate_raw_minute_bars_by_symbol={"AAA": candidate_bars},
            candidate_exact_rvol_by_symbol={"AAA": _rvol([6.0])},
        )
        row = rows[0]
        self.assertEqual(row["previous_close"], reacquired_previous)
        self.assertEqual(row["top_gainer_rank"], 1)
        self.assertEqual(row["percent_gain"], row["rank_leader_percent_gain"])

    def test_incomplete_rank_fails_closed_and_records_coverage(self) -> None:
        candidate_bars = _bars([2.0])
        rows = build_scanner_snapshot_rows(
            trading_date=date(2025, 4, 3),
            profile=_profile(time(7, 2)),
            candidate_rows=[_candidate()],
            float_records=[_float_record()],
            news_events=[],
            news_statuses=[_news_status()],
            membership_symbols=["AAA", "BBB"],
            previous_close_by_symbol={"AAA": 1.0},
            rank_raw_minute_bars_by_symbol={
                "AAA": candidate_bars,
                "BBB": _bars([3.0]),
            },
            candidate_raw_minute_bars_by_symbol={"AAA": candidate_bars},
            candidate_exact_rvol_by_symbol={"AAA": _rvol([6.0])},
        )

        row = rows[0]
        self.assertEqual(row["rank_members_with_completed_bar_count"], 2)
        self.assertEqual(row["rank_members_missing_previous_close_count"], 1)
        self.assertFalse(
            row["rank_input_complete_for_members_with_completed_bars"]
        )
        self.assertIsNone(row["top_gainer_rank"])
        self.assertEqual(
            row["disposition"],
            "feature_state_unknown_fail_closed_missing_cross_sectional_rank",
        )

    def test_unknown_float_and_news_provider_error_fail_closed(self) -> None:
        candidate_bars = _bars([2.0])
        common = {
            "trading_date": date(2025, 4, 3),
            "profile": _profile(time(7, 2)),
            "candidate_rows": [_candidate()],
            "news_events": [],
            "membership_symbols": ["AAA"],
            "previous_close_by_symbol": {"AAA": 1.0},
            "rank_raw_minute_bars_by_symbol": {"AAA": candidate_bars},
            "candidate_raw_minute_bars_by_symbol": {"AAA": candidate_bars},
            "candidate_exact_rvol_by_symbol": {"AAA": _rvol([6.0])},
        }
        unknown = build_scanner_snapshot_rows(
            **common,
            float_records=[_float_record(classification="unknown_fail_closed")],
            news_statuses=[_news_status()],
        )
        self.assertEqual(
            unknown[0]["disposition"],
            "feature_state_unknown_fail_closed_float",
        )
        provider_error = build_scanner_snapshot_rows(
            **common,
            float_records=[_float_record()],
            news_statuses=[
                _news_status(provider_status="provider_error_fail_closed")
            ],
        )
        self.assertEqual(
            provider_error[0]["disposition"],
            "feature_state_unknown_fail_closed_news_provider_error",
        )

    def test_missing_exact_candidate_bar_nulls_all_market_features(self) -> None:
        candidate_bars = _bars([2.0])
        rows = build_scanner_snapshot_rows(
            trading_date=date(2025, 4, 3),
            profile=_profile(time(7, 3)),
            candidate_rows=[_candidate()],
            float_records=[_float_record()],
            news_events=[],
            news_statuses=[_news_status()],
            membership_symbols=["AAA"],
            previous_close_by_symbol={"AAA": 1.0},
            rank_raw_minute_bars_by_symbol={"AAA": candidate_bars},
            candidate_raw_minute_bars_by_symbol={"AAA": candidate_bars},
            candidate_exact_rvol_by_symbol={"AAA": _rvol([6.0, 6.1])},
        )
        missing = rows[1]
        self.assertFalse(missing["candidate_completed_bar_present"])
        for field in (
            "price",
            "percent_gain",
            "cumulative_volume",
            "exact_same_time_rvol",
            "price_pillar_pass",
            "gain_pillar_pass",
            "rvol_pillar_pass",
        ):
            self.assertIsNone(missing[field])
        self.assertEqual(
            missing["disposition"],
            "feature_state_unknown_fail_closed_missing_candidate_completed_bar",
        )
        self.assertEqual(missing["top_gainer_rank"], 1)
        self.assertEqual(missing["rank_leader_symbol"], "AAA")
        self.assertEqual(missing["rank_leader_percent_gain"], 100.0)

        # Rank causally carries the latest completed close forward, whereas
        # candidate market features require this minute's exact bar.  The
        # resulting rank-one/null-current-gain row is valid and must survive
        # the artifact validator.
        payload, manifest = build_causal_scanner_snapshot_artifacts(
            trading_date=date(2025, 4, 3),
            profile=_profile(time(7, 3)),
            candidate_rows=[_candidate()],
            membership_symbols=["AAA"],
            rows=rows,
            source_hashes=_source_hashes(),
        )
        self.assertEqual(payload["row_count"], 2)
        self.assertEqual(
            manifest["summary"]["candidate_minute_disposition_count"],
            2,
        )

        wrong_leader_rows = deepcopy(rows)
        wrong_leader_rows[1]["rank_leader_symbol"] = "BBB"
        with self.assertRaisesRegex(
            ValueError,
            "rank-one candidate disagrees with leader",
        ):
            build_causal_scanner_snapshot_artifacts(
                trading_date=date(2025, 4, 3),
                profile=_profile(time(7, 3)),
                candidate_rows=[_candidate()],
                membership_symbols=["AAA"],
                rows=wrong_leader_rows,
                source_hashes=_source_hashes(),
            )

    def test_validator_rejects_tamper_duplicate_and_missing_disposition(self) -> None:
        profile = _profile(time(7, 2))
        candidate_rows = [_candidate()]
        candidate_bars = _bars([2.0])
        rows = build_scanner_snapshot_rows(
            trading_date=date(2025, 4, 3),
            profile=profile,
            candidate_rows=candidate_rows,
            float_records=[_float_record()],
            news_events=[],
            news_statuses=[_news_status()],
            membership_symbols=["AAA"],
            previous_close_by_symbol={"AAA": 1.0},
            rank_raw_minute_bars_by_symbol={"AAA": candidate_bars},
            candidate_raw_minute_bars_by_symbol={"AAA": candidate_bars},
            candidate_exact_rvol_by_symbol={"AAA": _rvol([6.0])},
        )
        payload, manifest = build_causal_scanner_snapshot_artifacts(
            trading_date=date(2025, 4, 3),
            profile=profile,
            candidate_rows=candidate_rows,
            membership_symbols=["AAA"],
            rows=rows,
            source_hashes=_source_hashes(),
        )
        self.assertTrue(
            manifest["eligibility"][
                "complete_relative_to_identity_resolved_membership"
            ]
        )
        self.assertFalse(manifest["eligibility"]["universe_complete"])
        self.assertFalse(manifest["eligibility"]["full_walk_forward_eligible"])
        self.assertFalse(manifest["eligibility"]["policy_promotion_eligible"])
        self.assertFalse(
            manifest["knowledge_policy"]["uses_benchmark_labels"]
        )
        self.assertEqual(
            causal_scanner_snapshot_v0_1_manifest()["rank_threshold_rule"],
            "feature_only_no_final_top_n_threshold_frozen",
        )
        self.assertEqual(
            causal_scanner_snapshot_v0_1_manifest()["rank_acquisition_basis"],
            {
                "provider": "alpaca_historical_stock_bars",
                "feed": "sip",
                "previous_close_timeframe": "1Day",
                "previous_close_adjustment": "split",
                "previous_close_lookback_calendar_days": 21,
                "minute_timeframe": "1Min",
                "minute_adjustment": "raw",
                "asof_rule": "trading_date",
            },
        )
        self.assertEqual(
            causal_scanner_snapshot_v0_1_manifest()["session_timezone"],
            "America/New_York",
        )
        self.assertEqual(
            causal_scanner_snapshot_v0_1_manifest()[
                "candidate_previous_close_authority_rule"
            ],
            "uniform_all_membership_reacquired_split_previous_close_is_"
            "authoritative_for_both_rank_and_candidate_snapshot_after_"
            "frozen_market_candidate_corroboration",
        )
        self.assertEqual(
            causal_scanner_snapshot_v0_1_manifest()[
                "candidate_previous_close_match_tolerance"
            ],
            {"relative": 1e-12, "absolute": 1e-12},
        )
        self.assertEqual(
            causal_scanner_snapshot_v0_1_manifest()[
                "source_input_fingerprint_rule"
            ],
            "streamed_canonical_newline_records_without_materializing_full_tape",
        )
        self.assertEqual(
            causal_scanner_snapshot_v0_1_manifest()[
                "candidate_rank_frame_authority_rule"
            ],
            "uniform_all_membership_reacquired_frame_is_authoritative_for_"
            "both_rank_and_candidate_features_never_switched_by_eventual_"
            "candidate_status",
        )
        self.assertEqual(
            causal_scanner_snapshot_v0_1_manifest()[
                "candidate_rank_frame_close_match_tolerance"
            ],
            {"relative": 1e-12, "absolute": 1e-12},
        )
        self.assertEqual(
            causal_scanner_snapshot_v0_1_manifest()[
                "candidate_rank_frame_volume_match_rule"
            ],
            "exact_numeric_equality",
        )
        self.assertEqual(
            causal_scanner_snapshot_v0_1_manifest()[
                "upstream_market_acquisition_tail_rule"
            ],
            "accept_target_date_minute_bars_through_10:01_America/New_York_"
            "then_drop_bars_not_completed_strictly_before_exclusive_cutoff_"
            "before_fingerprinting_or_features",
        )
        self.assertEqual(
            causal_scanner_snapshot_v0_1_manifest()["fingerprint"],
            "ed21becad10855b4a085b6e05b6feac8f21e4ce511a100b2381522154818f42a",
        )
        self.assertFalse(
            causal_scanner_snapshot_v0_1_manifest()[
                "partial_date_emission_on_provider_error"
            ]
        )
        self.assertEqual(
            manifest["provider_error_boundary"]["row_fail_closed_scope"],
            "defensive_validated_per_symbol_status_only",
        )
        self.assertFalse(
            manifest["provider_error_boundary"][
                "fatal_provider_error_emits_partial_date"
            ]
        )
        self.assertFalse(
            manifest["source_replay_boundary"][
                "independent_feature_recomputation_from_snapshot_artifact"
            ]
        )
        self.assertEqual(
            manifest["source_replay_boundary"][
                "reacquired_market_inputs_sha256_role"
            ],
            "integrity_commitment_only",
        )

        wrong_sources = _source_hashes()
        wrong_sources["market_candidates"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "differs from sources"):
            validate_causal_scanner_snapshot(
                payload,
                manifest,
                candidate_rows=candidate_rows,
                profile=profile,
                expected_source_hashes=wrong_sources,
            )
        uppercase_sources = _source_hashes()
        uppercase_sources["market_candidates"] = uppercase_sources[
            "market_candidates"
        ].upper()
        with self.assertRaisesRegex(ValueError, "lowercase SHA-256"):
            build_causal_scanner_snapshot_artifacts(
                trading_date=date(2025, 4, 3),
                profile=profile,
                candidate_rows=candidate_rows,
                membership_symbols=["AAA"],
                rows=rows,
                source_hashes=uppercase_sources,
            )

        tampered = deepcopy(payload)
        tampered["rows"][0]["price"] = 999.0
        with self.assertRaisesRegex(ValueError, "payload fingerprint"):
            validate_causal_scanner_snapshot(
                tampered,
                manifest,
                candidate_rows=candidate_rows,
                profile=profile,
                expected_source_hashes=_source_hashes(),
            )
        low_identity_payload = deepcopy(payload)
        low_identity_payload["identity_resolved_member_count"] = 0
        low_identity_payload["content_sha256"] = json_fingerprint(
            {
                key: value
                for key, value in low_identity_payload.items()
                if key != "content_sha256"
            }
        )
        low_identity_manifest = deepcopy(manifest)
        low_identity_manifest["summary"]["identity_resolved_member_count"] = 0
        low_identity_manifest["summary"]["records_content_sha256"] = (
            low_identity_payload["content_sha256"]
        )
        low_identity_manifest["content_sha256"] = json_fingerprint(
            {
                key: value
                for key, value in low_identity_manifest.items()
                if key != "content_sha256"
            }
        )
        with self.assertRaisesRegex(ValueError, "below candidate count"):
            validate_causal_scanner_snapshot(
                low_identity_payload,
                low_identity_manifest,
                candidate_rows=candidate_rows,
                profile=profile,
                expected_source_hashes=_source_hashes(),
            )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_causal_scanner_snapshot_artifacts(
                trading_date=date(2025, 4, 3),
                profile=profile,
                candidate_rows=candidate_rows,
                membership_symbols=["AAA"],
                rows=rows + [deepcopy(rows[0])],
                source_hashes=_source_hashes(),
            )
        with self.assertRaisesRegex(ValueError, "missing"):
            build_causal_scanner_snapshot_artifacts(
                trading_date=date(2025, 4, 3),
                profile=profile,
                candidate_rows=candidate_rows,
                membership_symbols=["AAA"],
                rows=[],
                source_hashes=_source_hashes(),
            )

        semantic_mutations = (
            ("activation_time", "2025-04-03T11:02:00+00:00", "activation"),
            ("percent_gain", 999.0, "percent gain"),
            ("float_pillar_pass", False, "float classification"),
            ("provider_news_event_count_as_of", 1, "news count"),
            ("rank_leader_percent_gain", -1.0, "rank leader"),
            ("rank_input_ordered_sha256", "A" * 64, "rank input fingerprint"),
        )
        for field, value, message in semantic_mutations:
            with self.subTest(field=field):
                changed = deepcopy(rows)
                changed[0][field] = value
                with self.assertRaisesRegex(ValueError, message):
                    build_causal_scanner_snapshot_artifacts(
                        trading_date=date(2025, 4, 3),
                        profile=profile,
                        candidate_rows=candidate_rows,
                        membership_symbols=["AAA"],
                        rows=changed,
                        source_hashes=_source_hashes(),
                    )
        with self.assertRaisesRegex(ValueError, "absent from membership"):
            build_causal_scanner_snapshot_artifacts(
                trading_date=date(2025, 4, 3),
                profile=profile,
                candidate_rows=candidate_rows,
                membership_symbols=["BBB"],
                rows=rows,
                source_hashes=_source_hashes(),
            )

    def test_session_frame_and_no_top_n_boundaries_are_enforced(self) -> None:
        before_session = {
            **_candidate(),
            "first_market_qualified_bar_started_at": (
                "2025-04-03T10:58:00+00:00"
            ),
            "first_market_qualified_at": "2025-04-03T10:59:00+00:00",
        }
        bars = _bars([2.0], start="2025-04-03T10:58:00Z")
        with self.assertRaisesRegex(ValueError, "before session start"):
            build_scanner_snapshot_rows(
                trading_date=date(2025, 4, 3),
                profile=_profile(time(7, 2)),
                candidate_rows=[before_session],
                float_records=[_float_record()],
                news_events=[],
                news_statuses=[_news_status()],
                membership_symbols=["AAA"],
                previous_close_by_symbol={"AAA": 1.0},
                rank_raw_minute_bars_by_symbol={"AAA": bars},
                candidate_raw_minute_bars_by_symbol={"AAA": bars},
                candidate_exact_rvol_by_symbol={
                    "AAA": pd.Series([6.0], index=bars.index)
                },
            )

        wrong_date_bars = _bars([2.0], start="2025-04-04T11:00:00Z")
        with self.assertRaisesRegex(ValueError, "target trading date"):
            build_scanner_snapshot_rows(
                trading_date=date(2025, 4, 3),
                profile=_profile(time(7, 2)),
                candidate_rows=[_candidate()],
                float_records=[_float_record()],
                news_events=[],
                news_statuses=[_news_status()],
                membership_symbols=["AAA"],
                previous_close_by_symbol={"AAA": 1.0},
                rank_raw_minute_bars_by_symbol={"AAA": wrong_date_bars},
                candidate_raw_minute_bars_by_symbol={"AAA": wrong_date_bars},
                candidate_exact_rvol_by_symbol={"AAA": _rvol([6.0])},
            )

        top_n = replace(_profile(time(7, 2)), require_top_gainer_rank=3)
        valid_bars = _bars([2.0])
        with self.assertRaisesRegex(ValueError, "top-N profiles"):
            build_scanner_snapshot_rows(
                trading_date=date(2025, 4, 3),
                profile=top_n,
                candidate_rows=[_candidate()],
                float_records=[_float_record()],
                news_events=[],
                news_statuses=[_news_status()],
                membership_symbols=["AAA"],
                previous_close_by_symbol={"AAA": 1.0},
                rank_raw_minute_bars_by_symbol={"AAA": valid_bars},
                candidate_raw_minute_bars_by_symbol={"AAA": valid_bars},
                candidate_exact_rvol_by_symbol={"AAA": _rvol([6.0])},
            )

        mismatched_float_limit = replace(
            _profile(time(7, 2)), max_float_shares=9_000_000
        )
        with self.assertRaisesRegex(ValueError, "frozen causal float policy"):
            build_scanner_snapshot_rows(
                trading_date=date(2025, 4, 3),
                profile=mismatched_float_limit,
                candidate_rows=[_candidate()],
                float_records=[_float_record()],
                news_events=[],
                news_statuses=[_news_status()],
                membership_symbols=["AAA"],
                previous_close_by_symbol={"AAA": 1.0},
                rank_raw_minute_bars_by_symbol={"AAA": valid_bars},
                candidate_raw_minute_bars_by_symbol={"AAA": valid_bars},
                candidate_exact_rvol_by_symbol={"AAA": _rvol([6.0])},
            )

    def test_market_input_hash_orders_membership_and_prior_closes(self) -> None:
        bars = {"AAA": _bars([2.0]), "BBB": _bars([3.0])}
        kwargs = {
            "trading_date": date(2025, 4, 3),
            "profile": _profile(time(7, 2)),
            "rank_raw_minute_bars_by_symbol": bars,
            "candidate_raw_minute_bars_by_symbol": {"AAA": bars["AAA"]},
            "candidate_exact_rvol_by_symbol": {"AAA": _rvol([6.0])},
        }
        first = market_inputs_fingerprint(
            **kwargs,
            membership_symbols=["BBB", "AAA"],
            previous_close_by_symbol={"BBB": 1.5, "AAA": 1.0},
        )
        reordered = market_inputs_fingerprint(
            **kwargs,
            membership_symbols=["AAA", "BBB"],
            previous_close_by_symbol={"AAA": 1.0, "BBB": 1.5},
        )
        changed = market_inputs_fingerprint(
            **kwargs,
            membership_symbols=["AAA", "BBB"],
            previous_close_by_symbol={"AAA": 1.0, "BBB": 1.6},
        )
        self.assertEqual(first, reordered)
        self.assertNotEqual(first, changed)

    def test_input_tape_excludes_bars_unavailable_before_cutoff(self) -> None:
        frame = _bars([2.0, 2.1, 2.2, 2.3])
        series = _rvol([6.0, 6.1, 6.2, 6.3])
        trimmed = trim_scanner_bar_frame(
            frame,
            trading_date=date(2025, 4, 3),
            start=time(4, 0),
            cutoff=time(7, 3),
            label="test bars",
        )
        trimmed_rvol = trim_scanner_rvol_series(
            series,
            trading_date=date(2025, 4, 3),
            start=time(4, 0),
            cutoff=time(7, 3),
            label="test RVOL",
        )
        self.assertEqual(
            list(trimmed.index),
            list(pd.DatetimeIndex(["2025-04-03T11:00:00Z", "2025-04-03T11:01:00Z"])),
        )
        self.assertEqual(list(trimmed_rvol.index), list(trimmed.index))
        self.assertNotIn(pd.Timestamp("2025-04-03T11:02:00Z"), trimmed.index)

        acquisition_tail = _bars(
            [2.0, 2.1, 2.2, 2.3],
            start="2025-04-03T13:58:00Z",
        )
        tail_rvol = pd.Series(
            [6.0, 6.1, 6.2, 6.3],
            index=acquisition_tail.index,
        )
        trimmed_tail = trim_scanner_bar_frame(
            acquisition_tail,
            trading_date=date(2025, 4, 3),
            start=time(4, 0),
            cutoff=time(10, 0),
            acquisition_end=UPSTREAM_MARKET_ACQUISITION_TAIL_END,
            label="upstream acquisition-tail bars",
        )
        trimmed_tail_rvol = trim_scanner_rvol_series(
            tail_rvol,
            trading_date=date(2025, 4, 3),
            start=time(4, 0),
            cutoff=time(10, 0),
            acquisition_end=UPSTREAM_MARKET_ACQUISITION_TAIL_END,
            label="upstream acquisition-tail RVOL",
        )
        self.assertEqual(
            list(trimmed_tail.index),
            list(pd.DatetimeIndex(["2025-04-03T13:58:00Z"])),
        )
        pd.testing.assert_frame_equal(trimmed_tail, acquisition_tail.iloc[:1])
        pd.testing.assert_series_equal(trimmed_tail_rvol, tail_rvol.iloc[:1])
        self.assertNotIn(
            pd.Timestamp("2025-04-03T14:01:00Z"), trimmed_tail.index
        )

        far_future = _bars([2.0], start="2025-04-03T14:02:00Z")
        with self.assertRaisesRegex(ValueError, "provider acquisition window"):
            trim_scanner_bar_frame(
                far_future,
                trading_date=date(2025, 4, 3),
                start=time(4, 0),
                cutoff=time(10, 0),
                acquisition_end=UPSTREAM_MARKET_ACQUISITION_TAIL_END,
                label="far-future bars",
            )

        undeclared_custom_tail = _bars(
            [2.0], start="2025-04-03T11:04:00Z"
        )
        with self.assertRaisesRegex(ValueError, "provider acquisition window"):
            trim_scanner_bar_frame(
                undeclared_custom_tail,
                trading_date=date(2025, 4, 3),
                start=time(4, 0),
                cutoff=time(7, 3),
                label="rank/custom-cutoff bars",
            )

        wrong_date = _bars([2.0], start="2025-04-04T14:01:00Z")
        with self.assertRaisesRegex(ValueError, "target trading date"):
            trim_scanner_bar_frame(
                wrong_date,
                trading_date=date(2025, 4, 3),
                start=time(4, 0),
                cutoff=time(10, 0),
                acquisition_end=UPSTREAM_MARKET_ACQUISITION_TAIL_END,
                label="wrong-date bars",
            )


if __name__ == "__main__":
    unittest.main()
