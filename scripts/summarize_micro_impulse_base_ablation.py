from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, Sequence

from momentumbot.research.micro_impulse_base_ablation import (
    MICRO_V0_2E_IMPULSE_BASE_ID,
)


def _load(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def _fill_prices(runtime: Mapping[str, object]) -> list[float]:
    values: list[float] = []
    steps = runtime.get("steps")
    if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes)):
        return values
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        outcome = step.get("outcome")
        if not isinstance(outcome, Mapping):
            continue
        price = outcome.get("fill_price")
        if isinstance(price, (int, float)) and not isinstance(price, bool):
            values.append(float(price))
    return values


def _first_pullback(value: object) -> int | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        return None
    first = value[0]
    return int(first) if isinstance(first, int) and not isinstance(first, bool) else None


def _minimum_difference(price: float | None, references: object) -> float | None:
    if price is None or not isinstance(references, Sequence) or isinstance(
        references, (str, bytes)
    ):
        return None
    values = [
        abs(price - float(value))
        for value in references
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    return min(values) if values else None


def _runtime_dimension(dimension: str, runtime: Mapping[str, object]) -> object:
    plan_count = int(runtime.get("plan_count") or 0)
    filled_count = int(runtime.get("filled_count") or 0)
    pullbacks = runtime.get("filled_pullback_numbers")
    first_pullback = _first_pullback(pullbacks)
    if dimension == "setup_detected":
        return plan_count > 0
    if dimension == "entry_participation":
        return filled_count > 0
    if dimension == "first_pullback_taken":
        return isinstance(pullbacks, Sequence) and 1 in pullbacks
    if dimension == "pullback_ordinal":
        return first_pullback
    raise ValueError(f"unsupported scored dimension {dimension!r}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare frozen-input impulse-base runtimes after replay."
    )
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--baseline-summary", type=Path, required=True)
    parser.add_argument("--workflow-run-id", type=int, required=True)
    parser.add_argument("--workflow-head-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    paths = sorted(args.runtime_root.rglob("runtime-replay.json"))
    if len(paths) != 4:
        raise ValueError(f"expected four scored ablation runtimes, found {len(paths)}")
    runtimes = [_load(path) for path in paths]
    baseline = _load(args.baseline_summary)
    baseline_cases_raw = baseline.get("cases")
    if not isinstance(baseline_cases_raw, Sequence) or isinstance(
        baseline_cases_raw, (str, bytes)
    ):
        raise TypeError("baseline cases must be a sequence")
    baseline_cases = {
        str(case.get("symbol")): case
        for case in baseline_cases_raw
        if isinstance(case, Mapping)
    }

    ablation_ids = {runtime.get("ablation_id") for runtime in runtimes}
    fingerprints = {runtime.get("ablation_fingerprint") for runtime in runtimes}
    parents = {runtime.get("parent_frozen_policy_fingerprint") for runtime in runtimes}
    if ablation_ids != {MICRO_V0_2E_IMPULSE_BASE_ID}:
        raise ValueError("unexpected impulse-base ablation identity")
    if len(fingerprints) != 1 or len(parents) != 1:
        raise ValueError("runtimes do not share one ablation and parent fingerprint")
    if next(iter(parents)) != baseline.get("frozen_policy_fingerprint"):
        raise ValueError("ablation parent differs from frozen baseline")
    if not all(runtime.get("source_policy_reproduced_exactly") is True for runtime in runtimes):
        raise ValueError("a source baseline did not reproduce exactly")

    cases: list[dict[str, object]] = []
    total_comparable = 0
    total_matching = 0
    baseline_plans = 0
    baseline_fills = 0
    ablation_plans = 0
    ablation_fills = 0
    for runtime in sorted(runtimes, key=lambda item: str(item.get("symbol"))):
        symbol = str(runtime.get("symbol") or "")
        base = baseline_cases.get(symbol)
        if base is None:
            raise ValueError(f"baseline has no case for {symbol}")
        dimensions_raw = base.get("scored_dimensions")
        if not isinstance(dimensions_raw, Mapping):
            raise TypeError(f"baseline dimensions missing for {symbol}")
        dimensions: dict[str, dict[str, object]] = {}
        for name, base_dimension in dimensions_raw.items():
            if not isinstance(base_dimension, Mapping):
                raise TypeError(f"invalid baseline dimension {name!r}")
            observed = base_dimension.get("observed")
            actual = _runtime_dimension(str(name), runtime)
            comparable = observed is not None and actual is not None
            match = observed == actual if comparable else None
            dimensions[str(name)] = {
                "observed": observed,
                "runtime": actual,
                "comparable": comparable,
                "match": match,
            }
            total_comparable += int(comparable)
            total_matching += int(match is True)

        base_price = base.get("price_references_descriptive_only")
        if not isinstance(base_price, Mapping):
            base_price = {}
        references = base_price.get("reported_fill_references")
        fill_prices = _fill_prices(runtime)
        first_fill = fill_prices[0] if fill_prices else None
        base_first_fill_raw = base_price.get("first_runtime_fill_price")
        base_first_fill = (
            float(base_first_fill_raw)
            if isinstance(base_first_fill_raw, (int, float))
            and not isinstance(base_first_fill_raw, bool)
            else None
        )
        base_plan_count = int(base.get("runtime_plan_count") or 0)
        base_filled_count = int(base.get("runtime_filled_count") or 0)
        ablation_plan_count = int(runtime.get("plan_count") or 0)
        ablation_filled_count = int(runtime.get("filled_count") or 0)
        baseline_plans += base_plan_count
        baseline_fills += base_filled_count
        ablation_plans += ablation_plan_count
        ablation_fills += ablation_filled_count
        cases.append(
            {
                "benchmark_id": base.get("benchmark_id"),
                "symbol": symbol,
                "baseline": {
                    "plan_count": base_plan_count,
                    "filled_count": base_filled_count,
                    "first_fill_price": base_first_fill,
                    "first_filled_pullback_number": _first_pullback(
                        base.get("runtime_filled_pullback_numbers")
                    ),
                },
                "ablation": {
                    "plan_count": ablation_plan_count,
                    "filled_count": ablation_filled_count,
                    "first_fill_price": first_fill,
                    "fill_prices": fill_prices,
                    "filled_pullback_numbers": runtime.get(
                        "filled_pullback_numbers"
                    ),
                    "first_filled_pullback_number": _first_pullback(
                        runtime.get("filled_pullback_numbers")
                    ),
                    "reason_counts": runtime.get("reason_counts"),
                },
                "reported_fill_references": references,
                "baseline_first_fill_closest_difference": _minimum_difference(
                    base_first_fill, references
                ),
                "ablation_first_fill_closest_difference": _minimum_difference(
                    first_fill, references
                ),
                "scored_dimensions": dimensions,
                "source_artifact": {
                    "workflow_run_id": runtime.get("source_workflow_run_id"),
                    "artifact_id": runtime.get("source_artifact_id"),
                    "artifact_name": runtime.get("source_artifact_name"),
                    "digest_sha256": runtime.get("source_artifact_digest_sha256"),
                    "baseline_runtime_core_sha256": runtime.get(
                        "source_baseline_runtime_core_sha256"
                    ),
                },
                "exact_human_trade_identity_scored": False,
            }
        )

    artifact = {
        "artifact_type": "micro_qualification_anchored_impulse_base_ablation_comparison",
        "schema_version": 1,
        "knowledge_policy": "post_replay_retrospective_evaluation_only",
        "strategy_feedback": "none",
        "ablation_id": next(iter(ablation_ids)),
        "ablation_fingerprint": next(iter(fingerprints)),
        "parent_frozen_policy_fingerprint": next(iter(parents)),
        "workflow_run_id": args.workflow_run_id,
        "workflow_head_sha": args.workflow_head_sha,
        "source_baseline_workflow_run_id": baseline.get(
            "authoritative_workflow_run_id"
        ),
        "case_count": len(cases),
        "total_comparable_broad_behavior_dimensions": total_comparable,
        "total_matching_broad_behavior_dimensions": total_matching,
        "broad_behavior_match_fraction_descriptive_only": (
            total_matching / total_comparable if total_comparable else None
        ),
        "activity": {
            "baseline_plan_count": baseline_plans,
            "ablation_plan_count": ablation_plans,
            "plan_count_delta": ablation_plans - baseline_plans,
            "baseline_filled_count": baseline_fills,
            "ablation_filled_count": ablation_fills,
            "filled_count_delta": ablation_fills - baseline_fills,
        },
        "interpretation": [
            "the runtime ablation changes only the retracement impulse base",
            "every case reuses and exactly reproduces its frozen v0.1 input/runtime core before the ablation is applied",
            "first-fill price alignment is retrospective descriptive evidence only",
            "the four-case scored seed is diagnostic and cannot promote a policy",
        ],
        "decision": {
            "promote": False,
            "reason": (
                "the change adds later plans and fills without moving the first modeled "
                "trade for DSY, TIVC, MMA, or UPXI"
            ),
        },
        "cases": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
