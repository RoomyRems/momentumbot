"""Label-blind semantic audit for provider instrument metadata.

Massive's ticker ``type`` field is useful but not sufficient on its own.  Live
cross-sectional censuses contain rows coded ``CS`` or ``ADRC`` whose names
explicitly describe preferred shares, exchange-listed debt, or rights.  This
module freezes narrow contradiction rules before an eligibility policy is
allowed to consume those fields.

The audit is deliberately not an eligibility classifier.  A row with no
detected contradiction is only "not contradicted by these rules"; it is not
thereby proven to be a strategy-eligible common equity.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re

from .providers.massive import normalize_reference_tickers


INSTRUMENT_METADATA_AUDIT_ID = "massive-instrument-metadata-audit-v0.1"
INSTRUMENT_METADATA_AUDIT_STATUS = "frozen_research_audit_not_eligibility"
COMMON_TYPE_FAMILY = ("ADRC", "CS")

_RULE_PATTERNS: dict[str, tuple[str, ...]] = {
    "explicit_preferred": (
        r"\bPREFERRED\s+(?:STOCK|SHARES?|UNITS?|CLASS|SERIES)\b",
        r"\bPREFERENCE\s+SHARES?\b",
        r"\bPFD\b",
    ),
    "explicit_debt": (
        r"\bNOTES?\b",
        r"\bDEBENTURES?\b",
        r"\bBONDS\b",
    ),
    "explicit_rights": (r"\bRIGHTS\b",),
    "explicit_warrant": (r"\bWARRANTS?\b",),
    "depositary_structure_review": (r"\bDEPOSITARY\s+SHARES\b",),
    "unit_structure_review": (r"\bUNITS?\b",),
}
_RULE_EXCLUSION_PATTERNS: dict[str, tuple[str, ...]] = {
    "depositary_structure_review": (
        r"AMERICAN\s+DEPOSITARY\s+SHARES\b",
        r"GLOBAL\s+DEPOSITARY\s+SHARES\b",
    ),
}
_COMPILED_RULES = {
    rule: tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)
    for rule, patterns in _RULE_PATTERNS.items()
}
_COMPILED_RULE_EXCLUSIONS = {
    rule: tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)
    for rule, patterns in _RULE_EXCLUSION_PATTERNS.items()
}
_EXPLICIT_NON_COMMON_FLAGS = frozenset(
    {
        "explicit_preferred",
        "explicit_debt",
        "explicit_rights",
        "explicit_warrant",
    }
)


class InstrumentMetadataStatus(str, Enum):
    OUTSIDE_COMMON_TYPE_FAMILY = "outside_common_type_family"
    MISSING_NAME_REVIEW = "missing_name_review"
    EXPLICIT_NON_COMMON_CONFLICT = "explicit_non_common_name_conflict"
    STRUCTURE_REVIEW = "instrument_structure_review"
    NO_NAME_CONFLICT_DETECTED = "no_name_conflict_detected"


@dataclass(frozen=True, slots=True)
class InstrumentMetadataAudit:
    ticker: str
    security_type: str
    name: str
    flags: tuple[str, ...]
    status: InstrumentMetadataStatus

    def payload(self) -> dict[str, object]:
        return {
            "ticker": self.ticker,
            "security_type": self.security_type,
            "name": self.name,
            "flags": list(self.flags),
            "status": self.status.value,
        }


def instrument_metadata_audit_manifest() -> dict[str, object]:
    payload: dict[str, object] = {
        "audit_id": INSTRUMENT_METADATA_AUDIT_ID,
        "status": INSTRUMENT_METADATA_AUDIT_STATUS,
        "common_type_family": list(COMMON_TYPE_FAMILY),
        "rule_patterns": {
            key: list(value) for key, value in sorted(_RULE_PATTERNS.items())
        },
        "rule_exclusion_patterns": {
            key: list(value)
            for key, value in sorted(_RULE_EXCLUSION_PATTERNS.items())
        },
        "interpretation": (
            "No detected name contradiction is not proof of common-equity "
            "eligibility. Explicit conflicts fail closed; unit structures and "
            "missing names require separate review."
        ),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {**payload, "fingerprint": hashlib.sha256(encoded).hexdigest()}


def instrument_name_flags(name: str) -> tuple[str, ...]:
    return tuple(
        rule
        for rule, patterns in sorted(_COMPILED_RULES.items())
        if any(pattern.search(name) for pattern in patterns)
        and not any(
            pattern.search(name)
            for pattern in _COMPILED_RULE_EXCLUSIONS.get(rule, ())
        )
    )


def audit_instrument_metadata(row: dict[str, object]) -> InstrumentMetadataAudit:
    normalized = normalize_reference_tickers([row])[0]
    ticker = str(normalized["ticker"])
    security_type = str(normalized["type"])
    name = str(normalized["name"])
    flags = instrument_name_flags(name)

    if security_type not in COMMON_TYPE_FAMILY:
        status = InstrumentMetadataStatus.OUTSIDE_COMMON_TYPE_FAMILY
    elif not name:
        status = InstrumentMetadataStatus.MISSING_NAME_REVIEW
    elif _EXPLICIT_NON_COMMON_FLAGS.intersection(flags):
        status = InstrumentMetadataStatus.EXPLICIT_NON_COMMON_CONFLICT
    elif {
        "depositary_structure_review",
        "unit_structure_review",
    }.intersection(flags):
        status = InstrumentMetadataStatus.STRUCTURE_REVIEW
    else:
        status = InstrumentMetadataStatus.NO_NAME_CONFLICT_DETECTED

    return InstrumentMetadataAudit(
        ticker=ticker,
        security_type=security_type,
        name=name,
        flags=flags,
        status=status,
    )
