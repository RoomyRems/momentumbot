from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.providers.massive import (
    normalize_reference_tickers,
    reference_membership_fingerprint,
    reference_ticker_fingerprint,
)


ET = ZoneInfo("America/New_York")


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


def group_security_records(
    rows: list[dict[str, object]] | tuple[dict[str, object], ...],
) -> list[dict[str, object]]:
    groups: dict[str, list[dict[str, object]]] = {}
    for row in normalize_reference_tickers(rows):
        groups.setdefault(str(row["ticker"]), []).append(row)
    return [
        {
            "ticker": ticker,
            "security_record_count": len(matches),
            "primary_exchanges": tuple(
                sorted({str(row["primary_exchange"]) for row in matches})
            ),
            "security_types": tuple(sorted({str(row["type"]) or "missing" for row in matches})),
        }
        for ticker, matches in sorted(groups.items())
    ]


def _session_dates(frame: pd.DataFrame) -> set[date]:
    if frame.empty:
        return set()
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("coverage bars require a timezone-aware DatetimeIndex")
    return set(frame.index.tz_convert(ET).date)


def evaluate_ticker_coverage(
    security: dict[str, object],
    *,
    trading_date: date,
    raw_frame: pd.DataFrame,
    split_frame: pd.DataFrame,
    invalid_symbol: bool,
) -> dict[str, object]:
    raw_dates = _session_dates(raw_frame)
    split_dates = _session_dates(split_frame)
    raw_target = trading_date in raw_dates
    raw_prior = any(value < trading_date for value in raw_dates)
    split_target = trading_date in split_dates
    split_prior = any(value < trading_date for value in split_dates)
    coverage_pass = bool(
        not invalid_symbol
        and raw_target
        and raw_prior
        and split_target
        and split_prior
    )
    return {
        "ticker": security["ticker"],
        "security_record_count": security["security_record_count"],
        "primary_exchanges": "|".join(security["primary_exchanges"]),
        "security_types": "|".join(security["security_types"]),
        "invalid_symbol": invalid_symbol,
        "raw_bar_count": len(raw_frame),
        "split_bar_count": len(split_frame),
        "raw_prior_session_present": raw_prior,
        "raw_target_session_present": raw_target,
        "split_prior_session_present": split_prior,
        "split_target_session_present": split_target,
        "coverage_pass": coverage_pass,
    }


def _group_summary(
    records: list[dict[str, object]],
    field: str,
) -> dict[str, dict[str, object]]:
    output: dict[str, dict[str, object]] = {}
    for record in records:
        values = str(record[field]).split("|") if record[field] else ["missing"]
        for value in values:
            bucket = output.setdefault(value, {"ticker_count": 0, "coverage_pass_count": 0})
            bucket["ticker_count"] = int(bucket["ticker_count"]) + 1
            if record["coverage_pass"]:
                bucket["coverage_pass_count"] = int(bucket["coverage_pass_count"]) + 1
    for bucket in output.values():
        total = int(bucket["ticker_count"])
        passed = int(bucket["coverage_pass_count"])
        bucket["coverage_fail_count"] = total - passed
        bucket["coverage_ratio"] = passed / total if total else None
    return dict(sorted(output.items()))


def summarize_coverage(records: list[dict[str, object]]) -> dict[str, object]:
    total = len(records)
    passed = sum(bool(record["coverage_pass"]) for record in records)
    failure_reasons = Counter()
    for record in records:
        if record["invalid_symbol"]:
            failure_reasons["invalid_symbol"] += 1
        for field in (
            "raw_prior_session_present",
            "raw_target_session_present",
            "split_prior_session_present",
            "split_target_session_present",
        ):
            if not record[field]:
                failure_reasons[f"missing_{field.removesuffix('_present')}"] += 1
    return {
        "unique_ticker_count": total,
        "coverage_pass_count": passed,
        "coverage_fail_count": total - passed,
        "coverage_ratio": passed / total if total else None,
        "invalid_symbol_count": sum(bool(record["invalid_symbol"]) for record in records),
        "failure_reason_counts": dict(sorted(failure_reasons.items())),
        "by_security_type": _group_summary(records, "security_types"),
        "by_primary_exchange": _group_summary(records, "primary_exchanges"),
        "records_sha256": _json_fingerprint(records),
    }


def build_coverage_manifest(
    *,
    trading_date: date,
    census_manifest: dict[str, Any],
    summary: dict[str, object],
    started_at_utc: str,
    completed_at_utc: str,
) -> dict[str, object]:
    all_market_data_covered = bool(
        summary["unique_ticker_count"]
        and summary["coverage_fail_count"] == 0
    )
    return {
        "schema_version": 1,
        "trading_date": trading_date.isoformat(),
        "started_at_utc": started_at_utc,
        "completed_at_utc": completed_at_utc,
        "census_content_sha256": census_manifest["census_content_sha256"],
        "membership_sha256": census_manifest["membership_sha256"],
        "query": {
            "provider": "alpaca_stock_bars",
            "feed": "sip",
            "timeframe": "1Day",
            "adjustments": ["raw", "split"],
            "asof": trading_date.isoformat(),
            "coverage_requirement": (
                "prior and target sessions present in both raw and split series"
            ),
        },
        "summary": summary,
        "eligibility": {
            "all_census_tickers_market_data_covered": all_market_data_covered,
            "universe_complete": False,
            "full_walk_forward_eligible": False,
            "policy_promotion_eligible": False,
            "remaining_gates": [
                "resolve every uncovered ticker or prove it ineligible",
                "freeze security-type eligibility translation",
                "reconcile symbol identity and corporate actions",
                "build and validate full causal feature snapshots",
            ],
        },
        "knowledge_policy": "provider_coverage_only_no_benchmark_labels_no_strategy_feedback",
    }


def _load_census(date_root: Path) -> tuple[dict[str, Any], tuple[dict[str, object], ...]]:
    manifest = json.loads((date_root / "manifest.json").read_text(encoding="utf-8"))
    payload = json.loads((date_root / "tickers.json").read_text(encoding="utf-8"))
    rows = normalize_reference_tickers(payload.get("rows", []))
    if manifest["requested_asof_date"] != date_root.name:
        raise RuntimeError("census directory date does not match its manifest")
    if reference_ticker_fingerprint(rows) != manifest["census_content_sha256"]:
        raise RuntimeError("census content fingerprint mismatch")
    if reference_membership_fingerprint(rows) != manifest["membership_sha256"]:
        raise RuntimeError("census membership fingerprint mismatch")
    if not manifest.get("fetch_complete"):
        raise RuntimeError("market coverage requires an exhausted census fetch")
    return manifest, rows


def _coverage_window(trading_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(
        trading_date - timedelta(days=14),
        time(0, 0),
        timezone.utc,
    )
    end = datetime.combine(
        trading_date + timedelta(days=1),
        time(0, 0),
        timezone.utc,
    )
    return start, end


def _write_records(path: Path, records: list[dict[str, object]]) -> None:
    fields = [
        "ticker",
        "security_record_count",
        "primary_exchanges",
        "security_types",
        "invalid_symbol",
        "raw_bar_count",
        "split_bar_count",
        "raw_prior_session_present",
        "raw_target_session_present",
        "split_prior_session_present",
        "split_target_session_present",
        "coverage_pass",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--census-root", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=250)
    args = parser.parse_args(argv)

    root_manifest = json.loads(
        (args.census_root / "manifest.json").read_text(encoding="utf-8")
    )
    if not root_manifest.get("all_fetches_complete"):
        raise RuntimeError("coverage audit requires complete census fetches")
    coverage_root = args.census_root / "market-data-coverage"
    coverage_root.mkdir(parents=True, exist_ok=False)

    date_manifests: list[dict[str, object]] = []
    for value in root_manifest["dates"]:
        trading_date = date.fromisoformat(value)
        census_manifest, census_rows = _load_census(args.census_root / value)
        securities = group_security_records(census_rows)
        tickers = [str(row["ticker"]) for row in securities]
        start, end = _coverage_window(trading_date)
        alpaca = AlpacaDataClient.from_env()
        started_at = datetime.now(timezone.utc).isoformat()
        raw = alpaca.bars_batched(
            tickers,
            batch_size=args.batch_size,
            timeframe="1Day",
            start=start,
            end=end,
            feed="sip",
            adjustment="raw",
            asof=trading_date,
        )
        split = alpaca.bars_batched(
            tickers,
            batch_size=args.batch_size,
            timeframe="1Day",
            start=start,
            end=end,
            feed="sip",
            adjustment="split",
            asof=trading_date,
        )
        records = [
            evaluate_ticker_coverage(
                security,
                trading_date=trading_date,
                raw_frame=raw.get(str(security["ticker"]), pd.DataFrame()),
                split_frame=split.get(str(security["ticker"]), pd.DataFrame()),
                invalid_symbol=str(security["ticker"]) in alpaca.invalid_symbols,
            )
            for security in securities
        ]
        completed_at = datetime.now(timezone.utc).isoformat()
        summary = summarize_coverage(records)
        manifest = build_coverage_manifest(
            trading_date=trading_date,
            census_manifest=census_manifest,
            summary=summary,
            started_at_utc=started_at,
            completed_at_utc=completed_at,
        )
        _write_records(coverage_root / f"{value}.csv", records)
        _write_json(coverage_root / f"{value}.json", manifest)
        date_manifests.append(manifest)

    output_manifest = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dates": root_manifest["dates"],
        "date_manifests": date_manifests,
        "universe_complete": False,
        "full_walk_forward_eligible": False,
        "policy_promotion_eligible": False,
        "knowledge_policy": "provider_coverage_only_no_benchmark_labels_no_strategy_feedback",
    }
    _write_json(coverage_root / "manifest.json", output_manifest)
    print(
        json.dumps(
            {
                "dates": root_manifest["dates"],
                "coverage": {
                    manifest["trading_date"]: manifest["summary"]["coverage_ratio"]
                    for manifest in date_manifests
                },
                "universe_complete": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
