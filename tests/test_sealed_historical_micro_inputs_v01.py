from __future__ import annotations

import copy
import contextlib
import gzip
import hashlib
import json
import io
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from momentumbot.research.sealed_historical_micro_inputs_v01 import (
    BoundedHTTP, CaptureError, CONTRACT_RELATIVE, EXECUTION_RELATIVE, PLAN_RELATIVE,
    MAX_REQUESTS, NoRedirect, acquire, capture_request, derive_requests,
    expected_contract, file_sha, frozen, normalized_row, request_url, seal,
    validate_contract,
)
from momentumbot.research.sealed_historical_source_checkpoint_v01 import canonical_fingerprint

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/capture_sealed_historical_micro_inputs_v01.py"


def request(kind="sip_trades"):
    return {"request_id": "a" * 64, "symbol": "TEST", "kind": kind,
            "trading_date": "2025-05-30", "asof": "2025-05-30", "feed": "sip",
            "start_inclusive": "2025-05-30T11:00:00+00:00",
            "end_exclusive": "2025-05-30T14:00:00+00:00",
            "adjustment": None if kind == "sip_trades" else "split"}


def trade(stamp="2025-05-30T11:00:00.123456789Z", identity=1):
    return {"t": stamp, "p": 3.15, "s": 100, "x": "Q", "c": ["@"], "i": identity, "z": "C"}


def page(rows, token=None):
    return {"trades": {"TEST": rows}, "next_page_token": token}


def capture_contract():
    return seal({"logical_request_count": 1, "request_manifest_sha256": canonical_fingerprint([request()])})


class HistoricalMicroInputsV01Tests(unittest.TestCase):
    def test_exact_plan_derives_340_requests_without_expanding_symbols(self):
        values = derive_requests(ROOT / PLAN_RELATIVE)
        self.assertEqual(len(values), 340)
        self.assertEqual(len({(r["trading_date"], r["symbol"]) for r in values}), 170)
        self.assertEqual(len({r["request_id"] for r in values}), 340)
        self.assertEqual(sum(r["kind"] == "sip_trades" for r in values), 170)
        contract = validate_contract(ROOT)
        self.assertEqual(contract, expected_contract(ROOT / PLAN_RELATIVE))
        self.assertEqual(contract["incremental_provider_cost_usd"], "0")
        self.assertFalse(contract["micro_replay_executed_by_acquisition"])

    def test_altered_frozen_plan_fails_before_request_derivation(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            payload = frozen(ROOT / PLAN_RELATIVE / "manifest.json")
            payload["activation_count"] += 1
            payload.pop("content_sha256")
            (target / "manifest.json").write_text(json.dumps(seal(payload)))
            with self.assertRaisesRegex(ValueError, "exact scanner activation"):
                derive_requests(target)

    def test_request_routes_preserve_sip_identity_and_exclusive_cutoff(self):
        for kind in ("sip_trades", "ema_warmup_1m_split"):
            url = urlparse(request_url(request(kind), "opaque-page"))
            query = parse_qs(url.query)
            self.assertEqual((url.scheme, url.netloc), ("https", "data.alpaca.markets"))
            self.assertEqual(query["feed"], ["sip"])
            self.assertEqual(query["symbols"], ["TEST"])
            self.assertEqual(query["asof"], ["2025-05-30"])
            self.assertEqual(query["end"], ["2025-05-30T13:59:59.999999999+00:00"])
            self.assertEqual(query["page_token"], ["opaque-page"])
            self.assertEqual(url.path, "/v2/stocks/trades" if kind == "sip_trades" else "/v2/stocks/bars")
            if kind == "ema_warmup_1m_split":
                self.assertEqual(query["timeframe"], ["1Min"])
                self.assertEqual(query["adjustment"], ["split"])

    def test_route_substitutions_fail(self):
        for field, value in (("symbol", "../account"), ("feed", "iex"), ("asof", "2026-01-01"), ("kind", "orders"), ("adjustment", "all")):
            changed = request()
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                request_url(changed)

    def test_capture_exhausts_pages_and_preserves_nanoseconds(self):
        pages = [page([trade()], "second"), page([trade("2025-05-30T11:00:00.123456790Z", 2)])]
        fetch = Mock(side_effect=pages)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            receipt = capture_request(request(), output, fetch)
            data = gzip.decompress((output / receipt["path"]).read_bytes())
            rows = [json.loads(line) for line in data.splitlines()]
            self.assertEqual(rows[0]["t"], "2025-05-30T11:00:00.123456789+00:00")
            self.assertEqual(rows[1]["i"], 2)
            self.assertEqual((receipt["pages"], receipt["record_count"]), (2, 2))
            self.assertEqual(receipt["logical_sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(receipt["file_sha256"], file_sha(output / receipt["path"]))
            self.assertEqual(fetch.call_args_list[1].args[1], "second")

    def test_invalid_or_repeated_pagination_is_retained_as_failure(self):
        for responses in ([page([trade()], "same"), page([trade()], "same")],
                          [{"trades": {"TEST": [trade()]}}],
                          [{"trades": {"OTHER": [trade()]}, "next_page_token": None}],
                          [page([])]):
            with self.subTest(responses=responses), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "capture"
                with self.assertRaises(CaptureError):
                    acquire([request()], output, Mock(side_effect=responses), contract=capture_contract(), provenance={})
                self.assertTrue((output / "capture-failure.json").is_file())
                self.assertFalse((output / "capture-report.json").exists())
                self.assertTrue(list(output.rglob("*.gz")))

    def test_failed_date_does_not_become_zero_or_leak_provider_exception(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "capture"
            secret = "PRIVATE_PROVIDER_EXCEPTION_VALUE"
            with self.assertRaises(CaptureError):
                acquire([request()], output, Mock(side_effect=RuntimeError(secret)), contract=capture_contract(), provenance={})
            failure = frozen(output / "capture-failure.json")
            self.assertEqual(failure["status"], "failed")
            self.assertNotIn(secret, (output / "capture-failure.json").read_text())
            self.assertFalse(failure["micro_runtime_executed"])

    def test_input_validation_rejects_wrong_time_or_malformed_values(self):
        for field, value in (("t", "2025-05-30T14:00:00Z"), ("t", "2025-05-30T11:00:00"),
                             ("p", float("nan")), ("s", True), ("s", 1.5),
                             ("z", "UNKNOWN"), ("c", None)):
            row = trade()
            row[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(CaptureError):
                normalized_row(row, request())

    def test_backward_pages_fail(self):
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(CaptureError, "chronological"):
            capture_request(request(), Path(temporary), Mock(side_effect=[
                page([trade("2025-05-30T11:01:00Z")], "next"), page([trade()])]))

    def test_overlapping_pages_cannot_double_count_a_trade(self):
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(CaptureError, "repeat the same"):
            capture_request(request(), Path(temporary), Mock(side_effect=[page([trade()], "next"), page([trade()])]))

    def test_existing_capture_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            sentinel = output / "immutable.txt"
            sentinel.write_text("keep")
            fetch = Mock()
            with self.assertRaises(FileExistsError):
                acquire([request()], output, fetch, contract={}, provenance={})
            fetch.assert_not_called()
            self.assertEqual(sentinel.read_text(), "keep")

    def test_request_ceiling_blocks_before_network_and_records_the_block(self):
        with tempfile.TemporaryDirectory() as temporary:
            fetch = BoundedHTTP(Path(temporary), key="synthetic-key", secret="synthetic-secret")
            fetch.attempts = MAX_REQUESTS
            fetch.opener = Mock()
            with self.assertRaisesRegex(CaptureError, "before network access"):
                fetch(request(), None)
            fetch.opener.open.assert_not_called()
            ledger = json.loads((Path(temporary) / "request-ledger.json").read_text())
            self.assertEqual(ledger["total_attempts"], MAX_REQUESTS)
            self.assertEqual(ledger["blocked_attempts"], 1)
            self.assertNotIn("synthetic-secret", json.dumps(ledger))

    def test_redirect_cannot_forward_credentials(self):
        with self.assertRaisesRegex(CaptureError, "redirect"):
            NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.org")

    def test_validation_cli_makes_no_provider_calls(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src")
        process = subprocess.run([sys.executable, str(SCRIPT), "--validate-only"], cwd=ROOT, env=env,
                                 text=True, capture_output=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        value = json.loads(process.stdout)
        self.assertTrue(value["contract_valid"])
        self.assertEqual(value["provider_calls"], 0)

    def test_workflow_consumes_and_preserves_evidence_before_secret_step(self):
        text = (ROOT / ".github/workflows/sealed-historical-micro-input-acquisition-v01.yml").read_text()
        self.assertNotIn("workflow_dispatch:", text)
        self.assertIn(EXECUTION_RELATIVE, text)
        self.assertIn('test "$GITHUB_RUN_ATTEMPT" = 1', text)
        self.assertIn("--diff-filter=A", text)
        self.assertIn("cancel-in-progress: false", text)
        self.assertIn("--require-hashes", text)
        self.assertLess(text.index("Atomically consume"), text.index("Durably upload consumption"))
        self.assertLess(text.index("Durably upload consumption"), text.index("secrets.ALPACA_MAIN_API_KEY"))
        self.assertEqual(text.count("secrets.ALPACA_MAIN_API_KEY"), 1)
        self.assertIn("if: always()", text)

    def test_real_workflow_parent_binding_accepts_only_the_execution_file(self):
        workflow = (ROOT / ".github/workflows/sealed-historical-micro-input-acquisition-v01.yml").read_text()
        binding = workflow.split("name: Bind sole execution child to its tested parent", 1)[1]
        script = textwrap.dedent(binding.split("run: |\n", 1)[1].split("      - uses:", 1)[0])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.DEVNULL, text=True).strip()
            git("init")
            git("config", "user.name", "Synthetic Test")
            git("config", "user.email", "synthetic@example.invalid")
            (root / "code.py").write_text("pass\n")
            git("add", "code.py")
            git("commit", "-m", "Synthetic code parent")
            parent = git("rev-parse", "HEAD")
            tree = git("show", "-s", "--format=%T", "HEAD")
            authority = root / EXECUTION_RELATIVE
            authority.parent.mkdir(parents=True)
            authority.write_text("{}\n")
            git("add", EXECUTION_RELATIVE)
            git("commit", "-m", "Synthetic execution child")
            env = dict(os.environ, GITHUB_EVENT_NAME="push", GITHUB_REF="refs/heads/phase-3-historical-snapshot",
                       GITHUB_RUN_ATTEMPT="1", GITHUB_ENV=str(root / "github-env"))
            result = subprocess.run(["bash", "-e", "-c", script], cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"EXECUTION_CODE_COMMIT_SHA={parent}", (root / "github-env").read_text())
            self.assertIn(f"EXECUTION_CODE_TREE_SHA={tree}", (root / "github-env").read_text())
            (root / "code.py").write_text("raise SystemExit(1)\n")
            git("add", "code.py")
            git("commit", "--amend", "--no-edit")
            changed = subprocess.run(["bash", "-e", "-c", script], cwd=root, env=env, capture_output=True, text=True)
            self.assertNotEqual(changed.returncode, 0)

    def test_warmup_is_normalized_without_inventing_micro_bars(self):
        row = {"t": "2025-05-30T11:00:00Z", "o": 3, "h": 4, "l": 2, "c": 3.5,
               "v": 500, "n": 5, "vw": 3.25}
        normalized = normalized_row(row, request("ema_warmup_1m_split"))
        self.assertEqual(normalized["c"], 3.5)
        self.assertEqual(normalized["v"], 500)
        row["l"] = 10
        with self.assertRaises(CaptureError):
            normalized_row(row, request("ema_warmup_1m_split"))

    def test_complete_cli_capture_with_synthetic_provider_preserves_all_receipts(self):
        with patch.object(sys, "path", [str(ROOT / "scripts"), *sys.path]):
            namespace = runpy.run_path(str(SCRIPT))["main"].__globals__
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(ROOT / PLAN_RELATIVE, root / PLAN_RELATIVE)
            contract_path = root / CONTRACT_RELATIVE
            contract_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / CONTRACT_RELATIVE, contract_path)
            workflow_path = root / namespace["WORKFLOW"]
            workflow_path.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / namespace["WORKFLOW"], workflow_path)
            contract = validate_contract(root)
            execution = namespace["execution_payload"](contract, code_commit="c" * 40,
                        code_tree="d" * 40, workflow_sha256=file_sha(workflow_path))
            (root / EXECUTION_RELATIVE).write_text(json.dumps(execution))
            marker = seal({"execution_content_sha256": execution["content_sha256"],
                           "consumption_ref": namespace["CONSUMPTION_REF"],
                           "execution_commit_sha": "e" * 40, "workflow_run_id": "123", "workflow_run_attempt": 1})
            (root / "consumption.json").write_text(json.dumps(marker))
            (root / "source.json").write_text(json.dumps(namespace["expected_source_receipt"](contract)))
            class SyntheticHTTP:
                def __init__(self, output, **kwargs):
                    self.output = output
                    self.attempts = self.blocked = 0
                def __call__(self, requested, token):
                    self.attempts += 1
                    if requested["kind"] == "sip_trades":
                        value = trade(requested["start_inclusive"])
                        return {"trades": {requested["symbol"]: [value]}, "next_page_token": None}
                    row = {"t": requested["start_inclusive"], "o": 3, "h": 4, "l": 2, "c": 3.5, "v": 500, "n": 5, "vw": 3.25}
                    return {"bars": {requested["symbol"]: [row]}, "next_page_token": None}
                def save_ledger(self):
                    (self.output / "request-ledger.json").write_text(json.dumps({"synthetic_provider": True, "total_attempts": self.attempts}))
            env = {"EXECUTION_CODE_COMMIT_SHA": "c" * 40, "EXECUTION_CODE_TREE_SHA": "d" * 40,
                   "GITHUB_SHA": "e" * 40, "GITHUB_RUN_ATTEMPT": "1", "GITHUB_RUN_ID": "123",
                   "GITHUB_REF": "refs/heads/phase-3-historical-snapshot", "GITHUB_EVENT_NAME": "push",
                   "GITHUB_REPOSITORY": "RoomyRems/momentumbot", "ALPACA_API_KEY": "synthetic-key", "ALPACA_API_SECRET": "synthetic-secret"}
            argv = [str(SCRIPT), "--acquire", "--output", str(root / "capture"),
                    "--consumption-marker", str(root / "consumption.json"), "--source-receipt", str(root / "source.json")]
            with patch.dict(namespace, {"ROOT": root, "BoundedHTTP": SyntheticHTTP}), patch.dict(os.environ, env, clear=True), patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(namespace["main"](), 0)
            inventory = frozen(root / "capture/capture-inventory.json")
            self.assertTrue(inventory["complete"])
            self.assertEqual(inventory["provider_attempts"], 340)
            self.assertFalse(inventory["micro_runtime_executed"])
            for relative, sha in inventory["files"].items():
                self.assertEqual(file_sha(root / "capture" / relative), sha)
            self.assertEqual(len(list((root / "capture/dates").rglob("*.gz"))), 340)
            self.assertEqual(frozen(root / "capture/capture-report.json")["logical_requests_completed"], 340)


if __name__ == "__main__":
    unittest.main()
