from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence

from .evidence import StrategyRule


SCHEMA_VERSION = 1
MATRIX_ID = "strategy-discretion-coverage-v0.1"
ARTIFACT_TYPE = "non_authoritative_strategy_and_discretion_inventory"

COVERAGE_STATUSES = frozenset(
    {
        "implemented_frozen",
        "implemented_unrun",
        "partial_deterministic",
        "partial_shadow",
        "data_blocked",
        "missing",
        "research_guard",
    }
)
IMPLEMENTATION_OWNERS = frozenset(
    {"deterministic", "ai_shadow", "mixed", "research_only", "unassigned"}
)
AUTHORITY_STATES = frozenset(
    {"runtime_deterministic", "shadow_only", "research_only", "none"}
)

_DOMAIN_ID = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def canonical_fingerprint(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _string_list(value: object, field: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    if not allow_empty and not value:
        raise ValueError(f"{field} must not be empty")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_nonempty_string(item, f"{field}[{index}]"))
    if len(result) != len(set(result)):
        raise ValueError(f"{field} must not contain duplicates")
    return result


def validate_strategy_coverage(
    payload: Mapping[str, object],
    *,
    rules: Sequence[StrategyRule],
    repository_root: str | Path,
) -> None:
    """Fail closed when the inventory overstates coverage or loses provenance."""

    root = Path(repository_root).resolve()
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported strategy coverage schema")
    if payload.get("matrix_id") != MATRIX_ID:
        raise ValueError("unexpected strategy coverage matrix")
    if payload.get("artifact_type") != ARTIFACT_TYPE:
        raise ValueError("unexpected strategy coverage artifact type")
    if payload.get("runtime_strategy_effect") != "none":
        raise ValueError("coverage inventory cannot affect runtime")
    for field in (
        "policy_promotion_eligible",
        "profitability_claim_eligible",
        "exact_ross_replication_claim_eligible",
        "retrospective_labels_allowed_in_runtime",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must be false")

    claimed = _nonempty_string(payload.get("content_sha256"), "content_sha256")
    if not _SHA256.fullmatch(claimed):
        raise ValueError("content_sha256 must be a lowercase SHA-256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("strategy coverage content fingerprint mismatch")

    source_bindings = _mapping(payload.get("source_bindings"), "source_bindings")
    files = source_bindings.get("rulebook_files")
    if not isinstance(files, list) or not files:
        raise ValueError("source_bindings.rulebook_files must be non-empty")
    bound_paths: set[str] = set()
    for index, value in enumerate(files):
        item = _mapping(value, f"source_bindings.rulebook_files[{index}]")
        relative = _nonempty_string(item.get("path"), "rulebook path")
        if relative in bound_paths:
            raise ValueError("rulebook file bindings must be unique")
        bound_paths.add(relative)
        path = (root / relative).resolve()
        if path != root and root not in path.parents:
            raise ValueError("rulebook binding escapes repository root")
        if not path.is_file():
            raise ValueError(f"bound rulebook file does not exist: {relative}")
        expected = _nonempty_string(item.get("file_sha256"), "rulebook file SHA-256")
        if not _SHA256.fullmatch(expected) or file_sha256(path) != expected:
            raise ValueError(f"bound rulebook file changed: {relative}")

    domains = payload.get("domains")
    if not isinstance(domains, list) or not domains:
        raise ValueError("coverage domains must be a non-empty list")
    domain_ids: list[str] = []
    cited_rule_ids: list[str] = []
    status_counts: Counter[str] = Counter()
    for index, value in enumerate(domains):
        item = _mapping(value, f"domains[{index}]")
        domain_id = _nonempty_string(item.get("domain_id"), "domain_id")
        if not _DOMAIN_ID.fullmatch(domain_id):
            raise ValueError(f"invalid domain_id: {domain_id}")
        domain_ids.append(domain_id)
        status = item.get("coverage_status")
        if status not in COVERAGE_STATUSES:
            raise ValueError(f"{domain_id} has an invalid coverage status")
        status_counts[str(status)] += 1
        if item.get("implementation_owner") not in IMPLEMENTATION_OWNERS:
            raise ValueError(f"{domain_id} has an invalid implementation owner")
        if item.get("current_authority") not in AUTHORITY_STATES:
            raise ValueError(f"{domain_id} has an invalid authority state")

        rule_ids = _string_list(item.get("evidence_rule_ids"), f"{domain_id}.evidence_rule_ids")
        cited_rule_ids.extend(rule_ids)
        _string_list(item.get("implemented_artifacts"), f"{domain_id}.implemented_artifacts")
        _string_list(item.get("missing_capabilities"), f"{domain_id}.missing_capabilities")
        _nonempty_string(item.get("next_gate"), f"{domain_id}.next_gate")
        _nonempty_string(item.get("claim_boundary"), f"{domain_id}.claim_boundary")

        for relative in item["implemented_artifacts"]:
            if "dataset_daytradewarrior" in relative:
                raise ValueError("raw transcript archives cannot be runtime artifacts")
            path = (root / relative).resolve()
            if path != root and root not in path.parents:
                raise ValueError("implemented artifact escapes repository root")
            if not path.exists():
                raise ValueError(f"implemented artifact does not exist: {relative}")

        if status in {"missing", "data_blocked"} and item.get("current_authority") != "none":
            raise ValueError(f"{domain_id} cannot have authority while {status}")
        if status == "research_guard" and item.get("implementation_owner") != "research_only":
            raise ValueError(f"{domain_id} research guard must be research-owned")

    if len(domain_ids) != len(set(domain_ids)):
        raise ValueError("coverage domain IDs must be unique")
    if len(cited_rule_ids) != len(set(cited_rule_ids)):
        raise ValueError("each promoted rule must map to exactly one coverage domain")
    expected_rule_ids = {rule.rule_id for rule in rules}
    observed_rule_ids = set(cited_rule_ids)
    if observed_rule_ids != expected_rule_ids:
        missing = sorted(expected_rule_ids - observed_rule_ids)
        unknown = sorted(observed_rule_ids - expected_rule_ids)
        raise ValueError(f"coverage rule mapping mismatch: missing={missing}, unknown={unknown}")

    summary = _mapping(payload.get("coverage_summary"), "coverage_summary")
    if summary.get("domain_count") != len(domains):
        raise ValueError("coverage domain count does not recompute")
    if summary.get("promoted_rule_count") != len(expected_rule_ids):
        raise ValueError("coverage promoted rule count does not recompute")
    if summary.get("status_counts") != dict(sorted(status_counts.items())):
        raise ValueError("coverage status counts do not recompute")

    priorities = _string_list(
        payload.get("next_priority_order"),
        "next_priority_order",
        allow_empty=False,
    )
    if any(item not in set(domain_ids) for item in priorities):
        raise ValueError("next priority references an unknown coverage domain")


def load_strategy_coverage(
    path: str | Path,
    *,
    rules: Sequence[StrategyRule],
    repository_root: str | Path,
) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("strategy coverage root must be an object")
    validate_strategy_coverage(payload, rules=rules, repository_root=repository_root)
    return payload
