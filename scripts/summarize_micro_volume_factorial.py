from __future__ import annotations

import argparse
import json
from pathlib import Path

from momentumbot.research.micro_volume_ablation import (
    MICRO_V0_2C_VOLUME_ID,
    MICRO_V0_2D_CONTEXT_VOLUME_ID,
)


def _load(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def _score_cell(score: dict[str, object]) -> dict[str, object]:
    price = score.get("price_references_descriptive_only")
    if not isinstance(price, dict):
        price = {}
    numbers = score.get("runtime_filled_pullback_numbers")
    if not isinstance(numbers, list):
        numbers = []
    return {
        "plan_count": score.get("runtime_plan_count"),
        "filled_count": score.get("runtime_filled_count"),
        "first_fill_price": price.get("first_runtime_fill_price"),
        "first_filled_pullback_number": numbers[0] if numbers else None,
        "closest_reported_fill_difference_from_first_fill": price.get(
            "closest_reported_fill_difference_from_first_fill"
        ),
        "comparable_dimensions": score.get("comparable_dimensions"),
        "matching_dimensions": score.get("matching_dimensions"),
        "structural_context_bars_available": score.get(
            "structural_context_bars_available"
        ),
    }


def _alignment(candidate: dict[str, object], baseline: dict[str, object]) -> str:
    candidate_fill = candidate.get("first_fill_price")
    baseline_fill = baseline.get("first_fill_price")
    candidate_diff = candidate.get("closest_reported_fill_difference_from_first_fill")
    baseline_diff = baseline.get("closest_reported_fill_difference_from_first_fill")
    if candidate_fill is None and baseline_fill is None:
        return "no_fill_either"
    if candidate_fill is None and baseline_fill is not None:
        return "lost_fill"
    if candidate_fill is not None and baseline_fill is None:
        return "gained_fill"
    if candidate_diff is None or baseline_diff is None:
        return "not_comparable"
    if candidate_diff < baseline_diff:
        return "closer"
    if candidate_diff > baseline_diff:
        return "farther"
    return "unchanged"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the 2x2 prequalification-context x hard-volume-gate comparison."
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--context-comparison", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    context_comparison = _load(args.context_comparison)
    context_cases = context_comparison.get("cases")
    if not isinstance(context_cases, list):
        raise TypeError("context comparison cases must be a list")
    historical = {
        str(case["benchmark_id"]): case
        for case in context_cases
        if isinstance(case, dict) and case.get("benchmark_id")
    }

    scores: dict[str, dict[str, dict[str, object]]] = {
        MICRO_V0_2C_VOLUME_ID: {},
        MICRO_V0_2D_CONTEXT_VOLUME_ID: {},
    }
    fingerprints: dict[str, str] = {}
    for path in sorted(args.root.rglob("case-score.json")):
        score = _load(path)
        ablation_id = str(score.get("ablation_id") or "")
        if ablation_id not in scores:
            continue
        benchmark_id = str(score.get("benchmark_id") or "")
        if not benchmark_id:
            raise ValueError(f"missing benchmark_id in {path}")
        scores[ablation_id][benchmark_id] = score
        fingerprint = str(score.get("ablation_fingerprint") or "")
        if fingerprint:
            fingerprints[ablation_id] = fingerprint

    expected_ids = set(historical)
    for ablation_id, grouped in scores.items():
        missing = expected_ids - set(grouped)
        if missing:
            raise ValueError(f"{ablation_id} missing scores for {sorted(missing)}")

    cases: list[dict[str, object]] = []
    totals = {
        "baseline": [0, 0],
        "context_only": [0, 0],
        "volume_only": [0, 0],
        "context_plus_volume": [0, 0],
    }
    interaction_first_fill_changes = 0

    for benchmark_id in sorted(historical):
        old = historical[benchmark_id]
        baseline = dict(old.get("baseline") or {})
        context_only = dict(old.get("ablation") or {})
        score_c = scores[MICRO_V0_2C_VOLUME_ID][benchmark_id]
        score_d = scores[MICRO_V0_2D_CONTEXT_VOLUME_ID][benchmark_id]
        volume_only = _score_cell(score_c)
        context_plus_volume = _score_cell(score_d)

        for name, cell in (
            ("baseline", baseline),
            ("context_only", context_only),
            ("volume_only", volume_only),
            ("context_plus_volume", context_plus_volume),
        ):
            totals[name][0] += int(cell.get("matching_dimensions") or 0)
            totals[name][1] += int(cell.get("comparable_dimensions") or 0)

        main_effect_fills = {
            baseline.get("first_fill_price"),
            context_only.get("first_fill_price"),
            volume_only.get("first_fill_price"),
        }
        if context_plus_volume.get("first_fill_price") not in main_effect_fills:
            interaction_first_fill_changes += 1

        cases.append(
            {
                "benchmark_id": benchmark_id,
                "symbol": old.get("symbol"),
                "reported_fill_references": old.get("reported_fill_references"),
                "cells": {
                    "baseline_context_off_volume_gate_on": baseline,
                    "context_on_volume_gate_on": context_only,
                    "context_off_volume_gate_off": volume_only,
                    "context_on_volume_gate_off": context_plus_volume,
                },
                "volume_only_alignment_vs_baseline_descriptive_only": _alignment(
                    volume_only, baseline
                ),
                "context_plus_volume_alignment_vs_baseline_descriptive_only": _alignment(
                    context_plus_volume, baseline
                ),
                "context_plus_volume_first_fill_differs_from_all_main_effect_cells": (
                    context_plus_volume.get("first_fill_price") not in main_effect_fills
                ),
                "exact_human_trade_identity_scored": False,
            }
        )

    cell_summary = {}
    for name, (matching, comparable) in totals.items():
        cell_summary[name] = {
            "matching_broad_behavior_dimensions": matching,
            "comparable_broad_behavior_dimensions": comparable,
            "broad_behavior_match_fraction_descriptive_only": (
                matching / comparable if comparable else None
            ),
        }

    artifact = {
        "artifact_type": "micro_volume_context_factorial_comparison",
        "schema_version": 1,
        "knowledge_policy": "post_replay_retrospective_evaluation_only",
        "strategy_feedback": "none",
        "parent_frozen_policy_id": "micro-v0.1",
        "parent_frozen_policy_fingerprint": context_comparison.get(
            "parent_frozen_policy_fingerprint"
        ),
        "existing_context_ablation_id": context_comparison.get("ablation_id"),
        "existing_context_ablation_fingerprint": context_comparison.get(
            "ablation_fingerprint"
        ),
        "volume_only_ablation_id": MICRO_V0_2C_VOLUME_ID,
        "volume_only_ablation_fingerprint": fingerprints.get(MICRO_V0_2C_VOLUME_ID),
        "context_plus_volume_ablation_id": MICRO_V0_2D_CONTEXT_VOLUME_ID,
        "context_plus_volume_ablation_fingerprint": fingerprints.get(
            MICRO_V0_2D_CONTEXT_VOLUME_ID
        ),
        "factor_definition": {
            "prequalification_context": "off = frozen v0.1 boundary; on = measured v0.2a 10-completed-bar bound",
            "hard_lower_pullback_volume_gate": "on = frozen v0.1 mean-volume rejection; off = volume retained as feature but not a rejection gate",
        },
        "cell_summary": cell_summary,
        "case_count": len(cases),
        "cases": cases,
        "interaction_diagnostic": {
            "cases_where_context_plus_volume_first_fill_differs_from_all_three_other_cells": interaction_first_fill_changes,
            "interpretation": "descriptive interaction signal only; not a fitted effect estimate or promotion criterion",
        },
        "exact_human_trade_identity_aggregate_score": None,
        "interpretation": [
            "the two new cells were replayed label-blind before retrospective scoring",
            "the context-on gate-on cell is the already-completed v0.2a experiment, not rerun or refit here",
            "turning off the hard volume gate introduces no fitted ratio threshold",
            "broad behavior matches and first-fill distances are diagnostic only",
            "the seed suite cannot by itself promote a policy",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
