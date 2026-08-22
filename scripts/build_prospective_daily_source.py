from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path

from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.providers.sec_edgar import SecEdgarClient
from momentumbot.research.prospective_daily_source import (
    capture_pre_session_from_providers,
    load_pre_session_prerequisites,
    produce_daily_source_from_providers,
    write_daily_artifacts,
    write_pre_session_prerequisites,
)


def _context(args: argparse.Namespace) -> dict[str, str]:
    return {
        key: str(value)
        for key, value in {
            "workflow_run_id": args.workflow_run_id,
            "workflow_run_attempt": args.workflow_run_attempt,
            "workflow_event_name": args.workflow_event_name,
            "workflow_source_sha": args.workflow_source_sha,
        }.items()
        if value is not None and str(value)
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture or produce one registered prospective scanner/Micro source."
    )
    parser.add_argument(
        "mode", choices=("capture-prerequisites", "produce")
    )
    parser.add_argument("--trading-date", required=True)
    parser.add_argument("--runtime-head-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prerequisite", type=Path)
    parser.add_argument("--asset-batch-size", type=int, default=250)
    parser.add_argument("--news-batch-size", type=int, default=50)
    parser.add_argument("--minimum-sec-request-interval", type=float, default=0.2)
    parser.add_argument("--workflow-run-id")
    parser.add_argument("--workflow-run-attempt")
    parser.add_argument("--workflow-event-name")
    parser.add_argument("--workflow-source-sha")
    args = parser.parse_args(argv)

    alpaca = AlpacaDataClient.from_env()
    sec = SecEdgarClient.from_env()
    if args.mode == "capture-prerequisites":
        if args.prerequisite is not None:
            raise ValueError("capture mode cannot accept a prerequisite artifact")
        payload = capture_pre_session_from_providers(
            trading_date=args.trading_date,
            alpaca=alpaca,
            sec=sec,
            runtime_head_sha=args.runtime_head_sha,
            workflow_context=_context(args),
        )
        write_pre_session_prerequisites(args.output, payload)
        summary = {
            "mode": args.mode,
            "trading_date": args.trading_date,
            "asset_count": payload["asset_count"],
            "sec_ticker_count": payload["sec_ticker_count"],
            "content_sha256": payload["content_sha256"],
        }
    else:
        if args.prerequisite is None:
            raise ValueError("produce mode requires --prerequisite")
        prerequisite = load_pre_session_prerequisites(args.prerequisite)
        if prerequisite["trading_date"] != args.trading_date:
            raise ValueError("prerequisite trading date differs from the requested date")
        if prerequisite["runtime_head_sha"] != args.runtime_head_sha:
            raise ValueError("producer checkout differs from the pre-session runtime head")
        artifacts = produce_daily_source_from_providers(
            prerequisite=prerequisite,
            alpaca=alpaca,
            sec=sec,
            asset_batch_size=args.asset_batch_size,
            news_batch_size=args.news_batch_size,
            minimum_sec_request_interval=args.minimum_sec_request_interval,
        )
        write_daily_artifacts(args.output, artifacts)
        summary = {
            "mode": args.mode,
            "trading_date": args.trading_date,
            "profile_activation_count": artifacts.producer_manifest[
                "profile_activation_count"
            ],
            "decision_count": artifacts.producer_manifest["decision_count"],
            "source_content_sha256": artifacts.decision_source[
                "content_sha256"
            ],
            "completed_at": datetime.now(UTC).isoformat(),
        }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
