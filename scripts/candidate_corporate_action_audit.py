from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone

import pandas as pd

from momentumbot.providers.alpaca import AlpacaDataClient

CANDIDATES = [
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


def _local_date(frame: pd.DataFrame):
    return pd.Index(frame.index.tz_convert("America/New_York").date)


def _bar_on(frame: pd.DataFrame, target: date):
    rows = frame.loc[_local_date(frame) == target]
    return None if rows.empty else rows.iloc[-1]


def _previous(frame: pd.DataFrame, target: date):
    rows = frame.loc[_local_date(frame) < target]
    return None if rows.empty else rows.iloc[-1]


def main() -> int:
    trading_date = date(2026, 7, 9)
    client = AlpacaDataClient.from_env()
    start = datetime.combine(trading_date - timedelta(days=7), time(0), timezone.utc)
    end = datetime.combine(trading_date + timedelta(days=1), time(0), timezone.utc)
    raw = client.bars(
        CANDIDATES,
        timeframe="1Day",
        start=start,
        end=end,
        feed="sip",
        adjustment="raw",
        asof=trading_date,
    )
    split = client.bars(
        CANDIDATES,
        timeframe="1Day",
        start=start,
        end=end,
        feed="sip",
        adjustment="split",
        asof=trading_date,
    )

    rows = []
    for symbol in CANDIDATES:
        raw_target = _bar_on(raw[symbol], trading_date)
        split_target = _bar_on(split[symbol], trading_date)
        split_prior = _previous(split[symbol], trading_date)
        if raw_target is None or split_target is None or split_prior is None:
            rows.append({"symbol": symbol, "complete": False})
            continue
        raw_close = float(raw_target["close"])
        split_close = float(split_target["close"])
        split_prior_close = float(split_prior["close"])
        scale_to_target_raw = raw_close / split_close
        target_basis_prior_close = split_prior_close * scale_to_target_raw
        rows.append(
            {
                "symbol": symbol,
                "complete": True,
                "raw_target_close": raw_close,
                "split_target_close": split_close,
                "split_target_to_raw_ratio": scale_to_target_raw,
                "split_prior_close": split_prior_close,
                "target_raw_basis_prior_close": target_basis_prior_close,
                "requires_target_basis_rescale": abs(scale_to_target_raw - 1.0) > 1e-9,
            }
        )

    payload = {
        "candidate_count": len(CANDIDATES),
        "rescale_required_count": sum(
            bool(row.get("requires_target_basis_rescale")) for row in rows
        ),
        "rows": rows,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
