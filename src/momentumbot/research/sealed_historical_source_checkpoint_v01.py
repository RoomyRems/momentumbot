"""Deterministic, provider-free checkpoint for sealed v0.4 source inputs.

The checkpoint is intentionally created before scanner snapshots exist.  It
binds the complete label-blind provider/source-input tree so that a later
provider-free validation failure cannot make the acquired inputs disappear.
This module imports no provider clients and performs no network access.
"""

from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Iterable, Mapping, Sequence

from momentumbot.research.sealed_historical_availability import SELECTED_DATES


SCHEMA_VERSION = 1
ARTIFACT_ID = "sealed-historical-source-checkpoint-v0.1"
ARTIFACT_TYPE = "sealed_historical_label_blind_source_checkpoint"
POST_SCANNER_BINDING_TYPE = (
    "sealed_historical_source_checkpoint_post_scanner_binding_v0.1"
)
AUTHORIZATION_ID = "sealed-historical-source-acquisition-v0.4"
EXPECTED_REPOSITORY = "RoomyRems/momentumbot"
EXPECTED_DATES = tuple(SELECTED_DATES)
EXPECTED_ALLOWED_HOSTS = (
    "api.massive.com",
    "data.alpaca.markets",
    "data.sec.gov",
)
BLOCKED_ATTEMPT_CATEGORIES = (
    "hostname",
    "https_transport",
    "redirect",
    "request_budget",
    "socket",
    "subprocess",
)
MASSIVE_TICKER_TYPES_FILE = "massive-ticker-types.json"
MASSIVE_TICKER_TYPES_SOURCE = "massive_v3_reference_tickers_types"
MASSIVE_TICKER_TYPES_CONTRACT = (
    "https://massive.com/docs/rest/stocks/tickers/ticker-types"
)

# The four auxiliary roots are products of the census/identity stages.  They
# are bound by the full inventory but are not independently acquired provider
# stages.  Keeping them explicit makes an unexpected top-level stage fatal.
EXPECTED_AUXILIARY_CENSUS_ROOTS = (
    "identity-continuity-v0.1",
    "instrument-metadata-audit",
    "market-data-coverage",
    "provisional-universe-v0.1",
)
EXPECTED_SCANNER_SNAPSHOT_ROOT = "causal-scanner-snapshot-v0.3"
ENVIRONMENT_FREEZE_LABEL = "environment/pip-freeze.txt"
REQUIREMENTS_LABEL = "environment/requirements-sealed-source-v04.txt"
EXPECTED_STAGE_ROOTS = (
    ("census", ".", "census-root"),
    (
        "identity",
        "identity-resolved-universe-v0.1",
        "identity-resolved-universe-v0.1",
    ),
    (
        "market",
        "causal-market-discovery-v0.3",
        "causal-market-discovery-v0.3",
    ),
    ("float", "causal-sec-float-v0.2", "causal-sec-float-v0.2"),
    ("news", "causal-alpaca-news-v0.2", "causal-alpaca-news-v0.2"),
    (
        "scanner_source_inputs",
        "causal-scanner-source-inputs-v0.2",
        "causal-scanner-source-inputs-v0.2",
    ),
)

CAUSAL_BOUNDARY = {
    "account_or_order_endpoints_called": False,
    "labels_or_transcripts_read": False,
    "orders_submitted": False,
    "provider_calls_performed_by_checkpoint_builder": False,
    "retrospective_outcomes_read": False,
    "ross_actions_fills_or_skips_read": False,
    "scanner_snapshot_present": False,
}

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_RUN_ID = re.compile(r"^[1-9][0-9]*$")
EXPECTED_WORKFLOW_REF = (
    "RoomyRems/momentumbot/.github/workflows/"
    "sealed-historical-source-acquisition-v04.yml@refs/heads/main"
)
_FORBIDDEN_LABEL_PATH_TOKENS = (
    "label",
    "order",
    "outcome",
    "retrospective",
    "ross",
    "transcript",
)

_CHECKPOINT_KEYS = frozenset(
    {
        "schema_version",
        "artifact_id",
        "artifact_type",
        "dates",
        "authorization",
        "provenance",
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


def canonical_fingerprint(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def load_json_object(path: str | Path) -> dict[str, object]:
    payload = json.loads(
        Path(path).read_text(encoding="utf-8"),
        parse_constant=_reject_json_constant,
        object_pairs_hook=_reject_duplicate_json_keys,
    )
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required at {path}")
    return payload


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolved_regular_external_file(
    value: str | Path,
    *,
    label: str,
    expected_basename: str,
    source_root: str | Path | None,
    checkpoint_output_path: str | Path | None,
) -> tuple[Path, os.stat_result]:
    path = Path(value)
    if ".." in path.parts:
        raise ValueError(f"{label} path may not contain parent traversal")
    absolute = Path(os.path.abspath(path))
    for component in (absolute, *absolute.parents):
        if component.is_symlink():
            raise ValueError(f"{label} path may not contain a symlink")
    if path.name != expected_basename:
        raise ValueError(f"{label} path must use the fixed portable filename")
    try:
        metadata = absolute.lstat()
    except FileNotFoundError as exc:
        raise ValueError(f"{label} must be an existing regular file") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{label} must be a regular file")
    resolved = absolute.resolve(strict=True)
    if source_root is not None:
        root = Path(source_root).resolve(strict=True)
        if resolved == root or root in resolved.parents:
            raise ValueError(f"{label} must be outside the source root")
    if checkpoint_output_path is not None:
        output = Path(checkpoint_output_path).resolve(strict=False)
        if resolved == output:
            raise ValueError(f"{label} may not alias the checkpoint output")
        if output.exists():
            output_metadata = output.stat()
            if (
                output_metadata.st_dev == metadata.st_dev
                and output_metadata.st_ino == metadata.st_ino
            ):
                raise ValueError(f"{label} may not alias the checkpoint output")
    return resolved, metadata


def _environment_record(
    *,
    environment_freeze_path: str | Path,
    requirements_path: str | Path,
    source_root: str | Path | None,
    checkpoint_output_path: str | Path | None,
) -> dict[str, object]:
    freeze, freeze_metadata = _resolved_regular_external_file(
        environment_freeze_path,
        label="environment freeze",
        expected_basename=PurePosixPath(ENVIRONMENT_FREEZE_LABEL).name,
        source_root=source_root,
        checkpoint_output_path=checkpoint_output_path,
    )
    requirements, requirements_metadata = _resolved_regular_external_file(
        requirements_path,
        label="requirements lock",
        expected_basename=PurePosixPath(REQUIREMENTS_LABEL).name,
        source_root=source_root,
        checkpoint_output_path=checkpoint_output_path,
    )
    if freeze == requirements or (
        freeze_metadata.st_dev == requirements_metadata.st_dev
        and freeze_metadata.st_ino == requirements_metadata.st_ino
    ):
        raise ValueError("environment freeze and requirements lock must be distinct files")
    return {
        "freeze_path": ENVIRONMENT_FREEZE_LABEL,
        "freeze_size_bytes": freeze_metadata.st_size,
        "freeze_sha256": _file_sha256(freeze),
        "requirements_path": REQUIREMENTS_LABEL,
        "requirements_size_bytes": requirements_metadata.st_size,
        "requirements_sha256": _file_sha256(requirements),
    }


def _validate_environment_record(
    value: object,
    *,
    environment_freeze_path: str | Path,
    requirements_path: str | Path,
    source_root: str | Path | None,
    checkpoint_output_path: str | Path | None,
) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != {
        "freeze_path",
        "freeze_size_bytes",
        "freeze_sha256",
        "requirements_path",
        "requirements_size_bytes",
        "requirements_sha256",
    }:
        raise ValueError("checkpoint environment inventory is invalid")
    if value.get("freeze_path") != ENVIRONMENT_FREEZE_LABEL or value.get(
        "requirements_path"
    ) != REQUIREMENTS_LABEL:
        raise ValueError("checkpoint environment portable paths changed")
    _safe_relative_path(value.get("freeze_path"), label="environment freeze label")
    _safe_relative_path(value.get("requirements_path"), label="requirements label")
    for key in ("freeze_sha256", "requirements_sha256"):
        if not _is_sha256(value.get(key)):
            raise ValueError("checkpoint environment hash is invalid")
    _strict_int(value.get("freeze_size_bytes"), label="environment freeze size")
    _strict_int(value.get("requirements_size_bytes"), label="requirements size")
    observed = _environment_record(
        environment_freeze_path=environment_freeze_path,
        requirements_path=requirements_path,
        source_root=source_root,
        checkpoint_output_path=checkpoint_output_path,
    )
    if dict(value) != observed:
        raise ValueError("checkpoint reproducibility environment changed")
    return dict(value)


def _strict_int(value: object, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _empty_blocked_attempts() -> dict[str, object]:
    return {
        "schema_version": 1,
        "total_blocked_attempts": 0,
        "by_category": {category: 0 for category in BLOCKED_ATTEMPT_CATEGORIES},
        "by_host": {},
    }


def _validate_blocked_attempts(
    value: object,
    *,
    require_zero: bool,
) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version",
        "total_blocked_attempts",
        "by_category",
        "by_host",
    }:
        raise ValueError("checkpoint blocked-attempt ledger fields changed")
    if _strict_int(
        value.get("schema_version"),
        label="blocked-attempt schema version",
        minimum=1,
    ) != 1:
        raise ValueError("checkpoint blocked-attempt schema changed")
    total = _strict_int(
        value.get("total_blocked_attempts"),
        label="blocked-attempt total",
    )
    categories = value.get("by_category")
    hosts = value.get("by_host")
    if (
        not isinstance(categories, Mapping)
        or tuple(sorted(categories)) != tuple(sorted(BLOCKED_ATTEMPT_CATEGORIES))
        or not isinstance(hosts, Mapping)
    ):
        raise ValueError("checkpoint blocked-attempt ledger is invalid")
    clean_categories: dict[str, int] = {}
    for category in BLOCKED_ATTEMPT_CATEGORIES:
        clean_categories[category] = _strict_int(
            categories[category],
            label=f"blocked-attempt category {category}",
        )
    clean_hosts: dict[str, int] = {}
    for host, count in hosts.items():
        if not isinstance(host, str) or not host:
            raise ValueError("checkpoint blocked-attempt host is invalid")
        clean_hosts[host] = _strict_int(
            count,
            label=f"blocked-attempt host {host}",
            minimum=1,
        )
    if sum(clean_categories.values()) != total or sum(clean_hosts.values()) > total:
        raise ValueError("checkpoint blocked-attempt counts are inconsistent")
    if require_zero and (total != 0 or clean_hosts):
        raise ValueError("successful checkpoint contains a blocked provider attempt")
    return {
        "schema_version": 1,
        "total_blocked_attempts": total,
        "by_category": clean_categories,
        "by_host": dict(sorted(clean_hosts.items())),
    }


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _exact_dates(value: object, *, label: str) -> list[str]:
    expected = list(EXPECTED_DATES)
    if not isinstance(value, list) or value != expected:
        raise ValueError(f"{label} must contain exactly the frozen 30 dates")
    for trading_date in value:
        date.fromisoformat(trading_date)
    return expected


def _safe_relative_path(value: object, *, label: str, allow_dot: bool = False) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a relative POSIX path")
    if allow_dot and value == ".":
        return value
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or value != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"{label} escapes or is not canonical")
    return value


def validate_authorization_envelope(
    authorization: Mapping[str, object],
) -> dict[str, object]:
    """Validate a self-hashed v0.4 envelope without freezing its full body."""

    payload = dict(authorization)
    claimed = payload.get("content_sha256")
    if not _is_sha256(claimed):
        raise ValueError("authorization content hash is invalid")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if claimed != canonical_fingerprint(unsigned):
        raise ValueError("authorization content hash mismatch")
    if _strict_int(
        payload.get("schema_version"),
        label="authorization schema version",
        minimum=1,
    ) != SCHEMA_VERSION:
        raise ValueError("authorization schema is not v0.4-compatible")
    if payload.get("authorization_id") != AUTHORIZATION_ID:
        raise ValueError("authorization ID is not the v0.4 child")

    parent = payload.get("frozen_parent")
    if not isinstance(parent, Mapping):
        raise ValueError("authorization frozen parent is missing")
    _exact_dates(parent.get("selected_dates"), label="authorization selected dates")

    authority = payload.get("authority_boundary")
    if not isinstance(authority, Mapping) or authority.get(
        "historical_source_acquisition_authorized"
    ) is not True:
        raise ValueError("authorization does not permit historical source acquisition")
    for key in ("live_order_authorized", "paper_order_authorized"):
        if authority.get(key) is not False:
            raise ValueError(f"authorization must prohibit {key}")

    causal = payload.get("causal_boundary")
    if not isinstance(causal, Mapping):
        raise ValueError("authorization causal boundary is missing")
    for key in (
        "ross_actions_fills_skips_or_outcomes_may_be_read",
        "transcript_record_values_may_be_read",
    ):
        if causal.get(key) is not False:
            raise ValueError(f"authorization must prohibit {key}")

    one_shot = payload.get("one_shot_contract")
    if not isinstance(one_shot, Mapping):
        raise ValueError("authorization one-shot contract is missing")
    if one_shot.get("automatic_rerun_allowed") is not False or _strict_int(
        one_shot.get("workflow_run_attempt_required"),
        label="authorization required workflow attempt",
        minimum=1,
    ) != 1:
        raise ValueError("authorization one-shot boundary changed")

    request_budget = payload.get("request_budget")
    if not isinstance(request_budget, Mapping):
        raise ValueError("authorization request budget is missing")
    allowed_hosts = request_budget.get("allowed_hosts")
    if allowed_hosts != list(EXPECTED_ALLOWED_HOSTS):
        raise ValueError("authorization provider host allowlist changed")
    _strict_int(
        request_budget.get("maximum_total_http_attempts_including_retries"),
        label="authorization request ceiling",
        minimum=1,
    )

    retention = payload.get("retention_budget")
    if not isinstance(retention, Mapping):
        raise ValueError("authorization retention budget is missing")
    _strict_int(
        retention.get("maximum_retained_bytes"),
        label="authorization retained-byte ceiling",
        minimum=1,
    )
    if retention.get("raw_provider_http_responses_persisted") is not False:
        raise ValueError("authorization must prohibit raw HTTP response retention")
    return payload


def load_authorization_envelope(path: str | Path) -> dict[str, object]:
    return validate_authorization_envelope(load_json_object(path))


def _validate_source_root_layout(
    source_root: Path,
    *,
    allow_scanner_snapshot_addition: bool = False,
) -> None:
    if source_root.is_symlink():
        raise ValueError("source root may not be a symlink")
    if not source_root.is_dir():
        raise ValueError("source root must be a directory")
    observed_files: set[str] = set()
    observed_directories: set[str] = set()
    for child in source_root.iterdir():
        if child.is_symlink():
            raise ValueError(f"source tree contains a symlink: {child.name}")
        mode = child.lstat().st_mode
        if stat.S_ISREG(mode):
            observed_files.add(child.name)
        elif stat.S_ISDIR(mode):
            observed_directories.add(child.name)
        else:
            raise ValueError(f"source tree contains a special file: {child.name}")

    expected_stage_directories = {
        relative for _, relative, _ in EXPECTED_STAGE_ROOTS if relative != "."
    }
    expected_directories = (
        set(EXPECTED_DATES)
        | expected_stage_directories
        | set(EXPECTED_AUXILIARY_CENSUS_ROOTS)
    )
    if allow_scanner_snapshot_addition:
        expected_directories.add(EXPECTED_SCANNER_SNAPSHOT_ROOT)
    if observed_files != {"manifest.json", MASSIVE_TICKER_TYPES_FILE}:
        raise ValueError("census root files are missing or contain extras")
    if observed_directories != expected_directories:
        missing = sorted(expected_directories - observed_directories)
        extra = sorted(observed_directories - expected_directories)
        raise ValueError(
            f"source stage roots are missing or extra; missing={missing}, extra={extra}"
        )


def inventory_source_tree(
    source_root: str | Path,
    *,
    allow_scanner_snapshot_addition: bool = False,
) -> dict[str, object]:
    """Inventory every source file and directory without following symlinks."""

    root = Path(source_root)
    _validate_source_root_layout(
        root,
        allow_scanner_snapshot_addition=allow_scanner_snapshot_addition,
    )
    directories: list[str] = []
    files: list[dict[str, object]] = []
    seen: set[str] = set()

    def visit(directory: Path, relative_parent: PurePosixPath | None) -> None:
        with os.scandir(directory) as entries:
            ordered = sorted(entries, key=lambda entry: entry.name)
        for entry in ordered:
            relative = (
                PurePosixPath(entry.name)
                if relative_parent is None
                else relative_parent / entry.name
            )
            relative_text = relative.as_posix()
            _safe_relative_path(relative_text, label="source inventory path")
            lowered_parts = tuple(part.lower() for part in relative.parts)
            if any(
                token in part
                for part in lowered_parts
                for token in _FORBIDDEN_LABEL_PATH_TOKENS
            ):
                raise ValueError(
                    f"source tree contains a forbidden retrospective path: {relative_text}"
                )
            if relative_text in seen:
                raise ValueError(f"duplicate source inventory path: {relative_text}")
            seen.add(relative_text)
            path = Path(entry.path)
            if entry.is_symlink():
                raise ValueError(f"source tree contains a symlink: {relative_text}")
            metadata = entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(metadata.st_mode):
                directories.append(relative_text)
                visit(path, relative)
            elif stat.S_ISREG(metadata.st_mode):
                files.append(
                    {
                        "path": relative_text,
                        "size_bytes": metadata.st_size,
                        "sha256": _file_sha256(path),
                    }
                )
            else:
                raise ValueError(f"source tree contains a special file: {relative_text}")

    visit(root, None)
    directories.sort()
    files.sort(key=lambda row: str(row["path"]))
    body: dict[str, object] = {
        "directory_count": len(directories),
        "directories": directories,
        "file_count": len(files),
        "files": files,
    }
    body["tree_content_sha256"] = canonical_fingerprint(body)
    return body


def _inventory_file_map(inventory: Mapping[str, object]) -> dict[str, dict[str, object]]:
    exact_keys = {
        "directory_count",
        "directories",
        "file_count",
        "files",
        "tree_content_sha256",
    }
    if set(inventory) != exact_keys:
        raise ValueError("checkpoint inventory keys changed")
    directories = inventory.get("directories")
    files = inventory.get("files")
    if not isinstance(directories, list) or not isinstance(files, list):
        raise ValueError("checkpoint inventory must contain directory and file lists")
    _strict_int(
        inventory.get("directory_count"),
        label="inventory directory count",
    )
    _strict_int(inventory.get("file_count"), label="inventory file count")
    if inventory["directory_count"] != len(directories) or inventory["file_count"] != len(
        files
    ):
        raise ValueError("checkpoint inventory counts do not match")

    clean_directories: list[str] = []
    seen_paths: set[str] = set()
    for value in directories:
        relative = _safe_relative_path(value, label="inventory directory")
        if relative in seen_paths:
            raise ValueError("checkpoint inventory contains duplicate paths")
        seen_paths.add(relative)
        clean_directories.append(relative)
    if clean_directories != sorted(clean_directories):
        raise ValueError("checkpoint directories are not in canonical order")

    clean_files: list[dict[str, object]] = []
    file_map: dict[str, dict[str, object]] = {}
    for row in files:
        if not isinstance(row, Mapping) or set(row) != {"path", "size_bytes", "sha256"}:
            raise ValueError("checkpoint file inventory row is invalid")
        relative = _safe_relative_path(row.get("path"), label="inventory file")
        if relative in seen_paths:
            raise ValueError("checkpoint inventory contains duplicate paths")
        seen_paths.add(relative)
        size = _strict_int(row.get("size_bytes"), label=f"file size {relative}")
        digest = row.get("sha256")
        if not _is_sha256(digest):
            raise ValueError(f"file digest is invalid: {relative}")
        normalized = {"path": relative, "size_bytes": size, "sha256": digest}
        clean_files.append(normalized)
        file_map[relative] = normalized
    if [row["path"] for row in clean_files] != sorted(file_map):
        raise ValueError("checkpoint files are not in canonical order")

    unsigned = {
        "directory_count": inventory["directory_count"],
        "directories": directories,
        "file_count": inventory["file_count"],
        "files": files,
    }
    if inventory.get("tree_content_sha256") != canonical_fingerprint(unsigned):
        raise ValueError("checkpoint tree content hash mismatch")
    return file_map


def _stage_root_records(
    source_root: Path,
    inventory: Mapping[str, object],
) -> list[dict[str, object]]:
    file_map = _inventory_file_map(inventory)
    records: list[dict[str, object]] = []
    for name, relative_root, artifact_id in EXPECTED_STAGE_ROOTS:
        manifest_relative = (
            "manifest.json"
            if relative_root == "."
            else f"{relative_root}/manifest.json"
        )
        inventoried = file_map.get(manifest_relative)
        if inventoried is None:
            raise ValueError(f"{name} stage manifest is missing from inventory")
        manifest = load_json_object(source_root / manifest_relative)
        _exact_dates(manifest.get("dates"), label=f"{name} stage dates")
        declared = manifest.get("artifact_id")
        if relative_root == ".":
            if declared is not None:
                raise ValueError("census root unexpectedly declares an artifact ID")
            _validate_census_ticker_types(source_root, manifest)
        elif declared != artifact_id:
            raise ValueError(f"{name} stage artifact ID changed")
        content_hash = manifest.get("content_sha256")
        if relative_root == "." and content_hash is not None:
            raise ValueError("census stage unexpectedly declares a content hash")
        if relative_root != "." and not _is_sha256(content_hash):
            raise ValueError(f"{name} stage content hash is invalid")
        records.append(
            {
                "name": name,
                "relative_path": relative_root,
                "artifact_id": artifact_id,
                "manifest_relative_path": manifest_relative,
                "manifest_file_sha256": inventoried["sha256"],
                "manifest_content_sha256": content_hash,
                "dates": list(EXPECTED_DATES),
            }
        )
    return records


def _request_budget_snapshot(
    request_budget: Mapping[str, object],
    authorization: Mapping[str, object],
) -> dict[str, object]:
    if set(request_budget) != {"schema_version", "total_attempts", "by_host"}:
        raise ValueError("request-budget state keys changed")
    if _strict_int(
        request_budget.get("schema_version"),
        label="request-budget schema version",
        minimum=1,
    ) != 1:
        raise ValueError("request-budget schema changed")
    total = _strict_int(request_budget.get("total_attempts"), label="total attempts")
    by_host = request_budget.get("by_host")
    if not isinstance(by_host, Mapping):
        raise ValueError("request-budget by-host state is invalid")
    observed: dict[str, int] = {}
    for host, value in by_host.items():
        if not isinstance(host, str) or host not in EXPECTED_ALLOWED_HOSTS:
            raise ValueError("request-budget contains an unauthorized host")
        observed[host] = _strict_int(value, label=f"request count for {host}")
    if sum(observed.values()) != total:
        raise ValueError("request-budget host counts do not equal total attempts")

    configured = authorization["request_budget"]
    assert isinstance(configured, Mapping)
    maximum = _strict_int(
        configured.get("maximum_total_http_attempts_including_retries"),
        label="request ceiling",
        minimum=1,
    )
    if total > maximum:
        raise ValueError("request-budget snapshot exceeds authorization ceiling")
    return {
        "schema_version": 1,
        "allowed_hosts": list(EXPECTED_ALLOWED_HOSTS),
        "maximum_total_http_attempts": maximum,
        "total_attempts": total,
        "by_host": dict(sorted(observed.items())),
    }


def normalize_request_budget_snapshot(
    request_budget: Mapping[str, object],
    authorization: Mapping[str, object],
) -> dict[str, object]:
    """Return the canonical checkpoint view of an external request ledger."""

    authorization_payload = validate_authorization_envelope(authorization)
    return _request_budget_snapshot(request_budget, authorization_payload)


def normalize_blocked_attempt_ledger(
    blocked_attempt_ledger: Mapping[str, object],
    *,
    require_zero: bool = True,
) -> dict[str, object]:
    """Return the canonical checkpoint view of an external blocked ledger."""

    return _validate_blocked_attempts(
        blocked_attempt_ledger,
        require_zero=require_zero,
    )


def _validate_census_ticker_types(
    source_root: Path,
    root_manifest: Mapping[str, object],
) -> None:
    ticker_types = load_json_object(source_root / MASSIVE_TICKER_TYPES_FILE)
    if set(ticker_types) != {
        "schema_version",
        "source",
        "official_contract",
        "retrieved_at_utc",
        "row_count",
        "sha256",
        "rows",
    }:
        raise ValueError("Massive ticker-types payload shape changed")
    if _strict_int(
        ticker_types.get("schema_version"),
        label="Massive ticker-types schema version",
        minimum=1,
    ) != 1:
        raise ValueError("Massive ticker-types schema changed")
    if ticker_types.get("source") != MASSIVE_TICKER_TYPES_SOURCE or ticker_types.get(
        "official_contract"
    ) != MASSIVE_TICKER_TYPES_CONTRACT:
        raise ValueError("Massive ticker-types source contract changed")
    retrieved_at = ticker_types.get("retrieved_at_utc")
    if not isinstance(retrieved_at, str) or not retrieved_at:
        raise ValueError("Massive ticker-types retrieval time is invalid")
    try:
        parsed_retrieved_at = datetime.fromisoformat(retrieved_at)
    except ValueError as exc:
        raise ValueError("Massive ticker-types retrieval time is invalid") from exc
    if parsed_retrieved_at.tzinfo is None or parsed_retrieved_at.utcoffset() is None:
        raise ValueError("Massive ticker-types retrieval time must be timezone-aware")

    rows = ticker_types.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Massive ticker-types rows must be a nonempty list")
    normalized_rows: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {
            "asset_class",
            "code",
            "description",
            "locale",
        }:
            raise ValueError("Massive ticker-types row shape changed")
        if any(not isinstance(row.get(key), str) for key in row):
            raise ValueError("Massive ticker-types rows must contain strings")
        normalized = {
            "asset_class": str(row["asset_class"]).strip().lower(),
            "code": str(row["code"]).strip().upper(),
            "description": str(row["description"]).strip(),
            "locale": str(row["locale"]).strip().lower(),
        }
        if not normalized["code"] or dict(row) != normalized:
            raise ValueError("Massive ticker-types rows are not canonical")
        normalized_rows.append(normalized)
    canonical_rows = sorted(normalized_rows, key=lambda row: row["code"])
    codes = [row["code"] for row in canonical_rows]
    if normalized_rows != canonical_rows or len(codes) != len(set(codes)):
        raise ValueError("Massive ticker-types rows are not uniquely code-sorted")
    row_count = _strict_int(
        ticker_types.get("row_count"),
        label="Massive ticker-types row count",
        minimum=1,
    )
    if row_count != len(canonical_rows):
        raise ValueError("Massive ticker-types row count mismatch")
    rows_sha256 = ticker_types.get("sha256")
    if not _is_sha256(rows_sha256) or rows_sha256 != canonical_fingerprint(
        canonical_rows
    ):
        raise ValueError("Massive ticker-types canonical rows hash mismatch")

    if _strict_int(
        root_manifest.get("schema_version"),
        label="census root schema version",
        minimum=1,
    ) != 1:
        raise ValueError("census root schema changed")
    if root_manifest.get("massive_ticker_type_count") != row_count or root_manifest.get(
        "massive_ticker_types_sha256"
    ) != rows_sha256:
        raise ValueError("census root ticker-types count/hash lineage mismatch")
    date_manifests = root_manifest.get("date_manifests")
    if not isinstance(date_manifests, list) or len(date_manifests) != len(
        EXPECTED_DATES
    ):
        raise ValueError("census root date-manifest lineage is incomplete")
    for trading_date, date_manifest in zip(
        EXPECTED_DATES,
        date_manifests,
        strict=True,
    ):
        if not isinstance(date_manifest, Mapping) or date_manifest.get(
            "requested_asof_date"
        ) != trading_date:
            raise ValueError("census root date-manifest order changed")
        if date_manifest.get("ticker_type_dictionary") != {
            "official_contract": MASSIVE_TICKER_TYPES_CONTRACT,
            "row_count": row_count,
            "sha256": rows_sha256,
        }:
            raise ValueError("census date ticker-types lineage mismatch")


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
        raise ValueError("checkpoint repository changed")
    for label, value in (
        ("authorization commit", authorization_commit_sha),
        ("authorization tree", authorization_tree_sha),
        ("dispatcher workflow", dispatcher_workflow_sha),
    ):
        if not isinstance(value, str) or _GIT_SHA.fullmatch(value) is None:
            raise ValueError(f"{label} must be a lowercase Git SHA")
    if dispatcher_workflow_ref != EXPECTED_WORKFLOW_REF:
        raise ValueError("dispatcher workflow ref is not the v0.4 main dispatcher")
    if not isinstance(workflow_run_id, str) or _RUN_ID.fullmatch(workflow_run_id) is None:
        raise ValueError("workflow run ID must be a positive decimal string")
    if _strict_int(
        workflow_run_attempt,
        label="workflow run attempt",
        minimum=1,
    ) != 1:
        raise ValueError("checkpoint requires workflow attempt 1")
    return {
        "repository": repository,
        "authorization_commit_sha": authorization_commit_sha,
        "authorization_tree_sha": authorization_tree_sha,
        "dispatcher_workflow_sha": dispatcher_workflow_sha,
        "dispatcher_workflow_ref": dispatcher_workflow_ref,
        "workflow_run_id": workflow_run_id,
        "workflow_run_attempt": workflow_run_attempt,
    }


def build_source_checkpoint(
    *,
    source_root: str | Path,
    authorization: Mapping[str, object],
    request_budget: Mapping[str, object],
    blocked_attempt_ledger: Mapping[str, object] | None = None,
    environment_freeze_path: str | Path,
    requirements_path: str | Path,
    checkpoint_output_path: str | Path | None = None,
    repository: str,
    authorization_commit_sha: str,
    authorization_tree_sha: str,
    dispatcher_workflow_sha: str,
    dispatcher_workflow_ref: str,
    workflow_run_id: str,
    workflow_run_attempt: int,
) -> dict[str, object]:
    authorization_payload = validate_authorization_envelope(authorization)
    root = Path(source_root)
    inventory = inventory_source_tree(root)
    file_map = _inventory_file_map(inventory)
    retained_bytes = sum(int(row["size_bytes"]) for row in file_map.values())
    retention = authorization_payload["retention_budget"]
    assert isinstance(retention, Mapping)
    ceiling = _strict_int(
        retention.get("maximum_retained_bytes"),
        label="retained-byte ceiling",
        minimum=1,
    )
    if retained_bytes > ceiling:
        raise ValueError("source checkpoint exceeds retained-byte ceiling")

    checkpoint: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": ARTIFACT_ID,
        "artifact_type": ARTIFACT_TYPE,
        "dates": list(EXPECTED_DATES),
        "authorization": {
            "authorization_id": authorization_payload["authorization_id"],
            "authorization_content_sha256": authorization_payload["content_sha256"],
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
        "request_budget": _request_budget_snapshot(request_budget, authorization_payload),
        "blocked_attempts": _validate_blocked_attempts(
            blocked_attempt_ledger or _empty_blocked_attempts(),
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
        "total_retained_bytes": retained_bytes,
        "causal_boundary": dict(CAUSAL_BOUNDARY),
    }
    checkpoint["content_sha256"] = canonical_fingerprint(checkpoint)
    validate_source_checkpoint(
        checkpoint,
        environment_freeze_path=environment_freeze_path,
        requirements_path=requirements_path,
        checkpoint_output_path=checkpoint_output_path,
        source_root=root,
        authorization=authorization_payload,
        expected_provenance=checkpoint["provenance"],  # type: ignore[arg-type]
    )
    return checkpoint


def _validate_stage_records(
    value: object,
    *,
    inventory_file_map: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    if not isinstance(value, list) or len(value) != len(EXPECTED_STAGE_ROOTS):
        raise ValueError("checkpoint stage-root inventory is incomplete")
    records: list[dict[str, object]] = []
    exact_keys = {
        "name",
        "relative_path",
        "artifact_id",
        "manifest_relative_path",
        "manifest_file_sha256",
        "manifest_content_sha256",
        "dates",
    }
    for observed, expected in zip(value, EXPECTED_STAGE_ROOTS, strict=True):
        if not isinstance(observed, Mapping) or set(observed) != exact_keys:
            raise ValueError("checkpoint stage-root record is invalid")
        name, relative_root, artifact_id = expected
        if (
            observed.get("name") != name
            or observed.get("relative_path") != relative_root
            or observed.get("artifact_id") != artifact_id
        ):
            raise ValueError("checkpoint stage-root IDs or paths changed")
        _safe_relative_path(
            observed.get("relative_path"),
            label="stage root",
            allow_dot=True,
        )
        manifest_relative = _safe_relative_path(
            observed.get("manifest_relative_path"),
            label="stage manifest",
        )
        expected_manifest = (
            "manifest.json"
            if relative_root == "."
            else f"{relative_root}/manifest.json"
        )
        if manifest_relative != expected_manifest:
            raise ValueError("checkpoint stage manifest path changed")
        file_row = inventory_file_map.get(manifest_relative)
        if file_row is None or observed.get("manifest_file_sha256") != file_row.get(
            "sha256"
        ):
            raise ValueError("checkpoint stage manifest file hash mismatch")
        content_hash = observed.get("manifest_content_sha256")
        if relative_root == "." and content_hash is not None:
            raise ValueError("census checkpoint stage content hash changed")
        if relative_root != "." and not _is_sha256(content_hash):
            raise ValueError("checkpoint stage content hash is invalid")
        _exact_dates(observed.get("dates"), label=f"{name} checkpoint stage dates")
        records.append(dict(observed))
    return records


def _validate_request_budget(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version",
        "allowed_hosts",
        "maximum_total_http_attempts",
        "total_attempts",
        "by_host",
    }:
        raise ValueError("checkpoint request-budget snapshot is invalid")
    if _strict_int(
        value.get("schema_version"),
        label="checkpoint request-budget schema version",
        minimum=1,
    ) != 1 or value.get("allowed_hosts") != list(EXPECTED_ALLOWED_HOSTS):
        raise ValueError("checkpoint request-budget authority changed")
    maximum = _strict_int(
        value.get("maximum_total_http_attempts"),
        label="checkpoint request ceiling",
        minimum=1,
    )
    total = _strict_int(value.get("total_attempts"), label="checkpoint total attempts")
    by_host = value.get("by_host")
    if not isinstance(by_host, Mapping):
        raise ValueError("checkpoint by-host request counts are invalid")
    clean: dict[str, int] = {}
    for host, count in by_host.items():
        if not isinstance(host, str) or host not in EXPECTED_ALLOWED_HOSTS:
            raise ValueError("checkpoint includes an unauthorized request host")
        clean[host] = _strict_int(count, label=f"checkpoint request count {host}")
    if list(by_host) != sorted(by_host) or sum(clean.values()) != total or total > maximum:
        raise ValueError("checkpoint request counts are inconsistent")
    return dict(value)


def _validate_checkpoint_inventory_subset(
    checkpoint_inventory: Mapping[str, object],
    observed_inventory: Mapping[str, object],
    *,
    source_root: Path,
) -> None:
    """Permit only a complete v0.3 scanner root after the provider checkpoint."""

    checkpoint_files = _inventory_file_map(checkpoint_inventory)
    observed_files = _inventory_file_map(observed_inventory)
    checkpoint_directories = set(checkpoint_inventory["directories"])  # type: ignore[arg-type]
    observed_directories = set(observed_inventory["directories"])  # type: ignore[arg-type]
    if not checkpoint_directories.issubset(observed_directories):
        raise ValueError("checkpointed source directories are missing after scanner freeze")
    for relative, expected in checkpoint_files.items():
        if observed_files.get(relative) != expected:
            raise ValueError(f"checkpointed source file changed or is missing: {relative}")

    extra_directories = observed_directories - checkpoint_directories
    extra_files = set(observed_files) - set(checkpoint_files)
    expected_extra_directories = {
        EXPECTED_SCANNER_SNAPSHOT_ROOT,
        *(
            f"{EXPECTED_SCANNER_SNAPSHOT_ROOT}/{trading_date}"
            for trading_date in EXPECTED_DATES
        ),
    }
    expected_extra_files = {
        f"{EXPECTED_SCANNER_SNAPSHOT_ROOT}/manifest.json",
        *(
            f"{EXPECTED_SCANNER_SNAPSHOT_ROOT}/{trading_date}/{filename}"
            for trading_date in EXPECTED_DATES
            for filename in ("manifest.json", "scanner-snapshot.json")
        ),
    }
    if extra_directories != expected_extra_directories:
        raise ValueError("post-checkpoint scanner directories are incomplete or contain extras")
    if extra_files != expected_extra_files:
        raise ValueError("post-checkpoint scanner files are incomplete or contain extras")
    manifest_relative = f"{EXPECTED_SCANNER_SNAPSHOT_ROOT}/manifest.json"
    manifest = load_json_object(source_root / manifest_relative)
    if manifest.get("artifact_id") != EXPECTED_SCANNER_SNAPSHOT_ROOT:
        raise ValueError("scanner snapshot artifact ID changed")
    _exact_dates(manifest.get("dates"), label="scanner snapshot dates")
    if not _is_sha256(manifest.get("content_sha256")):
        raise ValueError("scanner snapshot content hash is invalid")


def validate_source_checkpoint(
    checkpoint: Mapping[str, object],
    *,
    environment_freeze_path: str | Path,
    requirements_path: str | Path,
    checkpoint_output_path: str | Path | None = None,
    source_root: str | Path | None = None,
    authorization: Mapping[str, object] | None = None,
    expected_provenance: Mapping[str, object] | None = None,
    allow_scanner_snapshot_addition: bool = False,
) -> dict[str, object]:
    """Validate a checkpoint and optionally rehash its complete source tree."""

    payload = dict(checkpoint)
    if set(payload) != _CHECKPOINT_KEYS:
        raise ValueError("checkpoint keys changed")
    if _strict_int(
        payload.get("schema_version"),
        label="checkpoint schema version",
        minimum=1,
    ) != SCHEMA_VERSION or payload.get("artifact_id") != ARTIFACT_ID or payload.get(
        "artifact_type"
    ) != ARTIFACT_TYPE:
        raise ValueError("unsupported source checkpoint artifact")
    _exact_dates(payload.get("dates"), label="checkpoint dates")
    claimed = payload.get("content_sha256")
    if not _is_sha256(claimed):
        raise ValueError("checkpoint content hash is invalid")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if claimed != canonical_fingerprint(unsigned):
        raise ValueError("checkpoint content hash mismatch")

    authorization_binding = payload.get("authorization")
    if not isinstance(authorization_binding, Mapping) or set(authorization_binding) != {
        "authorization_id",
        "authorization_content_sha256",
    }:
        raise ValueError("checkpoint authorization binding is invalid")
    if authorization_binding.get("authorization_id") != AUTHORIZATION_ID or not _is_sha256(
        authorization_binding.get("authorization_content_sha256")
    ):
        raise ValueError("checkpoint authorization binding changed")

    provenance = payload.get("provenance")
    if not isinstance(provenance, Mapping) or set(provenance) != _PROVENANCE_KEYS:
        raise ValueError("checkpoint provenance is invalid")
    normalized_provenance = _provenance(
        repository=str(provenance.get("repository") or ""),
        authorization_commit_sha=str(
            provenance.get("authorization_commit_sha") or ""
        ),
        authorization_tree_sha=str(provenance.get("authorization_tree_sha") or ""),
        dispatcher_workflow_sha=str(provenance.get("dispatcher_workflow_sha") or ""),
        dispatcher_workflow_ref=str(provenance.get("dispatcher_workflow_ref") or ""),
        workflow_run_id=str(provenance.get("workflow_run_id") or ""),
        workflow_run_attempt=provenance.get("workflow_run_attempt"),  # type: ignore[arg-type]
    )
    if dict(provenance) != normalized_provenance:
        raise ValueError("checkpoint provenance is not canonical")
    if expected_provenance is not None and dict(provenance) != dict(expected_provenance):
        raise ValueError("checkpoint provenance does not match the expected run")

    budget = _validate_request_budget(payload.get("request_budget"))
    _validate_blocked_attempts(payload.get("blocked_attempts"), require_zero=True)
    _validate_environment_record(
        payload.get("environment"),
        environment_freeze_path=environment_freeze_path,
        requirements_path=requirements_path,
        source_root=source_root,
        checkpoint_output_path=checkpoint_output_path,
    )
    inventory = payload.get("inventory")
    if not isinstance(inventory, Mapping):
        raise ValueError("checkpoint inventory is missing")
    file_map = _inventory_file_map(inventory)
    _validate_stage_records(payload.get("stage_roots"), inventory_file_map=file_map)
    total_retained_bytes = _strict_int(
        payload.get("total_retained_bytes"),
        label="checkpoint retained bytes",
    )
    if total_retained_bytes != sum(int(row["size_bytes"]) for row in file_map.values()):
        raise ValueError("checkpoint retained-byte total is inconsistent")
    if payload.get("causal_boundary") != CAUSAL_BOUNDARY:
        raise ValueError("checkpoint causal boundary changed")

    validated_authorization: dict[str, object] | None = None
    if authorization is not None:
        validated_authorization = validate_authorization_envelope(authorization)
        if authorization_binding != {
            "authorization_id": validated_authorization["authorization_id"],
            "authorization_content_sha256": validated_authorization["content_sha256"],
        }:
            raise ValueError("checkpoint is bound to a different authorization")
        configured = validated_authorization["request_budget"]
        retention = validated_authorization["retention_budget"]
        assert isinstance(configured, Mapping) and isinstance(retention, Mapping)
        if budget["maximum_total_http_attempts"] != configured.get(
            "maximum_total_http_attempts_including_retries"
        ):
            raise ValueError("checkpoint request ceiling differs from authorization")
        if total_retained_bytes > _strict_int(
            retention.get("maximum_retained_bytes"),
            label="authorization retained-byte ceiling",
            minimum=1,
        ):
            raise ValueError("checkpoint exceeds authorization retention ceiling")

    if source_root is not None:
        root = Path(source_root)
        observed_inventory = inventory_source_tree(
            root,
            allow_scanner_snapshot_addition=allow_scanner_snapshot_addition,
        )
        if allow_scanner_snapshot_addition:
            _validate_checkpoint_inventory_subset(
                inventory,
                observed_inventory,
                source_root=root,
            )
        elif observed_inventory != inventory:
            raise ValueError("source tree changed after checkpoint inventory")
        observed_stages = _stage_root_records(root, observed_inventory)
        if observed_stages != payload.get("stage_roots"):
            raise ValueError("source stage manifests changed after checkpoint")
    return payload


def build_post_scanner_checkpoint_binding(
    checkpoint: Mapping[str, object],
    *,
    checkpoint_file_sha256: str,
    environment_freeze_path: str | Path,
    requirements_path: str | Path,
    checkpoint_output_path: str | Path,
    source_root: str | Path,
    authorization: Mapping[str, object],
    expected_provenance: Mapping[str, object],
) -> dict[str, object]:
    """Cross-bind the preserved checkpoint to the exact post-scanner tree."""

    if not _is_sha256(checkpoint_file_sha256):
        raise ValueError("checkpoint file SHA-256 is invalid")
    root = Path(source_root)
    checkpoint_path, _ = _resolved_regular_external_file(
        checkpoint_output_path,
        label="source checkpoint",
        expected_basename="source-checkpoint.json",
        source_root=root,
        checkpoint_output_path=None,
    )
    if _file_sha256(checkpoint_path) != checkpoint_file_sha256:
        raise ValueError("checkpoint file SHA-256 mismatch")
    if load_json_object(checkpoint_path) != dict(checkpoint):
        raise ValueError("checkpoint file payload differs from supplied checkpoint")

    validated = validate_source_checkpoint(
        checkpoint,
        environment_freeze_path=environment_freeze_path,
        requirements_path=requirements_path,
        checkpoint_output_path=checkpoint_path,
        source_root=root,
        authorization=authorization,
        expected_provenance=expected_provenance,
        allow_scanner_snapshot_addition=True,
    )
    final_inventory = inventory_source_tree(
        root,
        allow_scanner_snapshot_addition=True,
    )
    final_files = _inventory_file_map(final_inventory)
    pre_inventory = validated["inventory"]
    assert isinstance(pre_inventory, Mapping)
    binding: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "binding_type": POST_SCANNER_BINDING_TYPE,
        "checkpoint_artifact_id": validated["artifact_id"],
        "checkpoint_content_sha256": validated["content_sha256"],
        "checkpoint_file_sha256": checkpoint_file_sha256,
        "pre_scanner_tree_content_sha256": pre_inventory["tree_content_sha256"],
        "pre_scanner_file_count": pre_inventory["file_count"],
        "pre_scanner_retained_file_bytes": validated["total_retained_bytes"],
        "post_scanner_tree_content_sha256": final_inventory[
            "tree_content_sha256"
        ],
        "post_scanner_file_count": final_inventory["file_count"],
        "post_scanner_retained_file_bytes": sum(
            int(row["size_bytes"]) for row in final_files.values()
        ),
        "environment": validated["environment"],
        "request_budget": validated["request_budget"],
        "blocked_attempts": validated["blocked_attempts"],
        "provenance": validated["provenance"],
        "authorization": validated["authorization"],
        "sole_permitted_addition_id": EXPECTED_SCANNER_SNAPSHOT_ROOT,
    }
    binding["content_sha256"] = canonical_fingerprint(binding)
    return binding


def output_is_outside_source_root(
    output: str | Path,
    source_root: str | Path,
) -> bool:
    root = Path(source_root).resolve(strict=True)
    target = Path(output).resolve(strict=False)
    return target != root and root not in target.parents


def write_checkpoint_once(
    path: str | Path,
    checkpoint: Mapping[str, object],
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        dict(checkpoint),
        allow_nan=False,
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    ) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(target, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
