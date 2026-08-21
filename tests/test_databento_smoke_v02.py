from __future__ import annotations

import copy
import hashlib
import json
import unittest
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from momentumbot.research.databento_quote import SDK_VERSION
from momentumbot.research.databento_smoke_v02 import (
    ACQUISITION_CONTENT_SHA256,
    AUTHORIZED_PUSH_PARENT_SHA,
    MAX_PREFLIGHT_BILLABLE_SIZE_BYTES,
    MAX_PREFLIGHT_COST_USD,
    PARENT_FAILURE_CONTENT_SHA256,
    REQUESTS,
    RuntimeConstants,
    build_unavailable_report,
    load_acquisition_contract,
    load_parent_failure_audit,
    run_smoke_acquisition,
    validate_acquisition_contract,
    validate_parent_failure_audit,
    validate_smoke_report,
)
from momentumbot.research.microstructure_contract import canonical_fingerprint


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-smoke-acquisition-v0.2.json"
)
PARENT_FAILURE = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-smoke-acquisition-v0.1-"
    "run-32427326070-failure-2026-08-20.json"
)
REGISTRATION_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-smoke-acquisition-v0.2-registration-2026-08-20.json"
)
WORKFLOW = (
    ROOT / ".github" / "workflows" / "databento-microstructure-smoke-v02.yml"
)
SCRIPT = ROOT / "scripts" / "run_databento_microstructure_smoke_v02.py"
RUNTIME = RuntimeConstants(
    f_last=128,
    f_tob=64,
    f_snapshot=32,
    f_bad_ts_recv=8,
    undef_price=9_223_372_036_854_775_807,
)


@dataclass(slots=True)
class FakeLevel:
    bid_px: int
    ask_px: int
    bid_sz: int
    ask_sz: int
    bid_ct: int
    ask_ct: int


class FakeRecord:
    def __init__(self, **kwargs: object) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeStore:
    def __init__(self, schema: str, records: list[FakeRecord]) -> None:
        self.metadata = SimpleNamespace(dataset="XNAS.ITCH", schema=schema)
        self.records = records

    def __iter__(self):
        return iter(self.records)


def _state_levels(*, ask_price: int = 102) -> list[FakeLevel]:
    levels = [
        FakeLevel(
            bid_px=100,
            ask_px=ask_price,
            bid_sz=10,
            ask_sz=8,
            bid_ct=1,
            ask_ct=1,
        )
    ]
    levels.extend(
        FakeLevel(
            bid_px=RUNTIME.undef_price,
            ask_px=RUNTIME.undef_price,
            bid_sz=0,
            ask_sz=0,
            bid_ct=0,
            ask_ct=0,
        )
        for _ in range(9)
    )
    return levels


def _mbp_records(
    *,
    mismatch: bool = False,
    malformed: bool = False,
    recovery: bool = False,
) -> list[FakeRecord]:
    rows = [
        FakeRecord(
            ts_event=70_000_000_000,
            ts_recv=70_000_000_100,
            publisher_id=1,
            instrument_id=7,
            sequence=10,
            flags=0,
            levels=_state_levels(ask_price=103 if mismatch else 102),
        )
    ]
    if malformed:
        rows[0].levels = rows[0].levels[:9]
    if recovery:
        rows.append(
            FakeRecord(
                ts_event=130_000_000_000,
                ts_recv=130_000_000_100,
                publisher_id=1,
                instrument_id=7,
                sequence=20,
                flags=0,
                levels=_state_levels(ask_price=103),
            )
        )
    return rows


def _base_mbo() -> dict[str, int]:
    return {"publisher_id": 1, "instrument_id": 7, "channel_id": 0}


def _clear(*, flags: int, sequence: int = 0, side: str = "N") -> FakeRecord:
    return FakeRecord(
        **_base_mbo(),
        ts_event=1 if sequence == 0 else 100_000_000_000,
        ts_recv=10 if sequence == 0 else 100_000_000_100,
        sequence=sequence,
        action="R",
        side=side,
        price=RUNTIME.undef_price,
        size=0,
        order_id=0,
        flags=flags,
    )


def _add(
    *,
    side: str,
    price: int,
    size: int,
    order_id: int,
    sequence: int,
    flags: int,
    ts: int,
) -> FakeRecord:
    return FakeRecord(
        **_base_mbo(),
        ts_event=ts,
        ts_recv=ts + 100,
        sequence=sequence,
        action="A",
        side=side,
        price=price,
        size=size,
        order_id=order_id,
        flags=flags,
    )


def _mbo_records(
    *,
    reset_mode: str = "session",
    recovery: bool = False,
) -> list[FakeRecord]:
    if reset_mode == "preinit_mutation":
        rows = [
            _add(
                side="B",
                price=100,
                size=10,
                order_id=99,
                sequence=1,
                flags=RUNTIME.f_last,
                ts=1,
            ),
            _clear(flags=RUNTIME.f_last, sequence=2),
        ]
    elif reset_mode == "invalid_clear":
        rows = [_clear(flags=RUNTIME.f_last, side="A")]
    elif reset_mode == "snapshot":
        rows = [
            _clear(flags=RUNTIME.f_snapshot | RUNTIME.f_bad_ts_recv),
            _add(
                side="B",
                price=100,
                size=10,
                order_id=1,
                sequence=0,
                flags=RUNTIME.f_snapshot | RUNTIME.f_bad_ts_recv,
                ts=2,
            ),
            _add(
                side="A",
                price=102,
                size=8,
                order_id=2,
                sequence=0,
                flags=RUNTIME.f_snapshot | RUNTIME.f_bad_ts_recv,
                ts=3,
            ),
            FakeRecord(
                **_base_mbo(),
                ts_event=70_000_000_000,
                ts_recv=70_000_000_100,
                sequence=10,
                action="N",
                side="N",
                price=RUNTIME.undef_price,
                size=0,
                order_id=0,
                flags=RUNTIME.f_last,
            ),
        ]
        return rows
    else:
        rows = [_clear(flags=RUNTIME.f_last)]

    rows.extend(
        [
            _add(
                side="B",
                price=100,
                size=10,
                order_id=1,
                sequence=10,
                flags=0,
                ts=70_000_000_000,
            ),
            _add(
                side="A",
                price=102,
                size=8,
                order_id=2,
                sequence=10,
                flags=RUNTIME.f_last,
                ts=70_000_000_001,
            ),
        ]
    )
    if recovery:
        rows.extend(
            [
                _clear(flags=RUNTIME.f_last, sequence=11),
                _add(
                    side="B",
                    price=100,
                    size=10,
                    order_id=3,
                    sequence=20,
                    flags=0,
                    ts=130_000_000_000,
                ),
                _add(
                    side="A",
                    price=103,
                    size=8,
                    order_id=4,
                    sequence=20,
                    flags=RUNTIME.f_last,
                    ts=130_000_000_001,
                ),
            ]
        )
    return rows


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
        reset_mode: str = "session",
        mismatch: bool = False,
        malformed: bool = False,
        recovery: bool = False,
        fail_on_call: int | None = None,
    ) -> None:
        self.reset_mode = reset_mode
        self.mismatch = mismatch
        self.malformed = malformed
        self.recovery = recovery
        self.fail_on_call = fail_on_call
        self.calls: list[dict[str, object]] = []
        self.paths: list[Path] = []

    def get_range(self, **kwargs: object) -> FakeStore:
        self.calls.append(kwargs)
        path = Path(str(kwargs["path"]))
        self.paths.append(path)
        path.write_bytes(f"fake-dbn-{len(self.calls)}".encode())
        if self.fail_on_call == len(self.calls):
            raise RuntimeError("provider detail must not enter report")
        schema = str(kwargs["schema"])
        if schema == "mbp-10":
            records = _mbp_records(
                mismatch=self.mismatch,
                malformed=self.malformed,
                recovery=self.recovery,
            )
        else:
            records = _mbo_records(
                reset_mode=self.reset_mode,
                recovery=self.recovery,
            )
        return FakeStore(schema, records)


class FakeClient:
    def __init__(
        self,
        *,
        per_request_cost: float = 0.001,
        per_request_size: int = 100,
        reset_mode: str = "session",
        mismatch: bool = False,
        malformed: bool = False,
        recovery: bool = False,
        fail_on_call: int | None = None,
    ) -> None:
        self.metadata = FakeMetadata(
            per_request_cost=per_request_cost,
            per_request_size=per_request_size,
        )
        self.timeseries = FakeTimeseries(
            reset_mode=reset_mode,
            mismatch=mismatch,
            malformed=malformed,
            recovery=recovery,
            fail_on_call=fail_on_call,
        )


class DatabentoSmokeV02Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parent_failure = load_parent_failure_audit(PARENT_FAILURE)
        cls.contract = load_acquisition_contract(
            CONTRACT,
            parent_failure_audit=cls.parent_failure,
        )

    def run_gate(self, client: FakeClient) -> dict[str, object]:
        return run_smoke_acquisition(
            self.contract,
            client,
            parent_failure_audit=self.parent_failure,
            generated_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
            sdk_version=SDK_VERSION,
            runtime=RUNTIME,
        )

    def test_parent_failure_and_v02_contract_are_hash_bound(self):
        self.assertEqual(
            self.parent_failure["content_sha256"],
            PARENT_FAILURE_CONTENT_SHA256,
        )
        validate_parent_failure_audit(self.parent_failure)
        self.assertEqual(self.contract["content_sha256"], ACQUISITION_CONTENT_SHA256)
        self.assertEqual(
            canonical_fingerprint(
                {
                    key: value
                    for key, value in self.contract.items()
                    if key != "content_sha256"
                }
            ),
            ACQUISITION_CONTENT_SHA256,
        )
        self.assertEqual(len(REQUESTS), 2)
        self.assertEqual(
            self.contract["authorization"]["authorized_push_parent_sha"],
            AUTHORIZED_PUSH_PARENT_SHA,
        )
        self.assertEqual(MAX_PREFLIGHT_COST_USD, Decimal("0.02"))
        self.assertEqual(MAX_PREFLIGHT_BILLABLE_SIZE_BYTES, 15_000_000)

        changed = copy.deepcopy(self.contract)
        changed["authorization"]["exact_request_count_authorized"] = 3
        changed["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in changed.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "content hash changed"):
            validate_acquisition_contract(
                changed,
                parent_failure_audit=self.parent_failure,
            )

    def test_registration_audit_binds_the_exact_v02_bundle(self):
        audit = json.loads(REGISTRATION_AUDIT.read_text(encoding="utf-8"))
        claimed = audit["content_sha256"]
        unsigned = {key: value for key, value in audit.items() if key != "content_sha256"}
        self.assertEqual(canonical_fingerprint(unsigned), claimed)
        self.assertEqual(audit["contract"]["content_sha256"], ACQUISITION_CONTENT_SHA256)
        self.assertEqual(
            audit["parent_failure"]["content_sha256"],
            PARENT_FAILURE_CONTENT_SHA256,
        )
        for row in audit["bound_files"]:
            self.assertEqual(
                hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest(),
                row["file_sha256"],
            )
        self.assertFalse(audit["execution_status"]["provider_timeseries_request_run"])
        self.assertFalse(audit["authority_boundary"]["runtime_feature_authority_created"])
        self.assertFalse(audit["authority_boundary"]["paper_or_live_order_submitted"])

    def test_preflight_cost_or_size_failure_makes_zero_timeseries_calls(self):
        for client in (
            FakeClient(per_request_cost=0.011),
            FakeClient(per_request_size=7_500_001),
        ):
            with self.subTest(client=client):
                report = self.run_gate(client)
                validate_smoke_report(report)
                self.assertFalse(report["preflight"]["preflight_passed"])
                self.assertEqual(report["timeseries_request_count"], 0)
                self.assertEqual(client.timeseries.calls, [])

    def test_unflagged_session_clear_passes_exact_replay(self):
        client = FakeClient()
        report = self.run_gate(client)
        validate_smoke_report(report)
        self.assertEqual(report["timeseries_request_count"], 2)
        self.assertTrue(report["g1_schema_and_integrity_passed"])
        self.assertTrue(report["g2_reconstruction_passed"])
        self.assertTrue(report["smoke_acquisition_passed"])
        mbo = report["downloads"][1]["metrics"]
        self.assertEqual(mbo["session_initialization_clear_count"], 1)
        self.assertEqual(mbo["snapshot_initialization_clear_count"], 0)
        self.assertEqual(mbo["ready_book_count"], 1)
        comparison = mbo["comparison_metrics"]
        self.assertEqual(comparison["aligned_sample_count"], 1)
        self.assertEqual(comparison["mbp10_exact_match_count"], 1)
        self.assertEqual(
            comparison["incremental_replay_digest_sha256"],
            comparison["independent_replay_digest_sha256"],
        )
        self.assertEqual(
            comparison["incremental_replay_digest_sha256"],
            comparison["mbp10_reference_digest_sha256"],
        )
        self.assertTrue(all(not path.exists() for path in client.timeseries.paths))

    def test_snapshot_initialization_remains_supported(self):
        report = self.run_gate(FakeClient(reset_mode="snapshot"))
        validate_smoke_report(report)
        self.assertTrue(report["smoke_acquisition_passed"])
        mbo = report["downloads"][1]["metrics"]
        self.assertEqual(mbo["snapshot_initialization_clear_count"], 1)
        self.assertEqual(mbo["session_initialization_clear_count"], 0)

    def test_later_clear_resets_both_books_before_comparison_resumes(self):
        report = self.run_gate(FakeClient(recovery=True))
        validate_smoke_report(report)
        self.assertTrue(report["smoke_acquisition_passed"])
        mbo = report["downloads"][1]["metrics"]
        self.assertEqual(mbo["clear_action_count"], 2)
        self.assertEqual(mbo["recovery_clear_count"], 1)
        self.assertEqual(mbo["comparison_metrics"]["aligned_sample_count"], 2)

    def test_invalid_or_late_first_clear_fails_g1(self):
        for reset_mode in ("invalid_clear", "preinit_mutation"):
            with self.subTest(reset_mode=reset_mode):
                report = self.run_gate(FakeClient(reset_mode=reset_mode))
                validate_smoke_report(report)
                self.assertFalse(report["g1_schema_and_integrity_passed"])
                self.assertFalse(report["g2_reconstruction_passed"])

    def test_reference_mismatch_fails_g2_after_both_downloads(self):
        report = self.run_gate(FakeClient(mismatch=True))
        validate_smoke_report(report)
        self.assertEqual(report["timeseries_request_count"], 2)
        self.assertTrue(report["g1_schema_and_integrity_passed"])
        self.assertFalse(report["g2_reconstruction_passed"])
        comparison = report["downloads"][1]["metrics"]["comparison_metrics"]
        self.assertEqual(comparison["mbp10_exact_match_count"], 0)

    def test_provider_or_parser_failure_is_sanitized_without_retry(self):
        for client in (
            FakeClient(fail_on_call=2),
            FakeClient(malformed=True),
        ):
            with self.subTest(client=client):
                report = self.run_gate(client)
                validate_smoke_report(report)
                self.assertLessEqual(report["timeseries_request_count"], 2)
                self.assertFalse(report["automatic_retry_attempted"])
                self.assertNotIn("provider detail", json.dumps(report, sort_keys=True))
                self.assertTrue(all(not path.exists() for path in client.timeseries.paths))

    def test_unavailable_report_has_no_market_data_or_runtime_authority(self):
        report = build_unavailable_report(
            self.contract,
            parent_failure_audit=self.parent_failure,
            generated_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
            sdk_version="not_loaded",
            error_stage="credential",
            error_kind="missing_DATABENTO_API_KEY",
        )
        validate_smoke_report(report)
        self.assertEqual(report["timeseries_request_count"], 0)
        self.assertFalse(report["runtime_authority_created"])

        contaminated = copy.deepcopy(report)
        contaminated["downloads"] = [{"order_id": 123}]
        contaminated["content_sha256"] = canonical_fingerprint(
            {
                key: value
                for key, value in contaminated.items()
                if key != "content_sha256"
            }
        )
        with self.assertRaisesRegex(ValueError, "prohibited field"):
            validate_smoke_report(contaminated)

    def test_workflow_is_one_shot_and_uploads_only_sanitized_json(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("databento==0.83.0", text)
        self.assertIn("DATABENTO_API_KEY: ${{ secrets.DATABENTO_API_KEY }}", text)
        self.assertIn("MOMENTUMBOT_PUSH_BEFORE: ${{ github.event.before }}", text)
        self.assertIn("run_databento_microstructure_smoke_v02.py", text)
        self.assertNotIn("workflow_dispatch", text)
        self.assertNotIn("*.dbn", text)
        self.assertNotIn(".dbn.zst", text)
        self.assertNotIn("batch.submit_job", text)
        self.assertNotIn("live.subscribe", text)
        self.assertIn('run_attempt = os.getenv("GITHUB_RUN_ATTEMPT", "1")', script)
        self.assertIn("github_actions_rerun_blocked", script)
        self.assertIn("unauthorized_push_parent", script)
        self.assertEqual(text.count("DATABENTO_API_KEY"), 2)


if __name__ == "__main__":
    unittest.main()
