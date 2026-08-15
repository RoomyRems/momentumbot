from __future__ import annotations

import math

import pandas as pd

from .indicators import ema, macd, session_vwap, upper_wick_fraction, validate_bars
from .models import EntryPlan, MomentumPhase, PullbackFeatures, StrategyProfile


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


def build_first_pullback_plan(
    symbol: str,
    bars_so_far: pd.DataFrame,
    profile: StrategyProfile,
    *,
    pullback_number: int | None = None,
) -> EntryPlan | None:
    """Build a next-bar stop entry using completed one-minute bars only.

    Research translation notes:
    - the most recent *session high* anchors the impulse/pullback;
    - the impulse base is the lowest low of the five completed bars leading into
      that high. Ross defines the 50% concept but not a machine swing algorithm,
      so this five-bar anchor is deliberately isolated here for ablation;
    - a large topping tail is translated as an upper wick >= half the candle range.
    """
    validate_bars(bars_so_far)
    minimum = max(profile.macd_slow + profile.macd_signal, profile.ema_span) + 1
    if len(bars_so_far) < minimum:
        return None

    peak_index = _latest_pullback_peak(bars_so_far, profile.max_pullback_bars)
    if peak_index is None:
        return None

    pullback = bars_so_far.iloc[peak_index + 1 :]
    peak = bars_so_far.iloc[peak_index]
    peak_high = float(peak["high"])
    pullback_low = float(pullback["low"].min())

    impulse_start = max(0, peak_index - 4)
    impulse = bars_so_far.iloc[impulse_start : peak_index + 1]
    impulse_base = float(impulse["low"].min())
    impulse_range = peak_high - impulse_base
    if impulse_range <= 0:
        return None

    retrace_fraction = (peak_high - pullback_low) / impulse_range
    if retrace_fraction > profile.max_retrace_fraction:
        return None

    has_pause = (pullback["close"] < pullback["open"]).any() or (
        pullback["close"].diff().dropna() < 0
    ).any()
    if not has_pause:
        return None

    ema9 = ema(bars_so_far["close"], profile.ema_span)
    vwap = session_vwap(bars_so_far)
    macd_values = macd(
        bars_so_far["close"], profile.macd_fast, profile.macd_slow, profile.macd_signal
    )
    latest_macd = macd_values.iloc[-1]
    if pd.isna(latest_macd["macd"]) or pd.isna(latest_macd["signal"]):
        return None
    phase = (
        MomentumPhase.FRONT_SIDE
        if float(latest_macd["macd"]) > float(latest_macd["signal"])
        else MomentumPhase.BACK_SIDE
    )
    if phase is not MomentumPhase.FRONT_SIDE:
        return None

    low_timestamp = pullback["low"].idxmin()
    ema_at_low = float(ema9.loc[low_timestamp])
    vwap_at_low = float(vwap.loc[low_timestamp])
    if math.isnan(ema_at_low) or math.isnan(vwap_at_low):
        return None
    if pullback_low < ema_at_low or pullback_low < vwap_at_low:
        return None

    impulse_mean_volume = float(impulse["volume"].mean())
    pullback_mean_volume = float(pullback["volume"].mean())
    if pullback_mean_volume >= impulse_mean_volume:
        return None

    peak_wick = upper_wick_fraction(peak)
    if peak_wick >= profile.max_peak_upper_wick_fraction:
        return None

    previous_candle_high = float(pullback.iloc[-1]["high"])
    trigger = round(previous_candle_high + profile.tick_size, 10)
    stop = pullback_low
    risk_per_share = trigger - stop
    if risk_per_share <= 0:
        return None
    reward_r = (peak_high - trigger) / risk_per_share
    if reward_r < profile.min_reward_r_to_prior_high:
        return None

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
    return EntryPlan(
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
