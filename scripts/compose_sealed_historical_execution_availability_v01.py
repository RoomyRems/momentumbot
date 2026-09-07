"""Register, compose or fully reconstruct exact historical input availability."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from run_offline_python_v13 import deny_external_io
from momentumbot.research import sealed_historical_execution_availability_v01 as availability

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-registration", action="store_true")
    mode.add_argument("--compose", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--result-zip", type=Path)
    parser.add_argument("--consumption-zip", type=Path)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    sys.addaudithook(deny_external_io)
    if args.validate_registration:
        result = availability.validate_registration(ROOT)
    else:
        if any(value is None for value in (args.result_zip, args.consumption_zip, args.output_root)):
            parser.error("both exact artifact ZIPs and output root are required")
        operation = availability.write_bundle if args.compose else availability.verify_bundle
        result = operation(ROOT, output=args.output_root,
            result_zip=args.result_zip, consumption_zip=args.consumption_zip)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
