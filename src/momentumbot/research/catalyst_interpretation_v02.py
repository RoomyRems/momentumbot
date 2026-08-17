from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from momentumbot.research.catalyst_interpretation import (
    SOURCE_PACKET_CONTRACT_ID,
    _fingerprint,
    _provider_scope,
    _validate_packet,
)


SCHEMA_VERSION = 2
CONTRACT_ID = "catalyst-interpretation-protocol-shadow-v0.2"
SUPERSEDES_CONTRACT_ID = "catalyst-interpretation-protocol-shadow-v0.1"

ASSESSMENT_FIELDS = (
    "assessment_origin",
    "issuer_relevance",
    "headline_form",
    "event_type",
    "event_commitment_state",
    "economic_quantification",
    "repetition_status",
    "offering_overhang_signal",
    "novelty",
    "materiality",
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
    "event_commitment_state": (
        "title_states_exploration_or_pursuit",
        "title_states_board_authorization_not_execution",
        "title_states_definitive_agreement_or_completed_action",
        "title_states_withdrawal_or_cancellation",
        "ambiguous_title_only",
        "not_assessable_no_provider_event",
    ),
    "economic_quantification": (
        "specific_economic_amount_in_title",
        "numeric_terms_without_verified_economic_amount",
        "no_specific_economic_amount_in_title",
        "ambiguous_title_only",
        "not_assessable_no_provider_event",
    ),
    "repetition_status": (
        "possible_repetition_within_available_packet",
        "unknown_incomplete_prior_event_corpus",
        "not_assessable_no_provider_event",
    ),
    "offering_overhang_signal": (
        "title_signals_offering_or_possible_dilution",
        "title_signals_withdrawal_or_reduced_offering_overhang",
        "no_explicit_offering_signal_in_title",
        "ambiguous_title_only",
        "not_assessable_no_provider_event",
    ),
    "novelty": (
        "unknown_incomplete_prior_event_corpus",
        "not_assessable_no_provider_event",
    ),
    "materiality": (
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
    "pursuit_or_intent_language",
    "board_authorization_language",
    "definitive_or_completed_action_language",
    "withdrawal_or_cancellation_language",
    "specific_economic_amount_language",
    "numeric_terms_present_without_verified_economic_amount",
    "no_specific_economic_amount_language",
    "similar_prior_title_within_packet",
    "offering_or_possible_dilution_language",
    "offering_withdrawal_or_cancellation_language",
    "no_explicit_offering_language",
)

UNCERTAINTY_REASONS = (
    "title_only_no_article_body",
    "incomplete_prior_event_corpus",
    "no_causal_theme_state",
    "no_filing_corroboration",
    "provider_symbol_tag_not_proof_of_relevance",
    "candidate_not_title_focus",
    "economic_terms_not_verified_beyond_title",
    "event_scope_mixed",
    "no_provider_event",
    "provider_relative_absence_only",
)

NO_EVENT_VALUE = "not_assessable_no_provider_event"
EVENT_REQUIRED_UNCERTAINTIES = {
    "title_only_no_article_body",
    "incomplete_prior_event_corpus",
    "no_causal_theme_state",
    "no_filing_corroboration",
}
NO_EVENT_REQUIRED_UNCERTAINTIES = {
    "no_provider_event",
    "provider_relative_absence_only",
    "no_causal_theme_state",
}

COMMITMENT_OBSERVATION = {
    "title_states_exploration_or_pursuit": "pursuit_or_intent_language",
    "title_states_board_authorization_not_execution": "board_authorization_language",
    "title_states_definitive_agreement_or_completed_action": (
        "definitive_or_completed_action_language"
    ),
    "title_states_withdrawal_or_cancellation": "withdrawal_or_cancellation_language",
}
QUANTIFICATION_OBSERVATION = {
    "specific_economic_amount_in_title": "specific_economic_amount_language",
    "numeric_terms_without_verified_economic_amount": (
        "numeric_terms_present_without_verified_economic_amount"
    ),
    "no_specific_economic_amount_in_title": "no_specific_economic_amount_language",
}
OFFERING_OBSERVATION = {
    "title_signals_offering_or_possible_dilution": (
        "offering_or_possible_dilution_language"
    ),
    "title_signals_withdrawal_or_reduced_offering_overhang": (
        "offering_withdrawal_or_cancellation_language"
    ),
    "no_explicit_offering_signal_in_title": "no_explicit_offering_language",
}

REQUIRED_UNKNOWN_GUARDS = {
    "novelty_without_complete_prior_event_corpus": (
        "unknown_incomplete_prior_event_corpus"
    ),
    "absence_of_repetition_without_complete_prior_event_corpus": (
        "unknown_incomplete_prior_event_corpus"
    ),
    "materiality_from_title_only": "unknown_title_only",
    "theme_fit_without_causal_theme_state": "unknown_no_causal_theme_state",
}


def validate_catalyst_interpretation_v02_contract(
    payload: Mapping[str, object],
) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported catalyst-interpretation v0.2 schema")
    if payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected catalyst-interpretation v0.2 contract ID")
    if payload.get("supersedes_contract_id") != SUPERSEDES_CONTRACT_ID:
        raise ValueError("v0.2 must explicitly supersede the frozen v0.1 protocol")
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
    if source.get("retrospective_trade_labels_allowed") is not False:
        raise ValueError("retrospective labels must remain outside the protocol")

    if payload.get("assessment_fields") != list(ASSESSMENT_FIELDS):
        raise ValueError("assessment_fields must match the ordered v0.2 contract")
    enums = payload.get("enums")
    if not isinstance(enums, Mapping) or set(enums) != set(ENUMS):
        raise ValueError("enum fields must match the v0.2 interpretation axes")
    for field, values in ENUMS.items():
        if enums.get(field) != list(values):
            raise ValueError(f"enum {field} differs from the v0.2 contract")
    if payload.get("observation_codes") != list(OBSERVATION_CODES):
        raise ValueError("observation_codes differ from the v0.2 contract")
    if payload.get("uncertainty_reasons") != list(UNCERTAINTY_REASONS):
        raise ValueError("uncertainty_reasons differ from the v0.2 contract")
    if payload.get("required_unknown_guards") != REQUIRED_UNKNOWN_GUARDS:
        raise ValueError("required_unknown_guards differ from the v0.2 contract")


def load_catalyst_interpretation_v02_contract(
    path: str | Path,
) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("catalyst-interpretation v0.2 contract root must be an object")
    validate_catalyst_interpretation_v02_contract(payload)
    return payload


def _normalize_string_list(
    value: object,
    *,
    field: str,
    allowed: tuple[str, ...] | None = None,
) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be a string list")
    if len(value) != len(set(value)):
        raise ValueError(f"{field} must be unique")
    if allowed is not None and any(item not in allowed for item in value):
        raise ValueError(f"unsupported {field} value")
    return sorted(value)


def build_catalyst_interpretation_v02_record(
    packet: Mapping[str, object],
    assessment: Mapping[str, object],
) -> dict[str, object]:
    """Bind evidence-scoped catalyst semantics without producing a quality decision."""

    events, packet_hash = _validate_packet(packet)
    if set(assessment) != set(ASSESSMENT_FIELDS):
        raise ValueError("assessment fields must match the v0.2 contract")

    normalized: dict[str, object] = {}
    for field in ASSESSMENT_FIELDS[:11]:
        value = assessment.get(field)
        if value not in ENUMS[field]:
            raise ValueError(f"unsupported {field} value")
        normalized[field] = value

    available_ids = {str(event["headline_id"]) for event in events}
    evidence_ids = _normalize_string_list(
        assessment.get("evidence_headline_ids"), field="evidence_headline_ids"
    )
    if not set(evidence_ids).issubset(available_ids):
        raise ValueError("assessment references unavailable headline evidence")
    normalized["evidence_headline_ids"] = evidence_ids

    observations = _normalize_string_list(
        assessment.get("observation_codes"),
        field="observation_codes",
        allowed=OBSERVATION_CODES,
    )
    normalized["observation_codes"] = observations
    observation_set = set(observations)

    uncertainties = _normalize_string_list(
        assessment.get("uncertainty_reasons"),
        field="uncertainty_reasons",
        allowed=UNCERTAINTY_REASONS,
    )
    normalized["uncertainty_reasons"] = uncertainties
    uncertainty_set = set(uncertainties)

    scope = _provider_scope(events)
    expected_scope_observation = {
        "no_provider_event": "no_provider_event",
        "single_symbol_only": "provider_scope_single_symbol",
        "multi_symbol_only": "provider_scope_multi_symbol",
        "mixed_scope": "provider_scope_mixed",
    }[scope]
    if expected_scope_observation not in observation_set:
        raise ValueError("assessment omits the packet's provider-scope observation")

    semantic_fields = ASSESSMENT_FIELDS[1:11]
    if not events:
        if evidence_ids:
            raise ValueError("no-event assessment cannot cite headline evidence")
        for field in semantic_fields:
            if normalized[field] != NO_EVENT_VALUE:
                raise ValueError(f"{field} must be not-assessable without an event")
        if not NO_EVENT_REQUIRED_UNCERTAINTIES.issubset(uncertainty_set):
            raise ValueError("no-event interpretation omits required uncertainty reasons")
    else:
        if not evidence_ids:
            raise ValueError("event interpretation requires cited headline evidence")
        if normalized["novelty"] != "unknown_incomplete_prior_event_corpus":
            raise ValueError("novelty must remain unknown without a complete corpus")
        if normalized["materiality"] != "unknown_title_only":
            raise ValueError("materiality must remain unknown from title-only evidence")
        if normalized["theme_fit"] != "unknown_no_causal_theme_state":
            raise ValueError("theme fit must remain unknown without a causal theme state")
        if not EVENT_REQUIRED_UNCERTAINTIES.issubset(uncertainty_set):
            raise ValueError("event interpretation omits required uncertainty reasons")

        commitment = str(normalized["event_commitment_state"])
        required_commitment = COMMITMENT_OBSERVATION.get(commitment)
        if required_commitment and required_commitment not in observation_set:
            raise ValueError("commitment state lacks its required title observation")

        quantification = str(normalized["economic_quantification"])
        required_quantification = QUANTIFICATION_OBSERVATION.get(quantification)
        if required_quantification and required_quantification not in observation_set:
            raise ValueError("economic quantification lacks its required title observation")

        offering_signal = str(normalized["offering_overhang_signal"])
        required_offering = OFFERING_OBSERVATION.get(offering_signal)
        if required_offering and required_offering not in observation_set:
            raise ValueError("offering signal lacks its required title observation")
        if offering_signal.startswith("title_signals_") and normalized["event_type"] not in {
            "financing_or_capital_structure",
            "filing_or_compliance",
        }:
            raise ValueError("offering signal requires a financing or filing event type")

        repetition = normalized["repetition_status"]
        if repetition == "possible_repetition_within_available_packet":
            if len(evidence_ids) < 2:
                raise ValueError("possible repetition requires at least two cited headlines")
            if "similar_prior_title_within_packet" not in observation_set:
                raise ValueError("possible repetition lacks a comparison observation")
        elif repetition != "unknown_incomplete_prior_event_corpus":
            raise ValueError("unsupported event repetition status")

    record = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "supersedes_contract_id": SUPERSEDES_CONTRACT_ID,
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
            "complete_prior_event_corpus_available": False,
            "causal_theme_state_available": False,
            "quality_judgment_eligible": False,
        },
        "assessment": normalized,
        "prohibited_outputs": {
            "quality_score": None,
            "candidate_priority": None,
            "trade_recommendation": None,
            "selection_action": None,
            "order_action": None,
            "risk_action": None,
        },
    }
    record["record_content_sha256"] = _fingerprint(record)
    return record
