import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from momentumbot.providers.sec_bulk import SecBulkArchives


class SecBulkTests(unittest.TestCase):
    def _archives(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        companyfacts = root / "companyfacts.zip"
        submissions = root / "submissions.zip"
        cik = "0000001234"
        facts_payload = {
            "cik": 1234,
            "facts": {
                "dei": {
                    "EntityPublicFloat": {
                        "units": {
                            "USD": [
                                {
                                    "end": "2025-06-30",
                                    "val": 12_000_000,
                                    "accn": "0001",
                                    "fy": 2025,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "filed": "2025-08-01",
                                }
                            ]
                        }
                    },
                    "EntityCommonStockSharesOutstanding": {
                        "units": {
                            "shares": [
                                {
                                    "end": "2025-07-25",
                                    "val": 7_000_000,
                                    "accn": "0001",
                                    "fy": 2025,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "filed": "2025-08-01",
                                }
                            ]
                        }
                    },
                }
            },
        }
        submissions_payload = {
            "cik": "1234",
            "tickers": ["TEST"],
            "exchanges": ["Nasdaq"],
            "filings": {
                "recent": {
                    "accessionNumber": ["0001"],
                    "acceptanceDateTime": ["2025-08-01T16:30:00.000Z"],
                }
            },
        }
        with zipfile.ZipFile(companyfacts, "w") as archive:
            archive.writestr(f"CIK{cik}.json", json.dumps(facts_payload))
        with zipfile.ZipFile(submissions, "w") as archive:
            archive.writestr(f"submissions/CIK{cik}.json", json.dumps(submissions_payload))
        return tmp, companyfacts, submissions

    def test_resolves_ticker_and_parses_facts_without_extracting_zip(self):
        tmp, companyfacts, submissions = self._archives()
        self.addCleanup(tmp.cleanup)
        store = SecBulkArchives(companyfacts, submissions)
        self.assertEqual(store.cik_for_ticker("test"), "0000001234")
        parsed = store.parsed_companyfacts("1234")
        self.assertEqual(parsed.public_float[0].public_float_usd, 12_000_000)
        self.assertEqual(parsed.outstanding_shares[0].shares, 7_000_000)
        self.assertEqual(parsed.public_float[0].available_at.isoformat(), "2025-08-01T16:30:00+00:00")

    def test_unknown_ticker_returns_none(self):
        tmp, companyfacts, submissions = self._archives()
        self.addCleanup(tmp.cleanup)
        store = SecBulkArchives(companyfacts, submissions)
        self.assertIsNone(store.cik_for_ticker("NOPE"))


if __name__ == "__main__":
    unittest.main()
