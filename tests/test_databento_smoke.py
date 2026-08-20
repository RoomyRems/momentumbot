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

from momentumbot.research.databento_quote import (
    REQUIRED_SCHEMAS,
    SDK_VERSION,
    load_quote_contract,
)
from momentumbot.research.databento_smoke import (
    ACQUISITION_CONTENT_SHA256,
    AUTHORIZED_PUSH_PARENT_SHA,
    MAX_PREFLIGHT_BILLABLE_SIZE_BYTES,
    MAX_PREFLIGHT_COST_USD,
    RuntimeConstants,
    build_unavailable_report,
    load_acquisition_contract,
    run_smoke_acquisition,
    validate_acquisition_contract,
    validate_smoke_report,
)
from momentumbot.research.microstructure_contract import canonical_fingerprint


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-smoke-acquisition-v0.1.json"
)
QUOTE = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-metadata-quote-v0.1.json"
)
PARENT = ROOT / "research" / "strategy" / "level2-tape-feasibility-v0.1.json"
QUOTE_SUCCESS_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-metadata-quote-v0.1-run-32418655472-success-2026-08-20.json"
)
ACQUISITION_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-smoke-acquisition-v0.1-registration-2026-08-20.json"
)
WORKFLOW = ROOT / ".github" / "workflows" / "databento-microstructure-smoke.yml"
SCRIPT = ROOT / "scripts" / "run_databento_microstructure_smoke.py"
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


def _mbp_records(*, mismatch: bool = False, malformed: bool = False) -> list[FakeRecord]:
    kwargs: dict[str, object] = {
        "ts_event": 70_000_000_000,
        "ts_recv": 70_000_000_100,
        "publisher_id": 1,
        "instrument_id": 7,
        "sequence": 10,
        "flags": 0,
    }
    kwargs["levels"] = _state_levels(ask_price=103 if mismatch else 102)
    if malformed:
        kwargs["levels"] = kwargs["levels"][:9]
    return [FakeRecord(**kwargs)]


def _mbo_records() -> list[FakeRecord]:
    base = {
        "publisher_id": 1,
        "instrument_id": 7,
        "channel_id": 0,
    }
    return [
        FakeRecord(
            **base,
            ts_event=1,
            ts_recv=10,
            sequence=0,
            action="R",
            side="N",
            price=RUNTIME.undef_price,
            size=0,
            order_id=0,
            flags=RUNTIME.f_snapshot | RUNTIME.f_bad_ts_recv,
        ),
        FakeRecord(
            **base,
            ts_event=2,
            ts_recv=10,
            sequence=0,
            action="A",
            side="B",
            price=100,
            size=10,
            order_id=1,
            flags=RUNTIME.f_snapshot | RUNTIME.f_bad_ts_recv,
        ),
        FakeRecord(
            **base,
            ts_event=3,
            ts_recv=10,
            sequence=0,
            action="A",
            side="A",
            price=102,
            size=8,
            order_id=2,
            flags=RUNTIME.f_snapshot | RUNTIME.f_bad_ts_recv,
        ),
        FakeRecord(
            **base,
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


def _simple_records(schema: str) -> list[FakeRecord]:
    base = {
        "ts_event": 70_000_000_000,
        "ts_recv": 70_000_000_100,
        "publisher_id": 1,
        "instrument_id": 7,
    }
    if schema == "trades":
        return [
            FakeRecord(
                **base,
                sequence=10,
                action="T",
                side="B",
                price=101,
                size=2,
            )
        ]
    if schema == "definition":
        return [FakeRecord(**base)]
    return []


class FakeMetadata:
    def __init__(self, *, per_request_cost: float = 0.01, per_request_size: int = 100) -> None:
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
        mismatch: bool = False,
        malformed: bool = False,
        fail_on_call: int | None = None,
    ) -> None:
        self.mismatch = mismatch
        self.malformed = malformed
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
            records = _mbp_records(mismatch=self.mismatch, malformed=self.malformed)
        elif schema == "mbo":
            records = _mbo_records()
        else:
            records = _simple_records(schema)
        return FakeStore(schema, records)


class FakeClient:
    def __init__(
        self,
        *,
        per_request_cost: float = 0.01,
        per_request_size: int = 100,
        mismatch: bool = False,
        malformed: bool = False,
        fail_on_call: int | None = None,
    ) -> None:
        self.metadata = FakeMetadata(
            per_request_cost=per_request_cost,
            per_request_size=per_request_size,
        )
        self.timeseries = FakeTimeseries(
            mismatch=mismatch,
            malformed=malformed,
            fail_on_call=fail_on_call,
        )


class DatabentoSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.quote = load_quote_contract(QUOTE, parent_path=PARENT)
        cls.contract = load_acquisition_contract(CONTRACT, quote_contract=cls.quote)

    def run_gate(self, client: FakeClient) -> dict[str, object]:
        return run_smoke_acquisition(
            self.contract,
            self.quote,
            client,
            generated_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
            sdk_version=SDK_VERSION,
            runtime=RUNTIME,
        )

    def test_contract_is_hash_bound_and_authority_is_exact(self):
        self.assertEqual(self.contract["content_sha256"], ACQUISITION_CONTENT_SHA256)
        unsigned = {
            key: value
            for key, value in self.contract.items()
            if key != "content_sha256"
        }
        self.assertEqual(canonical_fingerprint(unsigned), ACQUISITION_CONTENT_SHA256)
        authorization = self.contract["authorization"]
        self.assertTrue(authorization["historical_timeseries_download_authorized"])
        self.assertEqual(authorization["exact_request_count_authorized"], 20)
        self.assertEqual(
            authorization["authorized_push_parent_sha"],
            AUTHORIZED_PUSH_PARENT_SHA,
        )
        self.assertFalse(authorization["automatic_retry_authorized"])
        self.assertFalse(authorization["batch_job_authorized"])
        self.assertEqual(MAX_PREFLIGHT_COST_USD, Decimal("0.50"))
        self.assertEqual(MAX_PREFLIGHT_BILLABLE_SIZE_BYTES, 500_000_000)

        changed = copy.deepcopy(self.contract)
        changed["authorization"]["exact_request_count_authorized"] = 21
        changed["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in changed.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "content hash changed"):
            validate_acquisition_contract(changed, quote_contract=self.quote)

    def test_verified_quote_audit_is_hash_bound(self):
        audit = json.loads(QUOTE_SUCCESS_AUDIT.read_text(encoding="utf-8"))
        claimed = audit["content_sha256"]
        unsigned = {key: value for key, value in audit.items() if key != "content_sha256"}
        self.assertEqual(canonical_fingerprint(unsigned), claimed)
        self.assertEqual(audit["github_actions"]["workflow_run_id"], 32418655472)
        self.assertEqual(
            audit["verified_result"]["conservative_total_quoted_cost_usd"],
            "0.207468646765",
        )
        self.assertFalse(audit["authority_boundary"]["market_data_downloaded_by_quote_run"])

    def test_registration_audit_binds_the_exact_acquisition_bundle(self):
        audit = json.loads(ACQUISITION_AUDIT.read_text(encoding="utf-8"))
        claimed = audit["content_sha256"]
        unsigned = {key: value for key, value in audit.items() if key != "content_sha256"}
        self.assertEqual(canonical_fingerprint(unsigned), claimed)
        self.assertEqual(audit["contract"]["content_sha256"], ACQUISITION_CONTENT_SHA256)
        for row in audit["bound_files"]:
            self.assertEqual(
                hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest(),
                row["file_sha256"],
            )
        self.assertFalse(audit["execution_status"]["provider_timeseries_request_run"])
        self.assertFalse(audit["authority_boundary"]["runtime_feature_authority_created"])
        self.assertFalse(audit["authority_boundary"]["paper_or_live_order_submitted"])

    def test_preflight_over_cost_ceiling_makes_zero_timeseries_calls(self):
        client = FakeClient(per_request_cost=0.03)
        report = self.run_gate(client)
        validate_smoke_report(report)
        self.assertFalse(report["preflight"]["cost_within_ceiling"])
        self.assertEqual(report["timeseries_request_count"], 0)
        self.assertEqual(client.timeseries.calls, [])
        self.assertFalse(report["smoke_acquisition_passed"])

    def test_preflight_over_size_ceiling_makes_zero_timeseries_calls(self):
        client = FakeClient(per_request_size=25_000_001)
        report = self.run_gate(client)
        validate_smoke_report(report)
        self.assertFalse(report["preflight"]["billable_size_within_ceiling"])
        self.assertEqual(report["timeseries_request_count"], 0)
        self.assertEqual(client.timeseries.calls, [])

    def test_twenty_exact_ephemeral_downloads_pass_and_are_sanitized(self):
        client = FakeClient()
        report = self.run_gate(client)
        validate_smoke_report(report)
        self.assertTrue(report["preflight"]["preflight_passed"])
        self.assertEqual(report["timeseries_request_count"], 20)
        self.assertEqual(len(report["downloads"]), 20)
        self.assertTrue(report["g1_schema_and_integrity_passed"])
        self.assertTrue(report["g2_reconstruction_passed"])
        self.assertTrue(report["smoke_acquisition_passed"])
        self.assertFalse(report["runtime_authority_created"])
        self.assertTrue(report["raw_temp_directory_empty_before_cleanup"])
        self.assertTrue(report["raw_temp_directory_removed"])
        self.assertTrue(all(not path.exists() for path in client.timeseries.paths))
        for case in report["cases"]:
            self.assertEqual(
                [row["schema"] for row in case["downloads"]],
                ["mbp-10", "mbo", "trades", "definition", "status"],
            )
            comparison = case["downloads"][1]["metrics"]["comparison_metrics"]
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
        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn("provider detail", rendered)
        self.assertNotIn(".dbn.zst", rendered)

    def test_reference_mismatch_fails_g2_after_all_schemas_finish(self):
        client = FakeClient(mismatch=True)
        report = self.run_gate(client)
        validate_smoke_report(report)
        self.assertEqual(report["timeseries_request_count"], 20)
        self.assertTrue(report["g1_schema_and_integrity_passed"])
        self.assertFalse(report["g2_reconstruction_passed"])
        self.assertFalse(report["smoke_acquisition_passed"])
        for case in report["cases"]:
            comparison = case["downloads"][1]["metrics"]["comparison_metrics"]
            self.assertEqual(comparison["mbp10_exact_match_count"], 0)

    def test_provider_failure_stops_without_retry_and_cleans_partial_file(self):
        client = FakeClient(fail_on_call=3)
        report = self.run_gate(client)
        validate_smoke_report(report)
        self.assertEqual(report["timeseries_request_count"], 3)
        self.assertEqual(len(client.timeseries.calls), 3)
        self.assertEqual(len(report["downloads"]), 2)
        self.assertEqual(report["errors"][0]["error_kind"], "RuntimeError")
        self.assertNotIn("provider detail", json.dumps(report, sort_keys=True))
        self.assertTrue(all(not path.exists() for path in client.timeseries.paths))
        self.assertFalse(report["automatic_retry_attempted"])

    def test_parser_failure_is_sanitized_and_raw_file_is_removed(self):
        client = FakeClient(malformed=True)
        report = self.run_gate(client)
        validate_smoke_report(report)
        self.assertEqual(report["timeseries_request_count"], 1)
        self.assertEqual(report["downloads"], [])
        self.assertEqual(report["errors"][0]["error_kind"], "ValueError")
        self.assertTrue(all(not path.exists() for path in client.timeseries.paths))

    def test_unavailable_report_has_no_market_data_authority(self):
        report = build_unavailable_report(
            self.contract,
            self.quote,
            generated_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
            sdk_version="not_loaded",
            error_stage="credential",
            error_kind="missing_DATABENTO_API_KEY",
        )
        validate_smoke_report(report)
        self.assertEqual(report["timeseries_request_count"], 0)
        self.assertFalse(report["smoke_acquisition_passed"])
        self.assertFalse(report["runtime_authority_created"])

        contaminated = copy.deepcopy(report)
        contaminated["downloads"] = [{"order_id": 123}]
        contaminated["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in contaminated.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "prohibited field"):
            validate_smoke_report(contaminated)

    def test_workflow_is_one_shot_and_uploads_only_sanitized_json(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("databento==0.83.0", text)
        self.assertIn("DATABENTO_API_KEY: ${{ secrets.DATABENTO_API_KEY }}", text)
        self.assertIn("MOMENTUMBOT_PUSH_BEFORE: ${{ github.event.before }}", text)
        self.assertIn("run_databento_microstructure_smoke.py", text)
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
