"""Offline census registration only; no provider capture or credential mode."""
import argparse
import json
from pathlib import Path
import sys

from run_offline_python_v13 import deny_external_io


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    sys.addaudithook(deny_external_io)
    from momentumbot.research import early_pullback_census_v01 as m
    root = Path(__file__).resolve().parents[1]
    if args.freeze:
        m.parent.parent.write_once(root / m.CONTRACT_PATH, m.registration(root))
    contract = m.validate_registration(root)
    print(json.dumps({"registration_sha256": contract["content_sha256"], "bound_files": len(contract["file_bindings"]), **m.BOUNDARY}, sort_keys=True))


if __name__ == "__main__":
    main()
