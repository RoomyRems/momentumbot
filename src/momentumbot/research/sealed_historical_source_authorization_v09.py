"""Authorization-only contract for sealed source recovery v0.9."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Mapping

from momentumbot.research.sealed_historical_source_checkpoint_v09 import (
    canonical_fingerprint,
    validate_authorization_envelope_v09,
)


SCHEMA_VERSION = 1
AUTHORIZATION_ID = "sealed-historical-source-acquisition-v0.9"
AUTHORIZATION_CONTENT_SHA256 = (
    "447c11b09206b4c19ccade6c1aae70ce5bb17e4a483db6f9581d14ee3f5f862f"
)
FAILED_CHILD_AUTHORIZATION_CONTENT_SHA256 = (
    "6fb5fdacd642a9d8957bafa6811d1055411def6de792c6769f929c628343b011"
)
FAILED_CHILD_FAILURE_AUDIT_CONTENT_SHA256 = (
    "dc45346045907afabc77e8321eb21654eef53578dfa5fd4f98cc197bfc85cd95"
)
FAILED_CHILD_RUN_ID = 33543415600
PARENT_FAILURE_AUDIT_CONTENT_SHA256 = (
    "a2637524a3bea25811fee58724d1421493d6ad73866a02e8dcfb35997a717406"
)
PARENT_AUTHORIZATION_CONTENT_SHA256 = (
    "0343efff8ceb49b7c3ae2e589029cf4cf0b02d72c1961f85807913f67385202e"
)
PARENT_RUN_ID = 33521937708
PARENT_FAILURE_CHECKPOINT_ZIP_SHA256 = (
    "ab51a247d4fc86b61d0099087721987b704def9d1086c6cdafb7767d63fa8b6e"
)
PARENT_FAILURE_AUDIT_REPORTED_CHECKPOINT_ZIP_SHA256 = (
    "ab51a247d4fc86fef16203f8dc7fefb104abd71668a37ffc6e450e2513d469c35"
)
PARENT_FAILURE_SUMMARY_ZIP_SHA256 = (
    "824f269328a99b90ec2c7aac6987f93a2dcc9b4d2879c8f23020b183ff3e046a"
)
PARENT_CONSUMPTION_MARKER_ZIP_SHA256 = (
    "c7273ca1e08945790a95f9578ca87bc105e64eee2a951cc7d999390774753257"
)

ROOT = Path(__file__).resolve().parents[3]
AUTHORIZATION_PATH = Path(
    "research/strategy/sealed-historical-source-acquisition-v0.9.json"
)
PARENT_AUTHORIZATION_PATH = Path(
    "research/strategy/sealed-historical-source-acquisition-v0.6.json"
)
FAILED_CHILD_AUTHORIZATION_PATH = Path(
    "research/strategy/sealed-historical-source-acquisition-v0.8.json"
)
PARENT_FAILURE_AUDIT_PATH = Path(
    "research/data-audits/"
    "sealed-historical-source-acquisition-v0.6-run-33521937708-failure-2026-09-01.json"
)
FAILED_CHILD_FAILURE_AUDIT_PATH = Path(
    "research/data-audits/"
    "sealed-historical-source-acquisition-v0.8-run-33543415600-failure-2026-09-01.json"
)
REGISTRATION_AUDIT_PATH = Path(
    "research/data-audits/"
    "sealed-historical-source-acquisition-v0.9-registration-2026-09-01.json"
)
EXPECTED_DISPATCHER_WORKFLOW_REF = (
    "RoomyRems/momentumbot/.github/workflows/"
    "sealed-historical-source-acquisition-v09.yml@refs/heads/main"
)
CONSUMPTION_TAG_PREFIX = (
    "refs/tags/sealed-historical-source-acquisition-v09-consumed-"
)

REGISTRATION_ARTIFACT_PATHS = {
    "acquisition_validator": Path(
        "src/momentumbot/research/sealed_historical_source_acquisition_v09.py"
    ),
    "alpaca_provider": Path("src/momentumbot/providers/alpaca.py"),
    "authorization": AUTHORIZATION_PATH,
    "authorization_validator": Path(
        "src/momentumbot/research/sealed_historical_source_authorization_v09.py"
    ),
    "artifact_metadata_validator": Path(
        "src/momentumbot/research/sealed_historical_source_artifact_metadata_v09.py"
    ),
    "artifact_metadata_runner": Path(
        "scripts/validate_parent_artifact_metadata_v09.py"
    ),
    "artifact_metadata_fixture": Path(
        "research/data-audits/"
        "sealed-historical-source-acquisition-v0.9-parent-artifact-metadata-2026-09-01.json"
    ),
    "checkpoint_builder": Path(
        "scripts/build_sealed_historical_source_checkpoint_v09.py"
    ),
    "checkpoint_validator": Path(
        "src/momentumbot/research/sealed_historical_source_checkpoint_v09.py"
    ),
    "documentation": Path(
        "docs/research/sealed_historical_source_acquisition_v09.md"
    ),
    "failure_audit": FAILED_CHILD_FAILURE_AUDIT_PATH,
    "source_parent_failure_audit": PARENT_FAILURE_AUDIT_PATH,
    "failed_child_authorization": FAILED_CHILD_AUTHORIZATION_PATH,
    "failed_child_registration": Path(
        "research/data-audits/"
        "sealed-historical-source-acquisition-v0.8-registration-2026-09-01.json"
    ),
    "failed_child_workflow": Path(
        ".github/workflows/sealed-historical-source-acquisition-v08.yml"
    ),
    "downstream_identity_compatibility": Path(
        "src/momentumbot/historical_float_identity_v09.py"
    ),
    "authoritative_identity_rule": Path(
        "src/momentumbot/historical_float_identity_v06.py"
    ),
    "float_policy": Path("src/momentumbot/historical_float_v04.py"),
    "historical_data": Path("src/momentumbot/historical_data_v03.py"),
    "http_transport": Path("src/momentumbot/providers/http_json.py"),
    "identity_loader": Path("src/momentumbot/identity_resolved_universe.py"),
    "market_loader": Path("src/momentumbot/causal_market_discovery_v03.py"),
    "news_adapter": Path("scripts/build_causal_news_enrichment_v09.py"),
    "news_parent": Path("scripts/build_causal_news_enrichment_v04.py"),
    "news_policy": Path("src/momentumbot/historical_news.py"),
    "parent_acquisition_validator": Path(
        "src/momentumbot/research/sealed_historical_source_acquisition_v06.py"
    ),
    "parent_authorization": PARENT_AUTHORIZATION_PATH,
    "parent_checkpoint_validator": Path(
        "src/momentumbot/research/sealed_historical_source_checkpoint_v06.py"
    ),
    "parent_float_adapter": Path("scripts/build_causal_float_enrichment_v06.py"),
    "project_metadata": Path("pyproject.toml"),
    "provider_wrapper": Path("scripts/run_provider_entrypoint_v09.py"),
    "provider_transport_guard": Path("scripts/run_provider_entrypoint_v04.py"),
    "recovery_runner": Path("scripts/validate_sealed_historical_source_recovery_v09.py"),
    "recovery_validator": Path(
        "src/momentumbot/research/sealed_historical_source_recovery_v09.py"
    ),
    "request_budget": Path("src/momentumbot/providers/request_budget.py"),
    "requirements": Path("requirements-sealed-source-v04.txt"),
    "runner": Path("scripts/run_sealed_historical_source_acquisition_v09.py"),
    "scanner_adapter": Path("scripts/build_causal_scanner_snapshot_v09.py"),
    "scanner_parent": Path("scripts/build_causal_scanner_snapshot_v04.py"),
    "scanner_policy": Path("src/momentumbot/causal_scanner_snapshot_v03.py"),
    "scanner_source_inputs": Path("src/momentumbot/scanner_source_inputs_v03.py"),
    "selected_dates": Path(
        "src/momentumbot/research/sealed_historical_availability.py"
    ),
    "strategy_profile_union": Path(
        "src/momentumbot/historical_profile_union_v01.py"
    ),
    "workflow": Path(
        ".github/workflows/sealed-historical-source-acquisition-v09.yml"
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
    validated = validate_authorization_envelope_v09(payload)
    if validated.get("content_sha256") != AUTHORIZATION_CONTENT_SHA256:
        raise ValueError("historical source v0.9 differs from frozen hash")
    if validated.get("dispatcher_contract") != {
        "contents_write_allowed_only_in_consumption_job": True,
        "dispatcher_blob_must_match_authorized_research_workflow": True,
        "provider_credentials_allowed_in_consume_or_freeze_job": False,
        "provider_free_freeze_is_separate_job": True,
        "workflow_ref": EXPECTED_DISPATCHER_WORKFLOW_REF,
    }:
        raise ValueError("v0.9 dispatcher contract changed")
    if validated.get("failed_child") != {
        "authorization_commit_sha": "4d36948548fcb630a9973ff639127e74fc6acf50",
        "authorization_content_sha256": FAILED_CHILD_AUTHORIZATION_CONTENT_SHA256,
        "authorization_id": "sealed-historical-source-acquisition-v0.8",
        "authorization_permanently_consumed": False,
        "authorization_tree_sha": "18396d2259161a9527f98fa6c41f256572c15be7",
        "consumption_tag_created": False,
        "dispatcher_workflow_sha": "53c0f5cce78464614115a1d4a80af548147a9953",
        "failure_audit_content_sha256": FAILED_CHILD_FAILURE_AUDIT_CONTENT_SHA256,
        "provider_calls": 0,
        "workflow_run_attempt": 1,
        "workflow_run_id": FAILED_CHILD_RUN_ID,
    }:
        raise ValueError("v0.9 failed-child provenance changed")
    if validated.get("reproducibility_environment_contract") != {
        "clean_cpython_3_12_virtual_environment_required_per_job": True,
        "editable_project_lines_must_match_respective_authorized_commits": True,
        "parent_artifact_full_replay_required_before_consumption": True,
        "parent_third_party_environment_freeze_must_match": True,
        "pip_check_required": True,
        "requirements_hashes_and_binary_wheels_required": True,
        "requirements_path": "requirements-sealed-source-v04.txt",
    }:
        raise ValueError("v0.9 reproducibility environment contract changed")
    provider = validated.get("provider_entrypoint_contract")
    if not isinstance(provider, Mapping) or provider.get("child_network_hosts") != [
        "data.alpaca.markets",
    ] or provider.get("massive_identity_market_sec_or_float_entrypoint_allowed") is not False:
        raise ValueError("v0.9 child provider network boundary changed")
    if validated.get("repair_boundary") != {
        "accepted_identity_kinds": ["composite_figi", "unique_cik_fallback"],
        "all_946_candidates_and_float_records_preflighted_before_consumption": True,
        "candidate_identity_values_rewritten": False,
        "float_records_rewritten": False,
        "field_specific_sanitized_artifact_metadata_diagnostics": True,
        "downloaded_zip_sha256_matches_frozen_artifact_metadata": True,
        "frozen_real_artifact_metadata_fixture_required": True,
        "news_and_scanner_use_one_downstream_compatibility_rule": True,
        "obsolete_cik_identity_kind_accepted": False,
        "parent_artifact_metadata_fetched_once_per_gate": True,
        "raw_provider_response_persisted": False,
        "strategy_float_news_scanner_or_micro_policy_changed": False,
        "transport_http_pagination_budget_authorization_or_artifact_error_remains_fatal": True,
    }:
        raise ValueError("v0.9 downstream identity repair boundary changed")


def load_authorization(path: str | Path) -> dict[str, object]:
    payload = _load_json_object(path)
    validate_authorization(payload)
    validate_parent_bundle()
    return payload


def validate_parent_bundle() -> dict[str, object]:
    parent_authorization = _load_json_object(ROOT / PARENT_AUTHORIZATION_PATH)
    if parent_authorization.get("content_sha256") != PARENT_AUTHORIZATION_CONTENT_SHA256:
        raise ValueError("v0.6 authorization parent changed")
    body = dict(parent_authorization)
    claimed = body.pop("content_sha256", None)
    if claimed != canonical_fingerprint(body):
        raise ValueError("v0.6 authorization parent hash mismatch")

    failure = _load_json_object(ROOT / PARENT_FAILURE_AUDIT_PATH)
    _validate_self_hash(
        failure,
        expected=PARENT_FAILURE_AUDIT_CONTENT_SHA256,
        label="v0.6 failure audit",
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
        != "fail_closed_downstream_identity_loader_version_mismatch"
    ):
        raise ValueError("v0.6 failure parent provenance changed")
    if not isinstance(artifacts, Mapping):
        raise ValueError("v0.6 preserved artifact evidence is missing")
    checkpoint = artifacts.get("failure_checkpoint")
    summary = artifacts.get("sanitized_failure")
    marker = artifacts.get("consumption_marker")
    if (
        not isinstance(checkpoint, Mapping)
        or checkpoint.get("zip_sha256")
        != PARENT_FAILURE_AUDIT_REPORTED_CHECKPOINT_ZIP_SHA256
        or not isinstance(summary, Mapping)
        or summary.get("zip_sha256") != PARENT_FAILURE_SUMMARY_ZIP_SHA256
        or not isinstance(marker, Mapping)
        or marker.get("zip_sha256") != PARENT_CONSUMPTION_MARKER_ZIP_SHA256
    ):
        raise ValueError("v0.6 preserved artifact digest changed")
    if (
        not isinstance(offline, Mapping)
        or offline.get("candidate_count") != 946
        or offline.get("date_count") != 30
        or offline.get("float_record_count") != 946
        or offline.get("source_file_count") != 584
        or offline.get("source_retained_bytes") != 542_222_230
        or offline.get("source_tree_content_sha256")
        != "7eec4b420581efa52e39208952f386d4f81a092a39bca5c4acaaee7da642740c"
        or offline.get("accepted_composite_figi_candidates") != 737
        or offline.get("accepted_unique_cik_fallback_candidates") != 209
        or offline.get(
            "all_candidates_and_float_records_load_with_authoritative_identity_contract"
        )
        is not True
        or not isinstance(accounting, Mapping)
        or accounting.get("observed_total_http_attempts") != 17_540
        or accounting.get("observed_attempts_by_host")
        != {
            "api.massive.com": 363,
            "data.alpaca.markets": 15_849,
            "data.sec.gov": 1_328,
        }
        or not isinstance(repair, Mapping)
        or repair.get("v0_6_may_be_rerun") is not False
        or repair.get("massive_identity_market_sec_and_float_acquisition_may_be_repeated")
        is not False
    ):
        raise ValueError("v0.6 recoverable checkpoint boundary changed")

    failed_child_authorization = _load_json_object(
        ROOT / FAILED_CHILD_AUTHORIZATION_PATH
    )
    if (
        failed_child_authorization.get("content_sha256")
        != FAILED_CHILD_AUTHORIZATION_CONTENT_SHA256
    ):
        raise ValueError("v0.8 authorization parent changed")
    failed_child_body = dict(failed_child_authorization)
    failed_child_claimed = failed_child_body.pop("content_sha256", None)
    if failed_child_claimed != canonical_fingerprint(failed_child_body):
        raise ValueError("v0.8 authorization parent hash mismatch")

    failed_child = _load_json_object(ROOT / FAILED_CHILD_FAILURE_AUDIT_PATH)
    _validate_self_hash(
        failed_child,
        expected=FAILED_CHILD_FAILURE_AUDIT_CONTENT_SHA256,
        label="v0.8 failure audit",
    )
    failed_workflow = failed_child.get("workflow")
    failed_authority = failed_child.get("frozen_authority")
    failed_causal = failed_child.get("causal_attestation")
    failed_artifacts = failed_child.get("run_artifacts")
    failed_metadata = failed_child.get("independently_verified_parent_artifact")
    failed_repair = failed_child.get("repair_boundary")
    failed_accounting = failed_child.get("provider_accounting")
    if (
        not isinstance(failed_workflow, Mapping)
        or failed_workflow.get("run_id") != FAILED_CHILD_RUN_ID
        or failed_workflow.get("attempt") != 1
        or failed_workflow.get("event") != "workflow_dispatch"
        or failed_workflow.get("status") != "failure"
        or not isinstance(failed_authority, Mapping)
        or failed_authority.get("authorization_content_sha256")
        != FAILED_CHILD_AUTHORIZATION_CONTENT_SHA256
        or failed_authority.get("authorization_permanently_consumed") is not False
        or failed_authority.get("authorization_commit_sha")
        != "4d36948548fcb630a9973ff639127e74fc6acf50"
        or failed_authority.get("authorization_tree_sha")
        != "18396d2259161a9527f98fa6c41f256572c15be7"
        or failed_child.get("conclusion")
        != "fail_closed_preregistered_parent_artifact_digest_mismatch"
    ):
        raise ValueError("v0.8 failure parent provenance changed")
    if (
        not isinstance(failed_causal, Mapping)
        or failed_causal.get("authorization_consumed") is not False
        or failed_causal.get("provider_called") is not False
        or failed_causal.get("transcript_record_values_read") is not False
        or not isinstance(failed_artifacts, Mapping)
        or failed_artifacts.get("artifact_count") != 0
        or failed_artifacts.get("consumption_marker_created") is not False
        or not isinstance(failed_metadata, Mapping)
        or failed_metadata.get("artifact_id") != 9_806_541_315
        or failed_metadata.get("digest")
        != "sha256:ab51a247d4fc86b61d0099087721987b704def9d1086c6cdafb7767d63fa8b6e"
        or failed_metadata.get("digest_matches_downloaded_zip_sha256") is not True
        or failed_metadata.get("archive_integrity_check") != "passed"
        or failed_metadata.get("v0_8_preregistered_digest")
        != "sha256:ab51a247d4fc86fef16203f8dc7fefb104abd71668a37ffc6e450e2513d469c35"
        or failed_metadata.get("workflow_run_id") != PARENT_RUN_ID
        or failed_metadata.get("expired") is not False
        or not isinstance(failed_repair, Mapping)
        or failed_repair.get("v0_8_may_be_rerun") is not False
        or failed_repair.get("artifact_metadata_must_be_fetched_once") is not True
        or failed_repair.get("frozen_real_metadata_fixture_required") is not True
        or failed_repair.get("downloaded_zip_sha256_must_match_frozen_live_metadata")
        is not True
        or not isinstance(failed_accounting, Mapping)
        or failed_accounting.get("child_attempts") != 0
        or failed_accounting.get("observed_total_http_attempts") != 17_540
    ):
        raise ValueError("v0.8 safe pre-consumption failure boundary changed")
    return {
        "v0_6_authorization": parent_authorization,
        "v0_6_failure_audit": failure,
        "v0_8_authorization": failed_child_authorization,
        "v0_8_failure_audit": failed_child,
    }


def validate_registration_bundle() -> dict[str, object]:
    path = ROOT / REGISTRATION_AUDIT_PATH
    if path.is_symlink() or not path.is_file():
        raise ValueError("v0.9 registration audit must be a regular file")
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
        raise ValueError("v0.9 registration audit fields changed")
    _validate_self_hash(
        audit,
        expected=str(audit.get("content_sha256")),
        label="v0.9 registration audit",
    )
    if (
        audit.get("schema_version") != 1
        or audit.get("artifact_type")
        != "provider_free_sealed_historical_source_recovery_v0_9_registration"
        or audit.get("authorization_id") != AUTHORIZATION_ID
        or audit.get("authorization_content_sha256")
        != AUTHORIZATION_CONTENT_SHA256
        or audit.get("registered_at_date") != "2026-09-01"
        or audit.get("registration_status")
        != "provider_free_complete_recovery_not_dispatched"
    ):
        raise ValueError("v0.9 registration identity changed")
    if audit.get("frozen_parent") != {
        "failed_child_authorization_content_sha256": FAILED_CHILD_AUTHORIZATION_CONTENT_SHA256,
        "failed_child_failure_audit_content_sha256": FAILED_CHILD_FAILURE_AUDIT_CONTENT_SHA256,
        "failed_child_workflow_run_id": FAILED_CHILD_RUN_ID,
        "failure_audit_content_sha256": PARENT_FAILURE_AUDIT_CONTENT_SHA256,
        "failure_checkpoint_zip_sha256": PARENT_FAILURE_CHECKPOINT_ZIP_SHA256,
        "v0_6_authorization_content_sha256": PARENT_AUTHORIZATION_CONTENT_SHA256,
        "v0_6_workflow_run_id": PARENT_RUN_ID,
    }:
        raise ValueError("v0.9 registration parent changed")
    if audit.get("repair") != {
        "all_946_candidates_and_float_records_preflighted": True,
        "authoritative_identity_kinds": ["composite_figi", "unique_cik_fallback"],
        "child_network_hosts": ["data.alpaca.markets"],
        "composite_parent_request_seed": 17_540,
        "field_specific_sanitized_artifact_metadata_diagnostics": True,
        "downloaded_zip_sha256_matches_frozen_artifact_metadata": True,
        "frozen_real_artifact_metadata_fixture_required": True,
        "parent_artifact_metadata_fetched_once_per_gate": True,
        "downstream_identity_values_or_float_records_rewritten": False,
        "external_provider_ledgers_cross_bound": True,
        "massive_identity_market_sec_or_float_requests_repeated": False,
        "non_alpaca_hosts_blocked_before_child_network_access": True,
        "news_and_scanner_use_one_compatibility_rule": True,
        "obsolete_cik_identity_kind_rejected": True,
        "parent_artifact_replayed_before_consumption": True,
        "parent_normalized_source_reused_exactly": True,
        "provider_checkpoint_before_scanner_freeze": True,
        "provider_free_freeze_separate_job": True,
        "strategy_profiles_or_thresholds_changed": False,
        "third_party_environment_exact_with_commit_specific_editable_line": True,
        "total_request_ceiling": 40_000,
    }:
        raise ValueError("v0.9 registration repair boundary changed")
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
        raise ValueError("v0.9 registration authority boundary changed")
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
        raise ValueError("v0.9 registration causal attestation changed")
    artifacts = audit.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != set(
        REGISTRATION_ARTIFACT_PATHS
    ):
        raise ValueError("v0.9 registration artifact census changed")
    for label, relative in REGISTRATION_ARTIFACT_PATHS.items():
        entry = artifacts.get(label)
        if (
            not isinstance(entry, Mapping)
            or set(entry) != {"file_sha256", "path"}
            or entry.get("path") != relative.as_posix()
        ):
            raise ValueError(f"v0.9 registration artifact {label} changed")
        absolute = ROOT / relative
        if absolute.is_symlink() or not absolute.is_file():
            raise ValueError(f"v0.9 registration artifact {label} is not regular")
        if entry.get("file_sha256") != _file_sha256(absolute):
            raise ValueError(f"v0.9 registration artifact {label} hash changed")
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
