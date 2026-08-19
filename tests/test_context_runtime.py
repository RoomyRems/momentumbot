import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from momentumbot.identity_resolved_universe import json_fingerprint
from momentumbot.research.context_heldout_panel import CONTRACT_ID, REGISTERED_DATES
from momentumbot.research.context_runtime import (
    DAILY_RUNTIME_ARTIFACT_ID,
    FROZEN_CONTRACT_CONTENT_SHA256S,
    MARKET_RUNTIME_ARTIFACT_ID,
    RUNTIME_REQUEST_CONTENT_SHA256,
    RUNTIME_REQUEST_ID,
    build_record_date_payload,
    build_record_root_manifest,
    validate_context_runtime_request,
    validate_market_runtime_manifest,
    validate_record_date_payload,
)
from momentumbot.research.daily_chart_context import (
    CONTRACT_ID as DAILY_CONTRACT_ID,
)
from scripts.build_context_daily_chart_runtime import build_daily_records_for_date
from scripts.build_context_heldout_market_runtime import (
    freeze_market_runtime_manifest,
    provider_pipeline_commands,
)
from scripts.build_context_snapshot_runtime import resolve_prior_runtime_root
from tests.test_context_assessment import _scanner_row


def _market_manifest():
    payload = {
        "schema_version": 1,
        "artifact_id": MARKET_RUNTIME_ARTIFACT_ID,
        "dates": list(REGISTERED_DATES),
        "registration": {
            "contract_id": CONTRACT_ID,
            "contract_content_sha256": "1" * 64,
            "request_id": RUNTIME_REQUEST_ID,
            "request_content_sha256": RUNTIME_REQUEST_CONTENT_SHA256,
            "label_content_review_started": False,
            "source_inventory_started": False,
            "session_calendar_content_sha256": "2" * 64,
        },
        "workflow": {
            "run_id": 1,
            "run_attempt": 1,
            "job": "build",
            "head_sha": "3" * 40,
        },
        "runtime_root_content_sha256s": {
            "identity": "4" * 64,
            "market": "5" * 64,
            "float": "6" * 64,
            "news": "7" * 64,
            "scanner": "8" * 64,
            "scanner_source_inputs": "9" * 64,
        },
        "date_results": {},
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
        "limits": [],
    }
    payload["content_sha256"] = json_fingerprint(payload)
    return payload


def _bars():
    index = pd.bdate_range(end="2026-07-31", periods=60, tz="UTC")
    index = index + pd.Timedelta(hours=20)
    return pd.DataFrame(
        [
            (3.0 + i * 0.05, 3.4 + i * 0.05, 2.8 + i * 0.05, 3.2 + i * 0.05, 100_000 + i)
            for i in range(60)
        ],
        columns=["open", "high", "low", "close", "volume"],
        index=index,
    )


class ContextRuntimeTests(unittest.TestCase):
    def test_runtime_request_is_fixed_label_blind_and_not_promotable(self):
        root = Path(__file__).resolve().parents[1]
        request = json.loads(
            (
                root
                / "research"
                / "data-audits"
                / "context-heldout-runtime-request-v0.1.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            validate_context_runtime_request(request), list(REGISTERED_DATES)
        )
        self.assertEqual(request["registered_dates"], list(REGISTERED_DATES))
        self.assertEqual(
            request["prior_completed_session_source"][
                "manifest_content_sha256"
            ],
            "2414f7389bf68d5a5e4b3302c646c9111020cb79ce06fc0213f7872062f79c48",
        )
        for field in (
            "uses_raw_transcripts",
            "uses_recap_inventory",
            "uses_ross_actions",
            "uses_retrospective_labels",
            "uses_later_price_outcomes",
            "top_n_selection_applied",
            "semantic_ai_included",
        ):
            self.assertFalse(request["causal_boundary"][field])
        self.assertFalse(request["eligibility"]["policy_promotion_eligible"])
        self.assertFalse(
            request["eligibility"][
                "human_evidence_review_allowed_before_successful_artifact_freeze"
            ]
        )

    def test_runtime_request_hashes_the_exact_frozen_contract_files(self):
        root = Path(__file__).resolve().parents[1]
        paths = {
            "context_panel_content_sha256": (
                root / "research/strategy/context-heldout-panel-v0.1.json"
            ),
            "context_assessment_content_sha256": (
                root
                / "research/strategy/discretion-context-assessment-shadow-v0.1.json"
            ),
            "daily_chart_content_sha256": (
                root / "research/strategy/daily-chart-context-shadow-v0.1.json"
            ),
            "theme_regime_content_sha256": (
                root / "research/strategy/theme-regime-context-shadow-v0.1.json"
            ),
        }
        observed = {
            key: json_fingerprint(json.loads(path.read_text(encoding="utf-8")))
            for key, path in paths.items()
        }
        self.assertEqual(observed, FROZEN_CONTRACT_CONTENT_SHA256S)

    def test_first_runtime_failure_is_permanent_and_not_promotable(self):
        root = Path(__file__).resolve().parents[1]
        audit = json.loads(
            (
                root
                / "research"
                / "data-audits"
                / "context-heldout-runtime-v0.1-run-32197398999-failure-2026-08-18.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(audit["workflow"]["run_id"], 32197398999)
        self.assertEqual(audit["workflow"]["conclusion"], "failure")
        self.assertEqual(
            audit["registered_inputs"]["runtime_request_content_sha256"],
            RUNTIME_REQUEST_CONTENT_SHA256,
        )
        self.assertEqual(
            audit["registered_inputs"]["prior_runtime_manifest_content_sha256"],
            "2414f7389bf68d5a5e4b3302c646c9111020cb79ce06fc0213f7872062f79c48",
        )
        self.assertEqual(len(audit["completed_stages"]["float_dates"]), 9)
        self.assertEqual(audit["failure"]["failed_trading_date"], "2026-08-06")
        for field in (
            "uses_raw_transcripts",
            "uses_recap_inventory",
            "uses_ross_actions",
            "uses_retrospective_labels",
            "uses_later_price_outcomes",
            "semantic_ai_included",
        ):
            self.assertFalse(audit["causal_boundary"][field])
        self.assertFalse(audit["disposition"]["partial_artifact_frozen"])
        self.assertFalse(audit["disposition"]["label_review_eligible"])
        self.assertFalse(audit["disposition"]["policy_promotion_eligible"])
        self.assertEqual(audit["disposition"]["runtime_strategy_effect"], "none")

    def test_run_32204337846_failures_are_permanent_and_not_promotable(self):
        root = Path(__file__).resolve().parents[1] / "research" / "data-audits"
        attempts = {
            number: json.loads(
                (
                    root
                    / (
                        "context-heldout-runtime-v0.1-run-32204337846-"
                        f"attempt-{number}-failure-2026-08-19.json"
                    )
                ).read_text(encoding="utf-8")
            )
            for number in (1, 2)
        }
        for number, audit in attempts.items():
            self.assertEqual(audit["workflow"]["run_id"], 32204337846)
            self.assertEqual(audit["workflow"]["run_attempt"], number)
            self.assertEqual(audit["workflow"]["conclusion"], "failure")
            self.assertEqual(
                audit["registered_inputs"]["runtime_request_content_sha256"],
                RUNTIME_REQUEST_CONTENT_SHA256,
            )
            self.assertEqual(
                audit["registered_inputs"][
                    "prior_runtime_manifest_content_sha256"
                ],
                "2414f7389bf68d5a5e4b3302c646c9111020cb79ce06fc0213f7872062f79c48",
            )
            for field in (
                "uses_raw_transcripts",
                "uses_recap_inventory",
                "uses_ross_actions",
                "uses_retrospective_labels",
                "uses_later_price_outcomes",
                "semantic_ai_included",
            ):
                self.assertFalse(audit["causal_boundary"][field])
            self.assertFalse(audit["disposition"]["partial_artifact_frozen"])
            self.assertFalse(audit["disposition"]["label_review_eligible"])
            self.assertFalse(audit["disposition"]["policy_promotion_eligible"])
            self.assertEqual(
                audit["disposition"]["runtime_strategy_effect"], "none"
            )
        self.assertEqual(attempts[1]["failure"]["status_code"], 429)
        self.assertTrue(
            attempts[1]["completed_stages"]["contract_and_regression_step_passed"]
        )
        self.assertFalse(attempts[1]["retry"]["code_changed_before_retry"])
        self.assertEqual(
            attempts[2]["failure"]["root_cause_classification"],
            "unbound_registration_variables_in_final_manifest_path",
        )
        self.assertTrue(
            attempts[2]["completed_stages"][
                "provider_independent_scanner_replay_validated_for_all_dates"
            ]
        )
        self.assertEqual(
            attempts[2]["completed_stages"]["market_candidate_total"], 195
        )

    def test_run_32243689589_failure_is_permanent_and_not_promotable(self):
        root = Path(__file__).resolve().parents[1] / "research" / "data-audits"
        audit = json.loads(
            (
                root
                / (
                    "context-heldout-runtime-v0.1-run-32243689589-"
                    "attempt-1-failure-2026-08-19.json"
                )
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(audit["workflow"]["run_id"], 32243689589)
        self.assertEqual(audit["workflow"]["run_attempt"], 1)
        self.assertEqual(audit["workflow"]["job_id"], 96039545750)
        self.assertEqual(
            audit["workflow"]["head_sha"],
            "e1d29d59498572977b2f8bd0b159fa4475275560",
        )
        self.assertEqual(
            audit["workflow"]["head_tree_sha"],
            "5d4e88577033d9f80e4e494b28ec10d459d7ed29",
        )
        self.assertEqual(
            audit["registered_inputs"]["runtime_request_content_sha256"],
            RUNTIME_REQUEST_CONTENT_SHA256,
        )
        self.assertEqual(
            audit["registered_inputs"][
                "prior_runtime_manifest_content_sha256"
            ],
            "2414f7389bf68d5a5e4b3302c646c9111020cb79ce06fc0213f7872062f79c48",
        )
        self.assertTrue(
            audit["completed_stages"][
                "provider_independent_scanner_replay_validated_for_all_dates"
            ]
        )
        self.assertEqual(
            audit["completed_stages"]["market_candidate_total"], 195
        )
        self.assertEqual(
            audit["completed_stages"]["market_manifest_content_sha256"],
            "e2ae38c63d8aeb5a1cd19f319114d677c84973f59c31fc8f03ca7ec4914d84f8",
        )
        self.assertEqual(
            audit["failure"]["root_cause_classification"],
            "unhandled_explicit_null_scanner_price_in_daily_chart_materializer",
        )
        self.assertEqual(
            audit["diagnostic_artifact"]["zip_sha256"],
            "377d79ef0613ae2b92633883caf00dba447f7567ae8c1e1af1203455788ead77",
        )
        for field in (
            "uses_raw_transcripts",
            "uses_recap_inventory",
            "uses_ross_actions",
            "uses_retrospective_labels",
            "uses_later_price_outcomes",
            "semantic_ai_included",
        ):
            self.assertFalse(audit["causal_boundary"][field])
        self.assertFalse(audit["disposition"]["partial_artifact_frozen"])
        self.assertFalse(audit["disposition"]["label_review_eligible"])
        self.assertFalse(audit["disposition"]["policy_promotion_eligible"])
        self.assertEqual(audit["disposition"]["runtime_strategy_effect"], "none")

    def test_run_32260356870_success_is_permanent_verified_and_not_promotable(self):
        root = Path(__file__).resolve().parents[1] / "research" / "data-audits"
        audit = json.loads(
            (
                root
                / (
                    "context-heldout-runtime-v0.1-run-32260356870-"
                    "success-2026-08-19.json"
                )
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(audit["workflow"]["run_id"], 32260356870)
        self.assertEqual(audit["workflow"]["conclusion"], "success")
        self.assertEqual(
            audit["workflow"]["head_sha"],
            "4a9f3512c1a79ae5d0df86f4a83a3864b2aa2ad2",
        )
        self.assertEqual(
            audit["workflow"]["tree_sha"],
            "3659efff5dc9567b4e5da3080bc80cc59ddeb327",
        )
        self.assertEqual(audit["artifact"]["id"], 9376599434)
        self.assertEqual(
            audit["artifact"]["independently_computed_zip_sha256"],
            "a29186eb092752cfafc031360cacf348bea5e607cb19ce326ddaff2ddfedac1a",
        )
        self.assertEqual(
            audit["registered_inputs"]["runtime_request_content_sha256"],
            RUNTIME_REQUEST_CONTENT_SHA256,
        )
        self.assertEqual(
            audit["registered_inputs"][
                "prior_runtime_manifest_content_sha256"
            ],
            "2414f7389bf68d5a5e4b3302c646c9111020cb79ce06fc0213f7872062f79c48",
        )
        verification = audit["independent_verification"]
        self.assertEqual(verification["content_sha256_claim_count"], 115)
        self.assertTrue(verification["all_content_sha256_claims_recomputed"])
        self.assertTrue(verification["all_parent_child_hash_links_match"])
        self.assertTrue(verification["provider_independent_scanner_replay_matches"])
        self.assertEqual(verification["market_candidate_count"], 195)
        self.assertEqual(verification["scanner_row_count"], 18954)
        self.assertEqual(verification["null_price_unavailable_count"], 29)
        unavailable = audit["null_price_unavailable_rows"]
        self.assertEqual(len(unavailable), 29)
        self.assertEqual(
            json_fingerprint(unavailable),
            verification["null_price_unavailable_rows_sha256"],
        )
        for row in unavailable:
            self.assertEqual(
                row["reason"],
                "decision_price_unavailable_missing_candidate_completed_bar",
            )
            self.assertEqual(
                row["scanner_disposition"],
                "feature_state_unknown_fail_closed_missing_candidate_completed_bar",
            )
        for field in (
            "uses_raw_transcripts",
            "uses_recap_inventory",
            "uses_ross_actions",
            "uses_retrospective_labels",
            "uses_later_price_outcomes",
            "semantic_ai_included",
            "semantic_assessments_included",
            "top_n_selection_applied",
        ):
            self.assertFalse(audit["causal_boundary"][field])
        self.assertTrue(audit["causal_boundary"]["all_market_candidates_retained"])
        self.assertEqual(audit["causal_boundary"]["runtime_strategy_effect"], "none")
        self.assertFalse(audit["eligibility"]["policy_promotion_eligible"])

    def test_workflow_uses_registered_builders_and_no_transcript_archive(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (
            root / ".github/workflows/context-heldout-runtime.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("build_context_heldout_market_runtime.py", workflow)
        self.assertIn("build_context_daily_chart_runtime.py", workflow)
        self.assertIn("build_context_snapshot_runtime.py", workflow)
        self.assertIn("run-id: 32071946359", workflow)
        self.assertIn("name: context-heldout-runtime-v0.1", workflow)
        self.assertNotIn("project_sources", workflow)
        self.assertNotIn("dataset_daytradewarrior", workflow)

    def test_market_manifest_is_hash_bound_label_blind_and_all_candidate(self):
        payload = _market_manifest()
        self.assertEqual(validate_market_runtime_manifest(payload), list(REGISTERED_DATES))
        changed = copy.deepcopy(payload)
        changed["causal_boundary"]["uses_ross_actions"] = True
        changed["content_sha256"] = json_fingerprint(
            {key: value for key, value in changed.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "uses_ross_actions"):
            validate_market_runtime_manifest(changed)

    def test_generic_date_and_root_payloads_preserve_missing_records(self):
        date_payloads = {}
        for value in REGISTERED_DATES:
            payload = build_record_date_payload(
                artifact_id=DAILY_RUNTIME_ARTIFACT_ID,
                contract_id=DAILY_CONTRACT_ID,
                trading_date=value,
                source_hashes={"market": "a" * 64},
                records=[],
                unavailable=[{"symbol": "AAA", "reason": "missing"}],
            )
            validate_record_date_payload(
                payload,
                artifact_id=DAILY_RUNTIME_ARTIFACT_ID,
                contract_id=DAILY_CONTRACT_ID,
            )
            date_payloads[value] = payload
        root = build_record_root_manifest(
            artifact_id=DAILY_RUNTIME_ARTIFACT_ID,
            contract_id=DAILY_CONTRACT_ID,
            contract_content_sha256="b" * 64,
            source_market_runtime_content_sha256="c" * 64,
            date_payloads=date_payloads,
        )
        self.assertEqual(root["record_count"], 0)
        self.assertEqual(root["unavailable_count"], len(REGISTERED_DATES))
        self.assertFalse(root["policy_promotion_eligible"])

    def test_provider_pipeline_uses_only_registered_dates_and_endpoint_identity_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            commands = provider_pipeline_commands(Path(temporary) / "runtime")
        flattened = [token for command in commands for token in command]
        for value in REGISTERED_DATES:
            self.assertIn(value, flattened)
        identity = next(
            command
            for command in commands
            if "audit_historical_identity_continuity.py" in command[1]
        )
        marker = identity.index("--dates")
        self.assertEqual(
            identity[marker + 1 : marker + 3],
            [REGISTERED_DATES[0], REGISTERED_DATES[-1]],
        )
        self.assertIn("--persist-source-inputs", commands[-1])

    def test_final_market_manifest_path_loads_and_binds_frozen_registration(self):
        scanner_rows = [{"symbol": "AAA", "decision_time": "2026-07-24T08:00:00-04:00"}]
        source_inputs = SimpleNamespace(
            trading_date=REGISTERED_DATES[0],
            source_hashes={"source": "a" * 64},
            membership_symbols=("AAA",),
            candidate_symbols=("AAA",),
            previous_close_by_symbol={},
            rank_raw_minute_bars_by_symbol={},
            candidate_raw_minute_bars_by_symbol={},
            candidate_exact_rvol_by_symbol={},
        )
        calendar = {
            "schema_version": 1,
            "dates": list(REGISTERED_DATES),
            "sessions": [
                {"trading_date": value, "session_observed": True}
                for value in REGISTERED_DATES
            ],
        }
        with tempfile.TemporaryDirectory() as temporary, patch(
            "scripts.build_context_heldout_market_runtime._root_content_sha256",
            return_value="a" * 64,
        ), patch(
            "scripts.build_context_heldout_market_runtime.load_identity_resolved_universe",
            return_value=([{"ticker": "AAA"}], {}, {}),
        ), patch(
            "scripts.build_context_heldout_market_runtime.load_market_candidate_payload",
            return_value=([{"symbol": "AAA"}], {}, {}),
        ), patch(
            "scripts.build_context_heldout_market_runtime.load_causal_float_records",
            return_value=([], {"summary": {"records_sha256": "b" * 64}}),
        ), patch(
            "scripts.build_context_heldout_market_runtime.load_publication_timed_news",
            return_value=([], {}, {}),
        ), patch(
            "scripts.build_context_heldout_market_runtime.load_scanner_source_input_bundle",
            return_value=(source_inputs, {"content_sha256": "c" * 64}),
        ), patch(
            "scripts.build_context_heldout_market_runtime.load_causal_scanner_snapshot",
            return_value=(scanner_rows, {"content_sha256": "d" * 64}, {}),
        ), patch(
            "scripts.build_context_heldout_market_runtime.build_scanner_snapshot_rows",
            return_value=scanner_rows,
        ):
            manifest = freeze_market_runtime_manifest(
                Path(temporary) / "runtime",
                calendar=calendar,
                workflow_run_id=1,
                workflow_run_attempt=3,
                workflow_job="build",
                head_sha="e" * 40,
            )

        self.assertEqual(
            manifest["registration"]["contract_content_sha256"],
            FROZEN_CONTRACT_CONTENT_SHA256S["context_panel_content_sha256"],
        )
        self.assertEqual(
            manifest["registration"]["request_content_sha256"],
            RUNTIME_REQUEST_CONTENT_SHA256,
        )
        self.assertEqual(manifest["workflow"]["run_attempt"], 3)
        self.assertEqual(len(manifest["date_results"]), len(REGISTERED_DATES))

    def test_prior_runtime_root_accepts_direct_or_named_artifact_layout_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "heldout-runtime-manifest.json"
            manifest.write_text("{}\n", encoding="utf-8")
            self.assertEqual(resolve_prior_runtime_root(root), root)

            nested = root / "discretion-heldout-runtime-v0.1"
            nested.mkdir()
            (nested / "heldout-runtime-manifest.json").write_text(
                "{}\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "ambiguous"):
                resolve_prior_runtime_root(root)

            manifest.unlink()
            self.assertEqual(resolve_prior_runtime_root(root), nested)

    def test_daily_runtime_builds_activation_record_and_preserves_unavailable(self):
        scanner = _scanner_row()
        packet = {
            "symbol": "AAA",
            "decision_time": scanner["decision_time"],
            "packet_reason": "candidate_activation",
        }
        identity = {
            "ticker": "AAA",
            "identity_identifier_kind": "composite_figi",
            "identity_identifier": "BBG000TEST01",
        }
        records, unavailable = build_daily_records_for_date(
            trading_date="2026-08-03",
            scanner_rows=[scanner],
            catalyst_packets=[packet],
            identity_rows=[identity],
            split_daily_bars_by_symbol={"AAA": _bars()},
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(unavailable, [])
        self.assertEqual(records[0]["symbol"], "AAA")
        self.assertFalse(records[0]["causal_cutoff"]["decision_session_bar_used"])

        records, unavailable = build_daily_records_for_date(
            trading_date="2026-08-03",
            scanner_rows=[scanner],
            catalyst_packets=[packet],
            identity_rows=[identity],
            split_daily_bars_by_symbol={},
        )
        self.assertEqual(records, [])
        self.assertEqual(unavailable[0]["reason"], "no_prior_completed_split_adjusted_daily_bars")

    def test_daily_runtime_preserves_null_decision_price_as_unavailable(self):
        scanner = _scanner_row()
        scanner["candidate_completed_bar_present"] = False
        scanner["candidate_bar_available_at"] = None
        scanner["price"] = None
        scanner["disposition"] = (
            "feature_state_unknown_fail_closed_missing_candidate_completed_bar"
        )
        packet = {
            "symbol": "AAA",
            "decision_time": scanner["decision_time"],
            "packet_reason": "provider_event_set_changed",
        }
        identity = {
            "ticker": "AAA",
            "identity_identifier_kind": "composite_figi",
            "identity_identifier": "BBG000TEST01",
        }

        records, unavailable = build_daily_records_for_date(
            trading_date="2026-08-03",
            scanner_rows=[scanner],
            catalyst_packets=[packet],
            identity_rows=[identity],
            split_daily_bars_by_symbol={"AAA": _bars()},
        )

        self.assertEqual(records, [])
        self.assertEqual(
            unavailable,
            [
                {
                    "symbol": "AAA",
                    "decision_time": scanner["decision_time"],
                    "packet_reason": "provider_event_set_changed",
                    "reason": (
                        "decision_price_unavailable_"
                        "missing_candidate_completed_bar"
                    ),
                    "scanner_disposition": (
                        "feature_state_unknown_fail_closed_"
                        "missing_candidate_completed_bar"
                    ),
                }
            ],
        )
        self.assertNotIn("decision_price", unavailable[0])

    def test_daily_runtime_keeps_invalid_non_null_price_fail_closed(self):
        packet = {
            "symbol": "AAA",
            "decision_time": _scanner_row()["decision_time"],
            "packet_reason": "provider_event_set_changed",
        }
        identity = {
            "ticker": "AAA",
            "identity_identifier_kind": "composite_figi",
            "identity_identifier": "BBG000TEST01",
        }

        for decision_price in (0.0, "not-a-price"):
            scanner = _scanner_row()
            scanner["price"] = decision_price
            with self.subTest(decision_price=decision_price), self.assertRaises(
                ValueError
            ):
                build_daily_records_for_date(
                    trading_date="2026-08-03",
                    scanner_rows=[scanner],
                    catalyst_packets=[packet],
                    identity_rows=[identity],
                    split_daily_bars_by_symbol={"AAA": _bars()},
                )


if __name__ == "__main__":
    unittest.main()
