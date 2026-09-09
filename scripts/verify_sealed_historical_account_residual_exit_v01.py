"""Stdlib-only bounded residual-exit verification against original tapes.

Retains frozen accounting and waiting checks, with an explicit two-terminal
ceiling plus independent acknowledgement, residual-share and first-print checks.
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

ID = "sealed-historical-account-residual-exit-v0.1"
WAITING_ID = "sealed-historical-account-exit-waiting-v0.1"
PARENT_RUNTIME = "7b0a0edd58ea285613a01047963bccb82a8a8df4ef6192f2437da222406d7edb"
PARENT_FILE = "b36b14350d1cb91c173122aee77e7892050546af52cd03253b587c54c288219e"
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
        require(event["contract_id"] == WAITING_ID and event["sequence"] == len(chain)
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
    if "residual_exit" in origin:
        identity["residual_exit"] = deepcopy(origin["residual_exit"])
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
    reason = (terminal_reason(entry, data, runtime, row) if "residual_exit" in origin else reason_at(row, None))
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


from verify_sealed_historical_account_continuity_v01 import account_state, priority
from verify_sealed_historical_account_state_producer_v01 import public_collections, ready, exact_money, checked_tree
from verify_sealed_historical_management_fee_reconciliation_v01 import number
BOUND = parent.BOUND
boundaries, source_for_events = parent.boundaries, parent.source_for_events
seal = parent.seal


def verify_events(source, runtime):
    snapshot = runtime["reconciliation_snapshot"]
    if snapshot is None:
        require(not runtime["events"], "blocked opening executed events")
        return 0
    journal = snapshot["journal"]
    cash = Decimal(str(snapshot["ledger"]["account"]["starting_buying_power"]))
    max_loss = Decimal(str(snapshot["ledger"]["account"]["starting_equity"])) * Decimal(".01")
    pending, active, quantity, locked = None, None, 0, False
    previous, last_clock, consumed, decisions = None, (-1, -1), set(), []
    ordered = sorted(source["opportunities"], key=priority)
    expected_ids = [i["position"]["entry_input"]["window"]["opportunity"]["opportunity_id"] for i in ordered]
    source_by_id = {i["position"]["entry_input"]["window"]["opportunity"]["opportunity_id"]: i for i in ordered}
    exit_orders, terminal, targets, used_liquidity = {}, {}, set(), set()
    campaign_entries = {}
    arrival_ms, cancel_ms, ack_ms = {"l1-conservative-v0.1": (100, 250, 100), "l1-stress-v0.1": (250, 150, 150)}[snapshot["identity"]["scenario_id"]]
    def lifecycle(order, at):
        require(order["arrival_ts_ns"] == at + arrival_ms * 1_000_000
            and order["cancel_requested_ts_ns"] == at + (arrival_ms + cancel_ms) * 1_000_000
            and order["cancel_ack_ts_ns"] == at + (arrival_ms + cancel_ms + ack_ms) * 1_000_000,
            "frozen execution latency changed")
    def view():
        return {"cash_usd": exact_money(cash), "confirmed_quantity": quantity,
            "capacity_reserved": pending is not None or active is not None, "account_locked": locked}
    for index, event in enumerate(runtime["events"]):
        checked(event)
        require(event["sequence"] == index and event["previous_event_sha256"] == previous, "event hash chain differs")
        previous = event["content_sha256"]
        clock = (event["at_ns"], event["phase"])
        require(clock >= last_clock, "global account event clock reversed")
        last_clock = clock
        at, phase, kind, oid = *clock, event["event_type"], event["opportunity_id"]
        require(oid in source_by_id, "foreign opportunity event")
        op = source_by_id[oid]["position"]["entry_input"]["window"]["opportunity"]
        if kind == "opportunity_disposition":
            require(phase == 1 and at == op["decision_ts_ns"], "decision time differs")
            require(event["account_before"] == view(), "decision saw incorrect cash, inventory, reservation or lock")
            decisions.append(oid)
            require(decisions == expected_ids[:len(decisions)], "frozen causal scarcity order differs")
            disposition = event["disposition"]
            if view()["capacity_reserved"]:
                require(disposition == "blocked_capacity", "reserved account was reused")
            elif locked:
                require(disposition == "blocked_account_lock", "locked account submitted")
            else:
                count = campaign_entries.get(op["activation_id"], 0)
                if count >= 2:
                    require(disposition == "blocked_campaign_entry_limit", "third campaign entry not blocked")
                else:
                    require(disposition in {"entry_submitted", "no_whole_share_capacity"}, "unsupported entry disposition")
            if disposition == "entry_submitted":
                require(pending is None and active is None and not locked, "overlapping or locked submission")
                order = event["order"]
                lifecycle(order, at)
                require(set(order) == {"order_id", "quantity", "limit_price", "decision_ts_ns", "arrival_ts_ns", "cancel_requested_ts_ns", "cancel_ack_ts_ns", "capture_content_sha256"}, "entry exposes private future execution")
                require(order["decision_ts_ns"] == at < order["arrival_ts_ns"] <= order["cancel_requested_ts_ns"] < order["cancel_ack_ts_ns"], "entry order lifecycle differs")
                pending = {"oid": oid, "order": order, "filled": 0}
            else:
                require(event["order"] is None, "rejected opportunity invented order")
        elif kind in {"entry_fill_confirmed", "sell_fill_confirmed"}:
            require(phase == 3 and event["journal_index"] not in consumed, "duplicate or early fill feedback")
            j = event["journal_index"]
            require(j == len(consumed) and j < len(journal), "missing or reordered confirmed fill")
            consumed.add(j)
            row = journal[j]
            trade, evidence = row["fee_application"]["trade"], row["execution_evidence"]
            require(at == trade["timestamp_ns"] == row["known_at_ns"], "fill exposed outside actual feedback clock")
            require(evidence["activation_id"] == op["activation_id"] if kind == "entry_fill_confirmed" else row["activation_id"] == op["activation_id"], "fill belongs to another activation")
            if kind == "entry_fill_confirmed":
                require(trade["side"] == "buy" and active is None and pending is not None and pending["oid"] == oid, "entry without reservation")
                require(pending["order"]["arrival_ts_ns"] <= at < pending["order"]["cancel_ack_ts_ns"], "entry outside lifecycle")
                require(trade["order_id"] == pending["order"]["order_id"] and 0 < trade["quantity"] <= pending["order"]["quantity"], "entry quantity/order differs")
                count = campaign_entries.get(op["activation_id"], 0)
                require(count < 2 and evidence["entry_role"] == ("starter" if count == 0 else "reentry"), "invalid campaign entry role/count")
                campaign_entries[op["activation_id"]] = count + 1
                quantity, active, pending["filled"] = trade["quantity"], oid, trade["quantity"]
            else:
                require(trade["side"] == "sell" and active == oid and trade["order_id"] in exit_orders, "sell without active order")
                order = exit_orders[trade["order_id"]]
                require(order["arrival_ts_ns"] <= at < order["cancel_ack_ts_ns"] and 0 < trade["quantity"] <= min(quantity, order["quantity"]), "sell exceeds reservation or lifecycle")
                liquidity = (evidence["source_request_sha256"], evidence["source_record_index"])
                require(liquidity not in used_liquidity, "displayed liquidity reused")
                used_liquidity.add(liquidity)
                quantity -= trade["quantity"]
            cash = number(row["cash_after"])
            net, high = number(row["net_realized_after"]), number(row["net_high_water_after"])
            locked = locked or net <= -max_loss or (high > 0 and net <= high / 2)
            require(event["account_after"] == view(), "fill public account projection differs")
        elif kind == "entry_cancel_acknowledged":
            require(phase == 3 and pending is not None and pending["oid"] == oid, "entry ack has no pending order")
            require(at == pending["order"]["cancel_ack_ts_ns"] and event["order_id"] == pending["order"]["order_id"], "early or foreign entry ack")
            require(event["confirmed_quantity"] == pending["filled"] and event["cancelled_quantity"] == pending["order"]["quantity"] - pending["filled"], "entry cancel quantity differs")
            pending = None
        elif kind == "sell_submitted":
            order = event["order"]
            lifecycle(order, at)
            require(phase == 2 and active == oid and at == order["decision_ts_ns"], "sell decision before confirmed entry or wrong phase")
            require(all(o["cancel_ack_ts_ns"] < at for o in exit_orders.values()), "sell reservation reused before acknowledgment")
            require(order["order_id"] not in exit_orders and 0 < order["quantity"] <= quantity, "invalid sell reservation")
            if event["reason"] == "first_target":
                require(oid not in targets, "target attempt retried")
                targets.add(oid)
            else:
                require(terminal.get(oid, 0) < 2 and order["quantity"] == quantity, "terminal attempt budget or quantity differs")
                terminal[oid] = terminal.get(oid, 0) + 1
            if event["reason"] == "account_risk_flatten":
                require(locked, "risk flatten without known account lock")
            end = source_by_id[oid]["position"]["entry_input"]["window"]["end_ns"]
            require(at < order["arrival_ts_ns"] <= order["cancel_requested_ts_ns"] < order["cancel_ack_ts_ns"] < end, "sell extends original window")
            exit_orders[order["order_id"]] = order
        elif kind == "capacity_released":
            require(phase in (3, 4) and active == oid and quantity == 0 and pending is None, "capacity released with shares or entry reservation")
            require(all(o["cancel_ack_ts_ns"] <= at for o in exit_orders.values()), "capacity released before sell acknowledgment")
            active = None
            require(event["account_after"] == view(), "released account view differs")
        else:
            raise ValueError("unknown scheduler event")
    require(consumed == set(range(len(journal))), "journal fill not exposed by scheduler")
    if runtime["complete_streams_verified"]:
        require(decisions == expected_ids and runtime["failure"] is None, "complete session missed decisions")
    return len(consumed)


def verify_path(program, result, manifest):
    checked(program)
    checked_tree(result)
    boundaries(result)
    require(program["contract_id"] == result["contract_id"] == parent.ID, "contract identity differs")
    require(program["input_scope"] == "authenticated_original_historical_sources", "source scope differs")
    require(program["source_bindings_content_sha256"] == BOUND, "bound manifest reference differs")
    originals = {p["path_id"]: p for p in manifest["paths"]}
    require(program["path_id"] == result["path_id"] and program["slots"] == originals[result["path_id"]]["sessions"], "original path catalog differs")
    require(result["program_content_sha256"] == program["content_sha256"], "program pin differs")
    require(len(program["slots"]) == len(program["sessions"]) == len(result["sessions"]) == result["session_count"] == 30, "all original slots required")
    bindings = {b["opportunity_id"]: b for b in manifest["opportunities"]}
    dependencies = {d["next_session_id"]: d for d in manifest["carry_dependencies"]}
    capital = "30000.00" if program["slots"][0]["account_key"] == "main_account" else "2000.00"
    opening = {"equity_usd": capital, "buying_power_usd": capital, "cumulative_realized_pnl_usd": "0.00",
        "cumulative_fees_usd": "0.00", "positions": [], "pending_orders": [], "campaigns": [], "unresolved_inputs": []}
    require(result["initial_account_state"] == opening and result["seed_application_count"] == 1, "once-only seed differs")
    previous, counts = None, {"sessions": 0, "executed_sessions": 0, "blocked_sessions": 0, "input_failure_sessions": 0,
        "unavailable_references": 0, "opportunity_references": 0, "events": 0, "confirmed_fills": 0,
        "confirmed_entries": 0, "confirmed_sells": 0, "completed_streams": 0}
    for index, (slot, source, pair) in enumerate(zip(program["slots"], program["sessions"], result["sessions"])):
        runtime, close = checked(pair["runtime"]), checked(pair["close"])
        boundaries(runtime)
        boundaries(close)
        require(source == {"session_id": slot["session_id"], "opportunities": slot["opportunity_inputs"]}, "original session references differ")
        require(runtime["contract_id"] == close["contract_id"] == parent.ID and runtime["path_id"] == close["path_id"] == result["path_id"], "runtime identity differs")
        require(runtime["session_id"] == close["session_id"] == slot["session_id"], "session identity differs")
        require(close["trading_date"] == slot["trading_date"] and close["session_index"] == index and close["seed_applied"] is (index == 0), "date/index/seed differs")
        require(runtime["source_slot_content_sha256"] == close["source_slot_content_sha256"] == slot["content_sha256"], "slot pin differs")
        require(close["previous_close_content_sha256"] == previous and close["source_runtime_content_sha256"] == runtime["content_sha256"], "close chain differs")
        require(runtime["session_program_sha256"] == digest(source) and runtime["opening_account_state_sha256"] == digest(opening), "source or preceding account state differs")
        require(runtime["source_bindings_content_sha256"] == BOUND, "source binding pin differs")
        snapshot, failure, blocked = runtime["reconciliation_snapshot"], runtime["failure"], runtime["blocked_before_execution"]
        projection_failure = failure is not None and failure["kind"] == "opening_ledger_projection_unavailable"
        require(blocked == (not ready(opening) or projection_failure), "opening readiness differs")
        if projection_failure:
            require(ready(opening) and any(Decimal(str(float(number(opening[k])))) != number(opening[k]) for k in ("equity_usd", "buying_power_usd")), "unsupported opening projection failure")
        require(runtime["historical_session_scheduler_executed"] == (snapshot is not None), "execution marker differs")
        counts["confirmed_fills"] += verify_events(source_for_events(source, slot, bindings), runtime)
        counts["events"] += len(runtime["events"])
        seen = {e["opportunity_id"]: e["disposition"] for e in runtime["events"] if e["event_type"] == "opportunity_disposition"}
        dispositions = [{**r, "disposition": "unavailable_input" if r["input_status"] == "unavailable" else
            seen.get(r["opportunity_id"], "blocked_prior_state" if blocked else "unprocessed_available_input")}
            for r in slot["opportunity_inputs"]]
        require(runtime["opportunity_dispositions"] == dispositions, "lost or invented opportunity disposition")
        gaps = [{"kind": d["disposition"], "opportunity_id": d["opportunity_id"], "availability_content_sha256": d["availability_content_sha256"],
            "reason": d["reason"], "blocks_next_session": d["disposition"] != "unavailable_input"} for d in dispositions
            if d["disposition"] in {"unavailable_input", "unprocessed_available_input", "blocked_prior_state"}]
        failures = [] if failure is None else [failure]
        if blocked:
            require(snapshot is None and not runtime["events"] and not runtime["processed_streams"] and runtime["unconfirmed_entry_order"] is None, "blocked state executed")
            expected = deepcopy(opening)
            expected["unresolved_inputs"] += gaps + failures + [{"kind": "preceding_state_blocks_execution", "blocks_next_session": True,
                "previous_close_content_sha256": previous}]
            net = gross = charged = Decimal(0)
        else:
            account_state(snapshot)
            require(number(str(snapshot["ledger"]["account"]["starting_equity"])) == number(opening["equity_usd"])
                and number(str(snapshot["ledger"]["account"]["starting_buying_power"])) == number(opening["buying_power_usd"]), "daily capital reset")
            positions, pending, extra = public_collections(snapshot)
            if runtime["unconfirmed_entry_order"] is not None:
                pending.append(runtime["unconfirmed_entry_order"])
            gross, net = number(snapshot["exact_account"]["gross_realized_pnl"]), number(snapshot["exact_account"]["net_realized_pnl"])
            charged = number(snapshot["fee_book"]["fees"]["total_charged"])
            expected = {"equity_usd": None if positions or pending else exact_money(number(opening["equity_usd"]) + net),
                "buying_power_usd": exact_money(number(snapshot["exact_account"]["remaining_buying_power"])),
                "cumulative_realized_pnl_usd": exact_money(number(opening["cumulative_realized_pnl_usd"]) + net),
                "cumulative_fees_usd": exact_money(number(opening["cumulative_fees_usd"]) + charged),
                "positions": positions, "pending_orders": pending, "campaigns": opening["campaigns"] + snapshot["ledger"]["campaigns"],
                "unresolved_inputs": opening["unresolved_inputs"] + gaps + failures + extra}
            trades = [r["fee_application"]["trade"] for r in snapshot["journal"]]
            counts["confirmed_entries"] += sum(t["side"] == "buy" for t in trades)
            counts["confirmed_sells"] += sum(t["side"] == "sell" for t in trades)
        require(close["account_state"] == expected and close["next_session_flat_cash_execution_ready"] == ready(expected), "derived exact close differs")
        for key, value in (("session_gross_realized_pnl_usd", gross), ("session_net_realized_pnl_usd", net), ("session_fees_usd", charged)):
            require(runtime[key] == exact_money(value), "session delta differs")
        complete = snapshot is not None and failure is None
        require(runtime["complete_streams_verified"] == complete, "stream completion flag differs")
        progress = runtime["processed_streams"]
        require(len({(p["opportunity_id"], p["resource"]) for p in progress}) == len(progress), "duplicate stream progress")
        for row in progress:
            require(row["opportunity_id"] in {r["opportunity_id"] for r in source["opportunities"] if r["input_status"] == "available"}, "foreign or unavailable stream")
            commitment = bindings[row["opportunity_id"]]["management_streams"][row["resource"]]
            require(type(row["rows"]) is int and 0 <= row["rows"] <= commitment["rows"], "stream progress exceeds registered source")
            if complete:
                require({k: row[k] for k in ("rows", "sha256")} == commitment, "complete stream differs from original binding")
        if complete:
            require(len(progress) == 2 * sum(r["input_status"] == "available" for r in source["opportunities"]), "complete session omitted original streams")
            counts["completed_streams"] += len(progress)
        active = runtime["active_original_window"]
        if active is not None:
            oid = active["opportunity"]["opportunity_id"]
            require(active == bindings[oid]["window"] and snapshot is not None and snapshot["management"] is not None, "active original window differs")
            require(snapshot["management"]["entry"]["opportunity_id"] == oid, "active window detached from retained management")
        elif snapshot is not None:
            require(snapshot["management"] is None, "active original window lost")
        dependency = dependencies.get(slot["session_id"])
        carry = None if dependency is None else seal({"dependency": dependency,
            "previous_close_content_sha256": previous, "opening_account_state_sha256": digest(opening),
            "status": "blocked_preserved_prior_state" if blocked else "flat_cash_no_share_mark_or_adjustment_required",
            "prior_state_preserved": True, "new_source_evidence_inferred": False})
        require(runtime["carry_dependency"] == carry, "carry source/state dependency differs")
        status = "blocked_prior_state" if blocked else "input_failure" if failure else "original_window_exhausted_with_unresolved_state" if not ready(expected) else "flat_complete_with_unavailable_inputs" if gaps else "flat_complete"
        require(runtime["status"] == status, "session completion status differs")
        counts["sessions"] += 1
        counts["executed_sessions"] += not blocked
        counts["blocked_sessions"] += blocked
        counts["input_failure_sessions"] += failure is not None
        counts["unavailable_references"] += sum(r["input_status"] == "unavailable" for r in source["opportunities"])
        counts["opportunity_references"] += len(dispositions)
        opening, previous = expected, close["content_sha256"]
    require(result["last_close_content_sha256"] == previous, "final close differs")
    require(result["path_complete"] == all(p["runtime"]["status"] == "flat_complete" for p in result["sessions"]), "path completion differs")
    return counts



def terminal_reason(entry, data, runtime, through):
    """Reconstruct the frozen terminal latch using only prior causal evidence."""
    snapshot = runtime["reconciliation_snapshot"]
    sells = [j["execution_evidence"] for j in snapshot["journal"]
        if j["fee_application"]["trade"]["side"] == "sell"
        and j["execution_evidence"]["entry_fill_id"] == entry["fill_id"]]
    locks = [ns(e["at"]) for e in snapshot["ledger"]["events"]
        if e["event_type"] == "account_locked" and e.get("flatten_required")]
    red_times = [b["timestamp_ns"] + MINUTE for b in data["bars"]
        if entry["fill_time_ns"] < b["timestamp_ns"] + MINUTE <= data["window"]["signal_end_ns"]
        and b["record"]["c"] < b["record"]["o"]]
    latched = None
    for item in data["trades"]:
        at = item["timestamp_ns"]
        if item["composed_record_ordinal"] > through["composed_record_ordinal"]:
            break
        if at <= entry["fill_time_ns"]:
            continue
        if locks and min(locks) < at and latched not in {"initial_stop", "breakeven_stop"}:
            latched = "account_risk_flatten"
        if not eligible(item["record"]):
            continue
        target = entry["quantity"] // 2
        target_sold = sum(s["quantity"] for s in sells if s["reason"] == "first_target" and s["fill_time_ns"] < at)
        breakeven = bool(target and target_sold == target)
        stop = float(entry["fill_price"]) if breakeven else entry["initial_stop_price"]
        if float(item["record"]["p"]) <= stop and latched not in {"initial_stop", "breakeven_stop"}:
            latched = "breakeven_stop" if breakeven else "initial_stop"
        elif latched is None and red_times and min(red_times) <= at:
            latched = "first_red_candle"
    return latched


def verify_residual(runtime, resolve):
    snapshot = runtime["reconciliation_snapshot"]
    counts = {"residual_ready": 0, "residual_proposals": 0, "residual_submissions": 0,
        "residual_expiries": 0, "residual_budget_exhaustions": 0}
    if snapshot is None:
        return counts
    entries = {j["execution_evidence"]["content_sha256"]: j["execution_evidence"]
        for j in snapshot["journal"] if j["fee_application"]["trade"]["side"] == "buy"}
    by_oid = {e["opportunity_id"]: e for e in entries.values()}
    orders = {}
    for event in runtime["events"]:
        if event["event_type"] == "sell_submitted":
            orders.setdefault(event["opportunity_id"], []).append(event)
    sells = [j["execution_evidence"] for j in snapshot["journal"]
        if j["fee_application"]["trade"]["side"] == "sell"]
    def sold(entry, at):
        return [s for s in sells if s["entry_fill_id"] == entry["fill_id"] and s["fill_time_ns"] <= at]
    def quantity(entry, at):
        return entry["quantity"] - sum(s["quantity"] for s in sold(entry, at))
    def cancel(entry, order, ack):
        checked(ack)
        fills = [s for s in sold(entry, order["cancel_ack_ts_ns"]) if s["order_id"] == order["order_id"]]
        filled = sum(s["quantity"] for s in fills)
        require(ack["event_type"] == "sell_cancel_acknowledged" and ack["order_id"] == order["order_id"]
            and ack["timestamp_ns"] == order["cancel_ack_ts_ns"]
            and ack["cancelled_quantity"] == order["quantity"] - filled > 0
            and ack["execution_status"] == ("partially_filled_cancelled" if filled else "cancelled_unfilled"),
            "residual cancellation witness differs")
    chains, states = {}, {}
    for event in snapshot.get("exit_residual_events", []):
        checked(event)
        eid, at, kind = event["entry_content_sha256"], event["timestamp_ns"], event["event_type"]
        require(eid in entries, "residual event has no confirmed entry")
        entry = entries[eid]
        chain = chains.setdefault(eid, [])
        require(event["contract_id"] == ID and event["opportunity_id"] == entry["opportunity_id"]
            and event["sequence"] == len(chain) and event["previous_event_sha256"] == (chain[-1]["content_sha256"] if chain else None)
            and (not chain or at >= chain[-1]["timestamp_ns"]), "residual event chain differs")
        chain.append(event)
        data = resolve(entry["opportunity_id"])
        window = data["window"]
        require(entry["fill_time_ns"] < at < window["end_ns"], "residual clock outside entry/window")
        remaining = quantity(entry, at - int(kind in {"residual_proposed", "residual_submitted"}))
        target = entry["quantity"] // 2
        target_filled = sum(s["quantity"] for s in sold(entry, at - 1) if s["reason"] == "first_target")
        stop = float(entry["fill_price"]) if target and target == target_filled else entry["initial_stop_price"]
        require(event["remaining_quantity"] == remaining > 0 and event["active_stop_price"] == stop
            and event["full_exit_attempted"] is True, "residual confirmed shares or stop differs")
        terminal = [e for e in orders.get(entry["opportunity_id"], []) if e["reason"] != "first_target"]
        require(1 <= len(terminal) <= 2, "residual terminal order budget differs")
        if kind == "residual_ready":
            require(eid not in states and event["residual_attempts"] == 0, "duplicate or consumed residual authority")
            context = checked(event["context"])
            require(set(context) == {"prior_submission_intent", "prior_order_id", "cancel_acknowledgement", "terminal_attempt_number", "content_sha256"}
                and context["terminal_attempt_number"] == 2, "residual context scope differs")
            intent = checked(context["prior_submission_intent"])
            prior = terminal[0]
            require(context["prior_order_id"] == prior["order"]["order_id"] == "exit-" + intent["content_sha256"]
                and intent["entry_content_sha256"] == eid and intent["decision_ts_ns"] == prior["at_ns"]
                and intent["reason"] == prior["reason"] and intent["quantity"] == prior["order"]["quantity"]
                and "residual_exit" not in intent, "residual prior submitted signal differs")
            cancel(entry, prior["order"], context["cancel_acknowledgement"])
            require(at == context["cancel_acknowledgement"]["timestamp_ns"]
                and (event["known_at_ns"] > at or (event["known_at_ns"] == at and event["clock_phase"] == 2)),
                "residual acknowledged before feedback")
            states[eid] = {"context": context, "events": [], "data": data, "entry": entry}
            counts["residual_ready"] += 1
            continue
        require(eid in states, "residual event without acknowledged authority")
        state = states[eid]
        state["events"].append(event)
        if kind == "residual_budget_exhausted":
            require(len(terminal) == 2 and event["residual_attempts"] == 1, "residual budget exhaustion differs")
            cancel(entry, terminal[1]["order"], event["cancel_acknowledgement"])
            require(at == terminal[1]["order"]["cancel_ack_ts_ns"]
                and (event["known_at_ns"] > at or (event["known_at_ns"] == at and event["clock_phase"] == 2)),
                "residual budget exhausted before acknowledgement")
            counts["residual_budget_exhaustions"] += 1
            continue
        require(event["context"] == state["context"], "residual authority changed")
        if kind == "residual_proposed":
            require(event["residual_attempts"] == 0, "residual proposal consumed budget")
            counts["residual_proposals"] += 1
        elif kind == "residual_submitted":
            require(event["residual_attempts"] == 1 and len(terminal) == 2
                and event["order"] == terminal[1]["order"], "residual submission order or count differs")
            intent = checked(event["intent"])
            require(intent["residual_exit"] == state["context"] and intent["decision_ts_ns"] == at
                and event["order"]["order_id"] == "exit-" + intent["content_sha256"]
                and intent["quantity"] == remaining == event["order"]["quantity"], "residual order signal or quantity differs")
            require(References(data["tape"]).at(window, at) is not None, "residual submitted without fresh reference")
            counts["residual_submissions"] += 1
        else:
            require(kind == "residual_expired" and event["residual_attempts"] == 0
                and at + TAIL >= window["end_ns"] and event["original_window_end_ns"] == window["end_ns"],
                "residual expiry differs")
            counts["residual_expiries"] += 1
    for eid, state in states.items():
        entry, data, context = state["entry"], state["data"], state["context"]
        events = state["events"]
        proposals = [e for e in events if e["event_type"] == "residual_proposed"]
        submissions = [e for e in events if e["event_type"] == "residual_submitted"]
        expiries = [e for e in events if e["event_type"] == "residual_expired"]
        exhausted = [e for e in events if e["event_type"] == "residual_budget_exhausted"]
        require(len(proposals) <= 1 and len(submissions) <= 1 and len(expiries) <= 1 and len(exhausted) <= 1,
            "repeated residual transition")
        ack = context["cancel_acknowledgement"]["timestamp_ns"]
        first = next((r for r in data["trades"] if ack < r["timestamp_ns"]
            and r["timestamp_ns"] + TAIL < data["window"]["end_ns"] and eligible(r["record"])), None)
        if proposals:
            proposal = proposals[0]
            intent = checked(proposal["intent"])
            require(first is not None and proposal["timestamp_ns"] == first["timestamp_ns"]
                and intent["trade_evidence"] == evidence(first, "sip_transactions"), "not first eligible post-ack residual print")
            reason = terminal_reason(entry, data, runtime, first)
            red = next(({"signal_ts_ns": b["timestamp_ns"] + MINUTE, "evidence": evidence(b, "raw_sip_1m_bars")}
                for b in data["bars"] if entry["fill_time_ns"] < b["timestamp_ns"] + MINUTE <= min(first["timestamp_ns"], data["window"]["signal_end_ns"])
                and b["record"]["c"] < b["record"]["o"]), None)
            expected = parent.seal({**{k: entry[k] for k in ("opportunity_id", "path_id", "session_id", "scenario_id")},
                "entry_content_sha256": eid, "decision_ts_ns": first["timestamp_ns"], "reason": reason,
                "quantity": proposal["remaining_quantity"], "trade_evidence": evidence(first, "sip_transactions"),
                "red_signal": red if reason == "first_red_candle" else None, "residual_exit": context})
            require(intent == expected and reason is not None, "residual signal priority or identity differs")
            if submissions:
                actual = submissions[0]
                if actual["intent"] != intent:
                    require(any(w["event_type"] == "wait_submitted" and w["submission_intent"] == actual["intent"]
                        and w["original_signal_content_sha256"] == intent["content_sha256"]
                        for w in snapshot.get("exit_wait_events", [])), "delayed residual order is not bound to wait evidence")
            else:
                require(runtime["failure"] is not None or any(w["event_type"] == "wait_expired"
                    and w["original_signal_content_sha256"] == intent["content_sha256"]
                    for w in snapshot.get("exit_wait_events", [])), "residual proposal omitted submission or preserved wait")
        else:
            require(not submissions and (runtime["failure"] is not None or (first is None and len(expiries) == 1)),
                "eligible residual proposal omitted")
        if submissions:
            order = submissions[0]["order"]
            if runtime["complete_streams_verified"] and quantity(entry, order["cancel_ack_ts_ns"]) > 0:
                require(len(exhausted) == 1, "residual exhausted remainder not recorded")
    # Omitting the entire audit must not conceal either authority or replacement.
    for oid, entry in by_oid.items():
        terminal = [e for e in orders.get(oid, []) if e["reason"] != "first_target"]
        if terminal:
            ack = terminal[0]["order"]["cancel_ack_ts_ns"]
            if runtime["complete_streams_verified"] and quantity(entry, ack) > 0:
                require(entry["content_sha256"] in states, "acknowledged residual authority omitted")
            if len(terminal) == 2:
                require(entry["content_sha256"] in states and any(e["event_type"] == "residual_submitted"
                    for e in states[entry["content_sha256"]]["events"]), "second terminal lacks residual authority")
    return counts


def verify_parent_prefix(before, after):
    """All completed parent sessions and the first residual precursor are exact."""
    for old_pair, new_pair in zip(before["sessions"], after["sessions"]):
        prior, current = old_pair["runtime"], new_pair["runtime"]
        snapshot = current["reconciliation_snapshot"]
        audit = [] if snapshot is None else snapshot.get("exit_residual_events", [])
        if not audit:
            require(old_pair == new_pair, "pre-residual parent session changed")
            continue
        first = audit[0]
        require(first["event_type"] == "residual_ready", "first residual event is not acknowledged authority")
        ack = first["context"]["cancel_acknowledgement"]["timestamp_ns"]
        prefix = [e for e in prior["events"] if e["at_ns"] <= ack]
        require([e for e in current["events"] if e["at_ns"] <= ack] == prefix,
            "pre-residual parent event prefix changed")
        old_engine = prior["reconciliation_snapshot"]["management"]
        require(old_engine is not None and old_engine["remaining_quantity"] == first["remaining_quantity"]
            and old_engine["events"][-1] == first["context"]["cancel_acknowledgement"],
            "parent acknowledged remainder changed")
        return
    require(before == after, "no-residual path differs from frozen parent")



def verify(root, runtime_root, binding_root, parent_runtime_root, expected_runtime_sha, paths):
    contract = read(root / f"research/strategy/{ID}.json")
    require(contract["contract_id"] == ID and contract["parent_runtime_content_sha256"] == PARENT_RUNTIME
        and contract["parent_runtime_file_sha256"] == PARENT_FILE, "residual parent identity differs")
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
                totals = {"path_id": after["path_id"], **verify_path(program, after, manifest)}
                verify_parent_prefix(before, after)
                for pair in after["sessions"]:
                    runtime = pair["runtime"]
                    if runtime["reconciliation_snapshot"] is not None:
                        verify_decimal_snapshot(runtime["reconciliation_snapshot"])
                    for key, count in verify_residual(runtime, sources).items():
                        totals[key] = totals.get(key, 0) + count
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
        "paths": counts, "totals": totals, "parent_chronology_checks_preserved_except_registered_two_terminal_ceiling": True,
        "original_waiting_signals_and_first_eligible_fresh_prints_verified": True,
        "pre_residual_parent_event_prefix_unchanged": True,
        "bounded_residual_cancel_signal_quantity_and_earliest_print_verified": True, "independent_fill_simulation": False,
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
