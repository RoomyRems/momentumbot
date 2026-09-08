"""Independent exact-risk verification and strict parity with the failed parent.

Only stdlib and frozen independent verifiers are imported. Rational arithmetic
recomputes each public campaign's risk from confirmed journal fills and the
active confirmed stop. Parent chronology/account checks run without tolerance.
"""
from decimal import localcontext
from fractions import Fraction
import argparse
import hashlib
import json
from pathlib import Path

import verify_sealed_historical_account_replay_v01 as parent
from verify_sealed_historical_account_state_producer_v01 import checked_tree
from verify_sealed_historical_management_fee_reconciliation_v01 import checked, read, require, digest

ID = "sealed-historical-account-risk-projection-v0.1"
PARENT_RUNTIME = "28c745a20e6669a831ce6b9e09028e01a0c480bc1d88055c33b218ca9d88d56d"
PARENT_FILE = "58508258633b3ee959ecfa701c5e2489932513e058851b30c178a12b2e699869"


def verify_decimal_snapshot(snapshot):
    positions = {}
    for row in snapshot["journal"]:
        trade, evidence = row["fee_application"]["trade"], row["execution_evidence"]
        activation = row["activation_id"]
        if trade["side"] == "buy":
            require(not positions.get(activation, {}).get("quantity", 0), "risk basis overlaps")
            positions[activation] = {"quantity": trade["quantity"], "price": Fraction(trade["price"])}
        else:
            positions[activation]["quantity"] -= trade["quantity"]
    engine = snapshot["management"]
    total = Fraction(0)
    campaigns = snapshot["ledger"]["campaigns"]
    require(len({c["activation_id"] for c in campaigns}) == len(campaigns), "duplicate risk campaign")
    require({c["activation_id"] for c in campaigns} == set(positions), "risk campaign inventory differs")
    for campaign in campaigns:
        activation = campaign["activation_id"]
        position = positions[activation]
        require(type(campaign["quantity"]) is int and campaign["quantity"] == position["quantity"] >= 0, "risk shares differ")
        expected = Fraction(0)
        if position["quantity"]:
            require(engine is not None and engine["entry"]["activation_id"] == activation, "risk stop is not bound")
            stop = Fraction(str(engine["active_stop_price"]))
            require(0 < stop <= position["price"], "risk stop exceeds registered entry/breakeven scope")
            expected = (position["price"] - stop) * position["quantity"]
        require(Fraction(str(campaign["open_risk"])) == expected, "exact campaign risk differs")
        total += expected
    require(Fraction(str(snapshot["ledger"]["account"]["total_open_risk"])) == total, "exact account risk differs")
    return len(campaigns)


def verify_delta(before, after):
    """Allow only risk numbers and hashes of paired, checked structures.

    Hash values are not a blanket exclusion: every changed reference must map
    to the digest of a corresponding object. All referenced object contents
    undergo the same strict comparison. Orders, fills and failure details are
    compared as part of the complete tree, including arbitrary nested fields.
    """
    checked_tree(before)
    checked_tree(after)
    pins = {}

    def remember(left, right):
        if left in pins:
            require(pins[left] == right, "ambiguous parity commitment")
        pins[left] = right

    def collect(left, right):
        if isinstance(left, dict) and isinstance(right, dict):
            require(set(left) == set(right), "nonrisk object inventory changed")
            remember(digest(left), digest(right))
            if "content_sha256" in left:
                remember(left["content_sha256"], right["content_sha256"])
            for key in left:
                collect(left[key], right[key])
        elif isinstance(left, list) and isinstance(right, list):
            require(len(left) == len(right), "nonrisk list inventory changed")
            remember(digest(left), digest(right))
            for old, new in zip(left, right):
                collect(old, new)

    collect(before, after)
    changed = 0

    def compare(left, right, path=()):
        nonlocal changed
        if type(left) is type(right) and left == right:
            return
        risk = (path[-3:] == ("ledger", "account", "total_open_risk")
            or (path[-1:] == ("open_risk",) and len(path) >= 3 and path[-3] == "campaigns"))
        if risk:
            require(type(left) in (float, int) and type(right) in (float, int), "risk must retain numeric schema")
            changed += 1
            return
        if isinstance(left, dict) and isinstance(right, dict):
            for key in left:
                compare(left[key], right[key], path + (key,))
        elif isinstance(left, list) and isinstance(right, list):
            for index, (old, new) in enumerate(zip(left, right)):
                compare(old, new, path + (index,))
        elif type(left) is str and type(right) is str and pins.get(left) == right:
            return
        else:
            raise ValueError("nonrisk value changed at " + "/".join(map(str, path)))

    compare(before, after)
    return changed


def _pinned_file(path, expected_sha):
    value = read(path)
    require(hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha, "immutable evidence bytes differ")
    return value


def verify(root, runtime_root, binding_root, parent_runtime_root, expected_runtime_sha):
    contract = read(root / f"research/strategy/{ID}.json")
    require(contract["contract_id"] == ID and contract["parent_runtime_content_sha256"] == PARENT_RUNTIME
        and contract["parent_runtime_file_sha256"] == PARENT_FILE, "risk child parent identity differs")
    for path, sha in {**contract["frozen_parent_file_sha256"], **contract["implementation_file_sha256"]}.items():
        require(hashlib.sha256((root / path).read_bytes()).hexdigest() == sha, "frozen code/parent differs: " + path)
    registration_root = root / f"research/runtime/{ID}"
    registration = read(registration_root / "freeze-manifest.json")
    require(registration["contract_id"] == ID and registration["contract_content_sha256"] == contract["content_sha256"], "registration identity differs")
    for name, spec in registration["file_inventory"].items():
        value = _pinned_file(registration_root / name, spec["sha256"])
        require((registration_root / name).stat().st_size == spec["bytes"]
            and value["content_sha256"] == registration["document_content_sha256"][name], "registration inventory differs")
    manifest = _pinned_file(binding_root / "source-bindings.json", parent.BOUND_FILE)
    require(manifest["content_sha256"] == parent.BOUND, "original bound manifest differs")
    old = _pinned_file(parent_runtime_root / "account-replay.json", PARENT_FILE)
    require(old["content_sha256"] == PARENT_RUNTIME, "failed parent runtime differs")
    frozen = read(runtime_root / "freeze-manifest.json")
    parent.boundaries(frozen)
    require(frozen["contract_id"] == ID and frozen["contract_content_sha256"] == contract["content_sha256"]
        and set(frozen["file_inventory"]) == {"account-replay.json"}, "runtime freeze scope differs")
    spec = frozen["file_inventory"]["account-replay.json"]
    result = _pinned_file(runtime_root / "account-replay.json", spec["sha256"])
    require((runtime_root / "account-replay.json").stat().st_size == spec["bytes"], "runtime byte length differs")
    require(result["content_sha256"] == expected_runtime_sha == frozen["document_content_sha256"]["account-replay.json"], "independent runtime pin differs")
    require(result["contract_id"] == ID and result["parent_runtime_content_sha256"] == PARENT_RUNTIME, "runtime child identity differs")
    require(result["registration_freeze_content_sha256"] == registration["content_sha256"], "runtime registration differs")
    require(result["source_bindings_content_sha256"] == parent.BOUND and result["source_archives"] == manifest["source_archives"], "source authority differs")
    parent.boundaries(result)
    programs = read(root / f"research/runtime/{parent.ID}/source-programs.json")["programs"]
    require(len(programs) == len(result["paths"]) == len(old["paths"]) == 12, "all original paths required")
    counts = []
    with localcontext() as context:
        context.prec = 60
        for program, before, after in zip(programs, old["paths"], result["paths"]):
            delta = verify_delta(before, after)
            risk_campaigns = sum(verify_decimal_snapshot(pair["runtime"]["reconciliation_snapshot"])
                for pair in after["sessions"] if pair["runtime"]["reconciliation_snapshot"] is not None)
            counts.append({"path_id": after["path_id"], **parent.verify_path(program, after, manifest),
                "risk_fields_changed": delta, "exact_risk_campaigns_verified": risk_campaigns})
    totals = {k: sum(c[k] for c in counts) for k in counts[0] if k != "path_id"}
    require((totals["sessions"], totals["opportunity_references"], totals["unavailable_references"]) == (360, 744, 162), "original population differs")
    return parent.seal({"contract_id": ID, "verification_passed": True,
        "runtime_content_sha256": expected_runtime_sha, "source_bindings_content_sha256": parent.BOUND,
        "parent_runtime_content_sha256": PARENT_RUNTIME,
        "registration_freeze_content_sha256": registration["content_sha256"], "paths": counts, "totals": totals,
        "unchanged_parent_chronology_and_account_checks_passed": True,
        "all_nonrisk_values_and_bound_hash_references_match_parent": True,
        "independent_fill_simulation": False, "financial_metrics_eligible": False,
        "account_backtest_complete": False, "retrospective_labels_opened": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("runtime-root", "binding-root", "parent-runtime-root", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--expected-runtime-sha256", required=True)
    args = parser.parse_args()
    import sys
    from run_offline_python_v13 import deny_external_io
    sys.addaudithook(deny_external_io)
    result = verify(Path(__file__).resolve().parents[1], args.runtime_root, args.binding_root,
        args.parent_runtime_root, args.expected_runtime_sha256)
    with args.output.open("xb") as handle:
        handle.write((json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
        handle.flush()
        __import__("os").fsync(handle.fileno())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
