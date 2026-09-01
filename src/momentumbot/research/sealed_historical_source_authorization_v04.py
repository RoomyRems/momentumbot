"""Authorization-only contract for sealed historical source acquisition v0.4."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Mapping

from momentumbot.historical_profile_union_v01 import (
    historical_profile_union_v0_1_manifest,
)
from momentumbot.research.sealed_historical_source_acquisition_v03 import (
    AUTHORIZATION_CONTENT_SHA256 as V03_AUTHORIZATION_CONTENT_SHA256,
    expected_authorization_body as expected_v03_authorization_body,
    validate_authorization as validate_v03_authorization,
)
from momentumbot.research.sealed_historical_walk_forward import (
    canonical_fingerprint,
)


SCHEMA_VERSION = 1
AUTHORIZATION_ID = "sealed-historical-source-acquisition-v0.4"
# Filled from the canonical JSON body below.  The value is deliberately kept
# next to the validator so the checked-in authorization cannot drift.
AUTHORIZATION_CONTENT_SHA256 = (
    "bbe51f4483a73f92b1f58c9f6c2085d8a47505346c2d340fbe59c0421f3f31b7"
)

ROOT = Path(__file__).resolve().parents[3]
V03_AUTHORIZATION_PATH = Path(
    "research/strategy/sealed-historical-source-acquisition-v0.3.json"
)
V03_FAILURE_AUDIT_PATH = Path(
    "research/data-audits/"
    "sealed-historical-source-acquisition-v0.3-run-33449815223-failure-2026-09-01.json"
)
REGISTRATION_AUDIT_PATH = Path(
    "research/data-audits/"
    "sealed-historical-source-acquisition-v0.4-registration-2026-09-01.json"
)
V02_SUCCESS_AUDIT_PATH = Path(
    "research/data-audits/"
    "sealed-historical-source-acquisition-v0.2-run-33389380992-success-2026-08-31.json"
)

V03_FAILURE_AUDIT_CONTENT_SHA256 = (
    "f63d995117fb95d673d9b0678baa258086f67f9f11bde331acbd74ee7604baaf"
)
V03_FAILURE_ZIP_SHA256 = (
    "71afe1777bb71beb3abcc1dba4682206fd1b555e1a47d9d998e0300053523478"
)
V03_CONSUMPTION_MARKER_ZIP_SHA256 = (
    "ca1243c521f0b2f19c1507d48b7b11078a103faed7d4fea75f982f7d0d46b070"
)
V03_WORKFLOW_RUN_ID = 33449815223
V02_SUCCESS_AUDIT_CONTENT_SHA256 = (
    "5be0fef73e639a6cbe9d40b0ec6b38ca22aefb007175790a7bc45248eeac583c"
)
V02_SUCCESS_ZIP_SHA256 = (
    "4d2b7528c846b428acee3024dbc727646b60756f0b811afcdfce1398dbdc5254"
)
V02_WORKFLOW_RUN_ID = 33389380992
PARENT_CANDIDATE_CAP = 50
MAX_CANDIDATES_PER_DATE_V04 = 100
EXPECTED_DISPATCHER_WORKFLOW_REF = (
    "RoomyRems/momentumbot/.github/workflows/"
    "sealed-historical-source-acquisition-v04.yml@refs/heads/main"
)
CONSUMPTION_TAG_PREFIX = (
    "refs/tags/sealed-historical-source-acquisition-v04-consumed-"
)
REGISTRATION_ARTIFACT_PATHS = {
    "acquisition_validator": Path(
        "src/momentumbot/research/sealed_historical_source_acquisition_v04.py"
    ),
    "alpaca_provider": Path("src/momentumbot/providers/alpaca.py"),
    "authorization": Path(
        "research/strategy/sealed-historical-source-acquisition-v0.4.json"
    ),
    "authorization_validator": Path(
        "src/momentumbot/research/sealed_historical_source_authorization_v04.py"
    ),
    "census_builder": Path("scripts/build_massive_historical_census.py"),
    "checkpoint_builder": Path(
        "scripts/build_sealed_historical_source_checkpoint_v04.py"
    ),
    "checkpoint_validator": Path(
        "src/momentumbot/research/sealed_historical_source_checkpoint_v01.py"
    ),
    "documentation": Path(
        "docs/research/sealed_historical_source_acquisition_v04.md"
    ),
    "float_builder": Path("scripts/build_causal_float_enrichment_v04.py"),
    "float_policy": Path("src/momentumbot/historical_float_v04.py"),
    "historical_data": Path("src/momentumbot/historical_data_v03.py"),
    "http_transport": Path("src/momentumbot/providers/http_json.py"),
    "identity_continuity_builder": Path(
        "scripts/audit_historical_identity_continuity.py"
    ),
    "identity_resolved_universe": Path(
        "src/momentumbot/identity_resolved_universe.py"
    ),
    "instrument_metadata_builder": Path(
        "scripts/audit_massive_instrument_metadata.py"
    ),
    "market_builder": Path(
        "scripts/build_identity_resolved_market_discovery_v04.py"
    ),
    "market_coverage_builder": Path(
        "scripts/audit_massive_alpaca_market_coverage.py"
    ),
    "market_policy": Path("src/momentumbot/causal_market_discovery_v03.py"),
    "massive_provider": Path("src/momentumbot/providers/massive.py"),
    "news_builder": Path("scripts/build_causal_news_enrichment_v04.py"),
    "news_policy": Path("src/momentumbot/historical_news.py"),
    "project_metadata": Path("pyproject.toml"),
    "provider_wrapper": Path("scripts/run_provider_entrypoint_v04.py"),
    "provisional_universe_builder": Path(
        "scripts/build_massive_provisional_universe.py"
    ),
    "request_budget": Path("src/momentumbot/providers/request_budget.py"),
    "requirements": Path("requirements-sealed-source-v04.txt"),
    "runner": Path("scripts/run_sealed_historical_source_acquisition_v04.py"),
    "scanner_builder": Path("scripts/build_causal_scanner_snapshot_v04.py"),
    "scanner_policy": Path("src/momentumbot/causal_scanner_snapshot_v03.py"),
    "scanner_source_inputs": Path("src/momentumbot/scanner_source_inputs_v03.py"),
    "sec_provider": Path("src/momentumbot/providers/sec_edgar.py"),
    "strategy_profile_union": Path(
        "src/momentumbot/historical_profile_union_v01.py"
    ),
    "universe_builder": Path("scripts/build_identity_resolved_universe.py"),
    "v0_3_failure_audit": V03_FAILURE_AUDIT_PATH,
    "workflow": Path(
        ".github/workflows/sealed-historical-source-acquisition-v04.yml"
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


def expected_authorization_body() -> dict[str, object]:
    """Return the exact v0.4 child body derived from frozen v0.3."""

    body = deepcopy(expected_v03_authorization_body())
    body.update(
        {
            "artifact_type": (
                "preregistered_sealed_historical_source_acquisition_v0_4_repair"
            ),
            "authorization_id": AUTHORIZATION_ID,
            "registered_at_date": "2026-09-01",
        }
    )

    frozen_parent = body["frozen_parent"]
    assert isinstance(frozen_parent, dict)
    frozen_parent.update(
        {
            "v0_3_authorization_content_sha256": (
                V03_AUTHORIZATION_CONTENT_SHA256
            ),
            "v0_3_failure_audit_content_sha256": (
                V03_FAILURE_AUDIT_CONTENT_SHA256
            ),
            "v0_3_workflow_run_id": str(V03_WORKFLOW_RUN_ID),
            "v0_3_sanitized_failure_zip_sha256": V03_FAILURE_ZIP_SHA256,
            "v0_3_consumption_marker_zip_sha256": (
                V03_CONSUMPTION_MARKER_ZIP_SHA256
            ),
        }
    )

    request_budget = body["request_budget"]
    assert isinstance(request_budget, dict)
    sec_budget = request_budget["sec"]
    news_budget = request_budget["news"]
    assert isinstance(sec_budget, dict)
    assert isinstance(news_budget, dict)
    sec_budget["maximum_candidates_per_date"] = MAX_CANDIDATES_PER_DATE_V04
    news_budget["maximum_candidates_per_date"] = MAX_CANDIDATES_PER_DATE_V04
    request_budget["candidate_operational_ceiling"] = {
        "parent_maximum_candidates_per_date": PARENT_CANDIDATE_CAP,
        "maximum_candidates_per_date": MAX_CANDIDATES_PER_DATE_V04,
        "reason": "immutable_general_and_small_profile_acquisition_union",
        "silent_truncation_allowed": False,
        "strategy_threshold_changed": False,
    }
    request_budget["provider_routes"] = {
        "massive": [
            "reference_tickers",
            "ticker_types",
            "stock_splits",
        ],
        "alpaca": [
            "sip_stock_bars",
            "corporate_actions",
            "news",
        ],
        "sec": [
            "companyfacts",
            "submissions",
        ],
        "routes_changed_from_v0_3": False,
    }

    retention = body["retention_budget"]
    assert isinstance(retention, dict)
    retention.update(
        {
            "pre_scanner_source_checkpoint_persisted": True,
            "upstream_progress_artifact_persisted_before_canonical_source_inputs": True,
            "pinned_requirements_persisted": True,
            "pip_freeze_persisted": True,
        }
    )

    one_shot = body["one_shot_contract"]
    assert isinstance(one_shot, dict)
    one_shot.update(
        {
            "manual_workflow_dispatch_required": True,
            "push_or_schedule_provider_access_allowed": False,
            "v0_3_authorization_may_be_rerun": False,
            "prior_authorization_reruns_allowed": {
                "v0.1": False,
                "v0.2": False,
                "v0.3": False,
            },
            "repository_consumption_tag_created_atomically_before_provider_access": True,
            "repository_consumption_tag_prefix": CONSUMPTION_TAG_PREFIX,
            "repository_consumption_tag_target": "exact_authorization_commit",
            "repository_consumption_tag_deletion_allowed": False,
            "consumption_marker_binds_tag_name_and_target": True,
        }
    )

    parent_normalization = body["normalization_contract"]
    assert isinstance(parent_normalization, dict)
    failed_scanner_policy = parent_normalization.pop("scanner_policy")
    parent_normalization.update(
        {
            "failed_v0_3_scanner_policy_parent": failed_scanner_policy,
            "scanner_policy": {
                "policy_id": "causal-scanner-snapshot-v0.3",
                "supersedes_policy_id": "causal-scanner-snapshot-v0.2",
                "displayed_price_validation_source": "raw_target_close",
                "cumulative_volume_validation_source": "raw_target_volume",
                "percent_gain_validation_source": (
                    "split_target_close_over_split_previous_close"
                ),
                "cross_sectional_rank_source": (
                    "split_target_close_over_split_previous_close"
                ),
                "raw_split_timestamp_coverage_must_match": True,
            },
            "validator_gain_compared_with_raw_display_price": False,
            "validator_gain_compared_with_split_target_price": True,
        }
    )

    body["acquisition_profile_union_contract"] = {
        **historical_profile_union_v0_1_manifest(),
        "acquisition_only": True,
        "general_strategy_profile_changed": False,
        "small_account_strategy_profile_changed": False,
        "micro_policy_changed": False,
    }
    body["float_normalization_contract"] = {
        "policy_id": "causal-sec-float-v0.2",
        "source_target_basis_artifact_id": "causal-float-target-basis-v0.1",
        "provider_adjustment_ratio": "A_x_equals_raw_close_x_over_split_close_x",
        "measure_to_target_share_factor": "A_measure_div_A_target",
        "target_pair_source": "exact_market_qualification_minute_raw_and_split_close",
        "later_target_session_price_allowed": False,
        "post_target_provider_split_factor_cancels": True,
        "missing_or_misaligned_target_pair_fails_closed": True,
    }
    body["pre_scanner_checkpoint_contract"] = {
        "artifact_id": "sealed-historical-source-checkpoint-v0.1",
        "contains_label_blind_acquired_and_canonical_source_inputs": True,
        "contains_scanner_snapshots": False,
        "upload_completed_before_scanner_loader_or_validator": True,
        "upload_completed_before_provider_free_freeze": True,
        "checkpoint_builder_provider_calls_allowed": False,
        "uploaded_in_provider_job": True,
        "downloaded_by_separate_provider_free_freeze_job": True,
        "request_budget_and_blocked_attempt_ledger_retained": True,
    }
    body["reproducibility_environment_contract"] = {
        "requirements_path": "requirements-sealed-source-v04.txt",
        "runner_image": "ubuntu-24.04",
        "architecture": "x86_64",
        "python_implementation": "CPython",
        "python_version": "3.12",
        "pip_version": "26.2.1",
        "clean_virtual_environment_required_per_job": True,
        "requirements_hashes_required": True,
        "binary_wheels_only": True,
        "source_distributions_allowed": False,
        "requirements_installed_without_dependency_resolution": True,
        "editable_project_installed_without_dependency_resolution_or_build_isolation": True,
        "pip_check_required": True,
        "pip_freeze_captured_before_provider_access": True,
        "requirements_and_freeze_retained_in_checkpoint": True,
        "environment_reuse_after_checkpoint_required": False,
        "provider_free_freeze_job_recreates_environment": True,
        "provider_free_freeze_environment_must_byte_match_checkpoint": True,
    }
    body["provider_entrypoint_contract"] = {
        "wrapper_path": "scripts/run_provider_entrypoint_v04.py",
        "all_network_capable_acquisition_scripts_must_use_wrapper": True,
        "allowed_hosts": list(request_budget["allowed_hosts"]),
        "https_only": True,
        "redirects_allowed": False,
        "redirects_rejected_before_follow_up_network_access": True,
        "ambient_proxy_use_allowed": False,
        "direct_https_transport_only": True,
        "direct_socket_or_process_escape_allowed": False,
        "disallowed_host_fails_before_network_access": True,
        "blocked_attempt_ledger_path_must_be_absolute": True,
        "blocked_attempt_ledger_sanitized": True,
        "blocked_request_budget_attempts_define_ceiling_exhaustion": True,
        "successful_provider_checkpoint_requires_zero_blocked_attempts": True,
        "provider_substitution_allowed": False,
    }
    body["dispatcher_contract"] = {
        "workflow_ref": EXPECTED_DISPATCHER_WORKFLOW_REF,
        "dispatcher_blob_must_match_authorized_research_workflow": True,
        "provider_job_timeout_minutes": 360,
        "canonical_source_step_timeout_minutes": 150,
        "provider_free_freeze_is_separate_job": True,
        "provider_credentials_allowed_in_consume_or_freeze_job": False,
        "contents_write_allowed_only_in_consumption_job": True,
    }
    body["execution_order_contract"] = [
        "validate_exact_authorization_and_frozen_parents_provider_free",
        "capture_pinned_environment_before_provider_access",
        "create_provenance_bound_consumption_marker_provider_free",
        "atomically_create_repository_consumption_tag_before_provider_access",
        "upload_consumption_marker_before_provider_access",
        "acquire_exact_frozen_provider_routes_through_pre_network_wrapper",
        "upload_upstream_progress_before_canonical_scanner_source_acquisition",
        "close_provider_access_and_persist_canonical_source_inputs",
        "build_and_upload_pre_scanner_source_checkpoint",
        "download_checkpoint_in_separate_provider_free_freeze_job",
        "recreate_and_byte_compare_frozen_environment_provider_free",
        "require_zero_blocked_attempts_provider_free",
        "load_validate_and_freeze_label_blind_scanner_outputs_provider_free",
        "deep_validate_and_exactly_replay_completed_bundle_provider_free",
    ]
    body["repair_boundary"] = {
        "v0_3_validator_mismatch_repaired": True,
        "v0_3_additional_provider_free_blockers_repaired": True,
        "dates_changed": False,
        "providers_or_routes_changed": False,
        "total_request_ceiling_changed": False,
        "retention_byte_ceiling_changed": False,
        "candidate_operational_cap_changed_from_50_to_100": True,
        "acquisition_profile_union_added": True,
        "strategy_or_account_profile_changed": False,
        "micro_policy_changed": False,
        "source_v0_3_partial_tree_reused": False,
        "provider_substitution_allowed": False,
    }
    return body


def _validate_content_hash(
    payload: Mapping[str, object],
    *,
    expected: str,
    label: str,
) -> None:
    body = dict(payload)
    claimed = body.pop("content_sha256", None)
    if claimed != expected or canonical_fingerprint(body) != claimed:
        raise ValueError(f"{label} content hash mismatch")


def validate_parent_bundle() -> dict[str, dict[str, object]]:
    """Load and validate the exact frozen parents from the repository root."""

    v03_authorization = _load_json_object(ROOT / V03_AUTHORIZATION_PATH)
    validate_v03_authorization(v03_authorization)
    if v03_authorization.get("content_sha256") != V03_AUTHORIZATION_CONTENT_SHA256:
        raise ValueError("v0.3 authorization parent changed")

    failure = _load_json_object(ROOT / V03_FAILURE_AUDIT_PATH)
    _validate_content_hash(
        failure,
        expected=V03_FAILURE_AUDIT_CONTENT_SHA256,
        label="v0.3 failure audit",
    )
    workflow = failure.get("workflow")
    authority = failure.get("frozen_authority")
    artifacts = failure.get("independently_verified_artifacts")
    partial = failure.get("partial_result")
    attestation = failure.get("causal_attestation")
    if (
        not isinstance(workflow, Mapping)
        or workflow.get("run_id") != V03_WORKFLOW_RUN_ID
        or workflow.get("attempt") != 1
        or not isinstance(authority, Mapping)
        or authority.get("authorization_content_sha256")
        != V03_AUTHORIZATION_CONTENT_SHA256
        or authority.get("authorization_permanently_consumed") is not True
        or failure.get("conclusion")
        != "fail_closed_split_consistent_gain_was_incorrectly_validated_against_raw_display_price"
        or not isinstance(partial, Mapping)
        or partial.get("reusable_completed_source_bundle_exists") is not False
        or partial.get("partial_source_tree_uploaded") is not False
    ):
        raise ValueError("v0.3 failure parent provenance changed")
    if not isinstance(artifacts, Mapping):
        raise ValueError("v0.3 independently verified artifacts are missing")
    sanitized = artifacts.get("sanitized_failure")
    marker = artifacts.get("consumption_marker")
    if (
        not isinstance(sanitized, Mapping)
        or sanitized.get("zip_sha256") != V03_FAILURE_ZIP_SHA256
        or not isinstance(marker, Mapping)
        or marker.get("zip_sha256") != V03_CONSUMPTION_MARKER_ZIP_SHA256
    ):
        raise ValueError("v0.3 preserved artifact digest changed")
    if not isinstance(attestation, Mapping) or any(
        attestation.get(field) is not False
        for field in (
            "account_or_order_endpoint_called",
            "automatic_rerun_allowed",
            "databento_called",
            "order_submitted",
            "provider_substitution_occurred",
            "ross_labels_or_outcomes_read",
            "strategy_micro_or_account_policy_changed",
            "transcript_record_values_read",
        )
    ):
        raise ValueError("v0.3 failure causal attestation changed")

    v02_success = _load_json_object(ROOT / V02_SUCCESS_AUDIT_PATH)
    _validate_content_hash(
        v02_success,
        expected=V02_SUCCESS_AUDIT_CONTENT_SHA256,
        label="v0.2 success audit",
    )
    v02_workflow = v02_success.get("workflow")
    v02_result = v02_success.get("result")
    v02_authority = v02_success.get("authority_boundary")
    v02_attestation = v02_success.get("causal_attestation")
    if (
        not isinstance(v02_workflow, Mapping)
        or v02_workflow.get("run_id") != V02_WORKFLOW_RUN_ID
        or v02_workflow.get("run_attempt") != 1
        or v02_workflow.get("conclusion") != "success"
        or v02_workflow.get("artifact_github_digest")
        != f"sha256:{V02_SUCCESS_ZIP_SHA256}"
        or not isinstance(v02_result, Mapping)
        or v02_result.get("source_acquisition_gate_passed") is not True
        or not isinstance(v02_authority, Mapping)
        or v02_authority.get("source_acquisition_rerun_authorized") is not False
    ):
        raise ValueError("v0.2 success parent provenance changed")
    if (
        not isinstance(v02_attestation, Mapping)
        or v02_attestation.get("raw_provider_http_responses_persisted") is not False
        or v02_attestation.get("transcript_record_values_read") is not False
        or v02_attestation.get("ross_labels_or_outcomes_read") is not False
        or v02_attestation.get("databento_called") is not False
        or v02_attestation.get("account_or_order_endpoint_called") is not False
        or v02_attestation.get("order_submitted") is not False
    ):
        raise ValueError("v0.2 success causal attestation changed")

    return {
        "v0_3_authorization": v03_authorization,
        "v0_3_failure_audit": failure,
        "v0_2_success_audit": v02_success,
    }


def validate_registration_bundle() -> dict[str, object]:
    """Validate the provider-free v0.4 registration and every bound file."""

    audit_path = ROOT / REGISTRATION_AUDIT_PATH
    if audit_path.is_symlink() or not audit_path.is_file():
        raise ValueError("v0.4 registration audit must be a regular file")
    audit = _load_json_object(audit_path)
    if set(audit) != {
        "artifact_type",
        "artifacts",
        "authority_boundary",
        "authorization_content_sha256",
        "authorization_id",
        "causal_attestation",
        "content_sha256",
        "frozen_parents",
        "registered_at_date",
        "registration_status",
        "repair",
        "schema_version",
    }:
        raise ValueError("v0.4 registration audit fields changed")
    unsigned = dict(audit)
    claimed = unsigned.pop("content_sha256", None)
    if claimed != canonical_fingerprint(unsigned):
        raise ValueError("v0.4 registration audit content hash mismatch")
    if (
        audit.get("schema_version") != 1
        or audit.get("artifact_type")
        != "provider_free_sealed_historical_source_acquisition_v0_4_registration"
        or audit.get("authorization_id") != AUTHORIZATION_ID
        or audit.get("authorization_content_sha256")
        != AUTHORIZATION_CONTENT_SHA256
        or audit.get("registered_at_date") != "2026-09-01"
        or audit.get("registration_status")
        != "provider_free_complete_acquisition_not_dispatched"
    ):
        raise ValueError("v0.4 registration identity changed")
    if audit.get("frozen_parents") != {
        "v0_2_success_audit_content_sha256": V02_SUCCESS_AUDIT_CONTENT_SHA256,
        "v0_3_authorization_content_sha256": V03_AUTHORIZATION_CONTENT_SHA256,
        "v0_3_failure_audit_content_sha256": V03_FAILURE_AUDIT_CONTENT_SHA256,
        "v0_3_workflow_run_id": V03_WORKFLOW_RUN_ID,
    }:
        raise ValueError("v0.4 registration parents changed")
    if audit.get("repair") != {
        "candidate_operational_cap": 100,
        "float_target_basis": "exact_qualification_minute",
        "provider_checkpoint_before_scanner_freeze": True,
        "provider_free_freeze_separate_job": True,
        "scanner_gain_and_rank_basis": "split_target_over_split_previous_close",
        "strategy_profiles_changed": False,
        "total_request_ceiling": 40_000,
        "v0_3_partial_source_reused": False,
    }:
        raise ValueError("v0.4 registration repair boundary changed")
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
        raise ValueError("v0.4 registration authority boundary changed")
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
        raise ValueError("v0.4 registration causal attestation changed")

    artifacts = audit.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != set(
        REGISTRATION_ARTIFACT_PATHS
    ):
        raise ValueError("v0.4 registration artifact census changed")
    for label, relative in REGISTRATION_ARTIFACT_PATHS.items():
        entry = artifacts.get(label)
        if not isinstance(entry, Mapping) or set(entry) != {
            "file_sha256",
            "path",
        }:
            raise ValueError(f"v0.4 registration artifact {label} changed")
        if entry.get("path") != relative.as_posix():
            raise ValueError(f"v0.4 registration artifact {label} path changed")
        absolute = ROOT / relative
        if absolute.is_symlink() or not absolute.is_file():
            raise ValueError(
                f"v0.4 registration artifact {label} must be a regular file"
            )
        if entry.get("file_sha256") != _file_sha256(absolute):
            raise ValueError(f"v0.4 registration artifact {label} hash changed")
    return audit


def validate_authorization(payload: Mapping[str, object]) -> None:
    body = dict(payload)
    claimed = body.pop("content_sha256", None)
    if claimed != canonical_fingerprint(body):
        raise ValueError("historical source v0.4 authorization hash mismatch")
    if claimed != AUTHORIZATION_CONTENT_SHA256:
        raise ValueError("historical source v0.4 differs from frozen hash")
    if body != expected_authorization_body():
        raise ValueError("historical source v0.4 authorization changed")


def load_authorization(path: str | Path) -> dict[str, object]:
    payload = _load_json_object(path)
    validate_authorization(payload)
    validate_parent_bundle()
    return payload
