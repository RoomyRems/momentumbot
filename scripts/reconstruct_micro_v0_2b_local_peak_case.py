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
from momentumbot.models import current_general_2026
from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.providers.alpaca_trades import historical_trades
from momentumbot.research.benchmark_market import (
    direct_historical_target_qualification,
    refine_candidate_minute_with_sip,
)
from momentumbot.research.micro_local_peak_ablation import (
    local_peak_runtime_artifact,
    micro_v0_2b_local_peak_ablation,
    replay_micro_candidate_with_local_peak,
)

ET = ZoneInfo("America/New_York")
EMA_WARMUP_CALENDAR_DAYS = 7


def _utc_session_start(trading_date: date) -> datetime:
    return datetime.combine(trading_date, time(4, 0), ET).astimezone(timezone.utc)


def _utc_entry_cutoff(trading_date: date, cutoff: time) -> datetime:
    return datetime.combine(trading_date, cutoff, ET).astimezone(timezone.utc)


def _write_frame(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.reset_index().to_csv(path, index=False)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reconstruct one label-blind historical case for the Micro v0.2b "
            "local-impulse-peak ablation."
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
    parent = micro_v0_1_policy()
    ablation = micro_v0_2b_local_peak_ablation()
    client = AlpacaDataClient.from_env()

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

    context: dict[str, object] = {
        "case_id": args.case_id,
        "symbol": symbol,
        "trading_date": trading_date.isoformat(),
        "knowledge_policy": "market_data_only_no_retrospective_behavior_labels",
        "candidate_anchor_scope": (
            "target_symbol_historical_price_gain_same_time_rvol_price_band; "
            "historical cross_sectional rank, point_in_time universe, float, and news "
            "are deliberately outside this micro setup ablation"
        ),
        "candidate_anchor_source": anchor_source,
        "target_qualification": target_row,
        "ablation_id": ablation.ablation_id,
        "ablation_fingerprint": ablation.fingerprint,
        "ablation_status": ablation.status,
        "parent_frozen_policy_id": parent.policy_id,
        "parent_frozen_policy_fingerprint": parent.fingerprint,
        "peak_rule": ablation.peak_rule,
        "peak_scope_bars": ablation.peak_scope_bars,
        "structural_context_rule": ablation.structural_context_rule,
        "pullback_ordinal_rule": ablation.pullback_ordinal_rule,
        "ablation_isolation": (
            "only the peak scope changes from all postqualification highs to the "
            "parent five-bar impulse lookback; all other v0.1 setup/execution rules are reused"
        ),
    }

    if first_acquisition_minute is None or previous_close is None:
        runtime = {
            "artifact_type": "micro_candidate_runtime_replay_ablation_unavailable",
            "schema_version": 2,
            "knowledge_policy": "runtime_market_data_only_no_retrospective_labels",
            "case_id": args.case_id,
            "symbol": symbol,
            "trading_date": trading_date.isoformat(),
            "status": "target_did_not_reach_direct_price_gain_rvol_qualification",
            "candidate_anchor_source": anchor_source,
            "ablation_id": ablation.ablation_id,
            "ablation_fingerprint": ablation.fingerprint,
            "parent_frozen_policy_id": parent.policy_id,
            "parent_frozen_policy_fingerprint": parent.fingerprint,
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
        qualified_at = acquisition_minute + pd.Timedelta(minutes=1)
        decision_time_source = "completed_acquisition_minute_fallback"
    if qualified_at.tzinfo is None:
        raise RuntimeError("qualification timestamp is not timezone-aware")

    replay_end = pd.Timestamp(
        _utc_entry_cutoff(trading_date, profile.no_new_entries_after)
    )
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

    result = replay_micro_candidate_with_local_peak(
        symbol,
        bars_10s,
        trades,
        candidate_qualified_at=qualified_at,
        spec=ablation,
        policy=parent.setup,
        vwap_available=support["vwap"],
        ema9_available=support["ema"],
        trigger_mode=MicroTriggerMode.CHART_PRICE,
        entry_latency_ms=0.0,
        exit_until=replay_end,
    )
    replay = result.replay
    runtime = local_peak_runtime_artifact(result)
    runtime.update(
        {
            "case_id": args.case_id,
            "trading_date": trading_date.isoformat(),
            "candidate_anchor_source": anchor_source,
            "candidate_anchor_scope": context["candidate_anchor_scope"],
            "candidate_acquisition_minute_start": acquisition_minute.isoformat(),
            "candidate_decision_time_source": decision_time_source,
            "intraminute_refinement": asdict(refined),
            "replay_window_policy": "candidate_qualification_to_no_new_entries_after",
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

    context.update(
        {
            "acquisition_minute_start": acquisition_minute.isoformat(),
            "intraminute_refinement": asdict(refined),
            "candidate_qualified_at": qualified_at.isoformat(),
            "decision_time_source": decision_time_source,
            "replay_end": replay_end.isoformat(),
            "replay_window_policy": "candidate_qualification_to_no_new_entries_after",
            "runtime_counts": {
                "trade_prints": len(trades),
                "micro_bars": len(bars_10s),
                "plans": replay.plan_count,
                "fills": replay.filled_count,
                "filled_pullback_numbers": list(replay.filled_pullback_numbers),
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
    (output / "runtime-context.json").write_text(
        json.dumps(context, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(runtime, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
