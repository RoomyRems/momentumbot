"""Identity-compatible child adapter for sealed float recovery v0.6."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from momentumbot import historical_float_v04 as float_parent
from momentumbot.historical_float_identity_v06 import (
    build_identity_preflight_receipt,
    candidate_identity_v06,
)

if __package__:
    from scripts import build_causal_float_enrichment_v05 as parent
else:
    import build_causal_float_enrichment_v05 as parent


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if any(argument in {"-h", "--help"} for argument in arguments):
        return parent.main(arguments)
    parent_arguments = arguments
    roots = argparse.ArgumentParser(add_help=False)
    roots.add_argument("--census-root", type=Path, required=True)
    root_arguments, _ = roots.parse_known_args(parent_arguments)
    market_root = root_arguments.census_root / "causal-market-discovery-v0.3"
    build_identity_preflight_receipt(market_root)

    original_identity = float_parent._candidate_identity
    float_parent._candidate_identity = candidate_identity_v06
    try:
        return parent.main(parent_arguments)
    finally:
        float_parent._candidate_identity = original_identity


if __name__ == "__main__":
    raise SystemExit(main())
