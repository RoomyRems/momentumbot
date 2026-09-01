from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from momentumbot.historical_float_v03 import causal_float_v0_1_manifest
from momentumbot.historical_float_v04 import (
    CAUSAL_FLOAT_POLICY_ID,
    CAUSAL_FLOAT_SCHEMA_VERSION,
    FLOAT_TARGET_BASIS_ARTIFACT_ID,
    TargetSessionPair,
    build_causal_float_date_manifest,
    build_causal_float_record,
    build_causal_float_root_manifest,
    build_float_target_basis_payload,
    causal_float_v0_2_manifest,
    estimate_float_row,
    file_sha256,
    load_causal_float_records,
    load_causal_float_root,
    load_float_target_basis,
    observe_target_basis,
    validate_causal_float_records,
    validate_target_basis_observation,
)
from scripts.build_causal_float_enrichment_v04 import (
    _basis_query_window,
    _download_basis,
)


TARGET = date(2025, 2, 3)
MEASURE = date(2025, 1, 2)


def _frame(rows: list[tuple[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(
        {"close": [close for _, close in rows]},
        index=pd.DatetimeIndex([timestamp for timestamp, _ in rows]),
    )


def _selected(
    *,
    shares: int | None = None,
    public_float_usd: object | None = None,
) -> dict[str, object]:
    current = None
    if shares is not None:
        current = {
            "measure_date": MEASURE.isoformat(),
            "shares": shares,
            "accession": "shares",
            "available_at": "2025-01-15T15:00:00+00:00",
            "form": "10-Q",
        }
    public = None
    if public_float_usd is not None:
        public = {
            "measure_date": MEASURE.isoformat(),
            "public_float_usd": public_float_usd,
            "accession": "public",
            "available_at": "2025-01-15T15:00:00+00:00",
            "form": "10-K",
        }
    return {
        "symbol": "AAA",
        "cik": "0000000001",
        "first_market_qualified_bar_started_at": "2025-02-03T14:59:00+00:00",
        "first_market_qualified_at": "2025-02-03T15:00:00+00:00",
        "public_float": public,
        "anchor_outstanding": None,
        "current_outstanding": current,
    }


def _candidate() -> dict[str, object]:
    return {
        "symbol": "AAA",
        "selected_cik": "1",
        "selected_composite_figi": "BBG000AAA111",
        "identity_identifier_kind": "composite_figi",
        "identity_identifier": "BBG000AAA111",
        "first_market_qualified_bar_started_at": "2025-02-03T14:59:00+00:00",
        "first_market_qualified_at": "2025-02-03T15:00:00+00:00",
    }


def _candidate_payload() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 2,
        "artifact_id": "causal-market-candidates-v0.3",
        "trading_date": TARGET.isoformat(),
        "candidate_count": 1,
        "rows": [_candidate()],
    }
    payload["content_sha256"] = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return payload


def _target_pair(*, raw: object, split: object) -> TargetSessionPair:
    return TargetSessionPair(
        symbol="AAA",
        target_date=TARGET.isoformat(),
        first_market_qualified_bar_started_at="2025-02-03T14:59:00+00:00",
        first_market_qualified_at="2025-02-03T15:00:00+00:00",
        raw_timestamp="2025-02-03T14:59:00+00:00",
        split_timestamp="2025-02-03T14:59:00+00:00",
        raw_close=str(raw),
        split_close=str(split),
        source_artifact_id=FLOAT_TARGET_BASIS_ARTIFACT_ID,
        source_content_sha256="d" * 64,
    )


def _observation(
    *,
    measure_raw: object,
    measure_split: object,
    target_raw: object,
    target_split: object,
):
    measure_timestamp = "2025-01-02T16:00:00+00:00"
    raw = _frame([(measure_timestamp, measure_raw)])
    split = _frame([(measure_timestamp, measure_split)])
    return observe_target_basis(
        raw,
        split,
        MEASURE,
        target_pair=_target_pair(raw=target_raw, split=target_split),
    )


class HistoricalFloatV04Tests(unittest.TestCase):
    def test_forward_split_before_target_multiplies_shares(self) -> None:
        observation = _observation(
            measure_raw=100,
            measure_split=10,
            target_raw=12,
            target_split=12,
        )
        self.assertEqual(observation.status, "complete")
        self.assertEqual(observation.share_factor_numerator, "10")
        self.assertEqual(observation.share_factor_denominator, "1")

        row = estimate_float_row(
            _selected(shares=900_000),
            {f"current:{MEASURE.isoformat()}": observation},
        )

        self.assertEqual(row.current_outstanding_target_basis, 9_000_000)
        self.assertEqual(row.estimated_float_shares, 9_000_000)
        self.assertTrue(row.float_pillar_pass)

    def test_reverse_split_before_target_divides_shares(self) -> None:
        observation = _observation(
            measure_raw=1,
            measure_split=10,
            target_raw=12,
            target_split=12,
        )
        self.assertEqual(observation.share_factor_numerator, "1")
        self.assertEqual(observation.share_factor_denominator, "10")

        row = estimate_float_row(
            _selected(shares=90_000_000),
            {f"current:{MEASURE.isoformat()}": observation},
        )

        self.assertEqual(row.current_outstanding_target_basis, 9_000_000)
        self.assertTrue(row.float_pillar_pass)

    def test_post_target_split_factor_cancels(self) -> None:
        observation = _observation(
            measure_raw=100,
            measure_split=10,
            target_raw=120,
            target_split=12,
        )

        self.assertEqual(observation.share_factor_numerator, "1")
        self.assertEqual(observation.share_factor_denominator, "1")
        row = estimate_float_row(
            _selected(shares=9_500_000),
            {f"current:{MEASURE.isoformat()}": observation},
        )
        self.assertEqual(row.estimated_float_shares, 9_500_000)
        self.assertTrue(row.float_pillar_pass)

    def test_exact_qualification_minute_target_pair_is_required(self) -> None:
        raw = {
            "AAA": _frame([("2025-02-03T14:58:00+00:00", 10)]),
        }
        split = {
            "AAA": _frame([("2025-02-03T14:59:00+00:00", 10)]),
        }

        with self.assertRaisesRegex(ValueError, "lacks the qualification bar"):
            build_float_target_basis_payload(
                trading_date=TARGET,
                candidate_rows=[_candidate()],
                candidate_payload=_candidate_payload(),
                raw_minutes_by_symbol=raw,
                split_minutes_by_symbol=split,
            )

    def test_malformed_or_misaligned_raw_split_pair_fails_closed(self) -> None:
        invalid = _observation(
            measure_raw=float("nan"),
            measure_split=10,
            target_raw=12,
            target_split=12,
        )
        self.assertEqual(invalid.status, "invalid_measure_close")

        mismatch = replace(
            _target_pair(raw=12, split=12),
            split_timestamp="2025-02-03T15:00:00+00:00",
        )
        with self.assertRaisesRegex(ValueError, "timestamp mismatch"):
            observe_target_basis(
                _frame([("2025-01-02T16:00:00+00:00", 10)]),
                _frame([("2025-01-02T16:00:00+00:00", 10)]),
                MEASURE,
                target_pair=mismatch,
            )

    def test_measure_frames_do_not_retreat_to_an_older_common_session(self) -> None:
        raw = _frame(
            [
                ("2025-01-02T16:00:00+00:00", 10),
                ("2025-01-03T16:00:00+00:00", 11),
            ]
        )
        split = _frame([("2025-01-02T16:00:00+00:00", 10)])

        observation = observe_target_basis(
            raw,
            split,
            date(2025, 1, 3),
            target_pair=_target_pair(raw=12, split=12),
        )

        self.assertEqual(observation.status, "measure_timestamp_mismatch")
        self.assertIsNone(observation.share_factor_numerator)

    def test_public_float_uses_raw_measure_price_then_target_factor(self) -> None:
        observation = _observation(
            measure_raw=10,
            measure_split=5,
            target_raw=25,
            target_split=25,
        )

        row = estimate_float_row(
            _selected(public_float_usd=80_000_000),
            {f"public:{MEASURE.isoformat()}": observation},
        )

        self.assertEqual(row.public_float_price_used, "10")
        self.assertEqual(row.estimated_float_shares, 16_000_000)
        self.assertFalse(row.float_pillar_pass)

    def test_threshold_rounding_is_exact_and_conservative(self) -> None:
        observation = _observation(
            measure_raw=10,
            measure_split=10,
            target_raw=10,
            target_split=10,
        )
        passed = estimate_float_row(
            _selected(public_float_usd=99_999_990),
            {f"public:{MEASURE.isoformat()}": observation},
        )
        failed = estimate_float_row(
            _selected(public_float_usd=99_999_991),
            {f"public:{MEASURE.isoformat()}": observation},
        )

        self.assertEqual(passed.estimated_float_shares, 9_999_999)
        self.assertTrue(passed.float_pillar_pass)
        self.assertEqual(failed.estimated_float_shares, 10_000_000)
        self.assertFalse(failed.float_pillar_pass)

    def test_nonfinite_public_float_and_nonintegral_shares_are_rejected(self) -> None:
        observation = _observation(
            measure_raw=10,
            measure_split=10,
            target_raw=10,
            target_split=10,
        )
        for invalid in (True, 1.5, "100"):
            selected = _selected(shares=1)
            selected["current_outstanding"]["shares"] = invalid
            with self.assertRaisesRegex(ValueError, "positive integer"):
                estimate_float_row(
                    selected,
                    {f"current:{MEASURE.isoformat()}": observation},
                )
        for invalid in (float("nan"), float("inf"), -1):
            selected = _selected(public_float_usd=invalid)
            with self.assertRaisesRegex(ValueError, "finite and positive"):
                estimate_float_row(
                    selected,
                    {f"public:{MEASURE.isoformat()}": observation},
                )

    def test_record_validation_recomputes_factor_decision_and_lineage(self) -> None:
        observation = _observation(
            measure_raw=100,
            measure_split=10,
            target_raw=12,
            target_split=12,
        )
        selected = _selected(shares=900_000)
        record = build_causal_float_record(
            selected,
            {f"current:{MEASURE.isoformat()}": observation},
            candidate=_candidate(),
            target_date=TARGET,
            target_basis_content_sha256="d" * 64,
            sec_status="success_selected_evidence_exact_acceptance",
        )

        validate_causal_float_records(
            [_candidate()], [record], expected_trading_date=TARGET
        )
        tampered = deepcopy(record)
        tampered["basis_observations"][f"current:{MEASURE.isoformat()}"][
            "share_factor_numerator"
        ] = "9"
        with self.assertRaisesRegex(ValueError, "lineage fingerprint mismatch"):
            validate_causal_float_records(
                [_candidate()], [tampered], expected_trading_date=TARGET
            )
        extra = deepcopy(record)
        extra["later_price"] = 999
        with self.assertRaisesRegex(ValueError, "fields are invalid"):
            validate_causal_float_records(
                [_candidate()], [extra], expected_trading_date=TARGET
            )
        with self.assertRaisesRegex(ValueError, "SEC status is unsupported"):
            build_causal_float_record(
                selected,
                {f"current:{MEASURE.isoformat()}": observation},
                candidate=_candidate(),
                target_date=TARGET,
                target_basis_content_sha256="d" * 64,
                sec_status="invented_status",
            )

    def test_target_basis_payload_round_trip_and_tampering(self) -> None:
        bar = "2025-02-03T14:59:00+00:00"
        payload = build_float_target_basis_payload(
            trading_date=TARGET,
            candidate_rows=[_candidate()],
            candidate_payload=_candidate_payload(),
            raw_minutes_by_symbol={"AAA": _frame([(bar, 12)])},
            split_minutes_by_symbol={"AAA": _frame([(bar, 6)])},
        )
        self.assertEqual(payload["rows"][0]["raw_close"], "12")
        self.assertEqual(payload["rows"][0]["split_close"], "6")
        with tempfile.TemporaryDirectory() as raw_root:
            path = Path(raw_root) / "float-target-basis.json"
            path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            pairs, loaded = load_float_target_basis(
                path,
                candidate_rows=[_candidate()],
                candidate_payload=_candidate_payload(),
                expected_trading_date=TARGET,
            )
            self.assertEqual(loaded, payload)
            self.assertEqual(pairs["AAA"].source_content_sha256, payload["content_sha256"])
            payload["rows"][0]["raw_close"] = "13"
            path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "content fingerprint mismatch"):
                load_float_target_basis(
                    path,
                    candidate_rows=[_candidate()],
                    candidate_payload=_candidate_payload(),
                    expected_trading_date=TARGET,
                )

    def test_date_and_root_loaders_reject_file_tampering(self) -> None:
        observation = _observation(
            measure_raw=100,
            measure_split=10,
            target_raw=12,
            target_split=12,
        )
        record = build_causal_float_record(
            _selected(shares=900_000),
            {f"current:{MEASURE.isoformat()}": observation},
            candidate=_candidate(),
            target_date=TARGET,
            target_basis_content_sha256="d" * 64,
            sec_status="success_selected_evidence_exact_acceptance",
        )
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root) / CAUSAL_FLOAT_POLICY_ID
            date_root = root / TARGET.isoformat()
            date_root.mkdir(parents=True)
            records_path = date_root / "float-records.json"
            records_payload = {
                "schema_version": CAUSAL_FLOAT_SCHEMA_VERSION,
                "artifact_id": CAUSAL_FLOAT_POLICY_ID,
                "trading_date": TARGET.isoformat(),
                "rows": [record],
            }
            records_path.write_text(
                json.dumps(records_payload, sort_keys=True), encoding="utf-8"
            )
            date_manifest = build_causal_float_date_manifest(
                trading_date=TARGET,
                candidate_rows=[_candidate()],
                candidate_payload=_candidate_payload(),
                source_market_discovery_manifest_sha256="b" * 64,
                source_float_target_basis_sha256="d" * 64,
                records=[record],
                records_file_sha256=file_sha256(records_path),
                provider_error_count=0,
            )
            date_manifest_path = date_root / "manifest.json"
            date_manifest_path.write_text(
                json.dumps(date_manifest, sort_keys=True), encoding="utf-8"
            )
            root_manifest = build_causal_float_root_manifest(
                dates=[TARGET.isoformat()],
                source_market_discovery_bundle_sha256="c" * 64,
                date_manifest_commitments=[
                    {
                        "trading_date": TARGET.isoformat(),
                        "manifest": f"{TARGET.isoformat()}/manifest.json",
                        "manifest_file_sha256": file_sha256(date_manifest_path),
                        "manifest_content_sha256": date_manifest["content_sha256"],
                    }
                ],
                fatal_provider_errors=[],
                sec_acquisition={
                    "unique_successfully_cached_cik_count": 1,
                    "cache_hit_count": 0,
                    "endpoint_request_count": 2,
                    "minimum_request_interval_seconds": 0.2,
                    "attempts_per_endpoint": 3,
                },
            )
            (root / "manifest.json").write_text(
                json.dumps(root_manifest, sort_keys=True), encoding="utf-8"
            )

            rows, loaded_date = load_causal_float_records(
                date_root,
                candidate_rows=[_candidate()],
                candidate_payload=_candidate_payload(),
                expected_trading_date=TARGET,
            )
            self.assertEqual(rows, [record])
            self.assertEqual(loaded_date, date_manifest)
            self.assertEqual(
                load_causal_float_root(root, expected_dates=[TARGET.isoformat()]),
                root_manifest,
            )

            records_payload["rows"][0]["method"] = "tampered"
            records_path.write_text(
                json.dumps(records_payload, sort_keys=True), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "file fingerprint mismatch"):
                load_causal_float_records(
                    date_root,
                    candidate_rows=[_candidate()],
                    candidate_payload=_candidate_payload(),
                    expected_trading_date=TARGET,
                )
            with self.assertRaisesRegex(ValueError, "records file fingerprint mismatch"):
                load_causal_float_root(root, expected_dates=[TARGET.isoformat()])

    def test_builder_daily_window_stops_after_measure_basis(self) -> None:
        start, end = _basis_query_window([MEASURE], trading_date=TARGET)
        self.assertEqual(start, datetime(2024, 12, 19, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2025, 1, 17, tzinfo=timezone.utc))

    def test_no_selected_sec_evidence_makes_no_alpaca_basis_call(self) -> None:
        class NoCallClient:
            def bars(self, *_args, **_kwargs):
                raise AssertionError("Alpaca basis route must not be called")

        raw, split = _download_basis(
            NoCallClient(),
            "AAA",
            [],
            trading_date=TARGET,
        )
        self.assertTrue(raw.empty)
        self.assertTrue(split.empty)

    def test_legacy_v01_contract_is_unchanged(self) -> None:
        self.assertEqual(
            causal_float_v0_1_manifest()["fingerprint"],
            "00252a48e20d684d08a5163a3d8a776e541ad6e59dfd4c7a7fcf87f623a71803",
        )
        self.assertEqual(CAUSAL_FLOAT_POLICY_ID, "causal-sec-float-v0.2")
        self.assertEqual(
            causal_float_v0_2_manifest()["supersedes_policy_fingerprint"],
            causal_float_v0_1_manifest()["fingerprint"],
        )


if __name__ == "__main__":
    unittest.main()
