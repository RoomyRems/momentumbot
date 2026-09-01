"""Single-fetch parent-artifact metadata gate for sealed recovery v0.8."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping


ARTIFACT_ID = 9_806_541_315
ARTIFACT_NAME = (
    "sealed-historical-source-acquisition-v06-failure-checkpoint-33521937708-1"
)
ARTIFACT_DIGEST = (
    "sha256:ab51a247d4fc86fef16203f8dc7fefb104abd71668a37ffc6e450e2513d469c35"
)
ARTIFACT_SIZE_BYTES = 43_338_553
PARENT_RUN_ID = 33_521_937_708
VALIDATOR_ID = "sealed-historical-parent-artifact-metadata-v0.8"
MAX_METADATA_BYTES = 1_000_000


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key is forbidden: {key}")
        output[key] = value
    return output


def canonical_fingerprint(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_metadata(path: str | Path) -> dict[str, object]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("artifact metadata input must be a regular file")
    size = source.stat().st_size
    if size <= 0 or size > MAX_METADATA_BYTES:
        raise ValueError("artifact metadata input size is invalid")
    payload = json.loads(
        source.read_text(encoding="utf-8"),
        parse_constant=_reject_json_constant,
        object_pairs_hook=_reject_duplicate_json_keys,
    )
    if not isinstance(payload, dict):
        raise ValueError("artifact metadata must be a JSON object")
    return payload


def _require_exact(
    payload: Mapping[str, object],
    field: str,
    expected: object,
    *,
    diagnostic_field: str | None = None,
) -> None:
    value = payload.get(field)
    if type(value) is not type(expected) or value != expected:
        label = diagnostic_field or field
        raise ValueError(f"artifact metadata field {label} changed")


def validate_parent_artifact_metadata_v08(
    payload: Mapping[str, object],
) -> dict[str, object]:
    """Validate one GitHub artifact response and return a hash-bound receipt."""

    _require_exact(payload, "id", ARTIFACT_ID)
    _require_exact(payload, "name", ARTIFACT_NAME)
    _require_exact(payload, "digest", ARTIFACT_DIGEST)
    _require_exact(payload, "size_in_bytes", ARTIFACT_SIZE_BYTES)
    _require_exact(payload, "expired", False)
    workflow_run = payload.get("workflow_run")
    if not isinstance(workflow_run, Mapping):
        raise ValueError("artifact metadata field workflow_run changed")
    _require_exact(
        workflow_run,
        "id",
        PARENT_RUN_ID,
        diagnostic_field="workflow_run.id",
    )

    receipt: dict[str, object] = {
        "artifact_type": "sealed_historical_parent_artifact_metadata_v0_8_receipt",
        "validator_id": VALIDATOR_ID,
        "artifact": {
            "id": ARTIFACT_ID,
            "name": ARTIFACT_NAME,
            "digest": ARTIFACT_DIGEST,
            "size_in_bytes": ARTIFACT_SIZE_BYTES,
            "expired": False,
            "workflow_run_id": PARENT_RUN_ID,
        },
        "metadata_fetched_once": True,
        "provider_calls": 0,
        "schema_version": 1,
    }
    receipt["content_sha256"] = canonical_fingerprint(receipt)
    return receipt


def load_and_validate_parent_artifact_metadata_v08(
    path: str | Path,
) -> dict[str, object]:
    return validate_parent_artifact_metadata_v08(_load_metadata(path))


__all__ = [
    "ARTIFACT_DIGEST",
    "ARTIFACT_ID",
    "ARTIFACT_NAME",
    "ARTIFACT_SIZE_BYTES",
    "PARENT_RUN_ID",
    "VALIDATOR_ID",
    "canonical_fingerprint",
    "load_and_validate_parent_artifact_metadata_v08",
    "validate_parent_artifact_metadata_v08",
]
