"""Research-only pre-qualification structural-context ablation.

Micro v0.1 deliberately remains unchanged. This module isolates one information-
boundary hypothesis discovered by the frozen seed benchmark: a trader can see
completed chart structure that existed before a scanner threshold was crossed,
while still being prohibited from acting before that causal qualification time.

The ablation therefore changes *only* the structural-history start used by setup
detection. Setup geometry, post-qualification pullback numbering, support rules,
trigger semantics, and execution remain the frozen parent policy's rules. It is
not permitted to arm or fill a plan before the actual candidate qualification
timestamp.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json

import pandas as pd

from ..micro_execution import MicroTriggerMode, simulate_micro_entries
from ..micro_policy import micro_v0_1_policy
from ..micro_replay import (
    MicroCandidateReplay,
    MicroReplayStep,
    causal_active_pullback_number,
    micro_replay_runtime_artifact,
)
from ..micro_setup import (
    MicroSetupPolicy,
    canonical_micro_setup_policy,
    evaluate_micro_pullback_plan,
)


MICRO_V0_2A_CONTEXT_ID = "micro-v0.2a-prequalification-context"
MICRO_V0_2A_CONTEXT_STATUS = "research_ablation_not_promoted"


@dataclass(frozen=True, slots=True)
class PrequalificationContextAblation:
    ablation_id: str
    status: str
    parent_policy_id: str
    parent_policy_fingerprint: str
    context_bars: int
    bar_interval_seconds: int
    action_gate: str = "actual_candidate_qualification"
    context_rule: str = "completed_bars_before_qualification_only"
    pullback_ordinal_rule: str = "actual_candidate_qualification"

    def __post_init__(self) -> None:
        if self.context_bars < 1:
            raise ValueError("context_bars must be positive")
        if self.bar_interval_seconds < 1:
            raise ValueError("bar_interval_seconds must be positive")

    def payload(self) -> dict[str, object]:
        return asdict(self)

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.payload(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @property
    def context_seconds(self) -> int:
        return self.context_bars * self.bar_interval_seconds


@dataclass(frozen=True, slots=True)
class PrequalificationContextReplay:
    spec: PrequalificationContextAblation
    structural_context_start: datetime
    available_prequalification_context_bars: int
    replay: MicroCandidateReplay


def micro_v0_2a_context_ablation() -> PrequalificationContextAblation:
    """Return the fixed first context ablation derived from v0.1 geometry.

    Ten context bars is not fitted to the seed examples. It is the minimum
    bounded history implied by the parent's existing five-bar impulse lookback
    plus five-bar maximum pullback duration.
    """
    parent = micro_v0_1_policy()
    return PrequalificationContextAblation(
        ablation_id=MICRO_V0_2A_CONTEXT_ID,
        status=MICRO_V0_2A_CONTEXT_STATUS,
        parent_policy_id=parent.policy_id,
        parent_policy_fingerprint=parent.fingerprint,
        context_bars=(
            parent.setup.impulse_lookback_bars + parent.setup.max_pullback_bars
        ),
        bar_interval_seconds=parent.micro_bar_interval_seconds,
    )


def _validate_micro_index(bars: pd.DataFrame) -> None:
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise TypeError("micro-bar index must be a DatetimeIndex")
    if bars.index.tz is None:
        raise ValueError("micro bars must be timezone-aware")
    if not bars.index.is_monotonic_increasing:
        raise ValueError("micro bars must be sorted by timestamp")


def completed_prequalification_context_start(
    bars: pd.DataFrame,
    *,
    candidate_qualified_at: datetime | pd.Timestamp,
    context_bars: int,
    bar_interval_seconds: int,
) -> tuple[pd.Timestamp, int]:
    """Return a bounded structural start using only bars completed by qualification."""
    _validate_micro_index(bars)
    qualified = pd.Timestamp(candidate_qualified_at)
    if qualified.tzinfo is None:
        raise ValueError("candidate_qualified_at must be timezone-aware")
    if context_bars < 1:
        raise ValueError("context_bars must be positive")
    if bar_interval_seconds < 1:
        raise ValueError("bar_interval_seconds must be positive")

    completed_at = bars.index + pd.Timedelta(seconds=bar_interval_seconds)
    available = bars.index[completed_at <= qualified]
    if len(available) == 0:
        return qualified, 0
    selected = available[-context_bars:]
    return pd.Timestamp(selected[0]), len(selected)


def replay_micro_candidate_with_prequalification_context(
    symbol: str,
    bars: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    candidate_qualified_at: datetime | pd.Timestamp,
    spec: PrequalificationContextAblation | None = None,
    policy: MicroSetupPolicy | None = None,
    vwap_available: pd.Series | None = None,
    ema9_available: pd.Series | None = None,
    trigger_mode: MicroTriggerMode = MicroTriggerMode.CHART_PRICE,
    entry_latency_ms: float = 0.0,
    target_price: float | None = None,
    exit_until: pd.Timestamp | None = None,
) -> PrequalificationContextReplay:
    """Replay post-qualification actions with bounded earlier completed structure.

    Evaluation still starts only on micro bars whose bucket start is at or after
    the actual qualification timestamp. Earlier completed bars may define setup
    geometry, but cannot themselves cause a plan to be armed. Pullback ordinal
    metadata remains anchored at the actual qualification timestamp so the
    experiment does not quietly change a second variable.
    """
    _validate_micro_index(bars)
    qualified = pd.Timestamp(candidate_qualified_at)
    if qualified.tzinfo is None:
        raise ValueError("candidate_qualified_at must be timezone-aware")
    setup_policy = policy or canonical_micro_setup_policy()
    context_spec = spec or micro_v0_2a_context_ablation()
    mode = MicroTriggerMode(trigger_mode)
    if entry_latency_ms < 0:
        raise ValueError("entry_latency_ms cannot be negative")

    structural_start, available_context = completed_prequalification_context_start(
        bars,
        candidate_qualified_at=qualified,
        context_bars=context_spec.context_bars,
        bar_interval_seconds=context_spec.bar_interval_seconds,
    )

    pending: list[tuple[pd.Timestamp, int, object]] = []
    plans = []
    plan_step_indexes: list[int] = []

    for timestamp in bars.loc[qualified:].index:
        prefix = bars.loc[:timestamp]
        # Ordinal remains exactly qualification-anchored as in the frozen parent.
        pullback_number = causal_active_pullback_number(
            prefix,
            candidate_qualified_at=qualified,
        )
        # Only setup geometry receives the earlier completed structural context.
        evaluation = evaluate_micro_pullback_plan(
            symbol,
            prefix,
            candidate_qualified_at=structural_start,
            policy=setup_policy,
            pullback_number=pullback_number,
            vwap_available=vwap_available,
            ema9_available=ema9_available,
        )
        step_index = len(pending)
        pending.append((pd.Timestamp(timestamp), pullback_number, evaluation))
        if evaluation.plan is not None:
            if pd.Timestamp(evaluation.plan.armed_at) < qualified:
                raise RuntimeError("context ablation attempted to arm before qualification")
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
        policy_name=f"{setup_policy.name}|{context_spec.ablation_id}",
        trigger_mode=mode,
        entry_latency_ms=float(entry_latency_ms),
        steps=steps,
    )
    return PrequalificationContextReplay(
        spec=context_spec,
        structural_context_start=structural_start.to_pydatetime(),
        available_prequalification_context_bars=available_context,
        replay=replay,
    )


def prequalification_context_runtime_artifact(
    result: PrequalificationContextReplay,
) -> dict[str, object]:
    """Serialize the ablation while preserving explicit parent-policy provenance."""
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
            "structural_context_rule": result.spec.context_rule,
            "structural_context_bars_requested": result.spec.context_bars,
            "structural_context_bars_available": result.available_prequalification_context_bars,
            "structural_context_start": result.structural_context_start.isoformat(),
            "action_gate": result.spec.action_gate,
            "pullback_ordinal_rule": result.spec.pullback_ordinal_rule,
        }
    )
    return payload
