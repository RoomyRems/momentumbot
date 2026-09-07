from __future__ import annotations

import copy
from dataclasses import replace
from datetime import date
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
import yaml

from momentumbot.research import sealed_historical_management_fill_feedback_v01 as m
from momentumbot.research.campaign_portfolio import AccountClass, CampaignPortfolioLedger, EntryFill, EntryRole, PlanEmission
from tests.test_sealed_historical_management_projection_v01 import trade as old_trade, bar as old_bar

ROOT = Path(__file__).resolve().parents[1]
BASE = int(pd.Timestamp("2025-05-30T13:00:00Z").value)
SECOND = 1_000_000_000


def reseal(value):
    return m.seal({k: v for k, v in value.items() if k != "content_sha256"})


def fixture(quantity=10, *, scenario="l1-conservative-v0.1", target_fill=None, final_fill=None, account="main_account"):
    policy, _ = m.SCENARIOS[scenario]
    profile = "current-general-2026" if account == "main_account" else "current-small-account-2026"
    plan = {"symbol": "SYNTHETIC", "source_bar_start": pd.Timestamp(BASE - 10 * SECOND, tz="UTC").isoformat(),
        "armed_at": pd.Timestamp(BASE, tz="UTC").isoformat(), "expires_at": pd.Timestamp(BASE + 10 * SECOND, tz="UTC").isoformat(),
        "breakout_level": 9.98, "minimum_new_high_price": 9.99, "stop_price": 9.0, "pullback_number": 1}
    decision = {"activation_id": "synthetic-activation", "symbol": "SYNTHETIC", "plan": plan,
        "candidate_qualified_at": pd.Timestamp(BASE - 60 * SECOND, tz="UTC").isoformat(),
        "decision_at": pd.Timestamp(BASE, tz="UTC").isoformat(), "micro_runtime_content_sha256": "a" * 64,
        "eligible_strategy_profile_ids": [profile]}
    decision["plan_id"] = "plan-" + m.canonical_fingerprint({"activation_id": decision["activation_id"], "plan": plan})
    day = m.seal({"trading_date": "2025-05-30", "decisions": [decision]})
    op = m.accounts.availability.plan._opportunities(day)[0]
    window = {"opportunity": op, "start_ns": BASE, "signal_end_ns": BASE + 900 * SECOND, "end_ns": BASE + 960 * SECOND,
        "availability_content_sha256": "b" * 64, "entry_input_status": "available", "entry_input_reason": "synthetic_available"}
    source_plan = json.loads((ROOT / m.parent.ACCOUNT_PLAN).read_text())
    path_id = m.accounts._path_id(account, 1, scenario)
    slot = copy.deepcopy(next(p for p in source_plan["paths"] if p["path_id"] == path_id)["sessions"][0])
    slot["opportunity_inputs"] = [{"opportunity_id": op["opportunity_id"], "availability_content_sha256": "b" * 64,
        "input_status": "available", "reason": "synthetic_available"}]
    slot["unavailable_opportunity_count"] = 0
    slot = reseal(slot)
    seed = next(s for s in m.accounts.seeds()["seeds"] if s["account_key"] == account)
    kind = AccountClass.MAIN if account == "main_account" else AccountClass.SMALL
    ledger = CampaignPortfolioLedger(date(2025, 5, 30), m.materialize_account_constraints(m.paper_account_policy(kind),
        account_id=seed["account_id"], starting_equity=float(seed["equity_usd"]), starting_buying_power=float(seed["buying_power_usd"])))
    request = {"request_id": "2025-05-30-SYNTHETIC-mbp-1", "trading_date": "2025-05-30", "dataset": "XNAS.ITCH",
        "schema": "mbp-1", "symbols": ["SYNTHETIC"], "stype_in": "raw_symbol", "start_ns": BASE - 100_000_000,
        "end_ns": window["end_ns"], "end_exclusive": True}
    status_request = {**request, "request_id": "2025-05-30-SYNTHETIC-status", "schema": "status",
        "start_ns": int(pd.Timestamp("2025-05-30", tz="UTC").value)}
    target_fill = quantity // 2 if target_fill is None else target_fill
    final_fill = quantity - target_fill if final_fill is None else final_fill
    raw = []
    def quote(at, bid, ask, shares, entry=False):
        # A positive displayed lot can still round to zero after participation.
        # Literal zero makes the frozen capture quote unavailable instead.
        size = max(1, int(m.Decimal(shares) / policy.displayed_size_participation))
        raw.append({"symbol": "SYNTHETIC", "ts_recv_ns": BASE + at, "sequence": len(raw),
            "bid_px_nanos": int(m.Decimal(str(bid)) * 1_000_000_000), "bid_size": 2000 if entry else size,
            "ask_px_nanos": int(m.Decimal(str(ask)) * 1_000_000_000), "ask_size": size if entry else 2000})
    near_arrival = policy.decision_to_arrival_ms * 1_000_000 - 10_000_000
    for at in (-1, near_arrival):
        quote(at, 9.99, 10, quantity, True)
    for at in (SECOND - 1, SECOND + near_arrival):
        quote(at, 12, 12.01, target_fill)
    for at in (2 * SECOND - 1, 2 * SECOND + near_arrival):
        quote(at, 9, 9.01, final_fill)
    source_sha = m.canonical_fingerprint(request)
    records = [{**r, "source_request_sha256": source_sha, "source_record_index": i} for i, r in enumerate(raw)]
    tape = {"quote_request": request, "quote_records": records, "status_request": status_request,
        "status_records": [{"symbol": "SYNTHETIC", "ts_recv_ns": request["start_ns"] - 1, "action": 7, "is_trading": "Y"}]}
    args = {"window": window, "slot": slot, "source_decision": decision, "pre_entry_ledger": ledger,
        "expected_pre_ledger_sha256": m.canonical_fingerprint(ledger.runtime_artifact()), "tape": tape,
        "expected_tape_sha256": m.canonical_fingerprint(tape)}
    args["expected_context_sha256"] = m.canonical_fingerprint({k: args[k] for k in ("window", "slot", "source_decision")})
    return args


def repin_context(args):
    args["expected_context_sha256"] = m.canonical_fingerprint({k: args[k] for k in ("window", "slot", "source_decision")})


def record(offset, price, ordinal=0, conditions=None):
    raw = old_trade(0, price, conditions)
    raw["t"] = pd.Timestamp(BASE + offset, tz="UTC").isoformat()
    return {"record": raw, "timestamp_ns": BASE + offset, "composed_record_ordinal": ordinal,
        "source_artifact_id": 123, "source_request_id": "synthetic-trades", "source_record_ordinal": ordinal + 10}


def minute_bar(minute=0, red=True, ordinal=0):
    raw = old_bar(0, 11 if red else 10, 10 if red else 11)
    raw["t"] = pd.Timestamp(BASE + minute * 60 * SECOND, tz="UTC").isoformat()
    return {"record": raw, "timestamp_ns": BASE + minute * 60 * SECOND, "composed_record_ordinal": ordinal,
        "source_artifact_id": 124, "source_request_id": "synthetic-bars", "source_record_ordinal": ordinal + 20}


def submit(engine, args, intent):
    return engine.submit_intent(intent, tape=args["tape"], expected_tape_sha256=args["expected_tape_sha256"])


class FillFeedbackTests(unittest.TestCase):
    def test_registration_pins_completed_parent_and_closed_historical_boundary(self):
        report = m.validate_registration(ROOT)
        self.assertTrue(report["verification_passed"])
        contract = m.expected_contract(ROOT)
        self.assertEqual(contract["parent_commit_sha"], "75cacb70c9fc6fcc1465b5a3f65d991bad0b45bb")
        self.assertIsNone(contract["historical_entry_producer"])
        for key, expected in m.BOUNDARY.items():
            self.assertEqual(contract[key], expected)

    def test_exact_population_dates_availability_and_all_path_references(self):
        data = {n: json.loads(v) for n, v in m.build_bundle(ROOT).items()}
        requirements = data["entry-binding-requirements.json"]
        original = m.frozen(ROOT / m.parent.OUTPUT_PATH / "projection-input-requirements.json")
        self.assertEqual(requirements["opportunity_windows_content_sha256"], m.canonical_fingerprint(original["opportunity_windows"]))
        self.assertEqual(requirements["dates_content_sha256"], m.canonical_fingerprint(original["dates"]))
        paths = m.frozen(ROOT / m.parent.ACCOUNT_PLAN)
        refs = [{"path_id": p["path_id"], "session_id": s["session_id"], "session_input_content_sha256": s["content_sha256"],
            "opportunity_inputs": s["opportunity_inputs"]} for p in paths["paths"] for s in p["sessions"]]
        self.assertEqual(requirements["session_references_content_sha256"], m.canonical_fingerprint(refs))
        self.assertEqual(requirements["account_session_plan_content_sha256"], paths["content_sha256"])
        self.assertEqual(len(refs), 360)
        self.assertEqual(sum(len(s["opportunity_inputs"]) for s in refs), 744)
        self.assertEqual(sum(r["input_status"] == "unavailable" for s in refs for r in s["opportunity_inputs"]), 162)
        self.assertEqual(len({s["path_id"] for s in refs}), 12)

    def test_metadata_build_never_opens_tapes_or_executes_entries(self):
        with patch.object(m, "bind_entry_evidence", side_effect=AssertionError("no runtime")), patch.object(m.parent.inputs, "ManagementInputBundle", side_effect=AssertionError("no source tape")):
            self.assertEqual(len(m.build_bundle(ROOT)), 4)

    def test_parent_mutation_is_rejected_even_if_child_would_be_rehashed(self):
        original = m.file_sha
        with patch.object(m, "file_sha", side_effect=lambda p: "0" * 64 if str(p).endswith(m.parent.MODULE_PATH) else original(p)):
            with self.assertRaisesRegex(ValueError, "parent differs"):
                m.validate_registration(ROOT)

    def test_implementation_mutation_invalidates_registration(self):
        original = m.file_sha
        with patch.object(m, "file_sha", side_effect=lambda p: "0" * 64 if str(p).endswith(m.MODULE_PATH) else original(p)):
            with self.assertRaisesRegex(ValueError, "registration differs"):
                m.validate_registration(ROOT)

    def test_write_once_and_rehashed_metadata_cannot_pass_reconstruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            self.assertTrue(m.write_bundle(ROOT, out)["verification_passed"])
            with self.assertRaises(FileExistsError):
                m.write_bundle(ROOT, out)
            p = out / "readiness-report.json"
            d = json.loads(p.read_text()); d["historical_entry_producer_registered"] = True
            p.write_bytes(m.accounts._bytes(reseal(d)))
            with self.assertRaisesRegex(ValueError, "reconstruction differs"):
                m.verify_bundle(ROOT, out)

    def test_wrong_output_symlink_and_extra_inventory_fail(self):
        with self.assertRaises(ValueError):
            m.write_bundle(ROOT, ROOT / "research/strategy/wrong")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"; m.write_bundle(ROOT, out)
            (Path(tmp) / "link").symlink_to(out)
            with self.assertRaises(ValueError):
                m.verify_bundle(ROOT, Path(tmp) / "link")
            (out / "extra.txt").write_text("extra")
            with self.assertRaisesRegex(ValueError, "inventory differs"):
                m.verify_bundle(ROOT, out)

    def test_cli_verifies_offline_and_exposes_no_runtime_mode(self):
        for option in ("--validate-registration", "--verify"):
            result = subprocess.run([sys.executable, str(ROOT / m.SCRIPT_PATH), option], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["verification_passed"])
        result = subprocess.run([sys.executable, str(ROOT / m.SCRIPT_PATH), "--run"], cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)

    def test_workflow_is_read_only_pinned_without_provider_credentials(self):
        text = (ROOT / m.WORKFLOW_PATH).read_text()
        data = yaml.safe_load(text)
        self.assertEqual(data["permissions"], {"contents": "read"})
        self.assertFalse(data["concurrency"]["cancel-in-progress"])
        self.assertNotIn("secrets.", text)
        self.assertNotIn("workflow_dispatch", text)
        self.assertIn("--require-hashes", text)
        self.assertIn("python -O -m unittest", text)

    def test_binding_recomputes_positive_fill_exact_event_and_does_not_mutate_ledger(self):
        args = fixture()
        before = args["pre_entry_ledger"].runtime_artifact()
        bound = m.bind_entry_evidence(**args)
        self.assertEqual(bound["quantity"], 10)
        self.assertEqual(bound["accepted_ledger_event"]["quantity"], 10)
        self.assertEqual(bound["execution"]["filled_quantity"], 10)
        self.assertEqual(bound["fill_quote_source"]["source_record_index"], 1)
        self.assertEqual(args["pre_entry_ledger"].runtime_artifact(), before)
        self.assertFalse(bound["historical_producer_authenticated"])
        self.assertFalse(bound["historical_runtime_authorized"])

    def test_all_caller_evidence_pins_are_required(self):
        for field in ("expected_context_sha256", "expected_pre_ledger_sha256", "expected_tape_sha256"):
            args = fixture(); args[field] = "0" * 64
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "caller pin"):
                m.bind_entry_evidence(**args)

    def test_unavailable_entry_never_promoted_by_management_data(self):
        args = fixture(); args["window"]["entry_input_status"] = "unavailable"; repin_context(args)
        with self.assertRaisesRegex(ValueError, "unavailable opportunity"):
            m.bind_entry_evidence(**args)

    def test_cross_profile_or_session_slot_substitution_rejected(self):
        for field, value in (("profile_id", "current-small-account-2026"), ("trading_date", "2025-06-02"), ("execution_scenario_id", "not-registered")):
            args = fixture(); args["slot"][field] = value; args["slot"] = reseal(args["slot"]); repin_context(args)
            with self.subTest(field=field), self.assertRaises(ValueError):
                m.bind_entry_evidence(**args)

    def test_availability_reference_and_reason_must_match(self):
        for key, value in (("availability_content_sha256", "c" * 64), ("reason", "different"), ("input_status", "unavailable")):
            args = fixture(); args["slot"]["opportunity_inputs"][0][key] = value; args["slot"] = reseal(args["slot"]); repin_context(args)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "availability"):
                m.bind_entry_evidence(**args)

    def test_original_stop_and_decision_cannot_be_replaced(self):
        args = fixture(); args["source_decision"]["plan"]["stop_price"] = 8.0; repin_context(args)
        with self.assertRaisesRegex(ValueError, "original decision"):
            m.bind_entry_evidence(**args)

    def test_risk_limits_and_initial_seed_are_not_caller_options(self):
        for update in ({"max_total_open_risk": 750.0}, {"account_id": "other-account"}):
            args = fixture(); ledger = args["pre_entry_ledger"]
            ledger.constraints = replace(ledger.constraints, **update)
            args["expected_pre_ledger_sha256"] = m.canonical_fingerprint(ledger.runtime_artifact())
            with self.subTest(update=update), self.assertRaises(ValueError):
                m.bind_entry_evidence(**args)

    def test_locked_account_cannot_create_accepted_binding(self):
        args = fixture(); args["pre_entry_ledger"].locked = True
        args["expected_pre_ledger_sha256"] = m.canonical_fingerprint(args["pre_entry_ledger"].runtime_artifact())
        with self.assertRaisesRegex(ValueError, "rejected by frozen ledger"):
            m.bind_entry_evidence(**args)

    def test_second_entry_or_add_campaign_is_explicitly_unsupported(self):
        args = fixture(); ledger = args["pre_entry_ledger"]; op = args["window"]["opportunity"]
        ledger.record_plan_emission(PlanEmission(op["activation_id"], op["plan_id"], op["symbol"], pd.Timestamp(BASE - SECOND, tz="UTC")))
        ledger.apply_entry_fill(EntryFill("prior-fill", op["activation_id"], op["plan_id"], op["symbol"], pd.Timestamp(BASE - 1, tz="UTC"), 1, 10.0, 10.0, 9.0, EntryRole.STARTER, True))
        args["expected_pre_ledger_sha256"] = m.canonical_fingerprint(ledger.runtime_artifact())
        with self.assertRaisesRegex(ValueError, "multiple-entry"):
            m.bind_entry_evidence(**args)

    def test_zero_liquidity_does_not_become_an_entry_receipt(self):
        args = fixture(0)
        with self.assertRaisesRegex(ValueError, "positive fill"):
            m.bind_entry_evidence(**args)

    def test_unknown_status_or_missing_quote_is_not_inferred(self):
        for mutate in (lambda a: a["tape"]["status_records"][0].update(is_trading="~"), lambda a: a["tape"].update(quote_records=[])):
            args = fixture(); mutate(args); args["expected_tape_sha256"] = m.canonical_fingerprint(args["tape"])
            with self.assertRaises(ValueError):
                m.bind_entry_evidence(**args)

    def test_whole_share_rounding_and_one_share_target_behavior(self):
        for quantity in (1, 2, 3, 11):
            args = fixture(quantity); engine = m.ManagementFillFeedback(**args)
            intent = engine.observe_trade(record(SECOND, 12))
            with self.subTest(quantity=quantity):
                self.assertEqual(engine.snapshot()["target_quantity"], quantity // 2)
                if quantity == 1:
                    self.assertIsNone(intent)
                    self.assertFalse(engine.snapshot()["breakeven_active"])
                else:
                    self.assertEqual(intent["quantity"], quantity // 2)

    def test_touch_and_pending_execution_do_not_activate_breakeven(self):
        args = fixture(); engine = m.ManagementFillFeedback(**args)
        intent = engine.observe_trade(record(SECOND, 12)); submit(engine, args, intent)
        state = engine.settle(BASE + SECOND + 50_000_000)
        self.assertEqual(state["remaining_quantity"], 10)
        self.assertEqual(state["reserved_sell_quantity"], 5)
        self.assertFalse(state["breakeven_active"])
        self.assertEqual(state["fills"], [])
        self.assertNotIn("fill_price", state["events"][-1]["order"])

    def test_full_target_fill_moves_stop_only_at_known_fill_time(self):
        args = fixture(); engine = m.ManagementFillFeedback(**args)
        order = submit(engine, args, engine.observe_trade(record(SECOND, 12)))
        state = engine.settle(order["arrival_ts_ns"])
        self.assertEqual(state["remaining_quantity"], 5)
        self.assertTrue(state["breakeven_active"])
        self.assertEqual(state["active_stop_price"], 10.0)
        self.assertTrue(state["pending_order"])
        self.assertEqual(state["reserved_sell_quantity"], 0)
        state = engine.settle(order["cancel_ack_ts_ns"])
        self.assertFalse(state["pending_order"])

    def test_partial_target_keeps_stop_and_reserves_unfilled_tranche_until_ack(self):
        args = fixture(target_fill=2); engine = m.ManagementFillFeedback(**args)
        order = submit(engine, args, engine.observe_trade(record(SECOND, 12)))
        state = engine.settle(order["arrival_ts_ns"])
        self.assertEqual((state["remaining_quantity"], state["target_filled_quantity"], state["reserved_sell_quantity"]), (8, 2, 3))
        self.assertEqual(state["active_stop_price"], 9.0)
        self.assertFalse(state["breakeven_active"])
        state = engine.settle(order["cancel_ack_ts_ns"])
        self.assertEqual(state["reserved_sell_quantity"], 0)
        self.assertIsNone(engine.observe_trade(record(2 * SECOND, 12, 1)))

    def test_zero_target_fill_does_not_move_stop_or_reduce_position(self):
        args = fixture(target_fill=0); engine = m.ManagementFillFeedback(**args)
        order = submit(engine, args, engine.observe_trade(record(SECOND, 12)))
        state = engine.settle(order["cancel_ack_ts_ns"])
        self.assertEqual(state["remaining_quantity"], 10)
        self.assertFalse(state["breakeven_active"])
        self.assertEqual(state["fills"], [])

    def test_target_then_terminal_fills_close_exact_shares_at_quote_prices(self):
        for scenario in m.SCENARIOS:
            args = fixture(scenario=scenario); engine = m.ManagementFillFeedback(**args)
            first = submit(engine, args, engine.observe_trade(record(SECOND, 12)))
            engine.settle(first["cancel_ack_ts_ns"])
            intent = engine.observe_trade(record(2 * SECOND, 9, 1))
            self.assertEqual((intent["reason"], intent["quantity"]), ("breakeven_stop", 5))
            final = submit(engine, args, intent)
            state = engine.settle(final["cancel_ack_ts_ns"])
            self.assertEqual(state["status"], "closed_confirmed_shares")
            self.assertEqual([f["quantity"] for f in state["fills"]], [5, 5])
            self.assertEqual([m.Decimal(f["fill_price"]) for f in state["fills"]], [m.Decimal(12), m.Decimal(9)])
            self.assertFalse(state["account_position_closed"])
            self.assertFalse(state["financial_metrics_eligible"])

    def test_partial_final_exit_remains_open_unresolved_without_automatic_retry(self):
        args = fixture(target_fill=2, final_fill=3); engine = m.ManagementFillFeedback(**args)
        first = submit(engine, args, engine.observe_trade(record(SECOND, 12))); engine.settle(first["cancel_ack_ts_ns"])
        final = submit(engine, args, engine.observe_trade(record(2 * SECOND, 8, 1))); state = engine.settle(final["cancel_ack_ts_ns"])
        self.assertEqual(state["status"], "open_unresolved_exit_remainder")
        self.assertEqual((state["sold_quantity"], state["remaining_quantity"]), (5, 5))
        self.assertIsNone(engine.observe_trade(record(3 * SECOND, 7, 2)))

    def test_zero_final_fill_remains_open(self):
        args = fixture(final_fill=0); engine = m.ManagementFillFeedback(**args)
        order = submit(engine, args, engine.observe_trade(record(2 * SECOND, 8)))
        state = engine.settle(order["cancel_ack_ts_ns"])
        self.assertEqual(state["remaining_quantity"], 10)
        self.assertEqual(state["status"], "open_unresolved_exit_remainder")

    def test_competing_stop_during_target_is_latched_without_overselling(self):
        args = fixture(); engine = m.ManagementFillFeedback(**args)
        first = submit(engine, args, engine.observe_trade(record(SECOND, 12)))
        self.assertIsNone(engine.observe_trade(record(SECOND + 20_000_000, 8, 1)))
        self.assertEqual(engine.snapshot()["latched_full_exit"], "initial_stop")
        engine.settle(first["cancel_ack_ts_ns"])
        intent = engine.observe_trade(record(2 * SECOND, 11, 2))
        self.assertEqual((intent["reason"], intent["quantity"]), ("initial_stop", 5))

    def test_equal_time_print_precedes_fill_feedback(self):
        args = fixture(); engine = m.ManagementFillFeedback(**args)
        first = submit(engine, args, engine.observe_trade(record(SECOND, 12)))
        engine.observe_trade(record(first["arrival_ts_ns"] - BASE, 9.5, 1))
        self.assertFalse(engine.snapshot()["breakeven_active"])
        self.assertIsNone(engine.snapshot()["latched_full_exit"])
        engine.settle(first["arrival_ts_ns"])
        self.assertTrue(engine.snapshot()["breakeven_active"])
        with self.assertRaisesRegex(ValueError, "equal-time"):
            engine.observe_trade(record(first["arrival_ts_ns"] - BASE, 9.5, 2))

    def test_entry_timestamp_prints_are_excluded(self):
        engine = m.ManagementFillFeedback(**fixture())
        at = engine.snapshot()["entry"]["fill_time_ns"] - BASE
        self.assertIsNone(engine.observe_trade(record(at, 8)))
        self.assertIsNone(engine.observe_trade(record(at, 12, 1)))
        self.assertEqual(engine.snapshot()["remaining_quantity"], 10)

    def test_source_conditions_unknown_codes_and_clean_odd_lots(self):
        engine = m.ManagementFillFeedback(**fixture())
        self.assertIsNone(engine.observe_trade(record(SECOND, 8, 0, ["UNKNOWN"])))
        self.assertIsNone(engine.observe_trade(record(SECOND + 1, 8, 1, ["I", "Z"])))
        self.assertEqual(engine.observe_trade(record(SECOND + 2, 8, 2, ["I"]))["reason"], "initial_stop")

    def test_completed_red_bar_needs_a_subsequent_eligible_print(self):
        engine = m.ManagementFillFeedback(**fixture())
        engine.observe_bar(minute_bar())
        self.assertFalse(engine.snapshot()["pending_order"])
        intent = engine.observe_trade(record(60 * SECOND, 12))
        self.assertEqual(intent["reason"], "first_red_candle")
        self.assertEqual(intent["red_signal"]["signal_ts_ns"], BASE + 60 * SECOND)
        self.assertEqual(intent["quantity"], 10)

    def test_stop_has_priority_over_completed_red_and_target(self):
        engine = m.ManagementFillFeedback(**fixture())
        engine.observe_bar(minute_bar())
        self.assertEqual(engine.observe_trade(record(60 * SECOND, 8))["reason"], "initial_stop")

    def test_late_bar_cannot_create_signal_after_frozen_signal_window(self):
        engine = m.ManagementFillFeedback(**fixture())
        engine.observe_bar(minute_bar(minute=15))
        self.assertIsNone(engine.observe_trade(record(930 * SECOND, 10)))

    def test_no_end_of_window_liquidation(self):
        engine = m.ManagementFillFeedback(**fixture())
        state = engine.settle(BASE + 960 * SECOND - 1)
        self.assertEqual(state["remaining_quantity"], 10)
        self.assertEqual(state["fills"], [])
        with self.assertRaises(ValueError):
            engine.settle(BASE + 960 * SECOND)

    def test_exit_capture_tail_cannot_extend_original_window(self):
        args = fixture(); engine = m.ManagementFillFeedback(**args)
        intent = engine.observe_trade(record(960 * SECOND - 100_000_000, 8))
        before = engine.snapshot()
        with self.assertRaisesRegex(ValueError, "outside original"):
            submit(engine, args, intent)
        self.assertEqual(engine.snapshot(), before)

    def test_outstanding_intent_cannot_use_later_data_at_earlier_clock(self):
        engine = m.ManagementFillFeedback(**fixture()); engine.observe_trade(record(SECOND, 12))
        before = engine.snapshot()
        with self.assertRaisesRegex(ValueError, "outstanding intent"):
            engine.observe_trade(record(SECOND + 1, 8, 1))
        self.assertEqual(engine.snapshot(), before)

    def test_changed_intent_or_duplicate_submission_is_rejected(self):
        args = fixture(); engine = m.ManagementFillFeedback(**args)
        intent = engine.observe_trade(record(SECOND, 12)); changed = copy.deepcopy(intent); changed["quantity"] += 1
        with self.assertRaisesRegex(ValueError, "exact outstanding"):
            submit(engine, args, changed)
        submit(engine, args, intent)
        with self.assertRaisesRegex(ValueError, "exact outstanding"):
            submit(engine, args, intent)

    def test_common_tape_cannot_change_between_exit_attempts(self):
        args = fixture(); engine = m.ManagementFillFeedback(**args)
        first = submit(engine, args, engine.observe_trade(record(SECOND, 12))); engine.settle(first["cancel_ack_ts_ns"])
        intent = engine.observe_trade(record(2 * SECOND, 8, 1)); before = engine.snapshot()
        args["tape"]["quote_records"][-1]["bid_size"] += 4
        args["expected_tape_sha256"] = m.canonical_fingerprint(args["tape"])
        with self.assertRaisesRegex(ValueError, "tape changed"):
            submit(engine, args, intent)
        self.assertEqual(engine.snapshot(), before)

    def test_previously_consumed_liquidity_cannot_be_spent_again(self):
        args = fixture(); engine = m.ManagementFillFeedback(**args)
        intent = engine.observe_trade(record(SECOND, 12))
        engine._used_liquidity.add((m.canonical_fingerprint(args["tape"]["quote_request"]), 3))
        before = engine.snapshot()
        with self.assertRaisesRegex(ValueError, "already consumed"):
            submit(engine, args, intent)
        self.assertEqual(engine.snapshot(), before)

    def test_original_source_ordinals_and_native_ties_survive_fill_binding(self):
        args = fixture()
        records = args["tape"]["quote_records"]
        records.insert(2, copy.deepcopy(records[1]))
        for i, row in enumerate(records):
            row["source_record_index"] = i
        args["expected_tape_sha256"] = m.canonical_fingerprint(args["tape"])
        bound = m.bind_entry_evidence(**args)
        self.assertEqual(bound["fill_quote_source"]["source_record_index"], 2)

    def test_source_order_and_clock_reversal_rejected_without_state_mutation(self):
        engine = m.ManagementFillFeedback(**fixture()); engine.observe_trade(record(SECOND, 10))
        for bad in (record(SECOND - 1, 10, 1), record(SECOND + 1, 10, 3)):
            before = engine.snapshot()
            with self.assertRaises(ValueError):
                engine.observe_trade(bad)
            self.assertEqual(engine.snapshot(), before)

    def test_snapshot_copies_and_event_hash_chain_preserve_evidence(self):
        args = fixture(); engine = m.ManagementFillFeedback(**args)
        order = submit(engine, args, engine.observe_trade(record(SECOND, 12))); snapshot = engine.settle(order["cancel_ack_ts_ns"])
        prior = None
        for event in snapshot["events"]:
            self.assertEqual(event["previous_event_sha256"], prior)
            self.assertEqual(reseal(event), event)
            prior = event["content_sha256"]
        snapshot["entry"]["quantity"] = 999
        snapshot["fills"].clear()
        self.assertEqual(engine.snapshot()["entry"]["quantity"], 10)
        self.assertEqual(len(engine.snapshot()["fills"]), 1)

    def test_seeded_synthetic_partial_paths_conserve_shares_in_both_scenarios(self):
        rng = random.Random(20260907)
        for scenario in m.SCENARIOS:
            for _ in range(35):
                quantity = rng.randrange(2, 35)
                target_filled = rng.randrange(quantity // 2 + 1)
                final_filled = rng.randrange(quantity - target_filled + 1)
                args = fixture(quantity, scenario=scenario, target_fill=target_filled, final_fill=final_filled)
                engine = m.ManagementFillFeedback(**args)
                first = submit(engine, args, engine.observe_trade(record(SECOND, 12))); engine.settle(first["cancel_ack_ts_ns"])
                final = submit(engine, args, engine.observe_trade(record(2 * SECOND, 8, 1))); state = engine.settle(final["cancel_ack_ts_ns"])
                with self.subTest(scenario=scenario, quantity=quantity, target=target_filled, final=final_filled):
                    self.assertEqual(state["sold_quantity"], target_filled + final_filled)
                    self.assertEqual(state["remaining_quantity"], quantity - target_filled - final_filled)
                    self.assertEqual(state["target_filled_quantity"], target_filled)
                    self.assertEqual(state["breakeven_active"], target_filled == quantity // 2)
                    self.assertEqual(state["reserved_sell_quantity"], 0)

    def test_small_account_uses_its_frozen_risk_capacity(self):
        bound = m.bind_entry_evidence(**fixture(quantity=10, account="small_account"))
        self.assertEqual(bound["quantity"], 4)
        self.assertEqual(bound["order"]["quantity"], 4)
        self.assertIn("small", bound["account_id"])

    def test_forged_plan_identity_rejected_after_all_outer_hashes_recomputed(self):
        args = fixture(); args["source_decision"]["plan_id"] = "plan-" + "0" * 64
        args["window"]["opportunity"]["plan_id"] = args["source_decision"]["plan_id"]
        args["window"]["opportunity"]["source_decision_content_sha256"] = m.canonical_fingerprint(args["source_decision"])
        repin_context(args)
        with self.assertRaisesRegex(ValueError, "plan identity"):
            m.bind_entry_evidence(**args)

    def test_sell_fill_uses_executable_bid_even_when_it_differs_from_SIP_target(self):
        args = fixture()
        for row in args["tape"]["quote_records"][2:4]:
            row["bid_px_nanos"] = 11_750_000_000
        args["expected_tape_sha256"] = m.canonical_fingerprint(args["tape"])
        engine = m.ManagementFillFeedback(**args)
        order = submit(engine, args, engine.observe_trade(record(SECOND, 13)))
        state = engine.settle(order["arrival_ts_ns"])
        self.assertEqual(m.Decimal(state["fills"][0]["fill_price"]), m.Decimal("11.75"))
        self.assertEqual(state["target_price"], 12)
        self.assertTrue(state["breakeven_active"])

    def test_missing_fresh_sell_reference_cannot_use_SIP_target_as_limit(self):
        args = fixture(); args["tape"]["quote_records"][2]["ts_recv_ns"] = BASE + SECOND - 100_000_001
        args["expected_tape_sha256"] = m.canonical_fingerprint(args["tape"])
        engine = m.ManagementFillFeedback(**args); intent = engine.observe_trade(record(SECOND, 12)); before = engine.snapshot()
        with self.assertRaisesRegex(ValueError, "decision reference unavailable"):
            submit(engine, args, intent)
        self.assertEqual(engine.snapshot(), before)

    def test_repeated_feedback_cannot_duplicate_sell_fills_or_acknowledgments(self):
        args = fixture(); engine = m.ManagementFillFeedback(**args)
        order = submit(engine, args, engine.observe_trade(record(SECOND, 12)))
        state = engine.settle(order["cancel_ack_ts_ns"])
        self.assertEqual(engine.settle(order["cancel_ack_ts_ns"]), state)
        self.assertEqual(len(state["fills"]), 1)
        self.assertEqual(sum(e["event_type"] == "sell_cancel_acknowledged" for e in state["events"]), 1)

    def test_latched_initial_stop_is_not_relabelled_after_target_fill(self):
        args = fixture(); engine = m.ManagementFillFeedback(**args)
        order = submit(engine, args, engine.observe_trade(record(SECOND, 12)))
        engine.observe_trade(record(SECOND + 1, 8, 1)); engine.settle(order["cancel_ack_ts_ns"])
        intent = engine.observe_trade(record(2 * SECOND, 8, 2))
        self.assertEqual(intent["reason"], "initial_stop")

    def test_cancel_ack_boundary_does_not_supply_a_last_instant_fill(self):
        args = fixture(target_fill=0)
        policy, _ = m.SCENARIOS[args["slot"]["execution_scenario_id"]]
        ack = BASE + SECOND + (policy.decision_to_arrival_ms + policy.cancel_after_arrival_ms + policy.cancel_ack_ms) * 1_000_000
        rows = args["tape"]["quote_records"]
        row = copy.deepcopy(rows[3]); row.update(ts_recv_ns=ack, bid_size=2000)
        rows.insert(4, row)
        for i, r in enumerate(rows):
            r["source_record_index"] = i
            r["sequence"] = i
        args["expected_tape_sha256"] = m.canonical_fingerprint(args["tape"])
        engine = m.ManagementFillFeedback(**args)
        submit(engine, args, engine.observe_trade(record(SECOND, 12)))
        state = engine.settle(ack)
        self.assertEqual(state["target_filled_quantity"], 0)
        self.assertFalse(state["breakeven_active"])

    def test_invalid_nanosecond_clock_is_rejected_without_advancing(self):
        engine = m.ManagementFillFeedback(**fixture()); before = engine.snapshot()
        for stamp in (True, float(BASE + SECOND), -1):
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                engine.settle(stamp)
            self.assertEqual(engine.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
