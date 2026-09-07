"""Provider-free acquisition tests; HTTP replies and execution identity are synthetic."""
from __future__ import annotations

from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
from datetime import date, timedelta
import gzip
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch

import pandas as pd
import yaml

from momentumbot.research import sealed_historical_execution_acquisition_v02 as acq
from momentumbot.research import sealed_historical_execution_quote_v01 as quote
from momentumbot.research import sealed_historical_record_order_v01 as adapter
from momentumbot.research import sealed_historical_record_order_registration_v01 as registration
from momentumbot.research.sealed_historical_execution_transport_v01 import ExactTimeseriesHTTP
from momentumbot.research.sealed_historical_metadata_transport_v01 import MetadataOnlyHTTP

ROOT = Path(__file__).resolve().parents[1]
HAS_SDK = importlib.util.find_spec("databento") is not None


class Store:
    def __init__(self, request, rows=None):
        self.request, self.rows = request, rows
        self.metadata = {k: request[k] for k in ("dataset", "schema", "symbols", "stype_in")}
        self.metadata.update(start=request["start_ns"], end=request["end_ns"])

    def to_df(self, **kwargs):
        if self.rows is not None:
            return pd.DataFrame(self.rows)
        r = self.request
        row = {"symbol": r["symbols"][0], "ts_recv": r["start_ns"] + 1}
        if r["schema"] == "mbp-1":
            row.update(sequence=1, bid_px_00=1_000_000_000, ask_px_00=1_010_000_000,
                       bid_sz_00=10, ask_sz_00=20)
        else:
            row.update(action=7, is_trading="Y")
        return pd.DataFrame([row])


class Client:
    def __init__(self, requests, fail=None, first_rows=None):
        self.requests, self.fail, self.first_rows = requests, fail, first_rows
        self.calls = []

    def get_range(self, path, **kwargs):
        i = len(self.calls)
        self.calls.append(kwargs)
        Path(path).write_bytes(b"synthetic-dbn")
        if i == self.fail:
            raise RuntimeError("synthetic-sensitive-provider-text")
        return Store(self.requests[i], self.first_rows if i == 0 else None)


def projection_rows():
    projected, _ = registration.diagnostic_fixture(ROOT)
    return [{k: value["value"] for k, value in row["fields"].items()} for row in projected]


def dbn_body(request, first=False):
    """Encode test DBN through the installed SDK, preserving all diagnostic native fields."""
    import databento_dbn as d
    day = date.fromisoformat(request["trading_date"])
    rows = projection_rows() if first else Store(request).to_df().to_dict("records")
    instrument = rows[0].get("instrument_id", 1)
    metadata = d.Metadata(dataset=request["dataset"], start=request["start_ns"], end=request["end_ns"],
        stype_in=d.SType.RAW_SYMBOL, stype_out=d.SType.INSTRUMENT_ID, schema=d.Schema(request["schema"]),
        symbols=request["symbols"], mappings=[N(raw_symbol=request["symbols"][0], intervals=[
            N(start_date=day, end_date=day + timedelta(days=1), symbol=str(instrument))])])
    messages = []
    for row in rows:
        base = {"publisher_id": row.get("publisher_id", 2), "instrument_id": instrument,
                "ts_event": row.get("ts_event", row["ts_recv"] - 1), "ts_recv": row["ts_recv"]}
        if request["schema"] == "mbp-1":
            message = d.MBP1Msg(**base, price=row["bid_px_00"], size=row["bid_sz_00"],
                action=d.Action(row.get("action", "A")), side=d.Side(row.get("side", "B")),
                depth=row.get("depth", 0), sequence=row["sequence"], flags=row.get("flags", 0),
                levels=d.BidAskPair(bid_px=row["bid_px_00"], ask_px=row["ask_px_00"],
                                    bid_sz=row["bid_sz_00"], ask_sz=row["ask_sz_00"]))
        else:
            message = d.StatusMsg(**base, action=d.StatusAction.TRADING, is_trading=d.TriState.YES)
        messages.append(bytes(message))
    return metadata.encode() + b"".join(messages)


class Response:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def iter_content(self, size):
        for i in range(0, len(self.body), size):
            yield self.body[i:i+size]


class Session:
    def __init__(self, requests, quoted, fail=None, metadata_increase=False):
        self.requests, self.quoted = requests, quoted
        self.fail, self.metadata_increase = fail, metadata_increase
        self.calls = []
        self.trust_env = None
        self.closed = False

    def post(self, url, **kwargs):
        i = len(self.calls)
        self.calls.append((url, kwargs))
        if i < 180:
            if url != "https://hist.databento.com/v0/metadata." + quote.METHODS[i % 2]:
                raise AssertionError("unexpected metadata URL")
            value = self.quoted["calls"][i]["value"]
            if self.metadata_increase and i == 0: value += 1
            return Response(json.dumps(value).encode())
        index = i - 180
        if url != "https://hist.databento.com/v0/timeseries.get_range":
            raise AssertionError("unexpected time-series URL")
        if index == self.fail:
            return Response(b"synthetic-sensitive-provider-text", 503)
        return Response(dbn_body(self.requests[index], first=index == 0))

    def close(self): self.closed = True


class Harness:
    def __init__(self, base):
        self.base = base
        self.requests, self.quoted = acq.validate_inputs(ROOT)
        self.execution_path = base / "synthetic-execution.json"
        self.execution = acq.execution_payload(code_commit="a" * 40, code_tree="b" * 40,
            workflow_sha256=acq.file_sha(ROOT / acq.WORKFLOW_PATH), ci_run_id="12345", validation_run_id="12346")
        acq.write_json(self.execution_path, self.execution)
        self.env = {"EXECUTION_CODE_COMMIT_SHA": "a" * 40, "EXECUTION_CODE_TREE_SHA": "b" * 40,
            "GITHUB_REPOSITORY": "RoomyRems/momentumbot", "GITHUB_EVENT_NAME": "push",
            "GITHUB_REF": "refs/heads/phase-3-historical-snapshot", "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_SHA": "c" * 40, "GITHUB_RUN_ID": "12347", "DATABENTO_API_KEY": "synthetic-test-key"}
        self.pins = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", (ROOT / quote.LOCK_PATH).read_text(), re.M))
        self.environment = acq.seal({"implementation": "CPython", "python_version": "3.12.14",
            "requirements_sha256": quote.LOCK_SHA256, "package_versions": self.pins})
        self.pre = base / "preflight"
        acq.write_json(self.pre / "consumption.json", acq.consumption(self.execution, self.env))
        acq.write_json(self.pre / "environment.json", self.environment)
        spec = importlib.util.spec_from_file_location("acquisition_v02_test_runner", ROOT / "scripts/acquire_sealed_historical_execution_inputs_v02.py")
        self.runner = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", [str(ROOT / "scripts"), *sys.path]):
            spec.loader.exec_module(self.runner)

    def run(self, *, name="capture", fail=None, metadata_increase=False, write_limits=None, fail_receipt=False):
        output = self.base / name
        session = Session(self.requests, self.quoted, fail, metadata_increase)
        with ExitStack() as stack:
            stack.enter_context(patch.object(acq, "EXECUTION_PATH", str(self.execution_path)))
            stack.enter_context(patch.dict(os.environ, self.env, clear=True))
            stack.enter_context(patch.object(sys, "argv", ["runner", "--acquire", "--preflight-root", str(self.pre), "--output-root", str(output)]))
            # Only external ZIP provenance and hosted-environment observations are synthetic.
            # All frozen contracts, native data validation, SDK parsing, transport and artifact verification execute.
            stack.enter_context(patch.object(acq, "verify_quote_zip", return_value=self.quoted))
            stack.enter_context(patch.object(acq, "environment", return_value=self.environment))
            stack.enter_context(patch("requests.Session", return_value=session))
            stack.enter_context(patch("socket.socket.connect", side_effect=AssertionError("test forbids network")))
            stack.enter_context(patch.object(self.runner, "MetadataOnlyHTTP", side_effect=lambda *a, **k: MetadataOnlyHTTP(*a, **k, pause=lambda _: None)))
            stack.enter_context(patch.object(self.runner, "ExactTimeseriesHTTP", side_effect=lambda *a, **k: ExactTimeseriesHTTP(*a, **k, pause=lambda _: None)))
            if write_limits is not None:
                original = acq.write_tape
                stack.enter_context(patch.object(acq, "write_tape", side_effect=lambda path, rows, **kw: original(path, rows, **{**kw, **write_limits})))
            if fail_receipt:
                original_write = acq.write_json
                def partial_receipt(path, value, **kwargs):
                    if path.parent.name == "receipts":
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(b'{"contract_id":')
                        raise OSError("synthetic-sensitive-provider-text")
                    return original_write(path, value, **kwargs)
                stack.enter_context(patch.object(acq, "write_json", side_effect=partial_receipt))
            with redirect_stdout(io.StringIO()):
                code = self.runner.main()
            result = acq.verify_capture(output, ROOT, require_success=code == 0)
        return code, output, result, session

    def verify(self, output, require_success=True):
        with patch.object(acq, "EXECUTION_PATH", str(self.execution_path)):
            return acq.verify_capture(output, ROOT, require_success=require_success)


def reseal_inventory(output):
    value = acq.frozen(output / "capture-inventory.json")
    value["files"] = {p.relative_to(output).as_posix(): {"sha256": acq.file_sha(p), "bytes": p.stat().st_size}
        for p in sorted(output.rglob("*")) if p.is_file() and p.name != "capture-inventory.json"}
    acq.write_json(output / "capture-inventory.json", acq.seal({k: v for k, v in value.items() if k != "content_sha256"}), replace=True)


class HistoricalExecutionAcquisitionV02Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests, cls.quoted = acq.validate_inputs(ROOT)
        cls.preflight = acq.preflight(cls.requests, deepcopy(cls.quoted["calls"]), provenance={}, http_attempts=180, blocked_attempts=0)

    def test_registration_preserves_exact_plan_adapter_and_parent_ceilings(self):
        contract = acq.contract()
        self.assertEqual(contract["request_list_content_sha256"], quote.REQUEST_LIST_SHA256)
        self.assertEqual(contract["maximum_billable_bytes"], 154456640)
        self.assertEqual(contract["maximum_quoted_cost_usd"], "0.172787457709")
        self.assertEqual(contract["first_request_native_content_sha256"], registration.NORMALIZED_SHA)
        self.assertNotEqual(acq.CONSUMPTION_REF, acq.parent.CONSUMPTION_REF)
        self.assertIs(acq.normalize, adapter.normalize_store)

    def test_first_request_cannot_substitute_synthetic_or_revised_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = Client(self.requests)
            rows = acq.acquire_tapes(self.requests, self.preflight, client=client, output=root / "out", temporary_root=root)
            self.assertEqual(len(client.calls), 1)
            self.assertEqual(rows[0]["error"], "diagnostic_native_rows_differ")
            self.assertEqual(list(root.glob("*.dbn.zst")), [])
            self.assertIsNone(rows[0]["tape"])

    def test_requote_increase_blocks_before_any_time_series_request(self):
        for index, value in ((0, self.quoted["calls"][0]["value"] + 1), (1, "1")):
            calls = deepcopy(self.quoted["calls"]); calls[index]["value"] = value
            pre = acq.preflight(self.requests, calls, provenance={}, http_attempts=180, blocked_attempts=0)
            client = Client(self.requests)
            with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
                acq.acquire_tapes(self.requests, pre, client=client, output=Path(tmp), temporary_root=Path(tmp))
            self.assertEqual(client.calls, [])

    def test_error_diagnostics_never_serialize_arbitrary_exception_text(self):
        self.assertEqual(acq.error_code(RuntimeError("synthetic-sensitive-provider-text")), "capture_stage_failed")
        self.assertEqual(acq.error_code(ValueError("native receive-time/sequence order reversed")), "native_key_order_reversed")
        self.assertEqual(acq.error_code(ValueError("private provider response")), "unclassified_validation_exception")

    def test_partial_normalized_and_compressed_ceiling_preserve_bounded_evidence(self):
        for limits, maximum, code in (({"maximum_normalized_bytes": 1}, acq.MAX_RETAINED_BYTES, "normalized_byte_ceiling"),
                                      ({"maximum_file_bytes": 15}, 15, "retained_byte_ceiling")):
            with self.subTest(limits=limits), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "partial.gz"
                with self.assertRaises(acq.CaptureFailure) as caught:
                    acq.write_tape(path, [{"row": i} for i in range(100)], **limits)
                self.assertEqual(caught.exception.code, code)
                self.assertLessEqual(path.stat().st_size, maximum)

    def test_deterministic_tape_and_write_once(self):
        rows = [{"row": i} for i in range(4)]
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.gz", Path(tmp) / "b.gz"
            self.assertEqual(acq.write_tape(a, rows), acq.write_tape(b, rows))
            self.assertEqual([json.loads(x) for x in gzip.decompress(a.read_bytes()).splitlines()], rows)
            with self.assertRaises(FileExistsError): acq.write_tape(a, rows)

    def test_hosted_environment_rejects_python_or_package_drift(self):
        pins = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", (ROOT / quote.LOCK_PATH).read_text(), re.M))
        with patch.object(acq.platform, "python_implementation", return_value="CPython"), patch.object(acq.platform, "python_version", return_value="3.12.14"), patch.object(acq.importlib.metadata, "version", side_effect=pins.__getitem__):
            self.assertEqual(acq.environment(ROOT)["package_versions"], pins)
            with patch.object(acq.platform, "python_version", return_value="3.12.13"), self.assertRaises(ValueError): acq.environment(ROOT)
            with patch.object(acq.importlib.metadata, "version", return_value="0"), self.assertRaises(ValueError): acq.environment(ROOT)

    def test_execution_rejects_attempt_two_wrong_parent_branch_and_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(Path(tmp))
            with patch.object(acq, "EXECUTION_PATH", str(h.execution_path)):
                self.assertEqual(acq.validate_execution(ROOT, h.env), h.execution)
                for key, value in (("GITHUB_RUN_ATTEMPT", "2"), ("GITHUB_EVENT_NAME", "workflow_dispatch"),
                                   ("GITHUB_REF", "refs/heads/main"), ("EXECUTION_CODE_COMMIT_SHA", "d" * 40)):
                    with self.subTest(key=key), self.assertRaises(ValueError): acq.validate_execution(ROOT, {**h.env, key: value})

    def test_workflow_consumes_only_sole_child_and_durable_upload_precedes_provider(self):
        workflow = yaml.load((ROOT / acq.WORKFLOW_PATH).read_text(), Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow["on"]), {"push"})
        self.assertEqual(workflow["concurrency"]["cancel-in-progress"], "false")
        steps = workflow["jobs"]["acquire"]["steps"]
        provider = [i for i, step in enumerate(steps) if "DATABENTO_API_KEY" in step.get("env", {})]
        self.assertEqual(len(provider), 1)
        for name in ("Validate execution and every parent byte offline", "Verify successful CI and dedicated validation at the exact code parent",
                     "Download and verify the exact independently verified parent quote", "Verify immutable adapter, consumed parents and protected evidence refs",
                     "Atomically consume the exact acquisition once", "Durably upload consumption before provider access"):
            self.assertLess(next(i for i, step in enumerate(steps) if step.get("name") == name), provider[0])
        detect = next(s for s in workflow["jobs"]["validate"]["steps"] if s.get("id") == "detect")["run"]
        self.assertIn("changed != [path] or added != [path]", detect)
        self.assertEqual(steps[-1]["if"], "always()")
        self.assertIn("--check-environment", workflow["jobs"]["validate"]["steps"][-1]["run"])


@unittest.skipUnless(HAS_SDK, "actual pinned SDK exercised in dedicated v0.2 validation")
class HistoricalExecutionV02EndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.h = Harness(Path(cls.temp.name))
        cls.code, cls.output, cls.result, cls.session = cls.h.run()

    def copied(self, name):
        path = self.h.base / name
        shutil.copytree(self.output, path)
        return path

    def test_real_sdk_full_cli_90_tapes_270_requests_and_full_byte_verification(self):
        self.assertEqual(self.code, 0)
        self.assertTrue(self.result["acquisition_gate_passed"])
        self.assertEqual(self.result["file_count"], 194)
        self.assertEqual(self.result["http_attempts"], 270)
        self.assertEqual(self.result["normalized_row_count"], 1225)
        self.assertEqual(self.result["schema_row_counts"], {"mbp-1": 1180, "status": 45})
        self.assertEqual(self.result["native_key_adjacent_ties"], 175)
        self.assertFalse(self.session.trust_env)
        self.assertTrue(self.session.closed)
        self.assertEqual(len(self.session.calls), 270)
        self.assertTrue(all(call[1]["allow_redirects"] is False for call in self.session.calls))

    def test_provider_failure_retains_complete_prefix_and_safe_ledger(self):
        code, output, result, session = self.h.run(name="http-failure", fail=2)
        self.assertEqual(code, 1)
        self.assertFalse(result["acquisition_gate_passed"])
        self.assertEqual(result["completed_request_count"], 2)
        self.assertEqual(len(session.calls), 183)
        report = acq.frozen(output / "capture-report.json")
        self.assertEqual(report["requests"][-1]["error"], "http_error")
        self.assertEqual(report["requests"][-1]["failure_stage"], "timeseries_request")
        self.assertNotIn("synthetic-sensitive-provider-text", json.dumps(report))
        with self.assertRaises(ValueError): self.h.verify(output)

    def test_requote_increase_never_enters_provider_data_stage(self):
        code, _, result, session = self.h.run(name="requote-increase", metadata_increase=True)
        self.assertEqual(code, 1)
        self.assertEqual(result["completed_request_count"], 0)
        self.assertEqual(len(session.calls), 180)

    def test_partial_tape_has_hash_and_cannot_pass_gate(self):
        code, output, result, session = self.h.run(name="partial", write_limits={"maximum_normalized_bytes": 500})
        self.assertEqual(code, 1)
        self.assertEqual(len(session.calls), 181)
        self.assertEqual(result["completed_request_count"], 0)
        row = acq.frozen(output / "capture-report.json")["requests"][0]
        self.assertEqual(row["error"], "normalized_byte_ceiling")
        self.assertFalse(row["partial_tape"]["runtime_input_eligible"])
        self.assertEqual(acq.file_sha(output / row["partial_tape"]["path"]), row["partial_tape"]["file_sha256"])

    def test_partial_receipt_failure_retains_all_bytes_without_completion(self):
        code, output, result, session = self.h.run(name="partial-receipt", fail_receipt=True)
        self.assertEqual(code, 1)
        self.assertEqual(len(session.calls), 181)
        self.assertEqual(result["completed_request_count"], 0)
        row = acq.frozen(output / "capture-report.json")["requests"][0]
        self.assertEqual(row["failure_stage"], "completion_receipt_write")
        self.assertFalse(row["partial_receipt"]["runtime_input_eligible"])
        self.assertEqual((output / row["partial_receipt"]["path"]).read_bytes(), b'{"contract_id":')
        self.assertIsNotNone(row["partial_tape"])

    def test_raw_tape_tamper_rejected(self):
        output = self.copied("tamper-bytes")
        with (output / "tapes/request-000.jsonl.gz").open("ab") as stream: stream.write(b"x")
        with self.assertRaises(ValueError): self.h.verify(output)

    def test_extra_member_rejected_even_with_rehashed_inventory(self):
        output = self.copied("extra-member")
        (output / "unexpected.txt").write_text("synthetic")
        reseal_inventory(output)
        with self.assertRaises(ValueError): self.h.verify(output)

    def test_rehashed_receipt_cannot_replace_request(self):
        output = self.copied("receipt-tamper")
        path = output / "receipts/request-000.json"
        receipt = acq.frozen(path); receipt["request"]["end_ns"] += 1
        acq.write_json(path, acq.seal({k: v for k, v in receipt.items() if k != "content_sha256"}), replace=True)
        reseal_inventory(output)
        with self.assertRaises(ValueError): self.h.verify(output)

    def test_rehashed_ledger_cannot_claim_retry_or_shift_request(self):
        for name, key, value in (("retry", "automatic_retries", 1), ("missing-attempt", "http_attempts", 89)):
            output = self.copied(name)
            path = output / "timeseries-http-ledger.json"
            ledger = acq.frozen(path); ledger[key] = value
            acq.write_json(path, acq.seal({k: v for k, v in ledger.items() if k != "content_sha256"}), replace=True)
            reseal_inventory(output)
            with self.assertRaises(ValueError): self.h.verify(output)

    def test_wrong_environment_rejected_even_with_valid_content_hashes(self):
        output = self.copied("environment-tamper")
        path = output / "environment.json"
        value = acq.frozen(path); value["python_version"] = "3.12.13"
        acq.write_json(path, acq.seal({k: v for k, v in value.items() if k != "content_sha256"}), replace=True)
        reseal_inventory(output)
        with self.assertRaises(ValueError): self.h.verify(output)


if __name__ == "__main__": unittest.main()
