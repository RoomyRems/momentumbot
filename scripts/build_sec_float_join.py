from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pandas as pd

from momentumbot.historical_float import (
    BasisObservation,
    FloatJoinRow,
    estimate_float_row as _estimate_row,
    normalize_shares as _normalize_shares,
    observe_basis as _observe_basis,
)
from momentumbot.providers.alpaca import AlpacaDataClient

def _download_basis(
    client: AlpacaDataClient,
    symbol: str,
    dates: list[date],
    *,
    trading_date: date,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not dates:
        return pd.DataFrame(), pd.DataFrame()
    start_date = min(dates) - timedelta(days=14)
    end_date = max(dates) + timedelta(days=15)
    start = datetime.combine(start_date, time(0), timezone.utc)
    end = datetime.combine(end_date, time(0), timezone.utc)
    raw = client.bars(
        [symbol], timeframe="1Day", start=start, end=end, feed="sip",
        adjustment="raw", asof=trading_date,
    ).get(symbol, pd.DataFrame())
    split = client.bars(
        [symbol], timeframe="1Day", start=start, end=end, feed="sip",
        adjustment="split", asof=trading_date,
    ).get(symbol, pd.DataFrame())
    return raw, split


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="research/reference_days/2026-07-09/sec_float_compact.json")
    parser.add_argument("--output", default="sec-float-join-artifact")
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    trading_date = date.fromisoformat(payload["trading_date"])
    client = AlpacaDataClient.from_env()
    rows: list[FloatJoinRow] = []
    basis_audit: dict[str, dict[str, dict]] = {}

    for candidate in payload["candidates"]:
        symbol = candidate["symbol"]
        tagged_dates: list[tuple[str, date]] = []
        for tag, key in (("public", "public_float"), ("anchor", "anchor_outstanding"), ("current", "current_outstanding")):
            disclosure = candidate.get(key)
            if disclosure:
                tagged_dates.append((tag, date.fromisoformat(disclosure["measure_date"])))
        raw, split = _download_basis(client, symbol, [d for _, d in tagged_dates], trading_date=trading_date)
        observations: dict[str, BasisObservation] = {}
        for tag, requested in tagged_dates:
            observation = _observe_basis(raw, split, requested)
            observations[f"{tag}:{requested.isoformat()}"] = observation
        basis_audit[symbol] = {key: asdict(value) for key, value in observations.items()}
        rows.append(_estimate_row(candidate, observations))

    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([asdict(row) | {"notes": "; ".join(row.notes)} for row in rows])
    frame.to_csv(root / "float_estimates.csv", index=False)
    (root / "basis_audit.json").write_text(json.dumps(basis_audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "trading_date": trading_date.isoformat(),
        "candidate_count": len(rows),
        "float_pass_count": sum(row.float_pillar_pass is True for row in rows),
        "float_fail_count": sum(row.float_pillar_pass is False for row in rows),
        "float_unknown_count": sum(row.float_pillar_pass is None for row in rows),
        "methods": {row.symbol: row.method for row in rows},
        "notes": [
            "Public float is converted from SEC dollars using Alpaca split-adjusted historical close as of the test date.",
            "Outstanding-share disclosures are normalized to the test-date share basis using raw/split price ratios before roll-forward.",
            "Normalized total common shares below the threshold are used as a deterministic upper bound on float.",
            "Names without sufficient SEC evidence remain unknown and fail closed until manually resolved.",
        ],
    }
    (root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(frame.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
