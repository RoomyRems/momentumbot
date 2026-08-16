from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

DESIGN_TYPE = "micro_volume_activity_cohort_design"
DESIGN_STATUS = "precommitted_before_market_discovery"
DISCOVERY_KNOWLEDGE_POLICY = "market_data_only_no_retrospective_behavior_labels"
SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_design(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("artifact_type") != DESIGN_TYPE:
        raise ValueError("unexpected activity-cohort design artifact type")
    if payload.get("status") != DESIGN_STATUS:
        raise ValueError("activity-cohort design was not precommitted")
    if payload.get("knowledge_policy") != DISCOVERY_KNOWLEDGE_POLICY:
        raise ValueError("activity-cohort design permits retrospective labels")
    dates = payload.get("trading_dates")
    if not isinstance(dates, list) or not dates or len(set(dates)) != len(dates):
        raise ValueError("activity-cohort trading_dates must be a unique nonempty list")
    count = payload.get("candidates_per_date")
    if not isinstance(count, int) or count < 1:
        raise ValueError("candidates_per_date must be a positive integer")
    expected_cells = {
        "baseline",
        "context_only",
        "volume_only",
        "context_plus_volume",
    }
    if set(payload.get("factorial_cells") or []) != expected_cells:
        raise ValueError("activity-cohort design does not contain the frozen four cells")
    return payload


def _qualified_rows(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"symbol", "previous_close", "first_market_qualified_at"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"discovery file missing columns: {sorted(missing)}")
    available = frame.loc[
        frame["first_market_qualified_at"].notna()
        & frame["first_market_qualified_at"].astype(str).str.strip().ne("")
    ].copy()
    if available.empty:
        return available
    available["symbol"] = available["symbol"].astype(str).str.upper().str.strip()
    invalid = sorted(
        symbol for symbol in available["symbol"] if not SYMBOL_PATTERN.fullmatch(symbol)
    )
    if invalid:
        raise ValueError(f"invalid symbols in discovery: {invalid}")
    available["_qualified_at"] = pd.to_datetime(
        available["first_market_qualified_at"], utc=True, errors="raise"
    )
    return available.sort_values(["_qualified_at", "symbol"], kind="stable")


def build_selection(design_path: Path, discovery_root: Path) -> dict[str, object]:
    design = _load_design(design_path)
    count = int(design["candidates_per_date"])
    cases: list[dict[str, object]] = []
    date_summaries: list[dict[str, object]] = []

    for trading_date in design["trading_dates"]:
        date_text = str(trading_date)
        discovery_path = discovery_root / date_text / "discovery.csv"
        manifest_path = discovery_root / date_text / "manifest.json"
        if not discovery_path.exists() or not manifest_path.exists():
            raise FileNotFoundError(f"missing discovery artifact for {date_text}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("kind") != "market_day_discovery":
            raise ValueError(f"unexpected discovery manifest for {date_text}")
        if manifest.get("trading_date") != date_text:
            raise ValueError(f"discovery date mismatch for {date_text}")

        qualified = _qualified_rows(discovery_path)
        selected = qualified.head(count)
        date_summaries.append(
            {
                "trading_date": date_text,
                "causally_qualified_count": len(qualified),
                "selected_count": len(selected),
                "discovery_sha256": _sha256(discovery_path),
            }
        )
        for selection_rank, row in enumerate(
            selected.to_dict(orient="records"), start=1
        ):
            symbol = str(row["symbol"])
            safe_symbol = re.sub(r"[^a-z0-9]+", "-", symbol.lower()).strip("-")
            cases.append(
                {
                    "case_id": f"{date_text}-{safe_symbol}-q{selection_rank}",
                    "trading_date": date_text,
                    "symbol": symbol,
                    "selection_rank_within_date": selection_rank,
                    "first_market_qualified_at": pd.Timestamp(
                        row["_qualified_at"]
                    ).isoformat(),
                    "previous_close": float(row["previous_close"]),
                    "selection_features": [
                        "first_market_qualified_at",
                        "symbol_tie_break"
                    ],
                }
            )

    if not cases:
        raise ValueError("precommitted dates produced no causally qualified candidates")
    matrix = {
        "include": [
            {
                "case_id": case["case_id"],
                "symbol": case["symbol"],
                "trading_date": case["trading_date"],
            }
            for case in cases
        ]
    }
    return {
        "artifact_type": "micro_volume_activity_cohort_selection",
        "schema_version": 1,
        "design_id": design["design_id"],
        "design_sha256": _sha256(design_path),
        "knowledge_policy": "runtime_market_data_only_no_retrospective_labels",
        "selection_status": "label_blind_market_discovery_complete",
        "strategy_feedback": "activity_stress_only",
        "policy_promotion_eligible": False,
        "candidate_selection_rule": design["candidate_selection_rule"],
        "selection_columns_used": [
            "first_market_qualified_at",
            "symbol"
        ],
        "selection_columns_prohibited": [
            "target_high",
            "max_session_gain_pct",
            "max_session_rvol_upper_bound",
            "max_session_rvol",
            "any_micro_replay_output",
            "any_retrospective_behavior_label"
        ],
        "date_summaries": date_summaries,
        "cases": cases,
        "matrix": matrix,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--discovery-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = build_selection(args.design, args.discovery_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
