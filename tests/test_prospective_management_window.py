from __future__ import annotations

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

import pandas as pd
import yaml

from momentumbot.research.microstructure_contract import canonical_fingerprint
from momentumbot.research.prospective_management_window import (
    CONTRACT_CONTENT_SHA256,
    SIGNAL_WINDOW_NS,
    build_management_capture,
    build_management_projection,
    build_management_request_manifest,
    capture_management_window_from_alpaca,
    load_management_window_contract,
    validate_management_capture,
    validate_management_projection,
    write_management_capture_bundle,
)
from tests.test_prospective_daily_account_runtime import _parents, _runtime


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "prospective-management-window-capture-v0.1.json"
)
SCRIPT = ROOT / "scripts" / "run_prospective_management_window.py"
WORKFLOW = ROOT / ".github" / "workflows" / "prospective-management-window.yml"
AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "prospective-management-window-capture-v0.1-registration-2026-08-22.json"
)


def _frames(
    *,
    red: bool = True,
    include_trades: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    bars = pd.DataFrame(
        [
            {"open": 3.00, "close": 3.10},
            {"open": 3.20, "close": 3.10 if red else 3.25},
        ],
        index=pd.DatetimeIndex(
            [
                "2026-08-24T11:00:00+00:00",
                "2026-08-24T11:01:00+00:00",
            ],
            name="timestamp",
        ),
    )
    trade_rows = (
        [
            {
                "price": 3.25,
                "size": 100,
                "exchange": "V",
                "conditions": (),
                "trade_id": "target",
                "tape": "C",
            },
            {
                "price": 3.10,
                "size": 100,
                "exchange": "V",
                "conditions": (),
                "trade_id": "red-exit",
                "tape": "C",
            },
        ]
        if include_trades
        else []
    )
    timestamps = (
        pd.DatetimeIndex(
            [
                "2026-08-24T11:00:30+00:00",
                "2026-08-24T11:02:00.100000+00:00",
            ],
            name="timestamp",
        )
        if include_trades
        else pd.DatetimeIndex([], name="timestamp", tz="UTC")
    )
    trades = pd.DataFrame(
        trade_rows,
        index=timestamps,
        columns=["price", "size", "exchange", "conditions", "trade_id", "tape"],
    )
    return bars, trades


def _capture(
    *,
    red: bool = True,
    include_trades: bool = True,
    include_trigger: bool = True,
):
    parents = _parents(include_trigger=include_trigger)
    opportunity = parents["opportunity_manifest"]
    contract = load_management_window_contract(CONTRACT)
    manifest = build_management_request_manifest(contract, opportunity)
    results = {}
    if include_trigger:
        bars, trades = _frames(red=red, include_trades=include_trades)
        results[manifest["requests"][0]["request_id"]] = {
            "request_complete": True,
            "bars": bars,
            "trades": trades,
        }
    capture = build_management_capture(
        contract,
        opportunity,
        manifest,
        results,
        capture_frozen_at="2026-08-24T12:00:00+00:00",
        provider_call_made=include_trigger,
    )
    return contract, opportunity, manifest, capture


class ProspectiveManagementWindowTests(unittest.TestCase):
    def test_registration_audit_binds_the_unrun_capture_surface(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        claimed = audit.pop("content_sha256")
        self.assertEqual(canonical_fingerprint(audit), claimed)
        self.assertEqual(audit["contract"]["content_sha256"], CONTRACT_CONTENT_SHA256)
        self.assertFalse(audit["execution_status"]["real_capture_created"])
        self.assertTrue(
            audit["mechanical_verification"]["synthetic_capture_and_projection_rehearsed"]
        )
        for row in audit["bound_files"]:
            raw = (ROOT / row["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), row["file_sha256"])

    def test_workflow_is_date_bounded_first_attempt_and_immutably_pinned(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIsInstance(yaml.safe_load(text), dict)
        self.assertIn('cron: "0 23 24-28,31 8 *"', text)
        self.assertIn('cron: "0 23 1-4 9 *"', text)
        self.assertIn("a prior management capture workflow already attempted", text)
        self.assertIn("WORKFLOW_RUN_ATTEMPT", text)
        self.assertIn("actions: read", text)
        self.assertIn("contents: read", text)
        self.assertNotIn("actions: write", text)
        self.assertNotRegex(text, r"uses:\s+actions/[^@\s]+@v\d")
        self.assertIn("ALPACA_API_KEY", text)
        self.assertIn("ALPACA_API_SECRET", text)
        self.assertNotIn("ALPACA_MAIN_API_KEY", text)
        self.assertNotIn("ALPACA_SMALL_API_KEY", text)

    def test_contract_is_hash_bound_and_keeps_portfolio_ineligible(self):
        contract = load_management_window_contract(CONTRACT)
        self.assertEqual(contract["content_sha256"], CONTRACT_CONTENT_SHA256)
        self.assertEqual(
            contract["window_policy"][
                "management_signal_window_after_decision_seconds"
            ],
            900,
        )
        self.assertFalse(
            contract["management_projection"][
                "portfolio_financial_metrics_eligible"
            ]
        )
        self.assertFalse(contract["authority_boundary"]["paper_order_authorized"])

    def test_request_manifest_merges_fixed_symbol_window_without_provider_call(self):
        contract, opportunity, manifest, _capture_payload = _capture()
        decision = opportunity["opportunities"][0]["decision_ts_ns"]
        request = manifest["requests"][0]
        self.assertEqual(request["start_ns"], decision - decision % 60_000_000_000)
        self.assertEqual(
            request["end_ns"],
            decision + SIGNAL_WINDOW_NS + 60_000_000_000,
        )
        self.assertEqual(request["feed"], "sip")
        self.assertFalse(manifest["provider_call_made"])

    def test_capture_filters_unknown_conditions_and_retains_odd_lot_proxy(self):
        parents = _parents()
        opportunity = parents["opportunity_manifest"]
        contract = load_management_window_contract(CONTRACT)
        manifest = build_management_request_manifest(contract, opportunity)
        bars, trades = _frames()
        extras = pd.DataFrame(
            [
                {
                    "price": 3.15,
                    "size": 10,
                    "exchange": "V",
                    "conditions": ("I",),
                    "trade_id": "odd",
                    "tape": "C",
                },
                {
                    "price": 99.0,
                    "size": 1,
                    "exchange": "V",
                    "conditions": ("?",),
                    "trade_id": "unknown",
                    "tape": "C",
                },
            ],
            index=pd.DatetimeIndex(
                [
                    "2026-08-24T11:00:31+00:00",
                    "2026-08-24T11:00:32+00:00",
                ],
                name="timestamp",
            ),
        )
        trades = pd.concat([trades.iloc[:1], extras, trades.iloc[1:]]).sort_index(
            kind="stable"
        )
        capture = build_management_capture(
            contract,
            opportunity,
            manifest,
            {
                manifest["requests"][0]["request_id"]: {
                    "request_complete": True,
                    "bars": bars,
                    "trades": trades,
                }
            },
            capture_frozen_at="2026-08-24T12:00:00+00:00",
            provider_call_made=True,
        )
        path = capture["paths"][0]
        self.assertEqual(path["raw_trade_count"], 4)
        self.assertEqual(path["eligible_trade_count"], 3)
        self.assertEqual(
            [row["trade_id"] for row in path["eligible_trades"]],
            ["target", "odd", "red-exit"],
        )
        self.assertTrue(path["eligible_trades"][1]["execution_via_odd_lot"])
        validate_management_capture(capture)

    def test_projection_resolves_descriptive_exits_but_leaves_ledger_open(self):
        contract, _opportunity, _manifest, capture = _capture()
        projection = build_management_projection(
            contract,
            _runtime(),
            capture,
            projection_frozen_at="2026-08-24T12:01:00+00:00",
        )
        validate_management_projection(projection)
        self.assertEqual(projection["cell_count"], 12)
        self.assertEqual(projection["decision_count"], 12)
        self.assertTrue(
            all(row["exit_status"] == "closed" for row in projection["decisions"])
        )
        self.assertTrue(
            all(row["open_position_count"] == 1 for row in projection["sessions"])
        )
        self.assertFalse(projection["parent_ledger_mutated"])
        self.assertFalse(projection["portfolio_financial_metrics_eligible"])
        first_prices = {
            (row["execution_scenario_id"], row["first_exit_price"])
            for row in projection["decisions"]
        }
        self.assertEqual(
            first_prices,
            {
                ("l1-conservative-v0.1", 3.2),
                ("l1-stress-v0.1", 3.23),
            },
        )
        outcomes = [
            row["outcome"]
            for cell in projection["cells"]
            for row in cell["management_outcomes"]
        ]
        self.assertTrue(all(len(outcome["legs"]) == 2 for outcome in outcomes))
        self.assertTrue(
            all(
                outcome["execution_evidence"]
                == "sip_transaction_proxy_not_broker_fill"
                for outcome in outcomes
            )
        )

    def test_incomplete_path_is_unavailable_and_never_liquidated(self):
        contract, _opportunity, _manifest, capture = _capture(include_trades=False)
        projection = build_management_projection(
            contract,
            _runtime(),
            capture,
            projection_frozen_at="2026-08-24T12:01:00+00:00",
        )
        self.assertTrue(
            all(row["exit_status"] == "unavailable" for row in projection["decisions"])
        )
        self.assertTrue(
            all(row["unavailable_input_count"] == 1 for row in projection["sessions"])
        )
        self.assertFalse(projection["sell_fees_or_realized_pnl_computed"])

    def test_zero_opportunity_date_makes_no_provider_call(self):
        parents = _parents(include_trigger=False)
        contract = load_management_window_contract(CONTRACT)

        class NoCallClient:
            def bars(self, *_args: object, **_kwargs: object) -> object:
                raise AssertionError("zero opportunity date cannot call Alpaca")

        manifest, capture = capture_management_window_from_alpaca(
            contract,
            parents["opportunity_manifest"],
            client=NoCallClient(),  # type: ignore[arg-type]
            clock=lambda: datetime(2026, 8, 24, 12, tzinfo=UTC),
            trade_loader=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("zero opportunity date cannot load trades")
            ),
        )
        self.assertEqual(manifest["trading_date"], "2026-08-24")
        self.assertEqual(manifest["request_count"], 0)
        self.assertEqual(capture["opportunity_count"], 0)
        self.assertFalse(capture["provider_call_made"])

    def test_provider_capture_uses_exact_sip_raw_asof_requests(self):
        parents = _parents()
        contract = load_management_window_contract(CONTRACT)
        calls: list[tuple[str, dict[str, object]]] = []
        bars, trades = _frames()

        class FakeClient:
            def bars(self, symbols: list[str], **kwargs: object):
                calls.append(("bars", {"symbols": symbols, **kwargs}))
                return {"TEST": bars}

        def load_trades(_client: object, symbol: str, **kwargs: object):
            calls.append(("trades", {"symbol": symbol, **kwargs}))
            return trades

        manifest, capture = capture_management_window_from_alpaca(
            contract,
            parents["opportunity_manifest"],
            client=FakeClient(),  # type: ignore[arg-type]
            clock=lambda: datetime(2026, 8, 24, 12, tzinfo=UTC),
            trade_loader=load_trades,
        )
        self.assertEqual([name for name, _kwargs in calls], ["bars", "trades"])
        self.assertEqual(calls[0][1]["feed"], "sip")
        self.assertEqual(calls[0][1]["adjustment"], "raw")
        self.assertEqual(calls[0][1]["asof"], "2026-08-24")
        self.assertEqual(calls[1][1]["feed"], "sip")
        self.assertEqual(capture["request_count"], manifest["request_count"])

    def test_hash_and_write_once_guards_reject_tampering(self):
        _contract, _opportunity, manifest, capture = _capture()
        changed = copy.deepcopy(capture)
        changed["paths"][0]["eligible_trades"][0]["price"] = 99.0
        with self.assertRaisesRegex(ValueError, "content hash"):
            validate_management_capture(changed)
        relabeled = copy.deepcopy(capture)
        relabeled["provider_call_made"] = False
        relabeled["content_sha256"] = canonical_fingerprint(
            {
                key: value
                for key, value in relabeled.items()
                if key != "content_sha256"
            }
        )
        with self.assertRaisesRegex(ValueError, "provider-call status"):
            validate_management_capture(relabeled)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "capture"
            write_management_capture_bundle(output, manifest, capture)
            with self.assertRaises(FileExistsError):
                write_management_capture_bundle(output, manifest, capture)

    def test_projection_rejects_rehashed_cell_that_differs_from_flattened_rows(self):
        contract, _opportunity, _manifest, capture = _capture()
        projection = build_management_projection(
            contract,
            _runtime(),
            capture,
            projection_frozen_at="2026-08-24T12:01:00+00:00",
        )
        changed = copy.deepcopy(projection)
        cell = changed["cells"][0]
        cell["candidate_decisions"][0]["plan_count"] += 1
        cell["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in cell.items() if key != "content_sha256"}
        )
        changed["content_sha256"] = canonical_fingerprint(
            {
                key: value
                for key, value in changed.items()
                if key != "content_sha256"
            }
        )
        with self.assertRaisesRegex(ValueError, "flattened management decisions"):
            validate_management_projection(changed)

    def test_manifest_cli_is_provider_free(self):
        parents = _parents(include_trigger=False)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            opportunity = root / "opportunity.json"
            opportunity.write_text(
                json.dumps(parents["opportunity_manifest"]), encoding="utf-8"
            )
            output = root / "output"
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(ROOT / "src")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "manifest",
                    "--opportunity-manifest",
                    str(opportunity),
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
            self.assertEqual(summary["request_count"], 0)
            self.assertFalse(summary["provider_call_made"])


if __name__ == "__main__":
    unittest.main()
