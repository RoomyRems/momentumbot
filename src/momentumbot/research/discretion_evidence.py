from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA_VERSION = 1
AUDIT_ID = "ross-discretion-evidence-coverage-v0.1"

_CONTEXT_CLASSES = {
    "retrospective_behavior",
    "explicit_retrospective_reason",
    "retrospective_skip_or_caution",
    "ambiguous_hindsight_or_self_critique",
    "negative_context_evidence",
}


def _resolve_pointer(payload: object, pointer: str) -> object:
    if not pointer.startswith("/"):
        raise ValueError(f"evidence path must be an absolute JSON pointer: {pointer}")
    current = payload
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if token not in current:
                raise ValueError(f"evidence path does not exist: {pointer}")
            current = current[token]
        elif isinstance(current, Sequence) and not isinstance(current, (str, bytes)):
            try:
                current = current[int(token)]
            except (ValueError, IndexError) as exc:
                raise ValueError(f"evidence path does not exist: {pointer}") from exc
        else:
            raise ValueError(f"evidence path does not exist: {pointer}")
    return current


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def validate_discretion_evidence_audit(
    payload: Mapping[str, object],
    *,
    benchmark_root: str | Path | None = None,
    context_contract: Mapping[str, object] | None = None,
) -> None:
    """Validate retrospective evidence coverage without making it runtime context."""

    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported discretion-evidence schema")
    if payload.get("audit_id") != AUDIT_ID:
        raise ValueError("unexpected discretion-evidence audit ID")
    if payload.get("artifact_type") != "retrospective_discretion_evidence_coverage_audit":
        raise ValueError("unexpected discretion-evidence artifact type")
    if payload.get("runtime_strategy_effect") != "none":
        raise ValueError("retrospective evidence audit must not affect runtime strategy")
    if payload.get("runtime_eligible") is not False:
        raise ValueError("retrospective evidence audit must remain runtime-ineligible")
    if payload.get("policy_promotion_eligible") is not False:
        raise ValueError("evidence coverage alone is not policy-promotion eligible")
    if payload.get("full_imitation_claim_eligible") is not False:
        raise ValueError("incomplete evidence cannot support a full imitation claim")

    domains = payload.get("domains")
    if not isinstance(domains, list) or not domains:
        raise ValueError("domains must be a non-empty list")
    domain_ids = [str(row.get("domain_id", "")) for row in domains if isinstance(row, Mapping)]
    if len(domain_ids) != len(domains) or any(not item for item in domain_ids):
        raise ValueError("every domain must have a non-empty domain_id")
    if len(domain_ids) != len(set(domain_ids)):
        raise ValueError("domain IDs must be unique")

    if context_contract is not None:
        expected_contract = str(context_contract.get("contract_id", ""))
        if payload.get("context_contract_id") != expected_contract:
            raise ValueError("context contract ID mismatch")
        contract_domains = context_contract.get("domains")
        if not isinstance(contract_domains, list):
            raise ValueError("context contract domains are invalid")
        expected_domains = [str(row["domain_id"]) for row in contract_domains]
        if domain_ids != expected_domains:
            raise ValueError("evidence audit domains must match contract order exactly")

    root = Path(benchmark_root) if benchmark_root is not None else None
    seen_benchmark_files: set[str] = set()
    computed_rows: dict[str, int] = {}
    computed_explicit_reasons: dict[str, int] = {}
    computed_preentry: dict[str, int] = {}

    for domain in domains:
        assert isinstance(domain, Mapping)
        domain_id = str(domain["domain_id"])
        rows = domain.get("evidence_rows")
        if not isinstance(rows, list):
            raise ValueError(f"{domain_id}.evidence_rows must be a list")
        if domain.get("runtime_gate_enabled") is not False:
            raise ValueError(f"{domain_id} evidence must not be a runtime gate")
        sufficiency = domain.get("sufficiency")
        if not isinstance(sufficiency, Mapping):
            raise ValueError(f"{domain_id}.sufficiency must be an object")
        if not str(domain.get("conclusion", "")).strip():
            raise ValueError(f"{domain_id}.conclusion is required")

        computed_rows[domain_id] = len(rows)
        computed_explicit_reasons[domain_id] = 0
        computed_preentry[domain_id] = 0

        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError(f"{domain_id} evidence rows must be objects")
            context_class = row.get("context_class")
            if context_class not in _CONTEXT_CLASSES:
                raise ValueError(f"invalid context class in {domain_id}")
            if context_class == "explicit_retrospective_reason":
                computed_explicit_reasons[domain_id] += 1
            if row.get("runtime_eligible") is not False:
                raise ValueError("benchmark behavior evidence must remain runtime-ineligible")
            if row.get("pre_entry_timestamp_verified") is True:
                computed_preentry[domain_id] += 1
            if row.get("alternative_candidate_set_complete") is not False:
                raise ValueError("current benchmark rows do not contain complete alternative sets")

            filename = str(row.get("benchmark_file", ""))
            if not filename or Path(filename).name != filename or not filename.endswith(".json"):
                raise ValueError("benchmark_file must be a plain JSON filename")
            pointers = row.get("evidence_paths")
            if not isinstance(pointers, list) or not pointers:
                raise ValueError(f"{domain_id} evidence rows require evidence_paths")
            if any(not isinstance(pointer, str) for pointer in pointers):
                raise ValueError("evidence paths must be strings")
            if not str(row.get("summary", "")).strip() or not str(row.get("limit", "")).strip():
                raise ValueError("evidence rows require summary and limit")

            seen_benchmark_files.add(filename)
            if root is not None:
                benchmark = _load_json(root / filename)
                if row.get("benchmark_id") != benchmark.get("benchmark_id"):
                    raise ValueError(f"benchmark ID mismatch for {filename}")
                if row.get("symbol") != benchmark.get("symbol"):
                    raise ValueError(f"benchmark symbol mismatch for {filename}")
                source = benchmark.get("source")
                if not isinstance(source, Mapping):
                    raise ValueError(f"benchmark source missing for {filename}")
                if row.get("source_video_id") != source.get("video_id"):
                    raise ValueError(f"source video mismatch for {filename}")
                if row.get("source_evidence_type") != source.get("evidence_type"):
                    raise ValueError(f"source evidence type mismatch for {filename}")
                for pointer in pointers:
                    _resolve_pointer(benchmark, pointer)
                if any(pointer.startswith("/observed_human_decision_context/") for pointer in pointers):
                    extraction = benchmark.get("decision_context_extraction")
                    if not isinstance(extraction, Mapping):
                        raise ValueError(f"decision context extraction missing for {filename}")
                    required_extraction_guards = {
                        "verbatim_transcript_persisted": False,
                        "runtime_eligible": False,
                        "pre_entry_video_timestamp_verified": False,
                        "complete_alternative_candidate_set": False,
                    }
                    for field, expected in required_extraction_guards.items():
                        if extraction.get(field) is not expected:
                            raise ValueError(
                                f"decision context extraction guard mismatch for {filename}: {field}"
                            )

        if sufficiency.get("evidence_row_count") != len(rows):
            raise ValueError(f"{domain_id} evidence row count mismatch")
        if sufficiency.get("explicit_retrospective_reason_count") != computed_explicit_reasons[domain_id]:
            raise ValueError(f"{domain_id} explicit-reason count mismatch")
        if sufficiency.get("pre_entry_timestamp_verified_count") != computed_preentry[domain_id]:
            raise ValueError(f"{domain_id} pre-entry timestamp count mismatch")
        if sufficiency.get("complete_alternative_candidate_set_count") != 0:
            raise ValueError(f"{domain_id} alternative-set count must remain zero")

    source_scope = payload.get("source_scope")
    if not isinstance(source_scope, Mapping):
        raise ValueError("source_scope must be an object")
    listed_files = source_scope.get("benchmark_files")
    if not isinstance(listed_files, list) or len(listed_files) != len(set(listed_files)):
        raise ValueError("source_scope benchmark files must be unique")
    if set(str(item) for item in listed_files) != seen_benchmark_files:
        raise ValueError("source_scope must exactly match referenced benchmark files")

    requests = payload.get("targeted_source_requests")
    if not isinstance(requests, list) or not requests:
        raise ValueError("targeted_source_requests must be a non-empty list")
    source_video_ids = {
        str(row["source_video_id"])
        for domain in domains
        for row in domain["evidence_rows"]
    }
    request_ids: set[str] = set()
    for request in requests:
        if not isinstance(request, Mapping):
            raise ValueError("source requests must be objects")
        request_id = str(request.get("request_id", ""))
        if not request_id or request_id in request_ids:
            raise ValueError("source request IDs must be non-empty and unique")
        request_ids.add(request_id)
        video_ids = request.get("video_ids")
        if not isinstance(video_ids, list) or not video_ids:
            raise ValueError(f"{request_id} must name at least one video")
        if not set(str(item) for item in video_ids).issubset(source_video_ids):
            raise ValueError(f"{request_id} references an unknown source video")
        requested_domains = request.get("domain_ids")
        if not isinstance(requested_domains, list) or not requested_domains:
            raise ValueError(f"{request_id} must name at least one domain")
        if not set(str(item) for item in requested_domains).issubset(set(domain_ids)):
            raise ValueError(f"{request_id} references an unknown domain")
        if not str(request.get("needed_segment", "")).strip():
            raise ValueError(f"{request_id}.needed_segment is required")
        if request.get("request_only_if_existing_evidence_is_insufficient") is not True:
            raise ValueError("source requests must remain targeted and conditional")


def load_discretion_evidence_audit(
    path: str | Path,
    *,
    benchmark_root: str | Path | None = None,
    context_contract: Mapping[str, object] | None = None,
) -> dict[str, object]:
    payload = _load_json(Path(path))
    validate_discretion_evidence_audit(
        payload,
        benchmark_root=benchmark_root,
        context_contract=context_contract,
    )
    return payload


def evidence_counts(payload: Mapping[str, object]) -> dict[str, int]:
    validate_discretion_evidence_audit(payload)
    return {
        str(domain["domain_id"]): len(domain["evidence_rows"])
        for domain in payload["domains"]  # type: ignore[index]
    }
