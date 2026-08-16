from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pandas as pd


ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class PricePathCriteria:
    trading_date: date
    rejection_level: float
    rejection_tolerance: float
    later_high: float
    later_high_tolerance: float
    coarse_max_high: float
    minimum_volume: int


def _session_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(4, 0), ET).astimezone(timezone.utc)
    end = datetime.combine(day, time(20, 0), ET).astimezone(timezone.utc)
    return start, end


def _window_bounds(day: date) -> tuple[datetime, datetime]:
    prior = day - timedelta(days=4)
    start = datetime.combine(prior, time(4, 0), ET).astimezone(timezone.utc)
    _, end = _session_bounds(day)
    return start, end


def _day_rows(frame: pd.DataFrame, day: date) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise TypeError("bar frame index must be a DatetimeIndex")
    index = frame.index
    if index.tz is None:
        raise ValueError("bar frame timestamps must be timezone-aware")
    local = index.tz_convert(ET)
    clock = local.time
    mask = (
        (local.date == day)
        & (clock >= time(4, 0))
        & (clock < time(20, 0))
    )
    return frame.loc[mask].sort_index()


def _previous_regular_close(frame: pd.DataFrame, day: date) -> float | None:
    if frame.empty:
        return None
    index = frame.index
    if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
        raise ValueError("bar frame timestamps must use a timezone-aware DatetimeIndex")
    local = index.tz_convert(ET)
    eligible_days = sorted({value for value in local.date if value < day}, reverse=True)
    for eligible_day in eligible_days:
        clock = local.time
        mask = (
            (local.date == eligible_day)
            & (clock >= time(9, 30))
            & (clock < time(16, 0))
        )
        rows = frame.loc[mask].sort_index()
        if not rows.empty:
            return float(rows.iloc[-1]["close"])
    return None


def _summary(rows: pd.DataFrame) -> dict[str, Any] | None:
    if rows.empty:
        return None
    return {
        "first_bar_at": rows.index[0].isoformat(),
        "last_bar_at": rows.index[-1].isoformat(),
        "open": float(rows.iloc[0]["open"]),
        "high": float(rows["high"].max()),
        "low": float(rows["low"].min()),
        "close": float(rows.iloc[-1]["close"]),
        "volume": int(rows["volume"].fillna(0).sum()),
        "bar_count": len(rows),
    }


def _coarse_candidate(rows: pd.DataFrame, criteria: PricePathCriteria) -> bool:
    summary = _summary(rows)
    if summary is None:
        return False
    later_floor = criteria.later_high - criteria.later_high_tolerance
    return bool(
        summary["low"] <= criteria.rejection_level + criteria.rejection_tolerance
        and summary["high"] >= later_floor
        and summary["high"] <= criteria.coarse_max_high
        and summary["volume"] >= criteria.minimum_volume
    )


def _rejection_rows(rows: pd.DataFrame, criteria: PricePathCriteria) -> pd.DataFrame:
    if rows.empty:
        return rows.copy()
    lower = criteria.rejection_level - criteria.rejection_tolerance
    upper = criteria.rejection_level + criteria.rejection_tolerance
    body_top = rows[["open", "close"]].max(axis=1)
    upper_wick = rows["high"] - body_top
    candle_range = (rows["high"] - rows["low"]).clip(lower=0.0)
    minimum_wick = pd.concat(
        [
            pd.Series(0.03, index=rows.index),
            candle_range * 0.25,
        ],
        axis=1,
    ).max(axis=1)
    mask = rows["high"].between(lower, upper) & (upper_wick >= minimum_wick)
    return rows.loc[mask]


def _candidate_record(
    symbol: str,
    asset: dict[str, Any],
    frame: pd.DataFrame,
    criteria: PricePathCriteria,
) -> dict[str, Any] | None:
    rows = _day_rows(frame, criteria.trading_date)
    summary = _summary(rows)
    if summary is None:
        return None

    rejection_rows = _rejection_rows(rows, criteria)
    later_floor = criteria.later_high - criteria.later_high_tolerance
    sequence_matches: list[dict[str, Any]] = []
    for timestamp, rejection in rejection_rows.iterrows():
        later = rows.loc[rows.index > timestamp]
        if later.empty:
            continue
        later_max = float(later["high"].max())
        if later_max < later_floor:
            continue
        later_peak_at = later["high"].idxmax()
        sequence_matches.append(
            {
                "rejection_bar_at": timestamp.isoformat(),
                "rejection_open": float(rejection["open"]),
                "rejection_high": float(rejection["high"]),
                "rejection_low": float(rejection["low"]),
                "rejection_close": float(rejection["close"]),
                "later_max_high": later_max,
                "later_peak_at": later_peak_at.isoformat(),
                "later_high_distance": abs(later_max - criteria.later_high),
            }
        )
    sequence_matches.sort(
        key=lambda row: (
            row["later_high_distance"],
            row["rejection_bar_at"],
        )
    )

    previous_close = _previous_regular_close(frame, criteria.trading_date)
    gain_at_high = None
    if previous_close not in (None, 0.0):
        gain_at_high = (summary["high"] / previous_close - 1.0) * 100.0

    best = sequence_matches[0] if sequence_matches else None
    return {
        "symbol": symbol,
        "name": asset.get("name"),
        "exchange": asset.get("exchange"),
        "status": asset.get("status"),
        "tradable": asset.get("tradable"),
        "fractionable": asset.get("fractionable"),
        "previous_regular_close": previous_close,
        "gain_at_session_high_pct": gain_at_high,
        "target_session": summary,
        "rejection_bar_count": len(rejection_rows),
        "ordered_rejection_then_later_high": bool(sequence_matches),
        "best_sequence_match": best,
        "sequence_match_count": len(sequence_matches),
    }


def rank_candidate_records(
    records: Iterable[dict[str, Any]], *, later_high: float = 8.0
) -> list[dict[str, Any]]:
    def rank(record: dict[str, Any]) -> tuple[Any, ...]:
        best = record.get("best_sequence_match") or {}
        later_distance = best.get("later_high_distance", float("inf"))
        high = record["target_session"]["high"]
        volume = record["target_session"]["volume"]
        return (
            not record["ordered_rejection_then_later_high"],
            later_distance,
            abs(high - later_high),
            -volume,
            record["symbol"],
        )

    return sorted(records, key=rank)


def build_candidate_records(
    assets: Iterable[dict[str, Any]],
    bars: dict[str, pd.DataFrame],
    criteria: PricePathCriteria,
) -> list[dict[str, Any]]:
    by_symbol = {
        str(asset.get("symbol", "")).upper(): asset
        for asset in assets
        if asset.get("symbol")
    }
    records = []
    for symbol, frame in bars.items():
        record = _candidate_record(
            symbol,
            by_symbol.get(symbol, {"symbol": symbol}),
            frame,
            criteria,
        )
        if record is not None:
            records.append(record)
    return rank_candidate_records(records, later_high=criteria.later_high)


def main() -> int:
    from momentumbot.providers.alpaca import AlpacaDataClient

    parser = argparse.ArgumentParser(
        description=(
            "Retrospectively audit an unresolved transcript-derived benchmark symbol "
            "against a market-wide historical price path. This program is an evidence "
            "identity tool and its output must never be supplied to strategy runtime."
        )
    )
    parser.add_argument("--trading-date", required=True)
    parser.add_argument("--rejection-level", type=float, required=True)
    parser.add_argument("--rejection-tolerance", type=float, default=0.20)
    parser.add_argument("--later-high", type=float, required=True)
    parser.add_argument("--later-high-tolerance", type=float, default=1.25)
    parser.add_argument("--coarse-max-high", type=float, default=20.0)
    parser.add_argument("--minimum-volume", type=int, default=100_000)
    parser.add_argument("--coarse-timeframe", default="1Hour")
    parser.add_argument("--maximum-candidates", type=int, default=200)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    criteria = PricePathCriteria(
        trading_date=date.fromisoformat(args.trading_date),
        rejection_level=args.rejection_level,
        rejection_tolerance=args.rejection_tolerance,
        later_high=args.later_high,
        later_high_tolerance=args.later_high_tolerance,
        coarse_max_high=args.coarse_max_high,
        minimum_volume=args.minimum_volume,
    )
    if criteria.rejection_tolerance <= 0 or criteria.later_high_tolerance <= 0:
        raise ValueError("price tolerances must be positive")
    if criteria.coarse_max_high < criteria.later_high:
        raise ValueError("coarse maximum high must not be below the later-high label")
    if args.maximum_candidates <= 0:
        raise ValueError("maximum candidates must be positive")

    client = AlpacaDataClient.from_env()
    assets = client.assets()
    symbols = sorted(
        {
            str(asset["symbol"]).upper()
            for asset in assets
            if asset.get("symbol")
        }
    )
    start, end = _window_bounds(criteria.trading_date)
    coarse = client.bars_batched(
        symbols,
        batch_size=200,
        timeframe=args.coarse_timeframe,
        start=start,
        end=end,
        feed="sip",
        adjustment="raw",
        asof=criteria.trading_date,
    )
    coarse_matches: list[tuple[str, dict[str, Any]]] = []
    for symbol, frame in coarse.items():
        rows = _day_rows(frame, criteria.trading_date)
        if not _coarse_candidate(rows, criteria):
            continue
        summary = _summary(rows)
        if summary is not None:
            coarse_matches.append((symbol, summary))
    coarse_matches.sort(
        key=lambda item: (
            abs(item[1]["high"] - criteria.later_high),
            -item[1]["volume"],
            item[0],
        )
    )
    coarse_symbols = [
        symbol for symbol, _ in coarse_matches[: args.maximum_candidates]
    ]

    refined = client.bars_batched(
        coarse_symbols,
        batch_size=100,
        timeframe="1Min",
        start=start,
        end=end,
        feed="sip",
        adjustment="raw",
        asof=criteria.trading_date,
    )
    candidates = build_candidate_records(assets, refined, criteria)
    artifact = {
        "artifact_type": "benchmark_symbol_identity_candidate_audit",
        "schema_version": 1,
        "knowledge_policy": (
            "retrospective_benchmark_identity_audit_only_never_runtime_context"
        ),
        "strategy_feedback": "none",
        "criteria": {
            **asdict(criteria),
            "trading_date": criteria.trading_date.isoformat(),
        },
        "provider": {
            "name": "alpaca",
            "feed": "sip",
            "adjustment": "raw",
            "asof": criteria.trading_date.isoformat(),
        },
        "universe": {
            "asset_master_rows": len(assets),
            "unique_symbols": len(symbols),
            "provider_invalid_symbols": sorted(client.invalid_symbols),
            "coarse_timeframe": args.coarse_timeframe,
            "coarse_candidate_count": len(coarse_matches),
            "coarse_candidates_refined": len(coarse_symbols),
            "refined_candidate_count": len(candidates),
        },
        "candidates": candidates,
        "interpretation_limitations": [
            "Price-path similarity can reject a bad ticker but cannot establish identity by itself.",
            "Share float is not present in the Alpaca asset master and must be verified independently.",
            "Transcript wording or chart/ticker evidence remains required before correcting a benchmark symbol.",
            "The retrospective criteria and candidate list are forbidden inputs to strategy replay or policy tuning.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(artifact, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
