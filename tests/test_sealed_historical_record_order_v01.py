from __future__ import annotations

import copy
from dataclasses import asdict, replace
from decimal import Decimal
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from momentumbot.research import execution_realism as e
from momentumbot.research import prospective_market_input_capture as c
from momentumbot.research import sealed_historical_execution_diagnostic_v01 as d
from momentumbot.research import sealed_historical_record_order_v01 as a
from momentumbot.research import sealed_historical_record_order_registration_v01 as r
from momentumbot.research.sealed_historical_execution_quote_v01 import canonical_fingerprint, seal
from tests.test_prospective_market_input_capture import _opportunity_manifest, _request_evidence

ROOT = Path(__file__).resolve().parents[1]
HAS_SDK = importlib.util.find_spec("databento") is not None


class Store:
    def __init__(self, request, rows):
        self.metadata = {k: request[k] for k in ("dataset", "schema", "stype_in", "symbols")}
        self.metadata.update(start=request["start_ns"], end=request["end_ns"])
        self.rows = rows

    def to_df(self, **kwargs):
        if kwargs != {"map_symbols": True, "pretty_ts": False, "price_type": "fixed"}:
            raise ValueError("mapping must preserve integer nanoseconds and prices")
        return pd.DataFrame(self.rows)


class RecordOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.opportunities = _opportunity_manifest()
        cls.op = cls.opportunities["opportunities"][0]
        cls.identity = a.WindowIdentity(**{k: cls.op[k] for k in (
            "opportunity_id", "trading_date", "symbol", "decision_ts_ns")})
        cls.contract = c.load_capture_contract(ROOT / "research/strategy/prospective-market-input-capture-v0.1.json")
        cls.manifest = c.build_request_manifest(cls.contract, cls.opportunities)
        cls.qr, cls.sr = cls.manifest["requests"]
        cls.t = cls.op["decision_ts_ns"]

    def native(self, offset=0, **updates):
        row = {"symbol": "TEST", "ts_recv_ns": self.t + offset, "sequence": 10,
               "bid_px_nanos": 1_000_000_000, "bid_size": 200,
               "ask_px_nanos": 1_010_000_000, "ask_size": 554}
        row.update(updates)
        return row

    def indexed(self, rows, request=None):
        sha = canonical_fingerprint(request or self.qr)
        return [dict(row, source_request_sha256=sha, source_record_index=i) for i, row in enumerate(rows)]

    def statuses(self):
        return [{"symbol": "TEST", "ts_recv_ns": self.qr["start_ns"] - 1,
                 "action": 7, "is_trading": "Y"}]

    def window(self, rows=None, statuses=None):
        return a.capture_window(self.identity, self.qr, rows if rows is not None else self.indexed([self.native()]),
                                self.sr, statuses if statuses is not None else self.statuses())

    def test_registered_parent_chain_and_policy_body_equivalence(self):
        self.assertTrue(r.validate_registration(ROOT)["verification_passed"])
        self.assertFalse(r.contract()["acquisition_gate_passed"])
        self.assertEqual(r.contract()["provider_calls_authorized"], 0)

    def test_full_gits_fixture_is_lossless_and_never_executed(self):
        with patch.object(a, "capture_window", side_effect=AssertionError("diagnostic is not runtime input")), patch.object(a, "simulate_record_order_limit_order", side_effect=AssertionError("no historical fills")):
            report = r.verify_diagnostic_adapter(ROOT)
        self.assertEqual(report["row_count"], 1136)
        self.assertEqual(report["distinct_trade_cancel_native_key_pairs"], 175)
        self.assertEqual(report["normalized_native_content_sha256"], r.NORMALIZED_SHA)
        self.assertFalse(report["runtime_input_eligible"])

    def test_full_gits_mapped_store_preserves_every_original_normalized_field(self):
        projected, native = r.diagnostic_fixture(ROOT)
        store = Store(d.request(), [{k: v["value"] for k, v in row["fields"].items()} for row in projected])
        records = a.normalize_store(store, d.request())
        self.assertEqual([{k: row[k] for k in a.QUOTE_FIELDS} for row in records], native)
        self.assertEqual([row["source_record_index"] for row in records], list(range(1136)))
        with self.assertRaisesRegex(ValueError, "receive-time and sequence"):
            c._quote_events(native)

    def test_equal_keys_retain_distinct_and_identical_updates(self):
        native = [self.native(), self.native(ask_size=54), self.native(ask_size=54)]
        result = a.quote_events(self.indexed(native), self.qr)
        self.assertEqual([v.ask_size for v in result], [554, 54, 54])
        self.assertEqual([v.sequence for v in result], [10, 10, 10])
        self.assertEqual([v.source_record_index for v in result], [0, 1, 2])

    def test_gaps_reversals_duplicate_or_noninteger_tape_ordinals_rejected(self):
        for indices in ([1, 2], [0, 2], [1, 0], [0, 0], [0, True], [0, 1.0], [0, -1]):
            with self.subTest(indices=indices):
                rows = self.indexed([self.native(), self.native(ask_size=54)])
                for row, index in zip(rows, indices, strict=True): row["source_record_index"] = index
                with self.assertRaises(ValueError): a.quote_events(rows, self.qr)

    def test_backward_native_keys_never_sorted_into_validity(self):
        for second in (self.native(-1), self.native(sequence=9)):
            with self.subTest(second=second):
                rows = self.indexed([self.native(), second])
                before = copy.deepcopy(rows)
                with self.assertRaisesRegex(ValueError, "reversed"): a.quote_events(rows, self.qr)
                self.assertEqual(rows, before)

    def test_source_identity_symbols_schema_extra_fields_and_empty_tape_rejected(self):
        for field, value in (("source_request_sha256", "f" * 64), ("symbol", "OTHER"),
                             ("sequence", True), ("ts_recv_ns", float(self.t)), ("extra", 1)):
            with self.subTest(field=field):
                rows = self.indexed([self.native()]); rows[0][field] = value
                with self.assertRaises(ValueError): a.quote_events(rows, self.qr)
        with self.assertRaises(ValueError): a.quote_events([], self.qr)
        with self.assertRaises(ValueError): a.quote_events(self.indexed([self.native()]), self.sr)

    def test_request_receive_time_bounds_are_exact_nanoseconds(self):
        for ns in (self.qr["start_ns"] - 1, self.qr["end_ns"]):
            with self.assertRaises(ValueError): a.quote_events(self.indexed([self.native(ts_recv_ns=ns)]), self.qr)
        rows = self.indexed([self.native(ts_recv_ns=self.qr["start_ns"]), self.native(ts_recv_ns=self.qr["end_ns"]-1)])
        self.assertEqual(len(a.quote_events(rows, self.qr)), 2)

    def test_frozen_metadata_and_integer_mapping_rejections_remain(self):
        raw = {"symbol": "TEST", "ts_recv": self.t, "sequence": 10,
               "bid_px_00": 1_000_000_000, "bid_sz_00": 200, "ask_px_00": 1_010_000_000, "ask_sz_00": 50}
        for field, value in (("dataset", "OTHER"), ("schema", "status"), ("stype_in", "instrument_id"),
                             ("symbols", ["OTHER"]), ("start", self.qr["start_ns"]-1), ("end", self.qr["end_ns"]+1)):
            with self.subTest(field=field):
                store = Store(self.qr, [raw]); store.metadata[field] = value
                with self.assertRaises(ValueError): a.normalize_store(store, self.qr)
        for field in ("ts_recv", "sequence", "bid_px_00", "ask_sz_00"):
            with self.subTest(field=field):
                with self.assertRaises(ValueError): a.normalize_store(Store(self.qr, [{**raw, field: True}]), self.qr)

    def test_status_conversion_vocabulary_and_order_are_frozen(self):
        status = self.statuses()[0]
        raw = {**status, "ts_recv": status["ts_recv_ns"]}; del raw["ts_recv_ns"]
        self.assertEqual(a.normalize_store(Store(self.sr, [raw]), self.sr), [status])
        for action in (15, -1, True):
            with self.assertRaises(ValueError): a.status_events([{**status, "action": action}], self.sr)
        for value in ("UNKNOWN", "", True):
            with self.assertRaises(ValueError): a.status_events([{**status, "is_trading": value}], self.sr)
        with self.assertRaises(ValueError): a.status_events([], self.sr)
        with self.assertRaises(ValueError): a.status_events([status, {**status, "ts_recv_ns": status["ts_recv_ns"]-1}], self.sr)

    def test_capture_retains_ties_and_ordinals_after_unusable_rows(self):
        rows = self.indexed([self.native(-1, bid_size=0), self.native(), self.native(ask_size=54)])
        result = self.window(rows)
        self.assertEqual(result["unusable_or_status_unknown_quote_count"], 1)
        self.assertEqual([v["source_record_index"] for v in result["quotes"]], [1, 2])
        events = a.top_of_book_events(result, self.identity, self.qr, rows, self.sr, self.statuses())
        self.assertEqual([v.ask_size for v in events], [554, 54])
        self.assertEqual([v.sequence for v in events], [10, 10])

    def test_equal_time_status_ambiguity_never_resolved_by_quote_sequence_or_ordinal(self):
        statuses = self.statuses() + [{"symbol": "TEST", "ts_recv_ns": self.t, "action": 7, "is_trading": "Y"}]
        result = self.window(self.indexed([self.native(), self.native(ask_size=54)]), statuses)
        self.assertEqual(result["usable_quote_count"], 0)
        self.assertEqual(result["unusable_or_status_unknown_quote_count"], 2)

    def test_unknown_initial_or_later_status_remains_unavailable(self):
        for statuses in ([{**self.statuses()[0], "is_trading": "~"}],
                         [{**self.statuses()[0], "ts_recv_ns": self.t - 1}],
                         self.statuses() + [{"symbol": "TEST", "ts_recv_ns": self.t+1, "action": 0, "is_trading": "~"}]):
            with self.subTest(statuses=statuses):
                result = self.window(statuses=statuses)
                self.assertEqual(result["capture_status"], "unavailable_status_not_causally_known")
                self.assertEqual(result["usable_quote_count"], 0)

    def test_request_substitution_or_incomplete_window_blocks(self):
        for request in ({**self.qr, "end_ns": self.qr["end_ns"]-1},
                        {**self.qr, "start_ns": self.qr["start_ns"]+1},
                        {**self.qr, "symbols": ["OTHER"]}):
            with self.assertRaises(ValueError):
                a.capture_window(self.identity, request, self.indexed([self.native()], request), self.sr, self.statuses())

    def test_rehashed_capture_tampering_cannot_pass_without_source_replay(self):
        rows = self.indexed([self.native(), self.native(ask_size=54)])
        result = self.window(rows)
        for field, value in (("sequence", 11), ("source_record_index", 7), ("ask_size", 1), ("halted", True), ("status_action", 0)):
            with self.subTest(field=field):
                altered = copy.deepcopy(result); altered["quotes"][1][field] = value
                altered = seal({k: v for k, v in altered.items() if k != "content_sha256"})
                with self.assertRaises(ValueError):
                    a.validate_capture_window(altered, self.identity, self.qr, rows, self.sr, self.statuses())

    def test_strict_stream_capture_is_identical_to_frozen_prospective_mechanics(self):
        for case in ("normal", "unknown", "halt", "same_time", "crossed", "tail", "no_initial"):
            with self.subTest(case=case):
                native = [self.native(-100_000_000), self.native(sequence=11), self.native(550_000_000, sequence=12)]
                statuses = self.statuses()
                if case == "unknown": statuses[0]["is_trading"] = "~"
                if case == "halt": statuses[0]["is_trading"] = "N"
                if case == "same_time": statuses.append({**statuses[0], "ts_recv_ns": self.t})
                if case == "crossed": native[1]["bid_px_nanos"] = native[1]["ask_px_nanos"]
                if case == "tail": statuses.append({**statuses[0], "ts_recv_ns": self.t+550_000_000, "is_trading": "~"})
                if case == "no_initial": statuses[0]["ts_recv_ns"] = self.t-1
                frozen = c.build_market_input_capture(self.contract, self.opportunities, self.manifest,
                    _request_evidence(self.manifest, quote_count=len(native), status_count=len(statuses)), native, statuses)["captures"][0]
                observed = self.window(self.indexed(native), statuses)
                comparable = {key: copy.deepcopy(observed[key]) for key in frozen}
                for row in comparable["quotes"]:
                    for key in a.ORDER_FIELDS: del row[key]
                self.assertEqual(comparable, frozen)

    def event(self, offset, index, **values):
        return a.RecordOrderedTopOfBook(symbol="TEST", ts_recv_ns=self.t+offset, sequence=values.pop("sequence", 10),
            bid_price=Decimal("1"), bid_size=200, ask_price=values.pop("ask_price", Decimal("1.01")),
            ask_size=values.pop("ask_size", 100), source_request_sha256="a"*64,
            source_record_index=index, **values)

    def order(self, side=e.OrderSide.BUY):
        return e.MarketableLimitOrder("synthetic-only", "TEST", side, 1000, self.t,
                                     Decimal("1.05") if side is e.OrderSide.BUY else Decimal("0.99"))

    def test_execution_at_arrival_uses_last_tied_state_not_transient_size(self):
        events = [self.event(100_000_000, 0, ask_size=554), self.event(100_000_000, 1, ask_size=54)]
        result = a.simulate_record_order_limit_order(self.order(), events, e.BASELINE_CONSERVATIVE_POLICY)
        self.assertEqual(result.filled_quantity, 13)
        self.assertEqual(result.displayed_contra_size, 54)
        with self.assertRaises(ValueError): e.simulate_marketable_limit_order(self.order(), events, e.BASELINE_CONSERVATIVE_POLICY)

    def test_execution_after_arrival_keeps_first_eligible_state_and_no_refill(self):
        events = [self.event(100_000_001, 0, ask_price=Decimal("1.06")),
                  self.event(100_000_001, 1, ask_size=54), self.event(100_000_001, 2, ask_size=1000)]
        result = a.simulate_record_order_limit_order(self.order(), events, e.BASELINE_CONSERVATIVE_POLICY)
        self.assertEqual(result.filled_quantity, 13)
        self.assertEqual(result.unfilled_quantity, 987)

    def test_execution_keeps_cancellation_exclusive_and_freshness_inclusive(self):
        for policy in (e.BASELINE_CONSERVATIVE_POLICY, e.STRESS_POLICY):
            arrival = policy.decision_to_arrival_ms * 1_000_000
            ack = arrival + (policy.cancel_after_arrival_ms + policy.cancel_ack_ms)*1_000_000
            stale = arrival - policy.max_quote_age_ms*1_000_000
            for offset, fills in ((stale-1, False), (stale, True), (ack-1, True), (ack, False)):
                with self.subTest(policy=policy.policy_id, offset=offset):
                    result = a.simulate_record_order_limit_order(self.order(), [self.event(offset, 0)], policy)
                    self.assertEqual(result.filled_quantity > 0, fills)

    def test_execution_provenance_and_original_order_required(self):
        event = self.event(0, 2)
        native = e.TopOfBookEvent(**{k:v for k,v in asdict(event).items() if k not in a.ORDER_FIELDS})
        for events in ([native], [event, replace(event, source_record_index=1)],
                       [event, replace(event, source_record_index=3, sequence=9)],
                       [event, replace(event, source_record_index=3, source_request_sha256="b"*64)]):
            with self.assertRaises(ValueError): a.simulate_record_order_limit_order(self.order(), events, e.STRESS_POLICY)

    def test_strict_execution_streams_match_both_frozen_policies_and_sides(self):
        for policy in (e.BASELINE_CONSERVATIVE_POLICY, e.STRESS_POLICY):
            for side in (e.OrderSide.BUY, e.OrderSide.SELL):
                for variant in ("normal", "halted", "resume", "no_size", "expensive", "stale", "empty"):
                    with self.subTest(policy=policy.policy_id, side=side, variant=variant):
                        events = [self.event(90_000_000, 0, sequence=10), self.event(300_000_000, 1, sequence=11)]
                        if variant == "halted": events = [replace(v, halted=True) for v in events]
                        if variant == "resume": events[0] = replace(events[0], halted=True)
                        if variant == "no_size": events = [replace(v, ask_size=0, bid_size=0) for v in events]
                        if variant == "expensive": events = [replace(v, ask_price=Decimal("2")) for v in events]
                        if variant == "stale": events = [self.event(-100_000_000, 0)]
                        if variant == "empty": events = []
                        native = [e.TopOfBookEvent(**{k:v for k,v in asdict(event).items() if k not in a.ORDER_FIELDS}) for event in events]
                        self.assertEqual(a.simulate_record_order_limit_order(self.order(side), events, policy),
                                         e.simulate_marketable_limit_order(self.order(side), native, policy))

    def test_semantic_guard_detects_latency_and_cross_schema_ambiguity_changes(self):
        source = (ROOT / r.MODULE_PATH).read_text()
        for old, new in (("arrival = order.decision_ts_ns +", "arrival = 1 + order.decision_ts_ns +"),
                         ("if quote.ts_recv_ns in status_time_set:", "if False:")):
            with self.subTest(old=old), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for path in (r.MODULE_PATH, "src/momentumbot/research/execution_realism.py", "src/momentumbot/research/prospective_market_input_capture.py"):
                    output = root / path; output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_text(source.replace(old, new) if path == r.MODULE_PATH else (ROOT/path).read_text())
                with self.assertRaises(ValueError): r.validate_mechanical_equivalence(root)

    @unittest.skipUnless(HAS_SDK, "pinned SDK covered by dedicated record-order validation")
    def test_real_pinned_sdk_preserves_same_message_record_order_offline(self):
        import databento
        import databento_dbn as dbn
        from datetime import date, timedelta
        from types import SimpleNamespace as N
        request = d.request()
        day = date.fromisoformat(request["trading_date"])
        ns = request["start_ns"] + 1
        metadata = dbn.Metadata(dataset="XNAS.ITCH", start=request["start_ns"], end=request["end_ns"],
            stype_in=dbn.SType.RAW_SYMBOL, stype_out=dbn.SType.INSTRUMENT_ID, schema=dbn.Schema.MBP_1,
            symbols=["GITS"], mappings=[N(raw_symbol="GITS", intervals=[N(start_date=day,
                end_date=day+timedelta(days=1), symbol="1")])])
        messages = [dbn.MBP1Msg(publisher_id=2, instrument_id=1, ts_event=ns-1,
            price=1_010_000_000, size=500, action=action, side=dbn.Side.ASK,
            depth=0, ts_recv=ns, sequence=1, flags=130,
            levels=dbn.BidAskPair(bid_px=1_000_000_000, ask_px=1_010_000_000,
                                  bid_sz=100, ask_sz=size))
            for action, size in ((dbn.Action.TRADE, 554), (dbn.Action.CANCEL, 54))]
        store = databento.DBNStore.from_bytes(io.BytesIO(metadata.encode()+b"".join(bytes(v) for v in messages)))
        result = a.normalize_store(store, d.request())
        self.assertEqual([row["source_record_index"] for row in result], [0, 1])
        self.assertEqual([row["sequence"] for row in result], [1, 1])
        self.assertEqual([row["ask_size"] for row in result], [554, 54])


if __name__ == "__main__":
    unittest.main()
