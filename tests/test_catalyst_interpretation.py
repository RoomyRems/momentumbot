import copy
import json
import unittest
from pathlib import Path

from momentumbot.research.catalyst_interpretation import (
    CONTRACT_ID,
    build_catalyst_interpretation_record,
    load_catalyst_interpretation_contract,
    validate_catalyst_interpretation_contract,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research" / "strategy" / "catalyst-interpretation-protocol-shadow-v0.1.json"
AUDIT = ROOT / "research" / "data-audits" / "catalyst-interpretation-protocol-shadow-v0.1.json"


def _fingerprint(payload):
    import hashlib

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _packet(*, events):
    packet = {
        "symbol": "AAA",
        "activation_time": "2026-01-02T12:00:00+00:00",
        "decision_time": "2026-01-02T12:01:00+00:00",
        "packet_reason": "candidate_activation",
        "news_provider_status": "success",
        "provider_relative_no_news_as_of": not events,
        "provider_news_event_count_as_of": len(events),
        "new_headline_ids": [event["headline_id"] for event in events],
        "events": events,
    }
    packet["packet_content_sha256"] = _fingerprint(packet)
    return packet


def _event(*, headline_id="provider:1", symbols=None, title="AAA signs supply agreement"):
    symbols = symbols or ["AAA"]
    return {
        "headline_id": headline_id,
        "published_at": "2026-01-02T12:00:30+00:00",
        "seconds_old_at_decision": 30.0,
        "availability_basis": "provider_updated_at",
        "provider": "alpaca-benzinga",
        "provider_story_id": headline_id.split(":")[-1],
        "source": "benzinga",
        "title": title,
        "provider_symbols": symbols,
        "provider_symbol_count": len(symbols),
        "single_symbol_story": len(symbols) == 1,
    }


def _event_assessment():
    return {
        "assessment_origin": "manual_research_example",
        "issuer_relevance": "direct_candidate",
        "headline_form": "issuer_specific_event",
        "event_type": "commercial_agreement",
        "novelty": "unknown_missing_prior_event_corpus",
        "materiality": "unknown_title_only",
        "dilution_risk": "unknown_title_only",
        "theme_fit": "unknown_no_causal_theme_state",
        "evidence_headline_ids": ["provider:1"],
        "observation_codes": [
            "provider_scope_single_symbol",
            "title_foregrounds_candidate",
            "commercial_agreement_language",
        ],
        "uncertainty_reasons": [
            "title_only_no_article_body",
            "no_prior_event_corpus",
            "no_causal_theme_state",
            "no_filing_corroboration",
            "terms_not_quantified",
        ],
    }


class CatalystInterpretationTests(unittest.TestCase):
    def test_contract_freezes_protocol_without_score_or_authority(self):
        payload = load_catalyst_interpretation_contract(CONTRACT)
        self.assertEqual(payload["contract_id"], CONTRACT_ID)
        self.assertFalse(payload["quality_score_frozen"])
        self.assertFalse(payload["ai_order_authority"])
        self.assertFalse(payload["policy_promotion_eligible"])

    def test_contract_rejects_strategy_effect(self):
        payload = load_catalyst_interpretation_contract(CONTRACT)
        changed = copy.deepcopy(payload)
        changed["runtime_strategy_effect"] = "selection_gate"
        with self.assertRaisesRegex(ValueError, "shadow-only"):
            validate_catalyst_interpretation_contract(changed)

    def test_binds_structured_assessment_to_causal_packet(self):
        record = build_catalyst_interpretation_record(
            _packet(events=[_event()]),
            _event_assessment(),
        )
        self.assertEqual(record["provider_scope"], "single_symbol_only")
        self.assertEqual(record["assessment"]["materiality"], "unknown_title_only")
        self.assertFalse(record["evidence_sufficiency"]["quality_judgment_eligible"])
        self.assertIsNone(record["prohibited_outputs"]["trade_recommendation"])
        self.assertEqual(len(record["record_content_sha256"]), 64)

    def test_no_event_forces_not_assessable_axes(self):
        assessment = {
            "assessment_origin": "manual_research_example",
            "issuer_relevance": "not_assessable_no_provider_event",
            "headline_form": "not_assessable_no_provider_event",
            "event_type": "not_assessable_no_provider_event",
            "novelty": "not_assessable_no_provider_event",
            "materiality": "not_assessable_no_provider_event",
            "dilution_risk": "not_assessable_no_provider_event",
            "theme_fit": "not_assessable_no_provider_event",
            "evidence_headline_ids": [],
            "observation_codes": ["no_provider_event"],
            "uncertainty_reasons": [
                "no_provider_event",
                "provider_relative_absence_only",
                "no_causal_theme_state",
            ],
        }
        record = build_catalyst_interpretation_record(_packet(events=[]), assessment)
        self.assertEqual(record["provider_scope"], "no_provider_event")
        self.assertFalse(record["evidence_sufficiency"]["title_semantics_available"])

    def test_rejects_unavailable_headline_reference(self):
        assessment = _event_assessment()
        assessment["evidence_headline_ids"] = ["provider:future"]
        with self.assertRaisesRegex(ValueError, "unavailable headline"):
            build_catalyst_interpretation_record(_packet(events=[_event()]), assessment)

    def test_title_only_evidence_cannot_claim_materiality(self):
        assessment = _event_assessment()
        assessment["materiality"] = "likely_material"
        with self.assertRaisesRegex(ValueError, "unsupported materiality"):
            build_catalyst_interpretation_record(_packet(events=[_event()]), assessment)

    def test_packet_hash_tamper_fails_closed(self):
        packet = _packet(events=[_event()])
        packet["decision_time"] = "2026-01-02T12:02:00+00:00"
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            build_catalyst_interpretation_record(packet, _event_assessment())

    def test_record_is_independent_of_set_like_input_order(self):
        packet = _packet(events=[_event()])
        assessment = _event_assessment()
        forward = build_catalyst_interpretation_record(packet, assessment)
        changed = copy.deepcopy(assessment)
        changed["observation_codes"].reverse()
        changed["uncertainty_reasons"].reverse()
        reverse = build_catalyst_interpretation_record(packet, changed)
        self.assertEqual(forward, reverse)

    def test_frozen_audit_records_examples_without_promotion(self):
        payload = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(payload["contract_id"], CONTRACT_ID)
        self.assertEqual(payload["validation_scope"]["packet_count"], 35)
        self.assertFalse(payload["decision"]["promote_catalyst_rule"])
        self.assertFalse(payload["decision"]["quality_score_frozen"])


if __name__ == "__main__":
    unittest.main()
