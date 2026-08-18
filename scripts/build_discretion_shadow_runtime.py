from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, Mapping

from momentumbot.causal_market_discovery import load_market_candidate_payload
from momentumbot.causal_scanner_snapshot import load_causal_scanner_snapshot
from momentumbot.historical_float import load_causal_float_records
from momentumbot.historical_news import (
    load_publication_timed_news,
    news_events_fingerprint,
)
from momentumbot.identity_resolved_universe import json_fingerprint
from momentumbot.models import current_general_2026
from momentumbot.research.attention_leadership import (
    CONTRACT_ID as ATTENTION_CONTRACT_ID,
    derive_attention_leadership_rows,
    load_attention_leadership_contract,
)
from momentumbot.research.catalyst_evidence import (
    CONTRACT_ID as EVIDENCE_CONTRACT_ID,
    build_catalyst_evidence_packets,
    load_catalyst_evidence_contract,
)
from momentumbot.research.catalyst_timing import (
    CONTRACT_ID as TIMING_CONTRACT_ID,
    derive_catalyst_timing_rows,
    load_catalyst_timing_contract,
)
from momentumbot.research.discretion_heldout_panel import REGISTERED_DATES
from momentumbot.scanner_source_inputs import load_scanner_source_input_bundle


ARTIFACT_ID = "ross-discretion-shadow-runtime-v0.1"
SOURCE_ARTIFACT_ID = "ross-discretion-heldout-runtime-v0.1"


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _validate_source_runtime(payload: Mapping[str, object]) -> list[str]:
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported held-out runtime schema")
    if payload.get("artifact_id") != SOURCE_ARTIFACT_ID:
        raise ValueError("unexpected held-out runtime artifact")
    claimed = payload.get("content_sha256")
    projection = {
        key: value for key, value in payload.items() if key != "content_sha256"
    }
    if claimed != json_fingerprint(projection):
        raise ValueError("held-out runtime manifest fingerprint mismatch")
    dates = payload.get("dates")
    if dates != list(REGISTERED_DATES):
        raise ValueError("held-out runtime dates differ from registration")
    causal = payload.get("causal_boundary")
    if not isinstance(causal, Mapping):
        raise ValueError("held-out runtime lacks causal boundary")
    for field in (
        "uses_benchmark_labels",
        "uses_ross_actions",
        "uses_retrospective_trade_outcomes",
        "uses_later_price_outcomes",
        "top_n_selection_applied",
    ):
        if causal.get(field) is not False:
            raise ValueError(f"held-out runtime violates {field}")
    if causal.get("all_market_candidates_retained") is not True:
        raise ValueError("held-out runtime did not retain all market candidates")
    if causal.get("provider_independent_scanner_replay_validated") is not True:
        raise ValueError("held-out scanner replay was not independently validated")
    registration = payload.get("registration")
    if not isinstance(registration, Mapping):
        raise ValueError("held-out runtime lacks registration provenance")
    if registration.get("label_content_review_started") is not False:
        raise ValueError("human labels were opened before shadow runtime")
    eligibility = payload.get("eligibility")
    if not isinstance(eligibility, Mapping):
        raise ValueError("held-out runtime lacks eligibility metadata")
    if eligibility.get("runtime_inputs_frozen") is not True:
        raise ValueError("held-out runtime inputs are not frozen")
    if eligibility.get("policy_promotion_eligible") is not False:
        raise ValueError("held-out runtime overclaims promotion eligibility")
    return list(dates)


def _freeze_rows(
    *,
    artifact_id: str,
    contract_id: str,
    trading_date: str,
    rows: Iterable[Mapping[str, object]],
    source_hashes: Mapping[str, str],
) -> dict[str, object]:
    materialized = [dict(row) for row in rows]
    payload: dict[str, object] = {
        "schema_version": 1,
        "artifact_id": artifact_id,
        "contract_id": contract_id,
        "trading_date": trading_date,
        "source_hashes": dict(sorted(source_hashes.items())),
        "knowledge_policy": {
            "uses_ross_actions": False,
            "uses_benchmark_labels": False,
            "uses_retrospective_trade_outcomes": False,
            "uses_later_price_outcomes": False,
            "runtime_strategy_effect": "none",
        },
        "row_count": len(materialized),
        "rows": materialized,
        "policy_promotion_eligible": False,
    }
    payload["content_sha256"] = json_fingerprint(payload)
    return payload


def _validate_frozen_rows(payload: Mapping[str, object]) -> None:
    claimed = payload.get("content_sha256")
    projection = {key: value for key, value in payload.items() if key != "content_sha256"}
    if claimed != json_fingerprint(projection):
        raise ValueError("shadow runtime payload fingerprint mismatch")
    rows = payload.get("rows")
    if not isinstance(rows, list) or payload.get("row_count") != len(rows):
        raise ValueError("shadow runtime row count mismatch")
    knowledge = payload.get("knowledge_policy")
    if not isinstance(knowledge, Mapping):
        raise ValueError("shadow runtime knowledge policy is missing")
    if knowledge.get("runtime_strategy_effect") != "none":
        raise ValueError("shadow runtime cannot alter strategy behavior")
    if any(
        knowledge.get(field) is not False
        for field in (
            "uses_ross_actions",
            "uses_benchmark_labels",
            "uses_retrospective_trade_outcomes",
            "uses_later_price_outcomes",
        )
    ):
        raise ValueError("shadow runtime contains retrospective knowledge")
    if payload.get("policy_promotion_eligible") is not False:
        raise ValueError("shadow runtime cannot promote a policy")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Derive threshold-free attention, provider-news chronology, and causal "
            "headline evidence packets from a frozen unlabeled held-out runtime."
        )
    )
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_root = args.runtime_root
    source_manifest = _read_json(source_root / "heldout-runtime-manifest.json")
    dates = _validate_source_runtime(source_manifest)
    if args.output.exists():
        raise FileExistsError(f"output already exists: {args.output}")
    args.output.mkdir(parents=True)

    attention_contract = load_attention_leadership_contract(
        "research/strategy/attention-leadership-shadow-v0.1.json"
    )
    timing_contract = load_catalyst_timing_contract(
        "research/strategy/catalyst-timing-shadow-v0.1.json"
    )
    evidence_contract = load_catalyst_evidence_contract(
        "research/strategy/catalyst-evidence-packet-shadow-v0.1.json"
    )
    contract_hashes = {
        ATTENTION_CONTRACT_ID: json_fingerprint(attention_contract),
        TIMING_CONTRACT_ID: json_fingerprint(timing_contract),
        EVIDENCE_CONTRACT_ID: json_fingerprint(evidence_contract),
    }

    market_root = source_root / "causal-market-discovery-v0.2"
    float_root = source_root / "causal-sec-float-v0.1"
    news_root = source_root / "causal-alpaca-news-v0.2"
    scanner_root = source_root / "causal-scanner-snapshot-v0.1"
    scanner_inputs_root = source_root / "causal-scanner-source-inputs-v0.1"
    profile = current_general_2026()
    date_results: dict[str, object] = {}

    for value in dates:
        candidate_rows, candidate_payload, _ = load_market_candidate_payload(
            market_root / value
        )
        _, float_manifest = load_causal_float_records(
            float_root / value,
            candidate_rows=candidate_rows,
            candidate_payload=candidate_payload,
        )
        news_events, _, news_manifest = load_publication_timed_news(
            news_root / value,
            candidate_rows=candidate_rows,
            candidate_payload=candidate_payload,
            source_float_records_sha256=str(
                float_manifest["summary"]["records_sha256"]
            ),
        )
        source_inputs, source_input_manifest = load_scanner_source_input_bundle(
            scanner_inputs_root / value,
            profile=profile,
        )
        scanner_rows, scanner_payload, scanner_manifest = (
            load_causal_scanner_snapshot(
                scanner_root / value,
                candidate_rows=candidate_rows,
                profile=profile,
                expected_source_hashes=source_inputs.source_hashes,
            )
        )
        if scanner_manifest.get("trading_date") != value:
            raise ValueError("scanner date manifest mismatch")

        source_hashes = {
            "heldout_runtime": str(source_manifest["content_sha256"]),
            "market_candidates": str(candidate_payload["content_sha256"]),
            "scanner_records": str(scanner_payload["content_sha256"]),
            "scanner_manifest": json_fingerprint(scanner_manifest),
            "scanner_source_inputs": str(source_input_manifest["content_sha256"]),
            "publication_timed_news_events": news_events_fingerprint(news_events),
            "publication_timed_news_manifest": json_fingerprint(news_manifest),
        }
        if scanner_rows:
            attention_rows = derive_attention_leadership_rows(scanner_rows)
            timing_rows = derive_catalyst_timing_rows(scanner_rows)
            evidence_rows = build_catalyst_evidence_packets(
                scanner_rows,
                {"full_window_event_tape": news_events},
            )
        elif candidate_rows:
            raise ValueError(
                f"market candidates for {value} produced no scanner decision rows"
            )
        else:
            attention_rows = []
            timing_rows = []
            evidence_rows = []

        attention = _freeze_rows(
            artifact_id="attention-leadership-heldout-shadow-v0.1",
            contract_id=ATTENTION_CONTRACT_ID,
            trading_date=value,
            rows=attention_rows,
            source_hashes=source_hashes,
        )
        timing = _freeze_rows(
            artifact_id="catalyst-timing-heldout-shadow-v0.1",
            contract_id=TIMING_CONTRACT_ID,
            trading_date=value,
            rows=timing_rows,
            source_hashes=source_hashes,
        )
        evidence = _freeze_rows(
            artifact_id="catalyst-evidence-heldout-shadow-v0.1",
            contract_id=EVIDENCE_CONTRACT_ID,
            trading_date=value,
            rows=evidence_rows,
            source_hashes=source_hashes,
        )
        for payload in (attention, timing, evidence):
            _validate_frozen_rows(payload)

        date_root = args.output / value
        _write_json(date_root / "attention-leadership.json", attention)
        _write_json(date_root / "catalyst-timing.json", timing)
        _write_json(date_root / "catalyst-evidence-packets.json", evidence)
        date_results[value] = {
            "market_candidate_count": len(candidate_rows),
            "scanner_row_count": len(scanner_rows),
            "attention_row_count": attention["row_count"],
            "catalyst_timing_row_count": timing["row_count"],
            "catalyst_evidence_packet_count": evidence["row_count"],
            "attention_content_sha256": attention["content_sha256"],
            "catalyst_timing_content_sha256": timing["content_sha256"],
            "catalyst_evidence_content_sha256": evidence["content_sha256"],
        }

    root_manifest: dict[str, object] = {
        "schema_version": 1,
        "artifact_id": ARTIFACT_ID,
        "dates": dates,
        "source_heldout_runtime_content_sha256": source_manifest["content_sha256"],
        "contract_content_sha256s": dict(sorted(contract_hashes.items())),
        "date_results": date_results,
        "knowledge_policy": {
            "uses_ross_actions": False,
            "uses_benchmark_labels": False,
            "uses_retrospective_trade_outcomes": False,
            "uses_later_price_outcomes": False,
            "future_news_exposed": False,
            "runtime_strategy_effect": "none",
        },
        "eligibility": {
            "all_market_candidates_retained": True,
            "selection_threshold_frozen": False,
            "catalyst_quality_score_frozen": False,
            "policy_promotion_eligible": False,
            "full_imitation_claim_eligible": False,
        },
    }
    root_manifest["content_sha256"] = json_fingerprint(root_manifest)
    _write_json(args.output / "manifest.json", root_manifest)
    print(
        json.dumps(
            {
                "artifact_id": ARTIFACT_ID,
                "dates": dates,
                "content_sha256": root_manifest["content_sha256"],
                "date_results": date_results,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
