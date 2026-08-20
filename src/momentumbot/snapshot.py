from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pandas as pd

from .backtest import NewsEvent
from .indicators import validate_bars
from .models import SymbolContext


class SnapshotError(ValueError):
    pass


def _parse_optional_datetime(value: object) -> datetime | None:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return None
    return pd.Timestamp(value).to_pydatetime()


def load_snapshot(
    path: str | Path,
) -> tuple[dict[str, pd.DataFrame], dict[str, SymbolContext], tuple[NewsEvent, ...], dict]:
    root = Path(path)
    manifest_path = root / "manifest.json"
    contexts_path = root / "contexts.csv"
    bars_dir = root / "bars"
    news_path = root / "news.csv"
    if not manifest_path.exists() or not contexts_path.exists() or not bars_dir.is_dir():
        raise SnapshotError("snapshot requires manifest.json, contexts.csv, and bars/")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("universe_complete", False):
        raise SnapshotError("snapshot must explicitly declare universe_complete=true")

    context_frame = pd.read_csv(contexts_path)
    required = {"symbol", "previous_close", "average_daily_volume_50", "float_shares", "float_asof"}
    if not required.issubset(context_frame.columns):
        missing = sorted(required - set(context_frame.columns))
        raise SnapshotError(f"contexts.csv missing columns: {missing}")

    contexts: dict[str, SymbolContext] = {}
    bars_by_symbol: dict[str, pd.DataFrame] = {}
    for row in context_frame.to_dict(orient="records"):
        symbol = str(row["symbol"])
        raw_float = row["float_shares"]
        float_shares = None if pd.isna(raw_float) else int(raw_float)
        contexts[symbol] = SymbolContext(
            symbol=symbol,
            previous_close=float(row["previous_close"]),
            average_daily_volume_50=float(row["average_daily_volume_50"]),
            float_shares=float_shares,
            float_asof=_parse_optional_datetime(row.get("float_asof")),
        )
        if float_shares is not None and contexts[symbol].float_asof is None:
            raise SnapshotError(f"point-in-time float requires float_asof for {symbol}")
        bar_path = bars_dir / f"{symbol}.csv"
        if not bar_path.exists():
            raise SnapshotError(f"missing bars file for {symbol}: {bar_path}")
        bars = pd.read_csv(bar_path, parse_dates=["timestamp"]).set_index("timestamp")
        if bars.index.tz is None:
            raise SnapshotError(f"bar timestamps must contain timezone offsets: {symbol}")
        validate_bars(bars)
        bars_by_symbol[symbol] = bars

    news_events: list[NewsEvent] = []
    if news_path.exists():
        news_frame = pd.read_csv(news_path)
        news_required = {"symbol", "published_at", "headline_id"}
        if not news_required.issubset(news_frame.columns):
            missing = sorted(news_required - set(news_frame.columns))
            raise SnapshotError(f"news.csv missing columns: {missing}")
        for row in news_frame.to_dict(orient="records"):
            published_at = pd.Timestamp(row["published_at"])
            if published_at.tz is None:
                raise SnapshotError("news published_at must be timezone-aware")
            news_events.append(
                NewsEvent(
                    symbol=str(row["symbol"]),
                    published_at=published_at.to_pydatetime(),
                    headline_id=str(row["headline_id"]),
                )
            )

    return bars_by_symbol, contexts, tuple(news_events), manifest


def write_contexts(path: str | Path, contexts: list[SymbolContext]) -> None:
    rows = []
    for context in contexts:
        row = asdict(context)
        row["float_asof"] = context.float_asof.isoformat() if context.float_asof else None
        rows.append(row)
    pd.DataFrame(rows).to_csv(path, index=False)


def directory_fingerprint(path: str | Path) -> str:
    """Stable SHA-256 over relative filenames and bytes, excluding the hash itself."""
    root = Path(path)
    digest = hashlib.sha256()
    for file_path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = file_path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
