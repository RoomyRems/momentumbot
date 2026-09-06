from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

from .corpus import CorpusRecord
from .evidence import StrategyRule


def _load_payload(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and "rule_files" in payload:
        rows: list[dict] = []
        for relative in payload["rule_files"]:
            child = (path.parent / str(relative)).resolve()
            if path.parent.resolve() not in child.parents:
                raise ValueError("rule manifest paths must stay under the manifest directory")
            child_payload = json.loads(child.read_text(encoding="utf-8"))
            if not isinstance(child_payload, list):
                raise ValueError(f"rule bundle must be a JSON list: {child}")
            rows.extend(child_payload)
        return rows
    raise ValueError("rulebook root must be a JSON list or rule_files manifest")


def load_rulebook(path: str | Path) -> list[StrategyRule]:
    rows = _load_payload(Path(path))
    rules = [StrategyRule.from_dict(item) for item in rows]
    ids = [rule.rule_id for rule in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("rule IDs must be unique")
    return rules


def rules_as_of(rules: Iterable[StrategyRule], as_of: date) -> list[StrategyRule]:
    return [rule for rule in rules if rule.applies_from and rule.applies_from <= as_of]


def validate_evidence_against_corpus(
    rules: Sequence[StrategyRule], records: Sequence[CorpusRecord]
) -> list[str]:
    """Return validation problems without importing transcript text into runtime artifacts."""
    by_id = {record.video_id: record for record in records}
    problems: list[str] = []
    for rule in rules:
        for evidence in rule.evidence:
            record = by_id.get(evidence.video_id)
            if record is None:
                problems.append(f"{rule.rule_id}: missing evidence video {evidence.video_id}")
                continue
            if evidence.published_at != record.published_at:
                problems.append(
                    f"{rule.rule_id}: evidence date mismatch for {evidence.video_id}: "
                    f"rule={evidence.published_at} corpus={record.published_at}"
                )
            if evidence.title != record.title:
                problems.append(f"{rule.rule_id}: evidence title mismatch for {evidence.video_id}")
    return problems
