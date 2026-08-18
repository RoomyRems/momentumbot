from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Mapping
from zoneinfo import ZoneInfo

from momentumbot.causal_scanner_snapshot import SNAPSHOT_ROW_FIELDS


SCHEMA_VERSION = 1
CONTRACT_ID = "theme-regime-context-shadow-v0.1"
RECORD_TYPE = "causal_theme_regime_evidence"
SESSION_SUMMARY_RECORD_TYPE = "completed_theme_regime_session_summary"
SESSION_TIMEZONE = "America/New_York"
PRIOR_COMPLETED_SESSION_LOOKBACK = 5

SCANNER_CONTRACT_ID = "causal-scanner-snapshot-v0.1"
SCANNER_POLICY_FINGERPRINT = (
    "ed21becad10855b4a085b6e05b6feac8f21e4ce511a100b2381522154818f42a"
)
NEWS_CONTRACT_ID = "causal-alpaca-news-v0.2"
CONTEXT_ASSESSMENT_CONTRACT_ID = "discretion-context-assessment-shadow-v0.1"
CONTEXT_HELDOUT_PANEL_ID = "ross-context-heldout-panel-v0.1"
CONTEXT_HELDOUT_PANEL_CONTENT_SHA256 = (
    "d227792368b3bff5c3c2365cacd204c11b7991daeb557efba450c22f076d8898"
)

SOURCE_ARTIFACT_KEYS = (
    "scanner_records",
    "publication_timed_news_events",
    "prior_session_summaries",
)
PROHIBITED_OUTPUT_FIELDS = (
    "hot_cold_regime_label",
    "theme_fit_classification",
    "no_news_acceptance_classification",
    "aggregate_context_score",
    "candidate_priority",
    "selection_action",
    "trade_recommendation",
    "order_action",
    "position_size",
    "risk_action",
)

_ET = ZoneInfo(SESSION_TIMEZONE)
_LOWER_HEX = frozenset("0123456789abcdef")
_PROHIBITED_OUTPUTS = {field: None for field in PROHIBITED_OUTPUT_FIELDS}


def canonical_fingerprint(payload: object) -> str:
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("payload must be canonical finite JSON data") from exc
    return hashlib.sha256(encoded).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _LOWER_HEX for character in value)
    )


def _timestamp(value: object, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO timestamp") from exc
    else:
        raise ValueError(f"{field} must be an ISO timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed


def _date(value: object, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO date") from exc
    raise ValueError(f"{field} must be an ISO date")


def _require_exact_keys(
    payload: Mapping[str, object], expected: Iterable[str], field: str
) -> None:
    expected_set = set(expected)
    actual = set(payload)
    if actual != expected_set:
        missing = sorted(expected_set - actual)
        extra = sorted(actual - expected_set)
        raise ValueError(f"{field} fields differ; missing={missing}, extra={extra}")


def validate_theme_regime_context_contract(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported theme/regime context schema")
    if payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected theme/regime context contract ID")
    if payload.get("artifact_type") != "causal_theme_regime_evidence_contract":
        raise ValueError("unexpected theme/regime context artifact type")
    if payload.get("status") != "frozen_schema_builder_no_heldout_runtime_artifact":
        raise ValueError("unexpected theme/regime context status")
    if payload.get("runtime_strategy_effect") != "none":
        raise ValueError("theme/regime context must remain shadow-only")
    for field in (
        "policy_promotion_eligible",
        "ai_order_authority",
        "ai_risk_authority",
        "hot_cold_threshold_frozen",
        "theme_fit_rule_frozen",
        "no_news_acceptance_threshold_frozen",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must be false")

    sources = payload.get("source_contracts")
    expected_sources = {
        "scanner": {
            "contract_id": SCANNER_CONTRACT_ID,
            "policy_fingerprint": SCANNER_POLICY_FINGERPRINT,
        },
        "publication_timed_news": {"contract_id": NEWS_CONTRACT_ID},
    }
    if sources != expected_sources:
        raise ValueError("theme/regime sources differ from the frozen contract")

    protocol = payload.get("feature_protocol")
    if not isinstance(protocol, Mapping):
        raise ValueError("feature_protocol must be an object")
    if protocol.get("current_session_observation_clock") != (
        "exact_candidate_decision_minute"
    ):
        raise ValueError("theme/regime observation clock differs from the contract")
    if protocol.get("prior_completed_session_lookback") != (
        PRIOR_COMPLETED_SESSION_LOOKBACK
    ):
        raise ValueError("theme/regime prior-session lookback differs")
    if protocol.get("current_session_fields") != [
        "same_minute_ranked_candidate_cohort",
        "candidate_activation_chronology_as_of_decision",
        "provider_news_no_news_and_error_counts",
        "available_provider_headline_story_universe",
        "cross_candidate_story_associations",
    ]:
        raise ValueError("current-session theme/regime fields differ")
    if protocol.get("prior_session_fields") != [
        "candidate_count",
        "activation_chronology",
        "final_provider_news_no_news_and_error_counts",
        "final_rank_leader",
    ]:
        raise ValueError("prior-session theme/regime fields differ")
    for field in (
        "hot_cold_threshold",
        "theme_fit_rule",
        "no_news_acceptance_threshold",
        "aggregate_score",
    ):
        if protocol.get(field) is not None:
            raise ValueError(f"feature_protocol.{field} must remain null")
    if protocol.get("provider_relative_absence_remains_provider_relative") is not True:
        raise ValueError("provider-relative absence rule must remain explicit")

    binding = payload.get("context_binding")
    if binding != {
        "context_assessment_contract_id": CONTEXT_ASSESSMENT_CONTRACT_ID,
        "evidence_domain": "theme_regime",
        "record_type": RECORD_TYPE,
        "source_artifact_hash_required_before_snapshot_binding": True,
    }:
        raise ValueError("theme/regime context binding differs")
    if payload.get("prohibited_outputs") != list(PROHIBITED_OUTPUT_FIELDS):
        raise ValueError("theme/regime prohibited outputs differ")
    if payload.get("evaluation_boundary") != {
        "registered_panel_id": CONTEXT_HELDOUT_PANEL_ID,
        "registered_panel_content_sha256": CONTEXT_HELDOUT_PANEL_CONTENT_SHA256,
        "runtime_frozen_before_recap_review": True,
        "raw_transcripts_allowed_in_runtime": False,
        "retrospective_labels_allowed_in_runtime": False,
        "policy_promotion_from_this_contract_allowed": False,
    }:
        raise ValueError("theme/regime evaluation boundary differs")


def load_theme_regime_context_contract(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("theme/regime context contract root must be an object")
    validate_theme_regime_context_contract(payload)
    return payload


def _canonical_scanner_rows(
    scanner_rows: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    activation_by_symbol: dict[str, str] = {}
    for source in scanner_rows:
        _require_exact_keys(source, SNAPSHOT_ROW_FIELDS, "scanner_row")
        row = dict(source)
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol or row.get("symbol") != symbol:
            raise ValueError("scanner symbols must be canonical uppercase")
        decision = _timestamp(row.get("decision_time"), "decision_time")
        activation = _timestamp(row.get("activation_time"), "activation_time")
        if activation > decision:
            raise ValueError("scanner activation follows decision")
        if symbol in activation_by_symbol and activation_by_symbol[symbol] != row[
            "activation_time"
        ]:
            raise ValueError("scanner symbol has inconsistent activation time")
        activation_by_symbol[symbol] = str(row["activation_time"])
        key = (symbol, decision.isoformat())
        if key in seen:
            raise ValueError("scanner rows repeat a symbol-decision pair")
        seen.add(key)
        rows.append(row)
    return sorted(
        rows,
        key=lambda row: (str(row["decision_time"]), str(row["symbol"])),
    )


def _news_state_counts(rows: Iterable[Mapping[str, object]]) -> dict[str, int]:
    counts = {
        "provider_news_candidate_count": 0,
        "provider_relative_no_news_candidate_count": 0,
        "provider_error_candidate_count": 0,
    }
    for row in rows:
        if row.get("news_provider_status") != "success":
            counts["provider_error_candidate_count"] += 1
        elif row.get("has_provider_news_as_of") is True:
            counts["provider_news_candidate_count"] += 1
        elif row.get("provider_relative_no_news_as_of") is True:
            counts["provider_relative_no_news_candidate_count"] += 1
        else:
            raise ValueError("scanner news state is internally incomplete")
    return counts


def build_completed_theme_regime_session_summary(
    scanner_rows: Iterable[Mapping[str, object]],
    *,
    trading_date: date | str,
    source_scanner_records_content_sha256: str,
) -> dict[str, object]:
    """Summarize one completed scanner session for use on later dates only."""

    target = _date(trading_date, "trading_date")
    if not _is_sha256(source_scanner_records_content_sha256):
        raise ValueError("scanner source hash must be lowercase SHA-256")
    rows = _canonical_scanner_rows(scanner_rows)
    if not rows:
        raise ValueError("completed session summary requires scanner rows")
    for row in rows:
        if _timestamp(row["decision_time"], "decision_time").astimezone(_ET).date() != target:
            raise ValueError("completed session scanner row has the wrong date")
    final_time = max(_timestamp(row["decision_time"], "decision_time") for row in rows)
    final_rows = [
        row
        for row in rows
        if _timestamp(row["decision_time"], "decision_time") == final_time
    ]
    symbols = sorted({str(row["symbol"]) for row in rows})
    if {str(row["symbol"]) for row in final_rows} != set(symbols):
        raise ValueError("final scanner minute does not cover every activated candidate")
    leader_pairs = {
        (row.get("rank_leader_symbol"), row.get("rank_leader_percent_gain"))
        for row in final_rows
    }
    if len(leader_pairs) != 1:
        raise ValueError("final scanner rows disagree on the market leader")
    leader_symbol, leader_gain = next(iter(leader_pairs))
    activation_rows = sorted(
        (
            {
                "symbol": symbol,
                "activation_time": next(
                    str(row["activation_time"])
                    for row in rows
                    if row["symbol"] == symbol
                ),
            }
            for symbol in symbols
        ),
        key=lambda row: (row["activation_time"], row["symbol"]),
    )
    summary: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "record_type": SESSION_SUMMARY_RECORD_TYPE,
        "contract_id": CONTRACT_ID,
        "trading_date": target.isoformat(),
        "final_decision_time": final_time.isoformat(),
        "source_scanner_records_content_sha256": (
            source_scanner_records_content_sha256
        ),
        "candidate_count": len(symbols),
        "activation_chronology": activation_rows,
        "final_observed_candidate_count": len(final_rows),
        "final_news_state_counts": _news_state_counts(final_rows),
        "final_rank_input_complete_candidate_count": sum(
            row.get("rank_input_complete_for_members_with_completed_bars") is True
            for row in final_rows
        ),
        "final_rank_leader_symbol": leader_symbol,
        "final_rank_leader_percent_gain": leader_gain,
    }
    summary["summary_content_sha256"] = canonical_fingerprint(summary)
    validate_completed_theme_regime_session_summary(summary)
    return summary


def validate_completed_theme_regime_session_summary(
    summary: Mapping[str, object],
) -> None:
    _require_exact_keys(
        summary,
        {
            "schema_version",
            "record_type",
            "contract_id",
            "trading_date",
            "final_decision_time",
            "source_scanner_records_content_sha256",
            "candidate_count",
            "activation_chronology",
            "final_observed_candidate_count",
            "final_news_state_counts",
            "final_rank_input_complete_candidate_count",
            "final_rank_leader_symbol",
            "final_rank_leader_percent_gain",
            "summary_content_sha256",
        },
        "completed_session_summary",
    )
    if summary.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported completed-session summary schema")
    if summary.get("record_type") != SESSION_SUMMARY_RECORD_TYPE:
        raise ValueError("unexpected completed-session summary type")
    if summary.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected completed-session summary contract")
    _date(summary.get("trading_date"), "trading_date")
    _timestamp(summary.get("final_decision_time"), "final_decision_time")
    if not _is_sha256(summary.get("source_scanner_records_content_sha256")):
        raise ValueError("completed-session scanner source hash is invalid")
    rows = summary.get("activation_chronology")
    if not isinstance(rows, list) or summary.get("candidate_count") != len(rows):
        raise ValueError("completed-session activation accounting mismatch")
    if summary.get("final_observed_candidate_count") != len(rows):
        raise ValueError("completed-session final candidate coverage mismatch")
    if not _is_sha256(summary.get("summary_content_sha256")):
        raise ValueError("completed-session summary hash is invalid")
    unhashed = dict(summary)
    supplied = unhashed.pop("summary_content_sha256")
    if canonical_fingerprint(unhashed) != supplied:
        raise ValueError("completed-session summary fingerprint mismatch")


def _canonical_available_news(
    news_events: Iterable[Mapping[str, object]],
    *,
    decision_time: datetime,
    active_symbols: set[str],
) -> list[dict[str, object]]:
    by_story: dict[str, dict[str, object]] = {}
    associations: dict[str, set[str]] = {}
    for source in news_events:
        symbol = str(source.get("symbol") or "").strip().upper()
        headline_id = str(source.get("headline_id") or "").strip()
        title = str(source.get("title") or "").strip()
        if not symbol or not headline_id or not title:
            raise ValueError("news events require symbol, headline_id, and title")
        published = _timestamp(source.get("published_at"), "published_at")
        if published > decision_time or symbol not in active_symbols:
            continue
        provider_symbols_raw = source.get("provider_symbols")
        if not isinstance(provider_symbols_raw, list) or not provider_symbols_raw:
            raise ValueError("news events require provider_symbols")
        provider_symbols = sorted(
            {str(value).strip().upper() for value in provider_symbols_raw if value}
        )
        if symbol not in provider_symbols:
            raise ValueError("news provider symbols omit the associated candidate")
        row = {
            "headline_id": headline_id,
            "published_at": published.isoformat(),
            "availability_basis": str(source.get("availability_basis") or ""),
            "provider": str(source.get("provider") or ""),
            "provider_story_id": str(source.get("provider_story_id") or ""),
            "source": str(source.get("source") or ""),
            "title": title,
            "provider_symbols": provider_symbols,
        }
        if any(not str(row[field]).strip() for field in (
            "availability_basis",
            "provider",
            "provider_story_id",
            "source",
        )):
            raise ValueError("news event provenance is incomplete")
        prior = by_story.get(headline_id)
        if prior is not None and prior != row:
            raise ValueError("duplicate headline ID has inconsistent story fields")
        by_story[headline_id] = row
        associations.setdefault(headline_id, set()).add(symbol)
    output = []
    for headline_id, row in by_story.items():
        candidate_symbols = sorted(associations[headline_id])
        output.append(
            {
                **row,
                "active_candidate_symbols": candidate_symbols,
                "active_candidate_symbol_count": len(candidate_symbols),
            }
        )
    return sorted(
        output,
        key=lambda row: (row["published_at"], row["headline_id"]),
    )


def _candidate_observations(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    output = [
        {
            "symbol": row["symbol"],
            "activation_time": row["activation_time"],
            "decision_time": row["decision_time"],
            "price": row["price"],
            "percent_gain": row["percent_gain"],
            "cumulative_volume": row["cumulative_volume"],
            "exact_same_time_rvol": row["exact_same_time_rvol"],
            "top_gainer_rank": row["top_gainer_rank"],
            "rank_leader_symbol": row["rank_leader_symbol"],
            "rank_leader_percent_gain": row["rank_leader_percent_gain"],
            "news_provider_status": row["news_provider_status"],
            "has_provider_news_as_of": row["has_provider_news_as_of"],
            "provider_relative_no_news_as_of": row[
                "provider_relative_no_news_as_of"
            ],
        }
        for row in rows
    ]
    return sorted(
        output,
        key=lambda row: (
            int(row["top_gainer_rank"])
            if row["top_gainer_rank"] is not None
            else math.inf,
            row["symbol"],
        ),
    )


def _validate_available_news_stories(
    stories: list[dict[str, object]],
    *,
    decision_time: datetime,
    active_symbols: set[str],
) -> None:
    expected_fields = {
        "headline_id",
        "published_at",
        "availability_basis",
        "provider",
        "provider_story_id",
        "source",
        "title",
        "provider_symbols",
        "active_candidate_symbols",
        "active_candidate_symbol_count",
    }
    seen: set[str] = set()
    prior_key: tuple[str, str] | None = None
    for story in stories:
        _require_exact_keys(story, expected_fields, "available_news_story")
        headline_id = str(story.get("headline_id") or "").strip()
        if not headline_id or headline_id in seen:
            raise ValueError("available news stories repeat or omit headline ID")
        seen.add(headline_id)
        published = _timestamp(story.get("published_at"), "story published_at")
        if published > decision_time:
            raise ValueError("available news story is later than the decision")
        key = (published.isoformat(), headline_id)
        if prior_key is not None and key < prior_key:
            raise ValueError("available news stories are not canonical")
        prior_key = key
        provider_symbols = story.get("provider_symbols")
        associated = story.get("active_candidate_symbols")
        if not isinstance(provider_symbols, list) or not provider_symbols:
            raise ValueError("available news story lacks provider symbols")
        if not isinstance(associated, list) or not associated:
            raise ValueError("available news story lacks active candidate associations")
        if associated != sorted(set(associated)):
            raise ValueError("active candidate story associations are not canonical")
        if not set(associated).issubset(active_symbols):
            raise ValueError("news story associates an inactive candidate")
        if not set(associated).issubset(set(provider_symbols)):
            raise ValueError("news story associations escape provider symbols")
        if story.get("active_candidate_symbol_count") != len(associated):
            raise ValueError("news story association count mismatch")
        if any(
            not str(story.get(field) or "").strip()
            for field in (
                "availability_basis",
                "provider",
                "provider_story_id",
                "source",
                "title",
            )
        ):
            raise ValueError("available news story provenance is incomplete")


def _materialize_theme_regime_record(
    *,
    current_rows: list[dict[str, object]],
    available_news: list[dict[str, object]],
    prior_summaries: list[dict[str, object]],
    symbol: str,
    decision_time: datetime,
    source_hashes: Mapping[str, str],
) -> dict[str, object]:
    if symbol not in {str(row["symbol"]) for row in current_rows}:
        raise ValueError("theme/regime subject is absent from current scanner rows")
    _validate_available_news_stories(
        available_news,
        decision_time=decision_time,
        active_symbols={str(row["symbol"]) for row in current_rows},
    )
    leader_pairs = {
        (row.get("rank_leader_symbol"), row.get("rank_leader_percent_gain"))
        for row in current_rows
    }
    if len(leader_pairs) != 1:
        raise ValueError("same-minute scanner rows disagree on the market leader")
    leader_symbol, leader_gain = next(iter(leader_pairs))
    rank_hashes = {row.get("rank_input_ordered_sha256") for row in current_rows}
    if len(rank_hashes) != 1:
        raise ValueError("same-minute scanner rows disagree on rank lineage")
    observations = _candidate_observations(current_rows)
    news_counts = _news_state_counts(current_rows)
    subject_headlines = [
        row["headline_id"]
        for row in available_news
        if symbol in row["active_candidate_symbols"]
    ]
    record: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "record_type": RECORD_TYPE,
        "contract_id": CONTRACT_ID,
        "symbol": symbol,
        "decision_time": decision_time.isoformat(),
        "decision_session_date": decision_time.astimezone(_ET).date().isoformat(),
        "evidence_available_at": decision_time.isoformat(),
        "source_artifact_content_sha256s": dict(source_hashes),
        "causal_cutoff": {
            "current_scanner_rows_exactly_at_decision_time": True,
            "future_headline_used": False,
            "current_session_final_state_used": False,
            "prior_session_summaries_strictly_precede_decision_session": True,
        },
        "input_rows": {
            "current_scanner_rows": current_rows,
            "available_news_stories": available_news,
            "prior_completed_session_summaries": prior_summaries,
        },
        "features": {
            "subject_candidate_observation": next(
                row for row in observations if row["symbol"] == symbol
            ),
            "same_minute_ranked_candidate_cohort": observations,
            "same_minute_observed_candidate_count": len(current_rows),
            "same_minute_rank_input_complete_candidate_count": sum(
                row.get("rank_input_complete_for_members_with_completed_bars") is True
                for row in current_rows
            ),
            "same_minute_rank_leader_symbol": leader_symbol,
            "same_minute_rank_leader_percent_gain": leader_gain,
            "same_minute_news_state_counts": news_counts,
            "available_provider_story_count": len(available_news),
            "cross_candidate_story_count": sum(
                int(row["active_candidate_symbol_count"]) > 1
                for row in available_news
            ),
            "subject_candidate_headline_ids": subject_headlines,
            "subject_candidate_headline_count": len(subject_headlines),
            "prior_completed_session_count": len(prior_summaries),
            "prior_completed_session_summaries": prior_summaries,
        },
        "prohibited_outputs": dict(_PROHIBITED_OUTPUTS),
    }
    record["record_content_sha256"] = canonical_fingerprint(record)
    return record


def build_theme_regime_evidence(
    scanner_rows: Iterable[Mapping[str, object]],
    news_events: Iterable[Mapping[str, object]],
    prior_completed_session_summaries: Iterable[Mapping[str, object]],
    *,
    symbol: str,
    decision_time: datetime | str,
    source_artifact_content_sha256s: Mapping[str, str],
) -> dict[str, object]:
    """Build one threshold-free theme/regime evidence packet."""

    rendered_symbol = str(symbol).strip().upper()
    if not rendered_symbol:
        raise ValueError("symbol is required")
    decision = _timestamp(decision_time, "decision_time")
    if set(source_artifact_content_sha256s) != set(SOURCE_ARTIFACT_KEYS):
        raise ValueError("theme/regime source artifact keys differ")
    source_hashes = {
        key: str(source_artifact_content_sha256s[key])
        for key in SOURCE_ARTIFACT_KEYS
    }
    if any(not _is_sha256(value) for value in source_hashes.values()):
        raise ValueError("theme/regime source hashes must be lowercase SHA-256")

    all_rows = _canonical_scanner_rows(scanner_rows)
    current_rows = [
        row
        for row in all_rows
        if _timestamp(row["decision_time"], "decision_time") == decision
    ]
    if not current_rows or rendered_symbol not in {
        str(row["symbol"]) for row in current_rows
    }:
        raise ValueError("subject candidate lacks an exact decision-time scanner row")
    if any(
        _timestamp(row["decision_time"], "decision_time").astimezone(_ET).date()
        != decision.astimezone(_ET).date()
        for row in current_rows
    ):
        raise ValueError("current scanner cohort has the wrong session date")

    summaries = [dict(row) for row in prior_completed_session_summaries]
    for summary in summaries:
        validate_completed_theme_regime_session_summary(summary)
        if _date(summary["trading_date"], "prior trading date") >= decision.astimezone(
            _ET
        ).date():
            raise ValueError("prior session summary does not precede the decision session")
    summaries.sort(key=lambda row: str(row["trading_date"]))
    if len({row["trading_date"] for row in summaries}) != len(summaries):
        raise ValueError("prior session summaries repeat a date")
    summaries = summaries[-PRIOR_COMPLETED_SESSION_LOOKBACK:]

    available_news = _canonical_available_news(
        news_events,
        decision_time=decision,
        active_symbols={str(row["symbol"]) for row in current_rows},
    )
    record = _materialize_theme_regime_record(
        current_rows=current_rows,
        available_news=available_news,
        prior_summaries=summaries,
        symbol=rendered_symbol,
        decision_time=decision,
        source_hashes=source_hashes,
    )
    validate_theme_regime_evidence(record)
    return record


def validate_theme_regime_evidence(record: Mapping[str, object]) -> None:
    _require_exact_keys(
        record,
        {
            "schema_version",
            "record_type",
            "contract_id",
            "symbol",
            "decision_time",
            "decision_session_date",
            "evidence_available_at",
            "source_artifact_content_sha256s",
            "causal_cutoff",
            "input_rows",
            "features",
            "prohibited_outputs",
            "record_content_sha256",
        },
        "theme_regime_evidence",
    )
    if record.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported theme/regime evidence schema")
    if record.get("record_type") != RECORD_TYPE or record.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected theme/regime evidence identity")
    symbol = str(record.get("symbol") or "").strip().upper()
    if not symbol or record.get("symbol") != symbol:
        raise ValueError("theme/regime symbol must be canonical uppercase")
    decision = _timestamp(record.get("decision_time"), "decision_time")
    if record.get("decision_session_date") != decision.astimezone(_ET).date().isoformat():
        raise ValueError("theme/regime decision session date mismatch")
    if record.get("evidence_available_at") != decision.isoformat():
        raise ValueError("theme/regime evidence availability mismatch")
    source_hashes = record.get("source_artifact_content_sha256s")
    if not isinstance(source_hashes, Mapping) or set(source_hashes) != set(
        SOURCE_ARTIFACT_KEYS
    ):
        raise ValueError("theme/regime source hashes differ")
    if any(not _is_sha256(value) for value in source_hashes.values()):
        raise ValueError("theme/regime source hash is invalid")
    if record.get("prohibited_outputs") != _PROHIBITED_OUTPUTS:
        raise ValueError("theme/regime prohibited outputs must remain null")
    supplied_hash = record.get("record_content_sha256")
    if not _is_sha256(supplied_hash):
        raise ValueError("theme/regime evidence hash is invalid")
    unhashed = dict(record)
    unhashed.pop("record_content_sha256")
    if canonical_fingerprint(unhashed) != supplied_hash:
        raise ValueError("theme/regime evidence fingerprint mismatch")

    inputs = record.get("input_rows")
    if not isinstance(inputs, Mapping):
        raise ValueError("theme/regime input_rows must be an object")
    _require_exact_keys(
        inputs,
        {
            "current_scanner_rows",
            "available_news_stories",
            "prior_completed_session_summaries",
        },
        "theme_regime_input_rows",
    )
    current_raw = inputs.get("current_scanner_rows")
    news_raw = inputs.get("available_news_stories")
    summaries_raw = inputs.get("prior_completed_session_summaries")
    if not isinstance(current_raw, list) or not current_raw:
        raise ValueError("theme/regime current scanner rows are required")
    if not isinstance(news_raw, list) or not isinstance(summaries_raw, list):
        raise ValueError("theme/regime news and prior summaries must be lists")
    current_rows = _canonical_scanner_rows(current_raw)
    if current_rows != current_raw:
        raise ValueError("theme/regime current scanner rows are not canonical")
    if any(
        _timestamp(row["decision_time"], "decision_time") != decision
        for row in current_rows
    ):
        raise ValueError("theme/regime scanner rows are not at the decision time")
    for summary in summaries_raw:
        if not isinstance(summary, Mapping):
            raise ValueError("theme/regime prior summary must be an object")
        validate_completed_theme_regime_session_summary(summary)
    expected = _materialize_theme_regime_record(
        current_rows=current_rows,
        available_news=[dict(row) for row in news_raw],
        prior_summaries=[dict(row) for row in summaries_raw],
        symbol=symbol,
        decision_time=decision,
        source_hashes={key: str(source_hashes[key]) for key in SOURCE_ARTIFACT_KEYS},
    )
    if dict(record) != expected:
        raise ValueError("theme/regime evidence differs from deterministic reconstruction")


def theme_regime_supplemental_evidence(
    record: Mapping[str, object],
    *,
    source_artifact_content_sha256: str,
) -> dict[str, object]:
    validate_theme_regime_evidence(record)
    if not _is_sha256(source_artifact_content_sha256):
        raise ValueError("source artifact hash must be lowercase SHA-256")
    return {
        "evidence_id": (
            f"theme-regime:{record['symbol']}:{record['record_content_sha256']}"
        ),
        "domain": "theme_regime",
        "available_at": record["evidence_available_at"],
        "source_contract_id": CONTRACT_ID,
        "source_artifact_content_sha256": source_artifact_content_sha256,
        "payload": dict(record),
    }
