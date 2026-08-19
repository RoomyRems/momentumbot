from __future__ import annotations

import copy
import hashlib
import json
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from momentumbot.research.campaign_portfolio import (
    CONTRACT_ID,
    AccountClass,
    AccountConstraints,
    CampaignPortfolioLedger,
    EntryFill,
    EntryRole,
    ExitFill,
    PlanEmission,
    canonical_fingerprint,
    load_campaign_portfolio_contract,
    validate_campaign_portfolio_contract,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research" / "strategy" / "campaign-portfolio-account-state-v0.1.json"
AUDIT = ROOT / "research" / "data-audits" / "campaign-portfolio-account-state-v0.1-2026-08-19.json"
SESSION = date(2026, 8, 19)


def _constraints(
    *,
    account_id: str | None = None,
    policy_id: str = "fixture-main-v0.1",
    account_class: AccountClass = AccountClass.MAIN,
    buying_power: float = 10_000.0,
    max_open_positions: int = 2,
    max_daily_loss: float = 500.0,
    allow_reentry: bool = True,
    max_slippage_bps: float | None = 100.0,
) -> AccountConstraints:
    return AccountConstraints(
        account_id=account_id or f"{account_class.value}-account",
        policy_id=policy_id,
        account_class=account_class,
        starting_equity=10_000.0,
        starting_buying_power=buying_power,
        max_open_positions=max_open_positions,
        max_total_open_notional=10_000.0,
        max_campaign_open_notional=5_000.0,
        max_total_open_risk=2_000.0,
        max_campaign_open_risk=1_000.0,
        max_entries_per_campaign=3,
        starter_max_notional=2_000.0,
        max_daily_loss_dollars=max_daily_loss,
        giveback_fraction=0.50,
        allow_reentry=allow_reentry,
        max_entry_slippage_bps=max_slippage_bps,
    )


def _time(value: str) -> pd.Timestamp:
    return pd.Timestamp(f"2026-08-19T{value}Z")


def _plan(
    activation_id: str = "activation-1",
    plan_id: str = "plan-1",
    symbol: str = "TEST",
    at: str = "13:00:00",
) -> PlanEmission:
    return PlanEmission(activation_id, plan_id, symbol, _time(at))


def _entry(
    *,
    fill_id: str = "entry-1",
    activation_id: str = "activation-1",
    plan_id: str = "plan-1",
    symbol: str = "TEST",
    at: str = "13:00:01",
    quantity: int = 100,
    reference_price: float = 10.0,
    fill_price: float = 10.0,
    stop_price: float = 9.0,
    role: EntryRole = EntryRole.STARTER,
    execution_approved: bool = True,
) -> EntryFill:
    return EntryFill(
        fill_id,
        activation_id,
        plan_id,
        symbol,
        _time(at),
        quantity,
        reference_price,
        fill_price,
        stop_price,
        role,
        execution_approved,
    )


def _exit(
    *,
    fill_id: str = "exit-1",
    activation_id: str = "activation-1",
    symbol: str = "TEST",
    at: str = "13:00:02",
    quantity: int = 100,
    fill_price: float = 11.0,
) -> ExitFill:
    return ExitFill(fill_id, activation_id, symbol, _time(at), quantity, fill_price)


class CampaignPortfolioContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = load_campaign_portfolio_contract(CONTRACT)

    def test_contract_preserves_frozen_parents_and_registers_no_account_values(self):
        self.assertEqual(self.payload["contract_id"], CONTRACT_ID)
        self.assertFalse(self.payload["contains_account_limit_values"])
        self.assertEqual(
            self.payload["frozen_parents"]["micro_policy_fingerprint"],
            "49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa",
        )
        self.assertEqual(
            self.payload["frozen_parents"]["context_comparison_content_sha256"],
            "d93d61ed0ebd5657bbed135beb7fe2d7b0f337d1e3f76720c0f1dcff7908ff54",
        )

    def test_contract_fails_if_retrospective_labels_are_enabled(self):
        changed = copy.deepcopy(self.payload)
        changed["knowledge_policy"]["retrospective_behavior_labels_allowed"] = True
        with self.assertRaisesRegex(ValueError, "must be False"):
            validate_campaign_portfolio_contract(changed)

    def test_contract_fails_if_simultaneous_selection_authority_is_added(self):
        changed = copy.deepcopy(self.payload)
        changed["authority_boundary"]["chooses_between_simultaneous_opportunities"] = True
        with self.assertRaisesRegex(ValueError, "must be False"):
            validate_campaign_portfolio_contract(changed)

    def test_contract_fingerprint_is_order_independent(self):
        self.assertEqual(
            canonical_fingerprint({"b": 2, "a": {"d": 4, "c": 3}}),
            canonical_fingerprint({"a": {"c": 3, "d": 4}, "b": 2}),
        )

    def test_mechanical_audit_binds_contract_code_and_documentation(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(
            audit["contract"]["canonical_content_sha256"],
            canonical_fingerprint(self.payload),
        )
        for section, path_key, hash_key in (
            ("contract", "path", "file_sha256"),
            ("implementation", "path", "file_sha256"),
            ("implementation", "documentation_path", "documentation_file_sha256"),
        ):
            path = ROOT / audit[section][path_key]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(audit[section][hash_key], digest)
        self.assertFalse(audit["authority_boundary"]["runtime_integration"])
        self.assertFalse(audit["authority_boundary"]["policy_promotion_eligible"])
        self.assertFalse(audit["knowledge_boundary"]["supplied_transcript_archives_opened"])


class CampaignPortfolioLedgerTests(unittest.TestCase):
    def test_repeated_plans_share_one_campaign_but_accounts_do_not(self):
        main = CampaignPortfolioLedger(SESSION, _constraints())
        first = main.record_plan_emission(_plan())
        second = main.record_plan_emission(_plan(plan_id="plan-2", at="13:00:01"))
        self.assertIs(first, second)
        self.assertEqual(first.plan_ids, ["plan-1", "plan-2"])

        small = CampaignPortfolioLedger(
            SESSION,
            _constraints(
                policy_id="fixture-small-v0.1",
                account_class=AccountClass.SMALL,
            ),
        )
        small_campaign = small.record_plan_emission(_plan())
        self.assertNotEqual(first.campaign_id, small_campaign.campaign_id)

        other_main = CampaignPortfolioLedger(
            SESSION,
            _constraints(account_id="second-main-account"),
        )
        other_campaign = other_main.record_plan_emission(_plan())
        self.assertNotEqual(first.campaign_id, other_campaign.campaign_id)

    def test_entry_updates_position_buying_power_and_open_risk(self):
        ledger = CampaignPortfolioLedger(SESSION, _constraints())
        campaign = ledger.record_plan_emission(_plan())
        decision = ledger.apply_entry_fill(_entry())

        self.assertTrue(decision.accepted)
        self.assertEqual(campaign.quantity, 100)
        self.assertEqual(campaign.average_entry_price, 10.0)
        self.assertEqual(ledger.remaining_buying_power, 9_000.0)
        self.assertEqual(ledger.total_open_notional, 1_000.0)
        self.assertEqual(ledger.total_open_risk, 100.0)

    def test_malformed_fill_values_reject_without_mutating_position_state(self):
        ledger = CampaignPortfolioLedger(SESSION, _constraints())
        campaign = ledger.record_plan_emission(_plan())
        rejected = ledger.apply_entry_fill(
            _entry(quantity=100.5, fill_price="bad", stop_price="bad")  # type: ignore[arg-type]
        )
        self.assertFalse(rejected.accepted)
        self.assertIn("invalid_quantity", rejected.reasons)
        self.assertIn("invalid_fill_price", rejected.reasons)
        self.assertIn("invalid_stop_price", rejected.reasons)
        self.assertEqual(campaign.quantity, 0)
        self.assertEqual(ledger.remaining_buying_power, 10_000.0)

    def test_add_requires_open_position_and_cannot_average_down(self):
        ledger = CampaignPortfolioLedger(SESSION, _constraints())
        ledger.record_plan_emission(_plan())
        ledger.record_plan_emission(_plan(plan_id="plan-2", at="13:00:01"))
        self.assertTrue(ledger.apply_entry_fill(_entry(at="13:00:02")).accepted)

        rejected = ledger.apply_entry_fill(
            _entry(
                fill_id="entry-2",
                plan_id="plan-2",
                at="13:00:03",
                fill_price=9.50,
                stop_price=9.00,
                role=EntryRole.ADD,
            )
        )
        self.assertFalse(rejected.accepted)
        self.assertIn("averaging_down_prohibited", rejected.reasons)
        self.assertEqual(ledger.campaigns["activation-1"].quantity, 100)

    def test_first_campaign_fill_cannot_be_mislabeled_as_an_add(self):
        ledger = CampaignPortfolioLedger(SESSION, _constraints())
        ledger.record_plan_emission(_plan())
        rejected = ledger.apply_entry_fill(_entry(role=EntryRole.ADD))
        self.assertFalse(rejected.accepted)
        self.assertIn("entry_role_must_be_starter", rejected.reasons)
        self.assertIn("first_session_entry_must_be_starter", rejected.reasons)

    def test_flat_campaign_requires_reentry_role_and_registered_permission(self):
        ledger = CampaignPortfolioLedger(SESSION, _constraints(allow_reentry=False))
        ledger.record_plan_emission(_plan())
        ledger.record_plan_emission(_plan(plan_id="plan-2", at="13:00:01"))
        self.assertTrue(ledger.apply_entry_fill(_entry(at="13:00:02")).accepted)
        self.assertTrue(ledger.apply_exit_fill(_exit(at="13:00:03")).accepted)

        rejected = ledger.apply_entry_fill(
            _entry(
                fill_id="entry-2",
                plan_id="plan-2",
                at="13:00:04",
                role=EntryRole.REENTRY,
            )
        )
        self.assertFalse(rejected.accepted)
        self.assertEqual(rejected.reasons, ("reentry_disabled",))

    def test_buying_power_and_position_count_fail_closed(self):
        ledger = CampaignPortfolioLedger(
            SESSION,
            _constraints(buying_power=1_500.0, max_open_positions=1),
        )
        ledger.record_plan_emission(_plan())
        ledger.record_plan_emission(
            _plan("activation-2", "plan-2", "TWO", "13:00:00")
        )
        self.assertTrue(ledger.apply_entry_fill(_entry(at="13:00:01")).accepted)
        rejected = ledger.apply_entry_fill(
            _entry(
                fill_id="entry-2",
                activation_id="activation-2",
                plan_id="plan-2",
                symbol="TWO",
                at="13:00:02",
                quantity=100,
            )
        )
        self.assertFalse(rejected.accepted)
        self.assertIn("insufficient_buying_power", rejected.reasons)
        self.assertIn("open_position_limit", rejected.reasons)

    def test_halt_blocks_fills_until_resume(self):
        ledger = CampaignPortfolioLedger(SESSION, _constraints())
        ledger.record_plan_emission(_plan())
        ledger.set_halt("TEST", True, _time("13:00:01"))
        rejected = ledger.apply_entry_fill(_entry(at="13:00:02"))
        self.assertIn("symbol_halted", rejected.reasons)

        ledger.set_halt("TEST", False, _time("13:00:03"))
        accepted = ledger.apply_entry_fill(
            _entry(fill_id="entry-2", at="13:00:04")
        )
        self.assertTrue(accepted.accepted)

    def test_entry_slippage_is_recorded_and_can_fail_a_registered_limit(self):
        ledger = CampaignPortfolioLedger(SESSION, _constraints(max_slippage_bps=25.0))
        ledger.record_plan_emission(_plan())
        rejected = ledger.apply_entry_fill(
            _entry(reference_price=10.0, fill_price=10.10)
        )
        self.assertFalse(rejected.accepted)
        self.assertIn("entry_slippage_limit", rejected.reasons)
        self.assertAlmostEqual(rejected.observed_slippage_bps or 0.0, 100.0)

    def test_profit_giveback_lock_uses_ordered_realized_pnl(self):
        ledger = CampaignPortfolioLedger(
            SESSION,
            _constraints(max_daily_loss=1_000.0),
        )
        ledger.record_plan_emission(_plan())
        ledger.record_plan_emission(
            _plan("activation-2", "plan-2", "TWO", "13:00:01")
        )
        ledger.apply_entry_fill(_entry(at="13:00:02"))
        ledger.apply_exit_fill(_exit(at="13:00:03", fill_price=12.0))
        self.assertEqual(ledger.high_water_pnl, 200.0)

        ledger.apply_entry_fill(
            _entry(
                fill_id="entry-2",
                activation_id="activation-2",
                plan_id="plan-2",
                symbol="TWO",
                at="13:00:04",
            )
        )
        ledger.apply_exit_fill(
            _exit(
                fill_id="exit-2",
                activation_id="activation-2",
                symbol="TWO",
                at="13:00:05",
                fill_price=9.0,
            )
        )
        self.assertEqual(ledger.realized_pnl, 100.0)
        self.assertTrue(ledger.locked)
        self.assertEqual(ledger.lock_reason, "profit_giveback")

    def test_loss_lock_is_terminal_for_entries_but_never_blocks_exits(self):
        ledger = CampaignPortfolioLedger(
            SESSION,
            _constraints(max_daily_loss=50.0),
        )
        ledger.record_plan_emission(_plan())
        ledger.record_plan_emission(
            _plan("activation-2", "plan-2", "TWO", "13:00:01")
        )
        self.assertTrue(ledger.apply_entry_fill(_entry(at="13:00:02")).accepted)
        loss = ledger.apply_exit_fill(_exit(at="13:00:03", fill_price=9.0))
        self.assertTrue(loss.accepted)
        self.assertTrue(ledger.locked)
        self.assertEqual(ledger.lock_reason, "daily_max_loss")

        rejected = ledger.apply_entry_fill(
            _entry(
                fill_id="entry-2",
                activation_id="activation-2",
                plan_id="plan-2",
                symbol="TWO",
                at="13:00:04",
            )
        )
        self.assertIn("account_locked", rejected.reasons)

        # A manual lock with an open position marks flattening as required and
        # still permits the caller-supplied exit fill.
        second = CampaignPortfolioLedger(SESSION, _constraints())
        second.record_plan_emission(_plan())
        second.apply_entry_fill(_entry())
        second.lock_account("manual_walk_away", _time("13:00:02"))
        self.assertTrue(second.flatten_required)
        self.assertTrue(second.apply_exit_fill(_exit(at="13:00:03")).accepted)
        self.assertFalse(second.flatten_required)

    def test_artifact_records_simultaneous_opportunities_and_is_label_blind(self):
        ledger = CampaignPortfolioLedger(SESSION, _constraints())
        ledger.record_plan_emission(_plan())
        ledger.record_plan_emission(
            _plan("activation-2", "plan-2", "TWO", "13:00:00")
        )
        payload = ledger.runtime_artifact()
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False)

        self.assertEqual(payload["artifact_type"], "campaign_portfolio_account_state_shadow")
        self.assertEqual(len(payload["simultaneous_opportunity_groups"]), 1)
        self.assertEqual(
            payload["simultaneous_opportunity_groups"][0]["selection_status"],
            "unresolved_no_selection_authority",
        )
        self.assertNotIn("ross_fill", encoded)
        self.assertNotIn("benchmark_label", encoded)
        self.assertNotIn("reported_action", encoded)

    def test_events_must_be_session_bounded_and_causally_ordered(self):
        ledger = CampaignPortfolioLedger(SESSION, _constraints())
        ledger.record_plan_emission(_plan(at="13:00:02"))
        with self.assertRaisesRegex(ValueError, "nondecreasing causal order"):
            ledger.record_plan_emission(_plan(plan_id="plan-2", at="13:00:01"))
        with self.assertRaisesRegex(ValueError, "session_date"):
            ledger.record_plan_emission(
                PlanEmission(
                    "activation-2",
                    "plan-3",
                    "TWO",
                    pd.Timestamp("2026-08-20T13:00:00Z"),
                )
            )

    def test_structurally_invalid_event_does_not_advance_ledger_clock(self):
        ledger = CampaignPortfolioLedger(SESSION, _constraints())
        with self.assertRaisesRegex(ValueError, "unknown candidate activation"):
            ledger.apply_entry_fill(_entry(at="13:00:05"))
        campaign = ledger.record_plan_emission(_plan(at="13:00:01"))
        self.assertEqual(campaign.plan_ids, ["plan-1"])


if __name__ == "__main__":
    unittest.main()
