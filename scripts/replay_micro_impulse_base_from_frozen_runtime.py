from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from momentumbot.micro_policy import micro_v0_1_policy
from momentumbot.micro_replay import micro_replay_runtime_artifact, replay_micro_candidate
from momentumbot.research.micro_impulse_base_ablation import (
    impulse_base_runtime_artifact,
    replay_micro_candidate_with_qualification_base,
)


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def _load_frame(
    path: Path, *, index_column: str, require_unique_index: bool = True
) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if index_column not in frame.columns:
        raise ValueError(f"{path} is missing {index_column}")
    frame[index_column] = pd.to_datetime(frame[index_column], utc=True)
    frame = frame.set_index(index_column)
    if not frame.index.is_monotonic_increasing:
        raise ValueError(f"{path} timestamps must be ordered")
    if require_unique_index and not frame.index.is_unique:
        raise ValueError(f"{path} timestamps must be unique")
    return frame


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Replay the label-blind impulse-base ablation from one exact frozen "
            "Micro v0.1 runtime input bundle. No benchmark label is accepted."
        )
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-workflow-run-id", type=int, required=True)
    parser.add_argument("--source-artifact-id", type=int, required=True)
    parser.add_argument("--source-artifact-name", required=True)
    parser.add_argument("--source-artifact-digest-sha256", required=True)
    args = parser.parse_args()

    source = args.input
    context = _load_json(source / "runtime-context.json")
    source_runtime = _load_json(source / "runtime-replay.json")
    bars = _load_frame(source / "bars-10s.csv", index_column="timestamp")
    trades = _load_frame(
        source / "trades.csv",
        index_column="timestamp",
        require_unique_index=False,
    )
    support = _load_frame(
        source / "support-available.csv", index_column="available_at"
    )
    if not {"vwap", "ema"}.issubset(support.columns):
        raise ValueError("support input is missing vwap or ema")

    symbol = str(source_runtime.get("symbol") or "")
    qualified = pd.Timestamp(context.get("candidate_qualified_at"))
    replay_end = pd.Timestamp(context.get("replay_end"))
    if not symbol or qualified.tzinfo is None or replay_end.tzinfo is None:
        raise ValueError("frozen runtime context is incomplete")

    parent = micro_v0_1_policy()
    baseline = replay_micro_candidate(
        symbol,
        bars,
        trades,
        candidate_qualified_at=qualified,
        policy=parent.setup,
        vwap_available=support["vwap"],
        ema9_available=support["ema"],
        exit_until=replay_end,
    )
    recomputed_core = micro_replay_runtime_artifact(baseline)
    source_core = {key: source_runtime.get(key) for key in recomputed_core}
    if recomputed_core != source_core:
        differing = sorted(
            key for key in recomputed_core if recomputed_core[key] != source_core[key]
        )
        raise RuntimeError(
            f"{symbol} no longer reproduces the frozen v0.1 runtime core: {differing}"
        )

    result = replay_micro_candidate_with_qualification_base(
        symbol,
        bars,
        trades,
        candidate_qualified_at=qualified,
        policy=parent.setup,
        vwap_available=support["vwap"],
        ema9_available=support["ema"],
        exit_until=replay_end,
    )
    runtime = impulse_base_runtime_artifact(result)
    runtime.update(
        {
            "source_policy_reproduced_exactly": True,
            "source_baseline_runtime_core_sha256": _canonical_sha256(source_core),
            "source_workflow_run_id": args.source_workflow_run_id,
            "source_artifact_id": args.source_artifact_id,
            "source_artifact_name": args.source_artifact_name,
            "source_artifact_digest_sha256": args.source_artifact_digest_sha256,
            "source_input_rule": (
                "exact frozen v0.1 trades, 10-second bars, completed-minute support, "
                "qualification timestamp, and replay cutoff"
            ),
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(runtime, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "symbol": symbol,
                "plan_count": result.replay.plan_count,
                "filled_count": result.replay.filled_count,
                "filled_pullback_numbers": list(result.replay.filled_pullback_numbers),
                "source_policy_reproduced_exactly": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
