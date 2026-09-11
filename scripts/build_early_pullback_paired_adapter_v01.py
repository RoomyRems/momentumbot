"""Read-only registration builder/checker; no provider or historical run mode."""
import argparse
import json
from pathlib import Path
from momentumbot.research import early_pullback_paired_adapter_v01 as adapter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--emit", action="store_true")
    args = parser.parse_args()
    if args.emit:
        print(json.dumps({adapter.CONTRACT_PATH: adapter.registration(args.root),
            f"{adapter.BASE}/data-plan.json": adapter.build_data_plan(adapter.selection.validate_registration(args.root))},
            sort_keys=True, allow_nan=False))
    else:
        value = adapter.validate_registration(args.root)
        print(json.dumps({"status": "verified", "registration_sha256": value["content_sha256"],
                          **adapter.BOUNDARY}, sort_keys=True))


if __name__ == "__main__":
    main()
