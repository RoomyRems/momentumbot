"""One-shot metadata-only quote for the exact historical execution input plan."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re

from momentumbot.research.sealed_historical_execution_inputs_v01 import (
    seal, validate_registration,
)
from momentumbot.research.sealed_historical_micro_inputs_v01 import file_sha, frozen
from momentumbot.research.sealed_historical_source_checkpoint_v01 import canonical_fingerprint

CONTRACT_ID = "sealed-historical-execution-input-quote-v0.1"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
EXECUTION_PATH = f"research/strategy/{CONTRACT_ID}-execution.json"
CONSUMPTION_REF = f"refs/tags/{CONTRACT_ID}-consumed"
WORKFLOW_PATH = ".github/workflows/sealed-historical-execution-input-quote-v01.yml"
PLAN_PATH = "research/runtime/sealed-historical-execution-input-plan-v0.1"
SDK_VERSION = "0.83.0"
LOCK_PATH = "requirements-sealed-execution-quote-v01.txt"
LOCK_SHA256 = "03f4da335027e4c83bcf38e523c2e11aeaae49778f5bd6caa47e4703348b31b4"
PLAN_INVENTORY_SHA256 = "6aa9208ce5d37998021dcf09f30fb68ca3e5184b4505ea25c42f3f80b8ab38c1"
REQUEST_LIST_SHA256 = "4515172de55e48d42f1312b5b298dd2c126fccea700b39417cf600221d76e8ce"
METHODS = ("get_billable_size", "get_cost")
MAX_CALLS = 180
SAFE_ERRORS = {"provider_error", "invalid_result", "blocked_request", "http_error", "network_error", "response_too_large"}
PREFLIGHT_ERRORS = {"credential_missing", "sdk_unavailable", "sdk_version_mismatch", "client_initialization_failed"}


def require_exact(actual: dict, expected: dict, label: str) -> None:
    if canonical_fingerprint(actual) != canonical_fingerprint(expected):
        raise ValueError(f"{label} differs from frozen metadata quote contract")


def registered_contract() -> dict:
    return seal({
        "schema_version": 1, "contract_id": CONTRACT_ID,
        "artifact_type": "preregistered_historical_execution_metadata_quote",
        "parent_commit_sha": "3af740c7ed80d04ba604399fa26b9d369d246271",
        "parent_tree_sha": "c91806b2929c714036dba3fc724ec790b627eca9",
        "input_plan_inventory_sha256": PLAN_INVENTORY_SHA256,
        "request_list_content_sha256": REQUEST_LIST_SHA256,
        "request_count": 90, "opportunity_count": 109, "date_count": 30,
        "sdk_version": SDK_VERSION, "python_version": "3.12.14",
        "requirements_path": LOCK_PATH, "requirements_file_sha256": LOCK_SHA256,
        "provider_methods": list(METHODS), "maximum_metadata_calls": MAX_CALLS,
        "maximum_http_attempts": MAX_CALLS, "maximum_response_bytes": 65536,
        "http_timeout_seconds": 30, "retry_count": 0, "redirects_allowed": False,
        "gateway": "https://hist.databento.com", "dataset": "XNAS.ITCH",
        "consumption_ref": CONSUMPTION_REF, "attempt": 1,
        "durable_consumption_before_provider_required": True,
        "scope": "every_exact_request_size_and_cost_in_frozen_order",
        "quote_gate": "all_90_requests_complete_nonzero_size_no_errors_or_blocked_attempts",
        "zero_size_or_unknown_status": "unavailable_without_substitution",
        "spend_authorized_usd": "0", "timeseries_or_broker_access_authorized": False,
        "policy_change_authorized": False, "retrospective_access_authorized": False,
        "account_or_fill_simulation_authorized": False,
        "next_gate": "independently_verified_quote_bound_bounded_execution_input_acquisition",
    })


def validate_inputs(root: Path) -> list[dict]:
    require_exact(frozen(root / CONTRACT_PATH), registered_contract(), "registration")
    if file_sha(root / LOCK_PATH) != LOCK_SHA256:
        raise ValueError("metadata quote dependency lock changed")
    report = validate_registration(
        repo_root=root, micro_root=root / "research/runtime/sealed-historical-micro-v0.1",
        scanner_root=root / "research/runtime/sealed-historical-scanner-activation-v0.2",
        output_root=root / PLAN_PATH,
    )
    if report["inventory_content_sha256"] != PLAN_INVENTORY_SHA256:
        raise ValueError("exact historical request plan changed")
    requests = frozen(root / PLAN_PATH / "request-manifest.json")["requests"]
    validate_requests(requests)
    return requests


def validate_requests(requests: list[dict]) -> None:
    if len(requests) != 90 or canonical_fingerprint(requests) != REQUEST_LIST_SHA256:
        raise ValueError("exact historical metadata requests changed")


def execution_payload(*, code_commit: str, code_tree: str, workflow_sha256: str,
                      ci_run_id: str, validation_run_id: str) -> dict:
    for value, length in ((code_commit, 40), (code_tree, 40), (workflow_sha256, 64)):
        if not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
            raise ValueError("full execution provenance is required")
    for value in (ci_run_id, validation_run_id):
        if not re.fullmatch(r"[1-9][0-9]+", value):
            raise ValueError("exact successful validation runs are required")
    return seal({
        "schema_version": 1, "execution_id": CONTRACT_ID + "-execution",
        "contract_content_sha256": registered_contract()["content_sha256"],
        "code_commit_sha": code_commit, "code_tree_sha": code_tree,
        "workflow_path": WORKFLOW_PATH, "workflow_file_sha256": workflow_sha256,
        "code_ci_run_id": ci_run_id, "code_validation_run_id": validation_run_id,
        "repository": "RoomyRems/momentumbot", "branch": "phase-3-historical-snapshot",
        "event": "push", "run_attempt": 1, "consumption_ref": CONSUMPTION_REF,
        "authority": "user_authorized_continued_development_and_operational_steps_2026-09-06",
        "metadata_only_quote_authorized": True, "maximum_metadata_calls": MAX_CALLS,
        "request_list_content_sha256": REQUEST_LIST_SHA256,
        "time_series_acquisition_authorized": False, "provider_spend_authorized_usd": "0",
    })


def validate_execution(root: Path, env: dict) -> dict:
    execution = frozen(root / EXECUTION_PATH)
    expected = execution_payload(
        code_commit=env.get("EXECUTION_CODE_COMMIT_SHA", ""),
        code_tree=env.get("EXECUTION_CODE_TREE_SHA", ""),
        workflow_sha256=file_sha(root / WORKFLOW_PATH),
        ci_run_id=execution.get("code_ci_run_id", ""),
        validation_run_id=execution.get("code_validation_run_id", ""),
    )
    require_exact(execution, expected, "execution child")
    for key, value in {"GITHUB_REPOSITORY": "RoomyRems/momentumbot", "GITHUB_EVENT_NAME": "push",
                       "GITHUB_REF": "refs/heads/phase-3-historical-snapshot", "GITHUB_RUN_ATTEMPT": "1"}.items():
        if env.get(key) != value:
            raise ValueError("quote requires the first exact research push")
    if not re.fullmatch(r"[0-9a-f]{40}", env.get("GITHUB_SHA", "")) or not re.fullmatch(r"[1-9][0-9]+", env.get("GITHUB_RUN_ID", "")):
        raise ValueError("exact quote execution commit and run are required")
    return execution


def consumption_payload(execution: dict, env: dict) -> dict:
    return seal({"execution_content_sha256": execution["content_sha256"],
                 "consumption_ref": CONSUMPTION_REF, "execution_commit_sha": env["GITHUB_SHA"],
                 "workflow_run_id": env["GITHUB_RUN_ID"], "workflow_run_attempt": 1})


def request_kwargs(request: dict) -> dict:
    def stamp(ns: int) -> str:
        seconds, nanos = divmod(ns, 1_000_000_000)
        return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%S") + f".{nanos:09d}Z"
    return {"dataset": request["dataset"], "schema": request["schema"],
            "symbols": list(request["symbols"]), "stype_in": request["stype_in"],
            "start": stamp(request["start_ns"]), "end": stamp(request["end_ns"])}


def _value(method: str, value):
    if method == "get_billable_size":
        if type(value) is not int or value < 0:
            raise ValueError("invalid result")
        return value
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("invalid result")
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("invalid result") from None
    if not number.is_finite() or number < 0:
        raise ValueError("invalid result")
    return format(number, "f")


class MetadataFailure(Exception):
    def __init__(self, code: str):
        self.code = code if code in SAFE_ERRORS else "provider_error"
        super().__init__(self.code)


def collect_quote(requests: list[dict], metadata, *, progress=None) -> list[dict]:
    validate_requests(requests)
    calls = []
    for request in requests:
        for method in METHODS:
            entry = {"ordinal": len(calls) + 1, "request_id": request["request_id"],
                     "request_content_sha256": canonical_fingerprint(request),
                     "method": method, "status": "pending", "value": None, "error": None}
            calls.append(entry)
            if progress:
                progress(seal({"calls": calls, "call_count": len(calls), "complete": False}))
            try:
                value = getattr(metadata, method)(**request_kwargs(request))
            except MetadataFailure as exc:
                entry.update(status="error", error=exc.code)
            except Exception:
                entry.update(status="error", error="provider_error")
            else:
                try:
                    entry.update(status="success", value=_value(method, value))
                except ValueError:
                    entry.update(status="error", error="invalid_result")
            if progress:
                progress(seal({"calls": calls, "call_count": len(calls), "complete": len(calls) == MAX_CALLS}))
    return calls


def build_report(requests: list[dict], calls: list[dict], *, provenance: dict,
                 http_attempts: int, blocked_attempts: int, preflight_error: str | None = None) -> dict:
    validate_requests(requests)
    if type(http_attempts) is not int or not 0 <= http_attempts <= MAX_CALLS or type(blocked_attempts) is not int or blocked_attempts < 0:
        raise ValueError("invalid metadata HTTP accounting")
    if preflight_error is not None and preflight_error not in PREFLIGHT_ERRORS:
        raise ValueError("invalid sanitized preflight failure")
    if len(calls) not in (0, MAX_CALLS) or (not calls) != (preflight_error is not None):
        raise ValueError("terminal quote must retain every call or a preflight failure")
    rows = []
    for i, request in enumerate(requests):
        values = []
        for j, method in enumerate(METHODS):
            if not calls:
                values.append(None)
                continue
            entry = calls[2*i+j]
            if set(entry) != {"ordinal", "request_id", "request_content_sha256", "method", "status", "value", "error"}:
                raise ValueError("quote call fields changed")
            expected = {"ordinal": 2*i+j+1, "request_id": request["request_id"],
                        "request_content_sha256": canonical_fingerprint(request), "method": method}
            require_exact({k: entry[k] for k in expected}, expected, "call identity")
            if entry["status"] == "success":
                if entry["error"] is not None or _value(method, entry["value"]) != entry["value"]:
                    raise ValueError("quote success result is malformed")
                values.append(entry["value"])
            elif entry["status"] == "error" and entry["error"] in SAFE_ERRORS and entry["value"] is None:
                values.append(None)
            else:
                raise ValueError("quote call is incomplete or unsanitized")
        size, cost = values
        complete = size is not None and cost is not None
        available = complete and size > 0
        rows.append({"request_id": request["request_id"], "schema": request["schema"],
                     "billable_size_bytes": size, "quoted_cost_usd": cost,
                     "quote_complete": complete, "available": available,
                     "status": "available" if available else ("zero_billable_size" if complete else "quote_incomplete")})
    complete = all(row["quote_complete"] for row in rows)
    success_count = sum(entry["status"] == "success" for entry in calls)
    if http_attempts > len(calls) or success_count > http_attempts:
        raise ValueError("metadata result contradicts HTTP accounting")
    passed = complete and all(row["available"] for row in rows) and http_attempts == MAX_CALLS and blocked_attempts == 0
    return seal({
        "schema_version": 1, "artifact_type": "historical_execution_input_metadata_quote",
        "contract_id": CONTRACT_ID, "contract_content_sha256": registered_contract()["content_sha256"],
        "request_list_content_sha256": REQUEST_LIST_SHA256, "input_plan_inventory_sha256": PLAN_INVENTORY_SHA256,
        "provenance": provenance, "sdk_version": SDK_VERSION, "request_count": 90,
        "metadata_call_count": len(calls), "http_attempts": http_attempts,
        "blocked_attempts": blocked_attempts, "maximum_metadata_calls": MAX_CALLS,
        "preflight_error": preflight_error, "calls": calls, "quote_rows": rows,
        "complete_request_count": sum(r["quote_complete"] for r in rows),
        "available_request_count": sum(r["available"] for r in rows),
        "total_billable_size_bytes": sum(r["billable_size_bytes"] for r in rows) if complete else None,
        "total_quoted_cost_usd": format(sum((Decimal(r["quoted_cost_usd"]) for r in rows), Decimal(0)), "f") if complete else None,
        "metadata_quote_gate_passed": passed,
        "status": "complete" if passed else "blocked",
        "timeseries_acquired": False, "provider_credential_or_error_text_persisted": False,
        "automatic_retry_attempted": False, "request_substitution_attempted": False,
        "account_or_fill_simulation_executed": False, "backtesting_executed": False,
        "retrospective_inputs_loaded": False, "policy_changed": False,
        "download_authorized_by_this_artifact": False,
    })


def validate_report(report: dict, requests: list[dict], provenance: dict) -> None:
    expected = build_report(requests, report.get("calls", []), provenance=provenance,
                            http_attempts=report.get("http_attempts"), blocked_attempts=report.get("blocked_attempts"),
                            preflight_error=report.get("preflight_error"))
    require_exact(report, expected, "quote report")


def write_json(path: Path, payload: dict, *, replace: bool = False) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if replace:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(rendered)
        temporary.replace(path)
    else:
        with path.open("x") as handle:
            handle.write(rendered)
