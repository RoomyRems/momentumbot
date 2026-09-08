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

from momentumbot.research import sealed_historical_account_valuation_v01 as m
from tests.test_sealed_historical_account_state_producer_v01 import empty_program, position_spec, attach, replay, cases, reseal

ROOT = Path(__file__).resolve().parents[1]
MS = 1_000_000


def fixture(*, kind="open", account="main_account", horizon=1, scenario="l1-conservative-v0.1", index=0):
    p = empty_program(account=account, horizon=horizon, scenario=scenario, count=index + 1)
    if kind in ("pending", "omitted", "unavailable"):
        p = cases()[{"pending": "pending_input_failure", "omitted": "available_omitted", "unavailable": "unavailable_retained"}[kind]]
        p["sessions"] = p["sessions"][:1]
        p = reseal(p)
    elif kind == "open":
        small = account == "small_account"
        spec = position_spec(day=p["slots"][index]["trading_date"], account=account, scenario=scenario,
            quantity=4 if small else 10, target_fill=1 if small else 2, final_fill=1 if small else 3)
        p = attach(p, index, spec)
    elif kind == "profit":
        p = attach(p, index, position_spec(day=p["slots"][index]["trading_date"], final_price="11", scenario=scenario))
    r = replay(p)
    close = r["sessions"][-1]["close"]
    slot = p["slots"][r["session_count"]]
    at = m.session_start_ns(slot)
    inputs = {"contract_id": m.CONTRACT_ID, "input_scope": "synthetic_component_fixture",
        "producer_program_content_sha256": p["content_sha256"], "producer_result_content_sha256": r["content_sha256"],
        "previous_close_content_sha256": close["content_sha256"], "next_session_id": slot["session_id"],
        "valuation_at_ns": at, "position_inputs": []}
    for position in close["account_state"]["positions"]:
        symbol, day = position["symbol"], slot["trading_date"]
        quote_request = {"request_id": f"{day}-{symbol}-mbp-1", "trading_date": day, "dataset": "XNAS.ITCH",
            "schema": "mbp-1", "symbols": [symbol], "stype_in": "raw_symbol", "start_ns": at - 1000 * MS,
            "end_ns": at + 1000 * MS, "end_exclusive": True}
        status_request = {**quote_request, "request_id": f"{day}-{symbol}-status", "schema": "status",
            "start_ns": int(pd.Timestamp(day, tz="UTC").value)}
        tape = {"quote_request": quote_request, "status_request": status_request,
            "quote_records": [{"symbol": symbol, "ts_recv_ns": at - 10 * MS, "sequence": 1,
                "bid_px_nanos": 8_000_000_000, "ask_px_nanos": 8_010_000_000, "bid_size": 1, "ask_size": 1,
                "source_request_sha256": m.canonical_fingerprint(quote_request), "source_record_index": 0}],
            "status_records": [{"symbol": symbol, "ts_recv_ns": at - 2000 * MS, "action": 7, "is_trading": "Y"}]}
        inputs["position_inputs"].append({"activation_id": position["activation_id"], "position_content_sha256": m.canonical_fingerprint(position),
            "units_evidence": {"status": "unchanged_raw_units", "source_id": "synthetic-share-unit-continuity",
                "known_at_ns": at, "from_close_content_sha256": close["content_sha256"], "through_ns": at},
            "tape": tape, "expected_tape_sha256": m.canonical_fingerprint(tape)})
    return {"program": p, "result": r, "inputs": m.seal(inputs)}


def repin(f):
    for p in f["inputs"]["position_inputs"]:
        if p["tape"] is not None:
            for row in p["tape"]["quote_records"]:
                row["source_request_sha256"] = m.canonical_fingerprint(p["tape"]["quote_request"])
            p["expected_tape_sha256"] = m.canonical_fingerprint(p["tape"])
    f["inputs"] = reseal(f["inputs"])
    return f


def value(f):
    return m.value_next_session(f["program"], f["result"], f["inputs"],
        expected_program_content_sha256=f["program"]["content_sha256"], expected_result_content_sha256=f["result"]["content_sha256"],
        expected_inputs_content_sha256=f["inputs"]["content_sha256"])


def verify(f, output):
    return m.verify_valuation(f["program"], f["result"], f["inputs"], output,
        expected_program_content_sha256=f["program"]["content_sha256"], expected_result_content_sha256=f["result"]["content_sha256"],
        expected_inputs_content_sha256=f["inputs"]["content_sha256"], expected_valuation_content_sha256=output["content_sha256"])


def vector_cases():
    result = {"open_bid_mark": fixture(), "flat_profit": fixture(kind="profit"), "pending_order": fixture(kind="pending"),
        "omitted_input": fixture(kind="omitted"), "unavailable_input": fixture(kind="unavailable")}
    subcent = fixture(); subcent["inputs"]["position_inputs"][0]["tape"]["quote_records"][0]["bid_px_nanos"] = 8_003_000_000
    result["subcent_mark"] = repin(subcent)
    for name in ("stale", "halted", "unknown_status", "unusable_latest", "missing_units", "adjustment_required", "future_units", "missing_tape", "missing_position", "bad_tape_pin", "same_time_status"):
        f = fixture(); entry = f["inputs"]["position_inputs"][0]; tape = entry["tape"]; at = f["inputs"]["valuation_at_ns"]
        if name == "stale": tape["quote_records"][0]["ts_recv_ns"] = at - 100 * MS - 1
        elif name == "halted": tape["status_records"][0]["is_trading"] = "N"
        elif name == "unknown_status": tape["status_records"][0]["is_trading"] = "~"
        elif name == "unusable_latest": tape["quote_records"][0]["bid_size"] = 0
        elif name == "missing_units": entry["units_evidence"] = None
        elif name == "adjustment_required": entry["units_evidence"]["status"] = "adjustment_required"
        elif name == "future_units": entry["units_evidence"]["known_at_ns"] = at + 1
        elif name == "missing_tape": entry["tape"] = entry["expected_tape_sha256"] = None
        elif name == "missing_position": f["inputs"]["position_inputs"] = []
        elif name == "same_time_status": tape["status_records"][0]["ts_recv_ns"] = tape["quote_records"][0]["ts_recv_ns"]
        f = repin(f)
        if name == "bad_tape_pin": entry["expected_tape_sha256"] = "0" * 64; f["inputs"] = reseal(f["inputs"])
        result[name] = f
    for account in ("main_account", "small_account"):
        for horizon in (1, 5, 10):
            for scenario in m.parent.fees.feedback.SCENARIOS:
                result["flat_" + m.parent.accounts._path_id(account, horizon, scenario)] = fixture(kind="flat", account=account, horizon=horizon, scenario=scenario)
    return result


def synthetic_vectors():
    vectors = []
    for name, f in vector_cases().items():
        output = value(f)
        vectors.append({"name": name, **f, "valuation": output, "verification": verify(f, output)})
    return m.seal({"contract_id": m.CONTRACT_ID, "synthetic_only": True, "vectors": vectors, **m.BOUNDARY})


class ValuationMechanicsTests(unittest.TestCase):
    def test_open_position_equity_and_original_cost_basis(self):
        f = fixture(); result = value(f); v = result["account_valuation"]
        self.assertEqual(v["cash_usd"], "29950.98")
        self.assertEqual(v["position_cost_basis_usd"], "50.00")
        self.assertEqual(v["position_market_value_usd"], "40.00")
        self.assertEqual(v["opening_unrealized_pnl_usd"], "-10.00")
        self.assertEqual(v["equity_usd"], "29990.98")
        self.assertEqual(v["cumulative_realized_pnl_usd"], "0.98")
        self.assertEqual(v["cumulative_fees_usd"], "0.02")
        self.assertTrue(v["valuation_complete"])
        self.assertFalse(result["mark_is_executable_proceeds"])
        self.assertTrue(verify(f, result)["verification_passed"])

    def test_valuation_preserves_positions_orders_fees_and_campaigns(self):
        f = fixture(); original = deepcopy(f); r = value(f)
        state = f["result"]["sessions"][-1]["close"]["account_state"]
        self.assertEqual(r["source_account_state"], state)
        for key in ("positions", "pending_orders", "campaigns", "unresolved_inputs"):
            self.assertEqual(r["continuation_context"][key], state[key])
        self.assertFalse(r["continuation_context"]["can_initialize_flat_session_ledger"])
        self.assertFalse(r["continuation_context"]["new_entry_or_exit_executed"])
        self.assertEqual(f, original)

    def test_fractional_cent_equity_is_exact(self):
        r = value(vector_cases()["subcent_mark"])
        self.assertEqual(r["account_valuation"]["equity_usd"], "29990.995")
        self.assertEqual(r["account_valuation"]["position_market_value_usd"], "40.015")

    def test_flat_profit_initializes_next_day_without_seed_reset(self):
        r = value(fixture(kind="profit"))
        self.assertEqual(r["account_valuation"]["equity_usd"], "30014.98")
        context = r["continuation_context"]
        self.assertTrue(context["can_initialize_flat_session_ledger"])
        self.assertEqual(context["flat_session_ledger"]["ledger"]["account"]["starting_equity"], 30014.98)
        self.assertEqual(context["flat_session_ledger"]["fee_book"]["trades"], [])

    def test_pending_order_does_not_disappear_when_its_ack_time_has_passed(self):
        f = fixture(kind="pending"); r = value(f)
        self.assertTrue(r["account_valuation"]["all_position_marks_complete"])
        self.assertFalse(r["account_valuation"]["confirmed_inventory_complete"])
        self.assertIsNone(r["account_valuation"]["equity_usd"])
        self.assertTrue(r["continuation_context"]["pending_orders"])
        self.assertFalse(r["continuation_context"]["pending_order_cancelled_by_valuation"])

    def test_omitted_available_input_cannot_be_cleared_by_valuation(self):
        r = value(fixture(kind="omitted"))
        self.assertFalse(r["account_valuation"]["valuation_complete"])
        self.assertIsNone(r["account_valuation"]["equity_usd"])
        self.assertFalse(r["continuation_context"]["can_initialize_flat_session_ledger"])

    def test_unavailable_input_remains_explicit_without_blocking_verified_flat_cash(self):
        r = value(fixture(kind="unavailable"))
        self.assertEqual(r["account_valuation"]["equity_usd"], "30000.00")
        self.assertEqual(r["continuation_context"]["unresolved_inputs"][0]["kind"], "unavailable_input")
        self.assertTrue(r["continuation_context"]["can_initialize_flat_session_ledger"])

    def test_freshness_boundaries_match_each_frozen_scenario(self):
        for scenario, ms in (("l1-conservative-v0.1", 100), ("l1-stress-v0.1", 50)):
            for extra, complete in ((0, True), (1, False)):
                f = fixture(scenario=scenario)
                f["inputs"]["position_inputs"][0]["tape"]["quote_records"][0]["ts_recv_ns"] = f["inputs"]["valuation_at_ns"] - ms * MS - extra
                self.assertEqual(value(repin(f))["account_valuation"]["valuation_complete"], complete)

    def test_quote_at_cutoff_is_known_but_one_nanosecond_later_is_not(self):
        for offset, complete in ((0, True), (1, False)):
            f = fixture()
            f["inputs"]["position_inputs"][0]["tape"]["quote_records"][0]["ts_recv_ns"] = f["inputs"]["valuation_at_ns"] + offset
            self.assertEqual(value(repin(f))["account_valuation"]["valuation_complete"], complete)

    def test_future_price_and_halt_do_not_change_the_causal_valuation(self):
        f = fixture(); before = value(f)
        tape = f["inputs"]["position_inputs"][0]["tape"]; at = f["inputs"]["valuation_at_ns"]
        tape["quote_records"].append({**tape["quote_records"][0], "ts_recv_ns": at + 100 * MS,
            "bid_px_nanos": 100_000_000_000, "ask_px_nanos": 101_000_000_000, "sequence": 2, "source_record_index": 1})
        tape["status_records"].append({**tape["status_records"][0], "ts_recv_ns": at + 200 * MS, "is_trading": "N"})
        after = value(repin(f))
        self.assertEqual(before["account_valuation"], after["account_valuation"])
        for field in ("mark_price_usd", "quote_source", "status_source", "reason"):
            self.assertEqual(before["position_valuations"][0][field], after["position_valuations"][0][field])

    def test_latest_native_ordinal_wins_equal_time_and_sequence(self):
        f = fixture(); tape = f["inputs"]["position_inputs"][0]["tape"]
        tape["quote_records"].append({**tape["quote_records"][0], "bid_px_nanos": 7_000_000_000, "source_record_index": 1})
        r = value(repin(f))
        self.assertEqual(r["position_valuations"][0]["mark_price_usd"], "7.00")
        self.assertEqual(r["position_valuations"][0]["quote_source"]["source_record_index"], 1)

    def test_unusable_latest_quote_does_not_fall_back_to_earlier_good_book(self):
        f = fixture(); tape = f["inputs"]["position_inputs"][0]["tape"]
        tape["quote_records"].append({**tape["quote_records"][0], "ts_recv_ns": f["inputs"]["valuation_at_ns"], "bid_size": 0, "source_record_index": 1})
        r = value(repin(f))
        self.assertEqual(r["position_valuations"][0]["reason"], "latest_book_unusable")
        self.assertIsNone(r["account_valuation"]["equity_usd"])

    def test_halt_unknown_and_same_time_status_are_unavailable(self):
        vectors = vector_cases()
        for name, reason in (("halted", "trading_halted"), ("unknown_status", "trading_status_unknown"),
                             ("same_time_status", "same_receive_time_status_quote_ambiguity")):
            r = value(vectors[name])
            self.assertEqual(r["position_valuations"][0]["reason"], reason)
            self.assertIsNone(r["account_valuation"]["equity_usd"])

    def test_resume_requires_a_fresh_book_after_the_status_transition(self):
        f = fixture(); tape = f["inputs"]["position_inputs"][0]["tape"]; at = f["inputs"]["valuation_at_ns"]
        tape["status_records"] += [{**tape["status_records"][0], "ts_recv_ns": at - 8 * MS, "is_trading": "N"},
                                   {**tape["status_records"][0], "ts_recv_ns": at - 5 * MS}]
        self.assertEqual(value(repin(f))["position_valuations"][0]["reason"], "quote_precedes_latest_status_transition")
        tape["quote_records"].append({**tape["quote_records"][0], "ts_recv_ns": at, "source_record_index": 1})
        self.assertTrue(value(repin(f))["account_valuation"]["valuation_complete"])

    def test_missing_unit_evidence_and_known_split_do_not_guess_adjustments(self):
        for name in ("missing_units", "adjustment_required", "future_units"):
            r = value(vector_cases()[name])
            self.assertIsNone(r["account_valuation"]["equity_usd"])
            self.assertEqual(r["continuation_context"]["positions"][0]["quantity"], 5)

    def test_missing_position_or_tape_preserves_unknown_equity(self):
        for name in ("missing_position", "missing_tape"):
            r = value(vector_cases()[name])
            self.assertIsNone(r["account_valuation"]["equity_usd"])
            self.assertEqual(r["account_valuation"]["cash_usd"], "29950.98")

    def test_bad_tape_pin_or_truncated_ordinals_is_an_input_failure(self):
        r = value(vector_cases()["bad_tape_pin"])
        self.assertEqual(r["position_valuations"][0]["valuation_status"], "input_failure")
        f = fixture(); f["inputs"]["position_inputs"][0]["tape"]["quote_records"][0]["source_record_index"] = 1
        self.assertEqual(value(repin(f))["position_valuations"][0]["valuation_status"], "input_failure")

    def test_wrong_source_symbol_date_or_request_coverage_rejected(self):
        for mutation in ("symbol", "date", "start", "end"):
            f = fixture(); req = f["inputs"]["position_inputs"][0]["tape"]["quote_request"]
            if mutation == "symbol": req["symbols"] = ["SYNTHETICTWO"]
            elif mutation == "date": req["trading_date"] = "2025-05-30"
            elif mutation == "start": req["start_ns"] = f["inputs"]["valuation_at_ns"]
            else: req["end_ns"] = f["inputs"]["valuation_at_ns"]
            self.assertEqual(value(repin(f))["position_valuations"][0]["valuation_status"], "input_failure")

    def test_valuation_time_is_frozen_next_session_start(self):
        f = fixture()
        stamp = pd.Timestamp(f["inputs"]["valuation_at_ns"], tz="UTC").tz_convert("America/New_York")
        self.assertEqual((stamp.hour, stamp.minute, stamp.second), (7, 0, 0))
        for delta in (-1, 1):
            changed = deepcopy(f); changed["inputs"]["valuation_at_ns"] += delta
            with self.assertRaisesRegex(ValueError, "following session"):
                value(repin(changed))

    def test_foreign_session_or_previous_close_rejected(self):
        for key, value_ in (("next_session_id", "wrong"), ("previous_close_content_sha256", "0" * 64)):
            f = fixture(); f["inputs"][key] = value_
            with self.assertRaises(ValueError): value(repin(f))

    def test_duplicate_or_foreign_position_inputs_rejected(self):
        f = fixture(); f["inputs"]["position_inputs"] *= 2
        with self.assertRaisesRegex(ValueError, "duplicate or foreign"): value(repin(f))
        f = fixture(); f["inputs"]["position_inputs"][0]["activation_id"] = "foreign"
        with self.assertRaisesRegex(ValueError, "duplicate or foreign"): value(repin(f))

    def test_tampered_producer_close_cannot_be_valued(self):
        f = fixture(); r = f["result"]
        r["sessions"][-1]["close"]["account_state"]["buying_power_usd"] = "40000.00"
        r["sessions"][-1]["close"] = reseal(r["sessions"][-1]["close"])
        r["last_close_content_sha256"] = r["sessions"][-1]["close"]["content_sha256"]
        f["result"] = reseal(r)
        with self.assertRaisesRegex(ValueError, "producer replay result"): value(f)

    def test_external_valuation_input_pin_is_required(self):
        f = fixture()
        with self.assertRaisesRegex(ValueError, "independent caller"):
            m.value_next_session(f["program"], f["result"], f["inputs"], expected_program_content_sha256=f["program"]["content_sha256"],
                expected_result_content_sha256=f["result"]["content_sha256"], expected_inputs_content_sha256="0" * 64)

    def test_resealed_forged_mark_is_rejected_by_recomputation(self):
        f = fixture(); r = value(f); r["account_valuation"]["equity_usd"] = "40000.00"
        with self.assertRaisesRegex(ValueError, "valuation replay"): verify(f, reseal(r))

    def test_historical_mode_or_extra_retrospective_fields_are_rejected(self):
        for key, value_ in (("input_scope", "historical"), ("ross_action", "buy")):
            f = fixture(); f["inputs"][key] = value_
            with self.assertRaisesRegex(ValueError, "synthetic valuation input"): value(repin(f))

    def test_final_registered_session_cannot_roll_into_an_unregistered_date(self):
        f = fixture(kind="flat"); f["program"] = empty_program(); f["result"] = replay(f["program"])
        f["inputs"]["producer_program_content_sha256"] = f["program"]["content_sha256"]
        f["inputs"]["producer_result_content_sha256"] = f["result"]["content_sha256"]
        with self.assertRaisesRegex(ValueError, "no next session"): value(repin(f))

    def test_july_transition_uses_original_registered_calendar(self):
        p = empty_program(); index = next(i for i, s in enumerate(p["slots"]) if s["trading_date"] >= "2025-07-01") - 1
        f = fixture(kind="flat", index=index); r = value(f)
        self.assertEqual(r["continuation_context"]["trading_date"], p["slots"][index+1]["trading_date"])
        self.assertEqual(r["account_valuation"]["equity_usd"], "30000.00")


class ValuationRegistrationTests(unittest.TestCase):
    def test_registration_pins_completed_producer_and_closed_boundaries(self):
        self.assertTrue(m.validate_registration(ROOT)["verification_passed"])
        contract = m.expected_contract(ROOT)
        self.assertEqual(contract["parent_commit_sha"], "7840e5696fe8d2961ade913771f2c7cfa257493a")
        self.assertEqual(contract["parent_producer_freeze_content_sha256"], m.PARENT_FREEZE)
        for key, expected in m.BOUNDARY.items(): self.assertEqual(contract[key], expected)

    def test_all_348_dependencies_preserve_frozen_session_slots(self):
        bundle = {name: json.loads(raw) for name, raw in m.build_bundle(ROOT).items()}
        deps = bundle["valuation-dependencies.json"]
        self.assertEqual((deps["path_count"], deps["session_count"], deps["valuation_transition_count"]), (12, 360, 348))
        self.assertEqual(len({s["next_session_id"] for s in deps["transitions"]}), 348)
        self.assertEqual(len({s["path_id"] for s in deps["transitions"]}), 12)
        self.assertTrue(all(pd.Timestamp(s["valuation_at_ns"], tz="UTC").tz_convert("America/New_York").hour == 7 for s in deps["transitions"]))
        self.assertEqual(bundle["readiness-report.json"]["historical_execution_count"], 0)

    def test_metadata_never_values_or_opens_market_tapes(self):
        with patch.object(m, "value_next_session", side_effect=AssertionError("runtime called")), patch.object(
                m.parent.runner.projection.inputs, "ManagementInputBundle", side_effect=AssertionError("tape read")):
            self.assertEqual(len(m.build_bundle(ROOT)), 4)

    def test_parent_or_child_mutation_invalidates_registration(self):
        original = m.file_sha
        for name in (m.parent.MODULE_PATH, m.MODULE_PATH):
            with patch.object(m, "file_sha", side_effect=lambda p, n=name: "0" * 64 if str(p).endswith(n) else original(p)):
                with self.assertRaises(ValueError): m.validate_registration(ROOT)

    def test_write_once_rehashed_metadata_and_extra_files_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle"
            self.assertTrue(m.write_bundle(ROOT, out)["verification_passed"])
            with self.assertRaises(FileExistsError): m.write_bundle(ROOT, out)
            path = out / "readiness-report.json"
            value_ = json.loads(path.read_text()); value_["historical_execution_count"] = 1
            path.write_bytes(m.parent.fees.encoded(reseal(value_)))
            with self.assertRaisesRegex(ValueError, "reconstruction differs"): m.verify_bundle(ROOT, out)
            (out / "extra").write_text("x")
            with self.assertRaisesRegex(ValueError, "inventory differs"): m.verify_bundle(ROOT, out)

    def test_frozen_output_and_symlink_paths_rejected(self):
        with self.assertRaises(ValueError): m.write_bundle(ROOT, ROOT / m.parent.OUTPUT_PATH)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "link"; path.symlink_to(Path(tmp), target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"): m.write_bundle(ROOT, path / "out")

    def test_independent_checker_recomputes_vectors_and_rejects_resealed_wrong_equity(self):
        from verify_sealed_historical_account_valuation_v01 import verify as independent, verify_case
        with tempfile.TemporaryDirectory() as tmp:
            vectors = synthetic_vectors(); path = Path(tmp) / "vectors.json"
            path.write_bytes(m.parent.fees.encoded(vectors))
            report = independent(ROOT, ROOT / m.OUTPUT_PATH, path)
            self.assertEqual(report["case_count"], 29)
            self.assertTrue(report["verification_passed"])
            case = deepcopy(vectors["vectors"][0])
            case["valuation"]["account_valuation"]["equity_usd"] = "99999.00"
            case["valuation"] = reseal(case["valuation"])
            case["verification"]["valuation_content_sha256"] = case["valuation"]["content_sha256"]
            case["verification"] = reseal(case["verification"])
            plan = m.frozen(ROOT / m.parent.fees.feedback.parent.ACCOUNT_PLAN)
            with self.assertRaisesRegex(ValueError, "account valuation differs"):
                verify_case(case, {p["path_id"]: p for p in plan["paths"]})

    def test_direct_offline_cli_produces_independently_verified_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, vectors = Path(tmp) / "bundle", Path(tmp) / "vectors"
            commands = [[sys.executable, m.SCRIPT_PATH, "--build", "--output-root", str(out)],
                [sys.executable, m.SCRIPT_PATH, "--verify", "--output-root", str(out)],
                [sys.executable, m.SCRIPT_PATH, "--synthetic-vectors", "--output-root", str(vectors)],
                [sys.executable, m.CHECKER_PATH, "--vectors", str(vectors / "synthetic-vectors.json"), "--output", str(vectors / "independent-verification.json")]]
            for command in commands:
                proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=90)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue(json.loads((vectors / "independent-verification.json").read_text())["verification_passed"])

    def test_entrypoints_have_no_undefined_globals_and_checker_is_stdlib(self):
        import ast
        from check_recovery_entrypoints_v13 import undefined_globals
        for name in (m.MODULE_PATH, m.SCRIPT_PATH, m.CHECKER_PATH):
            self.assertEqual(undefined_globals((ROOT / name).read_text(), name), set())
        tree = ast.parse((ROOT / m.CHECKER_PATH).read_text())
        imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertFalse(any(name and name.startswith("momentumbot") for name in imports))


if __name__ == "__main__":
    unittest.main()
