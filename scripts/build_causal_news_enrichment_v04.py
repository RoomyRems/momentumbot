from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path

from momentumbot.causal_market_discovery_v03 import (
    CAUSAL_MARKET_DISCOVERY_V0_3_POLICY_ID,
    causal_market_discovery_v0_3_manifest,
    load_market_candidate_payload,
    strategy_profile_manifest,
)
from momentumbot.historical_float_v04 import (
    CAUSAL_FLOAT_V0_2_POLICY_ID,
    load_causal_float_records,
    load_causal_float_root,
    load_float_target_basis,
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
from momentumbot.historical_profile_union_v01 import (
    HISTORICAL_PROFILE_UNION_V0_1_ID,
    historical_profile_union_v0_1,
    historical_profile_union_v0_1_manifest,
)
from momentumbot.identity_resolved_universe import json_fingerprint
from momentumbot.providers.alpaca import AlpacaDataClient, chunked


FIXED_MARKET_DISCOVERY_ID = CAUSAL_MARKET_DISCOVERY_V0_3_POLICY_ID
FIXED_FLOAT_POLICY_ID = CAUSAL_FLOAT_V0_2_POLICY_ID
FIXED_NEWS_POLICY_ID = CAUSAL_NEWS_POLICY_ID
FIXED_ACQUISITION_PROFILE_ID = HISTORICAL_PROFILE_UNION_V0_1_ID


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate_fixed_news_mode(
    *,
    market_discovery_id: str = FIXED_MARKET_DISCOVERY_ID,
    float_policy_id: str = FIXED_FLOAT_POLICY_ID,
    news_policy_id: str = FIXED_NEWS_POLICY_ID,
    acquisition_profile_id: str = FIXED_ACQUISITION_PROFILE_ID,
) -> None:
    """Fail before filesystem or provider access if the v0.4 tuple changes."""

    observed = (
        market_discovery_id,
        float_policy_id,
        news_policy_id,
        acquisition_profile_id,
    )
    expected = (
        FIXED_MARKET_DISCOVERY_ID,
        FIXED_FLOAT_POLICY_ID,
        FIXED_NEWS_POLICY_ID,
        FIXED_ACQUISITION_PROFILE_ID,
    )
    if observed != expected:
        raise ValueError("v0.4 news enrichment requires the frozen integration tuple")


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


def _load_market_root(root: Path) -> dict[str, object]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("market discovery root manifest must be an object")
    if manifest.get("artifact_id") != FIXED_MARKET_DISCOVERY_ID:
        raise ValueError("v0.4 news enrichment requires market discovery v0.3")
    if manifest.get("discovery_policy") != causal_market_discovery_v0_3_manifest():
        raise ValueError("market discovery v0.3 policy mismatch")
    union = historical_profile_union_v0_1_manifest()
    if manifest.get("acquisition_profile_union") != union:
        raise ValueError("market discovery does not bind the frozen profile union")
    expected_hash = json_fingerprint(
        {
            "discovery_policy": manifest.get("discovery_policy"),
            "source_membership_bundle_sha256": manifest.get(
                "source_membership_bundle_sha256"
            ),
            "date_manifests": manifest.get("date_manifests"),
        }
    )
    if manifest.get("content_sha256") != expected_hash:
        raise ValueError("market discovery root content fingerprint mismatch")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--census-root", type=Path, required=True)
    parser.add_argument("--dates", nargs="+")
    parser.add_argument("--news-batch-size", type=int, default=50)
    parser.add_argument("--news-max-pages", type=int, default=100)
    parser.add_argument("--max-candidates-per-date", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    # The v0.4 entry point deliberately exposes no basis/policy/profile switch.
    validate_fixed_news_mode()
    if args.news_batch_size <= 0:
        raise ValueError("news batch size must be positive")
    if args.news_max_pages <= 0:
        raise ValueError("news page ceiling must be positive")
    if args.max_candidates_per_date <= 0:
        raise ValueError("candidate ceiling must be positive")

    market_root = args.census_root / FIXED_MARKET_DISCOVERY_ID
    float_root = args.census_root / FIXED_FLOAT_POLICY_ID
    market_manifest = _load_market_root(market_root)
    dates = args.dates or market_manifest.get("dates")
    if not isinstance(dates, list) or not dates:
        raise ValueError("at least one news-enrichment date is required")
    if dates != sorted(set(dates)):
        raise ValueError("news-enrichment dates must be unique and ordered")
    for value in dates:
        date.fromisoformat(value)
    available = market_manifest.get("dates")
    if not isinstance(available, list) or not set(dates).issubset(available):
        raise ValueError("news dates must exist in the market discovery bundle")
    float_manifest = load_causal_float_root(
        float_root,
        expected_source_market_discovery_bundle_sha256=str(
            market_manifest["content_sha256"]
        ),
    )
    if not isinstance(float_manifest.get("dates"), list) or not set(dates).issubset(
        float_manifest["dates"]
    ):
        raise ValueError("news dates must exist in the float enrichment bundle")
    if float_manifest.get("eligibility", {}).get(
        "point_in_time_float_decisions_frozen"
    ) is not True:
        raise ValueError("news enrichment requires frozen causal float decisions")

    # Validate all provider-independent parents before constructing a client.
    prepared: list[
        tuple[
            str,
            list[dict[str, object]],
            dict[str, object],
            dict[str, object],
            list[dict[str, object]],
            dict[str, object],
            dict[str, object],
        ]
    ] = []
    union_manifest = historical_profile_union_v0_1_manifest()
    acquisition_profile = historical_profile_union_v0_1()
    for value in dates:
        candidate_rows, candidate_payload, market_date_manifest = (
            load_market_candidate_payload(market_root / value)
        )
        if len(candidate_rows) > args.max_candidates_per_date:
            raise RuntimeError(
                f"{value} candidate count exceeds the frozen acquisition ceiling"
            )
        if market_date_manifest.get("strategy_profile") != strategy_profile_manifest(
            acquisition_profile
        ):
            raise ValueError("market date does not use the acquisition profile union")
        if market_date_manifest.get("acquisition_profile_union") != union_manifest:
            raise ValueError("market date profile-union lineage mismatch")
        target_relative = market_date_manifest.get("files", {}).get(
            "float_target_basis"
        )
        if not isinstance(target_relative, str) or not target_relative:
            raise ValueError("market date lacks the qualification-minute float basis")
        target_path = Path(target_relative)
        if target_path.is_absolute() or ".." in target_path.parts:
            raise ValueError("float target-basis path escapes market discovery")
        _target_pairs, target_basis_payload = load_float_target_basis(
            market_root / value / target_path,
            candidate_rows=candidate_rows,
            candidate_payload=candidate_payload,
            expected_trading_date=value,
        )
        if market_date_manifest.get("summary", {}).get(
            "float_target_basis_sha256"
        ) != target_basis_payload.get("content_sha256"):
            raise ValueError("market date float target-basis commitment mismatch")
        market_date_sha = json_fingerprint(market_date_manifest)
        float_records, float_date_manifest = load_causal_float_records(
            float_root / value,
            candidate_rows=candidate_rows,
            candidate_payload=candidate_payload,
            expected_trading_date=value,
            expected_source_market_discovery_manifest_sha256=market_date_sha,
            expected_source_float_target_basis_sha256=str(
                target_basis_payload["content_sha256"]
            ),
        )
        prepared.append(
            (
                value,
                candidate_rows,
                candidate_payload,
                market_date_manifest,
                float_records,
                float_date_manifest,
                target_basis_payload,
            )
        )

    output_root = args.output or args.census_root / FIXED_NEWS_POLICY_ID
    output_root.mkdir(parents=True, exist_ok=False)
    alpaca = AlpacaDataClient.from_env()
    date_manifests: list[dict[str, object]] = []
    fatal_provider_errors: list[dict[str, object]] = []

    for (
        value,
        candidate_rows,
        candidate_payload,
        market_date_manifest,
        float_records,
        float_date_manifest,
        target_basis_payload,
    ) in prepared:
        trading_date = date.fromisoformat(value)
        calendar_bars = _calendar_proxy_bars(alpaca, trading_date=trading_date)
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
                        max_pages=args.news_max_pages,
                    )
                )
            except Exception as exc:
                error = {
                    "trading_date": value,
                    "symbols": list(batch),
                    "error": type(exc).__name__,
                }
                date_errors.append(error)
                fatal_provider_errors.append(error)
                for symbol in batch:
                    provider_status[symbol] = "provider_error_fail_closed"

        successful = {
            symbol for symbol, status in provider_status.items() if status == "success"
        }
        events, dispositions = normalize_alpaca_news(
            raw_rows,
            candidate_symbols=successful,
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
        coverage = news_tape_coverage(candidate_rows, events)
        summary: dict[str, object] = {
            "market_candidate_count": len(candidate_rows),
            "float_decision_count": len(float_records),
            "qualification_status_count": len(statuses),
            "full_window_raw_provider_row_count": len(raw_rows),
            **coverage,
            "candidates_with_news_at_market_qualification_count": sum(
                row["has_provider_news_at_market_qualification"] is True
                for row in statuses
            ),
            "candidates_with_provider_relative_no_news_at_market_qualification_count": sum(
                row["provider_relative_no_news_at_market_qualification"] is True
                for row in statuses
            ),
            "candidates_unknown_fail_closed_at_market_qualification_count": sum(
                row["unknown_fail_closed_at_market_qualification"] is True
                for row in statuses
            ),
            "provider_error_count": len(date_errors),
            "full_window_availability_basis_counts": dict(
                sorted(Counter(str(row["availability_basis"]) for row in events).items())
            ),
            "full_window_normalization_disposition_counts": dispositions,
            "full_window_events_sha256": event_hash,
            "qualification_statuses_sha256": status_hash,
        }
        date_manifest: dict[str, object] = {
            "schema_version": 2,
            "artifact_id": FIXED_NEWS_POLICY_ID,
            "trading_date": value,
            "news_policy": causal_news_v0_2_manifest(),
            "temporal_boundary": causal_news_v0_2_temporal_boundary(),
            "acquisition_profile_union": union_manifest,
            "strategy_profiles_modified": False,
            "source_market_candidates_sha256": candidate_payload["content_sha256"],
            "source_market_discovery_manifest_sha256": json_fingerprint(
                market_date_manifest
            ),
            "source_float_records_sha256": float_date_manifest["summary"][
                "records_sha256"
            ],
            "source_float_manifest_sha256": float_date_manifest["content_sha256"],
            "source_float_target_basis_sha256": target_basis_payload[
                "content_sha256"
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
                "full_window_tape_contains_post_qualification_events": coverage[
                    "full_window_post_qualification_candidate_event_count"
                ]
                > 0,
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
        "artifact_id": FIXED_NEWS_POLICY_ID,
        "dates": dates,
        "news_policy": causal_news_v0_2_manifest(),
        "temporal_boundary": causal_news_v0_2_temporal_boundary(),
        "acquisition_profile_union": union_manifest,
        "strategy_profiles_modified": False,
        "source_market_discovery_bundle_sha256": market_manifest["content_sha256"],
        "source_float_bundle_sha256": float_manifest["content_sha256"],
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
                "artifact_id": FIXED_NEWS_POLICY_ID,
                "acquisition_profile_union_id": FIXED_ACQUISITION_PROFILE_ID,
                "dates": dates,
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
