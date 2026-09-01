from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
import math
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.causal_market_discovery_v03 import (
    CAUSAL_MARKET_CANDIDATES_V0_3_ARTIFACT_ID,
    CAUSAL_MARKET_DISCOVERY_V0_3_POLICY_ID,
    causal_market_discovery_v0_3_manifest,
    identity_membership_as_acquisition_assets,
    load_market_candidate_payload,
    strategy_profile_manifest,
)
from momentumbot.causal_scanner_snapshot_v03 import (
    CAUSAL_SCANNER_SNAPSHOT_V0_3_ARTIFACT_ID,
    CAUSAL_SCANNER_SNAPSHOT_V0_3_POLICY_ID,
    CANDIDATE_VALUE_ABS_TOL,
    CANDIDATE_VALUE_REL_TOL,
    NORMALIZED_RANK_MINUTE_ADJUSTMENT,
    RANK_HISTORICAL_FEED,
    RANK_MINUTE_TIMEFRAME,
    RANK_PREVIOUS_CLOSE_ADJUSTMENT,
    RANK_PREVIOUS_CLOSE_TIMEFRAME,
    RANK_PRIOR_CLOSE_LOOKBACK_CALENDAR_DAYS,
    SESSION_TIMEZONE,
    UPSTREAM_MARKET_ACQUISITION_TAIL_END,
    build_causal_scanner_snapshot_artifacts,
    build_scanner_snapshot_rows,
    causal_scanner_snapshot_v0_3_manifest,
    load_causal_scanner_snapshot,
    trim_scanner_bar_frame,
    trim_scanner_rvol_series,
)
from momentumbot.historical_data_v03 import (
    DiscoveryResult,
    SPLIT_CONSISTENT_GAIN_BASIS,
    discover_market_day,
)
from momentumbot.historical_float_v04 import (
    CAUSAL_FLOAT_V0_2_POLICY_ID,
    load_causal_float_records,
    load_causal_float_root,
    load_float_target_basis,
)
from momentumbot.historical_news import (
    CAUSAL_NEWS_POLICY_ID,
    causal_news_v0_2_manifest,
    causal_news_v0_2_temporal_boundary,
    load_publication_timed_news,
)
from momentumbot.historical_profile_union_v01 import (
    HISTORICAL_PROFILE_UNION_V0_1_ID,
    historical_profile_union_v0_1,
    historical_profile_union_v0_1_manifest,
)
from momentumbot.identity_resolved_universe import (
    IDENTITY_RESOLVED_UNIVERSE_POLICY_ID,
    json_fingerprint,
    load_identity_resolved_universe,
)
from momentumbot.models import StrategyProfile
from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.scanner_source_inputs_v03 import (
    ARTIFACT_ID as SCANNER_SOURCE_INPUT_ARTIFACT_ID,
    build_scanner_source_input_root_manifest,
    load_scanner_source_input_bundle,
    validate_scanner_source_input_root_manifest,
    write_scanner_source_input_bundle,
)


FIXED_GAIN_BASIS = SPLIT_CONSISTENT_GAIN_BASIS
FIXED_MARKET_DISCOVERY_ID = CAUSAL_MARKET_DISCOVERY_V0_3_POLICY_ID
FIXED_FLOAT_POLICY_ID = CAUSAL_FLOAT_V0_2_POLICY_ID
FIXED_NEWS_POLICY_ID = CAUSAL_NEWS_POLICY_ID
FIXED_SCANNER_POLICY_ID = CAUSAL_SCANNER_SNAPSHOT_V0_3_POLICY_ID
FIXED_SCANNER_ARTIFACT_ID = CAUSAL_SCANNER_SNAPSHOT_V0_3_ARTIFACT_ID
FIXED_SOURCE_INPUT_ARTIFACT_ID = SCANNER_SOURCE_INPUT_ARTIFACT_ID
FIXED_ACQUISITION_PROFILE_ID = HISTORICAL_PROFILE_UNION_V0_1_ID

ET = ZoneInfo(SESSION_TIMEZONE)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _rehash(payload: dict[str, object]) -> None:
    payload["content_sha256"] = json_fingerprint(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )


def validate_fixed_scanner_mode(
    *,
    gain_basis: str = FIXED_GAIN_BASIS,
    market_discovery_id: str = FIXED_MARKET_DISCOVERY_ID,
    float_policy_id: str = FIXED_FLOAT_POLICY_ID,
    news_policy_id: str = FIXED_NEWS_POLICY_ID,
    scanner_policy_id: str = FIXED_SCANNER_POLICY_ID,
    scanner_artifact_id: str = FIXED_SCANNER_ARTIFACT_ID,
    source_input_artifact_id: str = FIXED_SOURCE_INPUT_ARTIFACT_ID,
    acquisition_profile_id: str = FIXED_ACQUISITION_PROFILE_ID,
) -> None:
    """Reject a mixed policy/basis tuple before touching files or providers."""

    observed = (
        gain_basis,
        market_discovery_id,
        float_policy_id,
        news_policy_id,
        scanner_policy_id,
        scanner_artifact_id,
        source_input_artifact_id,
        acquisition_profile_id,
    )
    expected = (
        FIXED_GAIN_BASIS,
        FIXED_MARKET_DISCOVERY_ID,
        FIXED_FLOAT_POLICY_ID,
        FIXED_NEWS_POLICY_ID,
        FIXED_SCANNER_POLICY_ID,
        FIXED_SCANNER_ARTIFACT_ID,
        FIXED_SOURCE_INPUT_ARTIFACT_ID,
        FIXED_ACQUISITION_PROFILE_ID,
    )
    if observed != expected:
        raise ValueError("v0.4 scanner requires the frozen raw/split integration tuple")


def _previous_split_close(frame: pd.DataFrame, *, trading_date: date) -> float | None:
    if frame.empty:
        return None
    if frame.index.tz is None or frame.index.has_duplicates:
        raise ValueError("daily split bars have invalid timestamps")
    if not frame.index.is_monotonic_increasing:
        raise ValueError("daily split bars must be ordered")
    eligible = frame.loc[frame.index.tz_convert(ET).date < trading_date]
    if eligible.empty or "close" not in eligible:
        return None
    try:
        value = float(eligible.iloc[-1]["close"])
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def reacquire_split_rank_market_inputs(
    client: AlpacaDataClient,
    *,
    trading_date: date,
    membership_symbols: list[str],
    profile: StrategyProfile,
    asset_batch_size: int,
) -> tuple[dict[str, float], dict[str, pd.DataFrame]]:
    if asset_batch_size <= 0:
        raise ValueError("asset batch size must be positive")
    symbols = sorted(str(value).strip().upper() for value in membership_symbols)
    if not symbols or any(not value for value in symbols) or len(symbols) != len(
        set(symbols)
    ):
        raise ValueError("rank acquisition requires unique membership symbols")
    daily_start = datetime.combine(
        trading_date - timedelta(days=RANK_PRIOR_CLOSE_LOOKBACK_CALENDAR_DAYS),
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
    split_minutes = client.bars_batched(
        symbols,
        batch_size=asset_batch_size,
        timeframe=RANK_MINUTE_TIMEFRAME,
        start=feature_start,
        end=cutoff,
        feed=RANK_HISTORICAL_FEED,
        adjustment=NORMALIZED_RANK_MINUTE_ADJUSTMENT,
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
    return previous, split_minutes


def verify_reconstructed_market_candidates(
    source_candidate_rows: list[dict[str, object]],
    reconstructed: DiscoveryResult,
) -> None:
    source = {
        str(row.get("symbol") or ""): (
            str(row.get("first_market_qualified_bar_started_at") or ""),
            str(row.get("first_market_qualified_at") or ""),
            float(row.get("previous_close") or 0),
        )
        for row in source_candidate_rows
    }
    if "" in source or len(source) != len(source_candidate_rows):
        raise ValueError("source market candidates are incomplete or repeated")
    rebuilt: dict[str, tuple[str, str, float]] = {}
    for row in reconstructed.rows:
        if row.first_market_qualified_at is None:
            continue
        if row.first_market_qualified_bar_started_at is None or row.symbol in rebuilt:
            raise ValueError("reconstructed market candidate timing is invalid")
        rebuilt[row.symbol] = (
            row.first_market_qualified_bar_started_at,
            row.first_market_qualified_at,
            float(row.previous_close),
        )
    if set(rebuilt) != set(source):
        raise ValueError("reconstructed market candidate set mismatch")
    for symbol, expected in source.items():
        observed = rebuilt[symbol]
        if observed[:2] != expected[:2] or not math.isclose(
            observed[2], expected[2], rel_tol=1e-12, abs_tol=1e-12
        ):
            raise ValueError(f"reconstructed market candidate mismatch for {symbol}")
    if reconstructed.market_candidate_count != len(source):
        raise ValueError("reconstructed market candidate count mismatch")
    if set(reconstructed.minutes) != set(source) or set(reconstructed.rvol_curves) != set(
        source
    ):
        raise ValueError("reconstructed candidate minute/RVOL coverage mismatch")


def validate_candidate_previous_closes(
    *,
    candidate_rows: list[dict[str, object]],
    split_previous_closes: Mapping[str, float],
) -> None:
    for row in candidate_rows:
        symbol = str(row.get("symbol") or "")
        try:
            source = float(row["previous_close"])
            rank = float(split_previous_closes[symbol])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"candidate split previous close is missing for {symbol}") from None
        if (
            not math.isfinite(source)
            or source <= 0
            or not math.isfinite(rank)
            or rank <= 0
            or not math.isclose(
                source,
                rank,
                rel_tol=CANDIDATE_VALUE_REL_TOL,
                abs_tol=CANDIDATE_VALUE_ABS_TOL,
            )
        ):
            raise ValueError(f"candidate split previous close mismatch for {symbol}")


def expected_upstream_source_hashes(
    *,
    membership_payload: Mapping[str, object],
    candidate_payload: Mapping[str, object],
    market_date_manifest: Mapping[str, object],
    float_date_manifest: Mapping[str, object],
    news_events: list[dict[str, object]],
    news_statuses: list[dict[str, object]],
    news_date_manifest: Mapping[str, object],
) -> dict[str, str]:
    return {
        "identity_resolved_membership": str(
            membership_payload["summary"]["membership_sha256"]  # type: ignore[index]
        ),
        "market_candidates": str(candidate_payload["content_sha256"]),
        "market_discovery_manifest": json_fingerprint(market_date_manifest),
        "causal_float_records": str(
            float_date_manifest["summary"]["records_sha256"]  # type: ignore[index]
        ),
        "causal_float_manifest": json_fingerprint(float_date_manifest),
        "publication_timed_news_events": json_fingerprint(news_events),
        "publication_timed_news_statuses": json_fingerprint(news_statuses),
        "publication_timed_news_manifest": json_fingerprint(news_date_manifest),
    }


def validate_loaded_source_lineage(
    *,
    source_inputs: object,
    source_manifest: Mapping[str, object],
    expected_upstream_hashes: Mapping[str, str],
) -> None:
    summary = source_manifest.get("summary")
    if not isinstance(summary, Mapping):
        raise ValueError("canonical source-input summary is missing")
    logical_sha = summary.get("logical_records_sha256")
    expected = {
        **dict(expected_upstream_hashes),
        "reacquired_market_inputs": str(logical_sha or ""),
    }
    if source_manifest.get("source_hashes") != expected or getattr(
        source_inputs, "source_hashes", None
    ) != expected:
        raise ValueError("canonical source-input per-date lineage mismatch")


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required at {path}")
    return payload


def _root_date_manifest(root: dict[str, object], trading_date: str) -> dict[str, object]:
    rows = root.get("date_manifests")
    if not isinstance(rows, list):
        raise ValueError("source root lacks date manifests")
    matches = [
        row
        for row in rows
        if isinstance(row, dict) and row.get("trading_date") == trading_date
    ]
    if len(matches) != 1:
        raise ValueError(f"source root date manifest mismatch for {trading_date}")
    return matches[0]


def _validate_market_root(manifest: dict[str, object]) -> None:
    if manifest.get("artifact_id") != FIXED_MARKET_DISCOVERY_ID:
        raise ValueError("scanner requires market discovery v0.3")
    if manifest.get("discovery_policy") != causal_market_discovery_v0_3_manifest():
        raise ValueError("scanner market discovery policy mismatch")
    if manifest.get("acquisition_profile_union") != historical_profile_union_v0_1_manifest():
        raise ValueError("scanner market root lacks the profile union")
    projection = {
        "discovery_policy": manifest.get("discovery_policy"),
        "source_membership_bundle_sha256": manifest.get(
            "source_membership_bundle_sha256"
        ),
        "date_manifests": manifest.get("date_manifests"),
    }
    if manifest.get("content_sha256") != json_fingerprint(projection):
        raise ValueError("scanner market root fingerprint mismatch")


def _validate_news_root(
    manifest: dict[str, object],
    *,
    market_sha: str,
    float_sha: str,
) -> None:
    if manifest.get("artifact_id") != FIXED_NEWS_POLICY_ID:
        raise ValueError("scanner requires causal news v0.2")
    if manifest.get("news_policy") != causal_news_v0_2_manifest() or manifest.get(
        "temporal_boundary"
    ) != causal_news_v0_2_temporal_boundary():
        raise ValueError("scanner causal news policy mismatch")
    if manifest.get("acquisition_profile_union") != historical_profile_union_v0_1_manifest():
        raise ValueError("scanner news root lacks the profile union")
    if manifest.get("source_market_discovery_bundle_sha256") != market_sha:
        raise ValueError("scanner news root market lineage mismatch")
    if manifest.get("source_float_bundle_sha256") != float_sha:
        raise ValueError("scanner news root float lineage mismatch")
    projection = {
        "news_policy": manifest.get("news_policy"),
        "temporal_boundary": manifest.get("temporal_boundary"),
        "source_market_discovery_bundle_sha256": market_sha,
        "source_float_bundle_sha256": float_sha,
        "date_manifests": manifest.get("date_manifests"),
    }
    if manifest.get("content_sha256") != json_fingerprint(projection):
        raise ValueError("scanner news root fingerprint mismatch")


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
    target_basis_sha256: str,
) -> None:
    _validate_market_root(market_root_manifest)
    _validate_news_root(
        news_root_manifest,
        market_sha=str(market_root_manifest["content_sha256"]),
        float_sha=str(float_root_manifest["content_sha256"]),
    )
    if membership_payload.get("trading_date") != trading_date or membership_payload.get(
        "artifact_id"
    ) != IDENTITY_RESOLVED_UNIVERSE_POLICY_ID:
        raise ValueError("scanner membership payload mismatch")
    if candidate_payload.get("trading_date") != trading_date or candidate_payload.get(
        "artifact_id"
    ) != CAUSAL_MARKET_CANDIDATES_V0_3_ARTIFACT_ID:
        raise ValueError("scanner market candidate payload mismatch")
    if market_date_manifest != _root_date_manifest(
        market_root_manifest, trading_date
    ) or news_date_manifest != _root_date_manifest(news_root_manifest, trading_date):
        raise ValueError("scanner date manifest differs from its root")
    if market_date_manifest.get("strategy_profile") != strategy_profile_manifest(profile):
        raise ValueError("scanner market date profile mismatch")
    union = historical_profile_union_v0_1_manifest()
    if market_date_manifest.get("acquisition_profile_union") != union or news_date_manifest.get(
        "acquisition_profile_union"
    ) != union:
        raise ValueError("scanner date profile-union lineage mismatch")

    membership_sha = membership_payload.get("summary", {}).get("membership_sha256")
    membership_root_sha = membership_root_manifest.get("content_sha256")
    market_root_sha = market_root_manifest.get("content_sha256")
    float_root_sha = float_root_manifest.get("content_sha256")
    if market_root_manifest.get("source_membership_bundle_sha256") != membership_root_sha:
        raise ValueError("scanner market root membership lineage mismatch")
    market_membership = market_date_manifest.get("source_membership", {})
    if market_membership.get("membership_sha256") != membership_sha or market_membership.get(
        "membership_bundle_sha256"
    ) != membership_root_sha or market_membership.get(
        "membership_payload_sha256"
    ) != json_fingerprint(membership_payload):
        raise ValueError("scanner market date membership lineage mismatch")
    if float_root_manifest.get("source_market_discovery_bundle_sha256") != market_root_sha:
        raise ValueError("scanner float root market lineage mismatch")
    if news_root_manifest.get("source_float_bundle_sha256") != float_root_sha:
        raise ValueError("scanner news root float lineage mismatch")

    market_date_sha = json_fingerprint(market_date_manifest)
    candidate_sha = candidate_payload.get("content_sha256")
    if market_date_manifest.get("summary", {}).get(
        "causal_market_candidate_set_sha256"
    ) != candidate_sha:
        raise ValueError("scanner market candidate hash mismatch")
    if float_date_manifest.get("source_market_candidates_sha256") != candidate_sha or float_date_manifest.get(
        "source_market_discovery_manifest_sha256"
    ) != market_date_sha:
        raise ValueError("scanner float date lineage mismatch")
    if float_date_manifest.get("source_float_target_basis_sha256") != (
        target_basis_sha256
    ):
        raise ValueError("scanner float qualification-minute basis lineage mismatch")
    float_commitments = float_root_manifest.get("date_manifests")
    if not isinstance(float_commitments, list):
        raise ValueError("scanner float root commitments are missing")
    commitments = [
        item
        for item in float_commitments
        if isinstance(item, dict) and item.get("trading_date") == trading_date
    ]
    if len(commitments) != 1 or commitments[0].get(
        "manifest_content_sha256"
    ) != float_date_manifest.get("content_sha256"):
        raise ValueError("scanner float date commitment mismatch")
    records_sha = float_date_manifest.get("summary", {}).get("records_sha256")
    if news_date_manifest.get("source_market_candidates_sha256") != candidate_sha or news_date_manifest.get(
        "source_market_discovery_manifest_sha256"
    ) != market_date_sha or news_date_manifest.get(
        "source_float_records_sha256"
    ) != records_sha or news_date_manifest.get(
        "source_float_manifest_sha256"
    ) != float_date_manifest.get("content_sha256") or news_date_manifest.get(
        "source_float_target_basis_sha256"
    ) != target_basis_sha256:
        raise ValueError("scanner news date lineage mismatch")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase",
        choices=("acquire-source-inputs", "freeze-snapshots"),
        required=True,
    )
    parser.add_argument("--census-root", type=Path, required=True)
    parser.add_argument("--dates", nargs="+")
    parser.add_argument("--asset-batch-size", type=int, default=250)
    parser.add_argument("--max-candidates-per-date", type=int, default=100)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-input-output", type=Path)
    args = parser.parse_args(argv)

    # No independent gain/policy/artifact switches exist on this entry point.
    validate_fixed_scanner_mode()
    if args.asset_batch_size <= 0:
        raise ValueError("asset batch size must be positive")
    if args.max_candidates_per_date <= 0:
        raise ValueError("candidate ceiling must be positive")

    membership_root = args.census_root / IDENTITY_RESOLVED_UNIVERSE_POLICY_ID
    market_root = args.census_root / FIXED_MARKET_DISCOVERY_ID
    float_root = args.census_root / FIXED_FLOAT_POLICY_ID
    news_root = args.census_root / FIXED_NEWS_POLICY_ID
    market_manifest = _load_json(market_root / "manifest.json")
    _validate_market_root(market_manifest)
    dates = args.dates or market_manifest.get("dates")
    if not isinstance(dates, list) or not dates:
        raise ValueError("at least one scanner date is required")
    if dates != sorted(set(dates)):
        raise ValueError("scanner dates must be unique and ordered")
    for value in dates:
        date.fromisoformat(value)
    market_dates = market_manifest.get("dates")
    if not isinstance(market_dates, list) or not set(dates).issubset(market_dates):
        raise ValueError("scanner dates are absent from the market bundle")
    float_manifest = load_causal_float_root(
        float_root,
        expected_source_market_discovery_bundle_sha256=str(
            market_manifest["content_sha256"]
        ),
    )
    if not set(dates).issubset(float_manifest["dates"]):
        raise ValueError("scanner dates are absent from the float bundle")
    news_manifest = _load_json(news_root / "manifest.json")
    _validate_news_root(
        news_manifest,
        market_sha=str(market_manifest["content_sha256"]),
        float_sha=str(float_manifest["content_sha256"]),
    )
    if not isinstance(news_manifest.get("dates"), list) or not set(dates).issubset(
        news_manifest["dates"]
    ):
        raise ValueError("scanner dates are absent from the news bundle")

    profile = historical_profile_union_v0_1()
    union_manifest = historical_profile_union_v0_1_manifest()
    prepared: list[tuple[object, ...]] = []
    # Deep-load all upstream sources before constructing the provider client.
    for value in dates:
        membership_rows, membership_payload, membership_manifest = (
            load_identity_resolved_universe(membership_root, trading_date=value)
        )
        candidate_rows, candidate_payload, market_date_manifest = (
            load_market_candidate_payload(market_root / value)
        )
        if len(candidate_rows) > args.max_candidates_per_date:
            raise RuntimeError(
                f"{value} candidate count exceeds the frozen acquisition ceiling"
            )
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
        target_basis_sha = str(target_basis_payload["content_sha256"])
        float_records, float_date_manifest = load_causal_float_records(
            float_root / value,
            candidate_rows=candidate_rows,
            candidate_payload=candidate_payload,
            expected_trading_date=value,
            expected_source_market_discovery_manifest_sha256=market_date_sha,
            expected_source_float_target_basis_sha256=target_basis_sha,
        )
        float_records_sha = str(float_date_manifest["summary"]["records_sha256"])
        news_events, news_statuses, news_date_manifest = load_publication_timed_news(
            news_root / value,
            candidate_rows=candidate_rows,
            candidate_payload=candidate_payload,
            source_float_records_sha256=float_records_sha,
        )
        validate_cross_artifact_lineage(
            trading_date=value,
            profile=profile,
            membership_root_manifest=membership_manifest,
            market_root_manifest=market_manifest,
            float_root_manifest=float_manifest,
            news_root_manifest=news_manifest,
            membership_payload=membership_payload,
            candidate_payload=candidate_payload,
            market_date_manifest=market_date_manifest,
            float_date_manifest=float_date_manifest,
            news_date_manifest=news_date_manifest,
            target_basis_sha256=target_basis_sha,
        )
        prepared.append(
            (
                value,
                membership_rows,
                membership_payload,
                membership_manifest,
                candidate_rows,
                candidate_payload,
                market_date_manifest,
                float_records,
                float_date_manifest,
                news_events,
                news_statuses,
                news_date_manifest,
            )
        )

    source_input_root = (
        args.source_input_output
        or args.census_root / FIXED_SOURCE_INPUT_ARTIFACT_ID
    )
    source_bundle_hashes = {
        "membership": str(prepared[0][3]["content_sha256"]),
        "market": str(market_manifest["content_sha256"]),
        "float": str(float_manifest["content_sha256"]),
        "news": str(news_manifest["content_sha256"]),
    }
    if len(
        {str(item[3]["content_sha256"]) for item in prepared}
    ) != 1:
        raise ValueError("scanner dates do not share one membership root")

    if args.phase == "acquire-source-inputs":
        if args.output is not None:
            raise ValueError("scanner output is invalid during source-input acquisition")
        source_input_root.mkdir(parents=True, exist_ok=False)
        client = AlpacaDataClient.from_env()
        source_input_manifests: list[dict[str, object]] = []
        for item in prepared:
            (
                value,
                membership_rows,
                membership_payload,
                _membership_manifest,
                candidate_rows,
                candidate_payload,
                market_date_manifest,
                _float_records,
                float_date_manifest,
                _news_events,
                _news_statuses,
                news_date_manifest,
            ) = item
            trading_date = date.fromisoformat(str(value))
            assets = identity_membership_as_acquisition_assets(membership_rows)
            reconstructed = discover_market_day(
                client,
                trading_date=trading_date,
                profile=profile,
                asset_batch_size=args.asset_batch_size,
                assets=assets,
                gain_basis=FIXED_GAIN_BASIS,
            )
            verify_reconstructed_market_candidates(candidate_rows, reconstructed)
            membership_symbols = sorted(
                str(row["ticker"]) for row in membership_rows
            )
            previous, rank_frames = reacquire_split_rank_market_inputs(
                client,
                trading_date=trading_date,
                membership_symbols=membership_symbols,
                profile=profile,
                asset_batch_size=args.asset_batch_size,
            )
            rank_frames = {
                symbol: trim_scanner_bar_frame(
                    frame,
                    trading_date=trading_date,
                    start=profile.volume_feature_start,
                    cutoff=profile.no_new_entries_after,
                    label=f"split rank bars for {symbol}",
                ).loc[:, ["close"]]
                for symbol, frame in rank_frames.items()
            }
            candidate_frames = {
                symbol: trim_scanner_bar_frame(
                    frame,
                    trading_date=trading_date,
                    start=profile.volume_feature_start,
                    cutoff=profile.no_new_entries_after,
                    acquisition_end=UPSTREAM_MARKET_ACQUISITION_TAIL_END,
                    label=f"raw candidate bars for {symbol}",
                ).loc[:, ["close", "volume"]]
                for symbol, frame in reconstructed.minutes.items()
            }
            candidate_rvol = {
                symbol: trim_scanner_rvol_series(
                    series,
                    trading_date=trading_date,
                    start=profile.volume_feature_start,
                    cutoff=profile.no_new_entries_after,
                    acquisition_end=UPSTREAM_MARKET_ACQUISITION_TAIL_END,
                    label=f"candidate RVOL for {symbol}",
                )
                for symbol, series in reconstructed.rvol_curves.items()
            }
            validate_candidate_previous_closes(
                candidate_rows=candidate_rows,
                split_previous_closes=previous,
            )
            source_hashes = expected_upstream_source_hashes(
                membership_payload=membership_payload,
                candidate_payload=candidate_payload,
                market_date_manifest=market_date_manifest,
                float_date_manifest=float_date_manifest,
                news_events=_news_events,
                news_statuses=_news_statuses,
                news_date_manifest=news_date_manifest,
            )
            source_manifest = write_scanner_source_input_bundle(
                source_input_root / str(value),
                trading_date=trading_date,
                profile=profile,
                membership_symbols=membership_symbols,
                candidate_symbols=[str(row["symbol"]) for row in candidate_rows],
                previous_close_by_symbol=previous,
                rank_split_minute_bars_by_symbol=rank_frames,
                candidate_raw_minute_bars_by_symbol=candidate_frames,
                candidate_exact_rvol_by_symbol=candidate_rvol,
                upstream_source_hashes=source_hashes,
            )
            source_manifest["acquisition_profile_union"] = union_manifest
            source_manifest["strategy_profiles_modified"] = False
            _rehash(source_manifest)
            _write_json(
                source_input_root / str(value) / "manifest.json",
                source_manifest,
            )
            source_input_manifests.append(source_manifest)

        source_root_manifest = build_scanner_source_input_root_manifest(
            date_manifests=source_input_manifests,
            source_bundle_hashes=source_bundle_hashes,
        )
        source_root_manifest["acquisition_profile_union"] = union_manifest
        source_root_manifest["strategy_profiles_modified"] = False
        _rehash(source_root_manifest)
        validate_scanner_source_input_root_manifest(source_root_manifest)
        _write_json(source_input_root / "manifest.json", source_root_manifest)
        print(
            json.dumps(
                {
                    "phase": args.phase,
                    "artifact_id": FIXED_SOURCE_INPUT_ARTIFACT_ID,
                    "acquisition_profile_union_id": FIXED_ACQUISITION_PROFILE_ID,
                    "dates": dates,
                    "all_source_inputs_frozen_before_scanner_validation": True,
                    "content_sha256": source_root_manifest["content_sha256"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    source_root_manifest = _load_json(source_input_root / "manifest.json")
    validate_scanner_source_input_root_manifest(source_root_manifest)
    if (
        source_root_manifest.get("dates") != dates
        or source_root_manifest.get("source_bundle_hashes")
        != dict(sorted(source_bundle_hashes.items()))
        or source_root_manifest.get("acquisition_profile_union") != union_manifest
        or source_root_manifest.get("strategy_profiles_modified") is not False
    ):
        raise ValueError("freeze phase source-input root lineage mismatch")
    expected_source_manifests = {
        str(row["trading_date"]): row
        for row in source_root_manifest["date_manifests"]
    }
    if set(expected_source_manifests) != set(dates):
        raise ValueError("freeze phase source-input date coverage mismatch")

    # Everything below is provider-free: no Alpaca client is constructed.
    output_root = args.output or args.census_root / FIXED_SCANNER_ARTIFACT_ID
    output_root.mkdir(parents=True, exist_ok=False)
    date_manifests: list[dict[str, object]] = []
    for item in prepared:
        (
            value,
            _membership_rows,
            membership_payload,
            _membership_manifest,
            candidate_rows,
            candidate_payload,
            market_date_manifest,
            float_records,
            float_date_manifest,
            news_events,
            news_statuses,
            news_date_manifest,
        ) = item
        trading_date = date.fromisoformat(str(value))
        loaded_inputs, loaded_source_manifest = load_scanner_source_input_bundle(
            source_input_root / str(value),
            profile=profile,
        )
        if loaded_source_manifest != expected_source_manifests[str(value)]:
            raise ValueError("freeze phase source-input date commitment mismatch")
        validate_loaded_source_lineage(
            source_inputs=loaded_inputs,
            source_manifest=loaded_source_manifest,
            expected_upstream_hashes=expected_upstream_source_hashes(
                membership_payload=membership_payload,
                candidate_payload=candidate_payload,
                market_date_manifest=market_date_manifest,
                float_date_manifest=float_date_manifest,
                news_events=news_events,
                news_statuses=news_statuses,
                news_date_manifest=news_date_manifest,
            ),
        )
        replayed_rows = build_scanner_snapshot_rows(
            trading_date=trading_date,
            profile=profile,
            candidate_rows=candidate_rows,
            float_records=float_records,
            news_events=news_events,
            news_statuses=news_statuses,
            membership_symbols=loaded_inputs.membership_symbols,
            previous_close_by_symbol=loaded_inputs.previous_close_by_symbol,
            rank_split_minute_bars_by_symbol=(
                loaded_inputs.rank_split_minute_bars_by_symbol
            ),
            candidate_raw_minute_bars_by_symbol=(
                loaded_inputs.candidate_raw_minute_bars_by_symbol
            ),
            candidate_exact_rvol_by_symbol=(
                loaded_inputs.candidate_exact_rvol_by_symbol
            ),
        )
        second_inputs, second_manifest = load_scanner_source_input_bundle(
            source_input_root / str(value),
            profile=profile,
        )
        rebuilt_rows = build_scanner_snapshot_rows(
            trading_date=trading_date,
            profile=profile,
            candidate_rows=candidate_rows,
            float_records=float_records,
            news_events=news_events,
            news_statuses=news_statuses,
            membership_symbols=second_inputs.membership_symbols,
            previous_close_by_symbol=second_inputs.previous_close_by_symbol,
            rank_split_minute_bars_by_symbol=(
                second_inputs.rank_split_minute_bars_by_symbol
            ),
            candidate_raw_minute_bars_by_symbol=(
                second_inputs.candidate_raw_minute_bars_by_symbol
            ),
            candidate_exact_rvol_by_symbol=(
                second_inputs.candidate_exact_rvol_by_symbol
            ),
        )
        if second_manifest != loaded_source_manifest or rebuilt_rows != replayed_rows:
            raise ValueError("provider-free canonical scanner rebuild differs exactly")
        payload, scanner_manifest = build_causal_scanner_snapshot_artifacts(
            trading_date=trading_date,
            profile=profile,
            candidate_rows=candidate_rows,
            membership_symbols=loaded_inputs.membership_symbols,
            rows=replayed_rows,
            source_hashes=loaded_inputs.source_hashes,
            previous_close_by_symbol=loaded_inputs.previous_close_by_symbol,
            rank_split_minute_bars_by_symbol=(
                loaded_inputs.rank_split_minute_bars_by_symbol
            ),
            candidate_raw_minute_bars_by_symbol=(
                loaded_inputs.candidate_raw_minute_bars_by_symbol
            ),
        )
        scanner_manifest["acquisition_profile_union"] = union_manifest
        scanner_manifest["strategy_profiles_modified"] = False
        _rehash(scanner_manifest)
        date_root = output_root / str(value)
        date_root.mkdir()
        _write_json(date_root / "scanner-snapshot.json", payload)
        _write_json(date_root / "manifest.json", scanner_manifest)
        loaded_rows, loaded_payload, loaded_manifest = load_causal_scanner_snapshot(
            date_root,
            candidate_rows=candidate_rows,
            profile=profile,
            source_inputs=loaded_inputs,
        )
        if (
            loaded_rows != replayed_rows
            or loaded_payload != payload
            or loaded_manifest != scanner_manifest
        ):
            raise ValueError("scanner snapshot changes on provider-free reload")
        date_manifests.append(scanner_manifest)

    root_manifest: dict[str, object] = {
        "schema_version": 2,
        "artifact_id": FIXED_SCANNER_ARTIFACT_ID,
        "dates": dates,
        "scanner_policy": causal_scanner_snapshot_v0_3_manifest(),
        "acquisition_profile_union": union_manifest,
        "strategy_profiles_modified": False,
        "source_bundle_hashes": source_bundle_hashes,
        "source_input_bundle_sha256": source_root_manifest["content_sha256"],
        "date_manifests": date_manifests,
        "eligibility": {
            "complete_relative_to_identity_resolved_membership": True,
            "candidate_minute_dispositions_frozen": True,
            "provider_free_replay_exact": True,
            "universe_complete": False,
            "full_walk_forward_eligible": False,
            "policy_promotion_eligible": False,
        },
        "knowledge_policy": {
            "uses_benchmark_labels": False,
            "uses_retrospective_trade_outcomes": False,
            "contains_trades_setups_portfolio_or_pnl": False,
            "general_and_small_strategy_profiles_unchanged": True,
        },
    }
    _rehash(root_manifest)
    _write_json(output_root / "manifest.json", root_manifest)
    print(
        json.dumps(
            {
                "artifact_id": FIXED_SCANNER_ARTIFACT_ID,
                "phase": args.phase,
                "source_input_artifact_id": FIXED_SOURCE_INPUT_ARTIFACT_ID,
                "acquisition_profile_union_id": FIXED_ACQUISITION_PROFILE_ID,
                "dates": dates,
                "provider_free_replay_exact": True,
                "candidate_minute_disposition_counts": {
                    manifest["trading_date"]: manifest["summary"][
                        "candidate_minute_disposition_count"
                    ]
                    for manifest in date_manifests
                },
                "policy_promotion_eligible": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
