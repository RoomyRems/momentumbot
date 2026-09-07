"""Register causal, fractional SIP management mechanics, never executable exits.

The pure primitive accepts an UNVERIFIED external fill argument. Only synthetic
tests call it in this registration. A separately frozen producer must bind a
confirmed entry and a verified ManagementInputBundle before historical use.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import math
import os
from pathlib import Path

import pandas as pd

from momentumbot.micro_bars import minute_trade_eligibility
from momentumbot.research import sealed_historical_management_inputs_v01 as inputs
from momentumbot.research.sealed_historical_execution_quote_v01 import file_sha, frozen, require_exact, seal

CONTRACT_ID = "sealed-historical-management-projection-v0.1"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
OUTPUT_PATH = f"research/runtime/{CONTRACT_ID}"
MODULE_PATH = "src/momentumbot/research/sealed_historical_management_projection_v01.py"
SCRIPT_PATH = "scripts/build_sealed_historical_management_projection_v01.py"
TEST_PATH = "tests/test_sealed_historical_management_projection_v01.py"
WORKFLOW_PATH = ".github/workflows/sealed-historical-management-projection-v01.yml"
PARENT_COMMIT = "f4a8d98b5ff780a4138ed4eb5628423891e4818d"
PARENT_TREE = "bf3e9dfe4c2d89f5f482f2d0701d8499d6508858"
INPUT_AUDIT = "research/data-audits/sealed-historical-management-inputs-v0.1-independent-verification.json"
INPUT_MANIFEST_SHA256 = "df00c1aa3e66fbb3040e63df210ef71ead7518858f5bc3ff44fc59067eeb15de"
ACCOUNT_PLAN = inputs.accounts.OUTPUT_PATH + "/account-session-input-plan.json"
CELL = "half-2r-breakeven-first-red-1m"
MINUTE_NS = 60_000_000_000
SIGNAL_NS = 900_000_000_000
TAIL_NS = 60_000_000_000
PRE_QUOTE_NS = 100_000_000
POST_QUOTE_NS = 550_000_000
BOUNDARY = dict(inputs.BOUNDARY)
NEXT_GATE = "register_confirmed_entry_binding_and_executable_management_fill_feedback_before_historical_projection_or_exit_capture"
PARENT_PINS = {
    INPUT_AUDIT: "386d8406c10714091b7a66e62c97604bf96ee08bb36138354546757f18deb5f7",
    inputs.SNAPSHOT_PATH + "/freeze-manifest.json": "8ac5bcdbc13f5d9f9c09ade2b6f550c6336bacaa620001c8555bd910d3e827b7",
    inputs.SNAPSHOT_PATH + "/management-input-manifest.json": "e4f1c62804a442f5718f87e18109509171b37a0bfe8810d08ba6cdb668e4d57e",
    inputs.SNAPSHOT_PATH + "/opportunity-input-index.json": "53272c4ce081c6b0684c95fd1332c64cc883d79e16bdd5cb4f797baab6cbae3b",
    inputs.SNAPSHOT_PATH + "/readiness-report.json": "8e3f936c90211ab52c14044ede577e409d6ac4bc595532fc2c74d9ec66169064",
    inputs.SNAPSHOT_PATH + "/source-verification.json": "37169a1dc11db3804cff698569524b5287b01b8154df2f5e9c6fff598a948b2d",
    inputs.CONTRACT_PATH: "bfdada0f93a3152dc0c561592dbaaa37e89a1c6d19b86af011344a57145d1227",
    inputs.MODULE_PATH: "4731af34014e2403f08f75b1cede71628e18fcc2d01a335a7dd26dc95c9face2",
    ACCOUNT_PLAN: "8ca638578e7957c88f4314e0768a3c379ee0bd1278bd6d8c8e9caa2144f05108",
    "research/strategy/prospective-management-execution-v0.1.json": "3760a73d4cc5d209098b75d555fb1f1a4ebcd7c0ecc428b1a16c39c2055008f8",
    "research/strategy/prospective-management-window-capture-v0.1.json": "dd42ad3b7e826e8893f63809d6c9804ac0efbfae708992e5c5bd4c0220ee5ae7",
    "src/momentumbot/micro_bars.py": "946cbcae2fe5c9272388e078e8c2e7e97094f97a6e6b32e9ad43335f09e9546c",
    "src/momentumbot/micro_execution.py": "234836c30b51fb8789aae345f159cfe2226b2d7bdbd6a2254380ca14eda4c266",
    "src/momentumbot/research/execution_realism.py": "446509405e3f44e3924c852569c5b06a096f61330552ede850a55c3da5794177",
    "src/momentumbot/research/prospective_management_window.py": "bc431e578c7c85e1c72c72eda60ff212cf128cd5fd52cae3dcbed1bcc36523e8",
    "src/momentumbot/research/prospective_market_input_capture.py": "7b736e329a9d12eb2dfdeb09473fd04fc1caa0416eb1cb84ff2db7f4819ae9ee",
    "src/momentumbot/research/sealed_historical_record_order_v01.py": "407e02fc6fe908e26715fac2799f0debf356e96336b640e795b50287762dec6b",
    "src/momentumbot/research/trade_management_shadow.py": "9309593b839a4260bd6ef8d34d1eec5c905128dcf502218032cb7c0f142af180",
    "scripts/run_offline_python_v13.py": "fd28ca7e4a27832721a890a1a41af36863a7f13568ca9e85e17c2d5f35e0627d",
}


def exit_requirements() -> dict:
    """Conditional requirements only: no request IDs, quotes, orders or prices."""
    return seal({"contract_id": CONTRACT_ID, "artifact_type": "conditional_executable_exit_requirements",
        "dataset": "XNAS.ITCH", "stype_in": "raw_symbol", "schemas": ["mbp-1", "status"],
        "quote_start_offset_ns": -PRE_QUOTE_NS, "quote_end_exclusive_offset_ns": POST_QUOTE_NS + 1,
        "status_start": "same_trading_date_UTC_midnight", "status_end": "quote_end_exclusive",
        "request_identity_and_scope": "requires_separate_registration_no_native_request_IDs_invented_here",
        "scenario_selection": "both_frozen_scenarios_same_evidence_no_best_scenario_selection",
        "scenarios": [
            {"scenario_id": "l1-conservative-v0.1", "arrival_latency_ns": 100_000_000,
             "max_quote_age_ns": 100_000_000, "cancel_after_arrival_ns": 250_000_000,
             "cancel_ack_latency_ns": 100_000_000, "displayed_size_haircut": "0.25", "limit_offset_ticks": 5},
            {"scenario_id": "l1-stress-v0.1", "arrival_latency_ns": 250_000_000,
             "max_quote_age_ns": 50_000_000, "cancel_after_arrival_ns": 150_000_000,
             "cancel_ack_latency_ns": 150_000_000, "displayed_size_haircut": "0.10", "limit_offset_ticks": 2}],
        "reference_quote": "latest_at_or_before_decision_within_frozen_100ms_reference_window",
        "sell_limit": "known_bid_minus_frozen_offset_times_0.01_tick_using_existing_marketable_limit_price",
        "execution_clock_and_order": "native_receive_time_sequence_original_request_ordinal_frozen_record_order_adapter",
        "quote_status_ambiguity_or_unknown_status": "unavailable_fail_closed_no_substitution",
        "liquidity": "first_eligible_state_once_floor_displayed_size_times_haircut_cancel_remainder",
        "capture_edge": "required_exclusive_end_must_not_exceed_original_opportunity_end_no_extension",
        "sip_or_bar_clock": "event_time_or_completed_bar_proxy_not_measured_receive_or_publication_latency",
        "unresolved_required_bindings": [
            "independently_verified_single_accepted_entry_with_path_scenario_symbol_session_stop_and_fill_receipt",
            "whole_share_half_target_rounding_and_one_share_behavior",
            "confirmed_target_fill_feedback_before_executable_breakeven_stop_activation",
            "partial_target_completion_cancellation_retry_and_competing_exit_order_lifecycle",
            "cross_order_liquidity_and_remaining_share_conservation",
            "causal_signal_to_order_clock_without_invented_SIP_receive_or_bar_publication_timestamps",
            "independently_quoted_and_authorized_exact_exit_quote_status_evidence_if_missing",
            "historical_date_applicable_fee_schedule_not_automatic_reuse_of_2026_prospective_fees",
            "confirmed_sell_fills_cash_risk_and_prior_session_close_handoff"],
        "actual_request_count": 0, "exit_execution_implementation_registered": False,
        "descriptive_target_touch_is_confirmed_fill": False, "sip_proxy_can_close_account": False, **BOUNDARY})


def expected_contract(root: Path) -> dict:
    return seal({"schema_version": 1, "contract_id": CONTRACT_ID,
        "artifact_type": "registered_causal_descriptive_mechanics_and_conditional_exit_requirements",
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "frozen_parent_file_sha256": PARENT_PINS, "management_input_manifest_content_sha256": INPUT_MANIFEST_SHA256,
        "hypothesis": "frozen_external_fill_management_legs_can_be_reproduced_with_causal_bar_timing_and_exact_source_lineage",
        "selected_cell_id": CELL, "signal_window_ns": SIGNAL_NS, "execution_observation_tail_ns": TAIL_NS,
        "strict_future_prints": "timestamp_ns_greater_than_external_fill_time_all_equal_time_prints_excluded",
        "print_eligibility": "frozen_Micro_price_eligibility_plus_otherwise_clean_odd_lots_unknown_conditions_fail_closed",
        "bar_eligibility": "start_plus_60s_greater_than_fill_and_not_after_signal_end",
        "priority": ["active_stop", "completed_first_red_minute", "first_2R_target"],
        "target_price": "round_float_fill_plus_2_times_float_fill_minus_stop_to_10_places_unchanged",
        "target_fraction": "0.5_descriptive_only", "target_gap_price": "target_proxy_not_observed_print_or_confirmed_fill",
        "stop_or_red_price": "observed_eligible_SIP_print_proxy", "breakeven": "after_descriptive_half_target_only_in_proxy_state",
        "tail_semantics": "stop_and_target_print_observations_continue_in_60s_tail_bar_signals_capped_at_signal_end",
        "red_signal_metadata": "only_completed_bars_known_by_terminal_proxy_exit_or_window_end_no_post_terminal_red_metadata",
        "empty_or_unfinished_path": "open_descriptive_state_no_end_of_data_liquidation_or_inferred_account_flat",
        "input_source": "future_verified_ManagementInputBundle_original_opportunity_bound_iterator",
        "historical_entry_producer": None, "historical_projection_runner_registered": False,
        "multiple_entry_or_add_campaign": "unavailable_requires_separate_registration",
        "exit_requirements_content_sha256": exit_requirements()["content_sha256"],
        "implementation_file_sha256": {p: file_sha(root / p) for p in (MODULE_PATH, SCRIPT_PATH, TEST_PATH, WORKFLOW_PATH)},
        "next_gate": NEXT_GATE, **BOUNDARY})


def validate_registration(root: Path) -> dict:
    for name, expected in PARENT_PINS.items():
        inputs.accounts.availability._regular(root / name)
        if file_sha(root / name) != expected:
            raise ValueError("management projection parent differs: " + name)
    inputs.validate_registration(root)
    require_exact(frozen(root / CONTRACT_PATH), expected_contract(root), "management projection registration")
    if frozen(root / inputs.SNAPSHOT_PATH / "freeze-manifest.json")["content_sha256"] != INPUT_MANIFEST_SHA256:
        raise ValueError("verified management manifest differs")
    return seal({"verification_passed": True, "contract_content_sha256": expected_contract(root)["content_sha256"], **BOUNDARY})


def _integer(value: object, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(label + " must be an exact integer")
    return value


def _price(value: object, label: str) -> float:
    if type(value) not in (float, int):
        raise ValueError(label + " must be a finite positive number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(label + " must be finite") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(label + " must be a finite positive number")
    return number


def validate_window(window: dict) -> None:
    decision = _integer(window["opportunity"]["decision_ts_ns"], "decision", 1)
    for key in ("start_ns", "signal_end_ns", "end_ns"):
        _integer(window[key], key, 1)
    if (window["start_ns"] != decision // MINUTE_NS * MINUTE_NS
            or window["signal_end_ns"] != decision + SIGNAL_NS
            or window["end_ns"] != decision + SIGNAL_NS + TAIL_NS):
        raise ValueError("original opportunity window required without extension")
    if window["entry_input_status"] not in ("available", "unavailable"):
        raise ValueError("original entry availability required")
    day = window["opportunity"]["trading_date"]
    if pd.Timestamp(decision, unit="ns", tz="UTC").date().isoformat() != day:
        raise ValueError("decision trading date differs")
    for key in ("opportunity_id", "symbol"):
        if not isinstance(window["opportunity"][key], str) or not window["opportunity"][key].strip():
            raise ValueError("nonempty opportunity identity required")


def conditional_exit_envelope(window: dict, decision_ns: int) -> dict:
    """An unbound envelope, not an executable decision or authorized request."""
    validate_window(window)
    _integer(decision_ns, "exit decision", 1)
    if window["entry_input_status"] != "available":
        raise ValueError("unavailable entry cannot be promoted by management data")
    if not window["opportunity"]["decision_ts_ns"] <= decision_ns < window["end_ns"]:
        raise ValueError("exit decision outside original opportunity")
    end = decision_ns + POST_QUOTE_NS + 1
    return seal({"artifact_type": "unbound_conditional_exit_envelope", "opportunity_id": window["opportunity"]["opportunity_id"],
        "exit_decision_ts_ns": decision_ns, "quote_start_ns": decision_ns - PRE_QUOTE_NS,
        "status_start_ns": int(pd.Timestamp(window["opportunity"]["trading_date"], tz="UTC").value),
        "end_ns": end, "end_exclusive": True, "original_opportunity_end_ns": window["end_ns"],
        "fits_frozen_envelope": end <= window["end_ns"],
        "status": "requires_separate_evidence_and_runtime_registration" if end <= window["end_ns"] else "unavailable_required_exit_tail_outside_frozen_envelope",
        "request_authorized": False, "order_authorized": False})


def print_eligibility(row: dict) -> tuple[bool, bool]:
    conditions, tape = row["c"], row["z"]
    if not isinstance(conditions, list) or any(not isinstance(c, str) for c in conditions) or tape not in ("A", "B", "C"):
        raise ValueError("canonical SIP conditions and tape required")
    eligibility = minute_trade_eligibility(tape, tuple(conditions))
    allowed, odd_lot = eligibility.updates_price, False
    if not allowed and "I" in conditions:
        remaining = minute_trade_eligibility(tape, tuple(c for c in conditions if c != "I"))
        allowed = remaining.updates_price and not remaining.unknown_conditions
        odd_lot = allowed
    return allowed, odd_lot


def _records(records, window: dict, resource: str):
    """Validate canonical iterator envelopes; never sort, deduplicate or rewrite."""
    previous_time = previous_composed = None
    source_ordinals = {}
    envelope_fields = {"record", "timestamp_ns", "composed_record_ordinal", "source_artifact_id", "source_request_id", "source_record_ordinal"}
    row_fields = {"t", "p", "s", "i", "x", "z", "c"} if resource == "sip_transactions" else {"t", "o", "h", "l", "c", "v", "n", "vw"}
    for item in records:
        if not isinstance(item, dict) or set(item) != envelope_fields or not isinstance(item["record"], dict) or set(item["record"]) != row_fields:
            raise ValueError("canonical source record and lineage envelope required")
        stamp = _integer(item["timestamp_ns"], "source timestamp", 1)
        ordinal = _integer(item["composed_record_ordinal"], "composed ordinal")
        source_ordinal = _integer(item["source_record_ordinal"], "source ordinal")
        artifact = _integer(item["source_artifact_id"], "source artifact", 1)
        request = item["source_request_id"]
        if not isinstance(request, str) or not request:
            raise ValueError("source request required")
        if not window["start_ns"] <= stamp < window["end_ns"]:
            raise ValueError("record outside original opportunity window")
        if previous_time is not None and (stamp < previous_time or ordinal != previous_composed + 1):
            raise ValueError("source order or composed ordinal continuity differs")
        key = (artifact, request)
        if key in source_ordinals and source_ordinal != source_ordinals[key] + 1:
            raise ValueError("source ordinal continuity differs")
        row = item["record"]
        timestamp = pd.Timestamp(row["t"])
        if pd.isna(timestamp) or timestamp.tzinfo is None or int(timestamp.value) != stamp:
            raise ValueError("record timestamp differs from exact lineage timestamp")
        if resource == "sip_transactions":
            _price(row["p"], "trade price")
            # The frozen normalizer admits zero size; the Micro price predicate
            # does not introduce an additional quantity eligibility rule.
            _integer(row["s"], "trade size")
            _integer(row["i"], "trade identity")
            if not isinstance(row["x"], str) or not row["x"]:
                raise ValueError("trade exchange required")
            print_eligibility(row)
        else:
            if stamp % MINUTE_NS or stamp == previous_time:
                raise ValueError("unique aligned raw minute bar required")
            for field in ("o", "h", "l", "c", "vw"):
                _price(row[field], "bar " + field)
            if not row["l"] <= min(row["o"], row["c"]) <= max(row["o"], row["c"]) <= row["h"]:
                raise ValueError("bar OHLC bounds differ")
            for field in ("v", "n"):
                _integer(row[field], "bar " + field)
        previous_time, previous_composed = stamp, ordinal
        source_ordinals[key] = source_ordinal
        yield item


def _evidence(item: dict, resource: str) -> dict:
    return {"resource": resource, **{k: deepcopy(v) for k, v in item.items() if k != "record"},
        "record_content_sha256": hashlib.sha256(inputs.reuse._canonical_line(item["record"])).hexdigest()}


def project_external_fill_proxy(*, window: dict, fill_time_ns: int, fill_price: float,
                                stop_price: float, trades, bars) -> dict:
    """Pure fractional proxy. The caller's fill is NOT a verified entry receipt.

    No entry selection, whole shares, sell fills, fees, cash, P&L or account
    state are computed. Historical use needs a separately registered runner.
    Source validation can inspect the full envelope; decision state stops at a
    terminal proxy exit. Later bars cannot leak into terminal signal metadata.
    """
    validate_window(window)
    if window["entry_input_status"] != "available":
        raise ValueError("unavailable entry cannot be promoted by management data")
    _integer(fill_time_ns, "external fill time", 1)
    if not window["opportunity"]["decision_ts_ns"] <= fill_time_ns < window["end_ns"]:
        raise ValueError("external fill outside original opportunity")
    fill, stop = _price(fill_price, "fill"), _price(stop_price, "stop")
    if stop >= fill:
        raise ValueError("initial stop must be below external fill")
    target = round(fill + 2.0 * (fill - stop), 10)
    if not math.isfinite(target) or target <= 0:
        raise ValueError("finite positive 2R target required")
    completed = [b for b in _records(bars, window, "raw_sip_1m_bars")
        if fill_time_ns < b["timestamp_ns"] + MINUTE_NS <= window["signal_end_ns"]]
    cursor, red = 0, None

    def advance(clock: int) -> None:
        nonlocal cursor, red
        while cursor < len(completed) and completed[cursor]["timestamp_ns"] + MINUTE_NS <= clock:
            bar = completed[cursor]
            cursor += 1
            if red is None and bar["record"]["c"] < bar["record"]["o"]:
                red = {"signal_ts_ns": bar["timestamp_ns"] + MINUTE_NS,
                       "bar_evidence": _evidence(bar, "raw_sip_1m_bars")}

    remaining, active_stop, touched = 1.0, stop, False
    legs = []
    for item in _records(trades, window, "sip_transactions"):
        at, row = item["timestamp_ns"], item["record"]
        if not remaining or at <= fill_time_ns:
            continue
        allowed, odd_lot = print_eligibility(row)
        if not allowed:
            continue
        advance(at)
        price = float(row["p"])
        if price <= active_stop:
            reason, fraction, proxy_price = "breakeven_stop" if touched else "initial_stop", remaining, price
        elif red is not None:
            reason, fraction, proxy_price = "first_red_candle", remaining, price
        elif not touched and price >= target:
            reason, fraction, proxy_price = "first_target", 0.5, target
        else:
            continue
        legs.append({"reason": reason, "quantity_fraction": fraction, "exit_time_ns": at,
            "proxy_price": proxy_price, "observed_trade_price": price, "execution_via_odd_lot": odd_lot,
            "trade_evidence": _evidence(item, "sip_transactions"),
            "completed_red_signal": deepcopy(red) if reason == "first_red_candle" else None,
            "price_basis": "sip_transaction_proxy_not_broker_fill"})
        remaining -= fraction
        if reason == "first_target":
            touched, active_stop = True, fill
    if remaining:
        advance(window["end_ns"] - 1)
    return seal({"contract_id": CONTRACT_ID, "artifact_type": "unbound_external_fill_descriptive_proxy",
        "opportunity_id": window["opportunity"]["opportunity_id"], "selected_cell_id": CELL,
        "fill_time_ns": fill_time_ns, "fill_price": fill, "initial_stop_price": stop,
        "first_target_price": target, "first_red_signal": red, "target_touched": touched,
        "stop_moved_to_breakeven": touched, "active_stop_price": active_stop,
        "legs": legs, "remaining_fraction": remaining, "status": "closed_proxy" if not remaining else "open_proxy",
        "entry_producer_verified": False, "historical_runtime_authorized": False,
        "executable_fill": False, "account_position_closed": False, "financial_metrics_eligible": False})


def build_bundle(root: Path) -> dict[str, bytes]:
    validate_registration(root)
    index = frozen(root / inputs.SNAPSHOT_PATH / "opportunity-input-index.json")
    plan = frozen(root / ACCOUNT_PLAN)
    windows = index["opportunity_windows"]
    for window in windows:
        validate_window(window)
    sessions = [session for path in plan["paths"] for session in path["sessions"]]
    references = [entry for session in sessions for entry in session["opportunity_inputs"]]
    counts = {"opportunities": len(windows), "available_entry_inputs": sum(w["entry_input_status"] == "available" for w in windows),
        "unavailable_entry_inputs": sum(w["entry_input_status"] == "unavailable" for w in windows),
        "dates": len(index["dates"]), "no_decision_dates": sum(d["opportunity_count"] == 0 for d in index["dates"]),
        "account_paths": len(plan["paths"]), "session_slots": len(sessions), "profile_scenario_opportunity_references": len(references)}
    require_exact(counts, {"opportunities": 109, "available_entry_inputs": 86, "unavailable_entry_inputs": 23,
        "dates": 30, "no_decision_dates": 5, "account_paths": 12, "session_slots": 360,
        "profile_scenario_opportunity_references": 744}, "unchanged management population")
    payloads = {"projection-input-requirements.json": seal({"contract_id": CONTRACT_ID,
        "management_input_manifest_content_sha256": INPUT_MANIFEST_SHA256,
        "source_opportunity_index_content_sha256": index["content_sha256"],
        "account_session_plan_content_sha256": plan["content_sha256"], "counts": counts,
        "opportunity_windows": windows, "dates": index["dates"],
        "available_input_is_confirmed_entry": False, "historical_entry_producer": None,
        "unavailable_entry_reason_changes": 0, **BOUNDARY}),
        "executable-exit-requirements.json": exit_requirements(),
        "readiness-report.json": seal({"contract_id": CONTRACT_ID, "counts": counts,
            "descriptive_causal_primitive_registered": True, "synthetic_testing_only": True,
            "historical_projections_produced": 0, "executable_exit_requests_produced": 0,
            "historical_confirmed_entry_binding_registered": False, "executable_exit_implementation_registered": False,
            "source_tapes_reopened_in_this_stage": False, "next_gate": NEXT_GATE, **BOUNDARY})}
    files = {name: inputs.accounts._bytes(payload) for name, payload in payloads.items()}
    files["freeze-manifest.json"] = inputs.accounts._bytes(seal({"contract_id": CONTRACT_ID,
        "contract_content_sha256": expected_contract(root)["content_sha256"],
        "parent_commit_sha": PARENT_COMMIT, "management_input_manifest_content_sha256": INPUT_MANIFEST_SHA256,
        "file_inventory": {name: {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)} for name, raw in files.items()},
        "document_content_sha256": {name: p["content_sha256"] for name, p in payloads.items()},
        "next_gate": NEXT_GATE, **BOUNDARY}))
    return files


def _output(root: Path, output: Path) -> None:
    if output.is_symlink() or any(p.is_symlink() for p in output.parents):
        raise ValueError("symlink output rejected")
    if output.resolve().is_relative_to(root.resolve()) and output.resolve() != (root / OUTPUT_PATH).resolve():
        raise ValueError("cannot overwrite frozen repository inputs")


def verify_bundle(root: Path, output: Path) -> dict:
    _output(root, output)
    expected = build_bundle(root)
    inventory = inputs.accounts.availability._inventory(output)
    if set(inventory) != set(expected):
        raise ValueError("management registration inventory differs")
    for name, raw in expected.items():
        if (output / name).read_bytes() != raw:
            raise ValueError("management registration reconstruction differs: " + name)
    return seal({"verification_passed": True, "contract_id": CONTRACT_ID, "file_inventory": inventory,
        "freeze_manifest_content_sha256": frozen(output / "freeze-manifest.json")["content_sha256"], **BOUNDARY})


def write_bundle(root: Path, output: Path) -> dict:
    _output(root, output)
    if output.exists():
        raise FileExistsError("management registration is write-once")
    files = build_bundle(root)
    output.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        with (output / name).open("xb") as handle:
            if handle.write(raw) != len(raw):
                raise OSError("short metadata write")
            handle.flush()
            os.fsync(handle.fileno())
    return verify_bundle(root, output)
