from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Mapping

from momentumbot.research.discretion_heldout_panel import (
    ACCOUNT_SCOPES,
    EVIDENCE_TIMING_QUALITIES,
    HUMAN_ACTION_STATES,
)


SCHEMA_VERSION = 1
CONTRACT_ID = "ross-context-heldout-panel-v0.1"
CONTEXT_CONTRACT_ID = "discretion-context-assessment-shadow-v0.1"
CONTEXT_CONTRACT_CONTENT_SHA256 = (
    "8205772680ce290d58de1d17fbe43d02c2beb21fd9f0e16d8bd2c7b3a1806f26"
)
EXCLUDED_PILOT_PANEL_ID = "ross-discretion-heldout-panel-v0.1"
EXCLUDED_PILOT_COMPARISON_ID = "ross-discretion-heldout-comparison-v0.1"
EXCLUDED_PILOT_COMPARISON_SHA256 = (
    "809d4b4a7231b708f9c933c9bf45b58c736f4d3101c8328483c62c1c48bcfb3d"
)
PRIOR_REVIEW_CUTOFF = date(2026, 7, 23)
REGISTERED_DATES = (
    "2026-07-24",
    "2026-07-27",
    "2026-07-28",
    "2026-07-29",
    "2026-07-30",
    "2026-07-31",
    "2026-08-03",
    "2026-08-04",
    "2026-08-05",
    "2026-08-06",
)
WORKFLOW_SEQUENCE = (
    "freeze_calendar_only_date_registration_before_source_inventory_or_review",
    "build_and_validate_deterministic_context_sources_label_blind",
    "freeze_hash_bound_context_snapshots_for_all_causal_market_candidates",
    "run_optional_semantic_assessments_shadow_only_with_abstention",
    "freeze_and_hash_all_runtime_and_shadow_artifacts",
    "inventory_and_review_same_day_human_evidence_without_replacing_dates",
    "freeze_retrospective_account_scoped_trade_skip_or_unknown_labels",
    "compare_components_without_threshold_fitting_or_policy_promotion",
)

_EXPECTED_SESSION_SEQUENCE = tuple(date.fromisoformat(value) for value in REGISTERED_DATES)
_FORBIDDEN_REGISTRATION_KEYS = {
    "benchmark_label",
    "entry_price",
    "human_action",
    "observed_human_behavior",
    "realized_pnl",
    "reported_fill",
    "ross_action",
    "skip_label",
    "source_id",
    "source_title",
    "trade_outcome",
    "trade_taken",
    "transcript_text",
}


def canonical_fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _walk_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_walk_keys(child))
    return keys


def _mapping(payload: Mapping[str, object], field: str) -> Mapping[str, object]:
    value = payload.get(field)
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _exact_list(value: object, expected: tuple[str, ...], field: str) -> None:
    if value != list(expected):
        raise ValueError(f"{field} differs from the frozen context panel")


def validate_context_heldout_panel_contract(payload: Mapping[str, object]) -> None:
    """Validate the calendar-only registration before any source review."""

    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported context held-out panel schema")
    if payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected context held-out panel ID")
    if payload.get("artifact_type") != "chronological_context_panel_registration":
        raise ValueError("unexpected context panel artifact type")
    if payload.get("registration_status") != "registered_unlabeled_uninventoried":
        raise ValueError("context panel must remain unlabeled and uninventoried")
    if payload.get("panel_kind") != "context_protocol_pilot_not_representative":
        raise ValueError("context panel must remain explicitly non-representative")
    if payload.get("runtime_strategy_effect") != "none":
        raise ValueError("context panel registration cannot affect runtime")
    for field in (
        "policy_promotion_eligible",
        "full_imitation_claim_eligible",
        "selection_threshold_frozen",
        "label_content_review_started",
        "source_inventory_started",
        "source_content_opened_for_date_selection",
        "dates_may_be_replaced",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must be false")

    forbidden = _walk_keys(payload) & _FORBIDDEN_REGISTRATION_KEYS
    if forbidden:
        raise ValueError(
            f"context panel contains source or retrospective keys: {sorted(forbidden)}"
        )

    parent = _mapping(payload, "parent_protocol")
    if dict(parent) != {
        "contract_id": CONTEXT_CONTRACT_ID,
        "content_sha256": CONTEXT_CONTRACT_CONTENT_SHA256,
        "semantic_model_frozen": False,
        "aggregate_score_frozen": False,
        "selection_threshold_frozen": False,
    }:
        raise ValueError("context panel parent binding differs from the protocol")

    sampling = _mapping(payload, "sampling_contract")
    if sampling.get("prior_review_cutoff") != PRIOR_REVIEW_CUTOFF.isoformat():
        raise ValueError("prior review cutoff differs from the context panel")
    _exact_list(sampling.get("registered_dates"), REGISTERED_DATES, "registered_dates")
    if sampling.get("selection_rule") != (
        "first_ten_verified_us_equity_sessions_strictly_after_prior_review_cutoff"
    ):
        raise ValueError("unexpected context panel selection rule")
    expected_sampling_guards = {
        "date_selection_uses_source_inventory": False,
        "date_selection_uses_source_content": False,
        "date_selection_uses_symbols": False,
        "date_selection_uses_ross_actions": False,
        "date_selection_uses_trade_outcomes": False,
        "date_selection_uses_pnl": False,
        "missing_source_date_replaced": False,
        "all_causal_market_candidates_retained": True,
        "top_n_or_rank_filter_applied": False,
        "session_calendar_verified": True,
    }
    for field, expected in expected_sampling_guards.items():
        if sampling.get(field) is not expected:
            raise ValueError(f"sampling_contract.{field} must be {expected}")
    try:
        sessions = tuple(date.fromisoformat(str(value)) for value in sampling["registered_dates"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("registered dates must be ISO calendar dates") from exc
    if sessions != _EXPECTED_SESSION_SEQUENCE:
        raise ValueError("registered session sequence differs from the frozen panel")
    if any(value <= PRIOR_REVIEW_CUTOFF for value in sessions):
        raise ValueError("every context panel date must follow the review cutoff")
    if any(value.weekday() >= 5 for value in sessions):
        raise ValueError("context panel dates must be weekdays")

    excluded = _mapping(payload, "excluded_fit_evidence")
    if dict(excluded) != {
        "panel_id": EXCLUDED_PILOT_PANEL_ID,
        "comparison_id": EXCLUDED_PILOT_COMPARISON_ID,
        "comparison_content_sha256": EXCLUDED_PILOT_COMPARISON_SHA256,
        "threshold_fit_allowed": False,
        "protocol_evaluation_allowed": False,
    }:
        raise ValueError("excluded pilot binding differs from the context panel")

    human = _mapping(payload, "human_evidence_policy")
    _exact_list(human.get("action_states"), HUMAN_ACTION_STATES, "action_states")
    _exact_list(human.get("account_scopes"), ACCOUNT_SCOPES, "account_scopes")
    _exact_list(
        human.get("evidence_timing_qualities"),
        EVIDENCE_TIMING_QUALITIES,
        "evidence_timing_qualities",
    )
    expected_human_guards = {
        "not_mentioned_counts_as_skip": False,
        "source_unavailable_counts_as_skip": False,
        "small_and_main_accounts_may_be_merged": False,
        "raw_transcript_allowed_in_runtime": False,
        "labels_created_only_after_runtime_hash_freeze": True,
        "date_replacement_after_source_review": False,
    }
    for field, expected in expected_human_guards.items():
        if human.get(field) is not expected:
            raise ValueError(f"human_evidence_policy.{field} must be {expected}")

    causal = _mapping(payload, "causal_separation")
    expected_causal = {
        "runtime_inputs_available_by_decision_time": True,
        "daily_context_uses_only_prior_completed_sessions": True,
        "theme_context_uses_only_current_or_prior_market_state": True,
        "runtime_and_shadow_artifacts_frozen_before_label_review": True,
        "retrospective_labels_allowed_in_runtime": False,
        "later_price_or_outcome_allowed_in_runtime": False,
        "label_artifact_stored_separately": True,
    }
    for field, expected in expected_causal.items():
        if causal.get(field) is not expected:
            raise ValueError(f"causal_separation.{field} must be {expected}")

    _exact_list(payload.get("workflow_sequence"), WORKFLOW_SEQUENCE, "workflow_sequence")

    evaluation = _mapping(payload, "evaluation_contract")
    expected_evaluation = {
        "component_thresholds_may_be_fit_on_panel": False,
        "technical_rules_may_be_retuned_on_panel": False,
        "aggregate_context_score_allowed": False,
        "overall_imitation_score_allowed": False,
        "policy_promotion_allowed": False,
        "unknown_actions_excluded_from_trade_skip_accuracy": True,
        "coverage_and_abstention_reported": True,
        "account_scopes_reported_separately": True,
        "provider_failures_and_missing_domains_reported": True,
    }
    for field, expected in expected_evaluation.items():
        if evaluation.get(field) is not expected:
            raise ValueError(f"evaluation_contract.{field} must be {expected}")

    status = _mapping(payload, "execution_status")
    if dict(status) != {
        "deterministic_runtime": "not_started",
        "semantic_shadow": "not_started",
        "source_inventory": "not_started",
        "human_label_review": "not_started",
        "runtime_artifact_sha256": None,
        "semantic_shadow_artifact_sha256": None,
        "label_artifact_sha256": None,
    }:
        raise ValueError("context panel execution status must remain not started")


def load_context_heldout_panel_contract(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("context held-out panel root must be an object")
    validate_context_heldout_panel_contract(payload)
    return payload
