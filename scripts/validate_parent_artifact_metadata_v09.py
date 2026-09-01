"""Validate one retained-parent artifact metadata response provider-free."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from momentumbot.research.sealed_historical_source_artifact_metadata_v09 import (  # noqa: E402
    load_and_validate_parent_artifact_metadata_v09,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise ValueError("artifact metadata receipt output is not a regular file")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _sanitized_failure(error: Exception) -> str:
    message = str(error)
    allowed = {
        "artifact metadata field id changed",
        "artifact metadata field name changed",
        "artifact metadata field digest changed",
        "artifact metadata field size_in_bytes changed",
        "artifact metadata field expired changed",
        "artifact metadata field workflow_run changed",
        "artifact metadata field workflow_run.id changed",
    }
    if message in allowed:
        return message
    return "artifact metadata document is malformed or unavailable"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-json", required=True, type=Path)
    parser.add_argument("--receipt-output", required=True, type=Path)
    args = parser.parse_args()

    try:
        receipt = load_and_validate_parent_artifact_metadata_v09(args.metadata_json)
        _write_json(args.receipt_output, receipt)
    except (OSError, UnicodeError, ValueError) as error:
        print(
            f"artifact metadata validation failed: {_sanitized_failure(error)}",
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "artifact_id": receipt["artifact"]["id"],  # type: ignore[index]
                "content_sha256": receipt["content_sha256"],
                "status": "validated",
                "validator_id": receipt["validator_id"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
