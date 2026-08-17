from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from momentumbot.historical_news import (
    CAUSAL_NEWS_POLICY_ID,
    QUALIFICATION_STATUS_FIELDS,
    build_news_candidate_statuses,
    causal_news_v0_1_manifest,
    causal_news_v0_2_manifest,
    causal_news_v0_2_temporal_boundary,
    load_publication_timed_news,
    load_publication_timed_news_as_of,
    news_events_fingerprint,
    news_statuses_fingerprint,
    news_tape_coverage,
    normalize_alpaca_news,
    prior_regular_session_date,
    project_news_events_as_of,
    publication_window,
    validate_publication_timed_news,
)


def _candidate() -> dict[str, object]:
    return {
        "symbol": "AAA",
        "selected_cik": "1",
        "first_market_qualified_bar_started_at": "2025-04-03T11:14:00+00:00",
        "first_market_qualified_at": "2025-04-03T11:15:00+00:00",
    }


def _event_source(
    provider_id: int,
    published_at: str,
    *,
    symbol: str = "AAA",
) -> dict[str, object]:
    return {
        "id": provider_id,
        "headline": f"Candidate headline {provider_id}",
        "source": "benzinga",
        "symbols": [symbol],
        "created_at": published_at,
        "updated_at": published_at,
    }


def _manifest(
    *,
    candidate: dict[str, object],
    events: list[dict[str, object]],
    statuses: list[dict[str, object]],
    start: datetime,
    end: datetime,
) -> dict[str, object]:
    coverage = news_tape_coverage([candidate], events)
    news_count = sum(
        row["has_provider_news_at_market_qualification"] is True
        for row in statuses
    )
    no_news_count = sum(
        row["provider_relative_no_news_at_market_qualification"] is True
        for row in statuses
    )
    unknown_count = sum(
        row["unknown_fail_closed_at_market_qualification"] is True
        for row in statuses
    )
    return {
        "schema_version": 2,
        "artifact_id": CAUSAL_NEWS_POLICY_ID,
        "news_policy": causal_news_v0_2_manifest(),
        "temporal_boundary": causal_news_v0_2_temporal_boundary(),
        "source_market_candidates_sha256": "market-candidates",
        "source_float_records_sha256": "float-records",
        "publication_window": {
            "start": start.isoformat(),
            "end_exclusive": end.isoformat(),
        },
        "summary": {
            "market_candidate_count": 1,
            "qualification_status_count": 1,
            "full_window_raw_provider_row_count": coverage[
                "full_window_provider_story_count"
            ],
            **coverage,
            "candidates_with_news_at_market_qualification_count": news_count,
            (
                "candidates_with_provider_relative_no_news_"
                "at_market_qualification_count"
            ): no_news_count,
            (
                "candidates_unknown_fail_closed_at_market_qualification_count"
            ): unknown_count,
            "provider_error_count": 0,
            "full_window_availability_basis_counts": dict(
                sorted(
                    Counter(
                        str(row["availability_basis"]) for row in events
                    ).items()
                )
            ),
            "full_window_events_sha256": news_events_fingerprint(events),
            "qualification_statuses_sha256": news_statuses_fingerprint(statuses),
        },
        "eligibility": {
            "complete_relative_to_provider": True,
            "publication_timed_news_frozen": True,
            "full_feature_snapshot_complete": False,
            "universe_complete": False,
        },
        "knowledge_policy": {
            "uses_benchmark_labels": False,
            "qualification_status_uses_future_publications": False,
            "full_window_tape_contains_post_qualification_events": (
                coverage[
                    "full_window_post_qualification_candidate_event_count"
                ]
                > 0
            ),
            "full_window_tape_is_runtime_safe_without_projection": False,
            "candidate_acquisition_depends_on_news": False,
            "absence_means_no_news_in_all_sources": False,
        },
        "files": {
            "news_records": "news-records.json",
            "news_records_schema": (
                "full_window_event_tape_plus_as_of_qualification_statuses"
            ),
        },
    }


def _records_payload(
    events: list[dict[str, object]],
    statuses: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": 2,
        "full_window_event_tape": events,
        "qualification_statuses": statuses,
    }


class HistoricalNewsTests(unittest.TestCase):
    def test_v0_2_preserves_v0_1_provenance_and_hardens_boundary(self) -> None:
        legacy = causal_news_v0_1_manifest()
        hardened = causal_news_v0_2_manifest()

        self.assertEqual(legacy["policy_id"], "causal-alpaca-news-v0.1")
        self.assertEqual(
            legacy["fingerprint"],
            "7f0197a411f418d766e6a294d5cb3ef877b640746ab9de1f4d8f214a3a19df2f",
        )
        self.assertEqual(hardened["policy_id"], "causal-alpaca-news-v0.2")
        self.assertEqual(hardened["supersedes_policy_id"], legacy["policy_id"])
        self.assertEqual(
            hardened["supersedes_policy_fingerprint"], legacy["fingerprint"]
        )
        self.assertNotEqual(hardened["fingerprint"], legacy["fingerprint"])
        self.assertEqual(
            hardened["fingerprint"],
            "0360d3e4ef7f6075d5621a1e9d3d1f6d145fa84f0875feb88b42c705631ee810",
        )
        self.assertEqual(
            hardened["temporal_boundary"]["as_of_projection_rule"],
            "published_at <= decision_time",
        )
        self.assertEqual(
            hardened["temporal_boundary"]["candidate_decision_time_field"],
            "first_market_qualified_at",
        )

    def test_prior_session_comes_from_market_calendar_proxy(self) -> None:
        index = pd.DatetimeIndex(
            ["2025-04-04T04:00:00Z", "2025-04-07T04:00:00Z"]
        )
        frame = pd.DataFrame({"close": [1.0, 1.0]}, index=index)

        prior = prior_regular_session_date(
            frame,
            trading_date=date(2025, 4, 7),
        )
        start, end = publication_window(
            trading_date=date(2025, 4, 7),
            prior_session=prior,
        )

        self.assertEqual(prior, date(2025, 4, 4))
        self.assertEqual(start.isoformat(), "2025-04-04T20:00:00+00:00")
        self.assertEqual(end.isoformat(), "2025-04-07T14:01:00+00:00")

    def test_post_only_event_stays_on_tape_but_not_in_status(self) -> None:
        start = datetime(2025, 4, 2, 20, tzinfo=timezone.utc)
        end = datetime(2025, 4, 3, 14, 1, tzinfo=timezone.utc)
        rows = [
            {
                **_event_source(7, "2025-04-03T11:00:00Z"),
                "symbols": ["AAA", "ZZZ"],
                "updated_at": "2025-04-03T11:30:00Z",
            },
            _event_source(8, "2025-04-03T14:02:00Z"),
        ]

        events, dispositions = normalize_alpaca_news(
            rows,
            candidate_symbols={"AAA"},
            window_start=start,
            window_end=end,
        )
        statuses = build_news_candidate_statuses(
            [_candidate()],
            events,
            provider_status_by_symbol={"AAA": "success"},
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["published_at"], "2025-04-03T11:30:00+00:00")
        self.assertEqual(events[0]["availability_basis"], "provider_updated_at")
        self.assertEqual(
            dispositions["ignored_outside_frozen_publication_window"], 1
        )
        status = statuses[0]
        self.assertEqual(set(status), QUALIFICATION_STATUS_FIELDS)
        self.assertEqual(status["eligible_event_count_at_market_qualification"], 0)
        self.assertIsNone(
            status["first_eligible_event_available_at_market_qualification"]
        )
        self.assertFalse(status["has_provider_news_at_market_qualification"])
        self.assertTrue(
            status["provider_relative_no_news_at_market_qualification"]
        )
        self.assertNotIn("event_count", status)
        self.assertNotIn("first_event_available_at", status)
        self.assertNotIn("provider_relative_no_news", status)
        self.assertEqual(
            news_tape_coverage([_candidate()], events),
            {
                "full_window_candidate_event_count": 1,
                "full_window_provider_story_count": 1,
                "candidates_with_any_full_window_provider_news_count": 1,
                "full_window_post_qualification_candidate_event_count": 1,
                "candidates_with_post_qualification_tape_events_count": 1,
            },
        )
        validate_publication_timed_news(
            [_candidate()],
            events,
            statuses,
            window_start=start,
            window_end=end,
        )

    def test_as_of_projection_is_inclusive_and_requires_aware_time(self) -> None:
        start = datetime(2025, 4, 2, 20, tzinfo=timezone.utc)
        end = datetime(2025, 4, 3, 14, 1, tzinfo=timezone.utc)
        events, _ = normalize_alpaca_news(
            [
                _event_source(1, "2025-04-03T11:05:00Z"),
                _event_source(2, "2025-04-03T11:15:00Z"),
                _event_source(3, "2025-04-03T11:15:01Z"),
                _event_source(4, "2025-04-03T11:05:00Z", symbol="BBB"),
            ],
            candidate_symbols={"AAA", "BBB"},
            window_start=start,
            window_end=end,
        )

        projected = project_news_events_as_of(
            events,
            decision_time=datetime(2025, 4, 3, 11, 15, tzinfo=timezone.utc),
            symbol="AAA",
        )
        self.assertEqual([row["provider_story_id"] for row in projected], ["1", "2"])
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            project_news_events_as_of(
                events,
                decision_time=datetime(2025, 4, 3, 11, 15),
            )

    def test_provider_failure_is_unknown_not_no_news(self) -> None:
        statuses = build_news_candidate_statuses(
            [_candidate()],
            [],
            provider_status_by_symbol={"AAA": "provider_error_fail_closed"},
        )

        self.assertTrue(
            statuses[0]["unknown_fail_closed_at_market_qualification"]
        )
        self.assertFalse(
            statuses[0]["provider_relative_no_news_at_market_qualification"]
        )

    def test_validator_rejects_ambiguous_full_window_status_field(self) -> None:
        start = datetime(2025, 4, 2, 20, tzinfo=timezone.utc)
        end = datetime(2025, 4, 3, 14, 1, tzinfo=timezone.utc)
        statuses = build_news_candidate_statuses(
            [_candidate()],
            [],
            provider_status_by_symbol={"AAA": "success"},
        )
        statuses[0]["event_count"] = 0

        with self.assertRaisesRegex(ValueError, "strictly as-of"):
            validate_publication_timed_news(
                [_candidate()],
                [],
                statuses,
                window_start=start,
                window_end=end,
            )

    def test_loader_checks_hashes_coverage_and_as_of_projection(self) -> None:
        candidate = _candidate()
        candidate_payload = {"content_sha256": "market-candidates"}
        start = datetime(2025, 4, 2, 20, tzinfo=timezone.utc)
        end = datetime(2025, 4, 3, 14, 1, tzinfo=timezone.utc)
        events, _ = normalize_alpaca_news(
            [
                _event_source(7, "2025-04-03T11:05:00Z"),
                _event_source(8, "2025-04-03T11:30:00Z"),
            ],
            candidate_symbols={"AAA"},
            window_start=start,
            window_end=end,
        )
        statuses = build_news_candidate_statuses(
            [candidate],
            events,
            provider_status_by_symbol={"AAA": "success"},
        )
        manifest = _manifest(
            candidate=candidate,
            events=events,
            statuses=statuses,
            start=start,
            end=end,
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            records = root / "news-records.json"
            records.write_text(
                json.dumps(_records_payload(events, statuses)),
                encoding="utf-8",
            )
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            loaded_events, loaded_statuses, loaded_manifest = (
                load_publication_timed_news(
                    root,
                    candidate_rows=[candidate],
                    candidate_payload=candidate_payload,
                    source_float_records_sha256="float-records",
                )
            )
            self.assertEqual(loaded_events, events)
            self.assertEqual(loaded_statuses, statuses)
            self.assertEqual(loaded_manifest, manifest)

            as_of_events, as_of_manifest = load_publication_timed_news_as_of(
                root,
                candidate_rows=[candidate],
                candidate_payload=candidate_payload,
                source_float_records_sha256="float-records",
                decision_time=datetime(
                    2025, 4, 3, 11, 15, tzinfo=timezone.utc
                ),
                symbol="AAA",
            )
            self.assertEqual(
                [row["provider_story_id"] for row in as_of_events], ["7"]
            )
            self.assertEqual(as_of_manifest, manifest)

            bad_coverage = json.loads(json.dumps(manifest))
            bad_coverage["summary"][
                "full_window_post_qualification_candidate_event_count"
            ] = 0
            manifest_path.write_text(
                json.dumps(bad_coverage),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "tape coverage mismatch"):
                load_publication_timed_news(
                    root,
                    candidate_rows=[candidate],
                    candidate_payload=candidate_payload,
                    source_float_records_sha256="float-records",
                )

            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            events[0]["title"] = "tampered"
            records.write_text(
                json.dumps(_records_payload(events, statuses)),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "event fingerprint"):
                load_publication_timed_news(
                    root,
                    candidate_rows=[candidate],
                    candidate_payload=candidate_payload,
                    source_float_records_sha256="float-records",
                )


if __name__ == "__main__":
    unittest.main()
