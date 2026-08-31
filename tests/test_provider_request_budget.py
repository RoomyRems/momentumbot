from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from momentumbot.providers.request_budget import (
    BUDGET_FILE_ENV,
    BUDGET_LIMIT_ENV,
    consume_provider_request,
    load_provider_request_budget,
)


class ProviderRequestBudgetTests(unittest.TestCase):
    def test_budget_is_inactive_when_unconfigured(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            consume_provider_request("https://data.alpaca.markets/example")

    def test_shared_budget_counts_attempts_by_host_without_urls(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "budget.json"
            environment = {
                BUDGET_FILE_ENV: str(path),
                BUDGET_LIMIT_ENV: "3",
            }
            with patch.dict(os.environ, environment, clear=True):
                consume_provider_request(
                    "https://data.alpaca.markets/path?secret=do-not-persist"
                )
                consume_provider_request("https://data.sec.gov/path")
                consume_provider_request("https://data.alpaca.markets/other")
            state = load_provider_request_budget(path)
            self.assertEqual(state["total_attempts"], 3)
            self.assertEqual(
                state["by_host"],
                {"data.alpaca.markets": 2, "data.sec.gov": 1},
            )
            self.assertNotIn("secret", path.read_text(encoding="utf-8"))

    def test_budget_exhaustion_fails_before_an_extra_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "budget.json"
            environment = {
                BUDGET_FILE_ENV: str(path),
                BUDGET_LIMIT_ENV: "1",
            }
            with patch.dict(os.environ, environment, clear=True):
                consume_provider_request("https://api.massive.com/first")
                with self.assertRaisesRegex(RuntimeError, "exhausted"):
                    consume_provider_request("https://api.massive.com/second")
            self.assertEqual(load_provider_request_budget(path)["total_attempts"], 1)

    def test_partial_or_relative_configuration_is_rejected(self) -> None:
        with patch.dict(
            os.environ,
            {BUDGET_FILE_ENV: "/tmp/provider-budget-test.json"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "both environment"):
                consume_provider_request("https://data.alpaca.markets/path")
        with patch.dict(
            os.environ,
            {BUDGET_FILE_ENV: "relative.json", BUDGET_LIMIT_ENV: "1"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "absolute"):
                consume_provider_request("https://data.alpaca.markets/path")


if __name__ == "__main__":
    unittest.main()
