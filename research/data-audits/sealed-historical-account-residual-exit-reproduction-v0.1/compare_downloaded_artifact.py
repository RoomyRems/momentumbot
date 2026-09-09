"""Read-only byte verification of the separately registered reproduction outputs."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile


CONTRACT_ID = "sealed-historical-account-residual-exit-reproduction-v0.1"
IMPLEMENTATION = "5b3e1864654abdd239f46f7e07b74fd070759f33"
REGISTRATION = "25b2124138c419363176286e9bb8e209c210792365f00fc6ae4c6245a1742582"
RUN_ID = 34347599749


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def seal(value):
    return {**value, "content_sha256": sha(canonical(value))}


def checked(raw):
    value = json.loads(raw)
    require(isinstance(value, dict), "document must be an object")
    unsigned = {key: item for key, item in value.items() if key != "content_sha256"}
    require(value.get("content_sha256") == sha(canonical(unsigned)), "document seal differs")
    require(raw == (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode(),
            "noncanonical serialized document")
    return value


def spec(raw):
    return {"bytes": len(raw), "sha256": sha(raw)}


def main():
    parser = argparse.ArgumentParser()
    for name in ("repo", "archive", "artifact-metadata", "local-root", "extract-root", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    contract = checked((args.repo / f"research/strategy/{CONTRACT_ID}.json").read_bytes())
    registration = checked((args.repo / f"research/runtime/{CONTRACT_ID}/freeze-manifest.json").read_bytes())
    require(registration["content_sha256"] == REGISTRATION, "registration changed")
    require(registration["contract_content_sha256"] == contract["content_sha256"], "contract differs")
    expected = contract["expected_documents"]
    require(len(expected) == 6, "original component count differs")
    names = set(expected) | {"reproduction-attempt.json", "reproduction-verification.json", "reproduction-freeze.json"}
    require(len(names) == 9, "reproduction document count differs")
    metadata = json.loads(args.artifact_metadata.read_text())
    require(metadata["workflow_run"]["id"] == RUN_ID, "unexpected hosted run")
    require(metadata["workflow_run"]["head_sha"] == IMPLEMENTATION, "unexpected implementation")
    require(metadata["name"] == f"sealed-historical-residual-reproduction-v01-{RUN_ID}-1", "attempt identity differs")
    require(metadata.get("expired") is False, "artifact expired")
    archive_bytes = args.archive.read_bytes()
    require(spec(archive_bytes) == {"bytes": metadata["size_in_bytes"], "sha256": metadata["digest"].removeprefix("sha256:")}, "archive metadata differs")
    local_files = list(args.local_root.rglob("*"))
    require(not args.local_root.is_symlink() and not any(p.is_symlink() for p in local_files), "local symlink")
    require({p.relative_to(args.local_root).as_posix() for p in local_files if p.is_file()} == names, "local inventory differs")
    members = {}
    with zipfile.ZipFile(args.archive) as archive:
        infos = archive.infolist()
        require(len(infos) == len(names) and {i.filename for i in infos} == names, "ZIP inventory or duplicate differs")
        for info in infos:
            path = PurePosixPath(info.filename)
            require(not path.is_absolute() and ".." not in path.parts and not info.is_dir(), "unsafe ZIP member")
            require(not stat.S_ISLNK(info.external_attr >> 16), "ZIP symlink")
        require(archive.testzip() is None, "ZIP CRC differs")
        for info in infos:
            members[info.filename] = archive.read(info)
    documents = {}
    inventory = {}
    rows = []
    for name, raw in sorted(members.items()):
        require(raw == (args.local_root / name).read_bytes(), "hosted/local bytes differ: " + name)
        doc = checked(raw)
        documents[name] = doc
        inventory[name] = spec(raw)
        original_match = None
        if name in expected:
            require({**spec(raw), "content_sha256": doc["content_sha256"]} == expected[name], "original component differs: " + name)
            original_match = True
        rows.append({"member": name, **spec(raw), "content_sha256": doc["content_sha256"],
                     "byte_identical_local_hosted": True, "matches_original_component": original_match})
    receipt = documents["reproduction-attempt.json"]
    report = documents["reproduction-verification.json"]
    freeze = documents["reproduction-freeze.json"]
    require(receipt["registration_freeze_content_sha256"] == REGISTRATION, "receipt registration differs")
    require(report["attempt_content_sha256"] == receipt["content_sha256"], "report receipt differs")
    require(report["runtime_reproduction_verified"] is True, "runtime reproduction rejected")
    require(report["all_six_original_component_files_byte_identical"] is True, "original comparison rejected")
    require(report["file_inventory"] == expected, "report component inventory differs")
    require(report["expected_incomplete_states_preserved"] == contract["required_incomplete_states"], "incomplete states differ")
    require(freeze["file_inventory"] == {name: row for name, row in inventory.items() if name != "reproduction-freeze.json"}, "reproduction freeze inventory differs")
    require(freeze["document_content_sha256"] == {name: doc["content_sha256"] for name, doc in documents.items() if name != "reproduction-freeze.json"}, "freeze seals differ")
    require(documents["verification/verification.json"]["verification_passed"] is True, "corrected verification failed")
    for key in ("runtime_mechanics_changed", "verification_mechanics_changed", "original_attempts_overwritten", "provider_requests_authorized", "broker_orders_authorized", "financial_metrics_eligible", "account_backtest_complete", "retrospective_labels_opened", "policy_promotion_eligible", "overnight_execution_authorized"):
        require(report[key] is False and freeze[key] is False and receipt[key] is False, "boundary differs: " + key)
    result = seal({"artifact_type": "independent_original_local_hosted_reproduction_byte_comparison",
        "contract_id": CONTRACT_ID, "registration_freeze_content_sha256": REGISTRATION,
        "implementation_commit_sha": IMPLEMENTATION, "hosted_run_id": RUN_ID, "hosted_run_attempt": 1,
        "hosted_artifact_id": metadata["id"], "archive_bytes": len(archive_bytes), "archive_sha256": sha(archive_bytes),
        "exact_nine_member_inventory_verified": True, "no_duplicate_or_symlink_members": True, "crc_verified": True,
        "all_nine_files_byte_identical_local_hosted": True, "all_six_original_components_byte_identical": True,
        "all_document_content_seals_and_serialized_bytes_verified": True,
        "original_runtime_content_sha256": contract["expected_runtime_content_sha256"],
        "reproduction_report_content_sha256": report["content_sha256"],
        "reproduction_freeze_content_sha256": freeze["content_sha256"],
        "corrected_verification_content_sha256": documents["verification/verification.json"]["content_sha256"],
        "members": rows, "account_backtest_complete": False, "financial_metrics_eligible": False,
        "retrospective_labels_opened": False, "provider_requests_authorized": False, "broker_orders_authorized": False})
    require(not args.extract_root.exists() and not args.extract_root.is_symlink(), "new extract directory required")
    args.extract_root.mkdir()
    for name, raw in members.items():
        destination = args.extract_root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as handle:
            handle.write(raw)
    with args.output.open("x") as handle:
        handle.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
