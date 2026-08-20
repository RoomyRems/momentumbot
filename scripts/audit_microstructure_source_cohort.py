from __future__ import annotations

import argparse
import json
from pathlib import Path

from momentumbot.research.microstructure_contract import (
    file_sha256,
    inspect_filled_micro_symbol_dates,
    select_activity_spread_smoke_cohort,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the frozen label-blind Micro runtime and derive the complete "
            "filled symbol-date cohort plus a deterministic activity-spread smoke sample."
        )
    )
    parser.add_argument("micro_zip", type=Path)
    args = parser.parse_args()

    rows = inspect_filled_micro_symbol_dates(args.micro_zip)
    payload = {
        "source_zip_sha256": file_sha256(args.micro_zip),
        "selection_rule": "every_symbol_date_with_filled_count_greater_than_zero",
        "retrospective_labels_used": False,
        "symbol_date_count": len(rows),
        "unique_symbol_count": len({row["symbol"] for row in rows}),
        "filled_symbol_dates": rows,
        "smoke_selection_rule": (
            "sort by causal SIP trade-row count, trading date, and symbol; select "
            "floor-spaced ranks 0, one-third, two-thirds, and last"
        ),
        "smoke_symbol_dates": select_activity_spread_smoke_cohort(rows),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
