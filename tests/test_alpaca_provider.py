import unittest
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


if __name__ == "__main__":
    unittest.main()
