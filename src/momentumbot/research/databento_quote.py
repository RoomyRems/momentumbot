from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from zoneinfo import ZoneInfo

from momentumbot.research.microstructure_contract import (
    canonical_fingerprint,
    load_level2_registration,
)


SCHEMA_VERSION = 1
QUOTE_CONTRACT_ID = "databento-microstructure-metadata-quote-v0.1"
ARTIFACT_TYPE = "sanitized_databento_metadata_and_exact_cost_quote"
PARENT_CONTRACT_ID = "level2-tape-feasibility-v0.1"
PARENT_CONTENT_SHA256 = (
    "6d3a41d6bde3844900bc880632d8bc9d6c5f7b787edd5f0c302a709dcb9c1bf1"
)
DATASET = "XNAS.ITCH"
SDK_VERSION = "0.83.0"
REQUIRED_SCHEMAS = ("mbo", "mbp-10", "trades", "definition", "status")
SMOKE_CASES = (
    ("2026-07-10", "INTJ"),
    ("2026-07-10", "EQPT"),
    ("2026-07-20", "AMC"),
    ("2026-07-10", "GMM"),
)
MAX_SMOKE_QUOTE_USD = Decimal("12.50")
NEW_YORK = ZoneInfo("America/New_York")


class MetadataAPI(Protocol):
    def list_datasets(self, *, start_date: str, end_date: str) -> list[str]: ...

    def list_schemas(self, *, dataset: str) -> list[str]: ...

    def list_fields(
        self,
        *,
        schema: str,
        encoding: str,
    ) -> list[dict[str, Any]]: ...

    def list_unit_prices(self, *, dataset: str) -> list[dict[str, Any]]: ...

    def get_dataset_condition(
        self,
        *,
        dataset: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]: ...

    def get_dataset_range(self, *, dataset: str) -> dict[str, Any]: ...

    def get_billable_size(
        self,
        *,
        dataset: str,
        start: str,
        end: str,
        symbols: list[str],
        schema: str,
        stype_in: str,
    ) -> int: ...

    def get_cost(
        self,
        *,
        dataset: str,
        start: str,
        end: str,
        symbols: list[str],
        schema: str,
        stype_in: str,
    ) -> float: ...


class SymbologyAPI(Protocol):
    def resolve(
        self,
        *,
        dataset: str,
        symbols: list[str],
        stype_in: str,
        stype_out: str,
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]: ...


class HistoricalClient(Protocol):
    metadata: MetadataAPI
    symbology: SymbologyAPI


@dataclass(frozen=True, slots=True)
class QuoteRequest:
    trading_date: str
    symbol: str
    dataset: str
    schema: str
    start: str
    end: str
    stype_in: str = "raw_symbol"

    def mapping(self) -> dict[str, str]:
        return asdict(self)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _parse_date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite non-negative number")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a finite non-negative number") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{field} must be a finite non-negative number")
    return parsed


def _iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _window(trading_date: date, schema: str) -> tuple[datetime, datetime]:
    utc_day_start = datetime.combine(trading_date, time(), tzinfo=UTC)
    local_end = datetime.combine(trading_date, time(10, 10), tzinfo=NEW_YORK)
    if schema == "mbo":
        return utc_day_start, local_end.astimezone(UTC)
    if schema in {"mbp-10", "trades"}:
        local_start = datetime.combine(trading_date, time(6, 50), tzinfo=NEW_YORK)
        return local_start.astimezone(UTC), local_end.astimezone(UTC)
    if schema in {"definition", "status"}:
        return utc_day_start, utc_day_start + timedelta(days=1)
    raise ValueError(f"unsupported quote schema {schema}")


def build_quote_requests(
    contract: Mapping[str, object],
) -> tuple[QuoteRequest, ...]:
    validate_quote_contract(contract)
    requests: list[QuoteRequest] = []
    for trading_date_value, symbol in SMOKE_CASES:
        trading_date = date.fromisoformat(trading_date_value)
        for schema in REQUIRED_SCHEMAS:
            start, end = _window(trading_date, schema)
            if any(
                value.second != 0 or value.microsecond != 0 or value.minute % 10 != 0
                for value in (start, end)
            ):
                raise ValueError("quote windows must remain aligned to ten minutes")
            requests.append(
                QuoteRequest(
                    trading_date=trading_date_value,
                    symbol=symbol,
                    dataset=DATASET,
                    schema=schema,
                    start=_iso_z(start),
                    end=_iso_z(end),
                )
            )
    return tuple(requests)


def validate_quote_contract(
    payload: Mapping[str, object],
    *,
    parent: Mapping[str, object] | None = None,
) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported Databento quote schema")
    if payload.get("quote_contract_id") != QUOTE_CONTRACT_ID:
        raise ValueError("unexpected Databento quote contract")
    if payload.get("artifact_type") != "preregistered_metadata_only_provider_quote":
        raise ValueError("unexpected Databento quote artifact type")

    claimed = payload.get("content_sha256")
    if not isinstance(claimed, str) or len(claimed) != 64:
        raise ValueError("quote contract content_sha256 is invalid")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("Databento quote contract content fingerprint mismatch")

    parent_binding = _mapping(payload.get("parent_level2_contract"), "parent_level2_contract")
    if parent_binding.get("contract_id") != PARENT_CONTRACT_ID:
        raise ValueError("Level 2 parent contract changed")
    if parent_binding.get("content_sha256") != PARENT_CONTENT_SHA256:
        raise ValueError("Level 2 parent content hash changed")
    if parent is not None:
        if parent.get("contract_id") != PARENT_CONTRACT_ID:
            raise ValueError("loaded Level 2 parent contract changed")
        if parent.get("content_sha256") != PARENT_CONTENT_SHA256:
            raise ValueError("loaded Level 2 parent content hash changed")

    authorization = _mapping(payload.get("authorization"), "authorization")
    expected_authorization = {
        "metadata_queries_authorized": True,
        "metadata_queries_billable": False,
        "timeseries_download_authorized": False,
        "batch_job_authorized": False,
        "broad_history_download_authorized": False,
        "broker_or_order_change_authorized": False,
        "reported_new_user_credit_usd": "125",
        "max_future_smoke_download_quote_usd": "12.50",
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

    schemas = payload.get("required_schemas")
    if schemas != list(REQUIRED_SCHEMAS):
        raise ValueError("required Databento schemas changed")
    cases = payload.get("smoke_cases")
    if not isinstance(cases, list):
        raise ValueError("smoke_cases must be a list")
    observed_cases = tuple(
        (
            str(_mapping(item, "smoke case").get("trading_date")),
            str(_mapping(item, "smoke case").get("symbol")),
        )
        for item in cases
    )
    if observed_cases != SMOKE_CASES:
        raise ValueError("Databento smoke cases changed")

    windows = _mapping(payload.get("quote_windows"), "quote_windows")
    expected_windows = {
        "mbo": "00:00 UTC through 10:10 America/New_York",
        "mbp-10": "06:50 through 10:10 America/New_York",
        "trades": "06:50 through 10:10 America/New_York",
        "definition": "full UTC trading-date day",
        "status": "full UTC trading-date day",
        "alignment": "all starts and ends are exact ten-minute boundaries",
    }
    for field, expected in expected_windows.items():
        if windows.get(field) != expected:
            raise ValueError(f"quote_windows.{field} changed")

    prohibited = payload.get("prohibited_calls")
    if prohibited != [
        "historical.timeseries.get_range",
        "historical.batch.submit_job",
        "historical.batch.download",
        "live.subscribe",
    ]:
        raise ValueError("prohibited provider call surface changed")


def load_quote_contract(
    path: str | Path,
    *,
    parent_path: str | Path,
) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Databento quote contract root must be an object")
    parent = load_level2_registration(parent_path)
    validate_quote_contract(payload, parent=parent)
    return payload


def _json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _field_summary(value: object) -> dict[str, object]:
    rows = value if isinstance(value, list) else []
    names = sorted(
        {
            str(row["name"])
            for row in rows
            if isinstance(row, Mapping) and row.get("name") not in (None, "")
        }
    )
    return {"record_count": len(rows), "field_names": names}


def _resolution_summary(value: object, symbol: str) -> dict[str, object]:
    payload = value if isinstance(value, Mapping) else {}
    result = payload.get("result")
    result_map = result if isinstance(result, Mapping) else {}
    not_found = payload.get("not_found")
    not_found_values = list(not_found) if isinstance(not_found, list) else []
    partial = payload.get("partial")
    partial_values = list(partial) if isinstance(partial, list) else []
    mapping_value = result_map.get(symbol)
    mapping_count = len(mapping_value) if isinstance(mapping_value, list) else int(
        mapping_value is not None
    )
    return {
        "symbol": symbol,
        "resolved": mapping_count > 0 and symbol not in not_found_values,
        "mapping_count": mapping_count,
        "not_found": symbol in not_found_values,
        "partial": symbol in partial_values,
    }


def _capture(
    errors: list[dict[str, str]],
    stage: str,
    operation: Callable[[], object],
) -> object | None:
    try:
        return operation()
    except Exception as exc:  # provider failures must be preserved without messages
        errors.append({"stage": stage, "error_kind": type(exc).__name__})
        return None


def _finish_report(report: dict[str, object]) -> dict[str, object]:
    unsigned = {key: value for key, value in report.items() if key != "content_sha256"}
    report["content_sha256"] = canonical_fingerprint(unsigned)
    return report


def build_unavailable_report(
    contract: Mapping[str, object],
    *,
    generated_at: datetime,
    error_stage: str,
    error_kind: str,
) -> dict[str, object]:
    validate_quote_contract(contract)
    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "quote_contract_id": QUOTE_CONTRACT_ID,
        "artifact_type": ARTIFACT_TYPE,
        "generated_at": _iso_z(generated_at),
        "parent_level2_content_sha256": PARENT_CONTENT_SHA256,
        "provider": "databento",
        "dataset": DATASET,
        "provider_credential_persisted": False,
        "raw_market_data_persisted": False,
        "timeseries_or_batch_endpoint_called": False,
        "metadata_query_cost_usd": "0",
        "quote_rows": [],
        "errors": [{"stage": error_stage, "error_kind": error_kind}],
        "g0_quote_passed": False,
        "download_authorized_by_this_artifact": False,
    }
    return _finish_report(report)


def run_metadata_quote(
    contract: Mapping[str, object],
    client: HistoricalClient,
    *,
    generated_at: datetime,
    sdk_version: str,
) -> dict[str, object]:
    validate_quote_contract(contract)
    if sdk_version != SDK_VERSION:
        raise ValueError(f"Databento SDK version must be {SDK_VERSION}")

    requests = build_quote_requests(contract)
    errors: list[dict[str, str]] = []
    minimum_date = min(date.fromisoformat(value) for value, _symbol in SMOKE_CASES)
    maximum_date = max(date.fromisoformat(value) for value, _symbol in SMOKE_CASES)
    exclusive_end_date = maximum_date + timedelta(days=1)

    datasets = _capture(
        errors,
        "metadata.list_datasets",
        lambda: client.metadata.list_datasets(
            start_date=minimum_date.isoformat(),
            end_date=exclusive_end_date.isoformat(),
        ),
    )
    schemas = _capture(
        errors,
        "metadata.list_schemas",
        lambda: client.metadata.list_schemas(dataset=DATASET),
    )
    dataset_range = _capture(
        errors,
        "metadata.get_dataset_range",
        lambda: client.metadata.get_dataset_range(dataset=DATASET),
    )
    dataset_conditions = _capture(
        errors,
        "metadata.get_dataset_condition",
        lambda: client.metadata.get_dataset_condition(
            dataset=DATASET,
            start_date=minimum_date.isoformat(),
            end_date=maximum_date.isoformat(),
        ),
    )
    unit_prices = _capture(
        errors,
        "metadata.list_unit_prices",
        lambda: client.metadata.list_unit_prices(dataset=DATASET),
    )

    field_summaries: dict[str, object] = {}
    for schema in REQUIRED_SCHEMAS:
        fields = _capture(
            errors,
            f"metadata.list_fields:{schema}",
            lambda schema=schema: client.metadata.list_fields(
                schema=schema,
                encoding="dbn",
            ),
        )
        field_summaries[schema] = _field_summary(fields)

    resolutions: list[dict[str, object]] = []
    for trading_date_value, symbol in SMOKE_CASES:
        trading_date = date.fromisoformat(trading_date_value)
        resolved = _capture(
            errors,
            f"symbology.resolve:{trading_date_value}:{symbol}",
            lambda trading_date=trading_date, symbol=symbol: client.symbology.resolve(
                dataset=DATASET,
                symbols=[symbol],
                stype_in="raw_symbol",
                stype_out="instrument_id",
                start_date=trading_date.isoformat(),
                end_date=(trading_date + timedelta(days=1)).isoformat(),
            ),
        )
        resolutions.append(_resolution_summary(resolved, symbol))

    quote_rows: list[dict[str, object]] = []
    total_cost = Decimal("0")
    total_size = 0
    complete_quotes = True
    for request in requests:
        kwargs = {
            "dataset": request.dataset,
            "start": request.start,
            "end": request.end,
            "symbols": [request.symbol],
            "schema": request.schema,
            "stype_in": request.stype_in,
        }
        size = _capture(
            errors,
            f"metadata.get_billable_size:{request.trading_date}:{request.symbol}:{request.schema}",
            lambda kwargs=kwargs: client.metadata.get_billable_size(**kwargs),
        )
        cost = _capture(
            errors,
            f"metadata.get_cost:{request.trading_date}:{request.symbol}:{request.schema}",
            lambda kwargs=kwargs: client.metadata.get_cost(**kwargs),
        )
        row = request.mapping()
        try:
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                raise ValueError("billable size must be a non-negative integer")
            parsed_cost = _decimal(cost, "quoted cost")
        except ValueError as exc:
            errors.append(
                {
                    "stage": (
                        f"quote_validation:{request.trading_date}:"
                        f"{request.symbol}:{request.schema}"
                    ),
                    "error_kind": type(exc).__name__,
                }
            )
            complete_quotes = False
            row.update({"billable_size_bytes": None, "quoted_cost_usd": None})
        else:
            total_size += size
            total_cost += parsed_cost
            row.update(
                {
                    "billable_size_bytes": size,
                    "quoted_cost_usd": format(parsed_cost, "f"),
                }
            )
        quote_rows.append(row)

    dataset_available = isinstance(datasets, list) and DATASET in datasets
    schema_values = set(schemas) if isinstance(schemas, list) else set()
    schemas_available = all(schema in schema_values for schema in REQUIRED_SCHEMAS)
    all_symbols_resolved = len(resolutions) == len(SMOKE_CASES) and all(
        row["resolved"] is True for row in resolutions
    )
    all_field_metadata_observed = all(
        isinstance(field_summaries[schema], Mapping)
        and int(field_summaries[schema].get("record_count", 0)) > 0
        for schema in REQUIRED_SCHEMAS
    )
    conditions_observed = isinstance(dataset_conditions, list) and bool(dataset_conditions)
    range_observed = isinstance(dataset_range, Mapping) and bool(dataset_range)
    unit_prices_observed = isinstance(unit_prices, list) and bool(unit_prices)
    quote_inside_budget = complete_quotes and total_cost <= MAX_SMOKE_QUOTE_USD

    pass_conditions = {
        "dataset_available_for_requested_range": dataset_available,
        "all_required_schemas_available": schemas_available,
        "all_required_schema_field_metadata_observed": all_field_metadata_observed,
        "dataset_range_observed": range_observed,
        "dataset_conditions_observed": conditions_observed,
        "unit_prices_observed": unit_prices_observed,
        "all_four_symbols_resolved_point_in_time": all_symbols_resolved,
        "all_twenty_quotes_complete": complete_quotes and len(quote_rows) == 20,
        "conservative_five_schema_sum_within_12_50_usd": quote_inside_budget,
        "no_provider_error": not errors,
        "no_market_data_endpoint_called": True,
    }
    g0_quote_passed = all(pass_conditions.values())
    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "quote_contract_id": QUOTE_CONTRACT_ID,
        "artifact_type": ARTIFACT_TYPE,
        "generated_at": _iso_z(generated_at),
        "parent_level2_content_sha256": PARENT_CONTENT_SHA256,
        "provider": "databento",
        "dataset": DATASET,
        "venue_scope": "single_venue_nasdaq_not_consolidated_national_depth",
        "sdk_version": sdk_version,
        "provider_credential_persisted": False,
        "raw_market_data_persisted": False,
        "timeseries_or_batch_endpoint_called": False,
        "metadata_query_cost_usd": "0",
        "reported_new_user_credit_usd": "125",
        "future_smoke_download_ceiling_usd": "12.50",
        "dataset_range": _json_safe(dataset_range),
        "dataset_condition": _json_safe(dataset_conditions),
        "unit_prices": _json_safe(unit_prices),
        "field_summaries": field_summaries,
        "symbology_resolutions": resolutions,
        "quote_rows": quote_rows,
        "quote_metrics": {
            "request_count": len(quote_rows),
            "total_billable_size_bytes": total_size if complete_quotes else None,
            "conservative_total_quoted_cost_usd": (
                format(total_cost, "f") if complete_quotes else None
            ),
            "aggregation_note": (
                "Sum of five separately quoted schemas for every smoke case; this is a "
                "conservative ceiling and not an acquisition decision."
            ),
        },
        "pass_conditions": pass_conditions,
        "errors": errors,
        "g0_quote_passed": g0_quote_passed,
        "download_authorized_by_this_artifact": False,
    }
    return _finish_report(report)


def validate_quote_report(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported quote report schema")
    if payload.get("quote_contract_id") != QUOTE_CONTRACT_ID:
        raise ValueError("unexpected quote report contract")
    if payload.get("artifact_type") != ARTIFACT_TYPE:
        raise ValueError("unexpected quote report artifact type")
    for field in (
        "provider_credential_persisted",
        "raw_market_data_persisted",
        "timeseries_or_batch_endpoint_called",
        "download_authorized_by_this_artifact",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must remain false")
    if payload.get("metadata_query_cost_usd") != "0":
        raise ValueError("metadata query cost must remain zero")
    claimed = payload.get("content_sha256")
    if not isinstance(claimed, str) or len(claimed) != 64:
        raise ValueError("quote report content hash is invalid")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("quote report content fingerprint mismatch")


__all__ = [
    "ARTIFACT_TYPE",
    "DATASET",
    "MAX_SMOKE_QUOTE_USD",
    "QUOTE_CONTRACT_ID",
    "REQUIRED_SCHEMAS",
    "SDK_VERSION",
    "SMOKE_CASES",
    "QuoteRequest",
    "build_quote_requests",
    "build_unavailable_report",
    "load_quote_contract",
    "run_metadata_quote",
    "validate_quote_contract",
    "validate_quote_report",
]
