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
    for score in scores:
        comparable = int(score.get("comparable_dimensions") or 0)
        matching = int(score.get("matching_dimensions") or 0)
        total_comparable += comparable
        total_matching += matching
        cases.append(
            {
                "benchmark_id": score.get("benchmark_id"),
                "symbol": score.get("symbol"),
                "case_role": score.get("case_role"),
                "runtime_status": score.get("runtime_status"),
                "runtime_plan_count": score.get("runtime_plan_count"),
                "runtime_filled_count": score.get("runtime_filled_count"),
                "runtime_filled_pullback_numbers": score.get("runtime_filled_pullback_numbers"),
                "comparable_dimensions": comparable,
                "matching_dimensions": matching,
                "scored_dimensions": score.get("scored_dimensions"),
                "price_references_descriptive_only": score.get(
                    "price_references_descriptive_only"
                ),
            }
        )

    artifact = {
        "artifact_type": "micro_v0_1_seed_suite_post_replay_summary",
        "schema_version": 1,
        "knowledge_policy": "post_replay_retrospective_evaluation_only",
        "strategy_feedback": "none",
        "case_count": len(cases),
        "frozen_policy_fingerprint": next(iter(fingerprints)),
        "total_comparable_dimensions": total_comparable,
        "total_matching_dimensions": total_matching,
        "dimension_match_fraction_descriptive_only": (
            total_matching / total_comparable if total_comparable else None
        ),
        "warning": (
            "This is an imitation/behavioral diagnostic on a deliberately selected seed suite, "
            "not a profitability estimate, statistical validation, or optimization objective."
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
