"""Offline registration only; no historical run, provider or account mode."""
from pathlib import Path
import argparse
import json
import sys

from run_offline_python_v13 import deny_external_io
sys.addaudithook(deny_external_io)

from momentumbot.research import sealed_historical_management_runner_v01 as runner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--validate-registration", action="store_true")
    modes.add_argument("--build", action="store_true")
    modes.add_argument("--verify", action="store_true")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output_root or root / runner.OUTPUT_PATH
    if args.validate_registration:
        report = runner.validate_registration(root)
    else:
        report = (runner.write_bundle if args.build else runner.verify_bundle)(root, output)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
