from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from momentumbot.causal_market_discovery import (
    CAUSAL_MARKET_DISCOVERY_POLICY_ID,
    build_causal_market_discovery_manifest,
    build_market_candidate_payload,
    causal_market_discovery_v0_1_manifest,
    causal_market_discovery_v0_2_manifest,
    identity_membership_as_acquisition_assets,
    load_market_candidate_payload,
    strategy_profile_manifest,
)
from momentumbot.historical_data import (
    DiscoveryAuditRow,
    DiscoveryResult,
    DiscoveryRow,
)
from momentumbot.identity_resolved_universe import (
    identity_resolved_membership_fingerprint,
)
from momentumbot.models import current_general_2026


def _member(ticker: str, mic: str) -> dict[str, object]:
    return {
        "ticker": ticker,
        "included": True,
        "reason": "included_provisional_common_equity",
        "security_record_count": 1,
        "common_type_record_count": 1,
        "accepted_identity_count": 1,
        "metadata_statuses": ["no_name_conflict_detected"],
        "selected_security_type": "CS",
        "selected_primary_exchange": mic,
        "selected_cik": "1",
        "selected_composite_figi": f"FIGI-{ticker}",
        "identity_identifier_kind": "composite_figi",
        "identity_identifier": f"FIGI-{ticker}",
    }


class CausalMarketDiscoveryTests(unittest.TestCase):
    def test_exchange_translation_preserves_every_frozen_member(self) -> None:
        rows = [
            _member("AAA", "XNAS"),
            _member("BBB", "XNYS"),
            _member("CCC", "XASE"),
            _member("DDD", "ARCX"),
            _member("EEE", "BATS"),
        ]

        assets = identity_membership_as_acquisition_assets(rows)

        self.assertEqual(len(assets), 5)
        self.assertEqual(
            {row["exchange"] for row in assets},
            {"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS"},
        )
        self.assertEqual(
            [row["symbol"] for row in assets],
            ["AAA", "BBB", "CCC", "DDD", "EEE"],
        )

    def test_strategy_profile_fingerprint_changes_with_policy(self) -> None:
        profile = current_general_2026()
        changed = replace(profile, min_percent_gain=11.0)

        self.assertNotEqual(
            strategy_profile_manifest(profile)["fingerprint"],
            strategy_profile_manifest(changed)["fingerprint"],
        )

    def test_manifest_is_complete_only_through_market_discovery(self) -> None:
        member = _member("AAA", "XNAS")
        membership_hash = identity_resolved_membership_fingerprint([member])
        assets = identity_membership_as_acquisition_assets([member])
        from momentumbot.historical_data import asset_master_fingerprint

        row = DiscoveryRow(
            symbol="AAA",
            status="active",
            exchange="NASDAQ",
            previous_close=2.0,
            target_high=3.0,
            max_session_gain_pct=50.0,
            max_session_rvol_upper_bound=6.0,
            max_session_rvol=5.5,
            rvol_history_sessions=50,
            average_daily_volume_50=100_000.0,
            first_market_qualified_at="2025-04-03T11:01:00+00:00",
            minute_bars=100,
            first_market_qualified_bar_started_at=(
                "2025-04-03T11:00:00+00:00"
            ),
        )
        result = DiscoveryResult(
            asset_count=1,
            listed_asset_count=1,
            daily_superset_count=1,
            rvol_prefilter_count=1,
            market_candidate_count=1,
            asset_master_sha256=asset_master_fingerprint(assets),
            asset_status_counts={"active": 1},
            rows=(row,),
            minutes={},
            contexts={},
            rvol_curves={},
            acquisition_audit=(
                DiscoveryAuditRow(
                    symbol="AAA",
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
                    first_market_qualified_at="2025-04-03T11:01:00+00:00",
                    first_market_qualified_bar_started_at=(
                        "2025-04-03T11:00:00+00:00"
                    ),
                ),
            ),
        )
        payload = {
            "artifact_id": "identity-resolved-universe-v0.1",
            "trading_date": "2025-04-03",
            "policy_fingerprint": "identity-policy",
            "summary": {
                "identity_accepted_ticker_count": 1,
                "membership_sha256": membership_hash,
            },
        }

        manifest = build_causal_market_discovery_manifest(
            trading_date="2025-04-03",
            membership_rows=[member],
            membership_payload=payload,
            membership_bundle_manifest={"content_sha256": "bundle"},
            result=result,
            profile=current_general_2026(),
        )

        self.assertEqual(
            causal_market_discovery_v0_1_manifest()["fingerprint"],
            "b6628f08eff913fbe30f465a9792d71fe4f70ac028ea23e4858277bb6068da1e",
        )
        self.assertEqual(manifest["artifact_id"], CAUSAL_MARKET_DISCOVERY_POLICY_ID)
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(
            manifest["discovery_policy"],
            causal_market_discovery_v0_2_manifest(),
        )
        self.assertEqual(
            causal_market_discovery_v0_2_manifest()["fingerprint"],
            "dbcbebae2b785ef8af68a37122658e02aa6fec3310c03581426273c5b66516d5",
        )
        self.assertNotEqual(
            causal_market_discovery_v0_1_manifest()["fingerprint"],
            causal_market_discovery_v0_2_manifest()["fingerprint"],
        )
        self.assertTrue(
            manifest["eligibility"]["causal_market_discovery_complete"]
        )
        self.assertEqual(manifest["summary"]["acquisition_decision_count"], 1)
        self.assertFalse(manifest["eligibility"]["full_feature_snapshot_complete"])
        self.assertFalse(manifest["eligibility"]["universe_complete"])
        self.assertFalse(manifest["knowledge_policy"]["uses_benchmark_labels"])
        candidates = build_market_candidate_payload(
            trading_date="2025-04-03",
            membership_rows=[member],
            result=result,
        )
        self.assertEqual(candidates["candidate_count"], 1)
        self.assertEqual(candidates["schema_version"], 2)
        self.assertEqual(candidates["rows"][0]["symbol"], "AAA")
        self.assertEqual(
            candidates["rows"][0]["first_market_qualified_bar_started_at"],
            "2025-04-03T11:00:00+00:00",
        )
        self.assertEqual(
            candidates["rows"][0]["first_market_qualified_at"],
            "2025-04-03T11:01:00+00:00",
        )
        self.assertEqual(
            candidates["rows"][0]["selected_cik"], member["selected_cik"]
        )
        self.assertEqual(
            manifest["summary"]["causal_market_candidate_set_sha256"],
            candidates["content_sha256"],
        )
        mismatched_audit = replace(
            result.acquisition_audit[0],
            first_market_qualified_bar_started_at=(
                "2025-04-03T11:01:00+00:00"
            ),
            first_market_qualified_at="2025-04-03T11:02:00+00:00",
        )
        with self.assertRaisesRegex(ValueError, "disagree with results"):
            build_causal_market_discovery_manifest(
                trading_date="2025-04-03",
                membership_rows=[member],
                membership_payload=payload,
                membership_bundle_manifest={"content_sha256": "bundle"},
                result=replace(
                    result,
                    acquisition_audit=(mismatched_audit,),
                ),
                profile=current_general_2026(),
            )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest["files"] = {"market_candidates": "market-candidates.json"}
            (root / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            (root / "market-candidates.json").write_text(
                json.dumps(candidates), encoding="utf-8"
            )
            loaded_rows, loaded_payload, loaded_manifest = (
                load_market_candidate_payload(root)
            )
            self.assertEqual(loaded_rows, candidates["rows"])
            self.assertEqual(loaded_payload, candidates)
            self.assertEqual(loaded_manifest, manifest)

            tampered = json.loads(json.dumps(candidates))
            tampered["rows"][0]["first_market_qualified_bar_started_at"] = (
                "2025-04-03T11:00:30+00:00"
            )
            from momentumbot.identity_resolved_universe import json_fingerprint

            tampered["content_sha256"] = json_fingerprint(
                {
                    key: value
                    for key, value in tampered.items()
                    if key != "content_sha256"
                }
            )
            tampered_manifest = json.loads(json.dumps(manifest))
            tampered_manifest["summary"][
                "causal_market_candidate_set_sha256"
            ] = tampered["content_sha256"]
            (root / "manifest.json").write_text(
                json.dumps(tampered_manifest), encoding="utf-8"
            )
            (root / "market-candidates.json").write_text(
                json.dumps(tampered), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "plus one minute"):
                load_market_candidate_payload(root)

    def test_manifest_rejects_member_without_required_daily_basis(self) -> None:
        member = _member("AAA", "XNAS")
        membership_hash = identity_resolved_membership_fingerprint([member])
        assets = identity_membership_as_acquisition_assets([member])
        from momentumbot.historical_data import asset_master_fingerprint

        audit = DiscoveryAuditRow(
            symbol="AAA",
            disposition="excluded_missing_daily_scan_basis",
            daily_scan_basis_available=False,
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
        )
        result = DiscoveryResult(
            asset_count=1,
            listed_asset_count=1,
            daily_superset_count=0,
            rvol_prefilter_count=0,
            market_candidate_count=0,
            asset_master_sha256=asset_master_fingerprint(assets),
            asset_status_counts={"active": 1},
            rows=(),
            minutes={},
            contexts={},
            rvol_curves={},
            acquisition_audit=(audit,),
        )
        payload = {
            "artifact_id": "identity-resolved-universe-v0.1",
            "trading_date": "2025-04-03",
            "policy_fingerprint": "identity-policy",
            "summary": {
                "identity_accepted_ticker_count": 1,
                "membership_sha256": membership_hash,
            },
        }

        with self.assertRaisesRegex(ValueError, "daily scan basis"):
            build_causal_market_discovery_manifest(
                trading_date="2025-04-03",
                membership_rows=[member],
                membership_payload=payload,
                membership_bundle_manifest={"content_sha256": "bundle"},
                result=result,
                profile=current_general_2026(),
            )


if __name__ == "__main__":
    unittest.main()
