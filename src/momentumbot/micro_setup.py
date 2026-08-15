"""Micro-pullback observation and deterministic setup translation.

Two layers intentionally coexist here:

1. ``detect_running_high_pullbacks`` is observational. It counts confirmed
   pullbacks after a stock becomes a qualified candidate and does not decide
   whether to trade.
2. ``evaluate_micro_pullback_plan`` evaluates an *unconfirmed current pullback*
   using only completed micro bars and can arm the next forming bar for the
   canonical first-candle-to-make-a-new-high entry.

The canonical policy translates the current evidence-backed pullback rules:
roughly <=50% retracement, lighter pullback volume, support above VWAP/9 EMA,
and no major topping-tail rejection. The machine definitions of the impulse
lookback and maximum micro-pullback duration are isolated as research
translations rather than presented as source-authored constants.

Half-dollar and whole-dollar prices are exposed as context only. They never
replace the canonical first-new-high trigger inside the setup evaluator. A
separate helper can create research continuation plans at those levels so
benchmarks can measure whether psychological-level context adds information
without silently turning an observed example into a universal rule.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import pandas as pd

from .indicators import upper_wick_fraction
from .micro_execution import MicroEntryPlan


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


class MicroPsychologicalLevel(str, Enum):
    HALF_DOLLAR = "half_dollar"
    WHOLE_DOLLAR = "whole_dollar"


@dataclass(frozen=True, slots=True)
class MicroSetupPolicy:
    name: str
    max_pullback_bars: int = 5
    impulse_lookback_bars: int = 5
    max_retrace_fraction: float = 0.50
    max_peak_upper_wick_fraction: float = 0.50
    require_lower_pullback_volume: bool = True
    require_vwap_support: bool = True
    require_ema9_support: bool = True
    tick_size: float = 0.01

    def __post_init__(self) -> None:
        if self.max_pullback_bars < 1:
            raise ValueError("max_pullback_bars must be positive")
        if self.impulse_lookback_bars < 1:
            raise ValueError("impulse_lookback_bars must be positive")
        if not 0 < self.max_retrace_fraction <= 1:
            raise ValueError("max_retrace_fraction must be in (0, 1]")
        if not 0 <= self.max_peak_upper_wick_fraction <= 1:
            raise ValueError("max_peak_upper_wick_fraction must be in [0, 1]")
        if self.tick_size <= 0:
            raise ValueError("tick_size must be positive")


@dataclass(frozen=True, slots=True)
class MicroPullbackFeatures:
    symbol: str
    evaluated_at: datetime
    pullback_number: int | None
    peak_time: datetime
    peak_high: float
    impulse_base: float
    pullback_start: datetime
    pullback_bars: int
    trough_time: datetime
    pullback_low: float
    retrace_fraction: float
    impulse_mean_volume: float
    pullback_mean_volume: float
    peak_upper_wick_fraction: float
    previous_candle_high: float
    next_half_dollar_above_peak: float
    next_whole_dollar_above_peak: float
    distance_to_next_half_dollar: float
    distance_to_next_whole_dollar: float
    vwap_at_low: float | None
    ema9_at_low: float | None


@dataclass(frozen=True, slots=True)
class MicroSetupEvaluation:
    plan: MicroEntryPlan | None
    reason: str
    features: MicroPullbackFeatures | None = None


def canonical_micro_setup_policy() -> MicroSetupPolicy:
    """Evidence-backed current micro translation with slower-chart support required."""
    return MicroSetupPolicy(name="canonical-micro-current-2026")


def geometry_only_micro_research_policy() -> MicroSetupPolicy:
    """Research-only geometry policy for benchmarks lacking causal support series."""
    return MicroSetupPolicy(
        name="micro-geometry-research-only",
        require_vwap_support=False,
        require_ema9_support=False,
    )


def _validate_micro_bars(bars: pd.DataFrame, required: set[str]) -> None:
    missing = sorted(required - set(bars.columns))
    if missing:
        raise ValueError(f"missing micro-bar columns: {missing}")
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise TypeError("micro-bar index must be a DatetimeIndex")
    if bars.index.tz is None:
        raise ValueError("micro-bar timestamps must be timezone-aware")
    if not bars.index.is_monotonic_increasing:
        raise ValueError("micro bars must be sorted by timestamp")


def detect_running_high_pullbacks(
    bars: pd.DataFrame,
    *,
    start_at: datetime | pd.Timestamp,
) -> tuple[MicroPullbackObservation, ...]:
    required = {"high", "low", "volume"}
    _validate_micro_bars(bars, required)

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


def _latest_running_high_pullback_peak(
    bars: pd.DataFrame,
    *,
    max_pullback_bars: int,
) -> int | None:
    """Find the latest *strict* running-high peak followed by 1..N pullback bars.

    A later candle that merely retests the same high remains part of the
    pullback. It cannot replace the original peak unless it exceeds every prior
    high. This matches ``detect_running_high_pullbacks`` and prevents an equal
    high from silently shrinking the measured impulse and pullback history.
    """
    latest = len(bars) - 1
    start = max(0, latest - max_pullback_bars)
    highs = pd.to_numeric(bars["high"], errors="coerce")
    for peak_index in range(latest - 1, start - 1, -1):
        peak_high = float(highs.iloc[peak_index])
        if peak_index > 0 and peak_high <= float(highs.iloc[:peak_index].max()):
            continue
        pullback = bars.iloc[peak_index + 1 :]
        if pullback.empty or len(pullback) > max_pullback_bars:
            continue
        if (pd.to_numeric(pullback["high"], errors="coerce") > peak_high).any():
            continue
        return peak_index
    return None


def _next_half_dollar_above(price: float) -> float:
    if price <= 0:
        raise ValueError("price must be positive")
    return round((math.floor(price * 2 + 1e-12) + 1) / 2, 10)


def _next_whole_dollar_above(price: float) -> float:
    if price <= 0:
        raise ValueError("price must be positive")
    return round(float(math.floor(price + 1e-12) + 1), 10)


def build_psychological_level_continuation_plan(
    evaluation: MicroSetupEvaluation,
    level: MicroPsychologicalLevel,
    *,
    tick_size: float = 0.01,
) -> MicroEntryPlan | None:
    """Create a research-only continuation plan from a valid micro setup.

    The base setup must already be valid. This helper does not claim that a
    half-dollar or whole-dollar should be chosen; it merely makes either context
    level executable for sensitivity analysis. The canonical plan stored on the
    evaluation remains unchanged.
    """
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")
    if evaluation.plan is None or evaluation.features is None:
        return None

    features = evaluation.features
    if level is MicroPsychologicalLevel.HALF_DOLLAR:
        trigger = features.next_half_dollar_above_peak
    elif level is MicroPsychologicalLevel.WHOLE_DOLLAR:
        trigger = features.next_whole_dollar_above_peak
    else:
        raise ValueError(f"unsupported psychological level: {level}")

    if trigger <= evaluation.plan.minimum_new_high_price:
        return None
    breakout_level = round(trigger - tick_size, 10)
    return MicroEntryPlan(
        symbol=evaluation.plan.symbol,
        source_bar_start=evaluation.plan.source_bar_start,
        armed_at=evaluation.plan.armed_at,
        expires_at=evaluation.plan.expires_at,
        breakout_level=breakout_level,
        minimum_new_high_price=trigger,
        stop_price=evaluation.plan.stop_price,
    )


def _support_asof(series: pd.Series | None, timestamp: pd.Timestamp) -> float | None:
    """Read a support series whose index represents when each value became available."""
    if series is None:
        return None
    if not isinstance(series.index, pd.DatetimeIndex):
        raise TypeError("support series index must be a DatetimeIndex")
    if series.index.tz is None:
        raise ValueError("support series timestamps must be timezone-aware")
    available = pd.to_numeric(series.loc[:timestamp], errors="coerce").dropna()
    if available.empty:
        return None
    return float(available.iloc[-1])


def evaluate_micro_pullback_plan(
    symbol: str,
    bars_so_far: pd.DataFrame,
    *,
    candidate_qualified_at: datetime | pd.Timestamp,
    policy: MicroSetupPolicy | None = None,
    pullback_number: int | None = None,
    vwap_available: pd.Series | None = None,
    ema9_available: pd.Series | None = None,
) -> MicroSetupEvaluation:
    """Evaluate a current micro pullback using completed bars only.

    ``vwap_available`` and ``ema9_available`` must be indexed by the timestamp
    when a value was actually knowable to the strategy, not merely by the start
    timestamp of a slower candle. This keeps the micro evaluator from reading a
    still-forming one-minute bar.
    """
    policy = policy or canonical_micro_setup_policy()
    required = {"open", "high", "low", "close", "volume"}
    _validate_micro_bars(bars_so_far, required)
    qualified = pd.Timestamp(candidate_qualified_at)
    if qualified.tzinfo is None:
        raise ValueError("candidate_qualified_at must be timezone-aware")
    window = bars_so_far.loc[qualified:].copy()
    if len(window) < 2:
        return MicroSetupEvaluation(None, "insufficient_micro_history")

    peak_index = _latest_running_high_pullback_peak(
        window,
        max_pullback_bars=policy.max_pullback_bars,
    )
    if peak_index is None:
        return MicroSetupEvaluation(None, "no_current_running_high_pullback")

    peak = window.iloc[peak_index]
    peak_time = window.index[peak_index]
    peak_high = float(peak["high"])
    pullback = window.iloc[peak_index + 1 :]
    pullback_low = float(pd.to_numeric(pullback["low"], errors="coerce").min())
    trough_time = pd.to_numeric(pullback["low"], errors="coerce").idxmin()

    has_pause = (pd.to_numeric(pullback["close"], errors="coerce") < pd.to_numeric(pullback["open"], errors="coerce")).any()
    close_changes = pd.to_numeric(pullback["close"], errors="coerce").diff().dropna()
    has_pause = bool(has_pause or (close_changes < 0).any())
    if not has_pause:
        return MicroSetupEvaluation(None, "no_micro_pullback_pause")

    impulse_start = max(0, peak_index - policy.impulse_lookback_bars + 1)
    impulse = window.iloc[impulse_start : peak_index + 1]
    impulse_base = float(pd.to_numeric(impulse["low"], errors="coerce").min())
    impulse_range = peak_high - impulse_base
    if impulse_range <= 0:
        return MicroSetupEvaluation(None, "nonpositive_micro_impulse_range")

    retrace_fraction = (peak_high - pullback_low) / impulse_range
    if retrace_fraction > policy.max_retrace_fraction:
        return MicroSetupEvaluation(None, "micro_retrace_above_half")

    impulse_mean_volume = float(pd.to_numeric(impulse["volume"], errors="coerce").mean())
    pullback_mean_volume = float(pd.to_numeric(pullback["volume"], errors="coerce").mean())
    if policy.require_lower_pullback_volume and pullback_mean_volume >= impulse_mean_volume:
        return MicroSetupEvaluation(None, "micro_pullback_volume_not_lower")

    peak_wick = upper_wick_fraction(peak)
    if peak_wick >= policy.max_peak_upper_wick_fraction:
        return MicroSetupEvaluation(None, "micro_peak_topping_tail")

    vwap_at_low = _support_asof(vwap_available, trough_time)
    ema9_at_low = _support_asof(ema9_available, trough_time)
    if policy.require_vwap_support:
        if vwap_at_low is None:
            return MicroSetupEvaluation(None, "micro_vwap_context_unavailable")
        if pullback_low < vwap_at_low:
            return MicroSetupEvaluation(None, "micro_pullback_below_vwap")
    if policy.require_ema9_support:
        if ema9_at_low is None:
            return MicroSetupEvaluation(None, "micro_ema9_context_unavailable")
        if pullback_low < ema9_at_low:
            return MicroSetupEvaluation(None, "micro_pullback_below_ema9")

    previous_candle_high = float(pullback.iloc[-1]["high"])
    trigger = round(previous_candle_high + policy.tick_size, 10)
    stop = pullback_low
    if trigger <= stop:
        return MicroSetupEvaluation(None, "nonpositive_micro_risk")

    next_half = _next_half_dollar_above(peak_high)
    next_whole = _next_whole_dollar_above(peak_high)
    features = MicroPullbackFeatures(
        symbol=symbol,
        evaluated_at=window.index[-1].to_pydatetime(),
        pullback_number=pullback_number,
        peak_time=peak_time.to_pydatetime(),
        peak_high=peak_high,
        impulse_base=impulse_base,
        pullback_start=pullback.index[0].to_pydatetime(),
        pullback_bars=len(pullback),
        trough_time=trough_time.to_pydatetime(),
        pullback_low=pullback_low,
        retrace_fraction=retrace_fraction,
        impulse_mean_volume=impulse_mean_volume,
        pullback_mean_volume=pullback_mean_volume,
        peak_upper_wick_fraction=peak_wick,
        previous_candle_high=previous_candle_high,
        next_half_dollar_above_peak=next_half,
        next_whole_dollar_above_peak=next_whole,
        distance_to_next_half_dollar=next_half - peak_high,
        distance_to_next_whole_dollar=next_whole - peak_high,
        vwap_at_low=vwap_at_low,
        ema9_at_low=ema9_at_low,
    )
    plan = MicroEntryPlan(
        symbol=symbol,
        source_bar_start=window.index[-1],
        armed_at=window.index[-1] + pd.Timedelta(seconds=10),
        expires_at=window.index[-1] + pd.Timedelta(seconds=20),
        breakout_level=previous_candle_high,
        minimum_new_high_price=trigger,
        stop_price=stop,
    )
    return MicroSetupEvaluation(plan, "plan", features)
