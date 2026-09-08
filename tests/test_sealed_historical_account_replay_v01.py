from copy import deepcopy
from decimal import localcontext
from pathlib import Path
import unittest
from unittest.mock import patch

from momentumbot.research import sealed_historical_account_replay_v01 as m
from tests.test_sealed_historical_account_continuity_v01 import case_programs, empty_program, replay as parent_replay
from tests.test_sealed_historical_account_scheduler_v01 import reseal
import verify_sealed_historical_account_replay_v01 as checker

ROOT = Path(__file__).resolve().parents[1]


def fixture(parent_program):
    """Private mechanics fixtures; never accepted by the public historical API."""
    p = deepcopy(parent_program)
    path = {"path_id": p["path_id"], "sessions": p["slots"]}
    dependencies = m.binding.carry_dependencies([path])
    program = m.seal({"contract_id": m.CONTRACT_ID, "artifact_type": "original_account_source_program",
        "input_scope": "authenticated_original_historical_sources", "path_id": p["path_id"],
        "source_bindings_content_sha256": m.BOUND_MANIFEST, "slots": p["slots"],
        "sessions": [{"session_id": s["session_id"], "opportunities": s["opportunity_inputs"]} for s in p["slots"]]})
    items, bindings = {}, {}
    for session, slot in zip(p["sessions"], p["slots"]):
        for item in session["opportunities"]:
            spec = item["position"]
            oid = spec["entry_input"]["window"]["opportunity"]["opportunity_id"]
            items[oid] = item
            bindings[oid] = {"opportunity_id": oid, "window": spec["entry_input"]["window"],
                "candidates": {slot["profile_id"]: item["candidate"]}, "management_streams": spec["expected_streams"]}
    return program, {"paths": [path], "opportunities": list(bindings.values()), "carry_dependencies": dependencies}, items


def run_fixture(p, *, stream=False):
    program, manifest, items = fixture(p)
    dependencies = {d["next_session_id"]: d for d in manifest["carry_dependencies"]}
    initial = m.accounts.account_state_input(program["slots"][0])["account_state"]
    opening, previous, sessions = initial, None, []
    def resolve(oid):
        item = deepcopy(items[oid])
        if stream:
            item["position"]["bars"] = iter(item["position"]["bars"])
            item["position"]["trades"] = iter(item["position"]["trades"])
        return item
    with localcontext() as context:
        context.prec = 60
        for slot, source in zip(program["slots"], program["sessions"]):
            pair = m._session(slot, source, opening, previous, resolve, dependencies.get(slot["session_id"]))
            sessions.append(pair)
            opening, previous = deepcopy(pair["close"]["account_state"]), pair["close"]["content_sha256"]
    result = m.seal({"contract_id": m.CONTRACT_ID, "artifact_type": "original_historical_account_path",
        "path_id": program["path_id"], "program_content_sha256": program["content_sha256"],
        "initial_account_state": initial, "seed_application_count": 1, "session_count": 30,
        "sessions": sessions, "last_close_content_sha256": previous,
        "path_complete": all(s["runtime"]["status"] == "flat_complete" for s in sessions), **m.RUNTIME_BOUNDARY})
    return program, result, manifest


def verify_fixture(p, r, b):
    with localcontext() as context:
        context.prec = 60
        return checker.verify_path(p, r, b)


class HistoricalReplayMechanicsTests(unittest.TestCase):
    def test_frozen_parent_state_parity_across_mechanics(self):
        for name, p in case_programs().items():
            if name == "omitted":
                continue
            with self.subTest(name=name):
                old = parent_replay(p)
                _, new, _ = run_fixture(p)
                close_pins = {a["close"]["content_sha256"]: b["close"]["content_sha256"]
                    for a, b in zip(old["sessions"], new["sessions"])}
                for before, after in zip(old["sessions"], new["sessions"]):
                    expected = deepcopy(before["close"]["account_state"])
                    # The historical wrapper has its own close identity. Every
                    # retained state field must match after translating that pin.
                    for gap in expected["unresolved_inputs"]:
                        if gap.get("kind") == "preceding_state_blocks_execution":
                            gap["previous_close_content_sha256"] = close_pins[gap["previous_close_content_sha256"]]
                    self.assertEqual(expected, after["close"]["account_state"])
                    for key in ("events", "opportunity_dispositions", "reconciliation_snapshot", "unconfirmed_entry_order", "failure"):
                        self.assertEqual(before["runtime"][key], after["runtime"][key])

    def test_independent_checker_accepts_every_frozen_mechanics_case(self):
        for name, p in case_programs().items():
            if name == "omitted":
                continue
            with self.subTest(name=name):
                program, result, binding = run_fixture(p)
                counts = verify_fixture(program, result, binding)
                self.assertEqual(counts["sessions"], 30)

    def test_stream_iterators_produce_identical_account_results(self):
        p = case_programs()["l1-conservative-v0.1-reentry"]
        self.assertEqual(run_fixture(p)[1], run_fixture(p, stream=True)[1])

    def test_all_twelve_paths_use_one_seed_and_thirty_slots(self):
        for account in ("main_account", "small_account"):
            for horizon in (1, 5, 10):
                for scenario in m.continuity.feedback.SCENARIOS:
                    p, r, b = run_fixture(empty_program(account=account, horizon=horizon, scenario=scenario))
                    self.assertEqual(verify_fixture(p, r, b)["sessions"], 30)
                    self.assertEqual(r["seed_application_count"], 1)
                    self.assertEqual(r["sessions"][-1]["close"]["account_state"]["equity_usd"], "30000.00" if account == "main_account" else "2000.00")

    def test_open_position_blocks_all_later_slots_with_exact_basis_and_cash(self):
        p, r, b = run_fixture(case_programs()["partial_carry"])
        first = r["sessions"][0]["close"]["account_state"]
        self.assertTrue(first["positions"])
        for pair in r["sessions"][1:]:
            self.assertTrue(pair["runtime"]["blocked_before_execution"])
            self.assertFalse(pair["runtime"]["historical_session_scheduler_executed"])
            for key in ("positions", "buying_power_usd", "equity_usd", "pending_orders", "campaigns"):
                self.assertEqual(pair["close"]["account_state"][key], first[key])
            self.assertEqual(pair["runtime"]["carry_dependency"]["status"], "blocked_preserved_prior_state")
        self.assertFalse(r["path_complete"])
        verify_fixture(p, r, b)

    def test_unavailable_is_retained_and_never_resolved(self):
        p = case_programs()["unavailable"]
        program, b, _ = fixture(p)
        source, slot = program["sessions"][0], program["slots"][0]
        opening = m.accounts.account_state_input(slot)["account_state"]
        def forbidden(_):
            self.fail("unavailable original input was resolved")
        pair = m._session(slot, source, opening, None, forbidden, None)
        self.assertEqual(pair["runtime"]["opportunity_dispositions"][0]["disposition"], "unavailable_input")
        self.assertEqual(pair["runtime"]["status"], "flat_complete_with_unavailable_inputs")
        self.assertFalse(pair["runtime"]["financial_metrics_eligible"])

    def test_public_api_rejects_caller_source_objects(self):
        with patch.object(m, "verify_bundle", return_value={"freeze_content_sha256": "pin"}):
            with self.assertRaisesRegex(ValueError, "original source reader"):
                m.replay_panel(ROOT, object(), expected_registration_sha256="pin")

    def test_external_registration_pin_is_required_before_source_access(self):
        with patch.object(m, "verify_bundle", return_value={"freeze_content_sha256": "pin"}):
            with self.assertRaisesRegex(ValueError, "registration pin"):
                m.replay_panel(ROOT, object(), expected_registration_sha256="wrong")

    def test_public_api_rejects_rehashed_synthetic_binding_manifest(self):
        obj = object.__new__(m.binding.OriginalSources)
        obj._temporary, obj._manifest = object(), m.seal({"paths": [], "opportunities": []})
        with patch.object(m, "verify_bundle", return_value={"freeze_content_sha256": "pin"}):
            with self.assertRaisesRegex(ValueError, "manifest differs"):
                m.replay_panel(ROOT, obj, expected_registration_sha256="pin")

    def test_parent_historical_guards_are_unchanged(self):
        p = empty_program()
        p["input_scope"] = "authenticated_original_historical_sources"
        with self.assertRaisesRegex(ValueError, "synthetic"):
            parent_replay(reseal(p))

    def test_omitted_original_source_fails_and_preserves_last_state(self):
        p, r, _ = run_fixture(case_programs()["omitted"])
        runtime = r["sessions"][0]["runtime"]
        self.assertEqual(runtime["status"], "input_failure")
        self.assertFalse(runtime["complete_streams_verified"])
        self.assertTrue(r["sessions"][1]["runtime"]["blocked_before_execution"])

    def test_pending_entry_failure_keeps_unreconciled_feedback(self):
        _, r, _ = run_fixture(case_programs()["pending_input_failure"])
        state = r["sessions"][0]["close"]["account_state"]
        self.assertTrue(state["pending_orders"])
        self.assertEqual(r["sessions"][-1]["close"]["account_state"]["pending_orders"], state["pending_orders"])

    def test_independent_checker_rejects_rehashed_cash_reseed(self):
        p, r, b = run_fixture(case_programs()["reentry-cash-carry"])
        r["sessions"][1]["close"]["account_state"]["equity_usd"] = "30000.00"
        r["sessions"][1]["close"] = reseal(r["sessions"][1]["close"])
        with self.assertRaisesRegex(ValueError, "close"):
            verify_fixture(p, reseal(r), b)

    def test_independent_checker_rejects_stream_substitution(self):
        p, r, b = run_fixture(case_programs()["l1-conservative-v0.1-reentry"])
        r["sessions"][0]["runtime"]["processed_streams"][0]["sha256"] = "a" * 64
        r["sessions"][0]["runtime"] = reseal(r["sessions"][0]["runtime"])
        r["sessions"][0]["close"]["source_runtime_content_sha256"] = r["sessions"][0]["runtime"]["content_sha256"]
        r["sessions"][0]["close"] = reseal(r["sessions"][0]["close"])
        with self.assertRaisesRegex(ValueError, "stream"):
            verify_fixture(p, reseal(r), b)

    def test_independent_checker_rejects_financial_promotion(self):
        p, r, b = run_fixture(empty_program())
        r["financial_metrics_eligible"] = True
        with self.assertRaisesRegex(ValueError, "boundary"):
            verify_fixture(p, reseal(r), b)

    def test_original_registration_preserves_panel_and_closed_metrics(self):
        programs = m.source_programs(ROOT)
        self.assertEqual(len(programs), 12)
        self.assertEqual(sum(len(p["slots"]) for p in programs), 360)
        refs = [r for p in programs for s in p["slots"] for r in s["opportunity_inputs"]]
        self.assertEqual((len(refs), sum(r["input_status"] == "unavailable" for r in refs)), (744, 162))
        self.assertFalse(m.RUNTIME_BOUNDARY["financial_metrics_eligible"])

    def test_resolved_foreign_opportunity_fails_before_order_submission(self):
        program, _, items = fixture(case_programs()["l1-conservative-v0.1-reentry"])
        slot, source = program["slots"][0], program["sessions"][0]
        first, second = list(items.values())[:2]
        pair = m._session(slot, source, m.accounts.account_state_input(slot)["account_state"], None,
            lambda oid: deepcopy(second), None)
        self.assertEqual(pair["runtime"]["status"], "input_failure")
        self.assertEqual(pair["runtime"]["events"], [])

    def test_omitted_unavailable_ref_is_rejected_before_execution(self):
        program, _, _ = fixture(case_programs()["unavailable"])
        source = deepcopy(program["sessions"][0])
        source["opportunities"] = []
        slot = program["slots"][0]
        pair = m._session(slot, source, m.accounts.account_state_input(slot)["account_state"], None,
            lambda oid: self.fail("source should not be opened"), None)
        self.assertEqual(pair["runtime"]["status"], "input_failure")
        self.assertEqual(pair["runtime"]["opportunity_dispositions"][0]["disposition"], "unavailable_input")

    def test_independent_checker_rejects_lost_open_window(self):
        p, r, b = run_fixture(case_programs()["partial_carry"])
        runtime = r["sessions"][0]["runtime"]
        runtime["active_original_window"] = None
        r["sessions"][0]["runtime"] = reseal(runtime)
        close = r["sessions"][0]["close"]
        close["source_runtime_content_sha256"] = r["sessions"][0]["runtime"]["content_sha256"]
        r["sessions"][0]["close"] = reseal(close)
        with self.assertRaisesRegex(ValueError, "window lost"):
            verify_fixture(p, reseal(r), b)

    def test_registration_is_reproducible_and_parent_pins_are_real(self):
        verified = m.verify_bundle(ROOT, ROOT / m.OUTPUT_PATH)
        self.assertTrue(verified["verification_passed"])
        self.assertEqual(len(m.PARENT_PINS), 13)


if __name__ == "__main__":
    unittest.main()
