import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.providers.alpaca_trades import historical_trades


class AlpacaTradesProviderTests(unittest.TestCase):
    def test_historical_trades_paginates_and_normalizes(self):
        client = AlpacaDataClient("key", "secret")
        pages = [
            {
                "trades": [{"t":"2026-07-09T11:32:01Z","p":6.0,"s":100,"x":"Q","c":["@"],"i":1,"z":"C"}],
                "next_page_token": "next",
            },
            {
                "trades": [{"t":"2026-07-09T11:32:02Z","p":6.1,"s":200,"x":"Q","c":["@"],"i":2,"z":"C"}],
                "next_page_token": None,
            },
        ]
        with patch("momentumbot.providers.alpaca_trades.get_json", side_effect=pages) as mocked:
            frame = historical_trades(
                client,
                "VRAX",
                start=datetime(2026, 7, 9, 11, 32, tzinfo=timezone.utc),
                end=datetime(2026, 7, 9, 11, 33, tzinfo=timezone.utc),
                asof="2026-07-09",
            )
        self.assertEqual(len(frame), 2)
        self.assertEqual(frame.iloc[0]["conditions"], ("@",))
        self.assertEqual(int(frame.iloc[1]["size"]), 200)
        self.assertEqual(mocked.call_count, 2)
        self.assertIn("page_token=next", mocked.call_args_list[1].args[0])

    def test_naive_bounds_are_rejected(self):
        client = AlpacaDataClient("key", "secret")
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            historical_trades(
                client,
                "VRAX",
                start=datetime(2026, 7, 9, 11, 32),
                end=datetime(2026, 7, 9, 11, 33),
            )


if __name__ == "__main__":
    unittest.main()
