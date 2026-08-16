from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, Sequence


def _load(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def _minimum_numeric(value: object) -> float | None:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return None
    numbers = [
        float(item)
        for item in value
        if isinstance(item, (int, float)) and not isinstance(item, bool)
    ]
    return min(numbers) if numbers else None


def _first_pullback(value: object) -> int | None:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        return None
    first = value[0]
    return int(first) if isinstance(first, int) and not isinstance(first, bool) else None


def _price_alignment_direction(
    baseline_difference: float | None,
    ablation_difference: float | None,
) -> str:
    if baseline_difference is None and ablation_difference is None:
        return "no_fill_either"
    if baseline_difference is None:
        return "ablation_added_fill"
    if ablation_difference is None:
        return "ablation_lost_fill"
    delta = baseline_difference - ablation_difference
    if abs(delta) < 1e-12:
        return "unchanged"
    return "closer" if delta > 0 else "farther"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare local-peak ablation scores with the frozen v0.1 seed baseline."
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--baseline-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    paths = sorted(args.root.rglob("case-score.json"))
    if not paths:
        raise FileNotFoundError(f"no case-score.json files under {args.root}")
    scores = [_load(path) for path in paths]
    baseline = _load(args.baseline_summary)
    if baseline.get("knowledge_policy") != "post_replay_retrospective_evaluation_only":
        raise ValueError("baseline summary is not post-replay evaluation only")

    baseline_cases_raw = baseline.get("cases")
    if not isinstance(baseline_cases_raw, Sequence) or isinstance(
        baseline_cases_raw, (str, bytes)
    ):
        raise TypeError("baseline cases must be a sequence")
    baseline_cases = {
        str(case.get("benchmark_id")): case
        for case in baseline_cases_raw
        if isinstance(case, Mapping)
    }

    ablation_ids = {score.get("ablation_id") for score in scores}
    fingerprints = {score.get("ablation_fingerprint") for score in scores}
    parents = {score.get("parent_frozen_policy_fingerprint") for score in scores}
    peak_rules = {score.get("peak_rule") for score in scores}
    peak_scopes = {score.get("peak_scope_bars") for score in scores}
    if (
        len(ablation_ids) != 1
        or len(fingerprints) != 1
        or len(parents) != 1
        or len(peak_rules) != 1
        or len(peak_scopes) != 1
    ):
        raise ValueError("local-peak scores do not share one ablation identity")
    if next(iter(parents)) != baseline.get("frozen_policy_fingerprint"):
        raise ValueError("ablation parent fingerprint differs from stored baseline")

    cases = []
    total_comparable = 0
    total_matching = 0
    alignment_counts: dict[str, int] = {}
    for score in scores:
        benchmark_id = str(score.get("benchmark_id") or "")
        base = baseline_cases.get(benchmark_id)
        if base is None:
            raise ValueError(f"baseline has no case {benchmark_id!r}")

        comparable = int(score.get("comparable_dimensions") or 0)
        matching = int(score.get("matching_dimensions") or 0)
        total_comparable += comparable
        total_matching += matching

        ablation_price = score.get("price_references_descriptive_only")
        if not isinstance(ablation_price, Mapping):
            ablation_price = {}
        baseline_price = base.get("price_references_descriptive_only")
        if not isinstance(baseline_price, Mapping):
            baseline_price = {}

        baseline_difference = _minimum_numeric(
            baseline_price.get("first_runtime_fill_absolute_differences")
        )
        ablation_difference = _minimum_numeric(
            ablation_price.get("first_runtime_fill_absolute_differences")
        )
        direction = _price_alignment_direction(
            baseline_difference, ablation_difference
        )
        alignment_counts[direction] = alignment_counts.get(direction, 0) + 1

        cases.append(
            {
                "benchmark_id": benchmark_id,
                "symbol": score.get("symbol"),
                "baseline": {
                    "plan_count": base.get("runtime_plan_count"),
                    "filled_count": base.get("runtime_filled_count"),
                    "first_fill_price": baseline_price.get("first_runtime_fill_price"),
                    "first_filled_pullback_number": _first_pullback(
                        base.get("runtime_filled_pullback_numbers")
                    ),
                    "closest_reported_fill_difference_from_first_fill": baseline_difference,
                    "matching_dimensions": base.get("matching_dimensions"),
                    "comparable_dimensions": base.get("comparable_dimensions"),
                },
                "ablation": {
                    "plan_count": score.get("runtime_plan_count"),
                    "filled_count": score.get("runtime_filled_count"),
                    "first_fill_price": ablation_price.get("first_runtime_fill_price"),
                    "first_filled_pullback_number": _first_pullback(
                        score.get("runtime_filled_pullback_numbers")
                    ),
                    "closest_reported_fill_difference_from_first_fill": ablation_difference,
                    "matching_dimensions": matching,
                    "comparable_dimensions": comparable,
                },
                "reported_fill_references": ablation_price.get(
                    "reported_fill_references"
                ),
                "price_alignment_direction_descriptive_only": direction,
                "exact_human_trade_identity_scored": False,
            }
        )

    artifact = {
        "artifact_type": "micro_local_peak_ablation_comparison",
        "schema_version": 1,
        "knowledge_policy": "post_replay_retrospective_evaluation_only",
        "strategy_feedback": "none",
        "ablation_id": next(iter(ablation_ids)),
        "ablation_fingerprint": next(iter(fingerprints)),
        "parent_frozen_policy_fingerprint": next(iter(parents)),
        "peak_rule": next(iter(peak_rules)),
        "peak_scope_bars": next(iter(peak_scopes)),
        "baseline_authoritative_workflow_run_id": baseline.get(
            "authoritative_workflow_run_id"
        ),
        "case_count": len(cases),
        "total_comparable_broad_behavior_dimensions": total_comparable,
        "total_matching_broad_behavior_dimensions": total_matching,
        "broad_behavior_match_fraction_descriptive_only": (
            total_matching / total_comparable if total_comparable else None
        ),
        "baseline_broad_behavior_match_fraction_descriptive_only": baseline.get(
            "broad_behavior_match_fraction_descriptive_only"
        ),
        "price_alignment_direction_counts_descriptive_only": dict(
            sorted(alignment_counts.items())
        ),
        "exact_human_trade_identity_aggregate_score": None,
        "interpretation": [
            "this isolates only full-window running-high versus parent-lookback local peak scope",
            "prequalification structural context remains disabled exactly as in frozen v0.1",
            "all other setup and execution rules remain the frozen parent rules",
            "first-fill price alignment is retrospective descriptive evidence only and was unavailable during runtime replay",
            "the seed suite is diagnostic and cannot by itself promote or optimize an ablation",
        ],
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
