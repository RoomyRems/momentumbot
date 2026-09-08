from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from momentumbot.research import sealed_historical_management_fee_reconciliation_v01 as m
from tests.test_sealed_historical_management_fill_feedback_v01 import fixture, record, minute_bar, BASE, SECOND, reseal, repin_context

ROOT = Path(__file__).resolve().parents[1]


def account(args):
    return m.ReconciledAccountDay(pre_session_ledger=args["pre_entry_ledger"],
        expected_pre_session_ledger_sha256=args["expected_pre_ledger_sha256"],
        path_id=args["slot"]["path_id"], scenario_id=args["slot"]["execution_scenario_id"])


def start(args):
    value = account(args)
    value.start_position(entry_arguments=args, expected_account_content_sha256=value.snapshot()["content_sha256"])
    return value


def set_final_price(args, price):
    for row in args["tape"]["quote_records"][4:]:
        row["bid_px_nanos"] = int(Decimal(price) * 10**9)
        row["ask_px_nanos"] = int((Decimal(price) + Decimal("0.01")) * 10**9)
    args["expected_tape_sha256"] = m.canonical_fingerprint(args["tape"])


def execute(value, args, *, offset=0):
    for dt, price, ordinal in ((SECOND, 12, 0), (2 * SECOND, 8, 1)):
        item = record(dt + offset, price, ordinal)
        intent = value.observe_trade(item)
        if intent is not None:
            order = value.submit_intent(intent, tape=args["tape"], expected_tape_sha256=args["expected_tape_sha256"])
            value.settle(order["cancel_ack_ts_ns"])
    return value.snapshot()


def second_arguments(value, *, offset=5 * SECOND):
    args = fixture()
    decision = args["source_decision"]
    decision["symbol"] = decision["plan"]["symbol"] = "SYNTHETICTWO"
    decision["activation_id"] = "synthetic-activation-two"
    for key in ("decision_at", "candidate_qualified_at"):
        decision[key] = (pd.Timestamp(decision[key]) + pd.Timedelta(offset, unit="ns")).isoformat()
    for key in ("source_bar_start", "armed_at", "expires_at"):
        decision["plan"][key] = (pd.Timestamp(decision["plan"][key]) + pd.Timedelta(offset, unit="ns")).isoformat()
    decision["plan_id"] = "plan-" + m.canonical_fingerprint({"activation_id": decision["activation_id"], "plan": decision["plan"]})
    op = m.feedback.accounts.availability.plan._opportunities(m.seal({"trading_date": "2025-05-30", "decisions": [decision]}))[0]
    args["window"]["opportunity"] = op
    for key in ("signal_end_ns", "end_ns"):
        args["window"][key] += offset
    args["window"]["start_ns"] = op["decision_ts_ns"] // (60 * SECOND) * (60 * SECOND)
    args["slot"]["opportunity_inputs"][0]["opportunity_id"] = op["opportunity_id"]
    args["slot"] = reseal(args["slot"])
    for key in ("quote_request", "status_request"):
        request = args["tape"][key]
        request["symbols"] = ["SYNTHETICTWO"]
        request["request_id"] = request["request_id"].replace("SYNTHETIC", "SYNTHETICTWO")
        if key == "quote_request":
            request["start_ns"] += offset
        request["end_ns"] += offset
    for row in args["tape"]["quote_records"] + args["tape"]["status_records"]:
        row["symbol"] = "SYNTHETICTWO"
        row["ts_recv_ns"] += offset
    for row in args["tape"]["quote_records"]:
        row["source_request_sha256"] = m.canonical_fingerprint(args["tape"]["quote_request"])
    args["expected_tape_sha256"] = m.canonical_fingerprint(args["tape"])
    args["pre_entry_ledger"] = value.ledger_copy()
    args["expected_pre_ledger_sha256"] = m.canonical_fingerprint(args["pre_entry_ledger"].runtime_artifact())
    repin_context(args)
    return args


def synthetic_vectors():
    """Independent checker input; deliberately synthetic, never market archives."""
    cases = []
    for scenario in m.feedback.SCENARIOS:
        for target_fill, final_fill, label in ((5, 5, "full"), (2, 3, "partial"), (0, 0, "zero")):
            args = fixture(scenario=scenario, target_fill=target_fill, final_fill=final_fill)
            value = start(args)
            initial = value.snapshot()
            final = execute(value, args)
            cases.append({"case_id": scenario + ":" + label, "requested_entry_fixture_shares": 10,
                          "initial": initial, "final": final})
    for price, label in (("9.003", "above_net_giveback"), ("9.002", "equal_net_giveback")):
        args = fixture()
        set_final_price(args, price)
        value = start(args)
        initial = value.snapshot()
        cases.append({"case_id": label, "requested_entry_fixture_shares": 10, "initial": initial, "final": execute(value, args)})
    args = fixture(account="small_account", quantity=4, target_fill=0, final_fill=4)
    set_final_price(args, "5.005")
    value = start(args)
    cases.append({"case_id": "small_net_loss_limit", "requested_entry_fixture_shares": 4,
                  "initial": value.snapshot(), "final": execute(value, args)})
    args = fixture()
    set_final_price(args, "11")
    value = start(args)
    initial = value.snapshot()
    execute(value, args)
    value.release_position()
    more = second_arguments(value)
    value.start_position(entry_arguments=more, expected_account_content_sha256=value.snapshot()["content_sha256"])
    cases.append({"case_id": "two_sequential_positions", "requested_entry_fixture_shares": 10,
                  "initial": initial, "final": execute(value, more, offset=5 * SECOND)})
    fee_cases = []
    for day in (date(2025, 6, 30), date(2025, 7, 1)):
        book = m.DailyFeeAccumulator(account_id="synthetic", path_id="synthetic-path", scenario_id="l1-conservative-v0.1", trading_date=day)
        at = int(pd.Timestamp(str(day) + "T13:00Z").value)
        events = [book.add(fill_id=str(i), order_id=str(i), side=side, quantity=qty, price="10", timestamp_ns=at + i)
                  for i, (side, qty) in enumerate((("buy", 1000), ("sell", 400), ("sell", 600), ("sell", 100000), ("sell", 100000)))]
        fee_cases.append({"day": str(day), "applications": events, "state": book.snapshot()})
    return m.seal({"contract_id": m.CONTRACT_ID, "synthetic_only": True, "historical_execution_count": 0,
                   "account_cases": cases, "fee_cases": fee_cases})


class HistoricalFeeTests(unittest.TestCase):
    def book(self, day=date(2025, 5, 30)):
        return m.DailyFeeAccumulator(account_id="synthetic", path_id="synthetic-path", scenario_id="l1-conservative-v0.1", trading_date=day)

    def trade(self, book, index, side="buy", qty=1, price="10", at=None):
        return book.add(fill_id=str(index), order_id=str(index), side=side, quantity=qty, price=price,
                        timestamp_ns=BASE + index if at is None else at)

    def test_historical_rates_are_explicit_and_do_not_use_2026_defaults(self):
        for day, cat in ((date(2025, 5, 30), "0.000035"), (date(2025, 6, 30), "0.000035"),
                         (date(2025, 7, 1), "0.000022"), (date(2025, 7, 17), "0.000022")):
            with self.subTest(day=day):
                rate = m.historical_schedule(day)
                self.assertEqual(rate.sec_sale_rate_per_dollar, Decimal(0))
                self.assertEqual(rate.taf_sale_rate_per_share, Decimal("0.000166"))
                self.assertEqual(rate.taf_per_trade_cap, Decimal("8.30"))
                self.assertEqual(rate.cat_rate_per_executed_share, Decimal(cat))
                self.assertEqual(rate.commission_rate_per_dollar, Decimal(0))
        self.assertEqual(m.execution.EquityFeeSchedule().taf_sale_rate_per_share, Decimal("0.000195"))

    def test_invalid_or_out_of_interval_dates_fail_closed(self):
        for day in (date(2025, 5, 29), date(2025, 7, 18), date(2026, 5, 30), "2025-05-30", datetime(2025, 5, 30)):
            with self.subTest(day=day), self.assertRaises(ValueError):
                self.book(day)

    def test_buy_only_cat_and_daily_rounding_increment_not_per_fill(self):
        book = self.book()
        self.assertEqual(self.trade(book, 0)["incremental_charge"]["total"], "0.01")
        for i in range(1, 285):
            self.assertEqual(Decimal(self.trade(book, i)["incremental_charge"]["total"]), 0)
        self.assertEqual(self.trade(book, 285)["incremental_charge"]["cat"], "0.01")
        fees = book.snapshot()["fees"]
        self.assertEqual(fees["cat_charged"], "0.02")
        self.assertEqual(fees["taf_charged"], "0.00")

    def test_sell_taf_and_cat_caps_are_per_trade_before_daily_rounding(self):
        book = self.book()
        self.trade(book, 0, "sell", 100000)
        self.trade(book, 1, "sell", 100000)
        self.assertEqual(book.snapshot()["fees"]["taf_charged"], "16.60")
        self.trade(book, 2, "sell", 1)
        self.assertEqual(book.snapshot()["fees"]["taf_charged"], "16.61")

    def test_july_boundary_uses_trade_date_not_invoice_month(self):
        for day, expected in ((date(2025, 6, 30), "0.04"), (date(2025, 7, 1), "0.03")):
            book = self.book(day)
            self.trade(book, 0, qty=1000, at=int(pd.Timestamp(str(day) + "T13:00Z").value))
            self.assertEqual(book.snapshot()["fees"]["total_charged"], expected)

    def test_repeated_read_does_not_post_fees_twice(self):
        book = self.book()
        self.trade(book, 0)
        before = book.snapshot()
        self.assertEqual(before, book.snapshot())
        before["identity"]["account_id"] = "mutated"
        before["trades"][0]["quantity"] = 900
        self.assertEqual(book.snapshot()["trades"][0]["quantity"], 1)
        self.assertEqual(book.snapshot()["identity"]["account_id"], "synthetic")

    def test_duplicate_fill_and_duplicate_order_are_atomic(self):
        book = self.book()
        self.trade(book, 0)
        before = book.snapshot()
        for fill, order in (("0", "new"), ("new", "0")):
            with self.assertRaisesRegex(ValueError, "duplicate"):
                book.add(fill_id=fill, order_id=order, side="buy", quantity=1, price="10", timestamp_ns=BASE)
            self.assertEqual(book.snapshot(), before)

    def test_canceled_zero_negative_fractional_shares_and_bad_prices_rejected(self):
        for qty in (0, -1, True, 1.5, 10**9 + 1):
            with self.subTest(quantity=qty), self.assertRaises(ValueError):
                self.trade(self.book(), 0, qty=qty)
        for price in ("0", "-1", "NaN", "Infinity", "1e10000", "0.0000000001", 10.0, True):
            with self.subTest(price=price), self.assertRaises(ValueError):
                self.trade(self.book(), 0, price=price)

    def test_fee_book_clock_and_new_york_date(self):
        book = self.book()
        self.trade(book, 2)
        before = book.snapshot()
        for at in (BASE + 1, BASE + 86400 * SECOND, True, -1):
            with self.subTest(at=at), self.assertRaises(ValueError):
                self.trade(book, 3, at=at)
            self.assertEqual(book.snapshot(), before)

    def test_deterministic_precision_ignores_callers_decimal_context(self):
        book = self.book()
        with localcontext() as ctx:
            ctx.prec = 6
            self.trade(book, 0, "sell", 123456789, "9.123456789")
            first = book.snapshot()
        self.assertEqual(first, book.snapshot())


class ReconciliationTests(unittest.TestCase):
    def test_recomputed_entry_applies_only_filled_shares_and_entry_fee(self):
        args = fixture(quantity=10)
        before = deepcopy(args["pre_entry_ledger"].runtime_artifact())
        value = start(args)
        state = value.snapshot()
        self.assertEqual(args["pre_entry_ledger"].runtime_artifact(), before)
        self.assertEqual(state["management"]["entry"]["quantity"], 10)
        self.assertGreater(state["management"]["entry"]["order"]["quantity"], 10)
        self.assertEqual(state["exact_account"]["remaining_buying_power"], "29899.99")
        self.assertEqual(state["exact_account"]["net_realized_pnl"], "-0.01")
        self.assertEqual(state["ledger"]["account"]["realized_pnl"], -0.01)

    def test_full_round_trip_updates_cash_shares_net_pnl_and_guards(self):
        args = fixture()
        value = start(args)
        state = execute(value, args)
        self.assertEqual(state["exact_account"]["gross_realized_pnl"], "5")
        self.assertEqual(state["exact_account"]["net_realized_pnl"], "4.98")
        self.assertEqual(state["exact_account"]["remaining_buying_power"], "30004.98")
        self.assertEqual(state["fee_book"]["fees"]["total_charged"], "0.02")
        self.assertEqual(len(state["journal"]), 3)
        self.assertEqual(state["ledger"]["account"]["total_open_risk"], 0)
        self.assertEqual(state["ledger"]["account"]["lock_reason"], "profit_giveback")
        self.assertTrue(value.release_position()["confirmed_position_shares_closed"])
        self.assertFalse(value.snapshot()["account_close_evidence"])

    def test_no_fee_cash_or_share_change_on_intent_or_submission(self):
        args = fixture()
        value = start(args)
        before = value.snapshot()
        intent = value.observe_trade(record(SECOND, 12))
        order = value.submit_intent(intent, tape=args["tape"], expected_tape_sha256=args["expected_tape_sha256"])
        state = value.snapshot()
        for key in ("exact_account", "fee_book", "journal", "ledger"):
            self.assertEqual(state[key], before[key])
        self.assertEqual(state["management"]["reserved_sell_quantity"], 5)
        self.assertEqual(len(value.settle(order["arrival_ts_ns"] - 1)["journal"]), 1)

    def test_equal_time_trade_precedes_fill_then_settlement_is_idempotent(self):
        args = fixture()
        value = start(args)
        intent = value.observe_trade(record(SECOND, 12))
        order = value.submit_intent(intent, tape=args["tape"], expected_tape_sha256=args["expected_tape_sha256"])
        fill_at = order["arrival_ts_ns"]
        value.observe_trade(record(fill_at - BASE, 11, 1))
        self.assertEqual(len(value.snapshot()["journal"]), 1)
        first = value.settle(fill_at)
        self.assertEqual(len(first["journal"]), 2)
        self.assertEqual(first, value.settle(fill_at))
        with self.assertRaisesRegex(ValueError, "clock"):
            value.observe_trade(record(fill_at - BASE, 11, 2))

    def test_partial_target_keeps_original_stop_and_correct_open_risk(self):
        args = fixture(target_fill=2)
        value = start(args)
        intent = value.observe_trade(record(SECOND, 12))
        order = value.submit_intent(intent, tape=args["tape"], expected_tape_sha256=args["expected_tape_sha256"])
        state = value.settle(order["cancel_ack_ts_ns"])
        self.assertFalse(state["management"]["breakeven_active"])
        self.assertEqual(state["ledger"]["account"]["total_open_risk"], 8)
        self.assertEqual(state["management"]["remaining_quantity"], 8)

    def test_complete_target_moves_remaining_ledger_lots_to_breakeven(self):
        args = fixture()
        value = start(args)
        intent = value.observe_trade(record(SECOND, 12))
        order = value.submit_intent(intent, tape=args["tape"], expected_tape_sha256=args["expected_tape_sha256"])
        state = value.settle(order["arrival_ts_ns"])
        self.assertTrue(state["management"]["breakeven_active"])
        self.assertEqual(state["ledger"]["account"]["total_open_risk"], 0)
        self.assertEqual([lot.stop_price for lot in value.ledger_copy().campaigns["synthetic-activation"].lots], [10])
        self.assertEqual(len([e for e in state["ledger"]["events"] if e["event_type"] == "confirmed_target_stop_updated"]), 1)

    def test_partial_terminal_cannot_close_or_release_and_charges_actual_fills(self):
        args = fixture(target_fill=2, final_fill=3)
        value = start(args)
        state = execute(value, args)
        self.assertEqual(state["management"]["remaining_quantity"], 5)
        self.assertEqual(state["management"]["reserved_sell_quantity"], 0)
        self.assertEqual(state["management"]["status"], "open_unresolved_exit_remainder")
        self.assertEqual(sum(t["quantity"] for t in state["fee_book"]["trades"] if t["side"] == "sell"), 5)
        before = value.snapshot()
        with self.assertRaisesRegex(ValueError, "confirmed flat"):
            value.release_position()
        self.assertEqual(before, value.snapshot())

    def test_zero_exit_fills_have_no_sale_fee_or_proceeds(self):
        args = fixture(target_fill=0, final_fill=0)
        value = start(args)
        before = value.snapshot()
        after = execute(value, args)
        self.assertEqual(after["fee_book"], before["fee_book"])
        self.assertEqual(after["exact_account"], before["exact_account"])
        self.assertEqual(len(after["journal"]), 1)

    def test_fee_inclusive_high_water_does_not_use_gross_intermediate_peak(self):
        args = fixture()
        set_final_price(args, "9.003")
        state = execute(start(args), args)
        self.assertEqual(state["exact_account"]["net_high_water_pnl"], "9.98")
        self.assertEqual(state["exact_account"]["net_realized_pnl"], "4.995")
        self.assertFalse(state["ledger"]["account"]["locked"])

    def test_exact_net_giveback_boundary_locks(self):
        args = fixture()
        set_final_price(args, "9.002")
        state = execute(start(args), args)
        self.assertEqual(Decimal(state["exact_account"]["net_realized_pnl"]), Decimal("4.99"))
        self.assertEqual(state["ledger"]["account"]["lock_reason"], "profit_giveback")

    def test_fees_take_small_account_to_exact_daily_loss_boundary(self):
        args = fixture(account="small_account", quantity=4, target_fill=0, final_fill=4)
        set_final_price(args, "5.005")
        state = execute(start(args), args)
        self.assertEqual(Decimal(state["exact_account"]["gross_realized_pnl"]), Decimal("-19.98"))
        self.assertEqual(Decimal(state["exact_account"]["net_realized_pnl"]), Decimal("-20.00"))
        self.assertEqual(state["ledger"]["account"]["lock_reason"], "daily_max_loss")

    def test_one_share_has_no_target_or_breakeven(self):
        args = fixture(quantity=1)
        state = execute(start(args), args)
        self.assertEqual(len(state["journal"]), 2)
        self.assertFalse(state["management"]["breakeven_active"])
        self.assertEqual(state["management"]["remaining_quantity"], 0)

    def test_bad_submission_and_failed_reconciliation_roll_back_entire_transition(self):
        args = fixture()
        value = start(args)
        intent = value.observe_trade(record(SECOND, 12))
        before = value.snapshot()
        with self.assertRaises(ValueError):
            value.submit_intent(intent, tape=args["tape"], expected_tape_sha256="0" * 64)
        self.assertEqual(value.snapshot(), before)
        order = value.submit_intent(intent, tape=args["tape"], expected_tape_sha256=args["expected_tape_sha256"])
        before = value.snapshot()
        with patch.object(m._NetLedger, "apply_exit_fill", side_effect=ValueError("injected rejection")):
            with self.assertRaisesRegex(ValueError, "injected rejection"):
                value.settle(order["cancel_ack_ts_ns"])
        self.assertEqual(value.snapshot(), before)
        self.assertEqual(len(value.settle(order["cancel_ack_ts_ns"])["journal"]), 2)

    def test_entry_pins_and_wrong_account_scenario_fail_without_mutation(self):
        args = fixture()
        value = account(args)
        before = value.snapshot()
        with self.assertRaisesRegex(ValueError, "caller pin"):
            value.start_position(entry_arguments=args, expected_account_content_sha256="0" * 64)
        self.assertEqual(value.snapshot(), before)
        wrong = fixture(scenario="l1-stress-v0.1")
        with self.assertRaisesRegex(ValueError, "scenario"):
            value.start_position(entry_arguments=wrong, expected_account_content_sha256=before["content_sha256"])
        self.assertEqual(value.snapshot(), before)

    def test_imported_or_mutated_opening_ledger_rejected(self):
        args = fixture()
        args["pre_entry_ledger"].remaining_buying_power = 29999
        args["expected_pre_ledger_sha256"] = m.canonical_fingerprint(args["pre_entry_ledger"].runtime_artifact())
        with self.assertRaisesRegex(ValueError, "empty"):
            account(args)

    def test_mutating_exported_state_and_ledger_cannot_change_account(self):
        value = start(fixture())
        before = value.snapshot()
        state = value.snapshot()
        state["identity"]["path_id"] = "fake"
        state["management"]["entry"]["quantity"] = 900
        state["journal"].clear()
        value.ledger_copy().remaining_buying_power = 1e8
        self.assertEqual(value.snapshot(), before)

    def test_second_position_keeps_daily_fee_book_and_net_cash(self):
        args = fixture()
        set_final_price(args, "11")
        value = start(args)
        execute(value, args)
        value.release_position()
        before = value.snapshot()
        more = second_arguments(value)
        value.start_position(entry_arguments=more, expected_account_content_sha256=before["content_sha256"])
        current = value.snapshot()
        self.assertEqual(current["journal"][-1]["fee_application"]["incremental_charge"]["total"], "0.00")
        self.assertEqual(len(current["fee_book"]["trades"]), 4)
        after = execute(value, more, offset=5 * SECOND)
        self.assertEqual(len(after["journal"]), 6)
        self.assertEqual(after["fee_book"]["fees"]["total_charged"], "0.02")
        self.assertEqual(Decimal(after["exact_account"]["remaining_buying_power"]), Decimal("30019.98"))

    def test_second_position_cannot_use_reset_ledger_or_stale_pin(self):
        args = fixture()
        set_final_price(args, "11")
        value = start(args)
        execute(value, args)
        value.release_position()
        more = second_arguments(value)
        more["pre_entry_ledger"] = fixture()["pre_entry_ledger"]
        more["expected_pre_ledger_sha256"] = m.canonical_fingerprint(more["pre_entry_ledger"].runtime_artifact())
        before = value.snapshot()
        with self.assertRaisesRegex(ValueError, "current net"):
            value.start_position(entry_arguments=more, expected_account_content_sha256=before["content_sha256"])
        self.assertEqual(value.snapshot(), before)

    def test_account_lock_persists_and_rejects_new_entry(self):
        args = fixture()
        value = start(args)
        execute(value, args)
        value.release_position()
        more = second_arguments(value)
        before = value.snapshot()
        with self.assertRaises(ValueError):
            value.start_position(entry_arguments=more, expected_account_content_sha256=before["content_sha256"])
        self.assertEqual(value.snapshot(), before)

    def test_no_concurrent_position_or_outstanding_ack_release(self):
        args = fixture()
        value = start(args)
        before = value.snapshot()
        with self.assertRaisesRegex(ValueError, "one active"):
            value.start_position(entry_arguments=args, expected_account_content_sha256=before["content_sha256"])
        self.assertEqual(value.snapshot(), before)
        intent = value.observe_trade(record(2 * SECOND, 8))
        order = value.submit_intent(intent, tape=args["tape"], expected_tape_sha256=args["expected_tape_sha256"])
        value.settle(order["arrival_ts_ns"])
        with self.assertRaisesRegex(ValueError, "cancel acknowledgements"):
            value.release_position()

    def test_bar_completion_delegates_to_frozen_engine_without_account_changes(self):
        args = fixture()
        value = start(args)
        before = value.snapshot()
        value.observe_bar(minute_bar())
        after = value.snapshot()
        for key in ("exact_account", "fee_book", "journal"):
            self.assertEqual(after[key], before[key])

    def test_both_frozen_execution_scenarios_preserve_closed_boundaries(self):
        for scenario in m.feedback.SCENARIOS:
            args = fixture(scenario=scenario)
            result = execute(start(args), args)
            self.assertEqual(result["management"]["remaining_quantity"], 0)
            for name, expected in m.BOUNDARY.items():
                self.assertEqual(result[name], expected)


class RegistrationTests(unittest.TestCase):
    def test_direct_cli_generates_synthetic_vectors_and_independent_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "vectors"
            result = subprocess.run([sys.executable, str(ROOT / m.SCRIPT_PATH), "--synthetic-vectors", "--output-root", str(out)],
                cwd=ROOT, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertTrue(output["synthetic_only"])
            check = subprocess.run([sys.executable, str(ROOT / m.CHECKER_PATH), "--vectors", str(out / "synthetic-vectors.json")],
                cwd=ROOT, text=True, capture_output=True, check=False)
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertEqual(json.loads(check.stdout)["confirmed_execution_rows_verified"], 28)

    def test_registration_and_complete_session_fee_map(self):
        report = m.validate_registration(ROOT)
        self.assertTrue(report["verification_passed"])
        bundle = {name: json.loads(raw) for name, raw in m.build_bundle(ROOT).items()}
        paths = bundle["fee-session-map.json"]["paths"]
        self.assertEqual(len(paths), 12)
        self.assertEqual(sum(len(p["sessions"]) for p in paths), 360)
        self.assertEqual(len({s["trading_date"] for p in paths for s in p["sessions"]}), 30)
        self.assertEqual({s["fee_period"] for p in paths for s in p["sessions"]}, {"2025-1", "2025-2"})

    def test_metadata_never_opens_market_tapes_or_executes_history(self):
        with patch.object(m.feedback, "ManagementFillFeedback", side_effect=AssertionError("no replay")), patch.object(m.parent, "ExitInputBundle", side_effect=AssertionError("no tapes")):
            self.assertEqual(len(m.build_bundle(ROOT)), 4)

    def test_parent_source_and_implementation_mutations_fail(self):
        original = m.file_sha
        for path in (next(iter(m.PARENT_PINS)), m.SOURCES_PATH, m.MODULE_PATH):
            with self.subTest(path=path), patch.object(m, "file_sha", side_effect=lambda p: "0" * 64 if str(p).endswith(path) else original(p)):
                with self.assertRaises(ValueError):
                    m.validate_registration(ROOT)

    def test_write_once_and_rehashed_metadata_still_fails_reconstruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle"
            self.assertTrue(m.write_bundle(ROOT, out)["verification_passed"])
            with self.assertRaises(FileExistsError):
                m.write_bundle(ROOT, out)
            path = out / "readiness-report.json"
            data = json.loads(path.read_text())
            data["historical_runtime_authorized"] = True
            path.write_bytes(m.encoded(reseal(data)))
            with self.assertRaisesRegex(ValueError, "reconstruction"):
                m.verify_bundle(ROOT, out)

    def test_independent_checker_validates_vectors_and_rejects_rehashed_wrong_cash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vectors.json"
            data = synthetic_vectors()
            path.write_bytes(m.encoded(data))
            from verify_sealed_historical_management_fee_reconciliation_v01 import verify
            result = verify(ROOT, ROOT / m.OUTPUT_PATH, path)
            self.assertTrue(result["verification_passed"])
            self.assertEqual(result["account_cases_verified"], 10)
            bad = deepcopy(data)
            bad["account_cases"][0]["final"]["exact_account"]["remaining_buying_power"] = "99999"
            bad["account_cases"][0]["final"] = reseal(bad["account_cases"][0]["final"])
            bad = reseal(bad)
            path.write_bytes(m.encoded(bad))
            with self.assertRaises(ValueError):
                verify(ROOT, ROOT / m.OUTPUT_PATH, path)


if __name__ == "__main__":
    unittest.main()
