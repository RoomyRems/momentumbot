"""Provider-free registration and source gate for historical runtime v0.2.

This module binds the next label-blind runtime stage to the independently
verified v0.13 source artifact. Registration and source validation do not
execute the separate scanner activation materializer. It fails closed on the Micro-v0.1 input
gap: the source bundle contains causal one-minute scanner evidence, but not the
completed ten-second bars or normalized SIP trade events required by the
frozen Micro policy.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo

from momentumbot.causal_scanner_snapshot import ordered_snapshot_records_fingerprint
from momentumbot.causal_market_discovery_v03 import strategy_profile_manifest
from momentumbot.historical_profile_union_v01 import (
    GENERAL_PROFILE_FINGERPRINT,
    SMALL_ACCOUNT_PROFILE_FINGERPRINT,
)
from momentumbot.micro_policy import micro_v0_1_policy
from momentumbot.models import current_general_2026, current_small_account_2026
from momentumbot.research.prospective_daily_source import profile_eligibility
from momentumbot.research.sealed_historical_source_acquisition_v13 import (
    validate_intermediate_checkpoint_v13,
    validate_recovery_report_v13,
)
from momentumbot.research.sealed_historical_source_checkpoint_v01 import (
    canonical_fingerprint,
    inventory_source_tree,
    load_json_object,
)


SCHEMA_VERSION = 1
CONTRACT_ID = "sealed-historical-scanner-micro-runtime-v0.2"
REGISTRATION_ID = f"{CONTRACT_ID}-registration"
REGISTRATION_DATE = "2026-09-06"
CONTRACT_CONTENT_SHA256 = (
    "0c1354fb1f9a7775a80def125f339de0aa94ed537bd574c0bfbbf7b02b4047d5"
)
REGISTRATION_CONTENT_SHA256 = (
    "506c4ec189eccd34694ef3e4d6bbae89b0e36eeb85acd02772b1597ff11ea737"
)

SOURCE_RUN_ID = "34039993297"
SOURCE_RUN_ATTEMPT = 1
SOURCE_ARTIFACT_ID = 9_993_250_947
SOURCE_ARTIFACT_NAME = "sealed-historical-source-acquisition-v13-34039993297-1"
SOURCE_ZIP_SHA256 = (
    "af89836213a905a1e02dabd54cce1d2bab2f55214c2d7bc0dce44d4700243638"
)
SOURCE_REPORT_FILE_SHA256 = (
    "048644a52d368381de3d01c143255758dd90f47b800d94716c4baa3193fcbdbf"
)
SOURCE_REPORT_CONTENT_SHA256 = (
    "03d2853fd82163387ee55fa32ba50c5f18e2c7a8a96e80054ff9830d47bd43c4"
)
SOURCE_INTERMEDIATE_FILE_SHA256 = (
    "e2627b5baa954129fcb5b092be92c43ec3544daec7865c61efe2b5c0048abf05"
)
SOURCE_INTERMEDIATE_CONTENT_SHA256 = (
    "d94525525e4fc6ab8b0e47154733f721ecba27ca71bdce57aa91458d39edf6d1"
)
SOURCE_TREE_SHA256 = (
    "74cc2895bf46d1c9a054f57108b7aae17af6a291f72678f1cd935118c844bed6"
)
SOURCE_FILE_COUNT = 767
SOURCE_DIRECTORY_COUNT = 190
SOURCE_RETAINED_BYTES = 748_128_473
SOURCE_AUTHORIZATION_COMMIT = "8b2b9379319d293291366bae5f898f66c5dd492b"
SOURCE_AUTHORIZATION_TREE = "997745472ccd749f0af4cb2e88a258ea3790ea8e"
SOURCE_DISPATCHER_COMMIT = "de24eb17316191da69d92e61f6843af25e9c22d0"
MICRO_POLICY_FINGERPRINT = (
    "49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa"
)
EXPECTED_DATES = (
    "2025-05-30", "2025-06-02", "2025-06-03", "2025-06-04",
    "2025-06-05", "2025-06-06", "2025-06-09", "2025-06-10",
    "2025-06-11", "2025-06-12", "2025-06-13", "2025-06-16",
    "2025-06-17", "2025-06-18", "2025-06-20", "2025-06-23",
    "2025-06-24", "2025-06-25", "2025-06-26", "2025-06-27",
    "2025-07-01", "2025-07-02", "2025-07-07", "2025-07-08",
    "2025-07-10", "2025-07-11", "2025-07-14", "2025-07-15",
    "2025-07-16", "2025-07-17",
)
MISSING_MICRO_INPUTS = (
    "completed_10_second_bars",
    "normalized_sip_trade_events",
)
ET = ZoneInfo("America/New_York")


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _assert_frozen(payload: Mapping[str, object], label: str) -> None:
    body = dict(payload)
    claimed = body.pop("content_sha256", None)
    if claimed != canonical_fingerprint(body):
        raise ValueError(f"{label} content hash mismatch")


def validate_frozen_policies() -> None:
    """Fail if either scanner profile or Micro-v0.1 changed in place."""

    observed_general = strategy_profile_manifest(current_general_2026())["fingerprint"]
    observed_small = strategy_profile_manifest(current_small_account_2026())["fingerprint"]
    if observed_general != GENERAL_PROFILE_FINGERPRINT:
        raise ValueError("frozen general strategy profile changed")
    if observed_small != SMALL_ACCOUNT_PROFILE_FINGERPRINT:
        raise ValueError("frozen small-account strategy profile changed")
    if micro_v0_1_policy().fingerprint != MICRO_POLICY_FINGERPRINT:
        raise ValueError("frozen Micro-v0.1 policy changed")


def validate_contract(payload: Mapping[str, object]) -> None:
    _assert_frozen(payload, "runtime contract")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("runtime contract schema changed")
    if payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("runtime contract ID changed")
    if payload.get("registration_status") != "prepared_unarmed_execution_not_started":
        raise ValueError("runtime registration status changed")
    source = payload.get("verified_source")
    if not isinstance(source, Mapping) or dict(source) != {
        "artifact_id": SOURCE_ARTIFACT_ID,
        "artifact_name": SOURCE_ARTIFACT_NAME,
        "artifact_zip_sha256": SOURCE_ZIP_SHA256,
        "authorization_commit_sha": SOURCE_AUTHORIZATION_COMMIT,
        "authorization_tree_sha": SOURCE_AUTHORIZATION_TREE,
        "directory_count": SOURCE_DIRECTORY_COUNT,
        "dispatcher_commit_sha": SOURCE_DISPATCHER_COMMIT,
        "file_count": SOURCE_FILE_COUNT,
        "intermediate_checkpoint_content_sha256": SOURCE_INTERMEDIATE_CONTENT_SHA256,
        "intermediate_checkpoint_file_sha256": SOURCE_INTERMEDIATE_FILE_SHA256,
        "recovery_report_content_sha256": SOURCE_REPORT_CONTENT_SHA256,
        "recovery_report_file_sha256": SOURCE_REPORT_FILE_SHA256,
        "retained_bytes": SOURCE_RETAINED_BYTES,
        "source_tree_content_sha256": SOURCE_TREE_SHA256,
        "workflow_run_attempt": SOURCE_RUN_ATTEMPT,
        "workflow_run_id": SOURCE_RUN_ID,
    }:
        raise ValueError("verified v0.13 source binding changed")
    policies = payload.get("frozen_policies")
    if not isinstance(policies, Mapping) or dict(policies) != {
        "general_strategy_profile_fingerprint": GENERAL_PROFILE_FINGERPRINT,
        "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
        "small_strategy_profile_fingerprint": SMALL_ACCOUNT_PROFILE_FINGERPRINT,
    }:
        raise ValueError("frozen runtime policy binding changed")
    inputs = payload.get("input_readiness")
    if not isinstance(inputs, Mapping):
        raise ValueError("runtime input readiness is missing")
    if inputs.get("scanner_snapshot_ready") is not True:
        raise ValueError("verified scanner source must remain ready")
    if inputs.get("micro_v0_1_runtime_ready") is not False:
        raise ValueError("contract must not claim Micro-v0.1 input completeness")
    if tuple(inputs.get("missing_required_inputs", ())) != MISSING_MICRO_INPUTS:
        raise ValueError("Micro-v0.1 input gap changed")
    authority = payload.get("authority_boundary")
    expected_false = {
        "backtesting_authorized",
        "broker_or_order_access_authorized",
        "databento_access_authorized",
        "market_provider_access_authorized",
        "policy_change_authorized",
        "retrospective_label_access_authorized",
        "runtime_execution_authorized",
        "transcript_access_authorized",
    }
    if not isinstance(authority, Mapping) or set(authority) != expected_false:
        raise ValueError("runtime authority boundary changed")
    if any(authority.values()):
        raise ValueError("unarmed runtime contract grants authority")
    status = payload.get("execution_status")
    if not isinstance(status, Mapping) or dict(status) != {
        "backtesting_started": False,
        "micro_runtime_started": False,
        "provider_calls": 0,
        "retrospective_labels_opened": False,
        "scanner_activation_materialization_started": False,
    }:
        raise ValueError("runtime execution status changed")
    if payload.get("selected_dates") != list(EXPECTED_DATES):
        raise ValueError("runtime dates differ from the frozen panel")
    validate_frozen_policies()
    if payload.get("content_sha256") != CONTRACT_CONTENT_SHA256:
        raise ValueError("registered runtime contract commitment changed")


def validate_registration(
    registration: Mapping[str, object], *, contract_path: str | Path
) -> None:
    _assert_frozen(registration, "runtime registration")
    if registration.get("registration_id") != REGISTRATION_ID:
        raise ValueError("runtime registration ID changed")
    if registration.get("contract_id") != CONTRACT_ID:
        raise ValueError("runtime registration contract changed")
    contract = load_json_object(contract_path)
    validate_contract(contract)
    record = registration.get("contract")
    if not isinstance(record, Mapping):
        raise ValueError("runtime registration contract receipt is missing")
    if record.get("content_sha256") != contract.get("content_sha256"):
        raise ValueError("runtime registration content receipt changed")
    if record.get("file_sha256") != _sha256_path(Path(contract_path)):
        raise ValueError("runtime registration file receipt changed")
    if registration.get("content_sha256") != REGISTRATION_CONTENT_SHA256:
        raise ValueError("registered runtime receipt commitment changed")


def build_scanner_activation_manifest(
    snapshot: Mapping[str, object], *, trading_date: str
) -> dict[str, object]:
    """Reapply the unchanged profiles without running Micro-v0.1."""

    validate_frozen_policies()
    if trading_date not in EXPECTED_DATES:
        raise ValueError("scanner activation date is outside the frozen panel")
    body = dict(snapshot)
    claimed = body.pop("content_sha256", None)
    if claimed != canonical_fingerprint(body):
        raise ValueError("scanner snapshot content hash mismatch")
    if snapshot.get("artifact_id") != "causal-scanner-snapshot-v0.3":
        raise ValueError("unexpected scanner snapshot artifact")
    if snapshot.get("trading_date") != trading_date:
        raise ValueError("scanner snapshot date changed")
    rows = snapshot.get("rows")
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise ValueError("scanner snapshot rows are invalid")
    ordered = sorted(
        (dict(row) for row in rows),
        key=lambda row: (str(row.get("decision_time")), str(row.get("symbol"))),
    )
    if rows != ordered:
        raise ValueError("scanner snapshot rows are not canonically ordered")
    if snapshot.get("row_count") != len(ordered):
        raise ValueError("scanner snapshot row count changed")
    if snapshot.get("ordered_records_sha256") != ordered_snapshot_records_fingerprint(ordered):
        raise ValueError("scanner snapshot ordered-record hash changed")

    profiles = {
        "current-general-2026": current_general_2026(),
        "current-small-account-2026": current_small_account_2026(),
    }
    first: dict[tuple[str, str], dict[str, object]] = {}
    for row in ordered:
        symbol = str(row.get("symbol") or "")
        decision_time = str(row.get("decision_time") or "")
        for profile_id, profile in profiles.items():
            state = profile_eligibility(row, profile)
            if state["quality"] != "reject":
                first.setdefault((symbol, profile_id), row)

    grouped: dict[tuple[str, str], list[str]] = {}
    source_rows: dict[tuple[str, str], dict[str, object]] = {}
    for (symbol, profile_id), row in first.items():
        decision_time = str(row["decision_time"])
        key = (symbol, decision_time)
        grouped.setdefault(key, []).append(profile_id)
        source_rows[key] = row
    profile_order = tuple(profiles)
    activations: list[dict[str, object]] = []
    for (symbol, decision_time), eligible in sorted(
        grouped.items(), key=lambda item: (item[0][1], item[0][0])
    ):
        source_row_sha = canonical_fingerprint(source_rows[(symbol, decision_time)])
        activation = {
            "symbol": symbol,
            "candidate_qualified_at": decision_time,
            "eligible_strategy_profile_ids": [
                profile_id for profile_id in profile_order if profile_id in eligible
            ],
            "scanner_record_content_sha256": source_row_sha,
            "scanner_snapshot_content_sha256": claimed,
        }
        activation["activation_id"] = (
            "activation-" + canonical_fingerprint(
                {"contract_id": CONTRACT_ID, "trading_date": trading_date, **activation}
            )
        )
        activations.append(activation)

    session_end = datetime.combine(
        date.fromisoformat(trading_date), time(10, 0), tzinfo=ET
    ).isoformat()
    requests = [
        {
            "activation_id": row["activation_id"],
            "symbol": row["symbol"],
            "start_inclusive": row["candidate_qualified_at"],
            "end_exclusive_new_york": session_end,
            "required_inputs": list(MISSING_MICRO_INPUTS),
        }
        for row in activations
    ]
    result: dict[str, object] = {
        "schema_version": 1,
        "artifact_type": "sealed_historical_scanner_activation_and_micro_input_plan",
        "contract_id": CONTRACT_ID,
        "trading_date": trading_date,
        "source_scanner_snapshot_content_sha256": claimed,
        "general_strategy_profile_fingerprint": GENERAL_PROFILE_FINGERPRINT,
        "small_strategy_profile_fingerprint": SMALL_ACCOUNT_PROFILE_FINGERPRINT,
        "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
        "activation_count": len(activations),
        "activations": activations,
        "micro_input_request_count": len(requests),
        "micro_input_requests": requests,
        "micro_runtime_complete": False,
        "provider_calls": 0,
        "retrospective_labels_loaded": False,
        "backtesting_started": False,
    }
    result["content_sha256"] = canonical_fingerprint(result)
    return result


def materialize_scanner_activation_plan(
    *, snapshot_root: str | Path, output_root: str | Path
) -> dict[str, object]:
    """Write the provider-free scanner activation/request plan exactly once."""

    frozen_root = Path(snapshot_root).resolve()
    target = Path(output_root).resolve()
    if target == frozen_root or frozen_root in target.parents:
        raise ValueError("runtime output must be outside the immutable source artifact")
    validate_final_snapshot(frozen_root)
    if target.exists():
        if not target.is_dir() or any(target.iterdir()):
            raise FileExistsError("runtime preparation output must be absent or empty")
    else:
        target.mkdir(parents=True)
    source = frozen_root / "source/causal-scanner-snapshot-v0.3"
    date_hashes: dict[str, str] = {}
    total_activations = 0
    total_requests = 0
    for trading_date in EXPECTED_DATES:
        snapshot = load_json_object(source / trading_date / "scanner-snapshot.json")
        manifest = build_scanner_activation_manifest(snapshot, trading_date=trading_date)
        output = target / "dates" / f"{trading_date}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        date_hashes[trading_date] = _sha256_path(output)
        total_activations += int(manifest["activation_count"])
        total_requests += int(manifest["micro_input_request_count"])
    root_manifest: dict[str, object] = {
        "schema_version": 1,
        "artifact_type": "sealed_historical_scanner_activation_plan_bundle",
        "contract_id": CONTRACT_ID,
        "source_artifact_id": SOURCE_ARTIFACT_ID,
        "source_artifact_zip_sha256": SOURCE_ZIP_SHA256,
        "source_tree_content_sha256": SOURCE_TREE_SHA256,
        "dates": list(EXPECTED_DATES),
        "date_file_sha256": date_hashes,
        "activation_count": total_activations,
        "micro_input_request_count": total_requests,
        "micro_runtime_complete": False,
        "provider_calls": 0,
        "backtesting_started": False,
        "next_gate": "bounded_candidate_micro_input_quote_and_acquisition",
    }
    root_manifest["content_sha256"] = canonical_fingerprint(root_manifest)
    (target / "manifest.json").write_text(
        json.dumps(root_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return root_manifest


def validate_final_snapshot(snapshot_root: str | Path) -> dict[str, object]:
    """Deeply bind an extracted final v0.13 artifact without running strategy code."""

    root = Path(snapshot_root)
    report_path = root / "recovery-report.json"
    if _sha256_path(report_path) != SOURCE_REPORT_FILE_SHA256:
        raise ValueError("final v0.13 recovery-report file hash changed")
    report = load_json_object(report_path)
    validate_recovery_report_v13(report)
    if report.get("content_sha256") != SOURCE_REPORT_CONTENT_SHA256:
        raise ValueError("final v0.13 recovery-report content hash changed")
    source_root = root / "source"
    inventory = inventory_source_tree(
        source_root, allow_scanner_snapshot_addition=True
    )
    if (
        inventory.get("file_count") != SOURCE_FILE_COUNT
        or inventory.get("directory_count") != SOURCE_DIRECTORY_COUNT
        or inventory.get("tree_content_sha256") != SOURCE_TREE_SHA256
        or sum(int(row["size_bytes"]) for row in inventory["files"])
        != SOURCE_RETAINED_BYTES
    ):
        raise ValueError("final v0.13 source inventory changed")
    intermediate_path = root / "v13-recovery/intermediate-checkpoint.json"
    if _sha256_path(intermediate_path) != SOURCE_INTERMEDIATE_FILE_SHA256:
        raise ValueError("final v0.13 intermediate-checkpoint file hash changed")
    intermediate = load_json_object(intermediate_path)
    if intermediate.get("content_sha256") != SOURCE_INTERMEDIATE_CONTENT_SHA256:
        raise ValueError("final v0.13 intermediate-checkpoint content hash changed")
    validate_intermediate_checkpoint_v13(
        intermediate,
        source_root=source_root,
        binding=report["parent_provider_checkpoint"]["binding"],
        environment_comparison=report["environment_comparison"],
        provenance=report["workflow_provenance"],
    )
    expected_files = {
        str(row["path"]): str(row["sha256"])
        for row in intermediate["source_inventory"]["files"]
    }
    observed_files = {
        str(row["path"]): str(row["sha256"]) for row in inventory["files"]
    }
    if observed_files != expected_files:
        raise ValueError("final v0.13 source file hashes changed")
    return {
        "schema_version": 1,
        "source_verified": True,
        "scanner_snapshot_ready": True,
        "micro_v0_1_runtime_ready": False,
        "missing_required_inputs": list(MISSING_MICRO_INPUTS),
        "provider_calls": 0,
        "runtime_started": False,
    }


__all__ = [
    "CONTRACT_ID",
    "EXPECTED_DATES",
    "MISSING_MICRO_INPUTS",
    "build_scanner_activation_manifest",
    "materialize_scanner_activation_plan",
    "validate_contract",
    "validate_final_snapshot",
    "validate_frozen_policies",
    "validate_registration",
]
