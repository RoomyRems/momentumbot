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
from momentumbot.models import current_general_2026
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
            [symbol],
            timeframe="1Day",
            start=start,
            end=end,
            feed="sip",
            adjustment="raw",
            asof=measure_date,
        )
        frame = frames[symbol]
        eligible = frame.loc[pd.Index(frame.index.tz_convert(ET).date) <= measure_date]
        if eligible.empty:
            raise RuntimeError(f"no historical price available for {symbol} near {measure_date}")
        value = float(eligible.iloc[-1]["close"])
        cache[measure_date] = value
        return value

    return lookup


def _normalize_marketaux(rows: list[dict]) -> list[dict]:
    output = []
    for row in rows:
        published = row.get("published_at")
        if not published:
            continue
        output.append(
            {
                "published_at": published,
                "uuid": f"marketaux:{row.get('uuid') or row.get('url') or row.get('title')}",
                "title": row.get("title"),
                "source": row.get("source"),
                "provider": "marketaux",
                "url": row.get("url"),
            }
        )
    return output


def _normalize_alpaca(rows: list[dict]) -> list[dict]:
    output = []
    for row in rows:
        published = row.get("created_at") or row.get("updated_at")
        if not published:
            continue
        output.append(
            {
                "published_at": published,
                "uuid": f"alpaca:{row.get('id') or row.get('url') or row.get('headline')}",
                "title": row.get("headline"),
                "source": row.get("source"),
                "provider": "alpaca-benzinga",
                "url": row.get("url"),
            }
        )
    return output


def _dedupe_news(rows: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    output = []
    for row in sorted(rows, key=lambda item: str(item.get("published_at", ""))):
        key = (str(row.get("published_at", "")), str(row.get("title", "")))
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


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
    context = discovery.contexts.get(symbol)
    if context is None:
        raise RuntimeError(f"reference symbol {symbol} lacks the required 50-session history")

    bars = discovery.minutes.get(symbol)
    if bars is None or bars.empty:
        start = datetime.combine(trading_date, profile.volume_feature_start, ET).astimezone(
            timezone.utc
        )
        end = datetime.combine(trading_date, time(10, 1), ET).astimezone(timezone.utc)
        bars = alpaca.bars(
            [symbol],
            timeframe="1Min",
            start=start,
            end=end,
            feed="sip",
            adjustment="raw",
            asof=trading_date,
        )[symbol]

    news_start = datetime.combine(trading_date, time(0), ET).astimezone(timezone.utc)
    news_end = datetime.combine(trading_date, time(10, 1), ET).astimezone(timezone.utc)
    news_errors: dict[str, str] = {}
    marketaux_raw: list[dict] = []
    alpaca_raw: list[dict] = []
    try:
        marketaux_raw = MarketAuxClient.from_env().news(
            symbol, published_after=news_start, published_before=news_end
        )
    except Exception as exc:
        news_errors["marketaux"] = f"{type(exc).__name__}: {exc}"
    try:
        alpaca_raw = alpaca.news([symbol], start=news_start, end=news_end)
    except Exception as exc:
        news_errors["alpaca"] = f"{type(exc).__name__}: {exc}"
    news = _dedupe_news(_normalize_marketaux(marketaux_raw) + _normalize_alpaca(alpaca_raw))

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

    rvol_curve = discovery.rvol_curves.get(symbol)
    write_reference_case(
        root=args.output / "reference" / f"{symbol}-{trading_date.isoformat()}",
        symbol=symbol,
        trading_date=trading_date,
        bars=bars,
        context=context,
        news_rows=news,
        float_estimate=float_estimate,
        rvol_curve=rvol_curve,
    )

    summary = {
        "date": trading_date.isoformat(),
        "reference_symbol": symbol,
        "asset_count": discovery.asset_count,
        "listed_asset_count": discovery.listed_asset_count,
        "daily_superset_count": discovery.daily_superset_count,
        "rvol_prefilter_count": discovery.rvol_prefilter_count,
        "market_candidate_count": discovery.market_candidate_count,
        "reference_in_market_candidates": row.first_market_qualified_at is not None,
        "reference_first_market_qualified_at": row.first_market_qualified_at,
        "reference_max_session_gain_pct": round(row.max_session_gain_pct, 3),
        "reference_max_session_rvol_upper_bound": (
            round(row.max_session_rvol_upper_bound, 3)
            if row.max_session_rvol_upper_bound is not None
            else None
        ),
        "reference_max_session_rvol": (
            round(row.max_session_rvol, 3) if row.max_session_rvol is not None else None
        ),
        "reference_rvol_history_sessions": row.rvol_history_sessions,
        "marketaux_news_count_before_1001_et": len(marketaux_raw),
        "alpaca_news_count_before_1001_et": len(alpaca_raw),
        "combined_news_count_before_1001_et": len(news),
        "news_provider_errors": news_errors,
        "float_estimate_shares": float_estimate.value_shares if float_estimate else None,
        "float_method": float_estimate.method if float_estimate else None,
        "sec_api_calls_consumed": sec_api_calls,
        "universe_complete": False,
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
