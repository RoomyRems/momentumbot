"""Versioned immutable policy contract for the deterministic micro baseline.

This module is intentionally boring.  Research experiments may create other
``MicroSetupPolicy`` objects, but backtests that claim to use Micro v0.1 must
resolve the exact policy defined here.  The policy is frozen before broad
benchmarking so later discoveries cannot silently rewrite the baseline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json

from .micro_setup import MicroSetupPolicy, canonical_micro_setup_policy


MICRO_V0_1_POLICY_ID = "micro-v0.1"
MICRO_V0_1_SETUP_FAMILY = "canonical_chart_confirmed_micro_pullback"
MICRO_V0_1_BAR_INTERVAL_SECONDS = 10
MICRO_V0_1_TRIGGER_MODE = "first_new_high_over_previous_completed_micro_bar"
MICRO_V0_1_STOP_MODE = "pullback_low"
MICRO_V0_1_SUPPORT_AVAILABILITY = "completed_minute_only"
MICRO_V0_1_STATUS = "frozen_research_baseline"


@dataclass(frozen=True, slots=True)
class FrozenMicroPolicy:
    policy_id: str
    status: str
    setup_family: str
    micro_bar_interval_seconds: int
    trigger_mode: str
    stop_mode: str
    support_availability: str
    setup: MicroSetupPolicy

    def payload(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "status": self.status,
            "setup_family": self.setup_family,
            "micro_bar_interval_seconds": self.micro_bar_interval_seconds,
            "trigger_mode": self.trigger_mode,
            "stop_mode": self.stop_mode,
            "support_availability": self.support_availability,
            "setup": asdict(self.setup),
        }

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.payload(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def micro_v0_1_policy() -> FrozenMicroPolicy:
    """Return the exact frozen deterministic Micro v0.1 research baseline."""
    return FrozenMicroPolicy(
        policy_id=MICRO_V0_1_POLICY_ID,
        status=MICRO_V0_1_STATUS,
        setup_family=MICRO_V0_1_SETUP_FAMILY,
        micro_bar_interval_seconds=MICRO_V0_1_BAR_INTERVAL_SECONDS,
        trigger_mode=MICRO_V0_1_TRIGGER_MODE,
        stop_mode=MICRO_V0_1_STOP_MODE,
        support_availability=MICRO_V0_1_SUPPORT_AVAILABILITY,
        setup=canonical_micro_setup_policy(),
    )


def micro_v0_1_manifest() -> dict[str, object]:
    policy = micro_v0_1_policy()
    return {**policy.payload(), "fingerprint": policy.fingerprint}
