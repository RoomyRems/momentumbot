import copy
import json
import unittest
from pathlib import Path

from momentumbot.research.discretion_heldout_labels import (
    DEFAULT_ACTION_STATE,
    expand_candidate_labels,
    load_discretion_heldout_labels,
    summarize_action_states,
    validate_discretion_heldout_labels,
)
from momentumbot.research.discretion_heldout_panel import canonical_fingerprint


ROOT = Path(__file__).resolve().parents[1]
LABELS = (
    ROOT
    / "research"
    / "data-audits"
    / "discretion-heldout-labels-v0.1-2026-08-18.json"
)
RUNTIME_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "discretion-heldout-runtime-v0.1-2026-08-17.json"
)


def _rehash(payload):
    payload["content_sha256"] = canonical_fingerprint(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )


class DiscretionHeldoutLabelTests(unittest.TestCase):
    def setUp(self):
        self.payload = load_discretion_heldout_labels(
            LABELS,
            runtime_audit_path=RUNTIME_AUDIT,
        )

    def test_all_candidates_are_bound_to_frozen_runtime(self):
        self.assertEqual(
            sum(row["candidate_count"] for row in self.payload["date_results"].values()),
            119,
        )
        self.assertTrue(self.payload["registration"]["labels_created_after_runtime_freeze"])
        self.assertFalse(self.payload["source_batch"]["allowed_in_runtime"])
        self.assertEqual(self.payload["runtime_strategy_effect"], "none")

    def test_sparse_labels_expand_unknown_without_inferred_skips(self):
        july_21 = expand_candidate_labels(self.payload, "2026-07-21")
        self.assertEqual(len(july_21), 11)
        self.assertTrue(
            all(
                account_state == DEFAULT_ACTION_STATE
                for row in july_21.values()
                for account_state in row.values()
            )
        )
        sessions = self.payload["date_results"]["2026-07-21"][
            "account_session_evidence"
        ]
        self.assertEqual(
            sessions["main_account"]["activity_state"],
            "reported_no_completed_trade_day",
        )
        self.assertEqual(
            sessions["small_account"]["activity_state"],
            "reported_no_completed_trade_day",
        )

    def test_account_scoped_counts_are_conservative(self):
        self.assertEqual(
            summarize_action_states(self.payload),
            {
                "main_account": {
                    "participated": 9,
                    "explicitly_skipped_or_rejected": 7,
                    "discussed_but_action_unclear": 2,
                    "not_mentioned_or_unobservable": 101,
                    "source_unavailable": 0,
                },
                "small_account": {
                    "participated": 9,
                    "explicitly_skipped_or_rejected": 2,
                    "discussed_but_action_unclear": 2,
                    "not_mentioned_or_unobservable": 106,
                    "source_unavailable": 0,
                },
            },
        )

    def test_unfilled_small_account_order_is_not_participation(self):
        gmm = next(
            row
            for row in self.payload["date_results"]["2026-07-10"][
                "explicit_candidate_labels"
            ]
            if row["symbol"] == "GMM"
        )
        self.assertEqual(
            gmm["small_account"]["state"], "discussed_but_action_unclear"
        )
        self.assertEqual(
            gmm["small_account"]["trade_completion"], "attempted_no_fill"
        )

    def test_off_candidate_trades_and_ticker_corrections_are_retained(self):
        july_14 = self.payload["date_results"]["2026-07-14"]
        self.assertEqual(
            july_14["observed_off_candidate_actions"][0]["canonical_symbol"],
            "JTAI",
        )
        july_15 = self.payload["date_results"]["2026-07-15"]
        vivs = next(
            row
            for row in july_15["observed_off_candidate_actions"]
            if row["canonical_symbol"] == "VIVS"
        )
        self.assertEqual(vivs["main_account"]["state"], "participated")
        self.assertEqual(vivs["small_account"]["state"], "participated")
        correction_ids = {
            row["correction_id"] for row in self.payload["transcription_corrections"]
        }
        self.assertIn("2026-07-14-jti-to-jtai", correction_ids)
        self.assertIn("2026-07-16-ruby-to-rubi", correction_ids)

    def test_self_rehashed_runtime_candidate_tamper_fails_against_audit(self):
        changed = copy.deepcopy(self.payload)
        changed["date_results"]["2026-07-10"]["candidate_activations"]["GMM"] = (
            "2026-07-10T11:01:00+00:00"
        )
        changed["date_results"]["2026-07-10"]["candidate_activations_sha256"] = (
            canonical_fingerprint(
                {
                    "trading_date": "2026-07-10",
                    "candidate_activations": changed["date_results"]["2026-07-10"][
                        "candidate_activations"
                    ],
                }
            )
        )
        _rehash(changed)
        runtime = json.loads(RUNTIME_AUDIT.read_text(encoding="utf-8"))
        activations = {
            date: row["candidate_activations"]
            for date, row in runtime["date_results"].items()
        }
        with self.assertRaisesRegex(ValueError, "frozen runtime candidates"):
            validate_discretion_heldout_labels(
                changed,
                runtime_candidate_activations=activations,
            )

    def test_no_trade_session_cannot_enable_skip_inference(self):
        changed = copy.deepcopy(self.payload)
        changed["label_policy"]["no_trade_session_converts_unmentioned_to_skip"] = True
        _rehash(changed)
        with self.assertRaisesRegex(ValueError, "cannot relabel"):
            validate_discretion_heldout_labels(changed)

    def test_participation_requires_completed_trade(self):
        changed = copy.deepcopy(self.payload)
        changed["date_results"]["2026-07-20"]["explicit_candidate_labels"][0][
            "main_account"
        ]["trade_completion"] = "unknown"
        _rehash(changed)
        with self.assertRaisesRegex(ValueError, "requires a completed trade"):
            validate_discretion_heldout_labels(changed)


if __name__ == "__main__":
    unittest.main()
