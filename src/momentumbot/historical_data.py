from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import pandas as pd

from .models import StrategyProfile, SymbolContext
from .providers.alpaca import AlpacaDataClient
from .providers.marketaux import MarketAuxClient
from .providers.sec_edgar import FloatEstimate, ParsedCompanyFacts, implied_float_shares, roll_forward_float

ET = ZoneInfo("America/New_York")
_ALLOWED_EXCHANGES = {"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS", "NYSEARCA"}


@dataclass(frozen=True, slots=True)
class DiscoveryRow:
    symbol: str
    status: str
    exchange: str
    previous_close: float
    target_high: float
    max_session_gain_pct: float
    max_session_rvol: float
    average_daily_volume_50: float
    first_nonfloat_qualified_at: str | None
    minute_bars: int


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    asset_count: int
    listed_asset_count: int
    daily_superset_count: int
    nonfloat_candidate_count: int
    rows: tuple[DiscoveryRow, ...]
    minutes: dict[str, pd.DataFrame]
    contexts: dict[str, SymbolContext]


def _local_date(index: pd.DatetimeIndex) -> pd.Index:
    return pd.Index(index.tz_convert(ET).date)


def _bar_for_date(frame: pd.DataFrame, target: date) -> pd.Series | None:
    if frame.empty:
        return None
    mask = _local_date(frame.index) == target
    matches = frame.loc[mask]
    return matches.iloc[-1] if not matches.empty else None


def _previous_bar(frame: pd.DataFrame, target: date) -> pd.Series | None:
    if frame.empty:
        return None
    local_dates = _local_date(frame.index)
    matches = frame.loc[local_dates < target]
    return matches.iloc[-1] if not matches.empty else None


def _average_volume_before(frame: pd.DataFrame, target: date, sessions: int = 50) -> float | None:
    if frame.empty:
        return None
    local_dates = _local_date(frame.index)
    values = pd.to_numeric(frame.loc[local_dates < target, "volume"], errors="coerce").dropna().tail(sessions)
    if len(values) < sessions:
        return None
    average = float(values.mean())
    return average if average > 0 else None


def _session_bounds(target: date) -> tuple[datetime, datetime]:
    start = datetime.combine(target, time(7, 0), ET)
    end = datetime.combine(target, time(10, 1), ET)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _daily_window(target: date, lookback_days: int) -> tuple[datetime, datetime]:
    start = datetime.combine(target - timedelta(days=lookback_days), time(0, 0), timezone.utc)
    end = datetime.combine(target + timedelta(days=1), time(0, 0), timezone.utc)
    return start, end


def discover_market_day(
    alpaca: AlpacaDataClient,
    *,
    trading_date: date,
    profile: StrategyProfile,
    asset_batch_size: int = 250,
) -> DiscoveryResult:
    assets = alpaca.assets()
    listed = [
        row
        for row in assets
        if str(row.get("exchange", "")).upper() in _ALLOWED_EXCHANGES
        and str(row.get("symbol", "")).strip()
    ]
    symbols = sorted({str(row["symbol"]).upper() for row in listed})
    asset_meta = {str(row["symbol"]).upper(): row for row in listed}

    coarse_start, coarse_end = _daily_window(trading_date, 8)
    coarse = alpaca.bars_batched(
        symbols,
        batch_size=asset_batch_size,
        timeframe="1Day",
        start=coarse_start,
        end=coarse_end,
        feed="sip",
        adjustment="raw",
        asof=trading_date,
    )
    superset: list[str] = []
    previous_close: dict[str, float] = {}
    target_high: dict[str, float] = {}
    for symbol, frame in coarse.items():
        target_bar = _bar_for_date(frame, trading_date)
        prior_bar = _previous_bar(frame, trading_date)
        if target_bar is None or prior_bar is None:
            continue
        prior_close = float(prior_bar["close"])
        high = float(target_bar["high"])
        low = float(target_bar["low"])
        if prior_close <= 0:
            continue
        gain_at_high = (high / prior_close - 1.0) * 100.0
        price_intersects = high >= profile.min_price and low <= profile.max_price
        if gain_at_high >= profile.min_percent_gain and price_intersects:
            superset.append(symbol)
            previous_close[symbol] = prior_close
            target_high[symbol] = high

    history_start, history_end = _daily_window(trading_date, 120)
    history = alpaca.bars_batched(
        superset,
        batch_size=asset_batch_size,
        timeframe="1Day",
        start=history_start,
        end=history_end,
        feed="sip",
        adjustment="raw",
        asof=trading_date,
    )
    session_start, session_end = _session_bounds(trading_date)
    minutes = alpaca.bars_batched(
        superset,
        batch_size=max(20, min(asset_batch_size, 100)),
        timeframe="1Min",
        start=session_start,
        end=session_end,
        feed="sip",
        adjustment="raw",
        asof=trading_date,
    )

    rows: list[DiscoveryRow] = []
    contexts: dict[str, SymbolContext] = {}
    qualified_minutes: dict[str, pd.DataFrame] = {}
    for symbol in superset:
        average = _average_volume_before(history.get(symbol, pd.DataFrame()), trading_date)
        frame = minutes.get(symbol, pd.DataFrame())
        if average is None or frame.empty:
            continue
        cumulative = pd.to_numeric(frame["volume"], errors="coerce").fillna(0).cumsum()
        gain = (pd.to_numeric(frame["close"], errors="coerce") / previous_close[symbol] - 1.0) * 100.0
        rvol = cumulative / average
        prices = pd.to_numeric(frame["close"], errors="coerce")
        mask = (
            (gain >= profile.min_percent_gain)
            & (rvol >= profile.min_relative_volume)
            & (prices >= profile.min_price)
            & (prices <= profile.max_price)
        )
        first = frame.index[mask][0].isoformat() if mask.any() else None
        meta = asset_meta.get(symbol, {})
        rows.append(
            DiscoveryRow(
                symbol=symbol,
                status=str(meta.get("status", "")),
                exchange=str(meta.get("exchange", "")),
                previous_close=previous_close[symbol],
                target_high=target_high[symbol],
                max_session_gain_pct=float(gain.max()),
                max_session_rvol=float(rvol.max()),
                average_daily_volume_50=average,
                first_nonfloat_qualified_at=first,
                minute_bars=len(frame),
            )
        )
        contexts[symbol] = SymbolContext(
            symbol=symbol,
            previous_close=previous_close[symbol],
            average_daily_volume_50=average,
            float_shares=None,
            float_asof=None,
        )
        if first:
            qualified_minutes[symbol] = frame

    rows.sort(key=lambda row: (row.first_nonfloat_qualified_at is not None, row.max_session_gain_pct), reverse=True)
    return DiscoveryResult(
        asset_count=len(assets),
        listed_asset_count=len(symbols),
        daily_superset_count=len(superset),
        nonfloat_candidate_count=sum(row.first_nonfloat_qualified_at is not None for row in rows),
        rows=tuple(rows),
        minutes=qualified_minutes,
        contexts=contexts,
    )


def estimate_float_from_facts(
    facts: ParsedCompanyFacts,
    *,
    as_of: datetime,
    price_lookup: Callable[[date], float],
) -> FloatEstimate | None:
    eligible_public = [item for item in facts.public_float if item.available_at <= as_of]
    if not eligible_public:
        return None
    public = max(eligible_public, key=lambda item: (item.available_at, item.measure_date))
    anchor = implied_float_shares(public, price_lookup(public.measure_date))
    eligible_outstanding = [item for item in facts.outstanding_shares if item.available_at <= as_of]
    if not eligible_outstanding:
        return anchor
    anchor_outstanding = min(
        eligible_outstanding,
        key=lambda item: (abs((item.measure_date - public.measure_date).days), item.available_at),
    )
    current = max(eligible_outstanding, key=lambda item: (item.available_at, item.measure_date))
    if current.shares <= anchor_outstanding.shares:
        return anchor
    return roll_forward_float(
        anchor,
        anchor_outstanding=anchor_outstanding,
        current_outstanding=current,
    )


def write_discovery(result: DiscoveryResult, root: Path, *, trading_date: date) -> None:
    root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([asdict(row) for row in result.rows]).to_csv(root / "discovery.csv", index=False)
    manifest = {
        "schema_version": 1,
        "kind": "market_day_discovery",
        "trading_date": trading_date.isoformat(),
        "asset_count": result.asset_count,
        "listed_asset_count": result.listed_asset_count,
        "daily_superset_count": result.daily_superset_count,
        "nonfloat_candidate_count": result.nonfloat_candidate_count,
        "universe_complete": False,
        "acquisition_prefilter_uses_full_day_high": True,
        "prefilter_is_not_available_to_strategy": True,
        "bar_adjustment": "raw",
        "notes": [
            "This artifact is a discovery/superset dataset, not yet a runnable complete snapshot.",
            "Float and news are intentionally absent from cross-sectional discovery.",
        ],
    }
    (root / "manifest.json").write_text(pd.Series(manifest).to_json(indent=2) + "\n", encoding="utf-8")


def write_reference_case(
    *,
    root: Path,
    symbol: str,
    trading_date: date,
    bars: pd.DataFrame,
    context: SymbolContext,
    news_rows: list[dict],
    float_estimate: FloatEstimate | None = None,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    bars_dir = root / "bars"
    bars_dir.mkdir(exist_ok=True)
    bars.reset_index().to_csv(bars_dir / f"{symbol}.csv", index=False)
    context_row = {
        "symbol": symbol,
        "previous_close": context.previous_close,
        "average_daily_volume_50": context.average_daily_volume_50,
        "float_shares": float_estimate.value_shares if float_estimate else None,
        "float_asof": float_estimate.available_at.isoformat() if float_estimate else None,
        "float_measure_date": float_estimate.measure_date.isoformat() if float_estimate else None,
        "float_method": float_estimate.method if float_estimate else None,
        "float_source_accession": float_estimate.source_accession if float_estimate else None,
    }
    pd.DataFrame([context_row]).to_csv(root / "contexts.csv", index=False)
    normalized_news = []
    for row in news_rows:
        published = row.get("published_at")
        if not published:
            continue
        normalized_news.append(
            {
                "symbol": symbol,
                "published_at": published,
                "headline_id": row.get("uuid") or row.get("url") or row.get("title"),
                "title": row.get("title"),
                "source": row.get("source"),
            }
        )
    pd.DataFrame(normalized_news).to_csv(root / "news.csv", index=False)
    manifest = {
        "schema_version": 1,
        "kind": "reference_case",
        "trading_date": trading_date.isoformat(),
        "symbol": symbol,
        "universe_complete": False,
        "runnable_backtest": False,
        "bar_adjustment": "raw",
        "float_complete": float_estimate is not None,
        "news_count": len(normalized_news),
    }
    import json
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
