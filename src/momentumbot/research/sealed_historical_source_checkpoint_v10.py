"""Versioned checkpoint adapter for sealed historical source recovery v0.10.

The final pre/post-scanner layout remains 706/767 files because v0.10 recovers
the complete 645-file market/float/news source, discards the one-file partial
scanner tape, and adds 61 complete scanner-source files before the
credential-free 61-file scanner freeze.
This adapter reuses the audited checkpoint implementation while rebinding its
immutable authority, parent receipt, workflow, and cumulative request seed.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Mapping

from momentumbot.research import sealed_historical_source_checkpoint_v05 as parent
from momentumbot.research.sealed_historical_source_recovery_v10 import (
    ARTIFACT_ID as RECOVERY_ARTIFACT_ID,
    PARENT_REQUEST_BUDGET,
)


AUTHORIZATION_ID = "sealed-historical-source-acquisition-v0.10"
ARTIFACT_ID = "sealed-historical-source-checkpoint-v0.3"
ARTIFACT_TYPE = "sealed_historical_label_blind_source_recovery_checkpoint_v0_10"
POST_SCANNER_BINDING_TYPE = (
    "sealed_historical_source_recovery_checkpoint_post_scanner_binding_v0.3"
)
EXPECTED_SCANNER_ADDITION_ID = parent.EXPECTED_SCANNER_ADDITION_ID
EXPECTED_REPOSITORY = parent.EXPECTED_REPOSITORY
EXPECTED_WORKFLOW_REF = (
    "RoomyRems/momentumbot/.github/workflows/"
    "sealed-historical-source-acquisition-v10.yml@refs/heads/main"
)
RECOVERY_RECEIPT_CONTENT_SHA256 = (
    "776470b9616c582b229f9e0118c0a31338639f17c33878676c85997ab3d3d750"
)
EXPECTED_ALLOWED_HOSTS = parent.EXPECTED_ALLOWED_HOSTS
EXPECTED_DATES = parent.EXPECTED_DATES
EXPECTED_PRE_SCANNER_FILE_COUNT = parent.EXPECTED_PRE_SCANNER_FILE_COUNT
EXPECTED_POST_SCANNER_FILE_COUNT = parent.EXPECTED_POST_SCANNER_FILE_COUNT
RECOVERY_RECEIPT_BASENAME = parent.RECOVERY_RECEIPT_BASENAME
NORMALIZATION_DIAGNOSTIC_ARTIFACT_ID = (
    parent.NORMALIZATION_DIAGNOSTIC_ARTIFACT_ID
)
NORMALIZATION_DIAGNOSTIC_BASENAME = parent.NORMALIZATION_DIAGNOSTIC_BASENAME
MAX_HTTP_ATTEMPTS = parent.MAX_HTTP_ATTEMPTS
MAX_RETAINED_BYTES = parent.MAX_RETAINED_BYTES
canonical_fingerprint = parent.canonical_fingerprint
_file_sha256 = parent._file_sha256
normalize_blocked_attempt_ledger = parent.normalize_blocked_attempt_ledger
output_is_outside_source_root = parent.output_is_outside_source_root
write_checkpoint_once = parent.write_checkpoint_once


def _rebindings() -> dict[str, object]:
    """Resolve contract values at call time so tests can use signed fixtures."""

    return {
        "AUTHORIZATION_ID": AUTHORIZATION_ID,
        "ARTIFACT_ID": ARTIFACT_ID,
        "ARTIFACT_TYPE": ARTIFACT_TYPE,
        "POST_SCANNER_BINDING_TYPE": POST_SCANNER_BINDING_TYPE,
        "EXPECTED_WORKFLOW_REF": EXPECTED_WORKFLOW_REF,
        "RECOVERY_ARTIFACT_ID": RECOVERY_ARTIFACT_ID,
        "RECOVERY_RECEIPT_CONTENT_SHA256": RECOVERY_RECEIPT_CONTENT_SHA256,
        "PARENT_REQUEST_BUDGET": PARENT_REQUEST_BUDGET,
    }


@contextmanager
def _v10_contract() -> Iterator[None]:
    rebindings = _rebindings()
    original = {name: getattr(parent, name) for name in rebindings}
    for name, value in rebindings.items():
        setattr(parent, name, value)
    try:
        yield
    finally:
        for name, value in original.items():
            setattr(parent, name, value)


def validate_authorization_envelope_v10(
    authorization: Mapping[str, object],
) -> dict[str, object]:
    with _v10_contract():
        return parent.validate_authorization_envelope_v05(authorization)


def load_authorization_envelope_v10(path: str | Path) -> dict[str, object]:
    with _v10_contract():
        return parent.load_authorization_envelope_v05(path)


def normalize_composite_request_budget(
    payload: Mapping[str, object],
) -> dict[str, object]:
    with _v10_contract():
        normalized = parent.normalize_composite_request_budget(payload)
    for host in ("api.massive.com", "data.sec.gov"):
        if normalized["by_host"].get(host) != PARENT_REQUEST_BUDGET["by_host"][host]:
            raise ValueError(f"v0.10 composite request budget repeated prohibited {host}")
    return normalized


def build_source_checkpoint_v10(**kwargs: object) -> dict[str, object]:
    with _v10_contract():
        return parent.build_source_checkpoint_v05(**kwargs)  # type: ignore[arg-type]


def validate_source_checkpoint_v10(
    checkpoint: Mapping[str, object],
    **kwargs: object,
) -> dict[str, object]:
    with _v10_contract():
        return parent.validate_source_checkpoint_v05(  # type: ignore[arg-type]
            checkpoint,
            **kwargs,
        )


def build_post_scanner_checkpoint_binding_v10(
    checkpoint: Mapping[str, object],
    **kwargs: object,
) -> dict[str, object]:
    with _v10_contract():
        return parent.build_post_scanner_checkpoint_binding_v05(  # type: ignore[arg-type]
            checkpoint,
            **kwargs
        )


def validate_post_scanner_checkpoint_binding_v10(
    binding: Mapping[str, object],
) -> dict[str, object]:
    with _v10_contract():
        return parent.validate_post_scanner_checkpoint_binding_v05(binding)


__all__ = [
    "ARTIFACT_ID",
    "AUTHORIZATION_ID",
    "EXPECTED_ALLOWED_HOSTS",
    "EXPECTED_DATES",
    "EXPECTED_PRE_SCANNER_FILE_COUNT",
    "EXPECTED_POST_SCANNER_FILE_COUNT",
    "EXPECTED_REPOSITORY",
    "EXPECTED_SCANNER_ADDITION_ID",
    "EXPECTED_WORKFLOW_REF",
    "MAX_HTTP_ATTEMPTS",
    "MAX_RETAINED_BYTES",
    "NORMALIZATION_DIAGNOSTIC_ARTIFACT_ID",
    "NORMALIZATION_DIAGNOSTIC_BASENAME",
    "POST_SCANNER_BINDING_TYPE",
    "RECOVERY_RECEIPT_BASENAME",
    "build_post_scanner_checkpoint_binding_v10",
    "build_source_checkpoint_v10",
    "canonical_fingerprint",
    "load_authorization_envelope_v10",
    "normalize_blocked_attempt_ledger",
    "normalize_composite_request_budget",
    "output_is_outside_source_root",
    "validate_authorization_envelope_v10",
    "validate_post_scanner_checkpoint_binding_v10",
    "validate_source_checkpoint_v10",
    "write_checkpoint_once",
]
