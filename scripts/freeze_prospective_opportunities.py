#!/usr/bin/env python3
"""Materialize a frozen prospective opportunity and exact request handoff."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from momentumbot.research.prospective_market_input_capture import (
    load_capture_contract,
)
from momentumbot.research.prospective_opportunity_freeze import (
    build_daily_opportunity_freeze,
    load_daily_decision_source,
    load_opportunity_freeze_contract,
    write_daily_opportunity_freeze,
)


ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze an already-produced label-blind daily Micro decision source; "
            "this command makes no provider or broker call"
        )
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-trading-date")
    parser.add_argument(
        "--contract",
        type=Path,
        default=(
            ROOT / "research" / "strategy" / "prospective-opportunity-freeze-v0.1.json"
        ),
    )
    parser.add_argument(
        "--market-input-contract",
        type=Path,
        default=(
            ROOT
            / "research"
            / "strategy"
            / "prospective-market-input-capture-v0.1.json"
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    contract = load_opportunity_freeze_contract(args.contract)
    market_input_contract = load_capture_contract(args.market_input_contract)
    source = load_daily_decision_source(args.source)
    if (
        args.expected_trading_date is not None
        and source["trading_date"] != args.expected_trading_date
    ):
        raise ValueError("source trading date differs from --expected-trading-date")
    result = build_daily_opportunity_freeze(
        contract,
        market_input_contract,
        source,
    )
    write_daily_opportunity_freeze(args.output_dir, result)
    print(
        json.dumps(
            {
                "trading_date": result.freeze_manifest["trading_date"],
                "candidate_count": result.freeze_manifest["candidate_count"],
                "opportunity_count": result.freeze_manifest["opportunity_count"],
                "request_count": result.freeze_manifest["request_count"],
                "source_content_sha256": result.freeze_manifest[
                    "source_content_sha256"
                ],
                "freeze_content_sha256": result.freeze_manifest["content_sha256"],
                "provider_call_made": False,
                "broker_order_submitted": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
