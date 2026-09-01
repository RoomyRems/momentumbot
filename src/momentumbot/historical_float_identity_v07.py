"""Downstream identity compatibility gate for sealed recovery v0.7.

The v0.6 float builder wrote authoritative candidate identities, but the
unchanged news and scanner builders reload those records through the legacy
``historical_float_v04`` validator.  That validator still recognizes the
obsolete kind ``cik`` instead of ``unique_cik_fallback``.  This module applies
the already-audited v0.6 identity rule only while downstream float artifacts
are being validated and proves, provider-free, that every retained candidate
and float record can be loaded before any provider client is constructed.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
from typing import Iterator

from momentumbot import historical_float_v04 as float_parent
from momentumbot.causal_market_discovery_v03 import (
    load_market_candidate_payload,
)
from momentumbot.historical_float_identity_v06 import candidate_identity_v06
from momentumbot.historical_float_v04 import (
    load_causal_float_records,
    load_causal_float_root,
    load_float_target_basis,
)
from momentumbot.identity_resolved_universe import json_fingerprint
from momentumbot.research.sealed_historical_availability import SELECTED_DATES


ARTIFACT_ID = "causal-downstream-float-identity-preflight-v0.1"
SCHEMA_VERSION = 1
EXPECTED_DATES = tuple(SELECTED_DATES)
EXPECTED_CANDIDATE_COUNT = 946
EXPECTED_FLOAT_RECORD_COUNT = 946
EXPECTED_KIND_COUNTS = {
    "composite_figi": 737,
    "unique_cik_fallback": 209,
}
EXPECTED_MARKET_ROOT_CONTENT_SHA256 = (
    "206431d94f8b6359fceb9627abb2d07acdcde414de2bfed351411b4b08e55852"
)
EXPECTED_FLOAT_ROOT_CONTENT_SHA256 = (
    "eac2a02d24cb0106181480355778c5094ed9436769d75356bd2d1ee90de4a9cc"
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


@contextmanager
def authoritative_float_identity_v07() -> Iterator[None]:
    """Temporarily make every downstream float load use the v0.6 rule."""

    original = float_parent._candidate_identity
    float_parent._candidate_identity = candidate_identity_v06
    try:
        yield
    finally:
        float_parent._candidate_identity = original


def validate_downstream_identity_preflight_receipt(
    payload: object,
) -> dict[str, object]:
    expected_keys = {
        "schema_version",
        "artifact_id",
        "dates",
        "candidate_count",
        "float_record_count",
        "identity_kind_counts",
        "accepted_identity_kinds",
        "source_market_root_content_sha256",
        "source_float_root_content_sha256",
        "downstream_loaders",
        "causal_boundary",
        "content_sha256",
    }
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise ValueError("downstream identity preflight fields are invalid")
    claimed = payload.get("content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if claimed != canonical_fingerprint(unsigned):
        raise ValueError("downstream identity preflight hash mismatch")
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("artifact_id") != ARTIFACT_ID
        or payload.get("dates") != list(EXPECTED_DATES)
        or payload.get("candidate_count") != EXPECTED_CANDIDATE_COUNT
        or payload.get("float_record_count") != EXPECTED_FLOAT_RECORD_COUNT
        or payload.get("identity_kind_counts") != EXPECTED_KIND_COUNTS
        or payload.get("accepted_identity_kinds") != list(EXPECTED_KIND_COUNTS)
        or payload.get("source_market_root_content_sha256")
        != EXPECTED_MARKET_ROOT_CONTENT_SHA256
        or payload.get("source_float_root_content_sha256")
        != EXPECTED_FLOAT_ROOT_CONTENT_SHA256
    ):
        raise ValueError("downstream identity preflight census changed")
    if payload.get("downstream_loaders") != [
        "publication_timed_news",
        "canonical_scanner_source_inputs",
    ]:
        raise ValueError("downstream identity preflight loader closure changed")
    if payload.get("causal_boundary") != {
        "float_records_rewritten": False,
        "identity_values_rewritten": False,
        "provider_calls_performed": False,
        "strategy_or_float_threshold_changed": False,
        "transcript_or_label_values_read": False,
    }:
        raise ValueError("downstream identity preflight causal boundary changed")
    return payload


def build_downstream_identity_preflight_receipt(
    source_root: str | Path,
) -> dict[str, object]:
    root = Path(source_root)
    market_root = root / "causal-market-discovery-v0.3"
    float_root = root / "causal-sec-float-v0.2"
    market_manifest = json.loads(
        (market_root / "manifest.json").read_text(encoding="utf-8")
    )
    if not isinstance(market_manifest, dict) or (
        market_manifest.get("dates") != list(EXPECTED_DATES)
        or market_manifest.get("content_sha256")
        != EXPECTED_MARKET_ROOT_CONTENT_SHA256
    ):
        raise ValueError("downstream identity preflight market root changed")
    kind_counts = {kind: 0 for kind in EXPECTED_KIND_COUNTS}
    candidate_count = 0
    float_record_count = 0
    with authoritative_float_identity_v07():
        float_manifest = load_causal_float_root(
            float_root,
            expected_source_market_discovery_bundle_sha256=(
                EXPECTED_MARKET_ROOT_CONTENT_SHA256
            ),
        )
        if (
            float_manifest.get("dates") != list(EXPECTED_DATES)
            or float_manifest.get("content_sha256")
            != EXPECTED_FLOAT_ROOT_CONTENT_SHA256
        ):
            raise ValueError("downstream identity preflight float root changed")
        for value in EXPECTED_DATES:
            candidates, candidate_payload, market_date_manifest = (
                load_market_candidate_payload(market_root / value)
            )
            target_relative = market_date_manifest.get("files", {}).get(
                "float_target_basis"
            )
            if not isinstance(target_relative, str) or not target_relative:
                raise ValueError("downstream identity preflight target basis is missing")
            target_path = Path(target_relative)
            if target_path.is_absolute() or ".." in target_path.parts:
                raise ValueError("downstream identity preflight target basis escaped")
            _target_pairs, target_payload = load_float_target_basis(
                market_root / value / target_path,
                candidate_rows=candidates,
                candidate_payload=candidate_payload,
                expected_trading_date=value,
            )
            target_sha = target_payload.get("content_sha256")
            if (
                not isinstance(target_sha, str)
                or market_date_manifest.get("summary", {}).get(
                    "float_target_basis_sha256"
                )
                != target_sha
            ):
                raise ValueError("downstream identity target-basis lineage changed")
            records, _float_date_manifest = load_causal_float_records(
                float_root / value,
                candidate_rows=candidates,
                candidate_payload=candidate_payload,
                expected_trading_date=value,
                expected_source_market_discovery_manifest_sha256=json_fingerprint(
                    market_date_manifest
                ),
                expected_source_float_target_basis_sha256=target_sha,
            )
            for candidate in candidates:
                identity = candidate_identity_v06(candidate)
                kind_counts[identity["identity_identifier_kind"]] += 1
            candidate_count += len(candidates)
            float_record_count += len(records)

    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": ARTIFACT_ID,
        "dates": list(EXPECTED_DATES),
        "candidate_count": candidate_count,
        "float_record_count": float_record_count,
        "identity_kind_counts": kind_counts,
        "accepted_identity_kinds": list(EXPECTED_KIND_COUNTS),
        "source_market_root_content_sha256": EXPECTED_MARKET_ROOT_CONTENT_SHA256,
        "source_float_root_content_sha256": EXPECTED_FLOAT_ROOT_CONTENT_SHA256,
        "downstream_loaders": [
            "publication_timed_news",
            "canonical_scanner_source_inputs",
        ],
        "causal_boundary": {
            "float_records_rewritten": False,
            "identity_values_rewritten": False,
            "provider_calls_performed": False,
            "strategy_or_float_threshold_changed": False,
            "transcript_or_label_values_read": False,
        },
    }
    payload["content_sha256"] = canonical_fingerprint(payload)
    return validate_downstream_identity_preflight_receipt(payload)


__all__ = [
    "ARTIFACT_ID",
    "EXPECTED_CANDIDATE_COUNT",
    "EXPECTED_FLOAT_RECORD_COUNT",
    "EXPECTED_KIND_COUNTS",
    "authoritative_float_identity_v07",
    "build_downstream_identity_preflight_receipt",
    "validate_downstream_identity_preflight_receipt",
]
