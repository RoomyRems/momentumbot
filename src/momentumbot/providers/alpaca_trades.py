"""Historical Alpaca SIP trade-print ingestion.

This module is intentionally separate from the minute-bar client while the
micro-timeframe research layer is validated. It performs read-only historical
market-data requests and has no brokerage/order functionality.
"""

from __future__ import annotations

import urllib.parse
from datetime import date, datetime
from typing import Any

import pandas as pd

from .alpaca import DATA_BASE, AlpacaDataClient
from .http_json import get_json

TRADE_COLUMNS = ("price", "size", "exchange", "conditions", "trade_id", "tape")
_TRADE_RENAME = {
    "p": "price",
    "s": "size",
    "x": "exchange",
    "c": "conditions",
    "i": "trade_id",
    "z": "tape",
}


def trade_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Normalize Alpaca historical trades into a timestamp-indexed frame."""
    if not rows:
        empty = pd.DataFrame(columns=list(TRADE_COLUMNS))
        empty.index = pd.DatetimeIndex([], name="timestamp", tz="UTC")
        return empty
    frame = pd.DataFrame(rows).rename(columns=_TRADE_RENAME)
    if "t" not in frame:
        raise ValueError("Alpaca trade payload is missing timestamps")
    frame["timestamp"] = pd.to_datetime(frame["t"], utc=True)
    for column in TRADE_COLUMNS:
        if column not in frame:
            frame[column] = None
    frame["price"] = pd.to_numeric(frame["price"], errors="raise")
    frame["size"] = pd.to_numeric(frame["size"], errors="raise").astype("int64")
    frame["conditions"] = frame["conditions"].apply(
        lambda value: tuple(value) if isinstance(value, list) else tuple()
    )
    return frame.set_index("timestamp")[list(TRADE_COLUMNS)].sort_index()


def historical_trades(
    client: AlpacaDataClient,
    symbol: str,
    *,
    start: datetime,
    end: datetime,
    feed: str = "sip",
    asof: date | str | None = None,
    limit: int = 10_000,
) -> pd.DataFrame:
    """Fetch all historical trade prints for one symbol with pagination."""
    symbol = str(symbol).strip().upper()
    if not symbol:
        raise ValueError("symbol is required")
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("trade bounds must be timezone-aware")
    if start >= end:
        raise ValueError("trade start must precede trade end")
    if not 1 <= limit <= 10_000:
        raise ValueError("Alpaca trade limit must be in [1, 10000]")

    rows: list[dict[str, Any]] = []
    page_token: str | None = None
    seen_tokens: set[str] = set()
    while True:
        params: dict[str, object] = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "feed": feed,
            "limit": limit,
            "sort": "asc",
        }
        if asof is not None:
            params["asof"] = asof.isoformat() if isinstance(asof, date) else asof
        if page_token:
            params["page_token"] = page_token
        query = urllib.parse.urlencode(params)
        payload = get_json(
            f"{DATA_BASE}/v2/stocks/{urllib.parse.quote(symbol, safe='')}/trades?{query}",
            headers=client.headers,
            timeout_seconds=client.timeout_seconds,
        )
        if not isinstance(payload, dict):
            raise ValueError("Alpaca trades response must be an object")
        page_rows = payload.get("trades", [])
        if isinstance(page_rows, list):
            rows.extend(row for row in page_rows if isinstance(row, dict))
        next_token = payload.get("next_page_token")
        if not next_token:
            break
        page_token = str(next_token)
        if page_token in seen_tokens:
            raise RuntimeError("Alpaca trades pagination token repeated")
        seen_tokens.add(page_token)
    return trade_frame(rows)
