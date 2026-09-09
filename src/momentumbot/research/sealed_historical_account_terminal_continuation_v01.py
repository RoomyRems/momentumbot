"""Causal terminal continuation after the frozen two-order residual prefix.

One pending sell at a time, acknowledged cancellation before replacement,
strictly later SIP prints and the original finite window provide the bound.
The parent implementation, source tapes and consumed liquidity are immutable.
"""
from copy import deepcopy
from pathlib import Path

from momentumbot.research import sealed_historical_account_residual_exit_v01 as parent

waiting, feedback = parent.waiting, parent.feedback
seal, fingerprint = parent.seal, parent.canonical_fingerprint
ID = "sealed-historical-account-terminal-continuation-v0.1"
PARENT_COMMIT = "998379812823ef44d2678cbca523ce73fbdf8bfb"
PARENT_TREE = "a3281978c765fdf490fbad9ed92076cd9c602efb"
PARENT_RUNTIME = "21bd9efa65c5c5776242bb9a6a53d28c134aefe31ed7da00d389402e29f3efba"
REPRODUCTION = "sealed-historical-account-residual-exit-reproduction-v0.1"
REPRODUCTION_FREEZE = "25b2124138c419363176286e9bb8e209c210792365f00fc6ae4c6245a1742582"
TAIL_NS = parent.TAIL_NS
OWN_FILES = (
    "src/momentumbot/research/sealed_historical_account_terminal_continuation_v01.py",
    "scripts/build_sealed_historical_account_terminal_continuation_v01.py",
    "scripts/verify_sealed_historical_account_terminal_continuation_v01.py",
    "tests/test_sealed_historical_account_terminal_continuation_v01.py",
    ".github/workflows/sealed-historical-account-terminal-continuation-v01.yml",
)
ADDITIONAL_PARENTS = (
    f"research/strategy/{REPRODUCTION}.json",
    f"research/runtime/{REPRODUCTION}/freeze-manifest.json",
    f"research/data-audits/{REPRODUCTION}-comparison.json",
    f"research/data-audits/{REPRODUCTION}-success.json",
    f"research/data-audits/{REPRODUCTION}/reproduction-verification.json",
    f"research/data-audits/{REPRODUCTION}/reproduction-freeze.json",
    "docs/research/sealed_historical_account_residual_exit_reproduction_v01.md",
)


class Management(parent._Management):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._init_continuation()

    def _init_continuation(self):
        self._continuation = None
        self._continuation_attempts = 0
        self._continuation_log = []
        self._continuation_root = None

    def _continuation_event(self, kind, at, **values):
        self._continuation_log.append(seal({
            "contract_id": ID, "event_type": kind,
            "sequence": len(self._continuation_log),
            "previous_event_sha256": self._continuation_log[-1]["content_sha256"] if self._continuation_log else None,
            "entry_content_sha256": self._entry["content_sha256"],
            "opportunity_id": self._entry["opportunity_id"], "timestamp_ns": at,
            "remaining_quantity": self._remaining,
            "continuation_attempts": self._continuation_attempts,
            "active_stop_price": self._stop, **deepcopy(values)}))

    def _advance(self, at, phase):
        previous = self._pending
        own_order = previous is not None and "terminal_continuation" in previous["intent"]
        # Before the first child order the parent journals remain byte exact.
        # Child orders still use the identical waiting/native feedback reducer.
        if own_order:
            waiting._Management._advance(self, at, phase)
        else:
            super()._advance(at, phase)
        if previous is not None and self._pending is None:
            intent = previous["intent"]
            if own_order and not self._remaining:
                self._continuation = None
            elif self._remaining and intent["reason"] != "first_target" and (own_order or self._residual_attempts == 1):
                ack = self._events[-1]
                if ack["event_type"] != "sell_cancel_acknowledged":
                    raise RuntimeError("continuation requires confirmed cancellation acknowledgement")
                if self._continuation_root is None:
                    event = self._residual_log[-1]
                    if event["event_type"] != "residual_budget_exhausted":
                        raise RuntimeError("original two-terminal prefix not exhausted")
                    self._continuation_root = event["content_sha256"]
                # Prior intents are linked by hash, avoiding recursively nested
                # order histories during long sequences of unfilled attempts.
                context = seal({"parent_residual_exhaustion_content_sha256": self._continuation_root,
                    "prior_submission_intent_content_sha256": intent["content_sha256"],
                    "prior_order_id": ack["order_id"], "cancel_acknowledgement": deepcopy(ack),
                    "terminal_attempt_number": 3 + self._continuation_attempts})
                self._continuation = {"context": context, "expired": False}
                self._continuation_event("continuation_ready", ack["timestamp_ns"],
                    context=context, known_at_ns=at, clock_phase=phase)
        state = self._continuation
        if (state is not None and not state["expired"] and self._pending is None
                and at + TAIL_NS >= self._window["end_ns"]):
            state["expired"] = True
            self._continuation_event("continuation_expired", at, context=state["context"],
                original_window_end_ns=self._window["end_ns"])

    def observe_trade(self, item):
        result = super().observe_trade(item)
        state = self._continuation
        if (result is not None or state is None or state["expired"] or not self._remaining
                or self._waiting is not None or self._pending is not None or self._intent is not None):
            return result
        at = item["timestamp_ns"]
        eligible, _ = feedback.parent.print_eligibility(item["record"])
        if not eligible or at <= state["context"]["cancel_acknowledgement"]["timestamp_ns"]:
            return None
        if not self._full_attempted or self._latched is None or self._residual_attempts != 1:
            raise RuntimeError("continuation lost terminal authority or parent attempt history")
        self._intent = seal({**{key: self._entry[key] for key in
            ("opportunity_id", "path_id", "session_id", "scenario_id")},
            "entry_content_sha256": self._entry["content_sha256"], "decision_ts_ns": at,
            "reason": self._latched, "quantity": self._remaining,
            "trade_evidence": feedback.parent._evidence(item, "sip_transactions"),
            "red_signal": deepcopy(self._red) if self._latched == "first_red_candle" else None,
            "terminal_continuation": deepcopy(state["context"])})
        self._event("sell_intent", at, intent=self._intent)
        self._continuation_event("continuation_proposed", at, context=state["context"], intent=self._intent)
        return deepcopy(self._intent)

    def submit_intent(self, intent, *, tape, expected_tape_sha256):
        if "terminal_continuation" not in intent:
            return super().submit_intent(intent, tape=tape, expected_tape_sha256=expected_tape_sha256)
        state = self._continuation
        if (state is None or state["expired"] or self._residual_attempts != 1
                or intent["terminal_continuation"] != state["context"]
                or state["context"]["terminal_attempt_number"] != 3 + self._continuation_attempts
                or intent["quantity"] != self._remaining or intent["reason"] == "first_target"
                or intent["decision_ts_ns"] <= state["context"]["cancel_acknowledgement"]["timestamp_ns"]
                or intent["decision_ts_ns"] + TAIL_NS >= self._window["end_ns"]):
            raise ValueError("continuation authority, quantity, clock or original window differs")
        order = waiting._Management.submit_intent(self, intent, tape=tape,
            expected_tape_sha256=expected_tape_sha256)
        if order is not None:
            self._continuation_attempts += 1
            self._continuation_event("continuation_submitted", intent["decision_ts_ns"],
                context=state["context"], intent=intent, order=order)
        return order


class AccountDay(parent._AccountDay):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._exit_continuation_events = []

    def _start(self, args):
        row = super()._start(args)
        engine = Management.__new__(Management)
        engine.__dict__ = self._engine.__dict__
        engine._init_continuation()
        self._engine = engine
        return row

    def _transition(self, method, *args, **kwargs):
        before = 0 if self._engine is None else len(self._engine._continuation_log)
        result = super()._transition(method, *args, **kwargs)
        self._exit_continuation_events.extend(deepcopy(self._engine._continuation_log[before:]))
        return result

    def snapshot(self):
        value = super().snapshot()
        if self._exit_continuation_events:
            value.pop("content_sha256")
            value["exit_continuation_events"] = deepcopy(self._exit_continuation_events)
            return seal(value)
        return value


class Session(parent._Session):
    def __init__(self, slot, source, opening, resolve):
        super().__init__(slot, source, opening, resolve)
        ledger = parent.CampaignPortfolioLedger(self.account._ledger.session_date, self.account._ledger.constraints)
        self.account = AccountDay(pre_session_ledger=ledger,
            expected_pre_session_ledger_sha256=fingerprint(ledger.runtime_artifact()),
            path_id=slot["path_id"], scenario_id=slot["execution_scenario_id"])


# Aliases keep the copied session finisher and panel arithmetic explicit.
Decimal, localcontext = parent.Decimal, parent.localcontext
binding, accounts, producer = parent.binding, parent.accounts, parent.producer
fees, os, json = parent.fees, parent.os, parent.json
frozen, file_sha, require_exact = parent.frozen, parent.file_sha, parent.require_exact
canonical_fingerprint = fingerprint
BOUNDARY, RUNTIME_BOUNDARY = parent.BOUNDARY, parent.RUNTIME_BOUNDARY
BOUND_MANIFEST, PARENT_FREEZE = parent.BOUND_MANIFEST, parent.PARENT_FREEZE
source_programs, _source_item = parent.source_programs, parent._source_item
CONTRACT_ID = ID
CONTRACT_PATH = f"research/strategy/{ID}.json"
OUTPUT_PATH = f"research/runtime/{ID}"
PARENT_FILE = "90f5a02dacc26eec03e8aacb5758150c0efc8b6a9b56d9c1d4eb7f5d7287c716"
NEXT_GATE = "independently_verify_continuation_and_preserve_all_remaining_incomplete_states"


def mechanics():
    return {
        "hypothesis": "preserve_terminal_latch_until_flat_or_original_window_expiry",
        "authority": "original_two_terminal_prefix_then_each_confirmed_cancellation_with_positive_remainder",
        "clock": "first_eligible_SIP_print_strictly_after_actual_cancel_acknowledgement",
        "bound": "one_pending_order_strictly_advancing_clock_finite_original_stream_and_window",
        "quantity": "all_and_only_confirmed_unreserved_remaining_shares",
        "target": "unchanged_single_target_attempt_no_target_continuation",
        "signal_priority": "unchanged_stop_account_risk_red_latch_and_wait_supersession",
        "reference": "unchanged_fresh_nonhalted_causal_quote_or_unsubmitted_wait",
        "expiry": "550ms_tail_plus_1ns_must_fit_original_window_no_extension",
        "attempt_consumption": "only_actual_submission_waiting_spends_zero",
        "context": "prior_actual_intent_hash_actual_ack_parent_exhaustion_hash_sequential_terminal_number",
        "liquidity": "same_common_tape_and_consumed_source_record_set_across_all_orders_and_reentry",
        "execution_risk_fees_seeds_strategy_sources": "all_frozen_parent_values_unchanged",
        "audit": "separate_entry_bound_ready_proposed_submitted_expired_chain",
        "evaluation": "all_12_paths_360_slots_744_references_162_unavailable_no_financial_or_label_evaluation",
    }


def parent_pins(root):
    registration = frozen(root / f"research/runtime/{REPRODUCTION}/freeze-manifest.json")
    if registration["content_sha256"] != REPRODUCTION_FREEZE:
        raise ValueError("completed reproduction registration differs")
    contract = frozen(root / f"research/strategy/{REPRODUCTION}.json")
    if contract["content_sha256"] != registration["contract_content_sha256"]:
        raise ValueError("completed reproduction contract differs")
    for path, spec in registration["file_inventory"].items():
        if (root / path).stat().st_size != spec["bytes"] or file_sha(root / path) != spec["sha256"]:
            raise ValueError("completed reproduction bytes differ")
    pins = {**contract["frozen_parent_file_sha256"], **contract["implementation_file_sha256"]}
    pins.update({p: file_sha(root / p) for p in ADDITIONAL_PARENTS})
    for path, sha in pins.items():
        binding.availability._regular(root / path)
        if file_sha(root / path) != sha:
            raise ValueError("frozen continuation parent differs: " + path)
    return pins


def expected_contract(root):
    return seal({"schema_version": 1, "contract_id": ID,
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "parent_reproduction_freeze_content_sha256": REPRODUCTION_FREEZE,
        "parent_runtime_content_sha256": PARENT_RUNTIME, "parent_runtime_file_sha256": PARENT_FILE,
        "source_bindings_content_sha256": BOUND_MANIFEST, "source_archives": binding.SOURCES,
        "frozen_parent_file_sha256": parent_pins(root),
        "implementation_file_sha256": {p: file_sha(root / p) for p in OWN_FILES},
        "mechanics": mechanics(), "attempts_per_environment": 1,
        "allowed_environments": ["local", "github"], "automatic_retries_authorized": False,
        "next_gate": NEXT_GATE, **BOUNDARY})


def validate_registration(root):
    saved = frozen(root / CONTRACT_PATH)
    # Check committed additional-parent pins as well as reconstruction.
    for path, sha in saved["frozen_parent_file_sha256"].items():
        if file_sha(root / path) != sha:
            raise ValueError("registered continuation parent differs: " + path)
    require_exact(saved, expected_contract(root), "terminal continuation registration")


def documents(values, contract_sha, *, runtime=False):
    files = parent.documents(values, contract_sha, runtime=runtime)
    manifest = json.loads(files["freeze-manifest.json"])
    manifest.pop("content_sha256")
    manifest["contract_id"] = ID
    files["freeze-manifest.json"] = fees.encoded(seal(manifest))
    return files


def build_bundle(root):
    validate_registration(root)
    return documents({"terminal-continuation-mechanics.json": seal({"contract_id": ID,
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
    require_exact(sorted(binding.availability._inventory(output)), sorted(expected), "continuation inventory")
    for name, raw in expected.items():
        if (output / name).read_bytes() != raw:
            raise ValueError("continuation registration bytes differ: " + name)
    return seal({"verification_passed": True,
        "freeze_content_sha256": frozen(output / "freeze-manifest.json")["content_sha256"], **BOUNDARY})

def _session(slot, source, opening, previous_sha, resolve, dependency):
    """Frozen finisher arithmetic; add historical identity and explicit carry."""
    blocked, machine, failure = not producer._ready(opening), None, None
    if not blocked:
        try:
            machine = Session(slot, source, opening, resolve).run()
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
    runtime = seal({"contract_id": parent.parent.CONTRACT_ID, "session_id": slot["session_id"], "path_id": slot["path_id"],
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
    close = seal({"contract_id": parent.parent.CONTRACT_ID, "session_id": slot["session_id"], "path_id": slot["path_id"],
        "trading_date": slot["trading_date"], "session_index": slot["session_index"], "seed_applied": slot["seed_applied"],
        "source_slot_content_sha256": slot["content_sha256"], "previous_close_content_sha256": previous_sha,
        "source_runtime_content_sha256": runtime["content_sha256"], "account_state": state,
        "next_session_flat_cash_execution_ready": producer._ready(state), **RUNTIME_BOUNDARY})
    return {"runtime": runtime, "close": close}


def replay_panel(root, sources, *, expected_registration_sha256, checkpoint=None):
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
                if checkpoint is not None:
                    checkpoint(program["path_id"], pair)
                print(json.dumps({"path_id": program["path_id"], "session_index": slot["session_index"],
                    "status": pair["runtime"]["status"]}), flush=True)
                opening, previous = deepcopy(pair["close"]["account_state"]), pair["close"]["content_sha256"]
            results.append(seal({"contract_id": parent.parent.CONTRACT_ID, "artifact_type": "original_historical_account_path",
                "path_id": program["path_id"], "program_content_sha256": program["content_sha256"],
                "initial_account_state": initial, "seed_application_count": 1,
                "session_count": len(sessions), "sessions": sessions, "last_close_content_sha256": previous,
                "path_complete": all(s["runtime"]["status"] == "flat_complete" for s in sessions), **RUNTIME_BOUNDARY}))
    return seal({"contract_id": CONTRACT_ID, "artifact_type": "frozen_original_historical_account_terminal_continuation_replay",
        "parent_runtime_content_sha256": PARENT_RUNTIME,
        "registration_freeze_content_sha256": expected_registration_sha256,
        "source_bindings_content_sha256": BOUND_MANIFEST, "source_archives": binding.SOURCES,
        "paths": results, "next_gate": NEXT_GATE, **RUNTIME_BOUNDARY})
