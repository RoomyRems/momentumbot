import unittest
from datetime import date, datetime, timezone

from momentumbot.historical_data import estimate_float_from_facts
from momentumbot.providers.sec_api import parse_float_response


class ProviderParserTests(unittest.TestCase):
    def test_sec_api_parser_sums_share_classes_and_preserves_public_float_dollars(self):
        payload = {
            "data": [
                {
                    "tickers": ["TEST"],
                    "cik": "1234",
                    "reportedAt": "2025-02-15T10:00:00-05:00",
                    "periodOfReport": "2024-12-31",
                    "sourceFilingAccessionNo": "0001",
                    "float": {
                        "outstandingShares": [
                            {"period": "2025-02-01", "shareClass": "A", "value": 6_000_000},
                            {"period": "2025-02-01", "shareClass": "B", "value": 1_000_000},
                        ],
                        "publicFloat": [
                            {"period": "2024-06-30", "shareClass": "", "value": 12_000_000}
                        ],
                    },
                }
            ]
        }
        parsed = parse_float_response(payload)
        self.assertEqual(parsed.outstanding_shares[0].shares, 7_000_000)
        self.assertEqual(parsed.public_float[0].public_float_usd, 12_000_000)
        self.assertEqual(parsed.public_float[0].available_at, datetime(2025, 2, 15, 15, tzinfo=timezone.utc))

    def test_float_estimate_is_unavailable_before_filing(self):
        payload = {
            "data": [
                {
                    "cik": "1234",
                    "reportedAt": "2025-02-15T10:00:00-05:00",
                    "sourceFilingAccessionNo": "0001",
                    "float": {
                        "outstandingShares": [{"period": "2025-02-01", "value": 7_000_000}],
                        "publicFloat": [{"period": "2024-06-30", "value": 12_000_000}],
                    },
                }
            ]
        }
        parsed = parse_float_response(payload)
        estimate = estimate_float_from_facts(
            parsed,
            as_of=datetime(2025, 2, 14, tzinfo=timezone.utc),
            price_lookup=lambda _: 2.0,
        )
        self.assertIsNone(estimate)

    def test_float_estimate_uses_historical_price(self):
        payload = {
            "data": [
                {
                    "cik": "1234",
                    "reportedAt": "2025-02-15T10:00:00-05:00",
                    "sourceFilingAccessionNo": "0001",
                    "float": {
                        "outstandingShares": [{"period": "2024-06-29", "value": 8_000_000}],
                        "publicFloat": [{"period": "2024-06-30", "value": 12_000_000}],
                    },
                }
            ]
        }
        parsed = parse_float_response(payload)
        estimate = estimate_float_from_facts(
            parsed,
            as_of=datetime(2025, 2, 16, tzinfo=timezone.utc),
            price_lookup=lambda day: 2.0 if day == date(2024, 6, 30) else 99.0,
        )
        self.assertEqual(estimate.value_shares, 6_000_000)
