"""Registered position orchestration and exact common exit-input requirements.

Only synthetic mechanics execute in this child. A frozen context is resolvable,
but no authenticated preceding-account producer, exit capture, fee integration,
or historical runtime activation is supplied here.
"""
from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from copy import deepcopy
import hashlib
import heapq
import json
import os
from pathlib import Path

import pandas as pd

from momentumbot.research import sealed_historical_management_fill_feedback_v01 as feedback
from momentumbot.research.sealed_historical_execution_quote_v01 import canonical_fingerprint, file_sha, frozen, require_exact, seal

CONTRACT_ID = "sealed-historical-management-runner-v0.1"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
OUTPUT_PATH = f"research/runtime/{CONTRACT_ID}"
MODULE_PATH = "src/momentumbot/research/sealed_historical_management_runner_v01.py"
SCRIPT_PATH = "scripts/build_sealed_historical_management_runner_v01.py"
TEST_PATH = "tests/test_sealed_historical_management_runner_v01.py"
WORKFLOW_PATH = ".github/workflows/sealed-historical-management-runner-v01.yml"
PARENT_COMMIT = "d9e5a04b6f9f78ba09fc87c53be2e7b9aa359b89"
PARENT_TREE = "c2414072ebc4776a1ee795561b660230d5a30ccc"
PARENT_FREEZE = "3304832421b6a0ed963a93eba8fcbecaa85ebab6b77471bead7c16ff00c058d5"
projection = feedback.parent
accounts = feedback.accounts
INPUT_REQUIREMENTS = projection.OUTPUT_PATH + "/projection-input-requirements.json"
ENTRY_REQUESTS = str(accounts.PLAN_PATH) + "/request-manifest.json"
PARENT_PINS = {
    feedback.MODULE_PATH: "8ac8b1ea0a8d3ccf57c07d5a3a5ddf0cd82409210dc16506c68400b768f8697d",
    feedback.CONTRACT_PATH: "eb41f6fc5112b84e85d014bbc0f990b14b521e76ca3141a23b7044ef54fbc178",
    "research/data-audits/sealed-historical-management-fill-feedback-v0.1-independent-verification.json": "0356a6ddbb0f51f6f07de6de823d0f20134d2c1b345b708f1e0cee95d7be5a77",
    INPUT_REQUIREMENTS: "8b89b1ffd05de277bcff906140b5aeb142a823cce99260d9c967a8d1dc9e931f",
    projection.ACCOUNT_PLAN: "8ca638578e7957c88f4314e0768a3c379ee0bd1278bd6d8c8e9caa2144f05108",
    ENTRY_REQUESTS: "ee0701cfbe81bfb546c1fb2d2573cf824b434d3a34ff6f1dffdd8cec5435a2e3",
}
BOUNDARY = dict(feedback.BOUNDARY)
NEXT_GATE = "verify_exact_existing_common_source_reuse_and_register_bounded_metadata_quote_for_remaining_exit_requests"
DEPENDENCIES = {
    "exact_exit_tapes_verified": False,
    "existing_common_source_reuse_bytes_verified": False,
    "historical_account_state_producer_verified": False,
    "historical_fee_and_sell_ledger_integration_verified": False,
    "causal_next_session_valuation_verified": False,
    "continuous_account_order_and_scarcity_integration_verified": False,
    "historical_execution_child_authorized": False,
}


def mechanics() -> dict:
    return {
        "context": "resolve_original_window_session_and_decision_hash_from_verified_frozen_catalog",
        "entry_source": "original_verified_entry_quote_status_source_only_never_replace_with_exit_capture",
        "merge": "streaming_two_way_merge_bar_close_then_SIP_source_order_then_equal_time_feedback",
        "feedback_clock": "scheduled_arrival_quote_receive_cancel_request_and_cancel_ack_ticks_no_private_future_outcome_read",
        "source_integrity": "validate_entire_original_order_and_incremental_canonical_envelope_commitments_before_success",
        "input_failure": "raise_with_partial_state_and_unresolved_intent_no_retry_no_fabricated_fill",
        "end_of_window": "settle_at_original_exclusive_end_minus_one_no_forced_liquidation",
        "exit_scope": "one_common_quote_status_pair_per_available_symbol_date_covers_all_registered_opportunity_envelopes",
        "quote_start": "earliest_available_original_decision_minus_frozen_100ms_reference_margin",
        "quote_end": "latest_available_original_opportunity_exclusive_end",
        "status_start": "UTC_midnight_of_original_date_same_end_as_quote",
        "reuse": "original_complete_pair_if_its_intervals_cover_required_scope_exact_byte_verification_still_required",
        "late_exit": "retain_input_failure_when_frozen_550ms_plus_1ns_capture_tail_exceeds_own_opportunity",
        "no_outcome_based_selection": True,
        "single_position_only": True,
        "multiple_entry_campaigns_and_account_closes": "separate_integration_dependency",
    }


def expected_contract(root: Path) -> dict:
    return seal({"schema_version": 1, "contract_id": CONTRACT_ID,
        "artifact_type": "historical_position_runner_specification_and_exact_exit_input_registration",
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "parent_freeze_content_sha256": PARENT_FREEZE, "frozen_parent_file_sha256": PARENT_PINS,
        "hypothesis": "causal_position_orchestration_preserves_source_order_and_uses_only_confirmed_fill_feedback",
        "mechanics": mechanics(), "historical_runtime_dependencies": DEPENDENCIES,
        "position_runner_mechanics_registered": True, "historical_runtime_activation_ready": False,
        "implementation_file_sha256": {p: file_sha(root / p) for p in (MODULE_PATH, SCRIPT_PATH, TEST_PATH, WORKFLOW_PATH)},
        "next_gate": NEXT_GATE, **BOUNDARY})


def validate_registration(root: Path) -> dict:
    for name, expected in PARENT_PINS.items():
        accounts.availability._regular(root / name)
        if file_sha(root / name) != expected:
            raise ValueError("runner parent differs: " + name)
    feedback.verify_bundle(root, root / feedback.OUTPUT_PATH)
    if frozen(root / feedback.OUTPUT_PATH / "freeze-manifest.json")["content_sha256"] != PARENT_FREEZE:
        raise ValueError("parent fill-feedback freeze differs")
    require_exact(frozen(root / CONTRACT_PATH), expected_contract(root), "runner registration")
    return seal({"verification_passed": True, "contract_content_sha256": expected_contract(root)["content_sha256"], **BOUNDARY})


def require_historical_runtime_ready(root: Path) -> None:
    """There is no caller-supplied Boolean or permissive fallback for this gate."""
    validate_registration(root)
    missing = [name for name, ready in DEPENDENCIES.items() if not ready]
    if missing:
        raise ValueError("historical runtime dependencies unresolved: " + ", ".join(missing))


def derive_exit_plan(windows: list[dict], original_requests: list[dict]) -> dict:
    """Interval algebra only: no SIP prices, fills, account selection or providers."""
    original = {}
    for request in original_requests:
        if request.get("schema") not in ("mbp-1", "status"):
            raise ValueError("unsupported original request schema")
        feedback.adapter._request(request, request["schema"])
        key = (request["trading_date"], request["symbols"][0], request["schema"])
        if key in original:
            raise ValueError("duplicate original request identity")
        original[key] = request
    grouped = defaultdict(list)
    retained, seen = [], set()
    for window in windows:
        projection.validate_window(window)
        op = window["opportunity"]
        if op["opportunity_id"] in seen:
            raise ValueError("duplicate original opportunity")
        seen.add(op["opportunity_id"])
        key = (op["trading_date"], op["symbol"])
        group_id = f"{key[0]}-{key[1]}-common-management-exit" if window["entry_input_status"] == "available" else None
        retained.append({"opportunity_id": op["opportunity_id"], "window_content_sha256": canonical_fingerprint(window),
            "entry_input_status": window["entry_input_status"], "entry_input_reason": window["entry_input_reason"],
            "availability_content_sha256": window["availability_content_sha256"], "group_id": group_id})
        if group_id:
            grouped[key].append(window)
    groups, requests, reused = [], [], []
    for (day, symbol), members in sorted(grouped.items()):
        start = min(w["opportunity"]["decision_ts_ns"] - projection.PRE_QUOTE_NS for w in members)
        end = max(w["end_ns"] for w in members)
        midnight = int(pd.Timestamp(day, tz="UTC").value)
        required = [{"request_id": f"{day}-{symbol}-{schema}", "trading_date": day,
            "dataset": "XNAS.ITCH", "schema": schema, "symbols": [symbol], "stype_in": "raw_symbol",
            "start_ns": first, "end_ns": end, "end_exclusive": True}
            for schema, first in (("mbp-1", start), ("status", midnight))]
        for request in required:
            feedback.adapter._request(request, request["schema"])
        old = [original.get((day, symbol, schema)) for schema in ("mbp-1", "status")]
        can_reuse = (all(r is not None and r["start_ns"] <= need["start_ns"] and r["end_ns"] >= end
                        for r, need in zip(old, required)) and old[0]["end_ns"] == old[1]["end_ns"])
        selected = deepcopy(old if can_reuse else required)
        (reused if can_reuse else requests).extend(selected)
        group = {"group_id": f"{day}-{symbol}-common-management-exit", "trading_date": day, "symbol": symbol,
            "required_quote_start_ns": start, "required_end_ns": end,
            "source_kind": "existing_entry_pair_reuse_requires_exact_byte_verification" if can_reuse else "new_pair_requires_quote_and_acquisition",
            "requests": selected, "request_content_sha256": [canonical_fingerprint(r) for r in selected],
            "source_bytes_verified": False, "provider_request_authorized": False,
            "members": [{"opportunity_id": w["opportunity"]["opportunity_id"], "window_content_sha256": canonical_fingerprint(w),
                "first_possible_exit_decision_ns": w["opportunity"]["decision_ts_ns"] + min(p.decision_to_arrival_ms for p, _ in feedback.SCENARIOS.values()) * 1_000_000 + 1,
                "last_covered_exit_decision_ns": w["end_ns"] - projection.POST_QUOTE_NS - 1,
                "original_end_ns": w["end_ns"]} for w in members]}
        groups.append(seal(group))
    return seal({"contract_id": CONTRACT_ID, "groups": groups, "opportunities": retained,
        "new_requests": requests, "reuse_candidate_requests": reused,
        "new_request_count": len(requests), "reuse_candidate_request_count": len(reused),
        "common_symbol_date_count": len(groups), "new_request_list_content_sha256": canonical_fingerprint(requests),
        "reuse_candidate_list_content_sha256": canonical_fingerprint(reused),
        "quote_duration_ns": sum(r["end_ns"] - r["start_ns"] for r in requests if r["schema"] == "mbp-1"),
        "future_metadata_call_ceiling": len(requests) * 2, "metadata_quote_executed": False,
        "billable_bytes": None, "quoted_cost_usd": None, **BOUNDARY})


def resolve_registered_context(root: Path, *, path_id: str, opportunity_id: str, source_decision: dict) -> dict:
    """Authenticate context against immutable catalog bytes, not a caller rehash."""
    validate_registration(root)
    windows = frozen(root / INPUT_REQUIREMENTS)["opportunity_windows"]
    matches = [w for w in windows if w["opportunity"]["opportunity_id"] == opportunity_id]
    if len(matches) != 1:
        raise ValueError("unregistered opportunity")
    window = matches[0]
    if window["entry_input_status"] != "available":
        raise ValueError("registered entry inputs unavailable")
    if set(source_decision) != accounts.availability.plan.DECISION_FIELDS or canonical_fingerprint(source_decision) != window["opportunity"]["source_decision_content_sha256"]:
        raise ValueError("decision differs from original catalog commitment")
    paths = frozen(root / projection.ACCOUNT_PLAN)["paths"]
    slots = [s for p in paths if p["path_id"] == path_id for s in p["sessions"]
             if s["trading_date"] == window["opportunity"]["trading_date"]]
    if len(slots) != 1 or not any(r["opportunity_id"] == opportunity_id and r["input_status"] == "available" for r in slots[0]["opportunity_inputs"]):
        raise ValueError("opportunity is not available in this registered account path")
    context = {"window": window, "slot": slots[0], "source_decision": deepcopy(source_decision)}
    return seal({"contract_id": CONTRACT_ID, "context": context, "context_content_sha256": canonical_fingerprint(context),
        "original_context_authenticated": True, "pre_entry_account_state_authenticated": False,
        "historical_runtime_authorized": False})


def _row_bytes(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def stream_commitment(records) -> dict:
    digest, count = hashlib.sha256(), 0
    for value in records:
        digest.update(_row_bytes(value)); count += 1
    return {"rows": count, "sha256": digest.hexdigest()}


class _Cursor:
    def __init__(self, records, window, resource, expected):
        if (not isinstance(expected, dict) or set(expected) != {"rows", "sha256"}
                or type(expected["rows"]) is not int or expected["rows"] < 0
                or not isinstance(expected["sha256"], str) or len(expected["sha256"]) != 64):
            raise ValueError("complete stream commitment required")
        self.iterator = iter(projection._records(records, window, resource))
        self.resource, self.expected = resource, deepcopy(expected)
        self.digest, self.count, self.value = hashlib.sha256(), 0, None
        self.advance()

    def advance(self):
        self.value = next(self.iterator, None)
        if self.value is None:
            require_exact({"rows": self.count, "sha256": self.digest.hexdigest()}, self.expected, "complete management stream")
        else:
            self.digest.update(_row_bytes(self.value)); self.count += 1

    def key(self):
        if self.value is None:
            return None
        bar = self.resource == "raw_sip_1m_bars"
        return (self.value["timestamp_ns"] + (projection.MINUTE_NS if bar else 0), 0 if bar else 1)


class RunnerInputFailure(ValueError):
    """A failed mechanics run preserves its last state; never a zero-trade result."""
    def __init__(self, stage: str, state: dict | None):
        super().__init__("position runner input failure: " + stage)
        self.stage = stage
        self.partial_state = deepcopy(state)


def run_position_mechanics(*, entry_arguments: dict, bars, trades, expected_streams: dict,
                           exit_group: dict, expected_exit_group_sha256: str,
                           exit_tape: dict, expected_exit_tape_sha256: str) -> dict:
    """Pure caller-pinned mechanics, not an activated historical/account runner.

    The scheduler reads no private pending outcome. Its feedback ticks come from
    public latency rules and actual quote receive timestamps. Per-source order
    is validated, not sorted. All same-time market records precede feedback.
    """
    engine, stage = None, "entry_or_exit_evidence"
    try:
        feedback._pinned(exit_group, expected_exit_group_sha256, "exit group")
        feedback._pinned(exit_tape, expected_exit_tape_sha256, "complete exit tape")
        accounts._sealed(exit_group, "exit group")
        if set(exit_tape) != {"quote_request", "quote_records", "status_request", "status_records"}:
            raise ValueError("exact complete exit tape fields required")
        require_exact([exit_tape["quote_request"], exit_tape["status_request"]], exit_group["requests"], "registered common exit requests")
        window = entry_arguments["window"]
        op = window["opportunity"]
        members = [v for v in exit_group["members"] if v["opportunity_id"] == op["opportunity_id"]]
        if len(members) != 1 or members[0]["window_content_sha256"] != canonical_fingerprint(window):
            raise ValueError("exit scope does not bind this exact original window")
        if (exit_group["symbol"] != op["symbol"] or exit_group["trading_date"] != op["trading_date"]
                or exit_group["required_quote_start_ns"] > op["decision_ts_ns"] - projection.PRE_QUOTE_NS
                or exit_group["required_end_ns"] < window["end_ns"]):
            raise ValueError("common scope does not cover original opportunity")
        for request in exit_group["requests"]:
            if (request["symbols"] != [op["symbol"]] or request["trading_date"] != op["trading_date"]
                    or request["start_ns"] > exit_group["required_quote_start_ns"]
                    or request["end_ns"] < exit_group["required_end_ns"]):
                raise ValueError("source request does not cover complete common scope")
        if exit_tape["quote_request"]["end_ns"] != exit_tape["status_request"]["end_ns"]:
            raise ValueError("common quote and status ends differ")
        # Validate even an unused tape; empty/invalid evidence is not a no-exit outcome.
        quotes = feedback.adapter.quote_events(exit_tape["quote_records"], exit_tape["quote_request"])
        feedback.adapter.status_events(exit_tape["status_records"], exit_tape["status_request"])
        quote_times = [q.ts_recv_ns for q in quotes]
        if set(expected_streams) != {"raw_sip_1m_bars", "sip_transactions"}:
            raise ValueError("both complete management streams required")
        engine = feedback.ManagementFillFeedback(**entry_arguments)
        stage = "management_stream"
        cursors = [_Cursor(records, entry_arguments["window"], resource, expected_streams[resource])
                   for records, resource in ((bars, "raw_sip_1m_bars"), (trades, "sip_transactions"))]
        ticks, scheduled, orders = [], set(), []
        end = entry_arguments["window"]["end_ns"]
        while any(c.value is not None for c in cursors) or ticks:
            live = [c for c in cursors if c.value is not None]
            cursor = min(live, key=lambda c: c.key()) if live else None
            tick = ticks[0] if ticks else None
            # Every bar and print tied with a feedback tick wins this comparison.
            if tick is not None and (cursor is None or tick < cursor.key()[0]):
                heapq.heappop(ticks); scheduled.remove(tick)
                engine.settle(tick)
                continue
            stage = "management_stream"
            at, phase = cursor.key()
            if phase == 0:
                engine.observe_bar(cursor.value)
            else:
                intent = engine.observe_trade(cursor.value)
                if intent:
                    stage = "executable_exit_evidence"
                    order = engine.submit_intent(intent, tape=exit_tape, expected_tape_sha256=expected_exit_tape_sha256)
                    orders.append(order)
                    times = {order["arrival_ts_ns"], order["cancel_requested_ts_ns"], order["cancel_ack_ts_ns"]}
                    lo = bisect_left(quote_times, order["arrival_ts_ns"])
                    hi = bisect_left(quote_times, order["cancel_ack_ts_ns"])
                    times.update(quote_times[lo:hi])
                    for stamp in times:
                        if stamp >= end:
                            raise ValueError("feedback outside original opportunity")
                        if stamp not in scheduled:
                            heapq.heappush(ticks, stamp); scheduled.add(stamp)
            stage = "management_stream"
            cursor.advance()
        stage = "final_feedback"
        final = engine.settle(end - 1)
    except (ValueError, KeyError, TypeError, OverflowError, OSError) as exc:
        raise RunnerInputFailure(stage, None if engine is None else engine.snapshot()) from exc
    return seal({"contract_id": CONTRACT_ID, "artifact_type": "caller_pinned_single_position_orchestration_result",
        "entry_context_content_sha256": entry_arguments["expected_context_sha256"],
        "exit_group_content_sha256": expected_exit_group_sha256, "exit_tape_content_sha256": expected_exit_tape_sha256,
        "management_streams": deepcopy(expected_streams), "orders": orders, "final_state": final,
        "complete_streams_verified": True, "no_private_future_outcome_read": True,
        "original_context_authenticated_by_this_function": False, "historical_producer_authenticated": False,
        "historical_runtime_authorized": False, "account_close_produced": False, "financial_metrics_eligible": False})


def build_bundle(root: Path) -> dict[str, bytes]:
    validate_registration(root)
    prior = frozen(root / INPUT_REQUIREMENTS)
    path_plan = frozen(root / projection.ACCOUNT_PLAN)
    exit_plan = derive_exit_plan(prior["opportunity_windows"], frozen(root / ENTRY_REQUESTS)["requests"])
    index = seal({"contract_id": CONTRACT_ID, "counts": prior["counts"],
        "original_windows_content_sha256": canonical_fingerprint(prior["opportunity_windows"]),
        "original_dates_content_sha256": canonical_fingerprint(prior["dates"]),
        "original_account_plan_content_sha256": path_plan["content_sha256"],
        "session_slots_content_sha256": canonical_fingerprint([s for p in path_plan["paths"] for s in p["sessions"]]),
        "source_requirements_path": INPUT_REQUIREMENTS, "source_account_plan_path": projection.ACCOUNT_PLAN,
        "exit_input_plan_content_sha256": exit_plan["content_sha256"],
        "management_input_manifest_content_sha256": projection.INPUT_MANIFEST_SHA256,
        "historical_runtime_dependencies": DEPENDENCIES, **BOUNDARY})
    report = seal({"contract_id": CONTRACT_ID, "counts": prior["counts"],
        "common_symbol_date_count": exit_plan["common_symbol_date_count"],
        "new_exit_request_count": exit_plan["new_request_count"],
        "reuse_candidate_request_count": exit_plan["reuse_candidate_request_count"],
        "position_runner_mechanics_registered": True, "historical_runtime_activation_ready": False,
        "historical_runtime_dependencies": DEPENDENCIES, "historical_entry_or_exit_count": 0,
        "metadata_quote_executed": False, "source_tapes_reopened": False,
        "quoted_cost_usd": None, "next_gate": NEXT_GATE, **BOUNDARY})
    docs = {"exit-input-request-plan.json": exit_plan, "runner-input-index.json": index, "readiness-report.json": report}
    files = {name: accounts._bytes(value) for name, value in docs.items()}
    files["freeze-manifest.json"] = accounts._bytes(seal({"contract_id": CONTRACT_ID, "parent_commit_sha": PARENT_COMMIT,
        "contract_content_sha256": expected_contract(root)["content_sha256"], "parent_freeze_content_sha256": PARENT_FREEZE,
        "file_inventory": {n: {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()} for n, raw in files.items()},
        "document_content_sha256": {n: v["content_sha256"] for n, v in docs.items()}, "next_gate": NEXT_GATE, **BOUNDARY}))
    return files


def _output(root: Path, output: Path):
    if output.is_symlink() or any(p.is_symlink() for p in output.parents):
        raise ValueError("symlink output rejected")
    if output.resolve().is_relative_to(root.resolve()) and output.resolve() != (root / OUTPUT_PATH).resolve():
        raise ValueError("cannot overwrite frozen repository inputs")


def verify_bundle(root: Path, output: Path) -> dict:
    _output(root, output)
    expected = build_bundle(root)
    actual = accounts.availability._inventory(output)
    if set(actual) != set(expected):
        raise ValueError("runner metadata inventory differs")
    for name, raw in expected.items():
        if (output / name).read_bytes() != raw:
            raise ValueError("runner reconstruction differs: " + name)
    return seal({"verification_passed": True, "contract_id": CONTRACT_ID, "file_inventory": actual,
        "freeze_manifest_content_sha256": frozen(output / "freeze-manifest.json")["content_sha256"], **BOUNDARY})


def write_bundle(root: Path, output: Path) -> dict:
    _output(root, output)
    if output.exists():
        raise FileExistsError("runner registration is write-once")
    files = build_bundle(root)
    output.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        with (output / name).open("xb") as handle:
            if handle.write(raw) != len(raw):
                raise OSError("short metadata write")
            handle.flush(); os.fsync(handle.fileno())
    return verify_bundle(root, output)
