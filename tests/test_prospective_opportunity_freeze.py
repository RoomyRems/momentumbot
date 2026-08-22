import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from momentumbot.research.account_chronological_integration import PANEL_ID
from momentumbot.research.microstructure_contract import canonical_fingerprint
from momentumbot.research.prospective_market_input_capture import (
    CONTRACT_CONTENT_SHA256 as MARKET_INPUT_CONTRACT_CONTENT_SHA256,
    PRE_DECISION_QUOTE_NS,
    build_request_manifest,
    load_capture_contract,
)
from momentumbot.research.prospective_opportunity_freeze import (
    CONTRACT_CONTENT_SHA256,
    CONTRACT_ID,
    DECISION_SEMANTICS,
    GENERAL_PROFILE_ID,
    PARENT_CHECKPOINT_SHA,
    PARENT_CHECKPOINT_TREE_SHA,
    SMALL_PROFILE_ID,
    build_daily_decision_source,
    build_daily_opportunity_freeze,
    build_opportunity_manifest,
    expected_opportunity_id,
    load_daily_decision_source,
    load_opportunity_freeze_contract,
    validate_daily_decision_source,
    validate_freeze_manifest,
    validate_opportunity_freeze_contract,
    write_daily_opportunity_freeze,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "prospective-opportunity-freeze-v0.1.json"
)
MARKET_INPUT_CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "prospective-market-input-capture-v0.1.json"
)
REGISTRATION_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "prospective-opportunity-freeze-v0.1-registration-2026-08-22.json"
)
WORKFLOW = ROOT / ".github" / "workflows" / "prospective-opportunity-freeze.yml"


def _ns(value: str) -> int:
    return int(datetime.fromisoformat(value).astimezone(UTC).timestamp() * 1_000_000_000)


def _rehash(payload: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(payload)
    unsigned = {key: value for key, value in result.items() if key != "content_sha256"}
    result["content_sha256"] = canonical_fingerprint(unsigned)
    return result


def _decision(
    *,
    symbol: str = "TEST",
    activation_id: str = "activation-test",
    plan_id: str = "plan-test",
    qualified: str = "2026-08-24T11:29:30+00:00",
    decision: str = "2026-08-24T11:30:00+00:00",
    runtime_hash: str = "c" * 64,
    profiles: list[str] | None = None,
) -> dict[str, object]:
    return {
        "activation_id": activation_id,
        "plan_id": plan_id,
        "symbol": symbol,
        "candidate_qualified_ts_ns": _ns(qualified),
        "decision_ts_ns": _ns(decision),
        "micro_runtime_content_sha256": runtime_hash,
        "eligible_strategy_profile_ids": profiles or [GENERAL_PROFILE_ID],
    }


def _source(*decisions: dict[str, object], candidate_count: int | None = None):
    return build_daily_decision_source(
        trading_date="2026-08-24",
        scanner_runtime_content_sha256="a" * 64,
        micro_runtime_manifest_content_sha256="b" * 64,
        candidate_count=(len(decisions) if candidate_count is None else candidate_count),
        decisions=decisions,
    )


class ProspectiveOpportunityFreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load_opportunity_freeze_contract(CONTRACT)
        cls.market_input_contract = load_capture_contract(MARKET_INPUT_CONTRACT)
        cls.source = _source(
            _decision(
                profiles=[GENERAL_PROFILE_ID, SMALL_PROFILE_ID],
            ),
            _decision(
                symbol="NEXT",
                activation_id="activation-next",
                plan_id="plan-next",
                qualified="2026-08-24T11:30:10+00:00",
                decision="2026-08-24T11:30:20+00:00",
                runtime_hash="d" * 64,
                profiles=[SMALL_PROFILE_ID],
            ),
        )

    def test_contract_binds_parent_profiles_and_zero_authority(self):
        self.assertEqual(self.contract["content_sha256"], CONTRACT_CONTENT_SHA256)
        parents = self.contract["frozen_parents"]
        self.assertEqual(parents["parent_checkpoint_sha"], PARENT_CHECKPOINT_SHA)
        self.assertEqual(
            parents["parent_checkpoint_tree_sha"],
            PARENT_CHECKPOINT_TREE_SHA,
        )
        self.assertEqual(
            parents["market_input_capture_contract_content_sha256"],
            MARKET_INPUT_CONTRACT_CONTENT_SHA256,
        )
        source = self.contract["source_contract"]
        self.assertTrue(source["profile_union_required"])
        self.assertTrue(source["every_causal_micro_decision_retained"])
        self.assertEqual(source["decision_semantics"], DECISION_SEMANTICS)
        authority = self.contract["authority_boundary"]
        self.assertEqual(authority["databento_credit_authorized_usd"], "0")
        self.assertFalse(authority["provider_metadata_quote_authorized"])
        self.assertFalse(authority["provider_request_authorized"])
        self.assertFalse(authority["paper_order_authorized"])
        self.assertFalse(authority["runtime_authority_created"])

    def test_source_builder_is_deterministic_and_profile_union_is_not_duplicated(self):
        late = _decision(
            symbol="NEXT",
            activation_id="activation-next",
            plan_id="plan-next",
            qualified="2026-08-24T11:30:10+00:00",
            decision="2026-08-24T11:30:20+00:00",
            runtime_hash="d" * 64,
            profiles=[SMALL_PROFILE_ID],
        )
        early = _decision(profiles=[GENERAL_PROFILE_ID, SMALL_PROFILE_ID])
        reordered = _source(late, early)
        self.assertEqual(reordered, self.source)
        rows = validate_daily_decision_source(reordered)
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            rows[0].eligible_strategy_profile_ids,
            (GENERAL_PROFILE_ID, SMALL_PROFILE_ID),
        )
        self.assertEqual(rows[0].symbol, "TEST")

    def test_stable_identity_excludes_profile_eligibility(self):
        general = _source(_decision(profiles=[GENERAL_PROFILE_ID]))
        both = _source(
            _decision(profiles=[GENERAL_PROFILE_ID, SMALL_PROFILE_ID])
        )
        self.assertEqual(
            general["decisions"][0]["opportunity_id"],
            both["decisions"][0]["opportunity_id"],
        )
        row = general["decisions"][0]
        self.assertEqual(
            row["opportunity_id"],
            expected_opportunity_id(
                trading_date="2026-08-24",
                activation_id=row["activation_id"],
                plan_id=row["plan_id"],
                symbol=row["symbol"],
                decision_ts_ns=row["decision_ts_ns"],
                micro_runtime_content_sha256=row[
                    "micro_runtime_content_sha256"
                ],
            ),
        )

    def test_same_symbol_time_is_sorted_by_opportunity_identity_for_handoff(self):
        source = _source(
            _decision(activation_id="activation-z", plan_id="plan-z"),
            _decision(activation_id="activation-a", plan_id="plan-a"),
        )
        ids = [row["opportunity_id"] for row in source["decisions"]]
        self.assertEqual(ids, sorted(ids))
        manifest = build_opportunity_manifest(self.contract, source)
        self.assertEqual(
            [row["opportunity_id"] for row in manifest["opportunities"]],
            ids,
        )

    def test_materializer_strips_provenance_to_exact_market_input_boundary(self):
        manifest = build_opportunity_manifest(self.contract, self.source)
        opportunities = manifest["opportunities"]
        self.assertEqual(len(opportunities), 2)
        self.assertEqual(
            set(opportunities[0]),
            {
                "opportunity_id",
                "trading_date",
                "symbol",
                "decision_ts_ns",
                "runtime_content_sha256",
            },
        )
        rendered = json.dumps(manifest, sort_keys=True)
        for prohibited in (
            "eligible_strategy_profile_ids",
            "activation_id",
            "plan_id",
            "quantity",
            "outcome",
        ):
            self.assertNotIn(prohibited, rendered)

    def test_daily_freeze_derives_exact_unquoted_request_pairs(self):
        result = build_daily_opportunity_freeze(
            self.contract,
            self.market_input_contract,
            self.source,
        )
        request = result.request_manifest
        self.assertEqual(request["opportunity_count"], 2)
        self.assertEqual(request["request_count"], 4)
        self.assertEqual(
            {(row["symbols"][0], row["schema"]) for row in request["requests"]},
            {
                ("NEXT", "mbp-1"),
                ("NEXT", "status"),
                ("TEST", "mbp-1"),
                ("TEST", "status"),
            },
        )
        test_quote = next(
            row
            for row in request["requests"]
            if row["symbols"] == ["TEST"] and row["schema"] == "mbp-1"
        )
        self.assertEqual(
            test_quote["start_ns"],
            self.source["decisions"][0]["decision_ts_ns"]
            - PRE_DECISION_QUOTE_NS,
        )
        self.assertFalse(request["provider_metadata_quote_made"])
        self.assertFalse(request["provider_timeseries_request_made"])
        self.assertEqual(request["databento_credit_authorized_usd"], "0")
        self.assertEqual(result.freeze_manifest["runtime_authority"], "none_unarmed")

    def test_zero_opportunity_date_is_retained_without_substitution(self):
        source = _source(candidate_count=3)
        result = build_daily_opportunity_freeze(
            self.contract,
            self.market_input_contract,
            source,
        )
        self.assertEqual(result.opportunity_manifest["opportunities"], [])
        self.assertEqual(result.request_manifest["requests"], [])
        self.assertEqual(result.request_manifest["request_count"], 0)
        self.assertTrue(result.freeze_manifest["zero_opportunity_date_retained"])
        self.assertEqual(result.freeze_manifest["candidate_count"], 3)

    def test_source_rejects_account_execution_and_retrospective_boundaries(self):
        for field, value in (
            ("account_snapshot_loaded", True),
            ("account_scarcity_applied", True),
            ("execution_scenario_applied", True),
            ("provider_quote_made", True),
            ("retrospective_labels_loaded", True),
            ("later_prices_or_pnl_loaded", True),
        ):
            changed = copy.deepcopy(self.source)
            changed[field] = value
            changed = _rehash(changed)
            with self.assertRaisesRegex(ValueError, "prohibited boundary"):
                validate_daily_decision_source(changed)

    def test_source_rejects_forbidden_fields_even_when_rehashed(self):
        for field, value in (
            ("outcome", "winner"),
            ("fill_price", 10.01),
            ("quantity", 100),
            ("ross_action", "buy"),
            ("selected_scenario", "baseline"),
        ):
            changed = copy.deepcopy(self.source)
            changed["decisions"][0][field] = value
            changed = _rehash(changed)
            with self.assertRaisesRegex(
                ValueError,
                "forbidden keys|row fields changed",
            ):
                validate_daily_decision_source(changed)

    def test_source_rejects_tamper_duplicate_and_wrong_date(self):
        tampered = copy.deepcopy(self.source)
        tampered["decisions"][0]["decision_ts_ns"] += 1
        tampered = _rehash(tampered)
        with self.assertRaisesRegex(ValueError, "identity changed"):
            validate_daily_decision_source(tampered)

        with self.assertRaisesRegex(ValueError, "chronological order|unique"):
            _source(_decision(), _decision(), candidate_count=2)

        wrong_date = copy.deepcopy(self.source)
        wrong_date["decisions"][0]["candidate_qualified_ts_ns"] = _ns(
            "2026-08-23T11:29:30+00:00"
        )
        row = wrong_date["decisions"][0]
        row["opportunity_id"] = expected_opportunity_id(
            trading_date="2026-08-24",
            activation_id=row["activation_id"],
            plan_id=row["plan_id"],
            symbol=row["symbol"],
            decision_ts_ns=row["decision_ts_ns"],
            micro_runtime_content_sha256=row["micro_runtime_content_sha256"],
        )
        wrong_date = _rehash(wrong_date)
        with self.assertRaisesRegex(ValueError, "registered trading date"):
            validate_daily_decision_source(wrong_date)

    def test_source_builder_rejects_invalid_date_order_profiles_and_counts(self):
        with self.assertRaisesRegex(ValueError, "outside the registered panel"):
            build_daily_decision_source(
                trading_date="2026-08-23",
                scanner_runtime_content_sha256="a" * 64,
                micro_runtime_manifest_content_sha256="b" * 64,
                candidate_count=0,
                decisions=(),
            )
        with self.assertRaisesRegex(ValueError, "cannot follow"):
            _source(
                _decision(
                    qualified="2026-08-24T11:31:00+00:00",
                    decision="2026-08-24T11:30:00+00:00",
                )
            )
        with self.assertRaisesRegex(ValueError, "unique and sorted"):
            _source(
                _decision(profiles=[SMALL_PROFILE_ID, GENERAL_PROFILE_ID])
            )
        with self.assertRaisesRegex(ValueError, "outside the frozen account panel"):
            _source(_decision(profiles=["future-profile"]))
        with self.assertRaisesRegex(ValueError, "candidate_count"):
            _source(_decision(), candidate_count=0)

    def test_rehashed_request_or_freeze_tamper_is_rejected(self):
        result = build_daily_opportunity_freeze(
            self.contract,
            self.market_input_contract,
            self.source,
        )
        opportunity = copy.deepcopy(result.opportunity_manifest)
        opportunity["opportunities"][0]["runtime_content_sha256"] = "e" * 64
        opportunity = _rehash(opportunity)
        matching_request = build_request_manifest(
            self.market_input_contract,
            opportunity,
        )
        matching_freeze = copy.deepcopy(result.freeze_manifest)
        matching_freeze["opportunity_manifest_content_sha256"] = opportunity[
            "content_sha256"
        ]
        matching_freeze["request_manifest_content_sha256"] = matching_request[
            "content_sha256"
        ]
        matching_freeze = _rehash(matching_freeze)
        with self.assertRaisesRegex(ValueError, "frozen source decisions"):
            validate_freeze_manifest(
                matching_freeze,
                contract=self.contract,
                market_input_contract=self.market_input_contract,
                source=self.source,
                opportunity_manifest=opportunity,
                request_manifest=matching_request,
            )

        request = copy.deepcopy(result.request_manifest)
        request["requests"][0]["start_ns"] += 1
        request = _rehash(request)
        with self.assertRaisesRegex(ValueError, "deterministic derivation"):
            validate_freeze_manifest(
                result.freeze_manifest,
                contract=self.contract,
                market_input_contract=self.market_input_contract,
                source=self.source,
                opportunity_manifest=result.opportunity_manifest,
                request_manifest=request,
            )

        freeze = copy.deepcopy(result.freeze_manifest)
        freeze["runtime_authority"] = "paper_orders"
        freeze = _rehash(freeze)
        with self.assertRaisesRegex(ValueError, "binding changed"):
            validate_freeze_manifest(
                freeze,
                contract=self.contract,
                market_input_contract=self.market_input_contract,
                source=self.source,
                opportunity_manifest=result.opportunity_manifest,
                request_manifest=result.request_manifest,
            )

    def test_contract_mutations_cannot_expand_scope_or_authority(self):
        raw = json.loads(CONTRACT.read_text(encoding="utf-8"))
        mutations = (
            ("source_contract", "account_scarcity_may_select_source_decisions", True),
            ("source_contract", "every_causal_micro_decision_retained", False),
            ("output_contract", "provider_quote_made", True),
            ("authority_boundary", "provider_request_authorized", True),
            ("authority_boundary", "paper_order_authorized", True),
        )
        for section, field, value in mutations:
            changed = copy.deepcopy(raw)
            changed[section][field] = value
            changed = _rehash(changed)
            with self.assertRaises(ValueError):
                validate_opportunity_freeze_contract(changed)

    def test_writer_and_loader_round_trip_exact_three_file_handoff(self):
        result = build_daily_opportunity_freeze(
            self.contract,
            self.market_input_contract,
            self.source,
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_path = root / "source.json"
            source_path.write_text(json.dumps(self.source), encoding="utf-8")
            self.assertEqual(load_daily_decision_source(source_path), self.source)
            output = root / "output"
            write_daily_opportunity_freeze(output, result)
            self.assertEqual(
                sorted(path.name for path in output.iterdir()),
                [
                    "freeze-manifest.json",
                    "opportunity-manifest.json",
                    "request-manifest.json",
                ],
            )
            self.assertEqual(
                json.loads((output / "freeze-manifest.json").read_text()),
                result.freeze_manifest,
            )
            with self.assertRaisesRegex(FileExistsError, "must be empty"):
                write_daily_opportunity_freeze(output, result)

    def test_cli_materializes_without_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_path = root / "prospective-daily-micro-decision-source.json"
            source_path.write_text(
                json.dumps(self.source, sort_keys=True),
                encoding="utf-8",
            )
            output = root / "output"
            env = {
                key: value
                for key, value in os.environ.items()
                if "ALPACA" not in key and "DATABENTO" not in key
            }
            current_pythonpath = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = str(ROOT / "src") + (
                os.pathsep + current_pythonpath if current_pythonpath else ""
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "freeze_prospective_opportunities.py"),
                    "--source",
                    str(source_path),
                    "--expected-trading-date",
                    "2026-08-24",
                    "--output-dir",
                    str(output),
                ],
                cwd=ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            summary = json.loads(completed.stdout)
            self.assertEqual(summary["opportunity_count"], 2)
            self.assertFalse(summary["provider_call_made"])
            self.assertFalse(summary["broker_order_submitted"])
            self.assertTrue((output / "freeze-manifest.json").exists())

    def test_workflow_is_source_bound_provider_free_and_not_prematurely_scheduled(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("workflow_call:", text)
        self.assertNotIn("schedule:", text)
        self.assertIn("actions: read", text)
        self.assertIn("contents: read", text)
        self.assertIn("actions/download-artifact@v4", text)
        self.assertIn("source_run_id", text)
        self.assertIn("prospective-daily-micro-decision-source.json", text)
        self.assertIn("freeze_prospective_opportunities.py", text)
        self.assertIn("EXPECTED_TRADING_DATE: ${{ inputs.trading_date }}", text)
        self.assertIn('--expected-trading-date "$EXPECTED_TRADING_DATE"', text)
        self.assertIn("retention-days: 90", text)
        for prohibited in (
            "ALPACA_API_KEY",
            "ALPACA_API_SECRET",
            "DATABENTO_API_KEY",
            "paper-api.alpaca.markets",
            "api.databento.com",
        ):
            self.assertNotIn(prohibited, text)

    def test_registration_audit_is_hash_bound_and_unarmed(self):
        audit = json.loads(REGISTRATION_AUDIT.read_text(encoding="utf-8"))
        unsigned = {
            key: value for key, value in audit.items() if key != "content_sha256"
        }
        self.assertEqual(
            canonical_fingerprint(unsigned),
            audit["content_sha256"],
        )
        self.assertEqual(audit["contract"]["content_sha256"], CONTRACT_CONTENT_SHA256)
        for row in audit["bound_files"]:
            self.assertEqual(
                hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest(),
                row["file_sha256"],
            )
        authority = audit["authority_boundary"]
        self.assertFalse(authority["provider_call_run"])
        self.assertFalse(authority["provider_quote_run"])
        self.assertFalse(authority["provider_download_run"])
        self.assertEqual(authority["databento_credit_used_usd"], "0")
        self.assertFalse(authority["broker_order_submitted"])
        self.assertFalse(authority["runtime_authority_created"])


if __name__ == "__main__":
    unittest.main()
