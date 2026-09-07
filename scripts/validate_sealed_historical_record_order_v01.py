#!/usr/bin/env python3
"""Validate the offline adapter and exact diagnostic fixture; no provider path."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from momentumbot.research.sealed_historical_record_order_registration_v01 import verify_diagnostic_adapter


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify_diagnostic_adapter(args.repo_root)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as handle:
            handle.write(encoded)
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
