"""Deterministic mechanical evidence; no historical labels or prices."""
from copy import deepcopy
from decimal import localcontext
from pathlib import Path
import ast
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from momentumbot.research import sealed_historical_account_terminal_continuation_v01 as m
from tests.test_sealed_historical_account_residual_exit_v01 import arguments, first_terminal, residual_program, run_fixture as parent_fixture
from tests.test_sealed_historical_account_replay_v01 import fixture
from tests.test_sealed_historical_account_scheduler_v01 import repin, spec, attach
import verify_sealed_historical_account_terminal_continuation_v01 as checker
from tests.test_sealed_historical_account_exit_waiting_v01 import repin_tape, submit
from tests.test_sealed_historical_management_fill_feedback_v01 import record, BASE, SECOND

MS = 1_000_000
ROOT = Path(__file__).resolve().parents[1]


def continuation_arguments(*, fills=(2, 2, 3, 3), scenario="l1-conservative-v0.1", delayed=False):
    args = arguments(first_fill=fills[0], replacement_fill=fills[1], scenario=scenario)
    policy, _ = m.feedback.SCENARIOS[scenario]
    for number, quantity in enumerate(fills[2:], 4):
        delay = 220 * MS if delayed and number == 4 else 0
        for at in (number * SECOND + delay - 1,
                   number * SECOND + delay + policy.decision_to_arrival_ms * MS - 10 * MS):
            q = deepcopy(args["tape"]["quote_records"][-1])
            q.update(ts_recv_ns=BASE + at, bid_size=max(1, int(m.parent.Decimal(quantity) / policy.displayed_size_participation)))
            args["tape"]["quote_records"].append(q)
    args["expected_tape_sha256"] = repin_tape(args["tape"])
    return args


def two_terminals(args, cls=m.Management):
    engine, _, order = first_terminal(args, cls)
    engine.settle(order["cancel_ack_ts_ns"])
    intent = engine.observe_trade(record(3 * SECOND, 8, 1))
    second = submit(engine, args, intent)
    engine.settle(second["cancel_ack_ts_ns"])
    return engine, intent, second


class TerminalContinuationTests(unittest.TestCase):
    def test_partial_target_never_arms_continuation(self):
        args = continuation_arguments()
        engine = m.Management(**args)
        intent = engine.observe_trade(record(SECOND, 12))
        order = submit(engine, args, intent)
        engine.settle(order["cancel_ack_ts_ns"])
        self.assertIsNone(engine._continuation)
        self.assertEqual(engine._continuation_log, [])
        self.assertEqual(engine._residual_log, [])

    def test_stop_supersedes_risk_latch_on_continuation_print(self):
        args = continuation_arguments()
        engine = m.Management(**args)
        # The frozen account reducer installs this latch on a confirmed lock.
        engine._latched = "account_risk_flatten"
        order = submit(engine, args, engine.observe_trade(record(2 * SECOND, 11)))
        engine.settle(order["cancel_ack_ts_ns"])
        second = engine.observe_trade(record(3 * SECOND, 11, 1))
        self.assertEqual(second["reason"], "account_risk_flatten")
        order = submit(engine, args, second)
        engine.settle(order["cancel_ack_ts_ns"])
        third = engine.observe_trade(record(4 * SECOND, 8, 2))
        self.assertEqual(third["reason"], "initial_stop")

    def test_consumed_third_order_liquidity_cannot_be_reused(self):
        args = continuation_arguments()
        engine, _, _ = two_terminals(args)
        engine._used_liquidity.add((m.fingerprint(args["tape"]["quote_request"]), 9))
        intent = engine.observe_trade(record(4 * SECOND, 8, 2))
        before = engine.snapshot()
        with self.assertRaisesRegex(ValueError, "already consumed"):
            submit(engine, args, intent)
        self.assertEqual(engine.snapshot(), before)
        self.assertEqual(engine._continuation_attempts, 0)

    def test_third_order_unknown_status_fails_and_known_halt_waits(self):
        for status in ("~", "N"):
            args = continuation_arguments()
            args["tape"]["status_records"].append({"symbol": "SYNTHETIC", "ts_recv_ns": BASE + 3800 * MS,
                "action": 1, "is_trading": status})
            args["expected_tape_sha256"] = repin_tape(args["tape"])
            engine, _, _ = two_terminals(args)
            intent = engine.observe_trade(record(4 * SECOND, 8, 2))
            if status == "~":
                with self.assertRaisesRegex(ValueError, "quote/status input unavailable"):
                    submit(engine, args, intent)
                self.assertIsNone(engine._waiting)
            else:
                self.assertIsNone(submit(engine, args, intent))
                self.assertIsNotNone(engine._waiting)
            self.assertEqual(engine._continuation_attempts, 0)

    def test_third_and_fourth_close_exact_remainder_across_scenarios(self):
        for scenario in m.feedback.SCENARIOS:
            with self.subTest(scenario=scenario):
                args = continuation_arguments(scenario=scenario)
                engine, second_intent, second = two_terminals(args)
                self.assertEqual((engine._remaining, engine._residual_attempts), (6, 1))
                self.assertEqual(engine._continuation["context"]["prior_submission_intent_content_sha256"], second_intent["content_sha256"])
                for number, remaining in ((4, 3), (5, 0)):
                    intent = engine.observe_trade(record(number * SECOND, 11, number - 2))
                    self.assertEqual(intent["terminal_continuation"]["terminal_attempt_number"], number - 1)
                    order = submit(engine, args, intent)
                    engine.settle(order["cancel_ack_ts_ns"])
                    self.assertEqual(engine._remaining, remaining)
                self.assertEqual((engine._continuation_attempts, len(engine._used_liquidity)), (2, 4))
                self.assertIsNone(engine._continuation)
                self.assertTrue(engine._full_attempted)
                self.assertEqual(engine._residual_log[-1]["event_type"], "residual_budget_exhausted")
                self.assertEqual(len([e for e in engine._residual_log if e["event_type"] == "residual_budget_exhausted"]), 1)

    def test_original_two_order_prefix_is_exact(self):
        args = continuation_arguments()
        before, _, _ = two_terminals(args, m.parent._Management)
        after, _, _ = two_terminals(args)
        self.assertEqual(before.snapshot(), after.snapshot())
        self.assertEqual(before._residual_log, after._residual_log)
        self.assertEqual(before._used_liquidity, after._used_liquidity)
        self.assertEqual(len(after._continuation_log), 1)

    def test_equal_ack_print_and_ineligible_print_cannot_replace(self):
        args = continuation_arguments()
        engine, _, _ = two_terminals(args)
        order = submit(engine, args, engine.observe_trade(record(4 * SECOND, 8, 2)))
        at = order["cancel_ack_ts_ns"] - BASE
        self.assertIsNone(engine.observe_trade(record(at - 1, 8, 3)))
        self.assertIsNone(engine.observe_trade(record(at, 8, 4)))
        engine.settle(order["cancel_ack_ts_ns"])
        self.assertIsNone(engine.observe_trade(record(at + 1, 8, 5, ["Z"])))
        intent = engine.observe_trade(record(5 * SECOND, 8, 6))
        self.assertEqual(intent["terminal_continuation"]["terminal_attempt_number"], 4)

    def test_unfilled_attempts_have_finite_source_window_and_flat_context_size(self):
        args = continuation_arguments(fills=(0,) * 20)
        engine, _, _ = two_terminals(args)
        for number in range(4, 22):
            intent = engine.observe_trade(record(number * SECOND, 8, number - 2))
            context = intent["terminal_continuation"]
            self.assertNotIn("prior_submission_intent", context)
            self.assertEqual(len(context), 6)
            order = submit(engine, args, intent)
            engine.settle(order["cancel_ack_ts_ns"])
        self.assertEqual((engine._remaining, engine._continuation_attempts, len(engine._used_liquidity)), (10, 18, 0))
        at = engine._window["end_ns"] - m.TAIL_NS
        self.assertIsNone(engine.observe_trade(record(at - BASE, 8, 20)))
        self.assertTrue(engine._continuation["expired"])
        self.assertEqual(engine._continuation_log[-1]["event_type"], "continuation_expired")
        self.assertEqual(engine._remaining, 10)

    def test_missing_reference_waits_without_spending_attempt(self):
        args = continuation_arguments(delayed=True)
        engine, _, _ = two_terminals(args)
        origin = engine.observe_trade(record(4 * SECOND, 8, 2))
        self.assertIsNone(submit(engine, args, origin))
        self.assertEqual(engine._continuation_attempts, 0)
        self.assertIsNone(engine.observe_trade(record(4 * SECOND + 100 * MS, 8, 3)))
        proposal = engine.observe_trade(record(4 * SECOND + 220 * MS, 8, 4))
        self.assertEqual(proposal["terminal_continuation"], origin["terminal_continuation"])
        order = submit(engine, args, proposal)
        self.assertEqual(engine._continuation_attempts, 1)
        engine.settle(order["cancel_ack_ts_ns"])
        self.assertEqual(engine._remaining, 3)

    def test_foreign_context_and_quantity_fail_before_order(self):
        args = continuation_arguments()
        engine, _, _ = two_terminals(args)
        intent = engine.observe_trade(record(4 * SECOND, 8, 2))
        for change in ("quantity", "context"):
            bad = deepcopy(intent)
            if change == "quantity":
                bad["quantity"] += 1
            else:
                bad["terminal_continuation"]["terminal_attempt_number"] += 1
            with self.assertRaises(ValueError):
                submit(engine, args, bad)
            self.assertIsNone(engine._pending)
            self.assertEqual(engine._continuation_attempts, 0)




def continuation_program(*, account="main_account", scenario="l1-conservative-v0.1", delayed=False, expiry=False, no_print=False, unfilled=False):
    initial = 0 if account == "small_account" or unfilled else 2
    p = residual_program(first_fill=initial, replacement_fill=initial, account=account, scenario=scenario)
    value = p["sessions"][0]["opportunities"][0]["position"]
    policy, _ = m.feedback.SCENARIOS[scenario]
    shares = 0 if unfilled else 1 if account == "small_account" else 3
    value["trades"] = [record(2 * SECOND, 8), record(3 * SECOND, 8, 1)]
    if not no_print:
        value["trades"].append(record(4 * SECOND, 11, 2))
        if delayed:
            value["trades"].append(record(4220 * MS, 11, 3))
        value["trades"].append(record(5 * SECOND, 8, len(value["trades"])))
    if not expiry:
        for second in (4, 5):
            delay = 220 * MS if delayed and second == 4 else 0
            for at in (second * SECOND + delay - 1,
                       second * SECOND + delay + policy.decision_to_arrival_ms * MS - 10 * MS):
                q = deepcopy(value["exit_tape"]["quote_records"][-1])
                q.update(ts_recv_ns=BASE + at,
                    bid_size=max(1, int(m.Decimal(shares) / policy.displayed_size_participation)))
                value["exit_tape"]["quote_records"].append(q)
    repin_tape(value["exit_tape"])
    repin(value)
    return p


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
    result = m.seal({"contract_id": m.parent.parent.CONTRACT_ID, "artifact_type": "original_historical_account_path",
        "path_id": program["path_id"], "program_content_sha256": program["content_sha256"],
        "initial_account_state": initial, "seed_application_count": 1, "session_count": 30,
        "sessions": sessions, "last_close_content_sha256": previous,
        "path_complete": all(s["runtime"]["status"] == "flat_complete" for s in sessions), **m.RUNTIME_BOUNDARY})
    def resolve(oid):
        s = items[oid]["position"]
        return {"window": s["entry_input"]["window"], "trades": s["trades"], "bars": s["bars"], "tape": s["exit_tape"]}
    return program, result, manifest, resolve


def checked_case(p):
    program, result, manifest, resolve = run_fixture(p)
    checker.verify_path(program, result, manifest)
    checker.verify_parent_prefix(parent_fixture(p)[1], result)
    for pair in result["sessions"]:
        runtime = pair["runtime"]
        if runtime["reconciliation_snapshot"] is not None:
            checker.verify_decimal_snapshot(runtime["reconciliation_snapshot"])
        checker.verify_residual(runtime, resolve)
        checker.verify_continuation(runtime, resolve)
        checker.verify_waiting(runtime, resolve)
    return program, result, manifest, resolve


class AccountAndVerificationTests(unittest.TestCase):
    def test_zero_fill_without_active_quote_uses_corrected_cancellation_classifier(self):
        p = continuation_program()
        value = p["sessions"][0]["opportunities"][0]["position"]
        del value["exit_tape"]["quote_records"][9]
        repin_tape(value["exit_tape"])
        repin(value)
        _, result, _, resolve = checked_case(p)
        audit = result["sessions"][0]["runtime"]["reconciliation_snapshot"]["exit_continuation_events"]
        ready = [e for e in audit if e["event_type"] == "continuation_ready"]
        self.assertEqual(ready[1]["context"]["cancel_acknowledgement"]["execution_status"], "unavailable_no_fresh_quote")

    def test_unsubmitted_expiry_cannot_be_omitted(self):
        _, result, _, resolve = checked_case(continuation_program(expiry=True))
        runtime = deepcopy(result["sessions"][0]["runtime"])
        runtime["reconciliation_snapshot"]["exit_continuation_events"].pop()
        with self.assertRaisesRegex(ValueError, "expiry omitted"):
            checker.verify_continuation(runtime, resolve)

    def test_independent_account_close_and_cash_carry_all_cells(self):
        for scenario in m.feedback.SCENARIOS:
            for account in ("main_account", "small_account"):
                with self.subTest(scenario=scenario, account=account):
                    _, result, _, resolve = checked_case(continuation_program(scenario=scenario, account=account))
                    self.assertTrue(result["path_complete"])
                    runtime = result["sessions"][0]["runtime"]
                    self.assertEqual(runtime["status"], "flat_complete")
                    self.assertIsNone(runtime["reconciliation_snapshot"]["management"])
                    counts = checker.verify_continuation(runtime, resolve)
                    self.assertEqual((counts["continuation_ready"], counts["continuation_submissions"]), (2, 2))

    def test_waited_third_submission_preserves_authority(self):
        for scenario in m.feedback.SCENARIOS:
            _, result, _, resolve = checked_case(continuation_program(delayed=True, scenario=scenario))
            runtime = result["sessions"][0]["runtime"]
            self.assertEqual(checker.verify_waiting(runtime, resolve)["wait_submissions"], 1)
            self.assertTrue(result["path_complete"])

    def test_expired_no_quote_no_print_and_unfilled_keep_later_slots_blocked(self):
        for options in ({"expiry": True}, {"no_print": True}, {"unfilled": True}):
            with self.subTest(options=options):
                _, result, _, resolve = checked_case(continuation_program(**options))
                runtime = result["sessions"][0]["runtime"]
                self.assertEqual(runtime["status"], "original_window_exhausted_with_unresolved_state")
                self.assertEqual(checker.verify_continuation(runtime, resolve)["continuation_expiries"], 1)
                self.assertTrue(all(pair["runtime"]["status"] == "blocked_prior_state" for pair in result["sessions"][1:]))
                first = result["sessions"][0]["close"]["account_state"]
                self.assertTrue(all(pair["close"]["account_state"]["positions"] == first["positions"]
                    for pair in result["sessions"][1:]))

    def test_release_permits_only_frozen_reentry_and_fee_accounting(self):
        p = continuation_program()
        p = attach(p, 0, spec("A", offset=7 * SECOND))
        _, result, _, _ = checked_case(p)
        runtime = result["sessions"][0]["runtime"]
        self.assertEqual(runtime["status"], "flat_complete")
        self.assertEqual(sum(e["event_type"] == "capacity_released" for e in runtime["events"]), 2)

    def test_parent_paths_without_new_authority_are_exact(self):
        for amount in (8, 10):
            p = residual_program(replacement_fill=amount)
            _, result, _, _ = checked_case(p)
            self.assertEqual(result, parent_fixture(p)[1])

    def test_removed_audit_or_rehashed_semantic_mutations_fail(self):
        _, result, _, resolve = checked_case(continuation_program())
        runtime = result["sessions"][0]["runtime"]
        missing = deepcopy(runtime)
        missing["reconciliation_snapshot"].pop("exit_continuation_events")
        with self.assertRaisesRegex(ValueError, "authority omitted|lacks continuation"):
            checker.verify_continuation(missing, resolve)
        for field, value in (("remaining_quantity", 7), ("continuation_attempts", 1), ("clock_phase", 1)):
            bad = deepcopy(runtime)
            events = bad["reconciliation_snapshot"]["exit_continuation_events"]
            events[0][field] = value
            for i, event in enumerate(events):
                event.pop("content_sha256")
                event["previous_event_sha256"] = events[i-1]["content_sha256"] if i else None
                events[i] = m.seal(event)
            with self.assertRaises(ValueError):
                checker.verify_continuation(bad, resolve)

    def test_earlier_eligible_third_print_cannot_be_skipped(self):
        _, result, _, resolve = checked_case(continuation_program())
        runtime = result["sessions"][0]["runtime"]
        def earlier(oid):
            data = deepcopy(resolve(oid))
            data["trades"][2] = record(3800 * MS, 11, 2)
            return data
        with self.assertRaisesRegex(ValueError, "first eligible"):
            checker.verify_continuation(runtime, earlier)

    def test_original_account_arithmetic_and_corrected_status_checks_are_preserved(self):
        def function(path, name):
            return next(n for n in ast.parse((ROOT / path).read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name == name)
        original = "scripts/verify_sealed_historical_account_residual_exit_v01.py"
        child = "scripts/verify_sealed_historical_account_terminal_continuation_v01.py"
        self.assertEqual(ast.dump(function(original, "verify_path")), ast.dump(function(child, "verify_path")))
        before = ast.unparse(function(original, "verify_events"))
        after = ast.unparse(function(child, "verify_events"))
        self.assertEqual(after, before.replace("terminal.get(oid, 0) < 2 and ", "")
            .replace("terminal attempt budget or quantity differs", "terminal quantity differs"))
        before = ast.unparse(function("scripts/verify_sealed_historical_account_residual_exit_status_v01.py", "verify_residual"))
        after = ast.unparse(function(child, "verify_residual"))
        self.assertEqual(after, before.replace("event['contract_id'] == ID", "event['contract_id'] == RESIDUAL_ID")
            .replace("if e['reason'] != 'first_target']", "if e['reason'] != 'first_target'][:2]"))
        before = ast.unparse(function("src/momentumbot/research/sealed_historical_account_residual_exit_v01.py", "_session"))
        after = ast.unparse(function(m.OWN_FILES[0], "_session"))
        self.assertEqual(after, before.replace("_Session(", "Session(").replace("parent.CONTRACT_ID", "parent.parent.CONTRACT_ID"))



class RegistrationTests(unittest.TestCase):
    def test_registration_binds_completed_parent_and_all_implementation(self):
        result = m.verify_bundle(ROOT, ROOT / m.OUTPUT_PATH)
        self.assertTrue(result["verification_passed"])
        contract = m.frozen(ROOT / m.CONTRACT_PATH)
        self.assertEqual(contract, m.expected_contract(ROOT))
        self.assertEqual(set(contract["implementation_file_sha256"]), set(m.OWN_FILES))
        self.assertEqual(contract["parent_runtime_content_sha256"], m.PARENT_RUNTIME)
        original = m.file_sha
        with patch.object(m, "file_sha", side_effect=lambda p: "0" * 64
                if str(p).endswith(m.ADDITIONAL_PARENTS[2]) else original(p)):
            with self.assertRaisesRegex(ValueError, "parent differs"):
                m.validate_registration(ROOT)

    def test_wrong_external_registration_rejects_before_receipt_or_source_access(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "attempt"
            command = [sys.executable, str(ROOT / m.OWN_FILES[1]), "--replay",
                "--expected-registration-sha256", "0" * 64, "--output-root", str(output)]
            for key in ("scanner", "management", "exit", "entry-result", "entry-consumption"):
                command += ["--" + key + "-zip", str(Path(directory) / "missing.zip")]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("independent replay registration commitment differs", result.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
