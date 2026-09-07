from __future__ import annotations

import copy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
import zipfile

import pandas as pd
import yaml

from momentumbot.research import sealed_historical_management_capture_v01 as m

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    import capture_sealed_historical_management_inputs_v01 as cli
finally:
    sys.path.pop(0)


def row(request, offset=0, identity=1):
    stamp = pd.Timestamp(request["start_ns"] + offset, unit="ns", tz="UTC").isoformat()
    if request["kind"] == "sip_trades":
        return {"t": stamp, "p": 4.0, "s": 25, "i": identity, "x": "Q", "z": "C", "c": ["@"]}
    return {"t": stamp, "o": 4.0, "h": 4.0, "l": 4.0, "c": 4.0, "v": 25, "n": 1, "vw": 4.0}


def payload(request, rows=None, token=None):
    key = "trades" if request["kind"] == "sip_trades" else "bars"
    return {key: {request["symbol"]: [row(request)] if rows is None else rows}, "next_page_token": token}


class Response(io.BytesIO):
    status = 200


class ManagementCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests = m.frozen(ROOT / m.reuse.MISSING_PATH)["requests"]
        cls.bar, cls.trade = cls.requests[:2]

    def test_registration_exactly_binds_verified_parent_and_closed_execution_gates(self):
        contract = m.validate_contract(ROOT)
        self.assertEqual(contract["parent_commit_sha"], "813960e42a96edd40983bc3e414743c0bf67452d")
        self.assertEqual(contract["requests"], self.requests)
        self.assertEqual(contract["logical_request_count"], 10)
        self.assertFalse(contract["provider_access_authorized_by_this_registration"])
        for key, value in m.BOUNDARY.items():
            self.assertEqual(contract[key], value)

    def test_verified_reuse_receipt_honestly_attests_prior_source_verification(self):
        receipt = m.verify_reuse_result(ROOT)
        self.assertTrue(receipt["verified_reuse_result"])
        self.assertFalse(receipt["original_source_archives_reopened_in_this_preflight"])
        self.assertEqual(len(receipt["reuse_result_file_inventory"]), 5)
        self.assertEqual(receipt["reuse_manifest_content_sha256"], "b8364219670b5f618334e18a8c9f8f9759e96d8ee64f608fc1ddd1ed076b57de")

    def test_parent_byte_tampering_cannot_be_resealed(self):
        original = m.file_sha
        with patch.object(m, "file_sha", side_effect=lambda p: "0" * 64 if str(p).endswith(m.REUSE_AUDIT) else original(p)):
            with self.assertRaisesRegex(ValueError, "parent differs"):
                m.verify_reuse_result(ROOT)

    def test_all_ten_urls_match_previously_frozen_nanosecond_renderer(self):
        for request in self.requests:
            with self.subTest(request=request["request_id"]):
                self.assertEqual(m.request_url(request, "a&b=1", requests=self.requests),
                    m.reuse.missing_request_url(ROOT, request["request_id"], "a&b=1"))
                parsed = urlsplit(m.request_url(request, None, requests=self.requests))
                query = parse_qs(parsed.query)
                self.assertEqual((parsed.scheme, parsed.netloc), ("https", "data.alpaca.markets"))
                self.assertEqual(pd.Timestamp(query["end"][0]).value, request["end_ns"] - 1)
                self.assertEqual(query["asof"], [request["trading_date"]])

    def test_url_rejects_modified_or_unregistered_request_and_invalid_token(self):
        for key, value in (("request_id", "x"), ("symbol", "AAPL"), ("start_ns", 1),
                           ("end_exclusive", 1), ("feed", "iex"), ("adjustment", "split")):
            with self.subTest(key=key), self.assertRaises((ValueError, m.CaptureError)):
                m.request_url({**self.trade, key: value}, None, requests=self.requests)
        for token in (False, 1, "", "x" * 16_385):
            with self.subTest(token_type=type(token)), self.assertRaises(m.CaptureError):
                m.request_url(self.trade, token, requests=self.requests)

    def transport(self, output):
        return m.BoundedHTTP(output, requests=self.requests, key="synthetic-key", secret="synthetic-secret")

    def test_missing_credentials_fail_before_any_transport(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(m.urllib.request, "build_opener") as opener:
            with self.assertRaises(m.CaptureError):
                m.BoundedHTTP(Path(directory), requests=self.requests, key="", secret="")
            opener.assert_not_called()

    def test_attempt_is_durably_recorded_before_get_and_contains_no_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            http = self.transport(output)
            def open_page(request, timeout):
                ledger = json.loads((output / "request-ledger.json").read_text())
                self.assertEqual(ledger["total_attempts"], 1)
                self.assertEqual(ledger["attempt_events"], [{"attempt": 1, "request_id": self.trade["request_id"]}])
                self.assertEqual(request.get_method(), "GET")
                self.assertEqual(timeout, 30)
                self.assertNotIn("synthetic-secret", json.dumps(ledger))
                return Response(json.dumps(payload(self.trade)).encode())
            http.opener = Mock(open=open_page)
            self.assertEqual(http(self.trade, None), payload(self.trade))

    def test_all_http_errors_are_one_attempt_without_retry_or_provider_body(self):
        for status in (400, 401, 403, 429, 500, 502, 503, 504):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                http = self.transport(Path(directory))
                http.opener = Mock()
                http.opener.open.side_effect = HTTPError("https://data.alpaca.markets", status, "PRIVATE", {}, io.BytesIO(b"PRIVATE"))
                with self.assertRaises(m.CaptureError) as error:
                    http(self.trade, None)
                self.assertNotIn("PRIVATE", str(error.exception))
                self.assertEqual(http.attempts, 1)
                http.opener.open.assert_called_once()

    def test_transport_timeouts_and_url_errors_do_not_retry(self):
        for error in (TimeoutError("PRIVATE"), URLError("PRIVATE"), OSError("PRIVATE")):
            with self.subTest(kind=type(error)), tempfile.TemporaryDirectory() as directory:
                http = self.transport(Path(directory))
                http.opener = Mock()
                http.opener.open.side_effect = error
                with self.assertRaisesRegex(m.CaptureError, "no retry") as caught:
                    http(self.trade, None)
                self.assertNotIn("PRIVATE", str(caught.exception))
                http.opener.open.assert_called_once()

    def test_redirect_handler_never_returns_redirect_request(self):
        with self.assertRaisesRegex(m.CaptureError, "redirect"):
            m.source.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example")

    def test_attempt_ceiling_and_repeated_page_block_before_network(self):
        for ceiling in (True, False):
            with self.subTest(ceiling=ceiling), tempfile.TemporaryDirectory() as directory:
                http = self.transport(Path(directory))
                if ceiling:
                    http.attempts = m.MAX_ATTEMPTS
                else:
                    http.pages.add((self.trade["request_id"], None))
                http.opener = Mock()
                with self.assertRaises(m.CaptureError):
                    http(self.trade, None)
                http.opener.open.assert_not_called()
                self.assertEqual(http.blocked, 1)

    def test_retained_byte_ceiling_blocks_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "synthetic.gz").write_bytes(b"x")
            http = self.transport(output)
            http.opener = Mock()
            with patch.object(m, "MAX_RETAINED_BYTES", 1), self.assertRaises(m.CaptureError):
                http(self.trade, None)
            http.opener.open.assert_not_called()

    def test_changed_request_blocks_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            http = self.transport(Path(directory))
            http.opener = Mock()
            with self.assertRaises(m.CaptureError):
                http({**self.trade, "symbol": "OTHER"}, None)
            self.assertEqual(http.attempts, 0)
            http.opener.open.assert_not_called()

    def test_response_bytes_invalid_json_duplicate_keys_and_non_object_fail(self):
        for raw in (b"x" * 100, b"not-json", b'[]', b'{"trades":{},"trades":{}}'):
            with self.subTest(raw=raw[:20]), tempfile.TemporaryDirectory() as directory:
                http = self.transport(Path(directory))
                http.opener = Mock()
                http.opener.open.return_value = Response(raw)
                with patch.object(m, "MAX_RESPONSE_BYTES", 80), self.assertRaises(m.CaptureError):
                    http(self.trade, None)
                self.assertEqual(http.attempts, 1)

    def test_minimum_interval_applies_between_actual_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            http = self.transport(Path(directory))
            http.opener = Mock()
            http.opener.open.side_effect = [Response(json.dumps(payload(self.trade)).encode()) for _ in range(2)]
            with patch.object(m.time, "monotonic", side_effect=[10.0, 10.1, 10.35]), patch.object(m.time, "sleep") as sleep:
                http(self.trade, None)
                http(self.trade, "second")
            self.assertAlmostEqual(sleep.call_args.args[0], 0.25)

    def capture(self, request, responses):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name)
        fetch = Mock(side_effect=responses)
        receipt = m.capture_request(request, output, fetch, m.CompressedBudget())
        return output, receipt, fetch

    def test_empty_exhausted_segments_are_retained_for_both_resources(self):
        for request in (self.bar, self.trade):
            with self.subTest(kind=request["kind"]):
                output, receipt, _ = self.capture(request, [payload(request, [])])
                self.assertEqual(receipt["record_count"], 0)
                self.assertEqual(receipt["pages"], 1)
                self.assertTrue(receipt["complete"])
                self.assertTrue(receipt["empty_exhausted_segment"])
                self.assertEqual(gzip.decompress((output / receipt["path"]).read_bytes()), b"")
                self.assertEqual(receipt["logical_sha256"], hashlib.sha256(b"").hexdigest())

    def test_absent_symbol_and_null_rows_retain_empty_receipts(self):
        for values in ({}, {self.trade["symbol"]: None}):
            output, receipt, _ = self.capture(self.trade, [{"trades": values, "next_page_token": None}])
            self.assertEqual(receipt["record_count"], 0)
            self.assertTrue((output / receipt["path"]).is_file())

    def test_empty_page_with_token_is_exhausted_not_mistaken_for_completion(self):
        _, receipt, fetch = self.capture(self.trade,
            [payload(self.trade, [], "next"), payload(self.trade, [row(self.trade)])])
        self.assertEqual((receipt["record_count"], receipt["pages"]), (1, 2))
        self.assertEqual(fetch.call_args_list[1].args[1], "next")

    def test_exact_endpoint_and_same_timestamp_order_are_lossless(self):
        last = self.trade["end_ns"] - self.trade["start_ns"] - 1
        rows = [row(self.trade, identity=2), row(self.trade, identity=1), row(self.trade, last, 3)]
        output, receipt, _ = self.capture(self.trade, [payload(self.trade, rows[:1], "next"), payload(self.trade, rows[1:])])
        raw = gzip.decompress((output / receipt["path"]).read_bytes())
        self.assertEqual(raw, b"".join(m.reuse._canonical_line(r) for r in rows))
        self.assertEqual(receipt["record_count"], 3)

    def test_before_start_and_exact_exclusive_end_are_rejected(self):
        for offset in (-1, self.trade["end_ns"] - self.trade["start_ns"]):
            with self.subTest(offset=offset), self.assertRaises(m.CaptureError):
                self.capture(self.trade, [payload(self.trade, [row(self.trade, offset)])])

    def test_non_chronological_or_duplicate_rows_across_pages_fail(self):
        for rows in ([row(self.trade, 1), row(self.trade, 0)], [row(self.trade), row(self.trade)]):
            with self.subTest(rows=rows), self.assertRaises(m.CaptureError):
                self.capture(self.trade, [payload(self.trade, rows[:1], "next"), payload(self.trade, rows[1:])])

    def test_invalid_or_repeated_pagination_tokens_fail(self):
        for token in (True, 1, "", "x" * 16_385):
            with self.subTest(token_type=type(token)), self.assertRaises(m.CaptureError):
                self.capture(self.trade, [payload(self.trade, [], token)])
        with self.assertRaisesRegex(m.CaptureError, "repeated"):
            self.capture(self.trade, [payload(self.trade, [], "same"), payload(self.trade, [], "same")])

    def test_wrong_symbol_missing_fields_and_oversized_page_fail(self):
        values = [{"trades": {"OTHER": []}, "next_page_token": None}, {"trades": {}},
                  {"bars": {}, "next_page_token": None}, payload(self.trade, [row(self.trade)] * 10_001),
                  {"trades": [], "next_page_token": None}]
        for value in values:
            with self.subTest(keys=list(value)), self.assertRaises(m.CaptureError):
                self.capture(self.trade, [value])

    def test_unchanged_normalization_retains_conditions_but_rejects_invalid_fields(self):
        record = {**row(self.trade), "c": ["I", "@"]}
        encoded, _ = m.checked_record(record, self.trade, None, set())
        self.assertEqual(json.loads(encoded)["c"], ["I", "@"])
        for key, value in (("p", 0), ("s", True), ("i", -1), ("x", "TOO LONG"), ("z", "D"), ("c", ["LONG"])):
            with self.subTest(key=key), self.assertRaises(m.CaptureError):
                m.checked_record({**record, key: value}, self.trade, None, set())

    def test_minute_bars_must_be_unique_aligned_and_have_valid_ohlc(self):
        for record, previous in ((row(self.bar, 1), None), (row(self.bar), self.bar["start_ns"]),
                                 ({**row(self.bar), "h": 3}, None)):
            with self.subTest(record=record), self.assertRaises(m.CaptureError):
                m.checked_record(record, self.bar, previous, set())

    def test_compressed_byte_limit_is_checked_before_every_write(self):
        raw, budget = io.BytesIO(), m.CompressedBudget()
        writer = budget.writer(raw)
        with patch.object(m, "MAX_RETAINED_BYTES", 5):
            self.assertEqual(writer.write(b"12345"), 5)
            with self.assertRaises(m.CaptureError):
                writer.write(b"6")
        self.assertEqual(raw.getvalue(), b"12345")
        self.assertEqual(budget.written, 5)

    def test_gzip_failure_keeps_partial_evidence_inside_shared_ceiling(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(m, "MAX_RETAINED_BYTES", 15):
            output = Path(directory)
            budget = m.CompressedBudget()
            with self.assertRaises(m.CaptureError):
                m.capture_request(self.trade, output, lambda *args: payload(self.trade), budget)
            self.assertLessEqual((output / m.tape_path(self.trade)).stat().st_size, 15)
            self.assertLessEqual(budget.written, 15)

    def contract(self):
        return m.frozen(ROOT / m.CONTRACT_PATH)

    def test_complete_synthetic_capture_retains_all_ten_requests_and_no_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            report = m.acquire(self.requests, output, lambda r, token: payload(r, []), contract=self.contract(), provenance={})
            self.assertEqual(report["logical_requests_completed"], 10)
            self.assertEqual(len(list((output / "receipts").iterdir())), 10)
            self.assertEqual(sum(r["record_count"] for r in report["receipts"]), 0)
            self.assertEqual(report["normalized_compressed_bytes"], sum(p.stat().st_size for p in output.rglob("*.gz")))
            for key, value in m.BOUNDARY.items():
                self.assertEqual(report[key], value)

    def test_failure_retains_completed_receipt_and_partial_tape_sanitized(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            def fetch(request, token):
                if request == self.requests[1]:
                    raise RuntimeError("PRIVATE CREDENTIALS")
                return payload(request)
            with self.assertRaises(m.CaptureError):
                m.acquire(self.requests, output, fetch, contract=self.contract(), provenance={})
            failure = m.frozen(output / "capture-failure.json")
            self.assertEqual(len(failure["completed_receipts"]), 1)
            self.assertTrue((output / m.tape_path(self.requests[1])).is_file())
            self.assertFalse((output / "capture-report.json").exists())
            self.assertNotIn("PRIVATE", json.dumps(failure))

    def test_incomplete_reordered_or_changed_request_sets_fail_before_capture(self):
        for requests in (self.requests[:-1], self.requests[::-1], [{**self.requests[0], "end_ns": 1}] + self.requests[1:]):
            with tempfile.TemporaryDirectory() as directory:
                fetch = Mock()
                with self.assertRaises((ValueError, m.CaptureError)):
                    m.acquire(requests, Path(directory), fetch, contract=self.contract(), provenance={})
                fetch.assert_not_called()

    def test_existing_output_and_symlink_are_not_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            output = parent / "existing"
            output.mkdir()
            (output / "keep").write_bytes(b"keep")
            link = parent / "link"
            link.symlink_to(output, target_is_directory=True)
            for path in (output, link, link / "child"):
                with self.subTest(path=path), self.assertRaises(m.CaptureError):
                    m.acquire(self.requests, path, Mock(), contract=self.contract(), provenance={})
            self.assertEqual((output / "keep").read_bytes(), b"keep")

    def test_execution_full_hashes_are_required(self):
        for values in (("short", "b" * 40, "c" * 64), (True, "b" * 40, "c" * 64), ("a" * 40, "b" * 40, "bad")):
            with self.subTest(values=values), self.assertRaises(ValueError):
                m.execution_payload(self.contract(), code_commit=values[0], code_tree=values[1], workflow_sha256=values[2])

    def execution_context(self):
        contract = self.contract()
        execution = m.execution_payload(contract, code_commit="a" * 40, code_tree="b" * 40,
            workflow_sha256=m.file_sha(ROOT / m.WORKFLOW_PATH))
        env = {"EXECUTION_CODE_COMMIT_SHA": "a" * 40, "EXECUTION_CODE_TREE_SHA": "b" * 40,
            "GITHUB_REPOSITORY": "RoomyRems/momentumbot", "GITHUB_EVENT_NAME": "push",
            "GITHUB_REF": "refs/heads/phase-3-historical-snapshot", "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_RUN_ID": "123", "GITHUB_SHA": "c" * 40,
            "ALPACA_API_KEY": "synthetic-key", "ALPACA_API_SECRET": "synthetic-secret"}
        original = m.frozen
        def read(path):
            return copy.deepcopy(execution) if path == ROOT / m.EXECUTION_PATH else original(path)
        return contract, execution, env, read

    def test_execution_rerun_wrong_branch_event_and_parent_are_rejected(self):
        contract, execution, env, read = self.execution_context()
        with patch.object(m, "frozen", side_effect=read):
            self.assertEqual(m.validate_execution(ROOT, contract, env), execution)
            for key, value in (("GITHUB_RUN_ATTEMPT", "2"), ("GITHUB_EVENT_NAME", "workflow_dispatch"),
                               ("GITHUB_REF", "refs/heads/main"), ("EXECUTION_CODE_COMMIT_SHA", "d" * 40),
                               ("GITHUB_RUN_ID", ""), ("GITHUB_SHA", "bad")):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    m.validate_execution(ROOT, contract, {**env, key: value})

    def test_workflow_consumes_and_uploads_before_credentials_and_has_no_rerun_trigger(self):
        value = yaml.safe_load((ROOT / m.WORKFLOW_PATH).read_text())
        trigger = value.get("on", value.get(True))
        self.assertEqual(set(trigger), {"push"})
        self.assertEqual(trigger["push"]["paths"], [m.EXECUTION_PATH])
        self.assertFalse(value["concurrency"]["cancel-in-progress"])
        steps = value["jobs"]["capture"]["steps"]
        names = [s.get("name", "") for s in steps]
        consume = names.index("Atomically consume this acquisition once")
        upload = names.index("Durably upload consumption before market-data access")
        capture = names.index("Capture only the ten exact missing management resources")
        self.assertLess(consume, upload)
        self.assertLess(upload, capture)
        self.assertEqual([i for i, s in enumerate(steps) if "ALPACA_API_KEY" in s.get("env", {})], [capture])
        self.assertEqual(steps[-1]["if"], "always()")
        self.assertIn('--diff-filter=A', steps[1]["run"])

    def test_cli_rejects_wrong_consumption_or_source_receipt_before_provider_construction(self):
        _, execution, env, read = self.execution_context()
        source_receipt = m.verify_reuse_result(ROOT)
        for bad_marker in (True, False):
            with self.subTest(bad_marker=bad_marker), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                marker = m.consumption_payload(execution, commit=env["GITHUB_SHA"], run_id="124" if bad_marker else "123")
                receipt = source_receipt if bad_marker else m.seal({"verified_reuse_result": True})
                m.write_json(base / "marker.json", marker)
                m.write_json(base / "source.json", receipt)
                argv = [m.SCRIPT_PATH, "--acquire", "--output", str(base / "capture"),
                    "--consumption-marker", str(base / "marker.json"), "--source-receipt", str(base / "source.json")]
                with patch.object(m, "frozen", side_effect=read), patch.dict(os.environ, env), patch("sys.argv", argv), \
                        patch.object(m, "BoundedHTTP") as transport, self.assertRaises(ValueError):
                    cli.main()
                transport.assert_not_called()
                self.assertFalse((base / "capture").exists())

    def test_cli_http_failure_retains_full_metadata_ledger_inventory_and_partial_tape(self):
        _, execution, env, read = self.execution_context()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            m.write_json(base / "marker.json", m.consumption_payload(execution, commit=env["GITHUB_SHA"], run_id="123"))
            m.write_json(base / "source.json", m.verify_reuse_result(ROOT))
            output = base / "capture"
            argv = [m.SCRIPT_PATH, "--acquire", "--output", str(output),
                "--consumption-marker", str(base / "marker.json"), "--source-receipt", str(base / "source.json")]
            opener = Mock()
            opener.open.side_effect = URLError("PRIVATE")
            with patch.object(m, "frozen", side_effect=read), patch.dict(os.environ, env), patch("sys.argv", argv), \
                    patch.object(m.urllib.request, "build_opener", return_value=opener), self.assertRaises(m.CaptureError):
                cli.main()
            opener.open.assert_called_once()
            inventory = m.frozen(output / "capture-inventory.json")
            self.assertFalse(inventory["complete"])
            self.assertEqual(inventory["provider_attempts"], 1)
            self.assertIn("capture-failure.json", inventory["files"])
            self.assertIn(m.tape_path(self.bar), inventory["files"])
            self.assertNotIn("capture-report.json", inventory["files"])
            for name, expected in inventory["files"].items():
                self.assertEqual(m.file_sha(output / name), expected)
            self.assertNotIn("PRIVATE", (output / "capture-failure.json").read_text())

    def synthetic_archive(self, directory):
        contract, execution, env, read = self.execution_context()
        base = Path(directory)
        marker = m.consumption_payload(execution, commit=env["GITHUB_SHA"], run_id=env["GITHUB_RUN_ID"])
        source_receipt = m.verify_reuse_result(ROOT)
        m.write_json(base / "marker.json", marker)
        m.write_json(base / "source.json", source_receipt)
        output = base / "capture"
        responses = []
        for index, request in enumerate(self.requests):
            responses.append(Response(json.dumps(payload(request, [] if index == 1 else [row(request)])).encode()))
        opener = Mock()
        opener.open.side_effect = responses
        argv = [m.SCRIPT_PATH, "--acquire", "--output", str(output), "--consumption-marker", str(base / "marker.json"),
                "--source-receipt", str(base / "source.json")]
        with patch.object(m, "frozen", side_effect=read), patch.dict(os.environ, env), patch("sys.argv", argv), \
                patch.object(m.urllib.request, "build_opener", return_value=opener), patch.object(m.time, "sleep"), \
                patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(cli.main(), 0)
        self.assertEqual(opener.open.call_count, 10)
        archive_path = base / "capture.zip"
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(output.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(output).as_posix())
        return archive_path, read

    def test_full_cli_capture_to_archive_verification_including_empty_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, read = self.synthetic_archive(directory)
            with patch.object(m, "frozen", side_effect=read):
                report = m.verify_archive(ROOT, archive, execution_commit="c" * 40, run_id="123")
            self.assertTrue(report["verification_passed"])
            self.assertEqual((report["verified_file_count"], report["provider_attempts"], report["normalized_row_count"]), (28, 10, 9))
            self.assertEqual(report["empty_exhausted_segments"], 1)

    def test_archive_rejects_resealed_wrong_ledger_request_receipt_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, read = self.synthetic_archive(directory)
            with zipfile.ZipFile(archive) as bundle:
                original = {n: bundle.read(n) for n in bundle.namelist()}
            cases = [("request-ledger.json", "total_attempts", 11), ("capture-report.json", "logical_requests_completed", 9),
                     ("consumption.json", "workflow_run_id", "124"),
                     ("receipts/" + self.requests[1]["request_id"] + ".json", "record_count", 1)]
            for index, (name, key, value) in enumerate(cases):
                members = dict(original)
                document = json.loads(members[name])
                document[key] = value
                if "content_sha256" in document:
                    document = m.seal({k: v for k, v in document.items() if k != "content_sha256"})
                members[name] = m.reuse.accounts._bytes(document)
                inventory = json.loads(members["capture-inventory.json"])
                inventory["files"][name] = hashlib.sha256(members[name]).hexdigest()
                members["capture-inventory.json"] = m.reuse.accounts._bytes(m.seal({k: v for k, v in inventory.items() if k != "content_sha256"}))
                changed = Path(directory) / f"changed-{index}.zip"
                with zipfile.ZipFile(changed, "w") as bundle:
                    for member, raw in members.items():
                        bundle.writestr(member, raw)
                with self.subTest(name=name), patch.object(m, "frozen", side_effect=read), self.assertRaises(ValueError):
                    m.verify_archive(ROOT, changed, execution_commit="c" * 40, run_id="123")


if __name__ == "__main__":
    unittest.main()
