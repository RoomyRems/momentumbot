from __future__ import annotations

import builtins
import copy
import hashlib
import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import run_databento_microstructure_features_v03 as runner

from momentumbot.research import databento_feature_diagnostic_v03 as diagnostic
from momentumbot.research.databento_feature_diagnostic_v01 import (
    extract_case_feature_diagnostic,
)
from momentumbot.research.databento_feature_diagnostic_v03 import (
    CONTRACT_CONTENT_SHA256,
    DIAGNOSTIC_CONTRACT_ID,
    EXECUTION_AUTHORIZATION_ID,
    PARENT_FAILURE_CONTENT_SHA256,
    REQUEST,
    SafeDiagnosticFailure,
    extract_repaired_feature_diagnostic,
    iter_instrument_mbo_events,
    load_parent_failure_audit,
    load_repair_contract,
    run_instrument_event_repair_diagnostic,
    translate_xnas_instrument_event,
    validate_execution_authorization,
    validate_repair_report,
)
from momentumbot.research.databento_quote import SDK_VERSION
from momentumbot.research.microstructure_contract import (
    DepthAction,
    canonical_fingerprint,
)
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
    / "databento-microstructure-feature-diagnostic-v0.3.json"
)
PARENT_FAILURE_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-feature-diagnostic-v0.2-"
    "run-32478204001-failure-2026-08-21.json"
)
FUTURE_AUTHORIZATION = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-feature-diagnostic-v0.3-execution.json"
)
V01_ADAPTER = (
    ROOT
    / "src"
    / "momentumbot"
    / "research"
    / "databento_feature_diagnostic_v01.py"
)
V02_CLASSIFIER = (
    ROOT
    / "src"
    / "momentumbot"
    / "research"
    / "databento_feature_diagnostic_v02.py"
)
FEATURE_ENGINE = ROOT / "src" / "momentumbot" / "research" / "microstructure_features.py"
WORKFLOW = (
    ROOT
    / ".github"
    / "workflows"
    / "databento-microstructure-features-v03.yml"
)
SCRIPT = ROOT / "scripts" / "run_databento_microstructure_features_v03.py"
REGISTRATION_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-feature-diagnostic-v0.3-registration-2026-08-21.json"
)
GENERATED_AT = datetime(2026, 8, 21, 13, tzinfo=UTC)
SENSITIVE_PROVIDER_DETAIL = "licensed provider detail 998877"


def _authorization() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "execution_authorization_id": EXECUTION_AUTHORIZATION_ID,
        "artifact_type": (
            "explicit_one_shot_databento_instrument_event_repair_authorization"
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


class FakeStore:
    def __init__(
        self,
        records: list[FakeRecord],
        *,
        dataset: str = "XNAS.ITCH",
        schema: str = "mbo",
    ) -> None:
        self.records = records
        self.metadata = SimpleNamespace(dataset=dataset, schema=schema)

    def __iter__(self):
        return iter(self.records)


class FakeMetadata:
    def __init__(self, *, cost: float = 0.0005, size: int = 117_040) -> None:
        self.cost = cost
        self.size = size
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get_billable_size(self, **kwargs: object) -> int:
        self.calls.append(("get_billable_size", kwargs))
        return self.size

    def get_cost(self, **kwargs: object) -> float:
        self.calls.append(("get_cost", kwargs))
        return self.cost


class FakeTimeseries:
    def __init__(
        self,
        *,
        records: list[FakeRecord] | None = None,
        mode: str = "success",
    ) -> None:
        self.records = _records() if records is None else records
        self.mode = mode
        self.calls: list[dict[str, object]] = []
        self.paths: list[Path] = []

    def get_range(self, **kwargs: object) -> FakeStore:
        self.calls.append(kwargs)
        path = Path(str(kwargs["path"]))
        self.paths.append(path)
        if self.mode == "provider_failure":
            raise RuntimeError(SENSITIVE_PROVIDER_DETAIL)
        if self.mode != "missing_file":
            path.write_bytes(b"synthetic DBN placeholder, not provider data")
        if self.mode == "bad_metadata":
            return FakeStore(self.records, dataset="wrong.dataset")
        return FakeStore(self.records)


class FakeClient:
    def __init__(
        self,
        *,
        cost: float = 0.0005,
        size: int = 117_040,
        records: list[FakeRecord] | None = None,
        mode: str = "success",
    ) -> None:
        self.metadata = FakeMetadata(cost=cost, size=size)
        self.timeseries = FakeTimeseries(records=records, mode=mode)


def _with_scope(record: FakeRecord, publisher_id: int, instrument_id: int) -> FakeRecord:
    clone = copy.copy(record)
    clone.publisher_id = publisher_id
    clone.instrument_id = instrument_id
    return clone


def _mixed_sequence_event() -> list[FakeRecord]:
    return [
        _record(
            sequence=0,
            action="R",
            side="N",
            ts_recv=1_000_000_000,
            flags=0,
        ),
        _record(
            sequence=1,
            action="A",
            side="B",
            price=100,
            size=100,
            order_id=1,
            ts_recv=1_100_000_000,
            flags=0,
        ),
        _record(
            sequence=1,
            action="A",
            side="A",
            price=102,
            size=100,
            order_id=2,
            ts_recv=1_200_000_000,
            flags=RUNTIME.f_last,
        ),
    ]


class DatabentoFeatureDiagnosticV03Tests(unittest.TestCase):
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
        return run_instrument_event_repair_diagnostic(
            self.contract,
            self.parent_failure,
            self.authorization,
            client,
            generated_at=GENERATED_AT,
            sdk_version=SDK_VERSION,
            runtime=RUNTIME,
        )

    def test_contract_and_parent_failure_are_hash_bound_and_unarmed(self):
        self.assertEqual(self.contract["content_sha256"], CONTRACT_CONTENT_SHA256)
        self.assertEqual(
            self.parent_failure["content_sha256"],
            PARENT_FAILURE_CONTENT_SHA256,
        )
        self.assertFalse(
            self.contract["future_execution_gate"]["provider_purchase_authorized"]
        )
        self.assertFalse(
            self.contract["future_execution_gate"][
                "execution_authorization_file_present"
            ]
        )
        self.assertFalse(FUTURE_AUTHORIZATION.exists())

    def test_frozen_parent_sources_and_feature_engine_are_unchanged(self):
        self.assertEqual(
            hashlib.sha256(V01_ADAPTER.read_bytes()).hexdigest(),
            diagnostic.V01_ADAPTER_FILE_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(V02_CLASSIFIER.read_bytes()).hexdigest(),
            diagnostic.V02_CLASSIFIER_FILE_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(FEATURE_ENGINE.read_bytes()).hexdigest(),
            diagnostic.FEATURE_ENGINE_SOURCE_FILE_SHA256,
        )

    def test_sequence_change_before_f_last_is_one_instrument_event(self):
        records = _mixed_sequence_event()
        events = tuple(iter_instrument_mbo_events(records, runtime=RUNTIME))
        self.assertEqual(events, (tuple(records),))
        translated = translate_xnas_instrument_event(
            events[0],
            symbol="INTJ",
            runtime=RUNTIME,
        )
        self.assertEqual(len(translated.depth_events), 3)
        self.assertEqual(
            tuple(event.sequence for event in translated.depth_events),
            (0, 1, 1),
        )

    def test_interleaved_scopes_close_independently(self):
        left = _mixed_sequence_event()
        right = [
            _with_scope(record, 2, 8) for record in _mixed_sequence_event()
        ]
        records = [left[0], right[0], right[1], left[1], right[2], left[2]]
        for index, record in enumerate(records, start=1):
            record.ts_recv = index * 100
            record.ts_event = record.ts_recv - 1
        events = tuple(iter_instrument_mbo_events(records, runtime=RUNTIME))
        self.assertEqual(len(events), 2)
        self.assertEqual(
            tuple((event[0].publisher_id, event[0].instrument_id) for event in events),
            ((2, 8), (1, 7)),
        )
        self.assertEqual(tuple(record.sequence for record in events[0]), (0, 1, 1))
        self.assertEqual(tuple(record.sequence for record in events[1]), (0, 1, 1))

    def test_incomplete_scope_fails_closed_even_when_another_scope_completes(self):
        incomplete = _mixed_sequence_event()[0]
        complete = _with_scope(
            _record(
                sequence=1,
                action="N",
                side="N",
                ts_recv=2_000_000_000,
                flags=RUNTIME.f_last,
            ),
            2,
            8,
        )
        with self.assertRaises(SafeDiagnosticFailure) as caught:
            tuple(iter_instrument_mbo_events([incomplete, complete], runtime=RUNTIME))
        self.assertEqual(
            (caught.exception.phase, caught.exception.code),
            ("atomic_group", "atomic_eof_before_last"),
        )

    def test_fill_cancel_match_is_sequence_scoped(self):
        matched = translate_xnas_instrument_event(
            _records()[3:6],
            symbol="INTJ",
            runtime=RUNTIME,
        )
        self.assertEqual(matched.matched_executed_removal_count, 1)
        self.assertEqual(matched.depth_events[-1].action, DepthAction.FILL)

        crossed = [copy.copy(record) for record in _records()[3:6]]
        crossed[-1].sequence = 11
        with self.assertRaises(SafeDiagnosticFailure) as caught:
            translate_xnas_instrument_event(
                crossed,
                symbol="INTJ",
                runtime=RUNTIME,
            )
        self.assertEqual(
            (caught.exception.phase, caught.exception.code),
            ("normalize", "fill_cancel_unmatched"),
        )

    def test_frozen_valid_fixture_preserves_all_parent_metrics(self):
        parent = extract_case_feature_diagnostic(
            _records(),
            request=REQUEST,
            runtime=RUNTIME,
        )
        repaired = extract_repaired_feature_diagnostic(
            _records(),
            request=REQUEST,
            runtime=RUNTIME,
        )
        converted = dict(repaired)
        converted["atomic_group_count"] = converted.pop("instrument_event_count")
        converted.pop("event_scope_count")
        converted.pop("within_event_sequence_transition_count")
        self.assertEqual(converted, parent)

    def test_mixed_sequence_repair_replays_without_thresholds(self):
        metrics = extract_repaired_feature_diagnostic(
            _mixed_sequence_event(),
            request=REQUEST,
            runtime=RUNTIME,
        )
        self.assertEqual(metrics["event_scope_count"], 1)
        self.assertEqual(metrics["within_event_sequence_transition_count"], 1)
        self.assertTrue(metrics["independent_feature_replay_exact"])
        self.assertFalse(metrics["feature_threshold_selected"])
        self.assertFalse(metrics["feature_horizon_selected"])
        self.assertFalse(metrics["runtime_authority_created"])

    def test_interleaved_scope_feature_engines_do_not_cross_contaminate(self):
        left = _mixed_sequence_event()
        right = [
            _with_scope(record, 2, 8) for record in _mixed_sequence_event()
        ]
        records = [left[0], right[0], left[1], right[1], left[2], right[2]]
        for index, record in enumerate(records, start=1):
            record.ts_recv = index * 1_000_000_000
            record.ts_event = record.ts_recv - 1
        metrics = extract_repaired_feature_diagnostic(
            records,
            request=REQUEST,
            runtime=RUNTIME,
        )
        self.assertEqual(metrics["event_scope_count"], 2)
        self.assertEqual(metrics["instrument_event_count"], 2)
        self.assertEqual(metrics["sampled_snapshot_count"], 2)
        self.assertTrue(metrics["independent_feature_replay_exact"])

    def test_preflight_budget_failure_makes_zero_timeseries_calls(self):
        for client in (
            FakeClient(cost=0.0010001),
            FakeClient(size=1_000_001),
        ):
            with self.subTest(client=client):
                report = self.run_gate(client)
                validate_repair_report(report)
                self.assertFalse(report["preflight"]["preflight_passed"])
                self.assertEqual(report["timeseries_request_count"], 0)
                self.assertEqual(client.timeseries.calls, [])

    def test_synthetic_success_is_one_request_and_cleans_raw_file(self):
        client = FakeClient(records=_mixed_sequence_event())
        report = self.run_gate(client)
        validate_repair_report(report)
        self.assertTrue(report["feature_replay_succeeded"])
        self.assertFalse(report["safe_failure_classified"])
        self.assertEqual(report["timeseries_request_count"], 1)
        self.assertEqual(len(client.timeseries.calls), 1)
        self.assertTrue(all(not path.exists() for path in client.timeseries.paths))

    def test_provider_failure_is_sanitized_without_retry(self):
        client = FakeClient(mode="provider_failure")
        report = self.run_gate(client)
        validate_repair_report(report)
        self.assertFalse(report["feature_replay_succeeded"])
        self.assertTrue(report["safe_failure_classified"])
        self.assertEqual(report["timeseries_request_count"], 1)
        self.assertEqual(len(client.timeseries.calls), 1)
        self.assertNotIn(SENSITIVE_PROVIDER_DETAIL, json.dumps(report, sort_keys=True))
        self.assertFalse(report["automatic_retry_attempted"])

    def test_report_validator_rejects_raw_values_and_unlisted_failure_phase(self):
        report = self.run_gate(FakeClient(records=_mixed_sequence_event()))
        contaminated = copy.deepcopy(report)
        contaminated["feature_snapshots"] = [{"price": 102}]
        contaminated["content_sha256"] = canonical_fingerprint(
            {
                key: value
                for key, value in contaminated.items()
                if key != "content_sha256"
            }
        )
        with self.assertRaisesRegex(ValueError, "prohibited field"):
            validate_repair_report(contaminated)

        failure = self.run_gate(FakeClient(mode="provider_failure"))
        failure["errors"][0]["failure_phase"] = "raw_provider_path"
        failure["content_sha256"] = canonical_fingerprint(
            {
                key: value for key, value in failure.items() if key != "content_sha256"
            }
        )
        with self.assertRaisesRegex(ValueError, "phase is not allowlisted"):
            validate_repair_report(failure)

    def test_authorization_validation_is_strict(self):
        invalid = copy.deepcopy(self.authorization)
        invalid["automatic_retry_authorized"] = True
        invalid["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in invalid.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "automatic_retry_authorized"):
            validate_execution_authorization(invalid)

    def test_unarmed_bundle_does_not_import_databento(self):
        real_import = builtins.__import__

        def guarded_import(name: str, *args: object, **kwargs: object):
            if name == "databento" or name.startswith("databento."):
                raise AssertionError("unarmed v0.3 imported provider SDK")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=guarded_import):
            parent = load_parent_failure_audit(PARENT_FAILURE_AUDIT)
            contract = load_repair_contract(
                CONTRACT,
                parent_failure_audit=parent,
            )
        self.assertEqual(contract["content_sha256"], CONTRACT_CONTENT_SHA256)

    def test_runner_requires_future_authorization_before_provider_import(self):
        with patch("builtins.__import__", wraps=builtins.__import__) as imported:
            with self.assertRaisesRegex(ValueError, "v0.3 execution authorization"):
                runner.main(
                    [
                        "--authorization",
                        str(FUTURE_AUTHORIZATION),
                        "--output",
                        str(ROOT / "unused-v0.3-report.json"),
                    ]
                )
        self.assertFalse(
            any(
                call.args
                and isinstance(call.args[0], str)
                and (
                    call.args[0] == "databento"
                    or call.args[0].startswith("databento.")
                )
                for call in imported.mock_calls
            )
        )

    def test_workflow_is_disjoint_from_unarmed_bundle_and_one_shot(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        script = SCRIPT.read_text(encoding="utf-8")
        trigger = workflow.split("permissions:", 1)[0]
        self.assertIn(
            "databento-microstructure-feature-diagnostic-v0.3-execution.json",
            trigger,
        )
        self.assertNotIn(
            "databento-microstructure-feature-diagnostic-v0.3.json",
            trigger,
        )
        self.assertNotIn("workflow_dispatch", workflow)
        self.assertNotIn("*.dbn", workflow)
        self.assertNotIn("batch.submit_job", workflow)
        self.assertNotIn("live.subscribe", workflow)
        self.assertIn("databento==0.83.0", workflow)
        self.assertIn('run_attempt = os.getenv("GITHUB_RUN_ATTEMPT")', script)
        self.assertIn('authorization["authorized_push_parent_sha"]', script)
        self.assertFalse(FUTURE_AUTHORIZATION.exists())

    def test_registration_audit_binds_the_unarmed_repair_bundle(self):
        audit = json.loads(REGISTRATION_AUDIT.read_text(encoding="utf-8"))
        claimed = audit["content_sha256"]
        unsigned = {
            key: value for key, value in audit.items() if key != "content_sha256"
        }
        self.assertEqual(canonical_fingerprint(unsigned), claimed)
        self.assertEqual(
            audit["contract"]["content_sha256"],
            CONTRACT_CONTENT_SHA256,
        )
        for row in audit["bound_files"]:
            path = ROOT / row["path"]
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                row["file_sha256"],
            )
        self.assertFalse(
            audit["execution_status"]["execution_authorization_present"]
        )
        self.assertFalse(audit["execution_status"]["provider_call_run"])
        self.assertFalse(audit["execution_status"]["databento_credit_used"])


if __name__ == "__main__":
    unittest.main()
