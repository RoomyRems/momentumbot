"""Bounded, label-blind Databento execution for the frozen behavioral cohort.

The module is deliberately inert without a separately published, parent-bound
authorization file.  It quotes every frozen request before the first download,
performs one pass with no retries, replays each stream twice, and persists only
sanitized cohort aggregates and cryptographic digests.
"""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping, Protocol, Sequence

from momentumbot.research import databento_feature_diagnostic_v03 as v03
from momentumbot.research import databento_fill_cancel_repair_v01 as repair
from momentumbot.research.databento_quote import SDK_VERSION
from momentumbot.research.databento_smoke import (
    RuntimeConstants,
    _decimal,
    _finish_report,
    _integer,
    _iso_z,
    _metadata_value,
)
from momentumbot.research.microstructure_behavioral_comparison import (
    PROTOCOL_CONTENT_SHA256,
    build_behavioral_comparison,
    validate_behavioral_registration,
)
from momentumbot.research.microstructure_contract import (
    CanonicalDepthEvent,
    canonical_fingerprint,
    file_sha256,
)
from momentumbot.research.microstructure_features import (
    CausalMicrostructureFeatureEngine,
    REGISTERED_WINDOWS_NS,
)


SCHEMA_VERSION = 1
COHORT_ID = "microstructure-behavioral-cohort-v0.1"
COHORT_CONTENT_SHA256 = (
    "2f97f8f2916113cf3e29fe398da7f38d72c1db0b79704cadb0b635ea062a939e"
)
COHORT_FILE_SHA256 = (
    "7889f16956225c8ec2e8a021b36527cf10403c87b9d4b3a02f318c6b28ae21e6"
)
PROTOCOL_FILE_SHA256 = (
    "d8e9bea2e6482dd885735bce2694026cedd38f7068ad58132d5e61eb2aa3c872"
)
PROTOCOL_SOURCE_FILE_SHA256 = (
    "595889e2eb778b3006b80929728d3b7ec9c887b85e661ea46a38089b7edcb4df"
)
FEATURE_ENGINE_SOURCE_FILE_SHA256 = (
    "07e2db045c9187e4bab46e7d25c546668c2c7b8d01f78c58ec36e88e48f1628e"
)
REPAIR_SOURCE_FILE_SHA256 = (
    "8ec8c10a489c46840ca980f71cc3f55f0367a5c3673600773ae1b12812f19a83"
)
PUBLISHED_COHORT_COMMIT_SHA = "0b16e07a7f9ee5938e654c29ad07486c1473c856"
PUBLISHED_COHORT_TREE_SHA = "4ae2852bffd75f06ee86cd9275b71eb2b54a924b"
EXECUTION_AUTHORIZATION_ID = "microstructure-behavioral-cohort-v0.1-execution"
ARTIFACT_TYPE = "sanitized_databento_microstructure_behavioral_cohort_v0.1"
MAX_PREFLIGHT_COST_USD = Decimal("0.25")
MAX_PREFLIGHT_BILLABLE_SIZE_BYTES = 225_000_000
DATASET = "XNAS.ITCH"
SCHEMA = "mbo"
STYPE_IN = "raw_symbol"
REQUEST_COUNT = 5
OPPORTUNITY_COUNT = 10
_ROOT = Path(__file__).resolve().parents[3]
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_ISO_NS = re.compile(
    r"^(?P<seconds>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<fraction>\d{1,9}))?Z$"
)


SafeDiagnosticFailure = v03.SafeDiagnosticFailure
SAFE_ERROR_CODES = v03.SAFE_ERROR_CODES


class MetadataAPI(Protocol):
    def get_billable_size(self, **kwargs: object) -> object: ...
    def get_cost(self, **kwargs: object) -> object: ...


class TimeseriesAPI(Protocol):
    def get_range(self, **kwargs: object) -> object: ...


class HistoricalClient(Protocol):
    metadata: MetadataAPI
    timeseries: TimeseriesAPI


@dataclass(frozen=True, slots=True)
class CohortRequest:
    request_id: str
    trading_date: str
    symbols: tuple[str, ...]
    start: str
    end: str

    def mapping(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "trading_date": self.trading_date,
            "symbols": list(self.symbols),
            "dataset": DATASET,
            "schema": SCHEMA,
            "start": self.start,
            "end": self.end,
            "stype_in": STYPE_IN,
        }

    def kwargs(self) -> dict[str, object]:
        return {
            "dataset": DATASET,
            "schema": SCHEMA,
            "symbols": list(self.symbols),
            "stype_in": STYPE_IN,
            "start": self.start,
            "end": self.end,
        }


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _load_object(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def _parse_ns(value: str) -> int:
    match = _ISO_NS.fullmatch(value)
    if match is None:
        raise ValueError("receive timestamp must be canonical UTC nanoseconds")
    whole = datetime.fromisoformat(match.group("seconds")).replace(tzinfo=UTC)
    fraction = (match.group("fraction") or "").ljust(9, "0")
    return int(whole.timestamp()) * 1_000_000_000 + int(fraction or "0")


def _price_nanos(value: object) -> int:
    parsed = Decimal(str(value)) * Decimal(1_000_000_000)
    if parsed != parsed.to_integral_value() or parsed <= 0:
        raise ValueError("breakout price must convert exactly to positive nanodollars")
    return int(parsed)


def _verify_frozen_sources() -> None:
    expected = {
        "src/momentumbot/research/microstructure_behavioral_comparison.py": (
            PROTOCOL_SOURCE_FILE_SHA256
        ),
        "src/momentumbot/research/microstructure_features.py": (
            FEATURE_ENGINE_SOURCE_FILE_SHA256
        ),
        "src/momentumbot/research/databento_fill_cancel_repair_v01.py": (
            REPAIR_SOURCE_FILE_SHA256
        ),
    }
    for relative, expected_sha in expected.items():
        if file_sha256(_ROOT / relative) != expected_sha:
            raise ValueError(f"frozen behavioral source changed: {relative}")


def _requests(payload: Mapping[str, object]) -> tuple[CohortRequest, ...]:
    surface = _mapping(payload.get("request_surface"), "request surface")
    rows = surface.get("requests")
    if not isinstance(rows, list) or len(rows) != REQUEST_COUNT:
        raise ValueError("cohort must retain exactly five requests")
    parsed: list[CohortRequest] = []
    for row in rows:
        item = _mapping(row, "request")
        symbols = item.get("symbols")
        if not isinstance(symbols, list) or not symbols or symbols != sorted(set(symbols)):
            raise ValueError("request symbols must be sorted and unique")
        if item.get("dataset") != DATASET or item.get("schema") != SCHEMA:
            raise ValueError("request dataset or schema changed")
        if item.get("stype_in") != STYPE_IN:
            raise ValueError("request input symbology changed")
        parsed.append(
            CohortRequest(
                request_id=str(item.get("request_id")),
                trading_date=str(item.get("trading_date")),
                symbols=tuple(str(symbol) for symbol in symbols),
                start=str(item.get("start")),
                end=str(item.get("end")),
            )
        )
    if surface.get("exact_request_count") != REQUEST_COUNT:
        raise ValueError("cohort request count changed")
    return tuple(parsed)


def validate_cohort(payload: Mapping[str, object]) -> None:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "cohort_id": COHORT_ID,
        "artifact_type": (
            "preregistered_unarmed_label_blind_microstructure_behavioral_cohort"
        ),
        "runtime_strategy_effect": "none_shadow_only",
        "provider_request_authorized": False,
        "provider_purchase_authorized": False,
        "execution_file_present": False,
        "policy_promotion_eligible": False,
        "profitability_claim_eligible": False,
        "feature_threshold_selection_permitted": False,
        "horizon_selection_permitted": False,
        "retrospective_labels_allowed_in_runtime": False,
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise ValueError(f"cohort {field} changed")
    claimed = payload.get("content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if claimed != COHORT_CONTENT_SHA256 or canonical_fingerprint(unsigned) != claimed:
        raise ValueError("cohort fingerprint changed")
    summary = _mapping(payload.get("cohort_summary"), "cohort summary")
    if summary.get("opportunity_count") != OPPORTUNITY_COUNT:
        raise ValueError("cohort opportunity count changed")
    opportunities = payload.get("opportunities")
    if not isinstance(opportunities, list) or len(opportunities) != OPPORTUNITY_COUNT:
        raise ValueError("cohort opportunities changed")
    requests = _requests(payload)
    exact_symbols = {
        (request.trading_date, symbol)
        for request in requests
        for symbol in request.symbols
    }
    observed_symbols = {
        (str(row.get("trading_date")), str(row.get("symbol")))
        for row in opportunities
        if isinstance(row, Mapping)
    }
    if observed_symbols != exact_symbols:
        raise ValueError("cohort request surface no longer covers exact opportunities")
    gate = _mapping(payload.get("future_execution_gate"), "future execution gate")
    expected_gate = {
        "status": "unarmed_exact_requests_and_caps_frozen",
        "new_parent_bound_execution_file_required": True,
        "authorization_only_direct_child_required": True,
        "first_github_actions_attempt_only": True,
        "exact_request_count_authorized_now": 0,
        "provider_cost_authorized_now_usd": "0",
        "provider_bytes_authorized_now": 0,
        "hard_preflight_cost_ceiling_usd": "0.25",
        "hard_preflight_billable_size_ceiling_bytes": 225_000_000,
        "all_five_requests_quoted_before_first_timeseries_call": True,
        "zero_timeseries_calls_if_either_aggregate_ceiling_exceeded": True,
        "automatic_retry_authorized": False,
        "partial_cohort_substitution_authorized": False,
        "batch_or_live_endpoint_authorized": False,
        "raw_market_data_publication_authorized": False,
        "feature_value_publication_authorized": False,
        "broker_or_order_change_authorized": False,
        "strategy_or_threshold_change_authorized": False,
    }
    for field, expected_value in expected_gate.items():
        if gate.get(field) != expected_value:
            raise ValueError(f"cohort execution gate {field} changed")


def load_cohort(path: str | Path) -> dict[str, object]:
    source = Path(path)
    if file_sha256(source) != COHORT_FILE_SHA256:
        raise ValueError("cohort file hash changed")
    payload = _load_object(source)
    validate_cohort(payload)
    return payload


def load_protocol(path: str | Path) -> dict[str, object]:
    source = Path(path)
    if file_sha256(source) != PROTOCOL_FILE_SHA256:
        raise ValueError("behavioral protocol file hash changed")
    payload = _load_object(source)
    validate_behavioral_registration(payload)
    return payload


def validate_execution_authorization(payload: Mapping[str, object]) -> None:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "execution_authorization_id": EXECUTION_AUTHORIZATION_ID,
        "artifact_type": "explicit_one_shot_databento_behavioral_cohort_authorization",
        "cohort_id": COHORT_ID,
        "cohort_content_sha256": COHORT_CONTENT_SHA256,
        "behavioral_protocol_content_sha256": PROTOCOL_CONTENT_SHA256,
        "provider_purchase_authorized": True,
        "exact_request_count_authorized": REQUEST_COUNT,
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
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise ValueError(f"behavioral cohort authorization {field} changed")
    parent = payload.get("authorized_push_parent_sha")
    if not isinstance(parent, str) or _SHA40.fullmatch(parent) is None:
        raise ValueError("behavioral cohort authorization parent SHA is invalid")
    statement = payload.get("explicit_user_authorization")
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError("explicit user authorization is required")
    claimed = payload.get("content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if (
        not isinstance(claimed, str)
        or _SHA64.fullmatch(claimed) is None
        or canonical_fingerprint(unsigned) != claimed
    ):
        raise ValueError("behavioral cohort authorization fingerprint mismatch")


def load_execution_authorization(path: str | Path) -> dict[str, object]:
    payload = _load_object(path)
    validate_execution_authorization(payload)
    return payload


def _run_preflight(
    client: HistoricalClient,
    requests: Sequence[CohortRequest],
) -> tuple[dict[str, object], list[dict[str, str]]]:
    rows: list[dict[str, object]] = []
    total_cost = Decimal("0")
    total_size = 0
    try:
        for request in requests:
            size = _integer(
                client.metadata.get_billable_size(**request.kwargs()),
                "billable size",
            )
            cost = _decimal(
                client.metadata.get_cost(**request.kwargs()),
                "quoted cost",
            )
            rows.append(
                {
                    **request.mapping(),
                    "quoted_cost_usd": format(cost, "f"),
                    "billable_size_bytes": size,
                }
            )
            total_cost += cost
            total_size += size
    except Exception:
        return (
            {
                "request_count_expected": len(requests),
                "request_count_quoted": len(rows),
                "quote_rows": rows,
                "total_quoted_cost_usd": None,
                "total_billable_size_bytes": None,
                "hard_cost_ceiling_usd": format(MAX_PREFLIGHT_COST_USD, "f"),
                "hard_billable_size_ceiling_bytes": MAX_PREFLIGHT_BILLABLE_SIZE_BYTES,
                "preflight_passed": False,
            },
            [{
                "failure_phase": "preflight",
                "safe_error_code": "preflight_metadata_query_failed",
            }],
        )
    passed = (
        len(rows) == len(requests)
        and total_cost <= MAX_PREFLIGHT_COST_USD
        and total_size <= MAX_PREFLIGHT_BILLABLE_SIZE_BYTES
    )
    return (
        {
            "request_count_expected": len(requests),
            "request_count_quoted": len(rows),
            "quote_rows": rows,
            "total_quoted_cost_usd": format(total_cost, "f"),
            "total_billable_size_bytes": total_size,
            "hard_cost_ceiling_usd": format(MAX_PREFLIGHT_COST_USD, "f"),
            "hard_billable_size_ceiling_bytes": MAX_PREFLIGHT_BILLABLE_SIZE_BYTES,
            "preflight_passed": passed,
        },
        [] if passed else [{
            "failure_phase": "preflight",
            "safe_error_code": "preflight_budget_rejected",
        }],
    )


def _base_report(
    authorization: Mapping[str, object],
    *,
    generated_at: datetime,
    sdk_version: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "cohort_id": COHORT_ID,
        "cohort_content_sha256": COHORT_CONTENT_SHA256,
        "behavioral_protocol_content_sha256": PROTOCOL_CONTENT_SHA256,
        "execution_authorization_id": EXECUTION_AUTHORIZATION_ID,
        "execution_authorization_content_sha256": authorization["content_sha256"],
        "authorized_push_parent_sha": authorization["authorized_push_parent_sha"],
        "published_cohort_commit_sha": PUBLISHED_COHORT_COMMIT_SHA,
        "published_cohort_tree_sha": PUBLISHED_COHORT_TREE_SHA,
        "protocol_source_file_sha256": PROTOCOL_SOURCE_FILE_SHA256,
        "feature_engine_source_file_sha256": FEATURE_ENGINE_SOURCE_FILE_SHA256,
        "repair_source_file_sha256": REPAIR_SOURCE_FILE_SHA256,
        "artifact_type": ARTIFACT_TYPE,
        "generated_at": _iso_z(generated_at),
        "provider": "databento",
        "dataset": DATASET,
        "schema": SCHEMA,
        "venue": "XNAS",
        "sdk_version": sdk_version,
        "provider_credential_persisted": False,
        "raw_market_data_persisted": False,
        "raw_market_data_uploaded": False,
        "feature_snapshot_values_persisted": False,
        "per_opportunity_feature_values_persisted": False,
        "derived_behavioral_values_persisted": False,
        "sanitized_cohort_aggregates_persisted": True,
        "batch_or_live_endpoint_called": False,
        "automatic_retry_attempted": False,
        "partial_cohort_substitution_attempted": False,
        "retrospective_labels_loaded": False,
        "ross_actions_or_labels_loaded": False,
        "pnl_or_later_prices_loaded": False,
        "feature_threshold_selected": False,
        "feature_horizon_selected": False,
        "strategy_or_threshold_change_made": False,
        "broker_or_order_change_made": False,
        "actual_billing_known": False,
        "runtime_authority_created": False,
        "policy_promotion_eligible": False,
    }


def build_unavailable_report(
    cohort: Mapping[str, object],
    protocol: Mapping[str, object],
    authorization: Mapping[str, object],
    *,
    generated_at: datetime,
    sdk_version: str,
    failure_phase: str,
    safe_error_code: str,
) -> dict[str, object]:
    validate_cohort(cohort)
    validate_behavioral_registration(protocol)
    validate_execution_authorization(authorization)
    report = _base_report(
        authorization,
        generated_at=generated_at,
        sdk_version=sdk_version,
    )
    report.update(
        {
            "preflight": {
                "request_count_expected": REQUEST_COUNT,
                "request_count_quoted": 0,
                "quote_rows": [],
                "total_quoted_cost_usd": None,
                "total_billable_size_bytes": None,
                "hard_cost_ceiling_usd": "0.25",
                "hard_billable_size_ceiling_bytes": 225_000_000,
                "preflight_passed": False,
            },
            "timeseries_request_count": 0,
            "downloads": [],
            "cohort_aggregate": None,
            "errors": [SafeDiagnosticFailure(failure_phase, safe_error_code).mapping()],
            "raw_temp_directory_empty_before_cleanup": True,
            "raw_temp_directory_removed": True,
            "diagnostic_observation_complete": False,
            "all_requests_succeeded": False,
            "safe_failure_classified": True,
        }
    )
    return _finish_report(report)


def _mapped_records(store: object) -> Iterable[object]:
    try:
        frame = store.to_df(
            map_symbols=True,
            pretty_ts=False,
            pretty_px=False,
        )
        if "ts_recv" not in frame.columns:
            frame = frame.reset_index()
        if "symbol" not in frame.columns:
            raise ValueError("mapped symbol column missing")
        return frame.itertuples(index=False, name="MappedMbo")
    except SafeDiagnosticFailure:
        raise
    except Exception:
        raise SafeDiagnosticFailure("record", "record_payload_invalid") from None


def _snapshot_pair(
    pair: tuple[CausalMicrostructureFeatureEngine, CausalMicrostructureFeatureEngine],
    *,
    checkpoint_ns: int,
    quantity: int,
    breakout_nanos: int,
) -> dict[str, object]:
    try:
        snapshots = tuple(
            engine.snapshot(
                as_of_ts_recv_ns=checkpoint_ns,
                hypothetical_order_sizes=(quantity,),
                breakout_level_nanos=breakout_nanos,
            )
            for engine in pair
        )
    except Exception:
        raise SafeDiagnosticFailure("feature_snapshot", "feature_snapshot_invariant") from None
    if snapshots[0] != snapshots[1]:
        raise SafeDiagnosticFailure("completion", "independent_replay_diverged")
    return snapshots[0]


def _aggregate_comparisons(comparisons: Sequence[Mapping[str, object]]) -> dict[str, object]:
    metric_counts: dict[tuple[int, str, str], Counter[str]] = defaultdict(Counter)
    walk_counts: dict[tuple[int, str, str], Counter[str]] = defaultdict(Counter)
    digest = hashlib.sha256()
    for comparison in comparisons:
        digest.update(str(comparison["content_sha256"]).encode("ascii"))
        digest.update(b"\n")
        horizons = comparison.get("horizons")
        if not isinstance(horizons, list):
            raise SafeDiagnosticFailure("completion", "feature_output_invariant")
        for horizon in horizons:
            row = _mapping(horizon, "comparison horizon")
            horizon_ns = _integer(row.get("horizon_ns"), "horizon")
            metrics = row.get("metrics")
            walks = row.get("depth_walk")
            if not isinstance(metrics, list) or not isinstance(walks, list):
                raise SafeDiagnosticFailure("completion", "feature_output_invariant")
            for metric in metrics:
                item = _mapping(metric, "comparison metric")
                key = (horizon_ns, str(item.get("metric_id")), str(item.get("value_type")))
                metric_counts[key][str(item.get("direction"))] += 1
                metric_counts[key]["available"] += int(item.get("available") is True)
                metric_counts[key]["availability_unavailable"] += int(
                    item.get("available") is not True
                )
            for walk in walks:
                walk_item = _mapping(walk, "depth walk")
                direction = str(walk_item.get("direction"))
                fields = walk_item.get("fields")
                if not isinstance(fields, list):
                    raise SafeDiagnosticFailure("completion", "feature_output_invariant")
                for field in fields:
                    item = _mapping(field, "depth-walk field")
                    key = (horizon_ns, direction, str(item.get("field")))
                    walk_counts[key][str(item.get("direction"))] += 1
                    walk_counts[key]["available"] += int(item.get("available") is True)
                    walk_counts[key]["availability_unavailable"] += int(
                        item.get("available") is not True
                    )
    def rows(source: Mapping[tuple[int, str, str], Counter[str]]) -> list[dict[str, object]]:
        output: list[dict[str, object]] = []
        for (horizon, first, second), counts in sorted(source.items()):
            output.append(
                {
                    "horizon_ns": horizon,
                    "id": first,
                    "kind": second,
                    "available_count": counts["available"],
                    "unavailable_count": counts["availability_unavailable"],
                    "increase_count": counts["increase"],
                    "decrease_count": counts["decrease"],
                    "unchanged_count": counts["unchanged"],
                    "unavailable_direction_count": counts["unavailable"],
                }
            )
        return output
    return {
        "opportunity_count": len(comparisons),
        "horizon_count": len(REGISTERED_WINDOWS_NS),
        "all_horizons_reported_together": True,
        "comparison_sequence_digest_sha256": digest.hexdigest(),
        "metric_direction_counts": rows(metric_counts),
        "depth_walk_direction_counts": rows(walk_counts),
        "independent_feature_replay_exact": True,
        "confirmation_or_adverse_classification_emitted": False,
        "hidden_buyer_or_seller_classification_emitted": False,
    }


def extract_request_comparisons(
    store: object,
    *,
    request: CohortRequest,
    opportunities: Sequence[Mapping[str, object]],
    runtime: RuntimeConstants,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    pending: dict[str, list[tuple[int, int, str, int]]] = defaultdict(list)
    snapshots: dict[int, dict[str, object]] = defaultdict(dict)
    for index, opportunity in enumerate(opportunities):
        symbol = str(opportunity.get("symbol"))
        anchor = _parse_ns(str(opportunity.get("anchor_receive_time")))
        pending[symbol].append((anchor, index, "pre", 0))
        for horizon in REGISTERED_WINDOWS_NS:
            pending[symbol].append((anchor + horizon, index, "post", horizon))
    for rows in pending.values():
        rows.sort()

    engines: dict[
        tuple[str, int, int],
        tuple[CausalMicrostructureFeatureEngine, CausalMicrostructureFeatureEngine],
    ] = {}
    symbol_scopes: dict[str, set[tuple[str, int, int]]] = defaultdict(set)
    record_count = 0
    atomic_event_count = 0
    translated_event_count = 0

    def emit_before(symbol: str, before_ns: int | None) -> None:
        rows = pending[symbol]
        while rows and (before_ns is None or rows[0][0] < before_ns):
            checkpoint, index, kind, horizon = rows.pop(0)
            scopes = symbol_scopes[symbol]
            if len(scopes) != 1:
                raise SafeDiagnosticFailure("completion", "no_complete_snapshot")
            key = next(iter(scopes))
            opportunity = opportunities[index]
            snapshot = _snapshot_pair(
                engines[key],
                checkpoint_ns=checkpoint,
                quantity=_integer(
                    opportunity.get("prospective_order_quantity"),
                    "prospective order quantity",
                    minimum=1,
                ),
                breakout_nanos=_price_nanos(opportunity.get("breakout_level")),
            )
            snapshots[index]["pre" if kind == "pre" else str(horizon)] = snapshot

    records = _mapped_records(store)
    for event in v03.iter_instrument_mbo_events(records, runtime=runtime):
        atomic_event_count += 1
        record_count += len(event)
        symbols = {str(getattr(record, "symbol")) for record in event}
        if len(symbols) != 1:
            raise SafeDiagnosticFailure("record", "record_payload_invalid")
        symbol = next(iter(symbols))
        if symbol not in request.symbols:
            raise SafeDiagnosticFailure("record", "record_payload_invalid")
        event_min = min(_integer(getattr(record, "ts_recv"), "ts_recv", minimum=1) for record in event)
        event_max = max(_integer(getattr(record, "ts_recv"), "ts_recv", minimum=1) for record in event)
        if any(event_min <= row[0] < event_max for row in pending[symbol]):
            raise SafeDiagnosticFailure("feature_snapshot", "feature_snapshot_invariant")
        emit_before(symbol, event_min)
        publisher_id, instrument_id = v03._event_scope(event[0])
        scope = (symbol, publisher_id, instrument_id)
        symbol_scopes[symbol].add(scope)
        if len(symbol_scopes[symbol]) != 1:
            raise SafeDiagnosticFailure("record", "record_payload_invalid")
        pair = engines.setdefault(
            scope,
            (CausalMicrostructureFeatureEngine(), CausalMicrostructureFeatureEngine()),
        )
        translated = repair.translate_xnas_instrument_event(
            event,
            symbol=symbol,
            runtime=runtime,
        )
        translated_event_count += len(translated.ordered_events)
        try:
            for engine in pair:
                for item in translated.ordered_events:
                    if isinstance(item, CanonicalDepthEvent):
                        engine.ingest_depth(item)
                    else:
                        engine.ingest_tape(item)
        except Exception:
            raise SafeDiagnosticFailure("book_replay", "book_state_invariant") from None

    for symbol in request.symbols:
        emit_before(symbol, None)
        if pending[symbol]:
            raise SafeDiagnosticFailure("completion", "no_complete_snapshot")

    comparisons: list[dict[str, object]] = []
    for index, opportunity in enumerate(opportunities):
        rows = snapshots[index]
        if set(rows) != {"pre", *(str(value) for value in REGISTERED_WINDOWS_NS)}:
            raise SafeDiagnosticFailure("completion", "no_complete_snapshot")
        try:
            comparison = build_behavioral_comparison(
                opportunity_id=str(opportunity.get("opportunity_id")),
                anchor_recv_ts_ns=_parse_ns(str(opportunity.get("anchor_receive_time"))),
                breakout_level_nanos=_price_nanos(opportunity.get("breakout_level")),
                pre_snapshot=_mapping(rows["pre"], "pre snapshot"),
                post_snapshots_by_horizon={
                    horizon: _mapping(rows[str(horizon)], "post snapshot")
                    for horizon in REGISTERED_WINDOWS_NS
                },
            )
        except SafeDiagnosticFailure:
            raise
        except Exception:
            raise SafeDiagnosticFailure("completion", "feature_output_invariant") from None
        comparisons.append(comparison)
    return comparisons, {
        "request_id": request.request_id,
        "trading_date": request.trading_date,
        "symbol_count": len(request.symbols),
        "opportunity_count": len(opportunities),
        "record_count": record_count,
        "atomic_instrument_event_count": atomic_event_count,
        "translated_canonical_event_count": translated_event_count,
        "independent_feature_replay_exact": True,
    }


def _download_and_replay(
    client: HistoricalClient,
    request: CohortRequest,
    path: Path,
    opportunities: Sequence[Mapping[str, object]],
    runtime: RuntimeConstants,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    try:
        store = client.timeseries.get_range(path=str(path), **request.kwargs())
    except Exception:
        raise SafeDiagnosticFailure("provider_download", "provider_download_failed") from None
    if not path.is_file() or path.stat().st_size <= 0:
        raise SafeDiagnosticFailure("downloaded_file", "download_empty")
    try:
        dataset = _metadata_value(getattr(store, "metadata", None), "dataset")
        schema = _metadata_value(getattr(store, "metadata", None), "schema")
    except Exception:
        raise SafeDiagnosticFailure("metadata", "metadata_mismatch") from None
    if dataset != DATASET.lower() or schema != SCHEMA:
        raise SafeDiagnosticFailure("metadata", "metadata_mismatch")
    comparisons, summary = extract_request_comparisons(
        store,
        request=request,
        opportunities=opportunities,
        runtime=runtime,
    )
    return comparisons, {
        **summary,
        "schema": SCHEMA,
        "ephemeral_file_sha256": file_sha256(path),
        "file_nonempty": True,
        "metadata_matches_request": True,
    }


def run_behavioral_cohort_diagnostic(
    cohort: Mapping[str, object],
    protocol: Mapping[str, object],
    authorization: Mapping[str, object],
    client: HistoricalClient,
    *,
    generated_at: datetime,
    sdk_version: str,
    runtime: RuntimeConstants,
) -> dict[str, object]:
    validate_cohort(cohort)
    validate_behavioral_registration(protocol)
    validate_execution_authorization(authorization)
    _verify_frozen_sources()
    if sdk_version != SDK_VERSION:
        raise ValueError(f"Databento SDK version must be {SDK_VERSION}")
    requests = _requests(cohort)
    preflight, errors = _run_preflight(client, requests)
    report = _base_report(
        authorization,
        generated_at=generated_at,
        sdk_version=sdk_version,
    )
    report.update(
        {
            "preflight": preflight,
            "timeseries_request_count": 0,
            "downloads": [],
            "cohort_aggregate": None,
            "errors": errors,
            "raw_temp_directory_empty_before_cleanup": True,
            "raw_temp_directory_removed": True,
        }
    )
    if preflight.get("preflight_passed") is not True:
        report.update(
            {
                "diagnostic_observation_complete": False,
                "all_requests_succeeded": False,
                "safe_failure_classified": bool(errors),
            }
        )
        return _finish_report(report)

    opportunities = cohort.get("opportunities")
    assert isinstance(opportunities, list)
    all_comparisons: list[dict[str, object]] = []
    temp = tempfile.TemporaryDirectory(prefix="momentumbot-databento-behavioral-")
    temp_path = Path(temp.name)
    try:
        for index, request in enumerate(requests):
            request_opportunities = [
                row
                for row in opportunities
                if isinstance(row, Mapping)
                and row.get("trading_date") == request.trading_date
                and row.get("symbol") in request.symbols
            ]
            path = temp_path / f"request-{index:02d}.dbn.zst"
            try:
                report["timeseries_request_count"] = int(report["timeseries_request_count"]) + 1
                comparisons, summary = _download_and_replay(
                    client,
                    request,
                    path,
                    request_opportunities,
                    runtime,
                )
                all_comparisons.extend(comparisons)
                report["downloads"].append(summary)
            except SafeDiagnosticFailure as exc:
                errors.append({"request_id": request.request_id, **exc.mapping()})
                break
            except Exception:
                errors.append(
                    {
                        "request_id": request.request_id,
                        "failure_phase": "completion",
                        "safe_error_code": "unclassified_fail_closed",
                    }
                )
                break
            finally:
                path.unlink(missing_ok=True)
    finally:
        report["raw_temp_directory_empty_before_cleanup"] = not any(temp_path.iterdir())
        temp_name = temp.name
        temp.cleanup()
        report["raw_temp_directory_removed"] = not Path(temp_name).exists()

    downloads = report["downloads"]
    all_succeeded = (
        len(downloads) == REQUEST_COUNT
        and len(all_comparisons) == OPPORTUNITY_COUNT
        and not errors
    )
    if all_succeeded:
        report["cohort_aggregate"] = _aggregate_comparisons(all_comparisons)
    terminal_failure = (
        len(errors) == 1
        and int(report["timeseries_request_count"]) == len(downloads) + 1
    )
    report.update(
        {
            "diagnostic_observation_complete": all_succeeded or terminal_failure,
            "all_requests_succeeded": all_succeeded,
            "safe_failure_classified": bool(errors)
            and all(row.get("safe_error_code") in SAFE_ERROR_CODES for row in errors),
        }
    )
    return _finish_report(report)


def _walk_keys(value: object) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def validate_behavioral_cohort_report(payload: Mapping[str, object]) -> None:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "cohort_id": COHORT_ID,
        "cohort_content_sha256": COHORT_CONTENT_SHA256,
        "behavioral_protocol_content_sha256": PROTOCOL_CONTENT_SHA256,
        "artifact_type": ARTIFACT_TYPE,
        "published_cohort_commit_sha": PUBLISHED_COHORT_COMMIT_SHA,
        "published_cohort_tree_sha": PUBLISHED_COHORT_TREE_SHA,
        "protocol_source_file_sha256": PROTOCOL_SOURCE_FILE_SHA256,
        "feature_engine_source_file_sha256": FEATURE_ENGINE_SOURCE_FILE_SHA256,
        "repair_source_file_sha256": REPAIR_SOURCE_FILE_SHA256,
        "sanitized_cohort_aggregates_persisted": True,
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise ValueError(f"behavioral cohort report {field} changed")
    for field in (
        "provider_credential_persisted",
        "raw_market_data_persisted",
        "raw_market_data_uploaded",
        "feature_snapshot_values_persisted",
        "per_opportunity_feature_values_persisted",
        "derived_behavioral_values_persisted",
        "batch_or_live_endpoint_called",
        "automatic_retry_attempted",
        "partial_cohort_substitution_attempted",
        "retrospective_labels_loaded",
        "ross_actions_or_labels_loaded",
        "pnl_or_later_prices_loaded",
        "feature_threshold_selected",
        "feature_horizon_selected",
        "strategy_or_threshold_change_made",
        "broker_or_order_change_made",
        "actual_billing_known",
        "runtime_authority_created",
        "policy_promotion_eligible",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"behavioral cohort report {field} must remain false")
    if payload.get("raw_temp_directory_empty_before_cleanup") is not True:
        raise ValueError("behavioral cohort temporary directory was not empty")
    if payload.get("raw_temp_directory_removed") is not True:
        raise ValueError("behavioral cohort temporary directory was not removed")
    request_count = _integer(payload.get("timeseries_request_count"), "request count")
    if request_count > REQUEST_COUNT:
        raise ValueError("behavioral cohort request count exceeded registration")
    forbidden = {
        "raw_records",
        "order_id",
        "instrument_id",
        "publisher_id",
        "feature_snapshots",
        "pre_snapshot",
        "post_snapshot",
        "provider_error_message",
        "exception_message",
        "error_message",
        "ross_action",
        "ross_label",
        "pnl",
        "later_price",
        "pre_value",
        "post_value",
        "post_minus_pre",
        "worst_price_nanos",
        "notional_price_nanos_shares",
    }
    if set(_walk_keys(payload)) & forbidden:
        raise ValueError("behavioral cohort report contains a prohibited field")
    preflight = _mapping(payload.get("preflight"), "preflight")
    if preflight.get("request_count_expected") != REQUEST_COUNT:
        raise ValueError("behavioral cohort preflight count changed")
    quoted = _integer(preflight.get("request_count_quoted"), "quoted count")
    if quoted < 0 or quoted > REQUEST_COUNT:
        raise ValueError("behavioral cohort quote count invalid")
    quote_rows = preflight.get("quote_rows")
    if not isinstance(quote_rows, list) or len(quote_rows) != quoted:
        raise ValueError("behavioral cohort quote rows invalid")
    if quoted == REQUEST_COUNT:
        for row, request in zip(quote_rows, _requests_for_report_validation()):
            item = _mapping(row, "quote row")
            for field, expected_value in request.mapping().items():
                if item.get(field) != expected_value:
                    raise ValueError(f"behavioral cohort quote row {field} changed")
        total_cost = _decimal(preflight.get("total_quoted_cost_usd"), "total cost")
        total_size = _integer(
            preflight.get("total_billable_size_bytes"),
            "total billable size",
        )
        expected_pass = (
            total_cost <= MAX_PREFLIGHT_COST_USD
            and total_size <= MAX_PREFLIGHT_BILLABLE_SIZE_BYTES
        )
        if preflight.get("preflight_passed") is not expected_pass:
            raise ValueError("behavioral cohort preflight result changed")
    downloads = payload.get("downloads")
    errors = payload.get("errors")
    if not isinstance(downloads, list) or len(downloads) > REQUEST_COUNT:
        raise ValueError("behavioral cohort downloads invalid")
    if not isinstance(errors, list) or len(errors) > 1:
        raise ValueError("behavioral cohort errors invalid")
    if payload.get("all_requests_succeeded") is True:
        if quoted != REQUEST_COUNT or preflight.get("preflight_passed") is not True:
            raise ValueError("behavioral cohort success lacks complete preflight")
        if request_count != REQUEST_COUNT or len(downloads) != REQUEST_COUNT or errors:
            raise ValueError("behavioral cohort success shape changed")
        aggregate = _mapping(payload.get("cohort_aggregate"), "cohort aggregate")
        if aggregate.get("opportunity_count") != OPPORTUNITY_COUNT:
            raise ValueError("behavioral cohort aggregate count changed")
        if aggregate.get("independent_feature_replay_exact") is not True:
            raise ValueError("behavioral cohort independent replay changed")
        metric_rows = aggregate.get("metric_direction_counts")
        walk_rows = aggregate.get("depth_walk_direction_counts")
        if not isinstance(metric_rows, list) or len(metric_rows) != 36:
            raise ValueError("behavioral cohort metric aggregate shape changed")
        if not isinstance(walk_rows, list) or len(walk_rows) != 24:
            raise ValueError("behavioral cohort depth-walk aggregate shape changed")
        for row in [*metric_rows, *walk_rows]:
            item = _mapping(row, "aggregate row")
            if (
                _integer(item.get("available_count"), "available count")
                + _integer(item.get("unavailable_count"), "unavailable count")
                != OPPORTUNITY_COUNT
            ):
                raise ValueError("behavioral cohort aggregate count changed")
    elif errors and any(row.get("safe_error_code") not in SAFE_ERROR_CODES for row in errors):
        raise ValueError("behavioral cohort failure was not safely classified")
    claimed = payload.get("content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if not isinstance(claimed, str) or canonical_fingerprint(unsigned) != claimed:
        raise ValueError("behavioral cohort report fingerprint mismatch")


def _requests_for_report_validation() -> tuple[CohortRequest, ...]:
    """Return the exact frozen surface without trusting values in a report."""
    cohort = _load_object(_ROOT / "research/strategy/microstructure-behavioral-cohort-v0.1.json")
    validate_cohort(cohort)
    return _requests(cohort)


__all__ = [
    "CohortRequest",
    "EXECUTION_AUTHORIZATION_ID",
    "MAX_PREFLIGHT_BILLABLE_SIZE_BYTES",
    "MAX_PREFLIGHT_COST_USD",
    "RuntimeConstants",
    "build_unavailable_report",
    "extract_request_comparisons",
    "load_cohort",
    "load_execution_authorization",
    "load_protocol",
    "run_behavioral_cohort_diagnostic",
    "validate_behavioral_cohort_report",
    "validate_execution_authorization",
]
