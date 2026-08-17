from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Mapping


SCHEMA_VERSION = 1
CONTRACT_ID = "ross-discretion-heldout-panel-v0.1"
DEVELOPMENT_EVIDENCE_CUTOFF = date(2026, 7, 9)
REGISTERED_DATES = (
    "2026-07-10",
    "2026-07-13",
    "2026-07-14",
    "2026-07-15",
    "2026-07-16",
    "2026-07-17",
    "2026-07-20",
    "2026-07-21",
    "2026-07-22",
    "2026-07-23",
)

WORKFLOW_SEQUENCE = (
    "freeze_date_registration_without_source_content_or_behavior_labels",
    "run_label_blind_market_and_context_replay_for_every_registered_date",
    "freeze_and_hash_runtime_artifacts",
    "locate_and_review_same_day_human_evidence_without_replacing_dates",
    "freeze_retrospective_account_scoped_trade_skip_or_unknown_labels",
    "compare_frozen_runtime_with_labels_and_report_missingness_and_activity",
)

HUMAN_ACTION_STATES = (
    "participated",
    "explicitly_skipped_or_rejected",
    "discussed_but_action_unclear",
    "not_mentioned_or_unobservable",
    "source_unavailable",
)
ACCOUNT_SCOPES = (
    "main_account",
    "small_account",
    "both_accounts_separately_observed",
    "account_scope_unknown",
)
EVIDENCE_TIMING_QUALITIES = (
    "market_clock_synchronized",
    "bounded_by_causal_market_events",
    "retrospective_sequence_only",
    "timing_unresolved",
)
CONTEXT_DOMAINS = (
    "technical_setup_and_trigger",
    "catalyst_substance",
    "attention_leadership",
    "daily_chart_context",
    "market_regime_and_theme",
    "liquidity_and_fill_quality",
    "level2_and_tape",
    "session_state_and_aggression",
)

_FORBIDDEN_REGISTRATION_KEYS = {
    "ross_action",
    "human_action",
    "trade_taken",
    "skip_label",
    "entry_price",
    "reported_fill",
    "realized_pnl",
    "observed_human_behavior",
    "observed_human_decision_context",
}


def canonical_fingerprint(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_mapping(payload: Mapping[str, object], field: str) -> Mapping[str, object]:
    value = payload.get(field)
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _require_exact_list(value: object, expected: tuple[str, ...], field: str) -> None:
    if value != list(expected):
        raise ValueError(f"{field} differs from the frozen held-out contract")


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


def validate_discretion_heldout_panel_contract(payload: Mapping[str, object]) -> None:
    """Validate an unlabeled chronological panel registration.

    The registration freezes dates and evaluation boundaries. It deliberately
    contains no Ross action, fill, outcome, or transcript-derived label.
    """

    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported discretion held-out panel schema")
    if payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected discretion held-out panel contract ID")
    if payload.get("artifact_type") != "chronological_heldout_panel_registration":
        raise ValueError("unexpected discretion held-out panel artifact type")
    if payload.get("registration_status") != "registered_unlabeled":
        raise ValueError("held-out panel must remain registered and unlabeled")
    if payload.get("panel_kind") != "pilot_not_representative":
        raise ValueError("v0.1 must remain an explicitly non-representative pilot")
    if payload.get("runtime_strategy_effect") != "none":
        raise ValueError("held-out registration must not affect runtime strategy")
    for field in (
        "policy_promotion_eligible",
        "full_imitation_claim_eligible",
        "selection_threshold_frozen",
        "label_content_review_started",
        "source_content_opened_for_date_selection",
        "dates_may_be_replaced",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must be false")

    forbidden = _walk_keys(payload) & _FORBIDDEN_REGISTRATION_KEYS
    if forbidden:
        raise ValueError(f"registration contains retrospective label keys: {sorted(forbidden)}")

    sampling = _require_mapping(payload, "sampling_contract")
    if sampling.get("development_evidence_cutoff") != DEVELOPMENT_EVIDENCE_CUTOFF.isoformat():
        raise ValueError("development evidence cutoff differs from the frozen contract")
    _require_exact_list(sampling.get("registered_dates"), REGISTERED_DATES, "registered_dates")
    if sampling.get("selection_rule") != (
        "first_ten_registered_us_equity_sessions_strictly_after_development_evidence_cutoff"
    ):
        raise ValueError("unexpected held-out date selection rule")
    required_sampling_guards = {
        "date_selection_uses_symbols": False,
        "date_selection_uses_ross_actions": False,
        "date_selection_uses_trade_outcomes": False,
        "date_selection_uses_pnl": False,
        "missing_source_date_replaced": False,
        "all_causal_market_candidates_retained": True,
        "top_n_or_rank_filter_applied": False,
        "session_calendar_must_be_verified_before_runtime": True,
    }
    for field, expected in required_sampling_guards.items():
        if sampling.get(field) is not expected:
            raise ValueError(f"sampling_contract.{field} must be {expected}")

    development_dates = sampling.get("development_benchmark_dates")
    if not isinstance(development_dates, list) or not development_dates:
        raise ValueError("development benchmark dates must be a non-empty list")
    if len(development_dates) != len(set(development_dates)):
        raise ValueError("development benchmark dates must be unique")
    try:
        parsed_development = [date.fromisoformat(str(item)) for item in development_dates]
        parsed_panel = [date.fromisoformat(item) for item in REGISTERED_DATES]
    except ValueError as exc:
        raise ValueError("panel dates must use ISO calendar dates") from exc
    if max(parsed_development) != DEVELOPMENT_EVIDENCE_CUTOFF:
        raise ValueError("development benchmark dates must end at the evidence cutoff")
    if any(item <= DEVELOPMENT_EVIDENCE_CUTOFF for item in parsed_panel):
        raise ValueError("every held-out date must follow the development cutoff")
    if any(item.weekday() >= 5 for item in parsed_panel):
        raise ValueError("registered held-out dates must be weekdays")
    if set(parsed_development) & set(parsed_panel):
        raise ValueError("held-out dates must be disjoint from development benchmarks")

    source_policy = _require_mapping(payload, "human_evidence_policy")
    _require_exact_list(source_policy.get("action_states"), HUMAN_ACTION_STATES, "action_states")
    _require_exact_list(source_policy.get("account_scopes"), ACCOUNT_SCOPES, "account_scopes")
    _require_exact_list(
        source_policy.get("evidence_timing_qualities"),
        EVIDENCE_TIMING_QUALITIES,
        "evidence_timing_qualities",
    )
    required_source_guards = {
        "not_mentioned_counts_as_skip": False,
        "source_unavailable_counts_as_skip": False,
        "small_and_main_accounts_may_be_merged": False,
        "raw_transcript_allowed_in_runtime": False,
        "labels_created_only_after_runtime_hash_freeze": True,
        "date_replacement_after_source_review": False,
    }
    for field, expected in required_source_guards.items():
        if source_policy.get(field) is not expected:
            raise ValueError(f"human_evidence_policy.{field} must be {expected}")

    separation = _require_mapping(payload, "causal_separation")
    required_separation = {
        "runtime_inputs_available_by_decision_time": True,
        "runtime_artifact_frozen_before_label_review": True,
        "retrospective_labels_allowed_in_runtime": False,
        "later_price_or_outcome_allowed_in_runtime": False,
        "label_artifact_stored_separately": True,
    }
    for field, expected in required_separation.items():
        if separation.get(field) is not expected:
            raise ValueError(f"causal_separation.{field} must be {expected}")

    _require_exact_list(payload.get("workflow_sequence"), WORKFLOW_SEQUENCE, "workflow_sequence")

    evaluation = _require_mapping(payload, "evaluation_contract")
    _require_exact_list(evaluation.get("context_domains"), CONTEXT_DOMAINS, "context_domains")
    required_evaluation_guards = {
        "unknown_actions_excluded_from_trade_skip_accuracy": True,
        "coverage_and_unknown_rate_reported": True,
        "account_scopes_reported_separately": True,
        "activity_density_reported": True,
        "component_thresholds_may_be_fit_on_panel": False,
        "technical_rules_may_be_retuned_on_panel": False,
        "overall_imitation_score_allowed": False,
        "requires_at_least_one_explicit_trade_and_one_explicit_skip_for_behavior_comparison": True,
    }
    for field, expected in required_evaluation_guards.items():
        if evaluation.get(field) is not expected:
            raise ValueError(f"evaluation_contract.{field} must be {expected}")

    status = _require_mapping(payload, "execution_status")
    if status.get("runtime_replay") != "not_started":
        raise ValueError("registered contract must precede runtime replay")
    if status.get("human_label_review") != "not_started":
        raise ValueError("registered contract must precede label review")
    if status.get("runtime_artifact_sha256") is not None:
        raise ValueError("unrun registration cannot claim a runtime artifact")
    if status.get("label_artifact_sha256") is not None:
        raise ValueError("unlabeled registration cannot claim a label artifact")


def load_discretion_heldout_panel_contract(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("discretion held-out panel root must be an object")
    validate_discretion_heldout_panel_contract(payload)
    return payload
