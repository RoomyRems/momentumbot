"""Provider-free authority, failure, and final gates for recovery v0.7."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Mapping

from momentumbot.historical_profile_union_v01 import historical_profile_union_v0_1
from momentumbot.research.sealed_historical_source_acquisition import (
    retained_tree_bytes,
    write_json_once,
)
from momentumbot.research.sealed_historical_source_acquisition_v04 import (
    summarize_source_root_v04,
)
from momentumbot.research.sealed_historical_source_acquisition_v07 import (
    build_acquisition_report_v07,
)
from momentumbot.research.sealed_historical_source_checkpoint_v01 import (
    load_json_object,
)
from momentumbot.research.sealed_historical_source_checkpoint_v07 import (
    EXPECTED_ALLOWED_HOSTS,
    build_post_scanner_checkpoint_binding_v07,
    canonical_fingerprint,
    normalize_blocked_attempt_ledger,
    normalize_composite_request_budget,
    output_is_outside_source_root,
)
from momentumbot.research.sealed_historical_source_recovery_v07 import (
    PARENT_REQUEST_BUDGET,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUTHORIZATION = (
    ROOT / "research/strategy/sealed-historical-source-acquisition-v0.7.json"
)
DEFAULT_REQUIREMENTS = ROOT / "requirements-sealed-source-v04.txt"
EXPECTED_REPOSITORY = "RoomyRems/momentumbot"
EXPECTED_AUTHORIZATION_PATH = (
    "research/strategy/sealed-historical-source-acquisition-v0.7.json"
)
EXPECTED_BRANCH = "phase-3-historical-snapshot"
EXPECTED_WORKFLOW_PATH = (
    ".github/workflows/sealed-historical-source-acquisition-v07.yml"
)
EXPECTED_WORKFLOW_REF = (
    "RoomyRems/momentumbot/.github/workflows/"
    "sealed-historical-source-acquisition-v07.yml@refs/heads/main"
)
CONSUMPTION_REF_PREFIX = (
    "refs/tags/sealed-historical-source-acquisition-v07-consumed-"
)
MAX_HTTP_ATTEMPTS = 40_000
MAX_RETAINED_BYTES = 1_500_000_000
EXPECTED_DATES = frozenset(
    {
        "2025-05-30", "2025-06-02", "2025-06-03", "2025-06-04",
        "2025-06-05", "2025-06-06", "2025-06-09", "2025-06-10",
        "2025-06-11", "2025-06-12", "2025-06-13", "2025-06-16",
        "2025-06-17", "2025-06-18", "2025-06-20", "2025-06-23",
        "2025-06-24", "2025-06-25", "2025-06-26", "2025-06-27",
        "2025-07-01", "2025-07-02", "2025-07-07", "2025-07-08",
        "2025-07-10", "2025-07-11", "2025-07-14", "2025-07-15",
        "2025-07-16", "2025-07-17",
    }
)
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^[1-9][0-9]*$")


def _authorization_api() -> tuple[object, object, object, str, str]:
    from momentumbot.research.sealed_historical_source_authorization_v07 import (
        AUTHORIZATION_CONTENT_SHA256,
        AUTHORIZATION_ID,
        load_authorization,
        validate_parent_bundle,
        validate_registration_bundle,
    )

    return (
        load_authorization,
        validate_parent_bundle,
        validate_registration_bundle,
        AUTHORIZATION_ID,
        AUTHORIZATION_CONTENT_SHA256,
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _regular_file(path: Path, *, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file")
    return path


def _strict_provenance(
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
        raise ValueError("v0.7 repository changed")
    for label, value in (
        ("authorization commit", authorization_commit_sha),
        ("authorization tree", authorization_tree_sha),
        ("dispatcher workflow", dispatcher_workflow_sha),
    ):
        if not isinstance(value, str) or _GIT_SHA.fullmatch(value) is None:
            raise ValueError(f"{label} must be a full lowercase Git SHA")
    if dispatcher_workflow_ref != EXPECTED_WORKFLOW_REF:
        raise ValueError("v0.7 dispatcher workflow ref changed")
    if not isinstance(workflow_run_id, str) or _RUN_ID.fullmatch(workflow_run_id) is None:
        raise ValueError("v0.7 workflow run ID must be a positive decimal")
    if isinstance(workflow_run_attempt, bool) or workflow_run_attempt != 1:
        raise ValueError("v0.7 acquisition is attempt 1 only")
    return {
        "repository": repository,
        "authorization_branch": EXPECTED_BRANCH,
        "authorization_path": EXPECTED_AUTHORIZATION_PATH,
        "authorization_commit_sha": authorization_commit_sha,
        "authorization_tree_sha": authorization_tree_sha,
        "dispatcher_workflow_path": EXPECTED_WORKFLOW_PATH,
        "dispatcher_workflow_sha": dispatcher_workflow_sha,
        "dispatcher_workflow_ref": dispatcher_workflow_ref,
        "workflow_run_id": workflow_run_id,
        "workflow_run_attempt": workflow_run_attempt,
    }


def _checkpoint_provenance(provenance: Mapping[str, object]) -> dict[str, object]:
    return {
        key: provenance[key]
        for key in (
            "repository",
            "authorization_commit_sha",
            "authorization_tree_sha",
            "dispatcher_workflow_sha",
            "dispatcher_workflow_ref",
            "workflow_run_id",
            "workflow_run_attempt",
        )
    }


def _load_frozen_authority(path: Path) -> tuple[dict[str, object], str, str]:
    (
        load_authorization,
        validate_parent_bundle,
        validate_registration_bundle,
        authorization_id,
        content_sha,
    ) = _authorization_api()
    authorization = load_authorization(path)  # type: ignore[operator]
    validate_parent_bundle()  # type: ignore[operator]
    validate_registration_bundle()  # type: ignore[operator]
    if (
        not isinstance(authorization, dict)
        or authorization.get("authorization_id") != authorization_id
        or authorization.get("content_sha256") != content_sha
        or _SHA256.fullmatch(content_sha) is None
    ):
        raise ValueError("v0.7 authorization constants and payload disagree")
    return authorization, authorization_id, content_sha


def build_consumption_marker_v07(
    *,
    authorization_id: str,
    authorization_content_sha256: str,
    provenance: Mapping[str, object],
    consumption_ref_name: str,
    consumption_ref_target_sha: str,
) -> dict[str, object]:
    _, _, _, expected_id, expected_sha = _authorization_api()
    if authorization_id != expected_id or authorization_content_sha256 != expected_sha:
        raise ValueError("consumption marker authority is not the frozen v0.7 child")
    canonical = _strict_provenance(
        repository=provenance.get("repository"),  # type: ignore[arg-type]
        authorization_commit_sha=provenance.get("authorization_commit_sha"),  # type: ignore[arg-type]
        authorization_tree_sha=provenance.get("authorization_tree_sha"),  # type: ignore[arg-type]
        dispatcher_workflow_sha=provenance.get("dispatcher_workflow_sha"),  # type: ignore[arg-type]
        dispatcher_workflow_ref=provenance.get("dispatcher_workflow_ref"),  # type: ignore[arg-type]
        workflow_run_id=provenance.get("workflow_run_id"),  # type: ignore[arg-type]
        workflow_run_attempt=provenance.get("workflow_run_attempt"),  # type: ignore[arg-type]
    )
    if dict(provenance) != canonical:
        raise ValueError("v0.7 consumption provenance is not canonical")
    expected_ref = f"{CONSUMPTION_REF_PREFIX}{authorization_content_sha256}"
    if consumption_ref_name != expected_ref:
        raise ValueError("v0.7 consumption ref is not bound to the authorization")
    if consumption_ref_target_sha != provenance.get("authorization_commit_sha"):
        raise ValueError("v0.7 consumption ref target changed")
    marker: dict[str, object] = {
        "schema_version": 1,
        "artifact_type": "sealed_historical_source_recovery_v0_7_consumption",
        "authorization": {
            "authorization_id": authorization_id,
            "authorization_content_sha256": authorization_content_sha256,
        },
        "workflow_provenance": canonical,
        "consumption_ref": {
            "name": consumption_ref_name,
            "target_commit_sha": consumption_ref_target_sha,
            "creation_mode": "atomic_create_only_git_ref",
        },
        "one_shot_attestation": {
            "authorization_consumed": True,
            "automatic_rerun_allowed": False,
            "provider_call_made_before_marker": False,
            "workflow_run_attempt_required": 1,
        },
        "causal_boundary": {
            "account_or_order_endpoint_called": False,
            "databento_called": False,
            "order_submitted": False,
            "ross_labels_or_outcomes_read": False,
            "transcript_record_values_read": False,
        },
    }
    marker["content_sha256"] = canonical_fingerprint(marker)
    return marker


def _empty_blocked_attempts() -> dict[str, object]:
    return {
        "schema_version": 1,
        "total_blocked_attempts": 0,
        "by_category": {
            name: 0
            for name in (
                "hostname",
                "https_transport",
                "redirect",
                "request_budget",
                "socket",
                "subprocess",
            )
        },
        "by_host": {},
    }


def _is_sanitized_host(value: object) -> bool:
    if value in {"<invalid>", "<missing>"}:
        return True
    if not isinstance(value, str) or len(value) > 253:
        return False
    labels = value.split(".")
    return bool(labels) and all(
        label
        and len(label) <= 63
        and label[0].isalnum()
        and label[-1].isalnum()
        and all(
            character.isascii()
            and (character.isalnum() or character == "-")
            for character in label
        )
        for label in labels
    )


def _safe_blocked_attempts(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return _empty_blocked_attempts()
    payload = load_json_object(_regular_file(path, label="blocked-attempt ledger"))
    empty = _empty_blocked_attempts()
    if set(payload) != set(empty):
        raise ValueError("v0.7 blocked-attempt ledger fields changed")
    total = payload.get("total_blocked_attempts")
    categories = payload.get("by_category")
    hosts = payload.get("by_host")
    if (
        payload.get("schema_version") != 1
        or isinstance(total, bool)
        or not isinstance(total, int)
        or total < 0
        or not isinstance(categories, Mapping)
        or set(categories) != set(empty["by_category"])
        or not isinstance(hosts, Mapping)
    ):
        raise ValueError("v0.7 blocked-attempt ledger is invalid")
    clean_categories: dict[str, int] = {}
    for name, count in categories.items():
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("v0.7 blocked-attempt category count is invalid")
        clean_categories[str(name)] = count
    clean_hosts: dict[str, int] = {}
    for host, count in hosts.items():
        if (
            not _is_sanitized_host(host)
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count <= 0
        ):
            raise ValueError("v0.7 blocked-attempt host count is invalid")
        clean_hosts[host] = count
    if sum(clean_categories.values()) != total or sum(clean_hosts.values()) > total:
        raise ValueError("v0.7 blocked-attempt counts are inconsistent")
    return {
        "schema_version": 1,
        "total_blocked_attempts": total,
        "by_category": clean_categories,
        "by_host": dict(sorted(clean_hosts.items())),
    }


def _safe_budget(path: Path | None) -> dict[str, object]:
    payload = (
        PARENT_REQUEST_BUDGET
        if path is None or not path.exists()
        else load_json_object(_regular_file(path, label="request budget"))
    )
    if set(payload) != {"schema_version", "total_attempts", "by_host"}:
        raise ValueError("failure request-budget fields changed")
    total = payload.get("total_attempts")
    hosts = payload.get("by_host")
    if (
        payload.get("schema_version") != 1
        or isinstance(total, bool)
        or not isinstance(total, int)
        or total < int(PARENT_REQUEST_BUDGET["total_attempts"])
        or not isinstance(hosts, Mapping)
    ):
        raise ValueError("failure request-budget ledger is invalid")
    clean_hosts: dict[str, int] = {}
    for raw_host, count in hosts.items():
        if (
            not isinstance(raw_host, str)
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
        ):
            raise ValueError("failure request-budget host accounting is invalid")
        host = raw_host if _is_sanitized_host(raw_host) else "<invalid>"
        clean_hosts[host] = clean_hosts.get(host, 0) + count
    if sum(clean_hosts.values()) != total:
        raise ValueError("failure request-budget counts are inconsistent")
    for host, seed in PARENT_REQUEST_BUDGET["by_host"].items():
        observed = clean_hosts.get(host, 0)
        if host in {"api.massive.com", "data.sec.gov"} and observed != seed:
            raise ValueError("failure request-budget repeated a prohibited parent route")
        if observed < seed:
            raise ValueError("failure request-budget dropped a parent request")
    unauthorized = sorted(set(clean_hosts) - set(EXPECTED_ALLOWED_HOSTS))
    return {
        "schema_version": 1,
        "allowed_hosts": list(EXPECTED_ALLOWED_HOSTS),
        "maximum_total_http_attempts": MAX_HTTP_ATTEMPTS,
        "parent_total_attempts": PARENT_REQUEST_BUDGET["total_attempts"],
        "parent_by_host": dict(PARENT_REQUEST_BUDGET["by_host"]),
        "total_attempts": total,
        "child_attempts": total - int(PARENT_REQUEST_BUDGET["total_attempts"]),
        "by_host": dict(sorted(clean_hosts.items())),
        "unauthorized_hosts_detected": unauthorized,
        "request_ceiling_exhausted": total >= MAX_HTTP_ATTEMPTS,
    }


def _completed_dates(source_root: Path, relative: str) -> list[str]:
    root = source_root / relative
    if not root.is_dir():
        return []
    observed = sorted(
        path.parent.name
        for path in root.glob("*/manifest.json")
        if path.is_file()
    )
    if len(observed) != len(set(observed)) or any(
        value not in EXPECTED_DATES for value in observed
    ):
        raise ValueError("v0.7 failure stage contains an unexpected date")
    return observed


def build_safe_failure_v07(
    *,
    authorization_id: str,
    authorization_content_sha256: str,
    provenance: Mapping[str, object],
    source_root: Path,
    request_budget_path: Path | None,
    blocked_attempt_ledger_path: Path | None,
    checkpoint_path: Path | None,
    recovery_receipt_path: Path | None,
    normalization_diagnostic_path: Path | None,
    environment_freeze_path: Path | None,
    requirements_path: Path | None,
) -> dict[str, object]:
    _, _, _, expected_id, expected_sha = _authorization_api()
    if authorization_id != expected_id or authorization_content_sha256 != expected_sha:
        raise ValueError("safe failure authority is not the frozen v0.7 child")
    canonical = _strict_provenance(
        repository=provenance.get("repository"),  # type: ignore[arg-type]
        authorization_commit_sha=provenance.get("authorization_commit_sha"),  # type: ignore[arg-type]
        authorization_tree_sha=provenance.get("authorization_tree_sha"),  # type: ignore[arg-type]
        dispatcher_workflow_sha=provenance.get("dispatcher_workflow_sha"),  # type: ignore[arg-type]
        dispatcher_workflow_ref=provenance.get("dispatcher_workflow_ref"),  # type: ignore[arg-type]
        workflow_run_id=provenance.get("workflow_run_id"),  # type: ignore[arg-type]
        workflow_run_attempt=provenance.get("workflow_run_attempt"),  # type: ignore[arg-type]
    )
    if dict(provenance) != canonical:
        raise ValueError("v0.7 safe-failure provenance is not canonical")
    files: dict[str, dict[str, object]] = {}
    for label, path in (
        ("source_checkpoint", checkpoint_path),
        ("parent_recovery_receipt", recovery_receipt_path),
        ("normalization_diagnostics", normalization_diagnostic_path),
        ("environment_freeze", environment_freeze_path),
        ("requirements", requirements_path),
    ):
        if path is not None and path.is_file() and not path.is_symlink():
            files[label] = {
                "size_bytes": path.stat().st_size,
                "sha256": _file_sha256(path),
            }
    failure: dict[str, object] = {
        "schema_version": 1,
        "artifact_type": "sealed_historical_source_recovery_v0_7_safe_failure",
        "authorization": {
            "authorization_id": authorization_id,
            "authorization_content_sha256": authorization_content_sha256,
        },
        "workflow_provenance": canonical,
        "request_budget": _safe_budget(request_budget_path),
        "blocked_attempts": _safe_blocked_attempts(blocked_attempt_ledger_path),
        "partial_retained_bytes": (
            retained_tree_bytes(source_root) if source_root.is_dir() else 0
        ),
        "completed_dates_by_stage": {
            "market_discovery_recovered": _completed_dates(
                source_root, "causal-market-discovery-v0.3"
            ),
            "float": _completed_dates(source_root, "causal-sec-float-v0.2"),
            "news": _completed_dates(source_root, "causal-alpaca-news-v0.2"),
            "canonical_scanner_inputs": _completed_dates(
                source_root, "causal-scanner-source-inputs-v0.2"
            ),
            "scanner_snapshot": _completed_dates(
                source_root, "causal-scanner-snapshot-v0.3"
            ),
        },
        "retained_lineage_files": files,
        "causal_attestation": {
            "account_or_order_endpoint_called": False,
            "automatic_rerun_allowed": False,
            "databento_called": False,
            "order_submitted": False,
            "raw_provider_http_responses_persisted": False,
            "ross_labels_or_outcomes_read": False,
            "transcript_record_values_read": False,
        },
    }
    failure["content_sha256"] = canonical_fingerprint(failure)
    return failure


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--authorization", type=Path, default=DEFAULT_AUTHORIZATION)
    modes = result.add_mutually_exclusive_group()
    modes.add_argument("--validate-only", action="store_true")
    modes.add_argument("--write-consumption-marker", action="store_true")
    modes.add_argument("--write-safe-failure", action="store_true")
    result.add_argument("--source-root", type=Path)
    result.add_argument("--request-budget", type=Path)
    result.add_argument("--blocked-attempt-ledger", type=Path)
    result.add_argument("--source-checkpoint", type=Path)
    result.add_argument("--parent-recovery-receipt", type=Path)
    result.add_argument("--normalization-diagnostics", type=Path)
    result.add_argument("--environment-freeze", type=Path)
    result.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    result.add_argument("--authorization-commit-sha", default="")
    result.add_argument("--authorization-tree-sha", default="")
    result.add_argument("--dispatcher-workflow-sha", default="")
    result.add_argument("--dispatcher-workflow-ref", default="")
    result.add_argument("--consumption-ref-name", default="")
    result.add_argument("--consumption-ref-target-sha", default="")
    result.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    result.add_argument("--workflow-run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    result.add_argument(
        "--workflow-run-attempt",
        type=int,
        default=int(os.environ.get("GITHUB_RUN_ATTEMPT", "0")),
    )
    result.add_argument("--output", type=Path)
    return result


def _required(value: object, *, label: str) -> object:
    if value is None or value == "":
        raise SystemExit(f"{label} is required in this mode")
    return value


def _required_path(value: object, *, label: str) -> Path:
    required = _required(value, label=label)
    if not isinstance(required, Path):
        raise SystemExit(f"{label} must be a filesystem path")
    return required


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    authorization, authorization_id, content_sha = _load_frozen_authority(
        args.authorization
    )
    if args.validate_only:
        print(
            json.dumps(
                {
                    "authorization_id": authorization_id,
                    "authorization_content_sha256": content_sha,
                    "maximum_total_http_attempts": MAX_HTTP_ATTEMPTS,
                    "parent_request_seed": PARENT_REQUEST_BUDGET,
                    "provider_calls": 0,
                    "v0_6_rerun": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    provenance = _strict_provenance(
        repository=args.repository,
        authorization_commit_sha=args.authorization_commit_sha,
        authorization_tree_sha=args.authorization_tree_sha,
        dispatcher_workflow_sha=args.dispatcher_workflow_sha,
        dispatcher_workflow_ref=args.dispatcher_workflow_ref,
        workflow_run_id=args.workflow_run_id,
        workflow_run_attempt=args.workflow_run_attempt,
    )
    output = _required_path(args.output, label="output")
    if args.write_consumption_marker:
        write_json_once(
            output,
            build_consumption_marker_v07(
                authorization_id=authorization_id,
                authorization_content_sha256=content_sha,
                provenance=provenance,
                consumption_ref_name=str(
                    _required(args.consumption_ref_name, label="consumption ref name")
                ),
                consumption_ref_target_sha=str(
                    _required(
                        args.consumption_ref_target_sha,
                        label="consumption ref target SHA",
                    )
                ),
            ),
        )
        return 0
    source_root = _required_path(args.source_root, label="source root")
    if args.write_safe_failure:
        write_json_once(
            output,
            build_safe_failure_v07(
                authorization_id=authorization_id,
                authorization_content_sha256=content_sha,
                provenance=provenance,
                source_root=source_root,
                request_budget_path=args.request_budget,
                blocked_attempt_ledger_path=args.blocked_attempt_ledger,
                checkpoint_path=args.source_checkpoint,
                recovery_receipt_path=args.parent_recovery_receipt,
                normalization_diagnostic_path=args.normalization_diagnostics,
                environment_freeze_path=args.environment_freeze,
                requirements_path=args.requirements,
            ),
        )
        return 0
    budget_path = _required_path(args.request_budget, label="request budget")
    blocked_path = _required_path(
        args.blocked_attempt_ledger, label="blocked-attempt ledger"
    )
    checkpoint_path = _required_path(
        args.source_checkpoint, label="source checkpoint"
    )
    recovery_path = _required_path(
        args.parent_recovery_receipt, label="parent recovery receipt"
    )
    diagnostic_path = _required_path(
        args.normalization_diagnostics, label="normalization diagnostics"
    )
    environment_path = _required_path(
        args.environment_freeze, label="environment freeze"
    )
    for label, path in (
        ("request budget", budget_path),
        ("blocked-attempt ledger", blocked_path),
        ("source checkpoint", checkpoint_path),
        ("parent recovery receipt", recovery_path),
        ("normalization diagnostics", diagnostic_path),
        ("environment freeze", environment_path),
        ("requirements", args.requirements),
    ):
        _regular_file(path, label=label)
    if not output_is_outside_source_root(output, source_root):
        raise ValueError("v0.7 report must stay outside the source root")
    checkpoint = load_json_object(checkpoint_path)
    binding = build_post_scanner_checkpoint_binding_v07(
        checkpoint,
        checkpoint_file_sha256=_file_sha256(checkpoint_path),
        checkpoint_output_path=checkpoint_path,
        source_root=source_root,
        authorization=authorization,
        recovery_receipt_path=recovery_path,
        normalization_diagnostic_path=diagnostic_path,
        expected_provenance=_checkpoint_provenance(provenance),
        environment_freeze_path=environment_path,
        requirements_path=args.requirements,
    )
    blocked = normalize_blocked_attempt_ledger(
        load_json_object(blocked_path),
        require_zero=True,
    )
    if binding.get("blocked_attempts") != blocked:
        raise ValueError("external blocked-attempt ledger differs from checkpoint")
    summary = summarize_source_root_v04(
        source_root,
        profile=historical_profile_union_v0_1(),
    )
    report = build_acquisition_report_v07(
        authorization_id=authorization_id,
        authorization_content_sha256=content_sha,
        source_checkpoint_binding=binding,
        source_summary=summary,
        request_budget=load_json_object(budget_path),
        retained_bytes=retained_tree_bytes(source_root),
        repository=args.repository,
        authorization_commit_sha=args.authorization_commit_sha,
        authorization_tree_sha=args.authorization_tree_sha,
        dispatcher_workflow_sha=args.dispatcher_workflow_sha,
        dispatcher_workflow_ref=args.dispatcher_workflow_ref,
        workflow_run_id=args.workflow_run_id,
        workflow_run_attempt=args.workflow_run_attempt,
    )
    write_json_once(output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
