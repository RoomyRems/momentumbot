from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Mapping, Sequence

from momentumbot.identity_resolved_universe import json_fingerprint
from momentumbot.research.context_assessment import (
    CONTRACT_ID as CONTEXT_ASSESSMENT_CONTRACT_ID,
    SEMANTIC_AXES,
    build_shadow_context_assessment,
    canonical_fingerprint,
    validate_context_decision_snapshot,
    validate_shadow_context_assessment,
)
from momentumbot.research.context_heldout_panel import REGISTERED_DATES


SCHEMA_VERSION = 1
RUBRIC_ID = "context-semantic-shadow-compiled-rubric-v0.1"
ARTIFACT_ID = "ross-context-heldout-semantic-shadow-runtime-v0.1"
MODEL_ID = "gpt-5.6-sol-work-mode-compiled-rubric-v0.1"
PROMPT_ID = RUBRIC_ID
FROZEN_PARENT_ZIP_SHA256 = (
    "a29186eb092752cfafc031360cacf348bea5e607cb19ce326ddaff2ddfedac1a"
)
FROZEN_PARENT_RUNTIME_CONTENT_SHA256 = (
    "3567619bfb6b7b2c177d02cc69f15423bf605663519017a6638b0394e4153702"
)
FROZEN_SNAPSHOT_RUNTIME_CONTENT_SHA256 = (
    "6dcc6f25ddb73e63b5f9c714e0c890ab954b15b099e7ba3a71ef948f9760939f"
)

_GENERIC_HEADLINE_PATTERNS = (
    "stocks moving",
    "shares are trading",
    "stock rallies",
    "stock jumps",
    "stock surges",
    "stock soars",
    "why is it moving",
    "why it is moving",
    "why it is trending",
    "why is it trending",
    "here's why",
    "here’s why",
    "here's what",
    "here’s what",
    "market-moving news",
    "market-moving News",
    "trading halt",
    "halted on circuit breaker",
    "investors' radars",
    "investors’ radars",
    "stock whisper",
    "dow jumps",
    "dow tumbles",
    "nasdaq down",
    "us stocks mixed",
)
_DIRECT_EVENT_PATTERNS = (
    "signs",
    "signed",
    "enters",
    "entered",
    "agreement",
    "agrees",
    "agreed",
    "acquires",
    "acquired",
    "acquisition",
    "completes",
    "completed",
    "closes",
    "closed",
    "secures",
    "secured",
    "receives",
    "received",
    "announces",
    "announced",
    "launches",
    "launched",
    "expands",
    "expanded",
    "names",
    "appoints",
    "judgment",
    "award",
    "earnings",
    " eps ",
    " sales ",
    "guidance",
    "results",
    "phase 1",
    "phase 2",
    "phase 3",
    "pdufa",
    "fda acceptance",
    "primary endpoint",
)
_WITHDRAWAL_PATTERNS = (
    "withdraws",
    "withdrawal",
    "cancels",
    "cancelled",
    "canceled",
    "terminates",
    "terminated",
    "termination",
)
_EXPLORATION_PATTERNS = (
    "mulls",
    "considers",
    "considering",
    "explores",
    "exploring",
    "seeks",
    "pursues",
    "pursuing",
    "plans",
    "planned",
    "proposed",
    "proposal",
    "letter of intent",
    " loi ",
    "to discuss",
    "webinar",
    "potential strategic options",
)
_AUTHORIZATION_PATTERNS = (
    "authorizes",
    "authorized",
    "approves",
    "approved",
    "delegating authority",
    "recommendation to advance",
    "acceptance of its new drug application",
    "priority review",
)
_COMPLETED_ACTION_PATTERNS = (
    "signs",
    "signed",
    "enters",
    "entered",
    "agrees",
    "agreed",
    "acquires",
    "acquired",
    "completes",
    "completed",
    "closes",
    "closed",
    "secures",
    "secured",
    "receives",
    "received",
    "launches",
    "launched",
    "expands",
    "expanded",
    "names",
    "appoints",
    "judgment",
    "award",
    "q1 ",
    "q2 ",
    "q3 ",
    "q4 ",
    " eps ",
    " sales ",
    "raises fy",
    "lowers fy",
    "affirms fy",
    "results from",
    "met its primary endpoint",
)
_QUANTIFIED_PATTERN = re.compile(
    r"(?:\$|\b\d+(?:\.\d+)?\s*(?:%|m|b|million|billion|yr|year|years|g/t|m\b)|"
    r"\bq[1-4]\b|\beps\b|\bsales\b|\bphase\s*[123]\b)",
    re.IGNORECASE,
)


def _read_json_object(path: str | Path) -> dict[str, object]:
    import json

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def load_compiled_rubric(path: str | Path) -> dict[str, object]:
    payload = _read_json_object(path)
    validate_compiled_rubric(payload)
    return payload


def validate_compiled_rubric(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported compiled semantic rubric schema")
    if payload.get("rubric_id") != RUBRIC_ID:
        raise ValueError("unexpected compiled semantic rubric")
    if payload.get("status") != "frozen_before_retrospective_source_inventory":
        raise ValueError("semantic rubric was not frozen before source inventory")
    generation = payload.get("generation_mode")
    if not isinstance(generation, Mapping):
        raise ValueError("compiled semantic rubric lacks generation mode")
    if generation.get("authoring_model") != "gpt-5.6-sol-work-mode":
        raise ValueError("compiled semantic rubric authoring model changed")
    if generation.get("runtime_application") != (
        "deterministic_compilation_of_the_frozen_ai_authored_rubric"
    ):
        raise ValueError("compiled semantic rubric runtime mode changed")
    if generation.get("external_model_api_call_per_record") is not False:
        raise ValueError("compiled semantic rubric overclaims per-record inference")
    parent = payload.get("frozen_parent")
    if not isinstance(parent, Mapping):
        raise ValueError("compiled semantic rubric lacks frozen parent")
    if parent.get("zip_sha256") != FROZEN_PARENT_ZIP_SHA256:
        raise ValueError("compiled semantic rubric ZIP parent changed")
    if parent.get("runtime_manifest_content_sha256") != (
        FROZEN_PARENT_RUNTIME_CONTENT_SHA256
    ):
        raise ValueError("compiled semantic rubric runtime parent changed")
    if parent.get("snapshot_runtime_content_sha256") != (
        FROZEN_SNAPSHOT_RUNTIME_CONTENT_SHA256
    ):
        raise ValueError("compiled semantic rubric snapshot parent changed")
    boundary = payload.get("knowledge_boundary")
    if not isinstance(boundary, Mapping):
        raise ValueError("compiled semantic rubric lacks knowledge boundary")
    if boundary.get("uses_only_frozen_snapshot_evidence") is not True:
        raise ValueError("compiled semantic rubric is not snapshot-only")
    for field in (
        "uses_raw_transcripts",
        "uses_recap_inventory",
        "uses_ross_actions",
        "uses_retrospective_labels",
        "uses_trade_outcomes",
        "uses_later_prices",
        "uses_excluded_pilot_to_fit_rubric",
    ):
        if boundary.get(field) is not False:
            raise ValueError(f"compiled semantic rubric violates {field}")
    authority = payload.get("authority")
    if not isinstance(authority, Mapping):
        raise ValueError("compiled semantic rubric lacks authority boundary")
    if authority.get("runtime_strategy_effect") != "none":
        raise ValueError("compiled semantic rubric has strategy authority")
    if authority.get("policy_promotion_eligible") is not False:
        raise ValueError("compiled semantic rubric overclaims promotion eligibility")
    for field in (
        "aggregate_score",
        "selection_threshold",
        "candidate_priority",
        "trade_recommendation",
        "order_action",
        "position_size",
        "risk_action",
    ):
        if authority.get(field) is not None:
            raise ValueError(f"compiled semantic rubric populates prohibited {field}")


def compiled_rubric_content_sha256(payload: Mapping[str, object]) -> str:
    validate_compiled_rubric(payload)
    return canonical_fingerprint(payload)


def _evidence_items(
    snapshot: Mapping[str, object], domain: str
) -> list[Mapping[str, object]]:
    items = snapshot.get("evidence_items")
    if not isinstance(items, list):
        raise ValueError("context snapshot lacks evidence items")
    return [
        item
        for item in items
        if isinstance(item, Mapping) and item.get("domain") == domain
    ]


def _claim(
    claim_id: str, statement: str, evidence_ids: Sequence[str]
) -> dict[str, object]:
    return {
        "claim_id": claim_id,
        "statement": statement,
        "evidence_ids": sorted(evidence_ids),
    }


def _assessed(
    axis: str,
    *,
    value: str,
    confidence: str,
    evidence_ids: Sequence[str],
    fact: str,
    inference: str,
) -> dict[str, object]:
    return {
        "state": "assessed",
        "value": value,
        "confidence": confidence,
        "evidence_ids": sorted(evidence_ids),
        "observed_facts": [
            _claim(f"{axis}.fact.1", fact, evidence_ids),
        ],
        "inferences": [
            _claim(f"{axis}.inference.1", inference, evidence_ids),
        ],
        "abstain_reason": None,
    }


def _abstained(
    axis: str,
    *,
    reason: str,
    evidence_ids: Sequence[str] = (),
    fact: str | None = None,
) -> dict[str, object]:
    facts = []
    if fact is not None:
        facts.append(_claim(f"{axis}.fact.1", fact, evidence_ids))
    return {
        "state": "abstained",
        "value": None,
        "confidence": None,
        "evidence_ids": sorted(evidence_ids),
        "observed_facts": facts,
        "inferences": [],
        "abstain_reason": reason,
    }


def _normalized_title(value: object) -> str:
    return " ".join(str(value or "").lower().split())


def _contains_any(value: str, patterns: Sequence[str]) -> bool:
    padded = f" {value} "
    return any(pattern.lower() in padded for pattern in patterns)


def _headline_substance(title: str) -> str:
    if _contains_any(title, _GENERIC_HEADLINE_PATTERNS):
        return "vague_or_incidental_event"
    if _contains_any(title, _DIRECT_EVENT_PATTERNS):
        if _QUANTIFIED_PATTERN.search(title):
            return "specific_event_with_explicit_terms"
        return "specific_event_terms_incomplete"
    return "vague_or_incidental_event"


def _headline_commitment(title: str) -> str:
    if _contains_any(title, _WITHDRAWAL_PATTERNS):
        return "withdrawal_or_cancellation"
    if _contains_any(title, _GENERIC_HEADLINE_PATTERNS):
        return "ambiguous_commitment_stage"
    if _contains_any(title, _AUTHORIZATION_PATTERNS):
        return "authorization_not_execution"
    if _contains_any(title, _EXPLORATION_PATTERNS):
        return "exploration_or_pursuit"
    if _contains_any(title, _COMPLETED_ACTION_PATTERNS):
        return "definitive_agreement_or_completed_action"
    return "ambiguous_commitment_stage"


def _headline_axis_inputs(
    snapshot: Mapping[str, object],
) -> tuple[list[str], list[str]]:
    items = _evidence_items(snapshot, "catalyst_headline")
    ids = [str(item["evidence_id"]) for item in items]
    titles = [
        str(item.get("payload", {}).get("title") or "")
        for item in items
        if isinstance(item.get("payload"), Mapping)
    ]
    return ids, titles


def _catalyst_substance(snapshot: Mapping[str, object]) -> dict[str, object]:
    axis = "catalyst_substance_specificity"
    headline_ids, raw_titles = _headline_axis_inputs(snapshot)
    if not headline_ids:
        chronology = _evidence_items(snapshot, "catalyst_chronology")
        if len(chronology) != 1:
            return _abstained(axis, reason="required_evidence_domain_unavailable")
        item = chronology[0]
        payload = item.get("payload")
        if not isinstance(payload, Mapping):
            return _abstained(axis, reason="source_unavailable")
        if (
            payload.get("news_provider_status") == "success"
            and payload.get("provider_relative_no_news_as_of") is True
            and payload.get("provider_news_event_count_as_of") == 0
        ):
            evidence_id = str(item["evidence_id"])
            return _assessed(
                axis,
                value="provider_relative_no_event",
                confidence="high",
                evidence_ids=[evidence_id],
                fact="The successful provider chronology contained zero events for the symbol at this decision time.",
                inference="Within the explicitly provider-relative boundary, no catalyst event was available to assess.",
            )
        return _abstained(axis, reason="source_unavailable")

    titles = [_normalized_title(title) for title in raw_titles]
    values = {_headline_substance(title) for title in titles}
    if len(values) == 1:
        value = next(iter(values))
    elif values.issubset(
        {"specific_event_with_explicit_terms", "specific_event_terms_incomplete"}
    ):
        value = "specific_event_with_explicit_terms"
    else:
        value = "mixed_or_ambiguous_event_substance"
    confidence = {
        "specific_event_with_explicit_terms": "high",
        "specific_event_terms_incomplete": "medium",
        "vague_or_incidental_event": "medium",
        "mixed_or_ambiguous_event_substance": "low",
    }[value]
    return _assessed(
        axis,
        value=value,
        confidence=confidence,
        evidence_ids=headline_ids,
        fact=(
            f"{len(raw_titles)} provider headline(s) were available at the decision time: "
            + " | ".join(raw_titles)
        ),
        inference=f"The available headline wording supports the bounded substance class {value}.",
    )


def _catalyst_commitment(snapshot: Mapping[str, object]) -> dict[str, object]:
    axis = "catalyst_commitment_stage"
    headline_ids, raw_titles = _headline_axis_inputs(snapshot)
    if not headline_ids:
        return _abstained(axis, reason="required_evidence_domain_unavailable")
    values = {_headline_commitment(_normalized_title(title)) for title in raw_titles}
    value = next(iter(values)) if len(values) == 1 else "ambiguous_commitment_stage"
    confidence = (
        "medium" if value != "ambiguous_commitment_stage" else "low"
    )
    return _assessed(
        axis,
        value=value,
        confidence=confidence,
        evidence_ids=headline_ids,
        fact=(
            f"{len(raw_titles)} provider headline(s) were available at the decision time: "
            + " | ".join(raw_titles)
        ),
        inference=f"The available wording supports the bounded commitment-stage class {value}.",
    )


def _theme_abstention(snapshot: Mapping[str, object]) -> dict[str, object]:
    axis = "theme_fit_no_news_acceptance"
    items = _evidence_items(snapshot, "theme_regime")
    if not items:
        return _abstained(axis, reason="required_evidence_domain_unavailable")
    item = items[0]
    payload = item.get("payload")
    features = payload.get("features") if isinstance(payload, Mapping) else None
    if not isinstance(features, Mapping):
        return _abstained(axis, reason="source_unavailable")
    count = features.get("same_minute_observed_candidate_count")
    stories = features.get("cross_candidate_story_count")
    return _abstained(
        axis,
        reason="insufficient_evidence",
        evidence_ids=[str(item["evidence_id"])],
        fact=(
            "The theme/regime record reports "
            f"{count} same-minute candidate(s) and {stories} cross-candidate story link(s), "
            "but it contains no asserted semantic issuer-theme class."
        ),
    )


def _leadership(snapshot: Mapping[str, object]) -> dict[str, object]:
    axis = "opportunity_obviousness_leadership_quality"
    items = _evidence_items(snapshot, "attention_leadership")
    if len(items) != 1:
        return _abstained(axis, reason="required_evidence_domain_unavailable")
    item = items[0]
    payload = item.get("payload")
    if not isinstance(payload, Mapping):
        return _abstained(axis, reason="source_unavailable")
    evidence_id = str(item["evidence_id"])
    if payload.get("candidate_completed_bar_present") is not True:
        return _abstained(
            axis,
            reason="source_unavailable",
            evidence_ids=[evidence_id],
            fact="The candidate had no exact completed bar at this decision time, so rank-based leadership evidence was unavailable.",
        )
    is_leader = payload.get("candidate_is_market_leader") is True
    consecutive = int(payload.get("candidate_consecutive_market_leader_minutes") or 0)
    rank = payload.get("candidate_top_gainer_rank")
    better = payload.get("active_candidates_with_better_market_rank")
    gap = payload.get("candidate_gap_to_leader_pct_points")
    if is_leader and consecutive >= 3:
        value, confidence = "dominant_persistent_leader", "high"
    elif is_leader:
        value, confidence = "emerging_leader", "medium"
    elif (
        (isinstance(rank, int) and rank <= 5)
        or (
            isinstance(better, int)
            and better <= 2
            and isinstance(gap, (int, float))
            and float(gap) <= 15.0
        )
    ):
        value, confidence = "competitive_not_dominant", "medium"
    elif (
        (isinstance(rank, int) and rank > 10)
        or (isinstance(gap, (int, float)) and float(gap) > 30.0)
    ):
        value, confidence = "not_current_leader", "high"
    else:
        value, confidence = "mixed_or_ambiguous_leadership", "low"
    return _assessed(
        axis,
        value=value,
        confidence=confidence,
        evidence_ids=[evidence_id],
        fact=(
            f"The candidate's market rank was {rank}, {better} active candidate(s) ranked better, "
            f"the gap to the leader was {gap} percentage points, and consecutive leader minutes were {consecutive}."
        ),
        inference=f"Those bounded cross-sectional observations support the leadership class {value}.",
    )


def _chart_context(snapshot: Mapping[str, object]) -> dict[str, object]:
    axis = "chart_context_cleanliness"
    items = _evidence_items(snapshot, "daily_chart")
    if not items:
        return _abstained(axis, reason="required_evidence_domain_unavailable")
    item = items[0]
    payload = item.get("payload")
    features = payload.get("features") if isinstance(payload, Mapping) else None
    coverage = payload.get("coverage") if isinstance(payload, Mapping) else None
    if not isinstance(features, Mapping) or not isinstance(coverage, Mapping):
        return _abstained(axis, reason="source_unavailable")
    recent = features.get("recent_session_metrics")
    recent_rows = recent if isinstance(recent, list) else []
    failed_pop_count = 0
    for row in recent_rows:
        if not isinstance(row, Mapping):
            continue
        high_excursion = row.get("high_excursion_pct")
        fade = row.get("high_to_close_fade_pct")
        volume_multiple = row.get("volume_multiple_to_prior_20_mean")
        if (
            isinstance(high_excursion, (int, float))
            and float(high_excursion) >= 20.0
            and isinstance(fade, (int, float))
            and float(fade) >= 25.0
            and isinstance(volume_multiple, (int, float))
            and float(volume_multiple) >= 2.0
        ):
            failed_pop_count += 1
    nearest = features.get("nearest_overhead_reference")
    nearest_distance = (
        nearest.get("distance_pct") if isinstance(nearest, Mapping) else None
    )
    sessions = int(coverage.get("included_prior_completed_sessions") or 0)
    if (
        isinstance(nearest_distance, (int, float))
        and float(nearest_distance) <= 5.0
    ) or failed_pop_count > 0:
        value, confidence = "near_resistance_or_failed_pop_history", "high"
    elif (
        isinstance(nearest_distance, (int, float))
        and float(nearest_distance) >= 20.0
        and failed_pop_count == 0
        and sessions >= 20
    ):
        value, confidence = "clear_room_and_clean_history", "medium"
    else:
        value, confidence = "mixed_chart_context", "medium"
    return _assessed(
        axis,
        value=value,
        confidence=confidence,
        evidence_ids=[str(item["evidence_id"])],
        fact=(
            f"The frozen daily record had {sessions} prior completed sessions, nearest overhead distance "
            f"{nearest_distance} percent, and {failed_pop_count} recent failed-pop-pattern session(s)."
        ),
        inference=f"Those bounded daily-history observations support the chart-context class {value}.",
    )


def build_compiled_shadow_assessment(
    snapshot: Mapping[str, object],
    *,
    rubric_content_sha256: str,
    generated_at: str,
    label_blind_run_id: str,
) -> dict[str, object]:
    validate_context_decision_snapshot(snapshot)
    credibility_reason = (
        "insufficient_evidence"
        if _evidence_items(snapshot, "catalyst_headline")
        else "required_evidence_domain_unavailable"
    )
    axis_assessments = {
        "catalyst_substance_specificity": _catalyst_substance(snapshot),
        "catalyst_commitment_stage": _catalyst_commitment(snapshot),
        "catalyst_credibility_repetition": _abstained(
            "catalyst_credibility_repetition",
            reason=credibility_reason,
        ),
        "theme_fit_no_news_acceptance": _theme_abstention(snapshot),
        "opportunity_obviousness_leadership_quality": _leadership(snapshot),
        "chart_context_cleanliness": _chart_context(snapshot),
    }
    decision = datetime.fromisoformat(
        str(snapshot["decision_time"]).replace("Z", "+00:00")
    )
    expires = (decision + timedelta(seconds=300)).isoformat()
    assessment = build_shadow_context_assessment(
        snapshot,
        axis_assessments=axis_assessments,
        model_provenance={
            "provider": "openai",
            "model_id": MODEL_ID,
            "prompt_id": PROMPT_ID,
            "prompt_content_sha256": rubric_content_sha256,
            "generated_at": generated_at,
            "label_blind_run_id": label_blind_run_id,
        },
        expires_at=expires,
    )
    validate_shadow_context_assessment(assessment, snapshot=snapshot)
    return assessment


def build_semantic_date_payload(
    *,
    trading_date: str,
    source_snapshot_date_content_sha256: str,
    rubric_content_sha256: str,
    assessments: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    if trading_date not in REGISTERED_DATES:
        raise ValueError("semantic date is outside the registered panel")
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": ARTIFACT_ID,
        "contract_id": CONTEXT_ASSESSMENT_CONTRACT_ID,
        "rubric_id": RUBRIC_ID,
        "trading_date": trading_date,
        "source_snapshot_runtime_content_sha256": FROZEN_SNAPSHOT_RUNTIME_CONTENT_SHA256,
        "source_snapshot_date_content_sha256": source_snapshot_date_content_sha256,
        "rubric_content_sha256": rubric_content_sha256,
        "record_count": len(assessments),
        "records": [dict(record) for record in assessments],
        "causal_boundary": {
            "uses_raw_transcripts": False,
            "uses_recap_inventory": False,
            "uses_ross_actions": False,
            "uses_retrospective_labels": False,
            "uses_trade_outcomes": False,
            "uses_later_prices": False,
            "runtime_strategy_effect": "none",
        },
        "policy_promotion_eligible": False,
    }
    payload["content_sha256"] = json_fingerprint(payload)
    validate_semantic_date_payload(payload)
    return payload


def validate_semantic_date_payload(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported semantic date payload schema")
    if payload.get("artifact_id") != ARTIFACT_ID:
        raise ValueError("unexpected semantic date artifact")
    if payload.get("contract_id") != CONTEXT_ASSESSMENT_CONTRACT_ID:
        raise ValueError("semantic date contract changed")
    if payload.get("rubric_id") != RUBRIC_ID:
        raise ValueError("semantic date rubric changed")
    if payload.get("trading_date") not in REGISTERED_DATES:
        raise ValueError("semantic date is outside the registered panel")
    if payload.get("source_snapshot_runtime_content_sha256") != (
        FROZEN_SNAPSHOT_RUNTIME_CONTENT_SHA256
    ):
        raise ValueError("semantic date snapshot parent changed")
    records = payload.get("records")
    if not isinstance(records, list) or payload.get("record_count") != len(records):
        raise ValueError("semantic date record count mismatch")
    causal = payload.get("causal_boundary")
    if not isinstance(causal, Mapping):
        raise ValueError("semantic date lacks causal boundary")
    for field in (
        "uses_raw_transcripts",
        "uses_recap_inventory",
        "uses_ross_actions",
        "uses_retrospective_labels",
        "uses_trade_outcomes",
        "uses_later_prices",
    ):
        if causal.get(field) is not False:
            raise ValueError(f"semantic date violates {field}")
    if causal.get("runtime_strategy_effect") != "none":
        raise ValueError("semantic date has strategy authority")
    if payload.get("policy_promotion_eligible") is not False:
        raise ValueError("semantic date overclaims promotion eligibility")
    claimed = payload.get("content_sha256")
    projection = {
        key: value for key, value in payload.items() if key != "content_sha256"
    }
    if claimed != json_fingerprint(projection):
        raise ValueError("semantic date fingerprint mismatch")


def _axis_statistics(
    date_payloads: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    states = {axis: Counter() for axis in SEMANTIC_AXES}
    values = {axis: Counter() for axis in SEMANTIC_AXES}
    confidence = {axis: Counter() for axis in SEMANTIC_AXES}
    for payload in date_payloads.values():
        records = payload.get("records")
        assert isinstance(records, list)
        for record in records:
            assert isinstance(record, Mapping)
            axes = record.get("axes")
            assert isinstance(axes, Mapping)
            for axis in SEMANTIC_AXES:
                row = axes[axis]
                assert isinstance(row, Mapping)
                states[axis][str(row["state"])] += 1
                if row.get("value") is not None:
                    values[axis][str(row["value"])] += 1
                if row.get("confidence") is not None:
                    confidence[axis][str(row["confidence"])] += 1
    return {
        axis: {
            "states": dict(sorted(states[axis].items())),
            "values": dict(sorted(values[axis].items())),
            "confidence": dict(sorted(confidence[axis].items())),
        }
        for axis in SEMANTIC_AXES
    }


def build_semantic_root_manifest(
    *,
    rubric_content_sha256: str,
    generator_source_sha256: str,
    generated_at: str,
    label_blind_run_id: str,
    date_payloads: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    if tuple(date_payloads) != REGISTERED_DATES:
        raise ValueError("semantic runtime dates differ from registration")
    record_count = sum(int(payload["record_count"]) for payload in date_payloads.values())
    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": ARTIFACT_ID,
        "contract_id": CONTEXT_ASSESSMENT_CONTRACT_ID,
        "rubric_id": RUBRIC_ID,
        "generation_mode": "deterministic_compilation_of_frozen_ai_authored_rubric",
        "model_id": MODEL_ID,
        "generated_at": generated_at,
        "label_blind_run_id": label_blind_run_id,
        "dates": list(REGISTERED_DATES),
        "record_count": record_count,
        "source_parent": {
            "artifact_id": "ross-context-heldout-runtime-v0.1",
            "github_artifact_id": 9376599434,
            "zip_sha256": FROZEN_PARENT_ZIP_SHA256,
            "runtime_manifest_content_sha256": FROZEN_PARENT_RUNTIME_CONTENT_SHA256,
            "snapshot_runtime_content_sha256": FROZEN_SNAPSHOT_RUNTIME_CONTENT_SHA256,
        },
        "rubric_content_sha256": rubric_content_sha256,
        "generator_source_sha256": generator_source_sha256,
        "date_content_sha256s": {
            value: payload["content_sha256"] for value, payload in date_payloads.items()
        },
        "axis_statistics": _axis_statistics(date_payloads),
        "causal_boundary": {
            "uses_raw_transcripts": False,
            "uses_recap_inventory": False,
            "uses_ross_actions": False,
            "uses_retrospective_labels": False,
            "uses_trade_outcomes": False,
            "uses_later_prices": False,
            "aggregate_score_created": False,
            "selection_threshold_created": False,
            "runtime_strategy_effect": "none",
        },
        "eligibility": {
            "frozen_before_retrospective_review": True,
            "descriptive_component_comparison_allowed": True,
            "policy_promotion_eligible": False,
            "representative_panel": False,
            "portfolio_backtest": False,
        },
    }
    manifest["content_sha256"] = json_fingerprint(manifest)
    validate_semantic_root_manifest(manifest)
    return manifest


def validate_semantic_root_manifest(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported semantic root schema")
    if payload.get("artifact_id") != ARTIFACT_ID:
        raise ValueError("unexpected semantic root artifact")
    if payload.get("contract_id") != CONTEXT_ASSESSMENT_CONTRACT_ID:
        raise ValueError("semantic root contract changed")
    if payload.get("rubric_id") != RUBRIC_ID:
        raise ValueError("semantic root rubric changed")
    if payload.get("generation_mode") != (
        "deterministic_compilation_of_frozen_ai_authored_rubric"
    ):
        raise ValueError("semantic root generation mode changed")
    if payload.get("model_id") != MODEL_ID:
        raise ValueError("semantic root model changed")
    if payload.get("dates") != list(REGISTERED_DATES):
        raise ValueError("semantic root dates differ from registration")
    if payload.get("record_count") != 314:
        raise ValueError("semantic root record count changed")
    parent = payload.get("source_parent")
    if not isinstance(parent, Mapping):
        raise ValueError("semantic root lacks parent")
    if parent.get("zip_sha256") != FROZEN_PARENT_ZIP_SHA256:
        raise ValueError("semantic root ZIP parent changed")
    if parent.get("runtime_manifest_content_sha256") != (
        FROZEN_PARENT_RUNTIME_CONTENT_SHA256
    ):
        raise ValueError("semantic root runtime parent changed")
    if parent.get("snapshot_runtime_content_sha256") != (
        FROZEN_SNAPSHOT_RUNTIME_CONTENT_SHA256
    ):
        raise ValueError("semantic root snapshot parent changed")
    causal = payload.get("causal_boundary")
    if not isinstance(causal, Mapping):
        raise ValueError("semantic root lacks causal boundary")
    for field in (
        "uses_raw_transcripts",
        "uses_recap_inventory",
        "uses_ross_actions",
        "uses_retrospective_labels",
        "uses_trade_outcomes",
        "uses_later_prices",
        "aggregate_score_created",
        "selection_threshold_created",
    ):
        if causal.get(field) is not False:
            raise ValueError(f"semantic root violates {field}")
    if causal.get("runtime_strategy_effect") != "none":
        raise ValueError("semantic root has strategy authority")
    eligibility = payload.get("eligibility")
    if not isinstance(eligibility, Mapping):
        raise ValueError("semantic root lacks eligibility")
    if eligibility.get("frozen_before_retrospective_review") is not True:
        raise ValueError("semantic root was not frozen before labels")
    for field in ("policy_promotion_eligible", "representative_panel", "portfolio_backtest"):
        if eligibility.get(field) is not False:
            raise ValueError(f"semantic root overclaims {field}")
    claimed = payload.get("content_sha256")
    projection = {
        key: value for key, value in payload.items() if key != "content_sha256"
    }
    if claimed != json_fingerprint(projection):
        raise ValueError("semantic root fingerprint mismatch")
