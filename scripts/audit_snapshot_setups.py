from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from momentumbot.backtest import Backtester
from momentumbot.models import current_general_2026, paper_safe_risk
from momentumbot.snapshot import load_snapshot


def _load_rvol(root: Path, symbols: set[str]) -> dict[str, pd.Series]:
    output: dict[str, pd.Series] = {}
    for symbol in sorted(symbols):
        frame = pd.read_csv(root / "rvol" / f"{symbol}.csv", parse_dates=["timestamp"])
        output[symbol] = pd.Series(
            pd.to_numeric(frame["relative_volume"], errors="coerce").to_numpy(),
            index=pd.DatetimeIndex(frame["timestamp"]),
            name="relative_volume",
        )
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--starting-equity", type=float, default=100_000.0)
    args = parser.parse_args()

    bars, contexts, news, manifest = load_snapshot(args.snapshot)
    curves = _load_rvol(args.snapshot, set(bars))
    result = Backtester(current_general_2026(), paper_safe_risk()).run_day(
        bars,
        contexts,
        news,
        starting_equity=args.starting_equity,
        relative_volume_by_symbol=curves,
    )
    report = {
        "snapshot_id": manifest["snapshot_id"],
        "candidate_events": result.candidate_events,
        "plan_events": result.plan_events,
        "trade_count": len(result.trades),
        "setup_rejections": result.setup_rejections,
        "setup_rejection_total": sum(result.setup_rejections.values()),
        "rejected_for_fill_slippage": result.rejected_for_fill_slippage,
    }
    (args.snapshot / "setup_audit.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
