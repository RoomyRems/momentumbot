from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone

from momentumbot.providers.alpaca import AlpacaDataClient

CANDIDATES = [
    "ENLV",
    "VRAX",
    "JLHL",
    "RPGL",
    "WRAP",
    "TDTH",
    "NDRA",
    "SUNE",
    "AP",
    "SMPL",
    "MAAS",
    "PLBL",
    "SRXH",
    "PTLE",
    "HOUR",
]
SPLIT_REFERENCE = ["ENLV", "SRXH"]


def _safe_actions(client: AlpacaDataClient, trading_date: date) -> list[dict]:
    rows = client.corporate_actions(
        symbols=CANDIDATES,
        start=trading_date - timedelta(days=5),
        end=trading_date + timedelta(days=5),
        types="forward_split,reverse_split,name_change",
    )
    return [
        {
            key: value
            for key, value in row.items()
            if key not in {"cusip", "old_cusip", "new_cusip"}
        }
        for row in rows
    ]


def _bar_rows(client: AlpacaDataClient, trading_date: date, adjustment: str) -> dict[str, list[dict]]:
    start = datetime.combine(trading_date - timedelta(days=6), time(0), timezone.utc)
    end = datetime.combine(trading_date + timedelta(days=1), time(0), timezone.utc)
    frames = client.bars(
        SPLIT_REFERENCE,
        timeframe="1Day",
        start=start,
        end=end,
        feed="sip",
        adjustment=adjustment,
        asof=trading_date,
    )
    output: dict[str, list[dict]] = {}
    for symbol, frame in frames.items():
        rows = []
        for timestamp, row in frame.iterrows():
            rows.append(
                {
                    "timestamp": timestamp.isoformat(),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": int(row["volume"]),
                }
            )
        output[symbol] = rows
    return output


def main() -> int:
    trading_date = date(2026, 7, 9)
    client = AlpacaDataClient.from_env()
    payload = {
        "candidate_count": len(CANDIDATES),
        "actions": _safe_actions(client, trading_date),
        "raw_daily_bars": _bar_rows(client, trading_date, "raw"),
        "split_adjusted_daily_bars": _bar_rows(client, trading_date, "split"),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
