import copy
import json
import unittest
from pathlib import Path

from momentumbot.research.catalyst_timing import (
    CONTRACT_ID,
    derive_catalyst_timing_rows,
    load_catalyst_timing_contract,
    validate_catalyst_timing_contract,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research" / "strategy" / "catalyst-timing-shadow-v0.1.json"
AUDIT = ROOT / "research" / "data-audits" / "catalyst-timing-shadow-v0.1.json"


def _row(
    *,
    symbol="AAA",
    activation="2026-01-02T12:00:00+00:00",
    decision="2026-01-02T12:00:00+00:00",
    count=0,
    first=None,
    latest=None,
    status="success",
):
    present = status == "success" and count > 0
    no_news = status == "success" and count == 0
    return {
        "symbol": symbol,
        "activation_time": activation,
        "decision_time": decision,
        "news_provider_status": status,
        "provider_news_event_count_as_of": count,
        "has_provider_news_as_of": present,
        "provider_relative_no_news_as_of": no_news,
        "first_provider_news_published_at_as_of": first,
        "latest_provider_news_published_at_as_of": latest,
    }


class CatalystTimingTests(unittest.TestCase):
    def test_contract_freezes_timing_features_without_quality_or_gate(self):
        payload = load_catalyst_timing_contract(CONTRACT)
        self.assertEqual(payload["contract_id"], CONTRACT_ID)
        self.assertFalse(payload["catalyst_quality_score_frozen"])
        self.assertFalse(payload["selection_threshold_frozen"])
        self.assertEqual(payload["runtime_strategy_effect"], "none")

    def test_contract_rejects_strategy_gate(self):
        payload = load_catalyst_timing_contract(CONTRACT)
        changed = copy.deepcopy(payload)
        changed["feature_definitions"][0]["strategy_gate_enabled"] = True
        with self.assertRaisesRegex(ValueError, "cannot be strategy gates"):
            validate_catalyst_timing_contract(changed)

    def test_frozen_validation_audit_is_pinned_and_non_promotional(self):
        payload = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(payload["contract_id"], CONTRACT_ID)
        self.assertEqual(
            payload["source_scanner_artifact"]["artifact_zip_sha256"],
            "dd05dcd58bd3adc20e18416035b2c6b4c517fb57d5d853d63c2b327d1b2a1d12",
        )
        self.assertEqual(payload["cross_date_summary"]["candidate_minute_row_count"], 2213)
        self.assertEqual(
            payload["cross_date_summary"][
                "candidates_qualified_before_later_first_provider_news"
            ],
            ["GT", "HOUR", "OSRH", "VRAX"],
        )
        self.assertFalse(payload["policy_promotion_eligible"])
        self.assertFalse(payload["decision"]["promote_catalyst_rule"])

    def test_news_arrival_after_activation_is_measured_causally(self):
        rows = [
            _row(),
            _row(
                decision="2026-01-02T12:01:00+00:00",
                count=1,
                first="2026-01-02T12:00:30+00:00",
                latest="2026-01-02T12:00:30+00:00",
            ),
            _row(
                decision="2026-01-02T12:02:00+00:00",
                count=2,
                first="2026-01-02T12:00:30+00:00",
                latest="2026-01-02T12:01:50+00:00",
            ),
        ]
        derived = derive_catalyst_timing_rows(reversed(rows))

        activation = derived[0]
        self.assertEqual(activation["provider_news_state"], "provider_relative_none")
        self.assertFalse(activation["provider_news_present_at_activation"])
        self.assertIsNone(activation["candidate_qualified_before_first_provider_news"])

        arrival = derived[1]
        self.assertEqual(arrival["provider_news_event_count_change_from_prior_minute"], 1)
        self.assertTrue(arrival["new_provider_news_became_available_this_minute"])
        self.assertTrue(arrival["provider_news_state_changed_from_prior_minute"])
        self.assertEqual(arrival["observed_provider_news_state_tenure_minutes"], 1)
        self.assertEqual(arrival["seconds_from_activation_to_first_provider_news"], 30.0)
        self.assertEqual(arrival["seconds_since_first_provider_news"], 30.0)
        self.assertTrue(arrival["candidate_qualified_before_first_provider_news"])

        second = derived[2]
        self.assertEqual(second["provider_news_event_count_change_from_prior_minute"], 1)
        self.assertFalse(second["provider_news_state_changed_from_prior_minute"])
        self.assertEqual(second["observed_provider_news_state_tenure_minutes"], 2)
        self.assertEqual(second["seconds_since_latest_provider_news"], 10.0)

    def test_preexisting_news_is_distinguished_from_post_activation_news(self):
        derived = derive_catalyst_timing_rows(
            [
                _row(
                    symbol="BBB",
                    count=1,
                    first="2026-01-02T11:00:00+00:00",
                    latest="2026-01-02T11:00:00+00:00",
                )
            ]
        )[0]
        self.assertTrue(derived["provider_news_present_at_activation"])
        self.assertEqual(derived["seconds_from_activation_to_first_provider_news"], -3600.0)
        self.assertFalse(derived["candidate_qualified_before_first_provider_news"])

    def test_provider_error_remains_unknown_not_no_news(self):
        derived = derive_catalyst_timing_rows([_row(status="provider_error")])[0]
        self.assertEqual(derived["provider_news_state"], "unknown_fail_closed")
        self.assertIsNone(derived["provider_news_present_at_activation"])
        self.assertIsNone(derived["candidate_qualified_before_first_provider_news"])

    def test_future_publication_fails_closed(self):
        row = _row(
            count=1,
            first="2026-01-02T12:00:01+00:00",
            latest="2026-01-02T12:00:01+00:00",
        )
        with self.assertRaisesRegex(ValueError, "ordered and causal"):
            derive_catalyst_timing_rows([row])

    def test_event_count_cannot_decrease(self):
        rows = [
            _row(
                count=2,
                first="2026-01-02T11:00:00+00:00",
                latest="2026-01-02T11:30:00+00:00",
            ),
            _row(
                decision="2026-01-02T12:01:00+00:00",
                count=1,
                first="2026-01-02T11:00:00+00:00",
                latest="2026-01-02T11:00:00+00:00",
            ),
        ]
        with self.assertRaisesRegex(ValueError, "cannot decrease"):
            derive_catalyst_timing_rows(rows)

    def test_observation_gap_resets_transitions(self):
        rows = [
            _row(),
            _row(decision="2026-01-02T12:02:00+00:00"),
        ]
        derived = derive_catalyst_timing_rows(rows)
        self.assertIsNone(derived[1]["provider_news_event_count_change_from_prior_minute"])
        self.assertIsNone(derived[1]["provider_news_state_changed_from_prior_minute"])
        self.assertEqual(derived[1]["observed_provider_news_state_tenure_minutes"], 1)


if __name__ == "__main__":
    unittest.main()
