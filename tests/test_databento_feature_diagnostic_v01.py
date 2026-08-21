from __future__ import annotations

import copy
import hashlib
import json
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from momentumbot.research.databento_feature_diagnostic_v01 import (
    CONTRACT_CONTENT_SHA256,
    DIAGNOSTIC_CONTRACT_ID,
    EXECUTION_AUTHORIZATION_ID,
    FEATURE_CASES,
    FEATURE_ENGINE_SOURCE_FILE_SHA256,
    MAX_PREFLIGHT_BILLABLE_SIZE_BYTES,
    MAX_PREFLIGHT_COST_USD,
    REQUESTS,
    RuntimeConstants,
    build_unavailable_report,
    extract_case_feature_diagnostic,
    iter_atomic_mbo_groups,
    load_diagnostic_contract,
    load_execution_authorization,
    run_feature_diagnostic,
    translate_xnas_atomic_group,
    validate_execution_authorization,
    validate_feature_diagnostic_report,
)
from momentumbot.research.databento_quote import SDK_VERSION
from momentumbot.research.microstructure_contract import (
    AggressorSide,
    CanonicalDepthEvent,
    CanonicalTapeEvent,
    DepthAction,
    canonical_fingerprint,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-feature-diagnostic-v0.1.json"
)
FUTURE_AUTHORIZATION = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-feature-diagnostic-v0.1-execution.json"
)
EXECUTION_AUTHORIZATION_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-feature-diagnostic-v0.1-execution-authorization-2026-08-20.json"
)
FEATURE_ENGINE = ROOT / "src" / "momentumbot" / "research" / "microstructure_features.py"
REGISTRATION_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-feature-diagnostic-v0.1-registration-2026-08-20.json"
)
WORKFLOW = (
    ROOT
    / ".github"
    / "workflows"
    / "databento-microstructure-features-v01.yml"
)
SCRIPT = ROOT / "scripts" / "run_databento_microstructure_features_v01.py"
PUBLISHED_AUTHORIZATION_PARENT_SHA = "c20f20213c75766fd72d60a3b18f75eb51242250"
PUBLISHED_AUTHORIZATION_PARENT_TREE = "99fcffc96e6bc23780b447f7ddb3c850774705ea"
UNARMED_REGISTRATION_CONTENT_SHA256 = (
    "1ef32200d60c744420743c831c5af66a0bafbdfff2e6a269ee5ad5dd209eeae7"
)
UNARMED_TEST_FILE_SHA256 = (
    "58100c19ab6e1126d89ac9d16143d21f13d6f43cd350544b1e734b9174e1b802"
)
RUNTIME = RuntimeConstants(
    f_last=128,
    f_tob=64,
    f_snapshot=32,
    f_bad_ts_recv=8,
    undef_price=9_223_372_036_854_775_807,
)


class FakeRecord:
    def __init__(self, **kwargs: object) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeStore:
    def __init__(self, records: list[FakeRecord]) -> None:
        self.metadata = SimpleNamespace(dataset="XNAS.ITCH", schema="mbo")
        self.records = records

    def __iter__(self):
        return iter(self.records)


def _record(
    *,
    sequence: int,
    action: str,
    side: str,
    ts_recv: int,
    flags: int,
    price: int | None = None,
    size: int = 0,
    order_id: int = 0,
) -> FakeRecord:
    return FakeRecord(
        ts_event=ts_recv - 10,
        ts_recv=ts_recv,
        publisher_id=1,
        instrument_id=7,
        channel_id=0,
        sequence=sequence,
        action=action,
        side=side,
        price=RUNTIME.undef_price if price is None else price,
        size=size,
        order_id=order_id,
        flags=flags,
    )


def _records() -> list[FakeRecord]:
    snapshot = RUNTIME.f_snapshot
    return [
        _record(
            sequence=0,
            action="R",
            side="N",
            ts_recv=1_000_000_000,
            flags=snapshot,
        ),
        _record(
            sequence=0,
            action="A",
            side="B",
            price=100,
            size=1_000,
            order_id=1,
            ts_recv=1_100_000_000,
            flags=snapshot,
        ),
        _record(
            sequence=0,
            action="A",
            side="A",
            price=102,
            size=800,
            order_id=2,
            ts_recv=1_200_000_000,
            flags=snapshot | RUNTIME.f_last,
        ),
        _record(
            sequence=10,
            action="T",
            side="B",
            price=102,
            size=200,
            ts_recv=2_100_000_000,
            flags=0,
        ),
        _record(
            sequence=10,
            action="F",
            side="A",
            price=102,
            size=200,
            order_id=2,
            ts_recv=2_200_000_000,
            flags=0,
        ),
        _record(
            sequence=10,
            action="C",
            side="A",
            price=102,
            size=200,
            order_id=2,
            ts_recv=2_300_000_000,
            flags=RUNTIME.f_last,
        ),
        _record(
            sequence=11,
            action="A",
            side="A",
            price=102,
            size=200,
            order_id=3,
            ts_recv=2_400_000_000,
            flags=RUNTIME.f_last,
        ),
        _record(
            sequence=12,
            action="N",
            side="N",
            ts_recv=3_200_000_000,
            flags=RUNTIME.f_last,
        ),
    ]


def _authorization() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "execution_authorization_id": EXECUTION_AUTHORIZATION_ID,
        "artifact_type": "explicit_one_shot_databento_feature_diagnostic_authorization",
        "diagnostic_contract_id": DIAGNOSTIC_CONTRACT_ID,
        "diagnostic_contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "authorized_push_parent_sha": "1" * 40,
        "explicit_user_authorization": "Synthetic deterministic test authorization only.",
        "provider_purchase_authorized": True,
        "exact_request_count_authorized": 4,
        "hard_preflight_cost_ceiling_usd": "0.08",
        "hard_preflight_billable_size_ceiling_bytes": 80_000_000,
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
        per_request_cost: float = 0.001,
        per_request_size: int = 100,
    ) -> None:
        self.per_request_cost = per_request_cost
        self.per_request_size = per_request_size
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get_billable_size(self, **kwargs: object) -> int:
        self.calls.append(("get_billable_size", kwargs))
        return self.per_request_size

    def get_cost(self, **kwargs: object) -> float:
        self.calls.append(("get_cost", kwargs))
        return self.per_request_cost


class FakeTimeseries:
    def __init__(
        self,
        *,
        fail_on_call: int | None = None,
        malformed: bool = False,
    ) -> None:
        self.fail_on_call = fail_on_call
        self.malformed = malformed
        self.calls: list[dict[str, object]] = []
        self.paths: list[Path] = []

    def get_range(self, **kwargs: object) -> FakeStore:
        self.calls.append(kwargs)
        path = Path(str(kwargs["path"]))
        self.paths.append(path)
        path.write_bytes(f"fake-mbo-{len(self.calls)}".encode())
        if self.fail_on_call == len(self.calls):
            raise RuntimeError("provider detail must not enter report")
        records = _records()
        if self.malformed:
            delattr(records[0], "channel_id")
        return FakeStore(records)


class FakeClient:
    def __init__(
        self,
        *,
        per_request_cost: float = 0.001,
        per_request_size: int = 100,
        fail_on_call: int | None = None,
        malformed: bool = False,
    ) -> None:
        self.metadata = FakeMetadata(
            per_request_cost=per_request_cost,
            per_request_size=per_request_size,
        )
        self.timeseries = FakeTimeseries(
            fail_on_call=fail_on_call,
            malformed=malformed,
        )


class DatabentoFeatureDiagnosticV01Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load_diagnostic_contract(CONTRACT)
        cls.authorization = _authorization()
        validate_execution_authorization(cls.authorization)

    def run_gate(self, client: FakeClient) -> dict[str, object]:
        return run_feature_diagnostic(
            self.contract,
            self.authorization,
            client,
            generated_at=datetime(2026, 8, 20, 20, tzinfo=UTC),
            sdk_version=SDK_VERSION,
            runtime=RUNTIME,
        )

    def test_contract_is_hash_bound_and_unarmed(self):
        self.assertEqual(self.contract["content_sha256"], CONTRACT_CONTENT_SHA256)
        unsigned = {
            key: value
            for key, value in self.contract.items()
            if key != "content_sha256"
        }
        self.assertEqual(canonical_fingerprint(unsigned), CONTRACT_CONTENT_SHA256)
        self.assertEqual(
            hashlib.sha256(FEATURE_ENGINE.read_bytes()).hexdigest(),
            FEATURE_ENGINE_SOURCE_FILE_SHA256,
        )
        gate = self.contract["execution_authorization_gate"]
        self.assertFalse(gate["provider_purchase_authorized"])
        self.assertFalse(gate["execution_authorization_file_present"])
        self.assertTrue(FUTURE_AUTHORIZATION.exists())

    def test_separate_execution_child_is_hash_bound_to_published_parent(self):
        authorization = load_execution_authorization(FUTURE_AUTHORIZATION)
        self.assertEqual(
            authorization["authorized_push_parent_sha"],
            PUBLISHED_AUTHORIZATION_PARENT_SHA,
        )
        self.assertTrue(authorization["provider_purchase_authorized"])
        self.assertEqual(authorization["exact_request_count_authorized"], 4)
        self.assertEqual(authorization["hard_preflight_cost_ceiling_usd"], "0.08")
        self.assertEqual(
            authorization["hard_preflight_billable_size_ceiling_bytes"],
            80_000_000,
        )

        audit = json.loads(
            EXECUTION_AUTHORIZATION_AUDIT.read_text(encoding="utf-8")
        )
        claimed = audit["content_sha256"]
        unsigned = {key: value for key, value in audit.items() if key != "content_sha256"}
        self.assertEqual(canonical_fingerprint(unsigned), claimed)
        self.assertEqual(
            audit["published_parent"]["commit_sha"],
            PUBLISHED_AUTHORIZATION_PARENT_SHA,
        )
        self.assertEqual(
            audit["published_parent"]["tree_sha"],
            PUBLISHED_AUTHORIZATION_PARENT_TREE,
        )
        self.assertEqual(
            audit["frozen_registration"]["content_sha256"],
            UNARMED_REGISTRATION_CONTENT_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(FUTURE_AUTHORIZATION.read_bytes()).hexdigest(),
            audit["execution_authorization"]["file_sha256"],
        )
        self.assertFalse(audit["prepublication_status"]["provider_call_run"])
        self.assertFalse(audit["prepublication_status"]["databento_credit_used"])

    def test_exact_four_mbo_requests_and_ceilings_are_frozen(self):
        self.assertEqual(len(REQUESTS), 4)
        self.assertEqual(
            tuple((request.trading_date, request.symbol) for request in REQUESTS),
            FEATURE_CASES,
        )
        self.assertEqual({request.schema for request in REQUESTS}, {"mbo"})
        self.assertEqual(MAX_PREFLIGHT_COST_USD, Decimal("0.08"))
        self.assertEqual(MAX_PREFLIGHT_BILLABLE_SIZE_BYTES, 80_000_000)

    def test_xnas_trade_fill_cancel_is_ordered_and_classified(self):
        group = translate_xnas_atomic_group(
            _records()[3:6],
            symbol="INTJ",
            runtime=RUNTIME,
        )
        self.assertEqual(
            tuple(type(event) for event in group.ordered_events),
            (CanonicalDepthEvent, CanonicalTapeEvent, CanonicalDepthEvent),
        )
        self.assertEqual(
            tuple(event.ts_recv_ns for event in group.ordered_events),
            (2_100_000_000, 2_100_000_000, 2_300_000_000),
        )
        self.assertEqual(group.depth_events[-1].action, DepthAction.FILL)
        self.assertEqual(group.tape_events[0].aggressor_side, AggressorSide.BUY)
        self.assertEqual(group.matched_executed_removal_count, 1)
        self.assertEqual(group.ignored_fill_marker_count, 1)

        unknown = translate_xnas_atomic_group(
            [
                _record(
                    sequence=20,
                    action="T",
                    side="N",
                    price=101,
                    size=10,
                    ts_recv=4_000_000_000,
                    flags=RUNTIME.f_last,
                )
            ],
            symbol="INTJ",
            runtime=RUNTIME,
        )
        self.assertEqual(
            unknown.tape_events[0].aggressor_side,
            AggressorSide.UNKNOWN,
        )

    def test_atomic_group_failures_are_closed(self):
        orphan = _record(
            sequence=20,
            action="F",
            side="A",
            price=102,
            size=1,
            order_id=2,
            ts_recv=4_000_000_000,
            flags=RUNTIME.f_last,
        )
        with self.assertRaisesRegex(ValueError, "no matching Cancel"):
            translate_xnas_atomic_group([orphan], symbol="INTJ", runtime=RUNTIME)

        incomplete = _record(
            sequence=21,
            action="N",
            side="N",
            ts_recv=4_100_000_000,
            flags=0,
        )
        with self.assertRaisesRegex(ValueError, "ended before F_LAST"):
            tuple(iter_atomic_mbo_groups([incomplete], runtime=RUNTIME))

    def test_threshold_free_feature_extraction_is_deterministic(self):
        left = extract_case_feature_diagnostic(
            _records(),
            request=REQUESTS[0],
            runtime=RUNTIME,
        )
        right = extract_case_feature_diagnostic(
            _records(),
            request=REQUESTS[0],
            runtime=RUNTIME,
        )
        self.assertEqual(left, right)
        self.assertEqual(left["record_count"], 8)
        self.assertEqual(left["matched_executed_removal_count"], 1)
        self.assertEqual(left["ignored_fill_marker_count"], 1)
        self.assertGreater(left["sampled_snapshot_count"], 0)
        self.assertEqual(left["book_available_count"], left["sampled_snapshot_count"])
        self.assertTrue(left["independent_feature_replay_exact"])
        self.assertFalse(left["feature_threshold_selected"])
        self.assertFalse(left["feature_horizon_selected"])
        self.assertFalse(left["runtime_authority_created"])

    def test_preflight_budget_failure_makes_zero_timeseries_calls(self):
        for client in (
            FakeClient(per_request_cost=0.0200001),
            FakeClient(per_request_size=20_000_001),
        ):
            with self.subTest(client=client):
                report = self.run_gate(client)
                validate_feature_diagnostic_report(report)
                self.assertFalse(report["preflight"]["preflight_passed"])
                self.assertEqual(report["timeseries_request_count"], 0)
                self.assertEqual(client.timeseries.calls, [])

    def test_all_four_synthetic_streams_pass_and_delete_raw_files(self):
        client = FakeClient()
        report = self.run_gate(client)
        validate_feature_diagnostic_report(report)
        self.assertTrue(report["preflight"]["preflight_passed"])
        self.assertEqual(report["timeseries_request_count"], 4)
        self.assertEqual(len(report["downloads"]), 4)
        self.assertTrue(report["g3_feature_diagnostic_passed"])
        self.assertTrue(
            all(
                row["metrics"]["independent_feature_replay_exact"]
                for row in report["downloads"]
            )
        )
        self.assertTrue(all(not path.exists() for path in client.timeseries.paths))
        self.assertFalse(report["runtime_authority_created"])
        self.assertFalse(report["policy_promotion_eligible"])

    def test_provider_or_parser_failure_is_sanitized_without_retry(self):
        for client in (
            FakeClient(fail_on_call=2),
            FakeClient(malformed=True),
        ):
            with self.subTest(client=client):
                report = self.run_gate(client)
                validate_feature_diagnostic_report(report)
                self.assertLess(report["timeseries_request_count"], 4)
                self.assertFalse(report["automatic_retry_attempted"])
                self.assertFalse(report["g3_feature_diagnostic_passed"])
                self.assertNotIn("provider detail", json.dumps(report, sort_keys=True))
                self.assertTrue(all(not path.exists() for path in client.timeseries.paths))

    def test_unavailable_report_and_sanitization_boundary(self):
        report = build_unavailable_report(
            self.contract,
            self.authorization,
            generated_at=datetime(2026, 8, 20, 20, tzinfo=UTC),
            sdk_version="not_loaded",
            error_stage="credential",
            error_kind="missing_DATABENTO_API_KEY",
        )
        validate_feature_diagnostic_report(report)
        self.assertEqual(report["timeseries_request_count"], 0)

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
            validate_feature_diagnostic_report(contaminated)

    def test_registration_audit_binds_the_inert_bundle(self):
        audit = json.loads(REGISTRATION_AUDIT.read_text(encoding="utf-8"))
        claimed = audit["content_sha256"]
        unsigned = {key: value for key, value in audit.items() if key != "content_sha256"}
        self.assertEqual(canonical_fingerprint(unsigned), claimed)
        self.assertEqual(audit["contract"]["content_sha256"], CONTRACT_CONTENT_SHA256)
        for row in audit["bound_files"]:
            if row["path"] == "tests/test_databento_feature_diagnostic_v01.py":
                self.assertEqual(row["file_sha256"], UNARMED_TEST_FILE_SHA256)
                continue
            self.assertEqual(
                hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest(),
                row["file_sha256"],
            )
        self.assertFalse(audit["execution_status"]["execution_authorization_present"])
        self.assertFalse(audit["execution_status"]["provider_call_run"])
        self.assertFalse(audit["authority_boundary"]["runtime_feature_authority_created"])

    def test_workflow_is_one_shot_after_separate_exact_authorization(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            "research/strategy/databento-microstructure-feature-diagnostic-v0.1-execution.json",
            workflow,
        )
        trigger = workflow.split("permissions:", 1)[0]
        self.assertNotIn("workflow_dispatch", workflow)
        self.assertNotIn(
            "research/strategy/databento-microstructure-feature-diagnostic-v0.1.json",
            trigger,
        )
        self.assertNotIn(
            ".github/workflows/databento-microstructure-features-v01.yml",
            trigger,
        )
        self.assertNotIn("*.dbn", workflow)
        self.assertNotIn("batch.submit_job", workflow)
        self.assertNotIn("live.subscribe", workflow)
        self.assertIn("databento==0.83.0", workflow)
        self.assertIn('run_attempt = os.getenv("GITHUB_RUN_ATTEMPT", "1")', script)
        self.assertIn('authorization["authorized_push_parent_sha"]', script)
        self.assertIn("github_actions_rerun_blocked", script)
        self.assertIn("unauthorized_push_parent", script)
        self.assertTrue(FUTURE_AUTHORIZATION.exists())


if __name__ == "__main__":
    unittest.main()
