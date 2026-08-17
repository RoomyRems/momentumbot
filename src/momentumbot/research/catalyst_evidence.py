from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

from momentumbot.research.catalyst_timing import derive_catalyst_timing_rows


SCHEMA_VERSION = 1
CONTRACT_ID = "catalyst-evidence-packet-shadow-v0.1"
SOURCE_SCANNER_POLICY_FINGERPRINT = (
    "ed21becad10855b4a085b6e05b6feac8f21e4ce511a100b2381522154818f42a"
)
PACKET_FIELDS = (
    "symbol",
    "activation_time",
    "decision_time",
    "packet_reason",
    "news_provider_status",
    "provider_relative_no_news_as_of",
    "provider_news_event_count_as_of",
    "new_headline_ids",
    "events",
    "packet_content_sha256",
)
EVENT_FIELDS = (
    "headline_id",
    "published_at",
    "seconds_old_at_decision",
    "availability_basis",
    "provider",
    "provider_story_id",
    "source",
    "title",
    "provider_symbols",
    "provider_symbol_count",
    "single_symbol_story",
)


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_catalyst_evidence_contract(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported catalyst-evidence schema")
    if payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected catalyst-evidence contract ID")
    if payload.get("artifact_type") != "causal_shadow_evidence_packet_contract":
        raise ValueError("unexpected catalyst-evidence artifact type")
    if payload.get("runtime_strategy_effect") != "none":
        raise ValueError("catalyst evidence packets must remain shadow-only")
    for field in (
        "semantic_classification_frozen",
        "selection_threshold_frozen",
        "ai_order_authority",
        "ai_risk_authority",
        "policy_promotion_eligible",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must be false")

    sources = payload.get("source_contracts")
    if not isinstance(sources, Mapping):
        raise ValueError("source_contracts must be an object")
    scanner = sources.get("scanner")
    news = sources.get("news")
    if not isinstance(scanner, Mapping) or not isinstance(news, Mapping):
        raise ValueError("scanner and news source contracts are required")
    if scanner.get("policy_fingerprint") != SOURCE_SCANNER_POLICY_FINGERPRINT:
        raise ValueError("unexpected scanner policy fingerprint")
    if news.get("policy_id") != "causal-alpaca-news-v0.2":
        raise ValueError("unexpected news source policy")

    knowledge = payload.get("knowledge_policy")
    if not isinstance(knowledge, Mapping):
        raise ValueError("knowledge_policy must be an object")
    guards = {
        "projects_full_tape_by_published_at_lte_decision_time": True,
        "future_events_exposed": False,
        "retrospective_trade_labels_allowed": False,
        "provider_relative_no_news_treated_as_universal_no_news": False,
        "headline_text_may_submit_orders": False,
    }
    for field, expected in guards.items():
        if knowledge.get(field) is not expected:
            raise ValueError(f"knowledge_policy.{field} must be {expected}")

    fields = payload.get("packet_fields")
    if not isinstance(fields, list) or tuple(fields) != PACKET_FIELDS:
        raise ValueError("packet_fields must match the frozen ordered packet contract")
    event_fields = payload.get("event_fields")
    if not isinstance(event_fields, list) or tuple(event_fields) != EVENT_FIELDS:
        raise ValueError("event_fields must match the frozen ordered event contract")
    if not str(payload.get("interpretation_limit", "")).strip():
        raise ValueError("interpretation_limit is required")


def load_catalyst_evidence_contract(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("catalyst-evidence contract root must be an object")
    validate_catalyst_evidence_contract(payload)
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
    return parsed


def _events(news_payload: Mapping[str, object]) -> dict[str, list[dict[str, object]]]:
    tape = news_payload.get("full_window_event_tape")
    if not isinstance(tape, list):
        raise ValueError("full_window_event_tape must be a list")
    by_symbol: dict[str, list[dict[str, object]]] = {}
    seen: set[tuple[str, str]] = set()
    for source in tape:
        if not isinstance(source, Mapping):
            raise ValueError("news tape rows must be objects")
        row = dict(source)
        symbol = str(row.get("symbol", "")).strip().upper()
        headline_id = str(row.get("headline_id", "")).strip()
        title = str(row.get("title", "")).strip()
        if not symbol or not headline_id or not title:
            raise ValueError("news rows require symbol, headline_id and title")
        if (symbol, headline_id) in seen:
            raise ValueError("duplicate symbol/headline_id news row")
        seen.add((symbol, headline_id))
        published = _timestamp(row.get("published_at"), "published_at")
        provider_symbols_raw = row.get("provider_symbols")
        if not isinstance(provider_symbols_raw, list) or not provider_symbols_raw:
            raise ValueError("provider_symbols must be a nonempty list")
        provider_symbols = [str(item).strip().upper() for item in provider_symbols_raw]
        if len(provider_symbols) != len(set(provider_symbols)) or symbol not in provider_symbols:
            raise ValueError("provider_symbols must be unique and include the candidate")
        for field in ("provider", "provider_story_id", "source", "availability_basis"):
            if not str(row.get(field, "")).strip():
                raise ValueError(f"news row requires {field}")
        by_symbol.setdefault(symbol, []).append(
            {
                "headline_id": headline_id,
                "published_at": row["published_at"],
                "_published": published,
                "availability_basis": row["availability_basis"],
                "provider": row["provider"],
                "provider_story_id": str(row["provider_story_id"]),
                "source": row["source"],
                "title": title,
                "provider_symbols": provider_symbols,
            }
        )
    for rows in by_symbol.values():
        rows.sort(key=lambda row: (row["_published"], row["headline_id"]))
    return by_symbol


def build_catalyst_evidence_packets(
    scanner_rows: Iterable[Mapping[str, object]],
    news_payload: Mapping[str, object],
) -> list[dict[str, object]]:
    """Build activation/change packets with a strict causal projection of the news tape."""

    timing_rows = derive_catalyst_timing_rows(scanner_rows)
    events_by_symbol = _events(news_payload)
    prior_ids: dict[str, tuple[str, ...]] = {}
    packets: list[dict[str, object]] = []

    for row in timing_rows:
        symbol = str(row["symbol"])
        decision = _timestamp(row["decision_time"], "decision_time")
        available = [
            event
            for event in events_by_symbol.get(symbol, [])
            if event["_published"] <= decision
        ]
        ids = tuple(str(event["headline_id"]) for event in available)
        expected_count = int(row["provider_news_event_count_as_of"])
        if row["news_provider_status"] == "success" and len(ids) != expected_count:
            raise ValueError("scanner/news event-count lineage mismatch")
        if row["news_provider_status"] != "success" and ids:
            raise ValueError("provider-error scanner row cannot expose news events")

        if available:
            if row["first_provider_news_published_at_as_of"] != available[0]["published_at"]:
                raise ValueError("scanner/news first-publication lineage mismatch")
            if row["latest_provider_news_published_at_as_of"] != available[-1]["published_at"]:
                raise ValueError("scanner/news latest-publication lineage mismatch")

        previous = prior_ids.get(symbol)
        if previous is not None and not set(previous).issubset(ids):
            raise ValueError("causal provider event set cannot lose an event")
        if previous == ids:
            continue
        reason = "candidate_activation" if previous is None else "provider_event_set_changed"
        previous_set = set(previous or ())
        event_rows = [
            {
                "headline_id": event["headline_id"],
                "published_at": event["published_at"],
                "seconds_old_at_decision": (decision - event["_published"]).total_seconds(),
                "availability_basis": event["availability_basis"],
                "provider": event["provider"],
                "provider_story_id": event["provider_story_id"],
                "source": event["source"],
                "title": event["title"],
                "provider_symbols": event["provider_symbols"],
                "provider_symbol_count": len(event["provider_symbols"]),
                "single_symbol_story": len(event["provider_symbols"]) == 1,
            }
            for event in available
        ]
        packet = {
            "symbol": symbol,
            "activation_time": row["activation_time"],
            "decision_time": row["decision_time"],
            "packet_reason": reason,
            "news_provider_status": row["news_provider_status"],
            "provider_relative_no_news_as_of": row["provider_news_state"]
            == "provider_relative_none",
            "provider_news_event_count_as_of": expected_count,
            "new_headline_ids": [item for item in ids if item not in previous_set],
            "events": event_rows,
        }
        packet["packet_content_sha256"] = _fingerprint(packet)
        packets.append(packet)
        prior_ids[symbol] = ids

    return sorted(packets, key=lambda row: (row["decision_time"], row["symbol"]))
