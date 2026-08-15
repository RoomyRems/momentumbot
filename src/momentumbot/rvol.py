from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ET = ZoneInfo("America/New_York")


@dataclass(frozen=True, slots=True)
class RvolCurve:
    values: pd.Series
    history_sessions: int
    method: str


def prior_session_dates(
    daily_bars: pd.DataFrame,
    *,
    trading_date: date,
    lookback_sessions: int,
) -> list[date]:
    if lookback_sessions <= 0:
        raise ValueError("lookback_sessions must be positive")
    if daily_bars.empty:
        return []
    if daily_bars.index.tz is None:
        raise ValueError("daily bars must have timezone-aware timestamps")
    local_dates = daily_bars.index.tz_convert(ET).date
    eligible = sorted({day for day in local_dates if day < trading_date})
    return eligible[-lookback_sessions:]


def _minute_grid(
    trading_date: date,
    *,
    start_time: time,
    end_time: time,
) -> pd.DatetimeIndex:
    start = pd.Timestamp(datetime.combine(trading_date, start_time, ET))
    end = pd.Timestamp(datetime.combine(trading_date, end_time, ET))
    if start > end:
        raise ValueError("start_time must not be after end_time")
    return pd.date_range(start, end, freq="1min").tz_convert("UTC")


def _minute_array(
    bars: pd.DataFrame,
    *,
    trading_date: date,
    start_time: time,
    end_time: time,
) -> np.ndarray:
    grid = _minute_grid(trading_date, start_time=start_time, end_time=end_time)
    result = np.zeros(len(grid), dtype=float)
    if bars.empty:
        return result
    if bars.index.tz is None:
        raise ValueError("intraday bars must have timezone-aware timestamps")
    local = bars.index.tz_convert(ET)
    target = bars.loc[local.date == trading_date]
    if target.empty:
        return result
    local_target = target.index.tz_convert(ET)
    start_minutes = start_time.hour * 60 + start_time.minute
    end_minutes = end_time.hour * 60 + end_time.minute
    volumes = pd.to_numeric(target["volume"], errors="coerce").fillna(0.0)
    for timestamp, volume in zip(local_target, volumes, strict=True):
        minute = timestamp.hour * 60 + timestamp.minute
        if start_minutes <= minute <= end_minutes:
            result[minute - start_minutes] += float(volume)
    return result


def _history_cumulative_matrix(
    bars: pd.DataFrame,
    *,
    session_dates: list[date],
    start_time: time,
    end_time: time,
) -> np.ndarray:
    rows = [
        np.cumsum(
            _minute_array(
                bars,
                trading_date=session_date,
                start_time=start_time,
                end_time=end_time,
            )
        )
        for session_date in session_dates
    ]
    if not rows:
        return np.empty((0, len(_minute_grid(date(2000, 1, 3), start_time=start_time, end_time=end_time))))
    return np.vstack(rows)


def same_time_rvol(
    split_adjusted_1m_bars: pd.DataFrame,
    *,
    trading_date: date,
    session_dates: list[date],
    start_time: time = time(4, 0),
    end_time: time = time(10, 0),
) -> RvolCurve:
    """Calculate cumulative RVOL against mean cumulative volume at each minute.

    Both numerator and history must be split-adjusted bars. That keeps share units
    comparable across reverse/forward splits while leaving the separate raw price
    series untouched for historical price-band and execution decisions.
    """
    grid = _minute_grid(trading_date, start_time=start_time, end_time=end_time)
    current = np.cumsum(
        _minute_array(
            split_adjusted_1m_bars,
            trading_date=trading_date,
            start_time=start_time,
            end_time=end_time,
        )
    )
    history = _history_cumulative_matrix(
        split_adjusted_1m_bars,
        session_dates=session_dates,
        start_time=start_time,
        end_time=end_time,
    )
    if history.size == 0:
        values = np.full(len(grid), np.nan, dtype=float)
    else:
        expected = history.mean(axis=0)
        values = np.divide(
            current,
            expected,
            out=np.full(len(grid), np.nan, dtype=float),
            where=expected > 0,
        )
        values[(expected == 0) & (current > 0)] = np.inf
    return RvolCurve(
        values=pd.Series(values, index=grid, name="relative_volume"),
        history_sessions=len(session_dates),
        method="same_time_cumulative_1m_split_adjusted",
    )


def coarse_rvol_upper_bound(
    current_split_adjusted_1m_bars: pd.DataFrame,
    historical_split_adjusted_15m_bars: pd.DataFrame,
    *,
    trading_date: date,
    session_dates: list[date],
    start_time: time = time(4, 0),
    end_time: time = time(10, 0),
) -> RvolCurve:
    """Conservative acquisition prefilter for exact same-time RVOL.

    The denominator includes only *completed* historical 15-minute buckets before
    the minute being evaluated. It therefore cannot exceed the true same-minute
    expected cumulative volume. The resulting ratio is an upper bound and may
    create false positives, but should not discard an exact 5x RVOL event merely
    because it happened early inside a 15-minute bucket.
    """
    grid = _minute_grid(trading_date, start_time=start_time, end_time=end_time)
    current = np.cumsum(
        _minute_array(
            current_split_adjusted_1m_bars,
            trading_date=trading_date,
            start_time=start_time,
            end_time=end_time,
        )
    )
    start_minutes = start_time.hour * 60 + start_time.minute
    end_minutes = end_time.hour * 60 + end_time.minute
    bucket_count = (end_minutes - start_minutes) // 15
    historical_cumulative: list[np.ndarray] = []

    if historical_split_adjusted_15m_bars.index.tz is None and not historical_split_adjusted_15m_bars.empty:
        raise ValueError("historical intraday bars must have timezone-aware timestamps")
    for session_date in session_dates:
        buckets = np.zeros(bucket_count, dtype=float)
        if not historical_split_adjusted_15m_bars.empty:
            local = historical_split_adjusted_15m_bars.index.tz_convert(ET)
            day_frame = historical_split_adjusted_15m_bars.loc[local.date == session_date]
            day_local = day_frame.index.tz_convert(ET)
            volumes = pd.to_numeric(day_frame["volume"], errors="coerce").fillna(0.0)
            for timestamp, volume in zip(day_local, volumes, strict=True):
                minute = timestamp.hour * 60 + timestamp.minute
                offset = minute - start_minutes
                if 0 <= offset < bucket_count * 15:
                    buckets[offset // 15] += float(volume)
        historical_cumulative.append(np.cumsum(buckets))

    if not historical_cumulative:
        values = np.full(len(grid), np.nan, dtype=float)
    else:
        expected_completed = np.vstack(historical_cumulative).mean(axis=0)
        denominators = np.zeros(len(grid), dtype=float)
        for offset in range(len(grid)):
            completed_buckets = offset // 15
            if completed_buckets > 0:
                denominators[offset] = expected_completed[completed_buckets - 1]
        values = np.divide(
            current,
            denominators,
            out=np.full(len(grid), np.nan, dtype=float),
            where=denominators > 0,
        )
        values[(denominators == 0) & (current > 0)] = np.inf
    return RvolCurve(
        values=pd.Series(values, index=grid, name="relative_volume_upper_bound"),
        history_sessions=len(session_dates),
        method="upper_bound_completed_15m_split_adjusted",
    )
