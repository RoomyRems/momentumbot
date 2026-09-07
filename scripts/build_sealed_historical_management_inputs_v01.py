"""Build or verify complete historical management inputs without provider IO."""
import argparse
import json
from pathlib import Path
import sys

from run_offline_python_v13 import deny_external_io


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--validate-registration", action="store_true")
    modes.add_argument("--build", action="store_true")
    modes.add_argument("--verify", action="store_true")
    parser.add_argument("--sip-zip", type=Path)
    parser.add_argument("--bars-zip", type=Path)
    parser.add_argument("--tails-zip", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--freeze-metadata", action="store_true")
    parser.add_argument("--check-committed", action="store_true")
    args = parser.parse_args()
    sys.addaudithook(deny_external_io)
    from momentumbot.research import sealed_historical_management_inputs_v01 as m
    root = Path(__file__).resolve().parents[1]
    if args.validate_registration:
        result = m.validate_registration(root)
    else:
        if any(p is None for p in (args.sip_zip, args.bars_zip, args.tails_zip)):
            parser.error("all three exact source ZIPs are required")
        if args.freeze_metadata and not args.build:
            parser.error("only a successful new build may freeze metadata")
        output = args.output_root or root / m.BUNDLE_PATH
        paths = {"original_sip": args.sip_zip, "original_bars": args.bars_zip, "missing_tails": args.tails_zip}
        operation = m.write_bundle if args.build else m.verify_bundle
        result = operation(root, output, paths,
            progress=lambda item: print(json.dumps(item, sort_keys=True), file=sys.stderr, flush=True))
        if args.freeze_metadata:
            m.freeze_metadata(root, output)
        if args.check_committed:
            result = m.check_committed_metadata(root, output)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
