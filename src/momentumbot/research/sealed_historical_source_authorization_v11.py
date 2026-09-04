"""Authorization-only contract for provider-free source recovery v0.11."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping

from momentumbot.research.sealed_historical_source_artifact_metadata_v11 import (
    load_and_validate_parent_artifact_metadata_v11,
)


SCHEMA_VERSION = 1
AUTHORIZATION_ID = "sealed-historical-source-acquisition-v0.11"
AUTHORIZATION_CONTENT_SHA256 = (
    "135f67d754d5d3c0f7fbb9aaf57b6acb2c9034bf861540c5b610d880754816b8"
)
PARENT_AUTHORIZATION_CONTENT_SHA256 = (
    "a6519754147c39273a25b2ea818b1906dfa93ea5018edac831e2a0a7052463c7"
)
PARENT_FAILURE_AUDIT_CONTENT_SHA256 = (
    "d793a0fe5d9e4e1d0b9bf77edf8f164eb58860724aa4b6a7e3d09ec4f1fc03c5"
)
PARENT_WORKFLOW_FILE_SHA256 = (
    "e3f5295f2f3d4c75723fcb62666f4bf8da2adceef3b8922513053d66eb248fd9"
)
EXPECTED_DISPATCHER_WORKFLOW_REF = (
    "RoomyRems/momentumbot/.github/workflows/"
    "sealed-historical-source-acquisition-v11.yml@refs/heads/main"
)

ROOT = Path(__file__).resolve().parents[3]
AUTHORIZATION_PATH = Path(
    "research/strategy/sealed-historical-source-acquisition-v0.11.json"
)
PARENT_AUTHORIZATION_PATH = Path(
    "research/strategy/sealed-historical-source-acquisition-v0.10.json"
)
PARENT_FAILURE_AUDIT_PATH = Path(
    "research/data-audits/"
    "sealed-historical-source-acquisition-v0.10-run-33706372901-"
    "failure-2026-09-04.json"
)
PARENT_ARTIFACT_METADATA_PATH = Path(
    "research/data-audits/"
    "sealed-historical-source-acquisition-v0.11-parent-artifact-"
    "metadata-2026-09-04.json"
)
PARENT_WORKFLOW_PATH = Path(
    ".github/workflows/sealed-historical-source-acquisition-v10.yml"
)
REGISTRATION_AUDIT_PATH = Path(
    "research/data-audits/"
    "sealed-historical-source-acquisition-v0.11-registration-2026-09-04.json"
)

REGISTRATION_ARTIFACT_PATHS = {
    "artifact_metadata_fixture": PARENT_ARTIFACT_METADATA_PATH,
    "artifact_metadata_runner": Path(
        "scripts/validate_parent_artifact_metadata_v11.py"
    ),
    "artifact_metadata_validator": Path(
        "src/momentumbot/research/"
        "sealed_historical_source_artifact_metadata_v11.py"
    ),
    "authorization": AUTHORIZATION_PATH,
    "authorization_validator": Path(
        "src/momentumbot/research/sealed_historical_source_authorization_v11.py"
    ),
    "documentation": Path(
        "docs/research/sealed_historical_source_acquisition_v11.md"
    ),
    "failure_audit": PARENT_FAILURE_AUDIT_PATH,
    "final_identity_adapter": Path(
        "src/momentumbot/historical_float_identity_v11.py"
    ),
    "final_report": Path(
        "src/momentumbot/research/sealed_historical_source_acquisition_v11.py"
    ),
    "historical_float_parent": Path("src/momentumbot/historical_float_v04.py"),
    "parent_authoritative_identity_rule": Path(
        "src/momentumbot/historical_float_identity_v06.py"
    ),
    "parent_checkpoint_validator": Path(
        "src/momentumbot/research/sealed_historical_source_checkpoint_v10.py"
    ),
    "parent_downstream_identity_adapter": Path(
        "src/momentumbot/historical_float_identity_v09.py"
    ),
    "parent_scanner_adapter": Path(
        "scripts/build_causal_scanner_snapshot_v10.py"
    ),
    "parent_workflow": PARENT_WORKFLOW_PATH,
    "requirements": Path("requirements-sealed-source-v04.txt"),
    "runner": Path("scripts/run_sealed_historical_source_acquisition_v11.py"),
    "workflow": Path(
        ".github/workflows/sealed-historical-source-acquisition-v11.yml"
    ),
}


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


def _load_json_object(path: str | Path) -> dict[str, object]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"JSON input must be a regular file: {source}")
    payload = json.loads(
        source.read_text(encoding="utf-8"),
        parse_constant=_reject_json_constant,
        object_pairs_hook=_reject_duplicate_json_keys,
    )
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required at {source}")
    return payload


def canonical_fingerprint(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(payload),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_self_hash(
    payload: Mapping[str, object], *, expected: str, label: str
) -> None:
    body = dict(payload)
    claimed = body.pop("content_sha256", None)
    if claimed != canonical_fingerprint(body) or claimed != expected:
        raise ValueError(f"{label} content hash changed")


def validate_authorization(payload: Mapping[str, object]) -> None:
    _validate_self_hash(
        payload,
        expected=AUTHORIZATION_CONTENT_SHA256,
        label="v0.11 authorization",
    )
    expected_keys = {
        "artifact_type",
        "authority_boundary",
        "authorization_id",
        "causal_boundary",
        "content_sha256",
        "cost_ceiling",
        "dispatcher_contract",
        "downstream_contract",
        "execution_order_contract",
        "failed_parent",
        "one_shot_contract",
        "provider_free_contract",
        "recovery_contract",
        "registered_at_date",
        "repair_boundary",
        "reproducibility_environment_contract",
        "request_accounting",
        "retention_budget",
        "schema_version",
    }
    if set(payload) != expected_keys:
        raise ValueError("v0.11 authorization fields changed")
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("artifact_type")
        != "preregistered_sealed_historical_source_freeze_recovery_v0_11"
        or payload.get("authorization_id") != AUTHORIZATION_ID
        or payload.get("registered_at_date") != "2026-09-04"
    ):
        raise ValueError("v0.11 authorization identity changed")
    if payload.get("dispatcher_contract") != {
        "contents_write_allowed": False,
        "dispatcher_blob_must_match_authorized_research_workflow": True,
        "provider_credentials_allowed_in_any_job": False,
        "workflow_ref": EXPECTED_DISPATCHER_WORKFLOW_REF,
    }:
        raise ValueError("v0.11 dispatcher boundary changed")
    if payload.get("provider_free_contract") != {
        "allowed_provider_entrypoints": [],
        "ambient_proxy_use_allowed": False,
        "brokerage_or_market_provider_hosts_allowed": [],
        "credential_environment_variables_allowed": [],
        "direct_socket_or_process_escape_allowed": False,
        "github_artifact_download_only": True,
        "provider_calls_authorized": 0,
    }:
        raise ValueError("v0.11 provider-free boundary changed")
    if payload.get("one_shot_contract") != {
        "automatic_rerun_allowed": False,
        "manual_workflow_dispatch_required": True,
        "parent_authorization_rerun_allowed": False,
        "provider_consumption_tag_required": False,
        "push_execution_limited_to_provider_free_validation": True,
        "workflow_run_attempt_required": 1,
    }:
        raise ValueError("v0.11 one-shot boundary changed")
    failed = payload.get("failed_parent")
    if not isinstance(failed, Mapping) or (
        failed.get("authorization_content_sha256")
        != PARENT_AUTHORIZATION_CONTENT_SHA256
        or failed.get("failure_audit_content_sha256")
        != PARENT_FAILURE_AUDIT_CONTENT_SHA256
        or failed.get("workflow_run_id") != 33_706_372_901
        or failed.get("provider_checkpoint_artifact_id") != 9_877_181_150
    ):
        raise ValueError("v0.11 failed-parent boundary changed")
    request = payload.get("request_accounting")
    if not isinstance(request, Mapping) or request.get(
        "additional_provider_http_attempts_authorized"
    ) != 0 or request.get("frozen_total_attempts") != 30_522:
        raise ValueError("v0.11 request accounting changed")


def validate_parent_bundle() -> dict[str, object]:
    from momentumbot.research.sealed_historical_source_authorization_v10 import (
        load_authorization as load_parent_authorization,
    )

    parent = load_parent_authorization(ROOT / PARENT_AUTHORIZATION_PATH)
    if parent.get("content_sha256") != PARENT_AUTHORIZATION_CONTENT_SHA256:
        raise ValueError("v0.10 parent authorization changed")
    failure = _load_json_object(ROOT / PARENT_FAILURE_AUDIT_PATH)
    _validate_self_hash(
        failure,
        expected=PARENT_FAILURE_AUDIT_CONTENT_SHA256,
        label="v0.10 failure audit",
    )
    if (
        failure.get("conclusion")
        != "fail_closed_final_summarizer_identity_scope_mismatch"
        or failure.get("workflow", {}).get("run_id") != 33_706_372_901  # type: ignore[union-attr]
    ):
        raise ValueError("v0.10 failure boundary changed")
    metadata = load_and_validate_parent_artifact_metadata_v11(
        ROOT / PARENT_ARTIFACT_METADATA_PATH
    )
    workflow = ROOT / PARENT_WORKFLOW_PATH
    if (
        workflow.is_symlink()
        or not workflow.is_file()
        or _file_sha256(workflow) != PARENT_WORKFLOW_FILE_SHA256
    ):
        raise ValueError("v0.10 workflow file changed")
    return {
        "v0_10_authorization": parent,
        "v0_10_failure_audit": failure,
        "v0_10_provider_checkpoint_metadata": metadata,
    }


def validate_registration_bundle() -> dict[str, object]:
    path = ROOT / REGISTRATION_AUDIT_PATH
    audit = _load_json_object(path)
    body = dict(audit)
    claimed = body.pop("content_sha256", None)
    if claimed != canonical_fingerprint(body):
        raise ValueError("v0.11 registration audit content hash changed")
    if (
        audit.get("schema_version") != 1
        or audit.get("artifact_type")
        != "provider_free_sealed_historical_source_recovery_v0_11_registration"
        or audit.get("authorization_id") != AUTHORIZATION_ID
        or audit.get("authorization_content_sha256")
        != AUTHORIZATION_CONTENT_SHA256
        or audit.get("registration_status")
        != "provider_free_freeze_recovery_not_dispatched"
    ):
        raise ValueError("v0.11 registration identity changed")
    if audit.get("authority_boundary") != {
        "automatic_rerun_allowed": False,
        "candidate_bound_databento_authorized": False,
        "exact_commit_tree_and_dispatcher_authorization_required": True,
        "live_order_authorized": False,
        "manual_dispatch_required": True,
        "paper_order_authorized": False,
        "policy_promotion_eligible": False,
        "provider_credentials_allowed": False,
        "push_validation_provider_free": True,
    }:
        raise ValueError("v0.11 registration authority boundary changed")
    if audit.get("causal_attestation") != {
        "account_or_order_endpoint_calls": 0,
        "credential_values_accessed_or_observed": False,
        "databento_calls": 0,
        "orders_submitted": 0,
        "provider_calls": 0,
        "ross_labels_or_outcomes_read": False,
        "runtime_started": False,
        "transcript_record_values_read": False,
    }:
        raise ValueError("v0.11 registration causal boundary changed")
    if audit.get("repair") != {
        "all_946_candidates_and_float_records_preflighted": True,
        "authoritative_identity_kind_counts": {
            "composite_figi": 737,
            "unique_cik_fallback": 209,
        },
        "candidate_identity_or_float_values_rewritten": False,
        "exact_v0_10_provider_checkpoint_reused": True,
        "final_summarizer_only_scope": True,
        "identity_validator_restored_after_success_or_exception": True,
        "provider_requests_repeated": False,
        "scanner_snapshots_rebuilt_from_canonical_inputs_only": True,
        "strategy_profiles_or_thresholds_changed": False,
    }:
        raise ValueError("v0.11 registration repair boundary changed")
    artifacts = audit.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != set(
        REGISTRATION_ARTIFACT_PATHS
    ):
        raise ValueError("v0.11 registration artifact census changed")
    for label, relative in REGISTRATION_ARTIFACT_PATHS.items():
        entry = artifacts.get(label)
        absolute = ROOT / relative
        if (
            not isinstance(entry, Mapping)
            or set(entry) != {"file_sha256", "path"}
            or entry.get("path") != relative.as_posix()
            or absolute.is_symlink()
            or not absolute.is_file()
            or entry.get("file_sha256") != _file_sha256(absolute)
        ):
            raise ValueError(f"v0.11 registration artifact {label} changed")
    return audit


def load_authorization(path: str | Path) -> dict[str, object]:
    payload = _load_json_object(path)
    validate_authorization(payload)
    validate_parent_bundle()
    validate_registration_bundle()
    return payload


__all__ = [
    "AUTHORIZATION_CONTENT_SHA256",
    "AUTHORIZATION_ID",
    "AUTHORIZATION_PATH",
    "EXPECTED_DISPATCHER_WORKFLOW_REF",
    "REGISTRATION_ARTIFACT_PATHS",
    "REGISTRATION_AUDIT_PATH",
    "canonical_fingerprint",
    "load_authorization",
    "validate_authorization",
    "validate_parent_bundle",
    "validate_registration_bundle",
]
