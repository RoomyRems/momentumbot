"""Final-summarizer identity compatibility for sealed recovery v0.11.

The v0.10 provider checkpoint contains the authoritative identity vocabulary
already frozen by v0.6: ``composite_figi`` and ``unique_cik_fallback``.  The
legacy final source summarizer reloads the float root through
``historical_float_v04`` after the scanner adapter has restored that module's
obsolete validator.  This module applies the audited v0.6 identity rule only
around that final deep replay and always restores the parent implementation.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from momentumbot import historical_float_v04 as float_parent
from momentumbot.historical_float_identity_v06 import candidate_identity_v06
from momentumbot.historical_float_identity_v09 import (
    EXPECTED_CANDIDATE_COUNT,
    EXPECTED_DATES,
    EXPECTED_FLOAT_RECORD_COUNT,
    EXPECTED_FLOAT_ROOT_CONTENT_SHA256,
    EXPECTED_KIND_COUNTS,
    EXPECTED_MARKET_ROOT_CONTENT_SHA256,
    build_downstream_identity_preflight_receipt,
    canonical_fingerprint,
)
from momentumbot.models import StrategyProfile
from momentumbot.research.sealed_historical_source_acquisition_v04 import (
    DeepValidationAPIs,
    summarize_source_root_v04,
)


ARTIFACT_ID = "causal-final-source-identity-preflight-v0.1"
SCHEMA_VERSION = 1


@contextmanager
def authoritative_float_identity_v11() -> Iterator[None]:
    """Temporarily make the final deep replay use the authoritative rule."""

    original = float_parent._candidate_identity
    float_parent._candidate_identity = candidate_identity_v06
    try:
        yield
    finally:
        float_parent._candidate_identity = original


def validate_final_identity_preflight_receipt(
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
        "legacy_downstream_preflight_content_sha256",
        "protected_loader",
        "causal_boundary",
        "content_sha256",
    }
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise ValueError("final identity preflight fields are invalid")
    claimed = payload.get("content_sha256")
    unsigned = {
        key: value for key, value in payload.items() if key != "content_sha256"
    }
    if claimed != canonical_fingerprint(unsigned):
        raise ValueError("final identity preflight hash mismatch")
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
        raise ValueError("final identity preflight census changed")
    legacy_hash = payload.get("legacy_downstream_preflight_content_sha256")
    if not isinstance(legacy_hash, str) or len(legacy_hash) != 64:
        raise ValueError("final identity preflight lineage hash is invalid")
    if payload.get("protected_loader") != "final_source_deep_replay_summarizer":
        raise ValueError("final identity preflight loader changed")
    if payload.get("causal_boundary") != {
        "float_records_rewritten": False,
        "identity_values_rewritten": False,
        "provider_calls_performed": False,
        "strategy_or_float_threshold_changed": False,
        "transcript_or_label_values_read": False,
    }:
        raise ValueError("final identity preflight causal boundary changed")
    return payload


def build_final_identity_preflight_receipt(
    source_root: str | Path,
) -> dict[str, object]:
    """Replay all 946 market/float identities before the final summarizer."""

    legacy = build_downstream_identity_preflight_receipt(source_root)
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": ARTIFACT_ID,
        "dates": list(EXPECTED_DATES),
        "candidate_count": legacy["candidate_count"],
        "float_record_count": legacy["float_record_count"],
        "identity_kind_counts": legacy["identity_kind_counts"],
        "accepted_identity_kinds": legacy["accepted_identity_kinds"],
        "source_market_root_content_sha256": legacy[
            "source_market_root_content_sha256"
        ],
        "source_float_root_content_sha256": legacy[
            "source_float_root_content_sha256"
        ],
        "legacy_downstream_preflight_content_sha256": legacy["content_sha256"],
        "protected_loader": "final_source_deep_replay_summarizer",
        "causal_boundary": {
            "float_records_rewritten": False,
            "identity_values_rewritten": False,
            "provider_calls_performed": False,
            "strategy_or_float_threshold_changed": False,
            "transcript_or_label_values_read": False,
        },
    }
    payload["content_sha256"] = canonical_fingerprint(payload)
    return validate_final_identity_preflight_receipt(payload)


def summarize_source_root_identity_compatible_v11(
    source_root: str | Path,
    *,
    profile: StrategyProfile,
    _apis: DeepValidationAPIs | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    """Preflight every identity, then deep-replay under the narrow adapter."""

    receipt = build_final_identity_preflight_receipt(source_root)
    with authoritative_float_identity_v11():
        summary = summarize_source_root_v04(
            source_root,
            profile=profile,
            _apis=_apis,
        )
    return summary, receipt


__all__ = [
    "ARTIFACT_ID",
    "authoritative_float_identity_v11",
    "build_final_identity_preflight_receipt",
    "summarize_source_root_identity_compatible_v11",
    "validate_final_identity_preflight_receipt",
]
