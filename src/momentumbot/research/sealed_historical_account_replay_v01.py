"""Original-source account activation with frozen mechanics and explicit carry.

Only the public replay_panel entry point grants this child's historical scope.
Parent synthetic entry points and component evidence remain unchanged. Source
descriptors are serializable commitments; market rows stream through the exact
parent cursors, and no caller account state can enter a historical path.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, localcontext
import hashlib
import os
from pathlib import Path

from momentumbot.research import sealed_historical_source_binding_v01 as binding
from momentumbot.research.sealed_historical_execution_quote_v01 import (
    canonical_fingerprint, file_sha, frozen, require_exact, seal)

continuity = binding.parent
scheduler, producer = continuity.scheduler, continuity.parent
accounts, runner, fees = continuity.accounts, continuity.runner, continuity.fees
CONTRACT_ID = "sealed-historical-account-replay-v0.1"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
OUTPUT_PATH = f"research/runtime/{CONTRACT_ID}"
MODULE_PATH = "src/momentumbot/research/sealed_historical_account_replay_v01.py"
SCRIPT_PATH = "scripts/build_sealed_historical_account_replay_v01.py"
CHECKER_PATH = "scripts/verify_sealed_historical_account_replay_v01.py"
TEST_PATH = "tests/test_sealed_historical_account_replay_v01.py"
WORKFLOW_PATH = ".github/workflows/sealed-historical-account-replay-v01.yml"
PARENT_COMMIT = "72a67b193ed44b3e9ee39d6bbb67ceb27c5c6248"
PARENT_TREE = "b9f306c34b2d8c331d321baabbcc2f40c58f7b4b"
PARENT_FREEZE = "a5765974223b6551dcb6e2dffcc0f1f050c172592d6530e94013ffa6c0fbed79"
BOUND_MANIFEST = "9bb780dcbfbec3ef1b4e437cc3dc76e1528897956490d4ddd32d399ed5f683cd"
# Literal direct-parent pins are generated from the verified parent checkpoint.
PARENT_PINS = {
    ".github/workflows/sealed-historical-source-binding-v01.yml": "326ebe9095ffe7c35132cc55479a72f91c92fac0fb2b78afeb6e9c8f489f593f",
    "docs/research/sealed_historical_source_binding_v01.md": "63954e566fc9a484cb4171d78583e5d9702154761c41c23e310e86bd4aec9066",
    "research/data-audits/sealed-historical-source-binding-v0.1-hosted-verification-34237152248.json": "dc1f4bfd5d3e5a148f8aa9ce89fb120cc5524d546a2c790d131137d5824c5c33",
    "research/data-audits/sealed-historical-source-binding-v0.1-independent-verification.json": "21e4d4285b80faaf6d1f2f3a14d610fea9c4c3f815b00adf631cda00c5977dd6",
    "research/runtime/sealed-historical-source-binding-v0.1/binding-mechanics.json": "07677069c1229f1e3ac165c6972cf23780ddcbb1256d73bd40596be04b773cac",
    "research/runtime/sealed-historical-source-binding-v0.1/carry-dependencies.json": "9d3c024f5d51b2330a8f17eca0fd8c2fbf2288645e4601ecc7519bc04a115909",
    "research/runtime/sealed-historical-source-binding-v0.1/freeze-manifest.json": "1eb29bd1d1e397028a9876621627129fb8fe97b49874a8a718450b6fd4b0d1ba",
    "research/runtime/sealed-historical-source-binding-v0.1/readiness-report.json": "2e41ce57237ebfaf17dc34b6066618b8aebd2f9349a0f8420cdf3a959b872b22",
    "research/strategy/sealed-historical-source-binding-v0.1.json": "cfabd8e97e2fe3be41222537d026a208137e73c71a9f629b5fbd3e45fb2168bd",
    "scripts/build_sealed_historical_source_binding_v01.py": "330c3b60e0d772c50babd11486a6b93adac36a44be0f7fa29f32e0889e3a5953",
    "scripts/verify_sealed_historical_source_binding_v01.py": "2d6885f853b1fb120ed5e55676beababc5bf419dfc2273820775105f79d39328",
    "src/momentumbot/research/sealed_historical_source_binding_v01.py": "616af65ac35f739317828122f8c67cd1feb6b1f862372b052dee1431b395b9c6",
    "tests/test_sealed_historical_source_binding_v01.py": "2cb8b540a3ce69f16686e789dfee79e61cd89c148a08bfa899093cdd11f98cb3"
}
BOUNDARY = {
    "historical_runtime_authorized": False,
    "historical_producer_authenticated": False,
    "original_market_source_provenance_authenticated": False,
    "financial_metrics_eligible": False,
    "account_close_evidence": False,
    "policy_promotion_eligible": False,
    "retrospective_labels_opened": False,
    "provider_requests_authorized": False,
    "broker_orders_authorized": False,
    "overnight_execution_authorized": False,
    "broker_statement_equivalence_verified": False,
}
RUNTIME_BOUNDARY = dict(BOUNDARY, historical_runtime_authorized=True,
    historical_producer_authenticated=True, original_market_source_provenance_authenticated=True)
NEXT_GATE = "diagnose_frozen_runtime_failures_and_unresolved_carry_before_separate_completion_or_comparison_gate"


def mechanics():
    return {
        "hypothesis": "verified_original_sources_execute_through_frozen_account_mechanics_or_preserve_exact_blocking_evidence",
        "source_scope": "exact_five_parent_archives_and_verified_original_binding_manifest",
        "source_program": "all_12_paths_30_slots_and_744_original_opportunity_references",
        "seed": "original_main_30000_small_2000_once_per_path_no_reseed",
        "strategy_risk_fees_execution_priority": "unchanged_frozen_continuity_ancestors",
        "clock": "parent_completed_bar_decision_trade_feedback_boundary_order",
        "streaming": "original_lineage_and_whole_stream_commitment_without_materialized_copy",
        "unavailable_entry": "retain_original_status_never_rescue_or_claim_no_trade_evidence",
        "failure": "retain_known_account_reservation_journal_and_unreconciled_feedback_block_later_execution",
        "carry": "exact_prior_close_no_marks_units_adjustments_window_extension_or_attempt_reset",
        "runtime_freeze": "write_once_all_path_results_before_any_retrospective_inputs",
        "independent_verification": "stdlib_source_identity_chronology_shares_cash_fees_carry_and_inventory_not_second_fill_simulator",
        "component_boundary": "nested_parent_flags_remain_component_local_outer_child_has_historical_provenance_only",
    }


def expected_contract(root):
    return seal({"schema_version": 1, "contract_id": CONTRACT_ID,
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "parent_source_binding_freeze_content_sha256": PARENT_FREEZE,
        "source_bindings_content_sha256": BOUND_MANIFEST,
        "frozen_parent_file_sha256": {**binding.PARENT_PINS, **PARENT_PINS},
        "source_archives": binding.SOURCES, "mechanics": mechanics(),
        "implementation_file_sha256": {p: file_sha(root / p) for p in
            (MODULE_PATH, SCRIPT_PATH, CHECKER_PATH, TEST_PATH, WORKFLOW_PATH)},
        "next_gate": NEXT_GATE, **BOUNDARY})


def validate_registration(root):
    for name, sha in {**binding.PARENT_PINS, **PARENT_PINS}.items():
        binding.availability._regular(root / name)
        if file_sha(root / name) != sha:
            raise ValueError("historical replay parent differs: " + name)
    checked = binding.verify_bundle(root, root / binding.OUTPUT_PATH)
    if checked["freeze_content_sha256"] != PARENT_FREEZE:
        raise ValueError("source binding registration differs")
    require_exact(frozen(root / CONTRACT_PATH), expected_contract(root), "historical replay registration")


def source_programs(root):
    paths = frozen(root / binding.projection.ACCOUNT_PLAN)["paths"]
    return [seal({"contract_id": CONTRACT_ID, "artifact_type": "original_account_source_program",
        "input_scope": "authenticated_original_historical_sources", "path_id": path["path_id"],
        "source_bindings_content_sha256": BOUND_MANIFEST, "slots": path["sessions"],
        "sessions": [{"session_id": s["session_id"], "opportunities": deepcopy(s["opportunity_inputs"])}
            for s in path["sessions"]]}) for path in paths]


def documents(values, contract_sha, *, runtime=False):
    files = {name: fees.encoded(value) for name, value in values.items()}
    files["freeze-manifest.json"] = fees.encoded(seal({"contract_id": CONTRACT_ID,
        "contract_content_sha256": contract_sha,
        "file_inventory": {name: {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()} for name, raw in files.items()},
        "document_content_sha256": {name: value["content_sha256"] for name, value in values.items()},
        **(RUNTIME_BOUNDARY if runtime else BOUNDARY)}))
    return files


def build_bundle(root):
    validate_registration(root)
    return documents({"source-programs.json": seal({"contract_id": CONTRACT_ID,
        "programs": source_programs(root), **BOUNDARY}),
        "replay-mechanics.json": seal({"contract_id": CONTRACT_ID, "mechanics": mechanics(), **BOUNDARY})},
        expected_contract(root)["content_sha256"])


def write_files(root, output, files, *, registration=False):
    if output.is_symlink() or any(p.is_symlink() for p in output.parents):
        raise ValueError("nonsymlink output required")
    if output.resolve().is_relative_to(root.resolve()) and (not registration or output.resolve() != (root / OUTPUT_PATH).resolve()):
        raise ValueError("new external output required")
    output.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        if Path(name).name != name:
            raise ValueError("flat output inventory required")
        with (output / name).open("xb") as handle:
            if handle.write(raw) != len(raw):
                raise OSError("short replay write")
            handle.flush()
            os.fsync(handle.fileno())
    return seal({"file_inventory": binding.availability._inventory(output), **BOUNDARY})


def verify_bundle(root, output):
    expected = build_bundle(root)
    require_exact(sorted(binding.availability._inventory(output)), sorted(expected), "replay inventory")
    for name, raw in expected.items():
        if (output / name).read_bytes() != raw:
            raise ValueError("replay registration bytes differ: " + name)
    return seal({"verification_passed": True,
        "freeze_content_sha256": frozen(output / "freeze-manifest.json")["content_sha256"], **BOUNDARY})


def _source_item(sources, path_id, oid):
    context = sources.context(path_id, oid, expected_manifest_sha256=BOUND_MANIFEST)
    row, slot = sources._resolve(path_id, oid, BOUND_MANIFEST)
    require_exact(context["context"]["slot"], slot, "original source slot")
    tape, tape_sha = sources.entry_tape(path_id, oid, expected_manifest_sha256=BOUND_MANIFEST)
    exit_tape, exit_sha = sources.exit_tape(path_id, oid, row["exit"]["member"]["first_possible_exit_decision_ns"],
        expected_manifest_sha256=BOUND_MANIFEST)
    if tape_sha != row["entry"]["execution_tape_content_sha256"] or exit_sha != row["exit"]["execution_tape_content_sha256"]:
        raise ValueError("resolved execution payload differs from original binding")
    group = row["exit"]["original_group"]
    return {"candidate": context["candidate"], "position": {
        "entry_input": {"window": row["window"], "source_decision": row["source_decision"],
            "tape": tape, "expected_tape_sha256": tape_sha},
        "bars": sources.iter_records(path_id, oid, "raw_sip_1m_bars", expected_manifest_sha256=BOUND_MANIFEST),
        "trades": sources.iter_records(path_id, oid, "sip_transactions", expected_manifest_sha256=BOUND_MANIFEST),
        "expected_streams": row["management_streams"], "exit_group": group,
        "expected_exit_group_sha256": canonical_fingerprint(group),
        "exit_tape": exit_tape, "expected_exit_tape_sha256": exit_sha}}


class _Session(continuity._Session):
    """Private adapter; public historical authority is checked in replay_panel."""
    def __init__(self, slot, source, opening, resolve):
        super().__init__(slot, source, opening)
        self.resolve = resolve
        self.processed = {}

    def initialize(self):
        require_exact(self.source, {"session_id": self.slot["session_id"],
            "opportunities": self.slot["opportunity_inputs"]}, "complete original session source")
        ranked = []
        for ref in self.source["opportunities"]:
            if ref["input_status"] == "unavailable":
                continue
            oid = ref["opportunity_id"]
            item = self.resolve(oid)
            if set(item) != {"candidate", "position"}:
                raise ValueError("exact resolved candidate and position required")
            spec = item["position"]
            if set(spec) != producer.POSITION_FIELDS or set(spec["entry_input"]) != producer.ENTRY_FIELDS:
                raise ValueError("exact original position source fields required")
            window = spec["entry_input"]["window"]
            continuity.feedback.parent.validate_window(window)
            op = window["opportunity"]
            if (op["opportunity_id"] != oid or oid in self.specs or window["availability_content_sha256"] != ref["availability_content_sha256"]
                    or window["entry_input_reason"] != ref["reason"]):
                raise ValueError("resolved source differs from original availability")
            if op["decision_ts_ns"] < continuity.valuation.session_start_ns(self.slot) or op["trading_date"] != self.slot["trading_date"]:
                raise ValueError("opportunity must follow frozen session start")
            ranked.append(scheduler._candidate(item["candidate"], op, self.slot))
            self.specs[oid] = spec
        for ordinal, item in enumerate(scheduler.order_scarce_capital_opportunities(ranked)):
            oid = item.opportunity_id
            self.rank[oid] = ordinal
            spec = self.specs[oid]
            op = spec["entry_input"]["window"]["opportunity"]
            self.push(op["decision_ts_ns"], 1, ordinal, "decision", oid)
            self.push(spec["entry_input"]["window"]["end_ns"] - 1, 4, ordinal, "boundary", oid)
            for name, resource in (("bars", "raw_sip_1m_bars"), ("trades", "sip_transactions")):
                cursor = runner._Cursor(spec[name], spec["entry_input"]["window"], resource, spec["expected_streams"][resource])
                self.cursors[(oid, resource)] = cursor
                self.push_cursor(oid, cursor)

    def market(self, at, phase, oid, resource):
        raw = runner._row_bytes(self.cursors[(oid, resource)].value)
        scheduler._Session.market(self, at, phase, oid, resource)
        digest, count = self.processed.get((oid, resource), (hashlib.sha256(), 0))
        digest.update(raw)
        self.processed[(oid, resource)] = digest, count + 1

    def progress(self):
        result = []
        for oid, resource in sorted(self.cursors):
            digest, count = self.processed.get((oid, resource), (hashlib.sha256(), 0))
            result.append({"opportunity_id": oid, "resource": resource, "rows": count, "sha256": digest.hexdigest()})
        return result


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
    runtime = seal({"contract_id": CONTRACT_ID, "session_id": slot["session_id"], "path_id": slot["path_id"],
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
    close = seal({"contract_id": CONTRACT_ID, "session_id": slot["session_id"], "path_id": slot["path_id"],
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
            results.append(seal({"contract_id": CONTRACT_ID, "artifact_type": "original_historical_account_path",
                "path_id": program["path_id"], "program_content_sha256": program["content_sha256"],
                "initial_account_state": initial, "seed_application_count": 1,
                "session_count": len(sessions), "sessions": sessions, "last_close_content_sha256": previous,
                "path_complete": all(s["runtime"]["status"] == "flat_complete" for s in sessions), **RUNTIME_BOUNDARY}))
    return seal({"contract_id": CONTRACT_ID, "artifact_type": "frozen_original_historical_account_replay",
        "registration_freeze_content_sha256": expected_registration_sha256,
        "source_bindings_content_sha256": BOUND_MANIFEST, "source_archives": binding.SOURCES,
        "paths": results, "next_gate": NEXT_GATE, **RUNTIME_BOUNDARY})
