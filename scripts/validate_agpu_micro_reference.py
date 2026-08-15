from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.micro_bars import aggregate_trade_bars, minute_trade_eligibility
from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.providers.alpaca_trades import historical_trades

ET = ZoneInfo("America/New_York")
SYMBOL = "AGPU"
TRADING_DATE = date(2026, 4, 22)
REFERENCE_HIGH = 8.50
SUPPORT_LEVEL = 8.00


def _utc(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime.combine(TRADING_DATE, time(hour, minute, second), ET).astimezone(timezone.utc)


def _eligible_rows(trades: pd.DataFrame) -> pd.DataFrame:
    mask = []
    for _, row in trades.iterrows():
        eligibility = minute_trade_eligibility(row.get("tape"), row.get("conditions") or ())
        mask.append(eligibility.updates_price)
    return trades.loc[mask]


def _event(row_index: pd.Timestamp, row: pd.Series) -> dict[str, object]:
    return {
        "timestamp": row_index.isoformat(),
        "price": float(row["price"]),
        "size": int(row["size"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconstruct the April 22 AGPU micro-pullback case study from SIP prints.")
    parser.add_argument("--output", type=Path, default=Path("agpu-micro-reference"))
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
        raise RuntimeError("Alpaca returned no AGPU minute bars")
    crossing_minutes = minute[pd.to_numeric(minute["high"]) >= REFERENCE_HIGH]
    if crossing_minutes.empty:
        raise RuntimeError("AGPU never reached the reported $8.50 reference level")
    first_cross_minute = crossing_minutes.index[0]

    tape_start = first_cross_minute - pd.Timedelta(minutes=2)
    tape_end = first_cross_minute + pd.Timedelta(minutes=6)
    trades = historical_trades(
        client,
        SYMBOL,
        start=tape_start.to_pydatetime(),
        end=tape_end.to_pydatetime(),
        feed="sip",
        asof=TRADING_DATE,
    )
    if trades.empty:
        raise RuntimeError("Alpaca returned no AGPU trades around the reference move")
    eligible = _eligible_rows(trades)

    initial = eligible[pd.to_numeric(eligible["price"]) >= REFERENCE_HIGH]
    if initial.empty:
        raise RuntimeError("No price-eligible print reached the reported $8.50 high")
    first_high_time = initial.index[0]
    first_high_row = initial.iloc[0]

    after_high = eligible.loc[first_high_time:]
    support = after_high[pd.to_numeric(after_high["price"]) <= SUPPORT_LEVEL]
    support_time = None
    support_row = None
    recross_time = None
    recross_row = None
    trough_time = None
    trough_price = None
    if not support.empty:
        support_time = support.index[0]
        support_row = support.iloc[0]
        after_support = eligible.loc[support_time:]
        recross = after_support[pd.to_numeric(after_support["price"]) >= REFERENCE_HIGH]
        if not recross.empty:
            recross_time = recross.index[0]
            recross_row = recross.iloc[0]
            interval = eligible.loc[support_time:recross_time]
            trough_time = interval["price"].idxmin()
            trough_price = float(interval.loc[trough_time, "price"])

    bars_10s = aggregate_trade_bars(trades, "10s")
    bars_1s = aggregate_trade_bars(trades, "1s")
    trades.reset_index().to_csv(args.output / "trades.csv", index=False)
    bars_10s.reset_index().to_csv(args.output / "bars-10s.csv", index=False)
    bars_1s.reset_index().to_csv(args.output / "bars-1s.csv", index=False)
    minute.loc[tape_start:tape_end].reset_index().to_csv(args.output / "official-1m.csv", index=False)

    summary = {
        "symbol": SYMBOL,
        "trading_date": TRADING_DATE.isoformat(),
        "first_minute_high_at_or_above_8_50": first_cross_minute.isoformat(),
        "first_price_eligible_print_at_or_above_8_50": _event(first_high_time, first_high_row),
        "first_price_eligible_print_at_or_below_8_after_high": (
            _event(support_time, support_row) if support_time is not None and support_row is not None else None
        ),
        "first_price_eligible_recross_8_50_after_support": (
            _event(recross_time, recross_row) if recross_time is not None and recross_row is not None else None
        ),
        "trough_between_support_and_recross": (
            {"timestamp": trough_time.isoformat(), "price": trough_price}
            if trough_time is not None else None
        ),
        "trade_count": len(trades),
        "ten_second_bar_count": len(bars_10s),
        "one_second_bar_count": len(bars_1s),
        "tape_window": {"start": tape_start.isoformat(), "end": tape_end.isoformat()},
        "source_reported": {
            "entry_fills": [8.33, 8.50],
            "stop_approx": 8.00,
            "confirmation_level": 8.50,
            "initial_target": 9.00,
        },
        "provenance": {
            "trades": "alpaca_historical_sip",
            "micro_bars": "derived_from_sip_trades_using_alpaca_minute_trade_condition_rules",
        },
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
