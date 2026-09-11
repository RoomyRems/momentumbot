"""Provider-free account-context registration; no historical or capture mode."""
import argparse
import json
from pathlib import Path

from momentumbot.research import early_pullback_panel_accounts_v01 as component


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emit", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    value = component.registration(root) if args.emit else component.validate_registration(root)
    print(json.dumps(value if args.emit else {"status": "verified", "registration_sha256": value["content_sha256"],
        "file_bindings": len(value["file_bindings"]), **component.BOUNDARY}, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
