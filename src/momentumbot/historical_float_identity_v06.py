"""Identity compatibility gate for sealed historical float recovery v0.6.

The normalized market-candidate contract has always admitted exactly two
stable identity kinds: ``composite_figi`` and ``unique_cik_fallback``.  The
consumed float implementation accidentally used the obsolete label ``cik``
for the latter.  This module changes no identity value or float policy; it
only makes the downstream validator consume the authoritative vocabulary.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from momentumbot.causal_market_discovery_v03 import load_market_candidate_payload
from momentumbot.research.sealed_historical_availability import SELECTED_DATES


ARTIFACT_ID = "causal-float-identity-compatibility-preflight-v0.1"
SCHEMA_VERSION = 1
EXPECTED_DATES = tuple(SELECTED_DATES)
EXPECTED_CANDIDATE_COUNT = 946
EXPECTED_KIND_COUNTS = {
    "composite_figi": 737,
    "unique_cik_fallback": 209,
}
EXPECTED_MARKET_ROOT_CONTENT_SHA256 = (
    "206431d94f8b6359fceb9627abb2d07acdcde414de2bfed351411b4b08e55852"
)


def canonical_fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def candidate_identity_v06(candidate: dict[str, object]) -> dict[str, str]:
    """Return the unchanged stable identity under the upstream contract."""

    identity = {
        "symbol": str(candidate.get("symbol") or ""),
        "selected_cik": str(candidate.get("selected_cik") or ""),
        "selected_composite_figi": str(
            candidate.get("selected_composite_figi") or ""
        ),
        "identity_identifier_kind": str(
            candidate.get("identity_identifier_kind") or ""
        ),
        "identity_identifier": str(candidate.get("identity_identifier") or ""),
    }
    if not identity["symbol"]:
        raise ValueError("float candidate identity lacks a symbol")
    if not identity["identity_identifier_kind"] or not identity["identity_identifier"]:
        raise ValueError("float candidate lacks a stable identity")
    kind = identity["identity_identifier_kind"]
    identifier = identity["identity_identifier"]
    figi = identity["selected_composite_figi"]
    cik = identity["selected_cik"]
    if kind == "composite_figi":
        if not figi or identifier != figi:
            raise ValueError("float candidate Composite FIGI identity mismatch")
    elif kind == "unique_cik_fallback":
        if figi or not cik or identifier != cik:
            raise ValueError("float candidate unique CIK fallback identity mismatch")
    else:
        raise ValueError("float candidate identity kind is unsupported")
    return identity


def validate_identity_preflight_receipt(payload: object) -> dict[str, object]:
    expected_keys = {
        "schema_version",
        "artifact_id",
        "dates",
        "candidate_count",
        "identity_kind_counts",
        "accepted_identity_kinds",
        "source_market_root_content_sha256",
        "causal_boundary",
        "content_sha256",
    }
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise ValueError("float identity preflight fields are invalid")
    claimed = payload.get("content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if claimed != canonical_fingerprint(unsigned):
        raise ValueError("float identity preflight hash mismatch")
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("artifact_id") != ARTIFACT_ID
        or payload.get("dates") != list(EXPECTED_DATES)
        or payload.get("candidate_count") != EXPECTED_CANDIDATE_COUNT
        or payload.get("identity_kind_counts") != EXPECTED_KIND_COUNTS
        or payload.get("accepted_identity_kinds") != list(EXPECTED_KIND_COUNTS)
        or payload.get("source_market_root_content_sha256")
        != EXPECTED_MARKET_ROOT_CONTENT_SHA256
    ):
        raise ValueError("float identity preflight census changed")
    if payload.get("causal_boundary") != {
        "identity_values_rewritten": False,
        "provider_calls_performed": False,
        "strategy_or_float_threshold_changed": False,
        "transcript_or_label_values_read": False,
    }:
        raise ValueError("float identity preflight causal boundary changed")
    return payload


def build_identity_preflight_receipt(
    market_root: str | Path,
) -> dict[str, object]:
    root = Path(market_root)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("market discovery root manifest must be an object")
    if (
        manifest.get("dates") != list(EXPECTED_DATES)
        or manifest.get("content_sha256") != EXPECTED_MARKET_ROOT_CONTENT_SHA256
    ):
        raise ValueError("float identity preflight market root changed")
    counts = {kind: 0 for kind in EXPECTED_KIND_COUNTS}
    observed_dates: list[str] = []
    candidate_count = 0
    for value in EXPECTED_DATES:
        rows, _, _ = load_market_candidate_payload(root / value)
        observed_dates.append(value)
        for candidate in rows:
            identity = candidate_identity_v06(candidate)
            counts[identity["identity_identifier_kind"]] += 1
            candidate_count += 1
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": ARTIFACT_ID,
        "dates": observed_dates,
        "candidate_count": candidate_count,
        "identity_kind_counts": counts,
        "accepted_identity_kinds": list(EXPECTED_KIND_COUNTS),
        "source_market_root_content_sha256": EXPECTED_MARKET_ROOT_CONTENT_SHA256,
        "causal_boundary": {
            "identity_values_rewritten": False,
            "provider_calls_performed": False,
            "strategy_or_float_threshold_changed": False,
            "transcript_or_label_values_read": False,
        },
    }
    payload["content_sha256"] = canonical_fingerprint(payload)
    return validate_identity_preflight_receipt(payload)


__all__ = [
    "ARTIFACT_ID",
    "EXPECTED_CANDIDATE_COUNT",
    "EXPECTED_KIND_COUNTS",
    "build_identity_preflight_receipt",
    "candidate_identity_v06",
    "validate_identity_preflight_receipt",
]
