"""Verifier-only correction: synthetic regressions and immutable-parent parity."""
import ast
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import verify_sealed_historical_account_residual_exit_status_v01 as checker
import verify_sealed_historical_account_residual_exit_v01 as frozen
import diagnose_sealed_historical_account_residual_exit_v01 as diagnostic
from tests.test_sealed_historical_account_residual_exit_v01 import (
    residual_program, run_fixture, parent_fixture, BASE, SECOND,
)
from tests.test_sealed_historical_account_residual_exit_diagnostic_v01 import lifecycle_input
from tests.test_sealed_historical_account_scheduler_v01 import repin

ROOT = Path(__file__).resolve().parents[1]
MS = 1_000_000


def status_program(scenario, kind):
    program = residual_program(first_fill=0, replacement_fill=10, scenario=scenario)
    value = program["sessions"][0]["opportunities"][0]["position"]
    tape = value["exit_tape"]
    if kind == "unavailable_no_fresh_quote":
        tape["quote_records"] = [q for q in tape["quote_records"]
            if not BASE + 2 * SECOND <= q["ts_recv_ns"] <= BASE + 2 * SECOND + frozen.TAIL]
    elif kind == "halted_cancelled":
        for offset, state in ((2 * SECOND + MS, "N"), (2700 * MS, "Y")):
            row = deepcopy(tape["status_records"][0])
            row.update(ts_recv_ns=BASE + offset, is_trading=state)
            tape["status_records"].append(row)
    repin(value)
    return program


def verify_fixture(program):
    source, result, manifest, resolve = run_fixture(program)
    checker.verify_path(source, result, manifest)
    checker.verify_parent_prefix(parent_fixture(program)[1], result)
    runtime = result["sessions"][0]["runtime"]
    checker.verify_decimal_snapshot(runtime["reconciliation_snapshot"])
    counts = checker.verify_residual(runtime, resolve)
    checker.verify_waiting(runtime, resolve)
    return result, runtime, resolve, counts


class SourceDerivedStatusTests(unittest.TestCase):
    def test_no_quote_and_halted_feedback_pass_only_corrected_checker(self):
        for scenario in diagnostic.POLICIES:
            for status in ("unavailable_no_fresh_quote", "halted_cancelled"):
                with self.subTest(scenario=scenario, status=status):
                    result, runtime, resolve, counts = verify_fixture(status_program(scenario, status))
                    self.assertEqual(runtime["status"], "flat_complete")
                    self.assertEqual((counts["residual_ready"], counts["residual_submissions"]), (1, 1))
                    rows = list(diagnostic.cancellations({"paths": [result]}))
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0]["acknowledgement"]["execution_status"], status)
                    with self.assertRaisesRegex(ValueError, diagnostic.EXPECTED_ERROR):
                        frozen.verify_residual(runtime, resolve)

    def test_existing_unfilled_partial_delayed_and_exhausted_paths_keep_checks(self):
        for scenario in diagnostic.POLICIES:
            for options in ({"first_fill": 0, "replacement_fill": 10}, {},
                            {"delayed": True}, {"replacement_fill": 2},
                            {"replacement_fill": 0}, {"expire": True}):
                with self.subTest(scenario=scenario, options=options):
                    _, runtime, resolve, counts = verify_fixture(residual_program(scenario=scenario, **options))
                    self.assertEqual(counts, frozen.verify_residual(runtime, resolve))

    def test_rehashed_forged_status_is_not_an_allowlisted_cancellation(self):
        for actual in ("cancelled_unfilled", "unavailable_no_fresh_quote", "halted_cancelled"):
            _, runtime, resolve, _ = verify_fixture(status_program("l1-conservative-v0.1", actual))
            for forged in ({"cancelled_unfilled", "unavailable_no_fresh_quote", "halted_cancelled",
                            "partially_filled_cancelled", "arbitrary"} - {actual}):
                bad = deepcopy(runtime)
                event = bad["reconciliation_snapshot"]["exit_residual_events"][0]
                context = event["context"]
                ack = context["cancel_acknowledgement"]
                ack["execution_status"] = forged
                context["cancel_acknowledgement"] = checker.parent.seal({k: v for k, v in ack.items() if k != "content_sha256"})
                event["context"] = checker.parent.seal({k: v for k, v in context.items() if k != "content_sha256"})
                bad["reconciliation_snapshot"]["exit_residual_events"][0] = checker.parent.seal({k: v for k, v in event.items() if k != "content_sha256"})
                with self.assertRaisesRegex(ValueError, "cancellation witness"):
                    checker.verify_residual(bad, resolve)

    def test_removed_authority_and_changed_shares_still_fail(self):
        _, runtime, resolve, _ = verify_fixture(status_program("l1-conservative-v0.1", "unavailable_no_fresh_quote"))
        omitted = deepcopy(runtime)
        omitted["reconciliation_snapshot"].pop("exit_residual_events")
        with self.assertRaisesRegex(ValueError, "authority omitted"):
            checker.verify_residual(omitted, resolve)
        event = runtime["reconciliation_snapshot"]["exit_residual_events"][0]
        event["remaining_quantity"] -= 1
        runtime["reconciliation_snapshot"]["exit_residual_events"][0] = checker.parent.seal({k: v for k, v in event.items() if k != "content_sha256"})
        with self.assertRaisesRegex(ValueError, "confirmed shares"):
            checker.verify_residual(runtime, resolve)

    def test_exact_age_and_half_open_active_interval_classify_status(self):
        for scenario, (delay, age, lifetime, cancel_delay) in diagnostic.POLICIES.items():
            ack = (delay + lifetime + cancel_delay) * MS
            for offset, expected in (((delay - age) * MS - 1, "unavailable_no_fresh_quote"),
                                     ((delay - age) * MS, "cancelled_unfilled"),
                                     (delay * MS, "cancelled_unfilled"),
                                     (ack - 1, "cancelled_unfilled"),
                                     (ack, "unavailable_no_fresh_quote")):
                tape, window, order, _ = lifecycle_input(scenario, (offset,))
                order["quantity"] = 2
                self.assertEqual(checker.cancellation_status({"scenario_id": scenario}, order, 0,
                    {"tape": tape, "window": window}), expected)

    def test_unknown_status_and_changed_clocks_fail_closed(self):
        for kind in ("unknown", "clock", "source", "window"):
            tape, window, order, scenario = lifecycle_input()
            order["quantity"] = 2
            if kind == "unknown":
                tape["status_records"][0]["is_trading"] = "~"
            elif kind == "clock":
                order["arrival_ts_ns"] += 1
            elif kind == "source":
                tape["quote_request"]["end_ns"] = order["decision_ts_ns"]
            else:
                window["end_ns"] = order["cancel_ack_ts_ns"]
            with self.assertRaises(ValueError):
                checker.cancellation_status({"scenario_id": scenario}, order, 0, {"tape": tape, "window": window})

    def test_positive_fill_rule_is_unchanged_and_invalid_quantity_rejected(self):
        self.assertEqual(checker.cancellation_status({}, {"quantity": 2}, 1, {}), "partially_filled_cancelled")
        for filled in (-1, 2, 0.5, True):
            with self.assertRaisesRegex(ValueError, "filled quantity"):
                checker.cancellation_status({}, {"quantity": 2}, filled, {})


class FrozenParityTests(unittest.TestCase):
    def test_outer_verification_body_is_identical(self):
        def node(module, name):
            return next(n for n in ast.parse(Path(module.__file__).read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name == name)
        before, after = node(frozen, "verify"), node(checker, "verify_original_runtime")
        after.name = before.name
        self.assertEqual(ast.dump(before), ast.dump(after))

    def test_residual_body_changes_only_the_expected_status_expression(self):
        tree = ast.parse(Path(frozen.__file__).read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "verify_residual")
        source = ast.get_source_segment(Path(frozen.__file__).read_text(), function)
        expression = '("partially_filled_cancelled" if filled else "cancelled_unfilled")'
        self.assertEqual(source.count(expression), 1)
        expected = ast.parse(source.replace(expression,
            'cancellation_status(entry, order, filled, resolve(entry["opportunity_id"]))')).body[0]
        actual = next(n for n in ast.parse(Path(checker.__file__).read_text()).body
            if isinstance(n, ast.FunctionDef) and n.name == "verify_residual")
        self.assertEqual(ast.dump(actual), ast.dump(expected))

    def test_inherited_checks_and_native_lifecycle_are_exact_original_functions(self):
        for name in ("verify_path", "verify_parent_prefix", "verify_waiting", "verify_decimal_snapshot",
                     "References", "OriginalEvidence", "terminal_reason", "eligible", "evidence", "parent"):
            self.assertIs(getattr(checker, name), getattr(frozen, name))
        self.assertIs(checker.quote_lifecycle, diagnostic.quote_lifecycle)
        tree = ast.parse(Path(checker.__file__).read_text())
        imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        self.assertFalse(any(name and name.startswith("momentumbot") for name in imports))


class RegistrationAndAttemptTests(unittest.TestCase):
    def test_registration_is_metadata_only_and_all_original_pins_are_unchanged(self):
        with patch.object(checker, "OriginalEvidence", side_effect=AssertionError("metadata only")):
            freeze = checker.read(checker.freeze_path(ROOT))
            contract, actual = checker.check_registration(ROOT, freeze["content_sha256"])
        self.assertEqual(actual, freeze)
        self.assertEqual(contract["runtime_content_sha256"], diagnostic.RUNTIME)
        self.assertTrue(contract["prior_failure_known_before_registration"])
        self.assertTrue(all(contract[key] is False for key in checker.BOUNDARIES))

    def test_wrong_external_freeze_and_mutated_child_or_parent_fail_before_evidence(self):
        with self.assertRaisesRegex(ValueError, "external registration"):
            checker.check_registration(ROOT, "0" * 64)
        expected = checker.read(checker.freeze_path(ROOT))["content_sha256"]
        original = checker.file_spec
        for relative in (checker.OWN_FILES[0], "scripts/verify_sealed_historical_account_residual_exit_v01.py",
                         "scripts/diagnose_sealed_historical_account_residual_exit_v01.py"):
            with patch.object(checker, "file_spec", side_effect=lambda path:
                    {"bytes": 1, "sha256": "0" * 64} if path == ROOT / relative else original(path)):
                with self.assertRaises(ValueError):
                    checker.check_registration(ROOT, expected)

    def test_wrong_stored_runtime_cannot_reach_original_verifier(self):
        with patch.object(checker, "check_registration", return_value=({}, {})), \
             patch.object(checker, "_pinned_file", return_value={"content_sha256": "wrong"}), \
             patch.object(checker, "verify_original_runtime", side_effect=AssertionError("must not execute")):
            with self.assertRaisesRegex(ValueError, "fixed stored runtime"):
                checker.verify_registered(ROOT, Path("synthetic"), None, None, {}, "pin")

    def test_attempt_receipt_precedes_verification_and_success_is_sealed(self):
        report = checker.parent.seal({"verification_passed": True})
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "new-attempt"
            def verify(*args):
                self.assertTrue((output / "attempt.json").is_file())
                return report
            with patch.object(checker, "check_registration"), patch.object(checker, "verify_registered", side_effect=verify):
                checker.run_attempt(ROOT, None, None, None, {}, "pin", output)
            self.assertEqual({p.name for p in output.iterdir()}, {"attempt.json", "verification.json", "freeze-manifest.json"})
            freeze = checker.read(output / "freeze-manifest.json")
            for name, spec in freeze["file_inventory"].items():
                self.assertEqual(checker.file_spec(output / name), spec)

    def test_new_failure_is_retained_and_attempt_directory_cannot_be_reused(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "new-attempt"
            with patch.object(checker, "check_registration"), \
                 patch.object(checker, "verify_registered", side_effect=ValueError("synthetic next gate")):
                with self.assertRaisesRegex(ValueError, "synthetic next gate"):
                    checker.run_attempt(ROOT, None, None, None, {}, "pin", output)
                failure = checker.read(output / "failure.json")
                self.assertEqual(failure["error"], "synthetic next gate")
                self.assertFalse(failure["verification_passed"])
                before = {p.name: p.read_bytes() for p in output.iterdir()}
                with self.assertRaises(FileExistsError):
                    checker.run_attempt(ROOT, None, None, None, {}, "pin", output)
                self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})

    def test_wrong_registration_creates_no_attempt_and_draft_writer_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "attempt"
            with patch.object(checker, "check_registration", side_effect=ValueError("wrong freeze")):
                with self.assertRaisesRegex(ValueError, "wrong freeze"):
                    checker.run_attempt(ROOT, None, None, None, {}, "pin", output)
            self.assertFalse(output.exists())
            with patch.object(checker, "registration_documents", return_value=({"contract": "synthetic"}, {"freeze": "synthetic"})):
                checker.build_registration(root)
                before = checker.contract_path(root).read_bytes()
                with self.assertRaises(FileExistsError):
                    checker.build_registration(root)
                self.assertEqual(checker.contract_path(root).read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
