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


def _load_bar_file(path: Path, *, label: str) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["timestamp"]).set_index("timestamp")
    if frame.index.tz is None:
        raise SnapshotError(f"{label} timestamps must contain timezone offsets: {path.name}")
    validate_bars(frame)
    return frame


def _validate_conditional_asset_master(root: Path, manifest: dict) -> None:
    if manifest.get("point_in_time_universe_complete") is not False:
        raise SnapshotError(
            "conditional universe must explicitly declare "
            "point_in_time_universe_complete=false"
        )
    eligibility = manifest.get("evaluation_eligibility")
    if not isinstance(eligibility, dict):
        raise SnapshotError("conditional universe requires an evaluation_eligibility object")
    if eligibility.get("conditional_diagnostic") is not True:
        raise SnapshotError(
            "conditional universe must explicitly allow conditional diagnostics"
        )
    if eligibility.get("policy_promotion") is not False:
        raise SnapshotError("conditional universe must explicitly prohibit policy promotion")
    if eligibility.get("full_scanner_walk_forward") is not False:
        raise SnapshotError(
            "conditional universe must explicitly prohibit full-scanner walk-forward claims"
        )

    membership = manifest.get("universe_membership")
    if not isinstance(membership, dict):
        raise SnapshotError("conditional universe requires universe_membership provenance")
    source_artifact = membership.get("source_artifact")
    if not isinstance(source_artifact, str) or not source_artifact:
        raise SnapshotError("conditional universe requires a source_artifact")
    relative = Path(source_artifact)
    if relative.is_absolute() or ".." in relative.parts:
        raise SnapshotError("conditional universe source_artifact must stay inside snapshot")
    artifact_path = root / relative
    if not artifact_path.is_file():
        raise SnapshotError(f"missing conditional universe source artifact: {source_artifact}")
    asset_master = json.loads(artifact_path.read_text(encoding="utf-8"))
    assets = asset_master.get("assets") if isinstance(asset_master, dict) else None
    if not isinstance(assets, list):
        raise SnapshotError("conditional universe source artifact requires an assets list")
    actual_sha256 = hashlib.sha256(
        json.dumps(
            assets,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    expected_sha256 = membership.get("source_sha256")
    if not isinstance(expected_sha256, str) or actual_sha256 != expected_sha256:
        raise SnapshotError("conditional universe asset-master fingerprint mismatch")
    if asset_master.get("sha256") != expected_sha256:
        raise SnapshotError("conditional universe artifact fingerprint mismatch")
    if asset_master.get("point_in_time_membership") is not False:
        raise SnapshotError(
            "conditional universe artifact must explicitly deny point-in-time membership"
        )


def load_snapshot(
    path: str | Path,
    *,
    allow_conditional_universe: bool = False,
) -> tuple[dict[str, pd.DataFrame], dict[str, SymbolContext], tuple[NewsEvent, ...], dict]:
    root = Path(path)
    manifest_path = root / "manifest.json"
    contexts_path = root / "contexts.csv"
    bars_dir = root / "bars"
    news_path = root / "news.csv"
    if not manifest_path.exists() or not contexts_path.exists() or not bars_dir.is_dir():
        raise SnapshotError("snapshot requires manifest.json, contexts.csv, and bars/")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    point_in_time_complete = bool(manifest.get("universe_complete", False))
    explicitly_not_point_in_time = manifest.get("point_in_time_universe_complete") is False
    if point_in_time_complete and explicitly_not_point_in_time:
        raise SnapshotError(
            "snapshot cannot declare universe_complete=true while "
            "point_in_time_universe_complete=false"
        )
    conditional_complete = bool(
        manifest.get("universe_complete_relative_to_asset_master", False)
    )
    if not point_in_time_complete:
        if not allow_conditional_universe or not conditional_complete:
            raise SnapshotError(
                "snapshot must explicitly declare universe_complete=true for a "
                "point-in-time universe; current-asset-master diagnostics require "
                "allow_conditional_universe=True"
            )
        _validate_conditional_asset_master(root, manifest)

    context_frame = pd.read_csv(contexts_path)
    required = {
        "symbol",
        "previous_close",
        "average_daily_volume_50",
        "float_shares",
        "float_asof",
    }
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
        bars_by_symbol[symbol] = _load_bar_file(bar_path, label="bar")

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


def load_indicator_warmup(path: str | Path) -> dict[str, pd.DataFrame]:
    """Load optional prior-session bars used only to warm continuous indicators.

    The warmup directory is deliberately separate from `bars/` so prior prices
    cannot accidentally enter current-session VWAP, scanner rank, pullback
    geometry, or execution. Consumers must opt into this data explicitly.
    """
    root = Path(path)
    warmup_dir = root / "warmup"
    if not warmup_dir.exists():
        return {}
    if not warmup_dir.is_dir():
        raise SnapshotError("warmup must be a directory")

    output: dict[str, pd.DataFrame] = {}
    for path_item in sorted(warmup_dir.glob("*.csv")):
        symbol = path_item.stem
        if symbol in output:
            raise SnapshotError(f"duplicate warmup symbol: {symbol}")
        output[symbol] = _load_bar_file(path_item, label="warmup")
    return output


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
