"""Exact retained-source reuse and one-shot management exit metadata quote.

This child preserves the frozen runner, original entry inputs and all unavailable
opportunities. Only the 80 previously registered missing requests may be quoted.
"""
from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import re

from momentumbot.research import sealed_historical_management_runner_v01 as runner
from momentumbot.research import sealed_historical_execution_availability_v01 as availability
from momentumbot.research.sealed_historical_execution_quote_v01 import (
    METHODS, SDK_VERSION, LOCK_PATH, LOCK_SHA256, SAFE_ERRORS, PREFLIGHT_ERRORS,
    MetadataFailure, _value, request_kwargs, write_json,
    seal, frozen, file_sha, canonical_fingerprint, require_exact,
)

CONTRACT_ID = "sealed-historical-management-exit-quote-v0.1"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
EXECUTION_PATH = f"research/strategy/{CONTRACT_ID}-execution.json"
CONSUMPTION_REF = f"refs/tags/{CONTRACT_ID}-consumed"
WORKFLOW_PATH = ".github/workflows/sealed-historical-management-exit-quote-v01.yml"
PLAN_PATH = f"research/runtime/{CONTRACT_ID}"
EXIT_PLAN_PATH = runner.OUTPUT_PATH + "/exit-input-request-plan.json"
REUSE_PATH = f"research/data-audits/{CONTRACT_ID}-xage-reuse.json"
REUSE_FILE_SHA256 = "799d8664916eb89f713dec276134400e87434251ff97ea5c0b0a29219983e75b"
PARENT_COMMIT = "e360af9289cfbfcd3e94dc7ff78b77828fb7c253"
PARENT_TREE = "f29475ce975895a92fcf3bd4aea0a9ba68371813"
RUNNER_FREEZE_SHA256 = "77452867363127a9234ddbf1b27702d38b15477911454a448b680b6a9d6b1366"
EXIT_PLAN_SHA256 = "e6123425e7363051b542da98efcbc4bcda148823715e2f3230509a7b2ab68115"
REQUEST_LIST_SHA256 = "973a926e063fda7ec76883dd4297b88c77a06af22fe3bc0618330e98e28825b4"
MAX_CALLS = 160
FROZEN_FILES = {'requirements-sealed-execution-quote-v01.txt': '03f4da335027e4c83bcf38e523c2e11aeaae49778f5bd6caa47e4703348b31b4',
 'research/data-audits/sealed-historical-execution-input-acquisition-v0.3-independent-verification-34084113393.json': '004c730b006e44232431a3a2be0b6e2468f543ac00d352cab3dcb41461e1fb9e',
 'research/data-audits/sealed-historical-management-runner-v0.1-independent-verification.json': 'fbd8f40126b33408af42851e27644c72216fd051035b591de1c3bc53bfba69c7',
 'research/runtime/sealed-historical-execution-input-plan-v0.1/request-manifest.json': 'ee0701cfbe81bfb546c1fb2d2573cf824b434d3a34ff6f1dffdd8cec5435a2e3',
 'research/runtime/sealed-historical-management-runner-v0.1/exit-input-request-plan.json': '562ed42e20c7021eecf384e3a22aed5f5ce25ae15926dd93072a0313d0e6f461',
 'research/strategy/sealed-historical-management-runner-v0.1.json': 'bf99c8e317d09456d0958133791a7c07b3ed51947a37e8f45c171916b1647faf',
 'src/momentumbot/research/sealed_historical_execution_availability_v01.py': 'ef541e915e75c10641c57e42cd4a62fbb66b472c6b40a02d4c2ad85d6dbedb37',
 'src/momentumbot/research/sealed_historical_execution_quote_v01.py': 'be5d81c039ba0256b2622ea65d2f966f56fa2f9a87b77f2e39485d92c6464383',
 'src/momentumbot/research/sealed_historical_management_runner_v01.py': '7f352ac748e57f9e3a3c59971a07de152e6063b783bcd4eb6b48723f8f904fc5',
 'src/momentumbot/research/sealed_historical_metadata_transport_v01.py': '0d3665043c805d661ecc2bd76e646ccfbb068d7f5e3e0d56419b4155a2fe893d'}


def registered_contract() -> dict:
    return seal({
        "schema_version": 1, "contract_id": CONTRACT_ID,
        "artifact_type": "preregistered_historical_management_exit_metadata_quote",
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "frozen_parent_file_sha256": FROZEN_FILES,
        "runner_freeze_content_sha256": RUNNER_FREEZE_SHA256,
        "exit_input_plan_content_sha256": EXIT_PLAN_SHA256,
        "reuse_evidence_path": REUSE_PATH, "reuse_evidence_file_sha256": REUSE_FILE_SHA256,
        "request_list_content_sha256": REQUEST_LIST_SHA256,
        "request_count": 80, "new_symbol_date_count": 40, "common_symbol_date_count": 41,
        "verified_reuse_request_count": 2, "opportunity_count": 109,
        "available_entry_opportunity_count": 86, "unavailable_entry_opportunity_count": 23,
        "date_count": 30, "sdk_version": SDK_VERSION, "python_version": "3.12.14",
        "requirements_path": LOCK_PATH, "requirements_file_sha256": LOCK_SHA256,
        "provider_methods": list(METHODS), "maximum_metadata_calls": MAX_CALLS,
        "maximum_http_attempts": MAX_CALLS, "maximum_response_bytes": 65536,
        "http_timeout_seconds": 30, "retry_count": 0, "redirects_allowed": False,
        "gateway": "https://hist.databento.com", "dataset": "XNAS.ITCH",
        "consumption_ref": CONSUMPTION_REF, "attempt": 1,
        "durable_consumption_before_provider_required": True,
        "scope": "every_exact_new_request_size_and_cost_in_frozen_order",
        "quote_gate": "all_80_requests_complete_nonzero_size_no_errors_or_blocked_attempts",
        "zero_size_or_unknown_status": "unavailable_without_substitution",
        "reuse_scope": "complete_original_bytes_and_request_interval_containment_only",
        "entry_inputs": "unchanged_original_prices_references_and_unavailable_classifications",
        "spend_authorized_usd": "0", "timeseries_or_broker_access_authorized": False,
        "policy_change_authorized": False, "retrospective_access_authorized": False,
        "account_or_fill_simulation_authorized": False,
        "next_gate": "independently_verified_quote_bound_bounded_management_exit_input_acquisition",
    })


def parent_plan(root: Path) -> dict:
    for name, expected in FROZEN_FILES.items():
        availability._regular(root / name)
        if file_sha(root / name) != expected:
            raise ValueError("frozen exit quote parent differs: " + name)
    verified = runner.verify_bundle(root, root / runner.OUTPUT_PATH)
    if verified["freeze_manifest_content_sha256"] != RUNNER_FREEZE_SHA256:
        raise ValueError("exact runner freeze differs")
    plan = frozen(root / EXIT_PLAN_PATH)
    if plan["content_sha256"] != EXIT_PLAN_SHA256:
        raise ValueError("exact exit input plan differs")
    return plan


def reuse_receipt(root: Path, *, result_zip: Path, consumption_zip: Path, workspace: Path) -> dict:
    """Reopen both exact original ZIPs and fully verify the frozen capture chain.

    No quote slicing, new normalization, fill simulation or status inference is
    performed. The inherited capture verifier checks all original file members;
    the exact XAGE pair is then checked over its entire native-order tape.
    """
    plan = parent_plan(root)
    result, prefix, verified = availability.verify_artifacts(root,
        result_zip=result_zip, consumption_zip=consumption_zip, workspace=workspace)
    original = frozen(root / runner.ENTRY_REQUESTS)["requests"]
    groups = [g for g in plan["groups"] if g["source_kind"] == "existing_entry_pair_reuse_requires_exact_byte_verification"]
    if len(groups) != 1 or groups[0]["group_id"] != "2025-07-15-XAGE-common-management-exit":
        raise ValueError("exact reuse group differs")
    group = groups[0]
    require_exact(group["requests"], plan["reuse_candidate_requests"], "reuse pair")
    sources = []
    for request in group["requests"]:
        index = original.index(request)
        if index not in (78, 79):
            raise ValueError("original XAGE request ordinal differs")
        value = availability._complete_input(request, result / "receipts" / f"request-{index:03d}.json",
            result, availability.ARTIFACTS["result"]["sha256"])
        availability._validate_request_input(value, request["schema"])
        start = group["required_quote_start_ns"] if request["schema"] == "mbp-1" else group["requests"][1]["start_ns"]
        if not request["start_ns"] <= start < group["required_end_ns"] <= request["end_ns"]:
            raise ValueError("original request does not contain required exit interval")
        sources.append({"original_request_ordinal": index, "request": request, "source_evidence": value.evidence,
            "first_record_ts_recv_ns": value.records[0]["ts_recv_ns"],
            "last_record_ts_recv_ns": value.records[-1]["ts_recv_ns"]})
    return seal({"schema_version": 1, "contract_id": CONTRACT_ID,
        "artifact_type": "exact_original_XAGE_pair_reuse_verification",
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "runner_freeze_content_sha256": RUNNER_FREEZE_SHA256,
        "exit_input_plan_content_sha256": EXIT_PLAN_SHA256,
        "archives": availability.ARTIFACTS, "frozen_verifier_confirmation": verified,
        "original_group": group, "sources": sources,
        "complete_original_pair_bytes_verified": True, "required_intervals_contained": True,
        "native_record_order_and_original_ordinals_preserved": True,
        "all_exit_times_executable_inferred": False, "status_or_resting_quote_inferred": False,
        "original_entry_availability_changed": False, "provider_calls": 0,
        "historical_execution_authorized": False, "acquisition_gate_passed": False,
        "account_or_fill_simulation_executed": False, "retrospective_inputs_loaded": False})


def request_manifest(plan: dict) -> dict:
    validate_requests(plan["new_requests"])
    return seal({"schema_version": 1, "contract_id": CONTRACT_ID,
        "artifact_type": "exact_frozen_management_exit_metadata_request_manifest",
        "exit_input_plan_content_sha256": EXIT_PLAN_SHA256,
        "reuse_evidence_file_sha256": REUSE_FILE_SHA256,
        "request_list_content_sha256": REQUEST_LIST_SHA256,
        "requests": plan["new_requests"], "request_count": 80,
        "all_original_opportunities_content_sha256": canonical_fingerprint(plan["opportunities"]),
        "original_entry_inputs_unchanged": True, "unavailable_entries_rescued": False,
        "historical_execution_authorized": False})


def validate_inputs(root: Path) -> list[dict]:
    plan = parent_plan(root)
    require_exact(frozen(root / CONTRACT_PATH), registered_contract(), "exit quote registration")
    availability._regular(root / REUSE_PATH)
    if file_sha(root / REUSE_PATH) != REUSE_FILE_SHA256:
        raise ValueError("exact independently verified XAGE reuse evidence differs")
    frozen(root / REUSE_PATH)
    require_exact(frozen(root / PLAN_PATH / "request-manifest.json"), request_manifest(plan), "exact exit request manifest")
    validate_requests(plan["new_requests"])
    return plan["new_requests"]


def validate_requests(requests: list[dict]) -> None:
    if type(requests) is not list or len(requests) != 80 or canonical_fingerprint(requests) != REQUEST_LIST_SHA256:
        raise ValueError("exact historical management exit metadata requests changed")


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
        "authority": "user_authorized_continued_development_and_operational_steps_2026-09-07",
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
        "schema_version": 1, "artifact_type": "historical_management_exit_input_metadata_quote",
        "contract_id": CONTRACT_ID, "contract_content_sha256": registered_contract()["content_sha256"],
        "request_list_content_sha256": REQUEST_LIST_SHA256, "exit_input_plan_content_sha256": EXIT_PLAN_SHA256, "reuse_evidence_file_sha256": REUSE_FILE_SHA256,
        "provenance": provenance, "sdk_version": SDK_VERSION, "request_count": 80,
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
