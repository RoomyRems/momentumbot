"""Observational micro-pullback state used by research and imitation tests.

The detector deliberately starts at the timestamp when a stock first becomes a
qualified/obvious candidate. It does not decide whether to trade. A pullback is
observed after a running high when one or more completed micro bars fail to make
a new high; it is confirmed only when a later completed bar exceeds that prior
running high. This gives us a causal pullback ordinal without fitting VRAX-only
price thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd


@dataclass(frozen=True, slots=True)
class MicroPullbackObservation:
    ordinal: int
    peak_time: datetime
    peak_high: float
    pullback_start: datetime
    trough_time: datetime
    trough_low: float
    resumption_time: datetime
    resumption_high: float
    pullback_bars: int
    pullback_mean_volume: float

    @property
    def peak_drawdown_fraction(self) -> float:
        return (self.peak_high - self.trough_low) / self.peak_high


def detect_running_high_pullbacks(
    bars: pd.DataFrame,
    *,
    start_at: datetime | pd.Timestamp,
) -> tuple[MicroPullbackObservation, ...]:
    required = {"high", "low", "volume"}
    missing = sorted(required - set(bars.columns))
    if missing:
        raise ValueError(f"missing micro-bar columns: {missing}")
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise TypeError("micro-bar index must be a DatetimeIndex")
    if bars.index.tz is None:
        raise ValueError("micro-bar timestamps must be timezone-aware")

    start = pd.Timestamp(start_at)
    if start.tzinfo is None:
        raise ValueError("start_at must be timezone-aware")
    window = bars.loc[start:].sort_index()
    if window.empty:
        return ()

    first_time = window.index[0]
    running_peak_time = first_time
    running_peak_high = float(window.iloc[0]["high"])
    pullback_start_time: pd.Timestamp | None = None
    trough_time: pd.Timestamp | None = None
    trough_low = float("inf")
    pullback_volumes: list[float] = []
    observations: list[MicroPullbackObservation] = []

    for timestamp, row in window.iloc[1:].iterrows():
        high = float(row["high"])
        low = float(row["low"])
        if high > running_peak_high:
            if pullback_start_time is not None and trough_time is not None:
                observations.append(
                    MicroPullbackObservation(
                        ordinal=len(observations) + 1,
                        peak_time=running_peak_time.to_pydatetime(),
                        peak_high=running_peak_high,
                        pullback_start=pullback_start_time.to_pydatetime(),
                        trough_time=trough_time.to_pydatetime(),
                        trough_low=trough_low,
                        resumption_time=timestamp.to_pydatetime(),
                        resumption_high=high,
                        pullback_bars=len(pullback_volumes),
                        pullback_mean_volume=sum(pullback_volumes) / len(pullback_volumes),
                    )
                )
            running_peak_time = timestamp
            running_peak_high = high
            pullback_start_time = None
            trough_time = None
            trough_low = float("inf")
            pullback_volumes = []
            continue

        if pullback_start_time is None:
            pullback_start_time = timestamp
        pullback_volumes.append(float(row["volume"]))
        if low < trough_low:
            trough_low = low
            trough_time = timestamp

    return tuple(observations)
