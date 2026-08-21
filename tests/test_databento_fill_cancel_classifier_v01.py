from __future__ import annotations

import builtins
import copy
import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import run_databento_fill_cancel_classifier_v01 as runner

from momentumbot.research import (
    databento_fill_cancel_classifier_execution_v01 as execution,
)
from momentumbot.research.databento_fill_cancel_classifier_execution_v01 import (
    EXECUTION_AUTHORIZATION_ID,
    run_fill_cancel_classifier_diagnostic,
    validate_classifier_report,
    validate_execution_authorization,
)
from momentumbot.research.databento_fill_cancel_classifier_v01 import (
    CLASSIFIER_CONTRACT_ID,
    CONTRACT_CONTENT_SHA256,
    PARENT_FAILURE_CONTENT_SHA256,
    REQUEST,
    classify_fill_cancel_structure,
    load_classifier_contract,
    load_parent_failure_audit,
)
from momentumbot.research.databento_quote import SDK_VERSION
from momentumbot.research.databento_smoke import RuntimeConstants
from momentumbot.research.microstructure_contract import canonical_fingerprint


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-fill-cancel-classifier-v0.1.json"
)
PARENT_FAILURE = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-feature-coverage-v0.1-"
    "run-32501827997-safe-failure-2026-08-21.json"
)
FUTURE_AUTHORIZATION = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-fill-cancel-classifier-v0.1-execution.json"
)
SOURCE = (
    ROOT
    / "src"
    / "momentumbot"
    / "research"
    / "databento_fill_cancel_classifier_v01.py"
)
EXECUTION_SOURCE = (
    ROOT
    / "src"
    / "momentumbot"
    / "research"
    / "databento_fill_cancel_classifier_execution_v01.py"
)
WORKFLOW = (
    ROOT
    / ".github"
    / "workflows"
    / "databento-fill-cancel-classifier-v01.yml"
)
SCRIPT = ROOT / "scripts" / "run_databento_fill_cancel_classifier_v01.py"
GENERATED_AT = datetime(2026, 8, 21, 18, tzinfo=UTC)
RUNTIME = RuntimeConstants(
    f_last=128,
    f_tob=64,
    f_snapshot=32,
    f_bad_ts_recv=8,
    undef_price=9_223_372_036_854_775_807,
)


def _record(
    *,
    action: str,
    ts_recv: int,
    flags: int,
    sequence: int = 10,
    order_id: int = 900_000_001,
    side: str = "A",
    price: int = 123_456_789_000,
    size: int = 777,
    publisher_id: int = 1,
    instrument_id: int = 7,
) -> SimpleNamespace:
    return SimpleNamespace(
        ts_event=ts_recv - 1,
        ts_recv=ts_recv,
        publisher_id=publisher_id,
        instrument_id=instrument_id,
        channel_id=0,
        sequence=sequence,
        action=action,
        side=side,
        price=price,
        size=size,
        order_id=order_id,
        flags=flags,
    )


def _event() -> list[SimpleNamespace]:
    return [
        _record(action="F", ts_recv=1_000_000_000, flags=0),
        _record(action="C", ts_recv=1_000_000_001, flags=RUNTIME.f_last),
    ]


def _authorization() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "execution_authorization_id": EXECUTION_AUTHORIZATION_ID,
        "artifact_type": (
            "explicit_one_shot_databento_fill_cancel_classifier_authorization"
        ),
        "classifier_contract_id": CLASSIFIER_CONTRACT_ID,
        "classifier_contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "authorized_push_parent_sha": "a" * 40,
        "explicit_user_authorization": (
            "Synthetic deterministic unit-test authorization; no provider call."
        ),
        "provider_purchase_authorized": True,
        "exact_request_count_authorized": 1,
        "hard_preflight_cost_ceiling_usd": "0.003",
        "hard_preflight_billable_size_ceiling_bytes": 3_000_000,
        "first_github_actions_attempt_only": True,
        "automatic_retry_authorized": False,
        "batch_or_live_endpoint_authorized": False,
        "raw_market_data_publication_authorized": False,
        "broker_or_order_change_authorized": False,
        "strategy_or_threshold_change_authorized": False,
    }
    payload["content_sha256"] = canonical_fingerprint(payload)
    return payload


class FakeStore:
    def __init__(self, records: list[SimpleNamespace]) -> None:
        self.metadata = SimpleNamespace(dataset="XNAS.ITCH", schema="mbo")
        self.records = records

    def __iter__(self):
        return iter(self.records)


class FakeMetadata:
    def __init__(self, *, cost: float = 0.0027, size: int = 2_406_208) -> None:
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
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, object]] = []

    def get_range(self, **kwargs: object) -> FakeStore:
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("licensed provider detail must not persist")
        Path(str(kwargs["path"])).write_bytes(b"synthetic DBN placeholder")
        return FakeStore(_event())


class FakeClient:
    def __init__(
        self,
        *,
        cost: float = 0.0027,
        size: int = 2_406_208,
        fail: bool = False,
    ) -> None:
        self.metadata = FakeMetadata(cost=cost, size=size)
        self.timeseries = FakeTimeseries(fail=fail)


class DatabentoFillCancelClassifierV01Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parent_failure = load_parent_failure_audit(PARENT_FAILURE)
        cls.contract = load_classifier_contract(
            CONTRACT,
            parent_failure_audit=cls.parent_failure,
        )
        cls.authorization = _authorization()
        validate_execution_authorization(cls.authorization)

    def classify(self, records: list[SimpleNamespace]) -> dict[str, object]:
        return classify_fill_cancel_structure(
            records,
            request=REQUEST,
            runtime=RUNTIME,
        )

    def test_contract_and_parent_are_hash_bound_and_unarmed(self):
        self.assertEqual(self.contract["content_sha256"], CONTRACT_CONTENT_SHA256)
        self.assertEqual(
            self.parent_failure["content_sha256"],
            PARENT_FAILURE_CONTENT_SHA256,
        )
        self.assertFalse(self.contract["provider_purchase_authorized"])
        self.assertFalse(self.contract["execution_authorization_file_present"])
        self.assertEqual(
            self.contract["future_execution_gate"]["exact_request_count_authorized"],
            0,
        )
        if FUTURE_AUTHORIZATION.exists():
            future_authorization = execution.load_execution_authorization(
                FUTURE_AUTHORIZATION
            )
            self.assertTrue(future_authorization["provider_purchase_authorized"])
            self.assertEqual(future_authorization["exact_request_count_authorized"], 1)
        else:
            self.assertFalse(FUTURE_AUTHORIZATION.exists())

    def test_exact_fill_cancel_pair_matches_all_projections(self):
        result = self.classify(_event())
        self.assertEqual(result["instrument_event_count"], 1)
        self.assertEqual(result["fill_bearing_event_count"], 1)
        self.assertEqual(result["fill_record_count"], 1)
        self.assertEqual(result["cancel_record_count_in_fill_bearing_events"], 1)
        self.assertEqual(
            set(result["projection_overlap_counts"].values()),
            {1},
        )
        self.assertEqual(
            set(result["projection_full_match_event_counts"].values()),
            {1},
        )

    def test_sequence_mismatch_isolated_by_registered_projection(self):
        records = _event()
        records[-1].sequence = 11
        result = self.classify(records)
        overlaps = result["projection_overlap_counts"]
        self.assertEqual(overlaps["exact"], 0)
        self.assertEqual(overlaps["without_sequence"], 1)
        self.assertEqual(overlaps["without_size"], 0)
        self.assertEqual(overlaps["without_sequence_and_size"], 1)
        self.assertEqual(result["multi_sequence_fill_event_count"], 1)

    def test_size_mismatch_isolated_by_registered_projection(self):
        records = _event()
        records[-1].size = 778
        overlaps = self.classify(records)["projection_overlap_counts"]
        self.assertEqual(overlaps["exact"], 0)
        self.assertEqual(overlaps["without_sequence"], 0)
        self.assertEqual(overlaps["without_size"], 1)
        self.assertEqual(overlaps["without_sequence_and_size"], 1)

    def test_order_mismatch_does_not_false_match_any_projection(self):
        records = _event()
        records[-1].order_id = 900_000_002
        result = self.classify(records)
        self.assertEqual(
            set(result["projection_overlap_counts"].values()),
            {0},
        )
        self.assertEqual(
            set(result["projection_full_match_event_counts"].values()),
            {0},
        )

    def test_fill_without_cancel_and_fill_last_are_counted(self):
        record = _record(
            action="F",
            ts_recv=1_000_000_000,
            flags=RUNTIME.f_last,
        )
        result = self.classify([record])
        self.assertEqual(result["fill_event_without_cancel_count"], 1)
        self.assertEqual(result["fill_last_record_count"], 1)
        self.assertEqual(result["cancel_record_count_in_fill_bearing_events"], 0)

    def test_interleaved_instrument_events_remain_separate(self):
        left = _event()
        right = [copy.copy(record) for record in _event()]
        for record in right:
            record.instrument_id = 8
        records = [left[0], right[0], left[1], right[1]]
        for index, record in enumerate(records, start=1):
            record.ts_recv = 1_000_000_000 + index
            record.ts_event = record.ts_recv - 1
        result = self.classify(records)
        self.assertEqual(result["instrument_event_count"], 2)
        self.assertEqual(result["fill_bearing_event_count"], 2)
        self.assertEqual(result["projection_overlap_counts"]["exact"], 2)

    def test_output_is_aggregate_only_and_source_has_no_provider_client(self):
        result = self.classify(_event())
        encoded = json.dumps(result, sort_keys=True)
        self.assertNotIn("900000001", encoded)
        self.assertNotIn("123456789000", encoded)
        self.assertFalse(result["raw_record_values_persisted"])
        self.assertFalse(result["feature_values_persisted"])
        self.assertFalse(result["runtime_authority_created"])
        source = SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("from databento", source)
        self.assertNotIn("\nimport databento", source)
        self.assertNotIn("get_range(", source)

    def run_gate(self, client: FakeClient) -> dict[str, object]:
        return run_fill_cancel_classifier_diagnostic(
            self.contract,
            self.parent_failure,
            self.authorization,
            client,
            generated_at=GENERATED_AT,
            sdk_version=SDK_VERSION,
            runtime=RUNTIME,
        )

    def test_one_shot_gate_requotes_downloads_once_and_sanitizes(self):
        client = FakeClient()
        report = self.run_gate(client)
        validate_classifier_report(report)
        self.assertEqual(len(client.metadata.calls), 2)
        self.assertEqual(len(client.timeseries.calls), 1)
        self.assertEqual(report["timeseries_request_count"], 1)
        self.assertTrue(report["diagnostic_observation_complete"])
        self.assertTrue(report["classifier_succeeded"])
        self.assertFalse(report["safe_failure_classified"])
        self.assertEqual(
            report["classification_metrics"]["projection_overlap_counts"]["exact"],
            1,
        )
        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn("900000001", rendered)
        self.assertNotIn("123456789000", rendered)
        self.assertNotIn("licensed provider detail", rendered)
        self.assertNotIn(".dbn", rendered)

    def test_budget_rejection_makes_zero_timeseries_calls(self):
        client = FakeClient(cost=0.0031)
        report = self.run_gate(client)
        validate_classifier_report(report)
        self.assertEqual(len(client.metadata.calls), 2)
        self.assertEqual(client.timeseries.calls, [])
        self.assertEqual(report["timeseries_request_count"], 0)
        self.assertFalse(report["preflight"]["preflight_passed"])
        self.assertEqual(
            report["errors"][0]["safe_error_code"],
            "preflight_budget_rejected",
        )

    def test_provider_failure_is_classified_without_retry_or_message(self):
        client = FakeClient(fail=True)
        report = self.run_gate(client)
        validate_classifier_report(report)
        self.assertEqual(len(client.timeseries.calls), 1)
        self.assertEqual(report["timeseries_request_count"], 1)
        self.assertFalse(report["classifier_succeeded"])
        self.assertTrue(report["safe_failure_classified"])
        self.assertEqual(
            report["errors"][0]["safe_error_code"],
            "provider_download_failed",
        )
        self.assertNotIn("licensed provider detail", json.dumps(report))
        self.assertFalse(report["automatic_retry_attempted"])

    def test_authorization_overclaim_and_bad_parent_fail_closed(self):
        overclaim = copy.deepcopy(self.authorization)
        overclaim["exact_request_count_authorized"] = 2
        overclaim["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in overclaim.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "request_count"):
            validate_execution_authorization(overclaim)

        bad_parent = copy.deepcopy(self.authorization)
        bad_parent["authorized_push_parent_sha"] = "not-a-sha"
        bad_parent["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in bad_parent.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "parent SHA"):
            validate_execution_authorization(bad_parent)

    def test_runner_rejects_absent_authorization_before_sdk_import(self):
        imported = []
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            imported.append(name)
            if name == "databento" or name.startswith("databento."):
                raise AssertionError("provider SDK imported before authorization")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=guarded_import):
            with self.assertRaisesRegex(ValueError, "authorization file is required"):
                runner.main(
                    [
                        "--authorization",
                        str(ROOT / "missing-fill-cancel-authorization.json"),
                        "--output",
                        str(ROOT / "unused-fill-cancel-report.json"),
                    ]
                )
        self.assertFalse(any(name == "databento" for name in imported))

    def test_workflow_is_unarmed_and_parent_bound(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        script = SCRIPT.read_text(encoding="utf-8")
        trigger = workflow.split("permissions:", 1)[0]
        self.assertIn(
            "databento-microstructure-fill-cancel-classifier-v0.1-execution.json",
            trigger,
        )
        self.assertNotIn(
            "databento-microstructure-fill-cancel-classifier-v0.1.json",
            trigger,
        )
        self.assertNotIn("workflow_dispatch", workflow)
        self.assertNotIn("*.dbn", workflow)
        self.assertNotIn("batch.submit_job", workflow)
        self.assertNotIn("live.subscribe", workflow)
        self.assertIn("databento==0.83.0", workflow)
        self.assertIn('run_attempt = os.getenv("GITHUB_RUN_ATTEMPT")', script)
        self.assertIn('authorization["authorized_push_parent_sha"]', script)
        self.assertTrue(EXECUTION_SOURCE.is_file())


if __name__ == "__main__":
    unittest.main()
