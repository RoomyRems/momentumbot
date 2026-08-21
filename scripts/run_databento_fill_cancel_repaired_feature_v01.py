from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from momentumbot.research.databento_fill_cancel_repair_v01 import (
    load_parent_success_audit,
    load_repair_contract,
)
from momentumbot.research.databento_fill_cancel_repaired_feature_v01 import (
    RuntimeConstants,
    build_unavailable_report,
    load_diagnostic_contract,
    load_execution_authorization,
    run_repaired_feature_diagnostic,
    validate_repaired_feature_report,
)
from momentumbot.research.databento_quote import SDK_VERSION


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-fill-cancel-repaired-feature-v0.1.json"
)
DEFAULT_PARENT_SUCCESS = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-fill-cancel-classifier-v0.1-"
    "run-32512602607-success-2026-08-21.json"
)
DEFAULT_REPAIR_CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-fill-cancel-repair-v0.1.json"
)
DEFAULT_AUTHORIZATION = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-fill-cancel-repaired-feature-v0.1-execution.json"
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
            "Run a separately authorized one-shot EQPT feature replay under "
            "the published Fill/Cancel identity repair."
        )
    )
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument(
        "--parent-success",
        type=Path,
        default=DEFAULT_PARENT_SUCCESS,
    )
    parser.add_argument(
        "--repair-contract",
        type=Path,
        default=DEFAULT_REPAIR_CONTRACT,
    )
    parser.add_argument(
        "--authorization",
        type=Path,
        default=DEFAULT_AUTHORIZATION,
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    # The authorization file is intentionally absent from the unarmed bundle.
    # Validate it before importing the provider SDK or constructing a client.
    if not args.authorization.is_file():
        raise ValueError("repaired feature execution authorization file is required")
    parent_success = load_parent_success_audit(args.parent_success)
    repair_contract = load_repair_contract(
        args.repair_contract,
        parent_success_audit=parent_success,
    )
    contract = load_diagnostic_contract(
        args.contract,
        parent_success_audit=parent_success,
        repair_contract=repair_contract,
    )
    authorization = load_execution_authorization(args.authorization)
    generated_at = datetime.now(UTC)
    run_attempt = os.getenv("GITHUB_RUN_ATTEMPT")
    push_before = os.getenv("MOMENTUMBOT_PUSH_BEFORE")
    secret = os.getenv("DATABENTO_API_KEY")

    if run_attempt != "1":
        report = build_unavailable_report(
            contract,
            parent_success,
            repair_contract,
            authorization,
            generated_at=generated_at,
            sdk_version="not_loaded",
            failure_phase="authorization",
            safe_error_code="github_actions_rerun_blocked",
        )
    elif push_before != authorization["authorized_push_parent_sha"]:
        report = build_unavailable_report(
            contract,
            parent_success,
            repair_contract,
            authorization,
            generated_at=generated_at,
            sdk_version="not_loaded",
            failure_phase="authorization",
            safe_error_code="unauthorized_push_parent",
        )
    elif not secret:
        report = build_unavailable_report(
            contract,
            parent_success,
            repair_contract,
            authorization,
            generated_at=generated_at,
            sdk_version="not_loaded",
            failure_phase="credential",
            safe_error_code="missing_databento_api_key",
        )
    else:
        try:
            import databento as db
        except Exception:
            report = build_unavailable_report(
                contract,
                parent_success,
                repair_contract,
                authorization,
                generated_at=generated_at,
                sdk_version="unavailable",
                failure_phase="sdk",
                safe_error_code="sdk_import_failed",
            )
        else:
            version = str(getattr(db, "__version__", "unknown"))
            if version != SDK_VERSION:
                report = build_unavailable_report(
                    contract,
                    parent_success,
                    repair_contract,
                    authorization,
                    generated_at=generated_at,
                    sdk_version=version,
                    failure_phase="sdk",
                    safe_error_code="sdk_version_mismatch",
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
                except Exception:
                    report = build_unavailable_report(
                        contract,
                        parent_success,
                        repair_contract,
                        authorization,
                        generated_at=generated_at,
                        sdk_version=version,
                        failure_phase="sdk",
                        safe_error_code="client_initialization_failed",
                    )
                else:
                    report = run_repaired_feature_diagnostic(
                        contract,
                        parent_success,
                        repair_contract,
                        authorization,
                        client,
                        generated_at=generated_at,
                        sdk_version=version,
                        runtime=runtime,
                    )

    validate_repaired_feature_report(report)
    rendered = _render(report, secret)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
