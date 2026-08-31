from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
import time as clock
from typing import Any, Callable
import urllib.error

import pandas as pd

from momentumbot.causal_market_discovery_v03 import (
    CAUSAL_MARKET_DISCOVERY_POLICY_ID,
    load_market_candidate_payload,
)
from momentumbot.historical_float_v03 import (
    CAUSAL_FLOAT_POLICY_ID,
    BasisObservation,
    build_causal_float_record,
    causal_float_records_fingerprint,
    causal_float_v0_1_manifest,
    observe_basis,
    select_float_evidence,
    validate_causal_float_records,
)
from momentumbot.identity_resolved_universe import json_fingerprint
from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.providers.request_budget import consume_provider_request
from momentumbot.providers.sec_edgar import (
    ParsedCompanyFacts,
    SecEdgarClient,
    normalize_cik,
    parse_companyfacts,
    parse_submission_acceptance_times,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sec_call(
    function: Callable[[], dict[str, Any]],
    *,
    attempts: int,
    retry_delay_seconds: float,
) -> tuple[dict[str, Any] | None, str, str | None]:
    for attempt in range(attempts):
        try:
            consume_provider_request("https://data.sec.gov")
            return function(), "success", None
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None, "not_found", None
            error = f"HTTPError:{exc.code}"
        except Exception as exc:  # Provider/network failure is recorded, never hidden.
            error = type(exc).__name__
        if attempt + 1 < attempts:
            clock.sleep(retry_delay_seconds * (2**attempt))
    return None, "provider_error", error


def _download_basis(
    client: AlpacaDataClient,
    symbol: str,
    requested_dates: list[date],
    *,
    trading_date: date,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not requested_dates:
        return pd.DataFrame(), pd.DataFrame()
    start, end = _basis_query_window(
        requested_dates,
        trading_date=trading_date,
    )
    raw = client.bars(
        [symbol],
        timeframe="1Day",
        start=start,
        end=end,
        feed="sip",
        adjustment="raw",
        asof=trading_date,
    ).get(symbol, pd.DataFrame())
    split = client.bars(
        [symbol],
        timeframe="1Day",
        start=start,
        end=end,
        feed="sip",
        adjustment="split",
        asof=trading_date,
    ).get(symbol, pd.DataFrame())
    return raw, split


def _basis_query_window(
    requested_dates: list[date],
    *,
    trading_date: date,
) -> tuple[datetime, datetime]:
    if not requested_dates:
        raise ValueError("at least one basis date is required")
    if max(requested_dates) > trading_date:
        raise ValueError("basis date cannot follow the causal trading date")
    start = datetime.combine(
        min(requested_dates) - timedelta(days=14),
        time(0),
        timezone.utc,
    )
    desired_end = datetime.combine(
        max(requested_dates) + timedelta(days=15),
        time(0),
        timezone.utc,
    )
    causal_end = datetime.combine(
        trading_date + timedelta(days=1),
        time(0),
        timezone.utc,
    )
    return start, min(desired_end, causal_end)


def _selected_evidence_status(
    selected: dict[str, object],
    *,
    submissions_available: bool,
    acceptance_times: dict[str, datetime],
) -> str:
    accessions = [
        str(disclosure["accession"])
        for key in ("public_float", "anchor_outstanding", "current_outstanding")
        if isinstance((disclosure := selected.get(key)), dict)
    ]
    if not accessions:
        return "success_no_eligible_sec_evidence"
    if not submissions_available:
        return "success_selected_evidence_conservative_filing_date_fallback"
    if all(accession in acceptance_times for accession in accessions):
        return "success_selected_evidence_exact_acceptance"
    return "success_selected_evidence_includes_conservative_fallback"


def _validate_sec_entity(
    payload: dict[str, Any],
    *,
    expected_cik: str,
    label: str,
) -> None:
    try:
        observed = normalize_cik(payload.get("cik", ""))
    except ValueError as exc:
        raise ValueError(f"{label} payload lacks a valid CIK") from exc
    if observed != expected_cik:
        raise ValueError(f"{label} payload CIK does not match candidate identity")


def _empty_float_record(
    candidate: dict[str, object],
    *,
    cik: str,
    status: str,
    provider_error: str | None = None,
) -> dict[str, object]:
    selected = {
        "symbol": candidate["symbol"],
        "cik": cik,
        "first_market_qualified_bar_started_at": candidate[
            "first_market_qualified_bar_started_at"
        ],
        "first_market_qualified_at": candidate["first_market_qualified_at"],
        "public_float": None,
        "anchor_outstanding": None,
        "current_outstanding": None,
    }
    return build_causal_float_record(
        selected,
        {},
        sec_status=status,
        sec_provider_error=provider_error,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--census-root", type=Path, required=True)
    parser.add_argument("--dates", nargs="+")
    parser.add_argument("--minimum-sec-request-interval", type=float, default=0.2)
    parser.add_argument("--sec-attempts", type=int, default=3)
    parser.add_argument("--max-candidates-per-date", type=int, default=100)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--market-discovery-id",
        default=CAUSAL_MARKET_DISCOVERY_POLICY_ID,
    )
    args = parser.parse_args(argv)
    if args.minimum_sec_request_interval < 0:
        raise ValueError("SEC request interval cannot be negative")
    if args.sec_attempts <= 0:
        raise ValueError("SEC attempts must be positive")
    if args.max_candidates_per_date <= 0:
        raise ValueError("candidate ceiling must be positive")

    discovery_root = args.census_root / args.market_discovery_id
    discovery_manifest = json.loads(
        (discovery_root / "manifest.json").read_text(encoding="utf-8")
    )
    dates = args.dates or discovery_manifest.get("dates")
    if not isinstance(dates, list) or not dates:
        raise ValueError("at least one float-enrichment date is required")
    if len(dates) != len(set(dates)):
        raise ValueError("float-enrichment dates must be unique")

    output_root = args.output or args.census_root / CAUSAL_FLOAT_POLICY_ID
    output_root.mkdir(parents=True, exist_ok=False)
    sec = SecEdgarClient.from_env()
    alpaca = AlpacaDataClient.from_env()
    date_manifests: list[dict[str, object]] = []
    fatal_provider_errors: list[dict[str, str]] = []
    sec_cache: dict[
        str,
        tuple[
            dict[str, Any] | None,
            str,
            str | None,
            dict[str, Any] | None,
            str,
            str | None,
        ],
    ] = {}
    sec_cache_hits = 0
    sec_endpoint_request_count = 0

    for value in dates:
        trading_date = date.fromisoformat(value)
        candidate_rows, candidate_payload, discovery_date_manifest = (
            load_market_candidate_payload(discovery_root / value)
        )
        if len(candidate_rows) > args.max_candidates_per_date:
            raise RuntimeError(
                f"{value} candidate count exceeds the frozen acquisition ceiling"
            )
        records: list[dict[str, object]] = []
        for candidate in candidate_rows:
            symbol = str(candidate["symbol"])
            raw_cik = str(candidate.get("selected_cik") or "")
            try:
                cik = normalize_cik(raw_cik)
            except ValueError:
                records.append(
                    _empty_float_record(
                        candidate,
                        cik=raw_cik,
                        status="missing_or_invalid_identity_cik",
                    )
                )
                continue

            cached = sec_cache.get(cik)
            if cached is None:
                submissions, submissions_status, submissions_error = _sec_call(
                    lambda cik=cik: sec.submissions(cik),
                    attempts=args.sec_attempts,
                    retry_delay_seconds=max(
                        args.minimum_sec_request_interval, 0.5
                    ),
                )
                sec_endpoint_request_count += 1
                clock.sleep(args.minimum_sec_request_interval)
                companyfacts, facts_status, facts_error = _sec_call(
                    lambda cik=cik: sec.companyfacts(cik),
                    attempts=args.sec_attempts,
                    retry_delay_seconds=max(
                        args.minimum_sec_request_interval, 0.5
                    ),
                )
                sec_endpoint_request_count += 1
                clock.sleep(args.minimum_sec_request_interval)
                cached = (
                    submissions,
                    submissions_status,
                    submissions_error,
                    companyfacts,
                    facts_status,
                    facts_error,
                )
                if (
                    submissions_status != "provider_error"
                    and facts_status != "provider_error"
                ):
                    sec_cache[cik] = cached
            else:
                sec_cache_hits += 1
            (
                submissions,
                submissions_status,
                submissions_error,
                companyfacts,
                facts_status,
                facts_error,
            ) = cached
            if submissions_status == "provider_error" or facts_status == "provider_error":
                error = submissions_error or facts_error or "unknown_provider_error"
                fatal_provider_errors.append(
                    {"trading_date": value, "symbol": symbol, "error": error}
                )
                records.append(
                    _empty_float_record(
                        candidate,
                        cik=cik,
                        status="provider_error",
                        provider_error=error,
                    )
                )
                continue
            if companyfacts is None:
                records.append(
                    _empty_float_record(
                        candidate,
                        cik=cik,
                        status="sec_companyfacts_not_found",
                    )
                )
                continue

            try:
                if submissions is not None:
                    _validate_sec_entity(
                        submissions,
                        expected_cik=cik,
                        label="submissions",
                    )
                _validate_sec_entity(
                    companyfacts,
                    expected_cik=cik,
                    label="companyfacts",
                )
                acceptance = (
                    parse_submission_acceptance_times(submissions)
                    if submissions is not None
                    else {}
                )
                parsed = parse_companyfacts(
                    companyfacts,
                    acceptance_times=acceptance,
                )
                qualified_at = datetime.fromisoformat(
                    str(candidate["first_market_qualified_at"])
                )
                qualified_bar_started_at = datetime.fromisoformat(
                    str(candidate["first_market_qualified_bar_started_at"])
                )
                selected = select_float_evidence(
                    parsed,
                    symbol=symbol,
                    cik=cik,
                    first_market_qualified_at=qualified_at,
                    first_market_qualified_bar_started_at=(
                        qualified_bar_started_at
                    ),
                )
                # Preserve the frozen source representation as well as the
                # instant; downstream fingerprints bind to the candidate row.
                selected["first_market_qualified_bar_started_at"] = candidate[
                    "first_market_qualified_bar_started_at"
                ]
                selected["first_market_qualified_at"] = candidate[
                    "first_market_qualified_at"
                ]
            except (KeyError, TypeError, ValueError) as exc:
                error = f"sec_payload_error:{type(exc).__name__}"
                fatal_provider_errors.append(
                    {"trading_date": value, "symbol": symbol, "error": error}
                )
                records.append(
                    _empty_float_record(
                        candidate,
                        cik=cik,
                        status="provider_error",
                        provider_error=error,
                    )
                )
                continue
            tagged_dates: list[tuple[str, date]] = []
            for tag, key in (
                ("public", "public_float"),
                ("anchor", "anchor_outstanding"),
                ("current", "current_outstanding"),
            ):
                disclosure = selected.get(key)
                if isinstance(disclosure, dict):
                    tagged_dates.append(
                        (tag, date.fromisoformat(str(disclosure["measure_date"])))
                    )
            raw, split = _download_basis(
                alpaca,
                symbol,
                [requested for _, requested in tagged_dates],
                trading_date=trading_date,
            )
            observations: dict[str, BasisObservation] = {}
            for tag, requested in tagged_dates:
                observations[f"{tag}:{requested.isoformat()}"] = observe_basis(
                    raw,
                    split,
                    requested,
                )
            records.append(
                build_causal_float_record(
                    selected,
                    observations,
                    sec_status=_selected_evidence_status(
                        selected,
                        submissions_available=submissions is not None,
                        acceptance_times=acceptance,
                    ),
                )
            )

        records.sort(key=lambda row: str(row["symbol"]))
        validate_causal_float_records(candidate_rows, records)
        pass_count = sum(row["float_classification"] == "pass" for row in records)
        fail_count = sum(row["float_classification"] == "fail" for row in records)
        unknown_count = sum(
            row["float_classification"] == "unknown_fail_closed" for row in records
        )
        date_errors = [
            row for row in fatal_provider_errors if row["trading_date"] == value
        ]
        record_hash = causal_float_records_fingerprint(records)
        date_manifest: dict[str, object] = {
            "schema_version": 2,
            "artifact_id": CAUSAL_FLOAT_POLICY_ID,
            "trading_date": value,
            "float_policy": causal_float_v0_1_manifest(),
            "source_market_candidates_sha256": candidate_payload["content_sha256"],
            "source_market_candidates_artifact_id": candidate_payload[
                "artifact_id"
            ],
            "source_market_discovery_manifest_sha256": json_fingerprint(
                discovery_date_manifest
            ),
            "summary": {
                "market_candidate_count": len(candidate_rows),
                "float_decision_count": len(records),
                "float_pass_count": pass_count,
                "float_fail_count": fail_count,
                "float_unknown_fail_closed_count": unknown_count,
                "provider_error_count": len(date_errors),
                "float_method_counts": dict(
                    sorted(Counter(str(row["method"]) for row in records).items())
                ),
                "sec_status_counts": dict(
                    sorted(
                        Counter(str(row["sec_status"]) for row in records).items()
                    )
                ),
                "records_sha256": record_hash,
            },
            "eligibility": {
                "complete_relative_to_market_candidates": not date_errors,
                "point_in_time_float_decisions_frozen": not date_errors,
                "publication_timed_news_complete": False,
                "full_feature_snapshot_complete": False,
                "universe_complete": False,
                "full_walk_forward_eligible": False,
                "policy_promotion_eligible": False,
            },
            "knowledge_policy": {
                "uses_benchmark_labels": False,
                "uses_future_filings": False,
                "raw_future_disclosures_persisted": False,
                "unknown_float_fails_closed": True,
            },
            "files": {"float_records": "float-records.json"},
        }
        date_root = output_root / value
        date_root.mkdir()
        _write_json(date_root / "float-records.json", {"rows": records})
        _write_json(date_root / "manifest.json", date_manifest)
        date_manifests.append(date_manifest)

    root_manifest: dict[str, object] = {
        "schema_version": 2,
        "artifact_id": CAUSAL_FLOAT_POLICY_ID,
        "dates": dates,
        "float_policy": causal_float_v0_1_manifest(),
        "source_market_discovery_bundle_sha256": discovery_manifest[
            "content_sha256"
        ],
        "date_manifests": date_manifests,
        "fatal_provider_errors": fatal_provider_errors,
        "sec_acquisition": {
            "unique_successfully_cached_cik_count": len(sec_cache),
            "cache_hit_count": sec_cache_hits,
            "endpoint_request_count": sec_endpoint_request_count,
            "minimum_request_interval_seconds": args.minimum_sec_request_interval,
            "attempts_per_endpoint": args.sec_attempts,
        },
        "eligibility": {
            "complete_relative_to_market_candidates": not fatal_provider_errors,
            "point_in_time_float_decisions_frozen": not fatal_provider_errors,
            "publication_timed_news_complete": False,
            "full_feature_snapshot_complete": False,
            "universe_complete": False,
            "full_walk_forward_eligible": False,
            "policy_promotion_eligible": False,
        },
        "knowledge_policy": {
            "uses_benchmark_labels": False,
            "uses_future_filings": False,
            "raw_future_disclosures_persisted": False,
            "unknown_float_fails_closed": True,
        },
    }
    root_manifest["content_sha256"] = json_fingerprint(
        {
            "float_policy": root_manifest["float_policy"],
            "source_market_discovery_bundle_sha256": root_manifest[
                "source_market_discovery_bundle_sha256"
            ],
            "date_manifests": date_manifests,
        }
    )
    _write_json(output_root / "manifest.json", root_manifest)
    print(
        json.dumps(
            {
                "artifact_id": CAUSAL_FLOAT_POLICY_ID,
                "dates": dates,
                "float_counts": {
                    manifest["trading_date"]: manifest["summary"]
                    for manifest in date_manifests
                },
                "fatal_provider_error_count": len(fatal_provider_errors),
                "full_feature_snapshot_complete": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 2 if fatal_provider_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
