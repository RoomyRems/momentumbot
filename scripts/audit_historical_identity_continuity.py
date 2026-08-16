from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.identity_continuity import build_cross_date_identity_bridge
from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.providers.massive import MassiveReferenceClient


ET = ZoneInfo("America/New_York")
ACTION_TYPES = (
    "forward_split",
    "reverse_split",
    "unit_split",
    "stock_dividend",
    "spin_off",
    "cash_merger",
    "stock_merger",
    "stock_and_cash_merger",
    "redemption",
    "name_change",
    "worthless_removal",
    "rights_distribution",
    "partial_call",
    "reorganization",
)
_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
_BAR_FIELDS = ("open", "high", "low", "close", "volume", "trade_count", "vwap")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"expected object in {path}")
    return payload


def _fingerprint(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _bar_on(frame: pd.DataFrame, target: date) -> dict[str, float | int | None] | None:
    if frame.empty:
        return None
    local_dates = pd.Index(frame.index.tz_convert(ET).date)
    matches = frame.loc[local_dates == target]
    if matches.empty:
        return None
    row = matches.iloc[-1]
    output: dict[str, float | int | None] = {}
    for field in _BAR_FIELDS:
        value = row.get(field)
        if pd.isna(value):
            output[field] = None
        elif field in {"volume", "trade_count"}:
            output[field] = int(value)
        else:
            output[field] = float(value)
    return output


def _bars_equal(
    left: dict[str, float | int | None] | None,
    right: dict[str, float | int | None] | None,
) -> tuple[bool, str]:
    if left is None or right is None:
        missing = []
        if left is None:
            missing.append("earlier_alias_view")
        if right is None:
            missing.append("later_alias_view")
        return False, "missing_" + "_and_".join(missing)
    for field in _BAR_FIELDS:
        first = left[field]
        second = right[field]
        if first is None or second is None:
            if first != second:
                return False, f"{field}_null_mismatch"
            continue
        if not math.isclose(float(first), float(second), rel_tol=1e-12, abs_tol=1e-12):
            return False, f"{field}_mismatch"
    return True, "exact_bar_match"


def _window(target: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(target - timedelta(days=7), time(0), timezone.utc),
        datetime.combine(target + timedelta(days=1), time(0), timezone.utc),
    )


def validate_alias_transitions(
    client: AlpacaDataClient,
    transitions: Iterable[dict[str, object]],
    *,
    earlier_date: date,
    later_date: date,
    batch_size: int,
) -> dict[str, object]:
    changed = [row for row in transitions if bool(row.get("ticker_changed"))]
    earlier_symbols = sorted({str(row["earlier_ticker"]) for row in changed})
    later_symbols = sorted({str(row["later_ticker"]) for row in changed})
    early_start, early_end = _window(earlier_date)
    late_start, late_end = _window(later_date)

    early_alias_at_early = client.bars_batched(
        earlier_symbols,
        batch_size=batch_size,
        timeframe="1Day",
        start=early_start,
        end=early_end,
        feed="sip",
        adjustment="raw",
        asof=earlier_date,
    )
    late_alias_at_early = client.bars_batched(
        later_symbols,
        batch_size=batch_size,
        timeframe="1Day",
        start=early_start,
        end=early_end,
        feed="sip",
        adjustment="raw",
        asof=later_date,
    )
    early_alias_at_late = client.bars_batched(
        earlier_symbols,
        batch_size=batch_size,
        timeframe="1Day",
        start=late_start,
        end=late_end,
        feed="sip",
        adjustment="raw",
        asof=earlier_date,
    )
    late_alias_at_late = client.bars_batched(
        later_symbols,
        batch_size=batch_size,
        timeframe="1Day",
        start=late_start,
        end=late_end,
        feed="sip",
        adjustment="raw",
        asof=later_date,
    )

    records: list[dict[str, object]] = []
    for transition in changed:
        earlier_ticker = str(transition["earlier_ticker"])
        later_ticker = str(transition["later_ticker"])
        early_left = _bar_on(early_alias_at_early[earlier_ticker], earlier_date)
        early_right = _bar_on(late_alias_at_early[later_ticker], earlier_date)
        late_left = _bar_on(early_alias_at_late[earlier_ticker], later_date)
        late_right = _bar_on(late_alias_at_late[later_ticker], later_date)
        early_match, early_reason = _bars_equal(early_left, early_right)
        late_match, late_reason = _bars_equal(late_left, late_right)
        records.append(
            {
                "identifier_kind": transition["identifier_kind"],
                "identifier": transition["identifier"],
                "earlier_ticker": earlier_ticker,
                "later_ticker": later_ticker,
                "symbol_reuse_involved": transition["symbol_reuse_involved"],
                "earlier_date_match": early_match,
                "earlier_date_reason": early_reason,
                "later_date_match": late_match,
                "later_date_reason": late_reason,
                "bidirectional_match": early_match and late_match,
            }
        )
    records.sort(
        key=lambda row: (
            str(row["identifier_kind"]),
            str(row["identifier"]),
        )
    )
    exact = [row for row in records if row["identifier_kind"] == "composite_figi"]
    fallback = [
        row for row in records if row["identifier_kind"] == "unique_cik_fallback"
    ]
    return {
        "schema_version": 1,
        "query_contract": {
            "feed": "sip",
            "timeframe": "1Day",
            "adjustment": "raw",
            "earlier_alias_asof": earlier_date.isoformat(),
            "later_alias_asof": later_date.isoformat(),
            "comparison_dates": [earlier_date.isoformat(), later_date.isoformat()],
            "provider_symbol_mapping_disabled": False,
        },
        "summary": {
            "changed_transition_count": len(records),
            "bidirectional_match_count": sum(
                bool(row["bidirectional_match"]) for row in records
            ),
            "exact_figi_transition_count": len(exact),
            "exact_figi_bidirectional_match_count": sum(
                bool(row["bidirectional_match"]) for row in exact
            ),
            "unique_cik_fallback_transition_count": len(fallback),
            "unique_cik_fallback_bidirectional_match_count": sum(
                bool(row["bidirectional_match"]) for row in fallback
            ),
            "symbol_reuse_transition_count": sum(
                bool(row["symbol_reuse_involved"]) for row in records
            ),
            "symbol_reuse_bidirectional_match_count": sum(
                bool(row["symbol_reuse_involved"])
                and bool(row["bidirectional_match"])
                for row in records
            ),
            "exact_figi_alias_validation_complete": all(
                bool(row["bidirectional_match"]) for row in exact
            ),
            "unique_cik_fallback_alias_validation_complete": all(
                bool(row["bidirectional_match"]) for row in fallback
            ),
        },
        "records": records,
    }


def extract_symbol_values(value: object, *, path: str = "") -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if isinstance(child, str) and (
                "symbol" in str(key).lower() or "ticker" in str(key).lower()
            ):
                rendered = child.strip().upper()
                if _SYMBOL_RE.fullmatch(rendered):
                    output.append({"path": child_path, "symbol": rendered})
            output.extend(extract_symbol_values(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            output.extend(extract_symbol_values(child, path=f"{path}[{index}]"))
    unique = {(row["path"], row["symbol"]): row for row in output}
    return [unique[key] for key in sorted(unique)]


def summarize_alpaca_actions(
    rows: Iterable[dict[str, object]],
    *,
    relevant_symbols: set[str],
) -> dict[str, object]:
    records = list(rows)
    relevant: list[dict[str, object]] = []
    schema_keys: set[str] = set()
    for row in records:
        schema_keys.update(str(key) for key in row)
        symbols = extract_symbol_values(row)
        matched = sorted(
            {item["symbol"] for item in symbols if item["symbol"] in relevant_symbols}
        )
        if matched:
            relevant.append(
                {
                    "action_type": row.get("action_type"),
                    "id": row.get("id"),
                    "matched_symbols": matched,
                    "symbol_fields": symbols,
                    "record": row,
                }
            )
    return {
        "total_action_count": len(records),
        "action_type_counts": dict(
            sorted(Counter(str(row.get("action_type", "")) for row in records).items())
        ),
        "observed_top_level_fields": sorted(schema_keys),
        "relevant_action_count": len(relevant),
        "relevant_actions": relevant,
    }


def summarize_massive_splits(
    rows: Iterable[dict[str, object]],
    *,
    relevant_symbols: set[str],
) -> dict[str, object]:
    records = list(rows)
    relevant = [row for row in records if str(row.get("ticker")) in relevant_symbols]
    return {
        "total_split_count": len(records),
        "adjustment_type_counts": dict(
            sorted(
                Counter(str(row.get("adjustment_type", "")) for row in records).items()
            )
        ),
        "relevant_split_count": len(relevant),
        "relevant_splits": relevant,
    }


def resolve_name_change_paths(
    transitions: Iterable[dict[str, object]],
    actions: Iterable[dict[str, object]],
    *,
    earlier_date: date,
    later_date: date,
    lookback_days: int,
    alias_records: Iterable[dict[str, object]],
) -> dict[str, object]:
    edges: list[dict[str, str]] = []
    for action in actions:
        if str(action.get("action_type")) != "name_changes":
            continue
        old_symbol = str(action.get("old_symbol") or "").strip().upper()
        new_symbol = str(action.get("new_symbol") or "").strip().upper()
        process_date = str(action.get("process_date") or "").strip()
        if (
            _SYMBOL_RE.fullmatch(old_symbol)
            and _SYMBOL_RE.fullmatch(new_symbol)
            and process_date
        ):
            parsed = date.fromisoformat(process_date)
            if earlier_date < parsed <= later_date:
                edges.append(
                    {
                        "id": str(action.get("id") or ""),
                        "old_symbol": old_symbol,
                        "new_symbol": new_symbol,
                        "process_date": process_date,
                        "old_cusip": str(action.get("old_cusip") or ""),
                        "new_cusip": str(action.get("new_cusip") or ""),
                    }
                )
    edges.sort(
        key=lambda row: (
            row["process_date"],
            row["old_symbol"],
            row["new_symbol"],
            row["id"],
        )
    )
    by_old: dict[str, list[dict[str, str]]] = {}
    for edge in edges:
        by_old.setdefault(edge["old_symbol"], []).append(edge)
    alias_by_identifier = {
        (str(row["identifier_kind"]), str(row["identifier"])): row
        for row in alias_records
    }
    late_lookback_start = later_date - timedelta(days=lookback_days)
    records: list[dict[str, object]] = []
    for transition in transitions:
        if not bool(transition.get("ticker_changed")):
            continue
        start_symbol = str(transition["earlier_ticker"])
        target_symbol = str(transition["later_ticker"])
        queue: list[tuple[str, str, list[dict[str, str]]]] = [
            (start_symbol, earlier_date.isoformat(), [])
        ]
        seen: set[tuple[str, str]] = {(start_symbol, earlier_date.isoformat())}
        path: list[dict[str, str]] | None = None
        while queue:
            current_symbol, last_date, current_path = queue.pop(0)
            if len(current_path) >= 20:
                continue
            for edge in by_old.get(current_symbol, []):
                if edge["process_date"] < last_date:
                    continue
                next_path = [*current_path, edge]
                if edge["new_symbol"] == target_symbol:
                    path = next_path
                    queue.clear()
                    break
                state = (edge["new_symbol"], edge["process_date"])
                if state not in seen:
                    seen.add(state)
                    queue.append((edge["new_symbol"], edge["process_date"], next_path))

        alias = alias_by_identifier.get(
            (str(transition["identifier_kind"]), str(transition["identifier"]))
        )
        full_gap_match = bool(alias and alias.get("bidirectional_match"))
        latest_change = max(
            (date.fromisoformat(edge["process_date"]) for edge in (path or [])),
            default=None,
        )
        outside_late_lookback = bool(
            latest_change is not None and latest_change < late_lookback_start
        )
        snapshot_window_safe = full_gap_match or outside_late_lookback
        records.append(
            {
                "identifier_kind": transition["identifier_kind"],
                "identifier": transition["identifier"],
                "earlier_ticker": start_symbol,
                "later_ticker": target_symbol,
                "full_gap_alias_match": full_gap_match,
                "name_change_path_found": path is not None,
                "name_change_path": path or [],
                "latest_name_change_process_date": (
                    latest_change.isoformat() if latest_change else None
                ),
                "later_snapshot_lookback_start": late_lookback_start.isoformat(),
                "name_change_precedes_later_lookback": outside_late_lookback,
                "snapshot_window_safe": snapshot_window_safe,
                "resolution": (
                    "provider_alias_mapping_verified"
                    if full_gap_match
                    else (
                        "alias_gap_outside_both_snapshot_lookbacks"
                        if outside_late_lookback
                        else "unresolved_snapshot_window_alias_gap"
                    )
                ),
            }
        )
    records.sort(
        key=lambda row: (
            str(row["identifier_kind"]),
            str(row["identifier"]),
        )
    )
    unresolved = [row for row in records if not bool(row["snapshot_window_safe"])]
    return {
        "schema_version": 1,
        "scope": {
            "earlier_date": earlier_date.isoformat(),
            "later_date": later_date.isoformat(),
            "later_snapshot_lookback_start": late_lookback_start.isoformat(),
            "lookback_days": lookback_days,
            "uses_benchmark_labels": False,
        },
        "summary": {
            "transition_count": len(records),
            "name_change_path_found_count": sum(
                bool(row["name_change_path_found"]) for row in records
            ),
            "full_gap_alias_match_count": sum(
                bool(row["full_gap_alias_match"]) for row in records
            ),
            "alias_gap_outside_snapshot_lookback_count": sum(
                row["resolution"] == "alias_gap_outside_both_snapshot_lookbacks"
                for row in records
            ),
            "unresolved_snapshot_window_alias_count": len(unresolved),
            "unresolved_snapshot_window_alias_tickers": sorted(
                {
                    str(value)
                    for row in unresolved
                    for value in (row["earlier_ticker"], row["later_ticker"])
                }
            ),
            "snapshot_window_alias_validation_complete": not unresolved,
        },
        "records": records,
    }


def audit_ticker_event_sample(
    client: MassiveReferenceClient,
    transitions: Iterable[dict[str, object]],
    *,
    sample_size: int,
) -> dict[str, object]:
    candidates = sorted(
        (
            row
            for row in transitions
            if bool(row.get("ticker_changed"))
            and row.get("identifier_kind") == "composite_figi"
        ),
        key=lambda row: str(row["identifier"]),
    )
    # Deterministic sample; this experimental endpoint is corroborative only.
    selected = candidates[:sample_size]
    records: list[dict[str, object]] = []
    for transition in selected:
        timeline = client.ticker_events(str(transition["identifier"]))
        symbol_fields = extract_symbol_values(list(timeline.events))
        observed = sorted({item["symbol"] for item in symbol_fields})
        expected = sorted(
            {
                str(transition["earlier_ticker"]),
                str(transition["later_ticker"]),
            }
        )
        records.append(
            {
                "identifier": transition["identifier"],
                "earlier_ticker": transition["earlier_ticker"],
                "later_ticker": transition["later_ticker"],
                "timeline_name": timeline.name,
                "event_count": len(timeline.events),
                "observed_symbols": observed,
                "expected_symbols": expected,
                "both_expected_symbols_observed": set(expected).issubset(observed),
                "events": list(timeline.events),
            }
        )
    return {
        "schema_version": 1,
        "selection_rule": "first_composite_figi_changed_transitions_sorted_by_figi",
        "sample_size_requested": sample_size,
        "sample_size_completed": len(records),
        "corroborative_only": True,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--census-root", type=Path, required=True)
    parser.add_argument("--dates", nargs=2, default=["2025-04-03", "2026-07-09"])
    parser.add_argument("--lookback-days", type=int, default=120)
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--minimum-massive-request-interval", type=float, default=12.5)
    parser.add_argument("--ticker-event-sample-size", type=int, default=10)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.lookback_days <= 0:
        raise ValueError("lookback days must be positive")
    if args.batch_size <= 0:
        raise ValueError("batch size must be positive")
    if args.ticker_event_sample_size < 0:
        raise ValueError("ticker-event sample size cannot be negative")

    rendered_dates = [date.fromisoformat(value) for value in args.dates]
    earlier_date, later_date = rendered_dates
    output_root = args.output or args.census_root / "identity-continuity-v0.1"
    output_root.mkdir(parents=True, exist_ok=True)
    provisional_root = args.census_root / "provisional-universe-v0.1"
    earlier_payload = _load_json(
        provisional_root / f"{earlier_date.isoformat()}-included.json"
    )
    later_payload = _load_json(
        provisional_root / f"{later_date.isoformat()}-included.json"
    )
    earlier_rows = earlier_payload.get("rows")
    later_rows = later_payload.get("rows")
    if not isinstance(earlier_rows, list) or not isinstance(later_rows, list):
        raise ValueError("provisional included artifacts must contain rows")

    bridge = build_cross_date_identity_bridge(
        earlier_rows,
        later_rows,
        earlier_date=earlier_date.isoformat(),
        later_date=later_date.isoformat(),
    )
    alpaca = AlpacaDataClient.from_env()
    alias_validation = validate_alias_transitions(
        alpaca,
        bridge["transitions"],
        earlier_date=earlier_date,
        later_date=later_date,
        batch_size=args.batch_size,
    )
    transition_actions = alpaca.corporate_actions(
        start=earlier_date + timedelta(days=1),
        end=later_date,
        types=("name_change",),
        data_quality="complete",
    )
    transition_resolution = resolve_name_change_paths(
        bridge["transitions"],
        transition_actions.rows,
        earlier_date=earlier_date,
        later_date=later_date,
        lookback_days=args.lookback_days,
        alias_records=alias_validation["records"],
    )
    transition_resolution["provider_query"] = transition_actions.query
    transition_resolution["provider_pages"] = [
        asdict(page) for page in transition_actions.pages
    ]
    massive = MassiveReferenceClient.from_env(
        minimum_request_interval_seconds=args.minimum_massive_request_interval
    )

    action_windows: dict[str, object] = {}
    rows_by_date = {
        earlier_date: earlier_rows,
        later_date: later_rows,
    }
    for target, included_rows in rows_by_date.items():
        start = target - timedelta(days=args.lookback_days)
        symbol_set = {str(row["ticker"]) for row in included_rows}
        alpaca_actions = alpaca.corporate_actions(
            start=start,
            end=target,
            types=ACTION_TYPES,
            data_quality="complete",
        )
        massive_splits = massive.stock_splits(start=start, end=target)
        alpaca_summary = summarize_alpaca_actions(
            alpaca_actions.rows,
            relevant_symbols=symbol_set,
        )
        massive_summary = summarize_massive_splits(
            massive_splits.rows,
            relevant_symbols=symbol_set,
        )
        action_windows[target.isoformat()] = {
            "start": start.isoformat(),
            "end": target.isoformat(),
            "included_symbol_count": len(symbol_set),
            "alpaca": {
                "query": alpaca_actions.query,
                "pages": [asdict(page) for page in alpaca_actions.pages],
                **alpaca_summary,
            },
            "massive": {
                "query": massive_splits.query,
                "pages": [asdict(page) for page in massive_splits.pages],
                **massive_summary,
            },
        }

    ticker_event_sample = audit_ticker_event_sample(
        massive,
        bridge["transitions"],
        sample_size=args.ticker_event_sample_size,
    )
    for name, payload in (
        ("identity-bridge.json", bridge),
        ("alias-validation.json", alias_validation),
        ("transition-name-change-resolution.json", transition_resolution),
        ("corporate-action-windows.json", action_windows),
        ("massive-ticker-event-sample.json", ticker_event_sample),
    ):
        (output_root / name).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n"
        )

    bridge_summary = bridge["summary"]
    alias_summary = alias_validation["summary"]
    transition_summary = transition_resolution["summary"]
    failed_alias_records = [
        record
        for record in alias_validation["records"]
        if not bool(record["bidirectional_match"])
    ]
    date_status = bridge["date_identity_status"]
    earlier_quarantine = date_status[earlier_date.isoformat()]["quarantined"]
    later_quarantine = date_status[later_date.isoformat()]["quarantined"]
    full_gap_alias_complete = bool(
        alias_summary["exact_figi_alias_validation_complete"]
    ) and bool(alias_summary["unique_cik_fallback_alias_validation_complete"])
    alias_gate = bool(transition_summary["snapshot_window_alias_validation_complete"])
    corporate_action_gate = all(
        bool(window["alpaca"]["pages"]) and bool(window["massive"]["pages"])
        for window in action_windows.values()
    ) and bool(transition_actions.pages)
    manifest: dict[str, object] = {
        "schema_version": 1,
        "audit_id": "historical-identity-corporate-action-audit-v0.1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "knowledge_policy": {
            "uses_benchmark_labels": False,
            "runtime_strategy_inputs_created": False,
            "corporate_actions_used_as_data_normalization_only": True,
            "ticker_event_sample_is_corroborative_only": True,
        },
        "source_artifacts": {
            earlier_date.isoformat(): {
                "included_membership_sha256": earlier_payload.get("membership_sha256"),
                "policy_fingerprint": earlier_payload.get("policy_fingerprint"),
            },
            later_date.isoformat(): {
                "included_membership_sha256": later_payload.get("membership_sha256"),
                "policy_fingerprint": later_payload.get("policy_fingerprint"),
            },
        },
        "scope": {
            "dates": [earlier_date.isoformat(), later_date.isoformat()],
            "corporate_action_lookback_days": args.lookback_days,
            "lookback_basis": "existing_full_feature_history_window",
        },
        "summary": {
            **bridge_summary,
            **alias_summary,
            **transition_summary,
            "earlier_identity_quarantine_tickers": [
                row["ticker"] for row in earlier_quarantine
            ],
            "later_identity_quarantine_tickers": [
                row["ticker"] for row in later_quarantine
            ],
            "failed_alias_records": failed_alias_records,
            "full_gap_alias_mapping_complete": full_gap_alias_complete,
            "alias_mapping_gate_pass": alias_gate,
            "bulk_corporate_action_gate_pass": corporate_action_gate,
        },
        "eligibility": {
            "identity_gate_passes_after_explicit_quarantine": alias_gate
            and corporate_action_gate,
            "universe_complete": False,
            "full_feature_snapshot_candidate": alias_gate and corporate_action_gate,
            "full_walk_forward_eligible": False,
            "policy_promotion_eligible": False,
        },
        "files": {
            "identity_bridge": "identity-bridge.json",
            "alias_validation": "alias-validation.json",
            "transition_name_change_resolution": "transition-name-change-resolution.json",
            "corporate_action_windows": "corporate-action-windows.json",
            "massive_ticker_event_sample": "massive-ticker-event-sample.json",
        },
    }
    manifest["content_sha256"] = _fingerprint(
        {
            "bridge": bridge,
            "alias_validation": alias_validation,
            "transition_resolution": transition_resolution,
            "action_windows": action_windows,
            "ticker_event_sample": ticker_event_sample,
        }
    )
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
