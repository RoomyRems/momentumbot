from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Mapping

from momentumbot.research.discretion_heldout_labels import (
    ACCOUNT_KEYS,
    HUMAN_ACTION_STATES,
)
from momentumbot.research.discretion_heldout_panel import (
    REGISTERED_DATES,
    canonical_fingerprint,
)


SCHEMA_VERSION = 1
ARTIFACT_ID = "ross-discretion-heldout-comparison-v0.1"
ARTIFACT_TYPE = "retrospective_component_alignment_diagnostic"
COMPARABLE_STATES = {"participated", "explicitly_skipped_or_rejected"}
EXPLICIT_STATES = COMPARABLE_STATES | {"discussed_but_action_unclear"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _require_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _technical_relation(state: str, filled_count: int | None) -> str:
    if state not in COMPARABLE_STATES:
        return "excluded_unclear_or_unknown"
    if filled_count is None:
        return "runtime_unavailable"
    has_fill = filled_count > 0
    if state == "participated":
        return "modeled_fill_on_participation" if has_fill else "no_modeled_fill_on_participation"
    return "modeled_fill_on_explicit_skip" if has_fill else "no_modeled_fill_on_explicit_skip"


def _median(values: list[int]) -> float | None:
    return float(median(values)) if values else None


def _validate_human_state_and_completion(row: Mapping[str, object]) -> None:
    state = row.get("human_state")
    completion = row.get("trade_completion")
    if state not in EXPLICIT_STATES:
        raise ValueError("comparison row must contain an explicit human state")
    if state == "participated" and completion != "completed_trade":
        raise ValueError("comparison participation requires a completed trade")
    if state == "explicitly_skipped_or_rejected" and completion != "no_trade":
        raise ValueError("comparison skip requires no_trade")
    if state == "discussed_but_action_unclear" and completion not in {
        "attempted_no_fill",
        "unknown",
    }:
        raise ValueError("comparison unclear action has inconsistent completion")


def _comparison_aggregates(
    decisions: list[dict[str, object]],
    off_candidate_decisions: list[dict[str, object]],
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    technical_counts: dict[str, object] = {
        account: {
            "modeled_fill_on_participation": 0,
            "no_modeled_fill_on_participation": 0,
            "modeled_fill_on_explicit_skip": 0,
            "no_modeled_fill_on_explicit_skip": 0,
            "runtime_unavailable": 0,
        }
        for account in ACCOUNT_KEYS
    }
    group_rows: dict[str, list[dict[str, object]]] = {
        f"{account}:{state}": []
        for account in ACCOUNT_KEYS
        for state in sorted(COMPARABLE_STATES)
    }
    for row in decisions:
        account = str(row["account"])
        relation = str(row["technical_relation"])
        account_counts = technical_counts[account]
        if not isinstance(account_counts, dict):  # pragma: no cover - construction guard
            raise TypeError("technical counts must be an object")
        if relation in account_counts:
            account_counts[relation] += 1
        if row["human_state"] in COMPARABLE_STATES:
            group_rows[f"{account}:{row['human_state']}"].append(row)

    shadow_groups: dict[str, object] = {}
    for group, rows in group_rows.items():
        activation_ranks = [
            int(row["shadow"]["rank_at_activation"])
            for row in rows
            if row["shadow"]["rank_at_activation"] is not None
        ]
        best_ranks = [
            int(row["shadow"]["best_rank"])
            for row in rows
            if row["shadow"]["best_rank"] is not None
        ]
        news_states = Counter(str(row["shadow"]["news_state_at_activation"]) for row in rows)
        shadow_groups[group] = {
            "decision_count": len(rows),
            "rank_at_activation_observed_count": len(activation_ranks),
            "median_rank_at_activation": _median(activation_ranks),
            "median_best_rank": _median(best_ranks),
            "ever_market_leader_count": sum(
                bool(row["shadow"]["ever_market_leader"]) for row in rows
            ),
            "news_state_at_activation_counts": dict(sorted(news_states.items())),
            "news_arrived_after_activation_count": sum(
                bool(row["shadow"]["news_arrived_after_activation"]) for row in rows
            ),
        }

    scanner_recall: dict[str, object] = {}
    for account in ACCOUNT_KEYS:
        in_candidates = sum(
            row["account"] == account and row["human_state"] == "participated"
            for row in decisions
        )
        off_candidates = sum(
            row["account"] == account and row["human_state"] == "participated"
            for row in off_candidate_decisions
        )
        observed_total = in_candidates + off_candidates
        scanner_recall[account] = {
            "observed_participation_decision_count": observed_total,
            "acquired_participation_decision_count": in_candidates,
            "off_candidate_participation_decision_count": off_candidates,
            "descriptive_acquisition_fraction": (
                in_candidates / observed_total if observed_total else None
            ),
        }

    unique_in = {
        (row["trading_date"], row["symbol"])
        for row in decisions
        if row["human_state"] == "participated"
    }
    unique_off = {
        (row["trading_date"], row["symbol"])
        for row in off_candidate_decisions
        if row["human_state"] == "participated"
    }
    unique_total = len(unique_in | unique_off)
    scanner_recall["unique_symbol_dates"] = {
        "observed_participated_symbol_date_count": unique_total,
        "acquired_participated_symbol_date_count": len(unique_in),
        "off_candidate_participated_symbol_date_count": len(unique_off),
        "descriptive_acquisition_fraction": (
            len(unique_in) / unique_total if unique_total else None
        ),
    }
    return scanner_recall, technical_counts, shadow_groups


def build_discretion_heldout_comparison(
    *,
    labels: Mapping[str, object],
    micro_by_candidate: Mapping[tuple[str, str], Mapping[str, object]],
    shadow_by_candidate: Mapping[tuple[str, str], Mapping[str, object]],
) -> dict[str, object]:
    """Compare frozen components without fitting or emitting an imitation score."""

    label_dates = _require_mapping(labels.get("date_results"), "date_results")
    decisions: list[dict[str, object]] = []
    off_candidate_decisions: list[dict[str, object]] = []

    for trading_date in REGISTERED_DATES:
        date_result = _require_mapping(label_dates.get(trading_date), trading_date)
        explicit = date_result.get("explicit_candidate_labels")
        if not isinstance(explicit, list):
            raise ValueError("explicit_candidate_labels must be a list")
        for row_value in explicit:
            row = _require_mapping(row_value, "candidate label")
            symbol = str(row["symbol"])
            key = (trading_date, symbol)
            micro = micro_by_candidate.get(key)
            shadow = shadow_by_candidate.get(key)
            if micro is None or shadow is None:
                raise ValueError(f"frozen component is missing {trading_date}/{symbol}")
            for account in ACCOUNT_KEYS:
                if account not in row:
                    continue
                label = _require_mapping(row[account], f"{symbol}.{account}")
                state = str(label["state"])
                filled_count = micro.get("filled_count")
                if filled_count is not None and (
                    isinstance(filled_count, bool) or not isinstance(filled_count, int)
                ):
                    raise ValueError("micro filled_count must be an integer or null")
                decisions.append(
                    {
                        "trading_date": trading_date,
                        "symbol": symbol,
                        "account": account,
                        "human_state": state,
                        "trade_completion": label["trade_completion"],
                        "candidate_acquired": True,
                        "technical_relation": _technical_relation(state, filled_count),
                        "micro": dict(micro),
                        "shadow": dict(shadow),
                    }
                )

        off_candidate = date_result.get("observed_off_candidate_actions")
        if not isinstance(off_candidate, list):
            raise ValueError("observed_off_candidate_actions must be a list")
        for row_value in off_candidate:
            row = _require_mapping(row_value, "off-candidate label")
            symbol = str(row["canonical_symbol"])
            for account in ACCOUNT_KEYS:
                if account not in row:
                    continue
                label = _require_mapping(row[account], f"{symbol}.{account}")
                off_candidate_decisions.append(
                    {
                        "trading_date": trading_date,
                        "symbol": symbol,
                        "account": account,
                        "human_state": label["state"],
                        "trade_completion": label["trade_completion"],
                        "candidate_acquired": False,
                        "identity_resolution_status": row[
                            "identity_resolution_status"
                        ],
                        "technical_relation": "not_evaluable_candidate_not_acquired",
                        "micro": None,
                        "shadow": None,
                    }
                )

    decisions.sort(key=lambda row: (row["trading_date"], row["symbol"], row["account"]))
    off_candidate_decisions.sort(
        key=lambda row: (row["trading_date"], row["symbol"], row["account"])
    )

    scanner_recall, technical_counts, shadow_groups = _comparison_aggregates(
        decisions, off_candidate_decisions
    )

    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": ARTIFACT_ID,
        "artifact_type": ARTIFACT_TYPE,
        "runtime_strategy_effect": "none",
        "policy_promotion_eligible": False,
        "technical_rule_retuning_allowed": False,
        "selection_threshold_fitting_allowed": False,
        "overall_imitation_score_allowed": False,
        "source_content_sha256s": {
            "labels": labels["content_sha256"],
            "scanner_runtime": labels["frozen_runtime"]["scanner_runtime"][
                "content_sha256"
            ],
            "micro_runtime": labels["frozen_runtime"]["micro_runtime"][
                "content_sha256"
            ],
            "shadow_runtime": labels["frozen_runtime"]["shadow_runtime"][
                "content_sha256"
            ],
        },
        "comparison_scope": {
            "registered_dates": list(REGISTERED_DATES),
            "account_scoped": True,
            "explicit_participation_and_skip_only_for_component_contingencies": True,
            "unclear_and_unmentioned_excluded": True,
            "first_fill_price_is_descriptive_only": True,
        },
        "scanner_acquisition": scanner_recall,
        "technical_contingency_counts": technical_counts,
        "shadow_group_descriptives": shadow_groups,
        "candidate_decisions": decisions,
        "off_candidate_decisions": off_candidate_decisions,
        "interpretation": {
            "no_overall_score": True,
            "account_agnostic_micro_can_disagree_between_accounts": True,
            "candidate_acquisition_and_micro_participation_are_separate_gates": True,
            "shadow_features_are_descriptive_not_a_selection_policy": True,
            "panel_is_too_small_and_nonrepresentative_for_fitting": True,
        },
    }
    payload["content_sha256"] = canonical_fingerprint(payload)
    return payload


def validate_discretion_heldout_comparison(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported held-out comparison schema")
    if payload.get("artifact_id") != ARTIFACT_ID:
        raise ValueError("unexpected held-out comparison artifact")
    if payload.get("artifact_type") != ARTIFACT_TYPE:
        raise ValueError("unexpected held-out comparison type")
    if payload.get("runtime_strategy_effect") != "none":
        raise ValueError("comparison cannot affect runtime")
    for field in (
        "policy_promotion_eligible",
        "technical_rule_retuning_allowed",
        "selection_threshold_fitting_allowed",
        "overall_imitation_score_allowed",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must be false")
    claimed = payload.get("content_sha256")
    if not isinstance(claimed, str) or not _SHA256.fullmatch(claimed):
        raise ValueError("comparison lacks a valid content fingerprint")
    projection = {key: value for key, value in payload.items() if key != "content_sha256"}
    if claimed != canonical_fingerprint(projection):
        raise ValueError("comparison content fingerprint mismatch")
    sources = _require_mapping(payload.get("source_content_sha256s"), "sources")
    if set(sources) != {"labels", "scanner_runtime", "micro_runtime", "shadow_runtime"}:
        raise ValueError("comparison source set is incomplete")
    if any(not isinstance(value, str) or not _SHA256.fullmatch(value) for value in sources.values()):
        raise ValueError("comparison source hash is invalid")
    decisions = payload.get("candidate_decisions")
    off_candidate = payload.get("off_candidate_decisions")
    if not isinstance(decisions, list) or not isinstance(off_candidate, list):
        raise ValueError("comparison decisions must be lists")
    scope = _require_mapping(payload.get("comparison_scope"), "comparison_scope")
    if scope.get("registered_dates") != list(REGISTERED_DATES):
        raise ValueError("comparison dates differ from registration")
    keys: set[tuple[object, object, object]] = set()
    for row_value in decisions:
        row = _require_mapping(row_value, "candidate decision")
        key = (row.get("trading_date"), row.get("symbol"), row.get("account"))
        if key in keys:
            raise ValueError("comparison candidate decision is duplicated")
        keys.add(key)
        if row.get("trading_date") not in REGISTERED_DATES:
            raise ValueError("candidate decision date is not registered")
        if row.get("account") not in ACCOUNT_KEYS:
            raise ValueError("candidate decision account is invalid")
        if row.get("human_state") not in HUMAN_ACTION_STATES:
            raise ValueError("candidate human state is invalid")
        _validate_human_state_and_completion(row)
        if row.get("candidate_acquired") is not True:
            raise ValueError("candidate decision must be acquired")
        micro = _require_mapping(row.get("micro"), "candidate micro")
        expected = _technical_relation(
            str(row.get("human_state")), micro.get("filled_count")
        )
        if row.get("technical_relation") != expected:
            raise ValueError("candidate technical relation is inconsistent")
        _require_mapping(row.get("shadow"), "candidate shadow")
    off_keys: set[tuple[object, object, object]] = set()
    for row_value in off_candidate:
        row = _require_mapping(row_value, "off-candidate decision")
        key = (row.get("trading_date"), row.get("symbol"), row.get("account"))
        if key in off_keys:
            raise ValueError("off-candidate decision is duplicated")
        off_keys.add(key)
        if row.get("trading_date") not in REGISTERED_DATES:
            raise ValueError("off-candidate decision date is not registered")
        if row.get("account") not in ACCOUNT_KEYS:
            raise ValueError("off-candidate decision account is invalid")
        if row.get("human_state") not in HUMAN_ACTION_STATES:
            raise ValueError("off-candidate human state is invalid")
        _validate_human_state_and_completion(row)
        if row.get("candidate_acquired") is not False:
            raise ValueError("off-candidate decision cannot be acquired")
        if row.get("micro") is not None or row.get("shadow") is not None:
            raise ValueError("off-candidate decision cannot claim runtime features")
        if row.get("technical_relation") != "not_evaluable_candidate_not_acquired":
            raise ValueError("off-candidate technical relation is inconsistent")

    materialized = [dict(row) for row in decisions]
    materialized_off = [dict(row) for row in off_candidate]
    expected_scanner, expected_technical, expected_shadow = _comparison_aggregates(
        materialized, materialized_off
    )
    if payload.get("scanner_acquisition") != expected_scanner:
        raise ValueError("scanner acquisition aggregate is inconsistent")
    if payload.get("technical_contingency_counts") != expected_technical:
        raise ValueError("technical contingency aggregate is inconsistent")
    if payload.get("shadow_group_descriptives") != expected_shadow:
        raise ValueError("shadow group aggregate is inconsistent")


def load_discretion_heldout_comparison(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("held-out comparison root must be an object")
    validate_discretion_heldout_comparison(payload)
    return payload
