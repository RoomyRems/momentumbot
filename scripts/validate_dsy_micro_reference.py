from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.micro_bars import aggregate_trade_bars, minute_trade_eligibility
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


def _eligible_rows(trades: pd.DataFrame) -> pd.DataFrame:
    mask: list[bool] = []
    for _, row in trades.iterrows():
        eligibility = minute_trade_eligibility(row.get("tape"), row.get("conditions") or ())
        mask.append(eligibility.updates_price)
    return trades.loc[mask]


def _event(timestamp: pd.Timestamp, row: pd.Series) -> dict[str, object]:
    return {"timestamp": timestamp.isoformat(), "price": float(row["price"]), "size": int(row["size"])}


def _crossing_candle_events(bars: pd.DataFrame) -> list[dict[str, object]]:
    """Describe possible first-new-high events without deciding that they are trades."""
    output: list[dict[str, object]] = []
    if len(bars) < 3:
        return output
    for index in range(2, len(bars)):
        prior2 = bars.iloc[index - 2]
        prior = bars.iloc[index - 1]
        current = bars.iloc[index]
        pause = float(prior["close"]) < float(prior["open"]) or float(prior["close"]) < float(prior2["close"])
        if not pause or float(current["high"]) <= float(prior["high"]):
            continue
        output.append(
            {
                "timestamp": bars.index[index].isoformat(),
                "trigger_from_prior_high": round(float(prior["high"]) + 0.01, 4),
                "prior_high": float(prior["high"]),
                "prior_low": float(prior["low"]),
                "current_high": float(current["high"]),
            }
        )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconstruct the June 10 DSY chart-confirmed micro reference from SIP prints.")
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
    eligible = _eligible_rows(trades)
    in_fill_zone = eligible[
        (pd.to_numeric(eligible["price"]) >= REPORTED_FILL_LOW)
        & (pd.to_numeric(eligible["price"]) <= REPORTED_FILL_HIGH)
    ]

    bars_10s = aggregate_trade_bars(trades, "10s")
    bars_1s = aggregate_trade_bars(trades, "1s")
    trades.reset_index().to_csv(args.output / "trades.csv", index=False)
    bars_10s.reset_index().to_csv(args.output / "bars-10s.csv", index=False)
    bars_1s.reset_index().to_csv(args.output / "bars-1s.csv", index=False)
    minute.loc[tape_start:tape_end].reset_index().to_csv(args.output / "official-1m.csv", index=False)

    first_fill_zone = None
    if not in_fill_zone.empty:
        first_fill_zone = _event(in_fill_zone.index[0], in_fill_zone.iloc[0])
    crossings = _crossing_candle_events(bars_10s)
    nearby_crossings = [
        row for row in crossings
        if REPORTED_FILL_LOW - 0.40 <= float(row["trigger_from_prior_high"]) <= REPORTED_FILL_HIGH + 0.40
    ]

    summary = {
        "symbol": SYMBOL,
        "trading_date": TRADING_DATE.isoformat(),
        "first_minute_high_at_or_above_3": first_reference_minute.isoformat(),
        "first_price_eligible_print_in_reported_fill_zone": first_fill_zone,
        "reported_fill_zone": [REPORTED_FILL_LOW, REPORTED_FILL_HIGH],
        "crossing_candle_events_near_reported_entry": nearby_crossings,
        "trade_count": len(trades),
        "ten_second_bar_count": len(bars_10s),
        "one_second_bar_count": len(bars_1s),
        "tape_window": {"start": tape_start.isoformat(), "end": tape_end.isoformat()},
        "provenance": {
            "trades": "alpaca_historical_sip",
            "micro_bars": "derived_from_sip_trades_using_alpaca_minute_trade_condition_rules"
        }
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
