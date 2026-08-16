from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from momentumbot.historical_data import discover_market_day, write_discovery
from momentumbot.models import current_general_2026
from momentumbot.providers.alpaca import AlpacaDataClient


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build one label-blind market-day discovery artifact for the precommitted "
            "Micro volume activity cohort."
        )
    )
    parser.add_argument("--trading-date", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    trading_date = date.fromisoformat(args.trading_date)
    profile = current_general_2026()
    result = discover_market_day(
        AlpacaDataClient.from_env(),
        trading_date=trading_date,
        profile=profile,
    )
    output = args.output_root / trading_date.isoformat()
    write_discovery(result, output, trading_date=trading_date)

    payload = {
        "artifact_type": "micro_volume_activity_cohort_day_discovery",
        "schema_version": 1,
        "trading_date": trading_date.isoformat(),
        "knowledge_policy": "runtime_market_data_only_no_retrospective_labels",
        "strategy_profile": profile.name,
        "asset_count": result.asset_count,
        "listed_asset_count": result.listed_asset_count,
        "daily_superset_count": result.daily_superset_count,
        "rvol_prefilter_count": result.rvol_prefilter_count,
        "market_candidate_count": result.market_candidate_count,
        "selection_applied": False,
        "notes": [
            "The full-day high is acquisition-only and is not exposed to selection or replay.",
            "Candidate selection occurs later using only first causal qualification time and symbol tie-break.",
            "Float, news, cross-sectional rank and retrospective behavior labels are absent."
        ],
    }
    (output / "day-summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
