"""Causal target-symbol market qualification for historical benchmark cases.

Full-market discovery uses the provider's current asset master as an acquisition
universe.  That is appropriate for current research but can omit a stock that
was tradable on an older benchmark date and was later delisted/renamed.  A
benchmark already knows its historical symbol/date by design, so this module can
query that symbol directly and reproduce the measurable price/gain/RVOL gate
without using any retrospective trade-behavior label.

The result is *not* evidence of historical cross-sectional rank or complete
point-in-time universe membership.  It is only a causal setup-benchmark anchor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from ..models import StrategyProfile
from ..providers.alpaca import AlpacaDataClient
from ..rvol import prior_session_dates, same_time_rvol

ET = ZoneInfo("America/New_York")


@dataclass(frozen=True, slots=True)
class HistoricalTargetQualification:
    symbol: str
    trading_date: str
    previous_close: float
    target_high: float
    average_daily_volume_50: float
    max_session_gain_pct: float
    max_session_rvol: float
    rvol_history_sessions: int
    first_market_qualified_at: str | None
    minute_bars: int
    source: str = "direct_historical_target_price_gain_rvol"


def _local_dates(frame: pd.DataFrame) -> pd.Index:
    return pd.Index(frame.index.tz_convert(ET).date)


def _target_bar(frame: pd.DataFrame, target: date) -> pd.Series | None:
    if frame.empty:
        return None
    rows = frame.loc[_local_dates(frame) == target]
    return rows.iloc[-1] if not rows.empty else None


def _prior_bar(frame: pd.DataFrame, target: date) -> pd.Series | None:
    if frame.empty:
        return None
    rows = frame.loc[_local_dates(frame) < target]
    return rows.iloc[-1] if not rows.empty else None


def _average_volume(frame: pd.DataFrame, target: date, sessions: int) -> float | None:
    if frame.empty:
        return None
    values = (
        pd.to_numeric(frame.loc[_local_dates(frame) < target, "volume"], errors="coerce")
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


def direct_historical_target_qualification(
    alpaca: AlpacaDataClient,
    *,
    symbol: str,
    trading_date: date,
    profile: StrategyProfile,
) -> HistoricalTargetQualification | None:
    """Rebuild the price/gain/same-time-RVOL qualification for one old symbol."""
    symbol = symbol.upper().strip()
    daily_start = datetime.combine(
        trading_date - timedelta(days=120), time(0), timezone.utc
    )
    daily_end = datetime.combine(
        trading_date + timedelta(days=1), time(0), timezone.utc
    )
    raw_daily = alpaca.bars(
        [symbol],
        timeframe="1Day",
        start=daily_start,
        end=daily_end,
        feed="sip",
        adjustment="raw",
        asof=trading_date,
    )[symbol]
    split_daily = alpaca.bars(
        [symbol],
        timeframe="1Day",
        start=daily_start,
        end=daily_end,
        feed="sip",
        adjustment="split",
        asof=trading_date,
    )[symbol]
    target_bar = _target_bar(raw_daily, trading_date)
    prior_bar = _prior_bar(split_daily, trading_date)
    if target_bar is None or prior_bar is None:
        return None
    previous_close = float(prior_bar["close"])
    target_high = float(target_bar["high"])
    if previous_close <= 0:
        return None
    average = _average_volume(
        split_daily, trading_date, profile.rvol_lookback_sessions
    )
    prior_dates = prior_session_dates(
        split_daily,
        trading_date=trading_date,
        lookback_sessions=profile.rvol_lookback_sessions,
    )
    if average is None or len(prior_dates) < profile.rvol_lookback_sessions:
        return None

    feature_start, feature_end = _feature_bounds(trading_date, profile)
    raw_current = alpaca.bars(
        [symbol],
        timeframe="1Min",
        start=feature_start,
        end=feature_end,
        feed="sip",
        adjustment="raw",
        asof=trading_date,
    )[symbol]
    if raw_current.empty:
        return None
    history_start = datetime.combine(
        trading_date - timedelta(days=max(120, int(profile.rvol_lookback_sessions * 2.2))),
        time(0),
        timezone.utc,
    )
    split_intraday = alpaca.bars(
        [symbol],
        timeframe="1Min",
        start=history_start,
        end=feature_end,
        feed="sip",
        adjustment="split",
        asof=trading_date,
    )[symbol]
    curve = same_time_rvol(
        split_intraday,
        trading_date=trading_date,
        session_dates=prior_dates,
        start_time=profile.volume_feature_start,
        end_time=profile.no_new_entries_after,
    ).values.reindex(raw_current.index)

    prices = pd.to_numeric(raw_current["close"], errors="coerce")
    gains = (prices / previous_close - 1.0) * 100.0
    local_times = raw_current.index.tz_convert(ET).time
    in_window = pd.Series(
        [profile.session_start <= value < profile.no_new_entries_after for value in local_times],
        index=raw_current.index,
    )
    mask = (
        in_window
        & (gains >= profile.min_percent_gain)
        & (curve >= profile.min_relative_volume)
        & (prices >= profile.min_price)
        & (prices <= profile.max_price)
    )
    scan_rvol = curve.loc[in_window].dropna()
    scan_gain = gains.loc[in_window].dropna()
    first = raw_current.index[mask][0].isoformat() if mask.any() else None
    return HistoricalTargetQualification(
        symbol=symbol,
        trading_date=trading_date.isoformat(),
        previous_close=previous_close,
        target_high=target_high,
        average_daily_volume_50=average,
        max_session_gain_pct=float(scan_gain.max()) if not scan_gain.empty else float("nan"),
        max_session_rvol=float(scan_rvol.max()) if not scan_rvol.empty else float("nan"),
        rvol_history_sessions=len(prior_dates),
        first_market_qualified_at=first,
        minute_bars=len(raw_current),
    )
