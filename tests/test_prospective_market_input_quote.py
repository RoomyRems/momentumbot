from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from momentumbot.research.microstructure_contract import canonical_fingerprint
from momentumbot.research.prospective_market_input_capture import (
    CONTRACT_CONTENT_SHA256 as CAPTURE_CONTRACT_CONTENT_SHA256,
    load_capture_contract,
)
from momentumbot.research.prospective_market_input_quote import (
    CONTRACT_CONTENT_SHA256,
    EXPECTED_REPOSITORY,
    FREEZE_CHECKPOINT_SHA,
    PERMITTED_METHODS,
    SDK_VERSION,
    build_quote_authorization,
    build_unavailable_report,
    build_zero_request_report,
    run_metadata_quote,
    validate_execution_context,
    validate_parent_bundle,
    validate_quote_authorization,
    validate_quote_contract,
    validate_quote_report,
    load_quote_contract,
)
from momentumbot.research.prospective_opportunity_freeze import (
    CONTRACT_CONTENT_SHA256 as FREEZE_CONTRACT_CONTENT_SHA256,
    GENERAL_PROFILE_ID,
    build_daily_decision_source,
    build_daily_opportunity_freeze,
    load_opportunity_freeze_contract,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "prospective-market-input-metadata-quote-v0.1.json"
)
CAPTURE_CONTRACT = (
    ROOT / "research" / "strategy" / "prospective-market-input-capture-v0.1.json"
)
FREEZE_CONTRACT = (
    ROOT / "research" / "strategy" / "prospective-opportunity-freeze-v0.1.json"
)
REGISTRATION_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "prospective-market-input-metadata-quote-v0.1-registration-2026-08-22.json"
)
WORKFLOW = ROOT / ".github" / "workflows" / "prospective-market-input-quote.yml"
SCRIPT = ROOT / "scripts" / "quote_prospective_market_inputs.py"


def _ns(value: str) -> int:
    return int(datetime.fromisoformat(value).astimezone(UTC).timestamp() * 1_000_000_000)


def _rehash(payload: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(payload)
    result.pop("content_sha256", None)
    result["content_sha256"] = canonical_fingerprint(result)
    return result


def _decision() -> dict[str, object]:
    return {
        "activation_id": "activation-test",
        "plan_id": "plan-test",
        "symbol": "TEST",
        "candidate_qualified_ts_ns": _ns("2026-08-24T11:29:30+00:00"),
        "decision_ts_ns": _ns("2026-08-24T11:30:00+00:00"),
        "micro_runtime_content_sha256": "c" * 64,
        "eligible_strategy_profile_ids": [GENERAL_PROFILE_ID],
    }


class _Metadata:
    def __init__(
        self,
        *,
        zero_schema: str | None = None,
        fail_method: str | None = None,
        fail_schema: str | None = None,
    ) -> None:
        self.zero_schema = zero_schema
        self.fail_method = fail_method
        self.fail_schema = fail_schema
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get_billable_size(self, **kwargs):
        self.calls.append(("get_billable_size", kwargs))
        if self.fail_method == "get_billable_size" and kwargs["schema"] == self.fail_schema:
            raise RuntimeError("provider narrative must not persist")
        return 0 if kwargs["schema"] == self.zero_schema else 1_250

    def get_cost(self, **kwargs):
        self.calls.append(("get_cost", kwargs))
        if self.fail_method == "get_cost" and kwargs["schema"] == self.fail_schema:
            raise RuntimeError("provider narrative must not persist")
        return 0.0125


class _Client:
    def __init__(self, metadata: _Metadata) -> None:
        self.metadata = metadata


class ProspectiveMarketInputQuoteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load_quote_contract(CONTRACT)
        cls.capture_contract = load_capture_contract(CAPTURE_CONTRACT)
        cls.freeze_contract = load_opportunity_freeze_contract(FREEZE_CONTRACT)
        cls.bundle = cls._build_bundle(_decision(), candidate_count=1)
        cls.authorization = cls._authorization(cls.bundle)

    @classmethod
    def _build_bundle(cls, *decisions, candidate_count: int):
        source = build_daily_decision_source(
            trading_date="2026-08-24",
            scanner_runtime_content_sha256="a" * 64,
            micro_runtime_manifest_content_sha256="b" * 64,
            candidate_count=candidate_count,
            decisions=decisions,
        )
        result = build_daily_opportunity_freeze(
            cls.freeze_contract,
            cls.capture_contract,
            source,
        )
        return validate_parent_bundle(
            cls.contract,
            cls.capture_contract,
            result.opportunity_manifest,
            result.request_manifest,
            result.freeze_manifest,
        )

    @classmethod
    def _authorization(cls, bundle):
        return build_quote_authorization(
            cls.contract,
            cls.capture_contract,
            bundle,
            repository=EXPECTED_REPOSITORY,
            freeze_run_id="123456789",
            freeze_run_attempt=1,
            freeze_artifact_name=(
                f"prospective-opportunity-freeze-{bundle.trading_date}"
            ),
        )

    def _run(self, metadata: _Metadata):
        return run_metadata_quote(
            self.contract,
            self.capture_contract,
            self.bundle,
            self.authorization,
            _Client(metadata),
            generated_at=datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
            sdk_version=SDK_VERSION,
            workflow_run_id="987654321",
            workflow_run_attempt=1,
        )

    def _validate(self, report, *, bundle=None, authorization=None):
        validate_quote_report(
            report,
            quote_contract=self.contract,
            capture_contract=self.capture_contract,
            bundle=bundle or self.bundle,
            authorization=authorization or self.authorization,
        )

    def test_contract_is_hash_bound_unarmed_and_metadata_only(self):
        self.assertEqual(self.contract["content_sha256"], CONTRACT_CONTENT_SHA256)
        parents = self.contract["frozen_parents"]
        self.assertEqual(
            parents["opportunity_freeze_contract_content_sha256"],
            FREEZE_CONTRACT_CONTENT_SHA256,
        )
        self.assertEqual(
            parents["market_input_capture_contract_content_sha256"],
            CAPTURE_CONTRACT_CONTENT_SHA256,
        )
        self.assertEqual(
            parents["opportunity_freeze_checkpoint_sha"],
            FREEZE_CHECKPOINT_SHA,
        )
        provider = self.contract["provider_scope"]
        self.assertEqual(provider["permitted_metadata_methods"], list(PERMITTED_METHODS))
        authority = self.contract["authority_boundary"]
        self.assertFalse(authority["provider_metadata_quote_authorized_at_registration"])
        self.assertEqual(authority["provider_metadata_quote_run_count"], 0)
        self.assertFalse(authority["provider_timeseries_request_authorized"])
        self.assertFalse(authority["provider_purchase_authorized"])
        self.assertFalse(authority["broker_order_authorized"])
        self.assertEqual(authority["databento_credit_authorized_usd"], "0")

    def test_bundle_rederives_every_request_and_rejects_rehashed_tamper(self):
        self.assertEqual(self.bundle.request_count, 2)
        request = copy.deepcopy(self.bundle.request_manifest)
        request["requests"][0]["start_ns"] += 1
        request = _rehash(request)
        with self.assertRaisesRegex(ValueError, "deterministic derivation"):
            validate_parent_bundle(
                self.contract,
                self.capture_contract,
                self.bundle.opportunity_manifest,
                request,
                self.bundle.freeze_manifest,
            )

        opportunity = copy.deepcopy(self.bundle.opportunity_manifest)
        opportunity["opportunities"][0]["ross_action"] = "buy"
        opportunity = _rehash(opportunity)
        with self.assertRaisesRegex(ValueError, "forbidden keys|row fields changed"):
            validate_parent_bundle(
                self.contract,
                self.capture_contract,
                opportunity,
                self.bundle.request_manifest,
                self.bundle.freeze_manifest,
            )

        freeze = copy.deepcopy(self.bundle.freeze_manifest)
        freeze["provider_metadata_quote_made"] = True
        freeze = _rehash(freeze)
        with self.assertRaisesRegex(ValueError, "binding changed"):
            validate_parent_bundle(
                self.contract,
                self.capture_contract,
                self.bundle.opportunity_manifest,
                self.bundle.request_manifest,
                freeze,
            )

    def test_authorization_is_deterministic_exact_and_does_not_authorize_download(self):
        repeated = self._authorization(self.bundle)
        self.assertEqual(repeated, self.authorization)
        self.assertEqual(self.authorization["request_count"], 2)
        self.assertEqual(self.authorization["maximum_provider_call_count"], 4)
        self.assertTrue(self.authorization["provider_metadata_quote_authorized"])
        self.assertFalse(self.authorization["provider_timeseries_request_authorized"])
        self.assertFalse(self.authorization["provider_purchase_authorized"])
        self.assertFalse(self.authorization["raw_market_data_persistence_authorized"])
        self.assertFalse(self.authorization["authorization_reuse_authorized"])
        self.assertEqual(
            self.authorization["parent_bundle"]["freeze_manifest_content_sha256"],
            self.bundle.freeze_manifest["content_sha256"],
        )

        changed = copy.deepcopy(self.authorization)
        changed["request_count"] = 1
        changed = _rehash(changed)
        with self.assertRaisesRegex(ValueError, "binding changed"):
            validate_quote_authorization(
                changed,
                quote_contract=self.contract,
                capture_contract=self.capture_contract,
                bundle=self.bundle,
            )

    def test_success_quotes_all_exact_rows_with_two_methods_each(self):
        metadata = _Metadata()
        report = self._run(metadata)
        self._validate(report)
        self.assertEqual(report["quote_status"], "complete")
        self.assertTrue(report["metadata_quote_gate_passed"])
        self.assertEqual(report["metadata_call_count"], 4)
        self.assertEqual(
            [method for method, _kwargs in metadata.calls],
            [
                "get_billable_size",
                "get_cost",
                "get_billable_size",
                "get_cost",
            ],
        )
        for _method, kwargs in metadata.calls:
            self.assertEqual(kwargs["dataset"], "XNAS.ITCH")
            self.assertEqual(kwargs["symbols"], ["TEST"])
            self.assertEqual(kwargs["stype_in"], "raw_symbol")
            self.assertRegex(kwargs["start"], r"\.\d{9}Z$")
            self.assertRegex(kwargs["end"], r"\.\d{9}Z$")
        metrics = report["quote_metrics"]
        self.assertTrue(metrics["totals_complete"])
        self.assertEqual(metrics["total_billable_size_bytes"], 2_500)
        self.assertEqual(metrics["total_quoted_cost_usd"], "0.0250")
        self.assertFalse(report["download_authorized_by_this_artifact"])

    def test_zero_size_is_unavailable_without_substitution(self):
        metadata = _Metadata(zero_schema="status")
        report = self._run(metadata)
        self._validate(report)
        self.assertEqual(report["quote_status"], "complete_with_unavailable_requests")
        self.assertFalse(report["metadata_quote_gate_passed"])
        self.assertEqual(report["quote_metrics"]["unavailable_request_count"], 1)
        status = next(row for row in report["quote_rows"] if row["schema"] == "status")
        self.assertEqual(status["availability_status"], "unavailable_zero_billable_size")
        self.assertFalse(report["request_substitution_attempted"])

    def test_partial_provider_failure_is_sanitized_and_totals_are_incomplete(self):
        metadata = _Metadata(fail_method="get_cost", fail_schema="status")
        report = self._run(metadata)
        self._validate(report)
        self.assertEqual(report["quote_status"], "partial")
        self.assertFalse(report["metadata_quote_gate_passed"])
        self.assertEqual(report["metadata_call_count"], 4)
        self.assertFalse(report["quote_metrics"]["totals_complete"])
        self.assertIsNone(report["quote_metrics"]["total_billable_size_bytes"])
        self.assertEqual(
            report["errors"],
            [
                {
                    "stage": "metadata.get_cost",
                    "request_id": "2026-08-24-TEST-status",
                    "error_kind": "RuntimeError",
                }
            ],
        )
        self.assertNotIn("provider narrative", json.dumps(report))
        self.assertFalse(report["provider_error_messages_persisted"])

    def test_zero_opportunity_date_is_success_without_client_or_credential(self):
        bundle = self._build_bundle(candidate_count=3)
        authorization = self._authorization(bundle)
        metadata = _Metadata(fail_method="get_cost", fail_schema="status")
        report = run_metadata_quote(
            self.contract,
            self.capture_contract,
            bundle,
            authorization,
            _Client(metadata),
            generated_at=datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
            sdk_version=SDK_VERSION,
            workflow_run_id="987654321",
            workflow_run_attempt=1,
        )
        self._validate(report, bundle=bundle, authorization=authorization)
        self.assertEqual(metadata.calls, [])
        self.assertEqual(report["quote_status"], "not_applicable_zero_requests")
        self.assertTrue(report["metadata_quote_gate_passed"])
        self.assertFalse(report["provider_metadata_quote_made"])
        self.assertTrue(report["quote_metrics"]["totals_complete"])
        self.assertEqual(report["quote_metrics"]["total_quoted_cost_usd"], "0")

        direct = build_zero_request_report(
            self.contract,
            self.capture_contract,
            bundle,
            authorization,
            generated_at=datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
            workflow_run_id="987654321",
            workflow_run_attempt=1,
        )
        self.assertEqual(direct, report)

    def test_pre_provider_failure_retains_every_request_without_messages(self):
        report = build_unavailable_report(
            self.contract,
            self.capture_contract,
            self.bundle,
            self.authorization,
            generated_at=datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
            workflow_run_id="987654321",
            workflow_run_attempt=1,
            sdk_version="not_loaded",
            error_stage="credential",
            error_kind="missing_databento_api_key",
        )
        self._validate(report)
        self.assertEqual(report["metadata_call_count"], 0)
        self.assertEqual(len(report["quote_rows"]), 2)
        self.assertTrue(
            all(row["availability_status"] == "unavailable_before_provider" for row in report["quote_rows"])
        )
        self.assertEqual(report["quote_status"], "unavailable_before_provider")
        self.assertFalse(report["metadata_quote_gate_passed"])

    def test_execution_context_requires_exact_freeze_and_first_attempt(self):
        validate_execution_context(
            self.authorization,
            repository=EXPECTED_REPOSITORY,
            freeze_run_id="123456789",
            freeze_run_attempt=1,
            freeze_artifact_name="prospective-opportunity-freeze-2026-08-24",
            workflow_run_id="987654321",
            workflow_run_attempt=1,
        )
        with self.assertRaisesRegex(ValueError, "freeze provenance"):
            validate_execution_context(
                self.authorization,
                repository=EXPECTED_REPOSITORY,
                freeze_run_id="123456788",
                freeze_run_attempt=1,
                freeze_artifact_name="prospective-opportunity-freeze-2026-08-24",
                workflow_run_id="987654321",
                workflow_run_attempt=1,
            )
        with self.assertRaisesRegex(ValueError, "rerun"):
            validate_execution_context(
                self.authorization,
                repository=EXPECTED_REPOSITORY,
                freeze_run_id="123456789",
                freeze_run_attempt=1,
                freeze_artifact_name="prospective-opportunity-freeze-2026-08-24",
                workflow_run_id="987654321",
                workflow_run_attempt=2,
            )

    def test_cli_authorization_and_missing_credential_quote_are_provider_free(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle_dir = root / "bundle"
            bundle_dir.mkdir()
            for name, payload in (
                ("opportunity-manifest.json", self.bundle.opportunity_manifest),
                ("request-manifest.json", self.bundle.request_manifest),
                ("freeze-manifest.json", self.bundle.freeze_manifest),
            ):
                (bundle_dir / name).write_text(json.dumps(payload), encoding="utf-8")
            authorization_path = root / "authorization.json"
            env = {
                key: value
                for key, value in os.environ.items()
                if "DATABENTO" not in key and "ALPACA" not in key
            }
            current_pythonpath = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = str(ROOT / "src") + (
                os.pathsep + current_pythonpath if current_pythonpath else ""
            )
            shared = [
                "--bundle-dir",
                str(bundle_dir),
                "--repository",
                EXPECTED_REPOSITORY,
                "--freeze-run-id",
                "123456789",
                "--freeze-run-attempt",
                "1",
                "--freeze-artifact-name",
                "prospective-opportunity-freeze-2026-08-24",
            ]
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "authorize",
                    *shared,
                    "--output",
                    str(authorization_path),
                ],
                cwd=ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(completed.stdout), self.authorization)
            self.assertEqual(json.loads(authorization_path.read_text()), self.authorization)

            output = root / "quote.json"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "quote",
                    *shared,
                    "--authorization",
                    str(authorization_path),
                    "--workflow-run-id",
                    "987654321",
                    "--workflow-run-attempt",
                    "1",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            report = json.loads(output.read_text())
            self._validate(report)
            self.assertEqual(report["quote_status"], "unavailable_before_provider")
            self.assertEqual(report["errors"][0]["error_kind"], "missing_databento_api_key")

    def test_contract_and_report_scope_expansion_is_rejected(self):
        changed_contract = copy.deepcopy(self.contract)
        changed_contract["authority_boundary"]["provider_purchase_authorized"] = True
        changed_contract = _rehash(changed_contract)
        with self.assertRaises(ValueError):
            validate_quote_contract(changed_contract)

        report = self._run(_Metadata())
        report["download_authorized_by_this_artifact"] = True
        report = _rehash(report)
        with self.assertRaisesRegex(ValueError, "must remain false"):
            self._validate(report)

    def test_workflow_push_is_provider_free_and_dispatch_requires_exact_authority(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("push:", text)
        self.assertIn("github.event_name == 'push'", text)
        self.assertIn("github.event_name == 'workflow_dispatch'", text)
        self.assertIn("authorization_commit_sha", text)
        self.assertIn("authorization_path", text)
        self.assertIn("freeze_run_id", text)
        self.assertIn("freeze_run_attempt", text)
        self.assertIn("actions/download-artifact@v4", text)
        self.assertIn("databento==0.83.0", text)
        self.assertIn("GITHUB_RUN_ATTEMPT", text)
        self.assertIn("DATABENTO_API_KEY", text)
        self.assertIn("metadata_quote_gate_passed", text)
        self.assertNotIn("historical.timeseries.get_range", text)
        self.assertNotIn("historical.batch", text)
        self.assertNotIn("live.subscribe", text)
        push_job, quote_job = text.split("  quote-exact-freeze-bundle:", maxsplit=1)
        self.assertNotIn("DATABENTO_API_KEY", push_job)
        self.assertNotIn("quote_prospective_market_inputs.py quote", push_job)
        self.assertIn("DATABENTO_API_KEY", quote_job)

    def test_registration_audit_is_hash_bound_and_unarmed(self):
        audit = json.loads(REGISTRATION_AUDIT.read_text(encoding="utf-8"))
        unsigned = {key: value for key, value in audit.items() if key != "content_sha256"}
        self.assertEqual(canonical_fingerprint(unsigned), audit["content_sha256"])
        self.assertEqual(audit["contract"]["content_sha256"], CONTRACT_CONTENT_SHA256)
        for row in audit["bound_files"]:
            self.assertEqual(
                hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest(),
                row["file_sha256"],
            )
        execution = audit["execution_status"]
        self.assertFalse(execution["exact_bundle_authorization_created"])
        self.assertFalse(execution["metadata_quote_run"])
        authority = audit["authority_boundary"]
        self.assertFalse(authority["provider_call_run"])
        self.assertFalse(authority["provider_credential_loaded"])
        self.assertFalse(authority["provider_download_run"])
        self.assertEqual(authority["databento_credit_used_usd"], "0")
        self.assertFalse(authority["broker_order_submitted"])
        self.assertFalse(authority["runtime_authority_created"])


if __name__ == "__main__":
    unittest.main()
