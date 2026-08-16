from __future__ import annotations

import argparse
import json

from .backtest import Backtester
from .models import current_general_2026, current_small_account_2026, paper_safe_risk
from .snapshot import load_snapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="momentumbot")
    subparsers = parser.add_subparsers(dest="command", required=True)
    backtest = subparsers.add_parser("backtest", help="Replay one frozen deterministic snapshot")
    backtest.add_argument(
        "snapshot",
        help="Path containing manifest.json, contexts.csv, bars/, news.csv",
    )
    backtest.add_argument(
        "--profile",
        choices=("general-2026", "small-account-2026"),
        default="general-2026",
    )
    backtest.add_argument("--starting-equity", type=float, default=100_000.0)
    backtest.add_argument(
        "--allow-conditional-universe",
        action="store_true",
        help=(
            "allow a diagnostic snapshot that is complete only relative to a "
            "frozen current asset master; never use its result for policy promotion"
        ),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "backtest":
        bars, contexts, news_events, manifest = load_snapshot(
            args.snapshot,
            allow_conditional_universe=args.allow_conditional_universe,
        )
        profile = (
            current_general_2026()
            if args.profile == "general-2026"
            else current_small_account_2026()
        )
        result = Backtester(profile, paper_safe_risk()).run_day(
            bars,
            contexts,
            news_events,
            starting_equity=args.starting_equity,
        )
        print(
            json.dumps(
                {
                    "snapshot": manifest.get("snapshot_id"),
                    "profile": profile.name,
                    "risk_policy": paper_safe_risk().name,
                    "universe_scope": (
                        "point_in_time"
                        if manifest.get("universe_complete", False)
                        else "conditional_current_asset_master"
                    ),
                    "policy_promotion_eligible": bool(
                        manifest.get("evaluation_eligibility", {}).get(
                            "policy_promotion",
                            manifest.get("universe_complete", False),
                        )
                    ),
                    "trades": len(result.trades),
                    "candidate_events": result.candidate_events,
                    "plan_events": result.plan_events,
                    "rejected_for_fill_slippage": result.rejected_for_fill_slippage,
                    "session_locked": result.session_locked,
                    "session_lock_reason": result.session_lock_reason,
                    "pnl_dollars": round(result.pnl_dollars, 2),
                    "total_r": round(result.total_r, 3),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
