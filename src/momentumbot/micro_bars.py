"""Build research micro-bars from historical SIP trade prints.

Alpaca publishes minute-bar aggregation rules based on SIP trade conditions.
For ten-second research bars we apply the *minute* price/volume eligibility
rules to each trade and then aggregate into ten-second buckets. This is not an
exchange-published bar; provenance must therefore identify it as a derived bar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

# Minute-bar semantics from Alpaca's Market Data FAQ. Values are
# (updates_price, updates_volume). Context-dependent codes are handled below.
_ALWAYS: dict[str, tuple[bool, bool]] = {
    "": (True, True),
    " ": (True, True),
    "@": (True, True),
    "A": (True, True),
    "C": (False, True),
    "D": (True, True),
    "E": (True, True),
    "F": (True, True),
    "G": (False, True),
    "H": (False, True),
    "I": (False, True),
    "K": (True, True),
    "L": (True, True),
    "M": (False, False),
    "N": (False, True),
    "O": (True, True),
    "P": (False, True),
    "Q": (False, False),
    "R": (False, True),
    "T": (True, True),
    "U": (False, True),
    "V": (False, True),
    "W": (False, True),
    "X": (True, True),
    "Y": (True, True),
    "Z": (False, True),
    "4": (False, True),
    "5": (True, True),
    "6": (True, True),
    "7": (False, True),
    "9": (False, False),
}


@dataclass(frozen=True, slots=True)
class TradeEligibility:
    updates_price: bool
    updates_volume: bool
    unknown_conditions: tuple[str, ...] = ()


def minute_trade_eligibility(tape: str | None, conditions: Iterable[str]) -> TradeEligibility:
    """Return Alpaca-minute-style eligibility for a SIP trade.

    Multiple conditions use the strictest rule. Unknown condition codes fail
    closed for both price and volume so research cannot silently invent bars.
    Code B is tape-dependent: Nasdaq tape C is a bunched trade (eligible),
    while NYSE tapes A/B are average-price trades (price-ineligible).
    """
    tape = (tape or "").upper()
    values = tuple(str(value) for value in conditions)
    if not values:
        return TradeEligibility(True, True)

    price_ok = True
    volume_ok = True
    unknown: list[str] = []
    for code in values:
        if code == "B":
            rule = (True, True) if tape == "C" else (False, True)
        elif code in _ALWAYS:
            rule = _ALWAYS[code]
        else:
            unknown.append(code)
            rule = (False, False)
        price_ok = price_ok and rule[0]
        volume_ok = volume_ok and rule[1]
    return TradeEligibility(price_ok, volume_ok, tuple(sorted(set(unknown))))


def aggregate_trade_bars(trades: pd.DataFrame, frequency: str = "10s") -> pd.DataFrame:
    """Aggregate normalized trade prints into derived OHLCV micro-bars."""
    required = {"price", "size", "conditions", "tape"}
    missing = sorted(required - set(trades.columns))
    if missing:
        raise ValueError(f"missing trade columns: {missing}")
    if not isinstance(trades.index, pd.DatetimeIndex):
        raise TypeError("trade index must be a DatetimeIndex")
    if trades.index.tz is None:
        raise ValueError("trade timestamps must be timezone-aware")
    if trades.empty:
        return pd.DataFrame(
            columns=["open", "high", "low", "close", "volume", "trade_count", "vwap", "unknown_condition_count"]
        ).set_axis(pd.DatetimeIndex([], name="timestamp", tz="UTC"))

    buckets: dict[pd.Timestamp, dict[str, object]] = {}
    for timestamp, row in trades.sort_index().iterrows():
        bucket = timestamp.floor(frequency)
        state = buckets.setdefault(
            bucket,
            {
                "open": None,
                "high": None,
                "low": None,
                "close": None,
                "volume": 0,
                "trade_count": 0,
                "vwap_numerator": 0.0,
                "vwap_volume": 0,
                "unknown_conditions": set(),
            },
        )
        eligibility = minute_trade_eligibility(row.get("tape"), row.get("conditions") or ())
        state["unknown_conditions"].update(eligibility.unknown_conditions)
        price = float(row["price"])
        size = int(row["size"])
        if eligibility.updates_volume:
            state["volume"] += size
            state["trade_count"] += 1
        if eligibility.updates_price:
            if state["open"] is None:
                state["open"] = price
            state["high"] = price if state["high"] is None else max(float(state["high"]), price)
            state["low"] = price if state["low"] is None else min(float(state["low"]), price)
            state["close"] = price
            if eligibility.updates_volume:
                state["vwap_numerator"] += price * size
                state["vwap_volume"] += size

    rows: list[dict[str, object]] = []
    index: list[pd.Timestamp] = []
    for timestamp in sorted(buckets):
        state = buckets[timestamp]
        if state["open"] is None or int(state["volume"]) <= 0:
            continue
        vwap_volume = int(state["vwap_volume"])
        rows.append(
            {
                "open": float(state["open"]),
                "high": float(state["high"]),
                "low": float(state["low"]),
                "close": float(state["close"]),
                "volume": int(state["volume"]),
                "trade_count": int(state["trade_count"]),
                "vwap": float(state["vwap_numerator"]) / vwap_volume if vwap_volume else float("nan"),
                "unknown_condition_count": len(state["unknown_conditions"]),
            }
        )
        index.append(timestamp)
    return pd.DataFrame(rows, index=pd.DatetimeIndex(index, name="timestamp"))
