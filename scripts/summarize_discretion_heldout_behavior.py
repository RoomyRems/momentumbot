from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Mapping

from momentumbot.identity_resolved_universe import json_fingerprint
from momentumbot.research.discretion_heldout_comparison import (
    build_discretion_heldout_comparison,
    validate_discretion_heldout_comparison,
)
from momentumbot.research.discretion_heldout_labels import (
    load_discretion_heldout_labels,
)
from momentumbot.research.discretion_heldout_panel import REGISTERED_DATES
from scripts.summarize_discretion_heldout_micro_runtime import build_panel_manifest


MICRO_ARTIFACT_ID = "ross-discretion-heldout-micro-runtime-v0.1"
SHADOW_ARTIFACT_ID = "ross-discretion-shadow-runtime-v0.1"
SHADOW_DATE_FILES = {
    "attention": (
        "attention-leadership.json",
        "attention-leadership-heldout-shadow-v0.1",
        "attention_content_sha256",
        "attention_row_count",
    ),
    "timing": (
        "catalyst-timing.json",
        "catalyst-timing-heldout-shadow-v0.1",
        "catalyst_timing_content_sha256",
        "catalyst_timing_row_count",
    ),
    "evidence": (
        "catalyst-evidence-packets.json",
        "catalyst-evidence-heldout-shadow-v0.1",
        "catalyst_evidence_content_sha256",
        "catalyst_evidence_packet_count",
    ),
}


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _validated_content_hash(
    payload: Mapping[str, object], *, description: str
) -> str:
    claimed = payload.get("content_sha256")
    projection = {
        key: value for key, value in payload.items() if key != "content_sha256"
    }
    if not isinstance(claimed, str) or claimed != json_fingerprint(projection):
        raise ValueError(f"{description} content fingerprint mismatch")
    return claimed


def _group_rows(
    rows: object,
    *,
    description: str,
) -> dict[str, list[dict[str, object]]]:
    if not isinstance(rows, list):
        raise ValueError(f"{description} rows must be a list")
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise ValueError(f"{description} row must be an object")
        symbol = raw.get("symbol")
        decision_time = raw.get("decision_time")
        if not isinstance(symbol, str) or not isinstance(decision_time, str):
            raise ValueError(f"{description} row lacks symbol/decision_time")
        key = (symbol, decision_time)
        if key in seen:
            raise ValueError(f"{description} contains a duplicate decision row")
        seen.add(key)
        grouped[symbol].append(dict(raw))
    for symbol_rows in grouped.values():
        symbol_rows.sort(key=lambda row: str(row["decision_time"]))
    return dict(grouped)


def _load_micro_candidates(
    root: Path,
    *,
    expected_content_sha256: str,
    expected_activations: Mapping[str, Mapping[str, str]],
) -> dict[tuple[str, str], dict[str, object]]:
    frozen_manifest = _read_json(root / "manifest.json")
    if frozen_manifest.get("artifact_id") != MICRO_ARTIFACT_ID:
        raise ValueError("unexpected held-out Micro artifact")
    if _validated_content_hash(
        frozen_manifest, description="held-out Micro manifest"
    ) != expected_content_sha256:
        raise ValueError("held-out Micro manifest differs from frozen labels")

    rebuilt_manifest = build_panel_manifest(root / "dates")
    if rebuilt_manifest != frozen_manifest:
        raise ValueError("held-out Micro artifact does not reproduce its manifest")

    result: dict[tuple[str, str], dict[str, object]] = {}
    raw_candidates = frozen_manifest.get("candidate_results")
    if not isinstance(raw_candidates, list):
        raise ValueError("held-out Micro manifest lacks candidate results")
    for raw in raw_candidates:
        if not isinstance(raw, Mapping):
            raise ValueError("held-out Micro candidate result must be an object")
        trading_date = str(raw["trading_date"])
        symbol = str(raw["symbol"])
        key = (trading_date, symbol)
        if key in result:
            raise ValueError("held-out Micro candidate is duplicated")
        runtime = _read_json(
            root / "dates" / trading_date / symbol / "runtime-replay.json"
        )
        if runtime.get("content_sha256") != raw.get("runtime_content_sha256"):
            raise ValueError("Micro candidate does not bind its runtime payload")
        status = str(raw["status"])
        plans = runtime.get("plan_count")
        fills = runtime.get("filled_count")
        first_plan_armed_at = None
        first_plan_pullback_number = None
        first_fill_time = None
        first_fill_price = None
        first_fill_pullback_number = None
        if status == "replayed":
            steps = runtime.get("steps")
            if not isinstance(steps, list):
                raise ValueError("replayed Micro runtime lacks steps")
            plan_steps = [
                step
                for step in steps
                if isinstance(step, Mapping) and step.get("reason") == "plan"
            ]
            if len(plan_steps) != plans:
                raise ValueError("Micro plan steps do not match the frozen count")
            if plan_steps:
                first_plan = min(
                    plan_steps,
                    key=lambda step: str(step["plan"]["armed_at"]),
                )
                first_plan_armed_at = first_plan["plan"]["armed_at"]
                first_plan_pullback_number = first_plan["pullback_number"]
            filled_steps = [
                step
                for step in plan_steps
                if isinstance(step.get("outcome"), Mapping)
                and step["outcome"].get("fill_time") is not None
            ]
            if len(filled_steps) != fills:
                raise ValueError("Micro fill steps do not match the frozen count")
            if [step["pullback_number"] for step in filled_steps] != runtime.get(
                "filled_pullback_numbers"
            ):
                raise ValueError("Micro filled pullback sequence is inconsistent")
            if filled_steps:
                first_fill = min(
                    filled_steps,
                    key=lambda step: str(step["outcome"]["fill_time"]),
                )
                first_fill_time = first_fill["outcome"]["fill_time"]
                first_fill_price = first_fill["outcome"]["fill_price"]
                first_fill_pullback_number = first_fill["pullback_number"]
        elif plans is not None or fills is not None:
            raise ValueError("unavailable Micro runtime must retain null activity")

        result[key] = {
            "status": status,
            "candidate_qualified_at": raw["candidate_qualified_at"],
            "plan_count": plans,
            "filled_count": fills,
            "first_plan_armed_at": first_plan_armed_at,
            "first_plan_pullback_number": first_plan_pullback_number,
            "first_fill_time": first_fill_time,
            "first_fill_price": first_fill_price,
            "first_fill_pullback_number": first_fill_pullback_number,
            "runtime_content_sha256": raw["runtime_content_sha256"],
        }

    expected_keys = {
        (trading_date, symbol)
        for trading_date, activations in expected_activations.items()
        for symbol in activations
    }
    if set(result) != expected_keys:
        raise ValueError("Micro candidates differ from the frozen scanner runtime")
    for key, row in result.items():
        if row["candidate_qualified_at"] != expected_activations[key[0]][key[1]]:
            raise ValueError("Micro activation differs from the frozen scanner runtime")
    return result


def _validate_shadow_payload(
    payload: Mapping[str, object],
    *,
    trading_date: str,
    artifact_id: str,
    expected_hash: str,
    expected_row_count: int,
    source_runtime_hash: str,
) -> list[dict[str, object]]:
    if payload.get("schema_version") != 1 or payload.get("artifact_id") != artifact_id:
        raise ValueError("unexpected held-out shadow date artifact")
    if payload.get("trading_date") != trading_date:
        raise ValueError("held-out shadow artifact date mismatch")
    if _validated_content_hash(
        payload, description=f"{trading_date} {artifact_id}"
    ) != expected_hash:
        raise ValueError("shadow date hash differs from its root manifest")
    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != expected_row_count:
        raise ValueError("shadow date row count mismatch")
    if payload.get("row_count") != len(rows):
        raise ValueError("shadow payload row_count is inconsistent")
    knowledge = payload.get("knowledge_policy")
    if not isinstance(knowledge, Mapping):
        raise ValueError("shadow payload lacks a knowledge policy")
    if knowledge.get("runtime_strategy_effect") != "none" or any(
        knowledge.get(field) is not False
        for field in (
            "uses_ross_actions",
            "uses_benchmark_labels",
            "uses_retrospective_trade_outcomes",
            "uses_later_price_outcomes",
        )
    ):
        raise ValueError("shadow payload violates the causal boundary")
    sources = payload.get("source_hashes")
    if not isinstance(sources, Mapping) or sources.get(
        "heldout_runtime"
    ) != source_runtime_hash:
        raise ValueError("shadow payload source runtime mismatch")
    return [dict(row) for row in rows]


def _load_shadow_candidates(
    root: Path,
    *,
    expected_content_sha256: str,
    expected_source_runtime_sha256: str,
    expected_activations: Mapping[str, Mapping[str, str]],
) -> dict[tuple[str, str], dict[str, object]]:
    manifest = _read_json(root / "manifest.json")
    if manifest.get("artifact_id") != SHADOW_ARTIFACT_ID:
        raise ValueError("unexpected held-out shadow artifact")
    if _validated_content_hash(
        manifest, description="held-out shadow manifest"
    ) != expected_content_sha256:
        raise ValueError("held-out shadow manifest differs from frozen labels")
    if manifest.get("dates") != list(REGISTERED_DATES):
        raise ValueError("held-out shadow dates differ from registration")
    if manifest.get(
        "source_heldout_runtime_content_sha256"
    ) != expected_source_runtime_sha256:
        raise ValueError("held-out shadow source differs from frozen labels")
    knowledge = manifest.get("knowledge_policy")
    if not isinstance(knowledge, Mapping) or knowledge.get(
        "runtime_strategy_effect"
    ) != "none":
        raise ValueError("held-out shadow root cannot affect runtime")
    if any(
        knowledge.get(field) is not False
        for field in (
            "uses_ross_actions",
            "uses_benchmark_labels",
            "uses_retrospective_trade_outcomes",
            "uses_later_price_outcomes",
            "future_news_exposed",
        )
    ):
        raise ValueError("held-out shadow root violates the causal boundary")
    eligibility = manifest.get("eligibility")
    if not isinstance(eligibility, Mapping) or eligibility.get(
        "policy_promotion_eligible"
    ) is not False:
        raise ValueError("held-out shadow root overclaims policy eligibility")

    date_results = manifest.get("date_results")
    if not isinstance(date_results, Mapping):
        raise ValueError("held-out shadow manifest lacks date results")
    result: dict[tuple[str, str], dict[str, object]] = {}
    for trading_date in REGISTERED_DATES:
        date_summary = date_results.get(trading_date)
        if not isinstance(date_summary, Mapping):
            raise ValueError("held-out shadow date result is missing")
        loaded: dict[str, list[dict[str, object]]] = {}
        for kind, (
            filename,
            artifact_id,
            hash_field,
            count_field,
        ) in SHADOW_DATE_FILES.items():
            loaded[kind] = _validate_shadow_payload(
                _read_json(root / trading_date / filename),
                trading_date=trading_date,
                artifact_id=artifact_id,
                expected_hash=str(date_summary[hash_field]),
                expected_row_count=int(date_summary[count_field]),
                source_runtime_hash=expected_source_runtime_sha256,
            )

        attention = _group_rows(
            loaded["attention"], description=f"{trading_date} attention"
        )
        timing = _group_rows(
            loaded["timing"], description=f"{trading_date} catalyst timing"
        )
        evidence = _group_rows(
            loaded["evidence"], description=f"{trading_date} catalyst evidence"
        )
        candidates = set(expected_activations[trading_date])
        if set(attention) != candidates or set(timing) != candidates or set(evidence) != candidates:
            raise ValueError("shadow candidate set differs from frozen scanner runtime")

        for symbol in sorted(candidates):
            attention_rows = attention[symbol]
            timing_rows = timing[symbol]
            evidence_rows = evidence[symbol]
            activation = expected_activations[trading_date][symbol]
            if not attention_rows or not timing_rows or not evidence_rows:
                raise ValueError("shadow candidate lacks required causal rows")
            if attention_rows[0].get("activation_time") != activation or timing_rows[
                0
            ].get("activation_time") != activation:
                raise ValueError("shadow activation differs from scanner runtime")
            attention_keys = [row["decision_time"] for row in attention_rows]
            timing_keys = [row["decision_time"] for row in timing_rows]
            if attention_keys != timing_keys:
                raise ValueError("shadow attention and timing grids differ")

            activation_attention = attention_rows[0]
            activation_timing = timing_rows[0]
            observed_ranks = [
                int(row["candidate_top_gainer_rank"])
                for row in attention_rows
                if row.get("candidate_top_gainer_rank") is not None
            ]
            observed_gains = [
                float(row["candidate_percent_gain"])
                for row in attention_rows
                if row.get("candidate_percent_gain") is not None
            ]
            leader_rows = [
                row for row in attention_rows if row.get("candidate_is_market_leader") is True
            ]
            new_news_rows = [
                row
                for row in timing_rows
                if row.get("new_provider_news_became_available_this_minute") is True
                and str(row["decision_time"]) > activation
            ]
            result[(trading_date, symbol)] = {
                "activation_time": activation,
                "rank_at_activation": activation_attention.get(
                    "candidate_top_gainer_rank"
                ),
                "best_rank": min(observed_ranks) if observed_ranks else None,
                "ever_market_leader": bool(leader_rows),
                "first_leader_decision_time": (
                    leader_rows[0]["decision_time"] if leader_rows else None
                ),
                "max_percent_gain_before_cutoff": (
                    max(observed_gains) if observed_gains else None
                ),
                "news_state_at_activation": activation_timing["provider_news_state"],
                "provider_news_present_at_activation": activation_timing[
                    "provider_news_present_at_activation"
                ],
                "candidate_qualified_before_first_provider_news": activation_timing[
                    "candidate_qualified_before_first_provider_news"
                ],
                "news_arrived_after_activation": bool(new_news_rows),
                "first_new_provider_news_decision_time": (
                    new_news_rows[0]["decision_time"] if new_news_rows else None
                ),
                "provider_news_event_count_at_cutoff": timing_rows[-1][
                    "provider_news_event_count_as_of"
                ],
                "catalyst_evidence_packet_count": len(evidence_rows),
            }
    expected_keys = {
        (trading_date, symbol)
        for trading_date, activations in expected_activations.items()
        for symbol in activations
    }
    if set(result) != expected_keys:
        raise ValueError("shadow summary differs from frozen scanner candidates")
    return result


def build_comparison_from_frozen_artifacts(
    *,
    labels_path: Path,
    runtime_audit_path: Path,
    micro_root: Path,
    shadow_root: Path,
) -> dict[str, object]:
    labels = load_discretion_heldout_labels(
        labels_path, runtime_audit_path=runtime_audit_path
    )
    date_results = labels["date_results"]
    if not isinstance(date_results, Mapping):
        raise ValueError("held-out labels lack date results")
    activations = {
        trading_date: dict(date_results[trading_date]["candidate_activations"])
        for trading_date in REGISTERED_DATES
    }
    frozen_runtime = labels["frozen_runtime"]
    micro_meta = frozen_runtime["micro_runtime"]
    scanner_meta = frozen_runtime["scanner_runtime"]
    shadow_meta = frozen_runtime["shadow_runtime"]
    micro = _load_micro_candidates(
        micro_root,
        expected_content_sha256=str(micro_meta["content_sha256"]),
        expected_activations=activations,
    )
    shadow = _load_shadow_candidates(
        shadow_root,
        expected_content_sha256=str(shadow_meta["content_sha256"]),
        expected_source_runtime_sha256=str(scanner_meta["content_sha256"]),
        expected_activations=activations,
    )
    payload = build_discretion_heldout_comparison(
        labels=labels,
        micro_by_candidate=micro,
        shadow_by_candidate=shadow,
    )
    validate_discretion_heldout_comparison(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare frozen retrospective Ross labels with the already-frozen "
            "scanner, Micro, and discretionary-shadow artifacts without retuning."
        )
    )
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--runtime-audit", type=Path, required=True)
    parser.add_argument("--micro-root", type=Path, required=True)
    parser.add_argument("--shadow-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"output already exists: {args.output}")
    payload = build_comparison_from_frozen_artifacts(
        labels_path=args.labels,
        runtime_audit_path=args.runtime_audit,
        micro_root=args.micro_root,
        shadow_root=args.shadow_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "content_sha256": payload["content_sha256"],
                "scanner_acquisition": payload["scanner_acquisition"],
                "technical_contingency_counts": payload[
                    "technical_contingency_counts"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
