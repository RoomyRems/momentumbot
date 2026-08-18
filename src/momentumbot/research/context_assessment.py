from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

from momentumbot.causal_scanner_snapshot import SNAPSHOT_ROW_FIELDS
from momentumbot.research.attention_leadership import FEATURE_NAMES
from momentumbot.research.catalyst_evidence import EVENT_FIELDS, PACKET_FIELDS
from momentumbot.research.catalyst_interpretation import _validate_packet


SCHEMA_VERSION = 1
CONTRACT_ID = "discretion-context-assessment-shadow-v0.1"
RECORD_TYPE_SNAPSHOT = "causal_context_decision_snapshot"
RECORD_TYPE_ASSESSMENT = "shadow_semantic_context_assessment"

MICRO_POLICY_ID = "micro-v0.1"
MICRO_POLICY_FINGERPRINT = (
    "49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa"
)
SCANNER_CONTRACT_ID = "causal-scanner-snapshot-v0.1"
SCANNER_POLICY_FINGERPRINT = (
    "ed21becad10855b4a085b6e05b6feac8f21e4ce511a100b2381522154818f42a"
)
ATTENTION_CONTRACT_ID = "attention-leadership-shadow-v0.1"
CATALYST_EVIDENCE_CONTRACT_ID = "catalyst-evidence-packet-shadow-v0.1"
CATALYST_INTERPRETATION_CONTRACT_ID = (
    "catalyst-interpretation-protocol-shadow-v0.2"
)
CONTEXT_INVENTORY_CONTRACT_ID = "ross-discretion-context-v0.1"

EXCLUDED_PILOT_PANEL_ID = "ross-discretion-heldout-panel-v0.1"
EXCLUDED_PILOT_COMPARISON_ID = "ross-discretion-heldout-comparison-v0.1"
EXCLUDED_PILOT_COMPARISON_SHA256 = (
    "809d4b4a7231b708f9c933c9bf45b58c736f4d3101c8328483c62c1c48bcfb3d"
)

SOURCE_ARTIFACT_KEYS = (
    "scanner_runtime",
    "attention_runtime",
    "catalyst_evidence_runtime",
)
SNAPSHOT_REASONS = (
    "candidate_activation",
    "scheduled_refresh",
    "source_evidence_changed",
)
EVIDENCE_DOMAINS = (
    "scanner_market",
    "attention_leadership",
    "catalyst_chronology",
    "catalyst_headline",
    "filing_corroboration",
    "issuer_event_history",
    "daily_chart",
    "theme_regime",
    "liquidity",
    "account_state",
    "portfolio_attention",
)
BASE_EVIDENCE_DOMAINS = {
    "scanner_market",
    "attention_leadership",
    "catalyst_chronology",
    "catalyst_headline",
}
SUPPLEMENTAL_EVIDENCE_DOMAINS = set(EVIDENCE_DOMAINS) - BASE_EVIDENCE_DOMAINS

SEMANTIC_AXES = (
    "catalyst_substance_specificity",
    "catalyst_commitment_stage",
    "catalyst_credibility_repetition",
    "theme_fit_no_news_acceptance",
    "opportunity_obviousness_leadership_quality",
    "chart_context_cleanliness",
)
AXIS_ALLOWED_EVIDENCE_DOMAINS = {
    "catalyst_substance_specificity": (
        "catalyst_chronology",
        "catalyst_headline",
        "filing_corroboration",
    ),
    "catalyst_commitment_stage": (
        "catalyst_headline",
        "filing_corroboration",
    ),
    "catalyst_credibility_repetition": (
        "catalyst_headline",
        "filing_corroboration",
        "issuer_event_history",
    ),
    "theme_fit_no_news_acceptance": ("theme_regime",),
    "opportunity_obviousness_leadership_quality": (
        "scanner_market",
        "attention_leadership",
        "portfolio_attention",
    ),
    "chart_context_cleanliness": ("daily_chart",),
}
AXIS_VALUES = {
    "catalyst_substance_specificity": (
        "specific_event_with_explicit_terms",
        "specific_event_terms_incomplete",
        "vague_or_incidental_event",
        "mixed_or_ambiguous_event_substance",
        "provider_relative_no_event",
    ),
    "catalyst_commitment_stage": (
        "exploration_or_pursuit",
        "authorization_not_execution",
        "definitive_agreement_or_completed_action",
        "withdrawal_or_cancellation",
        "ambiguous_commitment_stage",
    ),
    "catalyst_credibility_repetition": (
        "corroborated_source_evidence_present",
        "possible_recycled_or_repeated_promotion",
        "mixed_credibility_signals",
        "credibility_ambiguous",
    ),
    "theme_fit_no_news_acceptance": (
        "causal_theme_fit_present",
        "causal_theme_fit_absent",
        "causal_no_news_momentum_acceptance_present",
        "mixed_or_ambiguous_theme_state",
    ),
    "opportunity_obviousness_leadership_quality": (
        "dominant_persistent_leader",
        "emerging_leader",
        "competitive_not_dominant",
        "not_current_leader",
        "mixed_or_ambiguous_leadership",
    ),
    "chart_context_cleanliness": (
        "clear_room_and_clean_history",
        "near_resistance_or_failed_pop_history",
        "mixed_chart_context",
        "ambiguous_chart_context",
    ),
}
VALUE_REQUIRED_EVIDENCE_DOMAINS = {
    "corroborated_source_evidence_present": {"filing_corroboration"},
    "possible_recycled_or_repeated_promotion": {"issuer_event_history"},
    "causal_theme_fit_present": {"theme_regime"},
    "causal_theme_fit_absent": {"theme_regime"},
    "causal_no_news_momentum_acceptance_present": {"theme_regime"},
    "dominant_persistent_leader": {"attention_leadership"},
    "emerging_leader": {"attention_leadership"},
    "competitive_not_dominant": {"attention_leadership"},
    "not_current_leader": {"attention_leadership"},
    "clear_room_and_clean_history": {"daily_chart"},
    "near_resistance_or_failed_pop_history": {"daily_chart"},
}

ASSESSMENT_STATES = ("assessed", "abstained")
CONFIDENCE_LEVELS = ("low", "medium", "high")
ABSTAIN_REASONS = (
    "required_evidence_domain_unavailable",
    "insufficient_evidence",
    "ambiguous_or_conflicting_evidence",
    "source_unavailable",
    "outside_protocol",
)
MAX_ASSESSMENT_TTL_SECONDS = 300

FORBIDDEN_EVIDENCE_KEYS = (
    "benchmark_label",
    "future_outcome",
    "future_price",
    "later_price_outcome",
    "raw_transcript",
    "realized_pnl_outcome",
    "recap_judgment",
    "reported_fill",
    "retrospective_label",
    "ross_action",
    "ross_entry",
    "ross_fill",
    "trade_outcome",
    "winning_trade_label",
)
PROHIBITED_OUTPUT_FIELDS = (
    "aggregate_quality_score",
    "candidate_priority",
    "selection_action",
    "trade_recommendation",
    "order_action",
    "position_size",
    "risk_action",
)

_LOWER_HEX = frozenset("0123456789abcdef")
_EVIDENCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._/@+-]*$")
_ATTENTION_ROW_FIELDS = frozenset(
    {
        "symbol",
        "activation_time",
        "decision_time",
        "source_rank_input_ordered_sha256",
        "rank_input_complete_for_members_with_completed_bars",
        "identity_resolved_member_count",
        "rank_members_with_computable_gain_count",
        "candidate_completed_bar_present",
        *FEATURE_NAMES,
    }
)

_KNOWLEDGE_POLICY = {
    "uses_only_evidence_available_by_decision_time": True,
    "uses_raw_transcripts": False,
    "uses_ross_actions": False,
    "uses_retrospective_behavior_labels": False,
    "uses_future_price_or_volume": False,
    "provider_relative_absence_treated_as_universal_absence": False,
    "missing_evidence_may_be_inferred": False,
    "runtime_strategy_effect": "none",
}
_ASSESSMENT_KNOWLEDGE_POLICY = {
    "uses_raw_transcripts": False,
    "uses_ross_actions": False,
    "uses_retrospective_behavior_labels": False,
    "uses_future_price_outcomes": False,
    "may_submit_orders": False,
    "may_raise_deterministic_risk": False,
    "runtime_strategy_effect": "none",
}
_PROHIBITED_OUTPUTS = {field: None for field in PROHIBITED_OUTPUT_FIELDS}


def canonical_fingerprint(payload: object) -> str:
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("payload must be canonical JSON data") from exc
    return hashlib.sha256(encoded).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _LOWER_HEX for character in value)
    )


def _timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed


def _symbol(value: object) -> str:
    symbol = str(value or "").strip().upper()
    if not symbol:
        raise ValueError("symbol is required")
    return symbol


def _find_forbidden_key(payload: object) -> str | None:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            normalized = str(key).strip().lower().replace("-", "_").replace(" ", "_")
            if normalized in FORBIDDEN_EVIDENCE_KEYS:
                return normalized
            nested = _find_forbidden_key(value)
            if nested is not None:
                return nested
    elif isinstance(payload, list):
        for value in payload:
            nested = _find_forbidden_key(value)
            if nested is not None:
                return nested
    return None


def _validate_evidence_id(value: object) -> str:
    if not isinstance(value, str) or not _EVIDENCE_ID_PATTERN.fullmatch(value):
        raise ValueError("evidence_id must be a stable nonempty identifier")
    return value


def _require_exact_keys(
    payload: Mapping[str, object], expected: Iterable[str], field: str
) -> None:
    expected_set = set(expected)
    actual = set(payload)
    if actual != expected_set:
        missing = sorted(expected_set - actual)
        extra = sorted(actual - expected_set)
        raise ValueError(f"{field} fields differ; missing={missing}, extra={extra}")


def validate_context_assessment_contract(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported context-assessment schema")
    if payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected context-assessment contract ID")
    if payload.get("artifact_type") != "causal_shadow_context_assessment_protocol":
        raise ValueError("unexpected context-assessment artifact type")
    if payload.get("status") != "preregistered_schema_only_no_runtime_artifact":
        raise ValueError("unexpected context-assessment protocol status")
    if payload.get("runtime_strategy_effect") != "none":
        raise ValueError("context assessment must remain shadow-only")
    for field in (
        "aggregate_score_frozen",
        "selection_threshold_frozen",
        "ai_order_authority",
        "ai_risk_authority",
        "policy_promotion_eligible",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must be false")

    parents = payload.get("frozen_parents")
    if not isinstance(parents, Mapping):
        raise ValueError("frozen_parents must be an object")
    expected_parents = {
        "micro_policy_id": MICRO_POLICY_ID,
        "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
        "scanner_policy_id": SCANNER_CONTRACT_ID,
        "scanner_policy_fingerprint": SCANNER_POLICY_FINGERPRINT,
        "context_inventory_contract_id": CONTEXT_INVENTORY_CONTRACT_ID,
        "catalyst_interpretation_contract_id": CATALYST_INTERPRETATION_CONTRACT_ID,
    }
    if dict(parents) != expected_parents:
        raise ValueError("frozen parent bindings differ from the protocol")

    sources = payload.get("source_contracts")
    if sources != {
        "scanner": SCANNER_CONTRACT_ID,
        "attention_leadership": ATTENTION_CONTRACT_ID,
        "catalyst_evidence": CATALYST_EVIDENCE_CONTRACT_ID,
    }:
        raise ValueError("source contracts differ from the protocol")
    if payload.get("knowledge_policy") != _KNOWLEDGE_POLICY:
        raise ValueError("knowledge policy differs from the causal protocol")

    snapshot = payload.get("snapshot_protocol")
    if not isinstance(snapshot, Mapping):
        raise ValueError("snapshot_protocol must be an object")
    if snapshot.get("record_type") != RECORD_TYPE_SNAPSHOT:
        raise ValueError("unexpected snapshot record type")
    if snapshot.get("emission_reasons") != list(SNAPSHOT_REASONS):
        raise ValueError("snapshot emission reasons differ from the protocol")
    if snapshot.get("evidence_domains") != list(EVIDENCE_DOMAINS):
        raise ValueError("snapshot evidence domains differ from the protocol")
    if snapshot.get("required_base_domains") != [
        "scanner_market",
        "attention_leadership",
    ]:
        raise ValueError("snapshot base domains differ from the protocol")
    if snapshot.get("forbidden_evidence_keys") != list(FORBIDDEN_EVIDENCE_KEYS):
        raise ValueError("snapshot forbidden evidence keys differ from the protocol")
    if snapshot.get("content_hash_required") is not True:
        raise ValueError("snapshot content hash must be required")

    semantic = payload.get("semantic_assessment_protocol")
    if not isinstance(semantic, Mapping):
        raise ValueError("semantic_assessment_protocol must be an object")
    if semantic.get("record_type") != RECORD_TYPE_ASSESSMENT:
        raise ValueError("unexpected assessment record type")
    if semantic.get("assessment_states") != list(ASSESSMENT_STATES):
        raise ValueError("assessment states differ from the protocol")
    if semantic.get("confidence_levels") != list(CONFIDENCE_LEVELS):
        raise ValueError("confidence levels differ from the protocol")
    if semantic.get("abstain_reasons") != list(ABSTAIN_REASONS):
        raise ValueError("abstain reasons differ from the protocol")
    if semantic.get("max_assessment_ttl_seconds") != MAX_ASSESSMENT_TTL_SECONDS:
        raise ValueError("assessment TTL differs from the protocol")
    if semantic.get("historical_generation_may_postdate_logical_expiry") is not True:
        raise ValueError("historical replay timing rule must be explicit")
    if semantic.get("citations_required_per_assessed_axis") is not True:
        raise ValueError("assessment citations must be required")
    if semantic.get("observed_fact_and_inference_separation_required") is not True:
        raise ValueError("fact and inference separation must be required")

    axes = semantic.get("axes")
    if not isinstance(axes, list) or [row.get("axis_id") for row in axes if isinstance(row, Mapping)] != list(SEMANTIC_AXES):
        raise ValueError("semantic axes differ from the ordered protocol")
    for row in axes:
        if not isinstance(row, Mapping):
            raise ValueError("semantic axis rows must be objects")
        axis_id = str(row["axis_id"])
        if row.get("allowed_evidence_domains") != list(
            AXIS_ALLOWED_EVIDENCE_DOMAINS[axis_id]
        ):
            raise ValueError(f"allowed evidence domains differ for {axis_id}")
        if row.get("values") != list(AXIS_VALUES[axis_id]):
            raise ValueError(f"assessment values differ for {axis_id}")
        if row.get("requires_observed_fact") is not True:
            raise ValueError(f"{axis_id} must require an observed fact")
        if row.get("requires_inference") is not True:
            raise ValueError(f"{axis_id} must require an explicit inference")
        if row.get("abstention_allowed") is not True:
            raise ValueError(f"{axis_id} must allow abstention")

    if semantic.get("value_required_evidence_domains") != {
        key: sorted(value) for key, value in VALUE_REQUIRED_EVIDENCE_DOMAINS.items()
    }:
        raise ValueError("value-specific evidence requirements differ from the protocol")
    if semantic.get("prohibited_outputs") != list(PROHIBITED_OUTPUT_FIELDS):
        raise ValueError("prohibited outputs differ from the protocol")

    evaluation = payload.get("evaluation_boundary")
    if not isinstance(evaluation, Mapping):
        raise ValueError("evaluation_boundary must be an object")
    expected_evaluation = {
        "excluded_fit_panel_id": EXCLUDED_PILOT_PANEL_ID,
        "excluded_fit_comparison_id": EXCLUDED_PILOT_COMPARISON_ID,
        "excluded_fit_comparison_content_sha256": EXCLUDED_PILOT_COMPARISON_SHA256,
        "new_panel_registered_before_recap_review": True,
        "label_blind_runtime_frozen_before_retrospective_labels": True,
        "threshold_fit_on_excluded_panel_allowed": False,
        "policy_promotion_from_protocol_allowed": False,
    }
    if dict(evaluation) != expected_evaluation:
        raise ValueError("evaluation boundary differs from the preregistration")


def load_context_assessment_contract(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("context-assessment contract root must be an object")
    validate_context_assessment_contract(payload)
    return payload


def _evidence_item(
    *,
    evidence_id: str,
    domain: str,
    available_at: str,
    source_contract_id: str,
    source_artifact_content_sha256: str,
    payload: Mapping[str, object],
) -> dict[str, object]:
    _validate_evidence_id(evidence_id)
    if domain not in EVIDENCE_DOMAINS:
        raise ValueError("unsupported evidence domain")
    if not _is_sha256(source_artifact_content_sha256):
        raise ValueError("source artifact hash must be lowercase SHA-256")
    if "transcript" in source_contract_id.lower() or "recap" in source_contract_id.lower():
        raise ValueError("raw transcript or recap contracts cannot supply runtime evidence")
    forbidden = _find_forbidden_key(payload)
    if forbidden is not None:
        raise ValueError(f"evidence payload contains prohibited key: {forbidden}")
    materialized = dict(payload)
    return {
        "evidence_id": evidence_id,
        "domain": domain,
        "available_at": available_at,
        "source_contract_id": source_contract_id,
        "source_artifact_content_sha256": source_artifact_content_sha256,
        "source_record_content_sha256": canonical_fingerprint(materialized),
        "payload": materialized,
    }


def build_context_decision_snapshot(
    scanner_row: Mapping[str, object],
    attention_row: Mapping[str, object],
    *,
    catalyst_packet: Mapping[str, object] | None,
    source_artifact_content_sha256s: Mapping[str, str],
    snapshot_reason: str,
    supplemental_evidence: Iterable[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Compose one label-blind, decision-time context evidence snapshot.

    The builder carries exact source rows and evidence into a hash-bound envelope.
    It does not classify, rank, select, size, or trade a candidate.
    """

    _require_exact_keys(scanner_row, SNAPSHOT_ROW_FIELDS, "scanner_row")
    _require_exact_keys(attention_row, _ATTENTION_ROW_FIELDS, "attention_row")
    if snapshot_reason not in SNAPSHOT_REASONS:
        raise ValueError("unsupported snapshot reason")
    if set(source_artifact_content_sha256s) != set(SOURCE_ARTIFACT_KEYS):
        raise ValueError("source artifact hash keys differ from the protocol")
    source_hashes = {
        key: str(source_artifact_content_sha256s[key]) for key in SOURCE_ARTIFACT_KEYS
    }
    if any(not _is_sha256(value) for value in source_hashes.values()):
        raise ValueError("source artifact hashes must be lowercase SHA-256")

    symbol = _symbol(scanner_row.get("symbol"))
    activation = _timestamp(scanner_row.get("activation_time"), "activation_time")
    decision = _timestamp(scanner_row.get("decision_time"), "decision_time")
    if activation > decision:
        raise ValueError("activation_time cannot follow decision_time")
    if snapshot_reason == "candidate_activation" and activation != decision:
        raise ValueError("candidate-activation snapshot must occur at activation_time")
    if _symbol(attention_row.get("symbol")) != symbol:
        raise ValueError("attention row symbol differs from scanner row")
    if attention_row.get("activation_time") != scanner_row.get("activation_time"):
        raise ValueError("attention activation time differs from scanner row")
    if attention_row.get("decision_time") != scanner_row.get("decision_time"):
        raise ValueError("attention decision time differs from scanner row")
    if attention_row.get("source_rank_input_ordered_sha256") != scanner_row.get(
        "rank_input_ordered_sha256"
    ):
        raise ValueError("attention/scanner rank lineage mismatch")

    scanner_payload = dict(scanner_row)
    attention_payload = dict(attention_row)
    scanner_hash = canonical_fingerprint(scanner_payload)
    attention_hash = canonical_fingerprint(attention_payload)
    items = [
        _evidence_item(
            evidence_id=f"scanner:{scanner_hash}",
            domain="scanner_market",
            available_at=str(scanner_row["decision_time"]),
            source_contract_id=SCANNER_CONTRACT_ID,
            source_artifact_content_sha256=source_hashes["scanner_runtime"],
            payload=scanner_payload,
        ),
        _evidence_item(
            evidence_id=f"attention:{attention_hash}",
            domain="attention_leadership",
            available_at=str(attention_row["decision_time"]),
            source_contract_id=ATTENTION_CONTRACT_ID,
            source_artifact_content_sha256=source_hashes["attention_runtime"],
            payload=attention_payload,
        ),
    ]

    if catalyst_packet is not None:
        _require_exact_keys(catalyst_packet, PACKET_FIELDS, "catalyst_packet")
        events, packet_hash = _validate_packet(catalyst_packet)
        if _symbol(catalyst_packet.get("symbol")) != symbol:
            raise ValueError("catalyst packet symbol differs from scanner row")
        if catalyst_packet.get("activation_time") != scanner_row.get("activation_time"):
            raise ValueError("catalyst activation time differs from scanner row")
        packet_decision = _timestamp(
            catalyst_packet.get("decision_time"), "catalyst decision_time"
        )
        if packet_decision > decision:
            raise ValueError("future catalyst packet cannot enter a decision snapshot")
        unsigned_packet = {
            key: value
            for key, value in catalyst_packet.items()
            if key != "packet_content_sha256"
        }
        items.append(
            _evidence_item(
                evidence_id=f"catalyst-packet:{packet_hash}",
                domain="catalyst_chronology",
                available_at=str(catalyst_packet["decision_time"]),
                source_contract_id=CATALYST_EVIDENCE_CONTRACT_ID,
                source_artifact_content_sha256=source_hashes[
                    "catalyst_evidence_runtime"
                ],
                payload=unsigned_packet,
            )
        )
        for event in events:
            _require_exact_keys(event, EVENT_FIELDS, "catalyst event")
            published = _timestamp(event.get("published_at"), "headline published_at")
            if published > packet_decision:
                raise ValueError("future headline cannot enter a catalyst packet")
            expected_age = (packet_decision - published).total_seconds()
            if event.get("seconds_old_at_decision") != expected_age:
                raise ValueError("headline age differs from decision-time chronology")
            headline_id = _validate_evidence_id(str(event["headline_id"]))
            items.append(
                _evidence_item(
                    evidence_id=f"headline:{headline_id}",
                    domain="catalyst_headline",
                    available_at=str(event["published_at"]),
                    source_contract_id=CATALYST_EVIDENCE_CONTRACT_ID,
                    source_artifact_content_sha256=source_hashes[
                        "catalyst_evidence_runtime"
                    ],
                    payload=event,
                )
            )

    for source in supplemental_evidence:
        if not isinstance(source, Mapping):
            raise ValueError("supplemental evidence rows must be objects")
        _require_exact_keys(
            source,
            {
                "evidence_id",
                "domain",
                "available_at",
                "source_contract_id",
                "source_artifact_content_sha256",
                "payload",
            },
            "supplemental evidence",
        )
        domain = str(source["domain"])
        if domain not in SUPPLEMENTAL_EVIDENCE_DOMAINS:
            raise ValueError("supplemental evidence cannot replace a base domain")
        supplemental_payload = source["payload"]
        if not isinstance(supplemental_payload, Mapping):
            raise ValueError("supplemental evidence payload must be an object")
        items.append(
            _evidence_item(
                evidence_id=str(source["evidence_id"]),
                domain=domain,
                available_at=str(source["available_at"]),
                source_contract_id=str(source["source_contract_id"]),
                source_artifact_content_sha256=str(
                    source["source_artifact_content_sha256"]
                ),
                payload=supplemental_payload,
            )
        )

    items.sort(key=lambda row: (str(row["domain"]), str(row["evidence_id"])))
    evidence_ids = [str(row["evidence_id"]) for row in items]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("evidence IDs must be unique within a snapshot")
    coverage = {
        domain: {
            "evidence_present": any(row["domain"] == domain for row in items),
            "evidence_ids": sorted(
                str(row["evidence_id"])
                for row in items
                if row["domain"] == domain
            ),
        }
        for domain in EVIDENCE_DOMAINS
    }

    snapshot: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "record_type": RECORD_TYPE_SNAPSHOT,
        "runtime_strategy_effect": "none",
        "symbol": symbol,
        "activation_time": scanner_row["activation_time"],
        "decision_time": scanner_row["decision_time"],
        "snapshot_reason": snapshot_reason,
        "source_artifact_content_sha256s": source_hashes,
        "knowledge_policy": dict(_KNOWLEDGE_POLICY),
        "evidence_coverage": coverage,
        "evidence_items": items,
        "prohibited_outputs": dict(_PROHIBITED_OUTPUTS),
    }
    snapshot["snapshot_content_sha256"] = canonical_fingerprint(snapshot)
    validate_context_decision_snapshot(snapshot)
    return snapshot


def validate_context_decision_snapshot(snapshot: Mapping[str, object]) -> None:
    _require_exact_keys(
        snapshot,
        {
            "schema_version",
            "contract_id",
            "record_type",
            "runtime_strategy_effect",
            "symbol",
            "activation_time",
            "decision_time",
            "snapshot_reason",
            "source_artifact_content_sha256s",
            "knowledge_policy",
            "evidence_coverage",
            "evidence_items",
            "prohibited_outputs",
            "snapshot_content_sha256",
        },
        "context snapshot",
    )
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported context snapshot schema")
    if snapshot.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected context snapshot contract")
    if snapshot.get("record_type") != RECORD_TYPE_SNAPSHOT:
        raise ValueError("unexpected context snapshot record type")
    if snapshot.get("runtime_strategy_effect") != "none":
        raise ValueError("context snapshot cannot affect strategy runtime")
    claimed = snapshot.get("snapshot_content_sha256")
    unsigned = {
        key: value
        for key, value in snapshot.items()
        if key != "snapshot_content_sha256"
    }
    if not _is_sha256(claimed) or canonical_fingerprint(unsigned) != claimed:
        raise ValueError("context snapshot fingerprint mismatch")
    if snapshot.get("knowledge_policy") != _KNOWLEDGE_POLICY:
        raise ValueError("context snapshot violates the knowledge policy")
    if snapshot.get("prohibited_outputs") != _PROHIBITED_OUTPUTS:
        raise ValueError("context snapshot contains strategy outputs")

    symbol = _symbol(snapshot.get("symbol"))
    activation = _timestamp(snapshot.get("activation_time"), "activation_time")
    decision = _timestamp(snapshot.get("decision_time"), "decision_time")
    if activation > decision:
        raise ValueError("activation_time cannot follow decision_time")
    reason = snapshot.get("snapshot_reason")
    if reason not in SNAPSHOT_REASONS:
        raise ValueError("unsupported snapshot reason")
    if reason == "candidate_activation" and activation != decision:
        raise ValueError("candidate-activation snapshot must occur at activation_time")

    source_hashes = snapshot.get("source_artifact_content_sha256s")
    if not isinstance(source_hashes, Mapping) or set(source_hashes) != set(
        SOURCE_ARTIFACT_KEYS
    ):
        raise ValueError("context snapshot source hashes differ from the protocol")
    if any(not _is_sha256(value) for value in source_hashes.values()):
        raise ValueError("context snapshot source hashes must be SHA-256")

    items = snapshot.get("evidence_items")
    if not isinstance(items, list) or not items:
        raise ValueError("context snapshot requires evidence items")
    by_id: dict[str, Mapping[str, object]] = {}
    by_domain: dict[str, list[str]] = {domain: [] for domain in EVIDENCE_DOMAINS}
    for source in items:
        if not isinstance(source, Mapping):
            raise ValueError("context evidence items must be objects")
        _require_exact_keys(
            source,
            {
                "evidence_id",
                "domain",
                "available_at",
                "source_contract_id",
                "source_artifact_content_sha256",
                "source_record_content_sha256",
                "payload",
            },
            "context evidence item",
        )
        evidence_id = _validate_evidence_id(source.get("evidence_id"))
        if evidence_id in by_id:
            raise ValueError("context snapshot evidence IDs must be unique")
        by_id[evidence_id] = source
        domain = str(source.get("domain"))
        if domain not in EVIDENCE_DOMAINS:
            raise ValueError("unsupported context evidence domain")
        by_domain[domain].append(evidence_id)
        available = _timestamp(source.get("available_at"), "evidence available_at")
        if available > decision:
            raise ValueError("future evidence cannot enter a decision snapshot")
        source_contract_id = str(source.get("source_contract_id") or "")
        if not source_contract_id:
            raise ValueError("evidence source contract is required")
        if "transcript" in source_contract_id.lower() or "recap" in source_contract_id.lower():
            raise ValueError("raw transcript or recap evidence is prohibited")
        if not _is_sha256(source.get("source_artifact_content_sha256")):
            raise ValueError("evidence source artifact hash must be SHA-256")
        payload = source.get("payload")
        if not isinstance(payload, Mapping):
            raise ValueError("evidence payload must be an object")
        forbidden = _find_forbidden_key(payload)
        if forbidden is not None:
            raise ValueError(f"evidence payload contains prohibited key: {forbidden}")
        if source.get("source_record_content_sha256") != canonical_fingerprint(payload):
            raise ValueError("evidence source-record fingerprint mismatch")

    if len(by_domain["scanner_market"]) != 1:
        raise ValueError("context snapshot requires exactly one scanner row")
    if len(by_domain["attention_leadership"]) != 1:
        raise ValueError("context snapshot requires exactly one attention row")
    if len(by_domain["catalyst_chronology"]) > 1:
        raise ValueError("context snapshot allows at most one catalyst packet")

    scanner_item = by_id[by_domain["scanner_market"][0]]
    attention_item = by_id[by_domain["attention_leadership"][0]]
    if scanner_item["source_contract_id"] != SCANNER_CONTRACT_ID:
        raise ValueError("scanner evidence has the wrong source contract")
    if attention_item["source_contract_id"] != ATTENTION_CONTRACT_ID:
        raise ValueError("attention evidence has the wrong source contract")
    if scanner_item["source_artifact_content_sha256"] != source_hashes["scanner_runtime"]:
        raise ValueError("scanner evidence source artifact mismatch")
    if attention_item["source_artifact_content_sha256"] != source_hashes["attention_runtime"]:
        raise ValueError("attention evidence source artifact mismatch")
    scanner_payload = scanner_item["payload"]
    attention_payload = attention_item["payload"]
    assert isinstance(scanner_payload, Mapping)
    assert isinstance(attention_payload, Mapping)
    _require_exact_keys(scanner_payload, SNAPSHOT_ROW_FIELDS, "scanner evidence payload")
    _require_exact_keys(
        attention_payload, _ATTENTION_ROW_FIELDS, "attention evidence payload"
    )
    if _symbol(scanner_payload.get("symbol")) != symbol:
        raise ValueError("scanner evidence symbol differs from snapshot")
    if scanner_payload.get("activation_time") != snapshot.get("activation_time"):
        raise ValueError("scanner evidence activation differs from snapshot")
    if scanner_payload.get("decision_time") != snapshot.get("decision_time"):
        raise ValueError("scanner evidence decision differs from snapshot")
    if _symbol(attention_payload.get("symbol")) != symbol:
        raise ValueError("attention evidence symbol differs from snapshot")
    if attention_payload.get("activation_time") != snapshot.get("activation_time"):
        raise ValueError("attention evidence activation differs from snapshot")
    if attention_payload.get("decision_time") != snapshot.get("decision_time"):
        raise ValueError("attention evidence decision differs from snapshot")
    if attention_payload.get("source_rank_input_ordered_sha256") != scanner_payload.get(
        "rank_input_ordered_sha256"
    ):
        raise ValueError("scanner and attention evidence rank lineage mismatch")

    headline_items = [by_id[value] for value in by_domain["catalyst_headline"]]
    if by_domain["catalyst_chronology"]:
        packet_item = by_id[by_domain["catalyst_chronology"][0]]
        if packet_item["source_contract_id"] != CATALYST_EVIDENCE_CONTRACT_ID:
            raise ValueError("catalyst packet has the wrong source contract")
        if packet_item["source_artifact_content_sha256"] != source_hashes[
            "catalyst_evidence_runtime"
        ]:
            raise ValueError("catalyst packet source artifact mismatch")
        unsigned_packet = packet_item["payload"]
        assert isinstance(unsigned_packet, Mapping)
        packet = dict(unsigned_packet)
        packet["packet_content_sha256"] = packet_item[
            "source_record_content_sha256"
        ]
        _require_exact_keys(packet, PACKET_FIELDS, "catalyst packet evidence payload")
        events, _ = _validate_packet(packet)
        if _symbol(packet.get("symbol")) != symbol:
            raise ValueError("catalyst packet symbol differs from snapshot")
        if packet.get("activation_time") != snapshot.get("activation_time"):
            raise ValueError("catalyst packet activation differs from snapshot")
        packet_decision = _timestamp(packet.get("decision_time"), "catalyst decision_time")
        if packet_decision > decision:
            raise ValueError("future catalyst packet cannot enter a snapshot")
        expected_headline_ids = {f"headline:{event['headline_id']}" for event in events}
        if set(by_domain["catalyst_headline"]) != expected_headline_ids:
            raise ValueError("headline evidence does not match the catalyst packet")
        for event in events:
            published = _timestamp(event.get("published_at"), "headline published_at")
            if published > packet_decision:
                raise ValueError("future headline cannot enter a catalyst packet")
            expected_age = (packet_decision - published).total_seconds()
            if event.get("seconds_old_at_decision") != expected_age:
                raise ValueError("headline age differs from catalyst chronology")
            item = by_id[f"headline:{event['headline_id']}"]
            if item["source_contract_id"] != CATALYST_EVIDENCE_CONTRACT_ID:
                raise ValueError("headline evidence has the wrong source contract")
            if item["source_artifact_content_sha256"] != source_hashes[
                "catalyst_evidence_runtime"
            ]:
                raise ValueError("headline source artifact mismatch")
            if item["available_at"] != event["published_at"] or item["payload"] != event:
                raise ValueError("headline evidence differs from the catalyst packet")
    elif headline_items:
        raise ValueError("headline evidence requires a catalyst chronology packet")

    coverage = snapshot.get("evidence_coverage")
    if not isinstance(coverage, Mapping) or set(coverage) != set(EVIDENCE_DOMAINS):
        raise ValueError("context evidence coverage differs from the protocol")
    for domain in EVIDENCE_DOMAINS:
        expected_ids = sorted(by_domain[domain])
        if coverage.get(domain) != {
            "evidence_present": bool(expected_ids),
            "evidence_ids": expected_ids,
        }:
            raise ValueError(f"evidence coverage mismatch for {domain}")


def _normalize_claims(
    value: object,
    *,
    field: str,
    available_evidence_ids: set[str],
    allowed_evidence_ids: set[str],
) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    claims: list[dict[str, object]] = []
    seen: set[str] = set()
    for source in value:
        if not isinstance(source, Mapping):
            raise ValueError(f"{field} rows must be objects")
        _require_exact_keys(
            source, {"claim_id", "statement", "evidence_ids"}, f"{field} claim"
        )
        claim_id = _validate_evidence_id(source.get("claim_id"))
        if claim_id in seen:
            raise ValueError(f"{field} claim IDs must be unique")
        seen.add(claim_id)
        statement = str(source.get("statement") or "").strip()
        if not statement:
            raise ValueError(f"{field} claim statement is required")
        evidence_ids = source.get("evidence_ids")
        if (
            not isinstance(evidence_ids, list)
            or not evidence_ids
            or any(not isinstance(item, str) for item in evidence_ids)
            or len(evidence_ids) != len(set(evidence_ids))
        ):
            raise ValueError(f"{field} claim requires unique evidence IDs")
        cited = set(evidence_ids)
        if not cited.issubset(available_evidence_ids):
            raise ValueError(f"{field} claim cites unavailable evidence")
        if not cited.issubset(allowed_evidence_ids):
            raise ValueError(f"{field} claim cites an evidence domain outside its axis")
        claims.append(
            {
                "claim_id": claim_id,
                "statement": statement,
                "evidence_ids": sorted(cited),
            }
        )
    return sorted(claims, key=lambda row: str(row["claim_id"]))


def _normalize_axis_assessment(
    axis_id: str,
    source: Mapping[str, object],
    *,
    evidence_domains: Mapping[str, str],
) -> dict[str, object]:
    _require_exact_keys(
        source,
        {
            "state",
            "value",
            "confidence",
            "evidence_ids",
            "observed_facts",
            "inferences",
            "abstain_reason",
        },
        f"{axis_id} assessment",
    )
    state = source.get("state")
    if state not in ASSESSMENT_STATES:
        raise ValueError(f"unsupported assessment state for {axis_id}")
    available_ids = set(evidence_domains)
    allowed_domains = set(AXIS_ALLOWED_EVIDENCE_DOMAINS[axis_id])
    allowed_ids = {
        evidence_id
        for evidence_id, domain in evidence_domains.items()
        if domain in allowed_domains
    }
    raw_evidence_ids = source.get("evidence_ids")
    if (
        not isinstance(raw_evidence_ids, list)
        or any(not isinstance(item, str) for item in raw_evidence_ids)
        or len(raw_evidence_ids) != len(set(raw_evidence_ids))
    ):
        raise ValueError(f"{axis_id}.evidence_ids must be a unique string list")
    cited_ids = set(raw_evidence_ids)
    if not cited_ids.issubset(available_ids):
        raise ValueError(f"{axis_id} cites unavailable evidence")
    if not cited_ids.issubset(allowed_ids):
        raise ValueError(f"{axis_id} cites evidence outside its allowed domains")

    observed = _normalize_claims(
        source.get("observed_facts"),
        field=f"{axis_id}.observed_facts",
        available_evidence_ids=available_ids,
        allowed_evidence_ids=allowed_ids,
    )
    inferences = _normalize_claims(
        source.get("inferences"),
        field=f"{axis_id}.inferences",
        available_evidence_ids=available_ids,
        allowed_evidence_ids=allowed_ids,
    )
    claim_ids = [str(row["claim_id"]) for row in observed + inferences]
    if len(claim_ids) != len(set(claim_ids)):
        raise ValueError(f"{axis_id} claim IDs must be unique across facts and inferences")
    claim_evidence_ids = {
        evidence_id
        for row in observed + inferences
        for evidence_id in row["evidence_ids"]  # type: ignore[index]
    }
    if cited_ids != claim_evidence_ids:
        raise ValueError(f"{axis_id} evidence_ids must equal the claim citation union")

    value = source.get("value")
    confidence = source.get("confidence")
    abstain_reason = source.get("abstain_reason")
    if state == "assessed":
        if value not in AXIS_VALUES[axis_id]:
            raise ValueError(f"unsupported assessment value for {axis_id}")
        if confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"unsupported confidence for {axis_id}")
        if abstain_reason is not None:
            raise ValueError(f"assessed axis {axis_id} cannot include an abstain reason")
        if not cited_ids or not observed or not inferences:
            raise ValueError(
                f"assessed axis {axis_id} requires citations, observed facts, and inference"
            )
        cited_domains = {evidence_domains[evidence_id] for evidence_id in cited_ids}
        required_domains = VALUE_REQUIRED_EVIDENCE_DOMAINS.get(str(value), set())
        if not required_domains.issubset(cited_domains):
            raise ValueError(f"{axis_id} value lacks its required evidence domain")
    else:
        if value is not None or confidence is not None:
            raise ValueError(f"abstained axis {axis_id} cannot contain value or confidence")
        if abstain_reason not in ABSTAIN_REASONS:
            raise ValueError(f"unsupported abstain reason for {axis_id}")
        if inferences:
            raise ValueError(f"abstained axis {axis_id} cannot contain an inference")
        if not allowed_ids and abstain_reason != "required_evidence_domain_unavailable":
            raise ValueError(
                f"{axis_id} must identify unavailable required evidence when none exists"
            )

    return {
        "state": state,
        "value": value,
        "confidence": confidence,
        "evidence_ids": sorted(cited_ids),
        "observed_facts": observed,
        "inferences": inferences,
        "abstain_reason": abstain_reason,
    }


def build_shadow_context_assessment(
    snapshot: Mapping[str, object],
    *,
    axis_assessments: Mapping[str, Mapping[str, object]],
    model_provenance: Mapping[str, object],
    expires_at: str,
) -> dict[str, object]:
    """Bind an abstaining AI shadow assessment to one exact causal snapshot."""

    validate_context_decision_snapshot(snapshot)
    if set(axis_assessments) != set(SEMANTIC_AXES):
        raise ValueError("axis assessments must match the complete protocol")
    _require_exact_keys(
        model_provenance,
        {
            "provider",
            "model_id",
            "prompt_id",
            "prompt_content_sha256",
            "generated_at",
            "label_blind_run_id",
        },
        "model provenance",
    )
    for field in ("provider", "model_id", "prompt_id", "label_blind_run_id"):
        if not str(model_provenance.get(field) or "").strip():
            raise ValueError(f"model_provenance.{field} is required")
    if not _is_sha256(model_provenance.get("prompt_content_sha256")):
        raise ValueError("model prompt hash must be lowercase SHA-256")
    decision = _timestamp(snapshot.get("decision_time"), "decision_time")
    generated = _timestamp(model_provenance.get("generated_at"), "generated_at")
    if generated < decision:
        raise ValueError("assessment generation cannot predate its evidence snapshot")
    expires = _timestamp(expires_at, "expires_at")
    ttl = (expires - decision).total_seconds()
    if not 0 < ttl <= MAX_ASSESSMENT_TTL_SECONDS:
        raise ValueError("assessment expiry exceeds the bounded logical TTL")

    items = snapshot["evidence_items"]
    assert isinstance(items, list)
    evidence_domains = {
        str(row["evidence_id"]): str(row["domain"])
        for row in items
        if isinstance(row, Mapping)
    }
    normalized_axes = {
        axis_id: _normalize_axis_assessment(
            axis_id,
            axis_assessments[axis_id],
            evidence_domains=evidence_domains,
        )
        for axis_id in SEMANTIC_AXES
    }
    record: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "record_type": RECORD_TYPE_ASSESSMENT,
        "runtime_strategy_effect": "none",
        "symbol": snapshot["symbol"],
        "decision_time": snapshot["decision_time"],
        "logical_expires_at": expires_at,
        "source_snapshot_content_sha256": snapshot["snapshot_content_sha256"],
        "assessment_origin": "shadow_ai",
        "model_provenance": dict(model_provenance),
        "knowledge_policy": dict(_ASSESSMENT_KNOWLEDGE_POLICY),
        "axes": normalized_axes,
        "prohibited_outputs": dict(_PROHIBITED_OUTPUTS),
    }
    record["assessment_content_sha256"] = canonical_fingerprint(record)
    validate_shadow_context_assessment(record, snapshot=snapshot)
    return record


def validate_shadow_context_assessment(
    record: Mapping[str, object],
    *,
    snapshot: Mapping[str, object],
) -> None:
    validate_context_decision_snapshot(snapshot)
    _require_exact_keys(
        record,
        {
            "schema_version",
            "contract_id",
            "record_type",
            "runtime_strategy_effect",
            "symbol",
            "decision_time",
            "logical_expires_at",
            "source_snapshot_content_sha256",
            "assessment_origin",
            "model_provenance",
            "knowledge_policy",
            "axes",
            "prohibited_outputs",
            "assessment_content_sha256",
        },
        "shadow context assessment",
    )
    if record.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported shadow context-assessment schema")
    if record.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected shadow context-assessment contract")
    if record.get("record_type") != RECORD_TYPE_ASSESSMENT:
        raise ValueError("unexpected shadow context-assessment record type")
    if record.get("runtime_strategy_effect") != "none":
        raise ValueError("shadow context assessment cannot affect runtime")
    claimed = record.get("assessment_content_sha256")
    unsigned = {
        key: value
        for key, value in record.items()
        if key != "assessment_content_sha256"
    }
    if not _is_sha256(claimed) or canonical_fingerprint(unsigned) != claimed:
        raise ValueError("shadow context-assessment fingerprint mismatch")
    if record.get("symbol") != snapshot.get("symbol"):
        raise ValueError("assessment symbol differs from source snapshot")
    if record.get("decision_time") != snapshot.get("decision_time"):
        raise ValueError("assessment decision time differs from source snapshot")
    if record.get("source_snapshot_content_sha256") != snapshot.get(
        "snapshot_content_sha256"
    ):
        raise ValueError("assessment source snapshot fingerprint mismatch")
    if record.get("assessment_origin") != "shadow_ai":
        raise ValueError("context assessment origin must remain shadow AI")
    if record.get("knowledge_policy") != _ASSESSMENT_KNOWLEDGE_POLICY:
        raise ValueError("shadow assessment violates the knowledge policy")
    if record.get("prohibited_outputs") != _PROHIBITED_OUTPUTS:
        raise ValueError("shadow assessment contains prohibited strategy outputs")

    model = record.get("model_provenance")
    if not isinstance(model, Mapping):
        raise ValueError("assessment model provenance must be an object")
    _require_exact_keys(
        model,
        {
            "provider",
            "model_id",
            "prompt_id",
            "prompt_content_sha256",
            "generated_at",
            "label_blind_run_id",
        },
        "model provenance",
    )
    for field in ("provider", "model_id", "prompt_id", "label_blind_run_id"):
        if not str(model.get(field) or "").strip():
            raise ValueError(f"model_provenance.{field} is required")
    if not _is_sha256(model.get("prompt_content_sha256")):
        raise ValueError("model prompt hash must be SHA-256")
    decision = _timestamp(record.get("decision_time"), "decision_time")
    if _timestamp(model.get("generated_at"), "generated_at") < decision:
        raise ValueError("assessment generation cannot predate the evidence snapshot")
    ttl = (
        _timestamp(record.get("logical_expires_at"), "logical_expires_at")
        - decision
    ).total_seconds()
    if not 0 < ttl <= MAX_ASSESSMENT_TTL_SECONDS:
        raise ValueError("assessment expiry exceeds the bounded logical TTL")

    axes = record.get("axes")
    if not isinstance(axes, Mapping) or set(axes) != set(SEMANTIC_AXES):
        raise ValueError("assessment axes differ from the protocol")
    items = snapshot["evidence_items"]
    assert isinstance(items, list)
    evidence_domains = {
        str(row["evidence_id"]): str(row["domain"])
        for row in items
        if isinstance(row, Mapping)
    }
    for axis_id in SEMANTIC_AXES:
        source = axes[axis_id]
        if not isinstance(source, Mapping):
            raise ValueError(f"{axis_id} assessment must be an object")
        normalized = _normalize_axis_assessment(
            axis_id, source, evidence_domains=evidence_domains
        )
        if dict(source) != normalized:
            raise ValueError(f"{axis_id} assessment is not canonically ordered")
