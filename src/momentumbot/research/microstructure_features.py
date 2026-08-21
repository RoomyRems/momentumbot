"""Deterministic, causal Level 2 and tape feature mechanics.

This module turns already-normalized canonical depth and tape events into
threshold-free measurements.  It does not classify a setup, infer trader
intent, select a feature horizon, submit an order, or consume retrospective
Ross labels.  Venue scope stays explicit and corrections fail the affected
tape window closed.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from momentumbot.research.microstructure_contract import (
    AggressorSide,
    BookSide,
    CanonicalDepthEvent,
    CanonicalTapeEvent,
    DepthAction,
    canonical_fingerprint,
)


SCHEMA_VERSION = 1
FEATURE_SET_ID = "microstructure-feature-mechanics-v0.1"
FEATURE_SET_CONTENT_SHA256 = (
    "b048e26fabd163d66297fa57faf011fbb50d9b69377101dbd04337a1cc1eab6a"
)
REGISTERED_WINDOWS_NS = (1_000_000_000, 5_000_000_000, 10_000_000_000)
BOOK_LEVEL_LIMIT = 10
V03_SUCCESS_AUDIT_CONTENT_SHA256 = (
    "66e16d7481afceaf38dacdf78c0f1974532cdb31f24cf50252ad3c914c8338a3"
)


def validate_feature_registration(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported microstructure feature schema")
    if payload.get("feature_set_id") != FEATURE_SET_ID:
        raise ValueError("unexpected microstructure feature set")
    if payload.get("artifact_type") != (
        "preregistered_threshold_free_causal_microstructure_feature_mechanics"
    ):
        raise ValueError("unexpected microstructure feature artifact type")
    if payload.get("runtime_strategy_effect") != "none_shadow_only":
        raise ValueError("feature mechanics cannot affect runtime strategy")
    for field in (
        "policy_promotion_eligible",
        "profitability_claim_eligible",
        "exact_ross_replication_claim_eligible",
        "real_data_feature_run_started",
        "provider_purchase_authorized",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must be false")

    claimed = payload.get("content_sha256")
    if claimed != FEATURE_SET_CONTENT_SHA256:
        raise ValueError("microstructure feature content hash changed")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("microstructure feature fingerprint mismatch")

    parents = payload.get("frozen_parents")
    if not isinstance(parents, Mapping):
        raise ValueError("frozen_parents must be an object")
    if parents.get("databento_replication_audit_content_sha256") != (
        V03_SUCCESS_AUDIT_CONTENT_SHA256
    ):
        raise ValueError("v0.3 replication audit parent changed")
    if parents.get("retrospective_labels_used_for_mechanics") is not False:
        raise ValueError("mechanics must remain label blind")
    if parents.get("four_case_results_used_to_select_windows_or_thresholds") is not False:
        raise ValueError("engineering cases cannot select windows or thresholds")

    horizons = payload.get("engineering_horizons")
    if not isinstance(horizons, Mapping):
        raise ValueError("engineering_horizons must be an object")
    if horizons.get("receive_time_windows_ns") != list(REGISTERED_WINDOWS_NS):
        raise ValueError("registered engineering windows changed")
    if horizons.get("threshold_or_model_selection_permitted") is not False:
        raise ValueError("horizon selection must remain prohibited")

    features = payload.get("feature_mechanics")
    if not isinstance(features, list) or len(features) != 9:
        raise ValueError("all nine parent feature families must remain registered")
    feature_ids: set[str] = set()
    for item in features:
        if not isinstance(item, Mapping):
            raise ValueError("feature mechanics entries must be objects")
        feature_id = item.get("feature_id")
        if not isinstance(feature_id, str) or not feature_id:
            raise ValueError("feature ID must be a non-empty string")
        if feature_id in feature_ids:
            raise ValueError("feature IDs must be unique")
        feature_ids.add(feature_id)
        if item.get("threshold") is not None:
            raise ValueError("feature mechanics cannot contain thresholds")

    candidate = payload.get("next_bounded_real_data_candidate")
    if not isinstance(candidate, Mapping):
        raise ValueError("next bounded candidate must be an object")
    if candidate.get("authorized") is not False:
        raise ValueError("real-data feature run is not authorized")
    if candidate.get("new_explicit_user_authorization_required") is not True:
        raise ValueError("future provider spend must require explicit authorization")


def load_feature_registration(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("microstructure feature registration root must be an object")
    validate_feature_registration(payload)
    return payload


@dataclass(frozen=True, slots=True)
class _Order:
    side: BookSide
    price_nanos: int
    size: int


@dataclass(frozen=True, slots=True)
class _Flow:
    ts_recv_ns: int
    side: BookSide
    price_nanos: int
    direction: str
    kind: str
    shares: int


@dataclass(frozen=True, slots=True)
class _Tape:
    ts_recv_ns: int
    ts_event_ns: int
    sequence: int
    price_nanos: int
    size: int
    aggressor_side: AggressorSide
    correction_or_cancel: bool


class CausalMicrostructureFeatureEngine:
    """Maintain one venue/instrument stream and emit threshold-free snapshots."""

    def __init__(self) -> None:
        self._orders: dict[int, _Order] = {}
        self._flows: deque[_Flow] = deque()
        self._tape: deque[_Tape] = deque()
        self._scope: tuple[str, str, str, str] | None = None
        self._last_receive_ns = -1
        self._initialized = False
        self._ready = False

    @property
    def book_ready(self) -> bool:
        return self._ready

    def _bind_scope(
        self,
        *,
        provider: str,
        venue: str,
        symbol: str,
        instrument_id: str,
        ts_recv_ns: int,
    ) -> None:
        scope = (provider, venue, symbol, instrument_id)
        if self._scope is None:
            self._scope = scope
        elif scope != self._scope:
            raise ValueError("microstructure feature stream scope changed")
        if ts_recv_ns < self._last_receive_ns:
            raise ValueError("merged depth/tape stream must be receive-time ordered")
        self._last_receive_ns = ts_recv_ns

    def _record_flow(
        self,
        event: CanonicalDepthEvent,
        *,
        side: BookSide,
        price_nanos: int,
        direction: str,
        kind: str,
        shares: int,
    ) -> None:
        if event.is_snapshot or shares == 0:
            return
        self._flows.append(
            _Flow(
                ts_recv_ns=event.ts_recv_ns,
                side=side,
                price_nanos=price_nanos,
                direction=direction,
                kind=kind,
                shares=shares,
            )
        )

    def _prune_history(self, ts_recv_ns: int) -> None:
        cutoff = ts_recv_ns - max(REGISTERED_WINDOWS_NS)
        while self._flows and self._flows[0].ts_recv_ns <= cutoff:
            self._flows.popleft()
        while self._tape and self._tape[0].ts_recv_ns <= cutoff:
            self._tape.popleft()

    def _remove_order_shares(
        self,
        event: CanonicalDepthEvent,
        *,
        kind: str,
    ) -> None:
        if event.order_id is None or event.price_nanos is None:
            raise ValueError("book removal requires an order ID and price")
        existing = self._orders.get(event.order_id)
        if existing is None:
            raise ValueError("book removal references an unknown order")
        if existing.side is not event.side or existing.price_nanos != event.price_nanos:
            raise ValueError("book removal identity changed")
        if event.size > existing.size:
            raise ValueError("book removal exceeds resting size")
        remaining = existing.size - event.size
        if remaining:
            self._orders[event.order_id] = _Order(
                existing.side,
                existing.price_nanos,
                remaining,
            )
        else:
            del self._orders[event.order_id]
        self._record_flow(
            event,
            side=existing.side,
            price_nanos=existing.price_nanos,
            direction="remove",
            kind=kind,
            shares=event.size,
        )

    def ingest_depth(self, event: CanonicalDepthEvent) -> None:
        self._bind_scope(
            provider=event.provider,
            venue=event.venue,
            symbol=event.symbol,
            instrument_id=event.instrument_id,
            ts_recv_ns=event.ts_recv_ns,
        )

        if event.action is DepthAction.CLEAR:
            self._orders.clear()
            self._flows.clear()
            self._tape.clear()
            self._initialized = True
            self._ready = event.is_last
            return
        if not self._initialized:
            raise ValueError("book mutation observed before an initial clear")

        if event.action is DepthAction.ADD:
            if event.order_id is None or event.price_nanos is None:
                raise ValueError("book add requires an order ID and price")
            if event.order_id in self._orders:
                raise ValueError("duplicate book add")
            self._orders[event.order_id] = _Order(
                event.side,
                event.price_nanos,
                event.size,
            )
            self._record_flow(
                event,
                side=event.side,
                price_nanos=event.price_nanos,
                direction="add",
                kind="add",
                shares=event.size,
            )
        elif event.action is DepthAction.CANCEL:
            self._remove_order_shares(event, kind="cancel")
        elif event.action is DepthAction.FILL:
            self._remove_order_shares(event, kind="fill")
        elif event.action is DepthAction.MODIFY:
            if event.order_id is None or event.price_nanos is None:
                raise ValueError("book modify requires an order ID and price")
            existing = self._orders.get(event.order_id)
            if existing is None:
                raise ValueError("book modify references an unknown order")
            if existing.side is event.side and existing.price_nanos == event.price_nanos:
                if event.size > existing.size:
                    self._record_flow(
                        event,
                        side=event.side,
                        price_nanos=event.price_nanos,
                        direction="add",
                        kind="modify",
                        shares=event.size - existing.size,
                    )
                elif event.size < existing.size:
                    self._record_flow(
                        event,
                        side=event.side,
                        price_nanos=event.price_nanos,
                        direction="remove",
                        kind="modify",
                        shares=existing.size - event.size,
                    )
            else:
                self._record_flow(
                    event,
                    side=existing.side,
                    price_nanos=existing.price_nanos,
                    direction="remove",
                    kind="modify",
                    shares=existing.size,
                )
                self._record_flow(
                    event,
                    side=event.side,
                    price_nanos=event.price_nanos,
                    direction="add",
                    kind="modify",
                    shares=event.size,
                )
            self._orders[event.order_id] = _Order(
                event.side,
                event.price_nanos,
                event.size,
            )
        elif event.action is not DepthAction.TRADE:
            raise ValueError(f"unsupported depth action: {event.action.value}")

        if event.is_last:
            self._ready = True
        self._prune_history(event.ts_recv_ns)

    def ingest_tape(self, event: CanonicalTapeEvent) -> None:
        self._bind_scope(
            provider=event.provider,
            venue=event.venue,
            symbol=event.symbol,
            instrument_id=event.instrument_id,
            ts_recv_ns=event.ts_recv_ns,
        )
        if not self._initialized:
            raise ValueError("tape observed before an initial book clear")
        self._tape.append(
            _Tape(
                ts_recv_ns=event.ts_recv_ns,
                ts_event_ns=event.ts_event_ns,
                sequence=event.sequence,
                price_nanos=event.price_nanos,
                size=event.size,
                aggressor_side=event.aggressor_side,
                correction_or_cancel=event.correction_or_cancel,
            )
        )
        self._prune_history(event.ts_recv_ns)

    def _levels(self, side: BookSide) -> list[dict[str, int]]:
        levels: dict[int, list[int]] = defaultdict(lambda: [0, 0])
        for order in self._orders.values():
            if order.side is side:
                levels[order.price_nanos][0] += order.size
                levels[order.price_nanos][1] += 1
        prices = sorted(levels, reverse=side is BookSide.BID)[:BOOK_LEVEL_LIMIT]
        return [
            {
                "price_nanos": price,
                "displayed_size": levels[price][0],
                "order_count": levels[price][1],
            }
            for price in prices
        ]

    @staticmethod
    def _flow_counts(flows: Iterable[_Flow], side: BookSide) -> dict[str, int]:
        result = {
            "add_event_count": 0,
            "added_shares": 0,
            "cancel_event_count": 0,
            "canceled_shares": 0,
            "fill_event_count": 0,
            "filled_shares": 0,
            "modify_add_event_count": 0,
            "modified_added_shares": 0,
            "modify_remove_event_count": 0,
            "modified_removed_shares": 0,
        }
        for flow in flows:
            if flow.side is not side:
                continue
            if flow.kind == "add":
                result["add_event_count"] += 1
                result["added_shares"] += flow.shares
            elif flow.kind == "cancel":
                result["cancel_event_count"] += 1
                result["canceled_shares"] += flow.shares
            elif flow.kind == "fill":
                result["fill_event_count"] += 1
                result["filled_shares"] += flow.shares
            elif flow.direction == "add":
                result["modify_add_event_count"] += 1
                result["modified_added_shares"] += flow.shares
            else:
                result["modify_remove_event_count"] += 1
                result["modified_removed_shares"] += flow.shares
        return result

    @staticmethod
    def _replenishment(flows: Iterable[_Flow], side: BookSide) -> dict[str, int]:
        outstanding: dict[int, deque[list[object]]] = defaultdict(deque)
        result = {
            "replenishment_event_count": 0,
            "replenished_shares": 0,
            "replenished_after_fill_shares": 0,
            "replenished_after_nonexecution_removal_shares": 0,
        }
        for flow in flows:
            if flow.side is not side:
                continue
            queue = outstanding[flow.price_nanos]
            if flow.direction == "remove":
                queue.append([flow.kind, flow.shares])
                continue
            remaining = flow.shares
            matched = 0
            while remaining and queue:
                kind, shares = queue[0]
                consumed = min(remaining, int(shares))
                remaining -= consumed
                matched += consumed
                result["replenished_shares"] += consumed
                if kind == "fill":
                    result["replenished_after_fill_shares"] += consumed
                else:
                    result["replenished_after_nonexecution_removal_shares"] += consumed
                shares = int(shares) - consumed
                if shares:
                    queue[0][1] = shares
                else:
                    queue.popleft()
            if matched:
                result["replenishment_event_count"] += 1
        return result

    @staticmethod
    def _side_tape(
        trades: list[_Tape],
        side: AggressorSide,
        window_ns: int,
    ) -> dict[str, object]:
        selected = [trade for trade in trades if trade.aggressor_side is side]
        if not selected:
            return {
                "event_count": 0,
                "shares": 0,
                "notional_price_nanos_shares": 0,
                "first_price_nanos": None,
                "last_price_nanos": None,
                "minimum_price_nanos": None,
                "maximum_price_nanos": None,
                "signed_first_to_last_progress_nanos": None,
                "positive_progress_nanos": None,
                "event_rate_numerator": 0,
                "share_rate_numerator": 0,
                "rate_denominator_ns": window_ns,
            }
        first = selected[0].price_nanos
        last = selected[-1].price_nanos
        progress = last - first
        return {
            "event_count": len(selected),
            "shares": sum(trade.size for trade in selected),
            "notional_price_nanos_shares": sum(
                trade.price_nanos * trade.size for trade in selected
            ),
            "first_price_nanos": first,
            "last_price_nanos": last,
            "minimum_price_nanos": min(trade.price_nanos for trade in selected),
            "maximum_price_nanos": max(trade.price_nanos for trade in selected),
            "signed_first_to_last_progress_nanos": progress,
            "positive_progress_nanos": max(0, progress),
            "event_rate_numerator": len(selected),
            "share_rate_numerator": sum(trade.size for trade in selected),
            "rate_denominator_ns": window_ns,
        }

    @staticmethod
    def _breakout_context(
        trades: list[_Tape],
        breakout_level_nanos: int | None,
    ) -> dict[str, object]:
        if breakout_level_nanos is None:
            return {"available": False, "unavailable_reason": "breakout_level_not_supplied"}
        if not trades:
            return {"available": False, "unavailable_reason": "no_eligible_tape_events"}
        buy_at_or_above = [
            trade
            for trade in trades
            if trade.aggressor_side is AggressorSide.BUY
            and trade.price_nanos >= breakout_level_nanos
        ]
        first_cross = buy_at_or_above[0].ts_recv_ns if buy_at_or_above else None
        after_cross = (
            [trade for trade in trades if trade.ts_recv_ns >= first_cross]
            if first_cross is not None
            else []
        )
        return {
            "available": True,
            "unavailable_reason": None,
            "breakout_level_nanos": breakout_level_nanos,
            "buy_event_count_at_or_above": len(buy_at_or_above),
            "buy_shares_at_or_above": sum(trade.size for trade in buy_at_or_above),
            "first_buy_at_or_above_ts_recv_ns": first_cross,
            "maximum_trade_price_nanos": max(trade.price_nanos for trade in trades),
            "last_trade_price_nanos": trades[-1].price_nanos,
            "maximum_minus_breakout_nanos": (
                max(trade.price_nanos for trade in trades) - breakout_level_nanos
            ),
            "last_minus_breakout_nanos": trades[-1].price_nanos - breakout_level_nanos,
            "post_cross_trade_event_count": len(after_cross),
            "post_cross_sell_shares_below_breakout": sum(
                trade.size
                for trade in after_cross
                if trade.aggressor_side is AggressorSide.SELL
                and trade.price_nanos < breakout_level_nanos
            ),
        }

    @staticmethod
    def _depth_walk(
        levels: list[dict[str, int]],
        *,
        quantity: int,
        direction: str,
    ) -> dict[str, object]:
        remaining = quantity
        notional = 0
        worst_price: int | None = None
        levels_touched = 0
        for level in levels:
            take = min(remaining, level["displayed_size"])
            if take:
                notional += take * level["price_nanos"]
                worst_price = level["price_nanos"]
                levels_touched += 1
                remaining -= take
            if remaining == 0:
                break
        filled = quantity - remaining
        best_price = levels[0]["price_nanos"] if levels else None
        return {
            "direction": direction,
            "requested_quantity": quantity,
            "displayed_filled_quantity": filled,
            "displayed_unfilled_quantity": remaining,
            "complete_in_covered_depth": remaining == 0,
            "levels_touched": levels_touched,
            "best_price_nanos": best_price,
            "worst_price_nanos": worst_price,
            "notional_price_nanos_shares": notional,
            "average_price_numerator": notional if filled else None,
            "average_price_denominator_shares": filled if filled else None,
            "worst_price_slippage_nanos": (
                abs(worst_price - best_price)
                if worst_price is not None and best_price is not None
                else None
            ),
            "queue_position_resolved": False,
            "hidden_liquidity_assumed": False,
        }

    def snapshot(
        self,
        *,
        as_of_ts_recv_ns: int | None = None,
        hypothetical_order_sizes: Iterable[int] = (),
        breakout_level_nanos: int | None = None,
    ) -> dict[str, object]:
        if self._scope is None or self._last_receive_ns < 0:
            raise ValueError("cannot snapshot before the first canonical event")
        as_of = self._last_receive_ns if as_of_ts_recv_ns is None else as_of_ts_recv_ns
        if isinstance(as_of, bool) or not isinstance(as_of, int) or as_of < self._last_receive_ns:
            raise ValueError("snapshot time must be an integer at or after the latest event")
        if breakout_level_nanos is not None and (
            isinstance(breakout_level_nanos, bool)
            or not isinstance(breakout_level_nanos, int)
            or breakout_level_nanos <= 0
        ):
            raise ValueError("breakout level must be a positive integer price")

        order_sizes = list(hypothetical_order_sizes)
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in order_sizes
        ):
            raise ValueError("hypothetical order sizes must be positive integers")
        if len(order_sizes) != len(set(order_sizes)):
            raise ValueError("hypothetical order sizes must be unique")
        order_sizes.sort()

        provider, venue, symbol, instrument_id = self._scope
        bids = self._levels(BookSide.BID) if self._ready else []
        asks = self._levels(BookSide.ASK) if self._ready else []
        two_sided = bool(bids and asks)
        book: dict[str, object] = {
            "available": self._ready,
            "unavailable_reason": None if self._ready else "book_not_ready",
            "two_sided": two_sided,
            "covered_levels_per_side": BOOK_LEVEL_LIMIT,
            "bids": bids,
            "asks": asks,
        }
        if two_sided:
            bid_depth = sum(level["displayed_size"] for level in bids)
            ask_depth = sum(level["displayed_size"] for level in asks)
            spread = asks[0]["price_nanos"] - bids[0]["price_nanos"]
            book.update(
                {
                    "best_bid_price_nanos": bids[0]["price_nanos"],
                    "best_ask_price_nanos": asks[0]["price_nanos"],
                    "spread_nanos": spread,
                    "spread_bps_numerator": spread * 20_000,
                    "spread_bps_denominator": (
                        bids[0]["price_nanos"] + asks[0]["price_nanos"]
                    ),
                    "bid_depth_shares": bid_depth,
                    "ask_depth_shares": ask_depth,
                    "depth_imbalance_numerator": bid_depth - ask_depth,
                    "depth_imbalance_denominator": bid_depth + ask_depth,
                }
            )
        else:
            book.update(
                {
                    "best_bid_price_nanos": bids[0]["price_nanos"] if bids else None,
                    "best_ask_price_nanos": asks[0]["price_nanos"] if asks else None,
                    "spread_nanos": None,
                    "spread_bps_numerator": None,
                    "spread_bps_denominator": None,
                    "bid_depth_shares": (
                        sum(level["displayed_size"] for level in bids)
                        if self._ready
                        else None
                    ),
                    "ask_depth_shares": (
                        sum(level["displayed_size"] for level in asks)
                        if self._ready
                        else None
                    ),
                    "depth_imbalance_numerator": None,
                    "depth_imbalance_denominator": None,
                }
            )

        windows: list[dict[str, object]] = []
        for window_ns in REGISTERED_WINDOWS_NS:
            start = as_of - window_ns
            flows = [flow for flow in self._flows if start < flow.ts_recv_ns <= as_of]
            all_tape = [trade for trade in self._tape if start < trade.ts_recv_ns <= as_of]
            corrections = sum(trade.correction_or_cancel for trade in all_tape)
            eligible_tape = [trade for trade in all_tape if not trade.correction_or_cancel]
            tape_available = corrections == 0
            side_tape = {
                side.value: self._side_tape(eligible_tape, side, window_ns)
                for side in AggressorSide
            }
            tape_payload: dict[str, object] = {
                "available": tape_available,
                "unavailable_reason": (
                    None if tape_available else "correction_or_cancel_in_window"
                ),
                "correction_or_cancel_count": corrections,
                "by_aggressor_side": side_tape,
                "net_buy_minus_sell_shares": (
                    side_tape["buy"]["shares"] - side_tape["sell"]["shares"]
                ),
            }
            buy_prices = {
                trade.price_nanos
                for trade in eligible_tape
                if trade.aggressor_side is AggressorSide.BUY
            }
            sell_prices = {
                trade.price_nanos
                for trade in eligible_tape
                if trade.aggressor_side is AggressorSide.SELL
            }
            sweep = {
                "available": tape_available,
                "unavailable_reason": tape_payload["unavailable_reason"],
                "buy_distinct_trade_price_count": len(buy_prices),
                "sell_distinct_trade_price_count": len(sell_prices),
                "buy_observed_price_span_nanos": (
                    max(buy_prices) - min(buy_prices) if buy_prices else None
                ),
                "sell_observed_price_span_nanos": (
                    max(sell_prices) - min(sell_prices) if sell_prices else None
                ),
                "consumed_book_levels_claimed": False,
            }
            impact = {
                "available": tape_available and bool(eligible_tape),
                "unavailable_reason": (
                    tape_payload["unavailable_reason"]
                    if not tape_available
                    else (None if eligible_tape else "no_eligible_tape_events")
                ),
                "buy_executed_shares": side_tape["buy"]["shares"],
                "sell_executed_shares": side_tape["sell"]["shares"],
                "unknown_executed_shares": side_tape["unknown"]["shares"],
                "buy_positive_progress_nanos": side_tape["buy"][
                    "positive_progress_nanos"
                ],
                "sell_positive_progress_nanos": (
                    max(
                        0,
                        -int(side_tape["sell"]["signed_first_to_last_progress_nanos"]),
                    )
                    if side_tape["sell"]["signed_first_to_last_progress_nanos"]
                    is not None
                    else None
                ),
                "buy_volume_per_progress_numerator_shares": side_tape["buy"]["shares"],
                "buy_volume_per_progress_denominator_nanos": side_tape["buy"][
                    "positive_progress_nanos"
                ],
                "interpretation": "measurement_only_hidden_liquidity_not_proven",
            }
            windows.append(
                {
                    "window_ns": window_ns,
                    "start_exclusive_ts_recv_ns": start,
                    "end_inclusive_ts_recv_ns": as_of,
                    "book_flow": {
                        "available": self._ready,
                        "unavailable_reason": None if self._ready else "book_not_ready",
                        "bid": self._flow_counts(flows, BookSide.BID),
                        "ask": self._flow_counts(flows, BookSide.ASK),
                    },
                    "displayed_replenishment": {
                        "available": self._ready,
                        "unavailable_reason": None if self._ready else "book_not_ready",
                        "bid": self._replenishment(flows, BookSide.BID),
                        "ask": self._replenishment(flows, BookSide.ASK),
                        "matching_rule": "same_price_same_side_fifo_within_window",
                    },
                    "signed_trade_velocity": tape_payload,
                    "observed_trade_price_sweep": sweep,
                    "execution_price_impact": impact,
                    "breakout_progress_context": (
                        self._breakout_context(eligible_tape, breakout_level_nanos)
                        if tape_available
                        else {
                            "available": False,
                            "unavailable_reason": "correction_or_cancel_in_window",
                        }
                    ),
                }
            )

        depth_walks: list[dict[str, object]] = []
        for quantity in order_sizes:
            if not self._ready:
                depth_walks.append(
                    {
                        "requested_quantity": quantity,
                        "available": False,
                        "unavailable_reason": "book_not_ready",
                    }
                )
                continue
            depth_walks.extend(
                [
                    {
                        "available": True,
                        "unavailable_reason": None,
                        **self._depth_walk(
                            asks,
                            quantity=quantity,
                            direction="buy",
                        ),
                    },
                    {
                        "available": True,
                        "unavailable_reason": None,
                        **self._depth_walk(
                            bids,
                            quantity=quantity,
                            direction="sell",
                        ),
                    },
                ]
            )

        payload: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "feature_set_id": FEATURE_SET_ID,
            "as_of_ts_recv_ns": as_of,
            "source_scope": {
                "provider": provider,
                "venue": venue,
                "symbol": symbol,
                "instrument_id": instrument_id,
                "consolidated_national_depth": False,
            },
            "registered_windows_ns": list(REGISTERED_WINDOWS_NS),
            "window_selection_rule": "start_exclusive_end_inclusive_receive_time",
            "book": book,
            "windows": windows,
            "depth_constrained_slippage": depth_walks,
            "thresholds_applied": False,
            "retrospective_labels_loaded": False,
            "intent_or_spoofing_classified": False,
            "runtime_authority": "none_shadow_only",
        }
        payload["content_sha256"] = canonical_fingerprint(payload)
        return payload
