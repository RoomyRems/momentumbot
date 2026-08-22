"""Unarmed causal market-input capture for the prospective account panel.

This module freezes and validates the provider-neutral handoff from a future
label-blind opportunity manifest to receive-time L1 quote and trading-status
inputs.  It can derive exact request windows and materialize a hash-bound
capture from already acquired records, but it has no provider client, network
call, credential, order path, or authority to spend Databento credit.
"""

from __future__ import annotations

import json
import re
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

from momentumbot.research.account_chronological_integration import (
    PANEL_ID,
    REGISTERED_DATES,
)
from momentumbot.research.execution_realism import TopOfBookEvent
from momentumbot.research.microstructure_contract import canonical_fingerprint


SCHEMA_VERSION = 1
CONTRACT_ID = "prospective-market-input-capture-v0.1"
CONTRACT_CONTENT_SHA256 = (
    "0435f7d857a3efd12f0e325953b242572ffceb17aa07d421b1e89b7dd95ca774"
)

BRIDGE_CONTRACT_ID = "microstructure-behavioral-execution-bridge-v0.1"
BRIDGE_CONTRACT_CONTENT_SHA256 = (
    "fcafc556b20267a966ed228658a5da8daef2ed58955cf7d981c053acf8491411"
)
BRIDGE_CHECKPOINT_SHA = "392fb0d1fff322bc6ff38d5e416ff9e2b8926fab"
PROSPECTIVE_EXECUTION_CONTRACT_ID = "prospective-management-execution-v0.1"
PROSPECTIVE_EXECUTION_CONTENT_SHA256 = (
    "14812b9f25b5ea7230254ed86b1e0eaa30fffe3dc13b1ee141b19770706090f9"
)
ACCOUNT_CAPTURE_CONTRACT_ID = "account-session-snapshot-capture-v0.1"
ACCOUNT_CAPTURE_CONTENT_SHA256 = (
    "5e967dbbbe2ee53187940f2ea720bd1937a4391710c97043ec03cc80c9b257b7"
)
MICRO_POLICY_FINGERPRINT = (
    "49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa"
)

DATASET = "XNAS.ITCH"
SCHEMAS = ("mbp-1", "status")
STYPE_IN = "raw_symbol"
VENUE_SCOPE = "nasdaq_totalview_single_venue_not_consolidated_nbbo"
PRE_DECISION_QUOTE_NS = 100_000_000
POST_DECISION_CAPTURE_NS = 550_000_000
END_EXCLUSIVE_PAD_NS = 1
PRICE_SCALE = Decimal(1_000_000_000)
UNDEF_PRICE = 9_223_372_036_854_775_807
NEW_YORK = ZoneInfo("America/New_York")

_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.+\-]{0,31}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_KEYS = {
    "ross_action",
    "ross_actions",
    "ross_label",
    "ross_labels",
    "recap",
    "recaps",
    "pnl",
    "profit",
    "loss",
    "later_price",
    "later_prices",
    "outcome",
    "outcomes",
    "selected_horizon",
    "selected_scenario",
    "feature_threshold",
}


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    return value


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return value


def _symbol(value: object) -> str:
    if not isinstance(value, str) or not _SYMBOL.fullmatch(value):
        raise ValueError("symbol must use canonical uppercase US-equity notation")
    return value


def _decimal(value: object, field: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite decimal")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a finite decimal") from exc
    if not parsed.is_finite() or parsed < 0 or (positive and parsed <= 0):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{field} must be finite and {qualifier}")
    return parsed


def _walk_keys(value: object) -> list[str]:
    keys: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            keys.append(str(key).lower())
            keys.extend(_walk_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.extend(_walk_keys(item))
    return keys


def _validate_fingerprint(
    payload: Mapping[str, object],
    *,
    expected: str | None,
    label: str,
) -> str:
    claimed = _sha256(payload.get("content_sha256"), f"{label}.content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    actual = canonical_fingerprint(unsigned)
    if actual != claimed or (expected is not None and claimed != expected):
        raise ValueError(f"{label} content fingerprint changed")
    return claimed


def validate_capture_contract(payload: Mapping[str, object]) -> None:
    expected_scalars = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "artifact_type": "preregistered_unarmed_prospective_l1_status_capture",
        "registration_date": "2026-08-22",
        "registration_status": "registered_before_panel_market_inputs_and_opportunities",
        "runtime_strategy_effect": "prospective_shadow_input_only_after_validation",
    }
    for field, expected in expected_scalars.items():
        if payload.get(field) != expected:
            raise ValueError(f"capture contract {field} changed")
    _validate_fingerprint(
        payload,
        expected=CONTRACT_CONTENT_SHA256,
        label="capture contract",
    )

    parents = _mapping(payload.get("frozen_parents"), "frozen_parents")
    expected_parents = {
        "behavioral_execution_bridge_contract_id": BRIDGE_CONTRACT_ID,
        "behavioral_execution_bridge_content_sha256": (
            BRIDGE_CONTRACT_CONTENT_SHA256
        ),
        "behavioral_execution_bridge_checkpoint_sha": BRIDGE_CHECKPOINT_SHA,
        "prospective_execution_contract_id": PROSPECTIVE_EXECUTION_CONTRACT_ID,
        "prospective_execution_contract_content_sha256": (
            PROSPECTIVE_EXECUTION_CONTENT_SHA256
        ),
        "account_capture_contract_id": ACCOUNT_CAPTURE_CONTRACT_ID,
        "account_capture_contract_content_sha256": ACCOUNT_CAPTURE_CONTENT_SHA256,
        "account_panel_id": PANEL_ID,
        "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
    }
    for field, expected in expected_parents.items():
        if parents.get(field) != expected:
            raise ValueError(f"capture frozen parent {field} changed")

    panel = _mapping(payload.get("prospective_panel"), "prospective_panel")
    if panel.get("registered_dates") != list(REGISTERED_DATES):
        raise ValueError("capture panel dates changed")
    expected_panel = {
        "opportunity_source": "frozen_label_blind_prospective_runtime",
        "opportunity_manifest_frozen_before_provider_quote": True,
        "exact_symbol_date_decision_identity_required": True,
        "main_and_small_accounts_use_same_market_inputs": True,
        "missing_date_or_opportunity_behavior": "retain_unavailable_without_substitution",
    }
    for field, expected in expected_panel.items():
        if panel.get(field) != expected:
            raise ValueError(f"prospective_panel.{field} changed")

    source = _mapping(payload.get("source_scope"), "source_scope")
    expected_source = {
        "provider": "Databento Historical API",
        "dataset": DATASET,
        "schemas": list(SCHEMAS),
        "stype_in": STYPE_IN,
        "venue_scope": VENUE_SCOPE,
        "consolidated_nbbo_claim": False,
        "causal_clock": "ts_recv",
        "request_start_filter_clock": "ts_recv",
        "request_end_is_exclusive": True,
        "mbp1_start_before_earliest_decision_ns": PRE_DECISION_QUOTE_NS,
        "capture_after_latest_decision_ns": POST_DECISION_CAPTURE_NS,
        "end_exclusive_pad_ns": END_EXCLUSIVE_PAD_NS,
        "status_start_rule": "00:00:00Z_on_registered_trading_date",
        "raw_records_persisted_by_registration": False,
    }
    for field, expected in expected_source.items():
        if source.get(field) != expected:
            raise ValueError(f"source_scope.{field} changed")

    semantics = _mapping(payload.get("capture_semantics"), "capture_semantics")
    expected_semantics = {
        "complete_mbp1_updates_required": True,
        "complete_status_updates_required": True,
        "status_is_trading_values": ["Y", "N", "~"],
        "unknown_status_behavior": "unavailable_never_assume_trading",
        "missing_initial_status_behavior": "unavailable_never_assume_trading",
        "status_scope_rule": "same_registered_symbol_date_request_only",
        "status_event_order_tie_breaker": "original_provider_record_order",
        "quote_status_equal_ts_recv_behavior": (
            "quote_unavailable_due_to_cross_schema_order_ambiguity"
        ),
        "non_trading_state_can_fill": False,
        "one_sided_locked_or_crossed_book_behavior": "not_a_usable_quote",
        "quote_price_unit": "integer_nanos",
        "quote_size_unit": "shares",
        "provider_sequence_retained": True,
        "both_execution_scenarios_receive_identical_inputs": True,
        "sip_print_proxy_fallback_allowed": False,
    }
    for field, expected in expected_semantics.items():
        if semantics.get(field) != expected:
            raise ValueError(f"capture_semantics.{field} changed")

    knowledge = _mapping(payload.get("knowledge_boundary"), "knowledge_boundary")
    expected_knowledge = {
        "allowed_opportunity_fields": [
            "opportunity_id",
            "trading_date",
            "symbol",
            "decision_ts_ns",
            "runtime_content_sha256",
        ],
        "raw_transcripts_allowed": False,
        "ross_actions_labels_or_recaps_allowed": False,
        "later_prices_or_pnl_allowed": False,
        "behavioral_aggregate_may_select_requests": False,
        "case_specific_window_override_allowed": False,
        "outcome_driven_retry_or_substitution_allowed": False,
    }
    for field, expected in expected_knowledge.items():
        if knowledge.get(field) != expected:
            raise ValueError(f"knowledge_boundary.{field} changed")

    derivation = _mapping(payload.get("request_derivation"), "request_derivation")
    expected_derivation = {
        "group_by": "registered_trading_date_and_symbol",
        "symbols": (
            "one_exact_symbol_per_request_pair_from_frozen_opportunity_manifest"
        ),
        "mbp1_start": "earliest_decision_ts_ns_minus_100000000",
        "status_start": "registered_trading_date_midnight_utc",
        "shared_end": (
            "latest_decision_ts_ns_plus_550000000_plus_1ns_exclusive_pad"
        ),
        "schemas_reported_together": True,
        "offline_manifest_generation_only": True,
        "metadata_quote_requires_separate_authority": True,
        "timeseries_download_requires_separate_authority": True,
    }
    for field, expected in expected_derivation.items():
        if derivation.get(field) != expected:
            raise ValueError(f"request_derivation.{field} changed")

    authority = _mapping(payload.get("authority_boundary"), "authority_boundary")
    false_fields = (
        "provider_metadata_quote_authorized",
        "provider_request_authorized",
        "provider_purchase_authorized",
        "broker_order_authorized",
        "paper_order_authorized",
        "live_order_authorized",
        "retrospective_labels_allowed",
        "later_prices_or_pnl_allowed",
        "threshold_or_scenario_selection_authorized",
        "runtime_authority_created",
        "policy_promotion_eligible",
        "profitability_claim_eligible",
    )
    for field in false_fields:
        if authority.get(field) is not False:
            raise ValueError(f"authority_boundary.{field} must remain false")
    if authority.get("databento_credit_authorized_usd") != "0":
        raise ValueError("capture registration cannot authorize Databento credit")


def load_capture_contract(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("capture contract must be an object")
    validate_capture_contract(payload)
    return payload


@dataclass(frozen=True, slots=True)
class ProspectiveOpportunity:
    opportunity_id: str
    trading_date: str
    symbol: str
    decision_ts_ns: int
    runtime_content_sha256: str

    def __post_init__(self) -> None:
        if not self.opportunity_id.strip():
            raise ValueError("opportunity_id must be non-empty")
        if self.trading_date not in REGISTERED_DATES:
            raise ValueError("opportunity trading_date is outside the registered panel")
        object.__setattr__(self, "symbol", _symbol(self.symbol))
        _integer(self.decision_ts_ns, "decision_ts_ns", minimum=1)
        _sha256(self.runtime_content_sha256, "runtime_content_sha256")
        local_date = datetime.fromtimestamp(
            self.decision_ts_ns / 1_000_000_000,
            tz=UTC,
        ).astimezone(NEW_YORK).date().isoformat()
        if local_date != self.trading_date:
            raise ValueError("decision timestamp does not fall on the trading date")


def validate_opportunity_manifest(
    payload: Mapping[str, object],
) -> tuple[ProspectiveOpportunity, ...]:
    expected_top_level = {
        "schema_version",
        "artifact_id",
        "artifact_type",
        "panel_id",
        "opportunities",
        "retrospective_labels_loaded",
        "later_prices_or_pnl_loaded",
        "content_sha256",
    }
    if set(payload) != expected_top_level:
        raise ValueError("opportunity manifest fields changed")
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported opportunity manifest schema")
    if payload.get("artifact_type") != "frozen_label_blind_prospective_opportunities":
        raise ValueError("unexpected opportunity manifest type")
    if payload.get("panel_id") != PANEL_ID:
        raise ValueError("opportunity manifest panel changed")
    if payload.get("retrospective_labels_loaded") is not False:
        raise ValueError("opportunity manifest cannot load retrospective labels")
    if payload.get("later_prices_or_pnl_loaded") is not False:
        raise ValueError("opportunity manifest cannot load later prices or P&L")
    forbidden = sorted(set(_walk_keys(payload)) & _FORBIDDEN_KEYS)
    if forbidden:
        raise ValueError(f"opportunity manifest contains forbidden keys: {forbidden}")
    _validate_fingerprint(payload, expected=None, label="opportunity manifest")

    rows = _list(payload.get("opportunities"), "opportunities")
    opportunities: list[ProspectiveOpportunity] = []
    seen: set[str] = set()
    previous: tuple[str, int, str, str] | None = None
    for raw in rows:
        row = _mapping(raw, "opportunity")
        if set(row) != {
            "opportunity_id",
            "trading_date",
            "symbol",
            "decision_ts_ns",
            "runtime_content_sha256",
        }:
            raise ValueError("opportunity row fields changed")
        opportunity = ProspectiveOpportunity(
            opportunity_id=str(row["opportunity_id"]),
            trading_date=str(row["trading_date"]),
            symbol=str(row["symbol"]),
            decision_ts_ns=_integer(row["decision_ts_ns"], "decision_ts_ns", minimum=1),
            runtime_content_sha256=str(row["runtime_content_sha256"]),
        )
        key = (
            opportunity.trading_date,
            opportunity.decision_ts_ns,
            opportunity.symbol,
            opportunity.opportunity_id,
        )
        if opportunity.opportunity_id in seen:
            raise ValueError("opportunity IDs must be unique")
        if previous is not None and key <= previous:
            raise ValueError("opportunities must be in deterministic chronological order")
        seen.add(opportunity.opportunity_id)
        previous = key
        opportunities.append(opportunity)
    return tuple(opportunities)


def _utc_midnight_ns(trading_date: str) -> int:
    return int(
        datetime.fromisoformat(f"{trading_date}T00:00:00+00:00").timestamp()
        * 1_000_000_000
    )


def build_request_manifest(
    contract: Mapping[str, object],
    opportunity_manifest: Mapping[str, object],
) -> dict[str, object]:
    """Derive exact future request rows without making a provider call."""
    validate_capture_contract(contract)
    opportunities = validate_opportunity_manifest(opportunity_manifest)
    by_symbol_date: dict[tuple[str, str], list[ProspectiveOpportunity]] = defaultdict(list)
    for opportunity in opportunities:
        by_symbol_date[(opportunity.trading_date, opportunity.symbol)].append(
            opportunity
        )

    requests: list[dict[str, object]] = []
    for trading_date, symbol in sorted(by_symbol_date):
        rows = by_symbol_date[(trading_date, symbol)]
        symbols = [symbol]
        quote_start = min(row.decision_ts_ns for row in rows) - PRE_DECISION_QUOTE_NS
        end = (
            max(row.decision_ts_ns for row in rows)
            + POST_DECISION_CAPTURE_NS
            + END_EXCLUSIVE_PAD_NS
        )
        requests.extend(
            [
                {
                    "request_id": f"{trading_date}-{symbol}-mbp-1",
                    "trading_date": trading_date,
                    "dataset": DATASET,
                    "schema": "mbp-1",
                    "symbols": symbols,
                    "stype_in": STYPE_IN,
                    "start_ns": quote_start,
                    "end_ns": end,
                    "end_exclusive": True,
                },
                {
                    "request_id": f"{trading_date}-{symbol}-status",
                    "trading_date": trading_date,
                    "dataset": DATASET,
                    "schema": "status",
                    "symbols": symbols,
                    "stype_in": STYPE_IN,
                    "start_ns": _utc_midnight_ns(trading_date),
                    "end_ns": end,
                    "end_exclusive": True,
                },
            ]
        )

    report: dict[str, object] = {
        "schema_version": 1,
        "artifact_id": "prospective-market-input-request-manifest-v0.1",
        "artifact_type": "offline_exact_unquoted_market_input_requests",
        "contract_id": CONTRACT_ID,
        "contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "opportunity_manifest_content_sha256": opportunity_manifest["content_sha256"],
        "opportunity_count": len(opportunities),
        "request_count": len(requests),
        "requests": requests,
        "provider_metadata_quote_made": False,
        "provider_timeseries_request_made": False,
        "provider_purchase_authorized": False,
        "databento_credit_authorized_usd": "0",
        "retrospective_labels_loaded": False,
        "later_prices_or_pnl_loaded": False,
        "runtime_authority": "none_unarmed",
    }
    report["content_sha256"] = canonical_fingerprint(report)
    return report


@dataclass(frozen=True, slots=True)
class CapturedStatusEvent:
    symbol: str
    ts_recv_ns: int
    record_index: int
    action: int
    is_trading: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _symbol(self.symbol))
        _integer(self.ts_recv_ns, "status.ts_recv_ns", minimum=1)
        _integer(self.record_index, "status.record_index")
        _integer(self.action, "status.action", minimum=0)
        if self.action > 14:
            raise ValueError("status.action must be a registered Databento status action")
        if self.is_trading not in {"Y", "N", "~"}:
            raise ValueError("status.is_trading must be Y, N, or ~")


@dataclass(frozen=True, slots=True)
class CapturedQuoteEvent:
    symbol: str
    ts_recv_ns: int
    sequence: int
    bid_px_nanos: int
    bid_size: int
    ask_px_nanos: int
    ask_size: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _symbol(self.symbol))
        _integer(self.ts_recv_ns, "quote.ts_recv_ns", minimum=1)
        _integer(self.sequence, "quote.sequence")
        _integer(self.bid_px_nanos, "quote.bid_px_nanos")
        _integer(self.bid_size, "quote.bid_size")
        _integer(self.ask_px_nanos, "quote.ask_px_nanos")
        _integer(self.ask_size, "quote.ask_size")

    @property
    def usable(self) -> bool:
        return (
            self.bid_px_nanos > 0
            and self.ask_px_nanos > 0
            and self.bid_px_nanos < UNDEF_PRICE
            and self.ask_px_nanos < UNDEF_PRICE
            and self.bid_size > 0
            and self.ask_size > 0
            and self.bid_px_nanos < self.ask_px_nanos
        )


def _status_events(records: Sequence[Mapping[str, object]]) -> tuple[CapturedStatusEvent, ...]:
    result: list[CapturedStatusEvent] = []
    previous: tuple[int, int] | None = None
    for index, row in enumerate(records):
        if set(row) != {"symbol", "ts_recv_ns", "action", "is_trading"}:
            raise ValueError("normalized status record fields changed")
        event = CapturedStatusEvent(
            symbol=str(row.get("symbol", "")),
            ts_recv_ns=_integer(row.get("ts_recv_ns"), "status.ts_recv_ns", minimum=1),
            record_index=index,
            action=_integer(row.get("action"), "status.action"),
            is_trading=str(row.get("is_trading", "")),
        )
        key = (event.ts_recv_ns, event.record_index)
        if previous is not None and key <= previous:
            raise ValueError("status records must remain in receive-time order")
        previous = key
        result.append(event)
    return tuple(result)


def _quote_events(records: Sequence[Mapping[str, object]]) -> tuple[CapturedQuoteEvent, ...]:
    result: list[CapturedQuoteEvent] = []
    previous: tuple[int, int, str] | None = None
    for row in records:
        if set(row) != {
            "symbol",
            "ts_recv_ns",
            "sequence",
            "bid_px_nanos",
            "bid_size",
            "ask_px_nanos",
            "ask_size",
        }:
            raise ValueError("normalized quote record fields changed")
        event = CapturedQuoteEvent(
            symbol=str(row.get("symbol", "")),
            ts_recv_ns=_integer(row.get("ts_recv_ns"), "quote.ts_recv_ns", minimum=1),
            sequence=_integer(row.get("sequence"), "quote.sequence"),
            bid_px_nanos=_integer(row.get("bid_px_nanos"), "quote.bid_px_nanos"),
            bid_size=_integer(row.get("bid_size"), "quote.bid_size"),
            ask_px_nanos=_integer(row.get("ask_px_nanos"), "quote.ask_px_nanos"),
            ask_size=_integer(row.get("ask_size"), "quote.ask_size"),
        )
        key = (event.ts_recv_ns, event.sequence, event.symbol)
        if previous is not None and key <= previous:
            raise ValueError("quote records must remain in receive-time and sequence order")
        previous = key
        result.append(event)
    return tuple(result)


def _request_evidence(
    payload: Mapping[str, object],
    request_manifest: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    if set(payload) != {"requests"}:
        raise ValueError("request evidence fields changed")
    rows = _list(payload.get("requests"), "request_evidence.requests")
    expected_rows = _list(request_manifest.get("requests"), "request_manifest.requests")
    expected = {
        str(_mapping(row, "request").get("request_id")): _mapping(row, "request")
        for row in expected_rows
    }
    result: dict[str, Mapping[str, object]] = {}
    for raw in rows:
        row = _mapping(raw, "request evidence")
        if set(row) != {
            "request_id",
            "dataset",
            "schema",
            "metadata_matches",
            "request_completed",
            "record_count",
        }:
            raise ValueError("request evidence row fields changed")
        request_id = str(row.get("request_id", ""))
        if request_id not in expected or request_id in result:
            raise ValueError("request evidence identity changed")
        if row.get("dataset") != DATASET or row.get("schema") not in SCHEMAS:
            raise ValueError("request evidence provider scope changed")
        if row.get("metadata_matches") is not True:
            raise ValueError("request evidence metadata must match")
        if row.get("request_completed") is not True:
            raise ValueError("capture cannot use an incomplete provider request")
        _integer(row.get("record_count"), "request_evidence.record_count")
        result[request_id] = row
    if set(result) != set(expected):
        raise ValueError("request evidence must cover every exact request")
    return result


def _validate_record_coverage(
    request_manifest: Mapping[str, object],
    evidence: Mapping[str, Mapping[str, object]],
    quotes: Sequence[CapturedQuoteEvent],
    statuses: Sequence[CapturedStatusEvent],
) -> None:
    request_rows = [
        _mapping(row, "request")
        for row in _list(request_manifest.get("requests"), "request_manifest.requests")
    ]
    observed_counts: dict[str, int] = {request_id: 0 for request_id in evidence}
    for schema, records in (("mbp-1", quotes), ("status", statuses)):
        eligible = [row for row in request_rows if row.get("schema") == schema]
        for record in records:
            matches = [
                row
                for row in eligible
                if record.symbol in _list(row.get("symbols"), "request.symbols")
                and _integer(row.get("start_ns"), "request.start_ns")
                <= record.ts_recv_ns
                < _integer(row.get("end_ns"), "request.end_ns")
            ]
            if len(matches) != 1:
                raise ValueError(
                    f"{schema} record must map to exactly one frozen request"
                )
            request_id = str(matches[0]["request_id"])
            observed_counts[request_id] += 1
    for request_id, row in evidence.items():
        expected = _integer(row.get("record_count"), "request_evidence.record_count")
        if observed_counts[request_id] != expected:
            raise ValueError("request evidence record count does not reconcile")


def build_market_input_capture(
    contract: Mapping[str, object],
    opportunity_manifest: Mapping[str, object],
    request_manifest: Mapping[str, object],
    request_evidence: Mapping[str, object],
    quote_records: Sequence[Mapping[str, object]],
    status_records: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Build a label-blind capture from complete already-acquired records."""
    validate_capture_contract(contract)
    opportunities = validate_opportunity_manifest(opportunity_manifest)
    expected_requests = build_request_manifest(contract, opportunity_manifest)
    if request_manifest != expected_requests:
        raise ValueError("request manifest differs from the deterministic contract output")
    evidence = _request_evidence(request_evidence, request_manifest)
    quotes = _quote_events(quote_records)
    statuses = _status_events(status_records)
    _validate_record_coverage(
        request_manifest,
        evidence,
        quotes,
        statuses,
    )

    quotes_by_symbol: dict[str, list[CapturedQuoteEvent]] = defaultdict(list)
    status_by_symbol: dict[str, list[CapturedStatusEvent]] = defaultdict(list)
    for quote in quotes:
        quotes_by_symbol[quote.symbol].append(quote)
    for status in statuses:
        status_by_symbol[status.symbol].append(status)

    captures: list[dict[str, object]] = []
    for opportunity in opportunities:
        start = opportunity.decision_ts_ns - PRE_DECISION_QUOTE_NS
        end = opportunity.decision_ts_ns + POST_DECISION_CAPTURE_NS
        status_request_start = _utc_midnight_ns(opportunity.trading_date)
        symbol_statuses = [
            event
            for event in status_by_symbol.get(opportunity.symbol, [])
            if status_request_start <= event.ts_recv_ns <= end
        ]
        status_times = [event.ts_recv_ns for event in symbol_statuses]
        status_time_set = set(status_times)
        initial_index = bisect_right(status_times, start) - 1
        initial = symbol_statuses[initial_index] if initial_index >= 0 else None
        status_window = [
            event
            for event in symbol_statuses
            if start < event.ts_recv_ns <= end
        ]
        status_known = initial is not None and initial.is_trading in {"Y", "N"}
        unknown_seen = any(event.is_trading == "~" for event in status_window)
        status_complete = status_known and not unknown_seen

        usable_quotes: list[dict[str, object]] = []
        unusable_quote_count = 0
        for quote in quotes_by_symbol.get(opportunity.symbol, []):
            if not start <= quote.ts_recv_ns <= end:
                continue
            if not quote.usable:
                unusable_quote_count += 1
                continue
            if quote.ts_recv_ns in status_time_set:
                unusable_quote_count += 1
                continue
            quote_status_index = bisect_right(status_times, quote.ts_recv_ns) - 1
            current_status = (
                symbol_statuses[quote_status_index]
                if quote_status_index >= 0
                else None
            )
            if current_status is None or current_status.is_trading == "~":
                unusable_quote_count += 1
                continue
            usable_quotes.append(
                {
                    "symbol": quote.symbol,
                    "ts_recv_ns": quote.ts_recv_ns,
                    "sequence": quote.sequence,
                    "bid_price": format(
                        Decimal(quote.bid_px_nanos) / PRICE_SCALE,
                        "f",
                    ),
                    "bid_size": quote.bid_size,
                    "ask_price": format(
                        Decimal(quote.ask_px_nanos) / PRICE_SCALE,
                        "f",
                    ),
                    "ask_size": quote.ask_size,
                        "halted": current_status.is_trading != "Y",
                        "status_ts_recv_ns": current_status.ts_recv_ns,
                        "status_record_index": current_status.record_index,
                        "status_action": current_status.action,
                }
            )

        if not status_complete:
            unusable_quote_count += len(usable_quotes)
            usable_quotes = []

        captures.append(
            {
                "opportunity_id": opportunity.opportunity_id,
                "trading_date": opportunity.trading_date,
                "symbol": opportunity.symbol,
                "decision_ts_ns": opportunity.decision_ts_ns,
                "window_start_ns": start,
                "window_end_ns": end,
                "initial_status": (
                    None
                    if initial is None
                    else {
                        "ts_recv_ns": initial.ts_recv_ns,
                        "record_index": initial.record_index,
                        "action": initial.action,
                        "is_trading": initial.is_trading,
                    }
                ),
                "status_changes": [
                    {
                        "ts_recv_ns": event.ts_recv_ns,
                        "record_index": event.record_index,
                        "action": event.action,
                        "is_trading": event.is_trading,
                    }
                    for event in status_window
                ],
                "status_coverage_complete": status_complete,
                "usable_quote_count": len(usable_quotes),
                "unusable_or_status_unknown_quote_count": unusable_quote_count,
                "quotes": usable_quotes,
                "capture_status": (
                    "complete"
                    if status_complete
                    else "unavailable_status_not_causally_known"
                ),
            }
        )

    report: dict[str, object] = {
        "schema_version": 1,
        "artifact_id": "prospective-market-input-capture-v0.1",
        "artifact_type": "label_blind_receive_time_l1_and_status_capture",
        "contract_id": CONTRACT_ID,
        "contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "opportunity_manifest_content_sha256": opportunity_manifest["content_sha256"],
        "request_manifest_content_sha256": request_manifest["content_sha256"],
        "dataset": DATASET,
        "schemas": list(SCHEMAS),
        "venue_scope": VENUE_SCOPE,
        "opportunity_count": len(opportunities),
        "captures": captures,
        "retrospective_labels_loaded": False,
        "later_prices_or_pnl_loaded": False,
        "sip_print_proxy_used": False,
        "execution_outcomes_computed": False,
        "horizon_or_scenario_selected": False,
        "broker_order_submitted": False,
        "runtime_authority": "none_shadow_input_only",
        "policy_promotion_eligible": False,
        "profitability_claim_eligible": False,
    }
    report["content_sha256"] = canonical_fingerprint(report)
    validate_market_input_capture(report)
    return report


def validate_market_input_capture(payload: Mapping[str, object]) -> None:
    expected_top_level = {
        "schema_version",
        "artifact_id",
        "artifact_type",
        "contract_id",
        "contract_content_sha256",
        "opportunity_manifest_content_sha256",
        "request_manifest_content_sha256",
        "dataset",
        "schemas",
        "venue_scope",
        "opportunity_count",
        "captures",
        "retrospective_labels_loaded",
        "later_prices_or_pnl_loaded",
        "sip_print_proxy_used",
        "execution_outcomes_computed",
        "horizon_or_scenario_selected",
        "broker_order_submitted",
        "runtime_authority",
        "policy_promotion_eligible",
        "profitability_claim_eligible",
        "content_sha256",
    }
    if set(payload) != expected_top_level:
        raise ValueError("market input capture fields changed")
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported market input capture schema")
    if payload.get("artifact_id") != "prospective-market-input-capture-v0.1":
        raise ValueError("unexpected market input capture ID")
    if payload.get("artifact_type") != "label_blind_receive_time_l1_and_status_capture":
        raise ValueError("unexpected market input capture type")
    if payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("market input capture contract changed")
    if payload.get("contract_content_sha256") != CONTRACT_CONTENT_SHA256:
        raise ValueError("market input capture contract hash changed")
    if payload.get("dataset") != DATASET or payload.get("schemas") != list(SCHEMAS):
        raise ValueError("market input capture provider scope changed")
    if payload.get("venue_scope") != VENUE_SCOPE:
        raise ValueError("market input capture venue scope changed")
    _sha256(
        payload.get("opportunity_manifest_content_sha256"),
        "opportunity_manifest_content_sha256",
    )
    _sha256(
        payload.get("request_manifest_content_sha256"),
        "request_manifest_content_sha256",
    )
    if payload.get("runtime_authority") != "none_shadow_input_only":
        raise ValueError("market input capture runtime authority changed")
    _validate_fingerprint(payload, expected=None, label="market input capture")
    if any(
        payload.get(field) is not False
        for field in (
            "retrospective_labels_loaded",
            "later_prices_or_pnl_loaded",
            "sip_print_proxy_used",
            "execution_outcomes_computed",
            "horizon_or_scenario_selected",
            "broker_order_submitted",
            "policy_promotion_eligible",
            "profitability_claim_eligible",
        )
    ):
        raise ValueError("market input capture authority boundary changed")
    captures = _list(payload.get("captures"), "captures")
    opportunity_count = _integer(
        payload.get("opportunity_count"),
        "opportunity_count",
    )
    if opportunity_count != len(captures):
        raise ValueError("market input capture opportunity count changed")
    expected_capture_fields = {
        "opportunity_id",
        "trading_date",
        "symbol",
        "decision_ts_ns",
        "window_start_ns",
        "window_end_ns",
        "initial_status",
        "status_changes",
        "status_coverage_complete",
        "usable_quote_count",
        "unusable_or_status_unknown_quote_count",
        "quotes",
        "capture_status",
    }
    seen: set[str] = set()
    for raw in captures:
        row = _mapping(raw, "capture row")
        if set(row) != expected_capture_fields:
            raise ValueError("capture row fields changed")
        opportunity_id = str(row.get("opportunity_id", ""))
        if not opportunity_id.strip() or opportunity_id in seen:
            raise ValueError("capture opportunity IDs must be non-empty and unique")
        seen.add(opportunity_id)
        _symbol(row.get("symbol"))
        trading_date = str(row.get("trading_date", ""))
        if trading_date not in REGISTERED_DATES:
            raise ValueError("capture trading date is outside the registered panel")
        decision = _integer(row.get("decision_ts_ns"), "decision_ts_ns", minimum=1)
        local_date = datetime.fromtimestamp(
            decision / 1_000_000_000,
            tz=UTC,
        ).astimezone(NEW_YORK).date().isoformat()
        if local_date != trading_date:
            raise ValueError("capture decision timestamp changed trading date")
        start = _integer(row.get("window_start_ns"), "window_start_ns", minimum=1)
        end = _integer(row.get("window_end_ns"), "window_end_ns", minimum=1)
        if start != decision - PRE_DECISION_QUOTE_NS:
            raise ValueError("capture window start changed")
        if end != decision + POST_DECISION_CAPTURE_NS:
            raise ValueError("capture window end changed")

        initial_raw = row.get("initial_status")
        initial: dict[str, object] | None = None
        if initial_raw is not None:
            initial = dict(_mapping(initial_raw, "initial_status"))
            if set(initial) != {
                "ts_recv_ns",
                "record_index",
                "action",
                "is_trading",
            }:
                raise ValueError("initial status fields changed")
            initial_ts = _integer(
                initial["ts_recv_ns"],
                "initial_status.ts_recv_ns",
                minimum=1,
            )
            if initial_ts > start:
                raise ValueError("initial status must be known by the window start")
            if initial_ts < _utc_midnight_ns(trading_date):
                raise ValueError("initial status came from outside the symbol-date request")
            _integer(initial["record_index"], "initial_status.record_index")
            action = _integer(initial["action"], "initial_status.action")
            if action > 14 or initial["is_trading"] not in {"Y", "N", "~"}:
                raise ValueError("initial status value changed")

        changes: list[dict[str, object]] = []
        previous_status = (start, -1)
        for raw_change in _list(row.get("status_changes"), "status_changes"):
            change = dict(_mapping(raw_change, "status change"))
            if set(change) != {
                "ts_recv_ns",
                "record_index",
                "action",
                "is_trading",
            }:
                raise ValueError("status change fields changed")
            ts_recv = _integer(change["ts_recv_ns"], "status_change.ts_recv_ns", minimum=1)
            record_index = _integer(
                change["record_index"],
                "status_change.record_index",
            )
            action = _integer(change["action"], "status_change.action")
            key = (ts_recv, record_index)
            if not start < ts_recv <= end or key <= previous_status:
                raise ValueError("status changes must remain ordered inside the window")
            if action > 14 or change["is_trading"] not in {"Y", "N", "~"}:
                raise ValueError("status change value changed")
            previous_status = key
            changes.append(change)

        status_complete = (
            initial is not None
            and initial["is_trading"] in {"Y", "N"}
            and all(change["is_trading"] != "~" for change in changes)
        )
        if row.get("status_coverage_complete") is not status_complete:
            raise ValueError("status coverage completeness does not recompute")
        expected_status = (
            "complete"
            if status_complete
            else "unavailable_status_not_causally_known"
        )
        if row.get("capture_status") != expected_status:
            raise ValueError("capture status does not match status coverage")

        quote_rows = _list(row.get("quotes"), "quotes")
        usable_quote_count = _integer(
            row.get("usable_quote_count"),
            "usable_quote_count",
        )
        if usable_quote_count != len(quote_rows):
            raise ValueError("usable quote count changed")
        _integer(
            row.get("unusable_or_status_unknown_quote_count"),
            "unusable_or_status_unknown_quote_count",
        )
        if not status_complete and quote_rows:
            raise ValueError("status-unavailable capture cannot expose usable quotes")

        previous_quote: tuple[int, int] | None = None
        status_timeline = ([] if initial is None else [initial]) + changes
        status_times = [int(item["ts_recv_ns"]) for item in status_timeline]
        for raw_quote in quote_rows:
            quote = _mapping(raw_quote, "quote")
            if set(quote) != {
                "symbol",
                "ts_recv_ns",
                "sequence",
                "bid_price",
                "bid_size",
                "ask_price",
                "ask_size",
                "halted",
                "status_ts_recv_ns",
                "status_record_index",
                "status_action",
            }:
                raise ValueError("captured quote fields changed")
            if quote.get("symbol") != row.get("symbol"):
                raise ValueError("captured quote symbol changed")
            ts_recv = _integer(quote.get("ts_recv_ns"), "quote.ts_recv_ns", minimum=1)
            sequence = _integer(quote.get("sequence"), "quote.sequence")
            if not start <= ts_recv <= end:
                raise ValueError("captured quote falls outside the frozen window")
            key = (ts_recv, sequence)
            if previous_quote is not None and key <= previous_quote:
                raise ValueError("captured quotes must remain in receive-time order")
            previous_quote = key
            bid = _decimal(quote.get("bid_price"), "quote.bid_price", positive=True)
            ask = _decimal(quote.get("ask_price"), "quote.ask_price", positive=True)
            if bid >= ask:
                raise ValueError("captured quote must have a positive non-crossed spread")
            _integer(quote.get("bid_size"), "quote.bid_size", minimum=1)
            _integer(quote.get("ask_size"), "quote.ask_size", minimum=1)
            status_index = bisect_right(status_times, ts_recv) - 1
            if status_index < 0:
                raise ValueError("captured quote lacks causal status")
            current = status_timeline[status_index]
            if ts_recv in status_times:
                raise ValueError("captured quote has ambiguous equal-time status")
            status_ts_recv = _integer(
                quote.get("status_ts_recv_ns"),
                "quote.status_ts_recv_ns",
                minimum=1,
            )
            status_record_index = _integer(
                quote.get("status_record_index"),
                "quote.status_record_index",
            )
            status_action = _integer(
                quote.get("status_action"),
                "quote.status_action",
            )
            if status_action > 14:
                raise ValueError("captured quote status action changed")
            if status_ts_recv != current["ts_recv_ns"]:
                raise ValueError("captured quote status timestamp changed")
            if status_record_index != current["record_index"]:
                raise ValueError("captured quote status record index changed")
            if status_action != current["action"]:
                raise ValueError("captured quote status action changed")
            if quote.get("halted") is not (current["is_trading"] != "Y"):
                raise ValueError("captured quote halt state changed")


def top_of_book_events(
    capture: Mapping[str, object],
    opportunity_id: str,
) -> tuple[TopOfBookEvent, ...]:
    """Convert one complete capture to the frozen simulator input type."""
    validate_market_input_capture(capture)
    matches = [
        _mapping(row, "capture row")
        for row in _list(capture.get("captures"), "captures")
        if _mapping(row, "capture row").get("opportunity_id") == opportunity_id
    ]
    if len(matches) != 1:
        raise ValueError("opportunity capture must resolve exactly once")
    row = matches[0]
    if row.get("capture_status") != "complete":
        return ()
    events: list[TopOfBookEvent] = []
    for raw in _list(row.get("quotes"), "quotes"):
        quote = _mapping(raw, "quote")
        events.append(
            TopOfBookEvent(
                symbol=str(quote["symbol"]),
                ts_recv_ns=_integer(quote["ts_recv_ns"], "quote.ts_recv_ns", minimum=1),
                sequence=_integer(quote["sequence"], "quote.sequence"),
                bid_price=_decimal(quote["bid_price"], "quote.bid_price", positive=True),
                bid_size=_integer(quote["bid_size"], "quote.bid_size"),
                ask_price=_decimal(quote["ask_price"], "quote.ask_price", positive=True),
                ask_size=_integer(quote["ask_size"], "quote.ask_size"),
                halted=quote.get("halted") is True,
            )
        )
    return tuple(events)
