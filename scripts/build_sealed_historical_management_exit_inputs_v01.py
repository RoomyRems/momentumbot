"""Compose or verify immutable historical exit sources without provider IO."""
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
    for key in ("exit-result", "exit-consumption", "entry-result", "entry-consumption"):
        parser.add_argument("--" + key + "-zip", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--freeze-metadata", action="store_true")
    parser.add_argument("--check-committed", action="store_true")
    args = parser.parse_args()
    sys.addaudithook(deny_external_io)
    from momentumbot.research import sealed_historical_management_exit_inputs_v01 as m
    root = Path(__file__).resolve().parents[1]
    if args.validate_registration:
        result = m.validate_registration(root)
    else:
        paths = {k: getattr(args, k + "_zip") for k in ("exit_result", "exit_consumption", "entry_result", "entry_consumption")}
        if any(p is None for p in paths.values()):
            parser.error("all four exact source ZIPs are required")
        if args.freeze_metadata and not args.build:
            parser.error("only a successful new build may freeze metadata")
        output = args.output_root or root / m.BUNDLE_PATH
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
