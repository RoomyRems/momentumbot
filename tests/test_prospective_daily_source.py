from __future__ import annotations

import copy
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import pandas as pd
import yaml

from momentumbot.historical_data import (
    DiscoveryAuditRow,
    DiscoveryResult,
    DiscoveryRow,
    asset_master_fingerprint,
)
from momentumbot.providers.sec_edgar import normalize_company_tickers_exchange
from momentumbot.research.microstructure_contract import canonical_fingerprint
from momentumbot.research.prospective_daily_source import (
    GENERAL_PROFILE_ID,
    SMALL_PROFILE_ID,
    MicroTriggerDecision,
    ProfileActivation,
    build_daily_artifacts,
    build_micro_trigger_decisions,
    build_pre_session_prerequisites,
    build_profile_activations,
    build_scanner_runtime,
    capture_pre_session_from_providers,
    load_daily_source_contract,
    load_pre_session_prerequisites,
    produce_daily_source_from_providers,
    union_acquisition_profile,
    validate_pre_session_prerequisites,
    validate_daily_source_contract,
    write_daily_artifacts,
    write_pre_session_prerequisites,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRATION_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "prospective-daily-scanner-micro-source-v0.1-registration-2026-08-22.json"
)


def _asset(symbol: str = "TEST") -> dict[str, object]:
    return {
        "id": f"asset-{symbol}",
        "class": "us_equity",
        "exchange": "NASDAQ",
        "symbol": symbol,
        "name": f"{symbol} Corp",
        "status": "active",
        "tradable": True,
        "attributes": [],
    }


def _prerequisite() -> dict[str, object]:
    return build_pre_session_prerequisites(
        trading_date="2026-08-24",
        capture_started_at=datetime(2026, 8, 24, 9, 30, tzinfo=UTC),
        capture_completed_at=datetime(2026, 8, 24, 9, 30, 2, tzinfo=UTC),
        runtime_head_sha="a" * 40,
        asset_rows=[_asset()],
        sec_ticker_rows=[
            {
                "ticker": "TEST",
                "cik": "1234",
                "name": "Test Corp",
                "exchange": "Nasdaq",
            }
        ],
        workflow_context={"workflow_run_id": "42"},
    )


def _scanner_row(
    decision: str,
    *,
    gain: float,
    rank: int,
) -> dict[str, object]:
    return {
        "symbol": "TEST",
        "activation_time": "2026-08-24T11:00:00+00:00",
        "decision_time": decision,
        "candidate_completed_bar_present": True,
        "price": 3.0,
        "percent_gain": gain,
        "exact_same_time_rvol": 6.0,
        "estimated_float_shares": 5_000_000,
        "has_provider_news_as_of": True,
        "top_gainer_rank": rank,
    }


def _trade_frame() -> pd.DataFrame:
    index = pd.DatetimeIndex(
        [
            "2026-08-24T11:00:01+00:00",
            "2026-08-24T11:00:11+00:00",
            "2026-08-24T11:00:21+00:00",
        ],
        name="timestamp",
    )
    return pd.DataFrame(
        {
            "price": [9.90, 9.85, 9.92],
            "size": [100, 50, 100],
            "exchange": ["V", "V", "V"],
            "conditions": [(), (), ()],
            "trade_id": ["1", "2", "3"],
            "tape": ["C", "C", "C"],
        },
        index=index,
    )


def _empty_discovery() -> DiscoveryResult:
    return DiscoveryResult(
        asset_count=1,
        listed_asset_count=1,
        daily_superset_count=0,
        rvol_prefilter_count=0,
        market_candidate_count=0,
        asset_master_sha256=asset_master_fingerprint([_asset()]),
        asset_status_counts={"active": 1},
        rows=(),
        minutes={},
        contexts={},
        rvol_curves={},
        acquisition_audit=(
            DiscoveryAuditRow(
                symbol="TEST",
                disposition="excluded_daily_price_or_gain_acquisition_filter",
                daily_scan_basis_available=True,
                daily_price_gain_prefilter_pass=False,
                average_daily_volume_50_available=False,
                raw_target_minute_bars_present=False,
                split_target_minute_bars_present=False,
                rvol_history_sessions=0,
                coarse_rvol_evaluated=False,
                coarse_rvol_observation_available=False,
                coarse_rvol_prefilter_pass=False,
                exact_rvol_evaluated=False,
                exact_rvol_observation_available=False,
                causal_market_qualified=False,
                first_market_qualified_at=None,
                first_market_qualified_bar_started_at=None,
            ),
        ),
    )


def _candidate_discovery() -> DiscoveryResult:
    minute_index = pd.DatetimeIndex(
        ["2026-08-24T10:59:00+00:00"], name="timestamp"
    )
    minutes = pd.DataFrame(
        {
            "open": [2.90],
            "high": [3.05],
            "low": [2.85],
            "close": [3.00],
            "volume": [100_000],
            "trade_count": [100],
            "vwap": [2.95],
        },
        index=minute_index,
    )
    qualified_at = "2026-08-24T11:00:00+00:00"
    bar_started_at = "2026-08-24T10:59:00+00:00"
    return DiscoveryResult(
        asset_count=1,
        listed_asset_count=1,
        daily_superset_count=1,
        rvol_prefilter_count=1,
        market_candidate_count=1,
        asset_master_sha256=asset_master_fingerprint([_asset()]),
        asset_status_counts={"active": 1},
        rows=(
            DiscoveryRow(
                symbol="TEST",
                status="active",
                exchange="NASDAQ",
                previous_close=2.00,
                target_high=3.05,
                max_session_gain_pct=52.5,
                max_session_rvol_upper_bound=8.0,
                max_session_rvol=7.0,
                rvol_history_sessions=50,
                average_daily_volume_50=100_000.0,
                first_market_qualified_at=qualified_at,
                minute_bars=1,
                first_market_qualified_bar_started_at=bar_started_at,
            ),
        ),
        minutes={"TEST": minutes},
        contexts={},
        rvol_curves={
            "TEST": pd.Series([7.0], index=minute_index, name="rvol")
        },
        acquisition_audit=(
            DiscoveryAuditRow(
                symbol="TEST",
                disposition="causal_market_candidate",
                daily_scan_basis_available=True,
                daily_price_gain_prefilter_pass=True,
                average_daily_volume_50_available=True,
                raw_target_minute_bars_present=True,
                split_target_minute_bars_present=True,
                rvol_history_sessions=50,
                coarse_rvol_evaluated=True,
                coarse_rvol_observation_available=True,
                coarse_rvol_prefilter_pass=True,
                exact_rvol_evaluated=True,
                exact_rvol_observation_available=True,
                causal_market_qualified=True,
                first_market_qualified_at=qualified_at,
                first_market_qualified_bar_started_at=bar_started_at,
            ),
        ),
    )


class ProspectiveDailySourceTests(unittest.TestCase):
    def test_registered_contract_binds_parent_profiles_and_zero_execution_authority(self):
        contract = load_daily_source_contract(
            ROOT
            / "research"
            / "strategy"
            / "prospective-daily-scanner-micro-source-v0.1.json"
        )
        self.assertEqual(contract["registration_status"], "registered_before_first_prospective_session")
        self.assertEqual(contract["execution_status"]["daily_source_runtime_count"], 0)
        authority = contract["provider_authority"]
        self.assertTrue(authority["provider_reads_authorized"])
        self.assertFalse(authority["databento_request_authorized"])
        self.assertFalse(authority["paper_order_authorized"])
        changed = copy.deepcopy(contract)
        changed["micro_trigger_contract"]["fill_simulation_allowed"] = True
        changed["content_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "content hash|registration|fill"):
            validate_daily_source_contract(changed)

    def test_workflow_has_two_phase_schedule_and_only_registered_read_paths(self):
        path = ROOT / ".github" / "workflows" / "prospective-daily-source.yml"
        text = path.read_text(encoding="utf-8")
        self.assertIsInstance(yaml.safe_load(text), dict)
        for cron in (
            'cron: "30 9 24-28,31 8 *"',
            'cron: "30 9 1-4 9 *"',
            'cron: "20 14 24-28,31 8 *"',
            'cron: "20 14 1-4 9 *"',
        ):
            self.assertIn(cron, text)
        self.assertIn("actions: write", text)
        self.assertIn("ref: phase-3-historical-snapshot", text)
        self.assertIn("${{ runner.temp }}/prospective-prerequisite", text)
        self.assertIn("prospective-opportunity-freeze.yml/dispatches", text)
        self.assertIn("tests.test_prospective_daily_source", text)
        for forbidden in (
            "DATABENTO_API_KEY",
            "ALPACA_MAIN_API_KEY",
            "ALPACA_SMALL_API_KEY",
            "submit_order",
            "/v2/orders",
        ):
            self.assertNotIn(forbidden, text)

    def test_sec_crosswalk_normalization_is_strict_and_canonical(self):
        rows = normalize_company_tickers_exchange(
            {
                "fields": ["cik", "name", "ticker", "exchange"],
                "data": [
                    [1234, "Test Corp", "test", "Nasdaq"],
                    [9876, "Next Corp", "NEXT", "NYSE"],
                ],
            }
        )
        self.assertEqual([row["ticker"] for row in rows], ["NEXT", "TEST"])
        self.assertEqual(rows[1]["cik"], "0000001234")
        changed = {
            "fields": ["cik", "name", "ticker"],
            "data": [[1234, "Test", "TEST"]],
        }
        with self.assertRaisesRegex(ValueError, "incomplete"):
            normalize_company_tickers_exchange(changed)

    def test_pre_session_prerequisite_is_hash_bound_and_before_strategy(self):
        payload = _prerequisite()
        self.assertEqual(
            validate_pre_session_prerequisites(payload)["trading_date"],
            "2026-08-24",
        )
        self.assertEqual(payload["asset_count"], 1)
        self.assertEqual(payload["sec_ticker_count"], 1)
        changed = copy.deepcopy(payload)
        changed["asset_census"][0]["symbol"] = "LATE"
        with self.assertRaisesRegex(ValueError, "canonical|hash"):
            validate_pre_session_prerequisites(changed)
        with self.assertRaisesRegex(ValueError, "07:00"):
            build_pre_session_prerequisites(
                trading_date="2026-08-24",
                capture_started_at=datetime(2026, 8, 24, 11, 0, 1, tzinfo=UTC),
                capture_completed_at=datetime(2026, 8, 24, 11, 0, 2, tzinfo=UTC),
                runtime_head_sha="a" * 40,
                asset_rows=[_asset()],
                sec_ticker_rows=[
                    {
                        "ticker": "TEST",
                        "cik": "1234",
                        "name": "Test",
                        "exchange": "NASDAQ",
                    }
                ],
            )

    def test_pre_session_provider_capture_rejects_deadline_before_any_read(self):
        alpaca = Mock()
        sec = Mock()
        with self.assertRaisesRegex(ValueError, "before 07:00"):
            capture_pre_session_from_providers(
                trading_date="2026-08-24",
                alpaca=alpaca,
                sec=sec,
                runtime_head_sha="a" * 40,
                now=lambda: datetime(2026, 8, 24, 11, 0, tzinfo=UTC),
            )
        alpaca.assets.assert_not_called()
        sec.company_tickers_exchange.assert_not_called()

    def test_union_profile_covers_both_registered_price_and_gain_ranges(self):
        profile = union_acquisition_profile()
        self.assertEqual(profile.min_price, 1.5)
        self.assertEqual(profile.max_price, 20.0)
        self.assertEqual(profile.min_percent_gain, 10.0)
        self.assertIsNone(profile.require_top_gainer_rank)

    def test_profile_activations_preserve_later_small_account_qualification(self):
        rows = [
            _scanner_row(
                "2026-08-24T11:00:00+00:00", gain=15.0, rank=4
            ),
            _scanner_row(
                "2026-08-24T11:01:00+00:00", gain=30.0, rank=2
            ),
        ]
        activations, annotated = build_profile_activations(
            scanner_runtime_content_sha256="b" * 64,
            scanner_rows=rows,
        )
        self.assertEqual(len(activations), 2)
        self.assertEqual(
            activations[0].eligible_strategy_profile_ids,
            (GENERAL_PROFILE_ID,),
        )
        self.assertEqual(
            activations[1].eligible_strategy_profile_ids,
            (SMALL_PROFILE_ID,),
        )
        self.assertEqual(
            annotated[1]["profile_eligibility"][SMALL_PROFILE_ID]["quality"],
            "a_quality",
        )

    def test_same_minute_profile_union_is_emitted_once(self):
        rows = [
            _scanner_row(
                "2026-08-24T11:00:00+00:00", gain=30.0, rank=2
            )
        ]
        activations, _ = build_profile_activations(
            scanner_runtime_content_sha256="b" * 64,
            scanner_rows=rows,
        )
        self.assertEqual(len(activations), 1)
        self.assertEqual(
            activations[0].eligible_strategy_profile_ids,
            (GENERAL_PROFILE_ID, SMALL_PROFILE_ID),
        )

    def test_micro_source_stops_at_chart_trigger_without_fill_or_exit(self):
        activation = ProfileActivation(
            activation_id="activation-test",
            symbol="TEST",
            candidate_qualified_at="2026-08-24T11:00:00+00:00",
            scanner_record_content_sha256="c" * 64,
            eligible_strategy_profile_ids=(GENERAL_PROFILE_ID,),
        )
        index = pd.DatetimeIndex(
            [
                "2026-08-24T11:00:00+00:00",
                "2026-08-24T11:00:10+00:00",
            ],
            name="timestamp",
        )
        bars = pd.DataFrame(
            {
                "open": [9.50, 9.90],
                "high": [10.00, 9.90],
                "low": [9.50, 9.80],
                "close": [9.90, 9.82],
                "volume": [100, 40],
            },
            index=index,
        )
        support = pd.DataFrame(
            {"vwap": [9.0, 9.0], "ema": [9.0, 9.0]}, index=index
        )
        decisions = build_micro_trigger_decisions(
            activation,
            bars=bars,
            trades=_trade_frame(),
            support=support,
            replay_end=pd.Timestamp("2026-08-24T14:00:00+00:00"),
        )
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].decision_at, "2026-08-24T11:00:21+00:00")
        rendered = json.dumps(decisions[0].plan, sort_keys=True)
        for forbidden in ("fill", "exit", "outcome", "pnl", "quantity"):
            self.assertNotIn(forbidden, rendered)

    def test_daily_source_binds_scanner_and_micro_without_account_state(self):
        rows = [
            _scanner_row(
                "2026-08-24T11:00:00+00:00", gain=30.0, rank=2
            )
        ]
        scanner = build_scanner_runtime(
            trading_date="2026-08-24",
            prerequisite_content_sha256="d" * 64,
            scanner_rows=rows,
            scanner_lineage={"market_inputs_sha256": "e" * 64},
        )
        activations, _ = build_profile_activations(
            scanner_runtime_content_sha256=scanner["content_sha256"],
            scanner_rows=rows,
        )
        activation = activations[0]
        trigger = MicroTriggerDecision(
            activation_id=activation.activation_id,
            plan_id="plan-test",
            symbol="TEST",
            candidate_qualified_at=activation.candidate_qualified_at,
            decision_at="2026-08-24T11:00:21+00:00",
            micro_runtime_content_sha256="f" * 64,
            eligible_strategy_profile_ids=(
                activation.eligible_strategy_profile_ids
            ),
            plan={
                "symbol": "TEST",
                "source_bar_start": "2026-08-24T11:00:10+00:00",
            },
        )
        artifacts = build_daily_artifacts(
            scanner_runtime=scanner,
            trigger_decisions=[trigger],
        )
        self.assertEqual(artifacts.decision_source["candidate_count"], 1)
        self.assertEqual(artifacts.decision_source["decision_count"], 1)
        self.assertFalse(artifacts.decision_source["account_snapshot_loaded"])
        rendered = json.dumps(artifacts.decision_source, sort_keys=True)
        for forbidden in ("fill_price", "exit_time", "quantity", "outcome"):
            self.assertNotIn(forbidden, rendered)

    def test_write_once_artifacts_and_prerequisites(self):
        prerequisite = _prerequisite()
        with tempfile.TemporaryDirectory() as temporary:
            pre = Path(temporary) / "pre"
            write_pre_session_prerequisites(pre, prerequisite)
            loaded = load_pre_session_prerequisites(pre)
            self.assertEqual(loaded, prerequisite)
            with self.assertRaises(FileExistsError):
                write_pre_session_prerequisites(pre, prerequisite)

            scanner = build_scanner_runtime(
                trading_date="2026-08-24",
                prerequisite_content_sha256=prerequisite["content_sha256"],
                scanner_rows=[],
                scanner_lineage={"market_inputs_sha256": "e" * 64},
            )
            artifacts = build_daily_artifacts(
                scanner_runtime=scanner, trigger_decisions=[]
            )
            output = Path(temporary) / "daily"
            write_daily_artifacts(output, artifacts)
            self.assertTrue(
                (output / "prospective-daily-micro-decision-source.json").is_file()
            )
            with self.assertRaises(FileExistsError):
                write_daily_artifacts(output, artifacts)

    def test_provider_orchestrator_retains_an_explicit_zero_candidate_date(self):
        empty = _empty_discovery()
        with patch(
            "momentumbot.research.prospective_daily_source.discover_market_day",
            return_value=empty,
        ):
            artifacts = produce_daily_source_from_providers(
                prerequisite=_prerequisite(),
                alpaca=object(),  # type: ignore[arg-type]
                sec=object(),  # type: ignore[arg-type]
                now=lambda: datetime(2026, 8, 24, 14, 2, tzinfo=UTC),
            )
        self.assertEqual(artifacts.decision_source["candidate_count"], 0)
        self.assertEqual(artifacts.decision_source["decisions"], [])
        self.assertTrue(artifacts.producer_manifest["zero_opportunity_date"])

    def test_provider_orchestrator_does_not_hide_a_rejected_member_as_zero(self):
        empty = _empty_discovery()
        alpaca = SimpleNamespace(invalid_symbols={"TEST"})
        with patch(
            "momentumbot.research.prospective_daily_source.discover_market_day",
            return_value=empty,
        ), self.assertRaisesRegex(RuntimeError, "rejected frozen membership"):
            produce_daily_source_from_providers(
                prerequisite=_prerequisite(),
                alpaca=alpaca,  # type: ignore[arg-type]
                sec=object(),  # type: ignore[arg-type]
                now=lambda: datetime(2026, 8, 24, 14, 2, tzinfo=UTC),
            )

    def test_provider_orchestrator_composes_a_nonzero_source(self):
        discovery = _candidate_discovery()
        rank_frame = discovery.minutes["TEST"]
        support = pd.DataFrame(
            {"vwap": [2.90], "ema": [2.90]}, index=rank_frame.index
        )
        alpaca = Mock()
        alpaca.invalid_symbols = set()
        alpaca.bars_batched.return_value = {"TEST": pd.DataFrame()}

        def trigger(activation, **_kwargs):
            return [
                MicroTriggerDecision(
                    activation_id=activation.activation_id,
                    plan_id="plan-provider-test",
                    symbol=activation.symbol,
                    candidate_qualified_at=activation.candidate_qualified_at,
                    decision_at="2026-08-24T11:00:21+00:00",
                    micro_runtime_content_sha256="f" * 64,
                    eligible_strategy_profile_ids=(
                        activation.eligible_strategy_profile_ids
                    ),
                    plan={
                        "symbol": "TEST",
                        "source_bar_start": "2026-08-24T11:00:10+00:00",
                    },
                )
            ]

        news_manifest = {
            "event_sha256": "1" * 64,
            "status_sha256": "2" * 64,
            "content_sha256": "3" * 64,
        }
        with patch(
            "momentumbot.research.prospective_daily_source.discover_market_day",
            return_value=discovery,
        ), patch(
            "momentumbot.research.prospective_daily_source.build_float_records_from_providers",
            return_value=[{"float_classification": "known_below_limit"}],
        ), patch(
            "momentumbot.research.prospective_daily_source.causal_float_records_fingerprint",
            return_value="4" * 64,
        ), patch(
            "momentumbot.research.prospective_daily_source.build_news_records_from_provider",
            return_value=([], [], news_manifest),
        ), patch(
            "momentumbot.research.prospective_daily_source.reacquire_rank_inputs",
            return_value=({"TEST": 2.0}, {"TEST": rank_frame}),
        ), patch(
            "momentumbot.research.prospective_daily_source.bind_candidate_frames_to_reacquired_rank_frames",
            return_value={"TEST": rank_frame},
        ), patch(
            "momentumbot.research.prospective_daily_source.build_scanner_snapshot_rows",
            return_value=[
                _scanner_row(
                    "2026-08-24T11:00:00+00:00", gain=30.0, rank=2
                )
            ],
        ), patch(
            "momentumbot.research.prospective_daily_source.market_inputs_fingerprint",
            return_value="5" * 64,
        ), patch(
            "momentumbot.research.prospective_daily_source.completed_bar_support_series",
            return_value=support,
        ), patch(
            "momentumbot.research.prospective_daily_source.historical_trades",
            return_value=_trade_frame(),
        ), patch(
            "momentumbot.research.prospective_daily_source.aggregate_trade_bars",
            return_value=rank_frame,
        ), patch(
            "momentumbot.research.prospective_daily_source.build_micro_trigger_decisions",
            side_effect=trigger,
        ):
            artifacts = produce_daily_source_from_providers(
                prerequisite=_prerequisite(),
                alpaca=alpaca,
                sec=object(),  # type: ignore[arg-type]
                now=lambda: datetime(2026, 8, 24, 14, 2, tzinfo=UTC),
            )
        self.assertEqual(artifacts.decision_source["candidate_count"], 1)
        self.assertEqual(artifacts.decision_source["decision_count"], 1)
        self.assertFalse(artifacts.producer_manifest["zero_opportunity_date"])

    def test_provider_orchestrator_rejects_pre_cutoff_and_wrong_date_runs(self):
        for current in (
            datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            datetime(2026, 8, 25, 14, 2, tzinfo=UTC),
        ):
            with self.assertRaisesRegex(ValueError, "before 10:01|New York date"):
                produce_daily_source_from_providers(
                    prerequisite=_prerequisite(),
                    alpaca=object(),  # type: ignore[arg-type]
                    sec=object(),  # type: ignore[arg-type]
                    now=lambda current=current: current,
                )

    def test_registration_audit_is_hash_bound_and_unarmed(self):
        audit = json.loads(REGISTRATION_AUDIT.read_text(encoding="utf-8"))
        unsigned = {
            key: value for key, value in audit.items() if key != "content_sha256"
        }
        self.assertEqual(
            canonical_fingerprint(unsigned), audit["content_sha256"]
        )
        contract = load_daily_source_contract(
            ROOT
            / "research"
            / "strategy"
            / "prospective-daily-scanner-micro-source-v0.1.json"
        )
        self.assertEqual(
            audit["contract"]["content_sha256"], contract["content_sha256"]
        )
        for row in audit["bound_files"]:
            self.assertEqual(
                hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest(),
                row["file_sha256"],
            )
        authority = audit["authority_boundary"]
        self.assertFalse(authority["provider_data_read_performed"])
        self.assertFalse(authority["databento_quote_or_download_performed"])
        self.assertFalse(authority["broker_order_performed"])
        self.assertEqual(authority["incremental_purchase_authorized_usd"], "0")


if __name__ == "__main__":
    unittest.main()
