"""Exact, separately authorized acquisition of prospective L1/status inputs.

The registered harness is inert.  A later dynamic authorization can be built
only from an exact opportunity-freeze bundle and its successful metadata quote.
An authorized first workflow attempt requotes every request before downloading
the unchanged request manifest once, deletes temporary DBN files, and emits
only the minimal normalized capture defined by
``prospective-market-input-capture-v0.1``.
"""

from __future__ import annotations

import hashlib
import json
import operator
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from momentumbot.research.account_chronological_integration import (
    PANEL_ID,
    REGISTERED_DATES,
)
from momentumbot.research.microstructure_contract import canonical_fingerprint
from momentumbot.research.prospective_market_input_capture import (
    CONTRACT_CONTENT_SHA256 as CAPTURE_CONTRACT_CONTENT_SHA256,
    CONTRACT_ID as CAPTURE_CONTRACT_ID,
    build_market_input_capture,
    validate_capture_contract,
    validate_market_input_capture,
)
from momentumbot.research.prospective_market_input_quote import (
    CONTRACT_CONTENT_SHA256 as QUOTE_CONTRACT_CONTENT_SHA256,
    CONTRACT_ID as QUOTE_CONTRACT_ID,
    DATASET,
    EXPECTED_REPOSITORY,
    SCHEMAS,
    SDK_VERSION,
    ValidatedParentBundle,
    validate_parent_bundle,
    validate_quote_authorization,
    validate_quote_contract,
    validate_quote_report,
)
from momentumbot.research.prospective_opportunity_freeze import (
    CONTRACT_CONTENT_SHA256 as FREEZE_CONTRACT_CONTENT_SHA256,
    CONTRACT_ID as FREEZE_CONTRACT_ID,
)


SCHEMA_VERSION = 1
CONTRACT_ID = "prospective-market-input-acquisition-v0.1"
CONTRACT_CONTENT_SHA256 = (
    "7e783f4222b09c72342289bafbf9f3c2505b953ec9cb101e894ba4f30d4682d3"
)
AUTHORIZATION_ARTIFACT_TYPE = (
    "exact_quote_bound_prospective_market_input_acquisition_authorization"
)
REPORT_ARTIFACT_TYPE = "sanitized_exact_prospective_market_input_acquisition"
STYPE_IN = "raw_symbol"
PERMITTED_METHODS = (
    "historical.metadata.get_billable_size",
    "historical.metadata.get_cost",
    "historical.timeseries.get_range",
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^[1-9][0-9]*$")
_SAFE_CODE = re.compile(r"^[A-Za-z0-9_.:\-]{1,128}$")
_GENERATED_AT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class MetadataAPI(Protocol):
    def get_billable_size(self, **kwargs: object) -> int: ...

    def get_cost(self, **kwargs: object) -> float: ...


class TimeseriesAPI(Protocol):
    def get_range(self, **kwargs: object) -> object: ...


class HistoricalClient(Protocol):
    metadata: MetadataAPI
    timeseries: TimeseriesAPI


@dataclass(frozen=True, slots=True)
class ValidatedQuoteChain:
    bundle: ValidatedParentBundle
    quote_authorization: dict[str, object]
    quote_report: dict[str, object]
    trading_date: str
    request_count: int
    quoted_cost_usd: Decimal
    quoted_billable_size_bytes: int


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _array(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    return value


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer >= {minimum}")
    try:
        parsed = operator.index(value)
    except TypeError as exc:
        raise ValueError(f"{field} must be an integer >= {minimum}") from exc
    if parsed < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return parsed


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite non-negative decimal")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a finite non-negative decimal") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{field} must be a finite non-negative decimal")
    return parsed


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return value


def _run_id(value: object, field: str) -> str:
    rendered = str(value)
    if _RUN_ID.fullmatch(rendered) is None:
        raise ValueError(f"{field} must be a positive GitHub Actions run ID")
    return rendered


def _safe_code(value: object, field: str) -> str:
    if not isinstance(value, str) or _SAFE_CODE.fullmatch(value) is None:
        raise ValueError(f"{field} must be a sanitized code")
    return value


def _exception_kind(exc: Exception) -> str:
    kind = type(exc).__name__
    return kind if _SAFE_CODE.fullmatch(kind) is not None else "provider_error"


def _fingerprinted(payload: Mapping[str, object], field: str) -> str:
    claimed = _sha256(payload.get("content_sha256"), f"{field}.content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError(f"{field} content fingerprint changed")
    return claimed


def _finish(payload: dict[str, object]) -> dict[str, object]:
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    payload["content_sha256"] = canonical_fingerprint(unsigned)
    return payload


def _iso_z(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _ns_to_rfc3339(value: object) -> str:
    timestamp_ns = _integer(value, "request timestamp", minimum=1)
    seconds, nanoseconds = divmod(timestamp_ns, 1_000_000_000)
    prefix = datetime.fromtimestamp(seconds, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{prefix}.{nanoseconds:09d}Z"


def _read_object(path: str | Path, field: str) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{field} root must be an object")
    return payload


def _expect_mapping(
    payload: Mapping[str, object],
    field: str,
    expected: Mapping[str, object],
) -> None:
    if dict(_mapping(payload.get(field), field)) != dict(expected):
        raise ValueError(f"acquisition contract {field} changed")


def validate_acquisition_contract(payload: Mapping[str, object]) -> None:
    expected_fields = {
        "schema_version",
        "contract_id",
        "artifact_type",
        "registration_date",
        "registration_status",
        "purpose",
        "frozen_parents",
        "provider_scope",
        "required_parent_chain",
        "dynamic_authorization",
        "preflight_gate",
        "acquisition_semantics",
        "storage_and_cleanup",
        "workflow_boundary",
        "authority_boundary",
        "explicitly_prohibited",
        "next_gate",
        "content_sha256",
    }
    if set(payload) != expected_fields:
        raise ValueError("acquisition contract fields changed")
    expected_scalars = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "artifact_type": (
            "preregistered_unarmed_exact_prospective_market_input_acquisition"
        ),
        "registration_date": "2026-08-22",
        "registration_status": (
            "registered_before_first_prospective_request_quote_or_download"
        ),
        "purpose": (
            "Prepare a separately authorized fail-closed path that requotes and "
            "downloads only the exact frozen XNAS.ITCH mbp-1 and status requests, "
            "emits the minimal normalized causal capture, and creates no broker "
            "or policy authority."
        ),
        "next_gate": (
            "After a real registered date has a verified successful quote, create "
            "and publish one exact parent-bound acquisition authorization, run at "
            "most its first manual workflow attempt, preserve the minimal normalized "
            "capture or safe failure, and feed only complete captures into the "
            "still-separate account runtime."
        ),
    }
    for field, expected in expected_scalars.items():
        if payload.get(field) != expected:
            raise ValueError(f"acquisition contract {field} changed")
    if _fingerprinted(payload, "acquisition contract") != CONTRACT_CONTENT_SHA256:
        raise ValueError("acquisition contract registered fingerprint changed")

    _expect_mapping(
        payload,
        "frozen_parents",
        {
            "opportunity_freeze_contract_id": FREEZE_CONTRACT_ID,
            "opportunity_freeze_contract_content_sha256": (
                FREEZE_CONTRACT_CONTENT_SHA256
            ),
            "market_input_capture_contract_id": CAPTURE_CONTRACT_ID,
            "market_input_capture_contract_content_sha256": (
                CAPTURE_CONTRACT_CONTENT_SHA256
            ),
            "metadata_quote_contract_id": QUOTE_CONTRACT_ID,
            "metadata_quote_contract_content_sha256": QUOTE_CONTRACT_CONTENT_SHA256,
            "account_panel_id": PANEL_ID,
        },
    )
    _expect_mapping(
        payload,
        "provider_scope",
        {
            "provider": "Databento Historical API",
            "dataset": DATASET,
            "schemas": list(SCHEMAS),
            "stype_in": STYPE_IN,
            "sdk_package": "databento",
            "sdk_version": SDK_VERSION,
            "permitted_methods": list(PERMITTED_METHODS),
            "batch_or_live_methods_permitted": False,
            "venue_scope": "nasdaq_totalview_single_venue_not_consolidated_nbbo",
        },
    )
    _expect_mapping(
        payload,
        "required_parent_chain",
        {
            "exact_three_file_opportunity_freeze_required": True,
            "successful_complete_metadata_quote_required": True,
            "every_exact_request_must_be_available": True,
            "quote_report_must_bind_exact_freeze_and_quote_authorization": True,
            "all_parent_content_hashes_recomputed": True,
            "registered_trading_date_required": True,
            "zero_opportunity_date_retained": True,
            "retrospective_fields_rejected": True,
        },
    )
    _expect_mapping(
        payload,
        "dynamic_authorization",
        {
            "separate_exact_quote_bound_authorization_required": True,
            "authorization_created_only_after_successful_quote": True,
            "authorization_must_bind_freeze_quote_and_all_content_hashes": True,
            "hard_cost_ceiling_rule": "exact_successful_quote_total",
            "hard_billable_size_ceiling_rule": "exact_successful_quote_total",
            "maximum_metadata_call_count_rule": "two_requote_calls_per_exact_request",
            "maximum_timeseries_call_count_rule": "one_download_per_exact_request",
            "single_workflow_attempt_authorized": True,
            "authorization_reuse_authorized": False,
            "automatic_retry_authorized": False,
            "request_selection_or_substitution_authorized": False,
        },
    )
    _expect_mapping(
        payload,
        "preflight_gate",
        {
            "all_exact_requests_requoted_before_first_download": True,
            "requote_must_be_complete_and_available": True,
            "total_cost_must_not_exceed_authorized_quote_total": True,
            "total_billable_size_must_not_exceed_authorized_quote_total": True,
            "preflight_failure_timeseries_call_count": 0,
            "zero_request_date_provider_call_count": 0,
        },
    )
    _expect_mapping(
        payload,
        "acquisition_semantics",
        {
            "request_order": "exact_request_manifest_order",
            "one_timeseries_call_per_exact_request": True,
            "first_request_failure_stops_later_downloads": True,
            "partial_capture_persisted": False,
            "request_metadata_must_match": True,
            "every_downloaded_record_reconciled_to_one_exact_request": True,
            "minimal_normalized_capture_builder": CAPTURE_CONTRACT_ID,
            "both_execution_scenarios_receive_identical_capture": True,
            "sip_print_proxy_fallback_allowed": False,
            "another_symbol_venue_schema_or_window_substitution_allowed": False,
        },
    )
    _expect_mapping(
        payload,
        "storage_and_cleanup",
        {
            "temporary_raw_dbn_files_allowed_during_authorized_attempt": True,
            "temporary_raw_dbn_files_deleted_before_report": True,
            "raw_dbn_repository_persistence_allowed": False,
            "raw_dbn_actions_artifact_allowed": False,
            "minimal_normalized_capture_artifact_allowed": True,
            "provider_credentials_or_error_messages_persisted": False,
            "ephemeral_file_hashes_may_be_retained": True,
        },
    )
    _expect_mapping(
        payload,
        "workflow_boundary",
        {
            "expected_repository": EXPECTED_REPOSITORY,
            "provider_free_verification_on_push": True,
            "acquisition_event": "manual_workflow_dispatch_only",
            "exact_authorization_commit_sha_and_path_required": True,
            "named_successful_freeze_and_quote_runs_required": True,
            "first_acquisition_workflow_attempt_only": True,
            "provider_credential_loaded_only_in_acquisition_step": True,
            "safe_failure_report_uploaded": True,
            "raw_dbn_never_uploaded": True,
        },
    )
    _expect_mapping(
        payload,
        "authority_boundary",
        {
            "provider_metadata_requote_authorized_at_registration": False,
            "provider_timeseries_request_authorized_at_registration": False,
            "provider_purchase_authorized_at_registration": False,
            "databento_credit_authorized_usd": "0",
            "provider_call_run_count": 0,
            "broker_order_authorized": False,
            "paper_order_authorized": False,
            "live_order_authorized": False,
            "retrospective_labels_allowed": False,
            "later_prices_or_pnl_allowed": False,
            "threshold_horizon_or_scenario_selection_authorized": False,
            "runtime_authority_created": False,
            "policy_promotion_eligible": False,
            "profitability_claim_eligible": False,
        },
    )
    expected_prohibited = [
        (
            "creating an acquisition authorization before an exact successful "
            "metadata quote exists"
        ),
        (
            "downloading a request that is absent from or differs from the frozen "
            "request manifest"
        ),
        "continuing downloads after the first failed exact request",
        "persisting or uploading raw DBN files",
        (
            "using Ross actions, recaps, labels, later prices, P&L, account outcomes, "
            "or behavioral values to select or alter a request"
        ),
        (
            "substituting SIP prints, another venue, another symbol, another schema, "
            "or a broader time window for unavailable data"
        ),
        (
            "selecting a behavioral horizon, execution scenario, feature threshold, "
            "strategy rule, or promotion decision"
        ),
        "submitting a paper or live broker order",
    ]
    if payload.get("explicitly_prohibited") != expected_prohibited:
        raise ValueError("acquisition contract prohibited surface changed")


def load_acquisition_contract(path: str | Path) -> dict[str, object]:
    payload = _read_object(path, "acquisition contract")
    validate_acquisition_contract(payload)
    return payload


def validate_quote_chain(
    acquisition_contract: Mapping[str, object],
    quote_contract: Mapping[str, object],
    capture_contract: Mapping[str, object],
    bundle: ValidatedParentBundle,
    quote_authorization: Mapping[str, object],
    quote_report: Mapping[str, object],
) -> ValidatedQuoteChain:
    validate_acquisition_contract(acquisition_contract)
    validate_quote_contract(quote_contract)
    validate_capture_contract(capture_contract)
    bundle = validate_parent_bundle(
        quote_contract,
        capture_contract,
        bundle.opportunity_manifest,
        bundle.request_manifest,
        bundle.freeze_manifest,
    )
    validate_quote_authorization(
        quote_authorization,
        quote_contract=quote_contract,
        capture_contract=capture_contract,
        bundle=bundle,
    )
    validate_quote_report(
        quote_report,
        quote_contract=quote_contract,
        capture_contract=capture_contract,
        bundle=bundle,
        authorization=quote_authorization,
    )
    if quote_report.get("metadata_quote_gate_passed") is not True:
        raise ValueError("acquisition requires a successful metadata quote gate")
    metrics = _mapping(quote_report.get("quote_metrics"), "quote_metrics")
    size = _integer(
        metrics.get("total_billable_size_bytes"),
        "quote total billable size",
    )
    cost = _decimal(metrics.get("total_quoted_cost_usd"), "quote total cost")
    request_count = _integer(quote_report.get("request_count"), "request_count")
    expected_status = "not_applicable_zero_requests" if request_count == 0 else "complete"
    if quote_report.get("quote_status") != expected_status:
        raise ValueError("acquisition requires the exact complete quote status")
    if request_count != bundle.request_count:
        raise ValueError("quote request count differs from the freeze bundle")
    if request_count == 0 and (size != 0 or cost != 0):
        raise ValueError("zero-request quote must retain zero totals")
    return ValidatedQuoteChain(
        bundle=bundle,
        quote_authorization=dict(quote_authorization),
        quote_report=dict(quote_report),
        trading_date=bundle.trading_date,
        request_count=request_count,
        quoted_cost_usd=cost,
        quoted_billable_size_bytes=size,
    )


def load_quote_chain(
    *,
    acquisition_contract: Mapping[str, object],
    quote_contract: Mapping[str, object],
    capture_contract: Mapping[str, object],
    bundle: ValidatedParentBundle,
    quote_authorization_path: str | Path,
    quote_report_path: str | Path,
) -> ValidatedQuoteChain:
    return validate_quote_chain(
        acquisition_contract,
        quote_contract,
        capture_contract,
        bundle,
        _read_object(quote_authorization_path, "metadata quote authorization"),
        _read_object(quote_report_path, "metadata quote report"),
    )


def _parent_chain(chain: ValidatedQuoteChain) -> dict[str, object]:
    bundle = chain.bundle
    return {
        "source_content_sha256": bundle.freeze_manifest["source_content_sha256"],
        "opportunity_manifest_content_sha256": bundle.opportunity_manifest[
            "content_sha256"
        ],
        "request_manifest_content_sha256": bundle.request_manifest["content_sha256"],
        "freeze_manifest_content_sha256": bundle.freeze_manifest["content_sha256"],
        "quote_authorization_content_sha256": chain.quote_authorization[
            "content_sha256"
        ],
        "quote_report_content_sha256": chain.quote_report["content_sha256"],
    }


def _quote_artifact_name(chain: ValidatedQuoteChain) -> str:
    report = chain.quote_report
    return (
        f"prospective-market-input-metadata-quote-{chain.trading_date}-"
        f"{report['workflow_run_id']}-{report['workflow_run_attempt']}"
    )


def _authorization_unsigned(
    chain: ValidatedQuoteChain,
    *,
    repository: str,
    quote_artifact_name: str,
) -> dict[str, object]:
    if repository != EXPECTED_REPOSITORY:
        raise ValueError("acquisition repository changed")
    if quote_artifact_name != _quote_artifact_name(chain):
        raise ValueError("quote artifact name does not match the successful report")
    quote_run_id = _run_id(chain.quote_report.get("workflow_run_id"), "quote run ID")
    quote_attempt = _integer(
        chain.quote_report.get("workflow_run_attempt"),
        "quote run attempt",
        minimum=1,
    )
    freeze_provenance = dict(
        _mapping(chain.quote_authorization.get("freeze_provenance"), "freeze provenance")
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "authorization_id": (
            f"prospective-market-input-acquisition-{chain.trading_date}-"
            f"{str(chain.quote_report['content_sha256'])[:16]}"
        ),
        "artifact_type": AUTHORIZATION_ARTIFACT_TYPE,
        "acquisition_contract_id": CONTRACT_ID,
        "acquisition_contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "repository": repository,
        "trading_date": chain.trading_date,
        "freeze_provenance": freeze_provenance,
        "quote_provenance": {
            "workflow_run_id": quote_run_id,
            "workflow_run_attempt": quote_attempt,
            "artifact_name": quote_artifact_name,
        },
        "parent_chain": _parent_chain(chain),
        "request_count": chain.request_count,
        "hard_preflight_cost_ceiling_usd": format(chain.quoted_cost_usd, "f"),
        "hard_preflight_billable_size_ceiling_bytes": (
            chain.quoted_billable_size_bytes
        ),
        "permitted_provider_methods": list(PERMITTED_METHODS),
        "maximum_metadata_call_count": chain.request_count * 2,
        "maximum_timeseries_call_count": chain.request_count,
        "metadata_requote_authorized": True,
        "historical_timeseries_download_authorized": True,
        "databento_credit_authorized_usd": format(chain.quoted_cost_usd, "f"),
        "minimal_normalized_capture_persistence_authorized": True,
        "raw_dbn_persistence_or_upload_authorized": False,
        "first_acquisition_workflow_attempt_only": True,
        "authorization_reuse_authorized": False,
        "automatic_retry_authorized": False,
        "request_selection_or_substitution_authorized": False,
        "batch_or_live_endpoint_authorized": False,
        "broker_order_authorized": False,
        "retrospective_input_authorized": False,
        "horizon_or_scenario_selection_authorized": False,
        "runtime_authority_created": False,
    }


def build_acquisition_authorization(
    acquisition_contract: Mapping[str, object],
    quote_contract: Mapping[str, object],
    capture_contract: Mapping[str, object],
    bundle: ValidatedParentBundle,
    quote_authorization: Mapping[str, object],
    quote_report: Mapping[str, object],
    *,
    repository: str,
    quote_artifact_name: str,
) -> dict[str, object]:
    chain = validate_quote_chain(
        acquisition_contract,
        quote_contract,
        capture_contract,
        bundle,
        quote_authorization,
        quote_report,
    )
    return _finish(
        _authorization_unsigned(
            chain,
            repository=repository,
            quote_artifact_name=quote_artifact_name,
        )
    )


def validate_acquisition_authorization(
    payload: Mapping[str, object],
    *,
    acquisition_contract: Mapping[str, object],
    quote_contract: Mapping[str, object],
    capture_contract: Mapping[str, object],
    bundle: ValidatedParentBundle,
    quote_authorization: Mapping[str, object],
    quote_report: Mapping[str, object],
) -> ValidatedQuoteChain:
    chain = validate_quote_chain(
        acquisition_contract,
        quote_contract,
        capture_contract,
        bundle,
        quote_authorization,
        quote_report,
    )
    for field in (
        "metadata_requote_authorized",
        "historical_timeseries_download_authorized",
        "minimal_normalized_capture_persistence_authorized",
        "raw_dbn_persistence_or_upload_authorized",
        "first_acquisition_workflow_attempt_only",
        "authorization_reuse_authorized",
        "automatic_retry_authorized",
        "request_selection_or_substitution_authorized",
        "batch_or_live_endpoint_authorized",
        "broker_order_authorized",
        "retrospective_input_authorized",
        "horizon_or_scenario_selection_authorized",
        "runtime_authority_created",
    ):
        if not isinstance(payload.get(field), bool):
            raise ValueError(f"acquisition authorization {field} must be boolean")
    for field in (
        "request_count",
        "hard_preflight_billable_size_ceiling_bytes",
        "maximum_metadata_call_count",
        "maximum_timeseries_call_count",
    ):
        _integer(payload.get(field), f"acquisition authorization {field}")
    _decimal(
        payload.get("hard_preflight_cost_ceiling_usd"),
        "acquisition authorization cost ceiling",
    )
    _decimal(
        payload.get("databento_credit_authorized_usd"),
        "acquisition authorization credit",
    )
    provenance = _mapping(payload.get("quote_provenance"), "quote_provenance")
    expected = _authorization_unsigned(
        chain,
        repository=str(payload.get("repository")),
        quote_artifact_name=str(provenance.get("artifact_name")),
    )
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if unsigned != expected:
        raise ValueError("prospective acquisition authorization binding changed")
    _fingerprinted(payload, "acquisition authorization")
    return chain


def load_acquisition_authorization(
    path: str | Path,
    **validation: object,
) -> dict[str, object]:
    payload = _read_object(path, "acquisition authorization")
    validate_acquisition_authorization(payload, **validation)  # type: ignore[arg-type]
    return payload


def validate_execution_context(
    authorization: Mapping[str, object],
    *,
    repository: str,
    freeze_run_id: str,
    freeze_run_attempt: int,
    freeze_artifact_name: str,
    quote_run_id: str,
    quote_run_attempt: int,
    quote_artifact_name: str,
    workflow_run_id: str,
    workflow_run_attempt: int,
) -> None:
    if authorization.get("repository") != repository:
        raise ValueError("workflow repository does not match acquisition authorization")
    expected_freeze = {
        "workflow_run_id": _run_id(freeze_run_id, "freeze_run_id"),
        "workflow_run_attempt": _integer(
            freeze_run_attempt,
            "freeze_run_attempt",
            minimum=1,
        ),
        "artifact_name": freeze_artifact_name,
    }
    if dict(_mapping(authorization.get("freeze_provenance"), "freeze provenance")) != expected_freeze:
        raise ValueError("workflow freeze provenance does not match authorization")
    expected_quote = {
        "workflow_run_id": _run_id(quote_run_id, "quote_run_id"),
        "workflow_run_attempt": _integer(
            quote_run_attempt,
            "quote_run_attempt",
            minimum=1,
        ),
        "artifact_name": quote_artifact_name,
    }
    if dict(_mapping(authorization.get("quote_provenance"), "quote provenance")) != expected_quote:
        raise ValueError("workflow quote provenance does not match authorization")
    _run_id(workflow_run_id, "workflow_run_id")
    if _integer(workflow_run_attempt, "workflow_run_attempt", minimum=1) != 1:
        raise ValueError("prospective acquisition GitHub Actions rerun is not authorized")


def _request_kwargs(request: Mapping[str, object]) -> dict[str, object]:
    return {
        "dataset": request["dataset"],
        "start": _ns_to_rfc3339(request["start_ns"]),
        "end": _ns_to_rfc3339(request["end_ns"]),
        "symbols": list(_array(request.get("symbols"), "request.symbols")),
        "schema": request["schema"],
        "stype_in": request["stype_in"],
    }


def _metadata_field(metadata: object, field: str) -> object:
    value = getattr(metadata, field, None)
    if value is None and isinstance(metadata, Mapping):
        value = metadata.get(field)
    return value


def _metadata_value(metadata: object, field: str) -> str | None:
    value = _metadata_field(metadata, field)
    if value is None:
        return None
    value = getattr(value, "value", value)
    return str(value).lower().replace("_", "-")


def _metadata_timestamp_ns(metadata: object, field: str) -> int | None:
    value = _metadata_field(metadata, field)
    if value is None:
        return None
    raw = getattr(value, "value", None)
    if raw is not None:
        try:
            return _integer(raw, f"download metadata {field}", minimum=1)
        except ValueError:
            pass
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError(f"download metadata {field} is timezone-naive")
        delta = value.astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
        return (
            (delta.days * 86_400 + delta.seconds) * 1_000_000_000
            + delta.microseconds * 1_000
        )
    return _integer(value, f"download metadata {field}", minimum=1)


def _char(value: object) -> str:
    value = getattr(value, "value", value)
    if isinstance(value, bytes):
        return value.decode("ascii")
    try:
        integer = operator.index(value)
    except TypeError:
        pass
    else:
        if integer in {78, 89, 126}:
            return chr(integer)
    return str(value)


def _enum_int(value: object, field: str) -> int:
    return _integer(getattr(value, "value", value), field)


def _mapped_frame(store: object) -> object:
    try:
        frame = store.to_df(
            map_symbols=True,
            pretty_ts=False,
            price_type="fixed",
        )
    except Exception as exc:
        raise ValueError("provider record mapping failed") from exc
    columns = list(getattr(frame, "columns", ()))
    if "ts_recv" not in columns:
        frame = frame.reset_index()
        columns = list(getattr(frame, "columns", ()))
    if "ts_recv" not in columns or "symbol" not in columns:
        raise ValueError("mapped provider frame lacks ts_recv or symbol")
    return frame


def _normalize_store(
    store: object,
    request: Mapping[str, object],
) -> list[dict[str, object]]:
    metadata = getattr(store, "metadata", None)
    if _metadata_value(metadata, "dataset") != str(request["dataset"]).lower():
        raise ValueError("download metadata dataset mismatch")
    if _metadata_value(metadata, "schema") != str(request["schema"]).lower():
        raise ValueError("download metadata schema mismatch")
    expected_stype = str(request["stype_in"]).lower().replace("_", "-")
    if _metadata_value(metadata, "stype_in") != expected_stype:
        raise ValueError("download metadata input symbology mismatch")
    metadata_symbols = _metadata_field(metadata, "symbols")
    if not isinstance(metadata_symbols, (list, tuple)) or list(
        metadata_symbols
    ) != list(_array(request.get("symbols"), "request.symbols")):
        raise ValueError("download metadata symbols mismatch")
    if _metadata_timestamp_ns(metadata, "start") != _integer(
        request["start_ns"],
        "request.start_ns",
        minimum=1,
    ):
        raise ValueError("download metadata start mismatch")
    if _metadata_timestamp_ns(metadata, "end") != _integer(
        request["end_ns"],
        "request.end_ns",
        minimum=1,
    ):
        raise ValueError("download metadata end mismatch")
    frame = _mapped_frame(store)
    schema = str(request["schema"])
    symbol = str(_array(request.get("symbols"), "request.symbols")[0])
    if schema == "mbp-1":
        required = {
            "symbol",
            "ts_recv",
            "sequence",
            "bid_px_00",
            "bid_sz_00",
            "ask_px_00",
            "ask_sz_00",
        }
    elif schema == "status":
        required = {"symbol", "ts_recv", "action", "is_trading"}
    else:
        raise ValueError("download schema is not registered")
    columns = set(getattr(frame, "columns", ()))
    if not required.issubset(columns):
        raise ValueError("mapped provider frame lacks required schema fields")

    result: list[dict[str, object]] = []
    for row in frame.itertuples(index=False, name="ProspectiveRecord"):
        observed_symbol = str(getattr(row, "symbol"))
        if observed_symbol != symbol:
            raise ValueError("mapped provider record symbol differs from request")
        ts_recv_ns = _integer(getattr(row, "ts_recv"), "ts_recv", minimum=1)
        if not (
            _integer(request["start_ns"], "request.start_ns", minimum=1)
            <= ts_recv_ns
            < _integer(request["end_ns"], "request.end_ns", minimum=1)
        ):
            raise ValueError("mapped provider record falls outside exact request")
        if schema == "mbp-1":
            result.append(
                {
                    "symbol": observed_symbol,
                    "ts_recv_ns": ts_recv_ns,
                    "sequence": _integer(getattr(row, "sequence"), "sequence"),
                    "bid_px_nanos": _integer(getattr(row, "bid_px_00"), "bid_px_00"),
                    "bid_size": _integer(getattr(row, "bid_sz_00"), "bid_sz_00"),
                    "ask_px_nanos": _integer(getattr(row, "ask_px_00"), "ask_px_00"),
                    "ask_size": _integer(getattr(row, "ask_sz_00"), "ask_sz_00"),
                }
            )
        else:
            result.append(
                {
                    "symbol": observed_symbol,
                    "ts_recv_ns": ts_recv_ns,
                    "action": _enum_int(getattr(row, "action"), "status.action"),
                    "is_trading": _char(getattr(row, "is_trading")),
                }
            )
    return result


def _preflight_rows_pending(chain: ValidatedQuoteChain) -> list[dict[str, object]]:
    return [
        {
            "request_id": request["request_id"],
            "schema": request["schema"],
            "billable_size_bytes": None,
            "quoted_cost_usd": None,
            "quote_complete": False,
            "available": False,
            "status": "not_queried",
        }
        for request in _array(chain.bundle.request_manifest.get("requests"), "requests")
        if isinstance(request, Mapping)
    ]


def _run_preflight(
    chain: ValidatedQuoteChain,
    authorization: Mapping[str, object],
    client: HistoricalClient,
) -> tuple[dict[str, object], list[dict[str, object]], int]:
    rows: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    call_count = 0
    for raw in _array(chain.bundle.request_manifest.get("requests"), "requests"):
        request = _mapping(raw, "request")
        request_id = str(request["request_id"])
        kwargs = _request_kwargs(request)
        size: int | None = None
        cost: Decimal | None = None
        call_count += 1
        try:
            raw_size = client.metadata.get_billable_size(**kwargs)
            size = _integer(raw_size, "billable_size_bytes")
        except Exception as exc:
            errors.append(
                {
                    "stage": "metadata.get_billable_size",
                    "request_id": request_id,
                    "error_kind": _exception_kind(exc),
                }
            )
        call_count += 1
        try:
            cost = _decimal(client.metadata.get_cost(**kwargs), "quoted_cost_usd")
        except Exception as exc:
            errors.append(
                {
                    "stage": "metadata.get_cost",
                    "request_id": request_id,
                    "error_kind": _exception_kind(exc),
                }
            )
        complete = size is not None and cost is not None
        available = complete and size > 0
        rows.append(
            {
                "request_id": request_id,
                "schema": request["schema"],
                "billable_size_bytes": size,
                "quoted_cost_usd": None if cost is None else format(cost, "f"),
                "quote_complete": complete,
                "available": available,
                "status": (
                    "available"
                    if available
                    else "unavailable_zero_billable_size"
                    if complete
                    else "quote_incomplete"
                ),
            }
        )

    totals_complete = all(row["quote_complete"] is True for row in rows)
    all_available = all(row["available"] is True for row in rows)
    total_size = (
        sum(int(row["billable_size_bytes"]) for row in rows)
        if totals_complete
        else None
    )
    total_cost = (
        sum(
            (_decimal(row["quoted_cost_usd"], "quoted_cost_usd") for row in rows),
            Decimal("0"),
        )
        if totals_complete
        else None
    )
    cost_ceiling = _decimal(
        authorization.get("hard_preflight_cost_ceiling_usd"),
        "hard cost ceiling",
    )
    size_ceiling = _integer(
        authorization.get("hard_preflight_billable_size_ceiling_bytes"),
        "hard size ceiling",
    )
    cost_within = total_cost is not None and total_cost <= cost_ceiling
    size_within = total_size is not None and total_size <= size_ceiling
    passed = (
        len(rows) == chain.request_count
        and totals_complete
        and all_available
        and not errors
        and cost_within
        and size_within
    )
    return (
        {
            "request_count_expected": chain.request_count,
            "request_count_quoted": len(rows),
            "quote_rows": rows,
            "total_quoted_cost_usd": (
                None if total_cost is None else format(total_cost, "f")
            ),
            "total_billable_size_bytes": total_size,
            "hard_cost_ceiling_usd": format(cost_ceiling, "f"),
            "hard_billable_size_ceiling_bytes": size_ceiling,
            "all_quotes_complete_and_available": totals_complete and all_available,
            "cost_within_ceiling": cost_within,
            "billable_size_within_ceiling": size_within,
            "preflight_passed": passed,
        },
        errors,
        call_count,
    )


def _empty_preflight(
    chain: ValidatedQuoteChain,
    authorization: Mapping[str, object],
    *,
    zero_request_success: bool,
) -> dict[str, object]:
    return {
        "request_count_expected": chain.request_count,
        "request_count_quoted": 0,
        "quote_rows": [],
        "total_quoted_cost_usd": "0" if zero_request_success else None,
        "total_billable_size_bytes": 0 if zero_request_success else None,
        "hard_cost_ceiling_usd": str(
            authorization["hard_preflight_cost_ceiling_usd"]
        ),
        "hard_billable_size_ceiling_bytes": int(
            authorization["hard_preflight_billable_size_ceiling_bytes"]
        ),
        "all_quotes_complete_and_available": zero_request_success,
        "cost_within_ceiling": zero_request_success,
        "billable_size_within_ceiling": zero_request_success,
        "preflight_passed": zero_request_success,
    }


def _request_rows(chain: ValidatedQuoteChain) -> list[dict[str, object]]:
    return [
        {
            "request_id": request["request_id"],
            "schema": request["schema"],
            "status": "not_attempted",
            "request_completed": False,
            "metadata_matches": False,
            "record_count": None,
            "ephemeral_file_sha256": None,
        }
        for request in _array(chain.bundle.request_manifest.get("requests"), "requests")
        if isinstance(request, Mapping)
    ]


def _base_report(
    chain: ValidatedQuoteChain,
    authorization: Mapping[str, object],
    *,
    generated_at: datetime,
    workflow_run_id: str,
    workflow_run_attempt: int,
    sdk_version: str,
) -> dict[str, object]:
    run_id = _run_id(workflow_run_id, "workflow_run_id")
    attempt = _integer(workflow_run_attempt, "workflow_run_attempt", minimum=1)
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": (
            f"prospective-market-input-acquisition-{chain.trading_date}-"
            f"{run_id}-{attempt}"
        ),
        "artifact_type": REPORT_ARTIFACT_TYPE,
        "acquisition_contract_id": CONTRACT_ID,
        "acquisition_contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "authorization_id": authorization["authorization_id"],
        "authorization_content_sha256": authorization["content_sha256"],
        "generated_at": _iso_z(generated_at),
        "repository": authorization["repository"],
        "workflow_run_id": run_id,
        "workflow_run_attempt": attempt,
        "trading_date": chain.trading_date,
        "parent_chain": _parent_chain(chain),
        "provider": "databento",
        "dataset": DATASET,
        "schemas": list(SCHEMAS),
        "sdk_version": sdk_version,
        "request_count": chain.request_count,
        "maximum_authorized_metadata_call_count": chain.request_count * 2,
        "maximum_authorized_timeseries_call_count": chain.request_count,
        "metadata_call_count": 0,
        "timeseries_request_count": 0,
        "preflight": _empty_preflight(
            chain,
            authorization,
            zero_request_success=False,
        ),
        "request_rows": _request_rows(chain),
        "errors": [],
        "market_input_capture_content_sha256": None,
        "market_input_capture_complete": False,
        "normalized_capture_persisted": False,
        "raw_temp_directory_empty_before_cleanup": True,
        "raw_temp_directory_removed": True,
        "provider_metadata_calls_made": False,
        "provider_timeseries_calls_made": False,
        "provider_credential_persisted": False,
        "provider_error_messages_persisted": False,
        "raw_dbn_persisted": False,
        "raw_dbn_uploaded": False,
        "batch_or_live_endpoint_called": False,
        "request_substitution_attempted": False,
        "automatic_retry_attempted": False,
        "retrospective_labels_loaded": False,
        "ross_actions_or_recaps_loaded": False,
        "later_prices_or_pnl_loaded": False,
        "horizon_or_scenario_selected": False,
        "broker_order_submitted": False,
        "runtime_authority_created": False,
        "actual_billing_known": False,
        "acquisition_status": "unavailable_before_provider",
        "acquisition_gate_passed": False,
    }


def build_unavailable_report(
    acquisition_contract: Mapping[str, object],
    quote_contract: Mapping[str, object],
    capture_contract: Mapping[str, object],
    bundle: ValidatedParentBundle,
    quote_authorization: Mapping[str, object],
    quote_report: Mapping[str, object],
    authorization: Mapping[str, object],
    *,
    generated_at: datetime,
    workflow_run_id: str,
    workflow_run_attempt: int,
    sdk_version: str,
    error_stage: str,
    error_kind: str,
) -> dict[str, object]:
    chain = validate_acquisition_authorization(
        authorization,
        acquisition_contract=acquisition_contract,
        quote_contract=quote_contract,
        capture_contract=capture_contract,
        bundle=bundle,
        quote_authorization=quote_authorization,
        quote_report=quote_report,
    )
    if chain.request_count == 0:
        raise ValueError("zero-request dates are not provider failures")
    report = _base_report(
        chain,
        authorization,
        generated_at=generated_at,
        workflow_run_id=workflow_run_id,
        workflow_run_attempt=workflow_run_attempt,
        sdk_version=_safe_code(sdk_version, "sdk_version"),
    )
    report["errors"] = [
        {
            "stage": _safe_code(error_stage, "error_stage"),
            "request_id": None,
            "error_kind": _safe_code(error_kind, "error_kind"),
        }
    ]
    return _finish(report)


def build_zero_request_result(
    acquisition_contract: Mapping[str, object],
    quote_contract: Mapping[str, object],
    capture_contract: Mapping[str, object],
    bundle: ValidatedParentBundle,
    quote_authorization: Mapping[str, object],
    quote_report: Mapping[str, object],
    authorization: Mapping[str, object],
    *,
    generated_at: datetime,
    workflow_run_id: str,
    workflow_run_attempt: int,
) -> tuple[dict[str, object], dict[str, object]]:
    chain = validate_acquisition_authorization(
        authorization,
        acquisition_contract=acquisition_contract,
        quote_contract=quote_contract,
        capture_contract=capture_contract,
        bundle=bundle,
        quote_authorization=quote_authorization,
        quote_report=quote_report,
    )
    if chain.request_count != 0:
        raise ValueError("zero-request result requires an empty request manifest")
    capture = build_market_input_capture(
        capture_contract,
        chain.bundle.opportunity_manifest,
        chain.bundle.request_manifest,
        {"requests": []},
        [],
        [],
    )
    report = _base_report(
        chain,
        authorization,
        generated_at=generated_at,
        workflow_run_id=workflow_run_id,
        workflow_run_attempt=workflow_run_attempt,
        sdk_version="not_loaded_zero_requests",
    )
    report.update(
        {
            "preflight": _empty_preflight(
                chain,
                authorization,
                zero_request_success=True,
            ),
            "market_input_capture_content_sha256": capture["content_sha256"],
            "market_input_capture_complete": True,
            "normalized_capture_persisted": True,
            "acquisition_status": "not_applicable_zero_requests",
            "acquisition_gate_passed": True,
        }
    )
    return _finish(report), capture


def run_exact_acquisition(
    acquisition_contract: Mapping[str, object],
    quote_contract: Mapping[str, object],
    capture_contract: Mapping[str, object],
    bundle: ValidatedParentBundle,
    quote_authorization: Mapping[str, object],
    quote_report: Mapping[str, object],
    authorization: Mapping[str, object],
    client: HistoricalClient,
    *,
    generated_at: datetime,
    workflow_run_id: str,
    workflow_run_attempt: int,
    sdk_version: str,
) -> tuple[dict[str, object], dict[str, object] | None]:
    chain = validate_acquisition_authorization(
        authorization,
        acquisition_contract=acquisition_contract,
        quote_contract=quote_contract,
        capture_contract=capture_contract,
        bundle=bundle,
        quote_authorization=quote_authorization,
        quote_report=quote_report,
    )
    if workflow_run_attempt != 1:
        raise ValueError("prospective acquisition GitHub Actions rerun is not authorized")
    if sdk_version != SDK_VERSION:
        raise ValueError(f"Databento SDK version must be {SDK_VERSION}")
    if chain.request_count == 0:
        return build_zero_request_result(
            acquisition_contract,
            quote_contract,
            capture_contract,
            bundle,
            quote_authorization,
            quote_report,
            authorization,
            generated_at=generated_at,
            workflow_run_id=workflow_run_id,
            workflow_run_attempt=workflow_run_attempt,
        )

    report = _base_report(
        chain,
        authorization,
        generated_at=generated_at,
        workflow_run_id=workflow_run_id,
        workflow_run_attempt=workflow_run_attempt,
        sdk_version=sdk_version,
    )
    preflight, errors, metadata_calls = _run_preflight(chain, authorization, client)
    report["preflight"] = preflight
    report["metadata_call_count"] = metadata_calls
    report["provider_metadata_calls_made"] = metadata_calls > 0
    report["errors"] = errors
    if preflight["preflight_passed"] is not True:
        report["acquisition_status"] = "preflight_failed"
        return _finish(report), None

    requests = [
        _mapping(row, "request")
        for row in _array(chain.bundle.request_manifest.get("requests"), "requests")
    ]
    request_rows = _request_rows(chain)
    quote_records: list[dict[str, object]] = []
    status_records: list[dict[str, object]] = []
    evidence_rows: list[dict[str, object]] = []
    capture: dict[str, object] | None = None
    try:
        temporary = tempfile.TemporaryDirectory(
            prefix="momentumbot-prospective-input-"
        )
    except Exception as exc:
        errors.append(
            {
                "stage": "temporary_storage.create",
                "request_id": None,
                "error_kind": _exception_kind(exc),
            }
        )
        report["errors"] = errors
        report["acquisition_status"] = "acquisition_failed_closed"
        return _finish(report), None
    temporary_root = Path(temporary.name)
    try:
        for index, request in enumerate(requests):
            path = temporary_root / f"request-{index:03d}.dbn.zst"
            request_id = str(request["request_id"])
            try:
                report["timeseries_request_count"] = int(
                    report["timeseries_request_count"]
                ) + 1
                store = client.timeseries.get_range(
                    path=str(path),
                    **_request_kwargs(request),
                )
                if not path.is_file() or path.stat().st_size <= 0:
                    raise ValueError("downloaded DBN file is missing or empty")
                records = _normalize_store(store, request)
                if not records:
                    raise ValueError("available exact request returned zero records")
                file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
                request_rows[index] = {
                    "request_id": request_id,
                    "schema": request["schema"],
                    "status": "complete",
                    "request_completed": True,
                    "metadata_matches": True,
                    "record_count": len(records),
                    "ephemeral_file_sha256": file_hash,
                }
                evidence_rows.append(
                    {
                        "request_id": request_id,
                        "dataset": request["dataset"],
                        "schema": request["schema"],
                        "metadata_matches": True,
                        "request_completed": True,
                        "record_count": len(records),
                    }
                )
                if request["schema"] == "mbp-1":
                    quote_records.extend(records)
                else:
                    status_records.extend(records)
            except Exception as exc:
                request_rows[index]["status"] = "failed_closed"
                errors.append(
                    {
                        "stage": "timeseries.get_range_or_normalize",
                        "request_id": request_id,
                        "error_kind": _exception_kind(exc),
                    }
                )
                break
            finally:
                path.unlink(missing_ok=True)

        if not errors and len(evidence_rows) == chain.request_count:
            quote_records.sort(
                key=lambda row: (
                    int(row["ts_recv_ns"]),
                    int(row["sequence"]),
                    str(row["symbol"]),
                )
            )
            # Python's stable sort retains original provider order for equal
            # receive timestamps, as required by the capture contract.
            status_records.sort(key=lambda row: int(row["ts_recv_ns"]))
            try:
                capture = build_market_input_capture(
                    capture_contract,
                    chain.bundle.opportunity_manifest,
                    chain.bundle.request_manifest,
                    {"requests": evidence_rows},
                    quote_records,
                    status_records,
                )
            except Exception as exc:
                errors.append(
                    {
                        "stage": "capture.build_and_validate",
                        "request_id": None,
                        "error_kind": _exception_kind(exc),
                    }
                )
                capture = None
    finally:
        report["raw_temp_directory_empty_before_cleanup"] = not any(
            temporary_root.iterdir()
        )
        temporary_name = temporary.name
        temporary.cleanup()
        report["raw_temp_directory_removed"] = not Path(temporary_name).exists()

    report["request_rows"] = request_rows
    report["errors"] = errors
    report["provider_timeseries_calls_made"] = int(
        report["timeseries_request_count"]
    ) > 0
    complete = (
        not errors
        and capture is not None
        and int(report["timeseries_request_count"]) == chain.request_count
        and all(row["status"] == "complete" for row in request_rows)
        and report["raw_temp_directory_empty_before_cleanup"] is True
        and report["raw_temp_directory_removed"] is True
    )
    report.update(
        {
            "market_input_capture_content_sha256": (
                None if capture is None else capture["content_sha256"]
            ),
            "market_input_capture_complete": complete,
            "normalized_capture_persisted": complete,
            "acquisition_status": (
                "complete" if complete else "acquisition_failed_closed"
            ),
            "acquisition_gate_passed": complete,
        }
    )
    return _finish(report), capture if complete else None


def validate_acquisition_report(
    payload: Mapping[str, object],
    *,
    capture: Mapping[str, object] | None,
    acquisition_contract: Mapping[str, object],
    quote_contract: Mapping[str, object],
    capture_contract: Mapping[str, object],
    bundle: ValidatedParentBundle,
    quote_authorization: Mapping[str, object],
    quote_report: Mapping[str, object],
    authorization: Mapping[str, object],
) -> None:
    chain = validate_acquisition_authorization(
        authorization,
        acquisition_contract=acquisition_contract,
        quote_contract=quote_contract,
        capture_contract=capture_contract,
        bundle=bundle,
        quote_authorization=quote_authorization,
        quote_report=quote_report,
    )
    expected_fields = {
        "schema_version",
        "artifact_id",
        "artifact_type",
        "acquisition_contract_id",
        "acquisition_contract_content_sha256",
        "authorization_id",
        "authorization_content_sha256",
        "generated_at",
        "repository",
        "workflow_run_id",
        "workflow_run_attempt",
        "trading_date",
        "parent_chain",
        "provider",
        "dataset",
        "schemas",
        "sdk_version",
        "request_count",
        "maximum_authorized_metadata_call_count",
        "maximum_authorized_timeseries_call_count",
        "metadata_call_count",
        "timeseries_request_count",
        "preflight",
        "request_rows",
        "errors",
        "market_input_capture_content_sha256",
        "market_input_capture_complete",
        "normalized_capture_persisted",
        "raw_temp_directory_empty_before_cleanup",
        "raw_temp_directory_removed",
        "provider_metadata_calls_made",
        "provider_timeseries_calls_made",
        "provider_credential_persisted",
        "provider_error_messages_persisted",
        "raw_dbn_persisted",
        "raw_dbn_uploaded",
        "batch_or_live_endpoint_called",
        "request_substitution_attempted",
        "automatic_retry_attempted",
        "retrospective_labels_loaded",
        "ross_actions_or_recaps_loaded",
        "later_prices_or_pnl_loaded",
        "horizon_or_scenario_selected",
        "broker_order_submitted",
        "runtime_authority_created",
        "actual_billing_known",
        "acquisition_status",
        "acquisition_gate_passed",
        "content_sha256",
    }
    if set(payload) != expected_fields:
        raise ValueError("prospective acquisition report fields changed")
    expected_scalars = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": REPORT_ARTIFACT_TYPE,
        "acquisition_contract_id": CONTRACT_ID,
        "acquisition_contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "authorization_id": authorization["authorization_id"],
        "authorization_content_sha256": authorization["content_sha256"],
        "repository": authorization["repository"],
        "trading_date": chain.trading_date,
        "parent_chain": _parent_chain(chain),
        "provider": "databento",
        "dataset": DATASET,
        "schemas": list(SCHEMAS),
        "request_count": chain.request_count,
        "maximum_authorized_metadata_call_count": chain.request_count * 2,
        "maximum_authorized_timeseries_call_count": chain.request_count,
    }
    for field, expected in expected_scalars.items():
        if payload.get(field) != expected:
            raise ValueError(f"prospective acquisition report {field} changed")
    generated_at = payload.get("generated_at")
    if not isinstance(generated_at, str) or _GENERATED_AT.fullmatch(generated_at) is None:
        raise ValueError("prospective acquisition generated_at is invalid")
    run_id = _run_id(payload.get("workflow_run_id"), "workflow_run_id")
    attempt = _integer(payload.get("workflow_run_attempt"), "workflow_run_attempt", minimum=1)
    if attempt != 1:
        raise ValueError("prospective acquisition report cannot represent a rerun")
    if payload.get("artifact_id") != (
        f"prospective-market-input-acquisition-{chain.trading_date}-{run_id}-{attempt}"
    ):
        raise ValueError("prospective acquisition report identity changed")
    sdk_version = _safe_code(payload.get("sdk_version"), "sdk_version")
    for field in (
        "provider_credential_persisted",
        "provider_error_messages_persisted",
        "raw_dbn_persisted",
        "raw_dbn_uploaded",
        "batch_or_live_endpoint_called",
        "request_substitution_attempted",
        "automatic_retry_attempted",
        "retrospective_labels_loaded",
        "ross_actions_or_recaps_loaded",
        "later_prices_or_pnl_loaded",
        "horizon_or_scenario_selected",
        "broker_order_submitted",
        "runtime_authority_created",
        "actual_billing_known",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"prospective acquisition report {field} must remain false")
    raw_directory_empty = payload.get("raw_temp_directory_empty_before_cleanup")
    if not isinstance(raw_directory_empty, bool):
        raise ValueError("temporary raw directory cleanup flag changed")
    if payload.get("raw_temp_directory_removed") is not True:
        raise ValueError("temporary raw directory was not removed")

    metadata_calls = _integer(payload.get("metadata_call_count"), "metadata_call_count")
    timeseries_calls = _integer(
        payload.get("timeseries_request_count"),
        "timeseries_request_count",
    )
    if metadata_calls > chain.request_count * 2:
        raise ValueError("prospective acquisition exceeded metadata authorization")
    if timeseries_calls > chain.request_count:
        raise ValueError("prospective acquisition exceeded timeseries authorization")
    if (metadata_calls > 0 or timeseries_calls > 0) and sdk_version != SDK_VERSION:
        raise ValueError("provider calls require the pinned Databento SDK version")
    if chain.request_count == 0 and sdk_version != "not_loaded_zero_requests":
        raise ValueError("zero-request acquisition cannot load the provider SDK")
    if payload.get("provider_metadata_calls_made") is not (metadata_calls > 0):
        raise ValueError("metadata call flag does not reconcile")
    if payload.get("provider_timeseries_calls_made") is not (timeseries_calls > 0):
        raise ValueError("timeseries call flag does not reconcile")

    request_manifest_rows = _array(
        chain.bundle.request_manifest.get("requests"),
        "requests",
    )
    request_rows = _array(payload.get("request_rows"), "request_rows")
    if len(request_rows) != chain.request_count:
        raise ValueError("acquisition report must retain every exact request")
    completed = 0
    attempted = 0
    failure_seen = False
    not_attempted_seen = False
    for request_raw, row_raw in zip(request_manifest_rows, request_rows, strict=True):
        request = _mapping(request_raw, "request")
        row = _mapping(row_raw, "request row")
        if set(row) != {
            "request_id",
            "schema",
            "status",
            "request_completed",
            "metadata_matches",
            "record_count",
            "ephemeral_file_sha256",
        }:
            raise ValueError("prospective acquisition request row fields changed")
        if row.get("request_id") != request.get("request_id") or row.get("schema") != request.get("schema"):
            raise ValueError("prospective acquisition request identity changed")
        status = row.get("status")
        if status not in {"not_attempted", "failed_closed", "complete"}:
            raise ValueError("prospective acquisition request status changed")
        if status == "complete":
            if failure_seen or not_attempted_seen:
                raise ValueError("downloads are not an exact manifest-order prefix")
            if row.get("request_completed") is not True or row.get("metadata_matches") is not True:
                raise ValueError("completed request lacks completion metadata")
            _integer(row.get("record_count"), "record_count", minimum=1)
            _sha256(row.get("ephemeral_file_sha256"), "ephemeral_file_sha256")
            completed += 1
            attempted += 1
        elif status == "failed_closed":
            if failure_seen or not_attempted_seen:
                raise ValueError("downloads are not an exact manifest-order prefix")
            if row.get("request_completed") is not False or row.get("metadata_matches") is not False:
                raise ValueError("failed request cannot claim completion")
            if row.get("record_count") is not None or row.get("ephemeral_file_sha256") is not None:
                raise ValueError("failed request cannot retain completed evidence")
            failure_seen = True
            attempted += 1
        else:
            not_attempted_seen = True
            if any(
                row.get(field) not in {False, None}
                for field in (
                    "request_completed",
                    "metadata_matches",
                    "record_count",
                    "ephemeral_file_sha256",
                )
            ):
                raise ValueError("unattempted request carries acquisition evidence")
    if attempted != timeseries_calls:
        raise ValueError("timeseries request count does not match request rows")

    errors = _array(payload.get("errors"), "errors")
    request_ids = {str(row["request_id"]) for row in request_manifest_rows}
    for raw in errors:
        error = _mapping(raw, "error")
        if set(error) != {"stage", "request_id", "error_kind"}:
            raise ValueError("prospective acquisition error fields changed")
        _safe_code(error.get("stage"), "error.stage")
        _safe_code(error.get("error_kind"), "error.error_kind")
        if error.get("request_id") is not None and error.get("request_id") not in request_ids:
            raise ValueError("prospective acquisition error references unknown request")

    preflight = _mapping(payload.get("preflight"), "preflight")
    if set(preflight) != {
        "request_count_expected",
        "request_count_quoted",
        "quote_rows",
        "total_quoted_cost_usd",
        "total_billable_size_bytes",
        "hard_cost_ceiling_usd",
        "hard_billable_size_ceiling_bytes",
        "all_quotes_complete_and_available",
        "cost_within_ceiling",
        "billable_size_within_ceiling",
        "preflight_passed",
    }:
        raise ValueError("prospective acquisition preflight fields changed")
    if preflight.get("request_count_expected") != chain.request_count:
        raise ValueError("prospective acquisition preflight request count changed")
    if preflight.get("hard_cost_ceiling_usd") != authorization.get("hard_preflight_cost_ceiling_usd"):
        raise ValueError("prospective acquisition preflight cost ceiling changed")
    if preflight.get("hard_billable_size_ceiling_bytes") != authorization.get("hard_preflight_billable_size_ceiling_bytes"):
        raise ValueError("prospective acquisition preflight size ceiling changed")
    quote_rows = _array(preflight.get("quote_rows"), "preflight.quote_rows")
    quoted_count = _integer(preflight.get("request_count_quoted"), "request_count_quoted")
    if quoted_count != len(quote_rows):
        raise ValueError("prospective acquisition preflight row count changed")
    if quoted_count not in {0, chain.request_count}:
        raise ValueError("preflight must requote all exact requests together")
    for field in (
        "all_quotes_complete_and_available",
        "cost_within_ceiling",
        "billable_size_within_ceiling",
        "preflight_passed",
    ):
        if not isinstance(preflight.get(field), bool):
            raise ValueError(f"prospective acquisition preflight {field} changed")
    if quoted_count == 0:
        if metadata_calls != 0:
            raise ValueError("empty preflight cannot claim metadata calls")
        zero_success = chain.request_count == 0
        expected_preflight_values: dict[str, object] = {
            "total_quoted_cost_usd": "0" if zero_success else None,
            "total_billable_size_bytes": 0 if zero_success else None,
            "all_quotes_complete_and_available": zero_success,
            "cost_within_ceiling": zero_success,
            "billable_size_within_ceiling": zero_success,
            "preflight_passed": zero_success,
        }
    else:
        if metadata_calls != chain.request_count * 2:
            raise ValueError("preflight did not requote every exact request")
        complete_count = 0
        available_count = 0
        total_size = 0
        total_cost = Decimal("0")
        for request_raw, row_raw in zip(
            request_manifest_rows,
            quote_rows,
            strict=True,
        ):
            request = _mapping(request_raw, "request")
            row = _mapping(row_raw, "preflight quote row")
            if set(row) != {
                "request_id",
                "schema",
                "billable_size_bytes",
                "quoted_cost_usd",
                "quote_complete",
                "available",
                "status",
            }:
                raise ValueError("prospective preflight quote row fields changed")
            if row.get("request_id") != request.get("request_id") or row.get(
                "schema"
            ) != request.get("schema"):
                raise ValueError("prospective preflight request identity changed")
            if not isinstance(row.get("quote_complete"), bool) or not isinstance(
                row.get("available"),
                bool,
            ):
                raise ValueError("prospective preflight booleans changed")
            if row["quote_complete"] is True:
                size = _integer(
                    row.get("billable_size_bytes"),
                    "billable_size_bytes",
                )
                cost = _decimal(row.get("quoted_cost_usd"), "quoted_cost_usd")
                available = size > 0
                if row["available"] is not available:
                    raise ValueError("prospective preflight availability changed")
                expected_row_status = (
                    "available"
                    if available
                    else "unavailable_zero_billable_size"
                )
                complete_count += 1
                available_count += int(available)
                total_size += size
                total_cost += cost
            else:
                if row["available"] is not False:
                    raise ValueError(
                        "incomplete prospective preflight row cannot be available"
                    )
                if row.get("billable_size_bytes") is not None:
                    _integer(
                        row.get("billable_size_bytes"),
                        "partial billable_size_bytes",
                    )
                if row.get("quoted_cost_usd") is not None:
                    _decimal(
                        row.get("quoted_cost_usd"),
                        "partial quoted_cost_usd",
                    )
                expected_row_status = "quote_incomplete"
            if row.get("status") != expected_row_status:
                raise ValueError("prospective preflight row status changed")

        totals_complete = complete_count == chain.request_count
        all_available = available_count == chain.request_count
        expected_total_cost = format(total_cost, "f") if totals_complete else None
        expected_total_size = total_size if totals_complete else None
        cost_within = (
            totals_complete
            and total_cost
            <= _decimal(
                authorization["hard_preflight_cost_ceiling_usd"],
                "cost ceiling",
            )
        )
        size_within = (
            totals_complete
            and total_size
            <= _integer(
                authorization["hard_preflight_billable_size_ceiling_bytes"],
                "size ceiling",
            )
        )
        expected_preflight_values = {
            "total_quoted_cost_usd": expected_total_cost,
            "total_billable_size_bytes": expected_total_size,
            "all_quotes_complete_and_available": (
                totals_complete and all_available
            ),
            "cost_within_ceiling": cost_within,
            "billable_size_within_ceiling": size_within,
            "preflight_passed": (
                totals_complete and all_available and cost_within and size_within
            ),
        }
    for field, expected in expected_preflight_values.items():
        if preflight.get(field) != expected:
            raise ValueError(f"prospective acquisition preflight {field} changed")
    passed = preflight.get("preflight_passed") is True

    status = payload.get("acquisition_status")
    valid_statuses = {
        "not_applicable_zero_requests",
        "unavailable_before_provider",
        "preflight_failed",
        "acquisition_failed_closed",
        "complete",
    }
    if status not in valid_statuses:
        raise ValueError("prospective acquisition status changed")
    gate = payload.get("acquisition_gate_passed") is True
    capture_hash = payload.get("market_input_capture_content_sha256")
    if capture is not None:
        validate_market_input_capture(capture)
        if capture_hash != capture.get("content_sha256"):
            raise ValueError("prospective acquisition capture hash changed")
        if capture.get("opportunity_manifest_content_sha256") != chain.bundle.opportunity_manifest.get("content_sha256"):
            raise ValueError("prospective acquisition capture opportunity parent changed")
        if capture.get("request_manifest_content_sha256") != chain.bundle.request_manifest.get("content_sha256"):
            raise ValueError("prospective acquisition capture request parent changed")
    elif capture_hash is not None:
        raise ValueError("prospective acquisition report references a missing capture")

    if chain.request_count == 0:
        expected_status = "not_applicable_zero_requests"
        expected_gate = True
        if metadata_calls or timeseries_calls or errors or capture is None:
            raise ValueError("zero-request acquisition made a provider call or lost capture")
    elif metadata_calls == 0:
        expected_status = "unavailable_before_provider"
        expected_gate = False
        if timeseries_calls or len(errors) != 1 or capture is not None:
            raise ValueError("pre-provider acquisition failure is inconsistent")
    elif not passed:
        expected_status = "preflight_failed"
        expected_gate = False
        if timeseries_calls or capture is not None:
            raise ValueError("failed preflight cannot download or persist a capture")
    elif capture is None:
        expected_status = "acquisition_failed_closed"
        expected_gate = False
        if not errors:
            raise ValueError("failed acquisition lacks a safe error")
    else:
        expected_status = "complete"
        expected_gate = True
        if errors or completed != chain.request_count or timeseries_calls != chain.request_count:
            raise ValueError("complete acquisition does not cover every exact request")
    if status != expected_status or gate is not expected_gate:
        raise ValueError("prospective acquisition status or gate does not reconcile")
    if expected_gate and raw_directory_empty is not True:
        raise ValueError("complete acquisition retained a temporary raw file")
    if payload.get("market_input_capture_complete") is not expected_gate:
        raise ValueError("prospective acquisition capture-complete flag changed")
    if payload.get("normalized_capture_persisted") is not expected_gate:
        raise ValueError("prospective acquisition capture-persistence flag changed")
    _fingerprinted(payload, "prospective acquisition report")


__all__ = [
    "AUTHORIZATION_ARTIFACT_TYPE",
    "CONTRACT_CONTENT_SHA256",
    "CONTRACT_ID",
    "PERMITTED_METHODS",
    "REPORT_ARTIFACT_TYPE",
    "ValidatedQuoteChain",
    "build_acquisition_authorization",
    "build_unavailable_report",
    "build_zero_request_result",
    "load_acquisition_authorization",
    "load_acquisition_contract",
    "load_quote_chain",
    "run_exact_acquisition",
    "validate_acquisition_authorization",
    "validate_acquisition_contract",
    "validate_acquisition_report",
    "validate_execution_context",
    "validate_quote_chain",
]
