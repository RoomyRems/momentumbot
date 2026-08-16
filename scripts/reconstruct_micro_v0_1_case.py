from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.historical_data import discover_market_day
from momentumbot.indicators import completed_bar_support_series
from momentumbot.micro_bars import aggregate_trade_bars
from momentumbot.micro_execution import MicroTriggerMode
from momentumbot.micro_policy import micro_v0_1_policy
from momentumbot.micro_replay import micro_replay_runtime_artifact, replay_micro_candidate
from momentumbot.models import current_general_2026
from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.providers.alpaca_trades import historical_trades
from momentumbot.research.benchmark_market import direct_historical_target_qualification

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


def _candidate_row(discovery, symbol: str):
    return next((row for row in discovery.rows if row.symbol == symbol), None)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reconstruct one benchmark case using market data only and replay the "
            "frozen deterministic Micro v0.1 policy. No retrospective benchmark "
            "file is accepted by this program."
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

    discovery = discover_market_day(
        client,
        trading_date=trading_date,
        profile=profile,
    )
    row = _candidate_row(discovery, symbol)
    direct = None
    if row is None:
        direct = direct_historical_target_qualification(
            client,
            symbol=symbol,
            trading_date=trading_date,
            profile=profile,
        )

    if row is not None:
        target_row = asdict(row)
        first_qualified_at = row.first_market_qualified_at
        anchor_source = "full_market_discovery_current_provider_asset_master"
    elif direct is not None:
        target_row = asdict(direct)
        first_qualified_at = direct.first_market_qualified_at
        anchor_source = "direct_historical_target_fallback_missing_from_current_asset_master"
    else:
        target_row = None
        first_qualified_at = None
        anchor_source = "unresolved_historical_target"

    discovery_summary = {
        "case_id": args.case_id,
        "symbol": symbol,
        "trading_date": trading_date.isoformat(),
        "knowledge_policy": "market_data_only_no_retrospective_behavior_labels",
        "candidate_anchor_scope": (
            "causal_market_momentum_stage_price_gain_same_time_rvol_price_band; "
            "full point_in_time_float/news quality is not scored in this micro setup benchmark"
        ),
        "candidate_anchor_source": anchor_source,
        "historical_target_fallback_limitations": (
            [
                "fallback proves only causal target-symbol price/gain/RVOL qualification",
                "fallback does not establish historical cross-sectional rank",
                "fallback does not claim the provider's current asset master is a point-in-time universe",
            ]
            if direct is not None and row is None
            else []
        ),
        "market_discovery": {
            "asset_count": discovery.asset_count,
            "listed_asset_count": discovery.listed_asset_count,
            "daily_superset_count": discovery.daily_superset_count,
            "rvol_prefilter_count": discovery.rvol_prefilter_count,
            "market_candidate_count": discovery.market_candidate_count,
        },
        "target_discovery_row": target_row,
        "frozen_policy_id": frozen.policy_id,
        "frozen_policy_fingerprint": frozen.fingerprint,
    }

    if first_qualified_at is None:
        runtime = {
            "artifact_type": "micro_candidate_runtime_replay_unavailable",
            "schema_version": 1,
            "knowledge_policy": "runtime_market_data_only_no_retrospective_labels",
            "case_id": args.case_id,
            "symbol": symbol,
            "trading_date": trading_date.isoformat(),
            "status": "target_did_not_reach_market_momentum_qualification",
            "candidate_anchor_source": anchor_source,
            "frozen_policy_id": frozen.policy_id,
            "frozen_policy_fingerprint": frozen.fingerprint,
            "market_discovery": discovery_summary["market_discovery"],
            "target_discovery_row": target_row,
        }
        (output / "runtime-replay.json").write_text(
            json.dumps(runtime, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (output / "runtime-context.json").write_text(
            json.dumps(discovery_summary, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(runtime, indent=2, sort_keys=True))
        return 0

    qualified_at = pd.Timestamp(first_qualified_at)
    if qualified_at.tzinfo is None:
        raise RuntimeError("qualification timestamp is not timezone-aware")
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
            "frozen_policy_id": frozen.policy_id,
            "frozen_policy_fingerprint": frozen.fingerprint,
            "frozen_policy_status": frozen.status,
            "candidate_anchor_scope": discovery_summary["candidate_anchor_scope"],
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
    discovery_summary["candidate_qualified_at"] = qualified_at.isoformat()
    discovery_summary["replay_end"] = replay_end.isoformat()
    discovery_summary["runtime_counts"] = {
        "trade_prints": len(trades),
        "micro_bars": len(bars_10s),
        "plans": replay.plan_count,
        "fills": replay.filled_count,
        "filled_pullback_numbers": list(replay.filled_pullback_numbers),
    }
    (output / "runtime-context.json").write_text(
        json.dumps(discovery_summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(runtime, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
