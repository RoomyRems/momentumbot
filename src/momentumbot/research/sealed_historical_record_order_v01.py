"""Provider-free historical MBP-1 record-order adapter v0.1.

Native receive times and sequence numbers are evidence, not unique row IDs.
The separate ordinal records the original position within one exact request.
This module neither acquires inputs nor passes an acquisition/management gate.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_FLOOR
from typing import Mapping, Sequence

from momentumbot.research import prospective_market_input_capture as capture
from momentumbot.research.prospective_market_input_acquisition import _normalize_store
from momentumbot.research.microstructure_contract import canonical_fingerprint
from momentumbot.research.sealed_historical_execution_quote_v01 import require_exact, seal

# These names are deliberately the frozen dependencies of the two copied
# mechanical blocks below. Registration checks their ASTs against the parents.
from momentumbot.research.prospective_market_input_capture import (
    PRE_DECISION_QUOTE_NS, POST_DECISION_CAPTURE_NS, PRICE_SCALE,
    CapturedStatusEvent, _utc_midnight_ns,
)
from momentumbot.research.execution_realism import (
    TopOfBookEvent, MarketableLimitOrder, MarketableLimitPolicy, ExecutionOutcome,
    ExecutionStatus, _NS_PER_MS, _contra, _crosses_limit,
)

CONTRACT_ID = "sealed-historical-record-order-adapter-v0.1"
QUOTE_FIELDS = frozenset({"symbol", "ts_recv_ns", "sequence", "bid_px_nanos",
                          "bid_size", "ask_px_nanos", "ask_size"})
ORDER_FIELDS = frozenset({"source_request_sha256", "source_record_index"})


def _source(sha: str, index: int) -> None:
    if not isinstance(sha, str) or capture._SHA256.fullmatch(sha) is None:
        raise ValueError("source_request_sha256 must be an exact SHA-256")
    capture._integer(index, "source_record_index")


@dataclass(frozen=True, slots=True)
class RecordOrderedQuote(capture.CapturedQuoteEvent):
    source_request_sha256: str
    source_record_index: int

    def __post_init__(self) -> None:
        capture.CapturedQuoteEvent.__post_init__(self)
        _source(self.source_request_sha256, self.source_record_index)


@dataclass(frozen=True, slots=True, kw_only=True)
class RecordOrderedTopOfBook(TopOfBookEvent):
    source_request_sha256: str
    source_record_index: int

    def __post_init__(self) -> None:
        TopOfBookEvent.__post_init__(self)
        _source(self.source_request_sha256, self.source_record_index)


def _request(request: Mapping, schema: str) -> str:
    if set(request) != {"request_id", "trading_date", "dataset", "schema", "symbols",
                        "stype_in", "start_ns", "end_ns", "end_exclusive"}:
        raise ValueError("exact request fields required")
    if (request["dataset"] != capture.DATASET or request["schema"] != schema
            or request["stype_in"] != capture.STYPE_IN or request["end_exclusive"] is not True):
        raise ValueError("request scope differs")
    symbols = request["symbols"]
    if not isinstance(symbols, list) or len(symbols) != 1:
        raise ValueError("one exact request symbol required")
    symbol = capture._symbol(symbols[0])
    day = request["trading_date"]
    if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
        raise ValueError("canonical request date required")
    if request["request_id"] != f"{day}-{symbol}-{schema}":
        raise ValueError("request ID differs")
    start = capture._integer(request["start_ns"], "request.start_ns", minimum=1)
    end = capture._integer(request["end_ns"], "request.end_ns", minimum=1)
    midnight = _utc_midnight_ns(day)
    if not midnight <= start < end <= midnight + 86_400_000_000_000:
        raise ValueError("request must stay in its exact UTC date")
    if schema == "status" and start != midnight:
        raise ValueError("status request must start at UTC midnight")
    return canonical_fingerprint(request)


def _ordered(events: Sequence, symbol: str, source_sha: str,
             *, contiguous: bool) -> tuple:
    result = tuple(events)
    previous_key = None
    previous_index = None
    for position, event in enumerate(result):
        if event.symbol != symbol or event.source_request_sha256 != source_sha:
            raise ValueError("record source request or symbol differs")
        key = (event.ts_recv_ns, event.sequence)
        index = event.source_record_index
        if previous_key is not None and key < previous_key:
            raise ValueError("native receive-time/sequence order reversed")
        if previous_index is not None and index <= previous_index:
            raise ValueError("source record order reversed or duplicated")
        if contiguous and index != position:
            raise ValueError("complete tape ordinals must be contiguous from zero")
        previous_key, previous_index = key, index
    return result


def quote_events(records: Sequence[Mapping], request: Mapping) -> tuple[RecordOrderedQuote, ...]:
    """Validate a complete per-request tape, never sorting or deduplicating it."""
    source_sha = _request(request, "mbp-1")
    events = []
    for row in records:
        if not isinstance(row, Mapping) or set(row) != QUOTE_FIELDS | ORDER_FIELDS:
            raise ValueError("record-ordered quote fields differ")
        event = RecordOrderedQuote(**row)
        if not request["start_ns"] <= event.ts_recv_ns < request["end_ns"]:
            raise ValueError("quote outside exact request")
        events.append(event)
    if not events:
        raise ValueError("missing exact request records")
    return _ordered(events, request["symbols"][0], source_sha, contiguous=True)


def status_events(records: Sequence[Mapping], request: Mapping) -> tuple[CapturedStatusEvent, ...]:
    """Keep the frozen status vocabulary and receive-time ambiguity rules."""
    _request(request, "status")
    events = capture._status_events(records)
    if not events:
        raise ValueError("missing exact request records")
    for event in events:
        if event.symbol != request["symbols"][0] or not request["start_ns"] <= event.ts_recv_ns < request["end_ns"]:
            raise ValueError("status outside exact request or symbol")
    return events


def normalize_store(store, request: Mapping) -> list[dict]:
    """Preserve the frozen field/metadata conversion; add quote provenance only."""
    schema = request.get("schema")
    if schema not in capture.SCHEMAS:
        raise ValueError("unsupported record-order schema")
    source_sha = _request(request, schema)
    records = _normalize_store(store, request)
    if schema == "mbp-1":
        records = [dict(row, source_request_sha256=source_sha, source_record_index=i)
                   for i, row in enumerate(records)]
        quote_events(records, request)
    else:
        status_events(records, request)
    return records


@dataclass(frozen=True, slots=True)
class WindowIdentity:
    """Mechanical identity; the later historical composer must bind the frozen plan."""
    opportunity_id: str
    trading_date: str
    symbol: str
    decision_ts_ns: int

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity_id, str) or not self.opportunity_id.strip():
            raise ValueError("opportunity ID required")
        capture._symbol(self.symbol)
        if date.fromisoformat(self.trading_date).isoformat() != self.trading_date:
            raise ValueError("canonical opportunity date required")
        capture._integer(self.decision_ts_ns, "decision_ts_ns", minimum=1)


def capture_window(opportunity: WindowIdentity, quote_request: Mapping,
                   quote_records: Sequence[Mapping], status_request: Mapping,
                   status_records: Sequence[Mapping]) -> dict:
    """Project one causal window offline; this is not an acquisition receipt."""
    quotes = quote_events(quote_records, quote_request)
    statuses = status_events(status_records, status_request)
    start = opportunity.decision_ts_ns - PRE_DECISION_QUOTE_NS
    end = opportunity.decision_ts_ns + POST_DECISION_CAPTURE_NS
    for request in (quote_request, status_request):
        if (request["symbols"] != [opportunity.symbol]
                or request["trading_date"] != opportunity.trading_date
                or not request["start_ns"] <= start < end < request["end_ns"]):
            raise ValueError("window is not covered by its exact source requests")
    if quote_request["end_ns"] != status_request["end_ns"]:
        raise ValueError("quote/status request ends differ")
    result = _capture_window(opportunity, {opportunity.symbol: quotes},
                             {opportunity.symbol: statuses})
    result.update({
        "adapter_contract_id": CONTRACT_ID,
        "quote_source_request_sha256": canonical_fingerprint(quote_request),
        "status_source_request_sha256": canonical_fingerprint(status_request),
        "quote_tape_content_sha256": canonical_fingerprint(quote_records),
        "status_tape_content_sha256": canonical_fingerprint(status_records),
        "acquisition_gate_passed": False,
        "historical_execution_authorized": False,
    })
    return seal(result)


def validate_capture_window(payload: Mapping, opportunity: WindowIdentity,
                            quote_request: Mapping, quote_records: Sequence[Mapping],
                            status_request: Mapping, status_records: Sequence[Mapping]) -> None:
    """Rebuild from the bound complete tapes, not merely a rehashed report."""
    require_exact(payload, capture_window(opportunity, quote_request, quote_records,
                                          status_request, status_records), "causal ordered window")


def top_of_book_events(payload: Mapping, opportunity: WindowIdentity,
                       quote_request: Mapping, quote_records: Sequence[Mapping],
                       status_request: Mapping, status_records: Sequence[Mapping]) -> tuple[RecordOrderedTopOfBook, ...]:
    validate_capture_window(payload, opportunity, quote_request, quote_records,
                            status_request, status_records)
    events = tuple(RecordOrderedTopOfBook(**{k: row[k] for k in (
        "symbol", "ts_recv_ns", "sequence", "bid_price", "bid_size", "ask_price",
        "ask_size", "halted", "source_request_sha256", "source_record_index")})
        for row in payload["quotes"])
    return _validate_record_order_stream(opportunity.symbol, events)


def _validate_record_order_stream(symbol: str, quotes: Sequence[RecordOrderedTopOfBook]) -> tuple[RecordOrderedTopOfBook, ...]:
    events = tuple(quotes)
    if any(type(event) is not RecordOrderedTopOfBook for event in events):
        raise ValueError("execution adapter requires explicit record-order provenance")
    if not events:
        return events
    # Filtering a causal window may leave ordinal gaps; it must never renumber.
    return _ordered(events, symbol, events[0].source_request_sha256, contiguous=False)


# Frozen capture loop with only the two explicit quote provenance fields added.
def _capture_window(opportunity, quotes_by_symbol, status_by_symbol) -> dict:
    opportunities = (opportunity,)
    captures = []
    for opportunity in opportunities:
        start = opportunity.decision_ts_ns - PRE_DECISION_QUOTE_NS
        end = opportunity.decision_ts_ns + POST_DECISION_CAPTURE_NS
        status_request_start = _utc_midnight_ns(opportunity.trading_date)
        symbol_statuses = [
            event
            for event in status_by_symbol.get(opportunity.symbol, [])
            if status_request_start <= event.ts_recv_ns <= end
        ]
        status_times = [event.ts_recv_ns for event in symbol_statuses]
        status_time_set = set(status_times)
        initial_index = bisect_right(status_times, start) - 1
        initial = symbol_statuses[initial_index] if initial_index >= 0 else None
        status_window = [
            event
            for event in symbol_statuses
            if start < event.ts_recv_ns <= end
        ]
        status_known = initial is not None and initial.is_trading in {"Y", "N"}
        unknown_seen = any(event.is_trading == "~" for event in status_window)
        status_complete = status_known and not unknown_seen

        usable_quotes: list[dict[str, object]] = []
        unusable_quote_count = 0
        for quote in quotes_by_symbol.get(opportunity.symbol, []):
            if not start <= quote.ts_recv_ns <= end:
                continue
            if not quote.usable:
                unusable_quote_count += 1
                continue
            if quote.ts_recv_ns in status_time_set:
                unusable_quote_count += 1
                continue
            quote_status_index = bisect_right(status_times, quote.ts_recv_ns) - 1
            current_status = (
                symbol_statuses[quote_status_index]
                if quote_status_index >= 0
                else None
            )
            if current_status is None or current_status.is_trading == "~":
                unusable_quote_count += 1
                continue
            usable_quotes.append(
                {
                    "symbol": quote.symbol,
                    "ts_recv_ns": quote.ts_recv_ns,
                    "sequence": quote.sequence,
                    "source_request_sha256": quote.source_request_sha256,
                    "source_record_index": quote.source_record_index,
                    "bid_price": format(
                        Decimal(quote.bid_px_nanos) / PRICE_SCALE,
                        "f",
                    ),
                    "bid_size": quote.bid_size,
                    "ask_price": format(
                        Decimal(quote.ask_px_nanos) / PRICE_SCALE,
                        "f",
                    ),
                    "ask_size": quote.ask_size,
                        "halted": current_status.is_trading != "Y",
                        "status_ts_recv_ns": current_status.ts_recv_ns,
                        "status_record_index": current_status.record_index,
                        "status_action": current_status.action,
                }
            )

        if not status_complete:
            unusable_quote_count += len(usable_quotes)
            usable_quotes = []

        captures.append(
            {
                "opportunity_id": opportunity.opportunity_id,
                "trading_date": opportunity.trading_date,
                "symbol": opportunity.symbol,
                "decision_ts_ns": opportunity.decision_ts_ns,
                "window_start_ns": start,
                "window_end_ns": end,
                "initial_status": (
                    None
                    if initial is None
                    else {
                        "ts_recv_ns": initial.ts_recv_ns,
                        "record_index": initial.record_index,
                        "action": initial.action,
                        "is_trading": initial.is_trading,
                    }
                ),
                "status_changes": [
                    {
                        "ts_recv_ns": event.ts_recv_ns,
                        "record_index": event.record_index,
                        "action": event.action,
                        "is_trading": event.is_trading,
                    }
                    for event in status_window
                ],
                "status_coverage_complete": status_complete,
                "usable_quote_count": len(usable_quotes),
                "unusable_or_status_unknown_quote_count": unusable_quote_count,
                "quotes": usable_quotes,
                "capture_status": (
                    "complete"
                    if status_complete
                    else "unavailable_status_not_causally_known"
                ),
            }
        )
    return captures[0]


# Frozen execution body; only the ordering validator is versioned.
def simulate_record_order_limit_order(
    order: MarketableLimitOrder,
    quotes: Sequence[RecordOrderedTopOfBook],
    policy: MarketableLimitPolicy,
) -> ExecutionOutcome:
    """Simulate one immediate marketable-limit attempt without queue credit.

    The last quote at or before arrival may be used only if it is fresh.  Later
    full quote states may make the order marketable until cancellation is
    acknowledged.  The first eligible displayed state is haircut once; later
    states cannot refill the same attempt.
    """
    events = _validate_record_order_stream(order.symbol, quotes)
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
