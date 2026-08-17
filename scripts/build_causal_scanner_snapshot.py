from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
import math
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.causal_market_discovery import (
    CAUSAL_MARKET_CANDIDATES_ARTIFACT_ID,
    CAUSAL_MARKET_DISCOVERY_POLICY_ID,
    identity_membership_as_acquisition_assets,
    load_market_candidate_payload,
    strategy_profile_manifest,
)
from momentumbot.causal_scanner_snapshot import (
    CAUSAL_SCANNER_SNAPSHOT_ARTIFACT_ID,
    RANK_HISTORICAL_FEED,
    RANK_MINUTE_ADJUSTMENT,
    RANK_MINUTE_TIMEFRAME,
    RANK_PREVIOUS_CLOSE_ADJUSTMENT,
    RANK_PREVIOUS_CLOSE_TIMEFRAME,
    RANK_PRIOR_CLOSE_LOOKBACK_CALENDAR_DAYS,
    SESSION_TIMEZONE,
    build_causal_scanner_snapshot_artifacts,
    build_scanner_snapshot_rows,
    causal_scanner_snapshot_v0_1_manifest,
    market_inputs_fingerprint,
    overlay_authoritative_candidate_rank_frames,
    trim_scanner_bar_frame,
    trim_scanner_rvol_series,
)
from momentumbot.historical_data import DiscoveryResult, discover_market_day
from momentumbot.historical_float import (
    CAUSAL_FLOAT_POLICY_ID,
    load_causal_float_records,
)
from momentumbot.historical_news import (
    CAUSAL_NEWS_POLICY_ID,
    load_publication_timed_news,
)
from momentumbot.identity_resolved_universe import (
    IDENTITY_RESOLVED_UNIVERSE_POLICY_ID,
    json_fingerprint,
    load_identity_resolved_universe,
)
from momentumbot.models import StrategyProfile, current_general_2026
from momentumbot.providers.alpaca import AlpacaDataClient


ET = ZoneInfo(SESSION_TIMEZONE)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _previous_split_close(
    frame: pd.DataFrame,
    *,
    trading_date: date,
) -> float | None:
    if frame.empty:
        return None
    if frame.index.tz is None:
        raise ValueError("daily rank bars must be timezone-aware")
    if frame.index.has_duplicates:
        raise ValueError("daily rank bars repeat a timestamp")
    if not frame.index.is_monotonic_increasing:
        raise ValueError("daily rank bars must be ordered")
    local_dates = frame.index.tz_convert(ET).date
    eligible = frame.loc[local_dates < trading_date]
    if eligible.empty or "close" not in eligible:
        return None
    try:
        value = float(eligible.iloc[-1]["close"])
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def reacquire_rank_market_inputs(
    client: AlpacaDataClient,
    *,
    trading_date: date,
    membership_symbols: list[str],
    profile: StrategyProfile,
    asset_batch_size: int,
) -> tuple[dict[str, float], dict[str, pd.DataFrame]]:
    """Reacquire causal cross-sectional inputs for every frozen member.

    Split-adjusted daily bars supply the prior close on the target-date share
    basis.  Raw one-minute bars supply only closes completed by a decision.
    A provider exception is allowed to propagate; it is never converted into
    an empty response or an invented rank.
    """

    if asset_batch_size <= 0:
        raise ValueError("asset batch size must be positive")
    symbols = sorted(str(value).strip().upper() for value in membership_symbols)
    if not symbols or any(not value for value in symbols):
        raise ValueError("rank acquisition requires membership symbols")
    if len(symbols) != len(set(symbols)):
        raise ValueError("rank acquisition membership repeats a symbol")

    daily_start = datetime.combine(
        trading_date
        - timedelta(days=RANK_PRIOR_CLOSE_LOOKBACK_CALENDAR_DAYS),
        time(0),
        timezone.utc,
    )
    daily_end = datetime.combine(
        trading_date + timedelta(days=1),
        time(0),
        timezone.utc,
    )
    split_daily = client.bars_batched(
        symbols,
        batch_size=asset_batch_size,
        timeframe=RANK_PREVIOUS_CLOSE_TIMEFRAME,
        start=daily_start,
        end=daily_end,
        feed=RANK_HISTORICAL_FEED,
        adjustment=RANK_PREVIOUS_CLOSE_ADJUSTMENT,
        asof=trading_date,
    )
    feature_start = datetime.combine(
        trading_date,
        profile.volume_feature_start,
        ET,
    ).astimezone(timezone.utc)
    cutoff = datetime.combine(
        trading_date,
        profile.no_new_entries_after,
        ET,
    ).astimezone(timezone.utc)
    raw_minutes = client.bars_batched(
        symbols,
        batch_size=asset_batch_size,
        timeframe=RANK_MINUTE_TIMEFRAME,
        start=feature_start,
        end=cutoff,
        feed=RANK_HISTORICAL_FEED,
        adjustment=RANK_MINUTE_ADJUSTMENT,
        asof=trading_date,
    )
    quarantined = sorted(
        set(symbols)
        & {
            str(value).strip().upper()
            for value in getattr(client, "invalid_symbols", set())
        }
    )
    if quarantined:
        raise RuntimeError(
            "rank acquisition provider rejected frozen membership symbols: "
            + ",".join(quarantined)
        )
    previous = {
        symbol: close
        for symbol in symbols
        if (
            close := _previous_split_close(
                split_daily.get(symbol, pd.DataFrame()),
                trading_date=trading_date,
            )
        )
        is not None
    }
    return previous, raw_minutes


def verify_reconstructed_market_candidates(
    source_candidate_rows: list[dict[str, object]],
    reconstructed: DiscoveryResult,
) -> None:
    """Require exact candidate-set and corrected decision-time reproduction."""

    source: dict[str, tuple[str, str]] = {}
    for row in source_candidate_rows:
        symbol = str(row.get("symbol") or "")
        timing = (
            str(row.get("first_market_qualified_bar_started_at") or ""),
            str(row.get("first_market_qualified_at") or ""),
        )
        if not symbol or symbol in source or not all(timing):
            raise ValueError("source market candidate timing is incomplete")
        source[symbol] = timing
    rebuilt: dict[str, tuple[str, str]] = {}
    rebuilt_previous: dict[str, float] = {}
    for row in reconstructed.rows:
        if row.first_market_qualified_at is None:
            continue
        if row.first_market_qualified_bar_started_at is None:
            raise ValueError("reconstructed candidate lacks source bar start")
        if row.symbol in rebuilt:
            raise ValueError("reconstructed market candidates repeat a symbol")
        rebuilt[row.symbol] = (
            row.first_market_qualified_bar_started_at,
            row.first_market_qualified_at,
        )
        rebuilt_previous[row.symbol] = float(row.previous_close)
    if set(rebuilt) != set(source):
        missing = sorted(set(source) - set(rebuilt))
        extra = sorted(set(rebuilt) - set(source))
        raise ValueError(
            f"reconstructed market candidate set mismatch; missing={missing}, extra={extra}"
        )
    for symbol in sorted(source):
        if rebuilt[symbol] != source[symbol]:
            raise ValueError(
                f"reconstructed first qualification timestamp mismatch for {symbol}"
            )
        expected_previous = float(
            next(
                row["previous_close"]
                for row in source_candidate_rows
                if str(row["symbol"]) == symbol
            )
        )
        if not math.isclose(
            rebuilt_previous[symbol],
            expected_previous,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError(
                f"reconstructed previous close mismatch for {symbol}"
            )
    if reconstructed.market_candidate_count != len(source):
        raise ValueError("reconstructed market candidate count mismatch")
    if set(reconstructed.minutes) != set(source):
        raise ValueError("reconstructed candidate minute coverage mismatch")
    if set(reconstructed.rvol_curves) != set(source):
        raise ValueError("reconstructed candidate RVOL coverage mismatch")


def _read_bundle_manifest(path: Path, *, artifact_id: str) -> dict[str, object]:
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("artifact_id") != artifact_id:
        raise ValueError(f"unsupported source bundle at {path}")
    return manifest


def _assert_dates_available(
    dates: list[str],
    manifests: Mapping[str, dict[str, object]],
) -> None:
    for name, manifest in manifests.items():
        available = manifest.get("dates")
        if not isinstance(available, list) or not set(dates).issubset(available):
            raise ValueError(f"scanner dates are absent from {name} source bundle")


def _validate_root_content_fingerprint(manifest: dict[str, object]) -> None:
    artifact_id = manifest.get("artifact_id")
    if artifact_id == CAUSAL_MARKET_DISCOVERY_POLICY_ID:
        projection = {
            "discovery_policy": manifest.get("discovery_policy"),
            "source_membership_bundle_sha256": manifest.get(
                "source_membership_bundle_sha256"
            ),
            "date_manifests": manifest.get("date_manifests"),
        }
    elif artifact_id == CAUSAL_FLOAT_POLICY_ID:
        projection = {
            "float_policy": manifest.get("float_policy"),
            "source_market_discovery_bundle_sha256": manifest.get(
                "source_market_discovery_bundle_sha256"
            ),
            "date_manifests": manifest.get("date_manifests"),
        }
    elif artifact_id == CAUSAL_NEWS_POLICY_ID:
        projection = {
            "news_policy": manifest.get("news_policy"),
            "temporal_boundary": manifest.get("temporal_boundary"),
            "source_market_discovery_bundle_sha256": manifest.get(
                "source_market_discovery_bundle_sha256"
            ),
            "source_float_bundle_sha256": manifest.get(
                "source_float_bundle_sha256"
            ),
            "date_manifests": manifest.get("date_manifests"),
        }
    elif artifact_id == IDENTITY_RESOLVED_UNIVERSE_POLICY_ID:
        # The identity loader validates its richer bundle projection in full.
        if not str(manifest.get("content_sha256") or ""):
            raise ValueError("identity membership root content hash is missing")
        return
    else:
        raise ValueError("unsupported scanner lineage root artifact")
    if manifest.get("content_sha256") != json_fingerprint(projection):
        raise ValueError(f"{artifact_id} root content fingerprint mismatch")


def _root_date_manifest(
    root_manifest: dict[str, object],
    *,
    trading_date: str,
) -> dict[str, object]:
    rows = root_manifest.get("date_manifests")
    if not isinstance(rows, list):
        raise ValueError("source root lacks date manifests")
    matched = [
        row
        for row in rows
        if isinstance(row, dict) and row.get("trading_date") == trading_date
    ]
    if len(matched) != 1:
        raise ValueError(
            f"source root must contain exactly one date manifest for {trading_date}"
        )
    return matched[0]


def validate_cross_artifact_lineage(
    *,
    trading_date: str,
    profile: StrategyProfile,
    membership_root_manifest: dict[str, object],
    market_root_manifest: dict[str, object],
    float_root_manifest: dict[str, object],
    news_root_manifest: dict[str, object],
    membership_payload: dict[str, object],
    candidate_payload: dict[str, object],
    market_date_manifest: dict[str, object],
    float_date_manifest: dict[str, object],
    news_date_manifest: dict[str, object],
) -> None:
    """Verify every root and date hash edge from membership through news."""

    for manifest in (
        membership_root_manifest,
        market_root_manifest,
        float_root_manifest,
        news_root_manifest,
    ):
        _validate_root_content_fingerprint(manifest)
    if membership_payload.get("trading_date") != trading_date:
        raise ValueError("membership payload date mismatch")
    if membership_payload.get("artifact_id") != (
        IDENTITY_RESOLVED_UNIVERSE_POLICY_ID
    ):
        raise ValueError("membership payload artifact id mismatch")
    if candidate_payload.get("trading_date") != trading_date:
        raise ValueError("market candidate payload date mismatch")
    if candidate_payload.get("artifact_id") != (
        CAUSAL_MARKET_CANDIDATES_ARTIFACT_ID
    ):
        raise ValueError("market candidate artifact id mismatch")
    for date_manifest, expected_id, label in (
        (
            market_date_manifest,
            CAUSAL_MARKET_DISCOVERY_POLICY_ID,
            "market",
        ),
        (float_date_manifest, CAUSAL_FLOAT_POLICY_ID, "float"),
        (news_date_manifest, CAUSAL_NEWS_POLICY_ID, "news"),
    ):
        if date_manifest.get("trading_date") != trading_date:
            raise ValueError(f"{label} date manifest date mismatch")
        if date_manifest.get("artifact_id") != expected_id:
            raise ValueError(f"{label} date manifest artifact id mismatch")
    membership_root_sha = str(membership_root_manifest["content_sha256"])
    market_root_sha = str(market_root_manifest["content_sha256"])
    float_root_sha = str(float_root_manifest["content_sha256"])
    if market_root_manifest.get(
        "source_membership_bundle_sha256"
    ) != membership_root_sha:
        raise ValueError("market root does not descend from membership root")
    if float_root_manifest.get(
        "source_market_discovery_bundle_sha256"
    ) != market_root_sha:
        raise ValueError("float root does not descend from market root")
    if news_root_manifest.get(
        "source_market_discovery_bundle_sha256"
    ) != market_root_sha:
        raise ValueError("news root does not descend from market root")
    if news_root_manifest.get("source_float_bundle_sha256") != float_root_sha:
        raise ValueError("news root does not descend from float root")

    for root, date_manifest, label in (
        (market_root_manifest, market_date_manifest, "market"),
        (float_root_manifest, float_date_manifest, "float"),
        (news_root_manifest, news_date_manifest, "news"),
    ):
        if _root_date_manifest(root, trading_date=trading_date) != date_manifest:
            raise ValueError(f"{label} date manifest differs from its root bundle")
    membership_sha = membership_payload.get("summary", {}).get(
        "membership_sha256"
    )
    market_membership = market_date_manifest.get("source_membership", {})
    if market_membership.get("membership_sha256") != membership_sha:
        raise ValueError("market date membership hash mismatch")
    if market_membership.get("membership_bundle_sha256") != membership_root_sha:
        raise ValueError("market date membership root hash mismatch")
    if market_membership.get("membership_payload_sha256") != json_fingerprint(
        membership_payload
    ):
        raise ValueError("market date membership payload hash mismatch")
    if market_date_manifest.get("strategy_profile") != strategy_profile_manifest(
        profile
    ):
        raise ValueError("market date strategy profile mismatch")
    if market_date_manifest.get("summary", {}).get(
        "causal_market_candidate_set_sha256"
    ) != candidate_payload.get("content_sha256"):
        raise ValueError("market date candidate hash mismatch")

    market_date_sha = json_fingerprint(market_date_manifest)
    if float_date_manifest.get(
        "source_market_candidates_sha256"
    ) != candidate_payload.get("content_sha256"):
        raise ValueError("float date candidate hash mismatch")
    if float_date_manifest.get(
        "source_market_discovery_manifest_sha256"
    ) != market_date_sha:
        raise ValueError("float date market-manifest hash mismatch")
    float_records_sha = float_date_manifest.get("summary", {}).get(
        "records_sha256"
    )
    if news_date_manifest.get(
        "source_market_candidates_sha256"
    ) != candidate_payload.get("content_sha256"):
        raise ValueError("news date candidate hash mismatch")
    if news_date_manifest.get(
        "source_market_discovery_manifest_sha256"
    ) != market_date_sha:
        raise ValueError("news date market-manifest hash mismatch")
    if news_date_manifest.get(
        "source_float_records_sha256"
    ) != float_records_sha:
        raise ValueError("news date float-record hash mismatch")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--census-root", type=Path, required=True)
    parser.add_argument("--dates", nargs="+")
    parser.add_argument("--asset-batch-size", type=int, default=250)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.asset_batch_size <= 0:
        raise ValueError("asset batch size must be positive")

    membership_root = args.census_root / IDENTITY_RESOLVED_UNIVERSE_POLICY_ID
    market_root = args.census_root / CAUSAL_MARKET_DISCOVERY_POLICY_ID
    float_root = args.census_root / CAUSAL_FLOAT_POLICY_ID
    news_root = args.census_root / CAUSAL_NEWS_POLICY_ID
    bundle_manifests = {
        "membership": _read_bundle_manifest(
            membership_root,
            artifact_id=IDENTITY_RESOLVED_UNIVERSE_POLICY_ID,
        ),
        "market": _read_bundle_manifest(
            market_root,
            artifact_id=CAUSAL_MARKET_DISCOVERY_POLICY_ID,
        ),
        "float": _read_bundle_manifest(
            float_root,
            artifact_id=CAUSAL_FLOAT_POLICY_ID,
        ),
        "news": _read_bundle_manifest(
            news_root,
            artifact_id=CAUSAL_NEWS_POLICY_ID,
        ),
    }
    dates = args.dates or bundle_manifests["market"].get("dates")
    if not isinstance(dates, list) or not dates:
        raise ValueError("at least one scanner date is required")
    if len(dates) != len(set(dates)):
        raise ValueError("scanner dates must be unique")
    for value in dates:
        date.fromisoformat(value)
    _assert_dates_available(dates, bundle_manifests)

    output_root = args.output or args.census_root / CAUSAL_SCANNER_SNAPSHOT_ARTIFACT_ID
    output_root.mkdir(parents=True, exist_ok=False)
    client = AlpacaDataClient.from_env()
    profile = current_general_2026()
    date_manifests: list[dict[str, object]] = []
    for value in dates:
        trading_date = date.fromisoformat(value)
        membership_rows, membership_payload, membership_bundle_manifest = (
            load_identity_resolved_universe(
                membership_root,
                trading_date=value,
            )
        )
        candidate_rows, candidate_payload, market_date_manifest = (
            load_market_candidate_payload(market_root / value)
        )
        float_records, float_date_manifest = load_causal_float_records(
            float_root / value,
            candidate_rows=candidate_rows,
            candidate_payload=candidate_payload,
        )
        float_records_sha = str(
            float_date_manifest["summary"]["records_sha256"]
        )
        news_events, news_statuses, news_date_manifest = (
            load_publication_timed_news(
                news_root / value,
                candidate_rows=candidate_rows,
                candidate_payload=candidate_payload,
                source_float_records_sha256=float_records_sha,
            )
        )
        validate_cross_artifact_lineage(
            trading_date=value,
            profile=profile,
            membership_root_manifest=membership_bundle_manifest,
            market_root_manifest=bundle_manifests["market"],
            float_root_manifest=bundle_manifests["float"],
            news_root_manifest=bundle_manifests["news"],
            membership_payload=membership_payload,
            candidate_payload=candidate_payload,
            market_date_manifest=market_date_manifest,
            float_date_manifest=float_date_manifest,
            news_date_manifest=news_date_manifest,
        )

        assets = identity_membership_as_acquisition_assets(membership_rows)
        reconstructed = discover_market_day(
            client,
            trading_date=trading_date,
            profile=profile,
            asset_batch_size=args.asset_batch_size,
            assets=assets,
        )
        verify_reconstructed_market_candidates(candidate_rows, reconstructed)
        membership_symbols = sorted(str(row["ticker"]) for row in membership_rows)
        previous_closes, rank_minutes = reacquire_rank_market_inputs(
            client,
            trading_date=trading_date,
            membership_symbols=membership_symbols,
            profile=profile,
            asset_batch_size=args.asset_batch_size,
        )
        rank_minutes = {
            symbol: trim_scanner_bar_frame(
                frame,
                trading_date=trading_date,
                start=profile.volume_feature_start,
                cutoff=profile.no_new_entries_after,
                label=f"reacquired rank bars for {symbol}",
            )
            for symbol, frame in rank_minutes.items()
        }
        candidate_minutes = {
            symbol: trim_scanner_bar_frame(
                frame,
                trading_date=trading_date,
                start=profile.volume_feature_start,
                cutoff=profile.no_new_entries_after,
                label=f"authoritative candidate bars for {symbol}",
            )
            for symbol, frame in reconstructed.minutes.items()
        }
        candidate_rvol = {
            symbol: trim_scanner_rvol_series(
                series,
                trading_date=trading_date,
                start=profile.volume_feature_start,
                cutoff=profile.no_new_entries_after,
                label=f"authoritative candidate RVOL for {symbol}",
            )
            for symbol, series in reconstructed.rvol_curves.items()
        }
        rank_minutes = overlay_authoritative_candidate_rank_frames(
            membership_symbols=membership_symbols,
            reacquired_rank_frames=rank_minutes,
            authoritative_candidate_frames=candidate_minutes,
        )
        for candidate in candidate_rows:
            symbol = str(candidate["symbol"])
            rank_previous = previous_closes.get(symbol)
            if rank_previous is None or not math.isclose(
                rank_previous,
                float(candidate["previous_close"]),
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise ValueError(
                    f"rank reacquisition previous close mismatch for {symbol}"
                )

        input_sha = market_inputs_fingerprint(
            trading_date=trading_date,
            profile=profile,
            membership_symbols=membership_symbols,
            previous_close_by_symbol=previous_closes,
            rank_raw_minute_bars_by_symbol=rank_minutes,
            candidate_raw_minute_bars_by_symbol=candidate_minutes,
            candidate_exact_rvol_by_symbol=candidate_rvol,
        )
        source_hashes = {
            "identity_resolved_membership": str(
                membership_payload["summary"]["membership_sha256"]
            ),
            "market_candidates": str(candidate_payload["content_sha256"]),
            "market_discovery_manifest": json_fingerprint(market_date_manifest),
            "causal_float_records": float_records_sha,
            "causal_float_manifest": json_fingerprint(float_date_manifest),
            "publication_timed_news_events": str(
                news_date_manifest["summary"]["full_window_events_sha256"]
            ),
            "publication_timed_news_statuses": str(
                news_date_manifest["summary"]["qualification_statuses_sha256"]
            ),
            "publication_timed_news_manifest": json_fingerprint(
                news_date_manifest
            ),
            "reacquired_market_inputs": input_sha,
        }
        rows = build_scanner_snapshot_rows(
            trading_date=trading_date,
            profile=profile,
            candidate_rows=candidate_rows,
            float_records=float_records,
            news_events=news_events,
            news_statuses=news_statuses,
            membership_symbols=membership_symbols,
            previous_close_by_symbol=previous_closes,
            rank_raw_minute_bars_by_symbol=rank_minutes,
            candidate_raw_minute_bars_by_symbol=candidate_minutes,
            candidate_exact_rvol_by_symbol=candidate_rvol,
        )
        payload, manifest = build_causal_scanner_snapshot_artifacts(
            trading_date=trading_date,
            profile=profile,
            candidate_rows=candidate_rows,
            membership_symbols=membership_symbols,
            rows=rows,
            source_hashes=source_hashes,
        )
        date_root = output_root / value
        date_root.mkdir()
        _write_json(date_root / "scanner-snapshot.json", payload)
        _write_json(date_root / "manifest.json", manifest)
        date_manifests.append(manifest)

    root_manifest: dict[str, object] = {
        "schema_version": 1,
        "artifact_id": CAUSAL_SCANNER_SNAPSHOT_ARTIFACT_ID,
        "dates": dates,
        "scanner_policy": causal_scanner_snapshot_v0_1_manifest(),
        "source_bundle_hashes": {
            name: manifest.get("content_sha256")
            for name, manifest in bundle_manifests.items()
        },
        "date_manifests": date_manifests,
        "eligibility": {
            "complete_relative_to_identity_resolved_membership": True,
            "candidate_minute_dispositions_frozen": True,
            "universe_complete": False,
            "full_walk_forward_eligible": False,
            "policy_promotion_eligible": False,
        },
        "knowledge_policy": {
            "uses_benchmark_labels": False,
            "uses_retrospective_trade_outcomes": False,
            "future_session_extrema_used_as_snapshot_feature": False,
            "source_market_full_day_high_used_for_acquisition_only": True,
            "source_acquisition_prefilter_exposed_to_snapshot": False,
            "contains_trades_setups_portfolio_or_pnl": False,
        },
        "provider_error_boundary": {
            "upstream_float_loader_requires_complete_date": True,
            "upstream_news_loader_requires_complete_date": True,
            "fatal_provider_error_emits_partial_date": False,
            "row_fail_closed_scope": (
                "defensive_validated_per_symbol_status_only"
            ),
        },
        "source_replay_boundary": {
            "raw_reacquired_market_inputs_persisted": False,
            "reacquired_market_inputs_sha256_role": (
                "integrity_commitment_only"
            ),
            "independent_feature_recomputation_from_snapshot_artifact": False,
            "source_provider_replay_required_for_recomputation": True,
            "todo": (
                "persist_compact_compressed_canonical_source_input_bundle"
            ),
        },
    }
    root_manifest["content_sha256"] = json_fingerprint(
        {
            key: value
            for key, value in root_manifest.items()
            if key != "content_sha256"
        }
    )
    _write_json(output_root / "manifest.json", root_manifest)
    print(
        json.dumps(
            {
                "artifact_id": CAUSAL_SCANNER_SNAPSHOT_ARTIFACT_ID,
                "dates": dates,
                "candidate_minute_disposition_counts": {
                    manifest["trading_date"]: manifest["summary"][
                        "candidate_minute_disposition_count"
                    ]
                    for manifest in date_manifests
                },
                "complete_relative_to_identity_resolved_membership": True,
                "universe_complete": False,
                "full_walk_forward_eligible": False,
                "policy_promotion_eligible": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
