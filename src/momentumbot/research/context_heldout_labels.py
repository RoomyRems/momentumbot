from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Mapping

from momentumbot.research.context_heldout_panel import (
    CONTRACT_ID,
    REGISTERED_DATES,
    canonical_fingerprint,
)
from momentumbot.research.context_semantic_shadow import (
    ARTIFACT_ID as SEMANTIC_ARTIFACT_ID,
    validate_semantic_date_payload,
    validate_semantic_root_manifest,
)
from momentumbot.research.discretion_heldout_panel import HUMAN_ACTION_STATES


SCHEMA_VERSION = 1
ARTIFACT_ID = "ross-context-heldout-labels-v0.1"
ARTIFACT_TYPE = "retrospective_account_scoped_context_labels"
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
    "internally_corroborated",
    "externally_corroborated",
    "unresolved",
)
DEFAULT_ACTION_STATE = "not_mentioned_or_unobservable"

REGISTRATION_FILE_SHA256 = (
    "25123571f5fc79c7b89de31668448a4f01bb6f0ab4aee765c5cd4020f875cf1a"
)
REGISTRATION_CONTENT_SHA256 = (
    "d227792368b3bff5c3c2365cacd204c11b7991daeb557efba450c22f076d8898"
)
RUNTIME_ZIP_SHA256 = (
    "a29186eb092752cfafc031360cacf348bea5e607cb19ce326ddaff2ddfedac1a"
)
RUNTIME_CONTENT_SHA256 = (
    "3567619bfb6b7b2c177d02cc69f15423bf605663519017a6638b0394e4153702"
)
SNAPSHOT_RUNTIME_CONTENT_SHA256 = (
    "6dcc6f25ddb73e63b5f9c714e0c890ab954b15b099e7ba3a71ef948f9760939f"
)
SEMANTIC_MANIFEST_CONTENT_SHA256 = (
    "9b3be7a17f29e638b0e1da14b4d050762503bab17c74c3f97e62b99489f25cd4"
)
SEMANTIC_CHECKPOINT_TREE_SHA = "0c899fb80203c13fc4e5b59b758f1690ca892a33"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return value


def _validate_account_label(
    value: object,
    *,
    field: str,
    source_ids: set[str],
    date_source_ids: set[str],
) -> None:
    label = _mapping(value, field)
    state = label.get("state")
    if state not in HUMAN_ACTION_STATES:
        raise ValueError(f"{field}.state is not registered")
    if state in {DEFAULT_ACTION_STATE, "source_unavailable"}:
        raise ValueError(f"{field} cannot override the conservative default")
    completion = label.get("trade_completion")
    if completion not in TRADE_COMPLETION_STATES:
        raise ValueError(f"{field}.trade_completion is invalid")
    if state == "participated" and completion != "completed_trade":
        raise ValueError(f"{field} participation requires a completed trade")
    if state == "explicitly_skipped_or_rejected" and completion != "no_trade":
        raise ValueError(f"{field} rejection requires no_trade")
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


def validate_context_heldout_labels(
    payload: Mapping[str, object],
    *,
    semantic_candidates: Mapping[str, set[str]] | None = None,
) -> None:
    """Validate the post-freeze source inventory and sparse account labels."""

    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported context label schema")
    if payload.get("artifact_id") != ARTIFACT_ID:
        raise ValueError("unexpected context label artifact")
    if payload.get("artifact_type") != ARTIFACT_TYPE:
        raise ValueError("unexpected context label artifact type")
    if payload.get("label_status") != "frozen_retrospective_evidence":
        raise ValueError("context labels must be frozen retrospective evidence")
    if payload.get("runtime_strategy_effect") != "none":
        raise ValueError("retrospective context labels cannot affect runtime")
    for field in (
        "policy_promotion_eligible",
        "technical_rule_retuning_allowed",
        "selection_threshold_fitting_allowed",
        "aggregate_score_allowed",
        "overall_imitation_score_allowed",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must be false")

    claimed = _sha(payload.get("content_sha256"), "content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if claimed != canonical_fingerprint(unsigned):
        raise ValueError("context label content fingerprint mismatch")

    registration = _mapping(payload.get("registration"), "registration")
    if registration.get("contract_id") != CONTRACT_ID:
        raise ValueError("context labels do not bind the registered panel")
    if registration.get("contract_file_sha256") != REGISTRATION_FILE_SHA256:
        raise ValueError("context label registration file changed")
    if registration.get("contract_content_sha256") != REGISTRATION_CONTENT_SHA256:
        raise ValueError("context label registration content changed")
    if registration.get("dates_replaced_after_source_review") is not False:
        raise ValueError("registered dates cannot be replaced")

    parents = _mapping(payload.get("frozen_parents"), "frozen_parents")
    runtime = _mapping(parents.get("deterministic_runtime"), "deterministic_runtime")
    if runtime.get("zip_sha256") != RUNTIME_ZIP_SHA256:
        raise ValueError("deterministic runtime ZIP parent changed")
    if runtime.get("runtime_manifest_content_sha256") != RUNTIME_CONTENT_SHA256:
        raise ValueError("deterministic runtime manifest parent changed")
    if runtime.get("snapshot_runtime_content_sha256") != SNAPSHOT_RUNTIME_CONTENT_SHA256:
        raise ValueError("snapshot runtime parent changed")
    if runtime.get("labels_loaded_during_generation") is not False:
        raise ValueError("deterministic runtime was not label-blind")
    semantic = _mapping(parents.get("semantic_shadow"), "semantic_shadow")
    if semantic.get("artifact_id") != SEMANTIC_ARTIFACT_ID:
        raise ValueError("semantic artifact parent changed")
    if semantic.get("manifest_content_sha256") != SEMANTIC_MANIFEST_CONTENT_SHA256:
        raise ValueError("semantic manifest parent changed")
    if semantic.get("checkpoint_tree_sha") != SEMANTIC_CHECKPOINT_TREE_SHA:
        raise ValueError("semantic checkpoint tree changed")
    if semantic.get("retrospective_inventory_opened_before_freeze") is not False:
        raise ValueError("semantic checkpoint did not precede inventory")

    archive = _mapping(payload.get("source_archive"), "source_archive")
    files = archive.get("files")
    if not isinstance(files, list) or len(files) != 8:
        raise ValueError("source archive must retain all eight supplied files")
    file_ids: set[str] = set()
    record_total = 0
    for index, value in enumerate(files):
        item = _mapping(value, f"source_archive.files[{index}]")
        file_id = item.get("file_id")
        if not isinstance(file_id, str) or not file_id or file_id in file_ids:
            raise ValueError("source archive file IDs must be unique")
        file_ids.add(file_id)
        _sha(item.get("file_sha256"), f"source_archive.files[{index}].file_sha256")
        count = item.get("record_count")
        if not isinstance(count, int) or count <= 0:
            raise ValueError("source archive record counts must be positive")
        record_total += count
    if archive.get("file_count") != 8 or archive.get("record_count") != record_total:
        raise ValueError("source archive totals do not recompute")
    if record_total != 2292:
        raise ValueError("source archive must retain all 2,292 supplied records")
    for field in (
        "raw_archive_committed_to_repository",
        "allowed_in_runtime",
        "transcript_text_assumed_error_free",
    ):
        if archive.get(field) is not False:
            raise ValueError(f"source_archive.{field} must be false")

    sources = payload.get("sources")
    if not isinstance(sources, list) or len(sources) != 14:
        raise ValueError("current context panel must retain exactly 14 source records")
    source_ids: set[str] = set()
    source_dates: dict[str, set[str]] = {}
    for index, value in enumerate(sources):
        source = _mapping(value, f"sources[{index}]")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id or source_id in source_ids:
            raise ValueError("source IDs must be unique")
        source_ids.add(source_id)
        if source.get("archive_file_id") not in file_ids:
            raise ValueError("source references an unknown archive file")
        if not isinstance(source.get("batch_record_index"), int):
            raise ValueError("source batch_record_index must be an integer")
        _sha(source.get("caption_utf8_sha256"), "caption_utf8_sha256")
        if source.get("caption_status") != "OK":
            raise ValueError("only available caption sources may be cited")
        if "caption_text" in source or "captions" in source:
            raise ValueError("raw caption text must not be committed")
        dates = source.get("trading_dates")
        if not isinstance(dates, list) or not dates:
            raise ValueError("source trading_dates must be non-empty")
        if any(item not in REGISTERED_DATES for item in dates):
            raise ValueError("source cites an unregistered trading date")
        source_dates[source_id] = set(dates)
        if source.get("evidence_timing_quality") != "retrospective_sequence_only":
            raise ValueError("caption timing must remain retrospective sequence evidence")

    excluded = payload.get("excluded_source_records")
    if not isinstance(excluded, list) or not excluded:
        raise ValueError("source-date exclusions must be retained")
    excluded_ids: set[str] = set()
    for index, value in enumerate(excluded):
        row = _mapping(value, f"excluded_source_records[{index}]")
        source_id = row.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("excluded source_id must be non-empty")
        excluded_ids.add(source_id)
        if source_id in source_ids:
            raise ValueError("excluded sources cannot also be panel sources")
        if row.get("used_for_labels") is not False:
            raise ValueError("excluded source cannot be used for labels")
    if "youtube:CA8i4Rc2bUY" not in excluded_ids:
        raise ValueError("the delayed July 23 recap exclusion must be explicit")

    corrections = payload.get("transcription_corrections")
    if not isinstance(corrections, list):
        raise ValueError("transcription_corrections must be a list")
    correction_ids: set[str] = set()
    for index, value in enumerate(corrections):
        row = _mapping(value, f"transcription_corrections[{index}]")
        correction_id = row.get("correction_id")
        if not isinstance(correction_id, str) or not correction_id:
            raise ValueError("correction_id must be non-empty")
        if correction_id in correction_ids:
            raise ValueError("correction_id must be unique")
        correction_ids.add(correction_id)
        if row.get("source_id") not in source_ids:
            raise ValueError("correction cites an unknown source")
        if row.get("resolution_status") not in IDENTITY_RESOLUTION_STATES:
            raise ValueError("correction resolution status is invalid")
        if row.get("silent_rewrite_allowed") is not False:
            raise ValueError("transcription corrections must remain explicit")

    label_policy = _mapping(payload.get("label_policy"), "label_policy")
    if label_policy.get("action_states") != list(HUMAN_ACTION_STATES):
        raise ValueError("action states differ from registration")
    if label_policy.get("default_unlisted_candidate_state") != DEFAULT_ACTION_STATE:
        raise ValueError("unlisted candidates must remain unknown")
    if label_policy.get("no_trade_session_converts_unmentioned_to_skip") is not False:
        raise ValueError("no-trade sessions cannot infer candidate skips")
    if label_policy.get("accounts_merged") is not False:
        raise ValueError("account labels must remain separate")

    date_results = _mapping(payload.get("date_results"), "date_results")
    if set(date_results) != set(REGISTERED_DATES):
        raise ValueError("label dates differ from the registered panel")
    for trading_date in REGISTERED_DATES:
        result = _mapping(date_results.get(trading_date), f"date_results.{trading_date}")
        raw_date_sources = result.get("source_ids")
        if not isinstance(raw_date_sources, list) or not raw_date_sources:
            raise ValueError(f"{trading_date} must cite at least one source")
        date_source_ids = set(raw_date_sources)
        if len(date_source_ids) != len(raw_date_sources):
            raise ValueError(f"{trading_date} source IDs contain duplicates")
        if any(item not in source_ids for item in date_source_ids):
            raise ValueError(f"{trading_date} cites an unknown source")
        if any(trading_date not in source_dates[item] for item in date_source_ids):
            raise ValueError(f"{trading_date} cites a source without date coverage")

        symbols = result.get("candidate_symbols")
        if not isinstance(symbols, list) or symbols != sorted(set(symbols)):
            raise ValueError(f"{trading_date} candidates must be sorted and unique")
        if result.get("candidate_count") != len(symbols):
            raise ValueError(f"{trading_date} candidate count mismatch")
        _sha(result.get("candidate_symbols_sha256"), "candidate_symbols_sha256")
        expected_hash = canonical_fingerprint(
            {"trading_date": trading_date, "candidate_symbols": symbols}
        )
        if result.get("candidate_symbols_sha256") != expected_hash:
            raise ValueError(f"{trading_date} candidate symbol hash mismatch")
        if semantic_candidates is not None and semantic_candidates.get(trading_date) != set(symbols):
            raise ValueError(f"{trading_date} differs from the frozen semantic candidates")

        sessions = _mapping(result.get("account_session_evidence"), "account_session_evidence")
        if set(sessions) != set(ACCOUNT_KEYS):
            raise ValueError(f"{trading_date} must retain both account sessions")
        for account in ACCOUNT_KEYS:
            session = _mapping(sessions.get(account), f"{trading_date}.{account}.session")
            if session.get("activity_state") not in SESSION_ACTIVITY_STATES:
                raise ValueError(f"{trading_date}.{account} session state is invalid")
            evidence = session.get("source_ids")
            if not isinstance(evidence, list) or not evidence:
                raise ValueError(f"{trading_date}.{account} session needs evidence")
            if any(item not in date_source_ids for item in evidence):
                raise ValueError(f"{trading_date}.{account} session source mismatch")

        explicit = result.get("explicit_candidate_labels")
        if not isinstance(explicit, list):
            raise ValueError("explicit_candidate_labels must be a list")
        seen_symbols: set[str] = set()
        for index, value in enumerate(explicit):
            row = _mapping(value, f"{trading_date}.explicit_candidate_labels[{index}]")
            symbol = row.get("symbol")
            if symbol not in symbols or symbol in seen_symbols:
                raise ValueError(f"{trading_date} candidate label is invalid or duplicated")
            seen_symbols.add(str(symbol))
            accounts = {key for key in ACCOUNT_KEYS if key in row}
            if not accounts:
                raise ValueError(f"{trading_date}.{symbol} needs an account label")
            if set(row) - {"symbol", *ACCOUNT_KEYS}:
                raise ValueError(f"{trading_date}.{symbol} has unknown label keys")
            for account in accounts:
                _validate_account_label(
                    row[account],
                    field=f"{trading_date}.{symbol}.{account}",
                    source_ids=source_ids,
                    date_source_ids=date_source_ids,
                )
        if result.get("explicit_candidate_symbol_count") != len(seen_symbols):
            raise ValueError(f"{trading_date} explicit candidate count mismatch")

        off_candidate = result.get("observed_off_candidate_actions")
        if not isinstance(off_candidate, list):
            raise ValueError("observed_off_candidate_actions must be a list")
        seen_off: set[str] = set()
        for index, value in enumerate(off_candidate):
            row = _mapping(value, f"{trading_date}.off_candidate[{index}]")
            symbol = row.get("canonical_symbol")
            if not isinstance(symbol, str) or not symbol or symbol in seen_off:
                raise ValueError("off-candidate symbols must be unique and non-empty")
            seen_off.add(symbol)
            if symbol in symbols:
                raise ValueError(f"{trading_date}.{symbol} is not off-candidate")
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

    summary = _mapping(payload.get("summary"), "summary")
    if summary.get("candidate_symbol_date_count") != 195:
        raise ValueError("summary must retain all 195 candidate symbol-dates")
    if summary.get("source_record_count") != len(sources):
        raise ValueError("summary source count mismatch")
    if summary.get("account_action_states") != summarize_action_states(payload):
        raise ValueError("summary action-state counts do not recompute")


def load_context_heldout_labels(
    path: str | Path,
    *,
    semantic_root_path: str | Path | None = None,
) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("context label root must be an object")
    candidates = None
    if semantic_root_path is not None:
        root = Path(semantic_root_path)
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        validate_semantic_root_manifest(manifest)
        if manifest.get("content_sha256") != SEMANTIC_MANIFEST_CONTENT_SHA256:
            raise ValueError("unexpected semantic manifest content hash")
        candidates = {}
        for trading_date in REGISTERED_DATES:
            date_payload = json.loads(
                (root / "dates" / f"{trading_date}.json").read_text(encoding="utf-8")
            )
            validate_semantic_date_payload(date_payload)
            candidates[trading_date] = {
                str(record["symbol"]) for record in date_payload["records"]
            }
    validate_context_heldout_labels(payload, semantic_candidates=candidates)
    return payload


def expand_candidate_labels(
    payload: Mapping[str, object], trading_date: str
) -> dict[str, dict[str, str]]:
    date_results = _mapping(payload.get("date_results"), "date_results")
    result = _mapping(date_results.get(trading_date), trading_date)
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
    for value in explicit:
        row = _mapping(value, "candidate label")
        symbol = str(row["symbol"])
        for account in ACCOUNT_KEYS:
            if account in row:
                label = _mapping(row[account], f"{symbol}.{account}")
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
