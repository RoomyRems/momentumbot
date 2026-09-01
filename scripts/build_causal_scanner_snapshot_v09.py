"""Identity-compatible scanner-input adapter for sealed recovery v0.9."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from momentumbot.historical_float_identity_v09 import (
    authoritative_float_identity_v09,
    build_downstream_identity_preflight_receipt,
)

if __package__:
    from scripts import build_causal_scanner_snapshot_v04 as parent
else:
    import build_causal_scanner_snapshot_v04 as parent


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if any(argument in {"-h", "--help"} for argument in arguments):
        return parent.main(arguments)
    roots = argparse.ArgumentParser(add_help=False)
    roots.add_argument("--census-root", type=Path, required=True)
    root_arguments, _ = roots.parse_known_args(arguments)
    build_downstream_identity_preflight_receipt(root_arguments.census_root)
    with authoritative_float_identity_v09():
        return parent.main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
