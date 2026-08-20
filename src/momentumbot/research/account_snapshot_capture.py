"""Causal, secret-safe capture of the registered paper-account inputs.

This module reads two separately credentialed Alpaca paper accounts, retains
only the account fields needed by the frozen chronological-integration
contract, pseudonymizes the provider account identifier, and binds every
stored record with canonical SHA-256 fingerprints.  It never submits an order
and cannot create a snapshot after the registered 7:00 a.m. New York cutoff.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.parse
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from momentumbot.providers.http_json import get_json
from momentumbot.research.account_chronological_integration import (
    PANEL_ID,
    REGISTERED_DATES,
    AccountSessionSnapshot,
)
from momentumbot.research.campaign_portfolio import AccountClass

SCHEMA_VERSION = 1
CONTRACT_ID = "account-session-snapshot-capture-v0.1"
CONTRACT_CONTENT_SHA256 = (
    "5e967dbbbe2ee53187940f2ea720bd1937a4391710c97043ec03cc80c9b257b7"
)
INTEGRATION_CONTRACT_SHA256 = (
    "64489aa27fec5eaf8ca12c94f4aeb47344d49a79b14df1bdda706cd23cc9ce73"
)
PAPER_ENDPOINT = "https://paper-api.alpaca.markets"
ACCOUNT_CLASSES = ("main", "small")
EXPECTED_EQUITY = {
    "main": Decimal(30000),
    "small": Decimal(2000),
}
STRATEGY_START_ET = time(7, 0)
SCHEDULED_CAPTURE_ET = time(5, 15)
NEW_YORK = ZoneInfo("America/New_York")

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_HEAD_SHA = re.compile(r"^[0-9a-f]{40}$")


def canonical_fingerprint(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_capture_contract(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported account capture contract schema")
    if payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("unexpected account capture contract ID")
    if payload.get("artifact_type") != "paper_account_pre_session_capture_contract":
        raise ValueError("unexpected account capture artifact type")
    if payload.get("status") != "preregistered_unrun":
        raise ValueError("account capture contract must remain unrun")
    if payload.get("portfolio_backtest_eligible") is not False:
        raise ValueError("account capture contract is not backtest eligible")
    if payload.get("policy_promotion_eligible") is not False:
        raise ValueError("account capture contract is not promotion eligible")

    parent = payload.get("frozen_parent")
    if not isinstance(parent, Mapping):
        raise TypeError("frozen_parent must be an object")
    if parent.get("integration_contract_content_sha256") != INTEGRATION_CONTRACT_SHA256:
        raise ValueError("account capture parent integration hash changed")
    if parent.get("panel_id") != PANEL_ID:
        raise ValueError("account capture panel changed")

    accounts = payload.get("registered_account_setup")
    if not isinstance(accounts, list) or len(accounts) != 2:
        raise ValueError("registered account setup must contain main and small")
    expected_accounts = {
        "main": {
            "provider": "alpaca_paper",
            "expected_initial_equity": "30000",
            "api_key_secret": "ALPACA_MAIN_API_KEY",
            "api_secret_secret": "ALPACA_MAIN_API_SECRET",
        },
        "small": {
            "provider": "alpaca_paper",
            "expected_initial_equity": "2000",
            "api_key_secret": "ALPACA_SMALL_API_KEY",
            "api_secret_secret": "ALPACA_SMALL_API_SECRET",
        },
    }
    seen: set[str] = set()
    for row in accounts:
        if not isinstance(row, Mapping):
            raise TypeError("registered account rows must be objects")
        account_class = str(row.get("account_class", ""))
        if account_class in seen or account_class not in expected_accounts:
            raise ValueError("registered account classes must be unique main and small")
        seen.add(account_class)
        for field, expected in expected_accounts[account_class].items():
            if row.get(field) != expected:
                raise ValueError(f"{account_class}.{field} changed")
    if seen != set(ACCOUNT_CLASSES):
        raise ValueError("registered account classes differ from capture policy")

    provider = payload.get("provider_contract")
    if not isinstance(provider, Mapping):
        raise TypeError("provider_contract must be an object")
    expected_provider = {
        "endpoint": PAPER_ENDPOINT,
        "write_endpoints_allowed": False,
        "broker_orders_submitted": False,
        "main_and_small_credentials_must_resolve_to_distinct_accounts": True,
        "account_status_required": "ACTIVE",
        "currency_required": "USD",
        "blocked_flags_required": False,
        "open_positions_required": 0,
        "open_orders_required": 0,
        "equity_tolerance_dollars": "0.01",
        "positive_buying_power_required": True,
    }
    for field, expected in expected_provider.items():
        if provider.get(field) != expected:
            raise ValueError(f"provider_contract.{field} changed")

    schedule = payload.get("capture_schedule")
    if not isinstance(schedule, Mapping):
        raise TypeError("capture_schedule must be an object")
    expected_schedule = {
        "registered_dates": list(REGISTERED_DATES),
        "timezone": "America/New_York",
        "scheduled_capture_time": SCHEDULED_CAPTURE_ET.isoformat(),
        "strategy_start_deadline": STRATEGY_START_ET.isoformat(),
        "scheduled_cron_utc": [
            "15 9 24-28,31 8 *",
            "15 9 1-4 9 *",
        ],
        "manual_capture_fallback": True,
        "manual_capture_must_equal_current_new_york_date": True,
        "capture_start_and_completion_must_precede_deadline": True,
        "missing_or_late_capture_behavior": "fail_closed_no_account_runtime",
        "dates_may_be_replaced": False,
    }
    for field, expected in expected_schedule.items():
        if schedule.get(field) != expected:
            raise ValueError(f"capture_schedule.{field} changed")

    source = payload.get("source_projection")
    if not isinstance(source, Mapping):
        raise TypeError("source_projection must be an object")
    source_guards = {
        "raw_provider_account_id_stored": False,
        "account_number_stored": False,
        "api_credentials_stored": False,
        "nonrequired_provider_fields_stored": False,
        "source_projection_is_hash_bound": True,
        "snapshot_is_hash_bound": True,
        "bundle_manifest_is_hash_bound": True,
    }
    for field, expected in source_guards.items():
        if source.get(field) is not expected:
            raise ValueError(f"source_projection.{field} changed")

    workflow = payload.get("workflow_contract")
    if not isinstance(workflow, Mapping):
        raise TypeError("workflow_contract must be an object")
    workflow_guards = {
        "workflow": ".github/workflows/account-session-snapshot.yml",
        "push_behavior": "validation_only_not_session_eligible",
        "scheduled_behavior": "capture_only_on_exact_registered_2026_date",
        "default_branch_scheduler_checks_out": "phase-3-historical-snapshot",
        "scheduler_and_runtime_head_shas_recorded_separately": True,
        "workflow_dispatch_modes": ["validate", "capture"],
        "validation_artifact_is_session_eligible": False,
        "capture_artifact_retention_days": 90,
        "repository_permission": "contents_read_only",
        "credentials_scoped_to_capture_step_only": True,
    }
    for field, expected in workflow_guards.items():
        if workflow.get(field) != expected:
            raise ValueError(f"workflow_contract.{field} changed")

    knowledge = payload.get("knowledge_policy")
    if not isinstance(knowledge, Mapping):
        raise TypeError("knowledge_policy must be an object")
    knowledge_guards = {
        "runtime_inputs_available_by_capture_time": True,
        "raw_transcripts_allowed": False,
        "retrospective_actions_or_labels_allowed": False,
        "later_prices_or_outcomes_allowed": False,
        "semantic_ai_used": False,
        "scanner_or_micro_policy_changed": False,
        "risk_policy_changed": False,
    }
    for field, expected in knowledge_guards.items():
        if knowledge.get(field) is not expected:
            raise ValueError(f"knowledge_policy.{field} changed")


def load_capture_contract(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("account capture contract must be an object")
    validate_capture_contract(payload)
    if canonical_fingerprint(payload) != CONTRACT_CONTENT_SHA256:
        raise ValueError("account capture contract content hash changed")
    return payload


def _aware_utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _iso_utc(value: datetime) -> str:
    return _aware_utc(value, "timestamp").isoformat().replace("+00:00", "Z")


def _decimal(value: object, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a finite decimal") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"{field} must be finite and positive")
    return parsed


def _decimal_text(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _required_text(payload: Mapping[str, object], field: str) -> str:
    value = str(payload.get(field, "")).strip()
    if not value:
        raise ValueError(f"Alpaca account response is missing {field}")
    return value


def _required_bool(payload: Mapping[str, object], field: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise TypeError(f"Alpaca account response has invalid {field}")
    return value


def _pseudonymous_account_id(provider_account_id: str) -> str:
    digest = hashlib.sha256(provider_account_id.encode("utf-8")).hexdigest()
    return f"alpaca-paper-sha256:{digest}"


def _deadline(session_date: date) -> datetime:
    return datetime.combine(session_date, STRATEGY_START_ET, NEW_YORK)


@dataclass(frozen=True, slots=True)
class AccountCredentials:
    account_class: str
    api_key: str
    api_secret: str
    expected_equity: Decimal

    def __post_init__(self) -> None:
        if self.account_class not in ACCOUNT_CLASSES:
            raise ValueError("account_class must be main or small")
        if not self.api_key or not self.api_secret:
            raise ValueError(f"missing {self.account_class} Alpaca credentials")
        if self.expected_equity != EXPECTED_EQUITY[self.account_class]:
            raise ValueError(
                "expected equity differs from the registered account setup"
            )


class AlpacaPaperAccountClient:
    """Minimal read-only Alpaca trading client for account-state capture."""

    def __init__(
        self,
        credentials: AccountCredentials,
        *,
        endpoint: str = PAPER_ENDPOINT,
        request_json: Callable[..., object] = get_json,
    ) -> None:
        parsed = urllib.parse.urlparse(endpoint.rstrip("/"))
        if (
            parsed.scheme != "https"
            or parsed.hostname != "paper-api.alpaca.markets"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "account capture requires the official Alpaca paper endpoint"
            )
        self.credentials = credentials
        self.endpoint = endpoint.rstrip("/")
        self._request_json = request_json

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.credentials.api_key,
            "APCA-API-SECRET-KEY": self.credentials.api_secret,
            "Accept-Encoding": "gzip",
            "User-Agent": "MomentumBot/0.3 account-snapshot-capture",
        }

    def _get(self, path: str) -> object:
        try:
            return self._request_json(
                f"{self.endpoint}{path}",
                headers=self._headers,
                timeout_seconds=25,
                max_retries=2,
            )
        except Exception as exc:
            # Never include provider bodies, URLs, headers, or credentials in
            # the error that GitHub Actions will print.
            raise RuntimeError(
                f"Alpaca {self.credentials.account_class} account request failed "
                f"for {path.split('?')[0]} ({type(exc).__name__})"
            ) from exc

    def account(self) -> Mapping[str, object]:
        payload = self._get("/v2/account")
        if not isinstance(payload, Mapping):
            raise TypeError("Alpaca account response must be an object")
        return payload

    def positions(self) -> list[object]:
        payload = self._get("/v2/positions")
        if not isinstance(payload, list):
            raise TypeError("Alpaca positions response must be a list")
        return payload

    def open_orders(self) -> list[object]:
        payload = self._get("/v2/orders?status=open&limit=500&direction=desc")
        if not isinstance(payload, list):
            raise TypeError("Alpaca open-orders response must be a list")
        return payload


def credentials_from_env(account_class: str) -> AccountCredentials:
    if account_class not in ACCOUNT_CLASSES:
        raise ValueError("account_class must be main or small")
    prefix = f"ALPACA_{account_class.upper()}"
    return AccountCredentials(
        account_class=account_class,
        api_key=os.environ[f"{prefix}_API_KEY"],
        api_secret=os.environ[f"{prefix}_API_SECRET"],
        expected_equity=EXPECTED_EQUITY[account_class],
    )


def _capture_observation(
    client: AlpacaPaperAccountClient,
    *,
    clock: Callable[[], datetime],
) -> dict[str, object]:
    started_at = _aware_utc(clock(), "capture_started_at")
    account = client.account()
    positions = client.positions()
    open_orders = client.open_orders()
    captured_at = _aware_utc(clock(), "captured_at")
    if captured_at < started_at:
        raise ValueError("capture clock moved backwards")

    account_class = client.credentials.account_class
    provider_account_id = _required_text(account, "id")
    status = _required_text(account, "status").upper()
    currency = _required_text(account, "currency").upper()
    equity = _decimal(account.get("equity"), "equity")
    buying_power = _decimal(account.get("buying_power"), "buying_power")
    cash = _decimal(account.get("cash"), "cash")
    account_blocked = _required_bool(account, "account_blocked")
    trading_blocked = _required_bool(account, "trading_blocked")
    transfers_blocked = _required_bool(account, "transfers_blocked")

    if status != "ACTIVE":
        raise ValueError(f"{account_class} paper account is not ACTIVE")
    if currency != "USD":
        raise ValueError(f"{account_class} paper account is not USD")
    if account_blocked or trading_blocked or transfers_blocked:
        raise ValueError(f"{account_class} paper account is blocked")
    if positions:
        raise ValueError(f"{account_class} paper account has open positions")
    if open_orders:
        raise ValueError(f"{account_class} paper account has open orders")
    if abs(equity - client.credentials.expected_equity) > Decimal("0.01"):
        raise ValueError(
            f"{account_class} equity differs from the registered "
            f"{_decimal_text(client.credentials.expected_equity)} fixture"
        )

    source = {
        "schema_version": SCHEMA_VERSION,
        "source_type": "alpaca_paper_account_pre_session_projection",
        "account_class": account_class,
        "account_id": _pseudonymous_account_id(provider_account_id),
        "capture_started_at": _iso_utc(started_at),
        "captured_at": _iso_utc(captured_at),
        "status": status,
        "currency": currency,
        "equity": _decimal_text(equity),
        "buying_power": _decimal_text(buying_power),
        "cash": _decimal_text(cash),
        "account_blocked": account_blocked,
        "trading_blocked": trading_blocked,
        "transfers_blocked": transfers_blocked,
        "open_position_count": len(positions),
        "open_order_count": len(open_orders),
        "provider_fields_retained": [
            "id_as_sha256_pseudonym",
            "status",
            "currency",
            "equity",
            "buying_power",
            "cash",
            "account_blocked",
            "trading_blocked",
            "transfers_blocked",
        ],
        "provider_fields_omitted": "all_nonrequired_fields",
    }
    return {
        "source": source,
        "source_content_sha256": canonical_fingerprint(source),
    }


def _snapshot_from_observation(
    observation: Mapping[str, object],
    *,
    session_date: date,
) -> dict[str, object]:
    source = observation.get("source")
    if not isinstance(source, Mapping):
        raise TypeError("observation source must be an object")
    captured_at = datetime.fromisoformat(str(source["captured_at"]))
    deadline = _deadline(session_date)
    if captured_at.astimezone(NEW_YORK).date() != session_date:
        raise ValueError("account capture does not belong to the requested session")
    if captured_at > deadline:
        raise ValueError(
            "account capture completed after the 7:00 a.m. New York cutoff"
        )

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "account_session_snapshot",
        "contract_id": CONTRACT_ID,
        "parent_integration_contract_content_sha256": INTEGRATION_CONTRACT_SHA256,
        "panel_id": PANEL_ID,
        "account_id": source["account_id"],
        "account_class": source["account_class"],
        "session_date": session_date.isoformat(),
        "captured_at": source["captured_at"],
        "strategy_start_at": deadline.isoformat(),
        "starting_equity": source["equity"],
        "starting_buying_power": source["buying_power"],
        "source_id": f"alpaca-paper-api-v2:{source['account_id']}",
        "source_content_sha256": observation["source_content_sha256"],
        "source_record": dict(source),
        "causal_boundary": {
            "captured_by_strategy_start": True,
            "raw_provider_account_id_stored": False,
            "api_credentials_stored": False,
            "positions_open_at_capture": False,
            "orders_open_at_capture": False,
            "broker_orders_submitted": False,
            "uses_transcripts_or_recap_labels": False,
            "uses_later_prices_or_outcomes": False,
            "runtime_strategy_effect": "account_input_only",
        },
        "portfolio_backtest_eligible": False,
        "policy_promotion_eligible": False,
    }
    snapshot["content_sha256"] = canonical_fingerprint(snapshot)
    return snapshot


def _run_context(values: Mapping[str, str] | None) -> dict[str, object]:
    source = dict(values or {})
    head_sha = str(source.get("head_sha", "")).strip().lower()
    if head_sha and not _HEAD_SHA.fullmatch(head_sha):
        raise ValueError("head_sha must be a 40-character lowercase Git SHA")
    workflow_source_sha = str(source.get("workflow_source_sha", "")).strip().lower()
    if workflow_source_sha and not _HEAD_SHA.fullmatch(workflow_source_sha):
        raise ValueError("workflow_source_sha must be a 40-character lowercase Git SHA")
    result: dict[str, object] = {
        "workflow_run_id": str(source.get("workflow_run_id", "local")).strip()
        or "local",
        "workflow_run_attempt": str(source.get("workflow_run_attempt", "1")).strip()
        or "1",
        "workflow_event_name": str(source.get("workflow_event_name", "local")).strip()
        or "local",
        "runtime_head_sha": head_sha or None,
        "workflow_source_sha": workflow_source_sha or None,
    }
    return result


def capture_dual_account_bundle(
    clients: Mapping[str, AlpacaPaperAccountClient],
    *,
    mode: str,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    requested_session_date: date | None = None,
    run_context: Mapping[str, str] | None = None,
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    """Capture both account sources atomically into validation or session output."""

    if mode not in {"validate", "capture"}:
        raise ValueError("mode must be validate or capture")
    if tuple(sorted(clients)) != ACCOUNT_CLASSES:
        raise ValueError("exactly one main and one small client are required")

    bundle_started_at = _aware_utc(clock(), "bundle_started_at")
    effective_session_date: date | None = None
    if mode == "capture":
        effective_session_date = (
            requested_session_date or bundle_started_at.astimezone(NEW_YORK).date()
        )
        if effective_session_date.isoformat() not in REGISTERED_DATES:
            raise ValueError("session date is not in the registered account panel")
        if bundle_started_at.astimezone(NEW_YORK).date() != effective_session_date:
            raise ValueError("capture must run on the requested New York session date")
        if bundle_started_at > _deadline(effective_session_date):
            raise ValueError("capture started after the 7:00 a.m. New York cutoff")
    elif requested_session_date is not None:
        raise ValueError("validation mode cannot claim a registered session date")

    observations = {
        account_class: _capture_observation(clients[account_class], clock=clock)
        for account_class in ACCOUNT_CLASSES
    }
    account_ids = {
        str(observations[name]["source"]["account_id"]) for name in ACCOUNT_CLASSES
    }
    if len(account_ids) != 2:
        raise ValueError("main and small credentials resolve to the same paper account")

    bundle_completed_at = _aware_utc(clock(), "bundle_completed_at")
    if bundle_completed_at < bundle_started_at:
        raise ValueError("capture clock moved backwards")
    if effective_session_date is not None and bundle_completed_at > _deadline(
        effective_session_date
    ):
        raise ValueError("dual-account capture completed after the 7:00 a.m. cutoff")

    snapshots: dict[str, dict[str, object]] = {}
    if effective_session_date is not None:
        snapshots = {
            name: _snapshot_from_observation(
                observations[name], session_date=effective_session_date
            )
            for name in ACCOUNT_CLASSES
        }

    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": (
            "dual_account_pre_session_snapshot_bundle"
            if mode == "capture"
            else "dual_account_credential_validation"
        ),
        "contract_id": CONTRACT_ID,
        "parent_integration_contract_content_sha256": INTEGRATION_CONTRACT_SHA256,
        "panel_id": PANEL_ID,
        "mode": mode,
        "session_date": effective_session_date.isoformat()
        if effective_session_date is not None
        else None,
        "bundle_started_at": _iso_utc(bundle_started_at),
        "bundle_completed_at": _iso_utc(bundle_completed_at),
        "scheduled_capture_time_new_york": SCHEDULED_CAPTURE_ET.isoformat(),
        "strategy_start_time_new_york": STRATEGY_START_ET.isoformat(),
        "account_classes": list(ACCOUNT_CLASSES),
        "expected_equity": {
            name: _decimal_text(EXPECTED_EQUITY[name]) for name in ACCOUNT_CLASSES
        },
        "accounts_are_distinct": True,
        "account_source_content_sha256": {
            name: observations[name]["source_content_sha256"]
            for name in ACCOUNT_CLASSES
        },
        "account_source_records": {
            name: observations[name]["source"] for name in ACCOUNT_CLASSES
        }
        if mode == "validate"
        else None,
        "account_snapshot_content_sha256": {
            name: snapshots[name]["content_sha256"] for name in ACCOUNT_CLASSES
        }
        if snapshots
        else None,
        "run_context": _run_context(run_context),
        "causal_boundary": {
            "registered_session_input": mode == "capture",
            "captured_by_strategy_start": mode == "capture",
            "raw_provider_account_ids_stored": False,
            "api_credentials_stored": False,
            "both_accounts_clean": True,
            "broker_orders_submitted": False,
            "uses_transcripts_or_recap_labels": False,
            "uses_later_prices_or_outcomes": False,
            "runtime_strategy_effect": "account_input_only"
            if mode == "capture"
            else "none_validation_only",
        },
        "portfolio_backtest_eligible": False,
        "policy_promotion_eligible": False,
    }
    manifest["content_sha256"] = canonical_fingerprint(manifest)
    return manifest, snapshots


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def write_bundle(
    output_dir: Path,
    manifest: Mapping[str, object],
    snapshots: Mapping[str, Mapping[str, object]],
) -> tuple[Path, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for account_class in ACCOUNT_CLASSES:
        snapshot = snapshots.get(account_class)
        if snapshot is not None:
            path = output_dir / f"{account_class}.json"
            _write_json(path, snapshot)
            written.append(path)
    manifest_path = output_dir / "manifest.json"
    _write_json(manifest_path, manifest)
    written.append(manifest_path)
    return tuple(written)


def validate_snapshot_artifact(payload: Mapping[str, object]) -> AccountSessionSnapshot:
    claimed = str(payload.get("content_sha256", ""))
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if not _SHA256.fullmatch(claimed) or canonical_fingerprint(unsigned) != claimed:
        raise ValueError("account snapshot content hash mismatch")
    source = payload.get("source_record")
    if not isinstance(source, Mapping):
        raise TypeError("account snapshot source_record must be an object")
    source_claimed = str(payload.get("source_content_sha256", ""))
    if (
        not _SHA256.fullmatch(source_claimed)
        or canonical_fingerprint(source) != source_claimed
    ):
        raise ValueError("account snapshot source hash mismatch")
    boundary = payload.get("causal_boundary")
    if not isinstance(boundary, Mapping):
        raise TypeError("account snapshot causal_boundary must be an object")
    required = {
        "captured_by_strategy_start": True,
        "raw_provider_account_id_stored": False,
        "api_credentials_stored": False,
        "positions_open_at_capture": False,
        "orders_open_at_capture": False,
        "broker_orders_submitted": False,
        "uses_transcripts_or_recap_labels": False,
        "uses_later_prices_or_outcomes": False,
        "runtime_strategy_effect": "account_input_only",
    }
    for field, expected in required.items():
        if boundary.get(field) != expected:
            raise ValueError(f"account snapshot violates {field}")
    account_class = AccountClass(str(payload["account_class"]))
    snapshot = AccountSessionSnapshot(
        account_id=str(payload["account_id"]),
        account_class=account_class,
        session_date=date.fromisoformat(str(payload["session_date"])),
        captured_at=datetime.fromisoformat(str(payload["captured_at"])),
        starting_equity=float(_decimal(payload["starting_equity"], "starting_equity")),
        starting_buying_power=float(
            _decimal(payload["starting_buying_power"], "starting_buying_power")
        ),
        source_id=str(payload["source_id"]),
        source_content_sha256=source_claimed,
    )
    return snapshot


def validate_bundle(
    manifest: Mapping[str, object],
    snapshots: Mapping[str, Mapping[str, object]],
) -> None:
    claimed = str(manifest.get("content_sha256", ""))
    unsigned = {
        key: value for key, value in manifest.items() if key != "content_sha256"
    }
    if not _SHA256.fullmatch(claimed) or canonical_fingerprint(unsigned) != claimed:
        raise ValueError("account bundle content hash mismatch")
    if manifest.get("account_classes") != list(ACCOUNT_CLASSES):
        raise ValueError("account bundle classes differ from the capture contract")
    source_hashes = manifest.get("account_source_content_sha256")
    if not isinstance(source_hashes, Mapping):
        raise TypeError("account bundle source hashes must be an object")
    source_records = manifest.get("account_source_records")
    expected_hashes = manifest.get("account_snapshot_content_sha256")
    if snapshots:
        if source_records is not None:
            raise ValueError(
                "capture bundle duplicates source records outside snapshots"
            )
        if not isinstance(expected_hashes, Mapping):
            raise ValueError("capture bundle is missing snapshot hashes")
        for account_class in ACCOUNT_CLASSES:
            snapshot = validate_snapshot_artifact(snapshots[account_class])
            if snapshot.account_class.value != account_class:
                raise ValueError("snapshot account class mismatch")
            if source_hashes.get(account_class) != snapshots[account_class].get(
                "source_content_sha256"
            ):
                raise ValueError("manifest source hash mismatch")
            if expected_hashes.get(account_class) != snapshots[account_class].get(
                "content_sha256"
            ):
                raise ValueError("manifest snapshot hash mismatch")
    else:
        if expected_hashes is not None:
            raise ValueError("validation bundle cannot claim session snapshot hashes")
        if not isinstance(source_records, Mapping):
            raise TypeError("validation bundle must retain sanitized source records")
        account_ids: set[str] = set()
        for account_class in ACCOUNT_CLASSES:
            source = source_records.get(account_class)
            if not isinstance(source, Mapping):
                raise TypeError("validation source records must be objects")
            if source.get("account_class") != account_class:
                raise ValueError("validation source account class mismatch")
            if canonical_fingerprint(source) != source_hashes.get(account_class):
                raise ValueError("validation source hash mismatch")
            if source.get("equity") != _decimal_text(EXPECTED_EQUITY[account_class]):
                raise ValueError("validation source equity differs from fixture")
            if (
                source.get("open_position_count") != 0
                or source.get("open_order_count") != 0
            ):
                raise ValueError("validation source is not clean")
            account_ids.add(str(source.get("account_id", "")))
        if len(account_ids) != 2 or "" in account_ids:
            raise ValueError("validation source accounts are not distinct")
