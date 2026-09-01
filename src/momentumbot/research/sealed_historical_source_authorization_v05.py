"""Authorization-only contract for sealed source recovery v0.5."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Mapping

from momentumbot.research.sealed_historical_source_checkpoint_v05 import (
    canonical_fingerprint,
    validate_authorization_envelope_v05,
)


SCHEMA_VERSION = 1
AUTHORIZATION_ID = "sealed-historical-source-acquisition-v0.5"
AUTHORIZATION_CONTENT_SHA256 = (
    "23ad997837490c14c200c10b34c8285db7b18ddebca131e6299a8cd70b3bbc49"
)
PARENT_FAILURE_AUDIT_CONTENT_SHA256 = (
    "d2096f4c4217ccb5ac5753ca209cb5b0be9b2299dd79a8c33db08153faa58aeb"
)
PARENT_AUTHORIZATION_CONTENT_SHA256 = (
    "bbe51f4483a73f92b1f58c9f6c2085d8a47505346c2d340fbe59c0421f3f31b7"
)
PARENT_RUN_ID = 33468687163
PARENT_FAILURE_CHECKPOINT_ZIP_SHA256 = (
    "e9eb2854aa40d386509524475441f8ef159e0e73fcc63af4acf988b364ece1b9"
)
PARENT_FAILURE_SUMMARY_ZIP_SHA256 = (
    "150daca229e91c647b07f5b1f28ffc34b5c934c8de5257787075a90e74972ca3"
)
PARENT_CONSUMPTION_MARKER_ZIP_SHA256 = (
    "a30ab6de56fa090def6a00f1a42740ed4b08fb4267c71cda0da5b39d39b8e887"
)

ROOT = Path(__file__).resolve().parents[3]
AUTHORIZATION_PATH = Path(
    "research/strategy/sealed-historical-source-acquisition-v0.5.json"
)
PARENT_AUTHORIZATION_PATH = Path(
    "research/strategy/sealed-historical-source-acquisition-v0.4.json"
)
PARENT_FAILURE_AUDIT_PATH = Path(
    "research/data-audits/"
    "sealed-historical-source-acquisition-v0.4-run-33468687163-failure-2026-09-01.json"
)
REGISTRATION_AUDIT_PATH = Path(
    "research/data-audits/"
    "sealed-historical-source-acquisition-v0.5-registration-2026-09-01.json"
)
EXPECTED_DISPATCHER_WORKFLOW_REF = (
    "RoomyRems/momentumbot/.github/workflows/"
    "sealed-historical-source-acquisition-v05.yml@refs/heads/main"
)
CONSUMPTION_TAG_PREFIX = (
    "refs/tags/sealed-historical-source-acquisition-v05-consumed-"
)

REGISTRATION_ARTIFACT_PATHS = {
    "acquisition_validator": Path(
        "src/momentumbot/research/sealed_historical_source_acquisition_v05.py"
    ),
    "alpaca_provider": Path("src/momentumbot/providers/alpaca.py"),
    "authorization": AUTHORIZATION_PATH,
    "authorization_validator": Path(
        "src/momentumbot/research/sealed_historical_source_authorization_v05.py"
    ),
    "checkpoint_builder": Path(
        "scripts/build_sealed_historical_source_checkpoint_v05.py"
    ),
    "checkpoint_validator": Path(
        "src/momentumbot/research/sealed_historical_source_checkpoint_v05.py"
    ),
    "documentation": Path(
        "docs/research/sealed_historical_source_acquisition_v05.md"
    ),
    "failure_audit": PARENT_FAILURE_AUDIT_PATH,
    "float_adapter": Path("scripts/build_causal_float_enrichment_v05.py"),
    "float_parent": Path("scripts/build_causal_float_enrichment_v04.py"),
    "float_policy": Path("src/momentumbot/historical_float_v04.py"),
    "historical_data": Path("src/momentumbot/historical_data_v03.py"),
    "http_transport": Path("src/momentumbot/providers/http_json.py"),
    "identity_loader": Path("src/momentumbot/identity_resolved_universe.py"),
    "market_loader": Path("src/momentumbot/causal_market_discovery_v03.py"),
    "news_builder": Path("scripts/build_causal_news_enrichment_v04.py"),
    "news_policy": Path("src/momentumbot/historical_news.py"),
    "parent_acquisition_validator": Path(
        "src/momentumbot/research/sealed_historical_source_acquisition_v04.py"
    ),
    "parent_authorization": PARENT_AUTHORIZATION_PATH,
    "parent_checkpoint_validator": Path(
        "src/momentumbot/research/sealed_historical_source_checkpoint_v01.py"
    ),
    "project_metadata": Path("pyproject.toml"),
    "provider_wrapper": Path("scripts/run_provider_entrypoint_v05.py"),
    "provider_transport_guard": Path("scripts/run_provider_entrypoint_v04.py"),
    "recovery_runner": Path("scripts/validate_sealed_historical_source_recovery_v05.py"),
    "recovery_validator": Path(
        "src/momentumbot/research/sealed_historical_source_recovery_v05.py"
    ),
    "request_budget": Path("src/momentumbot/providers/request_budget.py"),
    "requirements": Path("requirements-sealed-source-v04.txt"),
    "runner": Path("scripts/run_sealed_historical_source_acquisition_v05.py"),
    "scanner_builder": Path("scripts/build_causal_scanner_snapshot_v04.py"),
    "scanner_policy": Path("src/momentumbot/causal_scanner_snapshot_v03.py"),
    "scanner_source_inputs": Path("src/momentumbot/scanner_source_inputs_v03.py"),
    "sec_provider": Path("src/momentumbot/providers/sec_edgar.py"),
    "selected_dates": Path(
        "src/momentumbot/research/sealed_historical_availability.py"
    ),
    "strategy_profile_union": Path(
        "src/momentumbot/historical_profile_union_v01.py"
    ),
    "workflow": Path(
        ".github/workflows/sealed-historical-source-acquisition-v05.yml"
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
    payload = json.loads(
        Path(path).read_text(encoding="utf-8"),
        parse_constant=_reject_json_constant,
        object_pairs_hook=_reject_duplicate_json_keys,
    )
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required at {path}")
    return payload


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


def expected_authorization_body() -> dict[str, object]:
    payload = _load_json_object(ROOT / AUTHORIZATION_PATH)
    validate_authorization(payload)
    body = deepcopy(payload)
    body.pop("content_sha256")
    return body


def validate_authorization(payload: Mapping[str, object]) -> None:
    validated = validate_authorization_envelope_v05(payload)
    if validated.get("content_sha256") != AUTHORIZATION_CONTENT_SHA256:
        raise ValueError("historical source v0.5 differs from frozen hash")
    if validated.get("dispatcher_contract") != {
        "contents_write_allowed_only_in_consumption_job": True,
        "dispatcher_blob_must_match_authorized_research_workflow": True,
        "provider_credentials_allowed_in_consume_or_freeze_job": False,
        "provider_free_freeze_is_separate_job": True,
        "workflow_ref": EXPECTED_DISPATCHER_WORKFLOW_REF,
    }:
        raise ValueError("v0.5 dispatcher contract changed")
    if validated.get("reproducibility_environment_contract") != {
        "clean_cpython_3_12_virtual_environment_required_per_job": True,
        "editable_project_lines_must_match_respective_authorized_commits": True,
        "parent_artifact_full_replay_required_before_consumption": True,
        "parent_third_party_environment_freeze_must_match": True,
        "pip_check_required": True,
        "requirements_hashes_and_binary_wheels_required": True,
        "requirements_path": "requirements-sealed-source-v04.txt",
    }:
        raise ValueError("v0.5 reproducibility environment contract changed")
    provider = validated.get("provider_entrypoint_contract")
    if not isinstance(provider, Mapping) or provider.get("child_network_hosts") != [
        "data.alpaca.markets",
        "data.sec.gov",
    ] or provider.get("market_identity_or_massive_entrypoint_allowed") is not False:
        raise ValueError("v0.5 child provider network boundary changed")
    repair = validated.get("repair_boundary")
    if not isinstance(repair, Mapping) or repair.get(
        "candidate_data_exception_classes"
    ) != ["TypeError", "ValueError"] or repair.get(
        "transport_http_pagination_budget_authorization_or_artifact_error_remains_fatal"
    ) is not True:
        raise ValueError("v0.5 candidate repair boundary changed")


def load_authorization(path: str | Path) -> dict[str, object]:
    payload = _load_json_object(path)
    validate_authorization(payload)
    validate_parent_bundle()
    return payload


def validate_parent_bundle() -> dict[str, object]:
    parent_authorization = _load_json_object(ROOT / PARENT_AUTHORIZATION_PATH)
    if parent_authorization.get("content_sha256") != PARENT_AUTHORIZATION_CONTENT_SHA256:
        raise ValueError("v0.4 authorization parent changed")
    body = dict(parent_authorization)
    claimed = body.pop("content_sha256", None)
    if claimed != canonical_fingerprint(body):
        raise ValueError("v0.4 authorization parent hash mismatch")

    failure = _load_json_object(ROOT / PARENT_FAILURE_AUDIT_PATH)
    _validate_self_hash(
        failure,
        expected=PARENT_FAILURE_AUDIT_CONTENT_SHA256,
        label="v0.4 failure audit",
    )
    workflow = failure.get("workflow")
    authority = failure.get("frozen_authority")
    artifacts = failure.get("independently_verified_artifacts")
    offline = failure.get("offline_checkpoint_verification")
    accounting = failure.get("provider_accounting")
    repair = failure.get("repair_boundary")
    if (
        not isinstance(workflow, Mapping)
        or workflow.get("run_id") != PARENT_RUN_ID
        or workflow.get("attempt") != 1
        or workflow.get("status") != "failure"
        or not isinstance(authority, Mapping)
        or authority.get("authorization_content_sha256")
        != PARENT_AUTHORIZATION_CONTENT_SHA256
        or authority.get("authorization_permanently_consumed") is not True
        or failure.get("conclusion")
        != "fail_closed_uncaught_candidate_float_normalization_data_validation_error"
    ):
        raise ValueError("v0.4 failure parent provenance changed")
    if not isinstance(artifacts, Mapping):
        raise ValueError("v0.4 preserved artifact evidence is missing")
    checkpoint = artifacts.get("failure_checkpoint")
    summary = artifacts.get("sanitized_failure")
    marker = artifacts.get("consumption_marker")
    if (
        not isinstance(checkpoint, Mapping)
        or checkpoint.get("zip_sha256") != PARENT_FAILURE_CHECKPOINT_ZIP_SHA256
        or not isinstance(summary, Mapping)
        or summary.get("zip_sha256") != PARENT_FAILURE_SUMMARY_ZIP_SHA256
        or not isinstance(marker, Mapping)
        or marker.get("zip_sha256") != PARENT_CONSUMPTION_MARKER_ZIP_SHA256
    ):
        raise ValueError("v0.4 preserved artifact digest changed")
    if (
        not isinstance(offline, Mapping)
        or offline.get("candidate_count") != 946
        or offline.get("date_count") != 30
        or offline.get("source_file_count") != 523
        or offline.get("source_retained_bytes") != 537_662_001
        or offline.get("source_tree_content_sha256")
        != "03182a9b2ccaf026589986f73f6bb3e3c156b360eee5e0cae3f8fc31b1537607"
        or offline.get("market_candidate_and_target_basis_loaders_passed") is not True
        or not isinstance(accounting, Mapping)
        or accounting.get("observed_total_http_attempts") != 14_524
        or accounting.get("observed_attempts_by_host")
        != {
            "api.massive.com": 363,
            "data.alpaca.markets": 14_155,
            "data.sec.gov": 6,
        }
        or not isinstance(repair, Mapping)
        or repair.get("v0_4_may_be_rerun") is not False
        or repair.get("market_membership_identity_and_discovery_may_be_reacquired")
        is not False
    ):
        raise ValueError("v0.4 recoverable checkpoint boundary changed")
    return {
        "v0_4_authorization": parent_authorization,
        "v0_4_failure_audit": failure,
    }


def validate_registration_bundle() -> dict[str, object]:
    path = ROOT / REGISTRATION_AUDIT_PATH
    if path.is_symlink() or not path.is_file():
        raise ValueError("v0.5 registration audit must be a regular file")
    audit = _load_json_object(path)
    expected_keys = {
        "artifact_type",
        "artifacts",
        "authority_boundary",
        "authorization_content_sha256",
        "authorization_id",
        "causal_attestation",
        "content_sha256",
        "frozen_parent",
        "registered_at_date",
        "registration_status",
        "repair",
        "schema_version",
    }
    if set(audit) != expected_keys:
        raise ValueError("v0.5 registration audit fields changed")
    _validate_self_hash(
        audit,
        expected=str(audit.get("content_sha256")),
        label="v0.5 registration audit",
    )
    if (
        audit.get("schema_version") != 1
        or audit.get("artifact_type")
        != "provider_free_sealed_historical_source_recovery_v0_5_registration"
        or audit.get("authorization_id") != AUTHORIZATION_ID
        or audit.get("authorization_content_sha256")
        != AUTHORIZATION_CONTENT_SHA256
        or audit.get("registered_at_date") != "2026-09-01"
        or audit.get("registration_status")
        != "provider_free_complete_recovery_not_dispatched"
    ):
        raise ValueError("v0.5 registration identity changed")
    if audit.get("frozen_parent") != {
        "failure_audit_content_sha256": PARENT_FAILURE_AUDIT_CONTENT_SHA256,
        "failure_checkpoint_zip_sha256": PARENT_FAILURE_CHECKPOINT_ZIP_SHA256,
        "v0_4_authorization_content_sha256": PARENT_AUTHORIZATION_CONTENT_SHA256,
        "v0_4_workflow_run_id": PARENT_RUN_ID,
    }:
        raise ValueError("v0.5 registration parent changed")
    if audit.get("repair") != {
        "candidate_data_errors_fail_closed_per_symbol_date": True,
        "child_network_hosts": ["data.alpaca.markets", "data.sec.gov"],
        "composite_parent_request_seed": 14_524,
        "external_provider_ledgers_cross_bound": True,
        "market_identity_or_massive_requests_repeated": False,
        "massive_blocked_before_child_network_access": True,
        "parent_artifact_replayed_before_consumption": True,
        "parent_normalized_source_reused_exactly": True,
        "provider_checkpoint_before_scanner_freeze": True,
        "provider_free_freeze_separate_job": True,
        "strategy_profiles_or_thresholds_changed": False,
        "third_party_environment_exact_with_commit_specific_editable_line": True,
        "total_request_ceiling": 40_000,
    }:
        raise ValueError("v0.5 registration repair boundary changed")
    if audit.get("authority_boundary") != {
        "automatic_rerun_allowed": False,
        "candidate_bound_databento_authorized": False,
        "exact_commit_tree_and_dispatcher_authorization_required": True,
        "live_order_authorized": False,
        "manual_dispatch_required": True,
        "paper_order_authorized": False,
        "policy_promotion_eligible": False,
        "push_validation_provider_free": True,
        "repository_consumption_tag_required_before_provider_access": True,
    }:
        raise ValueError("v0.5 registration authority boundary changed")
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
        raise ValueError("v0.5 registration causal attestation changed")
    artifacts = audit.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != set(
        REGISTRATION_ARTIFACT_PATHS
    ):
        raise ValueError("v0.5 registration artifact census changed")
    for label, relative in REGISTRATION_ARTIFACT_PATHS.items():
        entry = artifacts.get(label)
        if (
            not isinstance(entry, Mapping)
            or set(entry) != {"file_sha256", "path"}
            or entry.get("path") != relative.as_posix()
        ):
            raise ValueError(f"v0.5 registration artifact {label} changed")
        absolute = ROOT / relative
        if absolute.is_symlink() or not absolute.is_file():
            raise ValueError(f"v0.5 registration artifact {label} is not regular")
        if entry.get("file_sha256") != _file_sha256(absolute):
            raise ValueError(f"v0.5 registration artifact {label} hash changed")
    return audit


__all__ = [
    "AUTHORIZATION_CONTENT_SHA256",
    "AUTHORIZATION_ID",
    "CONSUMPTION_TAG_PREFIX",
    "EXPECTED_DISPATCHER_WORKFLOW_REF",
    "REGISTRATION_ARTIFACT_PATHS",
    "expected_authorization_body",
    "load_authorization",
    "validate_authorization",
    "validate_parent_bundle",
    "validate_registration_bundle",
]
