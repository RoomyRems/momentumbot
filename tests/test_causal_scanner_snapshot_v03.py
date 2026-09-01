from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date, time
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from momentumbot import causal_scanner_snapshot_v02 as legacy
from momentumbot.causal_scanner_snapshot_v03 import (
    CAUSAL_SCANNER_SNAPSHOT_V0_3_ARTIFACT_ID,
    build_causal_scanner_snapshot_artifacts,
    build_scanner_snapshot_rows,
    causal_scanner_snapshot_v0_3_manifest,
    load_causal_scanner_snapshot,
    validate_causal_scanner_snapshot,
)
from momentumbot.models import current_general_2026
from momentumbot.scanner_source_inputs_v03 import (
    ARTIFACT_ID as SOURCE_INPUT_ARTIFACT_ID,
    FORMAT_ID as SOURCE_INPUT_FORMAT_ID,
    SOURCE_HASH_NAMES,
    load_scanner_source_input_bundle,
    write_scanner_source_input_bundle,
)


def _profile():
    return replace(current_general_2026(), no_new_entries_after=time(7, 2))


def _frame(close: float, *, raw: bool) -> pd.DataFrame:
    index = pd.date_range("2025-04-03T11:00:00Z", periods=1, freq="1min")
    values: dict[str, list[float]] = {"close": [close]}
    if raw:
        values["volume"] = [1_000.0]
    return pd.DataFrame(values, index=index)


def _candidate(symbol: str, previous: float) -> dict[str, object]:
    return {
        "symbol": symbol,
        "previous_close": previous,
        "first_market_qualified_bar_started_at": "2025-04-03T11:00:00+00:00",
        "first_market_qualified_at": "2025-04-03T11:01:00+00:00",
    }


def _float(symbol: str) -> dict[str, object]:
    return {
        "symbol": symbol,
        "float_classification": "pass",
        "float_pillar_pass": True,
        "estimated_float_shares": 5_000_000,
        "float_asof": "2025-04-01T12:00:00+00:00",
        "method": "test-causal-float",
        "sec_status": "success",
    }


def _status(symbol: str) -> dict[str, object]:
    return {"symbol": symbol, "provider_status": "success"}


def _rvol() -> pd.Series:
    return pd.Series(
        [6.0],
        index=pd.date_range("2025-04-03T11:00:00Z", periods=1, freq="1min"),
    )


def _upstream_hashes() -> dict[str, str]:
    return {
        name: hashlib.sha256(name.encode("ascii")).hexdigest()
        for name in SOURCE_HASH_NAMES[:-1]
    }


def _rehash_artifact(payload: dict[str, object], manifest: dict[str, object]) -> None:
    rows = payload["rows"]
    assert isinstance(rows, list)
    payload["ordered_records_sha256"] = legacy.ordered_snapshot_records_fingerprint(rows)
    payload["content_sha256"] = legacy._json_fingerprint(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )
    summary = manifest["summary"]
    assert isinstance(summary, dict)
    summary["ordered_records_sha256"] = payload["ordered_records_sha256"]
    summary["records_content_sha256"] = payload["content_sha256"]
    summary["disposition_counts"] = dict(
        sorted(
            {
                str(row["disposition"]): sum(
                    1 for value in rows if value["disposition"] == row["disposition"]
                )
                for row in rows
            }.items()
        )
    )
    manifest["content_sha256"] = legacy._json_fingerprint(
        {key: value for key, value in manifest.items() if key != "content_sha256"}
    )


class CausalScannerSnapshotV03Tests(unittest.TestCase):
    def _values(
        self,
        *,
        raw_aaa: float = 100.0,
        split_aaa: float = 10.0,
        previous_aaa: float = 8.0,
    ) -> dict[str, object]:
        candidates = [_candidate("AAA", previous_aaa), _candidate("BBB", 2.0)]
        rank = {
            "AAA": _frame(split_aaa, raw=False),
            "BBB": _frame(3.0, raw=False),
        }
        raw = {
            "AAA": _frame(raw_aaa, raw=True),
            "BBB": _frame(3.0, raw=True),
        }
        previous = {"AAA": previous_aaa, "BBB": 2.0}
        kwargs = {
            "trading_date": date(2025, 4, 3),
            "profile": _profile(),
            "candidate_rows": candidates,
            "float_records": [_float("AAA"), _float("BBB")],
            "news_events": [],
            "news_statuses": [_status("AAA"), _status("BBB")],
            "membership_symbols": ["AAA", "BBB"],
            "previous_close_by_symbol": previous,
            "rank_split_minute_bars_by_symbol": rank,
            "candidate_raw_minute_bars_by_symbol": raw,
            "candidate_exact_rvol_by_symbol": {"AAA": _rvol(), "BBB": _rvol()},
        }
        rows = build_scanner_snapshot_rows(**kwargs)
        return {**kwargs, "rows": rows}

    def test_policy_and_source_tape_have_new_versioned_identity(self) -> None:
        policy = causal_scanner_snapshot_v0_3_manifest()
        self.assertEqual(policy["policy_id"], CAUSAL_SCANNER_SNAPSHOT_V0_3_ARTIFACT_ID)
        self.assertEqual(policy["source_float_policy_id"], "causal-sec-float-v0.2")
        self.assertEqual(policy["canonical_source_input_artifact_id"], SOURCE_INPUT_ARTIFACT_ID)
        self.assertNotIn("candidate_rank_frame_close_match_tolerance", policy)
        self.assertEqual(
            policy["candidate_raw_split_timestamp_match_rule"],
            "exact_timestamp_index_equality_required_without_close_or_volume_"
            "equality_between_distinct_adjustment_bases",
        )
        self.assertEqual(SOURCE_INPUT_ARTIFACT_ID, "causal-scanner-source-inputs-v0.2")
        self.assertEqual(SOURCE_INPUT_FORMAT_ID, "streamed-canonical-market-inputs-v2")
        self.assertEqual(
            policy["supersedes_policy_fingerprint"],
            legacy.causal_scanner_snapshot_v0_2_manifest()["fingerprint"],
        )

    def test_raw_price_is_separate_from_split_gain_and_rank(self) -> None:
        values = self._values()
        rows = {str(row["symbol"]): row for row in values["rows"]}
        aaa = rows["AAA"]
        bbb = rows["BBB"]
        self.assertEqual(aaa["price"], 100.0)
        self.assertEqual(aaa["percent_gain"], 25.0)
        self.assertFalse(aaa["price_pillar_pass"])
        self.assertTrue(aaa["gain_pillar_pass"])
        self.assertEqual(aaa["top_gainer_rank"], 2)
        self.assertEqual(bbb["top_gainer_rank"], 1)
        self.assertEqual(aaa["rank_leader_symbol"], "BBB")

        affordable = self._values(raw_aaa=10.0)
        affordable_aaa = next(row for row in affordable["rows"] if row["symbol"] == "AAA")
        self.assertEqual(affordable_aaa["price"], 10.0)
        self.assertTrue(affordable_aaa["price_pillar_pass"])
        for field in ("percent_gain", "gain_pillar_pass", "top_gainer_rank", "rank_leader_symbol"):
            self.assertEqual(affordable_aaa[field], aaa[field])

    def test_forward_and_reverse_scale_factors_cancel_from_gain_and_rank(self) -> None:
        base = self._values(raw_aaa=10.0, split_aaa=10.0, previous_aaa=8.0)
        forward_adjusted = self._values(raw_aaa=10.0, split_aaa=1.0, previous_aaa=0.8)
        reverse_adjusted = self._values(raw_aaa=10.0, split_aaa=100.0, previous_aaa=80.0)
        observed = []
        for values in (base, forward_adjusted, reverse_adjusted):
            row = next(item for item in values["rows"] if item["symbol"] == "AAA")
            observed.append((row["price"], row["percent_gain"], row["top_gainer_rank"]))
        self.assertEqual(observed, [(10.0, 25.0, 2)] * 3)

    def test_normalized_sidecar_and_snapshot_round_trip(self) -> None:
        values = self._values()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sidecar_root = root / "source-input"
            sidecar_manifest = write_scanner_source_input_bundle(
                sidecar_root,
                trading_date=values["trading_date"],
                profile=values["profile"],
                membership_symbols=values["membership_symbols"],
                candidate_symbols=["AAA", "BBB"],
                previous_close_by_symbol=values["previous_close_by_symbol"],
                rank_split_minute_bars_by_symbol=values["rank_split_minute_bars_by_symbol"],
                candidate_raw_minute_bars_by_symbol=values["candidate_raw_minute_bars_by_symbol"],
                candidate_exact_rvol_by_symbol=values["candidate_exact_rvol_by_symbol"],
                upstream_source_hashes=_upstream_hashes(),
            )
            loaded, loaded_manifest = load_scanner_source_input_bundle(
                sidecar_root, profile=values["profile"]
            )
            self.assertEqual(loaded_manifest, sidecar_manifest)
            self.assertEqual(
                loaded.rank_split_minute_bars_by_symbol["AAA"].iloc[0]["close"],
                10.0,
            )
            self.assertEqual(
                loaded.candidate_raw_minute_bars_by_symbol["AAA"].iloc[0]["close"],
                100.0,
            )

            payload, manifest = build_causal_scanner_snapshot_artifacts(
                trading_date=values["trading_date"],
                profile=values["profile"],
                candidate_rows=values["candidate_rows"],
                membership_symbols=values["membership_symbols"],
                rows=values["rows"],
                source_hashes=loaded.source_hashes,
                previous_close_by_symbol=loaded.previous_close_by_symbol,
                rank_split_minute_bars_by_symbol=loaded.rank_split_minute_bars_by_symbol,
                candidate_raw_minute_bars_by_symbol=loaded.candidate_raw_minute_bars_by_symbol,
            )
            snapshot_root = root / "snapshot"
            snapshot_root.mkdir()
            (snapshot_root / "scanner-snapshot.json").write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (snapshot_root / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            replayed, replay_payload, replay_manifest = load_causal_scanner_snapshot(
                snapshot_root,
                candidate_rows=values["candidate_rows"],
                profile=values["profile"],
                source_inputs=loaded,
            )
            self.assertEqual(replayed, values["rows"])
            self.assertEqual(replay_payload, payload)
            self.assertEqual(replay_manifest, manifest)

    def test_artifact_loaders_reject_duplicate_json_keys(self) -> None:
        values = self._values()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sidecar_root = root / "source-input"
            write_scanner_source_input_bundle(
                sidecar_root,
                trading_date=values["trading_date"],
                profile=values["profile"],
                membership_symbols=values["membership_symbols"],
                candidate_symbols=["AAA", "BBB"],
                previous_close_by_symbol=values["previous_close_by_symbol"],
                rank_split_minute_bars_by_symbol=values[
                    "rank_split_minute_bars_by_symbol"
                ],
                candidate_raw_minute_bars_by_symbol=values[
                    "candidate_raw_minute_bars_by_symbol"
                ],
                candidate_exact_rvol_by_symbol=values[
                    "candidate_exact_rvol_by_symbol"
                ],
                upstream_source_hashes=_upstream_hashes(),
            )
            sidecar_manifest_path = sidecar_root / "manifest.json"
            original_sidecar = sidecar_manifest_path.read_text(encoding="utf-8")
            sidecar_manifest_path.write_text(
                original_sidecar.replace(
                    '  "artifact_id":',
                    '  "artifact_id": "shadow",\n  "artifact_id":',
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                load_scanner_source_input_bundle(
                    sidecar_root,
                    profile=values["profile"],
                )
            sidecar_manifest_path.write_text(original_sidecar, encoding="utf-8")
            loaded, _ = load_scanner_source_input_bundle(
                sidecar_root,
                profile=values["profile"],
            )

            payload, manifest = build_causal_scanner_snapshot_artifacts(
                trading_date=values["trading_date"],
                profile=values["profile"],
                candidate_rows=values["candidate_rows"],
                membership_symbols=values["membership_symbols"],
                rows=values["rows"],
                source_hashes=loaded.source_hashes,
                previous_close_by_symbol=loaded.previous_close_by_symbol,
                rank_split_minute_bars_by_symbol=(
                    loaded.rank_split_minute_bars_by_symbol
                ),
                candidate_raw_minute_bars_by_symbol=(
                    loaded.candidate_raw_minute_bars_by_symbol
                ),
            )
            snapshot_root = root / "snapshot"
            snapshot_root.mkdir()
            (snapshot_root / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            snapshot_payload = json.dumps(payload, indent=2, sort_keys=True) + "\n"
            (snapshot_root / "scanner-snapshot.json").write_text(
                snapshot_payload.replace(
                    '  "artifact_id":',
                    '  "artifact_id": "shadow",\n  "artifact_id":',
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                load_causal_scanner_snapshot(
                    snapshot_root,
                    candidate_rows=values["candidate_rows"],
                    profile=values["profile"],
                    source_inputs=loaded,
                )

    def test_rehashed_raw_price_and_normalized_gain_tampering_fail(self) -> None:
        values = self._values()
        source_hashes = {**_upstream_hashes(), "reacquired_market_inputs": "f" * 64}
        payload, manifest = build_causal_scanner_snapshot_artifacts(
            trading_date=values["trading_date"],
            profile=values["profile"],
            candidate_rows=values["candidate_rows"],
            membership_symbols=values["membership_symbols"],
            rows=values["rows"],
            source_hashes=source_hashes,
            previous_close_by_symbol=values["previous_close_by_symbol"],
            rank_split_minute_bars_by_symbol=values["rank_split_minute_bars_by_symbol"],
            candidate_raw_minute_bars_by_symbol=values["candidate_raw_minute_bars_by_symbol"],
        )
        for field, value, message in (
            ("price", 10.0, "raw displayed price"),
            ("percent_gain", 26.0, "percent gain|split-consistent gain"),
        ):
            changed_payload = deepcopy(payload)
            changed_manifest = deepcopy(manifest)
            row = next(item for item in changed_payload["rows"] if item["symbol"] == "AAA")
            row[field] = value
            if field == "price":
                row["price_pillar_pass"] = True
            row["disposition"] = legacy.disposition_from_snapshot_row(row, profile=values["profile"])
            _rehash_artifact(changed_payload, changed_manifest)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                validate_causal_scanner_snapshot(
                    changed_payload,
                    changed_manifest,
                    candidate_rows=values["candidate_rows"],
                    profile=values["profile"],
                    expected_source_hashes=source_hashes,
                    membership_symbols=values["membership_symbols"],
                    previous_close_by_symbol=values["previous_close_by_symbol"],
                    rank_split_minute_bars_by_symbol=values["rank_split_minute_bars_by_symbol"],
                    candidate_raw_minute_bars_by_symbol=values["candidate_raw_minute_bars_by_symbol"],
                )

    def test_raw_split_timestamp_mismatch_fails_closed(self) -> None:
        values = self._values()
        raw = dict(values["candidate_raw_minute_bars_by_symbol"])
        raw["AAA"] = raw["AAA"].set_axis(
            pd.date_range("2025-04-03T11:01:00Z", periods=1, freq="1min")
        )
        with self.assertRaisesRegex(ValueError, "timestamp coverage mismatch"):
            build_scanner_snapshot_rows(
                trading_date=values["trading_date"],
                profile=values["profile"],
                candidate_rows=values["candidate_rows"],
                float_records=values["float_records"],
                news_events=values["news_events"],
                news_statuses=values["news_statuses"],
                membership_symbols=values["membership_symbols"],
                previous_close_by_symbol=values["previous_close_by_symbol"],
                rank_split_minute_bars_by_symbol=values["rank_split_minute_bars_by_symbol"],
                candidate_raw_minute_bars_by_symbol=raw,
                candidate_exact_rvol_by_symbol=values["candidate_exact_rvol_by_symbol"],
            )


if __name__ == "__main__":
    unittest.main()
