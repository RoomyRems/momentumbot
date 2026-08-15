"""Loading and chronology filtering for the evidence-backed rulebook."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Iterable

from .evidence import StrategyRule


def load_rulebook(path: str | Path) -> list[StrategyRule]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Rulebook root must be a JSON list")
    rules = [StrategyRule.from_dict(item) for item in payload]
    ids = [rule.rule_id for rule in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("Rule IDs must be unique")
    return rules


def rules_as_of(rules: Iterable[StrategyRule], as_of: date) -> list[StrategyRule]:
    """Return only rules whose evidence was available by an experiment date.

    A rule with any future-dated evidence is not automatically invalid; the
    important boundary is `applies_from`, which is set by the researcher after
    reviewing when the policy is actually supported. Undated evidence cannot
    establish an applies_from date for chronology-sensitive work.
    """
    return [rule for rule in rules if rule.applies_from and rule.applies_from <= as_of]
