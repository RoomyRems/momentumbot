"""Provider-free registration for the sealed historical walk-forward panel.

The registration deliberately separates three things:

* opaque commitment to the supplied transcript corpus without decoding record
  values;
* calendar-only date selection with every previously referenced research date
  removed; and
* a frozen runtime/evaluation contract that cannot open retrospective evidence
  until every label-blind runtime artifact is hash-frozen.

This module authorizes no provider request and no paper or live order.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Mapping, Sequence


SCHEMA_VERSION = 1
CONTRACT_ID = "sealed-historical-walk-forward-v0.1"
CORPUS_MANIFEST_ID = "sealed-daytradewarrior-corpus-v0.1"
EXCLUSION_MANIFEST_ID = "sealed-historical-date-exclusions-v0.1"
REGISTRATION_ID = "sealed-historical-walk-forward-v0.1-registration"
REGISTRATION_DATE = "2026-08-31"
CONTRACT_CONTENT_SHA256 = (
    "93a4316a4ef785e30ebc393ec140fa02ea23027aa9cd85673d34401b3bca3452"
)
CORPUS_MANIFEST_CONTENT_SHA256 = (
    "551ae4862174c30dd738cc444e27ed6ad1e54e4ebb6201edaab4c7afceb7c17e"
)
EXCLUSION_MANIFEST_CONTENT_SHA256 = (
    "9521d404a8ce0c6a6807905d085250304637651c797c4e4e24554541cb482f77"
)

PARENT_RESEARCH_COMMIT = "a2d2ffe5959fce7b4f4733528df4f873ea1913be"
PARENT_RESEARCH_TREE = "bee90f8514963db644cfb2abbf9a8e2ae98378c0"
MICRO_POLICY_FINGERPRINT = (
    "49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa"
)
GENERAL_PROFILE_FINGERPRINT = (
    "7d15fb979701324bf862b1dc37e5f9b514dcf1ab8cf1e062ae4a60027233d4ff"
)
SMALL_PROFILE_FINGERPRINT = (
    "fb86fc5326903cab16c283a03d8e371f66487f41589fb1b69b79f8912a0a6489"
)
DAILY_SOURCE_CONTENT_SHA256 = (
    "99ba9f54ac50a913e64d78bb727351b67f8182818c54519f7d8be428651d6f38"
)
DAILY_RUNTIME_CONTENT_SHA256 = (
    "dea1d60a804626ca623512d8f4828b40eca7fa57da85b12525926fc04c3d0531"
)
MANAGEMENT_CAPTURE_CONTENT_SHA256 = (
    "97270ae8d401a20c7d5661fe49e36a65276ed00bf60098e9c466fa51b05518b0"
)
ACCOUNT_EVALUATION_CONTENT_SHA256 = (
    "537287a04f35d81d8104f67a02cdcd352ee880cc8703fd8b8a61c68d971d5d5c"
)

CANDIDATE_START = date(2025, 1, 2)
CANDIDATE_END = date(2026, 6, 30)
BLOCK_SIZE = 30
EXPECTED_CORPUS_PARTS = tuple(range(1, 9))
EXPECTED_CORPUS_RECORDS = 2_292
ACCOUNTS = ("main_account", "small_account")
BEHAVIORAL_HORIZONS_SECONDS = (1, 5, 10)
EXECUTION_SCENARIOS = ("baseline_conservative", "stress")
CELL_COUNT_PER_DATE = len(ACCOUNTS) * len(BEHAVIORAL_HORIZONS_SECONDS) * len(
    EXECUTION_SCENARIOS
)
TOTAL_SESSION_CELL_COUNT = BLOCK_SIZE * CELL_COUNT_PER_DATE
CALENDAR_ID = "embedded-nyse-full-session-calendar-2025-01-02--2026-06-30-v0.1"
SCAN_ROOTS = ("research", "docs/research", "docs/project")
SCAN_SUFFIXES = frozenset({".csv", ".json", ".jsonl", ".md", ".txt", ".yaml", ".yml"})

# Explicit exchange closures in the bounded registration interval.  The
# provider availability stage must independently confirm every selected date.
_NYSE_CLOSED_DATES = frozenset(
    {
        date(2025, 1, 9),  # National Day of Mourning for Jimmy Carter
        date(2025, 1, 20),
        date(2025, 2, 17),
        date(2025, 4, 18),
        date(2025, 5, 26),
        date(2025, 6, 19),
        date(2025, 7, 4),
        date(2025, 9, 1),
        date(2025, 11, 27),
        date(2025, 12, 25),
        date(2026, 1, 1),
        date(2026, 1, 19),
        date(2026, 2, 16),
        date(2026, 4, 3),
        date(2026, 5, 25),
        date(2026, 6, 19),
    }
)
_NYSE_EARLY_CLOSE_DATES = frozenset(
    {
        date(2025, 7, 3),
        date(2025, 11, 28),
        date(2025, 12, 24),
    }
)
_DATE_PATTERN = re.compile(r"(?<!\d)(20\d{2}-\d{2}-\d{2})(?!\d)")
_PART_PATTERN = re.compile(r"(?:^|[^a-z0-9])part-(\d+)(?:[^0-9]|$)", re.IGNORECASE)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_REGISTRATION_KEYS = {
    "captions",
    "reported_entry",
    "reported_exit",
    "ross_action",
    "ross_fill",
    "ross_skip",
    "ross_trade",
    "ticker",
    "title",
    "trade_outcome",
    "transcript_text",
}


def canonical_fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def freeze(payload: Mapping[str, object]) -> dict[str, object]:
    result = dict(payload)
    result["content_sha256"] = canonical_fingerprint(payload)
    return result


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_frozen(payload: Mapping[str, object], field: str) -> None:
    observed = payload.get("content_sha256")
    if not isinstance(observed, str) or _SHA256_PATTERN.fullmatch(observed) is None:
        raise ValueError(f"{field}.content_sha256 must be a lowercase SHA-256")
    body = dict(payload)
    body.pop("content_sha256", None)
    if canonical_fingerprint(body) != observed:
        raise ValueError(f"{field} content hash mismatch")


def _walk_keys(value: object) -> set[str]:
    result: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            result.add(str(key).lower())
            result.update(_walk_keys(child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            result.update(_walk_keys(child))
    return result


def _structural_root(data: bytes) -> tuple[int, int]:
    """Return first and final non-whitespace byte positions without decoding."""

    whitespace = b" \t\r\n"
    first = 0
    while first < len(data) and data[first] in whitespace:
        first += 1
    final = len(data) - 1
    while final >= 0 and data[final] in whitespace:
        final -= 1
    if first > final:
        raise ValueError("corpus part is empty")
    return first, final


def _count_array_records_without_decoding(data: bytes) -> int:
    first, final = _structural_root(data)
    if data[first] != ord("[") or data[final] != ord("]"):
        raise ValueError("JSON corpus part must be a top-level array")
    depth = 0
    count = 0
    in_string = False
    escaped = False
    for byte in data[first : final + 1]:
        if in_string:
            if escaped:
                escaped = False
            elif byte == ord("\\"):
                escaped = True
            elif byte == ord('"'):
                in_string = False
            continue
        if byte == ord('"'):
            in_string = True
        elif byte in (ord("["), ord("{")):
            if byte == ord("{") and depth == 1:
                count += 1
            depth += 1
        elif byte in (ord("]"), ord("}")):
            depth -= 1
            if depth < 0:
                raise ValueError("corpus part has unbalanced containers")
    if in_string or depth != 0:
        raise ValueError("corpus part has an incomplete JSON structure")
    return count


def _count_jsonl_records_without_decoding(data: bytes) -> int:
    count = 0
    for line_number, raw in enumerate(data.splitlines(), start=1):
        value = raw.strip()
        if not value:
            continue
        first, final = _structural_root(value)
        if value[first] != ord("{") or value[final] != ord("}"):
            raise ValueError(f"JSONL corpus line {line_number} is not one object")
        count += 1
    if count == 0:
        raise ValueError("JSONL corpus part contains no records")
    return count


def build_corpus_manifest(
    paths: Iterable[str | Path],
    *,
    expected_parts: Sequence[int] = EXPECTED_CORPUS_PARTS,
    expected_records: int | None = EXPECTED_CORPUS_RECORDS,
) -> dict[str, object]:
    """Commit to raw corpus bytes without decoding any record field value."""

    parts: list[dict[str, object]] = []
    seen: set[int] = set()
    for raw_path in paths:
        path = Path(raw_path)
        match = _PART_PATTERN.search(path.name)
        if match is None:
            raise ValueError(f"corpus filename lacks a logical part number: {path.name}")
        part_number = int(match.group(1))
        if part_number in seen:
            raise ValueError(f"duplicate corpus part: {part_number}")
        seen.add(part_number)
        data = path.read_bytes()
        first, _ = _structural_root(data)
        if data[first] == ord("["):
            serialization = "json_array"
            record_count = _count_array_records_without_decoding(data)
        elif data[first] == ord("{"):
            serialization = "json_lines"
            record_count = _count_jsonl_records_without_decoding(data)
        else:
            raise ValueError(f"unsupported corpus serialization for part {part_number}")
        parts.append(
            {
                "logical_part": part_number,
                "serialization": serialization,
                "byte_count": len(data),
                "record_count": record_count,
                "raw_sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    parts.sort(key=lambda item: int(item["logical_part"]))
    if tuple(int(item["logical_part"]) for item in parts) != tuple(expected_parts):
        raise ValueError("corpus logical parts differ from the sealed inventory")
    total = sum(int(item["record_count"]) for item in parts)
    if expected_records is not None and total != expected_records:
        raise ValueError(
            f"corpus record count is {total}; expected exactly {expected_records}"
        )
    return freeze(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "opaque_transcript_corpus_commitment",
            "manifest_id": CORPUS_MANIFEST_ID,
            "registered_at_date": REGISTRATION_DATE,
            "parts": parts,
            "part_count": len(parts),
            "record_count": total,
            "record_values_decoded": False,
            "record_values_persisted": False,
            "forbidden_values_opened_for_selection": False,
            "selection_input": "this_manifest_content_sha256_only",
            "forbidden_record_fields": [
                "title",
                "captions",
                "videoId",
                "channelName",
                "channelID",
                "dateText",
                "relativeDateText",
                "thumbnailUrl",
                "status",
                "reason",
            ],
            "raw_files_committed_to_repository": False,
        }
    )


def verify_corpus_files(
    manifest: Mapping[str, object], paths: Iterable[str | Path]
) -> None:
    validate_corpus_manifest(manifest)
    rebuilt = build_corpus_manifest(paths)
    if rebuilt != dict(manifest):
        raise ValueError("supplied corpus bytes differ from the sealed manifest")


def validate_corpus_manifest(payload: Mapping[str, object]) -> None:
    _assert_frozen(payload, "corpus_manifest")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported corpus manifest schema")
    if payload.get("manifest_id") != CORPUS_MANIFEST_ID:
        raise ValueError("unexpected corpus manifest ID")
    if payload.get("artifact_type") != "opaque_transcript_corpus_commitment":
        raise ValueError("unexpected corpus manifest artifact type")
    if payload.get("record_values_decoded") is not False:
        raise ValueError("corpus record values must remain undecoded")
    if payload.get("record_values_persisted") is not False:
        raise ValueError("corpus record values must not be persisted")
    if payload.get("forbidden_values_opened_for_selection") is not False:
        raise ValueError("forbidden corpus values cannot be opened for selection")
    if payload.get("raw_files_committed_to_repository") is not False:
        raise ValueError("raw transcript files cannot be committed")
    parts = payload.get("parts")
    if not isinstance(parts, list):
        raise ValueError("corpus parts must be a list")
    if tuple(item.get("logical_part") for item in parts if isinstance(item, Mapping)) != (
        EXPECTED_CORPUS_PARTS
    ):
        raise ValueError("corpus parts differ from the expected eight-part inventory")
    if payload.get("part_count") != len(EXPECTED_CORPUS_PARTS):
        raise ValueError("corpus part count mismatch")
    if payload.get("record_count") != EXPECTED_CORPUS_RECORDS:
        raise ValueError("corpus record count mismatch")
    if sum(int(item["record_count"]) for item in parts) != EXPECTED_CORPUS_RECORDS:
        raise ValueError("corpus part counts do not sum to the registered total")
    for item in parts:
        if not isinstance(item, Mapping):
            raise ValueError("corpus part must be an object")
        if item.get("serialization") not in {"json_array", "json_lines"}:
            raise ValueError("unsupported corpus serialization")
        if not isinstance(item.get("byte_count"), int) or int(item["byte_count"]) <= 0:
            raise ValueError("corpus byte count must be positive")
        if not isinstance(item.get("record_count"), int) or int(item["record_count"]) <= 0:
            raise ValueError("corpus record count must be positive")
        value = item.get("raw_sha256")
        if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("corpus raw hash must be a lowercase SHA-256")
    if payload.get("content_sha256") != CORPUS_MANIFEST_CONTENT_SHA256:
        raise ValueError("corpus manifest differs from the sealed fingerprint")


def build_prior_research_date_manifest(
    files: Iterable[tuple[str, bytes]],
) -> dict[str, object]:
    file_inventory: list[dict[str, object]] = []
    sources: dict[str, set[str]] = {}
    for relative, data in files:
        file_inventory.append(
            {
                "path": relative,
                "byte_count": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
        text = data.decode("utf-8")
        for match in _DATE_PATTERN.finditer(text):
            try:
                observed = date.fromisoformat(match.group(1))
            except ValueError:
                continue
            if CANDIDATE_START <= observed <= CANDIDATE_END:
                sources.setdefault(observed.isoformat(), set()).add(relative)
    inventory_digest = canonical_fingerprint(file_inventory)
    excluded = [
        {"date": value, "source_paths": sorted(paths)}
        for value, paths in sorted(sources.items())
    ]
    return freeze(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "prior_research_date_exclusion_manifest",
            "manifest_id": EXCLUSION_MANIFEST_ID,
            "registered_at_date": REGISTRATION_DATE,
            "parent_research_commit": PARENT_RESEARCH_COMMIT,
            "parent_research_tree": PARENT_RESEARCH_TREE,
            "scan_roots": list(SCAN_ROOTS),
            "scan_suffixes": sorted(SCAN_SUFFIXES),
            "scanned_file_count": len(file_inventory),
            "scanned_file_inventory_sha256": inventory_digest,
            "candidate_interval": {
                "start": CANDIDATE_START.isoformat(),
                "end": CANDIDATE_END.isoformat(),
            },
            "excluded_dates": excluded,
            "excluded_date_count": len(excluded),
            "exclusion_rule": "every valid ISO date referenced by the frozen scan inventory within the candidate interval",
            "case_specific_exception_allowed": False,
        }
    )


def scan_prior_research_dates(repo_root: str | Path) -> dict[str, object]:
    root = Path(repo_root).resolve()
    files: list[tuple[str, bytes]] = []
    for relative_root in SCAN_ROOTS:
        scan_root = root / relative_root
        if not scan_root.exists():
            raise ValueError(f"missing research scan root: {relative_root}")
        for path in sorted(item for item in scan_root.rglob("*") if item.is_file()):
            if path.suffix.lower() in SCAN_SUFFIXES:
                files.append((path.relative_to(root).as_posix(), path.read_bytes()))
    return build_prior_research_date_manifest(files)


def validate_exclusion_manifest(payload: Mapping[str, object]) -> None:
    _assert_frozen(payload, "exclusion_manifest")
    if payload.get("manifest_id") != EXCLUSION_MANIFEST_ID:
        raise ValueError("unexpected exclusion manifest ID")
    if payload.get("parent_research_commit") != PARENT_RESEARCH_COMMIT:
        raise ValueError("exclusion manifest parent commit mismatch")
    if payload.get("parent_research_tree") != PARENT_RESEARCH_TREE:
        raise ValueError("exclusion manifest parent tree mismatch")
    if payload.get("case_specific_exception_allowed") is not False:
        raise ValueError("case-specific exclusion exceptions are prohibited")
    excluded = payload.get("excluded_dates")
    if not isinstance(excluded, list):
        raise ValueError("excluded dates must be a list")
    values: list[str] = []
    for item in excluded:
        if not isinstance(item, Mapping):
            raise ValueError("excluded date entry must be an object")
        value = str(item.get("date"))
        parsed = date.fromisoformat(value)
        if not CANDIDATE_START <= parsed <= CANDIDATE_END:
            raise ValueError("excluded date lies outside the candidate interval")
        paths = item.get("source_paths")
        if not isinstance(paths, list) or not paths or paths != sorted(set(paths)):
            raise ValueError("excluded date sources must be a sorted nonempty list")
        values.append(value)
    if values != sorted(set(values)):
        raise ValueError("excluded dates must be unique and chronological")
    if payload.get("excluded_date_count") != len(values):
        raise ValueError("excluded date count mismatch")
    for required in ("2025-04-03", "2025-04-21", "2025-09-09", "2026-06-10"):
        if required not in values:
            raise ValueError(f"known seed or diagnostic date was not excluded: {required}")
    if payload.get("content_sha256") != EXCLUSION_MANIFEST_CONTENT_SHA256:
        raise ValueError("exclusion manifest differs from the sealed fingerprint")


def bounded_full_sessions() -> tuple[str, ...]:
    result: list[str] = []
    current = CANDIDATE_START
    while current <= CANDIDATE_END:
        if (
            current.weekday() < 5
            and current not in _NYSE_CLOSED_DATES
            and current not in _NYSE_EARLY_CLOSE_DATES
        ):
            result.append(current.isoformat())
        current += timedelta(days=1)
    return tuple(result)


def select_registered_dates(
    corpus_manifest: Mapping[str, object],
    exclusion_manifest: Mapping[str, object],
) -> dict[str, object]:
    validate_corpus_manifest(corpus_manifest)
    validate_exclusion_manifest(exclusion_manifest)
    excluded = {
        str(item["date"])
        for item in exclusion_manifest["excluded_dates"]  # type: ignore[index]
    }
    calendar_sessions = bounded_full_sessions()
    eligible = [value for value in calendar_sessions if value not in excluded]
    blocks = [
        eligible[index : index + BLOCK_SIZE]
        for index in range(0, len(eligible) - BLOCK_SIZE + 1, BLOCK_SIZE)
    ]
    if not blocks:
        raise ValueError("no complete 30-session selection block is available")
    seed_inputs = {
        "contract_id": CONTRACT_ID,
        "calendar_id": CALENDAR_ID,
        "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
        "corpus_manifest_content_sha256": corpus_manifest["content_sha256"],
        "exclusion_manifest_content_sha256": exclusion_manifest["content_sha256"],
    }
    seed = canonical_fingerprint(seed_inputs)
    block_index = int(seed, 16) % len(blocks)
    selected = blocks[block_index]
    return {
        "calendar_id": CALENDAR_ID,
        "candidate_interval": {
            "start": CANDIDATE_START.isoformat(),
            "end": CANDIDATE_END.isoformat(),
        },
        "weekends_excluded": True,
        "exchange_closures_excluded": sorted(value.isoformat() for value in _NYSE_CLOSED_DATES),
        "early_close_sessions_excluded": sorted(
            value.isoformat() for value in _NYSE_EARLY_CLOSE_DATES
        ),
        "prior_research_dates_excluded": True,
        "calendar_session_count": len(calendar_sessions),
        "eligible_session_count": len(eligible),
        "block_size": BLOCK_SIZE,
        "complete_block_count": len(blocks),
        "discarded_tail_session_count": len(eligible) - len(blocks) * BLOCK_SIZE,
        "seed_inputs": seed_inputs,
        "selection_seed_sha256": seed,
        "selected_block_index_zero_based": block_index,
        "selected_dates": selected,
        "date_replacement_allowed": False,
        "selection_uses_transcript_record_values": False,
        "selection_uses_symbols_or_outcomes": False,
        "provider_session_confirmation_required_before_acquisition": True,
    }


def build_contract(
    corpus_manifest: Mapping[str, object],
    exclusion_manifest: Mapping[str, object],
) -> dict[str, object]:
    selection = select_registered_dates(corpus_manifest, exclusion_manifest)
    return freeze(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "preregistered_sealed_historical_walk_forward",
            "contract_id": CONTRACT_ID,
            "registration_date": REGISTRATION_DATE,
            "registration_status": "registered_provider_free_runtime_not_started",
            "hypothesis": (
                "The unchanged causal scanner, Micro-v0.1, account, execution, and management chain can be replayed across a deterministically selected 30-session historical block and evaluated without opening retrospective transcript evidence before runtime freeze."
            ),
            "frozen_parents": {
                "research_commit": PARENT_RESEARCH_COMMIT,
                "research_tree": PARENT_RESEARCH_TREE,
                "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
                "general_strategy_profile_fingerprint": GENERAL_PROFILE_FINGERPRINT,
                "small_strategy_profile_fingerprint": SMALL_PROFILE_FINGERPRINT,
                "prospective_daily_source_content_sha256": DAILY_SOURCE_CONTENT_SHA256,
                "prospective_daily_runtime_content_sha256": DAILY_RUNTIME_CONTENT_SHA256,
                "prospective_management_capture_content_sha256": MANAGEMENT_CAPTURE_CONTENT_SHA256,
                "prospective_account_evaluation_content_sha256": ACCOUNT_EVALUATION_CONTENT_SHA256,
                "corpus_manifest_content_sha256": corpus_manifest["content_sha256"],
                "exclusion_manifest_content_sha256": exclusion_manifest["content_sha256"],
            },
            "isolated_change": {
                "changed_component": "session sampling and historical data transport only",
                "micro_policy_changed": False,
                "scanner_thresholds_changed": False,
                "account_rules_changed": False,
                "execution_scenarios_changed": False,
                "management_rule_changed": False,
                "retrospective_label_policy_changed": False,
                "case_specific_threshold_or_symbol_exception": False,
            },
            "sampling_contract": selection,
            "runtime_panel": {
                "accounts": list(ACCOUNTS),
                "behavioral_horizons_seconds": list(BEHAVIORAL_HORIZONS_SECONDS),
                "execution_scenarios": list(EXECUTION_SCENARIOS),
                "session_count": BLOCK_SIZE,
                "cells_per_session": CELL_COUNT_PER_DATE,
                "total_session_cell_count": TOTAL_SESSION_CELL_COUNT,
                "chronology": "each account-and-cell path carries state forward across all selected dates",
                "account_reset_between_dates": False,
                "cells_may_be_selected_or_ranked": False,
            },
            "causal_boundary": {
                "runtime_order": [
                    "point_in_time_reference_and_membership",
                    "causal_market_news_and_float_inputs",
                    "label_blind_scanner_and_micro_replay",
                    "candidate_bound_execution_inputs",
                    "chronological_account_and_management_replay",
                    "runtime_hash_freeze",
                    "retrospective_label_open",
                    "component_evaluation",
                ],
                "transcript_titles_or_captions_allowed_before_runtime_freeze": False,
                "ross_actions_fills_skips_or_recap_judgments_allowed_in_runtime": False,
                "later_prices_or_final_volume_allowed_at_decision_time": False,
                "present_day_reference_facts_projected_backward": False,
                "unavailable_date_replaced": False,
                "unavailable_date_counted_as_zero_opportunity": False,
            },
            "provider_gates": {
                "registration_provider_calls": 0,
                "availability_audit_required": True,
                "cost_quote_required_before_paid_acquisition": True,
                "point_in_time_universe_required": True,
                "complete_cross_section_required": True,
                "provider_or_coverage_failure_behavior": "freeze date as unavailable without replacement",
                "market_data_acquisition_authorized_by_this_contract": False,
                "credential_access_authorized_by_this_contract": False,
            },
            "evaluation_contract": {
                "all_accounts_horizons_and_scenarios_reported_separately": True,
                "best_cell_selection_allowed": False,
                "weighted_overall_imitation_score_allowed": False,
                "candidate_acquisition_reported": True,
                "trade_skip_agreement_reported_when_observable": True,
                "entry_and_exit_alignment_reported_descriptively": True,
                "financial_metrics_require_complete_flat_runtime": True,
                "best_trade_removed_sensitivity_required": True,
                "source_unavailable_is_not_a_skip": True,
                "policy_promotion_allowed": False,
            },
            "execution_status": {
                "provider_availability_audit": "not_started",
                "provider_cost_quote": "not_started",
                "historical_market_runtime": "not_started",
                "runtime_hash_freeze": "not_started",
                "retrospective_label_review": "not_started",
                "evaluation": "not_started",
            },
            "authority_boundary": {
                "paper_order_authorized": False,
                "live_order_authorized": False,
                "provider_call_authorized": False,
                "policy_promotion_eligible": False,
                "profitability_claim_eligible": False,
                "ross_replication_claim_eligible": False,
            },
        }
    )


def validate_contract(
    payload: Mapping[str, object],
    corpus_manifest: Mapping[str, object],
    exclusion_manifest: Mapping[str, object],
) -> None:
    _assert_frozen(payload, "contract")
    validate_corpus_manifest(corpus_manifest)
    validate_exclusion_manifest(exclusion_manifest)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported sealed walk-forward schema")
    if payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected sealed walk-forward contract ID")
    if payload.get("registration_status") != "registered_provider_free_runtime_not_started":
        raise ValueError("sealed walk-forward must remain provider-free and unrun")
    forbidden = _walk_keys(payload) & _FORBIDDEN_REGISTRATION_KEYS
    if forbidden:
        raise ValueError(f"registration contains retrospective keys: {sorted(forbidden)}")
    parents = payload.get("frozen_parents")
    if not isinstance(parents, Mapping):
        raise ValueError("frozen parents must be an object")
    expected_parents = {
        "research_commit": PARENT_RESEARCH_COMMIT,
        "research_tree": PARENT_RESEARCH_TREE,
        "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
        "general_strategy_profile_fingerprint": GENERAL_PROFILE_FINGERPRINT,
        "small_strategy_profile_fingerprint": SMALL_PROFILE_FINGERPRINT,
        "prospective_daily_source_content_sha256": DAILY_SOURCE_CONTENT_SHA256,
        "prospective_daily_runtime_content_sha256": DAILY_RUNTIME_CONTENT_SHA256,
        "prospective_management_capture_content_sha256": MANAGEMENT_CAPTURE_CONTENT_SHA256,
        "prospective_account_evaluation_content_sha256": ACCOUNT_EVALUATION_CONTENT_SHA256,
        "corpus_manifest_content_sha256": corpus_manifest["content_sha256"],
        "exclusion_manifest_content_sha256": exclusion_manifest["content_sha256"],
    }
    if dict(parents) != expected_parents:
        raise ValueError("frozen parent binding mismatch")
    selection = payload.get("sampling_contract")
    if not isinstance(selection, Mapping):
        raise ValueError("sampling contract must be an object")
    expected_selection = select_registered_dates(corpus_manifest, exclusion_manifest)
    if dict(selection) != expected_selection:
        raise ValueError("selected date block differs from deterministic registration")
    selected = selection["selected_dates"]
    if not isinstance(selected, list) or len(selected) != BLOCK_SIZE:
        raise ValueError("exactly 30 dates must be registered")
    excluded = {item["date"] for item in exclusion_manifest["excluded_dates"]}  # type: ignore[index]
    if set(selected) & excluded:
        raise ValueError("selected dates overlap prior research evidence")
    runtime = payload.get("runtime_panel")
    if not isinstance(runtime, Mapping):
        raise ValueError("runtime panel must be an object")
    if runtime.get("accounts") != list(ACCOUNTS):
        raise ValueError("runtime accounts differ from registration")
    if runtime.get("behavioral_horizons_seconds") != list(BEHAVIORAL_HORIZONS_SECONDS):
        raise ValueError("behavioral horizons differ from registration")
    if runtime.get("execution_scenarios") != list(EXECUTION_SCENARIOS):
        raise ValueError("execution scenarios differ from registration")
    if runtime.get("total_session_cell_count") != TOTAL_SESSION_CELL_COUNT:
        raise ValueError("runtime cell count must be 360")
    if runtime.get("account_reset_between_dates") is not False:
        raise ValueError("accounts cannot reset between historical dates")
    status = payload.get("execution_status")
    if not isinstance(status, Mapping) or set(status.values()) != {"not_started"}:
        raise ValueError("all registered execution stages must remain not started")
    authority = payload.get("authority_boundary")
    if not isinstance(authority, Mapping) or any(value is not False for value in authority.values()):
        raise ValueError("registration cannot grant provider, order, or promotion authority")
    if payload.get("content_sha256") != CONTRACT_CONTENT_SHA256:
        raise ValueError("contract differs from the sealed fingerprint")


def load_json_object(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def validate_registration_files(
    *,
    contract_path: str | Path,
    corpus_manifest_path: str | Path,
    exclusion_manifest_path: str | Path,
) -> None:
    corpus = load_json_object(corpus_manifest_path)
    exclusions = load_json_object(exclusion_manifest_path)
    contract = load_json_object(contract_path)
    validate_contract(contract, corpus, exclusions)


def write_json_once(path: str | Path, payload: Mapping[str, object]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(f"refusing to overwrite registered artifact: {target}")
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
