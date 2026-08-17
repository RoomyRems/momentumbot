"""Research-only qualification-anchored impulse-base ablation.

The frozen Micro v0.1 evaluator measures retracement from the minimum low in
the parent's five-bar impulse window ending at the selected peak.  This module
tests one categorical alternative: measure the retracement denominator from
the minimum *post-qualification* low through that same peak.

Only the retracement base changes.  Peak selection, the five-bar window used
for impulse mean volume, the 50% threshold, pullback duration, volume gate,
wick/support rules, trigger, stop, execution, action gate, and causal pullback
ordinal remain the frozen parent rules.  The alternative introduces no fitted
lookback or threshold and never reads pre-qualification structure.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json

import pandas as pd

from ..indicators import upper_wick_fraction
from ..micro_execution import MicroEntryPlan, MicroTriggerMode, simulate_micro_entries
from ..micro_policy import micro_v0_1_policy
from ..micro_replay import (
    MicroCandidateReplay,
    MicroReplayStep,
    causal_active_pullback_number,
    micro_replay_runtime_artifact,
)
from ..micro_setup import (
    MicroPullbackFeatures,
    MicroSetupEvaluation,
    MicroSetupPolicy,
    _latest_running_high_pullback_peak,
    _next_half_dollar_above,
    _next_whole_dollar_above,
    _support_asof,
    _validate_micro_bars,
)


MICRO_V0_2E_IMPULSE_BASE_ID = "micro-v0.2e-qualification-anchored-impulse-base"
MICRO_V0_2E_IMPULSE_BASE_STATUS = "research_ablation_not_promoted"


@dataclass(frozen=True, slots=True)
class QualificationAnchoredImpulseBaseAblation:
    ablation_id: str
    status: str
    parent_policy_id: str
    parent_policy_fingerprint: str
    parent_impulse_lookback_bars: int
    impulse_base_rule: str = "minimum_postqualification_low_through_selected_peak"
    impulse_volume_rule: str = "parent_five_bar_impulse_window_unchanged"
    peak_rule: str = "strict_running_high_parent_v0_1"
    action_gate: str = "actual_candidate_qualification"
    structural_context_rule: str = "postqualification_only_parent_v0_1"
    pullback_ordinal_rule: str = "actual_candidate_qualification_parent_observer"

    def __post_init__(self) -> None:
        if self.parent_impulse_lookback_bars < 1:
            raise ValueError("parent_impulse_lookback_bars must be positive")

    def payload(self) -> dict[str, object]:
        return asdict(self)

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.payload(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class QualificationAnchoredImpulseBaseReplay:
    spec: QualificationAnchoredImpulseBaseAblation
    replay: MicroCandidateReplay


def micro_v0_2e_impulse_base_ablation() -> QualificationAnchoredImpulseBaseAblation:
    parent = micro_v0_1_policy()
    return QualificationAnchoredImpulseBaseAblation(
        ablation_id=MICRO_V0_2E_IMPULSE_BASE_ID,
        status=MICRO_V0_2E_IMPULSE_BASE_STATUS,
        parent_policy_id=parent.policy_id,
        parent_policy_fingerprint=parent.fingerprint,
        parent_impulse_lookback_bars=parent.setup.impulse_lookback_bars,
    )


def evaluate_micro_pullback_plan_with_qualification_base(
    symbol: str,
    bars_so_far: pd.DataFrame,
    *,
    candidate_qualified_at: datetime | pd.Timestamp,
    policy: MicroSetupPolicy,
    pullback_number: int | None = None,
    vwap_available: pd.Series | None = None,
    ema9_available: pd.Series | None = None,
) -> MicroSetupEvaluation:
    """Evaluate v0.1 with only its retracement impulse base changed."""
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

    has_pause = (
        pd.to_numeric(pullback["close"], errors="coerce")
        < pd.to_numeric(pullback["open"], errors="coerce")
    ).any()
    close_changes = pd.to_numeric(pullback["close"], errors="coerce").diff().dropna()
    has_pause = bool(has_pause or (close_changes < 0).any())
    if not has_pause:
        return MicroSetupEvaluation(None, "no_micro_pullback_pause")

    # The sole ablation: the base scope begins at actual qualification.  The
    # parent's five-bar impulse remains authoritative for the volume feature.
    base_scope = window.iloc[: peak_index + 1]
    impulse_base = float(pd.to_numeric(base_scope["low"], errors="coerce").min())
    impulse_range = peak_high - impulse_base
    if impulse_range <= 0:
        return MicroSetupEvaluation(None, "nonpositive_micro_impulse_range")

    retrace_fraction = (peak_high - pullback_low) / impulse_range
    if retrace_fraction > policy.max_retrace_fraction:
        return MicroSetupEvaluation(None, "micro_retrace_above_half")

    impulse_start = max(0, peak_index - policy.impulse_lookback_bars + 1)
    parent_impulse = window.iloc[impulse_start : peak_index + 1]
    impulse_mean_volume = float(
        pd.to_numeric(parent_impulse["volume"], errors="coerce").mean()
    )
    pullback_mean_volume = float(
        pd.to_numeric(pullback["volume"], errors="coerce").mean()
    )
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


def replay_micro_candidate_with_qualification_base(
    symbol: str,
    bars: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    candidate_qualified_at: datetime | pd.Timestamp,
    spec: QualificationAnchoredImpulseBaseAblation | None = None,
    policy: MicroSetupPolicy | None = None,
    vwap_available: pd.Series | None = None,
    ema9_available: pd.Series | None = None,
    trigger_mode: MicroTriggerMode = MicroTriggerMode.CHART_PRICE,
    entry_latency_ms: float = 0.0,
    target_price: float | None = None,
    exit_until: pd.Timestamp | None = None,
) -> QualificationAnchoredImpulseBaseReplay:
    _validate_micro_bars(bars, {"open", "high", "low", "close", "volume"})
    qualified = pd.Timestamp(candidate_qualified_at)
    if qualified.tzinfo is None:
        raise ValueError("candidate_qualified_at must be timezone-aware")
    parent = micro_v0_1_policy()
    setup_policy = policy or parent.setup
    base_spec = spec or micro_v0_2e_impulse_base_ablation()
    mode = MicroTriggerMode(trigger_mode)
    if entry_latency_ms < 0:
        raise ValueError("entry_latency_ms cannot be negative")

    pending: list[tuple[pd.Timestamp, int, MicroSetupEvaluation]] = []
    plans: list[MicroEntryPlan] = []
    plan_step_indexes: list[int] = []
    for timestamp in bars.loc[qualified:].index:
        prefix = bars.loc[:timestamp]
        pullback_number = causal_active_pullback_number(
            prefix,
            candidate_qualified_at=qualified,
        )
        evaluation = evaluate_micro_pullback_plan_with_qualification_base(
            symbol,
            prefix,
            candidate_qualified_at=qualified,
            policy=setup_policy,
            pullback_number=pullback_number,
            vwap_available=vwap_available,
            ema9_available=ema9_available,
        )
        step_index = len(pending)
        pending.append((pd.Timestamp(timestamp), pullback_number, evaluation))
        if evaluation.plan is not None:
            if pd.Timestamp(evaluation.plan.armed_at) < qualified:
                raise RuntimeError("impulse-base ablation attempted to arm before qualification")
            plans.append(evaluation.plan)
            plan_step_indexes.append(step_index)

    outcomes = simulate_micro_entries(
        plans,
        trades,
        trigger_mode=mode,
        entry_latency_ms=entry_latency_ms,
        target_price=target_price,
        exit_until=exit_until,
    )
    outcome_by_step = {
        step_index: outcome
        for step_index, outcome in zip(plan_step_indexes, outcomes)
    }
    steps = tuple(
        MicroReplayStep(
            evaluated_at=timestamp.to_pydatetime(),
            pullback_number=pullback_number,
            reason=evaluation.reason,
            plan=evaluation.plan,
            features=evaluation.features,
            outcome=outcome_by_step.get(index),
        )
        for index, (timestamp, pullback_number, evaluation) in enumerate(pending)
    )
    replay = MicroCandidateReplay(
        symbol=symbol,
        candidate_qualified_at=qualified.to_pydatetime(),
        policy_name=f"{setup_policy.name}|{base_spec.ablation_id}",
        trigger_mode=mode,
        entry_latency_ms=float(entry_latency_ms),
        steps=steps,
    )
    return QualificationAnchoredImpulseBaseReplay(spec=base_spec, replay=replay)


def impulse_base_runtime_artifact(
    result: QualificationAnchoredImpulseBaseReplay,
) -> dict[str, object]:
    """Serialize one label-blind impulse-base runtime replay."""
    payload = micro_replay_runtime_artifact(result.replay)
    payload.update(
        {
            "artifact_type": "micro_candidate_runtime_replay_ablation",
            "schema_version": 2,
            "ablation_id": result.spec.ablation_id,
            "ablation_status": result.spec.status,
            "ablation_fingerprint": result.spec.fingerprint,
            "parent_frozen_policy_id": result.spec.parent_policy_id,
            "parent_frozen_policy_fingerprint": result.spec.parent_policy_fingerprint,
            "impulse_base_rule": result.spec.impulse_base_rule,
            "impulse_volume_rule": result.spec.impulse_volume_rule,
            "parent_impulse_lookback_bars": result.spec.parent_impulse_lookback_bars,
            "peak_rule": result.spec.peak_rule,
            "structural_context_rule": result.spec.structural_context_rule,
            "action_gate": result.spec.action_gate,
            "pullback_ordinal_rule": result.spec.pullback_ordinal_rule,
        }
    )
    return payload
