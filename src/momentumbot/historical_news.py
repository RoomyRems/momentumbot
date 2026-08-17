"""Causal, provider-relative publication-timed news contracts."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timezone
import hashlib
import json
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd


ET = ZoneInfo("America/New_York")
CAUSAL_NEWS_V0_1_POLICY_ID = "causal-alpaca-news-v0.1"
CAUSAL_NEWS_POLICY_ID = "causal-alpaca-news-v0.2"

QUALIFICATION_STATUS_FIELDS = frozenset(
    {
        "symbol",
        "first_market_qualified_at",
        "provider_status",
        "eligible_event_count_at_market_qualification",
        "first_eligible_event_available_at_market_qualification",
        "has_provider_news_at_market_qualification",
        "provider_relative_no_news_at_market_qualification",
        "unknown_fail_closed_at_market_qualification",
    }
)


def _json_fingerprint(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def causal_news_v0_1_manifest() -> dict[str, object]:
    payload: dict[str, object] = {
        "policy_id": CAUSAL_NEWS_V0_1_POLICY_ID,
        "status": "frozen_research_feature_contract_not_promotable",
        "provider": "alpaca_benzinga_news",
        "provider_endpoint": "alpaca_v1beta1_news",
        "freshness_window_start": "previous_regular_session_close_1600_et",
        "freshness_window_end_exclusive": "target_session_1001_et",
        "availability_rule": (
            "provider_updated_at_else_created_at_conservative_content_availability"
        ),
        "association_rule": "provider_story_symbols_intersect_frozen_candidate_symbol",
        "pagination_rule": (
            "exhaust_next_page_token_with_repetition_and_100_page_guards"
        ),
        "absence_rule": "zero_rows_means_no_news_in_this_provider_only",
        "headline_quality_rule": "not_classified_in_this_deterministic_layer",
    }
    return {**payload, "fingerprint": _json_fingerprint(payload)}


def causal_news_v0_2_temporal_boundary() -> dict[str, object]:
    return {
        "full_window_event_tape_retained": True,
        "candidate_status_scope": "as_of_first_market_qualification_only",
        "candidate_decision_time_field": "first_market_qualified_at",
        "candidate_decision_time_semantics": (
            "decision_availability_after_completed_source_bar"
        ),
        "as_of_projection_rule": "published_at <= decision_time",
        "decision_time_must_be_timezone_aware": True,
        "post_qualification_events_retained_on_tape": True,
        "post_qualification_events_available_to_earlier_decisions": False,
        "runtime_consumers_must_project_full_window_tape": True,
    }


def causal_news_v0_2_manifest() -> dict[str, object]:
    payload: dict[str, object] = {
        "policy_id": CAUSAL_NEWS_POLICY_ID,
        "supersedes_policy_id": CAUSAL_NEWS_V0_1_POLICY_ID,
        "supersedes_policy_fingerprint": causal_news_v0_1_manifest()[
            "fingerprint"
        ],
        "status": "frozen_research_feature_contract_not_promotable",
        "provider": "alpaca_benzinga_news",
        "provider_endpoint": "alpaca_v1beta1_news",
        "freshness_window_start": "previous_regular_session_close_1600_et",
        "freshness_window_end_exclusive": "target_session_1001_et",
        "availability_rule": (
            "provider_updated_at_else_created_at_conservative_content_availability"
        ),
        "association_rule": "provider_story_symbols_intersect_frozen_candidate_symbol",
        "pagination_rule": (
            "exhaust_next_page_token_with_repetition_and_100_page_guards"
        ),
        "absence_rule": (
            "zero_as_of_projected_rows_means_no_news_in_this_provider_only"
        ),
        "headline_quality_rule": "not_classified_in_this_deterministic_layer",
        "temporal_boundary": causal_news_v0_2_temporal_boundary(),
    }
    return {**payload, "fingerprint": _json_fingerprint(payload)}


def prior_regular_session_date(
    calendar_bars: pd.DataFrame,
    *,
    trading_date: date,
) -> date:
    if calendar_bars.empty:
        raise ValueError("calendar proxy returned no daily bars")
    if calendar_bars.index.tz is None:
        raise ValueError("calendar proxy bars must be timezone-aware")
    local_dates = calendar_bars.index.tz_convert(ET).date
    prior = sorted({value for value in local_dates if value < trading_date})
    if not prior:
        raise ValueError("calendar proxy lacks a prior regular session")
    return prior[-1]


def publication_window(
    *,
    trading_date: date,
    prior_session: date,
) -> tuple[datetime, datetime]:
    if prior_session >= trading_date:
        raise ValueError("prior news session must precede the target session")
    start = datetime.combine(prior_session, time(16, 0), ET)
    end = datetime.combine(trading_date, time(10, 1), ET)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _provider_timestamp(value: object, *, label: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Alpaca news {label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def normalize_alpaca_news(
    rows: Iterable[dict[str, object]],
    *,
    candidate_symbols: set[str],
    window_start: datetime,
    window_end: datetime,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    if window_start.tzinfo is None or window_end.tzinfo is None:
        raise ValueError("news window must be timezone-aware")
    if window_start >= window_end:
        raise ValueError("news window start must precede end")
    candidates = {symbol.strip().upper() for symbol in candidate_symbols if symbol}
    dispositions: Counter[str] = Counter()
    normalized: dict[tuple[str, str], dict[str, object]] = {}
    for source in rows:
        raw_symbols = source.get("symbols")
        provider_symbols = (
            sorted({str(value).strip().upper() for value in raw_symbols if value})
            if isinstance(raw_symbols, list)
            else []
        )
        matched = sorted(candidates & set(provider_symbols))
        if not matched:
            dispositions["ignored_without_frozen_candidate_association"] += 1
            continue
        created_raw = source.get("created_at")
        updated_raw = source.get("updated_at")
        if not created_raw and not updated_raw:
            raise ValueError("candidate-associated Alpaca story lacks a timestamp")
        created = (
            _provider_timestamp(created_raw, label="created_at")
            if created_raw
            else None
        )
        updated = (
            _provider_timestamp(updated_raw, label="updated_at")
            if updated_raw
            else None
        )
        if created and updated and updated < created:
            raise ValueError("Alpaca story updated_at precedes created_at")
        available_at = updated or created
        assert available_at is not None
        if not (window_start <= available_at < window_end):
            dispositions["ignored_outside_frozen_publication_window"] += 1
            continue
        provider_id = str(
            source.get("id") or source.get("url") or source.get("headline") or ""
        ).strip()
        if not provider_id:
            raise ValueError("candidate-associated Alpaca story lacks an identifier")
        headline_id = f"alpaca-benzinga:{provider_id}"
        for symbol in matched:
            event: dict[str, object] = {
                "symbol": symbol,
                "published_at": available_at.isoformat(),
                "headline_id": headline_id,
                "title": str(source.get("headline") or ""),
                "source": str(source.get("source") or ""),
                "provider": "alpaca-benzinga",
                "provider_story_id": provider_id,
                "provider_symbols": provider_symbols,
                "original_created_at": created.isoformat() if created else None,
                "provider_updated_at": updated.isoformat() if updated else None,
                "availability_basis": (
                    "provider_updated_at" if updated else "provider_created_at"
                ),
            }
            key = (symbol, headline_id)
            prior = normalized.get(key)
            if prior is None or str(event["published_at"]) > str(
                prior["published_at"]
            ):
                normalized[key] = event
            dispositions["normalized_candidate_event"] += 1
    events = sorted(
        normalized.values(),
        key=lambda row: (
            str(row["published_at"]),
            str(row["symbol"]),
            str(row["headline_id"]),
        ),
    )
    dispositions["deduplicated_candidate_event_count"] = len(events)
    return events, dict(sorted(dispositions.items()))


def project_news_events_as_of(
    events: Iterable[dict[str, object]],
    *,
    decision_time: datetime,
    symbol: str | None = None,
) -> list[dict[str, object]]:
    """Return only events knowable at a timezone-aware decision instant."""

    if decision_time.tzinfo is None:
        raise ValueError("news decision time must be timezone-aware")
    decision_utc = decision_time.astimezone(timezone.utc)
    selected_symbol = symbol.strip().upper() if symbol is not None else None
    if symbol is not None and not selected_symbol:
        raise ValueError("news projection symbol must be nonblank")
    projected: list[dict[str, object]] = []
    for event in events:
        event_symbol = str(event.get("symbol") or "").strip().upper()
        if not event_symbol:
            raise ValueError("news event symbol must be nonblank")
        published_at = _provider_timestamp(
            event.get("published_at"),
            label="published_at",
        )
        if selected_symbol is not None and event_symbol != selected_symbol:
            continue
        if published_at <= decision_utc:
            projected.append(event)
    return sorted(
        projected,
        key=lambda row: (
            str(row["published_at"]),
            str(row["symbol"]),
            str(row["headline_id"]),
        ),
    )


def news_tape_coverage(
    candidate_rows: Iterable[dict[str, object]],
    events: Iterable[dict[str, object]],
) -> dict[str, int]:
    """Summarize the full tape without turning future rows into status fields."""

    candidates: dict[str, datetime] = {}
    for candidate in candidate_rows:
        symbol = str(candidate.get("symbol") or "")
        qualified_at = datetime.fromisoformat(
            str(candidate.get("first_market_qualified_at") or "")
        )
        if not symbol or symbol in candidates:
            raise ValueError("news tape coverage requires unique candidate symbols")
        if qualified_at.tzinfo is None:
            raise ValueError("market qualification must be timezone-aware")
        candidates[symbol] = qualified_at.astimezone(timezone.utc)

    materialized_events = list(events)
    symbols_with_events: set[str] = set()
    symbols_with_post_qualification_events: set[str] = set()
    post_qualification_event_count = 0
    for event in materialized_events:
        symbol = str(event.get("symbol") or "")
        if symbol not in candidates:
            raise ValueError("news tape event is not tied to a frozen candidate")
        published_at = _provider_timestamp(
            event.get("published_at"),
            label="published_at",
        )
        symbols_with_events.add(symbol)
        if published_at > candidates[symbol]:
            post_qualification_event_count += 1
            symbols_with_post_qualification_events.add(symbol)
    return {
        "full_window_candidate_event_count": len(materialized_events),
        "full_window_provider_story_count": len(
            {str(row.get("headline_id") or "") for row in materialized_events}
        ),
        "candidates_with_any_full_window_provider_news_count": len(
            symbols_with_events
        ),
        "full_window_post_qualification_candidate_event_count": (
            post_qualification_event_count
        ),
        "candidates_with_post_qualification_tape_events_count": len(
            symbols_with_post_qualification_events
        ),
    }


def build_news_candidate_statuses(
    candidate_rows: Iterable[dict[str, object]],
    events: Iterable[dict[str, object]],
    *,
    provider_status_by_symbol: dict[str, str],
) -> list[dict[str, object]]:
    by_symbol: dict[str, list[dict[str, object]]] = {}
    for event in events:
        by_symbol.setdefault(str(event["symbol"]), []).append(event)
    output: list[dict[str, object]] = []
    for candidate in sorted(candidate_rows, key=lambda row: str(row["symbol"])):
        symbol = str(candidate["symbol"])
        qualified_at = datetime.fromisoformat(
            str(candidate["first_market_qualified_at"])
        )
        if qualified_at.tzinfo is None:
            raise ValueError("market qualification must be timezone-aware")
        rows = by_symbol.get(symbol, [])
        available_at_qualification = project_news_events_as_of(
            rows,
            decision_time=qualified_at,
        )
        status = provider_status_by_symbol.get(symbol)
        if status not in {"success", "provider_error_fail_closed"}:
            raise ValueError(f"missing news acquisition status for {symbol}")
        if status != "success" and rows:
            raise ValueError(f"provider-error news candidate {symbol} has events")
        output.append(
            {
                "symbol": symbol,
                "first_market_qualified_at": qualified_at.isoformat(),
                "provider_status": status,
                "eligible_event_count_at_market_qualification": len(
                    available_at_qualification
                ),
                "first_eligible_event_available_at_market_qualification": (
                    min(
                        str(row["published_at"])
                        for row in available_at_qualification
                    )
                    if available_at_qualification
                    else None
                ),
                "has_provider_news_at_market_qualification": bool(
                    available_at_qualification
                ),
                "provider_relative_no_news_at_market_qualification": (
                    status == "success" and not available_at_qualification
                ),
                "unknown_fail_closed_at_market_qualification": status != "success",
            }
        )
    return output


def validate_publication_timed_news(
    candidate_rows: Iterable[dict[str, object]],
    events: Iterable[dict[str, object]],
    statuses: Iterable[dict[str, object]],
    *,
    window_start: datetime,
    window_end: datetime,
) -> None:
    if window_start.tzinfo is None or window_end.tzinfo is None:
        raise ValueError("news window must be timezone-aware")
    if window_start >= window_end:
        raise ValueError("news window start must precede end")
    candidates = {str(row["symbol"]): row for row in candidate_rows}
    materialized_events = list(events)
    materialized_statuses = list(statuses)
    status_symbols = [str(row.get("symbol") or "") for row in materialized_statuses]
    if len(status_symbols) != len(set(status_symbols)):
        raise ValueError("news candidate statuses repeat a symbol")
    if set(status_symbols) != set(candidates):
        raise ValueError("news statuses do not decide every market candidate")
    event_keys: set[tuple[str, str]] = set()
    events_by_symbol: dict[str, list[dict[str, object]]] = {}
    for event in materialized_events:
        symbol = str(event.get("symbol") or "")
        if symbol not in candidates:
            raise ValueError("news event is not tied to a frozen market candidate")
        timestamp = datetime.fromisoformat(str(event.get("published_at") or ""))
        if timestamp.tzinfo is None:
            raise ValueError("news event publication must be timezone-aware")
        if not (window_start <= timestamp < window_end):
            raise ValueError("news event escaped its frozen publication window")
        key = (symbol, str(event.get("headline_id") or ""))
        if not key[1] or key in event_keys:
            raise ValueError("news events require unique stable headline IDs")
        event_keys.add(key)
        events_by_symbol.setdefault(symbol, []).append(event)
    for status in materialized_statuses:
        if set(status) != QUALIFICATION_STATUS_FIELDS:
            raise ValueError(
                "news qualification status fields are not strictly as-of qualification"
            )
        symbol = str(status["symbol"])
        candidate = candidates[symbol]
        if status.get("first_market_qualified_at") != candidate.get(
            "first_market_qualified_at"
        ):
            raise ValueError(f"news qualification mismatch for {symbol}")
        symbol_events = events_by_symbol.get(symbol, [])
        qualified_at = datetime.fromisoformat(
            str(candidate["first_market_qualified_at"])
        )
        if qualified_at.tzinfo is None:
            raise ValueError("market qualification must be timezone-aware")
        eligible_events = project_news_events_as_of(
            symbol_events,
            decision_time=qualified_at,
        )
        if status.get("eligible_event_count_at_market_qualification") != len(
            eligible_events
        ):
            raise ValueError(f"news eligible event count mismatch for {symbol}")
        expected_first = (
            min(str(row["published_at"]) for row in eligible_events)
            if eligible_events
            else None
        )
        if (
            status.get("first_eligible_event_available_at_market_qualification")
            != expected_first
        ):
            raise ValueError(
                f"news first eligible event timestamp mismatch for {symbol}"
            )
        expected_at_qualification = bool(eligible_events)
        if status.get(
            "has_provider_news_at_market_qualification"
        ) is not expected_at_qualification:
            raise ValueError(f"news qualification state mismatch for {symbol}")
        provider_status = status.get("provider_status")
        if provider_status == "provider_error_fail_closed":
            if (
                status.get("unknown_fail_closed_at_market_qualification")
                is not True
            ):
                raise ValueError(
                    f"news provider error did not fail closed for {symbol}"
                )
            if symbol_events:
                raise ValueError(f"news provider error retained events for {symbol}")
            if (
                status.get("provider_relative_no_news_at_market_qualification")
                is not False
            ):
                raise ValueError(f"news provider error mimics no-news for {symbol}")
        elif provider_status == "success":
            if (
                status.get("unknown_fail_closed_at_market_qualification")
                is not False
            ):
                raise ValueError(
                    f"successful news status is marked unknown for {symbol}"
                )
            if status.get(
                "provider_relative_no_news_at_market_qualification"
            ) is not (not eligible_events):
                raise ValueError(f"news no-news state mismatch for {symbol}")
        else:
            raise ValueError(f"unsupported news provider status for {symbol}")


def news_events_fingerprint(events: Iterable[dict[str, object]]) -> str:
    return _json_fingerprint(list(events))


def news_statuses_fingerprint(statuses: Iterable[dict[str, object]]) -> str:
    return _json_fingerprint(list(statuses))


def load_publication_timed_news(
    date_root: str | Path,
    *,
    candidate_rows: list[dict[str, object]],
    candidate_payload: dict[str, object],
    source_float_records_sha256: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    root = Path(date_root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 2:
        raise ValueError("unsupported causal news schema")
    if manifest.get("artifact_id") != CAUSAL_NEWS_POLICY_ID:
        raise ValueError("unsupported causal news artifact")
    if manifest.get("news_policy") != causal_news_v0_2_manifest():
        raise ValueError("causal news policy mismatch")
    if manifest.get("temporal_boundary") != causal_news_v0_2_temporal_boundary():
        raise ValueError("causal news temporal boundary mismatch")
    if manifest.get("source_market_candidates_sha256") != candidate_payload.get(
        "content_sha256"
    ):
        raise ValueError("causal news source candidate mismatch")
    if manifest.get("source_float_records_sha256") != source_float_records_sha256:
        raise ValueError("causal news source float mismatch")
    eligibility = manifest.get("eligibility", {})
    if eligibility.get("complete_relative_to_provider") is not True:
        raise ValueError("causal news acquisition is incomplete")
    if eligibility.get("publication_timed_news_frozen") is not True:
        raise ValueError("causal news decisions are not frozen")
    if eligibility.get("full_feature_snapshot_complete") is not False:
        raise ValueError("causal news artifact overclaims feature completeness")
    if eligibility.get("universe_complete") is not False:
        raise ValueError("causal news artifact overclaims universe completeness")
    knowledge = manifest.get("knowledge_policy", {})
    if knowledge.get("uses_benchmark_labels") is not False:
        raise ValueError("causal news artifact must be label-blind")
    if knowledge.get("qualification_status_uses_future_publications") is not False:
        raise ValueError("causal news qualification status used future publications")
    if (
        knowledge.get("full_window_tape_is_runtime_safe_without_projection")
        is not False
    ):
        raise ValueError("causal news full-window tape overclaims runtime safety")
    if knowledge.get("candidate_acquisition_depends_on_news") is not False:
        raise ValueError("causal news contaminated market-candidate acquisition")
    if knowledge.get("absence_means_no_news_in_all_sources") is not False:
        raise ValueError("causal news overclaims provider absence")
    files = manifest.get("files", {})
    if files.get("news_records_schema") != (
        "full_window_event_tape_plus_as_of_qualification_statuses"
    ):
        raise ValueError("causal news records schema metadata mismatch")
    relative = files.get("news_records")
    if not isinstance(relative, str) or not relative:
        raise ValueError("causal news artifact lacks records")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("causal news path must stay inside its artifact")
    payload = json.loads((root / path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 2:
        raise ValueError("causal news records payload is invalid")
    events = payload.get("full_window_event_tape")
    statuses = payload.get("qualification_statuses")
    if not isinstance(events, list) or not isinstance(statuses, list):
        raise ValueError("causal news records payload is invalid")
    window = manifest.get("publication_window", {})
    start = datetime.fromisoformat(str(window.get("start") or ""))
    end = datetime.fromisoformat(str(window.get("end_exclusive") or ""))
    validate_publication_timed_news(
        candidate_rows,
        events,
        statuses,
        window_start=start,
        window_end=end,
    )
    summary = manifest.get("summary", {})
    if summary.get("market_candidate_count") != len(candidate_rows):
        raise ValueError("causal news source candidate count mismatch")
    if summary.get("full_window_candidate_event_count") != len(events):
        raise ValueError("causal news event count mismatch")
    if summary.get("qualification_status_count") != len(statuses):
        raise ValueError("causal news candidate count mismatch")
    if summary.get("full_window_events_sha256") != news_events_fingerprint(events):
        raise ValueError("causal news event fingerprint mismatch")
    if summary.get("qualification_statuses_sha256") != news_statuses_fingerprint(
        statuses
    ):
        raise ValueError("causal news status fingerprint mismatch")
    coverage = news_tape_coverage(candidate_rows, events)
    for field, expected in coverage.items():
        if summary.get(field) != expected:
            raise ValueError(f"causal news tape coverage mismatch for {field}")
    expected_availability_counts = dict(
        sorted(Counter(str(row.get("availability_basis")) for row in events).items())
    )
    if (
        summary.get("full_window_availability_basis_counts")
        != expected_availability_counts
    ):
        raise ValueError("causal news availability-basis coverage mismatch")
    raw_provider_row_count = summary.get("full_window_raw_provider_row_count")
    if (
        not isinstance(raw_provider_row_count, int)
        or raw_provider_row_count < coverage["full_window_provider_story_count"]
    ):
        raise ValueError("causal news raw-provider coverage is invalid")
    contains_post_qualification = (
        coverage["full_window_post_qualification_candidate_event_count"] > 0
    )
    if knowledge.get(
        "full_window_tape_contains_post_qualification_events"
    ) is not contains_post_qualification:
        raise ValueError("causal news post-qualification boundary mismatch")
    news_at_qualification = sum(
        row.get("has_provider_news_at_market_qualification") is True
        for row in statuses
    )
    no_news_at_qualification = sum(
        row.get("provider_relative_no_news_at_market_qualification") is True
        for row in statuses
    )
    unknown_at_qualification = sum(
        row.get("unknown_fail_closed_at_market_qualification") is True
        for row in statuses
    )
    if summary.get(
        "candidates_with_news_at_market_qualification_count"
    ) != news_at_qualification:
        raise ValueError("causal news qualification-news count mismatch")
    if summary.get(
        "candidates_with_provider_relative_no_news_at_market_qualification_count"
    ) != no_news_at_qualification:
        raise ValueError("causal news qualification no-news count mismatch")
    if summary.get(
        "candidates_unknown_fail_closed_at_market_qualification_count"
    ) != unknown_at_qualification:
        raise ValueError("causal news qualification unknown count mismatch")
    if (
        news_at_qualification
        + no_news_at_qualification
        + unknown_at_qualification
        != len(candidate_rows)
    ):
        raise ValueError("causal news qualification statuses are not exhaustive")
    if summary.get("provider_error_count") != 0 or any(
        row.get("provider_status") != "success" for row in statuses
    ):
        raise ValueError("complete causal news artifact retains a provider error")
    return events, statuses, manifest


def load_publication_timed_news_as_of(
    date_root: str | Path,
    *,
    candidate_rows: list[dict[str, object]],
    candidate_payload: dict[str, object],
    source_float_records_sha256: str,
    decision_time: datetime,
    symbol: str | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Load and validate a tape, then expose only rows knowable as of a decision."""

    events, _qualification_statuses, manifest = load_publication_timed_news(
        date_root,
        candidate_rows=candidate_rows,
        candidate_payload=candidate_payload,
        source_float_records_sha256=source_float_records_sha256,
    )
    return (
        project_news_events_as_of(
            events,
            decision_time=decision_time,
            symbol=symbol,
        ),
        manifest,
    )
