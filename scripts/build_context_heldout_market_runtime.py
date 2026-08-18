from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo

from momentumbot.causal_market_discovery import load_market_candidate_payload
from momentumbot.causal_scanner_snapshot import (
    build_scanner_snapshot_rows,
    load_causal_scanner_snapshot,
)
from momentumbot.historical_float import load_causal_float_records
from momentumbot.historical_news import load_publication_timed_news
from momentumbot.identity_resolved_universe import (
    json_fingerprint,
    load_identity_resolved_universe,
)
from momentumbot.models import current_general_2026
from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.research.context_heldout_panel import (
    REGISTERED_DATES,
    canonical_fingerprint,
    load_context_heldout_panel_contract,
)
from momentumbot.research.context_runtime import (
    MARKET_RUNTIME_ARTIFACT_ID,
    load_context_runtime_request,
    validate_market_runtime_manifest,
    write_json,
)
from momentumbot.scanner_source_inputs import load_scanner_source_input_bundle


ET = ZoneInfo("America/New_York")
_LOWER_HEX = frozenset("0123456789abcdef")


def _root_content_sha256(path: Path, *, dates: list[str]) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("dates") != dates:
        raise RuntimeError(f"runtime root manifest is invalid: {path}")
    value = payload.get("content_sha256")
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _LOWER_HEX for character in value)
    ):
        raise RuntimeError(f"runtime root manifest lacks content hash: {path}")
    return value


def provider_pipeline_commands(root: Path) -> list[list[str]]:
    dates = list(REGISTERED_DATES)
    joined_dates = [value for value in dates]
    return [
        [
            sys.executable,
            "scripts/build_massive_historical_census.py",
            "--dates",
            *joined_dates,
            "--minimum-request-interval",
            "12.5",
            "--limit",
            "1000",
            "--output",
            str(root),
        ],
        [
            sys.executable,
            "scripts/audit_massive_instrument_metadata.py",
            "--census-root",
            str(root),
        ],
        [
            sys.executable,
            "scripts/audit_massive_alpaca_market_coverage.py",
            "--census-root",
            str(root),
            "--batch-size",
            "250",
        ],
        [
            sys.executable,
            "scripts/build_massive_provisional_universe.py",
            "--census-root",
            str(root),
        ],
        [
            sys.executable,
            "scripts/audit_historical_identity_continuity.py",
            "--census-root",
            str(root),
            "--dates",
            dates[0],
            dates[-1],
            "--lookback-days",
            "120",
            "--batch-size",
            "200",
            "--minimum-massive-request-interval",
            "12.5",
            "--ticker-event-sample-size",
            "10",
        ],
        [
            sys.executable,
            "scripts/build_identity_resolved_universe.py",
            "--census-root",
            str(root),
        ],
        [
            sys.executable,
            "scripts/build_identity_resolved_market_discovery.py",
            "--census-root",
            str(root),
            "--dates",
            *joined_dates,
            "--asset-batch-size",
            "250",
        ],
        [
            sys.executable,
            "scripts/build_causal_float_enrichment.py",
            "--census-root",
            str(root),
            "--dates",
            *joined_dates,
            "--minimum-sec-request-interval",
            "0.2",
            "--sec-attempts",
            "3",
        ],
        [
            sys.executable,
            "scripts/build_causal_news_enrichment.py",
            "--census-root",
            str(root),
            "--dates",
            *joined_dates,
            "--news-batch-size",
            "50",
        ],
        [
            sys.executable,
            "scripts/build_causal_scanner_snapshot.py",
            "--census-root",
            str(root),
            "--dates",
            *joined_dates,
            "--asset-batch-size",
            "250",
            "--persist-source-inputs",
        ],
    ]


def verify_registered_sessions(client: AlpacaDataClient) -> dict[str, object]:
    sessions = []
    for value in REGISTERED_DATES:
        target = date.fromisoformat(value)
        frame = client.bars(
            ["SPY"],
            timeframe="1Day",
            start=datetime.combine(
                target - timedelta(days=1),
                time(0),
                timezone.utc,
            ),
            end=datetime.combine(
                target + timedelta(days=2),
                time(0),
                timezone.utc,
            ),
            feed="sip",
            adjustment="raw",
            asof=target,
        ).get("SPY")
        observed = (
            set(frame.index.tz_convert(ET).date)
            if frame is not None and not frame.empty
            else set()
        )
        if target not in observed:
            raise RuntimeError(f"provider calendar lacks session {value}")
        sessions.append(
            {
                "trading_date": value,
                "provider": "alpaca_sip_SPY_1Day",
                "asof": value,
                "session_observed": True,
            }
        )
    contract = load_context_heldout_panel_contract(
        "research/strategy/context-heldout-panel-v0.1.json"
    )
    request = load_context_runtime_request(
        "research/data-audits/context-heldout-runtime-request-v0.1.json"
    )
    contract_hash = canonical_fingerprint(contract)
    if contract_hash != request["frozen_contracts"][
        "context_panel_content_sha256"
    ]:
        raise RuntimeError("context panel differs from the registered request")
    return {
        "schema_version": 1,
        "contract_id": contract["contract_id"],
        "contract_content_sha256": canonical_fingerprint(contract),
        "dates": list(REGISTERED_DATES),
        "sessions": sessions,
        "uses_ross_labels": False,
        "uses_trade_outcomes": False,
    }


def freeze_market_runtime_manifest(
    root: Path,
    *,
    calendar: Mapping[str, object],
    workflow_run_id: int,
    workflow_run_attempt: int,
    workflow_job: str,
    head_sha: str,
) -> dict[str, object]:
    dates = list(REGISTERED_DATES)
    contract = load_context_heldout_panel_contract(
        "research/strategy/context-heldout-panel-v0.1.json"
    )
    sessions = calendar.get("sessions")
    if (
        calendar.get("dates") != dates
        or not isinstance(sessions, list)
        or len(sessions) != len(dates)
        or not all(
            isinstance(row, Mapping) and row.get("session_observed") is True
            for row in sessions
        )
    ):
        raise RuntimeError("context runtime session calendar is invalid")
    write_json(root / "session-calendar-verification.json", calendar)

    identity_root = root / "identity-resolved-universe-v0.1"
    market_root = root / "causal-market-discovery-v0.2"
    float_root = root / "causal-sec-float-v0.1"
    news_root = root / "causal-alpaca-news-v0.2"
    scanner_root = root / "causal-scanner-snapshot-v0.1"
    source_root = root / "causal-scanner-source-inputs-v0.1"
    roots = {
        "identity": _root_content_sha256(
            identity_root / "manifest.json", dates=dates
        ),
        "market": _root_content_sha256(
            market_root / "manifest.json", dates=dates
        ),
        "float": _root_content_sha256(
            float_root / "manifest.json", dates=dates
        ),
        "news": _root_content_sha256(
            news_root / "manifest.json", dates=dates
        ),
        "scanner": _root_content_sha256(
            scanner_root / "manifest.json", dates=dates
        ),
        "scanner_source_inputs": _root_content_sha256(
            source_root / "manifest.json", dates=dates
        ),
    }
    profile = current_general_2026()
    date_results: dict[str, object] = {}
    for value in dates:
        members, _, _ = load_identity_resolved_universe(
            identity_root,
            trading_date=value,
        )
        candidates, candidate_payload, _ = load_market_candidate_payload(
            market_root / value
        )
        floats, float_manifest = load_causal_float_records(
            float_root / value,
            candidate_rows=candidates,
            candidate_payload=candidate_payload,
        )
        events, statuses, _ = load_publication_timed_news(
            news_root / value,
            candidate_rows=candidates,
            candidate_payload=candidate_payload,
            source_float_records_sha256=float_manifest["summary"][
                "records_sha256"
            ],
        )
        source_inputs, source_manifest = load_scanner_source_input_bundle(
            source_root / value,
            profile=profile,
        )
        if list(source_inputs.membership_symbols) != sorted(
            str(row["ticker"]) for row in members
        ):
            raise RuntimeError(f"scanner membership sidecar mismatch for {value}")
        if list(source_inputs.candidate_symbols) != sorted(
            str(row["symbol"]) for row in candidates
        ):
            raise RuntimeError(f"scanner candidate sidecar mismatch for {value}")
        rows, payload, _ = load_causal_scanner_snapshot(
            scanner_root / value,
            candidate_rows=candidates,
            profile=profile,
            expected_source_hashes=source_inputs.source_hashes,
        )
        if candidates and not rows:
            raise RuntimeError(
                f"market candidates produced no scanner decision rows for {value}"
            )
        replayed = build_scanner_snapshot_rows(
            trading_date=source_inputs.trading_date,
            profile=profile,
            candidate_rows=candidates,
            float_records=floats,
            news_events=events,
            news_statuses=statuses,
            membership_symbols=source_inputs.membership_symbols,
            previous_close_by_symbol=source_inputs.previous_close_by_symbol,
            rank_raw_minute_bars_by_symbol=(
                source_inputs.rank_raw_minute_bars_by_symbol
            ),
            candidate_raw_minute_bars_by_symbol=(
                source_inputs.candidate_raw_minute_bars_by_symbol
            ),
            candidate_exact_rvol_by_symbol=(
                source_inputs.candidate_exact_rvol_by_symbol
            ),
        )
        if replayed != rows:
            raise RuntimeError(f"provider-independent scanner replay changed {value}")
        date_results[value] = {
            "identity_member_count": len(members),
            "market_candidate_count": len(candidates),
            "scanner_row_count": len(rows),
            "scanner_records_content_sha256": payload["content_sha256"],
            "scanner_source_inputs_content_sha256": source_manifest[
                "content_sha256"
            ],
        }
    manifest: dict[str, object] = {
        "schema_version": 1,
        "artifact_id": MARKET_RUNTIME_ARTIFACT_ID,
        "dates": dates,
        "registration": {
            "contract_id": contract["contract_id"],
            "contract_content_sha256": contract_hash,
            "request_id": request["request_id"],
            "request_content_sha256": request["content_sha256"],
            "label_content_review_started": False,
            "source_inventory_started": False,
            "session_calendar_content_sha256": json_fingerprint(calendar),
        },
        "workflow": {
            "run_id": workflow_run_id,
            "run_attempt": workflow_run_attempt,
            "job": workflow_job,
            "head_sha": head_sha,
        },
        "runtime_root_content_sha256s": roots,
        "date_results": date_results,
        "causal_boundary": {
            "uses_benchmark_labels": False,
            "uses_ross_actions": False,
            "uses_retrospective_trade_outcomes": False,
            "uses_later_price_outcomes": False,
            "all_market_candidates_retained": True,
            "top_n_selection_applied": False,
            "provider_independent_scanner_replay_validated": True,
        },
        "eligibility": {
            "runtime_inputs_frozen": True,
            "human_label_review_may_start_after_all_context_artifacts_freeze": True,
            "universe_complete": False,
            "representative_panel": False,
            "full_walk_forward_eligible": False,
            "policy_promotion_eligible": False,
            "full_imitation_claim_eligible": False,
        },
        "limits": [
            "ten-session context pilot only",
            "historical provider records may later mutate",
            "universe complete only relative to the provider reconstruction",
            "no human trade or skip label is present",
        ],
    }
    manifest["content_sha256"] = json_fingerprint(manifest)
    validate_market_runtime_manifest(manifest)
    write_json(root / "context-market-runtime-manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the registered context panel's label-blind market runtime."
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workflow-run-id", type=int, required=True)
    parser.add_argument("--workflow-run-attempt", type=int, required=True)
    parser.add_argument("--workflow-job", required=True)
    parser.add_argument("--head-sha", required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"output already exists: {args.output}")
    client = AlpacaDataClient.from_env()
    calendar = verify_registered_sessions(client)
    for command in provider_pipeline_commands(args.output):
        subprocess.run(command, check=True)
    freeze_market_runtime_manifest(
        args.output,
        calendar=calendar,
        workflow_run_id=args.workflow_run_id,
        workflow_run_attempt=args.workflow_run_attempt,
        workflow_job=args.workflow_job,
        head_sha=args.head_sha,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
