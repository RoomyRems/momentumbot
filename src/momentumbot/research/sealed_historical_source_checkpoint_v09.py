"""Versioned checkpoint adapter for sealed historical source recovery v0.9.

The final pre/post-scanner layout remains 706/767 files because v0.9 recovers
the completed 61-file float bundle and adds only the 61-file news bundle plus
61 scanner-source files before the credential-free 61-file scanner freeze.
This adapter reuses the audited checkpoint implementation while rebinding its
immutable authority, parent receipt, workflow, and cumulative request seed.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Mapping

from momentumbot.research import sealed_historical_source_checkpoint_v05 as parent
from momentumbot.research.sealed_historical_source_recovery_v09 import (
    ARTIFACT_ID as RECOVERY_ARTIFACT_ID,
    PARENT_REQUEST_BUDGET,
)


AUTHORIZATION_ID = "sealed-historical-source-acquisition-v0.9"
ARTIFACT_ID = "sealed-historical-source-checkpoint-v0.3"
ARTIFACT_TYPE = "sealed_historical_label_blind_source_recovery_checkpoint_v0_9"
POST_SCANNER_BINDING_TYPE = (
    "sealed_historical_source_recovery_checkpoint_post_scanner_binding_v0.3"
)
EXPECTED_SCANNER_ADDITION_ID = parent.EXPECTED_SCANNER_ADDITION_ID
EXPECTED_REPOSITORY = parent.EXPECTED_REPOSITORY
EXPECTED_WORKFLOW_REF = (
    "RoomyRems/momentumbot/.github/workflows/"
    "sealed-historical-source-acquisition-v09.yml@refs/heads/main"
)
RECOVERY_RECEIPT_CONTENT_SHA256 = (
    "44f020cb81c11c13ca8fb9729c9bd7cf05c540a89ed9f88be20c960a3b3eb342"
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
def _v09_contract() -> Iterator[None]:
    rebindings = _rebindings()
    original = {name: getattr(parent, name) for name in rebindings}
    for name, value in rebindings.items():
        setattr(parent, name, value)
    try:
        yield
    finally:
        for name, value in original.items():
            setattr(parent, name, value)


def validate_authorization_envelope_v09(
    authorization: Mapping[str, object],
) -> dict[str, object]:
    with _v09_contract():
        return parent.validate_authorization_envelope_v05(authorization)


def load_authorization_envelope_v09(path: str | Path) -> dict[str, object]:
    with _v09_contract():
        return parent.load_authorization_envelope_v05(path)


def normalize_composite_request_budget(
    payload: Mapping[str, object],
) -> dict[str, object]:
    with _v09_contract():
        normalized = parent.normalize_composite_request_budget(payload)
    for host in ("api.massive.com", "data.sec.gov"):
        if normalized["by_host"].get(host) != PARENT_REQUEST_BUDGET["by_host"][host]:
            raise ValueError(f"v0.9 composite request budget repeated prohibited {host}")
    return normalized


def build_source_checkpoint_v09(**kwargs: object) -> dict[str, object]:
    with _v09_contract():
        return parent.build_source_checkpoint_v05(**kwargs)  # type: ignore[arg-type]


def validate_source_checkpoint_v09(
    checkpoint: Mapping[str, object],
    **kwargs: object,
) -> dict[str, object]:
    with _v09_contract():
        return parent.validate_source_checkpoint_v05(  # type: ignore[arg-type]
            checkpoint,
            **kwargs,
        )


def build_post_scanner_checkpoint_binding_v09(
    checkpoint: Mapping[str, object],
    **kwargs: object,
) -> dict[str, object]:
    with _v09_contract():
        return parent.build_post_scanner_checkpoint_binding_v05(  # type: ignore[arg-type]
            checkpoint,
            **kwargs
        )


def validate_post_scanner_checkpoint_binding_v09(
    binding: Mapping[str, object],
) -> dict[str, object]:
    with _v09_contract():
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
    "build_post_scanner_checkpoint_binding_v09",
    "build_source_checkpoint_v09",
    "canonical_fingerprint",
    "load_authorization_envelope_v09",
    "normalize_blocked_attempt_ledger",
    "normalize_composite_request_budget",
    "output_is_outside_source_root",
    "validate_authorization_envelope_v09",
    "validate_post_scanner_checkpoint_binding_v09",
    "validate_source_checkpoint_v09",
    "write_checkpoint_once",
]
