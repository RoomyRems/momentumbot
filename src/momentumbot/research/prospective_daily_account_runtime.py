"""Provider-free daily account/runtime composition for the prospective panel.

The composer joins only already-frozen causal artifacts.  It has no provider
client, credential loader, broker path, retrospective label reader, or policy
selection authority.  The current 550 ms market-input window can resolve entry
attempts but cannot resolve the registered one-minute management rule, so every
accepted entry remains explicitly open.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping, MutableMapping, Sequence

import pandas as pd

from momentumbot.models import (
    CandidateQuality,
    CandidateSnapshot,
    StrategyProfile,
    current_general_2026,
    current_small_account_2026,
)
from momentumbot.research.account_chronological_integration import (
    MICRO_POLICY_FINGERPRINT,
    PANEL_ID,
    REGISTERED_DATES,
    maximum_whole_share_quantity,
)
from momentumbot.research.account_priority_policy import (
    ScarceCapitalOpportunity,
    materialize_account_constraints,
    order_scarce_capital_opportunities,
    paper_account_policy,
)
from momentumbot.research.account_snapshot_capture import (
    CONTRACT_CONTENT_SHA256 as ACCOUNT_CAPTURE_CONTENT_SHA256,
    validate_bundle as validate_account_bundle,
    validate_snapshot_artifact,
)
from momentumbot.research.campaign_portfolio import (
    AccountClass,
    CampaignPortfolioLedger,
    EntryFill,
    EntryRole,
    PlanEmission,
)
from momentumbot.research.execution_realism import (
    BASELINE_CONSERVATIVE_POLICY,
    BASELINE_LIMIT_OFFSET_TICKS,
    CONTRACT_CONTENT_SHA256 as EXECUTION_CONTRACT_CONTENT_SHA256,
    STRESS_LIMIT_OFFSET_TICKS,
    STRESS_POLICY,
    ExecutedEquityTrade,
    ExecutionOutcome,
    ExecutionStatus,
    MarketableLimitOrder,
    MarketableLimitPolicy,
    OrderSide,
    TopOfBookEvent,
    aggregate_daily_equity_fees,
    marketable_limit_price,
    simulate_marketable_limit_order,
)
from momentumbot.research.microstructure_contract import canonical_fingerprint
from momentumbot.research.prospective_account_evaluation import (
    ACCOUNT_KEYS,
    CONTRACT_CONTENT_SHA256 as EVALUATION_CONTRACT_CONTENT_SHA256,
    AccountSessionPerformance,
    RuntimeDecision,
    registered_cells,
)
from momentumbot.research.prospective_daily_source import (
    CONTRACT_CONTENT_SHA256 as DAILY_SOURCE_CONTENT_SHA256,
    GENERAL_PROFILE_ID,
    MANIFEST_FILE as SOURCE_MANIFEST_FILE,
    MICRO_FILE,
    SCANNER_FILE,
    SMALL_PROFILE_ID,
    SOURCE_FILE,
    MicroTriggerDecision,
    build_daily_artifacts,
    profile_eligibility,
)
from momentumbot.research.prospective_market_input_capture import (
    CONTRACT_CONTENT_SHA256 as MARKET_INPUT_CONTENT_SHA256,
    PRE_DECISION_QUOTE_NS,
    load_capture_contract,
    top_of_book_events,
    validate_market_input_capture,
)
from momentumbot.research.prospective_opportunity_freeze import (
    CONTRACT_CONTENT_SHA256 as OPPORTUNITY_FREEZE_CONTENT_SHA256,
    load_opportunity_freeze_contract,
    validate_daily_decision_source,
    validate_freeze_manifest,
)


SCHEMA_VERSION = 1
CONTRACT_ID = "prospective-daily-account-runtime-v0.1"
CONTRACT_CONTENT_SHA256 = (
    "dea1d60a804626ca623512d8f4828b40eca7fa57da85b12525926fc04c3d0531"
)
ARTIFACT_TYPE = "label_blind_prospective_daily_account_runtime"
OUTPUT_FILE = "daily-account-runtime.json"
OPPORTUNITY_FILE = "opportunity-manifest.json"
REQUEST_FILE = "request-manifest.json"
FREEZE_FILE = "freeze-manifest.json"
ACCOUNT_INTEGRATION_CONTENT_SHA256 = (
    "64489aa27fec5eaf8ca12c94f4aeb47344d49a79b14df1bdda706cd23cc9ce73"
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,31}$")
_FORBIDDEN_RUNTIME_KEYS = {
    "benchmark_label",
    "evidence_content_sha256",
    "human_action",
    "human_decision",
    "human_state",
    "human_trade",
    "human_skip",
    "reported_entry",
    "reported_entry_prices",
    "reported_entry_times",
    "reported_exit",
    "reported_exit_prices",
    "reported_exit_reasons",
    "reported_exit_times",
    "retrospective_label",
    "ross_fill",
    "ross_action",
    "ross_skip",
    "ross_trade",
    "skip_label",
    "trade_completion",
    "transcript_text",
}
_SCENARIOS: dict[str, tuple[MarketableLimitPolicy, int]] = {
    BASELINE_CONSERVATIVE_POLICY.policy_id: (
        BASELINE_CONSERVATIVE_POLICY,
        BASELINE_LIMIT_OFFSET_TICKS,
    ),
    STRESS_POLICY.policy_id: (STRESS_POLICY, STRESS_LIMIT_OFFSET_TICKS),
}
_ACCOUNT_CONFIGURATION: dict[
    str, tuple[AccountClass, str, StrategyProfile]
] = {
    "main_account": (
        AccountClass.MAIN,
        GENERAL_PROFILE_ID,
        current_general_2026(),
    ),
    "small_account": (
        AccountClass.SMALL,
        SMALL_PROFILE_ID,
        current_small_account_2026(),
    ),
}


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _list(value: object, field: str) -> list[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return list(value)


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return value


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


def _number(value: object, field: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        qualifier = "positive" if positive else "finite"
        raise ValueError(f"{field} must be {qualifier}")
    return result


def _aware(value: object, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field} must be ISO 8601") from exc
    else:
        raise ValueError(f"{field} must be an aware timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed


def _iso_from_ns(value: int) -> str:
    return datetime.fromtimestamp(value / 1_000_000_000, tz=UTC).isoformat()


def _canonical_equal(left: object, right: object) -> bool:
    return json.dumps(
        left,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) == json.dumps(
        right,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _validate_hash(payload: Mapping[str, object], field: str) -> str:
    claimed = _sha(payload.get("content_sha256"), f"{field}.content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError(f"{field} content hash mismatch")
    return claimed


def _walk_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(_walk_keys(child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            keys.update(_walk_keys(child))
    return keys


def validate_daily_runtime_contract(payload: Mapping[str, object]) -> None:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "artifact_type": "preregistered_label_blind_daily_account_runtime_composer",
        "registration_date": "2026-08-22",
        "registration_status": "registered_before_first_prospective_session",
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise ValueError(f"daily runtime contract {field} changed")
    claimed = _sha(payload.get("content_sha256"), "contract.content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if claimed != CONTRACT_CONTENT_SHA256 or canonical_fingerprint(unsigned) != claimed:
        raise ValueError("daily runtime contract content hash mismatch")
    parents = _mapping(payload.get("frozen_parents"), "frozen_parents")
    expected_parents = {
        "panel_id": PANEL_ID,
        "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
        "daily_source_contract_content_sha256": DAILY_SOURCE_CONTENT_SHA256,
        "opportunity_freeze_contract_content_sha256": (
            OPPORTUNITY_FREEZE_CONTENT_SHA256
        ),
        "market_input_capture_contract_content_sha256": (
            MARKET_INPUT_CONTENT_SHA256
        ),
        "account_snapshot_capture_contract_content_sha256": (
            ACCOUNT_CAPTURE_CONTENT_SHA256
        ),
        "account_integration_contract_content_sha256": (
            ACCOUNT_INTEGRATION_CONTENT_SHA256
        ),
        "prospective_execution_contract_content_sha256": (
            EXECUTION_CONTRACT_CONTENT_SHA256
        ),
        "prospective_account_evaluation_contract_content_sha256": (
            EVALUATION_CONTRACT_CONTENT_SHA256
        ),
    }
    if dict(parents) != expected_parents:
        raise ValueError("daily runtime frozen parents changed")
    cells = _mapping(payload.get("registered_cells"), "registered_cells")
    if cells.get("accounts") != list(ACCOUNT_KEYS):
        raise ValueError("daily runtime accounts changed")
    if cells.get("daily_session_record_count") != 12:
        raise ValueError("daily runtime must retain twelve session records")
    if cells.get("ten_date_session_record_count") != 120:
        raise ValueError("panel runtime must retain 120 session records")
    if cells.get("best_cell_selection_allowed") is not False:
        raise ValueError("daily runtime cannot select a best cell")
    management = _mapping(payload.get("management_coverage"), "management_coverage")
    if management.get("one_minute_management_inputs_available") is not False:
        raise ValueError("daily runtime cannot claim absent management inputs")
    if management.get("filled_position_representation") != "open_unresolved":
        raise ValueError("daily runtime must retain unresolved open positions")
    if management.get("synthetic_exit_allowed") is not False:
        raise ValueError("daily runtime cannot synthesize exits")
    authority = _mapping(payload.get("authority_boundary"), "authority_boundary")
    for field in (
        "provider_call_authorized",
        "provider_credential_authorized",
        "broker_credential_authorized",
        "paper_order_authorized",
        "live_order_authorized",
        "retrospective_label_access_authorized",
        "later_price_access_authorized",
        "best_cell_selection_authorized",
        "policy_promotion_eligible",
        "profitability_claim_eligible",
        "ross_replication_claim_eligible",
    ):
        if authority.get(field) is not False:
            raise ValueError(f"daily runtime authority expanded at {field}")


def load_daily_runtime_contract(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("daily runtime contract root must be an object")
    validate_daily_runtime_contract(payload)
    return payload


def _validate_source_bundle(
    scanner_runtime: Mapping[str, object],
    micro_runtime: Mapping[str, object],
    decision_source: Mapping[str, object],
    producer_manifest: Mapping[str, object],
) -> tuple[list[Mapping[str, object]], list[Mapping[str, object]]]:
    _validate_hash(scanner_runtime, "scanner runtime")
    raw_decisions = _list(micro_runtime.get("decisions"), "micro decisions")
    triggers: list[MicroTriggerDecision] = []
    for index, raw in enumerate(raw_decisions):
        row = _mapping(raw, f"micro decisions[{index}]")
        triggers.append(
            MicroTriggerDecision(
                activation_id=str(row.get("activation_id", "")),
                plan_id=str(row.get("plan_id", "")),
                symbol=str(row.get("symbol", "")),
                candidate_qualified_at=str(row.get("candidate_qualified_at", "")),
                decision_at=str(row.get("decision_at", "")),
                micro_runtime_content_sha256=str(
                    row.get("micro_runtime_content_sha256", "")
                ),
                eligible_strategy_profile_ids=tuple(
                    str(value)
                    for value in _list(
                        row.get("eligible_strategy_profile_ids"),
                        "eligible strategy profiles",
                    )
                ),
                plan=dict(_mapping(row.get("plan"), "micro plan")),
            )
        )
    rebuilt = build_daily_artifacts(
        scanner_runtime=scanner_runtime,
        trigger_decisions=triggers,
    )
    comparisons = (
        (micro_runtime, rebuilt.micro_runtime, "micro runtime"),
        (decision_source, rebuilt.decision_source, "daily decision source"),
        (producer_manifest, rebuilt.producer_manifest, "producer manifest"),
    )
    for supplied, expected, field in comparisons:
        if not _canonical_equal(supplied, expected):
            raise ValueError(f"{field} differs from deterministic source composition")
    activations = [
        _mapping(row, "micro activation")
        for row in _list(micro_runtime.get("activations"), "micro activations")
    ]
    return activations, [
        _mapping(row, "micro decision") for row in raw_decisions
    ]


def _candidate_from_row(
    row: Mapping[str, object],
    profile: StrategyProfile,
) -> CandidateSnapshot:
    symbol = str(row.get("symbol", ""))
    if _SYMBOL.fullmatch(symbol) is None:
        raise ValueError("scanner candidate symbol is invalid")
    timestamp = _aware(row.get("decision_time"), "scanner decision_time")
    if row.get("candidate_completed_bar_present") is not True:
        raise ValueError("scanner activation row lacks its completed bar")
    price = _number(row.get("price"), "scanner price", positive=True)
    cumulative_volume = _integer(
        row.get("cumulative_volume"),
        "scanner cumulative_volume",
    )
    relative_volume = _number(
        row.get("exact_same_time_rvol"),
        "scanner exact_same_time_rvol",
    )
    percent_gain = _number(row.get("percent_gain"), "scanner percent_gain")
    raw_float = row.get("estimated_float_shares")
    float_shares = (
        None
        if raw_float is None
        else _integer(raw_float, "scanner estimated_float_shares", minimum=1)
    )
    raw_news = row.get("has_provider_news_as_of")
    if not isinstance(raw_news, bool):
        raise ValueError("scanner has_provider_news_as_of must be boolean")
    raw_rank = row.get("top_gainer_rank")
    rank = (
        None
        if raw_rank is None
        else _integer(raw_rank, "scanner top_gainer_rank", minimum=1)
    )
    state = profile_eligibility(row, profile)
    quality = CandidateQuality(str(state.get("quality", "")))
    pillars_raw = _mapping(state.get("pillars"), "profile eligibility pillars")
    pillars = {str(key): value is True for key, value in pillars_raw.items()}
    reasons = tuple(
        str(value)
        for value in _list(state.get("reasons"), "profile eligibility reasons")
    )
    return CandidateSnapshot(
        symbol=symbol,
        timestamp=timestamp,
        price=price,
        cumulative_volume=cumulative_volume,
        relative_volume=relative_volume,
        percent_gain=percent_gain,
        float_shares=float_shares,
        float_rotation=(
            cumulative_volume / float_shares if float_shares is not None else None
        ),
        has_fresh_news=raw_news,
        top_gainer_rank=rank,
        pillars=pillars,
        quality=quality,
        reasons=reasons,
    )


def _activation_candidates(
    scanner_runtime: Mapping[str, object],
    activations: Sequence[Mapping[str, object]],
) -> tuple[
    dict[str, Mapping[str, object]],
    dict[tuple[str, str], CandidateSnapshot],
]:
    scanner_rows = [
        _mapping(row, "scanner row")
        for row in _list(scanner_runtime.get("rows"), "scanner rows")
    ]
    by_hash: dict[str, Mapping[str, object]] = {}
    for row in scanner_rows:
        fingerprint = canonical_fingerprint(row)
        if fingerprint in by_hash:
            raise ValueError("scanner runtime repeats an identical activation row")
        by_hash[fingerprint] = row
    activation_index: dict[str, Mapping[str, object]] = {}
    candidate_index: dict[tuple[str, str], CandidateSnapshot] = {}
    for activation in activations:
        activation_id = str(activation.get("activation_id", ""))
        if not activation_id or activation_id in activation_index:
            raise ValueError("micro activation IDs must be non-empty and unique")
        row_hash = _sha(
            activation.get("scanner_record_content_sha256"),
            "activation scanner record hash",
        )
        row = by_hash.get(row_hash)
        if row is None:
            raise ValueError("micro activation does not bind an exact scanner row")
        if row.get("symbol") != activation.get("symbol"):
            raise ValueError("micro activation scanner symbol changed")
        if row.get("decision_time") != activation.get("candidate_qualified_at"):
            raise ValueError("micro activation scanner time changed")
        profiles = tuple(
            str(value)
            for value in _list(
                activation.get("eligible_strategy_profile_ids"),
                "activation eligible profiles",
            )
        )
        for _account, (_account_class, profile_id, profile) in (
            _ACCOUNT_CONFIGURATION.items()
        ):
            candidate = _candidate_from_row(row, profile)
            if (profile_id in profiles) != (
                candidate.quality is not CandidateQuality.REJECT
            ):
                raise ValueError("activation profile eligibility does not recompute")
            candidate_index[(activation_id, profile_id)] = candidate
        activation_index[activation_id] = activation
    return activation_index, candidate_index


def _decision_opportunities(
    decision_source: Mapping[str, object],
    micro_decisions: Sequence[Mapping[str, object]],
    activation_index: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    source_rows = validate_daily_decision_source(decision_source)
    micro_index: dict[tuple[str, str, int, str], Mapping[str, object]] = {}
    for row in micro_decisions:
        decision_ns = int(
            _aware(row.get("decision_at"), "micro decision_at")
            .astimezone(UTC)
            .timestamp()
            * 1_000_000_000
        )
        key = (
            str(row.get("activation_id", "")),
            str(row.get("plan_id", "")),
            decision_ns,
            str(row.get("micro_runtime_content_sha256", "")),
        )
        if key in micro_index:
            raise ValueError("micro decision identity is duplicated")
        micro_index[key] = row
    opportunities: list[dict[str, object]] = []
    for source in source_rows:
        key = (
            source.activation_id,
            source.plan_id,
            source.decision_ts_ns,
            source.micro_runtime_content_sha256,
        )
        micro = micro_index.get(key)
        if micro is None:
            raise ValueError("daily decision source does not bind an exact micro decision")
        activation = activation_index.get(source.activation_id)
        if activation is None:
            raise ValueError("daily decision source references an unknown activation")
        if source.symbol != micro.get("symbol"):
            raise ValueError("daily decision source micro symbol changed")
        profiles = tuple(source.eligible_strategy_profile_ids)
        if profiles != tuple(
            str(value)
            for value in _list(
                micro.get("eligible_strategy_profile_ids"),
                "micro eligible profiles",
            )
        ):
            raise ValueError("daily decision source profile union changed")
        opportunities.append(
            {
                "opportunity_id": source.opportunity_id,
                "activation_id": source.activation_id,
                "plan_id": source.plan_id,
                "symbol": source.symbol,
                "decision_ts_ns": source.decision_ts_ns,
                "decision_at": _iso_from_ns(source.decision_ts_ns),
                "eligible_strategy_profile_ids": profiles,
                "plan": dict(_mapping(micro.get("plan"), "micro plan")),
            }
        )
    return opportunities


def _capture_index(
    capture: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    validate_market_input_capture(capture)
    result: dict[str, Mapping[str, object]] = {}
    for raw in _list(capture.get("captures"), "market captures"):
        row = _mapping(raw, "market capture")
        opportunity_id = str(row.get("opportunity_id", ""))
        if not opportunity_id or opportunity_id in result:
            raise ValueError("market capture opportunity IDs must be unique")
        result[opportunity_id] = row
    return result


def _decision_quote(
    quotes: Sequence[TopOfBookEvent],
    decision_ts_ns: int,
) -> TopOfBookEvent | None:
    eligible = [
        quote
        for quote in quotes
        if decision_ts_ns - PRE_DECISION_QUOTE_NS
        <= quote.ts_recv_ns
        <= decision_ts_ns
    ]
    return eligible[-1] if eligible else None


def _execution_payload(outcome: ExecutionOutcome) -> dict[str, object]:
    return {
        "policy_id": outcome.policy.policy_id,
        "status": outcome.status.value,
        "arrival_ts_ns": outcome.arrival_ts_ns,
        "cancel_requested_ts_ns": outcome.cancel_requested_ts_ns,
        "cancel_ack_ts_ns": outcome.cancel_ack_ts_ns,
        "filled_quantity": outcome.filled_quantity,
        "unfilled_quantity": outcome.unfilled_quantity,
        "fill_ts_ns": outcome.fill_ts_ns,
        "fill_price": (
            None if outcome.fill_price is None else format(outcome.fill_price, "f")
        ),
        "quote_ts_recv_ns": outcome.quote_ts_recv_ns,
        "displayed_contra_size": outcome.displayed_contra_size,
        "spread": None if outcome.spread is None else format(outcome.spread, "f"),
        "reason": outcome.reason,
    }


def _attempt_template(opportunity: Mapping[str, object]) -> dict[str, object]:
    plan = _mapping(opportunity.get("plan"), "opportunity plan")
    pullback = plan.get("pullback_number")
    if pullback is not None:
        _integer(pullback, "plan.pullback_number", minimum=1)
    return {
        "opportunity_id": opportunity["opportunity_id"],
        "activation_id": opportunity["activation_id"],
        "plan_id": opportunity["plan_id"],
        "symbol": opportunity["symbol"],
        "decision_ts_ns": opportunity["decision_ts_ns"],
        "decision_at": opportunity["decision_at"],
        "pullback_number": pullback,
        "entry_result": "not_filled",
        "reason": None,
        "decision_reference_quote": None,
        "order": None,
        "execution": None,
        "ledger": None,
    }


def _compose_account_scenario(
    *,
    trading_date: str,
    account_key: str,
    account_snapshot: object,
    scenario_id: str,
    activations: Sequence[Mapping[str, object]],
    candidate_index: Mapping[tuple[str, str], CandidateSnapshot],
    opportunities: Sequence[Mapping[str, object]],
    capture: Mapping[str, object],
    captures: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    account_class, profile_id, _profile = _ACCOUNT_CONFIGURATION[account_key]
    policy, offset_ticks = _SCENARIOS[scenario_id]
    snapshot = account_snapshot
    constraints = materialize_account_constraints(
        paper_account_policy(account_class),
        account_id=str(snapshot.account_id),
        starting_equity=float(snapshot.starting_equity),
        starting_buying_power=float(snapshot.starting_buying_power),
    )
    ledger = CampaignPortfolioLedger(
        session_date=pd.Timestamp(trading_date).date(),
        constraints=constraints,
    )

    eligible: list[ScarceCapitalOpportunity] = []
    opportunity_by_id: dict[str, Mapping[str, object]] = {}
    for opportunity in opportunities:
        opportunity_id = str(opportunity["opportunity_id"])
        opportunity_by_id[opportunity_id] = opportunity
        if profile_id not in tuple(opportunity["eligible_strategy_profile_ids"]):
            continue
        activation_id = str(opportunity["activation_id"])
        eligible.append(
            ScarceCapitalOpportunity(
                opportunity_id=opportunity_id,
                account_id=str(snapshot.account_id),
                account_class=account_class,
                candidate_activation_id=activation_id,
                plan_id=str(opportunity["plan_id"]),
                execution_at=pd.Timestamp(str(opportunity["decision_at"])),
                candidate_snapshot=candidate_index[(activation_id, profile_id)],
            )
        )
    ordered = order_scarce_capital_opportunities(eligible)
    by_time: dict[int, list[ScarceCapitalOpportunity]] = defaultdict(list)
    for item in ordered:
        decision_ns = int(opportunity_by_id[item.opportunity_id]["decision_ts_ns"])
        by_time[decision_ns].append(item)

    attempts: list[dict[str, object]] = []
    attempts_by_id: dict[str, dict[str, object]] = {}
    executed_trades: list[ExecutedEquityTrade] = []
    pending: dict[str, object] | None = None

    def apply_pending_fill() -> None:
        nonlocal pending
        if pending is None or pending["fill_applied"] is True:
            return
        outcome = pending["outcome"]
        if not isinstance(outcome, ExecutionOutcome) or outcome.filled_quantity <= 0:
            return
        attempt = pending["attempt"]
        if not isinstance(attempt, MutableMapping):
            raise RuntimeError("pending attempt is not mutable")
        fill_price = outcome.fill_price
        fill_ts_ns = outcome.fill_ts_ns
        if fill_price is None or fill_ts_ns is None:
            raise RuntimeError("filled execution outcome lacks fill evidence")
        decision = ledger.apply_entry_fill(
            EntryFill(
                fill_id=str(pending["fill_id"]),
                activation_id=str(attempt["activation_id"]),
                plan_id=str(attempt["plan_id"]),
                symbol=str(attempt["symbol"]),
                filled_at=pd.Timestamp(fill_ts_ns, unit="ns", tz="UTC"),
                quantity=outcome.filled_quantity,
                reference_price=float(pending["reference_price"]),
                fill_price=float(fill_price),
                stop_price=float(pending["stop_price"]),
                role=pending["role"],
                execution_approved=True,
            )
        )
        attempt["ledger"] = {
            "accepted": decision.accepted,
            "reasons": list(decision.reasons),
            "campaign_id": decision.campaign_id,
            "remaining_buying_power_before": decision.remaining_buying_power_before,
            "remaining_buying_power_after": decision.remaining_buying_power_after,
        }
        if decision.accepted:
            attempt["entry_result"] = "filled"
            attempt["reason"] = "execution_fill_accepted_by_frozen_account_ledger"
            executed_trades.append(
                ExecutedEquityTrade(
                    side=OrderSide.BUY,
                    quantity=outcome.filled_quantity,
                    price=fill_price,
                )
            )
        else:
            attempt["entry_result"] = "not_filled"
            attempt["reason"] = "execution_fill_rejected_by_frozen_account_ledger"
        pending["fill_applied"] = True

    for decision_ns in sorted(by_time):
        if pending is not None:
            fill_ns = pending.get("fill_ts_ns")
            if isinstance(fill_ns, int) and fill_ns < decision_ns:
                apply_pending_fill()
            if int(pending["end_ts_ns"]) < decision_ns:
                pending = None

        group = by_time[decision_ns]
        for item in group:
            opportunity = opportunity_by_id[item.opportunity_id]
            ledger.record_plan_emission(
                PlanEmission(
                    activation_id=item.candidate_activation_id,
                    plan_id=item.plan_id,
                    symbol=str(opportunity["symbol"]),
                    emitted_at=pd.Timestamp(str(opportunity["decision_at"])),
                )
            )

        if pending is not None:
            fill_ns = pending.get("fill_ts_ns")
            if isinstance(fill_ns, int) and fill_ns == decision_ns:
                apply_pending_fill()
            if int(pending["end_ts_ns"]) <= decision_ns:
                pending = None

        for item in group:
            opportunity = opportunity_by_id[item.opportunity_id]
            attempt = _attempt_template(opportunity)
            attempts.append(attempt)
            attempts_by_id[item.opportunity_id] = attempt
            if pending is not None:
                attempt["reason"] = "one_inflight_entry_attempt_per_account"
                continue
            campaign = ledger.campaigns[item.candidate_activation_id]
            if (
                campaign.quantity == 0
                and ledger.open_campaign_count >= constraints.max_open_positions
            ):
                attempt["reason"] = "open_position_limit"
                continue
            if campaign.entry_fill_count >= constraints.max_entries_per_campaign:
                attempt["reason"] = "campaign_entry_limit"
                continue
            role = (
                EntryRole.STARTER
                if campaign.entry_fill_count == 0
                else EntryRole.ADD
                if campaign.quantity > 0
                else EntryRole.REENTRY
            )
            capture_row = captures[item.opportunity_id]
            quotes = top_of_book_events(capture, item.opportunity_id)
            if capture_row.get("capture_status") != "complete":
                attempt["entry_result"] = "unavailable"
                attempt["reason"] = str(capture_row.get("capture_status"))
                continue
            quote = _decision_quote(quotes, decision_ns)
            if quote is None:
                attempt["entry_result"] = "unavailable"
                attempt["reason"] = "no_causal_decision_reference_quote"
                continue
            attempt["decision_reference_quote"] = {
                "ts_recv_ns": quote.ts_recv_ns,
                "sequence": quote.sequence,
                "bid_price": format(quote.bid_price, "f"),
                "bid_size": quote.bid_size,
                "ask_price": format(quote.ask_price, "f"),
                "ask_size": quote.ask_size,
                "halted": quote.halted,
            }
            if quote.halted:
                attempt["reason"] = "symbol_halted_at_decision"
                continue
            limit_price = marketable_limit_price(
                quote.ask_price,
                side=OrderSide.BUY,
                offset_ticks=offset_ticks,
            )
            plan = _mapping(opportunity.get("plan"), "opportunity plan")
            stop_price = _number(
                plan.get("stop_price"),
                "plan.stop_price",
                positive=True,
            )
            if stop_price >= float(limit_price):
                attempt["reason"] = "stop_not_below_conservative_sizing_price"
                continue
            quantity = maximum_whole_share_quantity(
                ledger,
                activation_id=item.candidate_activation_id,
                fill_price=float(limit_price),
                stop_price=stop_price,
                role=role,
            )
            if quantity == 0:
                attempt["reason"] = "no_remaining_whole_share_capacity"
                continue
            order_id = "order-" + canonical_fingerprint(
                {
                    "contract_id": CONTRACT_ID,
                    "account_id": snapshot.account_id,
                    "scenario_id": scenario_id,
                    "opportunity_id": item.opportunity_id,
                    "quantity": quantity,
                    "limit_price": format(limit_price, "f"),
                }
            )
            order = MarketableLimitOrder(
                order_id=order_id,
                symbol=str(opportunity["symbol"]),
                side=OrderSide.BUY,
                quantity=quantity,
                decision_ts_ns=decision_ns,
                limit_price=limit_price,
            )
            outcome = simulate_marketable_limit_order(order, quotes, policy)
            attempt["order"] = {
                "order_id": order_id,
                "side": "buy",
                "quantity": quantity,
                "limit_price": format(limit_price, "f"),
                "role": role.value,
            }
            attempt["execution"] = _execution_payload(outcome)
            if outcome.status is ExecutionStatus.UNAVAILABLE_NO_FRESH_QUOTE:
                attempt["entry_result"] = "unavailable"
                attempt["reason"] = outcome.reason
            elif outcome.filled_quantity == 0:
                attempt["entry_result"] = "not_filled"
                attempt["reason"] = outcome.reason
            else:
                attempt["entry_result"] = "not_filled"
                attempt["reason"] = "execution_fill_pending_chronological_ledger"
            pending = {
                "attempt": attempt,
                "outcome": outcome,
                "fill_applied": False,
                "fill_ts_ns": outcome.fill_ts_ns,
                "end_ts_ns": outcome.cancel_ack_ts_ns,
                "fill_id": "fill-" + canonical_fingerprint(
                    {"order_id": order_id, "execution": attempt["execution"]}
                ),
                "reference_price": quote.ask_price,
                "stop_price": stop_price,
                "role": role,
            }

    if pending is not None:
        apply_pending_fill()

    symbols = sorted({str(activation["symbol"]) for activation in activations})
    candidate_rows: list[dict[str, object]] = []
    for symbol in symbols:
        symbol_activations = [
            activation
            for activation in activations
            if activation.get("symbol") == symbol
        ]
        qualified = any(
            profile_id
            in tuple(
                str(value)
                for value in _list(
                    activation.get("eligible_strategy_profile_ids"),
                    "activation profiles",
                )
            )
            for activation in symbol_activations
        )
        symbol_opportunities = [
            opportunity
            for opportunity in opportunities
            if opportunity.get("symbol") == symbol
            and profile_id in tuple(opportunity["eligible_strategy_profile_ids"])
        ]
        symbol_attempts = [
            attempts_by_id[str(opportunity["opportunity_id"])]
            for opportunity in symbol_opportunities
        ]
        fills = [
            attempt
            for attempt in symbol_attempts
            if attempt["entry_result"] == "filled"
        ]
        if fills:
            first = min(
                fills,
                key=lambda attempt: int(
                    _mapping(attempt["execution"], "execution")["fill_ts_ns"]
                ),
            )
            execution = _mapping(first["execution"], "execution")
            entry_status = "filled"
            first_entry_at = _iso_from_ns(int(execution["fill_ts_ns"]))
            first_entry_price = float(str(execution["fill_price"]))
            first_pullback = first["pullback_number"]
            exit_status = "open"
        elif not qualified:
            entry_status = "not_submitted"
            first_entry_at = None
            first_entry_price = None
            first_pullback = None
            exit_status = "not_applicable"
        elif any(attempt["entry_result"] == "unavailable" for attempt in symbol_attempts):
            entry_status = "unavailable"
            first_entry_at = None
            first_entry_price = None
            first_pullback = None
            exit_status = "unavailable"
        elif symbol_opportunities:
            entry_status = "not_filled"
            first_entry_at = None
            first_entry_price = None
            first_pullback = None
            exit_status = "not_applicable"
        else:
            entry_status = "not_submitted"
            first_entry_at = None
            first_entry_price = None
            first_pullback = None
            exit_status = "not_applicable"
        candidate_rows.append(
            {
                "trading_date": trading_date,
                "symbol": symbol,
                "account": account_key,
                "account_qualified": qualified,
                "plan_count": len(symbol_opportunities),
                "entry_status": entry_status,
                "first_entry_at": first_entry_at,
                "first_entry_price": first_entry_price,
                "first_entry_pullback_ordinal": first_pullback,
                "exit_status": exit_status,
                "first_exit_at": None,
                "first_exit_price": None,
                "exit_reason": None,
            }
        )

    fees = aggregate_daily_equity_fees(executed_trades)
    return {
        "account_id": snapshot.account_id,
        "account_class": account_class.value,
        "policy_id": constraints.policy_id,
        "strategy_profile_id": profile_id,
        "starting_equity": float(snapshot.starting_equity),
        "starting_buying_power": float(snapshot.starting_buying_power),
        "candidate_decisions": candidate_rows,
        "execution_attempts": attempts,
        "ledger_artifact": ledger.runtime_artifact(),
        "open_position_count": ledger.open_campaign_count,
        "unavailable_input_count": sum(
            attempt["entry_result"] == "unavailable" for attempt in attempts
        ),
        "closed_campaign_pnls": [],
        "fees": fees.as_strings(),
        "registered_fees": float(fees.total_charged),
    }


def _session_detail(
    *,
    trading_date: str,
    account_key: str,
    horizon: int,
    scenario_id: str,
    result: Mapping[str, object],
    frozen_inputs: Mapping[str, object],
) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object]]:
    intrinsic_decisions = []
    for raw in _list(result.get("candidate_decisions"), "candidate decisions"):
        row = dict(_mapping(raw, "candidate decision"))
        row["behavioral_horizon_seconds"] = horizon
        row["execution_scenario_id"] = scenario_id
        intrinsic_decisions.append(row)
    intrinsic_performance = {
        "trading_date": trading_date,
        "account": account_key,
        "behavioral_horizon_seconds": horizon,
        "execution_scenario_id": scenario_id,
        "starting_equity": result["starting_equity"],
        "runtime_complete": True,
        "open_position_count": result["open_position_count"],
        "unavailable_input_count": result["unavailable_input_count"],
        "closed_campaign_pnls": result["closed_campaign_pnls"],
        "registered_fees": result["registered_fees"],
    }
    detail: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "prospective_account_runtime_session_cell",
        "contract_id": CONTRACT_ID,
        "contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "panel_id": PANEL_ID,
        "trading_date": trading_date,
        "account": account_key,
        "account_id": result["account_id"],
        "account_class": result["account_class"],
        "policy_id": result["policy_id"],
        "strategy_profile_id": result["strategy_profile_id"],
        "behavioral_horizon_seconds": horizon,
        "execution_scenario_id": scenario_id,
        "behavioral_horizon_runtime_role": (
            "equal_report_identity_only_no_per_opportunity_modifier"
        ),
        "frozen_inputs": dict(frozen_inputs),
        "candidate_decisions": intrinsic_decisions,
        "execution_attempts": result["execution_attempts"],
        "ledger_artifact": result["ledger_artifact"],
        "fees": result["fees"],
        "performance": intrinsic_performance,
        "management_status": "open_unresolved_no_one_minute_management_inputs",
        "runtime_complete": True,
        "retrospective_labels_loaded": False,
        "later_prices_or_pnl_loaded": False,
        "raw_transcript_text_persisted": False,
        "broker_order_submitted": False,
        "paper_order_submitted": False,
        "live_order_submitted": False,
        "best_cell_selected": False,
        "policy_promotion_eligible": False,
        "profitability_claim_eligible": False,
        "ross_replication_claim_eligible": False,
    }
    detail["content_sha256"] = canonical_fingerprint(detail)
    session_hash = str(detail["content_sha256"])
    decisions = [
        RuntimeDecision.from_mapping(
            {**row, "runtime_content_sha256": session_hash}
        ).as_dict()
        for row in intrinsic_decisions
    ]
    performance = AccountSessionPerformance.from_mapping(
        {**intrinsic_performance, "runtime_content_sha256": session_hash}
    ).as_dict()
    return detail, decisions, performance


def build_daily_account_runtime(
    contract: Mapping[str, object],
    *,
    scanner_runtime: Mapping[str, object],
    micro_runtime: Mapping[str, object],
    decision_source: Mapping[str, object],
    producer_manifest: Mapping[str, object],
    opportunity_freeze_contract: Mapping[str, object],
    market_input_contract: Mapping[str, object],
    opportunity_manifest: Mapping[str, object],
    request_manifest: Mapping[str, object],
    freeze_manifest: Mapping[str, object],
    market_input_capture: Mapping[str, object],
    account_manifest: Mapping[str, object],
    account_snapshots: Mapping[str, Mapping[str, object]],
    runtime_frozen_at: str | datetime,
) -> dict[str, object]:
    """Build one date's twelve label-blind account/session cells."""

    validate_daily_runtime_contract(contract)
    activations, micro_decisions = _validate_source_bundle(
        scanner_runtime,
        micro_runtime,
        decision_source,
        producer_manifest,
    )
    validate_freeze_manifest(
        freeze_manifest,
        contract=opportunity_freeze_contract,
        market_input_contract=market_input_contract,
        source=decision_source,
        opportunity_manifest=opportunity_manifest,
        request_manifest=request_manifest,
    )
    validate_market_input_capture(market_input_capture)
    validate_account_bundle(account_manifest, account_snapshots)

    trading_date = str(decision_source.get("trading_date", ""))
    if trading_date not in REGISTERED_DATES:
        raise ValueError("daily runtime trading date is not registered")
    for field, value in (
        ("scanner runtime", scanner_runtime.get("trading_date")),
        ("micro runtime", micro_runtime.get("trading_date")),
        ("producer manifest", producer_manifest.get("trading_date")),
        ("freeze manifest", freeze_manifest.get("trading_date")),
        ("account manifest", account_manifest.get("session_date")),
    ):
        if value != trading_date:
            raise ValueError(f"{field} trading date differs from daily runtime")
    if account_manifest.get("mode") != "capture":
        raise ValueError("daily runtime requires a registered account capture bundle")
    if set(account_snapshots) != {"main", "small"}:
        raise ValueError("daily runtime requires exact main and small snapshots")
    parsed_snapshots = {
        key: validate_snapshot_artifact(value)
        for key, value in account_snapshots.items()
    }
    if any(snapshot.session_date.isoformat() != trading_date for snapshot in parsed_snapshots.values()):
        raise ValueError("account snapshot date differs from daily runtime")

    if market_input_capture.get("opportunity_manifest_content_sha256") != (
        opportunity_manifest.get("content_sha256")
    ):
        raise ValueError("market input capture does not bind opportunity manifest")
    if market_input_capture.get("request_manifest_content_sha256") != (
        request_manifest.get("content_sha256")
    ):
        raise ValueError("market input capture does not bind request manifest")
    opportunity_ids = {
        str(_mapping(row, "opportunity").get("opportunity_id", ""))
        for row in _list(opportunity_manifest.get("opportunities"), "opportunities")
    }
    captures = _capture_index(market_input_capture)
    if set(captures) != opportunity_ids:
        raise ValueError("market capture must cover every frozen opportunity exactly")

    activation_index, candidate_index = _activation_candidates(
        scanner_runtime,
        activations,
    )
    opportunities = _decision_opportunities(
        decision_source,
        micro_decisions,
        activation_index,
    )
    if {str(row["opportunity_id"]) for row in opportunities} != opportunity_ids:
        raise ValueError("runtime opportunity identity differs from frozen manifest")

    frozen_datetime = _aware(runtime_frozen_at, "runtime_frozen_at").astimezone(UTC)
    causal_completion_times = [
        _aware(account_manifest.get("bundle_completed_at"), "bundle_completed_at")
        .astimezone(UTC)
    ]
    causal_completion_times.extend(
        datetime.fromtimestamp(
            _integer(row.get("window_end_ns"), "capture window_end_ns", minimum=1)
            / 1_000_000_000,
            tz=UTC,
        )
        for row in captures.values()
    )
    if frozen_datetime < max(causal_completion_times):
        raise ValueError("runtime_frozen_at precedes completion of a causal parent")
    frozen_at = frozen_datetime.isoformat()
    frozen_inputs = {
        "scanner_runtime_content_sha256": _validate_hash(
            scanner_runtime, "scanner runtime"
        ),
        "micro_runtime_content_sha256": _validate_hash(
            micro_runtime, "micro runtime"
        ),
        "decision_source_content_sha256": _validate_hash(
            decision_source, "decision source"
        ),
        "producer_manifest_content_sha256": _validate_hash(
            producer_manifest, "producer manifest"
        ),
        "opportunity_manifest_content_sha256": _validate_hash(
            opportunity_manifest, "opportunity manifest"
        ),
        "request_manifest_content_sha256": _validate_hash(
            request_manifest, "request manifest"
        ),
        "freeze_manifest_content_sha256": _validate_hash(
            freeze_manifest, "freeze manifest"
        ),
        "market_input_capture_content_sha256": _validate_hash(
            market_input_capture, "market input capture"
        ),
        "account_manifest_content_sha256": _validate_hash(
            account_manifest, "account manifest"
        ),
        "main_snapshot_content_sha256": _validate_hash(
            account_snapshots["main"], "main snapshot"
        ),
        "small_snapshot_content_sha256": _validate_hash(
            account_snapshots["small"], "small snapshot"
        ),
    }

    scenario_results: dict[tuple[str, str], dict[str, object]] = {}
    for scenario_id in _SCENARIOS:
        for account_key, (account_class, _profile_id, _profile) in (
            _ACCOUNT_CONFIGURATION.items()
        ):
            scenario_results[(scenario_id, account_key)] = _compose_account_scenario(
                trading_date=trading_date,
                account_key=account_key,
                account_snapshot=parsed_snapshots[account_class.value],
                scenario_id=scenario_id,
                activations=activations,
                candidate_index=candidate_index,
                opportunities=opportunities,
                capture=market_input_capture,
                captures=captures,
            )

    details: list[dict[str, object]] = []
    decisions: list[dict[str, object]] = []
    sessions: list[dict[str, object]] = []
    for horizon, scenario_id in registered_cells():
        for account_key in ACCOUNT_KEYS:
            detail, projected_decisions, performance = _session_detail(
                trading_date=trading_date,
                account_key=account_key,
                horizon=horizon,
                scenario_id=scenario_id,
                result=scenario_results[(scenario_id, account_key)],
                frozen_inputs=frozen_inputs,
            )
            details.append(detail)
            decisions.extend(projected_decisions)
            sessions.append(performance)

    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": f"prospective-daily-account-runtime-{trading_date}",
        "artifact_type": ARTIFACT_TYPE,
        "contract_id": CONTRACT_ID,
        "contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "evaluation_contract_content_sha256": EVALUATION_CONTRACT_CONTENT_SHA256,
        "panel_id": PANEL_ID,
        "trading_date": trading_date,
        "runtime_frozen_at": frozen_at,
        "runtime_frozen_before_retrospective_review": True,
        "retrospective_review_started": False,
        "frozen_inputs": frozen_inputs,
        "candidate_symbol_count": len({str(row["symbol"]) for row in activations}),
        "opportunity_count": len(opportunities),
        "session_count": len(details),
        "decision_count": len(decisions),
        "session_details": details,
        "decisions": decisions,
        "sessions": sessions,
        "management_input_status": "unavailable_beyond_550ms_entries_remain_open",
        "runtime_strategy_effect": "none",
        "retrospective_labels_loaded": False,
        "later_prices_or_pnl_loaded": False,
        "raw_transcript_text_persisted": False,
        "provider_call_made": False,
        "provider_credential_loaded": False,
        "broker_credential_loaded": False,
        "broker_order_submitted": False,
        "paper_order_submitted": False,
        "live_order_submitted": False,
        "best_cell_selected": False,
        "policy_promotion_eligible": False,
        "profitability_claim_eligible": False,
        "ross_replication_claim_eligible": False,
    }
    report["content_sha256"] = canonical_fingerprint(report)
    validate_daily_account_runtime(report)
    return report


def validate_daily_account_runtime(payload: Mapping[str, object]) -> None:
    if _walk_keys(payload) & _FORBIDDEN_RUNTIME_KEYS:
        raise ValueError("daily account runtime contains retrospective label keys")
    expected_fields = {
        "schema_version",
        "artifact_id",
        "artifact_type",
        "contract_id",
        "contract_content_sha256",
        "evaluation_contract_content_sha256",
        "panel_id",
        "trading_date",
        "runtime_frozen_at",
        "runtime_frozen_before_retrospective_review",
        "retrospective_review_started",
        "frozen_inputs",
        "candidate_symbol_count",
        "opportunity_count",
        "session_count",
        "decision_count",
        "session_details",
        "decisions",
        "sessions",
        "management_input_status",
        "runtime_strategy_effect",
        "retrospective_labels_loaded",
        "later_prices_or_pnl_loaded",
        "raw_transcript_text_persisted",
        "provider_call_made",
        "provider_credential_loaded",
        "broker_credential_loaded",
        "broker_order_submitted",
        "paper_order_submitted",
        "live_order_submitted",
        "best_cell_selected",
        "policy_promotion_eligible",
        "profitability_claim_eligible",
        "ross_replication_claim_eligible",
        "content_sha256",
    }
    if set(payload) != expected_fields:
        raise ValueError("daily account runtime fields changed")
    expected_scalars = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "contract_id": CONTRACT_ID,
        "contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "evaluation_contract_content_sha256": EVALUATION_CONTRACT_CONTENT_SHA256,
        "panel_id": PANEL_ID,
        "runtime_frozen_before_retrospective_review": True,
        "retrospective_review_started": False,
        "management_input_status": "unavailable_beyond_550ms_entries_remain_open",
        "runtime_strategy_effect": "none",
    }
    for field, expected in expected_scalars.items():
        if payload.get(field) != expected:
            raise ValueError(f"daily account runtime {field} changed")
    trading_date = str(payload.get("trading_date", ""))
    if trading_date not in REGISTERED_DATES:
        raise ValueError("daily account runtime date is not registered")
    if payload.get("artifact_id") != f"prospective-daily-account-runtime-{trading_date}":
        raise ValueError("daily account runtime artifact ID changed")
    _aware(payload.get("runtime_frozen_at"), "runtime_frozen_at")
    for field in (
        "retrospective_labels_loaded",
        "later_prices_or_pnl_loaded",
        "raw_transcript_text_persisted",
        "provider_call_made",
        "provider_credential_loaded",
        "broker_credential_loaded",
        "broker_order_submitted",
        "paper_order_submitted",
        "live_order_submitted",
        "best_cell_selected",
        "policy_promotion_eligible",
        "profitability_claim_eligible",
        "ross_replication_claim_eligible",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"daily account runtime boundary changed at {field}")
    _validate_hash(payload, "daily account runtime")
    frozen_inputs = _mapping(payload.get("frozen_inputs"), "frozen_inputs")
    expected_input_fields = {
        "scanner_runtime_content_sha256",
        "micro_runtime_content_sha256",
        "decision_source_content_sha256",
        "producer_manifest_content_sha256",
        "opportunity_manifest_content_sha256",
        "request_manifest_content_sha256",
        "freeze_manifest_content_sha256",
        "market_input_capture_content_sha256",
        "account_manifest_content_sha256",
        "main_snapshot_content_sha256",
        "small_snapshot_content_sha256",
    }
    if set(frozen_inputs) != expected_input_fields:
        raise ValueError("daily account runtime frozen input fields changed")
    for field in expected_input_fields:
        _sha(frozen_inputs.get(field), f"frozen_inputs.{field}")

    details = [
        _mapping(row, "session detail")
        for row in _list(payload.get("session_details"), "session details")
    ]
    expected_keys = {
        (horizon, scenario, account)
        for horizon, scenario in registered_cells()
        for account in ACCOUNT_KEYS
    }
    actual_keys = {
        (
            _integer(row.get("behavioral_horizon_seconds"), "detail horizon"),
            str(row.get("execution_scenario_id", "")),
            str(row.get("account", "")),
        )
        for row in details
    }
    if len(details) != 12 or actual_keys != expected_keys:
        raise ValueError("daily account runtime must contain every account/cell once")
    if payload.get("session_count") != 12:
        raise ValueError("daily account runtime session count changed")

    expected_decisions: list[dict[str, object]] = []
    expected_sessions: list[dict[str, object]] = []
    candidate_sets: list[set[str]] = []
    for detail in details:
        expected_detail_fields = {
            "schema_version",
            "artifact_type",
            "contract_id",
            "contract_content_sha256",
            "panel_id",
            "trading_date",
            "account",
            "account_id",
            "account_class",
            "policy_id",
            "strategy_profile_id",
            "behavioral_horizon_seconds",
            "execution_scenario_id",
            "behavioral_horizon_runtime_role",
            "frozen_inputs",
            "candidate_decisions",
            "execution_attempts",
            "ledger_artifact",
            "fees",
            "performance",
            "management_status",
            "runtime_complete",
            "retrospective_labels_loaded",
            "later_prices_or_pnl_loaded",
            "raw_transcript_text_persisted",
            "broker_order_submitted",
            "paper_order_submitted",
            "live_order_submitted",
            "best_cell_selected",
            "policy_promotion_eligible",
            "profitability_claim_eligible",
            "ross_replication_claim_eligible",
            "content_sha256",
        }
        if set(detail) != expected_detail_fields:
            raise ValueError("session detail fields changed")
        session_hash = _validate_hash(detail, "session detail")
        expected_detail_scalars = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "prospective_account_runtime_session_cell",
            "contract_id": CONTRACT_ID,
            "contract_content_sha256": CONTRACT_CONTENT_SHA256,
            "panel_id": PANEL_ID,
            "behavioral_horizon_runtime_role": (
                "equal_report_identity_only_no_per_opportunity_modifier"
            ),
            "runtime_complete": True,
        }
        for field, expected in expected_detail_scalars.items():
            if detail.get(field) != expected:
                raise ValueError(f"session detail {field} changed")
        for field in (
            "retrospective_labels_loaded",
            "later_prices_or_pnl_loaded",
            "raw_transcript_text_persisted",
            "broker_order_submitted",
            "paper_order_submitted",
            "live_order_submitted",
            "best_cell_selected",
            "policy_promotion_eligible",
            "profitability_claim_eligible",
            "ross_replication_claim_eligible",
        ):
            if detail.get(field) is not False:
                raise ValueError(f"session detail boundary changed at {field}")
        if detail.get("frozen_inputs") != frozen_inputs:
            raise ValueError("session detail frozen inputs differ from daily runtime")
        if detail.get("trading_date") != trading_date:
            raise ValueError("session detail date changed")
        horizon = _integer(
            detail.get("behavioral_horizon_seconds"),
            "session detail horizon",
        )
        scenario = str(detail.get("execution_scenario_id", ""))
        account = str(detail.get("account", ""))
        intrinsic = [
            _mapping(row, "intrinsic decision")
            for row in _list(detail.get("candidate_decisions"), "candidate decisions")
        ]
        candidate_sets.append({str(row.get("symbol", "")) for row in intrinsic})
        for row in intrinsic:
            if row.get("behavioral_horizon_seconds") != horizon:
                raise ValueError("intrinsic decision horizon changed")
            if row.get("execution_scenario_id") != scenario:
                raise ValueError("intrinsic decision scenario changed")
            if row.get("account") != account:
                raise ValueError("intrinsic decision account changed")
            expected_decisions.append(
                RuntimeDecision.from_mapping(
                    {**dict(row), "runtime_content_sha256": session_hash}
                ).as_dict()
            )
        performance = _mapping(detail.get("performance"), "session performance")
        if performance.get("runtime_complete") is not True:
            raise ValueError("validated parent chain requires runtime_complete")
        expected_sessions.append(
            AccountSessionPerformance.from_mapping(
                {**dict(performance), "runtime_content_sha256": session_hash}
            ).as_dict()
        )
        if detail.get("management_status") != (
            "open_unresolved_no_one_minute_management_inputs"
        ):
            raise ValueError("session detail management status changed")
    if candidate_sets and any(value != candidate_sets[0] for value in candidate_sets[1:]):
        raise ValueError("all daily account cells must retain identical candidates")

    supplied_decisions = [
        dict(_mapping(row, "runtime decision"))
        for row in _list(payload.get("decisions"), "runtime decisions")
    ]
    supplied_sessions = [
        dict(_mapping(row, "runtime session"))
        for row in _list(payload.get("sessions"), "runtime sessions")
    ]
    if supplied_decisions != expected_decisions:
        raise ValueError("daily projected decisions differ from session details")
    if supplied_sessions != expected_sessions:
        raise ValueError("daily projected sessions differ from session details")
    if payload.get("decision_count") != len(expected_decisions):
        raise ValueError("daily account runtime decision count changed")
    expected_candidate_count = len(candidate_sets[0]) if candidate_sets else 0
    if payload.get("candidate_symbol_count") != expected_candidate_count:
        raise ValueError("daily account runtime candidate count changed")


def write_daily_account_runtime(
    output_dir: str | Path,
    payload: Mapping[str, object],
) -> Path:
    validate_daily_account_runtime(payload)
    target = Path(output_dir)
    if target.exists():
        if not target.is_dir() or any(target.iterdir()):
            raise FileExistsError("daily runtime output must be absent or empty")
    else:
        target.mkdir(parents=True)
    output = target / OUTPUT_FILE
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return output


def load_json_object(path: str | Path, field: str) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{field} root must be an object")
    return payload


def load_daily_account_runtime(path: str | Path) -> dict[str, object]:
    source = Path(path)
    if source.is_dir():
        source = source / OUTPUT_FILE
    payload = load_json_object(source, "daily account runtime")
    validate_daily_account_runtime(payload)
    return payload


def load_parent_directories(
    *,
    source_dir: str | Path,
    freeze_dir: str | Path,
    market_input_dir: str | Path,
    account_dir: str | Path,
) -> dict[str, object]:
    source = Path(source_dir)
    freeze = Path(freeze_dir)
    market = Path(market_input_dir)
    account = Path(account_dir)
    return {
        "scanner_runtime": load_json_object(source / SCANNER_FILE, "scanner runtime"),
        "micro_runtime": load_json_object(source / MICRO_FILE, "micro runtime"),
        "decision_source": load_json_object(source / SOURCE_FILE, "decision source"),
        "producer_manifest": load_json_object(
            source / SOURCE_MANIFEST_FILE,
            "producer manifest",
        ),
        "opportunity_manifest": load_json_object(
            freeze / OPPORTUNITY_FILE,
            "opportunity manifest",
        ),
        "request_manifest": load_json_object(
            freeze / REQUEST_FILE,
            "request manifest",
        ),
        "freeze_manifest": load_json_object(
            freeze / FREEZE_FILE,
            "freeze manifest",
        ),
        "market_input_capture": load_json_object(
            market / "market-input-capture.json",
            "market input capture",
        ),
        "account_manifest": load_json_object(account / "manifest.json", "account manifest"),
        "account_snapshots": {
            "main": load_json_object(account / "main.json", "main snapshot"),
            "small": load_json_object(account / "small.json", "small snapshot"),
        },
    }


def load_default_parent_contracts(root: str | Path) -> tuple[dict[str, object], dict[str, object]]:
    base = Path(root)
    opportunity_contract = load_opportunity_freeze_contract(
        base / "research" / "strategy" / "prospective-opportunity-freeze-v0.1.json"
    )
    market_contract = load_capture_contract(
        base / "research" / "strategy" / "prospective-market-input-capture-v0.1.json"
    )
    return opportunity_contract, market_contract
