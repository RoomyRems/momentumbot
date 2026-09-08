"""Synthetic campaign re-entry and replay-verified intraday continuation.

Frozen scheduler child: two accepted entries per activation, fresh management
per fill, persistent campaign accounting, and causal checkpoints. No overnight
window extension, historical source activation or retrospective inputs.
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

from momentumbot.research import sealed_historical_account_scheduler_v01 as scheduler
from momentumbot.research.campaign_portfolio import CampaignPortfolioLedger, EntryRole, PlanEmission, EntryFill
from momentumbot.research.sealed_historical_execution_quote_v01 import canonical_fingerprint, file_sha, frozen, require_exact, seal

parent, valuation = scheduler.parent, scheduler.valuation
fees, runner, accounts, feedback = scheduler.fees, scheduler.runner, scheduler.accounts, scheduler.feedback
ZERO = Decimal(0)
CONTRACT_ID = "sealed-historical-account-continuity-v0.1"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
OUTPUT_PATH = f"research/runtime/{CONTRACT_ID}"
MODULE_PATH = "src/momentumbot/research/sealed_historical_account_continuity_v01.py"
SCRIPT_PATH = "scripts/build_sealed_historical_account_continuity_v01.py"
CHECKER_PATH = "scripts/verify_sealed_historical_account_continuity_v01.py"
TEST_PATH = "tests/test_sealed_historical_account_continuity_v01.py"
WORKFLOW_PATH = ".github/workflows/sealed-historical-account-continuity-v01.yml"
PARENT_COMMIT = "6933ff419afb034f9509eaa0898c3467571e32d8"
PARENT_TREE = "506c78abbbd7d3cc1db32ace9baa9d63f2d08edd"
PARENT_FREEZE = "f49742c8262409b4cab7378a49b509d91d9aaee5c959175fcfc841a71ef06ff9"
PARENT_PINS = {
    ".github/workflows/sealed-historical-account-scheduler-v01.yml": "dc8c43799e3cf4faa18444d4b5fd40f3b041c1fb94ebdd1f9746ba4c9ca5b428",
    ".github/workflows/sealed-historical-account-state-producer-v01.yml": "c47cd7e2f814a11dab2b93179eed8d0d389be48a02a5790c410cac0e482dfcf9",
    ".github/workflows/sealed-historical-account-valuation-v01.yml": "d528e040c9900413d274af8b66a5961923bcc9714c8e9102c0df7d380d106f85",
    ".github/workflows/sealed-historical-management-fee-reconciliation-v01.yml": "2782f7618adce2a5d46844dced0ad826586dba2fcb099dfc7c9954c4cfc18cda",
    "docs/research/sealed_historical_account_scheduler_v01.md": "d81b2cca120bb7fb8a4c8e489f8d2e2dcf41b395bbdd7cd5d9d10409f9eb2e75",
    "docs/research/sealed_historical_account_valuation_v01.md": "81bb4ed86b47c53094cffd46a5056593d98f16f0db989d362b0f4f7c66338913",
    "requirements-sealed-execution-quote-v01.txt": "03f4da335027e4c83bcf38e523c2e11aeaae49778f5bd6caa47e4703348b31b4",
    "research/data-audits/sealed-historical-account-scheduler-v0.1-hosted-verification-34190813109.json": "e44ef62ccb4dd71ecf791aadc61e98afbce2e734a812845cb7eab04d770b267a",
    "research/data-audits/sealed-historical-account-scheduler-v0.1-independent-verification.json": "c0c73c103cd1ba24dff44fb52a425a352907bbdb4fdd69fa6a21bbee3408f653",
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
    "research/runtime/sealed-historical-account-scheduler-v0.1/freeze-manifest.json": "2861e35d3e96cf83cb621c24bff091813ffff45df46dad5759ff39e250e4f543",
    "research/runtime/sealed-historical-account-scheduler-v0.1/readiness-report.json": "1be8a52a339716b72fad69a52ea3e740dcda048b19a3a638c37ec41f07bc0c72",
    "research/runtime/sealed-historical-account-scheduler-v0.1/scheduler-dependencies.json": "98ac0d85df100174df7b00777d9f4dd7e32975e29e6fe2d4d29a4d635d00cbfe",
    "research/runtime/sealed-historical-account-scheduler-v0.1/scheduler-mechanics.json": "b4c52382088e335df1e78d41fa8192bae9afe77878361efbecc0c31b016fb902",
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
    "research/strategy/sealed-historical-account-scheduler-v0.1.json": "0cf0a5591e0449eeb433eccf3e3102402f39e500776beec0773d8a8c2b69459c",
    "research/strategy/sealed-historical-account-state-producer-v0.1.json": "d893c4b78ac26d996f72d0b3a373535704ebb5cbd8bda04ad4d59901d2800cb3",
    "research/strategy/sealed-historical-account-valuation-v0.1.json": "de39f01dac3d56c750bc5c72a859062930caad26cf6877a890b3047fedd687d5",
    "research/strategy/sealed-historical-management-exit-acquisition-v0.1-execution.json": "60bbd95d1017a3e0e2b3c40060e988f4a457d81b0280b4065c9712a03a1c54e0",
    "research/strategy/sealed-historical-management-exit-acquisition-v0.1.json": "147afc1aa99e33397c1d7f25d6bf17a443c5468d44f820edd40c0d64db989901",
    "research/strategy/sealed-historical-management-exit-inputs-v0.1.json": "e51b3d22feec29408245de3a1bc27406ac9d714203b839a5d5baada3e692c536",
    "research/strategy/sealed-historical-management-fee-reconciliation-v0.1-fee-sources.json": "bcb903f2b8e00dc168d3b5c54a6b435054e9bc08d4e3a57d3388044e29754929",
    "research/strategy/sealed-historical-management-fee-reconciliation-v0.1.json": "afc564cc279c180819bef3b5a0e89e28e0ae2c086263e193f17f7a5d6f9c7bdf",
    "research/strategy/sealed-historical-management-fill-feedback-v0.1.json": "eb41f6fc5112b84e85d014bbc0f990b14b521e76ca3141a23b7044ef54fbc178",
    "research/strategy/sealed-historical-management-projection-v0.1.json": "898bf4d7335a401d7f1962f9de48ee1956d5c2ac96ae9cd4b30d915d933a0a61",
    "scripts/build_sealed_historical_account_scheduler_v01.py": "dd11a75ebf87ace2795cd7bfeb6324636228947e4ec571a74da9444db9197391",
    "scripts/build_sealed_historical_account_state_producer_v01.py": "251c04f24df67b866925668da49588515d5860ab405c5bb507a275d429c0a315",
    "scripts/build_sealed_historical_account_valuation_v01.py": "64ec2a5f47fe6a762270303cebec8b7dc9f6f6fc1eda719369ee126113b7b6cc",
    "scripts/build_sealed_historical_management_fee_reconciliation_v01.py": "1f0b02fb1387c50943c49561387665fce032139b18d66cd54175cb979ec08574",
    "scripts/run_offline_python_v13.py": "fd28ca7e4a27832721a890a1a41af36863a7f13568ca9e85e17c2d5f35e0627d",
    "scripts/verify_sealed_historical_account_scheduler_v01.py": "57298784d552a5c48e4ad885d405eddec2c6f3e7ea128427f6d6574e20895f3d",
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
    "src/momentumbot/research/sealed_historical_account_scheduler_v01.py": "55dd5d4f1e91240bbc33506e5d7535e56d2c643a62389e80f1b8e075cca29cdc",
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
    "tests/test_sealed_historical_account_scheduler_v01.py": "21a2c671bdf1248a069346249a4e15ece19d81dd54230509f70d45679d20a5a7",
    "tests/test_sealed_historical_account_state_producer_v01.py": "72ca6dd1a28f98282a732eaef600a720d16b77be0a7f1165ce28e89120e0cb95",
    "tests/test_sealed_historical_account_valuation_v01.py": "238a6358850a35e0c98bb7ec448ac91a4c5f6e4b2e7b56e8b79dc7b58963b6ce",
    "tests/test_sealed_historical_management_fee_reconciliation_v01.py": "31169511e1391d6a2e3df60821017a6f95c788df1b11667ca07b02f9ce8e72da",
    "tests/test_sealed_historical_management_fill_feedback_v01.py": "18e9e649aa501d92fd058e956c5421615006ae7593b4bdc3c731932008113d8e",
    "tests/test_sealed_historical_management_projection_v01.py": "b34f7fb9224eb0da2b467a7ba22b1056ef9385a1e77abb5626a57b45119dbefb",
    "tests/test_sealed_historical_management_runner_v01.py": "d81119df620f327174779b0147204b7cad6714475771f18d70d487d8e46b93f5"
}
BOUNDARY = dict(scheduler.BOUNDARY, same_symbol_reentry_integrated=True,
    original_window_checkpoint_resumption_verified=True,
    carried_position_execution_resumption_integrated=False,
    overnight_execution_window_extension_authorized=False)
NEXT_GATE = "original_source_binding_and_explicit_expired_window_carry_dependencies_before_historical_activation"
PROGRAM_FIELDS = scheduler.PROGRAM_FIELDS
_without_labels = scheduler._without_labels


def _entry_role(ledger, op):
    campaign = ledger.campaigns.get(op["activation_id"])
    if campaign is None or not campaign.entry_fill_count:
        return EntryRole.STARTER
    if campaign.quantity:
        raise ValueError("re-entry requires confirmed flat campaign; adds unsupported")
    return EntryRole.REENTRY


def _entry_block(ledger, op):
    campaign = ledger.campaigns.get(op["activation_id"])
    if campaign is not None and campaign.symbol != op["symbol"]:
        raise ValueError("one activation cannot identify multiple symbols")
    if op["symbol"] in ledger.halted_symbols:
        return "blocked_symbol_halt"
    if campaign is not None:
        if campaign.terminal:
            return "blocked_campaign_terminal"
        if campaign.entry_fill_count >= ledger.constraints.max_entries_per_campaign:
            return "blocked_campaign_entry_limit"
        if campaign.entry_fill_count and not ledger.constraints.allow_reentry:
            return "blocked_reentry_disabled"
    return None


def _validate_entry_context(*, window, slot, source_decision, expected_context_sha256,
                            pre_entry_ledger, expected_pre_ledger_sha256, tape, expected_tape_sha256):
    """Frozen context preflight with the isolated flat re-entry eligibility delta."""
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


class _Management(feedback.ManagementFillFeedback):
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


class _AccountDay(scheduler._ChronologicalDay):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._released_liquidity = set()

    def snapshot(self):
        value = super().snapshot()
        value.pop("content_sha256")
        liquidity = self._released_liquidity | (set() if self._engine is None else self._engine._used_liquidity)
        value.update(contract_id=CONTRACT_ID, consumed_sell_liquidity=[list(k) for k in sorted(liquidity)], **BOUNDARY)
        return seal(value)

    def release_position(self):
        used = set() if self._engine is None else set(self._engine._used_liquidity)
        receipt = super().release_position()
        self._released_liquidity.update(used)
        return receipt

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
                old = self._positions.get(activation)
                if old is not None and (old["quantity"] or old["symbol"] != entry["symbol"]):
                    raise ValueError("re-entry requires the same confirmed flat campaign")
                self._positions[activation] = {"symbol": entry["symbol"], "entry_fill_id": entry["fill_id"],
                    "entry_price": str(price), "quantity": quantity,
                    "gross_realized_pnl": "0" if old is None else old["gross_realized_pnl"],
                    "fees_charged": "0" if old is None else old["fees_charged"],
                    "entry_fill_ids": ([] if old is None else old["entry_fill_ids"]) + [entry["fill_id"]]}
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


def _day(slot, opening):
    original = parent._new_day(slot, opening)
    ledger = CampaignPortfolioLedger(date.fromisoformat(slot["trading_date"]), original.ledger_copy().constraints)
    return _AccountDay(pre_session_ledger=ledger,
        expected_pre_session_ledger_sha256=canonical_fingerprint(ledger.runtime_artifact()),
        path_id=slot["path_id"], scenario_id=slot["execution_scenario_id"])


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


class _Session(scheduler._Session):
    def __init__(self, slot, source, opening):
        self.slot, self.source, self.opening = slot, source, deepcopy(opening)
        self.account = _day(slot, opening)
        self.heap, self.serial, self.events, self.dispositions = [], 0, [], []
        self.specs, self.cursors, self.quote_times, self.rank = {}, {}, {}, {}
        self.pending, self.active = None, None
        self.stage, self.failure, self.seen = "source_registration", None, set()
        self.initialized = False
        self.processed = {}
        self.through_ns = None

    def decision(self, at, oid):
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

    def market(self, at, phase, oid, resource):
        value = deepcopy(self.cursors[(oid, resource)].value)
        super().market(at, phase, oid, resource)
        self.processed.setdefault((oid, resource), []).append(value)

    def run_until(self, through_ns=None):
        if self.failure is not None:
            return self
        try:
            if not self.initialized:
                self.initialized = True
                self.initialize()
            while self.heap and (through_ns is None or self.heap[0][0] <= through_ns):
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
        self.through_ns = through_ns
        return self

    def run(self):
        return self.run_until()

    def continuation_state(self):
        """Only processed source progress and confirmed public account state."""
        snapshot = self.account.snapshot()
        entry = None
        if self.pending is not None:
            entry = {"opportunity_id": self.pending["oid"], **deepcopy(self.pending["public"]),
                "confirmed_filled_quantity": 0 if not self.pending["applied"] else snapshot["management"]["entry"]["quantity"],
                "unreconciled_execution_feedback": deepcopy(self.pending["unreconciled_execution_feedback"])}
        window = None if self.active is None else self.specs[self.active]["entry_input"]["window"]
        status = ("blocked_input_failure" if self.failure is not None else
            "original_window_exhausted" if window is not None and self.through_ns >= window["end_ns"] - 1 else
            "session_streams_complete" if not self.heap else "continuable_original_window")
        return {"status": status, "reconciliation_snapshot": snapshot, "active_opportunity_id": self.active,
            "active_original_window": deepcopy(window), "pending_entry_reservation": entry,
            "events": deepcopy(self.events), "opportunity_dispositions": deepcopy(self.dispositions),
            "processed_streams": [{"opportunity_id": oid, "resource": resource,
                **runner.stream_commitment(self.processed.get((oid, resource), []))}
                for oid, resource in sorted(self.cursors)],
            "complete_streams_verified": not self.heap and self.failure is None,
            "failure": deepcopy(self.failure)}


def _session(slot, source, opening, previous_sha, *, machine=None):
    if set(source) != {"session_id", "opportunities"} or source["session_id"] != slot["session_id"] or not isinstance(source["opportunities"], list):
        raise ValueError("exact chronological session program required")
    blocked, scheduler, failures = not parent._ready(opening), None, []
    if not blocked:
        try:
            scheduler = machine if machine is not None else _Session(slot, source, opening).run()
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
        if d["disposition"] in {"unavailable_input", "unprocessed_available_input", "blocked_prior_state"}]
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


def _validate_program(program, expected_program_content_sha256):
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
    return slots, sessions


def replay_path(program, *, expected_program_content_sha256):
    slots, sessions = _validate_program(program, expected_program_content_sha256)
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


def _checkpoint(program, through_ns, expected_program_content_sha256):
    slots, sessions = _validate_program(program, expected_program_content_sha256)
    slot, source = slots[len(sessions) - 1], sessions[-1]
    start = valuation.session_start_ns(slot)
    end = int((pd.Timestamp(slot["trading_date"], tz="America/New_York") + pd.DateOffset(days=1)).tz_convert("UTC").value)
    if type(through_ns) is not int or not start <= through_ns < end:
        raise ValueError("checkpoint must remain within the final original session")
    if set(source) != {"session_id", "opportunities"} or source["session_id"] != slot["session_id"]:
        raise ValueError("exact continuation session required")
    opening = accounts.account_state_input(slots[0])["account_state"]
    previous, completed = None, []
    with localcontext() as context:
        context.prec = 60
        for prior_slot, prior_source in zip(slots, sessions[:-1]):
            pair = _session(prior_slot, prior_source, opening, previous)
            completed.append(pair)
            opening, previous = deepcopy(pair["close"]["account_state"]), pair["close"]["content_sha256"]
        machine = None
        if parent._ready(opening):
            machine = _Session(slot, source, opening).run_until(through_ns)
            state = machine.continuation_state()
        else:
            state = {"status": "blocked_prior_state", "reconciliation_snapshot": None,
                "active_opportunity_id": None, "active_original_window": None, "pending_entry_reservation": None,
                "events": [], "opportunity_dispositions": [], "processed_streams": [],
                "complete_streams_verified": False, "failure": None}
    checkpoint = seal({"contract_id": CONTRACT_ID, "artifact_type": "replay_verified_intraday_checkpoint",
        "program_content_sha256": expected_program_content_sha256, "path_id": program["path_id"],
        "session_id": slot["session_id"], "session_index": slot["session_index"], "through_ns": through_ns,
        "source_slot_content_sha256": slot["content_sha256"], "previous_close_content_sha256": previous,
        "prior_completed_sessions": completed, "opening_account_state": deepcopy(opening),
        "seed_application_count": 1, **state, **BOUNDARY})
    return checkpoint, machine


def checkpoint_path(program, *, through_ns, expected_program_content_sha256):
    return _checkpoint(program, through_ns, expected_program_content_sha256)[0]


def resume_path(program, checkpoint, *, expected_program_content_sha256,
                expected_checkpoint_content_sha256, through_ns=None):
    """Reconstruct the exact committed prefix, then resume the same reducer.

    Never import claimed cash, quantities, private outcomes or serialized Python
    objects. The original source program remains immutable across every resume.
    A full resume returns byte-identical output to an uninterrupted path replay.
    """
    accounts._sealed(checkpoint, "continuation checkpoint")
    if checkpoint["content_sha256"] != expected_checkpoint_content_sha256:
        raise ValueError("checkpoint differs from independent caller commitment")
    _without_labels(checkpoint)
    expected, machine = _checkpoint(program, checkpoint["through_ns"], expected_program_content_sha256)
    require_exact(checkpoint, expected, "reconstructed continuation checkpoint")
    if through_ns is not None:
        if type(through_ns) is not int or through_ns <= checkpoint["through_ns"]:
            raise ValueError("continuation cutoff must advance")
        # The public API enforces the same session and source bounds again.
        return checkpoint_path(program, through_ns=through_ns,
            expected_program_content_sha256=expected_program_content_sha256)
    slots, sessions = program["slots"], program["sessions"]
    slot, source = slots[len(sessions) - 1], sessions[-1]
    opening = checkpoint["opening_account_state"]
    with localcontext() as context:
        context.prec = 60
        if machine is not None:
            machine.run()
        pair = _session(slot, source, opening, checkpoint["previous_close_content_sha256"], machine=machine)
    results = deepcopy(checkpoint["prior_completed_sessions"]) + [pair]
    return seal({"contract_id": CONTRACT_ID, "artifact_type": "synthetic_chronological_account_path",
        "program_content_sha256": program["content_sha256"], "slot_catalog_sha256": canonical_fingerprint(slots),
        "path_id": program["path_id"], "seed_content_sha256": slots[0]["seed_content_sha256"],
        "initial_account_state": accounts.account_state_input(slots[0])["account_state"],
        "seed_application_count": 1, "session_count": len(results), "sessions": results,
        "last_close_content_sha256": pair["close"]["content_sha256"], "synthetic_only": True, **BOUNDARY})


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
    return dict(scheduler.mechanics(),
        reentry="frozen_two_accepted_entries_per_activation_starter_then_flat_reentry_new_plan_required_no_adds",
        campaign="original_activation_identity_new_activation_is_a_new_campaign_no_symbol_aliasing",
        accounting="current_entry_cost_basis_plus_preserved_campaign_gross_fees_and_accepted_fill_ids",
        continuation="independently_pinned_program_and_checkpoint_prefix_recomputed_before_same_window_resume",
        checkpoint="public_confirmed_state_pending_reservations_processed_stream_hashes_no_private_outcomes",
        management="fresh_target_stop_and_attempt_state_per_new_entry_never_reset_on_resume",
        liquidity="preserve_consumed_sell_source_identities_across_reentry_and_resume",
        expired_window="retain_open_shares_orders_and_failure_no_extension_retry_or_overnight_execution")


def expected_contract(root):
    return seal({"schema_version": 1, "contract_id": CONTRACT_ID, "parent_commit_sha": PARENT_COMMIT,
        "parent_tree_sha": PARENT_TREE, "parent_scheduler_freeze_content_sha256": PARENT_FREEZE,
        "frozen_parent_file_sha256": PARENT_PINS, "mechanics": mechanics(),
        "hypothesis": "flat_campaign_reentry_and_verified_original_window_resumption_preserve_exact_history_and_frozen_attempt_ceilings",
        "implementation_file_sha256": {p: file_sha(root / p) for p in (MODULE_PATH, SCRIPT_PATH, CHECKER_PATH, TEST_PATH, WORKFLOW_PATH)},
        "next_gate": NEXT_GATE, **BOUNDARY})


def validate_registration(root):
    for path, sha in PARENT_PINS.items():
        accounts.availability._regular(root / path)
        if file_sha(root / path) != sha:
            raise ValueError("scheduler parent differs: " + path)
    scheduler.verify_bundle(root, root / scheduler.OUTPUT_PATH)
    if frozen(root / scheduler.OUTPUT_PATH / "freeze-manifest.json")["content_sha256"] != PARENT_FREEZE:
        raise ValueError("valuation freeze differs")
    require_exact(frozen(root / CONTRACT_PATH), expected_contract(root), "account scheduler registration")
    return seal({"verification_passed": True, "contract_content_sha256": expected_contract(root)["content_sha256"], **BOUNDARY})


def build_bundle(root):
    validate_registration(root)
    original = frozen(root / parent.OUTPUT_PATH / "account-state-dependencies.json")
    payloads = {"continuity-dependencies.json": seal({"contract_id": CONTRACT_ID, "account_plan_content_sha256": original["account_plan_content_sha256"],
        "slots": original["slots"], "path_count": original["path_count"], "session_count": original["session_count"],
        "seed_applications": original["seed_applications"], "previous_close_dependencies": original["previous_close_dependencies"], **BOUNDARY}),
        "continuity-mechanics.json": seal({"contract_id": CONTRACT_ID, "mechanics": mechanics(), **BOUNDARY}),
        "readiness-report.json": seal({"contract_id": CONTRACT_ID, "synthetic_account_continuity_registered": True,
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


