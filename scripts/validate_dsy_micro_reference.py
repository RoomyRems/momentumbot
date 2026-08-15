from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.micro_bars import aggregate_trade_bars, minute_trade_eligibility
from momentumbot.micro_execution import (
    MicroExecutionOutcome,
    completed_bar_breakout_plans,
    execution_eligible_trades,
    simulate_micro_entries,
)
from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.providers.alpaca_trades import historical_trades

ET = ZoneInfo("America/New_York")
SYMBOL = "DSY"
TRADING_DATE = date(2026, 6, 10)
REFERENCE_PRICE = 3.00
REPORTED_FILL_LOW = 3.07
REPORTED_FILL_HIGH = 3.11


def _utc(hour: int, minute: int) -> datetime:
    return datetime.combine(TRADING_DATE, time(hour, minute), ET).astimezone(timezone.utc)


def _chart_price_eligible_rows(trades: pd.DataFrame) -> pd.DataFrame:
    mask: list[bool] = []
    for _, row in trades.iterrows():
        eligibility = minute_trade_eligibility(row.get("tape"), row.get("conditions") or ())
        mask.append(eligibility.updates_price)
    return trades.loc[mask]


def _event(timestamp: pd.Timestamp, row: pd.Series) -> dict[str, object]:
    return {
        "timestamp": timestamp.isoformat(),
        "price": float(row["price"]),
        "size": int(row["size"]),
        "conditions": str(row.get("conditions")),
        "via_odd_lot_proxy": bool(row.get("_execution_via_odd_lot", False)),
    }


def _outcome_row(outcome: MicroExecutionOutcome) -> dict[str, object]:
    plan = outcome.plan
    return {
        "source_bar_start": plan.source_bar_start.isoformat(),
        "armed_at": plan.armed_at.isoformat(),
        "expires_at": plan.expires_at.isoformat(),
        "breakout_level": plan.breakout_level,
        "minimum_new_high_price": plan.minimum_new_high_price,
        "stop_price": plan.stop_price,
        "status": outcome.status.value,
        "trigger_time": outcome.trigger_time.isoformat() if outcome.trigger_time is not None else None,
        "trigger_print_price": outcome.trigger_print_price,
        "trigger_via_odd_lot": outcome.trigger_via_odd_lot,
        "fill_time": outcome.fill_time.isoformat() if outcome.fill_time is not None else None,
        "fill_price": outcome.fill_price,
        "entry_slippage": outcome.entry_slippage,
        "exit_time": outcome.exit_time.isoformat() if outcome.exit_time is not None else None,
        "exit_price": outcome.exit_price,
        "exit_via_odd_lot": outcome.exit_via_odd_lot,
        "realized_r": outcome.realized_r,
    }


def _distance_to_reported_fill(price: float) -> float:
    if REPORTED_FILL_LOW <= price <= REPORTED_FILL_HIGH:
        return 0.0
    return min(abs(price - REPORTED_FILL_LOW), abs(price - REPORTED_FILL_HIGH))


def _first_in_zone(frame: pd.DataFrame) -> dict[str, object] | None:
    if frame.empty:
        return None
    prices = pd.to_numeric(frame["price"], errors="coerce")
    in_zone = frame[(prices >= REPORTED_FILL_LOW) & (prices <= REPORTED_FILL_HIGH)]
    if in_zone.empty:
        return None
    return _event(in_zone.index[0], in_zone.iloc[0])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconstruct the June 10 DSY chart-confirmed micro reference from SIP prints."
    )
    parser.add_argument("--output", type=Path, default=Path("dsy-micro-reference"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    client = AlpacaDataClient.from_env()
    session_start, session_end = _utc(4, 0), _utc(10, 0)
    minute = client.bars(
        [SYMBOL],
        timeframe="1Min",
        start=session_start,
        end=session_end,
        feed="sip",
        adjustment="raw",
        asof=TRADING_DATE,
    )[SYMBOL]
    if minute.empty:
        raise RuntimeError("Alpaca returned no DSY minute bars")
    crossing_minutes = minute[pd.to_numeric(minute["high"]) >= REFERENCE_PRICE]
    if crossing_minutes.empty:
        raise RuntimeError("DSY never reached the reported ~$3 area")
    first_reference_minute = crossing_minutes.index[0]

    tape_start = first_reference_minute - pd.Timedelta(minutes=3)
    tape_end = first_reference_minute + pd.Timedelta(minutes=6)
    trades = historical_trades(
        client,
        SYMBOL,
        start=tape_start.to_pydatetime(),
        end=tape_end.to_pydatetime(),
        feed="sip",
        asof=TRADING_DATE,
    )
    if trades.empty:
        raise RuntimeError("Alpaca returned no DSY trades around the reference move")

    chart_path = _chart_price_eligible_rows(trades)
    execution_path = execution_eligible_trades(trades)
    bars_10s = aggregate_trade_bars(trades, "10s")
    bars_1s = aggregate_trade_bars(trades, "1s")

    trades.reset_index().to_csv(args.output / "trades.csv", index=False)
    bars_10s.reset_index().to_csv(args.output / "bars-10s.csv", index=False)
    bars_1s.reset_index().to_csv(args.output / "bars-1s.csv", index=False)
    minute.loc[tape_start:tape_end].reset_index().to_csv(
        args.output / "official-1m.csv", index=False
    )

    # Runtime candidate generation is deliberately independent of the recap's
    # reported fill prices. Every completed 10-second bar that finishes below
    # its own high may arm a next-bar new-high plan. The reported fills are used
    # only after simulation to score imitation fidelity.
    plans = completed_bar_breakout_plans(
        SYMBOL,
        bars_10s,
        bar_seconds=10,
        tick_size=0.01,
        start_at=tape_start,
    )
    outcomes = simulate_micro_entries(plans, trades, exit_until=tape_end)
    filled_outcomes = [outcome for outcome in outcomes if outcome.fill_price is not None]
    nearest_source_outcome = None
    if filled_outcomes:
        nearest_source_outcome = min(
            filled_outcomes,
            key=lambda outcome: _distance_to_reported_fill(float(outcome.fill_price)),
        )
    nearby_outcomes = [
        outcome
        for outcome in filled_outcomes
        if REPORTED_FILL_LOW - 0.35
        <= float(outcome.fill_price)
        <= REPORTED_FILL_HIGH + 0.35
    ]

    summary = {
        "symbol": SYMBOL,
        "trading_date": TRADING_DATE.isoformat(),
        "first_minute_high_at_or_above_3": first_reference_minute.isoformat(),
        "reported_fill_zone": [REPORTED_FILL_LOW, REPORTED_FILL_HIGH],
        "retrospective_ground_truth_diagnostics": {
            "runtime_uses_reported_fill_zone": False,
            "first_chart_price_eligible_print_in_reported_fill_zone": _first_in_zone(
                chart_path
            ),
            "first_execution_proxy_print_in_reported_fill_zone": _first_in_zone(
                execution_path
            ),
        },
        "causal_intrabar_execution": {
            "plan_generation": "completed_10s_bar_finishes_below_its_high_then_next_bar_must_make_new_high",
            "entry_window": "immediately_following_10s_bar_only",
            "fill_model": "first_execution_eligible_sip_print_at_or_above_prior_high_plus_tick",
            "stop_model": "first_later_execution_eligible_sip_print_at_or_below_completed_bar_low",
            "chart_price_path": "alpaca_minute_price_eligible_sip_prints_only",
            "execution_price_proxy": "chart_price_eligible_plus_otherwise_clean_odd_lot_sip_prints",
            "execution_proxy_limitations": [
                "observed print price does not guarantee a fill for the strategy order",
                "print size, displayed depth, hidden depth, queue priority, and order latency are not yet modeled",
                "odd lots remain excluded from derived chart OHLC",
            ],
            "sip_execution_path_normalized_once_for_all_plans": True,
            "plan_count": len(plans),
            "filled_plan_count": len(filled_outcomes),
            "nearest_reported_fill_after_the_fact": (
                _outcome_row(nearest_source_outcome)
                if nearest_source_outcome is not None
                else None
            ),
            "filled_events_near_reported_price_for_diagnostics": [
                _outcome_row(outcome) for outcome in nearby_outcomes
            ],
        },
        "trade_count": len(trades),
        "chart_price_eligible_trade_count": len(chart_path),
        "execution_proxy_trade_count": len(execution_path),
        "execution_proxy_odd_lot_trade_count": int(
            execution_path["_execution_via_odd_lot"].fillna(False).astype(bool).sum()
        ),
        "ten_second_bar_count": len(bars_10s),
        "one_second_bar_count": len(bars_1s),
        "tape_window": {"start": tape_start.isoformat(), "end": tape_end.isoformat()},
        "provenance": {
            "trades": "alpaca_historical_sip",
            "micro_bars": "derived_from_sip_trades_using_alpaca_minute_trade_condition_rules",
            "chart_execution_separation": "odd_lots_cannot_set_chart_price_but_otherwise_clean_odd_lots_can_inform_execution_price_proxy",
            "execution": "ordered_execution_proxy_sip_prints_after_completed_micro_bar",
        },
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
