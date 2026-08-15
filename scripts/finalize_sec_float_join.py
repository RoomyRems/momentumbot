from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

FLOAT_LIMIT = 10_000_000


def _latest_available_at(candidate: dict) -> str | None:
    values = []
    for key in ("public_float", "anchor_outstanding", "current_outstanding"):
        disclosure = candidate.get(key)
        if disclosure and disclosure.get("available_at"):
            values.append(str(disclosure["available_at"]))
    return max(values) if values else None


def apply_manual_overrides(
    frame: pd.DataFrame,
    *,
    compact: dict,
    manual: dict,
) -> pd.DataFrame:
    output = frame.copy()
    candidates = {row["symbol"]: row for row in compact["candidates"]}
    output["float_asof"] = output["symbol"].map(
        lambda symbol: _latest_available_at(candidates.get(str(symbol), {}))
    )
    output["classification_source"] = "sec_companyfacts_model"
    output["bound_type"] = pd.NA

    for symbol, override in manual.get("overrides", {}).items():
        mask = output["symbol"].astype(str) == symbol
        if not mask.any():
            raise ValueError(f"manual float override references missing symbol: {symbol}")
        passed = override.get("float_pillar_pass")
        bound = override.get("bound_shares")
        if passed is True and (bound is None or int(bound) >= FLOAT_LIMIT):
            raise ValueError(f"passing override must prove an upper bound below 10M: {symbol}")
        if passed is False and (bound is None or int(bound) <= FLOAT_LIMIT):
            raise ValueError(f"failing override must prove a lower bound above 10M: {symbol}")
        if passed is None and bound is not None:
            raise ValueError(f"unknown override cannot claim a deterministic bound: {symbol}")

        output.loc[mask, "method"] = str(override["method"])
        output.loc[mask, "estimated_float_shares"] = (
            pd.NA if bound is None else int(bound)
        )
        output.loc[mask, "current_outstanding_target_basis"] = output.loc[
            mask, "current_outstanding_target_basis"
        ]
        output.loc[mask, "float_pillar_pass"] = passed
        output.loc[mask, "float_asof"] = override.get("available_at")
        output.loc[mask, "classification_source"] = "sec_manual_filing_resolution"
        output.loc[mask, "bound_type"] = override.get("bound_type")
        existing = str(output.loc[mask, "notes"].iloc[0] or "").strip()
        manual_note = str(override.get("notes") or "").strip()
        output.loc[mask, "notes"] = "; ".join(
            value for value in (existing, manual_note) if value
        )

    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--join-dir", default="sec-float-join-artifact")
    parser.add_argument(
        "--compact",
        default="research/reference_days/2026-07-09/sec_float_compact.json",
    )
    parser.add_argument(
        "--manual",
        default="research/reference_days/2026-07-09/sec_float_manual_overrides.json",
    )
    args = parser.parse_args()

    root = Path(args.join_dir)
    frame = pd.read_csv(root / "float_estimates.csv")
    compact = json.loads(Path(args.compact).read_text(encoding="utf-8"))
    manual = json.loads(Path(args.manual).read_text(encoding="utf-8"))
    final = apply_manual_overrides(frame, compact=compact, manual=manual)
    final.to_csv(root / "final_float_estimates.csv", index=False)

    passed = final["float_pillar_pass"].eq(True)
    failed = final["float_pillar_pass"].eq(False)
    unknown = ~(passed | failed)
    summary = {
        "trading_date": compact["trading_date"],
        "candidate_count": int(len(final)),
        "float_pass_count": int(passed.sum()),
        "float_fail_count": int(failed.sum()),
        "float_unknown_count": int(unknown.sum()),
        "pass_symbols": sorted(final.loc[passed, "symbol"].astype(str).tolist()),
        "fail_symbols": sorted(final.loc[failed, "symbol"].astype(str).tolist()),
        "unknown_symbols": sorted(final.loc[unknown, "symbol"].astype(str).tolist()),
        "manual_resolution_symbols": sorted(manual.get("overrides", {})),
        "methodology": manual.get("methodology", []),
    }
    (root / "final_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
