from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from .http_json import get_json


MASSIVE_API_BASE = "https://api.massive.com"
POLYGON_API_BASE = "https://api.polygon.io"
OFFICIAL_ALL_TICKERS_DOC = (
    "https://massive.com/docs/rest/stocks/tickers/all-tickers"
)
_ALLOWED_HOSTS = {"api.massive.com", "api.polygon.io"}
_MEMBERSHIP_FIELDS = (
    "ticker",
    "active",
    "market",
    "locale",
    "primary_exchange",
    "type",
    "cik",
    "composite_figi",
    "share_class_figi",
)


@dataclass(frozen=True, slots=True)
class MassiveTickerPage:
    page_number: int
    row_count: int
    first_ticker: str
    last_ticker: str
    next_page_present: bool


@dataclass(frozen=True, slots=True)
class MassiveTickerCensus:
    as_of: str
    query: dict[str, object]
    pages: tuple[MassiveTickerPage, ...]
    rows: tuple[dict[str, object], ...]


def _text(value: object, *, upper: bool = False, lower: bool = False) -> str:
    rendered = "" if value is None else str(value).strip()
    if upper:
        return rendered.upper()
    if lower:
        return rendered.lower()
    return rendered


def normalize_reference_tickers(
    rows: list[dict[str, object]] | tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    normalized: list[dict[str, object]] = []
    for row in rows:
        ticker = _text(row.get("ticker"), upper=True)
        if not ticker:
            raise ValueError("Massive reference ticker row is missing ticker")
        raw_active = row.get("active")
        normalized.append(
            {
                "active": raw_active if isinstance(raw_active, bool) else None,
                "cik": _text(row.get("cik")),
                "composite_figi": _text(row.get("composite_figi"), upper=True),
                "currency_name": _text(row.get("currency_name"), upper=True),
                "delisted_utc": _text(row.get("delisted_utc")),
                "last_updated_utc": _text(row.get("last_updated_utc")),
                "locale": _text(row.get("locale"), lower=True),
                "market": _text(row.get("market"), lower=True),
                "name": _text(row.get("name")),
                "primary_exchange": _text(row.get("primary_exchange"), upper=True),
                "share_class_figi": _text(row.get("share_class_figi"), upper=True),
                "ticker": ticker,
                "type": _text(row.get("type"), upper=True),
            }
        )
    return tuple(sorted(normalized, key=lambda row: str(row["ticker"])))


def _fingerprint_payload(rows: object) -> str:
    payload = json.dumps(
        rows,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def reference_ticker_fingerprint(
    rows: list[dict[str, object]] | tuple[dict[str, object], ...],
) -> str:
    return _fingerprint_payload(normalize_reference_tickers(rows))


def reference_membership_fingerprint(
    rows: list[dict[str, object]] | tuple[dict[str, object], ...],
) -> str:
    normalized = normalize_reference_tickers(rows)
    membership = tuple(
        {field: row[field] for field in _MEMBERSHIP_FIELDS}
        for row in normalized
    )
    return _fingerprint_payload(membership)


def _credential() -> tuple[str, str, str]:
    if key := os.getenv("MASSIVE_API_KEY"):
        return key, "MASSIVE_API_KEY", MASSIVE_API_BASE
    if key := os.getenv("POLYGON_API_KEY"):
        return key, "POLYGON_API_KEY", POLYGON_API_BASE
    raise ValueError("MASSIVE_API_KEY or POLYGON_API_KEY is required")


class MassiveReferenceClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = MASSIVE_API_BASE,
        credential_name: str = "MASSIVE_API_KEY",
        timeout_seconds: int = 30,
        minimum_request_interval_seconds: float = 0.0,
        requester: Callable[..., Any] = get_json,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not api_key:
            raise ValueError("Massive API key is required")
        parsed = urllib.parse.urlparse(base_url.rstrip("/"))
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
            raise ValueError("Massive base URL must be an official HTTPS API host")
        if minimum_request_interval_seconds < 0:
            raise ValueError("minimum request interval cannot be negative")
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.credential_name = credential_name
        self.timeout_seconds = timeout_seconds
        self.minimum_request_interval_seconds = minimum_request_interval_seconds
        self._requester = requester
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request_started_at: float | None = None

    @classmethod
    def from_env(
        cls,
        *,
        minimum_request_interval_seconds: float = 0.0,
    ) -> "MassiveReferenceClient":
        key, name, base_url = _credential()
        return cls(
            key,
            base_url=base_url,
            credential_name=name,
            minimum_request_interval_seconds=minimum_request_interval_seconds,
        )

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Accept-Encoding": "gzip",
            "User-Agent": "MomentumBot/0.3 historical-universe",
        }

    def _paced_get(self, url: str) -> Any:
        now = self._monotonic()
        if self._last_request_started_at is not None:
            elapsed = now - self._last_request_started_at
            remaining = self.minimum_request_interval_seconds - elapsed
            if remaining > 0:
                self._sleep(remaining)
                now = self._monotonic()
        self._last_request_started_at = now
        return self._requester(
            url,
            headers=self.headers,
            timeout_seconds=self.timeout_seconds,
        )

    def _authenticated_url(self, raw_url: str) -> tuple[str, str]:
        absolute = urllib.parse.urljoin(f"{self.base_url}/", raw_url)
        parsed = urllib.parse.urlparse(absolute)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
            raise RuntimeError("Massive pagination escaped the official API hosts")
        if parsed.path != "/v3/reference/tickers":
            raise RuntimeError("Massive pagination changed the reference-tickers path")
        safe_parameters = [
            (key, value)
            for key, value in urllib.parse.parse_qsl(
                parsed.query,
                keep_blank_values=True,
            )
            if key.lower() != "apikey"
        ]
        safe_query = urllib.parse.urlencode(safe_parameters)
        cursor_identity = urllib.parse.urlunparse(parsed._replace(query=safe_query))
        authenticated_query = urllib.parse.urlencode(
            [*safe_parameters, ("apiKey", self._api_key)]
        )
        authenticated = urllib.parse.urlunparse(
            parsed._replace(query=authenticated_query)
        )
        return authenticated, cursor_identity

    def active_tickers_as_of(
        self,
        as_of: date,
        *,
        limit: int = 1000,
        max_pages: int = 100,
    ) -> MassiveTickerCensus:
        if limit <= 0 or limit > 1000:
            raise ValueError("Massive reference-ticker limit must be between 1 and 1000")
        if max_pages <= 0:
            raise ValueError("max_pages must be positive")
        query: dict[str, object] = {
            "market": "stocks",
            "locale": "us",
            "active": "true",
            "date": as_of.isoformat(),
            "order": "asc",
            "sort": "ticker",
            "limit": limit,
        }
        initial_query = urllib.parse.urlencode({**query, "apiKey": self._api_key})
        url = f"{self.base_url}/v3/reference/tickers?{initial_query}"
        rows: list[dict[str, object]] = []
        pages: list[MassiveTickerPage] = []
        seen_cursors: set[str] = set()
        seen_tickers: set[str] = set()
        previous_ticker: str | None = None

        for page_number in range(1, max_pages + 1):
            payload = self._paced_get(url)
            if not isinstance(payload, dict):
                raise RuntimeError("Massive reference-tickers response must be an object")
            raw_page = payload.get("results")
            if not isinstance(raw_page, list):
                raise RuntimeError("Massive reference-tickers results must be a list")
            if any(not isinstance(row, dict) for row in raw_page):
                raise RuntimeError("Massive reference-tickers page contains a non-object row")
            reported_count = payload.get("count")
            if isinstance(reported_count, int) and reported_count != len(raw_page):
                raise RuntimeError("Massive reference-tickers page count mismatch")

            normalized_page = normalize_reference_tickers(raw_page)
            page_tickers = [str(row["ticker"]) for row in normalized_page]
            if len(page_tickers) != len(set(page_tickers)):
                raise RuntimeError("Massive reference-tickers page contains duplicate tickers")
            if previous_ticker is not None and page_tickers and page_tickers[0] <= previous_ticker:
                raise RuntimeError("Massive reference-tickers pagination is not strictly ordered")
            duplicate = next((ticker for ticker in page_tickers if ticker in seen_tickers), None)
            if duplicate is not None:
                raise RuntimeError("Massive reference-tickers repeated a ticker across pages")
            for row in normalized_page:
                if row["active"] is not True:
                    raise RuntimeError("Massive active census returned a non-active ticker")
                if row["market"] != "stocks" or row["locale"] != "us":
                    raise RuntimeError("Massive active census violated market/locale filters")

            next_url = payload.get("next_url")
            next_page_present = bool(next_url)
            pages.append(
                MassiveTickerPage(
                    page_number=page_number,
                    row_count=len(normalized_page),
                    first_ticker=page_tickers[0] if page_tickers else "",
                    last_ticker=page_tickers[-1] if page_tickers else "",
                    next_page_present=next_page_present,
                )
            )
            rows.extend(normalized_page)
            seen_tickers.update(page_tickers)
            if page_tickers:
                previous_ticker = page_tickers[-1]
            if not next_page_present:
                break
            if not isinstance(next_url, str):
                raise RuntimeError("Massive next_url must be a string")
            url, cursor_identity = self._authenticated_url(next_url)
            if cursor_identity in seen_cursors:
                raise RuntimeError("Massive pagination cursor repeated")
            seen_cursors.add(cursor_identity)
        else:
            raise RuntimeError("Massive reference-tickers exceeded max_pages")

        normalized = normalize_reference_tickers(rows)
        if not normalized:
            raise RuntimeError("Massive active census returned no tickers")
        return MassiveTickerCensus(
            as_of=as_of.isoformat(),
            query=query,
            pages=tuple(pages),
            rows=normalized,
        )
