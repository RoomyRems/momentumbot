import unittest

from momentumbot.identity_resolved_universe import json_fingerprint
from scripts.build_discretion_shadow_runtime import (
    ARTIFACT_ID,
    SOURCE_ARTIFACT_ID,
    _freeze_rows,
    _validate_frozen_rows,
    _validate_source_runtime,
)
from momentumbot.research.discretion_heldout_panel import REGISTERED_DATES


class BuildDiscretionShadowRuntimeTests(unittest.TestCase):
    def _source(self):
        payload = {
            "schema_version": 1,
            "artifact_id": SOURCE_ARTIFACT_ID,
            "dates": list(REGISTERED_DATES),
            "registration": {"label_content_review_started": False},
            "causal_boundary": {
                "uses_benchmark_labels": False,
                "uses_ross_actions": False,
                "uses_retrospective_trade_outcomes": False,
                "uses_later_price_outcomes": False,
                "all_market_candidates_retained": True,
                "top_n_selection_applied": False,
                "provider_independent_scanner_replay_validated": True,
            },
            "eligibility": {
                "runtime_inputs_frozen": True,
                "policy_promotion_eligible": False,
            },
        }
        payload["content_sha256"] = json_fingerprint(payload)
        return payload

    def test_source_runtime_requires_unlabeled_frozen_all_candidate_replay(self):
        self.assertEqual(_validate_source_runtime(self._source()), list(REGISTERED_DATES))

        labeled = self._source()
        labeled["registration"]["label_content_review_started"] = True
        labeled["content_sha256"] = json_fingerprint(
            {key: value for key, value in labeled.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "labels were opened"):
            _validate_source_runtime(labeled)

        filtered = self._source()
        filtered["causal_boundary"]["top_n_selection_applied"] = True
        filtered["content_sha256"] = json_fingerprint(
            {key: value for key, value in filtered.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "top_n_selection_applied"):
            _validate_source_runtime(filtered)

        tampered = self._source()
        tampered["dates"] = list(reversed(REGISTERED_DATES))
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            _validate_source_runtime(tampered)

    def test_frozen_rows_are_hash_bound_and_shadow_only(self):
        payload = _freeze_rows(
            artifact_id=ARTIFACT_ID,
            contract_id="example-shadow-v0.1",
            trading_date="2026-07-10",
            rows=[{"symbol": "AAA", "decision_time": "2026-07-10T11:00:00+00:00"}],
            source_hashes={"scanner": "a" * 64},
        )
        _validate_frozen_rows(payload)
        self.assertEqual(payload["row_count"], 1)
        self.assertFalse(payload["policy_promotion_eligible"])
        self.assertEqual(payload["knowledge_policy"]["runtime_strategy_effect"], "none")
        expected = json_fingerprint(
            {key: value for key, value in payload.items() if key != "content_sha256"}
        )
        self.assertEqual(payload["content_sha256"], expected)

        payload["rows"][0]["symbol"] = "BBB"
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            _validate_frozen_rows(payload)


if __name__ == "__main__":
    unittest.main()
