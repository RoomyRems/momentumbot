"""Independent stdlib source-binding checker; no account or strategy imports.

Checks external archive bytes, original scanner/decision joins, fixed candidate
projection, native entry/exit identities, every management lineage stream and
every account context. It does not simulate fills or approve corporate actions.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile
from zoneinfo import ZoneInfo

from verify_sealed_historical_management_exit_inputs_v01 import records as native_records

ID = "sealed-historical-source-binding-v0.1"
PARENT_FREEZE = "0bf8f0ac9eb5262afca10addbd4068cc7aab3453dac8b227433600935c2e6338"
BASE = "research/runtime/"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def checked(value):
    require(value["content_sha256"] == digest({k: v for k, v in value.items() if k != "content_sha256"}), "JSON seal differs")
    return value


def read(path):
    return checked(parse(path.read_bytes()))


def ns(value):
    match = re.fullmatch(r"(.{19})(?:\.(\d{1,9}))?(Z|[+-]\d\d:\d\d)", value)
    require(match is not None, "aware exact source timestamp required")
    seconds, fraction, zone = match.groups()
    stamp = datetime.fromisoformat(seconds + ("+00:00" if zone == "Z" else zone))
    return int(stamp.timestamp()) * 10**9 + int((fraction or "").ljust(9, "0"))


def candidate(row, profile):
    require(profile in {"current-general-2026", "current-small-account-2026"}, "original profile required")
    small = profile == "current-small-account-2026"
    price, gain, rvol = (float(row[k]) for k in ("price", "percent_gain", "exact_same_time_rvol"))
    rank, floating = row["top_gainer_rank"], row["estimated_float_shares"]
    pillars = {"percent_gain": gain >= (25 if small else 10), "relative_volume": rvol >= 5,
        "fresh_news": row["has_provider_news_as_of"] is True,
        "price": (1.5 if small else 2) <= price <= (6 if small else 20),
        "float": floating is not None and 0 < floating < 10_000_000}
    missing = [k for k, v in pillars.items() if not v]
    rank_ok = not small or (rank is not None and rank <= 3)
    require(row["candidate_completed_bar_present"] is True and rank_ok, "candidate completed bar or rank differs")
    require(not missing or missing == ["fresh_news"] and rank == 1, "candidate fails original frozen profile")
    return {"symbol": row["symbol"], "timestamp": datetime.fromisoformat(row["decision_time"].replace("Z", "+00:00")).isoformat(),
        "price": price, "cumulative_volume": row["cumulative_volume"], "relative_volume": rvol,
        "percent_gain": gain, "float_shares": floating, "has_fresh_news": row["has_provider_news_as_of"],
        "top_gainer_rank": rank, "pillars": pillars, "quality": "conditional" if missing else "a_quality",
        "reasons": ["provider-relative no-news allowed only for current rank one"] if missing else []}


def stream_rows(raw, recipe, window):
    require(hashlib.sha256(raw).hexdigest() == recipe["file_sha256"], "original management tape bytes differ")
    rows = []
    segment_index = 0
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as handle:
        for ordinal, line in enumerate(handle):
            row = parse(line)
            require(encoded(row) + b"\n" == line, "canonical management source row differs")
            at = ns(row["t"])
            if not window["start_ns"] <= at < window["end_ns"]:
                continue
            while ordinal >= recipe["segments"][segment_index]["composed_end_ordinal_exclusive"]:
                segment_index += 1
            segment = recipe["segments"][segment_index]
            rows.append({"record": row, "timestamp_ns": at, "composed_record_ordinal": ordinal,
                "source_artifact_id": segment["source_artifact_id"], "source_request_id": segment["source_request_id"],
                "source_record_ordinal": segment["first_source_record_ordinal"] + ordinal - segment["composed_start_ordinal"]})
    return {"rows": len(rows), "sha256": hashlib.sha256(b"".join(encoded(r) + b"\n" for r in rows)).hexdigest()}


def verify(root, output, paths, expected_manifest_sha256):
    contract = read(root / f"research/strategy/{ID}.json")
    require(contract["parent_continuity_freeze_content_sha256"] == PARENT_FREEZE, "frozen continuity parent differs")
    for name, sha in {**contract["frozen_parent_file_sha256"], **contract["implementation_file_sha256"]}.items():
        require(hashlib.sha256((root / name).read_bytes()).hexdigest() == sha, "frozen file differs: " + name)
    freeze = read(output / "freeze-manifest.json")
    require(freeze["contract_content_sha256"] == contract["content_sha256"], "source artifact registration differs")
    require({p.name for p in output.iterdir()} - {"independent-verification.json"}
        == set(freeze["file_inventory"]) | {"freeze-manifest.json"}, "bound artifact inventory differs")
    for name, info in freeze["file_inventory"].items():
        raw = (output / name).read_bytes()
        require(info == {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}, "bound artifact bytes differ")
    manifest = read(output / "source-bindings.json")
    require(manifest["content_sha256"] == expected_manifest_sha256, "external source binding commitment differs")
    require(manifest["source_archives"] == contract["source_archives"], "source archive pins differ")
    reg = read(root / BASE / ID / "freeze-manifest.json")
    require(manifest["registration_freeze_content_sha256"] == reg["content_sha256"], "registration freeze differs")
    for key in ("historical_runtime_authorized", "historical_account_execution_enabled", "account_or_fill_simulation_executed",
            "financial_metrics_eligible", "corporate_action_source_provenance_verified", "retrospective_inputs_read"):
        require(manifest[key] is False, "closed runtime or corporate-action boundary differs")
    plan = read(root / BASE / "sealed-historical-account-management-inputs-v0.1/account-session-input-plan.json")
    require(manifest["paths"] == plan["paths"], "original 360 account slots differ")
    windows = read(root / BASE / "sealed-historical-management-projection-v0.1/projection-input-requirements.json")["opportunity_windows"]
    require([r["window"] for r in manifest["opportunities"]] == windows, "109 original windows or population differ")
    management = read(root / BASE / "sealed-historical-management-inputs-v0.1/management-input-manifest.json")
    resources = {r["resource_id"]: r for r in management["resources"]}
    exit_manifest = read(root / BASE / "sealed-historical-management-exit-inputs-v0.1/exit-input-manifest.json")
    exit_groups = {g["original_group"]["group_id"]: g for g in exit_manifest["groups"]}
    exit_resources = {r["resource_id"]: r for r in exit_manifest["resources"]}
    exit_ops = {r["opportunity_id"]: r for r in read(root / BASE / "sealed-historical-management-exit-inputs-v0.1/opportunity-input-index.json")["opportunities"]}
    entry_requests = read(root / BASE / "sealed-historical-execution-input-plan-v0.1/request-manifest.json")["requests"]
    counts = {"activations": 0, "opportunities": 0, "available_entries": 0, "unavailable_entries": 0,
        "management_streams": 0, "management_envelope_occurrences": 0, "entry_native_sources": 0,
        "exit_source_pairs": 0, "account_contexts": 0, "carry_dependencies": 0}
    with ExitStack() as stack:
        archives = {}
        for key, spec in contract["source_archives"].items():
            path = paths[key]
            require(not path.is_symlink() and path.is_file(), "regular original archive required")
            raw = path.read_bytes()
            require(len(raw) == spec["bytes"] and hashlib.sha256(raw).hexdigest() == spec["sha256"], "original archive bytes differ")
            archives[key] = stack.enter_context(zipfile.ZipFile(io.BytesIO(raw)))
        prefix = stack.enter_context(zipfile.ZipFile(io.BytesIO(archives["entry_result"].read("parent-v02-result.zip"))))
        entry = {}
        for index, request in enumerate(entry_requests):
            if index == 24:
                entry[request["request_id"]] = (request, None)
                continue
            archive = prefix if index < 24 else archives["entry_result"]
            receipt = checked(parse(archive.read(f"receipts/request-{index:03d}.json")))
            require(receipt["request"] == request, "original entry receipt request differs")
            tape = receipt["completion"]["tape"]
            rows = native_records(archive.read(tape["path"]), request, tape)
            entry[request["request_id"]] = (request, rows)
            counts["entry_native_sources"] += 1
        original_activations, decisions, available = {}, {}, {}
        for path in sorted((root / BASE / "sealed-historical-scanner-activation-v0.2/dates").glob("*.json")):
            daily = read(path)
            day = daily["trading_date"]
            snapshot = checked(parse(archives["scanner"].read(f"source/causal-scanner-snapshot-v0.3/{day}/scanner-snapshot.json")))
            require(snapshot["content_sha256"] == daily["source_scanner_snapshot_content_sha256"], "original scanner snapshot differs")
            wanted = {a["scanner_record_content_sha256"] for a in daily["activations"]}
            rows = {}
            for row in snapshot["rows"]:
                sha = digest(row)
                if sha in wanted:
                    require(sha not in rows, "duplicate original scanner row")
                    rows[sha] = row
            for a in daily["activations"]:
                original_activations[a["activation_id"]] = {"activation": a, "scanner_row": rows[a["scanner_record_content_sha256"]]}
            micro = read(root / BASE / f"sealed-historical-micro-v0.1/dates/{day}.json")
            decisions.update({digest(d): d for d in micro["decisions"]})
            avail = checked(parse(gzip.decompress((root / BASE / f"sealed-historical-execution-availability-v0.1/dates/{day}.json.gz").read_bytes())))
            available.update({r["opportunity"]["opportunity_id"]: r for r in avail["opportunities"]})
        require(manifest["activations"] == list(original_activations.values()), "complete original activation binding differs")
        counts["activations"] = len(original_activations)
        pair_cache, entry_cache = {}, {}
        for binding in manifest["opportunities"]:
            checked(binding)
            window, oid = binding["window"], binding["opportunity_id"]
            op = window["opportunity"]
            source = original_activations[op["activation_id"]]
            require(binding["activation"] == source["activation"] and binding["scanner_row"] == source["scanner_row"], "scanner activation row differs")
            require(binding["source_decision"] == decisions[op["source_decision_content_sha256"]], "original Micro decision differs")
            require(ns(source["scanner_row"]["decision_time"]) == op["candidate_qualified_ts_ns"] <= op["decision_ts_ns"], "candidate timing differs")
            require(binding["candidates"] == {p: candidate(source["scanner_row"], p) for p in op["eligible_strategy_profile_ids"]}, "original candidate priority projection differs")
            avail = checked(available[oid])
            require(binding["entry"]["availability_content_sha256"] == avail["content_sha256"]
                and binding["entry"]["input_status"] == avail["input_status"] and binding["entry"]["reason"] == avail["reason"], "original availability was changed")
            stem = op["trading_date"] + "-" + op["symbol"]
            if stem not in entry_cache:
                qr, quotes = entry[stem + "-mbp-1"]
                sr, statuses = entry[stem + "-status"]
                entry_cache[stem] = None if quotes is None or statuses is None else digest({"quote_request": qr,
                    "quote_records": quotes, "status_request": sr, "status_records": statuses})
            require(binding["entry"]["execution_tape_content_sha256"] == entry_cache[stem], "original entry native pair differs")
            for resource, rid in window["resource_ids"].items():
                recipe = resources[rid]
                expected = stream_rows(archives["management"].read(recipe["path"]), recipe, window)
                require(binding["management_streams"][resource] == expected, "management lineage stream differs")
                counts["management_streams"] += 1
                counts["management_envelope_occurrences"] += expected["rows"]
            group_id = exit_ops[oid]["group_id"]
            if avail["input_status"] != "available":
                require(binding["exit"] is None and group_id is None, "unavailable entry rescued by exit source")
                counts["unavailable_entries"] += 1
            else:
                group = exit_groups[group_id]
                member = next(v for v in group["original_group"]["members"] if v["opportunity_id"] == oid)
                if group_id not in pair_cache:
                    payload = {}
                    for kind, rid in zip(("quote", "status"), group["resource_ids"]):
                        resource = exit_resources[rid]
                        rows = native_records(archives["exit"].read(resource["path"]), resource["request"], resource["source_tape"])
                        payload[kind + "_request"], payload[kind + "_records"] = resource["request"], rows
                    pair_cache[group_id] = {"execution_tape_content_sha256": digest(payload),
                        "quote_rows": len(payload["quote_records"]), "status_rows": len(payload["status_records"])}
                expected = {"group_id": group_id, "original_group": group["original_group"], "member": member, **pair_cache[group_id]}
                require(binding["exit"] == expected, "common source pair or original opportunity envelope differs")
                counts["available_entries"] += 1
            counts["opportunities"] += 1
        counts["exit_source_pairs"] = len(pair_cache)
    bindings = {b["opportunity_id"]: b for b in manifest["opportunities"]}
    contexts, transitions = [], []
    for path in plan["paths"]:
        for index, slot in enumerate(path["sessions"]):
            for ref in slot["opportunity_inputs"]:
                binding = bindings[ref["opportunity_id"]]
                context = {"window": binding["window"], "slot": slot, "source_decision": binding["source_decision"]}
                contexts.append({"path_id": path["path_id"], "session_id": slot["session_id"], "opportunity_id": ref["opportunity_id"],
                    "context_content_sha256": digest(context), "candidate_content_sha256": digest(binding["candidates"][slot["profile_id"]]),
                    "binding_content_sha256": binding["content_sha256"], "entry_input_status": ref["input_status"]})
            if index:
                transitions.append((path, path["sessions"][index - 1], slot))
    access = read(output / "context-access-verification.json")
    require(access["contexts"] == contexts and access["source_bindings_content_sha256"] == manifest["content_sha256"], "all original account contexts differ")
    require(len(manifest["carry_dependencies"]) == len(transitions), "carry dependency population differs")
    for dependency, (path, previous, slot) in zip(manifest["carry_dependencies"], transitions):
        require(dependency["path_id"] == path["path_id"] and dependency["previous_session_id"] == previous["session_id"]
            and dependency["next_session_id"] == slot["session_id"] and dependency["next_slot_content_sha256"] == slot["content_sha256"], "carry dependency skipped a slot")
        at = int(datetime.fromisoformat(slot["trading_date"] + "T07:00:00").replace(tzinfo=ZoneInfo("America/New_York")).timestamp()) * 10**9
        require(dependency["valuation_at_ns"] == at and dependency["previous_close_content_sha256"] is None, "carry mark time or claimed prior state differs")
        for key in ("share_unit_continuity", "valuation_quote_status", "expired_window_execution"):
            require(dependency[key].startswith("unavailable_no_"), "missing carry evidence silently inferred")
        require(dependency["flat_state_inferred"] is False and dependency["unchanged_units_inferred_from_split_prices"] is False
            and dependency["source_request_authorized"] is False, "carry authority or flatness inferred")
    counts.update(account_contexts=len(contexts), carry_dependencies=len(transitions))
    require({k: counts[k] for k in counts if k != "management_envelope_occurrences"} == {"activations": 192, "opportunities": 109,
        "available_entries": 86, "unavailable_entries": 23, "management_streams": 218, "entry_native_sources": 89,
        "exit_source_pairs": 41, "account_contexts": 744, "carry_dependencies": 348}, "original verified population differs")
    result = {"contract_id": ID, "verification_passed": True, "source_bindings_content_sha256": manifest["content_sha256"],
        "counts": counts, "stdlib_only": True, "account_or_fill_simulation_executed": False,
        "historical_runtime_authorized": False, "corporate_action_source_provenance_verified": False,
        "retrospective_inputs_read": False, "provider_calls": 0}
    return {**result, "content_sha256": digest(result)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding-root", type=Path, required=True)
    parser.add_argument("--expected-source-bindings-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    for name in ("scanner", "management", "exit", "entry-result", "entry-consumption"):
        parser.add_argument("--" + name + "-zip", type=Path, required=True)
    args = parser.parse_args()
    from run_offline_python_v13 import deny_external_io
    sys.addaudithook(deny_external_io)
    root = Path(__file__).resolve().parents[1]
    require(not args.output.resolve().is_relative_to(root), "independent evidence must not modify repository sources")
    paths = {name: getattr(args, name + "_zip") for name in ("scanner", "management", "exit", "entry_result", "entry_consumption")}
    result = verify(root, args.binding_root, paths, args.expected_source_bindings_sha256)
    with args.output.open("xb") as handle:
        handle.write(json.dumps(result, indent=2, sort_keys=True).encode() + b"\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
