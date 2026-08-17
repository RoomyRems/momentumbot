from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Mapping


SCHEMA_VERSION = 1
CONTRACT_ID = "attention-leadership-shadow-v0.1"
SOURCE_SCANNER_ARTIFACT_ID = "causal-scanner-snapshot-v0.1"
SOURCE_SCANNER_POLICY_FINGERPRINT = (
    "ed21becad10855b4a085b6e05b6feac8f21e4ce511a100b2381522154818f42a"
)

FEATURE_NAMES = (
    "active_market_candidate_count",
    "active_candidates_with_better_market_rank",
    "market_leader_symbol",
    "market_leader_percent_gain",
    "prior_observed_market_leader_symbol",
    "market_leader_changed_from_prior_minute",
    "observed_market_leader_tenure_minutes",
    "candidate_top_gainer_rank",
    "candidate_is_market_leader",
    "candidate_became_market_leader_this_minute",
    "candidate_consecutive_market_leader_minutes",
    "candidate_rank_improvement_from_prior_minute",
    "candidate_percent_gain",
    "candidate_gain_change_pct_points_from_prior_minute",
    "candidate_gap_to_leader_pct_points",
    "candidate_gap_change_pct_points_from_prior_minute",
    "candidate_cumulative_volume",
    "candidate_volume_change_from_prior_minute",
    "minutes_since_candidate_activation",
)


def validate_attention_leadership_contract(payload: Mapping[str, object]) -> None:
    """Validate the feature contract without authorizing a trading decision."""

    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported attention-leadership schema")
    if payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected attention-leadership contract ID")
    if payload.get("artifact_type") != "causal_shadow_feature_contract":
        raise ValueError("unexpected attention-leadership artifact type")
    if payload.get("runtime_strategy_effect") != "none":
        raise ValueError("attention features must remain shadow-only")
    if payload.get("selection_threshold_frozen") is not False:
        raise ValueError("no attention selection threshold is frozen")
    if payload.get("order_authority") is not False:
        raise ValueError("attention features cannot submit orders")
    if payload.get("risk_authority") is not False:
        raise ValueError("attention features cannot alter risk")
    if payload.get("policy_promotion_eligible") is not False:
        raise ValueError("the shadow feature contract is not promotion eligible")

    source = payload.get("source_scanner")
    if not isinstance(source, Mapping):
        raise ValueError("source_scanner must be an object")
    if source.get("artifact_id") != SOURCE_SCANNER_ARTIFACT_ID:
        raise ValueError("unexpected source scanner artifact")
    if source.get("policy_fingerprint") != SOURCE_SCANNER_POLICY_FINGERPRINT:
        raise ValueError("unexpected source scanner policy fingerprint")
    if source.get("schema_version") != 1:
        raise ValueError("unexpected source scanner schema")

    knowledge = payload.get("knowledge_policy")
    if not isinstance(knowledge, Mapping):
        raise ValueError("knowledge_policy must be an object")
    guards = {
        "uses_only_current_or_prior_decision_rows": True,
        "later_candidate_activation_may_change_prior_features": False,
        "retrospective_trade_labels_allowed": False,
        "future_price_or_volume_allowed": False,
        "missing_minutes_backfilled": False,
    }
    for field, expected in guards.items():
        if knowledge.get(field) is not expected:
            raise ValueError(f"knowledge_policy.{field} must be {expected}")

    definitions = payload.get("feature_definitions")
    if not isinstance(definitions, list):
        raise ValueError("feature_definitions must be a list")
    names = [str(row.get("name", "")) for row in definitions if isinstance(row, Mapping)]
    if tuple(names) != FEATURE_NAMES:
        raise ValueError("feature definitions must match the frozen ordered feature list")
    for row in definitions:
        assert isinstance(row, Mapping)
        if not str(row.get("meaning", "")).strip():
            raise ValueError("each attention feature requires a meaning")
        if row.get("strategy_gate_enabled") is not False:
            raise ValueError("attention features cannot be strategy gates")

    if not str(payload.get("interpretation_limit", "")).strip():
        raise ValueError("interpretation_limit is required")


def load_attention_leadership_contract(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("attention-leadership contract root must be an object")
    validate_attention_leadership_contract(payload)
    return payload


def _timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    if parsed.second or parsed.microsecond:
        raise ValueError(f"{field} must be minute-aligned")
    return parsed


def _finite_number(value: object, field: str, *, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _rank(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("top_gainer_rank must be a positive integer or null")
    return value


def _volume(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("cumulative_volume must be a nonnegative integer or null")
    return value


def _normalized_source_rows(rows: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    seen: set[tuple[datetime, str]] = set()
    for source in rows:
        row = dict(source)
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            raise ValueError("scanner row symbol is required")
        decision = _timestamp(row.get("decision_time"), "decision_time")
        activation = _timestamp(row.get("activation_time"), "activation_time")
        if decision < activation:
            raise ValueError("decision_time cannot precede activation_time")
        if (decision - activation) % timedelta(minutes=1):
            raise ValueError("activation and decision times must share the minute grid")

        key = (decision, symbol)
        if key in seen:
            raise ValueError("duplicate scanner symbol/decision row")
        seen.add(key)

        completed = row.get("candidate_completed_bar_present")
        if not isinstance(completed, bool):
            raise ValueError("candidate_completed_bar_present must be boolean")
        gain = _finite_number(row.get("percent_gain"), "percent_gain", nullable=True)
        volume = _volume(row.get("cumulative_volume"))
        if not completed and (gain is not None or volume is not None):
            raise ValueError("missing exact candidate bars must have null gain and volume")
        if completed and (gain is None or volume is None):
            raise ValueError("completed candidate bars require gain and volume")

        rank = _rank(row.get("top_gainer_rank"))
        leader_symbol_raw = row.get("rank_leader_symbol")
        leader_symbol = None if leader_symbol_raw is None else str(leader_symbol_raw).strip().upper()
        if leader_symbol_raw is not None and not leader_symbol:
            raise ValueError("rank_leader_symbol cannot be empty")
        leader_gain = _finite_number(
            row.get("rank_leader_percent_gain"),
            "rank_leader_percent_gain",
            nullable=True,
        )
        if (leader_symbol is None) != (leader_gain is None):
            raise ValueError("leader symbol and gain must be jointly present or null")
        if rank == 1 and leader_symbol != symbol:
            raise ValueError("rank-one candidate must agree with the market leader")
        if rank == 1 and gain is not None and not math.isclose(gain, leader_gain, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("rank-one completed candidate gain must agree with leader gain")

        rank_hash = str(row.get("rank_input_ordered_sha256", ""))
        if len(rank_hash) != 64 or any(ch not in "0123456789abcdef" for ch in rank_hash):
            raise ValueError("rank_input_ordered_sha256 must be lowercase SHA-256")
        if not isinstance(row.get("rank_input_complete_for_members_with_completed_bars"), bool):
            raise ValueError("rank input completeness must be boolean")
        identity_count = row.get("identity_resolved_member_count")
        computable_count = row.get("rank_members_with_computable_gain_count")
        if (
            isinstance(identity_count, bool)
            or not isinstance(identity_count, int)
            or identity_count < 1
            or isinstance(computable_count, bool)
            or not isinstance(computable_count, int)
            or not 0 <= computable_count <= identity_count
        ):
            raise ValueError("rank coverage counts are invalid")

        row.update(
            {
                "symbol": symbol,
                "_decision": decision,
                "_activation": activation,
                "_rank": rank,
                "_gain": gain,
                "_volume": volume,
                "_leader_symbol": leader_symbol,
                "_leader_gain": leader_gain,
            }
        )
        normalized.append(row)
    if not normalized:
        raise ValueError("at least one scanner row is required")
    return sorted(normalized, key=lambda row: (row["_decision"], row["symbol"]))


def derive_attention_leadership_rows(
    rows: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Derive causal, threshold-free attention proxies from scanner rows.

    Rows are grouped by decision minute. Every transition uses only the current
    minute and the immediately preceding observed minute. A gap resets deltas
    and tenure instead of silently carrying information across missing input.
    """

    source_rows = _normalized_source_rows(rows)
    grouped: dict[datetime, list[dict[str, object]]] = {}
    for row in source_rows:
        grouped.setdefault(row["_decision"], []).append(row)  # type: ignore[arg-type]

    result: list[dict[str, object]] = []
    prior_decision: datetime | None = None
    prior_leader: str | None = None
    leader_tenure: int | None = None
    prior_by_symbol: dict[str, dict[str, object]] = {}

    for decision, group in sorted(grouped.items()):
        common_fields = (
            "_leader_symbol",
            "_leader_gain",
            "rank_input_ordered_sha256",
            "rank_input_complete_for_members_with_completed_bars",
            "identity_resolved_member_count",
            "rank_members_with_computable_gain_count",
        )
        for field in common_fields:
            if any(row[field] != group[0][field] for row in group[1:]):
                raise ValueError(f"scanner rows disagree within a decision minute: {field}")

        leader = group[0]["_leader_symbol"]
        leader_gain = group[0]["_leader_gain"]
        consecutive_global = prior_decision is not None and decision - prior_decision == timedelta(minutes=1)
        prior_observed_leader = prior_leader if consecutive_global else None
        if leader is None:
            leader_changed = None
            leader_tenure = None
        elif consecutive_global and prior_leader is not None:
            leader_changed = leader != prior_leader
            leader_tenure = (leader_tenure or 0) + 1 if not leader_changed else 1
        else:
            leader_changed = None
            leader_tenure = 1

        numeric_ranks = [row["_rank"] for row in group if row["_rank"] is not None]
        for row in group:
            symbol = str(row["symbol"])
            rank = row["_rank"]
            gain = row["_gain"]
            volume = row["_volume"]
            activation = row["_activation"]
            candidate_is_leader = None if rank is None or leader is None else rank == 1 and leader == symbol
            gap = None if gain is None or leader_gain is None else float(leader_gain) - float(gain)
            if rank == 1 and gap is not None and math.isclose(gap, 0.0, abs_tol=1e-12):
                gap = 0.0

            prior = prior_by_symbol.get(symbol)
            consecutive_candidate = (
                prior is not None
                and isinstance(prior.get("_decision"), datetime)
                and decision - prior["_decision"] == timedelta(minutes=1)  # type: ignore[operator]
            )
            rank_improvement = None
            gain_change = None
            volume_change = None
            gap_change = None
            prior_consecutive_leader = 0
            if consecutive_candidate:
                prior_rank = prior["_rank"]
                prior_gain = prior["_gain"]
                prior_volume = prior["_volume"]
                prior_gap = prior["_gap"]
                if rank is not None and prior_rank is not None:
                    rank_improvement = int(prior_rank) - int(rank)
                if gain is not None and prior_gain is not None:
                    gain_change = float(gain) - float(prior_gain)
                if volume is not None and prior_volume is not None:
                    volume_change = int(volume) - int(prior_volume)
                    if volume_change < 0:
                        raise ValueError("candidate cumulative volume cannot decrease")
                if gap is not None and prior_gap is not None:
                    gap_change = float(gap) - float(prior_gap)
                if prior["_is_leader"] is True:
                    prior_consecutive_leader = int(prior["_consecutive_leader"])

            if candidate_is_leader is None:
                consecutive_leader: int | None = None
                became_leader: bool | None = None
            elif candidate_is_leader:
                consecutive_leader = prior_consecutive_leader + 1
                became_leader = (
                    None
                    if not consecutive_global or prior_leader is None
                    else prior_leader != symbol
                )
            else:
                consecutive_leader = 0
                became_leader = False if consecutive_global and prior_leader is not None else None

            better_count = None if rank is None else sum(int(item) < int(rank) for item in numeric_ranks)
            minutes_since_activation = int((decision - activation).total_seconds() // 60)  # type: ignore[operator]
            derived = {
                "symbol": symbol,
                "activation_time": row["activation_time"],
                "decision_time": row["decision_time"],
                "source_rank_input_ordered_sha256": row["rank_input_ordered_sha256"],
                "rank_input_complete_for_members_with_completed_bars": row[
                    "rank_input_complete_for_members_with_completed_bars"
                ],
                "identity_resolved_member_count": row["identity_resolved_member_count"],
                "rank_members_with_computable_gain_count": row[
                    "rank_members_with_computable_gain_count"
                ],
                "candidate_completed_bar_present": row["candidate_completed_bar_present"],
                "active_market_candidate_count": len(group),
                "active_candidates_with_better_market_rank": better_count,
                "market_leader_symbol": leader,
                "market_leader_percent_gain": leader_gain,
                "prior_observed_market_leader_symbol": prior_observed_leader,
                "market_leader_changed_from_prior_minute": leader_changed,
                "observed_market_leader_tenure_minutes": leader_tenure,
                "candidate_top_gainer_rank": rank,
                "candidate_is_market_leader": candidate_is_leader,
                "candidate_became_market_leader_this_minute": became_leader,
                "candidate_consecutive_market_leader_minutes": consecutive_leader,
                "candidate_rank_improvement_from_prior_minute": rank_improvement,
                "candidate_percent_gain": gain,
                "candidate_gain_change_pct_points_from_prior_minute": gain_change,
                "candidate_gap_to_leader_pct_points": gap,
                "candidate_gap_change_pct_points_from_prior_minute": gap_change,
                "candidate_cumulative_volume": volume,
                "candidate_volume_change_from_prior_minute": volume_change,
                "minutes_since_candidate_activation": minutes_since_activation,
            }
            result.append(derived)
            prior_by_symbol[symbol] = {
                "_decision": decision,
                "_rank": rank,
                "_gain": gain,
                "_volume": volume,
                "_gap": gap,
                "_is_leader": candidate_is_leader,
                "_consecutive_leader": consecutive_leader,
            }

        prior_decision = decision
        prior_leader = leader  # type: ignore[assignment]

    return result
