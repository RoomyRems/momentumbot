from __future__ import annotations

import json
import re
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping

from momentumbot.research import databento_fill_cancel_classifier_v01 as classifier
from momentumbot.research.databento_fill_cancel_classifier_v01 import (
    CLASSIFIER_CONTRACT_ID,
    CONTRACT_CONTENT_SHA256,
    PARENT_FAILURE_AUDIT_ID,
    PARENT_FAILURE_CONTENT_SHA256,
    PARENT_REPORT_CONTENT_SHA256,
    REQUEST,
    classify_fill_cancel_structure,
    validate_classifier_contract,
    validate_parent_failure_audit,
)
from momentumbot.research.databento_quote import DATASET, SDK_VERSION
from momentumbot.research.databento_smoke import (
    HistoricalClient,
    RuntimeConstants,
    _decimal,
    _finish_report,
    _integer,
    _iso_z,
    _metadata_value,
    _request_kwargs,
)
from momentumbot.research.microstructure_contract import (
    canonical_fingerprint,
    file_sha256,
)


SCHEMA_VERSION = 1
EXECUTION_AUTHORIZATION_ID = (
    "databento-microstructure-fill-cancel-classifier-v0.1-execution"
)
ARTIFACT_TYPE = "sanitized_databento_fill_cancel_structure_classifier"
CLASSIFIER_SOURCE_FILE_SHA256 = (
    "0b8e3d258a7bc5ca90efbd7ef1e1011a5e281678c974b6dde43ca25fd405e14d"
)
MAX_PREFLIGHT_COST_USD = Decimal("0.003")
MAX_PREFLIGHT_BILLABLE_SIZE_BYTES = 3_000_000
PROJECTION_NAMES = (
    "exact",
    "without_sequence",
    "without_size",
    "without_sequence_and_size",
    "order_id_and_side",
    "order_id_only",
)
SAFE_ERROR_CODES = frozenset(
    {
        "github_actions_rerun_blocked",
        "unauthorized_push_parent",
        "missing_databento_api_key",
        "sdk_import_failed",
        "sdk_version_mismatch",
        "client_initialization_failed",
        "preflight_metadata_query_failed",
        "preflight_budget_rejected",
        "provider_download_failed",
        "download_empty",
        "metadata_mismatch",
        "classifier_failed",
        "unclassified_fail_closed",
    }
)

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")


class SafeClassifierFailure(Exception):
    def __init__(self, failure_phase: str, safe_error_code: str) -> None:
        super().__init__(safe_error_code)
        self.failure_phase = failure_phase
        self.safe_error_code = safe_error_code

    def mapping(self) -> dict[str, str]:
        return {
            "failure_phase": self.failure_phase,
            "safe_error_code": self.safe_error_code,
        }


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _verify_classifier_source() -> None:
    source = Path(str(classifier.__file__))
    if source.suffix != ".py" or file_sha256(source) != CLASSIFIER_SOURCE_FILE_SHA256:
        raise ValueError("frozen Fill/Cancel classifier source changed")


def validate_execution_authorization(payload: Mapping[str, object]) -> None:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "execution_authorization_id": EXECUTION_AUTHORIZATION_ID,
        "artifact_type": (
            "explicit_one_shot_databento_fill_cancel_classifier_authorization"
        ),
        "classifier_contract_id": CLASSIFIER_CONTRACT_ID,
        "classifier_contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "provider_purchase_authorized": True,
        "exact_request_count_authorized": 1,
        "hard_preflight_cost_ceiling_usd": "0.003",
        "hard_preflight_billable_size_ceiling_bytes": 3_000_000,
        "first_github_actions_attempt_only": True,
        "automatic_retry_authorized": False,
        "batch_or_live_endpoint_authorized": False,
        "raw_market_data_publication_authorized": False,
        "broker_or_order_change_authorized": False,
        "strategy_or_threshold_change_authorized": False,
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise ValueError(f"Fill/Cancel authorization {field} changed")
    parent_sha = payload.get("authorized_push_parent_sha")
    if not isinstance(parent_sha, str) or not _SHA40.fullmatch(parent_sha):
        raise ValueError("Fill/Cancel authorization parent SHA is invalid")
    statement = payload.get("explicit_user_authorization")
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError("Fill/Cancel explicit user authorization is required")
    claimed = payload.get("content_sha256")
    if not isinstance(claimed, str) or not _SHA64.fullmatch(claimed):
        raise ValueError("Fill/Cancel authorization hash is invalid")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("Fill/Cancel authorization fingerprint mismatch")


def load_execution_authorization(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Fill/Cancel authorization root must be an object")
    validate_execution_authorization(payload)
    return payload


def _run_preflight(
    client: HistoricalClient,
) -> tuple[dict[str, object], list[dict[str, str]]]:
    try:
        kwargs = _request_kwargs(REQUEST)
        size = _integer(client.metadata.get_billable_size(**kwargs), "billable size")
        cost = _decimal(client.metadata.get_cost(**kwargs), "quoted cost")
    except Exception:
        return (
            {
                "request_count_expected": 1,
                "request_count_quoted": 0,
                "quote_rows": [],
                "total_quoted_cost_usd": None,
                "total_billable_size_bytes": None,
                "hard_cost_ceiling_usd": format(MAX_PREFLIGHT_COST_USD, "f"),
                "hard_billable_size_ceiling_bytes": MAX_PREFLIGHT_BILLABLE_SIZE_BYTES,
                "preflight_passed": False,
            },
            [
                {
                    "failure_phase": "preflight",
                    "safe_error_code": "preflight_metadata_query_failed",
                }
            ],
        )
    passed = (
        cost <= MAX_PREFLIGHT_COST_USD
        and size <= MAX_PREFLIGHT_BILLABLE_SIZE_BYTES
    )
    errors = [] if passed else [
        {"failure_phase": "preflight", "safe_error_code": "preflight_budget_rejected"}
    ]
    quote_row: dict[str, object] = REQUEST.mapping()
    quote_row.update(
        {
            "quoted_cost_usd": format(cost, "f"),
            "billable_size_bytes": size,
        }
    )
    return (
        {
            "request_count_expected": 1,
            "request_count_quoted": 1,
            "quote_rows": [quote_row],
            "total_quoted_cost_usd": format(cost, "f"),
            "total_billable_size_bytes": size,
            "hard_cost_ceiling_usd": format(MAX_PREFLIGHT_COST_USD, "f"),
            "hard_billable_size_ceiling_bytes": MAX_PREFLIGHT_BILLABLE_SIZE_BYTES,
            "preflight_passed": passed,
        },
        errors,
    )


def _base_report(
    *,
    authorization: Mapping[str, object],
    generated_at: datetime,
    sdk_version: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "classifier_contract_id": CLASSIFIER_CONTRACT_ID,
        "classifier_contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "classifier_source_file_sha256": CLASSIFIER_SOURCE_FILE_SHA256,
        "execution_authorization_id": EXECUTION_AUTHORIZATION_ID,
        "execution_authorization_content_sha256": authorization["content_sha256"],
        "parent_failure_audit_id": PARENT_FAILURE_AUDIT_ID,
        "parent_failure_audit_content_sha256": PARENT_FAILURE_CONTENT_SHA256,
        "parent_failure_report_content_sha256": PARENT_REPORT_CONTENT_SHA256,
        "artifact_type": ARTIFACT_TYPE,
        "generated_at": _iso_z(generated_at),
        "provider": "databento",
        "dataset": DATASET,
        "schema": "mbo",
        "venue": "XNAS",
        "sdk_version": sdk_version,
        "provider_credential_persisted": False,
        "raw_market_data_persisted": False,
        "raw_market_data_uploaded": False,
        "raw_record_values_persisted": False,
        "feature_values_persisted": False,
        "batch_or_live_endpoint_called": False,
        "automatic_retry_attempted": False,
        "strategy_or_threshold_change_made": False,
        "broker_or_order_change_made": False,
        "actual_billing_known": False,
        "runtime_authority_created": False,
        "policy_promotion_eligible": False,
    }


def build_unavailable_report(
    contract: Mapping[str, object],
    parent_failure_audit: Mapping[str, object],
    authorization: Mapping[str, object],
    *,
    generated_at: datetime,
    sdk_version: str,
    failure_phase: str,
    safe_error_code: str,
) -> dict[str, object]:
    validate_classifier_contract(
        contract,
        parent_failure_audit=parent_failure_audit,
    )
    validate_parent_failure_audit(parent_failure_audit)
    validate_execution_authorization(authorization)
    report = _base_report(
        authorization=authorization,
        generated_at=generated_at,
        sdk_version=sdk_version,
    )
    report.update(
        {
            "preflight": {
                "request_count_expected": 1,
                "request_count_quoted": 0,
                "quote_rows": [],
                "total_quoted_cost_usd": None,
                "total_billable_size_bytes": None,
                "hard_cost_ceiling_usd": format(MAX_PREFLIGHT_COST_USD, "f"),
                "hard_billable_size_ceiling_bytes": MAX_PREFLIGHT_BILLABLE_SIZE_BYTES,
                "preflight_passed": False,
            },
            "timeseries_request_count": 0,
            "download": None,
            "classification_metrics": None,
            "errors": [SafeClassifierFailure(failure_phase, safe_error_code).mapping()],
            "raw_temp_directory_empty_before_cleanup": True,
            "raw_temp_directory_removed": True,
            "diagnostic_observation_complete": False,
            "classifier_succeeded": False,
            "safe_failure_classified": True,
        }
    )
    return _finish_report(report)


def _validate_metrics(metrics: Mapping[str, object]) -> None:
    count_fields = (
        "instrument_event_count",
        "fill_bearing_event_count",
        "fill_record_count",
        "cancel_record_count_in_fill_bearing_events",
        "fill_last_record_count",
        "fill_event_without_cancel_count",
        "multi_sequence_fill_event_count",
    )
    counts = {
        field: _integer(metrics.get(field), f"classification {field}")
        for field in count_fields
    }
    if counts["fill_bearing_event_count"] > counts["instrument_event_count"]:
        raise ValueError("Fill-bearing event count exceeds all events")
    if counts["fill_record_count"] < counts["fill_bearing_event_count"]:
        raise ValueError("Fill record count is inconsistent")
    if counts["fill_last_record_count"] > counts["fill_record_count"]:
        raise ValueError("Fill last-record count is inconsistent")
    for field in ("fill_event_without_cancel_count", "multi_sequence_fill_event_count"):
        if counts[field] > counts["fill_bearing_event_count"]:
            raise ValueError(f"classification {field} is inconsistent")
    for field in ("projection_overlap_counts", "projection_full_match_event_counts"):
        projections = _mapping(metrics.get(field), field)
        if len(projections) != len(PROJECTION_NAMES) or set(projections) != set(
            PROJECTION_NAMES
        ):
            raise ValueError(f"classification {field} changed")
        ceiling = (
            counts["fill_record_count"]
            if field == "projection_overlap_counts"
            else counts["fill_bearing_event_count"]
        )
        for name in PROJECTION_NAMES:
            if _integer(projections.get(name), f"{field}.{name}") > ceiling:
                raise ValueError(f"classification {field}.{name} is inconsistent")
    for field in (
        "raw_record_values_persisted",
        "feature_values_persisted",
        "runtime_authority_created",
    ):
        if metrics.get(field) is not False:
            raise ValueError(f"classification {field} must remain false")


def _download_and_classify(
    client: HistoricalClient,
    path: Path,
    runtime: RuntimeConstants,
) -> tuple[dict[str, object], dict[str, object]]:
    try:
        store = client.timeseries.get_range(path=str(path), **_request_kwargs(REQUEST))
    except Exception:
        raise SafeClassifierFailure("provider_download", "provider_download_failed") from None
    if not path.is_file() or path.stat().st_size <= 0:
        raise SafeClassifierFailure("downloaded_file", "download_empty")
    try:
        dataset = _metadata_value(getattr(store, "metadata", None), "dataset")
        schema = _metadata_value(getattr(store, "metadata", None), "schema")
    except Exception:
        raise SafeClassifierFailure("metadata", "metadata_mismatch") from None
    if dataset != DATASET.lower() or schema != "mbo":
        raise SafeClassifierFailure("metadata", "metadata_mismatch")
    try:
        metrics = classify_fill_cancel_structure(
            store,
            request=REQUEST,
            runtime=runtime,
        )
        _validate_metrics(metrics)
    except Exception:
        raise SafeClassifierFailure("classification", "classifier_failed") from None
    return (
        {
            "trading_date": REQUEST.trading_date,
            "symbol": REQUEST.symbol,
            "schema": REQUEST.schema,
            "ephemeral_file_sha256": file_sha256(path),
            "file_nonempty": True,
            "metadata_matches_request": True,
        },
        metrics,
    )


def run_fill_cancel_classifier_diagnostic(
    contract: Mapping[str, object],
    parent_failure_audit: Mapping[str, object],
    authorization: Mapping[str, object],
    client: HistoricalClient,
    *,
    generated_at: datetime,
    sdk_version: str,
    runtime: RuntimeConstants,
) -> dict[str, object]:
    validate_classifier_contract(
        contract,
        parent_failure_audit=parent_failure_audit,
    )
    validate_parent_failure_audit(parent_failure_audit)
    validate_execution_authorization(authorization)
    _verify_classifier_source()
    if sdk_version != SDK_VERSION:
        raise ValueError(f"Databento SDK version must be {SDK_VERSION}")
    preflight, errors = _run_preflight(client)
    report = _base_report(
        authorization=authorization,
        generated_at=generated_at,
        sdk_version=sdk_version,
    )
    report.update(
        {
            "preflight": preflight,
            "timeseries_request_count": 0,
            "download": None,
            "classification_metrics": None,
            "errors": errors,
            "raw_temp_directory_empty_before_cleanup": True,
            "raw_temp_directory_removed": True,
        }
    )
    if preflight.get("preflight_passed") is not True:
        report.update(
            {
                "diagnostic_observation_complete": False,
                "classifier_succeeded": False,
                "safe_failure_classified": bool(errors),
            }
        )
        return _finish_report(report)

    temp = tempfile.TemporaryDirectory(prefix="momentumbot-fill-cancel-classifier-v01-")
    temp_path = Path(temp.name)
    path = temp_path / "request-00.dbn.zst"
    try:
        try:
            report["timeseries_request_count"] = 1
            download, metrics = _download_and_classify(client, path, runtime)
            report["download"] = download
            report["classification_metrics"] = metrics
        except SafeClassifierFailure as exc:
            errors.append(exc.mapping())
        except Exception:
            errors.append(
                {
                    "failure_phase": "completion",
                    "safe_error_code": "unclassified_fail_closed",
                }
            )
        finally:
            path.unlink(missing_ok=True)
    finally:
        report["raw_temp_directory_empty_before_cleanup"] = not any(
            temp_path.iterdir()
        )
        temp_name = temp.name
        temp.cleanup()
        report["raw_temp_directory_removed"] = not Path(temp_name).exists()
    succeeded = report["classification_metrics"] is not None and not errors
    report.update(
        {
            "diagnostic_observation_complete": succeeded or bool(errors),
            "classifier_succeeded": succeeded,
            "safe_failure_classified": bool(errors)
            and all(row.get("safe_error_code") in SAFE_ERROR_CODES for row in errors),
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


def validate_classifier_report(payload: Mapping[str, object]) -> None:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "classifier_contract_id": CLASSIFIER_CONTRACT_ID,
        "classifier_contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "classifier_source_file_sha256": CLASSIFIER_SOURCE_FILE_SHA256,
        "parent_failure_audit_content_sha256": PARENT_FAILURE_CONTENT_SHA256,
        "parent_failure_report_content_sha256": PARENT_REPORT_CONTENT_SHA256,
        "artifact_type": ARTIFACT_TYPE,
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise ValueError(f"Fill/Cancel report {field} changed")
    for field in (
        "provider_credential_persisted",
        "raw_market_data_persisted",
        "raw_market_data_uploaded",
        "raw_record_values_persisted",
        "feature_values_persisted",
        "batch_or_live_endpoint_called",
        "automatic_retry_attempted",
        "strategy_or_threshold_change_made",
        "broker_or_order_change_made",
        "actual_billing_known",
        "runtime_authority_created",
        "policy_promotion_eligible",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"Fill/Cancel report {field} must remain false")
    if payload.get("raw_temp_directory_empty_before_cleanup") is not True:
        raise ValueError("Fill/Cancel temporary directory was not empty")
    if payload.get("raw_temp_directory_removed") is not True:
        raise ValueError("Fill/Cancel temporary directory was not removed")
    if _integer(payload.get("timeseries_request_count"), "timeseries request count") > 1:
        raise ValueError("Fill/Cancel request count exceeded authorization")
    forbidden_keys = {
        "raw_records",
        "record_values",
        "order_id",
        "instrument_id",
        "publisher_id",
        "price",
        "size",
        "levels",
        "temporary_path",
        "provider_error_message",
        "exception_message",
        "error_message",
        "ross_action",
        "ross_label",
        "pnl",
        "later_price",
    }
    if set(_walk_keys(payload)) & forbidden_keys:
        raise ValueError("Fill/Cancel report contains a prohibited field")
    preflight = _mapping(payload.get("preflight"), "preflight")
    if preflight.get("request_count_expected") != 1:
        raise ValueError("Fill/Cancel preflight request count changed")
    if preflight.get("hard_cost_ceiling_usd") != "0.003":
        raise ValueError("Fill/Cancel preflight cost ceiling changed")
    if preflight.get("hard_billable_size_ceiling_bytes") != 3_000_000:
        raise ValueError("Fill/Cancel preflight size ceiling changed")
    errors = payload.get("errors")
    if not isinstance(errors, list) or len(errors) > 1:
        raise ValueError("Fill/Cancel report errors are invalid")
    if errors:
        error = _mapping(errors[0], "error")
        if set(error) != {"failure_phase", "safe_error_code"}:
            raise ValueError("Fill/Cancel report error contains an unregistered field")
        if error.get("safe_error_code") not in SAFE_ERROR_CODES:
            raise ValueError("Fill/Cancel report error code is not allowlisted")
    succeeded = payload.get("classifier_succeeded") is True
    request_count = int(payload.get("timeseries_request_count", 0))
    if succeeded:
        if request_count != 1 or errors or payload.get("download") is None:
            raise ValueError("successful Fill/Cancel report is inconsistent")
        metrics = _mapping(payload.get("classification_metrics"), "classification metrics")
        _validate_metrics(metrics)
    elif payload.get("safe_failure_classified") is True:
        if len(errors) != 1 or payload.get("classification_metrics") is not None:
            raise ValueError("classified Fill/Cancel report is inconsistent")
        if preflight.get("preflight_passed") is True and request_count != 1:
            raise ValueError("attempted Fill/Cancel report is inconsistent")
        if preflight.get("preflight_passed") is not True and request_count != 0:
            raise ValueError("preflight Fill/Cancel report is inconsistent")
    else:
        raise ValueError("Fill/Cancel report lacks a terminal outcome")
    claimed = payload.get("content_sha256")
    if not isinstance(claimed, str) or not _SHA64.fullmatch(claimed):
        raise ValueError("Fill/Cancel report content hash is invalid")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("Fill/Cancel report fingerprint mismatch")


__all__ = [
    "ARTIFACT_TYPE",
    "CLASSIFIER_SOURCE_FILE_SHA256",
    "EXECUTION_AUTHORIZATION_ID",
    "MAX_PREFLIGHT_BILLABLE_SIZE_BYTES",
    "MAX_PREFLIGHT_COST_USD",
    "PROJECTION_NAMES",
    "build_unavailable_report",
    "load_execution_authorization",
    "run_fill_cancel_classifier_diagnostic",
    "validate_classifier_report",
    "validate_execution_authorization",
]
