from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from momentumbot.research.prospective_market_input_capture import (
    load_capture_contract,
)
from momentumbot.research.prospective_market_input_quote import (
    SDK_VERSION,
    build_quote_authorization,
    build_unavailable_report,
    build_zero_request_report,
    load_parent_bundle,
    load_quote_authorization,
    load_quote_contract,
    run_metadata_quote,
    validate_execution_context,
    validate_quote_authorization,
    validate_quote_report,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "prospective-market-input-metadata-quote-v0.1.json"
)
DEFAULT_CAPTURE_CONTRACT = (
    ROOT / "research" / "strategy" / "prospective-market-input-capture-v0.1.json"
)


def _add_parent_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument(
        "--capture-contract",
        type=Path,
        default=DEFAULT_CAPTURE_CONTRACT,
    )
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--freeze-run-id", required=True)
    parser.add_argument("--freeze-run-attempt", type=int, required=True)
    parser.add_argument("--freeze-artifact-name", required=True)


def _render(payload: dict[str, object], secret: str | None = None) -> str:
    rendered = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False)
    if secret and secret in rendered:
        raise ValueError("Databento credential reached the sanitized artifact")
    for prohibited in ('"provider_error_message":', ".dbn"):
        if prohibited in rendered:
            raise ValueError("raw provider detail reached the sanitized artifact")
    return rendered + "\n"


def _write_once(path: Path, rendered: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        output.write(rendered)


def _load_parents(args: argparse.Namespace):
    quote_contract = load_quote_contract(args.contract)
    capture_contract = load_capture_contract(args.capture_contract)
    bundle = load_parent_bundle(
        args.bundle_dir,
        quote_contract=quote_contract,
        capture_contract=capture_contract,
    )
    return quote_contract, capture_contract, bundle


def _authorize(args: argparse.Namespace) -> int:
    quote_contract, capture_contract, bundle = _load_parents(args)
    authorization = build_quote_authorization(
        quote_contract,
        capture_contract,
        bundle,
        repository=args.repository,
        freeze_run_id=args.freeze_run_id,
        freeze_run_attempt=args.freeze_run_attempt,
        freeze_artifact_name=args.freeze_artifact_name,
    )
    validate_quote_authorization(
        authorization,
        quote_contract=quote_contract,
        capture_contract=capture_contract,
        bundle=bundle,
    )
    rendered = _render(authorization)
    _write_once(args.output, rendered)
    print(rendered, end="")
    return 0


def _quote(args: argparse.Namespace) -> int:
    quote_contract, capture_contract, bundle = _load_parents(args)
    authorization = load_quote_authorization(
        args.authorization,
        quote_contract=quote_contract,
        capture_contract=capture_contract,
        bundle=bundle,
    )
    validate_execution_context(
        authorization,
        repository=args.repository,
        freeze_run_id=args.freeze_run_id,
        freeze_run_attempt=args.freeze_run_attempt,
        freeze_artifact_name=args.freeze_artifact_name,
        workflow_run_id=args.workflow_run_id,
        workflow_run_attempt=args.workflow_run_attempt,
    )
    generated_at = datetime.now(UTC)
    secret = os.getenv("DATABENTO_API_KEY")
    common = (
        quote_contract,
        capture_contract,
        bundle,
        authorization,
    )
    context = {
        "generated_at": generated_at,
        "workflow_run_id": args.workflow_run_id,
        "workflow_run_attempt": args.workflow_run_attempt,
    }
    if bundle.request_count == 0:
        report = build_zero_request_report(*common, **context)
    elif not secret:
        report = build_unavailable_report(
            *common,
            **context,
            sdk_version="not_loaded",
            error_stage="credential",
            error_kind="missing_databento_api_key",
        )
    else:
        try:
            import databento as db
        except Exception:
            report = build_unavailable_report(
                *common,
                **context,
                sdk_version="not_loaded",
                error_stage="sdk_import",
                error_kind="databento_sdk_import_failed",
            )
        else:
            version = str(getattr(db, "__version__", "unknown"))
            if version != SDK_VERSION:
                report = build_unavailable_report(
                    *common,
                    **context,
                    sdk_version=version,
                    error_stage="sdk_version",
                    error_kind="databento_sdk_version_mismatch",
                )
            else:
                try:
                    client = db.Historical()
                except Exception:
                    report = build_unavailable_report(
                        *common,
                        **context,
                        sdk_version=version,
                        error_stage="client_initialization",
                        error_kind="databento_client_initialization_failed",
                    )
                else:
                    report = run_metadata_quote(
                        *common,
                        client,
                        **context,
                        sdk_version=version,
                    )

    validate_quote_report(
        report,
        quote_contract=quote_contract,
        capture_contract=capture_contract,
        bundle=bundle,
        authorization=authorization,
    )
    rendered = _render(report, secret)
    _write_once(args.output, rendered)
    print(rendered, end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create an exact prospective metadata-quote authorization or run its "
            "sanitized metadata-only quote."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    authorize = commands.add_parser(
        "authorize",
        help="Create a provider-free authorization bound to a validated freeze.",
    )
    _add_parent_arguments(authorize)
    authorize.add_argument("--output", type=Path, required=True)

    quote = commands.add_parser(
        "quote",
        help="Run only the two authorized metadata methods and sanitize the result.",
    )
    _add_parent_arguments(quote)
    quote.add_argument("--authorization", type=Path, required=True)
    quote.add_argument("--workflow-run-id", required=True)
    quote.add_argument("--workflow-run-attempt", type=int, required=True)
    quote.add_argument("--output", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "authorize":
        return _authorize(args)
    return _quote(args)


if __name__ == "__main__":
    sys.exit(main())
