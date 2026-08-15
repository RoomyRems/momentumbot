from __future__ import annotations

import os
import re
import urllib.parse
from datetime import date, datetime
from typing import Any, Iterable

import pandas as pd

from .http_json import get_json

DATA_BASE = "https://data.alpaca.markets"
_ALLOWED_TRADING_HOSTS = {"paper-api.alpaca.markets", "api.alpaca.markets"}
_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
_INVALID_SYMBOL_RE = re.compile(r"invalid symbol:\s*([A-Z0-9.\-]+)", re.IGNORECASE)
_BAR_COLUMNS = {
    "o": "open",
    "h": "high",
    "l": "low",
    "c": "close",
    "v": "volume",
    "n": "trade_count",
    "vw": "vwap",
}


def chunked(values: list[str], size: int) -> Iterable[list[str]]:
    if size <= 0:
        raise ValueError("chunk size must be positive")
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def _frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    columns = ["open", "high", "low", "close", "volume", "trade_count", "vwap"]
    if not rows:
        empty = pd.DataFrame(columns=columns)
        empty.index = pd.DatetimeIndex([], name="timestamp", tz="UTC")
        return empty
    frame = pd.DataFrame(rows).rename(columns=_BAR_COLUMNS)
    frame["timestamp"] = pd.to_datetime(frame["t"], utc=True)
    for column in columns:
        if column not in frame:
            frame[column] = pd.NA
    frame = frame.set_index("timestamp")[columns].sort_index()
    return frame


class AlpacaDataClient:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        paper_endpoint: str = "https://paper-api.alpaca.markets",
        timeout_seconds: int = 30,
    ) -> None:
        if not api_key or not api_secret:
            raise ValueError("Alpaca key and secret are required")
        endpoint = paper_endpoint.rstrip("/")
        parsed = urllib.parse.urlparse(endpoint)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_TRADING_HOSTS:
            raise ValueError("paper endpoint must be an official Alpaca HTTPS host")
        self.api_key = api_key
        self.api_secret = api_secret
        self.paper_endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.invalid_symbols: set[str] = set()

    @classmethod
    def from_env(cls) -> "AlpacaDataClient":
        return cls(
            os.environ["ALPACA_API_KEY"],
            os.environ["ALPACA_API_SECRET"],
            paper_endpoint=os.getenv("ALPACA_PAPER_ENDPOINT", "https://paper-api.alpaca.markets"),
        )

    @property
    def headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
            "Accept-Encoding": "gzip",
            "User-Agent": "MomentumBot/0.3 historical-snapshot",
        }

    def assets(self) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode({"asset_class": "us_equity"})
        payload = get_json(
            f"{self.paper_endpoint}/v2/assets?{query}",
            headers=self.headers,
            timeout_seconds=self.timeout_seconds,
        )
        if not isinstance(payload, list):
            raise ValueError("Alpaca assets response must be a list")
        rows = [row for row in payload if isinstance(row, dict)]
        return [
            row
            for row in rows
            if _SYMBOL_RE.fullmatch(str(row.get("symbol", "")).strip().upper())
        ]

    def bars(
        self,
        symbols: Iterable[str],
        *,
        timeframe: str,
        start: datetime | str,
        end: datetime | str,
        feed: str = "sip",
        adjustment: str = "raw",
        asof: date | str | None = None,
        limit: int = 10_000,
    ) -> dict[str, pd.DataFrame]:
        names = list(dict.fromkeys(str(symbol).upper() for symbol in symbols if symbol))
        if not names:
            return {}
        result_rows: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in names}
        page_token: str | None = None
        seen_tokens: set[str] = set()
        while True:
            params: dict[str, object] = {
                "symbols": ",".join(names),
                "timeframe": timeframe,
                "start": start.isoformat() if isinstance(start, datetime) else start,
                "end": end.isoformat() if isinstance(end, datetime) else end,
                "feed": feed,
                "adjustment": adjustment,
                "limit": limit,
                "sort": "asc",
            }
            if asof is not None:
                params["asof"] = asof.isoformat() if isinstance(asof, date) else asof
            if page_token:
                params["page_token"] = page_token
            query = urllib.parse.urlencode(params)
            payload = get_json(
                f"{DATA_BASE}/v2/stocks/bars?{query}",
                headers=self.headers,
                timeout_seconds=self.timeout_seconds,
            )
            if not isinstance(payload, dict):
                raise ValueError("Alpaca bars response must be an object")
            bars = payload.get("bars", {})
            if isinstance(bars, dict):
                for symbol, rows in bars.items():
                    if symbol in result_rows and isinstance(rows, list):
                        result_rows[symbol].extend(row for row in rows if isinstance(row, dict))
            next_token = payload.get("next_page_token")
            if not next_token:
                break
            page_token = str(next_token)
            if page_token in seen_tokens:
                raise RuntimeError("Alpaca pagination token repeated")
            seen_tokens.add(page_token)
        return {symbol: _frame(rows) for symbol, rows in result_rows.items()}

    def bars_batched(
        self,
        symbols: list[str],
        *,
        batch_size: int = 250,
        **kwargs: Any,
    ) -> dict[str, pd.DataFrame]:
        """Download batches while quarantining only provider-declared invalid symbols.

        Alpaca's asset master can contain security identifiers that its historical
        stock-bars endpoint rejects. A named `invalid symbol` response therefore
        removes exactly that identifier and retries the remaining batch. Every
        other provider error is re-raised rather than being silently swallowed.
        """
        output: dict[str, pd.DataFrame] = {}
        for batch in chunked(symbols, batch_size):
            working = [symbol for symbol in batch if symbol not in self.invalid_symbols]
            while working:
                try:
                    output.update(self.bars(working, **kwargs))
                    break
                except RuntimeError as exc:
                    match = _INVALID_SYMBOL_RE.search(str(exc))
                    if not match:
                        raise
                    invalid = match.group(1).upper()
                    if invalid not in working:
                        raise
                    self.invalid_symbols.add(invalid)
                    working = [symbol for symbol in working if symbol != invalid]
        return output

    def news(
        self,
        symbols: Iterable[str],
        *,
        start: datetime,
        end: datetime,
        include_content: bool = False,
    ) -> list[dict[str, Any]]:
        names = list(dict.fromkeys(str(symbol).upper() for symbol in symbols if symbol))
        if not names:
            return []
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("news bounds must be timezone-aware")
        if start >= end:
            raise ValueError("news start must precede news end")
        output: list[dict[str, Any]] = []
        page_token: str | None = None
        seen_tokens: set[str] = set()
        while True:
            params: dict[str, object] = {
                "symbols": ",".join(names),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "sort": "asc",
                "limit": 50,
                "include_content": str(include_content).lower(),
            }
            if page_token:
                params["page_token"] = page_token
            payload = get_json(
                f"{DATA_BASE}/v1beta1/news?{urllib.parse.urlencode(params)}",
                headers=self.headers,
                timeout_seconds=self.timeout_seconds,
            )
            if not isinstance(payload, dict):
                raise ValueError("Alpaca news response must be an object")
            rows = payload.get("news", [])
            if isinstance(rows, list):
                output.extend(row for row in rows if isinstance(row, dict))
            next_token = payload.get("next_page_token")
            if not next_token:
                break
            page_token = str(next_token)
            if page_token in seen_tokens:
                raise RuntimeError("Alpaca news pagination token repeated")
            seen_tokens.add(page_token)
        return output

    def corporate_actions(
        self,
        *,
        symbols: Iterable[str],
        start: date,
        end: date,
        types: str = "forward_split,reverse_split,name_change",
    ) -> list[dict[str, Any]]:
        params = {
            "symbols": ",".join(symbols),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "types": types,
            "region": "us",
            "limit": 1000,
        }
        payload = get_json(
            f"{DATA_BASE}/v1/corporate-actions?{urllib.parse.urlencode(params)}",
            headers=self.headers,
            timeout_seconds=self.timeout_seconds,
        )
        if not isinstance(payload, dict):
            return []
        groups = payload.get("corporate_actions", payload)
        rows: list[dict[str, Any]] = []
        if isinstance(groups, dict):
            for action_type, values in groups.items():
                if isinstance(values, list):
                    for value in values:
                        if isinstance(value, dict):
                            rows.append({"type": action_type, **value})
        return rows
