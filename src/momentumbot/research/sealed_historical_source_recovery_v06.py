"""Provider-free recovery of the exact normalized v0.5 failure checkpoint.

Run 33516311649 reused every normalized market-discovery date and then failed
at the first authoritative unique-CIK-fallback identity. GitHub retained the
complete label-blind source. This module binds that exact artifact, its
composite request ledger, and the independently reproduced identity mismatch.
It performs no network access and imports no transcript or label code.
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
from momentumbot.historical_float_identity_v06 import candidate_identity_v06
from momentumbot.identity_resolved_universe import load_identity_resolved_universe
from momentumbot.research.sealed_historical_availability import SELECTED_DATES
from momentumbot.research.sealed_historical_source_acquisition_v04 import (
    _source_tree_commitment,
)


SCHEMA_VERSION = 1
ARTIFACT_ID = "sealed-historical-source-recovery-v0.6-parent-v0.5"
PARENT_RUN_ID = "33516311649"
PARENT_RUN_ATTEMPT = 1
PARENT_FAILURE_CHECKPOINT_ARTIFACT_ID = 9803791643
PARENT_FAILURE_CHECKPOINT_ARTIFACT_NAME = (
    "sealed-historical-source-acquisition-v05-failure-checkpoint-33516311649-1"
)
PARENT_FAILURE_CHECKPOINT_ZIP_SHA256 = (
    "0c40d099acf86fef16203f8dc7fefb104abd71668a37ffc6e450e2513d469c35"
)
PARENT_FAILURE_SUMMARY_ZIP_SHA256 = (
    "3069408571732288238c8f839257a085b2c7fa25a92853e8d962a79bf55312ea"
)
PARENT_CONSUMPTION_MARKER_ZIP_SHA256 = (
    "f0395b5cabdcb6b0a6318efa3f8d3796946ba8da2bd8e093d007593e7a4fd52f"
)
PARENT_AUTHORIZATION_CONTENT_SHA256 = (
    "23ad997837490c14c200c10b34c8285db7b18ddebca131e6299a8cd70b3bbc49"
)
PARENT_AUTHORIZATION_COMMIT_SHA = "12d3c08dcfa042f785c6e35060916cfbd47a1df8"
PARENT_AUTHORIZATION_TREE_SHA = "c9f3f47814376519a2d4ff5f77ed449f3e445a9d"
PARENT_DISPATCHER_WORKFLOW_SHA = "40bd399245654c5608abebf249d08c2f69403381"
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
    "92c13066948710f0ed7cbfcfba7a8be2ca10865c21d61c9d20db2ff843d47950"
)
PARENT_SAFE_FAILURE_CONTENT_SHA256 = (
    "a263933e493038b93d254885b78d496777e158817c7ec183731aa523eb869f73"
)
PARENT_CONSUMPTION_FILE_SHA256 = (
    "3224f328f6587c6f11e6904daceb8f904362707bfc6ee7af8145507280f2f2d2"
)
PARENT_CONSUMPTION_CONTENT_SHA256 = (
    "fdde6fbe2aa59515c4742ad670f517395dd656f289837d937cba2b9d2d2ce584"
)
PARENT_REQUIREMENTS_SHA256 = (
    "0a9cce71ad0e35defb000e4b0b1a210ed9c41e84c6eb113e8ac79c242a5b52f3"
)
PARENT_ENVIRONMENT_FREEZE_SHA256 = (
    "656c9cc6c828c7bc9f2a3d271ab87dd6c7478d0791afe4130e78f1f9156e6a89"
)
PARENT_BLOCKED_ATTEMPTS_SHA256 = (
    "c5440e87d25a712789d5c39f7ce22e44f176afcb181510fd49c0823eba908f9b"
)
PARENT_NORMALIZATION_DIAGNOSTICS_SHA256 = (
    "2e70f1cabfdbd2e034e414b8d7615d5b508ebcad238503b36fbeb986fa6d671a"
)
PARENT_RECOVERY_RECEIPT_SHA256 = (
    "d785578b0d53190f22b1d76a0b24cd5aa0d9f405f27bd0d13177173b5d3f543c"
)
PARENT_REQUEST_BUDGET_SHA256 = (
    "0361d6bd289b443f1f895609fe6adb5967e01639f85528bd72237b30b66ad73f"
)
PARENT_ENVIRONMENT_PROJECT_COMMIT_SHA = PARENT_AUTHORIZATION_COMMIT_SHA
PARENT_REQUEST_BUDGET = {
    "schema_version": 1,
    "total_attempts": 14_536,
    "by_host": {
        "api.massive.com": 363,
        "data.alpaca.markets": 14_161,
        "data.sec.gov": 12,
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
        "provider-checkpoint/blocked-attempts.json",
        "provider-checkpoint/environment/pip-freeze.txt",
        "provider-checkpoint/environment/requirements-sealed-source-v04.txt",
        "provider-checkpoint/float-normalization-rejections.json",
        "provider-checkpoint/parent-recovery-receipt.json",
        "provider-checkpoint/request-budget.json",
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
    if payload.get("artifact_type") != "sealed_historical_source_recovery_v0_5_safe_failure":
        raise ValueError("parent safe-failure artifact changed")
    authorization = payload.get("authorization")
    if authorization != {
        "authorization_id": "sealed-historical-source-acquisition-v0.5",
        "authorization_content_sha256": PARENT_AUTHORIZATION_CONTENT_SHA256,
    }:
        raise ValueError("parent safe-failure authorization changed")
    if payload.get("request_budget") != {
        "allowed_hosts": [
            "api.massive.com",
            "data.alpaca.markets",
            "data.sec.gov",
        ],
        "by_host": PARENT_REQUEST_BUDGET["by_host"],
        "child_attempts": 12,
        "maximum_total_http_attempts": 40_000,
        "parent_by_host": {
            "api.massive.com": 363,
            "data.alpaca.markets": 14_155,
            "data.sec.gov": 6,
        },
        "parent_total_attempts": 14_524,
        "request_ceiling_exhausted": False,
        "schema_version": 1,
        "total_attempts": 14_536,
        "unauthorized_hosts_detected": [],
    }:
        raise ValueError("parent safe-failure request accounting changed")
    stages = payload.get("completed_dates_by_stage")
    if not isinstance(stages, Mapping):
        raise ValueError("parent safe-failure stage accounting is missing")
    if stages.get("market_discovery_recovered") != list(EXPECTED_DATES):
        raise ValueError("parent market-discovery completion changed")
    for key in ("canonical_scanner_inputs", "float", "news", "scanner_snapshot"):
        if stages.get(key) != []:
            raise ValueError("parent safe failure overclaims a completed stage")
    provenance = payload.get("workflow_provenance")
    if not isinstance(provenance, Mapping) or provenance != {
        "authorization_branch": "phase-3-historical-snapshot",
        "authorization_commit_sha": PARENT_AUTHORIZATION_COMMIT_SHA,
        "authorization_path": (
            "research/strategy/sealed-historical-source-acquisition-v0.5.json"
        ),
        "authorization_tree_sha": PARENT_AUTHORIZATION_TREE_SHA,
        "dispatcher_workflow_path": (
            ".github/workflows/sealed-historical-source-acquisition-v05.yml"
        ),
        "dispatcher_workflow_ref": (
            "RoomyRems/momentumbot/.github/workflows/"
            "sealed-historical-source-acquisition-v05.yml@refs/heads/main"
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
        "authorization_id": "sealed-historical-source-acquisition-v0.5",
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
    if payload.get("consumption_ref") != {
        "creation_mode": "atomic_create_only_git_ref",
        "name": (
            "refs/tags/sealed-historical-source-acquisition-v05-consumed-"
            + PARENT_AUTHORIZATION_CONTENT_SHA256
        ),
        "target_commit_sha": PARENT_AUTHORIZATION_COMMIT_SHA,
    }:
        raise ValueError("parent consumption ref changed")


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
    blocked_path = checkpoint_root / "provider-checkpoint/blocked-attempts.json"
    diagnostics_path = (
        checkpoint_root / "provider-checkpoint/float-normalization-rejections.json"
    )
    recovery_path = checkpoint_root / "provider-checkpoint/parent-recovery-receipt.json"
    budget_path = checkpoint_root / "provider-checkpoint/request-budget.json"
    if file_sha256(safe_path) != PARENT_SAFE_FAILURE_FILE_SHA256:
        raise ValueError("parent safe-failure file hash changed")
    if file_sha256(consumption_path) != PARENT_CONSUMPTION_FILE_SHA256:
        raise ValueError("parent consumption file hash changed")
    if file_sha256(requirements_path) != PARENT_REQUIREMENTS_SHA256:
        raise ValueError("parent requirements hash changed")
    if file_sha256(freeze_path) != PARENT_ENVIRONMENT_FREEZE_SHA256:
        raise ValueError("parent environment freeze hash changed")
    for path, expected, label in (
        (blocked_path, PARENT_BLOCKED_ATTEMPTS_SHA256, "blocked attempts"),
        (
            diagnostics_path,
            PARENT_NORMALIZATION_DIAGNOSTICS_SHA256,
            "normalization diagnostics",
        ),
        (recovery_path, PARENT_RECOVERY_RECEIPT_SHA256, "recovery receipt"),
        (budget_path, PARENT_REQUEST_BUDGET_SHA256, "request budget"),
    ):
        if file_sha256(path) != expected:
            raise ValueError(f"parent {label} hash changed")
    safe_failure = load_json_object(safe_path)
    consumption = load_json_object(consumption_path)
    _validate_parent_failure(safe_failure)
    _validate_parent_consumption(consumption)
    if load_json_object(budget_path) != PARENT_REQUEST_BUDGET:
        raise ValueError("parent request-budget payload changed")
    if load_json_object(blocked_path) != {
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
    }:
        raise ValueError("parent blocked-attempt payload changed")
    diagnostics = load_json_object(diagnostics_path)
    if (
        diagnostics.get("artifact_id")
        != "causal-float-normalization-rejections-v0.1"
        or diagnostics.get("candidate_rejection_count") != 0
        or diagnostics.get("candidate_rejections") != []
        or diagnostics.get("content_sha256")
        != "2cce59443d35a7034d3025392da67708db27ad4ea6449b41e143c0df067da6c9"
    ):
        raise ValueError("parent normalization diagnostics changed")
    recovery = load_json_object(recovery_path)
    if (
        recovery.get("artifact_id")
        != "sealed-historical-source-recovery-v0.5-parent-v0.4"
        or recovery.get("content_sha256")
        != "674ac119d07ba7308b2379e5702c1e3e21be5f534e929b3e8593f2ef0a037d9d"
    ):
        raise ValueError("parent recovery receipt changed")

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
    identity_kind_counts = {
        "composite_figi": 0,
        "unique_cik_fallback": 0,
    }
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
        for candidate in candidates:
            identity = candidate_identity_v06(candidate)
            identity_kind_counts[identity["identity_identifier_kind"]] += 1
        counts[trading_date] = len(candidates)
    if sum(counts.values()) != PARENT_CANDIDATE_COUNT:
        raise ValueError("parent candidate total changed")
    if max(counts.values()) != PARENT_MAX_CANDIDATES_PER_DATE:
        raise ValueError("parent maximum candidate count changed")
    if identity_kind_counts != {
        "composite_figi": 737,
        "unique_cik_fallback": 209,
    }:
        raise ValueError("parent authoritative identity-kind census changed")

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
        "identity_kind_counts": identity_kind_counts,
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
