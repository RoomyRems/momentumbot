from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from momentumbot.research.prospective_market_input_acquisition import (
    SDK_VERSION,
    build_acquisition_authorization,
    build_unavailable_report,
    build_zero_request_result,
    load_acquisition_authorization,
    load_acquisition_contract,
    run_exact_acquisition,
    validate_acquisition_report,
    validate_execution_context,
    validate_quote_chain,
)
from momentumbot.research.prospective_market_input_capture import (
    load_capture_contract,
)
from momentumbot.research.prospective_market_input_quote import (
    load_parent_bundle,
    load_quote_authorization,
    load_quote_contract,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ACQUISITION_CONTRACT = (
    ROOT / "research" / "strategy" / "prospective-market-input-acquisition-v0.1.json"
)
DEFAULT_QUOTE_CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "prospective-market-input-metadata-quote-v0.1.json"
)
DEFAULT_CAPTURE_CONTRACT = (
    ROOT / "research" / "strategy" / "prospective-market-input-capture-v0.1.json"
)


def _read_object(path: Path, field: str) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{field} root must be an object")
    return payload


def _render(payload: dict[str, object], secret: str | None = None) -> str:
    rendered = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False)
    if secret and secret in rendered:
        raise ValueError("Databento credential reached a sanitized artifact")
    for prohibited in (
        '"provider_error_message":',
        '"exception_message":',
        '"raw_records":',
        ".dbn",
    ):
        if prohibited in rendered:
            raise ValueError("raw provider detail reached a sanitized artifact")
    return rendered + "\n"


def _write_once(path: Path, rendered: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        output.write(rendered)


def _add_chain_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--acquisition-contract",
        type=Path,
        default=DEFAULT_ACQUISITION_CONTRACT,
    )
    parser.add_argument(
        "--quote-contract",
        type=Path,
        default=DEFAULT_QUOTE_CONTRACT,
    )
    parser.add_argument(
        "--capture-contract",
        type=Path,
        default=DEFAULT_CAPTURE_CONTRACT,
    )
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--quote-authorization", type=Path, required=True)
    parser.add_argument("--quote-report", type=Path, required=True)


def _load_chain(args: argparse.Namespace):
    acquisition_contract = load_acquisition_contract(args.acquisition_contract)
    quote_contract = load_quote_contract(args.quote_contract)
    capture_contract = load_capture_contract(args.capture_contract)
    bundle = load_parent_bundle(
        args.bundle_dir,
        quote_contract=quote_contract,
        capture_contract=capture_contract,
    )
    quote_authorization = load_quote_authorization(
        args.quote_authorization,
        quote_contract=quote_contract,
        capture_contract=capture_contract,
        bundle=bundle,
    )
    quote_report = _read_object(args.quote_report, "metadata quote report")
    chain = validate_quote_chain(
        acquisition_contract,
        quote_contract,
        capture_contract,
        bundle,
        quote_authorization,
        quote_report,
    )
    return (
        acquisition_contract,
        quote_contract,
        capture_contract,
        chain.bundle,
        quote_authorization,
        quote_report,
    )


def _authorize(args: argparse.Namespace) -> int:
    chain = _load_chain(args)
    authorization = build_acquisition_authorization(
        *chain,
        repository=args.repository,
        quote_artifact_name=args.quote_artifact_name,
    )
    rendered = _render(authorization)
    _write_once(args.output, rendered)
    print(rendered, end="")
    return 0


def _acquire(args: argparse.Namespace) -> int:
    chain = _load_chain(args)
    authorization = load_acquisition_authorization(
        args.authorization,
        acquisition_contract=chain[0],
        quote_contract=chain[1],
        capture_contract=chain[2],
        bundle=chain[3],
        quote_authorization=chain[4],
        quote_report=chain[5],
    )
    validate_execution_context(
        authorization,
        repository=args.repository,
        freeze_run_id=args.freeze_run_id,
        freeze_run_attempt=args.freeze_run_attempt,
        freeze_artifact_name=args.freeze_artifact_name,
        quote_run_id=args.quote_run_id,
        quote_run_attempt=args.quote_run_attempt,
        quote_artifact_name=args.quote_artifact_name,
        workflow_run_id=args.workflow_run_id,
        workflow_run_attempt=args.workflow_run_attempt,
    )
    if args.report_output.exists() or args.capture_output.exists():
        raise FileExistsError("prospective acquisition outputs must be write-once")

    generated_at = datetime.now(UTC)
    secret = os.getenv("DATABENTO_API_KEY")
    common = (*chain, authorization)
    context = {
        "generated_at": generated_at,
        "workflow_run_id": args.workflow_run_id,
        "workflow_run_attempt": args.workflow_run_attempt,
    }
    if chain[3].request_count == 0:
        report, capture = build_zero_request_result(*common, **context)
    elif not secret:
        report = build_unavailable_report(
            *common,
            **context,
            sdk_version="not_loaded",
            error_stage="credential",
            error_kind="missing_databento_api_key",
        )
        capture = None
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
            capture = None
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
                capture = None
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
                    capture = None
                else:
                    report, capture = run_exact_acquisition(
                        *common,
                        client,
                        **context,
                        sdk_version=version,
                    )

    validate_acquisition_report(
        report,
        capture=capture,
        acquisition_contract=chain[0],
        quote_contract=chain[1],
        capture_contract=chain[2],
        bundle=chain[3],
        quote_authorization=chain[4],
        quote_report=chain[5],
        authorization=authorization,
    )
    rendered_report = _render(report, secret)
    rendered_capture = None if capture is None else _render(capture, secret)
    _write_once(args.report_output, rendered_report)
    if rendered_capture is not None:
        _write_once(args.capture_output, rendered_capture)
    print(rendered_report, end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create an exact quote-bound prospective acquisition authorization "
            "or execute its single sanitized first attempt."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    authorize = commands.add_parser(
        "authorize",
        help="Create a provider-free authorization after a successful exact quote.",
    )
    _add_chain_arguments(authorize)
    authorize.add_argument("--repository", required=True)
    authorize.add_argument("--quote-artifact-name", required=True)
    authorize.add_argument("--output", type=Path, required=True)

    acquire = commands.add_parser(
        "acquire",
        help="Requote and acquire only the exact authorized request manifest once.",
    )
    _add_chain_arguments(acquire)
    acquire.add_argument("--authorization", type=Path, required=True)
    acquire.add_argument("--repository", required=True)
    acquire.add_argument("--freeze-run-id", required=True)
    acquire.add_argument("--freeze-run-attempt", type=int, required=True)
    acquire.add_argument("--freeze-artifact-name", required=True)
    acquire.add_argument("--quote-run-id", required=True)
    acquire.add_argument("--quote-run-attempt", type=int, required=True)
    acquire.add_argument("--quote-artifact-name", required=True)
    acquire.add_argument("--workflow-run-id", required=True)
    acquire.add_argument("--workflow-run-attempt", type=int, required=True)
    acquire.add_argument("--report-output", type=Path, required=True)
    acquire.add_argument("--capture-output", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "authorize":
        return _authorize(args)
    return _acquire(args)


if __name__ == "__main__":
    sys.exit(main())
