from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from momentumbot.research.databento_quote import (
    SDK_VERSION,
    build_unavailable_report,
    load_quote_contract,
    run_metadata_quote,
    validate_quote_report,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-metadata-quote-v0.1.json"
)
DEFAULT_PARENT = ROOT / "research" / "strategy" / "level2-tape-feasibility-v0.1.json"


def _render(report: dict[str, object], secret: str | None) -> str:
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if secret and secret in rendered:
        raise ValueError("Databento credential reached the sanitized report")
    return rendered + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a sanitized metadata-only Databento Level 2 quote."
    )
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--parent", type=Path, default=DEFAULT_PARENT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    contract = load_quote_contract(args.contract, parent_path=args.parent)
    generated_at = datetime.now(UTC)
    secret = os.getenv("DATABENTO_API_KEY")
    if not secret:
        report = build_unavailable_report(
            contract,
            generated_at=generated_at,
            error_stage="credential",
            error_kind="missing_DATABENTO_API_KEY",
        )
    else:
        try:
            import databento as db
        except Exception as exc:
            report = build_unavailable_report(
                contract,
                generated_at=generated_at,
                error_stage="sdk_import",
                error_kind=type(exc).__name__,
            )
        else:
            version = str(getattr(db, "__version__", "unknown"))
            if version != SDK_VERSION:
                report = build_unavailable_report(
                    contract,
                    generated_at=generated_at,
                    error_stage="sdk_version",
                    error_kind=f"expected_{SDK_VERSION}_observed_{version}",
                )
            else:
                try:
                    client = db.Historical()
                    report = run_metadata_quote(
                        contract,
                        client,
                        generated_at=generated_at,
                        sdk_version=version,
                    )
                except Exception as exc:
                    report = build_unavailable_report(
                        contract,
                        generated_at=generated_at,
                        error_stage="metadata_quote",
                        error_kind=type(exc).__name__,
                    )

    validate_quote_report(report)
    rendered = _render(report, secret)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    # The workflow uploads both passing and failing sanitized reports and then
    # enforces g0_quote_passed in a separate final step.
    return 0


if __name__ == "__main__":
    sys.exit(main())
