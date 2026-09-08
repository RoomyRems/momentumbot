"""Register causal account scheduling and generate synthetic evidence offline."""
import argparse
import json
import os
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
    from momentumbot.research import sealed_historical_account_scheduler_v01 as producer
    root = Path(__file__).resolve().parents[1]
    if args.validate_registration:
        result = producer.validate_registration(root)
    elif args.synthetic_vectors:
        if args.output_root is None or args.output_root.resolve().is_relative_to(root):
            raise ValueError("synthetic vectors require a new external directory")
        producer._output(root, args.output_root)
        producer.validate_registration(root)
        sys.path.insert(0, str(root))
        from tests.test_sealed_historical_account_scheduler_v01 import synthetic_vectors
        result = synthetic_vectors()
        args.output_root.mkdir(parents=True, exist_ok=False)
        raw = producer.parent.fees.encoded(result)
        with (args.output_root / "synthetic-vectors.json").open("xb") as handle:
            if handle.write(raw) != len(raw):
                raise OSError("short synthetic evidence write")
            handle.flush()
            os.fsync(handle.fileno())
        result = {"synthetic_only": True, "content_sha256": result["content_sha256"], "bytes": len(raw)}
    else:
        output = args.output_root or root / producer.OUTPUT_PATH
        result = (producer.write_bundle if args.build else producer.verify_bundle)(root, output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
