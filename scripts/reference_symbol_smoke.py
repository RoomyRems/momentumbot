from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.models import current_general_2026
from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.rvol import prior_session_dates, same_time_rvol

ET = ZoneInfo("America/New_York")


def main() -> int:
    trading_date = date(2026, 7, 9)
    symbol = "VRAX"
    profile = current_general_2026()
    alpaca = AlpacaDataClient.from_env()

    history_start = datetime.combine(
        trading_date - timedelta(days=120), time(0), timezone.utc
    )
    feature_end = datetime.combine(trading_date, time(10, 1), ET).astimezone(timezone.utc)
    feature_start = datetime.combine(
        trading_date, profile.volume_feature_start, ET
    ).astimezone(timezone.utc)

    daily = alpaca.bars(
        [symbol],
        timeframe="1Day",
        start=history_start,
        end=feature_end,
        feed="sip",
        adjustment="raw",
        asof=trading_date,
    )[symbol]
    local_dates = pd.Index(daily.index.tz_convert(ET).date)
    prior_daily = daily.loc[local_dates < trading_date]
    if prior_daily.empty:
        raise RuntimeError("no prior daily bar")
    previous_close = float(prior_daily.iloc[-1]["close"])
    sessions = prior_session_dates(
        daily,
        trading_date=trading_date,
        lookback_sessions=profile.rvol_lookback_sessions,
    )

    split_history = alpaca.bars(
        [symbol],
        timeframe="1Min",
        start=history_start,
        end=feature_end,
        feed="sip",
        adjustment="split",
        asof=trading_date,
    )[symbol]
    curve = same_time_rvol(
        split_history,
        trading_date=trading_date,
        session_dates=sessions,
        start_time=profile.volume_feature_start,
        end_time=profile.no_new_entries_after,
    )
    raw = alpaca.bars(
        [symbol],
        timeframe="1Min",
        start=feature_start,
        end=feature_end,
        feed="sip",
        adjustment="raw",
        asof=trading_date,
    )[symbol]
    prices = pd.to_numeric(raw["close"], errors="coerce")
    gain = (prices / previous_close - 1.0) * 100.0
    rvol = curve.values.reindex(raw.index)
    local_times = raw.index.tz_convert(ET).time
    scan = pd.Series(
        [profile.session_start <= value < profile.no_new_entries_after for value in local_times],
        index=raw.index,
    )
    qualifies = (
        scan
        & (gain >= profile.min_percent_gain)
        & (rvol >= profile.min_relative_volume)
        & (prices >= profile.min_price)
        & (prices <= profile.max_price)
    )

    news_start = datetime.combine(trading_date, time(0), ET).astimezone(timezone.utc)
    news = alpaca.news([symbol], start=news_start, end=feature_end)
    news_before_scan_end = [
        row
        for row in news
        if row.get("created_at") and pd.Timestamp(row["created_at"]) <= feature_end
    ]

    summary = {
        "symbol": symbol,
        "date": trading_date.isoformat(),
        "previous_close": previous_close,
        "rvol_history_sessions": len(sessions),
        "max_rvol_0700_1000": round(float(rvol.loc[scan].max()), 3),
        "max_gain_pct_0700_1000": round(float(gain.loc[scan].max()), 3),
        "first_market_qualified_at": raw.index[qualifies][0].isoformat()
        if qualifies.any()
        else None,
        "alpaca_news_count_before_1001_et": len(news_before_scan_end),
        "alpaca_news": [
            {
                "created_at": row.get("created_at"),
                "headline": row.get("headline"),
                "source": row.get("source"),
            }
            for row in news_before_scan_end[:10]
        ],
        "sec_api_calls_consumed": 0,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
