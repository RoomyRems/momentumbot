#!/usr/bin/env python3
"""Compose one frozen provider-free prospective account runtime day."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from momentumbot.research.prospective_daily_account_runtime import (
    build_daily_account_runtime,
    load_daily_runtime_contract,
    load_default_parent_contracts,
    load_parent_directories,
    write_daily_account_runtime,
)


ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Join already-frozen source, opportunity, market-input, and account "
            "artifacts into twelve label-blind account/session cells. This command "
            "makes no provider or broker call."
        )
    )
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--freeze-dir", type=Path, required=True)
    parser.add_argument("--market-input-dir", type=Path, required=True)
    parser.add_argument("--account-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-trading-date", required=True)
    parser.add_argument(
        "--runtime-frozen-at",
        default="",
        help="Aware ISO timestamp; defaults to the current UTC time.",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=(
            ROOT
            / "research"
            / "strategy"
            / "prospective-daily-account-runtime-v0.1.json"
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    contract = load_daily_runtime_contract(args.contract)
    opportunity_contract, market_contract = load_default_parent_contracts(ROOT)
    parents = load_parent_directories(
        source_dir=args.source_dir,
        freeze_dir=args.freeze_dir,
        market_input_dir=args.market_input_dir,
        account_dir=args.account_dir,
    )
    frozen_at = args.runtime_frozen_at or datetime.now(UTC).isoformat()
    runtime = build_daily_account_runtime(
        contract,
        opportunity_freeze_contract=opportunity_contract,
        market_input_contract=market_contract,
        runtime_frozen_at=frozen_at,
        **parents,
    )
    if runtime["trading_date"] != args.expected_trading_date:
        raise ValueError("runtime trading date differs from --expected-trading-date")
    output = write_daily_account_runtime(args.output_dir, runtime)
    print(
        json.dumps(
            {
                "status": "success",
                "trading_date": runtime["trading_date"],
                "candidate_symbol_count": runtime["candidate_symbol_count"],
                "opportunity_count": runtime["opportunity_count"],
                "session_count": runtime["session_count"],
                "decision_count": runtime["decision_count"],
                "runtime_content_sha256": runtime["content_sha256"],
                "output_file": output.name,
                "provider_call_made": False,
                "broker_order_submitted": False,
                "retrospective_labels_loaded": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
