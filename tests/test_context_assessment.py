import copy
import json
import unittest
from pathlib import Path

import pandas as pd

from momentumbot.research.attention_leadership import derive_attention_leadership_rows
from momentumbot.research.context_assessment import (
    CONTRACT_ID,
    EXCLUDED_PILOT_COMPARISON_SHA256,
    MAX_ASSESSMENT_TTL_SECONDS,
    SEMANTIC_AXES,
    build_context_decision_snapshot,
    build_shadow_context_assessment,
    canonical_fingerprint,
    load_context_assessment_contract,
    validate_context_assessment_contract,
    validate_context_decision_snapshot,
    validate_shadow_context_assessment,
)
from momentumbot.research.daily_chart_context import (
    build_daily_chart_evidence,
    daily_chart_supplemental_evidence,
)
from momentumbot.research.theme_regime_context import (
    build_theme_regime_evidence,
    theme_regime_supplemental_evidence,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "discretion-context-assessment-shadow-v0.1.json"
)
AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "discretion-context-assessment-shadow-v0.1.json"
)


def _scanner_row():
    return {
        "symbol": "AAA",
        "activation_time": "2026-08-03T13:31:00+00:00",
        "decision_time": "2026-08-03T13:31:00+00:00",
        "required_source_bar_started_at": "2026-08-03T13:30:00+00:00",
        "candidate_completed_bar_present": True,
        "candidate_bar_available_at": "2026-08-03T13:31:00+00:00",
        "price": 5.0,
        "previous_close": 2.5,
        "percent_gain": 100.0,
        "cumulative_volume": 2_000_000,
        "exact_same_time_rvol": 10.0,
        "price_pillar_pass": True,
        "gain_pillar_pass": True,
        "rvol_pillar_pass": True,
        "float_classification": "known_at_or_below_limit",
        "float_pillar_pass": True,
        "estimated_float_shares": 5_000_000,
        "float_asof": "2026-08-01",
        "float_method": "sec_companyfacts",
        "float_provider_status": "success",
        "news_provider_status": "success",
        "provider_news_event_count_as_of": 1,
        "has_provider_news_as_of": True,
        "provider_relative_no_news_as_of": False,
        "first_provider_news_published_at_as_of": "2026-08-03T13:30:30+00:00",
        "latest_provider_news_published_at_as_of": "2026-08-03T13:30:30+00:00",
        "identity_resolved_member_count": 100,
        "rank_members_with_completed_bar_count": 90,
        "rank_members_with_completed_close_count": 90,
        "rank_members_missing_completed_close_count": 0,
        "rank_members_missing_previous_close_count": 0,
        "rank_members_with_computable_gain_count": 90,
        "rank_members_without_completed_bar_count": 10,
        "rank_input_complete_for_members_with_completed_bars": True,
        "rank_input_ordered_sha256": "1" * 64,
        "top_gainer_rank": 1,
        "rank_leader_symbol": "AAA",
        "rank_leader_percent_gain": 100.0,
        "disposition": "qualified_provider_news_presence_unclassified",
    }


def _attention_row(scanner=None):
    return derive_attention_leadership_rows([scanner or _scanner_row()])[0]


def _event():
    return {
        "headline_id": "alpaca:story-1",
        "published_at": "2026-08-03T13:30:30+00:00",
        "seconds_old_at_decision": 30.0,
        "availability_basis": "provider_updated_at",
        "provider": "alpaca-benzinga",
        "provider_story_id": "story-1",
        "source": "benzinga",
        "title": "AAA signs definitive supply agreement",
        "provider_symbols": ["AAA"],
        "provider_symbol_count": 1,
        "single_symbol_story": True,
    }


def _packet(events=None):
    rows = [_event()] if events is None else events
    packet = {
        "symbol": "AAA",
        "activation_time": "2026-08-03T13:31:00+00:00",
        "decision_time": "2026-08-03T13:31:00+00:00",
        "packet_reason": "candidate_activation",
        "news_provider_status": "success",
        "provider_relative_no_news_as_of": not rows,
        "provider_news_event_count_as_of": len(rows),
        "new_headline_ids": [row["headline_id"] for row in rows],
        "events": rows,
    }
    packet["packet_content_sha256"] = canonical_fingerprint(packet)
    return packet


def _source_hashes():
    return {
        "scanner_runtime": "a" * 64,
        "attention_runtime": "b" * 64,
        "catalyst_evidence_runtime": "c" * 64,
    }


def _supplemental(evidence_id, domain, payload):
    return {
        "evidence_id": evidence_id,
        "domain": domain,
        "available_at": "2026-08-03T13:31:00+00:00",
        "source_contract_id": f"{domain}-shadow-v0.1",
        "source_artifact_content_sha256": "d" * 64,
        "payload": payload,
    }


def _snapshot(*, supplemental=(), packet=None):
    scanner = _scanner_row()
    return build_context_decision_snapshot(
        scanner,
        _attention_row(scanner),
        catalyst_packet=_packet() if packet is None else packet,
        source_artifact_content_sha256s=_source_hashes(),
        snapshot_reason="candidate_activation",
        supplemental_evidence=supplemental,
    )


def _assessed(value, evidence_id, prefix):
    return {
        "state": "assessed",
        "value": value,
        "confidence": "medium",
        "evidence_ids": [evidence_id],
        "observed_facts": [
            {
                "claim_id": f"{prefix}.fact",
                "statement": "The cited decision-time evidence contains the stated observation.",
                "evidence_ids": [evidence_id],
            }
        ],
        "inferences": [
            {
                "claim_id": f"{prefix}.inference",
                "statement": "The observation supports this bounded semantic classification.",
                "evidence_ids": [evidence_id],
            }
        ],
        "abstain_reason": None,
    }


def _abstained(reason="required_evidence_domain_unavailable"):
    return {
        "state": "abstained",
        "value": None,
        "confidence": None,
        "evidence_ids": [],
        "observed_facts": [],
        "inferences": [],
        "abstain_reason": reason,
    }


def _model_provenance():
    return {
        "provider": "test-provider",
        "model_id": "shadow-model-test",
        "prompt_id": "context-shadow-v0.1",
        "prompt_content_sha256": "e" * 64,
        "generated_at": "2026-08-18T20:00:00+00:00",
        "label_blind_run_id": "unit-test-label-blind-run",
    }


class ContextAssessmentTests(unittest.TestCase):
    def test_protocol_is_preregistered_shadow_only_and_excludes_pilot_fit(self):
        payload = load_context_assessment_contract(CONTRACT)
        self.assertEqual(payload["contract_id"], CONTRACT_ID)
        self.assertEqual(
            payload["frozen_parents"]["micro_policy_fingerprint"],
            "49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa",
        )
        self.assertFalse(payload["aggregate_score_frozen"])
        self.assertFalse(payload["selection_threshold_frozen"])
        self.assertFalse(payload["ai_order_authority"])
        self.assertFalse(payload["ai_risk_authority"])
        self.assertEqual(
            payload["evaluation_boundary"][
                "excluded_fit_comparison_content_sha256"
            ],
            EXCLUDED_PILOT_COMPARISON_SHA256,
        )
        self.assertFalse(
            payload["evaluation_boundary"]["threshold_fit_on_excluded_panel_allowed"]
        )

    def test_contract_tamper_cannot_enable_strategy_authority(self):
        payload = load_context_assessment_contract(CONTRACT)
        changed = copy.deepcopy(payload)
        changed["ai_order_authority"] = True
        with self.assertRaisesRegex(ValueError, "must be false"):
            validate_context_assessment_contract(changed)

    def test_protocol_audit_binds_contract_and_freezes_no_model_or_rule(self):
        contract = load_context_assessment_contract(CONTRACT)
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(audit["contract_id"], CONTRACT_ID)
        self.assertEqual(
            audit["contract_content_sha256"], canonical_fingerprint(contract)
        )
        self.assertTrue(audit["decision"]["freeze_protocol_v01"])
        self.assertFalse(audit["decision"]["freeze_semantic_model"])
        self.assertFalse(audit["decision"]["fit_threshold_on_old_pilot"])
        self.assertFalse(audit["decision"]["promote_context_rule"])

    def test_snapshot_binds_exact_causal_sources_and_explicit_missing_domains(self):
        snapshot = _snapshot()
        self.assertEqual(snapshot["symbol"], "AAA")
        self.assertEqual(snapshot["snapshot_reason"], "candidate_activation")
        self.assertTrue(
            snapshot["evidence_coverage"]["scanner_market"]["evidence_present"]
        )
        self.assertTrue(
            snapshot["evidence_coverage"]["attention_leadership"][
                "evidence_present"
            ]
        )
        self.assertTrue(
            snapshot["evidence_coverage"]["catalyst_headline"]["evidence_present"]
        )
        self.assertFalse(
            snapshot["evidence_coverage"]["daily_chart"]["evidence_present"]
        )
        self.assertFalse(
            snapshot["evidence_coverage"]["theme_regime"]["evidence_present"]
        )
        self.assertTrue(snapshot["knowledge_policy"]["uses_only_evidence_available_by_decision_time"])
        self.assertFalse(snapshot["knowledge_policy"]["uses_ross_actions"])
        self.assertIsNone(snapshot["prohibited_outputs"]["candidate_priority"])
        self.assertEqual(len(snapshot["snapshot_content_sha256"]), 64)

    def test_snapshot_rejects_future_or_retrospective_evidence(self):
        future = _supplemental("daily:future", "daily_chart", {"prior_high": 8.0})
        future["available_at"] = "2026-08-03T13:32:00+00:00"
        with self.assertRaisesRegex(ValueError, "future evidence"):
            _snapshot(supplemental=[future])

        retrospective = _supplemental(
            "daily:bad",
            "daily_chart",
            {"prior_high": 8.0, "ross_fill": 5.25},
        )
        with self.assertRaisesRegex(ValueError, "prohibited key"):
            _snapshot(supplemental=[retrospective])

    def test_frozen_daily_chart_record_binds_as_supplemental_evidence(self):
        index = pd.bdate_range(end="2026-07-31", periods=60, tz="UTC")
        index = index + pd.Timedelta(hours=20)
        bars = pd.DataFrame(
            [
                (
                    3.0 + offset * 0.05,
                    3.4 + offset * 0.05,
                    2.8 + offset * 0.05,
                    3.2 + offset * 0.05,
                    100_000 + offset * 1_000,
                )
                for offset in range(60)
            ],
            columns=["open", "high", "low", "close", "volume"],
            index=index,
        )
        record = build_daily_chart_evidence(
            bars,
            symbol="AAA",
            decision_time="2026-08-03T13:31:00+00:00",
            decision_price=5.0,
            identity_identifier_kind="composite_figi",
            identity_identifier="BBG000TEST01",
            identity_verified_start_date="2026-04-01",
            identity_verified_through_date="2026-08-03",
        )
        supplemental = daily_chart_supplemental_evidence(
            record,
            source_artifact_content_sha256="f" * 64,
        )
        snapshot = _snapshot(supplemental=[supplemental])
        coverage = snapshot["evidence_coverage"]["daily_chart"]
        self.assertTrue(coverage["evidence_present"])
        self.assertEqual(coverage["evidence_ids"], [supplemental["evidence_id"]])
        daily_item = next(
            item
            for item in snapshot["evidence_items"]
            if item["domain"] == "daily_chart"
        )
        self.assertEqual(
            daily_item["payload"]["record_content_sha256"],
            record["record_content_sha256"],
        )
        self.assertIsNone(
            daily_item["payload"]["prohibited_outputs"]["selection_action"]
        )

    def test_frozen_theme_regime_record_binds_as_supplemental_evidence(self):
        scanner = _scanner_row()
        event = {**_event(), "symbol": "AAA"}
        record = build_theme_regime_evidence(
            [scanner],
            [event],
            [],
            symbol="AAA",
            decision_time="2026-08-03T13:31:00+00:00",
            source_artifact_content_sha256s={
                "scanner_records": "1" * 64,
                "publication_timed_news_events": "2" * 64,
                "prior_session_summaries": "3" * 64,
            },
        )
        supplemental = theme_regime_supplemental_evidence(
            record,
            source_artifact_content_sha256="4" * 64,
        )
        snapshot = _snapshot(supplemental=[supplemental])
        coverage = snapshot["evidence_coverage"]["theme_regime"]
        self.assertTrue(coverage["evidence_present"])
        self.assertEqual(coverage["evidence_ids"], [supplemental["evidence_id"]])
        item = next(
            item
            for item in snapshot["evidence_items"]
            if item["domain"] == "theme_regime"
        )
        self.assertEqual(
            item["payload"]["record_content_sha256"],
            record["record_content_sha256"],
        )
        self.assertIsNone(
            item["payload"]["prohibited_outputs"]["selection_action"]
        )

    def test_snapshot_rejects_future_headline_even_after_self_rehash(self):
        event = _event()
        event["published_at"] = "2026-08-03T13:32:00+00:00"
        event["seconds_old_at_decision"] = -60.0
        packet = _packet([event])
        with self.assertRaisesRegex(ValueError, "future headline"):
            _snapshot(packet=packet)

    def test_snapshot_rejects_attention_scanner_lineage_mismatch(self):
        scanner = _scanner_row()
        attention = _attention_row(scanner)
        attention["source_rank_input_ordered_sha256"] = "9" * 64
        with self.assertRaisesRegex(ValueError, "rank lineage mismatch"):
            build_context_decision_snapshot(
                scanner,
                attention,
                catalyst_packet=_packet(),
                source_artifact_content_sha256s=_source_hashes(),
                snapshot_reason="candidate_activation",
            )

    def test_snapshot_tamper_fails_content_hash_validation(self):
        snapshot = _snapshot()
        snapshot["evidence_items"][0]["payload"]["percent_gain"] = 999.0
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            validate_context_decision_snapshot(snapshot)

    def test_shadow_assessment_cites_facts_and_inferences_and_abstains(self):
        supplemental = [
            _supplemental(
                "theme:state-1",
                "theme_regime",
                {"state": "hot", "no_news_follow_through_observed": True},
            ),
            _supplemental(
                "daily:levels-1",
                "daily_chart",
                {"nearest_resistance": 8.0, "failed_pop_count": 0},
            ),
        ]
        snapshot = _snapshot(supplemental=supplemental)
        headline_id = snapshot["evidence_coverage"]["catalyst_headline"][
            "evidence_ids"
        ][0]
        attention_id = snapshot["evidence_coverage"]["attention_leadership"][
            "evidence_ids"
        ][0]
        axes = {
            "catalyst_substance_specificity": _assessed(
                "specific_event_terms_incomplete", headline_id, "substance"
            ),
            "catalyst_commitment_stage": _assessed(
                "definitive_agreement_or_completed_action",
                headline_id,
                "commitment",
            ),
            "catalyst_credibility_repetition": _abstained(
                "insufficient_evidence"
            ),
            "theme_fit_no_news_acceptance": _assessed(
                "causal_no_news_momentum_acceptance_present",
                "theme:state-1",
                "theme",
            ),
            "opportunity_obviousness_leadership_quality": _assessed(
                "dominant_persistent_leader", attention_id, "leadership"
            ),
            "chart_context_cleanliness": _assessed(
                "clear_room_and_clean_history", "daily:levels-1", "chart"
            ),
        }
        assessment = build_shadow_context_assessment(
            snapshot,
            axis_assessments=axes,
            model_provenance=_model_provenance(),
            expires_at="2026-08-03T13:36:00+00:00",
        )
        self.assertEqual(set(assessment["axes"]), set(SEMANTIC_AXES))
        self.assertEqual(
            assessment["axes"]["catalyst_credibility_repetition"]["state"],
            "abstained",
        )
        self.assertEqual(
            assessment["axes"]["chart_context_cleanliness"]["confidence"],
            "medium",
        )
        self.assertIsNone(assessment["prohibited_outputs"]["selection_action"])
        self.assertEqual(len(assessment["assessment_content_sha256"]), 64)

    def test_missing_domain_forces_abstention(self):
        snapshot = _snapshot()
        axes = {axis: _abstained() for axis in SEMANTIC_AXES}
        headline_id = snapshot["evidence_coverage"]["catalyst_headline"][
            "evidence_ids"
        ][0]
        axes["catalyst_substance_specificity"] = _assessed(
            "specific_event_terms_incomplete", headline_id, "substance"
        )
        axes["catalyst_commitment_stage"] = _assessed(
            "definitive_agreement_or_completed_action", headline_id, "commitment"
        )
        attention_id = snapshot["evidence_coverage"]["attention_leadership"][
            "evidence_ids"
        ][0]
        axes["opportunity_obviousness_leadership_quality"] = _assessed(
            "dominant_persistent_leader", attention_id, "leadership"
        )
        attempted_chart = _assessed(
            "clear_room_and_clean_history", attention_id, "chart"
        )
        axes["chart_context_cleanliness"] = attempted_chart
        with self.assertRaisesRegex(ValueError, "outside its allowed domains"):
            build_shadow_context_assessment(
                snapshot,
                axis_assessments=axes,
                model_provenance=_model_provenance(),
                expires_at="2026-08-03T13:32:00+00:00",
            )

    def test_value_specific_claim_requires_issuer_history(self):
        snapshot = _snapshot()
        headline_id = snapshot["evidence_coverage"]["catalyst_headline"][
            "evidence_ids"
        ][0]
        axes = {axis: _abstained() for axis in SEMANTIC_AXES}
        axes["catalyst_substance_specificity"] = _assessed(
            "specific_event_terms_incomplete", headline_id, "substance"
        )
        axes["catalyst_commitment_stage"] = _assessed(
            "definitive_agreement_or_completed_action", headline_id, "commitment"
        )
        axes["catalyst_credibility_repetition"] = _assessed(
            "possible_recycled_or_repeated_promotion", headline_id, "credibility"
        )
        attention_id = snapshot["evidence_coverage"]["attention_leadership"][
            "evidence_ids"
        ][0]
        axes["opportunity_obviousness_leadership_quality"] = _assessed(
            "dominant_persistent_leader", attention_id, "leadership"
        )
        with self.assertRaisesRegex(ValueError, "required evidence domain"):
            build_shadow_context_assessment(
                snapshot,
                axis_assessments=axes,
                model_provenance=_model_provenance(),
                expires_at="2026-08-03T13:32:00+00:00",
            )

    def test_assessment_requires_claim_citation_union_and_bounded_expiry(self):
        snapshot = _snapshot()
        axes = {axis: _abstained() for axis in SEMANTIC_AXES}
        headline_id = snapshot["evidence_coverage"]["catalyst_headline"][
            "evidence_ids"
        ][0]
        axes["catalyst_substance_specificity"] = _assessed(
            "specific_event_terms_incomplete", headline_id, "substance"
        )
        axes["catalyst_commitment_stage"] = _assessed(
            "definitive_agreement_or_completed_action", headline_id, "commitment"
        )
        attention_id = snapshot["evidence_coverage"]["attention_leadership"][
            "evidence_ids"
        ][0]
        axes["opportunity_obviousness_leadership_quality"] = _assessed(
            "dominant_persistent_leader", attention_id, "leadership"
        )
        axes["catalyst_substance_specificity"]["evidence_ids"] = []
        with self.assertRaisesRegex(ValueError, "citation union"):
            build_shadow_context_assessment(
                snapshot,
                axis_assessments=axes,
                model_provenance=_model_provenance(),
                expires_at="2026-08-03T13:32:00+00:00",
            )

        axes["catalyst_substance_specificity"]["evidence_ids"] = [headline_id]
        with self.assertRaisesRegex(ValueError, "bounded logical TTL"):
            build_shadow_context_assessment(
                snapshot,
                axis_assessments=axes,
                model_provenance=_model_provenance(),
                expires_at="2026-08-03T13:36:01+00:00",
            )
        self.assertEqual(MAX_ASSESSMENT_TTL_SECONDS, 300)

    def test_assessment_tamper_fails_content_hash_validation(self):
        supplemental = [
            _supplemental("theme:state-1", "theme_regime", {"state": "hot"}),
            _supplemental("daily:levels-1", "daily_chart", {"prior_high": 8.0}),
        ]
        snapshot = _snapshot(supplemental=supplemental)
        headline_id = snapshot["evidence_coverage"]["catalyst_headline"][
            "evidence_ids"
        ][0]
        attention_id = snapshot["evidence_coverage"]["attention_leadership"][
            "evidence_ids"
        ][0]
        axes = {
            "catalyst_substance_specificity": _assessed(
                "specific_event_terms_incomplete", headline_id, "substance"
            ),
            "catalyst_commitment_stage": _assessed(
                "definitive_agreement_or_completed_action",
                headline_id,
                "commitment",
            ),
            "catalyst_credibility_repetition": _abstained(
                "insufficient_evidence"
            ),
            "theme_fit_no_news_acceptance": _assessed(
                "causal_theme_fit_present", "theme:state-1", "theme"
            ),
            "opportunity_obviousness_leadership_quality": _assessed(
                "dominant_persistent_leader", attention_id, "leadership"
            ),
            "chart_context_cleanliness": _assessed(
                "clear_room_and_clean_history", "daily:levels-1", "chart"
            ),
        }
        assessment = build_shadow_context_assessment(
            snapshot,
            axis_assessments=axes,
            model_provenance=_model_provenance(),
            expires_at="2026-08-03T13:32:00+00:00",
        )
        assessment["axes"]["theme_fit_no_news_acceptance"]["value"] = (
            "causal_theme_fit_absent"
        )
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            validate_shadow_context_assessment(assessment, snapshot=snapshot)


if __name__ == "__main__":
    unittest.main()
