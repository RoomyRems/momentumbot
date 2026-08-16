from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, Sequence

from momentumbot.research.benchmark_suite import load_benchmark_suite
from momentumbot.research.micro_context_ablation import MICRO_V0_2A_CONTEXT_ID

RUNTIME_POLICY = "runtime_market_data_only_no_retrospective_labels"
LABEL_POLICY = "ground_truth_label_only_never_runtime_context"
RUNTIME_ARTIFACT = "micro_candidate_runtime_replay_ablation"


def _load(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def _bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _int(value: object) -> int | None:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else None


def _float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _numeric_sequence(value: object) -> tuple[float, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return ()
    return tuple(
        float(item)
        for item in value
        if isinstance(item, (int, float)) and not isinstance(item, bool)
    )


def _reported_fills(observed: Mapping[str, object]) -> tuple[float, ...]:
    values: list[float] = []
    for key in ("reported_fill_approx", "reported_entry", "reported_first_entry"):
        numeric = _float(observed.get(key))
        if numeric is not None:
            values.append(numeric)
    for key in ("reported_entry_fills_approx", "reported_entry_fills"):
        values.extend(_numeric_sequence(observed.get(key)))
    return tuple(values)


def _runtime_fills(runtime: Mapping[str, object]) -> tuple[float, ...]:
    raw_steps = runtime.get("steps")
    if not isinstance(raw_steps, Sequence) or isinstance(raw_steps, (str, bytes)):
        return ()
    values: list[float] = []
    for raw_step in raw_steps:
        if not isinstance(raw_step, Mapping):
            continue
        outcome = raw_step.get("outcome")
        if not isinstance(outcome, Mapping):
            continue
        fill = _float(outcome.get("fill_price"))
        if fill is not None:
            values.append(fill)
    return tuple(values)


def _difference_matrix(runtime: tuple[float, ...], observed: tuple[float, ...]):
    return [
        [abs(runtime_price - observed_price) for observed_price in observed]
        for runtime_price in runtime
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Score the pre-qualification-context ablation only after its label-blind "
            "runtime replay has completed."
        )
    )
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    runtime = _load(args.runtime)
    benchmark = _load(args.benchmark)
    suite = load_benchmark_suite(args.suite)
    if runtime.get("knowledge_policy") != RUNTIME_POLICY:
        raise ValueError("runtime artifact is not label-blind")
    if benchmark.get("knowledge_policy") != LABEL_POLICY:
        raise ValueError("benchmark is not retrospective-label-only")
    if runtime.get("symbol") != benchmark.get("symbol"):
        raise ValueError("runtime and benchmark symbols differ")
    if runtime.get("ablation_id") != MICRO_V0_2A_CONTEXT_ID:
        raise ValueError("runtime is not the expected context ablation")
    if runtime.get("parent_frozen_policy_id") != suite.policy_id:
        raise ValueError("ablation parent policy does not match benchmark suite")

    benchmark_id = str(benchmark.get("benchmark_id") or "")
    suite_case = next(
        (case for case in suite.cases if case.benchmark_id == benchmark_id), None
    )
    if suite_case is None:
        raise ValueError(f"benchmark {benchmark_id!r} is not in suite {suite.suite_id!r}")

    observed_raw = benchmark.get("observed_human_behavior")
    if not isinstance(observed_raw, Mapping):
        raise TypeError("benchmark observed_human_behavior must be a mapping")
    observed = observed_raw

    runtime_available = runtime.get("artifact_type") == RUNTIME_ARTIFACT
    runtime_status = str(
        runtime.get("status") or ("replayed" if runtime_available else "unavailable")
    )
    plan_count = int(runtime.get("plan_count") or 0) if runtime_available else 0
    filled_count = int(runtime.get("filled_count") or 0) if runtime_available else 0
    raw_numbers = runtime.get("filled_pullback_numbers", []) if runtime_available else []
    filled_numbers = (
        tuple(
            int(value)
            for value in raw_numbers
            if isinstance(value, int) and not isinstance(value, bool)
        )
        if isinstance(raw_numbers, Sequence) and not isinstance(raw_numbers, (str, bytes))
        else ()
    )

    observed_setup = observed.get("setup_type")
    observed_trade_taken = _bool(observed.get("trade_taken"))
    observed_first_taken = _bool(observed.get("first_pullback_taken"))
    observed_ordinal = _int(observed.get("pullback_ordinal"))

    runtime_setup = (plan_count > 0) if runtime_available else None
    runtime_participation = (filled_count > 0) if runtime_available else None
    runtime_first_taken = (1 in filled_numbers) if runtime_available else None
    runtime_first_ordinal = (
        filled_numbers[0] if runtime_available and filled_numbers else None
    )
    candidates: dict[str, tuple[object, object]] = {
        "setup_detected": (
            observed_setup == "micro_pullback" if isinstance(observed_setup, str) else None,
            runtime_setup,
        ),
        "entry_participation": (observed_trade_taken, runtime_participation),
        "first_pullback_taken": (observed_first_taken, runtime_first_taken),
        "pullback_ordinal": (observed_ordinal, runtime_first_ordinal),
    }

    dimensions: dict[str, dict[str, object]] = {}
    for dimension in suite_case.scored_dimensions:
        if dimension not in candidates:
            raise ValueError(f"unsupported scored dimension {dimension!r}")
        expected, actual = candidates[dimension]
        dimensions[dimension] = {
            "observed": expected,
            "runtime": actual,
            "comparable": expected is not None and actual is not None,
            "match": expected == actual if expected is not None and actual is not None else None,
        }

    reported_fills = _reported_fills(observed)
    runtime_fills = _runtime_fills(runtime) if runtime_available else ()
    first_runtime_fill = runtime_fills[0] if runtime_fills else None
    first_fill_differences = (
        [abs(first_runtime_fill - reference) for reference in reported_fills]
        if first_runtime_fill is not None
        else []
    )
    comparable = sum(bool(value["comparable"]) for value in dimensions.values())
    matching = sum(value["match"] is True for value in dimensions.values())

    artifact = {
        "artifact_type": "micro_context_ablation_suite_case_post_replay_score",
        "schema_version": 1,
        "knowledge_policy": "post_replay_retrospective_evaluation_only",
        "strategy_feedback": "none",
        "suite_id": suite.suite_id,
        "benchmark_id": benchmark_id,
        "symbol": benchmark.get("symbol"),
        "case_role": suite_case.role.value,
        "tags": list(suite_case.tags),
        "rationale": suite_case.rationale,
        "ablation_id": runtime.get("ablation_id"),
        "ablation_fingerprint": runtime.get("ablation_fingerprint"),
        "parent_frozen_policy_id": runtime.get("parent_frozen_policy_id"),
        "parent_frozen_policy_fingerprint": runtime.get(
            "parent_frozen_policy_fingerprint"
        ),
        "structural_context_bars_requested": runtime.get(
            "structural_context_bars_requested"
        ),
        "structural_context_bars_available": runtime.get(
            "structural_context_bars_available"
        ),
        "structural_context_start": runtime.get("structural_context_start"),
        "upstream_runtime_available": runtime_available,
        "runtime_status": runtime_status,
        "runtime_plan_count": plan_count if runtime_available else None,
        "runtime_filled_count": filled_count if runtime_available else None,
        "runtime_filled_pullback_numbers": list(filled_numbers) if runtime_available else None,
        "dimension_semantics": {
            "setup_detected": "any ablation plan during the eligible post-qualification replay window; not exact setup identity",
            "entry_participation": "any ablation fill during the eligible post-qualification replay window; not exact human-trade identity",
            "first_pullback_taken": "whether the ablation filled pullback ordinal 1 under its structural context",
            "pullback_ordinal": "first ablation filled pullback ordinal versus explicit human ordinal",
        },
        "exact_human_trade_identity_scored": False,
        "scored_dimensions": dimensions,
        "comparable_dimensions": comparable,
        "matching_dimensions": matching,
        "price_references_descriptive_only": {
            "runtime_fill_prices": list(runtime_fills),
            "first_runtime_fill_price": first_runtime_fill,
            "reported_fill_references": list(reported_fills),
            "first_runtime_fill_absolute_differences": first_fill_differences,
            "absolute_difference_matrix": _difference_matrix(runtime_fills, reported_fills),
            "used_for_policy_selection": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
