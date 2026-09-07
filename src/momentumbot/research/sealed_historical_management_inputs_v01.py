"""Materialize exact historical management sources without running a strategy.

Original canonical rows are copied, not translated. Compact segment receipts
map every composed ordinal back to its immutable source artifact and ordinal.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile

import pandas as pd

from momentumbot.research import sealed_historical_management_capture_v01 as capture
from momentumbot.research import sealed_historical_management_reuse_v01 as reuse
from momentumbot.research.sealed_historical_execution_quote_v01 import (
    canonical_fingerprint, file_sha, frozen, require_exact, seal,
)

accounts = reuse.accounts
CONTRACT_ID = "sealed-historical-management-inputs-v0.1"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
SNAPSHOT_PATH = f"research/runtime/{CONTRACT_ID}"
BUNDLE_PATH = f"artifacts/{CONTRACT_ID}"
MODULE_PATH = "src/momentumbot/research/sealed_historical_management_inputs_v01.py"
SCRIPT_PATH = "scripts/build_sealed_historical_management_inputs_v01.py"
WORKFLOW_PATH = ".github/workflows/sealed-historical-management-inputs-v01.yml"
TEST_PATH = "tests/test_sealed_historical_management_inputs_v01.py"
PARENT_COMMIT = "536226a134aa9863130205b954065f24c89ce599"
PARENT_TREE = "f0bc8b58e6c5988849b97717993390b42a1d19ce"
CAPTURE_AUDIT = "research/data-audits/sealed-historical-management-missing-input-v0.1-independent-verification-34142720577.json"
PARENT_PINS = {
    CAPTURE_AUDIT: "37cf0122e67719a4ac4046d1dc2e1c9e8258498b257018d6f8a73ae8d904e91e",
    capture.MODULE_PATH: "cfccb813c042089d9807e1e3fa16710befbb7a4211f6054319b77714dca95a20",
    capture.CONTRACT_PATH: "8834c39bfb0bb4c7194a6abc994102ba17f58bfc52215da10611eef47a2e2099",
    capture.EXECUTION_PATH: "cbfe27d98cb1ef6a506e300755a18d3ef1e725a22243d6d02abcec4fa5162337",
}
METADATA_FILES = ("source-verification.json", "management-input-manifest.json", "opportunity-input-index.json",
                  "readiness-report.json", "freeze-manifest.json")
RESOURCES = ("raw_sip_1m_bars", "sip_transactions")
BOUNDARY = dict(accounts.BOUNDARY)
NEXT_GATE = "register_causal_management_projection_and_executable_exit_dependencies_against_verified_inputs"


def parent_documents(root: Path) -> tuple[dict, dict, dict]:
    return (frozen(root / accounts.OUTPUT_PATH / "management-request-manifest.json"),
            frozen(root / reuse.OUTPUT_PATH / "reuse-coverage.json"), frozen(root / CAPTURE_AUDIT))


def source_specs(root: Path) -> dict:
    audit = frozen(root / CAPTURE_AUDIT)
    sources = {key: reuse.source_spec(root, resource) for key, resource in
               (("original_sip", "sip_transactions"), ("original_bars", "raw_sip_1m_bars"))}
    sources["missing_tails"] = {"artifact_id": audit["capture_artifact_id"], "run_id": audit["run_id"],
        "zip_sha256": audit["capture_zip_sha256"], "file_count": audit["verified_capture_file_count"],
        "record_count": audit["normalized_row_count"], "provider_attempts": audit["provider_attempts"],
        "execution_commit_sha": audit["execution_commit_sha"], "prior_audit_content_sha256": audit["content_sha256"]}
    return sources


def validate_segments(start: int, end: int, segments: list[dict]) -> None:
    if type(start) is not int or type(end) is not int or start < 0 or start >= end or not segments:
        raise ValueError("exact nonempty resource envelope required")
    cursor = start
    for segment in segments:
        lower, upper = segment["start_ns"], segment["end_ns"]
        if type(lower) is not int or type(upper) is not int or lower != cursor or not lower < upper <= end:
            raise ValueError("source envelopes overlap, have gaps or extend the frozen window")
        first, count = segment["first_source_record_ordinal"], segment["record_count"]
        if type(segment["source_tape_record_count"]) is not int or segment["source_tape_record_count"] < 0:
            raise ValueError("invalid source tape count")
        if type(count) is not int or count < 0 or (count == 0 and first is not None):
            raise ValueError("invalid empty segment or source count")
        if count and (type(first) is not int or first < 0 or first + count > segment["source_tape_record_count"]):
            raise ValueError("invalid source ordinal interval")
        cursor = upper
    if cursor != end:
        raise ValueError("source envelopes do not cover the complete frozen window")


def derive_recipes(root: Path) -> list[dict]:
    management, coverage, audit = parent_documents(root)
    specs = source_specs(root)
    missing = {r["coverage_id"]: r for r in frozen(root / reuse.MISSING_PATH)["requests"]}
    tail_receipts = {r["request_id"]: r for r in audit["primary_verification"]["receipts"]}
    windows = {r["request_id"]: r for r in management["requests"]}
    recipes = []
    for resource in coverage["resources"]:
        window = windows[resource["management_request_id"]]
        selected = resource["selection_evidence"]
        if len(resource["covered_intervals"]) != 1:
            raise ValueError("exact single retained source prefix required")
        count, first, last = (selected[k] for k in
            ("selected_record_count", "first_source_record_ordinal", "last_source_record_ordinal"))
        if (count == 0 and (first is not None or last is not None)) or (count and last - first + 1 != count):
            raise ValueError("retained selection is not an exact contiguous source slice")
        source_key = "original_bars" if resource["resource"] == "raw_sip_1m_bars" else "original_sip"
        kind = reuse.KINDS[resource["resource"]]
        lower, upper = resource["covered_intervals"][0]
        segments = [{"source_key": source_key, "source_artifact_id": specs[source_key]["artifact_id"],
            "source_zip_sha256": specs[source_key]["zip_sha256"], "source_request_id": resource["source_request_id"],
            "source_path": f"dates/{window['trading_date']}/{window['symbol']}-{kind}.jsonl.gz",
            "source_tape_file_sha256": selected["source_tape_file_sha256"],
            "source_tape_logical_sha256": selected["source_tape_logical_sha256"],
            "source_tape_record_count": selected["source_tape_record_count"],
            "first_source_record_ordinal": first, "record_count": count, "start_ns": lower, "end_ns": upper,
            "expected_selection_basis": "decimal_source_ordinal_colon_exact_canonical_row",
            "expected_selection_sha256": selected["selected_records_sha256"]}]
        if resource["missing_intervals"]:
            request = missing.pop(resource["coverage_id"])
            receipt = tail_receipts.pop(request["request_id"])
            require_exact(resource["missing_intervals"], [[request["start_ns"], request["end_ns"]]], "missing envelope")
            segments.append({"source_key": "missing_tails", "source_artifact_id": specs["missing_tails"]["artifact_id"],
                "source_zip_sha256": specs["missing_tails"]["zip_sha256"], "source_request_id": request["request_id"],
                "source_path": receipt["path"], "source_tape_file_sha256": receipt["file_sha256"],
                "source_tape_logical_sha256": receipt["logical_sha256"], "source_tape_record_count": receipt["record_count"],
                "first_source_record_ordinal": 0 if receipt["record_count"] else None,
                "record_count": receipt["record_count"], "start_ns": request["start_ns"], "end_ns": request["end_ns"],
                "expected_selection_basis": "exact_canonical_rows", "expected_selection_sha256": receipt["logical_sha256"]})
        validate_segments(window["start_ns"], window["end_ns"], segments)
        recipes.append({"resource_id": resource["coverage_id"], "resource": resource["resource"], "kind": kind,
            "management_request_id": window["request_id"], "trading_date": window["trading_date"], "symbol": window["symbol"],
            "start_ns": window["start_ns"], "end_ns": window["end_ns"], "end_exclusive": True,
            "feed": "sip", "asof": window["trading_date"], "adjustment": "raw" if kind == "session_1m_raw" else None,
            "opportunity_ids": window["opportunity_ids"], "segments": segments,
            "path": f"tapes/{window['request_id']}-{kind}.jsonl.gz"})
    if missing or tail_receipts or len(recipes) != 112 or len({r["resource_id"] for r in recipes}) != 112:
        raise ValueError("complete 112-resource composition and exact ten tails required")
    return recipes


def expected_contract(root: Path) -> dict:
    management, _, audit = parent_documents(root)
    return seal({"schema_version": 1, "contract_id": CONTRACT_ID,
        "artifact_type": "registered_provider_free_complete_management_input_composition",
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE, "frozen_parent_file_sha256": PARENT_PINS,
        "management_request_manifest_content_sha256": management["content_sha256"],
        "missing_capture_audit_content_sha256": audit["content_sha256"], "source_artifacts": source_specs(root),
        "resource_recipe_sha256": canonical_fingerprint(derive_recipes(root)),
        "merged_windows": 56, "logical_resources": 112, "opportunities": 109, "unavailable_entry_opportunities": 23,
        "hypothesis": "verified_reused_prefixes_and_exact_missing_tails_supply_all_frozen_management_input_envelopes",
        "composition": "byte_identical_canonical_source_rows_in_original_order_disjoint_half_open_segments",
        "lineage": "artifact_id_request_id_original_ordinal_to_composed_ordinal_via_contiguous_segment_receipts",
        "normalization": "unchanged_parent_normalizer_verified_before_copy_no_record_rewrite",
        "compression": {"format": "gzip", "level": 9, "mtime": 0, "filename": ""},
        "output_write": "finalize_one_compressed_tape_in_memory_then_exclusive_single_write_flush_fsync",
        "whole_source_archives_reverified": True, "write_once_output": True,
        "empty_envelopes": "retain_empty_tape_and_source_receipt_never_infer_trade_or_exit",
        "completed_bar_causality": "bar_close_is_not_usable_at_bar_start_future_projection_must_apply_frozen_rule",
        "management_trade_eligibility_filter_applied": False, "warmup_is_management_input": False,
        "entry_availability_is_changed_by_management_data": False, "source_window_extension_allowed": False,
        "implementation_file_sha256": {p: file_sha(root / p) for p in (MODULE_PATH, SCRIPT_PATH, WORKFLOW_PATH, TEST_PATH)},
        "next_gate": NEXT_GATE, **BOUNDARY})


def validate_registration(root: Path) -> dict:
    for name, expected in PARENT_PINS.items():
        accounts.availability._regular(root / name)
        if file_sha(root / name) != expected:
            raise ValueError("management composition parent differs: " + name)
    capture.validate_contract(root)
    audit = frozen(root / CAPTURE_AUDIT)
    if audit["verification_passed"] is not True or audit["independent_and_primary_verification_agree"] is not True:
        raise ValueError("verified tail acquisition required")
    require_exact(frozen(root / CONTRACT_PATH), expected_contract(root), "management input registration")
    return seal({"verification_passed": True, "contract_content_sha256": expected_contract(root)["content_sha256"], **BOUNDARY})


def verify_sources(root: Path, paths: dict[str, Path], progress=None) -> dict:
    specs = source_specs(root)
    if set(paths) != set(specs):
        raise ValueError("exact three source ZIPs required")
    for key, path in paths.items():
        accounts.availability._regular(path)
        if file_sha(path) != specs[key]["zip_sha256"]:
            raise ValueError("exact source ZIP differs: " + key)
    result = reuse.verify_bundle(root, root / reuse.OUTPUT_PATH,
        sip_zip=paths["original_sip"], bars_zip=paths["original_bars"], progress=progress)
    require_exact(result, frozen(root / capture.REUSE_AUDIT)["full_source_reconstruction"], "full retained reuse reconstruction")
    tail = capture.verify_archive(root, paths["missing_tails"],
        execution_commit=specs["missing_tails"]["execution_commit_sha"], run_id=str(specs["missing_tails"]["run_id"]))
    require_exact(tail, frozen(root / CAPTURE_AUDIT)["primary_verification"], "whole tail source verification")
    return seal({"contract_id": CONTRACT_ID, "all_source_archives_verified": True, "sources": specs,
        "original_reuse_reconstruction_content_sha256": result["content_sha256"],
        "missing_tail_verification_content_sha256": tail["content_sha256"],
        "verified_source_file_count": sum(s["file_count"] for s in specs.values()),
        "verified_source_tape_count": 520, "verified_source_row_count": sum(s["record_count"] for s in specs.values()),
        "normalization_verified_before_composition": True, "source_captures_modified": False, **BOUNDARY})


def row_timestamp_ns(raw: bytes) -> int:
    match = reuse.STAMP.search(raw)
    if match is None:
        raise ValueError("canonical source timestamp missing")
    timestamp = pd.Timestamp(match.group(1).decode())
    if pd.isna(timestamp) or timestamp.tzinfo is None:
        raise ValueError("aware source timestamp required")
    return int(timestamp.value)


@contextmanager
def finalized_gzip_file(path: Path):
    """Keep an in-progress compressor off the filesystem; retain partial evidence on failure."""
    if path.exists():
        raise FileExistsError("composed tape is write-once")
    buffer = io.BytesIO()
    try:
        with gzip.GzipFile(filename="", mode="wb", compresslevel=9, mtime=0, fileobj=buffer) as tape:
            yield tape
    finally:
        try:
            with path.open("xb") as destination:
                view = buffer.getbuffer()
                try:
                    if destination.write(view) != len(view):
                        raise OSError("short composed tape write")
                    destination.flush()
                    os.fsync(destination.fileno())
                finally:
                    view.release()
        finally:
            buffer.close()


def compose_tape(output: Path, recipe: dict, archives: dict[str, zipfile.ZipFile]) -> dict:
    validate_segments(recipe["start_ns"], recipe["end_ns"], recipe["segments"])
    relative = PurePosixPath(recipe["path"])
    if relative.is_absolute() or ".." in relative.parts or "\\" in recipe["path"] or len(relative.parts) != 2 or relative.parts[0] != "tapes":
        raise ValueError("unsafe composed tape path")
    path = output / recipe["path"]
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError("symbolic link tape path rejected")
    path.parent.mkdir(parents=True, exist_ok=True)
    logical, lineage, count, previous, segments = hashlib.sha256(), hashlib.sha256(), 0, None, []
    with finalized_gzip_file(path) as tape:
        for segment in recipe["segments"]:
            source_hash, selected_hash, copied = hashlib.sha256(), hashlib.sha256(), 0
            output_start = count
            first = segment["first_source_record_ordinal"]
            if segment["record_count"]:
                with archives[segment["source_key"]].open(segment["source_path"]) as member, gzip.GzipFile(fileobj=member) as source:
                    for ordinal, raw in enumerate(source):
                        if ordinal < first:
                            continue
                        if ordinal >= first + segment["record_count"]:
                            break
                        if len(raw) > 1000 or not raw.endswith(b"\n"):
                            raise ValueError("invalid canonical source row boundary")
                        stamp = row_timestamp_ns(raw)
                        if not segment["start_ns"] <= stamp < segment["end_ns"] or (previous is not None and stamp < previous):
                            raise ValueError("source segment interval or record order differs")
                        if recipe["kind"] == "session_1m_raw" and (stamp % 60_000_000_000 or stamp == previous):
                            raise ValueError("raw minute bar identity differs")
                        previous = stamp
                        ordinal_row = str(ordinal).encode() + b":" + raw
                        source_hash.update(raw)
                        selected_hash.update(ordinal_row)
                        lineage.update((str(segment["source_artifact_id"]) + ":" + segment["source_request_id"] + ":").encode() + ordinal_row)
                        logical.update(raw)
                        tape.write(raw)
                        copied += 1
                        count += 1
            if copied != segment["record_count"]:
                raise ValueError("source tape ended before the exact selection was copied")
            expected_basis = segment["expected_selection_basis"]
            if expected_basis not in {"decimal_source_ordinal_colon_exact_canonical_row", "exact_canonical_rows"}:
                raise ValueError("unknown frozen selection commitment")
            commitment = selected_hash if expected_basis == "decimal_source_ordinal_colon_exact_canonical_row" else source_hash
            if commitment.hexdigest() != segment["expected_selection_sha256"]:
                raise ValueError("copied source selection differs from independent parent evidence")
            segments.append({**segment, "composed_start_ordinal": output_start, "composed_end_ordinal_exclusive": count,
                "selected_rows_sha256": source_hash.hexdigest(), "selected_source_ordinals_sha256": selected_hash.hexdigest()})
    return {**recipe, "segments": segments, "record_count": count, "logical_sha256": logical.hexdigest(),
        "source_lineage_sha256": lineage.hexdigest(), "file_sha256": file_sha(path), "retained_bytes": path.stat().st_size,
        "complete_request_envelope": True, "empty_source_evidence": count == 0}


def documents(root: Path, receipts: list[dict], source_proof: dict) -> dict[str, dict]:
    management, _, _ = parent_documents(root)
    expected_ids = [r["resource_id"] for r in derive_recipes(root)]
    if [r["resource_id"] for r in receipts] != expected_ids:
        raise ValueError("complete ordered resource receipt population required")
    index = seal({"contract_id": CONTRACT_ID, "management_request_manifest_content_sha256": management["content_sha256"],
        "dates": management["dates"], "opportunity_windows": [{**op,
            "resource_ids": {resource: op["request_id"] + ":" + resource for resource in RESOURCES}}
            for op in management["opportunity_windows"]],
        "entry_availability_preserved": True, "unavailable_is_inferred_no_trade_outcome": False, **BOUNDARY})
    manifest = seal({"contract_id": CONTRACT_ID, "resources": receipts, "windows": management["requests"],
        "opportunity_input_index_content_sha256": index["content_sha256"],
        "source_verification_content_sha256": source_proof["content_sha256"], "all_request_envelopes_complete": True,
        "management_trade_eligibility_filter_applied": False, "rows_are_source_evidence_not_execution_outcomes": True, **BOUNDARY})
    unavailable = [op for op in management["opportunity_windows"] if op["entry_input_status"] == "unavailable"]
    readiness = seal({"contract_id": CONTRACT_ID, "management_source_composition_complete": True,
        "management_source_envelopes_verified": True, "merged_window_count": len(management["requests"]),
        "logical_resource_count": len(receipts), "complete_resource_count": len(receipts), "missing_resource_count": 0,
        "date_count": len(management["dates"]), "no_decision_dates": [d["trading_date"] for d in management["dates"] if d["opportunity_count"] == 0],
        "opportunity_count": len(management["opportunity_windows"]), "unavailable_entry_opportunity_count": len(unavailable),
        "unavailable_entry_opportunities": [{"opportunity_id": op["opportunity"]["opportunity_id"],
            "reason": op["entry_input_reason"], "availability_content_sha256": op["availability_content_sha256"]} for op in unavailable],
        "record_counts": {resource: sum(r["record_count"] for r in receipts if r["resource"] == resource) for resource in RESOURCES},
        "normalized_compressed_bytes": sum(r["retained_bytes"] for r in receipts),
        "empty_resource_tapes": sum(r["empty_source_evidence"] for r in receipts),
        "descriptive_sip_exit_may_close_account_position": False, "next_gate": NEXT_GATE, **BOUNDARY})
    return {"source-verification.json": source_proof, "management-input-manifest.json": manifest,
            "opportunity-input-index.json": index, "readiness-report.json": readiness}


def _output(root: Path, output: Path) -> None:
    if output.is_symlink() or any(p.is_symlink() for p in output.parents):
        raise ValueError("symbolic link output rejected")
    if output.resolve().is_relative_to(root.resolve()) and output.resolve() != (root / BUNDLE_PATH).resolve():
        raise ValueError("cannot overwrite frozen repository inputs")


def write_bundle(root: Path, output: Path, paths: dict[str, Path], progress=None) -> dict:
    _output(root, output)
    if output.exists():
        raise FileExistsError("management input composition is write-once")
    validate_registration(root)
    proof = verify_sources(root, paths, progress)
    recipes = derive_recipes(root)
    output.mkdir(parents=True, exist_ok=False)
    receipts = []
    try:
        with ExitStack() as stack:
            archives = {key: stack.enter_context(zipfile.ZipFile(path)) for key, path in paths.items()}
            for recipe in recipes:
                receipts.append(compose_tape(output, recipe, archives))
                if progress is not None:
                    progress({"composed_resources": len(receipts), "total_resources": len(recipes),
                              "composed_records": sum(r["record_count"] for r in receipts)})
        for key, spec in source_specs(root).items():
            if file_sha(paths[key]) != spec["zip_sha256"]:
                raise ValueError("source archive changed during composition")
        payloads = documents(root, receipts, proof)
        for name, payload in payloads.items():
            capture.write_json(output / name, payload)
        inventory = accounts.availability._inventory(output)
        verify_tape_receipts(output, receipts, inventory)
        manifest = seal({"contract_id": CONTRACT_ID, "contract_content_sha256": frozen(root / CONTRACT_PATH)["content_sha256"],
            "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
            "implementation_file_sha256": {p: file_sha(root / p) for p in (MODULE_PATH, SCRIPT_PATH, WORKFLOW_PATH, TEST_PATH, CONTRACT_PATH)},
            "file_inventory": inventory, "document_content_sha256": {n: p["content_sha256"] for n, p in payloads.items()},
            "normalized_tapes": len(receipts), "next_gate": NEXT_GATE, **BOUNDARY})
        capture.write_json(output / "freeze-manifest.json", manifest)
        return check_bundle_files(output)
    except Exception as exc:
        capture.write_json(output / "composition-failure.json", seal({"contract_id": CONTRACT_ID,
            "completed_resources": len(receipts), "exception_class": type(exc).__name__,
            "sanitized_error": "offline composition failed; partial output retained", **BOUNDARY}))
        raise ValueError("offline composition failed; partial evidence retained") from None


def verify_tape_receipts(output: Path, receipts: list[dict], inventory: dict) -> None:
    """Cross-check final files against write-time receipts, including gzip EOF/CRC."""
    if len({r['path'] for r in receipts}) != len(receipts):
        raise ValueError("duplicate composed tape receipt")
    for receipt in receipts:
        expected = {"sha256": receipt["file_sha256"], "bytes": receipt["retained_bytes"]}
        if inventory.get(receipt["path"]) != expected:
            raise ValueError("final tape differs from write-time receipt")
        logical, count, last = hashlib.sha256(), 0, b""
        with gzip.open(output / receipt["path"], "rb") as tape:
            for block in iter(lambda: tape.read(1024 * 1024), b""):
                logical.update(block)
                count += block.count(b"\n")
                last = block[-1:]
        if (last not in (b"", b"\n") or count != receipt["record_count"]
                or logical.hexdigest() != receipt["logical_sha256"]):
            raise ValueError("final tape logical content differs from write-time receipt")


def check_bundle_files(output: Path) -> dict:
    manifest = frozen(output / "freeze-manifest.json")
    actual = accounts.availability._inventory(output)
    require_exact({k: v for k, v in actual.items() if k != "freeze-manifest.json"}, manifest["file_inventory"], "complete composed file set")
    for name, expected in manifest["document_content_sha256"].items():
        if frozen(output / name)["content_sha256"] != expected:
            raise ValueError("composed metadata document differs")
    receipts = frozen(output / "management-input-manifest.json")["resources"]
    if (len(receipts) != manifest["normalized_tapes"] or set(actual)
            != set(METADATA_FILES) | {r["path"] for r in receipts}):
        raise ValueError("complete composed tape population differs")
    verify_tape_receipts(output, receipts, actual)
    return seal({"verification_passed": True, "freeze_manifest_content_sha256": manifest["content_sha256"],
        "file_inventory": actual, "readiness": frozen(output / "readiness-report.json"), **BOUNDARY})


def freeze_metadata(root: Path, output: Path) -> None:
    check_bundle_files(output)
    destination = root / SNAPSHOT_PATH
    if destination.exists() or destination.is_symlink() or any(p.is_symlink() for p in destination.parents):
        raise FileExistsError("committed management metadata is write-once")
    destination.mkdir(parents=True, exist_ok=False)
    for name in METADATA_FILES:
        with (destination / name).open("xb") as stream:
            stream.write((output / name).read_bytes())


def check_committed_metadata(root: Path, output: Path) -> dict:
    snapshot = root / SNAPSHOT_PATH
    inventory = accounts.availability._inventory(snapshot)
    if set(inventory) != set(METADATA_FILES):
        raise ValueError("committed metadata population differs")
    for name in METADATA_FILES:
        accounts.availability._regular(output / name)
        if (snapshot / name).read_bytes() != (output / name).read_bytes():
            raise ValueError("management output differs from committed freeze: " + name)
    return check_bundle_files(output)


def verify_bundle(root: Path, output: Path, paths: dict[str, Path], progress=None) -> dict:
    _output(root, output)
    observed = check_committed_metadata(root, output)
    with tempfile.TemporaryDirectory(prefix="management-source-reconstruction-") as directory:
        expected = write_bundle(root, Path(directory) / "bundle", paths, progress)
        require_exact(observed, expected, "full management input reconstruction")
    return observed


class ManagementInputBundle:
    """Verified input-only access; merged tails never leak into another opportunity."""
    def __init__(self, root: Path, output: Path, *, expected_manifest_content_sha256: str):
        _output(root, output)
        if not isinstance(expected_manifest_content_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_manifest_content_sha256):
            raise ValueError("caller must pin the exact independently verified input manifest")
        validate_registration(root)
        checked = check_committed_metadata(root, output)
        if checked["freeze_manifest_content_sha256"] != expected_manifest_content_sha256:
            raise ValueError("input bundle differs from caller's frozen parent")
        self.output = output
        self.resources = {r["resource_id"]: r for r in frozen(output / "management-input-manifest.json")["resources"]}
        self.opportunities = {r["opportunity"]["opportunity_id"]: r for r in frozen(output / "opportunity-input-index.json")["opportunity_windows"]}

    def opportunity(self, opportunity_id: str) -> dict:
        if opportunity_id not in self.opportunities:
            raise ValueError("unregistered management opportunity")
        return json.loads(json.dumps(self.opportunities[opportunity_id]))

    def iter_records(self, opportunity_id: str, resource: str):
        if resource not in RESOURCES:
            raise ValueError("unregistered management resource")
        opportunity = self.opportunity(opportunity_id)
        receipt = self.resources[opportunity["resource_ids"][resource]]
        path = self.output / receipt["path"]
        accounts.availability._regular(path)
        if file_sha(path) != receipt["file_sha256"]:
            raise ValueError("composed tape changed before input access")
        segments = receipt["segments"]
        segment_index = 0
        with gzip.open(path, "rb") as tape:
            for ordinal, raw in enumerate(tape):
                stamp = row_timestamp_ns(raw)
                if stamp < opportunity["start_ns"]:
                    continue
                if stamp >= opportunity["end_ns"]:
                    break
                while ordinal >= segments[segment_index]["composed_end_ordinal_exclusive"]:
                    segment_index += 1
                segment = segments[segment_index]
                yield {"record": reuse._json(raw), "timestamp_ns": stamp, "composed_record_ordinal": ordinal,
                    "source_artifact_id": segment["source_artifact_id"], "source_request_id": segment["source_request_id"],
                    "source_record_ordinal": segment["first_source_record_ordinal"] + ordinal - segment["composed_start_ordinal"]}
