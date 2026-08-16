from __future__ import annotations

import argparse
import json
from pathlib import Path


POST_REPLAY_POLICY = "post_replay_retrospective_evaluation_only"
EXPECTED_CELLS = {
    "baseline",
    "context_only",
    "volume_only",
    "context_plus_volume",
}


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


def _policy_provenance(score: dict[str, object]) -> dict[str, object]:
    ablation_id = score.get("ablation_id")
    if ablation_id is not None:
        return {
            "policy_id": ablation_id,
            "policy_fingerprint": score.get("ablation_fingerprint"),
            "parent_frozen_policy_id": score.get("parent_frozen_policy_id"),
            "parent_frozen_policy_fingerprint": score.get(
                "parent_frozen_policy_fingerprint"
            ),
        }
    return {
        "policy_id": score.get("frozen_policy_id"),
        "policy_fingerprint": score.get("frozen_policy_fingerprint"),
        "parent_frozen_policy_id": None,
        "parent_frozen_policy_fingerprint": None,
    }


def build_control_comparison(root: Path) -> dict[str, object]:
    cells: dict[str, dict[str, object]] = {}
    benchmark_id: object = None
    symbol: object = None
    case_role: object = None
    scored_dimension_names: set[str] | None = None

    for path in sorted(root.rglob("case-score.json")):
        score = _load(path)
        if score.get("knowledge_policy") != POST_REPLAY_POLICY:
            raise ValueError(f"{path} is not a post-replay score artifact")
        if score.get("exact_human_trade_identity_scored") is not False:
            raise ValueError(f"{path} does not preserve exact-trade scoring isolation")

        cell = _cell_name(score)
        if cell in cells:
            raise ValueError(f"duplicate {cell} score")

        current_benchmark_id = score.get("benchmark_id")
        current_symbol = score.get("symbol")
        current_case_role = score.get("case_role")
        if benchmark_id is None:
            benchmark_id = current_benchmark_id
            symbol = current_symbol
            case_role = current_case_role
        elif (
            current_benchmark_id != benchmark_id
            or current_symbol != symbol
            or current_case_role != case_role
        ):
            raise ValueError(f"{path} belongs to a different benchmark control")

        raw_dimensions = score.get("scored_dimensions")
        if not isinstance(raw_dimensions, dict):
            raise TypeError(f"{path} scored_dimensions must be a JSON object")
        current_dimension_names = {str(name) for name in raw_dimensions}
        if scored_dimension_names is None:
            scored_dimension_names = current_dimension_names
        elif current_dimension_names != scored_dimension_names:
            raise ValueError(f"{path} scored dimensions differ across cells")

        available = score.get("upstream_runtime_available")
        if not isinstance(available, bool):
            raise TypeError(f"{path} is missing upstream runtime availability")
        raw_numbers = score.get("runtime_filled_pullback_numbers")
        numbers = raw_numbers if isinstance(raw_numbers, list) else []
        cells[cell] = {
            **_policy_provenance(score),
            "upstream_runtime_available": available,
            "runtime_status": score.get("runtime_status"),
            "plan_count": score.get("runtime_plan_count"),
            "filled_count": score.get("runtime_filled_count"),
            "filled_pullback_numbers": numbers,
            "first_filled_pullback_number": numbers[0] if numbers else None,
            "first_fill_price": _first_fill(score),
            "matching_dimensions": score.get("matching_dimensions"),
            "comparable_dimensions": score.get("comparable_dimensions"),
            "scored_dimensions": raw_dimensions,
            "exact_human_trade_identity_scored": False,
        }

    if set(cells) != EXPECTED_CELLS:
        raise ValueError(f"expected {sorted(EXPECTED_CELLS)}, got {sorted(cells)}")
    if benchmark_id is None or symbol is None or case_role is None:
        raise ValueError("control scores are missing benchmark identity")

    availability = {
        bool(cell["upstream_runtime_available"]) for cell in cells.values()
    }
    if len(availability) != 1:
        raise ValueError("upstream runtime availability differs across policy cells")

    dimension_names = sorted(scored_dimension_names or set())
    return {
        "artifact_type": "micro_four_cell_control_comparison",
        "schema_version": 2,
        "knowledge_policy": POST_REPLAY_POLICY,
        "strategy_feedback": "none",
        "benchmark_id": benchmark_id,
        "symbol": symbol,
        "case_role": case_role,
        "upstream_runtime_available": availability.pop(),
        "manifest_scored_dimensions": dimension_names,
        "cells": cells,
        "interpretation": [
            "all runtime cells were produced label-blind before retrospective scoring",
            "this control compares unchanged frozen/ablation cells rather than fitting a new rule",
            "manifest-approved dimensions remain authoritative; fill prices are descriptive only",
            "a boundary control with no scored dimensions reports activity but cannot establish imitation accuracy or a scanner-eligible false-positive rate",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize scored micro policy cells for one control case."
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    artifact = build_control_comparison(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
