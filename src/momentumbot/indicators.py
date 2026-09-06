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
