"""Causal SIP management-window capture and fixed-entry projection.

This child deliberately does less than a portfolio runtime.  It captures a
fixed, label-blind one-minute/SIP path for each frozen opportunity and applies
the already-selected management translation to exact entry fills from the
immutable daily account runtime.  SIP prints are retained as transaction
evidence only: the projection never mutates the account ledger, synthesizes a
broker fill, closes an account session, or computes sell-side P&L.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Mapping, Sequence

import pandas as pd

from momentumbot.micro_execution import execution_eligible_trades
from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.providers.alpaca_trades import historical_trades
from momentumbot.research.account_chronological_integration import (
    PANEL_ID,
    REGISTERED_DATES,
)
from momentumbot.research.microstructure_contract import canonical_fingerprint
from momentumbot.research.prospective_account_evaluation import (
    ACCOUNT_KEYS,
    AccountSessionPerformance,
    RuntimeDecision,
    registered_cells,
)
from momentumbot.research.prospective_daily_account_runtime import (
    CONTRACT_CONTENT_SHA256 as DAILY_RUNTIME_CONTENT_SHA256,
    CONTRACT_ID as DAILY_RUNTIME_CONTRACT_ID,
    validate_daily_account_runtime,
)
from momentumbot.research.prospective_market_input_capture import (
    ProspectiveOpportunity,
    validate_opportunity_manifest,
)
from momentumbot.research.trade_management_shadow import (
    CONTRACT_CONTENT_SHA256 as TRADE_MANAGEMENT_CONTENT_SHA256,
    CONTRACT_ID as TRADE_MANAGEMENT_CONTRACT_ID,
    ManagementExitLeg,
    ManagementExitReason,
    TradeManagementOutcome,
    management_cell,
)


SCHEMA_VERSION = 1
CONTRACT_ID = "prospective-management-window-capture-v0.1"
CONTRACT_CONTENT_SHA256 = (
    "97270ae8d401a20c7d5661fe49e36a65276ed00bf60098e9c466fa51b05518b0"
)
CAPTURE_ARTIFACT_TYPE = "label_blind_prospective_sip_management_window_capture"
PROJECTION_ARTIFACT_TYPE = "label_blind_fixed_entry_management_projection"
REQUEST_ARTIFACT_TYPE = "label_blind_prospective_management_window_requests"
CAPTURE_FILE = "management-window-capture.json"
PROJECTION_FILE = "management-window-projection.json"
REQUEST_FILE = "management-window-request-manifest.json"

MANAGEMENT_EXECUTION_CONTENT_SHA256 = (
    "14812b9f25b5ea7230254ed86b1e0eaa30fffe3dc13b1ee141b19770706090f9"
)
MICRO_POLICY_FINGERPRINT = (
    "49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa"
)
SELECTED_CELL_ID = "half-2r-breakeven-first-red-1m"
SIGNAL_WINDOW_NS = 900_000_000_000
EXECUTION_TAIL_NS = 60_000_000_000
MINUTE_NS = 60_000_000_000
FEED = "sip"
TIMEFRAME = "1Min"
ADJUSTMENT = "raw"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,31}$")
_FORBIDDEN_KEYS = {
    "benchmark_label",
    "human_action",
    "human_decision",
    "human_state",
    "human_trade",
    "reported_entry",
    "reported_exit",
    "retrospective_label",
    "ross_action",
    "ross_fill",
    "ross_skip",
    "ross_trade",
    "transcript_text",
}


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _list(value: object, field: str) -> list[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return list(value)


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


def _number(value: object, field: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        qualifier = "positive" if positive else "finite"
        raise ValueError(f"{field} must be {qualifier}")
    return result


def _rendered_number(value: object, field: str, *, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite decimal")
    try:
        result = float(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite decimal") from exc
    if not math.isfinite(result) or (positive and result <= 0):
        qualifier = "positive" if positive else "finite"
        raise ValueError(f"{field} must be {qualifier}")
    return result


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return value


def _aware(value: object, field: str) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field} must be ISO 8601") from exc
    else:
        raise ValueError(f"{field} must be a timezone-aware timestamp")
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return result


def _ns(value: object, field: str) -> int:
    timestamp = _aware(value, field).astimezone(UTC)
    delta = timestamp - datetime(1970, 1, 1, tzinfo=UTC)
    return (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + (
        delta.microseconds * 1_000
    )


def _iso_from_ns(value: int) -> str:
    return datetime.fromtimestamp(value / 1_000_000_000, tz=UTC).isoformat()


def _walk_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            keys.add(str(key).lower())
            keys.update(_walk_keys(child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            keys.update(_walk_keys(child))
    return keys


def _validate_hash(payload: Mapping[str, object], field: str) -> str:
    claimed = _sha(payload.get("content_sha256"), f"{field}.content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError(f"{field} content hash changed")
    return claimed


def _finish(payload: dict[str, object]) -> dict[str, object]:
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    payload["content_sha256"] = canonical_fingerprint(unsigned)
    return payload


def validate_management_window_contract(payload: Mapping[str, object]) -> None:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "artifact_type": (
            "preregistered_label_blind_sip_management_window_capture_and_projection"
        ),
        "registration_date": "2026-08-22",
        "registration_status": "registered_before_first_august_24_panel_session",
        "content_sha256": CONTRACT_CONTENT_SHA256,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise ValueError(f"management-window contract {field} changed")
    _validate_hash(payload, "management-window contract")
    parents = _mapping(payload.get("frozen_parents"), "frozen_parents")
    expected_parents = {
        "panel_id": PANEL_ID,
        "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
        "daily_account_runtime_contract_id": DAILY_RUNTIME_CONTRACT_ID,
        "daily_account_runtime_contract_content_sha256": (
            DAILY_RUNTIME_CONTENT_SHA256
        ),
        "prospective_management_execution_contract_content_sha256": (
            MANAGEMENT_EXECUTION_CONTENT_SHA256
        ),
        "trade_management_contract_id": TRADE_MANAGEMENT_CONTRACT_ID,
        "trade_management_contract_content_sha256": (
            TRADE_MANAGEMENT_CONTENT_SHA256
        ),
        "selected_management_cell_id": SELECTED_CELL_ID,
    }
    for field, value in expected_parents.items():
        if parents.get(field) != value:
            raise ValueError(f"management-window frozen parent {field} changed")
    window = _mapping(payload.get("window_policy"), "window_policy")
    if window.get("management_signal_window_after_decision_seconds") != 900:
        raise ValueError("management signal window changed")
    if window.get("execution_observation_tail_seconds") != 60:
        raise ValueError("management execution tail changed")
    projection = _mapping(payload.get("management_projection"), "management_projection")
    if projection.get("parent_ledger_mutated") is not False:
        raise ValueError("management projection cannot mutate the parent ledger")
    if projection.get("portfolio_financial_metrics_eligible") is not False:
        raise ValueError("management projection cannot authorize portfolio metrics")
    authority = _mapping(payload.get("authority_boundary"), "authority_boundary")
    for field in (
        "broker_order_authorized",
        "paper_order_authorized",
        "live_order_authorized",
        "policy_promotion_eligible",
        "profitability_claim_eligible",
        "ross_replication_claim_eligible",
    ):
        if authority.get(field) is not False:
            raise ValueError(f"management-window authority {field} must remain false")


def load_management_window_contract(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("management-window contract root must be an object")
    validate_management_window_contract(payload)
    return payload


@dataclass(frozen=True, slots=True)
class _Window:
    trading_date: str
    symbol: str
    start_ns: int
    end_ns: int
    opportunity_ids: tuple[str, ...]


def _opportunity_bounds(opportunity: ProspectiveOpportunity) -> tuple[int, int]:
    start = opportunity.decision_ts_ns - opportunity.decision_ts_ns % MINUTE_NS
    end = opportunity.decision_ts_ns + SIGNAL_WINDOW_NS + EXECUTION_TAIL_NS
    return start, end


def _opportunity_manifest_date(payload: Mapping[str, object]) -> str:
    prefix = "prospective-opportunities-"
    artifact_id = str(payload.get("artifact_id", ""))
    if not artifact_id.startswith(prefix):
        raise ValueError("opportunity manifest artifact ID does not expose its date")
    trading_date = artifact_id.removeprefix(prefix)
    if trading_date not in REGISTERED_DATES:
        raise ValueError("opportunity manifest date is not registered")
    return trading_date


def _merge_windows(
    opportunities: Sequence[ProspectiveOpportunity],
) -> tuple[_Window, ...]:
    grouped: dict[tuple[str, str], list[ProspectiveOpportunity]] = {}
    for opportunity in opportunities:
        grouped.setdefault(
            (opportunity.trading_date, opportunity.symbol), []
        ).append(opportunity)
    result: list[_Window] = []
    for (trading_date, symbol), rows in sorted(grouped.items()):
        ordered = sorted(rows, key=lambda row: (row.decision_ts_ns, row.opportunity_id))
        current_start: int | None = None
        current_end: int | None = None
        current_ids: list[str] = []
        for opportunity in ordered:
            start, end = _opportunity_bounds(opportunity)
            if current_start is None or current_end is None or start > current_end:
                if current_start is not None and current_end is not None:
                    result.append(
                        _Window(
                            trading_date,
                            symbol,
                            current_start,
                            current_end,
                            tuple(current_ids),
                        )
                    )
                current_start, current_end = start, end
                current_ids = [opportunity.opportunity_id]
            else:
                current_end = max(current_end, end)
                current_ids.append(opportunity.opportunity_id)
        if current_start is not None and current_end is not None:
            result.append(
                _Window(
                    trading_date,
                    symbol,
                    current_start,
                    current_end,
                    tuple(current_ids),
                )
            )
    return tuple(result)


def build_management_request_manifest(
    contract: Mapping[str, object],
    opportunity_manifest: Mapping[str, object],
) -> dict[str, object]:
    """Derive exact merged Alpaca SIP windows without calling a provider."""

    validate_management_window_contract(contract)
    opportunities = validate_opportunity_manifest(opportunity_manifest)
    windows = _merge_windows(opportunities)
    requests: list[dict[str, object]] = []
    ordinals: dict[tuple[str, str], int] = {}
    for window in windows:
        key = (window.trading_date, window.symbol)
        ordinal = ordinals.get(key, 0) + 1
        ordinals[key] = ordinal
        requests.append(
            {
                "request_id": (
                    f"{window.trading_date}-{window.symbol}-management-{ordinal:02d}"
                ),
                "trading_date": window.trading_date,
                "symbol": window.symbol,
                "start_ns": window.start_ns,
                "end_ns": window.end_ns,
                "end_exclusive": True,
                "feed": FEED,
                "bar_timeframe": TIMEFRAME,
                "bar_adjustment": ADJUSTMENT,
                "symbol_asof": window.trading_date,
                "opportunity_ids": list(window.opportunity_ids),
            }
        )
    trading_date = _opportunity_manifest_date(opportunity_manifest)
    if any(opportunity.trading_date != trading_date for opportunity in opportunities):
        raise ValueError("opportunity manifest mixes registered dates")
    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": (
            "prospective-management-window-requests-"
            f"{trading_date}"
        ),
        "artifact_type": REQUEST_ARTIFACT_TYPE,
        "contract_id": CONTRACT_ID,
        "contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "panel_id": PANEL_ID,
        "trading_date": trading_date,
        "opportunity_manifest_content_sha256": opportunity_manifest["content_sha256"],
        "opportunity_count": len(opportunities),
        "request_count": len(requests),
        "requests": requests,
        "provider_call_made": False,
        "retrospective_labels_loaded": False,
        "later_prices_outside_registered_windows_loaded": False,
        "broker_order_submitted": False,
    }
    return _finish(report)


def validate_management_request_manifest(
    payload: Mapping[str, object],
    *,
    contract: Mapping[str, object],
    opportunity_manifest: Mapping[str, object],
) -> None:
    expected = build_management_request_manifest(contract, opportunity_manifest)
    if dict(payload) != expected:
        raise ValueError("management request manifest differs from deterministic output")


def _frame_bar_rows(frame: pd.DataFrame, request: Mapping[str, object]) -> list[dict[str, object]]:
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("management bars require a timezone-aware DatetimeIndex")
    if not {"open", "close"}.issubset(frame.columns):
        raise ValueError("management bars require open and close")
    start = _integer(request.get("start_ns"), "request.start_ns", minimum=1)
    end = _integer(request.get("end_ns"), "request.end_ns", minimum=1)
    rows: list[dict[str, object]] = []
    previous: int | None = None
    for timestamp, row in frame.sort_index(kind="stable").iterrows():
        ts_ns = int(pd.Timestamp(timestamp).value)
        if not start <= ts_ns < end:
            raise ValueError("management bar falls outside its exact request")
        if previous is not None and ts_ns <= previous:
            raise ValueError("management bars must have unique ordered timestamps")
        previous = ts_ns
        rows.append(
            {
                "timestamp_ns": ts_ns,
                "open": _number(row["open"], "bar.open", positive=True),
                "close": _number(row["close"], "bar.close", positive=True),
            }
        )
    return rows


def _frame_trade_rows(
    frame: pd.DataFrame,
    request: Mapping[str, object],
) -> tuple[int, list[dict[str, object]]]:
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("management trades require a timezone-aware DatetimeIndex")
    required = {"price", "size", "exchange", "conditions", "trade_id", "tape"}
    if not required.issubset(frame.columns):
        raise ValueError("management trades lack normalized Alpaca fields")
    ordered = frame.sort_index(kind="stable").copy()
    start = _integer(request.get("start_ns"), "request.start_ns", minimum=1)
    end = _integer(request.get("end_ns"), "request.end_ns", minimum=1)
    if any(not start <= int(pd.Timestamp(value).value) < end for value in ordered.index):
        raise ValueError("management trade falls outside its exact request")
    raw_count = len(ordered)
    eligible = execution_eligible_trades(ordered)
    rows: list[dict[str, object]] = []
    previous: tuple[int, int] | None = None
    for timestamp, row in eligible.iterrows():
        ts_ns = int(pd.Timestamp(timestamp).value)
        source_sequence = _integer(
            int(row["_source_sequence"]),
            "trade.source_sequence",
        )
        key = (ts_ns, source_sequence)
        if previous is not None and key <= previous:
            raise ValueError("eligible management trades must remain stably ordered")
        previous = key
        conditions = row.get("conditions")
        if isinstance(conditions, tuple):
            condition_rows = list(conditions)
        elif isinstance(conditions, list):
            condition_rows = list(conditions)
        else:
            condition_rows = []
        rows.append(
            {
                "timestamp_ns": ts_ns,
                "source_sequence": source_sequence,
                "price": _number(row["price"], "trade.price", positive=True),
                "size": _integer(int(row["size"]), "trade.size", minimum=1),
                "exchange": str(row.get("exchange") or ""),
                "conditions": [str(value) for value in condition_rows],
                "trade_id": str(row.get("trade_id") or ""),
                "tape": str(row.get("tape") or ""),
                "execution_via_odd_lot": bool(row["_execution_via_odd_lot"]),
            }
        )
    return raw_count, rows


def _request_index(request_manifest: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    result: dict[str, Mapping[str, object]] = {}
    for raw in _list(request_manifest.get("requests"), "requests"):
        row = _mapping(raw, "request")
        request_id = str(row.get("request_id", ""))
        if not request_id or request_id in result:
            raise ValueError("management request IDs must be unique")
        result[request_id] = row
    return result


def build_management_capture(
    contract: Mapping[str, object],
    opportunity_manifest: Mapping[str, object],
    request_manifest: Mapping[str, object],
    request_results: Mapping[str, Mapping[str, object]],
    *,
    capture_frozen_at: str | datetime,
    provider_call_made: bool,
) -> dict[str, object]:
    """Normalize complete already-returned Alpaca frames into one frozen capture."""

    validate_management_window_contract(contract)
    validate_management_request_manifest(
        request_manifest,
        contract=contract,
        opportunity_manifest=opportunity_manifest,
    )
    requests = _request_index(request_manifest)
    if set(request_results) != set(requests):
        raise ValueError("management request results must cover every exact request")
    frozen = _aware(capture_frozen_at, "capture_frozen_at").astimezone(UTC)
    if requests and int(frozen.timestamp() * 1_000_000_000) < max(
        int(row["end_ns"]) for row in requests.values()
    ):
        raise ValueError("capture_frozen_at precedes an exact request end")
    if not isinstance(provider_call_made, bool):
        raise ValueError("provider_call_made must be boolean")

    paths: list[dict[str, object]] = []
    for request_id, request in requests.items():
        result = _mapping(request_results[request_id], "request result")
        if set(result) != {"request_complete", "bars", "trades"}:
            raise ValueError("management request result fields changed")
        if result.get("request_complete") is not True:
            raise ValueError("partial management captures are prohibited")
        bars = result.get("bars")
        trades = result.get("trades")
        if not isinstance(bars, pd.DataFrame) or not isinstance(trades, pd.DataFrame):
            raise ValueError("management request results require bar and trade frames")
        bar_rows = _frame_bar_rows(bars, request)
        raw_trade_count, trade_rows = _frame_trade_rows(trades, request)
        paths.append(
            {
                "request_id": request_id,
                "trading_date": request["trading_date"],
                "symbol": request["symbol"],
                "start_ns": request["start_ns"],
                "end_ns": request["end_ns"],
                "opportunity_ids": request["opportunity_ids"],
                "request_complete": True,
                "raw_bar_count": len(bar_rows),
                "raw_trade_count": raw_trade_count,
                "eligible_trade_count": len(trade_rows),
                "bars": bar_rows,
                "eligible_trades": trade_rows,
            }
        )

    trading_date = request_manifest.get("trading_date")
    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": (
            f"prospective-management-window-capture-{trading_date}"
        ),
        "artifact_type": CAPTURE_ARTIFACT_TYPE,
        "contract_id": CONTRACT_ID,
        "contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "panel_id": PANEL_ID,
        "trading_date": trading_date,
        "capture_frozen_at": frozen.isoformat(),
        "opportunity_manifest_content_sha256": opportunity_manifest["content_sha256"],
        "request_manifest_content_sha256": request_manifest["content_sha256"],
        "opportunity_count": request_manifest["opportunity_count"],
        "request_count": request_manifest["request_count"],
        "paths": paths,
        "provider": "alpaca",
        "feed": FEED,
        "bar_timeframe": TIMEFRAME,
        "bar_adjustment": ADJUSTMENT,
        "provider_call_made": provider_call_made,
        "provider_credential_persisted": False,
        "provider_error_message_persisted": False,
        "raw_provider_payload_persisted": False,
        "retrospective_labels_loaded": False,
        "later_prices_outside_registered_windows_loaded": False,
        "execution_outcomes_computed": False,
        "broker_order_submitted": False,
        "paper_order_submitted": False,
        "live_order_submitted": False,
        "policy_promotion_eligible": False,
        "profitability_claim_eligible": False,
    }
    report = _finish(report)
    validate_management_capture(report)
    return report


def _persisted_trade_frame(rows: Sequence[object]) -> pd.DataFrame:
    data: list[dict[str, object]] = []
    timestamps: list[pd.Timestamp] = []
    for raw in rows:
        row = _mapping(raw, "eligible trade")
        timestamps.append(pd.Timestamp(int(row["timestamp_ns"]), unit="ns", tz="UTC"))
        data.append(
            {
                "price": row["price"],
                "size": row["size"],
                "exchange": row["exchange"],
                "conditions": tuple(_list(row["conditions"], "trade.conditions")),
                "trade_id": row["trade_id"],
                "tape": row["tape"],
                "_persisted_source_sequence": row["source_sequence"],
                "_persisted_odd_lot": row["execution_via_odd_lot"],
            }
        )
    frame = pd.DataFrame(data)
    frame.index = pd.DatetimeIndex(timestamps, name="timestamp")
    return frame


def validate_management_capture(payload: Mapping[str, object]) -> None:
    if _walk_keys(payload) & _FORBIDDEN_KEYS:
        raise ValueError("management capture contains retrospective keys")
    expected_fields = {
        "schema_version",
        "artifact_id",
        "artifact_type",
        "contract_id",
        "contract_content_sha256",
        "panel_id",
        "trading_date",
        "capture_frozen_at",
        "opportunity_manifest_content_sha256",
        "request_manifest_content_sha256",
        "opportunity_count",
        "request_count",
        "paths",
        "provider",
        "feed",
        "bar_timeframe",
        "bar_adjustment",
        "provider_call_made",
        "provider_credential_persisted",
        "provider_error_message_persisted",
        "raw_provider_payload_persisted",
        "retrospective_labels_loaded",
        "later_prices_outside_registered_windows_loaded",
        "execution_outcomes_computed",
        "broker_order_submitted",
        "paper_order_submitted",
        "live_order_submitted",
        "policy_promotion_eligible",
        "profitability_claim_eligible",
        "content_sha256",
    }
    if set(payload) != expected_fields:
        raise ValueError("management capture fields changed")
    expected = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": CAPTURE_ARTIFACT_TYPE,
        "contract_id": CONTRACT_ID,
        "contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "panel_id": PANEL_ID,
        "provider": "alpaca",
        "feed": FEED,
        "bar_timeframe": TIMEFRAME,
        "bar_adjustment": ADJUSTMENT,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise ValueError(f"management capture {field} changed")
    _validate_hash(payload, "management capture")
    capture_frozen = _aware(
        payload.get("capture_frozen_at"), "capture_frozen_at"
    ).astimezone(UTC)
    _sha(
        payload.get("opportunity_manifest_content_sha256"),
        "opportunity_manifest_content_sha256",
    )
    _sha(
        payload.get("request_manifest_content_sha256"),
        "request_manifest_content_sha256",
    )
    if not isinstance(payload.get("provider_call_made"), bool):
        raise ValueError("provider_call_made must be boolean")
    for field in (
        "provider_credential_persisted",
        "provider_error_message_persisted",
        "raw_provider_payload_persisted",
        "retrospective_labels_loaded",
        "later_prices_outside_registered_windows_loaded",
        "execution_outcomes_computed",
        "broker_order_submitted",
        "paper_order_submitted",
        "live_order_submitted",
        "policy_promotion_eligible",
        "profitability_claim_eligible",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"management capture boundary changed at {field}")
    trading_date = str(payload.get("trading_date", ""))
    if trading_date not in REGISTERED_DATES:
        raise ValueError("management capture date is not registered")
    if payload.get("artifact_id") != (
        f"prospective-management-window-capture-{trading_date}"
    ):
        raise ValueError("management capture artifact ID changed")
    paths = [_mapping(row, "management path") for row in _list(payload.get("paths"), "paths")]
    if _integer(payload.get("request_count"), "request_count") != len(paths):
        raise ValueError("management capture request count changed")
    if bool(paths) != payload.get("provider_call_made"):
        raise ValueError("management capture provider-call status differs from requests")
    seen: set[str] = set()
    opportunity_ids: set[str] = set()
    path_fields = {
        "request_id",
        "trading_date",
        "symbol",
        "start_ns",
        "end_ns",
        "opportunity_ids",
        "request_complete",
        "raw_bar_count",
        "raw_trade_count",
        "eligible_trade_count",
        "bars",
        "eligible_trades",
    }
    for path in paths:
        if set(path) != path_fields:
            raise ValueError("management path fields changed")
        request_id = str(path.get("request_id", ""))
        if not request_id or request_id in seen:
            raise ValueError("management path request IDs must be unique")
        seen.add(request_id)
        if path.get("trading_date") != trading_date:
            raise ValueError("management path date changed")
        symbol = str(path.get("symbol", ""))
        if _SYMBOL.fullmatch(symbol) is None:
            raise ValueError("management path symbol is invalid")
        start = _integer(path.get("start_ns"), "path.start_ns", minimum=1)
        end = _integer(path.get("end_ns"), "path.end_ns", minimum=start + 1)
        if end > int(capture_frozen.timestamp() * 1_000_000_000):
            raise ValueError("management path ends after capture freeze")
        if path.get("request_complete") is not True:
            raise ValueError("management path must be complete")
        ids = [str(value) for value in _list(path.get("opportunity_ids"), "opportunity_ids")]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("management path opportunity IDs must be unique")
        if opportunity_ids.intersection(ids):
            raise ValueError("an opportunity cannot appear in two management paths")
        opportunity_ids.update(ids)
        bars = _list(path.get("bars"), "bars")
        trades = _list(path.get("eligible_trades"), "eligible_trades")
        if _integer(path.get("raw_bar_count"), "raw_bar_count") != len(bars):
            raise ValueError("management bar count changed")
        raw_trade_count = _integer(path.get("raw_trade_count"), "raw_trade_count")
        if _integer(path.get("eligible_trade_count"), "eligible_trade_count") != len(trades):
            raise ValueError("eligible management trade count changed")
        if raw_trade_count < len(trades):
            raise ValueError("raw trade count cannot be below eligible count")
        previous_bar: int | None = None
        for raw_bar in bars:
            bar = _mapping(raw_bar, "bar")
            if set(bar) != {"timestamp_ns", "open", "close"}:
                raise ValueError("management bar fields changed")
            ts_ns = _integer(bar.get("timestamp_ns"), "bar.timestamp_ns", minimum=1)
            if not start <= ts_ns < end or (
                previous_bar is not None and ts_ns <= previous_bar
            ):
                raise ValueError("management bars must be ordered inside the request")
            previous_bar = ts_ns
            _number(bar.get("open"), "bar.open", positive=True)
            _number(bar.get("close"), "bar.close", positive=True)
        previous_trade: tuple[int, int] | None = None
        for raw_trade in trades:
            trade = _mapping(raw_trade, "trade")
            if set(trade) != {
                "timestamp_ns",
                "source_sequence",
                "price",
                "size",
                "exchange",
                "conditions",
                "trade_id",
                "tape",
                "execution_via_odd_lot",
            }:
                raise ValueError("management trade fields changed")
            ts_ns = _integer(trade.get("timestamp_ns"), "trade.timestamp_ns", minimum=1)
            source_sequence = _integer(
                trade.get("source_sequence"), "trade.source_sequence"
            )
            key = (ts_ns, source_sequence)
            if not start <= ts_ns < end or (
                previous_trade is not None and key <= previous_trade
            ):
                raise ValueError("management trades must be ordered inside the request")
            previous_trade = key
            _number(trade.get("price"), "trade.price", positive=True)
            _integer(trade.get("size"), "trade.size", minimum=1)
            _list(trade.get("conditions"), "trade.conditions")
            if not isinstance(trade.get("execution_via_odd_lot"), bool):
                raise ValueError("execution_via_odd_lot must be boolean")
        persisted = _persisted_trade_frame(trades)
        if not persisted.empty:
            recomputed = execution_eligible_trades(
                persisted.drop(
                    columns=["_persisted_source_sequence", "_persisted_odd_lot"]
                )
            )
            if len(recomputed) != len(persisted):
                raise ValueError("persisted trade is not execution eligible")
            if list(recomputed["_execution_via_odd_lot"].astype(bool)) != list(
                persisted["_persisted_odd_lot"].astype(bool)
            ):
                raise ValueError("persisted odd-lot eligibility changed")
    if _integer(payload.get("opportunity_count"), "opportunity_count") != len(
        opportunity_ids
    ):
        raise ValueError("management opportunity coverage changed")


def capture_management_window_from_alpaca(
    contract: Mapping[str, object],
    opportunity_manifest: Mapping[str, object],
    *,
    client: AlpacaDataClient,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    trade_loader: Callable[..., pd.DataFrame] = historical_trades,
) -> tuple[dict[str, object], dict[str, object]]:
    """Perform the exact registered read-only Alpaca requests once each."""

    request_manifest = build_management_request_manifest(
        contract, opportunity_manifest
    )
    results: dict[str, Mapping[str, object]] = {}
    for raw in _list(request_manifest.get("requests"), "requests"):
        request = _mapping(raw, "request")
        start = datetime.fromtimestamp(int(request["start_ns"]) / 1_000_000_000, tz=UTC)
        end = datetime.fromtimestamp(int(request["end_ns"]) / 1_000_000_000, tz=UTC)
        symbol = str(request["symbol"])
        bars = client.bars(
            [symbol],
            timeframe=TIMEFRAME,
            start=start,
            end=end,
            feed=FEED,
            adjustment=ADJUSTMENT,
            asof=str(request["symbol_asof"]),
        ).get(symbol)
        if bars is None:
            raise ValueError("Alpaca bar response omitted an exact requested symbol")
        trades = trade_loader(
            client,
            symbol,
            start=start,
            end=end,
            feed=FEED,
            asof=str(request["symbol_asof"]),
        )
        results[str(request["request_id"])] = {
            "request_complete": True,
            "bars": bars,
            "trades": trades,
        }
    capture = build_management_capture(
        contract,
        opportunity_manifest,
        request_manifest,
        results,
        capture_frozen_at=clock(),
        provider_call_made=bool(results),
    )
    return request_manifest, capture


def _path_for_opportunity(
    capture: Mapping[str, object], opportunity_id: str
) -> Mapping[str, object] | None:
    matches = [
        _mapping(raw, "management path")
        for raw in _list(capture.get("paths"), "paths")
        if opportunity_id
        in [str(value) for value in _list(_mapping(raw, "path").get("opportunity_ids"), "opportunity_ids")]
    ]
    if len(matches) > 1:
        raise ValueError("management opportunity resolves to more than one path")
    return matches[0] if matches else None


def _opportunity_frames(
    path: Mapping[str, object],
    *,
    decision_ts_ns: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    signal_end = decision_ts_ns + SIGNAL_WINDOW_NS
    execution_end = signal_end + EXECUTION_TAIL_NS
    bar_rows: list[dict[str, object]] = []
    bar_times: list[pd.Timestamp] = []
    for raw in _list(path.get("bars"), "bars"):
        row = _mapping(raw, "bar")
        ts_ns = int(row["timestamp_ns"])
        if ts_ns + MINUTE_NS <= signal_end and ts_ns + MINUTE_NS > decision_ts_ns:
            bar_times.append(pd.Timestamp(ts_ns, unit="ns", tz="UTC"))
            bar_rows.append({"open": row["open"], "close": row["close"]})
    bars = pd.DataFrame(bar_rows, columns=["open", "close"])
    bars.index = (
        pd.DatetimeIndex(bar_times, name="timestamp")
        if bar_times
        else pd.DatetimeIndex([], name="timestamp", tz="UTC")
    )

    trade_rows: list[dict[str, object]] = []
    trade_times: list[pd.Timestamp] = []
    for raw in _list(path.get("eligible_trades"), "eligible_trades"):
        row = _mapping(raw, "trade")
        ts_ns = int(row["timestamp_ns"])
        if decision_ts_ns <= ts_ns < execution_end:
            trade_times.append(pd.Timestamp(ts_ns, unit="ns", tz="UTC"))
            trade_rows.append(
                {
                    "price": row["price"],
                    "size": row["size"],
                    "exchange": row["exchange"],
                    "conditions": tuple(_list(row["conditions"], "conditions")),
                    "trade_id": row["trade_id"],
                    "tape": row["tape"],
                    "_captured_source_sequence": row["source_sequence"],
                }
            )
    trades = pd.DataFrame(
        trade_rows,
        columns=[
            "price",
            "size",
            "exchange",
            "conditions",
            "trade_id",
            "tape",
            "_captured_source_sequence",
        ],
    )
    trades.index = (
        pd.DatetimeIndex(trade_times, name="timestamp")
        if trade_times
        else pd.DatetimeIndex([], name="timestamp", tz="UTC")
    )
    return bars, trades


def simulate_external_fill_management(
    *,
    symbol: str,
    fill_time: pd.Timestamp,
    fill_price: float,
    stop_price: float,
    bars: pd.DataFrame,
    trades: pd.DataFrame,
) -> TradeManagementOutcome:
    """Apply the frozen management cell after an L1 fill absent from SIP prints."""

    selected = management_cell(SELECTED_CELL_ID)
    filled_at = pd.Timestamp(fill_time)
    if filled_at.tzinfo is None:
        raise ValueError("external fill time must be timezone-aware")
    numeric_fill = _number(fill_price, "fill_price", positive=True)
    numeric_stop = _number(stop_price, "stop_price", positive=True)
    if numeric_stop >= numeric_fill:
        raise ValueError("initial stop must remain below the actual fill")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("management bars must be timezone-aware")
    if not {"open", "close"}.issubset(bars.columns):
        raise ValueError("management bars require open and close")
    if not isinstance(trades.index, pd.DatetimeIndex) or trades.index.tz is None:
        raise ValueError("management trades must be timezone-aware")
    execution_path = execution_eligible_trades(
        trades.drop(columns=["_captured_source_sequence"], errors="ignore")
    )
    future = execution_path[execution_path.index > filled_at]
    first_red_signal: pd.Timestamp | None = None
    for bar_start, bar in bars.sort_index(kind="stable").iterrows():
        signal_at = pd.Timestamp(bar_start) + pd.Timedelta(minutes=1)
        if signal_at > filled_at and float(bar["close"]) < float(bar["open"]):
            first_red_signal = signal_at
            break

    initial_risk = numeric_fill - numeric_stop
    first_target = round(numeric_fill + 2.0 * initial_risk, 10)
    remaining = 1.0
    active_stop = numeric_stop
    target_touched = False
    stop_moved = False
    legs: list[ManagementExitLeg] = []
    for timestamp, row in future.iterrows():
        at = pd.Timestamp(timestamp)
        price = float(row["price"])
        odd_lot = bool(row.get("_execution_via_odd_lot", False))
        if price <= active_stop:
            reason = (
                ManagementExitReason.BREAKEVEN_STOP
                if stop_moved
                else ManagementExitReason.INITIAL_STOP
            )
            legs.append(ManagementExitLeg(remaining, at, price, reason, odd_lot))
            remaining = 0.0
            break
        if first_red_signal is not None and at >= first_red_signal:
            legs.append(
                ManagementExitLeg(
                    remaining,
                    at,
                    price,
                    ManagementExitReason.FIRST_RED_CANDLE,
                    odd_lot,
                )
            )
            remaining = 0.0
            break
        if not target_touched and price >= first_target:
            target_touched = True
            legs.append(
                ManagementExitLeg(
                    0.5,
                    at,
                    first_target,
                    ManagementExitReason.FIRST_TARGET,
                    odd_lot,
                )
            )
            remaining = 0.5
            active_stop = numeric_fill
            stop_moved = True
    return TradeManagementOutcome(
        cell=selected,
        symbol=symbol,
        fill_time=filled_at,
        fill_price=numeric_fill,
        initial_stop_price=numeric_stop,
        first_target_price=first_target,
        first_red_signal_at=first_red_signal,
        target_touched=target_touched,
        stop_moved_to_breakeven=stop_moved,
        legs=tuple(legs),
        remaining_fraction=remaining,
        active_stop_price=active_stop,
    )


def _outcome_payload(outcome: TradeManagementOutcome) -> dict[str, object]:
    return {
        "status": outcome.status,
        "cell_id": outcome.cell.cell_id,
        "fill_time": outcome.fill_time.isoformat(),
        "fill_price": outcome.fill_price,
        "initial_stop_price": outcome.initial_stop_price,
        "first_target_price": outcome.first_target_price,
        "first_red_signal_at": (
            None
            if outcome.first_red_signal_at is None
            else outcome.first_red_signal_at.isoformat()
        ),
        "target_touched": outcome.target_touched,
        "stop_moved_to_breakeven": outcome.stop_moved_to_breakeven,
        "legs": [
            {
                "quantity_fraction": leg.quantity_fraction,
                "exit_time": leg.exit_time.isoformat(),
                "exit_price": leg.exit_price,
                "reason": leg.reason.value,
                "execution_via_odd_lot": leg.execution_via_odd_lot,
            }
            for leg in outcome.legs
        ],
        "remaining_fraction": outcome.remaining_fraction,
        "active_stop_price": outcome.active_stop_price,
        "execution_evidence": "sip_transaction_proxy_not_broker_fill",
    }


def _accepted_entry(
    detail: Mapping[str, object], symbol: str
) -> tuple[Mapping[str, object], Mapping[str, object]] | str:
    attempts = [
        _mapping(raw, "execution attempt")
        for raw in _list(detail.get("execution_attempts"), "execution_attempts")
        if _mapping(raw, "attempt").get("symbol") == symbol
        and _mapping(raw, "attempt").get("entry_result") == "filled"
        and _mapping(_mapping(raw, "attempt").get("ledger"), "attempt ledger").get(
            "accepted"
        )
        is True
    ]
    if len(attempts) != 1:
        return (
            "no_exact_accepted_entry"
            if not attempts
            else "multiple_entry_or_add_campaign_outside_frozen_management_child"
        )
    attempt = attempts[0]
    execution = _mapping(attempt.get("execution"), "attempt execution")
    events = [
        _mapping(raw, "ledger event")
        for raw in _list(
            _mapping(detail.get("ledger_artifact"), "ledger artifact").get("events"),
            "ledger events",
        )
        if _mapping(raw, "event").get("event_type") == "entry_accepted"
        and _mapping(raw, "event").get("activation_id") == attempt.get("activation_id")
        and _mapping(raw, "event").get("plan_id") == attempt.get("plan_id")
    ]
    if len(events) != 1:
        return "accepted_entry_ledger_evidence_ambiguous"
    event = events[0]
    fill_ns = _integer(execution.get("fill_ts_ns"), "fill_ts_ns", minimum=1)
    if event.get("at") != _iso_from_ns(fill_ns):
        raise ValueError("accepted entry event time differs from execution fill")
    if not math.isclose(
        _number(event.get("fill_price"), "entry event fill_price", positive=True),
        _rendered_number(
            execution.get("fill_price"), "execution fill_price", positive=True
        ),
        abs_tol=1e-9,
    ):
        raise ValueError("accepted entry event price differs from execution fill")
    return attempt, event


def _project_cell(
    detail: Mapping[str, object], capture: Mapping[str, object]
) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object]]:
    projected_intrinsic: list[dict[str, object]] = []
    outcomes: list[dict[str, object]] = []
    unavailable_count = int(
        _mapping(detail.get("performance"), "performance").get(
            "unavailable_input_count", 0
        )
    )
    for raw_decision in _list(detail.get("candidate_decisions"), "candidate decisions"):
        decision = dict(_mapping(raw_decision, "candidate decision"))
        symbol = str(decision.get("symbol", ""))
        if decision.get("entry_status") != "filled":
            projected_intrinsic.append(decision)
            outcomes.append(
                {
                    "symbol": symbol,
                    "opportunity_id": None,
                    "projection_status": "not_applicable_no_frozen_entry",
                    "reason": None,
                    "outcome": None,
                }
            )
            continue
        accepted = _accepted_entry(detail, symbol)
        if isinstance(accepted, str):
            decision.update(
                {
                    "exit_status": "unavailable",
                    "first_exit_at": None,
                    "first_exit_price": None,
                    "exit_reason": None,
                }
            )
            unavailable_count += 1
            projected_intrinsic.append(decision)
            outcomes.append(
                {
                    "symbol": symbol,
                    "opportunity_id": None,
                    "projection_status": "unavailable",
                    "reason": accepted,
                    "outcome": None,
                }
            )
            continue
        attempt, event = accepted
        opportunity_id = str(attempt.get("opportunity_id", ""))
        path = _path_for_opportunity(capture, opportunity_id)
        if path is None:
            reason = "management_capture_missing_exact_opportunity"
            outcome_payload = None
        else:
            bars, trades = _opportunity_frames(
                path,
                decision_ts_ns=_integer(
                    attempt.get("decision_ts_ns"), "decision_ts_ns", minimum=1
                ),
            )
            fill_time = pd.Timestamp(
                _integer(
                    _mapping(attempt.get("execution"), "execution").get("fill_ts_ns"),
                    "fill_ts_ns",
                    minimum=1,
                ),
                unit="ns",
                tz="UTC",
            )
            future = trades[trades.index > fill_time]
            if bars.empty or future.empty:
                reason = "insufficient_bar_or_eligible_trade_path"
                outcome_payload = None
            else:
                outcome = simulate_external_fill_management(
                    symbol=symbol,
                    fill_time=fill_time,
                    fill_price=_rendered_number(
                        _mapping(attempt.get("execution"), "execution").get(
                            "fill_price"
                        ),
                        "fill_price",
                        positive=True,
                    ),
                    stop_price=_number(
                        event.get("stop_price"), "stop_price", positive=True
                    ),
                    bars=bars,
                    trades=trades,
                )
                outcome_payload = _outcome_payload(outcome)
                reason = None
        if outcome_payload is None:
            decision.update(
                {
                    "exit_status": "unavailable",
                    "first_exit_at": None,
                    "first_exit_price": None,
                    "exit_reason": None,
                }
            )
            unavailable_count += 1
            status = "unavailable"
        elif outcome_payload["status"] == "closed":
            first_leg = _mapping(
                _list(outcome_payload["legs"], "outcome legs")[0], "first exit leg"
            )
            decision.update(
                {
                    "exit_status": "closed",
                    "first_exit_at": first_leg["exit_time"],
                    "first_exit_price": first_leg["exit_price"],
                    "exit_reason": first_leg["reason"],
                }
            )
            status = "closed_transaction_proxy"
        else:
            decision.update(
                {
                    "exit_status": "open",
                    "first_exit_at": None,
                    "first_exit_price": None,
                    "exit_reason": None,
                }
            )
            status = str(outcome_payload["status"])
        projected_intrinsic.append(decision)
        outcomes.append(
            {
                "symbol": symbol,
                "opportunity_id": opportunity_id,
                "projection_status": status,
                "reason": reason,
                "outcome": outcome_payload,
            }
        )

    performance = dict(_mapping(detail.get("performance"), "performance"))
    performance["unavailable_input_count"] = unavailable_count
    cell: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "prospective_management_window_projection_cell",
        "contract_id": CONTRACT_ID,
        "contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "panel_id": PANEL_ID,
        "trading_date": detail["trading_date"],
        "account": detail["account"],
        "behavioral_horizon_seconds": detail["behavioral_horizon_seconds"],
        "execution_scenario_id": detail["execution_scenario_id"],
        "parent_runtime_content_sha256": detail["content_sha256"],
        "candidate_decisions": projected_intrinsic,
        "management_outcomes": outcomes,
        "performance": performance,
        "parent_ledger_mutated": False,
        "portfolio_financial_metrics_eligible": False,
        "sell_fees_or_realized_pnl_computed": False,
    }
    cell = _finish(cell)
    cell_hash = str(cell["content_sha256"])
    decisions = [
        RuntimeDecision.from_mapping(
            {**row, "runtime_content_sha256": cell_hash}
        ).as_dict()
        for row in projected_intrinsic
    ]
    session = AccountSessionPerformance.from_mapping(
        {**performance, "runtime_content_sha256": cell_hash}
    ).as_dict()
    return cell, decisions, session


def build_management_projection(
    contract: Mapping[str, object],
    daily_runtime: Mapping[str, object],
    management_capture: Mapping[str, object],
    *,
    projection_frozen_at: str | datetime,
) -> dict[str, object]:
    """Project management exits without closing or repricing the parent ledger."""

    validate_management_window_contract(contract)
    validate_daily_account_runtime(daily_runtime)
    validate_management_capture(management_capture)
    if daily_runtime.get("trading_date") != management_capture.get("trading_date"):
        raise ValueError("management capture and daily runtime dates differ")
    frozen_inputs = _mapping(daily_runtime.get("frozen_inputs"), "frozen_inputs")
    if frozen_inputs.get("opportunity_manifest_content_sha256") != (
        management_capture.get("opportunity_manifest_content_sha256")
    ):
        raise ValueError("management capture does not bind the runtime opportunities")
    frozen = _aware(projection_frozen_at, "projection_frozen_at").astimezone(UTC)
    if frozen < _aware(
        management_capture.get("capture_frozen_at"), "capture_frozen_at"
    ).astimezone(UTC):
        raise ValueError("projection cannot precede management capture freeze")
    cells: list[dict[str, object]] = []
    decisions: list[dict[str, object]] = []
    sessions: list[dict[str, object]] = []
    for raw in _list(daily_runtime.get("session_details"), "session details"):
        cell, cell_decisions, session = _project_cell(
            _mapping(raw, "session detail"), management_capture
        )
        cells.append(cell)
        decisions.extend(cell_decisions)
        sessions.append(session)
    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": (
            f"prospective-management-window-projection-{daily_runtime['trading_date']}"
        ),
        "artifact_type": PROJECTION_ARTIFACT_TYPE,
        "contract_id": CONTRACT_ID,
        "contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "panel_id": PANEL_ID,
        "trading_date": daily_runtime["trading_date"],
        "projection_frozen_at": frozen.isoformat(),
        "daily_runtime_content_sha256": daily_runtime["content_sha256"],
        "management_capture_content_sha256": management_capture["content_sha256"],
        "cell_count": len(cells),
        "decision_count": len(decisions),
        "cells": cells,
        "decisions": decisions,
        "sessions": sessions,
        "parent_ledger_mutated": False,
        "portfolio_financial_metrics_eligible": False,
        "sell_fees_or_realized_pnl_computed": False,
        "retrospective_labels_loaded": False,
        "raw_transcript_text_persisted": False,
        "broker_order_submitted": False,
        "paper_order_submitted": False,
        "live_order_submitted": False,
        "best_cell_selected": False,
        "policy_promotion_eligible": False,
        "profitability_claim_eligible": False,
        "ross_replication_claim_eligible": False,
    }
    report = _finish(report)
    validate_management_projection(report)
    return report


def validate_management_projection(payload: Mapping[str, object]) -> None:
    if _walk_keys(payload) & _FORBIDDEN_KEYS:
        raise ValueError("management projection contains retrospective keys")
    expected_fields = {
        "schema_version",
        "artifact_id",
        "artifact_type",
        "contract_id",
        "contract_content_sha256",
        "panel_id",
        "trading_date",
        "projection_frozen_at",
        "daily_runtime_content_sha256",
        "management_capture_content_sha256",
        "cell_count",
        "decision_count",
        "cells",
        "decisions",
        "sessions",
        "parent_ledger_mutated",
        "portfolio_financial_metrics_eligible",
        "sell_fees_or_realized_pnl_computed",
        "retrospective_labels_loaded",
        "raw_transcript_text_persisted",
        "broker_order_submitted",
        "paper_order_submitted",
        "live_order_submitted",
        "best_cell_selected",
        "policy_promotion_eligible",
        "profitability_claim_eligible",
        "ross_replication_claim_eligible",
        "content_sha256",
    }
    if set(payload) != expected_fields:
        raise ValueError("management projection fields changed")
    expected = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": PROJECTION_ARTIFACT_TYPE,
        "contract_id": CONTRACT_ID,
        "contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "panel_id": PANEL_ID,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise ValueError(f"management projection {field} changed")
    _validate_hash(payload, "management projection")
    trading_date = str(payload.get("trading_date", ""))
    if trading_date not in REGISTERED_DATES:
        raise ValueError("management projection date is not registered")
    if payload.get("artifact_id") != (
        f"prospective-management-window-projection-{trading_date}"
    ):
        raise ValueError("management projection artifact ID changed")
    _aware(payload.get("projection_frozen_at"), "projection_frozen_at")
    _sha(payload.get("daily_runtime_content_sha256"), "daily_runtime_content_sha256")
    _sha(
        payload.get("management_capture_content_sha256"),
        "management_capture_content_sha256",
    )
    for field in (
        "parent_ledger_mutated",
        "portfolio_financial_metrics_eligible",
        "sell_fees_or_realized_pnl_computed",
        "retrospective_labels_loaded",
        "raw_transcript_text_persisted",
        "broker_order_submitted",
        "paper_order_submitted",
        "live_order_submitted",
        "best_cell_selected",
        "policy_promotion_eligible",
        "profitability_claim_eligible",
        "ross_replication_claim_eligible",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"management projection boundary changed at {field}")
    cells = [
        _mapping(row, "projection cell")
        for row in _list(payload.get("cells"), "cells")
    ]
    decisions = [
        RuntimeDecision.from_mapping(_mapping(row, "projected decision")).as_dict()
        for row in _list(payload.get("decisions"), "decisions")
    ]
    sessions = [
        AccountSessionPerformance.from_mapping(_mapping(row, "projected session")).as_dict()
        for row in _list(payload.get("sessions"), "sessions")
    ]
    if _integer(payload.get("cell_count"), "cell_count") != len(cells) or len(cells) != 12:
        raise ValueError("management projection must retain twelve cells")
    if len(sessions) != len(cells):
        raise ValueError("management projection session count changed")
    if _integer(payload.get("decision_count"), "decision_count") != len(decisions):
        raise ValueError("management projection decision count changed")
    cell_fields = {
        "schema_version",
        "artifact_type",
        "contract_id",
        "contract_content_sha256",
        "panel_id",
        "trading_date",
        "account",
        "behavioral_horizon_seconds",
        "execution_scenario_id",
        "parent_runtime_content_sha256",
        "candidate_decisions",
        "management_outcomes",
        "performance",
        "parent_ledger_mutated",
        "portfolio_financial_metrics_eligible",
        "sell_fees_or_realized_pnl_computed",
        "content_sha256",
    }
    expected_cell_keys = {
        (horizon, scenario, account)
        for horizon, scenario in registered_cells()
        for account in ACCOUNT_KEYS
    }
    actual_cell_keys: set[tuple[int, str, str]] = set()
    expected_decisions: list[dict[str, object]] = []
    expected_sessions: list[dict[str, object]] = []
    cell_hashes: set[str] = set()
    for cell_index, cell in enumerate(cells):
        if set(cell) != cell_fields:
            raise ValueError("management projection cell fields changed")
        cell_hash = _validate_hash(cell, "projection cell")
        cell_hashes.add(cell_hash)
        for field, value in {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "prospective_management_window_projection_cell",
            "contract_id": CONTRACT_ID,
            "contract_content_sha256": CONTRACT_CONTENT_SHA256,
            "panel_id": PANEL_ID,
            "trading_date": trading_date,
            "parent_ledger_mutated": False,
            "portfolio_financial_metrics_eligible": False,
            "sell_fees_or_realized_pnl_computed": False,
        }.items():
            if cell.get(field) != value:
                raise ValueError(f"management projection cell {field} changed")
        account = str(cell.get("account", ""))
        horizon = _integer(
            cell.get("behavioral_horizon_seconds"),
            "behavioral_horizon_seconds",
            minimum=1,
        )
        scenario = str(cell.get("execution_scenario_id", ""))
        actual_cell_keys.add((horizon, scenario, account))
        _sha(
            cell.get("parent_runtime_content_sha256"),
            "parent_runtime_content_sha256",
        )
        cell_decisions = [
            _mapping(row, f"projection cell {cell_index} decision")
            for row in _list(cell.get("candidate_decisions"), "candidate_decisions")
        ]
        outcomes = [
            _mapping(row, f"projection cell {cell_index} outcome")
            for row in _list(cell.get("management_outcomes"), "management_outcomes")
        ]
        if len(cell_decisions) != len(outcomes):
            raise ValueError("management projection decisions and outcomes differ")
        for decision_index, (decision, outcome) in enumerate(
            zip(cell_decisions, outcomes, strict=True)
        ):
            normalized = RuntimeDecision.from_mapping(
                {**decision, "runtime_content_sha256": cell_hash}
            ).as_dict()
            if (
                normalized["account"] != account
                or normalized["behavioral_horizon_seconds"] != horizon
                or normalized["execution_scenario_id"] != scenario
                or normalized["trading_date"] != trading_date
            ):
                raise ValueError("management projection decision left its cell")
            if set(outcome) != {
                "symbol",
                "opportunity_id",
                "projection_status",
                "reason",
                "outcome",
            }:
                raise ValueError("management projection outcome fields changed")
            if outcome.get("symbol") != normalized["symbol"]:
                raise ValueError(
                    f"management projection outcome {decision_index} symbol differs"
                )
            projection_status = str(outcome.get("projection_status", ""))
            nested_outcome = outcome.get("outcome")
            if normalized["entry_status"] != "filled":
                if (
                    projection_status != "not_applicable_no_frozen_entry"
                    or nested_outcome is not None
                    or outcome.get("reason") is not None
                ):
                    raise ValueError("nonfilled entry acquired a management outcome")
            elif normalized["exit_status"] == "unavailable":
                if (
                    projection_status != "unavailable"
                    or nested_outcome is not None
                    or not isinstance(outcome.get("reason"), str)
                    or not str(outcome.get("reason")).strip()
                ):
                    raise ValueError("unavailable management outcome is inconsistent")
            else:
                if not isinstance(nested_outcome, Mapping):
                    raise ValueError("projected exit requires a management outcome")
                if outcome.get("reason") is not None:
                    raise ValueError("available management outcome cannot carry a reason")
                nested_status = str(nested_outcome.get("status", ""))
                expected_status = (
                    "closed_transaction_proxy"
                    if nested_status == "closed"
                    else nested_status
                )
                if projection_status != expected_status:
                    raise ValueError("management outcome status differs from projection")
                if (
                    (nested_status == "closed")
                    != (normalized["exit_status"] == "closed")
                ):
                    raise ValueError("management outcome differs from decision exit")
                if nested_outcome.get("cell_id") != SELECTED_CELL_ID or (
                    nested_outcome.get("execution_evidence")
                    != "sip_transaction_proxy_not_broker_fill"
                ):
                    raise ValueError("management outcome authority boundary changed")
            expected_decisions.append(normalized)
        performance = AccountSessionPerformance.from_mapping(
            {
                **_mapping(cell.get("performance"), "cell performance"),
                "runtime_content_sha256": cell_hash,
            }
        ).as_dict()
        if (
            performance["account"] != account
            or performance["behavioral_horizon_seconds"] != horizon
            or performance["execution_scenario_id"] != scenario
            or performance["trading_date"] != trading_date
        ):
            raise ValueError("management projection performance left its cell")
        expected_sessions.append(performance)
    if len(cell_hashes) != len(cells):
        raise ValueError("management projection cell hashes must be unique")
    if actual_cell_keys != expected_cell_keys:
        raise ValueError("management projection cells differ from the registry")
    if decisions != expected_decisions:
        raise ValueError("flattened management decisions differ from cells")
    if sessions != expected_sessions:
        raise ValueError("flattened management sessions differ from cells")


def write_management_artifact(
    output_dir: str | Path,
    payload: Mapping[str, object],
    *,
    filename: str,
) -> Path:
    if filename == CAPTURE_FILE:
        validate_management_capture(payload)
    elif filename == PROJECTION_FILE:
        validate_management_projection(payload)
    elif filename == REQUEST_FILE:
        _validate_hash(payload, "management request manifest")
    else:
        raise ValueError("unregistered management artifact filename")
    target = Path(output_dir)
    if target.exists():
        if not target.is_dir() or any(target.iterdir()):
            raise FileExistsError("management output directory must be absent or empty")
    else:
        target.mkdir(parents=True)
    path = target / filename
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def write_management_capture_bundle(
    output_dir: str | Path,
    request_manifest: Mapping[str, object],
    capture: Mapping[str, object],
) -> tuple[Path, Path]:
    _validate_hash(request_manifest, "management request manifest")
    validate_management_capture(capture)
    if capture.get("request_manifest_content_sha256") != request_manifest.get(
        "content_sha256"
    ):
        raise ValueError("management capture does not bind its request manifest")
    target = Path(output_dir)
    if target.exists():
        if not target.is_dir() or any(target.iterdir()):
            raise FileExistsError("management output directory must be absent or empty")
    else:
        target.mkdir(parents=True)
    request_path = target / REQUEST_FILE
    capture_path = target / CAPTURE_FILE
    for path, payload in (
        (request_path, request_manifest),
        (capture_path, capture),
    ):
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    return request_path, capture_path


def load_json_object(path: str | Path, field: str) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{field} root must be an object")
    return payload
