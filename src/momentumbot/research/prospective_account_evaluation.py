"""Preregistered component and portfolio evaluation for the prospective panel.

The evaluator is deliberately downstream of a frozen label-blind runtime.  It
joins normalized runtime rows to separately frozen retrospective account labels
and reports acquisition, participation, entry, exit, and portfolio components
without producing a weighted imitation score or selecting an execution cell.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import fmean
from typing import Mapping, Sequence

from momentumbot.research.account_chronological_integration import (
    MICRO_POLICY_FINGERPRINT,
    PANEL_ID,
    REGISTERED_DATES,
)
from momentumbot.research.execution_realism import (
    BASELINE_CONSERVATIVE_POLICY,
    CONTRACT_CONTENT_SHA256 as EXECUTION_CONTRACT_CONTENT_SHA256,
    STRESS_POLICY,
)


SCHEMA_VERSION = 1
CONTRACT_ID = "prospective-account-evaluation-v0.1"
CONTRACT_CONTENT_SHA256 = (
    "537287a04f35d81d8104f67a02cdcd352ee880cc8703fd8b8a61c68d971d5d5c"
)
REPORT_ID = "prospective-account-evaluation-report-v0.1"
REGISTRATION_DATE = "2026-08-22"
CONTRACT_ARTIFACT_TYPE = "preregistered_prospective_account_evaluation"
RUNTIME_ARTIFACT_TYPE = "prospective_account_runtime_evaluation_input"
LABELS_ARTIFACT_TYPE = "prospective_account_retrospective_labels"
REPORT_ARTIFACT_TYPE = (
    "retrospective_component_and_conditional_portfolio_evaluation"
)
ACCOUNT_INTEGRATION_CONTENT_SHA256 = (
    "64489aa27fec5eaf8ca12c94f4aeb47344d49a79b14df1bdda706cd23cc9ce73"
)
BEHAVIORAL_HORIZONS_SECONDS = (1, 5, 10)
EXECUTION_SCENARIOS = (
    BASELINE_CONSERVATIVE_POLICY.policy_id,
    STRESS_POLICY.policy_id,
)
ACCOUNT_KEYS = ("main_account", "small_account")
HUMAN_ACTION_STATES = (
    "participated",
    "explicitly_skipped_or_rejected",
    "discussed_but_action_unclear",
    "not_mentioned_or_unobservable",
    "source_unavailable",
)
ENTRY_STATUSES = ("filled", "not_filled", "not_submitted", "unavailable")
EXIT_STATUSES = ("closed", "open", "not_applicable", "unavailable")

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
_PROHIBITED_REPORT_KEYS = {
    "aggregate_imitation_score",
    "best_cell",
    "best_cell_id",
    "best_horizon",
    "best_horizon_seconds",
    "best_scenario",
    "best_scenario_id",
    "cell_rank",
    "cell_score",
    "imitation_score",
    "overall_imitation_score",
    "overall_score",
    "ranking",
    "selected_cell",
    "selected_execution_scenario",
    "selected_horizon",
    "selected_scenario",
    "weighted_imitation_score",
}


def canonical_fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _freeze(payload: Mapping[str, object]) -> dict[str, object]:
    result = dict(payload)
    result["content_sha256"] = canonical_fingerprint(payload)
    return result


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a list")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return value


def _finite(value: object, field: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        qualifier = "positive" if positive else "finite"
        raise ValueError(f"{field} must be {qualifier}")
    return result


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _positive_int(value: object, field: str) -> int:
    result = _nonnegative_int(value, field)
    if result == 0:
        raise ValueError(f"{field} must be positive")
    return result


def _aware_iso(value: object, field: str) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field} must be ISO 8601") from exc
    else:
        raise ValueError(f"{field} must be an aware ISO 8601 timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.isoformat()


def _optional_aware_iso(value: object, field: str) -> str | None:
    return None if value is None else _aware_iso(value, field)


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


def _cell_id(horizon_seconds: int, scenario_id: str) -> str:
    return f"h{horizon_seconds}s::{scenario_id}"


def registered_cells() -> tuple[tuple[int, str], ...]:
    return tuple(
        (horizon, scenario)
        for horizon in BEHAVIORAL_HORIZONS_SECONDS
        for scenario in EXECUTION_SCENARIOS
    )


def _metric_registry() -> dict[str, object]:
    return {
        "candidate_acquisition": [
            "observed_completed_trade_count",
            "acquisition_evaluable_completed_trade_count",
            "acquired_completed_trade_count",
            "descriptive_acquisition_fraction",
        ],
        "account_participation": [
            "account_qualified_human_trade_count",
            "fill_evaluable_acquired_human_trade_count",
            "bot_fill_on_human_trade_count",
            "bot_fill_on_explicit_skip_count",
            "descriptive_trade_skip_agreement_fraction",
        ],
        "entry_alignment": [
            "all_reported_reference_time_deltas_seconds",
            "all_reported_reference_price_differences",
            "pullback_ordinal_match_when_both_known",
        ],
        "exit_alignment": [
            "all_reported_reference_time_deltas_seconds",
            "all_reported_reference_price_differences",
            "exact_reason_match_when_both_known",
        ],
        "activity": [
            "runtime_candidate_count",
            "candidate_with_plan_count",
            "plan_emission_count",
            "filled_candidate_count",
            "closed_candidate_count",
            "unresolved_or_unavailable_count",
        ],
        "portfolio_if_complete": [
            "net_pnl_after_registered_fees",
            "net_return_fraction",
            "closed_campaign_win_rate",
            "gross_expectancy_per_closed_campaign",
            "gross_profit_factor",
            "gross_max_realized_drawdown",
        ],
        "aggregation_limits": {
            "unknown_actions_excluded_from_trade_skip_agreement": True,
            "unmentioned_candidates_are_not_skips": True,
            "incomplete_runtime_sessions_are_not_negative_decisions": True,
            "entry_and_exit_references_are_never_nearest_match_selected": True,
            "cells_reported_separately": True,
            "accounts_reported_separately": True,
            "best_cell_selection_allowed": False,
            "weighted_overall_imitation_score_allowed": False,
        },
    }


def _label_policy() -> dict[str, object]:
    return {
        "labels_opened_only_after_runtime_hash_freeze": True,
        "account_scoped": True,
        "completed_trade_required_for_participation": True,
        "unmentioned_candidate_is_not_a_skip": True,
        "attempted_order_without_fill_is_not_participation": True,
        "unknown_and_unavailable_excluded_from_trade_skip_agreement": True,
        "raw_transcript_text_persisted": False,
    }


def _portfolio_policy() -> dict[str, object]:
    return {
        "scope": "each_account_and_cell_reported_separately",
        "required_dates": list(REGISTERED_DATES),
        "every_session_runtime_complete_required": True,
        "zero_open_positions_required": True,
        "zero_unavailable_inputs_required": True,
        "ineligible_financial_fields": "null",
        "cross_cell_portfolio_aggregation_allowed": False,
        "best_cell_selection_allowed": False,
    }


def _contract_authority_boundary() -> dict[str, object]:
    return {
        "runtime_strategy_effect": "none",
        "metric_or_threshold_selection_authorized": False,
        "best_cell_selection_authorized": False,
        "policy_promotion_eligible": False,
        "profitability_claim_eligible": False,
        "ross_replication_claim_eligible": False,
        "paper_order_authorized": False,
        "live_order_authorized": False,
        "provider_call_authorized": False,
    }


def _report_authority_boundary() -> dict[str, object]:
    return {
        "runtime_strategy_effect": "none",
        "best_cell_selection_allowed": False,
        "weighted_overall_imitation_score_allowed": False,
        "technical_rule_retuning_allowed": False,
        "policy_promotion_eligible": False,
        "profitability_claim_eligible": False,
        "ross_replication_claim_eligible": False,
        "paper_order_authorized": False,
        "live_order_authorized": False,
    }


def _runtime_parent_bindings() -> dict[str, object]:
    return {
        "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
        "account_integration_content_sha256": ACCOUNT_INTEGRATION_CONTENT_SHA256,
        "prospective_execution_content_sha256": EXECUTION_CONTRACT_CONTENT_SHA256,
    }


@dataclass(frozen=True, slots=True)
class RuntimeDecision:
    trading_date: str
    symbol: str
    account: str
    behavioral_horizon_seconds: int
    execution_scenario_id: str
    runtime_content_sha256: str
    account_qualified: bool
    plan_count: int
    entry_status: str
    first_entry_at: str | datetime | None = None
    first_entry_price: float | None = None
    first_entry_pullback_ordinal: int | None = None
    exit_status: str = "not_applicable"
    first_exit_at: str | datetime | None = None
    first_exit_price: float | None = None
    exit_reason: str | None = None

    def __post_init__(self) -> None:
        if self.trading_date not in REGISTERED_DATES:
            raise ValueError("runtime decision date is not registered")
        if _SYMBOL.fullmatch(self.symbol) is None:
            raise ValueError("runtime symbol must be canonical uppercase notation")
        if self.account not in ACCOUNT_KEYS:
            raise ValueError("runtime account is invalid")
        if (
            isinstance(self.behavioral_horizon_seconds, bool)
            or not isinstance(self.behavioral_horizon_seconds, int)
            or self.behavioral_horizon_seconds not in BEHAVIORAL_HORIZONS_SECONDS
        ):
            raise ValueError("runtime behavioral horizon is not registered")
        if self.execution_scenario_id not in EXECUTION_SCENARIOS:
            raise ValueError("runtime execution scenario is not registered")
        _sha(self.runtime_content_sha256, "runtime_content_sha256")
        if not isinstance(self.account_qualified, bool):
            raise ValueError("account_qualified must be boolean")
        _nonnegative_int(self.plan_count, "plan_count")
        if self.entry_status not in ENTRY_STATUSES:
            raise ValueError("runtime entry_status is invalid")
        if self.exit_status not in EXIT_STATUSES:
            raise ValueError("runtime exit_status is invalid")
        entry_at = _optional_aware_iso(self.first_entry_at, "first_entry_at")
        entry_price = (
            None
            if self.first_entry_price is None
            else _finite(self.first_entry_price, "first_entry_price", positive=True)
        )
        if (entry_at is None) != (entry_price is None):
            raise ValueError("runtime first-entry time and price must appear together")
        if self.entry_status == "filled":
            if entry_at is None or self.plan_count == 0:
                raise ValueError("filled runtime entry requires a plan, time, and price")
        elif entry_at is not None or self.first_entry_pullback_ordinal is not None:
            raise ValueError("nonfilled runtime entry cannot carry entry details")
        if self.entry_status == "not_filled" and self.plan_count == 0:
            raise ValueError("not_filled runtime entry requires at least one plan")
        if self.first_entry_pullback_ordinal is not None:
            _positive_int(
                self.first_entry_pullback_ordinal,
                "first_entry_pullback_ordinal",
            )
        if not self.account_qualified and (
            self.plan_count != 0 or self.entry_status not in {"not_submitted", "unavailable"}
        ):
            raise ValueError("unqualified runtime decision cannot plan or fill")

        exit_at = _optional_aware_iso(self.first_exit_at, "first_exit_at")
        exit_price = (
            None
            if self.first_exit_price is None
            else _finite(self.first_exit_price, "first_exit_price", positive=True)
        )
        if (exit_at is None) != (exit_price is None):
            raise ValueError("runtime first-exit time and price must appear together")
        if self.exit_status == "closed":
            if (
                self.entry_status != "filled"
                or exit_at is None
                or not isinstance(self.exit_reason, str)
                or not self.exit_reason.strip()
            ):
                raise ValueError("closed runtime decision requires filled entry and exit")
            if datetime.fromisoformat(exit_at) < datetime.fromisoformat(str(entry_at)):
                raise ValueError("runtime exit cannot precede entry")
        elif exit_at is not None or self.exit_reason is not None:
            raise ValueError("nonclosed runtime decision cannot carry exit details")
        if self.entry_status == "filled" and self.exit_status == "not_applicable":
            raise ValueError("filled runtime entry must be closed, open, or unavailable")
        if self.entry_status != "filled" and self.exit_status not in {
            "not_applicable",
            "unavailable",
        }:
            raise ValueError("nonfilled entry cannot have an open or closed exit")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> RuntimeDecision:
        return cls(
            trading_date=str(value.get("trading_date", "")),
            symbol=str(value.get("symbol", "")),
            account=str(value.get("account", "")),
            behavioral_horizon_seconds=value.get("behavioral_horizon_seconds"),  # type: ignore[arg-type]
            execution_scenario_id=str(value.get("execution_scenario_id", "")),
            runtime_content_sha256=str(value.get("runtime_content_sha256", "")),
            account_qualified=value.get("account_qualified"),  # type: ignore[arg-type]
            plan_count=value.get("plan_count"),  # type: ignore[arg-type]
            entry_status=str(value.get("entry_status", "")),
            first_entry_at=value.get("first_entry_at"),  # type: ignore[arg-type]
            first_entry_price=value.get("first_entry_price"),  # type: ignore[arg-type]
            first_entry_pullback_ordinal=value.get("first_entry_pullback_ordinal"),  # type: ignore[arg-type]
            exit_status=str(value.get("exit_status", "")),
            first_exit_at=value.get("first_exit_at"),  # type: ignore[arg-type]
            first_exit_price=value.get("first_exit_price"),  # type: ignore[arg-type]
            exit_reason=value.get("exit_reason"),  # type: ignore[arg-type]
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "trading_date": self.trading_date,
            "symbol": self.symbol,
            "account": self.account,
            "behavioral_horizon_seconds": self.behavioral_horizon_seconds,
            "execution_scenario_id": self.execution_scenario_id,
            "runtime_content_sha256": self.runtime_content_sha256,
            "account_qualified": self.account_qualified,
            "plan_count": self.plan_count,
            "entry_status": self.entry_status,
            "first_entry_at": _optional_aware_iso(
                self.first_entry_at,
                "first_entry_at",
            ),
            "first_entry_price": self.first_entry_price,
            "first_entry_pullback_ordinal": self.first_entry_pullback_ordinal,
            "exit_status": self.exit_status,
            "first_exit_at": _optional_aware_iso(self.first_exit_at, "first_exit_at"),
            "first_exit_price": self.first_exit_price,
            "exit_reason": self.exit_reason,
        }


@dataclass(frozen=True, slots=True)
class HumanDecision:
    trading_date: str
    symbol: str
    account: str
    human_state: str
    trade_completion: str
    evidence_content_sha256: str
    reported_entry_times: tuple[str | datetime, ...] = ()
    reported_entry_prices: tuple[float, ...] = ()
    reported_entry_pullback_ordinal: int | None = None
    reported_exit_times: tuple[str | datetime, ...] = ()
    reported_exit_prices: tuple[float, ...] = ()
    reported_exit_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.trading_date not in REGISTERED_DATES:
            raise ValueError("human decision date is not registered")
        if _SYMBOL.fullmatch(self.symbol) is None:
            raise ValueError("human decision symbol must be canonical uppercase notation")
        if self.account not in ACCOUNT_KEYS:
            raise ValueError("human decision account is invalid")
        if self.human_state not in HUMAN_ACTION_STATES:
            raise ValueError("human_state is invalid")
        _sha(self.evidence_content_sha256, "evidence_content_sha256")
        expected_completion = {
            "participated": {"completed_trade"},
            "explicitly_skipped_or_rejected": {"no_trade"},
            "discussed_but_action_unclear": {"attempted_no_fill", "unknown"},
            "not_mentioned_or_unobservable": {"unknown"},
            "source_unavailable": {"source_unavailable"},
        }[self.human_state]
        if self.trade_completion not in expected_completion:
            raise ValueError("human state and trade completion are inconsistent")
        for index, value in enumerate(self.reported_entry_times):
            _aware_iso(value, f"reported_entry_times[{index}]")
        for index, value in enumerate(self.reported_exit_times):
            _aware_iso(value, f"reported_exit_times[{index}]")
        for index, value in enumerate(self.reported_entry_prices):
            _finite(value, f"reported_entry_prices[{index}]", positive=True)
        for index, value in enumerate(self.reported_exit_prices):
            _finite(value, f"reported_exit_prices[{index}]", positive=True)
        if self.reported_entry_pullback_ordinal is not None:
            _positive_int(
                self.reported_entry_pullback_ordinal,
                "reported_entry_pullback_ordinal",
            )
        if any(
            not isinstance(reason, str) or not reason.strip()
            for reason in self.reported_exit_reasons
        ):
            raise ValueError("reported exit reasons must be non-empty")
        if self.human_state != "participated" and (
            self.reported_entry_times
            or self.reported_entry_prices
            or self.reported_entry_pullback_ordinal is not None
            or self.reported_exit_times
            or self.reported_exit_prices
            or self.reported_exit_reasons
        ):
            raise ValueError("nonparticipation label cannot carry completed-trade details")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> HumanDecision:
        return cls(
            trading_date=str(value.get("trading_date", "")),
            symbol=str(value.get("symbol", "")),
            account=str(value.get("account", "")),
            human_state=str(value.get("human_state", "")),
            trade_completion=str(value.get("trade_completion", "")),
            evidence_content_sha256=str(value.get("evidence_content_sha256", "")),
            reported_entry_times=tuple(
                _sequence(value.get("reported_entry_times", ()), "reported_entry_times")
            ),
            reported_entry_prices=tuple(
                _sequence(value.get("reported_entry_prices", ()), "reported_entry_prices")
            ),  # type: ignore[arg-type]
            reported_entry_pullback_ordinal=value.get("reported_entry_pullback_ordinal"),  # type: ignore[arg-type]
            reported_exit_times=tuple(
                _sequence(value.get("reported_exit_times", ()), "reported_exit_times")
            ),
            reported_exit_prices=tuple(
                _sequence(value.get("reported_exit_prices", ()), "reported_exit_prices")
            ),  # type: ignore[arg-type]
            reported_exit_reasons=tuple(  # type: ignore[arg-type]
                _sequence(
                    value.get("reported_exit_reasons", ()), "reported_exit_reasons"
                )
            ),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "trading_date": self.trading_date,
            "symbol": self.symbol,
            "account": self.account,
            "human_state": self.human_state,
            "trade_completion": self.trade_completion,
            "evidence_content_sha256": self.evidence_content_sha256,
            "reported_entry_times": [
                _aware_iso(value, "reported_entry_time")
                for value in self.reported_entry_times
            ],
            "reported_entry_prices": list(self.reported_entry_prices),
            "reported_entry_pullback_ordinal": self.reported_entry_pullback_ordinal,
            "reported_exit_times": [
                _aware_iso(value, "reported_exit_time")
                for value in self.reported_exit_times
            ],
            "reported_exit_prices": list(self.reported_exit_prices),
            "reported_exit_reasons": list(self.reported_exit_reasons),
        }


@dataclass(frozen=True, slots=True)
class AccountSessionPerformance:
    """One cell/account/date summary with gross campaign P&L in close order."""

    trading_date: str
    account: str
    behavioral_horizon_seconds: int
    execution_scenario_id: str
    runtime_content_sha256: str
    starting_equity: float
    runtime_complete: bool
    open_position_count: int
    unavailable_input_count: int
    closed_campaign_pnls: tuple[float, ...]
    registered_fees: float

    def __post_init__(self) -> None:
        if self.trading_date not in REGISTERED_DATES:
            raise ValueError("session performance date is not registered")
        if self.account not in ACCOUNT_KEYS:
            raise ValueError("session performance account is invalid")
        if (
            isinstance(self.behavioral_horizon_seconds, bool)
            or not isinstance(self.behavioral_horizon_seconds, int)
            or self.behavioral_horizon_seconds not in BEHAVIORAL_HORIZONS_SECONDS
        ):
            raise ValueError("session performance horizon is not registered")
        if self.execution_scenario_id not in EXECUTION_SCENARIOS:
            raise ValueError("session performance scenario is not registered")
        _sha(self.runtime_content_sha256, "runtime_content_sha256")
        _finite(self.starting_equity, "starting_equity", positive=True)
        if not isinstance(self.runtime_complete, bool):
            raise ValueError("runtime_complete must be boolean")
        _nonnegative_int(self.open_position_count, "open_position_count")
        _nonnegative_int(self.unavailable_input_count, "unavailable_input_count")
        for index, value in enumerate(self.closed_campaign_pnls):
            _finite(value, f"closed_campaign_pnls[{index}]")
        fees = _finite(self.registered_fees, "registered_fees")
        if fees < 0:
            raise ValueError("registered_fees cannot be negative")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> AccountSessionPerformance:
        return cls(
            trading_date=str(value.get("trading_date", "")),
            account=str(value.get("account", "")),
            behavioral_horizon_seconds=value.get("behavioral_horizon_seconds"),  # type: ignore[arg-type]
            execution_scenario_id=str(value.get("execution_scenario_id", "")),
            runtime_content_sha256=str(value.get("runtime_content_sha256", "")),
            starting_equity=value.get("starting_equity"),  # type: ignore[arg-type]
            runtime_complete=value.get("runtime_complete"),  # type: ignore[arg-type]
            open_position_count=value.get("open_position_count"),  # type: ignore[arg-type]
            unavailable_input_count=value.get("unavailable_input_count"),  # type: ignore[arg-type]
            closed_campaign_pnls=tuple(
                _sequence(value.get("closed_campaign_pnls", ()), "closed_campaign_pnls")
            ),  # type: ignore[arg-type]
            registered_fees=value.get("registered_fees"),  # type: ignore[arg-type]
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "trading_date": self.trading_date,
            "account": self.account,
            "behavioral_horizon_seconds": self.behavioral_horizon_seconds,
            "execution_scenario_id": self.execution_scenario_id,
            "runtime_content_sha256": self.runtime_content_sha256,
            "starting_equity": self.starting_equity,
            "runtime_complete": self.runtime_complete,
            "open_position_count": self.open_position_count,
            "unavailable_input_count": self.unavailable_input_count,
            "closed_campaign_pnls": list(self.closed_campaign_pnls),
            "registered_fees": self.registered_fees,
        }


def _runtime_key(row: RuntimeDecision) -> tuple[int, str, str, str, str]:
    return (
        row.behavioral_horizon_seconds,
        row.execution_scenario_id,
        row.trading_date,
        row.symbol,
        row.account,
    )


def _human_key(row: HumanDecision) -> tuple[str, str, str]:
    return (row.trading_date, row.symbol, row.account)


def _session_key(row: AccountSessionPerformance) -> tuple[int, str, str, str]:
    return (
        row.behavioral_horizon_seconds,
        row.execution_scenario_id,
        row.trading_date,
        row.account,
    )


def _validate_runtime_inputs(
    decisions: tuple[RuntimeDecision, ...],
    sessions: tuple[AccountSessionPerformance, ...],
) -> None:
    keys = [_runtime_key(row) for row in decisions]
    if len(keys) != len(set(keys)):
        raise ValueError("runtime decisions contain duplicate cell/account candidates")
    _validate_session_inputs(sessions)
    session_hashes = {
        _session_key(row): row.runtime_content_sha256 for row in sessions
    }
    for row in decisions:
        session_key = (
            row.behavioral_horizon_seconds,
            row.execution_scenario_id,
            row.trading_date,
            row.account,
        )
        if row.runtime_content_sha256 != session_hashes[session_key]:
            raise ValueError("runtime decision does not bind its account session")

    candidate_sets: dict[str, set[tuple[str, str, str]]] = {}
    for horizon, scenario in registered_cells():
        cell = _cell_id(horizon, scenario)
        candidate_sets[cell] = {
            (row.trading_date, row.symbol, row.account)
            for row in decisions
            if row.behavioral_horizon_seconds == horizon
            and row.execution_scenario_id == scenario
        }
    first = candidate_sets[_cell_id(*registered_cells()[0])]
    if any(value != first for value in candidate_sets.values()):
        raise ValueError("all registered cells must retain the identical candidate set")


def _validate_session_inputs(
    sessions: tuple[AccountSessionPerformance, ...],
) -> None:
    session_keys = [_session_key(row) for row in sessions]
    if len(session_keys) != len(set(session_keys)):
        raise ValueError("session performance contains duplicate cell/account dates")
    expected_sessions = {
        (horizon, scenario, trading_date, account)
        for horizon, scenario in registered_cells()
        for trading_date in REGISTERED_DATES
        for account in ACCOUNT_KEYS
    }
    if set(session_keys) != expected_sessions:
        raise ValueError("session performance must cover every date/account/cell")


def _validate_human_inputs(
    human: tuple[HumanDecision, ...],
    runtime: tuple[RuntimeDecision, ...],
) -> None:
    human_keys = [_human_key(row) for row in human]
    if len(human_keys) != len(set(human_keys)):
        raise ValueError("human decisions contain duplicate account-scoped labels")
    runtime_base = {
        (row.trading_date, row.symbol, row.account)
        for row in runtime
    }
    if not runtime_base.issubset(set(human_keys)):
        raise ValueError("retrospective labels must cover every runtime candidate")


def _time_differences(runtime_value: str, references: Sequence[object]) -> list[float]:
    runtime_at = datetime.fromisoformat(runtime_value)
    return [
        (runtime_at - datetime.fromisoformat(str(reference))).total_seconds()
        for reference in references
    ]


def _price_differences(runtime_value: float, references: Sequence[object]) -> list[dict[str, float]]:
    result: list[dict[str, float]] = []
    for raw in references:
        reference = float(raw)
        signed = runtime_value - reference
        result.append(
            {
                "reported_reference": reference,
                "signed_difference": signed,
                "absolute_difference": abs(signed),
                "absolute_percentage_difference": abs(signed) / reference,
            }
        )
    return result


def _entry_alignment(
    human: Mapping[str, object],
    runtime: Mapping[str, object] | None,
) -> dict[str, object] | None:
    if human.get("human_state") != "participated" or runtime is None:
        return None
    if runtime.get("entry_status") != "filled":
        return None
    runtime_at = str(runtime["first_entry_at"])
    runtime_price = float(runtime["first_entry_price"])
    reported_times = list(_sequence(human.get("reported_entry_times", ()), "entry times"))
    reported_prices = list(
        _sequence(human.get("reported_entry_prices", ()), "entry prices")
    )
    runtime_ordinal = runtime.get("first_entry_pullback_ordinal")
    human_ordinal = human.get("reported_entry_pullback_ordinal")
    ordinal_match = (
        runtime_ordinal == human_ordinal
        if runtime_ordinal is not None and human_ordinal is not None
        else None
    )
    return {
        "runtime_first_entry_at": runtime_at,
        "runtime_first_entry_price": runtime_price,
        "runtime_first_entry_pullback_ordinal": runtime_ordinal,
        "reported_entry_times": reported_times,
        "reported_entry_prices": reported_prices,
        "reported_entry_pullback_ordinal": human_ordinal,
        "all_time_deltas_seconds": _time_differences(runtime_at, reported_times),
        "all_price_differences": _price_differences(runtime_price, reported_prices),
        "pullback_ordinal_match": ordinal_match,
        "nearest_reference_selected": False,
    }


def _exit_alignment(
    human: Mapping[str, object],
    runtime: Mapping[str, object] | None,
) -> dict[str, object] | None:
    if human.get("human_state") != "participated" or runtime is None:
        return None
    if runtime.get("exit_status") != "closed":
        return None
    runtime_at = str(runtime["first_exit_at"])
    runtime_price = float(runtime["first_exit_price"])
    runtime_reason = str(runtime["exit_reason"])
    reported_times = list(_sequence(human.get("reported_exit_times", ()), "exit times"))
    reported_prices = list(
        _sequence(human.get("reported_exit_prices", ()), "exit prices")
    )
    reported_reasons = [
        str(value)
        for value in _sequence(human.get("reported_exit_reasons", ()), "exit reasons")
    ]
    return {
        "runtime_first_exit_at": runtime_at,
        "runtime_first_exit_price": runtime_price,
        "runtime_exit_reason": runtime_reason,
        "reported_exit_times": reported_times,
        "reported_exit_prices": reported_prices,
        "reported_exit_reasons": reported_reasons,
        "all_time_deltas_seconds": _time_differences(runtime_at, reported_times),
        "all_price_differences": _price_differences(runtime_price, reported_prices),
        "exact_reason_matches": [runtime_reason == value for value in reported_reasons],
        "nearest_reference_selected": False,
    }


def _relation(
    human_state: str,
    runtime: Mapping[str, object] | None,
    session_complete: bool,
) -> str:
    if human_state not in {"participated", "explicitly_skipped_or_rejected"}:
        return f"excluded_{human_state}"
    suffix = "human_trade" if human_state == "participated" else "human_skip"
    if not session_complete:
        return f"runtime_unavailable_on_{suffix}"
    if runtime is None:
        return (
            "not_acquired_human_trade"
            if human_state == "participated"
            else "no_bot_fill_on_human_skip"
        )
    if runtime.get("entry_status") == "unavailable":
        return f"runtime_unavailable_on_{suffix}"
    if runtime.get("entry_status") == "filled":
        return (
            "bot_fill_on_human_trade"
            if human_state == "participated"
            else "bot_fill_on_human_skip"
        )
    return (
        "no_bot_fill_on_human_trade"
        if human_state == "participated"
        else "no_bot_fill_on_human_skip"
    )


def _build_comparisons(
    runtime: tuple[RuntimeDecision, ...],
    human: tuple[HumanDecision, ...],
    sessions: tuple[AccountSessionPerformance, ...],
) -> list[dict[str, object]]:
    runtime_by_key = {_runtime_key(row): row.as_dict() for row in runtime}
    session_by_key = {_session_key(row): row for row in sessions}
    rows: list[dict[str, object]] = []
    for horizon, scenario in registered_cells():
        for label in human:
            runtime_row = runtime_by_key.get(
                (horizon, scenario, label.trading_date, label.symbol, label.account)
            )
            session = session_by_key[
                (horizon, scenario, label.trading_date, label.account)
            ]
            human_row = label.as_dict()
            rows.append(
                {
                    "cell_id": _cell_id(horizon, scenario),
                    "behavioral_horizon_seconds": horizon,
                    "execution_scenario_id": scenario,
                    "trading_date": label.trading_date,
                    "symbol": label.symbol,
                    "account": label.account,
                    "human": human_row,
                    "runtime": runtime_row,
                    "session_runtime_complete": session.runtime_complete,
                    "candidate_acquired": (
                        runtime_row is not None if session.runtime_complete else None
                    ),
                    "relation": _relation(
                        label.human_state,
                        runtime_row,
                        session.runtime_complete,
                    ),
                    "entry_alignment": _entry_alignment(human_row, runtime_row),
                    "exit_alignment": _exit_alignment(human_row, runtime_row),
                }
            )
    rows.sort(
        key=lambda row: (
            row["behavioral_horizon_seconds"],
            row["execution_scenario_id"],
            row["trading_date"],
            row["symbol"],
            row["account"],
        )
    )
    return rows


def _fraction(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _aggregate_comparisons(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for horizon, scenario in registered_cells():
        cell = _cell_id(horizon, scenario)
        cell_result: dict[str, object] = {}
        for account in ACCOUNT_KEYS:
            scoped = [
                row
                for row in rows
                if row.get("cell_id") == cell and row.get("account") == account
            ]
            states = Counter(
                str(_mapping(row.get("human"), "human").get("human_state"))
                for row in scoped
            )
            relations = Counter(str(row.get("relation")) for row in scoped)
            runtime_rows = [
                _mapping(row.get("runtime"), "runtime")
                for row in scoped
                if row.get("runtime") is not None
            ]
            human_trades = states["participated"]
            acquisition_evaluable_trades = sum(
                _mapping(row.get("human"), "human").get("human_state")
                == "participated"
                and row.get("session_runtime_complete") is True
                for row in scoped
            )
            acquired_trades = sum(
                _mapping(row.get("human"), "human").get("human_state")
                == "participated"
                and row.get("session_runtime_complete") is True
                and row.get("runtime") is not None
                for row in scoped
            )
            qualified_trades = sum(
                _mapping(row.get("human"), "human").get("human_state")
                == "participated"
                and row.get("session_runtime_complete") is True
                and row.get("runtime") is not None
                and _mapping(row.get("runtime"), "runtime").get("account_qualified")
                is True
                for row in scoped
            )
            bot_trade_fills = relations["bot_fill_on_human_trade"]
            fill_evaluable_acquired_trades = sum(
                _mapping(row.get("human"), "human").get("human_state")
                == "participated"
                and row.get("session_runtime_complete") is True
                and row.get("runtime") is not None
                and _mapping(row.get("runtime"), "runtime").get("entry_status")
                != "unavailable"
                for row in scoped
            )
            comparable = states["participated"] + states[
                "explicitly_skipped_or_rejected"
            ]
            unavailable = relations["runtime_unavailable_on_human_trade"] + relations[
                "runtime_unavailable_on_human_skip"
            ]
            evaluable = comparable - unavailable
            agreement = relations["bot_fill_on_human_trade"] + relations[
                "no_bot_fill_on_human_skip"
            ]
            cell_result[account] = {
                "human_state_counts": dict(sorted(states.items())),
                "relation_counts": dict(sorted(relations.items())),
                "observed_completed_trade_count": human_trades,
                "acquisition_evaluable_completed_trade_count": (
                    acquisition_evaluable_trades
                ),
                "acquired_completed_trade_count": acquired_trades,
                "descriptive_acquisition_fraction": _fraction(
                    acquired_trades,
                    acquisition_evaluable_trades,
                ),
                "account_qualified_human_trade_count": qualified_trades,
                "fill_evaluable_acquired_human_trade_count": (
                    fill_evaluable_acquired_trades
                ),
                "bot_fill_on_human_trade_count": bot_trade_fills,
                "descriptive_fill_fraction_of_acquired_human_trades": _fraction(
                    bot_trade_fills,
                    fill_evaluable_acquired_trades,
                ),
                "explicit_skip_count": states["explicitly_skipped_or_rejected"],
                "bot_fill_on_explicit_skip_count": relations[
                    "bot_fill_on_human_skip"
                ],
                "explicit_comparable_decision_count": comparable,
                "evaluable_trade_skip_decision_count": evaluable,
                "descriptive_trade_skip_agreement_count": agreement,
                "descriptive_trade_skip_agreement_fraction": _fraction(
                    agreement,
                    evaluable,
                ),
                "runtime_candidate_count": len(runtime_rows),
                "candidate_with_plan_count": sum(
                    int(row.get("plan_count", 0)) > 0 for row in runtime_rows
                ),
                "plan_emission_count": sum(
                    int(row.get("plan_count", 0)) for row in runtime_rows
                ),
                "filled_candidate_count": sum(
                    row.get("entry_status") == "filled" for row in runtime_rows
                ),
                "closed_candidate_count": sum(
                    row.get("exit_status") == "closed" for row in runtime_rows
                ),
                "unresolved_or_unavailable_count": sum(
                    row.get("exit_status") in {"open", "unavailable"}
                    or row.get("entry_status") == "unavailable"
                    for row in runtime_rows
                ),
                "entry_alignment_case_count": sum(
                    row.get("entry_alignment") is not None for row in scoped
                ),
                "exit_alignment_case_count": sum(
                    row.get("exit_alignment") is not None for row in scoped
                ),
            }
        result[cell] = cell_result
    return result


def _candidate_identity(
    runtime: tuple[RuntimeDecision, ...],
) -> dict[str, object]:
    by_cell: dict[str, object] = {}
    for horizon, scenario in registered_cells():
        rows = sorted(
            (row.trading_date, row.symbol, row.account)
            for row in runtime
            if row.behavioral_horizon_seconds == horizon
            and row.execution_scenario_id == scenario
        )
        by_cell[_cell_id(horizon, scenario)] = {
            "candidate_count": len(rows),
            "candidate_identity_sha256": canonical_fingerprint(rows),
        }
    digests = {
        _mapping(value, "candidate cell").get("candidate_identity_sha256")
        for value in by_cell.values()
    }
    return {
        "identical_candidate_set_across_all_cells": len(digests) == 1,
        "cells": by_cell,
    }


def _maximum_drawdown(pnls: Sequence[float]) -> float:
    equity = 0.0
    high = 0.0
    maximum = 0.0
    for pnl in pnls:
        equity += pnl
        high = max(high, equity)
        maximum = max(maximum, high - equity)
    return maximum


def _portfolio_metrics(
    sessions: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for horizon, scenario in registered_cells():
        cell = _cell_id(horizon, scenario)
        cell_result: dict[str, object] = {}
        for account in ACCOUNT_KEYS:
            scoped = sorted(
                (
                    row
                    for row in sessions
                    if row.get("behavioral_horizon_seconds") == horizon
                    and row.get("execution_scenario_id") == scenario
                    and row.get("account") == account
                ),
                key=lambda row: str(row.get("trading_date")),
            )
            present_dates = {str(row.get("trading_date")) for row in scoped}
            missing_dates = [date for date in REGISTERED_DATES if date not in present_dates]
            incomplete_dates = [
                str(row.get("trading_date"))
                for row in scoped
                if row.get("runtime_complete") is not True
            ]
            open_positions = sum(int(row.get("open_position_count", 0)) for row in scoped)
            unavailable_inputs = sum(
                int(row.get("unavailable_input_count", 0)) for row in scoped
            )
            eligible = (
                not missing_dates
                and not incomplete_dates
                and open_positions == 0
                and unavailable_inputs == 0
            )
            pnls = [
                float(value)
                for row in scoped
                for value in _sequence(
                    row.get("closed_campaign_pnls", ()),
                    "closed_campaign_pnls",
                )
            ]
            fees = sum(float(row.get("registered_fees", 0.0)) for row in scoped)
            financial: dict[str, object]
            if eligible:
                gains = sum(value for value in pnls if value > 0)
                losses = -sum(value for value in pnls if value < 0)
                gross = sum(pnls)
                starting = float(scoped[0]["starting_equity"])
                financial = {
                    "gross_realized_pnl": gross,
                    "registered_fees": fees,
                    "net_pnl_after_registered_fees": gross - fees,
                    "panel_starting_equity": starting,
                    "net_return_fraction": (gross - fees) / starting,
                    "closed_campaign_count": len(pnls),
                    "winning_campaign_count": sum(value > 0 for value in pnls),
                    "losing_campaign_count": sum(value < 0 for value in pnls),
                    "flat_campaign_count": sum(value == 0 for value in pnls),
                    "closed_campaign_win_rate": _fraction(
                        sum(value > 0 for value in pnls),
                        len(pnls),
                    ),
                    "gross_expectancy_per_closed_campaign": (
                        fmean(pnls) if pnls else None
                    ),
                    "gross_profit_factor": gains / losses if losses > 0 else None,
                    "gross_max_realized_drawdown": _maximum_drawdown(pnls),
                }
            else:
                financial = {
                    "gross_realized_pnl": None,
                    "registered_fees": None,
                    "net_pnl_after_registered_fees": None,
                    "panel_starting_equity": None,
                    "net_return_fraction": None,
                    "closed_campaign_count": None,
                    "winning_campaign_count": None,
                    "losing_campaign_count": None,
                    "flat_campaign_count": None,
                    "closed_campaign_win_rate": None,
                    "gross_expectancy_per_closed_campaign": None,
                    "gross_profit_factor": None,
                    "gross_max_realized_drawdown": None,
                }
            cell_result[account] = {
                "session_record_count": len(scoped),
                "missing_dates": missing_dates,
                "incomplete_dates": incomplete_dates,
                "open_position_count": open_positions,
                "unavailable_input_count": unavailable_inputs,
                "portfolio_metrics_eligible": eligible,
                "ineligible_financial_fields_are_null": not eligible,
                **financial,
            }
        result[cell] = cell_result
    return result


def validate_evaluation_contract(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported prospective evaluation contract schema")
    if payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected prospective evaluation contract")
    if payload.get("artifact_type") != CONTRACT_ARTIFACT_TYPE:
        raise ValueError("unexpected prospective evaluation contract type")
    if payload.get("registration_date") != REGISTRATION_DATE:
        raise ValueError("prospective evaluation registration date changed")
    if payload.get("registration_status") != "registered_before_panel_open":
        raise ValueError("prospective evaluation registration status changed")
    claimed = payload.get("content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if claimed != CONTRACT_CONTENT_SHA256 or canonical_fingerprint(unsigned) != claimed:
        raise ValueError("prospective evaluation contract content hash mismatch")
    parents = _mapping(payload.get("frozen_parents"), "frozen_parents")
    expected_parents = {
        "panel_id": PANEL_ID,
        "registered_dates": list(REGISTERED_DATES),
        "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
        "account_integration_content_sha256": ACCOUNT_INTEGRATION_CONTENT_SHA256,
        "prospective_execution_content_sha256": EXECUTION_CONTRACT_CONTENT_SHA256,
    }
    if parents != expected_parents:
        raise ValueError("prospective evaluation frozen parents changed")
    cells = payload.get("equal_report_cells")
    expected_cells = [
        {
            "cell_id": _cell_id(horizon, scenario),
            "behavioral_horizon_seconds": horizon,
            "execution_scenario_id": scenario,
        }
        for horizon, scenario in registered_cells()
    ]
    if cells != expected_cells:
        raise ValueError("prospective evaluation cells changed")
    if payload.get("metric_registry") != _metric_registry():
        raise ValueError("prospective evaluation metric registry changed")
    if payload.get("label_policy") != _label_policy():
        raise ValueError("prospective evaluation label policy changed")
    if payload.get("portfolio_policy") != _portfolio_policy():
        raise ValueError("prospective evaluation portfolio policy changed")
    if payload.get("authority_boundary") != _contract_authority_boundary():
        raise ValueError("prospective evaluation authority boundary changed")


def load_evaluation_contract(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("prospective evaluation contract root must be an object")
    validate_evaluation_contract(payload)
    return payload


def _validate_bundle_hash(payload: Mapping[str, object], field: str) -> None:
    claimed = _sha(payload.get("content_sha256"), f"{field}.content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError(f"{field} content hash mismatch")


def validate_runtime_bundle(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported prospective runtime evaluation input schema")
    if payload.get("artifact_type") != RUNTIME_ARTIFACT_TYPE:
        raise ValueError("unexpected prospective runtime evaluation input")
    if payload.get("evaluation_contract_content_sha256") != CONTRACT_CONTENT_SHA256:
        raise ValueError("runtime evaluation contract binding changed")
    if payload.get("panel_id") != PANEL_ID:
        raise ValueError("runtime evaluation panel changed")
    if payload.get("registered_dates") != list(REGISTERED_DATES):
        raise ValueError("runtime evaluation dates changed")
    if payload.get("frozen_parents") != _runtime_parent_bindings():
        raise ValueError("runtime evaluation frozen parents changed")
    _aware_iso(payload.get("runtime_frozen_at"), "runtime_frozen_at")
    if payload.get("runtime_frozen_before_retrospective_review") is not True:
        raise ValueError("runtime must be frozen before retrospective review")
    if payload.get("retrospective_review_started") is not False:
        raise ValueError("runtime input cannot be built after label review starts")
    if payload.get("raw_transcript_text_persisted") is not False:
        raise ValueError("runtime input cannot persist raw transcript text")
    if payload.get("runtime_strategy_effect") != "none":
        raise ValueError("runtime evaluation input cannot alter strategy")
    if _walk_keys(payload) & _FORBIDDEN_RUNTIME_KEYS:
        raise ValueError("runtime bundle contains retrospective label keys")
    _validate_bundle_hash(payload, "runtime bundle")
    decisions = tuple(
        RuntimeDecision.from_mapping(_mapping(row, "runtime decision"))
        for row in _sequence(payload.get("decisions"), "runtime decisions")
    )
    sessions = tuple(
        AccountSessionPerformance.from_mapping(_mapping(row, "session performance"))
        for row in _sequence(payload.get("sessions"), "session performance")
    )
    _validate_runtime_inputs(decisions, sessions)


def validate_labels_bundle(
    payload: Mapping[str, object],
    *,
    runtime_content_sha256: str,
    runtime_frozen_at: str,
) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported prospective retrospective label schema")
    if payload.get("artifact_type") != LABELS_ARTIFACT_TYPE:
        raise ValueError("unexpected prospective retrospective labels")
    if payload.get("evaluation_contract_content_sha256") != CONTRACT_CONTENT_SHA256:
        raise ValueError("retrospective labels contract binding changed")
    if payload.get("panel_id") != PANEL_ID:
        raise ValueError("retrospective labels panel changed")
    if payload.get("registered_dates") != list(REGISTERED_DATES):
        raise ValueError("retrospective label dates changed")
    if payload.get("runtime_content_sha256") != runtime_content_sha256:
        raise ValueError("retrospective labels do not bind the exact runtime")
    normalized_runtime_frozen_at = _aware_iso(
        runtime_frozen_at,
        "runtime_frozen_at",
    )
    if payload.get("runtime_frozen_at") != normalized_runtime_frozen_at:
        raise ValueError("retrospective labels runtime freeze timestamp changed")
    labels_opened_at = _aware_iso(payload.get("labels_opened_at"), "labels_opened_at")
    if datetime.fromisoformat(labels_opened_at) <= datetime.fromisoformat(
        normalized_runtime_frozen_at
    ):
        raise ValueError("retrospective labels must be opened after runtime freeze")
    if payload.get("labels_opened_after_runtime_hash_freeze") is not True:
        raise ValueError("retrospective labels must follow runtime hash freeze")
    if payload.get("label_policy") != _label_policy():
        raise ValueError("retrospective labels policy changed")
    if payload.get("raw_transcript_text_persisted") is not False:
        raise ValueError("retrospective label bundle cannot persist raw transcripts")
    if payload.get("runtime_strategy_effect") != "none":
        raise ValueError("retrospective labels cannot affect runtime")
    _validate_bundle_hash(payload, "labels bundle")
    human = tuple(
        HumanDecision.from_mapping(_mapping(row, "human decision"))
        for row in _sequence(payload.get("decisions"), "human decisions")
    )
    _validate_human_inputs(human, ())


def build_prospective_account_evaluation(
    *,
    contract: Mapping[str, object],
    runtime_bundle: Mapping[str, object],
    labels_bundle: Mapping[str, object],
) -> dict[str, object]:
    """Build the preregistered retrospective report from frozen parents."""

    validate_evaluation_contract(contract)
    validate_runtime_bundle(runtime_bundle)
    runtime_hash = _sha(runtime_bundle.get("content_sha256"), "runtime content")
    runtime_frozen_at = _aware_iso(
        runtime_bundle.get("runtime_frozen_at"),
        "runtime_frozen_at",
    )
    validate_labels_bundle(
        labels_bundle,
        runtime_content_sha256=runtime_hash,
        runtime_frozen_at=runtime_frozen_at,
    )
    labels_hash = _sha(labels_bundle.get("content_sha256"), "labels content")
    labels_opened_at = _aware_iso(
        labels_bundle.get("labels_opened_at"),
        "labels_opened_at",
    )

    runtime = tuple(
        RuntimeDecision.from_mapping(_mapping(row, "runtime decision"))
        for row in _sequence(runtime_bundle.get("decisions"), "runtime decisions")
    )
    sessions = tuple(
        AccountSessionPerformance.from_mapping(_mapping(row, "session performance"))
        for row in _sequence(runtime_bundle.get("sessions"), "session performance")
    )
    human = tuple(
        HumanDecision.from_mapping(_mapping(row, "human decision"))
        for row in _sequence(labels_bundle.get("decisions"), "human decisions")
    )
    _validate_runtime_inputs(runtime, sessions)
    _validate_human_inputs(human, runtime)
    comparisons = _build_comparisons(runtime, human, sessions)
    serialized_sessions = [row.as_dict() for row in sessions]
    serialized_sessions.sort(
        key=lambda row: (
            row["behavioral_horizon_seconds"],
            row["execution_scenario_id"],
            row["trading_date"],
            row["account"],
        )
    )
    identity = _candidate_identity(runtime)
    if identity["identical_candidate_set_across_all_cells"] is not True:
        raise ValueError("candidate set differs across registered evaluation cells")
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": REPORT_ID,
        "artifact_type": REPORT_ARTIFACT_TYPE,
        "contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "panel_id": PANEL_ID,
        "registered_dates": list(REGISTERED_DATES),
        "source_content_sha256s": {
            "runtime": runtime_hash,
            "retrospective_labels": labels_hash,
        },
        "knowledge_policy": {
            "runtime_frozen_before_labels": True,
            "runtime_frozen_at": runtime_frozen_at,
            "labels_opened_at": labels_opened_at,
            "labels_have_no_runtime_effect": True,
            "raw_transcript_text_persisted": False,
        },
        "metric_registry": _metric_registry(),
        "portfolio_policy": _portfolio_policy(),
        "candidate_identity": identity,
        "component_metrics": _aggregate_comparisons(comparisons),
        "portfolio_metrics": _portfolio_metrics(serialized_sessions),
        "decision_comparisons": comparisons,
        "session_performance": serialized_sessions,
        "authority_boundary": _report_authority_boundary(),
    }
    return _freeze(payload)


def validate_evaluation_report(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported prospective evaluation report schema")
    if payload.get("artifact_id") != REPORT_ID:
        raise ValueError("unexpected prospective evaluation report")
    if payload.get("artifact_type") != REPORT_ARTIFACT_TYPE:
        raise ValueError("unexpected prospective evaluation report type")
    if payload.get("contract_content_sha256") != CONTRACT_CONTENT_SHA256:
        raise ValueError("prospective evaluation report contract changed")
    if payload.get("panel_id") != PANEL_ID:
        raise ValueError("prospective evaluation report panel changed")
    if payload.get("registered_dates") != list(REGISTERED_DATES):
        raise ValueError("prospective evaluation report dates changed")
    _validate_bundle_hash(payload, "evaluation report")
    if _walk_keys(payload) & _PROHIBITED_REPORT_KEYS:
        raise ValueError("evaluation report contains a prohibited aggregate or selection")
    if payload.get("metric_registry") != _metric_registry():
        raise ValueError("evaluation report metric registry changed")
    if payload.get("portfolio_policy") != _portfolio_policy():
        raise ValueError("evaluation report portfolio policy changed")
    sources = _mapping(payload.get("source_content_sha256s"), "sources")
    if set(sources) != {"runtime", "retrospective_labels"}:
        raise ValueError("evaluation report source set is incomplete")
    for field, value in sources.items():
        _sha(value, f"source.{field}")
    if payload.get("authority_boundary") != _report_authority_boundary():
        raise ValueError("evaluation report authority boundary changed")
    knowledge = _mapping(payload.get("knowledge_policy"), "knowledge_policy")
    runtime_frozen_at = _aware_iso(
        knowledge.get("runtime_frozen_at"),
        "knowledge_policy.runtime_frozen_at",
    )
    labels_opened_at = _aware_iso(
        knowledge.get("labels_opened_at"),
        "knowledge_policy.labels_opened_at",
    )
    if datetime.fromisoformat(labels_opened_at) <= datetime.fromisoformat(
        runtime_frozen_at
    ):
        raise ValueError("evaluation report labels do not follow runtime freeze")
    expected_knowledge = {
        "runtime_frozen_before_labels": True,
        "runtime_frozen_at": runtime_frozen_at,
        "labels_opened_at": labels_opened_at,
        "labels_have_no_runtime_effect": True,
        "raw_transcript_text_persisted": False,
    }
    if knowledge != expected_knowledge:
        raise ValueError("evaluation report knowledge policy changed")

    sessions = tuple(
        AccountSessionPerformance.from_mapping(_mapping(row, "session performance"))
        for row in _sequence(payload.get("session_performance"), "session performance")
    )
    _validate_session_inputs(sessions)
    session_by_key = {_session_key(row): row for row in sessions}
    session_dicts = [row.as_dict() for row in sessions]
    if payload.get("portfolio_metrics") != _portfolio_metrics(session_dicts):
        raise ValueError("evaluation report portfolio metrics are inconsistent")

    comparisons = [
        _mapping(row, "decision comparison")
        for row in _sequence(payload.get("decision_comparisons"), "comparisons")
    ]
    comparison_keys: set[tuple[object, ...]] = set()
    human_by_key: dict[tuple[str, str, str], HumanDecision] = {}
    human_keys_by_cell = {
        _cell_id(horizon, scenario): set() for horizon, scenario in registered_cells()
    }
    runtime_rows: list[RuntimeDecision] = []
    for row in comparisons:
        horizon = row.get("behavioral_horizon_seconds")
        scenario = row.get("execution_scenario_id")
        if (
            isinstance(horizon, bool)
            or not isinstance(horizon, int)
            or horizon not in BEHAVIORAL_HORIZONS_SECONDS
        ):
            raise ValueError("evaluation report comparison horizon is invalid")
        if scenario not in EXECUTION_SCENARIOS:
            raise ValueError("evaluation report comparison scenario is invalid")
        expected_cell = _cell_id(int(horizon), str(scenario))
        if row.get("cell_id") != expected_cell:
            raise ValueError("evaluation report comparison cell is inconsistent")
        key = (
            row.get("cell_id"),
            row.get("trading_date"),
            row.get("symbol"),
            row.get("account"),
        )
        if key in comparison_keys:
            raise ValueError("evaluation report comparison is duplicated")
        comparison_keys.add(key)
        human = _mapping(row.get("human"), "comparison human")
        human_decision = HumanDecision.from_mapping(human)
        if human != human_decision.as_dict():
            raise ValueError("evaluation report human decision is not canonical")
        human_key = _human_key(human_decision)
        if (
            row.get("trading_date"),
            row.get("symbol"),
            row.get("account"),
        ) != human_key:
            raise ValueError("evaluation report human row identity is inconsistent")
        previous_human = human_by_key.get(human_key)
        if previous_human is not None and previous_human.as_dict() != human_decision.as_dict():
            raise ValueError("evaluation report human label differs between cells")
        human_by_key[human_key] = human_decision
        human_keys_by_cell[expected_cell].add(human_key)
        runtime_value = row.get("runtime")
        runtime = (
            None
            if runtime_value is None
            else _mapping(runtime_value, "comparison runtime")
        )
        session = session_by_key[
            (int(horizon), str(scenario), human_decision.trading_date, human_decision.account)
        ]
        if row.get("session_runtime_complete") is not session.runtime_complete:
            raise ValueError("evaluation report session completeness is inconsistent")
        if runtime is not None:
            runtime_decision = RuntimeDecision.from_mapping(runtime)
            if runtime != runtime_decision.as_dict():
                raise ValueError("evaluation report runtime decision is not canonical")
            if (
                runtime_decision.behavioral_horizon_seconds,
                runtime_decision.execution_scenario_id,
                runtime_decision.trading_date,
                runtime_decision.symbol,
                runtime_decision.account,
            ) != (
                int(horizon),
                str(scenario),
                human_decision.trading_date,
                human_decision.symbol,
                human_decision.account,
            ):
                raise ValueError("evaluation report runtime row identity is inconsistent")
            if runtime_decision.runtime_content_sha256 != session.runtime_content_sha256:
                raise ValueError("evaluation report runtime row does not bind its session")
            runtime_rows.append(runtime_decision)
        expected_acquired = runtime is not None if session.runtime_complete else None
        if row.get("candidate_acquired") != expected_acquired:
            raise ValueError("evaluation report acquisition state is inconsistent")
        expected_relation = _relation(
            str(human.get("human_state")),
            runtime,
            row.get("session_runtime_complete") is True,
        )
        if row.get("relation") != expected_relation:
            raise ValueError("evaluation report relation is inconsistent")
        if row.get("entry_alignment") != _entry_alignment(human, runtime):
            raise ValueError("evaluation report entry alignment is inconsistent")
        if row.get("exit_alignment") != _exit_alignment(human, runtime):
            raise ValueError("evaluation report exit alignment is inconsistent")
    cell_human_sets = tuple(human_keys_by_cell.values())
    if any(value != cell_human_sets[0] for value in cell_human_sets[1:]):
        raise ValueError("evaluation report label set differs across cells")
    if len(comparisons) != len(human_by_key) * len(registered_cells()):
        raise ValueError("evaluation report does not contain every label in every cell")
    unique_runtime = {_runtime_key(row): row for row in runtime_rows}
    if len(unique_runtime) != len(runtime_rows):
        raise ValueError("evaluation report runtime decision is duplicated")
    runtime_tuple = tuple(unique_runtime.values())
    _validate_runtime_inputs(runtime_tuple, sessions)
    _validate_human_inputs(tuple(human_by_key.values()), runtime_tuple)
    if payload.get("component_metrics") != _aggregate_comparisons(comparisons):
        raise ValueError("evaluation report component metrics are inconsistent")
    expected_identity = _candidate_identity(runtime_tuple)
    if payload.get("candidate_identity") != expected_identity:
        raise ValueError("evaluation report candidate identity is inconsistent")
    if expected_identity["identical_candidate_set_across_all_cells"] is not True:
        raise ValueError("evaluation report cells do not share candidate identity")


def load_evaluation_report(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("prospective evaluation report root must be an object")
    validate_evaluation_report(payload)
    return payload


__all__ = [
    "ACCOUNT_KEYS",
    "AccountSessionPerformance",
    "BEHAVIORAL_HORIZONS_SECONDS",
    "CONTRACT_CONTENT_SHA256",
    "CONTRACT_ID",
    "EXECUTION_SCENARIOS",
    "HUMAN_ACTION_STATES",
    "HumanDecision",
    "REPORT_ID",
    "RuntimeDecision",
    "build_prospective_account_evaluation",
    "canonical_fingerprint",
    "load_evaluation_contract",
    "load_evaluation_report",
    "registered_cells",
    "validate_evaluation_contract",
    "validate_evaluation_report",
    "validate_labels_bundle",
    "validate_runtime_bundle",
]
