from __future__ import annotations

import contextlib
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

import yaml

from momentumbot.research import sealed_historical_micro_session_inputs_v02 as child
from momentumbot.research.sealed_historical_micro_inputs_v01 import derive_requests as parent_requests

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/capture_sealed_historical_micro_session_inputs_v02.py"
WORKFLOW = ROOT / ".github/workflows/sealed-historical-micro-session-input-acquisition-v02.yml"


def bar(request):
    return {"t": request["start_inclusive"], "o": 3, "h": 4, "l": 2,
            "c": 3.5, "v": 500, "n": 5, "vw": 3.25}


class HistoricalMicroSessionInputsV02Tests(unittest.TestCase):
    def test_exact_170_pairs_retain_every_activation_and_date(self):
        values = child.derive_requests(ROOT / child.PLAN_RELATIVE)
        parents = [r for r in parent_requests(ROOT / child.PLAN_RELATIVE) if r["kind"] == "sip_trades"]
        self.assertEqual(len(values), 170)
        self.assertEqual(len({r["trading_date"] for r in values}), 30)
        for current, parent in zip(values, parents, strict=True):
            self.assertEqual(current["activation_ids"], parent["activation_ids"])
            self.assertEqual(current["symbol"], parent["symbol"])
            self.assertEqual(current["end_exclusive"], parent["end_exclusive"])
            self.assertEqual(current["start_inclusive"], current["trading_date"] + "T08:00:00+00:00")
        contract = child.validate_contract(ROOT)
        self.assertEqual(contract["maximum_http_attempts"], 680)
        self.assertFalse(contract["micro_replay_executed_by_acquisition"])

    def test_route_requires_raw_sip_exact_date_and_session(self):
        request = child.derive_requests(ROOT / child.PLAN_RELATIVE)[0]
        url = urlparse(child.request_url(request, "next"))
        query = parse_qs(url.query)
        self.assertEqual((url.scheme, url.netloc, url.path), ("https", "data.alpaca.markets", "/v2/stocks/bars"))
        self.assertEqual(query["adjustment"], ["raw"])
        self.assertEqual(query["feed"], ["sip"])
        self.assertEqual(query["end"], [request["trading_date"] + "T13:59:59.999999999+00:00"])
        for key, value in [("adjustment", "split"), ("feed", "iex"), ("kind", "orders"),
                           ("asof", "2026-09-06"), ("start_inclusive", "2025-05-30T07:59:00Z"),
                           ("end_exclusive", "2025-05-30T14:01:00Z"), ("symbol", "../orders")]:
            with self.subTest(key=key), self.assertRaises(child.CaptureError):
                child.request_url({**request, key: value})

    def test_child_request_budget_is_enforced_before_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            fetch = child.BoundedHTTP(output, key="test-key", secret="test-secret")
            fetch.attempts = child.MAX_REQUESTS
            fetch.opener = Mock()
            request = child.derive_requests(ROOT / child.PLAN_RELATIVE)[0]
            with self.assertRaisesRegex(child.CaptureError, "before network"):
                fetch(request, None)
            fetch.opener.open.assert_not_called()
            self.assertEqual(json.loads((output / "request-ledger.json").read_text())["blocked_attempts"], 1)

    def test_failed_capture_retains_tape_and_sanitizes_exception(self):
        requests = child.derive_requests(ROOT / child.PLAN_RELATIVE)
        contract = child.validate_contract(ROOT)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "capture"
            with self.assertRaises(child.CaptureError):
                child.acquire(requests, output, Mock(side_effect=RuntimeError("PRIVATE_VALUE")), contract=contract, provenance={})
            failure = child.frozen(output / "capture-failure.json")
            self.assertNotIn("PRIVATE_VALUE", json.dumps(failure))
            self.assertEqual(failure["contract_id"], child.CONTRACT_ID)
            self.assertFalse((output / "capture-report.json").exists())
            self.assertEqual(len(list((output / "dates").rglob("*.gz"))), 1)

    def test_wrong_or_short_request_set_fails_before_capture(self):
        requests = child.derive_requests(ROOT / child.PLAN_RELATIVE)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "capture"
            fetch = Mock()
            with self.assertRaises(ValueError):
                child.acquire(requests[:-1], output, fetch, contract=child.validate_contract(ROOT), provenance={})
            fetch.assert_not_called()
            self.assertFalse(output.exists())

    def test_execution_workflow_guard_and_secret_step_are_exact(self):
        workflow = yaml.safe_load(WORKFLOW.read_text())
        steps = workflow["jobs"]["capture"]["steps"]
        guard = next(s["run"] for s in steps if s.get("name", "").startswith("Bind sole"))
        self.assertEqual([s["name"] for s in steps if "ALPACA_API_KEY" in s.get("env", {})], ["Capture only the missing raw session minute OHLC"])
        self.assertLess(next(i for i,s in enumerate(steps) if s.get("name", "").startswith("Durably upload")), next(i for i,s in enumerate(steps) if "ALPACA_API_KEY" in s.get("env", {})))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
            git("init")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.invalid")
            (root / "code.py").write_text("pass\n")
            git("add", ".")
            git("commit", "-m", "code")
            parent, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
            execution = root / child.EXECUTION_RELATIVE
            execution.parent.mkdir(parents=True)
            execution.write_text("{}\n")
            git("add", ".")
            git("commit", "-m", "execution")
            env = {**os.environ, "GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/phase-3-historical-snapshot", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_ENV": str(root / "env.out")}
            subprocess.run(["bash", "-e", "-c", guard], cwd=root, env=env, check=True, capture_output=True)
            self.assertEqual((root / "env.out").read_text(), f"EXECUTION_CODE_COMMIT_SHA={parent}\nEXECUTION_CODE_TREE_SHA={tree}\n")
            env["GITHUB_RUN_ATTEMPT"] = "2"
            self.assertNotEqual(subprocess.run(["bash", "-e", "-c", guard], cwd=root, env=env, capture_output=True).returncode, 0)

    def test_complete_synthetic_cli_capture_verifies_all_170_tapes(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            namespace = runpy.run_path(str(SCRIPT))
        finally:
            sys.path.pop(0)
        namespace = namespace["main"].__globals__
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(ROOT / child.PLAN_RELATIVE, root / child.PLAN_RELATIVE)
            (root / child.CONTRACT_RELATIVE).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / child.CONTRACT_RELATIVE, root / child.CONTRACT_RELATIVE)
            workflow_path = root / namespace["WORKFLOW"]
            workflow_path.parent.mkdir(parents=True)
            shutil.copyfile(WORKFLOW, workflow_path)
            contract = child.validate_contract(root)
            execution = namespace["execution_payload"](contract, code_commit="c" * 40, code_tree="d" * 40, workflow_sha256=child.file_sha(workflow_path))
            child.write_json(root / child.EXECUTION_RELATIVE, execution)
            marker = child.seal({"execution_content_sha256": execution["content_sha256"], "consumption_ref": child.CONSUMPTION_REF, "execution_commit_sha": "e" * 40, "workflow_run_id": "123", "workflow_run_attempt": 1})
            child.write_json(root / "consumption.json", marker)
            child.write_json(root / "source.json", namespace["expected_source_receipt"](contract))
            class SyntheticHTTP:
                def __init__(self, output, **kwargs):
                    self.output = output
                    self.attempts = self.blocked = 0
                def __call__(self, request, token):
                    self.attempts += 1
                    return {"bars": {request["symbol"]: [bar(request)]}, "next_page_token": None}
                def save_ledger(self):
                    (self.output / "request-ledger.json").write_text(json.dumps({"synthetic_provider": True, "total_attempts": self.attempts}))
            env = {"EXECUTION_CODE_COMMIT_SHA": "c" * 40, "EXECUTION_CODE_TREE_SHA": "d" * 40,
                   "GITHUB_SHA": "e" * 40, "GITHUB_RUN_ATTEMPT": "1", "GITHUB_RUN_ID": "123",
                   "GITHUB_REF": "refs/heads/phase-3-historical-snapshot", "GITHUB_EVENT_NAME": "push",
                   "GITHUB_REPOSITORY": "RoomyRems/momentumbot", "ALPACA_API_KEY": "synthetic-key", "ALPACA_API_SECRET": "synthetic-secret"}
            argv = [str(SCRIPT), "--acquire", "--output", str(root / "capture"), "--consumption-marker", str(root / "consumption.json"), "--source-receipt", str(root / "source.json")]
            with patch.dict(namespace, {"ROOT": root, "BoundedHTTP": SyntheticHTTP}), patch.dict(os.environ, env, clear=True), patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(namespace["main"](), 0)
            inventory = child.frozen(root / "capture/capture-inventory.json")
            self.assertTrue(inventory["complete"])
            self.assertEqual(inventory["provider_attempts"], 170)
            for relative, sha in inventory["files"].items():
                self.assertEqual(child.file_sha(root / "capture" / relative), sha)
            report = child.frozen(root / "capture/capture-report.json")
            self.assertEqual(report["contract_id"], child.CONTRACT_ID)
            self.assertEqual(report["logical_requests_completed"], 170)
            for receipt in report["receipts"]:
                data = gzip.decompress((root / "capture" / receipt["path"]).read_bytes())
                self.assertEqual(hashlib.sha256(data).hexdigest(), receipt["logical_sha256"])
                self.assertEqual(len(data.splitlines()), receipt["record_count"])


if __name__ == "__main__":
    unittest.main()
