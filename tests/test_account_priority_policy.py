from __future__ import annotations

import copy
import hashlib
import json
import unittest
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

from momentumbot.models import (
    CandidateQuality,
    CandidateSnapshot,
    current_general_2026,
    current_small_account_2026,
    paper_safe_risk,
)
from momentumbot.research.account_priority_policy import (
    CONTRACT_ID,
    GENERAL_PROFILE_FINGERPRINT,
    MAIN_POLICY_ID,
    PAPER_SAFE_RISK_FINGERPRINT,
    SMALL_POLICY_ID,
    SMALL_PROFILE_FINGERPRINT,
    ScarceCapitalOpportunity,
    canonical_fingerprint,
    load_account_priority_contract,
    materialize_account_constraints,
    order_scarce_capital_opportunities,
    paper_account_policy,
    policy_bundle_manifest,
    risk_policy_fingerprint,
    scarcity_priority_artifact,
    strategy_profile_fingerprint,
    validate_account_priority_contract,
)
from momentumbot.research.campaign_portfolio import AccountClass
from momentumbot.research.campaign_portfolio import (
    CampaignPortfolioLedger,
    EntryFill,
    EntryRole,
    PlanEmission,
)
from momentumbot.scanner import rank_candidates


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research" / "strategy" / "paper-account-scarcity-policy-v0.1.json"
AUDIT = ROOT / "research" / "data-audits" / "paper-account-scarcity-policy-v0.1-2026-08-19.json"


def _candidate(
    symbol: str,
    *,
    at: str = "2026-08-19T13:00:00+00:00",
    quality: CandidateQuality = CandidateQuality.A_QUALITY,
    rank: int | None = 1,
    gain: float = 40.0,
    rvol: float = 10.0,
    volume: int = 1_000_000,
    float_shares: int | None = 2_000_000,
) -> CandidateSnapshot:
    return CandidateSnapshot(
        symbol=symbol,
        timestamp=datetime.fromisoformat(at),
        price=5.0,
        cumulative_volume=volume,
        relative_volume=rvol,
        percent_gain=gain,
        float_shares=float_shares,
        float_rotation=0.5,
        has_fresh_news=True,
        top_gainer_rank=rank,
        pillars={
            "percent_gain": True,
            "relative_volume": True,
            "fresh_news": True,
            "price": True,
            "float": True,
        },
        quality=quality,
    )


def _opportunity(
    opportunity_id: str,
    candidate: CandidateSnapshot,
    *,
    execution_at: str = "2026-08-19T13:01:00+00:00",
    account_id: str = "main-paper",
    account_class: AccountClass = AccountClass.MAIN,
    plan_id: str | None = None,
) -> ScarceCapitalOpportunity:
    return ScarceCapitalOpportunity(
        opportunity_id=opportunity_id,
        account_id=account_id,
        account_class=account_class,
        candidate_activation_id=f"activation-{candidate.symbol}",
        plan_id=plan_id or f"plan-{candidate.symbol}",
        execution_at=datetime.fromisoformat(execution_at),
        candidate_snapshot=candidate,
    )


class AccountPriorityContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = load_account_priority_contract(CONTRACT)

    def test_contract_binds_exact_frozen_parents_and_two_accounts(self):
        self.assertEqual(self.payload["contract_id"], CONTRACT_ID)
        self.assertEqual(
            self.payload["frozen_parents"]["campaign_ledger_contract_content_sha256"],
            "f2a80f4350e6283e2638702d70515bf03ee6c930e7d52706d09ef5e1d9f419b6",
        )
        self.assertEqual(
            {row["policy_id"] for row in self.payload["account_policies"]},
            {MAIN_POLICY_ID, SMALL_POLICY_ID},
        )

    def test_transcript_observations_cannot_set_runtime_risk(self):
        changed = copy.deepcopy(self.payload)
        changed["offline_transcript_boundary_evidence"]["used_to_set_numeric_risk_values"] = True
        with self.assertRaisesRegex(ValueError, "cannot calibrate"):
            validate_account_priority_contract(changed)

    def test_cross_account_priority_cannot_be_silently_enabled(self):
        changed = copy.deepcopy(self.payload)
        changed["scarce_capital_priority"]["cross_account_priority"] = "main_first"
        with self.assertRaisesRegex(ValueError, "cross-account divided attention"):
            validate_account_priority_contract(changed)

    def test_registered_paper_safe_fraction_cannot_be_retuned(self):
        changed = copy.deepcopy(self.payload)
        changed["account_policies"][1]["risk_per_campaign_fraction_of_starting_equity"] = 0.10
        with self.assertRaisesRegex(ValueError, "must preserve paper-safe"):
            validate_account_priority_contract(changed)

    def test_policy_bundle_matches_registered_order(self):
        bundle = policy_bundle_manifest()
        self.assertEqual(
            bundle["scarcity_order"],
            self.payload["scarce_capital_priority"]["ordered_fields"],
        )
        self.assertEqual(bundle["cross_account_priority"], "unresolved_fail_closed")

    def test_mechanical_audit_binds_contract_bundle_code_and_documentation(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(
            audit["contract"]["canonical_content_sha256"],
            canonical_fingerprint(self.payload),
        )
        self.assertEqual(
            audit["policy_bundle"]["canonical_content_sha256"],
            canonical_fingerprint(policy_bundle_manifest()),
        )
        for section, path_key, hash_key in (
            ("contract", "path", "file_sha256"),
            ("implementation", "path", "file_sha256"),
            ("implementation", "documentation_path", "documentation_file_sha256"),
        ):
            path = ROOT / audit[section][path_key]
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                audit[section][hash_key],
            )
        self.assertFalse(audit["offline_evidence_review"]["used_to_set_numeric_risk_values"])
        self.assertFalse(audit["authority_boundary"]["historical_runtime_integration"])


class PaperAccountMaterializationTests(unittest.TestCase):
    def test_parent_fingerprints_are_recomputed_from_current_code(self):
        self.assertEqual(risk_policy_fingerprint(paper_safe_risk()), PAPER_SAFE_RISK_FINGERPRINT)
        self.assertEqual(
            strategy_profile_fingerprint(current_general_2026()),
            GENERAL_PROFILE_FINGERPRINT,
        )
        self.assertEqual(
            strategy_profile_fingerprint(current_small_account_2026()),
            SMALL_PROFILE_FINGERPRINT,
        )

    def test_main_policy_materializes_existing_paper_safe_fractions(self):
        policy = paper_account_policy(AccountClass.MAIN)
        constraints = materialize_account_constraints(
            policy,
            account_id="main-paper",
            starting_equity=100_000.0,
            starting_buying_power=150_000.0,
        )
        self.assertEqual(constraints.policy_id, MAIN_POLICY_ID)
        self.assertEqual(constraints.max_campaign_open_notional, 50_000.0)
        self.assertEqual(constraints.max_total_open_notional, 50_000.0)
        self.assertEqual(constraints.max_campaign_open_risk, 250.0)
        self.assertEqual(constraints.max_daily_loss_dollars, 1_000.0)
        self.assertEqual(constraints.max_open_positions, 1)
        self.assertEqual(constraints.max_entries_per_campaign, 2)
        self.assertTrue(constraints.allow_reentry)
        self.assertIsNone(constraints.max_entry_slippage_bps)

    def test_small_policy_is_separate_and_buying_power_binds_notional(self):
        policy = paper_account_policy(AccountClass.SMALL)
        constraints = materialize_account_constraints(
            policy,
            account_id="small-paper",
            starting_equity=2_000.0,
            starting_buying_power=600.0,
        )
        self.assertEqual(constraints.policy_id, SMALL_POLICY_ID)
        self.assertEqual(constraints.account_class, AccountClass.SMALL)
        self.assertEqual(constraints.max_campaign_open_notional, 600.0)
        self.assertEqual(constraints.max_campaign_open_risk, 5.0)
        self.assertEqual(constraints.max_daily_loss_dollars, 20.0)

    def test_unregistered_policy_mutation_fails_closed(self):
        policy = paper_account_policy(AccountClass.MAIN)
        changed = replace(policy, strategy_profile_fingerprint="0" * 64)
        with self.assertRaisesRegex(ValueError, "does not match"):
            materialize_account_constraints(
                changed,
                account_id="main-paper",
                starting_equity=100_000.0,
                starting_buying_power=100_000.0,
            )

    def test_materialized_policy_composes_with_frozen_ledger(self):
        constraints = materialize_account_constraints(
            paper_account_policy(AccountClass.MAIN),
            account_id="main-paper",
            starting_equity=100_000.0,
            starting_buying_power=100_000.0,
        )
        ledger = CampaignPortfolioLedger(date(2026, 8, 19), constraints)
        at = datetime.fromisoformat("2026-08-19T13:00:00+00:00")
        ledger.record_plan_emission(PlanEmission("activation-1", "plan-1", "AAA", at))
        decision = ledger.apply_entry_fill(
            EntryFill(
                "fill-1",
                "activation-1",
                "plan-1",
                "AAA",
                datetime.fromisoformat("2026-08-19T13:00:01+00:00"),
                100,
                10.0,
                10.0,
                9.0,
                EntryRole.STARTER,
                True,
            )
        )
        self.assertTrue(decision.accepted)
        self.assertEqual(ledger.total_open_risk, 100.0)


class ScarceCapitalPriorityTests(unittest.TestCase):
    def test_exact_time_collision_reuses_existing_candidate_ranking(self):
        candidates = (
            _candidate("LOW", rank=2, gain=60.0),
            _candidate("TOP", rank=1, gain=35.0),
            _candidate("COND", quality=CandidateQuality.CONDITIONAL, rank=1, gain=90.0),
        )
        expected = [row.symbol for row in rank_candidates(candidates)]
        ordered = order_scarce_capital_opportunities(
            _opportunity(f"opp-{row.symbol}", row) for row in reversed(candidates)
        )
        self.assertEqual([row.candidate_snapshot.symbol for row in ordered], expected)

    def test_execution_chronology_precedes_candidate_rank(self):
        better = _opportunity(
            "better",
            _candidate("BETTER", rank=1, gain=100.0),
            execution_at="2026-08-19T13:02:00+00:00",
        )
        earlier = _opportunity(
            "earlier",
            _candidate("EARLY", rank=5, gain=15.0),
            execution_at="2026-08-19T13:01:00+00:00",
        )
        ordered = order_scarce_capital_opportunities((better, earlier))
        self.assertEqual([row.opportunity_id for row in ordered], ["earlier", "better"])

    def test_stable_tie_breakers_are_input_order_independent(self):
        same = _candidate("AAA")
        rows = (
            _opportunity("z", same, plan_id="plan-z"),
            _opportunity("a", same, plan_id="plan-a"),
        )
        forward = order_scarce_capital_opportunities(rows)
        reverse = order_scarce_capital_opportunities(reversed(rows))
        self.assertEqual([row.opportunity_id for row in forward], ["a", "z"])
        self.assertEqual(forward, reverse)

    def test_cross_account_batch_fails_closed(self):
        main = _opportunity("main", _candidate("AAA"))
        small = _opportunity(
            "small",
            _candidate("BBB"),
            account_id="small-paper",
            account_class=AccountClass.SMALL,
        )
        with self.assertRaisesRegex(ValueError, "cross-account priority is unresolved"):
            order_scarce_capital_opportunities((main, small))

    def test_future_candidate_snapshot_is_rejected(self):
        future = _candidate("LATE", at="2026-08-19T13:02:00+00:00")
        with self.assertRaisesRegex(ValueError, "cannot be available after"):
            _opportunity(
                "late",
                future,
                execution_at="2026-08-19T13:01:00+00:00",
            )

    def test_priority_artifact_is_json_safe_and_label_blind(self):
        payload = scarcity_priority_artifact(
            (
                _opportunity("b", _candidate("BBB", rank=2)),
                _opportunity("a", _candidate("AAA", rank=1)),
            )
        )
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
        self.assertEqual(payload["artifact_type"], "paper_account_scarcity_priority_shadow")
        self.assertEqual(
            [row["opportunity_id"] for row in payload["ordered_opportunities"]],
            ["a", "b"],
        )
        self.assertNotIn("ross_action", encoded)
        self.assertNotIn("benchmark_label", encoded)
        self.assertNotIn("future_outcome", encoded)

    def test_timezone_naive_execution_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "execution_at must be timezone-aware"):
            _opportunity(
                "naive",
                _candidate("AAA"),
                execution_at="2026-08-19T13:01:00",
            )

    def test_ordered_collision_has_deterministic_ledger_consequence(self):
        constraints = materialize_account_constraints(
            paper_account_policy(AccountClass.MAIN),
            account_id="main-paper",
            starting_equity=100_000.0,
            starting_buying_power=100_000.0,
        )
        ledger = CampaignPortfolioLedger(date(2026, 8, 19), constraints)
        event_at = datetime.fromisoformat("2026-08-19T13:01:00+00:00")
        candidates = (
            _opportunity("lower", _candidate("LOWER", rank=2)),
            _opportunity("higher", _candidate("HIGHER", rank=1)),
        )
        for item in candidates:
            ledger.record_plan_emission(
                PlanEmission(
                    item.candidate_activation_id,
                    item.plan_id,
                    item.candidate_snapshot.symbol,
                    datetime.fromisoformat("2026-08-19T13:00:30+00:00"),
                )
            )

        decisions = []
        for item in order_scarce_capital_opportunities(candidates):
            decisions.append(
                (
                    item.opportunity_id,
                    ledger.apply_entry_fill(
                        EntryFill(
                            f"fill-{item.opportunity_id}",
                            item.candidate_activation_id,
                            item.plan_id,
                            item.candidate_snapshot.symbol,
                            event_at,
                            100,
                            10.0,
                            10.0,
                            9.0,
                            EntryRole.STARTER,
                            True,
                        )
                    ),
                )
            )
        self.assertEqual(decisions[0][0], "higher")
        self.assertTrue(decisions[0][1].accepted)
        self.assertEqual(decisions[1][0], "lower")
        self.assertIn("open_position_limit", decisions[1][1].reasons)


if __name__ == "__main__":
    unittest.main()
