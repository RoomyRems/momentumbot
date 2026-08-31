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
    SELECTED_DATES,
    load_authorization as load_v01_authorization,
)
from momentumbot.research.sealed_historical_availability_v02 import (
    AUTHORIZATION_CONTENT_SHA256,
    AUTHORIZATION_ID,
    MAIN_SECRET_NAMES,
    build_probe_plan,
    load_authorization,
    run_probe,
    validate_authorization,
    validate_parent_bundle,
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
    / "sealed-historical-provider-availability-v0.2-authorization.json"
)
V01_AUTHORIZATION = (
    ROOT
    / "research"
    / "strategy"
    / "sealed-historical-provider-availability-v0.1-authorization.json"
)
REGISTRATION = (
    ROOT / "research" / "strategy" / "sealed-historical-walk-forward-v0.1.json"
)
V01_REPORT = (
    ROOT
    / "research"
    / "data-audits"
    / "sealed-historical-provider-availability-v0.1-report-2026-08-31.json"
)
V01_FAILURE_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "sealed-historical-provider-availability-v0.1-failure-2026-08-31.json"
)
WORKFLOW = ROOT / ".github/workflows/sealed-historical-provider-availability-v02.yml"
REGISTRATION_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "sealed-historical-provider-availability-v0.2-registration-2026-08-31.json"
)
REGISTRATION_AUDIT_CONTENT_SHA256 = (
    "865ec84dfe7a818b292ce2dc8044e556834fbf9db2260a262f7d97ee0b2bacef"
)


def _alpaca_payload(
    *, dates: tuple[str, ...] = SELECTED_DATES, token: object = None
) -> dict[str, object]:
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


class SealedHistoricalAvailabilityV02Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.authorization = load_authorization(AUTHORIZATION)
        self.v01_authorization = load_v01_authorization(V01_AUTHORIZATION)
        self.registration = load_json_object(REGISTRATION)
        self.v01_report = load_json_object(V01_REPORT)
        self.v01_failure_audit = load_json_object(V01_FAILURE_AUDIT)

    def _run(self, response: Mapping[str, object] | None = None):
        calls: list[Mapping[str, object]] = []

        def alpaca(request: Mapping[str, object]):
            calls.append(request)
            return response or _alpaca_payload()

        report = run_probe(
            authorization=self.authorization,
            registration=self.registration,
            v01_authorization=self.v01_authorization,
            v01_report=self.v01_report,
            v01_failure_audit=self.v01_failure_audit,
            alpaca_request=alpaca,
            repository="RoomyRems/momentumbot",
            authorization_commit_sha="a" * 40,
            workflow_run_id="45678",
            workflow_run_attempt=1,
        )
        return report, calls

    def test_authorization_freezes_exact_main_credential_routing(self) -> None:
        self.assertEqual(
            self.authorization["content_sha256"], AUTHORIZATION_CONTENT_SHA256
        )
        self.assertEqual(
            self.authorization["credential_routing"]["github_actions_secret_names"],
            list(MAIN_SECRET_NAMES),
        )
        self.assertEqual(
            self.authorization["credential_routing"]["validated_precedent_commit"],
            "e7db059bf258b4d069c788d6293307737d4cea2e",
        )

    def test_parent_bundle_requires_exact_v01_401_and_passed_other_providers(self) -> None:
        validate_parent_bundle(
            registration=self.registration,
            v01_authorization=self.v01_authorization,
            v01_report=self.v01_report,
            v01_failure_audit=self.v01_failure_audit,
        )
        plan = build_probe_plan(
            authorization=self.authorization,
            registration=self.registration,
            v01_authorization=self.v01_authorization,
            v01_report=self.v01_report,
            v01_failure_audit=self.v01_failure_audit,
        )
        self.assertEqual(plan["maximum_total_calls"], 1)
        self.assertEqual(plan["alpaca"]["symbols"], "SPY")
        self.assertEqual(plan["alpaca"]["feed"], "sip")

    def test_registration_audit_binds_exact_repair_files(self) -> None:
        audit = load_json_object(REGISTRATION_AUDIT)
        body = dict(audit)
        claimed = body.pop("content_sha256")
        self.assertEqual(canonical_fingerprint(body), claimed)
        self.assertEqual(claimed, REGISTRATION_AUDIT_CONTENT_SHA256)
        self.assertEqual(audit["causal_attestation"]["provider_calls_during_registration"], 0)
        self.assertFalse(audit["isolated_repair"]["secret_values_changed_or_observed"])
        for row in audit["artifacts"].values():
            path = ROOT / row["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["file_sha256"])

    def test_success_makes_one_call_and_inherits_other_provider_results(self) -> None:
        report, calls = self._run()
        self.assertTrue(report["availability_gate_passed"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(report["current_attempt_call_counts"], {
            "alpaca": 1, "total": 1
        })
        self.assertFalse(report["massive_or_polygon_called"])
        self.assertFalse(report["databento_called"])
        self.assertEqual(
            report["credential_routing"]["github_actions_secret_names_used"],
            list(MAIN_SECRET_NAMES),
        )
        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn('"bars"', rendered)
        self.assertNotIn('"open"', rendered)

    def test_provider_failure_is_preserved_without_retry(self) -> None:
        response = {"ok": False, "status": 401, "error_kind": "http_error"}
        report, calls = self._run(response)
        self.assertFalse(report["availability_gate_passed"])
        self.assertEqual(len(calls), 1)
        self.assertFalse(report["automatic_retry_or_rerun_attempted"])
        self.assertIn("do not acquire", report["next_gate"])

    def test_missing_session_or_pagination_fails_closed(self) -> None:
        report, _ = self._run(_alpaca_payload(dates=SELECTED_DATES[:-1]))
        self.assertFalse(report["availability_gate_passed"])
        report, _ = self._run(_alpaca_payload(token="unexpected"))
        self.assertFalse(report["availability_gate_passed"])

    def test_rehashed_authorization_cannot_restore_generic_secret_names(self) -> None:
        changed = copy.deepcopy(self.authorization)
        changed["credential_routing"]["github_actions_secret_names"] = [
            "ALPACA_API_KEY",
            "ALPACA_API_SECRET",
        ]
        body = dict(changed)
        body.pop("content_sha256")
        changed["content_sha256"] = canonical_fingerprint(body)
        with self.assertRaisesRegex(ValueError, "frozen hash"):
            validate_authorization(changed)

    def test_rehashed_parent_substitution_is_rejected(self) -> None:
        changed = copy.deepcopy(self.v01_report)
        changed["workflow_provenance"]["workflow_run_id"] = "other"
        body = dict(changed)
        body.pop("content_sha256")
        changed["content_sha256"] = canonical_fingerprint(body)
        with self.assertRaisesRegex(ValueError, "v0.1 report changed"):
            validate_parent_bundle(
                registration=self.registration,
                v01_authorization=self.v01_authorization,
                v01_report=changed,
                v01_failure_audit=self.v01_failure_audit,
            )

    def test_wrong_repository_commit_or_attempt_is_rejected_before_call(self) -> None:
        calls = 0

        def alpaca(_: Mapping[str, object]):
            nonlocal calls
            calls += 1
            return _alpaca_payload()

        kwargs = dict(
            authorization=self.authorization,
            registration=self.registration,
            v01_authorization=self.v01_authorization,
            v01_report=self.v01_report,
            v01_failure_audit=self.v01_failure_audit,
            alpaca_request=alpaca,
            workflow_run_id="1",
        )
        with self.assertRaisesRegex(ValueError, "repository"):
            run_probe(repository="some/fork", authorization_commit_sha="a" * 40,
                      workflow_run_attempt=1, **kwargs)
        with self.assertRaisesRegex(ValueError, "full Git SHA"):
            run_probe(repository="RoomyRems/momentumbot", authorization_commit_sha="bad",
                      workflow_run_attempt=1, **kwargs)
        with self.assertRaisesRegex(ValueError, "one attempt"):
            run_probe(repository="RoomyRems/momentumbot", authorization_commit_sha="a" * 40,
                      workflow_run_attempt=2, **kwargs)
        self.assertEqual(calls, 0)

    def test_rehashed_report_cannot_claim_massive_or_databento_call(self) -> None:
        report, _ = self._run()
        report["databento_called"] = True
        body = dict(report)
        body.pop("content_sha256")
        report["content_sha256"] = canonical_fingerprint(body)
        with self.assertRaisesRegex(ValueError, "databento_called"):
            validate_report(report, self.authorization)

    def test_write_once_refuses_overwrite(self) -> None:
        report, _ = self._run()
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "report.json"
            write_json_once(target, report)
            with self.assertRaises(FileExistsError):
                write_json_once(target, report)

    def test_provider_free_cli_validation(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/probe_sealed_historical_availability_v02.py",
                "--validate-only",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["authorization_id"], AUTHORIZATION_ID)
        self.assertEqual(payload["maximum_total_calls"], 1)
        self.assertEqual(payload["provider_calls"], 0)

    def test_workflow_uses_only_validated_main_secret_pair(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            "ALPACA_API_KEY: ${{ secrets.ALPACA_MAIN_API_KEY }}", text
        )
        self.assertIn(
            "ALPACA_API_SECRET: ${{ secrets.ALPACA_MAIN_API_SECRET }}", text
        )
        self.assertNotIn("ALPACA_API_KEY: ${{ secrets.ALPACA_API_KEY }}", text)
        self.assertNotIn(
            "ALPACA_API_SECRET: ${{ secrets.ALPACA_API_SECRET }}", text
        )
        self.assertNotIn("DATABENTO_API_KEY", text)
        self.assertNotIn("MASSIVE_API_KEY", text)
        self.assertNotIn("POLYGON_API_KEY", text)
        self.assertIn("github.run_attempt == 1", text)
        self.assertNotIn("schedule:", text)


if __name__ == "__main__":
    unittest.main()
