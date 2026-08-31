"""One-shot request-budget repair for sealed historical source acquisition."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Mapping

from momentumbot.identity_resolved_universe import json_fingerprint
from momentumbot.research.sealed_historical_availability import SELECTED_DATES, freeze
from momentumbot.research.sealed_historical_source_acquisition import (
    ALLOWED_REQUEST_HOSTS,
    AUTHORIZATION_CONTENT_SHA256 as V01_AUTHORIZATION_CONTENT_SHA256,
    MAX_CANDIDATES_PER_DATE,
    MAX_CENSUS_PAGES_PER_DATE,
    MAX_RETAINED_BYTES,
    expected_authorization_body as expected_v01_authorization_body,
    validate_authorization as validate_v01_authorization,
    validate_parent_bundle as validate_v01_parent_bundle,
)
from momentumbot.research.sealed_historical_walk_forward import (
    canonical_fingerprint,
    load_json_object,
)


SCHEMA_VERSION = 1
AUTHORIZATION_ID = "sealed-historical-source-acquisition-v0.2"
AUTHORIZATION_CONTENT_SHA256 = (
    "be574f7e79c13eaf5c0235a02fd5d157738f4d7dd9431dd7b932c1cf20fcf315"
)
V01_FAILURE_AUDIT_CONTENT_SHA256 = (
    "934d1ca46ceb87192f3c2846894ada202554ffd4bbe07a6a2fe7fccaf246f292"
)
V01_FAILURE_REPORT_FILE_SHA256 = (
    "17c5dbe3f67af68bbc261dd718a04516a7f3f93c99dbeaf4d888f0452288a4cd"
)
V01_WORKFLOW_RUN_ID = "33350635957"
MAX_HTTP_ATTEMPTS = 40_000
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def expected_authorization_body() -> dict[str, object]:
    body = deepcopy(expected_v01_authorization_body())
    body["artifact_type"] = (
        "preregistered_bounded_sealed_historical_source_acquisition_repair"
    )
    body["authorization_id"] = AUTHORIZATION_ID
    body["registered_at_date"] = "2026-08-31"
    frozen_parent = body["frozen_parent"]
    assert isinstance(frozen_parent, dict)
    frozen_parent.update(
        {
            "v0_1_authorization_content_sha256": V01_AUTHORIZATION_CONTENT_SHA256,
            "v0_1_failure_audit_content_sha256": (
                V01_FAILURE_AUDIT_CONTENT_SHA256
            ),
            "v0_1_failure_artifact_file_sha256": (
                V01_FAILURE_REPORT_FILE_SHA256
            ),
            "v0_1_workflow_run_id": V01_WORKFLOW_RUN_ID,
        }
    )
    request_budget = body["request_budget"]
    assert isinstance(request_budget, dict)
    request_budget["maximum_total_http_attempts_including_retries"] = (
        MAX_HTTP_ATTEMPTS
    )
    one_shot = body["one_shot_contract"]
    assert isinstance(one_shot, dict)
    one_shot["v0_1_authorization_may_be_rerun"] = False
    body["repair_boundary"] = {
        "acquisition_code_or_parameters_changed": False,
        "dates_or_provider_routes_changed": False,
        "request_ceiling_only_change": True,
        "strategy_or_account_policy_changed": False,
        "v0_1_partial_tree_reused": False,
    }
    return body


def load_authorization(path: str) -> dict[str, object]:
    payload = load_json_object(path)
    validate_authorization(payload)
    return payload


def validate_authorization(payload: Mapping[str, object]) -> None:
    body = dict(payload)
    claimed = body.pop("content_sha256", None)
    if claimed != canonical_fingerprint(body):
        raise ValueError("historical source v0.2 authorization hash mismatch")
    if claimed != AUTHORIZATION_CONTENT_SHA256:
        raise ValueError("historical source v0.2 differs from frozen hash")
    if body != expected_authorization_body():
        raise ValueError("historical source v0.2 authorization changed")


def validate_v01_failure_parent(
    *,
    v01_authorization: Mapping[str, object],
    failure_report: Mapping[str, object],
    failure_audit: Mapping[str, object],
) -> None:
    validate_v01_authorization(v01_authorization)
    audit_body = dict(failure_audit)
    claimed = audit_body.pop("content_sha256", None)
    if claimed != canonical_fingerprint(audit_body):
        raise ValueError("historical source v0.1 failure audit hash mismatch")
    if claimed != V01_FAILURE_AUDIT_CONTENT_SHA256:
        raise ValueError("historical source v0.1 failure audit changed")
    if failure_audit.get("authorization") != {
        "authorization_content_sha256": V01_AUTHORIZATION_CONTENT_SHA256,
        "authorization_id": "sealed-historical-source-acquisition-v0.1",
    }:
        raise ValueError("historical source v0.1 failure parent is invalid")
    workflow = failure_audit.get("workflow")
    accounting = failure_audit.get("request_accounting")
    if (
        not isinstance(workflow, Mapping)
        or str(workflow.get("run_id")) != V01_WORKFLOW_RUN_ID
        or workflow.get("run_attempt") != 1
        or workflow.get("conclusion") != "failure"
        or accounting
        != {
            "alpaca_attempts": 18_659,
            "massive_attempts": 363,
            "maximum_authorized_attempts": 20_000,
            "sec_attempts": 978,
            "total_attempts": 20_000,
        }
    ):
        raise ValueError("historical source v0.1 failure accounting changed")
    expected_report = {
        "artifact_type": "sealed_historical_source_acquisition_safe_failure",
        "automatic_rerun_allowed": False,
        "order_submitted": False,
        "partial_retained_bytes": 613_915_592,
        "raw_provider_http_responses_persisted": False,
        "request_budget": {
            "by_host": {
                "api.massive.com": 363,
                "data.alpaca.markets": 18_659,
                "data.sec.gov": 978,
            },
            "schema_version": 1,
            "total_attempts": 20_000,
        },
        "schema_version": 1,
        "transcript_record_values_read": False,
        "workflow_run_attempt": 1,
        "workflow_run_id": V01_WORKFLOW_RUN_ID,
    }
    if dict(failure_report) != expected_report:
        raise ValueError("historical source v0.1 failure report changed")
    if json_fingerprint(failure_report) != json_fingerprint(expected_report):
        raise ValueError("historical source v0.1 failure report is invalid")


def validate_parent_bundle(
    *,
    contract: Mapping[str, object],
    availability_report: Mapping[str, object],
    availability_success_audit: Mapping[str, object],
    v01_authorization: Mapping[str, object],
    failure_report: Mapping[str, object],
    failure_audit: Mapping[str, object],
) -> None:
    validate_v01_parent_bundle(
        contract=contract,
        availability_report=availability_report,
        availability_success_audit=availability_success_audit,
    )
    validate_v01_failure_parent(
        v01_authorization=v01_authorization,
        failure_report=failure_report,
        failure_audit=failure_audit,
    )


def build_acquisition_report(
    *,
    authorization: Mapping[str, object],
    source_summary: Mapping[str, object],
    request_budget: Mapping[str, object],
    retained_bytes: int,
    repository: str,
    authorization_commit_sha: str,
    workflow_run_id: str,
    workflow_run_attempt: int,
) -> dict[str, object]:
    validate_authorization(authorization)
    if repository != "RoomyRems/momentumbot":
        raise ValueError("historical source repository mismatch")
    if _GIT_SHA.fullmatch(authorization_commit_sha) is None:
        raise ValueError("historical source commit must be a full Git SHA")
    if workflow_run_attempt != 1:
        raise ValueError("historical source v0.2 is one attempt only")
    dates = source_summary.get("dates")
    page_counts = source_summary.get("census_page_counts")
    candidate_counts = source_summary.get("candidate_counts")
    source_hashes = source_summary.get("source_hashes")
    if dates != list(SELECTED_DATES):
        raise ValueError("historical source dates changed")
    if not isinstance(page_counts, Mapping) or set(page_counts) != set(SELECTED_DATES):
        raise ValueError("historical source census page counts are incomplete")
    if any(
        not isinstance(value, int) or not 0 < value <= MAX_CENSUS_PAGES_PER_DATE
        for value in page_counts.values()
    ):
        raise ValueError("historical source census page ceiling exceeded")
    if not isinstance(candidate_counts, Mapping) or set(candidate_counts) != set(
        SELECTED_DATES
    ):
        raise ValueError("historical source candidate counts are incomplete")
    if any(
        not isinstance(value, int) or not 0 <= value <= MAX_CANDIDATES_PER_DATE
        for value in candidate_counts.values()
    ):
        raise ValueError("historical source candidate ceiling exceeded")
    if not isinstance(source_hashes, Mapping) or not source_hashes:
        raise ValueError("historical source root hashes are missing")
    if any(_SHA256.fullmatch(str(value)) is None for value in source_hashes.values()):
        raise ValueError("historical source root hash is invalid")
    if source_summary.get("gates") != {
        "census_complete": True,
        "identity_complete": True,
        "market_discovery_complete": True,
        "float_complete": True,
        "news_complete": True,
        "scanner_snapshot_complete": True,
        "canonical_scanner_inputs_complete": True,
        "present_day_asset_master_skipped": True,
    }:
        raise ValueError("historical source bundle is incomplete")
    total = request_budget.get("total_attempts")
    by_host = request_budget.get("by_host")
    if not isinstance(total, int) or not 0 < total <= MAX_HTTP_ATTEMPTS:
        raise ValueError("historical source HTTP attempt budget is invalid")
    if (
        not isinstance(by_host, Mapping)
        or not by_host
        or not set(by_host).issubset(ALLOWED_REQUEST_HOSTS)
        or any(not isinstance(value, int) or value < 0 for value in by_host.values())
        or sum(by_host.values()) != total
    ):
        raise ValueError("historical source request hosts are invalid")
    if not 0 < retained_bytes <= MAX_RETAINED_BYTES:
        raise ValueError("historical source retained-byte ceiling exceeded")
    report = freeze(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "sealed_historical_source_acquisition_v0_2_result",
            "authorization_id": AUTHORIZATION_ID,
            "authorization_content_sha256": authorization["content_sha256"],
            "selected_dates": list(SELECTED_DATES),
            "source_summary": dict(source_summary),
            "request_budget": {
                "maximum_total_http_attempts": MAX_HTTP_ATTEMPTS,
                "observed_total_http_attempts": total,
                "observed_attempts_by_host": dict(sorted(by_host.items())),
            },
            "retention": {
                "maximum_retained_bytes": MAX_RETAINED_BYTES,
                "observed_retained_bytes": retained_bytes,
                "raw_provider_http_responses_persisted": False,
                "canonical_scanner_runtime_inputs_persisted_gzip": True,
            },
            "workflow_provenance": {
                "repository": repository,
                "authorization_commit_sha": authorization_commit_sha,
                "workflow_run_id": str(workflow_run_id),
                "workflow_run_attempt": workflow_run_attempt,
                "v0_1_workflow_run_rerun": False,
            },
            "cost": {
                "incremental_provider_cost_usd": "0",
                "databento_called": False,
            },
            "causal_attestation": {
                "transcript_record_values_read": False,
                "ross_labels_or_outcomes_read": False,
                "account_or_order_endpoint_called": False,
                "order_submitted": False,
                "credential_values_persisted": False,
                "present_day_alpaca_asset_master_called": False,
                "strategy_or_account_policy_changed": False,
            },
            "source_acquisition_gate_passed": True,
            "next_gate": (
                "freeze label-blind scanner and Micro decisions, then register "
                "candidate-bound execution-data quote"
            ),
        }
    )
    validate_acquisition_report(report, authorization)
    return report


def validate_acquisition_report(
    report: Mapping[str, object], authorization: Mapping[str, object]
) -> None:
    validate_authorization(authorization)
    body = dict(report)
    claimed = body.pop("content_sha256", None)
    if claimed != canonical_fingerprint(body):
        raise ValueError("historical source v0.2 report hash mismatch")
    if report.get("authorization_content_sha256") != authorization.get(
        "content_sha256"
    ):
        raise ValueError("historical source v0.2 report authorization mismatch")
    if report.get("source_acquisition_gate_passed") is not True:
        raise ValueError("historical source v0.2 report did not pass")
    if report.get("cost") != {
        "incremental_provider_cost_usd": "0",
        "databento_called": False,
    }:
        raise ValueError("historical source v0.2 cost boundary changed")
    causal = report.get("causal_attestation")
    if causal != {
        "transcript_record_values_read": False,
        "ross_labels_or_outcomes_read": False,
        "account_or_order_endpoint_called": False,
        "order_submitted": False,
        "credential_values_persisted": False,
        "present_day_alpaca_asset_master_called": False,
        "strategy_or_account_policy_changed": False,
    }:
        raise ValueError("historical source v0.2 causal boundary changed")
