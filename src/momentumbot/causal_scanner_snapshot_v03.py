"""Split-consistent causal scanner snapshot v0.3.

This module is an additive validator/replay repair.  The registered v0.2
implementation remains untouched.  Actual price and cumulative volume are
read from raw candidate bars; gain and cross-sectional rank are read from the
same split-adjusted all-membership frame and split-adjusted previous close.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from datetime import date
import json
import math
from pathlib import Path
from typing import Iterable, Mapping, Protocol

import pandas as pd

from . import causal_scanner_snapshot_v02 as _parent
from .causal_market_discovery_v03 import causal_market_discovery_v0_3_manifest
from .models import StrategyProfile


CAUSAL_SCANNER_SNAPSHOT_V0_3_POLICY_ID = "causal-scanner-snapshot-v0.3"
CAUSAL_SCANNER_SNAPSHOT_V0_3_ARTIFACT_ID = CAUSAL_SCANNER_SNAPSHOT_V0_3_POLICY_ID
NORMALIZED_RANK_MINUTE_ADJUSTMENT = _parent.NORMALIZED_RANK_MINUTE_ADJUSTMENT
CANDIDATE_VALUE_REL_TOL = _parent.CANDIDATE_PREVIOUS_CLOSE_REL_TOL
CANDIDATE_VALUE_ABS_TOL = _parent.CANDIDATE_PREVIOUS_CLOSE_ABS_TOL
SOURCE_INPUT_ARTIFACT_ID = "causal-scanner-source-inputs-v0.2"

SNAPSHOT_ROW_FIELDS = _parent.SNAPSHOT_ROW_FIELDS
SESSION_TIMEZONE = _parent.SESSION_TIMEZONE
UPSTREAM_MARKET_ACQUISITION_TAIL_END = _parent.UPSTREAM_MARKET_ACQUISITION_TAIL_END


class ScannerSourceInputs(Protocol):
    trading_date: date
    membership_symbols: tuple[str, ...]
    candidate_symbols: tuple[str, ...]
    previous_close_by_symbol: Mapping[str, float | None]
    rank_split_minute_bars_by_symbol: Mapping[str, pd.DataFrame]
    candidate_raw_minute_bars_by_symbol: Mapping[str, pd.DataFrame]
    candidate_exact_rvol_by_symbol: Mapping[str, pd.Series]
    source_hashes: Mapping[str, str]


def causal_scanner_snapshot_v0_3_manifest() -> dict[str, object]:
    parent = _parent.causal_scanner_snapshot_v0_2_manifest()
    payload = {key: deepcopy(value) for key, value in parent.items() if key != "fingerprint"}
    # v0.2 compared same-basis candidate/rank closes.  That tolerance has no
    # meaning once the candidate close is raw and the rank close is split.
    payload.pop("candidate_rank_frame_close_match_tolerance", None)
    payload.update(
        {
            "policy_id": CAUSAL_SCANNER_SNAPSHOT_V0_3_POLICY_ID,
            "source_float_policy_id": "causal-sec-float-v0.2",
            "supersedes_policy_id": parent["policy_id"],
            "supersedes_policy_fingerprint": parent["fingerprint"],
            "candidate_raw_split_timestamp_match_rule": (
                "exact_timestamp_index_equality_required_without_close_or_volume_"
                "equality_between_distinct_adjustment_bases"
            ),
            "semantic_validation_rule": (
                "raw_displayed_price_matches_exact_raw_candidate_close_while_"
                "percent_gain_matches_exact_split_target_close_over_split_previous_close"
            ),
            "rank_semantic_validation_rule": (
                "candidate_gain_and_cross_sectional_rank_share_the_same_split_adjusted_"
                "target_minute_frame_and_split_adjusted_previous_close"
            ),
            "canonical_source_input_artifact_id": SOURCE_INPUT_ARTIFACT_ID,
            "source_input_persistence_rule": (
                "versioned_canonical_raw_price_volume_split_gain_rank_tape_is_required_"
                "for_provider_free_semantic_revalidation"
            ),
        }
    )
    return {**payload, "fingerprint": _parent._json_fingerprint(payload)}


def _finite_positive(value: object, *, label: str) -> float:
    number = _parent._numeric_feature(value)
    if number is None or not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be finite and positive")
    return number


def _same_number(observed: object, expected: float, *, label: str) -> None:
    number = _parent._numeric_feature(observed)
    if (
        number is None
        or not math.isfinite(number)
        or not math.isclose(
            number,
            expected,
            rel_tol=CANDIDATE_VALUE_REL_TOL,
            abs_tol=CANDIDATE_VALUE_ABS_TOL,
        )
    ):
        raise ValueError(f"{label} mismatch")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key is forbidden: {key}")
        output[key] = value
    return output


def _load_json_object(path: Path) -> dict[str, object]:
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=_reject_json_constant,
        object_pairs_hook=_reject_duplicate_json_keys,
    )
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required at {path}")
    return payload


def _candidate_map(candidate_rows: Iterable[Mapping[str, object]]) -> dict[str, Mapping[str, object]]:
    output: dict[str, Mapping[str, object]] = {}
    for row in candidate_rows:
        symbol = str(row.get("symbol") or "")
        if not symbol or symbol in output:
            raise ValueError("scanner candidates require unique nonblank symbols")
        output[symbol] = row
    return output


def _validate_basis_inputs(
    *,
    membership_symbols: Iterable[str],
    candidate_rows: Iterable[Mapping[str, object]],
    previous_close_by_symbol: Mapping[str, float | None],
    rank_split_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
    candidate_raw_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
) -> tuple[list[str], dict[str, Mapping[str, object]]]:
    symbols = _parent._validated_membership_symbols(membership_symbols)
    candidates = _candidate_map(candidate_rows)
    if not set(candidates).issubset(symbols):
        raise ValueError("scanner candidate is absent from membership")
    if set(previous_close_by_symbol) - set(symbols):
        raise ValueError("split previous closes contain nonmembership symbols")
    for symbol, value in previous_close_by_symbol.items():
        if value is not None:
            _finite_positive(value, label=f"split previous close for {symbol}")
    for symbol, candidate in candidates.items():
        source_previous = _finite_positive(
            candidate.get("previous_close"),
            label=f"candidate split previous close for {symbol}",
        )
        rank_previous = _finite_positive(
            previous_close_by_symbol.get(symbol),
            label=f"rank split previous close for {symbol}",
        )
        if not math.isclose(
            source_previous,
            rank_previous,
            rel_tol=CANDIDATE_VALUE_REL_TOL,
            abs_tol=CANDIDATE_VALUE_ABS_TOL,
        ):
            raise ValueError(f"candidate {symbol} split previous close mismatch")
    _parent.validate_normalized_rank_candidate_coverage(
        membership_symbols=symbols,
        normalized_rank_frames=rank_split_minute_bars_by_symbol,
        raw_candidate_frames=candidate_raw_minute_bars_by_symbol,
    )
    return symbols, candidates


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
    rank_split_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
    candidate_raw_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
    candidate_exact_rvol_by_symbol: Mapping[str, pd.Series],
) -> list[dict[str, object]]:
    """Build rows with an explicit, non-switchable raw/split basis."""

    symbols, _ = _validate_basis_inputs(
        membership_symbols=membership_symbols,
        candidate_rows=candidate_rows,
        previous_close_by_symbol=previous_close_by_symbol,
        rank_split_minute_bars_by_symbol=rank_split_minute_bars_by_symbol,
        candidate_raw_minute_bars_by_symbol=candidate_raw_minute_bars_by_symbol,
    )
    rows = _parent.build_scanner_snapshot_rows(
        trading_date=trading_date,
        profile=profile,
        candidate_rows=candidate_rows,
        float_records=float_records,
        news_events=news_events,
        news_statuses=news_statuses,
        membership_symbols=symbols,
        previous_close_by_symbol=previous_close_by_symbol,
        rank_raw_minute_bars_by_symbol=rank_split_minute_bars_by_symbol,
        candidate_raw_minute_bars_by_symbol=candidate_raw_minute_bars_by_symbol,
        candidate_exact_rvol_by_symbol=candidate_exact_rvol_by_symbol,
        rank_minute_adjustment=NORMALIZED_RANK_MINUTE_ADJUSTMENT,
    )
    validate_split_consistent_market_semantics(
        rows,
        candidate_rows=candidate_rows,
        profile=profile,
        membership_symbols=symbols,
        previous_close_by_symbol=previous_close_by_symbol,
        rank_split_minute_bars_by_symbol=rank_split_minute_bars_by_symbol,
        candidate_raw_minute_bars_by_symbol=candidate_raw_minute_bars_by_symbol,
    )
    return rows


def validate_split_consistent_market_semantics(
    rows: Iterable[Mapping[str, object]],
    *,
    candidate_rows: list[dict[str, object]],
    profile: StrategyProfile,
    membership_symbols: Iterable[str],
    previous_close_by_symbol: Mapping[str, float | None],
    rank_split_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
    candidate_raw_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
) -> None:
    """Independently recompute raw price/volume and split gain/rank."""

    symbols, candidates = _validate_basis_inputs(
        membership_symbols=membership_symbols,
        candidate_rows=candidate_rows,
        previous_close_by_symbol=previous_close_by_symbol,
        rank_split_minute_bars_by_symbol=rank_split_minute_bars_by_symbol,
        candidate_raw_minute_bars_by_symbol=candidate_raw_minute_bars_by_symbol,
    )
    materialized = [dict(row) for row in rows]
    decisions = sorted(
        {
            _parent._aware_datetime(row.get("decision_time"), label="scanner decision")
            for row in materialized
        }
    )
    rank_states = _parent.cross_sectional_rank_states(
        decision_times=decisions,
        membership_symbols=symbols,
        previous_close_by_symbol=previous_close_by_symbol,  # type: ignore[arg-type]
        raw_minute_bars_by_symbol=rank_split_minute_bars_by_symbol,
    )
    for row in materialized:
        symbol = str(row.get("symbol") or "")
        if symbol not in candidates:
            raise ValueError("scanner row symbol is not a candidate")
        started = _parent._aware_datetime(
            row.get("required_source_bar_started_at"),
            label="scanner source bar start",
        )
        decision = _parent._aware_datetime(row.get("decision_time"), label="scanner decision")
        raw_bar = _parent._exact_bar(
            candidate_raw_minute_bars_by_symbol.get(symbol, pd.DataFrame()),
            bar_started_at=started,
        )
        split_bar = _parent._exact_bar(
            rank_split_minute_bars_by_symbol.get(symbol, pd.DataFrame()),
            bar_started_at=started,
        )
        completed = raw_bar is not None
        if completed is not (split_bar is not None):
            raise ValueError("raw/split candidate completed-bar coverage mismatch")
        if row.get("candidate_completed_bar_present") is not completed:
            raise ValueError("scanner completed-bar flag disagrees with canonical inputs")
        if completed:
            assert raw_bar is not None and split_bar is not None
            raw_price = _finite_positive(raw_bar.get("close"), label="raw candidate close")
            split_price = _finite_positive(split_bar.get("close"), label="split target close")
            previous = _finite_positive(
                previous_close_by_symbol.get(symbol),
                label="split previous close",
            )
            expected_gain = (split_price / previous - 1.0) * 100.0
            _same_number(row.get("price"), raw_price, label="scanner raw displayed price")
            _same_number(row.get("percent_gain"), expected_gain, label="scanner split-consistent gain")
            expected_cumulative = _parent._cumulative_volume(
                candidate_raw_minute_bars_by_symbol[symbol],
                through_bar_started_at=started,
            )
            if row.get("cumulative_volume") != expected_cumulative:
                raise ValueError("scanner cumulative volume disagrees with raw candidate bars")
            expected_price_pillar = profile.min_price <= raw_price <= profile.max_price
            expected_gain_pillar = expected_gain >= profile.min_percent_gain
        else:
            if any(
                row.get(key) is not None
                for key in (
                    "price",
                    "percent_gain",
                    "cumulative_volume",
                    "price_pillar_pass",
                    "gain_pillar_pass",
                )
            ):
                raise ValueError("missing raw/split bar retained scanner market features")
            expected_price_pillar = None
            expected_gain_pillar = None
        if row.get("price_pillar_pass") is not expected_price_pillar:
            raise ValueError("scanner raw price pillar mismatch")
        if row.get("gain_pillar_pass") is not expected_gain_pillar:
            raise ValueError("scanner split gain pillar mismatch")

        state = rank_states[decision.isoformat()]
        state_values = asdict(state)
        for key, value in state_values.items():
            if key in {"ranks", "leader_symbol", "leader_percent_gain"}:
                continue
            if row.get(key) != value:
                raise ValueError(f"scanner split rank state mismatch for {key}")
        if row.get("top_gainer_rank") != state.ranks.get(symbol):
            raise ValueError("scanner top-gainer rank disagrees with split frame")
        if row.get("rank_leader_symbol") != state.leader_symbol:
            raise ValueError("scanner rank leader disagrees with split frame")
        if state.leader_percent_gain is None:
            if row.get("rank_leader_percent_gain") is not None:
                raise ValueError("scanner retained a leader gain for incomplete split rank")
        else:
            _same_number(
                row.get("rank_leader_percent_gain"),
                state.leader_percent_gain,
                label="scanner split rank leader gain",
            )
        if row.get("disposition") != _parent.disposition_from_snapshot_row(
            row, profile=profile
        ):
            raise ValueError("scanner disposition disagrees with raw/split features")


def _source_replay_boundary() -> dict[str, object]:
    return {
        "raw_provider_responses_persisted": False,
        "canonical_source_inputs_persisted": True,
        "canonical_source_input_artifact_id": SOURCE_INPUT_ARTIFACT_ID,
        "independent_feature_recomputation_from_canonical_inputs": True,
        "source_provider_replay_required_for_recomputation": False,
    }


def build_causal_scanner_snapshot_artifacts(
    *,
    trading_date: date,
    profile: StrategyProfile,
    candidate_rows: list[dict[str, object]],
    membership_symbols: Iterable[str],
    rows: list[dict[str, object]],
    source_hashes: Mapping[str, str],
    previous_close_by_symbol: Mapping[str, float | None],
    rank_split_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
    candidate_raw_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
) -> tuple[dict[str, object], dict[str, object]]:
    symbols = _parent._validated_membership_symbols(membership_symbols)
    ordered = sorted(rows, key=lambda row: (str(row.get("decision_time")), str(row.get("symbol"))))
    if rows != ordered:
        raise ValueError("scanner snapshot rows are not in canonical order")
    chain, chain_hash = _parent.build_source_hash_chain(source_hashes)
    row_hash = _parent.ordered_snapshot_records_fingerprint(rows)
    payload: dict[str, object] = {
        "schema_version": 2,
        "artifact_id": CAUSAL_SCANNER_SNAPSHOT_V0_3_ARTIFACT_ID,
        "trading_date": trading_date.isoformat(),
        "ordered_by": ["decision_time", "symbol"],
        "source_hash_chain_sha256": chain_hash,
        "candidate_count": len(candidate_rows),
        "identity_resolved_member_count": len(symbols),
        "row_count": len(rows),
        "ordered_records_sha256": row_hash,
        "rows": rows,
    }
    payload["content_sha256"] = _parent._json_fingerprint(payload)
    expected_keys = _parent.expected_candidate_decision_keys(
        candidate_rows,
        trading_date=trading_date,
        session_start=profile.session_start,
        cutoff=profile.no_new_entries_after,
    )
    manifest: dict[str, object] = {
        "schema_version": 2,
        "artifact_id": CAUSAL_SCANNER_SNAPSHOT_V0_3_ARTIFACT_ID,
        "trading_date": trading_date.isoformat(),
        "scanner_policy": causal_scanner_snapshot_v0_3_manifest(),
        "source_market_policy": causal_market_discovery_v0_3_manifest(),
        "source_news_policy": _parent.causal_news_v0_2_manifest(),
        "strategy_profile": _parent.strategy_profile_manifest(profile),
        "source_hash_chain": chain,
        "source_hash_chain_sha256": chain_hash,
        "summary": {
            "identity_resolved_member_count": len(symbols),
            "market_candidate_count": len(candidate_rows),
            "expected_candidate_minute_disposition_count": len(expected_keys),
            "candidate_minute_disposition_count": len(rows),
            "disposition_counts": dict(sorted(Counter(str(row.get("disposition")) for row in rows).items())),
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
            "row_fail_closed_scope": "defensive_validated_per_symbol_status_only",
        },
        "source_replay_boundary": _source_replay_boundary(),
        "files": {"scanner_records": "scanner-snapshot.json"},
    }
    manifest["content_sha256"] = _parent._json_fingerprint(manifest)
    validate_causal_scanner_snapshot(
        payload,
        manifest,
        candidate_rows=candidate_rows,
        profile=profile,
        expected_source_hashes=source_hashes,
        membership_symbols=symbols,
        previous_close_by_symbol=previous_close_by_symbol,
        rank_split_minute_bars_by_symbol=rank_split_minute_bars_by_symbol,
        candidate_raw_minute_bars_by_symbol=candidate_raw_minute_bars_by_symbol,
    )
    return payload, manifest


def _legacy_projection(
    payload: Mapping[str, object],
    manifest: Mapping[str, object],
    *,
    profile: StrategyProfile,
    rank_split_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
) -> tuple[dict[str, object], dict[str, object]]:
    """Project only for reuse of the parent's exhaustive structural validator."""

    projected_payload = deepcopy(dict(payload))
    projected_payload["schema_version"] = 1
    projected_rows = projected_payload.get("rows")
    assert isinstance(projected_rows, list)
    for row in projected_rows:
        assert isinstance(row, dict)
        if row.get("candidate_completed_bar_present") is True:
            symbol = str(row["symbol"])
            started = _parent._aware_datetime(row["required_source_bar_started_at"], label="source bar")
            bar = _parent._exact_bar(rank_split_minute_bars_by_symbol[symbol], bar_started_at=started)
            split_price = _finite_positive(bar.get("close") if bar is not None else None, label="split target close")
            row["price"] = split_price
            row["price_pillar_pass"] = profile.min_price <= split_price <= profile.max_price
            row["disposition"] = _parent.disposition_from_snapshot_row(row, profile=profile)
    projected_payload["ordered_records_sha256"] = _parent.ordered_snapshot_records_fingerprint(projected_rows)
    projected_payload["content_sha256"] = _parent._json_fingerprint(
        {key: value for key, value in projected_payload.items() if key != "content_sha256"}
    )
    projected_manifest = deepcopy(dict(manifest))
    projected_manifest["schema_version"] = 1
    summary = projected_manifest["summary"]
    assert isinstance(summary, dict)
    summary["disposition_counts"] = dict(
        sorted(Counter(str(row.get("disposition")) for row in projected_rows).items())
    )
    summary["ordered_records_sha256"] = projected_payload["ordered_records_sha256"]
    summary["records_content_sha256"] = projected_payload["content_sha256"]
    projected_manifest["source_replay_boundary"] = {
        "raw_reacquired_market_inputs_persisted": False,
        "reacquired_market_inputs_sha256_role": "integrity_commitment_only",
        "independent_feature_recomputation_from_snapshot_artifact": False,
        "source_provider_replay_required_for_recomputation": True,
        "todo": "persist_compact_compressed_canonical_source_input_bundle",
    }
    projected_manifest["content_sha256"] = _parent._json_fingerprint(
        {key: value for key, value in projected_manifest.items() if key != "content_sha256"}
    )
    return projected_payload, projected_manifest


def validate_causal_scanner_snapshot(
    payload: dict[str, object],
    manifest: dict[str, object],
    *,
    candidate_rows: list[dict[str, object]],
    profile: StrategyProfile,
    expected_source_hashes: Mapping[str, str],
    membership_symbols: Iterable[str],
    previous_close_by_symbol: Mapping[str, float | None],
    rank_split_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
    candidate_raw_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
) -> None:
    if payload.get("schema_version") != 2 or manifest.get("schema_version") != 2:
        raise ValueError("unsupported causal scanner snapshot v0.3 schema")
    if payload.get("artifact_id") != CAUSAL_SCANNER_SNAPSHOT_V0_3_ARTIFACT_ID or manifest.get(
        "artifact_id"
    ) != CAUSAL_SCANNER_SNAPSHOT_V0_3_ARTIFACT_ID:
        raise ValueError("unsupported causal scanner snapshot v0.3 artifact")
    if manifest.get("scanner_policy") != causal_scanner_snapshot_v0_3_manifest():
        raise ValueError("causal scanner v0.3 policy mismatch")
    if manifest.get("source_market_policy") != causal_market_discovery_v0_3_manifest():
        raise ValueError("causal scanner v0.3 market policy mismatch")
    if manifest.get("source_replay_boundary") != _source_replay_boundary():
        raise ValueError("causal scanner v0.3 replay boundary mismatch")
    if manifest.get("content_sha256") != _parent._json_fingerprint(
        {key: value for key, value in manifest.items() if key != "content_sha256"}
    ):
        raise ValueError("causal scanner v0.3 manifest fingerprint mismatch")
    if payload.get("content_sha256") != _parent._json_fingerprint(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    ):
        raise ValueError("causal scanner v0.3 payload fingerprint mismatch")

    projected_payload, projected_manifest = _legacy_projection(
        payload,
        manifest,
        profile=profile,
        rank_split_minute_bars_by_symbol=rank_split_minute_bars_by_symbol,
    )
    _parent.validate_causal_scanner_snapshot(
        projected_payload,
        projected_manifest,
        candidate_rows=candidate_rows,
        profile=profile,
        expected_source_hashes=expected_source_hashes,
        expected_scanner_policy=causal_scanner_snapshot_v0_3_manifest(),
        expected_market_policy=causal_market_discovery_v0_3_manifest(),
        expected_artifact_id=CAUSAL_SCANNER_SNAPSHOT_V0_3_ARTIFACT_ID,
    )
    rows = payload.get("rows")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("causal scanner v0.3 rows are invalid")
    validate_split_consistent_market_semantics(
        rows,
        candidate_rows=candidate_rows,
        profile=profile,
        membership_symbols=membership_symbols,
        previous_close_by_symbol=previous_close_by_symbol,
        rank_split_minute_bars_by_symbol=rank_split_minute_bars_by_symbol,
        candidate_raw_minute_bars_by_symbol=candidate_raw_minute_bars_by_symbol,
    )


def load_causal_scanner_snapshot(
    date_root: str | Path,
    *,
    candidate_rows: list[dict[str, object]],
    profile: StrategyProfile,
    source_inputs: ScannerSourceInputs,
) -> tuple[list[dict[str, object]], dict[str, object], dict[str, object]]:
    root = Path(date_root)
    manifest = _load_json_object(root / "manifest.json")
    relative = manifest.get("files", {}).get("scanner_records")
    if not isinstance(relative, str) or not relative:
        raise ValueError("causal scanner v0.3 manifest lacks records")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("causal scanner v0.3 records path escapes artifact")
    payload = _load_json_object(root / path)
    if payload.get("trading_date") != source_inputs.trading_date.isoformat():
        raise ValueError("scanner snapshot and canonical input dates disagree")
    if set(str(row.get("symbol") or "") for row in candidate_rows) != set(
        source_inputs.candidate_symbols
    ):
        raise ValueError("scanner snapshot and canonical input candidates disagree")
    validate_causal_scanner_snapshot(
        payload,
        manifest,
        candidate_rows=candidate_rows,
        profile=profile,
        expected_source_hashes=source_inputs.source_hashes,
        membership_symbols=source_inputs.membership_symbols,
        previous_close_by_symbol=source_inputs.previous_close_by_symbol,
        rank_split_minute_bars_by_symbol=source_inputs.rank_split_minute_bars_by_symbol,
        candidate_raw_minute_bars_by_symbol=source_inputs.candidate_raw_minute_bars_by_symbol,
    )
    return list(payload["rows"]), payload, manifest


# Explicitly re-export unchanged acquisition constants/helpers for the v0.4 builder.
trim_scanner_bar_frame = _parent.trim_scanner_bar_frame
trim_scanner_rvol_series = _parent.trim_scanner_rvol_series
cross_sectional_rank_states = _parent.cross_sectional_rank_states
build_source_hash_chain = _parent.build_source_hash_chain
ordered_snapshot_records_fingerprint = _parent.ordered_snapshot_records_fingerprint
RANK_ACQUISITION_PROVIDER = _parent.RANK_ACQUISITION_PROVIDER
RANK_HISTORICAL_FEED = _parent.RANK_HISTORICAL_FEED
RANK_PREVIOUS_CLOSE_TIMEFRAME = _parent.RANK_PREVIOUS_CLOSE_TIMEFRAME
RANK_PREVIOUS_CLOSE_ADJUSTMENT = _parent.RANK_PREVIOUS_CLOSE_ADJUSTMENT
RANK_PRIOR_CLOSE_LOOKBACK_CALENDAR_DAYS = _parent.RANK_PRIOR_CLOSE_LOOKBACK_CALENDAR_DAYS
RANK_MINUTE_TIMEFRAME = _parent.RANK_MINUTE_TIMEFRAME
RANK_ACQUISITION_ASOF_RULE = _parent.RANK_ACQUISITION_ASOF_RULE


def market_inputs_fingerprint(
    *,
    trading_date: date,
    profile: StrategyProfile,
    membership_symbols: Iterable[str],
    previous_close_by_symbol: Mapping[str, float | None],
    rank_split_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
    candidate_raw_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
    candidate_exact_rvol_by_symbol: Mapping[str, pd.Series],
) -> str:
    """Fingerprint the v0.2 canonical sidecar format without a provider call."""

    del profile
    from .scanner_source_inputs_v03 import market_inputs_fingerprint as fingerprint

    return fingerprint(
        trading_date=trading_date,
        membership_symbols=membership_symbols,
        previous_close_by_symbol=previous_close_by_symbol,
        rank_split_minute_bars_by_symbol=rank_split_minute_bars_by_symbol,
        candidate_raw_minute_bars_by_symbol=candidate_raw_minute_bars_by_symbol,
        candidate_exact_rvol_by_symbol=candidate_exact_rvol_by_symbol,
    )
