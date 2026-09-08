"""Provider-free composition of complete, identity-preserving exit sources.

An execution tape is immutable evidence for the frozen fill simulator, not a
strategy observation stream. Conditional windows stay bound to one original
opportunity; this module does not activate historical trading or account replay.
"""
from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile

from momentumbot.research import sealed_historical_management_exit_acquisition_v01 as capture
from momentumbot.research.sealed_historical_execution_quote_v01 import (
    canonical_fingerprint, file_sha, frozen, require_exact, seal,
)

quote = capture.quote
runner = quote.runner
projection = runner.projection
adapter = runner.feedback.adapter
availability = quote.availability
CONTRACT_ID = "sealed-historical-management-exit-inputs-v0.1"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
SNAPSHOT_PATH = f"research/runtime/{CONTRACT_ID}"
BUNDLE_PATH = f"artifacts/{CONTRACT_ID}"
MODULE_PATH = "src/momentumbot/research/sealed_historical_management_exit_inputs_v01.py"
SCRIPT_PATH = "scripts/build_sealed_historical_management_exit_inputs_v01.py"
CHECKER_PATH = "scripts/verify_sealed_historical_management_exit_inputs_v01.py"
TEST_PATH = "tests/test_sealed_historical_management_exit_inputs_v01.py"
WORKFLOW_PATH = ".github/workflows/sealed-historical-management-exit-inputs-v01.yml"
PARENT_COMMIT = "c0ccf773fcc49091682f600c07d991fdd26ab6a8"
PARENT_TREE = "de777b3271e0697a99b80db96fea2f5f58c96178"
CAPTURE_AUDIT = "research/data-audits/sealed-historical-management-exit-acquisition-v0.1-independent-verification-34172486163.json"
CAPTURE_REPORT = "research/data-audits/sealed-historical-management-exit-acquisition-v0.1-report-34172486163.json"
PARENT_PINS = {'research/data-audits/sealed-historical-management-exit-acquisition-v0.1-independent-verification-34172486163.json': '3d0aea8e76e65eab40df8f309f33153ee80c05e8dc7c076366bc25d31ae9bb33',
 'research/data-audits/sealed-historical-management-exit-acquisition-v0.1-report-34172486163.json': '2765deba3a5559c3ddf75caf83adfc680d720dbfa1c8292ee310cc5be1a89117',
 'research/data-audits/sealed-historical-management-exit-quote-v0.1-xage-reuse.json': '799d8664916eb89f713dec276134400e87434251ff97ea5c0b0a29219983e75b',
 'research/runtime/sealed-historical-management-projection-v0.1/projection-input-requirements.json': '8b89b1ffd05de277bcff906140b5aeb142a823cce99260d9c967a8d1dc9e931f',
 'research/runtime/sealed-historical-management-runner-v0.1/exit-input-request-plan.json': '562ed42e20c7021eecf384e3a22aed5f5ce25ae15926dd93072a0313d0e6f461',
 'research/strategy/sealed-historical-management-exit-acquisition-v0.1-execution.json': '60bbd95d1017a3e0e2b3c40060e988f4a457d81b0280b4065c9712a03a1c54e0',
 'research/strategy/sealed-historical-management-exit-acquisition-v0.1.json': '147afc1aa99e33397c1d7f25d6bf17a443c5468d44f820edd40c0d64db989901',
 'scripts/run_offline_python_v13.py': 'fd28ca7e4a27832721a890a1a41af36863a7f13568ca9e85e17c2d5f35e0627d',
 'src/momentumbot/research/sealed_historical_management_exit_acquisition_v01.py': 'b9e7286a793a164f67ee416152327d6cd7fb98ed7cd38293c4a0dd5ed24663f8',
 'src/momentumbot/research/sealed_historical_management_exit_quote_v01.py': '079200a3d0dededb5a3b775f46330ce3558d98fc8c1b67b10b2ce246cf8549f7'}
METADATA_FILES = ("source-verification.json", "exit-input-manifest.json", "opportunity-input-index.json",
                  "readiness-report.json", "freeze-manifest.json")
BOUNDARY = dict(runner.BOUNDARY,
    historical_runtime_activation_ready=False, original_entry_inputs_changed=False,
    all_exit_times_executable_inferred=False, unavailable_entries_rescued=False)
NEXT_GATE = "register_historical_fee_sell_reconciliation_and_authenticated_account_state_integration"


def encoded(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def source_specs(root: Path) -> dict:
    audit = frozen(root / CAPTURE_AUDIT)
    specs = {}
    for kind, item in audit["independent_verification"]["archives"].items():
        specs["exit_" + kind] = {"artifact_id": item["artifact_id"], "bytes": item["bytes"],
            "sha256": item["sha256"], "file_count": len(item["files"]), "run_id": audit["workflow_run_id"]}
    for kind, item in frozen(root / quote.REUSE_PATH)["archives"].items():
        specs["entry_" + kind] = item
    return specs


def recipes(root: Path) -> list[dict]:
    """Only frozen identities/receipts determine the 82 copies, never outcomes."""
    plan = frozen(root / quote.EXIT_PLAN_PATH)
    report = frozen(root / CAPTURE_REPORT)
    reuse = frozen(root / quote.REUSE_PATH)
    specs = source_specs(root)
    inventory = frozen(root / CAPTURE_AUDIT)["result_inventory"]["files"]
    by_sha = {}
    for index, (request, row) in enumerate(zip(plan["new_requests"], report["requests"], strict=True)):
        sha = canonical_fingerprint(request)
        if row["status"] != "complete" or row["request_content_sha256"] != sha or row["exit_request_index"] != index:
            raise ValueError("complete unchanged exit capture required")
        receipt_path = f"receipts/request-{index:03d}.json"
        by_sha[sha] = ("exit_result", index, request, row["tape"], receipt_path,
            inventory[receipt_path]["sha256"])
    if len(by_sha) != 80:
        raise ValueError("exact 80 new requests required")
    for source in reuse["sources"]:
        request, evidence = source["request"], source["source_evidence"]
        sha = canonical_fingerprint(request)
        if sha in by_sha:
            raise ValueError("reused request collides with new capture")
        by_sha[sha] = ("entry_result", source["original_request_ordinal"], request, evidence["tape"],
            evidence["receipt_path"], evidence["receipt_file_sha256"])
    result = []
    for group in plan["groups"]:
        for request in group["requests"]:
            sha = canonical_fingerprint(request)
            key, index, exact, tape, receipt_path, receipt_sha = by_sha.pop(sha)
            require_exact(request, exact, "original source request")
            required_start = group["required_quote_start_ns"] if request["schema"] == "mbp-1" else request["start_ns"]
            if not request["start_ns"] <= required_start < group["required_end_ns"] <= request["end_ns"]:
                raise ValueError("source does not contain common exit interval")
            result.append({"resource_id": group["group_id"] + ":" + request["schema"],
                "group_id": group["group_id"], "request": request, "request_content_sha256": sha,
                "source_key": key, "source_artifact_id": specs[key]["artifact_id"], "source_zip_sha256": specs[key]["sha256"],
                "source_request_ordinal": index, "source_tape": tape,
                "source_receipt_path": receipt_path, "source_receipt_file_sha256": receipt_sha,
                "path": f"tapes/{key}-request-{index:03d}.jsonl.gz",
                "required_start_ns": required_start, "required_end_ns": group["required_end_ns"],
                "source_record_ordinals": "unchanged_complete_original_tape_from_zero",
                "quote_source_request_identity": "unchanged_original_request_fingerprint"})
    if by_sha or len(result) != 82 or len({r["path"] for r in result}) != 82:
        raise ValueError("exact 82-source composition required")
    return result


def expected_contract(root: Path) -> dict:
    return seal({"schema_version": 1, "contract_id": CONTRACT_ID,
        "artifact_type": "registered_provider_free_complete_exit_source_composition",
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE, "frozen_parent_file_sha256": PARENT_PINS,
        "hypothesis": "verified_80_captured_sources_and_original_XAGE_pair_supply_all_41_registered_common_exit_pairs",
        "source_artifacts": source_specs(root), "recipe_content_sha256": canonical_fingerprint(recipes(root)),
        "composition": "byte_identical_full_original_gzip_tapes_no_clipping_recompression_sorting_or_renumbering",
        "output_write": "exclusive_single_write_flush_fsync_then_reopen_and_verify_every_final_tape",
        "reader": "external_freeze_and_original_window_pins_with_conditional_exit_envelope_checks",
        "execution_payload": "stable_full_group_tape_hash_across_sell_attempts_never_a_strategy_observation_stream",
        "common_source_pairs": 41, "source_tapes": 82, "new_sources": 80, "reused_sources": 2,
        "original_opportunities": 109, "available_entries": 86, "unavailable_entries": 23,
        "implementation_file_sha256": {p: file_sha(root / p) for p in (MODULE_PATH, SCRIPT_PATH, CHECKER_PATH, TEST_PATH, WORKFLOW_PATH)},
        "next_gate": NEXT_GATE, **BOUNDARY})


def validate_registration(root: Path) -> dict:
    for name, expected in PARENT_PINS.items():
        availability._regular(root / name)
        if file_sha(root / name) != expected:
            raise ValueError("exit composition parent differs: " + name)
    capture.validate_inputs(root)
    require_exact(frozen(root / CONTRACT_PATH), expected_contract(root), "exit composition registration")
    return seal({"verification_passed": True, "contract_content_sha256": expected_contract(root)["content_sha256"],
        **BOUNDARY})


def verify_sources(root: Path, paths: dict[str, Path], progress=None) -> dict:
    specs = source_specs(root)
    if set(paths) != set(specs):
        raise ValueError("exact four source ZIPs required")
    for key, path in paths.items():
        availability._regular(path)
        if path.stat().st_size != specs[key]["bytes"] or file_sha(path) != specs[key]["sha256"]:
            raise ValueError("exact source ZIP differs: " + key)
    audit = frozen(root / CAPTURE_AUDIT)
    with tempfile.TemporaryDirectory(prefix="exit-source-verification-") as directory:
        workspace = Path(directory)
        for kind in ("result", "consumption"):
            key = "exit_" + kind
            capture.extract_exact_zip(paths[key], workspace / key, specs[key]["sha256"])
            require_exact(availability._inventory(workspace / key),
                audit["independent_verification"]["archives"][kind]["files"], "complete exit archive members")
        result, consumption = workspace / "exit_result", workspace / "exit_consumption"
        shared = set(availability._inventory(result)) & set(availability._inventory(consumption))
        for name in shared:
            if (result / name).read_bytes() != (consumption / name).read_bytes():
                raise ValueError("exit consumption/result shared evidence differs")
        primary = capture.verify_capture(result, root, require_complete=True)
        require_exact(primary, audit["primary_verification"], "full exit capture reconstruction")
        if progress:
            progress({"verified_source": "exit_capture", "tapes": 80})
        reuse = quote.reuse_receipt(root, result_zip=paths["entry_result"], consumption_zip=paths["entry_consumption"],
            workspace=workspace / "entry")
        require_exact(reuse, frozen(root / quote.REUSE_PATH), "complete original XAGE reuse reconstruction")
        if progress:
            progress({"verified_source": "original_XAGE_and_entry_capture_chain", "reused_tapes": 2})
    return source_proof(root)


def source_proof(root: Path) -> dict:
    audit = frozen(root / CAPTURE_AUDIT)
    return seal({"contract_id": CONTRACT_ID, "all_four_source_archives_verified": True,
        "source_artifacts": source_specs(root), "direct_archive_file_count": 352,
        "exit_capture_verification_content_sha256": audit["primary_verification"]["content_sha256"],
        "exit_capture_audit_content_sha256": audit["content_sha256"],
        "XAGE_reuse_verification_content_sha256": frozen(root / quote.REUSE_PATH)["content_sha256"],
        "original_source_normalization_verified_before_copy": True, "source_captures_modified": False, **BOUNDARY})


def write_once(path: Path, raw: bytes) -> None:
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError("symbolic link output rejected")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        if handle.write(raw) != len(raw):
            raise OSError("short exit source write")
        handle.flush()
        os.fsync(handle.fileno())


def write_json(path: Path, value: dict) -> None:
    write_once(path, (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode())


def safe_tape_path(output: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if (str(relative) != name or relative.is_absolute() or ".." in relative.parts or "\\" in name
            or len(relative.parts) != 2 or relative.parts[0] != "tapes" or not name.endswith(".jsonl.gz")):
        raise ValueError("unsafe exit tape path")
    path = output / name
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError("symbolic link tape rejected")
    return path


def copy_source(output: Path, recipe: dict, archive: zipfile.ZipFile) -> None:
    raw = archive.read(recipe["source_tape"]["path"])
    tape = recipe["source_tape"]
    if len(raw) != tape["file_bytes"] or hashlib.sha256(raw).hexdigest() != tape["file_sha256"]:
        raise ValueError("source tape changed before copy")
    write_once(safe_tape_path(output, recipe["path"]), raw)


def digest_records(output: Path, recipe: dict, payload_digest) -> None:
    """Check complete final gzip/CRC and feed the canonical record-list encoding."""
    path = safe_tape_path(output, recipe["path"])
    availability._regular(path)
    tape = recipe["source_tape"]
    if path.stat().st_size != tape["file_bytes"] or file_sha(path) != tape["file_sha256"]:
        raise ValueError("final tape differs from original source receipt")
    logical, count, length = hashlib.sha256(), 0, 0
    payload_digest.update(b"[")
    with gzip.open(path, "rb") as handle:
        for raw in handle:
            if not raw.endswith(b"\n") or len(raw) > 1000:
                raise ValueError("canonical source row boundary differs")
            logical.update(raw)
            length += len(raw)
            if count:
                payload_digest.update(b",")
            payload_digest.update(raw[:-1])
            count += 1
    payload_digest.update(b"]")
    if not count or (count, length, logical.hexdigest()) != (tape["row_count"], tape["normalized_bytes"], tape["normalized_sha256"]):
        raise ValueError("complete normalized source tape differs")


def pair_fingerprint(output: Path, pair: list[dict]) -> str:
    """Exactly canonical_fingerprint of the frozen four-key fill-feedback tape."""
    if [r["request"]["schema"] for r in pair] != ["mbp-1", "status"]:
        raise ValueError("ordered quote/status pair required")
    digest = hashlib.sha256(b'{"quote_records":')
    digest_records(output, pair[0], digest)
    digest.update(b',"quote_request":' + encoded(pair[0]["request"]) + b',"status_records":')
    digest_records(output, pair[1], digest)
    digest.update(b',"status_request":' + encoded(pair[1]["request"]) + b"}")
    return digest.hexdigest()


def documents(root: Path, output: Path) -> dict[str, dict]:
    resources = recipes(root)
    plan = frozen(root / quote.EXIT_PLAN_PATH)
    groups = []
    for group in plan["groups"]:
        pair = [r for r in resources if r["group_id"] == group["group_id"]]
        groups.append({"original_group": group, "resource_ids": [r["resource_id"] for r in pair],
            "execution_tape_content_sha256": pair_fingerprint(output, pair), "complete_source_pair_verified": True})
    index = seal({"contract_id": CONTRACT_ID, "opportunities": plan["opportunities"],
        "opportunity_windows": frozen(root / runner.INPUT_REQUIREMENTS)["opportunity_windows"], **BOUNDARY})
    counts = {schema: sum(r["source_tape"]["row_count"] for r in resources if r["request"]["schema"] == schema)
              for schema in ("mbp-1", "status")}
    return {
        "source-verification.json": source_proof(root),
        "exit-input-manifest.json": seal({"contract_id": CONTRACT_ID, "resources": resources, "groups": groups,
            "original_exit_plan_content_sha256": plan["content_sha256"], **BOUNDARY}),
        "opportunity-input-index.json": index,
        "readiness-report.json": seal({"contract_id": CONTRACT_ID, "common_source_pairs": len(groups),
            "source_tapes": len(resources), "schema_row_counts": counts, "record_count": sum(counts.values()),
            "normalized_bytes": sum(r["source_tape"]["normalized_bytes"] for r in resources),
            "original_opportunity_count": len(index["opportunities"]), "available_entry_count": 86,
            "unavailable_entry_count": 23, "exit_sources_complete": True,
            "runtime_dependencies": {**runner.DEPENDENCIES, "exact_exit_tapes_verified": True,
                "existing_common_source_reuse_bytes_verified": True},
            "next_gate": NEXT_GATE, **BOUNDARY}),
    }


def _output(root: Path, output: Path) -> None:
    if output.is_symlink() or any(p.is_symlink() for p in output.parents):
        raise ValueError("symbolic link output rejected")
    if output.resolve().is_relative_to(root.resolve()) and output.resolve() != (root / BUNDLE_PATH).resolve():
        raise ValueError("cannot overwrite frozen repository inputs")


def check_bundle_files(root: Path, output: Path) -> dict:
    _output(root, output)
    manifest = frozen(output / "freeze-manifest.json")
    actual = availability._inventory(output)
    expected_docs = documents(root, output)
    expected_files = set(METADATA_FILES) | {r["path"] for r in expected_docs["exit-input-manifest.json"]["resources"]}
    if set(actual) != expected_files:
        raise ValueError("complete exit bundle file population differs")
    for name, expected in expected_docs.items():
        require_exact(frozen(output / name), expected, "reconstructed exit document " + name)
    expected_manifest = seal({"contract_id": CONTRACT_ID,
        "contract_content_sha256": frozen(root / CONTRACT_PATH)["content_sha256"],
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "document_content_sha256": {n: d["content_sha256"] for n, d in expected_docs.items()},
        "file_inventory": {n: v for n, v in actual.items() if n != "freeze-manifest.json"},
        "next_gate": NEXT_GATE, **BOUNDARY})
    require_exact(manifest, expected_manifest, "complete exit bundle freeze")
    return seal({"verification_passed": True, "freeze_manifest_content_sha256": manifest["content_sha256"],
        "file_inventory": actual, "readiness": expected_docs["readiness-report.json"], **BOUNDARY})


def write_bundle(root: Path, output: Path, paths: dict[str, Path], progress=None) -> dict:
    _output(root, output)
    if output.exists():
        raise FileExistsError("exit composition is write-once")
    validate_registration(root)
    verify_sources(root, paths, progress)
    output.mkdir(parents=True, exist_ok=False)
    completed = 0
    try:
        with ExitStack() as stack:
            archives = {key: stack.enter_context(zipfile.ZipFile(path)) for key, path in paths.items()}
            for recipe in recipes(root):
                copy_source(output, recipe, archives[recipe["source_key"]])
                completed += 1
        for key, spec in source_specs(root).items():
            if file_sha(paths[key]) != spec["sha256"]:
                raise ValueError("source archive changed during composition")
        payloads = documents(root, output)
        for name, payload in payloads.items():
            write_json(output / name, payload)
        manifest = seal({"contract_id": CONTRACT_ID,
            "contract_content_sha256": frozen(root / CONTRACT_PATH)["content_sha256"],
            "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
            "document_content_sha256": {n: p["content_sha256"] for n, p in payloads.items()},
            "file_inventory": availability._inventory(output), "next_gate": NEXT_GATE, **BOUNDARY})
        write_json(output / "freeze-manifest.json", manifest)
        return check_bundle_files(root, output)
    except Exception as exc:
        write_json(output / "composition-failure.json", seal({"contract_id": CONTRACT_ID,
            "completed_resources": completed, "exception_class": type(exc).__name__,
            "sanitized_error": "offline exit composition failed; partial evidence retained",
            **BOUNDARY, "exit_input_source_bundle_verified": False}))
        raise ValueError("offline exit composition failed; partial evidence retained") from None


def freeze_metadata(root: Path, output: Path) -> None:
    check_bundle_files(root, output)
    destination = root / SNAPSHOT_PATH
    if destination.exists() or destination.is_symlink() or any(p.is_symlink() for p in destination.parents):
        raise FileExistsError("committed exit metadata is write-once")
    destination.mkdir(parents=True, exist_ok=False)
    for name in METADATA_FILES:
        write_once(destination / name, (output / name).read_bytes())


def check_committed_metadata(root: Path, output: Path) -> dict:
    snapshot = root / SNAPSHOT_PATH
    if set(availability._inventory(snapshot)) != set(METADATA_FILES):
        raise ValueError("committed exit metadata population differs")
    for name in METADATA_FILES:
        availability._regular(output / name)
        if (snapshot / name).read_bytes() != (output / name).read_bytes():
            raise ValueError("exit bundle differs from committed freeze: " + name)
    return check_bundle_files(root, output)


def verify_bundle(root: Path, output: Path, paths: dict[str, Path], progress=None) -> dict:
    validate_registration(root)
    verify_sources(root, paths, progress)
    return check_committed_metadata(root, output)


class ExitInputBundle:
    """Pinned source access for execution evidence, with no order/runtime authority."""
    def __init__(self, root: Path, output: Path, *, expected_manifest_content_sha256: str):
        if not isinstance(expected_manifest_content_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_manifest_content_sha256):
            raise ValueError("external exact exit freeze pin required")
        validate_registration(root)
        checked = check_committed_metadata(root, output)
        if checked["freeze_manifest_content_sha256"] != expected_manifest_content_sha256:
            raise ValueError("exit source bundle differs from caller's frozen parent")
        self.output = output
        index = frozen(output / "opportunity-input-index.json")
        manifest = frozen(output / "exit-input-manifest.json")
        self._opportunities = {r["opportunity_id"]: r for r in index["opportunities"]}
        self._windows = {r["opportunity"]["opportunity_id"]: r for r in index["opportunity_windows"]}
        self._groups = {g["original_group"]["group_id"]: g for g in manifest["groups"]}
        self._resources = {r["resource_id"]: r for r in manifest["resources"]}

    def opportunity(self, opportunity_id: str) -> dict:
        if opportunity_id not in self._opportunities:
            raise ValueError("unregistered exit opportunity")
        return deepcopy(self._opportunities[opportunity_id])

    def _bound(self, opportunity_id: str, decision_ns: int, expected_window_content_sha256: str) -> tuple[dict, dict]:
        op = self.opportunity(opportunity_id)
        if op["window_content_sha256"] != expected_window_content_sha256:
            raise ValueError("original opportunity window pin differs")
        if op["entry_input_status"] != "available" or op["group_id"] is None:
            raise ValueError("unavailable entry cannot be rescued by exit data")
        window = self._windows[opportunity_id]
        if canonical_fingerprint(window) != expected_window_content_sha256:
            raise ValueError("bound original window changed")
        envelope = projection.conditional_exit_envelope(window, decision_ns)
        group = self._groups[op["group_id"]]
        member = next(m for m in group["original_group"]["members"] if m["opportunity_id"] == opportunity_id)
        if (not envelope["fits_frozen_envelope"] or not member["first_possible_exit_decision_ns"] <= decision_ns
                <= member["last_covered_exit_decision_ns"]):
            raise ValueError("conditional exit lies outside original opportunity coverage")
        return deepcopy(window), deepcopy(group)

    def execution_tape(self, opportunity_id: str, decision_ns: int, *, expected_window_content_sha256: str) -> tuple[dict, str]:
        """Stable full source pair for the frozen execution engine, not observations.

        Future rows remain sealed execution evidence. A future registered runner
        must schedule confirmed feedback causally; access does not create a fill.
        """
        _, group = self._bound(opportunity_id, decision_ns, expected_window_content_sha256)
        payload = {}
        for prefix, rid in zip(("quote", "status"), group["resource_ids"], strict=True):
            recipe = self._resources[rid]
            path = safe_tape_path(self.output, recipe["path"])
            availability._regular(path)
            records, info = capture.tape_records(path)
            require_exact({"path": recipe["source_tape"]["path"], **info}, recipe["source_tape"], "source at reader access")
            payload[prefix + "_request"] = deepcopy(recipe["request"])
            payload[prefix + "_records"] = records
        expected = group["execution_tape_content_sha256"]
        if canonical_fingerprint(payload) != expected:
            raise ValueError("complete execution tape differs from pinned pair")
        return payload, expected

    def capture_window(self, opportunity_id: str, decision_ns: int, *, expected_window_content_sha256: str) -> dict:
        """Offline conditional execution window, including its bounded fill tail."""
        window, _ = self._bound(opportunity_id, decision_ns, expected_window_content_sha256)
        tape, _ = self.execution_tape(opportunity_id, decision_ns, expected_window_content_sha256=expected_window_content_sha256)
        identity = adapter.WindowIdentity(opportunity_id, window["opportunity"]["trading_date"],
            window["opportunity"]["symbol"], decision_ns)
        return adapter.capture_window(identity, **tape)
