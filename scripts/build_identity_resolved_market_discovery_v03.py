from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date
import json
from pathlib import Path

import pandas as pd

from momentumbot.causal_market_discovery_v03 import (
    CAUSAL_MARKET_CANDIDATES_ARTIFACT_ID,
    CAUSAL_MARKET_CANDIDATES_V0_3_ARTIFACT_ID,
    CAUSAL_MARKET_DISCOVERY_POLICY_ID,
    CAUSAL_MARKET_DISCOVERY_V0_3_POLICY_ID,
    build_causal_market_discovery_manifest,
    build_market_candidate_payload,
    causal_market_discovery_v0_2_manifest,
    causal_market_discovery_v0_3_manifest,
    identity_membership_as_acquisition_assets,
)
from momentumbot.historical_data_v03 import (
    LEGACY_MIXED_GAIN_BASIS,
    SPLIT_CONSISTENT_GAIN_BASIS,
    discover_market_day,
)
from momentumbot.identity_resolved_universe import (
    json_fingerprint,
    load_identity_resolved_universe,
)
from momentumbot.models import current_general_2026
from momentumbot.providers.alpaca import AlpacaDataClient


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--census-root", type=Path, required=True)
    parser.add_argument("--dates", nargs="+")
    parser.add_argument("--asset-batch-size", type=int, default=250)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--gain-basis",
        choices=(LEGACY_MIXED_GAIN_BASIS, SPLIT_CONSISTENT_GAIN_BASIS),
        default=LEGACY_MIXED_GAIN_BASIS,
    )
    args = parser.parse_args(argv)
    if args.asset_batch_size <= 0:
        raise ValueError("asset batch size must be positive")

    membership_root = args.census_root / "identity-resolved-universe-v0.1"
    membership_manifest = json.loads(
        (membership_root / "manifest.json").read_text(encoding="utf-8")
    )
    dates = args.dates or membership_manifest.get("dates")
    if not isinstance(dates, list) or not dates:
        raise ValueError("at least one discovery date is required")
    if len(dates) != len(set(dates)):
        raise ValueError("discovery dates must be unique")

    normalized = args.gain_basis == SPLIT_CONSISTENT_GAIN_BASIS
    policy = (
        causal_market_discovery_v0_3_manifest()
        if normalized
        else causal_market_discovery_v0_2_manifest()
    )
    policy_id = (
        CAUSAL_MARKET_DISCOVERY_V0_3_POLICY_ID
        if normalized
        else CAUSAL_MARKET_DISCOVERY_POLICY_ID
    )
    candidate_artifact_id = (
        CAUSAL_MARKET_CANDIDATES_V0_3_ARTIFACT_ID
        if normalized
        else CAUSAL_MARKET_CANDIDATES_ARTIFACT_ID
    )
    output_root = args.output or args.census_root / policy_id
    output_root.mkdir(parents=True, exist_ok=False)
    profile = current_general_2026()
    alpaca = AlpacaDataClient.from_env()
    date_manifests: list[dict[str, object]] = []
    for value in dates:
        trading_date = date.fromisoformat(value)
        rows, membership_payload, verified_membership_manifest = (
            load_identity_resolved_universe(
                membership_root,
                trading_date=value,
            )
        )
        assets = identity_membership_as_acquisition_assets(rows)
        result = discover_market_day(
            alpaca,
            trading_date=trading_date,
            profile=profile,
            asset_batch_size=args.asset_batch_size,
            assets=assets,
            gain_basis=args.gain_basis,
        )
        manifest = build_causal_market_discovery_manifest(
            trading_date=value,
            membership_rows=rows,
            membership_payload=membership_payload,
            membership_bundle_manifest=verified_membership_manifest,
            result=result,
            profile=profile,
            discovery_policy=policy,
            candidate_artifact_id=candidate_artifact_id,
        )
        date_root = output_root / value
        date_root.mkdir()
        pd.DataFrame([asdict(row) for row in result.rows]).to_csv(
            date_root / "discovery.csv",
            index=False,
        )
        pd.DataFrame([asdict(row) for row in result.acquisition_audit]).to_csv(
            date_root / "acquisition-audit.csv",
            index=False,
        )
        _write_json(
            date_root / "identity-resolved-membership.json",
            membership_payload,
        )
        candidate_payload = build_market_candidate_payload(
            trading_date=value,
            membership_rows=rows,
            result=result,
            discovery_policy=policy,
            candidate_artifact_id=candidate_artifact_id,
        )
        if candidate_payload["content_sha256"] != manifest["summary"][
            "causal_market_candidate_set_sha256"
        ]:
            raise RuntimeError("market candidate payload fingerprint mismatch")
        _write_json(date_root / "market-candidates.json", candidate_payload)
        manifest["files"] = {
            "discovery_records": "discovery.csv",
            "acquisition_audit": "acquisition-audit.csv",
            "identity_resolved_membership": "identity-resolved-membership.json",
            "market_candidates": "market-candidates.json",
        }
        _write_json(date_root / "manifest.json", manifest)
        date_manifests.append(manifest)

    root_manifest = {
        "schema_version": 2,
        "artifact_id": policy_id,
        "dates": dates,
        "discovery_policy": policy,
        "source_membership_bundle_sha256": membership_manifest["content_sha256"],
        "date_manifests": date_manifests,
        "eligibility": {
            "causal_market_discovery_complete": all(
                manifest["eligibility"]["causal_market_discovery_complete"]
                for manifest in date_manifests
            ),
            "full_feature_snapshot_complete": False,
            "universe_complete": False,
            "full_walk_forward_eligible": False,
            "policy_promotion_eligible": False,
        },
        "knowledge_policy": {
            "uses_benchmark_labels": False,
            "uses_retrospective_trade_outcomes": False,
            "selection_applied": False,
        },
    }
    root_manifest["content_sha256"] = json_fingerprint(
        {
            "discovery_policy": root_manifest["discovery_policy"],
            "source_membership_bundle_sha256": root_manifest[
                "source_membership_bundle_sha256"
            ],
            "date_manifests": date_manifests,
        }
    )
    _write_json(output_root / "manifest.json", root_manifest)
    print(
        json.dumps(
            {
                "artifact_id": policy_id,
                "dates": dates,
                "daily_price_superset_counts": {
                    manifest["trading_date"]: manifest["summary"][
                        "daily_price_superset_count"
                    ]
                    for manifest in date_manifests
                },
                "causal_market_candidate_counts": {
                    manifest["trading_date"]: manifest["summary"][
                        "causal_market_candidate_count"
                    ]
                    for manifest in date_manifests
                },
                "full_feature_snapshot_complete": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
