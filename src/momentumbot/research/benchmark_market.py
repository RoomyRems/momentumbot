"""Causal target-symbol market qualification for historical benchmark cases.

Full-market discovery uses the provider's current asset master as an acquisition
universe. That can omit a stock that traded on an older benchmark date and was
later delisted/renamed. A benchmark already knows its historical symbol/date,
so direct historical queries may rebuild the measurable price/gain/RVOL gate
without using any retrospective trade-behavior label.

One-minute discovery timestamps are acquisition *bucket starts*, not decision
timestamps: their closing price and volume are only fully knowable at bucket
completion. For benchmark cases we refine the target bucket with ordered SIP
trades. The RVOL test uses the historical expected cumulative volume through the
*end* of that minute, making the intraminute crossing conservative rather than
using an unknowable second-by-second denominator.

Neither path establishes historical cross-sectional rank or a complete
point-in-time universe. Those belong to the broader backtest-data problem.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from ..micro_bars import minute_trade_eligibility
from ..models import StrategyProfile
from ..providers.alpaca import AlpacaDataClient
from ..providers.alpaca_trades import historical_trades
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


@dataclass(frozen=True, slots=True)
class IntraminuteQualification:
    symbol: str
    candidate_minute_start: str
    qualified_at: str | None
    method: str
    expected_cumulative_volume_through_minute: float
    cumulative_volume_before_minute: float
    cumulative_volume_at_qualification: float | None
    rvol_at_qualification: float | None
    price_at_qualification: float | None
    gain_pct_at_qualification: float | None
    trade_prints_in_candidate_minute: int


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


def _history_start(trading_date: date, profile: StrategyProfile) -> datetime:
    return datetime.combine(
        trading_date
        - timedelta(days=max(120, int(profile.rvol_lookback_sessions * 2.2))),
        time(0),
        timezone.utc,
    )


def _cumulative_volume_through_local_minute(
    bars: pd.DataFrame,
    *,
    session_date: date,
    start_time: time,
    through_time: time,
) -> float:
    if bars.empty:
        return 0.0
    local = bars.index.tz_convert(ET)
    times = local.time
    mask = (
        (local.date == session_date)
        & pd.Series([value >= start_time for value in times], index=bars.index).to_numpy()
        & pd.Series([value <= through_time for value in times], index=bars.index).to_numpy()
    )
    if not mask.any():
        return 0.0
    return float(pd.to_numeric(bars.loc[mask, "volume"], errors="coerce").fillna(0.0).sum())


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
    split_intraday = alpaca.bars(
        [symbol],
        timeframe="1Min",
        start=_history_start(trading_date, profile),
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


def refine_candidate_minute_with_sip(
    alpaca: AlpacaDataClient,
    *,
    symbol: str,
    trading_date: date,
    candidate_minute_start: datetime | pd.Timestamp,
    previous_close: float,
    profile: StrategyProfile,
) -> IntraminuteQualification:
    """Find a conservative causal crossing inside a one-minute acquisition bucket.

    The historical denominator is mean cumulative volume through the *end* of
    the candidate minute across the prior sessions. This intentionally delays,
    rather than anticipates, the RVOL crossing when only one-minute historical
    seasonality is available.
    """
    minute_start = pd.Timestamp(candidate_minute_start)
    if minute_start.tzinfo is None:
        raise ValueError("candidate_minute_start must be timezone-aware")
    minute_start = minute_start.floor("min")
    local_start = minute_start.tz_convert(ET)
    if local_start.date() != trading_date:
        raise ValueError("candidate minute must belong to trading_date")
    if previous_close <= 0:
        raise ValueError("previous_close must be positive")

    daily_start = datetime.combine(
        trading_date - timedelta(days=120), time(0), timezone.utc
    )
    daily_end = datetime.combine(trading_date, time(23, 59), timezone.utc)
    split_daily = alpaca.bars(
        [symbol],
        timeframe="1Day",
        start=daily_start,
        end=daily_end,
        feed="sip",
        adjustment="split",
        asof=trading_date,
    )[symbol]
    prior_dates = prior_session_dates(
        split_daily,
        trading_date=trading_date,
        lookback_sessions=profile.rvol_lookback_sessions,
    )
    if len(prior_dates) < profile.rvol_lookback_sessions:
        return IntraminuteQualification(
            symbol=symbol,
            candidate_minute_start=minute_start.isoformat(),
            qualified_at=None,
            method="insufficient_rvol_history",
            expected_cumulative_volume_through_minute=float("nan"),
            cumulative_volume_before_minute=float("nan"),
            cumulative_volume_at_qualification=None,
            rvol_at_qualification=None,
            price_at_qualification=None,
            gain_pct_at_qualification=None,
            trade_prints_in_candidate_minute=0,
        )

    minute_end = minute_start + pd.Timedelta(minutes=1)
    split_intraday = alpaca.bars(
        [symbol],
        timeframe="1Min",
        start=_history_start(trading_date, profile),
        end=minute_end.to_pydatetime(),
        feed="sip",
        adjustment="split",
        asof=trading_date,
    )[symbol]
    through_time = local_start.time().replace(second=0, microsecond=0)
    expected_values = [
        _cumulative_volume_through_local_minute(
            split_intraday,
            session_date=session_date,
            start_time=profile.volume_feature_start,
            through_time=through_time,
        )
        for session_date in prior_dates
    ]
    expected = float(pd.Series(expected_values, dtype=float).mean())
    current_local = split_intraday.index.tz_convert(ET)
    pre_mask = (
        (current_local.date == trading_date)
        & pd.Series(
            [profile.volume_feature_start <= value < through_time for value in current_local.time],
            index=split_intraday.index,
        ).to_numpy()
    )
    prior_volume = float(
        pd.to_numeric(split_intraday.loc[pre_mask, "volume"], errors="coerce")
        .fillna(0.0)
        .sum()
    )

    trades = historical_trades(
        alpaca,
        symbol,
        start=minute_start.to_pydatetime(),
        end=minute_end.to_pydatetime(),
        feed="sip",
        asof=trading_date,
    )
    cumulative = prior_volume
    latest_price: float | None = None
    for timestamp, trade in trades.iterrows():
        eligibility = minute_trade_eligibility(
            trade.get("tape"), trade.get("conditions") or ()
        )
        if eligibility.updates_volume:
            cumulative += float(trade["size"])
        if eligibility.updates_price:
            latest_price = float(trade["price"])
        if latest_price is None:
            continue
        rvol = (
            cumulative / expected
            if expected > 0
            else (float("inf") if cumulative > 0 else float("nan"))
        )
        gain = (latest_price / previous_close - 1.0) * 100.0
        if (
            profile.min_price <= latest_price <= profile.max_price
            and gain >= profile.min_percent_gain
            and rvol >= profile.min_relative_volume
        ):
            return IntraminuteQualification(
                symbol=symbol,
                candidate_minute_start=minute_start.isoformat(),
                qualified_at=pd.Timestamp(timestamp).isoformat(),
                method="sip_intraminute_conservative_end_minute_rvol_denominator",
                expected_cumulative_volume_through_minute=expected,
                cumulative_volume_before_minute=prior_volume,
                cumulative_volume_at_qualification=cumulative,
                rvol_at_qualification=rvol,
                price_at_qualification=latest_price,
                gain_pct_at_qualification=gain,
                trade_prints_in_candidate_minute=len(trades),
            )

    return IntraminuteQualification(
        symbol=symbol,
        candidate_minute_start=minute_start.isoformat(),
        qualified_at=None,
        method="no_conservative_intraminute_crossing_use_completed_minute_if_acquisition_qualified",
        expected_cumulative_volume_through_minute=expected,
        cumulative_volume_before_minute=prior_volume,
        cumulative_volume_at_qualification=None,
        rvol_at_qualification=None,
        price_at_qualification=None,
        gain_pct_at_qualification=None,
        trade_prints_in_candidate_minute=len(trades),
    )
