"""Causal normalized-source binding and synthetic paired-account mechanics.

No provider transport or new-panel historical entry point. Immutable old-date
guards stay in their owners; passing a source hash is not provider provenance.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import timedelta
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import re

import pandas as pd

from momentumbot import indicators, micro_bars
from momentumbot.research import early_pullback_selection_v01 as selection
from momentumbot.research import prospective_daily_source as daily
from momentumbot.research import sealed_historical_account_scheduler_v01 as scheduler
from momentumbot.research import sealed_historical_account_terminal_continuation_v01 as terminal

ID = "early-pullback-paired-adapter-v0.1"
PARENT = "2a675a6adae46f384341c7dc9a4921b4f00c6606"
PARENT_TREE = "43d0b57623c58b0048869c8c6cefb0f02fe75ea7"
SELECTION_SHA = "980d7f3c8ab122fcee5f35d9da8d9a03633feb50b4e00f7287a85a0b58dd10fb"
BASE = f"research/data-audits/{ID}"
CONTRACT_PATH = f"research/strategy/{ID}.json"
OWN_FILES = ("src/momentumbot/research/early_pullback_paired_adapter_v01.py",
             "scripts/build_early_pullback_paired_adapter_v01.py",
             "tests/test_early_pullback_paired_adapter_v01.py")
ARMS = ("unchanged_micro_v0.1", "early_pullbacks_one_and_two")
require, seal, fingerprint = selection.require, selection.freeze, selection.canonical_fingerprint
producer, accounts = terminal.producer, terminal.accounts
BOUNDARY = {"synthetic_only": True, "new_panel_historical_execution_enabled": False,
            "financial_evaluation_enabled": False, "provider_access_enabled": False,
            "brokerage_orders_enabled": False, "policy_promotion_eligible": False,
            "discretionary_strategy_integrated": False}


def json_safe(value):
    return json.loads(json.dumps(value, allow_nan=False))


def _pin(value, expected, label):
    require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected),
            "external SHA-256 required: " + label)
    require(fingerprint(value) == expected, "external commitment differs: " + label)


def _frame(value, required, optional=(), *, empty=False, ties=False):
    require(isinstance(value, dict) and set(value) == {"columns", "index", "data"},
            "exact normalized frame envelope required")
    columns, stamps, rows = value["columns"], value["index"], value["data"]
    require(isinstance(columns, list) and all(isinstance(c, str) for c in columns) and
            len(columns) == len(set(columns)) and set(required) <= set(columns) <= set(required) | set(optional),
            "unexpected normalized frame columns")
    require(isinstance(stamps, list) and isinstance(rows, list) and len(stamps) == len(rows)
            and (empty or bool(rows)), "invalid normalized frame population")
    require(all(isinstance(row, list) and len(row) == len(columns) for row in rows),
            "invalid normalized frame row")
    index = pd.DatetimeIndex([selection._aware(t) for t in stamps]) if stamps else pd.DatetimeIndex([], tz="UTC")
    require(index.is_monotonic_increasing and (ties or index.is_unique), "repeated or reversed source clocks")
    frame = pd.DataFrame(rows, columns=columns, index=index)
    for key in set(columns) & {"open", "high", "low", "close", "volume", "price", "size"}:
        require(all(type(v) in (int, float) for v in frame[key]), "numeric market field required")
    if "conditions" in columns:
        require(all(isinstance(v, list) and all(isinstance(c, str) for c in v) for v in frame["conditions"]),
                "normalized condition lists required")
        require(all(v in ("A", "B", "C") for v in frame["tape"]), "normalized SIP tape required")
    return frame


def authenticate_trigger(source, *, expected_source_sha256, expected_decision_sha256,
                         expected_activation_sha256):
    """Rebuild original bars, support, setup, ordinal and first trigger from a pin.

    The caller must supply previously frozen, independent commitments. This
    verifies normalized inputs and original Micro identity. It does not verify
    scanner membership completeness, normalization factors or raw provider ZIPs.
    """
    _pin(source, expected_source_sha256, "normalized causal source")
    require(isinstance(source, dict) and set(source) ==
            {"activation", "decision", "trades", "session_minutes", "ema_warmup"},
            "exact causal source fields required")
    activation, decision = source["activation"], source["decision"]
    _pin(activation, expected_activation_sha256, "original activation")
    _pin(decision, expected_decision_sha256, "original decision")
    require(isinstance(activation, dict) and set(activation) == set(daily.ProfileActivation.__dataclass_fields__),
            "exact original activation required")
    require(isinstance(decision, dict) and set(decision) == set(daily.MicroTriggerDecision.__dataclass_fields__),
            "exact original trigger required")
    profiles = activation["eligible_strategy_profile_ids"]
    require(isinstance(profiles, list) and bool(profiles) and profiles ==
            [p for p in (daily.GENERAL_PROFILE_ID, daily.SMALL_PROFILE_ID) if p in profiles],
            "original nonempty profile union required")
    for key in ("activation_id", "symbol", "candidate_qualified_at", "eligible_strategy_profile_ids"):
        require(decision[key] == activation[key], "decision differs from original activation")
    require(isinstance(activation["scanner_record_content_sha256"], str) and
            re.fullmatch(r"[0-9a-f]{64}", activation["scanner_record_content_sha256"]),
            "original scanner row commitment required")
    qualified = selection._aware(activation["candidate_qualified_at"])
    at = selection._aware(decision["decision_at"])
    start = selection._aware(decision["plan"]["source_bar_start"])
    day = qualified.tz_convert("America/New_York").normalize()
    require(day + pd.Timedelta(hours=7) <= qualified <= start < at < day + pd.Timedelta(hours=10),
            "source clocks outside original entry session")
    trades = _frame(source["trades"], {"price", "size", "conditions", "tape"},
                    {"exchange", "id"}, ties=True)
    require(trades.index[0] >= qualified and trades.index[-1] == at,
            "trade prefix must end exactly at original trigger without future records")
    ohlcv = {"open", "high", "low", "close", "volume"}
    minutes = _frame(source["session_minutes"], ohlcv)
    warmup = _frame(source["ema_warmup"], ohlcv, empty=True)
    require(all(t == t.floor("1min") for t in minutes.index) and
            minutes.index[0] >= day and minutes.index[-1] + pd.Timedelta(minutes=1) <= start,
            "only completed same-session support bars may enter original plan prefix")
    require(warmup.empty or (warmup.index[-1] < day and all(t == t.floor("1min") for t in warmup.index)),
            "EMA warmup must be strictly prior-session completed minutes")
    bars = micro_bars.aggregate_trade_bars(trades)
    bars = bars.loc[(bars.index >= qualified) & (bars.index <= start)]
    require(not bars.empty and bars.index[-1] == start, "original plan bar absent from SIP reconstruction")
    support = indicators.completed_bar_support_series(minutes, ema_warmup=warmup)
    rebuilt = daily.build_micro_trigger_decisions(daily.ProfileActivation(**activation),
        bars=bars, trades=trades, support=support, replay_end=day + pd.Timedelta(hours=10))
    matches = [json_safe(asdict(row)) for row in rebuilt if row.plan_id == decision["plan_id"]]
    require(matches == [decision], "original plan, first trigger or complete causal-prefix hash does not reproduce")
    choice = selection.select_causal_prefix(bars[["high", "low", "volume"]],
        candidate_qualified_at=qualified, source_bar_start=start, decision_at=at)
    require(type(decision["plan"]["pullback_number"]) is int and
            choice["pullback_number"] == decision["plan"]["pullback_number"],
            "recomputed ordinal differs from original plan")
    return seal({"contract_id": ID, "artifact_type": "normalized_causal_trigger_binding",
        "source_sha256": expected_source_sha256, "original_decision_sha256": expected_decision_sha256,
        "original_activation_sha256": expected_activation_sha256,
        "original_micro_prefix_sha256": decision["micro_runtime_content_sha256"],
        "activation_id": decision["activation_id"], "plan_id": decision["plan_id"],
        "symbol": decision["symbol"], "decision_at": decision["decision_at"],
        "selection": choice, "raw_provider_archive_authenticated": False,
        "scanner_cross_section_authenticated": False, "order_authorized": False})


class _SelectedSession(terminal.Session):
    def __init__(self, slot, source, opening, resolve, bindings, arm):
        super().__init__(slot, source, opening, resolve)
        self.selection_bindings, self.arm = bindings, arm

    def decision(self, at, oid):
        binding = self.selection_bindings[oid]
        original = self.specs[oid]["entry_input"]["source_decision"]
        require(fingerprint(original) == binding["original_decision_sha256"],
                "execution decision differs from authenticated trigger")
        if self.arm == ARMS[0] or binding["selection"]["selected"]:
            return super().decision(at, oid)
        # Retain the event at its original rank/time and keep checking streams.
        # Do not emit a plan, reserve capital or consume a campaign entry.
        self.seen.add(oid)
        self.dispositions.append({"opportunity_id": oid, "disposition": "withheld_late_pullback"})
        self.event(at, 1, "opportunity_disposition", opportunity_id=oid,
            disposition="withheld_late_pullback", account_before=self.view(), order=None,
            selection_binding_sha256=binding["content_sha256"])


def _finish(slot, opening, previous, machine, failure, *, arm, binding_sha):
    """Original finisher arithmetic with an explicitly synthetic child envelope."""
    blocked = machine is None
    seen = {} if blocked else {d["opportunity_id"]: d["disposition"] for d in machine.dispositions}
    dispositions = [{**deepcopy(r), "disposition": "unavailable_input" if r["input_status"] == "unavailable"
        else seen.get(r["opportunity_id"], "blocked_prior_state" if blocked else "unprocessed_available_input")}
        for r in slot["opportunity_inputs"]]
    gaps = [{"kind": d["disposition"], "opportunity_id": d["opportunity_id"],
        "availability_content_sha256": d["availability_content_sha256"], "reason": d["reason"],
        "blocks_next_session": d["disposition"] != "unavailable_input"} for d in dispositions
        if d["disposition"] in {"unavailable_input", "unprocessed_available_input", "blocked_prior_state"}]
    failures = [] if failure is None else [failure]
    snapshot = None if blocked else machine.account.snapshot()
    pending_entry = None if blocked else machine.pending_public()
    if blocked:
        state = deepcopy(opening)
        state["unresolved_inputs"] += gaps + failures + [{"kind": "preceding_state_blocks_execution",
            "blocks_next_session": True, "previous_close_content_sha256": previous}]
        gross = net = charged = Decimal(0)
    else:
        positions, pending, extra = producer._collections(snapshot)
        if pending_entry is not None:
            pending.append(pending_entry)
        exact = snapshot["exact_account"]
        gross, net, charged = (Decimal(exact["gross_realized_pnl"]), Decimal(exact["net_realized_pnl"]),
                               Decimal(snapshot["fee_book"]["fees"]["total_charged"]))
        state = {"equity_usd": None if positions or pending else producer.money(Decimal(opening["equity_usd"]) + net),
            "buying_power_usd": producer.money(exact["remaining_buying_power"]),
            "cumulative_realized_pnl_usd": producer.money(Decimal(opening["cumulative_realized_pnl_usd"]) + net),
            "cumulative_fees_usd": producer.money(Decimal(opening["cumulative_fees_usd"]) + charged),
            "positions": positions, "pending_orders": pending,
            "campaigns": deepcopy(opening["campaigns"]) + deepcopy(snapshot["ledger"]["campaigns"]),
            "unresolved_inputs": deepcopy(opening["unresolved_inputs"]) + gaps + failures + extra}
    producer.validate_state(state)
    runtime = seal({"contract_id": ID, "arm": arm, "session_id": slot["session_id"],
        "path_id": slot["path_id"], "source_slot_content_sha256": slot["content_sha256"],
        "binding_manifest_sha256": binding_sha, "opening_account_state_sha256": fingerprint(opening),
        "blocked_before_execution": blocked, "events": [] if blocked else machine.events,
        "opportunity_dispositions": dispositions, "reconciliation_snapshot": snapshot,
        "unconfirmed_entry_order": pending_entry, "failure": failure,
        "complete_streams_verified": not blocked and machine.failure is None and not machine.heap,
        "processed_streams": [] if blocked else machine.progress(),
        "active_original_window": None if blocked or machine.active is None else
            deepcopy(machine.specs[machine.active]["entry_input"]["window"]),
        "session_gross_realized_pnl_usd": producer.money(gross),
        "session_net_realized_pnl_usd": producer.money(net), "session_fees_usd": producer.money(charged),
        "status": "blocked_prior_state" if blocked else "input_failure" if failure else
            "original_window_exhausted_with_unresolved_state" if not producer._ready(state) else
            "flat_complete_with_unavailable_inputs" if gaps else "flat_complete", **BOUNDARY})
    close = seal({"contract_id": ID, "arm": arm, "session_id": slot["session_id"], "path_id": slot["path_id"],
        "trading_date": slot["trading_date"], "session_index": slot["session_index"], "seed_applied": slot["seed_applied"],
        "source_slot_content_sha256": slot["content_sha256"], "previous_close_content_sha256": previous,
        "source_runtime_content_sha256": runtime["content_sha256"], "account_state": state,
        "next_session_flat_cash_execution_ready": producer._ready(state), **BOUNDARY})
    return {"runtime": runtime, "close": close}


def replay_synthetic_pair(program, sources, *, expected_program_sha256, expected_sources_sha256):
    """Run both arms on a pinned synthetic original-catalogue source program.

    Original date/slot/window guards are retained. All bindings are reconstructed
    before either arm executes; neither a caller-supplied decision mask nor an
    existing control balance/result is accepted.
    """
    _pin(program, expected_program_sha256, "synthetic account source program")
    _pin(sources, expected_sources_sha256, "synthetic trigger source inventory")
    selection.verify_frozen(program)
    require(set(program) == scheduler.PROGRAM_FIELDS and program["input_scope"] == "synthetic_component_fixture"
            and program["contract_id"] == scheduler.CONTRACT_ID
            and program["artifact_type"] == "chronological_account_source_program", "synthetic scheduler program only")
    scheduler._without_labels(program)
    require(isinstance(sources, dict), "exact trigger source mapping required")
    slots, sessions = program["slots"], program["sessions"]
    require(isinstance(slots, list) and len(slots) == 30 and isinstance(sessions, list)
            and 1 <= len(sessions) <= 30, "complete synthetic catalogue and chronological prefix required")
    items, bindings = {}, {}
    for i, slot in enumerate(slots):
        producer._slot(slot)
        require(slot["session_index"] == i and slot["path_id"] == program["path_id"], "slot ancestry differs")
    for slot, session in zip(slots, sessions):
        require(set(session) == {"session_id", "opportunities"} and session["session_id"] == slot["session_id"],
                "exact chronological session source required")
        refs = {r["opportunity_id"]: r for r in slot["opportunity_inputs"]}
        require(len(refs) == len(slot["opportunity_inputs"]), "duplicate slot reference")
        present = set()
        for item in session["opportunities"]:
            require(isinstance(item, dict) and set(item) == {"candidate", "position"}, "exact position item required")
            spec = item["position"]
            op = spec["entry_input"]["window"]["opportunity"]
            oid, decision = op["opportunity_id"], spec["entry_input"]["source_decision"]
            require(op["symbol"].startswith("SYNTHETIC") and decision["symbol"] == op["symbol"],
                    "synthetic symbols only; no historical activation")
            require(oid not in items and oid in refs and refs[oid]["input_status"] == "available", "unexpected source opportunity")
            require(oid in sources and set(sources[oid]) == {"source", "source_sha256", "activation_sha256"},
                    "missing or extra causal source binding")
            record = sources[oid]
            require(record["source"]["decision"] == decision, "account and Micro decision differ")
            bindings[oid] = authenticate_trigger(record["source"], expected_source_sha256=record["source_sha256"],
                expected_decision_sha256=fingerprint(decision), expected_activation_sha256=record["activation_sha256"])
            items[oid] = deepcopy(item)
            present.add(oid)
        require(present == {oid for oid, ref in refs.items() if ref["input_status"] == "available"},
                "available opportunity omitted; retain failures instead of filtering inputs")
    require(set(items) == set(sources), "extra or omitted trigger sources")
    binding_sha = fingerprint(bindings)
    initial = accounts.account_state_input(slots[0])["account_state"]
    results = {}
    with localcontext() as context:
        context.prec = 60
        for arm in ARMS:
            opening, previous, history = deepcopy(initial), None, []
            for slot in slots[:len(sessions)]:
                source = {"session_id": slot["session_id"], "opportunities": deepcopy(slot["opportunity_inputs"])}
                machine, failure = None, None
                if producer._ready(opening):
                    try:
                        machine = _SelectedSession(slot, source, opening, lambda oid: deepcopy(items[oid]), bindings, arm).run()
                        failure = machine.failure
                    except (ValueError, TypeError, OverflowError) as exc:
                        failure = {"kind": "opening_ledger_projection_unavailable", "stage": "opening_ledger",
                                   "error_type": type(exc).__name__, "error": str(exc)[:300], "blocks_next_session": True}
                pair = _finish(slot, opening, previous, machine, failure, arm=arm, binding_sha=binding_sha)
                history.append(pair)
                opening, previous = deepcopy(pair["close"]["account_state"]), pair["close"]["content_sha256"]
            results[arm] = seal({"arm": arm, "path_id": program["path_id"], "initial_account_state": deepcopy(initial),
                "seed_application_count": 1, "sessions": history, "last_close_content_sha256": previous, **BOUNDARY})
    return seal({"contract_id": ID, "artifact_type": "synthetic_paired_account_paths",
        "program_sha256": expected_program_sha256, "sources_sha256": expected_sources_sha256,
        "bindings": bindings, "binding_manifest_sha256": binding_sha, "arms": results, **BOUNDARY})


def verify_pair(program, sources, result, *, expected_program_sha256, expected_sources_sha256, expected_result_sha256):
    _pin(result, expected_result_sha256, "paired result")
    require(result == replay_synthetic_pair(program, sources, expected_program_sha256=expected_program_sha256,
            expected_sources_sha256=expected_sources_sha256), "paired replay does not reproduce")
    return seal({"verification_passed": True, "result_sha256": expected_result_sha256, **BOUNDARY})


def build_data_plan(contract):
    """Exact four-call candidate probe and staged cost gate; execution is unarmed."""
    require(contract["content_sha256"] == SELECTION_SHA, "selection registration differs")
    dates = contract["sampling"]["selected_dates"]
    first, last = pd.Timestamp(dates[0]), pd.Timestamp(dates[-1])
    requests = [
        {"provider": "alpaca", "kind": "minimal_SIP_daily_entitlement_and_date_presence", "parameters": {
            "symbols": "SPY", "timeframe": "1Day", "start": (first - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z"),
            "end": (last + timedelta(days=2)).strftime("%Y-%m-%dT00:00:00Z"), "feed": "sip",
            "adjustment": "raw", "asof": dates[-1], "limit": 1000, "sort": "asc"}},
        *[{"provider": "massive", "kind": "minimal_point_in_time_membership_sample", "parameters": {
            "market": "stocks", "locale": "us", "active": "true", "date": d, "order": "asc", "sort": "ticker", "limit": 1}}
          for d in (dates[0], dates[-1])],
        {"provider": "databento", "kind": "dataset_range_metadata", "parameters": {
            "dataset": "XNAS.ITCH", "method": "metadata.get_dataset_range"}},
    ]
    return seal({"contract_id": ID, "artifact_type": "unarmed_new_panel_availability_and_cost_plan",
        "selection_registration_sha256": SELECTION_SHA, "selected_dates": dates,
        "planned_probe_requests": requests, "maximum_probe_calls_if_separately_authorized": 4,
        "authorized_calls_now": 0, "automatic_retry_or_pagination": False,
        "raw_probe_rows_persisted": False, "probe_result_projection": "availability status, counts and dates only; no prices, tickers or outcomes",
        "probe_proves": "limited endpoint entitlement and interval evidence, not complete cross-section or full-session coverage",
        "incremental_spend_authorized_usd": "0.00", "actual_incremental_cost_known": False,
        "later_capture_order": ["independently confirm every full session and bind new catalogue without changing ancestor guards",
            "point-in-time universe/identity/corporate-action/float/news and causal cross-section source plan",
            "shared SIP/minute capture and all original Micro triggers; same union for both arms",
            "exact trigger-bound quote/status and management request manifest",
            "metadata quote with per-request/total ceilings and separate one-shot approval",
            "capture once, byte-verify, then run all paired paths before outcome evaluation"],
        "bulk_request_count": None, "bulk_cost_usd": None,
        "unknown_cost_response": "no guessed dollar estimate or unbounded acquisition; freeze exact requests and quote first",
        "new_catalogue_adapter_implemented": False, "provider_transport_implemented": False,
        "credential_route": "reuse validated main Alpaca routing; never inspect or persist secret values",
        "changed_dates_or_replacements_allowed": False, **BOUNDARY})


def registration(root: Path):
    parent = selection.validate_registration(root)
    require(parent["content_sha256"] == SELECTION_SHA, "frozen selection parent differs")
    terminal.validate_registration(root)
    inherited = terminal.expected_contract(root)
    protected = set(inherited["frozen_parent_file_sha256"]) | set(inherited["implementation_file_sha256"])
    protected.update((selection.CONTRACT_PATH, selection.EXCLUSION_PATH, *selection.OWN_FILES,
                      "src/momentumbot/indicators.py", "src/momentumbot/micro_bars.py",
                      "src/momentumbot/research/prospective_daily_source.py"))
    bindings = {}
    for path in sorted(protected | set(OWN_FILES)):
        raw = (root / path).read_bytes()
        bindings[path] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    return seal({"contract_id": ID, "parent_commit": PARENT, "parent_tree": PARENT_TREE,
        "parent_selection_sha256": SELECTION_SHA, "artifact_type": "synthetic_source_binding_and_paired_replay_registration",
        "hypothesis": "normalized causal source commitments reproduce original triggers, and one eligibility gate can produce independent chronological account paths without changed execution mechanics",
        "file_bindings": bindings, "data_plan_sha256": build_data_plan(parent)["content_sha256"],
        "hybrid_objective": "component evidence on an incomplete deterministic baseline; discretionary context and other crucial components remain required research, with full-system edge and profitability unestablished",
        "transcript_use": "offline versioned design clarification only; no recap, fills, labels or later outcomes in replay; do not consult registered evaluation dates to tune this frozen experiment",
        "source_limits": "normalized commitment, bars/support and complete original Micro-prefix reproduction; raw archive provenance, normalization factor and scanner cross-section remain separate dependencies",
        "date_limit": "synthetic account mechanics retain the original ancestor catalogue; the new 30 dates are not mapped onto it",
        "decision_priority": "late-pullback eligibility withhold before original capacity/risk decision; original timestamp/rank retained; streams still checked",
        "unchanged": "all parent code, old baseline, first-two registration and dates, execution/risk/fees/management, and hosted-only local-replay waiver",
        "next_gate": "new-catalogue/source adapter and separately authorized exact four-call availability probe; no paid capture before quoted request ceilings",
        **BOUNDARY})


def validate_registration(root: Path):
    saved = json.loads((root / CONTRACT_PATH).read_bytes())
    require(saved == registration(root), "paired adapter registration or file binding differs")
    plan = json.loads((root / BASE / "data-plan.json").read_bytes())
    require(plan == build_data_plan(selection.validate_registration(root)), "new-panel data plan differs")
    return saved
