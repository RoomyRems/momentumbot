#!/usr/bin/env python3
"""Build the registered retrospective historical account diagnostic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from momentumbot.research.historical_account_diagnostic import (
    build_historical_account_diagnostic,
    load_historical_diagnostic_contract,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRATION = (
    ROOT / "research" / "strategy" / "historical-account-diagnostic-v0.1.json"
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-zip", type=Path, required=True)
    parser.add_argument("--micro-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--registration",
        type=Path,
        default=DEFAULT_REGISTRATION,
    )
    args = parser.parse_args()

    registration = load_historical_diagnostic_contract(args.registration)
    build = build_historical_account_diagnostic(
        args.source_zip,
        args.micro_zip,
        registration,
    )
    _write_json(args.output / "manifest.json", build.manifest)
    for relative_path, payload in sorted(build.session_artifacts.items()):
        _write_json(args.output / relative_path, payload)

    print(json.dumps(build.manifest["account_summaries"], indent=2, sort_keys=True))
    print(f"manifest_content_sha256={build.manifest['content_sha256']}")


if __name__ == "__main__":
    main()
