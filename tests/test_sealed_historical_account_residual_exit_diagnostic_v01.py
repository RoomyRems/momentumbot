"""Regression evidence for the preserved checker defect, without repairing it."""
from copy import deepcopy
import unittest

import diagnose_sealed_historical_account_residual_exit_v01 as diagnostic
import verify_sealed_historical_account_residual_exit_v01 as frozen
from momentumbot.research import execution_realism as execution
from tests.test_sealed_historical_account_residual_exit_v01 import residual_program, run_fixture, BASE, SECOND
from tests.test_sealed_historical_account_scheduler_v01 import repin

MS = 1_000_000
DECISION = 10 * SECOND


def lifecycle_input(scenario="l1-conservative-v0.1", offsets=(-1,)):
    delay, _, lifetime, cancel_delay = diagnostic.POLICIES[scenario]
    order = {"decision_ts_ns": DECISION, "arrival_ts_ns": DECISION + delay * MS,
        "cancel_requested_ts_ns": DECISION + (delay + lifetime) * MS,
        "cancel_ack_ts_ns": DECISION + (delay + lifetime + cancel_delay) * MS}
    request = {"start_ns": DECISION - SECOND, "end_ns": DECISION + SECOND}
    quotes = [{"symbol": "SYNTHETIC", "ts_recv_ns": DECISION + offset,
        "sequence": i, "source_request_sha256": "a" * 64, "source_record_index": i,
        "bid_px_nanos": 9_000_000_000, "ask_px_nanos": 9_010_000_000,
        "bid_size": 20, "ask_size": 20} for i, offset in enumerate(sorted(offsets))]
    tape = {"quote_request": request, "status_request": deepcopy(request), "quote_records": quotes,
        "status_records": [{"ts_recv_ns": DECISION - SECOND, "is_trading": "Y"}]}
    return tape, {"end_ns": DECISION + SECOND}, order, scenario


class QuoteLifecycleDiagnosticTests(unittest.TestCase):
    def test_diagnostic_constants_equal_both_frozen_execution_policies(self):
        for policy in (execution.BASELINE_CONSERVATIVE_POLICY, execution.STRESS_POLICY):
            self.assertEqual(diagnostic.POLICIES[policy.policy_id], (policy.decision_to_arrival_ms,
                policy.max_quote_age_ms, policy.cancel_after_arrival_ms, policy.cancel_ack_ms))

    def test_quote_fresh_at_decision_can_be_stale_at_arrival(self):
        for scenario in diagnostic.POLICIES:
            proof = diagnostic.quote_lifecycle(*lifecycle_input(scenario))
            self.assertIsNotNone(proof["decision_reference"])
            self.assertTrue(proof["no_fresh_quote_status_supported"])
            self.assertGreater(proof["last_quote_age_at_arrival_ns"], proof["max_quote_age_ns"])

    def test_arrival_freshness_includes_exact_age_boundary_only(self):
        for scenario, (delay, max_age, _, _) in diagnostic.POLICIES.items():
            boundary = (delay - max_age) * MS
            with self.subTest(scenario=scenario):
                exact = diagnostic.quote_lifecycle(*lifecycle_input(scenario, (boundary,)))
                stale = diagnostic.quote_lifecycle(*lifecycle_input(scenario, (boundary - 1,)))
                self.assertEqual(exact["carried_fresh_quote_count"], 1)
                self.assertTrue(stale["no_fresh_quote_status_supported"])

    def test_arrival_is_inclusive_and_cancellation_ack_is_exclusive(self):
        for scenario, (delay, _, lifetime, cancel_delay) in diagnostic.POLICIES.items():
            ack = (delay + lifetime + cancel_delay) * MS
            arrival = diagnostic.quote_lifecycle(*lifecycle_input(scenario, (-1, delay * MS)))
            before = diagnostic.quote_lifecycle(*lifecycle_input(scenario, (-1, ack - 1)))
            equal = diagnostic.quote_lifecycle(*lifecycle_input(scenario, (-1, ack)))
            self.assertEqual(arrival["active_candidate_count"], 1)
            self.assertEqual(before["later_active_quote_count"], 1)
            self.assertTrue(equal["no_fresh_quote_status_supported"])

    def test_halted_fresh_candidate_is_distinct_from_no_fresh_quote(self):
        tape, window, order, scenario = lifecycle_input(offsets=(-1, 90 * MS))
        tape["status_records"].append({"ts_recv_ns": DECISION + 80 * MS, "is_trading": "N"})
        proof = diagnostic.quote_lifecycle(tape, window, order, scenario)
        self.assertFalse(proof["no_fresh_quote_status_supported"])
        self.assertEqual((proof["active_candidate_count"], proof["active_nonhalted_candidate_count"]), (1, 0))

    def test_unknown_status_is_not_reclassified_as_a_quote_gap(self):
        tape, window, order, scenario = lifecycle_input()
        tape["status_records"].append({"ts_recv_ns": DECISION + 20 * MS, "is_trading": "~"})
        with self.assertRaisesRegex(ValueError, "status coverage"):
            diagnostic.quote_lifecycle(tape, window, order, scenario)

    def test_equal_time_status_and_unusable_quotes_cannot_fill_a_gap(self):
        for kind in ("equal_status", "crossed", "zero_size"):
            tape, window, order, scenario = lifecycle_input(offsets=(-1, 90 * MS))
            if kind == "equal_status":
                tape["status_records"].append({"ts_recv_ns": DECISION + 90 * MS, "is_trading": "Y"})
            elif kind == "crossed":
                tape["quote_records"][-1]["bid_px_nanos"] = 10_000_000_000
            else:
                tape["quote_records"][-1]["bid_size"] = 0
            self.assertTrue(diagnostic.quote_lifecycle(tape, window, order, scenario)["no_fresh_quote_status_supported"])

    def test_changed_clock_and_missing_capture_coverage_fail_closed(self):
        for kind in ("clock", "source", "window"):
            tape, window, order, scenario = lifecycle_input()
            if kind == "clock":
                order["cancel_ack_ts_ns"] += 1
            elif kind == "source":
                tape["quote_request"]["end_ns"] = DECISION + frozen.TAIL
            else:
                window["end_ns"] = DECISION + frozen.TAIL
            with self.assertRaises(ValueError):
                diagnostic.quote_lifecycle(tape, window, order, scenario)


class FrozenCheckerDefectRegressionTests(unittest.TestCase):
    def test_native_quote_gap_produces_valid_feedback_rejected_by_frozen_checker(self):
        for scenario in diagnostic.POLICIES:
            with self.subTest(scenario=scenario):
                p = residual_program(first_fill=0, replacement_fill=10, scenario=scenario)
                value = p["sessions"][0]["opportunities"][0]["position"]
                value["exit_tape"]["quote_records"] = [q for q in value["exit_tape"]["quote_records"]
                    if not BASE + 2 * SECOND <= q["ts_recv_ns"] <= BASE + 2 * SECOND + frozen.TAIL]
                repin(value)
                program, result, manifest, resolve = run_fixture(p)
                runtime = result["sessions"][0]["runtime"]
                frozen.verify_path(program, result, manifest)
                self.assertEqual(runtime["status"], "flat_complete")
                with self.assertRaisesRegex(ValueError, diagnostic.EXPECTED_ERROR):
                    frozen.verify_residual(runtime, resolve)
                rows = list(diagnostic.cancellations({"paths": [result]}))
                self.assertEqual(len(rows), 1)
                row = rows[0]
                self.assertEqual(row["acknowledgement"]["execution_status"], "unavailable_no_fresh_quote")
                self.assertEqual(row["confirmed_order_filled_quantity"], 0)
                data = resolve(row["entry"]["opportunity_id"])
                proof = diagnostic.quote_lifecycle(data["tape"], data["window"], row["order"], scenario)
                self.assertTrue(proof["no_fresh_quote_status_supported"])

    def test_ordinary_unfilled_cancellation_does_not_imply_a_quote_gap(self):
        _, result, _, resolve = run_fixture(residual_program(first_fill=0, replacement_fill=10))
        runtime = result["sessions"][0]["runtime"]
        frozen.verify_residual(runtime, resolve)
        row = list(diagnostic.cancellations({"paths": [result]}))[0]
        self.assertEqual(row["acknowledgement"]["execution_status"], "cancelled_unfilled")
        data = resolve(row["entry"]["opportunity_id"])
        proof = diagnostic.quote_lifecycle(data["tape"], data["window"], row["order"], row["entry"]["scenario_id"])
        self.assertFalse(proof["no_fresh_quote_status_supported"])


if __name__ == "__main__":
    unittest.main()
