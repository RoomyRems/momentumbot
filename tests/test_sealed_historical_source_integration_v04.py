from __future__ import annotations

from contextlib import ExitStack, redirect_stderr
from datetime import date
import hashlib
import io
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from momentumbot.historical_profile_union_v01 import (
    historical_profile_union_v0_1,
    historical_profile_union_v0_1_manifest,
)
from momentumbot.scanner_source_inputs_v03 import (
    SOURCE_HASH_NAMES,
    load_scanner_source_input_bundle,
    write_scanner_source_input_bundle,
)
from scripts import build_causal_news_enrichment_v04 as news_builder
from scripts import build_causal_scanner_snapshot_v04 as scanner_builder


TRADING_DATE = "2025-04-03"
SHA = "a" * 64


def _source_hashes() -> dict[str, str]:
    return {
        name: hashlib.sha256(name.encode("ascii")).hexdigest()
        for name in SOURCE_HASH_NAMES[:-1]
    }


def _frame(*, raw: bool) -> pd.DataFrame:
    index = pd.date_range("2025-04-03T11:00:00Z", periods=1, freq="1min")
    values = {"close": [2.0]}
    if raw:
        values["volume"] = [1_000.0]
    return pd.DataFrame(values, index=index)


class SealedHistoricalSourceIntegrationV04Tests(unittest.TestCase):
    def test_exact_fixed_tuple_and_mode_guards(self) -> None:
        scanner_builder.validate_fixed_scanner_mode()
        news_builder.validate_fixed_news_mode()
        scanner_changes = {
            "gain_basis": "raw_previous_close_raw_target_close_v0.1",
            "market_discovery_id": "causal-market-discovery-v0.2",
            "float_policy_id": "causal-sec-float-v0.1",
            "news_policy_id": "causal-alpaca-news-v0.1",
            "scanner_policy_id": "causal-scanner-snapshot-v0.2",
            "scanner_artifact_id": "causal-scanner-snapshot-v0.2",
            "source_input_artifact_id": "causal-scanner-source-inputs-v0.1",
            "acquisition_profile_id": "current-general-2026",
        }
        for name, value in scanner_changes.items():
            with self.subTest(scanner=name), self.assertRaisesRegex(
                ValueError, "frozen raw/split integration tuple"
            ):
                scanner_builder.validate_fixed_scanner_mode(**{name: value})
        news_changes = {
            "market_discovery_id": "causal-market-discovery-v0.2",
            "float_policy_id": "causal-sec-float-v0.1",
            "news_policy_id": "causal-alpaca-news-v0.1",
            "acquisition_profile_id": "current-general-2026",
        }
        for name, value in news_changes.items():
            with self.subTest(news=name), self.assertRaisesRegex(
                ValueError, "frozen integration tuple"
            ):
                news_builder.validate_fixed_news_mode(**{name: value})

    def test_removed_cli_basis_switch_fails_before_files_or_provider(self) -> None:
        with patch.object(scanner_builder, "_load_json") as load_json, patch.object(
            scanner_builder.AlpacaDataClient, "from_env"
        ) as provider, redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            scanner_builder.main(
                [
                    "--phase",
                    "acquire-source-inputs",
                    "--census-root",
                    "/does/not/matter",
                    "--gain-basis",
                    "raw",
                ]
            )
        load_json.assert_not_called()
        provider.assert_not_called()
        with patch.object(news_builder, "_load_market_root") as load_market, patch.object(
            news_builder.AlpacaDataClient, "from_env"
        ) as news_provider, redirect_stderr(io.StringIO()), self.assertRaises(
            SystemExit
        ):
            news_builder.main(
                [
                    "--census-root",
                    "/does/not/matter",
                    "--float-policy-id",
                    "causal-sec-float-v0.1",
                ]
            )
        load_market.assert_not_called()
        news_provider.assert_not_called()

    def test_source_sidecar_round_trip_and_compressed_tamper_fail_closed(self) -> None:
        profile = historical_profile_union_v0_1()
        rank = {"AAA": _frame(raw=False)}
        raw = {"AAA": _frame(raw=True)}
        rvol = {
            "AAA": pd.Series(
                [6.0],
                index=raw["AAA"].index,
                dtype="float64",
            )
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "sidecar"
            manifest = write_scanner_source_input_bundle(
                root,
                trading_date=date.fromisoformat(TRADING_DATE),
                profile=profile,
                membership_symbols=["AAA"],
                candidate_symbols=["AAA"],
                previous_close_by_symbol={"AAA": 1.0},
                rank_split_minute_bars_by_symbol=rank,
                candidate_raw_minute_bars_by_symbol=raw,
                candidate_exact_rvol_by_symbol=rvol,
                upstream_source_hashes=_source_hashes(),
            )
            loaded, loaded_manifest = load_scanner_source_input_bundle(
                root,
                profile=profile,
            )
            self.assertEqual(loaded_manifest, manifest)
            self.assertEqual(loaded.candidate_symbols, ("AAA",))
            with (root / "market-inputs.jsonl.gz").open("ab") as handle:
                handle.write(b"tamper")
            with self.assertRaisesRegex(ValueError, "compressed file hash"):
                load_scanner_source_input_bundle(root, profile=profile)

    def test_empty_candidate_date_is_a_valid_complete_reconstruction(self) -> None:
        empty = scanner_builder.DiscoveryResult(
            asset_count=1,
            listed_asset_count=1,
            daily_superset_count=0,
            rvol_prefilter_count=0,
            market_candidate_count=0,
            asset_master_sha256=SHA,
            asset_status_counts={"active": 1},
            rows=(),
            minutes={},
            contexts={},
            rvol_curves={},
        )
        scanner_builder.verify_reconstructed_market_candidates([], empty)

    def _patch_preflight(self, stack: ExitStack, *, source_root: dict[str, object]):
        market_root = {"dates": [TRADING_DATE], "content_sha256": "b" * 64}
        float_root = {
            "dates": [TRADING_DATE],
            "content_sha256": "c" * 64,
        }
        news_root = {"dates": [TRADING_DATE], "content_sha256": "d" * 64}

        def load_json(path: Path) -> dict[str, object]:
            text = str(path)
            if scanner_builder.FIXED_SOURCE_INPUT_ARTIFACT_ID in text:
                return source_root
            if scanner_builder.FIXED_NEWS_POLICY_ID in text:
                return news_root
            return market_root

        stack.enter_context(patch.object(scanner_builder, "_load_json", side_effect=load_json))
        stack.enter_context(patch.object(scanner_builder, "_validate_market_root"))
        stack.enter_context(patch.object(scanner_builder, "_validate_news_root"))
        stack.enter_context(
            patch.object(scanner_builder, "load_causal_float_root", return_value=float_root)
        )
        membership_manifest = {"content_sha256": SHA}
        membership_payload = {
            "summary": {"membership_sha256": "e" * 64}
        }
        stack.enter_context(
            patch.object(
                scanner_builder,
                "load_identity_resolved_universe",
                return_value=([{"ticker": "AAA"}], membership_payload, membership_manifest),
            )
        )
        candidate_rows = [{"symbol": "AAA"}]
        candidate_payload = {"content_sha256": "f" * 64}
        market_date = {
            "trading_date": TRADING_DATE,
            "files": {"float_target_basis": "float-target-basis.json"},
            "summary": {"float_target_basis_sha256": "6" * 64},
        }
        stack.enter_context(
            patch.object(
                scanner_builder,
                "load_market_candidate_payload",
                return_value=(candidate_rows, candidate_payload, market_date),
            )
        )
        stack.enter_context(
            patch.object(
                scanner_builder,
                "load_float_target_basis",
                return_value=({}, {"content_sha256": "6" * 64}),
            )
        )
        float_date = {"summary": {"records_sha256": "1" * 64}}
        stack.enter_context(
            patch.object(
                scanner_builder,
                "load_causal_float_records",
                return_value=([{"symbol": "AAA"}], float_date),
            )
        )
        news_date = {
            "trading_date": TRADING_DATE,
            "summary": {
                "full_window_events_sha256": "4" * 64,
                "qualification_statuses_sha256": "5" * 64,
            },
        }
        stack.enter_context(
            patch.object(
                scanner_builder,
                "load_publication_timed_news",
                return_value=([], [{"symbol": "AAA"}], news_date),
            )
        )
        stack.enter_context(patch.object(scanner_builder, "validate_cross_artifact_lineage"))
        return market_root, float_root, news_root, candidate_rows

    def test_freeze_phase_is_provider_free_and_exactly_rebuilds(self) -> None:
        union = historical_profile_union_v0_1_manifest()
        upstream_hashes = {name: SHA for name in SOURCE_HASH_NAMES[:-1]}
        all_source_hashes = {
            **upstream_hashes,
            "reacquired_market_inputs": "7" * 64,
        }
        source_date_manifest = {
            "trading_date": TRADING_DATE,
            "summary": {"logical_records_sha256": "7" * 64},
            "source_hashes": all_source_hashes,
        }
        source_hashes = {
            "membership": SHA,
            "market": "b" * 64,
            "float": "c" * 64,
            "news": "d" * 64,
        }
        source_root = {
            "dates": [TRADING_DATE],
            "source_bundle_hashes": dict(sorted(source_hashes.items())),
            "acquisition_profile_union": union,
            "strategy_profiles_modified": False,
            "date_manifests": [source_date_manifest],
            "content_sha256": "2" * 64,
        }
        loaded_inputs = SimpleNamespace(
            membership_symbols=("AAA",),
            previous_close_by_symbol={"AAA": 1.0},
            rank_split_minute_bars_by_symbol={"AAA": _frame(raw=False)},
            candidate_raw_minute_bars_by_symbol={"AAA": _frame(raw=True)},
            candidate_exact_rvol_by_symbol={
                "AAA": pd.Series([6.0], index=_frame(raw=True).index)
            },
            source_hashes=all_source_hashes,
        )
        payload: dict[str, object] = {"rows": [{"synthetic": True}]}
        manifest: dict[str, object] = {
            "trading_date": TRADING_DATE,
            "summary": {"candidate_minute_disposition_count": 1},
        }
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            self._patch_preflight(stack, source_root=source_root)
            stack.enter_context(
                patch.object(
                    scanner_builder,
                    "expected_upstream_source_hashes",
                    return_value=upstream_hashes,
                )
            )
            stack.enter_context(
                patch.object(scanner_builder, "validate_scanner_source_input_root_manifest")
            )
            source_loader = stack.enter_context(
                patch.object(
                    scanner_builder,
                    "load_scanner_source_input_bundle",
                    return_value=(loaded_inputs, source_date_manifest),
                )
            )
            build_rows = stack.enter_context(
                patch.object(
                    scanner_builder,
                    "build_scanner_snapshot_rows",
                    return_value=[{"synthetic": True}],
                )
            )
            stack.enter_context(
                patch.object(
                    scanner_builder,
                    "build_causal_scanner_snapshot_artifacts",
                    return_value=(payload, manifest),
                )
            )
            stack.enter_context(
                patch.object(
                    scanner_builder,
                    "load_causal_scanner_snapshot",
                    side_effect=lambda *args, **kwargs: (
                        [{"synthetic": True}],
                        payload,
                        manifest,
                    ),
                )
            )
            provider = stack.enter_context(
                patch.object(scanner_builder.AlpacaDataClient, "from_env")
            )
            result = scanner_builder.main(
                [
                    "--phase",
                    "freeze-snapshots",
                    "--census-root",
                    temporary,
                ]
            )
        self.assertEqual(result, 0)
        provider.assert_not_called()
        self.assertEqual(source_loader.call_count, 2)
        self.assertEqual(build_rows.call_count, 2)

    def test_freeze_rejects_rehashed_stale_per_date_sidecar_lineage(self) -> None:
        upstream = {name: SHA for name in SOURCE_HASH_NAMES[:-1]}
        expected = {**upstream, "reacquired_market_inputs": "7" * 64}
        manifest = {
            "summary": {"logical_records_sha256": "7" * 64},
            "source_hashes": expected,
        }
        scanner_builder.validate_loaded_source_lineage(
            source_inputs=SimpleNamespace(source_hashes=expected),
            source_manifest=manifest,
            expected_upstream_hashes=upstream,
        )
        stale = dict(expected)
        stale["market_candidates"] = "8" * 64
        with self.assertRaisesRegex(ValueError, "per-date lineage mismatch"):
            scanner_builder.validate_loaded_source_lineage(
                source_inputs=SimpleNamespace(source_hashes=stale),
                source_manifest={**manifest, "source_hashes": stale},
                expected_upstream_hashes=upstream,
            )

    def test_acquire_phase_never_invokes_scanner_validator(self) -> None:
        union = historical_profile_union_v0_1_manifest()
        source_root = {"unused": True}
        source_hashes = {name: SHA for name in SOURCE_HASH_NAMES}
        sidecar_manifest: dict[str, object] = {
            "trading_date": TRADING_DATE,
            "source_hashes": source_hashes,
        }
        frame = _frame(raw=True)
        rank = _frame(raw=False)
        reconstructed = SimpleNamespace(minutes={"AAA": frame}, rvol_curves={
            "AAA": pd.Series([6.0], index=frame.index)
        })
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            self._patch_preflight(stack, source_root=source_root)
            stack.enter_context(
                patch.object(
                    scanner_builder,
                    "identity_membership_as_acquisition_assets",
                    return_value=[],
                )
            )
            stack.enter_context(patch.object(scanner_builder, "discover_market_day", return_value=reconstructed))
            stack.enter_context(patch.object(scanner_builder, "verify_reconstructed_market_candidates"))
            stack.enter_context(
                patch.object(
                    scanner_builder,
                    "reacquire_split_rank_market_inputs",
                    return_value=({"AAA": 1.0}, {"AAA": rank}),
                )
            )
            stack.enter_context(patch.object(scanner_builder, "validate_candidate_previous_closes"))
            stack.enter_context(
                patch.object(
                    scanner_builder,
                    "write_scanner_source_input_bundle",
                    return_value=sidecar_manifest,
                )
            )
            stack.enter_context(patch.object(scanner_builder, "_write_json"))
            source_loader = stack.enter_context(
                patch.object(
                    scanner_builder,
                    "load_scanner_source_input_bundle",
                )
            )
            stack.enter_context(
                patch.object(
                    scanner_builder,
                    "build_scanner_source_input_root_manifest",
                    return_value={
                        "acquisition_profile_union": union,
                        "content_sha256": "3" * 64,
                    },
                )
            )
            stack.enter_context(
                patch.object(scanner_builder, "validate_scanner_source_input_root_manifest")
            )
            scanner_rows = stack.enter_context(
                patch.object(scanner_builder, "build_scanner_snapshot_rows")
            )
            scanner_artifact = stack.enter_context(
                patch.object(scanner_builder, "build_causal_scanner_snapshot_artifacts")
            )
            scanner_loader = stack.enter_context(
                patch.object(scanner_builder, "load_causal_scanner_snapshot")
            )
            stack.enter_context(
                patch.object(
                    scanner_builder.AlpacaDataClient,
                    "from_env",
                    return_value=SimpleNamespace(),
                )
            )
            result = scanner_builder.main(
                [
                    "--phase",
                    "acquire-source-inputs",
                    "--census-root",
                    temporary,
                ]
            )
        self.assertEqual(result, 0)
        scanner_rows.assert_not_called()
        scanner_artifact.assert_not_called()
        scanner_loader.assert_not_called()
        source_loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
