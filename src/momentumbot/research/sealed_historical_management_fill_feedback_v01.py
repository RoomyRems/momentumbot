"""Entry-evidence binding and whole-share management, tested on synthetic inputs.

These primitives verify mechanics against caller-pinned evidence. They do not
authenticate a historical producer, open source tapes, or run an account. No
historical entry/exit runner or fee/valuation authority is registered here.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import hashlib
import math
import os
from pathlib import Path

import pandas as pd

from momentumbot.research import execution_realism as execution
from momentumbot.research import sealed_historical_management_projection_v01 as parent
from momentumbot.research import sealed_historical_record_order_v01 as adapter
from momentumbot.research.account_chronological_integration import maximum_whole_share_quantity
from momentumbot.research.account_priority_policy import materialize_account_constraints, paper_account_policy
from momentumbot.research.campaign_portfolio import CampaignPortfolioLedger, EntryFill, EntryRole, PlanEmission
from momentumbot.research.prospective_daily_account_runtime import _decision_quote, _execution_payload
from momentumbot.research.sealed_historical_execution_quote_v01 import canonical_fingerprint, file_sha, frozen, require_exact, seal

CONTRACT_ID = "sealed-historical-management-fill-feedback-v0.1"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
OUTPUT_PATH = f"research/runtime/{CONTRACT_ID}"
MODULE_PATH = "src/momentumbot/research/sealed_historical_management_fill_feedback_v01.py"
SCRIPT_PATH = "scripts/build_sealed_historical_management_fill_feedback_v01.py"
TEST_PATH = "tests/test_sealed_historical_management_fill_feedback_v01.py"
WORKFLOW_PATH = ".github/workflows/sealed-historical-management-fill-feedback-v01.yml"
PARENT_COMMIT = "75cacb70c9fc6fcc1465b5a3f65d991bad0b45bb"
PARENT_TREE = "e13b1249d76cdae67ab49468c5b922320d6b75f1"
PARENT_FREEZE = "0fef2f3bf29a3439dfa07d58a8fa189294f533197f53d70bc7939e186280960d"
BOUNDARY = dict(parent.BOUNDARY)
NEXT_GATE = "register_historical_entry_management_runner_and_exact_exit_evidence_with_historical_fees_and_causal_valuation_dependencies"
PARENT_PINS = {
    "research/data-audits/sealed-historical-management-projection-v0.1-independent-verification.json": "ec712e11e5fa66e035507900115dcadac1fdd6ffba8f4f5f55a24532ab2e5f19",
    parent.CONTRACT_PATH: "898bf4d7335a401d7f1962f9de48ee1956d5c2ac96ae9cd4b30d915d933a0a61",
    parent.MODULE_PATH: "1741df5539180eed155c1b2160c7f9fccafdef869939da8330345aa56e548331",
    "src/momentumbot/research/sealed_historical_record_order_v01.py": "407e02fc6fe908e26715fac2799f0debf356e96336b640e795b50287762dec6b",
    "src/momentumbot/research/execution_realism.py": "446509405e3f44e3924c852569c5b06a096f61330552ede850a55c3da5794177",
    "src/momentumbot/research/campaign_portfolio.py": "5e8b5fb8e42cc739b8337bb544b811e57ccda2df5e7f46ca65ef5a30472149c4",
    "src/momentumbot/research/account_chronological_integration.py": "917257a23abba6a075f6ba1fb97b5a01fb2729dfd63d8c90f7655d6d590afe41",
    "src/momentumbot/research/account_priority_policy.py": "3c0254bcd06425670e7158fb6c2be44edaa6c6f4b74c045798148f9d43e250d7",
    "src/momentumbot/research/prospective_daily_account_runtime.py": "45473afe1b947d56fd794ca80a9f72cc7934ca446a161ecb3c7f6ab1e4080d2a",
    "src/momentumbot/research/sealed_historical_account_inputs_v01.py": "b7a28487807dd5d841a205d6ab74429fb3ed5f0f74b345712c57579e360228dd",
    "requirements-sealed-execution-quote-v01.txt": "03f4da335027e4c83bcf38e523c2e11aeaae49778f5bd6caa47e4703348b31b4",
}
SCENARIOS = {
    "l1-conservative-v0.1": (execution.BASELINE_CONSERVATIVE_POLICY, execution.BASELINE_LIMIT_OFFSET_TICKS),
    "l1-stress-v0.1": (execution.STRESS_POLICY, execution.STRESS_LIMIT_OFFSET_TICKS),
}
accounts = parent.inputs.accounts


def mechanics() -> dict:
    return {
        "entry_binding": "recompute_frozen_L1_fill_and_accept_in_copied_frozen_pre_entry_ledger",
        "external_trust": "caller_pins_context_tape_and_pre_ledger_but_historical_producer_authentication_is_not_supplied",
        "single_entry_only": True,
        "target_quantity": "floor_confirmed_entry_shares_divided_by_two",
        "one_share": "no_target_order_or_breakeven_only_original_stop_or_completed_red",
        "breakeven": "only_after_entire_intended_target_tranche_is_confirmed_filled",
        "target_attempts": "one_marketable_limit_attempt_no_automatic_retry",
        "full_exit_attempts": "one_marketable_limit_attempt_no_automatic_retry_partial_remainder_stays_open_unresolved",
        "pending_order": "reserve_all_requested_shares_until_fill_then_cancel_acknowledgement",
        "competing_exit": "latch_stop_or_red_during_target_attempt_submit_remaining_only_on_next_eligible_print_after_ack",
        "liquidity": "all_sells_use_one_pinned_complete_tape_original_row_identity_cannot_be_spent_twice",
        "clock": "bar_close_before_SIP_print_before_equal_time_fill_and_cancel_feedback",
        "entry_clock": "all_SIP_prints_at_or_before_entry_fill_are_excluded",
        "signal_price": "eligible_SIP_event_time_proxy_with_original_completed_bar_timing_not_measured_receive_latency",
        "signal_priority": ["active_stop", "latched_full_exit_or_completed_first_red", "first_target"],
        "source_bounds": "unchanged_original_opportunity_not_merged_extension",
        "fees": "no_2026_defaults_historical_schedule_and_cash_integration_required",
        "terminal_status": "confirmed_share_closure_only_not_account_close_or_financial_eligibility",
    }


def expected_contract(root: Path) -> dict:
    return seal({"schema_version": 1, "contract_id": CONTRACT_ID,
        "artifact_type": "synthetically_verified_entry_binding_and_executable_fill_feedback_registration",
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "parent_registration_freeze_content_sha256": PARENT_FREEZE,
        "frozen_parent_file_sha256": PARENT_PINS,
        "hypothesis": "single_accepted_entry_management_conserves_whole_shares_and_uses_only_confirmed_target_fill_feedback",
        "selected_cell_id": parent.CELL, "mechanics": mechanics(),
        "execution_requirements_content_sha256": parent.exit_requirements()["content_sha256"],
        "historical_entry_producer": None, "historical_runner_registered": False,
        "historical_fee_schedule_registered": False, "next_session_valuation_registered": False,
        "implementation_file_sha256": {p: file_sha(root / p) for p in (MODULE_PATH, SCRIPT_PATH, TEST_PATH, WORKFLOW_PATH)},
        "next_gate": NEXT_GATE, **BOUNDARY})


def validate_registration(root: Path) -> dict:
    for name, expected in PARENT_PINS.items():
        accounts.availability._regular(root / name)
        if file_sha(root / name) != expected:
            raise ValueError("fill-feedback parent differs: " + name)
    parent.verify_bundle(root, root / parent.OUTPUT_PATH)
    if frozen(root / parent.OUTPUT_PATH / "freeze-manifest.json")["content_sha256"] != PARENT_FREEZE:
        raise ValueError("parent mechanics freeze differs")
    require_exact(frozen(root / CONTRACT_PATH), expected_contract(root), "fill-feedback registration")
    return seal({"verification_passed": True, "contract_content_sha256": expected_contract(root)["content_sha256"], **BOUNDARY})


def _pinned(value: object, expected: str, label: str) -> None:
    if not isinstance(expected, str) or len(expected) != 64 or canonical_fingerprint(value) != expected:
        raise ValueError(label + " differs from independent caller pin")


def _quote_window(window: dict, decision_ns: int, tape: dict, expected_sha256: str):
    _pinned(tape, expected_sha256, "quote/status tape")
    if set(tape) != {"quote_request", "quote_records", "status_request", "status_records"}:
        raise ValueError("complete quote/status evidence required")
    envelope = parent.conditional_exit_envelope(window, decision_ns)
    if not envelope["fits_frozen_envelope"]:
        raise ValueError("required exit evidence outside original opportunity")
    op = window["opportunity"]
    identity = adapter.WindowIdentity(op["opportunity_id"], op["trading_date"], op["symbol"], decision_ns)
    payload = adapter.capture_window(identity, tape["quote_request"], tape["quote_records"],
        tape["status_request"], tape["status_records"])
    if payload["capture_status"] != "complete":
        raise ValueError("quote/status input unavailable")
    quotes = adapter.top_of_book_events(payload, identity, tape["quote_request"], tape["quote_records"],
        tape["status_request"], tape["status_records"])
    reference = _decision_quote(quotes, decision_ns)
    if reference is None or reference.halted:
        raise ValueError("fresh nonhalted decision reference unavailable")
    return quotes, reference, payload["content_sha256"]


def _selected_quote(order, quotes, policy, outcome):
    """Recover the exact source ordinal, including otherwise identical native ties."""
    if not outcome.filled_quantity:
        return None
    arrival, ack = outcome.arrival_ts_ns, outcome.cancel_ack_ts_ns
    prior = [q for q in quotes if q.ts_recv_ns <= arrival]
    candidates = prior[-1:] if prior and arrival - prior[-1].ts_recv_ns <= policy.max_quote_age_ms * 1_000_000 else []
    candidates += [q for q in quotes if arrival < q.ts_recv_ns < ack]
    for quote in candidates:
        price, size = (quote.ask_price, quote.ask_size) if order.side is execution.OrderSide.BUY else (quote.bid_price, quote.bid_size)
        crossing = price <= order.limit_price if order.side is execution.OrderSide.BUY else price >= order.limit_price
        if not quote.halted and crossing and int(Decimal(size) * policy.displayed_size_participation) > 0:
            if (outcome.quote_ts_recv_ns != quote.ts_recv_ns or outcome.fill_price != price
                    or outcome.filled_quantity != min(order.quantity, int(Decimal(size) * policy.displayed_size_participation))):
                raise ValueError("selected fill source differs from frozen execution")
            return quote
    raise ValueError("filled outcome has no exact source record")


def bind_entry_evidence(*, window: dict, slot: dict, source_decision: dict,
                       expected_context_sha256: str, pre_entry_ledger: CampaignPortfolioLedger,
                       expected_pre_ledger_sha256: str, tape: dict, expected_tape_sha256: str) -> dict:
    """Mechanically bind a single fill; caller pins are not producer authentication.

    The frozen sizing, execution, and entry-acceptance code is re-executed on a
    copy. This function never changes the caller's ledger or claims that these
    inputs came from an authorized historical runner. Only synthetic tests use it.
    """
    _pinned({"window": window, "slot": slot, "source_decision": source_decision}, expected_context_sha256, "entry context")
    parent.validate_window(window)
    seed = accounts._validate_slot(slot)
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
    stop = parent._price(source_decision["plan"]["stop_price"], "original stop")
    if not isinstance(pre_entry_ledger, CampaignPortfolioLedger):
        raise ValueError("frozen ledger required")
    before = pre_entry_ledger.runtime_artifact()
    _pinned(before, expected_pre_ledger_sha256, "pre-entry ledger")
    ledger = deepcopy(pre_entry_ledger)
    constraints = ledger.constraints
    if ledger.session_date.isoformat() != slot["trading_date"] or constraints.account_id != seed["account_id"]:
        raise ValueError("ledger account or session differs")
    expected_constraints = materialize_account_constraints(paper_account_policy(constraints.account_class),
        account_id=seed["account_id"], starting_equity=constraints.starting_equity,
        starting_buying_power=constraints.starting_buying_power)
    if constraints != expected_constraints or constraints.account_class.value != ("main" if slot["account_key"] == "main_account" else "small"):
        raise ValueError("frozen account risk constraints differ")
    if slot["seed_applied"] and (constraints.starting_equity != float(seed["equity_usd"]) or constraints.starting_buying_power != float(seed["buying_power_usd"])):
        raise ValueError("first-session seed differs")
    if any(e["event_type"] == "entry_accepted" and e["symbol"] == op["symbol"] for e in ledger.events):
        raise ValueError("multiple-entry or add campaign is unsupported")
    policy, offset = SCENARIOS[slot["execution_scenario_id"]]
    quotes, reference, capture_sha = _quote_window(window, op["decision_ts_ns"], tape, expected_tape_sha256)
    limit = execution.marketable_limit_price(reference.ask_price, side=execution.OrderSide.BUY, offset_ticks=offset)
    ledger.record_plan_emission(PlanEmission(op["activation_id"], op["plan_id"], op["symbol"], pd.Timestamp(op["decision_ts_ns"], unit="ns", tz="UTC")))
    quantity = maximum_whole_share_quantity(ledger, activation_id=op["activation_id"], fill_price=float(limit), stop_price=stop, role=EntryRole.STARTER)
    if quantity < 1:
        raise ValueError("entry has no whole-share capacity")
    order_id = "entry-" + canonical_fingerprint({"contract_id": CONTRACT_ID, "path_id": slot["path_id"], "context": expected_context_sha256,
        "pre_ledger": expected_pre_ledger_sha256, "quantity": quantity, "limit": str(limit)})
    order = execution.MarketableLimitOrder(order_id, op["symbol"], execution.OrderSide.BUY, quantity, op["decision_ts_ns"], limit)
    outcome = adapter.simulate_record_order_limit_order(order, quotes, policy)
    if outcome.filled_quantity < 1:
        raise ValueError("entry execution is not a confirmed positive fill")
    source = _selected_quote(order, quotes, policy, outcome)
    payload = _execution_payload(outcome)
    fill_id = "fill-" + canonical_fingerprint({"order_id": order_id, "execution": payload})
    accepted = ledger.apply_entry_fill(EntryFill(fill_id=fill_id, activation_id=op["activation_id"], plan_id=op["plan_id"], symbol=op["symbol"],
        filled_at=pd.Timestamp(outcome.fill_ts_ns, unit="ns", tz="UTC"), quantity=outcome.filled_quantity,
        reference_price=float(reference.ask_price), fill_price=float(outcome.fill_price), stop_price=stop, role=EntryRole.STARTER, execution_approved=True))
    if not accepted.accepted:
        raise ValueError("entry rejected by frozen ledger: " + ",".join(accepted.reasons))
    after = ledger.runtime_artifact()
    events = [e for e in after["events"] if e["event_type"] == "entry_accepted" and e.get("fill_id") == fill_id]
    if len(events) != 1:
        raise ValueError("unique accepted entry evidence required")
    return seal({"contract_id": CONTRACT_ID, "artifact_type": "mechanically_bound_single_entry_evidence",
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
        "entry_mechanics_verified": True, "historical_producer_authenticated": False, "historical_runtime_authorized": False})


class ManagementFillFeedback:
    """Causal single-position reducer. Constructor revalidates all entry evidence.

    A target and one terminal exit each get one frozen marketable-limit attempt.
    Partial/unfilled remainders stay open. No hidden retry or cash/P&L is invented.
    The pending simulation result is private and cannot alter state before its
    fill time. Equal-time prints are processed before fill/cancel feedback.
    """

    def __init__(self, **entry_arguments):
        self._entry = bind_entry_evidence(**entry_arguments)
        self._window = deepcopy(entry_arguments["window"])
        self._policy, self._offset = SCENARIOS[self._entry["scenario_id"]]
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

    def _event(self, kind: str, at: int, **values):
        row = seal({"sequence": len(self._events), "previous_event_sha256": self._events[-1]["content_sha256"] if self._events else None,
            "event_type": kind, "timestamp_ns": at, **deepcopy(values)})
        self._events.append(row)

    def _validate_clock(self, at: int, phase: int):
        parent._integer(at, "event time", 1)
        if (at, phase) < self._clock:
            raise ValueError("event clock reversed or equal-time feedback precedes market input")
        if at >= self._window["end_ns"]:
            raise ValueError("event outside original opportunity")

    def _advance(self, at: int, phase: int):
        self._validate_clock(at, phase)
        if self._intent is not None:
            raise ValueError("outstanding intent must be resolved before another event")
        pending = self._pending
        if pending is not None:
            outcome = pending["outcome"]
            def known(stamp):
                return stamp < at or (stamp == at and phase == 2)
            if outcome.filled_quantity and not pending["applied"] and known(outcome.fill_ts_ns):
                quantity = outcome.filled_quantity
                if quantity > self._remaining or quantity > pending["intent"]["quantity"]:
                    raise RuntimeError("sell fill exceeds conserved shares")
                self._remaining -= quantity
                if pending["intent"]["reason"] == "first_target":
                    self._target_filled += quantity
                    if self._target_filled == self._target_quantity:
                        self._stop = self._fill
                self._used_liquidity.add(pending["liquidity_key"])
                fill = seal({"order_id": outcome.order.order_id, "entry_fill_id": self._entry["fill_id"],
                    "quantity": quantity, "fill_time_ns": outcome.fill_ts_ns, "fill_price": str(outcome.fill_price),
                    "reason": pending["intent"]["reason"], "source_request_sha256": pending["liquidity_key"][0],
                    "source_record_index": pending["liquidity_key"][1], "remaining_quantity": self._remaining,
                    "executable_research_fill": True, "historical_producer_authenticated": False, "account_close_evidence": False})
                self._fills.append(fill)
                self._event("sell_fill_confirmed", outcome.fill_ts_ns, receipt=fill)
                pending["applied"] = True
            if known(outcome.cancel_ack_ts_ns):
                self._event("sell_cancel_acknowledged", outcome.cancel_ack_ts_ns, order_id=outcome.order.order_id,
                    cancelled_quantity=outcome.unfilled_quantity, execution_status=outcome.status.value)
                self._pending = None
        self._clock = (at, phase)

    def _item(self, item: dict, resource: str):
        value = next(parent._records([item], self._window, resource))
        previous = self._stream_positions.get(resource)
        stamp, ordinal = value["timestamp_ns"], value["composed_record_ordinal"]
        if previous is not None and (stamp < previous[0] or ordinal != previous[1] + 1 or (resource == "raw_sip_1m_bars" and stamp == previous[0])):
            raise ValueError("management source continuity differs")
        key = (resource, value["source_artifact_id"], value["source_request_id"])
        if key in self._source_positions and value["source_record_ordinal"] != self._source_positions[key] + 1:
            raise ValueError("original source ordinal continuity differs")
        return value, key

    def _remember(self, item, resource, key):
        self._stream_positions[resource] = (item["timestamp_ns"], item["composed_record_ordinal"])
        self._source_positions[key] = item["source_record_ordinal"]

    def observe_bar(self, item: dict):
        value, key = self._item(item, "raw_sip_1m_bars")
        at = value["timestamp_ns"] + parent.MINUTE_NS
        if at <= self._entry["fill_time_ns"] or at > self._window["signal_end_ns"]:
            self._remember(value, "raw_sip_1m_bars", key)
            return
        self._advance(at, 0)
        self._remember(value, "raw_sip_1m_bars", key)
        if self._remaining and self._red is None and at <= self._window["signal_end_ns"] and value["record"]["c"] < value["record"]["o"]:
            self._red = {"signal_ts_ns": at, "evidence": parent._evidence(value, "raw_sip_1m_bars")}

    def observe_trade(self, item: dict) -> dict | None:
        value, key = self._item(item, "sip_transactions")
        at = value["timestamp_ns"]
        if at <= self._entry["fill_time_ns"]:
            self._remember(value, "sip_transactions", key)
            return None
        self._advance(at, 1)
        self._remember(value, "sip_transactions", key)
        eligible, _odd = parent.print_eligibility(value["record"])
        if not self._remaining or not eligible:
            return None
        price = float(value["record"]["p"])
        if price <= self._stop and self._latched not in ("initial_stop", "breakeven_stop"):
            self._latched = "breakeven_stop" if self._target_quantity and self._target_filled == self._target_quantity else "initial_stop"
        elif self._latched is None and self._red is not None:
            self._latched = "first_red_candle"
        if self._pending is not None or self._intent is not None or self._full_attempted:
            return None
        if self._latched:
            reason, quantity = self._latched, self._remaining
        elif not self._target_attempted and self._target_quantity and price >= self._target:
            reason, quantity = "first_target", self._target_quantity
        else:
            return None
        self._intent = seal({"entry_content_sha256": self._entry["content_sha256"], "opportunity_id": self._entry["opportunity_id"],
            "path_id": self._entry["path_id"], "session_id": self._entry["session_id"], "scenario_id": self._entry["scenario_id"],
            "decision_ts_ns": at, "reason": reason, "quantity": quantity,
            "trade_evidence": parent._evidence(value, "sip_transactions"), "red_signal": deepcopy(self._red) if reason == "first_red_candle" else None})
        self._event("sell_intent", at, intent=self._intent)
        return deepcopy(self._intent)

    def submit_intent(self, intent: dict, *, tape: dict, expected_tape_sha256: str) -> dict:
        """Compute a pending frozen execution; expose no future fill to the state."""
        if self._intent is None or intent != self._intent or self._pending is not None:
            raise ValueError("exact outstanding intent required")
        at = intent["decision_ts_ns"]
        if self._clock != (at, 1):
            raise ValueError("intent must be submitted at its causal decision clock")
        quotes, reference, capture_sha = _quote_window(self._window, at, tape, expected_tape_sha256)
        source_sha = canonical_fingerprint(tape["quote_request"])
        if self._sell_tape_sha is not None and source_sha != self._sell_tape_sha:
            raise ValueError("all sell attempts require one common source tape for liquidity identity")
        if self._sell_tape_content_sha is not None and expected_tape_sha256 != self._sell_tape_content_sha:
            raise ValueError("complete sell tape changed between attempts")
        limit = execution.marketable_limit_price(reference.bid_price, side=execution.OrderSide.SELL, offset_ticks=self._offset)
        order = execution.MarketableLimitOrder("exit-" + intent["content_sha256"], self._entry["symbol"], execution.OrderSide.SELL,
            intent["quantity"], at, limit)
        outcome = adapter.simulate_record_order_limit_order(order, quotes, self._policy)
        source = _selected_quote(order, quotes, self._policy, outcome)
        liquidity_key = None if source is None else (source.source_request_sha256, source.source_record_index)
        if liquidity_key is not None and liquidity_key in self._used_liquidity:
            raise ValueError("displayed liquidity source was already consumed")
        # Mutate only after every source, lifecycle, and conservation check succeeds.
        self._sell_tape_sha = source_sha
        self._sell_tape_content_sha = expected_tape_sha256
        self._pending = {"intent": deepcopy(intent), "outcome": outcome, "liquidity_key": liquidity_key, "applied": False}
        self._intent = None
        if intent["reason"] == "first_target":
            self._target_attempted = True
        else:
            self._full_attempted = True
        known_order = {"order_id": order.order_id, "quantity": order.quantity, "limit_price": str(limit),
            "decision_ts_ns": at, "arrival_ts_ns": outcome.arrival_ts_ns,
            "cancel_requested_ts_ns": outcome.cancel_requested_ts_ns, "cancel_ack_ts_ns": outcome.cancel_ack_ts_ns,
            "capture_content_sha256": capture_sha}
        self._event("sell_submitted", at, order=known_order)
        return deepcopy(known_order)

    def settle(self, timestamp_ns: int) -> dict:
        """Apply only feedback known by this clock, after all equal-time market input."""
        self._advance(timestamp_ns, 2)
        return self.snapshot()

    def snapshot(self) -> dict:
        reserved = 0
        if self._pending is not None:
            reserved = self._pending["intent"]["quantity"]
            if self._pending["applied"]:
                reserved -= self._pending["outcome"].filled_quantity
        if not 0 <= reserved <= self._remaining:
            raise RuntimeError("share reservation exceeds remaining position")
        sold = sum(f["quantity"] for f in self._fills)
        if sold + self._remaining != self._entry["quantity"] or self._target_filled > self._target_quantity:
            raise RuntimeError("whole-share conservation violated")
        status = "closed_confirmed_shares" if not self._remaining else "open_unresolved_exit_remainder" if self._full_attempted and self._pending is None else "open"
        return seal({"contract_id": CONTRACT_ID, "artifact_type": "single_entry_executable_management_mechanics_state",
            "entry": deepcopy(self._entry), "clock_ns": self._clock[0], "clock_phase": self._clock[1],
            "remaining_quantity": self._remaining, "sold_quantity": sold, "reserved_sell_quantity": reserved,
            "target_quantity": self._target_quantity, "target_filled_quantity": self._target_filled,
            "breakeven_active": self._target_quantity > 0 and self._target_filled == self._target_quantity,
            "active_stop_price": self._stop, "target_price": self._target, "latched_full_exit": self._latched,
            "target_attempted": self._target_attempted, "full_exit_attempted": self._full_attempted,
            "pending_order": self._pending is not None, "outstanding_intent": deepcopy(self._intent), "status": status,
            "fills": deepcopy(self._fills), "events": deepcopy(self._events),
            "historical_producer_authenticated": False, "historical_runtime_authorized": False,
            "account_position_closed": False, "financial_metrics_eligible": False})


def build_bundle(root: Path) -> dict[str, bytes]:
    validate_registration(root)
    prior = frozen(root / parent.OUTPUT_PATH / "projection-input-requirements.json")
    paths = frozen(root / parent.ACCOUNT_PLAN)
    references = [{"path_id": p["path_id"], "session_id": s["session_id"], "session_input_content_sha256": s["content_sha256"],
        "opportunity_inputs": s["opportunity_inputs"]} for p in paths["paths"] for s in p["sessions"]]
    payloads = {
        "entry-binding-requirements.json": seal({"contract_id": CONTRACT_ID, "counts": prior["counts"],
            "parent_input_requirements_content_sha256": prior["content_sha256"],
            "opportunity_windows_content_sha256": canonical_fingerprint(prior["opportunity_windows"]),
            "dates_content_sha256": canonical_fingerprint(prior["dates"]),
            "session_references_content_sha256": canonical_fingerprint(references),
            "account_session_plan_content_sha256": paths["content_sha256"],
            "parent_requirements_path": parent.OUTPUT_PATH + "/projection-input-requirements.json",
            "account_session_plan_path": parent.ACCOUNT_PLAN,
            "path_ids": [p["path_id"] for p in paths["paths"]],
            "historical_entry_producer": None, "available_inputs_are_confirmed_entries": False,
            "entry_evidence_fields": ["original_decision_and_stop", "opportunity_availability", "profile_and_path", "session_slot",
                "pinned_pre_entry_ledger", "common_quote_status_tape", "recomputed_L1_execution", "unique_accepted_ledger_event"], **BOUNDARY}),
        "fill-feedback-mechanics.json": seal({"contract_id": CONTRACT_ID, "mechanics": mechanics(),
            "frozen_execution_requirements_content_sha256": parent.exit_requirements()["content_sha256"], **BOUNDARY}),
        "readiness-report.json": seal({"contract_id": CONTRACT_ID, "counts": prior["counts"],
            "entry_evidence_binding_mechanics_registered": True, "whole_share_fill_feedback_registered": True,
            "synthetic_testing_only": True, "historical_entry_producer_registered": False,
            "historical_execution_count": 0, "actual_exit_request_count": 0, "source_tapes_reopened": False,
            "historical_fee_schedule_registered": False, "next_session_valuation_registered": False,
            "next_gate": NEXT_GATE, **BOUNDARY}),
    }
    files = {n: accounts._bytes(v) for n, v in payloads.items()}
    files["freeze-manifest.json"] = accounts._bytes(seal({"contract_id": CONTRACT_ID, "parent_commit_sha": PARENT_COMMIT,
        "contract_content_sha256": expected_contract(root)["content_sha256"], "parent_registration_freeze_content_sha256": PARENT_FREEZE,
        "file_inventory": {n: {"sha256": hashlib.sha256(v).hexdigest(), "bytes": len(v)} for n, v in files.items()},
        "document_content_sha256": {n: v["content_sha256"] for n, v in payloads.items()}, "next_gate": NEXT_GATE, **BOUNDARY}))
    return files


def _output(root: Path, output: Path):
    if output.is_symlink() or any(p.is_symlink() for p in output.parents):
        raise ValueError("symlink output rejected")
    if output.resolve().is_relative_to(root.resolve()) and output.resolve() != (root / OUTPUT_PATH).resolve():
        raise ValueError("cannot overwrite frozen repository inputs")


def verify_bundle(root: Path, output: Path) -> dict:
    _output(root, output)
    expected = build_bundle(root)
    inventory = accounts.availability._inventory(output)
    if set(inventory) != set(expected):
        raise ValueError("fill-feedback metadata inventory differs")
    for name, raw in expected.items():
        if (output / name).read_bytes() != raw:
            raise ValueError("fill-feedback reconstruction differs: " + name)
    return seal({"verification_passed": True, "contract_id": CONTRACT_ID, "file_inventory": inventory,
        "freeze_manifest_content_sha256": frozen(output / "freeze-manifest.json")["content_sha256"], **BOUNDARY})


def write_bundle(root: Path, output: Path) -> dict:
    _output(root, output)
    if output.exists():
        raise FileExistsError("fill-feedback registration is write-once")
    files = build_bundle(root)
    output.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        with (output / name).open("xb") as handle:
            if handle.write(raw) != len(raw):
                raise OSError("short metadata write")
            handle.flush()
            os.fsync(handle.fileno())
    return verify_bundle(root, output)
