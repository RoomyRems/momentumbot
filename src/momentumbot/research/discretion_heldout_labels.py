from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Mapping

from momentumbot.research.discretion_heldout_panel import (
    HUMAN_ACTION_STATES,
    REGISTERED_DATES,
    canonical_fingerprint,
)


SCHEMA_VERSION = 1
ARTIFACT_ID = "ross-discretion-heldout-labels-v0.1"
ARTIFACT_TYPE = "retrospective_account_scoped_behavior_labels"
ACCOUNT_KEYS = ("main_account", "small_account")
SESSION_ACTIVITY_STATES = (
    "reported_trade_day",
    "reported_no_completed_trade_day",
    "coverage_incomplete",
)
TRADE_COMPLETION_STATES = (
    "completed_trade",
    "no_trade",
    "attempted_no_fill",
    "unknown",
)
IDENTITY_RESOLUTION_STATES = (
    "frozen_candidate_match",
    "externally_corroborated",
    "internally_corroborated",
    "unresolved",
)
DEFAULT_ACTION_STATE = "not_mentioned_or_unobservable"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _require_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _require_sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return value


def _validate_source_batch(payload: Mapping[str, object]) -> None:
    batch = _require_mapping(payload.get("source_batch"), "source_batch")
    if batch.get("record_count") != 300:
        raise ValueError("source batch must retain the supplied 300-record count")
    _require_sha(batch.get("file_sha256"), "source_batch.file_sha256")
    if batch.get("raw_batch_committed_to_repository") is not False:
        raise ValueError("raw transcript batch must not be committed")
    if batch.get("allowed_in_runtime") is not False:
        raise ValueError("raw transcripts cannot enter runtime")
    if batch.get("transcript_text_assumed_error_free") is not False:
        raise ValueError("transcript fallibility must remain explicit")


def _validate_account_label(
    value: object,
    *,
    field: str,
    source_ids: set[str],
    date_source_ids: set[str],
) -> None:
    label = _require_mapping(value, field)
    state = label.get("state")
    if state not in HUMAN_ACTION_STATES:
        raise ValueError(f"{field}.state is not registered")
    if state in {DEFAULT_ACTION_STATE, "source_unavailable"}:
        raise ValueError(f"{field} cannot redundantly override the frozen default")
    completion = label.get("trade_completion")
    if completion not in TRADE_COMPLETION_STATES:
        raise ValueError(f"{field}.trade_completion is invalid")
    if state == "participated" and completion != "completed_trade":
        raise ValueError(f"{field} participation requires a completed trade")
    if state == "explicitly_skipped_or_rejected" and completion != "no_trade":
        raise ValueError(f"{field} skip requires no_trade")
    if state == "discussed_but_action_unclear" and completion not in {
        "attempted_no_fill",
        "unknown",
    }:
        raise ValueError(f"{field} unclear action has inconsistent completion")
    evidence = label.get("source_ids")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError(f"{field}.source_ids must be non-empty")
    if len(evidence) != len(set(evidence)):
        raise ValueError(f"{field}.source_ids contains duplicates")
    if any(item not in source_ids for item in evidence):
        raise ValueError(f"{field} cites an unknown source")
    if any(item not in date_source_ids for item in evidence):
        raise ValueError(f"{field} cites a source outside the trading date")
    summary = label.get("evidence_summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError(f"{field}.evidence_summary must be non-empty")


def validate_discretion_heldout_labels(
    payload: Mapping[str, object],
    *,
    runtime_candidate_activations: Mapping[str, Mapping[str, str]] | None = None,
) -> None:
    """Validate frozen labels created only after the label-blind artifacts.

    Candidate labels are sparse by design. Every unlisted candidate expands to
    ``not_mentioned_or_unobservable`` independently for each account; it never
    becomes an inferred skip merely because a recap says no trades were taken.
    """

    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported held-out label schema")
    if payload.get("artifact_id") != ARTIFACT_ID:
        raise ValueError("unexpected held-out label artifact")
    if payload.get("artifact_type") != ARTIFACT_TYPE:
        raise ValueError("unexpected held-out label artifact type")
    if payload.get("label_status") != "frozen_retrospective_evidence":
        raise ValueError("label artifact must be frozen retrospective evidence")
    if payload.get("runtime_strategy_effect") != "none":
        raise ValueError("retrospective labels cannot affect runtime")
    for field in (
        "policy_promotion_eligible",
        "technical_rule_retuning_allowed",
        "selection_threshold_fitting_allowed",
        "overall_imitation_score_allowed",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must be false")

    claimed = _require_sha(payload.get("content_sha256"), "content_sha256")
    projection = {key: value for key, value in payload.items() if key != "content_sha256"}
    if claimed != canonical_fingerprint(projection):
        raise ValueError("held-out label content fingerprint mismatch")

    registration = _require_mapping(payload.get("registration"), "registration")
    if registration.get("contract_id") != "ross-discretion-heldout-panel-v0.1":
        raise ValueError("labels do not bind the registered panel")
    _require_sha(
        registration.get("contract_content_sha256"),
        "registration.contract_content_sha256",
    )
    if registration.get("labels_created_after_runtime_freeze") is not True:
        raise ValueError("labels must be created after runtime freeze")

    frozen_runtime = _require_mapping(payload.get("frozen_runtime"), "frozen_runtime")
    for name in ("scanner_runtime", "micro_runtime", "shadow_runtime"):
        item = _require_mapping(frozen_runtime.get(name), f"frozen_runtime.{name}")
        _require_sha(item.get("content_sha256"), f"frozen_runtime.{name}.content_sha256")
        if item.get("labels_loaded_during_generation") is not False:
            raise ValueError(f"frozen_runtime.{name} must remain label-blind")

    _validate_source_batch(payload)
    label_policy = _require_mapping(payload.get("label_policy"), "label_policy")
    if label_policy.get("action_states") != list(HUMAN_ACTION_STATES):
        raise ValueError("action states differ from registration")
    if label_policy.get("default_unlisted_candidate_state") != DEFAULT_ACTION_STATE:
        raise ValueError("unlisted candidate default must remain unknown")
    if label_policy.get("no_trade_session_converts_unmentioned_to_skip") is not False:
        raise ValueError("no-trade sessions cannot relabel unmentioned candidates")
    if label_policy.get("accounts_merged") is not False:
        raise ValueError("account labels must remain separate")

    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError("sources must be a non-empty list")
    source_ids: set[str] = set()
    source_dates: dict[str, set[str]] = {}
    for index, source_value in enumerate(raw_sources):
        source = _require_mapping(source_value, f"sources[{index}]")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("source_id must be non-empty")
        if source_id in source_ids:
            raise ValueError("source_id must be unique")
        source_ids.add(source_id)
        _require_sha(source.get("caption_utf8_sha256"), f"sources[{index}].caption_utf8_sha256")
        if source.get("caption_status") != "OK":
            raise ValueError("only available caption sources may be cited")
        dates = source.get("trading_dates")
        if not isinstance(dates, list) or not dates:
            raise ValueError("source trading_dates must be non-empty")
        if any(item not in REGISTERED_DATES for item in dates):
            raise ValueError("source cites an unregistered trading date")
        source_dates[source_id] = set(dates)
        if source.get("evidence_timing_quality") != "retrospective_sequence_only":
            raise ValueError("caption sources must remain retrospective sequence evidence")

    corrections = payload.get("transcription_corrections")
    if not isinstance(corrections, list):
        raise ValueError("transcription_corrections must be a list")
    correction_ids: set[str] = set()
    for index, correction_value in enumerate(corrections):
        correction = _require_mapping(
            correction_value, f"transcription_corrections[{index}]"
        )
        correction_id = correction.get("correction_id")
        if not isinstance(correction_id, str) or not correction_id:
            raise ValueError("correction_id must be non-empty")
        if correction_id in correction_ids:
            raise ValueError("correction_id must be unique")
        correction_ids.add(correction_id)
        if correction.get("resolution_status") not in IDENTITY_RESOLUTION_STATES:
            raise ValueError("transcription correction has invalid resolution status")
        if correction.get("silent_rewrite_allowed") is not False:
            raise ValueError("transcription corrections must remain explicit")

    date_results = _require_mapping(payload.get("date_results"), "date_results")
    if set(date_results) != set(REGISTERED_DATES):
        raise ValueError("label dates differ from registered panel")

    for trading_date in REGISTERED_DATES:
        result = _require_mapping(date_results.get(trading_date), f"date_results.{trading_date}")
        date_source_ids_raw = result.get("source_ids")
        if not isinstance(date_source_ids_raw, list) or not date_source_ids_raw:
            raise ValueError(f"{trading_date} must cite at least one source")
        date_source_ids = set(date_source_ids_raw)
        if len(date_source_ids) != len(date_source_ids_raw):
            raise ValueError(f"{trading_date} source IDs contain duplicates")
        if any(item not in source_ids for item in date_source_ids):
            raise ValueError(f"{trading_date} cites an unknown source")
        if any(trading_date not in source_dates[item] for item in date_source_ids):
            raise ValueError(f"{trading_date} cites a source without date coverage")

        candidate_symbols = result.get("candidate_symbols")
        if not isinstance(candidate_symbols, list):
            raise ValueError(f"{trading_date}.candidate_symbols must be a list")
        if candidate_symbols != sorted(set(candidate_symbols)):
            raise ValueError(f"{trading_date}.candidate_symbols must be sorted and unique")
        if result.get("candidate_count") != len(candidate_symbols):
            raise ValueError(f"{trading_date} candidate count mismatch")
        activations = _require_mapping(
            result.get("candidate_activations"),
            f"{trading_date}.candidate_activations",
        )
        if set(activations) != set(candidate_symbols):
            raise ValueError(f"{trading_date} candidate activations mismatch")
        _require_sha(
            result.get("candidate_activations_sha256"),
            f"{trading_date}.candidate_activations_sha256",
        )
        expected_activation_hash = canonical_fingerprint(
            {"trading_date": trading_date, "candidate_activations": dict(activations)}
        )
        if result.get("candidate_activations_sha256") != expected_activation_hash:
            raise ValueError(f"{trading_date} candidate activation hash mismatch")
        if runtime_candidate_activations is not None:
            expected = runtime_candidate_activations.get(trading_date)
            if expected is None or dict(expected) != dict(activations):
                raise ValueError(f"{trading_date} differs from frozen runtime candidates")

        session = _require_mapping(
            result.get("account_session_evidence"),
            f"{trading_date}.account_session_evidence",
        )
        if set(session) != set(ACCOUNT_KEYS):
            raise ValueError(f"{trading_date} must keep both account sessions")
        for account in ACCOUNT_KEYS:
            account_session = _require_mapping(
                session.get(account), f"{trading_date}.{account} session"
            )
            if account_session.get("activity_state") not in SESSION_ACTIVITY_STATES:
                raise ValueError(f"{trading_date}.{account} session state is invalid")
            evidence = account_session.get("source_ids")
            if not isinstance(evidence, list) or not evidence:
                raise ValueError(f"{trading_date}.{account} session needs evidence")
            if any(item not in date_source_ids for item in evidence):
                raise ValueError(f"{trading_date}.{account} session source mismatch")

        explicit = result.get("explicit_candidate_labels")
        if not isinstance(explicit, list):
            raise ValueError(f"{trading_date}.explicit_candidate_labels must be a list")
        explicit_symbols: set[str] = set()
        for index, row_value in enumerate(explicit):
            row = _require_mapping(
                row_value, f"{trading_date}.explicit_candidate_labels[{index}]"
            )
            symbol = row.get("symbol")
            if symbol not in candidate_symbols:
                raise ValueError(f"{trading_date} labels a noncandidate as a candidate")
            if symbol in explicit_symbols:
                raise ValueError(f"{trading_date} candidate label symbol is duplicated")
            explicit_symbols.add(str(symbol))
            accounts = {key for key in ACCOUNT_KEYS if key in row}
            if not accounts:
                raise ValueError(f"{trading_date}.{symbol} needs an account label")
            unknown_keys = set(row) - {"symbol", *ACCOUNT_KEYS}
            if unknown_keys:
                raise ValueError(f"{trading_date}.{symbol} has unknown label keys")
            for account in accounts:
                _validate_account_label(
                    row[account],
                    field=f"{trading_date}.{symbol}.{account}",
                    source_ids=source_ids,
                    date_source_ids=date_source_ids,
                )
        if result.get("explicit_candidate_symbol_count") != len(explicit_symbols):
            raise ValueError(f"{trading_date} explicit candidate count mismatch")

        off_candidate = result.get("observed_off_candidate_actions")
        if not isinstance(off_candidate, list):
            raise ValueError(f"{trading_date}.observed_off_candidate_actions must be a list")
        seen_off: set[str] = set()
        for index, row_value in enumerate(off_candidate):
            row = _require_mapping(
                row_value, f"{trading_date}.observed_off_candidate_actions[{index}]"
            )
            symbol = row.get("canonical_symbol")
            if not isinstance(symbol, str) or not symbol:
                raise ValueError("off-candidate canonical_symbol must be non-empty")
            if symbol in candidate_symbols:
                raise ValueError(f"{trading_date}.{symbol} is not off-candidate")
            if symbol in seen_off:
                raise ValueError(f"{trading_date}.{symbol} off-candidate row is duplicated")
            seen_off.add(symbol)
            if row.get("identity_resolution_status") not in IDENTITY_RESOLUTION_STATES:
                raise ValueError("off-candidate identity status is invalid")
            accounts = {key for key in ACCOUNT_KEYS if key in row}
            if not accounts:
                raise ValueError("off-candidate row needs an account label")
            for account in accounts:
                _validate_account_label(
                    row[account],
                    field=f"{trading_date}.{symbol}.{account}",
                    source_ids=source_ids,
                    date_source_ids=date_source_ids,
                )


def load_discretion_heldout_labels(
    path: str | Path,
    *,
    runtime_audit_path: str | Path | None = None,
) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("held-out label root must be an object")
    runtime_candidates = None
    if runtime_audit_path is not None:
        audit = json.loads(Path(runtime_audit_path).read_text(encoding="utf-8"))
        runtime_candidates = {
            trading_date: dict(result["candidate_activations"])
            for trading_date, result in audit["date_results"].items()
        }
    validate_discretion_heldout_labels(
        payload,
        runtime_candidate_activations=runtime_candidates,
    )
    return payload


def expand_candidate_labels(
    payload: Mapping[str, object],
    trading_date: str,
) -> dict[str, dict[str, str]]:
    """Expand sparse explicit evidence without inferring skips."""

    date_results = _require_mapping(payload.get("date_results"), "date_results")
    result = _require_mapping(date_results.get(trading_date), trading_date)
    symbols = result.get("candidate_symbols")
    if not isinstance(symbols, list):
        raise ValueError("candidate_symbols must be a list")
    expanded = {
        str(symbol): {account: DEFAULT_ACTION_STATE for account in ACCOUNT_KEYS}
        for symbol in symbols
    }
    explicit = result.get("explicit_candidate_labels")
    if not isinstance(explicit, list):
        raise ValueError("explicit_candidate_labels must be a list")
    for row_value in explicit:
        row = _require_mapping(row_value, "candidate label")
        symbol = str(row["symbol"])
        for account in ACCOUNT_KEYS:
            if account in row:
                label = _require_mapping(row[account], f"{symbol}.{account}")
                expanded[symbol][account] = str(label["state"])
    return expanded


def summarize_action_states(payload: Mapping[str, object]) -> dict[str, dict[str, int]]:
    counts = {account: Counter() for account in ACCOUNT_KEYS}
    for trading_date in REGISTERED_DATES:
        expanded = expand_candidate_labels(payload, trading_date)
        for account in ACCOUNT_KEYS:
            counts[account].update(row[account] for row in expanded.values())
    return {
        account: {state: counts[account].get(state, 0) for state in HUMAN_ACTION_STATES}
        for account in ACCOUNT_KEYS
    }
