"""Replay-verifiable account-state production, without historical activation.

A balance is derived from the approved seed and recomputed executions; it is
never accepted as a caller assertion. This child supports serial complete
position windows and exact flat-cash continuity. Open or incomplete states are
preserved and block execution in later sessions pending separate integration.
"""
from __future__ import annotations

from bisect import bisect_left
from copy import deepcopy
from datetime import date
from decimal import Decimal, localcontext
import hashlib
import heapq
import os
from pathlib import Path
import re

from momentumbot.research import sealed_historical_management_fee_reconciliation_v01 as fees
from momentumbot.research import sealed_historical_management_runner_v01 as runner
from momentumbot.research.campaign_portfolio import AccountClass, CampaignPortfolioLedger
from momentumbot.research.sealed_historical_execution_quote_v01 import canonical_fingerprint, file_sha, frozen, require_exact, seal

accounts = fees.feedback.accounts
CONTRACT_ID = "sealed-historical-account-state-producer-v0.1"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
OUTPUT_PATH = f"research/runtime/{CONTRACT_ID}"
MODULE_PATH = "src/momentumbot/research/sealed_historical_account_state_producer_v01.py"
SCRIPT_PATH = "scripts/build_sealed_historical_account_state_producer_v01.py"
CHECKER_PATH = "scripts/verify_sealed_historical_account_state_producer_v01.py"
TEST_PATH = "tests/test_sealed_historical_account_state_producer_v01.py"
WORKFLOW_PATH = ".github/workflows/sealed-historical-account-state-producer-v01.yml"
PARENT_COMMIT = "dcf1bc47b586653f3c0c97a4e433b4bdf1fff32a"
PARENT_TREE = "1a7bc4a67f04a148b53df1e14b5e99d1f96ecf5c"
PARENT_FREEZE = "0fa4f9b21e0d17fc12ba6daba3a36159daf0915d3b258cd9ef5d018d6747536c"
PARENT_PINS = {'.github/workflows/sealed-historical-management-fee-reconciliation-v01.yml': '2782f7618adce2a5d46844dced0ad826586dba2fcb099dfc7c9954c4cfc18cda',
 'requirements-sealed-execution-quote-v01.txt': '03f4da335027e4c83bcf38e523c2e11aeaae49778f5bd6caa47e4703348b31b4',
 'research/data-audits/sealed-historical-management-exit-acquisition-v0.1-independent-verification-34172486163.json': '3d0aea8e76e65eab40df8f309f33153ee80c05e8dc7c076366bc25d31ae9bb33',
 'research/data-audits/sealed-historical-management-exit-acquisition-v0.1-report-34172486163.json': '2765deba3a5559c3ddf75caf83adfc680d720dbfa1c8292ee310cc5be1a89117',
 'research/data-audits/sealed-historical-management-exit-inputs-v0.1-hosted-verification-34176013955.json': '61d2b97c583dfdb8cd02642e49d2ceb6e2663cadb763d1bb795029062536b02a',
 'research/data-audits/sealed-historical-management-exit-inputs-v0.1-independent-verification.json': '54649d3daaa57314dbf7aa4ceb7fb5fe4df2eefa8dc51cf3ca41fa6894e1be6a',
 'research/data-audits/sealed-historical-management-exit-quote-v0.1-xage-reuse.json': '799d8664916eb89f713dec276134400e87434251ff97ea5c0b0a29219983e75b',
 'research/data-audits/sealed-historical-management-fee-reconciliation-v0.1-hosted-verification-34181750634.json': '06840dfc13afe2f4479328e5ce5feabe0556559694a258dcf037767fbd3036a9',
 'research/data-audits/sealed-historical-management-fee-reconciliation-v0.1-independent-verification.json': '17214b643f3d0e2748d718eb0f6e27c3396094ce733af9c2fefa48656c7a7278',
 'research/data-audits/sealed-historical-management-projection-v0.1-independent-verification.json': 'ec712e11e5fa66e035507900115dcadac1fdd6ffba8f4f5f55a24532ab2e5f19',
 'research/runtime/sealed-historical-account-management-inputs-v0.1/account-session-input-plan.json': '8ca638578e7957c88f4314e0768a3c379ee0bd1278bd6d8c8e9caa2144f05108',
 'research/runtime/sealed-historical-management-exit-inputs-v0.1/exit-input-manifest.json': '9733ada8bd2a5db8a1fd21066377d71d71820066c4e1ea3cf52831b37292739e',
 'research/runtime/sealed-historical-management-exit-inputs-v0.1/freeze-manifest.json': '1acad35bfcbf016b26965f03d1759c13dddb0094124f97b71a9fb25bb271fb1c',
 'research/runtime/sealed-historical-management-exit-inputs-v0.1/opportunity-input-index.json': 'd58232d30a1b28a3be4a67273835eb8b0eae4a644049945aa213955fe5450ebc',
 'research/runtime/sealed-historical-management-exit-inputs-v0.1/readiness-report.json': '83cd64d28316da750fc8af33cac8859e2981c4b898e0308af10b2839b3311664',
 'research/runtime/sealed-historical-management-exit-inputs-v0.1/source-verification.json': '4557cdd6a1589dbfac64fa75db5a3b80037578146c0fc9510de52411f98770f4',
 'research/runtime/sealed-historical-management-fee-reconciliation-v0.1/fee-session-map.json': '64d49c1f337107f2a3ce1c5fdded4479514d24b80d62a47d216364528fc04c3c',
 'research/runtime/sealed-historical-management-fee-reconciliation-v0.1/freeze-manifest.json': '2ce37076b467ff8e867eb22f48888d9dd1416c52deb145210df4e58d0ebd1d90',
 'research/runtime/sealed-historical-management-fee-reconciliation-v0.1/readiness-report.json': 'f759a699e7414eb89a8aced05fd34eb29fe867fb928fd8f6b9e4440e287a5df9',
 'research/runtime/sealed-historical-management-fee-reconciliation-v0.1/reconciliation-mechanics.json': 'f581561c5a98140998f68429bea8c56dc036e4a39bda281f80699c6a7f5eeecb',
 'research/runtime/sealed-historical-management-fill-feedback-v0.1/entry-binding-requirements.json': '274a0a384ee9f682711c73aff23d46d561e9f99b08a317729edb700b087e7110',
 'research/runtime/sealed-historical-management-fill-feedback-v0.1/fill-feedback-mechanics.json': '1804798cb77e4ba36938d6d1c3f2201719f039bed2b247784c902b64814317f4',
 'research/runtime/sealed-historical-management-fill-feedback-v0.1/freeze-manifest.json': '6b0480b88442dcb83e75d2bbd790245e99dee5219c603b97b3de129e325c06e8',
 'research/runtime/sealed-historical-management-fill-feedback-v0.1/readiness-report.json': 'ae1e94aca391f80b356837d6b48dba62dbb8f852e79610b958707dabfe789d53',
 'research/runtime/sealed-historical-management-projection-v0.1/projection-input-requirements.json': '8b89b1ffd05de277bcff906140b5aeb142a823cce99260d9c967a8d1dc9e931f',
 'research/runtime/sealed-historical-management-runner-v0.1/exit-input-request-plan.json': '562ed42e20c7021eecf384e3a22aed5f5ce25ae15926dd93072a0313d0e6f461',
 'research/strategy/sealed-historical-management-exit-acquisition-v0.1-execution.json': '60bbd95d1017a3e0e2b3c40060e988f4a457d81b0280b4065c9712a03a1c54e0',
 'research/strategy/sealed-historical-management-exit-acquisition-v0.1.json': '147afc1aa99e33397c1d7f25d6bf17a443c5468d44f820edd40c0d64db989901',
 'research/strategy/sealed-historical-management-exit-inputs-v0.1.json': 'e51b3d22feec29408245de3a1bc27406ac9d714203b839a5d5baada3e692c536',
 'research/strategy/sealed-historical-management-fee-reconciliation-v0.1-fee-sources.json': 'bcb903f2b8e00dc168d3b5c54a6b435054e9bc08d4e3a57d3388044e29754929',
 'research/strategy/sealed-historical-management-fee-reconciliation-v0.1.json': 'afc564cc279c180819bef3b5a0e89e28e0ae2c086263e193f17f7a5d6f9c7bdf',
 'research/strategy/sealed-historical-management-fill-feedback-v0.1.json': 'eb41f6fc5112b84e85d014bbc0f990b14b521e76ca3141a23b7044ef54fbc178',
 'research/strategy/sealed-historical-management-projection-v0.1.json': '898bf4d7335a401d7f1962f9de48ee1956d5c2ac96ae9cd4b30d915d933a0a61',
 'scripts/build_sealed_historical_management_fee_reconciliation_v01.py': '1f0b02fb1387c50943c49561387665fce032139b18d66cd54175cb979ec08574',
 'scripts/run_offline_python_v13.py': 'fd28ca7e4a27832721a890a1a41af36863a7f13568ca9e85e17c2d5f35e0627d',
 'scripts/verify_sealed_historical_management_exit_inputs_v01.py': 'e7e859f6cb6bce8ffb4fa43915ff17cc8da1a07d9d768aac317fad3388595168',
 'scripts/verify_sealed_historical_management_fee_reconciliation_v01.py': '4ea27b0937c991b339660d626354fe11f209c63e4a1ba5075eacc27312594409',
 'src/momentumbot/research/account_chronological_integration.py': '917257a23abba6a075f6ba1fb97b5a01fb2729dfd63d8c90f7655d6d590afe41',
 'src/momentumbot/research/account_priority_policy.py': '3c0254bcd06425670e7158fb6c2be44edaa6c6f4b74c045798148f9d43e250d7',
 'src/momentumbot/research/campaign_portfolio.py': '5e8b5fb8e42cc739b8337bb544b811e57ccda2df5e7f46ca65ef5a30472149c4',
 'src/momentumbot/research/execution_realism.py': '446509405e3f44e3924c852569c5b06a096f61330552ede850a55c3da5794177',
 'src/momentumbot/research/prospective_daily_account_runtime.py': '45473afe1b947d56fd794ca80a9f72cc7934ca446a161ecb3c7f6ab1e4080d2a',
 'src/momentumbot/research/sealed_historical_account_inputs_v01.py': 'b7a28487807dd5d841a205d6ab74429fb3ed5f0f74b345712c57579e360228dd',
 'src/momentumbot/research/sealed_historical_management_exit_acquisition_v01.py': 'b9e7286a793a164f67ee416152327d6cd7fb98ed7cd38293c4a0dd5ed24663f8',
 'src/momentumbot/research/sealed_historical_management_exit_inputs_v01.py': '5c45ee5f5f05b70e72a070f4ecc35dfbbda56039493b711fd4fe712494ba7d2e',
 'src/momentumbot/research/sealed_historical_management_exit_quote_v01.py': '079200a3d0dededb5a3b775f46330ce3558d98fc8c1b67b10b2ce246cf8549f7',
 'src/momentumbot/research/sealed_historical_management_fee_reconciliation_v01.py': 'edf9f1d449ade225ef871a3976b8e0095b4f8a022080a761d836d62b185b2ab0',
 'src/momentumbot/research/sealed_historical_management_fill_feedback_v01.py': '8ac8b1ea0a8d3ccf57c07d5a3a5ddf0cd82409210dc16506c68400b768f8697d',
 'src/momentumbot/research/sealed_historical_management_projection_v01.py': '1741df5539180eed155c1b2160c7f9fccafdef869939da8330345aa56e548331',
 'src/momentumbot/research/sealed_historical_management_runner_v01.py': '7f352ac748e57f9e3a3c59971a07de152e6063b783bcd4eb6b48723f8f904fc5',
 'src/momentumbot/research/sealed_historical_record_order_v01.py': '407e02fc6fe908e26715fac2799f0debf356e96336b640e795b50287762dec6b',
 'tests/test_sealed_historical_account_inputs_v01.py': '69f0398e4edce650ffbeeca51e7501ae84da6bcabadf258b665ea3b07df58e1b',
 'tests/test_sealed_historical_management_fee_reconciliation_v01.py': '31169511e1391d6a2e3df60821017a6f95c788df1b11667ca07b02f9ce8e72da',
 'tests/test_sealed_historical_management_fill_feedback_v01.py': '18e9e649aa501d92fd058e956c5421615006ae7593b4bdc3c731932008113d8e',
 'tests/test_sealed_historical_management_projection_v01.py': 'b34f7fb9224eb0da2b467a7ba22b1056ef9385a1e77abb5626a57b45119dbefb',
 'tests/test_sealed_historical_management_runner_v01.py': 'd81119df620f327174779b0147204b7cad6714475771f18d70d487d8e46b93f5'}
BOUNDARY = dict(fees.BOUNDARY, original_market_source_provenance_authenticated=False,
                continuous_account_order_integration_verified=False, next_session_open_position_valuation_verified=False)
NEXT_GATE = "causal_open_position_valuation_and_continuous_account_order_scarcity_integration"
STATE_FIELDS = {"equity_usd", "buying_power_usd", "cumulative_realized_pnl_usd", "cumulative_fees_usd",
                "positions", "pending_orders", "campaigns", "unresolved_inputs"}
POSITION_FIELDS = {"entry_input", "bars", "trades", "expected_streams", "exit_group", "expected_exit_group_sha256",
                   "exit_tape", "expected_exit_tape_sha256"}
ENTRY_FIELDS = {"window", "source_decision", "tape", "expected_tape_sha256"}
MONEY = re.compile(r"-?(?:0|[1-9][0-9]*)\.[0-9]{2,9}\Z")


def money(value):
    """Preserve sub-cent execution amounts; never round a transported balance."""
    number = fees._decimal(value, "account money")
    if number == 0:
        return "0.00"
    text = format(number, "f")
    integer, _, fraction = text.partition(".")
    return integer + "." + fraction.rstrip("0").ljust(2, "0")


def validate_state(state):
    if not isinstance(state, dict) or set(state) != STATE_FIELDS:
        raise ValueError("complete exact account state required")
    for name in ("equity_usd", "buying_power_usd", "cumulative_realized_pnl_usd", "cumulative_fees_usd"):
        value = state[name]
        if value is None:
            continue
        if not isinstance(value, str) or not MONEY.fullmatch(value) or money(value) != value:
            raise ValueError("canonical exact account money required")
    if state["cumulative_fees_usd"] is not None and Decimal(state["cumulative_fees_usd"]) < 0:
        raise ValueError("negative cumulative fees")
    for name in ("positions", "pending_orders", "campaigns", "unresolved_inputs"):
        if not isinstance(state[name], list) or any(not isinstance(x, dict) for x in state[name]):
            raise ValueError("complete account collections required")
    def walk(value):
        if isinstance(value, dict):
            if accounts._FORBIDDEN.intersection(value):
                raise ValueError("retrospective account inputs prohibited")
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(state)
    canonical_fingerprint(state)


def _projection(value, label):
    exact = Decimal(value)
    projected = float(exact)
    if Decimal(str(projected)) != exact:
        raise ValueError(label + " cannot be represented by frozen ledger without decimal loss")
    return projected


def _new_day(slot, opening):
    validate_state(opening)
    kind = AccountClass.MAIN if slot["account_key"] == "main_account" else AccountClass.SMALL
    seed = accounts._validate_slot(slot)
    constraints = fees.feedback.materialize_account_constraints(fees.feedback.paper_account_policy(kind),
        account_id=seed["account_id"], starting_equity=_projection(opening["equity_usd"], "equity"),
        starting_buying_power=_projection(opening["buying_power_usd"], "buying power"))
    ledger = CampaignPortfolioLedger(date.fromisoformat(slot["trading_date"]), constraints)
    return fees.ReconciledAccountDay(pre_session_ledger=ledger,
        expected_pre_session_ledger_sha256=canonical_fingerprint(ledger.runtime_artifact()),
        path_id=slot["path_id"], scenario_id=slot["execution_scenario_id"])


def _entry_arguments(account, slot, spec):
    if not isinstance(spec, dict) or set(spec) != ENTRY_FIELDS:
        raise ValueError("producer derives ledger and context pins; exact entry source fields required")
    ledger = account.ledger_copy()
    context = {"window": spec["window"], "slot": slot, "source_decision": spec["source_decision"]}
    return {**deepcopy(context), "tape": spec["tape"], "expected_tape_sha256": spec["expected_tape_sha256"],
        "pre_entry_ledger": ledger, "expected_pre_ledger_sha256": canonical_fingerprint(ledger.runtime_artifact()),
        "expected_context_sha256": canonical_fingerprint(context)}


def _exit_evidence(entry, spec):
    """Same preflight as the frozen position runner, before an account entry."""
    group, tape = spec["exit_group"], spec["exit_tape"]
    fees.feedback._pinned(group, spec["expected_exit_group_sha256"], "exit group")
    fees.feedback._pinned(tape, spec["expected_exit_tape_sha256"], "complete exit tape")
    accounts._sealed(group, "exit group")
    if set(tape) != {"quote_request", "quote_records", "status_request", "status_records"}:
        raise ValueError("exact complete exit tape fields required")
    require_exact([tape["quote_request"], tape["status_request"]], group["requests"], "registered common exit requests")
    window = entry["window"]
    op = window["opportunity"]
    members = [v for v in group["members"] if v["opportunity_id"] == op["opportunity_id"]]
    if len(members) != 1 or members[0]["window_content_sha256"] != canonical_fingerprint(window):
        raise ValueError("exit scope must bind the original opportunity window")
    if (group["symbol"] != op["symbol"] or group["trading_date"] != op["trading_date"]
            or group["required_quote_start_ns"] > op["decision_ts_ns"] - runner.projection.PRE_QUOTE_NS
            or group["required_end_ns"] < window["end_ns"]):
        raise ValueError("common scope does not cover original opportunity")
    for request in group["requests"]:
        if (request["symbols"] != [op["symbol"]] or request["trading_date"] != op["trading_date"]
                or request["start_ns"] > group["required_quote_start_ns"] or request["end_ns"] < group["required_end_ns"]):
            raise ValueError("source request does not cover complete common scope")
    if tape["quote_request"]["end_ns"] != tape["status_request"]["end_ns"]:
        raise ValueError("common quote/status ends differ")
    quotes = fees.feedback.adapter.quote_events(tape["quote_records"], tape["quote_request"])
    fees.feedback.adapter.status_events(tape["status_records"], tape["status_request"])
    if set(spec["expected_streams"]) != {"raw_sip_1m_bars", "sip_transactions"}:
        raise ValueError("both complete management streams required")
    return [q.ts_recv_ns for q in quotes]


def run_reconciled_position(account, slot, spec):
    """Frozen clock ordering, with every transition routed through reconciliation.

    No global scheduling or scarcity choice is made here. Later decisions must
    follow the entire previous window. Complete trailing input is verified even
    after a fill closes the shares. Failures retain the account's known state.
    """
    if not isinstance(spec, dict) or set(spec) != POSITION_FIELDS:
        raise ValueError("exact position program fields required")
    stage, orders = "entry_or_exit_evidence", []
    try:
        entry = _entry_arguments(account, slot, spec["entry_input"])
        quote_times = _exit_evidence(entry, spec)
        account.start_position(entry_arguments=entry, expected_account_content_sha256=account.snapshot()["content_sha256"])
        stage = "management_stream"
        cursors = [runner._Cursor(records, entry["window"], resource, spec["expected_streams"][resource])
            for records, resource in ((spec["bars"], "raw_sip_1m_bars"), (spec["trades"], "sip_transactions"))]
        ticks, scheduled = [], set()
        end = entry["window"]["end_ns"]
        while any(c.value is not None for c in cursors) or ticks:
            live = [c for c in cursors if c.value is not None]
            cursor = min(live, key=lambda c: c.key()) if live else None
            tick = ticks[0] if ticks else None
            if tick is not None and (cursor is None or tick < cursor.key()[0]):
                heapq.heappop(ticks)
                scheduled.remove(tick)
                stage = "fill_feedback"
                account.settle(tick)
                continue
            stage = "management_stream"
            _, phase = cursor.key()
            if phase == 0:
                account.observe_bar(cursor.value)
            else:
                intent = account.observe_trade(cursor.value)
                if intent:
                    stage = "executable_exit_evidence"
                    order = account.submit_intent(intent, tape=spec["exit_tape"], expected_tape_sha256=spec["expected_exit_tape_sha256"])
                    orders.append(order)
                    times = {order["arrival_ts_ns"], order["cancel_requested_ts_ns"], order["cancel_ack_ts_ns"]}
                    lo = bisect_left(quote_times, order["arrival_ts_ns"])
                    hi = bisect_left(quote_times, order["cancel_ack_ts_ns"])
                    times.update(quote_times[lo:hi])
                    for stamp in times:
                        if stamp >= end:
                            raise ValueError("feedback outside original opportunity")
                        if stamp not in scheduled:
                            heapq.heappush(ticks, stamp)
                            scheduled.add(stamp)
            stage = "management_stream"
            cursor.advance()
        stage = "final_feedback"
        account.settle(end - 1)
    except (ValueError, KeyError, TypeError, OverflowError, OSError) as exc:
        return seal({"status": "input_failure", "stage": stage, "error_type": type(exc).__name__,
            "error": str(exc)[:300], "position_program_sha256": canonical_fingerprint(spec),
            "orders": orders, "complete_streams_verified": False, "account_snapshot": account.snapshot(), **BOUNDARY})
    return seal({"status": "complete", "position_program_sha256": canonical_fingerprint(spec),
        "orders": orders, "complete_streams_verified": True, "account_snapshot": account.snapshot(), **BOUNDARY})


def _collections(snapshot):
    """Only public confirmed state; pending outcome prices never enter a close."""
    engine = snapshot["management"]
    positions, pending, unresolved = [], [], []
    if engine is None:
        return positions, pending, unresolved
    entry = engine["entry"]
    if engine["remaining_quantity"]:
        positions.append({"activation_id": entry["activation_id"], "symbol": entry["symbol"],
            "entry_fill_id": entry["fill_id"], "quantity": engine["remaining_quantity"], "entry_price": entry["fill_price"],
            "active_stop_price": str(engine["active_stop_price"]), "target_quantity": engine["target_quantity"],
            "target_filled_quantity": engine["target_filled_quantity"], "management_status": engine["status"],
            "source_management_content_sha256": engine["content_sha256"], "valuation_usd": None})
    clock = (engine["clock_ns"], engine["clock_phase"])
    ack_known = (entry["entry_cancel_ack_ns"], 2) <= clock
    if not ack_known:
        pending.append({"kind": "entry_cancel_pending", "order_id": entry["order"]["order_id"],
            "quantity": entry["order"]["quantity"], "confirmed_filled_quantity": entry["quantity"],
            "remaining_order_quantity": entry["order"]["quantity"] - entry["quantity"],
            "cancel_ack_ts_ns": entry["entry_cancel_ack_ns"]})
    if engine["pending_order"]:
        order = next(e["order"] for e in reversed(engine["events"]) if e["event_type"] == "sell_submitted")
        pending.append({"kind": "sell_cancel_pending", **deepcopy(order),
            "confirmed_filled_quantity": sum(f["quantity"] for f in engine["fills"] if f["order_id"] == order["order_id"]),
            "remaining_order_quantity": engine["reserved_sell_quantity"]})
    if engine["outstanding_intent"] is not None:
        unresolved.append({"kind": "unsubmitted_exit_intent", "blocks_next_session": True,
            "intent": deepcopy(engine["outstanding_intent"])})
    return positions, pending, unresolved


def _ready(state):
    return (not state["positions"] and not state["pending_orders"]
        and not any(x["blocks_next_session"] for x in state["unresolved_inputs"])
        and all(state[k] is not None and Decimal(state[k]) > 0 for k in ("equity_usd", "buying_power_usd")))


def _slot(slot):
    seed = accounts._validate_slot(slot)
    refs = slot["opportunity_inputs"]
    if (not isinstance(refs, list) or len({r["opportunity_id"] for r in refs}) != len(refs)
            or any(set(r) != {"opportunity_id", "availability_content_sha256", "input_status", "reason"} for r in refs)
            or any(r["input_status"] not in ("available", "unavailable") for r in refs)
            or slot["unavailable_opportunity_count"] != sum(r["input_status"] == "unavailable" for r in refs)):
        raise ValueError("complete unique opportunity references required")
    return seed


def _transport(slot, state, runtime_sha):
    # The frozen transport accepts cents only. Preserve it unchanged; use the
    # child's exact state when nanodollar execution produces a fractional cent.
    if any(state[k] is not None and Decimal(state[k]) != Decimal(state[k]).quantize(Decimal(".01"))
           for k in ("equity_usd", "buying_power_usd", "cumulative_realized_pnl_usd", "cumulative_fees_usd")):
        return None
    accounts._validate_state(state)
    return seal({"session_id": slot["session_id"], "path_id": slot["path_id"], "trading_date": slot["trading_date"],
        "source_runtime_content_sha256": runtime_sha, "account_state": deepcopy(state)})


def _session(slot, session, opening, previous_close_sha):
    if set(session) != {"session_id", "positions"} or session["session_id"] != slot["session_id"] or not isinstance(session["positions"], list):
        raise ValueError("ordered session program must match exact registered slot")
    blocked = not _ready(opening)
    results, dispositions, failures = [], [], []
    refs = {r["opportunity_id"]: r for r in slot["opportunity_inputs"]}
    seen = set()
    for ref in refs.values():
        if ref["input_status"] == "unavailable":
            dispositions.append({**deepcopy(ref), "disposition": "unavailable_input"})
    account = None
    if blocked:
        if session["positions"]:
            raise ValueError("prior unresolved or insolvent state blocks new execution; no reset allowed")
    else:
        try:
            account = _new_day(slot, opening)
        except ValueError as exc:
            blocked = True
            failures.append({"kind": "opening_ledger_projection_unavailable", "blocks_next_session": True, "error": str(exc)[:300]})
            if session["positions"]:
                raise ValueError("opening projection blocks execution") from exc
        for spec in session["positions"]:
            if set(spec) != POSITION_FIELDS or set(spec["entry_input"]) != ENTRY_FIELDS:
                raise ValueError("exact position and entry program fields required")
            op = spec["entry_input"]["window"]["opportunity"]
            oid = op["opportunity_id"]
            if oid not in refs or refs[oid]["input_status"] != "available" or oid in seen:
                raise ValueError("position must be a unique available opportunity in this slot")
            if not op["symbol"].startswith("SYNTHETIC"):
                raise ValueError("component replay accepts synthetic source fixtures only")
            if failures:
                raise ValueError("input failure blocks later position execution")
            seen.add(oid)
            result = run_reconciled_position(account, slot, spec)
            results.append(result)
            dispositions.append({**deepcopy(refs[oid]), "disposition": "executed_source_program" if result["status"] == "complete" else "input_failure",
                                 "position_result_content_sha256": result["content_sha256"]})
            if result["status"] != "complete":
                failures.append({"kind": "position_input_failure", "opportunity_id": oid, "blocks_next_session": True,
                    "position_result_content_sha256": result["content_sha256"], "stage": result["stage"]})
            else:
                state = account.snapshot()["management"]
                if not state["remaining_quantity"] and not state["pending_order"] and state["outstanding_intent"] is None:
                    account.release_position()
    for ref in refs.values():
        if ref["input_status"] == "available" and ref["opportunity_id"] not in seen:
            dispositions.append({**deepcopy(ref), "disposition": "unprocessed_available_input"})
    input_gaps = [{"kind": d["disposition"], "opportunity_id": d["opportunity_id"],
                   "availability_content_sha256": d["availability_content_sha256"], "reason": d["reason"],
                   "blocks_next_session": d["disposition"] == "unprocessed_available_input"}
                  for d in dispositions if d["disposition"] in ("unavailable_input", "unprocessed_available_input")]
    snapshot = None if account is None else account.snapshot()
    if blocked:
        state = deepcopy(opening)
        state["unresolved_inputs"] += failures + input_gaps
        state["unresolved_inputs"].append({"kind": "preceding_state_blocks_execution", "blocks_next_session": True,
                                            "previous_close_content_sha256": previous_close_sha})
        net_delta = gross_delta = fee_delta = Decimal(0)
    else:
        positions, pending, extra = _collections(snapshot)
        net_delta = Decimal(snapshot["exact_account"]["net_realized_pnl"])
        gross_delta = Decimal(snapshot["exact_account"]["gross_realized_pnl"])
        fee_delta = Decimal(snapshot["fee_book"]["fees"]["total_charged"])
        state = {"equity_usd": None if positions else money(Decimal(opening["equity_usd"]) + net_delta),
            "buying_power_usd": money(snapshot["exact_account"]["remaining_buying_power"]),
            "cumulative_realized_pnl_usd": money(Decimal(opening["cumulative_realized_pnl_usd"]) + net_delta),
            "cumulative_fees_usd": money(Decimal(opening["cumulative_fees_usd"]) + fee_delta),
            "positions": positions, "pending_orders": pending,
            "campaigns": deepcopy(opening["campaigns"]) + deepcopy(snapshot["ledger"]["campaigns"]),
            "unresolved_inputs": deepcopy(opening["unresolved_inputs"]) + input_gaps + failures + extra}
    validate_state(state)
    runtime = seal({"contract_id": CONTRACT_ID, "session_id": slot["session_id"], "path_id": slot["path_id"],
        "source_slot_content_sha256": slot["content_sha256"], "session_program_sha256": canonical_fingerprint(session),
        "opening_account_state_sha256": canonical_fingerprint(opening), "position_results": results,
        "opportunity_dispositions": dispositions, "reconciliation_snapshot": snapshot,
        "blocked_before_execution": blocked, "session_gross_realized_pnl_usd": money(gross_delta),
        "session_net_realized_pnl_usd": money(net_delta), "session_fees_usd": money(fee_delta), **BOUNDARY})
    close = seal({"contract_id": CONTRACT_ID, "artifact_type": "replay_derived_account_session_checkpoint",
        "session_id": slot["session_id"], "path_id": slot["path_id"], "trading_date": slot["trading_date"],
        "session_index": slot["session_index"], "source_slot_content_sha256": slot["content_sha256"],
        "previous_close_content_sha256": previous_close_sha, "seed_applied": slot["session_index"] == 0,
        "source_runtime_content_sha256": runtime["content_sha256"], "account_state": state,
        "next_session_flat_cash_execution_ready": _ready(state),
        "checkpoint_status": "blocked_prior_state" if blocked else "open_requires_valuation" if state["positions"]
            else "flat_state_ready" if _ready(state) else "incomplete_or_unfunded",
        "money_semantics": "exact_USD_2_to_9_decimal_places_cumulative_realized_is_net_of_fees",
        "frozen_cent_transport": _transport(slot, state, runtime["content_sha256"]), **BOUNDARY})
    return {"runtime": runtime, "close": close}


def replay_path(program, *, expected_program_content_sha256):
    """Recompute a complete prefix from once-only seeds; accept no prior balances.

    Synthetic fixtures exercise the producer. Real-source origin, registration
    of chronological selection and historical activation remain separate gates.
    The input commitment must come from outside the claimed result.
    """
    accounts._sealed(program, "account replay program")
    if program["content_sha256"] != expected_program_content_sha256:
        raise ValueError("program differs from independent caller commitment")
    if set(program) != {"contract_id", "artifact_type", "input_scope", "path_id", "slots", "sessions", "content_sha256"}:
        raise ValueError("exact replay program fields required; caller balances and closes are forbidden")
    if (program["contract_id"] != CONTRACT_ID or program["artifact_type"] != "account_state_replay_program"
            or program["input_scope"] != "synthetic_component_fixture"):
        raise ValueError("historical execution requires its separately registered activation child")
    slots, sessions = program["slots"], program["sessions"]
    if not isinstance(slots, list) or len(slots) != 30 or not isinstance(sessions, list) or not 1 <= len(sessions) <= 30:
        raise ValueError("all 30 slots and a nonempty contiguous session prefix required")
    for index, slot in enumerate(slots):
        _slot(slot)
        if slot["session_index"] != index or slot["path_id"] != program["path_id"]:
            raise ValueError("same path and exact chronological slot index required")
    initial = accounts.account_state_input(slots[0])["account_state"]
    previous_sha, opening, results = None, initial, []
    with localcontext() as context:
        context.prec = 60
        for slot, session in zip(slots, sessions):
            result = _session(slot, session, opening, previous_sha)
            results.append(result)
            opening = deepcopy(result["close"]["account_state"])
            previous_sha = result["close"]["content_sha256"]
    return seal({"contract_id": CONTRACT_ID, "artifact_type": "replayed_account_path_prefix",
        "program_content_sha256": program["content_sha256"], "slot_catalog_sha256": canonical_fingerprint(slots),
        "path_id": program["path_id"], "seed_content_sha256": slots[0]["seed_content_sha256"],
        "initial_account_state": initial, "session_count": len(results), "seed_application_count": 1,
        "sessions": results, "last_close_content_sha256": previous_sha,
        "producer_mechanics_replayed": True, "synthetic_only": True, **BOUNDARY})


def verify_path(program, result, *, expected_program_content_sha256, expected_result_content_sha256):
    accounts._sealed(result, "account path result")
    if result["content_sha256"] != expected_result_content_sha256:
        raise ValueError("result differs from independent caller commitment")
    expected = replay_path(program, expected_program_content_sha256=expected_program_content_sha256)
    require_exact(result, expected, "producer replay result")
    return seal({"verification_passed": True, "producer_state_authenticated_by_replay": True,
        "program_content_sha256": expected_program_content_sha256, "result_content_sha256": expected_result_content_sha256,
        "session_count": expected["session_count"], "last_close_content_sha256": expected["last_close_content_sha256"], **BOUNDARY})


def mechanics():
    return {
        "producer": "derive_ledger_from_once_only_seed_then_recompute_every_confirmed_execution_no_caller_balances_or_close_import",
        "authentication": "independently_pinned_program_and_result_plus_complete_deterministic_replay_not_self_attested_hashes",
        "source_trust": "replay_proves_computation_not_market_source_origin_synthetic_only_until_historical_execution_child",
        "chronology": "complete_prefix_of_registered_30_slots_same_account_horizon_scenario_previous_close_exact",
        "position_scheduler": "frozen_two_stream_order_and_public_feedback_ticks_routed_through_fee_account_reducer",
        "serial_scope": "entire_previous_window_verified_before_next_position_global_overlap_scarcity_is_separate_integration",
        "cash_continuity": "flat_exact_cash_carries_directly_positive_balances_required_daily_guards_and_fee_book_restart_without_reseeding",
        "open_continuity": "positions_pending_orders_intents_and_input_failures_preserved_no_market_value_invented_blocks_future_execution",
        "availability": "every_slot_reference_dispositioned_unavailable_retained_without_rescue_unprocessed_available_blocks_next_session",
        "precision": "exact_USD_two_to_nine_fractional_digits_never_round_subcent_execution_proceeds_legacy_cent_transport_only_if_exact",
        "realized_pnl": "cumulative_net_after_fees_gross_and_fee_deltas_separate_never_double_subtract_fees",
        "seed": "approved_30000_main_2000_small_once_per_path_no_later_seed_argument",
        "empty_sessions": "preserve_registered_zero_decision_dates_and_carry_prior_state_without_fabricated_execution",
        "failure": "retain_known_account_and_unresolved_order_state_no_zero_trade_replacement_or_implicit_liquidation",
    }


def expected_contract(root):
    return seal({"schema_version": 1, "contract_id": CONTRACT_ID,
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "parent_reconciliation_freeze_content_sha256": PARENT_FREEZE,
        "frozen_parent_file_sha256": PARENT_PINS,
        "hypothesis": "replayed_execution_history_authenticates_account_state_and_preserves_capital_and_unresolved_state_across_sessions",
        "mechanics": mechanics(), "account_state_producer_mechanics_registered": True,
        "implementation_file_sha256": {p: file_sha(root / p) for p in (MODULE_PATH, SCRIPT_PATH, CHECKER_PATH, TEST_PATH, WORKFLOW_PATH)},
        "next_gate": NEXT_GATE, **BOUNDARY})


def validate_registration(root):
    for path, sha in PARENT_PINS.items():
        accounts.availability._regular(root / path)
        if file_sha(root / path) != sha:
            raise ValueError("account producer parent differs: " + path)
    fees.verify_bundle(root, root / fees.OUTPUT_PATH)
    if frozen(root / fees.OUTPUT_PATH / "freeze-manifest.json")["content_sha256"] != PARENT_FREEZE:
        raise ValueError("reconciliation freeze differs")
    require_exact(frozen(root / CONTRACT_PATH), expected_contract(root), "account producer registration")
    return seal({"verification_passed": True, "contract_content_sha256": expected_contract(root)["content_sha256"], **BOUNDARY})


def build_bundle(root):
    validate_registration(root)
    plan = frozen(root / fees.feedback.parent.ACCOUNT_PLAN)
    slots = [{"path_id": p["path_id"], "session_id": s["session_id"], "trading_date": s["trading_date"],
        "session_index": s["session_index"], "previous_session_id": s["previous_session_id"],
        "source_slot_content_sha256": s["content_sha256"], "seed_applied": s["seed_applied"],
        "opportunity_inputs": s["opportunity_inputs"]} for p in plan["paths"] for s in p["sessions"]]
    payloads = {
        "account-state-dependencies.json": seal({"contract_id": CONTRACT_ID,
            "account_plan_content_sha256": plan["content_sha256"], "slots": slots,
            "path_count": 12, "session_count": len(slots), "seed_applications": sum(s["seed_applied"] for s in slots),
            "previous_close_dependencies": sum(s["previous_session_id"] is not None for s in slots), **BOUNDARY}),
        "producer-mechanics.json": seal({"contract_id": CONTRACT_ID, "mechanics": mechanics(), **BOUNDARY}),
        "readiness-report.json": seal({"contract_id": CONTRACT_ID, "account_state_producer_mechanics_registered": True,
            "exact_flat_cash_continuity_implemented": True, "replay_verification_implemented": True,
            "synthetic_testing_only": True, "historical_execution_count": 0, "source_tapes_reopened": False,
            "open_position_continuation_requires_valuation_and_execution_integration": True,
            "next_gate": NEXT_GATE, **BOUNDARY}),
    }
    files = {name: fees.encoded(value) for name, value in payloads.items()}
    files["freeze-manifest.json"] = fees.encoded(seal({"contract_id": CONTRACT_ID, "parent_commit_sha": PARENT_COMMIT,
        "contract_content_sha256": expected_contract(root)["content_sha256"],
        "file_inventory": {name: {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)} for name, raw in files.items()},
        "document_content_sha256": {name: value["content_sha256"] for name, value in payloads.items()}, **BOUNDARY}))
    return files


def _output(root, output):
    if output.is_symlink() or any(p.is_symlink() for p in output.parents):
        raise ValueError("symlink output rejected")
    if output.resolve().is_relative_to(root.resolve()) and output.resolve() != (root / OUTPUT_PATH).resolve():
        raise ValueError("cannot overwrite frozen repository inputs")


def verify_bundle(root, output):
    _output(root, output)
    expected = build_bundle(root)
    inventory = accounts.availability._inventory(output)
    if set(inventory) != set(expected):
        raise ValueError("account producer inventory differs")
    for name, raw in expected.items():
        if (output / name).read_bytes() != raw:
            raise ValueError("account producer reconstruction differs: " + name)
    return seal({"verification_passed": True, "contract_id": CONTRACT_ID, "file_inventory": inventory,
        "freeze_content_sha256": frozen(output / "freeze-manifest.json")["content_sha256"], **BOUNDARY})


def write_bundle(root, output):
    _output(root, output)
    if output.exists():
        raise FileExistsError("account producer registration is write-once")
    files = build_bundle(root)
    output.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        with (output / name).open("xb") as handle:
            if handle.write(raw) != len(raw):
                raise OSError("short metadata write")
            handle.flush()
            os.fsync(handle.fileno())
    return verify_bundle(root, output)
