from copy import deepcopy
from decimal import localcontext
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

from momentumbot.research import sealed_historical_account_exit_waiting_v01 as m
from tests.test_sealed_historical_management_fill_feedback_v01 import fixture as entry_fixture, record, minute_bar, BASE, SECOND
from tests.test_sealed_historical_account_scheduler_v01 import spec, repin, attach
from tests.test_sealed_historical_account_continuity_v01 import case_programs, empty_program
from tests.test_sealed_historical_account_replay_v01 import fixture, verify_fixture
from tests.test_sealed_historical_account_risk_projection_v01 import run_fixture as risk_fixture

ROOT = Path(__file__).resolve().parents[1]
MS = 1_000_000


def repin_tape(tape):
    tape["quote_records"].sort(key=lambda q: q["ts_recv_ns"])
    for index, row in enumerate(tape["quote_records"]):
        row.update(sequence=index, source_record_index=index,
            source_request_sha256=m.canonical_fingerprint(tape["quote_request"]))
    return m.canonical_fingerprint(tape)


def waiting_args(**kwargs):
    args = entry_fixture(**kwargs)
    rows = args["tape"]["quote_records"]
    rows[2]["ts_recv_ns"] = BASE + SECOND + 200 * MS
    rows[3]["ts_recv_ns"] = BASE + SECOND + 300 * MS
    args["expected_tape_sha256"] = repin_tape(args["tape"])
    return args


def submit(engine, args, intent):
    return engine.submit_intent(intent, tape=args["tape"], expected_tape_sha256=args["expected_tape_sha256"])


def start_wait(**kwargs):
    args = waiting_args(**kwargs)
    engine = m._Management(**args)
    intent = engine.observe_trade(record(SECOND, 12))
    if submit(engine, args, intent) is not None:
        raise ValueError("fixture did not wait")
    return engine, args, intent


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
    return program, result, manifest, items


def waiting_program(*, expire=False, scenario="l1-conservative-v0.1", account="main_account"):
    value = spec(quantity=10 if account == "main_account" else 2, bars=[],
        trades=[record(SECOND, 8), record(SECOND + 100 * MS, 8, 1), record(SECOND + 220 * MS, 8, 2)],
        target_fill=0, scenario=scenario, account=account)
    rows = value["exit_tape"]["quote_records"]
    rows[2]["ts_recv_ns"] = BASE + SECOND + 200 * MS
    rows[3]["ts_recv_ns"] = BASE + SECOND + 300 * MS
    for row in rows[2:]:
        row.update(bid_px_nanos=9_000_000_000, ask_px_nanos=9_010_000_000, bid_size=1000)
    arrival_quote = deepcopy(rows[3])
    arrival_quote["ts_recv_ns"] = BASE + SECOND + 440 * MS
    rows.insert(4, arrival_quote)
    if expire:
        value["exit_tape"]["quote_records"] = rows[:2]
    return attach(empty_program(scenario=scenario, account=account), 0, repin(value))


class WaitingManagementTests(unittest.TestCase):
    def test_stale_reference_waits_without_reserving_or_consuming_attempt(self):
        engine, args, intent = start_wait()
        value = engine.snapshot()
        self.assertEqual(value["outstanding_intent"], intent)
        self.assertEqual((value["target_attempted"], value["full_exit_attempted"], value["pending_order"], value["reserved_sell_quantity"]), (False, False, False, 0))
        self.assertEqual(value["remaining_quantity"], 10)
        self.assertEqual([e["event_type"] for e in engine._wait_log], ["wait_started"])

    def test_no_future_quote_then_first_fresh_print_submits_latched_target(self):
        engine, args, origin = start_wait()
        self.assertIsNone(engine.observe_trade(record(SECOND + 199 * MS, 11, 1)))
        intent = engine.observe_trade(record(SECOND + 220 * MS, 11, 2))
        self.assertEqual(intent["waiting_signal"], origin)
        self.assertEqual(intent["reason"], "first_target")
        order = submit(engine, args, intent)
        self.assertEqual(order["decision_ts_ns"], BASE + SECOND + 220 * MS)
        self.assertEqual(order["order_id"], "exit-" + intent["content_sha256"])
        self.assertTrue(engine.snapshot()["target_attempted"])
        self.assertFalse(engine.snapshot()["full_exit_attempted"])

    def test_ineligible_print_does_not_reconsider_but_clean_odd_lot_does(self):
        engine, args, _ = start_wait()
        self.assertIsNone(engine.observe_trade(record(SECOND + 210 * MS, 8, 1, ["Z"])))
        intent = engine.observe_trade(record(SECOND + 220 * MS, 11, 2, ["I"]))
        self.assertEqual(intent["reason"], "first_target")
        submit(engine, args, intent)

    def test_stop_supersedes_waiting_target_and_preserves_origin(self):
        engine, args, origin = start_wait()
        self.assertIsNone(engine.observe_trade(record(SECOND + 100 * MS, 8, 1)))
        intent = engine.observe_trade(record(SECOND + 220 * MS, 11, 2))
        self.assertEqual((intent["reason"], intent["quantity"]), ("initial_stop", 10))
        self.assertEqual(intent["waiting_signal"]["decision_ts_ns"], BASE + SECOND + 100 * MS)
        self.assertEqual(intent["original_waiting_signal_content_sha256"], origin["content_sha256"])
        submit(engine, args, intent)
        self.assertEqual((engine._target_attempted, engine._full_attempted), (False, True))
        self.assertEqual([e["event_type"] for e in engine._wait_log], ["wait_started", "wait_superseded", "wait_submitted"])

    def test_completed_red_bar_supersedes_target_but_never_stop(self):
        for first_price, expected in ((11, "first_red_candle"), (8, "initial_stop")):
            engine, args, _ = start_wait()
            self.assertIsNone(engine.observe_trade(record(SECOND + 100 * MS, first_price, 1)))
            engine.observe_bar(minute_bar())
            self.assertIsNone(engine.observe_trade(record(61 * SECOND, 11, 2)))
            self.assertEqual(engine._waiting["signal"]["reason"], expected)

    def test_account_risk_latch_can_supersede_target_but_stop_has_priority(self):
        engine, args, _ = start_wait()
        engine._latched = "account_risk_flatten"  # Parent account guard sets this before observing a print.
        self.assertIsNone(engine.observe_trade(record(SECOND + 100 * MS, 11, 1)))
        self.assertEqual(engine._waiting["signal"]["reason"], "account_risk_flatten")
        intent = engine.observe_trade(record(SECOND + 220 * MS, 8, 2))
        self.assertEqual(intent["reason"], "initial_stop")

    def test_freshness_is_inclusive_and_native_ties_keep_last_record(self):
        args = waiting_args()
        extra = deepcopy(args["tape"]["quote_records"][2])
        extra["bid_px_nanos"] -= 1
        args["tape"]["quote_records"].insert(3, extra)
        pin = repin_tape(args["tape"])
        index = m._ReferenceIndex.build(args["window"], BASE + SECOND, args["tape"], pin)
        at = BASE + SECOND + 200 * MS
        self.assertEqual(index.reference(args["window"], at)["source_record_index"], 3)
        # Use the earlier entry reference to isolate the exact freshness boundary.
        last_entry = args["tape"]["quote_records"][1]["ts_recv_ns"]
        self.assertIsNotNone(index.reference(args["window"], last_entry + 100 * MS))
        self.assertIsNone(index.reference(args["window"], last_entry + 100 * MS + 1))

    def test_reference_index_is_immutable_and_matches_frozen_capture(self):
        args = waiting_args()
        index = m._ReferenceIndex.build(args["window"], BASE + SECOND, args["tape"], args["expected_tape_sha256"])
        self.assertIs(deepcopy(index), index)
        with self.assertRaises(AttributeError):
            index.quotes[0].bid_size = 100
        for offset in (0, 190 * MS, SECOND, SECOND + 199 * MS, SECOND + 200 * MS, SECOND + 300 * MS):
            at = BASE + offset
            try:
                _, reference, _ = m.feedback._quote_window(args["window"], at, args["tape"], args["expected_tape_sha256"])
            except ValueError as exc:
                self.assertEqual(str(exc), "fresh nonhalted decision reference unavailable")
                self.assertIsNone(index.reference(args["window"], at))
            else:
                self.assertEqual(index.reference(args["window"], at)["source_record_index"], reference.source_record_index)

    def test_known_halt_waits_and_unknown_status_is_not_a_wait(self):
        for status in ("N", "~"):
            args = waiting_args()
            args["tape"]["status_records"].append({"symbol": "SYNTHETIC", "ts_recv_ns": BASE + 600 * MS, "action": 1, "is_trading": status})
            args["expected_tape_sha256"] = repin_tape(args["tape"])
            engine = m._Management(**args)
            intent = engine.observe_trade(record(SECOND + 220 * MS, 8))
            if status == "N":
                self.assertIsNone(submit(engine, args, intent))
            else:
                with self.assertRaisesRegex(ValueError, "quote/status input unavailable"):
                    submit(engine, args, intent)
                self.assertIsNone(engine._waiting)

    def test_unknown_status_in_frozen_execution_tail_still_fails_closed(self):
        engine, args, _ = start_wait()
        changed = deepcopy(args["tape"])
        changed["status_records"].append({"symbol": "SYNTHETIC", "ts_recv_ns": BASE + 1700 * MS, "action": 1, "is_trading": "~"})
        index = m._ReferenceIndex.build(args["window"], BASE + SECOND, changed, repin_tape(changed))
        with self.assertRaisesRegex(ValueError, "quote/status input unavailable"):
            index.reference(args["window"], BASE + 1220 * MS)

    def test_tape_mutation_or_wrong_pin_never_becomes_waiting(self):
        args = waiting_args()
        engine = m._Management(**args)
        intent = engine.observe_trade(record(SECOND, 12))
        args["tape"]["quote_records"][0]["bid_size"] += 1
        with self.assertRaisesRegex(ValueError, "quote/status tape differs"):
            submit(engine, args, intent)
        self.assertIsNone(engine._waiting)

    def test_changed_tape_while_waiting_is_rejected(self):
        engine, args, _ = start_wait()
        intent = engine.observe_trade(record(SECOND + 220 * MS, 11, 1))
        args["tape"]["quote_records"][0]["bid_size"] += 1
        args["expected_tape_sha256"] = repin_tape(args["tape"])
        with self.assertRaisesRegex(ValueError, "tape changed while waiting"):
            submit(engine, args, intent)

    def test_window_expiry_preserves_open_intent_and_shares(self):
        engine, args, origin = start_wait()
        last = args["window"]["end_ns"] - m.TAIL_NS - 1
        engine.settle(last)
        self.assertFalse(engine._waiting["expired"])
        engine.settle(last + 1)
        engine.settle(args["window"]["end_ns"] - 1)
        value = engine.snapshot()
        self.assertEqual(value["outstanding_intent"], origin)
        self.assertEqual((value["remaining_quantity"], value["target_attempted"], value["full_exit_attempted"]), (10, False, False))
        self.assertEqual([e["event_type"] for e in engine._wait_log], ["wait_started", "wait_expired"])

    def test_first_signal_without_full_tail_still_fails(self):
        args = waiting_args()
        engine = m._Management(**args)
        intent = engine.observe_trade(record(960 * SECOND - m.TAIL_NS, 8))
        with self.assertRaisesRegex(ValueError, "outside original opportunity"):
            submit(engine, args, intent)

    def test_terminal_partial_fill_does_not_retry(self):
        engine, args, _ = start_wait(final_fill=2)
        intent = engine.observe_trade(record(2 * SECOND, 8, 1))
        order = submit(engine, args, intent)
        engine.settle(order["cancel_ack_ts_ns"])
        self.assertEqual(engine.snapshot()["remaining_quantity"], 8)
        self.assertIsNone(engine.observe_trade(record(3 * SECOND, 8, 2)))
        self.assertEqual(sum(e["event_type"] == "sell_submitted" for e in engine._events), 1)


class WaitingAccountTests(unittest.TestCase):
    def test_no_wait_path_objects_match_risk_parent_exactly(self):
        for name, p in case_programs().items():
            if name == "omitted":
                continue
            with self.subTest(name=name):
                program, result, manifest, _ = run_fixture(p)
                self.assertEqual(result, risk_fixture(p)[1])
                verify_fixture(program, result, manifest)

    def test_waiting_closes_and_preserves_audit_after_capacity_release(self):
        for scenario in m.feedback.SCENARIOS:
            for account in ("main_account", "small_account"):
                with self.subTest(scenario=scenario, account=account):
                    p, r, b, _ = run_fixture(waiting_program(scenario=scenario, account=account))
                    first = r["sessions"][0]["runtime"]
                    self.assertIsNone(first["failure"])
                    snapshot = first["reconciliation_snapshot"]
                    self.assertIsNone(snapshot["management"])
                    self.assertEqual([e["event_type"] for e in snapshot["exit_wait_events"]], ["wait_started", "wait_submitted"])
                    self.assertEqual(first["status"], "flat_complete")
                    self.assertTrue(r["path_complete"])
                    verify_fixture(p, r, b)

    def test_expired_wait_blocks_all_later_slots_with_exact_shares(self):
        p, r, b, _ = run_fixture(waiting_program(expire=True))
        runtime = r["sessions"][0]["runtime"]
        self.assertEqual(runtime["status"], "original_window_exhausted_with_unresolved_state")
        self.assertIsNone(runtime["failure"])
        self.assertTrue(runtime["complete_streams_verified"])
        first = r["sessions"][0]["close"]["account_state"]
        for pair in r["sessions"][1:]:
            self.assertTrue(pair["runtime"]["blocked_before_execution"])
            self.assertEqual(pair["close"]["account_state"]["positions"], first["positions"])
        verify_fixture(p, r, b)


class WaitingIndependentTests(unittest.TestCase):
    def result(self, **kwargs):
        import verify_sealed_historical_account_exit_waiting_v01 as checker
        p, r, b, items = run_fixture(waiting_program(**kwargs))
        def resolve(oid):
            s = items[oid]["position"]
            return {"window": s["entry_input"]["window"], "trades": s["trades"], "bars": s["bars"], "tape": s["exit_tape"]}
        return checker, r["sessions"][0]["runtime"], resolve

    def test_independent_wait_sources_and_unchanged_account_checks(self):
        for expire in (True, False):
            for scenario in m.feedback.SCENARIOS:
                checker, runtime, resolve = self.result(expire=expire, scenario=scenario)
                counts = checker.verify_waiting(runtime, resolve)
                self.assertEqual(counts["waits"], 1)
                self.assertEqual(counts["wait_expiries"], int(expire))
                self.assertEqual(counts["wait_submissions"], int(not expire))

    def test_independent_reference_matches_frozen_index_on_status_ties_and_unknowns(self):
        import verify_sealed_historical_account_exit_waiting_v01 as checker
        for status in ("Y", "N", "~"):
            args = waiting_args()
            args["tape"]["status_records"].append({"symbol": "SYNTHETIC", "ts_recv_ns": BASE + 1200 * MS, "action": 1, "is_trading": status})
            args["expected_tape_sha256"] = repin_tape(args["tape"])
            index = m._ReferenceIndex.build(args["window"], BASE + SECOND, args["tape"], args["expected_tape_sha256"])
            separate = checker.References(args["tape"])
            for offset in (0, 190 * MS, 1000 * MS, 1199 * MS, 1200 * MS, 1300 * MS, 1800 * MS):
                at = BASE + offset
                try:
                    expected = index.reference(args["window"], at)
                except ValueError:
                    with self.assertRaises(ValueError):
                        separate.at(args["window"], at)
                else:
                    self.assertEqual(separate.at(args["window"], at), expected)

    def test_rehashed_quote_witness_mutation_is_rejected(self):
        checker, runtime, resolve = self.result()
        bad = deepcopy(runtime)
        events = bad["reconciliation_snapshot"]["exit_wait_events"]
        events[-1]["reference"]["source_record_index"] += 1
        events[-1] = m.seal({k: v for k, v in events[-1].items() if k != "content_sha256"})
        with self.assertRaisesRegex(ValueError, "submission evidence differs"):
            checker.verify_waiting(bad, resolve)

    def test_rehashed_attempt_consumption_before_submission_is_rejected(self):
        checker, runtime, resolve = self.result()
        bad = deepcopy(runtime)
        events = bad["reconciliation_snapshot"]["exit_wait_events"]
        events[0]["full_exit_attempted"] = True
        events[0] = m.seal({k: v for k, v in events[0].items() if k != "content_sha256"})
        with self.assertRaisesRegex(ValueError, "attempt flags"):
            checker.verify_waiting(bad, resolve)

    def test_rehashed_false_expiry_and_dropped_wait_end_are_rejected(self):
        checker, runtime, resolve = self.result(expire=True)
        for mutation in ("early", "missing"):
            bad = deepcopy(runtime)
            events = bad["reconciliation_snapshot"]["exit_wait_events"]
            if mutation == "early":
                events[-1]["timestamp_ns"] = BASE + 3 * SECOND
                events[-1] = m.seal({k: v for k, v in events[-1].items() if k != "content_sha256"})
            else:
                events.pop()
            with self.assertRaises(ValueError):
                checker.verify_waiting(bad, resolve)

    def test_registration_and_source_authority_fail_before_original_access(self):
        with patch.object(m, "verify_bundle", return_value={"freeze_content_sha256": "pin"}):
            with self.assertRaisesRegex(ValueError, "registration pin"):
                m.replay_panel(ROOT, object(), expected_registration_sha256="wrong")
            with self.assertRaisesRegex(ValueError, "original source reader"):
                m.replay_panel(ROOT, object(), expected_registration_sha256="pin")

    def test_failed_submission_preserves_causal_proposal_without_attempt(self):
        original = m._Management.submit_intent
        def fail_ready(engine, intent, **kwargs):
            if "waiting_signal" in intent:
                raise ValueError("synthetic full submission validation failure")
            return original(engine, intent, **kwargs)
        with patch.object(m._Management, "submit_intent", fail_ready):
            checker, runtime, resolve = self.result()
        self.assertEqual(runtime["failure"]["stage"], "executable_exit_evidence")
        engine = runtime["reconciliation_snapshot"]["management"]
        self.assertIn("waiting_signal", engine["outstanding_intent"])
        self.assertFalse(engine["full_exit_attempted"])
        counts = checker.verify_waiting(runtime, resolve)
        self.assertEqual((counts["waits"], counts["wait_submissions"]), (1, 0))

    def test_delayed_submission_after_an_earlier_fresh_print_is_rejected(self):
        checker, runtime, resolve = self.result()
        def earlier(oid):
            data = deepcopy(resolve(oid))
            data["trades"][1]["timestamp_ns"] = BASE + 1210 * MS
            return data
        with self.assertRaisesRegex(ValueError, "not first eligible"):
            checker.verify_waiting(runtime, earlier)

    def test_supersession_is_independently_reconstructed(self):
        import verify_sealed_historical_account_exit_waiting_v01 as checker
        p = waiting_program()
        position = p["sessions"][0]["opportunities"][0]["position"]
        position["trades"][0]["record"]["p"] = 12
        repin(position)
        program, result, manifest, items = run_fixture(p)
        def resolve(oid):
            s = items[oid]["position"]
            return {"window": s["entry_input"]["window"], "trades": s["trades"], "bars": s["bars"], "tape": s["exit_tape"]}
        runtime = result["sessions"][0]["runtime"]
        verify_fixture(program, result, manifest)
        self.assertEqual(checker.verify_waiting(runtime, resolve)["wait_supersessions"], 1)

    def test_registration_reproduces_and_metadata_build_never_opens_originals(self):
        with patch.object(m.binding, "OriginalSources", side_effect=AssertionError("metadata only")):
            self.assertTrue(m.verify_bundle(ROOT, ROOT / m.OUTPUT_PATH)["verification_passed"])
        self.assertEqual(m.mechanics()["retry_clock"], "subsequent_eligible_SIP_prints_only_original_phase_and_record_order")
        self.assertFalse(m.RUNTIME_BOUNDARY["financial_metrics_eligible"])

    def test_mutated_parent_or_child_invalidates_registration(self):
        original = m.file_sha
        for target in (m.risk.MODULE_PATH, m.MODULE_PATH):
            with patch.object(m, "file_sha", side_effect=lambda p: "0" * 64 if p == ROOT / target else original(p)):
                with self.assertRaises(ValueError):
                    m.validate_registration(ROOT)

    def test_runtime_output_is_external_and_write_once(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "waiting"
            m.write_files(ROOT, output, {"synthetic.json": b"{}\n"})
            with self.assertRaises(FileExistsError):
                m.write_files(ROOT, output, {"synthetic.json": b"changed\n"})
            self.assertEqual((output / "synthetic.json").read_bytes(), b"{}\n")


if __name__ == "__main__":
    unittest.main()
