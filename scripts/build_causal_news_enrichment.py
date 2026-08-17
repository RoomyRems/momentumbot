from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path

from momentumbot.causal_market_discovery import (
    CAUSAL_MARKET_DISCOVERY_POLICY_ID,
    load_market_candidate_payload,
)
from momentumbot.historical_float import (
    CAUSAL_FLOAT_POLICY_ID,
    load_causal_float_records,
)
from momentumbot.historical_news import (
    CAUSAL_NEWS_POLICY_ID,
    build_news_candidate_statuses,
    causal_news_v0_2_manifest,
    causal_news_v0_2_temporal_boundary,
    news_events_fingerprint,
    news_statuses_fingerprint,
    news_tape_coverage,
    normalize_alpaca_news,
    prior_regular_session_date,
    publication_window,
    validate_publication_timed_news,
)
from momentumbot.identity_resolved_universe import json_fingerprint
from momentumbot.providers.alpaca import AlpacaDataClient, chunked


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _calendar_proxy_bars(
    client: AlpacaDataClient,
    *,
    trading_date: date,
):
    start = datetime.combine(
        trading_date - timedelta(days=14),
        time(0),
        timezone.utc,
    )
    end = datetime.combine(
        trading_date + timedelta(days=1),
        time(0),
        timezone.utc,
    )
    return client.bars(
        ["SPY"],
        timeframe="1Day",
        start=start,
        end=end,
        feed="sip",
        adjustment="raw",
        asof=trading_date,
    ).get("SPY")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--census-root", type=Path, required=True)
    parser.add_argument("--dates", nargs="+")
    parser.add_argument("--news-batch-size", type=int, default=50)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.news_batch_size <= 0:
        raise ValueError("news batch size must be positive")

    discovery_root = args.census_root / CAUSAL_MARKET_DISCOVERY_POLICY_ID
    float_root = args.census_root / CAUSAL_FLOAT_POLICY_ID
    discovery_manifest = json.loads(
        (discovery_root / "manifest.json").read_text(encoding="utf-8")
    )
    float_bundle_manifest = json.loads(
        (float_root / "manifest.json").read_text(encoding="utf-8")
    )
    dates = args.dates or discovery_manifest.get("dates")
    if not isinstance(dates, list) or not dates:
        raise ValueError("at least one news-enrichment date is required")
    if len(dates) != len(set(dates)):
        raise ValueError("news-enrichment dates must be unique")
    float_dates = float_bundle_manifest.get("dates")
    discovery_dates = discovery_manifest.get("dates")
    if not isinstance(float_dates, list) or not set(dates).issubset(float_dates):
        raise ValueError("news dates must exist in the float enrichment bundle")
    if not isinstance(discovery_dates, list) or not set(dates).issubset(
        discovery_dates
    ):
        raise ValueError("news dates must exist in the market discovery bundle")
    if float_bundle_manifest.get("eligibility", {}).get(
        "point_in_time_float_decisions_frozen"
    ) is not True:
        raise ValueError("news enrichment requires frozen causal float decisions")

    output_root = args.output or args.census_root / CAUSAL_NEWS_POLICY_ID
    output_root.mkdir(parents=True, exist_ok=False)
    alpaca = AlpacaDataClient.from_env()
    date_manifests: list[dict[str, object]] = []
    fatal_provider_errors: list[dict[str, object]] = []

    for value in dates:
        trading_date = date.fromisoformat(value)
        candidate_rows, candidate_payload, discovery_date_manifest = (
            load_market_candidate_payload(discovery_root / value)
        )
        float_records, float_date_manifest = load_causal_float_records(
            float_root / value,
            candidate_rows=candidate_rows,
            candidate_payload=candidate_payload,
        )
        calendar_bars = _calendar_proxy_bars(
            alpaca,
            trading_date=trading_date,
        )
        if calendar_bars is None:
            raise RuntimeError("SPY calendar proxy is absent from Alpaca response")
        prior_session = prior_regular_session_date(
            calendar_bars,
            trading_date=trading_date,
        )
        window_start, window_end = publication_window(
            trading_date=trading_date,
            prior_session=prior_session,
        )

        symbols = sorted(str(row["symbol"]) for row in candidate_rows)
        provider_status = {symbol: "success" for symbol in symbols}
        raw_rows: list[dict[str, object]] = []
        date_errors: list[dict[str, object]] = []
        for batch in chunked(symbols, args.news_batch_size):
            try:
                raw_rows.extend(
                    alpaca.news(
                        batch,
                        start=window_start,
                        end=window_end,
                        include_content=False,
                    )
                )
            except Exception as exc:  # A missing provider page is not no-news.
                error = {
                    "trading_date": value,
                    "symbols": list(batch),
                    "error": type(exc).__name__,
                }
                date_errors.append(error)
                fatal_provider_errors.append(error)
                for symbol in batch:
                    provider_status[symbol] = "provider_error_fail_closed"

        successful_symbols = {
            symbol for symbol, status in provider_status.items() if status == "success"
        }
        events, normalization_dispositions = normalize_alpaca_news(
            raw_rows,
            candidate_symbols=successful_symbols,
            window_start=window_start,
            window_end=window_end,
        )
        statuses = build_news_candidate_statuses(
            candidate_rows,
            events,
            provider_status_by_symbol=provider_status,
        )
        validate_publication_timed_news(
            candidate_rows,
            events,
            statuses,
            window_start=window_start,
            window_end=window_end,
        )

        event_hash = news_events_fingerprint(events)
        status_hash = news_statuses_fingerprint(statuses)
        tape_coverage = news_tape_coverage(candidate_rows, events)
        summary: dict[str, object] = {
            "market_candidate_count": len(candidate_rows),
            "float_decision_count": len(float_records),
            "qualification_status_count": len(statuses),
            "full_window_raw_provider_row_count": len(raw_rows),
            **tape_coverage,
            "candidates_with_news_at_market_qualification_count": sum(
                row["has_provider_news_at_market_qualification"] is True
                for row in statuses
            ),
            (
                "candidates_with_provider_relative_no_news_"
                "at_market_qualification_count"
            ): sum(
                row[
                    "provider_relative_no_news_at_market_qualification"
                ] is True
                for row in statuses
            ),
            "candidates_unknown_fail_closed_at_market_qualification_count": sum(
                row["unknown_fail_closed_at_market_qualification"] is True
                for row in statuses
            ),
            "provider_error_count": len(date_errors),
            "full_window_availability_basis_counts": dict(
                sorted(
                    Counter(str(row["availability_basis"]) for row in events).items()
                )
            ),
            "full_window_normalization_disposition_counts": (
                normalization_dispositions
            ),
            "full_window_events_sha256": event_hash,
            "qualification_statuses_sha256": status_hash,
        }
        date_manifest: dict[str, object] = {
            "schema_version": 2,
            "artifact_id": CAUSAL_NEWS_POLICY_ID,
            "trading_date": value,
            "news_policy": causal_news_v0_2_manifest(),
            "temporal_boundary": causal_news_v0_2_temporal_boundary(),
            "source_market_candidates_sha256": candidate_payload["content_sha256"],
            "source_market_discovery_manifest_sha256": json_fingerprint(
                discovery_date_manifest
            ),
            "source_float_records_sha256": float_date_manifest["summary"][
                "records_sha256"
            ],
            "publication_window": {
                "calendar_proxy": "SPY_alpaca_sip_daily",
                "prior_regular_session": prior_session.isoformat(),
                "start": window_start.isoformat(),
                "end_exclusive": window_end.isoformat(),
            },
            "summary": summary,
            "provider_errors": date_errors,
            "eligibility": {
                "complete_relative_to_provider": not date_errors,
                "publication_timed_news_frozen": not date_errors,
                "point_in_time_float_complete": True,
                "full_feature_snapshot_complete": False,
                "universe_complete": False,
                "full_walk_forward_eligible": False,
                "policy_promotion_eligible": False,
            },
            "knowledge_policy": {
                "uses_benchmark_labels": False,
                "uses_retrospective_trade_outcomes": False,
                "qualification_status_uses_future_publications": False,
                "full_window_tape_contains_post_qualification_events": (
                    tape_coverage[
                        "full_window_post_qualification_candidate_event_count"
                    ]
                    > 0
                ),
                "full_window_tape_is_runtime_safe_without_projection": False,
                "candidate_acquisition_depends_on_news": False,
                "absence_means_no_news_in_all_sources": False,
                "headline_quality_classified": False,
            },
            "files": {
                "news_records": "news-records.json",
                "news_records_schema": (
                    "full_window_event_tape_plus_as_of_qualification_statuses"
                ),
            },
        }
        date_root = output_root / value
        date_root.mkdir()
        _write_json(
            date_root / "news-records.json",
            {
                "schema_version": 2,
                "full_window_event_tape": events,
                "qualification_statuses": statuses,
            },
        )
        _write_json(date_root / "manifest.json", date_manifest)
        date_manifests.append(date_manifest)

    root_manifest: dict[str, object] = {
        "schema_version": 2,
        "artifact_id": CAUSAL_NEWS_POLICY_ID,
        "dates": dates,
        "news_policy": causal_news_v0_2_manifest(),
        "temporal_boundary": causal_news_v0_2_temporal_boundary(),
        "source_market_discovery_bundle_sha256": discovery_manifest[
            "content_sha256"
        ],
        "source_float_bundle_sha256": float_bundle_manifest["content_sha256"],
        "date_manifests": date_manifests,
        "fatal_provider_errors": fatal_provider_errors,
        "eligibility": {
            "complete_relative_to_provider": not fatal_provider_errors,
            "publication_timed_news_frozen": not fatal_provider_errors,
            "full_feature_snapshot_complete": False,
            "universe_complete": False,
            "full_walk_forward_eligible": False,
            "policy_promotion_eligible": False,
        },
        "knowledge_policy": {
            "uses_benchmark_labels": False,
            "uses_retrospective_trade_outcomes": False,
            "qualification_status_uses_future_publications": False,
            "full_window_tape_contains_post_qualification_events": any(
                manifest["knowledge_policy"][
                    "full_window_tape_contains_post_qualification_events"
                ]
                for manifest in date_manifests
            ),
            "full_window_tape_is_runtime_safe_without_projection": False,
            "candidate_acquisition_depends_on_news": False,
            "absence_means_no_news_in_all_sources": False,
        },
    }
    root_manifest["content_sha256"] = json_fingerprint(
        {
            "news_policy": root_manifest["news_policy"],
            "temporal_boundary": root_manifest["temporal_boundary"],
            "source_market_discovery_bundle_sha256": root_manifest[
                "source_market_discovery_bundle_sha256"
            ],
            "source_float_bundle_sha256": root_manifest[
                "source_float_bundle_sha256"
            ],
            "date_manifests": date_manifests,
        }
    )
    _write_json(output_root / "manifest.json", root_manifest)
    print(
        json.dumps(
            {
                "artifact_id": CAUSAL_NEWS_POLICY_ID,
                "dates": dates,
                "news_counts": {
                    manifest["trading_date"]: manifest["summary"]
                    for manifest in date_manifests
                },
                "fatal_provider_error_count": len(fatal_provider_errors),
                "full_feature_snapshot_complete": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 2 if fatal_provider_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
