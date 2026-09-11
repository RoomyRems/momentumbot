"""Emit a new registration or independently check its immutable parent inventory.

No provider access, account replay, file extraction or output overwrite. The
emit mode prints JSON for explicit registration; default mode is read-only.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

from momentumbot.research import early_pullback_selection_v01 as experiment


def parent_files(root):
    tree = subprocess.check_output(
        ["git", "rev-parse", f"{experiment.PARENT}^{{tree}}"], cwd=root, text=True).strip()
    experiment.require(tree == experiment.PARENT_TREE, "immutable parent tree differs")
    listed = subprocess.check_output(
        ["git", "ls-tree", "-rz", experiment.PARENT], cwd=root)
    expected = {}
    for entry in listed.rstrip(b"\0").split(b"\0"):
        metadata, path = entry.split(b"\t", 1)
        mode, kind, sha = metadata.decode().split()
        experiment.require(kind == "blob" and mode in ("100644", "100755"),
                           "regular tracked parent blobs required")
        expected[path.decode()] = sha
    raw = subprocess.check_output(["git", "archive", experiment.PARENT], cwd=root)
    seen = set()
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in sorted(archive.getmembers(), key=lambda item: item.name):
            if member.isdir():
                continue
            experiment.require(member.isfile(), "non-regular parent member")
            data = archive.extractfile(member).read()
            blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            experiment.require(member.name not in seen and expected.get(member.name) == blob,
                               "archived parent bytes differ from tracked blob")
            seen.add(member.name)
            yield member.name, data
    experiment.require(seen == set(expected), "parent archive omitted tracked files")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--emit", action="store_true")
    parser.add_argument("--verify-parent", action="store_true")
    args = parser.parse_args()
    if args.emit:
        exclusions = experiment.build_exclusions(parent_files(args.root))
        experiment.require(exclusions["content_sha256"] == experiment.EXCLUSION_CONTENT_SHA256,
                           "first selection inventory changed; do not re-select")
        print(json.dumps({experiment.EXCLUSION_PATH: exclusions,
                          experiment.CONTRACT_PATH: experiment.build_contract(args.root, exclusions)},
                         sort_keys=True, allow_nan=False))
        return
    contract = experiment.validate_registration(args.root)
    if args.verify_parent:
        exclusions = experiment.build_exclusions(parent_files(args.root))
        saved = json.loads((args.root / experiment.EXCLUSION_PATH).read_bytes())
        experiment.require(exclusions == saved, "saved exclusion inventory differs from immutable parent")
    print(json.dumps({"status": "verified", "contract_sha256": contract["content_sha256"],
                      "parent_inventory_reconstructed": args.verify_parent,
                      "provider_calls": 0, "market_evaluation": "not_started"}, sort_keys=True))


if __name__ == "__main__":
    main()
