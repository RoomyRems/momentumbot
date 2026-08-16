import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from momentumbot.providers.sec_edgar import (
    SecEdgarClient,
    implied_float_shares,
    latest_available,
    parse_companyfacts,
    parse_submission_acceptance_times,
    roll_forward_float,
)


class SecEdgarFloatTests(unittest.TestCase):
    def setUp(self):
        self.submissions = {
            "filings": {
                "recent": {
                    "accessionNumber": ["0001-25-000001", "0001-25-000002", "0001-25-000003"],
                    "acceptanceDateTime": [
                        "2025-03-01T14:00:00Z",
                        "2025-05-01T12:00:00Z",
                        "2025-08-01T12:00:00Z",
                    ],
                }
            }
        }
        self.companyfacts = {
            "cik": 1234,
            "facts": {
                "dei": {
                    "EntityPublicFloat": {
                        "units": {
                            "USD": [
                                {
                                    "end": "2024-06-28",
                                    "val": 24_000_000,
                                    "accn": "0001-25-000001",
                                    "form": "10-K",
                                    "filed": "2025-03-01",
                                }
                            ]
                        }
                    },
                    "EntityCommonStockSharesOutstanding": {
                        "units": {
                            "shares": [
                                {
                                    "end": "2025-02-20",
                                    "val": 12_000_000,
                                    "accn": "0001-25-000001",
                                    "form": "10-K",
                                    "filed": "2025-03-01",
                                },
                                {
                                    "end": "2025-04-25",
                                    "val": 15_000_000,
                                    "accn": "0001-25-000002",
                                    "form": "10-Q",
                                    "filed": "2025-05-01",
                                },
                                {
                                    "end": "2025-07-25",
                                    "val": 18_000_000,
                                    "accn": "0001-25-000003",
                                    "form": "10-Q",
                                    "filed": "2025-08-01",
                                },
                            ]
                        }
                    },
                }
            },
        }

    def test_acceptance_time_controls_information_availability(self):
        acceptance = parse_submission_acceptance_times(self.submissions)
        parsed = parse_companyfacts(self.companyfacts, acceptance_times=acceptance)
        before_filing = datetime(2025, 3, 1, 13, 59, tzinfo=timezone.utc)
        after_filing = datetime(2025, 3, 1, 14, 1, tzinfo=timezone.utc)
        self.assertIsNone(latest_available(parsed.public_float, before_filing))
        self.assertIsNotNone(latest_available(parsed.public_float, after_filing))

    def test_public_float_is_converted_from_dollars_to_implied_shares(self):
        acceptance = parse_submission_acceptance_times(self.submissions)
        disclosure = parse_companyfacts(
            self.companyfacts,
            acceptance_times=acceptance,
        ).public_float[0]
        estimate = implied_float_shares(disclosure, historical_price=3.0)
        self.assertEqual(estimate.value_shares, 8_000_000)
        self.assertEqual(estimate.public_float_usd, 24_000_000)
        self.assertEqual(estimate.price_used, 3.0)
        self.assertIn("historical_price", estimate.method)

    def test_roll_forward_raises_float_after_net_share_issuance(self):
        acceptance = parse_submission_acceptance_times(self.submissions)
        parsed = parse_companyfacts(self.companyfacts, acceptance_times=acceptance)
        anchor = implied_float_shares(parsed.public_float[0], historical_price=3.0)
        rolled = roll_forward_float(
            anchor,
            anchor_outstanding=parsed.outstanding_shares[0],
            current_outstanding=parsed.outstanding_shares[1],
        )
        # Anchor: 12M outstanding - 8M float = 4M affiliate shares.
        # Later 15M outstanding - constant 4M affiliates => 11M conservative float.
        self.assertEqual(rolled.value_shares, 11_000_000)
        self.assertEqual(rolled.current_outstanding_shares, 15_000_000)

    def test_roll_forward_does_not_reduce_float_on_buyback_without_new_annual_float(self):
        acceptance = parse_submission_acceptance_times(self.submissions)
        parsed = parse_companyfacts(self.companyfacts, acceptance_times=acceptance)
        anchor = implied_float_shares(parsed.public_float[0], historical_price=3.0)
        smaller = type(parsed.outstanding_shares[0])(
            cik=parsed.outstanding_shares[0].cik,
            measure_date=parsed.outstanding_shares[1].measure_date,
            shares=9_000_000,
            filed_date=parsed.outstanding_shares[1].filed_date,
            available_at=parsed.outstanding_shares[1].available_at,
            accession="buyback",
            form="10-Q",
        )
        rolled = roll_forward_float(
            anchor,
            anchor_outstanding=parsed.outstanding_shares[0],
            current_outstanding=smaller,
        )
        self.assertEqual(rolled.value_shares, 8_000_000)

    def test_duplicate_companyfacts_rows_are_deduplicated(self):
        row = self.companyfacts["facts"]["dei"]["EntityPublicFloat"]["units"]["USD"][0]
        self.companyfacts["facts"]["dei"]["EntityPublicFloat"]["units"]["USD"].append(dict(row))
        parsed = parse_companyfacts(self.companyfacts)
        self.assertEqual(len(parsed.public_float), 1)

    def test_client_requires_declared_contact_email(self):
        with self.assertRaisesRegex(ValueError, "contact email"):
            SecEdgarClient("MomentumBot https://github.com/RoomyRems/momentumbot")
        client = SecEdgarClient("RoomyRems MomentumBot research@example.com")
        self.assertEqual(
            client.user_agent,
            "RoomyRems MomentumBot research@example.com",
        )

    def test_client_reads_declared_identity_from_environment(self):
        with patch.dict(
            "os.environ",
            {"SEC_USER_AGENT": "RoomyRems MomentumBot research@example.com"},
        ):
            client = SecEdgarClient.from_env()
        self.assertIn("research@example.com", client.user_agent)

    def test_client_fails_before_network_without_declared_identity(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "SEC_USER_AGENT"):
                SecEdgarClient.from_env()


if __name__ == "__main__":
    unittest.main()
