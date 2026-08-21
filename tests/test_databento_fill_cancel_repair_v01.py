from __future__ import annotations

import re
import unittest
from pathlib import Path
from types import SimpleNamespace

from momentumbot.research import databento_feature_diagnostic_v03 as v03
from momentumbot.research.databento_fill_cancel_repair_v01 import (
    PARENT_SUCCESS_CONTENT_SHA256,
    REPAIR_CONTRACT_CONTENT_SHA256,
    build_fill_cancel_pairing,
    load_parent_success_audit,
    load_repair_contract,
    translate_xnas_instrument_event,
)
from momentumbot.research.databento_smoke import RuntimeConstants
from momentumbot.research.microstructure_contract import DepthAction


ROOT = Path(__file__).resolve().parents[1]
AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-fill-cancel-classifier-v0.1-"
    "run-32512602607-success-2026-08-21.json"
)
CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-fill-cancel-repair-v0.1.json"
)
SOURCE = (
    ROOT
    / "src"
    / "momentumbot"
    / "research"
    / "databento_fill_cancel_repair_v01.py"
)
FUTURE_EXECUTION = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-fill-cancel-repair-v0.1-execution.json"
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


def _exact_event() -> list[SimpleNamespace]:
    return [
        _record(action="F", ts_recv=1_000_000_000, flags=0),
        _record(action="C", ts_recv=1_000_000_001, flags=RUNTIME.f_last),
    ]


class DatabentoFillCancelRepairV01Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = load_parent_success_audit(AUDIT)
        cls.contract = load_repair_contract(
            CONTRACT,
            parent_success_audit=cls.audit,
        )

    def test_success_audit_and_repair_contract_are_hash_bound(self):
        self.assertEqual(
            self.audit["content_sha256"],
            PARENT_SUCCESS_CONTENT_SHA256,
        )
        self.assertEqual(
            self.contract["content_sha256"],
            REPAIR_CONTRACT_CONTENT_SHA256,
        )
        self.assertEqual(
            self.audit["repair_interpretation"][
                "coarse_only_full_match_event_count"
            ],
            13,
        )
        self.assertEqual(
            self.audit["repair_interpretation"][
                "coarse_only_match_fill_record_count"
            ],
            15,
        )

    def test_registration_is_unarmed_and_provider_free(self):
        self.assertFalse(self.contract["provider_purchase_authorized"])
        self.assertFalse(self.contract["execution_authorization_file_present"])
        self.assertEqual(
            self.contract["future_execution_gate"][
                "exact_request_count_authorized"
            ],
            0,
        )
        self.assertFalse(FUTURE_EXECUTION.exists())
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIsNone(
            re.search(r"^\s*(?:import databento|from databento)", source, re.MULTILINE)
        )
        self.assertNotIn("HistoricalClient", source)

    def test_exact_match_is_identical_to_frozen_v03_translation(self):
        records = _exact_event()
        plan = build_fill_cancel_pairing(records)
        self.assertEqual(plan.exact_match_count, 1)
        self.assertEqual(plan.coarse_only_match_count, 0)
        self.assertEqual(plan.extra_cancel_count, 0)
        expected = v03.translate_xnas_instrument_event(
            records,
            symbol="EQPT",
            runtime=RUNTIME,
        )
        actual = translate_xnas_instrument_event(
            records,
            symbol="EQPT",
            runtime=RUNTIME,
        )
        self.assertEqual(actual, expected)

    def test_price_only_exception_uses_cancel_payload_for_removal(self):
        records = _exact_event()
        records[0].price = 123_000_000_000
        with self.assertRaises(v03.SafeDiagnosticFailure) as caught:
            v03.translate_xnas_instrument_event(
                records,
                symbol="EQPT",
                runtime=RUNTIME,
            )
        self.assertEqual(
            (caught.exception.phase, caught.exception.code),
            ("normalize", "fill_cancel_unmatched"),
        )
        plan = build_fill_cancel_pairing(records)
        self.assertEqual(plan.exact_match_count, 0)
        self.assertEqual(plan.coarse_only_match_count, 1)
        translated = translate_xnas_instrument_event(
            records,
            symbol="EQPT",
            runtime=RUNTIME,
        )
        self.assertEqual(translated.matched_executed_removal_count, 1)
        self.assertEqual(translated.ignored_fill_marker_count, 1)
        self.assertEqual(len(translated.depth_events), 1)
        self.assertEqual(translated.depth_events[0].action, DepthAction.FILL)
        self.assertEqual(translated.depth_events[0].price_nanos, records[1].price)
        self.assertEqual(translated.depth_events[0].size, records[1].size)

    def test_sequence_and_size_differences_are_coarse_only_matches(self):
        records = _exact_event()
        records[0].sequence = 9
        records[0].size = 111
        plan = build_fill_cancel_pairing(records)
        self.assertEqual(plan.exact_match_count, 0)
        self.assertEqual(plan.coarse_only_match_count, 1)
        translated = translate_xnas_instrument_event(
            records,
            symbol="EQPT",
            runtime=RUNTIME,
        )
        self.assertEqual(translated.depth_events[0].sequence, records[1].sequence)
        self.assertEqual(translated.depth_events[0].size, records[1].size)

    def test_multiset_pairing_prefers_exact_then_stable_coarse_match(self):
        records = [
            _record(
                action="F",
                ts_recv=1_000_000_000,
                flags=0,
                price=100_000_000_000,
            ),
            _record(
                action="F",
                ts_recv=1_000_000_001,
                flags=0,
                price=101_000_000_000,
            ),
            _record(
                action="C",
                ts_recv=1_000_000_002,
                flags=0,
                price=102_000_000_000,
            ),
            _record(
                action="C",
                ts_recv=1_000_000_003,
                flags=0,
                price=100_000_000_000,
            ),
            _record(
                action="C",
                ts_recv=1_000_000_004,
                flags=RUNTIME.f_last,
                price=101_000_000_000,
            ),
        ]
        plan = build_fill_cancel_pairing(records)
        self.assertEqual(plan.matched_cancel_indexes, (3, 4))
        self.assertEqual(plan.exact_match_count, 2)
        self.assertEqual(plan.coarse_only_match_count, 0)
        self.assertEqual(plan.extra_cancel_count, 1)
        translated = translate_xnas_instrument_event(
            records,
            symbol="EQPT",
            runtime=RUNTIME,
        )
        self.assertEqual(
            [event.action for event in translated.depth_events],
            [DepthAction.CANCEL, DepthAction.FILL, DepthAction.FILL],
        )

    def test_multiple_coarse_matches_preserve_multiset_counts(self):
        records = [
            _record(action="F", ts_recv=1_000_000_000, flags=0, price=100),
            _record(action="F", ts_recv=1_000_000_001, flags=0, price=101),
            _record(action="C", ts_recv=1_000_000_002, flags=0, price=102),
            _record(
                action="C",
                ts_recv=1_000_000_003,
                flags=RUNTIME.f_last,
                price=103,
            ),
        ]
        plan = build_fill_cancel_pairing(records)
        self.assertEqual(plan.matched_cancel_indexes, (2, 3))
        self.assertEqual(plan.exact_match_count, 0)
        self.assertEqual(plan.coarse_only_match_count, 2)
        self.assertEqual(plan.fill_marker_count, 2)

    def test_order_id_or_side_mismatch_fails_closed(self):
        for field, value in (("order_id", 900_000_002), ("side", "B")):
            with self.subTest(field=field):
                records = _exact_event()
                setattr(records[-1], field, value)
                with self.assertRaises(v03.SafeDiagnosticFailure) as caught:
                    build_fill_cancel_pairing(records)
                self.assertEqual(
                    (caught.exception.phase, caught.exception.code),
                    ("normalize", "fill_cancel_unmatched"),
                )


if __name__ == "__main__":
    unittest.main()
