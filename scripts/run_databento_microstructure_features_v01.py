from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from momentumbot.research.databento_feature_diagnostic_v01 import (
    RuntimeConstants,
    build_unavailable_report,
    load_diagnostic_contract,
    load_execution_authorization,
    run_feature_diagnostic,
    validate_feature_diagnostic_report,
)
from momentumbot.research.databento_quote import SDK_VERSION


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-feature-diagnostic-v0.1.json"
)
DEFAULT_AUTHORIZATION = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-feature-diagnostic-v0.1-execution.json"
)


def _render(report: dict[str, object], secret: str | None) -> str:
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if secret and secret in rendered:
        raise ValueError("Databento credential reached the sanitized report")
    if ".dbn" in rendered:
        raise ValueError("temporary DBN filename reached the sanitized report")
    return rendered + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the separately authorized four-case Databento threshold-free "
            "microstructure feature diagnostic."
        )
    )
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument(
        "--authorization",
        type=Path,
        default=DEFAULT_AUTHORIZATION,
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    contract = load_diagnostic_contract(args.contract)
    authorization = load_execution_authorization(args.authorization)
    generated_at = datetime.now(UTC)
    secret = os.getenv("DATABENTO_API_KEY")
    run_attempt = os.getenv("GITHUB_RUN_ATTEMPT", "1")
    push_before = os.getenv("MOMENTUMBOT_PUSH_BEFORE")

    if run_attempt != "1":
        report = build_unavailable_report(
            contract,
            authorization,
            generated_at=generated_at,
            sdk_version="not_loaded",
            error_stage="authorization",
            error_kind="github_actions_rerun_blocked",
        )
    elif push_before != authorization["authorized_push_parent_sha"]:
        report = build_unavailable_report(
            contract,
            authorization,
            generated_at=generated_at,
            sdk_version="not_loaded",
            error_stage="authorization",
            error_kind="unauthorized_push_parent",
        )
    elif not secret:
        report = build_unavailable_report(
            contract,
            authorization,
            generated_at=generated_at,
            sdk_version="not_loaded",
            error_stage="credential",
            error_kind="missing_DATABENTO_API_KEY",
        )
    else:
        try:
            import databento as db
        except Exception as exc:
            report = build_unavailable_report(
                contract,
                authorization,
                generated_at=generated_at,
                sdk_version="unavailable",
                error_stage="sdk_import",
                error_kind=type(exc).__name__,
            )
        else:
            version = str(getattr(db, "__version__", "unknown"))
            if version != SDK_VERSION:
                report = build_unavailable_report(
                    contract,
                    authorization,
                    generated_at=generated_at,
                    sdk_version=version,
                    error_stage="sdk_version",
                    error_kind=f"expected_{SDK_VERSION}_observed_{version}",
                )
            else:
                try:
                    runtime = RuntimeConstants(
                        f_last=int(db.RecordFlags.F_LAST),
                        f_tob=int(db.RecordFlags.F_TOB),
                        f_snapshot=int(db.RecordFlags.F_SNAPSHOT),
                        f_bad_ts_recv=int(db.RecordFlags.F_BAD_TS_RECV),
                        undef_price=int(db.UNDEF_PRICE),
                    )
                    client = db.Historical()
                except Exception as exc:
                    report = build_unavailable_report(
                        contract,
                        authorization,
                        generated_at=generated_at,
                        sdk_version=version,
                        error_stage="client_initialization",
                        error_kind=type(exc).__name__,
                    )
                else:
                    # Provider, parser, and temporary-file failures are
                    # sanitized by the gate. There is no automatic retry.
                    report = run_feature_diagnostic(
                        contract,
                        authorization,
                        client,
                        generated_at=generated_at,
                        sdk_version=version,
                        runtime=runtime,
                    )

    validate_feature_diagnostic_report(report)
    rendered = _render(report, secret)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
