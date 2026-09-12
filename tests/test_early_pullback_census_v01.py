from copy import deepcopy
from contextlib import nullcontext
import http.client
import json
from pathlib import Path
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.parse import quote, urlencode
import zipfile

from momentumbot.research import early_pullback_census_v01 as m
from momentumbot.research.early_pullback_census_http_v01 import DirectHTTPS

ROOT = Path(__file__).resolve().parents[1]
SECRET = "synthetic-key-only"
STAMP = "2026-09-12T00:00:00+00:00"


def row(ticker="SYNTH", **extra):
    return dict(ticker=ticker, active=True, market="stocks", locale="us", **extra)


def body(rows, cursor=None):
    return m.render({"status": "OK", "count": len(rows), "results": rows,
                     "next_url": None if cursor is None else m.parent.CENSUS_ROUTE + "?" + urlencode({"cursor": cursor})})


def synthetic_reply(request, credential):
    rows = ([{"code": "CS", "asset_class": "stocks", "locale": "us", "description": "Synthetic fixture"}]
            if request["kind"] == "current_type_dictionary" else [row(type="CS")])
    return {"status": 200, "body": body(rows), "complete": True, "encoding": "identity"}


class Clock:
    def __init__(self):
        self.now, self.sleeps = 0, []

    def read(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += round(seconds * 1_000_000_000)


def session(output, transport=synthetic_reply, contract=None, credential=SECRET):
    clock = Clock()
    result = m.CaptureSession(contract or m.seal({"contract_id": m.ID, "limits": m.limits()}),
        output=output, transport=transport, credential=credential, clock_ns=clock.read,
        sleeper=clock.sleep, utc_now=lambda: STAMP)
    return result, clock


def archive_files(path, files):
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(files.items()):
            archive.writestr(name, raw)
    return dict(expected_bytes=path.stat().st_size, expected_sha256=m.sha(path.read_bytes()),
                expected_inventory_sha256=m.sha(files["inventory.json"]))


def repin(files):
    files["inventory.json"] = m.render(m.seal({"contract_id": m.ID, "files": {
        name: {"bytes": len(raw), "sha256": m.sha(raw)} for name, raw in files.items() if name != "inventory.json"}}))


class CensusTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def capture(self, transport=synthetic_reply, **kwargs):
        instance, clock = session(self.base / "capture", transport, **kwargs)
        result = instance.run()
        return instance, clock, result

    def complete_files(self):
        instance, _, _ = self.capture()
        return instance, {p.name: p.read_bytes() for p in instance.store.path.iterdir()}

    def test_frozen_parent_and_registration(self):
        contract = m.validate_registration(ROOT)
        self.assertEqual(contract["parent_registration_sha256"], m.PARENT_SHA)
        self.assertEqual(contract["selected_dates"], list(m.DATES))
        self.assertEqual(contract["limits"]["maximum_http_attempts"], 601)

    def test_complete_31_request_capture_and_independent_byte_replay(self):
        instance, clock, result = self.capture()
        self.assertTrue(result["protocol_complete"])
        self.assertEqual(result["attempt_count"], 31)
        self.assertEqual(clock.sleeps, [12.5] * 30)
        files = {p.name: p.read_bytes() for p in instance.store.path.iterdir()}
        archive = self.base / "capture.zip"
        verified = m.verify_archive(archive, contract=instance.contract, **archive_files(archive, files))
        self.assertEqual(verified["verified_member_count"], 127)
        self.assertEqual(len(verified["dates"]), 30)
        for key, value in m.BOUNDARY.items():
            self.assertEqual(verified[key], value)

    def test_intent_persisted_before_transport_and_no_credential_files(self):
        observed = []
        def transport(request, credential):
            prefix = f"{len(observed):04d}"
            self.assertTrue((self.base / "capture" / (prefix + ".intent.json")).is_file())
            self.assertFalse((self.base / "capture" / (prefix + ".receipt.json")).exists())
            observed.append(request)
            return synthetic_reply(request, credential)
        instance, _, _ = self.capture(transport)
        self.assertEqual(len(observed), 31)
        self.assertFalse(any(SECRET.encode() in p.read_bytes() for p in instance.store.path.iterdir()))

    def test_two_pages_all_dates_are_exhausted(self):
        def transport(request, credential):
            reply = synthetic_reply(request, credential)
            if request["kind"] != "current_type_dictionary":
                reply["body"] = body([row("AAA" if request["page"] == 1 else "ZZZ")],
                                     "next" if request["page"] == 1 else None)
            return reply
        _, _, result = self.capture(transport)
        self.assertTrue(result["protocol_complete"])
        self.assertEqual(result["attempt_count"], 61)
        self.assertTrue(all(d["accepted_rows"] == 2 and d["accepted_pages"] == 2 for d in result["dates"]))

    def test_twentieth_terminal_page_and_601_attempt_ceiling(self):
        def transport(request, credential):
            reply = synthetic_reply(request, credential)
            if request["kind"] != "current_type_dictionary":
                number = request["page"]
                reply["body"] = body([row(f"SYN{number:02d}")], str(number) if number < 20 else None)
            return reply
        _, _, result = self.capture(transport)
        self.assertTrue(result["protocol_complete"])
        self.assertEqual(result["attempt_count"], 601)

    def test_required_page_21_fails_without_next_request(self):
        def transport(request, credential):
            reply = synthetic_reply(request, credential)
            if request["kind"] != "current_type_dictionary":
                number = request["page"]
                reply["body"] = body([row(f"SYN{number:02d}")], str(number))
            return reply
        _, _, result = self.capture(transport)
        self.assertEqual(result["attempt_count"], 21)
        self.assertEqual(result["failure"]["reason"], "invalid_census_chain")
        self.assertEqual(result["dates"][0]["accepted_pages"], 19)
        self.assertEqual(result["dates"][1]["state"], "not_started")

    def test_ticker_collisions_missing_identity_and_unknown_types_retained(self):
        state = m.CensusState()
        request = state.next_request()
        raw = synthetic_reply(request, SECRET)["body"]
        state.accept(request, m.sha(raw), m.project_body(request, raw))
        request = state.next_request()
        raw = body([row("SYNTH", composite_figi="ONE", type="OLD"), row("SYNTH", composite_figi="TWO")])
        state.accept(request, m.sha(raw), m.project_body(request, raw))
        result = state.summary()[0]
        self.assertEqual(result["accepted_rows"], 2)
        self.assertEqual(result["ticker_collision_groups"], 1)
        self.assertEqual(result["missing_metadata_counts"]["cik"], 2)
        self.assertEqual(result["unknown_current_type_codes"], ["", "OLD"])

    def test_duplicate_membership_within_or_across_pages_rejected(self):
        for across in (False, True):
            state = m.CensusState()
            request = state.next_request()
            raw = synthetic_reply(request, SECRET)["body"]
            state.accept(request, m.sha(raw), m.project_body(request, raw))
            if across:
                request = state.next_request()
                raw = body([row()], "next")
                state.accept(request, m.sha(raw), m.project_body(request, raw))
            request = state.next_request()
            raw = body([row()] if across else [row(), row()])
            before = deepcopy(state.summary())
            with self.assertRaisesRegex(ValueError, "duplicate"):
                state.accept(request, m.sha(raw), m.project_body(request, raw))
            self.assertEqual(state.summary(), before)

    def test_page_and_cross_page_order_regression_rejected(self):
        request = m.parent.census_request(m.DATES[0])
        with self.assertRaises(ValueError):
            m.project_body(request, body([row("ZZZ"), row("AAA")]))
        state = m.CensusState()
        for raw in (synthetic_reply(state.next_request(), SECRET)["body"], body([row("ZZZ")], "next")):
            request = state.next_request()
            state.accept(request, m.sha(raw), m.project_body(request, raw))
        request = state.next_request()
        raw = body([row("AAA")])
        with self.assertRaisesRegex(ValueError, "ordering"):
            state.accept(request, m.sha(raw), m.project_body(request, raw))

    def test_empty_complete_census_is_failure_not_zero_opportunities(self):
        def transport(request, credential):
            reply = synthetic_reply(request, credential)
            if request["kind"] != "current_type_dictionary":
                reply["body"] = body([])
            return reply
        _, _, result = self.capture(transport)
        self.assertFalse(result["protocol_complete"])
        self.assertEqual(result["attempt_count"], 2)
        self.assertEqual(result["failure"]["reason"], "invalid_census_chain")

    def test_empty_intermediate_or_terminal_after_members_can_complete(self):
        def transport(request, credential):
            reply = synthetic_reply(request, credential)
            if request["kind"] != "current_type_dictionary":
                number = request["page"]
                reply["body"] = body([row()] if number == 2 else [], str(number) if number < 3 else None)
            return reply
        _, _, result = self.capture(transport)
        self.assertTrue(result["protocol_complete"])
        self.assertEqual(result["attempt_count"], 91)

    def test_request_mutations_fail_before_transport(self):
        for key, value in (("params", None), ("url", "https://evil.invalid/"), ("page", True), ("trading_date", "2026-03-07")):
            request = dict(m.parent.census_request(m.DATES[0]))
            request[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.validate_request(request)

    def test_schema_rejects_labels_coercion_nonfinite_and_duplicate_json(self):
        request = m.parent.census_request(m.DATES[0])
        invalid = [body([row(active_marker="outcome")]), body([row(ticker_value=3)]),
                   b'{"status":"OK","status":"OK","results":[]}',
                   b'{"status":"OK","count":NaN,"results":[]}',
                   m.render({"status": "OK", "count": True, "results": [row()]}),
                   m.render({"status": "OK", "results": [dict(row(), active="true")]}),
                   body([dict(row(), cik=123)]), body([row(name="bad\ntext")]),
                   body([row()] * 1001), b'[]']
        for raw in invalid:
            with self.subTest(raw=raw[:120]), self.assertRaises((ValueError, TypeError)):
                m.project_body(request, raw)

    def test_current_type_dictionary_rejects_empty_duplicate_or_paginated(self):
        types = [{"code": "CS", "asset_class": "stocks", "locale": "us"}]
        for raw in (body([]), body(types * 2), body(types, "next")):
            with self.assertRaises((ValueError, RuntimeError)):
                m.project_body(m.type_request(), raw)

    def test_bad_http_encoding_incomplete_and_oversize_stop_without_retry(self):
        cases = [("http_error", {"status": 302}), ("http_error", {"status": 429}),
                 ("incomplete_body", {"complete": False}), ("content_encoding", {"encoding": "gzip"}),
                 ("response_too_large", {"body": b"x" * (m.MAX_BODY + 1)}),
                 ("invalid_payload", {"body": b"not JSON"}), ("transport_error", {"status": True})]
        for number, (reason, change) in enumerate(cases):
            calls = []
            def transport(request, credential):
                calls.append(request)
                return dict(synthetic_reply(request, credential), **change)
            instance, _ = session(self.base / str(number), transport)
            result = instance.run()
            self.assertEqual(result["failure"]["reason"], reason)
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(result["dates"]), 30)
            self.assertFalse(list(instance.store.path.glob("*.body.json")))

    def test_transport_exception_sanitized_and_not_retried(self):
        def transport(request, credential):
            raise OSError("secret=" + credential)
        instance, _, result = self.capture(transport)
        self.assertEqual(result["attempt_count"], 1)
        self.assertEqual(result["failure"]["reason"], "transport_error")
        self.assertFalse(any(SECRET.encode() in p.read_bytes() for p in instance.store.path.iterdir()))

    def test_literal_encoded_and_json_escaped_credential_echo_never_retained(self):
        secret = 'synthetic+key/"only'
        for number, echo in enumerate((secret, quote(secret, safe=""), json.dumps(secret)[1:-1])):
            def transport(request, credential):
                return dict(synthetic_reply(request, credential), body=echo.encode())
            instance, _ = session(self.base / str(number), transport, credential=secret)
            result = instance.run()
            self.assertEqual(result["failure"]["reason"], "credential_echo")
            self.assertFalse(list(instance.store.path.glob("*.body.json")))
            self.assertFalse(any(echo.encode() in p.read_bytes() for p in instance.store.path.iterdir()))

    def test_interruption_preserves_pending_intent_and_failure_inventory(self):
        def transport(request, credential):
            raise KeyboardInterrupt()
        instance, _ = session(self.base / "capture", transport)
        with self.assertRaises(KeyboardInterrupt):
            instance.run()
        self.assertTrue((instance.store.path / "0000.intent.json").exists())
        self.assertFalse((instance.store.path / "0000.receipt.json").exists())
        result = json.loads((instance.store.path / "report.json").read_bytes())
        self.assertEqual(result["failure"]["reason"], "interrupted")
        self.assertFalse(result["protocol_complete"])
        self.assertTrue((instance.store.path / "inventory.json").exists())

    def test_unicode_escaped_credential_in_unprojected_metadata_not_retained(self):
        def transport(request, credential):
            raw = synthetic_reply(request, credential)["body"]
            value = json.loads(raw)
            value["request_id"] = "ESCAPED_PLACEHOLDER"
            escaped = "".join("\\u%04x" % ord(c) for c in credential)
            raw = m.render(value).replace(b"ESCAPED_PLACEHOLDER", escaped.encode())
            return dict(synthetic_reply(request, credential), body=raw)
        instance, _, result = self.capture(transport)
        self.assertEqual(result["failure"]["reason"], "credential_echo")
        self.assertFalse(list(instance.store.path.glob("*.body.json")))

    def test_no_restart_output_reuse_or_implicit_transport(self):
        instance, _, _ = self.capture()
        with self.assertRaises(ValueError):
            instance.run()
        with self.assertRaises(FileExistsError):
            session(instance.store.path)
        with self.assertRaises(ValueError):
            session(self.base / "other", None)

    def test_no_early_request_when_sleeper_fails_to_advance_clock(self):
        instance, _ = session(self.base / "capture")
        instance.sleeper = lambda seconds: None
        with self.assertRaisesRegex(ValueError, "pacing"):
            instance.run()
        self.assertEqual(instance.attempts, 1)

    def test_payload_limit_stops_and_retains_failure_metadata(self):
        instance, _ = session(self.base / "capture")
        instance.store.payload_bytes = m.MAX_PAYLOAD
        result = instance.run()
        self.assertEqual(result["failure"]["reason"], "retention_limit")
        self.assertFalse(list(instance.store.path.glob("*.body.json")))
        self.assertTrue((instance.store.path / "inventory.json").is_file())

    def test_output_symlink_and_metadata_overflow_rejected(self):
        (self.base / "link").symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(ValueError):
            session(self.base / "link" / "capture")
        store = m.RetainedFiles(self.base / "capture")
        store.metadata_bytes = m.METADATA_RESERVE
        with self.assertRaises(ValueError):
            store.write("x.json", b"x")

    def test_archive_outer_and_inventory_pins_are_required(self):
        instance, files = self.complete_files()
        path = self.base / "capture.zip"
        pins = archive_files(path, files)
        for key, value in (("expected_bytes", pins["expected_bytes"] + 1), ("expected_sha256", "0" * 64), ("expected_inventory_sha256", "0" * 64)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.verify_archive(path, contract=instance.contract, **dict(pins, **{key: value}))

    def test_archive_inner_hash_detects_changed_raw_bytes(self):
        instance, files = self.complete_files()
        files["0001.body.json"] += b" "
        path = self.base / "tampered.zip"
        with self.assertRaisesRegex(ValueError, "commitment"):
            m.verify_archive(path, contract=instance.contract, **archive_files(path, files))

    def test_resealed_normalization_report_and_pacing_forgery_rejected(self):
        instance, original = self.complete_files()
        for number, name in enumerate(("0001.normalized.json", "report.json", "0001.intent.json")):
            files = dict(original)
            value = json.loads(files[name])
            if "normalized" in name:
                value["rows"][0]["ticker"] = "OTHER"
            else:
                value.pop("content_sha256")
                value["provider_origin_authenticated" if name == "report.json" else "started_monotonic_ns"] = True if name == "report.json" else 0
                value = m.seal(value)
            files[name] = m.render(value)
            repin(files)
            path = self.base / f"tampered-{number}.zip"
            with self.assertRaises(ValueError):
                m.verify_archive(path, contract=instance.contract, **archive_files(path, files))

    def test_archive_missing_extra_and_partial_evidence_cannot_pass(self):
        instance, original = self.complete_files()
        for number, change in enumerate(("missing", "extra", "partial")):
            files = dict(original)
            if change == "extra":
                files["0601.body.json"] = b"{}"
            else:
                files.pop("0001.body.json" if change == "missing" else "0030.receipt.json")
            repin(files)
            path = self.base / f"bad-{number}.zip"
            with self.assertRaises(ValueError):
                m.verify_archive(path, contract=instance.contract, **archive_files(path, files))

    def test_archive_unsafe_duplicate_and_special_members_rejected(self):
        instance, files = self.complete_files()
        for number, name in enumerate(("../escape", "0000.body.json", "link.json")):
            path = self.base / f"unsafe-{number}.zip"
            with zipfile.ZipFile(path, "x") as archive:
                for original, raw in files.items():
                    archive.writestr(original, raw)
                info = zipfile.ZipInfo(name)
                if number == 2:
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                with self.assertWarns(UserWarning) if number == 1 else nullcontext():
                    archive.writestr(info, b"bad")
            with self.assertRaises(ValueError):
                m.verify_archive(path, expected_bytes=path.stat().st_size, expected_sha256=m.sha(path.read_bytes()),
                                 expected_inventory_sha256=m.sha(files["inventory.json"]), contract=instance.contract)

    def test_independently_pinned_contract_must_match(self):
        instance, files = self.complete_files()
        path = self.base / "capture.zip"
        with self.assertRaisesRegex(ValueError, "contract"):
            m.verify_archive(path, contract=dict(instance.contract, altered=True), **archive_files(path, files))

    def test_cli_offline_validation_and_no_capture_mode(self):
        result = subprocess.run([sys.executable, "scripts/validate_early_pullback_census_v01.py"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["provider_calls_authorized_now"], 0)
        invalid = subprocess.run([sys.executable, "scripts/validate_early_pullback_census_v01.py", "--capture"], cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(invalid.returncode, 0)


class HTTPTests(unittest.TestCase):
    def invoke(self, *, status=200, raw=b"{}", headers=None, error=None):
        calls = []
        class Response:
            def __init__(self):
                self.status, self.position = status, 0
            def getheader(self, name, default=None):
                return (headers or {}).get(name, default)
            def read1(self, count):
                if error:
                    raise error
                output = raw[self.position:self.position + count]
                self.position += len(output)
                return output
        class Connection:
            def __init__(self, host, timeout):
                calls.append((host, timeout))
            def request(self, method, path, headers):
                calls.append((method, path, headers))
            def getresponse(self):
                return Response()
            def close(self):
                calls.append("closed")
        reply = DirectHTTPS(connection_factory=Connection, clock=lambda: 0)(m.type_request(), SECRET)
        return reply, calls

    def test_fixed_host_exact_get_identity_encoding_and_close(self):
        reply, calls = self.invoke()
        self.assertTrue(reply["complete"])
        self.assertEqual(calls[0], ("api.massive.com", 30))
        self.assertEqual(calls[1][0], "GET")
        self.assertEqual(calls[1][2]["Accept-Encoding"], "identity")
        self.assertEqual(calls[-1], "closed")
        self.assertIn("apiKey=" + SECRET, calls[1][1])

    def test_redirect_is_returned_without_following(self):
        reply, calls = self.invoke(status=302, headers={"Location": "https://evil.invalid"})
        self.assertEqual(reply["status"], 302)
        self.assertEqual(len(calls), 3)

    def test_content_length_mismatch_marks_incomplete(self):
        reply, _ = self.invoke(headers={"Content-Length": "3"})
        self.assertFalse(reply["complete"])

    def test_read_error_preserves_partial_failure_and_closes(self):
        for error in (TimeoutError(), http.client.IncompleteRead(b"partial"), OSError()):
            reply, calls = self.invoke(error=error)
            self.assertFalse(reply["complete"])
            self.assertEqual(calls[-1], "closed")

    def test_transport_stops_at_oversize_sentinel(self):
        with patch.object(m, "MAX_BODY", 5):
            reply, _ = self.invoke(raw=b"0123456789")
        self.assertEqual(reply["body"], b"012345")
        self.assertFalse(reply["complete"])

    def test_invalid_request_never_constructs_connection(self):
        with self.assertRaises(ValueError):
            DirectHTTPS(connection_factory=lambda *args, **kwargs: self.fail("network started"))(
                dict(m.type_request(), url="https://evil.invalid"), SECRET)


if __name__ == "__main__":
    unittest.main()
