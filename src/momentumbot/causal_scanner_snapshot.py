"""Causal, label-blind scanner feature decisions on a completed-bar clock.

This module deliberately stops at a scanner disposition.  It contains no
trade, setup, portfolio, P&L, or retrospective benchmark behavior.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
import hashlib
import json
import math
from pathlib import Path
from typing import Iterable, Mapping
from zoneinfo import ZoneInfo

import pandas as pd

from .causal_market_discovery import (
    CAUSAL_MARKET_CANDIDATES_ARTIFACT_ID,
    CAUSAL_MARKET_DISCOVERY_POLICY_ID,
    causal_market_discovery_v0_2_manifest,
    strategy_profile_manifest,
)
from .historical_float import CAUSAL_FLOAT_POLICY_ID, FLOAT_LIMIT
from .historical_news import (
    CAUSAL_NEWS_POLICY_ID,
    causal_news_v0_2_manifest,
    project_news_events_as_of,
)
from .identity_resolved_universe import (
    IDENTITY_RESOLVED_UNIVERSE_POLICY_ID,
)
from .models import StrategyProfile


SESSION_TIMEZONE = "America/New_York"
ET = ZoneInfo(SESSION_TIMEZONE)
CAUSAL_SCANNER_SNAPSHOT_POLICY_ID = "causal-scanner-snapshot-v0.1"
CAUSAL_SCANNER_SNAPSHOT_ARTIFACT_ID = CAUSAL_SCANNER_SNAPSHOT_POLICY_ID
RANK_ACQUISITION_PROVIDER = "alpaca_historical_stock_bars"
RANK_HISTORICAL_FEED = "sip"
RANK_PREVIOUS_CLOSE_TIMEFRAME = "1Day"
RANK_PREVIOUS_CLOSE_ADJUSTMENT = "split"
RANK_PRIOR_CLOSE_LOOKBACK_CALENDAR_DAYS = 21
RANK_MINUTE_TIMEFRAME = "1Min"
RANK_MINUTE_ADJUSTMENT = "raw"
RANK_ACQUISITION_ASOF_RULE = "trading_date"
UPSTREAM_MARKET_ACQUISITION_TAIL_END = time(10, 1)
CANDIDATE_PREVIOUS_CLOSE_REL_TOL = 1e-12
CANDIDATE_PREVIOUS_CLOSE_ABS_TOL = 1e-12

_SOURCE_HASH_ORDER = (
    "identity_resolved_membership",
    "market_candidates",
    "market_discovery_manifest",
    "causal_float_records",
    "causal_float_manifest",
    "publication_timed_news_events",
    "publication_timed_news_statuses",
    "publication_timed_news_manifest",
    "reacquired_market_inputs",
)
_LOWER_HEX = frozenset("0123456789abcdef")

SNAPSHOT_ROW_FIELDS = frozenset(
    {
        "symbol",
        "activation_time",
        "decision_time",
        "required_source_bar_started_at",
        "candidate_completed_bar_present",
        "candidate_bar_available_at",
        "price",
        "previous_close",
        "percent_gain",
        "cumulative_volume",
        "exact_same_time_rvol",
        "price_pillar_pass",
        "gain_pillar_pass",
        "rvol_pillar_pass",
        "float_classification",
        "float_pillar_pass",
        "estimated_float_shares",
        "float_asof",
        "float_method",
        "float_provider_status",
        "news_provider_status",
        "provider_news_event_count_as_of",
        "has_provider_news_as_of",
        "provider_relative_no_news_as_of",
        "first_provider_news_published_at_as_of",
        "latest_provider_news_published_at_as_of",
        "identity_resolved_member_count",
        "rank_members_with_completed_bar_count",
        "rank_members_with_completed_close_count",
        "rank_members_missing_completed_close_count",
        "rank_members_missing_previous_close_count",
        "rank_members_with_computable_gain_count",
        "rank_members_without_completed_bar_count",
        "rank_input_complete_for_members_with_completed_bars",
        "rank_input_ordered_sha256",
        "top_gainer_rank",
        "rank_leader_symbol",
        "rank_leader_percent_gain",
        "disposition",
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


def _is_lower_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _LOWER_HEX for character in value)
    )


def _canonical_number(value: object) -> float | str | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    if math.isinf(number):
        return "positive_infinity" if number > 0 else "negative_infinity"
    if not math.isfinite(number):
        return None
    return number


def _numeric_feature(value: object) -> float | None:
    if value == "positive_infinity":
        return math.inf
    if value == "negative_infinity":
        return -math.inf
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if not math.isnan(number) else None


def causal_scanner_snapshot_v0_1_manifest() -> dict[str, object]:
    payload: dict[str, object] = {
        "policy_id": CAUSAL_SCANNER_SNAPSHOT_POLICY_ID,
        "status": "frozen_research_feature_decision_contract_not_promotable",
        "source_identity_policy_id": IDENTITY_RESOLVED_UNIVERSE_POLICY_ID,
        "source_market_policy_id": CAUSAL_MARKET_DISCOVERY_POLICY_ID,
        "source_market_candidate_artifact_id": (
            CAUSAL_MARKET_CANDIDATES_ARTIFACT_ID
        ),
        "source_float_policy_id": CAUSAL_FLOAT_POLICY_ID,
        "source_news_policy_id": CAUSAL_NEWS_POLICY_ID,
        "activation_rule": "first_market_qualified_at",
        "session_timezone": SESSION_TIMEZONE,
        "decision_clock_rule": (
            "one_wall_clock_minute_from_activation_to_exclusive_cutoff"
        ),
        "completed_bar_rule": (
            "one_minute_bar_close_available_at_bar_start_plus_one_minute"
        ),
        "candidate_bar_rule": (
            "exact_completed_uniform_reacquired_membership_bar_required_for_"
            "each_candidate_decision_after_market_reconstruction_corroboration"
        ),
        "candidate_rank_frame_authority_rule": (
            "uniform_all_membership_reacquired_frame_is_authoritative_for_"
            "both_rank_and_candidate_features_never_switched_by_eventual_"
            "candidate_status"
        ),
        "candidate_rank_frame_close_match_tolerance": {
            "relative": CANDIDATE_PREVIOUS_CLOSE_REL_TOL,
            "absolute": CANDIDATE_PREVIOUS_CLOSE_ABS_TOL,
        },
        "candidate_rank_frame_volume_match_rule": "exact_numeric_equality",
        "upstream_market_acquisition_tail_rule": (
            "accept_target_date_minute_bars_through_10:01_America/New_York_"
            "then_drop_bars_not_completed_strictly_before_exclusive_cutoff_"
            "before_fingerprinting_or_features"
        ),
        "market_feature_rule": (
            "raw_close_gain_cumulative_volume_and_exact_same_time_split_rvol"
        ),
        "rank_rule": (
            "gain_desc_symbol_asc_over_all_identity_members_with_latest_"
            "completed_close_observed_from_volume_feature_start_through_"
            "decision_and_carried_forward"
        ),
        "rank_coverage_rule": (
            "members_without_completed_bar_since_volume_feature_start_are_"
            "counted_but_absent_from_rank_input"
        ),
        "rank_threshold_rule": "feature_only_no_final_top_n_threshold_frozen",
        "prior_close_input_rule": (
            "identity_membership_symbol_ascending_split_adjusted_previous_close"
        ),
        "candidate_previous_close_authority_rule": (
            "uniform_all_membership_reacquired_split_previous_close_is_"
            "authoritative_for_both_rank_and_candidate_snapshot_after_"
            "frozen_market_candidate_corroboration"
        ),
        "candidate_previous_close_match_tolerance": {
            "relative": CANDIDATE_PREVIOUS_CLOSE_REL_TOL,
            "absolute": CANDIDATE_PREVIOUS_CLOSE_ABS_TOL,
        },
        "rank_acquisition_basis": {
            "provider": RANK_ACQUISITION_PROVIDER,
            "feed": RANK_HISTORICAL_FEED,
            "previous_close_timeframe": RANK_PREVIOUS_CLOSE_TIMEFRAME,
            "previous_close_adjustment": RANK_PREVIOUS_CLOSE_ADJUSTMENT,
            "previous_close_lookback_calendar_days": (
                RANK_PRIOR_CLOSE_LOOKBACK_CALENDAR_DAYS
            ),
            "minute_timeframe": RANK_MINUTE_TIMEFRAME,
            "minute_adjustment": RANK_MINUTE_ADJUSTMENT,
            "asof_rule": RANK_ACQUISITION_ASOF_RULE,
        },
        "rank_missing_rule": (
            "missing_candidate_rank_or_incomplete_gain_input_fails_closed"
        ),
        "float_rule": "frozen_causal_classification_and_asof",
        "float_profile_rule": (
            "profile_max_float_shares_must_equal_source_float_policy_limit"
        ),
        "float_unknown_rule": "unknown_or_provider_error_fails_closed",
        "news_rule": "provider_event_published_at_lte_decision_time_only",
        "news_absence_rule": (
            "successful_provider_relative_absence_recorded_unclassified"
        ),
        "news_provider_error_rule": "provider_error_fails_closed",
        "artifact_provider_error_rule": (
            "fatal_upstream_float_news_or_rank_acquisition_error_blocks_"
            "entire_date"
        ),
        "row_provider_error_rule": (
            "defensive_fail_closed_state_for_validated_per_symbol_status_only"
        ),
        "partial_date_emission_on_provider_error": False,
        "disposition_precedence": [
            "missing_candidate_completed_bar",
            "missing_candidate_market_feature",
            "missing_cross_sectional_rank",
            "unknown_float",
            "news_provider_error",
            "price_rule",
            "gain_rule",
            "rvol_rule",
            "float_rule",
            "provider_news_presence_unclassified",
        ],
        "ordered_record_rule": "decision_time_ascending_then_symbol_ascending",
        "source_input_fingerprint_rule": (
            "streamed_canonical_newline_records_without_materializing_full_tape"
        ),
        "source_input_persistence_rule": (
            "fingerprint_only_raw_reacquired_inputs_not_persisted"
        ),
        "forbidden_runtime_inputs": [
            "benchmark_labels",
            "retrospective_trade_outcomes",
            "future_session_extrema_as_snapshot_features",
            "trades",
            "setups",
            "portfolio_state",
            "pnl",
        ],
    }
    return {**payload, "fingerprint": _json_fingerprint(payload)}


def _aware_datetime(value: object, *, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError(f"{label} is not a valid timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed


def _validate_feature_only_profile(profile: StrategyProfile) -> None:
    if profile.require_top_gainer_rank is not None:
        raise ValueError(
            "causal scanner snapshot freezes rank as a feature only; "
            "top-N profiles are unsupported"
        )
    if profile.max_float_shares != FLOAT_LIMIT:
        raise ValueError(
            "scanner profile max float must equal the frozen causal float "
            f"policy limit of {FLOAT_LIMIT} shares"
        )
    if any(
        value.second or value.microsecond
        for value in (
            profile.volume_feature_start,
            profile.session_start,
            profile.no_new_entries_after,
        )
    ):
        raise ValueError("scanner profile time boundaries must be minute-aligned")
    if not (
        profile.volume_feature_start
        <= profile.session_start
        < profile.no_new_entries_after
    ):
        raise ValueError(
            "scanner profile requires volume start <= session start < cutoff"
        )


def _validate_intraday_frame_window(
    frame: pd.DataFrame,
    *,
    trading_date: date,
    start: time,
    cutoff: time,
    label: str,
) -> None:
    _validate_frame(frame, label=label)
    if frame.empty:
        return
    local = frame.index.tz_convert(ET)
    cutoff_at = datetime.combine(trading_date, cutoff, ET)
    for timestamp in local:
        if timestamp.date() != trading_date:
            raise ValueError(f"{label} escaped the target trading date")
        if timestamp.second or timestamp.microsecond or timestamp.nanosecond:
            raise ValueError(f"{label} contains an off-minute timestamp")
        local_time = timestamp.timetz().replace(tzinfo=None)
        if local_time < start or timestamp.to_pydatetime() + timedelta(
            minutes=1
        ) >= cutoff_at:
            raise ValueError(f"{label} escaped the frozen intraday window")


def trim_scanner_bar_frame(
    frame: pd.DataFrame,
    *,
    trading_date: date,
    start: time,
    cutoff: time,
    acquisition_end: time | None = None,
    label: str,
) -> pd.DataFrame:
    """Validate a declared fetch envelope, then drop unavailable tail bars."""

    _validate_frame(frame, label=label)
    if frame.empty:
        return frame.copy()
    local = frame.index.tz_convert(ET)
    acquisition_window_end = cutoff if acquisition_end is None else acquisition_end
    if acquisition_window_end < cutoff:
        raise ValueError(f"{label} acquisition end precedes the runtime cutoff")
    for timestamp in local:
        if timestamp.date() != trading_date:
            raise ValueError(f"{label} escaped the target trading date")
        if timestamp.second or timestamp.microsecond or timestamp.nanosecond:
            raise ValueError(f"{label} contains an off-minute timestamp")
        local_time = timestamp.timetz().replace(tzinfo=None)
        if not start <= local_time <= acquisition_window_end:
            raise ValueError(f"{label} escaped the provider acquisition window")
    cutoff_at = datetime.combine(trading_date, cutoff, ET)
    usable = frame.index + pd.Timedelta(minutes=1) < cutoff_at
    trimmed = frame.loc[usable].copy()
    _validate_intraday_frame_window(
        trimmed,
        trading_date=trading_date,
        start=start,
        cutoff=cutoff,
        label=label,
    )
    return trimmed


def trim_scanner_rvol_series(
    series: pd.Series,
    *,
    trading_date: date,
    start: time,
    cutoff: time,
    acquisition_end: time | None = None,
    label: str,
) -> pd.Series:
    if not isinstance(series, pd.Series):
        raise ValueError(f"{label} must be a Series")
    frame = trim_scanner_bar_frame(
        pd.DataFrame({"value": series.to_numpy()}, index=series.index),
        trading_date=trading_date,
        start=start,
        cutoff=cutoff,
        acquisition_end=acquisition_end,
        label=label,
    )
    return pd.Series(
        frame["value"].to_numpy(),
        index=frame.index,
        name=series.name,
        dtype=series.dtype,
    )


def _candidate_activations(
    candidate_rows: Iterable[dict[str, object]],
) -> dict[str, datetime]:
    activations: dict[str, datetime] = {}
    for row in candidate_rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol or symbol in activations:
            raise ValueError("market candidates require unique nonblank symbols")
        started = _aware_datetime(
            row.get("first_market_qualified_bar_started_at"),
            label=f"market candidate {symbol} qualification bar start",
        )
        activated = _aware_datetime(
            row.get("first_market_qualified_at"),
            label=f"market candidate {symbol} activation",
        )
        if activated - started != timedelta(minutes=1):
            raise ValueError(
                f"market candidate {symbol} decision timestamp must equal "
                "bar start plus one minute"
            )
        if activated.second or activated.microsecond:
            raise ValueError(f"market candidate {symbol} activation is off minute")
        activations[symbol] = activated
    return activations


def expected_candidate_decision_keys(
    candidate_rows: Iterable[dict[str, object]],
    *,
    trading_date: date,
    session_start: time,
    cutoff: time,
) -> list[tuple[str, str]]:
    activations = _candidate_activations(candidate_rows)
    cutoff_at = datetime.combine(trading_date, cutoff, ET)
    keys: list[tuple[str, str]] = []
    for symbol, activation in activations.items():
        local = activation.astimezone(ET)
        if local.date() != trading_date:
            raise ValueError(f"market candidate {symbol} activation date mismatch")
        local_time = local.timetz().replace(tzinfo=None)
        if local_time < session_start:
            raise ValueError(f"market candidate {symbol} activates before session start")
        current = activation
        if current >= cutoff_at:
            raise ValueError(f"market candidate {symbol} activates at/after cutoff")
        while current < cutoff_at:
            keys.append((current.isoformat(), symbol))
            current += timedelta(minutes=1)
    return sorted(keys)


def _validated_membership_symbols(symbols: Iterable[str]) -> list[str]:
    materialized = [str(value).strip().upper() for value in symbols]
    if not materialized or any(not value for value in materialized):
        raise ValueError("identity-resolved membership symbols must be nonblank")
    if len(materialized) != len(set(materialized)):
        raise ValueError("identity-resolved membership repeats a symbol")
    return sorted(materialized)


def _validate_frame(frame: pd.DataFrame, *, label: str) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise ValueError(f"{label} must be a DataFrame")
    if frame.empty:
        return
    if frame.index.tz is None:
        raise ValueError(f"{label} index must be timezone-aware")
    if frame.index.has_duplicates:
        raise ValueError(f"{label} timestamps must be unique")
    if not frame.index.is_monotonic_increasing:
        raise ValueError(f"{label} timestamps must be ordered")


def bind_candidate_frames_to_reacquired_rank_frames(
    *,
    membership_symbols: Iterable[str],
    reacquired_rank_frames: Mapping[str, pd.DataFrame],
    authoritative_candidate_frames: Mapping[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """Make candidate feature and rank reads share the uniform rank frame.

    The all-membership reacquisition is authoritative for every member at every
    decision, whether or not that member eventually becomes a candidate.  The
    independently reconstructed candidate frames corroborate timestamp, close,
    and volume coverage, then candidate feature reads bind to the reacquired
    objects.  Eventual candidate status therefore cannot rewrite an earlier
    cross-sectional rank input.
    """

    symbols = _validated_membership_symbols(membership_symbols)
    member_set = set(symbols)
    rank_extras = set(reacquired_rank_frames) - member_set
    candidate_extras = set(authoritative_candidate_frames) - member_set
    if rank_extras or candidate_extras:
        raise ValueError(
            "candidate/rank frame binding contains nonmembership symbols; "
            f"rank_extra={sorted(rank_extras)}, "
            f"candidate_extra={sorted(candidate_extras)}"
        )
    output: dict[str, pd.DataFrame] = {}
    for symbol, authoritative in authoritative_candidate_frames.items():
        _validate_frame(
            authoritative,
            label=f"authoritative candidate bars for {symbol}",
        )
        if authoritative.empty:
            raise ValueError(f"authoritative candidate bars are empty for {symbol}")
        reacquired = reacquired_rank_frames.get(symbol)
        if reacquired is None or reacquired.empty:
            raise ValueError(f"reacquired rank bars are empty for {symbol}")
        _validate_frame(reacquired, label=f"reacquired rank bars for {symbol}")
        if not reacquired.index.equals(authoritative.index):
            raise ValueError(
                "candidate/rank raw-minute timestamp coverage mismatch for "
                f"{symbol}"
            )
        for field in ("close", "volume"):
            if field not in reacquired or field not in authoritative:
                raise ValueError(
                    f"candidate/rank raw-minute frames lack {field} for {symbol}"
                )
        for timestamp in authoritative.index:
            rank_close = _numeric_feature(reacquired.at[timestamp, "close"])
            candidate_close = _numeric_feature(
                authoritative.at[timestamp, "close"]
            )
            if (
                rank_close is None
                or candidate_close is None
                or not math.isclose(
                    rank_close,
                    candidate_close,
                    rel_tol=CANDIDATE_PREVIOUS_CLOSE_REL_TOL,
                    abs_tol=CANDIDATE_PREVIOUS_CLOSE_ABS_TOL,
                )
            ):
                raise ValueError(
                    "candidate/rank raw-minute close mismatch for "
                    f"{symbol} at {timestamp.isoformat()}"
                )
            rank_volume = _numeric_feature(reacquired.at[timestamp, "volume"])
            candidate_volume = _numeric_feature(
                authoritative.at[timestamp, "volume"]
            )
            if rank_volume is None or rank_volume != candidate_volume:
                raise ValueError(
                    "candidate/rank raw-minute volume mismatch for "
                    f"{symbol} at {timestamp.isoformat()}"
                )
        output[symbol] = reacquired
    return output


@dataclass(frozen=True, slots=True)
class CrossSectionalRankState:
    identity_resolved_member_count: int
    rank_members_with_completed_bar_count: int
    rank_members_with_completed_close_count: int
    rank_members_missing_completed_close_count: int
    rank_members_missing_previous_close_count: int
    rank_members_with_computable_gain_count: int
    rank_members_without_completed_bar_count: int
    rank_input_complete_for_members_with_completed_bars: bool
    rank_input_ordered_sha256: str
    ranks: dict[str, int]
    leader_symbol: str | None
    leader_percent_gain: float | None


def cross_sectional_rank_state(
    *,
    decision_time: datetime,
    membership_symbols: Iterable[str],
    previous_close_by_symbol: Mapping[str, float],
    raw_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
) -> CrossSectionalRankState:
    """Build one causal rank using the latest close completed by decision_time."""

    return cross_sectional_rank_states(
        decision_times=[decision_time],
        membership_symbols=membership_symbols,
        previous_close_by_symbol=previous_close_by_symbol,
        raw_minute_bars_by_symbol=raw_minute_bars_by_symbol,
    )[decision_time.isoformat()]


def cross_sectional_rank_states(
    *,
    decision_times: Iterable[datetime],
    membership_symbols: Iterable[str],
    previous_close_by_symbol: Mapping[str, float],
    raw_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
) -> dict[str, CrossSectionalRankState]:
    """Build many rank instants in one pass over the full membership bars."""

    decisions = sorted(set(decision_times))
    if not decisions:
        return {}
    if any(value.tzinfo is None for value in decisions):
        raise ValueError("rank decision time must be timezone-aware")
    symbols = _validated_membership_symbols(membership_symbols)
    extras = set(raw_minute_bars_by_symbol) - set(symbols)
    if extras:
        raise ValueError(f"rank bars contain nonmembership symbols: {sorted(extras)}")
    previous_extras = set(previous_close_by_symbol) - set(symbols)
    if previous_extras:
        raise ValueError(
            "rank previous closes contain nonmembership symbols: "
            f"{sorted(previous_extras)}"
        )

    with_bar = [0] * len(decisions)
    with_close = [0] * len(decisions)
    missing_close = [0] * len(decisions)
    missing_previous = [0] * len(decisions)
    rank_inputs: list[list[dict[str, object]]] = [
        [] for _value in decisions
    ]
    for symbol in symbols:
        frame = raw_minute_bars_by_symbol.get(symbol, pd.DataFrame())
        _validate_frame(frame, label=f"rank bars for {symbol}")
        if frame.empty:
            continue
        previous = _numeric_feature(previous_close_by_symbol.get(symbol))
        available_at = frame.index + pd.Timedelta(minutes=1)
        for offset, decision in enumerate(decisions):
            position = available_at.searchsorted(
                pd.Timestamp(decision), side="right"
            ) - 1
            if position < 0:
                continue
            with_bar[offset] += 1
            if "close" not in frame:
                missing_close[offset] += 1
                continue
            close = _numeric_feature(frame.iloc[position]["close"])
            if close is None or not math.isfinite(close) or close <= 0:
                missing_close[offset] += 1
                continue
            with_close[offset] += 1
            if previous is None or not math.isfinite(previous) or previous <= 0:
                missing_previous[offset] += 1
                continue
            gain = (close / previous - 1.0) * 100.0
            rank_inputs[offset].append(
                {
                    "symbol": symbol,
                    "latest_completed_bar_started_at": (
                        frame.index[position].isoformat()
                    ),
                    "latest_completed_close": close,
                    "previous_close": previous,
                    "percent_gain": gain,
                }
            )

    output: dict[str, CrossSectionalRankState] = {}
    for offset, decision in enumerate(decisions):
        ordered = sorted(
            rank_inputs[offset],
            key=lambda row: (-float(row["percent_gain"]), str(row["symbol"])),
        )
        complete = (
            missing_close[offset] == 0
            and missing_previous[offset] == 0
            and bool(ordered)
        )
        ranks = (
            {
                str(row["symbol"]): rank_offset + 1
                for rank_offset, row in enumerate(ordered)
            }
            if complete
            else {}
        )
        leader = ordered[0] if complete else None
        output[decision.isoformat()] = CrossSectionalRankState(
            identity_resolved_member_count=len(symbols),
            rank_members_with_completed_bar_count=with_bar[offset],
            rank_members_with_completed_close_count=with_close[offset],
            rank_members_missing_completed_close_count=missing_close[offset],
            rank_members_missing_previous_close_count=missing_previous[offset],
            rank_members_with_computable_gain_count=len(ordered),
            rank_members_without_completed_bar_count=(
                len(symbols) - with_bar[offset]
            ),
            rank_input_complete_for_members_with_completed_bars=complete,
            rank_input_ordered_sha256=_json_fingerprint(ordered),
            ranks=ranks,
            leader_symbol=str(leader["symbol"]) if leader else None,
            leader_percent_gain=(
                float(leader["percent_gain"]) if leader else None
            ),
        )
    return output


def _exact_bar(
    frame: pd.DataFrame,
    *,
    bar_started_at: datetime,
) -> pd.Series | None:
    _validate_frame(frame, label="candidate minute bars")
    if frame.empty or bar_started_at not in frame.index:
        return None
    row = frame.loc[bar_started_at]
    if isinstance(row, pd.DataFrame):
        raise ValueError("candidate minute bars repeat a timestamp")
    return row


def _cumulative_volume(
    frame: pd.DataFrame,
    *,
    through_bar_started_at: datetime,
) -> int | None:
    if "volume" not in frame:
        return None
    eligible = frame.loc[frame.index <= through_bar_started_at, "volume"]
    numeric = pd.to_numeric(eligible, errors="coerce")
    if numeric.isna().any() or (numeric < 0).any():
        return None
    return int(round(float(numeric.sum())))


def _rvol_at(series: pd.Series, bar_started_at: datetime) -> float | str | None:
    if not isinstance(series, pd.Series):
        raise ValueError("candidate RVOL curve must be a Series")
    if not series.empty:
        if series.index.tz is None:
            raise ValueError("candidate RVOL index must be timezone-aware")
        if series.index.has_duplicates:
            raise ValueError("candidate RVOL timestamps must be unique")
    if bar_started_at not in series.index:
        return None
    return _canonical_number(series.loc[bar_started_at])


def _float_asof(record: dict[str, object], *, activation: datetime) -> str | None:
    value = record.get("float_asof")
    if value is None:
        return None
    parsed = _aware_datetime(value, label="float as-of")
    if parsed > activation:
        raise ValueError("float evidence became available after candidate activation")
    return parsed.isoformat()


def disposition_from_snapshot_row(
    row: Mapping[str, object],
    *,
    profile: StrategyProfile,
) -> str:
    """Apply the frozen single-disposition precedence to one feature row."""

    if row.get("candidate_completed_bar_present") is not True:
        return "feature_state_unknown_fail_closed_missing_candidate_completed_bar"
    if any(
        row.get(key) is None
        for key in ("price", "percent_gain", "cumulative_volume")
    ) or _numeric_feature(row.get("exact_same_time_rvol")) is None:
        return "feature_state_unknown_fail_closed_missing_candidate_market_feature"
    if (
        row.get("rank_input_complete_for_members_with_completed_bars") is not True
        or row.get("top_gainer_rank") is None
    ):
        return "feature_state_unknown_fail_closed_missing_cross_sectional_rank"
    if (
        row.get("float_classification") == "unknown_fail_closed"
        or row.get("float_provider_status") == "provider_error"
    ):
        return "feature_state_unknown_fail_closed_float"
    if row.get("news_provider_status") != "success":
        return "feature_state_unknown_fail_closed_news_provider_error"

    price = _numeric_feature(row.get("price"))
    gain = _numeric_feature(row.get("percent_gain"))
    rvol = _numeric_feature(row.get("exact_same_time_rvol"))
    assert price is not None and gain is not None and rvol is not None
    if not profile.min_price <= price <= profile.max_price:
        return "feature_state_price_outside_range"
    if gain < profile.min_percent_gain:
        return "feature_state_gain_below_minimum"
    if rvol < profile.min_relative_volume:
        return "feature_state_rvol_below_minimum"
    if row.get("float_classification") == "fail":
        return "feature_state_float_at_or_above_limit"
    if row.get("float_classification") != "pass":
        return "feature_state_unknown_fail_closed_float"
    if row.get("has_provider_news_as_of") is True:
        return "feature_state_provider_news_present_unclassified"
    return "feature_state_provider_relative_no_news_unclassified"


def build_scanner_snapshot_rows(
    *,
    trading_date: date,
    profile: StrategyProfile,
    candidate_rows: list[dict[str, object]],
    float_records: list[dict[str, object]],
    news_events: list[dict[str, object]],
    news_statuses: list[dict[str, object]],
    membership_symbols: Iterable[str],
    previous_close_by_symbol: Mapping[str, float],
    rank_raw_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
    candidate_raw_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
    candidate_exact_rvol_by_symbol: Mapping[str, pd.Series],
) -> list[dict[str, object]]:
    """Materialize every candidate-minute feature decision without labels."""

    _validate_feature_only_profile(profile)
    symbols = _validated_membership_symbols(membership_symbols)
    activations = _candidate_activations(candidate_rows)
    if not set(activations).issubset(symbols):
        raise ValueError("market candidate is absent from identity membership")
    for symbol in activations:
        if rank_raw_minute_bars_by_symbol.get(symbol) is not (
            candidate_raw_minute_bars_by_symbol.get(symbol)
        ):
            raise ValueError(
                f"candidate {symbol} price and rank must share one raw-minute frame"
            )
    floats = {str(row.get("symbol") or ""): row for row in float_records}
    if len(floats) != len(float_records) or set(floats) != set(activations):
        raise ValueError("float records must decide every market candidate once")
    statuses = {str(row.get("symbol") or ""): row for row in news_statuses}
    if len(statuses) != len(news_statuses) or set(statuses) != set(activations):
        raise ValueError("news statuses must decide every market candidate once")
    for event in news_events:
        if str(event.get("symbol") or "") not in activations:
            raise ValueError("news event is not tied to a market candidate")
    for symbol, frame in rank_raw_minute_bars_by_symbol.items():
        _validate_intraday_frame_window(
            frame,
            trading_date=trading_date,
            start=profile.volume_feature_start,
            cutoff=profile.no_new_entries_after,
            label=f"rank raw-minute bars for {symbol}",
        )
    for symbol, frame in candidate_raw_minute_bars_by_symbol.items():
        _validate_intraday_frame_window(
            frame,
            trading_date=trading_date,
            start=profile.volume_feature_start,
            cutoff=profile.no_new_entries_after,
            label=f"candidate raw-minute bars for {symbol}",
        )
    for symbol, series in candidate_exact_rvol_by_symbol.items():
        if not isinstance(series, pd.Series):
            raise ValueError(f"candidate RVOL for {symbol} must be a Series")
        _validate_intraday_frame_window(
            pd.DataFrame(index=series.index),
            trading_date=trading_date,
            start=profile.volume_feature_start,
            cutoff=profile.no_new_entries_after,
            label=f"candidate exact RVOL for {symbol}",
        )

    cutoff = datetime.combine(trading_date, profile.no_new_entries_after, ET)
    all_decision_times = sorted(
        {
            _aware_datetime(value, label="candidate decision time")
            for value, _symbol in expected_candidate_decision_keys(
                candidate_rows,
                trading_date=trading_date,
                session_start=profile.session_start,
                cutoff=profile.no_new_entries_after,
            )
        }
    )
    rank_cache = cross_sectional_rank_states(
        decision_times=all_decision_times,
        membership_symbols=symbols,
        previous_close_by_symbol=previous_close_by_symbol,
        raw_minute_bars_by_symbol=rank_raw_minute_bars_by_symbol,
    )
    output: list[dict[str, object]] = []
    candidate_by_symbol = {
        str(row["symbol"]): row for row in candidate_rows
    }
    for symbol, activation in activations.items():
        source = candidate_by_symbol[symbol]
        source_previous = _numeric_feature(source.get("previous_close"))
        if source_previous is None or source_previous <= 0:
            raise ValueError(f"market candidate {symbol} lacks previous close")
        rank_previous = _numeric_feature(previous_close_by_symbol.get(symbol))
        if (
            rank_previous is None
            or not math.isclose(
                source_previous,
                rank_previous,
                rel_tol=CANDIDATE_PREVIOUS_CLOSE_REL_TOL,
                abs_tol=CANDIDATE_PREVIOUS_CLOSE_ABS_TOL,
            )
        ):
            raise ValueError(
                f"candidate {symbol} previous close disagrees with rank input"
            )
        minute_bars = candidate_raw_minute_bars_by_symbol.get(
            symbol, pd.DataFrame()
        )
        rvol_curve = candidate_exact_rvol_by_symbol.get(
            symbol, pd.Series(dtype=float)
        )
        float_record = floats[symbol]
        float_classification = str(
            float_record.get("float_classification") or ""
        )
        if float_classification not in {"pass", "fail", "unknown_fail_closed"}:
            raise ValueError(f"float record {symbol} has invalid classification")
        float_asof = _float_asof(float_record, activation=activation)
        status = statuses[symbol]
        provider_status = str(status.get("provider_status") or "")
        if provider_status not in {"success", "provider_error_fail_closed"}:
            raise ValueError(f"news status {symbol} has invalid provider status")
        symbol_news_events = [
            event
            for event in news_events
            if str(event.get("symbol") or "") == symbol
        ]
        if provider_status != "success" and symbol_news_events:
            raise ValueError(f"news provider error for {symbol} retained events")

        decision_time = activation
        while decision_time < cutoff:
            bar_started_at = decision_time - timedelta(minutes=1)
            bar = _exact_bar(minute_bars, bar_started_at=bar_started_at)
            completed = bar is not None
            price = (
                _numeric_feature(bar.get("close")) if bar is not None else None
            )
            if price is not None and (not math.isfinite(price) or price <= 0):
                price = None
            percent_gain = (
                (price / rank_previous - 1.0) * 100.0
                if price is not None
                else None
            )
            cumulative = (
                _cumulative_volume(
                    minute_bars,
                    through_bar_started_at=bar_started_at,
                )
                if completed
                else None
            )
            rvol = _rvol_at(rvol_curve, bar_started_at) if completed else None

            rank_key = decision_time.isoformat()
            rank = rank_cache[rank_key]
            projected = project_news_events_as_of(
                symbol_news_events,
                decision_time=decision_time,
                symbol=symbol,
            )
            first_news = (
                str(
                    min(
                        projected,
                        key=lambda event: _aware_datetime(
                            event.get("published_at"),
                            label="projected news publication",
                        ),
                    )["published_at"]
                )
                if projected
                else None
            )
            latest_news = (
                str(
                    max(
                        projected,
                        key=lambda event: _aware_datetime(
                            event.get("published_at"),
                            label="projected news publication",
                        ),
                    )["published_at"]
                )
                if projected
                else None
            )
            numeric_rvol = _numeric_feature(rvol)
            row: dict[str, object] = {
                "symbol": symbol,
                "activation_time": activation.isoformat(),
                "decision_time": decision_time.isoformat(),
                "required_source_bar_started_at": bar_started_at.isoformat(),
                "candidate_completed_bar_present": completed,
                "candidate_bar_available_at": (
                    decision_time.isoformat() if completed else None
                ),
                "price": price,
                "previous_close": rank_previous,
                "percent_gain": percent_gain,
                "cumulative_volume": cumulative,
                "exact_same_time_rvol": rvol,
                "price_pillar_pass": (
                    profile.min_price <= price <= profile.max_price
                    if price is not None
                    else None
                ),
                "gain_pillar_pass": (
                    percent_gain >= profile.min_percent_gain
                    if percent_gain is not None
                    else None
                ),
                "rvol_pillar_pass": (
                    numeric_rvol >= profile.min_relative_volume
                    if numeric_rvol is not None
                    else None
                ),
                "float_classification": float_classification,
                "float_pillar_pass": float_record.get("float_pillar_pass"),
                "estimated_float_shares": float_record.get(
                    "estimated_float_shares"
                ),
                "float_asof": float_asof,
                "float_method": float_record.get("method"),
                "float_provider_status": float_record.get("sec_status"),
                "news_provider_status": provider_status,
                "provider_news_event_count_as_of": len(projected),
                "has_provider_news_as_of": bool(projected),
                "provider_relative_no_news_as_of": (
                    provider_status == "success" and not projected
                ),
                "first_provider_news_published_at_as_of": first_news,
                "latest_provider_news_published_at_as_of": latest_news,
                **{
                    key: value
                    for key, value in asdict(rank).items()
                    if key not in {"ranks", "leader_symbol", "leader_percent_gain"}
                },
                "top_gainer_rank": rank.ranks.get(symbol),
                "rank_leader_symbol": rank.leader_symbol,
                "rank_leader_percent_gain": rank.leader_percent_gain,
            }
            row["disposition"] = disposition_from_snapshot_row(
                row,
                profile=profile,
            )
            if set(row) != SNAPSHOT_ROW_FIELDS:
                raise RuntimeError("scanner snapshot row schema drifted")
            output.append(row)
            decision_time += timedelta(minutes=1)
    return sorted(output, key=lambda row: (str(row["decision_time"]), str(row["symbol"])))


def ordered_snapshot_records_fingerprint(
    rows: Iterable[dict[str, object]],
) -> str:
    return _json_fingerprint(list(rows))


def build_source_hash_chain(
    source_hashes: Mapping[str, str],
) -> tuple[list[dict[str, str]], str]:
    if set(source_hashes) != set(_SOURCE_HASH_ORDER):
        missing = sorted(set(_SOURCE_HASH_ORDER) - set(source_hashes))
        extra = sorted(set(source_hashes) - set(_SOURCE_HASH_ORDER))
        raise ValueError(f"scanner source hashes mismatch; missing={missing}, extra={extra}")
    chain: list[dict[str, str]] = []
    previous = ""
    for name in _SOURCE_HASH_ORDER:
        source_sha = source_hashes[name]
        if not _is_lower_sha256(source_sha):
            raise ValueError(
                f"scanner source hash {name} is not lowercase SHA-256"
            )
        link = _json_fingerprint(
            {"name": name, "source_sha256": source_sha, "previous_link": previous}
        )
        chain.append(
            {
                "name": name,
                "source_sha256": source_sha,
                "previous_link_sha256": previous,
                "link_sha256": link,
            }
        )
        previous = link
    return chain, _json_fingerprint(chain)


def market_inputs_fingerprint(
    *,
    trading_date: date,
    profile: StrategyProfile,
    membership_symbols: Iterable[str],
    previous_close_by_symbol: Mapping[str, float],
    rank_raw_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
    candidate_raw_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
    candidate_exact_rvol_by_symbol: Mapping[str, pd.Series],
) -> str:
    _validate_feature_only_profile(profile)
    symbols = _validated_membership_symbols(membership_symbols)
    symbol_set = set(symbols)
    for label, values in (
        ("previous closes", previous_close_by_symbol),
        ("rank bars", rank_raw_minute_bars_by_symbol),
        ("candidate bars", candidate_raw_minute_bars_by_symbol),
        ("candidate RVOL", candidate_exact_rvol_by_symbol),
    ):
        extras = set(values) - symbol_set
        if extras:
            raise ValueError(f"fingerprinted {label} contain nonmembers: {sorted(extras)}")
    digest = hashlib.sha256()

    def emit(kind: str, value: object) -> None:
        digest.update(kind.encode("ascii"))
        digest.update(b"\t")
        digest.update(
            json.dumps(
                value,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        digest.update(b"\n")

    emit(
        "contract",
        {
            "artifact": CAUSAL_SCANNER_SNAPSHOT_ARTIFACT_ID,
            "trading_date": trading_date.isoformat(),
            "format": "streamed-canonical-market-inputs-v1",
        },
    )
    for symbol in symbols:
        emit("membership", {"symbol": symbol})
    for symbol in symbols:
        emit(
            "previous_close",
            {
                "symbol": symbol,
                "split_adjusted_previous_close": _canonical_number(
                    previous_close_by_symbol.get(symbol)
                ),
            },
        )

    def emit_frames(
        kind: str,
        frames: Mapping[str, pd.DataFrame],
        columns: tuple[str, ...],
    ) -> None:
        for symbol in sorted(frames):
            frame = frames[symbol]
            _validate_intraday_frame_window(
                frame,
                trading_date=trading_date,
                start=profile.volume_feature_start,
                cutoff=profile.no_new_entries_after,
                label=f"fingerprinted {kind} for {symbol}",
            )
            for timestamp, source in frame.iterrows():
                emit(
                    kind,
                    {
                        "symbol": symbol,
                        "bar_started_at": timestamp.isoformat(),
                        **{
                            column: _canonical_number(source.get(column))
                            for column in columns
                        },
                    },
                )
    emit_frames("rank_close_bar", rank_raw_minute_bars_by_symbol, ("close",))
    emit_frames(
        "candidate_bar",
        candidate_raw_minute_bars_by_symbol,
        ("close", "volume"),
    )
    for symbol in sorted(candidate_exact_rvol_by_symbol):
        series = candidate_exact_rvol_by_symbol[symbol]
        _validate_intraday_frame_window(
            pd.DataFrame(index=series.index),
            trading_date=trading_date,
            start=profile.volume_feature_start,
            cutoff=profile.no_new_entries_after,
            label=f"fingerprinted candidate RVOL for {symbol}",
        )
        for timestamp, value in series.items():
            emit(
                "candidate_exact_rvol",
                {
                    "symbol": symbol,
                    "bar_started_at": timestamp.isoformat(),
                    "exact_same_time_rvol": _canonical_number(value),
                },
            )
    return digest.hexdigest()


def build_causal_scanner_snapshot_artifacts(
    *,
    trading_date: date,
    profile: StrategyProfile,
    candidate_rows: list[dict[str, object]],
    membership_symbols: Iterable[str],
    rows: list[dict[str, object]],
    source_hashes: Mapping[str, str],
) -> tuple[dict[str, object], dict[str, object]]:
    _validate_feature_only_profile(profile)
    symbols = _validated_membership_symbols(membership_symbols)
    if not set(_candidate_activations(candidate_rows)).issubset(symbols):
        raise ValueError("scanner artifact candidate is absent from membership")
    ordered_rows = sorted(
        rows,
        key=lambda row: (str(row.get("decision_time")), str(row.get("symbol"))),
    )
    if rows != ordered_rows:
        raise ValueError("scanner snapshot rows are not in canonical order")
    chain, chain_hash = build_source_hash_chain(source_hashes)
    row_hash = ordered_snapshot_records_fingerprint(rows)
    payload: dict[str, object] = {
        "schema_version": 1,
        "artifact_id": CAUSAL_SCANNER_SNAPSHOT_ARTIFACT_ID,
        "trading_date": trading_date.isoformat(),
        "ordered_by": ["decision_time", "symbol"],
        "source_hash_chain_sha256": chain_hash,
        "candidate_count": len(candidate_rows),
        "identity_resolved_member_count": len(symbols),
        "row_count": len(rows),
        "ordered_records_sha256": row_hash,
        "rows": rows,
    }
    payload["content_sha256"] = _json_fingerprint(payload)
    expected_keys = expected_candidate_decision_keys(
        candidate_rows,
        trading_date=trading_date,
        session_start=profile.session_start,
        cutoff=profile.no_new_entries_after,
    )
    manifest: dict[str, object] = {
        "schema_version": 1,
        "artifact_id": CAUSAL_SCANNER_SNAPSHOT_ARTIFACT_ID,
        "trading_date": trading_date.isoformat(),
        "scanner_policy": causal_scanner_snapshot_v0_1_manifest(),
        "source_market_policy": causal_market_discovery_v0_2_manifest(),
        "source_news_policy": causal_news_v0_2_manifest(),
        "strategy_profile": strategy_profile_manifest(profile),
        "source_hash_chain": chain,
        "source_hash_chain_sha256": chain_hash,
        "summary": {
            "identity_resolved_member_count": len(symbols),
            "market_candidate_count": len(candidate_rows),
            "expected_candidate_minute_disposition_count": len(expected_keys),
            "candidate_minute_disposition_count": len(rows),
            "disposition_counts": dict(
                sorted(Counter(str(row.get("disposition")) for row in rows).items())
            ),
            "ordered_records_sha256": row_hash,
            "records_content_sha256": payload["content_sha256"],
        },
        "eligibility": {
            "complete_relative_to_identity_resolved_membership": True,
            "candidate_minute_dispositions_frozen": True,
            "universe_complete": False,
            "full_walk_forward_eligible": False,
            "policy_promotion_eligible": False,
        },
        "knowledge_policy": {
            "uses_benchmark_labels": False,
            "uses_retrospective_trade_outcomes": False,
            "future_session_extrema_used_as_snapshot_feature": False,
            "source_market_full_day_high_used_for_acquisition_only": True,
            "source_acquisition_prefilter_exposed_to_snapshot": False,
            "uses_future_news_publications": False,
            "contains_trades_setups_portfolio_or_pnl": False,
            "rank_threshold_or_top_n_selection_frozen": False,
        },
        "provider_error_boundary": {
            "upstream_float_loader_requires_complete_date": True,
            "upstream_news_loader_requires_complete_date": True,
            "fatal_provider_error_emits_partial_date": False,
            "row_fail_closed_scope": (
                "defensive_validated_per_symbol_status_only"
            ),
        },
        "source_replay_boundary": {
            "raw_reacquired_market_inputs_persisted": False,
            "reacquired_market_inputs_sha256_role": (
                "integrity_commitment_only"
            ),
            "independent_feature_recomputation_from_snapshot_artifact": False,
            "source_provider_replay_required_for_recomputation": True,
            "todo": (
                "persist_compact_compressed_canonical_source_input_bundle"
            ),
        },
        "files": {"scanner_records": "scanner-snapshot.json"},
    }
    manifest["content_sha256"] = _json_fingerprint(
        {key: value for key, value in manifest.items() if key != "content_sha256"}
    )
    validate_causal_scanner_snapshot(
        payload,
        manifest,
        candidate_rows=candidate_rows,
        profile=profile,
        expected_source_hashes=source_hashes,
    )
    return payload, manifest


def validate_causal_scanner_snapshot(
    payload: dict[str, object],
    manifest: dict[str, object],
    *,
    candidate_rows: list[dict[str, object]],
    profile: StrategyProfile,
    expected_source_hashes: Mapping[str, str],
) -> None:
    _validate_feature_only_profile(profile)
    if payload.get("schema_version") != 1 or manifest.get("schema_version") != 1:
        raise ValueError("unsupported causal scanner snapshot schema")
    if payload.get("artifact_id") != CAUSAL_SCANNER_SNAPSHOT_ARTIFACT_ID:
        raise ValueError("unsupported causal scanner snapshot payload")
    if manifest.get("artifact_id") != CAUSAL_SCANNER_SNAPSHOT_ARTIFACT_ID:
        raise ValueError("unsupported causal scanner snapshot manifest")
    if manifest.get("scanner_policy") != causal_scanner_snapshot_v0_1_manifest():
        raise ValueError("causal scanner snapshot policy mismatch")
    if manifest.get("source_market_policy") != causal_market_discovery_v0_2_manifest():
        raise ValueError("causal scanner market policy mismatch")
    if manifest.get("source_news_policy") != causal_news_v0_2_manifest():
        raise ValueError("causal scanner news policy mismatch")
    if manifest.get("strategy_profile") != strategy_profile_manifest(profile):
        raise ValueError("causal scanner strategy profile mismatch")
    if payload.get("trading_date") != manifest.get("trading_date"):
        raise ValueError("causal scanner trading date mismatch")
    if payload.get("ordered_by") != ["decision_time", "symbol"]:
        raise ValueError("causal scanner record order metadata mismatch")
    expected_manifest_hash = _json_fingerprint(
        {key: value for key, value in manifest.items() if key != "content_sha256"}
    )
    if manifest.get("content_sha256") != expected_manifest_hash:
        raise ValueError("causal scanner manifest fingerprint mismatch")
    claimed_payload_hash = payload.get("content_sha256")
    if claimed_payload_hash != _json_fingerprint(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    ):
        raise ValueError("causal scanner payload fingerprint mismatch")
    chain = manifest.get("source_hash_chain")
    if not isinstance(chain, list) or manifest.get(
        "source_hash_chain_sha256"
    ) != _json_fingerprint(chain):
        raise ValueError("causal scanner source hash chain mismatch")
    if payload.get("source_hash_chain_sha256") != manifest.get(
        "source_hash_chain_sha256"
    ):
        raise ValueError("causal scanner payload source chain mismatch")
    expected_chain, expected_chain_hash = build_source_hash_chain(
        expected_source_hashes
    )
    if chain != expected_chain or manifest.get(
        "source_hash_chain_sha256"
    ) != expected_chain_hash:
        raise ValueError("causal scanner source hash chain differs from sources")
    if [row.get("name") for row in chain if isinstance(row, dict)] != list(
        _SOURCE_HASH_ORDER
    ):
        raise ValueError("causal scanner source hash chain order mismatch")
    previous = ""
    for link in chain:
        if not isinstance(link, dict):
            raise ValueError("causal scanner source hash link is invalid")
        if not str(link.get("source_sha256") or "").strip():
            raise ValueError("causal scanner source hash link is blank")
        expected_link = _json_fingerprint(
            {
                "name": link.get("name"),
                "source_sha256": link.get("source_sha256"),
                "previous_link": previous,
            }
        )
        if link.get("previous_link_sha256") != previous or link.get(
            "link_sha256"
        ) != expected_link:
            raise ValueError("causal scanner source hash link mismatch")
        previous = expected_link

    rows = payload.get("rows")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("causal scanner rows are invalid")
    if payload.get("row_count") != len(rows):
        raise ValueError("causal scanner row count mismatch")
    if payload.get("ordered_records_sha256") != ordered_snapshot_records_fingerprint(rows):
        raise ValueError("causal scanner ordered record fingerprint mismatch")
    summary = manifest.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("causal scanner summary is invalid")
    if summary.get("ordered_records_sha256") != payload.get(
        "ordered_records_sha256"
    ) or summary.get("records_content_sha256") != claimed_payload_hash:
        raise ValueError("causal scanner summary fingerprint mismatch")
    if manifest.get("eligibility", {}).get(
        "complete_relative_to_identity_resolved_membership"
    ) is not True:
        raise ValueError("causal scanner snapshot is incomplete")
    if manifest.get("eligibility", {}).get("universe_complete") is not False:
        raise ValueError("causal scanner snapshot overclaims universe completeness")
    if manifest.get("eligibility", {}).get(
        "full_walk_forward_eligible"
    ) is not False or manifest.get("eligibility", {}).get(
        "policy_promotion_eligible"
    ) is not False:
        raise ValueError("causal scanner snapshot overclaims research eligibility")
    knowledge = manifest.get("knowledge_policy", {})
    if knowledge.get("uses_benchmark_labels") is not False or knowledge.get(
        "uses_retrospective_trade_outcomes"
    ) is not False:
        raise ValueError("causal scanner snapshot is not label-blind")
    if knowledge.get("uses_future_news_publications") is not False or knowledge.get(
        "contains_trades_setups_portfolio_or_pnl"
    ) is not False:
        raise ValueError("causal scanner snapshot crosses its decision boundary")
    if knowledge.get(
        "future_session_extrema_used_as_snapshot_feature"
    ) is not False or knowledge.get(
        "source_market_full_day_high_used_for_acquisition_only"
    ) is not True or knowledge.get(
        "source_acquisition_prefilter_exposed_to_snapshot"
    ) is not False:
        raise ValueError("causal scanner acquisition boundary is misstated")
    replay = manifest.get("source_replay_boundary", {})
    if replay != {
        "raw_reacquired_market_inputs_persisted": False,
        "reacquired_market_inputs_sha256_role": "integrity_commitment_only",
        "independent_feature_recomputation_from_snapshot_artifact": False,
        "source_provider_replay_required_for_recomputation": True,
        "todo": "persist_compact_compressed_canonical_source_input_bundle",
    }:
        raise ValueError("causal scanner source replay boundary is misstated")
    if manifest.get("provider_error_boundary") != {
        "upstream_float_loader_requires_complete_date": True,
        "upstream_news_loader_requires_complete_date": True,
        "fatal_provider_error_emits_partial_date": False,
        "row_fail_closed_scope": "defensive_validated_per_symbol_status_only",
    }:
        raise ValueError("causal scanner provider error boundary is misstated")

    trading_date = date.fromisoformat(str(payload.get("trading_date") or ""))
    expected = expected_candidate_decision_keys(
        candidate_rows,
        trading_date=trading_date,
        session_start=profile.session_start,
        cutoff=profile.no_new_entries_after,
    )
    activations = _candidate_activations(candidate_rows)
    candidates = {str(row["symbol"]): row for row in candidate_rows}
    observed = [
        (str(row.get("decision_time") or ""), str(row.get("symbol") or ""))
        for row in rows
    ]
    if observed != sorted(observed):
        raise ValueError("causal scanner rows are not in canonical order")
    if len(observed) != len(set(observed)):
        raise ValueError("causal scanner has duplicate candidate-minute disposition")
    if observed != expected:
        raise ValueError("causal scanner is missing a candidate-minute disposition")
    if summary.get("expected_candidate_minute_disposition_count") != len(expected):
        raise ValueError("causal scanner expected disposition count mismatch")
    if summary.get("candidate_minute_disposition_count") != len(rows):
        raise ValueError("causal scanner disposition count mismatch")
    if payload.get("candidate_count") != len(candidate_rows) or summary.get(
        "market_candidate_count"
    ) != len(candidate_rows):
        raise ValueError("causal scanner candidate count mismatch")
    if payload.get("identity_resolved_member_count") != summary.get(
        "identity_resolved_member_count"
    ):
        raise ValueError("causal scanner identity membership count mismatch")
    payload_identity_count = payload.get("identity_resolved_member_count")
    if (
        not isinstance(payload_identity_count, int)
        or isinstance(payload_identity_count, bool)
        or payload_identity_count < len(candidate_rows)
    ):
        raise ValueError("causal scanner identity count is below candidate count")
    expected_counts = dict(
        sorted(Counter(str(row.get("disposition")) for row in rows).items())
    )
    if summary.get("disposition_counts") != expected_counts:
        raise ValueError("causal scanner disposition summary mismatch")

    for row in rows:
        if set(row) != SNAPSHOT_ROW_FIELDS:
            raise ValueError("causal scanner row fields are invalid")
        symbol = str(row["symbol"])
        decision = _aware_datetime(row["decision_time"], label="scanner decision")
        activation = _aware_datetime(
            row["activation_time"],
            label="scanner activation",
        )
        if activation != activations[symbol] or decision < activation:
            raise ValueError("scanner activation is inconsistent with market source")
        started = _aware_datetime(
            row["required_source_bar_started_at"],
            label="scanner source bar start",
        )
        if decision - started != timedelta(minutes=1):
            raise ValueError("scanner decision did not wait for completed bar")
        available = row.get("candidate_bar_available_at")
        completed = row.get("candidate_completed_bar_present")
        if not isinstance(completed, bool):
            raise ValueError("scanner candidate completed-bar flag is invalid")
        if completed:
            if available != decision.isoformat():
                raise ValueError("scanner candidate bar availability mismatch")
        elif available is not None:
            raise ValueError("missing scanner bar has an availability timestamp")

        source_previous = _numeric_feature(
            candidates[symbol].get("previous_close")
        )
        previous_close = _numeric_feature(row.get("previous_close"))
        if (
            source_previous is None
            or previous_close is None
            or not math.isclose(
                source_previous,
                previous_close,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
        ):
            raise ValueError("scanner previous close is inconsistent with market source")
        price = _numeric_feature(row.get("price"))
        gain = _numeric_feature(row.get("percent_gain"))
        cumulative = row.get("cumulative_volume")
        rvol = _numeric_feature(row.get("exact_same_time_rvol"))
        if completed and price is not None:
            if not math.isfinite(price) or price <= 0:
                raise ValueError("scanner completed bar has an invalid price")
            expected_gain = (price / previous_close - 1.0) * 100.0
            if gain is None or not math.isclose(
                gain,
                expected_gain,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise ValueError("scanner percent gain is inconsistent with price")
        elif gain is not None:
            raise ValueError("scanner missing bar retained price or gain")
        if not completed and price is not None:
            raise ValueError("scanner missing bar retained a price")
        if cumulative is not None and (
            not isinstance(cumulative, int)
            or isinstance(cumulative, bool)
            or cumulative < 0
        ):
            raise ValueError("scanner cumulative volume is invalid")
        expected_price_pillar = (
            profile.min_price <= price <= profile.max_price
            if price is not None
            else None
        )
        expected_gain_pillar = (
            gain >= profile.min_percent_gain if gain is not None else None
        )
        expected_rvol_pillar = (
            rvol >= profile.min_relative_volume if rvol is not None else None
        )
        if not completed and any(
            row.get(field) is not None
            for field in (
                "price",
                "percent_gain",
                "cumulative_volume",
                "exact_same_time_rvol",
                "price_pillar_pass",
                "gain_pillar_pass",
                "rvol_pillar_pass",
            )
        ):
            raise ValueError("missing scanner bar retained market features")
        for field, expected_pillar in (
            ("price_pillar_pass", expected_price_pillar),
            ("gain_pillar_pass", expected_gain_pillar),
            ("rvol_pillar_pass", expected_rvol_pillar),
        ):
            if row.get(field) is not expected_pillar:
                raise ValueError(f"scanner {field} is inconsistent with its feature")

        float_classification = row.get("float_classification")
        expected_float_pillar = {
            "pass": True,
            "fail": False,
            "unknown_fail_closed": None,
        }.get(str(float_classification))
        if str(float_classification) not in {
            "pass",
            "fail",
            "unknown_fail_closed",
        } or row.get("float_pillar_pass") is not expected_float_pillar:
            raise ValueError("scanner float classification/pillar mismatch")
        if row.get("float_provider_status") == "provider_error" and (
            float_classification != "unknown_fail_closed"
        ):
            raise ValueError("scanner float provider error did not fail closed")
        if float_classification in {"pass", "fail"} and row.get("float_asof") is None:
            raise ValueError("known scanner float classification lacks an as-of")
        if not str(row.get("float_method") or "") or not str(
            row.get("float_provider_status") or ""
        ):
            raise ValueError("scanner float provenance is incomplete")
        identity_count = row.get("identity_resolved_member_count")
        if identity_count != payload.get("identity_resolved_member_count"):
            raise ValueError("scanner row identity membership count mismatch")
        with_bar = row.get("rank_members_with_completed_bar_count")
        without_bar = row.get("rank_members_without_completed_bar_count")
        with_close = row.get("rank_members_with_completed_close_count")
        missing_close = row.get("rank_members_missing_completed_close_count")
        missing_previous = row.get("rank_members_missing_previous_close_count")
        computable = row.get("rank_members_with_computable_gain_count")
        if not all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in (
                identity_count,
                with_bar,
                without_bar,
                with_close,
                missing_close,
                missing_previous,
                computable,
            )
        ):
            raise ValueError("scanner rank coverage counts are invalid")
        if with_bar + without_bar != identity_count:
            raise ValueError("scanner rank membership coverage mismatch")
        if with_close + missing_close != with_bar:
            raise ValueError("scanner rank completed-close coverage mismatch")
        if computable + missing_previous != with_close:
            raise ValueError("scanner rank previous-close coverage mismatch")
        complete = row.get("rank_input_complete_for_members_with_completed_bars")
        if complete is not (missing_close == 0 and missing_previous == 0 and computable > 0):
            raise ValueError("scanner rank completeness flag mismatch")
        rank = row.get("top_gainer_rank")
        if rank is not None and (
            not isinstance(rank, int)
            or isinstance(rank, bool)
            or not 1 <= rank <= computable
        ):
            raise ValueError("scanner candidate rank is invalid")
        if not _is_lower_sha256(row.get("rank_input_ordered_sha256")):
            raise ValueError("scanner rank input fingerprint is missing")
        leader_symbol = row.get("rank_leader_symbol")
        leader_gain = _numeric_feature(row.get("rank_leader_percent_gain"))
        if complete:
            if rank is None:
                raise ValueError("complete scanner rank omitted candidate rank")
            if not isinstance(leader_symbol, str) or not leader_symbol or leader_gain is None:
                raise ValueError("complete scanner rank omitted its leader")
            if gain is not None and leader_gain + 1e-12 < gain:
                raise ValueError("scanner rank leader gain is below candidate gain")
            if rank == 1 and (
                leader_symbol != symbol
                or gain is None
                or not math.isclose(
                    leader_gain,
                    gain,
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                )
            ):
                raise ValueError("scanner rank-one candidate disagrees with leader")
        elif rank is not None or leader_symbol is not None or leader_gain is not None:
            raise ValueError("incomplete scanner rank retained a rank or leader")

        news_status = row.get("news_provider_status")
        news_count = row.get("provider_news_event_count_as_of")
        if news_status not in {"success", "provider_error_fail_closed"}:
            raise ValueError("scanner news provider status is invalid")
        if (
            not isinstance(news_count, int)
            or isinstance(news_count, bool)
            or news_count < 0
        ):
            raise ValueError("scanner news event count is invalid")
        has_news = row.get("has_provider_news_as_of")
        no_news = row.get("provider_relative_no_news_as_of")
        if not isinstance(has_news, bool) or not isinstance(no_news, bool):
            raise ValueError("scanner news booleans are invalid")
        if has_news is not (news_count > 0):
            raise ValueError("scanner news count/presence mismatch")
        if no_news is not (news_status == "success" and news_count == 0):
            raise ValueError("scanner provider-relative no-news mismatch")
        first_news_raw = row.get("first_provider_news_published_at_as_of")
        latest_news_raw = row.get("latest_provider_news_published_at_as_of")
        if news_count == 0:
            if first_news_raw is not None or latest_news_raw is not None:
                raise ValueError("zero-news scanner row retained news timestamps")
        else:
            if first_news_raw is None or latest_news_raw is None:
                raise ValueError("scanner news-present row lacks timestamps")
            first_news = _aware_datetime(
                first_news_raw,
                label="scanner first news publication",
            )
            latest_news = _aware_datetime(
                latest_news_raw,
                label="scanner latest news publication",
            )
            if first_news > latest_news or latest_news > decision:
                raise ValueError("scanner news timestamp ordering is invalid")
            if news_count == 1 and first_news != latest_news:
                raise ValueError("single-news scanner timestamps disagree")
        if news_status != "success" and (
            news_count != 0 or has_news or no_news
        ):
            raise ValueError("scanner news provider error did not fail closed")
        for key in (
            "first_provider_news_published_at_as_of",
            "latest_provider_news_published_at_as_of",
        ):
            published = row.get(key)
            if published is not None and _aware_datetime(
                published, label="scanner news publication"
            ) > decision:
                raise ValueError("future news escaped scanner as-of projection")
        float_asof = row.get("float_asof")
        if float_asof is not None and _aware_datetime(
            float_asof, label="scanner float as-of"
        ) > activation:
            raise ValueError("post-activation float evidence escaped scanner decision")
        if row.get("disposition") != disposition_from_snapshot_row(
            row,
            profile=profile,
        ):
            raise ValueError("causal scanner disposition is inconsistent with features")


def load_causal_scanner_snapshot(
    date_root: str | Path,
    *,
    candidate_rows: list[dict[str, object]],
    profile: StrategyProfile,
    expected_source_hashes: Mapping[str, str],
) -> tuple[list[dict[str, object]], dict[str, object], dict[str, object]]:
    root = Path(date_root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("causal scanner manifest must be an object")
    relative = manifest.get("files", {}).get("scanner_records")
    if not isinstance(relative, str) or not relative:
        raise ValueError("causal scanner manifest lacks records")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("causal scanner records path escapes artifact")
    payload = json.loads((root / path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("causal scanner payload must be an object")
    validate_causal_scanner_snapshot(
        payload,
        manifest,
        candidate_rows=candidate_rows,
        profile=profile,
        expected_source_hashes=expected_source_hashes,
    )
    return list(payload["rows"]), payload, manifest
