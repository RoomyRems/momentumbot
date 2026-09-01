"""Provider-free recovery of the exact normalized v0.4 failure checkpoint.

Run 33468687163 completed every market-discovery date before float enrichment
failed.  GitHub retained a normalized, label-blind failure checkpoint.  This
module binds that exact artifact and independently reloads all 30 identity,
market-candidate, and qualification-minute float-basis inputs.  It performs no
network access and does not import transcript or retrospective-label code.
"""

from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
from typing import Mapping

from momentumbot.causal_market_discovery_v03 import load_market_candidate_payload
from momentumbot.historical_float_v04 import load_float_target_basis
from momentumbot.identity_resolved_universe import load_identity_resolved_universe
from momentumbot.research.sealed_historical_availability import SELECTED_DATES
from momentumbot.research.sealed_historical_source_acquisition_v04 import (
    _source_tree_commitment,
)


SCHEMA_VERSION = 1
ARTIFACT_ID = "sealed-historical-source-recovery-v0.5-parent-v0.4"
PARENT_RUN_ID = "33468687163"
PARENT_RUN_ATTEMPT = 1
PARENT_FAILURE_CHECKPOINT_ARTIFACT_ID = 9790775145
PARENT_FAILURE_CHECKPOINT_ARTIFACT_NAME = (
    "sealed-historical-source-acquisition-v04-failure-checkpoint-33468687163-1"
)
PARENT_FAILURE_CHECKPOINT_ZIP_SHA256 = (
    "e9eb2854aa40d386509524475441f8ef159e0e73fcc63af4acf988b364ece1b9"
)
PARENT_FAILURE_SUMMARY_ZIP_SHA256 = (
    "150daca229e91c647b07f5b1f28ffc34b5c934c8de5257787075a90e74972ca3"
)
PARENT_CONSUMPTION_MARKER_ZIP_SHA256 = (
    "a30ab6de56fa090def6a00f1a42740ed4b08fb4267c71cda0da5b39d39b8e887"
)
PARENT_AUTHORIZATION_CONTENT_SHA256 = (
    "bbe51f4483a73f92b1f58c9f6c2085d8a47505346c2d340fbe59c0421f3f31b7"
)
PARENT_AUTHORIZATION_COMMIT_SHA = "ae55aabd3963a9d2764b19a759efd271c723a83a"
PARENT_AUTHORIZATION_TREE_SHA = "d58384a3096b4e39ed31a21af7870c569458e65f"
PARENT_DISPATCHER_WORKFLOW_SHA = "a53f6f36fb3a1ccb39e03eed0b13c406a02d9b69"
PARENT_SOURCE_TREE_CONTENT_SHA256 = (
    "03182a9b2ccaf026589986f73f6bb3e3c156b360eee5e0cae3f8fc31b1537607"
)
PARENT_SOURCE_FILE_COUNT = 523
PARENT_SOURCE_DIRECTORY_COUNT = 66
PARENT_SOURCE_RETAINED_BYTES = 537_662_001
PARENT_MARKET_ROOT_CONTENT_SHA256 = (
    "206431d94f8b6359fceb9627abb2d07acdcde414de2bfed351411b4b08e55852"
)
PARENT_IDENTITY_ROOT_CONTENT_SHA256 = (
    "225ed7b4fb4a9d8651b319250437a5f323f8961b2b61ef3a09849f83451ce3f5"
)
PARENT_SAFE_FAILURE_FILE_SHA256 = (
    "ca646fad65a03ca2e69090e876acf9d988da3cb81791d7e730f2f728f030571d"
)
PARENT_SAFE_FAILURE_CONTENT_SHA256 = (
    "ab2d6446e68be3ec9975cf76afc8f797e1680a1fb0ff06bdba7ae2f5d5cf876e"
)
PARENT_CONSUMPTION_FILE_SHA256 = (
    "6c26d80d90b1384750f683a32c7862ee800244f69f53f1bee1eb302ebff79a9f"
)
PARENT_CONSUMPTION_CONTENT_SHA256 = (
    "e7b93149b939e12fe92da3eb0840ca7e6969802442135bda1374ccc0aee4be98"
)
PARENT_REQUIREMENTS_SHA256 = (
    "0a9cce71ad0e35defb000e4b0b1a210ed9c41e84c6eb113e8ac79c242a5b52f3"
)
PARENT_ENVIRONMENT_FREEZE_SHA256 = (
    "64a429906d2a587b7fba60e9e5e300f4fbea8baaa1699ffe564b52db459dffb4"
)
PARENT_ENVIRONMENT_PROJECT_COMMIT_SHA = PARENT_AUTHORIZATION_COMMIT_SHA
PARENT_REQUEST_BUDGET = {
    "schema_version": 1,
    "total_attempts": 14_524,
    "by_host": {
        "api.massive.com": 363,
        "data.alpaca.markets": 14_155,
        "data.sec.gov": 6,
    },
}
PARENT_CANDIDATE_COUNT = 946
PARENT_MAX_CANDIDATES_PER_DATE = 48
EXPECTED_DATES = tuple(SELECTED_DATES)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_EDITABLE_PROJECT = re.compile(
    r"^-e git\+https://github\.com/RoomyRems/momentumbot(?:\.git)?@"
    r"([0-9a-f]{40})#egg=momentumbot$"
)


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


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _environment_freeze_parts(
    path: str | Path,
    *,
    expected_project_commit_sha: str,
    label: str,
) -> tuple[str, ...]:
    freeze_path = Path(path)
    if freeze_path.is_symlink() or not freeze_path.is_file():
        raise ValueError(f"{label} environment freeze must be a regular file")
    if _GIT_SHA.fullmatch(expected_project_commit_sha) is None:
        raise ValueError(f"{label} project commit is not a canonical Git SHA")
    raw = freeze_path.read_bytes()
    if not raw or not raw.endswith(b"\n") or b"\r" in raw:
        raise ValueError(f"{label} environment freeze text is not canonical")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} environment freeze is not UTF-8") from exc
    if not lines or any(not line for line in lines) or len(lines) != len(set(lines)):
        raise ValueError(f"{label} environment freeze lines are invalid")
    editable = [
        match for line in lines if (match := _EDITABLE_PROJECT.fullmatch(line))
    ]
    if len(editable) != 1 or editable[0].group(1) != expected_project_commit_sha:
        raise ValueError(f"{label} editable project commit changed")
    third_party = tuple(
        line for line in lines if _EDITABLE_PROJECT.fullmatch(line) is None
    )
    if not third_party:
        raise ValueError(f"{label} third-party environment is empty")
    return third_party


def validate_recovery_environment_pair(
    *,
    parent_environment_freeze_path: str | Path,
    child_environment_freeze_path: str | Path,
    expected_child_commit_sha: str,
) -> dict[str, object]:
    """Require identical dependencies while binding each editable checkout."""

    parent_path = Path(parent_environment_freeze_path)
    child_path = Path(child_environment_freeze_path)
    if file_sha256(parent_path) != PARENT_ENVIRONMENT_FREEZE_SHA256:
        raise ValueError("parent environment freeze hash changed")
    parent_dependencies = _environment_freeze_parts(
        parent_path,
        expected_project_commit_sha=PARENT_ENVIRONMENT_PROJECT_COMMIT_SHA,
        label="parent",
    )
    child_dependencies = _environment_freeze_parts(
        child_path,
        expected_project_commit_sha=expected_child_commit_sha,
        label="child",
    )
    if child_dependencies != parent_dependencies:
        raise ValueError("child third-party environment differs from parent")
    return {
        "schema_version": 1,
        "parent_environment_freeze_sha256": file_sha256(parent_path),
        "child_environment_freeze_sha256": file_sha256(child_path),
        "parent_project_commit_sha": PARENT_ENVIRONMENT_PROJECT_COMMIT_SHA,
        "child_project_commit_sha": expected_child_commit_sha,
        "third_party_environment_sha256": canonical_fingerprint(
            {"lines": list(parent_dependencies)}
        ),
    }


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def load_json_object(path: str | Path) -> dict[str, object]:
    payload = json.loads(
        Path(path).read_text(encoding="utf-8"),
        parse_constant=_reject_constant,
        object_pairs_hook=_reject_duplicates,
    )
    if not isinstance(payload, dict):
        raise ValueError("recovery JSON must be an object")
    return payload


def _validate_self_hash(payload: Mapping[str, object], *, label: str) -> None:
    claimed = payload.get("content_sha256")
    if not isinstance(claimed, str) or _SHA256.fullmatch(claimed) is None:
        raise ValueError(f"{label} content hash is invalid")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if claimed != canonical_fingerprint(unsigned):
        raise ValueError(f"{label} content hash mismatch")


def _validate_parent_layout(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("parent failure checkpoint root is invalid")
    required_files = {
        "consumption.json",
        "safe-failure.json",
        "provider-checkpoint/environment/pip-freeze.txt",
        "provider-checkpoint/environment/requirements-sealed-source-v04.txt",
    }
    observed_external: set[str] = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise ValueError("parent failure checkpoint contains a symlink")
        if path.is_file() and not relative.startswith("source/"):
            observed_external.add(relative)
        if not path.is_file() and not path.is_dir():
            raise ValueError("parent failure checkpoint contains a special file")
    if observed_external != required_files:
        raise ValueError("parent failure checkpoint external layout changed")


def _validate_parent_failure(payload: Mapping[str, object]) -> None:
    _validate_self_hash(payload, label="parent safe failure")
    if payload.get("content_sha256") != PARENT_SAFE_FAILURE_CONTENT_SHA256:
        raise ValueError("parent safe-failure content changed")
    if payload.get("artifact_type") != (
        "sealed_historical_source_acquisition_v0_4_safe_failure"
    ):
        raise ValueError("parent safe-failure artifact changed")
    authorization = payload.get("authorization")
    if authorization != {
        "authorization_id": "sealed-historical-source-acquisition-v0.4",
        "authorization_content_sha256": PARENT_AUTHORIZATION_CONTENT_SHA256,
    }:
        raise ValueError("parent safe-failure authorization changed")
    if payload.get("request_budget") != {
        **PARENT_REQUEST_BUDGET,
        "maximum_total_http_attempts": 40_000,
        "request_ceiling_exceeded": False,
        "unauthorized_hosts_detected": [],
    }:
        raise ValueError("parent safe-failure request accounting changed")
    stages = payload.get("completed_dates_by_stage")
    if not isinstance(stages, Mapping):
        raise ValueError("parent safe-failure stage accounting is missing")
    if stages.get("market_discovery") != list(EXPECTED_DATES):
        raise ValueError("parent market-discovery completion changed")
    for key in ("canonical_scanner_inputs", "float", "news", "scanner_snapshot"):
        if stages.get(key) != []:
            raise ValueError("parent safe failure overclaims a completed stage")
    provenance = payload.get("workflow_provenance")
    if not isinstance(provenance, Mapping) or provenance != {
        "authorization_branch": "phase-3-historical-snapshot",
        "authorization_commit_sha": PARENT_AUTHORIZATION_COMMIT_SHA,
        "authorization_path": (
            "research/strategy/sealed-historical-source-acquisition-v0.4.json"
        ),
        "authorization_tree_sha": PARENT_AUTHORIZATION_TREE_SHA,
        "dispatcher_workflow_path": (
            ".github/workflows/sealed-historical-source-acquisition-v04.yml"
        ),
        "dispatcher_workflow_ref": (
            "RoomyRems/momentumbot/.github/workflows/"
            "sealed-historical-source-acquisition-v04.yml@refs/heads/main"
        ),
        "dispatcher_workflow_sha": PARENT_DISPATCHER_WORKFLOW_SHA,
        "repository": "RoomyRems/momentumbot",
        "workflow_run_attempt": PARENT_RUN_ATTEMPT,
        "workflow_run_id": PARENT_RUN_ID,
    }:
        raise ValueError("parent safe-failure provenance changed")
    if payload.get("partial_retained_bytes") != PARENT_SOURCE_RETAINED_BYTES:
        raise ValueError("parent retained-byte accounting changed")


def _validate_parent_consumption(payload: Mapping[str, object]) -> None:
    _validate_self_hash(payload, label="parent consumption")
    if payload.get("content_sha256") != PARENT_CONSUMPTION_CONTENT_SHA256:
        raise ValueError("parent consumption content changed")
    if payload.get("authorization") != {
        "authorization_id": "sealed-historical-source-acquisition-v0.4",
        "authorization_content_sha256": PARENT_AUTHORIZATION_CONTENT_SHA256,
    }:
        raise ValueError("parent consumption authorization changed")
    one_shot = payload.get("one_shot_attestation")
    if one_shot != {
        "authorization_consumed": True,
        "automatic_rerun_allowed": False,
        "provider_call_made_before_marker": False,
        "workflow_run_attempt_required": 1,
    }:
        raise ValueError("parent consumption boundary changed")


def validate_parent_failure_checkpoint(root: str | Path) -> dict[str, object]:
    checkpoint_root = Path(root)
    _validate_parent_layout(checkpoint_root)
    safe_path = checkpoint_root / "safe-failure.json"
    consumption_path = checkpoint_root / "consumption.json"
    requirements_path = (
        checkpoint_root
        / "provider-checkpoint/environment/requirements-sealed-source-v04.txt"
    )
    freeze_path = checkpoint_root / "provider-checkpoint/environment/pip-freeze.txt"
    if file_sha256(safe_path) != PARENT_SAFE_FAILURE_FILE_SHA256:
        raise ValueError("parent safe-failure file hash changed")
    if file_sha256(consumption_path) != PARENT_CONSUMPTION_FILE_SHA256:
        raise ValueError("parent consumption file hash changed")
    if file_sha256(requirements_path) != PARENT_REQUIREMENTS_SHA256:
        raise ValueError("parent requirements hash changed")
    if file_sha256(freeze_path) != PARENT_ENVIRONMENT_FREEZE_SHA256:
        raise ValueError("parent environment freeze hash changed")
    safe_failure = load_json_object(safe_path)
    consumption = load_json_object(consumption_path)
    _validate_parent_failure(safe_failure)
    _validate_parent_consumption(consumption)

    source_root = checkpoint_root / "source"
    commitment = _source_tree_commitment(source_root)
    if (
        commitment.get("tree_content_sha256")
        != PARENT_SOURCE_TREE_CONTENT_SHA256
        or commitment.get("file_count") != PARENT_SOURCE_FILE_COUNT
        or commitment.get("directory_count") != PARENT_SOURCE_DIRECTORY_COUNT
        or commitment.get("retained_file_bytes") != PARENT_SOURCE_RETAINED_BYTES
    ):
        raise ValueError("parent normalized source tree changed")
    forbidden_roots = {
        "causal-sec-float-v0.2",
        "causal-alpaca-news-v0.2",
        "causal-scanner-source-inputs-v0.2",
        "causal-scanner-snapshot-v0.3",
    }
    if any((source_root / value).exists() for value in forbidden_roots):
        raise ValueError("parent source contains a stage that never completed")

    identity_root = source_root / "identity-resolved-universe-v0.1"
    _, _, identity_manifest = load_identity_resolved_universe(
        identity_root,
        trading_date=EXPECTED_DATES[0],
    )
    if identity_manifest.get("content_sha256") != PARENT_IDENTITY_ROOT_CONTENT_SHA256:
        raise ValueError("parent identity bundle changed")
    market_root = source_root / "causal-market-discovery-v0.3"
    market_manifest = load_json_object(market_root / "manifest.json")
    if (
        market_manifest.get("dates") != list(EXPECTED_DATES)
        or market_manifest.get("content_sha256")
        != PARENT_MARKET_ROOT_CONTENT_SHA256
    ):
        raise ValueError("parent market root changed")

    counts: dict[str, int] = {}
    for trading_date in EXPECTED_DATES:
        candidates, candidate_payload, date_manifest = load_market_candidate_payload(
            market_root / trading_date
        )
        target_relative = date_manifest.get("files", {}).get("float_target_basis")
        if not isinstance(target_relative, str):
            raise ValueError("parent market date lacks float target basis")
        pairs, _ = load_float_target_basis(
            market_root / trading_date / target_relative,
            candidate_rows=candidates,
            candidate_payload=candidate_payload,
            expected_trading_date=date.fromisoformat(trading_date),
        )
        if set(pairs) != {str(row["symbol"]) for row in candidates}:
            raise ValueError("parent float target-basis candidate set changed")
        counts[trading_date] = len(candidates)
    if sum(counts.values()) != PARENT_CANDIDATE_COUNT:
        raise ValueError("parent candidate total changed")
    if max(counts.values()) != PARENT_MAX_CANDIDATES_PER_DATE:
        raise ValueError("parent maximum candidate count changed")

    result: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": ARTIFACT_ID,
        "parent_run": {
            "repository": "RoomyRems/momentumbot",
            "workflow_run_id": PARENT_RUN_ID,
            "workflow_run_attempt": PARENT_RUN_ATTEMPT,
            "failure_checkpoint_artifact_id": PARENT_FAILURE_CHECKPOINT_ARTIFACT_ID,
            "failure_checkpoint_artifact_name": PARENT_FAILURE_CHECKPOINT_ARTIFACT_NAME,
            "failure_checkpoint_zip_sha256": PARENT_FAILURE_CHECKPOINT_ZIP_SHA256,
            "failure_summary_zip_sha256": PARENT_FAILURE_SUMMARY_ZIP_SHA256,
            "consumption_marker_zip_sha256": PARENT_CONSUMPTION_MARKER_ZIP_SHA256,
        },
        "source_commitment": {
            "tree_content_sha256": PARENT_SOURCE_TREE_CONTENT_SHA256,
            "file_count": PARENT_SOURCE_FILE_COUNT,
            "directory_count": PARENT_SOURCE_DIRECTORY_COUNT,
            "retained_file_bytes": PARENT_SOURCE_RETAINED_BYTES,
            "identity_root_content_sha256": PARENT_IDENTITY_ROOT_CONTENT_SHA256,
            "market_root_content_sha256": PARENT_MARKET_ROOT_CONTENT_SHA256,
        },
        "dates": list(EXPECTED_DATES),
        "candidate_counts": counts,
        "candidate_count": sum(counts.values()),
        "request_budget_seed": PARENT_REQUEST_BUDGET,
        "causal_boundary": {
            "normalized_parent_source_reused_exactly": True,
            "parent_provider_requests_repeated": False,
            "raw_provider_http_responses_present": False,
            "scanner_float_news_or_runtime_outputs_present": False,
            "transcript_or_label_values_read": False,
        },
    }
    result["content_sha256"] = canonical_fingerprint(result)
    return result


def _write_json_once(path: Path, payload: object) -> None:
    if path.exists():
        raise FileExistsError(f"recovery output already exists: {path.name}")
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise ValueError("recovery output parent is invalid")
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def materialize_parent_recovery(
    parent_root: str | Path,
    *,
    source_output: str | Path,
    recovery_receipt_output: str | Path,
    request_budget_output: str | Path,
    blocked_attempt_output: str | Path,
) -> dict[str, object]:
    parent = Path(parent_root)
    receipt = validate_parent_failure_checkpoint(parent)
    source_target = Path(source_output)
    if source_target.exists():
        raise FileExistsError("recovery source output already exists")
    for ancestor in (source_target.parent,):
        if ancestor.is_symlink() or not ancestor.is_dir():
            raise ValueError("recovery source parent is invalid")
    shutil.copytree(parent / "source", source_target, copy_function=shutil.copy2)
    copied = _source_tree_commitment(source_target)
    expected = receipt["source_commitment"]
    if not isinstance(expected, Mapping) or any(
        copied.get(key) != expected.get(key)
        for key in (
            "tree_content_sha256",
            "file_count",
            "directory_count",
            "retained_file_bytes",
        )
    ):
        raise ValueError("materialized recovery source differs from parent")
    _write_json_once(Path(recovery_receipt_output), receipt)
    _write_json_once(Path(request_budget_output), PARENT_REQUEST_BUDGET)
    _write_json_once(
        Path(blocked_attempt_output),
        {
            "schema_version": 1,
            "total_blocked_attempts": 0,
            "by_category": {
                "hostname": 0,
                "https_transport": 0,
                "redirect": 0,
                "request_budget": 0,
                "socket": 0,
                "subprocess": 0,
            },
            "by_host": {},
        },
    )
    return receipt


__all__ = [
    "ARTIFACT_ID",
    "PARENT_REQUEST_BUDGET",
    "PARENT_SOURCE_TREE_CONTENT_SHA256",
    "canonical_fingerprint",
    "file_sha256",
    "materialize_parent_recovery",
    "validate_recovery_environment_pair",
    "validate_parent_failure_checkpoint",
]
