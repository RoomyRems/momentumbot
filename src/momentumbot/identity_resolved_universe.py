"""Frozen contract for identity-resolved historical universe membership.

This layer does not reclassify instruments or introduce strategy inputs.  It
accepts the provisional common-equity rows, removes only the explicit
identity-continuity quarantine, and attaches the stable identifier selected by
the label-blind identity audit.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable

from .historical_universe import HISTORICAL_UNIVERSE_POLICY_ID
from .identity_continuity import IDENTITY_POLICY_ID


IDENTITY_RESOLVED_UNIVERSE_POLICY_ID = "identity-resolved-universe-v0.1"
IDENTITY_RESOLVED_UNIVERSE_POLICY_STATUS = (
    "frozen_research_data_contract_not_promotable"
)
IDENTITY_AUDIT_LOOKBACK_DAYS = 120


def json_fingerprint(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _text(value: object, *, upper: bool = False) -> str:
    rendered = "" if value is None else str(value).strip()
    return rendered.upper() if upper else rendered


@dataclass(frozen=True, slots=True)
class FrozenIdentityResolvedUniversePolicy:
    policy_id: str
    status: str
    source_universe_policy_id: str
    identity_policy_id: str
    identity_audit_lookback_days: int
    accepted_identity_rule: str
    quarantine_rule: str
    membership_mutation_rule: str

    def payload(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "status": self.status,
            "source_universe_policy_id": self.source_universe_policy_id,
            "identity_policy_id": self.identity_policy_id,
            "identity_audit_lookback_days": self.identity_audit_lookback_days,
            "accepted_identity_rule": self.accepted_identity_rule,
            "quarantine_rule": self.quarantine_rule,
            "membership_mutation_rule": self.membership_mutation_rule,
        }

    @property
    def fingerprint(self) -> str:
        return json_fingerprint(self.payload())


def identity_resolved_universe_v0_1_policy(
) -> FrozenIdentityResolvedUniversePolicy:
    return FrozenIdentityResolvedUniversePolicy(
        policy_id=IDENTITY_RESOLVED_UNIVERSE_POLICY_ID,
        status=IDENTITY_RESOLVED_UNIVERSE_POLICY_STATUS,
        source_universe_policy_id=HISTORICAL_UNIVERSE_POLICY_ID,
        identity_policy_id=IDENTITY_POLICY_ID,
        identity_audit_lookback_days=IDENTITY_AUDIT_LOOKBACK_DAYS,
        accepted_identity_rule=(
            "composite_figi_else_unique_nonblank_cik_when_figi_missing"
        ),
        quarantine_rule="missing_composite_figi_and_no_unique_cik_fallback",
        membership_mutation_rule=(
            "remove_exactly_audit_quarantine_and_attach_selected_identity"
        ),
    )


def identity_resolved_universe_v0_1_manifest() -> dict[str, object]:
    policy = identity_resolved_universe_v0_1_policy()
    return {**policy.payload(), "fingerprint": policy.fingerprint}


def _normalized_provisional_rows(
    rows: Iterable[dict[str, object]],
) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for source in rows:
        row = dict(source)
        ticker = _text(row.get("ticker"), upper=True)
        if not ticker:
            raise ValueError("provisional identity row is missing ticker")
        if ticker in seen:
            raise ValueError(f"provisional identity rows repeat ticker {ticker}")
        if row.get("included") is not True:
            raise ValueError("identity resolution accepts included rows only")
        seen.add(ticker)
        row["ticker"] = ticker
        normalized.append(row)
    return sorted(normalized, key=lambda row: str(row["ticker"]))


def provisional_membership_fingerprint(
    rows: Iterable[dict[str, object]],
) -> str:
    """Reproduce the membership hash emitted by the provisional v0.1 builder."""

    normalized = _normalized_provisional_rows(rows)
    projection = [
        {
            "ticker": row["ticker"],
            "security_type": _text(row.get("selected_security_type"), upper=True),
            "primary_exchange": _text(
                row.get("selected_primary_exchange"), upper=True
            ),
            "cik": _text(row.get("selected_cik")),
            "composite_figi": _text(
                row.get("selected_composite_figi"), upper=True
            ),
        }
        for row in normalized
    ]
    return json_fingerprint(projection)


def resolve_identity_membership(
    provisional_rows: Iterable[dict[str, object]],
    accepted_statuses: Iterable[dict[str, object]],
    quarantined_statuses: Iterable[dict[str, object]],
) -> list[dict[str, object]]:
    """Apply exactly one complete identity status decision to every input row."""

    normalized = _normalized_provisional_rows(provisional_rows)
    by_ticker = {str(row["ticker"]): row for row in normalized}

    accepted: dict[str, dict[str, str]] = {}
    for source in accepted_statuses:
        ticker = _text(source.get("ticker"), upper=True)
        kind = _text(source.get("identifier_kind"))
        identifier = _text(
            source.get("identifier"), upper=kind == "composite_figi"
        )
        if not ticker or not kind or not identifier:
            raise ValueError("accepted identity status is incomplete")
        if ticker in accepted:
            raise ValueError(f"accepted identity repeats ticker {ticker}")
        if kind not in {"composite_figi", "unique_cik_fallback"}:
            raise ValueError(f"unsupported accepted identity kind {kind!r}")
        accepted[ticker] = {
            "identity_identifier_kind": kind,
            "identity_identifier": identifier,
        }

    quarantined: dict[str, dict[str, str]] = {}
    for source in quarantined_statuses:
        ticker = _text(source.get("ticker"), upper=True)
        reason = _text(source.get("reason"))
        if not ticker or not reason:
            raise ValueError("quarantined identity status is incomplete")
        if ticker in quarantined:
            raise ValueError(f"identity quarantine repeats ticker {ticker}")
        quarantined[ticker] = {
            "cik": _text(source.get("cik")),
            "composite_figi": _text(
                source.get("composite_figi"), upper=True
            ),
            "reason": reason,
        }

    overlap = set(accepted) & set(quarantined)
    if overlap:
        raise ValueError(f"identity statuses overlap: {sorted(overlap)}")
    status_tickers = set(accepted) | set(quarantined)
    if status_tickers != set(by_ticker):
        missing = sorted(set(by_ticker) - status_tickers)
        extra = sorted(status_tickers - set(by_ticker))
        raise ValueError(
            f"identity statuses do not cover provisional membership; "
            f"missing={missing}, extra={extra}"
        )

    resolved: list[dict[str, object]] = []
    for ticker in sorted(accepted):
        row = dict(by_ticker[ticker])
        identity = accepted[ticker]
        kind = identity["identity_identifier_kind"]
        identifier = identity["identity_identifier"]
        figi = _text(row.get("selected_composite_figi"), upper=True)
        cik = _text(row.get("selected_cik"))
        if kind == "composite_figi" and identifier != figi:
            raise ValueError(f"Composite FIGI mismatch for {ticker}")
        if kind == "unique_cik_fallback" and (figi or identifier != cik):
            raise ValueError(f"unique CIK fallback mismatch for {ticker}")
        row.update(identity)
        resolved.append(row)

    for ticker, status in quarantined.items():
        row = by_ticker[ticker]
        if status["cik"] != _text(row.get("selected_cik")):
            raise ValueError(f"quarantine CIK mismatch for {ticker}")
        if status["composite_figi"] != _text(
            row.get("selected_composite_figi"), upper=True
        ):
            raise ValueError(f"quarantine Composite FIGI mismatch for {ticker}")
    return resolved


def identity_resolved_membership_fingerprint(
    rows: Iterable[dict[str, object]],
) -> str:
    projection = []
    seen: set[str] = set()
    for source in rows:
        ticker = _text(source.get("ticker"), upper=True)
        if not ticker:
            raise ValueError("resolved identity row is missing ticker")
        if ticker in seen:
            raise ValueError(f"resolved identity rows repeat ticker {ticker}")
        seen.add(ticker)
        projection.append(
            {
                "ticker": ticker,
                "security_type": _text(
                    source.get("selected_security_type"), upper=True
                ),
                "primary_exchange": _text(
                    source.get("selected_primary_exchange"), upper=True
                ),
                "cik": _text(source.get("selected_cik")),
                "composite_figi": _text(
                    source.get("selected_composite_figi"), upper=True
                ),
                "identity_identifier_kind": _text(
                    source.get("identity_identifier_kind")
                ),
                "identity_identifier": _text(
                    source.get("identity_identifier"),
                    upper=(
                        _text(source.get("identity_identifier_kind"))
                        == "composite_figi"
                    ),
                ),
            }
        )
    return json_fingerprint(sorted(projection, key=lambda row: row["ticker"]))
