from __future__ import annotations

import copy
import builtins
import hashlib
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import run_databento_microstructure_features_v02 as runner

from momentumbot.research import databento_feature_diagnostic_v02 as diagnostic
from momentumbot.research.databento_feature_diagnostic_v01 import (
    FEATURE_ENGINE_SOURCE_FILE_SHA256 as V01_FEATURE_ENGINE_SOURCE_FILE_SHA256,
    extract_case_feature_diagnostic,
)
from momentumbot.research.databento_feature_diagnostic_v02 import (
    CONTRACT_CONTENT_SHA256,
    DIAGNOSTIC_CONTRACT_ID,
    EXECUTION_AUTHORIZATION_ID,
    FEATURE_ENGINE_SOURCE_FILE_SHA256,
    MAX_PREFLIGHT_BILLABLE_SIZE_BYTES,
    MAX_PREFLIGHT_COST_USD,
    PARENT_ADAPTER_FILE_SHA256,
    PARENT_FAILURE_AUDIT_ID,
    PARENT_FAILURE_CONTENT_SHA256,
    REQUEST,
    SAFE_ERROR_CODES,
    SafeDiagnosticFailure,
    build_unavailable_report,
    extract_classified_feature_diagnostic,
    load_parent_failure_audit,
    load_repair_contract,
    run_safe_failure_classifier,
    validate_execution_authorization,
    validate_safe_failure_report,
)
from momentumbot.research.databento_quote import SDK_VERSION
from momentumbot.research.microstructure_contract import canonical_fingerprint
from tests.test_databento_feature_diagnostic_v01 import (
    FakeRecord,
    RUNTIME,
    _record,
    _records,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-feature-diagnostic-v0.2.json"
)
PARENT_FAILURE_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-feature-diagnostic-v0.1-"
    "run-32444174639-failure-2026-08-20.json"
)
PARENT_ADAPTER = (
    ROOT
    / "src"
    / "momentumbot"
    / "research"
    / "databento_feature_diagnostic_v01.py"
)
FEATURE_ENGINE = ROOT / "src" / "momentumbot" / "research" / "microstructure_features.py"
FUTURE_AUTHORIZATION = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-feature-diagnostic-v0.2-execution.json"
)
WORKFLOW = (
    ROOT
    / ".github"
    / "workflows"
    / "databento-microstructure-features-v02.yml"
)
REGISTRATION_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-feature-diagnostic-v0.2-registration-2026-08-20.json"
)
GENERATED_AT = datetime(2026, 8, 20, 22, tzinfo=UTC)
SENSITIVE_PROVIDER_DETAIL = "licensed provider detail 998877"


def _authorization() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "execution_authorization_id": EXECUTION_AUTHORIZATION_ID,
        "artifact_type": (
            "explicit_one_shot_databento_safe_failure_classifier_authorization"
        ),
        "diagnostic_contract_id": DIAGNOSTIC_CONTRACT_ID,
        "diagnostic_contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "authorized_push_parent_sha": "a" * 40,
        "explicit_user_authorization": (
            "Synthetic deterministic unit-test authorization; no provider call."
        ),
        "provider_purchase_authorized": True,
        "exact_request_count_authorized": 1,
        "hard_preflight_cost_ceiling_usd": "0.001",
        "hard_preflight_billable_size_ceiling_bytes": 1_000_000,
        "first_github_actions_attempt_only": True,
        "automatic_retry_authorized": False,
        "batch_or_live_endpoint_authorized": False,
        "mbp10_redownload_authorized": False,
        "raw_market_data_publication_authorized": False,
        "broker_or_order_change_authorized": False,
        "strategy_or_threshold_change_authorized": False,
    }
    payload["content_sha256"] = canonical_fingerprint(payload)
    return payload


class FakeMetadata:
    def __init__(
        self,
        *,
        cost: float = 0.0005,
        size: int = 117_040,
        fail: bool = False,
    ) -> None:
        self.cost = cost
        self.size = size
        self.fail = fail
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get_billable_size(self, **kwargs: object) -> int:
        self.calls.append(("get_billable_size", kwargs))
        if self.fail:
            raise RuntimeError(SENSITIVE_PROVIDER_DETAIL)
        return self.size

    def get_cost(self, **kwargs: object) -> float:
        self.calls.append(("get_cost", kwargs))
        if self.fail:
            raise RuntimeError(SENSITIVE_PROVIDER_DETAIL)
        return self.cost


class FakeStore:
    def __init__(
        self,
        records: list[FakeRecord],
        *,
        dataset: str = "XNAS.ITCH",
        schema: str = "mbo",
        iteration_failure: bool = False,
    ) -> None:
        self.metadata = SimpleNamespace(dataset=dataset, schema=schema)
        self.records = records
        self.iteration_failure = iteration_failure

    def __iter__(self):
        if self.iteration_failure:
            raise RuntimeError(SENSITIVE_PROVIDER_DETAIL)
        return iter(self.records)


class FakeTimeseries:
    def __init__(
        self,
        *,
        mode: str = "success",
        records: list[FakeRecord] | None = None,
    ) -> None:
        self.mode = mode
        self.records = _records() if records is None else records
        self.calls: list[dict[str, object]] = []
        self.paths: list[Path] = []

    def get_range(self, **kwargs: object) -> FakeStore:
        self.calls.append(kwargs)
        path = Path(str(kwargs["path"]))
        self.paths.append(path)
        if self.mode == "missing_file":
            return FakeStore(self.records)
        if self.mode == "empty_file":
            path.write_bytes(b"")
            return FakeStore(self.records)
        path.write_bytes(b"synthetic DBN placeholder, not provider data")
        if self.mode == "provider_failure":
            raise RuntimeError(SENSITIVE_PROVIDER_DETAIL)
        if self.mode == "metadata_failure":
            return FakeStore(self.records, dataset="wrong.dataset")
        if self.mode == "iteration_failure":
            return FakeStore(self.records, iteration_failure=True)
        return FakeStore(self.records)


class FakeClient:
    def __init__(
        self,
        *,
        cost: float = 0.0005,
        size: int = 117_040,
        preflight_failure: bool = False,
        timeseries_mode: str = "success",
        records: list[FakeRecord] | None = None,
    ) -> None:
        self.metadata = FakeMetadata(
            cost=cost,
            size=size,
            fail=preflight_failure,
        )
        self.timeseries = FakeTimeseries(mode=timeseries_mode, records=records)


def _resign(payload: dict[str, object]) -> None:
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    payload["content_sha256"] = canonical_fingerprint(unsigned)


def _failure(exc: SafeDiagnosticFailure) -> tuple[str, str, str | None]:
    return exc.phase, exc.code, exc.exception_kind


def _unknown_cancel_records() -> list[FakeRecord]:
    return [
        _record(
            sequence=1,
            action="R",
            side="N",
            ts_recv=1_000_000_000,
            flags=RUNTIME.f_last,
        ),
        _record(
            sequence=2,
            action="C",
            side="A",
            price=102,
            size=10,
            order_id=999,
            ts_recv=2_000_000_000,
            flags=RUNTIME.f_last,
        ),
    ]


class DatabentoFeatureDiagnosticV02Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parent_failure = load_parent_failure_audit(PARENT_FAILURE_AUDIT)
        cls.contract = load_repair_contract(
            CONTRACT,
            parent_failure_audit=cls.parent_failure,
        )
        cls.authorization = _authorization()
        validate_execution_authorization(cls.authorization)

    def run_gate(self, client: FakeClient) -> dict[str, object]:
        return run_safe_failure_classifier(
            self.contract,
            self.parent_failure,
            self.authorization,
            client,
            generated_at=GENERATED_AT,
            sdk_version=SDK_VERSION,
            runtime=RUNTIME,
        )

    def test_failure_audit_contract_and_frozen_sources_are_hash_bound(self):
        for payload, expected in (
            (self.parent_failure, PARENT_FAILURE_CONTENT_SHA256),
            (self.contract, CONTRACT_CONTENT_SHA256),
        ):
            claimed = payload["content_sha256"]
            unsigned = {
                key: value
                for key, value in payload.items()
                if key != "content_sha256"
            }
            self.assertEqual(claimed, expected)
            self.assertEqual(canonical_fingerprint(unsigned), expected)
        self.assertEqual(
            self.parent_failure["audit_id"],
            PARENT_FAILURE_AUDIT_ID,
        )
        self.assertEqual(
            hashlib.sha256(PARENT_ADAPTER.read_bytes()).hexdigest(),
            PARENT_ADAPTER_FILE_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(FEATURE_ENGINE.read_bytes()).hexdigest(),
            FEATURE_ENGINE_SOURCE_FILE_SHA256,
        )
        self.assertEqual(
            FEATURE_ENGINE_SOURCE_FILE_SHA256,
            V01_FEATURE_ENGINE_SOURCE_FILE_SHA256,
        )
        self.assertEqual(MAX_PREFLIGHT_COST_USD.as_tuple().exponent, -3)
        self.assertEqual(MAX_PREFLIGHT_BILLABLE_SIZE_BYTES, 1_000_000)

    def test_child_remains_unarmed_and_workflow_only_awaits_future_authorization(self):
        gate = self.contract["future_execution_gate"]
        self.assertFalse(gate["provider_purchase_authorized"])
        self.assertFalse(gate["execution_authorization_file_present"])
        self.assertEqual(gate["exact_request_count_authorized"], 0)
        if FUTURE_AUTHORIZATION.exists():
            future_authorization = diagnostic.load_execution_authorization(
                FUTURE_AUTHORIZATION
            )
            self.assertTrue(future_authorization["provider_purchase_authorized"])
            self.assertEqual(
                future_authorization["exact_request_count_authorized"],
                1,
            )
        else:
            self.assertFalse(FUTURE_AUTHORIZATION.exists())

        # The workflow is authored concurrently with this suite.  Once present,
        # its only push trigger must be the separately authorized child file.
        if WORKFLOW.exists():
            workflow = WORKFLOW.read_text(encoding="utf-8")
            trigger = workflow.split("permissions:", 1)[0]
            future_path = (
                "research/strategy/databento-microstructure-feature-"
                "diagnostic-v0.2-execution.json"
            )
            self.assertIn("phase-3-historical-snapshot", trigger)
            self.assertIn(future_path, trigger)
            for forbidden_trigger in (
                "workflow_dispatch",
                "schedule:",
                "pull_request:",
                "repository_dispatch:",
            ):
                self.assertNotIn(forbidden_trigger, trigger)
            self.assertNotIn(
                "research/strategy/databento-microstructure-feature-"
                "diagnostic-v0.2.json",
                trigger,
            )
            self.assertNotIn("batch.submit_job", workflow)
            self.assertNotIn("live.subscribe", workflow)
            self.assertNotIn("*.dbn", workflow)
            self.assertIn("fetch-depth: 2", workflow)
            self.assertIn('assert parent == before', workflow)
            self.assertIn('assert changed == [expected]', workflow)

    def test_runner_early_gates_never_import_sdk_or_construct_client(self):
        imported: list[str] = []
        original_import = builtins.__import__

        def sentinel_import(name: str, *args: object, **kwargs: object):
            if name == "databento":
                imported.append(name)
                raise AssertionError("Databento import crossed an early gate")
            return original_import(name, *args, **kwargs)

        with tempfile.TemporaryDirectory(prefix="momentumbot-v02-runner-test-") as raw:
            directory = Path(raw)
            authorization_path = directory / "authorization.json"
            authorization_path.write_text(
                json.dumps(self.authorization, sort_keys=True),
                encoding="utf-8",
            )

            missing = directory / "missing-authorization.json"
            with patch.object(builtins, "__import__", side_effect=sentinel_import):
                with self.assertRaisesRegex(ValueError, "authorization file"):
                    runner.main(
                        [
                            "--contract",
                            str(CONTRACT),
                            "--parent-failure",
                            str(PARENT_FAILURE_AUDIT),
                            "--authorization",
                            str(missing),
                            "--output",
                            str(directory / "missing.json"),
                        ]
                    )
            self.assertEqual(imported, [])

            cases = (
                ({}, "github_actions_rerun_blocked"),
                ({"GITHUB_RUN_ATTEMPT": "2"}, "github_actions_rerun_blocked"),
                (
                    {
                        "GITHUB_RUN_ATTEMPT": "1",
                        "MOMENTUMBOT_PUSH_BEFORE": "b" * 40,
                        "DATABENTO_API_KEY": "synthetic-secret",
                    },
                    "unauthorized_push_parent",
                ),
                (
                    {
                        "GITHUB_RUN_ATTEMPT": "1",
                        "MOMENTUMBOT_PUSH_BEFORE": "a" * 40,
                    },
                    "missing_databento_api_key",
                ),
            )
            for index, (environment, expected_code) in enumerate(cases):
                output = directory / f"early-{index}.json"
                with self.subTest(expected_code=expected_code):
                    with patch.dict(os.environ, environment, clear=True):
                        with patch.object(
                            builtins,
                            "__import__",
                            side_effect=sentinel_import,
                        ):
                            with redirect_stdout(StringIO()):
                                self.assertEqual(
                                    runner.main(
                                        [
                                            "--contract",
                                            str(CONTRACT),
                                            "--parent-failure",
                                            str(PARENT_FAILURE_AUDIT),
                                            "--authorization",
                                            str(authorization_path),
                                            "--output",
                                            str(output),
                                        ]
                                    ),
                                    0,
                                )
                    report = json.loads(output.read_text(encoding="utf-8"))
                    validate_safe_failure_report(report)
                    self.assertEqual(report["timeseries_request_count"], 0)
                    self.assertEqual(
                        report["errors"][0]["safe_error_code"],
                        expected_code,
                    )
                    self.assertNotIn("synthetic-secret", output.read_text())
            self.assertEqual(imported, [])

    def test_registration_audit_binds_final_unarmed_bundle_when_present(self):
        if not REGISTRATION_AUDIT.exists():
            self.skipTest("registration audit is created after this test file stabilizes")
        audit = json.loads(REGISTRATION_AUDIT.read_text(encoding="utf-8"))
        claimed = audit["content_sha256"]
        unsigned = {
            key: value for key, value in audit.items() if key != "content_sha256"
        }
        self.assertEqual(canonical_fingerprint(unsigned), claimed)
        self.assertEqual(audit["contract"]["content_sha256"], CONTRACT_CONTENT_SHA256)
        for row in audit["bound_files"]:
            path = ROOT / row["path"]
            self.assertTrue(path.is_file(), row["path"])
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                row["file_sha256"],
                row["path"],
            )
        status = audit["execution_status"]
        self.assertFalse(status["execution_authorization_present"])
        self.assertFalse(status["provider_call_run"])
        self.assertFalse(status["databento_credit_used"])

    def test_safe_failure_object_is_closed_and_non_reconstructive(self):
        failure = SafeDiagnosticFailure(
            "normalize",
            "fill_cancel_unmatched",
            "ValueError",
        )
        self.assertEqual(
            failure.mapping(),
            {
                "failure_phase": "normalize",
                "safe_error_code": "fill_cancel_unmatched",
                "exception_kind": "ValueError",
            },
        )
        serialized = json.dumps(failure.mapping(), sort_keys=True)
        for prohibited in (
            "message",
            "signature",
            "path",
            "record_index",
            "order_id",
            "price",
            "size",
        ):
            self.assertNotIn(prohibited, serialized)
        with self.assertRaisesRegex(ValueError, "phase is not allowlisted"):
            SafeDiagnosticFailure("raw_path", "fill_cancel_unmatched")
        with self.assertRaisesRegex(ValueError, "code is not allowlisted"):
            SafeDiagnosticFailure("normalize", "raw_998877")
        with self.assertRaisesRegex(ValueError, "kind is not allowlisted"):
            SafeDiagnosticFailure(
                "normalize",
                "fill_cancel_unmatched",
                "ProviderSecretError",
            )
        self.assertIn("unclassified_fail_closed", SAFE_ERROR_CODES)

    def test_atomic_group_boundary_and_timestamp_failures_are_classified(self):
        complete = _record(
            sequence=1,
            action="R",
            side="N",
            ts_recv=100,
            flags=RUNTIME.f_last,
        )
        self.assertEqual(
            diagnostic._validated_atomic_groups([complete], runtime=RUNTIME),
            ((complete,),),
        )

        changed = [
            _record(
                sequence=1,
                action="R",
                side="N",
                ts_recv=100,
                flags=0,
            ),
            _record(
                sequence=2,
                action="N",
                side="N",
                ts_recv=101,
                flags=RUNTIME.f_last,
            ),
        ]
        with self.assertRaises(SafeDiagnosticFailure) as caught:
            diagnostic._validated_atomic_groups(changed, runtime=RUNTIME)
        self.assertEqual(
            _failure(caught.exception)[:2],
            ("atomic_group", "atomic_key_change_before_last"),
        )

        incomplete = copy.copy(changed[0])
        with self.assertRaises(SafeDiagnosticFailure) as caught:
            diagnostic._validated_atomic_groups([incomplete], runtime=RUNTIME)
        self.assertEqual(
            _failure(caught.exception)[:2],
            ("atomic_group", "atomic_eof_before_last"),
        )

        reversed_unflagged = [
            complete,
            _record(
                sequence=2,
                action="N",
                side="N",
                ts_recv=90,
                flags=RUNTIME.f_last,
            ),
        ]
        with self.assertRaises(SafeDiagnosticFailure) as caught:
            diagnostic._validated_atomic_groups(
                reversed_unflagged,
                runtime=RUNTIME,
            )
        self.assertEqual(
            _failure(caught.exception)[:2],
            ("record", "receive_time_invalid"),
        )

        reversed_flagged = copy.copy(reversed_unflagged)
        reversed_flagged[1] = copy.copy(reversed_unflagged[1])
        reversed_flagged[1].flags |= RUNTIME.f_bad_ts_recv
        groups = diagnostic._validated_atomic_groups(
            reversed_flagged,
            runtime=RUNTIME,
        )
        self.assertEqual(len(groups), 2)

    def test_fill_cancel_and_normalization_failures_have_specific_codes(self):
        matched = diagnostic._validate_and_translate_group(
            _records()[3:6],
            runtime=RUNTIME,
        )
        self.assertEqual(matched.matched_executed_removal_count, 1)

        orphan_fill = _record(
            sequence=20,
            action="F",
            side="A",
            price=102,
            size=10,
            order_id=2,
            ts_recv=4_000_000_000,
            flags=RUNTIME.f_last,
        )
        with self.assertRaises(SafeDiagnosticFailure) as caught:
            diagnostic._validate_and_translate_group(
                [orphan_fill],
                runtime=RUNTIME,
            )
        self.assertEqual(
            _failure(caught.exception)[:2],
            ("normalize", "fill_cancel_unmatched"),
        )

        unsupported = _record(
            sequence=21,
            action="X",
            side="N",
            ts_recv=4_100_000_000,
            flags=RUNTIME.f_last,
        )
        with self.assertRaises(SafeDiagnosticFailure) as caught:
            diagnostic._validate_and_translate_group(
                [unsupported],
                runtime=RUNTIME,
            )
        self.assertEqual(
            _failure(caught.exception)[:2],
            ("normalize", "unsupported_action_or_side"),
        )

        malformed_fill = copy.copy(orphan_fill)
        malformed_fill.order_id = 0
        with self.assertRaises(SafeDiagnosticFailure) as caught:
            diagnostic._validate_and_translate_group(
                [malformed_fill],
                runtime=RUNTIME,
            )
        self.assertEqual(
            _failure(caught.exception),
            ("normalize", "mutation_payload_invalid", "ValueError"),
        )

        missing = _records()
        delattr(missing[0], "channel_id")
        with self.assertRaises(SafeDiagnosticFailure) as caught:
            extract_classified_feature_diagnostic(
                missing,
                request=REQUEST,
                runtime=RUNTIME,
            )
        self.assertEqual(
            _failure(caught.exception)[:2],
            ("record", "required_field_missing"),
        )

    def test_success_is_deterministic_and_exactly_matches_frozen_v01_metrics(self):
        expected = extract_case_feature_diagnostic(
            _records(),
            request=REQUEST,
            runtime=RUNTIME,
        )
        first = extract_classified_feature_diagnostic(
            _records(),
            request=REQUEST,
            runtime=RUNTIME,
        )
        second = extract_classified_feature_diagnostic(
            _records(),
            request=REQUEST,
            runtime=RUNTIME,
        )
        self.assertEqual(first, expected)
        self.assertEqual(second, expected)
        self.assertEqual(first["record_count"], 8)
        self.assertTrue(first["independent_feature_replay_exact"])
        self.assertFalse(first["feature_threshold_selected"])
        self.assertFalse(first["runtime_authority_created"])

    def test_feature_snapshot_failure_is_classified_without_exception_text(self):
        with patch.object(
            diagnostic.CausalMicrostructureFeatureEngine,
            "snapshot",
            side_effect=ValueError(SENSITIVE_PROVIDER_DETAIL),
        ):
            with self.assertRaises(SafeDiagnosticFailure) as caught:
                extract_classified_feature_diagnostic(
                    _records(),
                    request=REQUEST,
                    runtime=RUNTIME,
                )
        self.assertEqual(
            _failure(caught.exception),
            ("feature_snapshot", "feature_snapshot_invariant", "ValueError"),
        )
        self.assertNotIn(SENSITIVE_PROVIDER_DETAIL, json.dumps(caught.exception.mapping()))

    def test_provider_file_metadata_iteration_and_replay_failures_are_one_shot(self):
        cases = (
            (
                FakeClient(timeseries_mode="provider_failure"),
                "provider_download",
                "provider_download_failed",
            ),
            (
                FakeClient(timeseries_mode="missing_file"),
                "downloaded_file",
                "download_empty",
            ),
            (
                FakeClient(timeseries_mode="empty_file"),
                "downloaded_file",
                "download_empty",
            ),
            (
                FakeClient(timeseries_mode="metadata_failure"),
                "metadata",
                "metadata_mismatch",
            ),
            (
                FakeClient(timeseries_mode="iteration_failure"),
                "record",
                "record_payload_invalid",
            ),
            (
                FakeClient(records=_unknown_cancel_records()),
                "book_replay",
                "book_state_invariant",
            ),
        )
        for client, phase, code in cases:
            with self.subTest(phase=phase, code=code):
                report = self.run_gate(client)
                validate_safe_failure_report(report)
                self.assertEqual(report["timeseries_request_count"], 1)
                self.assertEqual(len(client.timeseries.calls), 1)
                self.assertFalse(report["automatic_retry_attempted"])
                self.assertTrue(report["diagnostic_observation_complete"])
                self.assertFalse(report["feature_replay_succeeded"])
                self.assertTrue(report["safe_failure_classified"])
                self.assertEqual(report["downloads"], [])
                self.assertEqual(report["errors"][0]["failure_phase"], phase)
                self.assertEqual(report["errors"][0]["safe_error_code"], code)
                self.assertTrue(report["raw_temp_directory_empty_before_cleanup"])
                self.assertTrue(report["raw_temp_directory_removed"])
                self.assertTrue(
                    all(not path.exists() for path in client.timeseries.paths)
                )
                serialized = json.dumps(report, sort_keys=True)
                self.assertNotIn(SENSITIVE_PROVIDER_DETAIL, serialized)
                for path in client.timeseries.paths:
                    self.assertNotIn(str(path), serialized)

    def test_successful_gate_is_one_shot_and_deletes_raw_placeholder(self):
        client = FakeClient()
        report = self.run_gate(client)
        validate_safe_failure_report(report)
        self.assertTrue(report["preflight"]["preflight_passed"])
        self.assertEqual(report["timeseries_request_count"], 1)
        self.assertEqual(len(client.timeseries.calls), 1)
        self.assertEqual(len(report["downloads"]), 1)
        self.assertTrue(report["diagnostic_observation_complete"])
        self.assertTrue(report["feature_replay_succeeded"])
        self.assertFalse(report["safe_failure_classified"])
        self.assertFalse(report["automatic_retry_attempted"])
        self.assertTrue(all(not path.exists() for path in client.timeseries.paths))

    def test_preflight_query_or_budget_failure_makes_zero_timeseries_calls(self):
        cases = (
            (
                FakeClient(preflight_failure=True),
                "preflight_metadata_query_failed",
            ),
            (FakeClient(cost=0.0010001), "preflight_budget_rejected"),
            (
                FakeClient(size=MAX_PREFLIGHT_BILLABLE_SIZE_BYTES + 1),
                "preflight_budget_rejected",
            ),
        )
        for client, code in cases:
            with self.subTest(code=code):
                report = self.run_gate(client)
                validate_safe_failure_report(report)
                self.assertFalse(report["preflight"]["preflight_passed"])
                self.assertEqual(report["timeseries_request_count"], 0)
                self.assertEqual(client.timeseries.calls, [])
                self.assertEqual(report["errors"][0]["safe_error_code"], code)
                self.assertFalse(report["automatic_retry_attempted"])
                self.assertNotIn(
                    SENSITIVE_PROVIDER_DETAIL,
                    json.dumps(report, sort_keys=True),
                )

    def test_report_validator_rejects_unknown_codes_fields_messages_and_hashes(self):
        report = build_unavailable_report(
            self.contract,
            self.parent_failure,
            self.authorization,
            generated_at=GENERATED_AT,
            sdk_version="not_loaded",
            failure_phase="credential",
            safe_error_code="missing_databento_api_key",
        )
        validate_safe_failure_report(report)

        unknown_code = copy.deepcopy(report)
        unknown_code["errors"][0]["safe_error_code"] = "raw_provider_failure_998877"
        _resign(unknown_code)
        with self.assertRaisesRegex(ValueError, "code is not allowlisted"):
            validate_safe_failure_report(unknown_code)

        unknown_field = copy.deepcopy(report)
        unknown_field["errors"][0]["provider_detail"] = "998877"
        _resign(unknown_field)
        with self.assertRaisesRegex(ValueError, "unregistered field"):
            validate_safe_failure_report(unknown_field)

        for field in (
            "exception_message",
            "error_signature_sha256",
            "temporary_path",
            "raw_records",
        ):
            contaminated = copy.deepcopy(report)
            contaminated[field] = SENSITIVE_PROVIDER_DETAIL
            _resign(contaminated)
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "prohibited field"):
                    validate_safe_failure_report(contaminated)


if __name__ == "__main__":
    unittest.main()
