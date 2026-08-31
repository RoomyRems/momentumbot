from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Mapping

from momentumbot.research.sealed_historical_availability import (
    AUTHORIZATION_CONTENT_SHA256,
    DATASET,
    SELECTED_DATES,
    build_probe_plan,
    load_authorization,
    run_probe,
    validate_authorization,
    validate_report,
    write_json_once,
)
from momentumbot.research.sealed_historical_walk_forward import (
    canonical_fingerprint,
    load_json_object,
)


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = (
    ROOT
    / "research"
    / "strategy"
    / "sealed-historical-provider-availability-v0.1-authorization.json"
)
REGISTRATION = (
    ROOT / "research" / "strategy" / "sealed-historical-walk-forward-v0.1.json"
)
WORKFLOW = ROOT / ".github/workflows/sealed-historical-provider-availability.yml"
REGISTRATION_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "sealed-historical-provider-availability-v0.1-registration-2026-08-31.json"
)
REGISTRATION_AUDIT_CONTENT_SHA256 = (
    "46e6122be93b434a456d7a0da0f09e6eb1c5596e26bc37727ab24089c3e46c05"
)


class _Metadata:
    def __init__(self, value: object) -> None:
        self.value = value
        self.calls = 0

    def get_dataset_range(self, *, dataset: str) -> Mapping[str, object]:
        self.calls += 1
        if isinstance(self.value, BaseException):
            raise self.value
        if dataset != DATASET or not isinstance(self.value, Mapping):
            raise AssertionError("unexpected Databento metadata request")
        return self.value


class _Databento:
    def __init__(self, value: object) -> None:
        self.metadata = _Metadata(value)


def _alpaca_payload(*, dates: tuple[str, ...] = SELECTED_DATES, token: object = None):
    return {
        "ok": True,
        "status": 200,
        "payload": {
            "bars": {
                "SPY": [
                    {"t": f"{value}T14:00:00Z", "o": 1, "h": 2, "l": 1, "c": 2}
                    for value in dates
                ]
            },
            "next_page_token": token,
        },
    }


def _massive_payload():
    return {
        "ok": True,
        "status": 200,
        "payload": {
            "results": [
                {
                    "ticker": "A",
                    "active": True,
                    "market": "stocks",
                    "locale": "us",
                    "primary_exchange": "XNYS",
                    "type": "CS",
                    "name": "opaque",
                }
            ],
            "next_url": "https://example.invalid/next",
        },
    }


class SealedHistoricalAvailabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.authorization = load_authorization(AUTHORIZATION)
        self.registration = load_json_object(REGISTRATION)

    def _run(
        self,
        *,
        alpaca_response: Mapping[str, object] | None = None,
        massive_response: Mapping[str, object] | None = None,
        databento_value: object | None = None,
    ):
        alpaca_calls: list[Mapping[str, object]] = []
        massive_calls: list[Mapping[str, object]] = []

        def alpaca(request: Mapping[str, object]):
            alpaca_calls.append(request)
            return alpaca_response or _alpaca_payload()

        def massive(request: Mapping[str, object]):
            massive_calls.append(request)
            return massive_response or _massive_payload()

        client = _Databento(
            databento_value
            or {"start": "2018-05-01", "end": "2026-08-31T23:59:59Z"}
        )
        report = run_probe(
            registration=self.registration,
            authorization=self.authorization,
            alpaca_request=alpaca,
            massive_request=massive,
            databento_client=client,
            repository="RoomyRems/momentumbot",
            authorization_commit_sha="a" * 40,
            workflow_run_id="12345",
            workflow_run_attempt=1,
        )
        return report, alpaca_calls, massive_calls, client

    def test_authorization_and_plan_are_exactly_frozen(self) -> None:
        self.assertEqual(
            self.authorization["content_sha256"], AUTHORIZATION_CONTENT_SHA256
        )
        plan = build_probe_plan(self.registration, self.authorization)
        self.assertEqual(plan["maximum_total_calls"], 4)
        self.assertEqual([row["date"] for row in plan["massive"]], [
            SELECTED_DATES[0], SELECTED_DATES[-1]
        ])
        self.assertEqual(plan["databento"], {
            "dataset": "XNAS.ITCH", "method": "metadata.get_dataset_range"
        })

    def test_registration_audit_is_hash_bound_to_exact_files(self) -> None:
        audit = load_json_object(REGISTRATION_AUDIT)
        body = dict(audit)
        claimed = body.pop("content_sha256")
        self.assertEqual(canonical_fingerprint(body), claimed)
        self.assertEqual(claimed, REGISTRATION_AUDIT_CONTENT_SHA256)
        self.assertEqual(audit["causal_attestation"]["provider_calls_during_registration"], 0)
        for row in audit["artifacts"].values():
            path = ROOT / row["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["file_sha256"])

    def test_success_uses_four_calls_and_persists_only_summaries(self) -> None:
        report, alpaca_calls, massive_calls, client = self._run()
        self.assertTrue(report["availability_gate_passed"])
        self.assertEqual(report["call_counts"], {
            "alpaca": 1, "massive": 2, "databento": 1, "total": 4
        })
        self.assertEqual(len(alpaca_calls), 1)
        self.assertEqual(len(massive_calls), 2)
        self.assertEqual(client.metadata.calls, 1)
        rendered = json.dumps(report, sort_keys=True)
        for raw_value in ("opaque", "https://example.invalid/next", '"ticker": "A"'):
            self.assertNotIn(raw_value, rendered)
        self.assertNotIn('"bars"', rendered)

    def test_missing_session_fails_without_becoming_zero(self) -> None:
        report, *_ = self._run(alpaca_response=_alpaca_payload(dates=SELECTED_DATES[:-1]))
        self.assertFalse(report["availability_gate_passed"])
        summary = report["probes"]["alpaca_sip_session_calendar"]
        self.assertEqual(summary["missing_selected_dates"], [SELECTED_DATES[-1]])
        self.assertIn("do not acquire", report["next_gate"])

    def test_alpaca_pagination_token_fails_closed(self) -> None:
        report, *_ = self._run(alpaca_response=_alpaca_payload(token="another-page"))
        self.assertFalse(report["availability_gate_passed"])
        self.assertTrue(
            report["probes"]["alpaca_sip_session_calendar"]["next_page_present"]
        )

    def test_massive_missing_required_field_fails_closed(self) -> None:
        response = _massive_payload()
        del response["payload"]["results"][0]["primary_exchange"]
        report, *_ = self._run(massive_response=response)
        self.assertFalse(report["availability_gate_passed"])

    def test_databento_short_range_fails_closed(self) -> None:
        report, *_ = self._run(
            databento_value={"start": "2025-06-01", "end": "2025-07-01"}
        )
        self.assertFalse(report["availability_gate_passed"])
        self.assertFalse(
            report["probes"]["databento_dataset_range"][
                "selected_interval_covered"
            ]
        )

    def test_provider_exception_is_sanitized_and_report_remains_valid(self) -> None:
        report, *_ = self._run(databento_value=RuntimeError("secret provider body"))
        self.assertFalse(report["availability_gate_passed"])
        rendered = json.dumps(report)
        self.assertNotIn("secret provider body", rendered)
        self.assertIn("RuntimeError", rendered)
        validate_report(report, self.authorization, self.registration)

    def test_rehashed_authorization_cannot_expand_call_budget(self) -> None:
        changed = copy.deepcopy(self.authorization)
        changed["authorized_calls"]["maximum_total_calls"] = 5
        body = dict(changed)
        body.pop("content_sha256")
        changed["content_sha256"] = canonical_fingerprint(body)
        with self.assertRaisesRegex(ValueError, "frozen hash"):
            validate_authorization(changed)

    def test_wrong_repository_commit_or_attempt_is_rejected(self) -> None:
        kwargs = dict(
            registration=self.registration,
            authorization=self.authorization,
            alpaca_request=lambda _: _alpaca_payload(),
            massive_request=lambda _: _massive_payload(),
            databento_client=_Databento({"start": "2018-01-01", "end": "2030-01-01"}),
            workflow_run_id="1",
        )
        with self.assertRaisesRegex(ValueError, "repository"):
            run_probe(repository="some/fork", authorization_commit_sha="a" * 40,
                      workflow_run_attempt=1, **kwargs)
        with self.assertRaisesRegex(ValueError, "full Git SHA"):
            run_probe(repository="RoomyRems/momentumbot", authorization_commit_sha="abc",
                      workflow_run_attempt=1, **kwargs)
        with self.assertRaisesRegex(ValueError, "one attempt"):
            run_probe(repository="RoomyRems/momentumbot", authorization_commit_sha="a" * 40,
                      workflow_run_attempt=2, **kwargs)

    def test_rehashed_report_tampering_is_rejected(self) -> None:
        report, *_ = self._run()
        report["raw_provider_rows_persisted"] = True
        body = dict(report)
        body.pop("content_sha256")
        report["content_sha256"] = canonical_fingerprint(body)
        with self.assertRaisesRegex(ValueError, "raw_provider_rows_persisted"):
            validate_report(report, self.authorization, self.registration)

    def test_write_once_refuses_overwrite(self) -> None:
        report, *_ = self._run()
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "report.json"
            write_json_once(target, report)
            with self.assertRaises(FileExistsError):
                write_json_once(target, report)

    def test_provider_free_cli_validation(self) -> None:
        completed = subprocess.run(
            [sys.executable, "scripts/probe_sealed_historical_availability.py", "--validate-only"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["validated"])
        self.assertEqual(payload["provider_calls"], 0)

    def test_workflow_has_manual_one_shot_provider_gate_only(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("schedule:", text)
        self.assertIn("github.run_attempt == 1", text)
        self.assertIn("databento==0.83.0", text)
        self.assertIn("availability_gate_passed", text)
        self.assertNotIn("pull_request:", text)
        self.assertNotIn("paper-api.alpaca.markets", text)


if __name__ == "__main__":
    unittest.main()
