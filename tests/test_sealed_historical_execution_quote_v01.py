from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from momentumbot.research import sealed_historical_execution_quote_v01 as quote
from momentumbot.research.sealed_historical_metadata_transport_v01 import MetadataOnlyHTTP, sdk_metadata

ROOT = Path(__file__).resolve().parents[1]
HAS_SDK = importlib.util.find_spec("databento") is not None
PROVENANCE = {"execution_commit_sha": "a" * 40, "workflow_run_id": "12345", "workflow_run_attempt": 1}


class Metadata:
    def __init__(self, fail=None, zero=False, cost=0.01):
        self.calls = []
        self.fail, self.zero, self.cost = fail, zero, cost

    def invoke(self, method, kwargs):
        self.calls.append((method, deepcopy(kwargs)))
        if self.fail == method:
            raise RuntimeError("synthetic-secret and raw provider body must be discarded")
        return (0 if self.zero else 100) if method == "get_billable_size" else self.cost

    def get_billable_size(self, **kwargs):
        return self.invoke("get_billable_size", kwargs)

    def get_cost(self, **kwargs):
        return self.invoke("get_cost", kwargs)


class Response:
    def __init__(self, value=100, status=200, large=False):
        self.status_code = status
        self.value, self.large = value, large

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_content(self, size):
        yield b"x" * 65537 if self.large else json.dumps(self.value).encode()


class Session:
    def __init__(self, status=200, large=False, error=False):
        self.calls = []
        self.status, self.large, self.error = status, large, error

    def post(self, url, **kwargs):
        self.calls.append((url, deepcopy(kwargs)))
        if self.error:
            raise RuntimeError("synthetic network secret")
        return Response(0.01 if url.endswith("get_cost") else 100, self.status, self.large)


class HistoricalExecutionQuoteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests = quote.validate_inputs(ROOT)

    def run_quote(self, metadata):
        calls = quote.collect_quote(self.requests, metadata)
        return quote.build_report(self.requests, calls, provenance=PROVENANCE,
                                  http_attempts=len(calls), blocked_attempts=0)

    def transport(self, session=None):
        session = session or Session()
        return MetadataOnlyHTTP(self.requests, session=session, key="synthetic-key", pause=lambda _: None), session

    def data(self, row=None):
        row = row or self.requests[0]
        data = quote.request_kwargs(row)
        data["symbols"] = data["symbols"][0]
        data["stype_out"] = "instrument_id"
        return data

    def test_exact_registration_requires_all_ninety_requests(self):
        self.assertEqual(len(self.requests), 90)
        self.assertEqual(quote.registered_contract()["maximum_http_attempts"], 180)
        self.assertFalse(quote.registered_contract()["timeseries_or_broker_access_authorized"])

    def test_complete_quote_visits_every_method_once_and_preserves_nanos(self):
        metadata = Metadata()
        report = self.run_quote(metadata)
        self.assertEqual(len(metadata.calls), 180)
        self.assertEqual(report["total_billable_size_bytes"], 9000)
        self.assertEqual(report["total_quoted_cost_usd"], "0.90")
        self.assertTrue(report["metadata_quote_gate_passed"])
        first = next(kwargs for method, kwargs in metadata.calls if kwargs["symbols"] == ["GITS"] and kwargs["schema"] == "mbp-1" and kwargs["start"].startswith("2025-05-30"))
        self.assertEqual(first["start"], "2025-05-30T12:57:03.047734566Z")
        self.assertEqual(first["end"], "2025-05-30T12:57:30.749660996Z")
        quote.validate_report(report, self.requests, PROVENANCE)

    def test_provider_errors_are_sanitized_no_retry_and_totals_unknown(self):
        metadata = Metadata(fail="get_cost")
        report = self.run_quote(metadata)
        self.assertEqual(len(metadata.calls), 180)
        self.assertEqual(len(report["quote_rows"]), 90)
        self.assertIsNone(report["total_quoted_cost_usd"])
        self.assertIsNone(report["total_billable_size_bytes"])
        self.assertFalse(report["metadata_quote_gate_passed"])
        self.assertNotIn("synthetic-secret", json.dumps(report))
        self.assertFalse(report["automatic_retry_attempted"])

    def test_zero_size_is_unavailable_and_does_not_change_the_plan(self):
        report = self.run_quote(Metadata(zero=True))
        self.assertEqual(report["complete_request_count"], 90)
        self.assertEqual(report["available_request_count"], 0)
        self.assertFalse(report["metadata_quote_gate_passed"])
        self.assertTrue(all(r["status"] == "zero_billable_size" for r in report["quote_rows"]))
        self.assertEqual([r["request_id"] for r in report["quote_rows"]], [r["request_id"] for r in self.requests])

    def test_invalid_numeric_results_fail_closed(self):
        for value in (True, -1, float("nan"), float("inf"), "raw-secret"):
            with self.subTest(value=value):
                report = self.run_quote(Metadata(cost=value))
                self.assertFalse(report["metadata_quote_gate_passed"])
                self.assertEqual({r["error"] for r in report["calls"] if r["status"] == "error"}, {"invalid_result"})

    def test_changed_request_is_rejected_before_client_call(self):
        requests = deepcopy(self.requests)
        requests[0]["end_ns"] += 1
        metadata = Metadata()
        with self.assertRaisesRegex(ValueError, "requests changed"):
            quote.collect_quote(requests, metadata)
        self.assertEqual(metadata.calls, [])

    def test_call_is_journaled_before_provider_and_failure_is_retained(self):
        metadata = Metadata()
        states = []
        quote.collect_quote(self.requests, metadata, progress=lambda payload: states.append((deepcopy(payload), len(metadata.calls))))
        self.assertEqual(states[0][0]["calls"][0]["status"], "pending")
        self.assertEqual(states[0][1], 0)
        self.assertEqual(states[-1][1], 180)
        self.assertTrue(states[-1][0]["complete"])

    def test_rehashed_report_identity_or_gate_tampering_is_rejected(self):
        source = self.run_quote(Metadata())
        for mutate in (
            lambda x: x.update(total_quoted_cost_usd="0"),
            lambda x: x["calls"][0].update(request_id="other"),
            lambda x: x.update(http_attempts=179),
            lambda x: x.update(download_authorized_by_this_artifact=True),
            lambda x: x.update(backtesting_executed=True),
        ):
            changed = deepcopy(source)
            mutate(changed)
            changed = quote.seal({k:v for k,v in changed.items() if k != "content_sha256"})
            with self.assertRaises(ValueError):
                quote.validate_report(changed, self.requests, PROVENANCE)

    def test_preflight_failure_is_explicit_and_zero_call(self):
        report = quote.build_report(self.requests, [], provenance=PROVENANCE,
                                    http_attempts=0, blocked_attempts=0, preflight_error="credential_missing")
        quote.validate_report(report, self.requests, PROVENANCE)
        self.assertFalse(report["metadata_quote_gate_passed"])
        self.assertEqual(report["metadata_call_count"], 0)
        self.assertEqual(len(report["quote_rows"]), 90)

    def test_execution_is_parent_bound_and_rejects_reruns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflow = root / quote.WORKFLOW_PATH
            workflow.parent.mkdir(parents=True)
            workflow.write_bytes((ROOT / quote.WORKFLOW_PATH).read_bytes())
            execution = quote.execution_payload(code_commit="a"*40, code_tree="b"*40,
                workflow_sha256=quote.file_sha(workflow), ci_run_id="12345", validation_run_id="12346")
            quote.write_json(root / quote.EXECUTION_PATH, execution)
            env = {"EXECUTION_CODE_COMMIT_SHA":"a"*40, "EXECUTION_CODE_TREE_SHA":"b"*40,
                   "GITHUB_REPOSITORY":"RoomyRems/momentumbot", "GITHUB_EVENT_NAME":"push",
                   "GITHUB_REF":"refs/heads/phase-3-historical-snapshot", "GITHUB_RUN_ATTEMPT":"1",
                   "GITHUB_SHA":"c"*40, "GITHUB_RUN_ID":"12347"}
            self.assertEqual(quote.validate_execution(root, env), execution)
            with self.assertRaises(ValueError):
                quote.validate_execution(root, {**env, "GITHUB_RUN_ATTEMPT":"2"})
            workflow.write_text("modified")
            with self.assertRaises(ValueError):
                quote.validate_execution(root, env)

    def test_transport_rejects_other_endpoints_or_changed_symbols_before_network(self):
        for url, data in (
            ("https://hist.databento.com/v0/timeseries.get_range", self.data()),
            ("https://example.com/v0/metadata.get_billable_size", self.data()),
            ("https://hist.databento.com/v0/metadata.get_billable_size", {**self.data(), "symbols":"OTHER"}),
        ):
            transport, session = self.transport()
            with self.assertRaises(quote.MetadataFailure):
                transport.post(url, data, basic_auth=True)
            self.assertEqual(session.calls, [])
            self.assertEqual(transport.blocked, 1)

    def test_transport_redirect_http_and_oversized_response_fail_without_retry(self):
        for session in (Session(status=302), Session(status=403), Session(large=True), Session(error=True)):
            transport, _ = self.transport(session)
            with self.assertRaises(quote.MetadataFailure):
                transport.post("https://hist.databento.com/v0/metadata.get_billable_size", self.data(), basic_auth=True)
            self.assertEqual(len(session.calls), 1)
            self.assertFalse(session.calls[0][1]["allow_redirects"])
            self.assertEqual(transport.ledger()["http_attempts"], 1)
            self.assertEqual(transport.attempts[0]["status"], "error")
            self.assertNotIn("synthetic", json.dumps(transport.ledger()))

    @unittest.skipUnless(HAS_SDK, "pinned SDK exercised by dedicated quote validation")
    def test_real_pinned_sdk_serializes_all_180_exact_http_requests(self):
        import databento
        self.assertEqual(databento.__version__, quote.SDK_VERSION)
        transport, session = self.transport()
        calls = quote.collect_quote(self.requests, sdk_metadata(transport))
        report = quote.build_report(self.requests, calls, provenance=PROVENANCE,
                                    http_attempts=len(transport.attempts), blocked_attempts=transport.blocked)
        self.assertTrue(report["metadata_quote_gate_passed"])
        self.assertEqual(len(session.calls), 180)
        with self.assertRaises(quote.MetadataFailure):
            sdk_metadata(transport).get_billable_size(**quote.request_kwargs(self.requests[0]))
        self.assertEqual(len(session.calls), 180)

    @unittest.skipUnless(HAS_SDK, "pinned SDK exercised by dedicated quote validation")
    def test_other_sdk_metadata_method_has_no_network_authority(self):
        transport, session = self.transport()
        with self.assertRaises(quote.MetadataFailure):
            sdk_metadata(transport).list_datasets()
        self.assertEqual(session.calls, [])

    def test_workflow_consumes_and_uploads_before_the_only_secret_step(self):
        workflow = yaml.load((ROOT / quote.WORKFLOW_PATH).read_text(), Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow["on"]), {"push"})
        job = workflow["jobs"]["quote"]
        self.assertEqual(job["if"], "needs.validate.outputs.execute == 'true'")
        steps = job["steps"]
        secret = [i for i,s in enumerate(steps) if "DATABENTO_API_KEY" in s.get("env", {})]
        self.assertEqual(len(secret), 1)
        upload = next(i for i,s in enumerate(steps) if s.get("name") == "Durably upload consumption before metadata access")
        self.assertLess(upload, secret[0])
        self.assertEqual(steps[-1]["if"], "always()")


if __name__ == "__main__":
    unittest.main()
