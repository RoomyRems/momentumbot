from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from momentumbot.historical_data import (
    asset_master_fingerprint,
    asset_master_status_counts,
    normalize_asset_master,
)
from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.providers.massive import (
    OFFICIAL_ALL_TICKERS_DOC,
    MassiveReferenceClient,
    MassiveTickerCensus,
    normalize_reference_tickers,
    reference_membership_identity,
    reference_membership_fingerprint,
    reference_ticker_fingerprint,
)


DEFAULT_DATES = ("2025-04-03", "2026-07-09")


def _json_fingerprint(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def summarize_census(
    rows: list[dict[str, object]] | tuple[dict[str, object], ...],
) -> dict[str, object]:
    normalized = normalize_reference_tickers(rows)
    tickers = [str(row["ticker"]) for row in normalized]
    membership_identities = [reference_membership_identity(row) for row in normalized]
    ticker_counts = Counter(tickers)
    active_counts = Counter(str(row["active"]).lower() for row in normalized)
    exchange_counts = Counter(str(row["primary_exchange"]) or "missing" for row in normalized)
    type_counts = Counter(str(row["type"]) or "missing" for row in normalized)
    market_counts = Counter(str(row["market"]) or "missing" for row in normalized)
    locale_counts = Counter(str(row["locale"]) or "missing" for row in normalized)
    return {
        "row_count": len(normalized),
        "unique_ticker_count": len(set(tickers)),
        "duplicate_ticker_count": len(tickers) - len(set(tickers)),
        "ticker_collision_group_count": sum(
            count > 1 for count in ticker_counts.values()
        ),
        "unique_membership_identity_count": len(set(membership_identities)),
        "duplicate_membership_identity_count": (
            len(membership_identities) - len(set(membership_identities))
        ),
        "active_counts": dict(sorted(active_counts.items())),
        "market_counts": dict(sorted(market_counts.items())),
        "locale_counts": dict(sorted(locale_counts.items())),
        "primary_exchange_counts": dict(sorted(exchange_counts.items())),
        "security_type_counts": dict(sorted(type_counts.items())),
        "missing_primary_exchange_count": sum(not row["primary_exchange"] for row in normalized),
        "missing_security_type_count": sum(not row["type"] for row in normalized),
        "missing_cik_count": sum(not row["cik"] for row in normalized),
        "missing_composite_figi_count": sum(not row["composite_figi"] for row in normalized),
        "all_rows_active": all(row["active"] is True for row in normalized),
        "all_rows_us_stocks": all(
            row["market"] == "stocks" and row["locale"] == "us"
            for row in normalized
        ),
    }


def build_reconciliation(
    massive_rows: list[dict[str, object]] | tuple[dict[str, object], ...],
    alpaca_rows: list[dict[str, object]] | tuple[dict[str, object], ...],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    normalized_massive = normalize_reference_tickers(massive_rows)
    massive_groups: dict[str, list[dict[str, object]]] = {}
    for row in normalized_massive:
        massive_groups.setdefault(str(row["ticker"]), []).append(row)
    normalized_alpaca = normalize_asset_master(list(alpaca_rows))
    alpaca_groups: dict[str, list[dict[str, object]]] = {}
    for row in normalized_alpaca:
        alpaca_groups.setdefault(str(row["symbol"]), []).append(row)

    records: list[dict[str, object]] = []
    for ticker in sorted(set(massive_groups) | set(alpaca_groups)):
        massive_matches = massive_groups.get(ticker, [])
        alpaca_matches = alpaca_groups.get(ticker, [])
        records.append(
            {
                "ticker": ticker,
                "massive_asof_member": bool(massive_matches),
                "massive_asof_match_count": len(massive_matches),
                "massive_primary_exchanges": "|".join(
                    sorted({str(row["primary_exchange"]) for row in massive_matches})
                ),
                "massive_security_types": "|".join(
                    sorted({str(row["type"]) for row in massive_matches})
                ),
                "massive_composite_figis": "|".join(
                    sorted(
                        {
                            str(row["composite_figi"])
                            for row in massive_matches
                            if row["composite_figi"]
                        }
                    )
                ),
                "alpaca_current_member": bool(alpaca_matches),
                "alpaca_current_match_count": len(alpaca_matches),
                "alpaca_current_exchanges": "|".join(
                    sorted({str(row["exchange"]) for row in alpaca_matches})
                ),
                "alpaca_current_statuses": "|".join(
                    sorted({str(row["status"]) for row in alpaca_matches})
                ),
            }
        )

    massive_symbols = set(massive_groups)
    alpaca_symbols = set(alpaca_groups)
    overlap = massive_symbols & alpaca_symbols
    summary: dict[str, object] = {
        "comparison_scope": "massive_point_in_time_vs_alpaca_current_all_status_census",
        "alpaca_comparison_is_point_in_time": False,
        "massive_asof_count": len(massive_symbols),
        "massive_asof_security_record_count": len(normalized_massive),
        "massive_duplicate_ticker_count": (
            len(normalized_massive) - len(massive_symbols)
        ),
        "alpaca_current_unique_symbol_count": len(alpaca_symbols),
        "overlap_count": len(overlap),
        "massive_not_in_alpaca_current_count": len(massive_symbols - alpaca_symbols),
        "alpaca_current_not_in_massive_asof_count": len(alpaca_symbols - massive_symbols),
        "massive_ticker_overlap_ratio": (
            len(overlap) / len(massive_symbols) if massive_symbols else None
        ),
        "alpaca_duplicate_symbol_count": sum(
            len(matches) - 1 for matches in alpaca_groups.values()
        ),
        "record_count": len(records),
        "records_sha256": _json_fingerprint(records),
        "interpretation": (
            "Ticker overlap is a diagnostic only. Alpaca's comparison census is current, "
            "so agreement cannot prove historical membership completeness and disagreement "
            "may reflect delistings, symbol changes, security typing or provider coverage."
        ),
    }
    return records, summary


def build_date_manifest(
    census: MassiveTickerCensus,
    *,
    census_summary: dict[str, object],
    reconciliation_summary: dict[str, object],
    retrieved_at_utc: str,
    completed_at_utc: str,
    credential_name: str,
) -> dict[str, object]:
    page_rows = sum(page.row_count for page in census.pages)
    pagination_exhausted = bool(census.pages and not census.pages[-1].next_page_present)
    fetch_complete = pagination_exhausted and page_rows == len(census.rows)
    membership_candidate = bool(
        fetch_complete
        and census_summary["duplicate_membership_identity_count"] == 0
        and census_summary["all_rows_active"]
        and census_summary["all_rows_us_stocks"]
    )
    return {
        "schema_version": 1,
        "source": "massive_v3_reference_tickers",
        "official_contract": OFFICIAL_ALL_TICKERS_DOC,
        "credential_name": credential_name,
        "requested_asof_date": census.as_of,
        "query_without_credential": census.query,
        "retrieved_at_utc": retrieved_at_utc,
        "completed_at_utc": completed_at_utc,
        "page_count": len(census.pages),
        "pages": [asdict(page) for page in census.pages],
        "pagination_exhausted": pagination_exhausted,
        "page_row_sum": page_rows,
        "fetch_complete": fetch_complete,
        "census_summary": census_summary,
        "census_content_sha256": reference_ticker_fingerprint(census.rows),
        "membership_sha256": reference_membership_fingerprint(census.rows),
        "reconciliation": reconciliation_summary,
        "eligibility": {
            "point_in_time_membership_candidate": membership_candidate,
            "universe_complete": False,
            "full_walk_forward_eligible": False,
            "policy_promotion_eligible": False,
            "remaining_gates": [
                "historical market-data coverage for the entire census",
                "security-type and exchange eligibility translation",
                "symbol-identity and corporate-action reconciliation",
                "independent cross-sectional coverage checks",
            ],
        },
        "knowledge_policy": "provider_membership_only_no_benchmark_labels_no_strategy_feedback",
    }


def _write_reconciliation(path: Path, rows: list[dict[str, object]]) -> None:
    fields = [
        "ticker",
        "massive_asof_member",
        "massive_asof_match_count",
        "massive_primary_exchanges",
        "massive_security_types",
        "massive_composite_figis",
        "alpaca_current_member",
        "alpaca_current_match_count",
        "alpaca_current_exchanges",
        "alpaca_current_statuses",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dates", nargs="+", default=list(DEFAULT_DATES))
    parser.add_argument("--output", type=Path, default=Path("massive-historical-census"))
    parser.add_argument("--minimum-request-interval", type=float, default=12.5)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--max-pages", type=int, default=100)
    args = parser.parse_args(argv)

    trading_dates = sorted({date.fromisoformat(value) for value in args.dates})
    if not trading_dates:
        raise ValueError("at least one historical date is required")
    root = args.output
    if root.exists() and any(root.iterdir()):
        raise RuntimeError("output directory must be absent or empty")
    root.mkdir(parents=True, exist_ok=True)

    massive = MassiveReferenceClient.from_env(
        minimum_request_interval_seconds=args.minimum_request_interval
    )
    alpaca = AlpacaDataClient.from_env()
    alpaca_retrieved_at = datetime.now(timezone.utc).isoformat()
    raw_alpaca_assets = alpaca.assets()
    normalized_alpaca_assets = normalize_asset_master(raw_alpaca_assets)
    alpaca_master_sha = asset_master_fingerprint(raw_alpaca_assets)
    _write_json(
        root / "alpaca-current-asset-master.json",
        {
            "schema_version": 1,
            "source": "alpaca_v2_assets",
            "retrieved_at_utc": alpaca_retrieved_at,
            "point_in_time_membership": False,
            "asset_count": len(normalized_alpaca_assets),
            "status_counts": asset_master_status_counts(raw_alpaca_assets),
            "sha256": alpaca_master_sha,
            "assets": normalized_alpaca_assets,
        },
    )

    date_manifests: list[dict[str, object]] = []
    for trading_date in trading_dates:
        retrieved_at = datetime.now(timezone.utc).isoformat()
        census = massive.active_tickers_as_of(
            trading_date,
            limit=args.limit,
            max_pages=args.max_pages,
        )
        completed_at = datetime.now(timezone.utc).isoformat()
        census_summary = summarize_census(census.rows)
        reconciliation_rows, reconciliation_summary = build_reconciliation(
            census.rows,
            list(normalized_alpaca_assets),
        )
        manifest = build_date_manifest(
            census,
            census_summary=census_summary,
            reconciliation_summary=reconciliation_summary,
            retrieved_at_utc=retrieved_at,
            completed_at_utc=completed_at,
            credential_name=massive.credential_name,
        )

        date_root = root / trading_date.isoformat()
        date_root.mkdir(parents=True, exist_ok=False)
        _write_json(
            date_root / "tickers.json",
            {
                "schema_version": 1,
                "requested_asof_date": trading_date.isoformat(),
                "content_sha256": manifest["census_content_sha256"],
                "membership_sha256": manifest["membership_sha256"],
                "rows": census.rows,
            },
        )
        _write_reconciliation(
            date_root / "alpaca-current-reconciliation.csv",
            reconciliation_rows,
        )
        _write_json(date_root / "manifest.json", manifest)
        date_manifests.append(manifest)

    root_manifest = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "label-blind paginated historical ticker-census prototype",
        "dates": [value.isoformat() for value in trading_dates],
        "massive_credential_name": massive.credential_name,
        "minimum_request_interval_seconds": args.minimum_request_interval,
        "official_free_tier_limit": "5 API requests per minute",
        "alpaca_current_asset_master_sha256": alpaca_master_sha,
        "date_manifests": date_manifests,
        "all_fetches_complete": all(
            bool(manifest["fetch_complete"]) for manifest in date_manifests
        ),
        "universe_complete": False,
        "full_walk_forward_eligible": False,
        "policy_promotion_eligible": False,
        "knowledge_policy": "provider_membership_only_no_benchmark_labels_no_strategy_feedback",
    }
    _write_json(root / "manifest.json", root_manifest)
    print(
        json.dumps(
            {
                "output": str(root),
                "dates": root_manifest["dates"],
                "row_counts": {
                    manifest["requested_asof_date"]: manifest["census_summary"]["row_count"]
                    for manifest in date_manifests
                },
                "page_counts": {
                    manifest["requested_asof_date"]: manifest["page_count"]
                    for manifest in date_manifests
                },
                "all_fetches_complete": root_manifest["all_fetches_complete"],
                "universe_complete": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
