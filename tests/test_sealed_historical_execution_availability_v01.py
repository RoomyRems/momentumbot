from __future__ import annotations

import copy
from dataclasses import replace
import gzip
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from momentumbot.research import sealed_historical_execution_availability_v01 as a
from momentumbot.research import sealed_historical_record_order_v01 as adapter
from momentumbot.research.sealed_historical_execution_quote_v01 import (
    PLAN_PATH, canonical_fingerprint, frozen, seal,
)

ROOT = Path(__file__).resolve().parents[1]


def source(request, records):
    """Synthetic evidence only; the production loader requires exact ZIPs."""
    return a.RequestInput(copy.deepcopy(request), seal({
        "request_id": request["request_id"],
        "request_content_sha256": canonical_fingerprint(request),
        "classification": "unavailable" if records is None else "complete",
        "archive_sha256": "a" * 64, "receipt_path": "synthetic.json",
        "receipt_file_sha256": "b" * 64,
        "tape": None if records is None else {"synthetic": True},
        "records_content_sha256": None if records is None else canonical_fingerprint(records),
        "unavailable_code": "metadata_only_exact_request" if records is None else None,
    }), copy.deepcopy(records))


def quote(request, ts, index=0, **updates):
    return {"symbol": request["symbols"][0], "ts_recv_ns": ts, "sequence": 10,
        "bid_px_nanos": 1_000_000_000, "ask_px_nanos": 1_010_000_000,
        "bid_size": 200, "ask_size": 100,
        "source_request_sha256": canonical_fingerprint(request),
        "source_record_index": index, **updates}


def status(request, **updates):
    return {"symbol": request["symbols"][0], "ts_recv_ns": request["start_ns"],
        "action": 7, "is_trading": "Y", **updates}


def synthetic_inputs(opportunities, requests):
    values = []
    for request in requests:
        if request["request_id"] == a.JVA_REQUEST:
            records = None
        elif request["schema"] == "status":
            records = [status(request)]
        else:
            times = sorted(op["decision_ts_ns"] + offset
                for op in opportunities["opportunities"]
                if (op["trading_date"], op["symbol"]) == (request["trading_date"], request["symbols"][0])
                for offset in (-100_000_000, 0, 550_000_000))
            records = [quote(request, ts, i) for i, ts in enumerate(times)]
        values.append(source(request, records))
    return values


class AvailabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.opportunities = frozen(ROOT / PLAN_PATH / "opportunity-manifest.json")
        cls.requests = frozen(ROOT / PLAN_PATH / "request-manifest.json")["requests"]
        cls.op = cls.opportunities["opportunities"][0]
        cls.qr, cls.sr = cls.requests[:2]
        cls.t = cls.op["decision_ts_ns"]

    def compose(self, quotes=None, statuses=None, opportunity=None):
        return a.compose_opportunity(opportunity or self.op,
            source(self.qr, [quote(self.qr, self.t)] if quotes is None else quotes),
            source(self.sr, [status(self.sr)] if statuses is None else statuses))

    def test_registration_rederives_exact_frozen_parent_chain(self):
        result = a.validate_registration(ROOT)
        self.assertTrue(result["verification_passed"])
        self.assertEqual(result["parent_commit_sha"], "24aaa19c50a39bce43ef9491f7630e2a81e330f8")
        self.assertEqual(a.contract()["opportunity_count"], 109)
        self.assertEqual(a.contract()["window_before_decision_ns"], 100_000_000)
        self.assertEqual(a.contract()["window_after_decision_ns"], 550_000_000)
        self.assertEqual(a.contract()["boundary"], a.BOUNDARY)

    def test_rehashed_contract_cannot_change_thresholds_or_population(self):
        actual_frozen = a.frozen
        for key, value in (("window_before_decision_ns", 101_000_000),
                           ("opportunity_count", 108), ("unavailable_request", "OTHER")):
            changed = dict(a.contract(), **{key: value})
            changed = seal({k: v for k, v in changed.items() if k != "content_sha256"})
            with self.subTest(key=key), patch.object(a, "frozen", side_effect=lambda path:
                    changed if path == ROOT / a.CONTRACT_PATH else actual_frozen(path)):
                with self.assertRaisesRegex(ValueError, "availability registration"):
                    a.validate_registration(ROOT)

    def test_changed_frozen_parent_is_rejected_before_composition(self):
        actual_sha = a.file_sha
        path = ROOT / "src/momentumbot/research/prospective_daily_account_runtime.py"
        with patch.object(a, "file_sha", side_effect=lambda p: "0" * 64 if p == path else actual_sha(p)):
            with self.assertRaisesRegex(ValueError, "frozen availability parent differs"):
                a.validate_registration(ROOT)

    def test_fresh_reference_preserves_exact_identity_and_all_closed_gates(self):
        before = copy.deepcopy(self.op)
        result = self.compose()
        self.assertEqual(result["opportunity"], before)
        self.assertEqual(self.op, before)
        self.assertEqual(result["input_status"], "available")
        self.assertEqual(result["decision_reference_age_ns"], 0)
        for key, value in a.BOUNDARY.items():
            self.assertEqual(result[key], value)
        self.assertFalse(result["availability_is_trade_or_order_eligibility"])

    def test_reference_100ms_boundary_is_inclusive(self):
        result = self.compose([quote(self.qr, self.t - 100_000_000)])
        self.assertEqual(result["input_status"], "available")
        self.assertEqual(result["decision_reference_age_ns"], 100_000_000)

    def test_stale_or_postdecision_quotes_never_become_reference(self):
        # Use a later opportunity in the same exact tape to test a stale quote
        # that is still inside the request's full bounds.
        op = next(o for o in self.opportunities["opportunities"]
                  if o["symbol"] == self.op["symbol"] and o["trading_date"] == self.op["trading_date"]
                  and o["decision_ts_ns"] > self.t + 100_000_001)
        for ts in (op["decision_ts_ns"] - 100_000_001, op["decision_ts_ns"] + 1):
            result = self.compose([quote(self.qr, ts)], opportunity=op)
            self.assertEqual(result["reason"], "unavailable_no_fresh_decision_quote")
            self.assertIsNone(result["decision_reference"])

    def test_latest_original_ordinal_resolves_same_native_key(self):
        rows = [quote(self.qr, self.t, 0, ask_size=554), quote(self.qr, self.t, 1, ask_size=54)]
        result = self.compose(rows)
        self.assertEqual([v["source_record_index"] for v in result["capture"]["quotes"]], [0, 1])
        self.assertEqual(result["decision_reference"]["ask_size"], 54)
        self.assertEqual(result["decision_reference"]["source_record_index"], 1)
        self.assertEqual([v["sequence"] for v in result["capture"]["quotes"]], [10, 10])

    def test_unusable_quotes_do_not_renumber_source_ordinals(self):
        rows = [quote(self.qr, self.t - 1, 0, bid_size=0), quote(self.qr, self.t, 1)]
        result = self.compose(rows)
        self.assertEqual(result["decision_reference"]["source_record_index"], 1)
        self.assertEqual(result["capture"]["unusable_or_status_unknown_quote_count"], 1)

    def test_quote_status_tie_is_not_resolved_by_quote_sequence(self):
        result = self.compose(statuses=[status(self.sr), status(self.sr, ts_recv_ns=self.t)])
        self.assertEqual(result["reason"], "unavailable_no_fresh_decision_quote")
        self.assertEqual(result["capture"]["usable_quote_count"], 0)

    def test_unknown_initial_late_and_tail_status_fail_closed(self):
        cases = ([status(self.sr, is_trading="~")],
            [status(self.sr, ts_recv_ns=self.t - 1)],
            [status(self.sr), status(self.sr, ts_recv_ns=self.t + 550_000_000, is_trading="~")])
        for statuses in cases:
            with self.subTest(statuses=statuses):
                result = self.compose(statuses=statuses)
                self.assertEqual(result["reason"], "unavailable_status_not_causally_known")
                self.assertIsNone(result["decision_reference"])
                self.assertFalse(result["capture"]["status_coverage_complete"])

    def test_known_halt_is_retained_as_its_own_input_state(self):
        result = self.compose(statuses=[status(self.sr, is_trading="N")])
        self.assertEqual(result["input_status"], "halted")
        self.assertEqual(result["reason"], "known_halted_decision_reference")
        self.assertTrue(result["decision_reference"]["halted"])

    def test_jva_is_explicitly_unavailable_without_synthetic_empty_tape(self):
        op = next(o for o in self.opportunities["opportunities"] if o["opportunity_id"] == a.JVA_OPPORTUNITY)
        qr, sr = self.requests[24:26]
        result = a.compose_opportunity(op, source(qr, None), source(sr, [status(sr)]))
        self.assertEqual(result["opportunity"], op)
        self.assertEqual(result["reason"], "unavailable_exact_quote_request")
        self.assertIsNone(result["capture"])
        self.assertIsNone(result["decision_reference"])

    def test_missing_status_request_remains_distinct(self):
        result = a.compose_opportunity(self.op, source(self.qr, [quote(self.qr, self.t)]), source(self.sr, None))
        self.assertEqual(result["reason"], "unavailable_exact_status_request")
        self.assertIsNone(result["capture"])

    def test_empty_substituted_or_reordered_source_records_are_rejected(self):
        good = source(self.qr, [quote(self.qr, self.t)])
        bad_sources = [source(self.qr, []), replace(source(self.qr, None), records=[]),
            replace(good, records=[quote(self.qr, self.t, ask_size=99)]),
            source(self.qr, [quote(self.qr, self.t, 1), quote(self.qr, self.t, 0)]),
            source(self.qr, [quote(self.qr, self.t, source_request_sha256="f" * 64)])]
        for value in bad_sources:
            with self.subTest(value=value), self.assertRaises(ValueError):
                a.compose_opportunity(self.op, value, source(self.sr, [status(self.sr)]))

    def test_request_identity_and_incomplete_window_substitution_rejected(self):
        for op in ({**self.op, "symbol": "OTHER"},
                   {**self.op, "trading_date": "2025-06-02"},
                   {**self.op, "decision_ts_ns": self.qr["end_ns"] - 550_000_000}):
            with self.subTest(op=op), self.assertRaises(ValueError):
                self.compose(opportunity=op)

    def test_all_109_opportunities_profiles_and_30_dates_retained(self):
        inputs = synthetic_inputs(self.opportunities, self.requests)
        before = copy.deepcopy(self.opportunities)
        with patch.object(socket, "socket", side_effect=AssertionError("no provider calls")), \
             patch.object(adapter, "simulate_record_order_limit_order", side_effect=AssertionError("no fills")):
            dates, summary = a._build_dates(self.opportunities, inputs)
        self.assertEqual(list(dates), list(a.plan.EXPECTED_DATES))
        rows = [row for day in dates.values() for row in day["opportunities"]]
        self.assertEqual([r["opportunity"] for r in rows], before["opportunities"])
        self.assertEqual(self.opportunities, before)
        self.assertEqual(summary["input_status_counts"], {"available": 108, "halted": 0, "unavailable": 1})
        self.assertEqual([date for date, value in dates.items() if not value["opportunities"]],
                         ["2025-06-03", "2025-06-05", "2025-06-16", "2025-06-17", "2025-06-20"])
        self.assertTrue(all(v["date_status"] == "not_applicable_no_micro_decisions"
                            for v in dates.values() if not v["opportunities"]))

    def test_missing_duplicate_and_reordered_request_population_rejected(self):
        values = synthetic_inputs(self.opportunities, self.requests)
        for changed in (values[:-1], values + values[:1], list(reversed(values))):
            with self.assertRaisesRegex(ValueError, "original request order"):
                a._build_dates(self.opportunities, changed)

    def test_duplicate_opportunities_and_changed_date_counts_rejected(self):
        values = synthetic_inputs(self.opportunities, self.requests)
        for case in ("duplicate", "count", "dates"):
            changed = copy.deepcopy(self.opportunities)
            if case == "duplicate": changed["opportunities"][-1] = changed["opportunities"][0]
            if case == "count": changed["dates"][0]["decision_count"] += 1
            if case == "dates": changed["dates"] = changed["dates"][1:]
            with self.subTest(case=case), self.assertRaises(ValueError):
                a._build_dates(changed, values)

    def test_additional_missing_request_cannot_replace_verified_complete_tape(self):
        values = synthetic_inputs(self.opportunities, self.requests)
        values[0] = source(values[0].request, None)
        with self.assertRaisesRegex(ValueError, "classifications changed"):
            a._build_dates(self.opportunities, values)

    def test_wrong_archive_rejected_before_capture_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wrong.zip"
            path.write_bytes(b"not the original ZIP")
            with patch.object(a.acquisition, "verify_capture", side_effect=AssertionError("must not reach verifier")):
                with self.assertRaisesRegex(ValueError, "ZIP size differs"):
                    a.verify_artifacts(ROOT, result_zip=path, consumption_zip=path, workspace=Path(tmp) / "work")

    def test_full_bundle_reconstruction_write_once_and_tamper_rejection(self):
        values = synthetic_inputs(self.opportunities, self.requests)
        # Only the immutable external archive boundary is replaced. Date/window
        # construction, parent registration, hashing, writing and verification
        # are the same functions used by the real offline command.
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(a, "verify_artifacts", return_value=(Path(tmp), Path(tmp), {"synthetic_only": True})), \
             patch.object(a, "load_request_inputs", return_value=values):
            out = Path(tmp) / "result"
            args = {"output": out, "result_zip": Path(tmp) / "result.zip", "consumption_zip": Path(tmp) / "consumption.zip"}
            report = a.write_bundle(ROOT, **args)
            self.assertEqual(report["file_count"], 31)
            self.assertEqual(a.verify_bundle(ROOT, **args), report)
            with self.assertRaises(FileExistsError): a.write_bundle(ROOT, **args)
            manifest = frozen(out / "manifest.json")
            self.assertEqual(manifest["profile_decision_counts"], self.opportunities["profile_decision_counts"])
            self.assertFalse(manifest["all_opportunity_inputs_available"])
            day_path = out / "dates/2025-05-30.json.gz"
            original = day_path.read_bytes()
            day = json.loads(gzip.decompress(original))
            day["opportunities"][0]["decision_reference"]["ask_size"] = 1
            day = seal({k: v for k, v in day.items() if k != "content_sha256"})
            day_path.write_bytes(a._gzip_bytes(day))
            with self.assertRaisesRegex(ValueError, "source reconstruction"):
                a.verify_bundle(ROOT, **args)
            day_path.write_bytes(original)
            (out / "extra.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "inventory differs"):
                a.verify_bundle(ROOT, **args)

    def test_symlink_and_repository_input_output_paths_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / "link"
            link.symlink_to(ROOT, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                a._safe_output(ROOT, link / "new")
        with self.assertRaisesRegex(ValueError, "frozen repository inputs"):
            a._safe_output(ROOT, ROOT / PLAN_PATH)

    def test_output_serialization_is_deterministic(self):
        payload = self.compose()
        raw = a._gzip_bytes(payload)
        self.assertEqual(a._gzip_bytes(payload), raw)
        self.assertEqual(json.loads(gzip.decompress(raw)), payload)
        self.assertEqual(raw[4:8], b"\0\0\0\0")


if __name__ == "__main__":
    unittest.main()
