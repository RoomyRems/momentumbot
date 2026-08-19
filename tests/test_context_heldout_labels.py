import copy
import json
import unittest
from pathlib import Path

from momentumbot.research.context_heldout_labels import (
    DEFAULT_ACTION_STATE,
    expand_candidate_labels,
    load_context_heldout_labels,
    summarize_action_states,
    validate_context_heldout_labels,
)
from momentumbot.research.context_heldout_panel import canonical_fingerprint


ROOT = Path(__file__).resolve().parents[1]
LABELS = (
    ROOT
    / "research"
    / "data-audits"
    / "context-heldout-labels-v0.1-2026-08-19.json"
)
SEMANTIC_ROOT = (
    ROOT / "research" / "frozen" / "context-semantic-shadow-runtime-v0.1"
)
EXPECTED_CONTENT_SHA256 = (
    "3ff85b371de31ea5dc1d2e4afc4e334c6f6f5051bfe5c7340fb51007527b7cd1"
)


def _rehash(payload):
    payload["content_sha256"] = canonical_fingerprint(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )


class ContextHeldoutLabelTests(unittest.TestCase):
    def setUp(self):
        self.payload = load_context_heldout_labels(
            LABELS,
            semantic_root_path=SEMANTIC_ROOT,
        )

    def test_labels_bind_exact_frozen_runtime_semantic_tree_and_candidates(self):
        self.assertEqual(self.payload["content_sha256"], EXPECTED_CONTENT_SHA256)
        self.assertEqual(
            sum(row["candidate_count"] for row in self.payload["date_results"].values()),
            195,
        )
        parents = self.payload["frozen_parents"]
        self.assertEqual(
            parents["deterministic_runtime"]["snapshot_runtime_content_sha256"],
            "6dcc6f25ddb73e63b5f9c714e0c890ab954b15b099e7ba3a71ef948f9760939f",
        )
        self.assertEqual(
            parents["semantic_shadow"]["checkpoint_tree_sha"],
            "0c899fb80203c13fc4e5b59b758f1690ca892a33",
        )
        self.assertFalse(
            parents["semantic_shadow"]["retrospective_inventory_opened_before_freeze"]
        )

    def test_all_eight_files_are_inventoried_but_raw_archive_is_not_committed(self):
        archive = self.payload["source_archive"]
        self.assertEqual(archive["file_count"], 8)
        self.assertEqual(archive["record_count"], 2292)
        self.assertFalse(archive["raw_archive_committed_to_repository"])
        self.assertFalse(archive["allowed_in_runtime"])
        self.assertEqual(len(self.payload["sources"]), 14)
        self.assertTrue(
            all("caption_text" not in row and "captions" not in row for row in self.payload["sources"])
        )

    def test_publication_date_is_not_silently_used_as_trading_date(self):
        august_6_ids = set(self.payload["date_results"]["2026-08-06"]["source_ids"])
        self.assertEqual(
            august_6_ids,
            {"youtube:coqONALABpo", "youtube:cZcprj_8wEM"},
        )
        august_6_sources = {
            row["source_id"]: row for row in self.payload["sources"] if row["source_id"] in august_6_ids
        }
        self.assertTrue(
            all(row["published_date_text"] == "Aug 7, 2026" for row in august_6_sources.values())
        )
        excluded = {
            row["source_id"]: row for row in self.payload["excluded_source_records"]
        }
        self.assertIn("youtube:CA8i4Rc2bUY", excluded)
        self.assertFalse(excluded["youtube:CA8i4Rc2bUY"]["used_for_labels"])
        self.assertIn("2026-07-23", excluded["youtube:CA8i4Rc2bUY"]["content_date_resolution"])

    def test_sparse_counts_keep_unmentioned_candidates_unknown(self):
        self.assertEqual(
            summarize_action_states(self.payload),
            {
                "main_account": {
                    "participated": 11,
                    "explicitly_skipped_or_rejected": 4,
                    "discussed_but_action_unclear": 0,
                    "not_mentioned_or_unobservable": 180,
                    "source_unavailable": 0,
                },
                "small_account": {
                    "participated": 6,
                    "explicitly_skipped_or_rejected": 8,
                    "discussed_but_action_unclear": 0,
                    "not_mentioned_or_unobservable": 181,
                    "source_unavailable": 0,
                },
            },
        )
        july_30 = expand_candidate_labels(self.payload, "2026-07-30")
        self.assertEqual(
            july_30["NUWE"]["small_account"],
            DEFAULT_ACTION_STATE,
        )
        self.assertEqual(
            self.payload["date_results"]["2026-07-30"]["account_session_evidence"][
                "small_account"
            ]["activity_state"],
            "reported_no_completed_trade_day",
        )

    def test_account_scope_is_preserved_on_same_symbol(self):
        july_27 = self.payload["date_results"]["2026-07-27"]
        edbl = next(row for row in july_27["explicit_candidate_labels"] if row["symbol"] == "EDBL")
        self.assertEqual(edbl["main_account"]["state"], "participated")
        self.assertEqual(
            edbl["small_account"]["state"],
            "explicitly_skipped_or_rejected",
        )
        august_3 = self.payload["date_results"]["2026-08-03"]
        fcuv = next(row for row in august_3["explicit_candidate_labels"] if row["symbol"] == "FCUV")
        self.assertEqual(fcuv["main_account"]["state"], "participated")
        self.assertEqual(
            fcuv["small_account"]["state"],
            "explicitly_skipped_or_rejected",
        )

    def test_off_candidate_actions_and_transcription_corrections_are_retained(self):
        july_24 = self.payload["date_results"]["2026-07-24"]
        exyn = next(
            row for row in july_24["observed_off_candidate_actions"]
            if row["canonical_symbol"] == "EXYN"
        )
        self.assertEqual(exyn["main_account"]["state"], "participated")
        self.assertEqual(exyn["small_account"]["state"], "participated")
        august_6 = self.payload["date_results"]["2026-08-06"]
        self.assertEqual(
            {row["canonical_symbol"] for row in august_6["observed_off_candidate_actions"]},
            {"DSY", "MB", "NAMI"},
        )
        correction_ids = {
            row["correction_id"] for row in self.payload["transcription_corrections"]
        }
        self.assertIn("2026-07-28-infl-inlx-infs-to-inlf", correction_ids)
        self.assertIn("2026-08-06-dsw-to-dsy", correction_ids)
        self.assertTrue(
            all(row["silent_rewrite_allowed"] is False for row in self.payload["transcription_corrections"])
        )

    def test_self_rehashed_candidate_tamper_fails_against_semantic_parent(self):
        changed = copy.deepcopy(self.payload)
        result = changed["date_results"]["2026-08-04"]
        result["candidate_symbols"].remove("AMIX")
        result["candidate_count"] -= 1
        result["explicit_candidate_labels"] = []
        result["explicit_candidate_symbol_count"] = 0
        result["candidate_symbols_sha256"] = canonical_fingerprint(
            {
                "trading_date": "2026-08-04",
                "candidate_symbols": result["candidate_symbols"],
            }
        )
        changed["summary"]["candidate_symbol_date_count"] -= 1
        changed["summary"]["explicit_candidate_symbol_date_count"] -= 1
        changed["summary"]["account_action_states"]["main_account"][
            "explicitly_skipped_or_rejected"
        ] -= 1
        changed["summary"]["account_action_states"]["main_account"][
            "not_mentioned_or_unobservable"
        ] += 1
        changed["summary"]["account_action_states"]["small_account"][
            "explicitly_skipped_or_rejected"
        ] -= 1
        changed["summary"]["account_action_states"]["small_account"][
            "not_mentioned_or_unobservable"
        ] += 1
        _rehash(changed)
        candidates = {}
        for trading_date in self.payload["date_results"]:
            date_payload = json.loads(
                (SEMANTIC_ROOT / "dates" / f"{trading_date}.json").read_text(encoding="utf-8")
            )
            candidates[trading_date] = {
                record["symbol"] for record in date_payload["records"]
            }
        with self.assertRaisesRegex(ValueError, "frozen semantic candidates"):
            validate_context_heldout_labels(changed, semantic_candidates=candidates)

    def test_no_trade_session_cannot_enable_skip_inference(self):
        changed = copy.deepcopy(self.payload)
        changed["label_policy"]["no_trade_session_converts_unmentioned_to_skip"] = True
        _rehash(changed)
        with self.assertRaisesRegex(ValueError, "cannot infer candidate skips"):
            validate_context_heldout_labels(changed)

    def test_labels_cannot_enable_strategy_authority(self):
        changed = copy.deepcopy(self.payload)
        changed["policy_promotion_eligible"] = True
        _rehash(changed)
        with self.assertRaisesRegex(ValueError, "policy_promotion_eligible"):
            validate_context_heldout_labels(changed)


if __name__ == "__main__":
    unittest.main()
