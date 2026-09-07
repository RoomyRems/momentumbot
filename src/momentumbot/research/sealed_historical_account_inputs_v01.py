"""Approved historical account seeds, state handoff, and management requests.

This is an input planner. It cannot execute entries, book descriptive exits,
value an overnight position, or turn unavailable evidence into a trade result.
"""
from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
import gzip
import json
from pathlib import Path
import re

from momentumbot.research import sealed_historical_execution_availability_v01 as availability
from momentumbot.research import prospective_management_window as management
from momentumbot.research.account_priority_policy import materialize_account_constraints, paper_account_policy
from momentumbot.research.campaign_portfolio import AccountClass
from momentumbot.research.prospective_account_evaluation import registered_cells
from momentumbot.research.sealed_historical_execution_quote_v01 import (
    PLAN_PATH, canonical_fingerprint, file_sha, frozen, require_exact, seal,
)
from momentumbot.research.sealed_historical_record_order_v01 import WindowIdentity

CONTRACT_ID = "sealed-historical-account-management-inputs-v0.1"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
OUTPUT_PATH = "research/runtime/sealed-historical-account-management-inputs-v0.1"
MODULE_PATH = "src/momentumbot/research/sealed_historical_account_inputs_v01.py"
SCRIPT_PATH = "scripts/build_sealed_historical_account_inputs_v01.py"
WORKFLOW_PATH = ".github/workflows/sealed-historical-account-inputs-v01.yml"
AVAILABILITY_AUDIT = "research/data-audits/sealed-historical-execution-input-availability-v0.1-independent-verification.json"
PARENT_COMMIT = "1f7c83b11d6fa26f600cbe37c16c9eed14fb7bb2"
PARENT_TREE = "dcf71e6bc1df1f7c10f2c38b2a9a4258c1f5431f"
DATES = tuple(availability.plan.EXPECTED_DATES)
ACCOUNT_SEEDS = {"main_account": "30000.00", "small_account": "2000.00"}
FROZEN_FILES = {'requirements-sealed-execution-quote-v01.txt': '03f4da335027e4c83bcf38e523c2e11aeaae49778f5bd6caa47e4703348b31b4',
 'research/data-audits/sealed-historical-execution-input-availability-v0.1-independent-verification.json': 'f5f1369adc03d908ca6fed0a934798f20829427277be0442ecc5f991371a0e34',
 'research/runtime/sealed-historical-execution-availability-v0.1/manifest.json': '6ed576e70dee9f439fdd2a1773f89931e6de23a73ea56e1ff1d9c81650bc8380',
 'research/strategy/paper-account-scarcity-policy-v0.1.json': '12c968d873cb459a9e65181b3bb2533b110006eddd9bf95b0def38a085c5a8fa',
 'research/strategy/prospective-management-execution-v0.1.json': '3760a73d4cc5d209098b75d555fb1f1a4ebcd7c0ecc428b1a16c39c2055008f8',
 'research/strategy/prospective-management-window-capture-v0.1.json': 'dd42ad3b7e826e8893f63809d6c9804ac0efbfae708992e5c5bd4c0220ee5ae7',
 'research/strategy/sealed-historical-execution-input-availability-v0.1.json': 'c7ab0f91782b11b7944946e3edea3d105e44b757058929a7f2e5cb3c12159f31',
 'research/strategy/sealed-historical-walk-forward-v0.1.json': '063df5e36210386a7c25890963ace5a7b2a70fdafb07f9103c5d402c69b195e2',
 'scripts/run_offline_python_v13.py': 'fd28ca7e4a27832721a890a1a41af36863a7f13568ca9e85e17c2d5f35e0627d',
 'src/momentumbot/models.py': 'efa4857a1fa92d24896b750b7df4846abd952fafd966f046054e0aad21325a82',
 'src/momentumbot/research/account_priority_policy.py': '3c0254bcd06425670e7158fb6c2be44edaa6c6f4b74c045798148f9d43e250d7',
 'src/momentumbot/research/campaign_portfolio.py': '5e8b5fb8e42cc739b8337bb544b811e57ccda2df5e7f46ca65ef5a30472149c4',
 'src/momentumbot/research/prospective_account_evaluation.py': '56ccebf7725ef04a797e4b5dead0ecd091ef9e9866290bf6e67b90283a9dd3bd',
 'src/momentumbot/research/prospective_management_window.py': 'bc431e578c7c85e1c72c72eda60ff212cf128cd5fd52cae3dcbed1bcc36523e8',
 'src/momentumbot/research/sealed_historical_execution_availability_v01.py': 'ef541e915e75c10641c57e42cd4a62fbb66b472c6b40a02d4c2ad85d6dbedb37',
 'src/momentumbot/research/sealed_historical_execution_inputs_v01.py': 'f100c220ed4fe5a6511d854599d8ed1494aaf554540a4fcabf6646f856b2a40f',
 'src/momentumbot/research/sealed_historical_execution_quote_v01.py': 'be5d81c039ba0256b2622ea65d2f966f56fa2f9a87b77f2e39485d92c6464383',
 'src/momentumbot/research/sealed_historical_record_order_v01.py': '407e02fc6fe908e26715fac2799f0debf356e96336b640e795b50287762dec6b',
 'src/momentumbot/research/trade_management_shadow.py': '9309593b839a4260bd6ef8d34d1eec5c905128dcf502218032cb7c0f142af180'}
BOUNDARY = {
    "provider_calls": 0, "provider_purchase_authorized_usd": "0",
    "broker_account_read": False, "account_or_fill_simulation_executed": False,
    "management_projection_executed": False, "backtesting_executed": False,
    "retrospective_inputs_loaded": False, "policy_changed": False,
    "acquisition_gate_passed": False, "historical_execution_authorized": False,
    "account_runtime_input_gate_passed": False, "management_input_gate_passed": False,
    "portfolio_financial_metrics_eligible": False, "paper_or_live_orders_authorized": False,
}
NEXT_GATE = "verify_retained_management_source_reuse_and_register_bounded_missing_input_capture"
_MONEY = re.compile(r"^-?(?:0|[1-9][0-9]*)\.[0-9]{2}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN = {"ross_action", "ross_fill", "ross_skip", "transcript_text", "retrospective_label", "human_action", "reported_entry", "reported_exit"}


def contract() -> dict:
    return seal({
        "schema_version": 1, "contract_id": CONTRACT_ID,
        "artifact_type": "registered_historical_account_and_management_input_plan",
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "frozen_parent_file_sha256": FROZEN_FILES,
        "hypothesis": "approved_once_only_seeds_and_frozen_management_windows_define_inputs_without_reset_or_substitution",
        "user_approved_seed_equity_and_buying_power_usd": ACCOUNT_SEEDS,
        "user_approval_scope": "hypothetical_balances_equal_buying_power_and_continuous_state_across_all_30_sessions",
        "account_seed_source": "explicit_user_approval_in_current_conversation_2026-09-07",
        "historical_broker_snapshot_claim": False,
        "seed_application": "first_registered_date_only_for_each_independent_account_horizon_scenario_path",
        "dates": list(DATES), "path_count": 12, "session_input_slot_count": 360,
        "horizons_and_scenarios": [list(cell) for cell in registered_cells()],
        "account_reset_between_dates": False,
        "handoff": "exact_prior_close_hash_same_path_immediately_previous_registered_date_complete_state_preserved",
        "handoff_verifies_execution_or_valuation": False,
        "later_session_equity_or_risk_limits_inferred": False,
        "missing_or_unresolved_prior_state": "remain_unavailable_never_reseed_or_assume_flat",
        "session_local_risk_state": "future_runtime_must_apply_unchanged_daily_policy_without_erasing_carried_account_state",
        "management_window_before_source_start": "floor_decision_to_UTC_minute",
        "management_signal_window_seconds": 900, "execution_observation_tail_seconds": 60,
        "management_request_end_exclusive": True,
        "management_merge": "unchanged_prospective_management_window_merge_mechanics",
        "management_population": "all_109_frozen_opportunities_including_all_23_unavailable_inputs",
        "management_source": {"provider": "Alpaca", "feed": "sip", "bar_timeframe": "1Min", "bar_adjustment": "raw", "symbol_asof": "exact_trading_date"},
        "retained_source_reuse": "requires_separate_full_artifact_and_normalization_coverage_verification_before_acquisition",
        "management_transaction_projection_may_close_account_positions": False,
        "management_window_extension_or_end_of_data_liquidation": False,
        "next_gate": NEXT_GATE, "boundary": BOUNDARY,
    })


def _sealed(value: dict, label: str) -> None:
    require_exact(value, seal({k: v for k, v in value.items() if k != "content_sha256"}), label)


def validate_registration(root: Path) -> dict:
    for name, sha in FROZEN_FILES.items():
        availability._regular(root / name)
        if file_sha(root / name) != sha:
            raise ValueError("frozen account-input parent differs: " + name)
    require_exact(frozen(root / CONTRACT_PATH), contract(), "account input registration")
    availability.validate_registration(root)
    management.validate_management_window_contract(frozen(root / "research/strategy/prospective-management-window-capture-v0.1.json"))
    return seal({"verification_passed": True, "contract_content_sha256": contract()["content_sha256"], **BOUNDARY})


def load_parent(root: Path) -> tuple[dict, dict, list[dict]]:
    validate_registration(root)
    output = root / availability.OUTPUT_PATH
    audit = frozen(root / AVAILABILITY_AUDIT)
    require_exact(availability._inventory(output), audit["full_source_reconstruction"]["file_inventory"], "exact verified availability files")
    manifest = frozen(output / "manifest.json")
    opportunities = frozen(root / PLAN_PATH / "opportunity-manifest.json")
    rows = []
    for date in DATES:
        day = json.loads(gzip.decompress((output / f"dates/{date}.json.gz").read_bytes()))
        _sealed(day, "frozen availability date")
        if day["trading_date"] != date or day["content_sha256"] != manifest["date_content_sha256"][date]:
            raise ValueError("availability date differs")
        rows.extend(day["opportunities"])
    for row in rows:
        _sealed(row, "frozen opportunity availability")
    require_exact([r["opportunity"] for r in rows], opportunities["opportunities"], "all original opportunities")
    require_exact(availability._summary(rows), manifest["summary"], "availability summary")
    return opportunities, manifest, rows


def seeds() -> dict:
    result = []
    for key, amount in ACCOUNT_SEEDS.items():
        kind = AccountClass.MAIN if key == "main_account" else AccountClass.SMALL
        account_id = f"sealed-historical-synthetic-{kind.value}-v0.1"
        constraints = asdict(materialize_account_constraints(paper_account_policy(kind),
            account_id=account_id, starting_equity=float(amount), starting_buying_power=float(amount)))
        constraints["account_class"] = kind.value
        result.append(seal({"account_key": key, "account_id": account_id,
            "effective_trading_date": DATES[0], "equity_usd": amount,
            "buying_power_usd": amount, "hypothetical": True,
            "broker_snapshot_claim": False, "applied_once_per_path": True,
            "first_session_frozen_constraints": constraints}))
    return seal({"contract_id": CONTRACT_ID, "seeds": result,
        "account_seed_inputs_registered": True, **BOUNDARY})


def _path_id(account: str, horizon: int, scenario: str) -> str:
    if account not in ACCOUNT_SEEDS or type(horizon) is not int or (horizon, scenario) not in registered_cells():
        raise ValueError("unregistered account/horizon/scenario")
    return f"{account}-{horizon}s-{scenario}"


def _session_id(path_id: str, date: str) -> str:
    return "session-" + canonical_fingerprint({"contract_id": CONTRACT_ID, "path_id": path_id, "trading_date": date})


def session_plan(opportunities: dict, availability_rows: list[dict]) -> dict:
    by_id = {row["opportunity"]["opportunity_id"]: row for row in availability_rows}
    if len(by_id) != 109 or [r["opportunity"] for r in availability_rows] != opportunities["opportunities"]:
        raise ValueError("all 109 ordered opportunities required")
    seed_index = {seed["account_key"]: seed for seed in seeds()["seeds"]}
    paths = []
    for account in ACCOUNT_SEEDS:
        profile = "current-general-2026" if account == "main_account" else "current-small-account-2026"
        for horizon, scenario in registered_cells():
            path_id = _path_id(account, horizon, scenario)
            slots = []
            for i, date in enumerate(DATES):
                selected = [op for op in opportunities["opportunities"] if op["trading_date"] == date and profile in op["eligible_strategy_profile_ids"]]
                refs = [{"opportunity_id": op["opportunity_id"],
                    "availability_content_sha256": by_id[op["opportunity_id"]]["content_sha256"],
                    "input_status": by_id[op["opportunity_id"]]["input_status"],
                    "reason": by_id[op["opportunity_id"]]["reason"]} for op in selected]
                slots.append(seal({"path_id": path_id, "session_id": _session_id(path_id, date),
                    "account_key": account, "behavioral_horizon_seconds": horizon,
                    "execution_scenario_id": scenario, "trading_date": date, "session_index": i,
                    "previous_session_id": None if i == 0 else _session_id(path_id, DATES[i - 1]),
                    "seed_content_sha256": seed_index[account]["content_sha256"],
                    "state_source": "approved_initial_seed" if i == 0 else "exact_previous_session_close_required",
                    "seed_applied": i == 0, "later_session_balances_inferred": False,
                    "profile_id": profile, "opportunity_inputs": refs,
                    "unavailable_opportunity_count": sum(r["input_status"] == "unavailable" for r in refs),
                    "source_date_has_no_micro_decisions": not any(op["trading_date"] == date for op in opportunities["opportunities"]),
                    "runtime_executed": False}))
            paths.append({"path_id": path_id, "sessions": slots})
    return seal({"contract_id": CONTRACT_ID, "paths": paths, "path_count": 12,
        "session_input_slot_count": sum(len(p["sessions"]) for p in paths),
        "opportunity_manifest_content_sha256": opportunities["content_sha256"],
        "account_reset_between_dates": False, **BOUNDARY})


def _validate_slot(slot: dict) -> dict:
    _sealed(slot, "session slot")
    path_id = _path_id(slot["account_key"], slot["behavioral_horizon_seconds"], slot["execution_scenario_id"])
    i = slot["session_index"]
    if type(i) is not int or not 0 <= i < len(DATES):
        raise ValueError("unregistered session index")
    seed = next(s for s in seeds()["seeds"] if s["account_key"] == slot["account_key"])
    expected = {"trading_date": DATES[i], "path_id": path_id,
        "session_id": _session_id(path_id, DATES[i]),
        "previous_session_id": None if i == 0 else _session_id(path_id, DATES[i - 1]),
        "seed_content_sha256": seed["content_sha256"], "seed_applied": i == 0,
        "state_source": "approved_initial_seed" if i == 0 else "exact_previous_session_close_required"}
    require_exact({k: slot[k] for k in expected}, expected, "registered session ancestry")
    return seed


def _validate_state(state: dict) -> None:
    expected = {"equity_usd", "buying_power_usd", "cumulative_realized_pnl_usd",
        "cumulative_fees_usd", "positions", "pending_orders", "campaigns", "unresolved_inputs"}
    if not isinstance(state, dict) or set(state) != expected:
        raise ValueError("complete carried account state required")
    for key in ("equity_usd", "buying_power_usd", "cumulative_realized_pnl_usd", "cumulative_fees_usd"):
        value = state[key]
        if value is not None and (not isinstance(value, str) or not _MONEY.fullmatch(value) or value == "-0.00"):
            raise ValueError("money must be exact decimal cents or explicitly unknown")
    if state["cumulative_fees_usd"] is not None and Decimal(state["cumulative_fees_usd"]) < 0:
        raise ValueError("cumulative fees cannot be negative")
    for key in ("positions", "pending_orders", "campaigns", "unresolved_inputs"):
        if not isinstance(state[key], list) or any(not isinstance(v, dict) for v in state[key]):
            raise ValueError("complete carried state collections required")
    def walk(value):
        if isinstance(value, dict):
            if _FORBIDDEN.intersection(value):
                raise ValueError("retrospective inputs forbidden in account handoff")
            for child in value.values(): walk(child)
        elif isinstance(value, list):
            for child in value: walk(child)
    walk(state)
    canonical_fingerprint(state)  # Reject nonfinite or non-JSON nested values.


def account_state_input(slot: dict, *, previous_close: dict | None = None,
                        expected_close_content_sha256: str | None = None) -> dict:
    """Carry a pinned future close intact; this does not verify its execution.

    The future runtime must supply its separately validated close commitment.
    A carried valuation is not automatically the next session's causal equity.
    Missing, open, insolvent and unresolved state is never replaced by a seed.
    """
    seed = _validate_slot(slot)
    if slot["session_index"] == 0:
        if previous_close is not None or expected_close_content_sha256 is not None:
            raise ValueError("first session uses only the approved seed")
        state = {"equity_usd": seed["equity_usd"], "buying_power_usd": seed["buying_power_usd"],
            "cumulative_realized_pnl_usd": "0.00", "cumulative_fees_usd": "0.00",
            "positions": [], "pending_orders": [], "campaigns": [], "unresolved_inputs": []}
        origin = seed["content_sha256"]
    else:
        if previous_close is None or not isinstance(expected_close_content_sha256, str) or not _SHA.fullmatch(expected_close_content_sha256):
            raise ValueError("exact previous close is required; account cannot reset")
        _sealed(previous_close, "previous close")
        if set(previous_close) != {"session_id", "path_id", "trading_date", "source_runtime_content_sha256", "account_state", "content_sha256"}:
            raise ValueError("exact close envelope required")
        if previous_close["content_sha256"] != expected_close_content_sha256:
            raise ValueError("pinned previous close differs")
        if (previous_close["session_id"] != slot["previous_session_id"] or previous_close["path_id"] != slot["path_id"]
                or previous_close["trading_date"] != DATES[slot["session_index"] - 1]):
            raise ValueError("previous close must be same path and immediately preceding registered date")
        runtime_sha = previous_close["source_runtime_content_sha256"]
        if not isinstance(runtime_sha, str) or not _SHA.fullmatch(runtime_sha):
            raise ValueError("source runtime commitment required")
        state, origin = previous_close["account_state"], previous_close["content_sha256"]
    _validate_state(state)
    # A new independent value prevents later callers from mutating prior evidence.
    copied = json.loads(json.dumps(state, allow_nan=False))
    return seal({"contract_id": CONTRACT_ID, "session_id": slot["session_id"],
        "path_id": slot["path_id"], "trading_date": slot["trading_date"],
        "source_slot_content_sha256": slot["content_sha256"],
        "state_origin_content_sha256": origin, "seed_applied": slot["session_index"] == 0,
        "account_state": copied, "carried_state_content_sha256": canonical_fingerprint(copied),
        "next_session_valuation_and_daily_risk_validation_required": slot["session_index"] != 0,
        "source_execution_verified_by_handoff": False, **BOUNDARY})


def management_requests(opportunities: dict, availability_rows: list[dict]) -> dict:
    rows = opportunities["opportunities"]
    if len(rows) != 109 or [r["opportunity"] for r in availability_rows] != rows:
        raise ValueError("complete management opportunity population required")
    identities = [WindowIdentity(**{k: op[k] for k in ("opportunity_id", "trading_date", "symbol", "decision_ts_ns")}) for op in rows]
    windows = management._merge_windows(identities)
    requests, by_op, ordinals = [], {}, {}
    for window in windows:
        key = (window.trading_date, window.symbol)
        ordinal = ordinals.get(key, 0) + 1
        ordinals[key] = ordinal
        rid = f"{window.trading_date}-{window.symbol}-management-{ordinal:02d}"
        request = {"request_id": rid, "trading_date": window.trading_date,
            "symbol": window.symbol, "start_ns": window.start_ns, "end_ns": window.end_ns,
            "end_exclusive": True, "feed": management.FEED,
            "bar_timeframe": management.TIMEFRAME, "bar_adjustment": management.ADJUSTMENT,
            "symbol_asof": window.trading_date, "opportunity_ids": list(window.opportunity_ids)}
        requests.append(request)
        for oid in window.opportunity_ids:
            if oid in by_op: raise ValueError("opportunity assigned to multiple merged requests")
            by_op[oid] = rid
    bounds = []
    for op, state in zip(rows, availability_rows, strict=True):
        ts = op["decision_ts_ns"]
        bounds.append({"opportunity": op, "request_id": by_op[op["opportunity_id"]],
            "start_ns": ts - ts % management.MINUTE_NS,
            "signal_end_ns": ts + management.SIGNAL_WINDOW_NS,
            "end_ns": ts + management.SIGNAL_WINDOW_NS + management.EXECUTION_TAIL_NS,
            "entry_input_status": state["input_status"], "entry_input_reason": state["reason"],
            "availability_content_sha256": state["content_sha256"]})
    return seal({"contract_id": CONTRACT_ID,
        "opportunity_manifest_content_sha256": opportunities["content_sha256"],
        "opportunity_count": len(rows), "merged_window_count": len(requests),
        "logical_resource_request_count": 2 * len(requests),
        "logical_resources_per_window": ["raw_sip_1m_bars", "sip_transactions"],
        "http_attempt_count_not_yet_quoted_or_authorized": True,
        "requests": requests, "opportunity_windows": bounds,
        "dates": [{"trading_date": date, "merged_window_count": sum(r["trading_date"] == date for r in requests),
            "opportunity_count": sum(op["trading_date"] == date for op in rows)} for date in DATES],
        "source_reuse_coverage_verified": False, **BOUNDARY})


def _bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def build_bundle(root: Path) -> dict[str, bytes]:
    opportunities, available, rows = load_parent(root)
    accounts = session_plan(opportunities, rows)
    requests = management_requests(opportunities, rows)
    payloads = {"account-seeds.json": seeds(), "account-session-input-plan.json": accounts,
        "management-request-manifest.json": requests,
        "readiness-report.json": seal({"contract_id": CONTRACT_ID,
            "account_seed_inputs_registered": True, "account_state_handoff_implemented": True,
            "account_paths": 12, "session_input_slots": 360,
            "once_only_seed_slots": 12, "prior_close_dependency_slots": 348,
            "availability_summary": available["summary"],
            "unavailable_opportunities": [{"opportunity_id": row["opportunity"]["opportunity_id"],
                "reason": row["reason"], "availability_content_sha256": row["content_sha256"]}
                for row in rows if row["input_status"] == "unavailable"],
            "merged_management_windows": requests["merged_window_count"],
            "management_logical_resource_requests": requests["logical_resource_request_count"],
            "management_source_reuse_or_capture_verified": False,
            "exit_execution_implementation_registered": False,
            "descriptive_sip_exit_may_close_account_position": False,
            "later_session_state": "requires_frozen_prior_close_and_causal_session_start_valuation",
            "next_gate": NEXT_GATE, **BOUNDARY})}
    files = {name: _bytes(payload) for name, payload in payloads.items()}
    import hashlib
    manifest = seal({"contract_id": CONTRACT_ID, "parent_commit_sha": PARENT_COMMIT,
        "parent_tree_sha": PARENT_TREE, "contract_content_sha256": contract()["content_sha256"],
        "availability_manifest_content_sha256": available["content_sha256"],
        "implementation_file_sha256": {name: file_sha(root / name) for name in (MODULE_PATH, SCRIPT_PATH, WORKFLOW_PATH, CONTRACT_PATH)},
        "file_inventory": {name: {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)} for name, raw in files.items()},
        "document_content_sha256": {name: payload["content_sha256"] for name, payload in payloads.items()},
        "next_gate": NEXT_GATE, **BOUNDARY})
    files["freeze-manifest.json"] = _bytes(manifest)
    return files


def _output(root: Path, output: Path) -> None:
    if output.is_symlink() or any(p.is_symlink() for p in output.parents):
        raise ValueError("symlink output rejected")
    if output.resolve().is_relative_to(root.resolve()) and output.resolve() != (root / OUTPUT_PATH).resolve():
        raise ValueError("cannot overwrite frozen repository inputs")


def verify_bundle(root: Path, output: Path) -> dict:
    _output(root, output)
    expected = build_bundle(root)
    inventory = availability._inventory(output)
    if set(inventory) != set(expected): raise ValueError("input-plan inventory differs")
    for name, raw in expected.items():
        if (output / name).read_bytes() != raw: raise ValueError("input plan differs from source reconstruction: " + name)
    return seal({"verification_passed": True, "contract_id": CONTRACT_ID,
        "file_inventory": inventory, "file_count": len(inventory),
        "freeze_manifest_content_sha256": frozen(output / "freeze-manifest.json")["content_sha256"],
        "readiness": frozen(output / "readiness-report.json"), **BOUNDARY})


def write_bundle(root: Path, output: Path) -> dict:
    _output(root, output)
    if output.exists(): raise FileExistsError("input plan is write-once")
    files = build_bundle(root)
    output.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        with (output / name).open("xb") as handle: handle.write(raw)
    return verify_bundle(root, output)
