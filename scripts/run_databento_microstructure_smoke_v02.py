from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from momentumbot.research.databento_quote import SDK_VERSION
from momentumbot.research.databento_smoke_v02 import (
    AUTHORIZED_PUSH_PARENT_SHA,
    RuntimeConstants,
    build_unavailable_report,
    load_acquisition_contract,
    load_parent_failure_audit,
    run_smoke_acquisition,
    validate_smoke_report,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-smoke-acquisition-v0.2.json"
)
DEFAULT_PARENT_FAILURE = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-smoke-acquisition-v0.1-"
    "run-32427326070-failure-2026-08-20.json"
)


def _render(report: dict[str, object], secret: str | None) -> str:
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if secret and secret in rendered:
        raise ValueError("Databento credential reached the sanitized report")
    if ".dbn.zst" in rendered:
        raise ValueError("temporary DBN filename reached the sanitized report")
    return rendered + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the bounded Databento MBO reset-repair smoke gate."
    )
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument(
        "--parent-failure",
        type=Path,
        default=DEFAULT_PARENT_FAILURE,
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    parent_failure = load_parent_failure_audit(args.parent_failure)
    contract = load_acquisition_contract(
        args.contract,
        parent_failure_audit=parent_failure,
    )
    generated_at = datetime.now(UTC)
    secret = os.getenv("DATABENTO_API_KEY")
    run_attempt = os.getenv("GITHUB_RUN_ATTEMPT", "1")
    push_before = os.getenv("MOMENTUMBOT_PUSH_BEFORE")

    if run_attempt != "1":
        report = build_unavailable_report(
            contract,
            parent_failure_audit=parent_failure,
            generated_at=generated_at,
            sdk_version="not_loaded",
            error_stage="authorization",
            error_kind="github_actions_rerun_blocked",
        )
    elif push_before != AUTHORIZED_PUSH_PARENT_SHA:
        report = build_unavailable_report(
            contract,
            parent_failure_audit=parent_failure,
            generated_at=generated_at,
            sdk_version="not_loaded",
            error_stage="authorization",
            error_kind="unauthorized_push_parent",
        )
    elif not secret:
        report = build_unavailable_report(
            contract,
            parent_failure_audit=parent_failure,
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
                parent_failure_audit=parent_failure,
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
                    parent_failure_audit=parent_failure,
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
                        parent_failure_audit=parent_failure,
                        generated_at=generated_at,
                        sdk_version=version,
                        error_stage="client_initialization",
                        error_kind=type(exc).__name__,
                    )
                else:
                    # Provider, file, and parser failures are sanitized inside
                    # the gate. Unexpected programming or cleanup failures must
                    # abort instead of producing a false clean diagnostic.
                    report = run_smoke_acquisition(
                        contract,
                        client,
                        parent_failure_audit=parent_failure,
                        generated_at=generated_at,
                        sdk_version=version,
                        runtime=runtime,
                    )

    validate_smoke_report(report)
    rendered = _render(report, secret)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
