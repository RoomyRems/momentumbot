"""Normalization-only child for the sealed historical source acquisition."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import re
from typing import Mapping

from momentumbot.causal_market_discovery_v03 import (
    CAUSAL_MARKET_DISCOVERY_V0_3_POLICY_ID,
    causal_market_discovery_v0_3_manifest,
)
from momentumbot.causal_scanner_snapshot_v02 import (
    CAUSAL_SCANNER_SNAPSHOT_V0_2_ARTIFACT_ID,
    causal_scanner_snapshot_v0_2_manifest,
)
from momentumbot.historical_float_v03 import CAUSAL_FLOAT_POLICY_ID
from momentumbot.historical_news import CAUSAL_NEWS_POLICY_ID
from momentumbot.identity_resolved_universe import IDENTITY_RESOLVED_UNIVERSE_POLICY_ID
from momentumbot.scanner_source_inputs_v02 import (
    ARTIFACT_ID as SCANNER_SOURCE_INPUT_ARTIFACT_ID,
    validate_scanner_source_input_manifest,
)
from momentumbot.research.sealed_historical_availability import SELECTED_DATES, freeze
from momentumbot.research.sealed_historical_source_acquisition import (
    ALLOWED_REQUEST_HOSTS,
    MAX_CANDIDATES_PER_DATE,
    MAX_CENSUS_PAGES_PER_DATE,
    MAX_RETAINED_BYTES,
)
from momentumbot.research.sealed_historical_source_acquisition_v02 import (
    AUTHORIZATION_CONTENT_SHA256 as V02_AUTHORIZATION_CONTENT_SHA256,
    MAX_HTTP_ATTEMPTS,
    expected_authorization_body as expected_v02_authorization_body,
    validate_authorization as validate_v02_authorization,
)
from momentumbot.research.sealed_historical_walk_forward import (
    canonical_fingerprint,
    load_json_object,
)


SCHEMA_VERSION = 1
AUTHORIZATION_ID = "sealed-historical-source-acquisition-v0.3"
AUTHORIZATION_CONTENT_SHA256 = (
    "77a37b207dc9ef15b5cbbef32911285c11926c95a53821635458b54b8ae3bffb"
)
V02_SUCCESS_AUDIT_CONTENT_SHA256 = (
    "5be0fef73e639a6cbe9d40b0ec6b38ca22aefb007175790a7bc45248eeac583c"
)
SCANNER_FAILURE_AUDIT_CONTENT_SHA256 = (
    "216a991edb77fadc70d83f4c9d944080fb8b6bdc477ad55085313c62ec992fd6"
)
V02_WORKFLOW_RUN_ID = "33389380992"
V02_ARTIFACT_ZIP_SHA256 = (
    "4d2b7528c846b428acee3024dbc727646b60756f0b811afcdfce1398dbdc5254"
)
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def expected_authorization_body() -> dict[str, object]:
    body = deepcopy(expected_v02_authorization_body())
    body["artifact_type"] = (
        "preregistered_split_consistent_sealed_historical_source_acquisition_repair"
    )
    body["authorization_id"] = AUTHORIZATION_ID
    parent = body["frozen_parent"]
    assert isinstance(parent, dict)
    parent.update(
        {
            "v0_2_authorization_content_sha256": V02_AUTHORIZATION_CONTENT_SHA256,
            "v0_2_success_audit_content_sha256": V02_SUCCESS_AUDIT_CONTENT_SHA256,
            "v0_2_workflow_run_id": V02_WORKFLOW_RUN_ID,
            "v0_2_artifact_zip_sha256": V02_ARTIFACT_ZIP_SHA256,
            "scanner_v0_1_failure_audit_content_sha256": (
                SCANNER_FAILURE_AUDIT_CONTENT_SHA256
            ),
        }
    )
    one_shot = body["one_shot_contract"]
    assert isinstance(one_shot, dict)
    one_shot["v0_2_authorization_may_be_rerun"] = False
    body["repair_boundary"] = {
        "dates_or_provider_routes_changed": False,
        "request_or_retention_ceiling_changed": False,
        "candidate_discovery_and_rank_rebuilt": True,
        "source_v0_2_tree_reused_or_mutated": False,
        "strategy_micro_or_account_policy_changed": False,
        "normalization_only_change": True,
    }
    body["normalization_contract"] = {
        "market_discovery_policy": causal_market_discovery_v0_3_manifest(),
        "scanner_policy": causal_scanner_snapshot_v0_2_manifest(),
        "actual_price_and_volume_adjustment": "raw",
        "percent_gain_previous_close_adjustment": "split",
        "percent_gain_target_minute_adjustment": "split",
        "cross_sectional_rank_previous_close_adjustment": "split",
        "cross_sectional_rank_target_minute_adjustment": "split",
        "raw_split_target_timestamp_coverage_must_match": True,
        "split_factor_may_not_affect_price_threshold": True,
        "split_factor_cancels_from_gain_and_rank": True,
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
        raise ValueError("historical source v0.3 authorization hash mismatch")
    if claimed != AUTHORIZATION_CONTENT_SHA256:
        raise ValueError("historical source v0.3 differs from frozen hash")
    if body != expected_authorization_body():
        raise ValueError("historical source v0.3 authorization changed")


def validate_parent_bundle(
    *,
    v02_authorization: Mapping[str, object],
    v02_success_audit: Mapping[str, object],
    scanner_failure_audit: Mapping[str, object],
) -> None:
    validate_v02_authorization(v02_authorization)
    for payload, expected, label in (
        (v02_success_audit, V02_SUCCESS_AUDIT_CONTENT_SHA256, "v0.2 success"),
        (
            scanner_failure_audit,
            SCANNER_FAILURE_AUDIT_CONTENT_SHA256,
            "scanner failure",
        ),
    ):
        body = dict(payload)
        claimed = body.pop("content_sha256", None)
        if claimed != expected or canonical_fingerprint(body) != claimed:
            raise ValueError(f"{label} audit hash mismatch")
    if v02_success_audit.get("workflow", {}).get("run_id") != int(
        V02_WORKFLOW_RUN_ID
    ):
        raise ValueError("v0.2 success run changed")
    if scanner_failure_audit.get("conclusion") != (
        "fail_closed_mixed_split_adjusted_previous_close_and_raw_intraday_"
        "price_basis_invalidates_cross_sectional_rank"
    ):
        raise ValueError("scanner failure conclusion changed")


def summarize_source_root_v03(root: str | Path) -> dict[str, object]:
    source_root = Path(root)

    def manifest(relative: str) -> dict[str, object]:
        return load_json_object(source_root / relative / "manifest.json")

    census = load_json_object(source_root / "manifest.json")
    identity = manifest(IDENTITY_RESOLVED_UNIVERSE_POLICY_ID)
    market = manifest(CAUSAL_MARKET_DISCOVERY_V0_3_POLICY_ID)
    floats = manifest(CAUSAL_FLOAT_POLICY_ID)
    news = manifest(CAUSAL_NEWS_POLICY_ID)
    scanner = manifest(CAUSAL_SCANNER_SNAPSHOT_V0_2_ARTIFACT_ID)
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
    if not isinstance(date_source_manifests, list) or len(date_source_manifests) != len(SELECTED_DATES):
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
        for row in census_dates if isinstance(row, Mapping)
    }
    row_counts = {
        str(row["requested_asof_date"]): int(row["census_summary"]["row_count"])
        for row in census_dates if isinstance(row, Mapping)
    }
    candidate_counts = {
        str(row["trading_date"]): int(row["summary"]["causal_market_candidate_count"])
        for row in market_dates if isinstance(row, Mapping)
    }
    compressed_bytes = {
        str(row["trading_date"]): int(row["summary"]["compressed_size_bytes"])
        for row in date_source_manifests
    }
    source_hashes = {
        name: str(payload.get("content_sha256"))
        for name, payload in manifests.items() if name != "census"
    }
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
            "identity_complete": identity.get("eligibility", {}).get("complete_relative_to_provisional_membership") is True,
            "market_discovery_complete": market.get("eligibility", {}).get("causal_market_discovery_complete") is True,
            "float_complete": floats.get("eligibility", {}).get("point_in_time_float_decisions_frozen") is True,
            "news_complete": news.get("eligibility", {}).get("publication_timed_news_frozen") is True,
            "scanner_snapshot_complete": scanner.get("eligibility", {}).get("candidate_minute_dispositions_frozen") is True,
            "canonical_scanner_inputs_complete": source_inputs.get("replay_boundary", {}).get("canonical_runtime_inputs_persisted") is True,
            "present_day_asset_master_skipped": census.get("current_alpaca_reconciliation_skipped") is True,
        },
    }


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
        raise ValueError("historical source v0.3 is one attempt only")
    if source_summary.get("dates") != list(SELECTED_DATES):
        raise ValueError("historical source dates changed")
    page_counts = source_summary.get("census_page_counts")
    candidate_counts = source_summary.get("candidate_counts")
    source_hashes = source_summary.get("source_hashes")
    if not isinstance(page_counts, Mapping) or any(
        not isinstance(value, int) or not 0 < value <= MAX_CENSUS_PAGES_PER_DATE
        for value in page_counts.values()
    ):
        raise ValueError("historical source census page ceiling exceeded")
    if not isinstance(candidate_counts, Mapping) or any(
        not isinstance(value, int) or not 0 <= value <= MAX_CANDIDATES_PER_DATE
        for value in candidate_counts.values()
    ):
        raise ValueError("historical source candidate ceiling exceeded")
    if not isinstance(source_hashes, Mapping) or any(
        _SHA256.fullmatch(str(value)) is None for value in source_hashes.values()
    ):
        raise ValueError("historical source hashes are invalid")
    if not all(source_summary.get("gates", {}).values()):
        raise ValueError("historical source bundle is incomplete")
    total = request_budget.get("total_attempts")
    by_host = request_budget.get("by_host")
    if not isinstance(total, int) or not 0 < total <= MAX_HTTP_ATTEMPTS:
        raise ValueError("historical source HTTP attempt budget is invalid")
    if (
        not isinstance(by_host, Mapping)
        or not set(by_host).issubset(ALLOWED_REQUEST_HOSTS)
        or sum(int(value) for value in by_host.values()) != total
    ):
        raise ValueError("historical source request hosts are invalid")
    if not 0 < retained_bytes <= MAX_RETAINED_BYTES:
        raise ValueError("historical source retained-byte ceiling exceeded")
    report = freeze(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "sealed_historical_source_acquisition_v0_3_result",
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
            },
            "workflow_provenance": {
                "repository": repository,
                "authorization_commit_sha": authorization_commit_sha,
                "workflow_run_id": str(workflow_run_id),
                "workflow_run_attempt": workflow_run_attempt,
                "v0_2_workflow_run_rerun": False,
            },
            "cost": {"incremental_provider_cost_usd": "0", "databento_called": False},
            "causal_attestation": {
                "transcript_record_values_read": False,
                "ross_labels_or_outcomes_read": False,
                "account_or_order_endpoint_called": False,
                "order_submitted": False,
                "strategy_micro_or_account_policy_changed": False,
            },
            "source_acquisition_gate_passed": True,
            "next_gate": "provider_free_label_blind_scanner_and_micro_runtime_freeze",
        }
    )
    return report
