from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from momentumbot.research.databento_fill_cancel_classifier_v01 import (
    CONTRACT_CONTENT_SHA256,
    PARENT_FAILURE_CONTENT_SHA256,
    REQUEST,
    classify_fill_cancel_structure,
    load_classifier_contract,
    load_parent_failure_audit,
)
from momentumbot.research.databento_smoke import RuntimeConstants


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-fill-cancel-classifier-v0.1.json"
)
PARENT_FAILURE = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-feature-coverage-v0.1-"
    "run-32501827997-safe-failure-2026-08-21.json"
)
FUTURE_AUTHORIZATION = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-fill-cancel-classifier-v0.1-execution.json"
)
SOURCE = (
    ROOT
    / "src"
    / "momentumbot"
    / "research"
    / "databento_fill_cancel_classifier_v01.py"
)
RUNTIME = RuntimeConstants(
    f_last=128,
    f_tob=64,
    f_snapshot=32,
    f_bad_ts_recv=8,
    undef_price=9_223_372_036_854_775_807,
)


def _record(
    *,
    action: str,
    ts_recv: int,
    flags: int,
    sequence: int = 10,
    order_id: int = 900_000_001,
    side: str = "A",
    price: int = 123_456_789_000,
    size: int = 777,
    publisher_id: int = 1,
    instrument_id: int = 7,
) -> SimpleNamespace:
    return SimpleNamespace(
        ts_event=ts_recv - 1,
        ts_recv=ts_recv,
        publisher_id=publisher_id,
        instrument_id=instrument_id,
        channel_id=0,
        sequence=sequence,
        action=action,
        side=side,
        price=price,
        size=size,
        order_id=order_id,
        flags=flags,
    )


def _event() -> list[SimpleNamespace]:
    return [
        _record(action="F", ts_recv=1_000_000_000, flags=0),
        _record(action="C", ts_recv=1_000_000_001, flags=RUNTIME.f_last),
    ]


class DatabentoFillCancelClassifierV01Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parent_failure = load_parent_failure_audit(PARENT_FAILURE)
        cls.contract = load_classifier_contract(
            CONTRACT,
            parent_failure_audit=cls.parent_failure,
        )

    def classify(self, records: list[SimpleNamespace]) -> dict[str, object]:
        return classify_fill_cancel_structure(
            records,
            request=REQUEST,
            runtime=RUNTIME,
        )

    def test_contract_and_parent_are_hash_bound_and_unarmed(self):
        self.assertEqual(self.contract["content_sha256"], CONTRACT_CONTENT_SHA256)
        self.assertEqual(
            self.parent_failure["content_sha256"],
            PARENT_FAILURE_CONTENT_SHA256,
        )
        self.assertFalse(self.contract["provider_purchase_authorized"])
        self.assertFalse(self.contract["execution_authorization_file_present"])
        self.assertEqual(
            self.contract["future_execution_gate"]["exact_request_count_authorized"],
            0,
        )
        self.assertFalse(FUTURE_AUTHORIZATION.exists())

    def test_exact_fill_cancel_pair_matches_all_projections(self):
        result = self.classify(_event())
        self.assertEqual(result["instrument_event_count"], 1)
        self.assertEqual(result["fill_bearing_event_count"], 1)
        self.assertEqual(result["fill_record_count"], 1)
        self.assertEqual(result["cancel_record_count_in_fill_bearing_events"], 1)
        self.assertEqual(
            set(result["projection_overlap_counts"].values()),
            {1},
        )
        self.assertEqual(
            set(result["projection_full_match_event_counts"].values()),
            {1},
        )

    def test_sequence_mismatch_isolated_by_registered_projection(self):
        records = _event()
        records[-1].sequence = 11
        result = self.classify(records)
        overlaps = result["projection_overlap_counts"]
        self.assertEqual(overlaps["exact"], 0)
        self.assertEqual(overlaps["without_sequence"], 1)
        self.assertEqual(overlaps["without_size"], 0)
        self.assertEqual(overlaps["without_sequence_and_size"], 1)
        self.assertEqual(result["multi_sequence_fill_event_count"], 1)

    def test_size_mismatch_isolated_by_registered_projection(self):
        records = _event()
        records[-1].size = 778
        overlaps = self.classify(records)["projection_overlap_counts"]
        self.assertEqual(overlaps["exact"], 0)
        self.assertEqual(overlaps["without_sequence"], 0)
        self.assertEqual(overlaps["without_size"], 1)
        self.assertEqual(overlaps["without_sequence_and_size"], 1)

    def test_order_mismatch_does_not_false_match_any_projection(self):
        records = _event()
        records[-1].order_id = 900_000_002
        result = self.classify(records)
        self.assertEqual(
            set(result["projection_overlap_counts"].values()),
            {0},
        )
        self.assertEqual(
            set(result["projection_full_match_event_counts"].values()),
            {0},
        )

    def test_fill_without_cancel_and_fill_last_are_counted(self):
        record = _record(
            action="F",
            ts_recv=1_000_000_000,
            flags=RUNTIME.f_last,
        )
        result = self.classify([record])
        self.assertEqual(result["fill_event_without_cancel_count"], 1)
        self.assertEqual(result["fill_last_record_count"], 1)
        self.assertEqual(result["cancel_record_count_in_fill_bearing_events"], 0)

    def test_interleaved_instrument_events_remain_separate(self):
        left = _event()
        right = [copy.copy(record) for record in _event()]
        for record in right:
            record.instrument_id = 8
        records = [left[0], right[0], left[1], right[1]]
        for index, record in enumerate(records, start=1):
            record.ts_recv = 1_000_000_000 + index
            record.ts_event = record.ts_recv - 1
        result = self.classify(records)
        self.assertEqual(result["instrument_event_count"], 2)
        self.assertEqual(result["fill_bearing_event_count"], 2)
        self.assertEqual(result["projection_overlap_counts"]["exact"], 2)

    def test_output_is_aggregate_only_and_source_has_no_provider_client(self):
        result = self.classify(_event())
        encoded = json.dumps(result, sort_keys=True)
        self.assertNotIn("900000001", encoded)
        self.assertNotIn("123456789000", encoded)
        self.assertFalse(result["raw_record_values_persisted"])
        self.assertFalse(result["feature_values_persisted"])
        self.assertFalse(result["runtime_authority_created"])
        source = SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("from databento", source)
        self.assertNotIn("\nimport databento", source)
        self.assertNotIn("get_range(", source)


if __name__ == "__main__":
    unittest.main()
