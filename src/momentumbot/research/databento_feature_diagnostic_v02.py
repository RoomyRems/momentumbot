from __future__ import annotations

import json
import re
import tempfile
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from momentumbot.research import databento_feature_diagnostic_v01 as parent
from momentumbot.research.databento_quote import DATASET, SDK_VERSION, QuoteRequest
from momentumbot.research.databento_smoke import (
    HistoricalClient,
    RuntimeConstants,
    _char,
    _decimal,
    _finish_report,
    _has_fields,
    _integer,
    _iso_z,
    _metadata_value,
    _request_kwargs,
)
from momentumbot.research.microstructure_contract import (
    CanonicalDepthEvent,
    canonical_fingerprint,
    file_sha256,
)
from momentumbot.research.microstructure_features import (
    FEATURE_SET_CONTENT_SHA256,
    CausalMicrostructureFeatureEngine,
)


SCHEMA_VERSION = 1
DIAGNOSTIC_CONTRACT_ID = "databento-microstructure-feature-diagnostic-v0.2"
EXECUTION_AUTHORIZATION_ID = (
    "databento-microstructure-feature-diagnostic-v0.2-execution"
)
ARTIFACT_TYPE = "sanitized_databento_safe_failure_classifier"
CONTRACT_CONTENT_SHA256 = (
    "14b2a0500b7d2626a71f0a598eb876837f7d4f36754d44e3ecffee1fb3d9a648"
)
PARENT_FAILURE_AUDIT_ID = (
    "databento-microstructure-feature-diagnostic-v0.1-"
    "run-32444174639-failure-2026-08-20"
)
PARENT_FAILURE_CONTENT_SHA256 = (
    "004d5c37136674a91056371043fd389cd42e87fb10fbba90bea431220b2d57c7"
)
PARENT_FAILURE_REPORT_CONTENT_SHA256 = (
    "17899a4e833ce96d16311619a789be963848984ad2eff40dc05c12ab725d2b78"
)
PARENT_DIAGNOSTIC_CONTENT_SHA256 = parent.CONTRACT_CONTENT_SHA256
PARENT_ADAPTER_FILE_SHA256 = (
    "3c0c5ac0d18ffc3d72c1a18da9758ac33a269e3c074bac35fefb1528a99e1919"
)
FEATURE_ENGINE_SOURCE_FILE_SHA256 = parent.FEATURE_ENGINE_SOURCE_FILE_SHA256
MAX_PREFLIGHT_COST_USD = Decimal("0.001")
MAX_PREFLIGHT_BILLABLE_SIZE_BYTES = 1_000_000
REQUEST = parent.REQUESTS[0]
REQUESTS = (REQUEST,)
SAMPLE_INTERVAL_NS = parent.SAMPLE_INTERVAL_NS
FIXED_HYPOTHETICAL_ORDER_SIZES = parent.FIXED_HYPOTHETICAL_ORDER_SIZES

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_EXCEPTION_KINDS = frozenset(
    {
        "AttributeError",
        "Exception",
        "OSError",
        "RuntimeError",
        "TypeError",
        "UnicodeError",
        "ValueError",
    }
)
_REQUIRED_MBO_FIELDS = (
    "ts_recv",
    "ts_event",
    "publisher_id",
    "instrument_id",
    "channel_id",
    "sequence",
    "action",
    "side",
    "price",
    "size",
    "order_id",
    "flags",
)
_PHASES = frozenset(
    {
        "authorization",
        "credential",
        "sdk",
        "preflight",
        "provider_download",
        "downloaded_file",
        "metadata",
        "record",
        "atomic_group",
        "normalize",
        "book_replay",
        "feature_snapshot",
        "completion",
    }
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
        "required_field_missing",
        "record_payload_invalid",
        "receive_time_invalid",
        "atomic_key_change_before_last",
        "atomic_eof_before_last",
        "atomic_scope_invalid",
        "unsupported_action_or_side",
        "mutation_payload_invalid",
        "fill_cancel_unmatched",
        "canonical_event_rejected",
        "book_state_invariant",
        "feature_snapshot_invariant",
        "independent_replay_diverged",
        "feature_output_invariant",
        "stream_empty",
        "no_complete_snapshot",
        "unclassified_fail_closed",
    }
)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _verify_parent_sources() -> None:
    adapter_path = Path(str(parent.__file__))
    if adapter_path.suffix != ".py":
        raise ValueError("safe classifier requires the frozen parent Python source")
    if file_sha256(adapter_path) != PARENT_ADAPTER_FILE_SHA256:
        raise ValueError("frozen parent adapter source changed")
    parent._verify_feature_engine_source()


def validate_parent_failure_audit(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported parent feature failure audit schema")
    if payload.get("audit_id") != PARENT_FAILURE_AUDIT_ID:
        raise ValueError("unexpected parent feature failure audit")
    if payload.get("artifact_type") != (
        "independently_verified_sanitized_databento_feature_diagnostic_failure"
    ):
        raise ValueError("unexpected parent feature failure audit type")
    claimed = payload.get("content_sha256")
    if claimed != PARENT_FAILURE_CONTENT_SHA256:
        raise ValueError("parent feature failure content hash changed")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("parent feature failure fingerprint mismatch")
    actions = _mapping(payload.get("github_actions"), "github_actions")
    expected_actions = {
        "workflow_run_id": 32444174639,
        "workflow_run_attempt": 1,
        "workflow_conclusion": "failure",
        "workflow_head_sha": "3efee47b6daf8e27e1ea033da4393caecf237543",
        "workflow_head_tree_sha": "61f25367ba5b12dff29e8a40ad8e029d4d4cce0a",
        "artifact_id": 9433488265,
        "artifact_zip_sha256": (
            "6852f5e78f749125c8d1612b2d2e035165efbbe59c4bd78018cd3b3bd7afa747"
        ),
        "sanitized_report_content_sha256": PARENT_FAILURE_REPORT_CONTENT_SHA256,
    }
    for field, expected in expected_actions.items():
        if actions.get(field) != expected:
            raise ValueError(f"parent github_actions.{field} changed")
    verified = _mapping(
        payload.get("verified_preflight_and_attempt"),
        "verified_preflight_and_attempt",
    )
    expected_verified = {
        "preflight_passed": True,
        "request_count_quoted": 4,
        "timeseries_request_count": 1,
        "successful_download_summary_count": 0,
        "actual_billing_known": False,
        "automatic_retry_attempted": False,
        "first_attempt_only_observed": True,
    }
    for field, expected in expected_verified.items():
        if verified.get(field) != expected:
            raise ValueError(f"parent verified_preflight_and_attempt.{field} changed")
    interpretation = _mapping(
        payload.get("failure_interpretation"), "failure_interpretation"
    )
    if interpretation.get("exact_failing_guard_identified") is not False:
        raise ValueError("parent failure must remain unresolved")
    if interpretation.get("policy_promotion_allowed") is not False:
        raise ValueError("parent failure cannot promote policy")


def load_parent_failure_audit(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("parent feature failure audit root must be an object")
    validate_parent_failure_audit(payload)
    return payload


def validate_repair_contract(
    payload: Mapping[str, object],
    *,
    parent_failure_audit: Mapping[str, object] | None = None,
) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported safe classifier contract schema")
    if payload.get("diagnostic_contract_id") != DIAGNOSTIC_CONTRACT_ID:
        raise ValueError("unexpected safe classifier contract")
    if payload.get("artifact_type") != (
        "preregistered_unarmed_databento_safe_failure_classifier"
    ):
        raise ValueError("unexpected safe classifier contract type")
    claimed = payload.get("content_sha256")
    if claimed != CONTRACT_CONTENT_SHA256:
        raise ValueError("safe classifier contract content hash changed")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("safe classifier contract fingerprint mismatch")

    failure = _mapping(payload.get("frozen_parent_failure"), "frozen_parent_failure")
    expected_failure = {
        "audit_id": PARENT_FAILURE_AUDIT_ID,
        "content_sha256": PARENT_FAILURE_CONTENT_SHA256,
        "workflow_run_id": 32444174639,
        "workflow_run_attempt": 1,
        "sanitized_report_content_sha256": PARENT_FAILURE_REPORT_CONTENT_SHA256,
        "observed_error_kind": "ValueError",
        "exact_failing_guard_identified": False,
    }
    for field, expected in expected_failure.items():
        if failure.get(field) != expected:
            raise ValueError(f"frozen_parent_failure.{field} changed")
    if parent_failure_audit is not None:
        validate_parent_failure_audit(parent_failure_audit)

    frozen = _mapping(payload.get("frozen_mechanics"), "frozen_mechanics")
    expected_frozen = {
        "parent_diagnostic_content_sha256": PARENT_DIAGNOSTIC_CONTENT_SHA256,
        "parent_adapter_file_sha256": PARENT_ADAPTER_FILE_SHA256,
        "feature_set_content_sha256": FEATURE_SET_CONTENT_SHA256,
        "feature_engine_file_sha256": FEATURE_ENGINE_SOURCE_FILE_SHA256,
        "adapter_semantics_changed": False,
        "feature_mechanics_changed": False,
        "feature_windows_or_thresholds_changed": False,
    }
    for field, expected in expected_frozen.items():
        if frozen.get(field) != expected:
            raise ValueError(f"frozen_mechanics.{field} changed")

    surface = _mapping(payload.get("request_surface"), "request_surface")
    if surface.get("exact_request_count") != 1:
        raise ValueError("safe classifier request count changed")
    rows = surface.get("requests")
    if not isinstance(rows, list) or len(rows) != 1:
        raise ValueError("safe classifier exact request changed")
    observed = _mapping(rows[0], "safe classifier request")
    if dict(observed) != REQUEST.mapping():
        raise ValueError("safe classifier INTJ request surface changed")
    if surface.get("proposed_hard_preflight_cost_ceiling_usd") != "0.001":
        raise ValueError("safe classifier proposed cost ceiling changed")
    if surface.get("proposed_hard_preflight_billable_size_ceiling_bytes") != 1_000_000:
        raise ValueError("safe classifier proposed size ceiling changed")

    policy = _mapping(payload.get("safe_diagnostic_policy"), "safe_diagnostic_policy")
    expected_policy = {
        "provider_exception_message_retained": False,
        "adapter_exception_message_retained": False,
        "exception_message_hash_retained": False,
        "raw_values_in_error_code_allowed": False,
        "unknown_value_error_fails_closed": True,
        "unknown_exception_fails_closed": True,
        "automatic_retry_allowed": False,
    }
    for field, expected in expected_policy.items():
        if policy.get(field) != expected:
            raise ValueError(f"safe_diagnostic_policy.{field} changed")

    gate = _mapping(payload.get("future_execution_gate"), "future_execution_gate")
    expected_gate = {
        "provider_purchase_authorized": False,
        "execution_authorization_file_present": False,
        "new_explicit_user_authorization_required": True,
        "future_authorization_must_bind_published_parent_sha": True,
        "first_github_actions_attempt_only": True,
        "exact_request_count_authorized": 0,
        "hard_preflight_cost_ceiling_usd": "0.001",
        "hard_preflight_billable_size_ceiling_bytes": 1_000_000,
        "automatic_retry_authorized": False,
        "batch_or_live_endpoint_authorized": False,
        "mbp10_redownload_authorized": False,
        "raw_market_data_publication_authorized": False,
        "broker_or_order_change_authorized": False,
        "strategy_or_threshold_change_authorized": False,
    }
    for field, expected in expected_gate.items():
        if gate.get(field) != expected:
            raise ValueError(f"future_execution_gate.{field} changed")
    _verify_parent_sources()


def load_repair_contract(
    path: str | Path,
    *,
    parent_failure_audit: Mapping[str, object] | None = None,
) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("safe classifier contract root must be an object")
    validate_repair_contract(
        payload,
        parent_failure_audit=parent_failure_audit,
    )
    return payload


def validate_execution_authorization(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported v0.2 execution authorization schema")
    if payload.get("execution_authorization_id") != EXECUTION_AUTHORIZATION_ID:
        raise ValueError("unexpected v0.2 execution authorization")
    if payload.get("artifact_type") != (
        "explicit_one_shot_databento_safe_failure_classifier_authorization"
    ):
        raise ValueError("unexpected v0.2 execution authorization type")
    if payload.get("diagnostic_contract_id") != DIAGNOSTIC_CONTRACT_ID:
        raise ValueError("v0.2 execution authorization contract ID changed")
    if payload.get("diagnostic_contract_content_sha256") != CONTRACT_CONTENT_SHA256:
        raise ValueError("v0.2 execution authorization contract binding changed")
    claimed = payload.get("content_sha256")
    if not isinstance(claimed, str) or not _SHA64.fullmatch(claimed):
        raise ValueError("v0.2 execution authorization hash is invalid")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("v0.2 execution authorization fingerprint mismatch")
    parent_sha = payload.get("authorized_push_parent_sha")
    if not isinstance(parent_sha, str) or not _SHA40.fullmatch(parent_sha):
        raise ValueError("v0.2 execution authorization parent SHA is invalid")
    expected = {
        "provider_purchase_authorized": True,
        "exact_request_count_authorized": 1,
        "hard_preflight_cost_ceiling_usd": "0.001",
        "hard_preflight_billable_size_ceiling_bytes": 1_000_000,
        "first_github_actions_attempt_only": True,
        "automatic_retry_authorized": False,
        "batch_or_live_endpoint_authorized": False,
        "mbp10_redownload_authorized": False,
        "raw_market_data_publication_authorized": False,
        "broker_or_order_change_authorized": False,
        "strategy_or_threshold_change_authorized": False,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise ValueError(f"v0.2 execution authorization {field} changed")
    statement = payload.get("explicit_user_authorization")
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError("v0.2 explicit user authorization is required")


def load_execution_authorization(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("v0.2 execution authorization root must be an object")
    validate_execution_authorization(payload)
    return payload


class SafeDiagnosticFailure(Exception):
    __slots__ = ("phase", "code", "exception_kind")

    def __init__(
        self,
        phase: str,
        code: str,
        exception_kind: str | None = None,
    ) -> None:
        if phase not in _PHASES:
            raise ValueError("safe diagnostic failure phase is not allowlisted")
        if code not in SAFE_ERROR_CODES:
            raise ValueError("safe diagnostic failure code is not allowlisted")
        if exception_kind is not None and exception_kind not in _EXCEPTION_KINDS:
            raise ValueError("safe diagnostic exception kind is not allowlisted")
        self.phase = phase
        self.code = code
        self.exception_kind = exception_kind
        super().__init__(code)

    def mapping(self) -> dict[str, str]:
        row = {"failure_phase": self.phase, "safe_error_code": self.code}
        if self.exception_kind is not None:
            row["exception_kind"] = self.exception_kind
        return row


def _exception_kind(exc: Exception) -> str:
    if isinstance(exc, UnicodeError):
        return "UnicodeError"
    if isinstance(exc, AttributeError):
        return "AttributeError"
    if isinstance(exc, TypeError):
        return "TypeError"
    if isinstance(exc, ValueError):
        return "ValueError"
    if isinstance(exc, OSError):
        return "OSError"
    if isinstance(exc, RuntimeError):
        return "RuntimeError"
    return "Exception"


def _classified_from_exception(
    *,
    phase: str,
    code: str,
    exc: Exception,
) -> SafeDiagnosticFailure:
    return SafeDiagnosticFailure(phase, code, _exception_kind(exc))


def _record_key(record: object) -> tuple[int, int, int]:
    try:
        return (
            _integer(getattr(record, "publisher_id"), "publisher_id"),
            _integer(getattr(record, "instrument_id"), "instrument_id"),
            _integer(getattr(record, "sequence"), "sequence"),
        )
    except (AttributeError, ValueError, TypeError) as exc:
        raise _classified_from_exception(
            phase="record",
            code="record_payload_invalid",
            exc=exc,
        ) from None


def _validated_atomic_groups(
    records: Iterable[object],
    *,
    runtime: RuntimeConstants,
) -> tuple[tuple[object, ...], ...]:
    groups: list[tuple[object, ...]] = []
    current: list[object] = []
    current_key: tuple[int, int, int] | None = None
    previous_ts_recv = -1
    for record in records:
        if not _has_fields(record, _REQUIRED_MBO_FIELDS):
            raise SafeDiagnosticFailure("record", "required_field_missing")
        try:
            ts_recv = _integer(getattr(record, "ts_recv"), "ts_recv", minimum=1)
            flags = _integer(getattr(record, "flags"), "flags")
        except (AttributeError, ValueError, TypeError) as exc:
            raise _classified_from_exception(
                phase="record",
                code="record_payload_invalid",
                exc=exc,
            ) from None
        if ts_recv < previous_ts_recv and not flags & runtime.f_bad_ts_recv:
            raise SafeDiagnosticFailure("record", "receive_time_invalid")
        previous_ts_recv = max(previous_ts_recv, ts_recv)
        key = _record_key(record)
        if current_key is None:
            current_key = key
        elif key != current_key:
            raise SafeDiagnosticFailure(
                "atomic_group", "atomic_key_change_before_last"
            )
        current.append(record)
        if flags & runtime.f_last:
            groups.append(tuple(current))
            current = []
            current_key = None
    if current:
        raise SafeDiagnosticFailure("atomic_group", "atomic_eof_before_last")
    if not groups:
        raise SafeDiagnosticFailure("completion", "stream_empty")
    return tuple(groups)


def _record_identity(record: object) -> tuple[int, str, int, int]:
    try:
        return (
            _integer(getattr(record, "order_id"), "order_id", minimum=1),
            _char(getattr(record, "side")),
            _integer(getattr(record, "price"), "price", minimum=1),
            _integer(getattr(record, "size"), "size", minimum=1),
        )
    except (AttributeError, ValueError, TypeError, UnicodeError) as exc:
        raise _classified_from_exception(
            phase="normalize",
            code="mutation_payload_invalid",
            exc=exc,
        ) from None


def _validate_and_translate_group(
    records: Sequence[object],
    *,
    runtime: RuntimeConstants,
) -> parent.TranslatedAtomicGroup:
    keys = {_record_key(record) for record in records}
    if len(keys) != 1:
        raise SafeDiagnosticFailure("atomic_group", "atomic_scope_invalid")
    fills: Counter[tuple[int, str, int, int]] = Counter()
    cancels: Counter[tuple[int, str, int, int]] = Counter()
    for record in records:
        try:
            action = _char(getattr(record, "action"))
            side = _char(getattr(record, "side"))
        except (AttributeError, UnicodeError) as exc:
            raise _classified_from_exception(
                phase="record",
                code="record_payload_invalid",
                exc=exc,
            ) from None
        if action not in {"A", "C", "M", "R", "T", "F", "N"}:
            raise SafeDiagnosticFailure("normalize", "unsupported_action_or_side")
        if side not in {"A", "B", "N"}:
            raise SafeDiagnosticFailure("normalize", "unsupported_action_or_side")
        if action in {"A", "C", "M"}:
            try:
                price = _integer(getattr(record, "price"), "price")
                size = _integer(getattr(record, "size"), "size")
            except (AttributeError, ValueError, TypeError) as exc:
                raise _classified_from_exception(
                    phase="normalize",
                    code="mutation_payload_invalid",
                    exc=exc,
                ) from None
            if price == runtime.undef_price or (action == "M" and size == 0):
                raise SafeDiagnosticFailure(
                    "normalize",
                    "mutation_payload_invalid",
                )
        if action == "F":
            fills[_record_identity(record)] += 1
        elif action == "C":
            cancels[_record_identity(record)] += 1
    if any(count > cancels[identity] for identity, count in fills.items()):
        raise SafeDiagnosticFailure("normalize", "fill_cancel_unmatched")
    try:
        return parent.translate_xnas_atomic_group(
            records,
            symbol=REQUEST.symbol,
            runtime=runtime,
        )
    except Exception as exc:
        raise _classified_from_exception(
            phase="normalize",
            code="canonical_event_rejected",
            exc=exc,
        ) from None


def _probe_parent_pipeline(
    records: Sequence[object],
    *,
    runtime: RuntimeConstants,
) -> None:
    groups = _validated_atomic_groups(records, runtime=runtime)
    engine = CausalMicrostructureFeatureEngine()
    current_bucket: int | None = None
    last_complete_ts_recv: int | None = None
    ingested_any = False

    def sample(ts_recv_ns: int) -> None:
        try:
            engine.snapshot(
                as_of_ts_recv_ns=ts_recv_ns,
                hypothetical_order_sizes=FIXED_HYPOTHETICAL_ORDER_SIZES,
            )
        except Exception as exc:
            raise _classified_from_exception(
                phase="feature_snapshot",
                code="feature_snapshot_invariant",
                exc=exc,
            ) from None

    for records_in_group in groups:
        translated = _validate_and_translate_group(
            records_in_group,
            runtime=runtime,
        )
        bucket = translated.ts_recv_ns // SAMPLE_INTERVAL_NS
        if (
            current_bucket is not None
            and bucket != current_bucket
            and last_complete_ts_recv is not None
            and ingested_any
        ):
            sample(last_complete_ts_recv)
        current_bucket = bucket
        last_complete_ts_recv = translated.ts_recv_ns
        try:
            for event in translated.ordered_events:
                if isinstance(event, CanonicalDepthEvent):
                    engine.ingest_depth(event)
                else:
                    engine.ingest_tape(event)
        except Exception as exc:
            raise _classified_from_exception(
                phase="book_replay",
                code="book_state_invariant",
                exc=exc,
            ) from None
        ingested_any = ingested_any or bool(translated.ordered_events)
    if last_complete_ts_recv is not None and ingested_any:
        sample(last_complete_ts_recv)
    if not ingested_any:
        raise SafeDiagnosticFailure("completion", "no_complete_snapshot")


_PARENT_COMPLETION_CODES = {
    "independent feature replays diverged": "independent_replay_diverged",
    "feature snapshot applied an unregistered threshold": "feature_output_invariant",
    "feature snapshot created runtime authority": "feature_output_invariant",
    "feature depth walks must be a list": "feature_output_invariant",
    "feature snapshot windows changed": "feature_output_invariant",
    "MBO feature diagnostic stream was empty": "stream_empty",
    "MBO feature diagnostic produced no complete snapshot": "no_complete_snapshot",
}


def extract_classified_feature_diagnostic(
    store: Iterable[object],
    *,
    request: QuoteRequest,
    runtime: RuntimeConstants,
) -> dict[str, object]:
    if request != REQUEST:
        raise ValueError("safe classifier requires the exact frozen INTJ request")
    try:
        records = tuple(store)
    except Exception as exc:
        raise _classified_from_exception(
            phase="record",
            code="record_payload_invalid",
            exc=exc,
        ) from None
    _probe_parent_pipeline(records, runtime=runtime)
    try:
        return parent.extract_case_feature_diagnostic(
            records,
            request=request,
            runtime=runtime,
        )
    except ValueError as exc:
        code = _PARENT_COMPLETION_CODES.get(str(exc), "unclassified_fail_closed")
        raise _classified_from_exception(
            phase="completion",
            code=code,
            exc=exc,
        ) from None
    except Exception as exc:
        raise _classified_from_exception(
            phase="completion",
            code="unclassified_fail_closed",
            exc=exc,
        ) from None


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
                "hard_billable_size_ceiling_bytes": (
                    MAX_PREFLIGHT_BILLABLE_SIZE_BYTES
                ),
                "preflight_passed": False,
            },
            [
                {
                    "failure_phase": "preflight",
                    "safe_error_code": "preflight_metadata_query_failed",
                }
            ],
        )
    within_cost = cost <= MAX_PREFLIGHT_COST_USD
    within_size = size <= MAX_PREFLIGHT_BILLABLE_SIZE_BYTES
    row: dict[str, object] = REQUEST.mapping()
    row.update(
        {
            "quoted_cost_usd": format(cost, "f"),
            "billable_size_bytes": size,
        }
    )
    errors: list[dict[str, str]] = []
    if not (within_cost and within_size):
        errors.append(
            {
                "failure_phase": "preflight",
                "safe_error_code": "preflight_budget_rejected",
            }
        )
    return (
        {
            "request_count_expected": 1,
            "request_count_quoted": 1,
            "quote_rows": [row],
            "total_quoted_cost_usd": format(cost, "f"),
            "total_billable_size_bytes": size,
            "hard_cost_ceiling_usd": format(MAX_PREFLIGHT_COST_USD, "f"),
            "hard_billable_size_ceiling_bytes": MAX_PREFLIGHT_BILLABLE_SIZE_BYTES,
            "preflight_passed": within_cost and within_size,
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
        "diagnostic_contract_id": DIAGNOSTIC_CONTRACT_ID,
        "diagnostic_contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "execution_authorization_id": EXECUTION_AUTHORIZATION_ID,
        "execution_authorization_content_sha256": authorization["content_sha256"],
        "parent_failure_audit_id": PARENT_FAILURE_AUDIT_ID,
        "parent_failure_audit_content_sha256": PARENT_FAILURE_CONTENT_SHA256,
        "parent_failure_report_content_sha256": (
            PARENT_FAILURE_REPORT_CONTENT_SHA256
        ),
        "parent_adapter_file_sha256": PARENT_ADAPTER_FILE_SHA256,
        "feature_engine_source_file_sha256": FEATURE_ENGINE_SOURCE_FILE_SHA256,
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
        "feature_snapshot_values_persisted": False,
        "batch_or_live_endpoint_called": False,
        "automatic_retry_attempted": False,
        "mbp10_redownloaded": False,
        "retrospective_labels_loaded": False,
        "strategy_or_threshold_change_made": False,
        "broker_or_order_change_made": False,
        "adapter_or_feature_mechanics_changed": False,
        "actual_billing_known": False,
        "billing_note": (
            "Preflight quotes are not represented as actual billed charges; "
            "a completed time-series request may be billable."
        ),
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
    validate_repair_contract(
        contract,
        parent_failure_audit=parent_failure_audit,
    )
    validate_execution_authorization(authorization)
    failure = SafeDiagnosticFailure(failure_phase, safe_error_code)
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
                "hard_billable_size_ceiling_bytes": (
                    MAX_PREFLIGHT_BILLABLE_SIZE_BYTES
                ),
                "preflight_passed": False,
            },
            "timeseries_request_count": 0,
            "downloads": [],
            "errors": [failure.mapping()],
            "raw_temp_directory_empty_before_cleanup": True,
            "raw_temp_directory_removed": True,
            "diagnostic_observation_complete": False,
            "feature_replay_succeeded": False,
            "safe_failure_classified": True,
            "runtime_authority_created": False,
            "policy_promotion_eligible": False,
        }
    )
    return _finish_report(report)


def _download_and_observe(
    client: HistoricalClient,
    path: Path,
    runtime: RuntimeConstants,
) -> dict[str, object]:
    try:
        store = client.timeseries.get_range(
            path=str(path),
            **_request_kwargs(REQUEST),
        )
    except Exception:
        raise SafeDiagnosticFailure(
            "provider_download", "provider_download_failed"
        ) from None
    try:
        file_nonempty = path.is_file() and path.stat().st_size > 0
    except OSError as exc:
        raise _classified_from_exception(
            phase="downloaded_file",
            code="download_empty",
            exc=exc,
        ) from None
    if not file_nonempty:
        raise SafeDiagnosticFailure("downloaded_file", "download_empty")
    try:
        dataset = _metadata_value(getattr(store, "metadata", None), "dataset")
        schema = _metadata_value(getattr(store, "metadata", None), "schema")
    except Exception as exc:
        raise _classified_from_exception(
            phase="metadata",
            code="metadata_mismatch",
            exc=exc,
        ) from None
    if dataset != DATASET.lower() or schema != "mbo":
        raise SafeDiagnosticFailure("metadata", "metadata_mismatch")
    metrics = extract_classified_feature_diagnostic(
        store,
        request=REQUEST,
        runtime=runtime,
    )
    return {
        "trading_date": REQUEST.trading_date,
        "symbol": REQUEST.symbol,
        "schema": REQUEST.schema,
        "ephemeral_file_sha256": file_sha256(path),
        "file_nonempty": True,
        "metadata_matches_request": True,
        "metrics": metrics,
    }


def run_safe_failure_classifier(
    contract: Mapping[str, object],
    parent_failure_audit: Mapping[str, object],
    authorization: Mapping[str, object],
    client: HistoricalClient,
    *,
    generated_at: datetime,
    sdk_version: str,
    runtime: RuntimeConstants,
) -> dict[str, object]:
    validate_repair_contract(
        contract,
        parent_failure_audit=parent_failure_audit,
    )
    validate_execution_authorization(authorization)
    _verify_parent_sources()
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
            "downloads": [],
            "errors": errors,
            "raw_temp_directory_empty_before_cleanup": True,
            "raw_temp_directory_removed": True,
        }
    )
    if preflight.get("preflight_passed") is not True:
        report.update(
            {
                "diagnostic_observation_complete": False,
                "feature_replay_succeeded": False,
                "safe_failure_classified": bool(errors),
                "runtime_authority_created": False,
                "policy_promotion_eligible": False,
            }
        )
        return _finish_report(report)

    temp = tempfile.TemporaryDirectory(prefix="momentumbot-databento-features-v02-")
    temp_path = Path(temp.name)
    path = temp_path / "request-00.dbn.zst"
    try:
        try:
            report["timeseries_request_count"] = 1
            report["downloads"].append(_download_and_observe(client, path, runtime))
        except SafeDiagnosticFailure as exc:
            errors.append(exc.mapping())
        except Exception as exc:
            errors.append(
                _classified_from_exception(
                    phase="completion",
                    code="unclassified_fail_closed",
                    exc=exc,
                ).mapping()
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

    downloads = report["downloads"] if isinstance(report["downloads"], list) else []
    observation_complete = (
        report["timeseries_request_count"] == 1
        and report["raw_temp_directory_empty_before_cleanup"] is True
        and report["raw_temp_directory_removed"] is True
        and (
            (len(downloads) == 1 and not errors)
            or (not downloads and len(errors) == 1)
        )
    )
    report.update(
        {
            "diagnostic_observation_complete": observation_complete,
            "feature_replay_succeeded": len(downloads) == 1 and not errors,
            "safe_failure_classified": bool(errors)
            and all(
                isinstance(row, Mapping)
                and row.get("safe_error_code") in SAFE_ERROR_CODES
                for row in errors
            ),
            "runtime_authority_created": False,
            "policy_promotion_eligible": False,
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


def validate_safe_failure_report(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported safe failure report schema")
    if payload.get("diagnostic_contract_id") != DIAGNOSTIC_CONTRACT_ID:
        raise ValueError("unexpected safe failure report contract")
    if payload.get("diagnostic_contract_content_sha256") != CONTRACT_CONTENT_SHA256:
        raise ValueError("safe failure report contract binding changed")
    if payload.get("artifact_type") != ARTIFACT_TYPE:
        raise ValueError("unexpected safe failure report type")
    expected_hashes = {
        "parent_failure_audit_content_sha256": PARENT_FAILURE_CONTENT_SHA256,
        "parent_failure_report_content_sha256": (
            PARENT_FAILURE_REPORT_CONTENT_SHA256
        ),
        "parent_adapter_file_sha256": PARENT_ADAPTER_FILE_SHA256,
        "feature_engine_source_file_sha256": FEATURE_ENGINE_SOURCE_FILE_SHA256,
    }
    for field, expected in expected_hashes.items():
        if payload.get(field) != expected:
            raise ValueError(f"safe failure report {field} changed")
    for field in (
        "provider_credential_persisted",
        "raw_market_data_persisted",
        "raw_market_data_uploaded",
        "feature_snapshot_values_persisted",
        "batch_or_live_endpoint_called",
        "automatic_retry_attempted",
        "mbp10_redownloaded",
        "retrospective_labels_loaded",
        "strategy_or_threshold_change_made",
        "broker_or_order_change_made",
        "adapter_or_feature_mechanics_changed",
        "actual_billing_known",
        "runtime_authority_created",
        "policy_promotion_eligible",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must remain false")
    request_count = int(payload.get("timeseries_request_count", 0))
    if request_count not in {0, 1}:
        raise ValueError("safe classifier request count exceeded one")
    if payload.get("raw_temp_directory_empty_before_cleanup") is not True:
        raise ValueError("safe classifier temporary directory was not empty")
    if payload.get("raw_temp_directory_removed") is not True:
        raise ValueError("safe classifier temporary directory was not removed")
    forbidden_keys = {
        "raw_records",
        "record_values",
        "order_id",
        "instrument_id",
        "price",
        "size",
        "levels",
        "feature_snapshots",
        "temporary_path",
        "provider_error_message",
        "exception_message",
        "error_message",
        "error_signature_sha256",
        "record_index",
        "ross_action",
        "ross_label",
        "pnl",
        "later_price",
    }
    if set(_walk_keys(payload)) & forbidden_keys:
        raise ValueError("safe failure report contains a prohibited field")
    errors = payload.get("errors")
    if not isinstance(errors, list) or len(errors) > 1:
        raise ValueError("safe failure report errors must be a list")
    for row in errors:
        if not isinstance(row, Mapping):
            raise ValueError("safe failure row must be an object")
        if set(row) - {"failure_phase", "safe_error_code", "exception_kind"}:
            raise ValueError("safe failure row contains an unregistered field")
        if row.get("failure_phase") not in _PHASES:
            raise ValueError("safe failure phase is not allowlisted")
        if row.get("safe_error_code") not in SAFE_ERROR_CODES:
            raise ValueError("safe failure code is not allowlisted")
        exception_kind = row.get("exception_kind")
        if exception_kind is not None and exception_kind not in _EXCEPTION_KINDS:
            raise ValueError("safe failure exception kind is not allowlisted")
    downloads = payload.get("downloads")
    if not isinstance(downloads, list) or len(downloads) > 1:
        raise ValueError("safe failure downloads must contain at most one row")
    replay_succeeded = payload.get("feature_replay_succeeded") is True
    classified = payload.get("safe_failure_classified") is True
    if replay_succeeded == classified:
        raise ValueError("safe report must record exactly one terminal outcome")
    if replay_succeeded and (
        request_count != 1 or len(downloads) != 1 or errors
    ):
        raise ValueError("successful safe report is internally inconsistent")
    if classified and (
        len(errors) != 1
        or downloads
        or (request_count == 0 and payload.get("diagnostic_observation_complete") is True)
    ):
        raise ValueError("classified safe report is internally inconsistent")
    claimed = payload.get("content_sha256")
    if not isinstance(claimed, str) or not _SHA64.fullmatch(claimed):
        raise ValueError("safe failure report content hash is invalid")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("safe failure report fingerprint mismatch")


__all__ = [
    "ARTIFACT_TYPE",
    "CONTRACT_CONTENT_SHA256",
    "DIAGNOSTIC_CONTRACT_ID",
    "EXECUTION_AUTHORIZATION_ID",
    "FEATURE_ENGINE_SOURCE_FILE_SHA256",
    "MAX_PREFLIGHT_BILLABLE_SIZE_BYTES",
    "MAX_PREFLIGHT_COST_USD",
    "PARENT_ADAPTER_FILE_SHA256",
    "PARENT_FAILURE_AUDIT_ID",
    "PARENT_FAILURE_CONTENT_SHA256",
    "REQUEST",
    "REQUESTS",
    "RuntimeConstants",
    "SAFE_ERROR_CODES",
    "SafeDiagnosticFailure",
    "build_unavailable_report",
    "extract_classified_feature_diagnostic",
    "load_execution_authorization",
    "load_parent_failure_audit",
    "load_repair_contract",
    "run_safe_failure_classifier",
    "validate_execution_authorization",
    "validate_parent_failure_audit",
    "validate_repair_contract",
    "validate_safe_failure_report",
]
