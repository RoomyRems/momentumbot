"""One-call credential-routing repair for the sealed historical provider gate."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

from momentumbot.research.sealed_historical_availability import (
    AUTHORIZATION_CONTENT_SHA256 as V01_AUTHORIZATION_CONTENT_SHA256,
    SELECTED_DATES,
    ProviderRequest,
    _summarize_alpaca,
    _walk_keys,
    build_probe_plan as build_v01_probe_plan,
    freeze,
    validate_authorization as validate_v01_authorization,
    validate_report as validate_v01_report,
    write_json_once,
)
from momentumbot.research.sealed_historical_walk_forward import (
    CONTRACT_CONTENT_SHA256,
    CONTRACT_ID,
    canonical_fingerprint,
    load_json_object,
)


SCHEMA_VERSION = 1
AUTHORIZATION_ID = "sealed-historical-provider-availability-v0.2"
AUTHORIZATION_CONTENT_SHA256 = (
    "72840ae3386559dfc0cb2ddea422e67a2e6a71685b641f0d94e193d5680d2de9"
)
ARTIFACT_TYPE = "bounded_sanitized_historical_provider_availability_repair"
V01_FAILURE_REPORT_CONTENT_SHA256 = (
    "05be1e2e7ab30433489b4d00ec79414c13a73b249df0c5d33742049a7d7a6e08"
)
V01_FAILURE_AUDIT_CONTENT_SHA256 = (
    "59fc89f8f86af18cb08fa65abb40dba388665afe880d2d18013bfc1317c42759"
)
V01_WORKFLOW_RUN_ID = 33348067097
VALIDATED_PRECEDENT_COMMIT = "e7db059bf258b4d069c788d6293307737d4cea2e"
MAIN_SECRET_NAMES = ("ALPACA_MAIN_API_KEY", "ALPACA_MAIN_API_SECRET")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_FORBIDDEN_REPORT_KEYS = {
    "api_key",
    "api_secret",
    "bars",
    "captions",
    "close",
    "high",
    "low",
    "open",
    "results",
    "title",
    "volume",
}


def load_authorization(path: str | Path) -> dict[str, object]:
    payload = load_json_object(path)
    validate_authorization(payload)
    return payload


def validate_authorization(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported availability-repair authorization schema")
    if payload.get("artifact_type") != (
        "preregistered_bounded_provider_availability_credential_routing_repair"
    ):
        raise ValueError("unexpected availability-repair authorization type")
    if payload.get("authorization_id") != AUTHORIZATION_ID:
        raise ValueError("unexpected availability-repair authorization ID")
    body = dict(payload)
    claimed = body.pop("content_sha256", None)
    if claimed != canonical_fingerprint(body):
        raise ValueError("availability-repair authorization content hash mismatch")
    if claimed != AUTHORIZATION_CONTENT_SHA256:
        raise ValueError("availability-repair authorization differs from frozen hash")
    if payload.get("authorized_call") != {
        "alpaca_sip_spy_daily": {
            "maximum_calls": 1,
            "pagination_allowed": False,
            "raw_rows_persisted": False,
        },
        "maximum_total_calls": 1,
    }:
        raise ValueError("availability-repair call budget changed")
    if payload.get("credential_routing") != {
        "github_actions_secret_names": list(MAIN_SECRET_NAMES),
        "prior_incorrect_secret_names": [
            "ALPACA_API_KEY",
            "ALPACA_API_SECRET",
        ],
        "runtime_environment_aliases": {
            "ALPACA_API_KEY": MAIN_SECRET_NAMES[0],
            "ALPACA_API_SECRET": MAIN_SECRET_NAMES[1],
        },
        "validated_precedent_commit": VALIDATED_PRECEDENT_COMMIT,
        "validated_precedent_description": (
            "Use validated paper credentials for prospective scheduler"
        ),
    }:
        raise ValueError("availability-repair credential routing changed")
    if payload.get("frozen_parent") != {
        "contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "contract_id": CONTRACT_ID,
        "selected_dates": list(SELECTED_DATES),
        "v0_1_authorization_content_sha256": V01_AUTHORIZATION_CONTENT_SHA256,
        "v0_1_failure_audit_content_sha256": V01_FAILURE_AUDIT_CONTENT_SHA256,
        "v0_1_failure_report_content_sha256": V01_FAILURE_REPORT_CONTENT_SHA256,
        "v0_1_workflow_run_id": V01_WORKFLOW_RUN_ID,
    }:
        raise ValueError("availability-repair frozen parent changed")
    if payload.get("inherited_provider_results") != {
        "databento_xnas_itch_interval_covered": True,
        "massive_point_in_time_sample_dates": [
            SELECTED_DATES[0],
            SELECTED_DATES[-1],
        ],
        "provider_calls_repeated": False,
    }:
        raise ValueError("availability-repair inherited results changed")
    if payload.get("isolated_change") != {
        "alpaca_endpoint_or_parameters_changed": False,
        "credential_values_changed_or_observed": False,
        "github_secret_routing_only": True,
        "massive_or_databento_called_again": False,
        "selected_dates_or_strategy_changed": False,
    }:
        raise ValueError("availability-repair isolated change expanded")
    if payload.get("one_shot_contract") != {
        "automatic_retry_allowed": False,
        "run_attempt_required": 1,
        "v0_1_run_may_be_rerun": False,
    }:
        raise ValueError("availability-repair one-shot contract changed")
    if payload.get("prohibitions") != [
        "account_or_broker_endpoint",
        "automatic_retry_or_rerun",
        "databento_call",
        "historical_universe_or_intraday_bulk_download",
        "massive_or_polygon_call",
        "news_or_sec_content_download",
        "paper_or_live_order",
        "transcript_record_value_read",
    ]:
        raise ValueError("availability-repair prohibitions changed")
    if payload.get("reported_incremental_cost_usd") != "0":
        raise ValueError("availability-repair quoted cost changed")
    if payload.get("authority_boundary") != {
        "full_data_acquisition_authorized": False,
        "live_order_authorized": False,
        "paper_order_authorized": False,
        "policy_promotion_eligible": False,
        "provider_repair_probe_authorized": True,
    }:
        raise ValueError("availability-repair authority boundary changed")


def validate_parent_bundle(
    *,
    registration: Mapping[str, object],
    v01_authorization: Mapping[str, object],
    v01_report: Mapping[str, object],
    v01_failure_audit: Mapping[str, object],
) -> None:
    validate_v01_authorization(v01_authorization)
    validate_v01_report(v01_report, v01_authorization, registration)
    if v01_report.get("content_sha256") != V01_FAILURE_REPORT_CONTENT_SHA256:
        raise ValueError("availability-repair v0.1 report changed")
    probes = v01_report.get("probes")
    if not isinstance(probes, Mapping):
        raise ValueError("availability-repair v0.1 probes missing")
    alpaca = probes.get("alpaca_sip_session_calendar")
    massive = probes.get("massive_point_in_time_endpoints")
    databento = probes.get("databento_dataset_range")
    if not isinstance(alpaca, Mapping) or alpaca.get("status") != 401:
        raise ValueError("availability-repair parent is not the frozen 401")
    if not isinstance(massive, list) or not all(
        isinstance(row, Mapping) and row.get("ok") is True for row in massive
    ):
        raise ValueError("availability-repair Massive parent did not pass")
    if not isinstance(databento, Mapping) or databento.get("ok") is not True:
        raise ValueError("availability-repair Databento parent did not pass")
    audit_body = dict(v01_failure_audit)
    audit_hash = audit_body.pop("content_sha256", None)
    if audit_hash != canonical_fingerprint(audit_body):
        raise ValueError("availability-repair v0.1 failure audit hash mismatch")
    if audit_hash != V01_FAILURE_AUDIT_CONTENT_SHA256:
        raise ValueError("availability-repair v0.1 failure audit changed")
    workflow = v01_failure_audit.get("workflow")
    if not isinstance(workflow, Mapping) or workflow.get("run_id") != V01_WORKFLOW_RUN_ID:
        raise ValueError("availability-repair v0.1 run binding changed")


def build_probe_plan(
    *,
    authorization: Mapping[str, object],
    registration: Mapping[str, object],
    v01_authorization: Mapping[str, object],
    v01_report: Mapping[str, object],
    v01_failure_audit: Mapping[str, object],
) -> dict[str, object]:
    validate_authorization(authorization)
    validate_parent_bundle(
        registration=registration,
        v01_authorization=v01_authorization,
        v01_report=v01_report,
        v01_failure_audit=v01_failure_audit,
    )
    v01_plan = build_v01_probe_plan(registration, v01_authorization)
    return {
        "authorization_id": AUTHORIZATION_ID,
        "authorization_content_sha256": authorization["content_sha256"],
        "alpaca": v01_plan["alpaca"],
        "maximum_total_calls": 1,
    }


def run_probe(
    *,
    authorization: Mapping[str, object],
    registration: Mapping[str, object],
    v01_authorization: Mapping[str, object],
    v01_report: Mapping[str, object],
    v01_failure_audit: Mapping[str, object],
    alpaca_request: ProviderRequest,
    repository: str,
    authorization_commit_sha: str,
    workflow_run_id: str,
    workflow_run_attempt: int,
) -> dict[str, object]:
    plan = build_probe_plan(
        authorization=authorization,
        registration=registration,
        v01_authorization=v01_authorization,
        v01_report=v01_report,
        v01_failure_audit=v01_failure_audit,
    )
    if repository != "RoomyRems/momentumbot":
        raise ValueError("availability-repair repository mismatch")
    if _GIT_SHA.fullmatch(authorization_commit_sha) is None:
        raise ValueError("availability-repair commit must be a full Git SHA")
    if workflow_run_attempt != 1:
        raise ValueError("availability-repair is one attempt only")
    alpaca = _summarize_alpaca(alpaca_request(plan["alpaca"]))
    passed = alpaca.get("ok") is True
    report = freeze(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": ARTIFACT_TYPE,
            "authorization_id": AUTHORIZATION_ID,
            "authorization_content_sha256": authorization["content_sha256"],
            "selected_dates": list(SELECTED_DATES),
            "workflow_provenance": {
                "repository": repository,
                "authorization_commit_sha": authorization_commit_sha,
                "workflow_run_id": str(workflow_run_id),
                "workflow_run_attempt": workflow_run_attempt,
            },
            "credential_routing": {
                "github_actions_secret_names_used": list(MAIN_SECRET_NAMES),
                "credential_values_observed_or_persisted": False,
                "validated_precedent_commit": VALIDATED_PRECEDENT_COMMIT,
            },
            "current_attempt_call_counts": {"alpaca": 1, "total": 1},
            "maximum_authorized_call_count": plan["maximum_total_calls"],
            "cumulative_v0_1_and_v0_2_call_count": 5,
            "probes": {"alpaca_sip_session_calendar": alpaca},
            "inherited_provider_results": {
                "source_report_content_sha256": V01_FAILURE_REPORT_CONTENT_SHA256,
                "massive_point_in_time_samples_passed": True,
                "databento_xnas_itch_interval_covered": True,
                "provider_calls_repeated": False,
            },
            "availability_gate_passed": passed,
            "incremental_cost_usd": "0",
            "provider_error_messages_persisted": False,
            "provider_credentials_persisted": False,
            "raw_provider_rows_persisted": False,
            "historical_universe_downloaded": False,
            "intraday_market_data_downloaded": False,
            "massive_or_polygon_called": False,
            "databento_called": False,
            "transcript_record_values_read": False,
            "account_or_broker_endpoint_called": False,
            "order_submitted": False,
            "automatic_retry_or_rerun_attempted": False,
            "v0_1_run_rerun": False,
            "next_gate": (
                "register exact bounded historical acquisition and cost ceilings"
                if passed
                else "preserve the v0.2 safe failure and do not acquire data"
            ),
        }
    )
    validate_report(report, authorization)
    return report


def validate_report(
    report: Mapping[str, object], authorization: Mapping[str, object]
) -> None:
    validate_authorization(authorization)
    if report.get("artifact_type") != ARTIFACT_TYPE:
        raise ValueError("unexpected availability-repair report type")
    body = dict(report)
    claimed = body.pop("content_sha256", None)
    if claimed != canonical_fingerprint(body):
        raise ValueError("availability-repair report content hash mismatch")
    if report.get("authorization_id") != AUTHORIZATION_ID:
        raise ValueError("availability-repair report authorization mismatch")
    if report.get("authorization_content_sha256") != authorization.get(
        "content_sha256"
    ):
        raise ValueError("availability-repair report authorization hash mismatch")
    if report.get("selected_dates") != list(SELECTED_DATES):
        raise ValueError("availability-repair selected dates changed")
    provenance = report.get("workflow_provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("availability-repair provenance missing")
    if provenance.get("repository") != "RoomyRems/momentumbot":
        raise ValueError("availability-repair provenance repository mismatch")
    if _GIT_SHA.fullmatch(str(provenance.get("authorization_commit_sha", ""))) is None:
        raise ValueError("availability-repair provenance commit invalid")
    if provenance.get("workflow_run_attempt") != 1:
        raise ValueError("availability-repair provenance attempt changed")
    if report.get("current_attempt_call_counts") != {"alpaca": 1, "total": 1}:
        raise ValueError("availability-repair call accounting changed")
    if report.get("maximum_authorized_call_count") != 1:
        raise ValueError("availability-repair call ceiling changed")
    routing = report.get("credential_routing")
    if routing != {
        "github_actions_secret_names_used": list(MAIN_SECRET_NAMES),
        "credential_values_observed_or_persisted": False,
        "validated_precedent_commit": VALIDATED_PRECEDENT_COMMIT,
    }:
        raise ValueError("availability-repair report routing changed")
    inherited = report.get("inherited_provider_results")
    if inherited != {
        "source_report_content_sha256": V01_FAILURE_REPORT_CONTENT_SHA256,
        "massive_point_in_time_samples_passed": True,
        "databento_xnas_itch_interval_covered": True,
        "provider_calls_repeated": False,
    }:
        raise ValueError("availability-repair inherited results changed")
    probes = report.get("probes")
    alpaca = probes.get("alpaca_sip_session_calendar") if isinstance(probes, Mapping) else None
    if not isinstance(alpaca, Mapping):
        raise ValueError("availability-repair Alpaca summary missing")
    if report.get("availability_gate_passed") is not (alpaca.get("ok") is True):
        raise ValueError("availability-repair gate conclusion inconsistent")
    for field, expected in {
        "incremental_cost_usd": "0",
        "provider_error_messages_persisted": False,
        "provider_credentials_persisted": False,
        "raw_provider_rows_persisted": False,
        "historical_universe_downloaded": False,
        "intraday_market_data_downloaded": False,
        "massive_or_polygon_called": False,
        "databento_called": False,
        "transcript_record_values_read": False,
        "account_or_broker_endpoint_called": False,
        "order_submitted": False,
        "automatic_retry_or_rerun_attempted": False,
        "v0_1_run_rerun": False,
    }.items():
        if report.get(field) != expected:
            raise ValueError(f"availability-repair report changed {field}")
    forbidden = _walk_keys(report) & _FORBIDDEN_REPORT_KEYS
    if forbidden:
        raise ValueError(f"availability-repair report leaked raw fields: {sorted(forbidden)}")


__all__ = [
    "AUTHORIZATION_CONTENT_SHA256",
    "AUTHORIZATION_ID",
    "MAIN_SECRET_NAMES",
    "build_probe_plan",
    "freeze",
    "load_authorization",
    "run_probe",
    "validate_authorization",
    "validate_parent_bundle",
    "validate_report",
    "write_json_once",
]
