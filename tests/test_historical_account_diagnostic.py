from __future__ import annotations

import copy
import hashlib
import json
import unittest
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from momentumbot.micro_execution import (
    MicroEntryPlan,
    MicroExecutionOutcome,
    MicroExecutionStatus,
    MicroTriggerMode,
)
from momentumbot.micro_replay import MicroCandidateReplay, MicroReplayStep
from momentumbot.models import (
    CandidateQuality,
    CandidateSnapshot,
    current_general_2026,
    current_small_account_2026,
)
from momentumbot.research.account_chronological_integration import (
    AccountCandidateRuntime,
    AccountSessionSnapshot,
    integrate_account_session,
)
from momentumbot.research.campaign_portfolio import AccountClass
from momentumbot.research.historical_account_diagnostic import (
    CONTRACT_ID,
    MICRO_POLICY_FINGERPRINT,
    REGISTERED_DATES,
    HistoricalDiagnosticAccountSnapshot,
    candidate_snapshot_from_causal_row,
    load_historical_diagnostic_contract,
    micro_replay_from_runtime,
    validate_historical_diagnostic_contract,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research" / "strategy" / "historical-account-diagnostic-v0.1.json"
AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "historical-account-diagnostic-v0.1-2026-08-19.json"
)
SESSION = date(2026, 7, 10)


def _scanner_row(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "symbol": "TEST",
        "activation_time": "2026-07-10T13:00:00+00:00",
        "decision_time": "2026-07-10T13:00:00+00:00",
        "candidate_completed_bar_present": True,
        "price": 4.0,
        "cumulative_volume": 1_000_000,
        "exact_same_time_rvol": 10.0,
        "percent_gain": 30.0,
        "estimated_float_shares": 2_000_000,
        "has_provider_news_as_of": True,
        "top_gainer_rank": 1,
    }
    row.update(changes)
    return row


def _candidate() -> CandidateSnapshot:
    return candidate_snapshot_from_causal_row(
        _scanner_row(),
        current_general_2026(),
    )


def _plan() -> MicroEntryPlan:
    return MicroEntryPlan(
        symbol="TEST",
        source_bar_start=pd.Timestamp("2026-07-10T13:00:00+00:00"),
        armed_at=pd.Timestamp("2026-07-10T13:00:10+00:00"),
        expires_at=pd.Timestamp("2026-07-10T13:00:20+00:00"),
        breakout_level=9.98,
        minimum_new_high_price=9.99,
        stop_price=9.0,
    )


def _replay() -> MicroCandidateReplay:
    plan = _plan()
    outcome = MicroExecutionOutcome(
        plan=plan,
        status=MicroExecutionStatus.STOPPED,
        trigger_mode=MicroTriggerMode.CHART_PRICE,
        trigger_time=pd.Timestamp("2026-07-10T13:00:11+00:00"),
        trigger_print_price=9.99,
        fill_time=pd.Timestamp("2026-07-10T13:00:11+00:00"),
        fill_price=10.0,
        exit_time=pd.Timestamp("2026-07-10T13:00:12+00:00"),
        exit_price=9.0,
    )
    return MicroCandidateReplay(
        symbol="TEST",
        candidate_qualified_at=datetime.fromisoformat(
            "2026-07-10T13:00:00+00:00"
        ),
        policy_name="canonical-micro-current-2026",
        trigger_mode=MicroTriggerMode.CHART_PRICE,
        entry_latency_ms=0.0,
        steps=(
            MicroReplayStep(
                evaluated_at=datetime.fromisoformat(
                    "2026-07-10T13:00:00+00:00"
                ),
                pullback_number=1,
                reason="qualified",
                plan=plan,
                features=None,
                outcome=outcome,
            ),
        ),
    )


def _historical_account() -> HistoricalDiagnosticAccountSnapshot:
    return HistoricalDiagnosticAccountSnapshot(
        account_id="synthetic-main-30000-historical-diagnostic",
        account_class=AccountClass.MAIN,
        session_date=SESSION,
        captured_at=datetime.fromisoformat("2026-07-10T10:59:00+00:00"),
        starting_equity=30_000.0,
        starting_buying_power=30_000.0,
        source_id="registered-synthetic-fixed-balance-v0.1",
        source_content_sha256="a" * 64,
    )


class HistoricalDiagnosticContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = load_historical_diagnostic_contract(CONTRACT)

    def test_contract_is_retrospective_non_promotable_and_separate(self):
        self.assertEqual(self.payload["contract_id"], CONTRACT_ID)
        self.assertEqual(tuple(self.payload["sampling_contract"]["dates"]), REGISTERED_DATES)
        self.assertFalse(self.payload["prospective_contract_modified"])
        self.assertFalse(self.payload["portfolio_backtest_eligible"])
        self.assertFalse(self.payload["policy_promotion_eligible"])
        self.assertEqual(
            self.payload["registration_status"],
            "registered_after_source_runtime_before_account_composition",
        )

    def test_contract_mutations_fail_closed(self):
        changed = copy.deepcopy(self.payload)
        changed["frozen_parents"]["micro_policy_fingerprint"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "frozen_parents"):
            validate_historical_diagnostic_contract(changed)

        changed = copy.deepcopy(self.payload)
        changed["sampling_contract"]["dates"][-1] = "2026-07-24"
        with self.assertRaisesRegex(ValueError, "sampling dates"):
            validate_historical_diagnostic_contract(changed)

    def test_mechanical_audit_binds_deliverables(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        for item in audit["bound_files"]:
            path = ROOT / item["path"]
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                item["file_sha256"],
            )
        result = json.loads(
            (ROOT / audit["result"]["manifest_path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(
            result["content_sha256"],
            audit["result"]["manifest_content_sha256"],
        )
        self.assertFalse(audit["authority_boundary"]["full_backtest_completed"])


class CandidateProjectionTests(unittest.TestCase):
    def test_profiles_are_reapplied_to_same_causal_activation(self):
        row = _scanner_row(price=1.75)
        general = candidate_snapshot_from_causal_row(row, current_general_2026())
        small = candidate_snapshot_from_causal_row(row, current_small_account_2026())
        self.assertEqual(general.quality, CandidateQuality.REJECT)
        self.assertEqual(small.quality, CandidateQuality.A_QUALITY)
        self.assertEqual(general.timestamp, small.timestamp)
        self.assertEqual(general.top_gainer_rank, small.top_gainer_rank)

    def test_provider_relative_no_news_exception_remains_narrow(self):
        rank_one = candidate_snapshot_from_causal_row(
            _scanner_row(has_provider_news_as_of=False),
            current_general_2026(),
        )
        rank_two = candidate_snapshot_from_causal_row(
            _scanner_row(has_provider_news_as_of=False, top_gainer_rank=2),
            current_general_2026(),
        )
        self.assertEqual(rank_one.quality, CandidateQuality.CONDITIONAL)
        self.assertEqual(rank_two.quality, CandidateQuality.REJECT)

    def test_activation_row_must_be_exact_and_complete(self):
        with self.assertRaisesRegex(ValueError, "first activation"):
            candidate_snapshot_from_causal_row(
                _scanner_row(activation_time="2026-07-10T12:59:00+00:00"),
                current_general_2026(),
            )


class HistoricalCompositionTests(unittest.TestCase):
    def test_separate_historical_snapshot_does_not_weaken_prospective_guard(self):
        account = _historical_account()
        self.assertEqual(account.session_date, SESSION)
        with self.assertRaisesRegex(ValueError, "registered integration panel"):
            AccountSessionSnapshot(
                account_id=account.account_id,
                account_class=account.account_class,
                session_date=account.session_date,
                captured_at=account.captured_at,
                starting_equity=account.starting_equity,
                starting_buying_power=account.starting_buying_power,
                source_id=account.source_id,
                source_content_sha256=account.source_content_sha256,
            )

    def test_unchanged_engine_sizes_and_applies_historical_events(self):
        record = AccountCandidateRuntime(
            activation_id="activation-test",
            strategy_profile_id="current-general-2026",
            candidate_snapshot=_candidate(),
            scanner_record_content_sha256="b" * 64,
            micro_runtime_content_sha256="c" * 64,
            runtime_status="replayed",
            micro_replay=_replay(),
        )
        artifact = integrate_account_session(
            _historical_account(),  # type: ignore[arg-type]
            (record,),
        )
        entry = next(
            event
            for event in artifact["integration_events"]
            if event["event_type"] == "entry_accepted"
        )
        self.assertEqual(entry["quantity"], 75)
        self.assertEqual(
            artifact["ledger_artifact"]["account"]["realized_pnl"],
            -75.0,
        )

    def test_runtime_parser_preserves_frozen_plan_and_outcome(self):
        plan = _plan()
        runtime = {
            "artifact_type": "micro_candidate_runtime_replay",
            "frozen_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
            "retrospective_behavior_labels_loaded": False,
            "symbol": "TEST",
            "candidate_qualified_at": "2026-07-10T13:00:00+00:00",
            "policy_name": "canonical-micro-current-2026",
            "trigger_mode": "chart_price",
            "entry_latency_ms": 0.0,
            "plan_count": 1,
            "filled_count": 1,
            "steps": [
                {
                    "evaluated_at": "2026-07-10T13:00:00+00:00",
                    "pullback_number": 1,
                    "reason": "qualified",
                    "features": None,
                    "plan": {
                        "symbol": plan.symbol,
                        "source_bar_start": plan.source_bar_start.isoformat(),
                        "armed_at": plan.armed_at.isoformat(),
                        "expires_at": plan.expires_at.isoformat(),
                        "breakout_level": plan.breakout_level,
                        "minimum_new_high_price": plan.minimum_new_high_price,
                        "stop_price": plan.stop_price,
                    },
                    "outcome": {
                        "plan": {
                            "symbol": plan.symbol,
                            "source_bar_start": plan.source_bar_start.isoformat(),
                            "armed_at": plan.armed_at.isoformat(),
                            "expires_at": plan.expires_at.isoformat(),
                            "breakout_level": plan.breakout_level,
                            "minimum_new_high_price": plan.minimum_new_high_price,
                            "stop_price": plan.stop_price,
                        },
                        "status": "stopped",
                        "trigger_mode": "chart_price",
                        "entry_latency_ms": 0.0,
                        "trigger_time": "2026-07-10T13:00:11+00:00",
                        "trigger_print_price": 9.99,
                        "fill_time": "2026-07-10T13:00:11+00:00",
                        "fill_price": 10.0,
                        "exit_time": "2026-07-10T13:00:12+00:00",
                        "exit_price": 9.0,
                    },
                }
            ],
        }
        replay = micro_replay_from_runtime(runtime)
        self.assertEqual(replay.plan_count, 1)
        self.assertEqual(replay.filled_count, 1)
        self.assertEqual(
            replay.steps[0].outcome.status,
            MicroExecutionStatus.STOPPED,
        )


if __name__ == "__main__":
    unittest.main()
