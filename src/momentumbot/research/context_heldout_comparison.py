from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Mapping

from momentumbot.research.context_assessment import EVIDENCE_DOMAINS, SEMANTIC_AXES
from momentumbot.research.context_heldout_labels import (
    ACCOUNT_KEYS,
    RUNTIME_CONTENT_SHA256,
    RUNTIME_ZIP_SHA256,
    SEMANTIC_MANIFEST_CONTENT_SHA256,
    SNAPSHOT_RUNTIME_CONTENT_SHA256,
)
from momentumbot.research.context_heldout_panel import (
    REGISTERED_DATES,
    canonical_fingerprint,
)
from momentumbot.research.discretion_heldout_panel import HUMAN_ACTION_STATES


SCHEMA_VERSION = 1
ARTIFACT_ID = "ross-context-heldout-comparison-v0.1"
ARTIFACT_TYPE = "retrospective_descriptive_context_component_comparison"
COMPARABLE_STATES = {"participated", "explicitly_skipped_or_rejected"}
EXPLICIT_STATES = COMPARABLE_STATES | {"discussed_but_action_unclear"}
SEMANTIC_RUBRIC_CONTENT_SHA256 = (
    "959256aedcc7ed89c8120b19cd1640547a63eb24fcca359c476117ba679f13d3"
)
LABELS_CONTENT_SHA256 = (
    "3ff85b371de31ea5dc1d2e4afc4e334c6f6f5051bfe5c7340fb51007527b7cd1"
)
FROZEN_COMPARISON_CONTENT_SHA256 = (
    "d93d61ed0ebd5657bbed135beb7fe2d7b0f337d1e3f76720c0f1dcff7908ff54"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

SnapshotKey = tuple[str, str, str]


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return value


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


def _item_payload(
    snapshot: Mapping[str, object], domain: str
) -> Mapping[str, object] | None:
    items = snapshot.get("evidence_items")
    if not isinstance(items, list):
        raise ValueError("deterministic snapshot lacks evidence_items")
    matches = [
        item
        for item in items
        if isinstance(item, Mapping) and item.get("domain") == domain
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError(f"deterministic snapshot has repeated {domain} payloads")
    return _mapping(matches[0].get("payload"), f"{domain}.payload")


def _evidence_coverage(snapshot: Mapping[str, object]) -> dict[str, bool]:
    raw = _mapping(snapshot.get("evidence_coverage"), "evidence_coverage")
    if set(raw) != set(EVIDENCE_DOMAINS):
        raise ValueError("deterministic evidence domains differ from the protocol")
    result: dict[str, bool] = {}
    for domain in EVIDENCE_DOMAINS:
        row = _mapping(raw[domain], f"evidence_coverage.{domain}")
        present = row.get("evidence_present")
        if not isinstance(present, bool):
            raise ValueError("deterministic evidence coverage must be boolean")
        result[domain] = present
    return result


def _compact_deterministic(snapshot: Mapping[str, object]) -> dict[str, object]:
    scanner = _item_payload(snapshot, "scanner_market")
    attention = _item_payload(snapshot, "attention_leadership")
    catalyst = _item_payload(snapshot, "catalyst_chronology")
    daily = _item_payload(snapshot, "daily_chart")
    theme = _item_payload(snapshot, "theme_regime")
    if scanner is None or attention is None or catalyst is None or theme is None:
        raise ValueError("deterministic snapshot lacks a required context component")

    events = catalyst.get("events")
    if not isinstance(events, list):
        raise ValueError("catalyst chronology events must be a list")
    catalyst_summary = {
        "news_provider_status": catalyst.get("news_provider_status"),
        "provider_news_event_count_as_of": catalyst.get(
            "provider_news_event_count_as_of"
        ),
        "provider_relative_no_news_as_of": catalyst.get(
            "provider_relative_no_news_as_of"
        ),
        "single_symbol_event_count": sum(
            isinstance(event, Mapping) and event.get("single_symbol_story") is True
            for event in events
        ),
        "multi_symbol_event_count": sum(
            isinstance(event, Mapping) and event.get("single_symbol_story") is False
            for event in events
        ),
    }

    daily_summary = None
    if daily is not None:
        coverage = _mapping(daily.get("coverage"), "daily_chart.coverage")
        features = _mapping(daily.get("features"), "daily_chart.features")
        nearest = features.get("nearest_overhead_reference")
        nearest_row = nearest if isinstance(nearest, Mapping) else {}
        daily_summary = {
            "included_prior_completed_sessions": coverage.get(
                "included_prior_completed_sessions"
            ),
            "history_complete_for_requested_window": coverage.get(
                "history_complete_for_requested_window"
            ),
            "moving_average_200_status": coverage.get("moving_average_200_status"),
            "nearest_overhead_distance_pct": nearest_row.get("distance_pct"),
            "nearest_overhead_source_type": nearest_row.get("source_type"),
        }

    theme_features = _mapping(theme.get("features"), "theme_regime.features")
    return {
        "evidence_coverage": _evidence_coverage(snapshot),
        "scanner_market": {
            field: scanner.get(field)
            for field in (
                "disposition",
                "candidate_completed_bar_present",
                "price",
                "percent_gain",
                "cumulative_volume",
                "exact_same_time_rvol",
                "estimated_float_shares",
                "top_gainer_rank",
                "provider_news_event_count_as_of",
                "provider_relative_no_news_as_of",
            )
        },
        "attention_leadership": {
            field: attention.get(field)
            for field in (
                "active_market_candidate_count",
                "active_candidates_with_better_market_rank",
                "candidate_top_gainer_rank",
                "candidate_gap_to_leader_pct_points",
                "candidate_is_market_leader",
                "candidate_consecutive_market_leader_minutes",
            )
        },
        "catalyst_chronology": catalyst_summary,
        "daily_chart": daily_summary,
        "theme_regime": {
            field: theme_features.get(field)
            for field in (
                "same_minute_observed_candidate_count",
                "same_minute_news_state_counts",
                "cross_candidate_story_count",
                "subject_candidate_headline_count",
                "prior_completed_session_count",
            )
        },
    }


def _compact_semantic(record: Mapping[str, object]) -> dict[str, object]:
    raw_axes = _mapping(record.get("axes"), "semantic axes")
    if set(raw_axes) != set(SEMANTIC_AXES):
        raise ValueError("semantic axes differ from the frozen protocol")
    result: dict[str, object] = {}
    for axis in SEMANTIC_AXES:
        row = _mapping(raw_axes[axis], f"semantic axes.{axis}")
        evidence_ids = row.get("evidence_ids")
        if not isinstance(evidence_ids, list) or any(
            not isinstance(value, str) for value in evidence_ids
        ):
            raise ValueError("semantic axis evidence_ids must be a string list")
        result[axis] = {
            "state": row.get("state"),
            "value": row.get("value"),
            "confidence": row.get("confidence"),
            "abstain_reason": row.get("abstain_reason"),
            "evidence_ids": list(evidence_ids),
        }
    return result


def _coverage_statistics(
    coverage_rows: list[Mapping[str, object]],
) -> dict[str, object]:
    counts: dict[str, object] = {}
    for domain in EVIDENCE_DOMAINS:
        present = sum(row.get(domain) is True for row in coverage_rows)
        counts[domain] = {
            "present": present,
            "missing": len(coverage_rows) - present,
        }
    return {"record_count": len(coverage_rows), "domains": counts}


def _semantic_statistics(axis_rows: list[Mapping[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for axis in SEMANTIC_AXES:
        states: Counter[str] = Counter()
        values: Counter[str] = Counter()
        confidence: Counter[str] = Counter()
        abstain_reasons: Counter[str] = Counter()
        cited_axis_count = 0
        evidence_reference_count = 0
        for axes in axis_rows:
            row = _mapping(axes.get(axis), axis)
            states[str(row.get("state"))] += 1
            if row.get("value") is not None:
                values[str(row["value"])] += 1
            if row.get("confidence") is not None:
                confidence[str(row["confidence"])] += 1
            if row.get("abstain_reason") is not None:
                abstain_reasons[str(row["abstain_reason"])] += 1
            evidence_ids = row.get("evidence_ids")
            if not isinstance(evidence_ids, list):
                raise ValueError("semantic axis evidence_ids must be a list")
            if evidence_ids:
                cited_axis_count += 1
                evidence_reference_count += len(evidence_ids)
        result[axis] = {
            "states": dict(sorted(states.items())),
            "values": dict(sorted(values.items())),
            "confidence": dict(sorted(confidence.items())),
            "abstain_reasons": dict(sorted(abstain_reasons.items())),
            "axis_instances_with_evidence_citations": cited_axis_count,
            "evidence_reference_count": evidence_reference_count,
        }
    return {"record_count": len(axis_rows), "axes": result}


def _provider_statistics(snapshots: list[Mapping[str, object]]) -> dict[str, object]:
    scanner_news: Counter[str] = Counter()
    scanner_float: Counter[str] = Counter()
    catalyst_news: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    for snapshot in snapshots:
        scanner = _item_payload(snapshot, "scanner_market")
        catalyst = _item_payload(snapshot, "catalyst_chronology")
        assert scanner is not None and catalyst is not None
        scanner_news[str(scanner.get("news_provider_status"))] += 1
        scanner_float[str(scanner.get("float_provider_status"))] += 1
        catalyst_news[str(catalyst.get("news_provider_status"))] += 1
        reasons[str(snapshot.get("snapshot_reason"))] += 1
    return {
        "snapshot_reason_counts": dict(sorted(reasons.items())),
        "scanner_news_provider_status_counts": dict(sorted(scanner_news.items())),
        "scanner_float_provider_status_counts": dict(sorted(scanner_float.items())),
        "catalyst_news_provider_status_counts": dict(sorted(catalyst_news.items())),
    }


def _deterministic_statistics(
    snapshots: list[Mapping[str, object]],
) -> dict[str, object]:
    result = _coverage_statistics([_evidence_coverage(row) for row in snapshots])
    result.update(_provider_statistics(snapshots))
    return result


def _action_aggregates(
    decisions: list[dict[str, object]],
    off_candidate_decisions: list[dict[str, object]],
) -> tuple[dict[str, object], dict[str, object]]:
    groups: dict[str, object] = {}
    for account in ACCOUNT_KEYS:
        for state in sorted(COMPARABLE_STATES):
            rows = [
                row
                for row in decisions
                if row["account"] == account and row["human_state"] == state
            ]
            groups[f"{account}:{state}"] = {
                "decision_count": len(rows),
                "deterministic_evidence_coverage": _coverage_statistics(
                    [row["deterministic_components"]["evidence_coverage"] for row in rows]
                ),
                "semantic_axis_descriptives": _semantic_statistics(
                    [row["semantic_axes"] for row in rows]
                ),
            }

    acquisition: dict[str, object] = {}
    for account in ACCOUNT_KEYS:
        acquired = sum(
            row["account"] == account and row["human_state"] == "participated"
            for row in decisions
        )
        missed = sum(
            row["account"] == account and row["human_state"] == "participated"
            for row in off_candidate_decisions
        )
        observed = acquired + missed
        acquisition[account] = {
            "observed_completed_trade_action_count": observed,
            "acquired_completed_trade_action_count": acquired,
            "off_candidate_completed_trade_action_count": missed,
            "descriptive_acquisition_fraction": acquired / observed if observed else None,
        }
    acquired_unique = {
        (row["trading_date"], row["symbol"])
        for row in decisions
        if row["human_state"] == "participated"
    }
    missed_unique = {
        (row["trading_date"], row["symbol"])
        for row in off_candidate_decisions
        if row["human_state"] == "participated"
    }
    observed_unique = acquired_unique | missed_unique
    acquisition["unique_symbol_dates"] = {
        "observed_completed_trade_symbol_date_count": len(observed_unique),
        "acquired_completed_trade_symbol_date_count": len(acquired_unique),
        "off_candidate_completed_trade_symbol_date_count": len(missed_unique),
        "descriptive_acquisition_fraction": (
            len(acquired_unique) / len(observed_unique) if observed_unique else None
        ),
    }
    return groups, acquisition


def _pairing_integrity(
    snapshots: Mapping[SnapshotKey, Mapping[str, object]],
    semantic: Mapping[SnapshotKey, Mapping[str, object]],
) -> dict[str, object]:
    if set(snapshots) != set(semantic):
        raise ValueError("deterministic and semantic record keys differ")
    exact_hash_matches = 0
    axis_instances = 0
    cited_axis_instances = 0
    evidence_references = 0
    resolved_references = 0
    for key in sorted(snapshots):
        snapshot = snapshots[key]
        record = semantic[key]
        if record.get("source_snapshot_content_sha256") == snapshot.get(
            "snapshot_content_sha256"
        ):
            exact_hash_matches += 1
        items = snapshot.get("evidence_items")
        if not isinstance(items, list):
            raise ValueError("snapshot evidence_items must be a list")
        available = {
            item.get("evidence_id") for item in items if isinstance(item, Mapping)
        }
        axes = _mapping(record.get("axes"), "semantic axes")
        for axis in SEMANTIC_AXES:
            axis_instances += 1
            row = _mapping(axes.get(axis), axis)
            citations = row.get("evidence_ids")
            if not isinstance(citations, list):
                raise ValueError("semantic evidence_ids must be a list")
            if citations:
                cited_axis_instances += 1
            evidence_references += len(citations)
            resolved_references += sum(value in available for value in citations)
    count = len(snapshots)
    return {
        "deterministic_record_count": count,
        "semantic_record_count": len(semantic),
        "exact_key_pair_count": count,
        "exact_source_snapshot_hash_match_count": exact_hash_matches,
        "semantic_axis_instance_count": axis_instances,
        "axis_instances_with_evidence_citations": cited_axis_instances,
        "semantic_evidence_reference_count": evidence_references,
        "references_resolved_to_exact_snapshot_count": resolved_references,
        "all_record_keys_paired": True,
        "all_source_snapshot_hashes_match": exact_hash_matches == count,
        "all_semantic_citations_resolve_to_exact_snapshot": (
            evidence_references == resolved_references
        ),
    }


def build_context_heldout_comparison(
    *,
    labels: Mapping[str, object],
    deterministic_snapshots: Mapping[SnapshotKey, Mapping[str, object]],
    semantic_records: Mapping[SnapshotKey, Mapping[str, object]],
) -> dict[str, object]:
    """Compare frozen context components descriptively without fitting a policy."""

    pairing = _pairing_integrity(deterministic_snapshots, semantic_records)
    activation: dict[tuple[str, str], Mapping[str, object]] = {}
    activation_semantic: dict[tuple[str, str], Mapping[str, object]] = {}
    for key, snapshot in deterministic_snapshots.items():
        trading_date, symbol, decision_time = key
        if decision_time != snapshot.get("decision_time"):
            raise ValueError("deterministic record key differs from its payload")
        if snapshot.get("decision_time") == snapshot.get("activation_time"):
            candidate_key = (trading_date, symbol)
            if candidate_key in activation:
                raise ValueError("candidate has repeated activation snapshots")
            activation[candidate_key] = snapshot
            activation_semantic[candidate_key] = semantic_records[key]
    if len(activation) != 195:
        raise ValueError("comparison must retain exactly 195 activation snapshots")

    date_results = _mapping(labels.get("date_results"), "date_results")
    decisions: list[dict[str, object]] = []
    off_candidate_decisions: list[dict[str, object]] = []
    explicit_symbol_dates: set[tuple[str, str]] = set()
    for trading_date in REGISTERED_DATES:
        date_result = _mapping(date_results.get(trading_date), trading_date)
        explicit = date_result.get("explicit_candidate_labels")
        if not isinstance(explicit, list):
            raise ValueError("explicit_candidate_labels must be a list")
        for raw in explicit:
            row = _mapping(raw, "candidate label")
            symbol = str(row["symbol"])
            candidate_key = (trading_date, symbol)
            snapshot = activation.get(candidate_key)
            semantic = activation_semantic.get(candidate_key)
            if snapshot is None or semantic is None:
                raise ValueError(f"activation component missing for {trading_date}/{symbol}")
            explicit_symbol_dates.add(candidate_key)
            for account in ACCOUNT_KEYS:
                if account not in row:
                    continue
                label = _mapping(row[account], f"{symbol}.{account}")
                decisions.append(
                    {
                        "trading_date": trading_date,
                        "symbol": symbol,
                        "account": account,
                        "human_state": label["state"],
                        "trade_completion": label["trade_completion"],
                        "candidate_acquired": True,
                        "human_evidence_timing_quality": "retrospective_sequence_only",
                        "comparison_snapshot_role": (
                            "candidate_activation_neutral_anchor_not_claimed_trade_time"
                        ),
                        "activation_time": snapshot["activation_time"],
                        "deterministic_snapshot_content_sha256": snapshot[
                            "snapshot_content_sha256"
                        ],
                        "semantic_assessment_content_sha256": semantic[
                            "assessment_content_sha256"
                        ],
                        "deterministic_components": _compact_deterministic(snapshot),
                        "semantic_axes": _compact_semantic(semantic),
                    }
                )

        off_candidate = date_result.get("observed_off_candidate_actions")
        if not isinstance(off_candidate, list):
            raise ValueError("observed_off_candidate_actions must be a list")
        for raw in off_candidate:
            row = _mapping(raw, "off-candidate label")
            symbol = str(row["canonical_symbol"])
            for account in ACCOUNT_KEYS:
                if account not in row:
                    continue
                label = _mapping(row[account], f"{symbol}.{account}")
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
                        "human_evidence_timing_quality": "retrospective_sequence_only",
                        "deterministic_components": None,
                        "semantic_axes": None,
                    }
                )

    decisions.sort(key=lambda row: (row["trading_date"], row["symbol"], row["account"]))
    off_candidate_decisions.sort(
        key=lambda row: (row["trading_date"], row["symbol"], row["account"])
    )
    action_groups, acquisition = _action_aggregates(
        decisions, off_candidate_decisions
    )

    all_snapshots = [deterministic_snapshots[key] for key in sorted(deterministic_snapshots)]
    activation_snapshots = [activation[key] for key in sorted(activation)]
    all_semantic = [
        _compact_semantic(semantic_records[key]) for key in sorted(semantic_records)
    ]
    activation_axes = [
        _compact_semantic(activation_semantic[key]) for key in sorted(activation_semantic)
    ]
    explicit_snapshots = [activation[key] for key in sorted(explicit_symbol_dates)]

    parents = _mapping(labels.get("frozen_parents"), "frozen_parents")
    runtime_parent = _mapping(parents.get("deterministic_runtime"), "deterministic_runtime")
    semantic_parent = _mapping(parents.get("semantic_shadow"), "semantic_shadow")
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": ARTIFACT_ID,
        "artifact_type": ARTIFACT_TYPE,
        "comparison_status": "frozen_descriptive_only",
        "runtime_strategy_effect": "none",
        "policy_promotion_eligible": False,
        "technical_rule_retuning_allowed": False,
        "selection_threshold_fitting_allowed": False,
        "aggregate_context_score_allowed": False,
        "overall_imitation_score_allowed": False,
        "source_content_sha256s": {
            "labels": labels["content_sha256"],
            "deterministic_runtime_zip": runtime_parent["zip_sha256"],
            "deterministic_runtime_manifest": runtime_parent[
                "runtime_manifest_content_sha256"
            ],
            "deterministic_snapshot_runtime": runtime_parent[
                "snapshot_runtime_content_sha256"
            ],
            "semantic_manifest": semantic_parent["manifest_content_sha256"],
            "semantic_rubric": semantic_parent["rubric_content_sha256"],
        },
        "comparison_scope": {
            "registered_dates": list(REGISTERED_DATES),
            "all_causal_market_candidates_retained": True,
            "top_n_or_rank_filter_applied": False,
            "account_scoped": True,
            "explicit_participation_and_skip_only_for_action_groups": True,
            "unclear_unmentioned_and_unavailable_excluded_from_action_groups": True,
            "paired_snapshot_rule": "candidate_activation",
            "later_source_change_snapshots_used_for_action_comparison": False,
            "exact_human_decision_time_claimed": False,
            "activation_anchor_is_trade_time_proxy": False,
        },
        "panel_counts": {
            "registered_date_count": len(REGISTERED_DATES),
            "candidate_symbol_date_count": len(activation),
            "candidate_account_label_slot_count": len(activation) * len(ACCOUNT_KEYS),
            "deterministic_snapshot_count": len(deterministic_snapshots),
            "semantic_record_count": len(semantic_records),
            "explicit_candidate_symbol_date_count": len(explicit_symbol_dates),
            "explicit_candidate_account_action_count": len(decisions),
            "off_candidate_account_action_count": len(off_candidate_decisions),
        },
        "frozen_component_pairing": pairing,
        "deterministic_component_descriptives": {
            "all_frozen_snapshots": _deterministic_statistics(all_snapshots),
            "candidate_activation_snapshots": _deterministic_statistics(
                activation_snapshots
            ),
            "explicit_candidate_symbol_dates_at_activation": (
                _deterministic_statistics(explicit_snapshots)
            ),
        },
        "semantic_component_descriptives": {
            "all_frozen_snapshots": _semantic_statistics(all_semantic),
            "candidate_activation_snapshots": _semantic_statistics(activation_axes),
        },
        "action_group_descriptives": action_groups,
        "candidate_acquisition": acquisition,
        "candidate_actions": decisions,
        "off_candidate_actions": off_candidate_decisions,
        "interpretation": {
            "no_overall_or_aggregate_score": True,
            "no_component_value_is_declared_a_trade_rule": True,
            "group_counts_are_descriptive_not_accuracy_estimates": True,
            "activation_is_a_neutral_shared_anchor_not_a_reconstructed_trade_time": True,
            "candidate_acquisition_and_context_assessment_are_separate_gates": True,
            "micro_v0_1_unchanged": True,
            "panel_is_nonrepresentative_and_not_fit_evidence": True,
        },
    }
    payload["content_sha256"] = canonical_fingerprint(payload)
    return payload


def _validate_semantic_axes(value: object) -> None:
    axes = _mapping(value, "semantic_axes")
    if set(axes) != set(SEMANTIC_AXES):
        raise ValueError("comparison semantic axes differ from the protocol")
    for axis in SEMANTIC_AXES:
        row = _mapping(axes[axis], axis)
        if set(row) != {
            "state",
            "value",
            "confidence",
            "abstain_reason",
            "evidence_ids",
        }:
            raise ValueError("comparison semantic axis fields differ")
        state = row.get("state")
        if state not in {"assessed", "abstained"}:
            raise ValueError("comparison semantic axis state is invalid")
        if state == "assessed" and (
            row.get("value") is None
            or row.get("confidence") not in {"low", "medium", "high"}
            or row.get("abstain_reason") is not None
        ):
            raise ValueError("assessed semantic axis is inconsistent")
        if state == "abstained" and (
            row.get("value") is not None
            or row.get("confidence") is not None
            or not isinstance(row.get("abstain_reason"), str)
        ):
            raise ValueError("abstained semantic axis is inconsistent")
        evidence = row.get("evidence_ids")
        if not isinstance(evidence, list) or any(
            not isinstance(item, str) for item in evidence
        ):
            raise ValueError("comparison semantic evidence IDs are invalid")


def _validate_deterministic_components(value: object) -> Mapping[str, object]:
    components = _mapping(value, "deterministic_components")
    if set(components) != {
        "evidence_coverage",
        "scanner_market",
        "attention_leadership",
        "catalyst_chronology",
        "daily_chart",
        "theme_regime",
    }:
        raise ValueError("comparison deterministic component set differs")
    coverage = _mapping(components.get("evidence_coverage"), "evidence_coverage")
    if set(coverage) != set(EVIDENCE_DOMAINS) or any(
        not isinstance(value, bool) for value in coverage.values()
    ):
        raise ValueError("comparison deterministic evidence coverage is invalid")
    for field in (
        "scanner_market",
        "attention_leadership",
        "catalyst_chronology",
        "theme_regime",
    ):
        _mapping(components.get(field), field)
    if components.get("daily_chart") is not None:
        _mapping(components.get("daily_chart"), "daily_chart")
    return components


def validate_context_heldout_comparison(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported context comparison schema")
    if payload.get("artifact_id") != ARTIFACT_ID:
        raise ValueError("unexpected context comparison artifact")
    if payload.get("artifact_type") != ARTIFACT_TYPE:
        raise ValueError("unexpected context comparison artifact type")
    if payload.get("comparison_status") != "frozen_descriptive_only":
        raise ValueError("context comparison must remain frozen descriptive output")
    if payload.get("runtime_strategy_effect") != "none":
        raise ValueError("context comparison cannot affect runtime")
    for field in (
        "policy_promotion_eligible",
        "technical_rule_retuning_allowed",
        "selection_threshold_fitting_allowed",
        "aggregate_context_score_allowed",
        "overall_imitation_score_allowed",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must be false")
    claimed = _sha(payload.get("content_sha256"), "content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if claimed != canonical_fingerprint(unsigned):
        raise ValueError("context comparison content fingerprint mismatch")

    sources = _mapping(payload.get("source_content_sha256s"), "source hashes")
    if set(sources) != {
        "labels",
        "deterministic_runtime_zip",
        "deterministic_runtime_manifest",
        "deterministic_snapshot_runtime",
        "semantic_manifest",
        "semantic_rubric",
    }:
        raise ValueError("context comparison source set is incomplete")
    for field, value in sources.items():
        _sha(value, f"source_content_sha256s.{field}")
    expected_sources = {
        "labels": LABELS_CONTENT_SHA256,
        "deterministic_runtime_zip": RUNTIME_ZIP_SHA256,
        "deterministic_runtime_manifest": RUNTIME_CONTENT_SHA256,
        "deterministic_snapshot_runtime": SNAPSHOT_RUNTIME_CONTENT_SHA256,
        "semantic_manifest": SEMANTIC_MANIFEST_CONTENT_SHA256,
        "semantic_rubric": SEMANTIC_RUBRIC_CONTENT_SHA256,
    }
    for field, expected in expected_sources.items():
        if sources.get(field) != expected:
            raise ValueError(f"context comparison {field} parent changed")

    scope = _mapping(payload.get("comparison_scope"), "comparison_scope")
    if scope.get("registered_dates") != list(REGISTERED_DATES):
        raise ValueError("context comparison dates differ from registration")
    expected_scope_guards = {
        "all_causal_market_candidates_retained": True,
        "top_n_or_rank_filter_applied": False,
        "account_scoped": True,
        "explicit_participation_and_skip_only_for_action_groups": True,
        "unclear_unmentioned_and_unavailable_excluded_from_action_groups": True,
        "later_source_change_snapshots_used_for_action_comparison": False,
        "exact_human_decision_time_claimed": False,
        "activation_anchor_is_trade_time_proxy": False,
    }
    for field, expected in expected_scope_guards.items():
        if scope.get(field) is not expected:
            raise ValueError(f"comparison_scope.{field} must be {expected}")
    if scope.get("paired_snapshot_rule") != "candidate_activation":
        raise ValueError("context comparison must use the activation anchor")

    decisions = payload.get("candidate_actions")
    off_candidate = payload.get("off_candidate_actions")
    if not isinstance(decisions, list) or not isinstance(off_candidate, list):
        raise ValueError("context comparison action rows must be lists")
    decision_keys: set[tuple[object, object, object]] = set()
    for raw in decisions:
        row = _mapping(raw, "candidate action")
        key = (row.get("trading_date"), row.get("symbol"), row.get("account"))
        if key in decision_keys:
            raise ValueError("context comparison candidate action is duplicated")
        decision_keys.add(key)
        if row.get("trading_date") not in REGISTERED_DATES:
            raise ValueError("candidate action date is not registered")
        if row.get("account") not in ACCOUNT_KEYS:
            raise ValueError("candidate action account is invalid")
        if row.get("human_state") not in HUMAN_ACTION_STATES:
            raise ValueError("candidate human state is invalid")
        _validate_human_state_and_completion(row)
        if row.get("candidate_acquired") is not True:
            raise ValueError("candidate action must be acquired")
        if row.get("human_evidence_timing_quality") != "retrospective_sequence_only":
            raise ValueError("candidate action overclaims human timing")
        if row.get("comparison_snapshot_role") != (
            "candidate_activation_neutral_anchor_not_claimed_trade_time"
        ):
            raise ValueError("candidate action uses an invalid snapshot role")
        _sha(
            row.get("deterministic_snapshot_content_sha256"),
            "deterministic_snapshot_content_sha256",
        )
        _sha(
            row.get("semantic_assessment_content_sha256"),
            "semantic_assessment_content_sha256",
        )
        _validate_deterministic_components(row.get("deterministic_components"))
        _validate_semantic_axes(row.get("semantic_axes"))

    off_keys: set[tuple[object, object, object]] = set()
    for raw in off_candidate:
        row = _mapping(raw, "off-candidate action")
        key = (row.get("trading_date"), row.get("symbol"), row.get("account"))
        if key in off_keys:
            raise ValueError("off-candidate action is duplicated")
        off_keys.add(key)
        if row.get("trading_date") not in REGISTERED_DATES:
            raise ValueError("off-candidate date is not registered")
        if row.get("account") not in ACCOUNT_KEYS:
            raise ValueError("off-candidate account is invalid")
        _validate_human_state_and_completion(row)
        if row.get("candidate_acquired") is not False:
            raise ValueError("off-candidate action cannot be acquired")
        if row.get("deterministic_components") is not None or row.get(
            "semantic_axes"
        ) is not None:
            raise ValueError("off-candidate action cannot claim context components")

    materialized = [dict(row) for row in decisions]
    materialized_off = [dict(row) for row in off_candidate]
    expected_groups, expected_acquisition = _action_aggregates(
        materialized, materialized_off
    )
    if payload.get("action_group_descriptives") != expected_groups:
        raise ValueError("context action-group descriptives are inconsistent")
    if payload.get("candidate_acquisition") != expected_acquisition:
        raise ValueError("context candidate acquisition is inconsistent")

    counts = _mapping(payload.get("panel_counts"), "panel_counts")
    explicit_symbol_dates = {
        (row["trading_date"], row["symbol"]) for row in materialized
    }
    expected_counts = {
        "registered_date_count": 10,
        "candidate_symbol_date_count": 195,
        "candidate_account_label_slot_count": 390,
        "deterministic_snapshot_count": 314,
        "semantic_record_count": 314,
        "explicit_candidate_symbol_date_count": len(explicit_symbol_dates),
        "explicit_candidate_account_action_count": len(materialized),
        "off_candidate_account_action_count": len(materialized_off),
    }
    if dict(counts) != expected_counts:
        raise ValueError("context comparison panel counts are inconsistent")

    pairing = _mapping(payload.get("frozen_component_pairing"), "pairing")
    required_pairing = {
        "deterministic_record_count": 314,
        "semantic_record_count": 314,
        "exact_key_pair_count": 314,
        "exact_source_snapshot_hash_match_count": 314,
        "semantic_axis_instance_count": 314 * len(SEMANTIC_AXES),
        "axis_instances_with_evidence_citations": 1481,
        "semantic_evidence_reference_count": 2545,
        "references_resolved_to_exact_snapshot_count": 2545,
        "all_record_keys_paired": True,
        "all_source_snapshot_hashes_match": True,
        "all_semantic_citations_resolve_to_exact_snapshot": True,
    }
    for field, expected in required_pairing.items():
        if pairing.get(field) != expected:
            raise ValueError(f"frozen component pairing {field} is inconsistent")
    if pairing.get("semantic_evidence_reference_count") != pairing.get(
        "references_resolved_to_exact_snapshot_count"
    ):
        raise ValueError("semantic evidence references do not resolve")

    deterministic = _mapping(
        payload.get("deterministic_component_descriptives"),
        "deterministic_component_descriptives",
    )
    expected_scope_counts = {
        "all_frozen_snapshots": 314,
        "candidate_activation_snapshots": 195,
        "explicit_candidate_symbol_dates_at_activation": len(explicit_symbol_dates),
    }
    for name, count in expected_scope_counts.items():
        scope_row = _mapping(deterministic.get(name), name)
        if scope_row.get("record_count") != count:
            raise ValueError(f"deterministic descriptive count for {name} changed")
        domains = _mapping(scope_row.get("domains"), f"{name}.domains")
        if set(domains) != set(EVIDENCE_DOMAINS):
            raise ValueError("deterministic descriptive domains changed")
        for domain, raw in domains.items():
            row = _mapping(raw, f"{name}.{domain}")
            if row.get("present", 0) + row.get("missing", 0) != count:
                raise ValueError("deterministic coverage counts do not sum")

    semantic = _mapping(
        payload.get("semantic_component_descriptives"),
        "semantic_component_descriptives",
    )
    for name, count in {
        "all_frozen_snapshots": 314,
        "candidate_activation_snapshots": 195,
    }.items():
        scope_row = _mapping(semantic.get(name), name)
        if scope_row.get("record_count") != count:
            raise ValueError(f"semantic descriptive count for {name} changed")
        axes = _mapping(scope_row.get("axes"), f"{name}.axes")
        if set(axes) != set(SEMANTIC_AXES):
            raise ValueError("semantic descriptive axes changed")
        for axis in SEMANTIC_AXES:
            row = _mapping(axes[axis], f"{name}.{axis}")
            states = _mapping(row.get("states"), f"{name}.{axis}.states")
            if sum(states.values()) != count:
                raise ValueError("semantic state counts do not sum")

    interpretation = _mapping(payload.get("interpretation"), "interpretation")
    expected_interpretation = {
        "no_overall_or_aggregate_score": True,
        "no_component_value_is_declared_a_trade_rule": True,
        "group_counts_are_descriptive_not_accuracy_estimates": True,
        "activation_is_a_neutral_shared_anchor_not_a_reconstructed_trade_time": True,
        "candidate_acquisition_and_context_assessment_are_separate_gates": True,
        "micro_v0_1_unchanged": True,
        "panel_is_nonrepresentative_and_not_fit_evidence": True,
    }
    if dict(interpretation) != expected_interpretation:
        raise ValueError("context comparison interpretation boundary changed")
    if claimed != FROZEN_COMPARISON_CONTENT_SHA256:
        raise ValueError("frozen context comparison content hash changed")


def load_context_heldout_comparison(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("context comparison root must be an object")
    validate_context_heldout_comparison(payload)
    return payload
