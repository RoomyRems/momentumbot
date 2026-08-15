from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.historical_data import (
    discover_market_day,
    estimate_float_from_facts,
    write_discovery,
    write_reference_case,
)
from momentumbot.models import SymbolContext, current_general_2026
from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.providers.marketaux import MarketAuxClient
from momentumbot.providers.sec_api import SecApiFloatClient

ET = ZoneInfo("America/New_York")


def _row_for_symbol(discovery, symbol: str):
    return next((row for row in discovery.rows if row.symbol == symbol), None)


def _price_lookup(alpaca: AlpacaDataClient, symbol: str):
    cache: dict[date, float] = {}

    def lookup(measure_date: date) -> float:
        if measure_date in cache:
            return cache[measure_date]
        start = datetime.combine(measure_date - timedelta(days=7), time(0), timezone.utc)
        end = datetime.combine(measure_date + timedelta(days=1), time(0), timezone.utc)
        frames = alpaca.bars(
            [symbol], timeframe="1Day", start=start, end=end, feed="sip", adjustment="raw", asof=measure_date
        )
        frame = frames[symbol]
        eligible = frame.loc[pd.Index(frame.index.tz_convert(ET).date) <= measure_date]
        if eligible.empty:
            raise RuntimeError(f"no historical price available for {symbol} near {measure_date}")
        value = float(eligible.iloc[-1]["close"])
        cache[measure_date] = value
        return value

    return lookup


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2026-07-09")
    parser.add_argument("--symbol", default="VRAX")
    parser.add_argument("--output", type=Path, default=Path("historical-artifact"))
    parser.add_argument("--with-sec-api", action="store_true")
    args = parser.parse_args()

    trading_date = date.fromisoformat(args.date)
    symbol = args.symbol.upper()
    alpaca = AlpacaDataClient.from_env()
    profile = current_general_2026()
    discovery = discover_market_day(alpaca, trading_date=trading_date, profile=profile)
    write_discovery(discovery, args.output / "discovery", trading_date=trading_date)

    row = _row_for_symbol(discovery, symbol)
    if row is None:
        raise RuntimeError(f"reference symbol {symbol} was not in the acquisition superset")
    bars = discovery.minutes.get(symbol)
    if bars is None or bars.empty:
        # The reference can still be useful even if it did not pass RVOL in our current implementation.
        start = datetime.combine(trading_date, time(7), ET).astimezone(timezone.utc)
        end = datetime.combine(trading_date, time(10, 1), ET).astimezone(timezone.utc)
        bars = alpaca.bars(
            [symbol], timeframe="1Min", start=start, end=end, feed="sip", adjustment="raw", asof=trading_date
        )[symbol]

    context = discovery.contexts[symbol]
    news_start = datetime.combine(trading_date, time(0), ET).astimezone(timezone.utc)
    news_end = datetime.combine(trading_date, time(10, 1), ET).astimezone(timezone.utc)
    news = MarketAuxClient.from_env().news(symbol, published_after=news_start, published_before=news_end)

    float_estimate = None
    sec_api_calls = 0
    if args.with_sec_api:
        sec_api_calls = 1
        facts = SecApiFloatClient.from_env().company_facts(ticker=symbol)
        as_of = datetime.combine(trading_date, time(10, 1), ET).astimezone(timezone.utc)
        float_estimate = estimate_float_from_facts(
            facts,
            as_of=as_of,
            price_lookup=_price_lookup(alpaca, symbol),
        )

    write_reference_case(
        root=args.output / "reference" / f"{symbol}-{trading_date.isoformat()}",
        symbol=symbol,
        trading_date=trading_date,
        bars=bars,
        context=context,
        news_rows=news,
        float_estimate=float_estimate,
    )

    summary = {
        "date": trading_date.isoformat(),
        "reference_symbol": symbol,
        "asset_count": discovery.asset_count,
        "listed_asset_count": discovery.listed_asset_count,
        "daily_superset_count": discovery.daily_superset_count,
        "nonfloat_candidate_count": discovery.nonfloat_candidate_count,
        "reference_in_nonfloat_candidates": row.first_nonfloat_qualified_at is not None,
        "reference_first_nonfloat_qualified_at": row.first_nonfloat_qualified_at,
        "reference_max_session_gain_pct": round(row.max_session_gain_pct, 3),
        "reference_max_session_rvol": round(row.max_session_rvol, 3),
        "marketaux_news_count_before_1001_et": len(news),
        "float_estimate_shares": float_estimate.value_shares if float_estimate else None,
        "float_method": float_estimate.method if float_estimate else None,
        "sec_api_calls_consumed": sec_api_calls,
        "universe_complete": False,
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
