"""Verify retained management sources or reconstruct their frozen coverage."""
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
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    sys.addaudithook(deny_external_io)
    from momentumbot.research import sealed_historical_management_reuse_v01 as reuse
    root = Path(__file__).resolve().parents[1]
    if args.validate_registration:
        result = reuse.validate_registration(root)
    else:
        if args.sip_zip is None or args.bars_zip is None:
            parser.error("both exact source archives are required")
        operation = reuse.write_bundle if args.build else reuse.verify_bundle
        result = operation(root, args.output_root or root / reuse.OUTPUT_PATH,
            sip_zip=args.sip_zip, bars_zip=args.bars_zip,
            progress=lambda value: print(json.dumps(value, sort_keys=True), file=sys.stderr, flush=True))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
