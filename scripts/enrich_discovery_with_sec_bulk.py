from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from momentumbot.providers.sec_bulk import SecBulkArchives


def _serialize_fact(item) -> dict[str, object]:
    row = asdict(item)
    for key, value in tuple(row.items()):
        if hasattr(value, "isoformat"):
            row[key] = value.isoformat()
    return row


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enrich a MomentumBot discovery CSV using local SEC nightly bulk archives."
    )
    parser.add_argument("--discovery", type=Path, required=True)
    parser.add_argument("--companyfacts", type=Path, required=True)
    parser.add_argument("--submissions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    discovery = pd.read_csv(args.discovery)
    required = {"symbol", "first_market_qualified_at"}
    missing = required.difference(discovery.columns)
    if missing:
        raise ValueError(f"discovery CSV missing columns: {sorted(missing)}")

    candidates = sorted(
        {
            str(symbol).upper()
            for symbol in discovery.loc[
                discovery["first_market_qualified_at"].notna(), "symbol"
            ]
        }
    )
    archives = SecBulkArchives(args.companyfacts, args.submissions)
    args.output.mkdir(parents=True, exist_ok=True)

    facts_path = args.output / "sec-float-facts.jsonl"
    unresolved: list[dict[str, str]] = []
    resolved = 0
    with facts_path.open("w", encoding="utf-8") as handle:
        for symbol in candidates:
            cik = archives.cik_for_ticker(symbol)
            if cik is None:
                unresolved.append({"symbol": symbol, "reason": "ticker_not_in_submissions_bulk"})
                continue
            try:
                parsed = archives.parsed_companyfacts(cik)
            except KeyError as exc:
                unresolved.append({"symbol": symbol, "reason": str(exc)})
                continue
            payload = {
                "symbol": symbol,
                "cik": cik,
                "public_float": [_serialize_fact(item) for item in parsed.public_float],
                "outstanding_shares": [
                    _serialize_fact(item) for item in parsed.outstanding_shares
                ],
            }
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
            resolved += 1

    pd.DataFrame(unresolved, columns=["symbol", "reason"]).to_csv(
        args.output / "unresolved.csv", index=False
    )
    summary = {
        "candidate_symbols": len(candidates),
        "resolved_symbols": resolved,
        "unresolved_symbols": len(unresolved),
        "raw_sec_archives_committed": False,
        "facts_output": facts_path.name,
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
