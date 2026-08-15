from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.indicators import completed_bar_support_series
from momentumbot.micro_bars import aggregate_trade_bars, minute_trade_eligibility
from momentumbot.micro_execution import MicroTriggerMode, simulate_micro_entries
from momentumbot.micro_setup import (
    MicroPsychologicalLevel,
    build_psychological_level_continuation_plan,
    canonical_micro_setup_policy,
    detect_running_high_pullbacks,
    evaluate_micro_pullback_plan,
    geometry_only_micro_research_policy,
)
from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.providers.alpaca_trades import historical_trades

ET = ZoneInfo("America/New_York")
QUALIFIED_AT = pd.Timestamp("2026-07-09T11:31:00Z")


def _utc(day: date, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute, second), ET).astimezone(timezone.utc)


def _write_frame(frame: pd.DataFrame, path: Path) -> None:
    frame.reset_index().to_csv(path, index=False)


def _first_eligible_at_or_above(trades: pd.DataFrame, level: float) -> dict | None:
    for timestamp, row in trades[pd.to_numeric(trades["price"]) >= level].iterrows():
        eligibility = minute_trade_eligibility(row.get("tape"), row.get("conditions") or ())
        if eligibility.updates_price:
            return {
                "timestamp": timestamp.isoformat(),
                "price": float(row["price"]),
                "size": int(row["size"]),
            }
    return None


def _compare_minute_bars(reconstructed: pd.DataFrame, official: pd.DataFrame) -> list[dict]:
    output: list[dict] = []
    for timestamp in reconstructed.index.intersection(official.index):
        left, right = reconstructed.loc[timestamp], official.loc[timestamp]
        output.append(
            {
                "timestamp": timestamp.isoformat(),
                "open_delta": float(left["open"] - right["open"]),
                "high_delta": float(left["high"] - right["high"]),
                "low_delta": float(left["low"] - right["low"]),
                "close_delta": float(left["close"] - right["close"]),
                "volume_delta": int(left["volume"] - right["volume"]),
            }
        )
    return output


def _outcome_row(metadata: dict[str, object], outcome) -> dict[str, object]:
    row = dict(metadata)
    row.update(
        {
            "execution_status": outcome.status.value,
            "trigger_time": (
                outcome.trigger_time.isoformat() if outcome.trigger_time is not None else None
            ),
            "trigger_print_price": outcome.trigger_print_price,
            "fill_time": (
                outcome.fill_time.isoformat() if outcome.fill_time is not None else None
            ),
            "fill_price": outcome.fill_price,
            "entry_slippage": outcome.entry_slippage,
        }
    )
    return row


def _context_sensitivity(
    metadata: list[dict[str, object]],
    plans,
    trades: pd.DataFrame,
    *,
    end: datetime,
) -> dict[str, object]:
    outcomes = simulate_micro_entries(
        plans,
        trades,
        trigger_mode=MicroTriggerMode.CHART_PRICE,
        entry_latency_ms=0.0,
        exit_until=pd.Timestamp(end),
    )
    return {
        "plan_count": len(plans),
        "chart_confirmed_fill_count": sum(outcome.fill_price is not None for outcome in outcomes),
        "plans": [
            _outcome_row(row, outcome)
            for row, outcome in zip(metadata, outcomes)
        ],
    }


def _micro_geometry_diagnostics(
    bars_10s: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    end: datetime,
) -> dict[str, object]:
    """Run geometry-only setup and level context without using recap labels."""
    policy = geometry_only_micro_research_policy()
    reasons: Counter[str] = Counter()
    plans = []
    plan_features: list[dict[str, object]] = []
    context_plans = {
        MicroPsychologicalLevel.HALF_DOLLAR: [],
        MicroPsychologicalLevel.WHOLE_DOLLAR: [],
    }
    context_metadata: dict[MicroPsychologicalLevel, list[dict[str, object]]] = {
        MicroPsychologicalLevel.HALF_DOLLAR: [],
        MicroPsychologicalLevel.WHOLE_DOLLAR: [],
    }

    for timestamp in bars_10s.loc[QUALIFIED_AT:].index:
        evaluation = evaluate_micro_pullback_plan(
            "VRAX",
            bars_10s.loc[:timestamp],
            candidate_qualified_at=QUALIFIED_AT,
            policy=policy,
        )
        reasons[evaluation.reason] += 1
        if evaluation.plan is None or evaluation.features is None:
            continue

        plans.append(evaluation.plan)
        features = evaluation.features
        base_row = {
            "evaluated_at": features.evaluated_at.isoformat(),
            "peak_time": features.peak_time.isoformat(),
            "peak_high": features.peak_high,
            "impulse_base": features.impulse_base,
            "pullback_start": features.pullback_start.isoformat(),
            "pullback_bars": features.pullback_bars,
            "trough_time": features.trough_time.isoformat(),
            "pullback_low": features.pullback_low,
            "retrace_fraction": features.retrace_fraction,
            "impulse_mean_volume": features.impulse_mean_volume,
            "pullback_mean_volume": features.pullback_mean_volume,
            "peak_upper_wick_fraction": features.peak_upper_wick_fraction,
            "previous_candle_high": features.previous_candle_high,
            "next_half_dollar_above_peak": features.next_half_dollar_above_peak,
            "next_whole_dollar_above_peak": features.next_whole_dollar_above_peak,
            "distance_to_next_half_dollar": features.distance_to_next_half_dollar,
            "distance_to_next_whole_dollar": features.distance_to_next_whole_dollar,
            "trigger_price": evaluation.plan.minimum_new_high_price,
            "stop_price": evaluation.plan.stop_price,
        }
        plan_features.append(base_row)

        for level in context_plans:
            context_plan = build_psychological_level_continuation_plan(
                evaluation,
                level,
                tick_size=policy.tick_size,
            )
            if context_plan is None:
                continue
            context_plans[level].append(context_plan)
            context_metadata[level].append(
                {
                    "evaluated_at": features.evaluated_at.isoformat(),
                    "peak_time": features.peak_time.isoformat(),
                    "peak_high": features.peak_high,
                    "pullback_low": features.pullback_low,
                    "context_level": level.value,
                    "context_trigger_price": context_plan.minimum_new_high_price,
                    "canonical_trigger_price": evaluation.plan.minimum_new_high_price,
                    "stop_price": context_plan.stop_price,
                }
            )

    outcomes = simulate_micro_entries(
        plans,
        trades,
        trigger_mode=MicroTriggerMode.CHART_PRICE,
        entry_latency_ms=0.0,
        exit_until=pd.Timestamp(end),
    )
    outcome_rows = [
        _outcome_row(features, outcome)
        for features, outcome in zip(plan_features, outcomes)
    ]

    level_sensitivities = {
        level.value: _context_sensitivity(
            context_metadata[level], context_plans[level], trades, end=end
        )
        for level in context_plans
    }
    return {
        "policy": policy.name,
        "policy_role": "geometry_only_research_diagnostic_not_canonical_strategy",
        "candidate_anchor": QUALIFIED_AT.isoformat(),
        "support_filters_enforced": False,
        "machine_translation": {
            "max_pullback_bars": policy.max_pullback_bars,
            "impulse_lookback_bars": policy.impulse_lookback_bars,
            "max_retrace_fraction": policy.max_retrace_fraction,
            "require_lower_pullback_volume": policy.require_lower_pullback_volume,
        },
        "evaluation_reason_counts": dict(sorted(reasons.items())),
        "plan_count": len(plans),
        "chart_confirmed_fill_count": sum(outcome.fill_price is not None for outcome in outcomes),
        "plans": outcome_rows,
        "psychological_level_context": {
            "role": "research_sensitivity_only_not_a_chart_only_selection_rule",
            "selection_policy": "none; half-dollar and whole-dollar alternatives are both reported",
            "canonical_trigger_unchanged": True,
            "sensitivities": level_sensitivities,
        },
    }


def _canonical_support_diagnostics(
    bars_10s: pd.DataFrame,
    trades: pd.DataFrame,
    support: pd.DataFrame,
    *,
    end: datetime,
) -> dict[str, object]:
    """Run the canonical setup with only completed one-minute support values."""
    policy = canonical_micro_setup_policy()
    reasons: Counter[str] = Counter()
    plans = []
    metadata: list[dict[str, object]] = []
    for timestamp in bars_10s.loc[QUALIFIED_AT:].index:
        evaluation = evaluate_micro_pullback_plan(
            "VRAX",
            bars_10s.loc[:timestamp],
            candidate_qualified_at=QUALIFIED_AT,
            policy=policy,
            vwap_available=support["vwap"],
            ema9_available=support["ema"],
        )
        reasons[evaluation.reason] += 1
        if evaluation.plan is None or evaluation.features is None:
            continue
        plans.append(evaluation.plan)
        features = evaluation.features
        metadata.append(
            {
                "evaluated_at": features.evaluated_at.isoformat(),
                "peak_time": features.peak_time.isoformat(),
                "peak_high": features.peak_high,
                "pullback_start": features.pullback_start.isoformat(),
                "pullback_bars": features.pullback_bars,
                "trough_time": features.trough_time.isoformat(),
                "pullback_low": features.pullback_low,
                "retrace_fraction": features.retrace_fraction,
                "pullback_mean_volume": features.pullback_mean_volume,
                "impulse_mean_volume": features.impulse_mean_volume,
                "vwap_at_low": features.vwap_at_low,
                "ema9_at_low": features.ema9_at_low,
                "trigger_price": evaluation.plan.minimum_new_high_price,
                "stop_price": evaluation.plan.stop_price,
            }
        )

    outcomes = simulate_micro_entries(
        plans,
        trades,
        trigger_mode=MicroTriggerMode.CHART_PRICE,
        entry_latency_ms=0.0,
        exit_until=pd.Timestamp(end),
    )
    return {
        "policy": policy.name,
        "policy_role": "canonical_setup_with_completed_one_minute_support_context",
        "candidate_anchor": QUALIFIED_AT.isoformat(),
        "support_filters_enforced": True,
        "support_availability": "one_minute_values_indexed_at_bar_end_not_bar_start",
        "support_session_start": support.index[0].isoformat() if not support.empty else None,
        "evaluation_reason_counts": dict(sorted(reasons.items())),
        "plan_count": len(plans),
        "chart_confirmed_fill_count": sum(outcome.fill_price is not None for outcome in outcomes),
        "plans": [
            _outcome_row(row, outcome)
            for row, outcome in zip(metadata, outcomes)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the July 9 VRAX micro-timeframe reference trade."
    )
    parser.add_argument("--output", type=Path, default=Path("vrax-micro-reference"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    trading_date = date(2026, 7, 9)
    start, end = _utc(trading_date, 7, 29, 30), _utc(trading_date, 7, 34, 30)
    support_start = _utc(trading_date, 4, 0)
    client = AlpacaDataClient.from_env()
    trades = historical_trades(
        client, "VRAX", start=start, end=end, feed="sip", asof=trading_date
    )
    if trades.empty:
        raise RuntimeError("Alpaca returned no VRAX SIP trades in the reference window")
    bars_10s = aggregate_trade_bars(trades, "10s")
    reconstructed_1m = aggregate_trade_bars(trades, "1min")
    official = client.bars(
        ["VRAX"],
        timeframe="1Min",
        start=start,
        end=end,
        feed="sip",
        adjustment="raw",
        asof=trading_date,
    )["VRAX"]
    support_bars = client.bars(
        ["VRAX"],
        timeframe="1Min",
        start=support_start,
        end=end,
        feed="sip",
        adjustment="raw",
        asof=trading_date,
    )["VRAX"]
    if support_bars.empty:
        raise RuntimeError("Alpaca returned no VRAX one-minute support history")
    support = completed_bar_support_series(
        support_bars,
        ema_span=9,
        bar_duration="1min",
    )

    _write_frame(trades, args.output / "trades.csv")
    _write_frame(bars_10s, args.output / "bars-10s.csv")
    _write_frame(reconstructed_1m, args.output / "reconstructed-1m.csv")
    _write_frame(official, args.output / "official-1m.csv")
    _write_frame(support_bars, args.output / "support-history-1m.csv")
    _write_frame(support, args.output / "support-available.csv")

    levels = {
        str(level): _first_eligible_at_or_above(trades, level)
        for level in (5.5, 5.75, 6.0, 6.3, 6.5, 7.0)
    }
    at_six, at_fill = levels["6.0"], levels["6.3"]
    seconds_6_to_63 = None
    if at_six and at_fill:
        seconds_6_to_63 = (
            pd.Timestamp(at_fill["timestamp"]) - pd.Timestamp(at_six["timestamp"])
        ).total_seconds()
    pullbacks = detect_running_high_pullbacks(bars_10s, start_at=QUALIFIED_AT)
    pullback_rows = [
        {
            "ordinal": item.ordinal,
            "peak_time": item.peak_time.isoformat(),
            "peak_high": item.peak_high,
            "pullback_start": item.pullback_start.isoformat(),
            "trough_time": item.trough_time.isoformat(),
            "trough_low": item.trough_low,
            "resumption_time": item.resumption_time.isoformat(),
            "resumption_high": item.resumption_high,
            "pullback_bars": item.pullback_bars,
            "pullback_mean_volume": item.pullback_mean_volume,
            "peak_drawdown_fraction": item.peak_drawdown_fraction,
        }
        for item in pullbacks
    ]
    summary = {
        "symbol": "VRAX",
        "trading_date": trading_date.isoformat(),
        "candidate_qualified_at": QUALIFIED_AT.isoformat(),
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "feed": "sip",
        "trade_count": len(trades),
        "ten_second_bar_count": len(bars_10s),
        "unknown_condition_bars": int(
            (bars_10s["unknown_condition_count"] > 0).sum()
        ),
        "eligible_level_crossings": levels,
        "seconds_from_6_to_first_eligible_6_30_plus": seconds_6_to_63,
        "observed_pullbacks_after_qualification": pullback_rows,
        "micro_geometry_research_diagnostics": _micro_geometry_diagnostics(
            bars_10s, trades, end=end
        ),
        "canonical_micro_support_diagnostics": _canonical_support_diagnostics(
            bars_10s, trades, support, end=end
        ),
        "raw_min_price": float(trades["price"].min()),
        "raw_max_price": float(trades["price"].max()),
        "minute_comparison": _compare_minute_bars(reconstructed_1m, official),
        "provenance": {
            "micro_bars": "derived_from_historical_sip_trade_prints_using_alpaca_minute_trade_condition_rules",
            "official_bars": "alpaca_historical_sip_1min",
            "micro_geometry_policy": "research_only_and_independent_of_recap_labels",
            "psychological_level_context": "rule-derived_context_candidates_not_ground_truth_selected",
            "canonical_support": "session_vwap_and_ema9_from_alpaca_sip_1min_history_available_only_at_bar_completion",
        },
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
