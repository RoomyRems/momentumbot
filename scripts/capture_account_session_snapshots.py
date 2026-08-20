from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from momentumbot.research.account_snapshot_capture import (
    ACCOUNT_CLASSES,
    PAPER_ENDPOINT,
    AlpacaPaperAccountClient,
    capture_dual_account_bundle,
    credentials_from_env,
    validate_bundle,
    write_bundle,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate or capture the two registered Alpaca paper accounts "
            "without storing credentials or raw provider account IDs."
        )
    )
    parser.add_argument("--mode", choices=("validate", "capture"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--session-date",
        default="",
        help="Optional YYYY-MM-DD guard; capture still derives and checks New York time.",
    )
    parser.add_argument(
        "--workflow-run-id", default=os.getenv("GITHUB_RUN_ID", "local")
    )
    parser.add_argument(
        "--workflow-run-attempt", default=os.getenv("GITHUB_RUN_ATTEMPT", "1")
    )
    parser.add_argument(
        "--workflow-event-name", default=os.getenv("GITHUB_EVENT_NAME", "local")
    )
    parser.add_argument("--head-sha", default=os.getenv("GITHUB_SHA", ""))
    parser.add_argument("--workflow-source-sha", default=os.getenv("GITHUB_SHA", ""))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        requested_date = (
            date.fromisoformat(args.session_date.strip())
            if args.session_date.strip()
            else None
        )
        if args.output.exists() and any(args.output.iterdir()):
            raise ValueError("output directory must be absent or empty")
        endpoint = os.getenv("ALPACA_PAPER_ENDPOINT", PAPER_ENDPOINT)
        clients = {
            account_class: AlpacaPaperAccountClient(
                credentials_from_env(account_class), endpoint=endpoint
            )
            for account_class in ACCOUNT_CLASSES
        }
        manifest, snapshots = capture_dual_account_bundle(
            clients,
            mode=args.mode,
            requested_session_date=requested_date,
            run_context={
                "workflow_run_id": args.workflow_run_id,
                "workflow_run_attempt": args.workflow_run_attempt,
                "workflow_event_name": args.workflow_event_name,
                "head_sha": args.head_sha,
                "workflow_source_sha": args.workflow_source_sha,
            },
        )
        validate_bundle(manifest, snapshots)
        written = write_bundle(args.output, manifest, snapshots)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        # Deliberately suppress chained provider exceptions and response bodies.
        print(f"account snapshot capture failed: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "status": "success",
                "mode": manifest["mode"],
                "session_date": manifest["session_date"],
                "account_classes": manifest["account_classes"],
                "manifest_content_sha256": manifest["content_sha256"],
                "written_files": [path.name for path in written],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
