from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping

from momentumbot.research import databento_smoke_v02 as reset_engine
from momentumbot.research.databento_quote import DATASET, SDK_VERSION, QuoteRequest
from momentumbot.research.databento_smoke import (
    HistoricalClient,
    ReferenceSample,
    RuntimeConstants,
    _decimal,
    _finish_report,
    _integer,
    _mapping,
    _request_kwargs,
)
from momentumbot.research.microstructure_contract import canonical_fingerprint


SCHEMA_VERSION = 1
REPLICATION_CONTRACT_ID = "databento-microstructure-replication-v0.3"
ARTIFACT_TYPE = "sanitized_ephemeral_databento_three_case_replication"
REPLICATION_CONTENT_SHA256 = (
    "d6aca7030155bbf9483e1b2c014481e31eaca5954b42155bbb8366b7501c7b07"
)
AUTHORIZED_PUSH_PARENT_SHA = "a89f0470e4387d016600cdf7beebd09ae25b3146"
PARENT_SUCCESS_AUDIT_ID = (
    "databento-microstructure-smoke-acquisition-v0.2-"
    "run-32435988929-success-2026-08-20"
)
PARENT_SUCCESS_CONTENT_SHA256 = (
    "1ad29da41493c65f17ce906969415bb6246d745909dbc47beffa7ae86bb1d29b"
)
PARENT_SUCCESS_REPORT_CONTENT_SHA256 = (
    "15bd478f44f0953fa877cd9eed30d20e131b0dd988fbc774e7f56f943ee6e71c"
)
RESET_ENGINE_SOURCE_FILE_SHA256 = (
    "c04229c2750d780bde14276171a14e0ce62bd527f6e09bb1ef0331a3020c99e9"
)
MAX_PREFLIGHT_COST_USD = Decimal("0.20")
MAX_PREFLIGHT_BILLABLE_SIZE_BYTES = 380_000_000
REPLICATION_CASES = (
    ("2026-07-10", "INTJ"),
    ("2026-07-20", "AMC"),
    ("2026-07-10", "GMM"),
)
REQUESTS = (
    QuoteRequest(
        trading_date="2026-07-10",
        symbol="INTJ",
        dataset=DATASET,
        schema="mbp-10",
        start="2026-07-10T10:50:00Z",
        end="2026-07-10T14:10:00Z",
    ),
    QuoteRequest(
        trading_date="2026-07-10",
        symbol="INTJ",
        dataset=DATASET,
        schema="mbo",
        start="2026-07-10T00:00:00Z",
        end="2026-07-10T14:10:00Z",
    ),
    QuoteRequest(
        trading_date="2026-07-20",
        symbol="AMC",
        dataset=DATASET,
        schema="mbp-10",
        start="2026-07-20T10:50:00Z",
        end="2026-07-20T14:10:00Z",
    ),
    QuoteRequest(
        trading_date="2026-07-20",
        symbol="AMC",
        dataset=DATASET,
        schema="mbo",
        start="2026-07-20T00:00:00Z",
        end="2026-07-20T14:10:00Z",
    ),
    QuoteRequest(
        trading_date="2026-07-10",
        symbol="GMM",
        dataset=DATASET,
        schema="mbp-10",
        start="2026-07-10T10:50:00Z",
        end="2026-07-10T14:10:00Z",
    ),
    QuoteRequest(
        trading_date="2026-07-10",
        symbol="GMM",
        dataset=DATASET,
        schema="mbo",
        start="2026-07-10T00:00:00Z",
        end="2026-07-10T14:10:00Z",
    ),
)


def _verify_reset_engine_source() -> None:
    source_path = Path(str(reset_engine.__file__))
    if source_path.suffix != ".py":
        raise ValueError("v0.3 requires the frozen v0.2 Python source file")
    observed = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if observed != RESET_ENGINE_SOURCE_FILE_SHA256:
        raise ValueError("frozen v0.2 reset engine source changed")


def validate_parent_success_audit(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported parent success audit schema")
    if payload.get("audit_id") != PARENT_SUCCESS_AUDIT_ID:
        raise ValueError("unexpected parent success audit")
    if payload.get("artifact_type") != (
        "independently_verified_sanitized_databento_reset_repair_success"
    ):
        raise ValueError("unexpected parent success audit type")
    claimed = payload.get("content_sha256")
    if claimed != PARENT_SUCCESS_CONTENT_SHA256:
        raise ValueError("parent success audit content hash changed")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("parent success audit fingerprint mismatch")

    actions = _mapping(payload.get("github_actions"), "github_actions")
    expected_actions = {
        "workflow_run_id": 32435988929,
        "workflow_run_attempt": 1,
        "workflow_conclusion": "success",
        "workflow_head_sha": AUTHORIZED_PUSH_PARENT_SHA,
        "sanitized_report_content_sha256": (
            PARENT_SUCCESS_REPORT_CONTENT_SHA256
        ),
    }
    for field, expected in expected_actions.items():
        if actions.get(field) != expected:
            raise ValueError(f"parent github_actions.{field} changed")

    acquisition = _mapping(payload.get("verified_acquisition"), "verified_acquisition")
    expected_acquisition = {
        "symbol": "EQPT",
        "timeseries_request_count": 2,
        "total_quoted_cost_usd": "0.005820024014",
        "total_billable_size_bytes": 10810592,
        "g1_schema_and_integrity_passed": True,
        "g2_reconstruction_passed": True,
        "smoke_acquisition_passed": True,
    }
    for field, expected in expected_acquisition.items():
        if acquisition.get(field) != expected:
            raise ValueError(f"parent verified_acquisition.{field} changed")

    evidence = _mapping(
        payload.get("verified_reset_and_alignment_evidence"),
        "verified_reset_and_alignment_evidence",
    )
    for field in (
        "aligned_sample_count",
        "independent_replay_exact_match_count",
        "mbp10_exact_match_count",
        "mbp10_price_match_count",
        "mbp10_size_match_count",
        "mbp10_order_count_match_count",
    ):
        if evidence.get(field) != 153:
            raise ValueError(f"parent alignment {field} changed")
    if evidence.get("reference_alignment_ratio") != "1":
        raise ValueError("parent alignment ratio changed")

    safety = _mapping(payload.get("safety_verification"), "safety_verification")
    for field in (
        "automatic_retry_attempted",
        "batch_or_live_endpoint_called",
        "provider_credential_persisted",
        "raw_market_data_persisted",
        "raw_market_data_uploaded",
        "runtime_authority_created",
        "broker_or_order_change_made",
        "strategy_or_threshold_change_made",
    ):
        if safety.get(field) is not False:
            raise ValueError(f"parent safety field {field} changed")


def load_parent_success_audit(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("parent success audit root must be an object")
    validate_parent_success_audit(payload)
    return payload


def validate_replication_contract(
    payload: Mapping[str, object],
    *,
    parent_success_audit: Mapping[str, object] | None = None,
) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported Databento v0.3 replication schema")
    if payload.get("replication_contract_id") != REPLICATION_CONTRACT_ID:
        raise ValueError("unexpected Databento v0.3 replication contract")
    if payload.get("artifact_type") != (
        "preregistered_bounded_ephemeral_databento_three_case_replication"
    ):
        raise ValueError("unexpected Databento v0.3 replication type")
    claimed = payload.get("content_sha256")
    if claimed != REPLICATION_CONTENT_SHA256:
        raise ValueError("Databento v0.3 replication content hash changed")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("Databento v0.3 replication fingerprint mismatch")

    parent = _mapping(payload.get("frozen_parent_success"), "frozen_parent_success")
    if parent.get("audit_id") != PARENT_SUCCESS_AUDIT_ID:
        raise ValueError("v0.3 parent audit changed")
    if parent.get("content_sha256") != PARENT_SUCCESS_CONTENT_SHA256:
        raise ValueError("v0.3 parent content hash changed")
    if parent.get("sanitized_report_content_sha256") != (
        PARENT_SUCCESS_REPORT_CONTENT_SHA256
    ):
        raise ValueError("v0.3 parent report hash changed")
    if parent_success_audit is not None:
        validate_parent_success_audit(parent_success_audit)

    engine = _mapping(payload.get("frozen_reset_engine"), "frozen_reset_engine")
    if engine.get("path") != "src/momentumbot/research/databento_smoke_v02.py":
        raise ValueError("v0.3 reset engine path changed")
    if engine.get("file_sha256") != RESET_ENGINE_SOURCE_FILE_SHA256:
        raise ValueError("v0.3 reset engine hash changed")
    if engine.get("change_allowed_in_replication") is not False:
        raise ValueError("v0.3 reset engine mutation was enabled")

    authorization = _mapping(payload.get("authorization"), "authorization")
    expected_authorization = {
        "metadata_requote_authorized": True,
        "historical_timeseries_download_authorized": True,
        "exact_request_count_authorized": 6,
        "authorized_push_parent_sha": AUTHORIZED_PUSH_PARENT_SHA,
        "batch_job_authorized": False,
        "live_subscription_authorized": False,
        "broad_history_download_authorized": False,
        "automatic_retry_authorized": False,
        "broker_or_order_change_authorized": False,
        "reported_new_user_credit_usd": "125",
        "observed_v0_1_three_case_quote_usd": "0.182469338178",
        "hard_preflight_cost_ceiling_usd": "0.20",
        "observed_v0_1_three_case_billable_size_bytes": 365533168,
        "hard_preflight_billable_size_ceiling_bytes": 380000000,
    }
    for field, expected in expected_authorization.items():
        if authorization.get(field) != expected:
            raise ValueError(f"authorization.{field} changed")

    provider = _mapping(payload.get("provider"), "provider")
    expected_provider = {
        "provider_id": "databento",
        "dataset": DATASET,
        "venue_scope": "single_venue_nasdaq_not_consolidated_national_depth",
        "sdk_package": "databento",
        "sdk_version": SDK_VERSION,
        "secret_name": "DATABENTO_API_KEY",
    }
    for field, expected in expected_provider.items():
        if provider.get(field) != expected:
            raise ValueError(f"provider.{field} changed")

    surface = _mapping(payload.get("request_surface"), "request_surface")
    observed_cases = tuple(
        (
            str(_mapping(item, "replication case").get("trading_date")),
            str(_mapping(item, "replication case").get("symbol")),
        )
        for item in surface.get("cases", [])
    )
    if observed_cases != REPLICATION_CASES:
        raise ValueError("v0.3 replication cases changed")
    observed_requests = tuple(
        QuoteRequest(
            trading_date=str(_mapping(item, "replication request").get("trading_date")),
            symbol=str(_mapping(item, "replication request").get("symbol")),
            dataset=str(_mapping(item, "replication request").get("dataset")),
            schema=str(_mapping(item, "replication request").get("schema")),
            start=str(_mapping(item, "replication request").get("start")),
            end=str(_mapping(item, "replication request").get("end")),
            stype_in=str(_mapping(item, "replication request").get("stype_in")),
        )
        for item in surface.get("requests", [])
    )
    if observed_requests != REQUESTS:
        raise ValueError("v0.3 exact request surface changed")
    if surface.get("allowed_calls") != [
        "historical.metadata.get_billable_size",
        "historical.metadata.get_cost",
        "historical.timeseries.get_range",
    ]:
        raise ValueError("v0.3 allowed provider calls changed")
    if surface.get("prohibited_calls") != [
        "historical.batch.submit_job",
        "historical.batch.download",
        "live.subscribe",
    ]:
        raise ValueError("v0.3 prohibited provider calls changed")

    storage = _mapping(payload.get("storage_and_licensing"), "storage_and_licensing")
    if storage.get("public_repository_raw_data") is not False:
        raise ValueError("v0.3 public raw-data policy changed")
    if storage.get("github_artifact_raw_data") is not False:
        raise ValueError("v0.3 raw artifact policy changed")


def load_replication_contract(
    path: str | Path,
    *,
    parent_success_audit: Mapping[str, object],
) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Databento v0.3 contract root must be an object")
    validate_replication_contract(
        payload,
        parent_success_audit=parent_success_audit,
    )
    return payload


def _run_preflight(
    client: HistoricalClient,
) -> tuple[dict[str, object], list[dict[str, str]]]:
    rows: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    total_cost = Decimal("0")
    total_size = 0
    for request in REQUESTS:
        kwargs = _request_kwargs(request)
        stage = f"preflight:{request.trading_date}:{request.symbol}:{request.schema}"
        try:
            size = _integer(client.metadata.get_billable_size(**kwargs), "billable size")
            cost = _decimal(client.metadata.get_cost(**kwargs), "quoted cost")
        except Exception as exc:
            errors.append({"stage": stage, "error_kind": type(exc).__name__})
            break
        total_size += size
        total_cost += cost
        row: dict[str, object] = request.mapping()
        row.update(
            {
                "billable_size_bytes": size,
                "quoted_cost_usd": format(cost, "f"),
            }
        )
        rows.append(row)

    complete = len(rows) == len(REQUESTS) == 6 and not errors
    within_cost = complete and total_cost <= MAX_PREFLIGHT_COST_USD
    within_size = complete and total_size <= MAX_PREFLIGHT_BILLABLE_SIZE_BYTES
    return (
        {
            "request_count_expected": 6,
            "request_count_quoted": len(rows),
            "quote_rows": rows,
            "total_quoted_cost_usd": format(total_cost, "f") if complete else None,
            "total_billable_size_bytes": total_size if complete else None,
            "hard_cost_ceiling_usd": format(MAX_PREFLIGHT_COST_USD, "f"),
            "hard_billable_size_ceiling_bytes": MAX_PREFLIGHT_BILLABLE_SIZE_BYTES,
            "all_six_quotes_complete": complete,
            "cost_within_ceiling": within_cost,
            "billable_size_within_ceiling": within_size,
            "preflight_passed": complete and within_cost and within_size,
        },
        errors,
    )


def _base_report(*, generated_at: datetime, sdk_version: str) -> dict[str, object]:
    from momentumbot.research.databento_smoke import _iso_z

    return {
        "schema_version": SCHEMA_VERSION,
        "replication_contract_id": REPLICATION_CONTRACT_ID,
        "replication_contract_content_sha256": REPLICATION_CONTENT_SHA256,
        "artifact_type": ARTIFACT_TYPE,
        "generated_at": _iso_z(generated_at),
        "parent_success_audit_id": PARENT_SUCCESS_AUDIT_ID,
        "parent_success_audit_content_sha256": PARENT_SUCCESS_CONTENT_SHA256,
        "parent_success_report_content_sha256": (
            PARENT_SUCCESS_REPORT_CONTENT_SHA256
        ),
        "reset_engine_source_file_sha256": RESET_ENGINE_SOURCE_FILE_SHA256,
        "provider": "databento",
        "dataset": DATASET,
        "venue_scope": "single_venue_nasdaq_not_consolidated_national_depth",
        "sdk_version": sdk_version,
        "provider_credential_persisted": False,
        "raw_market_data_persisted": False,
        "raw_market_data_uploaded": False,
        "batch_or_live_endpoint_called": False,
        "automatic_retry_attempted": False,
        "broker_or_order_change_made": False,
        "strategy_or_threshold_change_made": False,
        "actual_billing_known": False,
        "billing_note": (
            "Preflight quotes are not represented as actual billed charges; "
            "completed downloads may be billable."
        ),
    }


def build_unavailable_report(
    contract: Mapping[str, object],
    *,
    parent_success_audit: Mapping[str, object],
    generated_at: datetime,
    sdk_version: str,
    error_stage: str,
    error_kind: str,
) -> dict[str, object]:
    validate_replication_contract(
        contract,
        parent_success_audit=parent_success_audit,
    )
    _verify_reset_engine_source()
    report = _base_report(generated_at=generated_at, sdk_version=sdk_version)
    report.update(
        {
            "preflight": {
                "request_count_expected": 6,
                "request_count_quoted": 0,
                "quote_rows": [],
                "total_quoted_cost_usd": None,
                "total_billable_size_bytes": None,
                "hard_cost_ceiling_usd": format(MAX_PREFLIGHT_COST_USD, "f"),
                "hard_billable_size_ceiling_bytes": (
                    MAX_PREFLIGHT_BILLABLE_SIZE_BYTES
                ),
                "all_six_quotes_complete": False,
                "cost_within_ceiling": False,
                "billable_size_within_ceiling": False,
                "preflight_passed": False,
            },
            "timeseries_request_count": 0,
            "downloads": [],
            "cases": [],
            "errors": [{"stage": error_stage, "error_kind": error_kind}],
            "raw_temp_directory_empty_before_cleanup": True,
            "raw_temp_directory_removed": True,
            "g1_schema_and_integrity_passed": False,
            "g2_reconstruction_passed": False,
            "replication_passed": False,
            "runtime_authority_created": False,
        }
    )
    return _finish_report(report)


def run_replication(
    contract: Mapping[str, object],
    client: HistoricalClient,
    *,
    parent_success_audit: Mapping[str, object],
    generated_at: datetime,
    sdk_version: str,
    runtime: RuntimeConstants,
) -> dict[str, object]:
    validate_replication_contract(
        contract,
        parent_success_audit=parent_success_audit,
    )
    _verify_reset_engine_source()
    if sdk_version != SDK_VERSION:
        raise ValueError(f"Databento SDK version must be {SDK_VERSION}")
    preflight, errors = _run_preflight(client)
    report = _base_report(generated_at=generated_at, sdk_version=sdk_version)
    report.update(
        {
            "preflight": preflight,
            "timeseries_request_count": 0,
            "downloads": [],
            "cases": [],
            "errors": errors,
            "raw_temp_directory_empty_before_cleanup": True,
            "raw_temp_directory_removed": True,
        }
    )
    if preflight.get("preflight_passed") is not True:
        report.update(
            {
                "g1_schema_and_integrity_passed": False,
                "g2_reconstruction_passed": False,
                "replication_passed": False,
                "runtime_authority_created": False,
            }
        )
        return _finish_report(report)

    request_lookup = {
        (request.trading_date, request.symbol, request.schema): request
        for request in REQUESTS
    }
    temp = tempfile.TemporaryDirectory(prefix="momentumbot-databento-v03-")
    temp_path = Path(temp.name)
    halted = False
    try:
        for trading_date, symbol in REPLICATION_CASES:
            case_downloads: list[dict[str, object]] = []
            references: dict[tuple[int, int, int], ReferenceSample] | None = None
            for schema in reset_engine.DOWNLOAD_SCHEMA_ORDER:
                request = request_lookup[(trading_date, symbol, schema)]
                raw_path = temp_path / f"request-{len(report['downloads']):02d}.dbn.zst"
                stage = f"download_or_parse:{trading_date}:{symbol}:{schema}"
                try:
                    report["timeseries_request_count"] = int(
                        report["timeseries_request_count"]
                    ) + 1
                    row, new_references = reset_engine._download_and_process(
                        client,
                        request,
                        raw_path,
                        runtime,
                        references,
                    )
                    if new_references is not None:
                        references = new_references
                    case_downloads.append(row)
                    report["downloads"].append(row)
                except Exception as exc:
                    errors.append({"stage": stage, "error_kind": type(exc).__name__})
                    halted = True
                    break
                finally:
                    raw_path.unlink(missing_ok=True)
            case: dict[str, object] = {
                "trading_date": trading_date,
                "symbol": symbol,
                "downloads": case_downloads,
            }
            g1, g2, conditions = reset_engine._case_gate(case)
            case.update(
                {
                    "gate_conditions": conditions,
                    "g1_schema_and_integrity_passed": g1,
                    "g2_reconstruction_passed": g2,
                }
            )
            report["cases"].append(case)
            references = None
            if halted:
                break
    finally:
        report["raw_temp_directory_empty_before_cleanup"] = not any(
            temp_path.iterdir()
        )
        temp_name = temp.name
        temp.cleanup()
        report["raw_temp_directory_removed"] = not Path(temp_name).exists()

    cases = report["cases"] if isinstance(report["cases"], list) else []
    g1 = (
        len(cases) == len(REPLICATION_CASES)
        and not errors
        and len(report["downloads"]) == 6
        and all(
            isinstance(case, Mapping)
            and case.get("g1_schema_and_integrity_passed") is True
            for case in cases
        )
        and report["raw_temp_directory_empty_before_cleanup"] is True
        and report["raw_temp_directory_removed"] is True
    )
    g2 = g1 and all(
        isinstance(case, Mapping)
        and case.get("g2_reconstruction_passed") is True
        for case in cases
    )
    report.update(
        {
            "g1_schema_and_integrity_passed": g1,
            "g2_reconstruction_passed": g2,
            "replication_passed": g1 and g2,
            "runtime_authority_created": False,
        }
    )
    return _finish_report(report)


def _walk_keys(value: object) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def validate_replication_report(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported Databento v0.3 report schema")
    if payload.get("replication_contract_id") != REPLICATION_CONTRACT_ID:
        raise ValueError("unexpected Databento v0.3 report contract")
    if payload.get("replication_contract_content_sha256") != (
        REPLICATION_CONTENT_SHA256
    ):
        raise ValueError("v0.3 report contract binding changed")
    if payload.get("artifact_type") != ARTIFACT_TYPE:
        raise ValueError("unexpected Databento v0.3 report type")
    if payload.get("parent_success_audit_content_sha256") != (
        PARENT_SUCCESS_CONTENT_SHA256
    ):
        raise ValueError("v0.3 report parent binding changed")
    if payload.get("reset_engine_source_file_sha256") != (
        RESET_ENGINE_SOURCE_FILE_SHA256
    ):
        raise ValueError("v0.3 report reset engine binding changed")
    for field in (
        "provider_credential_persisted",
        "raw_market_data_persisted",
        "raw_market_data_uploaded",
        "batch_or_live_endpoint_called",
        "automatic_retry_attempted",
        "broker_or_order_change_made",
        "strategy_or_threshold_change_made",
        "actual_billing_known",
        "runtime_authority_created",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must remain false")
    if payload.get("raw_temp_directory_empty_before_cleanup") is not True:
        raise ValueError("v0.3 raw temporary directory was not empty")
    if payload.get("raw_temp_directory_removed") is not True:
        raise ValueError("v0.3 raw temporary directory was not removed")
    if int(payload.get("timeseries_request_count", 0)) > 6:
        raise ValueError("v0.3 request count exceeded authorization")
    forbidden_keys = {
        "raw_records",
        "record_values",
        "order_id",
        "instrument_id",
        "price",
        "size",
        "levels",
        "temporary_path",
        "provider_error_message",
        "exception_message",
    }
    if set(_walk_keys(payload)) & forbidden_keys:
        raise ValueError("sanitized v0.3 report contains a prohibited field")
    downloads = payload.get("downloads")
    if not isinstance(downloads, list):
        raise ValueError("v0.3 report downloads must be a list")
    for row in downloads:
        if not isinstance(row, Mapping):
            raise ValueError("v0.3 download summary must be an object")
        digest = row.get("ephemeral_file_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("v0.3 download file hash is invalid")
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("v0.3 report cases must be a list")
    claimed = payload.get("content_sha256")
    if not isinstance(claimed, str) or len(claimed) != 64:
        raise ValueError("v0.3 report content hash is invalid")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("v0.3 report content fingerprint mismatch")


__all__ = [
    "ARTIFACT_TYPE",
    "AUTHORIZED_PUSH_PARENT_SHA",
    "MAX_PREFLIGHT_BILLABLE_SIZE_BYTES",
    "MAX_PREFLIGHT_COST_USD",
    "PARENT_SUCCESS_CONTENT_SHA256",
    "REPLICATION_CASES",
    "REPLICATION_CONTENT_SHA256",
    "REPLICATION_CONTRACT_ID",
    "REQUESTS",
    "RESET_ENGINE_SOURCE_FILE_SHA256",
    "RuntimeConstants",
    "build_unavailable_report",
    "load_parent_success_audit",
    "load_replication_contract",
    "run_replication",
    "validate_parent_success_audit",
    "validate_replication_contract",
    "validate_replication_report",
]
