from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping


SCHEMA_VERSION = 1
CONTRACT_ID = "ross-discretion-context-v0.1"

_RESPONSIBILITIES = {"deterministic", "mixed", "ai_context"}
_IMPLEMENTATION_STATUSES = {
    "implemented_frozen",
    "partial_proxy",
    "partial_feature_only",
    "partial_not_end_to_end",
    "not_implemented",
    "deferred_missing_historical_data",
}
_FORBIDDEN_RUNTIME_TERMS = {
    "benchmark_label",
    "future_outcome",
    "reported_fill",
    "ross_entry",
    "ross_fill",
    "realized_pnl_outcome",
    "winning_trade_label",
}


def canonical_fingerprint(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_nonempty_strings(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty list")
    rows = tuple(str(item).strip() for item in value)
    if any(not item for item in rows):
        raise ValueError(f"{field} entries must be non-empty strings")
    if len(rows) != len(set(rows)):
        raise ValueError(f"{field} entries must be unique")
    return rows


def validate_discretion_context_contract(
    payload: Mapping[str, object],
    *,
    known_rule_ids: Iterable[str] | None = None,
) -> None:
    """Validate the research boundary without enabling a strategy decision.

    This contract inventories context that may explain Ross Cameron-style
    selection and participation. It intentionally cannot produce a candidate,
    setup, order, position size, or risk override.
    """

    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported discretion-context schema")
    if payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected discretion-context contract ID")
    if payload.get("artifact_type") != "research_discretion_context_coverage_contract":
        raise ValueError("unexpected discretion-context artifact type")
    if payload.get("runtime_strategy_effect") != "none":
        raise ValueError("the discretion-context contract must not affect runtime strategy")
    if payload.get("policy_promotion_eligible") is not False:
        raise ValueError("the discretion-context contract is not policy-promotion eligible")
    if payload.get("full_imitation_claim_eligible") is not False:
        raise ValueError("the incomplete context inventory cannot support an imitation claim")

    knowledge = payload.get("knowledge_policy")
    if not isinstance(knowledge, Mapping):
        raise ValueError("knowledge_policy must be an object")
    required_guards = {
        "runtime_inputs_available_by_decision_time": True,
        "raw_transcripts_allowed_at_runtime": False,
        "retrospective_behavior_labels_allowed_at_runtime": False,
        "ai_may_submit_orders": False,
        "ai_may_raise_deterministic_risk": False,
    }
    for field, expected in required_guards.items():
        if knowledge.get(field) is not expected:
            raise ValueError(f"knowledge_policy.{field} must be {expected}")

    domains = payload.get("domains")
    if not isinstance(domains, list) or not domains:
        raise ValueError("domains must be a non-empty list")

    expected_rule_ids = set(known_rule_ids) if known_rule_ids is not None else None
    domain_ids: set[str] = set()
    has_frozen_technical_anchor = False
    has_unimplemented_required_context = False

    for row in domains:
        if not isinstance(row, Mapping):
            raise ValueError("each domain must be an object")
        domain_id = str(row.get("domain_id", "")).strip()
        if not domain_id or domain_id in domain_ids:
            raise ValueError("domain IDs must be non-empty and unique")
        domain_ids.add(domain_id)

        responsibility = row.get("responsibility")
        if responsibility not in _RESPONSIBILITIES:
            raise ValueError(f"invalid responsibility for {domain_id}")
        status = row.get("implementation_status")
        if status not in _IMPLEMENTATION_STATUSES:
            raise ValueError(f"invalid implementation status for {domain_id}")

        stages = _require_nonempty_strings(row.get("decision_stages"), f"{domain_id}.decision_stages")
        rule_ids = _require_nonempty_strings(row.get("linked_rule_ids"), f"{domain_id}.linked_rule_ids")
        runtime_inputs = _require_nonempty_strings(
            row.get("causal_runtime_inputs"), f"{domain_id}.causal_runtime_inputs"
        )
        _require_nonempty_strings(row.get("evidence_needed"), f"{domain_id}.evidence_needed")

        if expected_rule_ids is not None:
            unknown = set(rule_ids) - expected_rule_ids
            if unknown:
                raise ValueError(f"{domain_id} links unknown rule IDs: {sorted(unknown)}")

        normalized_inputs = {item.lower().replace("-", "_").replace(" ", "_") for item in runtime_inputs}
        forbidden = normalized_inputs & _FORBIDDEN_RUNTIME_TERMS
        if forbidden:
            raise ValueError(f"{domain_id} contains retrospective runtime inputs: {sorted(forbidden)}")

        required = row.get("required_for_full_imitation_claim")
        if required is not True:
            raise ValueError(f"{domain_id} must state whether it is required for full imitation")
        if not str(row.get("current_limit", "")).strip():
            raise ValueError(f"{domain_id}.current_limit is required")
        if not str(row.get("promotion_gate", "")).strip():
            raise ValueError(f"{domain_id}.promotion_gate is required")

        if status == "implemented_frozen":
            has_frozen_technical_anchor = has_frozen_technical_anchor or "entry" in stages
        else:
            has_unimplemented_required_context = True
            if row.get("full_domain_strategy_gate_enabled") is not False:
                raise ValueError(f"incomplete domain {domain_id} must remain fail-closed")

        if responsibility in {"ai_context", "mixed"} and row.get("ai_mode") != "shadow_only":
            raise ValueError(f"contextual domain {domain_id} must keep AI shadow-only")

    if not has_frozen_technical_anchor:
        raise ValueError("the inventory must retain the frozen technical-entry anchor")
    if not has_unimplemented_required_context:
        raise ValueError("an incomplete research contract must identify missing context")


def load_discretion_context_contract(
    path: str | Path,
    *,
    known_rule_ids: Iterable[str] | None = None,
) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("discretion-context root must be an object")
    validate_discretion_context_contract(payload, known_rule_ids=known_rule_ids)
    return payload


def coverage_summary(payload: Mapping[str, object]) -> dict[str, int]:
    validate_discretion_context_contract(payload)
    counts: dict[str, int] = {}
    for row in payload["domains"]:  # type: ignore[index]
        status = str(row["implementation_status"])
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))
