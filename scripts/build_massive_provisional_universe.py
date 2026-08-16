from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from momentumbot.historical_universe import (
    HistoricalUniverseDecision,
    classify_ticker_group,
    historical_universe_v0_1_manifest,
    historical_universe_v0_1_policy,
)
from momentumbot.instrument_metadata import instrument_metadata_audit_manifest
from momentumbot.providers.massive import (
    normalize_reference_tickers,
    reference_membership_fingerprint,
    reference_ticker_fingerprint,
)


_BOOLEAN_FIELDS = (
    "invalid_symbol",
    "raw_prior_session_present",
    "raw_target_session_present",
    "split_prior_session_present",
    "split_target_session_present",
    "coverage_pass",
)
_INTEGER_FIELDS = (
    "security_record_count",
    "raw_bar_count",
    "split_bar_count",
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


def _parse_bool(value: str) -> bool:
    if value == "True":
        return True
    if value == "False":
        return False
    raise ValueError(f"invalid coverage boolean: {value!r}")


def _load_coverage_records(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8", newline="") as handle:
        raw_records = list(csv.DictReader(handle))
    records: list[dict[str, object]] = []
    for raw in raw_records:
        record: dict[str, object] = dict(raw)
        for field in _BOOLEAN_FIELDS:
            record[field] = _parse_bool(str(raw[field]))
        for field in _INTEGER_FIELDS:
            record[field] = int(raw[field])
        records.append(record)
    return records


def _load_string_records(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def summarize_decisions(
    decisions: list[HistoricalUniverseDecision],
) -> dict[str, object]:
    payloads = [decision.payload() for decision in decisions]
    included = [decision for decision in decisions if decision.included]
    reason_counts = Counter(decision.reason.value for decision in decisions)
    type_counts = Counter(decision.selected_security_type for decision in included)
    exchange_counts = Counter(decision.selected_primary_exchange for decision in included)
    included_membership = [
        {
            "ticker": decision.ticker,
            "security_type": decision.selected_security_type,
            "primary_exchange": decision.selected_primary_exchange,
            "cik": decision.selected_cik,
            "composite_figi": decision.selected_composite_figi,
        }
        for decision in included
    ]
    return {
        "decision_count": len(decisions),
        "included_ticker_count": len(included),
        "excluded_ticker_count": len(decisions) - len(included),
        "reason_counts": dict(sorted(reason_counts.items())),
        "included_security_type_counts": dict(sorted(type_counts.items())),
        "included_primary_exchange_counts": dict(sorted(exchange_counts.items())),
        "source_collision_ticker_count": sum(
            decision.security_record_count > 1 for decision in decisions
        ),
        "included_collision_ticker_count": sum(
            decision.included and decision.security_record_count > 1
            for decision in decisions
        ),
        "included_missing_cik_count": sum(
            not decision.selected_cik for decision in included
        ),
        "included_missing_composite_figi_count": sum(
            not decision.selected_composite_figi for decision in included
        ),
        "decisions_sha256": _json_fingerprint(payloads),
        "included_membership_sha256": _json_fingerprint(included_membership),
    }


def build_date_manifest(
    *,
    trading_date: str,
    census_manifest: dict[str, Any],
    metadata_manifest: dict[str, Any],
    coverage_manifest: dict[str, Any],
    summary: dict[str, object],
) -> dict[str, object]:
    complete_relative_to_census = bool(
        summary["decision_count"]
        == census_manifest["census_summary"]["unique_ticker_count"]
    )
    return {
        "schema_version": 1,
        "trading_date": trading_date,
        "universe_policy": historical_universe_v0_1_manifest(),
        "sources": {
            "census_content_sha256": census_manifest["census_content_sha256"],
            "census_membership_sha256": census_manifest["membership_sha256"],
            "metadata_records_sha256": metadata_manifest["summary"][
                "records_sha256"
            ],
            "market_coverage_records_sha256": coverage_manifest["summary"][
                "records_sha256"
            ],
        },
        "summary": summary,
        "eligibility": {
            "complete_relative_to_census": complete_relative_to_census,
            "point_in_time_membership_translated": complete_relative_to_census,
            "universe_complete": False,
            "full_walk_forward_eligible": False,
            "policy_promotion_eligible": False,
            "remaining_gates": [
                "validate symbol continuity and corporate actions",
                "build point-in-time float and publication-timed news for every candidate",
                "build full causal daily and intraday feature snapshots",
                "repeat the contract across a representative walk-forward date panel",
            ],
        },
        "knowledge_policy": (
            "provider_metadata_and_coverage_only_no_benchmark_labels_no_strategy_feedback"
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
        raise RuntimeError("provisional universe requires an exhausted census fetch")
    return manifest, rows


def _write_decisions(
    path: Path,
    decisions: list[HistoricalUniverseDecision],
) -> None:
    fields = [
        "ticker",
        "included",
        "reason",
        "security_record_count",
        "common_type_record_count",
        "accepted_identity_count",
        "metadata_statuses",
        "selected_security_type",
        "selected_primary_exchange",
        "selected_cik",
        "selected_composite_figi",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for decision in decisions:
            payload = decision.payload()
            payload["metadata_statuses"] = "|".join(decision.metadata_statuses)
            writer.writerow(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--census-root", type=Path, required=True)
    args = parser.parse_args(argv)

    root_manifest = json.loads(
        (args.census_root / "manifest.json").read_text(encoding="utf-8")
    )
    if not root_manifest.get("all_fetches_complete"):
        raise RuntimeError("provisional universe requires complete census fetches")
    output_root = args.census_root / "provisional-universe-v0.1"
    output_root.mkdir(parents=True, exist_ok=False)

    policy = historical_universe_v0_1_policy()
    metadata_policy = instrument_metadata_audit_manifest()
    date_manifests: list[dict[str, object]] = []
    for value in root_manifest["dates"]:
        census_manifest, rows = _load_census(args.census_root / value)
        groups: dict[str, list[dict[str, object]]] = {}
        for row in rows:
            groups.setdefault(str(row["ticker"]), []).append(row)

        metadata_manifest = json.loads(
            (
                args.census_root / "instrument-metadata-audit" / f"{value}.json"
            ).read_text(encoding="utf-8")
        )
        if metadata_manifest["census_content_sha256"] != census_manifest[
            "census_content_sha256"
        ]:
            raise RuntimeError("metadata audit census fingerprint mismatch")
        if metadata_manifest["audit_policy"]["fingerprint"] != metadata_policy[
            "fingerprint"
        ]:
            raise RuntimeError("metadata audit policy fingerprint mismatch")
        metadata_records = _load_string_records(
            args.census_root
            / "instrument-metadata-audit"
            / f"{value}.csv"
        )
        if _json_fingerprint(metadata_records) != metadata_manifest["summary"][
            "records_sha256"
        ]:
            raise RuntimeError("metadata audit records fingerprint mismatch")

        coverage_root = args.census_root / "market-data-coverage"
        coverage_manifest = json.loads(
            (coverage_root / f"{value}.json").read_text(encoding="utf-8")
        )
        if coverage_manifest["membership_sha256"] != census_manifest[
            "membership_sha256"
        ]:
            raise RuntimeError("market coverage census fingerprint mismatch")
        coverage_records = _load_coverage_records(coverage_root / f"{value}.csv")
        if _json_fingerprint(coverage_records) != coverage_manifest["summary"][
            "records_sha256"
        ]:
            raise RuntimeError("market coverage records fingerprint mismatch")
        coverage_by_ticker = {
            str(record["ticker"]): record for record in coverage_records
        }
        if len(coverage_by_ticker) != len(coverage_records):
            raise RuntimeError("market coverage contains duplicate tickers")
        if set(coverage_by_ticker) != set(groups):
            raise RuntimeError("market coverage does not match census tickers")

        decisions = [
            classify_ticker_group(
                groups[ticker],
                coverage_by_ticker[ticker],
                policy=policy,
            )
            for ticker in sorted(groups)
        ]
        summary = summarize_decisions(decisions)
        manifest = build_date_manifest(
            trading_date=value,
            census_manifest=census_manifest,
            metadata_manifest=metadata_manifest,
            coverage_manifest=coverage_manifest,
            summary=summary,
        )
        if not manifest["eligibility"]["complete_relative_to_census"]:
            raise RuntimeError("provisional universe did not decide every census ticker")
        _write_decisions(output_root / f"{value}.csv", decisions)
        _write_json(output_root / f"{value}.json", manifest)
        _write_json(
            output_root / f"{value}-included.json",
            {
                "schema_version": 1,
                "trading_date": value,
                "policy_fingerprint": policy.fingerprint,
                "membership_sha256": summary["included_membership_sha256"],
                "rows": [
                    decision.payload() for decision in decisions if decision.included
                ],
            },
        )
        date_manifests.append(manifest)

    output_manifest = {
        "schema_version": 1,
        "dates": root_manifest["dates"],
        "universe_policy": historical_universe_v0_1_manifest(),
        "date_manifests": date_manifests,
        "complete_relative_to_census": all(
            manifest["eligibility"]["complete_relative_to_census"]
            for manifest in date_manifests
        ),
        "universe_complete": False,
        "full_walk_forward_eligible": False,
        "policy_promotion_eligible": False,
        "knowledge_policy": (
            "provider_metadata_and_coverage_only_no_benchmark_labels_no_strategy_feedback"
        ),
    }
    _write_json(output_root / "manifest.json", output_manifest)
    print(
        json.dumps(
            {
                "dates": root_manifest["dates"],
                "included_ticker_counts": {
                    manifest["trading_date"]: manifest["summary"][
                        "included_ticker_count"
                    ]
                    for manifest in date_manifests
                },
                "complete_relative_to_census": output_manifest[
                    "complete_relative_to_census"
                ],
                "universe_complete": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
