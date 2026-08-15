import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from momentumbot.providers.marketaux import (
    _marketaux_response_timestamp,
    _marketaux_timestamp,
)


class MarketAuxProviderTests(unittest.TestCase):
    def test_timestamp_is_converted_to_utc_without_offset_suffix(self):
        eastern = ZoneInfo("America/New_York")
        value = datetime(2026, 7, 9, 10, 1, tzinfo=eastern)
        self.assertEqual(_marketaux_timestamp(value), "2026-07-09T14:01:00")

    def test_naive_timestamp_is_rejected(self):
        with self.assertRaises(ValueError):
            _marketaux_timestamp(datetime(2026, 7, 9, 10, 1))

    def test_naive_response_timestamp_is_interpreted_as_documented_utc(self):
        self.assertEqual(
            _marketaux_response_timestamp("2026-07-09T12:34:56"),
            "2026-07-09T12:34:56+00:00",
        )

    def test_offset_response_timestamp_is_normalized_to_utc(self):
        self.assertEqual(
            _marketaux_response_timestamp("2026-07-09T08:34:56-04:00"),
            "2026-07-09T12:34:56+00:00",
        )


if __name__ == "__main__":
    unittest.main()
