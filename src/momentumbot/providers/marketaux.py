from __future__ import annotations

import os
import urllib.parse
from datetime import datetime, timezone
from typing import Any

from .http_json import get_json

BASE_URL = "https://api.marketaux.com/v1/news/all"


def _marketaux_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("MarketAux timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _marketaux_response_timestamp(value: object) -> str:
    """Normalize MarketAux's UTC response timestamp to an aware ISO value.

    MarketAux documents all returned dates as UTC/GMT, while examples may omit
    an explicit offset. Snapshot data must never carry a naive timestamp, so a
    missing offset is interpreted as UTC rather than local runner time.
    """
    text = str(value).strip()
    if not text:
        raise ValueError("MarketAux published_at cannot be empty")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


class MarketAuxClient:
    def __init__(self, api_key: str, *, timeout_seconds: int = 30) -> None:
        if not api_key:
            raise ValueError("MarketAux API key is required")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "MarketAuxClient":
        return cls(os.environ["MARKETAUX_API_KEY"])

    def news(
        self,
        symbol: str,
        *,
        published_after: datetime,
        published_before: datetime,
        max_pages: int = 5,
        page_size: int = 3,
    ) -> list[dict[str, Any]]:
        if published_after.tzinfo is None or published_before.tzinfo is None:
            raise ValueError("news bounds must be timezone-aware")
        if published_after >= published_before:
            raise ValueError("published_after must precede published_before")
        output: list[dict[str, Any]] = []
        seen: set[str] = set()
        for page in range(1, max_pages + 1):
            params = {
                "symbols": symbol.upper(),
                "published_after": _marketaux_timestamp(published_after),
                "published_before": _marketaux_timestamp(published_before),
                "language": "en",
                "group_similar": "false",
                "limit": page_size,
                "page": page,
                "api_token": self.api_key,
            }
            payload = get_json(
                f"{BASE_URL}?{urllib.parse.urlencode(params)}",
                headers={"Accept-Encoding": "gzip", "User-Agent": "MomentumBot/0.3"},
                timeout_seconds=self.timeout_seconds,
            )
            if not isinstance(payload, dict):
                break
            rows = payload.get("data", [])
            if not isinstance(rows, list):
                break
            for raw_row in rows:
                if not isinstance(raw_row, dict):
                    continue
                row = dict(raw_row)
                published = row.get("published_at")
                if published:
                    try:
                        row["published_at"] = _marketaux_response_timestamp(published)
                    except (TypeError, ValueError):
                        continue
                key = str(row.get("uuid") or row.get("url") or row.get("title"))
                if key in seen:
                    continue
                seen.add(key)
                output.append(row)
            if len(rows) < page_size:
                break
        return output
