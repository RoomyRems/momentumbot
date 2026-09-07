from __future__ import annotations

import copy
import hashlib
import inspect
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from momentumbot.research import sealed_historical_management_runner_v01 as m
from tests.test_sealed_historical_management_fill_feedback_v01 import fixture, record, minute_bar, BASE, SECOND, repin_context

ROOT = Path(__file__).resolve().parents[1]


def arguments(*, bars=None, trades=None, quantity=10, scenario="l1-conservative-v0.1", target_fill=None, final_fill=None):
    entry = fixture(quantity, scenario=scenario, target_fill=target_fill, final_fill=final_fill)
    bars = [] if bars is None else bars
    trades = [record(SECOND, 12), record(2 * SECOND, 8, 1)] if trades is None else trades
    group = m.derive_exit_plan([entry["window"]], [entry["tape"]["quote_request"], entry["tape"]["status_request"]])["groups"][0]
    return {"entry_arguments": entry, "bars": bars, "trades": trades,
        "expected_streams": {"raw_sip_1m_bars": m.stream_commitment(bars), "sip_transactions": m.stream_commitment(trades)},
        "exit_group": group, "expected_exit_group_sha256": m.canonical_fingerprint(group),
        "exit_tape": copy.deepcopy(entry["tape"]), "expected_exit_tape_sha256": entry["expected_tape_sha256"]}


def repin(args):
    args["expected_exit_tape_sha256"] = m.canonical_fingerprint(args["exit_tape"])
    args["expected_exit_group_sha256"] = m.canonical_fingerprint(args["exit_group"])
    args["expected_streams"] = {"raw_sip_1m_bars": m.stream_commitment(args["bars"]), "sip_transactions": m.stream_commitment(args["trades"])}


def move_final_quotes(args, offset):
    delta = offset - 2 * SECOND
    for row in args["exit_tape"]["quote_records"][4:]:
        row["ts_recv_ns"] += delta
    repin(args)


class RunnerRegistrationTests(unittest.TestCase):
    def test_parent_and_contract_are_exact_and_runtime_closed(self):
        self.assertTrue(m.validate_registration(ROOT)["verification_passed"])
        contract = m.expected_contract(ROOT)
        self.assertEqual(contract["parent_commit_sha"], "d9e5a04b6f9f78ba09fc87c53be2e7b9aa359b89")
        self.assertTrue(contract["position_runner_mechanics_registered"])
        self.assertFalse(contract["historical_runtime_activation_ready"])
        self.assertTrue(all(v is False for v in contract["historical_runtime_dependencies"].values()))

    def test_exact_population_and_bounded_request_counts(self):
        bundle = {n: json.loads(raw) for n, raw in m.build_bundle(ROOT).items()}
        p = bundle["exit-input-request-plan.json"]
        self.assertEqual((len(p["opportunities"]), len(p["groups"]), len(p["new_requests"]), len(p["reuse_candidate_requests"])), (109, 41, 80, 2))
        self.assertEqual(sum(v["group_id"] is None for v in p["opportunities"]), 23)
        self.assertEqual(sum(len(g["members"]) for g in p["groups"]), 86)
        self.assertEqual(p["future_metadata_call_ceiling"], 160)
        self.assertIsNone(p["quoted_cost_usd"])
        reused = [g for g in p["groups"] if g["source_kind"].startswith("existing")]
        self.assertEqual([(g["trading_date"], g["symbol"]) for g in reused], [("2025-07-15", "XAGE")])
        self.assertFalse(reused[0]["source_bytes_verified"])

    def test_every_original_window_date_and_session_is_bound(self):
        prior = m.frozen(ROOT / m.INPUT_REQUIREMENTS)
        paths = m.frozen(ROOT / m.projection.ACCOUNT_PLAN)
        docs = {n: json.loads(raw) for n, raw in m.build_bundle(ROOT).items()}
        index = docs["runner-input-index.json"]
        self.assertEqual(index["original_windows_content_sha256"], m.canonical_fingerprint(prior["opportunity_windows"]))
        self.assertEqual(index["original_dates_content_sha256"], m.canonical_fingerprint(prior["dates"]))
        self.assertEqual(index["session_slots_content_sha256"], m.canonical_fingerprint([s for p in paths["paths"] for s in p["sessions"]]))
        self.assertEqual(index["counts"], prior["counts"])

    def test_metadata_never_reads_source_tapes_or_runs_mechanics(self):
        with patch.object(m, "run_position_mechanics", side_effect=AssertionError("no runtime")), patch.object(m.projection.inputs, "ManagementInputBundle", side_effect=AssertionError("no source tapes")):
            self.assertEqual(len(m.build_bundle(ROOT)), 4)

    def test_ancestor_mutation_cannot_be_rehashed_into_registration(self):
        original = m.file_sha
        with patch.object(m, "file_sha", side_effect=lambda p: "0" * 64 if str(p).endswith(m.feedback.MODULE_PATH) else original(p)):
            with self.assertRaisesRegex(ValueError, "parent differs"):
                m.validate_registration(ROOT)

    def test_implementation_mutation_invalidates_registration(self):
        original = m.file_sha
        with patch.object(m, "file_sha", side_effect=lambda p: "0" * 64 if str(p).endswith(m.MODULE_PATH) else original(p)):
            with self.assertRaisesRegex(ValueError, "registration differs"):
                m.validate_registration(ROOT)

    def test_write_once_and_rehashed_request_tampering_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            self.assertTrue(m.write_bundle(ROOT, out)["verification_passed"])
            with self.assertRaises(FileExistsError): m.write_bundle(ROOT, out)
            p = out / "exit-input-request-plan.json"
            d = json.loads(p.read_bytes()); d["new_requests"][0]["end_ns"] += 1
            p.write_bytes(m.accounts._bytes(m.seal({k: v for k, v in d.items() if k != "content_sha256"})))
            with self.assertRaisesRegex(ValueError, "reconstruction differs"): m.verify_bundle(ROOT, out)

    def test_output_symlink_and_extra_file_rejected(self):
        with self.assertRaises(ValueError): m.write_bundle(ROOT, ROOT / "research/strategy/incorrect")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"; m.write_bundle(ROOT, out)
            alias = Path(tmp) / "alias"; alias.symlink_to(out)
            with self.assertRaises(ValueError): m.verify_bundle(ROOT, alias)
            (out / "extra.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "inventory differs"): m.verify_bundle(ROOT, out)

    def test_historical_gate_fails_before_any_source_access(self):
        with patch.object(m.projection.inputs, "ManagementInputBundle", side_effect=AssertionError("no source access")):
            with self.assertRaisesRegex(ValueError, "dependencies unresolved"):
                m.require_historical_runtime_ready(ROOT)

    def test_cli_offline_verification_and_no_run_or_quote_mode(self):
        for option in ("--validate-registration", "--verify"):
            r = subprocess.run([sys.executable, str(ROOT / m.SCRIPT_PATH), option], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(json.loads(r.stdout)["verification_passed"])
        r = subprocess.run([sys.executable, str(ROOT / m.SCRIPT_PATH), "--run"], cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)

    def test_hosted_workflow_is_pinned_read_only_without_provider_paths(self):
        text = (ROOT / m.WORKFLOW_PATH).read_text()
        for token in ("contents: read", "cancel-in-progress: false", "--require-hashes", 'python-version: "3.12.14"', "python -O -m unittest"):
            self.assertIn(token, text)
        for token in ("secrets.", "workflow_dispatch", "--run", "--acquire", "--quote"):
            self.assertNotIn(token, text)

    def test_interval_scope_uses_integer_nanoseconds_and_not_actual_fills(self):
        args = fixture(); window = args["window"]
        plan = m.derive_exit_plan([window], [])
        g = plan["groups"][0]
        self.assertEqual(g["required_quote_start_ns"], BASE - 100_000_000)
        self.assertEqual(g["required_end_ns"], BASE + 960 * SECOND)
        self.assertEqual(g["members"][0]["first_possible_exit_decision_ns"], BASE + 100_000_001)
        self.assertEqual(g["members"][0]["last_covered_exit_decision_ns"], BASE + 960 * SECOND - 550_000_001)
        self.assertEqual(g["requests"][1]["start_ns"], int(pd.Timestamp("2025-05-30", tz="UTC").value))

    def test_unavailable_opportunity_is_retained_and_never_requests_exit_data(self):
        w = fixture()["window"]; w["entry_input_status"] = "unavailable"; w["entry_input_reason"] = "synthetic_missing"
        p = m.derive_exit_plan([w], [])
        self.assertEqual(p["new_requests"], [])
        self.assertEqual(p["groups"], [])
        self.assertEqual(p["opportunities"][0]["entry_input_reason"], "synthetic_missing")

    def test_reuse_requires_both_complete_requests_and_identical_ends(self):
        a = fixture(); pair = [a["tape"]["quote_request"], a["tape"]["status_request"]]
        self.assertEqual(m.derive_exit_plan([a["window"]], pair)["new_request_count"], 0)
        pair[1]["end_ns"] -= 1
        self.assertEqual(m.derive_exit_plan([a["window"]], pair)["new_request_count"], 2)
        self.assertEqual(m.derive_exit_plan([a["window"]], pair[:1])["new_request_count"], 2)

    def test_duplicate_opportunity_or_request_cannot_silently_collapse(self):
        a = fixture()
        with self.assertRaisesRegex(ValueError, "duplicate original opportunity"):
            m.derive_exit_plan([a["window"], a["window"]], [])
        with self.assertRaisesRegex(ValueError, "duplicate original request"):
            m.derive_exit_plan([a["window"]], [a["tape"]["quote_request"]] * 2)

    def test_resolver_uses_frozen_catalog_and_never_caller_context_pin(self):
        a = fixture()
        docs = {str(ROOT / m.INPUT_REQUIREMENTS): {"opportunity_windows": [a["window"]]},
            str(ROOT / m.projection.ACCOUNT_PLAN): {"paths": [{"path_id": a["slot"]["path_id"], "sessions": [a["slot"]]}]}}
        with patch.object(m, "validate_registration", return_value={}), patch.object(m, "frozen", side_effect=lambda p: copy.deepcopy(docs[str(p)])):
            kwargs = {"path_id": a["slot"]["path_id"], "opportunity_id": a["window"]["opportunity"]["opportunity_id"], "source_decision": a["source_decision"]}
            r = m.resolve_registered_context(ROOT, **kwargs)
            self.assertEqual(r["context_content_sha256"], a["expected_context_sha256"])
            self.assertTrue(r["original_context_authenticated"])
            self.assertFalse(r["pre_entry_account_state_authenticated"])
            kwargs["source_decision"] = copy.deepcopy(a["source_decision"]); kwargs["source_decision"]["plan"]["stop_price"] = 8
            with self.assertRaisesRegex(ValueError, "catalog commitment"): m.resolve_registered_context(ROOT, **kwargs)


class RunnerMechanicsTests(unittest.TestCase):
    def test_target_and_stop_automatically_process_fill_and_cancel_clocks(self):
        r = m.run_position_mechanics(**arguments())
        state = r["final_state"]
        self.assertEqual(state["remaining_quantity"], 0)
        self.assertEqual([f["quantity"] for f in state["fills"]], [5, 5])
        self.assertEqual([f["fill_price"] for f in state["fills"]], ["12", "9"])
        self.assertEqual([f["fill_time_ns"] for f in state["fills"]], [BASE + SECOND + 100_000_000, BASE + 2 * SECOND + 100_000_000])
        self.assertEqual(state["clock_ns"], BASE + 960 * SECOND - 1)
        self.assertFalse(r["historical_runtime_authorized"])

    def test_both_scenarios_and_small_odd_share_positions(self):
        for scenario in m.feedback.SCENARIOS:
            for q in (1, 2, 3, 7):
                with self.subTest(scenario=scenario, quantity=q):
                    r = m.run_position_mechanics(**arguments(quantity=q, scenario=scenario))
                    self.assertEqual(r["final_state"]["sold_quantity"], q)
                    self.assertEqual(r["final_state"]["target_filled_quantity"], q // 2)

    def test_partial_final_remainder_is_explicitly_open(self):
        state = m.run_position_mechanics(**arguments(target_fill=2, final_fill=3))["final_state"]
        self.assertEqual((state["sold_quantity"], state["remaining_quantity"]), (5, 5))
        self.assertFalse(state["breakeven_active"])
        self.assertEqual(state["status"], "open_unresolved_exit_remainder")
        self.assertFalse(state["pending_order"])

    def test_empty_streams_do_not_invent_liquidation(self):
        r = m.run_position_mechanics(**arguments(trades=[]))
        self.assertEqual(r["final_state"]["remaining_quantity"], 10)
        self.assertEqual(r["orders"], [])
        self.assertTrue(r["complete_streams_verified"])

    def test_no_later_print_is_needed_for_pending_fill_and_cancel_feedback(self):
        state = m.run_position_mechanics(**arguments(trades=[record(SECOND, 12)]))["final_state"]
        self.assertEqual(state["remaining_quantity"], 5)
        self.assertTrue(state["breakeven_active"])
        self.assertFalse(state["pending_order"])

    def test_completed_bar_precedes_same_time_print(self):
        a = arguments(bars=[minute_bar()], trades=[record(60 * SECOND, 11)])
        move_final_quotes(a, 60 * SECOND)
        r = m.run_position_mechanics(**a)
        self.assertEqual(r["final_state"]["fills"][0]["reason"], "first_red_candle")
        self.assertEqual(r["orders"][0]["decision_ts_ns"], BASE + 60 * SECOND)

    def test_bar_cannot_signal_before_its_close(self):
        a = arguments(bars=[minute_bar()], trades=[record(30 * SECOND, 11), record(60 * SECOND, 11, 1)])
        move_final_quotes(a, 60 * SECOND)
        self.assertEqual(m.run_position_mechanics(**a)["orders"][0]["decision_ts_ns"], BASE + 60 * SECOND)

    def test_equal_time_target_fill_cannot_retroactively_create_breakeven_signal(self):
        a = arguments(trades=[record(SECOND, 12), record(SECOND + 100_000_000, 9.5, 1), record(2 * SECOND, 11, 2)])
        r = m.run_position_mechanics(**a)
        self.assertEqual(len(r["orders"]), 1)
        self.assertIsNone(r["final_state"]["latched_full_exit"])

    def test_all_same_time_native_prints_precede_feedback(self):
        a = arguments(trades=[record(SECOND, 12), record(SECOND + 100_000_000, 9.5, 1), record(SECOND + 100_000_000, 9.4, 2)])
        self.assertIsNone(m.run_position_mechanics(**a)["final_state"]["latched_full_exit"])

    def test_competing_stop_latches_until_ack_and_next_eligible_print(self):
        a = arguments(trades=[record(SECOND, 12), record(SECOND + 50_000_000, 8, 1), record(2 * SECOND, 11, 2)])
        r = m.run_position_mechanics(**a)
        self.assertEqual(r["orders"][1]["decision_ts_ns"], BASE + 2 * SECOND)
        self.assertEqual(r["final_state"]["fills"][1]["reason"], "initial_stop")
        self.assertEqual(r["orders"][1]["quantity"], 5)

    def test_print_at_cancel_ack_cannot_clear_pending_before_that_print(self):
        a = arguments(trades=[record(SECOND, 12), record(SECOND + 50_000_000, 8, 1), record(SECOND + 450_000_000, 11, 2), record(2 * SECOND, 11, 3)])
        self.assertEqual(m.run_position_mechanics(**a)["orders"][1]["decision_ts_ns"], BASE + 2 * SECOND)

    def test_entry_time_print_is_excluded(self):
        a = arguments(trades=[record(100_000_000, 8)])
        self.assertEqual(m.run_position_mechanics(**a)["orders"], [])

    def test_source_unknown_conditions_remain_ineligible(self):
        a = arguments(trades=[record(SECOND, 12, conditions=["UNKNOWN"])])
        self.assertEqual(m.run_position_mechanics(**a)["orders"], [])

    def test_late_completed_bar_is_validated_without_extending_signal_window(self):
        a = arguments(bars=[minute_bar(minute=15)], trades=[])
        self.assertEqual(m.run_position_mechanics(**a)["orders"], [])

    def test_missing_exit_reference_preserves_entry_and_outstanding_intent(self):
        a = arguments(trades=[record(10 * SECOND, 12)])
        with self.assertRaises(m.RunnerInputFailure) as caught: m.run_position_mechanics(**a)
        self.assertEqual(caught.exception.stage, "executable_exit_evidence")
        self.assertEqual(caught.exception.partial_state["remaining_quantity"], 10)
        self.assertIsNotNone(caught.exception.partial_state["outstanding_intent"])

    def test_missing_exit_capture_tail_never_extends_window(self):
        a = arguments(trades=[record(960 * SECOND - 1, 12)])
        with self.assertRaises(m.RunnerInputFailure) as caught: m.run_position_mechanics(**a)
        self.assertEqual(caught.exception.partial_state["sold_quantity"], 0)
        self.assertEqual(caught.exception.partial_state["remaining_quantity"], 10)

    def test_incomplete_or_tampered_stream_cannot_return_success(self):
        a = arguments(); a["trades"] = a["trades"][:1]
        with self.assertRaises(m.RunnerInputFailure) as caught: m.run_position_mechanics(**a)
        self.assertEqual(caught.exception.stage, "management_stream")
        a = arguments(); a["expected_streams"]["sip_transactions"]["sha256"] = "0" * 64
        with self.assertRaises(m.RunnerInputFailure): m.run_position_mechanics(**a)

    def test_rehashed_source_reordering_and_skipped_ordinals_rejected(self):
        for mutate in (lambda a: a["trades"].reverse(), lambda a: a["trades"][1].update(composed_record_ordinal=7)):
            a = arguments(); mutate(a); repin(a)
            with self.assertRaises(m.RunnerInputFailure): m.run_position_mechanics(**a)

    def test_invalid_future_record_is_not_hidden_after_position_closes(self):
        a = arguments(); a["trades"].append(record(3 * SECOND, -1, 2)); repin(a)
        with self.assertRaises(m.RunnerInputFailure): m.run_position_mechanics(**a)

    def test_exact_group_tape_and_stream_pins_are_required(self):
        for key in ("expected_exit_group_sha256", "expected_exit_tape_sha256"):
            a = arguments(); a[key] = "0" * 64
            with self.assertRaises(m.RunnerInputFailure): m.run_position_mechanics(**a)
        a = arguments(); del a["expected_streams"]["raw_sip_1m_bars"]
        with self.assertRaises(m.RunnerInputFailure): m.run_position_mechanics(**a)

    def test_rehashed_request_substitution_cannot_bypass_registered_scope(self):
        a = arguments(); a["exit_tape"]["quote_request"]["start_ns"] -= 1; repin(a)
        with self.assertRaises(m.RunnerInputFailure): m.run_position_mechanics(**a)

    def test_exit_evidence_cannot_replace_original_entry_evidence(self):
        a = arguments(); a["entry_arguments"]["tape"]["quote_records"][1]["ask_px_nanos"] += 1
        with self.assertRaises(m.RunnerInputFailure) as caught: m.run_position_mechanics(**a)
        self.assertIsNone(caught.exception.partial_state)

    def test_input_and_output_are_detached_and_account_ledger_unchanged(self):
        a = arguments(); before = a["entry_arguments"]["pre_entry_ledger"].runtime_artifact()
        r = m.run_position_mechanics(**a)
        r["final_state"]["entry"]["quantity"] = 999
        self.assertEqual(before, a["entry_arguments"]["pre_entry_ledger"].runtime_artifact())
        self.assertEqual(m.run_position_mechanics(**a)["final_state"]["entry"]["quantity"], 10)

    def test_scheduler_does_not_read_private_future_outcome(self):
        source = inspect.getsource(m.run_position_mechanics)
        for token in ("._pending", "._policy", "outcome.fill", "._entry", "._remaining"):
            self.assertNotIn(token, source)

    def test_delayed_quote_fill_is_applied_at_its_receive_clock(self):
        for scenario, delayed in (("l1-conservative-v0.1", 200_000_000), ("l1-stress-v0.1", 300_000_000)):
            a = arguments(scenario=scenario, trades=[record(SECOND, 12), record(SECOND + delayed, 9.5, 1), record(2 * SECOND, 11, 2)])
            a["exit_tape"]["quote_records"][3]["ts_recv_ns"] = BASE + SECOND + delayed
            repin(a)
            r = m.run_position_mechanics(**a)
            self.assertEqual(r["final_state"]["fills"][0]["fill_time_ns"], BASE + SECOND + delayed)
            self.assertEqual(len(r["orders"]), 1)
            self.assertIsNone(r["final_state"]["latched_full_exit"])

    def test_unused_tape_extra_fields_are_not_accepted_as_source_evidence(self):
        a = arguments(trades=[]); a["exit_tape"]["extra_outcome"] = "not a source field"; repin(a)
        with self.assertRaises(m.RunnerInputFailure): m.run_position_mechanics(**a)

    def test_rehashed_incomplete_common_scope_fails_even_without_exit(self):
        a = arguments(trades=[])
        a["exit_group"]["required_end_ns"] -= 1
        a["exit_group"] = m.seal({k: v for k, v in a["exit_group"].items() if k != "content_sha256"})
        repin(a)
        with self.assertRaises(m.RunnerInputFailure): m.run_position_mechanics(**a)

    def test_source_io_failure_preserves_partial_state(self):
        a = arguments()
        def broken():
            yield record(SECOND, 12)
            raise OSError("synthetic interrupted read")
        a["trades"] = broken()
        with self.assertRaises(m.RunnerInputFailure) as caught: m.run_position_mechanics(**a)
        self.assertEqual(caught.exception.stage, "management_stream")
        self.assertIsNotNone(caught.exception.partial_state)

    def test_seeded_paths_agree_with_independent_integer_arithmetic(self):
        rng = random.Random(72109)
        for scenario in m.feedback.SCENARIOS:
            for _ in range(25):
                q = rng.randrange(1, 31); target = rng.randrange(q // 2 + 1); terminal = rng.randrange(q - target + 1)
                with self.subTest(scenario=scenario, q=q, target=target, terminal=terminal):
                    state = m.run_position_mechanics(**arguments(quantity=q, scenario=scenario, target_fill=target, final_fill=terminal))["final_state"]
                    self.assertEqual(state["remaining_quantity"], q - target - terminal)
                    self.assertEqual(state["sold_quantity"], target + terminal)
                    self.assertEqual(state["reserved_sell_quantity"], 0)
                    self.assertEqual(state["breakeven_active"], bool(q // 2 and target == q // 2))


if __name__ == "__main__":
    unittest.main()
