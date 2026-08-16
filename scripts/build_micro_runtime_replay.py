from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

import pandas as pd

from momentumbot.micro_execution import MicroTriggerMode
from momentumbot.micro_policy import micro_v0_1_policy
from momentumbot.micro_replay import micro_replay_runtime_artifact, replay_micro_candidate
from momentumbot.micro_setup import geometry_only_micro_research_policy


def _read_indexed_csv(path: Path, index_column: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if index_column not in frame.columns:
        raise ValueError(f"{path} is missing required index column {index_column!r}")
    index = pd.to_datetime(frame.pop(index_column), utc=True, errors="raise")
    frame.index = pd.DatetimeIndex(index, name=index_column)
    return frame.sort_index()


def _parse_conditions(value: object) -> tuple[str, ...]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ()
    if isinstance(value, (tuple, list)):
        return tuple(str(item) for item in value)
    if not isinstance(value, str):
        raise TypeError("trade conditions must be serialized as a string/list/tuple")
    parsed = ast.literal_eval(value)
    if isinstance(parsed, str):
        return (parsed,)
    if isinstance(parsed, (tuple, list)):
        return tuple(str(item) for item in parsed)
    raise ValueError(f"unsupported serialized trade conditions: {value!r}")


def _read_bars(path: Path) -> pd.DataFrame:
    bars = _read_indexed_csv(path, "timestamp")
    for column in ("open_time", "high_time", "low_time", "close_time"):
        if column in bars.columns:
            bars[column] = pd.to_datetime(bars[column], utc=True, errors="coerce")
    return bars


def _read_trades(path: Path) -> pd.DataFrame:
    trades = _read_indexed_csv(path, "timestamp")
    if "conditions" not in trades.columns:
        raise ValueError(f"{path} is missing trade conditions")
    trades["conditions"] = trades["conditions"].map(_parse_conditions)
    return trades


def _read_support(path: Path) -> pd.DataFrame:
    support = _read_indexed_csv(path, "available_at")
    missing = sorted({"vwap", "ema"} - set(support.columns))
    if missing:
        raise ValueError(f"{path} is missing support columns: {missing}")
    return support


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a label-blind causal micro runtime replay from emitted market-data files."
    )
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--candidate-qualified-at", required=True)
    parser.add_argument("--bars-csv", type=Path, required=True)
    parser.add_argument("--trades-csv", type=Path, required=True)
    parser.add_argument("--support-csv", type=Path)
    parser.add_argument(
        "--policy",
        choices=("micro-v0.1", "canonical", "geometry"),
        default="micro-v0.1",
        help="'canonical' is retained as a compatibility alias for frozen micro-v0.1.",
    )
    parser.add_argument("--entry-latency-ms", type=float, default=0.0)
    parser.add_argument("--exit-until")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    bars = _read_bars(args.bars_csv)
    trades = _read_trades(args.trades_csv)
    qualified_at = pd.Timestamp(args.candidate_qualified_at)
    if qualified_at.tzinfo is None:
        raise ValueError("--candidate-qualified-at must be timezone-aware")
    exit_until = pd.Timestamp(args.exit_until) if args.exit_until else None
    if exit_until is not None and exit_until.tzinfo is None:
        raise ValueError("--exit-until must be timezone-aware")

    support = _read_support(args.support_csv) if args.support_csv is not None else None
    frozen = None
    if args.policy in {"micro-v0.1", "canonical"}:
        if support is None:
            raise ValueError("Micro v0.1 replay requires --support-csv")
        frozen = micro_v0_1_policy()
        policy = frozen.setup
        vwap_available = support["vwap"]
        ema9_available = support["ema"]
    else:
        policy = geometry_only_micro_research_policy()
        vwap_available = None
        ema9_available = None

    replay = replay_micro_candidate(
        args.symbol,
        bars,
        trades,
        candidate_qualified_at=qualified_at,
        policy=policy,
        vwap_available=vwap_available,
        ema9_available=ema9_available,
        trigger_mode=MicroTriggerMode.CHART_PRICE,
        entry_latency_ms=args.entry_latency_ms,
        exit_until=exit_until,
    )
    artifact = micro_replay_runtime_artifact(replay)
    if frozen is not None:
        artifact["frozen_policy_id"] = frozen.policy_id
        artifact["frozen_policy_fingerprint"] = frozen.fingerprint
        artifact["frozen_policy_status"] = frozen.status
    else:
        artifact["research_policy"] = policy.name

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
