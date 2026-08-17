from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Mapping


SCHEMA_VERSION = 1
CONTRACT_ID = "catalyst-interpretation-protocol-shadow-v0.1"
SOURCE_PACKET_CONTRACT_ID = "catalyst-evidence-packet-shadow-v0.1"

ASSESSMENT_FIELDS = (
    "assessment_origin",
    "issuer_relevance",
    "headline_form",
    "event_type",
    "novelty",
    "materiality",
    "dilution_risk",
    "theme_fit",
    "evidence_headline_ids",
    "observation_codes",
    "uncertainty_reasons",
)

ENUMS = {
    "assessment_origin": ("manual_research_example", "shadow_ai"),
    "issuer_relevance": (
        "direct_candidate",
        "incidental_or_ambiguous",
        "unrelated",
        "ambiguous",
        "not_assessable_no_provider_event",
    ),
    "headline_form": (
        "issuer_specific_event",
        "multi_symbol_roundup_or_summary",
        "general_market_or_sector_item",
        "ambiguous",
        "not_assessable_no_provider_event",
    ),
    "event_type": (
        "commercial_agreement",
        "financial_result_or_guidance",
        "financing_or_capital_structure",
        "clinical_or_regulatory",
        "merger_or_corporate_action",
        "filing_or_compliance",
        "market_roundup",
        "market_move_or_halt",
        "other_specific_event",
        "unknown",
        "not_assessable_no_provider_event",
    ),
    "novelty": (
        "unknown_missing_prior_event_corpus",
        "not_assessable_no_provider_event",
    ),
    "materiality": (
        "unknown_title_only",
        "not_assessable_no_provider_event",
    ),
    "dilution_risk": (
        "title_signals_possible_dilution",
        "unknown_title_only",
        "not_assessable_no_provider_event",
    ),
    "theme_fit": (
        "unknown_no_causal_theme_state",
        "not_assessable_no_provider_event",
    ),
}

OBSERVATION_CODES = (
    "no_provider_event",
    "provider_scope_single_symbol",
    "provider_scope_multi_symbol",
    "provider_scope_mixed",
    "title_foregrounds_candidate",
    "title_foregrounds_other_issuer",
    "commercial_agreement_language",
    "market_roundup_language",
    "numeric_terms_present",
    "filing_or_compliance_language",
    "market_move_or_halt_language",
)

UNCERTAINTY_REASONS = (
    "title_only_no_article_body",
    "no_prior_event_corpus",
    "no_causal_theme_state",
    "no_filing_corroboration",
    "provider_symbol_tag_not_proof_of_relevance",
    "candidate_not_title_focus",
    "terms_not_quantified",
    "event_scope_mixed",
    "no_provider_event",
    "provider_relative_absence_only",
)

NO_EVENT_VALUE = "not_assessable_no_provider_event"
EVENT_REQUIRED_UNCERTAINTIES = {
    "title_only_no_article_body",
    "no_prior_event_corpus",
    "no_causal_theme_state",
    "no_filing_corroboration",
}
NO_EVENT_REQUIRED_UNCERTAINTIES = {
    "no_provider_event",
    "provider_relative_absence_only",
    "no_causal_theme_state",
}


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_catalyst_interpretation_contract(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported catalyst-interpretation schema")
    if payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected catalyst-interpretation contract ID")
    if payload.get("artifact_type") != "shadow_catalyst_interpretation_protocol":
        raise ValueError("unexpected catalyst-interpretation artifact type")
    if payload.get("runtime_strategy_effect") != "none":
        raise ValueError("catalyst interpretation must remain shadow-only")
    for field in (
        "quality_score_frozen",
        "selection_threshold_frozen",
        "ai_order_authority",
        "ai_risk_authority",
        "policy_promotion_eligible",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must be false")

    source = payload.get("source_contract")
    if not isinstance(source, Mapping) or source.get("contract_id") != SOURCE_PACKET_CONTRACT_ID:
        raise ValueError("unexpected catalyst evidence-packet source contract")

    fields = payload.get("assessment_fields")
    if not isinstance(fields, list) or tuple(fields) != ASSESSMENT_FIELDS:
        raise ValueError("assessment_fields must match the frozen ordered contract")
    enums = payload.get("enums")
    if not isinstance(enums, Mapping):
        raise ValueError("enums must be an object")
    if set(enums) != set(ENUMS):
        raise ValueError("enum fields must match the frozen interpretation axes")
    for field, values in ENUMS.items():
        if enums.get(field) != list(values):
            raise ValueError(f"enum {field} differs from the frozen contract")
    if payload.get("observation_codes") != list(OBSERVATION_CODES):
        raise ValueError("observation_codes differ from the frozen contract")
    if payload.get("uncertainty_reasons") != list(UNCERTAINTY_REASONS):
        raise ValueError("uncertainty_reasons differ from the frozen contract")

    guards = payload.get("required_unknown_guards")
    if not isinstance(guards, Mapping):
        raise ValueError("required_unknown_guards must be an object")
    expected = {
        "novelty_without_prior_event_corpus": "unknown_missing_prior_event_corpus",
        "materiality_from_title_only": "unknown_title_only",
        "theme_fit_without_causal_theme_state": "unknown_no_causal_theme_state",
    }
    if dict(guards) != expected:
        raise ValueError("required_unknown_guards differ from the frozen contract")


def load_catalyst_interpretation_contract(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("catalyst-interpretation contract root must be an object")
    validate_catalyst_interpretation_contract(payload)
    return payload


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


def _validate_packet(packet: Mapping[str, object]) -> tuple[list[dict[str, object]], str]:
    claimed_hash = packet.get("packet_content_sha256")
    if not isinstance(claimed_hash, str) or len(claimed_hash) != 64:
        raise ValueError("packet_content_sha256 must be a SHA-256")
    unsigned = {key: value for key, value in packet.items() if key != "packet_content_sha256"}
    if _fingerprint(unsigned) != claimed_hash:
        raise ValueError("catalyst evidence packet hash mismatch")
    if not str(packet.get("symbol", "")).strip():
        raise ValueError("catalyst evidence packet requires a symbol")
    _timestamp(packet.get("activation_time"), "activation_time")
    _timestamp(packet.get("decision_time"), "decision_time")
    events = packet.get("events")
    if not isinstance(events, list):
        raise ValueError("packet events must be a list")
    if packet.get("provider_news_event_count_as_of") != len(events):
        raise ValueError("packet event count mismatch")
    seen: set[str] = set()
    normalized: list[dict[str, object]] = []
    for source in events:
        if not isinstance(source, Mapping):
            raise ValueError("packet events must be objects")
        event = dict(source)
        headline_id = str(event.get("headline_id", "")).strip()
        if not headline_id or headline_id in seen:
            raise ValueError("packet headline IDs must be nonempty and unique")
        seen.add(headline_id)
        symbols = event.get("provider_symbols")
        if not isinstance(symbols, list) or not symbols:
            raise ValueError("provider_symbols must be nonempty")
        if event.get("provider_symbol_count") != len(symbols):
            raise ValueError("provider symbol count mismatch")
        if event.get("single_symbol_story") is not (len(symbols) == 1):
            raise ValueError("single-symbol flag mismatch")
        if not str(event.get("title", "")).strip():
            raise ValueError("event title is required")
        normalized.append(event)
    return normalized, claimed_hash


def _provider_scope(events: list[dict[str, object]]) -> str:
    if not events:
        return "no_provider_event"
    sizes = [int(event["provider_symbol_count"]) for event in events]
    if all(size == 1 for size in sizes):
        return "single_symbol_only"
    if all(size > 1 for size in sizes):
        return "multi_symbol_only"
    return "mixed_scope"


def build_catalyst_interpretation_record(
    packet: Mapping[str, object],
    assessment: Mapping[str, object],
) -> dict[str, object]:
    """Bind a structured shadow interpretation to one causal evidence packet."""

    events, packet_hash = _validate_packet(packet)
    if set(assessment) != set(ASSESSMENT_FIELDS):
        raise ValueError("assessment fields must match the frozen contract")

    normalized: dict[str, object] = {}
    for field in ASSESSMENT_FIELDS[:8]:
        value = assessment.get(field)
        if value not in ENUMS[field]:
            raise ValueError(f"unsupported {field} value")
        normalized[field] = value

    available_ids = {str(event["headline_id"]) for event in events}
    evidence_ids = assessment.get("evidence_headline_ids")
    if not isinstance(evidence_ids, list) or any(not isinstance(item, str) for item in evidence_ids):
        raise ValueError("evidence_headline_ids must be a string list")
    if len(evidence_ids) != len(set(evidence_ids)) or not set(evidence_ids).issubset(available_ids):
        raise ValueError("assessment references unavailable headline evidence")
    normalized["evidence_headline_ids"] = sorted(evidence_ids)

    observations = assessment.get("observation_codes")
    if not isinstance(observations, list) or any(item not in OBSERVATION_CODES for item in observations):
        raise ValueError("unsupported observation code")
    if len(observations) != len(set(observations)):
        raise ValueError("observation codes must be unique")
    normalized["observation_codes"] = sorted(observations)

    uncertainties = assessment.get("uncertainty_reasons")
    if not isinstance(uncertainties, list) or any(item not in UNCERTAINTY_REASONS for item in uncertainties):
        raise ValueError("unsupported uncertainty reason")
    if len(uncertainties) != len(set(uncertainties)):
        raise ValueError("uncertainty reasons must be unique")
    uncertainty_set = set(uncertainties)
    normalized["uncertainty_reasons"] = sorted(uncertainties)

    scope = _provider_scope(events)
    expected_scope_observation = {
        "no_provider_event": "no_provider_event",
        "single_symbol_only": "provider_scope_single_symbol",
        "multi_symbol_only": "provider_scope_multi_symbol",
        "mixed_scope": "provider_scope_mixed",
    }[scope]
    if expected_scope_observation not in observations:
        raise ValueError("assessment omits the packet's provider-scope observation")

    if events:
        if not evidence_ids:
            raise ValueError("event interpretation requires cited headline evidence")
        if normalized["novelty"] != "unknown_missing_prior_event_corpus":
            raise ValueError("novelty must remain unknown without a prior-event corpus")
        if normalized["materiality"] != "unknown_title_only":
            raise ValueError("materiality must remain unknown from title-only evidence")
        if normalized["theme_fit"] != "unknown_no_causal_theme_state":
            raise ValueError("theme fit must remain unknown without a causal theme state")
        if not EVENT_REQUIRED_UNCERTAINTIES.issubset(uncertainty_set):
            raise ValueError("event interpretation omits required uncertainty reasons")
    else:
        if evidence_ids:
            raise ValueError("no-event assessment cannot cite headline evidence")
        for field in ("issuer_relevance", "headline_form", "event_type", "novelty", "materiality", "dilution_risk", "theme_fit"):
            if normalized[field] != NO_EVENT_VALUE:
                raise ValueError(f"{field} must be not-assessable without an event")
        if not NO_EVENT_REQUIRED_UNCERTAINTIES.issubset(uncertainty_set):
            raise ValueError("no-event interpretation omits required uncertainty reasons")

    record = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "runtime_strategy_effect": "none",
        "symbol": packet["symbol"],
        "activation_time": packet["activation_time"],
        "decision_time": packet["decision_time"],
        "source_packet_content_sha256": packet_hash,
        "provider_scope": scope,
        "available_headline_ids": sorted(available_ids),
        "evidence_sufficiency": {
            "title_semantics_available": bool(events),
            "article_body_available": False,
            "filing_corroboration_available": False,
            "prior_event_comparison_corpus_available": False,
            "causal_theme_state_available": False,
            "quality_judgment_eligible": False,
        },
        "assessment": normalized,
        "prohibited_outputs": {
            "quality_score": None,
            "trade_recommendation": None,
            "selection_action": None,
            "order_action": None,
            "risk_action": None,
        },
    }
    record["record_content_sha256"] = _fingerprint(record)
    return record
