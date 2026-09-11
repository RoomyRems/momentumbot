"""Isolated context bridge to the frozen final account engine.

The copied methods below preserve ancestor mechanics. Tests compare their ASTs
with the exact parents, allowing only the explicitly listed context substitutions.
No module globals are patched, no dates are remapped, and no ancestor is edited.
Entry evidence retains the original mechanics contract ID; paths, opportunities,
session contexts and outer runtime/close envelopes identify the new panel.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal, localcontext
import math
from zoneinfo import ZoneInfo
import pandas as pd

from momentumbot.models import CandidateQuality, CandidateSnapshot
from momentumbot.research import early_pullback_panel_accounts_v01 as context
from momentumbot.research import sealed_historical_account_continuity_v01 as continuity
from momentumbot.research import sealed_historical_account_scheduler_v01 as scheduler
from momentumbot.research import sealed_historical_account_terminal_continuation_v01 as terminal
from momentumbot.research.account_priority_policy import ScarceCapitalOpportunity
from momentumbot.research.campaign_portfolio import AccountClass, CampaignPortfolioLedger, EntryRole, EntryFill, PlanEmission

parent = producer = context.producer
accounts, feedback, fees, runner = continuity.accounts, continuity.feedback, continuity.fees, continuity.runner
canonical_fingerprint = fingerprint = context.fingerprint
seal, require, validate_slot = context.seal, context.require, context.validate_slot
require_exact = producer.require_exact
validate_state, _projection = producer.validate_state, producer._projection
_entry_role, _entry_block = continuity._entry_role, continuity._entry_block
# Mechanical entry IDs retain the same schema in both prepare and reconciliation.
CONTRACT_ID = continuity.CONTRACT_ID
ID, BOUNDARY, ARMS = context.ID, context.BOUNDARY, context.parent.ARMS
_NetLedger, _decimal, ZERO = fees._NetLedger, fees._decimal, fees.ZERO
CANDIDATE_FIELDS = scheduler.CANDIDATE_FIELDS
current_general_2026 = continuity.valuation.current_general_2026
current_small_account_2026 = continuity.valuation.current_small_account_2026


def session_start_ns(slot):
    validate_slot(slot)
    profile = current_general_2026() if slot["account_key"] == "main_account" else current_small_account_2026()
    start = datetime.combine(date.fromisoformat(slot["trading_date"]), profile.session_start, ZoneInfo("America/New_York"))
    return int(start.timestamp()) * 1_000_000_000



def _new_day(slot, opening):
    validate_state(opening)
    kind = AccountClass.MAIN if slot["account_key"] == "main_account" else AccountClass.SMALL
    seed = validate_slot(slot)
    constraints = fees.feedback.materialize_account_constraints(fees.feedback.paper_account_policy(kind),
        account_id=seed["account_id"], starting_equity=_projection(opening["equity_usd"], "equity"),
        starting_buying_power=_projection(opening["buying_power_usd"], "buying power"))
    ledger = CampaignPortfolioLedger(date.fromisoformat(slot["trading_date"]), constraints)
    return _AccountDay(pre_session_ledger=ledger,
        expected_pre_session_ledger_sha256=canonical_fingerprint(ledger.runtime_artifact()),
        path_id=slot["path_id"], scenario_id=slot["execution_scenario_id"])


_day = _new_day


def _candidate(row, op, slot):
    if not isinstance(row, dict) or set(row) != CANDIDATE_FIELDS:
        raise ValueError("exact causal candidate fields required")
    stamp = pd.Timestamp(row["timestamp"])
    if (pd.isna(stamp) or stamp.tzinfo is None or int(stamp.value) != op["candidate_qualified_ts_ns"]
            or int(stamp.value) > op["decision_ts_ns"] or row["symbol"] != op["symbol"]):
        raise ValueError("candidate must bind original activation time and symbol")
    for key in ("price", "relative_volume", "percent_gain"):
        value = row[key]
        if type(value) not in (int, float) or not math.isfinite(value) or (key != "percent_gain" and value < 0):
            raise ValueError("finite causal candidate numbers required")
    if row["price"] <= 0 or type(row["cumulative_volume"]) is not int or row["cumulative_volume"] < 0:
        raise ValueError("valid candidate price and volume required")
    for key in ("float_shares", "top_gainer_rank"):
        if row[key] is not None and (type(row[key]) is not int or row[key] <= 0):
            raise ValueError("positive candidate float/rank required")
    if (type(row["has_fresh_news"]) is not bool or not isinstance(row["pillars"], dict)
            or any(type(v) is not bool for v in row["pillars"].values())
            or not isinstance(row["reasons"], list) or any(not isinstance(v, str) for v in row["reasons"])):
        raise ValueError("exact candidate flags required")
    snapshot = CandidateSnapshot(**{k: v for k, v in row.items() if k not in {"timestamp", "quality", "reasons"}},
        timestamp=stamp, quality=CandidateQuality(row["quality"]), reasons=tuple(row["reasons"]),
        float_rotation=None if row["float_shares"] is None else row["cumulative_volume"] / row["float_shares"])
    kind = AccountClass.MAIN if slot["account_key"] == "main_account" else AccountClass.SMALL
    return ScarceCapitalOpportunity(op["opportunity_id"], validate_slot(slot)["account_id"], kind,
        op["activation_id"], op["plan_id"], pd.Timestamp(op["decision_ts_ns"], unit="ns", tz="UTC"), snapshot)


def _validate_entry_context(*, window, slot, source_decision, expected_context_sha256,
                            pre_entry_ledger, expected_pre_ledger_sha256, tape, expected_tape_sha256):
    """Frozen context preflight with the isolated flat re-entry eligibility delta."""
    feedback._pinned({"window": window, "slot": slot, "source_decision": source_decision}, expected_context_sha256, "entry context")
    feedback.parent.validate_window(window)
    seed = validate_slot(slot)
    op = window["opportunity"]
    if set(source_decision) != accounts.availability.plan.DECISION_FIELDS:
        raise ValueError("exact original decision fields required")
    if window["entry_input_status"] != "available":
        raise ValueError("unavailable opportunity cannot become an entry")
    expected_profile = "current-general-2026" if slot["account_key"] == "main_account" else "current-small-account-2026"
    if slot["profile_id"] != expected_profile or expected_profile not in op["eligible_strategy_profile_ids"]:
        raise ValueError("entry profile differs from account path")
    refs = [r for r in slot["opportunity_inputs"] if r["opportunity_id"] == op["opportunity_id"]]
    if len(refs) != 1 or refs[0]["input_status"] != "available" or refs[0]["availability_content_sha256"] != window["availability_content_sha256"] or refs[0]["reason"] != window["entry_input_reason"]:
        raise ValueError("entry availability is not bound to the session slot")
    if slot["trading_date"] != op["trading_date"] or canonical_fingerprint(source_decision) != op["source_decision_content_sha256"]:
        raise ValueError("original decision or session differs")
    for key in ("activation_id", "plan_id", "symbol", "micro_runtime_content_sha256"):
        if source_decision[key] != op[key]:
            raise ValueError("original decision identity differs")
    if source_decision["eligible_strategy_profile_ids"] != op["eligible_strategy_profile_ids"]:
        raise ValueError("original profile membership differs")
    if source_decision["plan_id"] != "plan-" + canonical_fingerprint({"activation_id": source_decision["activation_id"], "plan": source_decision["plan"]}):
        raise ValueError("original plan identity differs")
    stamps = {key: pd.Timestamp(source_decision[key]) for key in ("decision_at", "candidate_qualified_at")}
    stamps.update({key: pd.Timestamp(source_decision["plan"][key]) for key in ("source_bar_start", "armed_at", "expires_at")})
    if any(pd.isna(t) or t.tzinfo is None for t in stamps.values()):
        raise ValueError("original decision and plan times must be aware")
    if (int(stamps["decision_at"].value) != op["decision_ts_ns"]
            or int(stamps["candidate_qualified_at"].value) != op["candidate_qualified_ts_ns"]
            or not stamps["candidate_qualified_at"] <= stamps["source_bar_start"]
            or stamps["armed_at"] != stamps["source_bar_start"] + pd.Timedelta(seconds=10)
            or stamps["expires_at"] != stamps["source_bar_start"] + pd.Timedelta(seconds=20)
            or not stamps["armed_at"] <= stamps["decision_at"] < stamps["expires_at"]
            or source_decision["plan"]["symbol"] != op["symbol"]):
        raise ValueError("original decision or plan timing differs")
    stop = feedback.parent._price(source_decision["plan"]["stop_price"], "original stop")
    if not isinstance(pre_entry_ledger, CampaignPortfolioLedger):
        raise ValueError("frozen ledger required")
    before = pre_entry_ledger.runtime_artifact()
    feedback._pinned(before, expected_pre_ledger_sha256, "pre-entry ledger")
    ledger = deepcopy(pre_entry_ledger)
    constraints = ledger.constraints
    if ledger.session_date.isoformat() != slot["trading_date"] or constraints.account_id != seed["account_id"]:
        raise ValueError("ledger account or session differs")
    expected_constraints = feedback.materialize_account_constraints(feedback.paper_account_policy(constraints.account_class),
        account_id=seed["account_id"], starting_equity=constraints.starting_equity,
        starting_buying_power=constraints.starting_buying_power)
    if constraints != expected_constraints or constraints.account_class.value != ("main" if slot["account_key"] == "main_account" else "small"):
        raise ValueError("frozen account risk constraints differ")
    if slot["seed_applied"] and (constraints.starting_equity != float(seed["equity_usd"]) or constraints.starting_buying_power != float(seed["buying_power_usd"])):
        raise ValueError("first-session seed differs")
    if ledger.open_campaign_count or ledger.locked:
        raise ValueError("entry requires an unlocked flat account")
    reason = _entry_block(ledger, op)
    if reason is not None:
        raise ValueError(reason)
    _entry_role(ledger, op)
    return ledger, stop, op


def bind_entry_evidence(**args):
    """Recompute entry with the untouched sizing/execution/ledger acceptance rules."""
    ledger, stop, op = _validate_entry_context(**args)
    window, slot, tape = args["window"], args["slot"], args["tape"]
    expected_tape_sha256 = args["expected_tape_sha256"]
    expected_context_sha256 = args["expected_context_sha256"]
    expected_pre_ledger_sha256 = args["expected_pre_ledger_sha256"]
    constraints, role = ledger.constraints, _entry_role(ledger, op)
    policy, offset = feedback.SCENARIOS[slot["execution_scenario_id"]]
    quotes, reference, capture_sha = feedback._quote_window(window, op["decision_ts_ns"], tape, expected_tape_sha256)
    limit = feedback.execution.marketable_limit_price(reference.ask_price, side=feedback.execution.OrderSide.BUY, offset_ticks=offset)
    ledger.record_plan_emission(PlanEmission(op["activation_id"], op["plan_id"], op["symbol"], pd.Timestamp(op["decision_ts_ns"], unit="ns", tz="UTC")))
    quantity = feedback.maximum_whole_share_quantity(ledger, activation_id=op["activation_id"], fill_price=float(limit), stop_price=stop, role=role)
    if quantity < 1:
        raise ValueError("entry has no whole-share capacity")
    order_id = "entry-" + canonical_fingerprint({"contract_id": CONTRACT_ID, "path_id": slot["path_id"], "context": expected_context_sha256,
        "pre_ledger": expected_pre_ledger_sha256, "quantity": quantity, "limit": str(limit)})
    order = feedback.execution.MarketableLimitOrder(order_id, op["symbol"], feedback.execution.OrderSide.BUY, quantity, op["decision_ts_ns"], limit)
    outcome = feedback.adapter.simulate_record_order_limit_order(order, quotes, policy)
    if outcome.filled_quantity < 1:
        raise ValueError("entry execution is not a confirmed positive fill")
    source = feedback._selected_quote(order, quotes, policy, outcome)
    payload = feedback._execution_payload(outcome)
    fill_id = "fill-" + canonical_fingerprint({"order_id": order_id, "execution": payload})
    accepted = ledger.apply_entry_fill(EntryFill(fill_id=fill_id, activation_id=op["activation_id"], plan_id=op["plan_id"], symbol=op["symbol"],
        filled_at=pd.Timestamp(outcome.fill_ts_ns, unit="ns", tz="UTC"), quantity=outcome.filled_quantity,
        reference_price=float(reference.ask_price), fill_price=float(outcome.fill_price), stop_price=stop, role=role, execution_approved=True))
    if not accepted.accepted:
        raise ValueError("entry rejected by frozen ledger: " + ",".join(accepted.reasons))
    after = ledger.runtime_artifact()
    events = [e for e in after["events"] if e["event_type"] == "entry_accepted" and e.get("fill_id") == fill_id]
    if len(events) != 1:
        raise ValueError("unique accepted entry evidence required")
    return seal({"contract_id": CONTRACT_ID, "artifact_type": "mechanically_bound_campaign_entry_evidence",
        "context_content_sha256": expected_context_sha256, "pre_ledger_content_sha256": expected_pre_ledger_sha256,
        "post_ledger_content_sha256": canonical_fingerprint(after), "account_id": constraints.account_id,
        "path_id": slot["path_id"], "session_id": slot["session_id"], "scenario_id": policy.policy_id,
        "opportunity_id": op["opportunity_id"], "activation_id": op["activation_id"], "plan_id": op["plan_id"],
        "symbol": op["symbol"], "trading_date": op["trading_date"], "fill_id": fill_id,
        "quantity": outcome.filled_quantity, "fill_time_ns": outcome.fill_ts_ns, "fill_price": str(outcome.fill_price),
        "initial_stop_price": stop, "entry_cancel_ack_ns": outcome.cancel_ack_ts_ns,
        "order": {"order_id": order_id, "quantity": quantity, "limit_price": str(limit)}, "execution": payload,
        "accepted_ledger_event": events[0], "tape_content_sha256": expected_tape_sha256, "capture_content_sha256": capture_sha,
        "fill_quote_source": {"source_request_sha256": source.source_request_sha256, "source_record_index": source.source_record_index},
        "entry_role": role.value, "entry_mechanics_verified": True, "historical_producer_authenticated": False, "historical_runtime_authorized": False})


class _Management(terminal.Management):
    def __init__(self, **entry_arguments):
        self._entry = bind_entry_evidence(**entry_arguments)
        self._window = deepcopy(entry_arguments["window"])
        self._policy, self._offset = feedback.SCENARIOS[self._entry["scenario_id"]]
        self._remaining = self._entry["quantity"]
        self._target_quantity = self._remaining // 2
        self._target_filled = 0
        self._fill = float(self._entry["fill_price"])
        self._stop = self._entry["initial_stop_price"]
        self._target = round(self._fill + 2.0 * (self._fill - self._stop), 10)
        if not math.isfinite(self._target) or self._target <= 0:
            raise ValueError("finite positive target required")
        self._red = None
        self._latched = None
        self._target_attempted = self._full_attempted = False
        self._pending = self._intent = None
        self._clock = (self._entry["fill_time_ns"], -1)
        self._stream_positions = {}
        self._source_positions = {}
        self._sell_tape_sha = None
        self._sell_tape_content_sha = None
        self._used_liquidity = set()
        self._events = []
        self._fills = []
        self._init_waiting()
        self._init_residual()
        self._init_continuation()


class DailyFeeAccumulator(fees.DailyFeeAccumulator):
    def __init__(self, *, account_id: str, path_id: str, scenario_id: str, trading_date: date):
        if any(not isinstance(v, str) or not v.strip() for v in (account_id, path_id)):
            raise ValueError("nonempty account and path required")
        if scenario_id not in feedback.SCENARIOS:
            raise ValueError("unregistered execution scenario")
        self._schedule = context.fee_schedule(trading_date)
        self._identity = {"account_id": account_id, "path_id": path_id, "scenario_id": scenario_id,
                          "trading_date": trading_date.isoformat()}
        self._day = trading_date
        self._trades = []

    def snapshot(self):
        value = super().snapshot()
        value.pop("content_sha256")
        value.update(contract_id=ID, fee_mechanics_contract_id=fees.CONTRACT_ID,
            modeled_schedule={k: str(v) for k, v in asdict(self._schedule).items()},
            dated_fee_context=True, broker_statement_equivalence_verified=False)
        return seal(value)


class _AccountDay(terminal.AccountDay):
    def __init__(self, *, pre_session_ledger, expected_pre_session_ledger_sha256: str,
                 path_id: str, scenario_id: str):
        if type(pre_session_ledger) is not CampaignPortfolioLedger:
            raise ValueError("original frozen session ledger required")
        feedback._pinned(pre_session_ledger.runtime_artifact(), expected_pre_session_ledger_sha256, "opening ledger")
        blank = CampaignPortfolioLedger(pre_session_ledger.session_date, pre_session_ledger.constraints)
        if pre_session_ledger.__dict__ != blank.__dict__:
            raise ValueError("opening ledger must be empty; imported history requires authenticated producer")
        self._ledger = _NetLedger(blank.session_date, blank.constraints)
        self._book = DailyFeeAccumulator(account_id=blank.constraints.account_id, path_id=path_id,
                                         scenario_id=scenario_id, trading_date=blank.session_date)
        self._opening_sha = expected_pre_session_ledger_sha256
        self._cash = _decimal(str(blank.constraints.starting_buying_power), "starting cash", positive=True)
        self._gross = self._net = self._high = ZERO
        self._positions = {}
        self._journal = []
        self._completed = []
        self._engine = None
        self._applied = 0
        self._clock = None
        self._released_liquidity = set()
        self._exit_wait_events = []
        self._exit_residual_events = []
        self._exit_continuation_events = []

    def _start(self, args):
        slot = args["slot"]
        identity = self._book._identity
        if (slot["path_id"] != identity["path_id"] or slot["execution_scenario_id"] != identity["scenario_id"]
                or slot["trading_date"] != identity["trading_date"]):
            raise ValueError("entry account path, scenario or date differs")
        if args["pre_entry_ledger"].__dict__ != self._ledger.__dict__:
            # An original pristine base ledger is equivalent before the first
            # entry; following entries must use the complete net ledger copy.
            if self._journal or args["pre_entry_ledger"].runtime_artifact() != self._ledger.runtime_artifact():
                raise ValueError("entry must bind current net account ledger")
        decision_ns = args["window"]["opportunity"]["decision_ts_ns"]
        if self._clock is not None and (decision_ns, 1) <= self._clock:
            raise ValueError("next position decision must follow prior account clock")
        engine = _Management(**args)
        entry = engine.snapshot()["entry"]
        if entry["account_id"] != identity["account_id"]:
            raise ValueError("entry account differs")
        _, reference, _ = feedback._quote_window(args["window"], decision_ns, args["tape"], args["expected_tape_sha256"])
        self._ledger.record_plan_emission(PlanEmission(entry["activation_id"], entry["plan_id"], entry["symbol"],
                                                       pd.Timestamp(decision_ns, unit="ns", tz="UTC")))
        accepted = self._ledger.apply_entry_fill(EntryFill(fill_id=entry["fill_id"], activation_id=entry["activation_id"],
            plan_id=entry["plan_id"], symbol=entry["symbol"], filled_at=fees._timestamp(entry["fill_time_ns"], self._book._day),
            quantity=entry["quantity"], reference_price=float(reference.ask_price), fill_price=float(entry["fill_price"]),
            stop_price=entry["initial_stop_price"], role=EntryRole(entry["entry_role"]), execution_approved=True))
        if not accepted.accepted or canonical_fingerprint(self._ledger.runtime_artifact()) != entry["post_ledger_content_sha256"]:
            raise ValueError("reconstructed entry differs from frozen accepted ledger")
        engine._used_liquidity = set(self._released_liquidity)
        self._engine, self._applied = engine, 0
        self._clock = (entry["fill_time_ns"], -1)
        self._record(entry, side="buy", entry=entry)
        self._ledger._apply_session_guards(fees._timestamp(entry["fill_time_ns"], self._book._day))
        self._check()
        return self._journal[-1]


def _prepare(account, slot, spec):
    """Private execution preparation; never return this object in public state.

    Frozen context checks and sizing precede submission. Simulated outcomes
    stay private, and even fill-reconciliation errors are deferred to feedback.
    """
    args = parent._entry_arguments(account, slot, spec["entry_input"])
    parent._exit_evidence(args, spec)
    ledger, stop, op = _validate_entry_context(**args)
    policy, offset = feedback.SCENARIOS[slot["execution_scenario_id"]]
    quotes, reference, capture = feedback._quote_window(args["window"], op["decision_ts_ns"], args["tape"], args["expected_tape_sha256"])
    limit = feedback.execution.marketable_limit_price(reference.ask_price, side=feedback.execution.OrderSide.BUY, offset_ticks=offset)
    ledger.record_plan_emission(PlanEmission(op["activation_id"], op["plan_id"], op["symbol"], pd.Timestamp(op["decision_ts_ns"], unit="ns", tz="UTC")))
    quantity = feedback.maximum_whole_share_quantity(ledger, activation_id=op["activation_id"], fill_price=float(limit),
        stop_price=stop, role=_entry_role(ledger, op))
    if quantity < 1:
        return None
    order_id = "entry-" + canonical_fingerprint({"contract_id": CONTRACT_ID, "path_id": slot["path_id"],
        "context": args["expected_context_sha256"], "pre_ledger": args["expected_pre_ledger_sha256"], "quantity": quantity, "limit": str(limit)})
    order = feedback.execution.MarketableLimitOrder(order_id, op["symbol"], feedback.execution.OrderSide.BUY, quantity, op["decision_ts_ns"] , limit)
    outcome = feedback.adapter.simulate_record_order_limit_order(order, quotes, policy)
    public = {"order_id": order_id, "quantity": quantity, "limit_price": str(limit),
        "decision_ts_ns": op["decision_ts_ns"], "arrival_ts_ns": outcome.arrival_ts_ns,
        "cancel_requested_ts_ns": outcome.cancel_requested_ts_ns, "cancel_ack_ts_ns": outcome.cancel_ack_ts_ns,
        "capture_content_sha256": capture}
    ticks = {public[k] for k in ("arrival_ts_ns", "cancel_requested_ts_ns", "cancel_ack_ts_ns")}
    ticks.update(q.ts_recv_ns for q in quotes if outcome.arrival_ts_ns < q.ts_recv_ns < outcome.cancel_ack_ts_ns)
    return {"public": public, "outcome": outcome, "arguments": args, "applied": False, "ticks": ticks,
        "unreconciled_execution_feedback": None}


class Session(terminal.Session):
    def __init__(self, slot, source, opening, resolve, bindings, arm):
        self.slot, self.source, self.opening = slot, source, deepcopy(opening)
        self.account = _day(slot, opening)
        self.heap, self.serial, self.events, self.dispositions = [], 0, [], []
        self.specs, self.cursors, self.quote_times, self.rank = {}, {}, {}, {}
        self.pending, self.active = None, None
        self.stage, self.failure, self.seen = "source_registration", None, set()
        self.initialized = False
        self.processed = {}
        self.through_ns = None
        self.resolve = resolve
        self.selection_bindings, self.arm = bindings, arm

    def initialize(self):
        require_exact(self.source, {"session_id": self.slot["session_id"],
            "opportunities": self.slot["opportunity_inputs"]}, "complete original session source")
        ranked = []
        for ref in self.source["opportunities"]:
            if ref["input_status"] == "unavailable":
                continue
            oid = ref["opportunity_id"]
            item = self.resolve(oid)
            if set(item) != {"candidate", "position"}:
                raise ValueError("exact resolved candidate and position required")
            spec = item["position"]
            if set(spec) != producer.POSITION_FIELDS or set(spec["entry_input"]) != producer.ENTRY_FIELDS:
                raise ValueError("exact original position source fields required")
            window = spec["entry_input"]["window"]
            continuity.feedback.parent.validate_window(window)
            op = window["opportunity"]
            if (op["opportunity_id"] != oid or oid in self.specs or window["availability_content_sha256"] != ref["availability_content_sha256"]
                    or window["entry_input_reason"] != ref["reason"]):
                raise ValueError("resolved source differs from original availability")
            if op["decision_ts_ns"] < session_start_ns(self.slot) or op["trading_date"] != self.slot["trading_date"]:
                raise ValueError("opportunity must follow frozen session start")
            ranked.append(_candidate(item["candidate"], op, self.slot))
            self.specs[oid] = spec
        for ordinal, item in enumerate(scheduler.order_scarce_capital_opportunities(ranked)):
            oid = item.opportunity_id
            self.rank[oid] = ordinal
            spec = self.specs[oid]
            op = spec["entry_input"]["window"]["opportunity"]
            self.push(op["decision_ts_ns"], 1, ordinal, "decision", oid)
            self.push(spec["entry_input"]["window"]["end_ns"] - 1, 4, ordinal, "boundary", oid)
            for name, resource in (("bars", "raw_sip_1m_bars"), ("trades", "sip_transactions")):
                cursor = runner._Cursor(spec[name], spec["entry_input"]["window"], resource, spec["expected_streams"][resource])
                self.cursors[(oid, resource)] = cursor
                self.push_cursor(oid, cursor)

    def decision(self, at, oid):
        binding = self.selection_bindings[oid]
        original = self.specs[oid]["entry_input"]["source_decision"]
        require(fingerprint(original) == binding["original_decision_sha256"],
                "execution decision differs from authenticated trigger")
        if self.arm == ARMS[0] or binding["selection"]["selected"]:
            return self._mechanical_decision(at, oid)
        # Retain the event at its original rank/time and keep checking streams.
        # Do not emit a plan, reserve capital or consume a campaign entry.
        self.seen.add(oid)
        self.dispositions.append({"opportunity_id": oid, "disposition": "withheld_late_pullback"})
        self.event(at, 1, "opportunity_disposition", opportunity_id=oid,
            disposition="withheld_late_pullback", account_before=self.view(), order=None,
            selection_binding_sha256=binding["content_sha256"])

    def _mechanical_decision(self, at, oid):
        before = self.view()
        self.seen.add(oid)
        spec = self.specs[oid]
        op = spec["entry_input"]["window"]["opportunity"]
        ledger = self.account.ledger_copy()
        if before["capacity_reserved"]:
            disposition = "blocked_capacity"
        elif before["account_locked"]:
            disposition = "blocked_account_lock"
        elif _entry_block(ledger, op) is not None:
            disposition = _entry_block(ledger, op)
        else:
            self.stage = "entry_source_and_execution"
            pending = _prepare(self.account, self.slot, spec)
            disposition = "no_whole_share_capacity" if pending is None else "entry_submitted"
            if pending is not None:
                pending["oid"] = oid
                self.pending = pending
                self.quote_times[oid] = parent._exit_evidence(parent._entry_arguments(self.account, self.slot, spec["entry_input"]), spec)
                for stamp in pending["ticks"]:
                    self.push(stamp, 3, self.rank[oid], "feedback", oid)
        self.dispositions.append({"opportunity_id": oid, "disposition": disposition})
        self.event(at, 1, "opportunity_disposition", opportunity_id=oid, disposition=disposition, account_before=before,
            order=None if disposition != "entry_submitted" else self.pending["public"])


def finish(slot, opening, previous, machine, failure, *, arm, binding_sha):
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
