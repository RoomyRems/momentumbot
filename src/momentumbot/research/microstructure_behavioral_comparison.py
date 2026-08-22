"""Unarmed, label-blind pre/post microstructure comparison mechanics.

The comparator reports exact arithmetic differences across preregistered,
disjoint receive-time windows.  It cannot select a horizon or threshold,
classify intent, make a trading decision, request provider data, or consume
retrospective outcomes.
"""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path
from typing import Mapping, Sequence

from momentumbot.research.microstructure_contract import canonical_fingerprint
from momentumbot.research.microstructure_features import (
    FEATURE_SET_CONTENT_SHA256,
    FEATURE_SET_ID,
    REGISTERED_WINDOWS_NS,
)


SCHEMA_VERSION = 1
PROTOCOL_ID = "microstructure-behavioral-comparison-v0.1"
PROTOCOL_CONTENT_SHA256 = (
    "7409973d369876d29a020785cc2f48bc945129d705648f793d693667dcdd3802"
)
FOUR_CASE_SUCCESS_AUDIT_CONTENT_SHA256 = (
    "592a02b54fbaeb3182772905eb96fe50caba5c406e5aa79ee33218d8cb3c9ec5"
)

INTEGER_METRICS: tuple[tuple[str, tuple[str, ...], str | None], ...] = (
    (
        "tape.net-buy-minus-sell-shares",
        ("signed_trade_velocity", "net_buy_minus_sell_shares"),
        "signed_trade_velocity",
    ),
    (
        "tape.buy-executed-shares",
        ("execution_price_impact", "buy_executed_shares"),
        "execution_price_impact",
    ),
    (
        "tape.sell-executed-shares",
        ("execution_price_impact", "sell_executed_shares"),
        "execution_price_impact",
    ),
    (
        "tape.buy-positive-progress-nanos",
        ("execution_price_impact", "buy_positive_progress_nanos"),
        "execution_price_impact",
    ),
    (
        "book.ask-replenished-after-fill-shares",
        (
            "displayed_replenishment",
            "ask",
            "replenished_after_fill_shares",
        ),
        "displayed_replenishment",
    ),
    (
        "book.bid-replenished-after-fill-shares",
        (
            "displayed_replenishment",
            "bid",
            "replenished_after_fill_shares",
        ),
        "displayed_replenishment",
    ),
    (
        "book.ask-canceled-shares",
        ("book_flow", "ask", "canceled_shares"),
        "book_flow",
    ),
    (
        "book.bid-canceled-shares",
        ("book_flow", "bid", "canceled_shares"),
        "book_flow",
    ),
    (
        "breakout.buy-shares-at-or-above",
        ("breakout_progress_context", "buy_shares_at_or_above"),
        "breakout_progress_context",
    ),
    (
        "breakout.post-cross-sell-shares-below",
        (
            "breakout_progress_context",
            "post_cross_sell_shares_below_breakout",
        ),
        "breakout_progress_context",
    ),
)

RATIONAL_METRICS: tuple[
    tuple[str, tuple[str, ...], tuple[str, ...]], ...
] = (
    (
        "book.depth-imbalance",
        ("depth_imbalance_numerator",),
        ("depth_imbalance_denominator",),
    ),
    (
        "book.spread-bps",
        ("spread_bps_numerator",),
        ("spread_bps_denominator",),
    ),
)

DEPTH_WALK_FIELDS = (
    "displayed_filled_quantity",
    "displayed_unfilled_quantity",
    "worst_price_nanos",
    "notional_price_nanos_shares",
)


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object in {path}")
    return payload


def validate_behavioral_registration(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported behavioral-comparison schema")
    if payload.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("unexpected behavioral-comparison protocol")
    if payload.get("artifact_type") != (
        "preregistered_unarmed_label_blind_microstructure_behavioral_comparison"
    ):
        raise ValueError("unexpected behavioral-comparison artifact type")
    if payload.get("registration_status") != (
        "registered_before_feature_values_or_outcomes"
    ):
        raise ValueError("comparison must be registered before values or outcomes")
    if payload.get("runtime_strategy_effect") != "none_shadow_only":
        raise ValueError("comparison cannot affect runtime strategy")
    for field in (
        "provider_request_authorized",
        "provider_purchase_authorized",
        "execution_file_present",
        "policy_promotion_eligible",
        "profitability_claim_eligible",
        "exact_ross_replication_claim_eligible",
        "feature_threshold_selection_permitted",
        "horizon_selection_permitted",
        "retrospective_labels_allowed_in_runtime",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must be false")

    claimed = payload.get("content_sha256")
    if claimed != PROTOCOL_CONTENT_SHA256:
        raise ValueError("behavioral-comparison content hash changed")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("behavioral-comparison content fingerprint mismatch")

    parents = payload.get("frozen_parents")
    if not isinstance(parents, Mapping):
        raise ValueError("frozen parents are required")
    if parents.get("feature_set_id") != FEATURE_SET_ID:
        raise ValueError("feature-set identity changed")
    if parents.get("feature_set_content_sha256") != FEATURE_SET_CONTENT_SHA256:
        raise ValueError("feature-set fingerprint changed")
    if (
        parents.get("four_case_success_audit_content_sha256")
        != FOUR_CASE_SUCCESS_AUDIT_CONTENT_SHA256
    ):
        raise ValueError("four-case success audit changed")
    if parents.get("engineering_feature_values_used_to_select_protocol") is not False:
        raise ValueError("engineering feature values cannot select the protocol")
    if parents.get("retrospective_outcomes_used_to_select_protocol") is not False:
        raise ValueError("outcomes cannot select the protocol")

    paired = payload.get("paired_windows")
    if not isinstance(paired, Mapping):
        raise ValueError("paired-window contract is required")
    if paired.get("horizons_ns") != list(REGISTERED_WINDOWS_NS):
        raise ValueError("all frozen horizons must remain registered")
    if paired.get("overlap_allowed") is not False:
        raise ValueError("pre/post windows must be disjoint")
    if paired.get("all_horizons_reported_together") is not True:
        raise ValueError("all horizons must be reported together")
    if paired.get("best_horizon_selection_allowed") is not False:
        raise ValueError("best-horizon selection is prohibited")

    future = payload.get("future_cohort_gate")
    if not isinstance(future, Mapping):
        raise ValueError("future cohort gate is required")
    if future.get("status") != "not_selected":
        raise ValueError("representative cohort must remain unselected here")
    if future.get("databento_request_count") != 0:
        raise ValueError("registration cannot authorize provider requests")
    if future.get("databento_cost_authorized_usd") != "0":
        raise ValueError("registration cannot authorize provider cost")
    if future.get("databento_bytes_authorized") != 0:
        raise ValueError("registration cannot authorize provider bytes")


def load_and_validate_behavioral_registration(path: Path) -> dict[str, object]:
    payload = _load_json(path)
    validate_behavioral_registration(payload)
    return payload


def _direction(value: int | Fraction) -> str:
    if value > 0:
        return "increase"
    if value < 0:
        return "decrease"
    return "unchanged"


def _path_value(payload: Mapping[str, object], path: Sequence[str]) -> object:
    current: object = payload
    for component in path:
        if not isinstance(current, Mapping) or component not in current:
            return None
        current = current[component]
    return current


def _exact_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _window(snapshot: Mapping[str, object], horizon_ns: int) -> Mapping[str, object]:
    rows = snapshot.get("windows")
    if not isinstance(rows, list):
        raise ValueError("snapshot windows are missing")
    matches = [
        row
        for row in rows
        if isinstance(row, Mapping) and row.get("window_ns") == horizon_ns
    ]
    if len(matches) != 1:
        raise ValueError("snapshot must contain each frozen horizon exactly once")
    return matches[0]


def _validate_snapshot(
    snapshot: Mapping[str, object],
    *,
    expected_scope: Mapping[str, object] | None = None,
) -> Mapping[str, object]:
    claimed = snapshot.get("content_sha256")
    unsigned = {key: value for key, value in snapshot.items() if key != "content_sha256"}
    if not isinstance(claimed, str) or canonical_fingerprint(unsigned) != claimed:
        raise ValueError("feature snapshot fingerprint mismatch")
    if snapshot.get("feature_set_id") != FEATURE_SET_ID:
        raise ValueError("snapshot feature set changed")
    if snapshot.get("registered_windows_ns") != list(REGISTERED_WINDOWS_NS):
        raise ValueError("snapshot horizons changed")
    if snapshot.get("thresholds_applied") is not False:
        raise ValueError("thresholded snapshots are prohibited")
    if snapshot.get("retrospective_labels_loaded") is not False:
        raise ValueError("retrospective labels are prohibited")
    if snapshot.get("runtime_authority") != "none_shadow_only":
        raise ValueError("snapshot cannot carry runtime authority")
    scope = snapshot.get("source_scope")
    if not isinstance(scope, Mapping):
        raise ValueError("source scope is required")
    if scope.get("consolidated_national_depth") is not False:
        raise ValueError("single-venue scope must remain explicit")
    if expected_scope is not None and dict(scope) != dict(expected_scope):
        raise ValueError("paired snapshots must have identical source scope")
    return scope


def _integer_comparison(
    metric_id: str,
    pre_window: Mapping[str, object],
    post_window: Mapping[str, object],
    path: Sequence[str],
    family: str | None,
) -> dict[str, object]:
    for side, window in (("pre", pre_window), ("post", post_window)):
        if family is not None:
            family_payload = window.get(family)
            if not isinstance(family_payload, Mapping) or family_payload.get("available") is not True:
                return {
                    "metric_id": metric_id,
                    "value_type": "integer",
                    "available": False,
                    "unavailable_reason": f"{side}_{family}_unavailable",
                    "direction": "unavailable",
                }
    pre_value = _exact_int(_path_value(pre_window, path))
    post_value = _exact_int(_path_value(post_window, path))
    if pre_value is None or post_value is None:
        return {
            "metric_id": metric_id,
            "value_type": "integer",
            "available": False,
            "unavailable_reason": "non_integer_or_missing_value",
            "direction": "unavailable",
        }
    delta = post_value - pre_value
    return {
        "metric_id": metric_id,
        "value_type": "integer",
        "available": True,
        "unavailable_reason": None,
        "pre_value": pre_value,
        "post_value": post_value,
        "post_minus_pre": delta,
        "direction": _direction(delta),
    }


def _rational_comparison(
    metric_id: str,
    pre_book: Mapping[str, object],
    post_book: Mapping[str, object],
    numerator_path: Sequence[str],
    denominator_path: Sequence[str],
) -> dict[str, object]:
    if pre_book.get("available") is not True or post_book.get("available") is not True:
        return {
            "metric_id": metric_id,
            "value_type": "rational",
            "available": False,
            "unavailable_reason": "book_unavailable",
            "direction": "unavailable",
        }
    pre_num = _exact_int(_path_value(pre_book, numerator_path))
    pre_den = _exact_int(_path_value(pre_book, denominator_path))
    post_num = _exact_int(_path_value(post_book, numerator_path))
    post_den = _exact_int(_path_value(post_book, denominator_path))
    if None in (pre_num, pre_den, post_num, post_den) or pre_den <= 0 or post_den <= 0:
        return {
            "metric_id": metric_id,
            "value_type": "rational",
            "available": False,
            "unavailable_reason": "invalid_rational_components",
            "direction": "unavailable",
        }
    pre = Fraction(pre_num, pre_den)
    post = Fraction(post_num, post_den)
    delta = post - pre
    return {
        "metric_id": metric_id,
        "value_type": "rational",
        "available": True,
        "unavailable_reason": None,
        "pre_numerator": pre_num,
        "pre_denominator": pre_den,
        "post_numerator": post_num,
        "post_denominator": post_den,
        "post_minus_pre_numerator": delta.numerator,
        "post_minus_pre_denominator": delta.denominator,
        "direction": _direction(delta),
    }


def _depth_walk_index(snapshot: Mapping[str, object]) -> dict[tuple[int, str], Mapping[str, object]]:
    rows = snapshot.get("depth_constrained_slippage")
    if not isinstance(rows, list):
        raise ValueError("depth-walk rows are missing")
    result: dict[tuple[int, str], Mapping[str, object]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("invalid depth-walk row")
        quantity = _exact_int(row.get("requested_quantity"))
        direction = row.get("direction")
        if quantity is None or quantity <= 0 or direction not in {"buy", "sell"}:
            raise ValueError("invalid depth-walk identity")
        key = (quantity, str(direction))
        if key in result:
            raise ValueError("duplicate depth-walk identity")
        result[key] = row
    return result


def _depth_walk_comparisons(
    pre_snapshot: Mapping[str, object],
    post_snapshot: Mapping[str, object],
) -> list[dict[str, object]]:
    pre = _depth_walk_index(pre_snapshot)
    post = _depth_walk_index(post_snapshot)
    if set(pre) != set(post):
        raise ValueError("depth-walk quantities and directions must be frozen")
    rows: list[dict[str, object]] = []
    for quantity, direction in sorted(pre):
        before = pre[(quantity, direction)]
        after = post[(quantity, direction)]
        if before.get("available") is not True or after.get("available") is not True:
            rows.append(
                {
                    "requested_quantity": quantity,
                    "direction": direction,
                    "available": False,
                    "unavailable_reason": "pre_or_post_depth_walk_unavailable",
                }
            )
            continue
        fields: list[dict[str, object]] = []
        for field in DEPTH_WALK_FIELDS:
            pre_value = _exact_int(before.get(field))
            post_value = _exact_int(after.get(field))
            if pre_value is None or post_value is None:
                fields.append(
                    {
                        "field": field,
                        "available": False,
                        "unavailable_reason": "non_integer_or_missing_value",
                        "direction": "unavailable",
                    }
                )
                continue
            delta = post_value - pre_value
            fields.append(
                {
                    "field": field,
                    "available": True,
                    "unavailable_reason": None,
                    "pre_value": pre_value,
                    "post_value": post_value,
                    "post_minus_pre": delta,
                    "direction": _direction(delta),
                }
            )
        rows.append(
            {
                "requested_quantity": quantity,
                "direction": direction,
                "available": True,
                "unavailable_reason": None,
                "fields": fields,
                "queue_position_assumed": False,
                "hidden_liquidity_assumed": False,
            }
        )
    return rows


def build_behavioral_comparison(
    *,
    opportunity_id: str,
    anchor_recv_ts_ns: int,
    breakout_level_nanos: int,
    pre_snapshot: Mapping[str, object],
    post_snapshots_by_horizon: Mapping[int, Mapping[str, object]],
) -> dict[str, object]:
    if not opportunity_id or not isinstance(opportunity_id, str):
        raise ValueError("opportunity_id is required")
    if isinstance(anchor_recv_ts_ns, bool) or not isinstance(anchor_recv_ts_ns, int) or anchor_recv_ts_ns <= 0:
        raise ValueError("anchor receive time must be a positive integer")
    if isinstance(breakout_level_nanos, bool) or not isinstance(breakout_level_nanos, int) or breakout_level_nanos <= 0:
        raise ValueError("breakout level must be a positive integer")
    if set(post_snapshots_by_horizon) != set(REGISTERED_WINDOWS_NS):
        raise ValueError("post snapshots must cover every frozen horizon exactly")

    scope = _validate_snapshot(pre_snapshot)
    if pre_snapshot.get("as_of_ts_recv_ns") != anchor_recv_ts_ns:
        raise ValueError("pre snapshot must end at the causal anchor")

    horizons: list[dict[str, object]] = []
    pre_book = pre_snapshot.get("book")
    if not isinstance(pre_book, Mapping):
        raise ValueError("pre snapshot book is missing")
    for horizon_ns in REGISTERED_WINDOWS_NS:
        post_snapshot = post_snapshots_by_horizon[horizon_ns]
        _validate_snapshot(post_snapshot, expected_scope=scope)
        if post_snapshot.get("as_of_ts_recv_ns") != anchor_recv_ts_ns + horizon_ns:
            raise ValueError("post snapshot must end exactly one horizon after anchor")
        pre_window = _window(pre_snapshot, horizon_ns)
        post_window = _window(post_snapshot, horizon_ns)
        if pre_window.get("start_exclusive_ts_recv_ns") != anchor_recv_ts_ns - horizon_ns:
            raise ValueError("pre window start changed")
        if pre_window.get("end_inclusive_ts_recv_ns") != anchor_recv_ts_ns:
            raise ValueError("pre window must end at anchor")
        if post_window.get("start_exclusive_ts_recv_ns") != anchor_recv_ts_ns:
            raise ValueError("post window must start exclusively at anchor")
        if post_window.get("end_inclusive_ts_recv_ns") != anchor_recv_ts_ns + horizon_ns:
            raise ValueError("post window end changed")
        for window in (pre_window, post_window):
            breakout = window.get("breakout_progress_context")
            if isinstance(breakout, Mapping) and breakout.get("available") is True:
                if breakout.get("breakout_level_nanos") != breakout_level_nanos:
                    raise ValueError("breakout level changed inside paired window")

        post_book = post_snapshot.get("book")
        if not isinstance(post_book, Mapping):
            raise ValueError("post snapshot book is missing")
        metrics = [
            _rational_comparison(metric_id, pre_book, post_book, num, den)
            for metric_id, num, den in RATIONAL_METRICS
        ]
        metrics.extend(
            _integer_comparison(metric_id, pre_window, post_window, path, family)
            for metric_id, path, family in INTEGER_METRICS
        )
        horizons.append(
            {
                "horizon_ns": horizon_ns,
                "pre_interval": {
                    "start_exclusive_ts_recv_ns": anchor_recv_ts_ns - horizon_ns,
                    "end_inclusive_ts_recv_ns": anchor_recv_ts_ns,
                },
                "post_interval": {
                    "start_exclusive_ts_recv_ns": anchor_recv_ts_ns,
                    "end_inclusive_ts_recv_ns": anchor_recv_ts_ns + horizon_ns,
                },
                "metrics": metrics,
                "depth_walk": _depth_walk_comparisons(pre_snapshot, post_snapshot),
            }
        )

    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "opportunity_id": opportunity_id,
        "anchor_recv_ts_ns": anchor_recv_ts_ns,
        "breakout_level_nanos": breakout_level_nanos,
        "source_scope": dict(scope),
        "horizons": horizons,
        "all_horizons_reported_together": True,
        "thresholds_applied": False,
        "retrospective_labels_loaded": False,
        "confirmation_or_adverse_classification": None,
        "hidden_buyer_or_seller_classification": None,
        "runtime_authority": "none_shadow_only",
        "provider_request_made": False,
    }
    payload["content_sha256"] = canonical_fingerprint(payload)
    return payload
