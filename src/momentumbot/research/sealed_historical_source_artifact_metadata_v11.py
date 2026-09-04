"""Exact v0.10 provider-checkpoint metadata gate for recovery v0.11."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping


ARTIFACT_ID = 9_877_181_150
ARTIFACT_NAME = (
    "sealed-historical-source-acquisition-v10-provider-checkpoint-33706372901-1"
)
ARTIFACT_DIGEST = (
    "sha256:b13bb68c5c231ba51b73c63d2a0d7e73fa78a0a837d4e35b94a55ddf5006b3b3"
)
ARTIFACT_SIZE_BYTES = 71_298_708
PARENT_RUN_ID = 33_706_372_901
PARENT_HEAD_SHA = "8b920876d9a513f31d6fdb6795c4155a2c1a1519"
VALIDATOR_ID = "sealed-historical-parent-artifact-metadata-v0.11"
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
        raise ValueError(
            f"artifact metadata field {diagnostic_field or field} changed"
        )


def validate_parent_artifact_metadata_v11(
    payload: Mapping[str, object],
) -> dict[str, object]:
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
    _require_exact(
        workflow_run,
        "head_sha",
        PARENT_HEAD_SHA,
        diagnostic_field="workflow_run.head_sha",
    )
    receipt: dict[str, object] = {
        "schema_version": 1,
        "artifact_type": "sealed_historical_parent_artifact_metadata_v0_11_receipt",
        "validator_id": VALIDATOR_ID,
        "artifact": {
            "id": ARTIFACT_ID,
            "name": ARTIFACT_NAME,
            "digest": ARTIFACT_DIGEST,
            "size_in_bytes": ARTIFACT_SIZE_BYTES,
            "expired": False,
            "workflow_run_id": PARENT_RUN_ID,
            "workflow_head_sha": PARENT_HEAD_SHA,
        },
        "metadata_fetched_once": True,
        "provider_calls": 0,
    }
    receipt["content_sha256"] = canonical_fingerprint(receipt)
    return receipt


def load_and_validate_parent_artifact_metadata_v11(
    path: str | Path,
) -> dict[str, object]:
    return validate_parent_artifact_metadata_v11(_load_metadata(path))


__all__ = [
    "ARTIFACT_DIGEST",
    "ARTIFACT_ID",
    "ARTIFACT_NAME",
    "ARTIFACT_SIZE_BYTES",
    "PARENT_HEAD_SHA",
    "PARENT_RUN_ID",
    "VALIDATOR_ID",
    "canonical_fingerprint",
    "load_and_validate_parent_artifact_metadata_v11",
    "validate_parent_artifact_metadata_v11",
]
