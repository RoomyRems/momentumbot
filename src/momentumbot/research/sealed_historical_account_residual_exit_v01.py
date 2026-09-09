"""One bounded residual terminal exit after acknowledged cancellation.

The waiting parent is immutable. No hidden resubmission, window extension,
liquidity reset, fresh capital, strategy change or retrospective input is added.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, localcontext
import hashlib
import json
import os
from pathlib import Path

from momentumbot.research import sealed_historical_account_exit_waiting_v01 as waiting
from momentumbot.research.campaign_portfolio import CampaignPortfolioLedger
from momentumbot.research.sealed_historical_execution_quote_v01 import (
    canonical_fingerprint, file_sha, frozen, require_exact, seal)

parent, risk = waiting.parent, waiting.risk
binding, continuity = waiting.binding, waiting.continuity
scheduler, producer = waiting.scheduler, waiting.producer
accounts, runner, fees = waiting.accounts, waiting.runner, waiting.fees
feedback, adapter = waiting.feedback, waiting.adapter
BOUNDARY, RUNTIME_BOUNDARY = waiting.BOUNDARY, waiting.RUNTIME_BOUNDARY
BOUND_MANIFEST, PARENT_FREEZE = waiting.BOUND_MANIFEST, waiting.PARENT_FREEZE
source_programs, _source_item = waiting.source_programs, waiting._source_item
PRE_NS, TAIL_NS = waiting.PRE_NS, waiting.TAIL_NS
CONTRACT_ID = "sealed-historical-account-residual-exit-v0.1"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
OUTPUT_PATH = f"research/runtime/{CONTRACT_ID}"
MODULE_PATH = "src/momentumbot/research/sealed_historical_account_residual_exit_v01.py"
SCRIPT_PATH = "scripts/build_sealed_historical_account_residual_exit_v01.py"
CHECKER_PATH = "scripts/verify_sealed_historical_account_residual_exit_v01.py"
TEST_PATH = "tests/test_sealed_historical_account_residual_exit_v01.py"
WORKFLOW_PATH = ".github/workflows/sealed-historical-account-residual-exit-v01.yml"
PARENT_COMMIT = "1bfb8e84491e3b1e24a642fc6c1df8675a223754"
PARENT_TREE = "63970e9046c7b6dfb01c277948b830c6f19680db"
PARENT_REPLAY_FREEZE = "5f48460d88be6ce068a1bc3741d2a0cdb184f8530b8230aabc0b7a0edc812b44"
PARENT_RUNTIME = "7b0a0edd58ea285613a01047963bccb82a8a8df4ef6192f2437da222406d7edb"
PARENT_RUNTIME_FILE = "b36b14350d1cb91c173122aee77e7892050546af52cd03253b587c54c288219e"
PARENT_PINS = {
    ".github/workflows/sealed-historical-account-exit-waiting-reproduction-v01.yml": "11d75a790db7c0df8fb919f4064aff053067c694788765f8c4e4d113b46f61e6",
    ".github/workflows/sealed-historical-account-exit-waiting-v01.yml": "7da6f34def217af5ae0d23a183083d0c0bbf7486ea3c3fac5f86f29cd4ecf575",
    "docs/research/sealed_historical_account_exit_waiting_v01.md": "5e99308815b5a2e8d181412c890b189d715b27f038b6cd839603eef3b8694d40",
    "research/data-audits/sealed-historical-account-exit-waiting-v0.1-hosted-archive-comparison.json": "625305d44d792faadb87596f2690a0af8d4ab0571605250a7340f8b60e55b693",
    "research/data-audits/sealed-historical-account-exit-waiting-v0.1-implementation-verification.json": "f15497780918499911197069217198dfa1abc10c003506c88a5a8bece36fa18d",
    "research/data-audits/sealed-historical-account-exit-waiting-v0.1-independent-verification.json": "f0b23a128ff5344dfdb9301c26bd2c372fff3533c35395df70bdc86e394bfda0",
    "research/data-audits/sealed-historical-account-exit-waiting-v0.1-local-runtime-and-hosted-cancellation.json": "7825d897fd2cb9badf1a46e0946bdbf4009c545972ff4a796de1ab58ea717ebb",
    "research/runtime/sealed-historical-account-exit-waiting-v0.1/exit-waiting-mechanics.json": "032312d1f3df7fe52c4ff9ec090337f49ed92aad6858986600fe46ad55de3a54",
    "research/runtime/sealed-historical-account-exit-waiting-v0.1/freeze-manifest.json": "cd4d40a454d9a6d1a91098a9206be874af276596c5e94f5fa990635fd7cf65b1",
    "research/strategy/sealed-historical-account-exit-waiting-reproduction-v0.1.json": "d2f4a3adb394f1c4e75574a14dae9cda44434a44c8316c5320a93eed13ba057a",
    "research/strategy/sealed-historical-account-exit-waiting-v0.1.json": "e13fe1ed4c91ad7a95a8b0a3e8f76d46e2de024619f0c2cd5b0d9c3d8a0e1337",
    "scripts/build_sealed_historical_account_exit_waiting_v01.py": "83f4f05534a2b16d2974789eccb2fd3a488bbfcdce7864d42ae2ebaff5e6ff2b",
    "scripts/verify_sealed_historical_account_exit_waiting_v01.py": "958eba64d2b2503f78a48cfe05ba59b2910e9c0779d804a35d63371e63d73ebe",
    "src/momentumbot/research/sealed_historical_account_exit_waiting_v01.py": "27a3ea328f4668997208a688e150a9345e802c5e1a7fbdae988a08c7c59af694",
    "tests/test_sealed_historical_account_exit_waiting_v01.py": "7201b40b098441e355d58e3bce5fd4071c9e26299e227e3a8d96e08a3be31139"
}
NEXT_GATE = "independently_verify_bounded_residual_exit_replay_and_register_remaining_blockers"
MAX_RESIDUAL_ATTEMPTS = 1


def mechanics():
    return {
        "hypothesis": "one_additional_terminal_order_may_manage_acknowledged_partial_or_unfilled_remainder",
        "bound": "one_target_and_at_most_two_terminal_orders_per_entry_no_counter_reset",
        "authority": "only_confirmed_positive_remainder_after_first_terminal_cancel_acknowledgement",
        "clock": "first_eligible_SIP_print_strictly_after_acknowledgement_original_phases_and_order",
        "signal": "preserve_exact_prior_submitted_intent_and_ack_witness_with_unchanged_stop_risk_red_priority",
        "quantity": "all_and_only_current_confirmed_unreserved_remaining_shares",
        "reference_wait": "unchanged_frozen_waiting_if_first_replacement_reference_is_not_fresh_nonhalted",
        "expiry": "550ms_tail_plus_1ns_must_fit_original_window_else_preserve_shares_and_intent",
        "budget_consumption": "only_on_actual_replacement_order_submission_not_proposal_or_wait",
        "liquidity": "original_common_tape_identity_and_consumed_record_set_preserved_across_orders_and_reentry",
        "execution": "unchanged_marketable_limit_offsets_latency_participation_fill_and_cancel_model",
        "exhaustion": "second_terminal_remainder_stays_open_no_third_attempt_or_inferred_liquidation",
        "audit": "persistent_ready_proposal_submitted_expiry_or_exhaustion_chain_bound_to_entry_and_prior_order",
        "source_seeds_strategy_risk_fees_windows": "all_frozen_parent_values_unchanged",
        "evaluation": "all_12_paths_and_360_slots_financial_metrics_and_retrospective_labels_remain_closed",
    }


class _Management(waiting._Management):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._init_residual()

    def _init_residual(self):
        self._residual = None
        self._residual_attempts = 0
        self._residual_log = []

    def _residual_event(self, kind, at, **values):
        self._residual_log.append(seal({"contract_id": CONTRACT_ID, "event_type": kind,
            "sequence": len(self._residual_log),
            "previous_event_sha256": self._residual_log[-1]["content_sha256"] if self._residual_log else None,
            "entry_content_sha256": self._entry["content_sha256"],
            "opportunity_id": self._entry["opportunity_id"], "timestamp_ns": at,
            "remaining_quantity": self._remaining, "active_stop_price": self._stop,
            "residual_attempts": self._residual_attempts,
            "full_exit_attempted": self._full_attempted, **deepcopy(values)}))

    def _advance(self, at, phase):
        previous = self._pending
        super()._advance(at, phase)
        # Inspect only feedback that the frozen reducer has now made public.
        if previous is not None and self._pending is None and self._remaining:
            intent = previous["intent"]
            if intent["reason"] != "first_target":
                ack = self._events[-1]
                if ack["event_type"] != "sell_cancel_acknowledged":
                    raise RuntimeError("residual authority requires confirmed cancel acknowledgement")
                if self._residual_attempts == 0:
                    self._residual = {"context": seal({
                        "prior_submission_intent": deepcopy(intent),
                        "prior_order_id": ack["order_id"], "cancel_acknowledgement": deepcopy(ack),
                        "terminal_attempt_number": 2}), "expired": False}
                    self._residual_event("residual_ready", ack["timestamp_ns"],
                        context=self._residual["context"], known_at_ns=at, clock_phase=phase)
                else:
                    self._residual_event("residual_budget_exhausted", ack["timestamp_ns"],
                        cancel_acknowledgement=ack, known_at_ns=at, clock_phase=phase)
        state = self._residual
        if (state is not None and not state["expired"] and not self._residual_attempts
                and self._waiting is None and at + TAIL_NS >= self._window["end_ns"]):
            state["expired"] = True
            self._residual_event("residual_expired", at, context=state["context"],
                original_window_end_ns=self._window["end_ns"])

    def observe_trade(self, item):
        result = super().observe_trade(item)
        state = self._residual
        if (result is not None or state is None or state["expired"] or self._waiting is not None
                or self._pending is not None or self._intent is not None or self._residual_attempts):
            return result
        at = item["timestamp_ns"]
        eligible, _ = feedback.parent.print_eligibility(item["record"])
        if not eligible or at <= state["context"]["cancel_acknowledgement"]["timestamp_ns"]:
            return None
        if not self._remaining or not self._full_attempted or self._latched is None:
            raise RuntimeError("residual exit lost confirmed shares or terminal signal")
        self._intent = seal({**{k: self._entry[k] for k in
            ("opportunity_id", "path_id", "session_id", "scenario_id")},
            "entry_content_sha256": self._entry["content_sha256"], "decision_ts_ns": at,
            "reason": self._latched, "quantity": self._remaining,
            "trade_evidence": feedback.parent._evidence(item, "sip_transactions"),
            "red_signal": deepcopy(self._red) if self._latched == "first_red_candle" else None,
            "residual_exit": deepcopy(state["context"])})
        self._event("sell_intent", at, intent=self._intent)
        self._residual_event("residual_proposed", at, context=state["context"], intent=self._intent)
        return deepcopy(self._intent)

    def submit_intent(self, intent, *, tape, expected_tape_sha256):
        residual = "residual_exit" in intent
        if residual and (self._residual is None or self._residual["expired"]
                or self._residual_attempts >= MAX_RESIDUAL_ATTEMPTS
                or intent["residual_exit"] != self._residual["context"]
                or intent["quantity"] != self._remaining or intent["reason"] == "first_target"):
            raise ValueError("residual submission authority, quantity or budget differs")
        if self._full_attempted and not residual:
            raise ValueError("additional terminal intent requires residual authority")
        order = super().submit_intent(intent, tape=tape, expected_tape_sha256=expected_tape_sha256)
        if residual and order is not None:
            self._residual_attempts += 1
            self._residual_event("residual_submitted", intent["decision_ts_ns"],
                context=self._residual["context"], intent=intent, order=order)
        return order


class _AccountDay(waiting._AccountDay):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._exit_residual_events = []

    def _start(self, args):
        row = super()._start(args)
        engine = _Management.__new__(_Management)
        engine.__dict__ = self._engine.__dict__
        engine._init_residual()
        self._engine = engine
        return row

    def _transition(self, method, *args, **kwargs):
        before = 0 if self._engine is None else len(self._engine._residual_log)
        result = super()._transition(method, *args, **kwargs)
        self._exit_residual_events.extend(deepcopy(self._engine._residual_log[before:]))
        return result

    def snapshot(self):
        value = super().snapshot()
        if self._exit_residual_events:
            value.pop("content_sha256")
            value["exit_residual_events"] = deepcopy(self._exit_residual_events)
            return seal(value)
        return value


class _Session(waiting._Session):
    def __init__(self, slot, source, opening, resolve):
        super().__init__(slot, source, opening, resolve)
        ledger = CampaignPortfolioLedger(self.account._ledger.session_date, self.account._ledger.constraints)
        self.account = _AccountDay(pre_session_ledger=ledger,
            expected_pre_session_ledger_sha256=canonical_fingerprint(ledger.runtime_artifact()),
            path_id=slot["path_id"], scenario_id=slot["execution_scenario_id"])


def expected_contract(root):
    return seal({"schema_version": 1, "contract_id": CONTRACT_ID,
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "parent_replay_freeze_content_sha256": PARENT_REPLAY_FREEZE,
        "parent_runtime_content_sha256": PARENT_RUNTIME,
        "parent_runtime_file_sha256": PARENT_RUNTIME_FILE,
        "source_bindings_content_sha256": BOUND_MANIFEST,
        "frozen_parent_file_sha256": {**binding.PARENT_PINS, **parent.PARENT_PINS, **risk.PARENT_PINS, **waiting.PARENT_PINS, **PARENT_PINS},
        "source_archives": binding.SOURCES, "mechanics": mechanics(),
        "implementation_file_sha256": {p: file_sha(root / p) for p in
            (MODULE_PATH, SCRIPT_PATH, CHECKER_PATH, TEST_PATH, WORKFLOW_PATH)},
        "next_gate": NEXT_GATE, **BOUNDARY})


def validate_registration(root):
    for name, sha in {**binding.PARENT_PINS, **parent.PARENT_PINS, **risk.PARENT_PINS, **waiting.PARENT_PINS, **PARENT_PINS}.items():
        binding.availability._regular(root / name)
        if file_sha(root / name) != sha:
            raise ValueError("residual exit parent differs: " + name)
    checked = waiting.verify_bundle(root, root / waiting.OUTPUT_PATH)
    if checked["freeze_content_sha256"] != PARENT_REPLAY_FREEZE:
        raise ValueError("parent replay registration differs")
    require_exact(frozen(root / CONTRACT_PATH), expected_contract(root), "residual exit registration")


def documents(values, contract_sha, *, runtime=False):
    files = parent.documents(values, contract_sha, runtime=runtime)
    manifest = json.loads(files["freeze-manifest.json"])
    manifest.pop("content_sha256")
    manifest["contract_id"] = CONTRACT_ID
    files["freeze-manifest.json"] = fees.encoded(seal(manifest))
    return files


def build_bundle(root):
    validate_registration(root)
    return documents({"residual-exit-mechanics.json": seal({"contract_id": CONTRACT_ID,
        "mechanics": mechanics(), **BOUNDARY})}, expected_contract(root)["content_sha256"])


def write_files(root, output, files, *, registration=False):
    if registration and output.resolve() == (root / OUTPUT_PATH).resolve():
        if output.is_symlink() or any(p.is_symlink() for p in output.parents):
            raise ValueError("nonsymlink output required")
        output.mkdir(parents=True, exist_ok=False)
        for name, raw in files.items():
            if Path(name).name != name:
                raise ValueError("flat output inventory required")
            with (output / name).open("xb") as handle:
                if handle.write(raw) != len(raw):
                    raise OSError("short registration write")
                handle.flush()
                os.fsync(handle.fileno())
        return seal({"file_inventory": binding.availability._inventory(output), **BOUNDARY})
    return parent.write_files(root, output, files)


def verify_bundle(root, output):
    expected = build_bundle(root)
    require_exact(sorted(binding.availability._inventory(output)), sorted(expected), "residual exit inventory")
    for name, raw in expected.items():
        if (output / name).read_bytes() != raw:
            raise ValueError("residual exit registration bytes differ: " + name)
    return seal({"verification_passed": True,
        "freeze_content_sha256": frozen(output / "freeze-manifest.json")["content_sha256"], **BOUNDARY})


def _session(slot, source, opening, previous_sha, resolve, dependency):
    """Frozen finisher arithmetic; add historical identity and explicit carry."""
    blocked, machine, failure = not producer._ready(opening), None, None
    if not blocked:
        try:
            machine = _Session(slot, source, opening, resolve).run()
            failure = machine.failure
        except (ValueError, TypeError, OverflowError) as exc:
            blocked = True
            failure = {"kind": "opening_ledger_projection_unavailable", "stage": "opening_ledger",
                "error_type": type(exc).__name__, "error": str(exc)[:300], "blocks_next_session": True}
    seen = {} if machine is None else {d["opportunity_id"]: d["disposition"] for d in machine.dispositions}
    dispositions = [{**deepcopy(r), "disposition": "unavailable_input" if r["input_status"] == "unavailable"
        else seen.get(r["opportunity_id"], "blocked_prior_state" if blocked else "unprocessed_available_input")}
        for r in slot["opportunity_inputs"]]
    gaps = [{"kind": d["disposition"], "opportunity_id": d["opportunity_id"],
        "availability_content_sha256": d["availability_content_sha256"], "reason": d["reason"],
        "blocks_next_session": d["disposition"] != "unavailable_input"} for d in dispositions
        if d["disposition"] in {"unavailable_input", "unprocessed_available_input", "blocked_prior_state"}]
    failures = [] if failure is None else [failure]
    snapshot = None if machine is None else machine.account.snapshot()
    entry_pending = None if machine is None else machine.pending_public()
    if blocked:
        state = deepcopy(opening)
        state["unresolved_inputs"] += gaps + failures + [{"kind": "preceding_state_blocks_execution", "blocks_next_session": True,
            "previous_close_content_sha256": previous_sha}]
        gross = net = charged = Decimal(0)
    else:
        positions, pending, extra = producer._collections(snapshot)
        if entry_pending is not None:
            pending.append(entry_pending)
        exact = snapshot["exact_account"]
        gross, net, charged = Decimal(exact["gross_realized_pnl"]), Decimal(exact["net_realized_pnl"]), Decimal(snapshot["fee_book"]["fees"]["total_charged"])
        state = {"equity_usd": None if positions or pending else producer.money(Decimal(opening["equity_usd"]) + net),
            "buying_power_usd": producer.money(exact["remaining_buying_power"]),
            "cumulative_realized_pnl_usd": producer.money(Decimal(opening["cumulative_realized_pnl_usd"]) + net),
            "cumulative_fees_usd": producer.money(Decimal(opening["cumulative_fees_usd"]) + charged),
            "positions": positions, "pending_orders": pending,
            "campaigns": deepcopy(opening["campaigns"]) + deepcopy(snapshot["ledger"]["campaigns"]),
            "unresolved_inputs": deepcopy(opening["unresolved_inputs"]) + gaps + failures + extra}
    producer.validate_state(state)
    window = None if machine is None or machine.active is None else machine.specs[machine.active]["entry_input"]["window"]
    carry = None if dependency is None else seal({"dependency": deepcopy(dependency),
        "previous_close_content_sha256": previous_sha, "opening_account_state_sha256": canonical_fingerprint(opening),
        "status": "blocked_preserved_prior_state" if blocked else "flat_cash_no_share_mark_or_adjustment_required",
        "prior_state_preserved": True, "new_source_evidence_inferred": False})
    complete = machine is not None and machine.failure is None and not machine.heap
    runtime = seal({"contract_id": parent.CONTRACT_ID, "session_id": slot["session_id"], "path_id": slot["path_id"],
        "source_slot_content_sha256": slot["content_sha256"], "session_program_sha256": canonical_fingerprint(source),
        "source_bindings_content_sha256": BOUND_MANIFEST,
        "opening_account_state_sha256": canonical_fingerprint(opening), "blocked_before_execution": blocked,
        "events": [] if machine is None else machine.events, "opportunity_dispositions": dispositions,
        "reconciliation_snapshot": snapshot, "unconfirmed_entry_order": entry_pending,
        "complete_streams_verified": complete, "processed_streams": [] if machine is None else machine.progress(),
        "failure": failure, "active_original_window": deepcopy(window), "carry_dependency": carry,
        "session_gross_realized_pnl_usd": producer.money(gross), "session_net_realized_pnl_usd": producer.money(net),
        "session_fees_usd": producer.money(charged), "historical_session_scheduler_executed": machine is not None,
        "status": "blocked_prior_state" if blocked else "input_failure" if failure else
            "original_window_exhausted_with_unresolved_state" if not producer._ready(state) else
            "flat_complete_with_unavailable_inputs" if gaps else "flat_complete",
        **RUNTIME_BOUNDARY})
    close = seal({"contract_id": parent.CONTRACT_ID, "session_id": slot["session_id"], "path_id": slot["path_id"],
        "trading_date": slot["trading_date"], "session_index": slot["session_index"], "seed_applied": slot["seed_applied"],
        "source_slot_content_sha256": slot["content_sha256"], "previous_close_content_sha256": previous_sha,
        "source_runtime_content_sha256": runtime["content_sha256"], "account_state": state,
        "next_session_flat_cash_execution_ready": producer._ready(state), **RUNTIME_BOUNDARY})
    return {"runtime": runtime, "close": close}



def replay_panel(root, sources, *, expected_registration_sha256):
    verified = verify_bundle(root, root / OUTPUT_PATH)
    if verified["freeze_content_sha256"] != expected_registration_sha256:
        raise ValueError("independent historical replay registration pin differs")
    if type(sources) is not binding.OriginalSources:
        raise ValueError("verified original source reader required; caller programs or accounts prohibited")
    manifest = sources.manifest()
    accounts._sealed(manifest, "authenticated original bindings")
    if manifest["content_sha256"] != BOUND_MANIFEST:
        raise ValueError("verified original binding manifest differs")
    programs = source_programs(root)
    require_exact([p["slots"] for p in programs], [p["sessions"] for p in manifest["paths"]], "original complete path catalogs")
    dependencies = {d["next_session_id"]: d for d in manifest["carry_dependencies"]}
    results = []
    with localcontext() as context:
        context.prec = 60
        for program in programs:
            initial = accounts.account_state_input(program["slots"][0])["account_state"]
            opening, previous, sessions = initial, None, []
            for slot, source in zip(program["slots"], program["sessions"]):
                pair = _session(slot, source, opening, previous,
                    lambda oid: _source_item(sources, program["path_id"], oid), dependencies.get(slot["session_id"]))
                sessions.append(pair)
                opening, previous = deepcopy(pair["close"]["account_state"]), pair["close"]["content_sha256"]
            results.append(seal({"contract_id": parent.CONTRACT_ID, "artifact_type": "original_historical_account_path",
                "path_id": program["path_id"], "program_content_sha256": program["content_sha256"],
                "initial_account_state": initial, "seed_application_count": 1,
                "session_count": len(sessions), "sessions": sessions, "last_close_content_sha256": previous,
                "path_complete": all(s["runtime"]["status"] == "flat_complete" for s in sessions), **RUNTIME_BOUNDARY}))
    return seal({"contract_id": CONTRACT_ID, "artifact_type": "frozen_original_historical_account_residual_exit_replay",
        "parent_runtime_content_sha256": PARENT_RUNTIME,
        "registration_freeze_content_sha256": expected_registration_sha256,
        "source_bindings_content_sha256": BOUND_MANIFEST, "source_archives": binding.SOURCES,
        "paths": results, "next_gate": NEXT_GATE, **RUNTIME_BOUNDARY})
