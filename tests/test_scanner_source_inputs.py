from __future__ import annotations

import copy
from dataclasses import replace
from datetime import date, time
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from momentumbot.causal_scanner_snapshot import (
    build_scanner_snapshot_rows,
    market_inputs_fingerprint,
)
from momentumbot.models import current_general_2026
from momentumbot.scanner_source_inputs import (
    ARTIFACT_ID,
    MANIFEST_FILE,
    RECORD_FILE,
    SOURCE_HASH_NAMES,
    build_scanner_source_input_root_manifest,
    load_scanner_source_input_bundle,
    validate_scanner_source_input_manifest,
    write_scanner_source_input_bundle,
)


def _fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _profile():
    return replace(current_general_2026(), no_new_entries_after=time(7, 3))


def _bars(closes, volumes, *, symbol_offset=0):
    index = pd.date_range("2025-04-03T11:00:00Z", periods=len(closes), freq="1min")
    return pd.DataFrame(
        {
            "close": [value + symbol_offset for value in closes],
            "volume": volumes,
        },
        index=index,
    )


def _inputs():
    aaa = _bars([2.0, 2.1], [100, 200])
    empty = pd.DataFrame(columns=["close", "volume"])
    return {
        "trading_date": date(2025, 4, 3),
        "profile": _profile(),
        "membership_symbols": ["BBB", "AAA"],
        "candidate_symbols": ["BBB", "AAA"],
        "previous_close_by_symbol": {"BBB": 1.5, "AAA": 1.0},
        "rank_raw_minute_bars_by_symbol": {"BBB": empty, "AAA": aaa},
        "candidate_raw_minute_bars_by_symbol": {"AAA": aaa, "BBB": empty},
        "candidate_exact_rvol_by_symbol": {
            "AAA": pd.Series([6.0, 6.5], index=aaa.index),
            "BBB": pd.Series(dtype="float64"),
        },
        "upstream_source_hashes": {
            name: format(index + 1, "064x")
            for index, name in enumerate(SOURCE_HASH_NAMES[:-1])
        },
    }


def _rewrite_gzip(path: Path, lines: list[bytes]) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw,
            compresslevel=9,
            mtime=0,
        ) as compressed:
            for line in lines:
                compressed.write(line)


class ScannerSourceInputTests(unittest.TestCase):
    def test_round_trip_preserves_existing_hash_and_empty_candidate(self):
        values = _inputs()
        expected = market_inputs_fingerprint(
            **{
                key: value
                for key, value in values.items()
                if key not in {"candidate_symbols", "upstream_source_hashes"}
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "date"
            manifest = write_scanner_source_input_bundle(root, **values)
            loaded, loaded_manifest = load_scanner_source_input_bundle(
                root, profile=values["profile"]
            )

        self.assertEqual(manifest, loaded_manifest)
        self.assertEqual(manifest["summary"]["logical_records_sha256"], expected)
        self.assertEqual(loaded.source_hashes["reacquired_market_inputs"], expected)
        self.assertEqual(loaded.membership_symbols, ("AAA", "BBB"))
        self.assertEqual(loaded.candidate_symbols, ("AAA", "BBB"))
        self.assertTrue(loaded.candidate_raw_minute_bars_by_symbol["BBB"].empty)
        self.assertTrue(loaded.candidate_exact_rvol_by_symbol["BBB"].empty)
        pd.testing.assert_frame_equal(
            loaded.candidate_raw_minute_bars_by_symbol["AAA"],
            values["candidate_raw_minute_bars_by_symbol"]["AAA"],
            check_dtype=False,
            check_freq=False,
        )

        candidate_rows = [
            {
                "symbol": symbol,
                "previous_close": previous,
                "first_market_qualified_bar_started_at": "2025-04-03T11:00:00+00:00",
                "first_market_qualified_at": "2025-04-03T11:01:00+00:00",
            }
            for symbol, previous in (("AAA", 1.0), ("BBB", 1.5))
        ]
        float_records = [
            {
                "symbol": symbol,
                "float_classification": "pass",
                "float_pillar_pass": True,
                "estimated_float_shares": 5_000_000,
                "float_asof": "2025-04-01T12:00:00+00:00",
                "method": "test-causal-float",
                "sec_status": "success",
            }
            for symbol in ("AAA", "BBB")
        ]
        news_statuses = [
            {"symbol": symbol, "provider_status": "success"}
            for symbol in ("AAA", "BBB")
        ]
        original_rows = build_scanner_snapshot_rows(
            trading_date=values["trading_date"],
            profile=values["profile"],
            candidate_rows=candidate_rows,
            float_records=float_records,
            news_events=[],
            news_statuses=news_statuses,
            membership_symbols=values["membership_symbols"],
            previous_close_by_symbol=values["previous_close_by_symbol"],
            rank_raw_minute_bars_by_symbol=values[
                "rank_raw_minute_bars_by_symbol"
            ],
            candidate_raw_minute_bars_by_symbol=values[
                "candidate_raw_minute_bars_by_symbol"
            ],
            candidate_exact_rvol_by_symbol=values[
                "candidate_exact_rvol_by_symbol"
            ],
        )
        replayed_rows = build_scanner_snapshot_rows(
            trading_date=loaded.trading_date,
            profile=values["profile"],
            candidate_rows=candidate_rows,
            float_records=float_records,
            news_events=[],
            news_statuses=news_statuses,
            membership_symbols=loaded.membership_symbols,
            previous_close_by_symbol=loaded.previous_close_by_symbol,
            rank_raw_minute_bars_by_symbol=loaded.rank_raw_minute_bars_by_symbol,
            candidate_raw_minute_bars_by_symbol=(
                loaded.candidate_raw_minute_bars_by_symbol
            ),
            candidate_exact_rvol_by_symbol=loaded.candidate_exact_rvol_by_symbol,
        )
        self.assertEqual(replayed_rows, original_rows)

    def test_compressed_sidecar_is_deterministic(self):
        values = _inputs()
        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "first"
            second = Path(temporary) / "second"
            first_manifest = write_scanner_source_input_bundle(first, **values)
            second_manifest = write_scanner_source_input_bundle(second, **values)
            self.assertEqual(
                (first / RECORD_FILE).read_bytes(),
                (second / RECORD_FILE).read_bytes(),
            )
        self.assertEqual(first_manifest, second_manifest)

    def test_manifest_knowledge_tamper_fails_closed(self):
        values = _inputs()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "date"
            manifest = write_scanner_source_input_bundle(root, **values)
            changed = copy.deepcopy(manifest)
            changed["knowledge_policy"]["uses_benchmark_labels"] = True
            changed["content_sha256"] = _fingerprint(
                {key: value for key, value in changed.items() if key != "content_sha256"}
            )
            with self.assertRaisesRegex(ValueError, "knowledge boundary"):
                validate_scanner_source_input_manifest(changed, root=root)

    def test_compressed_file_tamper_fails_closed(self):
        values = _inputs()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "date"
            write_scanner_source_input_bundle(root, **values)
            with (root / RECORD_FILE).open("ab") as handle:
                handle.write(b"tamper")
            with self.assertRaisesRegex(ValueError, "compressed file hash"):
                load_scanner_source_input_bundle(root, profile=values["profile"])

    def test_rehashed_out_of_order_stream_is_rejected(self):
        values = _inputs()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "date"
            manifest = write_scanner_source_input_bundle(root, **values)
            with gzip.open(root / RECORD_FILE, "rb") as handle:
                lines = handle.readlines()
            lines[2], lines[3] = lines[3], lines[2]
            _rewrite_gzip(root / RECORD_FILE, lines)
            logical_sha = hashlib.sha256(b"".join(lines)).hexdigest()
            manifest["source_hashes"]["reacquired_market_inputs"] = logical_sha
            manifest["summary"]["logical_records_sha256"] = logical_sha
            manifest["summary"]["compressed_file_sha256"] = hashlib.sha256(
                (root / RECORD_FILE).read_bytes()
            ).hexdigest()
            manifest["summary"]["compressed_size_bytes"] = (
                root / RECORD_FILE
            ).stat().st_size
            manifest["content_sha256"] = _fingerprint(
                {key: value for key, value in manifest.items() if key != "content_sha256"}
            )
            (root / MANIFEST_FILE).write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "out of order"):
                load_scanner_source_input_bundle(root, profile=values["profile"])

    def test_root_manifest_binds_ordered_dates_without_promotion(self):
        values = _inputs()
        with tempfile.TemporaryDirectory() as temporary:
            first_root = Path(temporary) / "first"
            first = write_scanner_source_input_bundle(first_root, **values)
            second = copy.deepcopy(first)
            second["trading_date"] = "2025-04-04"
            second["content_sha256"] = _fingerprint(
                {key: value for key, value in second.items() if key != "content_sha256"}
            )
            root = build_scanner_source_input_root_manifest(
                date_manifests=[first, second],
                source_bundle_hashes={
                    "membership": "a" * 64,
                    "market": "b" * 64,
                    "float": "c" * 64,
                    "news": "d" * 64,
                },
            )
        self.assertEqual(root["artifact_id"], ARTIFACT_ID)
        self.assertEqual(root["dates"], ["2025-04-03", "2025-04-04"])
        self.assertFalse(root["replay_boundary"]["policy_promotion_eligible"])
        with self.assertRaisesRegex(ValueError, "unique and ordered"):
            build_scanner_source_input_root_manifest(
                date_manifests=[second, first],
                source_bundle_hashes={"membership": "a" * 64},
            )


if __name__ == "__main__":
    unittest.main()
