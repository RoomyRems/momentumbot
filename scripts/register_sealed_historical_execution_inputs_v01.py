"""Freeze or validate the exact historical Micro execution/status request plan."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from run_offline_python_v13 import deny_external_io
from momentumbot.research.sealed_historical_execution_inputs_v01 import (
    validate_registration, write_registration,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    sys.addaudithook(deny_external_io)
    operation = validate_registration if args.validate_only else write_registration
    result = operation(
        repo_root=ROOT,
        micro_root=ROOT / "research/runtime/sealed-historical-micro-v0.1",
        scanner_root=ROOT / "research/runtime/sealed-historical-scanner-activation-v0.2",
        output_root=args.output_root,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
