from __future__ import annotations

import numpy as np
import pandas as pd

REQUIRED_BAR_COLUMNS = ("open", "high", "low", "close", "volume")


def validate_bars(bars: pd.DataFrame) -> None:
    missing = [column for column in REQUIRED_BAR_COLUMNS if column not in bars.columns]
    if missing:
        raise ValueError(f"missing bar columns: {missing}")
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise TypeError("bars index must be a pandas DatetimeIndex")
    if bars.index.has_duplicates:
        raise ValueError("bar timestamps must be unique")
    if not bars.index.is_monotonic_increasing:
        raise ValueError("bar timestamps must be increasing")
    if bars.empty:
        return
    if (bars["volume"] < 0).any():
        raise ValueError("volume cannot be negative")
    if (bars[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("prices must be positive")
    if (bars["high"] < bars[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("high must contain open/close/low")
    if (bars["low"] > bars[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("low must contain open/close/high")


def ema(series: pd.Series, span: int) -> pd.Series:
    if span <= 0:
        raise ValueError("EMA span must be positive")
    return series.astype(float).ewm(span=span, adjust=False, min_periods=span).mean()


def session_vwap(bars: pd.DataFrame) -> pd.Series:
    validate_bars(bars)
    typical = (bars["high"] + bars["low"] + bars["close"]) / 3.0
    volume = bars["volume"].astype(float)
    cumulative_volume = volume.cumsum()
    result = (typical * volume).cumsum() / cumulative_volume.replace(0, np.nan)
    return result


def completed_bar_support_series(
    bars: pd.DataFrame,
    *,
    ema_span: int = 9,
    bar_duration: str | pd.Timedelta = "1min",
) -> pd.DataFrame:
    """Return VWAP/EMA values indexed by when the completed bar became knowable.

    Input bars are expected to be indexed by bar *start* time. Indicator values
    are calculated causally from each row and its predecessors, then the output
    timestamp is shifted by ``bar_duration``. A one-minute bar stamped 07:31:00
    therefore first contributes support context at 07:32:00.

    ``session_vwap`` starts at the first supplied row, so callers must pass the
    intended session history rather than a benchmark-only slice when they need
    true session VWAP. Historical rows after the decision time are safe to
    include because their availability timestamps remain in the future.
    """
    validate_bars(bars)
    if bars.index.tz is None:
        raise ValueError("bars must use timezone-aware timestamps for causal availability")
    duration = pd.Timedelta(bar_duration)
    if duration <= pd.Timedelta(0):
        raise ValueError("bar_duration must be positive")

    values = pd.DataFrame(
        {
            "vwap": session_vwap(bars),
            "ema": ema(bars["close"], ema_span),
        },
        index=bars.index,
    )
    values.index = values.index + duration
    values.index.name = "available_at"
    return values


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    if not (0 < fast < slow and signal > 0):
        raise ValueError("MACD requires 0 < fast < slow and positive signal")
    fast_line = ema(close, fast)
    slow_line = ema(close, slow)
    line = fast_line - slow_line
    signal_line = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame(
        {"macd": line, "signal": signal_line, "histogram": line - signal_line},
        index=close.index,
    )


def upper_wick_fraction(row: pd.Series) -> float:
    candle_range = float(row["high"] - row["low"])
    if candle_range <= 0:
        return 0.0
    upper_body = max(float(row["open"]), float(row["close"]))
    return max(0.0, float(row["high"] - upper_body)) / candle_range
