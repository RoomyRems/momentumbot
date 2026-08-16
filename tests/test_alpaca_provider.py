import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

import pandas as pd

from momentumbot.providers.alpaca import AlpacaDataClient


class AlpacaProviderTests(unittest.TestCase):
    def test_batched_bars_quarantines_only_named_invalid_symbol_and_retries(self):
        client = AlpacaDataClient("key", "secret")
        calls = []

        def fake_bars(symbols, **kwargs):
            names = list(symbols)
            calls.append(names)
            if "B002455" in names:
                raise RuntimeError('HTTP 400 for provider request: {"message":"invalid symbol: B002455"}')
            return {symbol: pd.DataFrame() for symbol in names}

        with patch.object(client, "bars", side_effect=fake_bars):
            result = client.bars_batched(["AAPL", "B002455", "MSFT"], batch_size=3)

        self.assertEqual(calls, [["AAPL", "B002455", "MSFT"], ["AAPL", "MSFT"]])
        self.assertEqual(set(result), {"AAPL", "MSFT"})
        self.assertEqual(client.invalid_symbols, {"B002455"})

    def test_batched_bars_does_not_swallow_unrelated_provider_error(self):
        client = AlpacaDataClient("key", "secret")
        with patch.object(client, "bars", side_effect=RuntimeError("HTTP 429 rate limit")):
            with self.assertRaisesRegex(RuntimeError, "429"):
                client.bars_batched(["AAPL"])

    def test_corporate_actions_paginates_grouped_response(self):
        client = AlpacaDataClient("key", "secret")
        payloads = [
            {
                "corporate_actions": {
                    "reverse_splits": [
                        {
                            "id": "split-1",
                            "initiating_symbol": "AAA",
                            "process_date": "2025-04-02",
                        }
                    ],
                    "name_changes": [],
                },
                "next_page_token": "next-token",
            },
            {
                "corporate_actions": {
                    "name_changes": [
                        {
                            "id": "name-1",
                            "old_symbol": "BBB",
                            "new_symbol": "CCC",
                        }
                    ]
                },
                "next_page_token": None,
            },
        ]
        calls = []

        def fake_get(url, **_kwargs):
            calls.append(url)
            return payloads.pop(0)

        with patch("momentumbot.providers.alpaca.get_json", side_effect=fake_get):
            result = client.corporate_actions(
                start=date(2025, 1, 1),
                end=date(2025, 4, 3),
                types=("reverse_split", "name_change"),
            )

        self.assertEqual([page.row_count for page in result.pages], [1, 1])
        self.assertEqual({row["id"] for row in result.rows}, {"split-1", "name-1"})
        self.assertEqual(
            {row["action_type"] for row in result.rows},
            {"reverse_splits", "name_changes"},
        )
        self.assertNotIn("symbols", result.query)
        self.assertIn("page_token=next-token", calls[1])

    def test_corporate_actions_rejects_repeated_page_token(self):
        client = AlpacaDataClient("key", "secret")
        with patch(
            "momentumbot.providers.alpaca.get_json",
            return_value={
                "corporate_actions": {},
                "next_page_token": "same",
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "token repeated"):
                client.corporate_actions(
                    start=date(2025, 1, 1),
                    end=date(2025, 4, 3),
                )

    def test_news_exhausts_pagination(self):
        client = AlpacaDataClient("key", "secret")
        payloads = [
            {
                "news": [{"id": 1, "symbols": ["AAA"]}],
                "next_page_token": "next-token",
            },
            {
                "news": [{"id": 2, "symbols": ["AAA"]}],
                "next_page_token": None,
            },
        ]
        calls = []

        def fake_get(url, **_kwargs):
            calls.append(url)
            return payloads.pop(0)

        with patch("momentumbot.providers.alpaca.get_json", side_effect=fake_get):
            rows = client.news(
                ["AAA"],
                start=datetime(2025, 4, 2, tzinfo=timezone.utc),
                end=datetime(2025, 4, 3, tzinfo=timezone.utc),
            )

        self.assertEqual([row["id"] for row in rows], [1, 2])
        self.assertIn("page_token=next-token", calls[1])

    def test_news_rejects_unbounded_unique_pagination(self):
        client = AlpacaDataClient("key", "secret")
        responses = [
            {"news": [], "next_page_token": "one"},
            {"news": [], "next_page_token": "two"},
        ]
        with patch(
            "momentumbot.providers.alpaca.get_json",
            side_effect=responses,
        ):
            with self.assertRaisesRegex(RuntimeError, "exceeded max_pages"):
                client.news(
                    ["AAA"],
                    start=datetime(2025, 4, 2, tzinfo=timezone.utc),
                    end=datetime(2025, 4, 3, tzinfo=timezone.utc),
                    max_pages=2,
                )


if __name__ == "__main__":
    unittest.main()
