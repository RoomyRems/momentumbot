"""Build the preregistered fixed-entry trade-management sensitivity.

The builder verifies the exact frozen July Micro ZIP and historical account
manifest, evaluates every already-filled Micro plan under all four registered
management cells, and then projects those same outcomes onto only the entries
that the historical account diagnostic had already accepted.

It intentionally does not recompute candidate selection, entries, capital
reuse, or account chronology.  The output is a retrospective engineering and
fixed-entry diagnostic, not a portfolio backtest or profitability estimate.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from zipfile import ZipFile

import pandas as pd

from momentumbot.micro_execution import MicroEntryPlan, execution_eligible_trades
from momentumbot.research.trade_management_shadow import (
    CONTRACT_CONTENT_SHA256,
    CONTRACT_ID,
    EVIDENCE_AUDIT_CONTENT_SHA256,
    REGISTERED_CELLS,
    TradeManagementOutcome,
    simulate_trade_management_on_execution_path,
)


SCHEMA_VERSION = 1
MICRO_ZIP_SHA256 = (
    "3b59e4b1a69e268158f6ccbead1fe9abae425fc249e72b34f466e53ebba56b20"
)
MICRO_MANIFEST_CONTENT_SHA256 = (
    "feb2283acf1f180fd82b0e3c25acde1ebb9ebc036c47533e1d61fc9e8883e190"
)
ACCOUNT_MANIFEST_CONTENT_SHA256 = (
    "e9dd428d30790dcbf9cd2d171cc2c86ef41a71e4c9a2463d24bfaa34d7048a48"
)
REGISTERED_DATES = (
    "2026-07-10",
    "2026-07-13",
    "2026-07-14",
    "2026-07-15",
    "2026-07-16",
    "2026-07-17",
    "2026-07-20",
    "2026-07-21",
    "2026-07-22",
    "2026-07-23",
)
EXPECTED_FILLED_PLAN_COUNT = 87
EXPECTED_ACCOUNT_ENTRY_COUNTS = {"main": 10, "small": 2}
ACCOUNT_FIXED_EQUITY = {"main": 30_000.0, "small": 2_000.0}
REQUIRED_LABELS = (
    "retrospective",
    "fixed-entry sensitivity",
    "diagnostic-only",
    "non-promotable",
    "not-a-full-backtest",
)


@dataclass(slots=True)
class _AcceptedEntry:
    account_class: str
    session_date: str
    activation_id: str
    runtime_content_sha256: str
    plan_id: str
    fill_id: str
    symbol: str
    fill_time: pd.Timestamp
    fill_price: float
    stop_price: float
    quantity: int
    result_id: str | None = None


def build_trade_management_sensitivity(
    micro_zip: str | Path,
    account_root: str | Path,
    registration: Mapping[str, object],
    evidence_audit: Mapping[str, object],
) -> dict[str, object]:
    """Evaluate every registered cell on the exact frozen source paths."""
    validate_trade_management_registration(registration, evidence_audit)
    micro_path = Path(micro_zip)
    account_path = Path(account_root)
    _require_file_hash(micro_path, MICRO_ZIP_SHA256, "Micro runtime ZIP")
    account_manifest = _read_frozen_file(account_path / "manifest.json")
    if account_manifest["content_sha256"] != ACCOUNT_MANIFEST_CONTENT_SHA256:
        raise ValueError("historical account manifest differs from registration")
    accepted_entries = _load_accepted_entries(account_path, account_manifest)

    filled_results: list[dict[str, object]] = []
    accepted_by_runtime: dict[str, list[_AcceptedEntry]] = {}
    for entry in accepted_entries:
        accepted_by_runtime.setdefault(entry.runtime_content_sha256, []).append(entry)

    with ZipFile(micro_path) as archive:
        micro_manifest = _read_frozen_archive_json(archive, "manifest.json")
        if micro_manifest["content_sha256"] != MICRO_MANIFEST_CONTENT_SHA256:
            raise ValueError("Micro aggregate manifest differs from registration")
        if tuple(micro_manifest.get("dates", ())) != REGISTERED_DATES:
            raise ValueError("Micro aggregate dates differ from registration")

        runtime_names = sorted(
            name
            for name in archive.namelist()
            if name.startswith("dates/") and name.endswith("/runtime-replay.json")
        )
        for runtime_name in runtime_names:
            runtime = _read_frozen_archive_json(archive, runtime_name)
            steps = runtime.get("steps")
            if not isinstance(steps, list):
                raise ValueError(f"{runtime_name} steps must be an array")
            filled_steps = [
                step
                for step in steps
                if isinstance(step, Mapping)
                and isinstance(step.get("outcome"), Mapping)
                and step["outcome"].get("fill_price") is not None
            ]
            if not filled_steps:
                continue

            parts = runtime_name.split("/")
            if len(parts) != 4:
                raise ValueError("unexpected runtime path shape")
            trading_date, symbol = parts[1], parts[2]
            if trading_date not in REGISTERED_DATES:
                raise ValueError("runtime contains an unregistered date")
            if runtime.get("trading_date") != trading_date or runtime.get("symbol") != symbol:
                raise ValueError("runtime path and payload identity differ")
            runtime_hash = str(runtime["content_sha256"])

            prefix = f"dates/{trading_date}/{symbol}"
            bars_10s = _read_frame(archive, f"{prefix}/bars-10s.csv.gz")
            bars_1m = _read_frame(archive, f"{prefix}/session-1m.csv.gz")
            trades = _read_frame(archive, f"{prefix}/trades.csv.gz")
            execution_path = execution_eligible_trades(trades)

            for step in filled_steps:
                plan_payload = step.get("plan")
                outcome_payload = step.get("outcome")
                if not isinstance(plan_payload, Mapping) or not isinstance(
                    outcome_payload,
                    Mapping,
                ):
                    raise ValueError("filled step lacks plan or outcome")
                plan = _micro_plan(plan_payload)
                fill_time = _aware_timestamp(outcome_payload.get("fill_time"), "fill_time")
                fill_price = _finite_positive(outcome_payload.get("fill_price"), "fill_price")
                if plan.symbol != symbol:
                    raise ValueError("filled plan symbol differs from runtime")
                result_id = "management-result-" + canonical_fingerprint(
                    {
                        "runtime_content_sha256": runtime_hash,
                        "evaluated_at": step.get("evaluated_at"),
                        "fill_time": fill_time.isoformat(),
                        "fill_price": fill_price,
                        "plan": dict(plan_payload),
                    }
                )
                cell_results: dict[str, object] = {}
                outcomes: dict[str, TradeManagementOutcome] = {}
                for cell in REGISTERED_CELLS:
                    bars = bars_10s if cell.bar_seconds == 10 else bars_1m
                    managed = simulate_trade_management_on_execution_path(
                        plan,
                        fill_time=fill_time,
                        fill_price=fill_price,
                        bars=bars,
                        execution_path=execution_path,
                        cell=cell,
                    )
                    outcomes[cell.cell_id] = managed
                    cell_results[cell.cell_id] = _management_outcome_payload(managed)

                row = {
                    "result_id": result_id,
                    "trading_date": trading_date,
                    "symbol": symbol,
                    "runtime_content_sha256": runtime_hash,
                    "evaluated_at": step.get("evaluated_at"),
                    "pullback_number": step.get("pullback_number"),
                    "source_outcome_status": outcome_payload.get("status"),
                    "fill_time": fill_time.isoformat(),
                    "fill_price": fill_price,
                    "stop_price": float(plan.stop_price),
                    "cells": cell_results,
                }
                filled_results.append(row)
                _match_accepted_entries(
                    accepted_by_runtime.get(runtime_hash, ()),
                    plan,
                    fill_time,
                    fill_price,
                    result_id,
                )

    filled_results.sort(
        key=lambda row: (
            str(row["trading_date"]),
            str(row["symbol"]),
            str(row["fill_time"]),
            str(row["result_id"]),
        )
    )
    if len(filled_results) != EXPECTED_FILLED_PLAN_COUNT:
        raise ValueError("filled Micro plan count differs from frozen source")
    unmatched = [entry.fill_id for entry in accepted_entries if entry.result_id is None]
    if unmatched:
        raise ValueError(f"accepted account entries did not match source plans: {unmatched}")

    result_by_id = {str(row["result_id"]): row for row in filled_results}
    account_results = _account_overlay_results(accepted_entries, result_by_id)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "trade_management_shadow_fixed_entry_sensitivity",
        "contract_id": CONTRACT_ID,
        "labels": list(REQUIRED_LABELS),
        "source_binding": {
            "micro_runtime_zip_sha256": MICRO_ZIP_SHA256,
            "micro_runtime_manifest_content_sha256": MICRO_MANIFEST_CONTENT_SHA256,
            "historical_account_manifest_content_sha256": ACCOUNT_MANIFEST_CONTENT_SHA256,
            "registration_content_sha256": CONTRACT_CONTENT_SHA256,
            "evidence_audit_content_sha256": EVIDENCE_AUDIT_CONTENT_SHA256,
        },
        "dates": list(REGISTERED_DATES),
        "registered_cells": [
            {
                "cell_id": cell.cell_id,
                "bar_seconds": cell.bar_seconds,
                "scale_half_at_two_r": cell.scale_half_at_two_r,
            }
            for cell in REGISTERED_CELLS
        ],
        "engineering_summary": _engineering_summary(filled_results),
        "account_fixed_entry_summary": _account_summary(account_results),
        "account_fixed_entry_results": account_results,
        "filled_plan_results": filled_results,
        "interpretation": {
            "all_registered_cells_reported": True,
            "best_cell_selected": False,
            "selection_entry_or_sizing_changed": False,
            "account_capital_reuse_recomputed": False,
            "unresolved_positions_marked_to_market": False,
            "level2_or_aggressor_side_modeled": False,
            "portfolio_backtest": False,
            "economic_return_estimate": False,
            "policy_promotion_allowed": False,
            "prospective_august_panel_unchanged": True,
        },
    }
    return _freeze(manifest)


def validate_trade_management_registration(
    registration: Mapping[str, object],
    evidence_audit: Mapping[str, object],
) -> None:
    if canonical_fingerprint(registration) != CONTRACT_CONTENT_SHA256:
        raise ValueError("trade-management registration content differs")
    if canonical_fingerprint(evidence_audit) != EVIDENCE_AUDIT_CONTENT_SHA256:
        raise ValueError("trade-management evidence audit content differs")
    if registration.get("contract_id") != CONTRACT_ID:
        raise ValueError("trade-management contract_id differs")
    status = registration.get("execution_status")
    if status != {
        "management_path_execution": "not_started_at_registration",
        "runtime_artifact_sha256": None,
    }:
        raise ValueError("registration execution status changed")
    registered = registration.get("registered_cells")
    if not isinstance(registered, list):
        raise ValueError("registered_cells must be an array")
    expected = [cell.cell_id for cell in REGISTERED_CELLS]
    observed = [row.get("cell_id") for row in registered if isinstance(row, Mapping)]
    if observed != expected:
        raise ValueError("registered cell ordering differs")


def load_json_object(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} root must be an object")
    return payload


def canonical_fingerprint(payload: object) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _canonical_json(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _freeze(payload: dict[str, object]) -> dict[str, object]:
    result = dict(payload)
    result["content_sha256"] = canonical_fingerprint(result)
    return result


def _require_file_hash(path: Path, expected: str, label: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise ValueError(f"{label} SHA-256 differs from registration")


def _validate_frozen_payload(payload: object, label: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError(f"{label} root must be an object")
    embedded = payload.get("content_sha256")
    if not isinstance(embedded, str):
        raise ValueError(f"{label} lacks content_sha256")
    recomputed = canonical_fingerprint(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )
    if recomputed != embedded:
        raise ValueError(f"{label} embedded content SHA-256 is invalid")
    return payload


def _read_frozen_file(path: Path) -> dict[str, object]:
    return _validate_frozen_payload(json.loads(path.read_text(encoding="utf-8")), str(path))


def _read_frozen_archive_json(archive: ZipFile, name: str) -> dict[str, object]:
    return _validate_frozen_payload(json.loads(archive.read(name)), name)


def _read_frame(archive: ZipFile, name: str) -> pd.DataFrame:
    frame = pd.read_csv(io.BytesIO(archive.read(name)), compression="gzip")
    if "timestamp" not in frame.columns:
        raise ValueError(f"{name} lacks timestamp")
    timestamps = pd.to_datetime(frame.pop("timestamp"), utc=True, format="mixed")
    frame.index = pd.DatetimeIndex(timestamps)
    if not frame.index.is_monotonic_increasing:
        raise ValueError(f"{name} is not time ordered")
    return frame


def _aware_timestamp(value: object, name: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return timestamp


def _finite_positive(value: object, name: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return numeric


def _micro_plan(payload: Mapping[str, object]) -> MicroEntryPlan:
    return MicroEntryPlan(
        symbol=str(payload.get("symbol") or ""),
        source_bar_start=_aware_timestamp(payload.get("source_bar_start"), "source_bar_start"),
        armed_at=_aware_timestamp(payload.get("armed_at"), "armed_at"),
        expires_at=_aware_timestamp(payload.get("expires_at"), "expires_at"),
        breakout_level=_finite_positive(payload.get("breakout_level"), "breakout_level"),
        minimum_new_high_price=_finite_positive(
            payload.get("minimum_new_high_price"),
            "minimum_new_high_price",
        ),
        stop_price=_finite_positive(payload.get("stop_price"), "stop_price"),
    )


def _account_plan_id(activation_id: str, plan: MicroEntryPlan) -> str:
    fields = {
        "activation_id": activation_id,
        "symbol": plan.symbol,
        "source_bar_start": pd.Timestamp(plan.source_bar_start).isoformat(),
        "armed_at": pd.Timestamp(plan.armed_at).isoformat(),
        "expires_at": pd.Timestamp(plan.expires_at).isoformat(),
        "breakout_level": float(plan.breakout_level),
        "minimum_new_high_price": float(plan.minimum_new_high_price),
        "stop_price": float(plan.stop_price),
    }
    return "plan-" + canonical_fingerprint(fields)


def _load_accepted_entries(
    root: Path,
    manifest: Mapping[str, object],
) -> list[_AcceptedEntry]:
    session_index = manifest.get("sessions")
    if not isinstance(session_index, list):
        raise ValueError("account manifest sessions must be an array")
    entries: list[_AcceptedEntry] = []
    for index_row in session_index:
        if not isinstance(index_row, Mapping):
            raise ValueError("account session index row must be an object")
        relative = str(index_row.get("path") or "")
        session = _read_frozen_file(root / relative)
        if session.get("content_sha256") != index_row.get("content_sha256"):
            raise ValueError("account session hash differs from manifest")
        account_class = str(session.get("account_class") or "")
        session_date = str(session.get("session_date") or "")
        engine = session.get("composition_engine_output")
        if not isinstance(engine, Mapping):
            raise ValueError("account session lacks composition engine output")
        records = engine.get("candidate_records")
        events = engine.get("integration_events")
        if not isinstance(records, list) or not isinstance(events, list):
            raise ValueError("account session engine records/events are malformed")
        runtime_by_activation = {
            str(row.get("activation_id")): str(row.get("micro_runtime_content_sha256"))
            for row in records
            if isinstance(row, Mapping)
        }
        for event in events:
            if not isinstance(event, Mapping) or event.get("event_type") != "entry_accepted":
                continue
            activation_id = str(event.get("activation_id") or "")
            entries.append(
                _AcceptedEntry(
                    account_class=account_class,
                    session_date=session_date,
                    activation_id=activation_id,
                    runtime_content_sha256=runtime_by_activation[activation_id],
                    plan_id=str(event.get("plan_id") or ""),
                    fill_id=str(event.get("fill_id") or ""),
                    symbol=str(event.get("symbol") or ""),
                    fill_time=_aware_timestamp(event.get("at"), "account fill at"),
                    fill_price=_finite_positive(event.get("fill_price"), "account fill_price"),
                    stop_price=_finite_positive(event.get("stop_price"), "account stop_price"),
                    quantity=int(event.get("quantity", 0)),
                )
            )
    observed = Counter(entry.account_class for entry in entries)
    if dict(observed) != EXPECTED_ACCOUNT_ENTRY_COUNTS:
        raise ValueError("accepted account entry counts differ from frozen diagnostic")
    if any(entry.quantity <= 0 for entry in entries):
        raise ValueError("accepted account quantities must be positive")
    return entries


def _match_accepted_entries(
    entries: object,
    plan: MicroEntryPlan,
    fill_time: pd.Timestamp,
    fill_price: float,
    result_id: str,
) -> None:
    for entry in entries:
        if not isinstance(entry, _AcceptedEntry):
            raise TypeError("accepted entry index is malformed")
        if entry.plan_id != _account_plan_id(entry.activation_id, plan):
            continue
        if entry.result_id is not None:
            raise ValueError("accepted account entry matched multiple source steps")
        if entry.symbol != plan.symbol:
            raise ValueError("account and source plan symbols differ")
        if entry.fill_time != fill_time or not math.isclose(
            entry.fill_price,
            fill_price,
            abs_tol=1e-9,
        ):
            raise ValueError("account and source fill differ")
        if not math.isclose(entry.stop_price, plan.stop_price, abs_tol=1e-9):
            raise ValueError("account and source stop differ")
        entry.result_id = result_id


def _management_outcome_payload(outcome: TradeManagementOutcome) -> dict[str, object]:
    return {
        "status": outcome.status,
        "initial_risk_per_share": outcome.initial_risk_per_share,
        "first_target_price": outcome.first_target_price,
        "first_red_signal_at": (
            outcome.first_red_signal_at.isoformat()
            if outcome.first_red_signal_at is not None
            else None
        ),
        "target_touched": outcome.target_touched,
        "stop_moved_to_breakeven": outcome.stop_moved_to_breakeven,
        "active_stop_price": outcome.active_stop_price,
        "realized_fraction": outcome.realized_fraction,
        "remaining_fraction": outcome.remaining_fraction,
        "weighted_realized_r": outcome.weighted_realized_r,
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
    }


def _engineering_summary(rows: list[Mapping[str, object]]) -> dict[str, object]:
    summary: dict[str, object] = {}
    for cell in REGISTERED_CELLS:
        cell_rows = [row["cells"][cell.cell_id] for row in rows]
        reasons = Counter(
            str(leg["reason"])
            for outcome in cell_rows
            for leg in outcome["legs"]
        )
        statuses = Counter(str(outcome["status"]) for outcome in cell_rows)
        summary[cell.cell_id] = {
            "filled_plan_count": len(cell_rows),
            "status_counts": dict(sorted(statuses.items())),
            "target_touched_count": sum(bool(row["target_touched"]) for row in cell_rows),
            "stop_moved_to_breakeven_count": sum(
                bool(row["stop_moved_to_breakeven"]) for row in cell_rows
            ),
            "exit_leg_reason_counts": dict(sorted(reasons.items())),
            "sum_weighted_realized_r_without_open_mark": sum(
                float(row["weighted_realized_r"]) for row in cell_rows
            ),
            "remaining_fraction_sum_without_mark": sum(
                float(row["remaining_fraction"]) for row in cell_rows
            ),
            "overlapping_plan_outcomes": True,
            "strategy_expectancy_claim": False,
        }
    return summary


def _account_overlay_results(
    entries: list[_AcceptedEntry],
    result_by_id: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for entry in entries:
        assert entry.result_id is not None
        source = result_by_id[entry.result_id]
        for cell in REGISTERED_CELLS:
            outcome = source["cells"][cell.cell_id]
            realized_pnl = entry.quantity * sum(
                float(leg["quantity_fraction"])
                * (float(leg["exit_price"]) - entry.fill_price)
                for leg in outcome["legs"]
            )
            rows.append(
                {
                    "account_class": entry.account_class,
                    "session_date": entry.session_date,
                    "activation_id": entry.activation_id,
                    "plan_id": entry.plan_id,
                    "fill_id": entry.fill_id,
                    "management_result_id": entry.result_id,
                    "cell_id": cell.cell_id,
                    "symbol": entry.symbol,
                    "fill_time": entry.fill_time.isoformat(),
                    "fill_price": entry.fill_price,
                    "stop_price": entry.stop_price,
                    "accepted_quantity": entry.quantity,
                    "initial_risk_dollars": (
                        entry.quantity * (entry.fill_price - entry.stop_price)
                    ),
                    "realized_pnl_without_open_mark": realized_pnl,
                    "weighted_realized_r": outcome["weighted_realized_r"],
                    "status": outcome["status"],
                    "target_touched": outcome["target_touched"],
                    "remaining_quantity_equivalent": (
                        entry.quantity * float(outcome["remaining_fraction"])
                    ),
                    "remaining_entry_notional_without_mark": (
                        entry.quantity
                        * float(outcome["remaining_fraction"])
                        * entry.fill_price
                    ),
                    "exit_legs": outcome["legs"],
                }
            )
    rows.sort(
        key=lambda row: (
            str(row["account_class"]),
            str(row["cell_id"]),
            str(row["session_date"]),
            str(row["fill_time"]),
            str(row["fill_id"]),
        )
    )
    return rows


def _account_summary(rows: list[Mapping[str, object]]) -> dict[str, object]:
    summary: dict[str, object] = {}
    for account_class, fixed_equity in ACCOUNT_FIXED_EQUITY.items():
        summary[account_class] = {}
        for cell in REGISTERED_CELLS:
            selected = [
                row
                for row in rows
                if row["account_class"] == account_class
                and row["cell_id"] == cell.cell_id
            ]
            statuses = Counter(str(row["status"]) for row in selected)
            pnl = sum(float(row["realized_pnl_without_open_mark"]) for row in selected)
            summary[account_class][cell.cell_id] = {
                "fixed_entry_count": len(selected),
                "status_counts": dict(sorted(statuses.items())),
                "target_touched_count": sum(bool(row["target_touched"]) for row in selected),
                "sum_realized_pnl_without_open_mark": pnl,
                "sum_realized_pnl_over_one_fixed_session_equity": pnl / fixed_equity,
                "remaining_quantity_equivalent_without_mark": sum(
                    float(row["remaining_quantity_equivalent"]) for row in selected
                ),
                "remaining_entry_notional_without_mark": sum(
                    float(row["remaining_entry_notional_without_mark"])
                    for row in selected
                ),
                "capital_reuse_recomputed": False,
                "compounded_return_claim": False,
                "economic_return_claim": False,
            }
    return summary
