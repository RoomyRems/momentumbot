from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Mapping


SCHEMA_VERSION = 1
CONTRACT_ID = "catalyst-timing-shadow-v0.1"
SOURCE_SCANNER_ARTIFACT_ID = "causal-scanner-snapshot-v0.1"
SOURCE_SCANNER_POLICY_FINGERPRINT = (
    "ed21becad10855b4a085b6e05b6feac8f21e4ce511a100b2381522154818f42a"
)

FEATURE_NAMES = (
    "provider_news_state",
    "provider_news_present_at_activation",
    "provider_news_event_count_as_of",
    "provider_news_event_count_change_from_prior_minute",
    "new_provider_news_became_available_this_minute",
    "provider_news_state_changed_from_prior_minute",
    "observed_provider_news_state_tenure_minutes",
    "first_provider_news_published_at_as_of",
    "latest_provider_news_published_at_as_of",
    "seconds_since_first_provider_news",
    "seconds_since_latest_provider_news",
    "seconds_from_activation_to_first_provider_news",
    "candidate_qualified_before_first_provider_news",
)


def validate_catalyst_timing_contract(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported catalyst-timing schema")
    if payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected catalyst-timing contract ID")
    if payload.get("artifact_type") != "causal_shadow_feature_contract":
        raise ValueError("unexpected catalyst-timing artifact type")
    if payload.get("runtime_strategy_effect") != "none":
        raise ValueError("catalyst timing must remain shadow-only")
    for field in (
        "catalyst_quality_score_frozen",
        "selection_threshold_frozen",
        "order_authority",
        "risk_authority",
        "policy_promotion_eligible",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must be false")

    source = payload.get("source_scanner")
    if not isinstance(source, Mapping):
        raise ValueError("source_scanner must be an object")
    if source.get("artifact_id") != SOURCE_SCANNER_ARTIFACT_ID:
        raise ValueError("unexpected source scanner artifact")
    if source.get("policy_fingerprint") != SOURCE_SCANNER_POLICY_FINGERPRINT:
        raise ValueError("unexpected source scanner policy fingerprint")

    knowledge = payload.get("knowledge_policy")
    if not isinstance(knowledge, Mapping):
        raise ValueError("knowledge_policy must be an object")
    guards = {
        "published_at_must_be_lte_decision_time": True,
        "uses_only_current_or_prior_decision_rows": True,
        "future_news_allowed": False,
        "retrospective_trade_labels_allowed": False,
        "provider_relative_no_news_treated_as_universal_no_news": False,
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
            raise ValueError("each catalyst timing feature requires a meaning")
        if row.get("strategy_gate_enabled") is not False:
            raise ValueError("catalyst timing features cannot be strategy gates")
    if not str(payload.get("interpretation_limit", "")).strip():
        raise ValueError("interpretation_limit is required")


def load_catalyst_timing_contract(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("catalyst-timing contract root must be an object")
    validate_catalyst_timing_contract(payload)
    return payload


def _timestamp(value: object, field: str, *, nullable: bool = False) -> datetime | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed


def _normalized_row(source: Mapping[str, object]) -> dict[str, object]:
    row = dict(source)
    symbol = str(row.get("symbol", "")).strip().upper()
    if not symbol:
        raise ValueError("scanner row symbol is required")
    decision = _timestamp(row.get("decision_time"), "decision_time")
    activation = _timestamp(row.get("activation_time"), "activation_time")
    assert decision is not None and activation is not None
    if decision < activation:
        raise ValueError("decision_time cannot precede activation_time")

    status = str(row.get("news_provider_status", "")).strip()
    if not status:
        raise ValueError("news_provider_status is required")
    has_news = row.get("has_provider_news_as_of")
    no_news = row.get("provider_relative_no_news_as_of")
    if not isinstance(has_news, bool) or not isinstance(no_news, bool):
        raise ValueError("provider news flags must be boolean")
    count = row.get("provider_news_event_count_as_of")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("provider news event count must be a nonnegative integer")
    first = _timestamp(
        row.get("first_provider_news_published_at_as_of"),
        "first_provider_news_published_at_as_of",
        nullable=True,
    )
    latest = _timestamp(
        row.get("latest_provider_news_published_at_as_of"),
        "latest_provider_news_published_at_as_of",
        nullable=True,
    )

    if status == "success" and count > 0:
        if not has_news or no_news or first is None or latest is None:
            raise ValueError("successful news-present state is contradictory")
        if first > latest or latest > decision:
            raise ValueError("provider news publications must be ordered and causal")
        state = "present"
    elif status == "success" and count == 0:
        if has_news or not no_news or first is not None or latest is not None:
            raise ValueError("successful provider-relative no-news state is contradictory")
        state = "provider_relative_none"
    else:
        if count != 0 or has_news or no_news or first is not None or latest is not None:
            raise ValueError("provider-error news state must fail closed")
        state = "unknown_fail_closed"

    row.update(
        {
            "symbol": symbol,
            "_decision": decision,
            "_activation": activation,
            "_state": state,
            "_count": count,
            "_first": first,
            "_latest": latest,
        }
    )
    return row


def derive_catalyst_timing_rows(
    rows: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Derive provider-news chronology without interpreting catalyst quality."""

    normalized = [_normalized_row(row) for row in rows]
    if not normalized:
        raise ValueError("at least one scanner row is required")
    normalized.sort(key=lambda row: (row["symbol"], row["_decision"]))
    seen: set[tuple[str, datetime]] = set()
    result: list[dict[str, object]] = []
    prior_by_symbol: dict[str, dict[str, object]] = {}
    activation_state_by_symbol: dict[str, bool | None] = {}

    for row in normalized:
        symbol = str(row["symbol"])
        decision = row["_decision"]
        activation = row["_activation"]
        assert isinstance(decision, datetime) and isinstance(activation, datetime)
        key = (symbol, decision)
        if key in seen:
            raise ValueError("duplicate scanner symbol/decision row")
        seen.add(key)

        prior = prior_by_symbol.get(symbol)
        if prior is None:
            if decision != activation:
                raise ValueError("first candidate row must occur at activation_time")
            activation_state_by_symbol[symbol] = (
                True if row["_state"] == "present" else False
                if row["_state"] == "provider_relative_none" else None
            )
        elif row["_activation"] != prior["_activation"]:
            raise ValueError("candidate activation_time changed within the series")

        consecutive = (
            prior is not None
            and isinstance(prior["_decision"], datetime)
            and decision - prior["_decision"] == timedelta(minutes=1)
        )
        if consecutive:
            count_change = int(row["_count"]) - int(prior["_count"])
            if count_change < 0:
                raise ValueError("provider news event count cannot decrease")
            new_news = count_change > 0
            state_changed = row["_state"] != prior["_state"]
            state_tenure = int(prior["_state_tenure"]) + 1 if not state_changed else 1
        else:
            count_change = None
            new_news = None
            state_changed = None
            state_tenure = 1

        first = row["_first"]
        latest = row["_latest"]
        seconds_since_first = None if first is None else (decision - first).total_seconds()
        seconds_since_latest = None if latest is None else (decision - latest).total_seconds()
        activation_to_first = None if first is None else (first - activation).total_seconds()
        qualified_before_first = None if first is None else activation < first

        result.append(
            {
                "symbol": symbol,
                "activation_time": row["activation_time"],
                "decision_time": row["decision_time"],
                "news_provider_status": row["news_provider_status"],
                "provider_news_state": row["_state"],
                "provider_news_present_at_activation": activation_state_by_symbol[symbol],
                "provider_news_event_count_as_of": row["_count"],
                "provider_news_event_count_change_from_prior_minute": count_change,
                "new_provider_news_became_available_this_minute": new_news,
                "provider_news_state_changed_from_prior_minute": state_changed,
                "observed_provider_news_state_tenure_minutes": state_tenure,
                "first_provider_news_published_at_as_of": row[
                    "first_provider_news_published_at_as_of"
                ],
                "latest_provider_news_published_at_as_of": row[
                    "latest_provider_news_published_at_as_of"
                ],
                "seconds_since_first_provider_news": seconds_since_first,
                "seconds_since_latest_provider_news": seconds_since_latest,
                "seconds_from_activation_to_first_provider_news": activation_to_first,
                "candidate_qualified_before_first_provider_news": qualified_before_first,
            }
        )
        prior_by_symbol[symbol] = {
            "_decision": decision,
            "_activation": activation,
            "_state": row["_state"],
            "_count": row["_count"],
            "_state_tenure": state_tenure,
        }

    return sorted(result, key=lambda row: (row["decision_time"], row["symbol"]))
