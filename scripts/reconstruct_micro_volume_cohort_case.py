from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.indicators import completed_bar_support_series
from momentumbot.micro_bars import aggregate_trade_bars
from momentumbot.micro_execution import MicroTriggerMode
from momentumbot.micro_policy import micro_v0_1_policy
from momentumbot.micro_replay import (
    MicroCandidateReplay,
    micro_replay_runtime_artifact,
    replay_micro_candidate,
)
from momentumbot.models import current_general_2026
from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.providers.alpaca_trades import historical_trades
from momentumbot.research.benchmark_market import refine_candidate_minute_with_sip
from momentumbot.research.micro_context_ablation import (
    micro_v0_2a_context_ablation,
    prequalification_context_runtime_artifact,
    replay_micro_candidate_with_prequalification_context,
)
from momentumbot.research.micro_volume_ablation import (
    micro_v0_2c_volume_ablation,
    micro_v0_2d_context_volume_ablation,
    micro_volume_ablation_runtime_artifact,
    replay_micro_candidate_with_context_without_hard_volume_gate,
    replay_micro_candidate_without_hard_volume_gate,
)

ET = ZoneInfo("America/New_York")
EMA_WARMUP_CALENDAR_DAYS = 7
EXPECTED_SELECTION_TYPE = "micro_volume_activity_cohort_selection"
EXPECTED_SELECTION_POLICY = "runtime_market_data_only_no_retrospective_labels"


def _utc_session_start(trading_date: date) -> datetime:
    return datetime.combine(trading_date, time(4, 0), ET).astimezone(timezone.utc)


def _utc_entry_cutoff(trading_date: date, cutoff: time) -> datetime:
    return datetime.combine(trading_date, cutoff, ET).astimezone(timezone.utc)


def _write_frame(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.reset_index().to_csv(path, index=False)


def _selection_case(path: Path, case_id: str) -> tuple[dict[str, object], dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("artifact_type") != EXPECTED_SELECTION_TYPE:
        raise ValueError("unexpected cohort selection artifact type")
    if payload.get("knowledge_policy") != EXPECTED_SELECTION_POLICY:
        raise ValueError("cohort selection is not label-blind")
    if payload.get("selection_status") != "label_blind_market_discovery_complete":
        raise ValueError("cohort selection is not frozen")
    if payload.get("selection_columns_used") != [
        "first_market_qualified_at",
        "symbol",
    ]:
        raise ValueError("cohort selection used an unapproved field")
    matches = [case for case in payload.get("cases", []) if case.get("case_id") == case_id]
    if len(matches) != 1:
        raise ValueError(f"selection must contain exactly one case {case_id!r}")
    return payload, matches[0]


def _cell_summary(replay: MicroCandidateReplay, qualified_at: pd.Timestamp) -> dict[str, object]:
    plan_steps = [step for step in replay.steps if step.plan is not None]
    filled_steps = [
        step
        for step in replay.steps
        if step.outcome is not None and step.outcome.fill_time is not None
    ]
    first_plan = plan_steps[0] if plan_steps else None
    first_fill = (
        min(filled_steps, key=lambda step: pd.Timestamp(step.outcome.fill_time))
        if filled_steps
        else None
    )
    first_plan_at = pd.Timestamp(first_plan.evaluated_at) if first_plan else None
    first_fill_at = (
        pd.Timestamp(first_fill.outcome.fill_time) if first_fill is not None else None
    )
    return {
        "plan_count": replay.plan_count,
        "filled_count": replay.filled_count,
        "filled_pullback_numbers": list(replay.filled_pullback_numbers),
        "reason_counts": replay.reason_counts,
        "first_plan_evaluated_at": first_plan_at.isoformat() if first_plan_at else None,
        "first_plan_armed_at": (
            pd.Timestamp(first_plan.plan.armed_at).isoformat() if first_plan else None
        ),
        "first_plan_pullback_number": (
            first_plan.pullback_number if first_plan else None
        ),
        "first_plan_minimum_new_high_price": (
            float(first_plan.plan.minimum_new_high_price) if first_plan else None
        ),
        "first_plan_latency_seconds": (
            float((first_plan_at - qualified_at).total_seconds())
            if first_plan_at is not None
            else None
        ),
        "first_fill_at": first_fill_at.isoformat() if first_fill_at else None,
        "first_fill_price": (
            float(first_fill.outcome.fill_price) if first_fill is not None else None
        ),
        "first_filled_pullback_number": (
            first_fill.pullback_number if first_fill is not None else None
        ),
        "first_fill_latency_seconds": (
            float((first_fill_at - qualified_at).total_seconds())
            if first_fill_at is not None
            else None
        ),
    }


def _paired_delta(after: dict[str, object], before: dict[str, object]) -> dict[str, object]:
    before_fill = before.get("first_fill_at")
    after_fill = after.get("first_fill_at")
    if before_fill is None and after_fill is None:
        fill_state = "neither_filled"
    elif before_fill is None:
        fill_state = "gained_first_fill"
    elif after_fill is None:
        fill_state = "lost_first_fill"
    else:
        fill_state = "both_filled"

    def shift(field: str) -> float | None:
        left = before.get(field)
        right = after.get(field)
        if left is None or right is None:
            return None
        return float((pd.Timestamp(right) - pd.Timestamp(left)).total_seconds())

    def ordinal_delta(field: str) -> int | None:
        left = before.get(field)
        right = after.get(field)
        if left is None or right is None:
            return None
        return int(right) - int(left)

    return {
        "plan_count_delta": int(after["plan_count"]) - int(before["plan_count"]),
        "filled_count_delta": int(after["filled_count"]) - int(before["filled_count"]),
        "first_plan_shift_seconds": shift("first_plan_evaluated_at"),
        "first_fill_shift_seconds": shift("first_fill_at"),
        "first_plan_pullback_ordinal_delta": ordinal_delta(
            "first_plan_pullback_number"
        ),
        "first_fill_pullback_ordinal_delta": ordinal_delta(
            "first_filled_pullback_number"
        ),
        "first_fill_state": fill_state,
    }


def _add_common_runtime_fields(
    payload: dict[str, object],
    *,
    selection: dict[str, object],
    case: dict[str, object],
    selection_sha256: str,
    acquisition_minute: pd.Timestamp,
    qualified_at: pd.Timestamp,
    decision_time_source: str,
    refined: object,
    replay_end: pd.Timestamp,
    support_contract: dict[str, object],
) -> None:
    payload.update(
        {
            "case_id": case["case_id"],
            "trading_date": case["trading_date"],
            "cohort_design_id": selection["design_id"],
            "cohort_selection_sha256": selection_sha256,
            "selection_rank_within_date": case["selection_rank_within_date"],
            "candidate_anchor_source": "precommitted_label_blind_market_day_discovery",
            "candidate_anchor_scope": (
                "price/gain/same-time-RVOL/price-band qualification only; historical "
                "float, news and cross-sectional rank are outside this conditional "
                "micro-layer activity cohort"
            ),
            "candidate_acquisition_minute_start": acquisition_minute.isoformat(),
            "candidate_decision_time_source": decision_time_source,
            "candidate_qualified_at": qualified_at.isoformat(),
            "intraminute_refinement": asdict(refined),
            "replay_window_policy": "candidate_qualification_to_no_new_entries_after",
            "replay_end": replay_end.isoformat(),
            "support_contract": support_contract,
            "retrospective_behavior_labels_loaded": False,
            "policy_promotion_eligible": False,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay all four frozen Micro volume/context cells for one selected cohort case."
    )
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    selection, case = _selection_case(args.selection, args.case_id)
    selection_sha256 = hashlib.sha256(args.selection.read_bytes()).hexdigest()
    symbol = str(case["symbol"])
    trading_date = date.fromisoformat(str(case["trading_date"]))
    previous_close = float(case["previous_close"])
    acquisition_minute = pd.Timestamp(case["first_market_qualified_at"]).floor("min")
    if acquisition_minute.tzinfo is None:
        raise ValueError("selected qualification minute must be timezone-aware")

    profile = current_general_2026()
    parent = micro_v0_1_policy()
    context_spec = micro_v0_2a_context_ablation()
    volume_spec = micro_v0_2c_volume_ablation()
    context_volume_spec = micro_v0_2d_context_volume_ablation()
    client = AlpacaDataClient.from_env()

    refined = refine_candidate_minute_with_sip(
        client,
        symbol=symbol,
        trading_date=trading_date,
        candidate_minute_start=acquisition_minute,
        previous_close=previous_close,
        profile=profile,
    )
    if refined.qualified_at is not None:
        qualified_at = pd.Timestamp(refined.qualified_at)
        decision_time_source = "sip_intraminute_refinement"
    else:
        qualified_at = acquisition_minute + pd.Timedelta(minutes=1)
        decision_time_source = "completed_acquisition_minute_fallback"
    if qualified_at.tzinfo is None:
        raise RuntimeError("refined qualification timestamp is not timezone-aware")

    session_start = pd.Timestamp(_utc_session_start(trading_date))
    replay_end = pd.Timestamp(
        _utc_entry_cutoff(trading_date, profile.no_new_entries_after)
    )
    if replay_end <= qualified_at:
        raise RuntimeError("selected candidate qualified at or after the entry cutoff")
    context_seconds = context_spec.context_bars * context_spec.bar_interval_seconds
    trade_fetch_start = max(
        session_start,
        qualified_at.floor(f"{context_spec.bar_interval_seconds}s")
        - pd.Timedelta(seconds=context_seconds),
    )

    trades = historical_trades(
        client,
        symbol,
        start=trade_fetch_start.to_pydatetime(),
        end=replay_end.to_pydatetime(),
        feed="sip",
        asof=trading_date,
    )
    if trades.empty:
        raise RuntimeError(f"Alpaca returned no SIP trades for selected case {args.case_id}")
    bars = aggregate_trade_bars(trades, f"{parent.micro_bar_interval_seconds}s")
    if bars.empty:
        raise RuntimeError(f"could not derive micro bars for selected case {args.case_id}")
    action_bars = bars.loc[bars.index >= qualified_at]
    if action_bars.empty:
        raise RuntimeError("no completed micro bucket begins after candidate qualification")

    current_session = client.bars(
        [symbol],
        timeframe="1Min",
        start=session_start.to_pydatetime(),
        end=replay_end.to_pydatetime(),
        feed="sip",
        adjustment="raw",
        asof=trading_date,
    )[symbol]
    warmup_start = session_start - pd.Timedelta(days=EMA_WARMUP_CALENDAR_DAYS)
    split_history = client.bars(
        [symbol],
        timeframe="1Min",
        start=warmup_start.to_pydatetime(),
        end=session_start.to_pydatetime(),
        feed="sip",
        adjustment="split",
        asof=trading_date,
    )[symbol]
    support = completed_bar_support_series(
        current_session,
        ema_span=profile.ema_span,
        bar_duration="1min",
        ema_warmup=split_history,
    )
    common_replay = {
        "candidate_qualified_at": qualified_at,
        "vwap_available": support["vwap"],
        "ema9_available": support["ema"],
        "trigger_mode": MicroTriggerMode.CHART_PRICE,
        "entry_latency_ms": 0.0,
        "exit_until": replay_end,
    }

    baseline = replay_micro_candidate(
        symbol,
        action_bars,
        trades,
        policy=parent.setup,
        **common_replay,
    )
    context = replay_micro_candidate_with_prequalification_context(
        symbol,
        bars,
        trades,
        spec=context_spec,
        policy=parent.setup,
        **common_replay,
    )
    volume = replay_micro_candidate_without_hard_volume_gate(
        symbol,
        action_bars,
        trades,
        spec=volume_spec,
        **common_replay,
    )
    context_volume = replay_micro_candidate_with_context_without_hard_volume_gate(
        symbol,
        bars,
        trades,
        spec=context_volume_spec,
        **common_replay,
    )

    runtimes = {
        "baseline": micro_replay_runtime_artifact(baseline),
        "context_only": prequalification_context_runtime_artifact(context),
        "volume_only": micro_volume_ablation_runtime_artifact(volume),
        "context_plus_volume": micro_volume_ablation_runtime_artifact(context_volume),
    }
    runtimes["baseline"].update(
        {
            "frozen_policy_id": parent.policy_id,
            "frozen_policy_fingerprint": parent.fingerprint,
            "frozen_policy_status": parent.status,
        }
    )
    support_contract = {
        "vwap": "raw current session from 04:00 ET; available after minute completion",
        "ema9": "split-normalized prior one-minute warmup plus raw current session; available after minute completion",
        "ema_warmup_calendar_days": EMA_WARMUP_CALENDAR_DAYS,
        "ema_warmup_bar_count": len(split_history),
        "session_minute_bar_count": len(current_session),
        "shared_market_input_across_all_four_cells": True,
    }
    for runtime in runtimes.values():
        _add_common_runtime_fields(
            runtime,
            selection=selection,
            case=case,
            selection_sha256=selection_sha256,
            acquisition_minute=acquisition_minute,
            qualified_at=qualified_at,
            decision_time_source=decision_time_source,
            refined=refined,
            replay_end=replay_end,
            support_contract=support_contract,
        )

    summaries = {
        "baseline": _cell_summary(baseline, qualified_at),
        "context_only": _cell_summary(context.replay, qualified_at),
        "volume_only": _cell_summary(volume.replay, qualified_at),
        "context_plus_volume": _cell_summary(context_volume.replay, qualified_at),
    }
    identities = {
        "baseline": {
            "policy_id": parent.policy_id,
            "policy_fingerprint": parent.fingerprint,
        },
        "context_only": {
            "policy_id": context_spec.ablation_id,
            "policy_fingerprint": context_spec.fingerprint,
        },
        "volume_only": {
            "policy_id": volume_spec.ablation_id,
            "policy_fingerprint": volume_spec.fingerprint,
        },
        "context_plus_volume": {
            "policy_id": context_volume_spec.ablation_id,
            "policy_fingerprint": context_volume_spec.fingerprint,
        },
    }
    for cell, identity in identities.items():
        summaries[cell].update(identity)

    comparison = {
        "artifact_type": "micro_volume_activity_cohort_case_comparison",
        "schema_version": 1,
        "knowledge_policy": "runtime_market_data_only_no_retrospective_labels",
        "strategy_feedback": "activity_stress_only",
        "policy_promotion_eligible": False,
        "cohort_design_id": selection["design_id"],
        "cohort_selection_sha256": selection_sha256,
        "case_id": case["case_id"],
        "symbol": symbol,
        "trading_date": trading_date.isoformat(),
        "selection_rank_within_date": case["selection_rank_within_date"],
        "candidate_acquisition_minute_start": acquisition_minute.isoformat(),
        "candidate_qualified_at": qualified_at.isoformat(),
        "candidate_decision_time_source": decision_time_source,
        "cells": summaries,
        "paired_deltas": {
            "volume_only_vs_baseline": _paired_delta(
                summaries["volume_only"], summaries["baseline"]
            ),
            "context_plus_volume_vs_context_only": _paired_delta(
                summaries["context_plus_volume"], summaries["context_only"]
            ),
            "context_only_vs_baseline": _paired_delta(
                summaries["context_only"], summaries["baseline"]
            ),
            "context_plus_volume_vs_volume_only": _paired_delta(
                summaries["context_plus_volume"], summaries["volume_only"]
            ),
        },
        "interpretation_limits": [
            "activity counts are independent rolling diagnostic opportunities, not portfolio trades",
            "no human behavior label, later outcome, P&L, float, news or rank is loaded",
            "the case cannot score imitation or scanner false-positive rate",
            "the case cannot promote a policy",
        ],
    }

    args.output.mkdir(parents=True, exist_ok=True)
    for cell, runtime in runtimes.items():
        cell_path = args.output / "runtime" / cell / "runtime-replay.json"
        cell_path.parent.mkdir(parents=True, exist_ok=True)
        cell_path.write_text(
            json.dumps(runtime, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    shared_context = {
        "artifact_type": "micro_volume_activity_cohort_case_context",
        "schema_version": 1,
        "knowledge_policy": "runtime_market_data_only_no_retrospective_labels",
        "case": case,
        "cohort_design_id": selection["design_id"],
        "cohort_selection_sha256": selection_sha256,
        "candidate_qualified_at": qualified_at.isoformat(),
        "candidate_decision_time_source": decision_time_source,
        "intraminute_refinement": asdict(refined),
        "trade_fetch_start": trade_fetch_start.isoformat(),
        "replay_end": replay_end.isoformat(),
        "runtime_counts": {
            "trade_prints": len(trades),
            "micro_bars_with_context": len(bars),
            "micro_bars_action_only": len(action_bars),
        },
        "support_contract": support_contract,
        "retrospective_behavior_labels_loaded": False,
    }
    (args.output / "runtime-context.json").write_text(
        json.dumps(shared_context, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output / "case-comparison.json").write_text(
        json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_frame(trades, args.output / "inputs" / "trades.csv")
    _write_frame(bars, args.output / "inputs" / "bars-10s.csv")
    _write_frame(support, args.output / "inputs" / "support-available.csv")
    _write_frame(current_session, args.output / "inputs" / "session-1m.csv")
    _write_frame(split_history, args.output / "inputs" / "ema-warmup-1m.csv")
    print(json.dumps(comparison, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
