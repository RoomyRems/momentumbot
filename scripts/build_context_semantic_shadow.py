from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import datetime
from pathlib import Path

from momentumbot.identity_resolved_universe import json_fingerprint
from momentumbot.research.context_assessment import (
    CONTRACT_ID as CONTEXT_ASSESSMENT_CONTRACT_ID,
    validate_context_decision_snapshot,
)
from momentumbot.research.context_heldout_panel import REGISTERED_DATES
from momentumbot.research.context_runtime import (
    SNAPSHOT_RUNTIME_ARTIFACT_ID,
    validate_record_date_payload,
    write_json,
)
from momentumbot.research.context_semantic_shadow import (
    ARTIFACT_ID,
    FROZEN_PARENT_RUNTIME_CONTENT_SHA256,
    FROZEN_PARENT_ZIP_SHA256,
    FROZEN_SNAPSHOT_RUNTIME_CONTENT_SHA256,
    build_compiled_shadow_assessment,
    build_semantic_date_payload,
    build_semantic_root_manifest,
    compiled_rubric_content_sha256,
    load_compiled_rubric,
)


TOP_MANIFEST_PATH = "context-heldout-runtime-manifest.json"
SNAPSHOT_ROOT = (
    "deterministic-context-runtime-v0.1/"
    "ross-context-heldout-snapshot-runtime-v0.1"
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_from_zip(archive: zipfile.ZipFile, path: str) -> dict[str, object]:
    payload = json.loads(archive.read(path))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _validate_frozen_parent(archive: zipfile.ZipFile) -> dict[str, object]:
    top = _json_from_zip(archive, TOP_MANIFEST_PATH)
    claimed = top.get("content_sha256")
    projection = {key: value for key, value in top.items() if key != "content_sha256"}
    if claimed != json_fingerprint(projection):
        raise ValueError("frozen parent runtime manifest fingerprint mismatch")
    if claimed != FROZEN_PARENT_RUNTIME_CONTENT_SHA256:
        raise ValueError("runtime ZIP differs from the frozen parent")
    boundary = top.get("causal_boundary")
    if not isinstance(boundary, dict):
        raise ValueError("frozen parent lacks causal boundary")
    for field in (
        "uses_raw_transcripts",
        "uses_ross_actions",
        "uses_retrospective_labels",
        "uses_later_price_outcomes",
        "semantic_ai_included",
    ):
        if boundary.get(field) is not False:
            raise ValueError(f"frozen parent violates {field}")

    snapshot_manifest = _json_from_zip(archive, f"{SNAPSHOT_ROOT}/manifest.json")
    claimed = snapshot_manifest.get("content_sha256")
    projection = {
        key: value
        for key, value in snapshot_manifest.items()
        if key != "content_sha256"
    }
    if claimed != json_fingerprint(projection):
        raise ValueError("snapshot runtime manifest fingerprint mismatch")
    if claimed != FROZEN_SNAPSHOT_RUNTIME_CONTENT_SHA256:
        raise ValueError("snapshot runtime differs from the frozen parent")
    if snapshot_manifest.get("dates") != list(REGISTERED_DATES):
        raise ValueError("snapshot runtime dates differ from registration")
    if snapshot_manifest.get("record_count") != 314:
        raise ValueError("snapshot runtime record count changed")
    return snapshot_manifest


def _source_hash() -> str:
    root = Path(__file__).resolve().parents[1]
    sources = {
        "module_sha256": _sha256_file(
            root / "src" / "momentumbot" / "research" / "context_semantic_shadow.py"
        ),
        "script_sha256": _sha256_file(Path(__file__).resolve()),
    }
    return json_fingerprint(sources)


def _parse_generated_at(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("generated-at must be timezone-aware")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Freeze the label-blind compiled semantic context shadow."
    )
    parser.add_argument("--source-zip", type=Path, required=True)
    parser.add_argument("--rubric", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generated-at", required=True)
    parser.add_argument("--label-blind-run-id", required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"output already exists: {args.output}")
    generated_at = _parse_generated_at(args.generated_at)
    label_blind_run_id = args.label_blind_run_id.strip()
    if not label_blind_run_id:
        raise ValueError("label-blind-run-id is required")
    if _sha256_file(args.source_zip) != FROZEN_PARENT_ZIP_SHA256:
        raise ValueError("source ZIP digest differs from the frozen parent")
    rubric = load_compiled_rubric(args.rubric)
    rubric_hash = compiled_rubric_content_sha256(rubric)

    date_payloads: dict[str, dict[str, object]] = {}
    with zipfile.ZipFile(args.source_zip) as archive:
        if archive.testzip() is not None:
            raise ValueError("source ZIP integrity test failed")
        snapshot_manifest = _validate_frozen_parent(archive)
        date_hashes = snapshot_manifest.get("date_content_sha256s")
        if not isinstance(date_hashes, dict):
            raise ValueError("snapshot runtime lacks date hashes")
        for trading_date in REGISTERED_DATES:
            source = _json_from_zip(
                archive, f"{SNAPSHOT_ROOT}/dates/{trading_date}.json"
            )
            validate_record_date_payload(
                source,
                artifact_id=SNAPSHOT_RUNTIME_ARTIFACT_ID,
                contract_id=CONTEXT_ASSESSMENT_CONTRACT_ID,
            )
            if source.get("content_sha256") != date_hashes.get(trading_date):
                raise ValueError("snapshot date/root fingerprint mismatch")
            snapshots = source.get("records")
            if not isinstance(snapshots, list):
                raise ValueError("snapshot date lacks records")
            assessments = []
            for snapshot in snapshots:
                if not isinstance(snapshot, dict):
                    raise ValueError("snapshot record must be an object")
                validate_context_decision_snapshot(snapshot)
                assessments.append(
                    build_compiled_shadow_assessment(
                        snapshot,
                        rubric_content_sha256=rubric_hash,
                        generated_at=generated_at,
                        label_blind_run_id=label_blind_run_id,
                    )
                )
            date_payloads[trading_date] = build_semantic_date_payload(
                trading_date=trading_date,
                source_snapshot_date_content_sha256=str(source["content_sha256"]),
                rubric_content_sha256=rubric_hash,
                assessments=assessments,
            )

    manifest = build_semantic_root_manifest(
        rubric_content_sha256=rubric_hash,
        generator_source_sha256=_source_hash(),
        generated_at=generated_at,
        label_blind_run_id=label_blind_run_id,
        date_payloads=date_payloads,
    )
    args.output.mkdir(parents=True)
    for trading_date, payload in date_payloads.items():
        write_json(args.output / "dates" / f"{trading_date}.json", payload)
    write_json(args.output / "manifest.json", manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
