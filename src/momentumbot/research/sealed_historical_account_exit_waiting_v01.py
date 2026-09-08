"""Isolated causal waiting for an unsubmitted exit; frozen fills and risk remain.

Historical authority, source windows and attempt ceilings are inherited exactly.
Only later eligible SIP prints may reconsider a waiting sell reference.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from copy import deepcopy
from decimal import Decimal, Inexact, localcontext
import hashlib
import json
import os
from pathlib import Path

from momentumbot.research import sealed_historical_account_replay_v01 as parent
from momentumbot.research import sealed_historical_account_risk_projection_v01 as risk
from momentumbot.research.campaign_portfolio import CampaignPortfolioLedger
from momentumbot.research.sealed_historical_execution_quote_v01 import (
    canonical_fingerprint, file_sha, frozen, require_exact, seal)

binding, continuity = parent.binding, parent.continuity
scheduler, producer = parent.scheduler, parent.producer
accounts, runner, fees = parent.accounts, parent.runner, parent.fees
BOUNDARY, RUNTIME_BOUNDARY = parent.BOUNDARY, parent.RUNTIME_BOUNDARY
BOUND_MANIFEST, PARENT_FREEZE = parent.BOUND_MANIFEST, parent.PARENT_FREEZE
source_programs, _source_item = parent.source_programs, parent._source_item
CONTRACT_ID = "sealed-historical-account-exit-waiting-v0.1"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
OUTPUT_PATH = f"research/runtime/{CONTRACT_ID}"
MODULE_PATH = "src/momentumbot/research/sealed_historical_account_exit_waiting_v01.py"
SCRIPT_PATH = "scripts/build_sealed_historical_account_exit_waiting_v01.py"
CHECKER_PATH = "scripts/verify_sealed_historical_account_exit_waiting_v01.py"
TEST_PATH = "tests/test_sealed_historical_account_exit_waiting_v01.py"
WORKFLOW_PATH = ".github/workflows/sealed-historical-account-exit-waiting-v01.yml"
PARENT_COMMIT = "d2266c8cf151a55f705c06c59986eafc590f0422"
PARENT_TREE = "514af4067fae35cecda2ae2682eca5ccd13cfb06"
PARENT_REPLAY_FREEZE = "87b1ab436d60df1bd6272d9e9f1975b0b728d0a1cd4f0badcab91957bffe46be"
PARENT_RUNTIME = "5986950aab81652970a6318d93b7a6dd3b4b3384b8aa4a92d8578e3e985398e0"
PARENT_RUNTIME_FILE = "e4b35e830e1934117ad2fa205b4777fd6f700e1bf5995cc9c65e4e4808dcf649"
PARENT_PINS = {
    "research/data-audits/sealed-historical-account-risk-projection-v0.1-archive-comparison.json": "2474280556ace42255804f5994e96cf3777fd34de1bbb7ed00daef86deee01bd",
    ".github/workflows/sealed-historical-account-risk-projection-v01.yml": "83c1330254dea3424f9ba21251096b7c05722885da91de707a879595582a90af",
    "docs/research/sealed_historical_account_risk_projection_v01.md": "307df95f28bd27e43275dc2f7ae154f181b00b29f802c1c45a49b6fbf64cba85",
    "research/data-audits/sealed-historical-account-risk-projection-v0.1-independent-verification.json": "fdbd89b1785ff82e63398358e66e475a856165416ceda2c3a7a1836ff6189a06",
    "research/data-audits/sealed-historical-account-risk-projection-v0.1-local-and-hosted-verification.json": "9e2c4547e5318dac2e9627339aded464472249eca527e5565d3e4a217abc6052",
    "research/runtime/sealed-historical-account-risk-projection-v0.1/freeze-manifest.json": "0ec8bf24b4deee67bd743b7692e957b4715df537f949c7bb464b31d2677fefeb",
    "research/runtime/sealed-historical-account-risk-projection-v0.1/risk-projection-mechanics.json": "41c03b334cf67ec2c112615438221dc38afbc52eb50d904b4c174278393fbf70",
    "research/strategy/sealed-historical-account-risk-projection-v0.1.json": "eec2ddd424e5568781828807f811fe8ef9f79ea26de61dd6244e80ddb68fa917",
    "scripts/build_sealed_historical_account_risk_projection_v01.py": "d65675f68fb72edbdb37b2479be1fa5ff0c736206a3078fd12e1aee6b7f571aa",
    "scripts/verify_sealed_historical_account_risk_projection_v01.py": "a0a99ae474e0106952eae900447cd9985c7e3aee53b0455abc8d2af375c9bb92",
    "src/momentumbot/research/sealed_historical_account_risk_projection_v01.py": "68cdbbf7000e6e8cae93076e6cc77dc2e9d8eda62225ed2e49ba93390af1b845",
    "tests/test_sealed_historical_account_risk_projection_v01.py": "32ef85c03d321e7a71ef6d7536d077990dbb7316da34ee3e4edc4c89e4f222de"
}
NEXT_GATE = "independently_verify_waiting_replay_and_register_remaining_input_or_execution_blockers"
feedback = continuity.feedback
adapter = feedback.adapter
PRE_NS, TAIL_NS = 100_000_000, 550_000_000


def mechanics():
    return {
        "hypothesis": "unsubmitted_exit_can_wait_causally_for_fresh_reference_inside_original_window",
        "retry_clock": "subsequent_eligible_SIP_prints_only_original_phase_and_record_order",
        "reference": "latest_usable_record_at_or_before_print_with_inclusive_100ms_age_and_known_nonhalted_status",
        "signal": "preserve_original_signal_and_latch_target_until_terminal_supersedes_it",
        "priority": "unchanged_stop_then_account_risk_then_first_red_then_target_at_each_eligible_print",
        "attempts": "one_target_and_one_terminal_order_attempt_consumed_only_after_actual_submission",
        "expiry": "stop_reconsidering_when_550ms_tail_plus_1ns_no_longer_fits_preserve_intent_and_shares",
        "malformed_unknown_or_incomplete_status": "unchanged_fail_closed_not_transient_wait",
        "submission": "frozen_full_tape_revalidation_fill_selection_latency_cancel_and_liquidity_use",
        "cache": "validated_immutable_native_record_index_no_future_quote_used_for_decision",
        "audit": "persistent_wait_start_supersession_submission_expiry_chain_linked_to_original_signal",
        "source_seeds_strategy_risk_fees_windows": "all_frozen_parent_values_unchanged",
        "parent_schema": "nested_original_component_ids_retained_optional_account_wait_journal_only_when_used",
        "evaluation": "all_12_paths_and_360_slots_financial_metrics_and_retrospective_labels_remain_closed",
    }


@dataclass(frozen=True)
class _ReferenceIndex:
    """Full tape parsed once; immutable records may be shared across transactions."""
    quotes: tuple
    statuses: tuple
    times: tuple
    tape_sha: str

    def __deepcopy__(self, memo):
        return self

    @classmethod
    def build(cls, window, at, tape, pin):
        # This full validation must fail for malformed/unbound input, not wait.
        feedback._pinned(tape, pin, "quote/status tape")
        if set(tape) != {"quote_request", "quote_records", "status_request", "status_records"}:
            raise ValueError("complete quote/status evidence required")
        op = window["opportunity"]
        identity = adapter.WindowIdentity(op["opportunity_id"], op["trading_date"], op["symbol"], at)
        adapter.capture_window(identity, tape["quote_request"], tape["quote_records"],
            tape["status_request"], tape["status_records"])
        quotes = adapter.quote_events(tape["quote_records"], tape["quote_request"])
        statuses = adapter.status_events(tape["status_records"], tape["status_request"])
        return cls(quotes, statuses, tuple(q.ts_recv_ns for q in quotes), pin)

    def reference(self, window, at):
        op = window["opportunity"]
        identity = adapter.WindowIdentity(op["opportunity_id"], op["trading_date"], op["symbol"], at)
        quotes = self.quotes[bisect_left(self.times, at - PRE_NS):bisect_right(self.times, at + TAIL_NS)]
        payload = adapter._capture_window(identity, {op["symbol"]: quotes}, {op["symbol"]: self.statuses})
        if payload["capture_status"] != "complete":
            raise ValueError("quote/status input unavailable")
        prior = [q for q in payload["quotes"] if q["ts_recv_ns"] <= at]
        return None if not prior or prior[-1]["halted"] else prior[-1]


class _Management(continuity._Management):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._init_waiting()

    def _init_waiting(self):
        self._waiting = None
        self._reference_index = None
        self._wait_log = []

    def _wait_event(self, kind, at, **values):
        self._wait_log.append(seal({"contract_id": CONTRACT_ID, "event_type": kind,
            "sequence": len(self._wait_log),
            "previous_event_sha256": self._wait_log[-1]["content_sha256"] if self._wait_log else None,
            "entry_content_sha256": self._entry["content_sha256"],
            "opportunity_id": self._entry["opportunity_id"], "timestamp_ns": at,
            "remaining_quantity": self._remaining, "active_stop_price": self._stop,
            "target_attempted": self._target_attempted, "full_exit_attempted": self._full_attempted,
            **deepcopy(values)}))

    def _advance(self, at, phase):
        if self._waiting is None:
            return super()._advance(at, phase)
        # Waiting has no order, reservations, private fills or consumed attempt.
        intent, self._intent = self._intent, None
        try:
            super()._advance(at, phase)
        finally:
            self._intent = intent
        if not self._waiting["expired"] and at + TAIL_NS >= self._window["end_ns"]:
            self._waiting["expired"] = True
            self._wait_event("wait_expired", at, signal=self._waiting["signal"],
                original_signal_content_sha256=self._waiting["origin"]["content_sha256"],
                original_window_end_ns=self._window["end_ns"])

    def observe_trade(self, item):
        result = super().observe_trade(item)
        if self._waiting is None or self._waiting["expired"]:
            return result
        at = item["timestamp_ns"]
        eligible, _ = feedback.parent.print_eligibility(item["record"])
        if at <= self._entry["fill_time_ns"] or not eligible:
            return None
        wait = self._waiting
        if self._latched and self._latched != wait["signal"]["reason"]:
            old = wait["signal"]
            signal = {k: deepcopy(v) for k, v in old.items() if k != "content_sha256"}
            signal.update(decision_ts_ns=at, reason=self._latched, quantity=self._remaining,
                trade_evidence=feedback.parent._evidence(item, "sip_transactions"),
                red_signal=deepcopy(self._red) if self._latched == "first_red_candle" else None)
            wait["signal"] = self._intent = seal(signal)
            self._wait_event("wait_superseded", at, signal=wait["signal"],
                superseded_signal_content_sha256=old["content_sha256"],
                original_signal_content_sha256=wait["origin"]["content_sha256"])
        reference = self._reference_index.reference(self._window, at)
        if reference is None:
            return None
        proposal = {k: deepcopy(v) for k, v in wait["signal"].items() if k != "content_sha256"}
        proposal.update(decision_ts_ns=at, trade_evidence=feedback.parent._evidence(item, "sip_transactions"),
            waiting_signal=deepcopy(wait["signal"]),
            original_waiting_signal_content_sha256=wait["origin"]["content_sha256"])
        self._intent = seal(proposal)
        return deepcopy(self._intent)

    def submit_intent(self, intent, *, tape, expected_tape_sha256):
        if self._reference_index is not None and expected_tape_sha256 != self._reference_index.tape_sha:
            raise ValueError("complete sell tape changed while waiting")
        try:
            order = super().submit_intent(intent, tape=tape, expected_tape_sha256=expected_tape_sha256)
        except ValueError as exc:
            if str(exc) != "fresh nonhalted decision reference unavailable" or self._waiting is not None:
                raise
            source_sha = canonical_fingerprint(tape["quote_request"])
            if ((self._sell_tape_sha is not None and self._sell_tape_sha != source_sha)
                    or (self._sell_tape_content_sha is not None and self._sell_tape_content_sha != expected_tape_sha256)):
                raise ValueError("complete sell tape changed between attempts") from exc
            self._reference_index = _ReferenceIndex.build(self._window, intent["decision_ts_ns"], tape, expected_tape_sha256)
            if self._reference_index.reference(self._window, intent["decision_ts_ns"]) is not None:
                raise ValueError("waiting reference disagrees with frozen adapter") from exc
            self._waiting = {"origin": deepcopy(intent), "signal": deepcopy(intent), "expired": False}
            self._wait_event("wait_started", intent["decision_ts_ns"], signal=intent,
                tape_content_sha256=expected_tape_sha256, original_window_end_ns=self._window["end_ns"])
            return None
        if self._waiting is not None:
            wait = self._waiting
            self._wait_event("wait_submitted", intent["decision_ts_ns"], signal=wait["signal"],
                original_signal_content_sha256=wait["origin"]["content_sha256"], submission_intent=intent, order=order,
                reference=self._reference_index.reference(self._window, intent["decision_ts_ns"]),
                tape_content_sha256=expected_tape_sha256)
            self._waiting = None
        return order


class _AccountDay(risk._AccountDay):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._exit_wait_events = []

    def _start(self, args):
        row = super()._start(args)
        engine = _Management.__new__(_Management)
        engine.__dict__ = self._engine.__dict__
        engine._init_waiting()
        self._engine = engine
        return row

    def _transition(self, method, *args, **kwargs):
        before = 0 if self._engine is None else len(self._engine._wait_log)
        result = super()._transition(method, *args, **kwargs)
        self._exit_wait_events.extend(deepcopy(self._engine._wait_log[before:]))
        return result

    def snapshot(self):
        value = super().snapshot()
        if self._exit_wait_events:
            value.pop("content_sha256")
            value["exit_wait_events"] = deepcopy(self._exit_wait_events)
            return seal(value)
        return value


class _Session(parent._Session):
    def __init__(self, slot, source, opening, resolve):
        super().__init__(slot, source, opening, resolve)
        ledger = CampaignPortfolioLedger(self.account._ledger.session_date, self.account._ledger.constraints)
        self.account = _AccountDay(pre_session_ledger=ledger,
            expected_pre_session_ledger_sha256=canonical_fingerprint(ledger.runtime_artifact()),
            path_id=slot["path_id"], scenario_id=slot["execution_scenario_id"])

    def market(self, at, phase, oid, resource):
        cursor = self.cursors[(oid, resource)]
        raw = runner._row_bytes(cursor.value)
        if self.active == oid:
            if resource == "raw_sip_1m_bars":
                self.account.observe_bar(cursor.value)
            else:
                intent = self.account.observe_trade(cursor.value)
                if intent is not None:
                    self.stage = "executable_exit_evidence"
                    spec = self.specs[oid]
                    order = self.account.submit_intent(intent, tape=spec["exit_tape"], expected_tape_sha256=spec["expected_exit_tape_sha256"])
                    if order is not None:
                        self.event(at, phase, "sell_submitted", opportunity_id=oid, reason=intent["reason"], order=order)
                        stamps = {order[k] for k in ("arrival_ts_ns", "cancel_requested_ts_ns", "cancel_ack_ts_ns")}
                        stamps.update(t for t in self.quote_times[oid] if order["arrival_ts_ns"] < t < order["cancel_ack_ts_ns"])
                        for stamp in stamps:
                            if stamp >= spec["entry_input"]["window"]["end_ns"]:
                                raise ValueError("sell feedback outside original opportunity")
                            self.push(stamp, 3, self.rank[oid], "feedback", oid)
        self.stage = "management_stream"
        cursor.advance()
        self.push_cursor(oid, cursor)
        digest, count = self.processed.get((oid, resource), (hashlib.sha256(), 0))
        digest.update(raw)
        self.processed[(oid, resource)] = digest, count + 1


def expected_contract(root):
    return seal({"schema_version": 1, "contract_id": CONTRACT_ID,
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "parent_replay_freeze_content_sha256": PARENT_REPLAY_FREEZE,
        "parent_runtime_content_sha256": PARENT_RUNTIME,
        "parent_runtime_file_sha256": PARENT_RUNTIME_FILE,
        "source_bindings_content_sha256": BOUND_MANIFEST,
        "frozen_parent_file_sha256": {**binding.PARENT_PINS, **parent.PARENT_PINS, **risk.PARENT_PINS, **PARENT_PINS},
        "source_archives": binding.SOURCES, "mechanics": mechanics(),
        "implementation_file_sha256": {p: file_sha(root / p) for p in
            (MODULE_PATH, SCRIPT_PATH, CHECKER_PATH, TEST_PATH, WORKFLOW_PATH)},
        "next_gate": NEXT_GATE, **BOUNDARY})


def validate_registration(root):
    for name, sha in {**binding.PARENT_PINS, **parent.PARENT_PINS, **risk.PARENT_PINS, **PARENT_PINS}.items():
        binding.availability._regular(root / name)
        if file_sha(root / name) != sha:
            raise ValueError("exit waiting parent differs: " + name)
    checked = risk.verify_bundle(root, root / risk.OUTPUT_PATH)
    if checked["freeze_content_sha256"] != PARENT_REPLAY_FREEZE:
        raise ValueError("parent replay registration differs")
    require_exact(frozen(root / CONTRACT_PATH), expected_contract(root), "exit waiting registration")


def documents(values, contract_sha, *, runtime=False):
    files = parent.documents(values, contract_sha, runtime=runtime)
    manifest = json.loads(files["freeze-manifest.json"])
    manifest.pop("content_sha256")
    manifest["contract_id"] = CONTRACT_ID
    files["freeze-manifest.json"] = fees.encoded(seal(manifest))
    return files


def build_bundle(root):
    validate_registration(root)
    return documents({"exit-waiting-mechanics.json": seal({"contract_id": CONTRACT_ID,
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
    require_exact(sorted(binding.availability._inventory(output)), sorted(expected), "exit waiting inventory")
    for name, raw in expected.items():
        if (output / name).read_bytes() != raw:
            raise ValueError("exit waiting registration bytes differ: " + name)
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
    return seal({"contract_id": CONTRACT_ID, "artifact_type": "frozen_original_historical_account_exit_waiting_replay",
        "parent_runtime_content_sha256": PARENT_RUNTIME,
        "registration_freeze_content_sha256": expected_registration_sha256,
        "source_bindings_content_sha256": BOUND_MANIFEST, "source_archives": binding.SOURCES,
        "paths": results, "next_gate": NEXT_GATE, **RUNTIME_BOUNDARY})
