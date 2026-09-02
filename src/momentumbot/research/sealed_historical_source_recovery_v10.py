"""Provider-free recovery of the exact v0.9 scanner-acquisition checkpoint.

Run 33577895166 completed all 30 news dates, then failed while serializing the
first canonical scanner-input date.  The exact RVOL calculator emitted its
intended complete minute grid while the raw BLRX bars began only with the first
observed trade minute.  The frozen writer incorrectly required those source
indexes to be identical before projecting RVOL onto raw-bar timestamps.

This module binds the exact retained v0.9 checkpoint, cumulative request
ledger, complete market/float/news trees, and the partial BLRX scanner tape.
Materialization validates the parent byte-for-byte and removes only that
unreadable partial scanner directory so v0.10 can rebuild canonical scanner
inputs under the additive alignment adapter.  It imports no transcript or
label code and performs no network access.
"""

from __future__ import annotations

from datetime import date
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
from typing import Mapping

from momentumbot.causal_market_discovery_v03 import load_market_candidate_payload
from momentumbot.historical_float_identity_v06 import candidate_identity_v06
from momentumbot.historical_float_identity_v09 import (
    EXPECTED_FLOAT_ROOT_CONTENT_SHA256,
    build_downstream_identity_preflight_receipt,
)
from momentumbot.historical_float_v04 import load_float_target_basis
from momentumbot.identity_resolved_universe import load_identity_resolved_universe
from momentumbot.research.sealed_historical_availability import SELECTED_DATES
from momentumbot.research.sealed_historical_source_acquisition_v04 import (
    _source_tree_commitment,
)


SCHEMA_VERSION = 1
ARTIFACT_ID = "sealed-historical-source-recovery-v0.10-parent-v0.9"
PARENT_RUN_ID = "33577895166"
PARENT_RUN_ATTEMPT = 1
PARENT_FAILURE_CHECKPOINT_ARTIFACT_ID = 9827444933
PARENT_FAILURE_CHECKPOINT_ARTIFACT_NAME = (
    "sealed-historical-source-acquisition-v09-failure-checkpoint-33577895166-1"
)
PARENT_FAILURE_CHECKPOINT_ZIP_SHA256 = (
    "0db44af6ffe695642444e384378faf3dfb3b6be8e059c0dca7bc0ee77d589244"
)
PARENT_FAILURE_SUMMARY_ZIP_SHA256 = (
    "abfc32a08bc0995b7ee23ebdf8ebd3d2def7f1227273e3ddd8a80ee174718ffe"
)
PARENT_CONSUMPTION_MARKER_ZIP_SHA256 = (
    "45ffd55148274751a71d51f5d43b26d99fd828ad8ed29fa96afc0f70a3ed4049"
)
PARENT_UPSTREAM_PROGRESS_ZIP_SHA256 = (
    "9442dd289f7ae5bf8413159cde1cbc15f913d51b38d959e5e9eed4b7316cc40b"
)
PARENT_AUTHORIZATION_CONTENT_SHA256 = (
    "447c11b09206b4c19ccade6c1aae70ce5bb17e4a483db6f9581d14ee3f5f862f"
)
PARENT_AUTHORIZATION_COMMIT_SHA = "92d8b4deceae5c2bb6edfb10016a0e05c33c8bfa"
PARENT_AUTHORIZATION_TREE_SHA = "d214d0990665a92ea24760a972232998378fae38"
PARENT_DISPATCHER_WORKFLOW_SHA = "b92a236dc92e8311c70c1b76ab657cea809fbe90"
PARENT_SOURCE_TREE_CONTENT_SHA256 = (
    "60113df5eb307e3c5f31ab075017c9cca4e1da70c2177de40c26df7bed7a5f9f"
)
PARENT_SOURCE_FILE_COUNT = 646
PARENT_SOURCE_DIRECTORY_COUNT = 130
PARENT_SOURCE_RETAINED_BYTES = 544_738_038
RECOVERED_SOURCE_TREE_CONTENT_SHA256 = (
    "69ead0aa5a8eafc5b207627b2b0080ba3005abca33b84612072d1363c1f3dbc8"
)
RECOVERED_SOURCE_FILE_COUNT = 645
RECOVERED_SOURCE_DIRECTORY_COUNT = 128
RECOVERED_SOURCE_RETAINED_BYTES = 543_955_728
PARENT_MARKET_ROOT_CONTENT_SHA256 = (
    "206431d94f8b6359fceb9627abb2d07acdcde414de2bfed351411b4b08e55852"
)
PARENT_IDENTITY_ROOT_CONTENT_SHA256 = (
    "225ed7b4fb4a9d8651b319250437a5f323f8961b2b61ef3a09849f83451ce3f5"
)
PARENT_FLOAT_ROOT_CONTENT_SHA256 = EXPECTED_FLOAT_ROOT_CONTENT_SHA256
PARENT_NEWS_ROOT_CONTENT_SHA256 = (
    "da590a556a1c166d2e94ccea43a14e6dd1ba1a8e632f9d0620b9ef793171448a"
)
PARENT_PARTIAL_SCANNER_FILE_SHA256 = (
    "076fe05c8101f70679c884f6fc84c65cdd8fa78b6d378aa34022eb094f144377"
)
PARENT_PARTIAL_SCANNER_FILE_SIZE = 782_310
PARENT_BLRX_RAW_TIMESTAMP_SHA256 = (
    "e8899e681460b9e504b3c28e62849820afca44c60ee6db2d8f5020cc06a5f9cc"
)
PARENT_SAFE_FAILURE_FILE_SHA256 = (
    "16afa966d6ee07bb9d6b9d3a6385b8b86c5b1c06519f086063dee330753c7431"
)
PARENT_SAFE_FAILURE_CONTENT_SHA256 = (
    "812621e6b2c79574ecf8b5ccf14d67050179cccb2d619e3fa047a4a8e16da562"
)
PARENT_CONSUMPTION_FILE_SHA256 = (
    "809019e92ffcb2bcfa1525d98e4533a998e8063c2b25469162febcb401be245f"
)
PARENT_CONSUMPTION_CONTENT_SHA256 = (
    "022bb96d46b0d8c13c6430a03003625e682558ea0ba8cb2915c23e1d503057ff"
)
PARENT_REQUIREMENTS_SHA256 = (
    "0a9cce71ad0e35defb000e4b0b1a210ed9c41e84c6eb113e8ac79c242a5b52f3"
)
PARENT_ENVIRONMENT_FREEZE_SHA256 = (
    "85204ff9e9aba18b29e57a2aa019afea27803eaa64811af4b962247992abf5c6"
)
PARENT_BLOCKED_ATTEMPTS_SHA256 = (
    "c5440e87d25a712789d5c39f7ce22e44f176afcb181510fd49c0823eba908f9b"
)
PARENT_NORMALIZATION_DIAGNOSTICS_SHA256 = (
    "2e70f1cabfdbd2e034e414b8d7615d5b508ebcad238503b36fbeb986fa6d671a"
)
PARENT_RECOVERY_RECEIPT_SHA256 = (
    "16c5fd78db03ec69d37e0e45dd11eec69dbb18f9be34ac0a4f6aab38107aaadd"
)
PARENT_REQUEST_BUDGET_SHA256 = (
    "37e665bcf39cd9f9b715051bc8c415735c6fc2ab56ff448be09f658af86bbe81"
)
PARENT_ENVIRONMENT_PROJECT_COMMIT_SHA = PARENT_AUTHORIZATION_COMMIT_SHA
PARENT_REQUEST_BUDGET = {
    "schema_version": 1,
    "total_attempts": 17_844,
    "by_host": {
        "api.massive.com": 363,
        "data.alpaca.markets": 16_153,
        "data.sec.gov": 1_328,
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
    if payload.get("artifact_type") != "sealed_historical_source_recovery_v0_9_safe_failure":
        raise ValueError("parent safe-failure artifact changed")
    authorization = payload.get("authorization")
    if authorization != {
        "authorization_id": "sealed-historical-source-acquisition-v0.9",
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
        "child_attempts": 304,
        "maximum_total_http_attempts": 40_000,
        "parent_by_host": {
            "api.massive.com": 363,
            "data.alpaca.markets": 15_849,
            "data.sec.gov": 1_328,
        },
        "parent_total_attempts": 17_540,
        "request_ceiling_exhausted": False,
        "schema_version": 1,
        "total_attempts": 17_844,
        "unauthorized_hosts_detected": [],
    }:
        raise ValueError("parent safe-failure request accounting changed")
    stages = payload.get("completed_dates_by_stage")
    if not isinstance(stages, Mapping):
        raise ValueError("parent safe-failure stage accounting is missing")
    if stages.get("market_discovery_recovered") != list(EXPECTED_DATES):
        raise ValueError("parent market-discovery completion changed")
    for key in ("float", "news"):
        if stages.get(key) != list(EXPECTED_DATES):
            raise ValueError(f"parent {key} completion changed")
    for key in ("canonical_scanner_inputs", "scanner_snapshot"):
        if stages.get(key) != []:
            raise ValueError("parent safe failure overclaims a completed stage")
    provenance = payload.get("workflow_provenance")
    if not isinstance(provenance, Mapping) or provenance != {
        "authorization_branch": "phase-3-historical-snapshot",
        "authorization_commit_sha": PARENT_AUTHORIZATION_COMMIT_SHA,
        "authorization_path": (
            "research/strategy/sealed-historical-source-acquisition-v0.9.json"
        ),
        "authorization_tree_sha": PARENT_AUTHORIZATION_TREE_SHA,
        "dispatcher_workflow_path": (
            ".github/workflows/sealed-historical-source-acquisition-v09.yml"
        ),
        "dispatcher_workflow_ref": (
            "RoomyRems/momentumbot/.github/workflows/"
            "sealed-historical-source-acquisition-v09.yml@refs/heads/main"
        ),
        "dispatcher_workflow_sha": PARENT_DISPATCHER_WORKFLOW_SHA,
        "repository": "RoomyRems/momentumbot",
        "workflow_run_attempt": PARENT_RUN_ATTEMPT,
        "workflow_run_id": PARENT_RUN_ID,
    }:
        raise ValueError("parent safe-failure provenance changed")
    if payload.get("partial_retained_bytes") != PARENT_SOURCE_RETAINED_BYTES:
        raise ValueError("parent retained-byte accounting changed")
    if payload.get("causal_attestation") != {
        "account_or_order_endpoint_called": False,
        "automatic_rerun_allowed": False,
        "databento_called": False,
        "order_submitted": False,
        "raw_provider_http_responses_persisted": False,
        "ross_labels_or_outcomes_read": False,
        "transcript_record_values_read": False,
    }:
        raise ValueError("parent causal boundary changed")


def _validate_parent_consumption(payload: Mapping[str, object]) -> None:
    _validate_self_hash(payload, label="parent consumption")
    if payload.get("content_sha256") != PARENT_CONSUMPTION_CONTENT_SHA256:
        raise ValueError("parent consumption content changed")
    if payload.get("authorization") != {
        "authorization_id": "sealed-historical-source-acquisition-v0.9",
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
            "refs/tags/sealed-historical-source-acquisition-v09-consumed-"
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
        != "sealed-historical-source-recovery-v0.9-parent-v0.6"
        or recovery.get("content_sha256")
        != "44f020cb81c11c13ca8fb9729c9bd7cf05c540a89ed9f88be20c960a3b3eb342"
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
    if (source_root / "causal-scanner-snapshot-v0.3").exists():
        raise ValueError("parent source contains a scanner snapshot that never completed")

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
    news_root = source_root / "causal-alpaca-news-v0.2"
    news_manifest = load_json_object(news_root / "manifest.json")
    if (
        news_manifest.get("dates") != list(EXPECTED_DATES)
        or news_manifest.get("content_sha256") != PARENT_NEWS_ROOT_CONTENT_SHA256
    ):
        raise ValueError("parent news root changed")

    partial_root = source_root / "causal-scanner-source-inputs-v0.2"
    partial_file = partial_root / EXPECTED_DATES[0] / "market-inputs.jsonl.gz"
    observed_partial = sorted(
        path.relative_to(partial_root).as_posix()
        for path in partial_root.rglob("*")
        if path.is_file()
    )
    if observed_partial != [f"{EXPECTED_DATES[0]}/market-inputs.jsonl.gz"]:
        raise ValueError("parent partial scanner-input layout changed")
    if (
        partial_file.stat().st_size != PARENT_PARTIAL_SCANNER_FILE_SIZE
        or file_sha256(partial_file) != PARENT_PARTIAL_SCANNER_FILE_SHA256
    ):
        raise ValueError("parent partial scanner-input file changed")
    partial_counts: dict[str, int] = {}
    blrx_timestamps: list[str] = []
    with gzip.open(partial_file, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.endswith("\n") or "\t" not in line:
                raise ValueError("parent partial scanner-input framing changed")
            kind, encoded = line[:-1].split("\t", 1)
            value = json.loads(
                encoded,
                parse_constant=_reject_constant,
                object_pairs_hook=_reject_duplicates,
            )
            if not isinstance(value, dict):
                raise ValueError("parent partial scanner-input record changed")
            partial_counts[kind] = partial_counts.get(kind, 0) + 1
            if kind == "candidate_raw_bar" and value.get("symbol") == "BLRX":
                blrx_timestamps.append(str(value.get("bar_started_at") or ""))
    if partial_counts != {
        "contract": 1,
        "membership": 5_421,
        "previous_close": 5_421,
        "rank_split_close_bar": 136_018,
        "candidate_raw_bar": 3_078,
    }:
        raise ValueError("parent partial scanner-input record counts changed")
    blrx_timestamp_sha256 = hashlib.sha256(
        ("\n".join(blrx_timestamps) + "\n").encode("utf-8")
    ).hexdigest()
    if (
        len(blrx_timestamps) != 177
        or blrx_timestamps[0] != "2025-05-30T11:02:00+00:00"
        or blrx_timestamps[-1] != "2025-05-30T13:58:00+00:00"
        or blrx_timestamp_sha256 != PARENT_BLRX_RAW_TIMESTAMP_SHA256
    ):
        raise ValueError("parent BLRX raw timestamp evidence changed")

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
    downstream_preflight = build_downstream_identity_preflight_receipt(source_root)
    if (
        downstream_preflight.get("candidate_count") != PARENT_CANDIDATE_COUNT
        or downstream_preflight.get("float_record_count") != PARENT_CANDIDATE_COUNT
        or downstream_preflight.get("source_float_root_content_sha256")
        != PARENT_FLOAT_ROOT_CONTENT_SHA256
    ):
        raise ValueError("parent downstream float preflight changed")

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
            "upstream_progress_zip_sha256": PARENT_UPSTREAM_PROGRESS_ZIP_SHA256,
        },
        "source_commitment": {
            "tree_content_sha256": PARENT_SOURCE_TREE_CONTENT_SHA256,
            "file_count": PARENT_SOURCE_FILE_COUNT,
            "directory_count": PARENT_SOURCE_DIRECTORY_COUNT,
            "retained_file_bytes": PARENT_SOURCE_RETAINED_BYTES,
            "identity_root_content_sha256": PARENT_IDENTITY_ROOT_CONTENT_SHA256,
            "market_root_content_sha256": PARENT_MARKET_ROOT_CONTENT_SHA256,
            "float_root_content_sha256": PARENT_FLOAT_ROOT_CONTENT_SHA256,
            "news_root_content_sha256": PARENT_NEWS_ROOT_CONTENT_SHA256,
            "partial_scanner_file_sha256": PARENT_PARTIAL_SCANNER_FILE_SHA256,
            "partial_scanner_file_size": PARENT_PARTIAL_SCANNER_FILE_SIZE,
        },
        "recovered_source_commitment": {
            "tree_content_sha256": RECOVERED_SOURCE_TREE_CONTENT_SHA256,
            "file_count": RECOVERED_SOURCE_FILE_COUNT,
            "directory_count": RECOVERED_SOURCE_DIRECTORY_COUNT,
            "retained_file_bytes": RECOVERED_SOURCE_RETAINED_BYTES,
        },
        "partial_scanner_evidence": {
            "trading_date": EXPECTED_DATES[0],
            "first_candidate_symbol": "BLRX",
            "raw_timestamp_count": len(blrx_timestamps),
            "raw_timestamps_sha256": blrx_timestamp_sha256,
            "raw_first_timestamp": blrx_timestamps[0],
            "raw_last_timestamp": blrx_timestamps[-1],
            "record_counts": partial_counts,
            "manifest_completed": False,
        },
        "dates": list(EXPECTED_DATES),
        "candidate_counts": counts,
        "candidate_count": sum(counts.values()),
        "identity_kind_counts": identity_kind_counts,
        "downstream_identity_preflight": downstream_preflight,
        "request_budget_seed": PARENT_REQUEST_BUDGET,
        "causal_boundary": {
            "normalized_parent_source_validated_exactly": True,
            "partial_scanner_input_removed_before_reacquisition": True,
            "parent_provider_requests_repeated": False,
            "raw_provider_http_responses_present": False,
            "news_stage_reused_complete": True,
            "canonical_scanner_or_runtime_outputs_present": False,
            "float_stage_reused_complete": True,
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
    partial_root = source_target / "causal-scanner-source-inputs-v0.2"
    shutil.rmtree(partial_root)
    recovered = _source_tree_commitment(source_target)
    expected_recovered = receipt["recovered_source_commitment"]
    if not isinstance(expected_recovered, Mapping) or any(
        recovered.get(key) != expected_recovered.get(key)
        for key in (
            "tree_content_sha256",
            "file_count",
            "directory_count",
            "retained_file_bytes",
        )
    ):
        raise ValueError("recovered source differs after partial scanner cleanup")
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
