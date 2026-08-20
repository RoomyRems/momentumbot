#!/usr/bin/env python3
"""Build the registered July trade-management fixed-entry sensitivity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from momentumbot.research.trade_management_sensitivity import (
    build_trade_management_sensitivity,
    load_json_object,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ACCOUNT_ROOT = ROOT / "research" / "frozen" / "historical-account-diagnostic-v0.1"
DEFAULT_REGISTRATION = ROOT / "research" / "strategy" / "trade-management-shadow-v0.1.json"
DEFAULT_EVIDENCE = (
    ROOT / "research" / "data-audits" / "trade-management-evidence-v0.1-2026-08-19.json"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--micro-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--account-root", type=Path, default=DEFAULT_ACCOUNT_ROOT)
    parser.add_argument("--registration", type=Path, default=DEFAULT_REGISTRATION)
    parser.add_argument("--evidence-audit", type=Path, default=DEFAULT_EVIDENCE)
    args = parser.parse_args()

    manifest = build_trade_management_sensitivity(
        args.micro_zip,
        args.account_root,
        load_json_object(args.registration),
        load_json_object(args.evidence_audit),
    )
    args.output.mkdir(parents=True, exist_ok=True)
    output_path = args.output / "manifest.json"
    output_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest["account_fixed_entry_summary"], indent=2, sort_keys=True))
    print(f"manifest_content_sha256={manifest['content_sha256']}")


if __name__ == "__main__":
    main()
