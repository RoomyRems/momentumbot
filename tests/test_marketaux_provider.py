import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from momentumbot.providers.marketaux import _marketaux_timestamp


class MarketAuxProviderTests(unittest.TestCase):
    def test_timestamp_is_converted_to_utc_without_offset_suffix(self):
        eastern = ZoneInfo("America/New_York")
        value = datetime(2026, 7, 9, 10, 1, tzinfo=eastern)
        self.assertEqual(_marketaux_timestamp(value), "2026-07-09T14:01:00")

    def test_naive_timestamp_is_rejected(self):
        with self.assertRaises(ValueError):
            _marketaux_timestamp(datetime(2026, 7, 9, 10, 1))


if __name__ == "__main__":
    unittest.main()
