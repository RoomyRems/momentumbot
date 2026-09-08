from copy import deepcopy
from decimal import Decimal, Inexact, localcontext
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from momentumbot.research import sealed_historical_account_risk_projection_v01 as m
from momentumbot.research.campaign_portfolio import EntryRole
from tests.test_campaign_portfolio import _constraints, _plan, _entry, _exit, SESSION
from tests.test_sealed_historical_account_continuity_v01 import case_programs, empty_program
from tests.test_sealed_historical_account_scheduler_v01 import spec, attach, repin, reseal
from tests.test_sealed_historical_account_replay_v01 import fixture, run_fixture as old_fixture, verify_fixture
import verify_sealed_historical_account_risk_projection_v01 as checker

ROOT = Path(__file__).resolve().parents[1]


def ledger(fill=3.55, stop=3.35, quantity=2):
    value = m.CampaignPortfolioLedger(SESSION, _constraints())
    value.record_plan_emission(_plan())
    accepted = value.apply_entry_fill(_entry(quantity=quantity, reference_price=fill, fill_price=fill, stop_price=stop))
    if not accepted.accepted:
        raise ValueError(accepted.reasons)
    return value


def nonbinary_program(*, scenario="l1-stress-v0.1", account="main_account"):
    value = spec(quantity=2, bars=[], trades=[], scenario=scenario, account=account)
    value["entry_input"]["source_decision"]["plan"]["stop_price"] = 3.35
    for row in value["entry_input"]["tape"]["quote_records"][:2]:
        row["bid_px_nanos"] -= 6_450_000_000
        row["ask_px_nanos"] -= 6_450_000_000
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
    return program, result, manifest


class DecimalRiskTests(unittest.TestCase):
    def test_nonbinary_cent_and_subcent_vectors(self):
        for fill, stop, qty, expected in ((3.55, 3.35, 2, "0.40"), (10.03, 9.99, 7, "0.28"),
                (1.03, 1.01, 13, "0.26"), (3.60, 3.35, 36, "9.00"),
                (10.000000003, 10.000000001, 5, "0.000000010")):
            with self.subTest(fill=fill, stop=stop):
                value = ledger(fill, stop, qty)
                report = m.project_ledger(value)
                self.assertEqual(Decimal(str(report["account"]["total_open_risk"])), Decimal(expected))
                self.assertEqual(Decimal(str(report["campaigns"][0]["open_risk"])), Decimal(expected))

    def test_internal_ledger_and_frozen_entry_evidence_are_untouched(self):
        value = ledger()
        before, raw = deepcopy(value.__dict__), deepcopy(value.runtime_artifact())
        self.assertEqual(value.total_open_risk, 0.39999999999999947)
        self.assertEqual(m.project_ledger(value)["account"]["total_open_risk"], 0.4)
        self.assertEqual(value.__dict__, before)
        self.assertEqual(value.runtime_artifact(), raw)

    def test_projection_is_idempotent_and_does_not_alias_events(self):
        value = ledger()
        first = m.project_ledger(value)
        self.assertEqual(first, m.project_ledger(value))
        first["events"][0]["symbol"] = "CHANGED"
        self.assertNotEqual(first, m.project_ledger(value))

    def test_partial_exit_uses_confirmed_remaining_shares(self):
        value = ledger(quantity=7)
        self.assertTrue(value.apply_exit_fill(_exit(quantity=3, fill_price=3.75)).accepted)
        self.assertEqual(m.project_ledger(value)["account"]["total_open_risk"], 0.8)

    def test_confirmed_breakeven_and_flat_risk_are_exact_zero(self):
        value = ledger()
        for lot in value.campaigns["activation-1"].lots:
            lot.stop_price = lot.fill_price
        self.assertEqual(m.project_ledger(value)["account"]["total_open_risk"], 0)
        value.apply_exit_fill(_exit(quantity=2, fill_price=3.75))
        self.assertEqual(m.project_ledger(value)["account"]["total_open_risk"], 0)

    def test_multi_lot_risk_is_summed_before_numeric_projection(self):
        value = ledger()
        value.record_plan_emission(_plan(plan_id="plan-2", at="13:00:02"))
        accepted = value.apply_entry_fill(_entry(fill_id="entry-2", plan_id="plan-2", at="13:00:03",
            quantity=3, reference_price=3.65, fill_price=3.65, stop_price=3.35, role=EntryRole.ADD))
        self.assertTrue(accepted.accepted)
        self.assertEqual(m.project_ledger(value)["account"]["total_open_risk"], 1.3)

    def test_parent_equal_risk_representation_is_byte_identical(self):
        for value in (ledger(3.6, 3.35, 36), m.CampaignPortfolioLedger(SESSION, _constraints())):
            self.assertEqual(m.fees.encoded(m.project_ledger(value)), m.fees.encoded(value.runtime_artifact()))

    def test_no_epsilon_quantization_or_rounding_is_allowed(self):
        self.assertEqual(m.exact_lot_risk("1.000000000000000001", "1", 1), Decimal("0.000000000000000001"))
        with self.assertRaisesRegex(ValueError, "decimal loss"):
            m._number(Decimal("0.123456789012345678901"), 0.0)

    def test_precision_does_not_depend_on_callers_decimal_context(self):
        with localcontext() as context:
            context.prec = 2
            self.assertEqual(m.exact_lot_risk("10.03", "9.99", 17), Decimal(".68"))
            self.assertEqual(m.project_ledger(ledger())["account"]["total_open_risk"], 0.4)

    def test_excess_precision_fails_instead_of_rounding(self):
        with self.assertRaises(Inexact):
            m.exact_lot_risk("2", "0." + "1" * 70, 1)

    def test_invalid_share_and_stop_inputs_are_rejected(self):
        for qty in (-1, 0.5, True, "2"):
            with self.subTest(qty=qty), self.assertRaises(ValueError):
                m.exact_lot_risk(3.55, 3.35, qty)
        for fill, stop in ((float("nan"), 1), (2, float("inf")), (2, 0), (2, 3)):
            with self.subTest(fill=fill, stop=stop), self.assertRaises(ValueError):
                m.exact_lot_risk(fill, stop, 2)


class RiskReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.program = nonbinary_program()
        cls.source, cls.result, cls.manifest = run_fixture(cls.program)
        cls.old = old_fixture(cls.program)[1]

    def test_old_checker_rejects_parent_and_accepts_decimal_child(self):
        with self.assertRaisesRegex(ValueError, "confirmed stop risk differs"):
            verify_fixture(self.source, self.old, self.manifest)
        totals = verify_fixture(self.source, self.result, self.manifest)
        self.assertEqual(totals["confirmed_entries"], 1)
        self.assertEqual(totals["blocked_sessions"], 29)
        snapshot = self.result["sessions"][0]["runtime"]["reconciliation_snapshot"]
        self.assertEqual(snapshot["ledger"]["account"]["total_open_risk"], 0.4)
        self.assertEqual(checker.verify_decimal_snapshot(snapshot), 1)

    def test_all_nonrisk_state_and_commitments_match_parent(self):
        self.assertGreater(checker.verify_delta(self.old, self.result), 0)
        for old, new in zip(self.old["sessions"], self.result["sessions"]):
            for key in ("events", "failure", "opportunity_dispositions", "unconfirmed_entry_order", "active_original_window"):
                self.assertEqual(old["runtime"][key], new["runtime"][key])
        before = self.old["sessions"][0]["runtime"]["reconciliation_snapshot"]
        after = self.result["sessions"][0]["runtime"]["reconciliation_snapshot"]
        for key in ("journal", "management", "fee_book", "exact_account", "consumed_sell_liquidity"):
            self.assertEqual(before[key], after[key])

    def test_parent_cases_reentry_partial_fills_locks_and_failures_still_match(self):
        for name, p in case_programs().items():
            with self.subTest(name=name):
                program, result, manifest = run_fixture(p)
                checker.verify_delta(old_fixture(p)[1], result)
                if name != "omitted":
                    verify_fixture(program, result, manifest)
                for pair in result["sessions"]:
                    snapshot = pair["runtime"]["reconciliation_snapshot"]
                    if snapshot is not None:
                        checker.verify_decimal_snapshot(snapshot)

    def test_main_small_and_both_scenarios_preserve_entry_sizing(self):
        for account in ("main_account", "small_account"):
            for scenario in m.continuity.feedback.SCENARIOS:
                with self.subTest(account=account, scenario=scenario):
                    p = nonbinary_program(account=account, scenario=scenario)
                    program, result, manifest = run_fixture(p)
                    checker.verify_delta(old_fixture(p)[1], result)
                    verify_fixture(program, result, manifest)

    def test_all_twelve_empty_paths_preserve_exact_parent_bytes(self):
        for account in ("main_account", "small_account"):
            for horizon in (1, 5, 10):
                for scenario in m.continuity.feedback.SCENARIOS:
                    p = empty_program(account=account, horizon=horizon, scenario=scenario)
                    self.assertEqual(old_fixture(p)[1], run_fixture(p)[1])

    def test_internal_ledger_copy_stays_frozen_before_and_after_entry(self):
        program, manifest, items = fixture(self.program)
        slot, source = program["slots"][0], program["sessions"][0]
        machine = m._Session(slot, source, m.accounts.account_state_input(slot)["account_state"], lambda oid: deepcopy(items[oid])).run()
        self.assertEqual(type(machine.account.ledger_copy()), m.fees._NetLedger)
        self.assertEqual(machine.account.ledger_copy().total_open_risk, 0.39999999999999947)
        self.assertEqual(machine.account.snapshot()["ledger"]["account"]["total_open_risk"], 0.4)

    def test_parity_rejects_rehashed_arbitrary_nonrisk_changes(self):
        for key, value in (("buying_power_usd", "999.00"), ("positions", []), ("pending_orders", [{}])):
            bad = deepcopy(self.result)
            bad["sessions"][0]["close"]["account_state"][key] = value
            bad["sessions"][0]["close"] = reseal(bad["sessions"][0]["close"])
            with self.subTest(key=key), self.assertRaises(ValueError):
                checker.verify_delta(self.old, reseal(bad))

    def test_parity_does_not_ignore_arbitrary_hash_strings(self):
        old = m.seal({"entry": {"post_ledger_content_sha256": "a" * 64}})
        bad = m.seal({"entry": {"post_ledger_content_sha256": "b" * 64}})
        with self.assertRaisesRegex(ValueError, "nonrisk value changed"):
            checker.verify_delta(old, bad)

    def test_independent_rational_checker_rejects_total_and_campaign_risk(self):
        snapshot = self.result["sessions"][0]["runtime"]["reconciliation_snapshot"]
        for campaign in (False, True):
            bad = deepcopy(snapshot)
            if campaign:
                bad["ledger"]["campaigns"][0]["open_risk"] = 0.0
            else:
                bad["ledger"]["account"]["total_open_risk"] = 0.39999999999999947
            with self.subTest(campaign=campaign), self.assertRaisesRegex(ValueError, "risk differs"):
                checker.verify_decimal_snapshot(reseal(bad))

    def test_registration_and_source_objects_fail_before_historical_access(self):
        with patch.object(m, "verify_bundle", return_value={"freeze_content_sha256": "pin"}):
            with self.assertRaisesRegex(ValueError, "registration pin"):
                m.replay_panel(ROOT, object(), expected_registration_sha256="wrong")
            with self.assertRaisesRegex(ValueError, "original source reader"):
                m.replay_panel(ROOT, object(), expected_registration_sha256="pin")

    def test_write_once_output_and_parent_replay_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "risk"
            m.write_files(ROOT, output, {"synthetic.json": b"{}\n"})
            with self.assertRaises(FileExistsError):
                m.write_files(ROOT, output, {"synthetic.json": b"changed\n"})
            self.assertEqual((output / "synthetic.json").read_bytes(), b"{}\n")
        self.assertTrue(m.parent.verify_bundle(ROOT, ROOT / m.parent.OUTPUT_PATH)["verification_passed"])

    def test_registration_is_reproducible_with_all_parent_pins(self):
        self.assertTrue(m.verify_bundle(ROOT, ROOT / m.OUTPUT_PATH)["verification_passed"])
        self.assertEqual(len(m.PARENT_PINS), 11)
        self.assertFalse(m.RUNTIME_BOUNDARY["financial_metrics_eligible"])


if __name__ == "__main__":
    unittest.main()
