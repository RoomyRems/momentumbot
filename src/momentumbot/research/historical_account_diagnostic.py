"""Retrospective account-feasibility overlay on frozen historical runtimes.

This module deliberately does not extend the prospective account panel.  It
verifies two already-frozen artifacts, reapplies the unchanged main and small
scanner profiles to each exact causal activation row, and then delegates event
composition to the unchanged account-chronological-integration-v0.1 engine.

The result is diagnostic-only.  Historical account balances are synthetic,
sessions are independent, the small-account source universe is incomplete,
and open Micro outcomes are never closed with invented prices.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Mapping
from zipfile import ZipFile
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.micro_execution import (
    MicroEntryPlan,
    MicroExecutionOutcome,
    MicroExecutionStatus,
    MicroTriggerMode,
)
from momentumbot.micro_replay import MicroCandidateReplay, MicroReplayStep
from momentumbot.models import (
    CandidateQuality,
    CandidateSnapshot,
    StrategyProfile,
    current_general_2026,
    current_small_account_2026,
)
from momentumbot.research.account_chronological_integration import (
    ACCOUNT_POLICY_BUNDLE_SHA256,
    ACCOUNT_POLICY_CONTRACT_SHA256,
    LEDGER_CONTRACT_SHA256,
    MICRO_POLICY_FINGERPRINT,
    AccountCandidateRuntime,
    integrate_account_session,
)
from momentumbot.research.account_priority_policy import (
    GENERAL_PROFILE_FINGERPRINT,
    SMALL_PROFILE_FINGERPRINT,
)
from momentumbot.research.campaign_portfolio import AccountClass


SCHEMA_VERSION = 1
CONTRACT_ID = "historical-account-diagnostic-v0.1"
REGISTRATION_DATE = date(2026, 8, 19)
REGISTERED_DATES = (
    "2026-07-10",
    "2026-07-13",
    "2026-07-14",
    "2026-07-15",
    "2026-07-16",
    "2026-07-17",
    "2026-07-20",
    "2026-07-21",
    "2026-07-22",
    "2026-07-23",
)
PROSPECTIVE_INTEGRATION_CONTRACT_SHA256 = (
    "64489aa27fec5eaf8ca12c94f4aeb47344d49a79b14df1bdda706cd23cc9ce73"
)
SOURCE_ZIP_SHA256 = (
    "850d9cfba27d7677904ccf147251b3ff914292102be0e3c62fec7bb47b6f73bb"
)
SOURCE_MANIFEST_FILE_SHA256 = (
    "a55ea217d65ada1d189af51111b801b60610c3a62cf3838dcafd98b5a115385f"
)
SOURCE_MANIFEST_CONTENT_SHA256 = (
    "2414f7389bf68d5a5e4b3302c646c9111020cb79ce06fc0213f7872062f79c48"
)
SCANNER_AGGREGATE_FILE_SHA256 = (
    "34ce9c43df2f51f1c0b181bae5c72b144afc6b848c7d2bea4927b5c1c832de0c"
)
SCANNER_AGGREGATE_CONTENT_SHA256 = (
    "008ef162413ad3626944c44a6c8e964cbb825a6253fdfe360701d55d454e70a0"
)
MICRO_ZIP_SHA256 = (
    "3b59e4b1a69e268158f6ccbead1fe9abae425fc249e72b34f466e53ebba56b20"
)
MICRO_MANIFEST_FILE_SHA256 = (
    "cd1f52248ede37ac66010997c7b7f547efd023de27fe086846ad77863af40fa1"
)
MICRO_MANIFEST_CONTENT_SHA256 = (
    "feb2283acf1f180fd82b0e3c25acde1ebb9ebc036c47533e1d61fc9e8883e190"
)
ACCOUNT_SCENARIOS = {
    AccountClass.MAIN: {
        "account_id": "synthetic-main-30000-historical-diagnostic",
        "starting_equity": 30_000.0,
        "starting_buying_power": 30_000.0,
    },
    AccountClass.SMALL: {
        "account_id": "synthetic-small-2000-historical-diagnostic",
        "starting_equity": 2_000.0,
        "starting_buying_power": 2_000.0,
    },
}
REQUIRED_LABELS = (
    "retrospective",
    "diagnostic-only",
    "non-promotable",
    "not-a-full-backtest",
)


@dataclass(frozen=True, slots=True)
class HistoricalDiagnosticAccountSnapshot:
    """Synthetic fixed-balance input accepted by the unchanged engine.

    ``integrate_account_session`` is intentionally duck-typed.  Its historical
    exclusion lives in the prospective snapshot constructor, so this separate
    type supplies the same validated interface without weakening that guard.
    """

    account_id: str
    account_class: AccountClass
    session_date: date
    captured_at: datetime | pd.Timestamp
    starting_equity: float
    starting_buying_power: float
    source_id: str
    source_content_sha256: str

    def __post_init__(self) -> None:
        if self.session_date.isoformat() not in REGISTERED_DATES:
            raise ValueError("session_date is not in the historical diagnostic")
        expected = ACCOUNT_SCENARIOS.get(self.account_class)
        if expected is None:
            raise ValueError("unsupported account_class")
        if self.account_id != expected["account_id"]:
            raise ValueError("synthetic account_id differs from registration")
        for field in ("starting_equity", "starting_buying_power"):
            value = float(getattr(self, field))
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{field} must be finite and positive")
            if value != expected[field]:
                raise ValueError(f"{field} differs from registration")
        captured = _aware_timestamp(self.captured_at, "captured_at")
        if captured.tz_convert("America/New_York").date() != self.session_date:
            raise ValueError("captured_at must belong to session_date")
        if captured.tz_convert("America/New_York").time() > time(7, 0):
            raise ValueError("synthetic snapshot must be pre-session")
        if self.source_id != "registered-synthetic-fixed-balance-v0.1":
            raise ValueError("source_id differs from registration")
        _require_sha256(self.source_content_sha256, "source_content_sha256")


@dataclass(frozen=True, slots=True)
class HistoricalDiagnosticBuild:
    manifest: dict[str, object]
    session_artifacts: dict[str, dict[str, object]]


def build_historical_account_diagnostic(
    source_zip: str | Path,
    micro_zip: str | Path,
    registration: Mapping[str, object],
) -> HistoricalDiagnosticBuild:
    """Compose the registered ten-session diagnostic from exact frozen ZIPs."""
    validate_historical_diagnostic_contract(registration)
    source_path = Path(source_zip)
    micro_path = Path(micro_zip)
    _require_file_hash(source_path, SOURCE_ZIP_SHA256, "source ZIP")
    _require_file_hash(micro_path, MICRO_ZIP_SHA256, "Micro ZIP")

    with ZipFile(source_path) as source, ZipFile(micro_path) as micro:
        source_manifest = _read_frozen_json(
            source,
            "heldout-runtime-manifest.json",
            file_sha256=SOURCE_MANIFEST_FILE_SHA256,
            content_sha256=SOURCE_MANIFEST_CONTENT_SHA256,
        )
        scanner_aggregate = _read_frozen_json(
            source,
            "causal-scanner-snapshot-v0.1/manifest.json",
            file_sha256=SCANNER_AGGREGATE_FILE_SHA256,
            content_sha256=SCANNER_AGGREGATE_CONTENT_SHA256,
        )
        micro_manifest = _read_frozen_json(
            micro,
            "manifest.json",
            file_sha256=MICRO_MANIFEST_FILE_SHA256,
            content_sha256=MICRO_MANIFEST_CONTENT_SHA256,
        )
        _validate_source_manifests(
            source_manifest,
            scanner_aggregate,
            micro_manifest,
        )

        candidate_results = _candidate_results_by_date(micro_manifest)
        session_artifacts: dict[str, dict[str, object]] = {}
        session_index: list[dict[str, object]] = []

        for trading_date in REGISTERED_DATES:
            scanner_path = (
                f"causal-scanner-snapshot-v0.1/{trading_date}/scanner-snapshot.json"
            )
            scanner_payload = _read_frozen_json(source, scanner_path)
            expected_scanner_hash = source_manifest["date_results"][trading_date][
                "scanner_records_content_sha256"
            ]
            if scanner_payload.get("content_sha256") != expected_scanner_hash:
                raise ValueError(f"{trading_date} scanner hash differs from heldout manifest")
            rows = scanner_payload.get("rows")
            if not isinstance(rows, list):
                raise ValueError(f"{trading_date} scanner rows must be an array")
            row_index = _scanner_row_index(rows)

            date_manifest = _read_frozen_json(
                micro,
                f"dates/{trading_date}/manifest.json",
                content_sha256=micro_manifest["date_results"][trading_date][
                    "date_manifest_content_sha256"
                ],
            )
            _validate_date_manifest(
                trading_date,
                date_manifest,
                candidate_results[trading_date],
            )

            account_records: dict[AccountClass, list[AccountCandidateRuntime]] = {
                AccountClass.MAIN: [],
                AccountClass.SMALL: [],
            }
            eligible_counts = {AccountClass.MAIN: 0, AccountClass.SMALL: 0}
            unavailable_eligible = {AccountClass.MAIN: 0, AccountClass.SMALL: 0}

            for candidate_result in candidate_results[trading_date]:
                symbol = _nonempty_text(candidate_result, "symbol")
                qualified_at = _nonempty_text(
                    candidate_result,
                    "candidate_qualified_at",
                )
                key = (symbol, qualified_at)
                matching_rows = row_index.get(key, ())
                if len(matching_rows) != 1:
                    raise ValueError(
                        f"{trading_date} {symbol} requires one exact activation row; "
                        f"found {len(matching_rows)}"
                    )
                row = matching_rows[0]
                snapshots = {
                    AccountClass.MAIN: candidate_snapshot_from_causal_row(
                        row,
                        current_general_2026(),
                    ),
                    AccountClass.SMALL: candidate_snapshot_from_causal_row(
                        row,
                        current_small_account_2026(),
                    ),
                }
                for account_class, snapshot in snapshots.items():
                    if snapshot.quality is not CandidateQuality.REJECT:
                        eligible_counts[account_class] += 1

                status = _nonempty_text(candidate_result, "status")
                runtime_hash = _nonempty_text(
                    candidate_result,
                    "runtime_content_sha256",
                )
                _require_sha256(runtime_hash, "runtime_content_sha256")
                replay: MicroCandidateReplay | None = None
                if any(
                    snapshot.quality is not CandidateQuality.REJECT
                    for snapshot in snapshots.values()
                ):
                    runtime = _read_frozen_json(
                        micro,
                        f"dates/{trading_date}/{symbol}/runtime-replay.json",
                        content_sha256=runtime_hash,
                    )
                    if status == "replayed":
                        replay = micro_replay_from_runtime(runtime)
                    elif runtime.get("status") != status:
                        raise ValueError(
                            f"{trading_date} {symbol} runtime status differs from manifest"
                        )

                scanner_row_hash = canonical_fingerprint(row)
                for account_class, snapshot in snapshots.items():
                    profile = _profile(account_class)
                    account_replay = (
                        replay
                        if snapshot.quality is not CandidateQuality.REJECT
                        and status == "replayed"
                        else None
                    )
                    runtime_status = status
                    if snapshot.quality is CandidateQuality.REJECT:
                        runtime_status = "account_profile_rejected"
                    elif account_replay is None:
                        unavailable_eligible[account_class] += 1
                    account_records[account_class].append(
                        AccountCandidateRuntime(
                            activation_id=_activation_id(
                                profile.name,
                                trading_date,
                                symbol,
                                qualified_at,
                            ),
                            strategy_profile_id=profile.name,
                            candidate_snapshot=snapshot,
                            scanner_record_content_sha256=scanner_row_hash,
                            micro_runtime_content_sha256=runtime_hash,
                            runtime_status=runtime_status,
                            micro_replay=account_replay,
                        )
                    )

            for account_class in (AccountClass.MAIN, AccountClass.SMALL):
                snapshot = _synthetic_account_snapshot(
                    account_class,
                    date.fromisoformat(trading_date),
                )
                engine_output = integrate_account_session(
                    snapshot,  # type: ignore[arg-type]
                    account_records[account_class],
                )
                summary = _session_summary(
                    engine_output,
                    source_candidate_count=len(candidate_results[trading_date]),
                    eligible_candidate_count=eligible_counts[account_class],
                    unavailable_eligible_candidate_count=unavailable_eligible[
                        account_class
                    ],
                )
                session_payload = _freeze(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "contract_id": CONTRACT_ID,
                        "artifact_type": "historical_account_diagnostic_session",
                        "labels": list(REQUIRED_LABELS),
                        "session_date": trading_date,
                        "account_class": account_class.value,
                        "source_binding": {
                            "scanner_snapshot_content_sha256": scanner_payload[
                                "content_sha256"
                            ],
                            "micro_date_manifest_content_sha256": date_manifest[
                                "content_sha256"
                            ],
                        },
                        "coverage": _coverage(account_class),
                        "summary": summary,
                        "composition_engine_output": engine_output,
                        "authority_boundary": {
                            "historical_broker_balance_claim": False,
                            "independent_fixed_balance_session": True,
                            "cross_session_compounding": False,
                            "unresolved_positions_marked_to_market": False,
                            "portfolio_backtest_eligible": False,
                            "policy_promotion_eligible": False,
                        },
                    }
                )
                relative_path = f"sessions/{account_class.value}/{trading_date}.json"
                session_artifacts[relative_path] = session_payload
                session_index.append(
                    {
                        "path": relative_path,
                        "session_date": trading_date,
                        "account_class": account_class.value,
                        "content_sha256": session_payload["content_sha256"],
                        "summary": summary,
                    }
                )

    manifest = _freeze(
        {
            "schema_version": SCHEMA_VERSION,
            "contract_id": CONTRACT_ID,
            "artifact_type": "historical_account_diagnostic_manifest",
            "labels": list(REQUIRED_LABELS),
            "registration_content_sha256": canonical_fingerprint(registration),
            "source_artifacts": {
                "causal_scanner_runtime_zip_sha256": SOURCE_ZIP_SHA256,
                "causal_scanner_runtime_content_sha256": (
                    SOURCE_MANIFEST_CONTENT_SHA256
                ),
                "micro_runtime_zip_sha256": MICRO_ZIP_SHA256,
                "micro_runtime_content_sha256": MICRO_MANIFEST_CONTENT_SHA256,
            },
            "dates": list(REGISTERED_DATES),
            "sessions": session_index,
            "account_summaries": {
                account_class.value: _aggregate_summary(
                    session_index,
                    account_class,
                )
                for account_class in (AccountClass.MAIN, AccountClass.SMALL)
            },
            "coverage": {
                "main": _coverage(AccountClass.MAIN),
                "small": _coverage(AccountClass.SMALL),
            },
            "interpretation": {
                "immediate_account_feasibility_diagnostic": True,
                "full_backtest": False,
                "economic_return_estimate": False,
                "source_micro_exit_model": (
                    "stop exits only; no profit target or discretionary favorable exit "
                    "was modeled, and filled-open outcomes remain unresolved"
                ),
                "fixed_balance_sessions_not_compounded": True,
                "open_positions_excluded_from_realized_pnl": True,
                "prospective_august_24_to_september_4_panel_unchanged": True,
                "profitability_or_promotion_claim_allowed": False,
            },
        }
    )
    return HistoricalDiagnosticBuild(
        manifest=manifest,
        session_artifacts=session_artifacts,
    )


def candidate_snapshot_from_causal_row(
    row: Mapping[str, object],
    profile: StrategyProfile,
) -> CandidateSnapshot:
    """Reapply one unchanged account profile to an exact activation row."""
    symbol = _nonempty_text(row, "symbol")
    timestamp = _aware_timestamp(
        _nonempty_text(row, "decision_time"),
        "decision_time",
    )
    if row.get("activation_time") != row.get("decision_time"):
        raise ValueError("diagnostic requires the first activation scanner row")
    if row.get("candidate_completed_bar_present") is not True:
        raise ValueError("activation row must contain its exact completed bar")
    price = _finite_positive_number(row, "price")
    cumulative_volume = _nonnegative_integer(row, "cumulative_volume")
    relative_volume = _finite_nonnegative_number(row, "exact_same_time_rvol")
    percent_gain = _finite_number(row, "percent_gain")
    float_value = row.get("estimated_float_shares")
    float_shares = None if float_value is None else _positive_integer_value(
        float_value,
        "estimated_float_shares",
    )
    has_news = row.get("has_provider_news_as_of")
    if not isinstance(has_news, bool):
        raise ValueError("has_provider_news_as_of must be boolean")
    rank_value = row.get("top_gainer_rank")
    top_gainer_rank = None if rank_value is None else _positive_integer_value(
        rank_value,
        "top_gainer_rank",
    )
    pillars = {
        "percent_gain": percent_gain >= profile.min_percent_gain,
        "relative_volume": relative_volume >= profile.min_relative_volume,
        "fresh_news": has_news if profile.require_fresh_news_for_a_quality else True,
        "price": profile.min_price <= price <= profile.max_price,
        "float": float_shares is not None
        and float_shares < profile.max_float_shares,
    }
    missing = [name for name, passed in pillars.items() if not passed]
    rank_ok = profile.require_top_gainer_rank is None or (
        top_gainer_rank is not None
        and top_gainer_rank <= profile.require_top_gainer_rank
    )
    reasons: list[str] = []
    if not missing and rank_ok:
        quality = CandidateQuality.A_QUALITY
    elif (
        missing == ["fresh_news"]
        and profile.allow_obvious_no_news_exception
        and top_gainer_rank == 1
        and rank_ok
    ):
        quality = CandidateQuality.CONDITIONAL
        reasons.append(
            "no provider news; allowed only as the current #1 obvious gainer exception"
        )
    else:
        quality = CandidateQuality.REJECT
        reasons.extend(f"failed pillar: {name}" for name in missing)
        if not rank_ok:
            reasons.append("outside required top-gainer rank")
    if profile.preferred_min_price <= price <= profile.preferred_max_price:
        reasons.append("inside preferred price band")
    float_rotation = (
        cumulative_volume / float_shares
        if float_shares is not None and float_shares > 0
        else None
    )
    return CandidateSnapshot(
        symbol=symbol,
        timestamp=timestamp.to_pydatetime(),
        price=price,
        cumulative_volume=cumulative_volume,
        relative_volume=relative_volume,
        percent_gain=percent_gain,
        float_shares=float_shares,
        float_rotation=float_rotation,
        has_fresh_news=has_news,
        top_gainer_rank=top_gainer_rank,
        pillars=pillars,
        quality=quality,
        reasons=tuple(reasons),
    )


def micro_replay_from_runtime(runtime: Mapping[str, object]) -> MicroCandidateReplay:
    if runtime.get("artifact_type") != "micro_candidate_runtime_replay":
        raise ValueError("runtime is not a replayed Micro candidate")
    if runtime.get("frozen_policy_fingerprint") != MICRO_POLICY_FINGERPRINT:
        raise ValueError("Micro runtime fingerprint differs from frozen v0.1")
    if runtime.get("retrospective_behavior_labels_loaded") is not False:
        raise ValueError("Micro runtime must remain label-blind")
    steps_payload = runtime.get("steps")
    if not isinstance(steps_payload, list):
        raise ValueError("Micro runtime steps must be an array")
    steps: list[MicroReplayStep] = []
    for row in steps_payload:
        if not isinstance(row, Mapping):
            raise ValueError("Micro step must be an object")
        plan_payload = row.get("plan")
        plan = _micro_plan(plan_payload) if isinstance(plan_payload, Mapping) else None
        outcome_payload = row.get("outcome")
        outcome = None
        if isinstance(outcome_payload, Mapping):
            if plan is None:
                raise ValueError("Micro outcome requires its emitted plan")
            nested = outcome_payload.get("plan")
            if not isinstance(nested, Mapping) or _micro_plan(nested) != plan:
                raise ValueError("Micro outcome plan differs from step plan")
            outcome = MicroExecutionOutcome(
                plan=plan,
                status=MicroExecutionStatus(_nonempty_text(outcome_payload, "status")),
                trigger_mode=MicroTriggerMode(
                    _nonempty_text(outcome_payload, "trigger_mode")
                ),
                entry_latency_ms=float(outcome_payload.get("entry_latency_ms", 0.0)),
                trigger_time=_optional_timestamp(outcome_payload.get("trigger_time")),
                trigger_print_price=_optional_float(
                    outcome_payload.get("trigger_print_price")
                ),
                trigger_via_odd_lot=_optional_bool(
                    outcome_payload.get("trigger_via_odd_lot")
                ),
                fill_time=_optional_timestamp(outcome_payload.get("fill_time")),
                fill_price=_optional_float(outcome_payload.get("fill_price")),
                fill_via_odd_lot=_optional_bool(
                    outcome_payload.get("fill_via_odd_lot")
                ),
                exit_time=_optional_timestamp(outcome_payload.get("exit_time")),
                exit_price=_optional_float(outcome_payload.get("exit_price")),
                exit_via_odd_lot=_optional_bool(
                    outcome_payload.get("exit_via_odd_lot")
                ),
            )
        steps.append(
            MicroReplayStep(
                evaluated_at=_aware_timestamp(
                    _nonempty_text(row, "evaluated_at"),
                    "evaluated_at",
                ).to_pydatetime(),
                pullback_number=_positive_integer_value(
                    row.get("pullback_number"),
                    "pullback_number",
                ),
                reason=_nonempty_text(row, "reason"),
                plan=plan,
                features=None,
                outcome=outcome,
            )
        )
    replay = MicroCandidateReplay(
        symbol=_nonempty_text(runtime, "symbol"),
        candidate_qualified_at=_aware_timestamp(
            _nonempty_text(runtime, "candidate_qualified_at"),
            "candidate_qualified_at",
        ).to_pydatetime(),
        policy_name=_nonempty_text(runtime, "policy_name"),
        trigger_mode=MicroTriggerMode(_nonempty_text(runtime, "trigger_mode")),
        entry_latency_ms=float(runtime.get("entry_latency_ms", 0.0)),
        steps=tuple(steps),
    )
    if replay.plan_count != runtime.get("plan_count"):
        raise ValueError("parsed Micro plan count differs from frozen runtime")
    if replay.filled_count != runtime.get("filled_count"):
        raise ValueError("parsed Micro fill count differs from frozen runtime")
    return replay


def validate_historical_diagnostic_contract(payload: Mapping[str, object]) -> None:
    expected_root = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "artifact_type": "retrospective_account_overlay_registration",
        "registration_date": REGISTRATION_DATE.isoformat(),
        "registration_status": (
            "registered_after_source_runtime_before_account_composition"
        ),
        "runtime_strategy_effect": "none_shadow_only",
        "prospective_contract_modified": False,
        "portfolio_backtest_eligible": False,
        "policy_promotion_eligible": False,
        "profitability_claim_eligible": False,
        "ross_replication_claim_eligible": False,
    }
    for field, expected in expected_root.items():
        if payload.get(field) != expected:
            raise ValueError(f"{field} must be {expected!r}")
    parents = _mapping(payload, "frozen_parents")
    expected_parents = {
        "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
        "campaign_ledger_contract_content_sha256": LEDGER_CONTRACT_SHA256,
        "account_policy_contract_content_sha256": ACCOUNT_POLICY_CONTRACT_SHA256,
        "account_policy_bundle_sha256": ACCOUNT_POLICY_BUNDLE_SHA256,
        "prospective_account_integration_contract_content_sha256": (
            PROSPECTIVE_INTEGRATION_CONTRACT_SHA256
        ),
        "general_strategy_profile_fingerprint": GENERAL_PROFILE_FINGERPRINT,
        "small_strategy_profile_fingerprint": SMALL_PROFILE_FINGERPRINT,
    }
    for field, expected in expected_parents.items():
        if parents.get(field) != expected:
            raise ValueError(f"frozen_parents.{field} differs")
    sources = _mapping(payload, "frozen_sources")
    source = _mapping(sources, "causal_scanner_runtime")
    micro = _mapping(sources, "micro_runtime")
    expected_source = {
        "zip_sha256": SOURCE_ZIP_SHA256,
        "heldout_manifest_file_sha256": SOURCE_MANIFEST_FILE_SHA256,
        "heldout_manifest_content_sha256": SOURCE_MANIFEST_CONTENT_SHA256,
        "scanner_aggregate_manifest_file_sha256": (
            SCANNER_AGGREGATE_FILE_SHA256
        ),
        "scanner_aggregate_manifest_content_sha256": (
            SCANNER_AGGREGATE_CONTENT_SHA256
        ),
    }
    expected_micro = {
        "zip_sha256": MICRO_ZIP_SHA256,
        "manifest_file_sha256": MICRO_MANIFEST_FILE_SHA256,
        "manifest_content_sha256": MICRO_MANIFEST_CONTENT_SHA256,
        "source_heldout_runtime_content_sha256": (
            SOURCE_MANIFEST_CONTENT_SHA256
        ),
    }
    for field, expected in expected_source.items():
        if source.get(field) != expected:
            raise ValueError(f"frozen source {field} differs")
    for field, expected in expected_micro.items():
        if micro.get(field) != expected:
            raise ValueError(f"frozen Micro {field} differs")
    sampling = _mapping(payload, "sampling_contract")
    if tuple(sampling.get("dates", ())) != REGISTERED_DATES:
        raise ValueError("sampling dates differ from registration")
    if sampling.get("date_or_symbol_selection_changed") is not False:
        raise ValueError("date or symbol selection cannot change")
    candidate = _mapping(payload, "candidate_contract")
    if not str(candidate.get("small_account_coverage", "")).startswith(
        "partial_same_anchor_overlap_only"
    ):
        raise ValueError("small-account coverage limit must remain explicit")
    account = _mapping(payload, "synthetic_account_contract")
    for account_class in (AccountClass.MAIN, AccountClass.SMALL):
        row = _mapping(account, account_class.value)
        expected = ACCOUNT_SCENARIOS[account_class]
        for field, value in expected.items():
            if row.get(field) != value:
                raise ValueError(f"synthetic {account_class.value}.{field} differs")
    knowledge = _mapping(payload, "knowledge_policy")
    for field in (
        "raw_transcripts_used",
        "ross_actions_labels_or_reported_fills_used",
        "retrospective_behavior_labels_used",
        "semantic_context_used",
        "later_unmodeled_prices_used_to_close_positions",
    ):
        if knowledge.get(field) is not False:
            raise ValueError(f"knowledge_policy.{field} must be false")
    status = _mapping(payload, "execution_status")
    if status != {
        "account_composition": "not_started_at_registration",
        "runtime_artifact_sha256": None,
    }:
        raise ValueError("registration execution status changed")


def load_historical_diagnostic_contract(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("historical diagnostic contract root must be an object")
    validate_historical_diagnostic_contract(payload)
    return payload


def canonical_fingerprint(payload: object) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _validate_source_manifests(
    source: Mapping[str, object],
    scanner: Mapping[str, object],
    micro: Mapping[str, object],
) -> None:
    if tuple(source.get("dates", ())) != REGISTERED_DATES:
        raise ValueError("heldout source dates differ")
    if tuple(scanner.get("dates", ())) != REGISTERED_DATES:
        raise ValueError("scanner source dates differ")
    if tuple(micro.get("dates", ())) != REGISTERED_DATES:
        raise ValueError("Micro source dates differ")
    if micro.get("source_heldout_runtime_content_sha256") != (
        SOURCE_MANIFEST_CONTENT_SHA256
    ):
        raise ValueError("Micro source does not bind the heldout scanner runtime")
    policy = micro.get("frozen_micro_policy")
    if not isinstance(policy, Mapping) or policy.get("fingerprint") != (
        MICRO_POLICY_FINGERPRINT
    ):
        raise ValueError("Micro aggregate policy fingerprint differs")


def _candidate_results_by_date(
    manifest: Mapping[str, object],
) -> dict[str, list[Mapping[str, object]]]:
    rows = manifest.get("candidate_results")
    if not isinstance(rows, list):
        raise ValueError("Micro aggregate candidate_results must be an array")
    grouped = {value: [] for value in REGISTERED_DATES}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("Micro aggregate candidate result must be an object")
        trading_date = _nonempty_text(row, "trading_date")
        if trading_date not in grouped:
            raise ValueError("Micro aggregate includes an unregistered date")
        grouped[trading_date].append(row)
    if sum(len(value) for value in grouped.values()) != 119:
        raise ValueError("Micro aggregate candidate count differs from frozen audit")
    for values in grouped.values():
        values.sort(key=lambda row: (_nonempty_text(row, "symbol")))
    return grouped


def _scanner_row_index(
    rows: list[object],
) -> dict[tuple[str, str], tuple[Mapping[str, object], ...]]:
    grouped: dict[tuple[str, str], list[Mapping[str, object]]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("scanner row must be an object")
        key = (
            _nonempty_text(row, "symbol"),
            _nonempty_text(row, "decision_time"),
        )
        grouped.setdefault(key, []).append(row)
    return {key: tuple(value) for key, value in grouped.items()}


def _validate_date_manifest(
    trading_date: str,
    manifest: Mapping[str, object],
    aggregate_rows: list[Mapping[str, object]],
) -> None:
    if manifest.get("trading_date") != trading_date:
        raise ValueError("Micro date manifest trading_date differs")
    if manifest.get("source_heldout_runtime_content_sha256") != (
        SOURCE_MANIFEST_CONTENT_SHA256
    ):
        raise ValueError("Micro date manifest source hash differs")
    rows = manifest.get("candidate_results")
    if not isinstance(rows, Mapping):
        raise ValueError("Micro date candidate_results must be an object")
    expected = {
        _nonempty_text(row, "symbol"): {
            "status": row.get("status"),
            "candidate_qualified_at": row.get("candidate_qualified_at"),
            "plan_count": row.get("plan_count"),
            "filled_count": row.get("filled_count"),
            "runtime_content_sha256": row.get("runtime_content_sha256"),
        }
        for row in aggregate_rows
    }
    if dict(rows) != expected:
        raise ValueError(f"{trading_date} date and aggregate candidate results differ")


def _synthetic_account_snapshot(
    account_class: AccountClass,
    session_date: date,
) -> HistoricalDiagnosticAccountSnapshot:
    scenario = ACCOUNT_SCENARIOS[account_class]
    source = {
        "contract_id": CONTRACT_ID,
        "account_class": account_class.value,
        "session_date": session_date.isoformat(),
        "starting_equity": scenario["starting_equity"],
        "starting_buying_power": scenario["starting_buying_power"],
        "semantics": "independent_fixed_balance_historical_feasibility_scenario",
    }
    return HistoricalDiagnosticAccountSnapshot(
        account_id=str(scenario["account_id"]),
        account_class=account_class,
        session_date=session_date,
        captured_at=datetime.combine(
            session_date,
            time(6, 59),
            ZoneInfo("America/New_York"),
        ),
        starting_equity=float(scenario["starting_equity"]),
        starting_buying_power=float(scenario["starting_buying_power"]),
        source_id="registered-synthetic-fixed-balance-v0.1",
        source_content_sha256=canonical_fingerprint(source),
    )


def _profile(account_class: AccountClass) -> StrategyProfile:
    return (
        current_general_2026()
        if account_class is AccountClass.MAIN
        else current_small_account_2026()
    )


def _activation_id(
    profile_id: str,
    trading_date: str,
    symbol: str,
    qualified_at: str,
) -> str:
    return f"activation-{canonical_fingerprint([profile_id, trading_date, symbol, qualified_at])}"


def _micro_plan(payload: Mapping[str, object]) -> MicroEntryPlan:
    return MicroEntryPlan(
        symbol=_nonempty_text(payload, "symbol"),
        source_bar_start=_aware_timestamp(
            _nonempty_text(payload, "source_bar_start"),
            "source_bar_start",
        ),
        armed_at=_aware_timestamp(
            _nonempty_text(payload, "armed_at"),
            "armed_at",
        ),
        expires_at=_aware_timestamp(
            _nonempty_text(payload, "expires_at"),
            "expires_at",
        ),
        breakout_level=_finite_positive_number(payload, "breakout_level"),
        minimum_new_high_price=_finite_positive_number(
            payload,
            "minimum_new_high_price",
        ),
        stop_price=_finite_positive_number(payload, "stop_price"),
    )


def _session_summary(
    output: Mapping[str, object],
    *,
    source_candidate_count: int,
    eligible_candidate_count: int,
    unavailable_eligible_candidate_count: int,
) -> dict[str, object]:
    events = output.get("integration_events")
    ledger = output.get("ledger_artifact")
    if not isinstance(events, list) or not isinstance(ledger, Mapping):
        raise ValueError("composition engine output is malformed")
    account = ledger.get("account")
    if not isinstance(account, Mapping):
        raise ValueError("composition engine ledger account is malformed")
    counts: dict[str, int] = {}
    for event in events:
        if not isinstance(event, Mapping):
            raise ValueError("composition engine event is malformed")
        event_type = _nonempty_text(event, "event_type")
        counts[event_type] = counts.get(event_type, 0) + 1
    realized_pnl = float(account.get("realized_pnl", 0.0))
    starting_equity = float(account["starting_equity"])
    return {
        "source_candidate_count": source_candidate_count,
        "eligible_candidate_count": eligible_candidate_count,
        "profile_rejected_candidate_count": (
            source_candidate_count - eligible_candidate_count
        ),
        "unavailable_eligible_candidate_count": unavailable_eligible_candidate_count,
        "plan_emission_count": counts.get("plan_emission", 0),
        "accepted_entry_count": counts.get("entry_accepted", 0),
        "rejected_entry_count": counts.get("entry_rejected", 0),
        "not_submitted_entry_count": counts.get("entry_not_submitted", 0),
        "accepted_exit_count": counts.get("exit_accepted", 0),
        "rejected_exit_count": counts.get("exit_rejected", 0),
        "not_applied_exit_count": counts.get("exit_not_applied", 0),
        "realized_pnl": realized_pnl,
        "fixed_starting_equity": starting_equity,
        "realized_stop_only_pnl_fraction_of_fixed_starting_equity": (
            realized_pnl / starting_equity
        ),
        "ending_equity_if_realized_only": starting_equity + realized_pnl,
        "open_campaign_count": int(account["open_campaign_count"]),
        "unresolved_open_notional": float(account["total_open_notional"]),
        "unresolved_open_risk": float(account["total_open_risk"]),
        "session_locked": bool(account["locked"]),
        "session_lock_reason": account.get("lock_reason"),
    }


def _aggregate_summary(
    index: list[Mapping[str, object]],
    account_class: AccountClass,
) -> dict[str, object]:
    rows = [row for row in index if row.get("account_class") == account_class.value]
    if len(rows) != len(REGISTERED_DATES):
        raise ValueError("account session index is incomplete")
    summaries = [row["summary"] for row in rows]
    if not all(isinstance(row, Mapping) for row in summaries):
        raise ValueError("account session summary is malformed")
    starting_equity = float(ACCOUNT_SCENARIOS[account_class]["starting_equity"])
    realized = sum(float(row["realized_pnl"]) for row in summaries)
    return {
        "account_class": account_class.value,
        "session_count": len(rows),
        "fixed_starting_equity_per_session": starting_equity,
        "sum_of_independently_sized_realized_pnl": realized,
        "realized_stop_only_pnl_sum_over_fixed_starting_equity": (
            realized / starting_equity
        ),
        "positive_realized_sessions": sum(
            float(row["realized_pnl"]) > 0 for row in summaries
        ),
        "negative_realized_sessions": sum(
            float(row["realized_pnl"]) < 0 for row in summaries
        ),
        "flat_realized_sessions": sum(
            float(row["realized_pnl"]) == 0 for row in summaries
        ),
        "eligible_candidate_count": sum(
            int(row["eligible_candidate_count"]) for row in summaries
        ),
        "accepted_entry_count": sum(
            int(row["accepted_entry_count"]) for row in summaries
        ),
        "accepted_exit_count": sum(
            int(row["accepted_exit_count"]) for row in summaries
        ),
        "sessions_with_unresolved_open_positions": sum(
            int(row["open_campaign_count"]) > 0 for row in summaries
        ),
        "unresolved_open_notional_sum_across_independent_sessions": sum(
            float(row["unresolved_open_notional"]) for row in summaries
        ),
        "result_is_compounded_equity_curve": False,
        "result_is_full_backtest": False,
        "result_is_economic_return_estimate": False,
    }


def _coverage(account_class: AccountClass) -> dict[str, object]:
    if account_class is AccountClass.MAIN:
        return {
            "every_frozen_candidate_anchor_evaluated": True,
            "complete_account_qualified_activation_set": False,
            "complete_market_universe": False,
            "reason": (
                "Qualification is tested only at the frozen market/Micro anchor; a "
                "candidate first becoming account-eligible on a later scanner row is "
                "not re-anchored, and the historical universe is not full-walk-forward "
                "eligible."
            ),
        }
    return {
        "every_frozen_candidate_anchor_evaluated": True,
        "complete_account_qualified_activation_set": False,
        "complete_small_profile_candidate_universe": False,
        "complete_market_universe": False,
        "reason": (
            "The general-profile source may omit small-profile candidates priced "
            "from 1.50 through 1.99, and candidates first satisfying the small "
            "profile after the frozen general anchor are not re-anchored."
        ),
    }


def _read_frozen_json(
    archive: ZipFile,
    name: str,
    *,
    file_sha256: str | None = None,
    content_sha256: str | None = None,
) -> dict[str, object]:
    raw = archive.read(name)
    if file_sha256 is not None and hashlib.sha256(raw).hexdigest() != file_sha256:
        raise ValueError(f"{name} file SHA-256 differs")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"{name} root must be an object")
    embedded = payload.get("content_sha256")
    if not isinstance(embedded, str):
        raise ValueError(f"{name} lacks content_sha256")
    recomputed = canonical_fingerprint(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )
    if embedded != recomputed:
        raise ValueError(f"{name} embedded content SHA-256 is invalid")
    if content_sha256 is not None and embedded != content_sha256:
        raise ValueError(f"{name} content SHA-256 differs")
    return payload


def _require_file_hash(path: Path, expected: str, label: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise ValueError(f"{label} SHA-256 differs from registration")


def _freeze(payload: dict[str, object]) -> dict[str, object]:
    result = dict(payload)
    result["content_sha256"] = canonical_fingerprint(result)
    return result


def _canonical_json(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _mapping(payload: Mapping[str, object], field: str) -> Mapping[str, object]:
    value = payload.get(field)
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _nonempty_text(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value


def _aware_timestamp(value: object, field: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return timestamp


def _optional_timestamp(value: object) -> pd.Timestamp | None:
    return None if value is None else _aware_timestamp(value, "optional timestamp")


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError("optional numeric field must be finite")
    return numeric


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError("optional boolean field must be boolean")
    return value


def _finite_number(payload: Mapping[str, object], field: str) -> float:
    value = payload.get(field)
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    numeric = float(value)  # type: ignore[arg-type]
    if not math.isfinite(numeric):
        raise ValueError(f"{field} must be finite")
    return numeric


def _finite_positive_number(payload: Mapping[str, object], field: str) -> float:
    value = _finite_number(payload, field)
    if value <= 0:
        raise ValueError(f"{field} must be positive")
    return value


def _finite_nonnegative_number(payload: Mapping[str, object], field: str) -> float:
    value = _finite_number(payload, field)
    if value < 0:
        raise ValueError(f"{field} must be nonnegative")
    return value


def _nonnegative_integer(payload: Mapping[str, object], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or int(value) != value:  # type: ignore[arg-type]
        raise ValueError(f"{field} must be an integer")
    result = int(value)  # type: ignore[arg-type]
    if result < 0:
        raise ValueError(f"{field} must be nonnegative")
    return result


def _positive_integer_value(value: object, field: str) -> int:
    if isinstance(value, bool) or int(value) != value:  # type: ignore[arg-type]
        raise ValueError(f"{field} must be an integer")
    result = int(value)  # type: ignore[arg-type]
    if result < 1:
        raise ValueError(f"{field} must be positive")
    return result


def _require_sha256(value: str, field: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field} must be a lowercase SHA-256")
