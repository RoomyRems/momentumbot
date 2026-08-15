from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.backtest import Backtester
from momentumbot.historical_data import discover_market_day
from momentumbot.models import SymbolContext, current_general_2026, paper_safe_risk
from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.providers.marketaux import MarketAuxClient
from momentumbot.snapshot import load_snapshot

ET = ZoneInfo("America/New_York")


def _bounds(trading_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(trading_date, time(4, 0), ET).astimezone(timezone.utc)
    end = datetime.combine(trading_date, time(10, 1), ET).astimezone(timezone.utc)
    return start, end


def _news_bounds(trading_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(trading_date, time(0, 0), ET).astimezone(timezone.utc)
    end = datetime.combine(trading_date, time(10, 1), ET).astimezone(timezone.utc)
    return start, end


def _normalize_alpaca_news(rows: list[dict], candidate_symbols: set[str]) -> list[dict]:
    output: list[dict] = []
    for row in rows:
        published = row.get("created_at") or row.get("updated_at")
        if not published:
            continue
        symbols = row.get("symbols")
        if not isinstance(symbols, list):
            continue
        for symbol in sorted(candidate_symbols & {str(value).upper() for value in symbols}):
            output.append(
                {
                    "symbol": symbol,
                    "published_at": published,
                    "headline_id": f"alpaca:{row.get('id') or row.get('url') or row.get('headline')}",
                    "title": row.get("headline"),
                    "source": row.get("source"),
                    "provider": "alpaca-benzinga",
                }
            )
    return output


def _normalize_marketaux_news(symbol: str, rows: list[dict]) -> list[dict]:
    output: list[dict] = []
    for row in rows:
        published = row.get("published_at")
        if not published:
            continue
        output.append(
            {
                "symbol": symbol,
                "published_at": published,
                "headline_id": f"marketaux:{row.get('uuid') or row.get('url') or row.get('title')}",
                "title": row.get("title"),
                "source": row.get("source"),
                "provider": "marketaux",
            }
        )
    return output


def _dedupe_news(rows: list[dict]) -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    output: list[dict] = []
    for row in sorted(
        rows,
        key=lambda value: (
            str(value.get("published_at", "")),
            str(value.get("symbol", "")),
            str(value.get("headline_id", "")),
        ),
    ):
        key = (
            str(row.get("symbol", "")),
            str(row.get("published_at", "")),
            str(row.get("title", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def _load_rvol(root: Path, symbols: set[str]) -> dict[str, pd.Series]:
    output: dict[str, pd.Series] = {}
    for symbol in sorted(symbols):
        frame = pd.read_csv(root / "rvol" / f"{symbol}.csv", parse_dates=["timestamp"])
        series = pd.Series(
            pd.to_numeric(frame["relative_volume"], errors="coerce").to_numpy(),
            index=pd.DatetimeIndex(frame["timestamp"]),
            name="relative_volume",
        )
        output[symbol] = series
    return output


def _safe_int(value: object) -> int | None:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return None
    return int(float(value))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2026-07-09")
    parser.add_argument("--floats", default="sec-float-join-artifact/final_float_estimates.csv")
    parser.add_argument("--output", type=Path, default=Path("complete-reference-snapshot"))
    parser.add_argument("--starting-equity", type=float, default=100_000.0)
    args = parser.parse_args()

    trading_date = date.fromisoformat(args.date)
    profile = current_general_2026()
    alpaca = AlpacaDataClient.from_env()
    discovery = discover_market_day(alpaca, trading_date=trading_date, profile=profile)

    market_rows = [row for row in discovery.rows if row.first_market_qualified_at is not None]
    market_symbols = {row.symbol for row in market_rows}
    float_frame = pd.read_csv(args.floats)
    float_symbols = set(float_frame["symbol"].astype(str))
    if float_symbols != market_symbols:
        raise RuntimeError(
            f"final float table must exactly match market candidates; floats={sorted(float_symbols)}, market={sorted(market_symbols)}"
        )
    floats = {str(row["symbol"]): row for row in float_frame.to_dict(orient="records")}

    # Discovery rows are the complete deterministic acquisition universe after
    # requiring the 50-session history needed for same-time RVOL. Full-day high
    # was used only to acquire a superset; strategy evaluation never receives it.
    universe_rows = list(discovery.rows)
    universe_symbols = [row.symbol for row in universe_rows]
    universe_set = set(universe_symbols)
    if not market_symbols.issubset(universe_set):
        raise RuntimeError("market candidate escaped the research universe")

    start, end = _bounds(trading_date)
    bars = alpaca.bars_batched(
        universe_symbols,
        batch_size=75,
        timeframe="1Min",
        start=start,
        end=end,
        feed="sip",
        adjustment="raw",
        asof=trading_date,
    )
    missing_bars = sorted(symbol for symbol in universe_symbols if bars.get(symbol, pd.DataFrame()).empty)
    if missing_bars:
        raise RuntimeError(f"research universe has missing intraday bars: {missing_bars}")

    root = args.output
    bars_dir = root / "bars"
    rvol_dir = root / "rvol"
    bars_dir.mkdir(parents=True, exist_ok=True)
    rvol_dir.mkdir(parents=True, exist_ok=True)

    contexts: list[dict] = []
    discovery_by_symbol = {row.symbol: row for row in universe_rows}
    for symbol in universe_symbols:
        frame = bars[symbol]
        frame.reset_index().to_csv(bars_dir / f"{symbol}.csv", index=False)

        exact_curve = discovery.rvol_curves.get(symbol)
        if exact_curve is not None:
            curve = exact_curve.reindex(frame.index)
            rvol_status = "exact_same_time_1m"
        else:
            # Discovery already proved these securities never satisfied the
            # combined gain/price/RVOL market mask. NaN is a conservative
            # fail-closed value for strategy evaluation while retaining their
            # bars for cross-sectional gainer ranking.
            curve = pd.Series(float("nan"), index=frame.index, name="relative_volume")
            rvol_status = "fail_closed_not_exact_market_candidate"
        curve.rename("relative_volume").to_csv(
            rvol_dir / f"{symbol}.csv", index_label="timestamp"
        )

        source_context = discovery.contexts[symbol]
        float_shares = None
        float_asof = None
        float_method = None
        float_classification = "not_market_candidate"
        if symbol in market_symbols:
            row = floats[symbol]
            float_shares = _safe_int(row.get("estimated_float_shares"))
            raw_asof = row.get("float_asof")
            float_asof = None if raw_asof is None or pd.isna(raw_asof) else str(raw_asof)
            float_method = str(row.get("method") or "")
            raw_pass = row.get("float_pillar_pass")
            if pd.isna(raw_pass):
                float_classification = "unknown_fail_closed"
            elif bool(raw_pass):
                float_classification = "pass"
            else:
                float_classification = "fail"

        contexts.append(
            {
                "symbol": symbol,
                "previous_close": source_context.previous_close,
                "average_daily_volume_50": source_context.average_daily_volume_50,
                "float_shares": float_shares,
                "float_asof": float_asof,
                "float_method": float_method,
                "float_classification": float_classification,
                "market_candidate": symbol in market_symbols,
                "first_market_qualified_at": discovery_by_symbol[symbol].first_market_qualified_at,
                "rvol_status": rvol_status,
            }
        )
    pd.DataFrame(contexts).to_csv(root / "contexts.csv", index=False)

    pd.DataFrame([asdict(row) for row in universe_rows]).to_csv(root / "discovery.csv", index=False)
    float_frame.to_csv(root / "candidate_float_evidence.csv", index=False)

    news_start, news_end = _news_bounds(trading_date)
    news_errors: dict[str, str] = {}
    normalized_news: list[dict] = []
    try:
        alpaca_rows = alpaca.news(market_symbols, start=news_start, end=news_end)
        normalized_news.extend(_normalize_alpaca_news(alpaca_rows, market_symbols))
    except Exception as exc:
        news_errors["alpaca"] = f"{type(exc).__name__}: {exc}"

    by_symbol = {symbol: 0 for symbol in market_symbols}
    for row in normalized_news:
        by_symbol[str(row["symbol"])] += 1

    # MarketAux is a fallback only for candidates with no Alpaca/Benzinga item,
    # limiting external quota use while avoiding a single-provider blind spot.
    if os.getenv("MARKETAUX_API_KEY"):
        marketaux = MarketAuxClient.from_env()
        for symbol in sorted(market_symbols):
            if by_symbol[symbol] > 0:
                continue
            try:
                rows = marketaux.news(
                    symbol,
                    published_after=news_start,
                    published_before=news_end,
                    max_pages=1,
                    page_size=3,
                )
                additions = _normalize_marketaux_news(symbol, rows)
                normalized_news.extend(additions)
                by_symbol[symbol] += len(additions)
            except Exception as exc:
                news_errors[f"marketaux:{symbol}"] = f"{type(exc).__name__}: {exc}"

    news = _dedupe_news(normalized_news)
    pd.DataFrame(
        news,
        columns=["symbol", "published_at", "headline_id", "title", "source", "provider"],
    ).to_csv(root / "news.csv", index=False)

    classified = float_frame["float_pillar_pass"]
    manifest = {
        "schema_version": 3,
        "kind": "complete_historical_snapshot",
        "snapshot_id": f"current-general-2026:{trading_date.isoformat()}",
        "trading_date": trading_date.isoformat(),
        "strategy_profile": profile.name,
        "universe_complete": True,
        "universe_definition": "complete daily acquisition superset with the required 50-session RVOL history and intraday bars",
        "research_universe_count": len(universe_symbols),
        "listed_asset_count": discovery.listed_asset_count,
        "daily_superset_count": discovery.daily_superset_count,
        "market_candidate_count": len(market_symbols),
        "market_candidates": sorted(market_symbols),
        "candidate_float_pass_count": int(classified.eq(True).sum()),
        "candidate_float_fail_count": int(classified.eq(False).sum()),
        "candidate_float_unknown_count": int(classified.isna().sum()),
        "news_count": len(news),
        "news_counts_by_candidate": dict(sorted(by_symbol.items())),
        "news_provider_errors": news_errors,
        "news_window": {"start": news_start.isoformat(), "end": news_end.isoformat()},
        "price_bar_adjustment": "raw",
        "previous_close_basis": "split-adjusted onto trading-date share basis",
        "rvol_bar_adjustment": "split",
        "rvol_method": "same_time_cumulative_1m over 50 prior sessions",
        "rvol_fail_closed_for_non_market_candidates": True,
        "acquisition_prefilter_uses_full_day_high": True,
        "prefilter_is_not_available_to_strategy": True,
        "data_window": {"start": start.isoformat(), "end_exclusive": end.isoformat()},
        "notes": [
            "The full-day high is used only to choose the acquisition superset and is never exposed as a strategy feature.",
            "All securities that can satisfy the market price/gain/RVOL screen are retained with exact RVOL; other acquisition-universe names remain in bars for causal cross-sectional gain ranking and receive fail-closed RVOL.",
            "Unknown float remains null and therefore fails the float pillar closed.",
        ],
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    loaded_bars, loaded_contexts, loaded_news, loaded_manifest = load_snapshot(root)
    if set(loaded_bars) != universe_set or set(loaded_contexts) != universe_set:
        raise RuntimeError("snapshot loader changed the research universe")
    curves = _load_rvol(root, universe_set)
    result = Backtester(profile, paper_safe_risk()).run_day(
        loaded_bars,
        loaded_contexts,
        loaded_news,
        starting_equity=args.starting_equity,
        relative_volume_by_symbol=curves,
    )

    trades = []
    for trade in result.trades:
        row = asdict(trade)
        row["entry_time"] = trade.entry_time.isoformat()
        row["exit_time"] = trade.exit_time.isoformat()
        row["exit_reason"] = trade.exit_reason.value
        trades.append(row)
    pd.DataFrame(trades).to_csv(root / "trades.csv", index=False)
    backtest_summary = {
        "snapshot_id": loaded_manifest["snapshot_id"],
        "starting_equity": args.starting_equity,
        "trade_count": len(result.trades),
        "candidate_events": result.candidate_events,
        "plan_events": result.plan_events,
        "rejected_for_fill_slippage": result.rejected_for_fill_slippage,
        "pnl_dollars": result.pnl_dollars,
        "total_r": result.total_r,
        "session_locked": result.session_locked,
        "session_lock_reason": result.session_lock_reason,
        "traded_symbols": sorted({trade.symbol for trade in result.trades}),
    }
    (root / "backtest_summary.json").write_text(
        json.dumps(backtest_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"manifest": manifest, "backtest": backtest_summary}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
