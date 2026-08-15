from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.micro_bars import aggregate_trade_bars
from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.providers.alpaca_trades import historical_trades

ET = ZoneInfo("America/New_York")


def _utc(day: date, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute, second), ET).astimezone(timezone.utc)


def _write_frame(frame: pd.DataFrame, path: Path) -> None:
    frame.reset_index().to_csv(path, index=False)


def _first_price_at_or_above(trades: pd.DataFrame, level: float) -> dict | None:
    eligible = trades[pd.to_numeric(trades["price"]) >= level]
    if eligible.empty:
        return None
    timestamp = eligible.index[0]
    row = eligible.iloc[0]
    return {"timestamp": timestamp.isoformat(), "price": float(row["price"]), "size": int(row["size"])}


def _compare_minute_bars(reconstructed: pd.DataFrame, official: pd.DataFrame) -> list[dict]:
    output: list[dict] = []
    common = reconstructed.index.intersection(official.index)
    for timestamp in common:
        left = reconstructed.loc[timestamp]
        right = official.loc[timestamp]
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the July 9 VRAX micro-timeframe reference trade.")
    parser.add_argument("--output", type=Path, default=Path("vrax-micro-reference"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    trading_date = date(2026, 7, 9)
    start = _utc(trading_date, 7, 29, 30)
    end = _utc(trading_date, 7, 34, 30)
    client = AlpacaDataClient.from_env()
    trades = historical_trades(client, "VRAX", start=start, end=end, feed="sip", asof=trading_date)
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

    _write_frame(trades, args.output / "trades.csv")
    _write_frame(bars_10s, args.output / "bars-10s.csv")
    _write_frame(reconstructed_1m, args.output / "reconstructed-1m.csv")
    _write_frame(official, args.output / "official-1m.csv")

    summary = {
        "symbol": "VRAX",
        "trading_date": trading_date.isoformat(),
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "feed": "sip",
        "trade_count": len(trades),
        "ten_second_bar_count": len(bars_10s),
        "unknown_condition_bars": int((bars_10s["unknown_condition_count"] > 0).sum()) if not bars_10s.empty else 0,
        "first_raw_trade_at_or_above_6": _first_price_at_or_above(trades, 6.0),
        "raw_min_price": float(trades["price"].min()),
        "raw_max_price": float(trades["price"].max()),
        "minute_comparison": _compare_minute_bars(reconstructed_1m, official),
        "provenance": {
            "micro_bars": "derived_from_historical_sip_trade_prints_using_alpaca_minute_trade_condition_rules",
            "official_bars": "alpaca_historical_sip_1min",
        },
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
