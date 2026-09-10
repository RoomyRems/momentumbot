"""Verified no-update observations are distinct from unverified source data."""
from contextlib import ExitStack
from copy import deepcopy
import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from momentumbot.research import sealed_historical_entry_reference_evidence_v01 as m

DAY = "2025-01-02"
MIDNIGHT = m.adapter.capture._utc_midnight_ns(DAY)
DECISION = MIDNIGHT + 50_000_000_000_000


def requests():
    shared = {"trading_date": DAY, "dataset": "XNAS.ITCH", "symbols": ["SYN"],
        "stype_in": "raw_symbol", "end_ns": DECISION + 550_000_001, "end_exclusive": True}
    return ({**shared, "request_id": DAY + "-SYN-mbp-1", "schema": "mbp-1",
             "start_ns": DECISION - 5_000_000_000},
            {**shared, "request_id": DAY + "-SYN-status", "schema": "status", "start_ns": MIDNIGHT})


def raw_quotes(offsets=(-50_000_000,)):
    req, _ = requests()
    return [{"symbol": "SYN", "ts_recv_ns": DECISION + offset, "sequence": i,
        "bid_px_nanos": 1_000_000_000, "bid_size": 100,
        "ask_px_nanos": 1_010_000_000, "ask_size": 100,
        "source_request_sha256": m.fingerprint(req), "source_record_index": i}
        for i, offset in enumerate(offsets)]


def observation(offsets=(-50_000_000,), *, state="complete", quote_changes=None, status_changes=None):
    qr, sr = requests()
    raw = raw_quotes(offsets)
    if quote_changes:
        quote_changes(raw)
    quotes = tuple(m.adapter.RecordOrderedQuote(**row) for row in raw)
    statuses = [{"symbol": "SYN", "ts_recv_ns": MIDNIGHT, "action": 1, "is_trading": "Y"}]
    if status_changes:
        status_changes(statuses)
    return m.entry_observation({"opportunity_id": "synthetic", "symbol": "SYN", "trading_date": DAY,
        "decision_ts_ns": DECISION}, qr, quotes, sr, m.adapter.status_events(statuses, sr), source_state=state)


class EntryObservationTests(unittest.TestCase):
    def test_both_inclusive_endpoints_are_eligible(self):
        for offset in (-100_000_000, 0):
            with self.subTest(offset=offset):
                result = observation((offset,))
                self.assertEqual(result["observation"], "reference_observed")
                self.assertEqual(result["reference_age_ns"], -offset)
                self.assertFalse(result["order_authorized"])

    def test_older_reference_does_not_relax_freshness(self):
        result = observation((-100_000_001,))
        self.assertEqual(result["observation"], "no_quote_update_observed")
        self.assertEqual(result["older_quote_updates_in_original_request"], 1)
        self.assertEqual(result["entry_gate"], "withhold_entry_under_observed_update_policy")

    def test_future_quote_never_authorizes_earlier_entry(self):
        self.assertEqual(observation((1,))["observation"], "no_quote_update_observed")

    def test_future_quote_values_do_not_change_observation(self):
        a = observation((-20_000_000, 1))
        b = observation((-20_000_000, 1), quote_changes=lambda rows: rows[1].update(
            ask_px_nanos=50_000_000_000, ask_size=10_000_000))
        self.assertEqual(a, b)

    def test_future_unknown_status_does_not_rewrite_decision(self):
        a = observation()
        b = observation(status_changes=lambda rows: rows.append({"symbol": "SYN",
            "ts_recv_ns": DECISION + 1, "action": 1, "is_trading": "~"}))
        self.assertEqual(a, b)

    def test_last_usable_update_preserves_ordinal(self):
        result = observation((-90_000_000, -10_000_000, -10_000_000))
        self.assertEqual(result["reference_source_record_index"], 2)

    def test_locked_or_one_sided_books_do_not_supply_reference(self):
        for changes in ({"ask_px_nanos": 1_000_000_000}, {"bid_size": 0}, {"ask_px_nanos": 0}):
            with self.subTest(changes=changes):
                result = observation(quote_changes=lambda rows: rows[0].update(changes))
                self.assertEqual(result["observation"], "no_usable_quote_update")

    def test_frozen_latest_usable_selection_is_preserved(self):
        result = observation((-90_000_000, -1), quote_changes=lambda rows: rows[1].update(bid_size=0))
        self.assertEqual(result["reference_source_record_index"], 0)

    def test_equal_receive_time_status_is_ambiguous(self):
        result = observation(status_changes=lambda rows: rows.append({"symbol": "SYN",
            "ts_recv_ns": DECISION - 50_000_000, "action": 1, "is_trading": "Y"}))
        self.assertEqual(result["filtered_update_counts"], {"ambiguous_status_time": 1})
        self.assertEqual(result["observation"], "no_usable_quote_update")

    def test_unknown_causal_status_stays_unresolved(self):
        result = observation(status_changes=lambda rows: rows[0].update(is_trading="~"))
        self.assertEqual(result["entry_gate"], "unresolved")

    def test_unverified_source_is_never_known_abstention(self):
        result = observation((), state="unverified")
        self.assertEqual(result["observation"], "unverified_source")
        self.assertEqual(result["entry_gate"], "unresolved")

    def test_verified_empty_source_withholds_entry(self):
        result = observation((), state="verified_empty")
        self.assertEqual(result["observation"], "no_quote_update_observed")
        self.assertFalse(result["order_authorized"])

    def test_empty_without_empty_evidence_is_rejected(self):
        with self.assertRaises(ValueError):
            observation((), state="complete")

    def test_nonempty_source_cannot_claim_empty(self):
        with self.assertRaises(ValueError):
            observation(state="verified_empty")

    def test_discontinuous_ordinals_and_wrong_symbols_are_rejected(self):
        for changes in ({"source_record_index": 1}, {"symbol": "OTHER"}, {"source_request_sha256": "0" * 64}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                observation(quote_changes=lambda rows: rows[0].update(changes))

    def test_outside_request_quote_is_rejected(self):
        with self.assertRaises(ValueError):
            observation((-5_000_000_001,))

    def test_halted_quote_is_not_order_authority(self):
        result = observation(status_changes=lambda rows: rows[0].update(is_trading="N"))
        self.assertEqual(result["entry_gate"], "reference_present_requires_remaining_entry_checks")
        self.assertFalse(result["order_authorized"])


def source_fixture():
    req, _ = requests()
    rows = raw_quotes()
    decoded = b"".join((json.dumps(row, sort_keys=True) + "\n").encode() for row in rows)
    tape = gzip.compress(decoded, mtime=0)
    spec = {"path": "tapes/source.jsonl.gz", "file_bytes": len(tape),
        "file_sha256": hashlib.sha256(tape).hexdigest(), "normalized_bytes": len(decoded),
        "normalized_sha256": hashlib.sha256(decoded).hexdigest(), "row_count": len(rows)}
    receipt = m.seal({"request": req, "completion": {"status": "complete", "error": None,
        "failure_stage": None, "normalization": {"row_count": len(rows)}, "tape": spec}})
    evidence = m.seal({"classification": "complete", "request_id": req["request_id"],
        "request_content_sha256": m.fingerprint(req), "receipt_path": "receipts/source.json",
        "receipt_file_sha256": hashlib.sha256(m.encoded(receipt)).hexdigest(),
        "records_content_sha256": m.fingerprint(rows), "tape": spec})
    return req, rows, tape, receipt, evidence


def fixture_archive(tape, receipt):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("tapes/source.jsonl.gz", tape)
        archive.writestr("receipts/source.json", m.encoded(receipt))
    buffer.seek(0)
    return zipfile.ZipFile(buffer)


class SourceProofTests(unittest.TestCase):
    def test_nonempty_source_checks_physical_logical_and_receipt_identity(self):
        req, rows, tape, receipt, evidence = source_fixture()
        with fixture_archive(tape, receipt) as archive:
            got = m.request_records(archive, req, evidence)
        self.assertEqual(got[0].source_record_index, rows[0]["source_record_index"])

    def test_failed_partial_or_incomplete_receipt_cannot_prove_absence(self):
        for change in ({"status": "failed"}, {"error": "truncated"}, {"partial": ["row"]},
                       {"partial_tape": "somewhere"}, {"failure_stage": "decode"}):
            req, _, tape, receipt, evidence = source_fixture()
            receipt["completion"].update(change)
            receipt = m.seal(receipt)
            evidence["receipt_file_sha256"] = hashlib.sha256(m.encoded(receipt)).hexdigest()
            evidence = m.seal(evidence)
            with self.subTest(change=change), fixture_archive(tape, receipt) as archive:
                with self.assertRaises(ValueError):
                    m.request_records(archive, req, evidence)

    def test_tape_mutation_is_rejected(self):
        req, _, tape, receipt, evidence = source_fixture()
        with fixture_archive(tape + b"altered", receipt) as archive, self.assertRaises(ValueError):
            m.request_records(archive, req, evidence)

    def test_rehashed_evidence_with_wrong_logical_rows_is_rejected(self):
        req, _, tape, receipt, evidence = source_fixture()
        evidence["records_content_sha256"] = "0" * 64
        with fixture_archive(tape, receipt) as archive, self.assertRaises(ValueError):
            m.request_records(archive, req, m.seal(evidence))

    def test_wrong_archive_bytes_rejected_before_reading(self):
        with ExitStack() as stack, self.assertRaises(ValueError):
            m.open_archive(stack, b"wrong", {"bytes": 5, "sha256": "0" * 64})

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaises(ValueError):
            m.document(b'{"a":1,"a":2}')

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            m.write_new(path, {"first": 1})
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                m.write_new(path, {"second": 2})
            self.assertEqual(path.read_bytes(), before)


class EmptyResponseTests(unittest.TestCase):
    @staticmethod
    def fixture():
        req, _ = requests()
        value = lambda v: {"value": v}
        return req, {"diagnostic_evidence_complete": True, "error": None, "native_observation": {
            "decoding_complete": True, "native_record_count": 0, "native_mbp1_count": 0,
            "record_types": {}, "decoded_v3_record_bytes_sha256": hashlib.sha256(b"").hexdigest(),
            "metadata": {"exact_request_metadata": True, "not_found": [], "partial": [],
                "dataset": value("XNAS.ITCH"), "schema": value(1), "symbols": [value("SYN")],
                "start": value(req["start_ns"]), "end": value(req["end_ns"]),
                "limit": {"kind": "null"}, "mapping_interval_count": 1,
                "mappings": [{"raw_symbol": value("SYN"), "intervals": [
                    {"start_date": DAY, "end_date": "2025-01-03", "instrument_id": 1}]}]}}}

    def test_exact_verified_empty_request_is_supported(self):
        req, report = self.fixture()
        m.verify_empty_quote(report, req)

    def test_truncated_or_nonempty_native_result_is_rejected(self):
        for changes in ({"decoding_complete": False}, {"native_record_count": 1}, {"native_mbp1_count": 1}):
            req, report = self.fixture()
            report["native_observation"].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                m.verify_empty_quote(report, req)

    def test_empty_result_needs_exact_bounds_and_mapping(self):
        for change in ({"not_found": ["SYN"]}, {"partial": ["SYN"]},
                       {"start": {"value": DECISION}}, {"limit": {"kind": "integer", "value": 1}},
                       {"mapping_interval_count": 0}):
            req, report = self.fixture()
            report["native_observation"]["metadata"].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                m.verify_empty_quote(report, req)

    def test_source_proof_does_not_open_financial_or_market_completeness_gate(self):
        self.assertTrue(all(v is False for v in m.BOUNDARY.values()))


if __name__ == "__main__":
    unittest.main()
