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
from types import SimpleNamespace

import pandas as pd

from momentumbot.research.microstructure_contract import canonical_fingerprint
from momentumbot.research.prospective_market_input_acquisition import (
    CONTRACT_CONTENT_SHA256,
    CONTRACT_ID,
    PERMITTED_METHODS,
    build_acquisition_authorization,
    build_unavailable_report,
    build_zero_request_result,
    load_acquisition_contract,
    run_exact_acquisition,
    validate_acquisition_authorization,
    validate_acquisition_contract,
    validate_acquisition_report,
    validate_execution_context,
)
from momentumbot.research.prospective_market_input_capture import (
    CONTRACT_CONTENT_SHA256 as CAPTURE_CONTRACT_CONTENT_SHA256,
    load_capture_contract,
)
from momentumbot.research.prospective_market_input_quote import (
    CONTRACT_CONTENT_SHA256 as QUOTE_CONTRACT_CONTENT_SHA256,
    EXPECTED_REPOSITORY,
    SDK_VERSION,
    build_quote_authorization,
    build_zero_request_report,
    load_quote_contract,
    run_metadata_quote,
    validate_parent_bundle,
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
    ROOT / "research" / "strategy" / "prospective-market-input-acquisition-v0.1.json"
)
QUOTE_CONTRACT = (
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
    / "prospective-market-input-acquisition-v0.1-registration-2026-08-22.json"
)
WORKFLOW = ROOT / ".github" / "workflows" / "prospective-market-input-acquisition.yml"
SCRIPT = ROOT / "scripts" / "acquire_prospective_market_inputs.py"

FREEZE_RUN_ID = "123456789"
QUOTE_RUN_ID = "987654321"
ACQUISITION_RUN_ID = "1122334455"


def _ns(value: str) -> int:
    return int(
        datetime.fromisoformat(value).astimezone(UTC).timestamp() * 1_000_000_000
    )


def _rfc3339_ns(value: str) -> int:
    prefix, fraction = value.removesuffix("Z").split(".", maxsplit=1)
    seconds = int(
        datetime.fromisoformat(prefix).replace(tzinfo=UTC).timestamp()
    )
    return seconds * 1_000_000_000 + int(fraction.ljust(9, "0")[:9])


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
        size: int = 1_250,
        cost: float = 0.0125,
        zero_schema: str | None = None,
        fail_method: str | None = None,
        fail_schema: str | None = None,
    ) -> None:
        self.size = size
        self.cost = cost
        self.zero_schema = zero_schema
        self.fail_method = fail_method
        self.fail_schema = fail_schema
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get_billable_size(self, **kwargs):
        self.calls.append(("get_billable_size", kwargs))
        if self.fail_method == "get_billable_size" and (
            self.fail_schema is None or kwargs["schema"] == self.fail_schema
        ):
            raise RuntimeError("provider narrative must never persist")
        return 0 if kwargs["schema"] == self.zero_schema else self.size

    def get_cost(self, **kwargs):
        self.calls.append(("get_cost", kwargs))
        if self.fail_method == "get_cost" and (
            self.fail_schema is None or kwargs["schema"] == self.fail_schema
        ):
            raise RuntimeError("provider narrative must never persist")
        return self.cost


class _Store:
    def __init__(
        self,
        *,
        dataset: str,
        schema: str,
        stype_in: str,
        symbols: list[str],
        start_ns: int,
        end_ns: int,
        records: list[dict[str, object]],
    ) -> None:
        self.metadata = SimpleNamespace(
            dataset=dataset,
            schema=schema,
            stype_in=stype_in,
            symbols=symbols,
            start=start_ns,
            end=end_ns,
        )
        self.records = records

    def to_df(self, **kwargs):
        if kwargs != {
            "map_symbols": True,
            "pretty_ts": False,
            "price_type": "fixed",
        }:
            raise AssertionError("record conversion contract changed")
        return pd.DataFrame(self.records)


class _Timeseries:
    def __init__(
        self,
        records: dict[str, list[dict[str, object]]],
        *,
        fail_schema: str | None = None,
        metadata_schema: str | None = None,
        metadata_dataset: str | None = None,
    ) -> None:
        self.records = records
        self.fail_schema = fail_schema
        self.metadata_schema = metadata_schema
        self.metadata_dataset = metadata_dataset
        self.calls: list[dict[str, object]] = []
        self.paths: list[Path] = []

    def get_range(self, **kwargs):
        self.calls.append(kwargs)
        path = Path(str(kwargs["path"]))
        self.paths.append(path)
        if kwargs["schema"] == self.fail_schema:
            raise RuntimeError("provider download narrative must never persist")
        path.write_bytes(f"fixture-{kwargs['schema']}".encode("ascii"))
        return _Store(
            dataset=self.metadata_dataset or str(kwargs["dataset"]),
            schema=self.metadata_schema or str(kwargs["schema"]),
            stype_in=str(kwargs["stype_in"]),
            symbols=list(kwargs["symbols"]),
            start_ns=_rfc3339_ns(str(kwargs["start"])),
            end_ns=_rfc3339_ns(str(kwargs["end"])),
            records=copy.deepcopy(self.records[str(kwargs["schema"])]),
        )


class _Client:
    def __init__(self, metadata: _Metadata, timeseries: _Timeseries) -> None:
        self.metadata = metadata
        self.timeseries = timeseries


class ProspectiveMarketInputAcquisitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load_acquisition_contract(CONTRACT)
        cls.quote_contract = load_quote_contract(QUOTE_CONTRACT)
        cls.capture_contract = load_capture_contract(CAPTURE_CONTRACT)
        cls.freeze_contract = load_opportunity_freeze_contract(FREEZE_CONTRACT)
        cls.bundle = cls._build_bundle(_decision(), candidate_count=1)
        cls.quote_authorization = cls._quote_authorization(cls.bundle)
        cls.quote_report = cls._quote_report(
            cls.bundle,
            cls.quote_authorization,
            _Metadata(),
        )
        cls.quote_artifact_name = (
            "prospective-market-input-metadata-quote-2026-08-24-"
            f"{QUOTE_RUN_ID}-1"
        )
        cls.authorization = cls._acquisition_authorization(
            cls.bundle,
            cls.quote_authorization,
            cls.quote_report,
        )

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
            cls.quote_contract,
            cls.capture_contract,
            result.opportunity_manifest,
            result.request_manifest,
            result.freeze_manifest,
        )

    @classmethod
    def _quote_authorization(cls, bundle):
        return build_quote_authorization(
            cls.quote_contract,
            cls.capture_contract,
            bundle,
            repository=EXPECTED_REPOSITORY,
            freeze_run_id=FREEZE_RUN_ID,
            freeze_run_attempt=1,
            freeze_artifact_name=(
                f"prospective-opportunity-freeze-{bundle.trading_date}"
            ),
        )

    @classmethod
    def _quote_report(cls, bundle, authorization, metadata: _Metadata):
        return run_metadata_quote(
            cls.quote_contract,
            cls.capture_contract,
            bundle,
            authorization,
            SimpleNamespace(metadata=metadata),
            generated_at=datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
            sdk_version=SDK_VERSION,
            workflow_run_id=QUOTE_RUN_ID,
            workflow_run_attempt=1,
        )

    @classmethod
    def _acquisition_authorization(
        cls,
        bundle,
        quote_authorization,
        quote_report,
    ):
        return build_acquisition_authorization(
            cls.contract,
            cls.quote_contract,
            cls.capture_contract,
            bundle,
            quote_authorization,
            quote_report,
            repository=EXPECTED_REPOSITORY,
            quote_artifact_name=(
                f"prospective-market-input-metadata-quote-{bundle.trading_date}-"
                f"{quote_report['workflow_run_id']}-"
                f"{quote_report['workflow_run_attempt']}"
            ),
        )

    @classmethod
    def _records(cls, bundle):
        opportunity = bundle.opportunity_manifest["opportunities"][0]
        decision = int(opportunity["decision_ts_ns"])
        return {
            "mbp-1": [
                {
                    "symbol": "TEST",
                    "ts_recv": decision,
                    "sequence": 10,
                    "bid_px_00": 10_000_000_000,
                    "bid_sz_00": 500,
                    "ask_px_00": 10_010_000_000,
                    "ask_sz_00": 400,
                }
            ],
            "status": [
                {
                    "symbol": "TEST",
                    "ts_recv": decision - 200_000_000,
                    "action": 1,
                    "is_trading": "Y",
                }
            ],
        }

    def _run(
        self,
        *,
        metadata: _Metadata | None = None,
        timeseries: _Timeseries | None = None,
    ):
        metadata = metadata or _Metadata()
        timeseries = timeseries or _Timeseries(self._records(self.bundle))
        report, capture = run_exact_acquisition(
            self.contract,
            self.quote_contract,
            self.capture_contract,
            self.bundle,
            self.quote_authorization,
            self.quote_report,
            self.authorization,
            _Client(metadata, timeseries),
            generated_at=datetime(2026, 8, 24, 12, 30, tzinfo=UTC),
            workflow_run_id=ACQUISITION_RUN_ID,
            workflow_run_attempt=1,
            sdk_version=SDK_VERSION,
        )
        return report, capture, metadata, timeseries

    def _validate(
        self,
        report,
        capture,
        *,
        bundle=None,
        quote_authorization=None,
        quote_report=None,
        authorization=None,
    ) -> None:
        validate_acquisition_report(
            report,
            capture=capture,
            acquisition_contract=self.contract,
            quote_contract=self.quote_contract,
            capture_contract=self.capture_contract,
            bundle=bundle or self.bundle,
            quote_authorization=quote_authorization or self.quote_authorization,
            quote_report=quote_report or self.quote_report,
            authorization=authorization or self.authorization,
        )

    def test_contract_is_hash_bound_unarmed_and_exact(self):
        self.assertEqual(self.contract["content_sha256"], CONTRACT_CONTENT_SHA256)
        self.assertEqual(self.contract["contract_id"], CONTRACT_ID)
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
            parents["metadata_quote_contract_content_sha256"],
            QUOTE_CONTRACT_CONTENT_SHA256,
        )
        self.assertEqual(
            self.contract["provider_scope"]["permitted_methods"],
            list(PERMITTED_METHODS),
        )
        authority = self.contract["authority_boundary"]
        self.assertFalse(authority["provider_metadata_requote_authorized_at_registration"])
        self.assertFalse(authority["provider_timeseries_request_authorized_at_registration"])
        self.assertFalse(authority["provider_purchase_authorized_at_registration"])
        self.assertEqual(authority["provider_call_run_count"], 0)
        self.assertEqual(authority["databento_credit_authorized_usd"], "0")
        self.assertFalse(authority["broker_order_authorized"])

        changed = copy.deepcopy(self.contract)
        changed["authority_boundary"]["provider_timeseries_request_authorized_at_registration"] = True
        changed = _rehash(changed)
        with self.assertRaises(ValueError):
            validate_acquisition_contract(changed)

    def test_only_a_successful_exact_quote_can_create_authority(self):
        unavailable_quote = self._quote_report(
            self.bundle,
            self.quote_authorization,
            _Metadata(zero_schema="status"),
        )
        with self.assertRaisesRegex(ValueError, "successful metadata quote gate"):
            self._acquisition_authorization(
                self.bundle,
                self.quote_authorization,
                unavailable_quote,
            )

    def test_authorization_binds_quote_freeze_ceilings_and_first_attempt(self):
        repeated = self._acquisition_authorization(
            self.bundle,
            self.quote_authorization,
            self.quote_report,
        )
        self.assertEqual(repeated, self.authorization)
        self.assertEqual(self.authorization["request_count"], 2)
        self.assertEqual(self.authorization["maximum_metadata_call_count"], 4)
        self.assertEqual(self.authorization["maximum_timeseries_call_count"], 2)
        self.assertEqual(
            self.authorization["hard_preflight_cost_ceiling_usd"],
            "0.0250",
        )
        self.assertEqual(
            self.authorization["hard_preflight_billable_size_ceiling_bytes"],
            2_500,
        )
        self.assertTrue(self.authorization["metadata_requote_authorized"])
        self.assertTrue(self.authorization["historical_timeseries_download_authorized"])
        self.assertFalse(self.authorization["authorization_reuse_authorized"])
        self.assertFalse(self.authorization["automatic_retry_authorized"])
        self.assertFalse(self.authorization["broker_order_authorized"])

        changed = copy.deepcopy(self.authorization)
        changed["maximum_timeseries_call_count"] = 3
        changed = _rehash(changed)
        with self.assertRaisesRegex(ValueError, "binding changed"):
            validate_acquisition_authorization(
                changed,
                acquisition_contract=self.contract,
                quote_contract=self.quote_contract,
                capture_contract=self.capture_contract,
                bundle=self.bundle,
                quote_authorization=self.quote_authorization,
                quote_report=self.quote_report,
            )

        changed = copy.deepcopy(self.authorization)
        changed["historical_timeseries_download_authorized"] = 1
        changed = _rehash(changed)
        with self.assertRaisesRegex(ValueError, "must be boolean"):
            validate_acquisition_authorization(
                changed,
                acquisition_contract=self.contract,
                quote_contract=self.quote_contract,
                capture_contract=self.capture_contract,
                bundle=self.bundle,
                quote_authorization=self.quote_authorization,
                quote_report=self.quote_report,
            )

    def test_success_requotes_then_downloads_each_exact_request_once(self):
        report, capture, metadata, timeseries = self._run()
        self._validate(report, capture)
        self.assertEqual(report["acquisition_status"], "complete")
        self.assertTrue(report["acquisition_gate_passed"])
        self.assertEqual(report["metadata_call_count"], 4)
        self.assertEqual(report["timeseries_request_count"], 2)
        self.assertEqual(
            [method for method, _kwargs in metadata.calls],
            [
                "get_billable_size",
                "get_cost",
                "get_billable_size",
                "get_cost",
            ],
        )
        self.assertEqual(
            [row["schema"] for row in timeseries.calls],
            [row["schema"] for row in self.bundle.request_manifest["requests"]],
        )
        for row, request in zip(
            timeseries.calls,
            self.bundle.request_manifest["requests"],
            strict=True,
        ):
            self.assertEqual(row["dataset"], request["dataset"])
            self.assertEqual(row["symbols"], request["symbols"])
            self.assertEqual(row["schema"], request["schema"])
            self.assertEqual(row["stype_in"], request["stype_in"])
            self.assertRegex(str(row["start"]), r"\.\d{9}Z$")
            self.assertRegex(str(row["end"]), r"\.\d{9}Z$")
        self.assertTrue(all(not path.exists() for path in timeseries.paths))
        self.assertIsNotNone(capture)
        self.assertEqual(capture["captures"][0]["usable_quote_count"], 1)
        self.assertEqual(capture["captures"][0]["quotes"][0]["bid_price"], "10")
        self.assertFalse(report["raw_dbn_persisted"])
        self.assertFalse(report["raw_dbn_uploaded"])
        self.assertNotIn("provider narrative", json.dumps(report))

    def test_cost_or_availability_drift_stops_before_every_download(self):
        for metadata in (
            _Metadata(cost=0.02),
            _Metadata(zero_schema="status"),
            _Metadata(fail_method="get_cost", fail_schema="status"),
        ):
            with self.subTest(metadata=metadata.__dict__):
                timeseries = _Timeseries(self._records(self.bundle))
                report, capture, observed_metadata, observed_timeseries = self._run(
                    metadata=metadata,
                    timeseries=timeseries,
                )
                self._validate(report, capture)
                self.assertEqual(report["acquisition_status"], "preflight_failed")
                self.assertFalse(report["acquisition_gate_passed"])
                self.assertEqual(report["metadata_call_count"], 4)
                self.assertEqual(report["timeseries_request_count"], 0)
                self.assertEqual(len(observed_metadata.calls), 4)
                self.assertEqual(observed_timeseries.calls, [])
                self.assertIsNone(capture)
                self.assertNotIn("provider narrative", json.dumps(report))

    def test_first_download_failure_stops_later_requests_and_discards_partial_capture(self):
        first_schema = str(self.bundle.request_manifest["requests"][0]["schema"])
        timeseries = _Timeseries(
            self._records(self.bundle),
            fail_schema=first_schema,
        )
        report, capture, _metadata, observed = self._run(timeseries=timeseries)
        self._validate(report, capture)
        self.assertEqual(report["acquisition_status"], "acquisition_failed_closed")
        self.assertEqual(report["timeseries_request_count"], 1)
        self.assertEqual(len(observed.calls), 1)
        self.assertEqual(report["request_rows"][0]["status"], "failed_closed")
        self.assertEqual(report["request_rows"][1]["status"], "not_attempted")
        self.assertIsNone(capture)
        self.assertFalse(report["normalized_capture_persisted"])
        self.assertNotIn("download narrative", json.dumps(report))

    def test_download_metadata_symbol_and_window_mismatches_fail_closed(self):
        cases: list[tuple[str, _Timeseries]] = []
        cases.append(
            (
                "schema",
                _Timeseries(self._records(self.bundle), metadata_schema="mbo"),
            )
        )
        symbol_records = self._records(self.bundle)
        symbol_records["mbp-1"][0]["symbol"] = "WRONG"
        cases.append(("symbol", _Timeseries(symbol_records)))
        window_records = self._records(self.bundle)
        mbp_request = next(
            row
            for row in self.bundle.request_manifest["requests"]
            if row["schema"] == "mbp-1"
        )
        window_records["mbp-1"][0]["ts_recv"] = mbp_request["end_ns"]
        cases.append(("window", _Timeseries(window_records)))

        for name, timeseries in cases:
            with self.subTest(name=name):
                report, capture, _metadata, _timeseries = self._run(
                    timeseries=timeseries
                )
                self._validate(report, capture)
                self.assertEqual(
                    report["acquisition_status"],
                    "acquisition_failed_closed",
                )
                self.assertIsNone(capture)
                self.assertFalse(report["request_substitution_attempted"])

    def test_zero_request_date_makes_no_provider_calls_and_emits_empty_capture(self):
        bundle = self._build_bundle(candidate_count=3)
        quote_authorization = self._quote_authorization(bundle)
        quote_report = build_zero_request_report(
            self.quote_contract,
            self.capture_contract,
            bundle,
            quote_authorization,
            generated_at=datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
            workflow_run_id=QUOTE_RUN_ID,
            workflow_run_attempt=1,
        )
        authorization = self._acquisition_authorization(
            bundle,
            quote_authorization,
            quote_report,
        )
        metadata = _Metadata(fail_method="get_cost")
        timeseries = _Timeseries({})
        report, capture = run_exact_acquisition(
            self.contract,
            self.quote_contract,
            self.capture_contract,
            bundle,
            quote_authorization,
            quote_report,
            authorization,
            _Client(metadata, timeseries),
            generated_at=datetime(2026, 8, 24, 12, 30, tzinfo=UTC),
            workflow_run_id=ACQUISITION_RUN_ID,
            workflow_run_attempt=1,
            sdk_version=SDK_VERSION,
        )
        self._validate(
            report,
            capture,
            bundle=bundle,
            quote_authorization=quote_authorization,
            quote_report=quote_report,
            authorization=authorization,
        )
        self.assertEqual(metadata.calls, [])
        self.assertEqual(timeseries.calls, [])
        self.assertEqual(report["acquisition_status"], "not_applicable_zero_requests")
        self.assertTrue(report["acquisition_gate_passed"])
        self.assertEqual(capture["opportunity_count"], 0)
        self.assertEqual(capture["captures"], [])

        direct_report, direct_capture = build_zero_request_result(
            self.contract,
            self.quote_contract,
            self.capture_contract,
            bundle,
            quote_authorization,
            quote_report,
            authorization,
            generated_at=datetime(2026, 8, 24, 12, 30, tzinfo=UTC),
            workflow_run_id=ACQUISITION_RUN_ID,
            workflow_run_attempt=1,
        )
        self.assertEqual((direct_report, direct_capture), (report, capture))

    def test_pre_provider_failure_and_execution_context_are_exact(self):
        report = build_unavailable_report(
            self.contract,
            self.quote_contract,
            self.capture_contract,
            self.bundle,
            self.quote_authorization,
            self.quote_report,
            self.authorization,
            generated_at=datetime(2026, 8, 24, 12, 30, tzinfo=UTC),
            workflow_run_id=ACQUISITION_RUN_ID,
            workflow_run_attempt=1,
            sdk_version="not_loaded",
            error_stage="credential",
            error_kind="missing_databento_api_key",
        )
        self._validate(report, None)
        self.assertEqual(report["metadata_call_count"], 0)
        self.assertEqual(report["timeseries_request_count"], 0)
        self.assertEqual(report["acquisition_status"], "unavailable_before_provider")

        validate_execution_context(
            self.authorization,
            repository=EXPECTED_REPOSITORY,
            freeze_run_id=FREEZE_RUN_ID,
            freeze_run_attempt=1,
            freeze_artifact_name="prospective-opportunity-freeze-2026-08-24",
            quote_run_id=QUOTE_RUN_ID,
            quote_run_attempt=1,
            quote_artifact_name=self.quote_artifact_name,
            workflow_run_id=ACQUISITION_RUN_ID,
            workflow_run_attempt=1,
        )
        with self.assertRaisesRegex(ValueError, "quote provenance"):
            validate_execution_context(
                self.authorization,
                repository=EXPECTED_REPOSITORY,
                freeze_run_id=FREEZE_RUN_ID,
                freeze_run_attempt=1,
                freeze_artifact_name="prospective-opportunity-freeze-2026-08-24",
                quote_run_id="987654320",
                quote_run_attempt=1,
                quote_artifact_name=self.quote_artifact_name,
                workflow_run_id=ACQUISITION_RUN_ID,
                workflow_run_attempt=1,
            )
        with self.assertRaisesRegex(ValueError, "rerun"):
            validate_execution_context(
                self.authorization,
                repository=EXPECTED_REPOSITORY,
                freeze_run_id=FREEZE_RUN_ID,
                freeze_run_attempt=1,
                freeze_artifact_name="prospective-opportunity-freeze-2026-08-24",
                quote_run_id=QUOTE_RUN_ID,
                quote_run_attempt=1,
                quote_artifact_name=self.quote_artifact_name,
                workflow_run_id=ACQUISITION_RUN_ID,
                workflow_run_attempt=2,
            )

    def test_report_tampering_and_retrospective_scope_expansion_are_rejected(self):
        report, capture, _metadata, _timeseries = self._run()
        changed = copy.deepcopy(report)
        changed["preflight"]["total_quoted_cost_usd"] = "0"
        changed = _rehash(changed)
        with self.assertRaisesRegex(ValueError, "preflight"):
            self._validate(changed, capture)

        changed = copy.deepcopy(report)
        changed["ross_actions_or_recaps_loaded"] = True
        changed = _rehash(changed)
        with self.assertRaisesRegex(ValueError, "must remain false"):
            self._validate(changed, capture)

        with self.assertRaisesRegex(ValueError, "missing capture"):
            self._validate(report, None)

        second_schema = str(self.bundle.request_manifest["requests"][1]["schema"])
        failed, failed_capture, _metadata, _timeseries = self._run(
            timeseries=_Timeseries(
                self._records(self.bundle),
                fail_schema=second_schema,
            )
        )
        self.assertIsNone(failed_capture)
        skipped_prefix = copy.deepcopy(failed)
        skipped_prefix["request_rows"][0] = {
            "request_id": self.bundle.request_manifest["requests"][0]["request_id"],
            "schema": self.bundle.request_manifest["requests"][0]["schema"],
            "status": "not_attempted",
            "request_completed": False,
            "metadata_matches": False,
            "record_count": None,
            "ephemeral_file_sha256": None,
        }
        skipped_prefix["timeseries_request_count"] = 1
        skipped_prefix = _rehash(skipped_prefix)
        with self.assertRaisesRegex(ValueError, "manifest-order prefix"):
            self._validate(skipped_prefix, None)

    def test_cli_authorization_is_provider_free_write_once_and_missing_key_is_safe(self):
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
            quote_authorization_path = root / "quote-authorization.json"
            quote_authorization_path.write_text(
                json.dumps(self.quote_authorization),
                encoding="utf-8",
            )
            quote_report_path = root / "quote-report.json"
            quote_report_path.write_text(json.dumps(self.quote_report), encoding="utf-8")
            authorization_path = root / "acquisition-authorization.json"
            env = {
                key: value
                for key, value in os.environ.items()
                if "DATABENTO" not in key and "ALPACA" not in key
            }
            current_pythonpath = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = str(ROOT / "src") + (
                os.pathsep + current_pythonpath if current_pythonpath else ""
            )
            chain_args = [
                "--bundle-dir",
                str(bundle_dir),
                "--quote-authorization",
                str(quote_authorization_path),
                "--quote-report",
                str(quote_report_path),
            ]
            authorize_args = [
                sys.executable,
                str(SCRIPT),
                "authorize",
                *chain_args,
                "--repository",
                EXPECTED_REPOSITORY,
                "--quote-artifact-name",
                self.quote_artifact_name,
                "--output",
                str(authorization_path),
            ]
            completed = subprocess.run(
                authorize_args,
                cwd=ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(completed.stdout), self.authorization)
            repeated = subprocess.run(
                authorize_args,
                cwd=ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(repeated.returncode, 0)

            report_path = root / "acquisition-report.json"
            capture_path = root / "market-input-capture.json"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "acquire",
                    *chain_args,
                    "--authorization",
                    str(authorization_path),
                    "--repository",
                    EXPECTED_REPOSITORY,
                    "--freeze-run-id",
                    FREEZE_RUN_ID,
                    "--freeze-run-attempt",
                    "1",
                    "--freeze-artifact-name",
                    "prospective-opportunity-freeze-2026-08-24",
                    "--quote-run-id",
                    QUOTE_RUN_ID,
                    "--quote-run-attempt",
                    "1",
                    "--quote-artifact-name",
                    self.quote_artifact_name,
                    "--workflow-run-id",
                    ACQUISITION_RUN_ID,
                    "--workflow-run-attempt",
                    "1",
                    "--report-output",
                    str(report_path),
                    "--capture-output",
                    str(capture_path),
                ],
                cwd=ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self._validate(report, None)
            self.assertEqual(report["acquisition_status"], "unavailable_before_provider")
            self.assertFalse(capture_path.exists())

    def test_workflow_push_is_provider_free_and_dispatch_is_exact(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("push:", text)
        self.assertNotIn("schedule:", text)
        self.assertIn("github.event_name == 'push'", text)
        self.assertIn("github.event_name == 'workflow_dispatch'", text)
        for value in (
            "authorization_commit_sha",
            "authorization_path",
            "quote_authorization_path",
            "freeze_run_id",
            "freeze_run_attempt",
            "quote_run_id",
            "quote_run_attempt",
            "actions/download-artifact@v4",
            "databento==0.83.0",
            "GITHUB_RUN_ATTEMPT",
            "DATABENTO_API_KEY",
            "acquisition_gate_passed",
            "prospective-market-input-acquisition-consumed-",
            "Refuse an acquisition authorization already consumed",
        ):
            self.assertIn(value, text)
        self.assertNotIn("historical.batch", text)
        self.assertNotIn("live.subscribe", text)
        push_job, acquisition_job = text.split(
            "  acquire-exact-quoted-bundle:",
            maxsplit=1,
        )
        self.assertNotIn("DATABENTO_API_KEY", push_job)
        self.assertNotIn("acquire_prospective_market_inputs.py acquire", push_job)
        self.assertIn("DATABENTO_API_KEY", acquisition_job)
        upload_step = acquisition_job.split(
            "      - name: Enforce complete normalized capture gate",
            maxsplit=1,
        )[0]
        self.assertNotIn("*.dbn", upload_step)

    def test_registration_audit_is_hash_bound_and_inert(self):
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
        self.assertFalse(execution["exact_acquisition_authorization_created"])
        self.assertFalse(execution["provider_preflight_run"])
        self.assertFalse(execution["provider_timeseries_run"])
        authority = audit["authority_boundary"]
        self.assertFalse(authority["provider_call_run"])
        self.assertFalse(authority["provider_credential_loaded"])
        self.assertFalse(authority["provider_download_run"])
        self.assertEqual(authority["databento_credit_used_usd"], "0")
        self.assertFalse(authority["broker_order_submitted"])
        self.assertFalse(authority["runtime_authority_created"])


if __name__ == "__main__":
    unittest.main()
