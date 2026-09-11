import ast
from copy import deepcopy
from datetime import date
from decimal import Decimal
import inspect
import json
from pathlib import Path
import tempfile
import textwrap
import unittest

import pandas as pd

from momentumbot.research import early_pullback_panel_accounts_v01 as a
from momentumbot.research import early_pullback_panel_account_engine_v01 as engine
from momentumbot.research import sealed_historical_account_replay_v01 as original_replay
from tests.test_early_pullback_panel_sources_v01 import archive_fixture, day_source
from tests.test_sealed_historical_account_scheduler_v01 import spec, repin

ROOT = Path(__file__).resolve().parents[1]
MONEY = ("equity_usd", "buying_power_usd", "cumulative_realized_pnl_usd", "cumulative_fees_usd")


def small_price_day(day=a.sources.DATES[0]):
    value = day_source(day)
    scanner = value["scanner"]
    scanner["candidate_rows"][0]["previous_close"] /= 2
    scanner["previous_close_by_symbol"]["SYNTHETICA"] /= 2
    packed = [scanner["candidate_raw_minute_bars_by_symbol"]["SYNTHETICA"],
              scanner["rank_split_minute_bars_by_symbol"]["SYNTHETICA"]]
    micro = value["micro_by_symbol"]["SYNTHETICA"]
    packed += [micro["trades"], micro["session_minutes_raw"], micro["ema_warmup_split"]]
    for frame in packed:
        for i, key in enumerate(frame["columns"]):
            if key in {"price", "open", "high", "low", "close", "vwap"}:
                for row in frame["data"]:
                    row[i] /= 2
    return value


def fixture(path, *, changes=None, unavailable_ordinals=(), partial=False, stress_quotes=True, price_scale=1):
    pins = archive_fixture(path, changes=changes)
    with a.sources.SourceArchive(path, **pins) as archive:
        panel = a.sources.bind_panel(archive)
    execution = {"contract_id": a.ID, "scope": a.sources.SCOPE, "source_archive": pins["expected_archive"],
        "capture_manifest_sha256": pins["expected_manifest_sha256"], "by_plan": {}}
    for day, built in panel["days"].items():
        for decision in built["decisions"]:
            if decision["plan"]["pullback_number"] in unavailable_ordinals:
                record = {"input_status": "unavailable", "reason": "synthetic_missing_quote", "execution": None}
            else:
                offset = int(pd.Timestamp(decision["decision_at"]).value) - int(pd.Timestamp(day + "T13:00:00Z").value)
                # One shared displayed tape covers both fixed participation
                # scenarios. The explicit partial fixture keeps scarce depth.
                value = spec(day=day, offset=offset,
                    **({"target_fill": 2, "final_fill": 3} if partial else {"final_fill": 10}))
                if price_scale != 1:
                    for tape in (value["entry_input"]["tape"], value["exit_tape"]):
                        for row in tape["quote_records"]:
                            for key in ("bid_px_nanos", "ask_px_nanos"):
                                row[key] = int(row[key] * price_scale)
                    for row in value["trades"]:
                        row["record"]["p"] *= price_scale
                if stress_quotes:
                    # A second observed update precedes the stress arrival by
                    # 10 ms; no change to either scenario's strict quote clock.
                    at = int(pd.Timestamp(decision["decision_at"]).value)
                    for tape in (value["entry_input"]["tape"], value["exit_tape"]):
                        extra = []
                        for row in tape["quote_records"]:
                            if (row["ts_recv_ns"] - at) % 1_000_000_000 == 90_000_000:
                                extra.append({**deepcopy(row), "ts_recv_ns": row["ts_recv_ns"] + 150_000_000})
                        tape["quote_records"].extend(extra)
                        tape["quote_records"].sort(key=lambda row: row["ts_recv_ns"])
                repin(value)
                record = {"input_status": "available", "reason": "synthetic_available", "execution": {
                    "entry_tape": value["entry_input"]["tape"], "entry_tape_sha256": value["entry_input"]["expected_tape_sha256"],
                    "bars": value["bars"], "trades": value["trades"], "expected_streams": value["expected_streams"],
                    "exit_tape": value["exit_tape"], "exit_tape_sha256": value["expected_exit_tape_sha256"]}}
            execution["by_plan"][decision["plan_id"]] = record
    return pins, execution


def prepare(path, pins, execution):
    with a.sources.SourceArchive(path, **pins) as archive:
        return a.prepare_inputs(archive, execution, expected_execution_sha256=a.fingerprint(execution))


def replay(path, pins, execution):
    with a.sources.SourceArchive(path, **pins) as archive:
        return a.replay_synthetic_panel(archive, execution, expected_execution_sha256=a.fingerprint(execution))


def run_path(prepared, index=0):
    return a._run_path(prepared["paths"][index], prepared["items"], prepared["bindings"])


def state(result, index=0):
    return result["sessions"][index]["close"]["account_state"]


class MechanicalParityTests(unittest.TestCase):
    def compare(self, new, old, substitutions=(), tail=""):
        expected = textwrap.dedent(inspect.getsource(old))
        for before, after in substitutions:
            self.assertIn(before, expected)
            expected = expected.replace(before, after)
        expected += tail
        self.assertEqual(ast.dump(ast.parse(textwrap.dedent(inspect.getsource(new)))), ast.dump(ast.parse(expected)))

    def test_context_ports_preserve_every_frozen_mechanical_statement(self):
        c = engine.continuity
        self.compare(engine._new_day, a.producer._new_day,
            (("accounts._validate_slot(slot)", "validate_slot(slot)"), ("fees.ReconciledAccountDay(", "_AccountDay(")))
        self.compare(engine._candidate, engine.scheduler._candidate, (("accounts._validate_slot(slot)", "validate_slot(slot)"),))
        self.compare(engine._validate_entry_context, c._validate_entry_context, (("accounts._validate_slot(slot)", "validate_slot(slot)"),))
        self.compare(engine.bind_entry_evidence, c.bind_entry_evidence)
        self.compare(engine._Management.__init__, c._Management.__init__, tail=
            "    self._init_waiting()\n    self._init_residual()\n    self._init_continuation()\n")
        self.compare(engine._AccountDay._start, c._AccountDay._start)
        self.compare(engine._prepare, c._prepare)
        self.compare(engine.Session.__init__, c._Session.__init__,
            (("def __init__(self, slot, source, opening):", "def __init__(self, slot, source, opening, resolve, bindings, arm):"),),
            tail="    self.resolve = resolve\n    self.selection_bindings, self.arm = bindings, arm\n")
        self.compare(engine.Session.initialize, original_replay._Session.initialize,
            (("scheduler._candidate(", "_candidate("), ("continuity.valuation.session_start_ns(", "session_start_ns(")))
        self.compare(engine.session_start_ns, engine.continuity.valuation.session_start_ns,
            (("parent.accounts._validate_slot(slot)", "validate_slot(slot)"),))
        self.compare(engine.Session._mechanical_decision, c._Session.decision, (("def decision(", "def _mechanical_decision("),))
        self.compare(engine.Session.decision, a.parent._SelectedSession.decision,
            (("super().decision(at, oid)", "self._mechanical_decision(at, oid)"),))
        self.compare(engine.finish, a.parent._finish, (("def _finish(", "def finish("),))
        self.compare(engine.DailyFeeAccumulator.__init__, engine.fees.DailyFeeAccumulator.__init__,
            (("historical_schedule(trading_date)", "context.fee_schedule(trading_date)"),))
        self.compare(engine._AccountDay.__init__, engine.fees.ReconciledAccountDay.__init__, tail=
            "    self._released_liquidity = set()\n    self._exit_wait_events = []\n"
            "    self._exit_residual_events = []\n    self._exit_continuation_events = []\n")

    def test_final_management_and_account_methods_are_inherited_unchanged(self):
        for name in ("market", "settle", "run_until", "push_cursor", "pending_public", "progress"):
            self.assertIs(getattr(engine.Session, name), getattr(engine.terminal.Session, name))
        for name in ("snapshot", "_transition", "_record", "release_position", "_check"):
            self.assertIs(getattr(engine._AccountDay, name), getattr(engine.terminal.AccountDay, name))
        for name in ("observe_trade", "observe_bar", "submit_intent", "_advance", "snapshot"):
            self.assertIs(getattr(engine._Management, name), getattr(engine.terminal.Management, name))
        self.assertEqual(engine.CONTRACT_ID, engine.continuity.CONTRACT_ID)
        self.assertIs(engine.DailyFeeAccumulator.add, engine.fees.DailyFeeAccumulator.add)


class FeeContextTests(unittest.TestCase):
    def test_dated_2026_schedule_and_original_guard(self):
        for day, sec, cat in (("2026-03-04", "0", "0"), ("2026-04-02", "0", "0"),
                              ("2026-04-06", "0.0000206", "0"), ("2026-04-30", "0.0000206", "0"),
                              ("2026-05-04", "0.0000206", "0.000003"), ("2026-05-19", "0.0000206", "0.000003")):
            value = a.fee_schedule(date.fromisoformat(day))
            self.assertEqual(value.sec_sale_rate_per_dollar, Decimal(sec))
            self.assertEqual(value.cat_rate_per_executed_share, Decimal(cat))
            self.assertEqual(value.taf_sale_rate_per_share, Decimal("0.000195"))
            self.assertEqual(value.taf_per_trade_cap, Decimal("9.79"))
        with self.assertRaisesRegex(ValueError, "2025 fee interval"):
            engine.fees.historical_schedule(date(2026, 3, 4))
        for value in (date(2025, 5, 30), date(2026, 3, 11), "2026-03-04", True):
            with self.assertRaises(ValueError):
                a.fee_schedule(value)

    def test_same_fee_arithmetic_capping_and_daily_increment_on_new_dates(self):
        for day, total in (("2026-03-04", "9.79"), ("2026-04-06", "22.15"), ("2026-05-04", "22.63")):
            book = engine.DailyFeeAccumulator(account_id="synthetic-account", path_id="synthetic-path",
                scenario_id="l1-conservative-v0.1", trading_date=date.fromisoformat(day))
            at = int(a.sources._local(day, 8).value)
            self.assertEqual(Decimal(book.snapshot()["fees"]["total_charged"]), 0)
            buy = book.add(fill_id="buy-fill", order_id="buy-order", side="buy", quantity=100000, price="10", timestamp_ns=at)
            sell = book.add(fill_id="sell-fill", order_id="sell-order", side="sell", quantity=60000, price="10", timestamp_ns=at+1)
            self.assertEqual(Decimal(book.snapshot()["fees"]["total_charged"]), Decimal(total))
            self.assertEqual(Decimal(buy["incremental_charge"]["total"]) + Decimal(sell["incremental_charge"]["total"]), Decimal(total))
            before = book.snapshot()
            with self.assertRaisesRegex(ValueError, "duplicate"):
                book.add(fill_id="sell-fill", order_id="sell-order", side="sell", quantity=60000, price="10", timestamp_ns=at+2)
            self.assertEqual(book.snapshot(), before)
            self.assertEqual(before["contract_id"], a.ID)
            self.assertTrue(before["dated_fee_context"])
            self.assertFalse(before["broker_statement_equivalence_verified"])


class PanelAccountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.temp.name) / "sources.zip"
        cls.pins, cls.execution = fixture(cls.path)
        cls.prepared = prepare(cls.path, cls.pins, cls.execution)
        cls.result = replay(cls.path, cls.pins, cls.execution)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_all_24_paths_run_720_real_new_date_slots_seed_once(self):
        result = self.result
        self.assertEqual((result["path_count"], result["session_slot_count"]), (24, 720))
        self.assertEqual(len({p["path_id"] for p in result["paths"]}), 24)
        for path in result["paths"]:
            self.assertEqual(path["seed_application_count"], 1)
            self.assertEqual([s["close"]["trading_date"] for s in path["sessions"]], list(a.sources.DATES))
            self.assertEqual(sum(s["close"]["seed_applied"] for s in path["sessions"]), 1)
            for i, session in enumerate(path["sessions"]):
                self.assertIsNone(session["runtime"]["failure"])
                self.assertEqual(session["runtime"]["status"], "flat_complete")
                self.assertTrue(session["runtime"]["complete_streams_verified"])
                self.assertEqual(session["close"]["previous_close_content_sha256"],
                    None if i == 0 else path["sessions"][i - 1]["close"]["content_sha256"])
                if i:
                    self.assertEqual(session["close"]["account_state"], state(path, i - 1))
            if "main_account" in path["cell_id"]:
                self.assertGreater(Decimal(state(path)["cumulative_fees_usd"]), 0)
            else:
                # The unchanged small profile rejects this fixture's $8
                # scanner price; it must not borrow main-account eligibility.
                self.assertEqual(state(path), path["initial_account_state"])
            net = Decimal(state(path)["cumulative_realized_pnl_usd"])
            self.assertEqual(Decimal(state(path)["equity_usd"]), Decimal(path["initial_account_state"]["equity_usd"]) + net)
            self.assertEqual(Decimal(state(path)["buying_power_usd"]), Decimal(state(path)["equity_usd"]))
            self.assertEqual(Decimal(path["sessions"][0]["runtime"]["session_gross_realized_pnl_usd"]),
                net + Decimal(state(path)["cumulative_fees_usd"]))

    def test_both_arms_have_identical_economics_when_gate_admits(self):
        paths = self.result["paths"]
        for control, selected in zip(paths[:12], paths[12:]):
            self.assertNotEqual(control["path_id"], selected["path_id"])
            self.assertEqual(control["cell_id"], selected["cell_id"])
            self.assertEqual({k: state(control)[k] for k in MONEY}, {k: state(selected)[k] for k in MONEY})
            for p in (control, selected):
                snapshot = p["sessions"][0]["runtime"]["reconciliation_snapshot"]
                self.assertEqual(snapshot["ledger"]["account"]["account_id"], p["path_id"])

    def test_original_causal_candidate_projection_and_new_opportunity_identity(self):
        for oid, item in self.prepared["items"].items():
            op = item["position"]["entry_input"]["window"]["opportunity"]
            self.assertEqual(op["panel_id"], a.ID)
            self.assertEqual(op["opportunity_id"], oid)
            candidate = item["candidates"][a.parent.daily.GENERAL_PROFILE_ID]
            self.assertEqual(candidate["price"], 8)
            self.assertEqual(candidate["relative_volume"], 10)
            self.assertFalse(candidate["has_fresh_news"])
            self.assertEqual(pd.Timestamp(candidate["timestamp"]).value, op["candidate_qualified_ts_ns"])

    def test_slot_changes_cannot_reseed_move_dates_or_alias_arms(self):
        original = self.prepared["paths"][0]["slots"][1]
        for key, value in (("seed_applied", True), ("trading_date", "2025-05-30"), ("session_index", True),
                           ("previous_session_id", "wrong"), ("arm", a.parent.ARMS[1]),
                           ("account_key", "small_account"), ("behavioral_horizon_seconds", 2)):
            slot = deepcopy(original)
            slot[key] = value
            slot = a.seal({k: v for k, v in slot.items() if k != "content_sha256"})
            with self.subTest(key=key), self.assertRaises((ValueError, KeyError)):
                a.validate_slot(slot)

    def test_previous_close_requires_same_arm_cell_and_immediate_date(self):
        slots = self.prepared["paths"][0]["slots"]
        previous = self.result["paths"][0]["sessions"][0]["close"]
        opening = a.opening_state(slots[1], previous, expected_previous_close_sha256=a.fingerprint(previous))
        self.assertEqual(opening, previous["account_state"])
        opening["positions"].append({"mutated": True})
        self.assertFalse(previous["account_state"]["positions"])
        for index in (1, 12):
            wrong = self.result["paths"][index]["sessions"][0]["close"]
            with self.assertRaisesRegex(ValueError, "chronology"):
                a.opening_state(slots[1], wrong, expected_previous_close_sha256=a.fingerprint(wrong))
        with self.assertRaisesRegex(ValueError, "chronology"):
            a.opening_state(slots[2], previous, expected_previous_close_sha256=a.fingerprint(previous))
        with self.assertRaisesRegex(ValueError, "no reseeding"):
            a.opening_state(slots[1])
        with self.assertRaises(ValueError):
            a.opening_state(slots[0], previous, expected_previous_close_sha256=a.fingerprint(previous))

    def test_ancestor_date_guards_and_old_entry_points_stay_frozen(self):
        slot = self.prepared["paths"][0]["slots"][0]
        with self.assertRaises((ValueError, KeyError)):
            a.accounts._validate_slot(slot)
        self.assertFalse(set(a.accounts.DATES).intersection(a.sources.DATES))
        a.sources.validate_registration(ROOT)

    def test_missing_extra_or_mutated_inventory_cannot_filter_plans(self):
        first = next(iter(self.execution["by_plan"]))
        for kind in ("missing", "extra", "recap", "mask", "decision", "source", "tape", "unavailable_payload"):
            value = deepcopy(self.execution)
            if kind == "missing": value["by_plan"].pop(first)
            elif kind == "extra": value["by_plan"]["invented-plan"] = value["by_plan"][first]
            elif kind == "recap": value["ross_action"] = "buy"
            elif kind == "mask": value["selection_mask"] = {}
            elif kind == "decision": value["by_plan"][first]["execution"]["source_decision"] = {}
            elif kind == "source": value["capture_manifest_sha256"] = "0" * 64
            elif kind == "tape": value["by_plan"][first]["execution"]["entry_tape"]["quote_records"][0]["ask_size"] += 1
            else: value["by_plan"][first]["input_status"] = "unavailable"
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                prepare(self.path, self.pins, value)

    def test_independent_inventory_and_result_commitments_required(self):
        with a.sources.SourceArchive(self.path, **self.pins) as archive:
            with self.assertRaises(ValueError):
                a.prepare_inputs(archive, self.execution, expected_execution_sha256="0" * 64)
            with self.assertRaises(ValueError):
                a.verify_replay(archive, self.execution, self.result, expected_execution_sha256=a.fingerprint(self.execution),
                                expected_result_sha256="0" * 64)

    def test_full_replay_is_reproducible(self):
        with a.sources.SourceArchive(self.path, **self.pins) as archive:
            verified = a.verify_replay(archive, self.execution, self.result,
                expected_execution_sha256=a.fingerprint(self.execution), expected_result_sha256=a.fingerprint(self.result))
        self.assertTrue(verified["verification_passed"])
        self.assertFalse(verified["independent_execution_engine"])

    def test_new_dates_across_dst_and_last_date_execute_and_carry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.zip"
            pins, execution = fixture(path, changes={f"dates/{d}.json": day_source(d) for d in (a.sources.DATES[3], a.sources.DATES[-1])})
            prepared = prepare(path, pins, execution)
            result = run_path(prepared)
        for i in (0, 3, 29):
            runtime = result["sessions"][i]["runtime"]
            self.assertIsNone(runtime["failure"])
            self.assertEqual(runtime["status"], "flat_complete")
            snapshot = runtime["reconciliation_snapshot"]
            self.assertEqual(snapshot["ledger"]["session_date"], a.sources.DATES[i])
        self.assertEqual(state(result)["equity_usd"], "30004.99")
        self.assertEqual(state(result, 29)["equity_usd"], "30014.95")

    def test_unavailable_early_plans_preserved_late_gate_changes_only_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.zip"
            pins, execution = fixture(path, changes={f"dates/{a.sources.DATES[0]}.json": day_source(ordinal=3)}, unavailable_ordinals=(1, 2))
            prepared = prepare(path, pins, execution)
            control, selected = run_path(prepared), run_path(prepared, 12)
        for value in (control, selected):
            refs = value["sessions"][0]["runtime"]["opportunity_dispositions"]
            self.assertEqual([r["disposition"] for r in refs[:2]], ["unavailable_input"] * 2)
            self.assertEqual(len(state(value)["unresolved_inputs"]), 2)
            self.assertEqual(state(value, 29), state(value))
        self.assertGreater(Decimal(state(control)["cumulative_fees_usd"]), 0)
        self.assertEqual(state(selected)["cumulative_fees_usd"], "0.00")
        self.assertEqual(state(selected)["equity_usd"], "30000.00")
        self.assertEqual(state(selected)["campaigns"], [])
        runtime = selected["sessions"][0]["runtime"]
        event = next(e for e in runtime["events"] if e["event_type"] == "opportunity_disposition")
        self.assertEqual(event["disposition"], "withheld_late_pullback")
        self.assertIsNone(event["order"])
        self.assertTrue(runtime["complete_streams_verified"])

    def test_unresolved_position_carries_without_invented_liquidation_or_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.zip"
            pins, execution = fixture(path, partial=True)
            prepared = prepare(path, pins, execution)
            result = run_path(prepared)
        initial = state(result)
        self.assertTrue(initial["positions"])
        self.assertIsNone(initial["equity_usd"])
        self.assertEqual(result["sessions"][0]["runtime"]["status"], "original_window_exhausted_with_unresolved_state")
        for i in range(1, 30):
            self.assertEqual(result["sessions"][i]["runtime"]["status"], "blocked_prior_state")
            self.assertEqual(state(result, i)["positions"], initial["positions"])
            self.assertEqual(state(result, i)["buying_power_usd"], initial["buying_power_usd"])
            self.assertEqual(state(result, i)["cumulative_fees_usd"], initial["cumulative_fees_usd"])

    def test_late_stream_corruption_retains_known_state_and_blocks_next_day(self):
        value = deepcopy(self.execution)
        record = next(iter(value["by_plan"].values()))["execution"]
        record["expected_streams"]["sip_transactions"]["sha256"] = "0" * 64
        result = run_path(prepare(self.path, self.pins, value))
        self.assertIsNotNone(result["sessions"][0]["runtime"]["failure"])
        self.assertTrue(state(result)["unresolved_inputs"])
        self.assertEqual(result["sessions"][1]["runtime"]["status"], "blocked_prior_state")
        self.assertEqual(state(result, 1)["buying_power_usd"], state(result)["buying_power_usd"])

    def test_late_withhold_cannot_hide_invalid_entry_or_exit_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.zip"
            pins, execution = fixture(path, changes={f"dates/{a.sources.DATES[0]}.json": day_source(ordinal=3)}, unavailable_ordinals=(1, 2))
            for field in ("entry_tape", "exit_tape"):
                changed = deepcopy(execution)
                value = next(r["execution"] for r in changed["by_plan"].values() if r["input_status"] == "available")
                value[field]["quote_request"]["trading_date"] = "2025-05-30"
                value[field + "_sha256"] = a.fingerprint(value[field])
                with self.subTest(field=field), self.assertRaises(ValueError):
                    prepare(path, pins, changed)

    def test_label_inside_carried_state_is_rejected(self):
        previous = deepcopy(self.result["paths"][0]["sessions"][0]["close"])
        previous["account_state"]["campaigns"].append({"transcript_text": "retrospective data"})
        previous = a.seal({k: v for k, v in previous.items() if k != "content_sha256"})
        with self.assertRaises(ValueError):
            a.opening_state(self.prepared["paths"][0]["slots"][1], previous,
                            expected_previous_close_sha256=a.fingerprint(previous))

    def test_no_fresh_quote_at_stress_arrival_means_no_fill_or_fee(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.zip"
            pins, execution = fixture(path, stress_quotes=False)
            prepared = prepare(path, pins, execution)
            index = next(i for i, p in enumerate(prepared["paths"]) if p["slots"][0]["execution_scenario_id"] == "l1-stress-v0.1")
            result = run_path(prepared, index)
        self.assertEqual(state(result), result["initial_account_state"])
        self.assertEqual(result["sessions"][0]["runtime"]["status"], "flat_complete")
        self.assertTrue(result["sessions"][0]["runtime"]["complete_streams_verified"])

    def test_small_profile_executes_with_own_seed_on_qualifying_price(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.zip"
            pins, execution = fixture(path, changes={f"dates/{a.sources.DATES[0]}.json": small_price_day()}, price_scale=0.5)
            prepared = prepare(path, pins, execution)
            for index in (6, 7, 18, 19):
                result = run_path(prepared, index)
                runtime = result["sessions"][0]["runtime"]
                self.assertEqual(result["initial_account_state"]["equity_usd"], "2000.00")
                self.assertEqual(runtime["status"], "flat_complete")
                self.assertIsNone(runtime["failure"])
                self.assertGreater(Decimal(state(result)["cumulative_fees_usd"]), 0)
                self.assertNotEqual(state(result)["equity_usd"], "2000.00")
                self.assertEqual(state(result, 29), state(result))

    def test_evaluation_provider_and_brokerage_gates_remain_closed(self):
        for key in ("new_panel_historical_execution_enabled", "financial_evaluation_enabled", "provider_access_enabled",
                    "brokerage_orders_enabled", "policy_promotion_eligible", "discretionary_strategy_integrated",
                    "provider_origin_authenticated", "historical_execution_inputs_authenticated"):
            self.assertFalse(self.result[key])


class RegistrationTests(unittest.TestCase):
    def test_registration_and_exact_unarmed_four_call_preparation(self):
        saved = a.validate_registration(ROOT)
        plan = a.provider_check_preparation(ROOT)
        self.assertEqual(saved["parent_registration_sha256"], a.PARENT_SHA)
        self.assertEqual(len(plan["requests"]), 4)
        self.assertEqual(plan["authorized_calls_now"], 0)
        self.assertEqual(plan["incremental_spend_authorized_usd"], "0.00")
        self.assertFalse(plan["provider_transport_implemented"])
        self.assertFalse(plan["automatic_retries"])
        for item in plan["requests"]:
            self.assertEqual(item["request_sha256"], a.fingerprint(item["request"]))


if __name__ == "__main__":
    unittest.main()
