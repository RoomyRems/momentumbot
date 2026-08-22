"""Parent-bound metadata-only quotes for prospective market-input requests.

The registration represented here is deliberately unarmed.  It validates a
completed prospective opportunity-freeze bundle and can deterministically
materialize a later, exact-bundle authorization.  Only that separate
authorization permits the two Databento metadata methods defined below.  This
module has no time-series, batch, live, broker, download, or order surface.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Protocol

from momentumbot.research.account_chronological_integration import (
    PANEL_ID,
    REGISTERED_DATES,
)
from momentumbot.research.microstructure_contract import canonical_fingerprint
from momentumbot.research.prospective_market_input_capture import (
    CONTRACT_CONTENT_SHA256 as CAPTURE_CONTRACT_CONTENT_SHA256,
    CONTRACT_ID as CAPTURE_CONTRACT_ID,
    build_request_manifest,
    validate_capture_contract,
    validate_opportunity_manifest,
)
from momentumbot.research.prospective_opportunity_freeze import (
    CONTRACT_CONTENT_SHA256 as FREEZE_CONTRACT_CONTENT_SHA256,
    CONTRACT_ID as FREEZE_CONTRACT_ID,
    FREEZE_ARTIFACT_TYPE,
)


SCHEMA_VERSION = 1
CONTRACT_ID = "prospective-market-input-metadata-quote-v0.1"
CONTRACT_CONTENT_SHA256 = (
    "6e637a1ba675eb29bacc7d0effffc4836e5d67225c1835dc36cc4f43d5ba0b79"
)
ARTIFACT_TYPE = "sanitized_prospective_market_input_metadata_quote"
AUTHORIZATION_ARTIFACT_TYPE = (
    "exact_parent_bound_prospective_market_input_metadata_quote_authorization"
)
EXPECTED_REPOSITORY = "RoomyRems/momentumbot"
DATASET = "XNAS.ITCH"
SCHEMAS = ("mbp-1", "status")
STYPE_IN = "raw_symbol"
SDK_VERSION = "0.83.0"
PERMITTED_METHODS = (
    "historical.metadata.get_billable_size",
    "historical.metadata.get_cost",
)
FREEZE_CHECKPOINT_SHA = "8f8faf3ab551e6774ad677a842cea87ccb183238"
MICRO_POLICY_FINGERPRINT = (
    "49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa"
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^[1-9][0-9]*$")
_SAFE_CODE = re.compile(r"^[A-Za-z0-9_.:\-]{1,128}$")
_GENERATED_AT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_FREEZE_FIELDS = {
    "schema_version",
    "artifact_id",
    "artifact_type",
    "contract_id",
    "contract_content_sha256",
    "market_input_contract_id",
    "market_input_contract_content_sha256",
    "panel_id",
    "trading_date",
    "source_content_sha256",
    "opportunity_manifest_content_sha256",
    "request_manifest_content_sha256",
    "candidate_count",
    "opportunity_count",
    "request_count",
    "zero_opportunity_date_retained",
    "profile_union_preserved_before_account_scarcity",
    "provider_metadata_quote_made",
    "provider_timeseries_request_made",
    "provider_purchase_authorized",
    "databento_credit_authorized_usd",
    "broker_order_submitted",
    "retrospective_labels_loaded",
    "later_prices_or_pnl_loaded",
    "runtime_authority",
    "content_sha256",
}


class MetadataAPI(Protocol):
    """The entire provider surface available to the quote runner."""

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


class HistoricalClient(Protocol):
    metadata: MetadataAPI


@dataclass(frozen=True, slots=True)
class ValidatedParentBundle:
    opportunity_manifest: dict[str, object]
    request_manifest: dict[str, object]
    freeze_manifest: dict[str, object]
    trading_date: str
    request_count: int


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _array(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    return value


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


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


def _expect_mapping(
    payload: Mapping[str, object],
    field: str,
    expected: Mapping[str, object],
) -> None:
    observed = _mapping(payload.get(field), field)
    if dict(observed) != dict(expected):
        raise ValueError(f"quote contract {field} changed")


def validate_quote_contract(payload: Mapping[str, object]) -> None:
    expected_top_level = {
        "schema_version",
        "contract_id",
        "artifact_type",
        "registration_date",
        "registration_status",
        "purpose",
        "frozen_parents",
        "provider_scope",
        "parent_bundle_gate",
        "dynamic_authorization",
        "workflow_boundary",
        "sanitized_report",
        "authority_boundary",
        "explicitly_prohibited",
        "next_gate",
        "content_sha256",
    }
    if set(payload) != expected_top_level:
        raise ValueError("quote contract fields changed")
    expected_scalars = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "artifact_type": "preregistered_unarmed_dynamic_metadata_quote_harness",
        "registration_date": "2026-08-22",
        "registration_status": (
            "registered_before_first_prospective_request_manifest_and_quote"
        ),
        "purpose": (
            "Prepare a parent-bound metadata-only quote path for future exact "
            "prospective XNAS.ITCH mbp-1 and status requests without selecting "
            "an opportunity, downloading market data, or creating broker authority."
        ),
        "next_gate": (
            "After a registered date produces an independently verified opportunity "
            "freeze, create one exact-hash metadata-only authorization, run at most "
            "one quote attempt, preserve the sanitized report, and require a new "
            "bounded child before any time-series download."
        ),
    }
    for field, expected in expected_scalars.items():
        if payload.get(field) != expected:
            raise ValueError(f"quote contract {field} changed")
    _fingerprinted(payload, "quote contract")
    if payload["content_sha256"] != CONTRACT_CONTENT_SHA256:
        raise ValueError("quote contract registered fingerprint changed")

    _expect_mapping(
        payload,
        "frozen_parents",
        {
            "opportunity_freeze_contract_id": FREEZE_CONTRACT_ID,
            "opportunity_freeze_contract_content_sha256": (
                FREEZE_CONTRACT_CONTENT_SHA256
            ),
            "opportunity_freeze_checkpoint_sha": FREEZE_CHECKPOINT_SHA,
            "market_input_capture_contract_id": CAPTURE_CONTRACT_ID,
            "market_input_capture_contract_content_sha256": (
                CAPTURE_CONTRACT_CONTENT_SHA256
            ),
            "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
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
            "permitted_metadata_methods": list(PERMITTED_METHODS),
            "metadata_query_cost_usd": "0",
            "venue_scope": "nasdaq_totalview_single_venue_not_consolidated_nbbo",
        },
    )
    _expect_mapping(
        payload,
        "parent_bundle_gate",
        {
            "opportunity_manifest_required": True,
            "request_manifest_required": True,
            "freeze_manifest_required": True,
            "request_manifest_rederived_from_opportunities": True,
            "all_three_content_hashes_recomputed": True,
            "registered_trading_date_required": True,
            "zero_opportunity_date_retained": True,
            "retrospective_fields_rejected": True,
        },
    )
    _expect_mapping(
        payload,
        "dynamic_authorization",
        {
            "separate_exact_bundle_authorization_required": True,
            "authorization_created_only_after_valid_freeze": True,
            "authorization_must_bind_contract_and_all_parent_hashes": True,
            "maximum_metadata_call_count_rule": "two_calls_per_exact_request",
            "zero_request_date_rule": (
                "zero_provider_calls_and_explicit_not_applicable_success"
            ),
            "single_workflow_attempt_authorized": True,
            "rerun_authorized": False,
            "metadata_quote_may_select_request": False,
            "metadata_quote_may_authorize_download": False,
        },
    )
    _expect_mapping(
        payload,
        "workflow_boundary",
        {
            "expected_repository": EXPECTED_REPOSITORY,
            "provider_free_verification_on_push": True,
            "provider_quote_event": "manual_workflow_dispatch_only",
            "exact_authorization_commit_sha_required": True,
            "exact_authorization_path_required": True,
            "named_same_repository_freeze_run_and_artifact_required": True,
            "first_quote_workflow_attempt_only": True,
            "provider_credential_loaded_only_in_quote_step": True,
            "sanitized_report_uploaded_on_success_or_safe_failure": True,
        },
    )
    _expect_mapping(
        payload,
        "sanitized_report",
        {
            "one_row_per_exact_request": True,
            "provider_error_messages_persisted": False,
            "provider_credentials_persisted": False,
            "raw_market_data_persisted": False,
            "partial_quote_totals_reported_as_complete": False,
            "zero_billable_size_behavior": "request_unavailable_without_substitution",
            "download_authorized_by_report": False,
            "horizon_or_scenario_selected": False,
        },
    )
    _expect_mapping(
        payload,
        "authority_boundary",
        {
            "provider_metadata_quote_authorized_at_registration": False,
            "provider_metadata_quote_run_count": 0,
            "provider_timeseries_request_authorized": False,
            "provider_batch_request_authorized": False,
            "provider_purchase_authorized": False,
            "databento_credit_authorized_usd": "0",
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
            "creating or executing a metadata quote before an exact frozen "
            "opportunity and request bundle exists"
        ),
        (
            "using Ross actions, recaps, labels, later prices, P&L, account "
            "outcomes, or behavioral values to select or alter a request"
        ),
        (
            "calling historical.timeseries.get_range, historical.batch.submit_job, "
            "historical.batch.download, or live.subscribe"
        ),
        "treating a quote as purchase or download authority",
        (
            "substituting SIP prints, another venue, another symbol, or a broader "
            "time window for an unavailable request"
        ),
        (
            "selecting a behavioral horizon, execution scenario, feature threshold, "
            "strategy rule, or promotion decision"
        ),
        "submitting a paper or live broker order",
    ]
    if payload.get("explicitly_prohibited") != expected_prohibited:
        raise ValueError("quote contract prohibited surface changed")


def load_quote_contract(path: str | Path) -> dict[str, object]:
    payload = _load_object(path, "quote contract")
    validate_quote_contract(payload)
    return payload


def _load_object(path: str | Path, field: str) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{field} root must be an object")
    return payload


def validate_parent_bundle(
    quote_contract: Mapping[str, object],
    capture_contract: Mapping[str, object],
    opportunity_manifest: Mapping[str, object],
    request_manifest: Mapping[str, object],
    freeze_manifest: Mapping[str, object],
) -> ValidatedParentBundle:
    """Validate the three-file freeze handoff without requiring its source file."""
    validate_quote_contract(quote_contract)
    validate_capture_contract(capture_contract)
    opportunities = validate_opportunity_manifest(opportunity_manifest)
    expected_request = build_request_manifest(capture_contract, opportunity_manifest)
    if dict(request_manifest) != expected_request:
        raise ValueError("request manifest differs from deterministic derivation")
    _fingerprinted(request_manifest, "request manifest")

    if set(freeze_manifest) != _FREEZE_FIELDS:
        raise ValueError("opportunity freeze manifest fields changed")
    trading_date = str(freeze_manifest.get("trading_date"))
    if trading_date not in REGISTERED_DATES:
        raise ValueError("freeze trading date is outside the registered panel")
    if opportunity_manifest.get("artifact_id") != (
        f"prospective-opportunities-{trading_date}"
    ):
        raise ValueError("opportunity manifest does not bind the freeze date")
    if any(row.trading_date != trading_date for row in opportunities):
        raise ValueError("opportunity manifest contains another trading date")

    opportunity_count = len(opportunities)
    request_count = _integer(
        request_manifest.get("request_count"),
        "request_manifest.request_count",
    )
    candidate_count = _integer(
        freeze_manifest.get("candidate_count"),
        "freeze_manifest.candidate_count",
    )
    if candidate_count < opportunity_count:
        raise ValueError("freeze candidate count cannot be below opportunity count")
    source_hash = _sha256(
        freeze_manifest.get("source_content_sha256"),
        "freeze_manifest.source_content_sha256",
    )
    expected_freeze = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": f"prospective-opportunity-freeze-{trading_date}",
        "artifact_type": FREEZE_ARTIFACT_TYPE,
        "contract_id": FREEZE_CONTRACT_ID,
        "contract_content_sha256": FREEZE_CONTRACT_CONTENT_SHA256,
        "market_input_contract_id": CAPTURE_CONTRACT_ID,
        "market_input_contract_content_sha256": CAPTURE_CONTRACT_CONTENT_SHA256,
        "panel_id": PANEL_ID,
        "trading_date": trading_date,
        "source_content_sha256": source_hash,
        "opportunity_manifest_content_sha256": opportunity_manifest[
            "content_sha256"
        ],
        "request_manifest_content_sha256": request_manifest["content_sha256"],
        "candidate_count": candidate_count,
        "opportunity_count": opportunity_count,
        "request_count": request_count,
        "zero_opportunity_date_retained": opportunity_count == 0,
        "profile_union_preserved_before_account_scarcity": True,
        "provider_metadata_quote_made": False,
        "provider_timeseries_request_made": False,
        "provider_purchase_authorized": False,
        "databento_credit_authorized_usd": "0",
        "broker_order_submitted": False,
        "retrospective_labels_loaded": False,
        "later_prices_or_pnl_loaded": False,
        "runtime_authority": "none_unarmed",
    }
    unsigned_freeze = {
        key: value for key, value in freeze_manifest.items() if key != "content_sha256"
    }
    if unsigned_freeze != expected_freeze:
        raise ValueError("opportunity freeze manifest binding changed")
    _fingerprinted(freeze_manifest, "opportunity freeze manifest")
    return ValidatedParentBundle(
        opportunity_manifest=dict(opportunity_manifest),
        request_manifest=dict(request_manifest),
        freeze_manifest=dict(freeze_manifest),
        trading_date=trading_date,
        request_count=request_count,
    )


def load_parent_bundle(
    bundle_dir: str | Path,
    *,
    quote_contract: Mapping[str, object],
    capture_contract: Mapping[str, object],
) -> ValidatedParentBundle:
    root = Path(bundle_dir)
    opportunity = _load_object(root / "opportunity-manifest.json", "opportunity manifest")
    request = _load_object(root / "request-manifest.json", "request manifest")
    freeze = _load_object(root / "freeze-manifest.json", "freeze manifest")
    return validate_parent_bundle(
        quote_contract,
        capture_contract,
        opportunity,
        request,
        freeze,
    )


def _revalidate_bundle(
    quote_contract: Mapping[str, object],
    capture_contract: Mapping[str, object],
    bundle: ValidatedParentBundle,
) -> ValidatedParentBundle:
    return validate_parent_bundle(
        quote_contract,
        capture_contract,
        bundle.opportunity_manifest,
        bundle.request_manifest,
        bundle.freeze_manifest,
    )


def _freeze_artifact_name(trading_date: str) -> str:
    return f"prospective-opportunity-freeze-{trading_date}"


def _parent_hashes(bundle: ValidatedParentBundle) -> dict[str, object]:
    return {
        "source_content_sha256": bundle.freeze_manifest["source_content_sha256"],
        "opportunity_manifest_content_sha256": bundle.opportunity_manifest[
            "content_sha256"
        ],
        "request_manifest_content_sha256": bundle.request_manifest[
            "content_sha256"
        ],
        "freeze_manifest_content_sha256": bundle.freeze_manifest["content_sha256"],
    }


def _authorization_unsigned(
    bundle: ValidatedParentBundle,
    *,
    repository: str,
    freeze_run_id: str,
    freeze_run_attempt: int,
    freeze_artifact_name: str,
) -> dict[str, object]:
    if repository != EXPECTED_REPOSITORY:
        raise ValueError("metadata quote repository changed")
    run_id = _run_id(freeze_run_id, "freeze_run_id")
    attempt = _integer(freeze_run_attempt, "freeze_run_attempt", minimum=1)
    expected_artifact = _freeze_artifact_name(bundle.trading_date)
    if freeze_artifact_name != expected_artifact:
        raise ValueError("freeze artifact name does not match the registered date")
    freeze_hash = str(bundle.freeze_manifest["content_sha256"])
    return {
        "schema_version": SCHEMA_VERSION,
        "authorization_id": (
            f"prospective-market-input-metadata-quote-{bundle.trading_date}-"
            f"{freeze_hash[:16]}"
        ),
        "artifact_type": AUTHORIZATION_ARTIFACT_TYPE,
        "quote_contract_id": CONTRACT_ID,
        "quote_contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "repository": repository,
        "freeze_provenance": {
            "workflow_run_id": run_id,
            "workflow_run_attempt": attempt,
            "artifact_name": freeze_artifact_name,
        },
        "trading_date": bundle.trading_date,
        "parent_bundle": _parent_hashes(bundle),
        "request_count": bundle.request_count,
        "permitted_metadata_methods": list(PERMITTED_METHODS),
        "maximum_provider_call_count": bundle.request_count * 2,
        "provider_metadata_quote_authorized": True,
        "metadata_query_cost_usd": "0",
        "first_quote_workflow_attempt_only": True,
        "authorization_reuse_authorized": False,
        "automatic_retry_authorized": False,
        "request_selection_authorized": False,
        "provider_timeseries_request_authorized": False,
        "provider_batch_request_authorized": False,
        "provider_purchase_authorized": False,
        "databento_credit_authorized_usd": "0",
        "raw_market_data_persistence_authorized": False,
        "broker_order_authorized": False,
        "horizon_or_scenario_selection_authorized": False,
        "runtime_authority_created": False,
    }


def build_quote_authorization(
    quote_contract: Mapping[str, object],
    capture_contract: Mapping[str, object],
    bundle: ValidatedParentBundle,
    *,
    repository: str,
    freeze_run_id: str,
    freeze_run_attempt: int,
    freeze_artifact_name: str,
) -> dict[str, object]:
    validate_quote_contract(quote_contract)
    bundle = _revalidate_bundle(quote_contract, capture_contract, bundle)
    authorization = _authorization_unsigned(
        bundle,
        repository=repository,
        freeze_run_id=freeze_run_id,
        freeze_run_attempt=freeze_run_attempt,
        freeze_artifact_name=freeze_artifact_name,
    )
    return _finish(authorization)


def validate_quote_authorization(
    payload: Mapping[str, object],
    *,
    quote_contract: Mapping[str, object],
    capture_contract: Mapping[str, object],
    bundle: ValidatedParentBundle,
) -> None:
    validate_quote_contract(quote_contract)
    bundle = _revalidate_bundle(quote_contract, capture_contract, bundle)
    provenance = _mapping(payload.get("freeze_provenance"), "freeze_provenance")
    expected = _authorization_unsigned(
        bundle,
        repository=str(payload.get("repository")),
        freeze_run_id=_run_id(provenance.get("workflow_run_id"), "workflow_run_id"),
        freeze_run_attempt=_integer(
            provenance.get("workflow_run_attempt"),
            "freeze workflow run attempt",
            minimum=1,
        ),
        freeze_artifact_name=str(provenance.get("artifact_name")),
    )
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if unsigned != expected:
        raise ValueError("metadata quote authorization binding changed")
    _fingerprinted(payload, "metadata quote authorization")


def load_quote_authorization(
    path: str | Path,
    *,
    quote_contract: Mapping[str, object],
    capture_contract: Mapping[str, object],
    bundle: ValidatedParentBundle,
) -> dict[str, object]:
    payload = _load_object(path, "metadata quote authorization")
    validate_quote_authorization(
        payload,
        quote_contract=quote_contract,
        capture_contract=capture_contract,
        bundle=bundle,
    )
    return payload


def validate_execution_context(
    authorization: Mapping[str, object],
    *,
    repository: str,
    freeze_run_id: str,
    freeze_run_attempt: int,
    freeze_artifact_name: str,
    workflow_run_id: str,
    workflow_run_attempt: int,
) -> None:
    if repository != authorization.get("repository"):
        raise ValueError("workflow repository does not match authorization")
    provenance = _mapping(authorization.get("freeze_provenance"), "freeze_provenance")
    expected = {
        "workflow_run_id": _run_id(freeze_run_id, "freeze_run_id"),
        "workflow_run_attempt": _integer(
            freeze_run_attempt,
            "freeze_run_attempt",
            minimum=1,
        ),
        "artifact_name": freeze_artifact_name,
    }
    if dict(provenance) != expected:
        raise ValueError("workflow freeze provenance does not match authorization")
    _run_id(workflow_run_id, "workflow_run_id")
    if _integer(workflow_run_attempt, "workflow_run_attempt", minimum=1) != 1:
        raise ValueError("metadata quote GitHub Actions rerun is not authorized")


def _ns_to_rfc3339(timestamp_ns: int) -> str:
    seconds, nanoseconds = divmod(
        _integer(timestamp_ns, "request timestamp", minimum=1),
        1_000_000_000,
    )
    prefix = datetime.fromtimestamp(seconds, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{prefix}.{nanoseconds:09d}Z"


def _iso_z(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _report_rows_unavailable(
    bundle: ValidatedParentBundle,
) -> list[dict[str, object]]:
    return [
        {
            "request_id": row["request_id"],
            "schema": row["schema"],
            "billable_size_bytes": None,
            "quoted_cost_usd": None,
            "quote_complete": False,
            "available": False,
            "availability_status": "unavailable_before_provider",
        }
        for row in _array(bundle.request_manifest.get("requests"), "requests")
        if isinstance(row, Mapping)
    ]


def _build_report(
    authorization: Mapping[str, object],
    bundle: ValidatedParentBundle,
    *,
    generated_at: datetime,
    workflow_run_id: str,
    workflow_run_attempt: int,
    sdk_version: str,
    quote_rows: list[dict[str, object]],
    errors: list[dict[str, object]],
    metadata_call_count: int,
    quote_status: str,
    metadata_quote_gate_passed: bool,
) -> dict[str, object]:
    request_count = bundle.request_count
    quoted_count = sum(row.get("quote_complete") is True for row in quote_rows)
    available_count = sum(row.get("available") is True for row in quote_rows)
    totals_complete = quoted_count == request_count
    if totals_complete:
        total_size = sum(int(row["billable_size_bytes"]) for row in quote_rows)
        total_cost = sum(
            (_decimal(row["quoted_cost_usd"], "quoted_cost_usd") for row in quote_rows),
            Decimal("0"),
        )
    else:
        total_size = None
        total_cost = None
    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": (
            f"prospective-market-input-metadata-quote-{bundle.trading_date}-"
            f"{_run_id(workflow_run_id, 'workflow_run_id')}-"
            f"{_integer(workflow_run_attempt, 'workflow_run_attempt', minimum=1)}"
        ),
        "artifact_type": ARTIFACT_TYPE,
        "quote_contract_id": CONTRACT_ID,
        "quote_contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "authorization_id": authorization["authorization_id"],
        "authorization_content_sha256": authorization["content_sha256"],
        "generated_at": _iso_z(generated_at),
        "repository": authorization["repository"],
        "workflow_run_id": str(workflow_run_id),
        "workflow_run_attempt": workflow_run_attempt,
        "trading_date": bundle.trading_date,
        "parent_bundle": _parent_hashes(bundle),
        "provider": "databento",
        "dataset": DATASET,
        "schemas": list(SCHEMAS),
        "sdk_version": sdk_version,
        "request_count": request_count,
        "maximum_authorized_metadata_call_count": request_count * 2,
        "metadata_call_count": metadata_call_count,
        "metadata_query_cost_usd": "0",
        "quote_rows": quote_rows,
        "quote_metrics": {
            "request_count": request_count,
            "quoted_request_count": quoted_count,
            "available_request_count": available_count,
            "unavailable_request_count": request_count - available_count,
            "total_billable_size_bytes": total_size,
            "total_quoted_cost_usd": (
                format(total_cost, "f") if total_cost is not None else None
            ),
            "totals_complete": totals_complete,
        },
        "errors": errors,
        "quote_status": quote_status,
        "metadata_quote_gate_passed": metadata_quote_gate_passed,
        "zero_request_date": request_count == 0,
        "provider_metadata_quote_made": metadata_call_count > 0,
        "provider_credential_persisted": False,
        "provider_error_messages_persisted": False,
        "raw_market_data_persisted": False,
        "timeseries_batch_or_live_endpoint_called": False,
        "request_substitution_attempted": False,
        "automatic_retry_attempted": False,
        "retrospective_labels_loaded": False,
        "ross_actions_or_recaps_loaded": False,
        "later_prices_or_pnl_loaded": False,
        "horizon_or_scenario_selected": False,
        "broker_order_submitted": False,
        "runtime_authority_created": False,
        "download_authorized_by_this_artifact": False,
        "authorization_reuse_authorized": False,
    }
    return _finish(report)


def build_zero_request_report(
    quote_contract: Mapping[str, object],
    capture_contract: Mapping[str, object],
    bundle: ValidatedParentBundle,
    authorization: Mapping[str, object],
    *,
    generated_at: datetime,
    workflow_run_id: str,
    workflow_run_attempt: int,
) -> dict[str, object]:
    bundle = _revalidate_bundle(quote_contract, capture_contract, bundle)
    validate_quote_authorization(
        authorization,
        quote_contract=quote_contract,
        capture_contract=capture_contract,
        bundle=bundle,
    )
    if bundle.request_count != 0:
        raise ValueError("zero-request report requires an empty request manifest")
    return _build_report(
        authorization,
        bundle,
        generated_at=generated_at,
        workflow_run_id=workflow_run_id,
        workflow_run_attempt=workflow_run_attempt,
        sdk_version="not_loaded_zero_requests",
        quote_rows=[],
        errors=[],
        metadata_call_count=0,
        quote_status="not_applicable_zero_requests",
        metadata_quote_gate_passed=True,
    )


def build_unavailable_report(
    quote_contract: Mapping[str, object],
    capture_contract: Mapping[str, object],
    bundle: ValidatedParentBundle,
    authorization: Mapping[str, object],
    *,
    generated_at: datetime,
    workflow_run_id: str,
    workflow_run_attempt: int,
    sdk_version: str,
    error_stage: str,
    error_kind: str,
) -> dict[str, object]:
    bundle = _revalidate_bundle(quote_contract, capture_contract, bundle)
    validate_quote_authorization(
        authorization,
        quote_contract=quote_contract,
        capture_contract=capture_contract,
        bundle=bundle,
    )
    if bundle.request_count == 0:
        raise ValueError("an empty request manifest is not a provider failure")
    error = {
        "stage": _safe_code(error_stage, "error_stage"),
        "request_id": None,
        "error_kind": _safe_code(error_kind, "error_kind"),
    }
    return _build_report(
        authorization,
        bundle,
        generated_at=generated_at,
        workflow_run_id=workflow_run_id,
        workflow_run_attempt=workflow_run_attempt,
        sdk_version=_safe_code(sdk_version, "sdk_version"),
        quote_rows=_report_rows_unavailable(bundle),
        errors=[error],
        metadata_call_count=0,
        quote_status="unavailable_before_provider",
        metadata_quote_gate_passed=False,
    )


def run_metadata_quote(
    quote_contract: Mapping[str, object],
    capture_contract: Mapping[str, object],
    bundle: ValidatedParentBundle,
    authorization: Mapping[str, object],
    client: HistoricalClient,
    *,
    generated_at: datetime,
    sdk_version: str,
    workflow_run_id: str,
    workflow_run_attempt: int,
) -> dict[str, object]:
    bundle = _revalidate_bundle(quote_contract, capture_contract, bundle)
    validate_quote_authorization(
        authorization,
        quote_contract=quote_contract,
        capture_contract=capture_contract,
        bundle=bundle,
    )
    if sdk_version != SDK_VERSION:
        raise ValueError(f"Databento SDK version must be {SDK_VERSION}")
    if workflow_run_attempt != 1:
        raise ValueError("metadata quote GitHub Actions rerun is not authorized")
    if bundle.request_count == 0:
        return build_zero_request_report(
            quote_contract,
            capture_contract,
            bundle,
            authorization,
            generated_at=generated_at,
            workflow_run_id=workflow_run_id,
            workflow_run_attempt=workflow_run_attempt,
        )

    errors: list[dict[str, object]] = []
    quote_rows: list[dict[str, object]] = []
    metadata_call_count = 0
    for raw_request in _array(bundle.request_manifest.get("requests"), "requests"):
        request = _mapping(raw_request, "request")
        request_id = str(request["request_id"])
        kwargs: dict[str, Any] = {
            "dataset": request["dataset"],
            "start": _ns_to_rfc3339(int(request["start_ns"])),
            "end": _ns_to_rfc3339(int(request["end_ns"])),
            "symbols": list(request["symbols"]),
            "schema": request["schema"],
            "stype_in": request["stype_in"],
        }
        size: int | None = None
        cost: Decimal | None = None
        metadata_call_count += 1
        try:
            raw_size = client.metadata.get_billable_size(**kwargs)
        except Exception as exc:  # provider messages are deliberately discarded
            errors.append(
                {
                    "stage": "metadata.get_billable_size",
                    "request_id": request_id,
                    "error_kind": _exception_kind(exc),
                }
            )
        else:
            if isinstance(raw_size, bool) or not isinstance(raw_size, int) or raw_size < 0:
                errors.append(
                    {
                        "stage": "validation.billable_size",
                        "request_id": request_id,
                        "error_kind": "invalid_billable_size",
                    }
                )
            else:
                size = raw_size

        metadata_call_count += 1
        try:
            raw_cost = client.metadata.get_cost(**kwargs)
        except Exception as exc:  # provider messages are deliberately discarded
            errors.append(
                {
                    "stage": "metadata.get_cost",
                    "request_id": request_id,
                    "error_kind": _exception_kind(exc),
                }
            )
        else:
            try:
                cost = _decimal(raw_cost, "quoted cost")
            except ValueError:
                errors.append(
                    {
                        "stage": "validation.quoted_cost",
                        "request_id": request_id,
                        "error_kind": "invalid_quoted_cost",
                    }
                )

        complete = size is not None and cost is not None
        available = complete and size > 0
        if not complete:
            availability_status = "quote_incomplete"
        elif not available:
            availability_status = "unavailable_zero_billable_size"
        else:
            availability_status = "available"
        quote_rows.append(
            {
                "request_id": request_id,
                "schema": request["schema"],
                "billable_size_bytes": size,
                "quoted_cost_usd": format(cost, "f") if cost is not None else None,
                "quote_complete": complete,
                "available": available,
                "availability_status": availability_status,
            }
        )

    all_complete = all(row["quote_complete"] is True for row in quote_rows)
    all_available = all(row["available"] is True for row in quote_rows)
    if not all_complete or errors:
        quote_status = "partial"
    elif not all_available:
        quote_status = "complete_with_unavailable_requests"
    else:
        quote_status = "complete"
    return _build_report(
        authorization,
        bundle,
        generated_at=generated_at,
        workflow_run_id=workflow_run_id,
        workflow_run_attempt=workflow_run_attempt,
        sdk_version=sdk_version,
        quote_rows=quote_rows,
        errors=errors,
        metadata_call_count=metadata_call_count,
        quote_status=quote_status,
        metadata_quote_gate_passed=all_complete and all_available and not errors,
    )


def validate_quote_report(
    payload: Mapping[str, object],
    *,
    quote_contract: Mapping[str, object],
    capture_contract: Mapping[str, object],
    bundle: ValidatedParentBundle,
    authorization: Mapping[str, object],
) -> None:
    bundle = _revalidate_bundle(quote_contract, capture_contract, bundle)
    validate_quote_authorization(
        authorization,
        quote_contract=quote_contract,
        capture_contract=capture_contract,
        bundle=bundle,
    )
    expected_fields = {
        "schema_version",
        "artifact_id",
        "artifact_type",
        "quote_contract_id",
        "quote_contract_content_sha256",
        "authorization_id",
        "authorization_content_sha256",
        "generated_at",
        "repository",
        "workflow_run_id",
        "workflow_run_attempt",
        "trading_date",
        "parent_bundle",
        "provider",
        "dataset",
        "schemas",
        "sdk_version",
        "request_count",
        "maximum_authorized_metadata_call_count",
        "metadata_call_count",
        "metadata_query_cost_usd",
        "quote_rows",
        "quote_metrics",
        "errors",
        "quote_status",
        "metadata_quote_gate_passed",
        "zero_request_date",
        "provider_metadata_quote_made",
        "provider_credential_persisted",
        "provider_error_messages_persisted",
        "raw_market_data_persisted",
        "timeseries_batch_or_live_endpoint_called",
        "request_substitution_attempted",
        "automatic_retry_attempted",
        "retrospective_labels_loaded",
        "ross_actions_or_recaps_loaded",
        "later_prices_or_pnl_loaded",
        "horizon_or_scenario_selected",
        "broker_order_submitted",
        "runtime_authority_created",
        "download_authorized_by_this_artifact",
        "authorization_reuse_authorized",
        "content_sha256",
    }
    if set(payload) != expected_fields:
        raise ValueError("metadata quote report fields changed")
    expected_scalars = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "quote_contract_id": CONTRACT_ID,
        "quote_contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "authorization_id": authorization["authorization_id"],
        "authorization_content_sha256": authorization["content_sha256"],
        "repository": authorization["repository"],
        "trading_date": bundle.trading_date,
        "parent_bundle": _parent_hashes(bundle),
        "provider": "databento",
        "dataset": DATASET,
        "schemas": list(SCHEMAS),
        "request_count": bundle.request_count,
        "maximum_authorized_metadata_call_count": bundle.request_count * 2,
        "metadata_query_cost_usd": "0",
        "zero_request_date": bundle.request_count == 0,
    }
    for field, expected in expected_scalars.items():
        if payload.get(field) != expected:
            raise ValueError(f"metadata quote report {field} changed")
    for field in (
        "provider_credential_persisted",
        "provider_error_messages_persisted",
        "raw_market_data_persisted",
        "timeseries_batch_or_live_endpoint_called",
        "request_substitution_attempted",
        "automatic_retry_attempted",
        "retrospective_labels_loaded",
        "ross_actions_or_recaps_loaded",
        "later_prices_or_pnl_loaded",
        "horizon_or_scenario_selected",
        "broker_order_submitted",
        "runtime_authority_created",
        "download_authorized_by_this_artifact",
        "authorization_reuse_authorized",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"metadata quote report {field} must remain false")
    generated_at = payload.get("generated_at")
    if not isinstance(generated_at, str) or _GENERATED_AT.fullmatch(generated_at) is None:
        raise ValueError("metadata quote generated_at is invalid")
    run_id = _run_id(payload.get("workflow_run_id"), "workflow_run_id")
    run_attempt = _integer(
        payload.get("workflow_run_attempt"),
        "workflow_run_attempt",
        minimum=1,
    )
    if run_attempt != 1:
        raise ValueError("metadata quote report cannot represent a rerun")
    expected_artifact_id = (
        f"prospective-market-input-metadata-quote-{bundle.trading_date}-"
        f"{run_id}-{run_attempt}"
    )
    if payload.get("artifact_id") != expected_artifact_id:
        raise ValueError("metadata quote report artifact identity changed")
    _safe_code(payload.get("sdk_version"), "sdk_version")

    request_rows = _array(bundle.request_manifest.get("requests"), "requests")
    quote_rows = _array(payload.get("quote_rows"), "quote_rows")
    if len(quote_rows) != len(request_rows):
        raise ValueError("metadata quote report must retain every exact request")
    valid_statuses = {
        "available",
        "unavailable_zero_billable_size",
        "quote_incomplete",
        "unavailable_before_provider",
    }
    complete_count = 0
    available_count = 0
    total_size = 0
    total_cost = Decimal("0")
    for request_raw, quote_raw in zip(request_rows, quote_rows, strict=True):
        request = _mapping(request_raw, "request")
        row = _mapping(quote_raw, "quote row")
        if set(row) != {
            "request_id",
            "schema",
            "billable_size_bytes",
            "quoted_cost_usd",
            "quote_complete",
            "available",
            "availability_status",
        }:
            raise ValueError("metadata quote row fields changed")
        if row.get("request_id") != request.get("request_id") or row.get(
            "schema"
        ) != request.get("schema"):
            raise ValueError("metadata quote row request identity changed")
        status = row.get("availability_status")
        if status not in valid_statuses:
            raise ValueError("metadata quote row availability status changed")
        complete = row.get("quote_complete") is True
        available = row.get("available") is True
        size_value = row.get("billable_size_bytes")
        cost_value = row.get("quoted_cost_usd")
        if complete:
            size = _integer(size_value, "billable_size_bytes")
            cost = _decimal(cost_value, "quoted_cost_usd")
            if available != (size > 0):
                raise ValueError("metadata quote availability does not match size")
            expected_status = "available" if size > 0 else "unavailable_zero_billable_size"
            if status != expected_status:
                raise ValueError("metadata quote availability status is inconsistent")
            complete_count += 1
            available_count += int(available)
            total_size += size
            total_cost += cost
        else:
            if available or status not in {"quote_incomplete", "unavailable_before_provider"}:
                raise ValueError("incomplete metadata quote row is inconsistent")
            if size_value is not None:
                _integer(size_value, "partial billable_size_bytes")
            if cost_value is not None:
                _decimal(cost_value, "partial quoted_cost_usd")

    errors = _array(payload.get("errors"), "errors")
    request_ids = {str(row["request_id"]) for row in request_rows}
    for raw_error in errors:
        error = _mapping(raw_error, "error")
        if set(error) != {"stage", "request_id", "error_kind"}:
            raise ValueError("metadata quote error fields changed")
        _safe_code(error.get("stage"), "error.stage")
        _safe_code(error.get("error_kind"), "error.error_kind")
        if error.get("request_id") is not None and error.get("request_id") not in request_ids:
            raise ValueError("metadata quote error references an unknown request")

    metrics = _mapping(payload.get("quote_metrics"), "quote_metrics")
    totals_complete = complete_count == bundle.request_count
    expected_metrics = {
        "request_count": bundle.request_count,
        "quoted_request_count": complete_count,
        "available_request_count": available_count,
        "unavailable_request_count": bundle.request_count - available_count,
        "total_billable_size_bytes": total_size if totals_complete else None,
        "total_quoted_cost_usd": format(total_cost, "f") if totals_complete else None,
        "totals_complete": totals_complete,
    }
    if dict(metrics) != expected_metrics:
        raise ValueError("metadata quote metrics do not reconcile")

    call_count = _integer(payload.get("metadata_call_count"), "metadata_call_count")
    if call_count > bundle.request_count * 2:
        raise ValueError("metadata quote exceeded its call authorization")
    provider_called = payload.get("provider_metadata_quote_made") is True
    if provider_called != (call_count > 0):
        raise ValueError("metadata provider call flag does not reconcile")
    if bundle.request_count == 0:
        expected_status = "not_applicable_zero_requests"
        expected_gate = True
        if call_count != 0 or errors:
            raise ValueError("zero-request date cannot call the provider")
    elif call_count == 0:
        expected_status = "unavailable_before_provider"
        expected_gate = False
        if len(errors) != 1 or complete_count != 0:
            raise ValueError("pre-provider failure report is inconsistent")
    else:
        if call_count != bundle.request_count * 2:
            raise ValueError("metadata quote must attempt both calls for every request")
        if complete_count != bundle.request_count or errors:
            expected_status = "partial"
        elif available_count != bundle.request_count:
            expected_status = "complete_with_unavailable_requests"
        else:
            expected_status = "complete"
        expected_gate = (
            complete_count == bundle.request_count
            and available_count == bundle.request_count
            and not errors
        )
    if payload.get("quote_status") != expected_status:
        raise ValueError("metadata quote status does not reconcile")
    if payload.get("metadata_quote_gate_passed") is not expected_gate:
        raise ValueError("metadata quote gate does not reconcile")
    _fingerprinted(payload, "metadata quote report")


__all__ = [
    "ARTIFACT_TYPE",
    "AUTHORIZATION_ARTIFACT_TYPE",
    "CONTRACT_CONTENT_SHA256",
    "CONTRACT_ID",
    "DATASET",
    "EXPECTED_REPOSITORY",
    "PERMITTED_METHODS",
    "SCHEMAS",
    "SDK_VERSION",
    "ValidatedParentBundle",
    "build_quote_authorization",
    "build_unavailable_report",
    "build_zero_request_report",
    "load_parent_bundle",
    "load_quote_authorization",
    "load_quote_contract",
    "run_metadata_quote",
    "validate_execution_context",
    "validate_parent_bundle",
    "validate_quote_authorization",
    "validate_quote_contract",
    "validate_quote_report",
]
