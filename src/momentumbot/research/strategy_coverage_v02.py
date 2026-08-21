from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Mapping, Sequence

from . import strategy_coverage as v01
from .evidence import StrategyRule


SCHEMA_VERSION = 1
MATRIX_ID = "strategy-discretion-coverage-v0.2"
ARTIFACT_TYPE = "non_authoritative_strategy_and_discretion_inventory_delta"
PARENT_MATRIX_ID = v01.MATRIX_ID
PARENT_CONTENT_SHA256 = (
    "3507642f70bbb8f4551238bc09242dd8c31474b463bf9a4e88f03a7894d97fe3"
)
PARENT_FILE_SHA256 = (
    "c1f7072f77aa07af6fdc10b1512bcabfd0e674e94cabcedb40d784f045e53a97"
)
CONTENT_SHA256 = (
    "e03c5130d36a075a274c0be9a504ca891307c271bf13b826f2af64fb0e217189"
)
ALLOWED_DOMAIN_UPDATES = frozenset(
    {
        "setup.hidden-buyer-anticipation",
        "management.chart-and-tape-exits",
        "microstructure.hidden-seller",
        "execution.realistic-broker",
        "data.level2-and-tape",
    }
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def validate_strategy_coverage_v02_delta(payload: Mapping[str, object]) -> None:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "matrix_id": MATRIX_ID,
        "artifact_type": ARTIFACT_TYPE,
        "runtime_strategy_effect": "none",
        "policy_promotion_eligible": False,
        "profitability_claim_eligible": False,
        "exact_ross_replication_claim_eligible": False,
        "retrospective_labels_allowed_in_runtime": False,
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise ValueError(f"v0.2 coverage delta {field} changed")
    claimed = payload.get("content_sha256")
    if claimed != CONTENT_SHA256:
        raise ValueError("v0.2 coverage delta content hash changed")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if v01.canonical_fingerprint(unsigned) != claimed:
        raise ValueError("v0.2 coverage delta fingerprint mismatch")
    parent = _mapping(payload.get("frozen_parent"), "frozen_parent")
    expected_parent = {
        "matrix_id": PARENT_MATRIX_ID,
        "content_sha256": PARENT_CONTENT_SHA256,
        "file_sha256": PARENT_FILE_SHA256,
    }
    for field, expected_value in expected_parent.items():
        if parent.get(field) != expected_value:
            raise ValueError(f"v0.2 coverage parent {field} changed")
    updates = payload.get("domain_updates")
    if not isinstance(updates, list) or not updates:
        raise ValueError("v0.2 coverage domain_updates must be non-empty")
    observed: list[str] = []
    required_fields = {
        "domain_id",
        "coverage_status",
        "implementation_owner",
        "current_authority",
        "implemented_artifacts",
        "missing_capabilities",
        "next_gate",
        "claim_boundary",
    }
    for index, value in enumerate(updates):
        update = _mapping(value, f"domain_updates[{index}]")
        if set(update) != required_fields:
            raise ValueError("v0.2 coverage update fields changed")
        domain_id = update.get("domain_id")
        if domain_id not in ALLOWED_DOMAIN_UPDATES:
            raise ValueError("v0.2 coverage update targets an unregistered domain")
        observed.append(str(domain_id))
        if update.get("coverage_status") not in v01.COVERAGE_STATUSES:
            raise ValueError("v0.2 coverage status is invalid")
        if update.get("implementation_owner") not in v01.IMPLEMENTATION_OWNERS:
            raise ValueError("v0.2 coverage owner is invalid")
        if update.get("current_authority") not in v01.AUTHORITY_STATES:
            raise ValueError("v0.2 coverage authority is invalid")
        for field in ("implemented_artifacts", "missing_capabilities"):
            values = update.get(field)
            if not isinstance(values, list) or any(
                not isinstance(item, str) or not item for item in values
            ):
                raise ValueError(f"v0.2 coverage {field} is invalid")
        for field in ("next_gate", "claim_boundary"):
            value = update.get(field)
            if not isinstance(value, str) or not value:
                raise ValueError(f"v0.2 coverage {field} is invalid")
    if len(observed) != len(set(observed)):
        raise ValueError("v0.2 coverage domains must be unique")
    if set(observed) != ALLOWED_DOMAIN_UPDATES:
        raise ValueError("v0.2 coverage update set changed")


def load_strategy_coverage_v02_delta(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("v0.2 coverage delta root must be an object")
    validate_strategy_coverage_v02_delta(payload)
    return payload


def resolve_strategy_coverage_v02(
    delta: Mapping[str, object],
    *,
    parent_path: str | Path,
    rules: Sequence[StrategyRule],
    repository_root: str | Path,
) -> dict[str, object]:
    validate_strategy_coverage_v02_delta(delta)
    parent_file = Path(parent_path)
    if v01.file_sha256(parent_file) != PARENT_FILE_SHA256:
        raise ValueError("v0.2 coverage parent file changed")
    parent = v01.load_strategy_coverage(
        parent_file,
        rules=rules,
        repository_root=repository_root,
    )
    if parent.get("content_sha256") != PARENT_CONTENT_SHA256:
        raise ValueError("v0.2 coverage parent content changed")
    resolved = copy.deepcopy(parent)
    by_id = {str(row["domain_id"]): row for row in resolved["domains"]}
    for update in delta["domain_updates"]:
        target = by_id[str(update["domain_id"])]
        for field, value in update.items():
            if field != "domain_id":
                target[field] = copy.deepcopy(value)
    resolved["matrix_id"] = MATRIX_ID
    resolved["registration_date"] = delta["registration_date"]
    resolved["purpose"] = delta["purpose"]
    resolved["coverage_summary"]["status_counts"] = dict(
        sorted(
            {
                status: sum(
                    row["coverage_status"] == status for row in resolved["domains"]
                )
                for status in v01.COVERAGE_STATUSES
                if any(
                    row["coverage_status"] == status for row in resolved["domains"]
                )
            }.items()
        )
    )
    resolved["next_priority_order"] = list(delta["next_priority_order"])

    # Reuse the frozen v0.1 structural validator without modifying its
    # permanently audited source. Only the matrix ID and fingerprint are
    # translated for compatibility during validation.
    compatibility = copy.deepcopy(resolved)
    compatibility["matrix_id"] = v01.MATRIX_ID
    compatibility["content_sha256"] = v01.canonical_fingerprint(
        {
            key: value
            for key, value in compatibility.items()
            if key != "content_sha256"
        }
    )
    v01.validate_strategy_coverage(
        compatibility,
        rules=rules,
        repository_root=repository_root,
    )
    resolved["content_sha256"] = v01.canonical_fingerprint(
        {key: value for key, value in resolved.items() if key != "content_sha256"}
    )
    return resolved


__all__ = [
    "ALLOWED_DOMAIN_UPDATES",
    "ARTIFACT_TYPE",
    "CONTENT_SHA256",
    "MATRIX_ID",
    "PARENT_CONTENT_SHA256",
    "PARENT_FILE_SHA256",
    "load_strategy_coverage_v02_delta",
    "resolve_strategy_coverage_v02",
    "validate_strategy_coverage_v02_delta",
]
