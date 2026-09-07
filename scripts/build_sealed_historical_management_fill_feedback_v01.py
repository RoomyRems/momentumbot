"""Register and verify entry binding/fill feedback offline; no historical runner."""
import argparse
import json
from pathlib import Path
import sys

from run_offline_python_v13 import deny_external_io


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-registration", action="store_true")
    mode.add_argument("--build", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    sys.addaudithook(deny_external_io)
    from momentumbot.research import sealed_historical_management_fill_feedback_v01 as feedback
    root = Path(__file__).resolve().parents[1]
    if args.validate_registration:
        result = feedback.validate_registration(root)
    else:
        output = args.output_root or root / feedback.OUTPUT_PATH
        result = (feedback.write_bundle if args.build else feedback.verify_bundle)(root, output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
