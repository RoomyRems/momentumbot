"""Causal intrabar execution for research micro pullback plans.

The execution engine intentionally does not decide whether a setup is good.
A plan may only be armed from a fully completed micro bar. Once armed, ordered
price-eligible SIP prints determine whether the next forming bar actually makes
a new high, the first observable fill price, and the ordering of later stop or
target events.

This module is research-only. It never places brokerage orders.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

import pandas as pd

from .micro_bars import minute_trade_eligibility


class MicroExecutionStatus(str, Enum):
    NOT_TRIGGERED = "not_triggered"
    FILLED_OPEN = "filled_open"
    STOPPED = "stopped"
    TARGET_HIT = "target_hit"


@dataclass(frozen=True, slots=True)
class MicroEntryPlan:
    symbol: str
    source_bar_start: pd.Timestamp
    armed_at: pd.Timestamp
    expires_at: pd.Timestamp
    breakout_level: float
    minimum_new_high_price: float
    stop_price: float

    def __post_init__(self) -> None:
        for name in ("source_bar_start", "armed_at", "expires_at"):
            value = pd.Timestamp(getattr(self, name))
            if value.tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.armed_at >= self.expires_at:
            raise ValueError("armed_at must be before expires_at")
        if self.breakout_level <= 0 or self.minimum_new_high_price <= 0:
            raise ValueError("entry prices must be positive")
        if self.minimum_new_high_price <= self.breakout_level:
            raise ValueError("minimum_new_high_price must exceed breakout_level")
        if self.stop_price <= 0 or self.stop_price >= self.minimum_new_high_price:
            raise ValueError("stop_price must be positive and below entry trigger")


@dataclass(frozen=True, slots=True)
class MicroExecutionOutcome:
    plan: MicroEntryPlan
    status: MicroExecutionStatus
    trigger_time: pd.Timestamp | None = None
    trigger_print_price: float | None = None
    fill_time: pd.Timestamp | None = None
    fill_price: float | None = None
    exit_time: pd.Timestamp | None = None
    exit_price: float | None = None

    @property
    def planned_trigger_price(self) -> float:
        return self.plan.minimum_new_high_price

    @property
    def entry_slippage(self) -> float | None:
        if self.fill_price is None:
            return None
        return self.fill_price - self.plan.minimum_new_high_price

    @property
    def initial_risk_per_share(self) -> float | None:
        if self.fill_price is None:
            return None
        return self.fill_price - self.plan.stop_price

    @property
    def realized_r(self) -> float | None:
        risk = self.initial_risk_per_share
        if risk is None or risk <= 0 or self.exit_price is None or self.fill_price is None:
            return None
        return (self.exit_price - self.fill_price) / risk


def _conditions(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    try:
        if pd.isna(value):
            return ()
    except (TypeError, ValueError):
        pass
    if isinstance(value, tuple):
        return tuple(str(item) for item in value)
    if isinstance(value, (list, set)):
        return tuple(str(item) for item in value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ()
        if text[0] in "([":
            try:
                parsed = ast.literal_eval(text)
            except (SyntaxError, ValueError):
                return (text,)
            if isinstance(parsed, str):
                return (parsed,)
            if isinstance(parsed, Iterable):
                return tuple(str(item) for item in parsed)
        return (text,)
    return (str(value),)


def price_eligible_trades(trades: pd.DataFrame) -> pd.DataFrame:
    """Return a stable ordered price path using Alpaca minute-bar eligibility."""
    required = {"price", "conditions", "tape"}
    missing = sorted(required - set(trades.columns))
    if missing:
        raise ValueError(f"missing trade columns: {missing}")
    if not isinstance(trades.index, pd.DatetimeIndex):
        raise TypeError("trade index must be a DatetimeIndex")
    if trades.index.tz is None:
        raise ValueError("trade timestamps must be timezone-aware")
    if trades.empty:
        result = trades.copy()
        result["_sequence"] = pd.Series(dtype="int64")
        return result

    ordered = trades.copy()
    ordered["_source_sequence"] = range(len(ordered))
    ordered = ordered.sort_index(kind="stable")
    mask: list[bool] = []
    for _, row in ordered.iterrows():
        eligibility = minute_trade_eligibility(
            str(row.get("tape") or ""),
            _conditions(row.get("conditions")),
        )
        mask.append(eligibility.updates_price)
    eligible = ordered.loc[mask].copy()
    eligible["_sequence"] = range(len(eligible))
    return eligible


def build_completed_bar_breakout_plan(
    symbol: str,
    bar_start: pd.Timestamp,
    bar: pd.Series,
    *,
    bar_seconds: int = 10,
    tick_size: float = 0.01,
) -> MicroEntryPlan | None:
    """Arm a one-bar breakout plan from information known at bar completion.

    This helper is intentionally permissive: it only asks whether the completed
    bar made a high and then finished below it, so a later strategy layer can
    decide whether that pause is a high-quality micro pullback. The stop is the
    completed bar's low. The plan expires at the end of the immediately
    following micro bar; if no new high occurs, a later completed bar must create
    a fresh plan with fresh information.
    """
    required = {"high", "low", "close"}
    missing = sorted(required - set(bar.index))
    if missing:
        raise ValueError(f"completed bar missing columns: {missing}")
    start = pd.Timestamp(bar_start)
    if start.tzinfo is None:
        raise ValueError("bar_start must be timezone-aware")
    if bar_seconds <= 0:
        raise ValueError("bar_seconds must be positive")
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")

    high = float(bar["high"])
    low = float(bar["low"])
    close = float(bar["close"])
    if high <= 0 or low <= 0 or low > high:
        raise ValueError("invalid completed bar price range")
    if close >= high:
        return None

    high_time = bar.get("high_time")
    close_time = bar.get("close_time")
    if high_time is not None and close_time is not None:
        high_timestamp = pd.Timestamp(high_time)
        close_timestamp = pd.Timestamp(close_time)
        if high_timestamp.tzinfo is None or close_timestamp.tzinfo is None:
            raise ValueError("high_time and close_time must be timezone-aware")
        if high_timestamp >= close_timestamp:
            return None

    duration = pd.Timedelta(seconds=bar_seconds)
    armed_at = start + duration
    minimum_new_high = round(high + tick_size, 10)
    return MicroEntryPlan(
        symbol=symbol,
        source_bar_start=start,
        armed_at=armed_at,
        expires_at=armed_at + duration,
        breakout_level=high,
        minimum_new_high_price=minimum_new_high,
        stop_price=low,
    )


def completed_bar_breakout_plans(
    symbol: str,
    bars: pd.DataFrame,
    *,
    bar_seconds: int = 10,
    tick_size: float = 0.01,
    start_at: pd.Timestamp | None = None,
) -> tuple[MicroEntryPlan, ...]:
    """Create all causal next-bar breakout plans from completed micro bars."""
    required = {"high", "low", "close"}
    missing = sorted(required - set(bars.columns))
    if missing:
        raise ValueError(f"micro bars missing columns: {missing}")
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise TypeError("micro-bar index must be a DatetimeIndex")
    if bars.index.tz is None:
        raise ValueError("micro-bar timestamps must be timezone-aware")
    window = bars.sort_index()
    if start_at is not None:
        start = pd.Timestamp(start_at)
        if start.tzinfo is None:
            raise ValueError("start_at must be timezone-aware")
        window = window.loc[start:]

    plans: list[MicroEntryPlan] = []
    for bar_start, bar in window.iterrows():
        plan = build_completed_bar_breakout_plan(
            symbol,
            bar_start,
            bar,
            bar_seconds=bar_seconds,
            tick_size=tick_size,
        )
        if plan is not None:
            plans.append(plan)
    return tuple(plans)


def _exit_limit(value: pd.Timestamp | None) -> pd.Timestamp | None:
    if value is None:
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("exit_until must be timezone-aware")
    return timestamp


def _simulate_on_price_path(
    plan: MicroEntryPlan,
    path: pd.DataFrame,
    *,
    target_price: float | None,
    exit_limit: pd.Timestamp | None,
) -> MicroExecutionOutcome:
    if target_price is not None and target_price <= plan.minimum_new_high_price:
        raise ValueError("target_price must exceed the planned trigger")
    if path.empty:
        return MicroExecutionOutcome(plan=plan, status=MicroExecutionStatus.NOT_TRIGGERED)

    entry_window = path[
        (path.index >= plan.armed_at) & (path.index < plan.expires_at)
    ]
    prices = pd.to_numeric(entry_window["price"], errors="coerce")
    crossing = entry_window[prices >= plan.minimum_new_high_price]
    if crossing.empty:
        return MicroExecutionOutcome(plan=plan, status=MicroExecutionStatus.NOT_TRIGGERED)

    trigger_row = crossing.iloc[0]
    trigger_sequence = int(trigger_row["_sequence"])
    trigger_time = pd.Timestamp(crossing.index[0])
    trigger_price = float(trigger_row["price"])
    fill_price = trigger_price

    after_fill = path[path["_sequence"] > trigger_sequence]
    if exit_limit is not None:
        after_fill = after_fill[after_fill.index <= exit_limit]
    if after_fill.empty:
        return MicroExecutionOutcome(
            plan=plan,
            status=MicroExecutionStatus.FILLED_OPEN,
            trigger_time=trigger_time,
            trigger_print_price=trigger_price,
            fill_time=trigger_time,
            fill_price=fill_price,
        )

    future_prices = pd.to_numeric(after_fill["price"], errors="coerce")
    stop_hits = after_fill[future_prices <= plan.stop_price]
    target_hits = (
        after_fill[future_prices >= target_price]
        if target_price is not None
        else after_fill.iloc[0:0]
    )
    first_stop = stop_hits.iloc[0] if not stop_hits.empty else None
    first_target = target_hits.iloc[0] if not target_hits.empty else None

    if first_stop is not None and (
        first_target is None
        or int(first_stop["_sequence"]) < int(first_target["_sequence"])
    ):
        stop_time = pd.Timestamp(stop_hits.index[0])
        return MicroExecutionOutcome(
            plan=plan,
            status=MicroExecutionStatus.STOPPED,
            trigger_time=trigger_time,
            trigger_print_price=trigger_price,
            fill_time=trigger_time,
            fill_price=fill_price,
            exit_time=stop_time,
            exit_price=float(first_stop["price"]),
        )
    if first_target is not None:
        target_time = pd.Timestamp(target_hits.index[0])
        return MicroExecutionOutcome(
            plan=plan,
            status=MicroExecutionStatus.TARGET_HIT,
            trigger_time=trigger_time,
            trigger_print_price=trigger_price,
            fill_time=trigger_time,
            fill_price=fill_price,
            exit_time=target_time,
            exit_price=float(target_price),
        )

    return MicroExecutionOutcome(
        plan=plan,
        status=MicroExecutionStatus.FILLED_OPEN,
        trigger_time=trigger_time,
        trigger_print_price=trigger_price,
        fill_time=trigger_time,
        fill_price=fill_price,
    )


def simulate_micro_entry(
    plan: MicroEntryPlan,
    trades: pd.DataFrame,
    *,
    target_price: float | None = None,
    exit_until: pd.Timestamp | None = None,
) -> MicroExecutionOutcome:
    """Execute one causal long stop-entry plan against ordered SIP prints.

    Entry uses the first price-eligible print at or above the minimum new-high
    price during the plan's one-bar lifetime. Its observed print price is the
    fill, so a gap from the planned trigger is recorded as adverse slippage.

    After a fill, a stop is modeled as stop-market: the first eligible print at
    or below the stop becomes the exit fill and may be worse than the stop.
    An optional profit target is modeled as a limit: the first eligible print at
    or above the target establishes event ordering, but the fill is capped at
    the target rather than granting favorable print slippage.
    """
    path = price_eligible_trades(trades)
    return _simulate_on_price_path(
        plan,
        path,
        target_price=target_price,
        exit_limit=_exit_limit(exit_until),
    )


def simulate_micro_entries(
    plans: Iterable[MicroEntryPlan],
    trades: pd.DataFrame,
    *,
    target_price: float | None = None,
    exit_until: pd.Timestamp | None = None,
) -> tuple[MicroExecutionOutcome, ...]:
    """Execute many plans while normalizing the SIP price path only once."""
    path = price_eligible_trades(trades)
    exit_limit = _exit_limit(exit_until)
    return tuple(
        _simulate_on_price_path(
            plan,
            path,
            target_price=target_price,
            exit_limit=exit_limit,
        )
        for plan in plans
    )
