"""Causal next-session marks for replay-verified account state.

Synthetic component scope: a mark supplies an equity anchor, not an execution
or an implicit cancellation. Historical source provenance and continuous
position/order execution remain separate dependencies.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, localcontext
import hashlib
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from momentumbot.models import current_general_2026, current_small_account_2026
from momentumbot.research import sealed_historical_account_state_producer_v01 as parent
from momentumbot.research.sealed_historical_execution_quote_v01 import canonical_fingerprint, file_sha, frozen, require_exact, seal

CONTRACT_ID = "sealed-historical-account-valuation-v0.1"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
OUTPUT_PATH = f"research/runtime/{CONTRACT_ID}"
MODULE_PATH = "src/momentumbot/research/sealed_historical_account_valuation_v01.py"
SCRIPT_PATH = "scripts/build_sealed_historical_account_valuation_v01.py"
CHECKER_PATH = "scripts/verify_sealed_historical_account_valuation_v01.py"
TEST_PATH = "tests/test_sealed_historical_account_valuation_v01.py"
WORKFLOW_PATH = ".github/workflows/sealed-historical-account-valuation-v01.yml"
PARENT_COMMIT = "7840e5696fe8d2961ade913771f2c7cfa257493a"
PARENT_TREE = "df78ff3a64a2caf2ae93b95a56538b394964625d"
PARENT_FREEZE = "81fafc0a88ca1fcb5f74caf94f7aa55d557960b8f51f15334a4272adf71c594d"
PARENT_PINS = {'.github/workflows/sealed-historical-account-state-producer-v01.yml': 'c47cd7e2f814a11dab2b93179eed8d0d389be48a02a5790c410cac0e482dfcf9',
 '.github/workflows/sealed-historical-management-fee-reconciliation-v01.yml': '2782f7618adce2a5d46844dced0ad826586dba2fcb099dfc7c9954c4cfc18cda',
 'requirements-sealed-execution-quote-v01.txt': '03f4da335027e4c83bcf38e523c2e11aeaae49778f5bd6caa47e4703348b31b4',
 'research/data-audits/sealed-historical-account-state-producer-v0.1-hosted-verification-34185273453.json': '826eabfe3141bd2f3dfa5abdf78a2ad0384e73b5f03dc030b5e0340db488570a',
 'research/data-audits/sealed-historical-account-state-producer-v0.1-independent-verification.json': '160c9ef1e4bc2eaa9ada69d7da2ea057814539f00524f12e41a53b2f2ad8a269',
 'research/data-audits/sealed-historical-management-exit-acquisition-v0.1-independent-verification-34172486163.json': '3d0aea8e76e65eab40df8f309f33153ee80c05e8dc7c076366bc25d31ae9bb33',
 'research/data-audits/sealed-historical-management-exit-acquisition-v0.1-report-34172486163.json': '2765deba3a5559c3ddf75caf83adfc680d720dbfa1c8292ee310cc5be1a89117',
 'research/data-audits/sealed-historical-management-exit-inputs-v0.1-hosted-verification-34176013955.json': '61d2b97c583dfdb8cd02642e49d2ceb6e2663cadb763d1bb795029062536b02a',
 'research/data-audits/sealed-historical-management-exit-inputs-v0.1-independent-verification.json': '54649d3daaa57314dbf7aa4ceb7fb5fe4df2eefa8dc51cf3ca41fa6894e1be6a',
 'research/data-audits/sealed-historical-management-exit-quote-v0.1-xage-reuse.json': '799d8664916eb89f713dec276134400e87434251ff97ea5c0b0a29219983e75b',
 'research/data-audits/sealed-historical-management-fee-reconciliation-v0.1-hosted-verification-34181750634.json': '06840dfc13afe2f4479328e5ce5feabe0556559694a258dcf037767fbd3036a9',
 'research/data-audits/sealed-historical-management-fee-reconciliation-v0.1-independent-verification.json': '17214b643f3d0e2748d718eb0f6e27c3396094ce733af9c2fefa48656c7a7278',
 'research/data-audits/sealed-historical-management-projection-v0.1-independent-verification.json': 'ec712e11e5fa66e035507900115dcadac1fdd6ffba8f4f5f55a24532ab2e5f19',
 'research/runtime/sealed-historical-account-management-inputs-v0.1/account-session-input-plan.json': '8ca638578e7957c88f4314e0768a3c379ee0bd1278bd6d8c8e9caa2144f05108',
 'research/runtime/sealed-historical-account-state-producer-v0.1/account-state-dependencies.json': '4431b54c2b568608902a2301e8cffc461c3c5c180fe41a04003b4c34cb770151',
 'research/runtime/sealed-historical-account-state-producer-v0.1/freeze-manifest.json': '72d81edc01d0c6dcb70c31d884276cc61d07ab5a4a22a0255d7cd4ab888a15c5',
 'research/runtime/sealed-historical-account-state-producer-v0.1/producer-mechanics.json': '4f6d713eed6d5452cc9eddc7b824c2c661bfc976c4ea99ca5fbfa5628b7067ed',
 'research/runtime/sealed-historical-account-state-producer-v0.1/readiness-report.json': 'a0908d0970d62659ac0689cf054117bc525327538d15caac0df58bd8efe149f2',
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
 'research/strategy/sealed-historical-account-state-producer-v0.1.json': 'd893c4b78ac26d996f72d0b3a373535704ebb5cbd8bda04ad4d59901d2800cb3',
 'research/strategy/sealed-historical-management-exit-acquisition-v0.1-execution.json': '60bbd95d1017a3e0e2b3c40060e988f4a457d81b0280b4065c9712a03a1c54e0',
 'research/strategy/sealed-historical-management-exit-acquisition-v0.1.json': '147afc1aa99e33397c1d7f25d6bf17a443c5468d44f820edd40c0d64db989901',
 'research/strategy/sealed-historical-management-exit-inputs-v0.1.json': 'e51b3d22feec29408245de3a1bc27406ac9d714203b839a5d5baada3e692c536',
 'research/strategy/sealed-historical-management-fee-reconciliation-v0.1-fee-sources.json': 'bcb903f2b8e00dc168d3b5c54a6b435054e9bc08d4e3a57d3388044e29754929',
 'research/strategy/sealed-historical-management-fee-reconciliation-v0.1.json': 'afc564cc279c180819bef3b5a0e89e28e0ae2c086263e193f17f7a5d6f9c7bdf',
 'research/strategy/sealed-historical-management-fill-feedback-v0.1.json': 'eb41f6fc5112b84e85d014bbc0f990b14b521e76ca3141a23b7044ef54fbc178',
 'research/strategy/sealed-historical-management-projection-v0.1.json': '898bf4d7335a401d7f1962f9de48ee1956d5c2ac96ae9cd4b30d915d933a0a61',
 'scripts/build_sealed_historical_account_state_producer_v01.py': '251c04f24df67b866925668da49588515d5860ab405c5bb507a275d429c0a315',
 'scripts/build_sealed_historical_management_fee_reconciliation_v01.py': '1f0b02fb1387c50943c49561387665fce032139b18d66cd54175cb979ec08574',
 'scripts/run_offline_python_v13.py': 'fd28ca7e4a27832721a890a1a41af36863a7f13568ca9e85e17c2d5f35e0627d',
 'scripts/verify_sealed_historical_account_state_producer_v01.py': '93d8feb3ff4eb628e7530ad96bf4c97fcc290a48b6fa571b19955b1bf501a659',
 'scripts/verify_sealed_historical_management_exit_inputs_v01.py': 'e7e859f6cb6bce8ffb4fa43915ff17cc8da1a07d9d768aac317fad3388595168',
 'scripts/verify_sealed_historical_management_fee_reconciliation_v01.py': '4ea27b0937c991b339660d626354fe11f209c63e4a1ba5075eacc27312594409',
 'src/momentumbot/models.py': 'efa4857a1fa92d24896b750b7df4846abd952fafd966f046054e0aad21325a82',
 'src/momentumbot/research/account_chronological_integration.py': '917257a23abba6a075f6ba1fb97b5a01fb2729dfd63d8c90f7655d6d590afe41',
 'src/momentumbot/research/account_priority_policy.py': '3c0254bcd06425670e7158fb6c2be44edaa6c6f4b74c045798148f9d43e250d7',
 'src/momentumbot/research/campaign_portfolio.py': '5e8b5fb8e42cc739b8337bb544b811e57ccda2df5e7f46ca65ef5a30472149c4',
 'src/momentumbot/research/execution_realism.py': '446509405e3f44e3924c852569c5b06a096f61330552ede850a55c3da5794177',
 'src/momentumbot/research/prospective_daily_account_runtime.py': '45473afe1b947d56fd794ca80a9f72cc7934ca446a161ecb3c7f6ab1e4080d2a',
 'src/momentumbot/research/sealed_historical_account_inputs_v01.py': 'b7a28487807dd5d841a205d6ab74429fb3ed5f0f74b345712c57579e360228dd',
 'src/momentumbot/research/sealed_historical_account_state_producer_v01.py': 'b26456cff4d70e2845a555f166511797141fd4031112d601111bac0e21072f42',
 'src/momentumbot/research/sealed_historical_management_exit_acquisition_v01.py': 'b9e7286a793a164f67ee416152327d6cd7fb98ed7cd38293c4a0dd5ed24663f8',
 'src/momentumbot/research/sealed_historical_management_exit_inputs_v01.py': '5c45ee5f5f05b70e72a070f4ecc35dfbbda56039493b711fd4fe712494ba7d2e',
 'src/momentumbot/research/sealed_historical_management_exit_quote_v01.py': '079200a3d0dededb5a3b775f46330ce3558d98fc8c1b67b10b2ce246cf8549f7',
 'src/momentumbot/research/sealed_historical_management_fee_reconciliation_v01.py': 'edf9f1d449ade225ef871a3976b8e0095b4f8a022080a761d836d62b185b2ab0',
 'src/momentumbot/research/sealed_historical_management_fill_feedback_v01.py': '8ac8b1ea0a8d3ccf57c07d5a3a5ddf0cd82409210dc16506c68400b768f8697d',
 'src/momentumbot/research/sealed_historical_management_projection_v01.py': '1741df5539180eed155c1b2160c7f9fccafdef869939da8330345aa56e548331',
 'src/momentumbot/research/sealed_historical_management_runner_v01.py': '7f352ac748e57f9e3a3c59971a07de152e6063b783bcd4eb6b48723f8f904fc5',
 'src/momentumbot/research/sealed_historical_record_order_v01.py': '407e02fc6fe908e26715fac2799f0debf356e96336b640e795b50287762dec6b',
 'tests/test_sealed_historical_account_inputs_v01.py': '69f0398e4edce650ffbeeca51e7501ae84da6bcabadf258b665ea3b07df58e1b',
 'tests/test_sealed_historical_account_state_producer_v01.py': '72ca6dd1a28f98282a732eaef600a720d16b77be0a7f1165ce28e89120e0cb95',
 'tests/test_sealed_historical_management_fee_reconciliation_v01.py': '31169511e1391d6a2e3df60821017a6f95c788df1b11667ca07b02f9ce8e72da',
 'tests/test_sealed_historical_management_fill_feedback_v01.py': '18e9e649aa501d92fd058e956c5421615006ae7593b4bdc3c731932008113d8e',
 'tests/test_sealed_historical_management_projection_v01.py': 'b34f7fb9224eb0da2b467a7ba22b1056ef9385a1e77abb5626a57b45119dbefb',
 'tests/test_sealed_historical_management_runner_v01.py': 'd81119df620f327174779b0147204b7cad6714475771f18d70d487d8e46b93f5'}
BOUNDARY = dict(parent.BOUNDARY, corporate_action_source_provenance_verified=False,
                mark_is_executable_proceeds=False, continuous_position_order_execution_authorized=False)
NEXT_GATE = "continuous_account_order_scarcity_integration_and_original_source_binding"
INPUT_FIELDS = {"contract_id", "input_scope", "producer_program_content_sha256", "producer_result_content_sha256",
                "previous_close_content_sha256", "next_session_id", "valuation_at_ns", "position_inputs", "content_sha256"}
POSITION_INPUT_FIELDS = {"activation_id", "position_content_sha256", "units_evidence", "tape", "expected_tape_sha256"}
UNITS_FIELDS = {"status", "source_id", "known_at_ns", "from_close_content_sha256", "through_ns"}
adapter = parent.fees.feedback.adapter
money = parent.money


def session_start_ns(slot):
    parent.accounts._validate_slot(slot)
    profile = current_general_2026() if slot["account_key"] == "main_account" else current_small_account_2026()
    start = datetime.combine(date.fromisoformat(slot["trading_date"]), profile.session_start, ZoneInfo("America/New_York"))
    return int(start.timestamp()) * 1_000_000_000


def _integer(value, label):
    if type(value) is not int or value <= 0:
        raise ValueError(label + " must be a positive integer")
    return value


def _units(evidence, close_sha, at):
    if evidence is None:
        return "missing_share_unit_continuity"
    if not isinstance(evidence, dict) or set(evidence) != UNITS_FIELDS:
        raise ValueError("exact share-unit continuity evidence required")
    if not isinstance(evidence["source_id"], str) or not evidence["source_id"].startswith("synthetic-"):
        raise ValueError("synthetic share-unit evidence only")
    if evidence["from_close_content_sha256"] != close_sha or evidence["through_ns"] != at:
        raise ValueError("share-unit evidence must cover the exact preceding close and valuation time")
    _integer(evidence["through_ns"], "unit coverage time")
    known = _integer(evidence["known_at_ns"], "unit evidence knowledge time")
    if known > at:
        return "share_unit_evidence_not_yet_known"
    if evidence["status"] not in {"unchanged_raw_units", "adjustment_required", "unavailable"}:
        raise ValueError("unknown share-unit continuity status")
    return None if evidence["status"] == "unchanged_raw_units" else "share_unit_" + evidence["status"]


def _mark(position, supplied, slot, close_sha, at):
    base = {"activation_id": position["activation_id"], "symbol": position["symbol"],
        "quantity": position["quantity"], "position_content_sha256": canonical_fingerprint(position),
        "valuation_at_ns": at, "basis": "fresh_raw_bid_reference_mark", "mark_price_usd": None,
        "market_value_usd": None, "carried_cost_basis_usd": money(Decimal(position["entry_price"]) * position["quantity"]),
        "opening_unrealized_pnl_usd": None, "quote_source": None, "status_source": None,
        "input_content_sha256": None if supplied is None else canonical_fingerprint(supplied)}
    if supplied is None:
        return seal({**base, "valuation_status": "unavailable", "reason": "missing_position_inputs", **BOUNDARY})
    try:
        if not isinstance(supplied, dict) or set(supplied) != POSITION_INPUT_FIELDS:
            raise ValueError("exact position valuation input fields required")
        if (supplied["activation_id"] != position["activation_id"]
                or supplied["position_content_sha256"] != base["position_content_sha256"]):
            raise ValueError("valuation inputs must bind the exact carried position")
        reason = _units(supplied["units_evidence"], close_sha, at)
        if reason:
            return seal({**base, "valuation_status": "unavailable", "reason": reason, **BOUNDARY})
        tape = supplied["tape"]
        if tape is None:
            if supplied["expected_tape_sha256"] is not None:
                raise ValueError("missing tape cannot have a content pin")
            return seal({**base, "valuation_status": "unavailable", "reason": "missing_quote_status_inputs", **BOUNDARY})
        if not isinstance(tape, dict) or set(tape) != {"quote_request", "quote_records", "status_request", "status_records"}:
            raise ValueError("exact complete valuation tape required")
        parent.fees.feedback._pinned(tape, supplied["expected_tape_sha256"], "complete valuation tape")
        policy = parent.fees.feedback.SCENARIOS[slot["execution_scenario_id"]][0]
        age_ns = policy.max_quote_age_ms * 1_000_000
        for request in (tape["quote_request"], tape["status_request"]):
            if (request["symbols"] != [position["symbol"]] or request["trading_date"] != slot["trading_date"]
                    or request["start_ns"] > at - age_ns or request["end_ns"] <= at):
                raise ValueError("valuation source does not cover the exact symbol, date and freshness interval")
        if tape["quote_request"]["end_ns"] != tape["status_request"]["end_ns"]:
            raise ValueError("valuation quote and status scope ends differ")
        quotes = adapter.quote_events(tape["quote_records"], tape["quote_request"])
        statuses = adapter.status_events(tape["status_records"], tape["status_request"])
        known_quotes = [q for q in quotes if q.ts_recv_ns <= at]
        known_statuses = [s for s in statuses if s.ts_recv_ns <= at]
        quote = known_quotes[-1] if known_quotes else None
        status = known_statuses[-1] if known_statuses else None
        reason = None
        if quote is None:
            reason = "no_quote_known_by_session_start"
        elif at - quote.ts_recv_ns > age_ns:
            reason = "stale_quote"
        elif not quote.usable:
            reason = "latest_book_unusable"
        elif status is None or status.is_trading == "~":
            reason = "trading_status_unknown"
        elif status.is_trading == "N":
            reason = "trading_halted"
        elif any(s.ts_recv_ns == quote.ts_recv_ns for s in known_statuses):
            reason = "same_receive_time_status_quote_ambiguity"
        elif status.ts_recv_ns > quote.ts_recv_ns:
            reason = "quote_precedes_latest_status_transition"
        if reason:
            return seal({**base, "valuation_status": "unavailable", "reason": reason, **BOUNDARY})
        price = Decimal(quote.bid_px_nanos) / Decimal(1_000_000_000)
        value = price * position["quantity"]
        base.update(mark_price_usd=money(price), market_value_usd=money(value),
            opening_unrealized_pnl_usd=money(value - Decimal(base["carried_cost_basis_usd"])),
            quote_source={"source_request_sha256": quote.source_request_sha256, "source_record_index": quote.source_record_index,
                "ts_recv_ns": quote.ts_recv_ns, "sequence": quote.sequence, "bid_px_nanos": quote.bid_px_nanos,
                "bid_size": quote.bid_size},
            status_source={"source_request_sha256": canonical_fingerprint(tape["status_request"]),
                "ts_recv_ns": status.ts_recv_ns, "action": status.action, "is_trading": status.is_trading})
        return seal({**base, "valuation_status": "valued", "reason": "fresh_causal_bid_and_unchanged_raw_share_units", **BOUNDARY})
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        return seal({**base, "valuation_status": "input_failure", "reason": "invalid_valuation_evidence",
            "error_type": type(exc).__name__, "error": str(exc)[:300], **BOUNDARY})


def value_next_session(program, result, inputs, *, expected_program_content_sha256,
                       expected_result_content_sha256, expected_inputs_content_sha256):
    replay = parent.verify_path(program, result, expected_program_content_sha256=expected_program_content_sha256,
                                expected_result_content_sha256=expected_result_content_sha256)
    parent.accounts._sealed(inputs, "valuation input program")
    if inputs["content_sha256"] != expected_inputs_content_sha256:
        raise ValueError("valuation input differs from independent caller commitment")
    if set(inputs) != INPUT_FIELDS or inputs["contract_id"] != CONTRACT_ID or inputs["input_scope"] != "synthetic_component_fixture":
        raise ValueError("exact synthetic valuation input program required; historical activation remains closed")
    if (inputs["producer_program_content_sha256"] != expected_program_content_sha256
            or inputs["producer_result_content_sha256"] != expected_result_content_sha256):
        raise ValueError("valuation input producer commitments differ")
    index = result["session_count"]
    if index == 30:
        raise ValueError("completed registered path has no next session")
    slot = program["slots"][index]
    close = result["sessions"][-1]["close"]
    at = session_start_ns(slot)
    if (inputs["previous_close_content_sha256"] != close["content_sha256"] or inputs["next_session_id"] != slot["session_id"]
            or _integer(inputs["valuation_at_ns"], "valuation time") != at):
        raise ValueError("exact immediately following session and frozen strategy-start time required")
    supplied = inputs["position_inputs"]
    if not isinstance(supplied, list) or any(not isinstance(p, dict) or set(p) != POSITION_INPUT_FIELDS for p in supplied):
        raise ValueError("exact position input inventory required")
    by_id = {p["activation_id"]: p for p in supplied}
    state = close["account_state"]
    ids = {p["activation_id"] for p in state["positions"]}
    if len(by_id) != len(supplied) or not set(by_id) <= ids:
        raise ValueError("duplicate or foreign carried position input")
    with localcontext() as context:
        context.prec = 60
        marks = [_mark(p, by_id.get(p["activation_id"]), slot, close["content_sha256"], at) for p in state["positions"]]
        marks_complete = all(p["valuation_status"] == "valued" for p in marks)
        inventory_complete = not state["pending_orders"] and not any(p["blocks_next_session"] for p in state["unresolved_inputs"])
        market_value = sum((Decimal(p["market_value_usd"]) for p in marks), Decimal(0)) if marks_complete else None
        cost = sum((Decimal(p["carried_cost_basis_usd"]) for p in marks), Decimal(0))
        cash = Decimal(state["buying_power_usd"])
        complete = marks_complete and inventory_complete
        equity = cash + market_value if complete else None
        # Realized P&L and fees are already in cash. A mark never realizes P&L.
        valuation = {"cash_usd": money(cash), "position_cost_basis_usd": money(cost),
            "position_market_value_usd": None if market_value is None else money(market_value),
            "opening_unrealized_pnl_usd": None if market_value is None else money(market_value - cost),
            "equity_usd": None if equity is None else money(equity), "all_position_marks_complete": marks_complete,
            "confirmed_inventory_complete": inventory_complete, "valuation_complete": complete,
            "cumulative_realized_pnl_usd": state["cumulative_realized_pnl_usd"], "cumulative_fees_usd": state["cumulative_fees_usd"]}
        blockers = [{"kind": "position_valuation_unavailable", "activation_id": p["activation_id"], "reason": p["reason"]}
                    for p in marks if p["valuation_status"] != "valued"]
        if not inventory_complete:
            blockers.append({"kind": "unresolved_order_or_account_inputs"})
        if state["positions"]:
            blockers.append({"kind": "continuous_carried_position_execution_not_integrated"})
        if complete and (equity <= 0 or cash <= 0):
            blockers.append({"kind": "nonpositive_equity_or_cash"})
        ledger = None
        if not blockers:
            try:
                ledger = parent._new_day(slot, state).snapshot()
            except ValueError as exc:
                blockers.append({"kind": "frozen_ledger_projection_unavailable", "error": str(exc)[:300]})
        continuation = {"next_session_id": slot["session_id"], "trading_date": slot["trading_date"],
            "source_session_runtime_content_sha256": close["source_runtime_content_sha256"],
            "opening_equity_anchor_usd": valuation["equity_usd"], "cash_usd": state["buying_power_usd"],
            "positions": deepcopy(state["positions"]), "pending_orders": deepcopy(state["pending_orders"]),
            "campaigns": deepcopy(state["campaigns"]), "unresolved_inputs": deepcopy(state["unresolved_inputs"]),
            "opening_marks": deepcopy(marks), "blockers": blockers,
            "can_initialize_flat_session_ledger": not blockers, "flat_session_ledger": ledger,
            "new_entry_or_exit_executed": False, "pending_order_cancelled_by_valuation": False}
    return seal({"contract_id": CONTRACT_ID, "artifact_type": "synthetic_replay_verified_next_session_valuation",
        "producer_program_content_sha256": expected_program_content_sha256, "producer_result_content_sha256": expected_result_content_sha256,
        "valuation_inputs_content_sha256": expected_inputs_content_sha256, "producer_replay_verification": replay,
        "previous_close_content_sha256": close["content_sha256"], "next_slot_content_sha256": slot["content_sha256"],
        "path_id": slot["path_id"], "valuation_at_ns": at, "source_account_state": deepcopy(state),
        "position_valuations": marks, "account_valuation": valuation, "continuation_context": continuation,
        "synthetic_only": True, "historical_execution_count": 0, **BOUNDARY})


def verify_valuation(program, result, inputs, valuation, *, expected_program_content_sha256,
                     expected_result_content_sha256, expected_inputs_content_sha256, expected_valuation_content_sha256):
    parent.accounts._sealed(valuation, "claimed valuation")
    if valuation["content_sha256"] != expected_valuation_content_sha256:
        raise ValueError("valuation result differs from independent caller commitment")
    actual = value_next_session(program, result, inputs, expected_program_content_sha256=expected_program_content_sha256,
        expected_result_content_sha256=expected_result_content_sha256, expected_inputs_content_sha256=expected_inputs_content_sha256)
    require_exact(valuation, actual, "causal account valuation replay")
    return seal({"verification_passed": True, "valuation_content_sha256": valuation["content_sha256"],
        "valuation_inputs_content_sha256": expected_inputs_content_sha256, "synthetic_only": True, **BOUNDARY})


def mechanics():
    return {"producer_authentication": "replay_entire_committed_parent_prefix_before_accepting_its_final_state",
        "cutoff": "immediately_following_registered_session_at_frozen_profile_start_0700_America_New_York",
        "price": "latest_raw_bid_by_receive_time_sequence_original_ordinal_at_or_before_cutoff_no_last_good_fallback",
        "freshness": "unchanged_execution_scenario_max_quote_age_100ms_conservative_50ms_stress_inclusive",
        "status": "known_trading_at_cutoff_fresh_quote_after_last_status_transition_no_equal_receive_time_ambiguity",
        "units": "explicit_causal_unchanged_raw_share_units_required_adjustment_or_unknown_blocks_mark_no_split_guess",
        "equity": "confirmed_cash_plus_marked_remaining_shares_no_realization_or_second_fee_subtraction",
        "basis": "retain_original_cost_basis_and_opening_unrealized_anchor_for_later_daily_account_integration",
        "incomplete": "all_missing_prices_orders_and_input_failures_retained_equity_unknown_if_confirmed_inventory_incomplete",
        "continuation": "preserve_positions_orders_campaigns_and_inputs_exactly_flat_ledger_initialization_only_open_execution_remains_blocked",
        "scope": "synthetic_component_only_no_market_source_or_corporate_action_provenance_authenticated_no_orders_or_provider_calls"}


def expected_contract(root):
    return seal({"schema_version": 1, "contract_id": CONTRACT_ID, "parent_commit_sha": PARENT_COMMIT,
        "parent_tree_sha": PARENT_TREE, "parent_producer_freeze_content_sha256": PARENT_FREEZE,
        "frozen_parent_file_sha256": PARENT_PINS,
        "hypothesis": "causal_next_session_marks_establish_equity_anchors_without_changing_confirmed_account_or_order_state",
        "mechanics": mechanics(), "causal_valuation_mechanics_registered": True,
        "implementation_file_sha256": {p: file_sha(root / p) for p in (MODULE_PATH, SCRIPT_PATH, CHECKER_PATH, TEST_PATH, WORKFLOW_PATH)},
        "next_gate": NEXT_GATE, **BOUNDARY})


def validate_registration(root):
    for path, expected in PARENT_PINS.items():
        parent.accounts.availability._regular(root / path)
        if file_sha(root / path) != expected:
            raise ValueError("valuation parent differs: " + path)
    parent.verify_bundle(root, root / parent.OUTPUT_PATH)
    if frozen(root / parent.OUTPUT_PATH / "freeze-manifest.json")["content_sha256"] != PARENT_FREEZE:
        raise ValueError("producer freeze differs")
    require_exact(frozen(root / CONTRACT_PATH), expected_contract(root), "account valuation registration")
    return seal({"verification_passed": True, "contract_content_sha256": expected_contract(root)["content_sha256"], **BOUNDARY})


def build_bundle(root):
    validate_registration(root)
    plan = frozen(root / parent.fees.feedback.parent.ACCOUNT_PLAN)
    transitions = [{"path_id": p["path_id"], "previous_session_id": s["previous_session_id"], "next_session_id": s["session_id"],
        "next_slot_content_sha256": s["content_sha256"], "valuation_at_ns": session_start_ns(s),
        "position_inputs": "conditional_on_replay_derived_carried_positions_no_source_request_authorized"}
        for p in plan["paths"] for s in p["sessions"][1:]]
    payloads = {
        "valuation-dependencies.json": seal({"contract_id": CONTRACT_ID, "account_plan_content_sha256": plan["content_sha256"],
            "transitions": transitions, "path_count": 12, "session_count": 360, "valuation_transition_count": 348, **BOUNDARY}),
        "valuation-mechanics.json": seal({"contract_id": CONTRACT_ID, "mechanics": mechanics(), **BOUNDARY}),
        "readiness-report.json": seal({"contract_id": CONTRACT_ID, "causal_valuation_mechanics_registered": True,
            "historical_execution_count": 0, "source_tapes_reopened": False, "synthetic_testing_only": True,
            "continuous_execution_integration_complete": False, "next_gate": NEXT_GATE, **BOUNDARY}),
    }
    files = {name: parent.fees.encoded(value) for name, value in payloads.items()}
    files["freeze-manifest.json"] = parent.fees.encoded(seal({"contract_id": CONTRACT_ID, "parent_commit_sha": PARENT_COMMIT,
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
    inventory = parent.accounts.availability._inventory(output)
    if set(inventory) != set(expected):
        raise ValueError("valuation inventory differs")
    for name, raw in expected.items():
        if (output / name).read_bytes() != raw:
            raise ValueError("valuation reconstruction differs: " + name)
    return seal({"verification_passed": True, "contract_id": CONTRACT_ID, "file_inventory": inventory,
        "freeze_content_sha256": frozen(output / "freeze-manifest.json")["content_sha256"], **BOUNDARY})


def write_bundle(root, output):
    _output(root, output)
    if output.exists():
        raise FileExistsError("valuation registration is write-once")
    files = build_bundle(root)
    output.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        with (output / name).open("xb") as handle:
            if handle.write(raw) != len(raw):
                raise OSError("short metadata write")
            handle.flush(); os.fsync(handle.fileno())
    return verify_bundle(root, output)
