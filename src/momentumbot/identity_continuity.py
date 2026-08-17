"""Label-blind identity continuity contracts for historical universe snapshots.

The bridge uses provider identifiers only. Composite FIGI is the primary
security-level key. A nonblank CIK may be used as a provisional fallback only
when exactly one accepted common-equity ticker carries that CIK on each side
and at least one side lacks a FIGI. Two different nonblank FIGIs are never
collapsed merely because their issuer CIK matches.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from typing import Iterable


IDENTITY_POLICY_ID = "historical-identity-continuity-v0.1"


def _text(value: object, *, upper: bool = False) -> str:
    rendered = "" if value is None else str(value).strip()
    return rendered.upper() if upper else rendered


def _normalize_rows(rows: Iterable[dict[str, object]]) -> tuple[dict[str, str], ...]:
    normalized: list[dict[str, str]] = []
    seen_tickers: set[str] = set()
    for row in rows:
        ticker = _text(row.get("ticker"), upper=True)
        if not ticker:
            raise ValueError("included identity row is missing ticker")
        if ticker in seen_tickers:
            raise ValueError(f"included identity rows repeat ticker {ticker}")
        if row.get("included") is False:
            raise ValueError("identity bridge accepts included rows only")
        seen_tickers.add(ticker)
        normalized.append(
            {
                "ticker": ticker,
                "cik": _text(row.get("selected_cik")),
                "composite_figi": _text(
                    row.get("selected_composite_figi"), upper=True
                ),
                "primary_exchange": _text(
                    row.get("selected_primary_exchange"), upper=True
                ),
                "security_type": _text(
                    row.get("selected_security_type"), upper=True
                ),
            }
        )
    return tuple(sorted(normalized, key=lambda row: row["ticker"]))


def _group(
    rows: tuple[dict[str, str], ...],
    field: str,
) -> dict[str, list[dict[str, str]]]:
    output: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        value = row[field]
        if value:
            output[value].append(row)
    return dict(output)


def _fingerprint(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _date_identity_statuses(
    rows: tuple[dict[str, str], ...],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    cik_counts = Counter(row["cik"] for row in rows if row["cik"])
    accepted: list[dict[str, str]] = []
    quarantined: list[dict[str, str]] = []
    for row in rows:
        if row["composite_figi"]:
            accepted.append(
                {
                    "ticker": row["ticker"],
                    "identifier_kind": "composite_figi",
                    "identifier": row["composite_figi"],
                }
            )
        elif row["cik"] and cik_counts[row["cik"]] == 1:
            accepted.append(
                {
                    "ticker": row["ticker"],
                    "identifier_kind": "unique_cik_fallback",
                    "identifier": row["cik"],
                }
            )
        else:
            reason = "missing_stable_identifier"
            if row["cik"] and cik_counts[row["cik"]] > 1:
                reason = "nonunique_cik_without_composite_figi"
            quarantined.append(
                {
                    "ticker": row["ticker"],
                    "cik": row["cik"],
                    "composite_figi": row["composite_figi"],
                    "reason": reason,
                }
            )
    return accepted, quarantined


def build_date_identity_statuses(
    rows: Iterable[dict[str, object]],
) -> dict[str, list[dict[str, str]]]:
    """Apply the frozen identity decision independently to one snapshot date."""

    normalized = _normalize_rows(rows)
    accepted, quarantined = _date_identity_statuses(normalized)
    return {
        "accepted": accepted,
        "quarantined": quarantined,
    }


def build_cross_date_identity_bridge(
    earlier_rows: Iterable[dict[str, object]],
    later_rows: Iterable[dict[str, object]],
    *,
    earlier_date: str,
    later_date: str,
) -> dict[str, object]:
    if earlier_date >= later_date:
        raise ValueError("identity bridge dates must be strictly increasing")
    earlier = _normalize_rows(earlier_rows)
    later = _normalize_rows(later_rows)
    earlier_figi = _group(earlier, "composite_figi")
    later_figi = _group(later, "composite_figi")
    earlier_cik = _group(earlier, "cik")
    later_cik = _group(later, "cik")
    earlier_by_ticker = {row["ticker"]: row for row in earlier}
    later_by_ticker = {row["ticker"]: row for row in later}

    transitions: list[dict[str, object]] = []
    matched_earlier: set[str] = set()
    matched_later: set[str] = set()

    for figi in sorted(set(earlier_figi) & set(later_figi)):
        left = earlier_figi[figi]
        right = later_figi[figi]
        if len(left) != 1 or len(right) != 1:
            continue
        before = left[0]
        after = right[0]
        transitions.append(
            {
                "identifier_kind": "composite_figi",
                "identifier": figi,
                "earlier_ticker": before["ticker"],
                "later_ticker": after["ticker"],
                "earlier_cik": before["cik"],
                "later_cik": after["cik"],
                "earlier_composite_figi": before["composite_figi"],
                "later_composite_figi": after["composite_figi"],
                "ticker_changed": before["ticker"] != after["ticker"],
            }
        )
        matched_earlier.add(before["ticker"])
        matched_later.add(after["ticker"])

    for cik in sorted(set(earlier_cik) & set(later_cik)):
        left = earlier_cik[cik]
        right = later_cik[cik]
        if len(left) != 1 or len(right) != 1:
            continue
        before = left[0]
        after = right[0]
        if before["ticker"] in matched_earlier or after["ticker"] in matched_later:
            continue
        if before["composite_figi"] and after["composite_figi"]:
            # Different nonblank security identifiers are not an issuer-level match.
            continue
        transitions.append(
            {
                "identifier_kind": "unique_cik_fallback",
                "identifier": cik,
                "earlier_ticker": before["ticker"],
                "later_ticker": after["ticker"],
                "earlier_cik": before["cik"],
                "later_cik": after["cik"],
                "earlier_composite_figi": before["composite_figi"],
                "later_composite_figi": after["composite_figi"],
                "ticker_changed": before["ticker"] != after["ticker"],
            }
        )
        matched_earlier.add(before["ticker"])
        matched_later.add(after["ticker"])

    transitions.sort(
        key=lambda row: (
            str(row["identifier_kind"]),
            str(row["identifier"]),
            str(row["earlier_ticker"]),
            str(row["later_ticker"]),
        )
    )
    for transition in transitions:
        earlier_ticker = str(transition["earlier_ticker"])
        later_ticker = str(transition["later_ticker"])
        later_reuse = later_by_ticker.get(earlier_ticker)
        earlier_reuse = earlier_by_ticker.get(later_ticker)
        transition["symbol_reuse_involved"] = bool(
            (
                later_reuse
                and transition["earlier_composite_figi"]
                and later_reuse["composite_figi"]
                and transition["earlier_composite_figi"]
                != later_reuse["composite_figi"]
            )
            or (
                earlier_reuse
                and transition["later_composite_figi"]
                and earlier_reuse["composite_figi"]
                and transition["later_composite_figi"]
                != earlier_reuse["composite_figi"]
            )
        )

    same_ticker_different_figi = []
    for ticker in sorted(set(earlier_by_ticker) & set(later_by_ticker)):
        before = earlier_by_ticker[ticker]
        after = later_by_ticker[ticker]
        if (
            before["composite_figi"]
            and after["composite_figi"]
            and before["composite_figi"] != after["composite_figi"]
        ):
            same_ticker_different_figi.append(
                {
                    "ticker": ticker,
                    "earlier_composite_figi": before["composite_figi"],
                    "later_composite_figi": after["composite_figi"],
                }
            )

    earlier_accepted, earlier_quarantined = _date_identity_statuses(earlier)
    later_accepted, later_quarantined = _date_identity_statuses(later)
    changed = [row for row in transitions if row["ticker_changed"]]
    payload: dict[str, object] = {
        "schema_version": 1,
        "identity_policy_id": IDENTITY_POLICY_ID,
        "earlier_date": earlier_date,
        "later_date": later_date,
        "knowledge_policy": {
            "uses_benchmark_labels": False,
            "primary_identity": "composite_figi",
            "fallback_identity": "unique_nonblank_cik_with_missing_figi",
            "different_nonblank_figis_are_never_collapsed_by_cik": True,
        },
        "summary": {
            "earlier_included_count": len(earlier),
            "later_included_count": len(later),
            "earlier_identity_accepted_count": len(earlier_accepted),
            "later_identity_accepted_count": len(later_accepted),
            "earlier_identity_quarantine_count": len(earlier_quarantined),
            "later_identity_quarantine_count": len(later_quarantined),
            "cross_date_transition_count": len(transitions),
            "exact_figi_transition_count": sum(
                row["identifier_kind"] == "composite_figi" for row in transitions
            ),
            "unique_cik_fallback_transition_count": sum(
                row["identifier_kind"] == "unique_cik_fallback"
                for row in transitions
            ),
            "changed_ticker_transition_count": len(changed),
            "changed_ticker_exact_figi_count": sum(
                row["identifier_kind"] == "composite_figi" for row in changed
            ),
            "changed_ticker_unique_cik_fallback_count": sum(
                row["identifier_kind"] == "unique_cik_fallback" for row in changed
            ),
            "symbol_reuse_transition_count": sum(
                bool(row["symbol_reuse_involved"]) for row in transitions
            ),
            "same_ticker_different_figi_count": len(same_ticker_different_figi),
        },
        "date_identity_status": {
            earlier_date: {
                "accepted": earlier_accepted,
                "quarantined": earlier_quarantined,
            },
            later_date: {
                "accepted": later_accepted,
                "quarantined": later_quarantined,
            },
        },
        "transitions": transitions,
        "same_ticker_different_figi": same_ticker_different_figi,
    }
    payload["bridge_sha256"] = _fingerprint(payload)
    return payload

