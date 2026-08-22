"""Deterministic daily freeze for prospective Micro entry decisions.

The source accepted here is deliberately smaller than a completed Micro replay.
It contains only causal entry-decision events already emitted by the frozen
scanner/Micro runtime.  Account balances, scarcity ordering, execution
scenarios, fills, exits, outcomes, retrospective labels, and provider records
are outside this boundary.

This module has no network client and no order path.  Its only market-input
handoff delegates to the already registered offline request derivation in
``prospective_market_input_capture``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

from momentumbot.research.account_chronological_integration import (
    MICRO_POLICY_FINGERPRINT,
    PANEL_ID,
    REGISTERED_DATES,
)
from momentumbot.research.account_priority_policy import (
    GENERAL_PROFILE_FINGERPRINT,
    SMALL_PROFILE_FINGERPRINT,
)
from momentumbot.research.microstructure_contract import canonical_fingerprint
from momentumbot.research.prospective_market_input_capture import (
    CONTRACT_CONTENT_SHA256 as MARKET_INPUT_CONTRACT_CONTENT_SHA256,
    CONTRACT_ID as MARKET_INPUT_CONTRACT_ID,
    build_request_manifest,
    validate_capture_contract,
    validate_opportunity_manifest,
)


SCHEMA_VERSION = 1
CONTRACT_ID = "prospective-opportunity-freeze-v0.1"
CONTRACT_CONTENT_SHA256 = (
    "13e4458b20b64c81dc24508d2515b20cce8b61f565816e0a3ba0eea4dcee66e1"
)
PARENT_CHECKPOINT_SHA = "fa786a79103375d3c67b01240663873e2b5478df"
PARENT_CHECKPOINT_TREE_SHA = "03ea9336c25c058ec96cc26f353a3be5a4f7102c"
ACCOUNT_INTEGRATION_CONTRACT_CONTENT_SHA256 = (
    "64489aa27fec5eaf8ca12c94f4aeb47344d49a79b14df1bdda706cd23cc9ce73"
)

SOURCE_ARTIFACT_TYPE = "frozen_label_blind_prospective_micro_decisions"
OPPORTUNITY_ARTIFACT_TYPE = "frozen_label_blind_prospective_opportunities"
FREEZE_ARTIFACT_TYPE = "prospective_opportunity_request_freeze_handoff"
DECISION_SEMANTICS = (
    "causal_micro_trigger_at_order_decision_before_execution_simulation"
)
DECISION_CLOCK = "utc_unix_epoch_nanoseconds"
GENERAL_PROFILE_ID = "current-general-2026"
SMALL_PROFILE_ID = "current-small-account-2026"
STRATEGY_PROFILE_IDS = (GENERAL_PROFILE_ID, SMALL_PROFILE_ID)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.+\-]{0,31}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{0,255}$")
_NEW_YORK = ZoneInfo("America/New_York")
_SOURCE_FIELDS = {
    "schema_version",
    "artifact_id",
    "artifact_type",
    "panel_id",
    "trading_date",
    "scanner_runtime_content_sha256",
    "micro_runtime_manifest_content_sha256",
    "micro_policy_fingerprint",
    "decision_clock",
    "decision_semantics",
    "candidate_count",
    "decision_count",
    "decisions",
    "account_snapshot_loaded",
    "account_scarcity_applied",
    "execution_scenario_applied",
    "provider_quote_made",
    "retrospective_labels_loaded",
    "later_prices_or_pnl_loaded",
    "content_sha256",
}
_DECISION_INPUT_FIELDS = {
    "activation_id",
    "plan_id",
    "symbol",
    "candidate_qualified_ts_ns",
    "decision_ts_ns",
    "micro_runtime_content_sha256",
    "eligible_strategy_profile_ids",
}
_DECISION_FIELDS = _DECISION_INPUT_FIELDS | {"opportunity_id"}
_FORBIDDEN_SOURCE_KEYS = {
    "account_id",
    "benchmark_label",
    "buying_power",
    "entry_price",
    "equity",
    "exit",
    "exit_price",
    "exit_time",
    "fill",
    "fill_price",
    "fill_time",
    "human_action",
    "later_price",
    "later_prices",
    "loss",
    "outcome",
    "outcomes",
    "pnl",
    "profit",
    "quantity",
    "recap",
    "recaps",
    "reported_fill",
    "retrospective_label",
    "ross_action",
    "ross_label",
    "selected_horizon",
    "selected_scenario",
    "trade_outcome",
    "transcript_text",
}


@dataclass(frozen=True, slots=True)
class ProspectiveMicroDecision:
    opportunity_id: str
    activation_id: str
    plan_id: str
    symbol: str
    candidate_qualified_ts_ns: int
    decision_ts_ns: int
    micro_runtime_content_sha256: str
    eligible_strategy_profile_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProspectiveOpportunityFreeze:
    opportunity_manifest: dict[str, object]
    request_manifest: dict[str, object]
    freeze_manifest: dict[str, object]


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _array(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    return value


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return value


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field} must be a stable identifier")
    return value


def _symbol(value: object) -> str:
    if not isinstance(value, str) or not _SYMBOL.fullmatch(value):
        raise ValueError("symbol must use canonical uppercase US-equity notation")
    return value


def _walk_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            keys.add(str(key).lower())
            keys.update(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_walk_keys(child))
    return keys


def _fingerprinted(payload: Mapping[str, object], field: str) -> str:
    claimed = _sha256(payload.get("content_sha256"), f"{field}.content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if canonical_fingerprint(unsigned) != claimed:
        raise ValueError(f"{field} content fingerprint changed")
    return claimed


def _freeze(payload: Mapping[str, object]) -> dict[str, object]:
    result = dict(payload)
    result["content_sha256"] = canonical_fingerprint(result)
    return result


def _local_date(timestamp_ns: int) -> str:
    seconds, _nanoseconds = divmod(timestamp_ns, 1_000_000_000)
    return datetime.fromtimestamp(seconds, tz=UTC).astimezone(_NEW_YORK).date().isoformat()


def _profiles(value: object) -> tuple[str, ...]:
    rows = _array(value, "eligible_strategy_profile_ids")
    if not rows or any(not isinstance(item, str) for item in rows):
        raise ValueError("eligible_strategy_profile_ids must be a non-empty string array")
    parsed = tuple(rows)
    if parsed != tuple(sorted(set(parsed))):
        raise ValueError("eligible strategy profiles must be unique and sorted")
    if not set(parsed).issubset(STRATEGY_PROFILE_IDS):
        raise ValueError("eligible strategy profile is outside the frozen account panel")
    return parsed


def expected_opportunity_id(
    *,
    trading_date: str,
    activation_id: str,
    plan_id: str,
    symbol: str,
    decision_ts_ns: int,
    micro_runtime_content_sha256: str,
) -> str:
    identity = {
        "panel_id": PANEL_ID,
        "trading_date": trading_date,
        "activation_id": activation_id,
        "plan_id": plan_id,
        "symbol": symbol,
        "decision_ts_ns": decision_ts_ns,
        "micro_runtime_content_sha256": micro_runtime_content_sha256,
    }
    return f"opportunity-{canonical_fingerprint(identity)}"


def validate_opportunity_freeze_contract(payload: Mapping[str, object]) -> None:
    expected_root = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "artifact_type": "preregistered_unarmed_prospective_opportunity_freeze",
        "registration_date": "2026-08-22",
        "registration_status": "registered_before_prospective_panel_runtime",
        "runtime_strategy_effect": "none_materialization_only",
    }
    for field, expected in expected_root.items():
        if payload.get(field) != expected:
            raise ValueError(f"opportunity freeze contract {field} changed")
    if _fingerprinted(payload, "opportunity freeze contract") != CONTRACT_CONTENT_SHA256:
        raise ValueError("opportunity freeze contract content fingerprint changed")

    parents = _mapping(payload.get("frozen_parents"), "frozen_parents")
    expected_parents = {
        "parent_checkpoint_sha": PARENT_CHECKPOINT_SHA,
        "parent_checkpoint_tree_sha": PARENT_CHECKPOINT_TREE_SHA,
        "market_input_capture_contract_id": MARKET_INPUT_CONTRACT_ID,
        "market_input_capture_contract_content_sha256": (
            MARKET_INPUT_CONTRACT_CONTENT_SHA256
        ),
        "account_integration_contract_content_sha256": (
            ACCOUNT_INTEGRATION_CONTRACT_CONTENT_SHA256
        ),
        "account_panel_id": PANEL_ID,
        "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
        "general_strategy_profile_fingerprint": GENERAL_PROFILE_FINGERPRINT,
        "small_strategy_profile_fingerprint": SMALL_PROFILE_FINGERPRINT,
    }
    if dict(parents) != expected_parents:
        raise ValueError("opportunity freeze parent bindings changed")

    source = _mapping(payload.get("source_contract"), "source_contract")
    expected_source = {
        "artifact_type": SOURCE_ARTIFACT_TYPE,
        "registered_dates": list(REGISTERED_DATES),
        "decision_clock": DECISION_CLOCK,
        "decision_semantics": DECISION_SEMANTICS,
        "eligible_strategy_profile_ids": list(STRATEGY_PROFILE_IDS),
        "profile_union_required": True,
        "every_causal_micro_decision_retained": True,
        "zero_decision_date_retained": True,
        "account_snapshot_may_select_source_decisions": False,
        "account_scarcity_may_select_source_decisions": False,
        "execution_scenario_may_select_source_decisions": False,
    }
    if dict(source) != expected_source:
        raise ValueError("opportunity freeze source contract changed")

    output = _mapping(payload.get("output_contract"), "output_contract")
    expected_output = {
        "opportunity_artifact_type": OPPORTUNITY_ARTIFACT_TYPE,
        "opportunity_fields": [
            "opportunity_id",
            "trading_date",
            "symbol",
            "decision_ts_ns",
            "runtime_content_sha256",
        ],
        "request_derivation_contract_id": MARKET_INPUT_CONTRACT_ID,
        "request_derivation_is_offline": True,
        "provider_quote_made": False,
        "provider_download_made": False,
        "broker_order_made": False,
    }
    if dict(output) != expected_output:
        raise ValueError("opportunity freeze output contract changed")

    authority = _mapping(payload.get("authority_boundary"), "authority_boundary")
    expected_false = {
        "provider_metadata_quote_authorized",
        "provider_request_authorized",
        "provider_purchase_authorized",
        "broker_order_authorized",
        "paper_order_authorized",
        "live_order_authorized",
        "account_selection_authorized",
        "execution_scenario_selection_authorized",
        "retrospective_labels_allowed",
        "later_prices_or_pnl_allowed",
        "runtime_authority_created",
        "policy_promotion_eligible",
        "profitability_claim_eligible",
    }
    if authority.get("databento_credit_authorized_usd") != "0":
        raise ValueError("opportunity freeze authorizes zero Databento credit")
    if any(authority.get(field) is not False for field in expected_false):
        raise ValueError("opportunity freeze authority expanded")


def load_opportunity_freeze_contract(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("opportunity freeze contract root must be an object")
    validate_opportunity_freeze_contract(payload)
    return payload


def build_daily_decision_source(
    *,
    trading_date: str,
    scanner_runtime_content_sha256: str,
    micro_runtime_manifest_content_sha256: str,
    candidate_count: int,
    decisions: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Freeze normalized causal decisions emitted by a future daily producer."""
    if trading_date not in REGISTERED_DATES:
        raise ValueError("trading_date is outside the registered panel")
    _sha256(scanner_runtime_content_sha256, "scanner_runtime_content_sha256")
    _sha256(
        micro_runtime_manifest_content_sha256,
        "micro_runtime_manifest_content_sha256",
    )
    _integer(candidate_count, "candidate_count")
    normalized: list[dict[str, object]] = []
    for index, raw in enumerate(decisions):
        row = _mapping(raw, f"decisions[{index}]")
        if set(row) != _DECISION_INPUT_FIELDS:
            raise ValueError("decision input fields changed")
        activation_id = _identifier(row.get("activation_id"), "activation_id")
        plan_id = _identifier(row.get("plan_id"), "plan_id")
        symbol = _symbol(row.get("symbol"))
        qualified = _integer(
            row.get("candidate_qualified_ts_ns"),
            "candidate_qualified_ts_ns",
            minimum=1,
        )
        decision = _integer(row.get("decision_ts_ns"), "decision_ts_ns", minimum=1)
        if qualified > decision:
            raise ValueError("candidate qualification cannot follow its decision")
        runtime_hash = _sha256(
            row.get("micro_runtime_content_sha256"),
            "micro_runtime_content_sha256",
        )
        profiles = _profiles(row.get("eligible_strategy_profile_ids"))
        normalized.append(
            {
                "opportunity_id": expected_opportunity_id(
                    trading_date=trading_date,
                    activation_id=activation_id,
                    plan_id=plan_id,
                    symbol=symbol,
                    decision_ts_ns=decision,
                    micro_runtime_content_sha256=runtime_hash,
                ),
                "activation_id": activation_id,
                "plan_id": plan_id,
                "symbol": symbol,
                "candidate_qualified_ts_ns": qualified,
                "decision_ts_ns": decision,
                "micro_runtime_content_sha256": runtime_hash,
                "eligible_strategy_profile_ids": list(profiles),
            }
        )
    normalized.sort(
        key=lambda row: (
            row["decision_ts_ns"],
            row["symbol"],
            row["opportunity_id"],
        )
    )
    payload = _freeze(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_id": f"prospective-daily-micro-decisions-{trading_date}",
            "artifact_type": SOURCE_ARTIFACT_TYPE,
            "panel_id": PANEL_ID,
            "trading_date": trading_date,
            "scanner_runtime_content_sha256": scanner_runtime_content_sha256,
            "micro_runtime_manifest_content_sha256": (
                micro_runtime_manifest_content_sha256
            ),
            "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
            "decision_clock": DECISION_CLOCK,
            "decision_semantics": DECISION_SEMANTICS,
            "candidate_count": candidate_count,
            "decision_count": len(normalized),
            "decisions": normalized,
            "account_snapshot_loaded": False,
            "account_scarcity_applied": False,
            "execution_scenario_applied": False,
            "provider_quote_made": False,
            "retrospective_labels_loaded": False,
            "later_prices_or_pnl_loaded": False,
        }
    )
    validate_daily_decision_source(payload)
    return payload


def validate_daily_decision_source(
    payload: Mapping[str, object],
) -> tuple[ProspectiveMicroDecision, ...]:
    if set(payload) != _SOURCE_FIELDS:
        raise ValueError("daily decision source fields changed")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported daily decision source schema")
    if payload.get("artifact_type") != SOURCE_ARTIFACT_TYPE:
        raise ValueError("unexpected daily decision source type")
    if payload.get("panel_id") != PANEL_ID:
        raise ValueError("daily decision source panel changed")
    trading_date = payload.get("trading_date")
    if not isinstance(trading_date, str) or trading_date not in REGISTERED_DATES:
        raise ValueError("daily decision source date is outside the registered panel")
    if payload.get("artifact_id") != f"prospective-daily-micro-decisions-{trading_date}":
        raise ValueError("daily decision source artifact_id changed")
    _sha256(payload.get("scanner_runtime_content_sha256"), "scanner runtime hash")
    _sha256(
        payload.get("micro_runtime_manifest_content_sha256"),
        "Micro runtime manifest hash",
    )
    if payload.get("micro_policy_fingerprint") != MICRO_POLICY_FINGERPRINT:
        raise ValueError("daily decision source Micro policy changed")
    if payload.get("decision_clock") != DECISION_CLOCK:
        raise ValueError("daily decision source clock changed")
    if payload.get("decision_semantics") != DECISION_SEMANTICS:
        raise ValueError("daily decision semantics changed")
    candidate_count = _integer(payload.get("candidate_count"), "candidate_count")
    flags = (
        "account_snapshot_loaded",
        "account_scarcity_applied",
        "execution_scenario_applied",
        "provider_quote_made",
        "retrospective_labels_loaded",
        "later_prices_or_pnl_loaded",
    )
    if any(payload.get(field) is not False for field in flags):
        raise ValueError("daily decision source crossed a prohibited boundary")
    forbidden = sorted(_walk_keys(payload) & _FORBIDDEN_SOURCE_KEYS)
    if forbidden:
        raise ValueError(f"daily decision source contains forbidden keys: {forbidden}")
    _fingerprinted(payload, "daily decision source")

    raw_rows = _array(payload.get("decisions"), "decisions")
    if payload.get("decision_count") != len(raw_rows):
        raise ValueError("daily decision source decision_count changed")
    parsed: list[ProspectiveMicroDecision] = []
    previous: tuple[int, str, str] | None = None
    seen_ids: set[str] = set()
    activations: set[str] = set()
    for index, raw in enumerate(raw_rows):
        row = _mapping(raw, f"decisions[{index}]")
        if set(row) != _DECISION_FIELDS:
            raise ValueError("daily decision row fields changed")
        activation_id = _identifier(row.get("activation_id"), "activation_id")
        plan_id = _identifier(row.get("plan_id"), "plan_id")
        symbol = _symbol(row.get("symbol"))
        qualified = _integer(
            row.get("candidate_qualified_ts_ns"),
            "candidate_qualified_ts_ns",
            minimum=1,
        )
        decision = _integer(row.get("decision_ts_ns"), "decision_ts_ns", minimum=1)
        if qualified > decision:
            raise ValueError("candidate qualification cannot follow its decision")
        if _local_date(qualified) != trading_date or _local_date(decision) != trading_date:
            raise ValueError("decision timestamps must belong to the registered trading date")
        runtime_hash = _sha256(
            row.get("micro_runtime_content_sha256"),
            "micro_runtime_content_sha256",
        )
        profiles = _profiles(row.get("eligible_strategy_profile_ids"))
        opportunity_id = _identifier(row.get("opportunity_id"), "opportunity_id")
        expected_id = expected_opportunity_id(
            trading_date=trading_date,
            activation_id=activation_id,
            plan_id=plan_id,
            symbol=symbol,
            decision_ts_ns=decision,
            micro_runtime_content_sha256=runtime_hash,
        )
        if opportunity_id != expected_id:
            raise ValueError("daily decision opportunity identity changed")
        order_key = (decision, symbol, opportunity_id)
        if previous is not None and order_key <= previous:
            raise ValueError("daily decisions must be in deterministic chronological order")
        if opportunity_id in seen_ids:
            raise ValueError("daily decision opportunity IDs must be unique")
        previous = order_key
        seen_ids.add(opportunity_id)
        activations.add(activation_id)
        parsed.append(
            ProspectiveMicroDecision(
                opportunity_id=opportunity_id,
                activation_id=activation_id,
                plan_id=plan_id,
                symbol=symbol,
                candidate_qualified_ts_ns=qualified,
                decision_ts_ns=decision,
                micro_runtime_content_sha256=runtime_hash,
                eligible_strategy_profile_ids=profiles,
            )
        )
    if candidate_count < len(activations):
        raise ValueError("candidate_count cannot be smaller than represented activations")
    return tuple(parsed)


def build_opportunity_manifest(
    contract: Mapping[str, object],
    source: Mapping[str, object],
) -> dict[str, object]:
    """Strip the frozen source to the exact market-input opportunity boundary."""
    validate_opportunity_freeze_contract(contract)
    decisions = validate_daily_decision_source(source)
    trading_date = str(source["trading_date"])
    manifest = _freeze(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_id": f"prospective-opportunities-{trading_date}",
            "artifact_type": OPPORTUNITY_ARTIFACT_TYPE,
            "panel_id": PANEL_ID,
            "opportunities": [
                {
                    "opportunity_id": row.opportunity_id,
                    "trading_date": trading_date,
                    "symbol": row.symbol,
                    "decision_ts_ns": row.decision_ts_ns,
                    "runtime_content_sha256": row.micro_runtime_content_sha256,
                }
                for row in decisions
            ],
            "retrospective_labels_loaded": False,
            "later_prices_or_pnl_loaded": False,
        }
    )
    validate_opportunity_manifest(manifest)
    return manifest


def build_daily_opportunity_freeze(
    contract: Mapping[str, object],
    market_input_contract: Mapping[str, object],
    source: Mapping[str, object],
) -> ProspectiveOpportunityFreeze:
    validate_opportunity_freeze_contract(contract)
    validate_capture_contract(market_input_contract)
    decisions = validate_daily_decision_source(source)
    opportunity_manifest = build_opportunity_manifest(contract, source)
    request_manifest = build_request_manifest(
        market_input_contract,
        opportunity_manifest,
    )
    trading_date = str(source["trading_date"])
    freeze_manifest = _freeze(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_id": f"prospective-opportunity-freeze-{trading_date}",
            "artifact_type": FREEZE_ARTIFACT_TYPE,
            "contract_id": CONTRACT_ID,
            "contract_content_sha256": CONTRACT_CONTENT_SHA256,
            "market_input_contract_id": MARKET_INPUT_CONTRACT_ID,
            "market_input_contract_content_sha256": (
                MARKET_INPUT_CONTRACT_CONTENT_SHA256
            ),
            "panel_id": PANEL_ID,
            "trading_date": trading_date,
            "source_content_sha256": source["content_sha256"],
            "opportunity_manifest_content_sha256": (
                opportunity_manifest["content_sha256"]
            ),
            "request_manifest_content_sha256": request_manifest["content_sha256"],
            "candidate_count": source["candidate_count"],
            "opportunity_count": len(decisions),
            "request_count": request_manifest["request_count"],
            "zero_opportunity_date_retained": len(decisions) == 0,
            "profile_union_preserved_before_account_scarcity": True,
            "provider_metadata_quote_made": False,
            "provider_timeseries_request_made": False,
            "provider_purchase_authorized": False,
            "databento_credit_authorized_usd": "0",
            "broker_order_submitted": False,
            "retrospective_labels_loaded": False,
            "later_prices_or_pnl_loaded": False,
            "runtime_authority": "none_unarmed",
        }
    )
    validate_freeze_manifest(
        freeze_manifest,
        contract=contract,
        market_input_contract=market_input_contract,
        source=source,
        opportunity_manifest=opportunity_manifest,
        request_manifest=request_manifest,
    )
    return ProspectiveOpportunityFreeze(
        opportunity_manifest=opportunity_manifest,
        request_manifest=request_manifest,
        freeze_manifest=freeze_manifest,
    )


def validate_freeze_manifest(
    payload: Mapping[str, object],
    *,
    contract: Mapping[str, object],
    market_input_contract: Mapping[str, object],
    source: Mapping[str, object],
    opportunity_manifest: Mapping[str, object],
    request_manifest: Mapping[str, object],
) -> None:
    expected_fields = {
        "schema_version",
        "artifact_id",
        "artifact_type",
        "contract_id",
        "contract_content_sha256",
        "market_input_contract_id",
        "market_input_contract_content_sha256",
        "panel_id",
        "trading_date",
        "source_content_sha256",
        "opportunity_manifest_content_sha256",
        "request_manifest_content_sha256",
        "candidate_count",
        "opportunity_count",
        "request_count",
        "zero_opportunity_date_retained",
        "profile_union_preserved_before_account_scarcity",
        "provider_metadata_quote_made",
        "provider_timeseries_request_made",
        "provider_purchase_authorized",
        "databento_credit_authorized_usd",
        "broker_order_submitted",
        "retrospective_labels_loaded",
        "later_prices_or_pnl_loaded",
        "runtime_authority",
        "content_sha256",
    }
    if set(payload) != expected_fields:
        raise ValueError("opportunity freeze manifest fields changed")
    validate_opportunity_freeze_contract(contract)
    validate_capture_contract(market_input_contract)
    decisions = validate_daily_decision_source(source)
    expected_opportunity_manifest = build_opportunity_manifest(contract, source)
    if dict(opportunity_manifest) != expected_opportunity_manifest:
        raise ValueError("opportunity manifest differs from frozen source decisions")
    opportunities = validate_opportunity_manifest(opportunity_manifest)
    expected_request_manifest = build_request_manifest(
        market_input_contract,
        opportunity_manifest,
    )
    if dict(request_manifest) != expected_request_manifest:
        raise ValueError("request manifest differs from deterministic derivation")
    trading_date = str(source["trading_date"])
    expected = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": f"prospective-opportunity-freeze-{trading_date}",
        "artifact_type": FREEZE_ARTIFACT_TYPE,
        "contract_id": CONTRACT_ID,
        "contract_content_sha256": CONTRACT_CONTENT_SHA256,
        "market_input_contract_id": MARKET_INPUT_CONTRACT_ID,
        "market_input_contract_content_sha256": MARKET_INPUT_CONTRACT_CONTENT_SHA256,
        "panel_id": PANEL_ID,
        "trading_date": trading_date,
        "source_content_sha256": source["content_sha256"],
        "opportunity_manifest_content_sha256": opportunity_manifest["content_sha256"],
        "request_manifest_content_sha256": request_manifest["content_sha256"],
        "candidate_count": source["candidate_count"],
        "opportunity_count": len(decisions),
        "request_count": request_manifest.get("request_count"),
        "zero_opportunity_date_retained": len(decisions) == 0,
        "profile_union_preserved_before_account_scarcity": True,
        "provider_metadata_quote_made": False,
        "provider_timeseries_request_made": False,
        "provider_purchase_authorized": False,
        "databento_credit_authorized_usd": "0",
        "broker_order_submitted": False,
        "retrospective_labels_loaded": False,
        "later_prices_or_pnl_loaded": False,
        "runtime_authority": "none_unarmed",
    }
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if unsigned != expected:
        raise ValueError("opportunity freeze manifest binding changed")
    if len(opportunities) != len(decisions):
        raise ValueError("opportunity freeze manifest dropped a source decision")
    if request_manifest.get("opportunity_manifest_content_sha256") != (
        opportunity_manifest["content_sha256"]
    ):
        raise ValueError("request manifest does not bind the opportunity manifest")
    _fingerprinted(payload, "opportunity freeze manifest")


def write_daily_opportunity_freeze(
    output_dir: str | Path,
    result: ProspectiveOpportunityFreeze,
) -> None:
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("opportunity freeze output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "opportunity-manifest.json": result.opportunity_manifest,
        "request-manifest.json": result.request_manifest,
        "freeze-manifest.json": result.freeze_manifest,
    }
    for name, payload in files.items():
        (output / name).write_text(
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )


def load_daily_decision_source(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("daily decision source root must be an object")
    validate_daily_decision_source(payload)
    return payload
