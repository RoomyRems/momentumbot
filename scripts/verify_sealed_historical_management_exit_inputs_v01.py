"""Independent stdlib-only check of all exit source bytes and bundle identities.

Does not import the composer, acquisition verifier, broker or strategy modules.
The exact archived provenance was independently verified at the frozen parent;
this checker reopens every archive member and every selected normalized row.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile

CID = "sealed-historical-management-exit-inputs-v0.1"
AUDIT = "research/data-audits/sealed-historical-management-exit-acquisition-v0.1-independent-verification-34172486163.json"
REPORT = "research/data-audits/sealed-historical-management-exit-acquisition-v0.1-report-34172486163.json"
REUSE = "research/data-audits/sealed-historical-management-exit-quote-v0.1-xage-reuse.json"
PLAN = "research/runtime/sealed-historical-management-runner-v0.1/exit-input-request-plan.json"
WINDOWS = "research/runtime/sealed-historical-management-projection-v0.1/projection-input-requirements.json"
METADATA = {"source-verification.json", "exit-input-manifest.json", "opportunity-input-index.json", "readiness-report.json", "freeze-manifest.json"}


def check(ok, message):
    if not ok:
        raise ValueError(message)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def sealed(raw):
    data = json.loads(raw)
    check(data["content_sha256"] == sha(encoded({k: v for k, v in data.items() if k != "content_sha256"})), "JSON seal differs")
    return data


def regular(path):
    check(path.is_file() and not path.is_symlink() and not any(p.is_symlink() for p in path.parents), "regular source file required")


def archive(path, spec):
    regular(path)
    raw = path.read_bytes()
    check((len(raw), sha(raw)) == (spec["bytes"], spec["sha256"]), "exact source archive bytes differ")
    members = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as handle:
        for info in handle.infolist():
            name = info.filename
            relative = PurePosixPath(name)
            check(name == str(relative) and not relative.is_absolute() and ".." not in relative.parts
                and "\\" not in name and not info.is_dir() and not stat.S_ISLNK(info.external_attr >> 16)
                and name not in members, "unsafe or duplicate archive member")
            members[name] = handle.read(info)
    inventory = {n: {"bytes": len(v), "sha256": sha(v)} for n, v in sorted(members.items())}
    check(len(inventory) == spec["file_count"], "complete source inventory differs")
    return members, inventory


def records(raw, request, tape):
    check((len(raw), sha(raw)) == (tape["file_bytes"], tape["file_sha256"]), "compressed source tape differs")
    rows, digest, length, previous = [], hashlib.sha256(), 0, None
    source_sha = sha(encoded(request))
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as handle:
        for ordinal, line in enumerate(handle):
            row = json.loads(line)
            check(line == encoded(row) + b"\n", "canonical source row differs")
            digest.update(line)
            length += len(line)
            timestamp = row["ts_recv_ns"]
            check(type(timestamp) is int and request["start_ns"] <= timestamp < request["end_ns"], "source time outside original request")
            check(row["symbol"] == request["symbols"][0], "source symbol differs")
            if request["schema"] == "mbp-1":
                check(set(row) == {"symbol", "ts_recv_ns", "sequence", "bid_px_nanos", "bid_size", "ask_px_nanos", "ask_size", "source_request_sha256", "source_record_index"}, "quote fields differ")
                check(row["source_request_sha256"] == source_sha and type(row["source_record_index"]) is int
                    and row["source_record_index"] == ordinal, "original quote source identity or ordinal differs")
                for field in ("sequence", "bid_px_nanos", "bid_size", "ask_px_nanos", "ask_size"):
                    check(type(row[field]) is int and row[field] >= 0, "native numeric field differs")
                key = (timestamp, row["sequence"])
            else:
                check(request["schema"] == "status" and set(row) == {"symbol", "ts_recv_ns", "action", "is_trading"}, "status fields differ")
                check(type(row["action"]) is int and 0 <= row["action"] <= 14 and row["is_trading"] in {"Y", "N", "~"}, "status vocabulary differs")
                key = (timestamp, ordinal)
            check(previous is None or key >= previous, "original native record order reversed")
            previous = key
            rows.append(row)
    check(rows and (len(rows), length, digest.hexdigest()) == (tape["row_count"], tape["normalized_bytes"], tape["normalized_sha256"]), "complete normalized tape differs")
    return rows


def verify(root, output, paths):
    contract = sealed((root / f"research/strategy/{CID}.json").read_bytes())
    check(contract["parent_commit_sha"] == "c0ccf773fcc49091682f600c07d991fdd26ab6a8", "frozen composition parent differs")
    for name, expected in {**contract["frozen_parent_file_sha256"], **contract["implementation_file_sha256"]}.items():
        regular(root / name)
        check(sha((root / name).read_bytes()) == expected, "parent or implementation file differs: " + name)
    audit, report, reuse, plan, windows = [sealed((root / p).read_bytes()) for p in (AUDIT, REPORT, REUSE, PLAN, WINDOWS)]
    specs = contract["source_artifacts"]
    check(set(paths) == set(specs) == {"exit_result", "exit_consumption", "entry_result", "entry_consumption"}, "exact four sources required")
    archives, inventories = {}, {}
    for key in specs:
        archives[key], inventories[key] = archive(paths[key], specs[key])
        if key.startswith("exit_"):
            kind = key.split("_")[1]
            check(inventories[key] == audit["independent_verification"]["archives"][kind]["files"], "parent audit archive inventory differs")
        else:
            check(specs[key] == reuse["archives"][key.split("_")[1]], "original reuse archive provenance differs")
    for prefix in ("exit", "entry"):
        left, right = archives[prefix + "_result"], archives[prefix + "_consumption"]
        for name in set(left) & set(right):
            check(left[name] == right[name], "shared durable consumption evidence differs")
    check(archives["exit_result"]["capture-report.json"] == (root / REPORT).read_bytes(), "exact exit report differs")
    actual = {}
    for path in sorted(output.rglob("*")):
        check(not path.is_symlink() and (path.is_dir() or path.is_file()), "nonregular output member")
        if path.is_file():
            regular(path)
            raw = path.read_bytes()
            actual[path.relative_to(output).as_posix()] = {"bytes": len(raw), "sha256": sha(raw)}
    documents = {n: sealed((output / n).read_bytes()) for n in METADATA}
    for name in METADATA:
        check((output / name).read_bytes() == (root / f"research/runtime/{CID}" / name).read_bytes(), "committed freeze differs")
    manifest, index, freeze, readiness = (documents[n] for n in ("exit-input-manifest.json", "opportunity-input-index.json", "freeze-manifest.json", "readiness-report.json"))
    check(freeze["file_inventory"] == {n: v for n, v in actual.items() if n != "freeze-manifest.json"}, "complete final file inventory differs")
    check(freeze["contract_content_sha256"] == contract["content_sha256"], "freeze registration binding differs")
    check(freeze["document_content_sha256"] == {n: d["content_sha256"] for n, d in documents.items() if n != "freeze-manifest.json"}, "frozen document identities differ")
    check(index["opportunities"] == plan["opportunities"] and index["opportunity_windows"] == windows["opportunity_windows"], "original opportunities or unavailable entries changed")
    check(len(index["opportunities"]) == 109 and sum(o["entry_input_status"] == "unavailable" for o in index["opportunities"]) == 23, "original entry population differs")
    check([g["original_group"] for g in manifest["groups"]] == plan["groups"], "original common groups changed")
    check(len(manifest["groups"]) == 41 and len(manifest["resources"]) == 82, "complete exit source population differs")
    new = {sha(encoded(r)): (i, r) for i, r in enumerate(plan["new_requests"])}
    old = {sha(encoded(s["request"])): s for s in reuse["sources"]}
    by_id = {r["resource_id"]: r for r in manifest["resources"]}
    check(len(by_id) == 82, "duplicate resource identity")
    normalized, counts, source_count, seen = 0, {"mbp-1": 0, "status": 0}, {"exit_result": 0, "entry_result": 0}, set()
    for group in manifest["groups"]:
        original = group["original_group"]
        check(group["resource_ids"] == [original["group_id"] + ":" + schema for schema in ("mbp-1", "status")], "group source mapping differs")
        payload = {}
        for prefix, rid, request in zip(("quote", "status"), group["resource_ids"], original["requests"], strict=True):
            r = by_id[rid]
            request_sha = sha(encoded(request))
            if request_sha in new:
                ordinal, expected = new.pop(request_sha)
                key = "exit_result"
                check(report["requests"][ordinal]["status"] == "complete", "incomplete exit source")
                expected_tape = report["requests"][ordinal]["tape"]
            else:
                source = old.pop(request_sha)
                ordinal, expected = source["original_request_ordinal"], source["request"]
                key = "entry_result"
                expected_tape = source["source_evidence"]["tape"]
            check(r["request"] == expected == request and r["request_content_sha256"] == request_sha, "request identity changed")
            check((r["source_key"], r["source_request_ordinal"], r["source_artifact_id"], r["source_zip_sha256"])
                == (key, ordinal, specs[key]["artifact_id"], specs[key]["sha256"]), "source provenance changed")
            expected_path = f"tapes/{key}-request-{ordinal:03d}.jsonl.gz"
            check(r["path"] == expected_path and expected_path not in seen, "source output namespace differs")
            seen.add(expected_path)
            receipt_name = f"receipts/request-{ordinal:03d}.json"
            receipt_raw = archives[key][receipt_name]
            receipt = sealed(receipt_raw)
            check(r["source_receipt_path"] == receipt_name and r["source_receipt_file_sha256"] == sha(receipt_raw), "original receipt binding differs")
            check(receipt["request"] == request and receipt["completion"]["status"] == "complete"
                and r["source_tape"] == receipt["completion"]["tape"] == expected_tape, "original complete tape receipt differs")
            raw = (output / expected_path).read_bytes()
            check(raw == archives[key][expected_tape["path"]], "copied compressed source bytes changed")
            rows = records(raw, request, expected_tape)
            payload[prefix + "_records"] = rows
            payload[prefix + "_request"] = request
            lower = original["required_quote_start_ns"] if prefix == "quote" else request["start_ns"]
            check((r["required_start_ns"], r["required_end_ns"]) == (lower, original["required_end_ns"]), "required envelope changed")
            check(request["start_ns"] <= lower < original["required_end_ns"] <= request["end_ns"], "required exit interval outside source")
            normalized += expected_tape["normalized_bytes"]
            counts[request["schema"]] += len(rows)
            source_count[key] += 1
        check(sha(encoded(payload)) == group["execution_tape_content_sha256"], "stable four-key execution payload hash differs")
    check(not new and not old and source_count == {"exit_result": 80, "entry_result": 2}, "sources missing or duplicated")
    check(set(actual) == METADATA | seen and len(actual) == 87, "unexpected or missing composed files")
    check(counts == {"mbp-1": 2223297, "status": 151} and normalized == 604286662, "complete composed population differs")
    check(readiness["schema_row_counts"] == counts and readiness["normalized_bytes"] == normalized, "readiness counts differ")
    for document in documents.values():
        for key in ("historical_execution_authorized", "account_or_fill_simulation_executed", "backtesting_executed", "retrospective_inputs_loaded", "policy_changed", "original_entry_inputs_changed", "all_exit_times_executable_inferred", "unavailable_entries_rescued", "historical_runtime_activation_ready"):
            check(document[key] is False, "closed boundary changed: " + key)
        check(document["provider_calls"] == 0, "provider-free boundary changed")
    return {"verification_passed": True, "production_verifier_imported": False, "provider_calls": 0,
        "contract_content_sha256": contract["content_sha256"], "freeze_manifest_content_sha256": freeze["content_sha256"],
        "source_archives": specs, "direct_archive_file_count": sum(len(i) for i in inventories.values()),
        "file_inventory": actual, "common_source_pairs": 41, "source_tapes": 82, "source_counts": source_count,
        "schema_row_counts": counts, "normalized_bytes": normalized, "original_opportunities": 109,
        "unavailable_entry_opportunities": 23, "original_source_ordinals_preserved": True,
        "stable_execution_payload_hashes_verified": 41, "historical_execution_authorized": False,
        "retrospective_inputs_loaded": False, "all_exit_times_executable_inferred": False}


def deny_io(event, args):
    if event.startswith("socket.") or event in {"subprocess.Popen", "os.system", "os.posix_spawn", "os.posix_spawnp", "os.exec", "os.fork", "os.forkpty"}:
        raise RuntimeError("independent exit verification forbids external IO")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("exit-result", "exit-consumption", "entry-result", "entry-consumption"):
        parser.add_argument("--" + name + "-zip", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    sys.addaudithook(deny_io)
    paths = {key: getattr(args, key + "_zip") for key in ("exit_result", "exit_consumption", "entry_result", "entry_consumption")}
    print(json.dumps(verify(Path(__file__).resolve().parents[1], args.output_root, paths), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
