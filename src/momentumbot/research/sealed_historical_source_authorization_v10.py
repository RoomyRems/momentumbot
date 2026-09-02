"""Authorization-only contract for sealed source recovery v0.10."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Mapping

from momentumbot.research.sealed_historical_source_checkpoint_v10 import (
    canonical_fingerprint,
    validate_authorization_envelope_v10,
)


SCHEMA_VERSION = 1
AUTHORIZATION_ID = "sealed-historical-source-acquisition-v0.10"
AUTHORIZATION_CONTENT_SHA256 = (
    "a6519754147c39273a25b2ea818b1906dfa93ea5018edac831e2a0a7052463c7"
)
PARENT_AUTHORIZATION_CONTENT_SHA256 = (
    "447c11b09206b4c19ccade6c1aae70ce5bb17e4a483db6f9581d14ee3f5f862f"
)
PARENT_FAILURE_AUDIT_CONTENT_SHA256 = (
    "2484db2533c09d6abd08151b3538017443ebbc7ed00cbe026bf5dc08e280b7ff"
)
PARENT_REGISTRATION_CONTENT_SHA256 = (
    "d5351a1412034715560cb3a72025f70434590a32d957758906400f02962c0c1c"
)
PARENT_WORKFLOW_FILE_SHA256 = (
    "3e923d1b8ace9e7d9b910a2e743cffd8685251259fcad1694369f520d5509237"
)
PARENT_RUN_ID = 33_577_895_166
PARENT_FAILURE_CHECKPOINT_ZIP_SHA256 = (
    "0db44af6ffe695642444e384378faf3dfb3b6be8e059c0dca7bc0ee77d589244"
)
PARENT_FAILURE_SUMMARY_ZIP_SHA256 = (
    "abfc32a08bc0995b7ee23ebdf8ebd3d2def7f1227273e3ddd8a80ee174718ffe"
)
PARENT_CONSUMPTION_MARKER_ZIP_SHA256 = (
    "45ffd55148274751a71d51f5d43b26d99fd828ad8ed29fa96afc0f70a3ed4049"
)
PARENT_UPSTREAM_PROGRESS_ZIP_SHA256 = (
    "9442dd289f7ae5bf8413159cde1cbc15f913d51b38d959e5e9eed4b7316cc40b"
)

ROOT = Path(__file__).resolve().parents[3]
AUTHORIZATION_PATH = Path(
    "research/strategy/sealed-historical-source-acquisition-v0.10.json"
)
PARENT_AUTHORIZATION_PATH = Path(
    "research/strategy/sealed-historical-source-acquisition-v0.9.json"
)
PARENT_FAILURE_AUDIT_PATH = Path(
    "research/data-audits/"
    "sealed-historical-source-acquisition-v0.9-run-33577895166-failure-2026-09-02.json"
)
PARENT_REGISTRATION_PATH = Path(
    "research/data-audits/"
    "sealed-historical-source-acquisition-v0.9-registration-2026-09-01.json"
)
PARENT_WORKFLOW_PATH = Path(
    ".github/workflows/sealed-historical-source-acquisition-v09.yml"
)
REGISTRATION_AUDIT_PATH = Path(
    "research/data-audits/"
    "sealed-historical-source-acquisition-v0.10-registration-2026-09-02.json"
)
EXPECTED_DISPATCHER_WORKFLOW_REF = (
    "RoomyRems/momentumbot/.github/workflows/"
    "sealed-historical-source-acquisition-v10.yml@refs/heads/main"
)
CONSUMPTION_TAG_PREFIX = (
    "refs/tags/sealed-historical-source-acquisition-v10-consumed-"
)

REGISTRATION_ARTIFACT_PATHS = {
    "acquisition_validator": Path(
        "src/momentumbot/research/sealed_historical_source_acquisition_v10.py"
    ),
    "alpaca_provider": Path("src/momentumbot/providers/alpaca.py"),
    "authorization": AUTHORIZATION_PATH,
    "authorization_validator": Path(
        "src/momentumbot/research/sealed_historical_source_authorization_v10.py"
    ),
    "artifact_metadata_fixture": Path(
        "research/data-audits/"
        "sealed-historical-source-acquisition-v0.10-parent-artifact-metadata-2026-09-02.json"
    ),
    "artifact_metadata_runner": Path(
        "scripts/validate_parent_artifact_metadata_v10.py"
    ),
    "artifact_metadata_validator": Path(
        "src/momentumbot/research/sealed_historical_source_artifact_metadata_v10.py"
    ),
    "authoritative_identity_rule": Path(
        "src/momentumbot/historical_float_identity_v06.py"
    ),
    "checkpoint_builder": Path(
        "scripts/build_sealed_historical_source_checkpoint_v10.py"
    ),
    "checkpoint_validator": Path(
        "src/momentumbot/research/sealed_historical_source_checkpoint_v10.py"
    ),
    "documentation": Path(
        "docs/research/sealed_historical_source_acquisition_v10.md"
    ),
    "downstream_identity_compatibility": Path(
        "src/momentumbot/historical_float_identity_v09.py"
    ),
    "failure_audit": PARENT_FAILURE_AUDIT_PATH,
    "float_policy": Path("src/momentumbot/historical_float_v04.py"),
    "historical_data": Path("src/momentumbot/historical_data_v03.py"),
    "http_transport": Path("src/momentumbot/providers/http_json.py"),
    "identity_loader": Path("src/momentumbot/identity_resolved_universe.py"),
    "market_loader": Path("src/momentumbot/causal_market_discovery_v03.py"),
    "news_policy": Path("src/momentumbot/historical_news.py"),
    "parent_authorization": PARENT_AUTHORIZATION_PATH,
    "parent_registration": PARENT_REGISTRATION_PATH,
    "parent_workflow": PARENT_WORKFLOW_PATH,
    "project_metadata": Path("pyproject.toml"),
    "provider_transport_guard": Path("scripts/run_provider_entrypoint_v04.py"),
    "provider_wrapper": Path("scripts/run_provider_entrypoint_v10.py"),
    "recovery_runner": Path(
        "scripts/validate_sealed_historical_source_recovery_v10.py"
    ),
    "recovery_validator": Path(
        "src/momentumbot/research/sealed_historical_source_recovery_v10.py"
    ),
    "request_budget": Path("src/momentumbot/providers/request_budget.py"),
    "requirements": Path("requirements-sealed-source-v04.txt"),
    "runner": Path("scripts/run_sealed_historical_source_acquisition_v10.py"),
    "rvol_alignment": Path("src/momentumbot/scanner_rvol_alignment_v10.py"),
    "rvol_regression_test": Path("tests/test_scanner_rvol_alignment_v10.py"),
    "scanner_adapter": Path("scripts/build_causal_scanner_snapshot_v10.py"),
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
        ".github/workflows/sealed-historical-source-acquisition-v10.yml"
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
    validated = validate_authorization_envelope_v10(payload)
    if validated.get("content_sha256") != AUTHORIZATION_CONTENT_SHA256:
        raise ValueError("historical source v0.10 differs from frozen hash")
    if (
        validated.get("artifact_type")
        != "preregistered_sealed_historical_source_recovery_v0_10"
        or validated.get("registered_at_date") != "2026-09-02"
    ):
        raise ValueError("v0.10 authorization identity changed")
    if validated.get("dispatcher_contract") != {
        "contents_write_allowed_only_in_consumption_job": True,
        "dispatcher_blob_must_match_authorized_research_workflow": True,
        "provider_credentials_allowed_in_consume_or_freeze_job": False,
        "provider_free_freeze_is_separate_job": True,
        "workflow_ref": EXPECTED_DISPATCHER_WORKFLOW_REF,
    }:
        raise ValueError("v0.10 dispatcher contract changed")
    if validated.get("failed_parent") != {
        "authorization_commit_sha": "92d8b4deceae5c2bb6edfb10016a0e05c33c8bfa",
        "authorization_content_sha256": PARENT_AUTHORIZATION_CONTENT_SHA256,
        "authorization_id": "sealed-historical-source-acquisition-v0.9",
        "authorization_permanently_consumed": True,
        "authorization_tree_sha": "d214d0990665a92ea24760a972232998378fae38",
        "consumption_marker_zip_sha256": PARENT_CONSUMPTION_MARKER_ZIP_SHA256,
        "dispatcher_workflow_sha": "b92a236dc92e8311c70c1b76ab657cea809fbe90",
        "failure_audit_content_sha256": PARENT_FAILURE_AUDIT_CONTENT_SHA256,
        "failure_checkpoint_artifact_id": 9_827_444_933,
        "failure_checkpoint_artifact_name": (
            "sealed-historical-source-acquisition-v09-"
            "failure-checkpoint-33577895166-1"
        ),
        "failure_checkpoint_zip_sha256": PARENT_FAILURE_CHECKPOINT_ZIP_SHA256,
        "failure_summary_zip_sha256": PARENT_FAILURE_SUMMARY_ZIP_SHA256,
        "source_candidate_count": 946,
        "source_file_count": 646,
        "source_float_record_count": 946,
        "source_retained_bytes": 544_738_038,
        "source_tree_content_sha256": (
            "60113df5eb307e3c5f31ab075017c9cca4e1da70c2177de40c26df7bed7a5f9f"
        ),
        "upstream_progress_zip_sha256": PARENT_UPSTREAM_PROGRESS_ZIP_SHA256,
        "workflow_run_attempt": 1,
        "workflow_run_id": PARENT_RUN_ID,
    }:
        raise ValueError("v0.10 failed-parent provenance changed")
    if validated.get("provider_entrypoint_contract") != {
        "all_network_capable_scripts_use_wrapper": True,
        "allowed_entrypoints": ["scripts/build_causal_scanner_snapshot_v10.py"],
        "ambient_proxy_use_allowed": False,
        "child_network_hosts": ["data.alpaca.markets"],
        "direct_socket_or_process_escape_allowed": False,
        "massive_identity_market_sec_float_or_news_entrypoint_allowed": False,
        "redirects_allowed": False,
        "wrapper_path": "scripts/run_provider_entrypoint_v10.py",
    }:
        raise ValueError("v0.10 child provider boundary changed")
    if validated.get("recovery_contract") != {
        "complete_parent_market_float_and_news_source_reused": True,
        "failure_checkpoint_artifact_downloaded_from_exact_parent_run": True,
        "incomplete_parent_scanner_tape_removed_before_recovery": True,
        "normalized_parent_source_reused_exactly_except_partial_scanner_tape": True,
        "parent_identity_or_market_provider_requests_repeated": False,
        "parent_identity_market_float_or_news_provider_requests_repeated": False,
        "parent_source_recovery_receipt_content_sha256": (
            "776470b9616c582b229f9e0118c0a31338639f17c33878676c85997ab3d3d750"
        ),
        "raw_parent_provider_responses_present_or_reused": False,
        "resume_stage": "canonical_split_rank_scanner_source_inputs",
    }:
        raise ValueError("v0.10 recovery boundary changed")
    if validated.get("repair_boundary") != {
        "all_946_candidates_and_float_records_preflighted_before_consumption": True,
        "blrx_177_raw_vs_359_dense_timestamp_case_reproduced": True,
        "candidate_identity_or_float_values_rewritten": False,
        "complete_scanner_source_write_read_round_trip_required": True,
        "downloaded_zip_sha256_matches_frozen_artifact_metadata": True,
        "exact_rvol_fill_or_interpolation_allowed": False,
        "exact_rvol_missing_raw_timestamp_allowed": False,
        "exact_rvol_projected_to_corresponding_raw_bar_index": True,
        "exact_rvol_values_changed": False,
        "field_specific_sanitized_artifact_metadata_diagnostics": True,
        "frozen_real_artifact_metadata_fixture_required": True,
        "parent_artifact_metadata_fetched_once_per_gate": True,
        "partial_parent_scanner_tape_reused": False,
        "raw_provider_response_persisted": False,
        "strategy_float_news_scanner_or_micro_policy_changed": False,
        "transport_http_pagination_budget_authorization_or_artifact_error_remains_fatal": True,
    }:
        raise ValueError("v0.10 RVOL repair boundary changed")
    one_shot = validated.get("one_shot_contract")
    if not isinstance(one_shot, Mapping) or one_shot.get(
        "prior_authorization_reruns_allowed"
    ) != {f"v0.{index}": False for index in range(1, 10)} or one_shot.get(
        "repository_consumption_tag_prefix"
    ) != CONSUMPTION_TAG_PREFIX:
        raise ValueError("v0.10 one-shot boundary changed")
    if validated.get("request_budget") != {
        "allowed_hosts": [
            "api.massive.com",
            "data.alpaca.markets",
            "data.sec.gov",
        ],
        "candidate_operational_ceiling_per_date": 100,
        "child_massive_calls_authorized": 0,
        "child_news_calls_authorized": 0,
        "child_sec_calls_authorized": 0,
        "composite_parent_attempts_by_host": {
            "api.massive.com": 363,
            "data.alpaca.markets": 16_153,
            "data.sec.gov": 1_328,
        },
        "composite_parent_total_attempts": 17_844,
        "maximum_total_http_attempts_including_parent_and_child_retries": 40_000,
        "new_attempts_increment_parent_seed": True,
    }:
        raise ValueError("v0.10 request boundary changed")
    if validated.get("cost_ceiling") != {
        "databento_calls_authorized": 0,
        "incremental_provider_cost_usd": "0",
        "paid_acquisition_authorized": False,
    }:
        raise ValueError("v0.10 cost boundary changed")


def load_authorization(path: str | Path) -> dict[str, object]:
    payload = _load_json_object(path)
    validate_authorization(payload)
    validate_parent_bundle()
    return payload


def validate_parent_bundle() -> dict[str, object]:
    parent_authorization = _load_json_object(ROOT / PARENT_AUTHORIZATION_PATH)
    _validate_self_hash(
        parent_authorization,
        expected=PARENT_AUTHORIZATION_CONTENT_SHA256,
        label="v0.9 authorization",
    )
    if parent_authorization.get("authorization_id") != (
        "sealed-historical-source-acquisition-v0.9"
    ):
        raise ValueError("v0.9 authorization identity changed")

    failure = _load_json_object(ROOT / PARENT_FAILURE_AUDIT_PATH)
    _validate_self_hash(
        failure,
        expected=PARENT_FAILURE_AUDIT_CONTENT_SHA256,
        label="v0.9 failure audit",
    )
    workflow = failure.get("workflow")
    authority = failure.get("frozen_authority")
    causal = failure.get("causal_attestation")
    artifacts = failure.get("preserved_artifacts")
    accounting = failure.get("provider_accounting")
    partial = failure.get("partial_scanner_evidence")
    repair = failure.get("repair_boundary")
    if (
        not isinstance(workflow, Mapping)
        or workflow.get("run_id") != PARENT_RUN_ID
        or workflow.get("attempt") != 1
        or workflow.get("event") != "workflow_dispatch"
        or workflow.get("status") != "failure"
        or not isinstance(authority, Mapping)
        or authority.get("authorization_content_sha256")
        != PARENT_AUTHORIZATION_CONTENT_SHA256
        or authority.get("authorization_permanently_consumed") is not True
        or failure.get("conclusion")
        != "fail_closed_exact_rvol_raw_bar_index_contract_mismatch"
    ):
        raise ValueError("v0.9 failure provenance changed")
    if (
        not isinstance(causal, Mapping)
        or causal.get("transcript_record_values_read") is not False
        or causal.get("ross_labels_or_outcomes_read") is not False
        or causal.get("account_or_order_endpoint_called") is not False
        or not isinstance(accounting, Mapping)
        or accounting.get("observed_total_http_attempts") != 17_844
        or accounting.get("observed_attempts_by_host")
        != {
            "api.massive.com": 363,
            "data.alpaca.markets": 16_153,
            "data.sec.gov": 1_328,
        }
        or accounting.get("blocked_attempts") != 0
        or not isinstance(repair, Mapping)
        or repair.get("v0_9_may_be_rerun") is not False
        or repair.get("fill_or_interpolation_allowed") is not False
        or repair.get("provider_free_sparse_timestamp_round_trip_required")
        is not True
    ):
        raise ValueError("v0.9 failure safety boundary changed")
    if not isinstance(artifacts, Mapping):
        raise ValueError("v0.9 preserved artifacts are missing")
    checkpoint = artifacts.get("failure_checkpoint")
    summary = artifacts.get("sanitized_failure")
    marker = artifacts.get("consumption_marker")
    upstream = artifacts.get("upstream_progress")
    if (
        not isinstance(checkpoint, Mapping)
        or checkpoint.get("zip_sha256") != PARENT_FAILURE_CHECKPOINT_ZIP_SHA256
        or checkpoint.get("source_file_count") != 646
        or checkpoint.get("source_retained_bytes") != 544_738_038
        or not isinstance(summary, Mapping)
        or summary.get("zip_sha256") != PARENT_FAILURE_SUMMARY_ZIP_SHA256
        or not isinstance(marker, Mapping)
        or marker.get("zip_sha256") != PARENT_CONSUMPTION_MARKER_ZIP_SHA256
        or not isinstance(upstream, Mapping)
        or upstream.get("zip_sha256") != PARENT_UPSTREAM_PROGRESS_ZIP_SHA256
        or not isinstance(partial, Mapping)
        or partial.get("first_candidate_raw_timestamp_count") != 177
        or partial.get("candidate_exact_rvol_records") != 0
        or partial.get("manifest_completed") is not False
    ):
        raise ValueError("v0.9 preserved artifact boundary changed")

    parent_registration = _load_json_object(ROOT / PARENT_REGISTRATION_PATH)
    _validate_self_hash(
        parent_registration,
        expected=PARENT_REGISTRATION_CONTENT_SHA256,
        label="v0.9 registration",
    )
    if (
        parent_registration.get("authorization_content_sha256")
        != PARENT_AUTHORIZATION_CONTENT_SHA256
    ):
        raise ValueError("v0.9 registration authority changed")
    parent_workflow = ROOT / PARENT_WORKFLOW_PATH
    if (
        parent_workflow.is_symlink()
        or not parent_workflow.is_file()
        or _file_sha256(parent_workflow) != PARENT_WORKFLOW_FILE_SHA256
    ):
        raise ValueError("v0.9 workflow file changed")
    return {
        "v0_9_authorization": parent_authorization,
        "v0_9_failure_audit": failure,
        "v0_9_registration": parent_registration,
    }


def validate_registration_bundle() -> dict[str, object]:
    path = ROOT / REGISTRATION_AUDIT_PATH
    if path.is_symlink() or not path.is_file():
        raise ValueError("v0.10 registration audit must be a regular file")
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
        raise ValueError("v0.10 registration audit fields changed")
    _validate_self_hash(
        audit,
        expected=str(audit.get("content_sha256")),
        label="v0.10 registration audit",
    )
    if (
        audit.get("schema_version") != 1
        or audit.get("artifact_type")
        != "provider_free_sealed_historical_source_recovery_v0_10_registration"
        or audit.get("authorization_id") != AUTHORIZATION_ID
        or audit.get("authorization_content_sha256")
        != AUTHORIZATION_CONTENT_SHA256
        or audit.get("registered_at_date") != "2026-09-02"
        or audit.get("registration_status")
        != "provider_free_complete_recovery_not_dispatched"
    ):
        raise ValueError("v0.10 registration identity changed")
    if audit.get("frozen_parent") != {
        "authorization_content_sha256": PARENT_AUTHORIZATION_CONTENT_SHA256,
        "failure_audit_content_sha256": PARENT_FAILURE_AUDIT_CONTENT_SHA256,
        "failure_checkpoint_zip_sha256": PARENT_FAILURE_CHECKPOINT_ZIP_SHA256,
        "workflow_run_id": PARENT_RUN_ID,
    }:
        raise ValueError("v0.10 registration parent changed")
    if audit.get("repair") != {
        "blrx_sparse_timestamp_regression_passed": True,
        "child_network_hosts": ["data.alpaca.markets"],
        "complete_market_float_and_news_source_reused": True,
        "composite_parent_request_seed": 17_844,
        "exact_rvol_fill_interpolation_or_value_change": False,
        "exact_rvol_projected_to_raw_bar_index": True,
        "external_provider_ledgers_cross_bound": True,
        "massive_identity_market_sec_float_or_news_requests_repeated": False,
        "missing_raw_timestamp_fails_closed": True,
        "parent_artifact_replayed_before_consumption": True,
        "partial_parent_scanner_tape_reused": False,
        "provider_checkpoint_before_scanner_freeze": True,
        "provider_free_freeze_separate_job": True,
        "scanner_source_round_trip_passed": True,
        "strategy_profiles_or_thresholds_changed": False,
        "third_party_environment_exact_with_commit_specific_editable_line": True,
        "total_request_ceiling": 40_000,
    }:
        raise ValueError("v0.10 registration repair boundary changed")
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
        raise ValueError("v0.10 registration authority boundary changed")
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
        raise ValueError("v0.10 registration causal attestation changed")
    artifacts = audit.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != set(
        REGISTRATION_ARTIFACT_PATHS
    ):
        raise ValueError("v0.10 registration artifact census changed")
    for label, relative in REGISTRATION_ARTIFACT_PATHS.items():
        entry = artifacts.get(label)
        if (
            not isinstance(entry, Mapping)
            or set(entry) != {"file_sha256", "path"}
            or entry.get("path") != relative.as_posix()
        ):
            raise ValueError(f"v0.10 registration artifact {label} changed")
        absolute = ROOT / relative
        if absolute.is_symlink() or not absolute.is_file():
            raise ValueError(f"v0.10 registration artifact {label} is not regular")
        if entry.get("file_sha256") != _file_sha256(absolute):
            raise ValueError(f"v0.10 registration artifact {label} hash changed")
    return audit


__all__ = [
    "AUTHORIZATION_CONTENT_SHA256",
    "AUTHORIZATION_ID",
    "AUTHORIZATION_PATH",
    "CONSUMPTION_TAG_PREFIX",
    "EXPECTED_DISPATCHER_WORKFLOW_REF",
    "REGISTRATION_ARTIFACT_PATHS",
    "REGISTRATION_AUDIT_PATH",
    "expected_authorization_body",
    "load_authorization",
    "validate_authorization",
    "validate_parent_bundle",
    "validate_registration_bundle",
]
