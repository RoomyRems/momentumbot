"""Build fee/reconciliation metadata or synthetic accounting vectors offline."""
import argparse
import json
from pathlib import Path
import sys

from run_offline_python_v13 import deny_external_io


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-registration", action="store_true")
    mode.add_argument("--build", action="store_true")
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--synthetic-vectors", action="store_true")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    sys.addaudithook(deny_external_io)
    from momentumbot.research import sealed_historical_management_fee_reconciliation_v01 as fees
    root = Path(__file__).resolve().parents[1]
    if args.validate_registration:
        result = fees.validate_registration(root)
    elif args.synthetic_vectors:
        if args.output_root is None or args.output_root.resolve().is_relative_to(root):
            raise ValueError("synthetic vectors require a new external output directory")
        fees._output(root, args.output_root)
        fees.validate_registration(root)
        # Direct script execution starts sys.path at scripts/, not the repo.
        # Only this explicitly synthetic mode imports the pinned test fixtures.
        sys.path.insert(0, str(root))
        from tests.test_sealed_historical_management_fee_reconciliation_v01 import synthetic_vectors
        vectors = synthetic_vectors()
        args.output_root.mkdir(parents=True, exist_ok=False)
        with (args.output_root / "synthetic-vectors.json").open("xb") as handle:
            raw = fees.encoded(vectors)
            if handle.write(raw) != len(raw):
                raise OSError("short synthetic vector write")
            handle.flush()
            fees.os.fsync(handle.fileno())
        result = {"synthetic_only": True, "content_sha256": vectors["content_sha256"],
                  "path": str(args.output_root / "synthetic-vectors.json")}
    else:
        output = args.output_root or root / fees.OUTPUT_PATH
        result = (fees.write_bundle if args.build else fees.verify_bundle)(root, output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
