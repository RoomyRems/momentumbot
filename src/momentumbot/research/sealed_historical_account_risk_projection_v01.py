"""Child-only exact decimal open-risk projection; parent execution is immutable.

The ledger and its acceptance/sizing methods remain the parent's. This adapter
changes only the public reconciliation snapshot's risk fields, derived from
confirmed lots before any decimal-to-JSON projection. The chronological parent
admits sizing only when flat. This is not a general decimal trading engine.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, Inexact, localcontext
import hashlib
import json
import os
from pathlib import Path

from momentumbot.research import sealed_historical_account_replay_v01 as parent
from momentumbot.research.campaign_portfolio import CampaignPortfolioLedger
from momentumbot.research.sealed_historical_execution_quote_v01 import (
    canonical_fingerprint, file_sha, frozen, require_exact, seal)

binding, continuity = parent.binding, parent.continuity
scheduler, producer = parent.scheduler, parent.producer
accounts, runner, fees = parent.accounts, parent.runner, parent.fees
BOUNDARY, RUNTIME_BOUNDARY = parent.BOUNDARY, parent.RUNTIME_BOUNDARY
BOUND_MANIFEST, PARENT_FREEZE = parent.BOUND_MANIFEST, parent.PARENT_FREEZE
source_programs, _source_item = parent.source_programs, parent._source_item
CONTRACT_ID = "sealed-historical-account-risk-projection-v0.1"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
OUTPUT_PATH = f"research/runtime/{CONTRACT_ID}"
MODULE_PATH = "src/momentumbot/research/sealed_historical_account_risk_projection_v01.py"
SCRIPT_PATH = "scripts/build_sealed_historical_account_risk_projection_v01.py"
CHECKER_PATH = "scripts/verify_sealed_historical_account_risk_projection_v01.py"
TEST_PATH = "tests/test_sealed_historical_account_risk_projection_v01.py"
WORKFLOW_PATH = ".github/workflows/sealed-historical-account-risk-projection-v01.yml"
PARENT_COMMIT = "9df7ad3487da1f2336701372703e4e5d196bd855"
PARENT_TREE = "a1c364558ca95bcbca5467eafcb7e0c247d3e7ba"
PARENT_REPLAY_FREEZE = "964a95b484843110f266a5a121232d11b55d0a5819a1381bd0bb982ba6df7352"
PARENT_RUNTIME = "28c745a20e6669a831ce6b9e09028e01a0c480bc1d88055c33b218ca9d88d56d"
PARENT_RUNTIME_FILE = "58508258633b3ee959ecfa701c5e2489932513e058851b30c178a12b2e699869"
PARENT_PINS = {
    ".github/workflows/sealed-historical-account-replay-v01.yml": "76a5111d640818730a656efb5043adb407b8ec4034944c8139798d0101de36d3",
    "docs/research/sealed_historical_account_replay_v01.md": "1eb65344157bc2e934357b12228cc390bf9f73e1aba6fe23a40ecb01c1a641d9",
    "research/data-audits/sealed-historical-account-replay-v0.1-first-runtime-failure.json": "a7b2c99e5d0285dbfeec5934e1050923adc17ebe3a78d876cbc907d87da248dd",
    "research/runtime/sealed-historical-account-replay-v0.1/freeze-manifest.json": "d82e56203ece2ee9cfb811fef46b70dcf93470180ab953f0df9ed97b737f8547",
    "research/runtime/sealed-historical-account-replay-v0.1/replay-mechanics.json": "34f423778a6275cede578e4398930f4d63a7a064721ce1f09e5f434a6da0101b",
    "research/runtime/sealed-historical-account-replay-v0.1/source-programs.json": "e2f65fcb8c65442283cd2cad3a58c941f5f30378c8097fc6d811030a07a19823",
    "research/strategy/sealed-historical-account-replay-v0.1.json": "a50498ca67c5a1169991ab6d9443abec7e16e8328cb2a3bd7d9be4e0e16510d6",
    "scripts/build_sealed_historical_account_replay_v01.py": "f1b3e3f7a96ee9cac06822c006249dd3878d7078be41c863556b9861bf471b91",
    "scripts/verify_sealed_historical_account_replay_v01.py": "a7a6fa11adf1af4808915c829eab8744097e21331ce6ae2ab30371eade9c0acd",
    "src/momentumbot/research/sealed_historical_account_replay_v01.py": "b33afa09d4eddcdebd65a5c6d91b6a545cfc6728f9a224310b834816cac02754",
    "tests/test_sealed_historical_account_replay_v01.py": "da0873dae231394e1bbe5ec4105796f9b181ecd5d207258aeffa17ca5d4d8ef2"
}
NEXT_GATE = "register_causal_wait_for_fresh_exit_reference_within_original_windows_and_attempt_ceilings"


def mechanics():
    return {
        "hypothesis": "exact_confirmed_lot_risk_projection_passes_unchanged_independent_checker_without_trade_changes",
        "delta": "public_snapshot_campaign_and_account_open_risk_only_plus_dependent_content_commitments",
        "arithmetic": "Decimal_of_each_price_string_before_subtraction_times_confirmed_integer_remaining_shares",
        "precision": "60_digits_trap_inexact_no_quantization_no_tolerance",
        "json_projection": "retain_equal_parent_number_else_exact_decimal_roundtrip_float_or_fail_closed",
        "sizing_and_acceptance": "unchanged_parent_float_methods_only_flat_accounts_reach_entry_sizing",
        "scope_limit": "not_a_general_decimal_sizer_or_entry_guard_repair",
        "evidence": "new_original_replay_not_edit_or_postprocess_of_failed_parent",
        "parity": "independent_strict_structural_comparison_all_nonrisk_values_and_authenticated_hash_references",
        "parent_schema": "nested_paths_sessions_and_entry_evidence_keep_frozen_component_ids_outer_child_binds_delta",
        "sources_seeds_strategy_fees_windows_attempts": "all_frozen_parent_values_unchanged",
        "failure": "fresh_quote_failure_and_exact_blocked_carry_remain_no_wait_policy_added",
    }


def exact_lot_risk(fill_price, stop_price, quantity):
    if type(quantity) is not int or quantity < 0:
        raise ValueError("confirmed nonnegative integer shares required")
    fill, stop = Decimal(str(fill_price)), Decimal(str(stop_price))
    if not fill.is_finite() or not stop.is_finite() or not 0 < stop <= fill:
        raise ValueError("finite positive lot prices and stop no higher than entry required")
    with localcontext() as context:
        context.prec = 60
        context.traps[Inexact] = True
        return (fill - stop) * quantity


def _number(exact, original):
    if Decimal(str(original)) == exact:
        return original
    projected = float(exact)
    if not exact.is_finite() or Decimal(str(projected)) != exact:
        raise ValueError("exact open risk cannot be projected without decimal loss")
    return projected


def project_ledger(ledger):
    """Publish exact confirmed lot risk without mutating the execution ledger."""
    artifact = deepcopy(ledger.runtime_artifact())
    with localcontext() as context:
        context.prec = 60
        context.traps[Inexact] = True
        risks = {key: sum((exact_lot_risk(lot.fill_price, lot.stop_price, lot.remaining_quantity)
            for lot in campaign.lots), Decimal(0)) for key, campaign in ledger.campaigns.items()}
        for campaign in artifact["campaigns"]:
            campaign["open_risk"] = _number(risks[campaign["activation_id"]], campaign["open_risk"])
        artifact["account"]["total_open_risk"] = _number(sum(risks.values(), Decimal(0)),
            artifact["account"]["total_open_risk"])
    return artifact


class _AccountDay(continuity._AccountDay):
    def snapshot(self):
        value = super().snapshot()
        value.pop("content_sha256")
        value["ledger"] = project_ledger(self._ledger)
        return seal(value)


class _Session(parent._Session):
    def __init__(self, slot, source, opening, resolve):
        super().__init__(slot, source, opening, resolve)
        ledger = CampaignPortfolioLedger(self.account._ledger.session_date, self.account._ledger.constraints)
        self.account = _AccountDay(pre_session_ledger=ledger,
            expected_pre_session_ledger_sha256=canonical_fingerprint(ledger.runtime_artifact()),
            path_id=slot["path_id"], scenario_id=slot["execution_scenario_id"])


def expected_contract(root):
    return seal({"schema_version": 1, "contract_id": CONTRACT_ID,
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "parent_replay_freeze_content_sha256": PARENT_REPLAY_FREEZE,
        "parent_runtime_content_sha256": PARENT_RUNTIME,
        "parent_runtime_file_sha256": PARENT_RUNTIME_FILE,
        "source_bindings_content_sha256": BOUND_MANIFEST,
        "frozen_parent_file_sha256": {**binding.PARENT_PINS, **parent.PARENT_PINS, **PARENT_PINS},
        "source_archives": binding.SOURCES, "mechanics": mechanics(),
        "implementation_file_sha256": {p: file_sha(root / p) for p in
            (MODULE_PATH, SCRIPT_PATH, CHECKER_PATH, TEST_PATH, WORKFLOW_PATH)},
        "next_gate": NEXT_GATE, **BOUNDARY})


def validate_registration(root):
    for name, sha in {**binding.PARENT_PINS, **parent.PARENT_PINS, **PARENT_PINS}.items():
        binding.availability._regular(root / name)
        if file_sha(root / name) != sha:
            raise ValueError("risk projection parent differs: " + name)
    checked = parent.verify_bundle(root, root / parent.OUTPUT_PATH)
    if checked["freeze_content_sha256"] != PARENT_REPLAY_FREEZE:
        raise ValueError("parent replay registration differs")
    require_exact(frozen(root / CONTRACT_PATH), expected_contract(root), "risk projection registration")


def documents(values, contract_sha, *, runtime=False):
    files = parent.documents(values, contract_sha, runtime=runtime)
    manifest = json.loads(files["freeze-manifest.json"])
    manifest.pop("content_sha256")
    manifest["contract_id"] = CONTRACT_ID
    files["freeze-manifest.json"] = fees.encoded(seal(manifest))
    return files


def build_bundle(root):
    validate_registration(root)
    return documents({"risk-projection-mechanics.json": seal({"contract_id": CONTRACT_ID,
        "mechanics": mechanics(), **BOUNDARY})}, expected_contract(root)["content_sha256"])


def write_files(root, output, files, *, registration=False):
    if registration and output.resolve() == (root / OUTPUT_PATH).resolve():
        if output.is_symlink() or any(p.is_symlink() for p in output.parents):
            raise ValueError("nonsymlink output required")
        output.mkdir(parents=True, exist_ok=False)
        for name, raw in files.items():
            if Path(name).name != name:
                raise ValueError("flat output inventory required")
            with (output / name).open("xb") as handle:
                if handle.write(raw) != len(raw):
                    raise OSError("short registration write")
                handle.flush()
                os.fsync(handle.fileno())
        return seal({"file_inventory": binding.availability._inventory(output), **BOUNDARY})
    return parent.write_files(root, output, files)


def verify_bundle(root, output):
    expected = build_bundle(root)
    require_exact(sorted(binding.availability._inventory(output)), sorted(expected), "risk projection inventory")
    for name, raw in expected.items():
        if (output / name).read_bytes() != raw:
            raise ValueError("risk projection registration bytes differ: " + name)
    return seal({"verification_passed": True,
        "freeze_content_sha256": frozen(output / "freeze-manifest.json")["content_sha256"], **BOUNDARY})


def _session(slot, source, opening, previous_sha, resolve, dependency):
    """Frozen finisher arithmetic; add historical identity and explicit carry."""
    blocked, machine, failure = not producer._ready(opening), None, None
    if not blocked:
        try:
            machine = _Session(slot, source, opening, resolve).run()
            failure = machine.failure
        except (ValueError, TypeError, OverflowError) as exc:
            blocked = True
            failure = {"kind": "opening_ledger_projection_unavailable", "stage": "opening_ledger",
                "error_type": type(exc).__name__, "error": str(exc)[:300], "blocks_next_session": True}
    seen = {} if machine is None else {d["opportunity_id"]: d["disposition"] for d in machine.dispositions}
    dispositions = [{**deepcopy(r), "disposition": "unavailable_input" if r["input_status"] == "unavailable"
        else seen.get(r["opportunity_id"], "blocked_prior_state" if blocked else "unprocessed_available_input")}
        for r in slot["opportunity_inputs"]]
    gaps = [{"kind": d["disposition"], "opportunity_id": d["opportunity_id"],
        "availability_content_sha256": d["availability_content_sha256"], "reason": d["reason"],
        "blocks_next_session": d["disposition"] != "unavailable_input"} for d in dispositions
        if d["disposition"] in {"unavailable_input", "unprocessed_available_input", "blocked_prior_state"}]
    failures = [] if failure is None else [failure]
    snapshot = None if machine is None else machine.account.snapshot()
    entry_pending = None if machine is None else machine.pending_public()
    if blocked:
        state = deepcopy(opening)
        state["unresolved_inputs"] += gaps + failures + [{"kind": "preceding_state_blocks_execution", "blocks_next_session": True,
            "previous_close_content_sha256": previous_sha}]
        gross = net = charged = Decimal(0)
    else:
        positions, pending, extra = producer._collections(snapshot)
        if entry_pending is not None:
            pending.append(entry_pending)
        exact = snapshot["exact_account"]
        gross, net, charged = Decimal(exact["gross_realized_pnl"]), Decimal(exact["net_realized_pnl"]), Decimal(snapshot["fee_book"]["fees"]["total_charged"])
        state = {"equity_usd": None if positions or pending else producer.money(Decimal(opening["equity_usd"]) + net),
            "buying_power_usd": producer.money(exact["remaining_buying_power"]),
            "cumulative_realized_pnl_usd": producer.money(Decimal(opening["cumulative_realized_pnl_usd"]) + net),
            "cumulative_fees_usd": producer.money(Decimal(opening["cumulative_fees_usd"]) + charged),
            "positions": positions, "pending_orders": pending,
            "campaigns": deepcopy(opening["campaigns"]) + deepcopy(snapshot["ledger"]["campaigns"]),
            "unresolved_inputs": deepcopy(opening["unresolved_inputs"]) + gaps + failures + extra}
    producer.validate_state(state)
    window = None if machine is None or machine.active is None else machine.specs[machine.active]["entry_input"]["window"]
    carry = None if dependency is None else seal({"dependency": deepcopy(dependency),
        "previous_close_content_sha256": previous_sha, "opening_account_state_sha256": canonical_fingerprint(opening),
        "status": "blocked_preserved_prior_state" if blocked else "flat_cash_no_share_mark_or_adjustment_required",
        "prior_state_preserved": True, "new_source_evidence_inferred": False})
    complete = machine is not None and machine.failure is None and not machine.heap
    runtime = seal({"contract_id": parent.CONTRACT_ID, "session_id": slot["session_id"], "path_id": slot["path_id"],
        "source_slot_content_sha256": slot["content_sha256"], "session_program_sha256": canonical_fingerprint(source),
        "source_bindings_content_sha256": BOUND_MANIFEST,
        "opening_account_state_sha256": canonical_fingerprint(opening), "blocked_before_execution": blocked,
        "events": [] if machine is None else machine.events, "opportunity_dispositions": dispositions,
        "reconciliation_snapshot": snapshot, "unconfirmed_entry_order": entry_pending,
        "complete_streams_verified": complete, "processed_streams": [] if machine is None else machine.progress(),
        "failure": failure, "active_original_window": deepcopy(window), "carry_dependency": carry,
        "session_gross_realized_pnl_usd": producer.money(gross), "session_net_realized_pnl_usd": producer.money(net),
        "session_fees_usd": producer.money(charged), "historical_session_scheduler_executed": machine is not None,
        "status": "blocked_prior_state" if blocked else "input_failure" if failure else
            "original_window_exhausted_with_unresolved_state" if not producer._ready(state) else
            "flat_complete_with_unavailable_inputs" if gaps else "flat_complete",
        **RUNTIME_BOUNDARY})
    close = seal({"contract_id": parent.CONTRACT_ID, "session_id": slot["session_id"], "path_id": slot["path_id"],
        "trading_date": slot["trading_date"], "session_index": slot["session_index"], "seed_applied": slot["seed_applied"],
        "source_slot_content_sha256": slot["content_sha256"], "previous_close_content_sha256": previous_sha,
        "source_runtime_content_sha256": runtime["content_sha256"], "account_state": state,
        "next_session_flat_cash_execution_ready": producer._ready(state), **RUNTIME_BOUNDARY})
    return {"runtime": runtime, "close": close}



def replay_panel(root, sources, *, expected_registration_sha256):
    verified = verify_bundle(root, root / OUTPUT_PATH)
    if verified["freeze_content_sha256"] != expected_registration_sha256:
        raise ValueError("independent historical replay registration pin differs")
    if type(sources) is not binding.OriginalSources:
        raise ValueError("verified original source reader required; caller programs or accounts prohibited")
    manifest = sources.manifest()
    accounts._sealed(manifest, "authenticated original bindings")
    if manifest["content_sha256"] != BOUND_MANIFEST:
        raise ValueError("verified original binding manifest differs")
    programs = source_programs(root)
    require_exact([p["slots"] for p in programs], [p["sessions"] for p in manifest["paths"]], "original complete path catalogs")
    dependencies = {d["next_session_id"]: d for d in manifest["carry_dependencies"]}
    results = []
    with localcontext() as context:
        context.prec = 60
        for program in programs:
            initial = accounts.account_state_input(program["slots"][0])["account_state"]
            opening, previous, sessions = initial, None, []
            for slot, source in zip(program["slots"], program["sessions"]):
                pair = _session(slot, source, opening, previous,
                    lambda oid: _source_item(sources, program["path_id"], oid), dependencies.get(slot["session_id"]))
                sessions.append(pair)
                opening, previous = deepcopy(pair["close"]["account_state"]), pair["close"]["content_sha256"]
            results.append(seal({"contract_id": parent.CONTRACT_ID, "artifact_type": "original_historical_account_path",
                "path_id": program["path_id"], "program_content_sha256": program["content_sha256"],
                "initial_account_state": initial, "seed_application_count": 1,
                "session_count": len(sessions), "sessions": sessions, "last_close_content_sha256": previous,
                "path_complete": all(s["runtime"]["status"] == "flat_complete" for s in sessions), **RUNTIME_BOUNDARY}))
    return seal({"contract_id": CONTRACT_ID, "artifact_type": "frozen_original_historical_account_risk_projection_replay",
        "parent_runtime_content_sha256": PARENT_RUNTIME,
        "registration_freeze_content_sha256": expected_registration_sha256,
        "source_bindings_content_sha256": BOUND_MANIFEST, "source_archives": binding.SOURCES,
        "paths": results, "next_gate": NEXT_GATE, **RUNTIME_BOUNDARY})
