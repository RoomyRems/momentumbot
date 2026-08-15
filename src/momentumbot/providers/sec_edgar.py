from __future__ import annotations

import gzip
import json
import urllib.request
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable, TypeVar

SEC_DATA_BASE = "https://data.sec.gov"
DEFAULT_USER_AGENT = "MomentumBot/0.2 https://github.com/RoomyRems/momentumbot"
_ALLOWED_PUBLIC_FLOAT_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
_ALLOWED_OUTSTANDING_FORMS = _ALLOWED_PUBLIC_FLOAT_FORMS | {"10-Q", "10-Q/A"}


@dataclass(frozen=True, slots=True)
class PublicFloatDisclosure:
    cik: str
    measure_date: date
    public_float_usd: float
    filed_date: date
    available_at: datetime
    accession: str
    form: str


@dataclass(frozen=True, slots=True)
class OutstandingSharesDisclosure:
    cik: str
    measure_date: date
    shares: int
    filed_date: date
    available_at: datetime
    accession: str
    form: str


@dataclass(frozen=True, slots=True)
class FloatEstimate:
    cik: str
    value_shares: int
    measure_date: date
    available_at: datetime
    method: str
    source_accession: str
    public_float_usd: float | None = None
    price_used: float | None = None
    anchor_outstanding_shares: int | None = None
    current_outstanding_shares: int | None = None


@dataclass(frozen=True, slots=True)
class ParsedCompanyFacts:
    public_float: tuple[PublicFloatDisclosure, ...]
    outstanding_shares: tuple[OutstandingSharesDisclosure, ...]


def normalize_cik(cik: str | int) -> str:
    digits = str(cik).strip()
    if not digits.isdigit():
        raise ValueError(f"CIK must be numeric: {cik!r}")
    return digits.zfill(10)


def _parse_sec_datetime(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_submission_acceptance_times(payload: dict[str, Any]) -> dict[str, datetime]:
    """Map accession number to its exact EDGAR acceptance timestamp when available."""
    filings = payload.get("filings", {})
    recent = filings.get("recent", {}) if isinstance(filings, dict) else {}
    accessions = recent.get("accessionNumber", []) if isinstance(recent, dict) else []
    accepted = recent.get("acceptanceDateTime", []) if isinstance(recent, dict) else []
    result: dict[str, datetime] = {}
    if not isinstance(accessions, list) or not isinstance(accepted, list):
        return result
    for accession, timestamp in zip(accessions, accepted, strict=False):
        if accession and timestamp:
            result[str(accession)] = _parse_sec_datetime(str(timestamp))
    return result


def _conservative_available_at(filed: date) -> datetime:
    """Fallback when exact acceptance time is unavailable.

    Company-facts rows expose only a filing date. Rather than allowing the fact
    during that same premarket session, make it available at the following
    regular-session open in a conservative UTC approximation. Exact acceptance
    timestamps from the submissions feed override this fallback.
    """
    return datetime.combine(filed + timedelta(days=1), time(14, 30), tzinfo=timezone.utc)


def _available_at(
    accession: str,
    filed: date,
    acceptance_times: dict[str, datetime] | None,
) -> datetime:
    if acceptance_times and accession in acceptance_times:
        return acceptance_times[accession]
    return _conservative_available_at(filed)


def _unit_rows(payload: dict[str, Any], concept: str, unit: str) -> list[dict[str, Any]]:
    facts = payload.get("facts", {})
    dei = facts.get("dei", {}) if isinstance(facts, dict) else {}
    concept_payload = dei.get(concept, {}) if isinstance(dei, dict) else {}
    units = concept_payload.get("units", {}) if isinstance(concept_payload, dict) else {}
    rows = units.get(unit, []) if isinstance(units, dict) else []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def parse_companyfacts(
    payload: dict[str, Any],
    *,
    acceptance_times: dict[str, datetime] | None = None,
) -> ParsedCompanyFacts:
    """Parse point-in-time float/share-count disclosures from SEC company facts.

    Public float is an SEC monetary disclosure, not a share count. It must be
    converted later using historical price data. Availability is keyed to the
    filing timestamp, never the older measurement date.
    """
    cik = normalize_cik(payload.get("cik", ""))
    public_float: list[PublicFloatDisclosure] = []
    outstanding: list[OutstandingSharesDisclosure] = []

    seen_public: set[tuple[str, str, float]] = set()
    for row in _unit_rows(payload, "EntityPublicFloat", "USD"):
        form = str(row.get("form", ""))
        accession = str(row.get("accn", ""))
        if form not in _ALLOWED_PUBLIC_FLOAT_FORMS or not accession:
            continue
        try:
            measure_date = date.fromisoformat(str(row["end"]))
            filed = date.fromisoformat(str(row["filed"]))
            value = float(row["val"])
        except (KeyError, TypeError, ValueError):
            continue
        if value <= 0:
            continue
        key = (accession, measure_date.isoformat(), value)
        if key in seen_public:
            continue
        seen_public.add(key)
        public_float.append(
            PublicFloatDisclosure(
                cik=cik,
                measure_date=measure_date,
                public_float_usd=value,
                filed_date=filed,
                available_at=_available_at(accession, filed, acceptance_times),
                accession=accession,
                form=form,
            )
        )

    seen_outstanding: set[tuple[str, str, int]] = set()
    for row in _unit_rows(payload, "EntityCommonStockSharesOutstanding", "shares"):
        form = str(row.get("form", ""))
        accession = str(row.get("accn", ""))
        if form not in _ALLOWED_OUTSTANDING_FORMS or not accession:
            continue
        try:
            measure_date = date.fromisoformat(str(row["end"]))
            filed = date.fromisoformat(str(row["filed"]))
            shares = int(round(float(row["val"])))
        except (KeyError, TypeError, ValueError):
            continue
        if shares <= 0:
            continue
        key = (accession, measure_date.isoformat(), shares)
        if key in seen_outstanding:
            continue
        seen_outstanding.add(key)
        outstanding.append(
            OutstandingSharesDisclosure(
                cik=cik,
                measure_date=measure_date,
                shares=shares,
                filed_date=filed,
                available_at=_available_at(accession, filed, acceptance_times),
                accession=accession,
                form=form,
            )
        )

    public_float.sort(key=lambda item: (item.available_at, item.measure_date, item.accession))
    outstanding.sort(key=lambda item: (item.available_at, item.measure_date, item.accession))
    return ParsedCompanyFacts(tuple(public_float), tuple(outstanding))


TDisclosure = TypeVar("TDisclosure", PublicFloatDisclosure, OutstandingSharesDisclosure)


def latest_available(disclosures: Iterable[TDisclosure], as_of: datetime) -> TDisclosure | None:
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    eligible = [item for item in disclosures if item.available_at <= as_of]
    if not eligible:
        return None
    return max(eligible, key=lambda item: (item.available_at, item.measure_date))


def implied_float_shares(disclosure: PublicFloatDisclosure, historical_price: float) -> FloatEstimate:
    """Convert SEC dollar public float to implied non-affiliate shares.

    The result is an estimate because the filing reports aggregate market value,
    while the historical price feed supplies the price used to reverse that value
    into a share count.
    """
    if historical_price <= 0:
        raise ValueError("historical_price must be positive")
    shares = max(1, int(round(disclosure.public_float_usd / historical_price)))
    return FloatEstimate(
        cik=disclosure.cik,
        value_shares=shares,
        measure_date=disclosure.measure_date,
        available_at=disclosure.available_at,
        method="sec_public_float_usd_div_historical_price",
        source_accession=disclosure.accession,
        public_float_usd=disclosure.public_float_usd,
        price_used=historical_price,
    )


def roll_forward_float(
    anchor: FloatEstimate,
    *,
    anchor_outstanding: OutstandingSharesDisclosure,
    current_outstanding: OutstandingSharesDisclosure,
) -> FloatEstimate:
    """Conservatively roll an annual float estimate through newer share counts.

    Affiliate shares are held constant from the anchor. New net shares therefore
    increase estimated float; buybacks do not reduce the estimate until a later
    annual public-float disclosure confirms a lower value. This is deliberately
    biased toward false rejections of the low-float screen rather than false
    qualification after dilution.
    """
    if anchor.cik != anchor_outstanding.cik or anchor.cik != current_outstanding.cik:
        raise ValueError("CIKs must match")
    affiliate_shares = max(anchor_outstanding.shares - anchor.value_shares, 0)
    rolled = max(anchor.value_shares, current_outstanding.shares - affiliate_shares)
    return replace(
        anchor,
        value_shares=rolled,
        measure_date=current_outstanding.measure_date,
        available_at=max(anchor.available_at, current_outstanding.available_at),
        method="sec_public_float_anchor_plus_outstanding_rollforward",
        anchor_outstanding_shares=anchor_outstanding.shares,
        current_outstanding_shares=current_outstanding.shares,
    )


class SecEdgarClient:
    """Small, fair-access client for SEC public data APIs.

    Large historical builds should prefer SEC's nightly bulk archives. This
    client is intended for targeted fills, current updates, and validation.
    """

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT, timeout_seconds: int = 30):
        if not user_agent.strip():
            raise ValueError("SEC user agent must identify the application")
        self.user_agent = user_agent.strip()
        self.timeout_seconds = timeout_seconds

    def _json(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Host": "data.sec.gov",
            },
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            raw = response.read()
            if "gzip" in (response.headers.get("Content-Encoding") or "").lower():
                raw = gzip.decompress(raw)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("SEC response must be a JSON object")
        return payload

    def companyfacts(self, cik: str | int) -> dict[str, Any]:
        return self._json(f"{SEC_DATA_BASE}/api/xbrl/companyfacts/CIK{normalize_cik(cik)}.json")

    def submissions(self, cik: str | int) -> dict[str, Any]:
        return self._json(f"{SEC_DATA_BASE}/submissions/CIK{normalize_cik(cik)}.json")

    def parsed_companyfacts(self, cik: str | int) -> ParsedCompanyFacts:
        submissions = self.submissions(cik)
        acceptance = parse_submission_acceptance_times(submissions)
        return parse_companyfacts(self.companyfacts(cik), acceptance_times=acceptance)
