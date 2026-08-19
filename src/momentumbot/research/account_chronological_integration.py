"""Label-blind chronological composition of scanner, Micro, and account state.

This research layer consumes already-built account-specific candidate snapshots
and frozen Micro-v0.1 replays.  It materializes the registered paper account,
orders exact-time entry collisions with the frozen scarcity policy, sizes only
whole-share synthetic fills inside the remaining risk/notional envelope, and
applies accepted events to the frozen campaign ledger.

The integration is deliberately not a broker simulator or portfolio backtest.
It has no retrospective label inputs, no cross-account dispatch rule, no depth
or locate model, and no invented exit for a Micro outcome that remains open.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Mapping
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.micro_execution import MicroExecutionOutcome
from momentumbot.micro_execution import MicroExecutionStatus, MicroTriggerMode
from momentumbot.micro_policy import micro_v0_1_policy
from momentumbot.micro_replay import MicroCandidateReplay
from momentumbot.models import CandidateQuality, CandidateSnapshot
from momentumbot.research.account_priority_policy import (
    GENERAL_PROFILE_FINGERPRINT,
    SMALL_PROFILE_FINGERPRINT,
    ScarceCapitalOpportunity,
    canonical_fingerprint as account_policy_fingerprint,
    materialize_account_constraints,
    order_scarce_capital_opportunities,
    paper_account_policy,
    policy_bundle_manifest,
)
from momentumbot.research.campaign_portfolio import (
    AccountClass,
    CampaignPortfolioLedger,
    EntryFill,
    EntryRole,
    ExitFill,
    PlanEmission,
)


SCHEMA_VERSION = 1
CONTRACT_ID = "account-chronological-integration-v0.1"
PANEL_ID = "ross-account-integration-panel-v0.1"
PRIOR_REVIEW_CUTOFF = date(2026, 8, 6)
REGISTRATION_DATE = date(2026, 8, 19)
REGISTERED_DATES = (
    "2026-08-24",
    "2026-08-25",
    "2026-08-26",
    "2026-08-27",
    "2026-08-28",
    "2026-08-31",
    "2026-09-01",
    "2026-09-02",
    "2026-09-03",
    "2026-09-04",
)
MICRO_POLICY_FINGERPRINT = (
    "49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa"
)
LEDGER_CONTRACT_SHA256 = (
    "f2a80f4350e6283e2638702d70515bf03ee6c930e7d52706d09ef5e1d9f419b6"
)
ACCOUNT_POLICY_CONTRACT_SHA256 = (
    "78dd5e3aef9485fc77f07632baec0274dceecb44c8cefd68ab8ea03e7727ceff"
)
ACCOUNT_POLICY_BUNDLE_SHA256 = (
    "df66cfb6637783f69e86379e63428813ce521bd3b648a7ab0131d1c7250cff51"
)
EVENT_ORDER = (
    "timestamp ascending",
    "plan emissions before entry attempts at the same timestamp",
    "same-time entry attempts by paper-account-scarcity-policy-v0.1",
    "exit fills after entry attempts at the same timestamp",
    "stable identifier tie-breakers",
)
SIZING_RULE = (
    "maximum positive whole shares inside remaining buying power, starter, "
    "campaign and total notional, and campaign and total open-risk ceilings"
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_CONTRACT_KEYS = {
    "benchmark_label",
    "human_action",
    "reported_fill",
    "retrospective_label",
    "ross_action",
    "skip_label",
    "trade_outcome",
    "transcript_text",
}


@dataclass(frozen=True, slots=True)
class AccountSessionSnapshot:
    """Hash-bound account values known before the strategy session starts."""

    account_id: str
    account_class: AccountClass
    session_date: date
    captured_at: datetime | pd.Timestamp
    starting_equity: float
    starting_buying_power: float
    source_id: str
    source_content_sha256: str

    def __post_init__(self) -> None:
        if not self.account_id.strip():
            raise ValueError("account_id must be non-empty")
        if not isinstance(self.account_class, AccountClass):
            raise ValueError("account_class must be an AccountClass")
        if not self.source_id.strip():
            raise ValueError("source_id must be non-empty")
        _require_sha256(self.source_content_sha256, "source_content_sha256")
        if not _finite_positive(self.starting_equity):
            raise ValueError("starting_equity must be finite and positive")
        if not _finite_positive(self.starting_buying_power):
            raise ValueError("starting_buying_power must be finite and positive")
        captured = _aware_timestamp(self.captured_at, "captured_at")
        if self.session_date.isoformat() not in REGISTERED_DATES:
            raise ValueError("session_date is not in the registered integration panel")
        if captured.tz_convert("America/New_York").date() != self.session_date:
            raise ValueError("account snapshot must belong to session_date")
        profile = paper_account_policy(self.account_class)
        strategy_start = pd.Timestamp(
            datetime.combine(
                self.session_date,
                _strategy_start(profile.strategy_profile_id),
                ZoneInfo("America/New_York"),
            )
        )
        if captured > strategy_start:
            raise ValueError("account snapshot must be captured by strategy session start")


@dataclass(frozen=True, slots=True)
class AccountCandidateRuntime:
    """One account-specific activation and its optional frozen Micro replay."""

    activation_id: str
    strategy_profile_id: str
    candidate_snapshot: CandidateSnapshot
    scanner_record_content_sha256: str
    micro_runtime_content_sha256: str
    runtime_status: str
    micro_replay: MicroCandidateReplay | None

    def __post_init__(self) -> None:
        if not self.activation_id.strip():
            raise ValueError("activation_id must be non-empty")
        if not self.strategy_profile_id.strip():
            raise ValueError("strategy_profile_id must be non-empty")
        if not self.runtime_status.strip():
            raise ValueError("runtime_status must be non-empty")
        _require_sha256(
            self.scanner_record_content_sha256,
            "scanner_record_content_sha256",
        )
        _require_sha256(
            self.micro_runtime_content_sha256,
            "micro_runtime_content_sha256",
        )
        _aware_timestamp(
            self.candidate_snapshot.timestamp,
            "candidate_snapshot.timestamp",
        )
        if self.micro_replay is None:
            if self.runtime_status == "replayed":
                raise ValueError("replayed status requires a Micro replay")
            return
        if self.runtime_status != "replayed":
            raise ValueError("a Micro replay requires replayed status")
        if self.candidate_snapshot.quality is CandidateQuality.REJECT:
            raise ValueError("rejected candidate cannot carry a Micro replay")
        if self.micro_replay.symbol != self.candidate_snapshot.symbol:
            raise ValueError("Micro replay symbol differs from candidate snapshot")
        if self.micro_replay.policy_name != micro_v0_1_policy().setup.name:
            raise ValueError("Micro replay does not use frozen Micro-v0.1 setup")
        if self.micro_replay.trigger_mode is not MicroTriggerMode.CHART_PRICE:
            raise ValueError("Micro replay must use the frozen chart-price trigger mode")
        if self.micro_replay.entry_latency_ms != 0.0:
            raise ValueError("v0.1 integration requires frozen zero-millisecond latency")
        qualified = _aware_timestamp(
            self.micro_replay.candidate_qualified_at,
            "micro_replay.candidate_qualified_at",
        )
        snapshot_at = _aware_timestamp(
            self.candidate_snapshot.timestamp,
            "candidate_snapshot.timestamp",
        )
        if qualified != snapshot_at:
            raise ValueError("candidate activation and Micro qualification must match")


@dataclass(frozen=True, slots=True)
class _PlanRuntimeEvent:
    at: pd.Timestamp
    activation_id: str
    plan_id: str
    symbol: str


@dataclass(frozen=True, slots=True)
class _EntryRuntimeEvent:
    at: pd.Timestamp
    activation_id: str
    plan_id: str
    opportunity_id: str
    fill_id: str
    symbol: str
    candidate_snapshot: CandidateSnapshot
    outcome: MicroExecutionOutcome


@dataclass(frozen=True, slots=True)
class _ExitRuntimeEvent:
    at: pd.Timestamp
    activation_id: str
    entry_fill_id: str
    exit_fill_id: str
    symbol: str
    fill_price: float


def integrate_account_session(
    account: AccountSessionSnapshot,
    candidates: Iterable[AccountCandidateRuntime],
) -> dict[str, object]:
    """Compose one account/session in deterministic causal order.

    Main and small accounts must be invoked separately.  A caller may later
    place the two resulting artifacts beside each other, but this function has
    no authority to decide which account receives attention first.
    """
    _validate_frozen_parent_code()
    policy = paper_account_policy(account.account_class)
    constraints = materialize_account_constraints(
        policy,
        account_id=account.account_id,
        starting_equity=account.starting_equity,
        starting_buying_power=account.starting_buying_power,
    )
    ledger = CampaignPortfolioLedger(account.session_date, constraints)
    records = tuple(candidates)
    _validate_records(account, policy.strategy_profile_id, records)

    plan_events: list[_PlanRuntimeEvent] = []
    entry_events: list[_EntryRuntimeEvent] = []
    exit_events: list[_ExitRuntimeEvent] = []
    for record in records:
        if record.micro_replay is None:
            continue
        for step in record.micro_replay.steps:
            plan = step.plan
            if plan is None:
                continue
            plan_id = _plan_id(record.activation_id, plan)
            armed_at = _aware_timestamp(plan.armed_at, "plan.armed_at")
            plan_events.append(
                _PlanRuntimeEvent(
                    at=armed_at,
                    activation_id=record.activation_id,
                    plan_id=plan_id,
                    symbol=record.candidate_snapshot.symbol,
                )
            )
            outcome = step.outcome
            if outcome is None:
                continue
            _validate_outcome_shape(outcome)
            if outcome.fill_time is None or outcome.fill_price is None:
                continue
            if outcome.plan != plan:
                raise ValueError("Micro outcome plan differs from emitted plan")
            fill_at = _aware_timestamp(outcome.fill_time, "outcome.fill_time")
            if fill_at < armed_at:
                raise ValueError("Micro fill cannot precede plan emission")
            opportunity_id = _stable_id(
                "opportunity",
                record.activation_id,
                plan_id,
                fill_at.isoformat(),
            )
            fill_id = _stable_id("entry", opportunity_id)
            entry_events.append(
                _EntryRuntimeEvent(
                    at=fill_at,
                    activation_id=record.activation_id,
                    plan_id=plan_id,
                    opportunity_id=opportunity_id,
                    fill_id=fill_id,
                    symbol=record.candidate_snapshot.symbol,
                    candidate_snapshot=record.candidate_snapshot,
                    outcome=outcome,
                )
            )
            if outcome.exit_time is not None and outcome.exit_price is not None:
                exit_at = _aware_timestamp(outcome.exit_time, "outcome.exit_time")
                if exit_at < fill_at:
                    raise ValueError("Micro exit cannot precede its fill")
                exit_events.append(
                    _ExitRuntimeEvent(
                        at=exit_at,
                        activation_id=record.activation_id,
                        entry_fill_id=fill_id,
                        exit_fill_id=_stable_id("exit", fill_id, exit_at.isoformat()),
                        symbol=record.candidate_snapshot.symbol,
                        fill_price=float(outcome.exit_price),
                    )
                )
            elif outcome.exit_time is not None or outcome.exit_price is not None:
                raise ValueError("Micro exit time and price must both be present or absent")

    plans_by_time = _group_by_time(plan_events)
    entries_by_time = _group_by_time(entry_events)
    exits_by_time = _group_by_time(exit_events)
    timestamps = sorted(set(plans_by_time) | set(entries_by_time) | set(exits_by_time))
    integration_events: list[dict[str, object]] = []
    accepted_quantities: dict[str, int] = {}

    for at in timestamps:
        for event in sorted(
            plans_by_time.get(at, ()),
            key=lambda item: (item.activation_id, item.plan_id),
        ):
            ledger.record_plan_emission(
                PlanEmission(
                    activation_id=event.activation_id,
                    plan_id=event.plan_id,
                    symbol=event.symbol,
                    emitted_at=event.at,
                )
            )
            integration_events.append(
                {
                    "event_type": "plan_emission",
                    "at": event.at.isoformat(),
                    "activation_id": event.activation_id,
                    "plan_id": event.plan_id,
                    "symbol": event.symbol,
                }
            )

        same_time_entries = entries_by_time.get(at, ())
        opportunity_ids = [event.opportunity_id for event in same_time_entries]
        if len(opportunity_ids) != len(set(opportunity_ids)):
            raise ValueError("entry opportunity IDs must be unique")
        opportunities = {
            event.opportunity_id: event for event in same_time_entries
        }
        ordered = order_scarce_capital_opportunities(
            ScarceCapitalOpportunity(
                opportunity_id=event.opportunity_id,
                account_id=account.account_id,
                account_class=account.account_class,
                candidate_activation_id=event.activation_id,
                plan_id=event.plan_id,
                execution_at=event.at,
                candidate_snapshot=event.candidate_snapshot,
            )
            for event in same_time_entries
        )
        for ordinal, opportunity in enumerate(ordered, start=1):
            event = opportunities[opportunity.opportunity_id]
            role = _expected_role(ledger, event.activation_id)
            quantity = maximum_whole_share_quantity(
                ledger,
                activation_id=event.activation_id,
                fill_price=float(event.outcome.fill_price),
                stop_price=float(event.outcome.plan.stop_price),
                role=role,
            )
            if quantity < 1:
                integration_events.append(
                    {
                        "event_type": "entry_not_submitted",
                        "at": event.at.isoformat(),
                        "same_time_entry_ordinal": ordinal,
                        "opportunity_id": event.opportunity_id,
                        "activation_id": event.activation_id,
                        "plan_id": event.plan_id,
                        "symbol": event.symbol,
                        "role": role.value,
                        "reason": "no_positive_whole_share_capacity",
                    }
                )
                continue
            decision = ledger.apply_entry_fill(
                EntryFill(
                    fill_id=event.fill_id,
                    activation_id=event.activation_id,
                    plan_id=event.plan_id,
                    symbol=event.symbol,
                    filled_at=event.at,
                    quantity=quantity,
                    reference_price=event.outcome.planned_trigger_price,
                    fill_price=float(event.outcome.fill_price),
                    stop_price=float(event.outcome.plan.stop_price),
                    role=role,
                    execution_approved=True,
                )
            )
            if decision.accepted:
                accepted_quantities[event.fill_id] = quantity
            integration_events.append(
                {
                    "event_type": (
                        "entry_accepted" if decision.accepted else "entry_rejected"
                    ),
                    "at": event.at.isoformat(),
                    "same_time_entry_ordinal": ordinal,
                    "opportunity_id": event.opportunity_id,
                    "activation_id": event.activation_id,
                    "plan_id": event.plan_id,
                    "fill_id": event.fill_id,
                    "symbol": event.symbol,
                    "role": role.value,
                    "quantity": quantity,
                    "reference_price": event.outcome.planned_trigger_price,
                    "fill_price": float(event.outcome.fill_price),
                    "stop_price": float(event.outcome.plan.stop_price),
                    "reasons": list(decision.reasons),
                }
            )

        for event in sorted(
            exits_by_time.get(at, ()),
            key=lambda item: (item.activation_id, item.exit_fill_id),
        ):
            quantity = accepted_quantities.get(event.entry_fill_id)
            if quantity is None:
                integration_events.append(
                    {
                        "event_type": "exit_not_applied",
                        "at": event.at.isoformat(),
                        "activation_id": event.activation_id,
                        "entry_fill_id": event.entry_fill_id,
                        "exit_fill_id": event.exit_fill_id,
                        "symbol": event.symbol,
                        "reason": "corresponding_entry_not_accepted",
                    }
                )
                continue
            decision = ledger.apply_exit_fill(
                ExitFill(
                    fill_id=event.exit_fill_id,
                    activation_id=event.activation_id,
                    symbol=event.symbol,
                    filled_at=event.at,
                    quantity=quantity,
                    fill_price=event.fill_price,
                )
            )
            integration_events.append(
                {
                    "event_type": (
                        "exit_accepted" if decision.accepted else "exit_rejected"
                    ),
                    "at": event.at.isoformat(),
                    "activation_id": event.activation_id,
                    "entry_fill_id": event.entry_fill_id,
                    "exit_fill_id": event.exit_fill_id,
                    "symbol": event.symbol,
                    "quantity": quantity,
                    "fill_price": event.fill_price,
                    "realized_pnl": decision.realized_pnl,
                    "reasons": list(decision.reasons),
                }
            )

    source_records = [
        {
            "activation_id": record.activation_id,
            "symbol": record.candidate_snapshot.symbol,
            "candidate_snapshot_at": _aware_timestamp(
                record.candidate_snapshot.timestamp,
                "candidate_snapshot.timestamp",
            ).isoformat(),
            "candidate_quality": record.candidate_snapshot.quality.value,
            "strategy_profile_id": record.strategy_profile_id,
            "runtime_status": record.runtime_status,
            "scanner_record_content_sha256": record.scanner_record_content_sha256,
            "micro_runtime_content_sha256": record.micro_runtime_content_sha256,
        }
        for record in sorted(records, key=lambda item: item.activation_id)
    ]
    ledger_artifact = ledger.runtime_artifact()
    open_positions = int(ledger_artifact["account"]["open_campaign_count"])
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "panel_id": PANEL_ID,
        "artifact_type": "account_chronological_integration_shadow",
        "session_date": account.session_date.isoformat(),
        "account": {
            "account_id": account.account_id,
            "account_class": account.account_class.value,
            "policy_id": policy.policy_id,
            "strategy_profile_id": policy.strategy_profile_id,
            "snapshot_captured_at": _aware_timestamp(
                account.captured_at,
                "captured_at",
            ).isoformat(),
            "snapshot_source_id": account.source_id,
            "snapshot_source_content_sha256": account.source_content_sha256,
            "starting_equity": account.starting_equity,
            "starting_buying_power": account.starting_buying_power,
        },
        "frozen_parents": _frozen_parents(),
        "event_order": list(EVENT_ORDER),
        "sizing_rule": SIZING_RULE,
        "candidate_records": source_records,
        "integration_events": integration_events,
        "ledger_artifact": ledger_artifact,
        "knowledge_policy": {
            "runtime_market_execution_and_predecision_account_state_only": True,
            "uses_raw_transcripts": False,
            "uses_ross_actions_or_fills": False,
            "uses_retrospective_labels": False,
            "uses_later_price_outcomes": False,
            "uses_semantic_ai": False,
        },
        "authority_boundary": {
            "research_sizing_only": True,
            "broker_order_authority": False,
            "cross_account_dispatch_authority": False,
            "liquidity_or_locate_verified": False,
            "unmodeled_open_positions": open_positions,
            "portfolio_backtest_eligible": False,
            "policy_promotion_eligible": False,
            "ross_replication_claim_eligible": False,
        },
    }
    return _freeze(payload)


def maximum_whole_share_quantity(
    ledger: CampaignPortfolioLedger,
    *,
    activation_id: str,
    fill_price: float,
    stop_price: float,
    role: EntryRole,
) -> int:
    """Return the full remaining paper-safe capacity as whole shares."""
    if not _finite_positive(fill_price):
        raise ValueError("fill_price must be finite and positive")
    if not _finite_positive(stop_price) or stop_price >= fill_price:
        raise ValueError("stop_price must be positive and below fill_price")
    if not isinstance(role, EntryRole):
        raise ValueError("role must be an EntryRole")
    campaign = ledger.campaigns.get(activation_id)
    if campaign is None:
        raise ValueError("quantity sizing requires an emitted campaign")
    constraints = ledger.constraints
    risk_per_share = fill_price - stop_price
    capacities = [
        ledger.remaining_buying_power / fill_price,
        (constraints.max_total_open_notional - ledger.total_open_notional) / fill_price,
        (constraints.max_campaign_open_notional - campaign.open_notional) / fill_price,
        (constraints.max_total_open_risk - ledger.total_open_risk) / risk_per_share,
        (constraints.max_campaign_open_risk - campaign.open_risk) / risk_per_share,
    ]
    if role is EntryRole.STARTER:
        capacities.append(
            (constraints.starter_max_notional - campaign.open_notional) / fill_price
        )
    capacity = min(capacities)
    if not math.isfinite(capacity) or capacity < 1:
        return 0
    return max(0, math.floor(capacity + 1e-12))


def validate_account_integration_contract(payload: Mapping[str, object]) -> None:
    expected_root = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "panel_id": PANEL_ID,
        "artifact_type": "chronological_account_integration_registration",
        "registration_status": "registered_unrun_label_blind",
        "runtime_strategy_effect": "shadow_only",
        "retrospective_review_started": False,
        "source_inventory_started": False,
        "dates_may_be_replaced": False,
        "portfolio_backtest_eligible": False,
        "policy_promotion_eligible": False,
        "ross_replication_claim_eligible": False,
    }
    for field, expected in expected_root.items():
        if payload.get(field) != expected:
            raise ValueError(f"{field} must be {expected!r}")
    forbidden = _walk_keys(payload) & _FORBIDDEN_CONTRACT_KEYS
    if forbidden:
        raise ValueError(f"integration contract contains retrospective keys: {sorted(forbidden)}")

    if payload.get("frozen_parents") != _frozen_parents():
        raise ValueError("frozen_parents differ from the exact registered parents")
    panel = _mapping(payload, "sampling_contract")
    if panel.get("prior_review_cutoff") != PRIOR_REVIEW_CUTOFF.isoformat():
        raise ValueError("sampling_contract.prior_review_cutoff changed")
    if panel.get("registration_date") != REGISTRATION_DATE.isoformat():
        raise ValueError("sampling_contract.registration_date changed")
    if panel.get("selection_rule") != (
        "first_ten_scheduled_us_equity_sessions_beginning_first_monday_after_registration"
    ):
        raise ValueError("sampling selection rule changed")
    if panel.get("registered_dates") != list(REGISTERED_DATES):
        raise ValueError("registered_dates differ from the frozen integration panel")
    guards = {
        "date_selection_uses_source_inventory": False,
        "date_selection_uses_symbols": False,
        "date_selection_uses_retrospective_behavior": False,
        "date_selection_uses_trade_results": False,
        "missing_date_may_be_replaced": False,
        "union_of_main_and_small_market_candidates_retained": True,
        "top_n_filter_applied": False,
    }
    for field, expected in guards.items():
        if panel.get(field) is not expected:
            raise ValueError(f"sampling_contract.{field} must be {expected}")
    sessions = tuple(date.fromisoformat(value) for value in REGISTERED_DATES)
    if any(value <= PRIOR_REVIEW_CUTOFF for value in sessions):
        raise ValueError("registered sessions must follow the prior review cutoff")
    if any(value <= REGISTRATION_DATE for value in sessions):
        raise ValueError("registered sessions must be prospective at registration")
    if any(value.weekday() >= 5 for value in sessions):
        raise ValueError("registered sessions must be weekdays")

    account_input = _mapping(payload, "account_snapshot_contract")
    expected_account = {
        "fixed_historical_balance_invented": False,
        "source_must_be_hash_bound": True,
        "captured_by_strategy_session_start": True,
        "main_and_small_accounts_processed_separately": True,
        "missing_snapshot_behavior": "fail_closed_no_account_runtime",
    }
    for field, expected in expected_account.items():
        if account_input.get(field) != expected:
            raise ValueError(f"account_snapshot_contract.{field} must be {expected!r}")

    sizing = _mapping(payload, "sizing_contract")
    if sizing.get("rule") != SIZING_RULE:
        raise ValueError("sizing_contract.rule changed")
    expected_sizing = {
        "fractional_shares_allowed": False,
        "uses_full_remaining_registered_capacity": True,
        "uses_observed_trade_size_as_liquidity": False,
        "uses_level2_or_queue_model": False,
        "quantity_zero_behavior": "record_not_submitted",
        "classification": "deterministic_project_research_sizing_not_ross_behavior",
    }
    for field, expected in expected_sizing.items():
        if sizing.get(field) != expected:
            raise ValueError(f"sizing_contract.{field} must be {expected!r}")

    ordering = _mapping(payload, "chronology_contract")
    if ordering.get("event_order") != list(EVENT_ORDER):
        raise ValueError("chronology_contract.event_order changed")
    if ordering.get("activation_snapshot_used_for_same_time_rank") is not True:
        raise ValueError("same-time rank must use the causal activation snapshot")
    if ordering.get("same_time_exit_recycles_capacity") is not False:
        raise ValueError("same-time exits cannot recycle capacity for entries")
    if ordering.get("cross_account_priority") != "unresolved_fail_closed":
        raise ValueError("cross-account priority must remain unresolved")

    knowledge = _mapping(payload, "knowledge_policy")
    expected_knowledge = {
        "runtime_inputs_available_by_event_time": True,
        "raw_transcripts_allowed_at_runtime": False,
        "retrospective_actions_labels_or_fills_allowed_at_runtime": False,
        "later_prices_or_outcomes_allowed_at_runtime": False,
        "semantic_ai_used": False,
        "labels_opened_only_after_runtime_hash_freeze": True,
    }
    for field, expected in expected_knowledge.items():
        if knowledge.get(field) is not expected:
            raise ValueError(f"knowledge_policy.{field} must be {expected}")

    status = _mapping(payload, "execution_status")
    if status != {
        "market_runtime": "not_started",
        "micro_runtime": "not_started",
        "account_runtime": "not_started",
        "runtime_artifact_sha256": None,
        "retrospective_evaluation": "not_started",
    }:
        raise ValueError("execution_status must remain unrun")


def load_account_integration_contract(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("account integration contract root must be an object")
    validate_account_integration_contract(payload)
    return payload


def canonical_fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_records(
    account: AccountSessionSnapshot,
    strategy_profile_id: str,
    records: tuple[AccountCandidateRuntime, ...],
) -> None:
    activation_ids = [record.activation_id for record in records]
    if len(activation_ids) != len(set(activation_ids)):
        raise ValueError("activation_id values must be unique per account session")
    for record in records:
        if record.strategy_profile_id != strategy_profile_id:
            raise ValueError("candidate strategy profile differs from account policy")
        snapshot_at = _aware_timestamp(
            record.candidate_snapshot.timestamp,
            "candidate_snapshot.timestamp",
        )
        if snapshot_at.tz_convert("America/New_York").date() != account.session_date:
            raise ValueError("candidate snapshot must belong to account session_date")
        if record.micro_replay is None:
            continue
        for step in record.micro_replay.steps:
            evaluated = _aware_timestamp(step.evaluated_at, "step.evaluated_at")
            if evaluated < snapshot_at:
                raise ValueError("Micro step cannot precede candidate activation")


def _validate_outcome_shape(outcome: MicroExecutionOutcome) -> None:
    fill_fields = (outcome.fill_time, outcome.fill_price)
    if (fill_fields[0] is None) != (fill_fields[1] is None):
        raise ValueError("Micro fill time and price must both be present or absent")
    exit_fields = (outcome.exit_time, outcome.exit_price)
    if (exit_fields[0] is None) != (exit_fields[1] is None):
        raise ValueError("Micro exit time and price must both be present or absent")
    filled_statuses = {
        MicroExecutionStatus.FILLED_OPEN,
        MicroExecutionStatus.STOPPED,
        MicroExecutionStatus.TARGET_HIT,
    }
    if outcome.status in filled_statuses and outcome.fill_time is None:
        raise ValueError("filled Micro status requires a fill")
    if outcome.status not in filled_statuses and outcome.fill_time is not None:
        raise ValueError("unfilled Micro status cannot carry a fill")
    if outcome.status is MicroExecutionStatus.FILLED_OPEN and outcome.exit_time is not None:
        raise ValueError("filled-open Micro status cannot carry an exit")
    if outcome.status in {
        MicroExecutionStatus.STOPPED,
        MicroExecutionStatus.TARGET_HIT,
    } and outcome.exit_time is None:
        raise ValueError("closed Micro status requires an exit")


def _expected_role(
    ledger: CampaignPortfolioLedger,
    activation_id: str,
) -> EntryRole:
    campaign = ledger.campaigns.get(activation_id)
    if campaign is None:
        raise ValueError("entry opportunity requires an emitted campaign")
    if campaign.entry_fill_count == 0:
        return EntryRole.STARTER
    if campaign.quantity > 0:
        return EntryRole.ADD
    return EntryRole.REENTRY


def _plan_id(activation_id: str, plan: object) -> str:
    fields = {
        "activation_id": activation_id,
        "symbol": str(getattr(plan, "symbol")),
        "source_bar_start": _aware_timestamp(
            getattr(plan, "source_bar_start"),
            "plan.source_bar_start",
        ).isoformat(),
        "armed_at": _aware_timestamp(getattr(plan, "armed_at"), "plan.armed_at").isoformat(),
        "expires_at": _aware_timestamp(
            getattr(plan, "expires_at"),
            "plan.expires_at",
        ).isoformat(),
        "breakout_level": float(getattr(plan, "breakout_level")),
        "minimum_new_high_price": float(getattr(plan, "minimum_new_high_price")),
        "stop_price": float(getattr(plan, "stop_price")),
    }
    return f"plan-{canonical_fingerprint(fields)}"


def _stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}-{canonical_fingerprint(list(parts))}"


def _group_by_time(events: Iterable[object]) -> dict[pd.Timestamp, tuple[object, ...]]:
    grouped: dict[pd.Timestamp, list[object]] = {}
    for event in events:
        grouped.setdefault(getattr(event, "at"), []).append(event)
    return {key: tuple(value) for key, value in grouped.items()}


def _strategy_start(profile_id: str):
    if profile_id == "current-general-2026":
        from momentumbot.models import current_general_2026

        return current_general_2026().session_start
    if profile_id == "current-small-account-2026":
        from momentumbot.models import current_small_account_2026

        return current_small_account_2026().session_start
    raise ValueError("unknown strategy profile")


def _frozen_parents() -> dict[str, object]:
    return {
        "micro_policy_id": "micro-v0.1",
        "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
        "campaign_ledger_contract_content_sha256": LEDGER_CONTRACT_SHA256,
        "account_policy_contract_content_sha256": ACCOUNT_POLICY_CONTRACT_SHA256,
        "account_policy_bundle_sha256": ACCOUNT_POLICY_BUNDLE_SHA256,
        "general_strategy_profile_fingerprint": GENERAL_PROFILE_FINGERPRINT,
        "small_strategy_profile_fingerprint": SMALL_PROFILE_FINGERPRINT,
    }


def _validate_frozen_parent_code() -> None:
    micro = micro_v0_1_policy()
    if micro.fingerprint != MICRO_POLICY_FINGERPRINT:
        raise RuntimeError("frozen Micro-v0.1 fingerprint changed")
    bundle = account_policy_fingerprint(policy_bundle_manifest())
    if bundle != ACCOUNT_POLICY_BUNDLE_SHA256:
        raise RuntimeError("frozen account policy bundle fingerprint changed")


def _freeze(payload: dict[str, object]) -> dict[str, object]:
    result = dict(payload)
    result["content_sha256"] = canonical_fingerprint(payload)
    return result


def _mapping(payload: Mapping[str, object], field: str) -> Mapping[str, object]:
    value = payload.get(field)
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _walk_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_walk_keys(child))
    return keys


def _aware_timestamp(value: datetime | pd.Timestamp, field: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return timestamp


def _require_sha256(value: str, field: str) -> None:
    if not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _finite_positive(value: float) -> bool:
    return bool(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and value > 0
    )
