from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path
from typing import Mapping

from momentumbot.identity_resolved_universe import json_fingerprint
from momentumbot.research.context_assessment import (
    SEMANTIC_AXES,
    validate_context_decision_snapshot,
    validate_shadow_context_assessment,
)
from momentumbot.research.context_heldout_comparison import (
    SnapshotKey,
    build_context_heldout_comparison,
    validate_context_heldout_comparison,
)
from momentumbot.research.context_heldout_labels import (
    RUNTIME_CONTENT_SHA256,
    RUNTIME_ZIP_SHA256,
    SEMANTIC_MANIFEST_CONTENT_SHA256,
    SNAPSHOT_RUNTIME_CONTENT_SHA256,
    load_context_heldout_labels,
)
from momentumbot.research.context_heldout_panel import (
    REGISTERED_DATES,
)
from momentumbot.research.context_semantic_shadow import (
    validate_semantic_date_payload,
    validate_semantic_root_manifest,
)


RUNTIME_ARTIFACT_ID = "ross-context-heldout-runtime-v0.1"
SNAPSHOT_ARTIFACT_ID = "ross-context-heldout-snapshot-runtime-v0.1"
SNAPSHOT_ROOT = (
    "deterministic-context-runtime-v0.1/"
    "ross-context-heldout-snapshot-runtime-v0.1"
)


def _json_object(value: bytes | str, field: str) -> dict[str, object]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError(f"{field} must contain a JSON object")
    return payload


def _read_json(path: Path) -> dict[str, object]:
    return _json_object(path.read_text(encoding="utf-8"), str(path))


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_content_hash(
    payload: Mapping[str, object],
    *,
    expected: str | None,
    field: str,
) -> str:
    claimed = payload.get("content_sha256")
    projection = {
        key: value for key, value in payload.items() if key != "content_sha256"
    }
    if not isinstance(claimed, str) or claimed != json_fingerprint(projection):
        raise ValueError(f"{field} content fingerprint mismatch")
    if expected is not None and claimed != expected:
        raise ValueError(f"{field} differs from its frozen parent")
    return claimed


def _validate_runtime_manifest(payload: Mapping[str, object]) -> None:
    if payload.get("artifact_id") != RUNTIME_ARTIFACT_ID:
        raise ValueError("unexpected deterministic runtime artifact")
    _validate_content_hash(
        payload,
        expected=RUNTIME_CONTENT_SHA256,
        field="deterministic runtime manifest",
    )
    if payload.get("dates") != list(REGISTERED_DATES):
        raise ValueError("deterministic runtime dates differ from registration")
    if payload.get("policy_promotion_eligible") is not False:
        raise ValueError("deterministic runtime overclaims policy eligibility")
    boundary = _mapping(payload.get("causal_boundary"), "causal_boundary")
    if boundary.get("all_market_candidates_retained") is not True:
        raise ValueError("deterministic runtime dropped market candidates")
    if boundary.get("semantic_ai_included") is not False:
        raise ValueError("deterministic runtime unexpectedly contains semantic AI")
    if boundary.get("runtime_strategy_effect") != "none" or any(
        boundary.get(field) is not False
        for field in (
            "uses_later_price_outcomes",
            "uses_raw_transcripts",
            "uses_retrospective_labels",
            "uses_ross_actions",
        )
    ):
        raise ValueError("deterministic runtime violates the causal boundary")


def _validate_snapshot_manifest(payload: Mapping[str, object]) -> Mapping[str, object]:
    if payload.get("artifact_id") != SNAPSHOT_ARTIFACT_ID:
        raise ValueError("unexpected deterministic snapshot artifact")
    _validate_content_hash(
        payload,
        expected=SNAPSHOT_RUNTIME_CONTENT_SHA256,
        field="deterministic snapshot manifest",
    )
    if payload.get("dates") != list(REGISTERED_DATES):
        raise ValueError("snapshot dates differ from registration")
    if payload.get("record_count") != 314 or payload.get("unavailable_count") != 0:
        raise ValueError("snapshot manifest counts changed")
    if payload.get("policy_promotion_eligible") is not False:
        raise ValueError("snapshot manifest overclaims policy eligibility")
    hashes = _mapping(payload.get("date_content_sha256s"), "date hashes")
    if set(hashes) != set(REGISTERED_DATES):
        raise ValueError("snapshot manifest date hashes are incomplete")
    return hashes


def load_frozen_deterministic_snapshots(
    runtime_zip: Path,
    *,
    labels: Mapping[str, object],
) -> tuple[dict[SnapshotKey, dict[str, object]], dict[str, str]]:
    if _file_sha256(runtime_zip) != RUNTIME_ZIP_SHA256:
        raise ValueError("deterministic runtime ZIP differs from the frozen labels")
    date_results = _mapping(labels.get("date_results"), "date_results")
    snapshots: dict[SnapshotKey, dict[str, object]] = {}
    date_hashes: dict[str, str] = {}
    with zipfile.ZipFile(runtime_zip) as archive:
        runtime_manifest = _json_object(
            archive.read("context-heldout-runtime-manifest.json"),
            "context-heldout-runtime-manifest.json",
        )
        _validate_runtime_manifest(runtime_manifest)
        snapshot_manifest = _json_object(
            archive.read(f"{SNAPSHOT_ROOT}/manifest.json"),
            "deterministic snapshot manifest",
        )
        expected_date_hashes = _validate_snapshot_manifest(snapshot_manifest)

        for trading_date in REGISTERED_DATES:
            payload = _json_object(
                archive.read(f"{SNAPSHOT_ROOT}/dates/{trading_date}.json"),
                f"snapshot date {trading_date}",
            )
            if payload.get("artifact_id") != SNAPSHOT_ARTIFACT_ID:
                raise ValueError("unexpected deterministic snapshot date artifact")
            if payload.get("trading_date") != trading_date:
                raise ValueError("deterministic snapshot date mismatch")
            date_hashes[trading_date] = _validate_content_hash(
                payload,
                expected=str(expected_date_hashes[trading_date]),
                field=f"snapshot date {trading_date}",
            )
            records = payload.get("records")
            if not isinstance(records, list) or payload.get("record_count") != len(
                records
            ):
                raise ValueError("deterministic snapshot date count mismatch")
            unavailable = payload.get("unavailable")
            if unavailable != [] or payload.get("unavailable_count") != 0:
                raise ValueError("unexpected unavailable deterministic snapshot")
            knowledge = _mapping(payload.get("knowledge_policy"), "knowledge_policy")
            if knowledge.get("runtime_strategy_effect") != "none" or any(
                knowledge.get(field) is not False
                for field in (
                    "uses_benchmark_labels",
                    "uses_later_price_outcomes",
                    "uses_raw_transcripts",
                    "uses_retrospective_trade_outcomes",
                    "uses_ross_actions",
                )
            ):
                raise ValueError("snapshot date violates its causal boundary")

            seen_symbols: set[str] = set()
            activation_symbols: set[str] = set()
            for raw in records:
                record = _mapping(raw, "deterministic snapshot")
                validate_context_decision_snapshot(record)
                symbol = str(record["symbol"])
                decision_time = str(record["decision_time"])
                key = (trading_date, symbol, decision_time)
                if key in snapshots:
                    raise ValueError("deterministic snapshot key is duplicated")
                snapshots[key] = dict(record)
                seen_symbols.add(symbol)
                if decision_time == record.get("activation_time"):
                    if record.get("snapshot_reason") != "candidate_activation":
                        raise ValueError("activation snapshot has the wrong reason")
                    if symbol in activation_symbols:
                        raise ValueError("candidate has repeated activation snapshots")
                    activation_symbols.add(symbol)
            date_result = _mapping(date_results.get(trading_date), trading_date)
            expected_symbols = set(date_result.get("candidate_symbols", []))
            if seen_symbols != expected_symbols or activation_symbols != expected_symbols:
                raise ValueError("snapshot candidates differ from frozen labels")
    if len(snapshots) != 314:
        raise ValueError("deterministic snapshot record count changed")
    return snapshots, date_hashes


def _axis_statistics(
    date_payloads: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    states = {axis: Counter() for axis in SEMANTIC_AXES}
    values = {axis: Counter() for axis in SEMANTIC_AXES}
    confidence = {axis: Counter() for axis in SEMANTIC_AXES}
    for payload in date_payloads.values():
        records = payload.get("records")
        assert isinstance(records, list)
        for record in records:
            assert isinstance(record, Mapping)
            axes = _mapping(record.get("axes"), "semantic axes")
            for axis in SEMANTIC_AXES:
                row = _mapping(axes.get(axis), axis)
                states[axis][str(row["state"])] += 1
                if row.get("value") is not None:
                    values[axis][str(row["value"])] += 1
                if row.get("confidence") is not None:
                    confidence[axis][str(row["confidence"])] += 1
    return {
        axis: {
            "states": dict(sorted(states[axis].items())),
            "values": dict(sorted(values[axis].items())),
            "confidence": dict(sorted(confidence[axis].items())),
        }
        for axis in SEMANTIC_AXES
    }


def load_frozen_semantic_records(
    semantic_root: Path,
    *,
    deterministic_snapshots: Mapping[SnapshotKey, Mapping[str, object]],
    deterministic_date_hashes: Mapping[str, str],
) -> dict[SnapshotKey, dict[str, object]]:
    manifest = _read_json(semantic_root / "manifest.json")
    validate_semantic_root_manifest(manifest)
    if manifest.get("content_sha256") != SEMANTIC_MANIFEST_CONTENT_SHA256:
        raise ValueError("semantic manifest differs from frozen labels")
    manifest_date_hashes = _mapping(
        manifest.get("date_content_sha256s"), "semantic date hashes"
    )
    payloads: dict[str, dict[str, object]] = {}
    semantic: dict[SnapshotKey, dict[str, object]] = {}
    for trading_date in REGISTERED_DATES:
        payload = _read_json(semantic_root / "dates" / f"{trading_date}.json")
        validate_semantic_date_payload(payload)
        if payload.get("content_sha256") != manifest_date_hashes.get(trading_date):
            raise ValueError("semantic date differs from root manifest")
        if payload.get("source_snapshot_date_content_sha256") != (
            deterministic_date_hashes[trading_date]
        ):
            raise ValueError("semantic date differs from deterministic snapshot date")
        records = payload.get("records")
        assert isinstance(records, list)
        for raw in records:
            record = _mapping(raw, "semantic record")
            key = (trading_date, str(record["symbol"]), str(record["decision_time"]))
            if key in semantic:
                raise ValueError("semantic record key is duplicated")
            snapshot = deterministic_snapshots.get(key)
            if snapshot is None:
                raise ValueError("semantic record lacks an exact deterministic snapshot")
            validate_shadow_context_assessment(record, snapshot=snapshot)
            semantic[key] = dict(record)
        payloads[trading_date] = payload
    if len(semantic) != 314 or set(semantic) != set(deterministic_snapshots):
        raise ValueError("semantic record set differs from deterministic snapshots")
    if manifest.get("axis_statistics") != _axis_statistics(payloads):
        raise ValueError("semantic root axis statistics do not reproduce")
    return semantic


def build_comparison_from_frozen_artifacts(
    *,
    labels_path: Path,
    runtime_zip: Path,
    semantic_root: Path,
) -> dict[str, object]:
    labels = load_context_heldout_labels(
        labels_path, semantic_root_path=semantic_root
    )
    snapshots, date_hashes = load_frozen_deterministic_snapshots(
        runtime_zip, labels=labels
    )
    semantic = load_frozen_semantic_records(
        semantic_root,
        deterministic_snapshots=snapshots,
        deterministic_date_hashes=date_hashes,
    )
    payload = build_context_heldout_comparison(
        labels=labels,
        deterministic_snapshots=snapshots,
        semantic_records=semantic,
    )
    validate_context_heldout_comparison(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare frozen context snapshots and semantic axes with frozen "
            "account actions descriptively, without fitting or promotion."
        )
    )
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--runtime-zip", type=Path, required=True)
    parser.add_argument("--semantic-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"output already exists: {args.output}")
    payload = build_comparison_from_frozen_artifacts(
        labels_path=args.labels,
        runtime_zip=args.runtime_zip,
        semantic_root=args.semantic_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "content_sha256": payload["content_sha256"],
                "panel_counts": payload["panel_counts"],
                "candidate_acquisition": payload["candidate_acquisition"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
