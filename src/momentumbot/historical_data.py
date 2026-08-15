from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import pandas as pd

from .models import StrategyProfile, SymbolContext
from .providers.alpaca import AlpacaDataClient
from .providers.sec_edgar import (
    FloatEstimate,
    ParsedCompanyFacts,
    implied_float_shares,
    roll_forward_float,
)
from .rvol import RvolCurve, coarse_rvol_upper_bound, prior_session_dates, same_time_rvol

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
    max_session_rvol_upper_bound: float | None
    max_session_rvol: float | None
    rvol_history_sessions: int
    average_daily_volume_50: float
    first_market_qualified_at: str | None
    minute_bars: int


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    asset_count: int
    listed_asset_count: int
    daily_superset_count: int
    rvol_prefilter_count: int
    market_candidate_count: int
    rows: tuple[DiscoveryRow, ...]
    minutes: dict[str, pd.DataFrame]
    contexts: dict[str, SymbolContext]
    rvol_curves: dict[str, pd.Series]


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


def _daily_scan_basis(
    raw_frame: pd.DataFrame,
    split_frame: pd.DataFrame,
    target: date,
) -> tuple[float, float, float] | None:
    """Return split-consistent prior close plus raw target high/low.

    A reverse split can make a raw previous close incomparable with the target
    session's raw price. Alpaca's split-adjusted series puts the prior close on
    the target/as-of share basis, while the target day's raw high/low preserve
    the actual prices that traders saw. This keeps corporate actions from being
    misclassified as percentage-gap momentum.
    """
    target_bar = _bar_for_date(raw_frame, target)
    prior_bar = _previous_bar(split_frame, target)
    if target_bar is None or prior_bar is None:
        return None
    prior_close = float(prior_bar["close"])
    high = float(target_bar["high"])
    low = float(target_bar["low"])
    if prior_close <= 0:
        return None
    return prior_close, high, low


def _average_volume_before(
    frame: pd.DataFrame,
    target: date,
    sessions: int = 50,
) -> float | None:
    if frame.empty:
        return None
    local_dates = _local_date(frame.index)
    values = (
        pd.to_numeric(frame.loc[local_dates < target, "volume"], errors="coerce")
        .dropna()
        .tail(sessions)
    )
    if len(values) < sessions:
        return None
    average = float(values.mean())
    return average if average > 0 else None


def _feature_bounds(target: date, profile: StrategyProfile) -> tuple[datetime, datetime]:
    start = datetime.combine(target, profile.volume_feature_start, ET)
    end = datetime.combine(target, time(10, 1), ET)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _daily_window(target: date, lookback_days: int) -> tuple[datetime, datetime]:
    start = datetime.combine(
        target - timedelta(days=lookback_days),
        time(0, 0),
        timezone.utc,
    )
    end = datetime.combine(target + timedelta(days=1), time(0, 0), timezone.utc)
    return start, end


def _history_window(target: date, profile: StrategyProfile) -> tuple[datetime, datetime]:
    # 120 calendar days safely covers 50 trading sessions under ordinary closures.
    days = max(120, int(profile.rvol_lookback_sessions * 2.2))
    start = datetime.combine(target - timedelta(days=days), time(0, 0), timezone.utc)
    _, end = _feature_bounds(target, profile)
    return start, end


def _scan_values(
    frame: pd.DataFrame,
    *,
    previous_close: float,
    rvol_curve: pd.Series,
    profile: StrategyProfile,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    if frame.empty:
        empty = pd.Series(dtype=float)
        return empty, empty, empty, pd.Series(dtype=bool)
    prices = pd.to_numeric(frame["close"], errors="coerce")
    gain = (prices / previous_close - 1.0) * 100.0
    rvol = rvol_curve.reindex(frame.index)
    local_times = frame.index.tz_convert(ET).time
    in_scan_window = pd.Series(
        [profile.session_start <= value < profile.no_new_entries_after for value in local_times],
        index=frame.index,
    )
    mask = (
        in_scan_window
        & (gain >= profile.min_percent_gain)
        & (rvol >= profile.min_relative_volume)
        & (prices >= profile.min_price)
        & (prices <= profile.max_price)
    )
    return prices, gain, rvol, mask


def discover_market_day(
    alpaca: AlpacaDataClient,
    *,
    trading_date: date,
    profile: StrategyProfile,
    asset_batch_size: int = 250,
) -> DiscoveryResult:
    """Build a causal market-day acquisition set with exact time-of-day RVOL.

    The full-day daily high is used only as a *superset acquisition filter* so we
    avoid downloading intraday history for tens of thousands of securities. It
    never enters the strategy. A conservative 15-minute historical RVOL upper
    bound then narrows the set before exact one-minute, same-time-of-day RVOL is
    downloaded/calculated for the survivors.

    Percentage-gain comparisons use a split-adjusted previous-session close on
    the trading-date share basis. Execution/price-range checks still use raw
    target-session prices. This prevents a split itself from masquerading as a
    momentum gap while retaining genuine post-split price action.
    """
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
    coarse_raw = alpaca.bars_batched(
        symbols,
        batch_size=asset_batch_size,
        timeframe="1Day",
        start=coarse_start,
        end=coarse_end,
        feed="sip",
        adjustment="raw",
        asof=trading_date,
    )
    coarse_split = alpaca.bars_batched(
        symbols,
        batch_size=asset_batch_size,
        timeframe="1Day",
        start=coarse_start,
        end=coarse_end,
        feed="sip",
        adjustment="split",
        asof=trading_date,
    )
    superset: list[str] = []
    previous_close: dict[str, float] = {}
    target_high: dict[str, float] = {}
    for symbol, raw_frame in coarse_raw.items():
        basis = _daily_scan_basis(
            raw_frame,
            coarse_split.get(symbol, pd.DataFrame()),
            trading_date,
        )
        if basis is None:
            continue
        prior_close, high, low = basis
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
        adjustment="split",
        asof=trading_date,
    )
    feature_start, feature_end = _feature_bounds(trading_date, profile)
    raw_minutes = alpaca.bars_batched(
        superset,
        batch_size=max(20, min(asset_batch_size, 100)),
        timeframe="1Min",
        start=feature_start,
        end=feature_end,
        feed="sip",
        adjustment="raw",
        asof=trading_date,
    )
    split_current = alpaca.bars_batched(
        superset,
        batch_size=max(20, min(asset_batch_size, 100)),
        timeframe="1Min",
        start=feature_start,
        end=feature_end,
        feed="sip",
        adjustment="split",
        asof=trading_date,
    )

    rvol_history_start, rvol_history_end = _history_window(trading_date, profile)
    coarse_rvol_history = alpaca.bars_batched(
        superset,
        batch_size=max(10, min(asset_batch_size, 40)),
        timeframe="15Min",
        start=rvol_history_start,
        end=rvol_history_end,
        feed="sip",
        adjustment="split",
        asof=trading_date,
    )

    contexts: dict[str, SymbolContext] = {}
    session_dates_by_symbol: dict[str, list[date]] = {}
    upper_curves: dict[str, RvolCurve] = {}
    narrowed: list[str] = []
    intermediate: dict[str, dict[str, object]] = {}

    for symbol in superset:
        daily = history.get(symbol, pd.DataFrame())
        average = _average_volume_before(
            daily,
            trading_date,
            sessions=profile.rvol_lookback_sessions,
        )
        frame = raw_minutes.get(symbol, pd.DataFrame())
        current_split = split_current.get(symbol, pd.DataFrame())
        prior_dates = prior_session_dates(
            daily,
            trading_date=trading_date,
            lookback_sessions=profile.rvol_lookback_sessions,
        )
        session_dates_by_symbol[symbol] = prior_dates
        if average is None or frame.empty:
            continue
        contexts[symbol] = SymbolContext(
            symbol=symbol,
            previous_close=previous_close[symbol],
            average_daily_volume_50=average,
            float_shares=None,
            float_asof=None,
        )
        scan_times = pd.Series(
            [
                profile.session_start <= value < profile.no_new_entries_after
                for value in frame.index.tz_convert(ET).time
            ],
            index=frame.index,
        )
        gain = (
            pd.to_numeric(frame["close"], errors="coerce") / previous_close[symbol] - 1.0
        ) * 100.0
        intermediate[symbol] = {
            "average": average,
            "frame": frame,
            "gain": gain,
            "scan_times": scan_times,
        }
        if len(prior_dates) < profile.rvol_lookback_sessions or current_split.empty:
            continue
        coarse_history = coarse_rvol_history.get(symbol, pd.DataFrame())
        upper = coarse_rvol_upper_bound(
            current_split,
            coarse_history,
            trading_date=trading_date,
            session_dates=prior_dates,
            start_time=profile.volume_feature_start,
            end_time=profile.no_new_entries_after,
        )
        upper_curves[symbol] = upper
        _, _, _, upper_mask = _scan_values(
            frame,
            previous_close=previous_close[symbol],
            rvol_curve=upper.values,
            profile=profile,
        )
        if upper_mask.any():
            narrowed.append(symbol)

    exact_history = alpaca.bars_batched(
        narrowed,
        batch_size=max(5, min(asset_batch_size, 20)),
        timeframe="1Min",
        start=rvol_history_start,
        end=rvol_history_end,
        feed="sip",
        adjustment="split",
        asof=trading_date,
    )
    exact_curves: dict[str, RvolCurve] = {}
    first_qualified: dict[str, str] = {}
    for symbol in narrowed:
        full = exact_history.get(symbol, pd.DataFrame())
        prior_dates = session_dates_by_symbol[symbol]
        exact = same_time_rvol(
            full,
            trading_date=trading_date,
            session_dates=prior_dates,
            start_time=profile.volume_feature_start,
            end_time=profile.no_new_entries_after,
        )
        exact_curves[symbol] = exact
        frame = raw_minutes[symbol]
        _, _, _, mask = _scan_values(
            frame,
            previous_close=previous_close[symbol],
            rvol_curve=exact.values,
            profile=profile,
        )
        if mask.any():
            first_qualified[symbol] = frame.index[mask][0].isoformat()

    rows: list[DiscoveryRow] = []
    qualified_minutes: dict[str, pd.DataFrame] = {}
    rvol_curves: dict[str, pd.Series] = {}
    for symbol, values in intermediate.items():
        frame = values["frame"]
        gain = values["gain"]
        scan_times = values["scan_times"]
        assert isinstance(frame, pd.DataFrame)
        assert isinstance(gain, pd.Series)
        assert isinstance(scan_times, pd.Series)
        scan_gain = gain.loc[scan_times]
        upper = upper_curves.get(symbol)
        exact = exact_curves.get(symbol)
        upper_max = None
        if upper is not None:
            upper_values = upper.values.reindex(frame.index).loc[scan_times].replace(
                [float("inf"), float("-inf")],
                pd.NA,
            )
            if upper_values.notna().any():
                upper_max = float(upper_values.max())
        exact_max = None
        if exact is not None:
            exact_values = exact.values.reindex(frame.index).loc[scan_times].replace(
                [float("inf"), float("-inf")],
                pd.NA,
            )
            if exact_values.notna().any():
                exact_max = float(exact_values.max())
        meta = asset_meta.get(symbol, {})
        first = first_qualified.get(symbol)
        rows.append(
            DiscoveryRow(
                symbol=symbol,
                status=str(meta.get("status", "")),
                exchange=str(meta.get("exchange", "")),
                previous_close=previous_close[symbol],
                target_high=target_high[symbol],
                max_session_gain_pct=(
                    float(scan_gain.max()) if not scan_gain.empty else float("nan")
                ),
                max_session_rvol_upper_bound=upper_max,
                max_session_rvol=exact_max,
                rvol_history_sessions=len(session_dates_by_symbol.get(symbol, [])),
                average_daily_volume_50=float(values["average"]),
                first_market_qualified_at=first,
                minute_bars=len(frame),
            )
        )
        if first:
            qualified_minutes[symbol] = frame
            rvol_curves[symbol] = exact_curves[symbol].values

    rows.sort(
        key=lambda row: (
            row.first_market_qualified_at is not None,
            row.max_session_gain_pct,
        ),
        reverse=True,
    )
    return DiscoveryResult(
        asset_count=len(assets),
        listed_asset_count=len(symbols),
        daily_superset_count=len(superset),
        rvol_prefilter_count=len(narrowed),
        market_candidate_count=len(first_qualified),
        rows=tuple(rows),
        minutes=qualified_minutes,
        contexts=contexts,
        rvol_curves=rvol_curves,
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
    eligible_outstanding = [
        item for item in facts.outstanding_shares if item.available_at <= as_of
    ]
    if not eligible_outstanding:
        return anchor
    anchor_outstanding = min(
        eligible_outstanding,
        key=lambda item: (
            abs((item.measure_date - public.measure_date).days),
            item.available_at,
        ),
    )
    current = max(
        eligible_outstanding,
        key=lambda item: (item.available_at, item.measure_date),
    )
    if current.shares <= anchor_outstanding.shares:
        return anchor
    return roll_forward_float(
        anchor,
        anchor_outstanding=anchor_outstanding,
        current_outstanding=current,
    )


def write_discovery(result: DiscoveryResult, root: Path, *, trading_date: date) -> None:
    root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([asdict(row) for row in result.rows]).to_csv(
        root / "discovery.csv",
        index=False,
    )
    manifest = {
        "schema_version": 3,
        "kind": "market_day_discovery",
        "trading_date": trading_date.isoformat(),
        "asset_count": result.asset_count,
        "listed_asset_count": result.listed_asset_count,
        "daily_superset_count": result.daily_superset_count,
        "rvol_prefilter_count": result.rvol_prefilter_count,
        "market_candidate_count": result.market_candidate_count,
        "universe_complete": False,
        "acquisition_prefilter_uses_full_day_high": True,
        "prefilter_is_not_available_to_strategy": True,
        "execution_price_bar_adjustment": "raw",
        "percent_gain_previous_close_adjustment": "split",
        "daily_volume_history_adjustment": "split",
        "rvol_bar_adjustment": "split",
        "rvol_method": "same_time_cumulative_1m",
        "rvol_acquisition_prefilter": "completed_15m_denominator_upper_bound",
        "notes": [
            "This artifact is a discovery/superset dataset, not yet a runnable complete snapshot.",
            "Float and news are intentionally absent from cross-sectional discovery.",
            (
                "Full-day high is used only to decide what data to acquire and is never "
                "a strategy feature."
            ),
            (
                "Percent gain compares raw target prices with a split-adjusted prior close "
                "on the trading-date share basis."
            ),
        ],
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_reference_case(
    *,
    root: Path,
    symbol: str,
    trading_date: date,
    bars: pd.DataFrame,
    context: SymbolContext,
    news_rows: list[dict],
    float_estimate: FloatEstimate | None = None,
    rvol_curve: pd.Series | None = None,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    bars_dir = root / "bars"
    bars_dir.mkdir(exist_ok=True)
    bars.reset_index().to_csv(bars_dir / f"{symbol}.csv", index=False)
    if rvol_curve is not None:
        rvol_curve.rename("relative_volume").to_csv(
            root / "rvol.csv",
            index_label="timestamp",
        )
    context_row = {
        "symbol": symbol,
        "previous_close": context.previous_close,
        "average_daily_volume_50": context.average_daily_volume_50,
        "float_shares": float_estimate.value_shares if float_estimate else None,
        "float_asof": float_estimate.available_at.isoformat() if float_estimate else None,
        "float_measure_date": (
            float_estimate.measure_date.isoformat() if float_estimate else None
        ),
        "float_method": float_estimate.method if float_estimate else None,
        "float_source_accession": (
            float_estimate.source_accession if float_estimate else None
        ),
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
                "provider": row.get("provider"),
            }
        )
    pd.DataFrame(
        normalized_news,
        columns=[
            "symbol",
            "published_at",
            "headline_id",
            "title",
            "source",
            "provider",
        ],
    ).to_csv(root / "news.csv", index=False)
    manifest = {
        "schema_version": 3,
        "kind": "reference_case",
        "trading_date": trading_date.isoformat(),
        "symbol": symbol,
        "universe_complete": False,
        "runnable_backtest": False,
        "execution_price_bar_adjustment": "raw",
        "percent_gain_previous_close_adjustment": "split",
        "rvol_bar_adjustment": "split",
        "rvol_complete": rvol_curve is not None,
        "float_complete": float_estimate is not None,
        "news_count": len(normalized_news),
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
