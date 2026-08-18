from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from momentumbot.identity_resolved_universe import json_fingerprint
from momentumbot.research.context_heldout_panel import (
    CONTRACT_ID as PANEL_CONTRACT_ID,
    REGISTERED_DATES,
)


SCHEMA_VERSION = 1
MARKET_RUNTIME_ARTIFACT_ID = "ross-context-heldout-market-runtime-v0.1"
DAILY_RUNTIME_ARTIFACT_ID = "ross-context-heldout-daily-chart-runtime-v0.1"
THEME_RUNTIME_ARTIFACT_ID = "ross-context-heldout-theme-regime-runtime-v0.1"
SNAPSHOT_RUNTIME_ARTIFACT_ID = "ross-context-heldout-snapshot-runtime-v0.1"
RUNTIME_REQUEST_ID = "ross-context-heldout-runtime-request-v0.1"
RUNTIME_REQUEST_CONTENT_SHA256 = (
    "9459660565c6c76c4af2fd09fd8362789bfda89fe57601d0f016b189112bbff0"
)
RUNTIME_ARTIFACT_ID = "ross-context-heldout-runtime-v0.1"
RUNTIME_ARTIFACT_NAME = "context-heldout-runtime-v0.1"
RUNTIME_WORKFLOW_PATH = ".github/workflows/context-heldout-runtime.yml"
PRIOR_RUNTIME_CONTENT_SHA256 = (
    "2414f7389bf68d5a5e4b3302c646c9111020cb79ce06fc0213f7872062f79c48"
)
FROZEN_CONTRACT_CONTENT_SHA256S = {
    "context_panel_content_sha256": (
        "d227792368b3bff5c3c2365cacd204c11b7991daeb557efba450c22f076d8898"
    ),
    "context_assessment_content_sha256": (
        "8205772680ce290d58de1d17fbe43d02c2beb21fd9f0e16d8bd2c7b3a1806f26"
    ),
    "daily_chart_content_sha256": (
        "55262a3c6537d1511248577c0e01f0a36775ed98bff9d6839b12e00da3f2fa87"
    ),
    "theme_regime_content_sha256": (
        "e240babc3004c33f2a9fd16ed80f3be24d8a332c48eb603ebfe57a9c795a92e0"
    ),
}

_LOWER_HEX = frozenset("0123456789abcdef")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _LOWER_HEX for character in value)
    )


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate_context_runtime_request(payload: Mapping[str, object]) -> list[str]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported context runtime request schema")
    if payload.get("request_id") != RUNTIME_REQUEST_ID:
        raise ValueError("unexpected context runtime request ID")
    claimed = payload.get("content_sha256")
    projection = {
        key: value for key, value in payload.items() if key != "content_sha256"
    }
    if claimed != json_fingerprint(projection):
        raise ValueError("context runtime request fingerprint mismatch")
    if claimed != RUNTIME_REQUEST_CONTENT_SHA256:
        raise ValueError("context runtime request differs from the frozen request")
    if payload.get("status") != "registered_unexecuted":
        raise ValueError("context runtime request status changed")
    if payload.get("branch") != "phase-3-historical-snapshot":
        raise ValueError("context runtime request branch changed")
    if payload.get("workflow_path") != RUNTIME_WORKFLOW_PATH:
        raise ValueError("context runtime request workflow changed")
    if payload.get("expected_artifact_name") != RUNTIME_ARTIFACT_NAME:
        raise ValueError("context runtime request artifact changed")
    dates = payload.get("registered_dates")
    if dates != list(REGISTERED_DATES):
        raise ValueError("context runtime request dates changed")
    if payload.get("frozen_contracts") != FROZEN_CONTRACT_CONTENT_SHA256S:
        raise ValueError("context runtime request contract hashes changed")
    prior = payload.get("prior_completed_session_source")
    if not isinstance(prior, Mapping):
        raise ValueError("context runtime request lacks prior-session source")
    if prior.get("manifest_content_sha256") != PRIOR_RUNTIME_CONTENT_SHA256:
        raise ValueError("context runtime request prior artifact changed")
    causal = payload.get("causal_boundary")
    if not isinstance(causal, Mapping):
        raise ValueError("context runtime request lacks causal boundary")
    for field in (
        "uses_raw_transcripts",
        "uses_recap_inventory",
        "uses_ross_actions",
        "uses_retrospective_labels",
        "uses_later_price_outcomes",
        "top_n_selection_applied",
        "semantic_ai_included",
    ):
        if causal.get(field) is not False:
            raise ValueError(f"context runtime request violates {field}")
    if causal.get("all_market_candidates_retained") is not True:
        raise ValueError("context runtime request does not retain all candidates")
    if causal.get("runtime_strategy_effect") != "none":
        raise ValueError("context runtime request has strategy authority")
    eligibility = payload.get("eligibility")
    if not isinstance(eligibility, Mapping):
        raise ValueError("context runtime request lacks eligibility")
    for field in (
        "policy_promotion_eligible",
        "representative_panel",
        "portfolio_backtest",
        "human_evidence_review_allowed_before_successful_artifact_freeze",
    ):
        if eligibility.get(field) is not False:
            raise ValueError(f"context runtime request overclaims {field}")
    return list(dates)


def load_context_runtime_request(path: str | Path) -> dict[str, object]:
    payload = _read_json(Path(path))
    validate_context_runtime_request(payload)
    return payload


def validate_market_runtime_manifest(payload: Mapping[str, object]) -> list[str]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported context market runtime schema")
    if payload.get("artifact_id") != MARKET_RUNTIME_ARTIFACT_ID:
        raise ValueError("unexpected context market runtime artifact")
    claimed = payload.get("content_sha256")
    projection = {
        key: value for key, value in payload.items() if key != "content_sha256"
    }
    if claimed != json_fingerprint(projection):
        raise ValueError("context market runtime fingerprint mismatch")
    dates = payload.get("dates")
    if dates != list(REGISTERED_DATES):
        raise ValueError("context market runtime dates differ from registration")
    registration = payload.get("registration")
    if not isinstance(registration, Mapping):
        raise ValueError("context market runtime lacks registration")
    if registration.get("contract_id") != PANEL_CONTRACT_ID:
        raise ValueError("context market runtime registration ID mismatch")
    if registration.get("request_id") != RUNTIME_REQUEST_ID:
        raise ValueError("context market runtime request ID mismatch")
    if registration.get("request_content_sha256") != (
        RUNTIME_REQUEST_CONTENT_SHA256
    ):
        raise ValueError("context market runtime request hash changed")
    if registration.get("label_content_review_started") is not False:
        raise ValueError("context labels were opened before market runtime freeze")
    causal = payload.get("causal_boundary")
    if not isinstance(causal, Mapping):
        raise ValueError("context market runtime lacks causal boundary")
    for field in (
        "uses_benchmark_labels",
        "uses_ross_actions",
        "uses_retrospective_trade_outcomes",
        "uses_later_price_outcomes",
        "top_n_selection_applied",
    ):
        if causal.get(field) is not False:
            raise ValueError(f"context market runtime violates {field}")
    for field in (
        "all_market_candidates_retained",
        "provider_independent_scanner_replay_validated",
    ):
        if causal.get(field) is not True:
            raise ValueError(f"context market runtime lacks {field}")
    eligibility = payload.get("eligibility")
    if not isinstance(eligibility, Mapping):
        raise ValueError("context market runtime lacks eligibility")
    if eligibility.get("runtime_inputs_frozen") is not True:
        raise ValueError("context market runtime inputs are not frozen")
    if eligibility.get("policy_promotion_eligible") is not False:
        raise ValueError("context market runtime overclaims promotion eligibility")
    roots = payload.get("runtime_root_content_sha256s")
    if not isinstance(roots, Mapping) or not roots:
        raise ValueError("context market runtime lacks root hashes")
    if any(not _is_sha256(value) for value in roots.values()):
        raise ValueError("context market runtime has invalid root hash")
    return list(dates)


def load_market_runtime_manifest(root: str | Path) -> dict[str, object]:
    payload = _read_json(Path(root) / "context-market-runtime-manifest.json")
    validate_market_runtime_manifest(payload)
    return payload


def build_record_date_payload(
    *,
    artifact_id: str,
    contract_id: str,
    trading_date: str,
    source_hashes: Mapping[str, str],
    records: list[Mapping[str, object]],
    unavailable: list[Mapping[str, object]],
) -> dict[str, object]:
    if trading_date not in REGISTERED_DATES:
        raise ValueError("record date is outside the registered panel")
    if not source_hashes or any(not _is_sha256(value) for value in source_hashes.values()):
        raise ValueError("record date payload requires source hashes")
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "contract_id": contract_id,
        "trading_date": trading_date,
        "source_hashes": dict(sorted(source_hashes.items())),
        "knowledge_policy": {
            "uses_raw_transcripts": False,
            "uses_ross_actions": False,
            "uses_benchmark_labels": False,
            "uses_retrospective_trade_outcomes": False,
            "uses_later_price_outcomes": False,
            "runtime_strategy_effect": "none",
        },
        "record_count": len(records),
        "unavailable_count": len(unavailable),
        "records": [dict(row) for row in records],
        "unavailable": [dict(row) for row in unavailable],
        "policy_promotion_eligible": False,
    }
    payload["content_sha256"] = json_fingerprint(payload)
    validate_record_date_payload(
        payload,
        artifact_id=artifact_id,
        contract_id=contract_id,
    )
    return payload


def validate_record_date_payload(
    payload: Mapping[str, object],
    *,
    artifact_id: str,
    contract_id: str,
) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported context record-date schema")
    if payload.get("artifact_id") != artifact_id:
        raise ValueError("context record-date artifact mismatch")
    if payload.get("contract_id") != contract_id:
        raise ValueError("context record-date contract mismatch")
    if payload.get("trading_date") not in REGISTERED_DATES:
        raise ValueError("context record date is outside the panel")
    claimed = payload.get("content_sha256")
    projection = {
        key: value for key, value in payload.items() if key != "content_sha256"
    }
    if claimed != json_fingerprint(projection):
        raise ValueError("context record-date fingerprint mismatch")
    records = payload.get("records")
    unavailable = payload.get("unavailable")
    if not isinstance(records, list) or payload.get("record_count") != len(records):
        raise ValueError("context record-date record count mismatch")
    if not isinstance(unavailable, list) or payload.get("unavailable_count") != len(
        unavailable
    ):
        raise ValueError("context record-date unavailable count mismatch")
    if payload.get("policy_promotion_eligible") is not False:
        raise ValueError("context record-date payload cannot promote a policy")
    knowledge = payload.get("knowledge_policy")
    if not isinstance(knowledge, Mapping) or knowledge.get(
        "runtime_strategy_effect"
    ) != "none":
        raise ValueError("context record-date payload is not shadow-only")
    for field in (
        "uses_raw_transcripts",
        "uses_ross_actions",
        "uses_benchmark_labels",
        "uses_retrospective_trade_outcomes",
        "uses_later_price_outcomes",
    ):
        if knowledge.get(field) is not False:
            raise ValueError(f"context record-date knowledge violates {field}")


def build_record_root_manifest(
    *,
    artifact_id: str,
    contract_id: str,
    contract_content_sha256: str,
    source_market_runtime_content_sha256: str,
    date_payloads: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    if list(date_payloads) != list(REGISTERED_DATES):
        raise ValueError("context record root dates differ from registration")
    for value, payload in date_payloads.items():
        validate_record_date_payload(
            payload,
            artifact_id=artifact_id,
            contract_id=contract_id,
        )
        if payload.get("trading_date") != value:
            raise ValueError("context record root date payload mismatch")
    for value in (contract_content_sha256, source_market_runtime_content_sha256):
        if not _is_sha256(value):
            raise ValueError("context record root requires SHA-256 provenance")
    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "contract_id": contract_id,
        "contract_content_sha256": contract_content_sha256,
        "dates": list(REGISTERED_DATES),
        "source_market_runtime_content_sha256": (
            source_market_runtime_content_sha256
        ),
        "date_content_sha256s": {
            value: str(payload["content_sha256"])
            for value, payload in date_payloads.items()
        },
        "record_count": sum(int(payload["record_count"]) for payload in date_payloads.values()),
        "unavailable_count": sum(
            int(payload["unavailable_count"]) for payload in date_payloads.values()
        ),
        "causal_boundary": {
            "uses_raw_transcripts": False,
            "uses_ross_actions": False,
            "uses_retrospective_labels": False,
            "uses_later_price_outcomes": False,
            "runtime_strategy_effect": "none",
        },
        "policy_promotion_eligible": False,
    }
    manifest["content_sha256"] = json_fingerprint(manifest)
    return manifest
