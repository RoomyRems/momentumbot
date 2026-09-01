"""Provider-free pre-scanner checkpoint for sealed recovery v0.5.

The v0.5 child starts from the exact normalized source retained by failed run
33468687163.  This checkpoint therefore binds both the completed source tree
and the provider-free recovery receipt that proves its v0.4 parent.  Request
accounting is composite: the external ledger starts at the parent's 14,524
attempts and every child attempt increments that same ledger.

This module imports no provider client and performs no network access.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Mapping

from momentumbot.causal_market_discovery_v03 import load_market_candidate_payload
from momentumbot.research.sealed_historical_availability import SELECTED_DATES
from momentumbot.research.sealed_historical_source_checkpoint_v01 import (
    _environment_record,
    _inventory_file_map,
    _stage_root_records,
    _validate_blocked_attempts,
    _validate_checkpoint_inventory_subset,
    _validate_environment_record,
    _validate_stage_records,
    inventory_source_tree,
    load_json_object,
    output_is_outside_source_root,
    write_checkpoint_once,
)
from momentumbot.research.sealed_historical_source_recovery_v05 import (
    ARTIFACT_ID as RECOVERY_ARTIFACT_ID,
    PARENT_REQUEST_BUDGET,
)


SCHEMA_VERSION = 1
ARTIFACT_ID = "sealed-historical-source-checkpoint-v0.2"
ARTIFACT_TYPE = "sealed_historical_label_blind_source_recovery_checkpoint"
POST_SCANNER_BINDING_TYPE = (
    "sealed_historical_source_recovery_checkpoint_post_scanner_binding_v0.2"
)
AUTHORIZATION_ID = "sealed-historical-source-acquisition-v0.5"
RECOVERY_RECEIPT_BASENAME = "parent-recovery-receipt.json"
RECOVERY_RECEIPT_CONTENT_SHA256 = (
    "674ac119d07ba7308b2379e5702c1e3e21be5f534e929b3e8593f2ef0a037d9d"
)
EXPECTED_REPOSITORY = "RoomyRems/momentumbot"
EXPECTED_WORKFLOW_REF = (
    "RoomyRems/momentumbot/.github/workflows/"
    "sealed-historical-source-acquisition-v05.yml@refs/heads/main"
)
EXPECTED_DATES = tuple(SELECTED_DATES)
EXPECTED_ALLOWED_HOSTS = (
    "api.massive.com",
    "data.alpaca.markets",
    "data.sec.gov",
)
EXPECTED_PRE_SCANNER_FILE_COUNT = 706
EXPECTED_POST_SCANNER_FILE_COUNT = 767
MAX_HTTP_ATTEMPTS = 40_000
MAX_RETAINED_BYTES = 1_500_000_000
EXPECTED_SCANNER_ADDITION_ID = "causal-scanner-snapshot-v0.3"
NORMALIZATION_DIAGNOSTIC_ARTIFACT_ID = (
    "causal-float-normalization-rejections-v0.1"
)
NORMALIZATION_DIAGNOSTIC_BASENAME = "float-normalization-rejections.json"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_RUN_ID = re.compile(r"^[1-9][0-9]*$")

_CHECKPOINT_KEYS = frozenset(
    {
        "schema_version",
        "artifact_id",
        "artifact_type",
        "dates",
        "authorization",
        "provenance",
        "recovery",
        "normalization_diagnostics",
        "request_budget",
        "blocked_attempts",
        "environment",
        "stage_roots",
        "inventory",
        "total_retained_bytes",
        "causal_boundary",
        "content_sha256",
    }
)
_PROVENANCE_KEYS = frozenset(
    {
        "repository",
        "authorization_commit_sha",
        "authorization_tree_sha",
        "dispatcher_workflow_sha",
        "dispatcher_workflow_ref",
        "workflow_run_id",
        "workflow_run_attempt",
    }
)
_RECOVERY_KEYS = frozenset(
    {
        "artifact_id",
        "receipt_path",
        "receipt_size_bytes",
        "receipt_file_sha256",
        "receipt_content_sha256",
        "parent_request_budget_seed",
    }
)
_DIAGNOSTIC_KEYS = frozenset(
    {
        "artifact_id",
        "path",
        "size_bytes",
        "file_sha256",
        "content_sha256",
        "candidate_rejection_count",
    }
)
_POST_BINDING_KEYS = frozenset(
    {
        "schema_version",
        "binding_type",
        "checkpoint_artifact_id",
        "checkpoint_content_sha256",
        "checkpoint_file_sha256",
        "pre_scanner_tree_content_sha256",
        "pre_scanner_file_count",
        "pre_scanner_retained_file_bytes",
        "post_scanner_tree_content_sha256",
        "post_scanner_file_count",
        "post_scanner_retained_file_bytes",
        "environment",
        "request_budget",
        "blocked_attempts",
        "provenance",
        "authorization",
        "recovery",
        "normalization_diagnostics",
        "sole_permitted_addition_id",
        "content_sha256",
    }
)
_CAUSAL_BOUNDARY = {
    "account_or_order_endpoints_called": False,
    "labels_or_transcripts_read": False,
    "orders_submitted": False,
    "parent_normalized_source_reused_exactly": True,
    "parent_provider_requests_repeated": False,
    "provider_calls_performed_by_checkpoint_builder": False,
    "retrospective_outcomes_read": False,
    "scanner_snapshot_present": False,
}


def canonical_fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _strict_int(value: object, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def validate_authorization_envelope_v05(
    authorization: Mapping[str, object],
) -> dict[str, object]:
    payload = dict(authorization)
    claimed = payload.get("content_sha256")
    if not _is_sha256(claimed):
        raise ValueError("v0.5 authorization content hash is invalid")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if claimed != canonical_fingerprint(unsigned):
        raise ValueError("v0.5 authorization content hash mismatch")
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("authorization_id") != AUTHORIZATION_ID
    ):
        raise ValueError("authorization is not the frozen v0.5 child")

    authority = payload.get("authority_boundary")
    causal = payload.get("causal_boundary")
    one_shot = payload.get("one_shot_contract")
    if (
        not isinstance(authority, Mapping)
        or authority.get("historical_source_recovery_authorized") is not True
        or authority.get("live_order_authorized") is not False
        or authority.get("paper_order_authorized") is not False
        or not isinstance(causal, Mapping)
        or causal.get("ross_actions_fills_skips_or_outcomes_may_be_read") is not False
        or causal.get("transcript_record_values_may_be_read") is not False
        or not isinstance(one_shot, Mapping)
        or one_shot.get("automatic_rerun_allowed") is not False
        or one_shot.get("workflow_run_attempt_required") != 1
    ):
        raise ValueError("v0.5 authority or causal boundary changed")

    budget = payload.get("request_budget")
    if not isinstance(budget, Mapping):
        raise ValueError("v0.5 request budget is missing")
    if (
        budget.get("allowed_hosts") != list(EXPECTED_ALLOWED_HOSTS)
        or budget.get("composite_parent_attempts_by_host")
        != PARENT_REQUEST_BUDGET["by_host"]
        or budget.get("composite_parent_total_attempts")
        != PARENT_REQUEST_BUDGET["total_attempts"]
        or budget.get(
            "maximum_total_http_attempts_including_parent_and_child_retries"
        )
        != MAX_HTTP_ATTEMPTS
        or budget.get("child_massive_calls_authorized") != 0
    ):
        raise ValueError("v0.5 composite request boundary changed")
    retention = payload.get("retention_budget")
    if (
        not isinstance(retention, Mapping)
        or retention.get("maximum_retained_bytes") != MAX_RETAINED_BYTES
        or retention.get("raw_provider_http_responses_persisted") is not False
    ):
        raise ValueError("v0.5 retention boundary changed")
    recovery = payload.get("recovery_contract")
    if (
        not isinstance(recovery, Mapping)
        or recovery.get("parent_source_recovery_receipt_content_sha256")
        != RECOVERY_RECEIPT_CONTENT_SHA256
        or recovery.get("parent_identity_or_market_provider_requests_repeated")
        is not False
    ):
        raise ValueError("v0.5 recovery boundary changed")
    return payload


def load_authorization_envelope_v05(path: str | Path) -> dict[str, object]:
    return validate_authorization_envelope_v05(load_json_object(path))


def _provenance(
    *,
    repository: str,
    authorization_commit_sha: str,
    authorization_tree_sha: str,
    dispatcher_workflow_sha: str,
    dispatcher_workflow_ref: str,
    workflow_run_id: str,
    workflow_run_attempt: int,
) -> dict[str, object]:
    if repository != EXPECTED_REPOSITORY:
        raise ValueError("v0.5 checkpoint repository changed")
    for label, value in (
        ("authorization commit", authorization_commit_sha),
        ("authorization tree", authorization_tree_sha),
        ("dispatcher workflow", dispatcher_workflow_sha),
    ):
        if not isinstance(value, str) or _GIT_SHA.fullmatch(value) is None:
            raise ValueError(f"{label} must be a full lowercase Git SHA")
    if dispatcher_workflow_ref != EXPECTED_WORKFLOW_REF:
        raise ValueError("v0.5 dispatcher workflow ref changed")
    if not isinstance(workflow_run_id, str) or _RUN_ID.fullmatch(workflow_run_id) is None:
        raise ValueError("workflow run ID must be a positive decimal string")
    if isinstance(workflow_run_attempt, bool) or workflow_run_attempt != 1:
        raise ValueError("v0.5 checkpoint requires attempt 1")
    return {
        "repository": repository,
        "authorization_commit_sha": authorization_commit_sha,
        "authorization_tree_sha": authorization_tree_sha,
        "dispatcher_workflow_sha": dispatcher_workflow_sha,
        "dispatcher_workflow_ref": dispatcher_workflow_ref,
        "workflow_run_id": workflow_run_id,
        "workflow_run_attempt": workflow_run_attempt,
    }


def normalize_composite_request_budget(
    value: Mapping[str, object],
) -> dict[str, object]:
    if set(value) != {"schema_version", "total_attempts", "by_host"}:
        raise ValueError("composite request-budget fields changed")
    if value.get("schema_version") != 1:
        raise ValueError("composite request-budget schema changed")
    total = _strict_int(value.get("total_attempts"), label="composite request total")
    by_host = value.get("by_host")
    if not isinstance(by_host, Mapping):
        raise ValueError("composite request host accounting is invalid")
    clean: dict[str, int] = {}
    for host, count in by_host.items():
        if not isinstance(host, str) or host not in EXPECTED_ALLOWED_HOSTS:
            raise ValueError("composite request ledger contains an unauthorized host")
        clean[host] = _strict_int(count, label=f"request count for {host}")
    for host, seed in PARENT_REQUEST_BUDGET["by_host"].items():
        observed = clean.get(host, 0)
        if host == "api.massive.com" and observed != seed:
            raise ValueError("v0.5 repeated or omitted a parent Massive request")
        if observed < seed:
            raise ValueError("composite request ledger is below its parent seed")
    if sum(clean.values()) != total or total > MAX_HTTP_ATTEMPTS:
        raise ValueError("composite request counts are inconsistent")
    return {
        "schema_version": 1,
        "allowed_hosts": list(EXPECTED_ALLOWED_HOSTS),
        "maximum_total_http_attempts": MAX_HTTP_ATTEMPTS,
        "parent_total_attempts": PARENT_REQUEST_BUDGET["total_attempts"],
        "parent_by_host": dict(PARENT_REQUEST_BUDGET["by_host"]),
        "total_attempts": total,
        "child_attempts": total - int(PARENT_REQUEST_BUDGET["total_attempts"]),
        "by_host": dict(sorted(clean.items())),
    }


def normalize_blocked_attempt_ledger(
    value: Mapping[str, object],
    *,
    require_zero: bool = True,
) -> dict[str, object]:
    return _validate_blocked_attempts(value, require_zero=require_zero)


def _validate_composite_request_snapshot(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version",
        "allowed_hosts",
        "maximum_total_http_attempts",
        "parent_total_attempts",
        "parent_by_host",
        "total_attempts",
        "child_attempts",
        "by_host",
    }:
        raise ValueError("checkpoint composite request snapshot fields changed")
    external = {
        "schema_version": value.get("schema_version"),
        "total_attempts": value.get("total_attempts"),
        "by_host": value.get("by_host"),
    }
    normalized = normalize_composite_request_budget(external)
    if dict(value) != normalized:
        raise ValueError("checkpoint composite request snapshot is not canonical")
    return normalized


def _regular_external_file(
    path: str | Path,
    *,
    label: str,
    basename: str,
    source_root: Path,
    checkpoint_output_path: str | Path | None,
) -> Path:
    raw = Path(path)
    if ".." in raw.parts or raw.name != basename:
        raise ValueError(f"{label} path is not canonical")
    absolute = Path(os.path.abspath(raw))
    for component in (absolute, *absolute.parents):
        if component.is_symlink():
            raise ValueError(f"{label} path contains a symlink")
    if not absolute.is_file() or not stat.S_ISREG(absolute.stat().st_mode):
        raise ValueError(f"{label} must be a regular file")
    resolved = absolute.resolve(strict=True)
    root = source_root.resolve(strict=True)
    if resolved == root or root in resolved.parents:
        raise ValueError(f"{label} must be outside the source tree")
    if checkpoint_output_path is not None and resolved == Path(
        checkpoint_output_path
    ).resolve(strict=False):
        raise ValueError(f"{label} may not alias the checkpoint output")
    return resolved


def _recovery_record(
    receipt_path: str | Path,
    *,
    source_root: Path,
    checkpoint_output_path: str | Path | None,
) -> dict[str, object]:
    path = _regular_external_file(
        receipt_path,
        label="parent recovery receipt",
        basename=RECOVERY_RECEIPT_BASENAME,
        source_root=source_root,
        checkpoint_output_path=checkpoint_output_path,
    )
    receipt = load_json_object(path)
    if (
        receipt.get("artifact_id") != RECOVERY_ARTIFACT_ID
        or receipt.get("content_sha256") != RECOVERY_RECEIPT_CONTENT_SHA256
    ):
        raise ValueError("parent recovery receipt identity changed")
    unsigned = {key: value for key, value in receipt.items() if key != "content_sha256"}
    if receipt.get("content_sha256") != canonical_fingerprint(unsigned):
        raise ValueError("parent recovery receipt content hash mismatch")
    if receipt.get("request_budget_seed") != PARENT_REQUEST_BUDGET:
        raise ValueError("parent recovery receipt request seed changed")
    return {
        "artifact_id": RECOVERY_ARTIFACT_ID,
        "receipt_path": RECOVERY_RECEIPT_BASENAME,
        "receipt_size_bytes": path.stat().st_size,
        "receipt_file_sha256": _file_sha256(path),
        "receipt_content_sha256": RECOVERY_RECEIPT_CONTENT_SHA256,
        "parent_request_budget_seed": PARENT_REQUEST_BUDGET,
    }


def _validate_recovery_record(
    value: object,
    *,
    receipt_path: str | Path,
    source_root: Path,
    checkpoint_output_path: str | Path | None,
) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _RECOVERY_KEYS:
        raise ValueError("checkpoint recovery binding fields changed")
    observed = _recovery_record(
        receipt_path,
        source_root=source_root,
        checkpoint_output_path=checkpoint_output_path,
    )
    if dict(value) != observed:
        raise ValueError("checkpoint parent recovery receipt changed")
    return observed


def _normalization_diagnostic_record(
    diagnostic_path: str | Path,
    *,
    source_root: Path,
    checkpoint_output_path: str | Path | None,
) -> dict[str, object]:
    path = _regular_external_file(
        diagnostic_path,
        label="float normalization diagnostics",
        basename=NORMALIZATION_DIAGNOSTIC_BASENAME,
        source_root=source_root,
        checkpoint_output_path=checkpoint_output_path,
    )
    payload = load_json_object(path)
    if set(payload) != {
        "schema_version",
        "artifact_id",
        "candidate_rejection_count",
        "candidate_rejections",
        "causal_boundary",
        "content_sha256",
    }:
        raise ValueError("float normalization diagnostic payload fields changed")
    claimed = payload.get("content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if (
        payload.get("schema_version") != 1
        or payload.get("artifact_id") != NORMALIZATION_DIAGNOSTIC_ARTIFACT_ID
        or not _is_sha256(claimed)
        or claimed != canonical_fingerprint(unsigned)
    ):
        raise ValueError("float normalization diagnostic identity or hash changed")
    rows = payload.get("candidate_rejections")
    count = payload.get("candidate_rejection_count")
    if not isinstance(rows, list) or isinstance(count, bool) or count != len(rows):
        raise ValueError("float normalization diagnostic count changed")
    expected_row_keys = {
        "trading_date",
        "symbol",
        "stage",
        "exception_class",
        "disposition",
    }
    seen: set[tuple[str, str]] = set()
    candidate_symbols_by_date: dict[str, set[str]] = {}
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or set(row) != expected_row_keys
            or row.get("exception_class") not in {"TypeError", "ValueError"}
            or row.get("stage")
            != "measure_basis_provider_data_normalization"
            or row.get("disposition")
            != "unknown_fail_closed_missing_measure_pair"
            or not isinstance(row.get("symbol"), str)
            or not row.get("symbol")
            or row.get("trading_date") not in EXPECTED_DATES
        ):
            raise ValueError("float normalization diagnostic row changed")
        trading_date = str(row["trading_date"])
        symbol = str(row["symbol"])
        identity = (trading_date, symbol)
        if identity in seen:
            raise ValueError("float normalization diagnostics repeat a candidate")
        seen.add(identity)
        if trading_date not in candidate_symbols_by_date:
            candidate_rows, _, _ = load_market_candidate_payload(
                source_root / "causal-market-discovery-v0.3" / trading_date
            )
            candidate_symbols_by_date[trading_date] = {
                str(candidate["symbol"]) for candidate in candidate_rows
            }
        if symbol not in candidate_symbols_by_date[trading_date]:
            raise ValueError("float normalization diagnostic symbol is not a candidate")
    if rows != sorted(
        rows,
        key=lambda row: (
            str(row["trading_date"]),
            str(row["symbol"]),
            str(row["stage"]),
            str(row["exception_class"]),
        ),
    ):
        raise ValueError("float normalization diagnostics are not canonical")
    if payload.get("causal_boundary") != {
        "candidate_scope_only": True,
        "exception_messages_persisted": False,
        "raw_provider_http_responses_persisted": False,
        "strategy_thresholds_changed": False,
        "transcript_or_label_values_read": False,
    }:
        raise ValueError("float normalization diagnostic boundary changed")
    return {
        "artifact_id": NORMALIZATION_DIAGNOSTIC_ARTIFACT_ID,
        "path": NORMALIZATION_DIAGNOSTIC_BASENAME,
        "size_bytes": path.stat().st_size,
        "file_sha256": _file_sha256(path),
        "content_sha256": claimed,
        "candidate_rejection_count": count,
    }


def _validate_normalization_diagnostic_record(
    value: object,
    *,
    diagnostic_path: str | Path,
    source_root: Path,
    checkpoint_output_path: str | Path | None,
) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _DIAGNOSTIC_KEYS:
        raise ValueError("checkpoint normalization diagnostic binding changed")
    observed = _normalization_diagnostic_record(
        diagnostic_path,
        source_root=source_root,
        checkpoint_output_path=checkpoint_output_path,
    )
    if dict(value) != observed:
        raise ValueError("checkpoint float normalization diagnostics changed")
    return observed


def build_source_checkpoint_v05(
    *,
    source_root: str | Path,
    authorization: Mapping[str, object],
    recovery_receipt_path: str | Path,
    normalization_diagnostic_path: str | Path,
    request_budget: Mapping[str, object],
    blocked_attempt_ledger: Mapping[str, object],
    environment_freeze_path: str | Path,
    requirements_path: str | Path,
    checkpoint_output_path: str | Path | None,
    repository: str,
    authorization_commit_sha: str,
    authorization_tree_sha: str,
    dispatcher_workflow_sha: str,
    dispatcher_workflow_ref: str,
    workflow_run_id: str,
    workflow_run_attempt: int,
) -> dict[str, object]:
    auth = validate_authorization_envelope_v05(authorization)
    root = Path(source_root)
    inventory = inventory_source_tree(root)
    files = _inventory_file_map(inventory)
    if inventory.get("file_count") != EXPECTED_PRE_SCANNER_FILE_COUNT:
        raise ValueError("v0.5 pre-scanner file count changed")
    retained = sum(int(row["size_bytes"]) for row in files.values())
    if retained > MAX_RETAINED_BYTES:
        raise ValueError("v0.5 checkpoint exceeds retained-byte ceiling")
    checkpoint: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": ARTIFACT_ID,
        "artifact_type": ARTIFACT_TYPE,
        "dates": list(EXPECTED_DATES),
        "authorization": {
            "authorization_id": AUTHORIZATION_ID,
            "authorization_content_sha256": auth["content_sha256"],
        },
        "provenance": _provenance(
            repository=repository,
            authorization_commit_sha=authorization_commit_sha,
            authorization_tree_sha=authorization_tree_sha,
            dispatcher_workflow_sha=dispatcher_workflow_sha,
            dispatcher_workflow_ref=dispatcher_workflow_ref,
            workflow_run_id=workflow_run_id,
            workflow_run_attempt=workflow_run_attempt,
        ),
        "recovery": _recovery_record(
            recovery_receipt_path,
            source_root=root,
            checkpoint_output_path=checkpoint_output_path,
        ),
        "normalization_diagnostics": _normalization_diagnostic_record(
            normalization_diagnostic_path,
            source_root=root,
            checkpoint_output_path=checkpoint_output_path,
        ),
        "request_budget": normalize_composite_request_budget(request_budget),
        "blocked_attempts": _validate_blocked_attempts(
            blocked_attempt_ledger,
            require_zero=True,
        ),
        "environment": _environment_record(
            environment_freeze_path=environment_freeze_path,
            requirements_path=requirements_path,
            source_root=root,
            checkpoint_output_path=checkpoint_output_path,
        ),
        "stage_roots": _stage_root_records(root, inventory),
        "inventory": inventory,
        "total_retained_bytes": retained,
        "causal_boundary": dict(_CAUSAL_BOUNDARY),
    }
    checkpoint["content_sha256"] = canonical_fingerprint(checkpoint)
    validate_source_checkpoint_v05(
        checkpoint,
        recovery_receipt_path=recovery_receipt_path,
        normalization_diagnostic_path=normalization_diagnostic_path,
        environment_freeze_path=environment_freeze_path,
        requirements_path=requirements_path,
        checkpoint_output_path=checkpoint_output_path,
        source_root=root,
        authorization=auth,
        expected_provenance=checkpoint["provenance"],  # type: ignore[arg-type]
    )
    return checkpoint


def validate_source_checkpoint_v05(
    checkpoint: Mapping[str, object],
    *,
    recovery_receipt_path: str | Path,
    normalization_diagnostic_path: str | Path,
    environment_freeze_path: str | Path,
    requirements_path: str | Path,
    checkpoint_output_path: str | Path | None = None,
    source_root: str | Path,
    authorization: Mapping[str, object] | None = None,
    expected_provenance: Mapping[str, object] | None = None,
    allow_scanner_snapshot_addition: bool = False,
) -> dict[str, object]:
    payload = dict(checkpoint)
    if set(payload) != _CHECKPOINT_KEYS:
        raise ValueError("v0.5 checkpoint keys changed")
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("artifact_id") != ARTIFACT_ID
        or payload.get("artifact_type") != ARTIFACT_TYPE
        or payload.get("dates") != list(EXPECTED_DATES)
    ):
        raise ValueError("unsupported v0.5 source checkpoint")
    claimed = payload.get("content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if not _is_sha256(claimed) or claimed != canonical_fingerprint(unsigned):
        raise ValueError("v0.5 checkpoint content hash mismatch")
    auth_binding = payload.get("authorization")
    if not isinstance(auth_binding, Mapping) or set(auth_binding) != {
        "authorization_id",
        "authorization_content_sha256",
    } or auth_binding.get("authorization_id") != AUTHORIZATION_ID or not _is_sha256(
        auth_binding.get("authorization_content_sha256")
    ):
        raise ValueError("v0.5 checkpoint authorization binding changed")
    provenance = payload.get("provenance")
    if not isinstance(provenance, Mapping) or set(provenance) != _PROVENANCE_KEYS:
        raise ValueError("v0.5 checkpoint provenance is invalid")
    canonical_provenance = _provenance(**dict(provenance))  # type: ignore[arg-type]
    if dict(provenance) != canonical_provenance:
        raise ValueError("v0.5 checkpoint provenance is not canonical")
    if expected_provenance is not None and dict(provenance) != dict(expected_provenance):
        raise ValueError("v0.5 checkpoint provenance differs from the expected run")

    root = Path(source_root)
    _validate_recovery_record(
        payload.get("recovery"),
        receipt_path=recovery_receipt_path,
        source_root=root,
        checkpoint_output_path=checkpoint_output_path,
    )
    _validate_normalization_diagnostic_record(
        payload.get("normalization_diagnostics"),
        diagnostic_path=normalization_diagnostic_path,
        source_root=root,
        checkpoint_output_path=checkpoint_output_path,
    )
    _validate_composite_request_snapshot(payload.get("request_budget"))
    _validate_blocked_attempts(payload.get("blocked_attempts"), require_zero=True)
    _validate_environment_record(
        payload.get("environment"),
        environment_freeze_path=environment_freeze_path,
        requirements_path=requirements_path,
        source_root=root,
        checkpoint_output_path=checkpoint_output_path,
    )
    inventory = payload.get("inventory")
    if not isinstance(inventory, Mapping):
        raise ValueError("v0.5 checkpoint inventory is missing")
    files = _inventory_file_map(inventory)
    if inventory.get("file_count") != EXPECTED_PRE_SCANNER_FILE_COUNT:
        raise ValueError("v0.5 pre-scanner file count changed")
    _validate_stage_records(payload.get("stage_roots"), inventory_file_map=files)
    retained = _strict_int(
        payload.get("total_retained_bytes"), label="checkpoint retained bytes"
    )
    if retained != sum(int(row["size_bytes"]) for row in files.values()):
        raise ValueError("v0.5 checkpoint retained-byte total changed")
    if payload.get("causal_boundary") != _CAUSAL_BOUNDARY:
        raise ValueError("v0.5 checkpoint causal boundary changed")

    if authorization is not None:
        auth = validate_authorization_envelope_v05(authorization)
        if dict(auth_binding) != {
            "authorization_id": AUTHORIZATION_ID,
            "authorization_content_sha256": auth["content_sha256"],
        }:
            raise ValueError("v0.5 checkpoint is bound to a different authorization")
    observed = inventory_source_tree(
        root,
        allow_scanner_snapshot_addition=allow_scanner_snapshot_addition,
    )
    if allow_scanner_snapshot_addition:
        _validate_checkpoint_inventory_subset(inventory, observed, source_root=root)
        if observed.get("file_count") != EXPECTED_POST_SCANNER_FILE_COUNT:
            raise ValueError("v0.5 post-scanner file count changed")
    elif observed != inventory:
        raise ValueError("v0.5 source tree changed after checkpoint")
    if _stage_root_records(root, observed) != payload.get("stage_roots"):
        raise ValueError("v0.5 source stage manifests changed after checkpoint")
    return payload


def build_post_scanner_checkpoint_binding_v05(
    checkpoint: Mapping[str, object],
    *,
    checkpoint_file_sha256: str,
    checkpoint_output_path: str | Path,
    source_root: str | Path,
    authorization: Mapping[str, object],
    recovery_receipt_path: str | Path,
    normalization_diagnostic_path: str | Path,
    expected_provenance: Mapping[str, object],
    environment_freeze_path: str | Path,
    requirements_path: str | Path,
) -> dict[str, object]:
    if not _is_sha256(checkpoint_file_sha256):
        raise ValueError("v0.5 checkpoint file SHA-256 is invalid")
    root = Path(source_root)
    path = _regular_external_file(
        checkpoint_output_path,
        label="source checkpoint",
        basename="source-checkpoint.json",
        source_root=root,
        checkpoint_output_path=None,
    )
    if _file_sha256(path) != checkpoint_file_sha256:
        raise ValueError("v0.5 checkpoint file hash mismatch")
    if load_json_object(path) != dict(checkpoint):
        raise ValueError("v0.5 checkpoint file payload changed")
    validated = validate_source_checkpoint_v05(
        checkpoint,
        recovery_receipt_path=recovery_receipt_path,
        normalization_diagnostic_path=normalization_diagnostic_path,
        environment_freeze_path=environment_freeze_path,
        requirements_path=requirements_path,
        checkpoint_output_path=path,
        source_root=root,
        authorization=authorization,
        expected_provenance=expected_provenance,
        allow_scanner_snapshot_addition=True,
    )
    final_inventory = inventory_source_tree(
        root, allow_scanner_snapshot_addition=True
    )
    final_files = _inventory_file_map(final_inventory)
    pre_inventory = validated["inventory"]
    if not isinstance(pre_inventory, Mapping):
        raise ValueError("v0.5 validated pre-scanner inventory is invalid")
    binding: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "binding_type": POST_SCANNER_BINDING_TYPE,
        "checkpoint_artifact_id": ARTIFACT_ID,
        "checkpoint_content_sha256": validated["content_sha256"],
        "checkpoint_file_sha256": checkpoint_file_sha256,
        "pre_scanner_tree_content_sha256": pre_inventory["tree_content_sha256"],
        "pre_scanner_file_count": pre_inventory["file_count"],
        "pre_scanner_retained_file_bytes": validated["total_retained_bytes"],
        "post_scanner_tree_content_sha256": final_inventory["tree_content_sha256"],
        "post_scanner_file_count": final_inventory["file_count"],
        "post_scanner_retained_file_bytes": sum(
            int(row["size_bytes"]) for row in final_files.values()
        ),
        "environment": validated["environment"],
        "request_budget": validated["request_budget"],
        "blocked_attempts": validated["blocked_attempts"],
        "provenance": validated["provenance"],
        "authorization": validated["authorization"],
        "recovery": validated["recovery"],
        "normalization_diagnostics": validated["normalization_diagnostics"],
        "sole_permitted_addition_id": EXPECTED_SCANNER_ADDITION_ID,
    }
    binding["content_sha256"] = canonical_fingerprint(binding)
    return validate_post_scanner_checkpoint_binding_v05(binding)


def validate_post_scanner_checkpoint_binding_v05(
    value: Mapping[str, object],
) -> dict[str, object]:
    binding = dict(value)
    if set(binding) != _POST_BINDING_KEYS:
        raise ValueError("v0.5 post-scanner checkpoint binding fields changed")
    claimed = binding.get("content_sha256")
    unsigned = {key: item for key, item in binding.items() if key != "content_sha256"}
    if not _is_sha256(claimed) or claimed != canonical_fingerprint(unsigned):
        raise ValueError("v0.5 post-scanner checkpoint binding hash mismatch")
    if (
        binding.get("schema_version") != SCHEMA_VERSION
        or binding.get("binding_type") != POST_SCANNER_BINDING_TYPE
        or binding.get("checkpoint_artifact_id") != ARTIFACT_ID
        or binding.get("sole_permitted_addition_id")
        != EXPECTED_SCANNER_ADDITION_ID
    ):
        raise ValueError("v0.5 post-scanner checkpoint binding identity changed")
    for key in (
        "checkpoint_content_sha256",
        "checkpoint_file_sha256",
        "pre_scanner_tree_content_sha256",
        "post_scanner_tree_content_sha256",
    ):
        if not _is_sha256(binding.get(key)):
            raise ValueError(f"v0.5 checkpoint {key} is invalid")
    pre_count = _strict_int(
        binding.get("pre_scanner_file_count"), label="pre-scanner file count"
    )
    post_count = _strict_int(
        binding.get("post_scanner_file_count"), label="post-scanner file count"
    )
    if (
        pre_count != EXPECTED_PRE_SCANNER_FILE_COUNT
        or post_count != EXPECTED_POST_SCANNER_FILE_COUNT
        or post_count != pre_count + 1 + (2 * len(EXPECTED_DATES))
    ):
        raise ValueError("v0.5 scanner-only file addition count changed")
    pre_bytes = _strict_int(
        binding.get("pre_scanner_retained_file_bytes"),
        label="pre-scanner retained bytes",
        minimum=1,
    )
    post_bytes = _strict_int(
        binding.get("post_scanner_retained_file_bytes"),
        label="post-scanner retained bytes",
        minimum=1,
    )
    if post_bytes <= pre_bytes:
        raise ValueError("v0.5 scanner addition retained no bytes")
    _validate_composite_request_snapshot(binding.get("request_budget"))
    _validate_blocked_attempts(binding.get("blocked_attempts"), require_zero=True)
    authorization = binding.get("authorization")
    if (
        not isinstance(authorization, Mapping)
        or set(authorization)
        != {"authorization_id", "authorization_content_sha256"}
        or authorization.get("authorization_id") != AUTHORIZATION_ID
        or not _is_sha256(authorization.get("authorization_content_sha256"))
    ):
        raise ValueError("v0.5 checkpoint authorization binding changed")
    provenance = binding.get("provenance")
    if not isinstance(provenance, Mapping) or set(provenance) != _PROVENANCE_KEYS:
        raise ValueError("v0.5 checkpoint provenance binding changed")
    if dict(provenance) != _provenance(**dict(provenance)):  # type: ignore[arg-type]
        raise ValueError("v0.5 checkpoint provenance binding is not canonical")
    recovery = binding.get("recovery")
    if (
        not isinstance(recovery, Mapping)
        or set(recovery) != _RECOVERY_KEYS
        or recovery.get("artifact_id") != RECOVERY_ARTIFACT_ID
        or recovery.get("receipt_path") != RECOVERY_RECEIPT_BASENAME
        or recovery.get("receipt_content_sha256")
        != RECOVERY_RECEIPT_CONTENT_SHA256
        or recovery.get("parent_request_budget_seed") != PARENT_REQUEST_BUDGET
        or not _is_sha256(recovery.get("receipt_file_sha256"))
    ):
        raise ValueError("v0.5 checkpoint recovery binding changed")
    _strict_int(recovery.get("receipt_size_bytes"), label="recovery receipt size", minimum=1)
    diagnostics = binding.get("normalization_diagnostics")
    if (
        not isinstance(diagnostics, Mapping)
        or set(diagnostics) != _DIAGNOSTIC_KEYS
        or diagnostics.get("artifact_id")
        != NORMALIZATION_DIAGNOSTIC_ARTIFACT_ID
        or diagnostics.get("path") != NORMALIZATION_DIAGNOSTIC_BASENAME
        or not _is_sha256(diagnostics.get("file_sha256"))
        or not _is_sha256(diagnostics.get("content_sha256"))
    ):
        raise ValueError("v0.5 checkpoint normalization diagnostics binding changed")
    _strict_int(diagnostics.get("size_bytes"), label="diagnostic size", minimum=1)
    _strict_int(
        diagnostics.get("candidate_rejection_count"),
        label="candidate rejection count",
    )
    environment = binding.get("environment")
    if not isinstance(environment, Mapping) or set(environment) != {
        "freeze_path",
        "freeze_size_bytes",
        "freeze_sha256",
        "requirements_path",
        "requirements_size_bytes",
        "requirements_sha256",
    }:
        raise ValueError("v0.5 checkpoint environment binding changed")
    if (
        environment.get("freeze_path") != "environment/pip-freeze.txt"
        or environment.get("requirements_path")
        != "environment/requirements-sealed-source-v04.txt"
        or not _is_sha256(environment.get("freeze_sha256"))
        or not _is_sha256(environment.get("requirements_sha256"))
    ):
        raise ValueError("v0.5 checkpoint environment binding is invalid")
    _strict_int(environment.get("freeze_size_bytes"), label="freeze size", minimum=1)
    _strict_int(
        environment.get("requirements_size_bytes"),
        label="requirements size",
        minimum=1,
    )
    return binding


__all__ = [
    "ARTIFACT_ID",
    "POST_SCANNER_BINDING_TYPE",
    "build_post_scanner_checkpoint_binding_v05",
    "build_source_checkpoint_v05",
    "canonical_fingerprint",
    "load_authorization_envelope_v05",
    "normalize_blocked_attempt_ledger",
    "normalize_composite_request_budget",
    "output_is_outside_source_root",
    "validate_post_scanner_checkpoint_binding_v05",
    "validate_source_checkpoint_v05",
    "write_checkpoint_once",
]
