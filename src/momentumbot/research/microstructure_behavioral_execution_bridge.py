"""Threshold-free bridge from sanitized behavior to prospective execution.

The bridge is deliberately provider-inert. It forms the complete Cartesian
product of the three frozen behavioral horizons and the two frozen execution
scenarios, while retaining each execution cell as pending until causal quote,
halt, and account inputs exist. It cannot score, rank, select, or trade.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from momentumbot.research.execution_realism import (
    CONTRACT_CONTENT_SHA256 as PROSPECTIVE_EXECUTION_CONTENT_SHA256,
    CONTRACT_ID as PROSPECTIVE_EXECUTION_CONTRACT_ID,
    validate_prospective_execution_contract,
)
from momentumbot.research.microstructure_contract import canonical_fingerprint


SCHEMA_VERSION = 1
CONTRACT_ID = "microstructure-behavioral-execution-bridge-v0.1"
CONTRACT_CONTENT_SHA256 = (
    "fcafc556b20267a966ed228658a5da8daef2ed58955cf7d981c053acf8491411"
)
BEHAVIORAL_SUCCESS_AUDIT_CONTENT_SHA256 = (
    "f1544b5a0d83e28d5b013b5dba64a9c806fefe7ab81dc614be67223dea908b22"
)
BEHAVIORAL_SUCCESS_RUN_ID = 32575593240
BEHAVIORAL_SUCCESS_HEAD_SHA = "0687093a778bd6ac0973889e788886df8cd48cbf"
PUBLISHED_SUCCESS_CHECKPOINT_SHA = "1b67dae2ff39b7942ec8f968dd50dff3ed81aa51"
HORIZONS_NS = (1_000_000_000, 5_000_000_000, 10_000_000_000)
EXECUTION_SCENARIO_IDS = ("l1-conservative-v0.1", "l1-stress-v0.1")
PENDING_EXECUTION_STATUS = "pending_causal_top_of_book_and_halt_states"


def _load_object(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def _validate_fingerprint(
    payload: Mapping[str, object],
    *,
    expected: str,
    label: str,
) -> None:
    claimed = payload.get("content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if claimed != expected or canonical_fingerprint(unsigned) != expected:
        raise ValueError(f"{label} content fingerprint changed")


def validate_bridge_contract(payload: Mapping[str, object]) -> None:
    expected_scalars = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "artifact_type": (
            "preregistered_unarmed_threshold_free_behavioral_execution_bridge"
        ),
        "registration_status": (
            "registered_after_behavioral_cohort_success_before_prospective_panel"
        ),
        "runtime_strategy_effect": "none_shadow_only",
    }
    for field, expected in expected_scalars.items():
        if payload.get(field) != expected:
            raise ValueError(f"bridge contract {field} changed")
    _validate_fingerprint(
        payload,
        expected=CONTRACT_CONTENT_SHA256,
        label="bridge contract",
    )

    parents = payload.get("frozen_parents")
    if not isinstance(parents, Mapping):
        raise ValueError("bridge frozen parents are required")
    expected_parents = {
        "behavioral_success_audit_content_sha256": (
            BEHAVIORAL_SUCCESS_AUDIT_CONTENT_SHA256
        ),
        "behavioral_success_workflow_run_id": BEHAVIORAL_SUCCESS_RUN_ID,
        "behavioral_success_workflow_attempt": 1,
        "behavioral_success_head_sha": BEHAVIORAL_SUCCESS_HEAD_SHA,
        "published_success_checkpoint_sha": PUBLISHED_SUCCESS_CHECKPOINT_SHA,
        "prospective_execution_contract_id": PROSPECTIVE_EXECUTION_CONTRACT_ID,
        "prospective_execution_contract_content_sha256": (
            PROSPECTIVE_EXECUTION_CONTENT_SHA256
        ),
    }
    for field, expected in expected_parents.items():
        if parents.get(field) != expected:
            raise ValueError(f"bridge frozen parent {field} changed")

    matrix = payload.get("readiness_matrix")
    if not isinstance(matrix, Mapping):
        raise ValueError("bridge readiness matrix is required")
    if matrix.get("horizons_ns") != list(HORIZONS_NS):
        raise ValueError("bridge must retain every frozen horizon")
    if matrix.get("execution_scenario_ids") != list(EXECUTION_SCENARIO_IDS):
        raise ValueError("bridge must retain both frozen execution scenarios")
    required_matrix_values = {
        "complete_cartesian_product_required": True,
        "expected_cell_count": 6,
        "all_horizons_reported_together": True,
        "both_execution_scenarios_reported_together": True,
        "best_horizon_selection_allowed": False,
        "best_execution_scenario_selection_allowed": False,
        "score_or_rank_allowed": False,
        "pending_execution_status": PENDING_EXECUTION_STATUS,
    }
    for field, expected in required_matrix_values.items():
        if matrix.get(field) != expected:
            raise ValueError(f"bridge readiness matrix {field} changed")

    knowledge = payload.get("knowledge_boundary")
    authority = payload.get("authority_boundary")
    future = payload.get("future_input_gate")
    if not all(isinstance(value, Mapping) for value in (knowledge, authority, future)):
        raise ValueError("bridge knowledge, authority, and future gates are required")
    if knowledge.get("sanitized_cohort_aggregate_allowed") is not True:
        raise ValueError("bridge requires the sanitized cohort aggregate")
    for field in (
        "per_opportunity_feature_values_allowed",
        "raw_market_data_allowed",
        "ross_actions_labels_or_recaps_allowed",
        "later_prices_or_pnl_allowed",
        "prospective_execution_outcomes_available_at_registration",
        "behavioral_values_may_select_execution_assumptions",
    ):
        if knowledge.get(field) is not False:
            raise ValueError(f"bridge knowledge boundary {field} must be false")
    for field in (
        "provider_request_authorized",
        "provider_purchase_authorized",
        "broker_order_authorized",
        "paper_order_authorized",
        "live_order_authorized",
        "runtime_authority_created",
        "feature_threshold_selection_authorized",
        "execution_scenario_selection_authorized",
        "policy_promotion_eligible",
        "profitability_claim_eligible",
    ):
        if authority.get(field) is not False:
            raise ValueError(f"bridge authority boundary {field} must be false")
    if authority.get("databento_credit_authorized_usd") != "0":
        raise ValueError("bridge cannot authorize Databento credit")
    if future.get("sip_print_proxy_fallback_allowed") is not False:
        raise ValueError("bridge cannot fall back to the SIP print proxy")
    if future.get("same_opportunity_inputs_required_for_both_scenarios") is not True:
        raise ValueError("both scenarios require identical opportunity inputs")


def load_bridge_contract(path: str | Path) -> dict[str, object]:
    payload = _load_object(path)
    validate_bridge_contract(payload)
    return payload


def validate_behavioral_success_audit(payload: Mapping[str, object]) -> None:
    _validate_fingerprint(
        payload,
        expected=BEHAVIORAL_SUCCESS_AUDIT_CONTENT_SHA256,
        label="behavioral success audit",
    )
    actions = payload.get("github_actions")
    attempt = payload.get("verified_preflight_and_attempt")
    aggregate = payload.get("verified_cohort_aggregate")
    safety = payload.get("safety_verification")
    if not all(isinstance(value, Mapping) for value in (actions, attempt, aggregate, safety)):
        raise ValueError("behavioral success audit shape changed")
    if (
        actions.get("workflow_run_id") != BEHAVIORAL_SUCCESS_RUN_ID
        or actions.get("workflow_run_attempt") != 1
        or actions.get("workflow_head_sha") != BEHAVIORAL_SUCCESS_HEAD_SHA
        or actions.get("workflow_conclusion") != "success"
    ):
        raise ValueError("behavioral success workflow identity changed")
    if (
        attempt.get("request_count_quoted") != 5
        or attempt.get("timeseries_request_count") != 5
        or attempt.get("successful_download_summary_count") != 5
        or attempt.get("automatic_retry_attempted") is not False
    ):
        raise ValueError("behavioral success attempt changed")
    if (
        aggregate.get("opportunity_count") != 10
        or aggregate.get("horizon_count") != 3
        or aggregate.get("all_horizons_reported_together") is not True
        or aggregate.get("independent_feature_replay_exact") is not True
        or aggregate.get("feature_horizon_selected") is not False
        or aggregate.get("feature_threshold_selected") is not False
        or aggregate.get("policy_promotion_eligible") is not False
    ):
        raise ValueError("behavioral cohort aggregate changed")
    if (
        safety.get("raw_market_data_persisted") is not False
        or safety.get("per_opportunity_feature_values_persisted") is not False
        or safety.get("retrospective_labels_loaded") is not False
        or safety.get("runtime_authority_created") is not False
    ):
        raise ValueError("behavioral success safety boundary changed")


def load_behavioral_success_audit(path: str | Path) -> dict[str, object]:
    payload = _load_object(path)
    validate_behavioral_success_audit(payload)
    return payload


def load_prospective_contract(path: str | Path) -> dict[str, object]:
    payload = _load_object(path)
    validate_prospective_execution_contract(payload)
    return payload


def _rows_by_horizon(
    rows: object,
    *,
    label: str,
) -> dict[int, dict[str, object]]:
    if not isinstance(rows, list):
        raise ValueError(f"{label} rows are required")
    result: dict[int, dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError(f"{label} row must be an object")
        horizon = row.get("horizon_ns")
        if horizon not in HORIZONS_NS or horizon in result:
            raise ValueError(f"{label} horizons changed")
        result[int(horizon)] = dict(row)
    if tuple(result) != HORIZONS_NS:
        raise ValueError(f"{label} must retain ordered frozen horizons")
    return result


def build_behavioral_execution_bridge(
    contract: Mapping[str, object],
    success_audit: Mapping[str, object],
    prospective_contract: Mapping[str, object],
) -> dict[str, object]:
    """Build the six-cell pending matrix without market or outcome inputs."""
    validate_bridge_contract(contract)
    validate_behavioral_success_audit(success_audit)
    validate_prospective_execution_contract(prospective_contract)

    aggregate = success_audit["verified_cohort_aggregate"]
    assert isinstance(aggregate, Mapping)
    metric_rows = _rows_by_horizon(
        aggregate.get("metric_direction_totals_by_horizon"),
        label="metric direction totals",
    )
    depth_rows = _rows_by_horizon(
        aggregate.get("depth_walk_direction_totals_by_horizon"),
        label="depth-walk direction totals",
    )
    scenario_rows = prospective_contract.get("execution_scenarios")
    if not isinstance(scenario_rows, list):
        raise ValueError("prospective execution scenarios are required")
    scenarios = {
        row.get("policy_id"): dict(row)
        for row in scenario_rows
        if isinstance(row, Mapping)
    }
    if tuple(scenarios) != EXECUTION_SCENARIO_IDS:
        raise ValueError("prospective execution scenario order changed")

    cells: list[dict[str, object]] = []
    for horizon in HORIZONS_NS:
        for scenario_id in EXECUTION_SCENARIO_IDS:
            cells.append(
                {
                    "horizon_ns": horizon,
                    "execution_scenario_id": scenario_id,
                    "execution_assumptions": scenarios[scenario_id],
                    "behavioral_metric_direction_totals": metric_rows[horizon],
                    "behavioral_depth_walk_direction_totals": depth_rows[horizon],
                    "prospective_execution_status": PENDING_EXECUTION_STATUS,
                    "comparable_execution_outcome_available": False,
                }
            )

    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": "microstructure-behavioral-execution-bridge-v0.1-readiness",
        "artifact_type": "threshold_free_shadow_behavioral_execution_readiness_matrix",
        "contract_id": CONTRACT_ID,
        "contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "behavioral_success_audit_content_sha256": (
            BEHAVIORAL_SUCCESS_AUDIT_CONTENT_SHA256
        ),
        "prospective_execution_contract_content_sha256": (
            PROSPECTIVE_EXECUTION_CONTENT_SHA256
        ),
        "source_cohort": {
            "opportunity_count": aggregate["opportunity_count"],
            "comparison_sequence_digest_sha256": aggregate[
                "comparison_sequence_digest_sha256"
            ],
            "sanitized_aggregate_only": True,
            "per_opportunity_feature_values_loaded": False,
        },
        "matrix": {
            "horizons_ns": list(HORIZONS_NS),
            "execution_scenario_ids": list(EXECUTION_SCENARIO_IDS),
            "cell_count": len(cells),
            "cells": cells,
        },
        "provider_request_made": False,
        "broker_order_submitted": False,
        "retrospective_labels_loaded": False,
        "threshold_or_score_applied": False,
        "horizon_or_scenario_selected": False,
        "runtime_authority": "none_shadow_only",
        "policy_promotion_eligible": False,
        "profitability_claim_eligible": False,
    }
    report["content_sha256"] = canonical_fingerprint(report)
    return report
