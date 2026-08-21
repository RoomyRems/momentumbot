from __future__ import annotations

import hashlib
import json
import tempfile
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping

from momentumbot.research.databento_quote import DATASET, SDK_VERSION, QuoteRequest
from momentumbot.research.databento_smoke import (
    BookState,
    HistoricalClient,
    IncrementalBook,
    IndependentOrderMap,
    ReferenceSample,
    RuntimeConstants,
    _char,
    _decimal,
    _digest_state,
    _file_sha256,
    _finish_report,
    _has_fields,
    _integer,
    _mapping,
    _metadata_value,
    _process_mbp10,
    _record_int,
    _request_kwargs,
    _state_component_matches,
    _state_is_crossed,
    _unflagged_time_inversion,
)
from momentumbot.research.microstructure_contract import canonical_fingerprint


SCHEMA_VERSION = 1
ACQUISITION_CONTRACT_ID = "databento-microstructure-smoke-acquisition-v0.2"
ARTIFACT_TYPE = "sanitized_ephemeral_databento_reset_repair"
ACQUISITION_CONTENT_SHA256 = (
    "61b9ab6a0894a5a6871feda0236cdb9605f14b7ce13633c36dd1cffc4aa4de2a"
)
AUTHORIZED_PUSH_PARENT_SHA = "2754a33d2a7deecac6aca7aa7c8cd1ba7c854b98"
PARENT_FAILURE_AUDIT_ID = (
    "databento-microstructure-smoke-acquisition-v0.1-"
    "run-32427326070-failure-2026-08-20"
)
PARENT_FAILURE_CONTENT_SHA256 = (
    "b2c0b03fd4f43985a81f8d0321978c8dc180c5e6953cbe95ff871fb34aba088c"
)
PARENT_FAILURE_REPORT_CONTENT_SHA256 = (
    "fdd4a903bb80e6f3d32081217a858de6f728678012030815b56c541e3dba3b49"
)
MAX_PREFLIGHT_COST_USD = Decimal("0.02")
MAX_PREFLIGHT_BILLABLE_SIZE_BYTES = 15_000_000
MIN_REFERENCE_ALIGNMENT_RATIO = Decimal("0.95")
DOWNLOAD_SCHEMA_ORDER = ("mbp-10", "mbo")
REQUESTS = (
    QuoteRequest(
        trading_date="2026-07-10",
        symbol="EQPT",
        dataset=DATASET,
        schema="mbp-10",
        start="2026-07-10T10:50:00Z",
        end="2026-07-10T14:10:00Z",
    ),
    QuoteRequest(
        trading_date="2026-07-10",
        symbol="EQPT",
        dataset=DATASET,
        schema="mbo",
        start="2026-07-10T00:00:00Z",
        end="2026-07-10T14:10:00Z",
    ),
)


def validate_parent_failure_audit(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported parent failure audit schema")
    if payload.get("audit_id") != PARENT_FAILURE_AUDIT_ID:
        raise ValueError("unexpected parent failure audit")
    if payload.get("artifact_type") != (
        "independently_verified_sanitized_databento_acquisition_failure"
    ):
        raise ValueError("unexpected parent failure audit type")
    claimed = payload.get("content_sha256")
    if claimed != PARENT_FAILURE_CONTENT_SHA256:
        raise ValueError("parent failure audit content hash changed")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("parent failure audit fingerprint mismatch")
    actions = _mapping(payload.get("github_actions"), "github_actions")
    if actions.get("workflow_run_id") != 32427326070:
        raise ValueError("parent workflow run changed")
    if actions.get("workflow_run_attempt") != 1:
        raise ValueError("parent workflow attempt changed")
    if actions.get("sanitized_report_content_sha256") != (
        PARENT_FAILURE_REPORT_CONTENT_SHA256
    ):
        raise ValueError("parent sanitized report changed")
    acquisition = _mapping(payload.get("verified_acquisition"), "verified_acquisition")
    if acquisition.get("timeseries_request_count") != 20:
        raise ValueError("parent request count changed")
    if acquisition.get("g1_schema_and_integrity_passed") is not False:
        raise ValueError("parent G1 result changed")
    if acquisition.get("g2_reconstruction_passed") is not False:
        raise ValueError("parent G2 result changed")
    interpretation = _mapping(
        payload.get("failure_interpretation"),
        "failure_interpretation",
    )
    if interpretation.get("mbo_mbp10_disagreement_observed") is not False:
        raise ValueError("parent comparison interpretation changed")
    safety = _mapping(payload.get("safety_verification"), "safety_verification")
    for field in (
        "automatic_retry_attempted",
        "batch_or_live_endpoint_called",
        "provider_credential_persisted",
        "raw_market_data_persisted",
        "raw_market_data_uploaded",
        "runtime_authority_created",
        "broker_or_order_change_made",
        "strategy_or_threshold_change_made",
    ):
        if safety.get(field) is not False:
            raise ValueError(f"parent safety field {field} changed")


def load_parent_failure_audit(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("parent failure audit root must be an object")
    validate_parent_failure_audit(payload)
    return payload


def validate_acquisition_contract(
    payload: Mapping[str, object],
    *,
    parent_failure_audit: Mapping[str, object] | None = None,
) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported Databento v0.2 acquisition schema")
    if payload.get("acquisition_contract_id") != ACQUISITION_CONTRACT_ID:
        raise ValueError("unexpected Databento v0.2 acquisition contract")
    if payload.get("artifact_type") != (
        "preregistered_bounded_ephemeral_databento_reset_repair"
    ):
        raise ValueError("unexpected Databento v0.2 acquisition type")
    claimed = payload.get("content_sha256")
    if claimed != ACQUISITION_CONTENT_SHA256:
        raise ValueError("Databento v0.2 acquisition content hash changed")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("Databento v0.2 acquisition fingerprint mismatch")

    parent = _mapping(payload.get("frozen_parent_failure"), "frozen_parent_failure")
    if parent.get("audit_id") != PARENT_FAILURE_AUDIT_ID:
        raise ValueError("v0.2 parent audit changed")
    if parent.get("content_sha256") != PARENT_FAILURE_CONTENT_SHA256:
        raise ValueError("v0.2 parent content hash changed")
    if parent.get("sanitized_report_content_sha256") != (
        PARENT_FAILURE_REPORT_CONTENT_SHA256
    ):
        raise ValueError("v0.2 parent report hash changed")
    if parent_failure_audit is not None:
        validate_parent_failure_audit(parent_failure_audit)

    authorization = _mapping(payload.get("authorization"), "authorization")
    expected_authorization = {
        "metadata_requote_authorized": True,
        "historical_timeseries_download_authorized": True,
        "exact_request_count_authorized": 2,
        "authorized_push_parent_sha": AUTHORIZED_PUSH_PARENT_SHA,
        "batch_job_authorized": False,
        "live_subscription_authorized": False,
        "broad_history_download_authorized": False,
        "automatic_retry_authorized": False,
        "broker_or_order_change_authorized": False,
        "reported_new_user_credit_usd": "125",
        "observed_v0_1_eqpt_quote_usd": "0.005820024014",
        "hard_preflight_cost_ceiling_usd": "0.02",
        "observed_v0_1_eqpt_billable_size_bytes": 10810592,
        "hard_preflight_billable_size_ceiling_bytes": 15000000,
    }
    for field, expected in expected_authorization.items():
        if authorization.get(field) != expected:
            raise ValueError(f"authorization.{field} changed")

    provider = _mapping(payload.get("provider"), "provider")
    expected_provider = {
        "provider_id": "databento",
        "dataset": DATASET,
        "venue_scope": "single_venue_nasdaq_not_consolidated_national_depth",
        "sdk_package": "databento",
        "sdk_version": SDK_VERSION,
        "secret_name": "DATABENTO_API_KEY",
    }
    for field, expected in expected_provider.items():
        if provider.get(field) != expected:
            raise ValueError(f"provider.{field} changed")

    surface = _mapping(payload.get("request_surface"), "request_surface")
    observed_requests = tuple(
        QuoteRequest(
            trading_date=str(surface.get("trading_date")),
            symbol=str(item.get("symbol")),
            dataset=str(item.get("dataset")),
            schema=str(item.get("schema")),
            start=str(item.get("start")),
            end=str(item.get("end")),
            stype_in=str(item.get("stype_in")),
        )
        for item in surface.get("requests", [])
        if isinstance(item, Mapping)
    )
    if observed_requests != REQUESTS:
        raise ValueError("v0.2 exact request surface changed")
    if surface.get("allowed_calls") != [
        "historical.metadata.get_billable_size",
        "historical.metadata.get_cost",
        "historical.timeseries.get_range",
    ]:
        raise ValueError("v0.2 allowed provider calls changed")
    if surface.get("prohibited_calls") != [
        "historical.batch.submit_job",
        "historical.batch.download",
        "live.subscribe",
    ]:
        raise ValueError("v0.2 prohibited provider calls changed")

    storage = _mapping(payload.get("storage_and_licensing"), "storage_and_licensing")
    if storage.get("public_repository_raw_data") is not False:
        raise ValueError("v0.2 public raw-data policy changed")
    if storage.get("github_artifact_raw_data") is not False:
        raise ValueError("v0.2 raw artifact policy changed")


def load_acquisition_contract(
    path: str | Path,
    *,
    parent_failure_audit: Mapping[str, object],
) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Databento v0.2 contract root must be an object")
    validate_acquisition_contract(
        payload,
        parent_failure_audit=parent_failure_audit,
    )
    return payload


def _run_preflight(
    client: HistoricalClient,
) -> tuple[dict[str, object], list[dict[str, str]]]:
    rows: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    total_cost = Decimal("0")
    total_size = 0
    for request in REQUESTS:
        kwargs = _request_kwargs(request)
        stage = f"preflight:{request.trading_date}:{request.symbol}:{request.schema}"
        try:
            size = _integer(client.metadata.get_billable_size(**kwargs), "billable size")
            cost = _decimal(client.metadata.get_cost(**kwargs), "quoted cost")
        except Exception as exc:
            errors.append({"stage": stage, "error_kind": type(exc).__name__})
            break
        total_size += size
        total_cost += cost
        row: dict[str, object] = request.mapping()
        row.update(
            {
                "billable_size_bytes": size,
                "quoted_cost_usd": format(cost, "f"),
            }
        )
        rows.append(row)

    complete = len(rows) == len(REQUESTS) == 2 and not errors
    within_cost = complete and total_cost <= MAX_PREFLIGHT_COST_USD
    within_size = complete and total_size <= MAX_PREFLIGHT_BILLABLE_SIZE_BYTES
    return (
        {
            "request_count_expected": 2,
            "request_count_quoted": len(rows),
            "quote_rows": rows,
            "total_quoted_cost_usd": format(total_cost, "f") if complete else None,
            "total_billable_size_bytes": total_size if complete else None,
            "hard_cost_ceiling_usd": format(MAX_PREFLIGHT_COST_USD, "f"),
            "hard_billable_size_ceiling_bytes": MAX_PREFLIGHT_BILLABLE_SIZE_BYTES,
            "all_two_quotes_complete": complete,
            "cost_within_ceiling": within_cost,
            "billable_size_within_ceiling": within_size,
            "preflight_passed": complete and within_cost and within_size,
        },
        errors,
    )


def _valid_clear(
    *,
    action: str,
    side: str,
    price: int,
    size: int,
    order_id: int,
    runtime: RuntimeConstants,
) -> bool:
    return (
        action == "R"
        and side == "N"
        and price == runtime.undef_price
        and size == 0
        and order_id == 0
    )


def _process_mbo_v02(
    store: Iterable[object],
    runtime: RuntimeConstants,
    references: Mapping[tuple[int, int, int], ReferenceSample],
) -> dict[str, object]:
    required = (
        "ts_recv",
        "ts_event",
        "publisher_id",
        "instrument_id",
        "channel_id",
        "sequence",
        "action",
        "side",
        "price",
        "size",
        "order_id",
        "flags",
    )
    record_count = 0
    fields_observed = True
    action_counts: Counter[str] = Counter()
    issue_counts: Counter[str] = Counter()
    unflagged_inversions = 0
    receive_reversals = 0
    sequence_reversals = 0
    sequence_gaps = 0
    last_receive: dict[tuple[int, int], int] = {}
    last_sequence: dict[tuple[int, int], int] = {}
    incremental: dict[tuple[int, int], IncrementalBook] = {}
    independent: dict[tuple[int, int], IndependentOrderMap] = {}
    observed_books: set[tuple[int, int]] = set()
    initialization_clears: set[tuple[int, int]] = set()
    snapshot_initialization_clears: set[tuple[int, int]] = set()
    session_initialization_clears: set[tuple[int, int]] = set()
    reset_pending: set[tuple[int, int]] = set()
    ready: set[tuple[int, int]] = set()
    matched_reference_keys: set[tuple[int, int, int]] = set()
    clear_action_count = 0
    recovery_clear_count = 0
    invalid_clear_field_count = 0
    preinitialization_mutating_record_count = 0
    aligned = 0
    independent_matches = 0
    reference_exact_matches = 0
    price_matches = 0
    size_matches = 0
    count_matches = 0
    crossed_samples = 0
    top_of_book_events = 0
    zero_size_modifies = 0
    incremental_digest = hashlib.sha256()
    independent_digest = hashlib.sha256()
    reference_digest = hashlib.sha256()

    for record in store:
        record_count += 1
        if not _has_fields(record, required):
            fields_observed = False
            continue
        flags = _record_int(record, "flags")
        publisher_id = _record_int(record, "publisher_id")
        instrument_id = _record_int(record, "instrument_id")
        channel_id = _record_int(record, "channel_id")
        sequence = _record_int(record, "sequence")
        ts_recv = _record_int(record, "ts_recv")
        action = _char(getattr(record, "action"))
        side = _char(getattr(record, "side"))
        price = int(getattr(record, "price"))
        size = _record_int(record, "size")
        order_id = _record_int(record, "order_id")
        action_counts[
            action if action in {"A", "C", "M", "R", "T", "F", "N"} else "unknown"
        ] += 1

        channel_key = (publisher_id, channel_id)
        if _unflagged_time_inversion(record, flags, runtime):
            unflagged_inversions += 1
        if channel_key in last_receive and ts_recv < last_receive[channel_key]:
            if not flags & runtime.f_bad_ts_recv:
                receive_reversals += 1
        last_receive[channel_key] = ts_recv
        if sequence > 0:
            previous = last_sequence.get(channel_key)
            if previous is not None and sequence < previous:
                sequence_reversals += 1
            elif previous is not None and sequence > previous + 1:
                sequence_gaps += 1
            last_sequence[channel_key] = sequence

        book_key = (publisher_id, instrument_id)
        first_observed = book_key not in observed_books
        if first_observed:
            observed_books.add(book_key)
        first = incremental.setdefault(book_key, IncrementalBook())
        second = independent.setdefault(book_key, IndependentOrderMap())
        valid_clear = _valid_clear(
            action=action,
            side=side,
            price=price,
            size=size,
            order_id=order_id,
            runtime=runtime,
        )

        if action == "R":
            clear_action_count += 1
            ready.discard(book_key)
            reset_pending.discard(book_key)
            if not valid_clear:
                invalid_clear_field_count += 1
                issue_counts["invalid_clear_fields"] += 1
            else:
                reset_pending.add(book_key)
                if first_observed:
                    initialization_clears.add(book_key)
                    if flags & runtime.f_snapshot:
                        snapshot_initialization_clears.add(book_key)
                    else:
                        session_initialization_clears.add(book_key)
                else:
                    recovery_clear_count += 1
        elif action in {"A", "C", "M"} and book_key not in initialization_clears:
            preinitialization_mutating_record_count += 1

        kwargs = {
            "action": action,
            "side": side,
            "order_id": order_id,
            "price": price,
            "size": size,
            "flags": flags,
            "runtime": runtime,
        }
        first_issues = first.apply(**kwargs)
        second_issues = second.apply(**kwargs)
        issue_counts.update(first_issues)
        if sorted(first_issues) != sorted(second_issues):
            issue_counts["independent_apply_issue_mismatch"] += 1
        if flags & runtime.f_tob:
            top_of_book_events += 1
        if action == "M" and size == 0:
            zero_size_modifies += 1

        if (
            book_key in reset_pending
            and not flags & runtime.f_snapshot
            and flags & runtime.f_last
        ):
            ready.add(book_key)
            reset_pending.discard(book_key)

        reference_key = (publisher_id, instrument_id, sequence)
        if (
            flags & runtime.f_last
            and book_key in ready
            and reference_key in references
            and reference_key not in matched_reference_keys
        ):
            matched_reference_keys.add(reference_key)
            aligned += 1
            first_state: BookState = first.top_ten(runtime.undef_price)
            second_state: BookState = second.top_ten(runtime.undef_price)
            reference_state = references[reference_key].state
            if first_state == second_state:
                independent_matches += 1
            if first_state == reference_state:
                reference_exact_matches += 1
            price_match, size_match, count_match = _state_component_matches(
                first_state,
                reference_state,
            )
            price_matches += int(price_match)
            size_matches += int(size_match)
            count_matches += int(count_match)
            crossed_samples += int(_state_is_crossed(first_state, runtime.undef_price))
            _digest_state(
                incremental_digest,
                publisher_id,
                instrument_id,
                sequence,
                first_state,
            )
            _digest_state(
                independent_digest,
                publisher_id,
                instrument_id,
                sequence,
                second_state,
            )
            _digest_state(
                reference_digest,
                publisher_id,
                instrument_id,
                sequence,
                reference_state,
            )

    reference_count = len(references)
    coverage = Decimal(aligned) / Decimal(reference_count) if reference_count else Decimal("0")
    return {
        "record_count": record_count,
        "required_fields_observed": fields_observed and record_count > 0,
        "book_count": len(incremental),
        "first_record_clear_count": len(initialization_clears),
        "snapshot_initialization_clear_count": len(snapshot_initialization_clears),
        "session_initialization_clear_count": len(session_initialization_clears),
        "clear_action_count": clear_action_count,
        "recovery_clear_count": recovery_clear_count,
        "invalid_clear_field_count": invalid_clear_field_count,
        "preinitialization_mutating_record_count": (
            preinitialization_mutating_record_count
        ),
        "ready_book_count": len(ready),
        "action_counts": {
            key: action_counts.get(key, 0)
            for key in ("A", "C", "M", "R", "T", "F", "N", "unknown")
        },
        "issue_counts": {
            key: issue_counts.get(key, 0)
            for key in (
                "duplicate_add",
                "orphan_cancel",
                "cancel_identity_mismatch",
                "cancel_exceeds_resting_size",
                "missing_modify",
                "modify_identity_mismatch",
                "invalid_action",
                "invalid_side",
                "invalid_size",
                "invalid_price",
                "invalid_order_id",
                "invalid_clear_fields",
                "level_underflow",
                "independent_apply_issue_mismatch",
            )
        },
        "top_of_book_event_count": top_of_book_events,
        "zero_size_modify_count": zero_size_modifies,
        "unflagged_timestamp_inversion_count": unflagged_inversions,
        "receive_timestamp_reversal_count": receive_reversals,
        "sequence_reversal_count": sequence_reversals,
        "symbol_filtered_forward_sequence_gap_count": sequence_gaps,
        "comparison_metrics": {
            "reference_sample_count": reference_count,
            "aligned_sample_count": aligned,
            "reference_alignment_ratio": format(coverage, "f"),
            "independent_replay_exact_match_count": independent_matches,
            "mbp10_exact_match_count": reference_exact_matches,
            "mbp10_price_match_count": price_matches,
            "mbp10_size_match_count": size_matches,
            "mbp10_order_count_match_count": count_matches,
            "crossed_reconstructed_sample_count": crossed_samples,
            "incremental_replay_digest_sha256": incremental_digest.hexdigest(),
            "independent_replay_digest_sha256": independent_digest.hexdigest(),
            "mbp10_reference_digest_sha256": reference_digest.hexdigest(),
        },
    }


def _download_and_process(
    client: HistoricalClient,
    request: QuoteRequest,
    path: Path,
    runtime: RuntimeConstants,
    references: Mapping[tuple[int, int, int], ReferenceSample] | None,
) -> tuple[dict[str, object], dict[tuple[int, int, int], ReferenceSample] | None]:
    store = client.timeseries.get_range(path=str(path), **_request_kwargs(request))
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError("Databento DBN file was not created or was empty")
    metadata = getattr(store, "metadata", None)
    dataset_matches = _metadata_value(metadata, "dataset") == DATASET.lower()
    schema_matches = _metadata_value(metadata, "schema") == request.schema
    if request.schema == "mbp-10":
        metrics, samples = _process_mbp10(store, runtime)
    elif request.schema == "mbo":
        if references is None:
            raise ValueError("v0.2 MBO processing requires ephemeral MBP-10 references")
        metrics = _process_mbo_v02(store, runtime, references)
        samples = None
    else:
        raise ValueError("v0.2 request schema is not authorized")
    row: dict[str, object] = request.mapping()
    row.update(
        {
            "compressed_file_size_bytes": path.stat().st_size,
            "ephemeral_file_sha256": _file_sha256(path),
            "dataset_metadata_matches": dataset_matches,
            "schema_metadata_matches": schema_matches,
            "metrics": metrics,
        }
    )
    return row, samples


def _case_gate(case: Mapping[str, object]) -> tuple[bool, bool, dict[str, bool]]:
    rows = case.get("downloads") if isinstance(case.get("downloads"), list) else []
    by_schema = {
        str(row.get("schema")): row
        for row in rows
        if isinstance(row, Mapping)
    }
    all_schemas = set(by_schema) == set(DOWNLOAD_SCHEMA_ORDER)
    metadata_matches = all(
        row.get("dataset_metadata_matches") is True
        and row.get("schema_metadata_matches") is True
        for row in by_schema.values()
    )
    fields_observed = all(
        _mapping(row.get("metrics"), "download metrics").get("required_fields_observed")
        is True
        for row in by_schema.values()
    ) if all_schemas else False
    required_nonempty = all(
        int(_mapping(row.get("metrics"), "download metrics").get("record_count", 0))
        > 0
        for row in by_schema.values()
    ) if all_schemas else False
    mbo = (
        _mapping(by_schema["mbo"].get("metrics"), "MBO metrics")
        if "mbo" in by_schema
        else {}
    )
    book_count = int(mbo.get("book_count", 0))
    g1_conditions = {
        "both_exact_schemas_downloaded": all_schemas,
        "dataset_and_schema_metadata_match": metadata_matches,
        "required_fields_observed": fields_observed,
        "required_schemas_nonempty": required_nonempty,
        "every_book_begins_with_valid_clear": (
            book_count > 0
            and int(mbo.get("first_record_clear_count", 0)) == book_count
            and int(mbo.get("invalid_clear_field_count", -1)) == 0
        ),
        "no_mutation_before_initialization_clear": (
            int(mbo.get("preinitialization_mutating_record_count", -1)) == 0
        ),
        "every_book_becomes_ready": (
            book_count > 0 and int(mbo.get("ready_book_count", 0)) == book_count
        ),
    }
    g1 = all(g1_conditions.values())

    comparison = _mapping(mbo.get("comparison_metrics", {}), "comparison metrics")
    aligned = int(comparison.get("aligned_sample_count", 0))
    reference_count = int(comparison.get("reference_sample_count", 0))
    ratio = _decimal(comparison.get("reference_alignment_ratio", "0"), "alignment ratio")
    issue_counts = _mapping(mbo.get("issue_counts", {}), "issue counts")
    mbp = (
        _mapping(by_schema["mbp-10"].get("metrics"), "MBP-10 metrics")
        if "mbp-10" in by_schema
        else {}
    )
    g2_conditions = {
        "aligned_sample_exists": aligned > 0,
        "reference_alignment_at_least_95_percent": (
            reference_count > 0 and ratio >= MIN_REFERENCE_ALIGNMENT_RATIO
        ),
        "independent_replays_match_every_aligned_sample": (
            int(comparison.get("independent_replay_exact_match_count", -1)) == aligned
        ),
        "mbp10_exactly_matches_every_aligned_sample": (
            int(comparison.get("mbp10_exact_match_count", -1)) == aligned
        ),
        "mbp10_prices_match_every_aligned_sample": (
            int(comparison.get("mbp10_price_match_count", -1)) == aligned
        ),
        "mbp10_sizes_match_every_aligned_sample": (
            int(comparison.get("mbp10_size_match_count", -1)) == aligned
        ),
        "mbp10_order_counts_match_every_aligned_sample": (
            int(comparison.get("mbp10_order_count_match_count", -1)) == aligned
        ),
        "replay_digests_match": (
            comparison.get("incremental_replay_digest_sha256")
            == comparison.get("independent_replay_digest_sha256")
            == comparison.get("mbp10_reference_digest_sha256")
        ),
        "no_book_mutation_issue": all(int(value) == 0 for value in issue_counts.values()),
        "no_unflagged_timestamp_inversion": (
            int(mbo.get("unflagged_timestamp_inversion_count", -1)) == 0
            and int(mbp.get("unflagged_timestamp_inversion_count", -1)) == 0
        ),
        "no_receive_timestamp_reversal": (
            int(mbo.get("receive_timestamp_reversal_count", -1)) == 0
            and int(mbp.get("receive_timestamp_reversal_count", -1)) == 0
        ),
        "no_sequence_reversal": int(mbo.get("sequence_reversal_count", -1)) == 0,
        "no_crossed_sampled_book": (
            int(comparison.get("crossed_reconstructed_sample_count", -1)) == 0
            and int(mbp.get("crossed_reference_sample_count", -1)) == 0
        ),
        "no_reference_key_collision": (
            int(mbp.get("reference_key_collision_count", -1)) == 0
        ),
    }
    g2 = g1 and all(g2_conditions.values())
    return g1, g2, {**g1_conditions, **g2_conditions}


def _base_report(*, generated_at: datetime, sdk_version: str) -> dict[str, object]:
    from momentumbot.research.databento_smoke import _iso_z

    return {
        "schema_version": SCHEMA_VERSION,
        "acquisition_contract_id": ACQUISITION_CONTRACT_ID,
        "acquisition_contract_content_sha256": ACQUISITION_CONTENT_SHA256,
        "artifact_type": ARTIFACT_TYPE,
        "generated_at": _iso_z(generated_at),
        "parent_failure_audit_id": PARENT_FAILURE_AUDIT_ID,
        "parent_failure_audit_content_sha256": PARENT_FAILURE_CONTENT_SHA256,
        "parent_failure_report_content_sha256": (
            PARENT_FAILURE_REPORT_CONTENT_SHA256
        ),
        "provider": "databento",
        "dataset": DATASET,
        "venue_scope": "single_venue_nasdaq_not_consolidated_national_depth",
        "sdk_version": sdk_version,
        "provider_credential_persisted": False,
        "raw_market_data_persisted": False,
        "raw_market_data_uploaded": False,
        "batch_or_live_endpoint_called": False,
        "automatic_retry_attempted": False,
        "broker_or_order_change_made": False,
        "strategy_or_threshold_change_made": False,
        "actual_billing_known": False,
        "billing_note": (
            "Preflight quotes are not represented as actual billed charges; "
            "completed downloads may be billable."
        ),
    }


def build_unavailable_report(
    contract: Mapping[str, object],
    *,
    parent_failure_audit: Mapping[str, object],
    generated_at: datetime,
    sdk_version: str,
    error_stage: str,
    error_kind: str,
) -> dict[str, object]:
    validate_acquisition_contract(
        contract,
        parent_failure_audit=parent_failure_audit,
    )
    report = _base_report(generated_at=generated_at, sdk_version=sdk_version)
    report.update(
        {
            "preflight": {
                "request_count_expected": 2,
                "request_count_quoted": 0,
                "quote_rows": [],
                "total_quoted_cost_usd": None,
                "total_billable_size_bytes": None,
                "hard_cost_ceiling_usd": format(MAX_PREFLIGHT_COST_USD, "f"),
                "hard_billable_size_ceiling_bytes": (
                    MAX_PREFLIGHT_BILLABLE_SIZE_BYTES
                ),
                "all_two_quotes_complete": False,
                "cost_within_ceiling": False,
                "billable_size_within_ceiling": False,
                "preflight_passed": False,
            },
            "timeseries_request_count": 0,
            "downloads": [],
            "case": None,
            "errors": [{"stage": error_stage, "error_kind": error_kind}],
            "raw_temp_directory_empty_before_cleanup": True,
            "raw_temp_directory_removed": True,
            "g1_schema_and_integrity_passed": False,
            "g2_reconstruction_passed": False,
            "smoke_acquisition_passed": False,
            "runtime_authority_created": False,
        }
    )
    return _finish_report(report)


def run_smoke_acquisition(
    contract: Mapping[str, object],
    client: HistoricalClient,
    *,
    parent_failure_audit: Mapping[str, object],
    generated_at: datetime,
    sdk_version: str,
    runtime: RuntimeConstants,
) -> dict[str, object]:
    validate_acquisition_contract(
        contract,
        parent_failure_audit=parent_failure_audit,
    )
    if sdk_version != SDK_VERSION:
        raise ValueError(f"Databento SDK version must be {SDK_VERSION}")
    preflight, errors = _run_preflight(client)
    report = _base_report(generated_at=generated_at, sdk_version=sdk_version)
    report.update(
        {
            "preflight": preflight,
            "timeseries_request_count": 0,
            "downloads": [],
            "case": None,
            "errors": errors,
            "raw_temp_directory_empty_before_cleanup": True,
            "raw_temp_directory_removed": True,
        }
    )
    if preflight.get("preflight_passed") is not True:
        report.update(
            {
                "g1_schema_and_integrity_passed": False,
                "g2_reconstruction_passed": False,
                "smoke_acquisition_passed": False,
                "runtime_authority_created": False,
            }
        )
        return _finish_report(report)

    temp = tempfile.TemporaryDirectory(prefix="momentumbot-databento-v02-")
    temp_path = Path(temp.name)
    case_downloads: list[dict[str, object]] = []
    references: dict[tuple[int, int, int], ReferenceSample] | None = None
    try:
        for request in REQUESTS:
            raw_path = temp_path / f"request-{len(case_downloads):02d}.dbn.zst"
            stage = f"download_or_parse:{request.trading_date}:{request.symbol}:{request.schema}"
            try:
                report["timeseries_request_count"] = int(
                    report["timeseries_request_count"]
                ) + 1
                row, new_references = _download_and_process(
                    client,
                    request,
                    raw_path,
                    runtime,
                    references,
                )
                if new_references is not None:
                    references = new_references
                case_downloads.append(row)
                report["downloads"].append(row)
            except Exception as exc:
                errors.append({"stage": stage, "error_kind": type(exc).__name__})
                break
            finally:
                raw_path.unlink(missing_ok=True)
        case: dict[str, object] = {
            "trading_date": "2026-07-10",
            "symbol": "EQPT",
            "downloads": case_downloads,
        }
        g1, g2, conditions = _case_gate(case)
        case.update(
            {
                "gate_conditions": conditions,
                "g1_schema_and_integrity_passed": g1,
                "g2_reconstruction_passed": g2,
            }
        )
        report["case"] = case
        references = None
    finally:
        report["raw_temp_directory_empty_before_cleanup"] = not any(
            temp_path.iterdir()
        )
        temp_name = temp.name
        temp.cleanup()
        report["raw_temp_directory_removed"] = not Path(temp_name).exists()

    case = report.get("case")
    g1 = (
        not errors
        and len(report["downloads"]) == 2
        and isinstance(case, Mapping)
        and case.get("g1_schema_and_integrity_passed") is True
        and report["raw_temp_directory_empty_before_cleanup"] is True
        and report["raw_temp_directory_removed"] is True
    )
    g2 = g1 and isinstance(case, Mapping) and case.get(
        "g2_reconstruction_passed"
    ) is True
    report.update(
        {
            "g1_schema_and_integrity_passed": g1,
            "g2_reconstruction_passed": g2,
            "smoke_acquisition_passed": g1 and g2,
            "runtime_authority_created": False,
        }
    )
    return _finish_report(report)


def _walk_keys(value: object) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def validate_smoke_report(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported Databento v0.2 report schema")
    if payload.get("acquisition_contract_id") != ACQUISITION_CONTRACT_ID:
        raise ValueError("unexpected Databento v0.2 report contract")
    if payload.get("acquisition_contract_content_sha256") != (
        ACQUISITION_CONTENT_SHA256
    ):
        raise ValueError("v0.2 report acquisition binding changed")
    if payload.get("artifact_type") != ARTIFACT_TYPE:
        raise ValueError("unexpected Databento v0.2 report type")
    if payload.get("parent_failure_audit_content_sha256") != (
        PARENT_FAILURE_CONTENT_SHA256
    ):
        raise ValueError("v0.2 report parent binding changed")
    for field in (
        "provider_credential_persisted",
        "raw_market_data_persisted",
        "raw_market_data_uploaded",
        "batch_or_live_endpoint_called",
        "automatic_retry_attempted",
        "broker_or_order_change_made",
        "strategy_or_threshold_change_made",
        "actual_billing_known",
        "runtime_authority_created",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"{field} must remain false")
    if payload.get("raw_temp_directory_empty_before_cleanup") is not True:
        raise ValueError("v0.2 raw temporary directory was not empty")
    if payload.get("raw_temp_directory_removed") is not True:
        raise ValueError("v0.2 raw temporary directory was not removed")
    if int(payload.get("timeseries_request_count", 0)) > 2:
        raise ValueError("v0.2 request count exceeded authorization")
    forbidden_keys = {
        "raw_records",
        "record_values",
        "order_id",
        "instrument_id",
        "price",
        "size",
        "levels",
        "temporary_path",
        "provider_error_message",
        "exception_message",
    }
    if set(_walk_keys(payload)) & forbidden_keys:
        raise ValueError("sanitized v0.2 report contains a prohibited field")
    downloads = payload.get("downloads")
    if not isinstance(downloads, list):
        raise ValueError("v0.2 report downloads must be a list")
    for row in downloads:
        if not isinstance(row, Mapping):
            raise ValueError("v0.2 download summary must be an object")
        digest = row.get("ephemeral_file_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("v0.2 download file hash is invalid")
    claimed = payload.get("content_sha256")
    if not isinstance(claimed, str) or len(claimed) != 64:
        raise ValueError("v0.2 report content hash is invalid")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("v0.2 report content fingerprint mismatch")


__all__ = [
    "ACQUISITION_CONTENT_SHA256",
    "ACQUISITION_CONTRACT_ID",
    "ARTIFACT_TYPE",
    "AUTHORIZED_PUSH_PARENT_SHA",
    "DOWNLOAD_SCHEMA_ORDER",
    "MAX_PREFLIGHT_BILLABLE_SIZE_BYTES",
    "MAX_PREFLIGHT_COST_USD",
    "REQUESTS",
    "RuntimeConstants",
    "build_unavailable_report",
    "load_acquisition_contract",
    "load_parent_failure_audit",
    "run_smoke_acquisition",
    "validate_acquisition_contract",
    "validate_parent_failure_audit",
    "validate_smoke_report",
]
