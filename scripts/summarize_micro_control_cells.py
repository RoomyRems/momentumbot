from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def _cell_name(score: dict[str, object]) -> str:
    ablation_id = score.get("ablation_id")
    if ablation_id == "micro-v0.2a-prequalification-context":
        return "context_only"
    if ablation_id == "micro-v0.2c-no-hard-volume-gate":
        return "volume_only"
    if ablation_id == "micro-v0.2d-context-no-hard-volume-gate":
        return "context_plus_volume"
    if score.get("frozen_policy_id") == "micro-v0.1":
        return "baseline"
    raise ValueError(f"cannot identify score cell from keys: {sorted(score)}")


def _first_fill(score: dict[str, object]) -> object:
    price = score.get("price_references_descriptive_only")
    if isinstance(price, dict):
        return price.get("first_runtime_fill_price")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize scored micro policy cells for one control case.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    cells: dict[str, dict[str, object]] = {}
    benchmark_id = None
    symbol = None
    for path in sorted(args.root.rglob("case-score.json")):
        score = _load(path)
        cell = _cell_name(score)
        if cell in cells:
            raise ValueError(f"duplicate {cell} score")
        benchmark_id = benchmark_id or score.get("benchmark_id")
        symbol = symbol or score.get("symbol")
        raw_numbers = score.get("runtime_filled_pullback_numbers")
        numbers = raw_numbers if isinstance(raw_numbers, list) else []
        cells[cell] = {
            "plan_count": score.get("runtime_plan_count"),
            "filled_count": score.get("runtime_filled_count"),
            "filled_pullback_numbers": numbers,
            "first_filled_pullback_number": numbers[0] if numbers else None,
            "first_fill_price": _first_fill(score),
            "matching_dimensions": score.get("matching_dimensions"),
            "comparable_dimensions": score.get("comparable_dimensions"),
            "scored_dimensions": score.get("scored_dimensions"),
            "exact_human_trade_identity_scored": score.get("exact_human_trade_identity_scored"),
        }

    expected = {"baseline", "context_only", "volume_only", "context_plus_volume"}
    if set(cells) != expected:
        raise ValueError(f"expected {sorted(expected)}, got {sorted(cells)}")

    artifact = {
        "artifact_type": "micro_four_cell_control_comparison",
        "schema_version": 1,
        "knowledge_policy": "post_replay_retrospective_evaluation_only",
        "strategy_feedback": "none",
        "benchmark_id": benchmark_id,
        "symbol": symbol,
        "cells": cells,
        "interpretation": [
            "all runtime cells were produced label-blind before retrospective scoring",
            "this control compares unchanged frozen/ablation cells rather than fitting a new rule",
            "manifest-approved dimensions remain authoritative; fill prices are descriptive only",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
