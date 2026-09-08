from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from momentumbot.research import sealed_historical_account_scheduler_v01 as m
from tests.test_sealed_historical_account_state_producer_v01 import empty_program as parent_program, position_spec, reseal, BASE, SECOND, record
from tests.test_sealed_historical_account_valuation_v01 import fixture as valued_fixture

ROOT = Path(__file__).resolve().parents[1]
MS = 1_000_000


def empty_program(**kwargs):
    original = parent_program(**kwargs)
    return m.seal({**{k: v for k, v in original.items() if k not in {"content_sha256", "contract_id", "artifact_type", "sessions"}},
        "contract_id": m.CONTRACT_ID, "artifact_type": "chronological_account_source_program",
        "sessions": [{"session_id": s["session_id"], "opportunities": []} for s in original["sessions"]]})


def repin(spec):
    decision = spec["entry_input"]["source_decision"]
    decision["plan_id"] = "plan-" + m.canonical_fingerprint({"activation_id": decision["activation_id"], "plan": decision["plan"]})
    window = spec["entry_input"]["window"]
    day = window["opportunity"]["trading_date"]
    window["opportunity"] = m.accounts.availability.plan._opportunities(m.seal({"trading_date": day, "decisions": [decision]}))[0]
    for tape in (spec["entry_input"]["tape"], spec["exit_tape"]):
        for index, row in enumerate(tape["quote_records"]):
            row.update(source_request_sha256=m.canonical_fingerprint(tape["quote_request"]), source_record_index=index, sequence=index)
    spec["entry_input"]["expected_tape_sha256"] = m.canonical_fingerprint(spec["entry_input"]["tape"])
    spec["expected_exit_tape_sha256"] = m.canonical_fingerprint(spec["exit_tape"])
    tape = spec["exit_tape"]
    spec["exit_group"] = m.runner.derive_exit_plan([window], [tape["quote_request"], tape["status_request"]])["groups"][0]
    spec["expected_exit_group_sha256"] = m.canonical_fingerprint(spec["exit_group"])
    spec["expected_streams"] = {"raw_sip_1m_bars": m.runner.stream_commitment(spec["bars"]),
        "sip_transactions": m.runner.stream_commitment(spec["trades"])}
    return spec


def spec(tag="A", **kwargs):
    result = position_spec(**kwargs)
    old = result["entry_input"]["source_decision"]["symbol"]
    def rename(value):
        if isinstance(value, dict): return {k: rename(v) for k, v in value.items()}
        if isinstance(value, list): return [rename(v) for v in value]
        if isinstance(value, str): return value.replace(old, "SYNTHETIC" + tag)
        return value
    result = rename(result)
    result["entry_input"]["source_decision"]["activation_id"] += "-" + tag
    return repin(result)


def attach(program, index, position, *, rank=1):
    op = position["entry_input"]["window"]["opportunity"]
    source = position["entry_input"]["source_decision"]
    slot = program["slots"][index]
    slot["opportunity_inputs"].append({"opportunity_id": op["opportunity_id"], "availability_content_sha256": "b" * 64,
        "input_status": "available", "reason": "synthetic_available"})
    slot["source_date_has_no_micro_decisions"] = False
    program["slots"][index] = reseal(slot)
    candidate = {"symbol": op["symbol"], "timestamp": source["candidate_qualified_at"], "price": 10,
        "cumulative_volume": 1_000_000, "relative_volume": 10, "percent_gain": 50, "float_shares": 5_000_000,
        "has_fresh_news": True, "top_gainer_rank": rank, "quality": "a_quality", "pillars": {}, "reasons": []}
    program["sessions"][index]["opportunities"].append({"candidate": candidate, "position": position})
    return reseal(program)


def replay(program):
    return m.replay_path(program, expected_program_content_sha256=program["content_sha256"])


def verify(program, result):
    return m.verify_path(program, result, expected_program_content_sha256=program["content_sha256"],
        expected_result_content_sha256=result["content_sha256"])


def runtime(result, index=0): return result["sessions"][index]["runtime"]
def state(result, index=0): return result["sessions"][index]["close"]["account_state"]
def decisions(result): return [e for e in runtime(result)["events"] if e["event_type"] == "opportunity_disposition"]


def changed_entry(kind):
    value = spec()
    tape = value["entry_input"]["tape"]
    row = tape["quote_records"][1]
    row.update(bid_px_nanos=10_990_000_000, ask_px_nanos=11_000_000_000)
    if kind == "delayed":
        added = deepcopy(row)
        added.update(ts_recv_ns=BASE + 250 * MS, bid_px_nanos=9_990_000_000, ask_px_nanos=10_000_000_000)
        tape["quote_records"].insert(2, added)
    value["exit_tape"] = deepcopy(tape)
    return repin(value)


def cases():
    result = {}
    for scenario in m.feedback.SCENARIOS:
        p = attach(empty_program(count=2, scenario=scenario), 0, spec(final_price="11", scenario=scenario))
        p = attach(p, 0, spec("B", offset=3 * SECOND, final_price="11", scenario=scenario))
        result[scenario + "-overlap"] = p
    for kind in ("delayed", "unfilled"):
        p = attach(empty_program(count=1), 0, changed_entry(kind))
        result[kind] = attach(p, 0, spec("B", offset=100 * MS))
    result["collision"] = attach(attach(empty_program(count=1), 0, spec("A"), rank=2), 0, spec("B"), rank=1)
    result["partial_carry"] = attach(empty_program(count=2), 0, spec(target_fill=2, final_fill=3))
    p = attach(empty_program(count=2), 0, spec(final_price="11"))
    result["reentry_unresolved"] = attach(p, 0, spec("A", offset=3 * SECOND))
    broken = spec(trades=[record(10 * MS, 10), record(20 * MS, 10, 3)])
    result["pending_input_failure"] = attach(empty_program(count=2), 0, broken)
    p = attach(empty_program(count=2), 0, spec())
    p["sessions"][0]["opportunities"] = []
    result["omitted"] = reseal(p)
    p = empty_program(count=2)
    slot = p["slots"][0]
    slot.update(opportunity_inputs=[{"opportunity_id": "synthetic-unavailable", "availability_content_sha256": "c" * 64,
        "input_status": "unavailable", "reason": "source_unavailable"}], unavailable_opportunity_count=1, source_date_has_no_micro_decisions=False)
    p["slots"][0] = reseal(slot)
    result["unavailable"] = reseal(p)
    p = empty_program(count=1)
    p = attach(p, 0, spec("A", quantity=70, target_fill=0, final_fill=70, final_price="10.0005", trades=[record(2 * SECOND, 8)]))
    p = attach(p, 0, spec("B", offset=3 * SECOND, quantity=70, target_fill=0, final_fill=70, final_price="10.000285714", trades=[record(2 * SECOND, 8)]))
    p = attach(p, 0, spec("C", offset=6 * SECOND, quantity=70, target_fill=70, trades=[record(SECOND, 11)]))
    result["risk_flatten"] = p
    return result


def synthetic_vectors():
    programs = cases()
    for account in ("main_account", "small_account"):
        for horizon in (1, 5, 10):
            for scenario in m.feedback.SCENARIOS:
                p = empty_program(account=account, horizon=horizon, scenario=scenario)
                programs["empty-" + p["path_id"]] = p
    vectors = []
    for name, p in programs.items():
        result = replay(p)
        vectors.append({"name": name, "program": p, "result": result, "verification": verify(p, result)})
    return m.seal({"contract_id": m.CONTRACT_ID, "synthetic_only": True, "vectors": vectors, **m.BOUNDARY})


class SchedulerMechanicsTests(unittest.TestCase):
    def test_all_thirty_empty_slots_seed_once(self):
        for account in ("main_account", "small_account"):
            p = empty_program(account=account)
            r = replay(p)
            self.assertEqual(r["session_count"], 30)
            self.assertEqual(r["seed_application_count"], 1)
            self.assertTrue(all(state(r, i) == r["initial_account_state"] for i in range(30)))

    def test_overlapping_windows_release_before_old_window_end(self):
        for scenario in m.feedback.SCENARIOS:
            p = cases()[scenario + "-overlap"]
            r = replay(p)
            self.assertIsNone(runtime(r)["failure"])
            self.assertEqual([d["disposition"] for d in decisions(r)], ["entry_submitted", "entry_submitted"])
            self.assertEqual(state(r)["equity_usd"], "30029.98")
            self.assertEqual(state(r, 1)["equity_usd"], "30029.98")
            self.assertEqual(state(r)["cumulative_fees_usd"], "0.02")
            self.assertTrue(verify(p, r)["verification_passed"])

    def test_exact_time_collision_uses_frozen_rank_not_input_order(self):
        p = cases()["collision"]
        first = replay(p)
        self.assertEqual([d["disposition"] for d in decisions(first)], ["entry_submitted", "blocked_capacity"])
        self.assertEqual(runtime(first)["reconciliation_snapshot"]["journal"][0]["execution_evidence"]["symbol"], "SYNTHETICB")
        p["sessions"][0]["opportunities"].reverse()
        second = replay(reseal(p))
        self.assertEqual(decisions(first), decisions(second))

    def test_delayed_entry_does_not_expose_future_fill_or_cash(self):
        r = replay(cases()["delayed"])
        decision = decisions(r)[1]
        self.assertEqual(decision["disposition"], "blocked_capacity")
        self.assertEqual(decision["account_before"]["confirmed_quantity"], 0)
        self.assertEqual(decision["account_before"]["cash_usd"], "30000.00")
        event = next(e for e in runtime(r)["events"] if e["event_type"] == "entry_fill_confirmed")
        self.assertEqual(event["at_ns"], BASE + 250 * MS)

    def test_unfilled_entry_holds_capacity_until_ack_and_has_no_fee(self):
        r = replay(cases()["unfilled"])
        self.assertIsNone(runtime(r)["failure"])
        self.assertEqual(decisions(r)[1]["disposition"], "blocked_capacity")
        self.assertEqual(state(r)["equity_usd"], "30000.00")
        self.assertEqual(state(r)["cumulative_fees_usd"], "0.00")
        ack = next(e for e in runtime(r)["events"] if e["event_type"] == "entry_cancel_acknowledged")
        self.assertEqual(ack["confirmed_quantity"], 0)
        self.assertGreater(ack["cancelled_quantity"], 0)

    def test_entry_ack_tie_cannot_recycle_capacity_but_next_ns_can(self):
        p = attach(empty_program(count=1), 0, changed_entry("unfilled"))
        baseline = replay(p)
        ack = next(e["at_ns"] for e in runtime(baseline)["events"] if e["event_type"] == "entry_cancel_acknowledged")
        for delta, expected in ((0, "blocked_capacity"), (1, "entry_submitted")):
            q = attach(deepcopy(p), 0, spec("B", offset=ack - BASE + delta))
            self.assertEqual(decisions(replay(q))[1]["disposition"], expected)

    def test_exit_ack_tie_cannot_recycle_capacity_but_next_ns_can(self):
        p = attach(empty_program(count=1), 0, spec(final_price="11"))
        baseline = replay(p)
        ack = next(e["at_ns"] for e in runtime(baseline)["events"] if e["event_type"] == "capacity_released")
        for delta, expected in ((0, "blocked_capacity"), (1, "entry_submitted")):
            q = attach(deepcopy(p), 0, spec("B", offset=ack - BASE + delta))
            self.assertEqual(decisions(replay(q))[1]["disposition"], expected)

    def test_future_entry_price_cannot_change_earlier_scarcity(self):
        p = cases()["delayed"]
        before = decisions(replay(p))[1]
        value = p["sessions"][0]["opportunities"][0]["position"]
        value["entry_input"]["tape"]["quote_records"][2]["ask_px_nanos"] = 10_005_000_000
        repin(value)
        after = decisions(replay(reseal(p)))[1]
        self.assertEqual(before["account_before"], after["account_before"])
        self.assertEqual(before["disposition"], after["disposition"])

    def test_partial_position_survives_next_day_without_seed_reset(self):
        r = replay(cases()["partial_carry"])
        self.assertEqual(state(r)["positions"][0]["quantity"], 5)
        self.assertEqual(state(r, 1)["positions"], state(r)["positions"])
        self.assertEqual(state(r, 1)["buying_power_usd"], "29950.98")
        self.assertTrue(runtime(r, 1)["blocked_before_execution"])

    def test_unconfirmed_entry_is_preserved_after_stream_failure(self):
        r = replay(cases()["pending_input_failure"])
        self.assertIsNotNone(runtime(r)["failure"])
        self.assertEqual(state(r)["buying_power_usd"], "30000.00")
        self.assertEqual(state(r)["positions"], [])
        self.assertEqual(state(r)["pending_orders"][0]["kind"], "unconfirmed_entry_order")
        self.assertEqual(state(r, 1)["pending_orders"], state(r)["pending_orders"])
        self.assertIsNone(state(r)["equity_usd"])

    def test_same_symbol_reentry_is_explicit_blocking_dependency(self):
        r = replay(cases()["reentry_unresolved"])
        self.assertEqual(decisions(r)[1]["disposition"], "unsupported_same_symbol_reentry")
        self.assertTrue(any(x["kind"] == "unsupported_same_symbol_reentry" for x in state(r)["unresolved_inputs"]))
        self.assertTrue(runtime(r, 1)["blocked_before_execution"])

    def test_missing_available_source_blocks_but_unavailable_receipt_does_not(self):
        missing = replay(cases()["omitted"])
        absent = replay(cases()["unavailable"])
        self.assertTrue(runtime(missing, 1)["blocked_before_execution"])
        self.assertFalse(runtime(absent, 1)["blocked_before_execution"])
        self.assertEqual(state(absent)["unresolved_inputs"][0]["kind"], "unavailable_input")

    def test_risk_guard_executes_one_frozen_terminal_attempt(self):
        r = replay(cases()["risk_flatten"])
        self.assertIsNone(runtime(r)["failure"])
        orders = [e for e in runtime(r)["events"] if e["event_type"] == "sell_submitted" and e["reason"] == "account_risk_flatten"]
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["order"]["quantity"], 70)
        self.assertEqual(state(r)["positions"], [])
        self.assertTrue(runtime(r)["reconciliation_snapshot"]["ledger"]["account"]["locked"])

    def test_trailing_old_source_is_verified_after_capacity_reuse(self):
        first = spec(final_price="11", trades=[record(SECOND, 12), record(2 * SECOND, 8, 1), record(900 * SECOND, 10, 2)])
        first["expected_streams"]["sip_transactions"]["sha256"] = "0" * 64
        p = attach(attach(empty_program(count=1), 0, first), 0, spec("B", offset=3 * SECOND))
        r = replay(p)
        self.assertEqual(len(runtime(r)["reconciliation_snapshot"]["completed_positions"]), 2)
        self.assertIsNotNone(runtime(r)["failure"])
        self.assertFalse(runtime(r)["complete_streams_verified"])
        self.assertEqual(state(r)["buying_power_usd"], "30019.98")

    def test_known_profit_giveback_lock_blocks_later_entry(self):
        p = attach(attach(empty_program(count=1), 0, spec()), 0, spec("B", offset=3 * SECOND))
        r = replay(p)
        self.assertEqual(decisions(r)[1]["disposition"], "blocked_account_lock")
        self.assertEqual(runtime(r)["reconciliation_snapshot"]["ledger"]["account"]["lock_reason"], "profit_giveback")

    def test_flat_valuation_handoff_replays_parent_and_keeps_capital(self):
        f = valued_fixture(kind="profit")
        slot = f["program"]["slots"][f["result"]["session_count"]]
        source = {"session_id": slot["session_id"], "opportunities": []}
        r = m.continue_valued_session(f["program"], f["result"], f["inputs"], source,
            expected_program_content_sha256=f["program"]["content_sha256"], expected_result_content_sha256=f["result"]["content_sha256"],
            expected_inputs_content_sha256=f["inputs"]["content_sha256"], expected_session_sha256=m.canonical_fingerprint(source))
        self.assertEqual(r["session"]["close"]["account_state"]["equity_usd"], "30014.98")
        self.assertEqual(r["seed_application_count"], 0)

    def test_open_valuation_handoff_cannot_extend_original_window(self):
        f = valued_fixture()
        slot = f["program"]["slots"][f["result"]["session_count"]]
        source = {"session_id": slot["session_id"], "opportunities": []}
        r = m.continue_valued_session(f["program"], f["result"], f["inputs"], source,
            expected_program_content_sha256=f["program"]["content_sha256"], expected_result_content_sha256=f["result"]["content_sha256"],
            expected_inputs_content_sha256=f["inputs"]["content_sha256"], expected_session_sha256=m.canonical_fingerprint(source))
        self.assertTrue(r["valuation"]["account_valuation"]["valuation_complete"])
        self.assertTrue(r["session"]["runtime"]["blocked_before_execution"])
        self.assertEqual(r["session"]["close"]["account_state"]["positions"], r["valuation"]["source_account_state"]["positions"])

    def test_future_candidate_is_rejected(self):
        p = cases()["collision"]
        p["sessions"][0]["opportunities"][0]["candidate"]["timestamp"] = "2025-05-30T14:00:00Z"
        r = replay(reseal(p))
        self.assertIsNotNone(runtime(r)["failure"])
        self.assertEqual(runtime(r)["reconciliation_snapshot"]["journal"], [])

    def test_source_pin_tamper_and_rehashed_result_tamper_are_rejected(self):
        p = cases()["collision"]
        with self.assertRaisesRegex(ValueError, "independent caller"):
            m.replay_path(p, expected_program_content_sha256="0" * 64)
        r = replay(p)
        r["sessions"][0]["close"]["account_state"]["buying_power_usd"] = "1.00"
        with self.assertRaises(ValueError): verify(p, reseal(r))

    def test_retrospective_inputs_and_historical_mode_rejected(self):
        p = empty_program(count=1)
        p["sessions"][0]["ross_fill"] = 10
        with self.assertRaises(ValueError): replay(reseal(p))
        p = empty_program(count=1); p["input_scope"] = "historical"
        with self.assertRaisesRegex(ValueError, "synthetic"): replay(reseal(p))

    def test_parent_and_input_objects_are_unchanged(self):
        p = cases()["collision"]
        original = deepcopy(p)
        replay(p)
        self.assertEqual(p, original)

    def test_future_reconciliation_failure_is_deferred_and_preserves_feedback(self):
        p = cases()["delayed"]
        value = p["sessions"][0]["opportunities"][0]["position"]
        value["entry_input"]["tape"]["quote_records"][2].update(bid_px_nanos=7_990_000_000, ask_px_nanos=8_000_000_000)
        repin(value)
        r = replay(reseal(p))
        self.assertEqual(decisions(r)[1]["disposition"], "blocked_capacity")
        self.assertEqual(decisions(r)[1]["account_before"]["cash_usd"], "30000.00")
        self.assertEqual(runtime(r)["failure"]["stage"], "feedback")
        pending = state(r)["pending_orders"][0]
        self.assertEqual(pending["unreconciled_execution_feedback"]["known_at_ns"], BASE + 250 * MS)
        self.assertEqual(pending["unreconciled_execution_feedback"]["execution"]["filled_quantity"], 10)

    def test_entry_fill_tie_is_still_reserved_and_not_yet_booked(self):
        p = attach(empty_program(count=1), 0, changed_entry("delayed"))
        p = attach(p, 0, spec("B", offset=250 * MS))
        row = decisions(replay(p))[1]
        self.assertEqual(row["account_before"]["confirmed_quantity"], 0)
        self.assertEqual(row["account_before"]["cash_usd"], "30000.00")

    def test_risk_exit_partial_fill_has_no_automatic_retry(self):
        p = cases()["risk_flatten"]
        last = p["sessions"][0]["opportunities"][-1]["position"]
        for tape in (last["entry_input"]["tape"], last["exit_tape"]):
            for row in tape["quote_records"][2:4]: row["bid_size"] = int(Decimal(1) / m.feedback.SCENARIOS["l1-conservative-v0.1"][0].displayed_size_participation)
        repin(last)
        r = replay(reseal(p))
        self.assertIsNone(runtime(r)["failure"])
        self.assertEqual(state(r)["positions"][0]["quantity"], 69)
        self.assertEqual(sum(e.get("reason") == "account_risk_flatten" for e in runtime(r)["events"]), 1)

    def test_risk_exit_missing_tape_retains_unsubmitted_intent(self):
        p = cases()["risk_flatten"]
        last = p["sessions"][0]["opportunities"][-1]["position"]
        # Valid complete source, but no causal executable reference at the risk print.
        last["exit_tape"]["quote_records"] = last["exit_tape"]["quote_records"][:2]
        repin(last)
        r = replay(reseal(p))
        self.assertEqual(runtime(r)["failure"]["stage"], "executable_exit_evidence")
        self.assertEqual(state(r)["positions"][0]["quantity"], 70)
        self.assertTrue(any(x["kind"] == "unsubmitted_exit_intent" for x in state(r)["unresolved_inputs"]))

    def test_subcent_cash_survives_next_session(self):
        p = attach(empty_program(count=2), 0, spec(final_price="9.003"))
        r = replay(p)
        self.assertEqual(state(r)["equity_usd"], "30004.995")
        self.assertEqual(state(r, 1)["equity_usd"], "30004.995")

    def test_invalid_candidate_numeric_shapes_fail_before_execution(self):
        for key, value in (("price", True), ("top_gainer_rank", 0), ("float_shares", False), ("has_fresh_news", "Y")):
            p = cases()["collision"]
            p["sessions"][0]["opportunities"][0]["candidate"][key] = value
            r = replay(reseal(p))
            self.assertIsNotNone(runtime(r)["failure"])
            self.assertEqual(runtime(r)["reconciliation_snapshot"]["journal"], [])

    def test_wrong_source_decision_hash_blocks_submission(self):
        p = attach(empty_program(count=1), 0, spec())
        p["sessions"][0]["opportunities"][0]["position"]["entry_input"]["source_decision"]["plan"]["stop_price"] = 8
        r = replay(reseal(p))
        self.assertIsNotNone(runtime(r)["failure"])
        self.assertEqual(runtime(r)["events"], [])

    def test_exact_slot_order_and_foreign_path_rejected(self):
        p = empty_program(count=2)
        p["slots"][0], p["slots"][1] = p["slots"][1], p["slots"][0]
        with self.assertRaises(ValueError): replay(reseal(p))
        p = empty_program(count=1); p["path_id"] += "-foreign"
        with self.assertRaises(ValueError): replay(reseal(p))

    def test_duplicate_and_unknown_opportunities_fail_closed(self):
        p = cases()["collision"]
        p["sessions"][0]["opportunities"].append(deepcopy(p["sessions"][0]["opportunities"][0]))
        r = replay(reseal(p))
        self.assertIsNotNone(runtime(r)["failure"])
        self.assertEqual(runtime(r)["reconciliation_snapshot"]["journal"], [])

    def test_boundary_flags_do_not_claim_complete_historical_integration(self):
        r = replay(empty_program(count=1))
        for key in ("historical_runtime_authorized", "historical_producer_authenticated", "financial_metrics_eligible",
                    "continuous_account_order_integration_verified", "same_symbol_reentry_integrated", "carried_position_execution_resumption_integrated"):
            self.assertFalse(r[key])

    def test_continuation_requires_independent_session_pin(self):
        f = valued_fixture(kind="flat")
        with self.assertRaisesRegex(ValueError, "independent caller pin"):
            m.continue_valued_session(f["program"], f["result"], f["inputs"], {},
                expected_program_content_sha256=f["program"]["content_sha256"], expected_result_content_sha256=f["result"]["content_sha256"],
                expected_inputs_content_sha256=f["inputs"]["content_sha256"], expected_session_sha256="0" * 64)
        source = {"session_id": f["inputs"]["next_session_id"], "opportunities": [{"ross_fill": 10}]}
        with patch.object(m.valuation, "value_next_session", side_effect=AssertionError("no valuation before input boundary")):
            with self.assertRaisesRegex(ValueError, "retrospective"):
                m.continue_valued_session(f["program"], f["result"], f["inputs"], source,
                    expected_program_content_sha256=f["program"]["content_sha256"], expected_result_content_sha256=f["result"]["content_sha256"],
                    expected_inputs_content_sha256=f["inputs"]["content_sha256"], expected_session_sha256=m.canonical_fingerprint(source))

    def test_context_preflight_is_exact_frozen_prefix(self):
        import ast
        import inspect
        source = inspect.getsource(m.feedback.bind_entry_evidence)
        node = ast.parse(source).body[0]
        start = next(n for n in node.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call))
        end = next(n for n in node.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Tuple) and ast.unparse(n.targets[0]) == "(policy, offset)")
        body = "\n".join(source.splitlines()[start.lineno - 1:end.lineno - 1])
        body = body.replace("_pinned(", "feedback._pinned(").replace("parent.", "feedback.parent.").replace("materialize_account_constraints(", "feedback.materialize_account_constraints(").replace("paper_account_policy(", "feedback.paper_account_policy(")
        self.assertIn(body, inspect.getsource(m._validate_entry_context))


class SchedulerRegistrationTests(unittest.TestCase):
    def test_registration_binds_immutable_parent_and_scope(self):
        self.assertTrue(m.validate_registration(ROOT)["verification_passed"])
        contract = m.expected_contract(ROOT)
        self.assertEqual(contract["parent_commit_sha"], "86733376b10b2a5feb252d174254f4e40fe701ef")
        self.assertEqual(len(contract["frozen_parent_file_sha256"]), 82)
        self.assertFalse(contract["continuous_account_order_integration_verified"])

    def test_all_original_slots_and_unavailable_references_unchanged(self):
        bundle = {name: json.loads(raw) for name, raw in m.build_bundle(ROOT).items()}
        mapping = bundle["scheduler-dependencies.json"]
        parent = m.frozen(ROOT / m.parent.OUTPUT_PATH / "account-state-dependencies.json")
        self.assertEqual(mapping["slots"], parent["slots"])
        self.assertEqual(mapping["session_count"], 360)
        self.assertEqual(mapping["previous_close_dependencies"], 348)
        self.assertEqual(sum(len(s["opportunity_inputs"]) for s in mapping["slots"]), 744)
        self.assertEqual(sum(r["input_status"] == "unavailable" for s in mapping["slots"] for r in s["opportunity_inputs"]), 162)

    def test_metadata_build_cannot_run_mechanics_or_open_market_bundle(self):
        with patch.object(m, "replay_path", side_effect=AssertionError("no runtime")), patch.object(m.feedback.parent.inputs, "ManagementInputBundle", side_effect=AssertionError("no tapes")):
            self.assertEqual(len(m.build_bundle(ROOT)), 4)

    def test_parent_and_implementation_mutations_fail_registration(self):
        original = m.file_sha
        for name in (m.valuation.MODULE_PATH, m.MODULE_PATH):
            with patch.object(m, "file_sha", side_effect=lambda p, n=name: "0" * 64 if str(p).endswith(n) else original(p)):
                with self.assertRaises(ValueError): m.validate_registration(ROOT)

    def test_write_once_rehashed_metadata_and_extra_files_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle"
            self.assertTrue(m.write_bundle(ROOT, out)["verification_passed"])
            with self.assertRaises(FileExistsError): m.write_bundle(ROOT, out)
            path = out / "readiness-report.json"
            value = json.loads(path.read_text()); value["historical_execution_count"] = 1
            path.write_bytes(m.fees.encoded(reseal(value)))
            with self.assertRaisesRegex(ValueError, "reconstruction differs"): m.verify_bundle(ROOT, out)
            (out / "extra").write_text("x")
            with self.assertRaisesRegex(ValueError, "inventory differs"): m.verify_bundle(ROOT, out)

    def test_symlink_and_frozen_output_paths_rejected(self):
        with self.assertRaises(ValueError): m.write_bundle(ROOT, ROOT / m.valuation.OUTPUT_PATH)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "link"; path.symlink_to(Path(tmp), target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"): m.write_bundle(ROOT, path / "out")

    def test_independent_checker_recomputes_and_rejects_rehashed_scarcity(self):
        from verify_sealed_historical_account_scheduler_v01 import verify as independent, verify_events
        vectors = synthetic_vectors()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vectors.json"
            path.write_bytes(m.fees.encoded(vectors))
            report = independent(ROOT, ROOT / m.OUTPUT_PATH, path)
            self.assertTrue(report["verification_passed"])
            self.assertEqual(report["case_count"], 23)
        case = next(v for v in vectors["vectors"] if v["name"] == "collision")
        data = deepcopy(runtime(case["result"]))
        for index, event in enumerate(data["events"]):
            if event["event_type"] == "opportunity_disposition" and event["disposition"] == "blocked_capacity":
                event["account_before"]["capacity_reserved"] = False
                data["events"][index] = reseal(event)
                break
        with self.assertRaisesRegex(ValueError, "reservation or lock"):
            verify_events(case["program"]["sessions"][0], data)

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
