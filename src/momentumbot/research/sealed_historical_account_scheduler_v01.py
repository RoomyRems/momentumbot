"""Synthetic chronological account scheduling over immutable execution mechanics.

One account, one active position, one shared fee book and one event clock.
Private simulated entry outcomes cannot affect account state before feedback.
Historical source binding, same-symbol re-entry and carried-window resumption
remain explicit gates; this module is not an activated historical backtest.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal, localcontext
import hashlib
import heapq
import math
import os
from pathlib import Path

import pandas as pd

from momentumbot.models import CandidateQuality, CandidateSnapshot
from momentumbot.research import sealed_historical_account_valuation_v01 as valuation
from momentumbot.research.account_priority_policy import ScarceCapitalOpportunity, order_scarce_capital_opportunities
from momentumbot.research.campaign_portfolio import AccountClass, CampaignPortfolioLedger, EntryRole, PlanEmission
from momentumbot.research.sealed_historical_execution_quote_v01 import canonical_fingerprint, file_sha, frozen, require_exact, seal

parent = valuation.parent
fees, runner, accounts = parent.fees, parent.runner, parent.accounts
feedback = fees.feedback
CONTRACT_ID = "sealed-historical-account-scheduler-v0.1"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
OUTPUT_PATH = f"research/runtime/{CONTRACT_ID}"
MODULE_PATH = "src/momentumbot/research/sealed_historical_account_scheduler_v01.py"
SCRIPT_PATH = "scripts/build_sealed_historical_account_scheduler_v01.py"
CHECKER_PATH = "scripts/verify_sealed_historical_account_scheduler_v01.py"
TEST_PATH = "tests/test_sealed_historical_account_scheduler_v01.py"
WORKFLOW_PATH = ".github/workflows/sealed-historical-account-scheduler-v01.yml"
PARENT_COMMIT = "86733376b10b2a5feb252d174254f4e40fe701ef"
PARENT_TREE = "38c5ab6fe7ddee72d27202675620c890af5c51cf"
PARENT_FREEZE = "22328ab6acb6e94a8941748a7f578d95658c8c7880f4571d71404ed47a835afa"
PARENT_PINS = {
    ".github/workflows/sealed-historical-account-state-producer-v01.yml": "c47cd7e2f814a11dab2b93179eed8d0d389be48a02a5790c410cac0e482dfcf9",
    ".github/workflows/sealed-historical-account-valuation-v01.yml": "d528e040c9900413d274af8b66a5961923bcc9714c8e9102c0df7d380d106f85",
    ".github/workflows/sealed-historical-management-fee-reconciliation-v01.yml": "2782f7618adce2a5d46844dced0ad826586dba2fcb099dfc7c9954c4cfc18cda",
    "docs/research/sealed_historical_account_valuation_v01.md": "81bb4ed86b47c53094cffd46a5056593d98f16f0db989d362b0f4f7c66338913",
    "requirements-sealed-execution-quote-v01.txt": "03f4da335027e4c83bcf38e523c2e11aeaae49778f5bd6caa47e4703348b31b4",
    "research/data-audits/sealed-historical-account-state-producer-v0.1-hosted-verification-34185273453.json": "826eabfe3141bd2f3dfa5abdf78a2ad0384e73b5f03dc030b5e0340db488570a",
    "research/data-audits/sealed-historical-account-state-producer-v0.1-independent-verification.json": "160c9ef1e4bc2eaa9ada69d7da2ea057814539f00524f12e41a53b2f2ad8a269",
    "research/data-audits/sealed-historical-account-valuation-v0.1-hosted-verification-34187472158.json": "b8c665e28458aef851d636cb6415b2791fc60a65928aaa1bd9a9a0dfd2a066c6",
    "research/data-audits/sealed-historical-account-valuation-v0.1-independent-verification.json": "fe35e3d6f93af84cf2c6678a3c3e7450a3b2ad3eb56aa7f7fe1218343590d632",
    "research/data-audits/sealed-historical-management-exit-acquisition-v0.1-independent-verification-34172486163.json": "3d0aea8e76e65eab40df8f309f33153ee80c05e8dc7c076366bc25d31ae9bb33",
    "research/data-audits/sealed-historical-management-exit-acquisition-v0.1-report-34172486163.json": "2765deba3a5559c3ddf75caf83adfc680d720dbfa1c8292ee310cc5be1a89117",
    "research/data-audits/sealed-historical-management-exit-inputs-v0.1-hosted-verification-34176013955.json": "61d2b97c583dfdb8cd02642e49d2ceb6e2663cadb763d1bb795029062536b02a",
    "research/data-audits/sealed-historical-management-exit-inputs-v0.1-independent-verification.json": "54649d3daaa57314dbf7aa4ceb7fb5fe4df2eefa8dc51cf3ca41fa6894e1be6a",
    "research/data-audits/sealed-historical-management-exit-quote-v0.1-xage-reuse.json": "799d8664916eb89f713dec276134400e87434251ff97ea5c0b0a29219983e75b",
    "research/data-audits/sealed-historical-management-fee-reconciliation-v0.1-hosted-verification-34181750634.json": "06840dfc13afe2f4479328e5ce5feabe0556559694a258dcf037767fbd3036a9",
    "research/data-audits/sealed-historical-management-fee-reconciliation-v0.1-independent-verification.json": "17214b643f3d0e2748d718eb0f6e27c3396094ce733af9c2fefa48656c7a7278",
    "research/data-audits/sealed-historical-management-projection-v0.1-independent-verification.json": "ec712e11e5fa66e035507900115dcadac1fdd6ffba8f4f5f55a24532ab2e5f19",
    "research/runtime/sealed-historical-account-management-inputs-v0.1/account-session-input-plan.json": "8ca638578e7957c88f4314e0768a3c379ee0bd1278bd6d8c8e9caa2144f05108",
    "research/runtime/sealed-historical-account-state-producer-v0.1/account-state-dependencies.json": "4431b54c2b568608902a2301e8cffc461c3c5c180fe41a04003b4c34cb770151",
    "research/runtime/sealed-historical-account-state-producer-v0.1/freeze-manifest.json": "72d81edc01d0c6dcb70c31d884276cc61d07ab5a4a22a0255d7cd4ab888a15c5",
    "research/runtime/sealed-historical-account-state-producer-v0.1/producer-mechanics.json": "4f6d713eed6d5452cc9eddc7b824c2c661bfc976c4ea99ca5fbfa5628b7067ed",
    "research/runtime/sealed-historical-account-state-producer-v0.1/readiness-report.json": "a0908d0970d62659ac0689cf054117bc525327538d15caac0df58bd8efe149f2",
    "research/runtime/sealed-historical-account-valuation-v0.1/freeze-manifest.json": "044dcee834155e3b063dc146ed9a154eaad7f19b4b9027f6618f23cccf792b56",
    "research/runtime/sealed-historical-account-valuation-v0.1/readiness-report.json": "b411119554826b5e1ea0a67e116b41d38bb44dac7a5cb3b02a94e997f79446f3",
    "research/runtime/sealed-historical-account-valuation-v0.1/valuation-dependencies.json": "dc1e47b7f60d8e0f3b2f50d6e4cbe85984c6d6c4a99dee713dbaecab0e556c5f",
    "research/runtime/sealed-historical-account-valuation-v0.1/valuation-mechanics.json": "078555d60025c68d22ba80719597876c3ae1ee99ff51bdea7fe756fa0d349796",
    "research/runtime/sealed-historical-management-exit-inputs-v0.1/exit-input-manifest.json": "9733ada8bd2a5db8a1fd21066377d71d71820066c4e1ea3cf52831b37292739e",
    "research/runtime/sealed-historical-management-exit-inputs-v0.1/freeze-manifest.json": "1acad35bfcbf016b26965f03d1759c13dddb0094124f97b71a9fb25bb271fb1c",
    "research/runtime/sealed-historical-management-exit-inputs-v0.1/opportunity-input-index.json": "d58232d30a1b28a3be4a67273835eb8b0eae4a644049945aa213955fe5450ebc",
    "research/runtime/sealed-historical-management-exit-inputs-v0.1/readiness-report.json": "83cd64d28316da750fc8af33cac8859e2981c4b898e0308af10b2839b3311664",
    "research/runtime/sealed-historical-management-exit-inputs-v0.1/source-verification.json": "4557cdd6a1589dbfac64fa75db5a3b80037578146c0fc9510de52411f98770f4",
    "research/runtime/sealed-historical-management-fee-reconciliation-v0.1/fee-session-map.json": "64d49c1f337107f2a3ce1c5fdded4479514d24b80d62a47d216364528fc04c3c",
    "research/runtime/sealed-historical-management-fee-reconciliation-v0.1/freeze-manifest.json": "2ce37076b467ff8e867eb22f48888d9dd1416c52deb145210df4e58d0ebd1d90",
    "research/runtime/sealed-historical-management-fee-reconciliation-v0.1/readiness-report.json": "f759a699e7414eb89a8aced05fd34eb29fe867fb928fd8f6b9e4440e287a5df9",
    "research/runtime/sealed-historical-management-fee-reconciliation-v0.1/reconciliation-mechanics.json": "f581561c5a98140998f68429bea8c56dc036e4a39bda281f80699c6a7f5eeecb",
    "research/runtime/sealed-historical-management-fill-feedback-v0.1/entry-binding-requirements.json": "274a0a384ee9f682711c73aff23d46d561e9f99b08a317729edb700b087e7110",
    "research/runtime/sealed-historical-management-fill-feedback-v0.1/fill-feedback-mechanics.json": "1804798cb77e4ba36938d6d1c3f2201719f039bed2b247784c902b64814317f4",
    "research/runtime/sealed-historical-management-fill-feedback-v0.1/freeze-manifest.json": "6b0480b88442dcb83e75d2bbd790245e99dee5219c603b97b3de129e325c06e8",
    "research/runtime/sealed-historical-management-fill-feedback-v0.1/readiness-report.json": "ae1e94aca391f80b356837d6b48dba62dbb8f852e79610b958707dabfe789d53",
    "research/runtime/sealed-historical-management-projection-v0.1/projection-input-requirements.json": "8b89b1ffd05de277bcff906140b5aeb142a823cce99260d9c967a8d1dc9e931f",
    "research/runtime/sealed-historical-management-runner-v0.1/exit-input-request-plan.json": "562ed42e20c7021eecf384e3a22aed5f5ce25ae15926dd93072a0313d0e6f461",
    "research/strategy/sealed-historical-account-state-producer-v0.1.json": "d893c4b78ac26d996f72d0b3a373535704ebb5cbd8bda04ad4d59901d2800cb3",
    "research/strategy/sealed-historical-account-valuation-v0.1.json": "de39f01dac3d56c750bc5c72a859062930caad26cf6877a890b3047fedd687d5",
    "research/strategy/sealed-historical-management-exit-acquisition-v0.1-execution.json": "60bbd95d1017a3e0e2b3c40060e988f4a457d81b0280b4065c9712a03a1c54e0",
    "research/strategy/sealed-historical-management-exit-acquisition-v0.1.json": "147afc1aa99e33397c1d7f25d6bf17a443c5468d44f820edd40c0d64db989901",
    "research/strategy/sealed-historical-management-exit-inputs-v0.1.json": "e51b3d22feec29408245de3a1bc27406ac9d714203b839a5d5baada3e692c536",
    "research/strategy/sealed-historical-management-fee-reconciliation-v0.1-fee-sources.json": "bcb903f2b8e00dc168d3b5c54a6b435054e9bc08d4e3a57d3388044e29754929",
    "research/strategy/sealed-historical-management-fee-reconciliation-v0.1.json": "afc564cc279c180819bef3b5a0e89e28e0ae2c086263e193f17f7a5d6f9c7bdf",
    "research/strategy/sealed-historical-management-fill-feedback-v0.1.json": "eb41f6fc5112b84e85d014bbc0f990b14b521e76ca3141a23b7044ef54fbc178",
    "research/strategy/sealed-historical-management-projection-v0.1.json": "898bf4d7335a401d7f1962f9de48ee1956d5c2ac96ae9cd4b30d915d933a0a61",
    "scripts/build_sealed_historical_account_state_producer_v01.py": "251c04f24df67b866925668da49588515d5860ab405c5bb507a275d429c0a315",
    "scripts/build_sealed_historical_account_valuation_v01.py": "64ec2a5f47fe6a762270303cebec8b7dc9f6f6fc1eda719369ee126113b7b6cc",
    "scripts/build_sealed_historical_management_fee_reconciliation_v01.py": "1f0b02fb1387c50943c49561387665fce032139b18d66cd54175cb979ec08574",
    "scripts/run_offline_python_v13.py": "fd28ca7e4a27832721a890a1a41af36863a7f13568ca9e85e17c2d5f35e0627d",
    "scripts/verify_sealed_historical_account_state_producer_v01.py": "93d8feb3ff4eb628e7530ad96bf4c97fcc290a48b6fa571b19955b1bf501a659",
    "scripts/verify_sealed_historical_account_valuation_v01.py": "d2aec3399e53776538b0bae6545de1e51ee1b98abbf6d26644a435d354f16c01",
    "scripts/verify_sealed_historical_management_exit_inputs_v01.py": "e7e859f6cb6bce8ffb4fa43915ff17cc8da1a07d9d768aac317fad3388595168",
    "scripts/verify_sealed_historical_management_fee_reconciliation_v01.py": "4ea27b0937c991b339660d626354fe11f209c63e4a1ba5075eacc27312594409",
    "src/momentumbot/models.py": "efa4857a1fa92d24896b750b7df4846abd952fafd966f046054e0aad21325a82",
    "src/momentumbot/research/account_chronological_integration.py": "917257a23abba6a075f6ba1fb97b5a01fb2729dfd63d8c90f7655d6d590afe41",
    "src/momentumbot/research/account_priority_policy.py": "3c0254bcd06425670e7158fb6c2be44edaa6c6f4b74c045798148f9d43e250d7",
    "src/momentumbot/research/campaign_portfolio.py": "5e8b5fb8e42cc739b8337bb544b811e57ccda2df5e7f46ca65ef5a30472149c4",
    "src/momentumbot/research/execution_realism.py": "446509405e3f44e3924c852569c5b06a096f61330552ede850a55c3da5794177",
    "src/momentumbot/research/prospective_daily_account_runtime.py": "45473afe1b947d56fd794ca80a9f72cc7934ca446a161ecb3c7f6ab1e4080d2a",
    "src/momentumbot/research/sealed_historical_account_inputs_v01.py": "b7a28487807dd5d841a205d6ab74429fb3ed5f0f74b345712c57579e360228dd",
    "src/momentumbot/research/sealed_historical_account_state_producer_v01.py": "b26456cff4d70e2845a555f166511797141fd4031112d601111bac0e21072f42",
    "src/momentumbot/research/sealed_historical_account_valuation_v01.py": "a86edead169d1d8fc6352d0cad798b46e67d206968123b508f87c613c2d90351",
    "src/momentumbot/research/sealed_historical_management_exit_acquisition_v01.py": "b9e7286a793a164f67ee416152327d6cd7fb98ed7cd38293c4a0dd5ed24663f8",
    "src/momentumbot/research/sealed_historical_management_exit_inputs_v01.py": "5c45ee5f5f05b70e72a070f4ecc35dfbbda56039493b711fd4fe712494ba7d2e",
    "src/momentumbot/research/sealed_historical_management_exit_quote_v01.py": "079200a3d0dededb5a3b775f46330ce3558d98fc8c1b67b10b2ce246cf8549f7",
    "src/momentumbot/research/sealed_historical_management_fee_reconciliation_v01.py": "edf9f1d449ade225ef871a3976b8e0095b4f8a022080a761d836d62b185b2ab0",
    "src/momentumbot/research/sealed_historical_management_fill_feedback_v01.py": "8ac8b1ea0a8d3ccf57c07d5a3a5ddf0cd82409210dc16506c68400b768f8697d",
    "src/momentumbot/research/sealed_historical_management_projection_v01.py": "1741df5539180eed155c1b2160c7f9fccafdef869939da8330345aa56e548331",
    "src/momentumbot/research/sealed_historical_management_runner_v01.py": "7f352ac748e57f9e3a3c59971a07de152e6063b783bcd4eb6b48723f8f904fc5",
    "src/momentumbot/research/sealed_historical_record_order_v01.py": "407e02fc6fe908e26715fac2799f0debf356e96336b640e795b50287762dec6b",
    "tests/test_sealed_historical_account_inputs_v01.py": "69f0398e4edce650ffbeeca51e7501ae84da6bcabadf258b665ea3b07df58e1b",
    "tests/test_sealed_historical_account_state_producer_v01.py": "72ca6dd1a28f98282a732eaef600a720d16b77be0a7f1165ce28e89120e0cb95",
    "tests/test_sealed_historical_account_valuation_v01.py": "238a6358850a35e0c98bb7ec448ac91a4c5f6e4b2e7b56e8b79dc7b58963b6ce",
    "tests/test_sealed_historical_management_fee_reconciliation_v01.py": "31169511e1391d6a2e3df60821017a6f95c788df1b11667ca07b02f9ce8e72da",
    "tests/test_sealed_historical_management_fill_feedback_v01.py": "18e9e649aa501d92fd058e956c5421615006ae7593b4bdc3c731932008113d8e",
    "tests/test_sealed_historical_management_projection_v01.py": "b34f7fb9224eb0da2b467a7ba22b1056ef9385a1e77abb5626a57b45119dbefb",
    "tests/test_sealed_historical_management_runner_v01.py": "d81119df620f327174779b0147204b7cad6714475771f18d70d487d8e46b93f5"
}
BOUNDARY = dict(valuation.BOUNDARY, historical_execution_count=0,
    same_symbol_reentry_integrated=False, carried_position_execution_resumption_integrated=False)
NEXT_GATE = "same_symbol_reentry_and_carried_window_resumption_then_original_source_binding"
CANDIDATE_FIELDS = {"symbol", "timestamp", "price", "cumulative_volume", "relative_volume", "percent_gain",
    "float_shares", "has_fresh_news", "top_gainer_rank", "quality", "pillars", "reasons"}
PROGRAM_FIELDS = {"contract_id", "artifact_type", "input_scope", "path_id", "slots", "sessions", "content_sha256"}


def _without_labels(value):
    if isinstance(value, dict):
        if accounts._FORBIDDEN.intersection(value):
            raise ValueError("retrospective scheduler input prohibited")
        for child in value.values():
            _without_labels(child)
    elif isinstance(value, list):
        for child in value:
            _without_labels(child)


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
    return ScarceCapitalOpportunity(op["opportunity_id"], accounts._validate_slot(slot)["account_id"], kind,
        op["activation_id"], op["plan_id"], pd.Timestamp(op["decision_ts_ns"], unit="ns", tz="UTC"), snapshot)


class _ChronologicalDay(fees.ReconciledAccountDay):
    def observe_trade(self, item):
        candidate = deepcopy(self)
        if (candidate._ledger.flatten_required and candidate._engine is not None
                and candidate._engine._latched not in ("initial_stop", "breakeven_stop")):
            # Known account guards request the frozen one terminal attempt on
            # the next eligible SIP print. Existing reservations and the one-
            # attempt ceiling are still enforced by the untouched engine.
            candidate._engine._latched = "account_risk_flatten"
        result = fees.ReconciledAccountDay.observe_trade(candidate, item)
        self.__dict__ = candidate.__dict__
        return result


def _day(slot, opening):
    original = parent._new_day(slot, opening)
    ledger = CampaignPortfolioLedger(date.fromisoformat(slot["trading_date"]), original.ledger_copy().constraints)
    return _ChronologicalDay(pre_session_ledger=ledger,
        expected_pre_session_ledger_sha256=canonical_fingerprint(ledger.runtime_artifact()),
        path_id=slot["path_id"], scenario_id=slot["execution_scenario_id"])


def _validate_entry_context(*, window, slot, source_decision, expected_context_sha256,
                            pre_entry_ledger, expected_pre_ledger_sha256, tape, expected_tape_sha256):
    """Exact frozen binder preflight, factored before future execution simulation."""
    feedback._pinned({"window": window, "slot": slot, "source_decision": source_decision}, expected_context_sha256, "entry context")
    feedback.parent.validate_window(window)
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
    if any(e["event_type"] == "entry_accepted" and e["symbol"] == op["symbol"] for e in ledger.events):
        raise ValueError("multiple-entry or add campaign is unsupported")
    return ledger, stop, op


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
        stop_price=stop, role=EntryRole.STARTER)
    if quantity < 1:
        return None
    order_id = "entry-" + canonical_fingerprint({"contract_id": feedback.CONTRACT_ID, "path_id": slot["path_id"],
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


class _Session:
    """Incremental stream merge; failed trailing evidence retains known state."""
    def __init__(self, slot, source, opening):
        self.slot, self.source, self.opening = slot, source, deepcopy(opening)
        self.account = _day(slot, opening)
        self.heap, self.serial, self.events, self.dispositions = [], 0, [], []
        self.specs, self.cursors, self.quote_times, self.rank = {}, {}, {}, {}
        self.pending, self.active = None, None
        self.stage, self.failure, self.seen = "source_registration", None, set()

    def push(self, at, phase, rank, kind, oid, value=None):
        self.serial += 1
        heapq.heappush(self.heap, (at, phase, rank, self.serial, kind, oid, value))

    def event(self, at, phase, kind, **values):
        self.events.append(seal({"sequence": len(self.events),
            "previous_event_sha256": self.events[-1]["content_sha256"] if self.events else None,
            "at_ns": at, "phase": phase, "event_type": kind, **deepcopy(values)}))

    def view(self):
        snapshot = self.account.snapshot()
        return {"cash_usd": parent.money(snapshot["exact_account"]["remaining_buying_power"]),
            "confirmed_quantity": sum(p["quantity"] for p in snapshot["exact_account"]["positions"].values()),
            "capacity_reserved": self.pending is not None or self.active is not None,
            "account_locked": snapshot["ledger"]["account"]["locked"]}

    def initialize(self):
        refs = {r["opportunity_id"]: r for r in self.slot["opportunity_inputs"]}
        ranked = []
        for item in self.source["opportunities"]:
            if not isinstance(item, dict) or set(item) != {"candidate", "position"}:
                raise ValueError("exact candidate and position program required")
            spec = item["position"]
            if set(spec) != parent.POSITION_FIELDS or set(spec["entry_input"]) != parent.ENTRY_FIELDS:
                raise ValueError("exact position source fields required")
            window = spec["entry_input"]["window"]
            feedback.parent.validate_window(window)
            op = window["opportunity"]
            oid = op["opportunity_id"]
            if oid in self.specs or oid not in refs or refs[oid]["input_status"] != "available":
                raise ValueError("unique original available opportunity required")
            if not op["symbol"].startswith("SYNTHETIC"):
                raise ValueError("scheduler accepts synthetic source fixtures only")
            if op["decision_ts_ns"] < valuation.session_start_ns(self.slot) or op["trading_date"] != self.slot["trading_date"]:
                raise ValueError("opportunity must follow the frozen session start")
            ranked.append(_candidate(item["candidate"], op, self.slot))
            self.specs[oid] = spec
        for ordinal, item in enumerate(order_scarce_capital_opportunities(ranked)):
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

    def push_cursor(self, oid, cursor):
        if cursor.value is not None:
            at, phase = cursor.key()
            self.push(at, 0 if phase == 0 else 2, self.rank[oid], "market", oid, cursor.resource)

    def decision(self, at, oid):
        before = self.view()
        self.seen.add(oid)
        spec = self.specs[oid]
        symbol = spec["entry_input"]["window"]["opportunity"]["symbol"]
        if before["capacity_reserved"]:
            disposition = "blocked_capacity"
        elif before["account_locked"]:
            disposition = "blocked_account_lock"
        elif any(e["event_type"] == "entry_accepted" and e["symbol"] == symbol for e in self.account.snapshot()["ledger"]["events"]):
            disposition = "unsupported_same_symbol_reentry"
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

    def settle(self, at, oid, phase=3):
        if self.pending is not None and self.pending["oid"] == oid:
            pending, outcome = self.pending, self.pending["outcome"]
            if not pending["applied"] and outcome.filled_quantity and outcome.fill_ts_ns <= at:
                if outcome.fill_ts_ns != at:
                    raise ValueError("entry feedback tick did not expose fill at its actual clock")
                candidate = deepcopy(self.account)
                try:
                    candidate.start_position(entry_arguments=pending["arguments"],
                        expected_account_content_sha256=candidate.snapshot()["content_sha256"])
                except (ValueError, KeyError, TypeError, OverflowError) as exc:
                    pending["unreconciled_execution_feedback"] = {"known_at_ns": at,
                        "execution": feedback._execution_payload(outcome), "error_type": type(exc).__name__}
                    raise
                self.account, self.active, pending["applied"] = candidate, oid, True
                self.event(at, phase, "entry_fill_confirmed", opportunity_id=oid,
                    journal_index=len(self.account.snapshot()["journal"]) - 1, account_after=self.view())
            if at >= pending["public"]["cancel_ack_ts_ns"]:
                self.pending = None
                self.event(at, phase, "entry_cancel_acknowledged", opportunity_id=oid,
                    order_id=pending["public"]["order_id"], confirmed_quantity=outcome.filled_quantity,
                    cancelled_quantity=pending["public"]["quantity"] - outcome.filled_quantity)
        if self.active != oid:
            return
        before = len(self.account.snapshot()["journal"])
        snapshot = self.account.settle(at)
        for index in range(before, len(snapshot["journal"])):
            self.event(at, phase, "sell_fill_confirmed", opportunity_id=oid, journal_index=index, account_after=self.view())
        engine = snapshot["management"]
        if (not engine["remaining_quantity"] and not engine["pending_order"] and engine["outstanding_intent"] is None
                and self.pending is None and (engine["entry"]["entry_cancel_ack_ns"], 2) <= (engine["clock_ns"], engine["clock_phase"])):
            receipt = self.account.release_position()
            self.active = None
            self.event(at, phase, "capacity_released", opportunity_id=oid, receipt=receipt, account_after=self.view())

    def market(self, at, phase, oid, resource):
        cursor = self.cursors[(oid, resource)]
        if self.active == oid:
            if resource == "raw_sip_1m_bars":
                self.account.observe_bar(cursor.value)
            else:
                intent = self.account.observe_trade(cursor.value)
                if intent is not None:
                    self.stage = "executable_exit_evidence"
                    spec = self.specs[oid]
                    order = self.account.submit_intent(intent, tape=spec["exit_tape"], expected_tape_sha256=spec["expected_exit_tape_sha256"])
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

    def run(self):
        try:
            self.initialize()
            while self.heap:
                at, phase, _rank, _serial, kind, oid, value = heapq.heappop(self.heap)
                self.stage = kind
                if kind == "decision":
                    self.decision(at, oid)
                elif kind == "market":
                    self.market(at, phase, oid, value)
                else:
                    self.settle(at, oid, phase)
        except (ValueError, KeyError, TypeError, OverflowError, OSError) as exc:
            self.failure = {"kind": "chronological_input_failure", "stage": self.stage,
                "error_type": type(exc).__name__, "error": str(exc)[:300], "blocks_next_session": True}
        return self

    def pending_public(self):
        if self.pending is None or self.pending["applied"]:
            return None
        return {"kind": "unconfirmed_entry_order", "opportunity_id": self.pending["oid"],
            **deepcopy(self.pending["public"]), "confirmed_filled_quantity": 0,
            "unreconciled_execution_feedback": deepcopy(self.pending["unreconciled_execution_feedback"])}


def _session(slot, source, opening, previous_sha):
    if set(source) != {"session_id", "opportunities"} or source["session_id"] != slot["session_id"] or not isinstance(source["opportunities"], list):
        raise ValueError("exact chronological session program required")
    blocked, scheduler, failures = not parent._ready(opening), None, []
    if not blocked:
        try:
            scheduler = _Session(slot, source, opening).run()
        except ValueError as exc:
            blocked = True
            failures.append({"kind": "opening_ledger_projection_unavailable", "error": str(exc)[:300], "blocks_next_session": True})
    seen = {} if scheduler is None else {d["opportunity_id"]: d["disposition"] for d in scheduler.dispositions}
    dispositions = [{**deepcopy(r), "disposition": "unavailable_input" if r["input_status"] == "unavailable"
        else seen.get(r["opportunity_id"], "blocked_prior_state" if blocked else "unprocessed_available_input")}
        for r in slot["opportunity_inputs"]]
    gaps = [{"kind": d["disposition"], "opportunity_id": d["opportunity_id"],
        "availability_content_sha256": d["availability_content_sha256"], "reason": d["reason"],
        "blocks_next_session": d["disposition"] != "unavailable_input"} for d in dispositions
        if d["disposition"] in {"unavailable_input", "unprocessed_available_input", "blocked_prior_state", "unsupported_same_symbol_reentry"}]
    snapshot = None if scheduler is None else scheduler.account.snapshot()
    entry_pending = None if scheduler is None else scheduler.pending_public()
    if scheduler is not None and scheduler.failure is not None:
        failures.append(scheduler.failure)
    if blocked:
        state = deepcopy(opening)
        state["unresolved_inputs"] += gaps + failures + [{"kind": "preceding_state_blocks_execution", "blocks_next_session": True,
            "previous_close_content_sha256": previous_sha}]
        gross = net = charged = Decimal(0)
    else:
        positions, pending, extra = parent._collections(snapshot)
        if entry_pending is not None:
            pending.append(entry_pending)
        exact = snapshot["exact_account"]
        gross, net, charged = Decimal(exact["gross_realized_pnl"]), Decimal(exact["net_realized_pnl"]), Decimal(snapshot["fee_book"]["fees"]["total_charged"])
        state = {"equity_usd": None if positions or pending else parent.money(Decimal(opening["equity_usd"]) + net),
            "buying_power_usd": parent.money(exact["remaining_buying_power"]),
            "cumulative_realized_pnl_usd": parent.money(Decimal(opening["cumulative_realized_pnl_usd"]) + net),
            "cumulative_fees_usd": parent.money(Decimal(opening["cumulative_fees_usd"]) + charged),
            "positions": positions, "pending_orders": pending,
            "campaigns": deepcopy(opening["campaigns"]) + deepcopy(snapshot["ledger"]["campaigns"]),
            "unresolved_inputs": deepcopy(opening["unresolved_inputs"]) + gaps + failures + extra}
    parent.validate_state(state)
    runtime = seal({"contract_id": CONTRACT_ID, "session_id": slot["session_id"], "path_id": slot["path_id"],
        "source_slot_content_sha256": slot["content_sha256"], "session_program_sha256": canonical_fingerprint(source),
        "opening_account_state_sha256": canonical_fingerprint(opening), "blocked_before_execution": blocked,
        "events": [] if scheduler is None else scheduler.events, "opportunity_dispositions": dispositions,
        "reconciliation_snapshot": snapshot, "unconfirmed_entry_order": entry_pending,
        "complete_streams_verified": scheduler is not None and scheduler.failure is None,
        "failure": None if scheduler is None else scheduler.failure,
        "session_gross_realized_pnl_usd": parent.money(gross), "session_net_realized_pnl_usd": parent.money(net),
        "session_fees_usd": parent.money(charged), "synthetic_intraday_scheduler_executed": not blocked, **BOUNDARY})
    close = seal({"contract_id": CONTRACT_ID, "session_id": slot["session_id"], "path_id": slot["path_id"],
        "trading_date": slot["trading_date"], "session_index": slot["session_index"], "seed_applied": slot["seed_applied"],
        "source_slot_content_sha256": slot["content_sha256"], "previous_close_content_sha256": previous_sha,
        "source_runtime_content_sha256": runtime["content_sha256"], "account_state": state,
        "next_session_flat_cash_execution_ready": parent._ready(state), **BOUNDARY})
    return {"runtime": runtime, "close": close}


def replay_path(program, *, expected_program_content_sha256):
    accounts._sealed(program, "scheduler source program")
    if program["content_sha256"] != expected_program_content_sha256:
        raise ValueError("source differs from independent caller commitment")
    if (set(program) != PROGRAM_FIELDS or program["contract_id"] != CONTRACT_ID
            or program["artifact_type"] != "chronological_account_source_program"
            or program["input_scope"] != "synthetic_component_fixture"):
        raise ValueError("exact synthetic scheduler program required; no historical activation")
    _without_labels(program)
    slots, sessions = program["slots"], program["sessions"]
    if not isinstance(slots, list) or len(slots) != 30 or not isinstance(sessions, list) or not 1 <= len(sessions) <= 30:
        raise ValueError("complete 30-slot catalog and nonempty chronological prefix required")
    for index, slot in enumerate(slots):
        parent._slot(slot)
        if slot["session_index"] != index or slot["path_id"] != program["path_id"]:
            raise ValueError("same path and exact chronological slot index required")
    initial = accounts.account_state_input(slots[0])["account_state"]
    opening, previous, results = initial, None, []
    with localcontext() as context:
        context.prec = 60
        for slot, source in zip(slots, sessions):
            result = _session(slot, source, opening, previous)
            results.append(result)
            opening, previous = deepcopy(result["close"]["account_state"]), result["close"]["content_sha256"]
    return seal({"contract_id": CONTRACT_ID, "artifact_type": "synthetic_chronological_account_path",
        "program_content_sha256": program["content_sha256"], "slot_catalog_sha256": canonical_fingerprint(slots),
        "path_id": program["path_id"], "seed_content_sha256": slots[0]["seed_content_sha256"], "initial_account_state": initial,
        "seed_application_count": 1, "session_count": len(results), "sessions": results,
        "last_close_content_sha256": previous, "synthetic_only": True, **BOUNDARY})


def verify_path(program, result, *, expected_program_content_sha256, expected_result_content_sha256):
    accounts._sealed(result, "scheduler result")
    if result["content_sha256"] != expected_result_content_sha256:
        raise ValueError("result differs from independent caller commitment")
    require_exact(result, replay_path(program, expected_program_content_sha256=expected_program_content_sha256), "scheduler replay result")
    return seal({"verification_passed": True, "program_content_sha256": expected_program_content_sha256,
        "result_content_sha256": expected_result_content_sha256, "synthetic_scheduler_replayed": True, **BOUNDARY})


def continue_valued_session(program, result, inputs, session, *, expected_program_content_sha256,
                           expected_result_content_sha256, expected_inputs_content_sha256, expected_session_sha256):
    """Verify the frozen parent's full prefix and valuation before handoff.

    An open position's mark is retained, but cannot extend its original execution
    window. Unresolved orders and imported-window resumption remain blocked.
    """
    feedback._pinned(session, expected_session_sha256, "continuation session")
    _without_labels(session)
    marked = valuation.value_next_session(program, result, inputs, expected_program_content_sha256=expected_program_content_sha256,
        expected_result_content_sha256=expected_result_content_sha256, expected_inputs_content_sha256=expected_inputs_content_sha256)
    slot = program["slots"][result["session_count"]]
    with localcontext() as context:
        context.prec = 60
        continued = _session(slot, session, marked["source_account_state"], inputs["previous_close_content_sha256"])
    return seal({"contract_id": CONTRACT_ID, "valuation": marked, "session": continued,
        "source_session_sha256": expected_session_sha256, "seed_application_count": 0, **BOUNDARY})


def mechanics():
    return {"clock": ["completed_bar", "ranked_entry_decision", "SIP_print", "fill_and_cancel_feedback", "original_window_boundary"],
        "scarcity": "frozen_activation_candidate_rank_for_exact_time_collisions_account_local_one_reserved_position",
        "entry_reservation": "from_submission_through_cancel_ack_even_if_unfilled_future_outcome_private_until_feedback",
        "release": "confirmed_flat_no_pending_sells_or_entry_cancels_before_new_capacity",
        "overlap": "release_after_actual_ack_not_after_entire_old_window_but_validate_all_trailing_stream_bytes",
        "risk_flatten": "known_net_guard_latches_one_frozen_terminal_attempt_on_next_eligible_print_no_retry_or_fabricated_fill",
        "capital": "shared_fee_book_per_day_exact_flat_cash_carry_once_only_seeds",
        "reentry": "explicit_unsupported_dependency_not_silent_strategy_rejection",
        "overnight": "preserve_open_positions_orders_and_valuation_no_extension_of_frozen_execution_window",
        "failure": "retain_confirmed_state_pending_orders_and_missing_inputs_block_later_execution"}


def expected_contract(root):
    return seal({"schema_version": 1, "contract_id": CONTRACT_ID, "parent_commit_sha": PARENT_COMMIT,
        "parent_tree_sha": PARENT_TREE, "parent_valuation_freeze_content_sha256": PARENT_FREEZE,
        "frozen_parent_file_sha256": PARENT_PINS, "mechanics": mechanics(),
        "hypothesis": "one_causal_account_clock_preserves_confirmed_state_and_scarcity_across_overlapping_position_windows",
        "implementation_file_sha256": {p: file_sha(root / p) for p in (MODULE_PATH, SCRIPT_PATH, CHECKER_PATH, TEST_PATH, WORKFLOW_PATH)},
        "next_gate": NEXT_GATE, **BOUNDARY})


def validate_registration(root):
    for path, sha in PARENT_PINS.items():
        accounts.availability._regular(root / path)
        if file_sha(root / path) != sha:
            raise ValueError("scheduler parent differs: " + path)
    valuation.verify_bundle(root, root / valuation.OUTPUT_PATH)
    if frozen(root / valuation.OUTPUT_PATH / "freeze-manifest.json")["content_sha256"] != PARENT_FREEZE:
        raise ValueError("valuation freeze differs")
    require_exact(frozen(root / CONTRACT_PATH), expected_contract(root), "account scheduler registration")
    return seal({"verification_passed": True, "contract_content_sha256": expected_contract(root)["content_sha256"], **BOUNDARY})


def build_bundle(root):
    validate_registration(root)
    original = frozen(root / parent.OUTPUT_PATH / "account-state-dependencies.json")
    payloads = {"scheduler-dependencies.json": seal({"contract_id": CONTRACT_ID, "account_plan_content_sha256": original["account_plan_content_sha256"],
        "slots": original["slots"], "path_count": original["path_count"], "session_count": original["session_count"],
        "seed_applications": original["seed_applications"], "previous_close_dependencies": original["previous_close_dependencies"], **BOUNDARY}),
        "scheduler-mechanics.json": seal({"contract_id": CONTRACT_ID, "mechanics": mechanics(), **BOUNDARY}),
        "readiness-report.json": seal({"contract_id": CONTRACT_ID, "synthetic_intraday_scheduler_registered": True,
            "source_tapes_reopened": False, "next_gate": NEXT_GATE, **BOUNDARY})}
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
        raise ValueError("scheduler inventory differs")
    for name, raw in expected.items():
        if (output / name).read_bytes() != raw:
            raise ValueError("scheduler reconstruction differs: " + name)
    return seal({"verification_passed": True, "contract_id": CONTRACT_ID, "file_inventory": inventory,
        "freeze_content_sha256": frozen(output / "freeze-manifest.json")["content_sha256"], **BOUNDARY})


def write_bundle(root, output):
    _output(root, output)
    if output.exists():
        raise FileExistsError("scheduler registration is write-once")
    files = build_bundle(root)
    output.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        with (output / name).open("xb") as handle:
            if handle.write(raw) != len(raw):
                raise OSError("short metadata write")
            handle.flush()
            os.fsync(handle.fileno())
    return verify_bundle(root, output)
