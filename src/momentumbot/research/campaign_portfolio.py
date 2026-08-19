"""Deterministic campaign, portfolio, and account-state research ledger.

This module sits *after* candidate qualification, Micro-v0.1 plan emission, and
execution modeling.  It does not discover candidates, choose between
opportunities, size an order, or synthesize a fill.  Instead it consumes an
explicitly ordered stream of already-authorized plan and fill events, groups
repeated plan emissions by candidate activation, and verifies that the supplied
events are feasible for one account.

The ledger is deliberately research-only.  Main and small accounts require
separate instances and caller-supplied registered constraints.  There are no
Ross-derived default account balances or fitted limits in this module.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from numbers import Real
from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd


SCHEMA_VERSION = 1
CONTRACT_ID = "campaign-portfolio-account-state-v0.1"


class AccountClass(str, Enum):
    MAIN = "main"
    SMALL = "small"


class EntryRole(str, Enum):
    STARTER = "starter"
    ADD = "add"
    REENTRY = "reentry"


@dataclass(frozen=True, slots=True)
class AccountConstraints:
    """Explicit deterministic limits for one research account.

    Values must come from a separately registered policy or test fixture.  The
    campaign contract intentionally supplies no main- or small-account values.
    """

    account_id: str
    policy_id: str
    account_class: AccountClass
    starting_equity: float
    starting_buying_power: float
    max_open_positions: int
    max_total_open_notional: float
    max_campaign_open_notional: float
    max_total_open_risk: float
    max_campaign_open_risk: float
    max_entries_per_campaign: int
    starter_max_notional: float
    max_daily_loss_dollars: float
    giveback_fraction: float
    allow_reentry: bool
    first_session_entry_must_be_starter: bool = True
    max_entry_slippage_bps: float | None = None

    def __post_init__(self) -> None:
        if not self.account_id.strip():
            raise ValueError("account_id must be non-empty")
        if not self.policy_id.strip():
            raise ValueError("policy_id must be non-empty")
        if not isinstance(self.account_class, AccountClass):
            raise ValueError("account_class must be an AccountClass")
        positive = {
            "starting_equity": self.starting_equity,
            "starting_buying_power": self.starting_buying_power,
            "max_total_open_notional": self.max_total_open_notional,
            "max_campaign_open_notional": self.max_campaign_open_notional,
            "max_total_open_risk": self.max_total_open_risk,
            "max_campaign_open_risk": self.max_campaign_open_risk,
            "starter_max_notional": self.starter_max_notional,
            "max_daily_loss_dollars": self.max_daily_loss_dollars,
        }
        for name, value in positive.items():
            if not _finite_positive(value):
                raise ValueError(f"{name} must be finite and positive")
        if self.max_open_positions < 1:
            raise ValueError("max_open_positions must be positive")
        if self.max_entries_per_campaign < 1:
            raise ValueError("max_entries_per_campaign must be positive")
        if self.max_campaign_open_notional > self.max_total_open_notional:
            raise ValueError("campaign notional cannot exceed total open notional")
        if self.max_campaign_open_risk > self.max_total_open_risk:
            raise ValueError("campaign risk cannot exceed total open risk")
        if not 0 < self.giveback_fraction <= 1:
            raise ValueError("giveback_fraction must be in (0, 1]")
        if self.max_entry_slippage_bps is not None:
            if not _finite_nonnegative(self.max_entry_slippage_bps):
                raise ValueError("max_entry_slippage_bps must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class PlanEmission:
    activation_id: str
    plan_id: str
    symbol: str
    emitted_at: pd.Timestamp

    def __post_init__(self) -> None:
        _require_identifiers(
            activation_id=self.activation_id,
            plan_id=self.plan_id,
            symbol=self.symbol,
        )
        _aware_timestamp(self.emitted_at, "emitted_at")


@dataclass(frozen=True, slots=True)
class EntryFill:
    fill_id: str
    activation_id: str
    plan_id: str
    symbol: str
    filled_at: pd.Timestamp
    quantity: int
    reference_price: float
    fill_price: float
    stop_price: float
    role: EntryRole
    execution_approved: bool

    def __post_init__(self) -> None:
        _require_identifiers(
            fill_id=self.fill_id,
            activation_id=self.activation_id,
            plan_id=self.plan_id,
            symbol=self.symbol,
        )
        _aware_timestamp(self.filled_at, "filled_at")
        if not isinstance(self.role, EntryRole):
            raise ValueError("role must be an EntryRole")
        if not isinstance(self.execution_approved, bool):
            raise ValueError("execution_approved must be boolean")


@dataclass(frozen=True, slots=True)
class ExitFill:
    fill_id: str
    activation_id: str
    symbol: str
    filled_at: pd.Timestamp
    quantity: int
    fill_price: float

    def __post_init__(self) -> None:
        _require_identifiers(
            fill_id=self.fill_id,
            activation_id=self.activation_id,
            symbol=self.symbol,
        )
        _aware_timestamp(self.filled_at, "filled_at")


@dataclass(frozen=True, slots=True)
class FeasibilityDecision:
    accepted: bool
    campaign_id: str
    reasons: tuple[str, ...]
    remaining_buying_power_before: float
    remaining_buying_power_after: float
    observed_slippage_bps: float | None = None
    realized_pnl: float | None = None


@dataclass(slots=True)
class _OpenLot:
    fill_id: str
    filled_at: pd.Timestamp
    fill_price: float
    stop_price: float
    remaining_quantity: int

    @property
    def notional(self) -> float:
        return self.fill_price * self.remaining_quantity

    @property
    def open_risk(self) -> float:
        return (self.fill_price - self.stop_price) * self.remaining_quantity


@dataclass(slots=True)
class CampaignState:
    campaign_id: str
    activation_id: str
    symbol: str
    plan_ids: list[str] = field(default_factory=list)
    lots: list[_OpenLot] = field(default_factory=list)
    entry_fill_count: int = 0
    reentry_count: int = 0
    realized_pnl: float = 0.0
    terminal: bool = False
    terminal_reason: str | None = None

    @property
    def quantity(self) -> int:
        return sum(lot.remaining_quantity for lot in self.lots)

    @property
    def open_notional(self) -> float:
        return sum(lot.notional for lot in self.lots)

    @property
    def open_risk(self) -> float:
        return sum(lot.open_risk for lot in self.lots)

    @property
    def average_entry_price(self) -> float | None:
        if self.quantity == 0:
            return None
        return self.open_notional / self.quantity

    @property
    def status(self) -> str:
        if self.terminal:
            return "terminal"
        if self.quantity:
            return "open"
        if self.entry_fill_count:
            return "flat"
        return "watching"


class CampaignPortfolioLedger:
    """Pure deterministic reducer for one account and one trading session."""

    def __init__(
        self,
        session_date: date,
        constraints: AccountConstraints,
        *,
        market_timezone: str = "America/New_York",
    ) -> None:
        self.session_date = session_date
        self.constraints = constraints
        self.market_timezone = market_timezone
        try:
            pd.Timestamp("2026-01-01", tz=market_timezone)
        except Exception as exc:  # pragma: no cover - pandas owns timezone parsing
            raise ValueError("market_timezone must be recognized") from exc
        self.remaining_buying_power = constraints.starting_buying_power
        self.realized_pnl = 0.0
        self.high_water_pnl = 0.0
        self.locked = False
        self.lock_reason: str | None = None
        self.flatten_required = False
        self.campaigns: dict[str, CampaignState] = {}
        self.halted_symbols: set[str] = set()
        self.events: list[dict[str, object]] = []
        self._seen_fill_ids: set[str] = set()
        self._last_event_at: pd.Timestamp | None = None
        self._session_entry_fill_count = 0

    @property
    def open_campaign_count(self) -> int:
        return sum(campaign.quantity > 0 for campaign in self.campaigns.values())

    @property
    def total_open_notional(self) -> float:
        return sum(campaign.open_notional for campaign in self.campaigns.values())

    @property
    def total_open_risk(self) -> float:
        return sum(campaign.open_risk for campaign in self.campaigns.values())

    def record_plan_emission(self, emission: PlanEmission) -> CampaignState:
        at = self._validate_event_time(emission.emitted_at)
        campaign = self.campaigns.get(emission.activation_id)
        if campaign is None:
            campaign = CampaignState(
                campaign_id=campaign_id(
                    session_date=self.session_date,
                    account_id=self.constraints.account_id,
                    policy_id=self.constraints.policy_id,
                    account_class=self.constraints.account_class,
                    activation_id=emission.activation_id,
                    symbol=emission.symbol,
                ),
                activation_id=emission.activation_id,
                symbol=emission.symbol,
            )
            self.campaigns[emission.activation_id] = campaign
        elif campaign.symbol != emission.symbol:
            raise ValueError("one activation_id cannot identify multiple symbols")
        if emission.plan_id in campaign.plan_ids:
            raise ValueError("plan_id must be unique within a campaign")
        self._commit_event_time(at)
        campaign.plan_ids.append(emission.plan_id)
        self._append_event(
            "plan_emission",
            at,
            campaign,
            plan_id=emission.plan_id,
        )
        return campaign

    def apply_entry_fill(self, fill: EntryFill) -> FeasibilityDecision:
        at = self._validate_event_time(fill.filled_at)
        campaign = self._campaign(fill.activation_id, fill.symbol)
        self._require_new_fill_id(fill.fill_id)
        self._commit_event_time(at)
        self._seen_fill_ids.add(fill.fill_id)
        before = self.remaining_buying_power
        reasons: list[str] = []

        if fill.plan_id not in campaign.plan_ids:
            reasons.append("unknown_plan")
        if self.locked:
            reasons.append("account_locked")
        if campaign.terminal:
            reasons.append("campaign_terminal")
        if fill.symbol in self.halted_symbols:
            reasons.append("symbol_halted")
        if not fill.execution_approved:
            reasons.append("execution_not_approved")
        valid_quantity = _valid_quantity(fill.quantity)
        valid_reference_price = _finite_positive(fill.reference_price)
        valid_fill_price = _finite_positive(fill.fill_price)
        valid_stop_price = (
            _finite_positive(fill.stop_price)
            and valid_fill_price
            and fill.stop_price < fill.fill_price
        )
        if not valid_quantity:
            reasons.append("invalid_quantity")
        if not valid_reference_price:
            reasons.append("invalid_reference_price")
        if not valid_fill_price:
            reasons.append("invalid_fill_price")
        if not valid_stop_price:
            reasons.append("invalid_stop_price")

        expected_role = self._expected_role(campaign)
        if fill.role is not expected_role:
            reasons.append(f"entry_role_must_be_{expected_role.value}")
        if (
            self._session_entry_fill_count == 0
            and self.constraints.first_session_entry_must_be_starter
            and fill.role is not EntryRole.STARTER
        ):
            reasons.append("first_session_entry_must_be_starter")
        if fill.role is EntryRole.REENTRY and not self.constraints.allow_reentry:
            reasons.append("reentry_disabled")
        if campaign.entry_fill_count >= self.constraints.max_entries_per_campaign:
            reasons.append("campaign_entry_limit")
        if (
            fill.role is EntryRole.ADD
            and campaign.average_entry_price is not None
            and valid_fill_price
            and fill.fill_price < campaign.average_entry_price
        ):
            reasons.append("averaging_down_prohibited")

        quantity = fill.quantity if valid_quantity else 0
        fill_price = float(fill.fill_price) if valid_fill_price else 0.0
        stop_price = float(fill.stop_price) if valid_stop_price else fill_price
        notional = quantity * fill_price
        risk = quantity * (fill_price - stop_price)
        slippage_bps = _entry_slippage_bps(fill.reference_price, fill.fill_price)
        if fill.role is EntryRole.STARTER and notional > self.constraints.starter_max_notional:
            reasons.append("starter_notional_limit")
        if (
            self.constraints.max_entry_slippage_bps is not None
            and slippage_bps is not None
            and slippage_bps > self.constraints.max_entry_slippage_bps
        ):
            reasons.append("entry_slippage_limit")
        if notional > self.remaining_buying_power:
            reasons.append("insufficient_buying_power")
        if self.total_open_notional + notional > self.constraints.max_total_open_notional:
            reasons.append("total_open_notional_limit")
        if campaign.open_notional + notional > self.constraints.max_campaign_open_notional:
            reasons.append("campaign_open_notional_limit")
        if risk > 0 and self.total_open_risk + risk > self.constraints.max_total_open_risk:
            reasons.append("total_open_risk_limit")
        if risk > 0 and campaign.open_risk + risk > self.constraints.max_campaign_open_risk:
            reasons.append("campaign_open_risk_limit")
        if campaign.quantity == 0 and self.open_campaign_count >= self.constraints.max_open_positions:
            reasons.append("open_position_limit")

        reasons = list(dict.fromkeys(reasons))
        if reasons:
            self._append_event(
                "entry_rejected",
                at,
                campaign,
                fill_id=fill.fill_id,
                plan_id=fill.plan_id,
                role=fill.role.value,
                reasons=reasons,
            )
            return FeasibilityDecision(
                accepted=False,
                campaign_id=campaign.campaign_id,
                reasons=tuple(reasons),
                remaining_buying_power_before=before,
                remaining_buying_power_after=before,
                observed_slippage_bps=slippage_bps,
            )

        campaign.lots.append(
            _OpenLot(
                fill_id=fill.fill_id,
                filled_at=at,
                fill_price=fill.fill_price,
                stop_price=fill.stop_price,
                remaining_quantity=fill.quantity,
            )
        )
        campaign.entry_fill_count += 1
        if fill.role is EntryRole.REENTRY:
            campaign.reentry_count += 1
        self._session_entry_fill_count += 1
        self.remaining_buying_power -= notional
        self._append_event(
            "entry_accepted",
            at,
            campaign,
            fill_id=fill.fill_id,
            plan_id=fill.plan_id,
            role=fill.role.value,
            quantity=fill.quantity,
            fill_price=fill.fill_price,
            stop_price=fill.stop_price,
            observed_slippage_bps=slippage_bps,
        )
        return FeasibilityDecision(
            accepted=True,
            campaign_id=campaign.campaign_id,
            reasons=(),
            remaining_buying_power_before=before,
            remaining_buying_power_after=self.remaining_buying_power,
            observed_slippage_bps=slippage_bps,
        )

    def apply_exit_fill(self, fill: ExitFill) -> FeasibilityDecision:
        at = self._validate_event_time(fill.filled_at)
        campaign = self._campaign(fill.activation_id, fill.symbol)
        self._require_new_fill_id(fill.fill_id)
        self._commit_event_time(at)
        self._seen_fill_ids.add(fill.fill_id)
        before = self.remaining_buying_power
        reasons: list[str] = []
        if fill.symbol in self.halted_symbols:
            reasons.append("symbol_halted")
        valid_quantity = _valid_quantity(fill.quantity)
        valid_fill_price = _finite_positive(fill.fill_price)
        if not valid_quantity:
            reasons.append("invalid_quantity")
        if not valid_fill_price:
            reasons.append("invalid_fill_price")
        if valid_quantity and fill.quantity > campaign.quantity:
            reasons.append("exit_exceeds_position")
        if reasons:
            self._append_event(
                "exit_rejected",
                at,
                campaign,
                fill_id=fill.fill_id,
                reasons=reasons,
            )
            return FeasibilityDecision(
                accepted=False,
                campaign_id=campaign.campaign_id,
                reasons=tuple(reasons),
                remaining_buying_power_before=before,
                remaining_buying_power_after=before,
            )

        remaining = fill.quantity
        realized = 0.0
        for lot in campaign.lots:
            if remaining == 0:
                break
            released = min(remaining, lot.remaining_quantity)
            realized += (fill.fill_price - lot.fill_price) * released
            lot.remaining_quantity -= released
            remaining -= released
        campaign.lots = [lot for lot in campaign.lots if lot.remaining_quantity]
        campaign.realized_pnl += realized
        self.realized_pnl += realized
        self.high_water_pnl = max(self.high_water_pnl, self.realized_pnl)
        self.remaining_buying_power += fill.fill_price * fill.quantity
        self._append_event(
            "exit_accepted",
            at,
            campaign,
            fill_id=fill.fill_id,
            quantity=fill.quantity,
            fill_price=fill.fill_price,
            realized_pnl=realized,
        )
        self._apply_session_guards(at)
        self.flatten_required = self.locked and self.open_campaign_count > 0
        return FeasibilityDecision(
            accepted=True,
            campaign_id=campaign.campaign_id,
            reasons=(),
            remaining_buying_power_before=before,
            remaining_buying_power_after=self.remaining_buying_power,
            realized_pnl=realized,
        )

    def set_halt(self, symbol: str, halted: bool, at: pd.Timestamp) -> None:
        if not symbol.strip():
            raise ValueError("symbol must be non-empty")
        if not isinstance(halted, bool):
            raise ValueError("halted must be boolean")
        timestamp = self._validate_event_time(at)
        self._commit_event_time(timestamp)
        if halted:
            self.halted_symbols.add(symbol)
        else:
            self.halted_symbols.discard(symbol)
        self.events.append(
            {
                "sequence": len(self.events) + 1,
                "event_type": "halt_started" if halted else "halt_ended",
                "at": timestamp.isoformat(),
                "symbol": symbol,
            }
        )

    def lock_account(self, reason: str, at: pd.Timestamp) -> None:
        if not reason.strip():
            raise ValueError("lock reason must be non-empty")
        timestamp = self._validate_event_time(at)
        self._commit_event_time(timestamp)
        self._lock(reason)
        self.flatten_required = self.open_campaign_count > 0
        self.events.append(
            {
                "sequence": len(self.events) + 1,
                "event_type": "account_locked",
                "at": timestamp.isoformat(),
                "reason": self.lock_reason,
                "flatten_required": self.flatten_required,
            }
        )

    def close_campaign(self, activation_id: str, reason: str, at: pd.Timestamp) -> None:
        if not reason.strip():
            raise ValueError("campaign close reason must be non-empty")
        timestamp = self._validate_event_time(at)
        campaign = self._campaign(activation_id)
        if campaign.quantity:
            raise ValueError("an open campaign cannot be closed before its position is flat")
        if campaign.terminal:
            raise ValueError("campaign is already terminal")
        self._commit_event_time(timestamp)
        campaign.terminal = True
        campaign.terminal_reason = campaign.terminal_reason or reason
        self._append_event("campaign_closed", timestamp, campaign, reason=reason)

    def simultaneous_opportunity_groups(self) -> tuple[dict[str, object], ...]:
        grouped: dict[str, set[str]] = {}
        for event in self.events:
            if event["event_type"] != "plan_emission":
                continue
            grouped.setdefault(str(event["at"]), set()).add(str(event["campaign_id"]))
        return tuple(
            {
                "at": at,
                "campaign_ids": sorted(campaign_ids),
                "selection_status": "unresolved_no_selection_authority",
            }
            for at, campaign_ids in sorted(grouped.items())
            if len(campaign_ids) > 1
        )

    def runtime_artifact(self) -> dict[str, object]:
        campaigns = []
        for campaign in sorted(self.campaigns.values(), key=lambda item: item.campaign_id):
            campaigns.append(
                {
                    "campaign_id": campaign.campaign_id,
                    "activation_id": campaign.activation_id,
                    "symbol": campaign.symbol,
                    "plan_ids": list(campaign.plan_ids),
                    "status": campaign.status,
                    "quantity": campaign.quantity,
                    "average_entry_price": campaign.average_entry_price,
                    "open_notional": campaign.open_notional,
                    "open_risk": campaign.open_risk,
                    "entry_fill_count": campaign.entry_fill_count,
                    "reentry_count": campaign.reentry_count,
                    "realized_pnl": campaign.realized_pnl,
                    "terminal_reason": campaign.terminal_reason,
                }
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "contract_id": CONTRACT_ID,
            "artifact_type": "campaign_portfolio_account_state_shadow",
            "knowledge_policy": "runtime_market_and_order_state_only_no_retrospective_labels",
            "strategy_authority": "none",
            "selection_authority": "none",
            "size_authority": "none",
            "policy_promotion_eligible": False,
            "session_date": self.session_date.isoformat(),
            "account": {
                "account_id": self.constraints.account_id,
                "policy_id": self.constraints.policy_id,
                "account_class": self.constraints.account_class.value,
                "starting_equity": self.constraints.starting_equity,
                "starting_buying_power": self.constraints.starting_buying_power,
                "remaining_buying_power": self.remaining_buying_power,
                "realized_pnl": self.realized_pnl,
                "high_water_pnl": self.high_water_pnl,
                "open_campaign_count": self.open_campaign_count,
                "total_open_notional": self.total_open_notional,
                "total_open_risk": self.total_open_risk,
                "locked": self.locked,
                "lock_reason": self.lock_reason,
                "flatten_required": self.flatten_required,
            },
            "halted_symbols": sorted(self.halted_symbols),
            "simultaneous_opportunity_groups": list(self.simultaneous_opportunity_groups()),
            "campaigns": campaigns,
            "events": list(self.events),
        }

    def _validate_event_time(self, value: pd.Timestamp) -> pd.Timestamp:
        timestamp = _aware_timestamp(value, "event time")
        if timestamp.tz_convert(self.market_timezone).date() != self.session_date:
            raise ValueError("event time must belong to the ledger session_date")
        if self._last_event_at is not None and timestamp < self._last_event_at:
            raise ValueError("events must be applied in nondecreasing causal order")
        return timestamp

    def _commit_event_time(self, timestamp: pd.Timestamp) -> None:
        self._last_event_at = timestamp

    def _campaign(self, activation_id: str, symbol: str | None = None) -> CampaignState:
        campaign = self.campaigns.get(activation_id)
        if campaign is None:
            raise ValueError("unknown candidate activation")
        if symbol is not None and campaign.symbol != symbol:
            raise ValueError("fill symbol does not match candidate activation")
        return campaign

    def _expected_role(self, campaign: CampaignState) -> EntryRole:
        if campaign.entry_fill_count == 0:
            return EntryRole.STARTER
        if campaign.quantity > 0:
            return EntryRole.ADD
        return EntryRole.REENTRY

    def _require_new_fill_id(self, fill_id: str) -> None:
        if fill_id in self._seen_fill_ids:
            raise ValueError("fill_id must be globally unique within the ledger")

    def _apply_session_guards(self, at: pd.Timestamp) -> None:
        if self.locked:
            return
        if self.realized_pnl <= -self.constraints.max_daily_loss_dollars:
            self._lock("daily_max_loss")
        elif self.high_water_pnl > 0:
            floor = self.high_water_pnl * (1.0 - self.constraints.giveback_fraction)
            if self.realized_pnl <= floor:
                self._lock("profit_giveback")
        if self.locked:
            self.events.append(
                {
                    "sequence": len(self.events) + 1,
                    "event_type": "account_locked",
                    "at": at.isoformat(),
                    "reason": self.lock_reason,
                    "flatten_required": self.open_campaign_count > 0,
                }
            )

    def _lock(self, reason: str) -> None:
        self.locked = True
        self.lock_reason = self.lock_reason or reason

    def _append_event(
        self,
        event_type: str,
        at: pd.Timestamp,
        campaign: CampaignState,
        **details: object,
    ) -> None:
        self.events.append(
            {
                "sequence": len(self.events) + 1,
                "event_type": event_type,
                "at": at.isoformat(),
                "campaign_id": campaign.campaign_id,
                "activation_id": campaign.activation_id,
                "symbol": campaign.symbol,
                **details,
            }
        )


def campaign_id(
    *,
    session_date: date,
    account_id: str,
    policy_id: str,
    account_class: AccountClass,
    activation_id: str,
    symbol: str,
) -> str:
    """Return a stable account-scoped identifier for one candidate activation."""
    _require_identifiers(
        account_id=account_id,
        policy_id=policy_id,
        activation_id=activation_id,
        symbol=symbol,
    )
    payload = "|".join(
        (
            CONTRACT_ID,
            session_date.isoformat(),
            account_id,
            policy_id,
            account_class.value,
            activation_id,
            symbol,
        )
    )
    return f"campaign-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20]}"


def canonical_fingerprint(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_campaign_portfolio_contract(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported campaign-portfolio schema")
    if payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected campaign-portfolio contract ID")
    if payload.get("artifact_type") != "research_campaign_portfolio_account_state_contract":
        raise ValueError("unexpected campaign-portfolio artifact type")
    required_root = {
        "runtime_strategy_effect": "none_until_separately_promoted",
        "integration_status": "standalone_research_ledger_not_wired_to_runtime",
        "policy_promotion_eligible": False,
        "portfolio_backtest_eligible": False,
        "contains_account_limit_values": False,
    }
    for field, expected in required_root.items():
        if payload.get(field) != expected:
            raise ValueError(f"{field} must be {expected!r}")

    parents = payload.get("frozen_parents")
    if not isinstance(parents, Mapping):
        raise ValueError("frozen_parents must be an object")
    expected_parents = {
        "micro_policy_id": "micro-v0.1",
        "micro_policy_fingerprint": "49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa",
        "context_comparison_id": "ross-context-heldout-comparison-v0.1",
        "context_comparison_content_sha256": "d93d61ed0ebd5657bbed135beb7fe2d7b0f337d1e3f76720c0f1dcff7908ff54",
    }
    for field, expected in expected_parents.items():
        if parents.get(field) != expected:
            raise ValueError(f"frozen_parents.{field} must preserve the frozen parent")

    knowledge = payload.get("knowledge_policy")
    if not isinstance(knowledge, Mapping):
        raise ValueError("knowledge_policy must be an object")
    required_guards = {
        "inputs_available_by_event_time": True,
        "raw_transcripts_allowed": False,
        "retrospective_behavior_labels_allowed": False,
        "later_market_outcomes_allowed": False,
        "ai_selection_or_order_authority": False,
        "ai_risk_increase_authority": False,
    }
    for field, expected in required_guards.items():
        if knowledge.get(field) is not expected:
            raise ValueError(f"knowledge_policy.{field} must be {expected}")

    boundary = payload.get("authority_boundary")
    if not isinstance(boundary, Mapping):
        raise ValueError("authority_boundary must be an object")
    required_boundary = {
        "chooses_between_simultaneous_opportunities": False,
        "creates_or_sizes_orders": False,
        "synthesizes_fills": False,
        "changes_scanner_or_micro_policy": False,
        "validates_caller_supplied_event_feasibility": True,
    }
    for field, expected in required_boundary.items():
        if boundary.get(field) is not expected:
            raise ValueError(f"authority_boundary.{field} must be {expected}")

    if payload.get("campaign_key_fields") != [
        "session_date",
        "account_id",
        "account_policy_id",
        "account_class",
        "candidate_activation_id",
        "symbol",
    ]:
        raise ValueError("campaign_key_fields must preserve account-scoped activation identity")
    if payload.get("account_classes") != ["main", "small"]:
        raise ValueError("main and small account classes must remain separate")

    state = payload.get("required_causal_state")
    if not isinstance(state, list):
        raise ValueError("required_causal_state must be a list")
    required_state = {
        "held_position_lots",
        "remaining_buying_power",
        "open_position_count",
        "open_notional",
        "open_risk",
        "starter_add_reentry_state",
        "halt_state",
        "realized_daily_pnl",
        "daily_pnl_high_water",
        "terminal_account_lock",
        "simultaneous_opportunity_groups",
    }
    if set(state) != required_state or len(state) != len(required_state):
        raise ValueError("required_causal_state is incomplete or duplicated")

    if payload.get("simultaneous_opportunity_policy") != (
        "record the collision; require an externally registered deterministic priority "
        "or observed event sequence; never choose by iteration order"
    ):
        raise ValueError("simultaneous opportunity handling must remain fail-closed")


def load_campaign_portfolio_contract(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("campaign-portfolio contract root must be an object")
    validate_campaign_portfolio_contract(payload)
    return payload


def _aware_timestamp(value: pd.Timestamp, field: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return timestamp


def _require_identifiers(**values: str) -> None:
    for name, value in values.items():
        if not value.strip():
            raise ValueError(f"{name} must be non-empty")


def _finite_positive(value: float) -> bool:
    return bool(
        isinstance(value, Real)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and value > 0
    )


def _finite_nonnegative(value: float) -> bool:
    return bool(
        isinstance(value, Real)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and value >= 0
    )


def _valid_quantity(value: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _entry_slippage_bps(reference_price: float, fill_price: float) -> float | None:
    if not _finite_positive(reference_price) or not _finite_positive(fill_price):
        return None
    return max(0.0, (fill_price - reference_price) / reference_price * 10_000.0)
