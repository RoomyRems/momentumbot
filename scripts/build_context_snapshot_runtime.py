from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping

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
    CONTRACT_ID as CATALYST_CONTRACT_ID,
    build_catalyst_evidence_packets,
    load_catalyst_evidence_contract,
)
from momentumbot.research.context_assessment import (
    CONTRACT_ID as CONTEXT_CONTRACT_ID,
    build_context_decision_snapshot,
    canonical_fingerprint as context_fingerprint,
    load_context_assessment_contract,
)
from momentumbot.research.context_heldout_panel import REGISTERED_DATES
from momentumbot.research.context_runtime import (
    DAILY_RUNTIME_ARTIFACT_ID,
    SNAPSHOT_RUNTIME_ARTIFACT_ID,
    THEME_RUNTIME_ARTIFACT_ID,
    build_record_date_payload,
    build_record_root_manifest,
    load_context_runtime_request,
    load_market_runtime_manifest,
    validate_record_date_payload,
    write_json,
)
from momentumbot.research.daily_chart_context import (
    CONTRACT_ID as DAILY_CONTRACT_ID,
    daily_chart_supplemental_evidence,
    validate_daily_chart_evidence,
)
from momentumbot.research.theme_regime_context import (
    CONTRACT_ID as THEME_CONTRACT_ID,
    build_completed_theme_regime_session_summary,
    build_theme_regime_evidence,
    canonical_fingerprint as theme_fingerprint,
    load_theme_regime_context_contract,
    theme_regime_supplemental_evidence,
)
from momentumbot.scanner_source_inputs import load_scanner_source_input_bundle


PRIOR_RUNTIME_ARTIFACT_ID = "ross-discretion-heldout-runtime-v0.1"
PRIOR_RUNTIME_CONTENT_SHA256 = (
    "2414f7389bf68d5a5e4b3302c646c9111020cb79ce06fc0213f7872062f79c48"
)
PRIOR_SUMMARY_DATES = (
    "2026-07-17",
    "2026-07-20",
    "2026-07-21",
    "2026-07-22",
    "2026-07-23",
)
ATTENTION_RUNTIME_ARTIFACT_ID = "ross-context-heldout-attention-runtime-v0.1"
CATALYST_RUNTIME_ARTIFACT_ID = "ross-context-heldout-catalyst-runtime-v0.1"


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def resolve_prior_runtime_root(root: Path) -> Path:
    """Resolve the two layouts emitted by GitHub artifact downloads.

    A named artifact normally extracts directly into ``root``. Older/manual
    extractions may retain the artifact-name directory. In either case the
    exact frozen manifest is still validated immediately after resolution.
    """

    candidates = (
        root,
        root / "discretion-heldout-runtime-v0.1",
    )
    matches = [
        candidate
        for candidate in candidates
        if (candidate / "heldout-runtime-manifest.json").is_file()
    ]
    if len(matches) != 1:
        raise ValueError(
            "prior held-out runtime root is missing or ambiguous; "
            f"found {len(matches)} frozen-manifest candidates"
        )
    return matches[0]


def _validate_prior_runtime(root: Path) -> dict[str, object]:
    payload = _read_json(root / "heldout-runtime-manifest.json")
    if payload.get("artifact_id") != PRIOR_RUNTIME_ARTIFACT_ID:
        raise ValueError("unexpected prior held-out runtime artifact")
    claimed = payload.get("content_sha256")
    projection = {
        key: value for key, value in payload.items() if key != "content_sha256"
    }
    if claimed != json_fingerprint(projection):
        raise ValueError("prior held-out runtime fingerprint mismatch")
    if claimed != PRIOR_RUNTIME_CONTENT_SHA256:
        raise ValueError("prior held-out runtime differs from the frozen artifact")
    causal = payload.get("causal_boundary")
    if not isinstance(causal, Mapping):
        raise ValueError("prior held-out runtime lacks causal boundary")
    if causal.get("uses_ross_actions") is not False:
        raise ValueError("prior held-out runtime contains Ross actions")
    if causal.get("uses_later_price_outcomes") is not False:
        raise ValueError("prior held-out runtime contains later outcomes")
    return payload


def _load_runtime_date(
    root: Path,
    value: str,
) -> tuple[list[dict[str, object]], dict[str, object], list[dict[str, object]], str]:
    profile = current_general_2026()
    market_root = root / "causal-market-discovery-v0.2"
    float_root = root / "causal-sec-float-v0.1"
    news_root = root / "causal-alpaca-news-v0.2"
    scanner_root = root / "causal-scanner-snapshot-v0.1"
    scanner_inputs_root = root / "causal-scanner-source-inputs-v0.1"
    candidates, candidate_payload, _ = load_market_candidate_payload(
        market_root / value
    )
    _, float_manifest = load_causal_float_records(
        float_root / value,
        candidate_rows=candidates,
        candidate_payload=candidate_payload,
    )
    news_events, _, _ = load_publication_timed_news(
        news_root / value,
        candidate_rows=candidates,
        candidate_payload=candidate_payload,
        source_float_records_sha256=str(
            float_manifest["summary"]["records_sha256"]
        ),
    )
    source_inputs, _ = load_scanner_source_input_bundle(
        scanner_inputs_root / value,
        profile=profile,
    )
    scanner_rows, scanner_payload, _ = load_causal_scanner_snapshot(
        scanner_root / value,
        candidate_rows=candidates,
        profile=profile,
        expected_source_hashes=source_inputs.source_hashes,
    )
    return (
        scanner_rows,
        scanner_payload,
        news_events,
        news_events_fingerprint(news_events),
    )


def _load_daily_runtime(
    root: Path,
    *,
    market_runtime_content_sha256: str,
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    manifest = _read_json(root / "manifest.json")
    if manifest.get("artifact_id") != DAILY_RUNTIME_ARTIFACT_ID:
        raise ValueError("unexpected daily-chart runtime artifact")
    if manifest.get("contract_id") != DAILY_CONTRACT_ID:
        raise ValueError("daily-chart runtime contract mismatch")
    if manifest.get("dates") != list(REGISTERED_DATES):
        raise ValueError("daily-chart runtime dates differ from registration")
    if manifest.get("source_market_runtime_content_sha256") != (
        market_runtime_content_sha256
    ):
        raise ValueError("daily-chart runtime market lineage mismatch")
    projection = {
        key: value for key, value in manifest.items() if key != "content_sha256"
    }
    if manifest.get("content_sha256") != json_fingerprint(projection):
        raise ValueError("daily-chart runtime root fingerprint mismatch")
    payloads: dict[str, dict[str, object]] = {}
    for value in REGISTERED_DATES:
        payload = _read_json(root / "dates" / f"{value}.json")
        validate_record_date_payload(
            payload,
            artifact_id=DAILY_RUNTIME_ARTIFACT_ID,
            contract_id=DAILY_CONTRACT_ID,
        )
        if payload.get("content_sha256") != manifest[
            "date_content_sha256s"
        ][value]:
            raise ValueError("daily-chart date/root fingerprint mismatch")
        for record in payload["records"]:
            validate_daily_chart_evidence(record)
        payloads[value] = payload
    return manifest, payloads


def _contract_hashes() -> dict[str, str]:
    attention = load_attention_leadership_contract(
        "research/strategy/attention-leadership-shadow-v0.1.json"
    )
    catalyst = load_catalyst_evidence_contract(
        "research/strategy/catalyst-evidence-packet-shadow-v0.1.json"
    )
    theme = load_theme_regime_context_contract(
        "research/strategy/theme-regime-context-shadow-v0.1.json"
    )
    context = load_context_assessment_contract(
        "research/strategy/discretion-context-assessment-shadow-v0.1.json"
    )
    return {
        ATTENTION_CONTRACT_ID: json_fingerprint(attention),
        CATALYST_CONTRACT_ID: json_fingerprint(catalyst),
        THEME_CONTRACT_ID: theme_fingerprint(theme),
        CONTEXT_CONTRACT_ID: context_fingerprint(context),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Freeze deterministic theme and context snapshots label-blind."
    )
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--daily-runtime-root", type=Path, required=True)
    parser.add_argument("--prior-runtime-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"output already exists: {args.output}")
    args.output.mkdir(parents=True)
    market_manifest = load_market_runtime_manifest(args.runtime_root)
    request = load_context_runtime_request(
        "research/data-audits/context-heldout-runtime-request-v0.1.json"
    )
    if market_manifest["registration"]["request_content_sha256"] != request[
        "content_sha256"
    ]:
        raise RuntimeError("market runtime uses a different registered request")
    prior_runtime_root = resolve_prior_runtime_root(args.prior_runtime_root)
    prior_manifest = _validate_prior_runtime(prior_runtime_root)
    daily_manifest, daily_payloads = _load_daily_runtime(
        args.daily_runtime_root,
        market_runtime_content_sha256=str(market_manifest["content_sha256"]),
    )
    contract_hashes = _contract_hashes()
    if contract_hashes[THEME_CONTRACT_ID] != request["frozen_contracts"][
        "theme_regime_content_sha256"
    ]:
        raise RuntimeError("theme/regime contract differs from the registered request")
    if contract_hashes[CONTEXT_CONTRACT_ID] != request["frozen_contracts"][
        "context_assessment_content_sha256"
    ]:
        raise RuntimeError("context contract differs from the registered request")
    if daily_manifest["contract_content_sha256"] != request["frozen_contracts"][
        "daily_chart_content_sha256"
    ]:
        raise RuntimeError("daily runtime differs from the registered request")

    completed_summaries: list[dict[str, object]] = []
    for value in PRIOR_SUMMARY_DATES:
        scanner_rows, scanner_payload, _, _ = _load_runtime_date(
            prior_runtime_root,
            value,
        )
        completed_summaries.append(
            build_completed_theme_regime_session_summary(
                scanner_rows,
                trading_date=value,
                source_scanner_records_content_sha256=str(
                    scanner_payload["content_sha256"]
                ),
            )
        )

    attention_payloads: dict[str, dict[str, object]] = {}
    catalyst_payloads: dict[str, dict[str, object]] = {}
    theme_payloads: dict[str, dict[str, object]] = {}
    date_inputs: dict[str, dict[str, object]] = {}
    for value in REGISTERED_DATES:
        scanner_rows, scanner_payload, news_events, news_hash = _load_runtime_date(
            args.runtime_root,
            value,
        )
        if not scanner_rows:
            raise ValueError(f"registered context date has no scanner rows: {value}")
        attention_rows = derive_attention_leadership_rows(scanner_rows)
        packets = build_catalyst_evidence_packets(
            scanner_rows,
            {"full_window_event_tape": news_events},
        )
        prior_summaries = completed_summaries[-5:]
        theme_rows = [
            build_theme_regime_evidence(
                scanner_rows,
                news_events,
                prior_summaries,
                symbol=str(packet["symbol"]),
                decision_time=str(packet["decision_time"]),
                source_artifact_content_sha256s={
                    "scanner_records": str(scanner_payload["content_sha256"]),
                    "publication_timed_news_events": news_hash,
                    "prior_session_summaries": theme_fingerprint(prior_summaries),
                },
            )
            for packet in packets
        ]
        common_source = {
            "market_runtime": str(market_manifest["content_sha256"]),
            "scanner_records": str(scanner_payload["content_sha256"]),
            "publication_timed_news_events": news_hash,
        }
        attention_payload = build_record_date_payload(
            artifact_id=ATTENTION_RUNTIME_ARTIFACT_ID,
            contract_id=ATTENTION_CONTRACT_ID,
            trading_date=value,
            source_hashes=common_source,
            records=attention_rows,
            unavailable=[],
        )
        catalyst_payload = build_record_date_payload(
            artifact_id=CATALYST_RUNTIME_ARTIFACT_ID,
            contract_id=CATALYST_CONTRACT_ID,
            trading_date=value,
            source_hashes=common_source,
            records=packets,
            unavailable=[],
        )
        theme_payload = build_record_date_payload(
            artifact_id=THEME_RUNTIME_ARTIFACT_ID,
            contract_id=THEME_CONTRACT_ID,
            trading_date=value,
            source_hashes={
                **common_source,
                "prior_session_summaries": theme_fingerprint(prior_summaries),
            },
            records=theme_rows,
            unavailable=[],
        )
        attention_payloads[value] = attention_payload
        catalyst_payloads[value] = catalyst_payload
        theme_payloads[value] = theme_payload
        date_inputs[value] = {
            "scanner_rows": scanner_rows,
            "scanner_payload": scanner_payload,
            "packets": packets,
        }
        completed_summaries.append(
            build_completed_theme_regime_session_summary(
                scanner_rows,
                trading_date=value,
                source_scanner_records_content_sha256=str(
                    scanner_payload["content_sha256"]
                ),
            )
        )

    roots = {
        ATTENTION_RUNTIME_ARTIFACT_ID: build_record_root_manifest(
            artifact_id=ATTENTION_RUNTIME_ARTIFACT_ID,
            contract_id=ATTENTION_CONTRACT_ID,
            contract_content_sha256=contract_hashes[ATTENTION_CONTRACT_ID],
            source_market_runtime_content_sha256=str(
                market_manifest["content_sha256"]
            ),
            date_payloads=attention_payloads,
        ),
        CATALYST_RUNTIME_ARTIFACT_ID: build_record_root_manifest(
            artifact_id=CATALYST_RUNTIME_ARTIFACT_ID,
            contract_id=CATALYST_CONTRACT_ID,
            contract_content_sha256=contract_hashes[CATALYST_CONTRACT_ID],
            source_market_runtime_content_sha256=str(
                market_manifest["content_sha256"]
            ),
            date_payloads=catalyst_payloads,
        ),
        THEME_RUNTIME_ARTIFACT_ID: build_record_root_manifest(
            artifact_id=THEME_RUNTIME_ARTIFACT_ID,
            contract_id=THEME_CONTRACT_ID,
            contract_content_sha256=contract_hashes[THEME_CONTRACT_ID],
            source_market_runtime_content_sha256=str(
                market_manifest["content_sha256"]
            ),
            date_payloads=theme_payloads,
        ),
    }
    for artifact_id, payloads in (
        (ATTENTION_RUNTIME_ARTIFACT_ID, attention_payloads),
        (CATALYST_RUNTIME_ARTIFACT_ID, catalyst_payloads),
        (THEME_RUNTIME_ARTIFACT_ID, theme_payloads),
    ):
        root = args.output / artifact_id
        for value, payload in payloads.items():
            write_json(root / "dates" / f"{value}.json", payload)
        write_json(root / "manifest.json", roots[artifact_id])

    snapshot_payloads: dict[str, dict[str, object]] = {}
    for value in REGISTERED_DATES:
        inputs = date_inputs[value]
        scanner_rows = inputs["scanner_rows"]
        packets = inputs["packets"]
        scanner_payload = inputs["scanner_payload"]
        attention_by_key = {
            (str(row["symbol"]), str(row["decision_time"])): row
            for row in attention_payloads[value]["records"]
        }
        scanner_by_key = {
            (str(row["symbol"]), str(row["decision_time"])): row
            for row in scanner_rows
        }
        daily_by_key = {
            (str(row["symbol"]), str(row["decision_time"])): row
            for row in daily_payloads[value]["records"]
        }
        theme_by_key = {
            (str(row["symbol"]), str(row["decision_time"])): row
            for row in theme_payloads[value]["records"]
        }
        snapshots = []
        for packet in packets:
            key = (str(packet["symbol"]), str(packet["decision_time"]))
            supplemental = [
                theme_regime_supplemental_evidence(
                    theme_by_key[key],
                    source_artifact_content_sha256=str(
                        roots[THEME_RUNTIME_ARTIFACT_ID]["content_sha256"]
                    ),
                )
            ]
            if key in daily_by_key:
                supplemental.insert(
                    0,
                    daily_chart_supplemental_evidence(
                        daily_by_key[key],
                        source_artifact_content_sha256=str(
                            daily_manifest["content_sha256"]
                        ),
                    ),
                )
            snapshots.append(
                build_context_decision_snapshot(
                    scanner_by_key[key],
                    attention_by_key[key],
                    catalyst_packet=packet,
                    source_artifact_content_sha256s={
                        "scanner_runtime": str(scanner_payload["content_sha256"]),
                        "attention_runtime": str(
                            attention_payloads[value]["content_sha256"]
                        ),
                        "catalyst_evidence_runtime": str(
                            catalyst_payloads[value]["content_sha256"]
                        ),
                    },
                    snapshot_reason=(
                        "candidate_activation"
                        if packet["packet_reason"] == "candidate_activation"
                        else "source_evidence_changed"
                    ),
                    supplemental_evidence=supplemental,
                )
            )
        payload = build_record_date_payload(
            artifact_id=SNAPSHOT_RUNTIME_ARTIFACT_ID,
            contract_id=CONTEXT_CONTRACT_ID,
            trading_date=value,
            source_hashes={
                "market_runtime": str(market_manifest["content_sha256"]),
                "daily_runtime": str(daily_manifest["content_sha256"]),
                "theme_runtime": str(
                    roots[THEME_RUNTIME_ARTIFACT_ID]["content_sha256"]
                ),
                "attention_runtime": str(
                    roots[ATTENTION_RUNTIME_ARTIFACT_ID]["content_sha256"]
                ),
                "catalyst_runtime": str(
                    roots[CATALYST_RUNTIME_ARTIFACT_ID]["content_sha256"]
                ),
            },
            records=snapshots,
            unavailable=[],
        )
        snapshot_payloads[value] = payload
    snapshot_root = build_record_root_manifest(
        artifact_id=SNAPSHOT_RUNTIME_ARTIFACT_ID,
        contract_id=CONTEXT_CONTRACT_ID,
        contract_content_sha256=contract_hashes[CONTEXT_CONTRACT_ID],
        source_market_runtime_content_sha256=str(market_manifest["content_sha256"]),
        date_payloads=snapshot_payloads,
    )
    snapshot_root_path = args.output / SNAPSHOT_RUNTIME_ARTIFACT_ID
    for value, payload in snapshot_payloads.items():
        write_json(snapshot_root_path / "dates" / f"{value}.json", payload)
    write_json(snapshot_root_path / "manifest.json", snapshot_root)

    master: dict[str, object] = {
        "schema_version": 1,
        "artifact_id": "ross-context-heldout-deterministic-runtime-v0.1",
        "dates": list(REGISTERED_DATES),
        "source_market_runtime_content_sha256": market_manifest["content_sha256"],
        "source_daily_runtime_content_sha256": daily_manifest["content_sha256"],
        "source_prior_runtime_content_sha256": prior_manifest["content_sha256"],
        "child_runtime_content_sha256s": {
            ATTENTION_RUNTIME_ARTIFACT_ID: roots[ATTENTION_RUNTIME_ARTIFACT_ID][
                "content_sha256"
            ],
            CATALYST_RUNTIME_ARTIFACT_ID: roots[CATALYST_RUNTIME_ARTIFACT_ID][
                "content_sha256"
            ],
            THEME_RUNTIME_ARTIFACT_ID: roots[THEME_RUNTIME_ARTIFACT_ID][
                "content_sha256"
            ],
            SNAPSHOT_RUNTIME_ARTIFACT_ID: snapshot_root["content_sha256"],
        },
        "knowledge_policy": {
            "uses_raw_transcripts": False,
            "uses_ross_actions": False,
            "uses_retrospective_labels": False,
            "uses_later_price_outcomes": False,
            "semantic_assessments_included": False,
            "runtime_strategy_effect": "none",
        },
        "policy_promotion_eligible": False,
    }
    master["content_sha256"] = json_fingerprint(master)
    write_json(args.output / "manifest.json", master)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
