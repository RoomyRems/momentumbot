import copy
import json
import unittest
from pathlib import Path

import pandas as pd

from momentumbot.research.daily_chart_context import (
    CONTRACT_ID,
    CONTEXT_HELDOUT_PANEL_CONTENT_SHA256,
    MOVING_AVERAGE_WINDOWS,
    REQUESTED_PRIOR_SESSIONS,
    build_daily_chart_evidence,
    canonical_fingerprint,
    daily_chart_supplemental_evidence,
    load_daily_chart_context_contract,
    validate_daily_chart_evidence,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research" / "strategy" / "daily-chart-context-shadow-v0.1.json"
AUDIT = ROOT / "research" / "data-audits" / "daily-chart-context-shadow-v0.1.json"


def _bars(count=REQUESTED_PRIOR_SESSIONS):
    index = pd.bdate_range(end="2026-07-31", periods=count, tz="UTC")
    index = index + pd.Timedelta(hours=20)
    rows = []
    for offset in range(count):
        open_price = 3.0 + offset * 0.05
        rows.append(
            (
                open_price,
                open_price + 0.40,
                open_price - 0.20,
                open_price + 0.20,
                100_000 + offset * 1_000,
            )
        )
    return pd.DataFrame(
        rows,
        columns=["open", "high", "low", "close", "volume"],
        index=index,
    )


def _record(bars=None, **overrides):
    values = {
        "symbol": "AAA",
        "decision_time": "2026-08-03T13:31:00+00:00",
        "decision_price": 5.50,
        "identity_identifier_kind": "composite_figi",
        "identity_identifier": "BBG000TEST01",
        "identity_verified_start_date": "2026-04-01",
        "identity_verified_through_date": "2026-08-03",
    }
    values.update(overrides)
    return build_daily_chart_evidence(_bars() if bars is None else bars, **values)


class DailyChartContextTests(unittest.TestCase):
    def test_contract_freezes_causal_sources_but_no_chart_threshold(self):
        payload = load_daily_chart_context_contract(CONTRACT)
        self.assertEqual(payload["contract_id"], CONTRACT_ID)
        self.assertEqual(
            payload["source_acquisition"]["adjustment_asof"],
            "decision_session_date",
        )
        self.assertFalse(
            payload["source_acquisition"]["current_session_complete_bar_allowed"]
        )
        self.assertEqual(
            payload["feature_protocol"]["moving_average_windows_sessions"],
            list(MOVING_AVERAGE_WINDOWS),
        )
        self.assertIsNone(payload["feature_protocol"]["failed_pop_threshold"])
        self.assertTrue(payload["identity_boundary"]["moving_average_200_deferred"])
        self.assertEqual(
            payload["evaluation_boundary"]["registered_panel_content_sha256"],
            CONTEXT_HELDOUT_PANEL_CONTENT_SHA256,
        )
        self.assertEqual(payload["runtime_strategy_effect"], "none")

    def test_protocol_audit_binds_exact_contract_without_promotion(self):
        contract = load_daily_chart_context_contract(CONTRACT)
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(audit["contract_id"], CONTRACT_ID)
        self.assertEqual(
            audit["contract_content_sha256"],
            canonical_fingerprint(contract),
        )
        self.assertTrue(audit["decision"]["freeze_daily_chart_schema_v01"])
        self.assertFalse(audit["decision"]["freeze_failed_pop_threshold"])
        self.assertFalse(audit["decision"]["promote_chart_rule"])

    def test_builder_uses_only_prior_completed_sessions_and_exact_formulas(self):
        bars = _bars()
        record = _record(bars)
        self.assertEqual(
            record["coverage"]["included_prior_completed_sessions"],
            REQUESTED_PRIOR_SESSIONS,
        )
        self.assertTrue(record["coverage"]["history_complete_for_requested_window"])
        self.assertFalse(record["causal_cutoff"]["decision_session_bar_used"])
        self.assertEqual(
            record["features"]["prior_completed_session"]["session_date"],
            "2026-07-31",
        )
        expected_sma_20 = float(bars.iloc[-20:]["close"].mean())
        self.assertAlmostEqual(
            record["features"]["moving_averages"]["sma_20"]["value"],
            expected_sma_20,
        )
        self.assertEqual(
            len(record["features"]["recent_session_metrics"]),
            20,
        )
        metric = record["features"]["recent_session_metrics"][-1]
        expected_excursion = (
            float(bars.iloc[-1]["high"]) / float(bars.iloc[-2]["close"]) - 1.0
        ) * 100.0
        self.assertAlmostEqual(metric["high_excursion_pct"], expected_excursion)
        self.assertIsNotNone(record["features"]["nearest_overhead_reference"])
        self.assertEqual(len(record["record_content_sha256"]), 64)

    def test_builder_rejects_current_session_and_naive_source_timestamps(self):
        current = _bars()
        current.loc[pd.Timestamp("2026-08-03T20:00:00+00:00")] = (
            7.0,
            8.0,
            6.5,
            7.5,
            1_000_000,
        )
        with self.assertRaisesRegex(ValueError, "strictly before"):
            _record(current)

        naive = _bars()
        naive.index = naive.index.tz_localize(None)
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            _record(naive)

    def test_identity_window_must_cover_every_included_bar_and_decision(self):
        with self.assertRaisesRegex(ValueError, "does not cover"):
            _record(identity_verified_start_date="2026-07-01")
        with self.assertRaisesRegex(ValueError, "does not reach"):
            _record(identity_verified_through_date="2026-07-31")

    def test_partial_history_is_explicit_and_does_not_invent_features(self):
        record = _record(_bars(10), identity_verified_start_date="2026-07-01")
        self.assertFalse(record["coverage"]["history_complete_for_requested_window"])
        self.assertEqual(
            record["features"]["moving_averages"]["sma_20"]["state"],
            "insufficient_history",
        )
        self.assertIsNone(record["features"]["moving_averages"]["sma_50"]["value"])
        self.assertFalse(record["coverage"]["moving_average_200_available"])

    def test_tamper_fails_hash_and_deterministic_reconstruction(self):
        record = _record()
        changed = copy.deepcopy(record)
        changed["features"]["prior_completed_session"]["high"] = 999.0
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            validate_daily_chart_evidence(changed)

        changed["record_content_sha256"] = canonical_fingerprint(
            {key: value for key, value in changed.items() if key != "record_content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "deterministic reconstruction"):
            validate_daily_chart_evidence(changed)

    def test_adapter_requires_frozen_artifact_hash_and_has_no_authority(self):
        record = _record()
        evidence = daily_chart_supplemental_evidence(
            record,
            source_artifact_content_sha256="a" * 64,
        )
        self.assertEqual(evidence["domain"], "daily_chart")
        self.assertEqual(evidence["source_contract_id"], CONTRACT_ID)
        self.assertTrue(evidence["evidence_id"].startswith("daily-chart:AAA:"))
        self.assertIsNone(evidence["payload"]["prohibited_outputs"]["order_action"])
        with self.assertRaisesRegex(ValueError, "source artifact hash"):
            daily_chart_supplemental_evidence(
                record,
                source_artifact_content_sha256="not-a-hash",
            )


if __name__ == "__main__":
    unittest.main()
