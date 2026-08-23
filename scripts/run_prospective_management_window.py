#!/usr/bin/env python3
"""Capture or project the preregistered prospective management window."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.research.prospective_management_window import (
    CAPTURE_FILE,
    PROJECTION_FILE,
    build_management_projection,
    build_management_request_manifest,
    capture_management_window_from_alpaca,
    load_json_object,
    load_management_window_contract,
    validate_management_capture,
    validate_management_projection,
    write_management_artifact,
    write_management_capture_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "prospective-management-window-capture-v0.1.json"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest = subparsers.add_parser("manifest")
    manifest.add_argument("--opportunity-manifest", type=Path, required=True)
    manifest.add_argument("--output-dir", type=Path, required=True)

    capture = subparsers.add_parser("capture")
    capture.add_argument("--opportunity-manifest", type=Path, required=True)
    capture.add_argument("--expected-trading-date", required=True)
    capture.add_argument("--output-dir", type=Path, required=True)

    project = subparsers.add_parser("project")
    project.add_argument("--daily-runtime", type=Path, required=True)
    project.add_argument("--management-capture", type=Path, required=True)
    project.add_argument("--expected-trading-date", required=True)
    project.add_argument("--output-dir", type=Path, required=True)
    return parser


def _write_manifest(output_dir: Path, payload: dict[str, object]) -> Path:
    return write_management_artifact(
        output_dir,
        payload,
        filename="management-window-request-manifest.json",
    )


def main() -> None:
    args = _parser().parse_args()
    contract = load_management_window_contract(args.contract)
    if args.command == "manifest":
        opportunity = load_json_object(
            args.opportunity_manifest, "opportunity manifest"
        )
        manifest = build_management_request_manifest(contract, opportunity)
        path = _write_manifest(args.output_dir, manifest)
        print(
            json.dumps(
                {
                    "output": str(path),
                    "trading_date": manifest["trading_date"],
                    "opportunity_count": manifest["opportunity_count"],
                    "request_count": manifest["request_count"],
                    "provider_call_made": False,
                },
                sort_keys=True,
            )
        )
        return

    if args.command == "capture":
        opportunity = load_json_object(
            args.opportunity_manifest, "opportunity manifest"
        )
        expected_artifact = f"prospective-opportunities-{args.expected_trading_date}"
        if opportunity.get("artifact_id") != expected_artifact:
            raise ValueError("opportunity manifest differs from the expected date")
        client = AlpacaDataClient.from_env()
        manifest, capture = capture_management_window_from_alpaca(
            contract,
            opportunity,
            client=client,
        )
        paths = write_management_capture_bundle(args.output_dir, manifest, capture)
        print(
            json.dumps(
                {
                    "outputs": [str(path) for path in paths],
                    "trading_date": capture["trading_date"],
                    "opportunity_count": capture["opportunity_count"],
                    "request_count": capture["request_count"],
                    "provider_call_made": capture["provider_call_made"],
                    "broker_order_submitted": False,
                },
                sort_keys=True,
            )
        )
        return

    daily_runtime = load_json_object(args.daily_runtime, "daily runtime")
    capture = load_json_object(args.management_capture, "management capture")
    validate_management_capture(capture)
    if daily_runtime.get("trading_date") != args.expected_trading_date:
        raise ValueError("daily runtime differs from the expected date")
    if capture.get("trading_date") != args.expected_trading_date:
        raise ValueError("management capture differs from the expected date")
    projection = build_management_projection(
        contract,
        daily_runtime,
        capture,
        projection_frozen_at=datetime.now(UTC),
    )
    validate_management_projection(projection)
    path = write_management_artifact(
        args.output_dir,
        projection,
        filename=PROJECTION_FILE,
    )
    print(
        json.dumps(
            {
                "output": str(path),
                "trading_date": projection["trading_date"],
                "cell_count": projection["cell_count"],
                "decision_count": projection["decision_count"],
                "portfolio_financial_metrics_eligible": False,
                "broker_order_submitted": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
