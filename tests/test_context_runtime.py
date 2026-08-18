import copy
import json
import tempfile
import unittest
from pathlib import Path

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
from scripts.build_context_heldout_market_runtime import provider_pipeline_commands
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


if __name__ == "__main__":
    unittest.main()
