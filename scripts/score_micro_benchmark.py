from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from momentumbot.micro_benchmark import compare_micro_runtime_to_label


def _load_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare an already-produced micro runtime replay to a retrospective benchmark label."
    )
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    runtime = _load_json(args.runtime)
    benchmark = _load_json(args.benchmark)
    comparison = compare_micro_runtime_to_label(runtime, benchmark)
    artifact = {
        "artifact_type": "micro_benchmark_post_replay_comparison",
        "schema_version": 1,
        "knowledge_policy": "post_replay_retrospective_evaluation_only",
        "runtime_artifact_knowledge_policy": runtime.get("knowledge_policy"),
        "benchmark_knowledge_policy": benchmark.get("knowledge_policy"),
        "benchmark_id": comparison.benchmark_id,
        "symbol": comparison.symbol,
        "runtime_policy_name": comparison.runtime_policy_name,
        "comparable_fields": comparison.comparable_fields,
        "matching_fields": comparison.matching_fields,
        "strategy_feedback": "none",
        "comparison": asdict(comparison),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
