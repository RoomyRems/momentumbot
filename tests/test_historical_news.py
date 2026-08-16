from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from momentumbot.historical_news import (
    build_news_candidate_statuses,
    causal_news_v0_1_manifest,
    load_publication_timed_news,
    news_events_fingerprint,
    news_statuses_fingerprint,
    normalize_alpaca_news,
    prior_regular_session_date,
    publication_window,
    validate_publication_timed_news,
)


def _candidate() -> dict[str, object]:
    return {
        "symbol": "AAA",
        "selected_cik": "1",
        "first_market_qualified_at": "2025-04-03T11:15:00+00:00",
    }


class HistoricalNewsTests(unittest.TestCase):
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

    def test_normalization_uses_conservative_updated_timestamp(self) -> None:
        start = datetime(2025, 4, 2, 20, tzinfo=timezone.utc)
        end = datetime(2025, 4, 3, 14, 1, tzinfo=timezone.utc)
        rows = [
            {
                "id": 7,
                "headline": "Candidate headline",
                "source": "benzinga",
                "symbols": ["AAA", "ZZZ"],
                "created_at": "2025-04-03T11:00:00Z",
                "updated_at": "2025-04-03T11:30:00Z",
            },
            {
                "id": 8,
                "headline": "Later revision",
                "symbols": ["AAA"],
                "created_at": "2025-04-03T13:59:00Z",
                "updated_at": "2025-04-03T14:02:00Z",
            },
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
        self.assertFalse(statuses[0]["has_provider_news_at_market_qualification"])
        validate_publication_timed_news(
            [_candidate()],
            events,
            statuses,
            window_start=start,
            window_end=end,
        )

    def test_provider_failure_is_unknown_not_no_news(self) -> None:
        statuses = build_news_candidate_statuses(
            [_candidate()],
            [],
            provider_status_by_symbol={"AAA": "provider_error_fail_closed"},
        )

        self.assertTrue(statuses[0]["unknown_fail_closed"])
        self.assertFalse(statuses[0]["provider_relative_no_news"])

    def test_loader_rejects_tampered_news_event(self) -> None:
        candidate = _candidate()
        candidate_payload = {"content_sha256": "market-candidates"}
        start = datetime(2025, 4, 2, 20, tzinfo=timezone.utc)
        end = datetime(2025, 4, 3, 14, 1, tzinfo=timezone.utc)
        events, _ = normalize_alpaca_news(
            [
                {
                    "id": 7,
                    "headline": "Candidate headline",
                    "source": "benzinga",
                    "symbols": ["AAA"],
                    "created_at": "2025-04-03T11:00:00Z",
                    "updated_at": "2025-04-03T11:05:00Z",
                }
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
        manifest = {
            "artifact_id": "causal-alpaca-news-v0.1",
            "news_policy": causal_news_v0_1_manifest(),
            "source_market_candidates_sha256": "market-candidates",
            "source_float_records_sha256": "float-records",
            "publication_window": {
                "start": start.isoformat(),
                "end_exclusive": end.isoformat(),
            },
            "summary": {
                "market_candidate_count": 1,
                "event_count": 1,
                "candidate_decision_count": 1,
                "provider_error_count": 0,
                "events_sha256": news_events_fingerprint(events),
                "candidate_statuses_sha256": news_statuses_fingerprint(statuses),
            },
            "eligibility": {
                "complete_relative_to_provider": True,
                "publication_timed_news_frozen": True,
                "full_feature_snapshot_complete": False,
                "universe_complete": False,
            },
            "knowledge_policy": {
                "uses_benchmark_labels": False,
                "uses_future_publications": False,
                "candidate_acquisition_depends_on_news": False,
                "absence_means_no_news_in_all_sources": False,
            },
            "files": {"news_records": "news-records.json"},
        }
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            records = root / "news-records.json"
            records.write_text(
                json.dumps({"rows": events, "candidate_statuses": statuses}),
                encoding="utf-8",
            )
            (root / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )

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
            events[0]["title"] = "tampered"
            records.write_text(
                json.dumps({"rows": events, "candidate_statuses": statuses}),
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
