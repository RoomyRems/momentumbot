"""Synthetic account execution on the fixed new panel, with frozen mechanics.

Public input is a byte-verified source archive plus a separately pinned complete
synthetic execution inventory. Neither account states nor candidate ranks,
decisions, selection masks, or saved control outcomes are caller inputs.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import date
from decimal import Decimal, localcontext
import json
from pathlib import Path

from momentumbot.research import early_pullback_panel_sources_v01 as sources

parent = sources.parent
accounts, producer = parent.accounts, parent.producer
fingerprint, seal, require = sources.fingerprint, sources.seal, sources.require
ID = "early-pullback-panel-accounts-v0.1"
PARENT = "6a7e385b277aab0c0690ad0325bc5f81e2225d70"
PARENT_TREE = "39c53dcddf43dfcae05cb35c8494b370a80c4aa2"
PARENT_SHA = "5743bf8ab6a70f2c78d61f98ef841a054bc804076fd0d0d4ae0b7c1c2145b87e"
CONTRACT_PATH = f"research/strategy/{ID}.json"
BASE = f"research/data-audits/{ID}"
FEE_SOURCES_PATH = f"research/strategy/{ID}-fee-sources.json"
OWN_FILES = ("src/momentumbot/research/early_pullback_panel_accounts_v01.py",
             "src/momentumbot/research/early_pullback_panel_account_engine_v01.py",
             "scripts/build_early_pullback_panel_accounts_v01.py",
             "tests/test_early_pullback_panel_accounts_v01.py")
BOUNDARY = dict(sources.BOUNDARY, synthetic_new_date_account_execution_verified=True,
    historical_account_context_adapter_integrated=True,
    historical_execution_inputs_authenticated=False, account_runtime_scope=sources.SCOPE,
    broker_statement_equivalence_verified=False, new_panel_fee_rates_are_modeled=True)
SLOT_FIELDS = {"contract_id", "path_id", "cell_id", "arm", "account_key", "profile_id",
    "behavioral_horizon_seconds", "execution_scenario_id", "session_id", "trading_date",
    "session_index", "previous_session_id", "seed_content_sha256", "seed_applied",
    "state_source", "source_slot_content_sha256", "source_day_content_sha256",
    "opportunity_inputs", "unavailable_opportunity_count", "source_date_has_no_micro_decisions",
    "content_sha256"}
EXECUTION_FIELDS = {"entry_tape", "entry_tape_sha256", "bars", "trades", "expected_streams",
                    "exit_tape", "exit_tape_sha256"}


def fee_schedule(trading_date):
    """Dated member-assessment model; customer pass-through remains assumed.

    This is a new-panel temporal context, not a change to the old fee book or
    its arithmetic. April's CAT announcement is assumed effective as proposed
    for May trades. Later verification documents never enter strategy inputs.
    """
    require(type(trading_date) is date and trading_date.isoformat() in sources.DATES,
            "registered new-panel fee date required")
    return producer.fees.execution.EquityFeeSchedule(
        sec_sale_rate_per_dollar=Decimal("0" if trading_date < date(2026, 4, 4) else "0.0000206"),
        taf_sale_rate_per_share=Decimal("0.000195"), taf_per_trade_cap=Decimal("9.79"),
        cat_rate_per_executed_share=Decimal("0" if trading_date < date(2026, 5, 1) else "0.000003"),
        commission_rate_per_dollar=Decimal("0"))


def fee_sources():
    return seal({"contract_id": ID, "artifact_type": "new_panel_dated_fee_assumptions",
        "read_on": "2026-09-11", "sources": [
            {"url": "https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2", "published": "2026-02-27",
             "use": "SEC Section 31 zero through April 3; 20.60 per million sale dollars from April 4"},
            {"url": "https://www.finra.org/rules-guidance/rule-filings/sr-finra-2024-019/fee-adjustment-schedule",
             "use": "2026 covered-equity TAF column: 0.000195 per sold share, 9.79 per-trade cap; rule approved January 2025"},
            {"url": "https://www.catnmsplan.com/sites/default/files/2025-11/11.25.25-CAT-Fee-Alert-2025-4.pdf", "published": "2025-11-25",
             "use": "last old-schedule invoice in December for November trades, then suspended until further notice"},
            {"url": "https://www.catnmsplan.com/sites/default/files/2026-04/04.01.26-CAT-Fee-Alert-2026-1.pdf", "published": "2026-04-01",
             "use": "prospective CAT 0.000001 per executed equivalent share, May trades invoiced June; no CAT assessments for December-April costs"},
            {"url": "https://www.catnmsplan.com/sites/default/files/2026-04/04.01.26-CAT-Fee-Alert-2026-2.pdf", "published": "2026-04-01",
             "use": "historical CAT 1A adds 0.000002 per executed equivalent share on May trades"}],
        "verification_only_later_sources": ["https://www.finra.org/rules-guidance/rule-filings/sr-finra-2026-010",
            "https://www.finra.org/rules-guidance/rule-filings/sr-finra-2026-011", "https://www.catnmsplan.com/faq/v10"],
        "rates_by_date": {d: {k: str(v) for k, v in asdict(fee_schedule(date.fromisoformat(d))).items()} for d in sources.DATES},
        "assumptions": ["one-to-one customer pass-through of modeled member assessments", "trade-date accrual and unchanged daily upward-cent rounding",
            "zero direct-API commissions", "May CAT rates effective as announced April 1", "no later refunds or revised fees inserted retrospectively"],
        "limits": "no particular broker customer statement or fee agreement authenticated; a fee-date context correction is required for these 2026 dates",
        "old_fee_interval_unchanged": True, **BOUNDARY})


def _identity(account, horizon, scenario, arm):
    require(arm in parent.ARMS, "registered paired arm required")
    require(type(horizon) is int, "integer horizon required")
    cell = accounts._path_id(account, horizon, scenario)
    path_id = "panel-path-" + fingerprint({"contract_id": sources.ID, "arm": arm, "cell_id": cell})
    amount = accounts.ACCOUNT_SEEDS[account]
    seed = seal({"account_id": path_id, "equity_usd": amount, "buying_power_usd": amount,
        "effective_trading_date": sources.DATES[0], "applied_once_per_path": True,
        "broker_snapshot_claim": False})
    return cell, path_id, seed


def validate_slot(slot):
    sources._exact(slot, SLOT_FIELDS, "new-panel account slot")
    parent.selection.verify_frozen(slot)
    i = slot["session_index"]
    require(type(i) is int and 0 <= i < len(sources.DATES), "fixed panel session index required")
    cell, path_id, seed = _identity(slot["account_key"], slot["behavioral_horizon_seconds"],
                                    slot["execution_scenario_id"], slot["arm"])
    session = lambda d: "panel-session-" + fingerprint({"path_id": path_id, "trading_date": d})
    expected = {"contract_id": ID, "cell_id": cell, "path_id": path_id,
        "trading_date": sources.DATES[i], "session_id": session(sources.DATES[i]),
        "previous_session_id": None if i == 0 else session(sources.DATES[i - 1]),
        "seed_content_sha256": seed["content_sha256"], "seed_applied": i == 0,
        "state_source": "approved_initial_seed" if i == 0 else "exact_previous_session_close_required",
        "profile_id": parent.daily.GENERAL_PROFILE_ID if slot["account_key"] == "main_account" else parent.daily.SMALL_PROFILE_ID}
    require(all(slot[k] == v for k, v in expected.items()) and type(slot["seed_applied"]) is bool,
            "new-panel session ancestry or seed differs")
    for key in ("source_slot_content_sha256", "source_day_content_sha256"):
        require(isinstance(slot[key], str) and accounts._SHA.fullmatch(slot[key]), "source commitment required")
    refs = slot["opportunity_inputs"]
    require(isinstance(refs, list), "complete opportunity references required")
    seen = set()
    for ref in refs:
        sources._exact(ref, {"opportunity_id", "availability_content_sha256", "input_status", "reason"}, "availability reference")
        require(isinstance(ref["opportunity_id"], str) and ref["opportunity_id"].startswith("opportunity-")
                and ref["opportunity_id"] not in seen, "unique opportunity reference required")
        require(isinstance(ref["availability_content_sha256"], str)
                and accounts._SHA.fullmatch(ref["availability_content_sha256"]), "availability commitment required")
        require(ref["input_status"] in ("available", "unavailable") and isinstance(ref["reason"], str)
                and bool(ref["reason"].strip()), "explicit input availability required")
        seen.add(ref["opportunity_id"])
    require(type(slot["unavailable_opportunity_count"]) is int and slot["unavailable_opportunity_count"] ==
            sum(r["input_status"] == "unavailable" for r in refs), "unavailable count differs")
    require(type(slot["source_date_has_no_micro_decisions"]) is bool
            and not (slot["source_date_has_no_micro_decisions"] and refs), "no-trigger declaration differs")
    return seed


def opening_state(slot, previous_close=None, *, expected_previous_close_sha256=None):
    seed = validate_slot(slot)
    if slot["session_index"] == 0:
        require(previous_close is None and expected_previous_close_sha256 is None, "first session uses seed only")
        return {"equity_usd": seed["equity_usd"], "buying_power_usd": seed["buying_power_usd"],
            "cumulative_realized_pnl_usd": "0.00", "cumulative_fees_usd": "0.00",
            "positions": [], "pending_orders": [], "campaigns": [], "unresolved_inputs": []}
    require(isinstance(previous_close, dict), "exact previous close required; no reseeding")
    parent._pin(previous_close, expected_previous_close_sha256, "previous account close")
    parent.selection.verify_frozen(previous_close)
    expected = {"contract_id": ID, "arm": slot["arm"], "path_id": slot["path_id"],
        "session_id": slot["previous_session_id"], "session_index": slot["session_index"] - 1,
        "trading_date": sources.DATES[slot["session_index"] - 1]}
    require(all(previous_close.get(k) == v for k, v in expected.items()), "previous close path, arm or chronology differs")
    producer.validate_state(previous_close["account_state"])
    return deepcopy(previous_close["account_state"])


def _opportunities(day):
    rows = accounts.availability.plan._opportunities(day)
    # Preserve the original projection fields but give this child its real
    # panel identity. New dates never masquerade as old-panel opportunities.
    for row in rows:
        row["panel_id"] = ID
        identity = {k: row[k] for k in ("panel_id", "trading_date", "activation_id", "plan_id",
            "symbol", "decision_ts_ns", "micro_runtime_content_sha256")}
        row["opportunity_id"] = "opportunity-" + fingerprint(identity)
    return rows


def prepare_inputs(archive, execution, *, expected_execution_sha256):
    """Reconstruct the whole union before either arm executes; no price masks."""
    parent._pin(execution, expected_execution_sha256, "synthetic execution inventory")
    sources._exact(execution, {"contract_id", "scope", "source_archive", "capture_manifest_sha256", "by_plan"}, "execution inventory")
    require(execution["contract_id"] == ID and execution["scope"] == sources.SCOPE, "synthetic execution inventory only")
    require(type(archive) is sources.SourceArchive, "verified source archive required")
    require(execution["source_archive"] == archive.archive_spec and execution["capture_manifest_sha256"] == archive.manifest_sha,
            "execution inventory belongs to a different source archive")
    panel = sources.bind_panel(archive)
    plans = {d["plan_id"] for day in panel["days"].values() for d in day["decisions"]}
    require(isinstance(execution["by_plan"], dict) and set(execution["by_plan"]) == plans,
            "every reconstructed plan requires an explicit execution status, including late pullbacks")
    items, bindings, by_day = {}, {}, {}
    projection = producer.fees.feedback.parent
    for day, built in panel["days"].items():
        raw = archive.read(f"dates/{day}.json")
        rows = sources.scanner.build_scanner_snapshot_rows(trading_date=date.fromisoformat(day),
            profile=sources.historical_profile_union_v0_1(), **sources.scanner_inputs(raw["scanner"], day))
        require(fingerprint(rows) == built["scanner_rows_sha256"], "candidate source rows changed")
        row_index = {fingerprint(row): row for row in rows}
        by_day[day] = []
        for op in _opportunities(built):
            plan_id, oid = op["plan_id"], op["opportunity_id"]
            status = execution["by_plan"][plan_id]
            sources._exact(status, {"input_status", "reason", "execution"}, "plan execution status")
            require(status["input_status"] in ("available", "unavailable") and isinstance(status["reason"], str)
                    and bool(status["reason"].strip()), "explicit execution status and reason required")
            ref = {"opportunity_id": oid, "availability_content_sha256": fingerprint(status),
                "input_status": status["input_status"], "reason": status["reason"]}
            bound = built["sources"][plan_id]
            bindings[oid] = deepcopy(bound["binding"])
            by_day[day].append({"opportunity": op, "reference": ref})
            if status["input_status"] == "unavailable":
                require(status["execution"] is None, "unavailable inputs cannot contain executable evidence")
                continue
            value = status["execution"]
            sources._exact(value, EXECUTION_FIELDS, "synthetic execution sources")
            require(isinstance(value["bars"], list) and isinstance(value["trades"], list), "pinned serializable streams required")
            for field in ("entry_tape", "exit_tape"):
                parent._pin(value[field], value[field + "_sha256"], field)
            window = {"opportunity": op, "start_ns": op["decision_ts_ns"] // projection.MINUTE_NS * projection.MINUTE_NS,
                "signal_end_ns": op["decision_ts_ns"] + projection.SIGNAL_NS,
                "end_ns": op["decision_ts_ns"] + projection.SIGNAL_NS + projection.TAIL_NS,
                "availability_content_sha256": ref["availability_content_sha256"],
                "entry_input_status": ref["input_status"], "entry_input_reason": ref["reason"]}
            projection.validate_window(window)
            tape = value["exit_tape"]
            group = producer.runner.derive_exit_plan([window], [tape["quote_request"], tape["status_request"]])["groups"][0]
            activation = bound["source"]["activation"]
            candidates = {p: sources.original.bind_candidate(row_index[activation["scanner_record_content_sha256"]],
                activation, op, p) for p in op["eligible_strategy_profile_ids"]}
            items[oid] = {"candidates": candidates, "position": {"entry_input": {"window": window,
                "source_decision": deepcopy(bound["source"]["decision"]), "tape": deepcopy(value["entry_tape"]),
                "expected_tape_sha256": value["entry_tape_sha256"]}, "bars": deepcopy(value["bars"]),
                "trades": deepcopy(value["trades"]), "expected_streams": deepcopy(value["expected_streams"]),
                "exit_group": group, "expected_exit_group_sha256": fingerprint(group),
                "exit_tape": deepcopy(tape), "expected_exit_tape_sha256": value["exit_tape_sha256"]}}
            # Both arms must receive valid executable evidence for every
            # declared-available plan, even if the eligibility gate withholds it.
            producer._exit_evidence({"window": window}, items[oid]["position"])
            producer.fees.feedback._quote_window(window, op["decision_ts_ns"],
                value["entry_tape"], value["entry_tape_sha256"])
    paths = []
    for path in panel["paths"]:
        slots = []
        for source_slot in path["sessions"]:
            refs = [deepcopy(row["reference"]) for row in by_day[source_slot["trading_date"]]
                    if path["profile_id"] in row["opportunity"]["eligible_strategy_profile_ids"]]
            slot = {k: deepcopy(path[k]) for k in ("path_id", "cell_id", "arm", "account_key", "profile_id",
                "behavioral_horizon_seconds", "execution_scenario_id")}
            slot.update({k: source_slot[k] for k in ("session_id", "trading_date", "session_index", "previous_session_id",
                "seed_content_sha256", "seed_applied", "source_day_content_sha256", "source_date_has_no_micro_decisions")})
            slot.update(contract_id=ID, source_slot_content_sha256=source_slot["content_sha256"],
                state_source="approved_initial_seed" if slot["seed_applied"] else "exact_previous_session_close_required",
                opportunity_inputs=refs, unavailable_opportunity_count=sum(r["input_status"] == "unavailable" for r in refs))
            slot = seal(slot)
            validate_slot(slot)
            slots.append(slot)
        paths.append({"path_id": path["path_id"], "cell_id": path["cell_id"], "arm": path["arm"], "slots": slots})
    return {"panel": panel, "paths": paths, "items": items, "bindings": bindings}


def _run_path(path, items, bindings):
    from momentumbot.research import early_pullback_panel_account_engine_v01 as engine
    history, previous = [], None
    binding_sha = fingerprint(bindings)
    with localcontext() as context:
        context.prec = 60
        for slot in path["slots"]:
            opening = opening_state(slot, previous, expected_previous_close_sha256=None if previous is None else fingerprint(previous))
            machine, failure = None, None
            if producer._ready(opening):
                def resolve(oid):
                    item = items[oid]
                    return {"candidate": deepcopy(item["candidates"][slot["profile_id"]]), "position": deepcopy(item["position"])}
                try:
                    source = {"session_id": slot["session_id"], "opportunities": deepcopy(slot["opportunity_inputs"])}
                    machine = engine.Session(slot, source, opening, resolve, bindings, path["arm"]).run()
                    failure = machine.failure
                except (ValueError, TypeError, OverflowError) as exc:
                    failure = {"kind": "opening_ledger_projection_unavailable", "stage": "opening_ledger",
                        "error_type": type(exc).__name__, "error": str(exc)[:300], "blocks_next_session": True}
            pair = engine.finish(slot, opening, None if previous is None else previous["content_sha256"],
                machine, failure, arm=path["arm"], binding_sha=binding_sha)
            history.append(pair)
            previous = pair["close"]
    return seal({"contract_id": ID, "arm": path["arm"], "path_id": path["path_id"], "cell_id": path["cell_id"],
        "initial_account_state": opening_state(path["slots"][0]), "seed_application_count": 1,
        "sessions": history, "last_close_content_sha256": previous["content_sha256"], **BOUNDARY})


def replay_synthetic_panel(archive, execution, *, expected_execution_sha256):
    prepared = prepare_inputs(archive, execution, expected_execution_sha256=expected_execution_sha256)
    results = [_run_path(p, prepared["items"], prepared["bindings"]) for p in prepared["paths"]]
    return seal({"contract_id": ID, "artifact_type": "synthetic_new_panel_account_replay",
        "source_archive": archive.archive_spec, "capture_manifest_sha256": archive.manifest_sha,
        "source_panel_sha256": fingerprint(prepared["panel"]), "execution_sha256": expected_execution_sha256,
        "binding_manifest_sha256": fingerprint(prepared["bindings"]), "selected_dates": list(sources.DATES),
        "path_count": len(results), "session_slot_count": sum(len(p["sessions"]) for p in results),
        "paths": results, **BOUNDARY})


def verify_replay(archive, execution, result, *, expected_execution_sha256, expected_result_sha256):
    parent._pin(result, expected_result_sha256, "complete panel account result")
    require(result == replay_synthetic_panel(archive, execution, expected_execution_sha256=expected_execution_sha256),
            "new-panel account replay does not reproduce")
    return seal({"contract_id": ID, "verification_passed": True, "result_sha256": expected_result_sha256,
                 "independent_execution_engine": False, **BOUNDARY})


def provider_check_preparation(root):
    """Freeze exact existing probe requests at this integration checkpoint."""
    plan = json.loads((root / parent.BASE / "data-plan.json").read_bytes())
    require(plan["content_sha256"] == "41d941377a8a53ccc250f03e406aaf5419e868df0eb64f6e67331b3fae1a4a16",
            "frozen four-call plan differs")
    parent.selection.verify_frozen(plan)
    requests = [{"ordinal": i, "request_sha256": fingerprint(r), "request": r}
                for i, r in enumerate(plan["planned_probe_requests"])]
    return seal({"contract_id": ID, "artifact_type": "unarmed_exact_provider_check_preparation",
        "parent_plan_sha256": plan["content_sha256"], "source_registration_sha256": PARENT_SHA,
        "selected_dates": list(sources.DATES), "requests": requests, "maximum_calls": 4,
        "automatic_retries": False, "automatic_pagination": False, "provider_transport_implemented": False,
        "authorized_calls_now": 0, "incremental_spend_authorized_usd": "0.00", "actual_incremental_cost_known": False,
        "response_projection": "availability status, counts and dates only; no prices, symbols or outcomes",
        "required_execution_binding": "exact checkout and request hashes; durable one-shot consumption before transport; retain each failure; no replacement dates",
        "calendar_limit": "daily SPY dates and endpoint samples do not independently establish every full session or universe completeness",
        "next_gate": "bounded provider transport and provenance; independent full-session calendar; exact source request graph and quoted ceilings before paid capture",
        **BOUNDARY})


def registration(root: Path):
    inherited = sources.validate_registration(root)
    require(inherited["content_sha256"] == PARENT_SHA, "source parent registration differs")
    files = set(inherited["file_bindings"]) | set(OWN_FILES) | {sources.CONTRACT_PATH, FEE_SOURCES_PATH}
    return seal({"contract_id": ID, "parent_commit": PARENT, "parent_tree": PARENT_TREE,
        "parent_registration_sha256": PARENT_SHA,
        "file_bindings": {p: {"bytes": (root / p).stat().st_size, "sha256": sources.sha((root / p).read_bytes())} for p in sorted(files)},
        "provider_preparation_sha256": provider_check_preparation(root)["content_sha256"],
        "fee_sources_sha256": fee_sources()["content_sha256"],
        "selected_dates": list(sources.DATES), "path_count": 24, "session_slot_count": 720,
        "mechanics": "explicit new slot/seed context; copied context-dependent methods checked against frozen ancestors; inherited final terminal-continuation engine",
        "unchanged": "original scanner/Micro, first-two gate, ranking, account risks, execution, fee arithmetic/rounding/pass-through assumptions, management, original baseline and local historical replay waiver",
        "temporal_context_change": "explicit 2026 SEC/TAF/CAT rate schedule for both arms; original 2025 rates and guard untouched; not a claim of literal old-rate parity",
        "inputs": "all candidates and decisions reconstructed from byte-verified synthetic source archive; every plan has explicit shared execution availability before either arm executes",
        "carry": "same arm/cell immediate prior close, no reset; unresolved open/pending state preserved and blocks later execution; no invented overnight marks or liquidation",
        "limits": "fixture mechanics only; provider origin, calendar, point-in-time census, identity/SEC/news and execution capture provenance remain unauthenticated",
        "hybrid_objective": "crucial discretionary/context components remain unintegrated; these tests do not establish or reject full-hybrid profitability",
        "transcript_use": "offline versioned design only, with no recap actions, fills, later outcomes or evaluation narratives in runtime/backtests",
        **BOUNDARY})


def validate_registration(root):
    saved = sources.original._json((root / CONTRACT_PATH).read_bytes())
    require(saved == registration(root), "new-panel account registration differs")
    require(sources.original._json((root / FEE_SOURCES_PATH).read_bytes()) == fee_sources(), "new-panel fee evidence differs")
    require(sources.original._json((root / BASE / "provider-check-preparation.json").read_bytes()) == provider_check_preparation(root),
            "provider check preparation differs")
    return saved
