"""Stdlib-only verification of causal waiting against immutable original tapes.

Reuses unchanged independent accounting checks. Independently reconstructs
reference eligibility and every waiting signal from original SIP/native rows.
This is not a second independent execution fill simulator.
"""
import argparse
from bisect import bisect_left, bisect_right
from copy import deepcopy
from decimal import Decimal, localcontext
import gzip
import hashlib
import io
import json
from pathlib import Path
import zipfile

import verify_sealed_historical_account_replay_v01 as parent
from verify_sealed_historical_account_risk_projection_v01 import verify_decimal_snapshot, _pinned_file
from verify_sealed_historical_source_binding_v01 import encoded, parse, ns, native_records
from verify_sealed_historical_management_fee_reconciliation_v01 import checked, read, require, digest

ID = "sealed-historical-account-exit-waiting-v0.1"
PARENT_RUNTIME = "5986950aab81652970a6318d93b7a6dd3b4b3384b8aa4a92d8578e3e985398e0"
PARENT_FILE = "e4b35e830e1934117ad2fa205b4777fd6f700e1bf5995cc9c65e4e4808dcf649"
PRE, TAIL, MINUTE = 100_000_000, 550_000_000, 60_000_000_000
UNDEF = 9_223_372_036_854_775_807


def evidence(item, resource):
    return {"resource": resource, **{k: v for k, v in item.items() if k != "record"},
        "record_content_sha256": hashlib.sha256(encoded(item["record"]) + b"\n").hexdigest()}


def eligible(row):
    require(row["z"] in {"A", "B", "C"} and type(row["c"]) is list
        and all(type(c) is str for c in row["c"]), "SIP eligibility schema differs")
    codes = {"": True, " ": True, "@": True, "A": True, "C": False, "D": True, "E": True,
        "F": True, "G": False, "H": False, "I": False, "K": True, "L": True, "M": False,
        "N": False, "O": True, "P": False, "Q": False, "R": False, "T": True, "U": False,
        "V": False, "W": False, "X": True, "Y": True, "Z": False, "4": False, "5": True,
        "6": True, "7": False, "9": False, "B": row["z"] == "C"}
    require(all(c in codes for c in row["c"]), "unknown trade condition")
    return all(codes[c] for c in row["c"] if c != "I")


class References:
    """Separate native-row implementation of the frozen capture eligibility."""
    def __init__(self, tape):
        self.tape = tape
        self.quotes = tape["quote_records"]
        self.statuses = tape["status_records"]
        self.times = [q["ts_recv_ns"] for q in self.quotes]
        self.status_times = [s["ts_recv_ns"] for s in self.statuses]

    def at(self, window, at):
        start, end = at - PRE, at + TAIL
        require(end < window["end_ns"], "reference tail outside original opportunity")
        for name in ("quote_request", "status_request"):
            r = self.tape[name]
            require(r["symbols"] == [window["opportunity"]["symbol"]]
                and r["trading_date"] == window["opportunity"]["trading_date"]
                and r["start_ns"] <= start < end < r["end_ns"], "reference source coverage differs")
        first = bisect_right(self.status_times, start) - 1
        require(first >= 0 and self.statuses[first]["is_trading"] in {"Y", "N"}, "quote/status input unavailable")
        stop = bisect_right(self.status_times, end)
        require(not any(s["is_trading"] == "~" for s in self.statuses[first + 1:stop]), "quote/status input unavailable")
        result = None
        for q in self.quotes[bisect_left(self.times, start):bisect_right(self.times, at)]:
            t = q["ts_recv_ns"]
            i = bisect_right(self.status_times, t) - 1
            if (i < 0 or self.status_times[i] == t or self.statuses[i]["is_trading"] == "~"
                    or not 0 < q["bid_px_nanos"] < q["ask_px_nanos"] < UNDEF
                    or q["bid_size"] <= 0 or q["ask_size"] <= 0):
                continue
            s = self.statuses[i]
            result = {k: q[k] for k in ("symbol", "ts_recv_ns", "sequence", "source_request_sha256",
                "source_record_index", "bid_size", "ask_size")}
            result.update(bid_price=format(Decimal(q["bid_px_nanos"]) / 10**9, "f"),
                ask_price=format(Decimal(q["ask_px_nanos"]) / 10**9, "f"), halted=s["is_trading"] != "Y",
                status_ts_recv_ns=s["ts_recv_ns"], status_record_index=i, status_action=s["action"])
        return None if result is None or result["halted"] else result


class OriginalEvidence:
    def __init__(self, root, manifest, paths, specs):
        self.manifest = {b["opportunity_id"]: b for b in manifest["opportunities"]}
        self.archives, self.cache, self.pairs = {}, {}, {}
        try:
            for key in ("management", "exit"):
                raw = paths[key].read_bytes()
                require((len(raw), hashlib.sha256(raw).hexdigest()) == (specs[key]["bytes"], specs[key]["sha256"]), "immutable source archive differs")
                archive = zipfile.ZipFile(io.BytesIO(raw))
                require(len(set(archive.namelist())) == len(archive.namelist()), "duplicate source member")
                self.archives[key] = archive
            base = root / "research/runtime"
            management = read(base / "sealed-historical-management-inputs-v0.1/management-input-manifest.json")
            exits = read(base / "sealed-historical-management-exit-inputs-v0.1/exit-input-manifest.json")
            self.resources = {r["resource_id"]: r for r in management["resources"]}
            self.groups = {g["original_group"]["group_id"]: g for g in exits["groups"]}
            self.exit_resources = {r["resource_id"]: r for r in exits["resources"]}
        except BaseException:
            self.close()
            raise

    def close(self):
        for archive in self.archives.values():
            archive.close()

    def __call__(self, oid):
        if oid in self.cache:
            return self.cache[oid]
        binding = self.manifest[oid]
        window = binding["window"]
        result = {"window": window}
        for name, resource in (("trades", "sip_transactions"), ("bars", "raw_sip_1m_bars")):
            recipe = self.resources[window["resource_ids"][resource]]
            raw = self.archives["management"].read(recipe["path"])
            require(hashlib.sha256(raw).hexdigest() == recipe["file_sha256"], "management source bytes differ")
            rows, segment_index = [], 0
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as handle:
                for ordinal, line in enumerate(handle):
                    row = parse(line)
                    require(encoded(row) + b"\n" == line, "noncanonical source row")
                    at = ns(row["t"])
                    if not window["start_ns"] <= at < window["end_ns"]:
                        continue
                    while ordinal >= recipe["segments"][segment_index]["composed_end_ordinal_exclusive"]:
                        segment_index += 1
                    segment = recipe["segments"][segment_index]
                    rows.append({"record": row, "timestamp_ns": at, "composed_record_ordinal": ordinal,
                        "source_artifact_id": segment["source_artifact_id"], "source_request_id": segment["source_request_id"],
                        "source_record_ordinal": segment["first_source_record_ordinal"] + ordinal - segment["composed_start_ordinal"]})
            require(binding["management_streams"][resource] == {"rows": len(rows),
                "sha256": hashlib.sha256(b"".join(encoded(r) + b"\n" for r in rows)).hexdigest()}, "bound management stream differs")
            result[name] = rows
        gid = binding["exit"]["group_id"]
        if gid not in self.pairs:
            tape = {}
            for kind, rid in zip(("quote", "status"), self.groups[gid]["resource_ids"]):
                resource = self.exit_resources[rid]
                tape[kind + "_records"] = native_records(self.archives["exit"].read(resource["path"]), resource["request"], resource["source_tape"])
                tape[kind + "_request"] = resource["request"]
            self.pairs[gid] = tape
        result["tape"] = self.pairs[gid]
        require(digest(result["tape"]) == binding["exit"]["execution_tape_content_sha256"], "bound exit tape differs")
        self.cache[oid] = result
        return result


def verify_waiting(runtime, resolve):
    snapshot = runtime["reconciliation_snapshot"]
    counts = {"waits": 0, "wait_submissions": 0, "wait_expiries": 0, "wait_supersessions": 0,
        "eligible_wait_prints_verified": 0}
    if snapshot is None:
        return counts
    entries = {j["execution_evidence"]["content_sha256"]: j["execution_evidence"]
        for j in snapshot["journal"] if j["fee_application"]["trade"]["side"] == "buy"}
    chains, active = {}, {}
    audit = snapshot.get("exit_wait_events", [])
    for event in audit:
        checked(event)
        eid, at, kind = event["entry_content_sha256"], event["timestamp_ns"], event["event_type"]
        entry = entries[eid]
        chain = chains.setdefault(eid, [])
        require(event["contract_id"] == ID and event["sequence"] == len(chain)
            and event["previous_event_sha256"] == (chain[-1]["content_sha256"] if chain else None), "waiting event chain differs")
        require(not chain or at >= chain[-1]["timestamp_ns"], "waiting clock reversed")
        chain.append(event)
        data = resolve(event["opportunity_id"])
        window, tape = data["window"], data["tape"]
        require(event["opportunity_id"] == entry["opportunity_id"] == window["opportunity"]["opportunity_id"]
            and entry["fill_time_ns"] < at < window["end_ns"], "waiting entry/window identity differs")
        # Waiting cannot receive fills: at a print, equal-time feedback is future.
        sells = [j["execution_evidence"] for j in snapshot["journal"]
            if j["fee_application"]["trade"]["side"] == "sell"
            and j["execution_evidence"]["entry_fill_id"] == entry["fill_id"]
            and j["execution_evidence"]["fill_time_ns"] < at]
        remaining = entry["quantity"] - sum(s["quantity"] for s in sells)
        target_quantity = entry["quantity"] // 2
        target_filled = sum(s["quantity"] for s in sells if s["reason"] == "first_target")
        stop = float(entry["fill_price"]) if target_quantity and target_filled == target_quantity else entry["initial_stop_price"]
        require(event["remaining_quantity"] == remaining > 0 and event["active_stop_price"] == stop, "waiting confirmed shares/stop differ")
        signal = checked(event["signal"])
        if kind == "wait_started":
            require(eid not in active and event["original_window_end_ns"] == window["end_ns"]
                and event["tape_content_sha256"] == digest(tape), "waiting start source differs")
            require(signal["decision_ts_ns"] == at and References(tape).at(window, at) is None, "waiting without missing fresh reference")
            active[eid] = {"start": event, "events": [], "data": data, "entry": entry,
                "remaining": remaining, "stop": stop, "target_quantity": target_quantity,
                "target": round(float(entry["fill_price"]) + 2 * (float(entry["fill_price"]) - entry["initial_stop_price"]), 10)}
            counts["waits"] += 1
        else:
            require(eid in active, "waiting event without origin")
            active[eid]["events"].append(event)
            require(event["original_signal_content_sha256"] == active[eid]["start"]["signal"]["content_sha256"], "waiting origin changed")
        before_orders = [e for e in runtime["events"] if e["event_type"] == "sell_submitted"
            and e["opportunity_id"] == event["opportunity_id"] and e["at_ns"] <= at
            and (kind == "wait_submitted" or e["at_ns"] < at)]
        require(event["target_attempted"] is any(e["reason"] == "first_target" for e in before_orders)
            and event["full_exit_attempted"] is any(e["reason"] != "first_target" for e in before_orders), "waiting attempt flags differ from actual orders")
        if kind in {"wait_submitted", "wait_expired"}:
            counts["eligible_wait_prints_verified"] += verify_episode(active.pop(eid), runtime, event)
            counts["wait_submissions" if kind == "wait_submitted" else "wait_expiries"] += 1
        elif kind == "wait_superseded":
            counts["wait_supersessions"] += 1
        else:
            require(kind == "wait_started", "unknown waiting event")
    for wait in active.values():
        require(runtime["failure"] is not None, "unfinished wait requires preserved input failure or expiry")
        counts["eligible_wait_prints_verified"] += verify_episode(wait, runtime, None)
    delayed_orders = {e["order"]["order_id"] for e in audit if e["event_type"] == "wait_submitted"}
    require(len(delayed_orders) == counts["wait_submissions"], "duplicate waiting submission")
    return counts


def verify_episode(wait, runtime, finish):
    start, data, entry = wait["start"], wait["data"], wait["entry"]
    origin = start["signal"]
    window, reference = data["window"], References(data["tape"])
    trades = data["trades"]
    by_ordinal = {r["composed_record_ordinal"]: i for i, r in enumerate(trades)}
    index = by_ordinal[origin["trade_evidence"]["composed_record_ordinal"]]
    row = trades[index]
    require(origin["trade_evidence"] == evidence(row, "sip_transactions") and eligible(row["record"]), "waiting original SIP witness differs")
    identity = {k: entry[k] for k in ("opportunity_id", "path_id", "session_id", "scenario_id")}
    identity["entry_content_sha256"] = entry["content_sha256"]
    def red_at(at):
        for b in data["bars"]:
            when = b["timestamp_ns"] + MINUTE
            if entry["fill_time_ns"] < when <= min(at, window["signal_end_ns"]) and b["record"]["c"] < b["record"]["o"]:
                return {"signal_ts_ns": when, "evidence": evidence(b, "raw_sip_1m_bars")}
        return None
    risk_locked = any(e["event_type"] == "account_locked" and e.get("flatten_required")
        and ns(e["at"]) <= start["timestamp_ns"] for e in runtime["reconciliation_snapshot"]["ledger"]["events"])
    def reason_at(item, latched):
        if float(item["record"]["p"]) <= wait["stop"]:
            return "breakeven_stop" if wait["stop"] == float(entry["fill_price"]) else "initial_stop"
        if latched in {"initial_stop", "breakeven_stop"}:
            return latched
        if risk_locked:
            return "account_risk_flatten"
        if latched is not None:
            return latched
        return "first_red_candle" if red_at(item["timestamp_ns"]) is not None else None
    def signal_for(item, reason):
        return parent.seal({**identity, "decision_ts_ns": item["timestamp_ns"], "reason": reason,
            "quantity": wait["target_quantity"] if reason == "first_target" else wait["remaining"],
            "trade_evidence": evidence(item, "sip_transactions"),
            "red_signal": red_at(item["timestamp_ns"]) if reason == "first_red_candle" else None})
    reason = reason_at(row, None)
    if reason is None:
        require(not start["target_attempted"] and wait["target_quantity"] > 0
            and float(row["record"]["p"]) >= wait["target"], "waiting target was not triggered")
        reason = "first_target"
    require(origin == signal_for(row, reason), "waiting original signal is not causal")
    signal, expected_updates, count, first_fresh = origin, [], 0, None
    through = (finish["timestamp_ns"] if finish else runtime["reconciliation_snapshot"]["management"]["clock_ns"])
    progress = next(p["rows"] for p in runtime["processed_streams"]
        if p["opportunity_id"] == entry["opportunity_id"] and p["resource"] == "sip_transactions")
    engine = runtime["reconciliation_snapshot"]["management"]
    failed_proposal = (engine["outstanding_intent"] if finish is None and engine is not None else None)
    failed_proposal = failed_proposal if failed_proposal and "waiting_signal" in failed_proposal else None
    if failed_proposal:
        require(runtime["failure"]["stage"] == "executable_exit_evidence"
            and progress < len(trades) and failed_proposal["trade_evidence"] == evidence(trades[progress], "sip_transactions"), "failed waiting proposal source differs")
        progress += 1  # Observed valid print; submission failure precedes cursor advancement.
    for item in trades[index + 1:progress]:
        at = item["timestamp_ns"]
        if at > through or at + TAIL >= window["end_ns"]:
            break
        if not eligible(item["record"]):
            continue
        count += 1
        new_reason = reason_at(item, None if signal["reason"] == "first_target" else signal["reason"])
        if new_reason and new_reason != signal["reason"]:
            new_signal = signal_for(item, new_reason)
            expected_updates.append((at, signal["content_sha256"], new_signal))
            signal = new_signal
        ref = reference.at(window, at)
        if ref is not None:
            first_fresh = (item, ref)
            break
    updates = [(e["timestamp_ns"], e["superseded_signal_content_sha256"], e["signal"])
        for e in wait["events"] if e["event_type"] == "wait_superseded"]
    require(updates == expected_updates, "waiting reason priority or supersession witness differs")
    if (finish and finish["event_type"] == "wait_submitted") or failed_proposal:
        stamp = finish["timestamp_ns"] if finish else failed_proposal["decision_ts_ns"]
        require(first_fresh is not None and first_fresh[0]["timestamp_ns"] == stamp, "not first eligible fresh waiting print")
        item, ref = first_fresh
        proposal = {k: deepcopy(v) for k, v in signal.items() if k != "content_sha256"}
        proposal.update(decision_ts_ns=item["timestamp_ns"], trade_evidence=evidence(item, "sip_transactions"),
            waiting_signal=signal, original_waiting_signal_content_sha256=origin["content_sha256"])
        proposal = parent.seal(proposal)
        if failed_proposal:
            require(failed_proposal == proposal and not engine["pending_order"], "failed waiting proposal was not preserved")
            require(not any(e["event_type"] == "sell_submitted" and e["order"]["order_id"] == "exit-" + proposal["content_sha256"]
                for e in runtime["events"]), "failed proposal consumed an order")
            return count
        require(finish["signal"] == signal and finish["submission_intent"] == proposal
            and finish["reference"] == ref and finish["tape_content_sha256"] == digest(data["tape"]), "waiting submission evidence differs")
        order = finish["order"]
        require(order["order_id"] == "exit-" + proposal["content_sha256"]
            and order["decision_ts_ns"] == item["timestamp_ns"] and order["quantity"] == signal["quantity"], "waiting order identity differs")
        require(any(e["event_type"] == "sell_submitted" and e["order"] == order and e["reason"] == signal["reason"]
            for e in runtime["events"]), "waiting order is absent from chronological events")
    else:
        require(first_fresh is None, "eligible waiting submission was omitted")
        if finish:
            require(finish["timestamp_ns"] + TAIL >= window["end_ns"]
                and finish["original_window_end_ns"] == window["end_ns"] and finish["signal"] == signal, "waiting expiry differs")
        engine = runtime["reconciliation_snapshot"]["management"]
        require(engine is not None and engine["outstanding_intent"] == signal and not engine["pending_order"], "unsubmitted waiting state was not preserved")
    return count


def verify(root, runtime_root, binding_root, parent_runtime_root, expected_runtime_sha, paths):
    contract = read(root / f"research/strategy/{ID}.json")
    require(contract["contract_id"] == ID and contract["parent_runtime_content_sha256"] == PARENT_RUNTIME
        and contract["parent_runtime_file_sha256"] == PARENT_FILE, "waiting parent identity differs")
    for path, sha in {**contract["frozen_parent_file_sha256"], **contract["implementation_file_sha256"]}.items():
        require(hashlib.sha256((root / path).read_bytes()).hexdigest() == sha, "frozen implementation/parent differs: " + path)
    registration_root = root / f"research/runtime/{ID}"
    registration = read(registration_root / "freeze-manifest.json")
    require(registration["contract_id"] == ID and registration["contract_content_sha256"] == contract["content_sha256"], "registration identity differs")
    for name, spec in registration["file_inventory"].items():
        value = _pinned_file(registration_root / name, spec["sha256"])
        require((registration_root / name).stat().st_size == spec["bytes"]
            and value["content_sha256"] == registration["document_content_sha256"][name], "registration inventory differs")
    manifest = _pinned_file(binding_root / "source-bindings.json", parent.BOUND_FILE)
    require(manifest["content_sha256"] == parent.BOUND, "original binding differs")
    old = _pinned_file(parent_runtime_root / "account-replay.json", PARENT_FILE)
    require(old["content_sha256"] == PARENT_RUNTIME, "parent runtime differs")
    frozen = read(runtime_root / "freeze-manifest.json")
    parent.boundaries(frozen)
    require(frozen["contract_id"] == ID and frozen["contract_content_sha256"] == contract["content_sha256"]
        and set(frozen["file_inventory"]) == {"account-replay.json"}, "runtime freeze scope differs")
    spec = frozen["file_inventory"]["account-replay.json"]
    result = _pinned_file(runtime_root / "account-replay.json", spec["sha256"])
    require((runtime_root / "account-replay.json").stat().st_size == spec["bytes"], "runtime byte length differs")
    require(result["content_sha256"] == expected_runtime_sha == frozen["document_content_sha256"]["account-replay.json"], "runtime commitment differs")
    require(result["contract_id"] == ID and result["parent_runtime_content_sha256"] == PARENT_RUNTIME
        and result["registration_freeze_content_sha256"] == registration["content_sha256"], "runtime authority differs")
    require(result["source_bindings_content_sha256"] == parent.BOUND and result["source_archives"] == manifest["source_archives"], "source authority differs")
    parent.boundaries(result)
    programs = read(root / f"research/runtime/{parent.ID}/source-programs.json")["programs"]
    require(len(programs) == len(result["paths"]) == len(old["paths"]) == 12, "all original paths required")
    counts = []
    sources = OriginalEvidence(root, manifest, paths, contract["source_archives"])
    try:
        with localcontext() as context:
            context.prec = 60
            for program, before, after in zip(programs, old["paths"], result["paths"]):
                totals = {"path_id": after["path_id"], **parent.verify_path(program, after, manifest)}
                # All parent paths reached this exact unsubmitted signal before failing.
                prior = before["sessions"][0]["runtime"]
                current = after["sessions"][0]["runtime"]
                require(current["events"][:len(prior["events"])] == prior["events"], "pre-wait parent event prefix changed")
                audit = current["reconciliation_snapshot"]["exit_wait_events"]
                require(audit[0]["signal"] == prior["reconciliation_snapshot"]["management"]["outstanding_intent"], "parent original exit signal changed")
                for pair in after["sessions"]:
                    runtime = pair["runtime"]
                    if runtime["reconciliation_snapshot"] is not None:
                        verify_decimal_snapshot(runtime["reconciliation_snapshot"])
                    for key, count in verify_waiting(runtime, sources).items():
                        totals[key] = totals.get(key, 0) + count
                counts.append(totals)
    finally:
        sources.close()
    totals = {k: sum(c[k] for c in counts) for k in counts[0] if k != "path_id"}
    require((totals["sessions"], totals["opportunity_references"], totals["unavailable_references"]) == (360, 744, 162), "original population differs")
    return parent.seal({"contract_id": ID, "verification_passed": True,
        "runtime_content_sha256": expected_runtime_sha, "source_bindings_content_sha256": parent.BOUND,
        "parent_runtime_content_sha256": PARENT_RUNTIME, "registration_freeze_content_sha256": registration["content_sha256"],
        "paths": counts, "totals": totals, "unchanged_parent_chronology_and_account_checks_passed": True,
        "original_waiting_signals_and_first_eligible_fresh_prints_verified": True,
        "pre_wait_parent_event_prefix_unchanged": True, "independent_fill_simulation": False,
        "financial_metrics_eligible": False, "account_backtest_complete": False, "retrospective_labels_opened": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("runtime-root", "binding-root", "parent-runtime-root", "output", "management-zip", "exit-zip"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--expected-runtime-sha256", required=True)
    args = parser.parse_args()
    import sys
    from run_offline_python_v13 import deny_external_io
    sys.addaudithook(deny_external_io)
    result = verify(Path(__file__).resolve().parents[1], args.runtime_root, args.binding_root,
        args.parent_runtime_root, args.expected_runtime_sha256, {"management": args.management_zip, "exit": args.exit_zip})
    with args.output.open("xb") as handle:
        handle.write((json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
        handle.flush()
        __import__("os").fsync(handle.fileno())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
