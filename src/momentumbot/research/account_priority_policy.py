"""Named paper-account constraints and deterministic scarcity ordering.

The policy in this module is deliberately a project safety envelope, not an
estimate of Ross Cameron's account aggression.  It materializes the existing
``paper-safe`` risk fractions from causal session-start equity and buying power,
then supplies the explicit structural fields required by the frozen campaign
ledger.

Opportunity ordering is similarly narrow.  It resolves same-account capacity
collisions with the already-existing ``CandidateSnapshot.ranking_key`` and
stable causal tie-breakers.  It cannot compare main with small accounts, apply
the ledger, create an order, or synthesize a fill.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd

from momentumbot.models import (
    CandidateQuality,
    CandidateSnapshot,
    RiskPolicy,
    StrategyProfile,
    current_general_2026,
    current_small_account_2026,
    paper_safe_risk,
)
from momentumbot.research.campaign_portfolio import AccountClass, AccountConstraints


SCHEMA_VERSION = 1
CONTRACT_ID = "paper-account-scarcity-policy-v0.1"
MAIN_POLICY_ID = "paper-safe-main-account-v0.1"
SMALL_POLICY_ID = "paper-safe-small-account-v0.1"
LEDGER_CONTRACT_SHA256 = "f2a80f4350e6283e2638702d70515bf03ee6c930e7d52706d09ef5e1d9f419b6"
PAPER_SAFE_RISK_FINGERPRINT = "dc8de12fe70d0035ec0dcb5883023196b5f3012457bda533b5acdd1fc70d42f3"
GENERAL_PROFILE_FINGERPRINT = "7d15fb979701324bf862b1dc37e5f9b514dcf1ab8cf1e062ae4a60027233d4ff"
SMALL_PROFILE_FINGERPRINT = "fb86fc5326903cab16c283a03d8e371f66487f41589fb1b69b79f8912a0a6489"


@dataclass(frozen=True, slots=True)
class PaperAccountPolicy:
    policy_id: str
    account_class: AccountClass
    strategy_profile_id: str
    strategy_profile_fingerprint: str
    risk_policy_id: str
    risk_policy_fingerprint: str
    max_open_positions: int = 1
    max_entries_per_campaign: int = 2
    allow_reentry: bool = True
    first_session_entry_must_be_starter: bool = True

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ValueError("policy_id must be non-empty")
        if not isinstance(self.account_class, AccountClass):
            raise ValueError("account_class must be an AccountClass")
        if self.max_open_positions != 1:
            raise ValueError("v0.1 paper safety policy requires one open position")
        if self.max_entries_per_campaign != 2:
            raise ValueError("v0.1 paper safety policy requires at most two campaign entries")
        if self.allow_reentry is not True:
            raise ValueError("v0.1 represents one bounded re-entry inside the two-entry cap")
        if self.first_session_entry_must_be_starter is not True:
            raise ValueError("v0.1 requires the first session entry to be a starter")

    def manifest(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "account_class": self.account_class.value,
            "strategy_profile_id": self.strategy_profile_id,
            "strategy_profile_fingerprint": self.strategy_profile_fingerprint,
            "risk_policy_id": self.risk_policy_id,
            "risk_policy_fingerprint": self.risk_policy_fingerprint,
            "max_open_positions": self.max_open_positions,
            "max_entries_per_campaign": self.max_entries_per_campaign,
            "allow_reentry": self.allow_reentry,
            "first_session_entry_must_be_starter": self.first_session_entry_must_be_starter,
            "materialization": {
                "campaign_open_notional": "min(starting_buying_power, starting_equity * max_position_fraction_of_equity)",
                "total_open_notional": "campaign_open_notional because max_open_positions is one",
                "campaign_open_risk": "starting_equity * risk_per_trade_fraction",
                "total_open_risk": "campaign_open_risk because max_open_positions is one",
                "starter_max_notional": "campaign_open_notional; starter role is enforced but no unsourced smaller fraction is invented",
                "max_daily_loss_dollars": "starting_equity * max_daily_loss_fraction",
                "max_entry_slippage_bps": "none; frozen execution approval remains authoritative",
            },
        }

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(self.manifest())


@dataclass(frozen=True, slots=True)
class ScarceCapitalOpportunity:
    opportunity_id: str
    account_id: str
    account_class: AccountClass
    candidate_activation_id: str
    plan_id: str
    execution_at: datetime | pd.Timestamp
    candidate_snapshot: CandidateSnapshot

    def __post_init__(self) -> None:
        for field_name in (
            "opportunity_id",
            "account_id",
            "candidate_activation_id",
            "plan_id",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must be non-empty")
        if not isinstance(self.account_class, AccountClass):
            raise ValueError("account_class must be an AccountClass")
        execution_at = _aware_timestamp(self.execution_at, "execution_at")
        snapshot_at = _aware_timestamp(
            self.candidate_snapshot.timestamp,
            "candidate_snapshot.timestamp",
        )
        if snapshot_at > execution_at:
            raise ValueError("candidate snapshot cannot be available after execution_at")
        if self.candidate_snapshot.quality is CandidateQuality.REJECT:
            raise ValueError("rejected candidates cannot enter scarcity ordering")
        if self.candidate_snapshot.symbol.strip() != self.candidate_snapshot.symbol:
            raise ValueError("candidate symbol must not contain surrounding whitespace")
        if self.candidate_snapshot.top_gainer_rank is not None:
            if self.candidate_snapshot.top_gainer_rank < 1:
                raise ValueError("top_gainer_rank must be positive when present")


def paper_account_policy(account_class: AccountClass) -> PaperAccountPolicy:
    if account_class is AccountClass.MAIN:
        strategy = current_general_2026()
        return PaperAccountPolicy(
            policy_id=MAIN_POLICY_ID,
            account_class=account_class,
            strategy_profile_id=strategy.name,
            strategy_profile_fingerprint=GENERAL_PROFILE_FINGERPRINT,
            risk_policy_id=paper_safe_risk().name,
            risk_policy_fingerprint=PAPER_SAFE_RISK_FINGERPRINT,
        )
    if account_class is AccountClass.SMALL:
        strategy = current_small_account_2026()
        return PaperAccountPolicy(
            policy_id=SMALL_POLICY_ID,
            account_class=account_class,
            strategy_profile_id=strategy.name,
            strategy_profile_fingerprint=SMALL_PROFILE_FINGERPRINT,
            risk_policy_id=paper_safe_risk().name,
            risk_policy_fingerprint=PAPER_SAFE_RISK_FINGERPRINT,
        )
    raise ValueError(f"unsupported account class: {account_class}")


def materialize_account_constraints(
    policy: PaperAccountPolicy,
    *,
    account_id: str,
    starting_equity: float,
    starting_buying_power: float,
) -> AccountConstraints:
    """Convert a named policy and causal broker snapshot into ledger limits."""
    if not account_id.strip():
        raise ValueError("account_id must be non-empty")
    if not _finite_positive(starting_equity):
        raise ValueError("starting_equity must be finite and positive")
    if not _finite_positive(starting_buying_power):
        raise ValueError("starting_buying_power must be finite and positive")

    risk = paper_safe_risk()
    _validate_policy_parents(policy, risk)
    campaign_notional = min(
        starting_buying_power,
        starting_equity * risk.max_position_fraction_of_equity,
    )
    campaign_risk = starting_equity * risk.risk_per_trade_fraction
    return AccountConstraints(
        account_id=account_id,
        policy_id=policy.policy_id,
        account_class=policy.account_class,
        starting_equity=starting_equity,
        starting_buying_power=starting_buying_power,
        max_open_positions=policy.max_open_positions,
        max_total_open_notional=campaign_notional,
        max_campaign_open_notional=campaign_notional,
        max_total_open_risk=campaign_risk,
        max_campaign_open_risk=campaign_risk,
        max_entries_per_campaign=policy.max_entries_per_campaign,
        starter_max_notional=campaign_notional,
        max_daily_loss_dollars=starting_equity * risk.max_daily_loss_fraction,
        giveback_fraction=risk.giveback_fraction,
        allow_reentry=policy.allow_reentry,
        first_session_entry_must_be_starter=policy.first_session_entry_must_be_starter,
        max_entry_slippage_bps=None,
    )


def order_scarce_capital_opportunities(
    opportunities: Iterable[ScarceCapitalOpportunity],
) -> tuple[ScarceCapitalOpportunity, ...]:
    """Order one account's events without using labels, outcomes, or AI context.

    Chronologically distinct execution events stay chronological.  Exact-time
    collisions use the existing candidate ranking, then earlier causal snapshot,
    symbol, plan, and opportunity identifiers.  Cross-account divided attention
    is intentionally unresolved and therefore fails closed.
    """
    rows = tuple(opportunities)
    if not rows:
        return ()
    account_keys = {(row.account_id, row.account_class) for row in rows}
    if len(account_keys) != 1:
        raise ValueError("scarcity ordering is account-local; cross-account priority is unresolved")
    opportunity_ids = [row.opportunity_id for row in rows]
    if len(opportunity_ids) != len(set(opportunity_ids)):
        raise ValueError("opportunity_id values must be unique")

    return tuple(sorted(rows, key=_opportunity_order_key))


def scarcity_priority_artifact(
    opportunities: Iterable[ScarceCapitalOpportunity],
) -> dict[str, object]:
    ordered = order_scarce_capital_opportunities(opportunities)
    rows = []
    for ordinal, item in enumerate(ordered, start=1):
        candidate = item.candidate_snapshot
        rows.append(
            {
                "priority_ordinal": ordinal,
                "opportunity_id": item.opportunity_id,
                "account_id": item.account_id,
                "account_class": item.account_class.value,
                "candidate_activation_id": item.candidate_activation_id,
                "plan_id": item.plan_id,
                "execution_at": _aware_timestamp(item.execution_at, "execution_at").isoformat(),
                "candidate_snapshot_at": _aware_timestamp(
                    candidate.timestamp,
                    "candidate_snapshot.timestamp",
                ).isoformat(),
                "symbol": candidate.symbol,
                "quality": candidate.quality.value,
                "top_gainer_rank": candidate.top_gainer_rank,
                "percent_gain": candidate.percent_gain,
                "relative_volume": candidate.relative_volume,
                "cumulative_volume": candidate.cumulative_volume,
                "float_shares": candidate.float_shares,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "artifact_type": "paper_account_scarcity_priority_shadow",
        "knowledge_policy": "causal_candidate_and_execution_state_only_no_labels_or_outcomes",
        "runtime_integration": False,
        "broker_order_or_size_authority": False,
        "policy_promotion_eligible": False,
        "ordered_opportunities": rows,
    }


def policy_bundle_manifest() -> dict[str, object]:
    return {
        "contract_id": CONTRACT_ID,
        "schema_version": SCHEMA_VERSION,
        "ledger_contract_content_sha256": LEDGER_CONTRACT_SHA256,
        "paper_safe_risk_fingerprint": risk_policy_fingerprint(paper_safe_risk()),
        "account_policies": [
            paper_account_policy(AccountClass.MAIN).manifest(),
            paper_account_policy(AccountClass.SMALL).manifest(),
        ],
        "scarcity_order": [
            "execution_at ascending",
            "existing CandidateSnapshot.ranking_key descending",
            "candidate snapshot timestamp ascending",
            "symbol ascending",
            "plan_id ascending",
            "opportunity_id ascending",
        ],
        "cross_account_priority": "unresolved_fail_closed",
    }


def canonical_fingerprint(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def dataclass_fingerprint(value: RiskPolicy | StrategyProfile) -> str:
    payload = asdict(value)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def risk_policy_fingerprint(policy: RiskPolicy) -> str:
    return dataclass_fingerprint(policy)


def strategy_profile_fingerprint(profile: StrategyProfile) -> str:
    return dataclass_fingerprint(profile)


def validate_account_priority_contract(payload: Mapping[str, object]) -> None:
    expected_root = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "artifact_type": "research_paper_account_and_scarcity_policy_contract",
        "runtime_strategy_effect": "none_not_integrated",
        "policy_promotion_eligible": False,
        "portfolio_backtest_eligible": False,
        "ross_replication_claim_eligible": False,
    }
    for field, expected in expected_root.items():
        if payload.get(field) != expected:
            raise ValueError(f"{field} must be {expected!r}")

    parents = payload.get("frozen_parents")
    if not isinstance(parents, Mapping):
        raise ValueError("frozen_parents must be an object")
    expected_parents = {
        "campaign_ledger_contract_content_sha256": LEDGER_CONTRACT_SHA256,
        "micro_policy_fingerprint": "49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa",
        "paper_safe_risk_fingerprint": PAPER_SAFE_RISK_FINGERPRINT,
        "general_strategy_profile_fingerprint": GENERAL_PROFILE_FINGERPRINT,
        "small_strategy_profile_fingerprint": SMALL_PROFILE_FINGERPRINT,
    }
    for field, expected in expected_parents.items():
        if parents.get(field) != expected:
            raise ValueError(f"frozen_parents.{field} must preserve the exact parent")

    knowledge = payload.get("knowledge_policy")
    if not isinstance(knowledge, Mapping):
        raise ValueError("knowledge_policy must be an object")
    expected_knowledge = {
        "runtime_inputs_available_by_decision_time": True,
        "raw_transcripts_allowed_at_runtime": False,
        "retrospective_actions_or_labels_allowed_at_runtime": False,
        "later_prices_or_outcomes_allowed_at_runtime": False,
        "semantic_ai_used_for_priority": False,
        "ai_may_create_orders_or_raise_risk": False,
    }
    for field, expected in expected_knowledge.items():
        if knowledge.get(field) is not expected:
            raise ValueError(f"knowledge_policy.{field} must be {expected}")

    policies = payload.get("account_policies")
    if not isinstance(policies, list) or len(policies) != 2:
        raise ValueError("exactly two account policies are required")
    expected_policies = {
        MAIN_POLICY_ID: (AccountClass.MAIN, "current-general-2026"),
        SMALL_POLICY_ID: (AccountClass.SMALL, "current-small-account-2026"),
    }
    found: set[str] = set()
    for row in policies:
        if not isinstance(row, Mapping):
            raise ValueError("each account policy must be an object")
        policy_id = str(row.get("policy_id", ""))
        if policy_id not in expected_policies or policy_id in found:
            raise ValueError("account policy IDs must be exact and unique")
        found.add(policy_id)
        expected_class, expected_profile = expected_policies[policy_id]
        if row.get("account_class") != expected_class.value:
            raise ValueError("account policy class mismatch")
        if row.get("strategy_profile_id") != expected_profile:
            raise ValueError("account strategy profile mismatch")
        if row.get("max_open_positions") != 1:
            raise ValueError("paper safety profile must cap open positions at one")
        if row.get("max_entries_per_campaign") != 2:
            raise ValueError("paper safety profile must cap campaign entries at two")
        if row.get("allow_reentry") is not True:
            raise ValueError("bounded re-entry representation must remain enabled")
        if row.get("first_session_entry_must_be_starter") is not True:
            raise ValueError("first session entry must remain a starter")
        exact_numeric_values = {
            "risk_per_campaign_fraction_of_starting_equity": 0.0025,
            "max_daily_loss_fraction_of_starting_equity": 0.01,
            "max_campaign_notional_fraction_of_starting_equity": 0.50,
            "profit_giveback_fraction": 0.50,
            "max_entry_slippage_bps": None,
        }
        for field, expected in exact_numeric_values.items():
            if row.get(field) != expected:
                raise ValueError(f"{policy_id}.{field} must preserve paper-safe")
        if row.get("numeric_risk_source") != "existing_paper_safe_policy_only":
            raise ValueError("account risk values cannot be fitted from transcripts")
        if row.get("structural_cap_classification") != "conservative_project_safety_translation":
            raise ValueError("structural caps cannot be presented as Ross-authored values")

    priority = payload.get("scarce_capital_priority")
    if not isinstance(priority, Mapping):
        raise ValueError("scarce_capital_priority must be an object")
    if priority.get("ordered_fields") != policy_bundle_manifest()["scarcity_order"]:
        raise ValueError("scarcity priority must preserve the registered causal ordering")
    if priority.get("cross_account_priority") != "unresolved_fail_closed":
        raise ValueError("cross-account divided attention must remain unresolved")
    if priority.get("top_n_candidate_filter") is not False:
        raise ValueError("scarcity priority cannot become a top-N scanner filter")

    evidence = payload.get("offline_transcript_boundary_evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError("offline_transcript_boundary_evidence must be an object")
    if evidence.get("runtime_allowed") is not False:
        raise ValueError("transcript evidence must remain runtime-prohibited")
    if evidence.get("used_to_set_numeric_risk_values") is not False:
        raise ValueError("transcripts cannot calibrate the paper safety numbers")
    if evidence.get("archive_file_sha256") != (
        "c59a8dd67bf4cb2b3bb4539996bbe1b648b1503a73916371b2f98661a4d33db0"
    ):
        raise ValueError("offline evidence archive hash mismatch")
    observations = evidence.get("observations")
    if not isinstance(observations, list) or len(observations) != 5:
        raise ValueError("the boundary audit must retain all five reviewed observations")
    if any(not isinstance(row, Mapping) or row.get("policy_role") != "boundary_only" for row in observations):
        raise ValueError("transcript observations must remain boundary-only")
    expected_video_ids = {
        "oaHTe5lotSQ",
        "8SWCCRLg1p0",
        "5AV2OLWD1gc",
        "2IMvfIR1TPA",
        "L1mi5ENCn98",
    }
    if {str(row.get("video_id")) for row in observations} != expected_video_ids:
        raise ValueError("offline transcript boundary evidence IDs changed")


def load_account_priority_contract(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("account-priority contract root must be an object")
    validate_account_priority_contract(payload)
    return payload


def _opportunity_order_key(item: ScarceCapitalOpportunity) -> tuple[object, ...]:
    ranking = item.candidate_snapshot.ranking_key
    return (
        _aware_timestamp(item.execution_at, "execution_at"),
        *(-value for value in ranking),
        _aware_timestamp(item.candidate_snapshot.timestamp, "candidate_snapshot.timestamp"),
        item.candidate_snapshot.symbol,
        item.plan_id,
        item.opportunity_id,
    )


def _validate_policy_parents(policy: PaperAccountPolicy, risk: RiskPolicy) -> None:
    expected = paper_account_policy(policy.account_class)
    if policy != expected:
        raise ValueError("paper account policy does not match the frozen named policy")
    if risk_policy_fingerprint(risk) != PAPER_SAFE_RISK_FINGERPRINT:
        raise ValueError("paper-safe risk policy fingerprint changed")
    if policy.account_class is AccountClass.MAIN:
        profile = current_general_2026()
        expected_fingerprint = GENERAL_PROFILE_FINGERPRINT
    else:
        profile = current_small_account_2026()
        expected_fingerprint = SMALL_PROFILE_FINGERPRINT
    if strategy_profile_fingerprint(profile) != expected_fingerprint:
        raise ValueError("strategy profile fingerprint changed")


def _aware_timestamp(value: datetime | pd.Timestamp, field: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return timestamp


def _finite_positive(value: float) -> bool:
    return bool(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and value > 0
    )
