from __future__ import annotations

from datetime import date
import hashlib
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from momentumbot.models import current_general_2026
from momentumbot.scanner_rvol_alignment_v10 import (
    align_exact_rvol_to_raw_bar_indexes_v10,
)
from momentumbot.scanner_source_inputs_v03 import (
    SOURCE_HASH_NAMES,
    load_scanner_source_input_bundle,
    write_scanner_source_input_bundle,
)
from scripts import build_causal_scanner_snapshot_v10 as adapter


BLRX_RAW_TIMESTAMP_SHA256 = (
    "e8899e681460b9e504b3c28e62849820afca44c60ee6db2d8f5020cc06a5f9cc"
)


def _blrx_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    raw_index = pd.date_range(
        "2025-05-30T11:02:00Z",
        "2025-05-30T13:58:00Z",
        freq="1min",
    )
    encoded = ("\n".join(value.isoformat() for value in raw_index) + "\n").encode()
    if hashlib.sha256(encoded).hexdigest() != BLRX_RAW_TIMESTAMP_SHA256:
        raise AssertionError("BLRX retained timestamp fixture changed")
    raw = pd.DataFrame(
        {
            "close": [4.23 + index / 10_000 for index in range(len(raw_index))],
            "volume": [100.0 + index for index in range(len(raw_index))],
        },
        index=raw_index,
    )
    split = raw.loc[:, ["close"]].copy()
    dense_index = pd.date_range(
        "2025-05-30T08:00:00Z",
        "2025-05-30T13:58:00Z",
        freq="1min",
    )
    rvol = pd.Series(
        [1.0 + index / 1_000 for index in range(len(dense_index))],
        index=dense_index,
        name="relative_volume",
    )
    return raw, split, rvol


class ScannerRvolAlignmentV10Tests(unittest.TestCase):
    def test_real_blrx_sparse_prefix_round_trips_without_value_change(self) -> None:
        raw, split, dense_rvol = _blrx_inputs()
        self.assertEqual(len(raw), 177)
        self.assertEqual(len(dense_rvol), 359)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "RVOL timestamp coverage"):
                write_scanner_source_input_bundle(
                    Path(temporary) / "unrepaired",
                    trading_date=date(2025, 5, 30),
                    profile=current_general_2026(),
                    membership_symbols=["BLRX"],
                    candidate_symbols=["BLRX"],
                    previous_close_by_symbol={"BLRX": 3.7909},
                    rank_split_minute_bars_by_symbol={"BLRX": split},
                    candidate_raw_minute_bars_by_symbol={"BLRX": raw},
                    candidate_exact_rvol_by_symbol={"BLRX": dense_rvol},
                    upstream_source_hashes={
                        name: format(index + 1, "064x")
                        for index, name in enumerate(SOURCE_HASH_NAMES[:-1])
                    },
                )

            aligned = align_exact_rvol_to_raw_bar_indexes_v10(
                candidate_raw_minute_bars_by_symbol={"BLRX": raw},
                candidate_exact_rvol_by_symbol={"BLRX": dense_rvol},
            )
            expected = dense_rvol.loc[raw.index]
            pd.testing.assert_series_equal(aligned["BLRX"], expected)

            root = Path(temporary) / "repaired"
            manifest = write_scanner_source_input_bundle(
                root,
                trading_date=date(2025, 5, 30),
                profile=current_general_2026(),
                membership_symbols=["BLRX"],
                candidate_symbols=["BLRX"],
                previous_close_by_symbol={"BLRX": 3.7909},
                rank_split_minute_bars_by_symbol={"BLRX": split},
                candidate_raw_minute_bars_by_symbol={"BLRX": raw},
                candidate_exact_rvol_by_symbol=aligned,
                upstream_source_hashes={
                    name: format(index + 1, "064x")
                    for index, name in enumerate(SOURCE_HASH_NAMES[:-1])
                },
            )
            loaded, loaded_manifest = load_scanner_source_input_bundle(
                root,
                profile=current_general_2026(),
            )
        self.assertEqual(manifest, loaded_manifest)
        self.assertEqual(
            manifest["summary"]["record_counts"]["candidate_raw_bar"],
            177,
        )
        self.assertEqual(
            manifest["summary"]["record_counts"]["candidate_exact_rvol"],
            177,
        )
        pd.testing.assert_series_equal(
            loaded.candidate_exact_rvol_by_symbol["BLRX"],
            expected.rename(None),
            check_freq=False,
        )

    def test_missing_raw_timestamp_fails_closed_without_imputation(self) -> None:
        raw, _split, dense_rvol = _blrx_inputs()
        missing = dense_rvol.drop(raw.index[7])
        with self.assertRaisesRegex(ValueError, "lacks a raw-bar timestamp"):
            align_exact_rvol_to_raw_bar_indexes_v10(
                candidate_raw_minute_bars_by_symbol={"BLRX": raw},
                candidate_exact_rvol_by_symbol={"BLRX": missing},
            )

    def test_extra_symbols_and_duplicate_rvol_timestamps_fail_closed(self) -> None:
        raw, _split, dense_rvol = _blrx_inputs()
        with self.assertRaisesRegex(ValueError, "symbols disagree"):
            align_exact_rvol_to_raw_bar_indexes_v10(
                candidate_raw_minute_bars_by_symbol={"BLRX": raw},
                candidate_exact_rvol_by_symbol={"OTHER": dense_rvol},
            )
        duplicated = pd.concat([dense_rvol, dense_rvol.iloc[-1:]])
        with self.assertRaisesRegex(ValueError, "timestamps are invalid"):
            align_exact_rvol_to_raw_bar_indexes_v10(
                candidate_raw_minute_bars_by_symbol={"BLRX": raw},
                candidate_exact_rvol_by_symbol={"BLRX": duplicated},
            )

    def test_scoped_writer_adapter_projects_then_restores_frozen_writer(self) -> None:
        raw, _split, dense_rvol = _blrx_inputs()
        observed: list[pd.Series] = []

        def frozen_writer(*_args: object, **kwargs: object) -> dict[str, object]:
            values = kwargs["candidate_exact_rvol_by_symbol"]
            if not isinstance(values, dict):
                raise AssertionError("adapter did not preserve candidate mapping")
            observed.append(values["BLRX"])
            return {"written": True}

        parent = adapter.parent
        previous = parent.write_scanner_source_input_bundle
        parent.write_scanner_source_input_bundle = frozen_writer
        try:
            with adapter.canonical_scanner_rvol_alignment_v10():
                result = parent.write_scanner_source_input_bundle(
                    candidate_raw_minute_bars_by_symbol={"BLRX": raw},
                    candidate_exact_rvol_by_symbol={"BLRX": dense_rvol},
                )
            self.assertEqual(result, {"written": True})
            self.assertIs(parent.write_scanner_source_input_bundle, frozen_writer)
            self.assertEqual(len(observed), 1)
            pd.testing.assert_series_equal(
                observed[0],
                dense_rvol.loc[raw.index],
            )
        finally:
            parent.write_scanner_source_input_bundle = previous


if __name__ == "__main__":
    unittest.main()
