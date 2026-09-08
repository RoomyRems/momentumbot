"""Historical fee assumptions and confirmed-fill account reconciliation.

Offline research mechanics only. A caller-pinned empty session ledger is not an
authenticated historical opening account. This child keeps the frozen strategy,
execution simulator and ledger acceptance rules; cash and guard comparisons use
an exact Decimal journal. One management position can be active at a time.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal, localcontext
import hashlib
import json
import os
from pathlib import Path

import pandas as pd

from momentumbot.research import execution_realism as execution
from momentumbot.research import sealed_historical_management_exit_inputs_v01 as parent
from momentumbot.research import sealed_historical_management_fill_feedback_v01 as feedback
from momentumbot.research.campaign_portfolio import CampaignPortfolioLedger, EntryFill, EntryRole, ExitFill, PlanEmission
from momentumbot.research.sealed_historical_execution_quote_v01 import canonical_fingerprint, file_sha, frozen, require_exact, seal

CONTRACT_ID = "sealed-historical-management-fee-reconciliation-v0.1"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
OUTPUT_PATH = f"research/runtime/{CONTRACT_ID}"
MODULE_PATH = "src/momentumbot/research/sealed_historical_management_fee_reconciliation_v01.py"
SCRIPT_PATH = "scripts/build_sealed_historical_management_fee_reconciliation_v01.py"
CHECKER_PATH = "scripts/verify_sealed_historical_management_fee_reconciliation_v01.py"
TEST_PATH = "tests/test_sealed_historical_management_fee_reconciliation_v01.py"
WORKFLOW_PATH = ".github/workflows/sealed-historical-management-fee-reconciliation-v01.yml"
SOURCES_PATH = f"research/strategy/{CONTRACT_ID}-fee-sources.json"
PARENT_COMMIT = "1cd6f71fa36710c357c30dd3c3b5cda118c1a742"
PARENT_TREE = "819577e15c1666ab8a8265bbb7d87aca5d394bc7"
PARENT_FREEZE = "a7f7a6e864e012fb2623872a7325c57fcc9c0ccbf8cd880597839c8b44965b67"
PARENT_PINS = {'requirements-sealed-execution-quote-v01.txt': '03f4da335027e4c83bcf38e523c2e11aeaae49778f5bd6caa47e4703348b31b4',
 'research/data-audits/sealed-historical-management-exit-acquisition-v0.1-independent-verification-34172486163.json': '3d0aea8e76e65eab40df8f309f33153ee80c05e8dc7c076366bc25d31ae9bb33',
 'research/data-audits/sealed-historical-management-exit-acquisition-v0.1-report-34172486163.json': '2765deba3a5559c3ddf75caf83adfc680d720dbfa1c8292ee310cc5be1a89117',
 'research/data-audits/sealed-historical-management-exit-inputs-v0.1-hosted-verification-34176013955.json': '61d2b97c583dfdb8cd02642e49d2ceb6e2663cadb763d1bb795029062536b02a',
 'research/data-audits/sealed-historical-management-exit-inputs-v0.1-independent-verification.json': '54649d3daaa57314dbf7aa4ceb7fb5fe4df2eefa8dc51cf3ca41fa6894e1be6a',
 'research/data-audits/sealed-historical-management-exit-quote-v0.1-xage-reuse.json': '799d8664916eb89f713dec276134400e87434251ff97ea5c0b0a29219983e75b',
 'research/data-audits/sealed-historical-management-projection-v0.1-independent-verification.json': 'ec712e11e5fa66e035507900115dcadac1fdd6ffba8f4f5f55a24532ab2e5f19',
 'research/runtime/sealed-historical-account-management-inputs-v0.1/account-session-input-plan.json': '8ca638578e7957c88f4314e0768a3c379ee0bd1278bd6d8c8e9caa2144f05108',
 'research/runtime/sealed-historical-management-exit-inputs-v0.1/exit-input-manifest.json': '9733ada8bd2a5db8a1fd21066377d71d71820066c4e1ea3cf52831b37292739e',
 'research/runtime/sealed-historical-management-exit-inputs-v0.1/freeze-manifest.json': '1acad35bfcbf016b26965f03d1759c13dddb0094124f97b71a9fb25bb271fb1c',
 'research/runtime/sealed-historical-management-exit-inputs-v0.1/opportunity-input-index.json': 'd58232d30a1b28a3be4a67273835eb8b0eae4a644049945aa213955fe5450ebc',
 'research/runtime/sealed-historical-management-exit-inputs-v0.1/readiness-report.json': '83cd64d28316da750fc8af33cac8859e2981c4b898e0308af10b2839b3311664',
 'research/runtime/sealed-historical-management-exit-inputs-v0.1/source-verification.json': '4557cdd6a1589dbfac64fa75db5a3b80037578146c0fc9510de52411f98770f4',
 'research/runtime/sealed-historical-management-fill-feedback-v0.1/entry-binding-requirements.json': '274a0a384ee9f682711c73aff23d46d561e9f99b08a317729edb700b087e7110',
 'research/runtime/sealed-historical-management-fill-feedback-v0.1/fill-feedback-mechanics.json': '1804798cb77e4ba36938d6d1c3f2201719f039bed2b247784c902b64814317f4',
 'research/runtime/sealed-historical-management-fill-feedback-v0.1/freeze-manifest.json': '6b0480b88442dcb83e75d2bbd790245e99dee5219c603b97b3de129e325c06e8',
 'research/runtime/sealed-historical-management-fill-feedback-v0.1/readiness-report.json': 'ae1e94aca391f80b356837d6b48dba62dbb8f852e79610b958707dabfe789d53',
 'research/runtime/sealed-historical-management-projection-v0.1/projection-input-requirements.json': '8b89b1ffd05de277bcff906140b5aeb142a823cce99260d9c967a8d1dc9e931f',
 'research/runtime/sealed-historical-management-runner-v0.1/exit-input-request-plan.json': '562ed42e20c7021eecf384e3a22aed5f5ce25ae15926dd93072a0313d0e6f461',
 'research/strategy/sealed-historical-management-exit-acquisition-v0.1-execution.json': '60bbd95d1017a3e0e2b3c40060e988f4a457d81b0280b4065c9712a03a1c54e0',
 'research/strategy/sealed-historical-management-exit-acquisition-v0.1.json': '147afc1aa99e33397c1d7f25d6bf17a443c5468d44f820edd40c0d64db989901',
 'research/strategy/sealed-historical-management-exit-inputs-v0.1.json': 'e51b3d22feec29408245de3a1bc27406ac9d714203b839a5d5baada3e692c536',
 'research/strategy/sealed-historical-management-fill-feedback-v0.1.json': 'eb41f6fc5112b84e85d014bbc0f990b14b521e76ca3141a23b7044ef54fbc178',
 'research/strategy/sealed-historical-management-projection-v0.1.json': '898bf4d7335a401d7f1962f9de48ee1956d5c2ac96ae9cd4b30d915d933a0a61',
 'scripts/run_offline_python_v13.py': 'fd28ca7e4a27832721a890a1a41af36863a7f13568ca9e85e17c2d5f35e0627d',
 'scripts/verify_sealed_historical_management_exit_inputs_v01.py': 'e7e859f6cb6bce8ffb4fa43915ff17cc8da1a07d9d768aac317fad3388595168',
 'src/momentumbot/research/account_chronological_integration.py': '917257a23abba6a075f6ba1fb97b5a01fb2729dfd63d8c90f7655d6d590afe41',
 'src/momentumbot/research/account_priority_policy.py': '3c0254bcd06425670e7158fb6c2be44edaa6c6f4b74c045798148f9d43e250d7',
 'src/momentumbot/research/campaign_portfolio.py': '5e8b5fb8e42cc739b8337bb544b811e57ccda2df5e7f46ca65ef5a30472149c4',
 'src/momentumbot/research/execution_realism.py': '446509405e3f44e3924c852569c5b06a096f61330552ede850a55c3da5794177',
 'src/momentumbot/research/prospective_daily_account_runtime.py': '45473afe1b947d56fd794ca80a9f72cc7934ca446a161ecb3c7f6ab1e4080d2a',
 'src/momentumbot/research/sealed_historical_account_inputs_v01.py': 'b7a28487807dd5d841a205d6ab74429fb3ed5f0f74b345712c57579e360228dd',
 'src/momentumbot/research/sealed_historical_management_exit_acquisition_v01.py': 'b9e7286a793a164f67ee416152327d6cd7fb98ed7cd38293c4a0dd5ed24663f8',
 'src/momentumbot/research/sealed_historical_management_exit_inputs_v01.py': '5c45ee5f5f05b70e72a070f4ecc35dfbbda56039493b711fd4fe712494ba7d2e',
 'src/momentumbot/research/sealed_historical_management_exit_quote_v01.py': '079200a3d0dededb5a3b775f46330ce3558d98fc8c1b67b10b2ce246cf8549f7',
 'src/momentumbot/research/sealed_historical_management_fill_feedback_v01.py': '8ac8b1ea0a8d3ccf57c07d5a3a5ddf0cd82409210dc16506c68400b768f8697d',
 'src/momentumbot/research/sealed_historical_management_projection_v01.py': '1741df5539180eed155c1b2160c7f9fccafdef869939da8330345aa56e548331',
 'src/momentumbot/research/sealed_historical_management_runner_v01.py': '7f352ac748e57f9e3a3c59971a07de152e6063b783bcd4eb6b48723f8f904fc5',
 'src/momentumbot/research/sealed_historical_record_order_v01.py': '407e02fc6fe908e26715fac2799f0debf356e96336b640e795b50287762dec6b',
 'tests/test_sealed_historical_management_fill_feedback_v01.py': '18e9e649aa501d92fd058e956c5421615006ae7593b4bdc3c731932008113d8e',
 'tests/test_sealed_historical_management_projection_v01.py': 'b34f7fb9224eb0da2b467a7ba22b1056ef9385a1e77abb5626a57b45119dbefb'}
NEXT_GATE = "authenticated_account_state_producer_then_causal_valuation_and_continuous_account_order_integration"
BOUNDARY = {
    "provider_calls": 0, "retrospective_inputs_read": False,
    "historical_runtime_authorized": False, "historical_producer_authenticated": False,
    "financial_metrics_eligible": False, "account_close_evidence": False,
    "broker_statement_equivalence_verified": False, "policy_promotion_eligible": False,
}
ZERO = Decimal("0")
FEE_TYPES = ("sec", "taf", "cat", "commission")


def historical_schedule(trading_date: date) -> execution.EquityFeeSchedule:
    """Explicit modeled rates, restricted to this panel's historical interval.

    July CAT reduction follows the May 29 announced schedule, assumed effective
    as proposed. Later official confirmation is verification-only provenance.
    Broker pass-through, rounding and zero commissions remain research assumptions.
    """
    if type(trading_date) is not date or not date(2025, 5, 30) <= trading_date <= date(2025, 7, 17):
        raise ValueError("date outside registered 2025 fee interval")
    return execution.EquityFeeSchedule(
        sec_sale_rate_per_dollar=Decimal("0"),
        taf_sale_rate_per_share=Decimal("0.000166"),
        taf_per_trade_cap=Decimal("8.30"),
        cat_rate_per_executed_share=Decimal("0.000035" if trading_date < date(2025, 7, 1) else "0.000022"),
        commission_rate_per_dollar=Decimal("0"),
    )


def _decimal(value, label, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError(label + " requires an exact decimal string or integer")
    try:
        result = Decimal(value)
    except Exception as exc:
        raise ValueError(label + " is not a decimal") from exc
    if not result.is_finite() or (positive and result <= 0):
        raise ValueError(label + " must be finite" + (" and positive" if positive else ""))
    # Frozen source prices have at most nine fractional digits. Bound arithmetic
    # rather than allowing hostile exponents to consume memory or lose precision.
    if result.as_tuple().exponent < -9 or abs(result) > Decimal("1e15"):
        raise ValueError(label + " exceeds supported exact arithmetic bounds")
    return result


def _timestamp(at, trading_date):
    if type(at) is not int or at < 1:
        raise ValueError("positive integer nanosecond timestamp required")
    stamp = pd.Timestamp(at, unit="ns", tz="UTC")
    if stamp.tz_convert("America/New_York").date() != trading_date:
        raise ValueError("fill timestamp differs from account trading date")
    return stamp


class DailyFeeAccumulator:
    """One persistent account-day fee book; one positive fill per frozen order.

    This low-level calculator does not authenticate executions. Account changes
    below are exclusively driven by the frozen engine's confirmed receipts.
    """

    def __init__(self, *, account_id: str, path_id: str, scenario_id: str, trading_date: date):
        if any(not isinstance(v, str) or not v.strip() for v in (account_id, path_id)):
            raise ValueError("nonempty account and path required")
        if scenario_id not in feedback.SCENARIOS:
            raise ValueError("unregistered execution scenario")
        self._schedule = historical_schedule(trading_date)
        self._identity = {"account_id": account_id, "path_id": path_id, "scenario_id": scenario_id,
                          "trading_date": trading_date.isoformat()}
        self._day = trading_date
        self._trades = []

    def snapshot(self):
        with localcontext() as ctx:
            ctx.prec = 60
            fees = execution.aggregate_daily_equity_fees([
                execution.ExecutedEquityTrade(execution.OrderSide(t["side"]), t["quantity"], Decimal(t["price"]))
                for t in self._trades], schedule=self._schedule)
        return seal({"contract_id": CONTRACT_ID, "identity": deepcopy(self._identity),
                     "trades": deepcopy(self._trades), "fees": fees.as_strings(),
                     "customer_fee_assumptions": True, **BOUNDARY})

    def add(self, *, fill_id: str, order_id: str, side: str, quantity: int, price: str, timestamp_ns: int):
        _timestamp(timestamp_ns, self._day)
        if any(not isinstance(v, str) or not v.strip() for v in (fill_id, order_id)):
            raise ValueError("nonempty fill and order identities required")
        if side not in ("buy", "sell") or type(quantity) is not int or not 0 < quantity <= 10**9:
            raise ValueError("positive whole-share buy or sell required")
        exact_price = _decimal(price, "execution price", positive=True)
        if any(t["fill_id"] == fill_id or t["order_id"] == order_id for t in self._trades):
            raise ValueError("duplicate fill or second positive fill for frozen one-fill order")
        if self._trades and timestamp_ns < self._trades[-1]["timestamp_ns"]:
            raise ValueError("fee book clock reversed")
        before = self.snapshot()["fees"]
        trade = {"fill_id": fill_id, "order_id": order_id, "side": side, "quantity": quantity,
                 "price": str(exact_price), "timestamp_ns": timestamp_ns}
        candidate = deepcopy(self)
        candidate._trades.append(trade)
        after = candidate.snapshot()["fees"]
        with localcontext() as ctx:
            ctx.prec = 60
            delta = {name: str(Decimal(after[name + "_charged"]) - Decimal(before[name + "_charged"])) for name in FEE_TYPES}
            delta["total"] = str(sum((Decimal(delta[name]) for name in FEE_TYPES), ZERO))
        self._trades = candidate._trades
        return {"trade": deepcopy(trade), "incremental_charge": delta, "cumulative_fees": after}


class _NetLedger(CampaignPortfolioLedger):
    """Child-only hook: evaluate frozen limits against exact post-fill net values.

    The frozen base calls guards midway through apply_exit_fill. Install the
    atomic final journal values before that call so gross intermediate gains
    cannot inflate the high-water mark or permanently trip a giveback lock.
    """

    def install(self, cash, net, high_water, campaign_net):
        self._exact_financials = (cash, net, high_water, deepcopy(campaign_net))

    def _apply_session_guards(self, at):
        cash, net, high, campaign_net = self._exact_financials
        self.remaining_buying_power, self.realized_pnl, self.high_water_pnl = map(float, (cash, net, high))
        for activation_id, value in campaign_net.items():
            self.campaigns[activation_id].realized_pnl = float(value)
        if not self.locked:
            if net <= -Decimal(str(self.constraints.max_daily_loss_dollars)):
                self._lock("daily_max_loss")
            elif high > 0 and net <= high * (1 - Decimal(str(self.constraints.giveback_fraction))):
                self._lock("profit_giveback")
            if self.locked:
                self.events.append({"sequence": len(self.events) + 1, "event_type": "account_locked",
                    "at": at.isoformat(), "reason": self.lock_reason, "flatten_required": self.open_campaign_count > 0})
        self.flatten_required = self.locked and self.open_campaign_count > 0


class ReconciledAccountDay:
    """Transactional single-active-position reducer with a persistent daily book.

    Construct once from an empty, externally pinned session ledger. Successive
    flat positions retain fees, cash and account locks. Concurrent positions,
    imported history, overnight lots, new seeds and authenticated historical
    activation require the later account producer/integration child.
    """

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

    def ledger_copy(self):
        """Isolated net ledger for the next entry's independently pinned binding."""
        return deepcopy(self._ledger)

    def snapshot(self):
        return seal({"contract_id": CONTRACT_ID, "artifact_type": "synthetic_verified_account_reconciliation_state",
            "opening_ledger_sha256": self._opening_sha, "identity": deepcopy(self._book._identity),
            "clock": list(self._clock) if self._clock is not None else None,
            "ledger": deepcopy(self._ledger.runtime_artifact()), "fee_book": self._book.snapshot(),
            "exact_account": {"remaining_buying_power": str(self._cash), "gross_realized_pnl": str(self._gross),
                "net_realized_pnl": str(self._net), "net_high_water_pnl": str(self._high),
                "cash_shortfall": str(max(ZERO, -self._cash)),
                "positions": deepcopy(self._positions)},
            "journal": deepcopy(self._journal), "completed_positions": deepcopy(self._completed),
            "management": None if self._engine is None else self._engine.snapshot(),
            "single_active_position_only": True, "account_risk_flatten_execution_integrated": False,
            "next_session_valuation_registered": False, **BOUNDARY})

    def start_position(self, *, entry_arguments: dict, expected_account_content_sha256: str):
        if expected_account_content_sha256 != self.snapshot()["content_sha256"]:
            raise ValueError("current account state differs from independent caller pin")
        if self._engine is not None:
            raise ValueError("one active position; release confirmed flat position first")
        candidate = deepcopy(self)
        with localcontext() as ctx:
            ctx.prec = 60
            result = candidate._start(entry_arguments)
        self.__dict__ = candidate.__dict__
        return deepcopy(result)

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
        engine = feedback.ManagementFillFeedback(**args)
        entry = engine.snapshot()["entry"]
        if entry["account_id"] != identity["account_id"]:
            raise ValueError("entry account differs")
        _, reference, _ = feedback._quote_window(args["window"], decision_ns, args["tape"], args["expected_tape_sha256"])
        self._ledger.record_plan_emission(PlanEmission(entry["activation_id"], entry["plan_id"], entry["symbol"],
                                                       pd.Timestamp(decision_ns, unit="ns", tz="UTC")))
        accepted = self._ledger.apply_entry_fill(EntryFill(fill_id=entry["fill_id"], activation_id=entry["activation_id"],
            plan_id=entry["plan_id"], symbol=entry["symbol"], filled_at=_timestamp(entry["fill_time_ns"], self._book._day),
            quantity=entry["quantity"], reference_price=float(reference.ask_price), fill_price=float(entry["fill_price"]),
            stop_price=entry["initial_stop_price"], role=EntryRole.STARTER, execution_approved=True))
        if not accepted.accepted or canonical_fingerprint(self._ledger.runtime_artifact()) != entry["post_ledger_content_sha256"]:
            raise ValueError("reconstructed entry differs from frozen accepted ledger")
        self._engine, self._applied = engine, 0
        self._clock = (entry["fill_time_ns"], -1)
        self._record(entry, side="buy", entry=entry)
        self._ledger._apply_session_guards(_timestamp(entry["fill_time_ns"], self._book._day))
        self._check()
        return self._journal[-1]

    def _record(self, receipt, *, side, entry):
        """Only called with internally recomputed entry or causal engine receipt."""
        at, quantity = receipt["fill_time_ns"], receipt["quantity"]
        if at > self._clock[0] or (side == "sell" and at == self._clock[0] and self._clock[1] != 2):
            raise ValueError("fill is not yet known at account clock")
        activation = entry["activation_id"]
        fill_id = entry["fill_id"] if side == "buy" else "sell-fill-" + receipt["content_sha256"]
        order_id = entry["order"]["order_id"] if side == "buy" else receipt["order_id"]
        fee = self._book.add(fill_id=fill_id, order_id=order_id, side=side, quantity=quantity,
                             price=receipt["fill_price"], timestamp_ns=at)
        charge = Decimal(fee["incremental_charge"]["total"])
        price = Decimal(receipt["fill_price"])
        with localcontext() as ctx:
            ctx.prec = 60
            if side == "buy":
                if activation in self._positions:
                    raise ValueError("one entry per activation supported")
                self._positions[activation] = {"symbol": entry["symbol"], "entry_fill_id": entry["fill_id"],
                    "entry_price": str(price), "quantity": quantity, "gross_realized_pnl": "0", "fees_charged": "0"}
                gross_delta = ZERO
                self._cash -= price * quantity + charge
            else:
                position = self._positions[activation]
                if receipt["entry_fill_id"] != position["entry_fill_id"] or quantity > position["quantity"]:
                    raise ValueError("sell receipt exceeds bound entry shares")
                gross_delta = (price - Decimal(position["entry_price"])) * quantity
                position["quantity"] -= quantity
                self._cash += price * quantity - charge
                self._gross += gross_delta
            position = self._positions[activation]
            position["gross_realized_pnl"] = str(Decimal(position["gross_realized_pnl"]) + gross_delta)
            position["fees_charged"] = str(Decimal(position["fees_charged"]) + charge)
            self._net = self._gross - Decimal(fee["cumulative_fees"]["total_charged"])
            self._high = max(self._high, self._net)
            campaign_net = {a: Decimal(p["gross_realized_pnl"]) - Decimal(p["fees_charged"]) for a, p in self._positions.items()}
            self._ledger.install(self._cash, self._net, self._high, campaign_net)
        journal = seal({"sequence": len(self._journal), "previous_event_sha256": self._journal[-1]["content_sha256"] if self._journal else None,
            "activation_id": activation, "execution_evidence": deepcopy(receipt), "fee_application": fee,
            "known_at_ns": self._clock[0], "clock_phase": self._clock[1], "gross_realized_delta": str(gross_delta),
            "remaining_quantity": position["quantity"], "cash_after": str(self._cash),
            "gross_realized_after": str(self._gross), "net_realized_after": str(self._net), "net_high_water_after": str(self._high)})
        self._journal.append(journal)
        return fill_id

    def _sync(self):
        state = self._engine.snapshot()
        self._clock = (state["clock_ns"], state["clock_phase"])
        entry = state["entry"]
        for receipt in state["fills"][self._applied:]:
            fill_id = self._record(receipt, side="sell", entry=entry)
            accepted = self._ledger.apply_exit_fill(ExitFill(fill_id=fill_id, activation_id=entry["activation_id"],
                symbol=entry["symbol"], filled_at=_timestamp(receipt["fill_time_ns"], self._book._day),
                quantity=receipt["quantity"], fill_price=float(receipt["fill_price"])))
            if not accepted.accepted:
                raise ValueError("confirmed sell rejected by frozen ledger: " + ",".join(accepted.reasons))
            self._applied += 1
        campaign = self._ledger.campaigns[entry["activation_id"]]
        if state["breakeven_active"] and any(lot.stop_price != state["active_stop_price"] for lot in campaign.lots):
            at = _timestamp(state["fills"][-1]["fill_time_ns"], self._book._day)
            for lot in campaign.lots:
                lot.stop_price = state["active_stop_price"]
            self._ledger._append_event("confirmed_target_stop_updated", at, campaign,
                stop_price=state["active_stop_price"], target_filled_quantity=state["target_filled_quantity"],
                management_state_content_sha256=state["content_sha256"])
        self._check()

    def _check(self):
        if (self._cash != Decimal(str(self._ledger.remaining_buying_power))
                or self._net != Decimal(str(self._ledger.realized_pnl))
                or self._high != Decimal(str(self._ledger.high_water_pnl))):
            # A float cannot represent arbitrarily large or sub-nanodollar
            # journal values. Reject that unsupported projection atomically.
            raise ValueError("exact journal cannot be projected into frozen ledger without decimal loss")
        for activation, position in self._positions.items():
            if self._ledger.campaigns[activation].quantity != position["quantity"]:
                raise ValueError("ledger and journal share conservation differs")
            campaign_net = Decimal(position["gross_realized_pnl"]) - Decimal(position["fees_charged"])
            if campaign_net != Decimal(str(self._ledger.campaigns[activation].realized_pnl)):
                raise ValueError("ledger and journal campaign accounting differs")
        if self._engine is not None:
            state = self._engine.snapshot()
            if self._positions[state["entry"]["activation_id"]]["quantity"] != state["remaining_quantity"]:
                raise ValueError("ledger and management shares differ")

    def _transition(self, method, *args, **kwargs):
        if self._engine is None:
            raise ValueError("active bound management position required")
        candidate = deepcopy(self)
        # Frozen methods only read supplied market/tape evidence. Keep the large
        # complete source payload read-only rather than making a second copy.
        result = getattr(candidate._engine, method)(*args, **kwargs)
        with localcontext() as ctx:
            ctx.prec = 60
            candidate._sync()
        self.__dict__ = candidate.__dict__
        return deepcopy(result)

    def observe_bar(self, item):
        return self._transition("observe_bar", item)

    def observe_trade(self, item):
        return self._transition("observe_trade", item)

    def submit_intent(self, intent, *, tape, expected_tape_sha256):
        return self._transition("submit_intent", intent, tape=tape, expected_tape_sha256=expected_tape_sha256)

    def settle(self, timestamp_ns):
        self._transition("settle", timestamp_ns)
        return self.snapshot()

    def release_position(self):
        if self._engine is None:
            raise ValueError("no active position")
        state = self._engine.snapshot()
        if state["remaining_quantity"] or state["pending_order"] or state["outstanding_intent"] is not None:
            raise ValueError("confirmed flat shares and all cancel acknowledgements required")
        if self._clock[0] < state["entry"]["entry_cancel_ack_ns"]:
            raise ValueError("entry cancel acknowledgement is still pending")
        candidate = deepcopy(self)
        receipt = seal({"entry_content_sha256": state["entry"]["content_sha256"],
            "management_content_sha256": state["content_sha256"], "account_before_release_content_sha256": self.snapshot()["content_sha256"],
            "released_at_ns": self._clock[0], "confirmed_position_shares_closed": True, **BOUNDARY})
        candidate._completed.append(receipt)
        candidate._engine = None
        candidate._applied = 0
        self.__dict__ = candidate.__dict__
        return deepcopy(receipt)


def mechanics():
    return {
        "fees": "explicit_2025_model_no_2026_defaults_no_broker_statement_equivalence",
        "rounding": "cumulative_account_day_each_type_ceiling_cent_charge_only_increment_since_previous_fill",
        "taf_cap": "each_sell_order_one_confirmed_positive_fill_cap_before_daily_sum",
        "fee_timing": "accrued_as_cash_and_net_realized_expense_when_fill_is_confirmed_no_second_EOD_debit",
        "fee_attribution": "daily_rounding_increment_charged_to_current_campaign_in_causal_order",
        "entry": "recompute_frozen_binding_and_identical_post_entry_ledger_before_fee_debit",
        "sells": "only_internal_causal_confirmed_receipts_actual_quantity_and_price_never_intents_or_canceled_shares",
        "net_guards": "exact_decimal_post_fill_net_high_water_and_frozen_loss_giveback_limits_atomic_with_fill",
        "stop_risk": "remaining_lots_stop_changes_only_after_entire_target_tranche_confirmed",
        "atomicity": "copy_validate_reconcile_commit_on_success_all_failures_preserve_prior_state",
        "continuation": "one_empty_session_ledger_once_one_active_position_persistent_fee_book_across_flat_releases",
        "scope": "no_overlapping_positions_imported_history_overnight_valuation_historical_authentication_or_automatic_risk_flatten_orders",
    }


def encoded(value):
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False).encode() + b"\n"


def expected_contract(root):
    return seal({"schema_version": 1, "contract_id": CONTRACT_ID,
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "parent_exit_inputs_freeze_content_sha256": PARENT_FREEZE, "frozen_parent_file_sha256": PARENT_PINS,
        "hypothesis": "causal_confirmed_fills_reconcile_cash_shares_daily_fees_and_net_risk_guards_without_changing_frozen_policy",
        "fee_sources_content_sha256": frozen(root / SOURCES_PATH)["content_sha256"],
        "mechanics": mechanics(), "historical_fee_model_registered": True,
        "implementation_file_sha256": {p: file_sha(root / p) for p in (MODULE_PATH, SCRIPT_PATH, CHECKER_PATH, TEST_PATH, WORKFLOW_PATH)},
        "next_gate": NEXT_GATE, **BOUNDARY})


def validate_registration(root):
    for path, sha in PARENT_PINS.items():
        feedback.accounts.availability._regular(root / path)
        if file_sha(root / path) != sha:
            raise ValueError("fee reconciliation parent differs: " + path)
    if frozen(root / parent.SNAPSHOT_PATH / "freeze-manifest.json")["content_sha256"] != PARENT_FREEZE:
        raise ValueError("exit inputs freeze differs")
    sources = frozen(root / SOURCES_PATH)
    if file_sha(root / SOURCES_PATH) != FEE_SOURCES_SHA256:
        raise ValueError("fee source evidence differs")
    require_exact(frozen(root / CONTRACT_PATH), expected_contract(root), "fee reconciliation registration")
    return seal({"verification_passed": True, "contract_content_sha256": expected_contract(root)["content_sha256"],
                 "fee_sources_content_sha256": sources["content_sha256"], **BOUNDARY})


FEE_SOURCES_SHA256 = "bcb903f2b8e00dc168d3b5c54a6b435054e9bc08d4e3a57d3388044e29754929"


def build_bundle(root):
    validate_registration(root)
    plan = frozen(root / feedback.parent.ACCOUNT_PLAN)
    paths = [{"path_id": p["path_id"], "sessions": [{"session_id": s["session_id"], "trading_date": s["trading_date"],
        "session_input_content_sha256": s["content_sha256"], "fee_period": "2025-1" if s["trading_date"] < "2025-07-01" else "2025-2"}
        for s in p["sessions"]]} for p in plan["paths"]]
    payloads = {
        "fee-session-map.json": seal({"contract_id": CONTRACT_ID, "account_plan_content_sha256": plan["content_sha256"],
            "paths": paths, "fee_sources_content_sha256": frozen(root / SOURCES_PATH)["content_sha256"], **BOUNDARY}),
        "reconciliation-mechanics.json": seal({"contract_id": CONTRACT_ID, "mechanics": mechanics(), **BOUNDARY}),
        "readiness-report.json": seal({"contract_id": CONTRACT_ID, "historical_fee_model_registered": True,
            "confirmed_sell_ledger_mechanics_registered": True, "synthetic_testing_only": True,
            "historical_account_producer_registered": False, "continuous_account_order_integration_registered": False,
            "next_session_valuation_registered": False, "historical_execution_count": 0, "source_tapes_reopened": False,
            "next_gate": NEXT_GATE, **BOUNDARY}),
    }
    files = {name: encoded(value) for name, value in payloads.items()}
    files["freeze-manifest.json"] = encoded(seal({"contract_id": CONTRACT_ID, "parent_commit_sha": PARENT_COMMIT,
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
    inventory = feedback.accounts.availability._inventory(output)
    if set(inventory) != set(expected):
        raise ValueError("fee reconciliation inventory differs")
    for name, raw in expected.items():
        if (output / name).read_bytes() != raw:
            raise ValueError("fee reconciliation reconstruction differs: " + name)
    return seal({"verification_passed": True, "contract_id": CONTRACT_ID, "file_inventory": inventory,
                 "freeze_content_sha256": frozen(output / "freeze-manifest.json")["content_sha256"], **BOUNDARY})


def write_bundle(root, output):
    _output(root, output)
    if output.exists():
        raise FileExistsError("fee reconciliation registration is write-once")
    files = build_bundle(root)
    output.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        with (output / name).open("xb") as handle:
            if handle.write(raw) != len(raw):
                raise OSError("short metadata write")
            handle.flush()
            os.fsync(handle.fileno())
    return verify_bundle(root, output)
