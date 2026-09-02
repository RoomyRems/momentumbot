from __future__ import annotations

import math
from dataclasses import dataclass

from .models import EntryPlan, RiskPolicy


@dataclass(slots=True)
class SessionRiskState:
    starting_equity: float
    policy: RiskPolicy
    realized_pnl: float = 0.0
    high_water_pnl: float = 0.0
    locked: bool = False
    lock_reason: str | None = None

    def record_realized(self, pnl: float) -> None:
        self.realized_pnl += pnl
        self.high_water_pnl = max(self.high_water_pnl, self.realized_pnl)
        self._apply_guards()

    def lock(self, reason: str) -> None:
        self.locked = True
        self.lock_reason = self.lock_reason or reason

    def _apply_guards(self) -> None:
        max_loss = self.starting_equity * self.policy.max_daily_loss_fraction
        if self.realized_pnl <= -max_loss:
            self.lock("daily max loss")
            return
        if self.high_water_pnl > 0:
            giveback_floor = self.high_water_pnl * (1.0 - self.policy.giveback_fraction)
            if self.realized_pnl <= giveback_floor:
                self.lock("profit giveback")


def size_entry(plan: EntryPlan, state: SessionRiskState) -> int:
    if state.locked or plan.risk_per_share <= 0:
        return 0
    equity = state.starting_equity + state.realized_pnl
    if equity <= 0:
        return 0
    risk_budget = equity * state.policy.risk_per_trade_fraction
    value_budget = equity * state.policy.max_position_fraction_of_equity
    by_risk = math.floor(risk_budget / plan.risk_per_share)
    by_value = math.floor(value_budget / plan.trigger_price)
    return max(0, min(by_risk, by_value))
