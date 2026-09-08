from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from momentumbot.research import sealed_historical_account_state_producer_v01 as m
from tests.test_sealed_historical_management_fill_feedback_v01 import fixture, record, minute_bar, BASE, SECOND, reseal

ROOT = Path(__file__).resolve().parents[1]


def empty_program(*, account="main_account", horizon=1, scenario="l1-conservative-v0.1", count=30):
    plan = m.frozen(ROOT / m.fees.feedback.parent.ACCOUNT_PLAN)
    path_id = m.accounts._path_id(account, horizon, scenario)
    slots = deepcopy(next(p for p in plan["paths"] if p["path_id"] == path_id)["sessions"])
    for index, slot in enumerate(slots):
        slot.update(opportunity_inputs=[], unavailable_opportunity_count=0, source_date_has_no_micro_decisions=True)
        slots[index] = reseal(slot)
    return m.seal({"contract_id": m.CONTRACT_ID, "artifact_type": "account_state_replay_program",
        "input_scope": "synthetic_component_fixture", "path_id": path_id, "slots": slots,
        "sessions": [{"session_id": s["session_id"], "positions": []} for s in slots[:count]]})


def position_spec(*, day="2025-05-30", offset=0, quantity=10, target_fill=None, final_fill=None,
                  final_price="9", scenario="l1-conservative-v0.1", account="main_account", bars=None, trades=None):
    entry = fixture(quantity, scenario=scenario, target_fill=target_fill, final_fill=final_fill, account=account)
    shift = int(pd.Timestamp(day + "T13:00:00Z").value) - BASE + offset
    def shifted(value):
        if isinstance(value, dict):
            return {k: shifted(v) for k, v in value.items()}
        if isinstance(value, list):
            return [shifted(v) for v in value]
        if type(value) is int and BASE - 86400 * SECOND <= value <= BASE + 86400 * SECOND:
            return value + shift
        if isinstance(value, str) and value == "SYNTHETIC" and offset:
            return "SYNTHETICTWO"
        if isinstance(value, str) and value.startswith("2025-05-30T"):
            return pd.Timestamp(int(pd.Timestamp(value).value) + shift, tz="UTC").isoformat()
        return value
    decision = shifted(entry["source_decision"])
    decision["activation_id"] += "-" + day + "-" + str(offset)
    decision["plan_id"] = "plan-" + m.canonical_fingerprint({"activation_id": decision["activation_id"], "plan": decision["plan"]})
    op = m.accounts.availability.plan._opportunities(m.seal({"trading_date": day, "decisions": [decision]}))[0]
    window = shifted(entry["window"])
    window["opportunity"] = op
    window["start_ns"] = (BASE + shift) // (60 * SECOND) * (60 * SECOND)
    tape = shifted(entry["tape"])
    for kind in ("quote", "status"):
        req = tape[kind + "_request"]
        req["trading_date"] = day
        req["request_id"] = day + "-" + decision["symbol"] + "-" + req["schema"]
        if kind == "status":
            req["start_ns"] = int(pd.Timestamp(day, tz="UTC").value)
    for row in tape["quote_records"]:
        row["source_request_sha256"] = m.canonical_fingerprint(tape["quote_request"])
    for row in tape["quote_records"][-2:]:
        row["bid_px_nanos"] = int(Decimal(final_price) * 10**9)
        row["ask_px_nanos"] = int((Decimal(final_price) + Decimal(".01")) * 10**9)
    bars = shifted([] if bars is None else bars)
    trades = shifted([record(SECOND, 12), record(2 * SECOND, 8, 1)] if trades is None else trades)
    group = m.runner.derive_exit_plan([window], [tape["quote_request"], tape["status_request"]])["groups"][0]
    return {"entry_input": {"window": window, "source_decision": decision, "tape": tape,
                "expected_tape_sha256": m.canonical_fingerprint(tape)},
        "bars": bars, "trades": trades,
        "expected_streams": {"raw_sip_1m_bars": m.runner.stream_commitment(bars), "sip_transactions": m.runner.stream_commitment(trades)},
        "exit_group": group, "expected_exit_group_sha256": m.canonical_fingerprint(group),
        "exit_tape": deepcopy(tape), "expected_exit_tape_sha256": m.canonical_fingerprint(tape)}


def attach(program, index, spec):
    op = spec["entry_input"]["window"]["opportunity"]
    slot = program["slots"][index]
    slot["opportunity_inputs"].append({"opportunity_id": op["opportunity_id"],
        "availability_content_sha256": "b" * 64, "input_status": "available", "reason": "synthetic_available"})
    slot["source_date_has_no_micro_decisions"] = False
    program["slots"][index] = reseal(slot)
    program["sessions"][index]["positions"].append(spec)
    return reseal(program)


def replay(program):
    return m.replay_path(program, expected_program_content_sha256=program["content_sha256"])


def verify(program, result):
    return m.verify_path(program, result, expected_program_content_sha256=program["content_sha256"],
        expected_result_content_sha256=result["content_sha256"])


def states(result):
    return [s["close"]["account_state"] for s in result["sessions"]]


def cases():
    profit = attach(empty_program(), 0, position_spec(final_price="11"))
    profit = attach(profit, 1, position_spec(day=profit["slots"][1]["trading_date"]))
    subcent = attach(empty_program(count=2), 0, position_spec(final_price="9.003"))
    partial = attach(empty_program(count=3), 0, position_spec(target_fill=2, final_fill=3))
    broken = position_spec()
    broken["trades"][1]["timestamp_ns"] -= 3 * SECOND
    pending = attach(empty_program(count=2), 0, broken)
    unavailable = empty_program(count=2)
    slot = unavailable["slots"][0]
    slot["opportunity_inputs"] = [{"opportunity_id": "synthetic-unavailable", "availability_content_sha256": "c" * 64,
        "input_status": "unavailable", "reason": "source_unavailable"}]
    slot["unavailable_opportunity_count"] = 1
    slot["source_date_has_no_micro_decisions"] = False
    unavailable["slots"][0] = reseal(slot)
    unavailable = reseal(unavailable)
    omitted = attach(empty_program(count=2), 0, position_spec())
    omitted["sessions"][0]["positions"] = []
    omitted = reseal(omitted)
    loss = attach(empty_program(account="small_account", count=2), 0,
        position_spec(account="small_account", quantity=4, target_fill=0, final_fill=4, final_price="5.005"))
    serial = attach(empty_program(count=1), 0, position_spec(final_price="11"))
    serial = attach(serial, 0, position_spec(offset=1000 * SECOND, final_price="11"))
    return {"profit_continuity": profit, "subcent_continuity": subcent, "partial_position": partial,
        "pending_input_failure": pending, "unavailable_retained": unavailable,
        "available_omitted": omitted, "small_loss_day_reset": loss, "serial_positions": serial}


def synthetic_vectors():
    programs = cases()
    for account in ("main_account", "small_account"):
        for horizon in (1, 5, 10):
            for scenario in m.fees.feedback.SCENARIOS:
                program = empty_program(account=account, horizon=horizon, scenario=scenario)
                programs["empty_" + program["path_id"]] = program
    result = []
    for name, program in programs.items():
        output = replay(program)
        result.append({"name": name, "program": program, "result": output, "verification": verify(program, output)})
    return m.seal({"contract_id": m.CONTRACT_ID, "synthetic_only": True, "vectors": result, **m.BOUNDARY})


class ProducerMechanicsTests(unittest.TestCase):
    def test_seed_once_and_all_empty_session_states(self):
        for account in ("main_account", "small_account"):
            p = empty_program(account=account)
            result = replay(p)
            self.assertEqual(result["seed_application_count"], 1)
            self.assertEqual(result["session_count"], 30)
            self.assertTrue(all(s == result["initial_account_state"] for s in states(result)))
            self.assertEqual(sum(s["close"]["seed_applied"] for s in result["sessions"]), 1)

    def test_profit_fee_continuity_and_thirty_day_prefix(self):
        p = cases()["profit_continuity"]
        result = replay(p)
        self.assertEqual(states(result)[0]["equity_usd"], "30014.98")
        self.assertEqual(states(result)[1]["equity_usd"], "30019.96")
        self.assertEqual(states(result)[-1]["cumulative_realized_pnl_usd"], "19.96")
        self.assertEqual(states(result)[-1]["cumulative_fees_usd"], "0.04")
        self.assertEqual(len(states(result)[-1]["campaigns"]), 2)
        second = result["sessions"][1]["runtime"]["reconciliation_snapshot"]
        self.assertEqual(second["ledger"]["account"]["starting_equity"], 30014.98)
        self.assertEqual(len(second["fee_book"]["trades"]), 3)
        self.assertTrue(verify(p, result)["producer_state_authenticated_by_replay"])

    def test_fractional_cent_survives_next_day_without_rounding(self):
        r = replay(cases()["subcent_continuity"])
        self.assertEqual(states(r)[0]["equity_usd"], "30004.995")
        self.assertEqual(states(r)[1]["equity_usd"], "30004.995")
        self.assertEqual(states(r)[1]["cumulative_realized_pnl_usd"], "4.995")
        self.assertIsNone(r["sessions"][0]["close"]["frozen_cent_transport"])

    def test_open_position_carried_without_inventing_equity(self):
        r = replay(cases()["partial_position"])
        initial = states(r)[0]
        self.assertIsNone(initial["equity_usd"])
        self.assertEqual(initial["buying_power_usd"], "29950.98")
        self.assertEqual(initial["positions"][0]["quantity"], 5)
        for s in states(r)[1:]:
            for key in m.STATE_FIELDS - {"unresolved_inputs"}:
                self.assertEqual(s[key], initial[key])
        self.assertTrue(r["sessions"][1]["runtime"]["blocked_before_execution"])

    def test_prior_open_position_prevents_new_execution(self):
        p = cases()["partial_position"]
        p = attach(p, 1, position_spec(day=p["slots"][1]["trading_date"]))
        with self.assertRaisesRegex(ValueError, "prior unresolved"):
            replay(p)

    def test_mid_stream_failure_retains_pending_order_and_confirmed_cash(self):
        r = replay(cases()["pending_input_failure"])
        s = states(r)[0]
        self.assertEqual(s["positions"][0]["quantity"], 10)
        self.assertEqual(s["buying_power_usd"], "29899.99")
        self.assertTrue(s["pending_orders"])
        self.assertEqual(s["pending_orders"][-1]["kind"], "sell_cancel_pending")
        self.assertEqual(s["pending_orders"][-1]["confirmed_filled_quantity"], 0)
        self.assertEqual(states(r)[1]["pending_orders"], s["pending_orders"])
        self.assertFalse(r["sessions"][0]["runtime"]["position_results"][0]["complete_streams_verified"])

    def test_unavailable_gap_is_preserved_without_an_order(self):
        r = replay(cases()["unavailable_retained"])
        self.assertEqual(states(r)[-1]["equity_usd"], "30000.00")
        self.assertEqual(states(r)[-1]["unresolved_inputs"][0]["kind"], "unavailable_input")
        self.assertFalse(states(r)[-1]["unresolved_inputs"][0]["blocks_next_session"])
        self.assertTrue(r["sessions"][1]["close"]["next_session_flat_cash_execution_ready"])

    def test_omitted_available_opportunity_blocks_an_empty_day_claim(self):
        r = replay(cases()["available_omitted"])
        self.assertEqual(states(r)[0]["unresolved_inputs"][0]["kind"], "unprocessed_available_input")
        self.assertFalse(r["sessions"][0]["close"]["next_session_flat_cash_execution_ready"])
        self.assertTrue(r["sessions"][1]["runtime"]["blocked_before_execution"])

    def test_small_daily_guard_resets_with_carried_capital(self):
        r = replay(cases()["small_loss_day_reset"])
        self.assertEqual(states(r)[0]["equity_usd"], "1980.00")
        first = r["sessions"][0]["runtime"]["reconciliation_snapshot"]["ledger"]["account"]
        second = r["sessions"][1]["runtime"]["reconciliation_snapshot"]["ledger"]["account"]
        self.assertTrue(first["locked"])
        self.assertFalse(second["locked"])
        self.assertEqual(second["starting_equity"], 1980.0)
        self.assertEqual(states(r)[1]["cumulative_realized_pnl_usd"], "-20.00")

    def test_fee_book_persists_across_two_serial_positions(self):
        r = replay(cases()["serial_positions"])
        self.assertEqual(states(r)[0]["equity_usd"], "30029.98")
        self.assertEqual(states(r)[0]["cumulative_fees_usd"], "0.02")
        self.assertEqual(len(r["sessions"][0]["runtime"]["position_results"]), 2)

    def test_overlapping_complete_windows_do_not_reset_the_clock(self):
        p = attach(empty_program(count=1), 0, position_spec())
        p = attach(p, 0, position_spec(offset=5 * SECOND))
        r = replay(p)
        self.assertEqual(r["sessions"][0]["runtime"]["position_results"][1]["status"], "input_failure")
        self.assertFalse(r["sessions"][0]["close"]["next_session_flat_cash_execution_ready"])
        self.assertEqual(states(r)[0]["equity_usd"], "30004.98")

    def test_frozen_runner_management_parity(self):
        p = attach(empty_program(count=1), 0, position_spec(bars=[minute_bar()]))
        spec = p["sessions"][0]["positions"][0]
        day = m._new_day(p["slots"][0], m.accounts.account_state_input(p["slots"][0])["account_state"])
        args = {"entry_arguments": m._entry_arguments(day, p["slots"][0], spec["entry_input"]),
                **{k: v for k, v in spec.items() if k != "entry_input"}}
        expected = m.runner.run_position_mechanics(**args)
        actual = replay(p)["sessions"][0]["runtime"]["position_results"][0]["account_snapshot"]["management"]
        self.assertEqual(actual, expected["final_state"])

    def test_complete_trailing_stream_is_checked_after_flat(self):
        spec = position_spec()
        spec["expected_streams"]["sip_transactions"]["rows"] += 1
        r = replay(attach(empty_program(count=1), 0, spec))
        self.assertEqual(r["sessions"][0]["runtime"]["position_results"][0]["status"], "input_failure")
        self.assertFalse(r["sessions"][0]["close"]["next_session_flat_cash_execution_ready"])

    def test_bad_exit_pin_cannot_debit_entry_cash(self):
        spec = position_spec()
        spec["expected_exit_tape_sha256"] = "0" * 64
        r = replay(attach(empty_program(count=1), 0, spec))
        self.assertEqual(states(r)[0]["buying_power_usd"], "30000.00")
        self.assertEqual(states(r)[0]["positions"], [])
        self.assertEqual(r["sessions"][0]["runtime"]["position_results"][0]["status"], "input_failure")

    def test_historical_scope_rejected(self):
        p = empty_program(count=1)
        p["input_scope"] = "historical_source"
        with self.assertRaisesRegex(ValueError, "historical execution"):
            replay(reseal(p))

    def test_real_symbol_cannot_use_synthetic_component_entrypoint(self):
        spec = position_spec()
        spec["entry_input"]["window"]["opportunity"]["symbol"] = "REAL"
        with self.assertRaisesRegex(ValueError, "synthetic source"):
            replay(attach(empty_program(count=1), 0, spec))

    def test_external_program_and_result_pins_required(self):
        p = empty_program(count=1)
        with self.assertRaisesRegex(ValueError, "independent caller"):
            m.replay_path(p, expected_program_content_sha256="0" * 64)
        r = replay(p)
        with self.assertRaisesRegex(ValueError, "independent caller"):
            m.verify_path(p, r, expected_program_content_sha256=p["content_sha256"], expected_result_content_sha256="0" * 64)

    def test_rehashed_forged_state_does_not_authenticate(self):
        p = cases()["profit_continuity"]
        r = replay(p)
        r["sessions"][-1]["close"]["account_state"]["buying_power_usd"] = "99999.00"
        r["sessions"][-1]["close"] = reseal(r["sessions"][-1]["close"])
        r["last_close_content_sha256"] = r["sessions"][-1]["close"]["content_sha256"]
        with self.assertRaisesRegex(ValueError, "producer replay result differs"):
            verify(p, reseal(r))

    def test_caller_balance_or_prior_close_fields_are_rejected(self):
        for field in ("opening_balance", "previous_close", "account_state"):
            p = empty_program(count=1)
            p[field] = {"equity_usd": "30000.00"}
            with self.assertRaisesRegex(ValueError, "caller balances"):
                replay(reseal(p))

    def test_ledger_injection_is_rejected(self):
        spec = position_spec()
        spec["entry_input"]["pre_entry_ledger"] = {}
        with self.assertRaisesRegex(ValueError, "exact position and entry"):
            replay(attach(empty_program(count=1), 0, spec))

    def test_sessions_must_be_contiguous_same_path_and_start_at_seed(self):
        p = empty_program(count=2)
        mutations = []
        a = deepcopy(p); a["sessions"].reverse(); mutations.append(a)
        a = deepcopy(p); a["sessions"] = a["sessions"][1:]; mutations.append(a)
        a = deepcopy(p); a["sessions"][1] = deepcopy(a["sessions"][0]); mutations.append(a)
        a = deepcopy(p); a["path_id"] = empty_program(account="small_account")["path_id"]; mutations.append(a)
        a = deepcopy(p); a["slots"].pop(); mutations.append(a)
        a = deepcopy(p); a["sessions"] = []; mutations.append(a)
        for invalid in mutations:
            with self.assertRaises(ValueError):
                replay(reseal(invalid))

    def test_changed_date_and_duplicate_opportunity_rejected(self):
        p = empty_program(count=1)
        p["slots"][0]["trading_date"] = "2025-06-02"
        p["slots"][0] = reseal(p["slots"][0])
        with self.assertRaises(ValueError):
            replay(reseal(p))
        p = attach(empty_program(count=1), 0, position_spec())
        p["slots"][0]["opportunity_inputs"] *= 2
        p["slots"][0] = reseal(p["slots"][0])
        with self.assertRaisesRegex(ValueError, "unique opportunity"):
            replay(reseal(p))

    def test_extending_prefix_preserves_prior_checkpoints(self):
        p = cases()["profit_continuity"]
        whole = replay(p)
        p["sessions"] = p["sessions"][:1]
        prefix = replay(reseal(p))
        self.assertEqual(prefix["sessions"], whole["sessions"][:1])

    def test_input_and_output_copies_are_isolated(self):
        p = cases()["partial_position"]
        before = deepcopy(p)
        r = replay(p)
        self.assertEqual(p, before)
        r["sessions"][1]["close"]["account_state"]["positions"][0]["quantity"] = 500
        self.assertEqual(states(r)[0]["positions"][0]["quantity"], 5)

    def test_exact_cent_legacy_transport_remains_transport_only(self):
        p = cases()["profit_continuity"]
        r = replay(p)
        close = r["sessions"][0]["close"]["frozen_cent_transport"]
        output = m.accounts.account_state_input(p["slots"][1], previous_close=close,
            expected_close_content_sha256=close["content_sha256"])
        self.assertEqual(output["account_state"], states(r)[0])
        self.assertFalse(output["source_execution_verified_by_handoff"])

    def test_canonical_exact_money_and_retrospective_field_exclusion(self):
        s = replay(empty_program(count=1))["initial_account_state"]
        for bad in ("1", "1.0", "01.00", "-0.00", "NaN", "0.0000000001", 3.0):
            altered = deepcopy(s); altered["equity_usd"] = bad
            with self.assertRaises(ValueError):
                m.validate_state(altered)
        s["positions"] = [{next(iter(m.accounts._FORBIDDEN)): True}]
        with self.assertRaisesRegex(ValueError, "retrospective"):
            m.validate_state(s)

    def test_unrepresentable_frozen_float_projection_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "decimal loss"):
            m._projection("123456789.000000001", "equity")

    def test_failure_before_entry_cancel_ack_preserves_the_entry_order(self):
        spec = position_spec(trades=[])
        spec["expected_streams"]["sip_transactions"]["rows"] = 1
        r = replay(attach(empty_program(count=2), 0, spec))
        pending = states(r)[0]["pending_orders"]
        self.assertEqual(pending[0]["kind"], "entry_cancel_pending")
        self.assertEqual(states(r)[1]["pending_orders"], pending)
        self.assertEqual(states(r)[0]["buying_power_usd"], "29899.99")

    def test_stress_scenario_reconciles_and_carries_its_own_path(self):
        scenario = "l1-stress-v0.1"
        p = attach(empty_program(count=2, scenario=scenario), 0, position_spec(scenario=scenario, final_price="11"))
        r = replay(p)
        self.assertEqual(states(r)[1]["equity_usd"], "30014.98")
        self.assertTrue(verify(p, r)["verification_passed"])


class ProducerRegistrationTests(unittest.TestCase):
    def test_registration_pins_parent_and_closed_boundaries(self):
        self.assertTrue(m.validate_registration(ROOT)["verification_passed"])
        contract = m.expected_contract(ROOT)
        self.assertEqual(contract["parent_commit_sha"], "dcf1bc47b586653f3c0c97a4e433b4bdf1fff32a")
        self.assertEqual(contract["parent_reconciliation_freeze_content_sha256"], m.PARENT_FREEZE)
        for key, value in m.BOUNDARY.items():
            self.assertEqual(contract[key], value)

    def test_metadata_preserves_all_original_slots_and_unavailable_inputs(self):
        result = {name: json.loads(raw) for name, raw in m.build_bundle(ROOT).items()}
        deps = result["account-state-dependencies.json"]
        self.assertEqual((deps["path_count"], deps["session_count"], deps["seed_applications"], deps["previous_close_dependencies"]), (12, 360, 12, 348))
        self.assertEqual(sum(len(s["opportunity_inputs"]) for s in deps["slots"]), 744)
        self.assertEqual(sum(r["input_status"] == "unavailable" for s in deps["slots"] for r in s["opportunity_inputs"]), 162)
        self.assertEqual(result["readiness-report.json"]["historical_execution_count"], 0)

    def test_metadata_does_not_replay_or_open_source_tapes(self):
        with patch.object(m, "replay_path", side_effect=AssertionError("runtime called")), patch.object(
                m.runner.projection.inputs, "ManagementInputBundle", side_effect=AssertionError("source tape read")):
            self.assertEqual(len(m.build_bundle(ROOT)), 4)

    def test_parent_or_implementation_mutation_invalidates_registration(self):
        original = m.file_sha
        for name in (m.fees.MODULE_PATH, m.MODULE_PATH):
            with patch.object(m, "file_sha", side_effect=lambda p, n=name: "0" * 64 if str(p).endswith(n) else original(p)):
                with self.assertRaises(ValueError):
                    m.validate_registration(ROOT)

    def test_write_once_rehashed_metadata_and_extra_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "bundle"
            self.assertTrue(m.write_bundle(ROOT, output)["verification_passed"])
            with self.assertRaises(FileExistsError):
                m.write_bundle(ROOT, output)
            changed = output / "readiness-report.json"
            value = json.loads(changed.read_text()); value["historical_execution_count"] = 1
            changed.write_bytes(m.fees.encoded(reseal(value)))
            with self.assertRaisesRegex(ValueError, "reconstruction differs"):
                m.verify_bundle(ROOT, output)
            (output / "extra").write_text("x")
            with self.assertRaisesRegex(ValueError, "inventory differs"):
                m.verify_bundle(ROOT, output)

    def test_output_cannot_replace_frozen_paths_or_follow_symlinks(self):
        with self.assertRaises(ValueError):
            m.write_bundle(ROOT, ROOT / m.fees.OUTPUT_PATH)
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / "link"
            link.symlink_to(Path(tmp), target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                m.write_bundle(ROOT, link / "out")

    def test_all_twelve_paths_and_independent_accounting(self):
        from verify_sealed_historical_account_state_producer_v01 import verify as independent
        with tempfile.TemporaryDirectory() as tmp:
            vectors = synthetic_vectors()
            self.assertEqual(len(vectors["vectors"]), 20)
            path = Path(tmp) / "vectors.json"
            path.write_bytes(m.fees.encoded(vectors))
            report = independent(ROOT, ROOT / m.OUTPUT_PATH, path)
            self.assertTrue(report["verification_passed"])
            self.assertEqual(report["session_checkpoints_checked"], 404)

    def test_independent_checker_rejects_forged_cash_despite_resealed_chain(self):
        from verify_sealed_historical_account_state_producer_v01 import verify_vector
        p = cases()["subcent_continuity"]; r = replay(p)
        r["sessions"][-1]["close"]["account_state"]["buying_power_usd"] = "30005.00"
        r["sessions"][-1]["close"] = reseal(r["sessions"][-1]["close"])
        r["last_close_content_sha256"] = r["sessions"][-1]["close"]["content_sha256"]
        r = reseal(r)
        fake = m.seal({"verification_passed": True, "producer_state_authenticated_by_replay": True,
            "program_content_sha256": p["content_sha256"], "result_content_sha256": r["content_sha256"],
            "last_close_content_sha256": r["last_close_content_sha256"], **m.BOUNDARY})
        plan = m.frozen(ROOT / m.fees.feedback.parent.ACCOUNT_PLAN)
        with self.assertRaisesRegex(ValueError, "derived account state differs"):
            verify_vector({"program": p, "result": r, "verification": fake}, {v["path_id"]: v for v in plan["paths"]})

    def test_offline_cli_build_verify_vectors_and_independent_checker(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "bundle"
            vectors = Path(tmp) / "vectors"
            commands = [
                [sys.executable, m.SCRIPT_PATH, "--build", "--output-root", str(output)],
                [sys.executable, m.SCRIPT_PATH, "--verify", "--output-root", str(output)],
                [sys.executable, m.SCRIPT_PATH, "--synthetic-vectors", "--output-root", str(vectors)],
                [sys.executable, m.CHECKER_PATH, "--vectors", str(vectors / "synthetic-vectors.json"), "--output", str(vectors / "independent-verification.json")],
            ]
            for command in commands:
                result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=90)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(json.loads((vectors / "independent-verification.json").read_text())["verification_passed"])

    def test_entrypoints_have_no_undefined_globals_and_checker_is_independent(self):
        from check_recovery_entrypoints_v13 import undefined_globals
        import ast
        for name in (m.MODULE_PATH, m.SCRIPT_PATH, m.CHECKER_PATH):
            self.assertEqual(undefined_globals((ROOT / name).read_text(), name), set())
        checker = ast.parse((ROOT / m.CHECKER_PATH).read_text())
        imports = [node.module for node in ast.walk(checker) if isinstance(node, ast.ImportFrom)]
        self.assertFalse(any(name and name.startswith("momentumbot") for name in imports))


if __name__ == "__main__":
    unittest.main()
