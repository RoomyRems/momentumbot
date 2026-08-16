from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize already-scored Micro benchmark cases without feeding results back to strategy."
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    paths = sorted(args.root.rglob("case-score.json"))
    if not paths:
        raise FileNotFoundError(f"no case-score.json files under {args.root}")
    scores = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    fingerprints = {score.get("frozen_policy_fingerprint") for score in scores}
    if len(fingerprints) != 1:
        raise ValueError("suite cases were not scored with one frozen policy fingerprint")

    cases = []
    total_comparable = 0
    total_matching = 0
    available_cases = 0
    unavailable_cases = 0
    for score in scores:
        comparable = int(score.get("comparable_dimensions") or 0)
        matching = int(score.get("matching_dimensions") or 0)
        total_comparable += comparable
        total_matching += matching
        available = bool(score.get("upstream_runtime_available"))
        if available:
            available_cases += 1
        else:
            unavailable_cases += 1
        price = score.get("price_references_descriptive_only") or {}
        cases.append(
            {
                "benchmark_id": score.get("benchmark_id"),
                "symbol": score.get("symbol"),
                "case_role": score.get("case_role"),
                "upstream_runtime_available": available,
                "runtime_status": score.get("runtime_status"),
                "runtime_plan_count": score.get("runtime_plan_count"),
                "runtime_filled_count": score.get("runtime_filled_count"),
                "runtime_filled_pullback_numbers": score.get("runtime_filled_pullback_numbers"),
                "comparable_dimensions": comparable,
                "matching_dimensions": matching,
                "exact_human_trade_identity_scored": score.get(
                    "exact_human_trade_identity_scored"
                ),
                "scored_dimensions": score.get("scored_dimensions"),
                "first_runtime_fill_price": price.get("first_runtime_fill_price"),
                "reported_fill_references": price.get("reported_fill_references"),
                "first_runtime_fill_absolute_differences": price.get(
                    "first_runtime_fill_absolute_differences"
                ),
                "price_references_descriptive_only": price,
            }
        )

    broad_fraction = total_matching / total_comparable if total_comparable else None
    artifact = {
        "artifact_type": "micro_v0_1_seed_suite_post_replay_summary",
        "schema_version": 2,
        "knowledge_policy": "post_replay_retrospective_evaluation_only",
        "strategy_feedback": "none",
        "case_count": len(cases),
        "upstream_runtime_available_case_count": available_cases,
        "upstream_runtime_unavailable_case_count": unavailable_cases,
        "frozen_policy_fingerprint": next(iter(fingerprints)),
        "total_comparable_broad_behavior_dimensions": total_comparable,
        "total_matching_broad_behavior_dimensions": total_matching,
        "broad_behavior_match_fraction_descriptive_only": broad_fraction,
        "exact_human_trade_identity_aggregate_score": None,
        "interpretation": [
            "setup_detected and entry_participation mean any plan/fill during the eligible post-qualification window, not the same human trade",
            "an upstream-unavailable case is non-comparable for micro behavior rather than counted as a micro failure",
            "reported-entry price differences are descriptive evidence of trade-identity mismatch and are never fed back into Micro v0.1",
            "the broad behavior fraction must not be described as imitation accuracy or strategy profitability",
        ],
        "warning": (
            "This is a deliberately selected behavioral seed-suite diagnostic, not a profitability estimate, "
            "statistical validation, exact-trade imitation score, or optimization objective."
        ),
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
