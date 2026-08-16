from __future__ import annotations

import argparse
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
from momentumbot.micro_replay import micro_replay_runtime_artifact, replay_micro_candidate
from momentumbot.models import current_general_2026
from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.providers.alpaca_trades import historical_trades
from momentumbot.research.benchmark_market import (
    direct_historical_target_qualification,
    refine_candidate_minute_with_sip,
)

ET = ZoneInfo("America/New_York")
EMA_WARMUP_CALENDAR_DAYS = 7
REPLAY_HORIZON_MINUTES = 15


def _utc_session_start(trading_date: date) -> datetime:
    return datetime.combine(trading_date, time(4, 0), ET).astimezone(timezone.utc)


def _utc_entry_cutoff(trading_date: date) -> datetime:
    return datetime.combine(trading_date, time(10, 0), ET).astimezone(timezone.utc)


def _write_frame(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.reset_index().to_csv(path, index=False)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reconstruct one benchmark case using target-symbol historical market data "
            "only and replay the frozen deterministic Micro v0.1 policy. No "
            "retrospective benchmark file is accepted by this program."
        )
    )
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--trading-date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    symbol = args.symbol.upper().strip()
    trading_date = date.fromisoformat(args.trading_date)
    output = args.output
    output.mkdir(parents=True, exist_ok=True)

    profile = current_general_2026()
    frozen = micro_v0_1_policy()
    client = AlpacaDataClient.from_env()

    # Benchmark reconstruction intentionally uses the known historical symbol/date
    # only. This validates whether the frozen micro layer can reproduce behavior
    # once a named historical candidate satisfies the measurable price/gain/RVOL
    # gate. It does not use the human entry/outcome label and it does not claim to
    # reconstruct historical cross-sectional rank or the complete point-in-time
    # tradable universe; those belong to the later full-market backtest phase.
    direct = direct_historical_target_qualification(
        client,
        symbol=symbol,
        trading_date=trading_date,
        profile=profile,
    )
    target_row = asdict(direct) if direct is not None else None
    first_acquisition_minute = (
        direct.first_market_qualified_at if direct is not None else None
    )
    previous_close = direct.previous_close if direct is not None else None
    anchor_source = "direct_historical_target_price_gain_same_time_rvol"

    context = {
        "case_id": args.case_id,
        "symbol": symbol,
        "trading_date": trading_date.isoformat(),
        "knowledge_policy": "market_data_only_no_retrospective_behavior_labels",
        "candidate_anchor_scope": (
            "target_symbol_historical_price_gain_same_time_rvol_price_band; "
            "historical cross_sectional rank, point_in_time universe, float, and news "
            "are deliberately outside this micro setup benchmark"
        ),
        "candidate_anchor_source": anchor_source,
        "target_qualification": target_row,
        "benchmark_scope_limitations": [
            "symbol/date identity is benchmark metadata, not a human behavior label",
            "target-only qualification does not establish historical top-gainer rank",
            "target-only qualification does not reconstruct the full historical tradable universe",
            "float/news quality belongs to the later stock-selection benchmark/backtest layer",
        ],
        "frozen_policy_id": frozen.policy_id,
        "frozen_policy_fingerprint": frozen.fingerprint,
    }

    if first_acquisition_minute is None or previous_close is None:
        runtime = {
            "artifact_type": "micro_candidate_runtime_replay_unavailable",
            "schema_version": 1,
            "knowledge_policy": "runtime_market_data_only_no_retrospective_labels",
            "case_id": args.case_id,
            "symbol": symbol,
            "trading_date": trading_date.isoformat(),
            "status": "target_did_not_reach_direct_price_gain_rvol_qualification",
            "candidate_anchor_source": anchor_source,
            "frozen_policy_id": frozen.policy_id,
            "frozen_policy_fingerprint": frozen.fingerprint,
            "target_qualification": target_row,
        }
        (output / "runtime-replay.json").write_text(
            json.dumps(runtime, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (output / "runtime-context.json").write_text(
            json.dumps(context, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(runtime, indent=2, sort_keys=True))
        return 0

    acquisition_minute = pd.Timestamp(first_acquisition_minute)
    if acquisition_minute.tzinfo is None:
        raise RuntimeError("acquisition-minute timestamp is not timezone-aware")
    acquisition_minute = acquisition_minute.floor("min")
    refined = refine_candidate_minute_with_sip(
        client,
        symbol=symbol,
        trading_date=trading_date,
        candidate_minute_start=acquisition_minute,
        previous_close=float(previous_close),
        profile=profile,
    )
    if refined.qualified_at is not None:
        qualified_at = pd.Timestamp(refined.qualified_at)
        decision_time_source = "sip_intraminute_refinement"
    else:
        # The one-minute acquisition bar's close/volume are only knowable after
        # completion. Never expose its bar-start timestamp to the micro policy.
        qualified_at = acquisition_minute + pd.Timedelta(minutes=1)
        decision_time_source = "completed_acquisition_minute_fallback"
    if qualified_at.tzinfo is None:
        raise RuntimeError("qualification timestamp is not timezone-aware")

    context["acquisition_minute_start"] = acquisition_minute.isoformat()
    context["intraminute_refinement"] = asdict(refined)
    context["candidate_qualified_at"] = qualified_at.isoformat()
    context["decision_time_source"] = decision_time_source

    cutoff = pd.Timestamp(_utc_entry_cutoff(trading_date))
    replay_end = min(qualified_at + pd.Timedelta(minutes=REPLAY_HORIZON_MINUTES), cutoff)
    if replay_end <= qualified_at:
        raise RuntimeError("candidate qualified at or after the entry cutoff")

    trades = historical_trades(
        client,
        symbol,
        start=qualified_at.to_pydatetime(),
        end=replay_end.to_pydatetime(),
        feed="sip",
        asof=trading_date,
    )
    if trades.empty:
        raise RuntimeError(f"Alpaca returned no SIP trades for {symbol} after qualification")
    bars_10s = aggregate_trade_bars(trades, "10s")
    if bars_10s.empty:
        raise RuntimeError(f"could not derive 10-second bars for {symbol}")

    session_start = pd.Timestamp(_utc_session_start(trading_date))
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

    replay = replay_micro_candidate(
        symbol,
        bars_10s,
        trades,
        candidate_qualified_at=qualified_at,
        policy=frozen.setup,
        vwap_available=support["vwap"],
        ema9_available=support["ema"],
        trigger_mode=MicroTriggerMode.CHART_PRICE,
        entry_latency_ms=0.0,
        exit_until=replay_end,
    )
    runtime = micro_replay_runtime_artifact(replay)
    runtime.update(
        {
            "case_id": args.case_id,
            "trading_date": trading_date.isoformat(),
            "candidate_anchor_source": anchor_source,
            "candidate_acquisition_minute_start": acquisition_minute.isoformat(),
            "candidate_decision_time_source": decision_time_source,
            "intraminute_refinement": asdict(refined),
            "frozen_policy_id": frozen.policy_id,
            "frozen_policy_fingerprint": frozen.fingerprint,
            "frozen_policy_status": frozen.status,
            "candidate_anchor_scope": context["candidate_anchor_scope"],
            "replay_horizon_minutes": REPLAY_HORIZON_MINUTES,
            "replay_end": replay_end.isoformat(),
            "support_contract": {
                "vwap": "raw current session from 04:00 ET; values available after minute completion",
                "ema9": "split-normalized prior one-minute warmup plus raw current session; values available after minute completion",
                "ema_warmup_calendar_days": EMA_WARMUP_CALENDAR_DAYS,
                "ema_warmup_bar_count": len(split_history),
                "session_minute_bar_count": len(current_session),
            },
        }
    )

    _write_frame(trades, output / "trades.csv")
    _write_frame(bars_10s, output / "bars-10s.csv")
    _write_frame(support, output / "support-available.csv")
    _write_frame(current_session, output / "session-1m.csv")
    _write_frame(split_history, output / "ema-warmup-1m.csv")
    (output / "runtime-replay.json").write_text(
        json.dumps(runtime, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    context["replay_end"] = replay_end.isoformat()
    context["runtime_counts"] = {
        "trade_prints": len(trades),
        "micro_bars": len(bars_10s),
        "plans": replay.plan_count,
        "fills": replay.filled_count,
        "filled_pullback_numbers": list(replay.filled_pullback_numbers),
    }
    (output / "runtime-context.json").write_text(
        json.dumps(context, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(runtime, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
