"""Deterministic marketable-limit and equity-fee research primitives.

This child layer is deliberately separate from the frozen Micro-v0.1 print
proxy.  It accepts only top-of-book states available by receive time and never
places a broker order.  Displayed size is haircut, used once, and never treated
as proof of queue priority, hidden liquidity, or a repeatable fill.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from enum import Enum
from pathlib import Path
from typing import Mapping, Sequence

from momentumbot.research.microstructure_contract import canonical_fingerprint


CONTRACT_ID = "prospective-management-execution-v0.1"
CONTRACT_CONTENT_SHA256 = (
    "14812b9f25b5ea7230254ed86b1e0eaa30fffe3dc13b1ee141b19770706090f9"
)
MICRO_POLICY_FINGERPRINT = (
    "49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa"
)
ACCOUNT_INTEGRATION_CONTENT_SHA256 = (
    "64489aa27fec5eaf8ca12c94f4aeb47344d49a79b14df1bdda706cd23cc9ce73"
)
TRADE_MANAGEMENT_RESULT_CONTENT_SHA256 = (
    "b06159fee47d1d0f59a8d67aabfc082a1c3af6872a88f18f9a7eb49a3f969434"
)
LEVEL2_CONTENT_SHA256 = (
    "6d3a41d6bde3844900bc880632d8bc9d6c5f7b787edd5f0c302a709dcb9c1bf1"
)
SELECTED_MANAGEMENT_CELL = "half-2r-breakeven-first-red-1m"

_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,31}$")
_CENT = Decimal("0.01")
_NS_PER_MS = 1_000_000
BASELINE_LIMIT_OFFSET_TICKS = 5
STRESS_LIMIT_OFFSET_TICKS = 2


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class ExecutionStatus(str, Enum):
    UNAVAILABLE_NO_FRESH_QUOTE = "unavailable_no_fresh_quote"
    CANCELLED_UNFILLED = "cancelled_unfilled"
    HALTED_CANCELLED = "halted_cancelled"
    PARTIALLY_FILLED_CANCELLED = "partially_filled_cancelled"
    FILLED = "filled"


def _decimal(value: object, field: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite decimal")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a finite decimal") from exc
    if not parsed.is_finite() or parsed < 0 or (positive and parsed <= 0):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{field} must be finite and {qualifier}")
    return parsed


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


@dataclass(frozen=True, slots=True)
class TopOfBookEvent:
    """A complete receive-time top-of-book state for one symbol."""

    symbol: str
    ts_recv_ns: int
    sequence: int
    bid_price: Decimal
    bid_size: int
    ask_price: Decimal
    ask_size: int
    halted: bool = False

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("symbol must be canonical uppercase US-equity notation")
        _integer(self.ts_recv_ns, "ts_recv_ns", minimum=1)
        _integer(self.sequence, "sequence")
        bid = _decimal(self.bid_price, "bid_price", positive=True)
        ask = _decimal(self.ask_price, "ask_price", positive=True)
        if bid >= ask:
            raise ValueError("top of book must have a positive, non-crossed spread")
        _integer(self.bid_size, "bid_size")
        _integer(self.ask_size, "ask_size")
        if not isinstance(self.halted, bool):
            raise ValueError("halted must be boolean")
        object.__setattr__(self, "bid_price", bid)
        object.__setattr__(self, "ask_price", ask)


@dataclass(frozen=True, slots=True)
class MarketableLimitOrder:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    decision_ts_ns: int
    limit_price: Decimal

    def __post_init__(self) -> None:
        if not self.order_id.strip():
            raise ValueError("order_id must be non-empty")
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("symbol must be canonical uppercase US-equity notation")
        _integer(self.quantity, "quantity", minimum=1)
        _integer(self.decision_ts_ns, "decision_ts_ns", minimum=1)
        try:
            side = OrderSide(self.side)
        except ValueError as exc:
            raise ValueError("side must be buy or sell") from exc
        object.__setattr__(self, "side", side)
        object.__setattr__(
            self,
            "limit_price",
            _decimal(self.limit_price, "limit_price", positive=True),
        )


@dataclass(frozen=True, slots=True)
class MarketableLimitPolicy:
    policy_id: str
    decision_to_arrival_ms: int
    max_quote_age_ms: int
    cancel_after_arrival_ms: int
    cancel_ack_ms: int
    displayed_size_participation: Decimal

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ValueError("policy_id must be non-empty")
        _integer(self.decision_to_arrival_ms, "decision_to_arrival_ms")
        _integer(self.max_quote_age_ms, "max_quote_age_ms", minimum=1)
        _integer(
            self.cancel_after_arrival_ms,
            "cancel_after_arrival_ms",
            minimum=1,
        )
        _integer(self.cancel_ack_ms, "cancel_ack_ms")
        participation = _decimal(
            self.displayed_size_participation,
            "displayed_size_participation",
            positive=True,
        )
        if participation > 1:
            raise ValueError("displayed_size_participation cannot exceed one")
        object.__setattr__(self, "displayed_size_participation", participation)


BASELINE_CONSERVATIVE_POLICY = MarketableLimitPolicy(
    policy_id="l1-conservative-v0.1",
    decision_to_arrival_ms=100,
    max_quote_age_ms=100,
    cancel_after_arrival_ms=250,
    cancel_ack_ms=100,
    displayed_size_participation=Decimal("0.25"),
)

STRESS_POLICY = MarketableLimitPolicy(
    policy_id="l1-stress-v0.1",
    decision_to_arrival_ms=250,
    max_quote_age_ms=50,
    cancel_after_arrival_ms=150,
    cancel_ack_ms=150,
    displayed_size_participation=Decimal("0.10"),
)


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    order: MarketableLimitOrder
    policy: MarketableLimitPolicy
    status: ExecutionStatus
    arrival_ts_ns: int
    cancel_requested_ts_ns: int
    cancel_ack_ts_ns: int
    filled_quantity: int
    unfilled_quantity: int
    fill_ts_ns: int | None = None
    fill_price: Decimal | None = None
    quote_ts_recv_ns: int | None = None
    displayed_contra_size: int | None = None
    spread: Decimal | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.filled_quantity < 0 or self.unfilled_quantity < 0:
            raise ValueError("fill quantities cannot be negative")
        if self.filled_quantity + self.unfilled_quantity != self.order.quantity:
            raise ValueError("filled and unfilled quantities must equal order quantity")
        if self.filled_quantity == 0:
            if any(
                value is not None
                for value in (
                    self.fill_ts_ns,
                    self.fill_price,
                    self.quote_ts_recv_ns,
                    self.displayed_contra_size,
                    self.spread,
                )
            ):
                raise ValueError("unfilled outcomes cannot carry fill evidence")
        else:
            if None in (
                self.fill_ts_ns,
                self.fill_price,
                self.quote_ts_recv_ns,
                self.displayed_contra_size,
                self.spread,
            ):
                raise ValueError("filled outcomes require complete quote and fill evidence")
            _decimal(self.fill_price, "fill_price", positive=True)
        if not self.reason.strip():
            raise ValueError("execution outcome requires an explicit reason")


def marketable_limit_price(
    contra_price: Decimal,
    *,
    side: OrderSide,
    tick_size: Decimal = Decimal("0.01"),
    offset_ticks: int,
) -> Decimal:
    """Create a guarded marketable limit from the causal contra quote."""
    reference = _decimal(contra_price, "contra_price", positive=True)
    tick = _decimal(tick_size, "tick_size", positive=True)
    _integer(offset_ticks, "offset_ticks")
    try:
        normalized_side = OrderSide(side)
    except ValueError as exc:
        raise ValueError("side must be buy or sell") from exc
    offset = tick * offset_ticks
    result = (
        reference + offset
        if normalized_side is OrderSide.BUY
        else reference - offset
    )
    if result <= 0:
        raise ValueError("sell limit offset must leave a positive price")
    return result


def _validate_quote_stream(
    symbol: str,
    quotes: Sequence[TopOfBookEvent],
) -> tuple[TopOfBookEvent, ...]:
    events = tuple(quotes)
    previous: tuple[int, int] | None = None
    for event in events:
        if event.symbol != symbol:
            raise ValueError("quote symbol does not match order symbol")
        key = (event.ts_recv_ns, event.sequence)
        if previous is not None and key <= previous:
            raise ValueError("quote stream must be strictly ordered by receive time and sequence")
        previous = key
    return events


def _contra(event: TopOfBookEvent, side: OrderSide) -> tuple[Decimal, int]:
    if side is OrderSide.BUY:
        return event.ask_price, event.ask_size
    return event.bid_price, event.bid_size


def _crosses_limit(price: Decimal, order: MarketableLimitOrder) -> bool:
    if order.side is OrderSide.BUY:
        return price <= order.limit_price
    return price >= order.limit_price


def simulate_marketable_limit_order(
    order: MarketableLimitOrder,
    quotes: Sequence[TopOfBookEvent],
    policy: MarketableLimitPolicy,
) -> ExecutionOutcome:
    """Simulate one immediate marketable-limit attempt without queue credit.

    The last quote at or before arrival may be used only if it is fresh.  Later
    full quote states may make the order marketable until cancellation is
    acknowledged.  The first eligible displayed state is haircut once; later
    states cannot refill the same attempt.
    """
    events = _validate_quote_stream(order.symbol, quotes)
    arrival = order.decision_ts_ns + policy.decision_to_arrival_ms * _NS_PER_MS
    cancel_requested = arrival + policy.cancel_after_arrival_ms * _NS_PER_MS
    cancel_ack = cancel_requested + policy.cancel_ack_ms * _NS_PER_MS
    max_age_ns = policy.max_quote_age_ms * _NS_PER_MS

    candidates: list[TopOfBookEvent] = []
    prior = [event for event in events if event.ts_recv_ns <= arrival]
    if prior and arrival - prior[-1].ts_recv_ns <= max_age_ns:
        candidates.append(prior[-1])
    candidates.extend(
        event for event in events if arrival < event.ts_recv_ns < cancel_ack
    )

    saw_fresh = False
    saw_halt = False
    saw_non_halted = False
    for event in candidates:
        saw_fresh = True
        if event.halted:
            saw_halt = True
            continue
        saw_non_halted = True
        contra_price, contra_size = _contra(event, order.side)
        if contra_size <= 0 or not _crosses_limit(contra_price, order):
            continue
        available = int(
            (Decimal(contra_size) * policy.displayed_size_participation).to_integral_value(
                rounding=ROUND_FLOOR
            )
        )
        if available <= 0:
            continue
        filled = min(order.quantity, available)
        status = (
            ExecutionStatus.FILLED
            if filled == order.quantity
            else ExecutionStatus.PARTIALLY_FILLED_CANCELLED
        )
        return ExecutionOutcome(
            order=order,
            policy=policy,
            status=status,
            arrival_ts_ns=arrival,
            cancel_requested_ts_ns=cancel_requested,
            cancel_ack_ts_ns=cancel_ack,
            filled_quantity=filled,
            unfilled_quantity=order.quantity - filled,
            fill_ts_ns=max(arrival, event.ts_recv_ns),
            fill_price=contra_price,
            quote_ts_recv_ns=event.ts_recv_ns,
            displayed_contra_size=contra_size,
            spread=event.ask_price - event.bid_price,
            reason=(
                "first eligible displayed contra state used once after participation haircut"
            ),
        )

    if not saw_fresh:
        status = ExecutionStatus.UNAVAILABLE_NO_FRESH_QUOTE
        reason = "no complete fresh top-of-book state existed while the order was active"
    elif saw_halt and not saw_non_halted:
        status = ExecutionStatus.HALTED_CANCELLED
        reason = "all fresh top-of-book states were halted before cancellation acknowledgement"
    else:
        status = ExecutionStatus.CANCELLED_UNFILLED
        reason = "no non-halted displayed contra state crossed the limit with usable haircut size"
    return ExecutionOutcome(
        order=order,
        policy=policy,
        status=status,
        arrival_ts_ns=arrival,
        cancel_requested_ts_ns=cancel_requested,
        cancel_ack_ts_ns=cancel_ack,
        filled_quantity=0,
        unfilled_quantity=order.quantity,
        reason=reason,
    )


@dataclass(frozen=True, slots=True)
class EquityFeeSchedule:
    """Frozen U.S. equity research fee schedule effective August 2026."""

    sec_sale_rate_per_dollar: Decimal = Decimal("0.0000206")
    taf_sale_rate_per_share: Decimal = Decimal("0.000195")
    taf_per_trade_cap: Decimal = Decimal("9.79")
    cat_rate_per_executed_share: Decimal = Decimal("0.000003")
    commission_rate_per_dollar: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        for field in (
            "sec_sale_rate_per_dollar",
            "taf_sale_rate_per_share",
            "taf_per_trade_cap",
            "cat_rate_per_executed_share",
            "commission_rate_per_dollar",
        ):
            object.__setattr__(self, field, _decimal(getattr(self, field), field))


@dataclass(frozen=True, slots=True)
class ExecutedEquityTrade:
    side: OrderSide
    quantity: int
    price: Decimal

    def __post_init__(self) -> None:
        _integer(self.quantity, "quantity", minimum=1)
        try:
            side = OrderSide(self.side)
        except ValueError as exc:
            raise ValueError("side must be buy or sell") from exc
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "price", _decimal(self.price, "price", positive=True))

    @property
    def notional(self) -> Decimal:
        return self.price * self.quantity


@dataclass(frozen=True, slots=True)
class DailyEquityFees:
    sec_exact: Decimal
    taf_exact: Decimal
    cat_exact: Decimal
    commission_exact: Decimal
    sec_charged: Decimal
    taf_charged: Decimal
    cat_charged: Decimal
    commission_charged: Decimal
    total_charged: Decimal

    def as_strings(self) -> dict[str, str]:
        return {
            field: format(getattr(self, field), "f")
            for field in self.__dataclass_fields__
        }


def _ceil_cent(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_CEILING)


def aggregate_daily_equity_fees(
    trades: Sequence[ExecutedEquityTrade],
    schedule: EquityFeeSchedule = EquityFeeSchedule(),
) -> DailyEquityFees:
    """Aggregate fee types by account-day, then round each type up to a cent."""
    sec = Decimal("0")
    taf = Decimal("0")
    cat = Decimal("0")
    commission = Decimal("0")
    for trade in trades:
        cat += Decimal(trade.quantity) * schedule.cat_rate_per_executed_share
        commission += trade.notional * schedule.commission_rate_per_dollar
        if trade.side is OrderSide.SELL:
            sec += trade.notional * schedule.sec_sale_rate_per_dollar
            taf += min(
                Decimal(trade.quantity) * schedule.taf_sale_rate_per_share,
                schedule.taf_per_trade_cap,
            )
    sec_charged = _ceil_cent(sec)
    taf_charged = _ceil_cent(taf)
    cat_charged = _ceil_cent(cat)
    commission_charged = _ceil_cent(commission)
    return DailyEquityFees(
        sec_exact=sec,
        taf_exact=taf,
        cat_exact=cat,
        commission_exact=commission,
        sec_charged=sec_charged,
        taf_charged=taf_charged,
        cat_charged=cat_charged,
        commission_charged=commission_charged,
        total_charged=(
            sec_charged + taf_charged + cat_charged + commission_charged
        ),
    )


def load_prospective_execution_contract(
    path: str | Path,
) -> dict[str, object]:
    with Path(path).open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("prospective management/execution contract must be an object")
    validate_prospective_execution_contract(payload)
    return payload


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def validate_prospective_execution_contract(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != 1 or payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected prospective management/execution contract")
    claimed = payload.get("content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if claimed != CONTRACT_CONTENT_SHA256 or canonical_fingerprint(unsigned) != claimed:
        raise ValueError("prospective management/execution content hash mismatch")

    parents = _mapping(payload.get("frozen_parents"), "frozen_parents")
    expected_parents = {
        "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
        "account_integration_content_sha256": ACCOUNT_INTEGRATION_CONTENT_SHA256,
        "trade_management_result_content_sha256": TRADE_MANAGEMENT_RESULT_CONTENT_SHA256,
        "level2_feasibility_content_sha256": LEVEL2_CONTENT_SHA256,
    }
    for key, expected in expected_parents.items():
        if parents.get(key) != expected:
            raise ValueError(f"frozen_parents.{key} changed")

    management = _mapping(payload.get("management_rule"), "management_rule")
    if management.get("selected_cell_id") != SELECTED_MANAGEMENT_CELL:
        raise ValueError("prospective management cell changed")
    if management.get("selection_used_july_pnl") is not False:
        raise ValueError("retrospective July P&L cannot select management")
    if management.get("bar_seconds") != 60:
        raise ValueError("prospective management timeframe changed")

    scenarios = payload.get("execution_scenarios")
    if not isinstance(scenarios, list) or len(scenarios) != 2:
        raise ValueError("exactly two execution scenarios are required")
    expected = (
        (BASELINE_CONSERVATIVE_POLICY, BASELINE_LIMIT_OFFSET_TICKS),
        (STRESS_POLICY, STRESS_LIMIT_OFFSET_TICKS),
    )
    for row, (policy, offset_ticks) in zip(scenarios, expected, strict=True):
        item = _mapping(row, "execution scenario")
        required = {
            "policy_id": policy.policy_id,
            "decision_to_arrival_ms": policy.decision_to_arrival_ms,
            "max_quote_age_ms": policy.max_quote_age_ms,
            "cancel_after_arrival_ms": policy.cancel_after_arrival_ms,
            "cancel_ack_ms": policy.cancel_ack_ms,
            "displayed_size_participation": format(
                policy.displayed_size_participation, "f"
            ),
            "marketable_limit_offset_ticks": offset_ticks,
        }
        for key, value in required.items():
            if item.get(key) != value:
                raise ValueError(f"execution scenario {policy.policy_id}.{key} changed")

    fees = _mapping(payload.get("fee_schedule"), "fee_schedule")
    expected_fees = {
        "effective_date": "2026-07-20",
        "sec_sell_rate_per_dollar": "0.0000206",
        "taf_sell_rate_per_share": "0.000195",
        "taf_per_trade_cap_usd": "9.79",
        "cat_rate_per_executed_equity_share": "0.000003",
        "direct_api_equity_commission_rate_per_dollar": "0",
        "aggregation": "sum each fee type by account-day then round each type up to the nearest cent",
    }
    for field, value in expected_fees.items():
        if fees.get(field) != value:
            raise ValueError(f"fee_schedule.{field} changed")

    if payload.get("best_scenario_selection_allowed") is not False:
        raise ValueError("execution scenarios must remain equal-report sensitivity")
    authority = _mapping(payload.get("authority_boundary"), "authority_boundary")
    for field in (
        "broker_orders_created",
        "paper_orders_submitted",
        "live_orders_submitted",
        "level2_features_authoritative",
        "portfolio_backtest_completed",
        "policy_promotion_eligible",
    ):
        if authority.get(field) is not False:
            raise ValueError(f"authority_boundary.{field} must remain false")


__all__ = [
    "BASELINE_CONSERVATIVE_POLICY",
    "BASELINE_LIMIT_OFFSET_TICKS",
    "CONTRACT_CONTENT_SHA256",
    "CONTRACT_ID",
    "DailyEquityFees",
    "EquityFeeSchedule",
    "ExecutedEquityTrade",
    "ExecutionOutcome",
    "ExecutionStatus",
    "MarketableLimitOrder",
    "MarketableLimitPolicy",
    "OrderSide",
    "SELECTED_MANAGEMENT_CELL",
    "STRESS_POLICY",
    "STRESS_LIMIT_OFFSET_TICKS",
    "TopOfBookEvent",
    "aggregate_daily_equity_fees",
    "load_prospective_execution_contract",
    "marketable_limit_price",
    "simulate_marketable_limit_order",
    "validate_prospective_execution_contract",
]
