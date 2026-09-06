"""Provider-free historical adapter for the frozen Micro-v0.1 policy.

The adapter composes only the exact final v0.13 source, frozen scanner
activations, independently verified SIP/warmup capture, and independently
verified raw-minute supplement.  It emits causal Micro trigger decisions; it
does not read retrospective evidence or simulate fills, accounts, or exits.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, time
import gzip
import hashlib
import json
from pathlib import Path
from statistics import median
from typing import Mapping
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.indicators import completed_bar_support_series
from momentumbot.micro_bars import aggregate_trade_bars
from momentumbot.micro_policy import micro_v0_1_policy
from momentumbot.models import current_general_2026
from momentumbot.research.prospective_daily_source import (
    MicroTriggerDecision,
    ProfileActivation,
    build_micro_trigger_decisions,
)
from momentumbot.research.sealed_historical_micro_inputs_v01 import (
    PLAN_CONTENT_SHA256,
    PLAN_FILE_SHA256,
    file_sha,
    frozen,
)
from momentumbot.research.sealed_historical_scanner_micro_runtime_v02 import (
    EXPECTED_DATES,
    MICRO_POLICY_FINGERPRINT,
    SOURCE_ARTIFACT_ID,
    SOURCE_REPORT_CONTENT_SHA256,
    SOURCE_REPORT_FILE_SHA256,
    SOURCE_TREE_SHA256,
    SOURCE_ZIP_SHA256,
    validate_final_snapshot,
    validate_frozen_policies,
)
from momentumbot.research.sealed_historical_source_checkpoint_v01 import canonical_fingerprint
from momentumbot.scanner_source_inputs_v03 import load_scanner_source_input_bundle

CONTRACT_ID = "sealed-historical-micro-runtime-v0.1"
CONTRACT_CONTENT_SHA256 = "7de72d106575468b716ed143c3304cc63adc0eee1ca7e44039054933691c58c6"
ET = ZoneInfo("America/New_York")

MICRO_INPUT_RUN_ID = 34_053_730_042
MICRO_INPUT_ARTIFACT_ID = 9_995_887_799
MICRO_INPUT_ZIP_SHA256 = "d31eac851c1246ce23025e9518562ed3f41b8f818d42b8de707a6d86d307be99"
MICRO_INPUT_REPORT_FILE_SHA256 = "9d9301ae407540d2d391080d0974868f2c594c807c8722809fbac7c5a72da8a3"
MICRO_INPUT_REPORT_CONTENT_SHA256 = "cd21c857a2fd28e819cb83811c67c05ad4bb45b62a4de9b699a88d001d400f50"
MICRO_INPUT_INVENTORY_FILE_SHA256 = "b9706f87d3509be57c620fe9f583441350fdaf1683f2b149eacdb2f4be6d6be7"
MICRO_INPUT_INVENTORY_CONTENT_SHA256 = "c717abec7ce0367c365ffde1dd045a92fea9cc7675545bb28aa81b57ca824dfe"
MICRO_INPUT_REQUEST_MANIFEST_SHA256 = "8efb12cdd14496d90da1c39d8d520de0e5163203b8bc3bc201c4bcbd2317c871"

SESSION_INPUT_RUN_ID = 34_054_580_516
SESSION_INPUT_ARTIFACT_ID = 9_995_587_996
SESSION_INPUT_ZIP_SHA256 = "d689f493c10996bee7eddde68d62812e7850fc322caa2d530d33a97c84878e3f"
SESSION_INPUT_REPORT_FILE_SHA256 = "ebd2f02b3df83fbc5cb45b8fee86120e278c3a41c8a1d07e87e972bef6c26b9d"
SESSION_INPUT_REPORT_CONTENT_SHA256 = "9fc1c5fda0942ded03cfb3a574d69802bae927dcf31f538c917cbfb33af103e0"
SESSION_INPUT_INVENTORY_FILE_SHA256 = "cc489fcf61690c020586ed43c48ed277ca4829834235b5b59620c5839526c4d7"
SESSION_INPUT_INVENTORY_CONTENT_SHA256 = "8e2c29219a11e8e510f53daf39cff887be0984c27f976f2be6cc35e55794f7d8"


def _write_frozen(path: Path, body: Mapping[str, object]) -> dict[str, object]:
    value = {**body, "content_sha256": canonical_fingerprint(body)}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return value


def _validate_capture_root(
    root: Path,
    *,
    expected_files: int,
    expected_requests: int,
    expected_attempts: int,
    report_file_sha256: str,
    report_content_sha256: str,
    inventory_file_sha256: str,
    inventory_content_sha256: str,
) -> tuple[dict, dict, dict[str, dict]]:
    report_path = root / "capture-report.json"
    inventory_path = root / "capture-inventory.json"
    if file_sha(report_path) != report_file_sha256 or file_sha(inventory_path) != inventory_file_sha256:
        raise ValueError("captured Micro input metadata file hash changed")
    report = frozen(report_path)
    inventory = frozen(inventory_path)
    if report["content_sha256"] != report_content_sha256 or inventory["content_sha256"] != inventory_content_sha256:
        raise ValueError("captured Micro input metadata content hash changed")
    actual = {p.relative_to(root).as_posix(): file_sha(p) for p in sorted(root.rglob("*")) if p.is_file()}
    if len(actual) != expected_files or set(inventory["files"]) != set(actual) - {"capture-inventory.json"}:
        raise ValueError("captured Micro input inventory changed")
    for relative, claimed in inventory["files"].items():
        if actual.get(relative) != claimed:
            raise ValueError("captured Micro input file hash changed")
    if (report.get("status") != "complete" or report.get("logical_requests_completed") != expected_requests
            or len(report.get("receipts", ())) != expected_requests or inventory.get("complete") is not True
            or inventory.get("provider_attempts") != expected_attempts or inventory.get("blocked_attempts") != 0):
        raise ValueError("captured Micro input completeness or ledger changed")
    receipts = {row["request_id"]: row for row in report["receipts"]}
    if len(receipts) != expected_requests:
        raise ValueError("captured Micro input receipts repeat an identity")
    return report, inventory, receipts


def validate_runtime_contract(path: Path) -> dict:
    contract = frozen(path)
    if contract.get("contract_id") != CONTRACT_ID or contract.get("content_sha256") != CONTRACT_CONTENT_SHA256:
        raise ValueError("historical Micro runtime contract changed")
    if contract.get("dates") != list(EXPECTED_DATES):
        raise ValueError("historical Micro runtime dates changed")
    boundary = contract.get("execution_boundary")
    if not isinstance(boundary, Mapping) or boundary.get("micro_runtime_execution_authorized") is not True:
        raise ValueError("historical Micro runtime authority is missing")
    for prohibited in (
        "account_or_order_activity", "backtesting_authorized", "databento_access",
        "fills_or_exits_simulated", "market_provider_access", "policy_change_authorized",
        "retrospective_labels_or_transcripts",
    ):
        if boundary.get(prohibited) is not False:
            raise ValueError("historical Micro runtime authority expanded")
    if contract.get("frozen_mechanics", {}).get("micro_policy_fingerprint") != MICRO_POLICY_FINGERPRINT:
        raise ValueError("historical Micro runtime policy changed")
    return contract


def validate_runtime_inputs(
    *,
    snapshot_root: Path,
    micro_input_root: Path,
    micro_input_zip: Path,
    session_input_root: Path,
    session_input_zip: Path,
    plan_root: Path,
    contract_path: Path,
) -> dict[str, object]:
    validate_frozen_policies()
    contract = validate_runtime_contract(contract_path)
    validate_final_snapshot(snapshot_root)
    if file_sha(micro_input_zip) != MICRO_INPUT_ZIP_SHA256 or file_sha(session_input_zip) != SESSION_INPUT_ZIP_SHA256:
        raise ValueError("exact captured Micro input ZIP digest changed")
    micro_report, micro_inventory, micro_receipts = _validate_capture_root(
        micro_input_root, expected_files=688, expected_requests=340, expected_attempts=2264,
        report_file_sha256=MICRO_INPUT_REPORT_FILE_SHA256,
        report_content_sha256=MICRO_INPUT_REPORT_CONTENT_SHA256,
        inventory_file_sha256=MICRO_INPUT_INVENTORY_FILE_SHA256,
        inventory_content_sha256=MICRO_INPUT_INVENTORY_CONTENT_SHA256,
    )
    session_report, session_inventory, session_receipts = _validate_capture_root(
        session_input_root, expected_files=348, expected_requests=170, expected_attempts=170,
        report_file_sha256=SESSION_INPUT_REPORT_FILE_SHA256,
        report_content_sha256=SESSION_INPUT_REPORT_CONTENT_SHA256,
        inventory_file_sha256=SESSION_INPUT_INVENTORY_FILE_SHA256,
        inventory_content_sha256=SESSION_INPUT_INVENTORY_CONTENT_SHA256,
    )
    plan = frozen(plan_root / "manifest.json")
    if (file_sha(plan_root / "manifest.json") != PLAN_FILE_SHA256
            or plan["content_sha256"] != PLAN_CONTENT_SHA256
            or plan["dates"] != list(EXPECTED_DATES)
            or plan["activation_count"] != 192):
        raise ValueError("frozen scanner activation plan changed")
    requests = frozen(micro_input_root / "requests.json")["requests"]
    if canonical_fingerprint(requests) != MICRO_INPUT_REQUEST_MANIFEST_SHA256:
        raise ValueError("Micro input request manifest changed")
    session_requests = frozen(session_input_root / "requests.json")["requests"]
    return {
        "micro_report": micro_report, "micro_inventory": micro_inventory,
        "micro_receipts": micro_receipts, "micro_requests": {r["request_id"]: r for r in requests},
        "session_report": session_report, "session_inventory": session_inventory,
        "session_receipts": session_receipts, "session_requests": {r["request_id"]: r for r in session_requests},
        "plan": plan, "contract": contract,
    }


def causal_raw_to_split_factor(
    raw_close: pd.Series, split_close: pd.Series, *, qualified_at: pd.Timestamp
) -> tuple[float, dict[str, object]]:
    """Infer one mechanical price-basis factor from completed preactivation pairs."""
    if qualified_at.tzinfo is None:
        raise ValueError("activation timestamp must be timezone-aware")
    pairs = pd.concat([raw_close.rename("raw"), split_close.rename("split")], axis=1).dropna()
    pairs = pairs.loc[pairs.index + pd.Timedelta(minutes=1) <= qualified_at]
    if pairs.empty or (pairs <= 0).any().any():
        raise ValueError("causal raw/split price-basis pairs are unavailable")
    ratios = (pairs["raw"] / pairs["split"]).astype(float)
    factor = float(median(ratios.tolist()))
    relative_deviation = ((ratios / factor) - 1.0).abs()
    if factor <= 0 or float(relative_deviation.max()) > 0.001:
        raise ValueError("causal raw/split price basis is not mechanically stable")
    evidence = {
        "method": "median_raw_close_divided_by_split_close_from_completed_preactivation_pairs",
        "pair_count": len(pairs),
        "last_pair_available_at": (pairs.index[-1] + pd.Timedelta(minutes=1)).isoformat(),
        "raw_to_split_factor": factor,
        "maximum_relative_pair_deviation": float(relative_deviation.max()),
        "ordered_pair_content_sha256": canonical_fingerprint([
            {"bar_started_at": stamp.isoformat(), "raw_close": float(row.raw), "split_close": float(row.split)}
            for stamp, row in pairs.iterrows()
        ]),
    }
    evidence["content_sha256"] = canonical_fingerprint(evidence)
    return factor, evidence


def normalize_warmup_to_raw(warmup: pd.DataFrame, factor: float) -> pd.DataFrame:
    if factor <= 0 or warmup.empty:
        raise ValueError("warmup normalization requires positive causal evidence")
    result = warmup.copy()
    for column in ("open", "high", "low", "close", "vwap"):
        result[column] = pd.to_numeric(result[column], errors="raise") * factor
    return result


def _read_rows(path: Path) -> list[dict]:
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            rows.append(json.loads(line))
    if not rows:
        raise ValueError("required captured Micro input tape is unavailable")
    return rows


def _frame(rows: list[dict], *, kind: str) -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp(row["t"]) for row in rows])
    if index.tz is None or not index.is_monotonic_increasing:
        raise ValueError("captured Micro input timestamps changed")
    if kind == "trades":
        return pd.DataFrame({
            "price": [row["p"] for row in rows], "size": [row["s"] for row in rows],
            "conditions": [row["c"] for row in rows], "tape": [row["z"] for row in rows],
        }, index=index)
    return pd.DataFrame({
        "open": [row["o"] for row in rows], "high": [row["h"] for row in rows],
        "low": [row["l"] for row in rows], "close": [row["c"] for row in rows],
        "volume": [row["v"] for row in rows], "vwap": [row["vw"] for row in rows],
    }, index=index)


def _receipt_for(receipts: Mapping[str, dict], *, trading_date: str, symbol: str, kind: str) -> dict:
    matches = [row for row in receipts.values() if row["path"] == f"dates/{trading_date}/{symbol}-{kind}.jsonl.gz"]
    if len(matches) != 1:
        raise ValueError("exact captured Micro input receipt is missing")
    return matches[0]


def execute_runtime(
    *, snapshot_root: Path, micro_input_root: Path, micro_input_zip: Path,
    session_input_root: Path, session_input_zip: Path, plan_root: Path,
    contract_path: Path, output_root: Path,
) -> dict[str, object]:
    if output_root.exists() and (not output_root.is_dir() or any(output_root.iterdir())):
        raise FileExistsError("historical Micro runtime output must be new and empty")
    output_root.mkdir(parents=True, exist_ok=True)
    validated = validate_runtime_inputs(
        snapshot_root=snapshot_root, micro_input_root=micro_input_root, micro_input_zip=micro_input_zip,
        session_input_root=session_input_root, session_input_zip=session_input_zip,
        plan_root=plan_root, contract_path=contract_path,
    )
    total_decisions = total_no_trigger = total_activations = 0
    date_hashes: dict[str, str] = {}
    basis_hashes: dict[str, str] = {}
    source_inputs_root = snapshot_root / "source/causal-scanner-source-inputs-v0.2"
    for trading_date in EXPECTED_DATES:
        day_plan = frozen(plan_root / "dates" / f"{trading_date}.json")
        source, source_manifest = load_scanner_source_input_bundle(
            source_inputs_root / trading_date, profile=current_general_2026()
        )
        grouped: dict[str, list[dict]] = {}
        for row in day_plan["activations"]:
            grouped.setdefault(row["symbol"], []).append(row)
        decisions: list[MicroTriggerDecision] = []
        outcomes = []
        basis = {}
        replay_end = pd.Timestamp(datetime.combine(date.fromisoformat(trading_date), time(10), ET))
        for symbol, activation_rows in sorted(grouped.items()):
            earliest = min(pd.Timestamp(row["candidate_qualified_at"]) for row in activation_rows)
            raw_source = source.candidate_raw_minute_bars_by_symbol[symbol]
            split_source = source.rank_split_minute_bars_by_symbol[symbol]
            factor, evidence = causal_raw_to_split_factor(
                raw_source["close"], split_source["close"], qualified_at=earliest
            )
            basis[symbol] = evidence
            trade_receipt = _receipt_for(validated["micro_receipts"], trading_date=trading_date, symbol=symbol, kind="sip_trades")
            warmup_receipt = _receipt_for(validated["micro_receipts"], trading_date=trading_date, symbol=symbol, kind="ema_warmup_1m_split")
            session_receipt = _receipt_for(validated["session_receipts"], trading_date=trading_date, symbol=symbol, kind="session_1m_raw")
            trades = _frame(_read_rows(micro_input_root / trade_receipt["path"]), kind="trades")
            warmup = _frame(_read_rows(micro_input_root / warmup_receipt["path"]), kind="bars")
            warmup = normalize_warmup_to_raw(warmup, factor)
            session = _frame(_read_rows(session_input_root / session_receipt["path"]), kind="bars")
            session = session.loc[session.index + pd.Timedelta(minutes=1) < replay_end]
            if not session.index.equals(raw_source.index):
                raise ValueError("raw session supplement timestamp coverage differs from the frozen source")
            if not session["close"].astype(float).equals(raw_source["close"].astype(float)):
                raise ValueError("raw session supplement closes differ from the frozen source")
            if not session["volume"].astype(float).equals(raw_source["volume"].astype(float)):
                raise ValueError("raw session supplement volumes differ from the frozen source")
            support = completed_bar_support_series(
                session, ema_span=current_general_2026().ema_span, bar_duration="1min", ema_warmup=warmup
            )
            bars = aggregate_trade_bars(trades, f"{micro_v0_1_policy().micro_bar_interval_seconds}s")
            input_hash = canonical_fingerprint({
                "trading_date": trading_date, "symbol": symbol,
                "source_manifest_content_sha256": source_manifest["content_sha256"],
                "basis_content_sha256": evidence["content_sha256"],
                "sip_trade_logical_sha256": trade_receipt["logical_sha256"],
                "ema_warmup_logical_sha256": warmup_receipt["logical_sha256"],
                "raw_session_logical_sha256": session_receipt["logical_sha256"],
            })
            for row in activation_rows:
                activation = ProfileActivation(
                    activation_id=row["activation_id"], symbol=row["symbol"],
                    candidate_qualified_at=row["candidate_qualified_at"],
                    scanner_record_content_sha256=row["scanner_record_content_sha256"],
                    eligible_strategy_profile_ids=tuple(row["eligible_strategy_profile_ids"]),
                )
                produced = build_micro_trigger_decisions(
                    activation, bars=bars, trades=trades, support=support, replay_end=replay_end
                )
                decisions.extend(produced)
                status = "triggered" if produced else "no_trigger"
                total_no_trigger += int(not produced)
                outcomes.append({
                    "activation_id": activation.activation_id, "symbol": symbol,
                    "candidate_qualified_at": activation.candidate_qualified_at,
                    "eligible_strategy_profile_ids": list(activation.eligible_strategy_profile_ids),
                    "status": status, "decision_count": len(produced),
                    "decision_plan_ids": [item.plan_id for item in produced],
                    "causal_input_content_sha256": input_hash,
                })
        decisions.sort(key=lambda row: (row.decision_at, row.symbol, row.plan_id))
        outcomes.sort(key=lambda row: (row["candidate_qualified_at"], row["symbol"], row["activation_id"]))
        daily = _write_frozen(output_root / "dates" / f"{trading_date}.json", {
            "schema_version": 1, "artifact_type": "sealed_historical_micro_trigger_runtime_date",
            "contract_id": CONTRACT_ID, "trading_date": trading_date,
            "scanner_activation_plan_content_sha256": day_plan["content_sha256"],
            "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
            "activation_count": len(day_plan["activations"]), "activations": day_plan["activations"],
            "outcome_count": len(outcomes), "outcomes": outcomes,
            "decision_count": len(decisions), "decisions": [asdict(row) for row in decisions],
            "basis_evidence": basis, "unavailable_count": 0,
            "provider_calls": 0, "retrospective_labels_loaded": False,
            "fills_simulated": False, "accounts_simulated": False, "backtesting_executed": False,
        })
        date_hashes[trading_date] = file_sha(output_root / "dates" / f"{trading_date}.json")
        basis_hashes[trading_date] = canonical_fingerprint(basis)
        total_activations += len(outcomes)
        total_decisions += len(decisions)
    manifest = _write_frozen(output_root / "manifest.json", {
        "schema_version": 1, "artifact_type": "sealed_historical_micro_trigger_runtime_bundle",
        "contract_id": CONTRACT_ID, "contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "dates": list(EXPECTED_DATES), "date_file_sha256": date_hashes,
        "basis_evidence_by_date_sha256": basis_hashes,
        "activation_count": total_activations, "decision_count": total_decisions,
        "no_trigger_activation_count": total_no_trigger, "unavailable_activation_count": 0,
        "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
        "scanner_plan_content_sha256": PLAN_CONTENT_SHA256,
        "source": {"artifact_id": SOURCE_ARTIFACT_ID, "zip_sha256": SOURCE_ZIP_SHA256,
                   "report_file_sha256": SOURCE_REPORT_FILE_SHA256,
                   "report_content_sha256": SOURCE_REPORT_CONTENT_SHA256,
                   "source_tree_sha256": SOURCE_TREE_SHA256},
        "micro_input": {"run_id": MICRO_INPUT_RUN_ID, "artifact_id": MICRO_INPUT_ARTIFACT_ID,
                        "zip_sha256": MICRO_INPUT_ZIP_SHA256,
                        "report_file_sha256": MICRO_INPUT_REPORT_FILE_SHA256,
                        "report_content_sha256": MICRO_INPUT_REPORT_CONTENT_SHA256},
        "session_input": {"run_id": SESSION_INPUT_RUN_ID, "artifact_id": SESSION_INPUT_ARTIFACT_ID,
                          "zip_sha256": SESSION_INPUT_ZIP_SHA256,
                          "report_file_sha256": SESSION_INPUT_REPORT_FILE_SHA256,
                          "report_content_sha256": SESSION_INPUT_REPORT_CONTENT_SHA256},
        "execution_mode": "provider_free_label_blind_historical_micro_runtime",
        "provider_calls": 0, "retrospective_labels_loaded": False,
        "fills_simulated": False, "accounts_simulated": False, "backtesting_executed": False,
        "next_gate": "candidate_bound_execution_and_status_input_registration",
    })
    return manifest


def validate_runtime_output(*, output_root: Path, plan_root: Path) -> dict:
    """Deeply validate a completed, write-once historical Micro runtime bundle."""
    manifest_path = output_root / "manifest.json"
    manifest = frozen(manifest_path)
    expected_paths = {"manifest.json"} | {f"dates/{day}.json" for day in EXPECTED_DATES}
    actual_paths = {
        path.relative_to(output_root).as_posix()
        for path in output_root.rglob("*")
        if path.is_file()
    }
    if actual_paths != expected_paths:
        raise ValueError("historical Micro runtime file inventory changed")
    if (
        manifest.get("artifact_type") != "sealed_historical_micro_trigger_runtime_bundle"
        or manifest.get("contract_id") != CONTRACT_ID
        or manifest.get("contract_content_sha256") != CONTRACT_CONTENT_SHA256
        or manifest.get("dates") != list(EXPECTED_DATES)
        or manifest.get("micro_policy_fingerprint") != MICRO_POLICY_FINGERPRINT
        or manifest.get("scanner_plan_content_sha256") != PLAN_CONTENT_SHA256
        or manifest.get("execution_mode") != "provider_free_label_blind_historical_micro_runtime"
        or manifest.get("next_gate") != "candidate_bound_execution_and_status_input_registration"
    ):
        raise ValueError("historical Micro runtime manifest binding changed")
    for prohibited, expected in (
        ("provider_calls", 0),
        ("retrospective_labels_loaded", False),
        ("fills_simulated", False),
        ("accounts_simulated", False),
        ("backtesting_executed", False),
        ("unavailable_activation_count", 0),
    ):
        if manifest.get(prohibited) != expected:
            raise ValueError("historical Micro runtime boundary changed")
    expected_bindings = {
        "source": {
            "artifact_id": SOURCE_ARTIFACT_ID,
            "zip_sha256": SOURCE_ZIP_SHA256,
            "report_file_sha256": SOURCE_REPORT_FILE_SHA256,
            "report_content_sha256": SOURCE_REPORT_CONTENT_SHA256,
            "source_tree_sha256": SOURCE_TREE_SHA256,
        },
        "micro_input": {
            "run_id": MICRO_INPUT_RUN_ID,
            "artifact_id": MICRO_INPUT_ARTIFACT_ID,
            "zip_sha256": MICRO_INPUT_ZIP_SHA256,
            "report_file_sha256": MICRO_INPUT_REPORT_FILE_SHA256,
            "report_content_sha256": MICRO_INPUT_REPORT_CONTENT_SHA256,
        },
        "session_input": {
            "run_id": SESSION_INPUT_RUN_ID,
            "artifact_id": SESSION_INPUT_ARTIFACT_ID,
            "zip_sha256": SESSION_INPUT_ZIP_SHA256,
            "report_file_sha256": SESSION_INPUT_REPORT_FILE_SHA256,
            "report_content_sha256": SESSION_INPUT_REPORT_CONTENT_SHA256,
        },
    }
    if any(manifest.get(key) != value for key, value in expected_bindings.items()):
        raise ValueError("historical Micro runtime evidence binding changed")

    total_activations = total_decisions = total_no_trigger = 0
    for trading_date in EXPECTED_DATES:
        runtime_path = output_root / "dates" / f"{trading_date}.json"
        plan = frozen(plan_root / "dates" / f"{trading_date}.json")
        daily = frozen(runtime_path)
        if manifest.get("date_file_sha256", {}).get(trading_date) != file_sha(runtime_path):
            raise ValueError("historical Micro runtime date file hash changed")
        if (
            daily.get("artifact_type") != "sealed_historical_micro_trigger_runtime_date"
            or daily.get("contract_id") != CONTRACT_ID
            or daily.get("trading_date") != trading_date
            or daily.get("scanner_activation_plan_content_sha256") != plan["content_sha256"]
            or daily.get("micro_policy_fingerprint") != MICRO_POLICY_FINGERPRINT
            or daily.get("activations") != plan["activations"]
            or daily.get("unavailable_count") != 0
        ):
            raise ValueError("historical Micro runtime date binding changed")
        for prohibited, expected in (
            ("provider_calls", 0),
            ("retrospective_labels_loaded", False),
            ("fills_simulated", False),
            ("accounts_simulated", False),
            ("backtesting_executed", False),
        ):
            if daily.get(prohibited) != expected:
                raise ValueError("historical Micro runtime date boundary changed")
        activations = {row["activation_id"]: row for row in daily["activations"]}
        outcomes = {row["activation_id"]: row for row in daily["outcomes"]}
        if (
            len(activations) != len(daily["activations"])
            or len(outcomes) != len(daily["outcomes"])
            or set(outcomes) != set(activations)
            or daily.get("activation_count") != len(activations)
            or daily.get("outcome_count") != len(outcomes)
        ):
            raise ValueError("historical Micro runtime activation coverage changed")
        decisions_by_activation: dict[str, list[dict]] = {key: [] for key in activations}
        plan_ids: set[str] = set()
        if daily["decisions"] != sorted(
            daily["decisions"],
            key=lambda row: (row["decision_at"], row["symbol"], row["plan_id"]),
        ):
            raise ValueError("historical Micro runtime decision ordering changed")
        replay_end = pd.Timestamp(datetime.combine(date.fromisoformat(trading_date), time(10), ET))
        for decision in daily["decisions"]:
            activation_id = decision.get("activation_id")
            if activation_id not in activations or decision.get("plan_id") in plan_ids:
                raise ValueError("historical Micro runtime decision identity changed")
            activation = activations[activation_id]
            if (
                decision.get("symbol") != activation["symbol"]
                or decision.get("candidate_qualified_at") != activation["candidate_qualified_at"]
                or decision.get("eligible_strategy_profile_ids") != activation["eligible_strategy_profile_ids"]
                or not isinstance(decision.get("micro_runtime_content_sha256"), str)
                or len(decision["micro_runtime_content_sha256"]) != 64
            ):
                raise ValueError("historical Micro runtime decision provenance changed")
            decision_at = pd.Timestamp(decision["decision_at"])
            if decision_at < pd.Timestamp(activation["candidate_qualified_at"]) or decision_at >= replay_end:
                raise ValueError("historical Micro runtime decision lies outside the causal entry window")
            plan_ids.add(decision["plan_id"])
            decisions_by_activation[activation_id].append(decision)
        if daily.get("decision_count") != len(daily["decisions"]):
            raise ValueError("historical Micro runtime decision count changed")
        for activation_id, outcome in outcomes.items():
            activation = activations[activation_id]
            observed = decisions_by_activation[activation_id]
            if (
                outcome.get("symbol") != activation["symbol"]
                or outcome.get("candidate_qualified_at") != activation["candidate_qualified_at"]
                or outcome.get("eligible_strategy_profile_ids") != activation["eligible_strategy_profile_ids"]
                or outcome.get("decision_count") != len(observed)
                or outcome.get("decision_plan_ids") != [row["plan_id"] for row in observed]
                or outcome.get("status") != ("triggered" if observed else "no_trigger")
                or not isinstance(outcome.get("causal_input_content_sha256"), str)
                or len(outcome["causal_input_content_sha256"]) != 64
            ):
                raise ValueError("historical Micro runtime explicit outcome changed")
        expected_symbols = {row["symbol"] for row in activations.values()}
        if set(daily.get("basis_evidence", {})) != expected_symbols:
            raise ValueError("historical Micro runtime basis evidence coverage changed")
        for symbol, evidence in daily["basis_evidence"].items():
            if canonical_fingerprint({k: v for k, v in evidence.items() if k != "content_sha256"}) != evidence.get("content_sha256"):
                raise ValueError("historical Micro runtime basis evidence hash changed")
            earliest = min(
                pd.Timestamp(row["candidate_qualified_at"])
                for row in activations.values()
                if row["symbol"] == symbol
            )
            if pd.Timestamp(evidence["last_pair_available_at"]) > earliest:
                raise ValueError("historical Micro runtime basis used future data")
        if manifest.get("basis_evidence_by_date_sha256", {}).get(trading_date) != canonical_fingerprint(daily["basis_evidence"]):
            raise ValueError("historical Micro runtime basis evidence commitment changed")
        total_activations += len(activations)
        total_decisions += len(daily["decisions"])
        total_no_trigger += sum(row["status"] == "no_trigger" for row in outcomes.values())
    if (
        manifest.get("activation_count") != total_activations
        or manifest.get("decision_count") != total_decisions
        or manifest.get("no_trigger_activation_count") != total_no_trigger
    ):
        raise ValueError("historical Micro runtime aggregate counts changed")
    return manifest


__all__ = [
    "CONTRACT_ID", "causal_raw_to_split_factor", "execute_runtime",
    "normalize_warmup_to_raw", "validate_runtime_contract", "validate_runtime_inputs",
    "validate_runtime_output",
]
