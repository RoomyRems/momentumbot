import copy
import json
import unittest
from pathlib import Path

from momentumbot.research.theme_regime_context import (
    CONTRACT_ID,
    CONTEXT_HELDOUT_PANEL_CONTENT_SHA256,
    PRIOR_COMPLETED_SESSION_LOOKBACK,
    build_completed_theme_regime_session_summary,
    build_theme_regime_evidence,
    canonical_fingerprint,
    load_theme_regime_context_contract,
    theme_regime_supplemental_evidence,
    validate_theme_regime_evidence,
)
from tests.test_context_assessment import _scanner_row


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research" / "strategy" / "theme-regime-context-shadow-v0.1.json"
AUDIT = ROOT / "research" / "data-audits" / "theme-regime-context-shadow-v0.1.json"


def _row(
    symbol,
    decision_time="2026-08-03T13:31:00+00:00",
    *,
    rank=1,
    leader="AAA",
    news=True,
):
    row = _scanner_row()
    row["symbol"] = symbol
    row["activation_time"] = "2026-08-03T13:31:00+00:00"
    row["decision_time"] = decision_time
    row["required_source_bar_started_at"] = (
        "2026-08-03T13:30:00+00:00"
        if decision_time.endswith("13:31:00+00:00")
        else "2026-08-03T13:31:00+00:00"
    )
    row["candidate_bar_available_at"] = decision_time
    row["top_gainer_rank"] = rank
    row["rank_leader_symbol"] = leader
    row["rank_leader_percent_gain"] = 100.0
    row["price"] = 5.0 if symbol == "AAA" else 4.0
    row["percent_gain"] = 100.0 if symbol == "AAA" else 60.0
    if news:
        row["news_provider_status"] = "success"
        row["provider_news_event_count_as_of"] = 1
        row["has_provider_news_as_of"] = True
        row["provider_relative_no_news_as_of"] = False
        row["first_provider_news_published_at_as_of"] = (
            "2026-08-03T13:30:30+00:00"
        )
        row["latest_provider_news_published_at_as_of"] = (
            "2026-08-03T13:30:30+00:00"
        )
    else:
        row["news_provider_status"] = "success"
        row["provider_news_event_count_as_of"] = 0
        row["has_provider_news_as_of"] = False
        row["provider_relative_no_news_as_of"] = True
        row["first_provider_news_published_at_as_of"] = None
        row["latest_provider_news_published_at_as_of"] = None
    return row


def _news(symbol="AAA", *, headline_id="story-1", published=None, symbols=None):
    return {
        "symbol": symbol,
        "published_at": published or "2026-08-03T13:30:30+00:00",
        "headline_id": f"alpaca-benzinga:{headline_id}",
        "title": "Companies announce a joint artificial intelligence agreement",
        "source": "benzinga",
        "provider": "alpaca-benzinga",
        "provider_story_id": headline_id,
        "provider_symbols": symbols or [symbol],
        "original_created_at": "2026-08-03T13:30:00+00:00",
        "provider_updated_at": "2026-08-03T13:30:30+00:00",
        "availability_basis": "provider_updated_at",
    }


def _prior_summary(trading_date="2026-07-31"):
    rows = [
        _row("AAA", "2026-08-03T13:31:00+00:00", rank=1),
        _row("BBB", "2026-08-03T13:31:00+00:00", rank=2, news=False),
        _row("AAA", "2026-08-03T13:32:00+00:00", rank=1),
        _row("BBB", "2026-08-03T13:32:00+00:00", rank=2, news=False),
    ]
    replacement = trading_date
    for row in rows:
        for field in (
            "activation_time",
            "decision_time",
            "required_source_bar_started_at",
            "candidate_bar_available_at",
            "first_provider_news_published_at_as_of",
            "latest_provider_news_published_at_as_of",
        ):
            if row[field] is not None:
                row[field] = str(row[field]).replace("2026-08-03", replacement)
    return build_completed_theme_regime_session_summary(
        rows,
        trading_date=trading_date,
        source_scanner_records_content_sha256="9" * 64,
    )


def _record(scanner_rows=None, news_events=None, summaries=None):
    rows = scanner_rows or [
        _row("AAA", rank=1),
        _row("BBB", rank=2, news=False),
    ]
    return build_theme_regime_evidence(
        rows,
        [_news()] if news_events is None else news_events,
        [_prior_summary()] if summaries is None else summaries,
        symbol="AAA",
        decision_time="2026-08-03T13:31:00+00:00",
        source_artifact_content_sha256s={
            "scanner_records": "a" * 64,
            "publication_timed_news_events": "b" * 64,
            "prior_session_summaries": "c" * 64,
        },
    )


class ThemeRegimeContextTests(unittest.TestCase):
    def test_contract_freezes_observations_but_no_semantic_threshold(self):
        payload = load_theme_regime_context_contract(CONTRACT)
        self.assertEqual(payload["contract_id"], CONTRACT_ID)
        self.assertEqual(
            payload["feature_protocol"]["prior_completed_session_lookback"],
            PRIOR_COMPLETED_SESSION_LOOKBACK,
        )
        self.assertIsNone(payload["feature_protocol"]["hot_cold_threshold"])
        self.assertIsNone(payload["feature_protocol"]["theme_fit_rule"])
        self.assertIsNone(
            payload["feature_protocol"]["no_news_acceptance_threshold"]
        )
        self.assertEqual(
            payload["evaluation_boundary"]["registered_panel_content_sha256"],
            CONTEXT_HELDOUT_PANEL_CONTENT_SHA256,
        )
        self.assertEqual(payload["runtime_strategy_effect"], "none")

    def test_registration_audit_binds_contract_without_promotion(self):
        contract = load_theme_regime_context_contract(CONTRACT)
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(audit["contract_id"], CONTRACT_ID)
        self.assertEqual(
            audit["contract_content_sha256"],
            canonical_fingerprint(contract),
        )
        self.assertTrue(audit["decision"]["freeze_theme_regime_schema_v01"])
        self.assertFalse(audit["decision"]["freeze_hot_cold_threshold"])
        self.assertFalse(audit["decision"]["promote_theme_regime_rule"])

    def test_completed_session_summary_is_hash_bound_and_accounted(self):
        summary = _prior_summary()
        self.assertEqual(summary["candidate_count"], 2)
        self.assertEqual(summary["final_observed_candidate_count"], 2)
        self.assertEqual(
            summary["final_news_state_counts"][
                "provider_relative_no_news_candidate_count"
            ],
            1,
        )
        self.assertEqual(summary["final_rank_leader_symbol"], "AAA")
        self.assertEqual(len(summary["summary_content_sha256"]), 64)

    def test_builder_measures_same_minute_news_and_leadership_without_label(self):
        record = _record()
        features = record["features"]
        self.assertEqual(features["same_minute_observed_candidate_count"], 2)
        self.assertEqual(features["same_minute_rank_leader_symbol"], "AAA")
        self.assertEqual(
            features["same_minute_news_state_counts"][
                "provider_relative_no_news_candidate_count"
            ],
            1,
        )
        self.assertEqual(features["available_provider_story_count"], 1)
        self.assertEqual(features["subject_candidate_headline_count"], 1)
        self.assertEqual(features["prior_completed_session_count"], 1)
        self.assertIsNone(
            record["prohibited_outputs"]["hot_cold_regime_label"]
        )
        self.assertIsNone(record["prohibited_outputs"]["theme_fit_classification"])

    def test_future_scanner_rows_and_headlines_cannot_enter_decision_packet(self):
        rows = [
            _row("AAA", rank=1),
            _row("BBB", rank=2, news=False),
            _row("CCC", "2026-08-03T13:32:00+00:00", rank=3, news=False),
        ]
        future = _news(
            headline_id="future",
            published="2026-08-03T13:31:30+00:00",
        )
        record = _record(scanner_rows=rows, news_events=[_news(), future])
        observed = {
            row["symbol"]
            for row in record["features"]["same_minute_ranked_candidate_cohort"]
        }
        self.assertEqual(observed, {"AAA", "BBB"})
        self.assertEqual(record["features"]["available_provider_story_count"], 1)
        self.assertFalse(record["causal_cutoff"]["future_headline_used"])

    def test_cross_candidate_story_is_association_not_theme_classification(self):
        shared = [
            _news("AAA", headline_id="shared", symbols=["AAA", "BBB"]),
            _news("BBB", headline_id="shared", symbols=["AAA", "BBB"]),
        ]
        record = _record(news_events=shared)
        self.assertEqual(record["features"]["cross_candidate_story_count"], 1)
        story = record["input_rows"]["available_news_stories"][0]
        self.assertEqual(story["active_candidate_symbols"], ["AAA", "BBB"])
        self.assertIsNone(record["prohibited_outputs"]["theme_fit_classification"])

    def test_prior_summary_must_strictly_precede_current_session(self):
        with self.assertRaisesRegex(ValueError, "does not precede"):
            _record(summaries=[_prior_summary("2026-08-03")])

    def test_tamper_fails_hash_and_deterministic_reconstruction(self):
        record = _record()
        changed = copy.deepcopy(record)
        changed["features"]["same_minute_observed_candidate_count"] = 999
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            validate_theme_regime_evidence(changed)
        changed["record_content_sha256"] = canonical_fingerprint(
            {key: value for key, value in changed.items() if key != "record_content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "deterministic reconstruction"):
            validate_theme_regime_evidence(changed)

    def test_adapter_requires_frozen_artifact_hash_and_has_no_authority(self):
        record = _record()
        evidence = theme_regime_supplemental_evidence(
            record,
            source_artifact_content_sha256="f" * 64,
        )
        self.assertEqual(evidence["domain"], "theme_regime")
        self.assertEqual(evidence["source_contract_id"], CONTRACT_ID)
        self.assertTrue(evidence["evidence_id"].startswith("theme-regime:AAA:"))
        self.assertIsNone(evidence["payload"]["prohibited_outputs"]["order_action"])


if __name__ == "__main__":
    unittest.main()
