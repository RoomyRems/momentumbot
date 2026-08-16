from __future__ import annotations

import unittest
from datetime import date

from momentumbot.providers.massive import (
    MassiveReferenceClient,
    reference_membership_fingerprint,
    reference_ticker_fingerprint,
)


def _row(ticker: str) -> dict[str, object]:
    return {
        "ticker": ticker,
        "active": True,
        "market": "stocks",
        "locale": "us",
        "primary_exchange": "XNAS",
        "type": "CS",
        "name": f"{ticker} Incorporated",
        "cik": "0000000001",
        "last_updated_utc": "2025-04-04T00:00:00Z",
    }


class MassiveProviderTests(unittest.TestCase):
    def test_paginates_normalizes_and_never_preserves_cursor_secret(self) -> None:
        calls: list[str] = []

        def requester(url: str, **_: object) -> object:
            calls.append(url)
            if len(calls) == 1:
                return {
                    "count": 2,
                    "results": [_row("BBB"), _row("AAA")],
                    "next_url": (
                        "https://api.massive.com/v3/reference/tickers?cursor=opaque"
                        "&apiKey=PROVIDER_ECHOED_SECRET"
                    ),
                }
            return {"count": 1, "results": [_row("CCC")]}

        client = MassiveReferenceClient("actual-secret", requester=requester)
        census = client.active_tickers_as_of(date(2025, 4, 3), limit=2)

        self.assertEqual([row["ticker"] for row in census.rows], ["AAA", "BBB", "CCC"])
        self.assertEqual([page.row_count for page in census.pages], [2, 1])
        self.assertIn("apiKey=actual-secret", calls[1])
        self.assertNotIn("PROVIDER_ECHOED_SECRET", calls[1])
        self.assertNotIn("actual-secret", repr(census))

    def test_repeated_cursor_is_rejected(self) -> None:
        def requester(url: str, **_: object) -> object:
            ticker = "AAA" if "cursor=" not in url else "BBB"
            return {
                "count": 1,
                "results": [_row(ticker)],
                "next_url": "https://api.massive.com/v3/reference/tickers?cursor=same",
            }

        client = MassiveReferenceClient("secret", requester=requester)
        with self.assertRaisesRegex(RuntimeError, "cursor repeated"):
            client.active_tickers_as_of(date(2025, 4, 3), limit=1)

    def test_unofficial_pagination_host_is_rejected(self) -> None:
        def requester(_: str, **__: object) -> object:
            return {
                "count": 1,
                "results": [_row("AAA")],
                "next_url": "https://example.invalid/v3/reference/tickers?cursor=bad",
            }

        client = MassiveReferenceClient("secret", requester=requester)
        with self.assertRaisesRegex(RuntimeError, "official API hosts"):
            client.active_tickers_as_of(date(2025, 4, 3), limit=1)

    def test_non_active_row_fails_closed(self) -> None:
        row = _row("AAA")
        row["active"] = False
        client = MassiveReferenceClient(
            "secret",
            requester=lambda *_args, **_kwargs: {"count": 1, "results": [row]},
        )
        with self.assertRaisesRegex(RuntimeError, "non-active"):
            client.active_tickers_as_of(date(2025, 4, 3))

    def test_same_ticker_with_distinct_security_identities_is_preserved(self) -> None:
        common = _row("AAA")
        preferred = {
            **_row("AAA"),
            "primary_exchange": "XNYS",
            "type": "PFD",
            "composite_figi": "BBG-DISTINCT",
        }
        client = MassiveReferenceClient(
            "secret",
            requester=lambda *_args, **_kwargs: {
                "count": 2,
                "results": [common, preferred],
            },
        )

        census = client.active_tickers_as_of(date(2025, 4, 3))

        self.assertEqual(len(census.rows), 2)
        self.assertEqual({row["ticker"] for row in census.rows}, {"AAA"})
        self.assertEqual({row["type"] for row in census.rows}, {"CS", "PFD"})

    def test_exact_membership_identity_duplicate_fails_closed(self) -> None:
        row = _row("AAA")
        client = MassiveReferenceClient(
            "secret",
            requester=lambda *_args, **_kwargs: {
                "count": 2,
                "results": [row, {**row, "name": "Metadata-only rename"}],
            },
        )

        with self.assertRaisesRegex(RuntimeError, "duplicate membership identity"):
            client.active_tickers_as_of(date(2025, 4, 3))

    def test_fingerprints_are_order_independent_and_membership_scoped(self) -> None:
        first = _row("AAA")
        second = _row("BBB")
        content = reference_ticker_fingerprint([first, second])
        self.assertEqual(content, reference_ticker_fingerprint([second, first]))
        membership = reference_membership_fingerprint([first, second])
        changed_name = {**first, "name": "Renamed after retrieval"}
        self.assertEqual(
            membership,
            reference_membership_fingerprint([changed_name, second]),
        )
        self.assertNotEqual(content, reference_ticker_fingerprint([changed_name, second]))


if __name__ == "__main__":
    unittest.main()
