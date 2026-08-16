from __future__ import annotations

import unittest

from momentumbot.historical_universe import (
    UniverseDecisionReason,
    classify_ticker_group,
    historical_universe_v0_1_manifest,
)


def _row(
    ticker: str,
    name: str,
    *,
    security_type: str = "CS",
    exchange: str = "XNAS",
    figi: str = "FIGI",
) -> dict[str, object]:
    return {
        "ticker": ticker,
        "active": True,
        "market": "stocks",
        "locale": "us",
        "primary_exchange": exchange,
        "type": security_type,
        "name": name,
        "cik": "1",
        "composite_figi": figi,
    }


def _coverage(
    *,
    raw_prior: bool = True,
    raw_target: bool = True,
    split_prior: bool = True,
    split_target: bool = True,
    invalid_symbol: bool = False,
) -> dict[str, object]:
    return {
        "invalid_symbol": invalid_symbol,
        "raw_prior_session_present": raw_prior,
        "raw_target_session_present": raw_target,
        "split_prior_session_present": split_prior,
        "split_target_session_present": split_target,
        "coverage_pass": bool(
            not invalid_symbol
            and raw_prior
            and raw_target
            and split_prior
            and split_target
        ),
    }


class HistoricalUniverseTests(unittest.TestCase):
    def test_clean_common_equity_with_complete_bars_is_included(self) -> None:
        decision = classify_ticker_group(
            [_row("AAA", "AAA Incorporated Common Stock")],
            _coverage(),
        )

        self.assertTrue(decision.included)
        self.assertEqual(decision.reason, UniverseDecisionReason.INCLUDED)
        self.assertEqual(decision.selected_security_type, "CS")
        self.assertEqual(decision.accepted_identity_count, 1)

    def test_type_name_conflict_and_units_fail_closed(self) -> None:
        preferred = classify_ticker_group(
            [_row("PREF", "Issuer Depositary Shares representing Preferred Stock")],
            _coverage(),
        )
        units = classify_ticker_group(
            [_row("UNIT", "Issuer L.P. Common Units")],
            _coverage(),
        )

        self.assertEqual(
            preferred.reason,
            UniverseDecisionReason.INSTRUMENT_METADATA_CONFLICT,
        )
        self.assertEqual(
            units.reason,
            UniverseDecisionReason.INSTRUMENT_STRUCTURE_REVIEW,
        )
        self.assertFalse(preferred.included)
        self.assertFalse(units.included)

    def test_collision_selects_one_clean_identity_but_not_two(self) -> None:
        clean = _row("AAA", "AAA Corporation Common Stock", figi="COMMON")
        preferred = _row(
            "AAA",
            "Other Issuer Preferred Stock",
            security_type="PFD",
            exchange="XNYS",
            figi="PREFERRED",
        )
        resolved = classify_ticker_group([preferred, clean], _coverage())
        ambiguous = classify_ticker_group(
            [clean, {**clean, "cik": "2", "composite_figi": "SECOND"}],
            _coverage(),
        )

        self.assertTrue(resolved.included)
        self.assertEqual(resolved.selected_composite_figi, "COMMON")
        self.assertFalse(ambiguous.included)
        self.assertEqual(
            ambiguous.reason,
            UniverseDecisionReason.MULTIPLE_ELIGIBLE_IDENTITIES,
        )

    def test_market_data_failure_reasons_are_structural_and_deterministic(self) -> None:
        row = _row("AAA", "AAA Corporation Common Stock")
        cases = [
            (
                _coverage(raw_prior=False, split_prior=False),
                UniverseDecisionReason.MISSING_PRIOR_SESSION,
            ),
            (
                _coverage(raw_target=False, split_target=False),
                UniverseDecisionReason.MISSING_TARGET_SESSION,
            ),
            (
                _coverage(
                    raw_prior=False,
                    raw_target=False,
                    split_prior=False,
                    split_target=False,
                ),
                UniverseDecisionReason.NO_DAILY_BARS_IN_WINDOW,
            ),
            (
                _coverage(raw_target=False),
                UniverseDecisionReason.RAW_SPLIT_COVERAGE_MISMATCH,
            ),
            (
                _coverage(invalid_symbol=True),
                UniverseDecisionReason.INVALID_MARKET_SYMBOL,
            ),
        ]

        for coverage, reason in cases:
            with self.subTest(reason=reason):
                decision = classify_ticker_group([row], coverage)
                self.assertFalse(decision.included)
                self.assertEqual(decision.reason, reason)

    def test_missing_coverage_and_disallowed_exchange_fail_closed(self) -> None:
        row = _row("AAA", "AAA Corporation Common Stock")
        missing = classify_ticker_group([row], None)
        exchange = classify_ticker_group(
            [{**row, "primary_exchange": "OTCX"}],
            _coverage(),
        )

        self.assertEqual(
            missing.reason,
            UniverseDecisionReason.COVERAGE_RECORD_MISSING,
        )
        self.assertEqual(
            exchange.reason,
            UniverseDecisionReason.DISALLOWED_PRIMARY_EXCHANGE,
        )

    def test_policy_manifest_is_stable_and_non_promotable_by_status(self) -> None:
        first = historical_universe_v0_1_manifest()
        second = historical_universe_v0_1_manifest()

        self.assertEqual(first, second)
        self.assertEqual(len(first["fingerprint"]), 64)
        self.assertEqual(first["policy_id"], "massive-common-equity-v0.1")
        self.assertEqual(
            first["status"],
            "frozen_research_data_contract_not_promotable",
        )


if __name__ == "__main__":
    unittest.main()
