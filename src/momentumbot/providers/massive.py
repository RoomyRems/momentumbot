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
OFFICIAL_TICKER_TYPES_DOC = (
    "https://massive.com/docs/rest/stocks/tickers/ticker-types"
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
    order_regression_from_previous_page: bool = False


@dataclass(frozen=True, slots=True)
class MassiveTickerCensus:
    as_of: str
    query: dict[str, object]
    pages: tuple[MassiveTickerPage, ...]
    rows: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class MassiveSplitPage:
    page_number: int
    row_count: int
    next_page_present: bool


@dataclass(frozen=True, slots=True)
class MassiveSplitCensus:
    query: dict[str, object]
    pages: tuple[MassiveSplitPage, ...]
    rows: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class MassiveTickerEventTimeline:
    identifier: str
    name: str
    events: tuple[dict[str, object], ...]


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
    return tuple(
        sorted(
            normalized,
            key=lambda row: tuple(
                str(row[field])
                for field in (
                    *_MEMBERSHIP_FIELDS,
                    "currency_name",
                    "delisted_utc",
                    "last_updated_utc",
                    "name",
                )
            ),
        )
    )


def reference_membership_identity(row: dict[str, object]) -> str:
    normalized = normalize_reference_tickers([row])[0]
    return json.dumps(
        {field: normalized[field] for field in _MEMBERSHIP_FIELDS},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


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


def normalize_ticker_types(
    rows: list[dict[str, object]] | tuple[dict[str, object], ...],
) -> tuple[dict[str, str], ...]:
    normalized: list[dict[str, str]] = []
    for row in rows:
        code = _text(row.get("code"), upper=True)
        if not code:
            raise ValueError("Massive ticker-type row is missing code")
        normalized.append(
            {
                "asset_class": _text(row.get("asset_class"), lower=True),
                "code": code,
                "description": _text(row.get("description")),
                "locale": _text(row.get("locale"), lower=True),
            }
        )
    output = tuple(sorted(normalized, key=lambda row: row["code"]))
    codes = [row["code"] for row in output]
    if len(codes) != len(set(codes)):
        raise RuntimeError("Massive ticker-type dictionary contains duplicate codes")
    return output


def ticker_type_fingerprint(
    rows: list[dict[str, object]] | tuple[dict[str, object], ...],
) -> str:
    return _fingerprint_payload(normalize_ticker_types(rows))


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

    def _authenticated_pagination_url(
        self,
        raw_url: str,
        *,
        expected_path: str,
    ) -> tuple[str, str]:
        absolute = urllib.parse.urljoin(f"{self.base_url}/", raw_url)
        parsed = urllib.parse.urlparse(absolute)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
            raise RuntimeError("Massive pagination escaped the official API hosts")
        if parsed.path != expected_path:
            raise RuntimeError("Massive pagination changed the expected endpoint path")
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

    def _authenticated_url(self, raw_url: str) -> tuple[str, str]:
        return self._authenticated_pagination_url(
            raw_url,
            expected_path="/v3/reference/tickers",
        )

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
        seen_identities: set[str] = set()
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
            page_identities = [
                reference_membership_identity(row) for row in normalized_page
            ]
            if len(page_identities) != len(set(page_identities)):
                raise RuntimeError(
                    "Massive reference-tickers page contains a duplicate membership identity"
                )
            order_regression = bool(
                previous_ticker is not None
                and page_tickers
                and page_tickers[0] < previous_ticker
            )
            duplicate_identity = next(
                (identity for identity in page_identities if identity in seen_identities),
                None,
            )
            if duplicate_identity is not None:
                raise RuntimeError(
                    "Massive reference-tickers repeated a membership identity across pages"
                )
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
                    order_regression_from_previous_page=order_regression,
                )
            )
            rows.extend(normalized_page)
            seen_identities.update(page_identities)
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

    def ticker_types(self) -> tuple[dict[str, str], ...]:
        query = urllib.parse.urlencode(
            {
                "asset_class": "stocks",
                "locale": "us",
                "apiKey": self._api_key,
            }
        )
        payload = self._paced_get(
            f"{self.base_url}/v3/reference/tickers/types?{query}"
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Massive ticker-types response must be an object")
        raw_results = payload.get("results")
        if isinstance(raw_results, dict):
            rows = [raw_results]
        elif isinstance(raw_results, list) and all(
            isinstance(row, dict) for row in raw_results
        ):
            rows = raw_results
        else:
            raise RuntimeError("Massive ticker-types results must be objects")
        normalized = normalize_ticker_types(rows)
        if not normalized:
            raise RuntimeError("Massive ticker-type dictionary is empty")
        for row in normalized:
            if row["asset_class"] != "stocks" or row["locale"] != "us":
                raise RuntimeError("Massive ticker-type dictionary violated its filters")
        return normalized

    def stock_splits(
        self,
        *,
        start: date,
        end: date,
        limit: int = 5000,
        max_pages: int = 20,
    ) -> MassiveSplitCensus:
        if start > end:
            raise ValueError("split start must not follow end")
        if limit <= 0 or limit > 5000:
            raise ValueError("split limit must be between 1 and 5000")
        if max_pages <= 0:
            raise ValueError("split max_pages must be positive")
        query: dict[str, object] = {
            "execution_date.gte": start.isoformat(),
            "execution_date.lte": end.isoformat(),
            "limit": limit,
            "sort": "execution_date.asc,ticker.asc",
        }
        initial_query = urllib.parse.urlencode({**query, "apiKey": self._api_key})
        url = f"{self.base_url}/stocks/v1/splits?{initial_query}"
        rows: list[dict[str, object]] = []
        pages: list[MassiveSplitPage] = []
        seen_cursors: set[str] = set()
        for page_number in range(1, max_pages + 1):
            payload = self._paced_get(url)
            if not isinstance(payload, dict):
                raise RuntimeError("Massive splits response must be an object")
            raw_page = payload.get("results")
            if not isinstance(raw_page, list) or any(
                not isinstance(row, dict) for row in raw_page
            ):
                raise RuntimeError("Massive splits results must be objects")
            normalized_page: list[dict[str, object]] = []
            for row in raw_page:
                execution_date = _text(row.get("execution_date"))
                ticker = _text(row.get("ticker"), upper=True)
                if not execution_date or not ticker:
                    raise RuntimeError("Massive split is missing date or ticker")
                if not start.isoformat() <= execution_date <= end.isoformat():
                    raise RuntimeError("Massive split escaped the requested date range")
                normalized_page.append(
                    {
                        "adjustment_type": _text(row.get("adjustment_type"), lower=True),
                        "execution_date": execution_date,
                        "historical_adjustment_factor": row.get(
                            "historical_adjustment_factor"
                        ),
                        "id": _text(row.get("id")),
                        "split_from": row.get("split_from"),
                        "split_to": row.get("split_to"),
                        "ticker": ticker,
                    }
                )
            rows.extend(normalized_page)
            next_url = payload.get("next_url")
            pages.append(
                MassiveSplitPage(
                    page_number=page_number,
                    row_count=len(normalized_page),
                    next_page_present=bool(next_url),
                )
            )
            if not next_url:
                break
            if not isinstance(next_url, str):
                raise RuntimeError("Massive split next_url must be a string")
            url, cursor_identity = self._authenticated_pagination_url(
                next_url,
                expected_path="/stocks/v1/splits",
            )
            if cursor_identity in seen_cursors:
                raise RuntimeError("Massive split pagination cursor repeated")
            seen_cursors.add(cursor_identity)
        else:
            raise RuntimeError("Massive splits exceeded max_pages")

        normalized = tuple(
            sorted(
                rows,
                key=lambda row: (
                    str(row["execution_date"]),
                    str(row["ticker"]),
                    str(row["id"]),
                ),
            )
        )
        return MassiveSplitCensus(
            query=query,
            pages=tuple(pages),
            rows=normalized,
        )

    def ticker_events(
        self,
        identifier: str,
        *,
        types: tuple[str, ...] = ("ticker_change",),
    ) -> MassiveTickerEventTimeline:
        rendered_identifier = str(identifier).strip().upper()
        if not rendered_identifier:
            raise ValueError("ticker-event identifier is required")
        query: dict[str, object] = {"apiKey": self._api_key}
        rendered_types = ",".join(
            dict.fromkeys(str(value).strip() for value in types if str(value).strip())
        )
        if rendered_types:
            query["types"] = rendered_types
        encoded_identifier = urllib.parse.quote(rendered_identifier, safe="")
        payload = self._paced_get(
            f"{self.base_url}/vX/reference/tickers/{encoded_identifier}/events?"
            f"{urllib.parse.urlencode(query)}"
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Massive ticker-events response must be an object")
        results = payload.get("results")
        if not isinstance(results, dict):
            raise RuntimeError("Massive ticker-events results must be an object")
        raw_events = results.get("events", [])
        if not isinstance(raw_events, list) or any(
            not isinstance(event, dict) for event in raw_events
        ):
            raise RuntimeError("Massive ticker-events events must be objects")
        events = tuple(
            sorted(
                (dict(event) for event in raw_events),
                key=lambda event: json.dumps(
                    event,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
        )
        return MassiveTickerEventTimeline(
            identifier=rendered_identifier,
            name=_text(results.get("name")),
            events=events,
        )
