from copy import deepcopy
from decimal import localcontext
from pathlib import Path
import ast
import tempfile
import unittest
from unittest.mock import patch

from momentumbot.research import sealed_historical_account_residual_exit_v01 as m
from tests.test_sealed_historical_management_fill_feedback_v01 import fixture as entry_fixture, record, BASE, SECOND
from tests.test_sealed_historical_account_exit_waiting_v01 import repin_tape, submit, run_fixture as parent_fixture, waiting_program
from tests.test_sealed_historical_account_scheduler_v01 import spec, repin, attach
from tests.test_sealed_historical_account_continuity_v01 import case_programs, empty_program
from tests.test_sealed_historical_account_replay_v01 import fixture
import verify_sealed_historical_account_residual_exit_v01 as checker

ROOT = Path(__file__).resolve().parents[1]
MS = 1_000_000


def add_replacement_quotes(tape, quantity, scenario, *, delayed=False, expire=False):
    if expire:
        return
    policy, _ = m.feedback.SCENARIOS[scenario]
    start = 3 * SECOND + (200 * MS if delayed else -1)
    arrival = 3 * SECOND + (220 * MS if delayed else 0) + policy.decision_to_arrival_ms * MS - 10 * MS
    for at in (start, arrival):
        q = deepcopy(tape["quote_records"][-1])
        q.update(ts_recv_ns=BASE + at, bid_px_nanos=9_000_000_000, ask_px_nanos=9_010_000_000,
            bid_size=max(1, int(m.Decimal(quantity) / policy.displayed_size_participation)))
        tape["quote_records"].append(q)
    repin_tape(tape)


def arguments(*, first_fill=2, replacement_fill=8, scenario="l1-conservative-v0.1", delayed=False, expire=False):
    args = entry_fixture(target_fill=0, final_fill=first_fill, scenario=scenario)
    add_replacement_quotes(args["tape"], replacement_fill, scenario, delayed=delayed, expire=expire)
    args["expected_tape_sha256"] = repin_tape(args["tape"])
    return args


def first_terminal(args, cls=m._Management):
    engine = cls(**args)
    intent = engine.observe_trade(record(2 * SECOND, 8))
    order = submit(engine, args, intent)
    return engine, intent, order


def residual_program(*, first_fill=2, replacement_fill=8, scenario="l1-conservative-v0.1", account="main_account", delayed=False, expire=False):
    quantity = 10 if account == "main_account" else 2
    first_fill = min(first_fill, quantity - 1)
    value = spec(quantity=quantity, final_fill=first_fill, target_fill=0, scenario=scenario, account=account,
        bars=[], trades=[record(2 * SECOND, 8), record(3 * SECOND, 11, 1),
            record(3 * SECOND + 100 * MS, 11, 2), record(3 * SECOND + 220 * MS, 11, 3), record(4 * SECOND, 8, 4)])
    add_replacement_quotes(value["exit_tape"], replacement_fill, scenario, delayed=delayed, expire=expire)
    return attach(empty_program(scenario=scenario, account=account), 0, repin(value))


def run_fixture(p):
    program, manifest, items = fixture(p)
    dependencies = {d["next_session_id"]: d for d in manifest["carry_dependencies"]}
    initial = m.accounts.account_state_input(program["slots"][0])["account_state"]
    opening, previous, sessions = initial, None, []
    with localcontext() as context:
        context.prec = 60
        for slot, source in zip(program["slots"], program["sessions"]):
            pair = m._session(slot, source, opening, previous, lambda oid: deepcopy(items[oid]), dependencies.get(slot["session_id"]))
            sessions.append(pair)
            opening, previous = deepcopy(pair["close"]["account_state"]), pair["close"]["content_sha256"]
    result = m.seal({"contract_id": m.parent.CONTRACT_ID, "artifact_type": "original_historical_account_path",
        "path_id": program["path_id"], "program_content_sha256": program["content_sha256"],
        "initial_account_state": initial, "seed_application_count": 1, "session_count": 30,
        "sessions": sessions, "last_close_content_sha256": previous,
        "path_complete": all(s["runtime"]["status"] == "flat_complete" for s in sessions), **m.RUNTIME_BOUNDARY})
    def resolve(oid):
        s = items[oid]["position"]
        return {"window": s["entry_input"]["window"], "trades": s["trades"], "bars": s["bars"], "tape": s["exit_tape"]}
    return program, result, manifest, resolve


class ResidualManagementTests(unittest.TestCase):
    def test_partial_terminal_ack_arms_without_resetting_attempt_or_liquidity(self):
        args = arguments()
        engine, intent, order = first_terminal(args)
        engine.settle(order["cancel_ack_ts_ns"])
        self.assertTrue(engine._full_attempted)
        self.assertEqual((engine._remaining, engine._residual_attempts, len(engine._used_liquidity)), (8, 0, 1))
        self.assertEqual(engine._residual["context"]["prior_submission_intent"], intent)
        self.assertEqual(engine._residual_log[0]["event_type"], "residual_ready")
        self.assertFalse(engine.snapshot()["pending_order"])

    def test_no_replacement_before_or_on_equal_time_ack_print(self):
        args = arguments()
        engine, _, order = first_terminal(args)
        at = order["cancel_ack_ts_ns"] - BASE
        self.assertIsNone(engine.observe_trade(record(at - 1, 8, 1)))
        self.assertIsNone(engine.observe_trade(record(at, 8, 2)))
        self.assertIsNone(engine._residual)
        engine.settle(order["cancel_ack_ts_ns"])
        with self.assertRaisesRegex(ValueError, "clock reversed"):
            engine.observe_trade(record(at, 8, 3))

    def test_first_later_eligible_print_uses_only_remainder_and_closes(self):
        for scenario in m.feedback.SCENARIOS:
            args = arguments(scenario=scenario)
            engine, original, order = first_terminal(args)
            engine.settle(order["cancel_ack_ts_ns"])
            self.assertIsNone(engine.observe_trade(record(2800 * MS, 8, 1, ["Z"])))
            intent = engine.observe_trade(record(3 * SECOND, 11, 2, ["I"]))
            self.assertEqual((intent["quantity"], intent["reason"]), (8, "initial_stop"))
            self.assertEqual(intent["residual_exit"]["prior_submission_intent"], original)
            second = submit(engine, args, intent)
            self.assertNotEqual(order["order_id"], second["order_id"])
            self.assertEqual(engine._residual_attempts, 1)
            engine.settle(second["cancel_ack_ts_ns"])
            self.assertEqual((engine._remaining, len(engine._used_liquidity)), (0, 2))

    def test_unfilled_original_has_no_consumed_liquidity_but_valid_authority(self):
        args = arguments(first_fill=0, replacement_fill=10)
        engine, _, order = first_terminal(args)
        engine.settle(order["cancel_ack_ts_ns"])
        self.assertEqual((engine._remaining, len(engine._used_liquidity)), (10, 0))
        intent = engine.observe_trade(record(3 * SECOND, 11, 1))
        self.assertEqual(intent["quantity"], 10)
        second = submit(engine, args, intent)
        engine.settle(second["cancel_ack_ts_ns"])
        self.assertEqual(engine._remaining, 0)

    def test_second_partial_or_unfilled_exit_exhausts_budget_without_third_attempt(self):
        for amount in (0, 2):
            args = arguments(replacement_fill=amount)
            engine, _, order = first_terminal(args)
            engine.settle(order["cancel_ack_ts_ns"])
            second = submit(engine, args, engine.observe_trade(record(3 * SECOND, 8, 1)))
            engine.settle(second["cancel_ack_ts_ns"])
            self.assertEqual(engine._remaining, 8 - amount)
            self.assertEqual(engine._residual_log[-1]["event_type"], "residual_budget_exhausted")
            self.assertIsNone(engine.observe_trade(record(4 * SECOND, 8, 2)))
            self.assertEqual(sum(e["event_type"] == "sell_submitted" for e in engine._events), 2)

    def test_fully_filled_terminal_never_arms_residual(self):
        args = arguments(first_fill=10)
        engine, _, order = first_terminal(args)
        engine.settle(order["cancel_ack_ts_ns"])
        self.assertIsNone(engine._residual)
        self.assertEqual(engine._residual_log, [])

    def test_partial_target_does_not_receive_replacement_authority(self):
        args = entry_fixture(target_fill=2)
        engine = m._Management(**args)
        order = submit(engine, args, engine.observe_trade(record(SECOND, 12)))
        engine.settle(order["cancel_ack_ts_ns"])
        self.assertIsNone(engine._residual)
        self.assertEqual(engine._residual_log, [])

    def test_missing_reference_waits_without_spending_residual_budget(self):
        args = arguments(delayed=True)
        engine, _, order = first_terminal(args)
        engine.settle(order["cancel_ack_ts_ns"])
        origin = engine.observe_trade(record(3 * SECOND, 11, 1))
        self.assertIsNone(submit(engine, args, origin))
        self.assertEqual((engine._residual_attempts, engine.snapshot()["reserved_sell_quantity"]), (0, 0))
        self.assertIsNone(engine.observe_trade(record(3100 * MS, 11, 2)))
        intent = engine.observe_trade(record(3220 * MS, 11, 3))
        self.assertEqual(intent["waiting_signal"], origin)
        self.assertEqual(intent["residual_exit"], origin["residual_exit"])
        second = submit(engine, args, intent)
        engine.settle(second["cancel_ack_ts_ns"])
        self.assertEqual(engine._remaining, 0)

    def test_wait_expiry_preserves_unsubmitted_remainder(self):
        args = arguments(expire=True)
        engine, _, order = first_terminal(args)
        engine.settle(order["cancel_ack_ts_ns"])
        intent = engine.observe_trade(record(3 * SECOND, 8, 1))
        self.assertIsNone(submit(engine, args, intent))
        engine.settle(args["window"]["end_ns"] - 1)
        self.assertEqual(engine.snapshot()["outstanding_intent"], intent)
        self.assertEqual((engine._remaining, engine._residual_attempts), (8, 0))

    def test_no_later_print_expires_authority_without_order(self):
        args = arguments()
        engine, _, order = first_terminal(args)
        engine.settle(order["cancel_ack_ts_ns"])
        engine.settle(args["window"]["end_ns"] - m.TAIL_NS - 1)
        self.assertFalse(engine._residual["expired"])
        engine.settle(args["window"]["end_ns"] - m.TAIL_NS)
        self.assertTrue(engine._residual["expired"])
        self.assertEqual(engine._residual_log[-1]["event_type"], "residual_expired")
        self.assertIsNone(engine._intent)

    def test_stop_can_supersede_prior_red_terminal_for_remainder(self):
        args = arguments()
        engine = m._Management(**args)
        engine._latched = "first_red_candle"
        order = submit(engine, args, engine.observe_trade(record(2 * SECOND, 11)))
        engine.settle(order["cancel_ack_ts_ns"])
        intent = engine.observe_trade(record(3 * SECOND, 8, 1))
        self.assertEqual(intent["reason"], "initial_stop")
        self.assertEqual(intent["residual_exit"]["prior_submission_intent"]["reason"], "first_red_candle")

    def test_wrong_tape_rejected_without_spending_attempt(self):
        args = arguments()
        engine, _, order = first_terminal(args)
        engine.settle(order["cancel_ack_ts_ns"])
        intent = engine.observe_trade(record(3 * SECOND, 8, 1))
        old = engine.snapshot()
        bad = deepcopy(args["tape"])
        bad["quote_records"][0]["bid_size"] += 1
        with self.assertRaises(ValueError):
            engine.submit_intent(intent, tape=bad, expected_tape_sha256=repin_tape(bad))
        self.assertEqual(engine.snapshot(), old)
        self.assertEqual(engine._residual_attempts, 0)

    def test_consumed_liquidity_is_not_reset_or_reused(self):
        args = arguments()
        engine, _, order = first_terminal(args)
        engine.settle(order["cancel_ack_ts_ns"])
        intent = engine.observe_trade(record(3 * SECOND, 8, 1))
        engine._used_liquidity.add((m.canonical_fingerprint(args["tape"]["quote_request"]), 7))
        with self.assertRaisesRegex(ValueError, "already consumed"):
            submit(engine, args, intent)
        self.assertEqual(engine._residual_attempts, 0)

    def test_unknown_status_is_a_failure_not_permission_to_retry(self):
        args = arguments()
        args["tape"]["status_records"].append({"symbol": "SYNTHETIC", "ts_recv_ns": BASE + 2800 * MS,
            "action": 1, "is_trading": "~"})
        args["expected_tape_sha256"] = repin_tape(args["tape"])
        engine, _, order = first_terminal(args)
        engine.settle(order["cancel_ack_ts_ns"])
        intent = engine.observe_trade(record(3 * SECOND, 8, 1))
        with self.assertRaisesRegex(ValueError, "quote/status input unavailable"):
            submit(engine, args, intent)
        self.assertEqual(engine._residual_attempts, 0)
        self.assertIsNone(engine._waiting)

    def test_known_halt_waits_without_consuming_additional_order(self):
        args = arguments()
        args["tape"]["status_records"].append({"symbol": "SYNTHETIC", "ts_recv_ns": BASE + 2800 * MS,
            "action": 1, "is_trading": "N"})
        args["expected_tape_sha256"] = repin_tape(args["tape"])
        engine, _, order = first_terminal(args)
        engine.settle(order["cancel_ack_ts_ns"])
        self.assertIsNone(submit(engine, args, engine.observe_trade(record(3 * SECOND, 8, 1))))
        self.assertEqual(engine._residual_attempts, 0)
        self.assertIsNotNone(engine._waiting)


class ResidualAccountAndIndependentTests(unittest.TestCase):
    def checked_fixture(self, **kwargs):
        p = residual_program(**kwargs)
        program, result, manifest, resolve = run_fixture(p)
        checker.verify_path(program, result, manifest)
        checker.verify_parent_prefix(parent_fixture(p)[1], result)
        runtime = result["sessions"][0]["runtime"]
        counts = checker.verify_residual(runtime, resolve)
        checker.verify_waiting(runtime, resolve)
        return runtime, resolve, counts

    def test_confirmed_residual_close_releases_capacity_and_keeps_audit(self):
        for scenario in m.feedback.SCENARIOS:
            for account in ("main_account", "small_account"):
                runtime, _, counts = self.checked_fixture(scenario=scenario, account=account)
                self.assertEqual(runtime["status"], "flat_complete")
                self.assertIsNone(runtime["reconciliation_snapshot"]["management"])
                self.assertEqual((counts["residual_ready"], counts["residual_submissions"]), (1, 1))

    def test_stale_replacement_waits_then_closes_independently(self):
        for scenario in m.feedback.SCENARIOS:
            runtime, _, counts = self.checked_fixture(scenario=scenario, delayed=True)
            self.assertEqual(runtime["status"], "flat_complete")
            self.assertEqual(counts["residual_submissions"], 1)

    def test_second_remainder_or_expired_wait_preserves_all_later_blocked_slots(self):
        for options in ({"replacement_fill": 2}, {"replacement_fill": 0}, {"expire": True}):
            p = residual_program(**options)
            program, result, manifest, resolve = run_fixture(p)
            checker.verify_path(program, result, manifest)
            runtime = result["sessions"][0]["runtime"]
            checker.verify_residual(runtime, resolve)
            checker.verify_waiting(runtime, resolve)
            self.assertEqual(runtime["status"], "original_window_exhausted_with_unresolved_state")
            first = result["sessions"][0]["close"]["account_state"]
            for pair in result["sessions"][1:]:
                self.assertEqual(pair["runtime"]["status"], "blocked_prior_state")
                self.assertEqual(pair["close"]["account_state"]["positions"], first["positions"])

    def test_no_residual_paths_are_byte_identical_to_waiting_parent(self):
        cases = list(case_programs().items()) + [("waiting", waiting_program()), ("waiting-expire", waiting_program(expire=True))]
        for name, p in cases:
            if name == "omitted":
                continue
            old = parent_fixture(p)[1]
            if any(pair["runtime"]["reconciliation_snapshot"] and pair["runtime"]["reconciliation_snapshot"]["management"]
                and pair["runtime"]["reconciliation_snapshot"]["management"]["full_exit_attempted"]
                and pair["runtime"]["reconciliation_snapshot"]["management"]["remaining_quantity"] for pair in old["sessions"]):
                continue
            with self.subTest(name=name):
                program, result, manifest, _ = run_fixture(p)
                self.assertEqual(result, old)
                checker.verify_path(program, result, manifest)

    def test_removed_residual_audit_cannot_hide_second_order(self):
        runtime, resolve, _ = self.checked_fixture()
        runtime["reconciliation_snapshot"].pop("exit_residual_events")
        with self.assertRaisesRegex(ValueError, "authority omitted"):
            checker.verify_residual(runtime, resolve)

    def test_mutated_ack_remaining_count_and_first_print_are_rejected(self):
        runtime, resolve, _ = self.checked_fixture()
        for field, value in (("remaining_quantity", 9), ("residual_attempts", 1), ("timestamp_ns", BASE + 3 * SECOND)):
            bad = deepcopy(runtime)
            event = bad["reconciliation_snapshot"]["exit_residual_events"][0]
            event[field] = value
            event.pop("content_sha256")
            bad["reconciliation_snapshot"]["exit_residual_events"][0] = m.seal(event)
            with self.assertRaises(ValueError):
                checker.verify_residual(bad, resolve)

    def test_earlier_eligible_source_print_cannot_be_omitted(self):
        runtime, resolve, _ = self.checked_fixture()
        def earlier(oid):
            data = deepcopy(resolve(oid))
            data["trades"][1] = record(2800 * MS, 8, 1)
            return data
        with self.assertRaisesRegex(ValueError, "first eligible"):
            checker.verify_residual(runtime, earlier)

    def test_no_post_ack_print_records_expiry_and_preserves_shares(self):
        p = residual_program()
        value = p["sessions"][0]["opportunities"][0]["position"]
        value["trades"] = value["trades"][:1]
        repin(value)
        program, result, manifest, resolve = run_fixture(p)
        checker.verify_path(program, result, manifest)
        runtime = result["sessions"][0]["runtime"]
        counts = checker.verify_residual(runtime, resolve)
        self.assertEqual((counts["residual_ready"], counts["residual_expiries"], counts["residual_proposals"]), (1, 1, 0))
        self.assertEqual(runtime["reconciliation_snapshot"]["management"]["remaining_quantity"], 8)

    def test_original_wait_and_residual_wait_remain_separate_bound_episodes(self):
        p = residual_program(delayed=True)
        value = p["sessions"][0]["opportunities"][0]["position"]
        value["exit_tape"]["quote_records"][4]["ts_recv_ns"] = BASE + 2200 * MS
        value["exit_tape"]["quote_records"][5]["ts_recv_ns"] = BASE + 2310 * MS
        value["trades"] = [record(2 * SECOND, 8), record(2220 * MS, 8, 1),
            record(3 * SECOND, 11, 2), record(3220 * MS, 11, 3)]
        repin(value)
        program, result, manifest, resolve = run_fixture(p)
        checker.verify_path(program, result, manifest)
        checker.verify_parent_prefix(parent_fixture(p)[1], result)
        runtime = result["sessions"][0]["runtime"]
        self.assertEqual(checker.verify_waiting(runtime, resolve)["wait_submissions"], 2)
        self.assertEqual(checker.verify_residual(runtime, resolve)["residual_submissions"], 1)

    def test_rehashed_third_terminal_order_exceeds_independent_budget(self):
        p = residual_program(replacement_fill=2)
        program, result, manifest, _ = run_fixture(p)
        runtime = result["sessions"][0]["runtime"]
        last = deepcopy(next(e for e in reversed(runtime["events"]) if e["event_type"] == "sell_submitted"))
        order = last["order"]
        shift = BASE + 4 * SECOND - order["decision_ts_ns"]
        for key in ("decision_ts_ns", "arrival_ts_ns", "cancel_requested_ts_ns", "cancel_ack_ts_ns"):
            order[key] += shift
        order.update(quantity=6, order_id="forged-third-terminal")
        last.update(at_ns=BASE + 4 * SECOND, sequence=len(runtime["events"]), previous_event_sha256=runtime["events"][-1]["content_sha256"])
        last.pop("content_sha256")
        runtime["events"].append(m.seal(last))
        source = checker.source_for_events(program["sessions"][0], program["slots"][0],
            {b["opportunity_id"]: b for b in manifest["opportunities"]})
        with self.assertRaisesRegex(ValueError, "terminal attempt budget"):
            checker.verify_events(source, runtime)

    def test_rehashed_invalid_cancellation_context_is_rejected(self):
        runtime, resolve, _ = self.checked_fixture()
        event = runtime["reconciliation_snapshot"]["exit_residual_events"][0]
        context = event["context"]
        ack = context["cancel_acknowledgement"]
        ack["cancelled_quantity"] += 1
        ack.pop("content_sha256")
        context["cancel_acknowledgement"] = m.seal(ack)
        context.pop("content_sha256")
        event["context"] = m.seal(context)
        event.pop("content_sha256")
        runtime["reconciliation_snapshot"]["exit_residual_events"][0] = m.seal(event)
        with self.assertRaisesRegex(ValueError, "cancellation witness"):
            checker.verify_residual(runtime, resolve)

    def test_changed_parent_prefix_is_rejected(self):
        p = residual_program()
        old = parent_fixture(p)[1]
        result = run_fixture(p)[1]
        result["sessions"][0]["runtime"]["events"][0]["order"]["quantity"] += 1
        with self.assertRaisesRegex(ValueError, "parent event prefix"):
            checker.verify_parent_prefix(old, result)

    def test_residual_release_can_change_later_capacity_decision_not_earlier_prefix(self):
        p = attach(residual_program(), 0, spec("B", offset=4 * SECOND, final_price="11"))
        old = parent_fixture(p)[1]
        program, result, manifest, resolve = run_fixture(p)
        checker.verify_path(program, result, manifest)
        checker.verify_parent_prefix(old, result)
        runtime = result["sessions"][0]["runtime"]
        checker.verify_residual(runtime, resolve)
        checker.verify_waiting(runtime, resolve)
        before = [e["disposition"] for e in old["sessions"][0]["runtime"]["events"] if e["event_type"] == "opportunity_disposition"]
        after = [e["disposition"] for e in runtime["events"] if e["event_type"] == "opportunity_disposition"]
        self.assertEqual(before, ["entry_submitted", "blocked_capacity"])
        self.assertEqual(after, ["entry_submitted", "entry_submitted"])

    def test_acknowledged_authority_cannot_be_omitted_when_no_replacement_fills(self):
        runtime, resolve, _ = self.checked_fixture(replacement_fill=0)
        runtime["reconciliation_snapshot"].pop("exit_residual_events")
        with self.assertRaisesRegex(ValueError, "authority omitted"):
            checker.verify_residual(runtime, resolve)

    def test_registration_and_original_reader_are_required(self):
        with patch.object(m, "verify_bundle", return_value={"freeze_content_sha256": "pin"}):
            with self.assertRaisesRegex(ValueError, "registration pin"):
                m.replay_panel(ROOT, object(), expected_registration_sha256="wrong")
            with self.assertRaisesRegex(ValueError, "original source reader"):
                m.replay_panel(ROOT, object(), expected_registration_sha256="pin")

    def test_registration_is_metadata_only_and_parent_remains_frozen(self):
        with patch.object(m.binding, "OriginalSources", side_effect=AssertionError("metadata only")):
            self.assertTrue(m.verify_bundle(ROOT, ROOT / m.OUTPUT_PATH)["verification_passed"])
        self.assertEqual(m.MAX_RESIDUAL_ATTEMPTS, 1)
        self.assertFalse(m.RUNTIME_BOUNDARY["financial_metrics_eligible"])

    def test_mutated_parent_or_child_invalidates_registration(self):
        original = m.file_sha
        for target in (m.waiting.MODULE_PATH, m.MODULE_PATH):
            with patch.object(m, "file_sha", side_effect=lambda p: "0" * 64 if p == ROOT / target else original(p)):
                with self.assertRaises(ValueError):
                    m.validate_registration(ROOT)

    def test_frozen_finisher_arithmetic_is_unchanged(self):
        def node(path, name):
            return next(n for n in ast.parse((ROOT / path).read_text()).body if isinstance(n, ast.FunctionDef) and n.name == name)
        self.assertEqual(ast.dump(node(m.MODULE_PATH, "_session")), ast.dump(node(m.waiting.MODULE_PATH, "_session")))

    def test_independent_chronology_delta_is_only_registered_terminal_ceiling(self):
        path = ROOT / "scripts/verify_sealed_historical_account_continuity_v01.py"
        original = path.read_text().split("def verify_events(source, runtime):")[1].split("\ndef verify_vector")[0]
        expected = ("def verify_events(source, runtime):" + original).replace(
            "exit_orders, terminal, targets, used_liquidity = {}, set(), set(), set()",
            "exit_orders, terminal, targets, used_liquidity = {}, {}, set(), set()").replace(
            'require(oid not in terminal and order["quantity"] == quantity, "terminal attempt retried or wrong quantity")\n                terminal.add(oid)',
            'require(terminal.get(oid, 0) < 2 and order["quantity"] == quantity, "terminal attempt budget or quantity differs")\n                terminal[oid] = terminal.get(oid, 0) + 1')
        actual = next(n for n in ast.parse((ROOT / m.CHECKER_PATH).read_text()).body if isinstance(n, ast.FunctionDef) and n.name == "verify_events")
        self.assertEqual(ast.dump(actual), ast.dump(ast.parse(expected).body[0]))

    def test_independent_account_checks_are_unchanged_except_parent_namespace(self):
        text = (ROOT / "scripts/verify_sealed_historical_account_replay_v01.py").read_text()
        original = "def verify_path(program, result, manifest):" + text.split("def verify_path(program, result, manifest):")[1].split("\ndef verify(root, runtime_root")[0]
        expected = original.replace('== ID, "contract identity differs"', '== parent.ID, "contract identity differs"').replace('== ID and runtime["path_id"]', '== parent.ID and runtime["path_id"]')
        actual = next(n for n in ast.parse((ROOT / m.CHECKER_PATH).read_text()).body if isinstance(n, ast.FunctionDef) and n.name == "verify_path")
        self.assertEqual(ast.dump(actual), ast.dump(ast.parse(expected).body[0]))

    def test_runtime_output_is_external_and_write_once(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "residual"
            m.write_files(ROOT, output, {"synthetic.json": b"{}\n"})
            with self.assertRaises(FileExistsError):
                m.write_files(ROOT, output, {"synthetic.json": b"changed\n"})
            self.assertEqual((output / "synthetic.json").read_bytes(), b"{}\n")


if __name__ == "__main__":
    unittest.main()
