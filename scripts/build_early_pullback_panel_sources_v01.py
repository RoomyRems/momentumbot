"""Provider-free registration only; no data acquisition or historical run mode."""
import argparse
import json
from pathlib import Path

from momentumbot.research import early_pullback_panel_sources_v01 as component


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emit", action="store_true", help="print the registration for an explicit local freeze")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.emit:
        print(json.dumps(component.registration(root), indent=2, sort_keys=True, allow_nan=False))
    else:
        saved = component.validate_registration(root)
        print(json.dumps({"status": "verified", "registration_sha256": saved["content_sha256"],
                          "file_bindings": len(saved["file_bindings"]), **component.BOUNDARY}, sort_keys=True))


if __name__ == "__main__":
    main()
