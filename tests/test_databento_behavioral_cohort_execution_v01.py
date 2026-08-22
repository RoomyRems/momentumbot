from __future__ import annotations

import copy
import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from momentumbot.research.databento_behavioral_cohort_execution_v01 import (
    COHORT_CONTENT_SHA256,
    CohortRequest,
    EXECUTION_AUTHORIZATION_ID,
    OPPORTUNITY_COUNT,
    REQUEST_COUNT,
    RuntimeConstants,
    SafeDiagnosticFailure,
    extract_request_comparisons,
    load_cohort,
    load_protocol,
    run_behavioral_cohort_diagnostic,
    validate_behavioral_cohort_report,
    validate_execution_authorization,
)
from momentumbot.research.databento_quote import SDK_VERSION
from momentumbot.research.microstructure_contract import canonical_fingerprint
from momentumbot.research.microstructure_contract import file_sha256


ROOT = Path(__file__).resolve().parents[1]
COHORT = ROOT / "research/strategy/microstructure-behavioral-cohort-v0.1.json"
PROTOCOL = ROOT / "research/strategy/microstructure-behavioral-comparison-v0.1.json"
FUTURE_AUTHORIZATION = (
    ROOT / "research/strategy/microstructure-behavioral-cohort-v0.1-execution.json"
)
WORKFLOW = (
    ROOT
    / ".github/workflows/databento-microstructure-behavioral-cohort-v01.yml"
)
SCRIPT = ROOT / "scripts/run_databento_microstructure_behavioral_cohort_v01.py"
REGISTRATION_AUDIT = (
    ROOT
    / "research/data-audits/"
    "databento-microstructure-behavioral-cohort-v0.1-"
    "harness-registration-2026-08-21.json"
)
SAFE_FAILURE_AUDIT = (
    ROOT
    / "research/data-audits/"
    "databento-microstructure-behavioral-cohort-v0.1-"
    "run-32550318387-safe-failure-2026-08-21.json"
)
GENERATED_AT = datetime(2026, 8, 21, 23, tzinfo=UTC)
RUNTIME = RuntimeConstants(
    f_last=128,
    f_tob=64,
    f_snapshot=32,
    f_bad_ts_recv=8,
    undef_price=9_223_372_036_854_775_807,
)


def _parse_ns(value: str) -> int:
    seconds, fraction = value.removesuffix("Z").split(".")
    whole = datetime.fromisoformat(seconds).replace(tzinfo=UTC)
    return int(whole.timestamp()) * 1_000_000_000 + int(fraction.ljust(9, "0"))


def _authorization(parent: str = "a" * 40) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "execution_authorization_id": EXECUTION_AUTHORIZATION_ID,
        "artifact_type": "explicit_one_shot_databento_behavioral_cohort_authorization",
        "cohort_id": "microstructure-behavioral-cohort-v0.1",
        "cohort_content_sha256": COHORT_CONTENT_SHA256,
        "behavioral_protocol_content_sha256": (
            "7409973d369876d29a020785cc2f48bc945129d705648f793d693667dcdd3802"
        ),
        "authorized_push_parent_sha": parent,
        "explicit_user_authorization": (
            "Synthetic deterministic unit-test authorization; no provider call."
        ),
        "provider_purchase_authorized": True,
        "exact_request_count_authorized": 5,
        "hard_preflight_cost_ceiling_usd": "0.25",
        "hard_preflight_billable_size_ceiling_bytes": 225_000_000,
        "all_requests_quoted_before_first_download": True,
        "first_github_actions_attempt_only": True,
        "automatic_retry_authorized": False,
        "partial_cohort_substitution_authorized": False,
        "batch_or_live_endpoint_authorized": False,
        "raw_market_data_publication_authorized": False,
        "feature_value_publication_authorized": False,
        "broker_or_order_change_authorized": False,
        "strategy_or_threshold_change_authorized": False,
    }
    payload["content_sha256"] = canonical_fingerprint(payload)
    return payload


def _record(
    *,
    symbol: str,
    instrument_id: int,
    sequence: int,
    ts_recv: int,
    action: str,
    side: str,
    flags: int,
    price: int | None = None,
    size: int = 0,
    order_id: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        symbol=symbol,
        ts_event=ts_recv - 10,
        ts_recv=ts_recv,
        publisher_id=1,
        instrument_id=instrument_id,
        channel_id=0,
        sequence=sequence,
        action=action,
        side=side,
        price=RUNTIME.undef_price if price is None else price,
        size=size,
        order_id=order_id,
        flags=flags,
    )


class FakeFrame:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows
        self.columns = [
            "symbol",
            "ts_event",
            "ts_recv",
            "publisher_id",
            "instrument_id",
            "channel_id",
            "sequence",
            "action",
            "side",
            "price",
            "size",
            "order_id",
            "flags",
        ]

    def reset_index(self):
        return self

    def itertuples(self, *, index: bool, name: str):
        del index, name
        return iter(self.rows)


class FakeStore:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows
        self.metadata = SimpleNamespace(dataset="XNAS.ITCH", schema="mbo")
        self.to_df_calls: list[dict[str, object]] = []

    def to_df(
        self,
        *,
        map_symbols: bool,
        pretty_ts: bool,
        price_type: str,
    ) -> FakeFrame:
        self.to_df_calls.append(
            {
                "map_symbols": map_symbols,
                "pretty_ts": pretty_ts,
                "price_type": price_type,
            }
        )
        return FakeFrame(self.rows)


def _rows_for_request(
    opportunities: list[dict[str, object]],
    symbols: list[str],
) -> list[SimpleNamespace]:
    rows: list[SimpleNamespace] = []
    for instrument_id, symbol in enumerate(symbols, start=100):
        symbol_opportunities = [row for row in opportunities if row["symbol"] == symbol]
        earliest = min(_parse_ns(str(row["anchor_receive_time"])) for row in symbol_opportunities)
        breakout = int(float(symbol_opportunities[0]["breakout_level"]) * 1_000_000_000)
        rows.extend(
            [
                _record(
                    symbol=symbol,
                    instrument_id=instrument_id,
                    sequence=0,
                    ts_recv=earliest - 20_000_000_000,
                    action="R",
                    side="N",
                    flags=RUNTIME.f_last,
                ),
                _record(
                    symbol=symbol,
                    instrument_id=instrument_id,
                    sequence=1,
                    ts_recv=earliest - 19_000_000_000,
                    action="A",
                    side="B",
                    flags=RUNTIME.f_last,
                    price=breakout - 10_000_000,
                    size=10_000,
                    order_id=instrument_id * 10 + 1,
                ),
                _record(
                    symbol=symbol,
                    instrument_id=instrument_id,
                    sequence=2,
                    ts_recv=earliest - 18_000_000_000,
                    action="A",
                    side="A",
                    flags=RUNTIME.f_last,
                    price=breakout + 10_000_000,
                    size=10_000,
                    order_id=instrument_id * 10 + 2,
                ),
            ]
        )
    return sorted(rows, key=lambda row: (row.ts_recv, row.instrument_id, row.sequence))


class FakeMetadata:
    def __init__(self, *, cost: float = 0.01, size: int = 1_000_000) -> None:
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
        opportunities: list[dict[str, object]],
        *,
        fail_at: int | None = None,
    ) -> None:
        self.opportunities = opportunities
        self.fail_at = fail_at
        self.calls: list[dict[str, object]] = []
        self.stores: list[FakeStore] = []

    def get_range(self, **kwargs: object) -> FakeStore:
        index = len(self.calls)
        self.calls.append(kwargs)
        if index == self.fail_at:
            raise RuntimeError("licensed provider detail must not persist")
        Path(str(kwargs["path"])).write_bytes(b"synthetic DBN placeholder")
        symbols = list(kwargs["symbols"])
        start = str(kwargs["start"])
        date = start[:10]
        opportunities = [
            row
            for row in self.opportunities
            if row["trading_date"] == date and row["symbol"] in symbols
        ]
        store = FakeStore(_rows_for_request(opportunities, symbols))
        self.stores.append(store)
        return store


class FakeClient:
    def __init__(
        self,
        opportunities: list[dict[str, object]],
        *,
        cost: float = 0.01,
        size: int = 1_000_000,
        fail_at: int | None = None,
    ) -> None:
        self.metadata = FakeMetadata(cost=cost, size=size)
        self.timeseries = FakeTimeseries(opportunities, fail_at=fail_at)


class DatabentoBehavioralCohortExecutionV01Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cohort = load_cohort(COHORT)
        cls.protocol = load_protocol(PROTOCOL)
        cls.authorization = _authorization()
        validate_execution_authorization(cls.authorization)

    def run_gate(self, client: FakeClient) -> dict[str, object]:
        return run_behavioral_cohort_diagnostic(
            self.cohort,
            self.protocol,
            self.authorization,
            client,
            generated_at=GENERATED_AT,
            sdk_version=SDK_VERSION,
            runtime=RUNTIME,
        )

    def test_cohort_is_exact_hash_bound_and_harness_is_unarmed(self):
        self.assertEqual(self.cohort["content_sha256"], COHORT_CONTENT_SHA256)
        self.assertEqual(len(self.cohort["opportunities"]), OPPORTUNITY_COUNT)
        self.assertEqual(
            self.cohort["request_surface"]["exact_request_count"],
            REQUEST_COUNT,
        )
        self.assertFalse(self.cohort["provider_purchase_authorized"])
        if FUTURE_AUTHORIZATION.exists():
            validate_execution_authorization(
                json.loads(FUTURE_AUTHORIZATION.read_text(encoding="utf-8"))
            )

    def test_authorization_drift_fails_closed(self):
        for field, value in (
            ("exact_request_count_authorized", 4),
            ("hard_preflight_cost_ceiling_usd", "0.26"),
            ("automatic_retry_authorized", True),
            ("feature_value_publication_authorized", True),
        ):
            payload = copy.deepcopy(self.authorization)
            payload[field] = value
            payload["content_sha256"] = canonical_fingerprint(
                {key: item for key, item in payload.items() if key != "content_sha256"}
            )
            with self.assertRaises(ValueError):
                validate_execution_authorization(payload)

    def test_all_quotes_precede_exact_five_downloads_and_report_is_sanitized(self):
        client = FakeClient(self.cohort["opportunities"])
        report = self.run_gate(client)
        validate_behavioral_cohort_report(report)
        self.assertEqual(len(client.metadata.calls), REQUEST_COUNT * 2)
        self.assertEqual(len(client.timeseries.calls), REQUEST_COUNT)
        self.assertEqual(len(client.timeseries.stores), REQUEST_COUNT)
        for store in client.timeseries.stores:
            self.assertEqual(
                store.to_df_calls,
                [{
                    "map_symbols": True,
                    "pretty_ts": False,
                    "price_type": "fixed",
                }],
            )
        self.assertTrue(report["all_requests_succeeded"])
        self.assertEqual(report["cohort_aggregate"]["opportunity_count"], 10)
        self.assertTrue(
            report["cohort_aggregate"]["independent_feature_replay_exact"]
        )
        rendered = json.dumps(report, sort_keys=True)
        for forbidden in (
            "licensed provider detail",
            "feature_snapshots",
            "pre_value",
            "post_value",
            ".dbn",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_aggregate_budget_rejection_makes_zero_timeseries_calls(self):
        client = FakeClient(self.cohort["opportunities"], cost=0.051)
        report = self.run_gate(client)
        validate_behavioral_cohort_report(report)
        self.assertEqual(len(client.metadata.calls), REQUEST_COUNT * 2)
        self.assertEqual(client.timeseries.calls, [])
        self.assertEqual(
            report["errors"][0]["safe_error_code"],
            "preflight_budget_rejected",
        )

    def test_first_provider_failure_stops_without_retry(self):
        client = FakeClient(self.cohort["opportunities"], fail_at=0)
        report = self.run_gate(client)
        validate_behavioral_cohort_report(report)
        self.assertEqual(len(client.timeseries.calls), 1)
        self.assertEqual(report["downloads"], [])
        self.assertTrue(report["safe_failure_classified"])
        self.assertFalse(report["automatic_retry_attempted"])

    def test_checkpoint_inside_atomic_event_fails_closed(self):
        opportunity = self.cohort["opportunities"][0]
        anchor = _parse_ns(str(opportunity["anchor_receive_time"]))
        symbol = str(opportunity["symbol"])
        first = _record(
            symbol=symbol,
            instrument_id=100,
            sequence=1,
            ts_recv=anchor - 1,
            action="A",
            side="B",
            flags=0,
            price=3_900_000_000,
            size=100,
            order_id=1,
        )
        last = _record(
            symbol=symbol,
            instrument_id=100,
            sequence=1,
            ts_recv=anchor + 1,
            action="A",
            side="A",
            flags=RUNTIME.f_last,
            price=3_920_000_000,
            size=100,
            order_id=2,
        )
        request_row = self.cohort["request_surface"]["requests"][0]
        request = CohortRequest(
            request_id=str(request_row["request_id"]),
            trading_date=str(request_row["trading_date"]),
            symbols=tuple(request_row["symbols"]),
            start=str(request_row["start"]),
            end=str(request_row["end"]),
        )
        with self.assertRaises(SafeDiagnosticFailure) as caught:
            extract_request_comparisons(
                FakeStore([first, last]),
                request=request,
                opportunities=[opportunity],
                runtime=RUNTIME,
            )
        self.assertEqual(caught.exception.code, "feature_snapshot_invariant")

    def test_workflow_is_authorization_only_first_attempt_and_pinned(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("microstructure-behavioral-cohort-v0.1-execution.json", workflow)
        self.assertIn("assert changed == [expected]", workflow)
        self.assertIn("assert parent == before", workflow)
        self.assertIn("databento==0.83.0", workflow)
        self.assertIn("GITHUB_RUN_ATTEMPT", SCRIPT.read_text(encoding="utf-8"))

    def test_registration_does_not_contain_execution_file(self):
        self.assertFalse(self.cohort["execution_file_present"])
        self.assertEqual(
            self.cohort["future_execution_gate"]["exact_request_count_authorized_now"],
            0,
        )

    def test_harness_registration_audit_binds_unarmed_files(self):
        audit = json.loads(REGISTRATION_AUDIT.read_text(encoding="utf-8"))
        self.assertFalse(audit["provider_request_made"])
        self.assertFalse(audit["provider_quote_made"])
        self.assertFalse(audit["execution_authorization_file_present"])
        for bound in audit["bound_files"]:
            self.assertEqual(file_sha256(ROOT / bound["path"]), bound["file_sha256"])
        unsigned = {
            key: value for key, value in audit.items() if key != "content_sha256"
        }
        self.assertEqual(canonical_fingerprint(unsigned), audit["content_sha256"])

    def test_safe_failure_audit_is_hash_bound_and_records_no_retry(self):
        audit = json.loads(SAFE_FAILURE_AUDIT.read_text(encoding="utf-8"))
        attempt = audit["verified_preflight_and_attempt"]
        failure = audit["classified_failure"]
        self.assertEqual(attempt["timeseries_request_count"], 1)
        self.assertFalse(attempt["automatic_retry_attempted"])
        self.assertFalse(failure["all_requests_succeeded"])
        self.assertEqual(failure["safe_error_code"], "record_payload_invalid")
        self.assertFalse(audit["corrective_interpretation"]["provider_rerun_authorized"])
        for bound in audit["bound_files"]:
            self.assertEqual(file_sha256(ROOT / bound["path"]), bound["file_sha256"])
        unsigned = {
            key: value for key, value in audit.items() if key != "content_sha256"
        }
        self.assertEqual(canonical_fingerprint(unsigned), audit["content_sha256"])


if __name__ == "__main__":
    unittest.main()
