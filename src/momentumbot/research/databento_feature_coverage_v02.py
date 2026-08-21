from __future__ import annotations

import hashlib
import json
import re
import tempfile
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping

from momentumbot.research import databento_feature_coverage_v01 as coverage_v01
from momentumbot.research import databento_fill_cancel_repair_v01 as repair
from momentumbot.research import databento_fill_cancel_repaired_feature_v01 as eqpt
from momentumbot.research.databento_quote import DATASET, SDK_VERSION, QuoteRequest
from momentumbot.research.microstructure_contract import canonical_fingerprint
from momentumbot.research.microstructure_features import (
    CanonicalDepthEvent,
    CausalMicrostructureFeatureEngine,
)


SCHEMA_VERSION = 1
COVERAGE_CONTRACT_ID = "databento-microstructure-feature-coverage-v0.2"
EXECUTION_AUTHORIZATION_ID = (
    "databento-microstructure-feature-coverage-v0.2-execution"
)
ARTIFACT_TYPE = "sanitized_databento_amc_gmm_repaired_feature_coverage"
CONTRACT_CONTENT_SHA256 = (
    "1218c98f80cbf7c535636ddd67842ed6ebc0a39628eaababfc44a7a0b822e213"
)
PUBLISHED_CHECKPOINT_COMMIT_SHA = (
    "a8e683465ac680ea233414455f8da568e0e6656c"
)
PUBLISHED_CHECKPOINT_TREE_SHA = (
    "91119666d04f39663442a0cb133bc28238a6229a"
)
INTJ_SUCCESS_CONTENT_SHA256 = (
    "093f65e4d62b125e370d972a5bd9ee3880b5439d72072dd3fd533e4774d18ebb"
)
INTJ_SUCCESS_FILE_SHA256 = (
    "013c7b67b68a90cd048f21b44a47c70533d765aff470dd0fe7dbaa3cc70c2015"
)
EQPT_SUCCESS_CONTENT_SHA256 = (
    "d87addf40a080d132799cb14daf8f6096b661d97369e7ebd9f8e216609cfffbb"
)
EQPT_SUCCESS_FILE_SHA256 = (
    "257673ce7fd4a4c321aeb7face80c3adb7d82985f0dbd70dabce5b1f0191b527"
)
REPAIR_CONTRACT_FILE_SHA256 = (
    "cbb717027ee8b6b3bd3d2e551e10e08977b0d392639672d873fd66adddbdd794"
)
REPAIR_SOURCE_FILE_SHA256 = (
    "8ec8c10a489c46840ca980f71cc3f55f0367a5c3673600773ae1b12812f19a83"
)
FEATURE_ENGINE_SOURCE_FILE_SHA256 = (
    "07e2db045c9187e4bab46e7d25c546668c2c7b8d01f78c58ec36e88e48f1628e"
)
MAX_PREFLIGHT_COST_USD = Decimal("0.07")
MAX_PREFLIGHT_BILLABLE_SIZE_BYTES = 65_000_000
REQUESTS = tuple(coverage_v01.REQUESTS[1:])
CASE_KEYS = tuple((request.trading_date, request.symbol) for request in REQUESTS)
SAFE_ERROR_CODES = eqpt.SAFE_ERROR_CODES
_SHA40 = re.compile(r"[0-9a-f]{40}")
_SHA64 = re.compile(r"[0-9a-f]{64}")
_ROOT = Path(__file__).resolve().parents[3]


HistoricalClient = coverage_v01.HistoricalClient
RuntimeConstants = coverage_v01.RuntimeConstants
SafeDiagnosticFailure = coverage_v01.SafeDiagnosticFailure


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_frozen_sources() -> None:
    expected = {
        "research/strategy/databento-microstructure-fill-cancel-repair-v0.1.json": (
            REPAIR_CONTRACT_FILE_SHA256
        ),
        "src/momentumbot/research/databento_fill_cancel_repair_v01.py": (
            REPAIR_SOURCE_FILE_SHA256
        ),
        "src/momentumbot/research/microstructure_features.py": (
            FEATURE_ENGINE_SOURCE_FILE_SHA256
        ),
    }
    for relative, digest in expected.items():
        if _sha256(_ROOT / relative) != digest:
            raise ValueError(f"frozen feature coverage source changed: {relative}")


def validate_intj_success_audit(payload: Mapping[str, object]) -> None:
    coverage_v01.validate_parent_success_audit(payload)
    if payload.get("content_sha256") != INTJ_SUCCESS_CONTENT_SHA256:
        raise ValueError("INTJ success audit content hash changed")


def load_intj_success_audit(path: str | Path) -> dict[str, object]:
    source = Path(path)
    if _sha256(source) != INTJ_SUCCESS_FILE_SHA256:
        raise ValueError("INTJ success audit file hash changed")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("INTJ success audit root must be an object")
    validate_intj_success_audit(payload)
    return payload


def validate_eqpt_success_audit(payload: Mapping[str, object]) -> None:
    claimed = payload.get("content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if claimed != EQPT_SUCCESS_CONTENT_SHA256:
        raise ValueError("EQPT success audit content hash changed")
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("EQPT success audit fingerprint mismatch")
    actions = _mapping(payload.get("github_actions"), "EQPT github_actions")
    result = _mapping(
        payload.get("verified_repaired_feature_result"),
        "EQPT repaired result",
    )
    interpretation = _mapping(
        payload.get("repair_interpretation"),
        "EQPT interpretation",
    )
    if actions.get("workflow_run_id") != 32520311940:
        raise ValueError("EQPT success workflow changed")
    if result.get("repaired_feature_replay_succeeded") is not True:
        raise ValueError("EQPT repaired feature success changed")
    if result.get("independent_feature_replay_exact") is not True:
        raise ValueError("EQPT independent replay changed")
    if int(result.get("sampled_snapshot_count", 0)) != 2_289:
        raise ValueError("EQPT snapshot count changed")
    for field in (
        "feature_threshold_selected",
        "feature_horizon_selected",
        "runtime_authority_created",
    ):
        if result.get(field) is not False:
            raise ValueError(f"EQPT boundary {field} changed")
    if interpretation.get("policy_promotion_allowed") is not False:
        raise ValueError("EQPT success cannot promote policy")


def load_eqpt_success_audit(path: str | Path) -> dict[str, object]:
    source = Path(path)
    if _sha256(source) != EQPT_SUCCESS_FILE_SHA256:
        raise ValueError("EQPT success audit file hash changed")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("EQPT success audit root must be an object")
    validate_eqpt_success_audit(payload)
    return payload


def validate_repair_contract(payload: Mapping[str, object]) -> None:
    claimed = payload.get("content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if claimed != repair.REPAIR_CONTRACT_CONTENT_SHA256:
        raise ValueError("Fill/Cancel repair contract hash changed")
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("Fill/Cancel repair contract fingerprint mismatch")
    if payload.get("provider_purchase_authorized") is not False:
        raise ValueError("Fill/Cancel repair contract provider boundary changed")
    mechanics = _mapping(payload.get("registered_repair"), "registered repair")
    if mechanics.get("fill_cancel_match_fields") != ["order_id", "side"]:
        raise ValueError("Fill/Cancel remaining identity changed")
    if mechanics.get("canonical_removal_payload_source") != "matched_cancel_record":
        raise ValueError("Fill/Cancel canonical removal changed")
    if mechanics.get("unmatched_fill_policy") != "fail_closed":
        raise ValueError("Fill/Cancel fail-closed boundary changed")


def load_repair_contract(path: str | Path) -> dict[str, object]:
    source = Path(path)
    if _sha256(source) != REPAIR_CONTRACT_FILE_SHA256:
        raise ValueError("Fill/Cancel repair contract file hash changed")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Fill/Cancel repair contract root must be an object")
    validate_repair_contract(payload)
    return payload


def validate_coverage_contract(
    payload: Mapping[str, object],
    *,
    intj_success_audit: Mapping[str, object],
    eqpt_success_audit: Mapping[str, object],
    repair_contract: Mapping[str, object],
) -> None:
    validate_intj_success_audit(intj_success_audit)
    validate_eqpt_success_audit(eqpt_success_audit)
    validate_repair_contract(repair_contract)
    expected = {
        "schema_version": SCHEMA_VERSION,
        "coverage_contract_id": COVERAGE_CONTRACT_ID,
        "artifact_type": (
            "preregistered_unarmed_databento_amc_gmm_repaired_feature_coverage"
        ),
        "runtime_strategy_effect": "none",
        "policy_promotion_eligible": False,
        "profitability_claim_eligible": False,
        "provider_purchase_authorized": False,
        "execution_authorization_file_present": False,
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise ValueError(f"AMC/GMM coverage contract {field} changed")
    claimed = payload.get("content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if claimed != CONTRACT_CONTENT_SHA256:
        raise ValueError("AMC/GMM coverage contract content hash changed")
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("AMC/GMM coverage contract fingerprint mismatch")
    checkpoint = _mapping(payload.get("published_checkpoint"), "published checkpoint")
    if checkpoint.get("commit_sha") != PUBLISHED_CHECKPOINT_COMMIT_SHA:
        raise ValueError("published checkpoint commit changed")
    if checkpoint.get("tree_sha") != PUBLISHED_CHECKPOINT_TREE_SHA:
        raise ValueError("published checkpoint tree changed")
    parents = _mapping(payload.get("frozen_verified_parents"), "verified parents")
    if _mapping(parents.get("intj"), "INTJ parent").get(
        "content_sha256"
    ) != INTJ_SUCCESS_CONTENT_SHA256:
        raise ValueError("INTJ parent binding changed")
    if _mapping(parents.get("eqpt"), "EQPT parent").get(
        "content_sha256"
    ) != EQPT_SUCCESS_CONTENT_SHA256:
        raise ValueError("EQPT parent binding changed")
    frozen = _mapping(payload.get("frozen_mechanics"), "frozen mechanics")
    expected_frozen = {
        "repair_contract_content_sha256": repair.REPAIR_CONTRACT_CONTENT_SHA256,
        "repair_source_file_sha256": REPAIR_SOURCE_FILE_SHA256,
        "feature_engine_source_file_sha256": FEATURE_ENGINE_SOURCE_FILE_SHA256,
        "matched_cancel_payload_is_canonical_removal": True,
        "unmatched_fill_fails_closed": True,
        "feature_mechanics_changed": False,
        "feature_windows_or_thresholds_changed": False,
        "strategy_or_broker_behavior_changed": False,
    }
    for field, expected_value in expected_frozen.items():
        if frozen.get(field) != expected_value:
            raise ValueError(f"AMC/GMM frozen mechanics {field} changed")
    surface = _mapping(payload.get("request_surface"), "request surface")
    if surface.get("exact_request_count") != len(REQUESTS):
        raise ValueError("AMC/GMM request count changed")
    if surface.get("cases") != [
        {"trading_date": date, "symbol": symbol} for date, symbol in CASE_KEYS
    ]:
        raise ValueError("AMC/GMM case order changed")
    if surface.get("requests") != [request.mapping() for request in REQUESTS]:
        raise ValueError("AMC/GMM request surface changed")
    gate = _mapping(payload.get("future_execution_gate"), "future execution gate")
    expected_gate = {
        "new_explicit_user_authorization_required": True,
        "future_authorization_must_bind_published_parent_sha": True,
        "authorization_only_direct_child_required": True,
        "first_github_actions_attempt_only": True,
        "exact_request_count_authorized": 0,
        "hard_preflight_cost_ceiling_usd": "0.07",
        "hard_preflight_billable_size_ceiling_bytes": 65_000_000,
        "automatic_retry_authorized": False,
        "batch_or_live_endpoint_authorized": False,
        "mbp10_redownload_authorized": False,
        "raw_market_data_publication_authorized": False,
        "broker_or_order_change_authorized": False,
        "strategy_or_threshold_change_authorized": False,
    }
    for field, expected_value in expected_gate.items():
        if gate.get(field) != expected_value:
            raise ValueError(f"AMC/GMM future execution gate {field} changed")
    _verify_frozen_sources()


def load_coverage_contract(
    path: str | Path,
    *,
    intj_success_audit: Mapping[str, object],
    eqpt_success_audit: Mapping[str, object],
    repair_contract: Mapping[str, object],
) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("AMC/GMM coverage contract root must be an object")
    validate_coverage_contract(
        payload,
        intj_success_audit=intj_success_audit,
        eqpt_success_audit=eqpt_success_audit,
        repair_contract=repair_contract,
    )
    return payload


def validate_execution_authorization(payload: Mapping[str, object]) -> None:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "execution_authorization_id": EXECUTION_AUTHORIZATION_ID,
        "artifact_type": (
            "explicit_one_shot_databento_amc_gmm_repaired_feature_authorization"
        ),
        "coverage_contract_id": COVERAGE_CONTRACT_ID,
        "coverage_contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "provider_purchase_authorized": True,
        "exact_request_count_authorized": 2,
        "hard_preflight_cost_ceiling_usd": "0.07",
        "hard_preflight_billable_size_ceiling_bytes": 65_000_000,
        "first_github_actions_attempt_only": True,
        "automatic_retry_authorized": False,
        "batch_or_live_endpoint_authorized": False,
        "mbp10_redownload_authorized": False,
        "raw_market_data_publication_authorized": False,
        "broker_or_order_change_authorized": False,
        "strategy_or_threshold_change_authorized": False,
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise ValueError(f"AMC/GMM authorization {field} changed")
    parent_sha = payload.get("authorized_push_parent_sha")
    if not isinstance(parent_sha, str) or not _SHA40.fullmatch(parent_sha):
        raise ValueError("AMC/GMM authorization parent SHA is invalid")
    statement = payload.get("explicit_user_authorization")
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError("AMC/GMM explicit user authorization is required")
    claimed = payload.get("content_sha256")
    if not isinstance(claimed, str) or not _SHA64.fullmatch(claimed):
        raise ValueError("AMC/GMM authorization hash is invalid")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("AMC/GMM authorization fingerprint mismatch")


def load_execution_authorization(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("AMC/GMM authorization root must be an object")
    validate_execution_authorization(payload)
    return payload


def _run_preflight(
    client: HistoricalClient,
) -> tuple[dict[str, object], list[dict[str, str]]]:
    rows: list[dict[str, object]] = []
    total_cost = Decimal("0")
    total_size = 0
    try:
        for request in REQUESTS:
            kwargs = coverage_v01._request_kwargs(request)
            size = coverage_v01._integer(
                client.metadata.get_billable_size(**kwargs),
                "billable size",
            )
            cost = coverage_v01._decimal(
                client.metadata.get_cost(**kwargs),
                "quoted cost",
            )
            rows.append(
                {
                    **request.mapping(),
                    "quoted_cost_usd": format(cost, "f"),
                    "billable_size_bytes": size,
                }
            )
            total_cost += cost
            total_size += size
    except Exception:
        return (
            {
                "request_count_expected": len(REQUESTS),
                "request_count_quoted": len(rows),
                "quote_rows": rows,
                "total_quoted_cost_usd": None,
                "total_billable_size_bytes": None,
                "hard_cost_ceiling_usd": format(MAX_PREFLIGHT_COST_USD, "f"),
                "hard_billable_size_ceiling_bytes": (
                    MAX_PREFLIGHT_BILLABLE_SIZE_BYTES
                ),
                "preflight_passed": False,
            },
            [{
                "failure_phase": "preflight",
                "safe_error_code": "preflight_metadata_query_failed",
            }],
        )
    passed = (
        total_cost <= MAX_PREFLIGHT_COST_USD
        and total_size <= MAX_PREFLIGHT_BILLABLE_SIZE_BYTES
    )
    return (
        {
            "request_count_expected": len(REQUESTS),
            "request_count_quoted": len(rows),
            "quote_rows": rows,
            "total_quoted_cost_usd": format(total_cost, "f"),
            "total_billable_size_bytes": total_size,
            "hard_cost_ceiling_usd": format(MAX_PREFLIGHT_COST_USD, "f"),
            "hard_billable_size_ceiling_bytes": MAX_PREFLIGHT_BILLABLE_SIZE_BYTES,
            "preflight_passed": passed,
        },
        [] if passed else [{
            "failure_phase": "preflight",
            "safe_error_code": "preflight_budget_rejected",
        }],
    )


def _base_report(
    *,
    authorization: Mapping[str, object],
    generated_at: datetime,
    sdk_version: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "coverage_contract_id": COVERAGE_CONTRACT_ID,
        "coverage_contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "execution_authorization_id": EXECUTION_AUTHORIZATION_ID,
        "execution_authorization_content_sha256": authorization["content_sha256"],
        "published_checkpoint_commit_sha": PUBLISHED_CHECKPOINT_COMMIT_SHA,
        "published_checkpoint_tree_sha": PUBLISHED_CHECKPOINT_TREE_SHA,
        "intj_success_audit_content_sha256": INTJ_SUCCESS_CONTENT_SHA256,
        "eqpt_success_audit_content_sha256": EQPT_SUCCESS_CONTENT_SHA256,
        "repair_contract_content_sha256": repair.REPAIR_CONTRACT_CONTENT_SHA256,
        "repair_source_file_sha256": REPAIR_SOURCE_FILE_SHA256,
        "feature_engine_source_file_sha256": FEATURE_ENGINE_SOURCE_FILE_SHA256,
        "artifact_type": ARTIFACT_TYPE,
        "generated_at": coverage_v01._iso_z(generated_at),
        "provider": "databento",
        "dataset": DATASET,
        "schema": "mbo",
        "venue": "XNAS",
        "sdk_version": sdk_version,
        "provider_credential_persisted": False,
        "raw_market_data_persisted": False,
        "raw_market_data_uploaded": False,
        "feature_snapshot_values_persisted": False,
        "batch_or_live_endpoint_called": False,
        "automatic_retry_attempted": False,
        "mbp10_redownloaded": False,
        "retrospective_labels_loaded": False,
        "registered_fill_cancel_repair_applied": True,
        "feature_mechanics_changed": False,
        "strategy_or_threshold_change_made": False,
        "broker_or_order_change_made": False,
        "actual_billing_known": False,
        "runtime_authority_created": False,
        "policy_promotion_eligible": False,
    }


def build_unavailable_report(
    contract: Mapping[str, object],
    intj_success_audit: Mapping[str, object],
    eqpt_success_audit: Mapping[str, object],
    repair_contract: Mapping[str, object],
    authorization: Mapping[str, object],
    *,
    generated_at: datetime,
    sdk_version: str,
    failure_phase: str,
    safe_error_code: str,
) -> dict[str, object]:
    validate_coverage_contract(
        contract,
        intj_success_audit=intj_success_audit,
        eqpt_success_audit=eqpt_success_audit,
        repair_contract=repair_contract,
    )
    validate_execution_authorization(authorization)
    report = _base_report(
        authorization=authorization,
        generated_at=generated_at,
        sdk_version=sdk_version,
    )
    report.update(
        {
            "preflight": {
                "request_count_expected": len(REQUESTS),
                "request_count_quoted": 0,
                "quote_rows": [],
                "total_quoted_cost_usd": None,
                "total_billable_size_bytes": None,
                "hard_cost_ceiling_usd": format(MAX_PREFLIGHT_COST_USD, "f"),
                "hard_billable_size_ceiling_bytes": (
                    MAX_PREFLIGHT_BILLABLE_SIZE_BYTES
                ),
                "preflight_passed": False,
            },
            "timeseries_request_count": 0,
            "downloads": [],
            "errors": [SafeDiagnosticFailure(
                failure_phase,
                safe_error_code,
            ).mapping()],
            "raw_temp_directory_empty_before_cleanup": True,
            "raw_temp_directory_removed": True,
            "diagnostic_observation_complete": False,
            "all_cases_succeeded": False,
            "safe_failure_classified": True,
        }
    )
    return coverage_v01._finish_report(report)


def extract_case_feature_diagnostic(
    store: Iterable[object],
    *,
    request: QuoteRequest,
    runtime: RuntimeConstants,
) -> dict[str, object]:
    if request not in REQUESTS:
        raise ValueError("AMC/GMM coverage requires a frozen remaining-case request")
    engines: dict[
        tuple[int, int],
        tuple[CausalMicrostructureFeatureEngine, CausalMicrostructureFeatureEngine],
    ] = {}
    current_bucket: dict[tuple[int, int], int] = {}
    last_complete_ts_recv: dict[tuple[int, int], int] = {}
    ingested: set[tuple[int, int]] = set()
    digest = hashlib.sha256()
    summary = eqpt.v03._snapshot_summary_template()
    action_counts: Counter[str] = Counter()
    record_count = 0
    event_count = 0
    depth_event_count = 0
    tape_event_count = 0
    matched_fill_count = 0
    ignored_fill_count = 0
    ignored_none_count = 0
    within_event_sequence_transition_count = 0

    def sample(scope: tuple[int, int], as_of_ts_recv_ns: int) -> None:
        pair = engines[scope]
        try:
            snapshots = tuple(
                engine.snapshot(
                    as_of_ts_recv_ns=as_of_ts_recv_ns,
                    hypothetical_order_sizes=eqpt.v03.FIXED_HYPOTHETICAL_ORDER_SIZES,
                )
                for engine in pair
            )
        except Exception as exc:
            raise eqpt.v03._classified(
                "feature_snapshot",
                "feature_snapshot_invariant",
                exc,
            ) from None
        if snapshots[0] != snapshots[1]:
            raise SafeDiagnosticFailure("completion", "independent_replay_diverged")
        snapshot = snapshots[0]
        if snapshot.get("thresholds_applied") is not False:
            raise SafeDiagnosticFailure("completion", "feature_output_invariant")
        if snapshot.get("runtime_authority") != "none_shadow_only":
            raise SafeDiagnosticFailure("completion", "feature_output_invariant")
        digest.update(str(snapshot["content_sha256"]).encode("ascii"))
        digest.update(b"\n")
        summary["sampled_snapshot_count"] = int(summary["sampled_snapshot_count"]) + 1
        book = _mapping(snapshot.get("book"), "feature book")
        summary["book_available_count"] = int(summary["book_available_count"]) + int(
            book.get("available") is True
        )
        summary["two_sided_book_count"] = int(summary["two_sided_book_count"]) + int(
            book.get("two_sided") is True
        )
        depth_walks = snapshot.get("depth_constrained_slippage")
        if not isinstance(depth_walks, list):
            raise SafeDiagnosticFailure("completion", "feature_output_invariant")
        summary["depth_walk_scenario_count"] = int(
            summary["depth_walk_scenario_count"]
        ) + len(depth_walks)
        summary["depth_walk_available_count"] = int(
            summary["depth_walk_available_count"]
        ) + sum(
            int(isinstance(row, Mapping) and row.get("available") is True)
            for row in depth_walks
        )
        windows = snapshot.get("windows")
        if not isinstance(windows, list) or len(windows) != len(
            eqpt.v01.REGISTERED_WINDOWS_NS
        ):
            raise SafeDiagnosticFailure("completion", "feature_output_invariant")
        availability = _mapping(summary["window_availability"], "window availability")
        for row in windows:
            window = _mapping(row, "feature window")
            counter = _mapping(
                availability.get(str(window.get("window_ns"))),
                "window counter",
            )
            counter["sample_count"] = int(counter["sample_count"]) + 1
            tape = _mapping(window.get("signed_trade_velocity"), "signed tape")
            available = tape.get("available") is True
            counter["signed_tape_available_count"] = int(
                counter["signed_tape_available_count"]
            ) + int(available)
            counter["signed_tape_unavailable_count"] = int(
                counter["signed_tape_unavailable_count"]
            ) + int(not available)
            counter["correction_fail_closed_count"] = int(
                counter["correction_fail_closed_count"]
            ) + int(tape.get("unavailable_reason") == "correction_or_cancel_in_window")
            breakout = _mapping(
                window.get("breakout_progress_context"),
                "breakout context",
            )
            summary["breakout_context_available_count"] = int(
                summary["breakout_context_available_count"]
            ) + int(breakout.get("available") is True)

    for records in eqpt.v03.iter_instrument_mbo_events(store, runtime=runtime):
        scope = eqpt.v03._event_scope(records[0])
        sequences = [
            coverage_v01._integer(getattr(record, "sequence"), "sequence")
            for record in records
        ]
        within_event_sequence_transition_count += sum(
            int(left != right) for left, right in zip(sequences, sequences[1:])
        )
        translated = repair.translate_xnas_instrument_event(
            records,
            symbol=request.symbol,
            runtime=runtime,
        )
        pair = engines.setdefault(
            scope,
            (
                CausalMicrostructureFeatureEngine(),
                CausalMicrostructureFeatureEngine(),
            ),
        )
        bucket = translated.ts_recv_ns // eqpt.v03.SAMPLE_INTERVAL_NS
        if (
            scope in current_bucket
            and bucket != current_bucket[scope]
            and scope in last_complete_ts_recv
            and scope in ingested
        ):
            sample(scope, last_complete_ts_recv[scope])
        current_bucket[scope] = bucket
        last_complete_ts_recv[scope] = translated.ts_recv_ns
        event_count += 1
        record_count += len(records)
        action_counts.update(translated.action_counts)
        matched_fill_count += translated.matched_executed_removal_count
        ignored_fill_count += translated.ignored_fill_marker_count
        ignored_none_count += translated.ignored_none_count
        depth_event_count += len(translated.depth_events)
        tape_event_count += len(translated.tape_events)
        try:
            for engine in pair:
                for event in translated.ordered_events:
                    if isinstance(event, CanonicalDepthEvent):
                        engine.ingest_depth(event)
                    else:
                        engine.ingest_tape(event)
        except Exception as exc:
            raise eqpt.v03._classified(
                "book_replay",
                "book_state_invariant",
                exc,
            ) from None
        if translated.ordered_events:
            ingested.add(scope)

    for scope in sorted(
        ingested,
        key=lambda item: (last_complete_ts_recv[item], item),
    ):
        sample(scope, last_complete_ts_recv[scope])
    if event_count == 0:
        raise SafeDiagnosticFailure("completion", "stream_empty")
    if int(summary["sampled_snapshot_count"]) == 0:
        raise SafeDiagnosticFailure("completion", "no_complete_snapshot")
    return {
        "record_count": record_count,
        "instrument_event_count": event_count,
        "event_scope_count": len(engines),
        "within_event_sequence_transition_count": (
            within_event_sequence_transition_count
        ),
        "canonical_depth_event_count": depth_event_count,
        "canonical_tape_event_count": tape_event_count,
        "provider_action_counts": {
            key: action_counts.get(key, 0)
            for key in ("A", "C", "M", "R", "T", "F", "N")
        },
        "matched_executed_removal_count": matched_fill_count,
        "ignored_fill_marker_count": ignored_fill_count,
        "ignored_none_boundary_count": ignored_none_count,
        **summary,
        "independent_feature_replay_exact": True,
        "full_snapshot_sequence_digest_sha256": digest.hexdigest(),
        "feature_threshold_selected": False,
        "feature_horizon_selected": False,
        "runtime_authority_created": False,
    }


def _download_and_replay(
    client: HistoricalClient,
    request: QuoteRequest,
    path: Path,
    runtime: RuntimeConstants,
) -> dict[str, object]:
    try:
        store = client.timeseries.get_range(
            path=str(path),
            **coverage_v01._request_kwargs(request),
        )
    except Exception:
        raise SafeDiagnosticFailure("provider_download", "provider_download_failed") from None
    if not path.is_file() or path.stat().st_size <= 0:
        raise SafeDiagnosticFailure("downloaded_file", "download_empty")
    try:
        dataset = coverage_v01._metadata_value(
            getattr(store, "metadata", None),
            "dataset",
        )
        schema = coverage_v01._metadata_value(
            getattr(store, "metadata", None),
            "schema",
        )
    except Exception:
        raise SafeDiagnosticFailure("metadata", "metadata_mismatch") from None
    if dataset != DATASET.lower() or schema != "mbo":
        raise SafeDiagnosticFailure("metadata", "metadata_mismatch")
    metrics = extract_case_feature_diagnostic(
        store,
        request=request,
        runtime=runtime,
    )
    return {
        "trading_date": request.trading_date,
        "symbol": request.symbol,
        "schema": request.schema,
        "ephemeral_file_sha256": coverage_v01.file_sha256(path),
        "file_nonempty": True,
        "metadata_matches_request": True,
        "metrics": metrics,
    }


def run_feature_coverage_diagnostic(
    contract: Mapping[str, object],
    intj_success_audit: Mapping[str, object],
    eqpt_success_audit: Mapping[str, object],
    repair_contract: Mapping[str, object],
    authorization: Mapping[str, object],
    client: HistoricalClient,
    *,
    generated_at: datetime,
    sdk_version: str,
    runtime: RuntimeConstants,
) -> dict[str, object]:
    validate_coverage_contract(
        contract,
        intj_success_audit=intj_success_audit,
        eqpt_success_audit=eqpt_success_audit,
        repair_contract=repair_contract,
    )
    validate_execution_authorization(authorization)
    if sdk_version != SDK_VERSION:
        raise ValueError(f"Databento SDK version must be {SDK_VERSION}")
    preflight, errors = _run_preflight(client)
    report = _base_report(
        authorization=authorization,
        generated_at=generated_at,
        sdk_version=sdk_version,
    )
    report.update(
        {
            "preflight": preflight,
            "timeseries_request_count": 0,
            "downloads": [],
            "errors": errors,
            "raw_temp_directory_empty_before_cleanup": True,
            "raw_temp_directory_removed": True,
        }
    )
    if preflight.get("preflight_passed") is not True:
        report.update(
            {
                "diagnostic_observation_complete": False,
                "all_cases_succeeded": False,
                "safe_failure_classified": bool(errors),
            }
        )
        return coverage_v01._finish_report(report)

    temp = tempfile.TemporaryDirectory(
        prefix="momentumbot-databento-feature-coverage-v02-"
    )
    temp_path = Path(temp.name)
    try:
        for index, request in enumerate(REQUESTS):
            path = temp_path / f"request-{index:02d}.dbn.zst"
            try:
                report["timeseries_request_count"] = int(
                    report["timeseries_request_count"]
                ) + 1
                report["downloads"].append(
                    _download_and_replay(client, request, path, runtime)
                )
            except SafeDiagnosticFailure as exc:
                errors.append(
                    {
                        "trading_date": request.trading_date,
                        "symbol": request.symbol,
                        **exc.mapping(),
                    }
                )
                break
            except Exception:
                errors.append(
                    {
                        "trading_date": request.trading_date,
                        "symbol": request.symbol,
                        "failure_phase": "completion",
                        "safe_error_code": "unclassified_fail_closed",
                    }
                )
                break
            finally:
                path.unlink(missing_ok=True)
    finally:
        report["raw_temp_directory_empty_before_cleanup"] = not any(
            temp_path.iterdir()
        )
        temp_name = temp.name
        temp.cleanup()
        report["raw_temp_directory_removed"] = not Path(temp_name).exists()
    downloads = report["downloads"]
    all_succeeded = len(downloads) == len(REQUESTS) and not errors
    terminal_failure_observed = (
        len(errors) == 1
        and int(report["timeseries_request_count"]) == len(downloads) + 1
    )
    report.update(
        {
            "diagnostic_observation_complete": (
                all_succeeded or terminal_failure_observed
            ),
            "all_cases_succeeded": all_succeeded,
            "safe_failure_classified": bool(errors)
            and all(row.get("safe_error_code") in SAFE_ERROR_CODES for row in errors),
        }
    )
    return coverage_v01._finish_report(report)


def _walk_keys(value: object) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def validate_coverage_report(payload: Mapping[str, object]) -> None:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "coverage_contract_id": COVERAGE_CONTRACT_ID,
        "coverage_contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "artifact_type": ARTIFACT_TYPE,
        "published_checkpoint_commit_sha": PUBLISHED_CHECKPOINT_COMMIT_SHA,
        "published_checkpoint_tree_sha": PUBLISHED_CHECKPOINT_TREE_SHA,
        "intj_success_audit_content_sha256": INTJ_SUCCESS_CONTENT_SHA256,
        "eqpt_success_audit_content_sha256": EQPT_SUCCESS_CONTENT_SHA256,
        "repair_contract_content_sha256": repair.REPAIR_CONTRACT_CONTENT_SHA256,
        "repair_source_file_sha256": REPAIR_SOURCE_FILE_SHA256,
        "feature_engine_source_file_sha256": FEATURE_ENGINE_SOURCE_FILE_SHA256,
        "registered_fill_cancel_repair_applied": True,
        "feature_mechanics_changed": False,
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise ValueError(f"AMC/GMM report {field} changed")
    for field in (
        "provider_credential_persisted",
        "raw_market_data_persisted",
        "raw_market_data_uploaded",
        "feature_snapshot_values_persisted",
        "batch_or_live_endpoint_called",
        "automatic_retry_attempted",
        "mbp10_redownloaded",
        "retrospective_labels_loaded",
        "strategy_or_threshold_change_made",
        "broker_or_order_change_made",
        "actual_billing_known",
        "runtime_authority_created",
        "policy_promotion_eligible",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"AMC/GMM report {field} must remain false")
    if payload.get("raw_temp_directory_empty_before_cleanup") is not True:
        raise ValueError("AMC/GMM temporary directory was not empty")
    if payload.get("raw_temp_directory_removed") is not True:
        raise ValueError("AMC/GMM temporary directory was not removed")
    request_count = int(payload.get("timeseries_request_count", 0))
    if request_count < 0 or request_count > len(REQUESTS):
        raise ValueError("AMC/GMM request count exceeded registration")
    forbidden_keys = {
        "raw_records",
        "record_values",
        "order_id",
        "instrument_id",
        "publisher_id",
        "price",
        "size",
        "levels",
        "feature_snapshots",
        "temporary_path",
        "provider_error_message",
        "exception_message",
        "error_message",
        "ross_action",
        "ross_label",
        "pnl",
        "later_price",
    }
    if set(_walk_keys(payload)) & forbidden_keys:
        raise ValueError("AMC/GMM report contains a prohibited field")
    downloads = payload.get("downloads")
    errors = payload.get("errors")
    if not isinstance(downloads, list) or len(downloads) > len(REQUESTS):
        raise ValueError("AMC/GMM downloads are invalid")
    if not isinstance(errors, list) or len(errors) > 1:
        raise ValueError("AMC/GMM errors are invalid")
    observed_keys = [
        (str(row.get("trading_date")), str(row.get("symbol")))
        for row in downloads
        if isinstance(row, Mapping)
    ]
    if observed_keys != list(CASE_KEYS[: len(observed_keys)]):
        raise ValueError("AMC/GMM case order changed")
    for row in downloads:
        metrics = _mapping(_mapping(row, "download").get("metrics"), "metrics")
        if metrics.get("independent_feature_replay_exact") is not True:
            raise ValueError("AMC/GMM independent replay must remain exact")
        for field in (
            "feature_threshold_selected",
            "feature_horizon_selected",
            "runtime_authority_created",
        ):
            if metrics.get(field) is not False:
                raise ValueError(f"AMC/GMM metrics {field} must remain false")
    if errors:
        error = _mapping(errors[0], "error")
        if set(error) - {
            "trading_date",
            "symbol",
            "failure_phase",
            "safe_error_code",
            "exception_kind",
        }:
            raise ValueError("AMC/GMM error contains an unregistered field")
        if error.get("safe_error_code") not in SAFE_ERROR_CODES:
            raise ValueError("AMC/GMM error code is not allowlisted")
    all_succeeded = payload.get("all_cases_succeeded") is True
    if all_succeeded:
        if request_count != len(REQUESTS) or len(downloads) != len(REQUESTS) or errors:
            raise ValueError("successful AMC/GMM report is inconsistent")
    elif payload.get("safe_failure_classified") is True:
        preflight_passed = _mapping(payload.get("preflight"), "preflight").get(
            "preflight_passed"
        )
        if preflight_passed is True:
            if len(errors) != 1 or request_count != len(downloads) + 1:
                raise ValueError("classified AMC/GMM report is inconsistent")
        elif request_count != 0 or downloads or len(errors) != 1:
            raise ValueError("preflight AMC/GMM failure is inconsistent")
    else:
        raise ValueError("AMC/GMM report lacks a terminal outcome")
    claimed = payload.get("content_sha256")
    if not isinstance(claimed, str) or not _SHA64.fullmatch(claimed):
        raise ValueError("AMC/GMM report content hash is invalid")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError("AMC/GMM report fingerprint mismatch")
