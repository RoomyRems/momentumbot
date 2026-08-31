"""Bounded provider-availability gate for the sealed historical panel.

The gate permits four metadata/minimal-session calls and persists no raw market
or reference rows.  It does not paginate, download the historical universe,
request candidate execution data, access an account, or submit an order.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Callable, Mapping, Protocol, Sequence
from zoneinfo import ZoneInfo

from momentumbot.research.sealed_historical_walk_forward import (
    CONTRACT_CONTENT_SHA256,
    CONTRACT_ID,
    canonical_fingerprint,
    load_json_object,
)


SCHEMA_VERSION = 1
AUTHORIZATION_ID = "sealed-historical-provider-availability-v0.1"
ARTIFACT_TYPE = "bounded_sanitized_historical_provider_availability_probe"
AUTHORIZATION_CONTENT_SHA256 = (
    "a985794bc0856aa37d8a79ba43f068994329e4950b60cb1d86ba5436a1f77295"
)
DATASET = "XNAS.ITCH"
NEW_YORK = ZoneInfo("America/New_York")
SELECTED_DATES = (
    "2025-05-30",
    "2025-06-02",
    "2025-06-03",
    "2025-06-04",
    "2025-06-05",
    "2025-06-06",
    "2025-06-09",
    "2025-06-10",
    "2025-06-11",
    "2025-06-12",
    "2025-06-13",
    "2025-06-16",
    "2025-06-17",
    "2025-06-18",
    "2025-06-20",
    "2025-06-23",
    "2025-06-24",
    "2025-06-25",
    "2025-06-26",
    "2025-06-27",
    "2025-07-01",
    "2025-07-02",
    "2025-07-07",
    "2025-07-08",
    "2025-07-10",
    "2025-07-11",
    "2025-07-14",
    "2025-07-15",
    "2025-07-16",
    "2025-07-17",
)
_SHA256 = re.compile(r"^[0-9a-f]{40}$")
_FORBIDDEN_REPORT_KEYS = {
    "api_key",
    "api_secret",
    "bars",
    "captions",
    "close",
    "high",
    "low",
    "name",
    "open",
    "results",
    "title",
    "ticker",
    "volume",
}


class DatabentoMetadata(Protocol):
    def get_dataset_range(self, *, dataset: str) -> Mapping[str, object]: ...


class DatabentoClient(Protocol):
    metadata: DatabentoMetadata


ProviderRequest = Callable[[Mapping[str, object]], Mapping[str, object]]


def freeze(payload: Mapping[str, object]) -> dict[str, object]:
    result = dict(payload)
    result["content_sha256"] = canonical_fingerprint(payload)
    return result


def _walk_keys(value: object) -> set[str]:
    output: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            output.add(str(key).lower())
            output.update(_walk_keys(child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            output.update(_walk_keys(child))
    return output


def _aware(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min, tzinfo=timezone.utc)
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    # Databento's metadata endpoint may return date-only or naive ISO values.
    # Interpreting those metadata boundaries as UTC does not alter market rows;
    # it only makes the dataset-range coverage test deterministic.
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def load_authorization(path: str | Path) -> dict[str, object]:
    payload = load_json_object(path)
    validate_authorization(payload)
    return payload


def validate_authorization(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported provider-availability authorization schema")
    if payload.get("authorization_id") != AUTHORIZATION_ID:
        raise ValueError("unexpected provider-availability authorization ID")
    if payload.get("artifact_type") != (
        "preregistered_bounded_provider_availability_authorization"
    ):
        raise ValueError("unexpected provider-availability authorization type")
    claimed = payload.get("content_sha256")
    body = dict(payload)
    body.pop("content_sha256", None)
    if claimed != canonical_fingerprint(body):
        raise ValueError("provider-availability authorization content hash mismatch")
    if claimed != AUTHORIZATION_CONTENT_SHA256:
        raise ValueError("provider-availability authorization differs from frozen hash")
    parent = payload.get("frozen_parent")
    if parent != {
        "contract_id": CONTRACT_ID,
        "content_sha256": CONTRACT_CONTENT_SHA256,
        "selected_dates": list(SELECTED_DATES),
    }:
        raise ValueError("provider-availability parent binding mismatch")
    calls = payload.get("authorized_calls")
    if calls != {
        "alpaca_sip_spy_daily": {
            "maximum_calls": 1,
            "pagination_allowed": False,
            "raw_rows_persisted": False,
        },
        "databento_dataset_range": {
            "dataset": DATASET,
            "maximum_calls": 1,
            "metadata_only": True,
        },
        "massive_point_in_time_sample": {
            "dates": [SELECTED_DATES[0], SELECTED_DATES[-1]],
            "limit_per_call": 1,
            "maximum_calls": 2,
            "pagination_allowed": False,
            "raw_rows_persisted": False,
        },
        "maximum_total_calls": 4,
    }:
        raise ValueError("provider-availability call budget mismatch")
    prohibitions = payload.get("prohibitions")
    if prohibitions != [
        "account_or_broker_endpoint",
        "automatic_retry_or_rerun",
        "databento_timeseries_or_batch_download",
        "full_massive_pagination",
        "historical_universe_or_intraday_bulk_download",
        "news_or_sec_content_download",
        "paper_or_live_order",
        "transcript_record_value_read",
    ]:
        raise ValueError("provider-availability prohibitions changed")
    if payload.get("reported_incremental_cost_usd") != "0":
        raise ValueError("provider-availability gate must have zero quoted incremental cost")
    authority = payload.get("authority_boundary")
    if authority != {
        "full_data_acquisition_authorized": False,
        "live_order_authorized": False,
        "paper_order_authorized": False,
        "policy_promotion_eligible": False,
        "provider_probe_authorized": True,
    }:
        raise ValueError("provider-availability authority boundary mismatch")


def build_probe_plan(
    registration: Mapping[str, object],
    authorization: Mapping[str, object],
) -> dict[str, object]:
    validate_authorization(authorization)
    if registration.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected sealed historical registration")
    if registration.get("content_sha256") != CONTRACT_CONTENT_SHA256:
        raise ValueError("sealed historical registration hash mismatch")
    sampling = registration.get("sampling_contract")
    if not isinstance(sampling, Mapping) or sampling.get("selected_dates") != list(
        SELECTED_DATES
    ):
        raise ValueError("selected dates differ from the frozen provider probe")
    return {
        "authorization_id": AUTHORIZATION_ID,
        "authorization_content_sha256": authorization["content_sha256"],
        "registration_content_sha256": registration["content_sha256"],
        "alpaca": {
            "symbols": "SPY",
            "timeframe": "1Day",
            "start": "2025-05-29T00:00:00Z",
            "end": "2025-07-19T00:00:00Z",
            "feed": "sip",
            "adjustment": "raw",
            "asof": SELECTED_DATES[-1],
            "limit": 1000,
            "sort": "asc",
        },
        "massive": [
            {
                "market": "stocks",
                "locale": "us",
                "active": "true",
                "date": value,
                "order": "asc",
                "sort": "ticker",
                "limit": 1,
            }
            for value in (SELECTED_DATES[0], SELECTED_DATES[-1])
        ],
        "databento": {"dataset": DATASET, "method": "metadata.get_dataset_range"},
        "maximum_total_calls": 4,
    }


def _status(response: Mapping[str, object]) -> int | None:
    value = response.get("status")
    return value if isinstance(value, int) else None


def _summarize_alpaca(response: Mapping[str, object]) -> dict[str, object]:
    if response.get("ok") is not True:
        return {
            "ok": False,
            "status": _status(response),
            "error_kind": str(response.get("error_kind", "provider_request_failed")),
            "observed_selected_dates": [],
            "missing_selected_dates": list(SELECTED_DATES),
            "next_page_present": False,
        }
    payload = response.get("payload")
    if not isinstance(payload, Mapping):
        return {
            "ok": False,
            "status": _status(response),
            "error_kind": "invalid_payload_shape",
            "observed_selected_dates": [],
            "missing_selected_dates": list(SELECTED_DATES),
            "next_page_present": False,
        }
    raw_bars = payload.get("bars")
    symbol_rows = raw_bars.get("SPY") if isinstance(raw_bars, Mapping) else None
    rows = symbol_rows if isinstance(symbol_rows, list) else []
    observed: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        timestamp = _aware(row.get("t"))
        if timestamp is not None:
            observed.add(timestamp.astimezone(NEW_YORK).date().isoformat())
    matched = sorted(set(SELECTED_DATES) & observed)
    missing = sorted(set(SELECTED_DATES) - observed)
    next_page = bool(payload.get("next_page_token"))
    return {
        "ok": not missing and not next_page,
        "status": _status(response),
        "response_row_count": len(rows),
        "observed_selected_dates": matched,
        "missing_selected_dates": missing,
        "next_page_present": next_page,
        "bar_values_persisted": False,
    }


def _summarize_massive(
    response: Mapping[str, object], requested_date: str
) -> dict[str, object]:
    if response.get("ok") is not True:
        return {
            "requested_date": requested_date,
            "ok": False,
            "status": _status(response),
            "error_kind": str(response.get("error_kind", "provider_request_failed")),
        }
    payload = response.get("payload")
    results = payload.get("results") if isinstance(payload, Mapping) else None
    rows = [row for row in results if isinstance(row, Mapping)] if isinstance(results, list) else []
    fields = sorted({str(key) for row in rows for key in row})
    active = sum(row.get("active") is True for row in rows)
    next_page = bool(payload.get("next_url")) if isinstance(payload, Mapping) else False
    required = {"ticker", "active", "market", "locale", "primary_exchange", "type"}
    ok = len(rows) == 1 and active == 1 and required <= set(fields) and next_page
    return {
        "requested_date": requested_date,
        "ok": ok,
        "status": _status(response),
        "sample_row_count": len(rows),
        "result_fields": fields,
        "active_true_count": active,
        "next_page_present": next_page,
        "raw_rows_persisted": False,
    }


def _range_value(payload: Mapping[str, object], names: Sequence[str]) -> datetime | None:
    for name in names:
        parsed = _aware(payload.get(name))
        if parsed is not None:
            return parsed
    return None


def _summarize_databento(value: object) -> dict[str, object]:
    if isinstance(value, BaseException):
        return {"ok": False, "error_kind": type(value).__name__}
    if not isinstance(value, Mapping):
        return {"ok": False, "error_kind": "invalid_payload_shape"}
    start = _range_value(value, ("start", "start_date", "start_time", "begin"))
    end = _range_value(value, ("end", "end_date", "end_time", "finish"))
    first = datetime.fromisoformat(f"{SELECTED_DATES[0]}T00:00:00+00:00")
    final = datetime.fromisoformat(f"{SELECTED_DATES[-1]}T23:59:59+00:00")
    covers = start is not None and end is not None and start <= first and end >= final
    return {
        "ok": covers,
        "dataset": DATASET,
        "range_start": start.isoformat() if start is not None else None,
        "range_end": end.isoformat() if end is not None else None,
        "selected_interval_covered": covers,
        "metadata_fields": sorted(str(key) for key in value),
        "raw_market_data_persisted": False,
    }


def run_probe(
    *,
    registration: Mapping[str, object],
    authorization: Mapping[str, object],
    alpaca_request: ProviderRequest,
    massive_request: ProviderRequest,
    databento_client: DatabentoClient,
    repository: str,
    authorization_commit_sha: str,
    workflow_run_id: str,
    workflow_run_attempt: int,
) -> dict[str, object]:
    plan = build_probe_plan(registration, authorization)
    if repository != "RoomyRems/momentumbot":
        raise ValueError("provider probe repository mismatch")
    if _SHA256.fullmatch(authorization_commit_sha) is None:
        raise ValueError("authorization commit must be a full Git SHA")
    if workflow_run_attempt != 1:
        raise ValueError("provider availability probe is one attempt only")
    alpaca_response = alpaca_request(plan["alpaca"])
    massive_rows = [
        _summarize_massive(massive_request(request), str(request["date"]))
        for request in plan["massive"]
    ]
    try:
        databento_value: object = databento_client.metadata.get_dataset_range(
            dataset=DATASET
        )
    except Exception as exc:  # sanitized below; provider message is never retained
        databento_value = exc
    alpaca = _summarize_alpaca(alpaca_response)
    databento = _summarize_databento(databento_value)
    call_counts = {
        "alpaca": 1,
        "massive": len(massive_rows),
        "databento": 1,
        "total": 2 + len(massive_rows),
    }
    passed = (
        alpaca.get("ok") is True
        and all(row.get("ok") is True for row in massive_rows)
        and databento.get("ok") is True
        and call_counts["total"] <= int(plan["maximum_total_calls"])
    )
    report = freeze(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": ARTIFACT_TYPE,
            "authorization_id": AUTHORIZATION_ID,
            "authorization_content_sha256": authorization["content_sha256"],
            "registration_content_sha256": registration["content_sha256"],
            "selected_dates": list(SELECTED_DATES),
            "workflow_provenance": {
                "repository": repository,
                "authorization_commit_sha": authorization_commit_sha,
                "workflow_run_id": str(workflow_run_id),
                "workflow_run_attempt": workflow_run_attempt,
            },
            "call_counts": call_counts,
            "maximum_authorized_call_count": plan["maximum_total_calls"],
            "probes": {
                "alpaca_sip_session_calendar": alpaca,
                "massive_point_in_time_endpoints": massive_rows,
                "databento_dataset_range": databento,
            },
            "availability_gate_passed": passed,
            "incremental_cost_usd": "0",
            "provider_error_messages_persisted": False,
            "provider_credentials_persisted": False,
            "raw_provider_rows_persisted": False,
            "historical_universe_downloaded": False,
            "intraday_market_data_downloaded": False,
            "databento_timeseries_or_batch_called": False,
            "transcript_record_values_read": False,
            "account_or_broker_endpoint_called": False,
            "order_submitted": False,
            "automatic_retry_or_rerun_attempted": False,
            "next_gate": (
                "register an exact full-universe acquisition plan if and only if this availability gate passes"
                if passed
                else "preserve the safe failure and do not acquire or substitute data"
            ),
        }
    )
    validate_report(report, authorization, registration)
    return report


def validate_report(
    report: Mapping[str, object],
    authorization: Mapping[str, object],
    registration: Mapping[str, object],
) -> None:
    validate_authorization(authorization)
    if report.get("artifact_type") != ARTIFACT_TYPE:
        raise ValueError("unexpected provider availability report type")
    claimed = report.get("content_sha256")
    body = dict(report)
    body.pop("content_sha256", None)
    if claimed != canonical_fingerprint(body):
        raise ValueError("provider availability report content hash mismatch")
    if report.get("authorization_content_sha256") != authorization.get(
        "content_sha256"
    ):
        raise ValueError("provider availability authorization binding mismatch")
    if report.get("registration_content_sha256") != registration.get(
        "content_sha256"
    ):
        raise ValueError("provider availability registration binding mismatch")
    if report.get("selected_dates") != list(SELECTED_DATES):
        raise ValueError("provider availability selected dates mismatch")
    provenance = report.get("workflow_provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("provider availability provenance is missing")
    if provenance.get("repository") != "RoomyRems/momentumbot":
        raise ValueError("provider availability provenance repository mismatch")
    if _SHA256.fullmatch(str(provenance.get("authorization_commit_sha", ""))) is None:
        raise ValueError("provider availability provenance commit is invalid")
    if provenance.get("workflow_run_attempt") != 1:
        raise ValueError("provider availability provenance attempt changed")
    calls = report.get("call_counts")
    if not isinstance(calls, Mapping) or calls != {
        "alpaca": 1,
        "massive": 2,
        "databento": 1,
        "total": 4,
    }:
        raise ValueError("provider availability must make exactly four bounded calls")
    if report.get("maximum_authorized_call_count") != 4:
        raise ValueError("provider availability call ceiling changed")
    probes = report.get("probes")
    if not isinstance(probes, Mapping):
        raise ValueError("provider availability probes are missing")
    alpaca = probes.get("alpaca_sip_session_calendar")
    massive = probes.get("massive_point_in_time_endpoints")
    databento = probes.get("databento_dataset_range")
    if not isinstance(alpaca, Mapping):
        raise ValueError("Alpaca availability summary is missing")
    if not isinstance(alpaca.get("next_page_present"), bool):
        raise ValueError("Alpaca availability pagination summary is missing")
    if not isinstance(massive, list) or len(massive) != 2:
        raise ValueError("Massive availability summaries changed")
    if [row.get("requested_date") for row in massive if isinstance(row, Mapping)] != [
        SELECTED_DATES[0],
        SELECTED_DATES[-1],
    ]:
        raise ValueError("Massive availability sample dates changed")
    if any(not isinstance(row, Mapping) for row in massive):
        raise ValueError("Massive availability summary shape changed")
    if not isinstance(databento, Mapping):
        raise ValueError("Databento availability summary changed")
    if databento.get("ok") is True and databento.get("dataset") != DATASET:
        raise ValueError("Databento availability dataset changed")
    passed = (
        alpaca.get("ok") is True
        and all(row.get("ok") is True for row in massive)
        and databento.get("ok") is True
    )
    if report.get("availability_gate_passed") is not passed:
        raise ValueError("provider availability gate conclusion is inconsistent")
    for field, expected in {
        "incremental_cost_usd": "0",
        "provider_error_messages_persisted": False,
        "provider_credentials_persisted": False,
        "raw_provider_rows_persisted": False,
        "historical_universe_downloaded": False,
        "intraday_market_data_downloaded": False,
        "databento_timeseries_or_batch_called": False,
        "transcript_record_values_read": False,
        "account_or_broker_endpoint_called": False,
        "order_submitted": False,
        "automatic_retry_or_rerun_attempted": False,
    }.items():
        if report.get(field) != expected:
            raise ValueError(f"provider availability report changed {field}")
    forbidden = _walk_keys(report) & _FORBIDDEN_REPORT_KEYS
    if forbidden:
        raise ValueError(f"provider availability report leaked raw fields: {sorted(forbidden)}")


def write_json_once(path: str | Path, payload: Mapping[str, object]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(f"refusing to overwrite provider probe report: {target}")
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
