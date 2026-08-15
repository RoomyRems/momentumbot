from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from .indicators import ema, macd, session_vwap, upper_wick_fraction, validate_bars
from .models import EntryPlan, MomentumPhase, PullbackFeatures, StrategyProfile


@dataclass(frozen=True, slots=True)
class PullbackPlanEvaluation:
    plan: EntryPlan | None
    reason: str


def _latest_pullback_peak(bars: pd.DataFrame, max_pullback_bars: int) -> int | None:
    """Return the most recent session-high peak followed by 1..N completed bars."""
    latest = len(bars) - 1
    start = max(0, latest - max_pullback_bars)
    for peak_index in range(latest - 1, start - 1, -1):
        peak_high = float(bars.iloc[peak_index]["high"])
        if peak_high == float(bars.iloc[: peak_index + 1]["high"].max()):
            pullback = bars.iloc[peak_index + 1 :]
            if not pullback.empty and not (pullback["high"] > peak_high).any():
                return peak_index
    return None


def _indicator_bars(
    session_bars: pd.DataFrame,
    indicator_warmup: pd.DataFrame | None,
) -> pd.DataFrame:
    """Combine prior bars with the current session for EMA/MACD only.

    VWAP and pullback geometry deliberately continue to use `session_bars`.
    A real EMA/MACD chart does not reset simply because our acquisition window
    starts at 04:00 ET, so historical replay must carry prior bars forward.
    """
    if indicator_warmup is None or indicator_warmup.empty:
        return session_bars
    validate_bars(indicator_warmup)
    if indicator_warmup.index.tz is None:
        raise ValueError("indicator warmup timestamps must be timezone-aware")
    if session_bars.empty:
        return indicator_warmup
    prior = indicator_warmup.loc[indicator_warmup.index < session_bars.index[0]]
    combined = pd.concat([prior, session_bars]).sort_index()
    return combined.loc[~combined.index.duplicated(keep="last")]


def evaluate_first_pullback_plan(
    symbol: str,
    bars_so_far: pd.DataFrame,
    profile: StrategyProfile,
    *,
    pullback_number: int | None = None,
    indicator_warmup: pd.DataFrame | None = None,
) -> PullbackPlanEvaluation:
    """Evaluate the deterministic pullback plan and preserve its first rejection reason.

    `bars_so_far` is the current-session history used for VWAP, peaks, pullback
    geometry and volume. `indicator_warmup` is prior history used only to warm
    EMA9/MACD. This separation prevents an arbitrary snapshot start time from
    resetting continuous indicators while still resetting session VWAP.
    """
    validate_bars(bars_so_far)
    indicators = _indicator_bars(bars_so_far, indicator_warmup)
    minimum = max(profile.macd_slow + profile.macd_signal, profile.ema_span) + 1
    if len(indicators) < minimum:
        return PullbackPlanEvaluation(None, "insufficient_history")

    peak_index = _latest_pullback_peak(bars_so_far, profile.max_pullback_bars)
    if peak_index is None:
        return PullbackPlanEvaluation(None, "no_recent_session_high_peak")

    pullback = bars_so_far.iloc[peak_index + 1 :]
    peak = bars_so_far.iloc[peak_index]
    peak_high = float(peak["high"])
    pullback_low = float(pullback["low"].min())

    impulse_start = max(0, peak_index - 4)
    impulse = bars_so_far.iloc[impulse_start : peak_index + 1]
    impulse_base = float(impulse["low"].min())
    impulse_range = peak_high - impulse_base
    if impulse_range <= 0:
        return PullbackPlanEvaluation(None, "nonpositive_impulse_range")

    retrace_fraction = (peak_high - pullback_low) / impulse_range
    if retrace_fraction > profile.max_retrace_fraction:
        return PullbackPlanEvaluation(None, "retrace_above_half")

    has_pause = (pullback["close"] < pullback["open"]).any() or (
        pullback["close"].diff().dropna() < 0
    ).any()
    if not has_pause:
        return PullbackPlanEvaluation(None, "no_pullback_pause")

    ema9 = ema(indicators["close"], profile.ema_span)
    macd_values = macd(
        indicators["close"], profile.macd_fast, profile.macd_slow, profile.macd_signal
    )
    vwap = session_vwap(bars_so_far)
    latest_timestamp = bars_so_far.index[-1]
    latest_macd = macd_values.loc[latest_timestamp]
    if pd.isna(latest_macd["macd"]) or pd.isna(latest_macd["signal"]):
        return PullbackPlanEvaluation(None, "macd_unavailable")
    phase = (
        MomentumPhase.FRONT_SIDE
        if float(latest_macd["macd"]) > float(latest_macd["signal"])
        else MomentumPhase.BACK_SIDE
    )
    if phase is not MomentumPhase.FRONT_SIDE:
        return PullbackPlanEvaluation(None, "back_side_momentum")

    low_timestamp = pullback["low"].idxmin()
    ema_at_low = float(ema9.loc[low_timestamp])
    vwap_at_low = float(vwap.loc[low_timestamp])
    if math.isnan(ema_at_low) or math.isnan(vwap_at_low):
        return PullbackPlanEvaluation(None, "ema_vwap_unavailable")
    if pullback_low < ema_at_low:
        return PullbackPlanEvaluation(None, "pullback_below_ema9")
    if pullback_low < vwap_at_low:
        return PullbackPlanEvaluation(None, "pullback_below_vwap")

    impulse_mean_volume = float(impulse["volume"].mean())
    pullback_mean_volume = float(pullback["volume"].mean())
    if pullback_mean_volume >= impulse_mean_volume:
        return PullbackPlanEvaluation(None, "pullback_volume_not_lower")

    peak_wick = upper_wick_fraction(peak)
    if peak_wick >= profile.max_peak_upper_wick_fraction:
        return PullbackPlanEvaluation(None, "peak_topping_tail")

    previous_candle_high = float(pullback.iloc[-1]["high"])
    trigger = round(previous_candle_high + profile.tick_size, 10)
    stop = pullback_low
    risk_per_share = trigger - stop
    if risk_per_share <= 0:
        return PullbackPlanEvaluation(None, "nonpositive_risk")
    reward_r = (peak_high - trigger) / risk_per_share
    if reward_r < profile.min_reward_r_to_prior_high:
        return PullbackPlanEvaluation(None, "insufficient_reward_to_prior_high")

    warnings: list[str] = []
    if pullback_number is not None and pullback_number > 2:
        warnings.append("later-than-second pullback")

    features = PullbackFeatures(
        symbol=symbol,
        evaluated_at=bars_so_far.index[-1].to_pydatetime(),
        pullback_bars=len(pullback),
        pullback_number=pullback_number,
        peak_high=peak_high,
        pullback_low=pullback_low,
        retrace_fraction=retrace_fraction,
        impulse_mean_volume=impulse_mean_volume,
        pullback_mean_volume=pullback_mean_volume,
        peak_upper_wick_fraction=peak_wick,
        ema9_at_low=ema_at_low,
        vwap_at_low=vwap_at_low,
        macd_line=float(latest_macd["macd"]),
        macd_signal=float(latest_macd["signal"]),
        momentum_phase=phase,
    )
    plan = EntryPlan(
        symbol=symbol,
        created_at=bars_so_far.index[-1].to_pydatetime(),
        trigger_price=trigger,
        stop_price=stop,
        prior_high=peak_high,
        risk_per_share=risk_per_share,
        reward_r_to_prior_high=reward_r,
        features=features,
        warnings=tuple(warnings),
    )
    return PullbackPlanEvaluation(plan, "plan")


def build_first_pullback_plan(
    symbol: str,
    bars_so_far: pd.DataFrame,
    profile: StrategyProfile,
    *,
    pullback_number: int | None = None,
    indicator_warmup: pd.DataFrame | None = None,
) -> EntryPlan | None:
    """Build a next-bar stop entry using completed one-minute session bars."""
    return evaluate_first_pullback_plan(
        symbol,
        bars_so_far,
        profile,
        pullback_number=pullback_number,
        indicator_warmup=indicator_warmup,
    ).plan
