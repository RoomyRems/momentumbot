from __future__ import annotations

import json
from datetime import date, timedelta

from momentumbot.providers.alpaca import AlpacaDataClient

CANDIDATES = [
    "ENLV", "VRAX", "JLHL", "RPGL", "WRAP", "TDTH", "NDRA", "SUNE",
    "AP", "SMPL", "MAAS", "PLBL", "SRXH", "PTLE", "HOUR",
]


def main() -> int:
    trading_date = date(2026, 7, 9)
    client = AlpacaDataClient.from_env()
    rows = client.corporate_actions(
        symbols=CANDIDATES,
        start=trading_date - timedelta(days=5),
        end=trading_date + timedelta(days=5),
        types="forward_split,reverse_split,name_change",
    )
    safe = []
    for row in rows:
        safe.append({key: value for key, value in row.items() if key not in {"cusip", "old_cusip", "new_cusip"}})
    print(json.dumps({"candidate_count": len(CANDIDATES), "actions": safe}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
