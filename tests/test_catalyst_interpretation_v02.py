import copy
import hashlib
import json
import unittest
from pathlib import Path

from momentumbot.research.catalyst_interpretation import (
    CONTRACT_ID as V01_CONTRACT_ID,
    load_catalyst_interpretation_contract,
)
from momentumbot.research.catalyst_interpretation_v02 import (
    CONTRACT_ID,
    build_catalyst_interpretation_v02_record,
    load_catalyst_interpretation_v02_contract,
    validate_catalyst_interpretation_v02_contract,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "catalyst-interpretation-protocol-shadow-v0.2.json"
)
V01_CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "catalyst-interpretation-protocol-shadow-v0.1.json"
)
AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "catalyst-interpretation-protocol-shadow-v0.2.json"
)


def _fingerprint(payload):
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _event(*, headline_id="provider:1", title="AAA enters supply agreement"):
    return {
        "headline_id": headline_id,
        "published_at": "2026-01-02T12:00:30+00:00",
        "seconds_old_at_decision": 30.0,
        "availability_basis": "provider_updated_at",
        "provider": "alpaca-benzinga",
        "provider_story_id": headline_id.split(":")[-1],
        "source": "benzinga",
        "title": title,
        "provider_symbols": ["AAA"],
        "provider_symbol_count": 1,
        "single_symbol_story": True,
    }


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


def _assessment():
    return {
        "assessment_origin": "manual_research_example",
        "issuer_relevance": "direct_candidate",
        "headline_form": "issuer_specific_event",
        "event_type": "commercial_agreement",
        "event_commitment_state": (
            "title_states_definitive_agreement_or_completed_action"
        ),
        "economic_quantification": "no_specific_economic_amount_in_title",
        "repetition_status": "unknown_incomplete_prior_event_corpus",
        "offering_overhang_signal": "no_explicit_offering_signal_in_title",
        "novelty": "unknown_incomplete_prior_event_corpus",
        "materiality": "unknown_title_only",
        "theme_fit": "unknown_no_causal_theme_state",
        "evidence_headline_ids": ["provider:1"],
        "observation_codes": [
            "provider_scope_single_symbol",
            "title_foregrounds_candidate",
            "definitive_or_completed_action_language",
            "no_specific_economic_amount_language",
            "no_explicit_offering_language",
        ],
        "uncertainty_reasons": [
            "title_only_no_article_body",
            "incomplete_prior_event_corpus",
            "no_causal_theme_state",
            "no_filing_corroboration",
            "economic_terms_not_verified_beyond_title",
        ],
    }


class CatalystInterpretationV02Tests(unittest.TestCase):
    def test_contract_adds_evidenced_axes_without_strategy_authority(self):
        payload = load_catalyst_interpretation_v02_contract(CONTRACT)
        self.assertEqual(payload["contract_id"], CONTRACT_ID)
        self.assertEqual(payload["supersedes_contract_id"], V01_CONTRACT_ID)
        self.assertIn("event_commitment_state", payload["assessment_fields"])
        self.assertIn("economic_quantification", payload["assessment_fields"])
        self.assertIn("repetition_status", payload["assessment_fields"])
        self.assertFalse(payload["quality_score_frozen"])
        self.assertFalse(payload["policy_promotion_eligible"])

    def test_v01_contract_remains_readable_and_unchanged(self):
        payload = load_catalyst_interpretation_contract(V01_CONTRACT)
        self.assertEqual(payload["contract_id"], V01_CONTRACT_ID)

    def test_definitive_unquantified_title_is_structured_but_not_scored(self):
        record = build_catalyst_interpretation_v02_record(
            _packet(events=[_event()]), _assessment()
        )
        self.assertEqual(
            record["assessment"]["event_commitment_state"],
            "title_states_definitive_agreement_or_completed_action",
        )
        self.assertEqual(record["assessment"]["materiality"], "unknown_title_only")
        self.assertFalse(record["evidence_sufficiency"]["quality_judgment_eligible"])
        self.assertIsNone(record["prohibited_outputs"]["candidate_priority"])

    def test_proposal_and_board_authorization_are_distinct_from_execution(self):
        assessment = _assessment()
        assessment["event_commitment_state"] = (
            "title_states_board_authorization_not_execution"
        )
        assessment["observation_codes"].remove(
            "definitive_or_completed_action_language"
        )
        assessment["observation_codes"].append("board_authorization_language")
        record = build_catalyst_interpretation_v02_record(
            _packet(events=[_event(title="AAA board approves pursuit of investment")]),
            assessment,
        )
        self.assertEqual(
            record["assessment"]["event_commitment_state"],
            "title_states_board_authorization_not_execution",
        )

    def test_specific_amount_does_not_claim_materiality(self):
        assessment = _assessment()
        assessment["economic_quantification"] = "specific_economic_amount_in_title"
        assessment["observation_codes"].remove(
            "no_specific_economic_amount_language"
        )
        assessment["observation_codes"].append(
            "specific_economic_amount_language"
        )
        record = build_catalyst_interpretation_v02_record(
            _packet(events=[_event(title="AAA announces $400M investment")]),
            assessment,
        )
        self.assertEqual(
            record["assessment"]["economic_quantification"],
            "specific_economic_amount_in_title",
        )
        self.assertEqual(record["assessment"]["materiality"], "unknown_title_only")

    def test_offering_withdrawal_is_signal_not_dilution_safety_claim(self):
        assessment = _assessment()
        assessment["event_type"] = "filing_or_compliance"
        assessment["event_commitment_state"] = "title_states_withdrawal_or_cancellation"
        assessment["offering_overhang_signal"] = (
            "title_signals_withdrawal_or_reduced_offering_overhang"
        )
        assessment["observation_codes"].remove(
            "definitive_or_completed_action_language"
        )
        assessment["observation_codes"].remove("no_explicit_offering_language")
        assessment["observation_codes"].extend(
            [
                "withdrawal_or_cancellation_language",
                "offering_withdrawal_or_cancellation_language",
            ]
        )
        record = build_catalyst_interpretation_v02_record(
            _packet(events=[_event(title="AAA withdraws shelf registration")]),
            assessment,
        )
        self.assertEqual(
            record["assessment"]["offering_overhang_signal"],
            "title_signals_withdrawal_or_reduced_offering_overhang",
        )
        self.assertFalse(record["evidence_sufficiency"]["filing_corroboration_available"])

    def test_possible_repetition_requires_two_available_headlines(self):
        assessment = _assessment()
        assessment["repetition_status"] = "possible_repetition_within_available_packet"
        assessment["observation_codes"].append("similar_prior_title_within_packet")
        with self.assertRaisesRegex(ValueError, "at least two cited"):
            build_catalyst_interpretation_v02_record(
                _packet(events=[_event()]), assessment
            )

        assessment["evidence_headline_ids"] = ["provider:1", "provider:2"]
        record = build_catalyst_interpretation_v02_record(
            _packet(
                events=[
                    _event(),
                    _event(headline_id="provider:2", title="AAA expands supply agreement"),
                ]
            ),
            assessment,
        )
        self.assertEqual(
            record["assessment"]["repetition_status"],
            "possible_repetition_within_available_packet",
        )
        self.assertEqual(record["assessment"]["novelty"], "unknown_incomplete_prior_event_corpus")

    def test_semantic_claim_without_required_title_observation_fails_closed(self):
        assessment = _assessment()
        assessment["observation_codes"].remove(
            "definitive_or_completed_action_language"
        )
        with self.assertRaisesRegex(ValueError, "commitment state"):
            build_catalyst_interpretation_v02_record(
                _packet(events=[_event()]), assessment
            )

    def test_no_event_forces_every_semantic_axis_not_assessable(self):
        assessment = {
            "assessment_origin": "manual_research_example",
            "issuer_relevance": "not_assessable_no_provider_event",
            "headline_form": "not_assessable_no_provider_event",
            "event_type": "not_assessable_no_provider_event",
            "event_commitment_state": "not_assessable_no_provider_event",
            "economic_quantification": "not_assessable_no_provider_event",
            "repetition_status": "not_assessable_no_provider_event",
            "offering_overhang_signal": "not_assessable_no_provider_event",
            "novelty": "not_assessable_no_provider_event",
            "materiality": "not_assessable_no_provider_event",
            "theme_fit": "not_assessable_no_provider_event",
            "evidence_headline_ids": [],
            "observation_codes": ["no_provider_event"],
            "uncertainty_reasons": [
                "no_provider_event",
                "provider_relative_absence_only",
                "no_causal_theme_state",
            ],
        }
        record = build_catalyst_interpretation_v02_record(
            _packet(events=[]), assessment
        )
        self.assertEqual(record["provider_scope"], "no_provider_event")

    def test_contract_and_record_tampering_fail_closed(self):
        contract = load_catalyst_interpretation_v02_contract(CONTRACT)
        changed = copy.deepcopy(contract)
        changed["runtime_strategy_effect"] = "selection_gate"
        with self.assertRaisesRegex(ValueError, "shadow-only"):
            validate_catalyst_interpretation_v02_contract(changed)

        assessment = _assessment()
        assessment["evidence_headline_ids"] = ["provider:future"]
        with self.assertRaisesRegex(ValueError, "unavailable headline"):
            build_catalyst_interpretation_v02_record(
                _packet(events=[_event()]), assessment
            )

    def test_audit_freezes_protocol_not_semantic_model(self):
        payload = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(payload["contract_id"], CONTRACT_ID)
        self.assertTrue(payload["decision"]["freeze_protocol_v02"])
        self.assertFalse(payload["decision"]["freeze_semantic_model"])
        self.assertFalse(payload["decision"]["promote_catalyst_rule"])


if __name__ == "__main__":
    unittest.main()
