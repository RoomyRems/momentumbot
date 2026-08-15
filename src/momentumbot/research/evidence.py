"""Typed schema for evidence-backed strategy observations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any

_RULE_ID = re.compile(r"^MB-[A-Z]+-[0-9]{3}$")


class ObservationType(str, Enum):
    RULE = "rule"
    PREFERENCE = "preference"
    EXCEPTION = "exception"
    MISTAKE = "mistake_self_critique"
    OBSERVATION = "observation"
    REGIME_ADAPTATION = "market_regime_adaptation"
    RESEARCH_GUARD = "research_guard"


class EvidenceMode(str, Enum):
    NORMATIVE = "normative_teaching"
    BEHAVIORAL = "observed_behavior"
    SELF_CRITIQUE = "self_critique"
    RESEARCH = "research_design"


class DecisionRole(str, Enum):
    DETERMINISTIC = "deterministic"
    AI_CONTEXT = "ai_context"
    MIXED = "mixed"
    RESEARCH_ONLY = "research_only"


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    video_id: str
    title: str
    published_at: date | None
    mode: EvidenceMode
    note: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceRef":
        published = data.get("published_at")
        return cls(
            video_id=str(data["video_id"]),
            title=str(data["title"]),
            published_at=date.fromisoformat(published) if published else None,
            mode=EvidenceMode(data["mode"]),
            note=str(data["note"]),
        )


@dataclass(frozen=True, slots=True)
class StrategyRule:
    rule_id: str
    title: str
    category: str
    statement: str
    observation_type: ObservationType
    decision_role: DecisionRole
    confidence: float
    status: str
    applies_from: date | None = None
    implementation_notes: tuple[str, ...] = ()
    contradictions_or_exceptions: tuple[str, ...] = ()
    evidence: tuple[EvidenceRef, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not _RULE_ID.fullmatch(self.rule_id):
            raise ValueError(f"Invalid rule id: {self.rule_id}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1]: {self.rule_id}")
        if not self.evidence and self.observation_type is not ObservationType.RESEARCH_GUARD:
            raise ValueError(f"Evidence required for strategy rule: {self.rule_id}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StrategyRule":
        applies = data.get("applies_from")
        return cls(
            rule_id=str(data["rule_id"]),
            title=str(data["title"]),
            category=str(data["category"]),
            statement=str(data["statement"]),
            observation_type=ObservationType(data["observation_type"]),
            decision_role=DecisionRole(data["decision_role"]),
            confidence=float(data["confidence"]),
            status=str(data["status"]),
            applies_from=date.fromisoformat(applies) if applies else None,
            implementation_notes=tuple(data.get("implementation_notes", [])),
            contradictions_or_exceptions=tuple(data.get("contradictions_or_exceptions", [])),
            evidence=tuple(EvidenceRef.from_dict(item) for item in data.get("evidence", [])),
        )
