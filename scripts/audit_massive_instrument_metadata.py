from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from momentumbot.instrument_metadata import (
    InstrumentMetadataStatus,
    audit_instrument_metadata,
    instrument_metadata_audit_manifest,
)
from momentumbot.providers.massive import (
    normalize_reference_tickers,
    reference_membership_fingerprint,
    reference_ticker_fingerprint,
)


def _json_fingerprint(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def audit_records(
    rows: list[dict[str, object]] | tuple[dict[str, object], ...],
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for row in normalize_reference_tickers(rows):
        audit = audit_instrument_metadata(row)
        output.append(
            {
                "ticker": audit.ticker,
                "security_type": audit.security_type or "missing",
                "primary_exchange": str(row["primary_exchange"]) or "missing",
                "name": audit.name,
                "cik": str(row["cik"]),
                "composite_figi": str(row["composite_figi"]),
                "share_class_figi": str(row["share_class_figi"]),
                "flags": "|".join(audit.flags),
                "status": audit.status.value,
            }
        )
    return output


def summarize_records(records: list[dict[str, object]]) -> dict[str, object]:
    statuses = Counter(str(record["status"]) for record in records)
    all_record_flags = Counter(
        flag
        for record in records
        for flag in str(record["flags"]).split("|")
        if flag
    )
    common_family_statuses = {
        InstrumentMetadataStatus.EXPLICIT_NON_COMMON_CONFLICT.value,
        InstrumentMetadataStatus.MISSING_NAME_REVIEW.value,
        InstrumentMetadataStatus.NO_NAME_CONFLICT_DETECTED.value,
        InstrumentMetadataStatus.UNIT_STRUCTURE_REVIEW.value,
    }
    common_family_flags = Counter(
        flag
        for record in records
        if str(record["status"]) in common_family_statuses
        for flag in str(record["flags"]).split("|")
        if flag
    )
    return {
        "security_record_count": len(records),
        "unique_ticker_count": len({str(record["ticker"]) for record in records}),
        "common_type_family_record_count": sum(
            str(record["status"]) in common_family_statuses for record in records
        ),
        "status_counts": dict(sorted(statuses.items())),
        "all_record_flag_counts": dict(sorted(all_record_flags.items())),
        "common_type_family_flag_counts": dict(sorted(common_family_flags.items())),
        "explicit_conflict_tickers": sorted(
            {
                str(record["ticker"])
                for record in records
                if record["status"]
                == InstrumentMetadataStatus.EXPLICIT_NON_COMMON_CONFLICT.value
            }
        ),
        "review_tickers": sorted(
            {
                str(record["ticker"])
                for record in records
                if record["status"]
                in {
                    InstrumentMetadataStatus.MISSING_NAME_REVIEW.value,
                    InstrumentMetadataStatus.UNIT_STRUCTURE_REVIEW.value,
                }
            }
        ),
        "records_sha256": _json_fingerprint(records),
    }


def build_date_manifest(
    *,
    census_manifest: dict[str, Any],
    summary: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "trading_date": census_manifest["requested_asof_date"],
        "census_content_sha256": census_manifest["census_content_sha256"],
        "membership_sha256": census_manifest["membership_sha256"],
        "audit_policy": instrument_metadata_audit_manifest(),
        "summary": summary,
        "eligibility": {
            "instrument_translation_frozen": False,
            "universe_complete": False,
            "full_walk_forward_eligible": False,
            "policy_promotion_eligible": False,
            "remaining_gates": [
                "resolve unit-structure review rows",
                "prove that no-name-conflict rows are semantically eligible",
                "resolve multi-identity tickers and corporate actions",
                "join the frozen market-data sufficiency contract",
            ],
        },
        "knowledge_policy": (
            "provider_metadata_only_no_benchmark_labels_no_strategy_feedback"
        ),
    }


def _load_census(
    date_root: Path,
) -> tuple[dict[str, Any], tuple[dict[str, object], ...]]:
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
        raise RuntimeError("metadata audit requires an exhausted census fetch")
    return manifest, rows


def _write_records(path: Path, records: list[dict[str, object]]) -> None:
    fields = [
        "ticker",
        "security_type",
        "primary_exchange",
        "name",
        "cik",
        "composite_figi",
        "share_class_figi",
        "flags",
        "status",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--census-root", type=Path, required=True)
    args = parser.parse_args(argv)

    root_manifest = json.loads(
        (args.census_root / "manifest.json").read_text(encoding="utf-8")
    )
    if not root_manifest.get("all_fetches_complete"):
        raise RuntimeError("metadata audit requires complete census fetches")

    output_root = args.census_root / "instrument-metadata-audit"
    output_root.mkdir(parents=True, exist_ok=False)
    date_manifests: list[dict[str, object]] = []
    for value in root_manifest["dates"]:
        census_manifest, rows = _load_census(args.census_root / value)
        records = audit_records(rows)
        summary = summarize_records(records)
        manifest = build_date_manifest(
            census_manifest=census_manifest,
            summary=summary,
        )
        _write_records(output_root / f"{value}.csv", records)
        _write_json(output_root / f"{value}.json", manifest)
        date_manifests.append(manifest)

    output_manifest = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dates": root_manifest["dates"],
        "audit_policy": instrument_metadata_audit_manifest(),
        "date_manifests": date_manifests,
        "instrument_translation_frozen": False,
        "universe_complete": False,
        "full_walk_forward_eligible": False,
        "policy_promotion_eligible": False,
        "knowledge_policy": (
            "provider_metadata_only_no_benchmark_labels_no_strategy_feedback"
        ),
    }
    _write_json(output_root / "manifest.json", output_manifest)
    print(
        json.dumps(
            {
                "dates": root_manifest["dates"],
                "status_counts": {
                    manifest["trading_date"]: manifest["summary"]["status_counts"]
                    for manifest in date_manifests
                },
                "instrument_translation_frozen": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
