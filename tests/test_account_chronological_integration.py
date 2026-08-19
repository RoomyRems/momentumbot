from __future__ import annotations

import copy
import hashlib
import json
import unittest
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from momentumbot.micro_execution import (
    MicroEntryPlan,
    MicroExecutionOutcome,
    MicroExecutionStatus,
    MicroTriggerMode,
)
from momentumbot.micro_replay import (
    MicroCandidateReplay,
    MicroReplayStep,
)
from momentumbot.models import CandidateQuality, CandidateSnapshot
from momentumbot.research.account_chronological_integration import (
    ACCOUNT_POLICY_BUNDLE_SHA256,
    CONTRACT_ID,
    MICRO_POLICY_FINGERPRINT,
    PANEL_ID,
    REGISTERED_DATES,
    AccountCandidateRuntime,
    AccountSessionSnapshot,
    canonical_fingerprint,
    integrate_account_session,
    load_account_integration_contract,
    validate_account_integration_contract,
)
from momentumbot.research.campaign_portfolio import AccountClass


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT / "research" / "strategy" / "account-chronological-integration-v0.1.json"
)
AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "account-chronological-integration-v0.1-2026-08-19.json"
)
SESSION = date(2026, 8, 19)
HASH_A = "a" * 64
HASH_B = "b" * 64


def _candidate(
    symbol: str,
    *,
    at: str = "2026-08-19T13:00:00+00:00",
    quality: CandidateQuality = CandidateQuality.A_QUALITY,
    rank: int = 1,
    gain: float = 40.0,
) -> CandidateSnapshot:
    return CandidateSnapshot(
        symbol=symbol,
        timestamp=datetime.fromisoformat(at),
        price=10.0,
        cumulative_volume=1_000_000,
        relative_volume=10.0,
        percent_gain=gain,
        float_shares=2_000_000,
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


def _replay(
    symbol: str,
    *,
    qualified_at: str = "2026-08-19T13:00:00+00:00",
    armed_at: str = "2026-08-19T13:00:10+00:00",
    fill_at: str | None = "2026-08-19T13:00:11+00:00",
    fill_price: float = 10.0,
    stop_price: float = 9.0,
    exit_at: str | None = None,
    exit_price: float | None = None,
    status: MicroExecutionStatus = MicroExecutionStatus.FILLED_OPEN,
) -> MicroCandidateReplay:
    armed = pd.Timestamp(armed_at)
    plan = MicroEntryPlan(
        symbol=symbol,
        source_bar_start=armed - pd.Timedelta(seconds=10),
        armed_at=armed,
        expires_at=armed + pd.Timedelta(seconds=10),
        breakout_level=9.98,
        minimum_new_high_price=9.99,
        stop_price=stop_price,
    )
    outcome = None
    if fill_at is not None:
        outcome = MicroExecutionOutcome(
            plan=plan,
            status=status,
            trigger_mode=MicroTriggerMode.CHART_PRICE,
            trigger_time=pd.Timestamp(fill_at),
            trigger_print_price=9.99,
            fill_time=pd.Timestamp(fill_at),
            fill_price=fill_price,
            exit_time=pd.Timestamp(exit_at) if exit_at is not None else None,
            exit_price=exit_price,
        )
    return MicroCandidateReplay(
        symbol=symbol,
        candidate_qualified_at=datetime.fromisoformat(qualified_at),
        policy_name="canonical-micro-current-2026",
        trigger_mode=MicroTriggerMode.CHART_PRICE,
        entry_latency_ms=0.0,
        steps=(
            MicroReplayStep(
                evaluated_at=datetime.fromisoformat(qualified_at),
                pullback_number=1,
                reason="qualified",
                plan=plan,
                features=None,
                outcome=outcome,
            ),
        ),
    )


def _record(
    symbol: str,
    *,
    activation_id: str | None = None,
    snapshot: CandidateSnapshot | None = None,
    replay: MicroCandidateReplay | None = None,
    profile: str = "current-general-2026",
    runtime_status: str | None = None,
) -> AccountCandidateRuntime:
    candidate = snapshot or _candidate(symbol)
    candidate_replay = replay if replay is not None else _replay(symbol)
    return AccountCandidateRuntime(
        activation_id=activation_id or f"activation-{symbol}",
        strategy_profile_id=profile,
        candidate_snapshot=candidate,
        scanner_record_content_sha256=HASH_A,
        micro_runtime_content_sha256=HASH_B,
        runtime_status=runtime_status or "replayed",
        micro_replay=candidate_replay,
    )


def _unavailable_record(
    symbol: str,
    *,
    quality: CandidateQuality = CandidateQuality.REJECT,
    profile: str = "current-general-2026",
) -> AccountCandidateRuntime:
    return AccountCandidateRuntime(
        activation_id=f"activation-{symbol}",
        strategy_profile_id=profile,
        candidate_snapshot=_candidate(symbol, quality=quality),
        scanner_record_content_sha256=HASH_A,
        micro_runtime_content_sha256=HASH_B,
        runtime_status="scanner_rejected_or_micro_unavailable",
        micro_replay=None,
    )


def _account(
    *,
    account_class: AccountClass = AccountClass.MAIN,
    equity: float = 10_000.0,
    buying_power: float = 10_000.0,
    captured_at: str = "2026-08-19T10:59:00+00:00",
) -> AccountSessionSnapshot:
    return AccountSessionSnapshot(
        account_id=f"{account_class.value}-paper",
        account_class=account_class,
        session_date=SESSION,
        captured_at=datetime.fromisoformat(captured_at),
        starting_equity=equity,
        starting_buying_power=buying_power,
        source_id=f"fixture-{account_class.value}-session-state",
        source_content_sha256="c" * 64,
    )


class AccountIntegrationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = load_account_integration_contract(CONTRACT)

    def test_calendar_is_prospectively_frozen_after_review_cutoff(self):
        self.assertEqual(self.payload["contract_id"], CONTRACT_ID)
        self.assertEqual(self.payload["panel_id"], PANEL_ID)
        self.assertEqual(
            REGISTERED_DATES,
            (
                "2026-08-07",
                "2026-08-10",
                "2026-08-11",
                "2026-08-12",
                "2026-08-13",
                "2026-08-14",
                "2026-08-17",
                "2026-08-18",
                "2026-08-19",
                "2026-08-20",
            ),
        )
        self.assertFalse(self.payload["source_inventory_started"])
        self.assertFalse(self.payload["retrospective_review_started"])
        self.assertFalse(
            self.payload["sampling_contract"]["date_selection_uses_symbols"]
        )

    def test_contract_binds_exact_frozen_parents(self):
        parents = self.payload["frozen_parents"]
        self.assertEqual(parents["micro_policy_fingerprint"], MICRO_POLICY_FINGERPRINT)
        self.assertEqual(
            parents["account_policy_bundle_sha256"],
            ACCOUNT_POLICY_BUNDLE_SHA256,
        )

        changed = copy.deepcopy(self.payload)
        changed["frozen_parents"]["micro_policy_fingerprint"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "frozen_parents differ"):
            validate_account_integration_contract(changed)

    def test_dates_and_retrospective_keys_fail_closed(self):
        changed = copy.deepcopy(self.payload)
        changed["sampling_contract"]["registered_dates"][-1] = "2026-08-21"
        with self.assertRaisesRegex(ValueError, "registered_dates differ"):
            validate_account_integration_contract(changed)

        changed = copy.deepcopy(self.payload)
        changed["sampling_contract"]["ross_action"] = "participated"
        with self.assertRaisesRegex(ValueError, "retrospective keys"):
            validate_account_integration_contract(changed)

    def test_contract_has_no_completed_runtime_or_backtest_claim(self):
        self.assertEqual(
            self.payload["execution_status"]["account_runtime"],
            "not_started",
        )
        self.assertIsNone(
            self.payload["execution_status"]["runtime_artifact_sha256"]
        )
        self.assertFalse(self.payload["portfolio_backtest_eligible"])
        self.assertFalse(self.payload["policy_promotion_eligible"])

    def test_mechanical_audit_binds_contract_code_and_documentation(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(
            audit["contract"]["canonical_content_sha256"],
            canonical_fingerprint(self.payload),
        )
        for section, path_key, hash_key in (
            ("contract", "path", "file_sha256"),
            ("implementation", "path", "file_sha256"),
            (
                "implementation",
                "documentation_path",
                "documentation_file_sha256",
            ),
        ):
            path = ROOT / audit[section][path_key]
            self.assertEqual(
                audit[section][hash_key],
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        self.assertFalse(audit["knowledge_boundary"]["uploaded_transcript_archives_opened"])
        self.assertFalse(audit["authority_boundary"]["registered_account_runtime_built"])


class AccountSnapshotTests(unittest.TestCase):
    def test_snapshot_must_be_hash_bound_and_predecision(self):
        with self.assertRaisesRegex(ValueError, "lowercase SHA-256"):
            replace(_account(), source_content_sha256="bad")
        with self.assertRaisesRegex(ValueError, "captured by strategy session start"):
            _account(captured_at="2026-08-19T11:01:00+00:00")
        with self.assertRaisesRegex(ValueError, "registered integration panel"):
            replace(
                _account(),
                session_date=date(2026, 8, 21),
                captured_at=datetime.fromisoformat("2026-08-21T10:59:00+00:00"),
            )

    def test_main_and_small_profiles_cannot_be_mixed(self):
        small_record = _record(
            "SMALL",
            profile="current-small-account-2026",
        )
        with self.assertRaisesRegex(ValueError, "strategy profile differs"):
            integrate_account_session(_account(), (small_record,))

        small_artifact = integrate_account_session(
            _account(
                account_class=AccountClass.SMALL,
                equity=2_000.0,
                buying_power=600.0,
            ),
            (small_record,),
        )
        self.assertEqual(small_artifact["account"]["account_class"], "small")
        self.assertEqual(
            small_artifact["account"]["strategy_profile_id"],
            "current-small-account-2026",
        )


class ChronologicalIntegrationTests(unittest.TestCase):
    def test_full_remaining_risk_capacity_is_sized_in_whole_shares(self):
        artifact = integrate_account_session(_account(), (_record("AAA"),))
        entry = next(
            row for row in artifact["integration_events"] if row["event_type"] == "entry_accepted"
        )
        self.assertEqual(entry["quantity"], 25)
        self.assertEqual(artifact["ledger_artifact"]["account"]["total_open_risk"], 25.0)

    def test_buying_power_and_notional_can_bind_before_risk(self):
        account = _account(equity=10_000.0, buying_power=20.0)
        artifact = integrate_account_session(account, (_record("AAA"),))
        entry = next(
            row for row in artifact["integration_events"] if row["event_type"] == "entry_accepted"
        )
        self.assertEqual(entry["quantity"], 2)
        self.assertEqual(artifact["ledger_artifact"]["account"]["remaining_buying_power"], 0.0)

    def test_zero_whole_share_capacity_records_no_submission(self):
        artifact = integrate_account_session(
            _account(equity=10_000.0, buying_power=5.0),
            (_record("AAA"),),
        )
        event_types = [row["event_type"] for row in artifact["integration_events"]]
        self.assertIn("entry_not_submitted", event_types)
        self.assertNotIn("entry_accepted", event_types)

    def test_exact_time_collision_uses_activation_rank(self):
        lower = _record(
            "LOW",
            snapshot=_candidate("LOW", rank=2, gain=80.0),
        )
        higher = _record(
            "HIGH",
            snapshot=_candidate("HIGH", rank=1, gain=30.0),
        )
        artifact = integrate_account_session(_account(), (lower, higher))
        attempts = [
            row
            for row in artifact["integration_events"]
            if row["event_type"]
            in {"entry_accepted", "entry_rejected", "entry_not_submitted"}
        ]
        self.assertEqual([row["symbol"] for row in attempts], ["HIGH", "LOW"])
        self.assertEqual(attempts[0]["event_type"], "entry_accepted")
        self.assertEqual(attempts[1]["event_type"], "entry_not_submitted")
        self.assertEqual(attempts[1]["reason"], "no_positive_whole_share_capacity")

    def test_chronology_precedes_rank(self):
        early = _record(
            "EARLY",
            snapshot=_candidate("EARLY", rank=5, gain=15.0),
            replay=_replay("EARLY", fill_at="2026-08-19T13:00:11+00:00"),
        )
        late = _record(
            "LATE",
            snapshot=_candidate("LATE", rank=1, gain=100.0),
            replay=_replay(
                "LATE",
                armed_at="2026-08-19T13:00:10+00:00",
                fill_at="2026-08-19T13:00:12+00:00",
            ),
        )
        artifact = integrate_account_session(_account(), (late, early))
        attempts = [
            row
            for row in artifact["integration_events"]
            if row["event_type"]
            in {"entry_accepted", "entry_rejected", "entry_not_submitted"}
        ]
        self.assertEqual([row["symbol"] for row in attempts], ["EARLY", "LATE"])

    def test_same_time_exit_does_not_recycle_capacity_for_entry(self):
        first = _record(
            "FIRST",
            replay=_replay(
                "FIRST",
                fill_at="2026-08-19T13:00:11+00:00",
                exit_at="2026-08-19T13:00:30+00:00",
                exit_price=11.0,
                status=MicroExecutionStatus.TARGET_HIT,
            ),
        )
        second = _record(
            "SECOND",
            snapshot=_candidate(
                "SECOND",
                at="2026-08-19T13:00:20+00:00",
                rank=1,
            ),
            replay=_replay(
                "SECOND",
                qualified_at="2026-08-19T13:00:20+00:00",
                armed_at="2026-08-19T13:00:20+00:00",
                fill_at="2026-08-19T13:00:30+00:00",
            ),
        )
        artifact = integrate_account_session(_account(), (first, second))
        at_collision = [
            row
            for row in artifact["integration_events"]
            if row["at"] == "2026-08-19T13:00:30+00:00"
        ]
        self.assertEqual(
            [row["event_type"] for row in at_collision],
            ["entry_not_submitted", "exit_accepted"],
        )
        self.assertEqual(
            at_collision[0]["reason"],
            "no_positive_whole_share_capacity",
        )

    def test_accepted_plan_local_exit_uses_accepted_quantity(self):
        replay = _replay(
            "AAA",
            exit_at="2026-08-19T13:00:15+00:00",
            exit_price=11.0,
            status=MicroExecutionStatus.TARGET_HIT,
        )
        artifact = integrate_account_session(
            _account(),
            (_record("AAA", replay=replay),),
        )
        exit_event = next(
            row for row in artifact["integration_events"] if row["event_type"] == "exit_accepted"
        )
        self.assertEqual(exit_event["quantity"], 25)
        self.assertEqual(exit_event["realized_pnl"], 25.0)
        self.assertEqual(artifact["ledger_artifact"]["account"]["open_campaign_count"], 0)

    def test_open_outcome_remains_unresolved_and_not_a_backtest(self):
        artifact = integrate_account_session(_account(), (_record("AAA"),))
        authority = artifact["authority_boundary"]
        self.assertEqual(authority["unmodeled_open_positions"], 1)
        self.assertFalse(authority["portfolio_backtest_eligible"])
        self.assertFalse(authority["ross_replication_claim_eligible"])

    def test_rejected_or_unavailable_candidate_is_retained_without_events(self):
        artifact = integrate_account_session(
            _account(),
            (_unavailable_record("NOPE"),),
        )
        self.assertEqual(len(artifact["candidate_records"]), 1)
        self.assertEqual(artifact["candidate_records"][0]["candidate_quality"], "reject")
        self.assertEqual(artifact["integration_events"], [])

    def test_input_order_does_not_change_artifact(self):
        first = _record("AAA", snapshot=_candidate("AAA", rank=1))
        second = _record("BBB", snapshot=_candidate("BBB", rank=2))
        forward = integrate_account_session(_account(), (first, second))
        reverse = integrate_account_session(_account(), (second, first))
        self.assertEqual(forward["content_sha256"], reverse["content_sha256"])
        self.assertEqual(forward, reverse)

    def test_artifact_is_json_safe_and_label_blind(self):
        artifact = integrate_account_session(_account(), (_record("AAA"),))
        encoded = json.dumps(artifact, sort_keys=True, allow_nan=False)
        self.assertEqual(
            artifact["content_sha256"],
            canonical_fingerprint(
                {key: value for key, value in artifact.items() if key != "content_sha256"}
            ),
        )
        keys: set[str] = set()

        def collect(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    keys.add(str(key))
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)

        collect(artifact)
        self.assertTrue(encoded)
        self.assertTrue(
            {
                "ross_action",
                "benchmark_label",
                "retrospective_label",
                "transcript_text",
            }.isdisjoint(keys)
        )

    def test_mismatched_micro_policy_and_other_session_fail_closed(self):
        replay = replace(_replay("AAA"), policy_name="changed-policy")
        with self.assertRaisesRegex(ValueError, "frozen Micro-v0.1"):
            _record("AAA", replay=replay)

        replay = replace(
            _replay("AAA"),
            trigger_mode=MicroTriggerMode.EXECUTION_PROXY,
        )
        with self.assertRaisesRegex(ValueError, "chart-price trigger"):
            _record("AAA", replay=replay)

        replay = replace(_replay("AAA"), entry_latency_ms=100.0)
        with self.assertRaisesRegex(ValueError, "zero-millisecond latency"):
            _record("AAA", replay=replay)

        other_day = _record(
            "AAA",
            snapshot=_candidate("AAA", at="2026-08-18T13:00:00+00:00"),
            replay=_replay("AAA", qualified_at="2026-08-18T13:00:00+00:00"),
        )
        with self.assertRaisesRegex(ValueError, "session_date"):
            integrate_account_session(_account(), (other_day,))

    def test_inconsistent_micro_execution_status_fails_closed(self):
        replay = _replay("AAA")
        step = replay.steps[0]
        assert step.outcome is not None
        changed_outcome = replace(
            step.outcome,
            status=MicroExecutionStatus.NOT_TRIGGERED,
        )
        changed = replace(replay, steps=(replace(step, outcome=changed_outcome),))
        with self.assertRaisesRegex(ValueError, "unfilled Micro status"):
            integrate_account_session(
                _account(),
                (_record("AAA", replay=changed),),
            )


if __name__ == "__main__":
    unittest.main()
