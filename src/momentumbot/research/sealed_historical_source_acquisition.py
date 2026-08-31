"""Bounded source acquisition for the sealed 30-session historical panel."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Mapping

from momentumbot.causal_market_discovery import (
    CAUSAL_MARKET_DISCOVERY_POLICY_ID,
)
from momentumbot.causal_scanner_snapshot import (
    CAUSAL_SCANNER_SNAPSHOT_ARTIFACT_ID,
)
from momentumbot.historical_float import CAUSAL_FLOAT_POLICY_ID
from momentumbot.historical_news import CAUSAL_NEWS_POLICY_ID
from momentumbot.identity_resolved_universe import (
    IDENTITY_RESOLVED_UNIVERSE_POLICY_ID,
)
from momentumbot.scanner_source_inputs import (
    ARTIFACT_ID as SCANNER_SOURCE_INPUT_ARTIFACT_ID,
    validate_scanner_source_input_manifest,
)

from .sealed_historical_availability import SELECTED_DATES, freeze
from .sealed_historical_walk_forward import (
    CONTRACT_CONTENT_SHA256,
    CONTRACT_ID,
    canonical_fingerprint,
    load_json_object,
)


SCHEMA_VERSION = 1
AUTHORIZATION_ID = "sealed-historical-source-acquisition-v0.1"
AUTHORIZATION_CONTENT_SHA256 = (
    "0dbc26228513bb81f55c484daa56e899feabdc38f419c2ccd758c9d2853eb4d7"
)
AVAILABILITY_REPORT_CONTENT_SHA256 = (
    "bc88728486e77ca718e77918fa83470b7a608502e34aedaa8ccb184fef03819c"
)
AVAILABILITY_SUCCESS_AUDIT_CONTENT_SHA256 = (
    "76baebc0df39c59e9a1a8ebc099c5c0c3080d1a4e4cb2ac013cb85f7f9070cb1"
)
AVAILABILITY_WORKFLOW_RUN_ID = "33348970745"
MAX_HTTP_ATTEMPTS = 20_000
MAX_CENSUS_PAGES_PER_DATE = 20
MAX_CANDIDATES_PER_DATE = 50
MAX_RETAINED_BYTES = 1_500_000_000
ALLOWED_REQUEST_HOSTS = (
    "api.massive.com",
    "data.alpaca.markets",
    "data.sec.gov",
)
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def expected_authorization_body() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "preregistered_bounded_sealed_historical_source_acquisition",
        "authorization_id": AUTHORIZATION_ID,
        "registered_at_date": "2026-08-31",
        "frozen_parent": {
            "contract_id": CONTRACT_ID,
            "contract_content_sha256": CONTRACT_CONTENT_SHA256,
            "availability_report_content_sha256": (
                AVAILABILITY_REPORT_CONTENT_SHA256
            ),
            "availability_success_audit_content_sha256": (
                AVAILABILITY_SUCCESS_AUDIT_CONTENT_SHA256
            ),
            "availability_workflow_run_id": AVAILABILITY_WORKFLOW_RUN_ID,
            "selected_dates": list(SELECTED_DATES),
        },
        "credential_routing": {
            "github_actions_secret_names": [
                "MASSIVE_API_KEY",
                "ALPACA_MAIN_API_KEY",
                "ALPACA_MAIN_API_SECRET",
                "SEC_USER_AGENT",
            ],
            "runtime_environment_aliases": {
                "MASSIVE_API_KEY": "MASSIVE_API_KEY",
                "ALPACA_API_KEY": "ALPACA_MAIN_API_KEY",
                "ALPACA_API_SECRET": "ALPACA_MAIN_API_SECRET",
                "SEC_USER_AGENT": "SEC_USER_AGENT",
            },
            "credential_values_changed_observed_or_persisted": False,
        },
        "request_budget": {
            "maximum_total_http_attempts_including_retries": MAX_HTTP_ATTEMPTS,
            "shared_cross_process_counter_required": True,
            "counter_persists_counts_by_hostname_only": True,
            "allowed_hosts": list(ALLOWED_REQUEST_HOSTS),
            "massive": {
                "ticker_type_calls": 1,
                "census_limit_per_page": 1000,
                "maximum_census_pages_per_date": MAX_CENSUS_PAGES_PER_DATE,
                "minimum_request_interval_seconds": "12.5",
                "split_maximum_pages_per_request": 20,
                "ticker_event_sample_calls": 0,
            },
            "alpaca": {
                "feed": "sip",
                "bars_maximum_pages_per_logical_request": 100,
                "corporate_action_maximum_pages_per_request": 100,
                "asset_or_account_endpoint_calls": 0,
                "daily_and_rank_batch_size": 250,
                "minute_batch_size_maximum": 100,
            },
            "sec": {
                "maximum_candidates_per_date": MAX_CANDIDATES_PER_DATE,
                "maximum_attempts_per_endpoint": 3,
                "minimum_request_interval_seconds": "0.2",
                "endpoints_per_unique_candidate_cik": 2,
            },
            "news": {
                "maximum_candidates_per_date": MAX_CANDIDATES_PER_DATE,
                "symbol_batch_size": 50,
                "maximum_pages_per_batch": 10,
                "include_content": False,
            },
        },
        "retention_budget": {
            "maximum_retained_bytes": MAX_RETAINED_BYTES,
            "raw_provider_http_responses_persisted": False,
            "canonical_scanner_runtime_inputs_persisted_gzip": True,
            "upstream_normalized_membership_market_float_news_persisted": True,
            "artifact_retention_days": 90,
        },
        "one_shot_contract": {
            "workflow_run_attempt_required": 1,
            "authorization_consumed_before_provider_access": True,
            "automatic_rerun_allowed": False,
            "provider_substitution_allowed": False,
        },
        "cost_ceiling": {
            "incremental_provider_cost_usd": "0",
            "databento_calls_authorized": 0,
            "paid_acquisition_authorized": False,
        },
        "causal_boundary": {
            "transcript_record_values_may_be_read": False,
            "ross_actions_fills_skips_or_outcomes_may_be_read": False,
            "strategy_threshold_or_setup_changes_allowed": False,
            "present_day_alpaca_asset_master_reconciliation_allowed": False,
            "later_price_or_final_volume_used_at_decision_time": False,
        },
        "authority_boundary": {
            "historical_source_acquisition_authorized": True,
            "candidate_bound_databento_acquisition_authorized": False,
            "historical_account_runtime_authorized": False,
            "paper_order_authorized": False,
            "live_order_authorized": False,
            "policy_promotion_eligible": False,
        },
    }


def load_authorization(path: str | Path) -> dict[str, object]:
    payload = load_json_object(path)
    validate_authorization(payload)
    return payload


def validate_authorization(payload: Mapping[str, object]) -> None:
    body = dict(payload)
    claimed = body.pop("content_sha256", None)
    if claimed != canonical_fingerprint(body):
        raise ValueError("historical source authorization content hash mismatch")
    if claimed != AUTHORIZATION_CONTENT_SHA256:
        raise ValueError("historical source authorization differs from frozen hash")
    if body != expected_authorization_body():
        raise ValueError("historical source authorization contract changed")


def _assert_frozen(payload: Mapping[str, object], expected: str, label: str) -> None:
    body = dict(payload)
    claimed = body.pop("content_sha256", None)
    if claimed != canonical_fingerprint(body) or claimed != expected:
        raise ValueError(f"{label} content hash mismatch")


def validate_parent_bundle(
    *,
    contract: Mapping[str, object],
    availability_report: Mapping[str, object],
    availability_success_audit: Mapping[str, object],
) -> None:
    _assert_frozen(contract, CONTRACT_CONTENT_SHA256, "historical panel contract")
    sampling = contract.get("sampling_contract")
    if (
        contract.get("contract_id") != CONTRACT_ID
        or not isinstance(sampling, Mapping)
        or sampling.get("selected_dates") != list(SELECTED_DATES)
    ):
        raise ValueError("historical panel parent changed")
    _assert_frozen(
        availability_report,
        AVAILABILITY_REPORT_CONTENT_SHA256,
        "availability report",
    )
    if (
        availability_report.get("availability_gate_passed") is not True
        or availability_report.get("selected_dates") != list(SELECTED_DATES)
        or availability_report.get("current_attempt_call_counts")
        != {"alpaca": 1, "total": 1}
    ):
        raise ValueError("availability report did not pass the exact parent gate")
    _assert_frozen(
        availability_success_audit,
        AVAILABILITY_SUCCESS_AUDIT_CONTENT_SHA256,
        "availability success audit",
    )
    workflow = availability_success_audit.get("workflow")
    result = availability_success_audit.get("result")
    if (
        not isinstance(workflow, Mapping)
        or str(workflow.get("run_id")) != AVAILABILITY_WORKFLOW_RUN_ID
        or not isinstance(result, Mapping)
        or result.get("availability_gate_passed") is not True
    ):
        raise ValueError("availability success audit did not bind the passed run")


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
        raise ValueError("historical source acquisition is one attempt only")
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
    required_gates = {
        "census_complete": True,
        "identity_complete": True,
        "market_discovery_complete": True,
        "float_complete": True,
        "news_complete": True,
        "scanner_snapshot_complete": True,
        "canonical_scanner_inputs_complete": True,
        "present_day_asset_master_skipped": True,
    }
    if source_summary.get("gates") != required_gates:
        raise ValueError("historical source bundle is incomplete")
    total = request_budget.get("total_attempts")
    by_host = request_budget.get("by_host")
    if not isinstance(total, int) or not 0 < total <= MAX_HTTP_ATTEMPTS:
        raise ValueError("historical source HTTP attempt budget is invalid")
    if (
        not isinstance(by_host, Mapping)
        or not by_host
        or not set(by_host).issubset(ALLOWED_REQUEST_HOSTS)
        or sum(int(value) for value in by_host.values()) != total
    ):
        raise ValueError("historical source request hosts are invalid")
    if not 0 < retained_bytes <= MAX_RETAINED_BYTES:
        raise ValueError("historical source retained-byte ceiling exceeded")
    report = freeze(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "sealed_historical_source_acquisition_result",
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
        raise ValueError("historical source report content hash mismatch")
    if report.get("authorization_content_sha256") != authorization.get(
        "content_sha256"
    ):
        raise ValueError("historical source report authorization mismatch")
    if report.get("source_acquisition_gate_passed") is not True:
        raise ValueError("historical source report did not pass")
    causal = report.get("causal_attestation")
    expected_causal = {
        "transcript_record_values_read": False,
        "ross_labels_or_outcomes_read": False,
        "account_or_order_endpoint_called": False,
        "order_submitted": False,
        "credential_values_persisted": False,
        "present_day_alpaca_asset_master_called": False,
    }
    if causal != expected_causal:
        raise ValueError("historical source causal boundary changed")
    cost = report.get("cost")
    if cost != {"incremental_provider_cost_usd": "0", "databento_called": False}:
        raise ValueError("historical source cost boundary changed")


def summarize_source_root(root: str | Path) -> dict[str, object]:
    source_root = Path(root)

    def manifest(relative: str) -> dict[str, object]:
        return load_json_object(source_root / relative / "manifest.json")

    census = load_json_object(source_root / "manifest.json")
    identity = manifest(IDENTITY_RESOLVED_UNIVERSE_POLICY_ID)
    market = manifest(CAUSAL_MARKET_DISCOVERY_POLICY_ID)
    floats = manifest(CAUSAL_FLOAT_POLICY_ID)
    news = manifest(CAUSAL_NEWS_POLICY_ID)
    scanner = manifest(CAUSAL_SCANNER_SNAPSHOT_ARTIFACT_ID)
    source_inputs = manifest(SCANNER_SOURCE_INPUT_ARTIFACT_ID)
    manifests = {
        "census": census,
        "identity": identity,
        "market": market,
        "float": floats,
        "news": news,
        "scanner": scanner,
        "source_inputs": source_inputs,
    }
    for name, payload in manifests.items():
        if payload.get("dates") != list(SELECTED_DATES):
            raise ValueError(f"historical source {name} dates changed")
    date_source_manifests = source_inputs.get("date_manifests")
    if not isinstance(date_source_manifests, list) or len(date_source_manifests) != len(
        SELECTED_DATES
    ):
        raise ValueError("canonical scanner source-input manifests are incomplete")
    for row in date_source_manifests:
        if not isinstance(row, Mapping):
            raise ValueError("canonical scanner source-input manifest is invalid")
        validate_scanner_source_input_manifest(row)
    census_dates = census.get("date_manifests")
    market_dates = market.get("date_manifests")
    if not isinstance(census_dates, list) or not isinstance(market_dates, list):
        raise ValueError("historical source date manifests are missing")
    page_counts = {
        str(row["requested_asof_date"]): int(row["page_count"])
        for row in census_dates
        if isinstance(row, Mapping)
    }
    row_counts = {
        str(row["requested_asof_date"]): int(row["census_summary"]["row_count"])
        for row in census_dates
        if isinstance(row, Mapping)
    }
    candidate_counts = {
        str(row["trading_date"]): int(row["summary"]["causal_market_candidate_count"])
        for row in market_dates
        if isinstance(row, Mapping)
    }
    compressed_bytes = {
        str(row["trading_date"]): int(row["summary"]["compressed_size_bytes"])
        for row in date_source_manifests
    }
    source_hashes = {
        name: str(payload.get("content_sha256"))
        for name, payload in manifests.items()
        if name != "census"
    }
    # The census manifest predates root hashing; bind it by exact file bytes.
    source_hashes["census_file"] = hashlib.sha256(
        (source_root / "manifest.json").read_bytes()
    ).hexdigest()
    return {
        "dates": list(SELECTED_DATES),
        "census_page_counts": page_counts,
        "census_row_counts": row_counts,
        "candidate_counts": candidate_counts,
        "canonical_source_input_compressed_bytes": compressed_bytes,
        "source_hashes": dict(sorted(source_hashes.items())),
        "gates": {
            "census_complete": census.get("all_fetches_complete") is True,
            "identity_complete": identity.get("eligibility", {}).get(
                "complete_relative_to_provisional_membership"
            )
            is True,
            "market_discovery_complete": market.get("eligibility", {}).get(
                "causal_market_discovery_complete"
            )
            is True,
            "float_complete": floats.get("eligibility", {}).get(
                "point_in_time_float_decisions_frozen"
            )
            is True,
            "news_complete": news.get("eligibility", {}).get(
                "publication_timed_news_frozen"
            )
            is True,
            "scanner_snapshot_complete": scanner.get("eligibility", {}).get(
                "candidate_minute_dispositions_frozen"
            )
            is True,
            "canonical_scanner_inputs_complete": source_inputs.get(
                "replay_boundary", {}
            ).get("canonical_runtime_inputs_persisted")
            is True,
            "present_day_asset_master_skipped": census.get(
                "current_alpaca_reconciliation_skipped"
            )
            is True,
        },
    }


def retained_tree_bytes(root: str | Path) -> int:
    return sum(path.stat().st_size for path in Path(root).rglob("*") if path.is_file())


def write_json_once(path: str | Path, payload: Mapping[str, object]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
