"""Research-only factorial ablations for the micro pullback volume gate.

Micro v0.1 remains immutable.  These experiments isolate whether the parent's
hard requirement that pullback mean volume be below impulse mean volume is
responsible for missed early entries, and whether that effect interacts with
the already-measured bounded pre-qualification context rule.

Two cells are defined here in addition to the existing baseline and v0.2a cells:

* v0.2c: no pre-qualification context, no hard lower-volume rejection.
* v0.2d: bounded pre-qualification context, no hard lower-volume rejection.

The volume measurements remain in the feature artifact; only their use as a
binary rejection gate changes.  No fitted volume ratio or threshold is added.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
import hashlib
import json

import pandas as pd

from ..micro_execution import MicroTriggerMode
from ..micro_policy import micro_v0_1_policy
from ..micro_replay import (
    MicroCandidateReplay,
    micro_replay_runtime_artifact,
    replay_micro_candidate,
)
from ..micro_setup import MicroSetupPolicy
from .micro_context_ablation import (
    micro_v0_2a_context_ablation,
    replay_micro_candidate_with_prequalification_context,
)


MICRO_V0_2C_VOLUME_ID = "micro-v0.2c-no-hard-volume-gate"
MICRO_V0_2D_CONTEXT_VOLUME_ID = "micro-v0.2d-context-no-hard-volume-gate"
MICRO_VOLUME_ABLATION_STATUS = "research_ablation_not_promoted"


@dataclass(frozen=True, slots=True)
class MicroVolumeAblationSpec:
    ablation_id: str
    status: str
    parent_policy_id: str
    parent_policy_fingerprint: str
    require_lower_pullback_volume: bool
    prequalification_context_enabled: bool
    context_bars: int
    context_bar_interval_seconds: int
    volume_rule: str = "measure_only_no_hard_rejection"
    action_gate: str = "actual_candidate_qualification"

    def __post_init__(self) -> None:
        if self.require_lower_pullback_volume:
            raise ValueError("volume ablation must disable the hard lower-volume gate")
        if self.context_bars < 0:
            raise ValueError("context_bars cannot be negative")
        if self.context_bar_interval_seconds < 1:
            raise ValueError("context_bar_interval_seconds must be positive")
        if not self.prequalification_context_enabled and self.context_bars != 0:
            raise ValueError("no-context ablation must request zero context bars")
        if self.prequalification_context_enabled and self.context_bars < 1:
            raise ValueError("context-enabled ablation must request context bars")

    def payload(self) -> dict[str, object]:
        return asdict(self)

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.payload(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class MicroVolumeAblationReplay:
    spec: MicroVolumeAblationSpec
    replay: MicroCandidateReplay
    structural_context_start: datetime | None = None
    available_prequalification_context_bars: int | None = None


def micro_v0_2c_volume_ablation() -> MicroVolumeAblationSpec:
    parent = micro_v0_1_policy()
    return MicroVolumeAblationSpec(
        ablation_id=MICRO_V0_2C_VOLUME_ID,
        status=MICRO_VOLUME_ABLATION_STATUS,
        parent_policy_id=parent.policy_id,
        parent_policy_fingerprint=parent.fingerprint,
        require_lower_pullback_volume=False,
        prequalification_context_enabled=False,
        context_bars=0,
        context_bar_interval_seconds=parent.micro_bar_interval_seconds,
    )


def micro_v0_2d_context_volume_ablation() -> MicroVolumeAblationSpec:
    parent = micro_v0_1_policy()
    context = micro_v0_2a_context_ablation()
    return MicroVolumeAblationSpec(
        ablation_id=MICRO_V0_2D_CONTEXT_VOLUME_ID,
        status=MICRO_VOLUME_ABLATION_STATUS,
        parent_policy_id=parent.policy_id,
        parent_policy_fingerprint=parent.fingerprint,
        require_lower_pullback_volume=False,
        prequalification_context_enabled=True,
        context_bars=context.context_bars,
        context_bar_interval_seconds=context.bar_interval_seconds,
    )


def parent_setup_without_hard_volume_gate() -> MicroSetupPolicy:
    """Return v0.1 setup geometry with only the hard volume rejection disabled."""
    parent = micro_v0_1_policy()
    return replace(
        parent.setup,
        name=f"{parent.setup.name}|no-hard-volume-gate",
        require_lower_pullback_volume=False,
    )


def replay_micro_candidate_without_hard_volume_gate(
    symbol: str,
    bars: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    candidate_qualified_at: datetime | pd.Timestamp,
    spec: MicroVolumeAblationSpec | None = None,
    vwap_available: pd.Series | None = None,
    ema9_available: pd.Series | None = None,
    trigger_mode: MicroTriggerMode = MicroTriggerMode.CHART_PRICE,
    entry_latency_ms: float = 0.0,
    target_price: float | None = None,
    exit_until: pd.Timestamp | None = None,
) -> MicroVolumeAblationReplay:
    volume_spec = spec or micro_v0_2c_volume_ablation()
    if volume_spec.prequalification_context_enabled:
        raise ValueError("no-context replay received a context-enabled spec")
    replay = replay_micro_candidate(
        symbol,
        bars,
        trades,
        candidate_qualified_at=candidate_qualified_at,
        policy=parent_setup_without_hard_volume_gate(),
        vwap_available=vwap_available,
        ema9_available=ema9_available,
        trigger_mode=trigger_mode,
        entry_latency_ms=entry_latency_ms,
        target_price=target_price,
        exit_until=exit_until,
    )
    return MicroVolumeAblationReplay(spec=volume_spec, replay=replay)


def replay_micro_candidate_with_context_without_hard_volume_gate(
    symbol: str,
    bars: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    candidate_qualified_at: datetime | pd.Timestamp,
    spec: MicroVolumeAblationSpec | None = None,
    vwap_available: pd.Series | None = None,
    ema9_available: pd.Series | None = None,
    trigger_mode: MicroTriggerMode = MicroTriggerMode.CHART_PRICE,
    entry_latency_ms: float = 0.0,
    target_price: float | None = None,
    exit_until: pd.Timestamp | None = None,
) -> MicroVolumeAblationReplay:
    volume_spec = spec or micro_v0_2d_context_volume_ablation()
    if not volume_spec.prequalification_context_enabled:
        raise ValueError("context replay received a no-context spec")
    context_spec = micro_v0_2a_context_ablation()
    if volume_spec.context_bars != context_spec.context_bars:
        raise ValueError("context-volume spec no longer matches the measured v0.2a bound")
    result = replay_micro_candidate_with_prequalification_context(
        symbol,
        bars,
        trades,
        candidate_qualified_at=candidate_qualified_at,
        spec=context_spec,
        policy=parent_setup_without_hard_volume_gate(),
        vwap_available=vwap_available,
        ema9_available=ema9_available,
        trigger_mode=trigger_mode,
        entry_latency_ms=entry_latency_ms,
        target_price=target_price,
        exit_until=exit_until,
    )
    return MicroVolumeAblationReplay(
        spec=volume_spec,
        replay=result.replay,
        structural_context_start=result.structural_context_start,
        available_prequalification_context_bars=(
            result.available_prequalification_context_bars
        ),
    )


def micro_volume_ablation_runtime_artifact(
    result: MicroVolumeAblationReplay,
) -> dict[str, object]:
    """Serialize one volume-factorial runtime without retrospective labels."""
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
            "require_lower_pullback_volume": False,
            "volume_rule": result.spec.volume_rule,
            "prequalification_context_enabled": (
                result.spec.prequalification_context_enabled
            ),
            "structural_context_bars_requested": result.spec.context_bars,
            "structural_context_bars_available": (
                result.available_prequalification_context_bars
            ),
            "structural_context_start": (
                result.structural_context_start.isoformat()
                if result.structural_context_start is not None
                else None
            ),
            "action_gate": result.spec.action_gate,
        }
    )
    return payload
