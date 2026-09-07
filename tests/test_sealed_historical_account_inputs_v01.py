from __future__ import annotations

import copy
from decimal import Decimal
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from momentumbot.research import sealed_historical_account_inputs_v01 as a

ROOT = Path(__file__).resolve().parents[1]


def reseal(value):
    return a.seal({k: v for k, v in value.items() if k != "content_sha256"})


def close_for(slot, state):
    # Synthetic close evidence only: no entry, exit or historical replay occurs.
    return a.seal({"session_id": slot["session_id"], "path_id": slot["path_id"],
        "trading_date": slot["trading_date"], "source_runtime_content_sha256": "a" * 64,
        "account_state": copy.deepcopy(state)})


class HistoricalAccountInputsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.opportunities, cls.manifest, cls.rows = a.load_parent(ROOT)
        cls.plan = a.session_plan(cls.opportunities, cls.rows)
        cls.slots = cls.plan["paths"][0]["sessions"]

    def initial(self):
        return a.account_state_input(self.slots[0])["account_state"]

    def carry(self, closed, slot=None, expected=None):
        return a.account_state_input(slot or self.slots[1], previous_close=closed,
            expected_close_content_sha256=expected or closed["content_sha256"])

    def test_registration_binds_approved_values_and_unchanged_parent(self):
        result = a.validate_registration(ROOT)
        self.assertTrue(result["verification_passed"])
        self.assertEqual(a.contract()["user_approved_seed_equity_and_buying_power_usd"],
                         {"main_account": "30000.00", "small_account": "2000.00"})
        self.assertFalse(a.contract()["account_reset_between_dates"])
        self.assertFalse(a.contract()["historical_broker_snapshot_claim"])

    def test_first_session_limits_reuse_frozen_policy_for_both_accounts(self):
        main, small = a.seeds()["seeds"]
        for seed, equity, risk, notional, daily_loss in (
            (main, "30000.00", 75.0, 15000.0, 300.0),
            (small, "2000.00", 5.0, 1000.0, 20.0)):
            with self.subTest(seed=seed["account_key"]):
                self.assertEqual(seed["equity_usd"], equity)
                self.assertEqual(seed["buying_power_usd"], equity)
                limits = seed["first_session_frozen_constraints"]
                self.assertEqual(limits["max_total_open_risk"], risk)
                self.assertEqual(limits["max_total_open_notional"], notional)
                self.assertEqual(limits["max_daily_loss_dollars"], daily_loss)
                self.assertEqual(limits["max_entries_per_campaign"], 2)
                self.assertEqual(limits["max_open_positions"], 1)
                self.assertEqual(limits["giveback_fraction"], 0.5)

    def test_12_paths_360_sessions_and_exactly_12_initial_seeds(self):
        paths = self.plan["paths"]
        self.assertEqual(len(paths), 12)
        self.assertEqual(len({p["path_id"] for p in paths}), 12)
        slots = [s for p in paths for s in p["sessions"]]
        self.assertEqual(len(slots), 360)
        self.assertEqual(sum(s["seed_applied"] for s in slots), 12)
        self.assertEqual(len({s["session_id"] for s in slots}), 360)
        for path in paths:
            self.assertEqual([s["trading_date"] for s in path["sessions"]], list(a.DATES))
            for previous, current in zip(path["sessions"], path["sessions"][1:]):
                self.assertEqual(current["previous_session_id"], previous["session_id"])

    def test_all_profiles_unavailable_opportunities_and_empty_dates_preserved(self):
        slots = [s for p in self.plan["paths"] for s in p["sessions"]]
        refs = [r for s in slots for r in s["opportunity_inputs"]]
        self.assertEqual(len(refs), 6 * (99 + 25))
        self.assertEqual(sum(r["input_status"] == "unavailable" for r in refs), 6 * (21 + 6))
        self.assertEqual(sum(s["source_date_has_no_micro_decisions"] for s in slots), 60)
        self.assertEqual({r["opportunity_id"] for r in refs if r["input_status"] == "unavailable"},
            {r["opportunity"]["opportunity_id"] for r in self.rows if r["input_status"] == "unavailable"})

    def test_30_session_synthetic_handoff_carries_profit_loss_fees_and_positions(self):
        for path in self.plan["paths"]:
            state = a.account_state_input(path["sessions"][0])["account_state"]
            seed_equity = Decimal(state["equity_usd"])
            for i, (old, new) in enumerate(zip(path["sessions"], path["sessions"][1:]), 1):
                delta = Decimal(i if i % 2 else -i)
                state["equity_usd"] = format(seed_equity + delta, ".2f")
                state["buying_power_usd"] = format(seed_equity + delta - 50, ".2f")
                state["cumulative_realized_pnl_usd"] = format(delta, ".2f")
                state["cumulative_fees_usd"] = format(Decimal(i) / 100, ".2f")
                state["positions"] = [{"symbol": "SYNTHETIC", "quantity": 5, "entry_cost_usd": "50.00", "exit_status": "unresolved"}]
                state["campaigns"] = [{"activation_id": "synthetic", "entry_count": 1}]
                closed = close_for(old, state)
                result = self.carry(closed, new)
                self.assertEqual(result["account_state"], state)
                self.assertFalse(result["seed_applied"])
                self.assertTrue(result["next_session_valuation_and_daily_risk_validation_required"])
                self.assertFalse(result["source_execution_verified_by_handoff"])
                state = result["account_state"]

    def test_pending_orders_and_unavailable_state_are_not_inferred_flat(self):
        state = self.initial()
        state["equity_usd"] = None
        state["buying_power_usd"] = None
        state["pending_orders"] = [{"order_id": "pending", "quantity": 10}]
        state["unresolved_inputs"] = [{"opportunity_id": "missing", "reason": "unavailable_exact_quote_request"}]
        result = self.carry(close_for(self.slots[0], state))
        self.assertEqual(result["account_state"], state)
        self.assertFalse(result["account_runtime_input_gate_passed"])

    def test_insolvent_state_is_preserved_without_reseeding(self):
        state = self.initial()
        state.update(equity_usd="-1.00", buying_power_usd="0.00", cumulative_realized_pnl_usd="-30001.00")
        self.assertEqual(self.carry(close_for(self.slots[0], state))["account_state"], state)

    def test_missing_previous_close_blocks_every_later_date_including_zero_dates(self):
        for slot in self.slots[1:]:
            with self.subTest(date=slot["trading_date"]), self.assertRaisesRegex(ValueError, "cannot reset"):
                a.account_state_input(slot)

    def test_first_date_rejects_a_supplied_previous_balance(self):
        closed = close_for(self.slots[0], self.initial())
        with self.assertRaisesRegex(ValueError, "only the approved seed"):
            self.carry(closed, self.slots[0])

    def test_close_from_wrong_account_horizon_scenario_or_date_is_rejected(self):
        closed = close_for(self.slots[0], self.initial())
        for slot in [p["sessions"][1] for p in self.plan["paths"][1:]] + [self.slots[2]]:
            with self.subTest(slot=slot["session_id"]), self.assertRaisesRegex(ValueError, "same path"):
                self.carry(closed, slot)

    def test_rehashed_changed_balance_cannot_match_pinned_close(self):
        closed = close_for(self.slots[0], self.initial())
        expected = closed["content_sha256"]
        closed["account_state"]["equity_usd"] = "999999.00"
        closed = reseal(closed)
        with self.assertRaisesRegex(ValueError, "pinned previous close differs"):
            self.carry(closed, expected=expected)

    def test_rehashed_slot_cannot_reset_or_skip_registered_session(self):
        for key, value in (("session_index", 0), ("seed_applied", True),
                           ("previous_session_id", self.slots[2]["session_id"]),
                           ("seed_content_sha256", "0" * 64), ("session_index", True)):
            slot = reseal({**self.slots[1], key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.carry(close_for(self.slots[0], self.initial()), slot)

    def test_handoff_does_not_share_mutable_state_with_prior_close(self):
        state = self.initial()
        state["positions"] = [{"symbol": "SYNTHETIC", "quantity": 5}]
        closed = close_for(self.slots[0], state)
        result = self.carry(closed)
        result["account_state"]["positions"][0]["quantity"] = 500
        self.assertEqual(closed["account_state"]["positions"][0]["quantity"], 5)

    def test_currency_must_be_exact_cents_and_complete_state_must_survive(self):
        for value in (30000.0, True, "30000", "1.001", "NaN", "Infinity", "-0.00"):
            state = self.initial(); state["equity_usd"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.carry(close_for(self.slots[0], state))
        for key in self.initial():
            state = self.initial(); del state[key]
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "complete carried"):
                self.carry(close_for(self.slots[0], state))

    def test_retrospective_keys_and_unbound_source_runtime_are_rejected(self):
        state = self.initial()
        state["positions"] = [{"nested": {"ross_fill": "prohibited"}}]
        with self.assertRaisesRegex(ValueError, "retrospective"):
            self.carry(close_for(self.slots[0], state))
        closed = reseal({**close_for(self.slots[0], self.initial()), "source_runtime_content_sha256": None})
        with self.assertRaisesRegex(ValueError, "runtime commitment"):
            self.carry(closed)

    def test_request_windows_keep_exact_nanoseconds_and_all_109_identities(self):
        manifest = a.management_requests(self.opportunities, self.rows)
        index = {r["request_id"]: r for r in manifest["requests"]}
        self.assertEqual([w["opportunity"] for w in manifest["opportunity_windows"]], self.opportunities["opportunities"])
        seen = []
        for window in manifest["opportunity_windows"]:
            op = window["opportunity"]
            ts = op["decision_ts_ns"]
            self.assertEqual(window["start_ns"], ts // 60_000_000_000 * 60_000_000_000)
            self.assertEqual(window["signal_end_ns"], ts + 900_000_000_000)
            self.assertEqual(window["end_ns"], ts + 960_000_000_000)
            request = index[window["request_id"]]
            self.assertLessEqual(request["start_ns"], window["start_ns"])
            self.assertGreaterEqual(request["end_ns"], window["end_ns"])
            self.assertIn(op["opportunity_id"], request["opportunity_ids"])
            self.assertEqual(request["symbol_asof"], op["trading_date"])
            self.assertTrue(request["end_exclusive"])
        for request in manifest["requests"]:
            seen.extend(request["opportunity_ids"])
        self.assertEqual(len(seen), 109)
        self.assertEqual(len(set(seen)), 109)
        self.assertEqual(sum(w["entry_input_status"] == "unavailable" for w in manifest["opportunity_windows"]), 23)

    def test_merged_bounds_equal_union_not_larger_or_outcome_extended(self):
        manifest = a.management_requests(self.opportunities, self.rows)
        windows = {w["opportunity"]["opportunity_id"]: w for w in manifest["opportunity_windows"]}
        previous = {}
        for request in manifest["requests"]:
            children = [windows[oid] for oid in request["opportunity_ids"]]
            self.assertEqual(request["start_ns"], min(w["start_ns"] for w in children))
            self.assertEqual(request["end_ns"], max(w["end_ns"] for w in children))
            key = (request["trading_date"], request["symbol"])
            if key in previous: self.assertGreater(request["start_ns"], previous[key])
            previous[key] = request["end_ns"]
            covered_end = children[0]["end_ns"]
            for window in children[1:]:
                self.assertLessEqual(window["start_ns"], covered_end)
                covered_end = max(covered_end, window["end_ns"])

    def test_missing_or_duplicate_opportunity_population_is_rejected(self):
        for changed in (self.rows[:-1], self.rows + self.rows[:1], list(reversed(self.rows))):
            with self.assertRaises(ValueError): a.session_plan(self.opportunities, changed)
            with self.assertRaises(ValueError): a.management_requests(self.opportunities, changed)

    def test_rehashed_registration_and_changed_parent_bytes_are_rejected(self):
        real_frozen = a.frozen
        changed = a.contract(); changed["user_approved_seed_equity_and_buying_power_usd"] = {"main_account": "60000.00", "small_account": "2000.00"}
        with patch.object(a, "frozen", side_effect=lambda p: reseal(changed) if p == ROOT / a.CONTRACT_PATH else real_frozen(p)):
            with self.assertRaisesRegex(ValueError, "registration"):
                a.validate_registration(ROOT)
        real_sha = a.file_sha
        with patch.object(a, "file_sha", side_effect=lambda p: "f" * 64 if p == ROOT / a.AVAILABILITY_AUDIT else real_sha(p)):
            with self.assertRaisesRegex(ValueError, "parent differs"):
                a.validate_registration(ROOT)

    def test_real_parent_plan_reconstructs_without_provider_or_execution_calls(self):
        with patch.object(socket, "socket", side_effect=AssertionError("no network")), \
             patch.object(a.management, "capture_management_window_from_alpaca", side_effect=AssertionError("no capture")), \
             patch.object(a.management, "simulate_external_fill_management", side_effect=AssertionError("no projection")):
            files = a.build_bundle(ROOT)
        self.assertEqual(len(files), 5)
        report = json.loads(files["readiness-report.json"])
        self.assertEqual(len(report["unavailable_opportunities"]), 23)
        self.assertTrue(report["account_seed_inputs_registered"])
        self.assertFalse(report["descriptive_sip_exit_may_close_account_position"])
        for key, value in a.BOUNDARY.items(): self.assertEqual(report[key], value)

    def test_write_once_and_full_reconstruction_reject_rehashed_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "result"
            first = a.write_bundle(ROOT, out)
            self.assertEqual(a.verify_bundle(ROOT, out), first)
            with self.assertRaises(FileExistsError): a.write_bundle(ROOT, out)
            path = out / "account-seeds.json"
            changed = json.loads(path.read_text()); changed["seeds"][0]["equity_usd"] = "99999.00"
            path.write_bytes(a._bytes(reseal(changed)))
            with self.assertRaisesRegex(ValueError, "source reconstruction"):
                a.verify_bundle(ROOT, out)

    def test_extra_output_file_and_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "result"
            a.write_bundle(ROOT, out)
            (out / "unexpected.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "inventory differs"):
                a.verify_bundle(ROOT, out)
            link = Path(tmp) / "link"; link.symlink_to(ROOT, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                a._output(ROOT, link / "new")
        with self.assertRaisesRegex(ValueError, "frozen repository inputs"):
            a._output(ROOT, ROOT / a.availability.OUTPUT_PATH)


if __name__ == "__main__":
    unittest.main()
