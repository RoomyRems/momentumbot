from __future__ import annotations

import os
import urllib.parse
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

from .http_json import get_json
from .sec_edgar import OutstandingSharesDisclosure, ParsedCompanyFacts, PublicFloatDisclosure

BASE_URL = "https://api.sec-api.io/float"


def _parse_reported_at(value: object) -> datetime:
    text = str(value).strip()
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_float_response(payload: dict[str, Any]) -> ParsedCompanyFacts:
    public: list[PublicFloatDisclosure] = []
    outstanding: list[OutstandingSharesDisclosure] = []
    for record in payload.get("data", []):
        if not isinstance(record, dict):
            continue
        try:
            cik = str(record["cik"])
            reported_at = _parse_reported_at(record["reportedAt"])
            accession = str(record["sourceFilingAccessionNo"])
        except (KeyError, TypeError, ValueError):
            continue
        float_payload = record.get("float", {})
        if not isinstance(float_payload, dict):
            continue

        grouped_outstanding: dict[date, int] = defaultdict(int)
        for row in float_payload.get("outstandingShares", []):
            if not isinstance(row, dict):
                continue
            try:
                period = date.fromisoformat(str(row["period"]))
                value = int(row["value"])
            except (KeyError, TypeError, ValueError):
                continue
            if value > 0:
                grouped_outstanding[period] += value
        for period, value in grouped_outstanding.items():
            outstanding.append(
                OutstandingSharesDisclosure(
                    cik=cik,
                    measure_date=period,
                    shares=value,
                    filed_date=reported_at.date(),
                    available_at=reported_at,
                    accession=accession,
                    form="SEC-API",
                )
            )

        grouped_public: dict[date, float] = defaultdict(float)
        for row in float_payload.get("publicFloat", []):
            if not isinstance(row, dict):
                continue
            try:
                period = date.fromisoformat(str(row["period"]))
                value = float(row["value"])
            except (KeyError, TypeError, ValueError):
                continue
            if value > 0:
                grouped_public[period] += value
        for period, value in grouped_public.items():
            public.append(
                PublicFloatDisclosure(
                    cik=cik,
                    measure_date=period,
                    public_float_usd=value,
                    filed_date=reported_at.date(),
                    available_at=reported_at,
                    accession=accession,
                    form="SEC-API",
                )
            )

    public.sort(key=lambda item: (item.available_at, item.measure_date))
    outstanding.sort(key=lambda item: (item.available_at, item.measure_date))
    return ParsedCompanyFacts(tuple(public), tuple(outstanding))


class SecApiFloatClient:
    def __init__(self, api_key: str, *, timeout_seconds: int = 30) -> None:
        if not api_key:
            raise ValueError("SEC-API key is required")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "SecApiFloatClient":
        return cls(os.environ["SEC_API_D2V_KEY"])

    def company_facts(self, *, ticker: str) -> ParsedCompanyFacts:
        query = urllib.parse.urlencode({"ticker": ticker.upper()})
        payload = get_json(
            f"{BASE_URL}?{query}",
            headers={
                "Authorization": self.api_key,
                "Accept-Encoding": "gzip",
                "User-Agent": "MomentumBot/0.3 validation",
            },
            timeout_seconds=self.timeout_seconds,
        )
        if not isinstance(payload, dict):
            raise ValueError("SEC-API float response must be an object")
        return parse_float_response(payload)
