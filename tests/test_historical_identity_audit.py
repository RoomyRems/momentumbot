from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from scripts.audit_historical_identity_continuity import (
    extract_symbol_values,
    summarize_alpaca_actions,
    validate_alias_transitions,
)


def _frame(target: date, *, close: float) -> pd.DataFrame:
    index = pd.DatetimeIndex(
        [f"{target.isoformat()}T20:00:00Z"],
        name="timestamp",
    )
    return pd.DataFrame(
        [
            {
                "open": close - 0.1,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "volume": 1000,
                "trade_count": 25,
                "vwap": close,
            }
        ],
        index=index,
    )


class _AliasClient:
    def bars_batched(self, symbols, **kwargs):
        target = date.fromisoformat(str(kwargs["start"])[:10])
        # The request begins seven days before the comparison date.
        target = target.fromordinal(target.toordinal() + 7)
        close = 10.0 if target == date(2025, 4, 3) else 20.0
        return {symbol: _frame(target, close=close) for symbol in symbols}


class HistoricalIdentityAuditTests(unittest.TestCase):
    def test_alias_validation_requires_matching_bars_in_both_directions(self) -> None:
        result = validate_alias_transitions(
            _AliasClient(),
            [
                {
                    "identifier_kind": "composite_figi",
                    "identifier": "FIGI-1",
                    "earlier_ticker": "OLD",
                    "later_ticker": "NEW",
                    "ticker_changed": True,
                    "symbol_reuse_involved": False,
                }
            ],
            earlier_date=date(2025, 4, 3),
            later_date=date(2026, 7, 9),
            batch_size=100,
        )

        self.assertTrue(result["records"][0]["bidirectional_match"])
        self.assertTrue(result["summary"]["exact_figi_alias_validation_complete"])

    def test_recursive_symbol_extraction_and_relevance_filter(self) -> None:
        action = {
            "action_type": "name_changes",
            "id": "event-1",
            "old_symbol": "OLD",
            "details": {"new_ticker": "NEW", "description": "not-a-symbol"},
        }

        symbols = extract_symbol_values(action)
        self.assertEqual(
            {row["symbol"] for row in symbols},
            {"OLD", "NEW"},
        )
        summary = summarize_alpaca_actions([action], relevant_symbols={"NEW"})
        self.assertEqual(summary["relevant_action_count"], 1)
        self.assertEqual(summary["relevant_actions"][0]["matched_symbols"], ["NEW"])


if __name__ == "__main__":
    unittest.main()

