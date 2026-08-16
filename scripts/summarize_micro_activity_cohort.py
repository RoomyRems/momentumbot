from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

EXPECTED_TYPE = "micro_volume_activity_cohort_case_comparison"
EXPECTED_POLICY = "runtime_market_data_only_no_retrospective_labels"
CELLS = (
    "baseline",
    "context_only",
    "volume_only",
    "context_plus_volume",
)
PAIRS = (
    "volume_only_vs_baseline",
    "context_plus_volume_vs_context_only",
    "context_only_vs_baseline",
    "context_plus_volume_vs_volume_only",
)


def _median(values: list[float | int]) -> float | None:
    return float(statistics.median(values)) if values else None


def _direction_counts(values: list[int | float]) -> dict[str, int]:
    return {
        "negative": sum(value < 0 for value in values),
        "zero": sum(value == 0 for value in values),
        "positive": sum(value > 0 for value in values),
    }


def _load_cases(root: Path) -> list[dict[str, object]]:
    paths = sorted(root.rglob("case-comparison.json"))
    if not paths:
        raise ValueError("no activity-cohort case comparisons found")
    cases: list[dict[str, object]] = []
    seen: set[str] = set()
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("artifact_type") != EXPECTED_TYPE:
            raise ValueError(f"unexpected case artifact: {path}")
        if payload.get("knowledge_policy") != EXPECTED_POLICY:
            raise ValueError(f"case is not label-blind: {path}")
        if payload.get("policy_promotion_eligible") is not False:
            raise ValueError(f"case improperly permits policy promotion: {path}")
        if set(payload.get("cells") or {}) != set(CELLS):
            raise ValueError(f"case does not contain the frozen four cells: {path}")
        if set(payload.get("paired_deltas") or {}) != set(PAIRS):
            raise ValueError(f"case does not contain the four predeclared contrasts: {path}")
        case_id = str(payload.get("case_id") or "")
        if not case_id or case_id in seen:
            raise ValueError(f"missing or duplicate case id: {case_id!r}")
        seen.add(case_id)
        cases.append(payload)
    return cases


def build_activity_summary(root: Path) -> dict[str, object]:
    cases = _load_cases(root)
    design_ids = {str(case["cohort_design_id"]) for case in cases}
    selection_hashes = {str(case["cohort_selection_sha256"]) for case in cases}
    if len(design_ids) != 1 or len(selection_hashes) != 1:
        raise ValueError("case comparisons came from different cohort selections")

    identities: dict[str, tuple[str, str]] = {}
    cell_summary: dict[str, dict[str, object]] = {}
    for cell in CELLS:
        cell_rows = [case["cells"][cell] for case in cases]
        cell_identities = {
            (str(row["policy_id"]), str(row["policy_fingerprint"]))
            for row in cell_rows
        }
        if len(cell_identities) != 1:
            raise ValueError(f"mixed policy identity in {cell}")
        identities[cell] = next(iter(cell_identities))
        plan_counts = [int(row["plan_count"]) for row in cell_rows]
        fill_counts = [int(row["filled_count"]) for row in cell_rows]
        first_plan_latency = [
            float(row["first_plan_latency_seconds"])
            for row in cell_rows
            if row.get("first_plan_latency_seconds") is not None
        ]
        first_fill_latency = [
            float(row["first_fill_latency_seconds"])
            for row in cell_rows
            if row.get("first_fill_latency_seconds") is not None
        ]
        cell_summary[cell] = {
            "policy_id": identities[cell][0],
            "policy_fingerprint": identities[cell][1],
            "total_plan_count": sum(plan_counts),
            "total_filled_count": sum(fill_counts),
            "cases_with_plan": sum(value > 0 for value in plan_counts),
            "cases_with_fill": sum(value > 0 for value in fill_counts),
            "median_plan_count_per_case": _median(plan_counts),
            "median_filled_count_per_case": _median(fill_counts),
            "median_first_plan_latency_seconds_when_present": _median(
                first_plan_latency
            ),
            "median_first_fill_latency_seconds_when_present": _median(
                first_fill_latency
            ),
        }

    paired_summary: dict[str, dict[str, object]] = {}
    for pair in PAIRS:
        rows = [case["paired_deltas"][pair] for case in cases]
        plan_deltas = [int(row["plan_count_delta"]) for row in rows]
        fill_deltas = [int(row["filled_count_delta"]) for row in rows]
        plan_shifts = [
            float(row["first_plan_shift_seconds"])
            for row in rows
            if row.get("first_plan_shift_seconds") is not None
        ]
        fill_shifts = [
            float(row["first_fill_shift_seconds"])
            for row in rows
            if row.get("first_fill_shift_seconds") is not None
        ]
        fill_states: dict[str, int] = {}
        for row in rows:
            state = str(row["first_fill_state"])
            fill_states[state] = fill_states.get(state, 0) + 1
        paired_summary[pair] = {
            "aggregate_plan_count_delta": sum(plan_deltas),
            "aggregate_filled_count_delta": sum(fill_deltas),
            "plan_count_delta_cases": _direction_counts(plan_deltas),
            "filled_count_delta_cases": _direction_counts(fill_deltas),
            "first_plan_shift_cases_when_both_present": _direction_counts(plan_shifts),
            "first_fill_shift_cases_when_both_present": _direction_counts(fill_shifts),
            "median_first_plan_shift_seconds_when_both_present": _median(plan_shifts),
            "median_first_fill_shift_seconds_when_both_present": _median(fill_shifts),
            "first_fill_state_counts": dict(sorted(fill_states.items())),
        }

    case_rows = []
    for case in sorted(cases, key=lambda item: (item["trading_date"], item["case_id"])):
        case_rows.append(
            {
                "case_id": case["case_id"],
                "symbol": case["symbol"],
                "trading_date": case["trading_date"],
                "selection_rank_within_date": case["selection_rank_within_date"],
                "candidate_qualified_at": case["candidate_qualified_at"],
                "cells": {
                    cell: {
                        "plan_count": case["cells"][cell]["plan_count"],
                        "filled_count": case["cells"][cell]["filled_count"],
                        "first_plan_pullback_number": case["cells"][cell][
                            "first_plan_pullback_number"
                        ],
                        "first_filled_pullback_number": case["cells"][cell][
                            "first_filled_pullback_number"
                        ],
                        "first_fill_price": case["cells"][cell]["first_fill_price"],
                    }
                    for cell in CELLS
                },
                "paired_deltas": case["paired_deltas"],
            }
        )

    return {
        "artifact_type": "micro_volume_activity_cohort_summary",
        "schema_version": 1,
        "knowledge_policy": EXPECTED_POLICY,
        "strategy_feedback": "activity_stress_only",
        "policy_promotion_eligible": False,
        "cohort_design_id": next(iter(design_ids)),
        "cohort_selection_sha256": next(iter(selection_hashes)),
        "case_count": len(cases),
        "trading_date_count": len({str(case["trading_date"]) for case in cases}),
        "cell_summary": cell_summary,
        "paired_summary": paired_summary,
        "cases": case_rows,
        "interpretation": [
            "all candidates were chosen by the precommitted calendar and causal qualification rule before micro replay",
            "all four cells for a case used the same frozen market input",
            "plan and fill counts are activity diagnostics, not portfolio trades or P&L",
            "no retrospective human behavior label was loaded or scored",
            "this conditional micro-layer cohort cannot estimate full-scanner false-positive rate or promote a policy",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_activity_summary(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
