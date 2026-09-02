"""RVOL-aligned scanner-input adapter for sealed recovery v0.10."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from pathlib import Path
import sys
from typing import Iterator

from momentumbot.historical_float_identity_v09 import (
    authoritative_float_identity_v09,
    build_downstream_identity_preflight_receipt,
)
from momentumbot.scanner_rvol_alignment_v10 import (
    align_exact_rvol_to_raw_bar_indexes_v10,
)

if __package__:
    from scripts import build_causal_scanner_snapshot_v04 as parent
else:
    import build_causal_scanner_snapshot_v04 as parent


@contextmanager
def canonical_scanner_rvol_alignment_v10() -> Iterator[None]:
    """Temporarily align only the serializer boundary used by the parent CLI."""

    original = parent.write_scanner_source_input_bundle

    def aligned_writer(*args: object, **kwargs: object) -> dict[str, object]:
        raw = kwargs.get("candidate_raw_minute_bars_by_symbol")
        rvol = kwargs.get("candidate_exact_rvol_by_symbol")
        if not isinstance(raw, dict) or not isinstance(rvol, dict):
            raise ValueError("v0.10 scanner writer requires candidate mappings")
        changed = dict(kwargs)
        changed["candidate_exact_rvol_by_symbol"] = (
            align_exact_rvol_to_raw_bar_indexes_v10(
                candidate_raw_minute_bars_by_symbol=raw,
                candidate_exact_rvol_by_symbol=rvol,
            )
        )
        return original(*args, **changed)

    parent.write_scanner_source_input_bundle = aligned_writer
    try:
        yield
    finally:
        parent.write_scanner_source_input_bundle = original


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if any(argument in {"-h", "--help"} for argument in arguments):
        return parent.main(arguments)
    roots = argparse.ArgumentParser(add_help=False)
    roots.add_argument("--census-root", type=Path, required=True)
    root_arguments, _ = roots.parse_known_args(arguments)
    build_downstream_identity_preflight_receipt(root_arguments.census_root)
    with authoritative_float_identity_v09(), canonical_scanner_rvol_alignment_v10():
        return parent.main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
