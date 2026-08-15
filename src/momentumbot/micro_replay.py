"""Reusable causal replay for one qualified micro-momentum candidate.

This module is intentionally label-blind. It receives only runtime market data,
a candidate qualification timestamp, and a deterministic setup policy. For each
completed micro bar it derives the active pullback ordinal from already-confirmed
running-high pullbacks, evaluates the setup, and then executes every armed plan
against the same ordered SIP tape.

Retrospective benchmark labels belong in a separate post-replay comparison step.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from numbers import Integral, Real
from typing import Any

import pandas as pd

from .micro_execution import (
    MicroEntryPlan,
    MicroExecutionOutcome,
    MicroTriggerMode,
    simulate_micro_entries,
)
from .micro_setup import (
    MicroPullbackFeatures,
    MicroSetupEvaluation,
    MicroSetupPolicy,
    canonical_micro_setup_policy,
    detect_running_high_pullbacks,
    evaluate_micro_pullback_plan,
)


@dataclass(frozen=True, slots=True)
class MicroReplayStep:
    evaluated_at: datetime
    pullback_number: int
    reason: str
    plan: MicroEntryPlan | None
    features: MicroPullbackFeatures | None
    outcome: MicroExecutionOutcome | None

    @property
    def execution_status(self) -> str | None:
        return self.outcome.status.value if self.outcome is not None else None

    @property
    def filled(self) -> bool:
        return self.outcome is not None and self.outcome.fill_price is not None


@dataclass(frozen=True, slots=True)
class MicroCandidateReplay:
    symbol: str
    candidate_qualified_at: datetime
    policy_name: str
    trigger_mode: MicroTriggerMode
    entry_latency_ms: float
    steps: tuple[MicroReplayStep, ...]

    @property
    def plan_count(self) -> int:
        return sum(step.plan is not None for step in self.steps)

    @property
    def filled_count(self) -> int:
        return sum(step.filled for step in self.steps)

    @property
    def filled_steps(self) -> tuple[MicroReplayStep, ...]:
        return tuple(step for step in self.steps if step.filled)

    @property
    def filled_pullback_numbers(self) -> tuple[int, ...]:
        return tuple(step.pullback_number for step in self.filled_steps)

    @property
    def reason_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(step.reason for step in self.steps).items()))


def _validated_qualified_at(value: datetime | pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("candidate_qualified_at must be timezone-aware")
    return timestamp


def _validate_micro_index(bars: pd.DataFrame) -> None:
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise TypeError("micro-bar index must be a DatetimeIndex")
    if bars.index.tz is None:
        raise ValueError("micro-bar timestamps must be timezone-aware")
    if not bars.index.is_monotonic_increasing:
        raise ValueError("micro bars must be sorted by timestamp")


def causal_active_pullback_number(
    bars_so_far: pd.DataFrame,
    *,
    candidate_qualified_at: datetime | pd.Timestamp,
) -> int:
    """Return confirmed pullbacks plus the currently forming pullback ordinal."""
    qualified = _validated_qualified_at(candidate_qualified_at)
    confirmed = detect_running_high_pullbacks(bars_so_far, start_at=qualified)
    return len(confirmed) + 1


def replay_micro_candidate(
    symbol: str,
    bars: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    candidate_qualified_at: datetime | pd.Timestamp,
    policy: MicroSetupPolicy | None = None,
    vwap_available: pd.Series | None = None,
    ema9_available: pd.Series | None = None,
    trigger_mode: MicroTriggerMode = MicroTriggerMode.CHART_PRICE,
    entry_latency_ms: float = 0.0,
    target_price: float | None = None,
    exit_until: pd.Timestamp | None = None,
) -> MicroCandidateReplay:
    """Replay every completed micro prefix causally for one qualified symbol.

    Plans are refreshed independently as each new micro bar completes. The
    function does not choose a retrospective 'best' plan and does not stop after
    a fill; it is a diagnostic replay of all deterministic opportunities. A
    later portfolio/campaign layer is responsible for position state and
    re-entry constraints.
    """
    _validate_micro_index(bars)
    qualified = _validated_qualified_at(candidate_qualified_at)
    setup_policy = policy or canonical_micro_setup_policy()
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
        evaluation = evaluate_micro_pullback_plan(
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
    return MicroCandidateReplay(
        symbol=symbol,
        candidate_qualified_at=qualified.to_pydatetime(),
        policy_name=setup_policy.name,
        trigger_mode=mode,
        entry_latency_ms=float(entry_latency_ms),
        steps=steps,
    )


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if is_dataclass(value):
        return {
            field.name: _json_safe(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        numeric = float(value)
        return None if pd.isna(numeric) else numeric
    return value


def micro_replay_runtime_artifact(replay: MicroCandidateReplay) -> dict[str, object]:
    """Serialize a replay without adding any retrospective benchmark context.

    This is the stable boundary between runtime reconstruction and imitation
    scoring. Downstream benchmark code may load a retrospective label only after
    this payload has already been produced.
    """
    return {
        "artifact_type": "micro_candidate_runtime_replay",
        "schema_version": 1,
        "knowledge_policy": "runtime_market_data_only_no_retrospective_labels",
        "symbol": replay.symbol,
        "candidate_qualified_at": replay.candidate_qualified_at.isoformat(),
        "policy_name": replay.policy_name,
        "trigger_mode": replay.trigger_mode.value,
        "entry_latency_ms": replay.entry_latency_ms,
        "plan_count": replay.plan_count,
        "filled_count": replay.filled_count,
        "filled_pullback_numbers": list(replay.filled_pullback_numbers),
        "reason_counts": replay.reason_counts,
        "steps": _json_safe(replay.steps),
    }
