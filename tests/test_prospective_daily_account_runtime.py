from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import yaml

from momentumbot.research.account_snapshot_capture import (
    AccountCredentials,
    AlpacaPaperAccountClient,
    capture_dual_account_bundle,
)
from momentumbot.research.microstructure_contract import canonical_fingerprint
from momentumbot.research.prospective_daily_account_runtime import (
    CONTRACT_CONTENT_SHA256,
    build_daily_account_runtime,
    load_daily_runtime_contract,
    validate_daily_account_runtime,
    write_daily_account_runtime,
)
from momentumbot.research.prospective_daily_source import (
    MicroTriggerDecision,
    build_daily_artifacts,
    build_profile_activations,
    build_scanner_runtime,
)
from momentumbot.research.prospective_market_input_capture import (
    build_market_input_capture,
    load_capture_contract,
)
from momentumbot.research.prospective_opportunity_freeze import (
    build_daily_opportunity_freeze,
    load_opportunity_freeze_contract,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "prospective-daily-account-runtime-v0.1.json"
)
OPPORTUNITY_CONTRACT = (
    ROOT / "research" / "strategy" / "prospective-opportunity-freeze-v0.1.json"
)
MARKET_CONTRACT = (
    ROOT / "research" / "strategy" / "prospective-market-input-capture-v0.1.json"
)
AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "prospective-daily-account-runtime-v0.1-registration-2026-08-22.json"
)
WORKFLOW = ROOT / ".github" / "workflows" / "prospective-daily-account-runtime.yml"


def _clock(start: datetime):
    values = iter(start + timedelta(seconds=offset) for offset in range(20))
    return lambda: next(values)


def _client(account_class: str, account_id: str, equity: str, buying_power: str):
    def request(url: str, **_kwargs: object) -> object:
        if url.endswith("/v2/account"):
            return {
                "id": account_id,
                "status": "ACTIVE",
                "currency": "USD",
                "equity": equity,
                "buying_power": buying_power,
                "cash": equity,
                "account_blocked": False,
                "trading_blocked": False,
                "transfers_blocked": False,
            }
        if url.endswith("/v2/positions") or "/v2/orders?" in url:
            return []
        raise AssertionError(f"unexpected URL: {url}")

    return AlpacaPaperAccountClient(
        AccountCredentials(
            account_class=account_class,
            api_key=f"{account_class}-synthetic-key",
            api_secret=f"{account_class}-synthetic-secret",
            expected_equity=Decimal("30000" if account_class == "main" else "2000"),
        ),
        request_json=request,
    )


def _account_bundle():
    clients = {
        "main": _client("main", "synthetic-provider-main", "30000", "120000"),
        "small": _client("small", "synthetic-provider-small", "2000", "4000"),
    }
    return capture_dual_account_bundle(
        clients,
        mode="capture",
        clock=_clock(datetime(2026, 8, 24, 9, 15, tzinfo=UTC)),
        requested_session_date=datetime(2026, 8, 24, tzinfo=UTC).date(),
        run_context={"workflow_run_id": "synthetic-rehearsal"},
    )


def _scanner_row(*, both_accounts: bool = True) -> dict[str, object]:
    return {
        "symbol": "TEST",
        "activation_time": "2026-08-24T11:00:00+00:00",
        "decision_time": "2026-08-24T11:00:00+00:00",
        "candidate_completed_bar_present": True,
        "price": 3.0,
        "percent_gain": 30.0 if both_accounts else 15.0,
        "exact_same_time_rvol": 6.0,
        "cumulative_volume": 1_000_000,
        "estimated_float_shares": 5_000_000,
        "has_provider_news_as_of": True,
        "top_gainer_rank": 1 if both_accounts else 4,
    }


def _source_bundle(*, include_trigger: bool, both_accounts: bool = True):
    rows = [_scanner_row(both_accounts=both_accounts)]
    scanner = build_scanner_runtime(
        trading_date="2026-08-24",
        prerequisite_content_sha256="d" * 64,
        scanner_rows=rows,
        scanner_lineage={"synthetic_market_inputs_sha256": "e" * 64},
    )
    activations, _ = build_profile_activations(
        scanner_runtime_content_sha256=scanner["content_sha256"],
        scanner_rows=rows,
    )
    triggers = []
    if include_trigger:
        activation = activations[0]
        triggers.append(
            MicroTriggerDecision(
                activation_id=activation.activation_id,
                plan_id="plan-synthetic-test",
                symbol="TEST",
                candidate_qualified_at=activation.candidate_qualified_at,
                decision_at="2026-08-24T11:00:21+00:00",
                micro_runtime_content_sha256="f" * 64,
                eligible_strategy_profile_ids=(
                    activation.eligible_strategy_profile_ids
                ),
                plan={
                    "symbol": "TEST",
                    "source_bar_start": "2026-08-24T11:00:10+00:00",
                    "armed_at": "2026-08-24T11:00:20+00:00",
                    "expires_at": "2026-08-24T11:00:30+00:00",
                    "breakout_level": 2.99,
                    "minimum_new_high_price": 3.0,
                    "stop_price": 2.90,
                    "pullback_number": 1,
                },
            )
        )
    return build_daily_artifacts(
        scanner_runtime=scanner,
        trigger_decisions=triggers,
    )


def _request_evidence(request_manifest: dict[str, object], quote_count: int, status_count: int):
    return {
        "requests": [
            {
                "request_id": row["request_id"],
                "dataset": row["dataset"],
                "schema": row["schema"],
                "metadata_matches": True,
                "request_completed": True,
                "record_count": quote_count if row["schema"] == "mbp-1" else status_count,
            }
            for row in request_manifest["requests"]
        ]
    }


def _parents(
    *,
    include_trigger: bool = True,
    status_known: bool = True,
    both_accounts: bool = True,
):
    daily = _source_bundle(
        include_trigger=include_trigger,
        both_accounts=both_accounts,
    )
    opportunity_contract = load_opportunity_freeze_contract(OPPORTUNITY_CONTRACT)
    market_contract = load_capture_contract(MARKET_CONTRACT)
    freeze = build_daily_opportunity_freeze(
        opportunity_contract,
        market_contract,
        daily.decision_source,
    )
    quote_records: list[dict[str, object]] = []
    status_records: list[dict[str, object]] = []
    if include_trigger:
        decision = freeze.opportunity_manifest["opportunities"][0]["decision_ts_ns"]
        quote_records = [
            {
                "symbol": "TEST",
                "ts_recv_ns": decision - 50_000_000,
                "sequence": 1,
                "bid_px_nanos": 2_990_000_000,
                "bid_size": 2_000,
                "ask_px_nanos": 3_000_000_000,
                "ask_size": 2_000,
            },
            {
                "symbol": "TEST",
                "ts_recv_ns": decision + 80_000_000,
                "sequence": 2,
                "bid_px_nanos": 2_990_000_000,
                "bid_size": 2_000,
                "ask_px_nanos": 3_000_000_000,
                "ask_size": 2_000,
            },
            {
                "symbol": "TEST",
                "ts_recv_ns": decision + 220_000_000,
                "sequence": 3,
                "bid_px_nanos": 3_000_000_000,
                "bid_size": 2_000,
                "ask_px_nanos": 3_010_000_000,
                "ask_size": 2_000,
            },
        ]
        status_records = [
            {
                "symbol": "TEST",
                "ts_recv_ns": decision - 1_000_000_000,
                "action": 7 if status_known else 0,
                "is_trading": "Y" if status_known else "~",
            }
        ]
    capture = build_market_input_capture(
        market_contract,
        freeze.opportunity_manifest,
        freeze.request_manifest,
        _request_evidence(
            freeze.request_manifest,
            quote_count=len(quote_records),
            status_count=len(status_records),
        ),
        quote_records,
        status_records,
    )
    account_manifest, snapshots = _account_bundle()
    return {
        "scanner_runtime": daily.scanner_runtime,
        "micro_runtime": daily.micro_runtime,
        "decision_source": daily.decision_source,
        "producer_manifest": daily.producer_manifest,
        "opportunity_freeze_contract": opportunity_contract,
        "market_input_contract": market_contract,
        "opportunity_manifest": freeze.opportunity_manifest,
        "request_manifest": freeze.request_manifest,
        "freeze_manifest": freeze.freeze_manifest,
        "market_input_capture": capture,
        "account_manifest": account_manifest,
        "account_snapshots": snapshots,
    }


def _runtime(
    *,
    include_trigger: bool = True,
    status_known: bool = True,
    both_accounts: bool = True,
):
    contract = load_daily_runtime_contract(CONTRACT)
    return build_daily_account_runtime(
        contract,
        **_parents(
            include_trigger=include_trigger,
            status_known=status_known,
            both_accounts=both_accounts,
        ),
        runtime_frozen_at="2026-08-24T15:00:00+00:00",
    )


class ProspectiveDailyAccountRuntimeTests(unittest.TestCase):
    def test_registration_audit_binds_the_inert_composer_surface(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        claimed = audit.pop("content_sha256")
        self.assertEqual(canonical_fingerprint(audit), claimed)
        self.assertEqual(audit["contract"]["content_sha256"], CONTRACT_CONTENT_SHA256)
        self.assertFalse(audit["execution_status"]["real_daily_runtime_created"])
        self.assertTrue(audit["mechanical_verification"]["synthetic_full_chain_rehearsed"])
        for row in audit["bound_files"]:
            raw = (ROOT / row["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), row["file_sha256"])

    def test_workflow_is_manual_parent_bound_and_credential_free(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        parsed = yaml.safe_load(text)
        self.assertIsInstance(parsed, dict)
        self.assertNotIn("schedule:", text)
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("actions: read", text)
        self.assertIn("contents: read", text)
        self.assertIn("Verify every named parent run and attempt", text)
        self.assertIn("Reverify provider-free mechanics before composition", text)
        self.assertNotIn("secrets.", text)
        for prohibited in (
            "DATABENTO_API_KEY",
            "ALPACA_MAIN_API_KEY",
            "ALPACA_SMALL_API_KEY",
            "ALPACA_API_SECRET",
        ):
            self.assertNotIn(prohibited, text)
        module = (
            ROOT
            / "src"
            / "momentumbot"
            / "research"
            / "prospective_daily_account_runtime.py"
        ).read_text(encoding="utf-8")
        for prohibited in (
            "credentials_from_env",
            "run_exact_acquisition",
            "get_json(",
            "providers.alpaca",
            "providers.databento",
        ):
            self.assertNotIn(prohibited, module)

    def test_contract_is_hash_bound_and_provider_free(self):
        contract = load_daily_runtime_contract(CONTRACT)
        self.assertEqual(contract["content_sha256"], CONTRACT_CONTENT_SHA256)
        self.assertEqual(contract["registered_cells"]["daily_session_record_count"], 12)
        self.assertEqual(contract["registered_cells"]["ten_date_session_record_count"], 120)
        self.assertFalse(contract["authority_boundary"]["provider_call_authorized"])
        self.assertFalse(contract["authority_boundary"]["paper_order_authorized"])
        self.assertEqual(
            contract["management_coverage"]["filled_position_representation"],
            "open_unresolved",
        )

    def test_full_synthetic_chain_emits_twelve_hash_bound_open_sessions(self):
        runtime = _runtime()
        validate_daily_account_runtime(runtime)
        self.assertEqual(runtime["session_count"], 12)
        self.assertEqual(runtime["decision_count"], 12)
        self.assertEqual(runtime["candidate_symbol_count"], 1)
        self.assertEqual(runtime["opportunity_count"], 1)
        self.assertEqual(
            canonical_fingerprint(
                {key: value for key, value in runtime.items() if key != "content_sha256"}
            ),
            runtime["content_sha256"],
        )
        self.assertTrue(all(row["entry_status"] == "filled" for row in runtime["decisions"]))
        self.assertTrue(all(row["exit_status"] == "open" for row in runtime["decisions"]))
        self.assertTrue(all(row["open_position_count"] == 1 for row in runtime["sessions"]))
        session_hashes = {
            (
                row["behavioral_horizon_seconds"],
                row["execution_scenario_id"],
                row["account"],
            ): row["runtime_content_sha256"]
            for row in runtime["sessions"]
        }
        for decision in runtime["decisions"]:
            key = (
                decision["behavioral_horizon_seconds"],
                decision["execution_scenario_id"],
                decision["account"],
            )
            self.assertEqual(decision["runtime_content_sha256"], session_hashes[key])
        rendered = json.dumps(runtime, sort_keys=True)
        for secret in (
            "main-synthetic-key",
            "main-synthetic-secret",
            "small-synthetic-key",
            "small-synthetic-secret",
            "synthetic-provider-main",
            "synthetic-provider-small",
        ):
            self.assertNotIn(secret, rendered)

    def test_scenarios_remain_separate_and_horizons_do_not_select(self):
        runtime = _runtime()
        prices: dict[tuple[str, str], set[float]] = {}
        for row in runtime["decisions"]:
            key = (row["execution_scenario_id"], row["account"])
            prices.setdefault(key, set()).add(row["first_entry_price"])
        self.assertEqual(prices[("l1-conservative-v0.1", "main_account")], {3.0})
        self.assertEqual(prices[("l1-stress-v0.1", "main_account")], {3.01})
        self.assertTrue(all(len(values) == 1 for values in prices.values()))
        self.assertFalse(runtime["best_cell_selected"])

    def test_unavailable_status_is_retained_without_fallback(self):
        runtime = _runtime(status_known=False)
        self.assertTrue(
            all(row["entry_status"] == "unavailable" for row in runtime["decisions"])
        )
        self.assertTrue(
            all(row["unavailable_input_count"] == 1 for row in runtime["sessions"])
        )
        self.assertTrue(all(row["open_position_count"] == 0 for row in runtime["sessions"]))
        rendered = json.dumps(runtime, sort_keys=True)
        self.assertNotIn("sip_print", rendered)

    def test_account_profile_difference_retains_unqualified_candidate(self):
        runtime = _runtime(both_accounts=False)
        main = [row for row in runtime["decisions"] if row["account"] == "main_account"]
        small = [row for row in runtime["decisions"] if row["account"] == "small_account"]
        self.assertTrue(all(row["account_qualified"] for row in main))
        self.assertTrue(all(row["entry_status"] == "filled" for row in main))
        self.assertTrue(all(not row["account_qualified"] for row in small))
        self.assertTrue(all(row["plan_count"] == 0 for row in small))
        self.assertTrue(all(row["entry_status"] == "not_submitted" for row in small))

    def test_zero_opportunity_date_still_emits_every_session_and_candidate(self):
        runtime = _runtime(include_trigger=False)
        self.assertEqual(runtime["opportunity_count"], 0)
        self.assertEqual(runtime["session_count"], 12)
        self.assertEqual(runtime["decision_count"], 12)
        self.assertTrue(all(row["plan_count"] == 0 for row in runtime["decisions"]))
        self.assertTrue(
            all(row["entry_status"] == "not_submitted" for row in runtime["decisions"])
        )
        self.assertTrue(all(row["open_position_count"] == 0 for row in runtime["sessions"]))

    def test_rehash_cannot_hide_session_or_retrospective_tampering(self):
        runtime = _runtime()
        changed = copy.deepcopy(runtime)
        changed["session_details"][0]["execution_attempts"][0]["reason"] = "changed"
        changed["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in changed.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "session detail content hash"):
            validate_daily_account_runtime(changed)

        changed = copy.deepcopy(runtime)
        changed["ross_action"] = "bought"
        changed["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in changed.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "retrospective label keys"):
            validate_daily_account_runtime(changed)

    def test_write_once_preserves_frozen_artifact(self):
        runtime = _runtime(include_trigger=False)
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "daily"
            output = write_daily_account_runtime(target, runtime)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), runtime)
            with self.assertRaises(FileExistsError):
                write_daily_account_runtime(target, runtime)

    def test_cli_materializes_exact_parent_directories_without_credentials(self):
        parents = _parents(include_trigger=False)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            freeze = root / "freeze"
            market = root / "market"
            account = root / "account"
            for directory in (source, freeze, market, account):
                directory.mkdir()
            files = {
                source / "scanner-runtime.json": parents["scanner_runtime"],
                source / "micro-trigger-runtime.json": parents["micro_runtime"],
                source / "prospective-daily-micro-decision-source.json": parents[
                    "decision_source"
                ],
                source / "producer-manifest.json": parents["producer_manifest"],
                freeze / "opportunity-manifest.json": parents["opportunity_manifest"],
                freeze / "request-manifest.json": parents["request_manifest"],
                freeze / "freeze-manifest.json": parents["freeze_manifest"],
                market / "market-input-capture.json": parents["market_input_capture"],
                account / "manifest.json": parents["account_manifest"],
                account / "main.json": parents["account_snapshots"]["main"],
                account / "small.json": parents["account_snapshots"]["small"],
            }
            for path, payload in files.items():
                path.write_text(
                    json.dumps(payload, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            output = root / "output"
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(ROOT / "src")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_prospective_daily_account_runtime.py"),
                    "--source-dir",
                    str(source),
                    "--freeze-dir",
                    str(freeze),
                    "--market-input-dir",
                    str(market),
                    "--account-dir",
                    str(account),
                    "--expected-trading-date",
                    "2026-08-24",
                    "--runtime-frozen-at",
                    "2026-08-24T15:00:00+00:00",
                    "--output-dir",
                    str(output),
                ],
                cwd=ROOT,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            summary = json.loads(completed.stdout)
            self.assertEqual(summary["session_count"], 12)
            self.assertFalse(summary["provider_call_made"])
            self.assertTrue((output / "daily-account-runtime.json").is_file())


if __name__ == "__main__":
    unittest.main()
