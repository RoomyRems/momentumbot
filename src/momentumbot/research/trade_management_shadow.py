"""Causal chart-only trade-management sensitivity for frozen Micro fills.

The module deliberately starts *after* a frozen entry fill.  It cannot select a
candidate, alter an entry, widen the original stop, place an order, or inspect a
retrospective behavior label.  Its four registered cells vary only two choices
that the source evidence leaves unresolved: whether to realize half at the
first two-R milestone, and whether the completed-red-candle signal is read on
the 10-second entry chart or the one-minute management chart.

This is not a depth-aware execution model.  Eligible SIP prints are transaction
evidence only; they do not prove queue position, available size, spread, market
impact, or whether a displayed/hidden seller existed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

import pandas as pd

from momentumbot.micro_execution import (
    MicroEntryPlan,
    execution_eligible_trades,
)


CONTRACT_ID = "trade-management-shadow-v0.1"
CONTRACT_CONTENT_SHA256 = (
    "0bc4d98d75815c316f61cb6a06d1ac7deb4b0948672fcae58dfbc250b2e59d25"
)
EVIDENCE_AUDIT_CONTENT_SHA256 = (
    "d9f4927d136a80735efc2875b972b47a88a0e060ba9049b58f783cbff4add0f0"
)


class ManagementExitReason(str, Enum):
    INITIAL_STOP = "initial_stop"
    FIRST_TARGET = "first_target"
    BREAKEVEN_STOP = "breakeven_stop"
    FIRST_RED_CANDLE = "first_red_candle"


@dataclass(frozen=True, slots=True)
class ManagementCell:
    cell_id: str
    bar_seconds: int
    scale_half_at_two_r: bool

    def __post_init__(self) -> None:
        if not self.cell_id.strip():
            raise ValueError("cell_id must be non-empty")
        if self.bar_seconds not in (10, 60):
            raise ValueError("registered management bars must be 10 or 60 seconds")


REGISTERED_CELLS = (
    ManagementCell("full-first-red-10s", 10, False),
    ManagementCell("half-2r-breakeven-first-red-10s", 10, True),
    ManagementCell("full-first-red-1m", 60, False),
    ManagementCell("half-2r-breakeven-first-red-1m", 60, True),
)
_CELL_BY_ID = {cell.cell_id: cell for cell in REGISTERED_CELLS}


@dataclass(frozen=True, slots=True)
class ManagementExitLeg:
    quantity_fraction: float
    exit_time: pd.Timestamp
    exit_price: float
    reason: ManagementExitReason
    execution_via_odd_lot: bool

    def __post_init__(self) -> None:
        if not 0 < self.quantity_fraction <= 1:
            raise ValueError("quantity_fraction must be in (0, 1]")
        timestamp = pd.Timestamp(self.exit_time)
        if timestamp.tzinfo is None:
            raise ValueError("exit_time must be timezone-aware")
        if not math.isfinite(self.exit_price) or self.exit_price <= 0:
            raise ValueError("exit_price must be finite and positive")


@dataclass(frozen=True, slots=True)
class TradeManagementOutcome:
    cell: ManagementCell
    symbol: str
    fill_time: pd.Timestamp
    fill_price: float
    initial_stop_price: float
    first_target_price: float
    first_red_signal_at: pd.Timestamp | None
    target_touched: bool
    stop_moved_to_breakeven: bool
    legs: tuple[ManagementExitLeg, ...]
    remaining_fraction: float
    active_stop_price: float

    def __post_init__(self) -> None:
        timestamp = pd.Timestamp(self.fill_time)
        if timestamp.tzinfo is None:
            raise ValueError("fill_time must be timezone-aware")
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if not math.isfinite(self.fill_price) or self.fill_price <= 0:
            raise ValueError("fill_price must be finite and positive")
        if not 0 < self.initial_stop_price < self.fill_price:
            raise ValueError("initial stop must be positive and below fill")
        if self.first_target_price <= self.fill_price:
            raise ValueError("first target must be above fill")
        if not -1e-12 <= self.remaining_fraction <= 1 + 1e-12:
            raise ValueError("remaining_fraction must be in [0, 1]")
        realized = sum(leg.quantity_fraction for leg in self.legs)
        if not math.isclose(realized + self.remaining_fraction, 1.0, abs_tol=1e-9):
            raise ValueError("exit legs and remaining fraction must sum to one")
        if self.active_stop_price < self.initial_stop_price:
            raise ValueError("management cannot widen the original stop")
        if self.stop_moved_to_breakeven and not math.isclose(
            self.active_stop_price,
            self.fill_price,
            abs_tol=1e-9,
        ):
            raise ValueError("breakeven state must use the actual fill price")

    @property
    def initial_risk_per_share(self) -> float:
        return self.fill_price - self.initial_stop_price

    @property
    def realized_fraction(self) -> float:
        return sum(leg.quantity_fraction for leg in self.legs)

    @property
    def weighted_realized_r(self) -> float:
        risk = self.initial_risk_per_share
        return sum(
            leg.quantity_fraction * (leg.exit_price - self.fill_price) / risk
            for leg in self.legs
        )

    @property
    def status(self) -> str:
        if math.isclose(self.remaining_fraction, 0.0, abs_tol=1e-9):
            return "closed"
        if self.legs:
            return "partially_realized_open"
        return "filled_open"


def management_cell(cell_id: str) -> ManagementCell:
    try:
        return _CELL_BY_ID[cell_id]
    except KeyError as exc:
        raise ValueError(f"unregistered management cell: {cell_id}") from exc


def _aware_timestamp(value: object, name: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return timestamp


def _validate_bars(bars: pd.DataFrame) -> pd.DataFrame:
    required = {"open", "close"}
    missing = sorted(required - set(bars.columns))
    if missing:
        raise ValueError(f"management bars missing columns: {missing}")
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise TypeError("management bar index must be a DatetimeIndex")
    if bars.index.tz is None:
        raise ValueError("management bar timestamps must be timezone-aware")
    result = bars.sort_index(kind="stable").copy()
    opens = pd.to_numeric(result["open"], errors="coerce")
    closes = pd.to_numeric(result["close"], errors="coerce")
    if opens.isna().any() or closes.isna().any():
        raise ValueError("management bar open/close values must be numeric")
    if (opens <= 0).any() or (closes <= 0).any():
        raise ValueError("management bar open/close values must be positive")
    return result


def _fill_source_sequence(
    execution_path: pd.DataFrame,
    fill_time: pd.Timestamp,
    fill_price: float,
) -> int:
    same_time = execution_path[execution_path.index == fill_time]
    if same_time.empty:
        raise ValueError("frozen fill timestamp is absent from execution path")
    prices = pd.to_numeric(same_time["price"], errors="coerce")
    matching = same_time[(prices - fill_price).abs() <= 1e-9]
    if matching.empty:
        raise ValueError("frozen fill price is absent at its execution timestamp")
    return int(matching.iloc[0]["_source_sequence"])


def _validate_execution_path(execution_path: pd.DataFrame) -> pd.DataFrame:
    required = {"price", "_source_sequence", "_execution_via_odd_lot"}
    missing = sorted(required - set(execution_path.columns))
    if missing:
        raise ValueError(f"normalized execution path missing columns: {missing}")
    if not isinstance(execution_path.index, pd.DatetimeIndex):
        raise TypeError("execution path index must be a DatetimeIndex")
    if execution_path.index.tz is None:
        raise ValueError("execution path timestamps must be timezone-aware")
    if not execution_path.index.is_monotonic_increasing:
        raise ValueError("execution path must be time ordered")
    sequences = pd.to_numeric(execution_path["_source_sequence"], errors="coerce")
    if sequences.isna().any() or not sequences.is_monotonic_increasing:
        raise ValueError("execution path source sequence must be ordered")
    prices = pd.to_numeric(execution_path["price"], errors="coerce")
    if prices.isna().any() or (prices <= 0).any():
        raise ValueError("execution path prices must be positive numbers")
    return execution_path


def _first_red_signal(
    bars: pd.DataFrame,
    *,
    fill_time: pd.Timestamp,
    bar_seconds: int,
) -> pd.Timestamp | None:
    duration = pd.Timedelta(seconds=bar_seconds)
    for bar_start, bar in bars.iterrows():
        signal_at = pd.Timestamp(bar_start) + duration
        if signal_at <= fill_time:
            continue
        if float(bar["close"]) < float(bar["open"]):
            return signal_at
    return None


def simulate_trade_management(
    plan: MicroEntryPlan,
    *,
    fill_time: pd.Timestamp,
    fill_price: float,
    bars: pd.DataFrame,
    trades: pd.DataFrame,
    cell: ManagementCell | str,
) -> TradeManagementOutcome:
    """Apply one registered management cell after an existing frozen fill.

    The first completed red bar is the only favorable chart-exit signal in
    v0.1.  Stop, target and signal execution are ordered on the eligible SIP
    path.  No end-of-window liquidation is invented.
    """
    execution_path = execution_eligible_trades(trades)
    return simulate_trade_management_on_execution_path(
        plan,
        fill_time=fill_time,
        fill_price=fill_price,
        bars=bars,
        execution_path=execution_path,
        cell=cell,
    )


def simulate_trade_management_on_execution_path(
    plan: MicroEntryPlan,
    *,
    fill_time: pd.Timestamp,
    fill_price: float,
    bars: pd.DataFrame,
    execution_path: pd.DataFrame,
    cell: ManagementCell | str,
) -> TradeManagementOutcome:
    """Apply a registered cell using one pre-normalized execution path.

    Builders evaluating several frozen fills for the same symbol should use
    this form so SIP eligibility is calculated once.  ``execution_path`` must
    be the unmodified output of :func:`execution_eligible_trades`.
    """
    selected = management_cell(cell) if isinstance(cell, str) else cell
    if selected.cell_id not in _CELL_BY_ID or _CELL_BY_ID[selected.cell_id] != selected:
        raise ValueError("cell is not an exact registered management cell")
    filled_at = _aware_timestamp(fill_time, "fill_time")
    numeric_fill = float(fill_price)
    if not math.isfinite(numeric_fill) or numeric_fill <= plan.stop_price:
        raise ValueError("fill_price must be finite and above the original stop")
    if plan.symbol.strip() == "":
        raise ValueError("plan symbol must be non-empty")

    management_bars = _validate_bars(bars)
    execution_path = _validate_execution_path(execution_path)
    fill_sequence = _fill_source_sequence(execution_path, filled_at, numeric_fill)
    future = execution_path[execution_path["_source_sequence"] > fill_sequence]

    initial_stop = float(plan.stop_price)
    initial_risk = numeric_fill - initial_stop
    first_target = round(numeric_fill + 2.0 * initial_risk, 10)
    red_signal_at = _first_red_signal(
        management_bars,
        fill_time=filled_at,
        bar_seconds=selected.bar_seconds,
    )

    remaining = 1.0
    active_stop = initial_stop
    target_touched = False
    stop_moved = False
    legs: list[ManagementExitLeg] = []

    for at, row in future.iterrows():
        timestamp = pd.Timestamp(at)
        price = float(row["price"])
        odd_lot = bool(row.get("_execution_via_odd_lot", False))

        # The stop was active before this print and therefore has priority.
        if price <= active_stop:
            reason = (
                ManagementExitReason.BREAKEVEN_STOP
                if stop_moved
                else ManagementExitReason.INITIAL_STOP
            )
            legs.append(
                ManagementExitLeg(remaining, timestamp, price, reason, odd_lot)
            )
            remaining = 0.0
            break

        # A bar-close market-exit decision already existed before this print.
        if red_signal_at is not None and timestamp >= red_signal_at:
            legs.append(
                ManagementExitLeg(
                    remaining,
                    timestamp,
                    price,
                    ManagementExitReason.FIRST_RED_CANDLE,
                    odd_lot,
                )
            )
            remaining = 0.0
            break

        if not target_touched and price >= first_target:
            target_touched = True
            if selected.scale_half_at_two_r:
                legs.append(
                    ManagementExitLeg(
                        0.5,
                        timestamp,
                        first_target,
                        ManagementExitReason.FIRST_TARGET,
                        odd_lot,
                    )
                )
                remaining = 0.5
                active_stop = numeric_fill
                stop_moved = True

    return TradeManagementOutcome(
        cell=selected,
        symbol=plan.symbol,
        fill_time=filled_at,
        fill_price=numeric_fill,
        initial_stop_price=initial_stop,
        first_target_price=first_target,
        first_red_signal_at=red_signal_at,
        target_touched=target_touched,
        stop_moved_to_breakeven=stop_moved,
        legs=tuple(legs),
        remaining_fraction=remaining,
        active_stop_price=active_stop,
    )
