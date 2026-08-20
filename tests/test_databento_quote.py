from __future__ import annotations

import copy
import hashlib
import json
import unittest
from datetime import UTC, datetime
from pathlib import Path

from momentumbot.research.databento_quote import (
    MAX_SMOKE_QUOTE_USD,
    REQUIRED_SCHEMAS,
    SDK_VERSION,
    build_quote_requests,
    build_unavailable_report,
    load_quote_contract,
    run_metadata_quote,
    validate_quote_contract,
    validate_quote_report,
)
from momentumbot.research.microstructure_contract import canonical_fingerprint


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "databento-microstructure-metadata-quote-v0.1.json"
)
PARENT = ROOT / "research" / "strategy" / "level2-tape-feasibility-v0.1.json"
WORKFLOW = ROOT / ".github" / "workflows" / "databento-microstructure-quote.yml"
AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-metadata-quote-v0.1-2026-08-20.json"
)
EXPECTED_CONTENT_SHA256 = (
    "1c9401e49d500c38715dd61c7f180e3eb868d71b9a28926caa4b399d335f45b1"
)


class FakeMetadata:
    def __init__(self, *, cost: str = "0.10") -> None:
        self.cost = cost
        self.calls: list[tuple[str, dict[str, object]]] = []

    def _record(self, name: str, kwargs: dict[str, object]) -> None:
        self.calls.append((name, kwargs))

    def list_datasets(self, **kwargs: object) -> list[str]:
        self._record("list_datasets", kwargs)
        return ["XNAS.ITCH"]

    def list_schemas(self, **kwargs: object) -> list[str]:
        self._record("list_schemas", kwargs)
        return list(REQUIRED_SCHEMAS)

    def list_fields(self, *, schema: str, encoding: str) -> list[dict[str, str]]:
        self._record("list_fields", {"schema": schema, "encoding": encoding})
        return [{"name": "ts_event", "type": "uint64"}]

    def list_unit_prices(self, **kwargs: object) -> list[dict[str, object]]:
        self._record("list_unit_prices", kwargs)
        return [{"mode": "historical", "schema": "mbo", "unit_price": 1.0}]

    def get_dataset_condition(self, **kwargs: object) -> list[dict[str, str]]:
        self._record("get_dataset_condition", kwargs)
        return [{"date": "2026-07-10", "condition": "available"}]

    def get_dataset_range(self, **kwargs: object) -> dict[str, str]:
        self._record("get_dataset_range", kwargs)
        return {"start": "2018-05-01", "end": "2026-08-20"}

    def get_billable_size(self, **kwargs: object) -> int:
        self._record("get_billable_size", kwargs)
        return 100

    def get_cost(self, **kwargs: object) -> float:
        self._record("get_cost", kwargs)
        return float(self.cost)


class FakeSymbology:
    def __init__(self, *, unresolved: str | None = None) -> None:
        self.unresolved = unresolved
        self.calls: list[tuple[str, dict[str, object]]] = []

    def resolve(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("resolve", kwargs))
        symbol = str(list(kwargs["symbols"])[0])
        if symbol == self.unresolved:
            return {"result": {}, "not_found": [symbol], "partial": []}
        return {
            "result": {symbol: [{"d0": str(kwargs["start_date"]), "s": "123"}]},
            "not_found": [],
            "partial": [],
        }


class FakeClient:
    def __init__(self, *, cost: str = "0.10", unresolved: str | None = None) -> None:
        self.metadata = FakeMetadata(cost=cost)
        self.symbology = FakeSymbology(unresolved=unresolved)


class DatabentoQuoteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load_quote_contract(CONTRACT, parent_path=PARENT)

    def test_contract_is_hash_bound_and_download_surface_is_disabled(self):
        self.assertEqual(self.contract["content_sha256"], EXPECTED_CONTENT_SHA256)
        unsigned = {
            key: value for key, value in self.contract.items() if key != "content_sha256"
        }
        self.assertEqual(canonical_fingerprint(unsigned), EXPECTED_CONTENT_SHA256)
        self.assertFalse(self.contract["authorization"]["timeseries_download_authorized"])
        self.assertFalse(self.contract["authorization"]["batch_job_authorized"])
        self.assertEqual(MAX_SMOKE_QUOTE_USD, 12.5)

        changed = copy.deepcopy(self.contract)
        changed["authorization"]["timeseries_download_authorized"] = True
        changed["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in changed.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "timeseries_download_authorized changed"):
            validate_quote_contract(changed)

    def test_twenty_requests_are_exact_and_ten_minute_aligned(self):
        requests = build_quote_requests(self.contract)
        self.assertEqual(len(requests), 20)
        intj = [row for row in requests if row.symbol == "INTJ"]
        self.assertEqual([row.schema for row in intj], list(REQUIRED_SCHEMAS))
        self.assertEqual(intj[0].start, "2026-07-10T00:00:00Z")
        self.assertEqual(intj[0].end, "2026-07-10T14:10:00Z")
        self.assertEqual(intj[1].start, "2026-07-10T10:50:00Z")
        self.assertEqual(intj[1].end, "2026-07-10T14:10:00Z")
        self.assertEqual(intj[3].end, "2026-07-11T00:00:00Z")
        for row in requests:
            for value in (row.start, row.end):
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                self.assertEqual(parsed.minute % 10, 0)
                self.assertEqual(parsed.second, 0)

    def test_metadata_only_quote_passes_and_is_sanitized(self):
        client = FakeClient()
        report = run_metadata_quote(
            self.contract,
            client,
            generated_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
            sdk_version=SDK_VERSION,
        )
        validate_quote_report(report)
        self.assertTrue(report["g0_quote_passed"])
        self.assertEqual(report["quote_metrics"]["request_count"], 20)
        self.assertEqual(
            report["quote_metrics"]["conservative_total_quoted_cost_usd"],
            "2.0",
        )
        self.assertEqual(report["quote_metrics"]["total_billable_size_bytes"], 2000)
        self.assertFalse(report["timeseries_or_batch_endpoint_called"])
        self.assertFalse(report["download_authorized_by_this_artifact"])
        self.assertNotIn("123", json.dumps(report, sort_keys=True))

        metadata_names = [name for name, _kwargs in client.metadata.calls]
        self.assertEqual(metadata_names.count("get_cost"), 20)
        self.assertEqual(metadata_names.count("get_billable_size"), 20)
        self.assertEqual(len(client.symbology.calls), 4)
        self.assertNotIn("get_range", metadata_names)
        self.assertNotIn("submit_job", metadata_names)

    def test_quote_over_ceiling_and_unresolved_symbol_fail_closed(self):
        expensive = run_metadata_quote(
            self.contract,
            FakeClient(cost="1.00"),
            generated_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
            sdk_version=SDK_VERSION,
        )
        self.assertFalse(expensive["g0_quote_passed"])
        self.assertFalse(
            expensive["pass_conditions"][
                "conservative_five_schema_sum_within_12_50_usd"
            ]
        )

        unresolved = run_metadata_quote(
            self.contract,
            FakeClient(unresolved="GMM"),
            generated_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
            sdk_version=SDK_VERSION,
        )
        self.assertFalse(unresolved["g0_quote_passed"])
        self.assertFalse(
            unresolved["pass_conditions"]["all_four_symbols_resolved_point_in_time"]
        )

    def test_unavailable_report_preserves_failure_without_authority(self):
        report = build_unavailable_report(
            self.contract,
            generated_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
            error_stage="credential",
            error_kind="missing_DATABENTO_API_KEY",
        )
        validate_quote_report(report)
        self.assertFalse(report["g0_quote_passed"])
        self.assertEqual(report["quote_rows"], [])
        self.assertEqual(report["metadata_query_cost_usd"], "0")

    def test_workflow_pins_sdk_scopes_secret_and_has_no_download_command(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("databento==0.83.0", text)
        self.assertIn("DATABENTO_API_KEY: ${{ secrets.DATABENTO_API_KEY }}", text)
        self.assertIn("quote_databento_microstructure.py", text)
        self.assertNotIn("timeseries.get_range", text)
        self.assertNotIn("batch.submit_job", text)
        self.assertNotIn("live.subscribe", text)

    def test_registration_audit_binds_metadata_only_child(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        claimed = audit["content_sha256"]
        unsigned = {
            key: value for key, value in audit.items() if key != "content_sha256"
        }
        self.assertEqual(canonical_fingerprint(unsigned), claimed)
        self.assertEqual(audit["contract"]["content_sha256"], EXPECTED_CONTENT_SHA256)
        for row in audit["bound_files"]:
            self.assertEqual(
                hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest(),
                row["file_sha256"],
            )
        self.assertFalse(audit["execution_status"]["provider_quote_run"])
        self.assertFalse(audit["authority_boundary"]["market_data_downloaded"])
        self.assertFalse(audit["authority_boundary"]["credits_spent"])


if __name__ == "__main__":
    unittest.main()
