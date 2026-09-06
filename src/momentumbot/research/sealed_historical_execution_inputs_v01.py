"""Provider-free registration of exact historical Micro execution/status inputs.

This historical adapter reads only the pinned, completed Micro decision bundle.
It never replays Micro or calls a provider. Prospective dates and artifact IDs
remain untouched; only their frozen quote/status request mechanics are reused.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path

import pandas as pd

from momentumbot.research.prospective_market_input_capture import (
    CONTRACT_CONTENT_SHA256 as CAPTURE_CONTRACT_SHA256,
    DATASET, END_EXCLUSIVE_PAD_NS, POST_DECISION_CAPTURE_NS,
    PRE_DECISION_QUOTE_NS, SCHEMAS, STYPE_IN, VENUE_SCOPE,
    validate_capture_contract,
)
from momentumbot.research.sealed_historical_micro_inputs_v01 import (
    PLAN_CONTENT_SHA256, PLAN_FILE_SHA256, file_sha, frozen,
)
from momentumbot.research.sealed_historical_micro_runtime_v01 import validate_runtime_output
from momentumbot.research.sealed_historical_scanner_micro_runtime_v02 import (
    EXPECTED_DATES, MICRO_POLICY_FINGERPRINT, validate_frozen_policies,
)
from momentumbot.research.sealed_historical_source_checkpoint_v01 import canonical_fingerprint

CONTRACT_ID = "sealed-historical-execution-input-registration-v0.1"
PANEL_ID = "sealed-historical-walk-forward-v0.1"
PARENT_COMMIT = "3d20c7efdcb53b8d3bfa46b550d41001108a8dac"
PARENT_TREE = "1ca85c8377483f6f4cdf50cc51bbfa584c8be807"
MICRO_CONTENT_SHA256 = "cca8dbf0fcf37dd05dc77355de06bf384f37c081152302ce750c939550100904"
MICRO_FILE_SHA256 = "2f46191a7a0e6ff085c58d589857b65617e33ae00ff9de018565ee8803d2e7cf"
MICRO_INVENTORY_SHA256 = "06b285120bab6acd21836a02b44969b1128dcc182ab7ea0ee444dc4384608f03"
WALK_FORWARD_SHA256 = "93a4316a4ef785e30ebc393ec140fa02ea23027aa9cd85673d34401b3bca3452"
EXECUTION_CONTRACT_SHA256 = "14812b9f25b5ea7230254ed86b1e0eaa30fffe3dc13b1ee141b19770706090f9"
OUTPUT_FILES = {"opportunity-manifest.json", "request-manifest.json", "freeze-manifest.json"}
DECISION_FIELDS = {
    "activation_id", "candidate_qualified_at", "decision_at",
    "eligible_strategy_profile_ids", "micro_runtime_content_sha256",
    "plan", "plan_id", "symbol",
}


def seal(body: dict) -> dict:
    return {**body, "content_sha256": canonical_fingerprint(body)}


def _require_exact(actual: dict, expected: dict, label: str) -> None:
    # Fingerprints distinguish false/0 and true/1, unlike Python equality.
    if canonical_fingerprint(actual) != canonical_fingerprint(expected):
        raise ValueError(f"{label} differs from exact historical derivation")


def registered_contract() -> dict:
    return seal({
        "schema_version": 1,
        "contract_id": CONTRACT_ID,
        "artifact_type": "preregistered_provider_free_historical_execution_input_plan",
        "panel_id": PANEL_ID,
        "frozen_parent": {
            "commit_sha": PARENT_COMMIT, "tree_sha": PARENT_TREE,
            "micro_manifest_content_sha256": MICRO_CONTENT_SHA256,
            "micro_manifest_file_sha256": MICRO_FILE_SHA256,
            "micro_inventory_content_sha256": MICRO_INVENTORY_SHA256,
            "scanner_manifest_content_sha256": PLAN_CONTENT_SHA256,
            "scanner_manifest_file_sha256": PLAN_FILE_SHA256,
            "walk_forward_content_sha256": WALK_FORWARD_SHA256,
            "market_input_capture_content_sha256": CAPTURE_CONTRACT_SHA256,
            "execution_contract_content_sha256": EXECUTION_CONTRACT_SHA256,
            "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
        },
        "dates": list(EXPECTED_DATES),
        "scope": {
            "decision_count": 109, "activation_count": 192,
            "triggered_activation_count": 48, "no_trigger_activation_count": 144,
            "unavailable_activation_count": 0, "symbol_date_count": 45,
            "request_count": 90, "dates_with_decisions": 25,
            "profile_union_preserved": True,
            "opportunity_identity": "historical_panel_date_activation_plan_symbol_decision_ns_runtime_prefix",
            "source_decisions_selected_by_account_or_execution_scenario": False,
        },
        "source_scope": {
            "dataset": DATASET, "schemas": list(SCHEMAS), "stype_in": STYPE_IN,
            "venue_scope": VENUE_SCOPE, "causal_clock": "ts_recv",
            "mbp1_start_before_earliest_decision_ns": PRE_DECISION_QUOTE_NS,
            "capture_after_latest_decision_ns": POST_DECISION_CAPTURE_NS,
            "end_exclusive_pad_ns": END_EXCLUSIVE_PAD_NS,
            "status_start_rule": "00:00:00Z_on_registered_trading_date",
            "no_substitute_symbols_dates_venues_schemas_or_sip_proxy": True,
            "unknown_or_missing_initial_status": "unavailable_never_assume_trading",
            "equal_quote_status_ts_recv": "unavailable_cross_schema_order_ambiguity",
            "unavailable_inputs_are_zero_trigger_results": False,
        },
        "next_gate": {
            "stage": "exact_historical_execution_input_metadata_quote",
            "allowed_methods_in_future_quote": [
                "historical.metadata.get_billable_size", "historical.metadata.get_cost",
            ],
            "maximum_metadata_calls_in_future_quote": 180,
            "quote_requires_own_tested_historical_adapter_and_exact_parent_bound_record": True,
            "download_requires_successful_exact_quote_and_bounded_consumption_record": True,
            "account_runtime_requires_independently_verified_execution_and_management_inputs": True,
            "missing_input_behavior": "retain_unavailable_without_replacement_or_simulation",
        },
        "boundary": {
            "provider_calls": 0, "metadata_quote_executed": False,
            "timeseries_acquisition_authorized_by_this_registration": False,
            "databento_credit_authorized_usd": "0", "credentials_accessed": False,
            "micro_reexecuted": False, "accounts_or_fills_simulated": False,
            "backtesting_executed": False, "paper_or_live_orders_authorized": False,
            "retrospective_labels_or_transcripts_loaded": False, "policy_changed": False,
        },
    })


def _inventory(root: Path, expected_paths: set[str]) -> dict[str, str]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("artifact root must be a regular directory")
    paths = list(root.rglob("*"))
    if any(path.is_symlink() or not (path.is_file() or path.is_dir()) for path in paths):
        raise ValueError("artifact contains a link or nonregular member")
    observed = {p.relative_to(root).as_posix() for p in paths if p.is_file()}
    if observed != expected_paths:
        raise ValueError("artifact file inventory changed")
    return {relative: file_sha(root / relative) for relative in sorted(observed)}


def validate_parent(*, repo_root: Path, micro_root: Path, scanner_root: Path) -> dict:
    inventory = _inventory(micro_root, {"manifest.json"} | {f"dates/{d}.json" for d in EXPECTED_DATES})
    if inventory["manifest.json"] != MICRO_FILE_SHA256 or canonical_fingerprint(inventory) != MICRO_INVENTORY_SHA256:
        raise ValueError("exact completed Micro parent bytes changed")
    if file_sha(scanner_root / "manifest.json") != PLAN_FILE_SHA256:
        raise ValueError("exact frozen scanner plan changed")
    parent = validate_runtime_output(output_root=micro_root, plan_root=scanner_root)
    if parent["content_sha256"] != MICRO_CONTENT_SHA256:
        raise ValueError("completed Micro parent content changed")
    validate_frozen_policies()
    strategy = repo_root / "research/strategy"
    validate_capture_contract(frozen(strategy / "prospective-market-input-capture-v0.1.json"))
    for name, expected in (
        ("sealed-historical-walk-forward-v0.1.json", WALK_FORWARD_SHA256),
        ("prospective-management-execution-v0.1.json", EXECUTION_CONTRACT_SHA256),
    ):
        if frozen(strategy / name)["content_sha256"] != expected:
            raise ValueError("frozen historical/execution policy contract changed")
    _require_exact(frozen(strategy / f"{CONTRACT_ID}.json"), registered_contract(), "registration contract")
    return parent


def _opportunities(day: dict) -> list[dict]:
    """Project a verified causal source without carrying prices or outcomes."""
    rows = []
    trading_date = day["trading_date"]
    for decision in day["decisions"]:
        if set(decision) != DECISION_FIELDS:
            raise ValueError("Micro decision fields changed")
        stamp = pd.Timestamp(decision["decision_at"])
        qualified = pd.Timestamp(decision["candidate_qualified_at"])
        if stamp.tzinfo is None or qualified.tzinfo is None or stamp < qualified:
            raise ValueError("Micro decision must have a causal aware timestamp")
        if stamp.tz_convert("America/New_York").date().isoformat() != trading_date:
            raise ValueError("Micro decision date changed")
        identity = {
            "panel_id": PANEL_ID, "trading_date": trading_date,
            "activation_id": decision["activation_id"], "plan_id": decision["plan_id"],
            "symbol": decision["symbol"], "decision_ts_ns": stamp.value,
            "micro_runtime_content_sha256": decision["micro_runtime_content_sha256"],
        }
        rows.append({
            **identity, "opportunity_id": f"opportunity-{canonical_fingerprint(identity)}",
            "candidate_qualified_ts_ns": qualified.value,
            "eligible_strategy_profile_ids": list(decision["eligible_strategy_profile_ids"]),
            "source_decision_content_sha256": canonical_fingerprint(decision),
            "source_date_content_sha256": day["content_sha256"],
        })
    return sorted(rows, key=lambda r: (r["decision_ts_ns"], r["symbol"], r["opportunity_id"]))


def _requests(opportunities: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for row in opportunities:
        grouped[(row["trading_date"], row["symbol"])].append(row["decision_ts_ns"])
    requests = []
    for (day, symbol), stamps in sorted(grouped.items()):
        # No float conversion of decision nanoseconds, even at submicrosecond boundaries.
        end = max(stamps) + POST_DECISION_CAPTURE_NS + END_EXCLUSIVE_PAD_NS
        midnight = int(datetime.fromisoformat(f"{day}T00:00:00+00:00").timestamp()) * 1_000_000_000
        for schema, start in (("mbp-1", min(stamps) - PRE_DECISION_QUOTE_NS), ("status", midnight)):
            requests.append({
                "request_id": f"{day}-{symbol}-{schema}", "trading_date": day,
                "dataset": DATASET, "schema": schema, "symbols": [symbol],
                "stype_in": STYPE_IN, "start_ns": start, "end_ns": end,
                "end_exclusive": True,
            })
    return requests


def build_registration(*, repo_root: Path, micro_root: Path, scanner_root: Path) -> dict[str, dict]:
    parent = validate_parent(repo_root=repo_root, micro_root=micro_root, scanner_root=scanner_root)
    opportunities, dates = [], []
    for day in EXPECTED_DATES:
        daily = frozen(micro_root / "dates" / f"{day}.json")
        rows = _opportunities(daily)
        opportunities.extend(rows)
        dates.append({
            "trading_date": day, "decision_count": len(rows),
            "activation_count": daily["activation_count"],
            "no_trigger_activation_count": sum(r["status"] == "no_trigger" for r in daily["outcomes"]),
            "unavailable_activation_count": daily["unavailable_count"],
            "request_count": 2 * len({r["symbol"] for r in rows}),
            "input_plan_status": "unquoted_requests" if rows else "not_applicable_no_micro_decisions",
            "source_date_content_sha256": daily["content_sha256"],
            "source_date_file_sha256": file_sha(micro_root / "dates" / f"{day}.json"),
        })
    if len(opportunities) != 109 or len({r["opportunity_id"] for r in opportunities}) != 109:
        raise ValueError("historical opportunity coverage changed")
    requests = _requests(opportunities)
    if len(requests) != 90:
        raise ValueError("historical request coverage changed")
    contract = registered_contract()
    common = {"schema_version": 1, "contract_id": CONTRACT_ID, "panel_id": PANEL_ID,
              "contract_content_sha256": contract["content_sha256"]}
    opportunity = seal({
        **common, "artifact_type": "frozen_label_blind_historical_execution_opportunities",
        "micro_manifest_content_sha256": MICRO_CONTENT_SHA256,
        "micro_manifest_file_sha256": MICRO_FILE_SHA256,
        "micro_inventory_content_sha256": MICRO_INVENTORY_SHA256,
        "input_bindings": {key: parent[key] for key in ("source", "micro_input", "session_input")},
        "dates": dates, "opportunity_count": len(opportunities), "opportunities": opportunities,
        "profile_decision_counts": {p: sum(p in r["eligible_strategy_profile_ids"] for r in opportunities)
                                    for p in ("current-general-2026", "current-small-account-2026")},
        "account_scarcity_applied": False, "execution_scenario_applied": False,
        "retrospective_labels_loaded": False,
    })
    request = seal({
        **common, "artifact_type": "offline_exact_unquoted_historical_market_input_requests",
        "opportunity_manifest_content_sha256": opportunity["content_sha256"],
        "dates": list(EXPECTED_DATES), "opportunity_count": len(opportunities),
        "request_count": len(requests), "requests": requests,
        "request_list_content_sha256": canonical_fingerprint(requests),
        "provider_metadata_quote_made": False, "provider_timeseries_request_made": False,
        "provider_purchase_authorized": False, "databento_credit_authorized_usd": "0",
    })
    freeze = seal({
        **common, "artifact_type": "historical_execution_input_registration_handoff",
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "micro_manifest_content_sha256": MICRO_CONTENT_SHA256,
        "opportunity_manifest_content_sha256": opportunity["content_sha256"],
        "request_manifest_content_sha256": request["content_sha256"],
        "dates": list(EXPECTED_DATES), "opportunity_count": 109, "request_count": 90,
        "explicit_no_decision_dates": [d["trading_date"] for d in dates if not d["decision_count"]],
        "next_gate": contract["next_gate"], "boundary": contract["boundary"],
    })
    return {"opportunity-manifest.json": opportunity, "request-manifest.json": request,
            "freeze-manifest.json": freeze}


def _encoded(payload: dict) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def write_registration(*, output_root: Path, **inputs) -> dict:
    bundle = build_registration(**inputs)
    if output_root.exists() and (not output_root.is_dir() or any(output_root.iterdir())):
        raise ValueError("historical input plan is write-once; existing evidence is preserved")
    if output_root.is_symlink():
        raise ValueError("historical input plan root must not be a symlink")
    output_root.mkdir(parents=True, exist_ok=True)
    for name, payload in bundle.items():
        with (output_root / name).open("xb") as handle:
            handle.write(_encoded(payload))
    return validate_registration(output_root=output_root, **inputs)


def validate_registration(*, output_root: Path, **inputs) -> dict:
    expected = build_registration(**inputs)
    inventory = _inventory(output_root, OUTPUT_FILES)
    for name, payload in expected.items():
        observed = frozen(output_root / name)
        _require_exact(observed, payload, name)
        if (output_root / name).read_bytes() != _encoded(payload):
            raise ValueError("historical input plan file serialization changed")
    return seal({
        "schema_version": 1, "artifact_type": "historical_execution_input_registration_validation",
        "contract_id": CONTRACT_ID, "verification_passed": True,
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "contract_content_sha256": registered_contract()["content_sha256"],
        "file_sha256": inventory, "inventory_content_sha256": canonical_fingerprint(inventory),
        "opportunity_count": 109, "request_count": 90, "date_count": 30,
        "symbol_date_count": 45, "provider_calls": 0,
        "micro_reexecuted": False, "accounts_or_fills_simulated": False,
        "backtesting_executed": False, "retrospective_labels_loaded": False,
    })
