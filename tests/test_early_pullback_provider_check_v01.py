from copy import deepcopy
from datetime import datetime
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
import urllib.parse
import zipfile

import yaml

from momentumbot.research import early_pullback_provider_check_v01 as m
from momentumbot.research.early_pullback_provider_transport_v01 import BoundedProbe, NoRedirect

ROOT = Path(__file__).resolve().parents[1]
CODE, TREE, EXECUTION = "a" * 40, "b" * 40, "c" * 40
ENV = {"GITHUB_SHA": EXECUTION, "GITHUB_RUN_ID": "123456", "GITHUB_RUN_ATTEMPT": "1",
       "GITHUB_REPOSITORY": "RoomyRems/momentumbot", "GITHUB_EVENT_NAME": "push",
       "GITHUB_REF": "refs/heads/phase-3-historical-snapshot"}
CREDENTIALS = {k: "SYNTHETIC_SECRET_" + k for k in
               ("ALPACA_API_KEY", "ALPACA_API_SECRET", "MASSIVE_API_KEY", "DATABENTO_API_KEY")}


def payloads():
    daily = {"bars": {"SPY": [{"t": datetime.fromisoformat(d).replace(tzinfo=m.NY).isoformat(),
                              "c": 123.456, "v": 9000} for d in m.DATES]}, "next_page_token": None}
    sample = {"status": "OK", "count": 1, "next_url": "https://api.massive.com/unfollowed?apiKey=UNSAFE_VALUE",
              "results": [{"active": True, "market": "stocks", "locale": "us", "ticker": "UNRETAINED_SYMBOL",
                           "primary_exchange": "XNYS", "type": "CS", "name": "UNRETAINED_COMPANY"}]}
    span = {"start": "2018-05-01T00:00:00.000000000Z", "end": "2026-06-01T00:00:00.000000000Z"}
    ranges = {**span, "schema": {s: dict(span) for s in m.SCHEMAS}}
    return [daily, deepcopy(sample), deepcopy(sample), ranges]


class Response(io.BytesIO):
    def __init__(self, payload, *, status=200, encoding="identity"):
        super().__init__(payload if type(payload) is bytes else json.dumps(payload).encode())
        self.status, self.headers, self.url = status, {"Content-Encoding": encoding}, None
        self.read_sizes = []

    def geturl(self):
        return self.url

    def read(self, size=-1):
        self.read_sizes.append(size)
        return super().read(size)


class Opener:
    def __init__(self, responses, before=None):
        self.responses, self.calls, self.before = responses, [], before

    def open(self, request, timeout):
        i = len(self.calls)
        self.calls.append((request, timeout))
        if self.before:
            self.before(i)
        value = self.responses[i]
        if isinstance(value, BaseException):
            raise value
        value.url = request.full_url
        return value


class ProviderCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = m.validate_registration(ROOT)
        cls.execution = m.execution_payload(cls.contract, code_commit=CODE, code_tree=TREE, ci_run_id="987654")
        cls.marker = m.consumption(cls.execution, ENV)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name) / "result"

    def runner(self, responses=None, *, credentials=None, before=None):
        opener = Opener(responses or [Response(p) for p in payloads()], before=before)
        runner = BoundedProbe(self.contract, self.execution, self.marker, ENV, output=self.output,
                              credentials=credentials or CREDENTIALS, opener=opener)
        return runner, opener

    def documents(self):
        return {p.name: p.read_bytes() for p in self.output.iterdir()}

    def verify(self, documents):
        return m.verify_documents(documents, self.contract, execution_commit=EXECUTION, run_id=ENV["GITHUB_RUN_ID"],
                                   code_commit=CODE, code_tree=TREE, ci_run_id="987654")

    def facts(self):
        return {"head": EXECUTION, "parent_commit": CODE, "parent_tree": TREE, "parents": [CODE],
                "changed_files": ["A\t" + m.EXECUTION_PATH], "clean": True}

    def test_frozen_requests_and_parent_unchanged(self):
        prep = m.parent.provider_check_preparation(ROOT)
        self.assertEqual(self.contract["requests"], prep["requests"])
        self.assertEqual(self.contract["parent_registration_sha256"], m.PARENT_SHA)
        self.assertEqual(self.contract["authorized_calls_now"], 0)
        self.assertEqual(self.contract["selected_dates"], list(m.DATES))
        self.assertEqual(len(m.DATES), 30)

    def test_complete_probe_and_independent_artifact_check(self):
        runner, opener = self.runner()
        result = runner.run()
        checked = self.verify(self.documents())
        self.assertTrue(result["limited_availability_passed"])
        self.assertTrue(checked["verification_passed"])
        self.assertEqual(checked["file_count"], 14)
        self.assertEqual(len(opener.calls), 4)
        self.assertFalse(result["historical_replay_enabled"])
        self.assertFalse(result["full_session_calendar_authenticated"])

    def test_requests_match_exact_parameters_with_no_pagination(self):
        runner, opener = self.runner()
        runner.run()
        for i, (request, timeout) in enumerate(opener.calls):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
            expected = {k: [str(v)] for k, v in self.contract["requests"][i]["request"]["parameters"].items() if k != "method"}
            query.pop("apiKey", None)
            self.assertEqual(query, expected)
            self.assertEqual(request.method, "GET")
            self.assertEqual(timeout, 20)
        self.assertTrue(opener.calls[3][0].get_header("Authorization").startswith("Basic "))
        self.assertIsNotNone(opener.calls[0][0].get_header("Apca-api-key-id"))

    def test_intent_is_written_before_each_network_attempt(self):
        def before(i):
            item = m.frozen(self.output / f"intent-{i}.json")
            self.assertEqual(item["ordinal"], i)
            self.assertFalse((self.output / f"receipt-{i}.json").exists())
        runner, _ = self.runner(before=before)
        runner.run()

    def test_no_secret_price_ticker_company_or_next_url_retained(self):
        runner, _ = self.runner()
        runner.run()
        rendered = b"".join(self.documents().values()).decode()
        for forbidden in (*CREDENTIALS.values(), "UNRETAINED_SYMBOL", "UNRETAINED_COMPANY", "UNSAFE_VALUE", "123.456"):
            self.assertNotIn(forbidden, rendered)

    def test_response_digest_is_raw_bytes_not_projected_values(self):
        raw = json.dumps(payloads()[0], indent=7).encode()
        runner, _ = self.runner([Response(raw), *[Response(p) for p in payloads()[1:]]])
        runner.run()
        receipt = m.frozen(self.output / "receipt-0.json")
        self.assertEqual(receipt["body_sha256"], m.sha(raw))
        self.assertEqual(receipt["body_bytes_observed"], len(raw))

    def test_fresh_process_cannot_reuse_output(self):
        runner, _ = self.runner()
        runner.run()
        with self.assertRaises(FileExistsError):
            self.runner()

    def test_in_memory_retries_and_out_of_order_attempts_rejected(self):
        runner, opener = self.runner()
        with self.assertRaises(ValueError):
            runner.once(1)
        runner.once(0)
        with self.assertRaises(ValueError):
            runner.once(0)
        with self.assertRaises(ValueError):
            runner.run()
        self.assertEqual(len(opener.calls), 1)

    def test_run_cannot_repeat_after_completion(self):
        runner, opener = self.runner()
        runner.run()
        with self.assertRaises(ValueError):
            runner.run()
        with self.assertRaises(ValueError):
            runner.once(4)
        self.assertEqual(len(opener.calls), 4)

    def test_http_failure_preserved_and_other_requests_attempted_once(self):
        responses = [Response({"error": "secret message"}, status=403), *[Response(p) for p in payloads()[1:]]]
        runner, opener = self.runner(responses)
        result = runner.run()
        self.assertFalse(result["limited_availability_passed"])
        self.assertEqual(result["projections"][0], {"ok": False, "reason": "http_error"})
        self.assertEqual(len(opener.calls), 4)
        self.assertTrue(self.verify(self.documents())["verification_passed"])

    def test_transport_exception_text_never_retained(self):
        runner, opener = self.runner([urllib.error.URLError("PRIVATE_TOKEN_IN_MESSAGE"), *[Response(p) for p in payloads()[1:]]])
        result = runner.run()
        self.assertEqual(result["projections"][0]["reason"], "transport_error")
        self.assertNotIn(b"PRIVATE_TOKEN_IN_MESSAGE", b"".join(self.documents().values()))
        self.assertEqual(len(opener.calls), 4)

    def test_interruption_preserves_consumed_intent_without_invented_response(self):
        runner, opener = self.runner([KeyboardInterrupt(), *[Response(p) for p in payloads()[1:]]])
        with self.assertRaises(KeyboardInterrupt):
            runner.run()
        self.assertEqual(len(opener.calls), 1)
        self.assertTrue((self.output / "intent-0.json").is_file())
        self.assertFalse((self.output / "receipt-0.json").exists())
        self.assertFalse(m.frozen(self.output / "inventory.json")["complete"])
        with self.assertRaises(ValueError):
            self.verify(self.documents())

    def test_oversized_body_reads_only_one_bounded_prefix(self):
        response = Response(b"x" * (m.MAX_RESPONSE_BYTES + 100))
        runner, _ = self.runner([response, *[Response(p) for p in payloads()[1:]]])
        result = runner.run()
        self.assertEqual(response.read_sizes, [m.MAX_RESPONSE_BYTES + 1])
        self.assertEqual(result["projections"][0]["reason"], "response_too_large")
        self.assertFalse(m.frozen(self.output / "receipt-0.json")["body_complete"])

    def test_unexpected_content_encoding_rejected_without_read(self):
        response = Response(b"compressed", encoding="gzip")
        runner, _ = self.runner([response, *[Response(p) for p in payloads()[1:]]])
        result = runner.run()
        self.assertEqual(response.read_sizes, [])
        self.assertEqual(result["projections"][0]["reason"], "content_encoding")

    def test_duplicate_json_and_nonfinite_json_rejected(self):
        for body in (b'{"bars":{},"bars":{}}', b'{"value":NaN}'):
            with self.subTest(body=body):
                with self.assertRaises(ValueError):
                    m.json_object(body)

    def test_non_json_response_is_retained_as_failure(self):
        runner, _ = self.runner([Response(b"<html>UNSAFE</html>"), *[Response(p) for p in payloads()[1:]]])
        self.assertEqual(runner.run()["projections"][0]["reason"], "invalid_json")
        self.assertTrue(self.verify(self.documents())["verification_passed"])

    def test_daily_dates_handle_dst_and_missing_date_without_replacement(self):
        raw = payloads()[0]
        self.assertIn("-05:00", raw["bars"]["SPY"][0]["t"])
        self.assertIn("-04:00", raw["bars"]["SPY"][-1]["t"])
        raw["bars"]["SPY"].pop(2)
        result = m.project(0, raw)
        self.assertEqual(result["missing_selected_dates"], [m.DATES[2]])
        self.assertFalse(result["ok"])

    def test_invalid_daily_clock_order_and_duplicate_rejected(self):
        for change in ("naive", "intraday", "reverse", "duplicate"):
            raw = payloads()[0]
            if change == "naive":
                raw["bars"]["SPY"][0]["t"] = m.DATES[0]
            elif change == "intraday":
                raw["bars"]["SPY"][0]["t"] = m.DATES[0] + "T12:00:00Z"
            elif change == "reverse":
                raw["bars"]["SPY"].reverse()
            else:
                raw["bars"]["SPY"].insert(0, raw["bars"]["SPY"][0])
            with self.subTest(change=change), self.assertRaises(ValueError):
                m.project(0, raw)

    def test_alpaca_next_page_fails_without_following(self):
        raw = payloads()
        raw[0]["next_page_token"] = "UNFOLLOWED_TOKEN"
        runner, opener = self.runner([Response(p) for p in raw])
        self.assertFalse(runner.run()["limited_availability_passed"])
        self.assertEqual(len(opener.calls), 4)

    def test_membership_row_filter_or_provider_status_mismatch_fails(self):
        for field, replacement in (("active", False), ("market", "crypto"), ("locale", "global")):
            raw = payloads()[1]
            raw["results"][0][field] = replacement
            self.assertFalse(m.project(1, raw)["ok"])
        raw = payloads()[1]
        raw["status"] = "ERROR"
        self.assertFalse(m.project(1, raw)["ok"])

    def test_schema_subset_and_exclusive_end_enforced(self):
        raw = payloads()[3]
        raw["schema"]["status"]["end"] = m.DATES[-1]
        self.assertFalse(m.project(3, raw)["ok"])
        del raw["schema"]["status"]
        result = m.project(3, raw)
        self.assertFalse(result["ok"])
        self.assertIsNone(result["required_schema_ranges"]["status"]["range_start"])

    def test_missing_credentials_fail_before_output_or_network(self):
        credentials = dict(CREDENTIALS)
        del credentials["DATABENTO_API_KEY"]
        with self.assertRaises(ValueError):
            self.runner(credentials=credentials)
        self.assertFalse(self.output.exists())

    def test_polygon_route_chosen_before_attempts_without_runtime_fallback(self):
        credentials = dict(CREDENTIALS)
        credentials["POLYGON_API_KEY"] = credentials.pop("MASSIVE_API_KEY")
        runner, opener = self.runner(credentials=credentials)
        runner.run()
        self.assertTrue(all("api.polygon.io" in opener.calls[i][0].full_url for i in (1, 2)))
        self.assertEqual([r["route"] for r in runner.receipts[1:3]], ["polygon", "polygon"])

    def test_redirect_handler_refuses_new_request(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://unapproved.example"))

    def test_execution_wrong_event_attempt_checkout_and_extra_files_rejected(self):
        self.assertEqual(m.validate_execution(self.execution, self.contract, ENV, self.facts()), self.execution)
        for key, value in (("GITHUB_RUN_ATTEMPT", "2"), ("GITHUB_EVENT_NAME", "workflow_dispatch"),
                           ("GITHUB_SHA", "d" * 40), ("GITHUB_REF", "refs/heads/main")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.validate_execution(self.execution, self.contract, {**ENV, key: value}, self.facts())
        facts = self.facts()
        facts["changed_files"].append("M\tstrategy.py")
        with self.assertRaises(ValueError):
            m.validate_execution(self.execution, self.contract, ENV, facts)
        facts = self.facts()
        facts["clean"] = False
        with self.assertRaises(ValueError):
            m.validate_execution(self.execution, self.contract, ENV, facts)

    def test_only_successful_exact_code_ci_permits_consumption(self):
        receipt = {"id": 987654, "head_sha": CODE, "path": ".github/workflows/ci.yml", "event": "push",
                   "status": "completed", "conclusion": "success", "repository": {"full_name": "RoomyRems/momentumbot"}}
        m.validate_ci(receipt, self.execution)
        for key, value in (("head_sha", EXECUTION), ("conclusion", "failure"), ("status", "in_progress"), ("id", 987653)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.validate_ci({**receipt, key: value}, self.execution)

    def test_consumption_from_other_run_rejected(self):
        marker = m.consumption(self.execution, {**ENV, "GITHUB_RUN_ID": "123457"})
        with self.assertRaises(ValueError):
            BoundedProbe(self.contract, self.execution, marker, ENV, output=self.output, credentials=CREDENTIALS)
        self.assertFalse(self.output.exists())

    def test_extra_raw_fields_and_forged_conclusion_rejected(self):
        runner, _ = self.runner()
        runner.run()
        row = deepcopy(runner.receipts[0])
        row["projection"]["price"] = 100
        row = m.seal({k: v for k, v in row.items() if k != "content_sha256"})
        with self.assertRaises(ValueError):
            m.validate_receipt(row, self.contract["requests"][0], self.marker)
        row = deepcopy(runner.receipts[0])
        row["status"] = 403
        row = m.seal({k: v for k, v in row.items() if k != "content_sha256"})
        with self.assertRaises(ValueError):
            m.validate_receipt(row, self.contract["requests"][0], self.marker)

    def test_archive_external_pins_and_changed_bytes_rejected(self):
        runner, _ = self.runner()
        runner.run()
        path = Path(self.tmp.name) / "evidence.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for name, raw in self.documents().items():
                archive.writestr(name, raw)
        raw = path.read_bytes()
        kwargs = dict(expected_bytes=len(raw), expected_sha256=m.sha(raw), execution_commit=EXECUTION,
                      run_id=ENV["GITHUB_RUN_ID"], code_commit=CODE, code_tree=TREE, ci_run_id="987654")
        self.assertTrue(m.verify_archive(path, self.contract, **kwargs)["verification_passed"])
        with self.assertRaises(ValueError):
            m.verify_archive(path, self.contract, **{**kwargs, "expected_sha256": "0" * 64})
        documents = self.documents()
        documents["requests.json"] += b" "
        with self.assertRaises(ValueError):
            self.verify(documents)

    def test_wrong_external_execution_identity_rejected(self):
        runner, _ = self.runner()
        runner.run()
        with self.assertRaises(ValueError):
            m.verify_documents(self.documents(), self.contract, execution_commit="d" * 40, run_id=ENV["GITHUB_RUN_ID"],
                               code_commit=CODE, code_tree=TREE, ci_run_id="987654")

    def test_workflow_consumes_before_separate_read_only_provider_job(self):
        workflow = yaml.safe_load((ROOT / m.WORKFLOW_PATH).read_text())
        trigger = workflow.get("on", workflow.get(True))
        self.assertEqual(trigger, {"push": {"branches": ["phase-3-historical-snapshot"], "paths": [m.EXECUTION_PATH]}})
        consume, probe = workflow["jobs"]["consume"], workflow["jobs"]["probe"]
        self.assertEqual(consume["permissions"]["contents"], "write")
        self.assertEqual(probe["permissions"]["contents"], "read")
        self.assertEqual(probe["needs"], "consume")
        self.assertNotIn("secrets.", json.dumps(consume))
        self.assertEqual(consume["if"], "github.run_attempt == 1")
        secret_steps = [s for s in probe["steps"] if "secrets." in json.dumps(s)]
        self.assertEqual(len(secret_steps), 1)
        self.assertIn("ALPACA_MAIN_API_KEY", json.dumps(secret_steps[0]))
        self.assertIn("--probe", secret_steps[0]["run"])


if __name__ == "__main__":
    unittest.main()
