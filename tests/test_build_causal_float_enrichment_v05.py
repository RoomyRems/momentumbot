from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from momentumbot.historical_float_v04 import (
    TargetBasisObservation,
    TargetSessionPair,
)
from scripts import build_causal_float_enrichment_v04 as parent
from scripts.build_causal_float_enrichment_v05 import (
    DIAGNOSTIC_DISPOSITION,
    DIAGNOSTIC_STAGE,
    build_float_record_candidate_fail_closed,
    build_sanitized_diagnostics,
    download_basis_candidate_fail_closed,
    main,
    observe_basis_candidate_fail_closed,
    validate_sanitized_diagnostics,
)


TARGET = date(2025, 5, 30)


class BuildCausalFloatEnrichmentV05Tests(unittest.TestCase):
    def test_value_error_rejects_only_candidate_without_retaining_message(self) -> None:
        rejections: list[dict[str, str]] = []

        def invalid_data(*_args, **_kwargs):
            raise ValueError("raw provider field and secret must never persist")

        raw, split = download_basis_candidate_fail_closed(
            object(),
            "CHEB",
            [date(2024, 12, 31)],
            trading_date=TARGET,
            rejections=rejections,
            delegate=invalid_data,
        )

        self.assertTrue(raw.empty)
        self.assertTrue(split.empty)
        self.assertEqual(
            rejections,
            [
                {
                    "trading_date": "2025-05-30",
                    "symbol": "CHEB",
                    "stage": DIAGNOSTIC_STAGE,
                    "exception_class": "ValueError",
                    "disposition": DIAGNOSTIC_DISPOSITION,
                }
            ],
        )
        rendered = json.dumps(build_sanitized_diagnostics(rejections))
        self.assertNotIn("raw provider field", rendered)
        self.assertNotIn("secret", rendered)

    def test_type_error_is_candidate_data_but_transport_error_remains_fatal(self) -> None:
        rejections: list[dict[str, str]] = []
        raw, split = download_basis_candidate_fail_closed(
            object(),
            "AAA",
            [],
            trading_date=TARGET,
            rejections=rejections,
            delegate=lambda *_args, **_kwargs: (_ for _ in ()).throw(TypeError("bad")),
        )
        self.assertTrue(raw.empty and split.empty)
        self.assertEqual(rejections[0]["exception_class"], "TypeError")

        with self.assertRaisesRegex(RuntimeError, "HTTP 429"):
            download_basis_candidate_fail_closed(
                object(),
                "BBB",
                [],
                trading_date=TARGET,
                rejections=rejections,
                delegate=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    RuntimeError("HTTP 429")
                ),
            )
        self.assertEqual(len(rejections), 1)

    def test_valid_candidate_is_unchanged(self) -> None:
        frame = pd.DataFrame({"close": [1.0]})
        rejections: list[dict[str, str]] = []
        raw, split = download_basis_candidate_fail_closed(
            object(),
            "AAA",
            [],
            trading_date=TARGET,
            rejections=rejections,
            delegate=lambda *_args, **_kwargs: (frame, frame.copy()),
        )
        self.assertEqual(raw.to_dict(), frame.to_dict())
        self.assertEqual(split.to_dict(), frame.to_dict())
        self.assertEqual(rejections, [])

    def test_observation_and_final_record_data_errors_are_candidate_contained(self) -> None:
        pair = TargetSessionPair(
            symbol="AAA",
            target_date=TARGET.isoformat(),
            first_market_qualified_bar_started_at="2025-05-30T11:00:00-04:00",
            first_market_qualified_at="2025-05-30T11:01:00-04:00",
            raw_timestamp="2025-05-30T11:00:00-04:00",
            split_timestamp="2025-05-30T11:00:00-04:00",
            raw_close="2",
            split_close="2",
            source_artifact_id="causal-float-target-basis-v0.1",
            source_content_sha256="a" * 64,
        )
        fallback = TargetBasisObservation(
            requested_date="2025-01-01",
            observed_date=None,
            measure_raw_timestamp=None,
            measure_split_timestamp=None,
            measure_raw_close=None,
            measure_split_close=None,
            target_date=TARGET.isoformat(),
            target_raw_timestamp=pair.raw_timestamp,
            target_split_timestamp=pair.split_timestamp,
            target_raw_close=pair.raw_close,
            target_split_close=pair.split_close,
            target_source_artifact_id=pair.source_artifact_id,
            target_source_content_sha256=pair.source_content_sha256,
            share_factor_numerator=None,
            share_factor_denominator=None,
            status="missing_measure_pair",
            lineage_sha256="b" * 64,
        )
        rejections: list[dict[str, str]] = []
        failed: set[tuple[str, str]] = set()

        def observation_delegate(raw, _split, _requested, *, target_pair):
            if raw.empty:
                return fallback
            raise ValueError("malformed provider frame")

        observed = observe_basis_candidate_fail_closed(
            pd.DataFrame({"close": [1.0]}),
            pd.DataFrame({"close": [1.0]}),
            date(2025, 1, 1),
            target_pair=pair,
            trading_date=TARGET,
            rejections=rejections,
            failed_candidates=failed,
            delegate=observation_delegate,
        )
        self.assertIs(observed, fallback)
        self.assertEqual(failed, {(TARGET.isoformat(), "AAA")})

        candidate = {
            "symbol": "AAA",
            "selected_cik": "1",
            "first_market_qualified_bar_started_at": pair.first_market_qualified_bar_started_at,
            "first_market_qualified_at": pair.first_market_qualified_at,
        }
        selected = {
            "symbol": "AAA",
            "cik": "0000000001",
            "first_market_qualified_bar_started_at": pair.first_market_qualified_bar_started_at,
            "first_market_qualified_at": pair.first_market_qualified_at,
            "public_float": {"provider": "derived"},
            "anchor_outstanding": None,
            "current_outstanding": None,
        }
        calls: list[tuple[dict[str, object], dict[str, object]]] = []

        def record_delegate(selected_value, observations_value, **_kwargs):
            calls.append((selected_value, observations_value))
            return {"unknown": not selected_value["public_float"]}

        record = build_float_record_candidate_fail_closed(
            selected,
            {"public:2025-01-01": fallback},
            candidate=candidate,
            target_date=TARGET,
            target_basis_content_sha256="c" * 64,
            sec_status="success_selected_evidence_exact_acceptance",
            rejections=rejections,
            failed_candidates=failed,
            delegate=record_delegate,
        )
        self.assertEqual(record, {"unknown": True})
        self.assertEqual(calls[0][1], {})
        self.assertIsNone(calls[0][0]["public_float"])
        self.assertEqual(len(rejections), 1)

    def test_invalid_target_source_is_fatal_not_candidate_contained(self) -> None:
        invalid = TargetSessionPair(
            symbol="AAA",
            target_date=TARGET.isoformat(),
            first_market_qualified_bar_started_at="2025-05-30T11:00:00-04:00",
            first_market_qualified_at="2025-05-30T11:01:00-04:00",
            raw_timestamp="2025-05-30T11:00:00-04:00",
            split_timestamp="2025-05-30T11:00:00-04:00",
            raw_close="2",
            split_close="2",
            source_artifact_id="tampered",
            source_content_sha256="a" * 64,
        )
        rejections: list[dict[str, str]] = []
        with self.assertRaisesRegex(ValueError, "source artifact"):
            observe_basis_candidate_fail_closed(
                pd.DataFrame(),
                pd.DataFrame(),
                date(2025, 1, 1),
                target_pair=invalid,
                trading_date=TARGET,
                rejections=rejections,
                failed_candidates=set(),
            )
        self.assertEqual(rejections, [])

    def test_adapter_restores_parent_and_writes_hashed_diagnostics(self) -> None:
        original = parent._download_basis
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            census = root / "source"
            census.mkdir()
            diagnostic = root / "float-normalization-rejections.json"

            def parent_main(_arguments):
                raw, split = parent._download_basis(
                    object(),
                    "CHEB",
                    [date(2024, 12, 31)],
                    trading_date=TARGET,
                )
                self.assertTrue(raw.empty and split.empty)
                return 0

            with patch.object(parent, "main", side_effect=parent_main), patch.object(
                parent,
                "_download_basis",
                side_effect=ValueError("do not retain me"),
            ) as mocked_download:
                patched_original = parent._download_basis
                result = main(
                    [
                        "--census-root",
                        str(census),
                        "--sanitized-normalization-diagnostics",
                        str(diagnostic),
                    ]
                )
                self.assertIs(parent._download_basis, patched_original)
                mocked_download.assert_called_once()
            self.assertEqual(result, 0)
            payload = json.loads(diagnostic.read_text(encoding="utf-8"))
            validate_sanitized_diagnostics(payload)
            self.assertEqual(payload["candidate_rejection_count"], 1)
            self.assertNotIn("do not retain me", diagnostic.read_text(encoding="utf-8"))
        self.assertIs(parent._download_basis, original)

    def test_diagnostics_tampering_is_rejected(self) -> None:
        payload = build_sanitized_diagnostics([])
        payload["candidate_rejection_count"] = 1
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            validate_sanitized_diagnostics(payload)

    def test_diagnostic_output_rejects_symlinked_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            census = root / "source"
            census.mkdir()
            real = root / "real"
            real.mkdir()
            linked = root / "linked"
            linked.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "contains a symlink"):
                main(
                    [
                        "--census-root",
                        str(census),
                        "--sanitized-normalization-diagnostics",
                        str(linked / "float-normalization-rejections.json"),
                    ]
                )


if __name__ == "__main__":
    unittest.main()
