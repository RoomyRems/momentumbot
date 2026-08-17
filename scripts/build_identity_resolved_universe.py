from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from momentumbot.historical_universe import historical_universe_v0_1_manifest
from momentumbot.identity_continuity import build_date_identity_statuses
from momentumbot.identity_resolved_universe import (
    IDENTITY_AUDIT_LOOKBACK_DAYS,
    IDENTITY_RESOLVED_UNIVERSE_POLICY_ID,
    identity_resolved_membership_fingerprint,
    identity_resolved_universe_v0_1_manifest,
    json_fingerprint,
    provisional_membership_fingerprint,
    resolve_identity_membership,
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate_identity_audit_bundle(
    identity_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _load_json(identity_root / "manifest.json")
    if manifest.get("audit_id") != (
        "historical-identity-corporate-action-audit-v0.1"
    ):
        raise RuntimeError("unsupported identity audit")
    if manifest.get("knowledge_policy", {}).get("uses_benchmark_labels") is not False:
        raise RuntimeError("identity audit must be label-blind")
    if manifest.get("knowledge_policy", {}).get(
        "runtime_strategy_inputs_created"
    ) is not False:
        raise RuntimeError("identity audit must not create strategy inputs")
    eligibility = manifest.get("eligibility", {})
    if eligibility.get("identity_gate_passes_after_explicit_quarantine") is not True:
        raise RuntimeError("identity audit gate did not pass")
    if eligibility.get("full_feature_snapshot_candidate") is not True:
        raise RuntimeError("identity audit did not authorize feature construction")
    if eligibility.get("universe_complete") is not False:
        raise RuntimeError("identity audit cannot claim universe completeness")
    summary = manifest.get("summary", {})
    if summary.get("alias_mapping_gate_pass") is not True:
        raise RuntimeError("identity alias-mapping gate did not pass")
    if summary.get("bulk_corporate_action_gate_pass") is not True:
        raise RuntimeError("identity corporate-action gate did not pass")
    scope = manifest.get("scope", {})
    if scope.get("corporate_action_lookback_days") != IDENTITY_AUDIT_LOOKBACK_DAYS:
        raise RuntimeError("identity audit lookback does not match frozen policy")

    files = manifest.get("files", {})
    required = {
        "identity_bridge": "bridge",
        "alias_validation": "alias_validation",
        "transition_name_change_resolution": "transition_resolution",
        "corporate_action_windows": "action_windows",
        "massive_ticker_event_sample": "ticker_event_sample",
    }
    content: dict[str, object] = {}
    loaded: dict[str, dict[str, Any]] = {}
    for manifest_key, content_key in required.items():
        filename = files.get(manifest_key)
        if not isinstance(filename, str) or not filename:
            raise RuntimeError(f"identity audit is missing {manifest_key}")
        payload = _load_json(identity_root / filename)
        loaded[manifest_key] = payload
        content[content_key] = payload
    if json_fingerprint(content) != manifest.get("content_sha256"):
        raise RuntimeError("identity audit content fingerprint mismatch")

    bridge = loaded["identity_bridge"]
    if bridge.get("identity_policy_id") != (
        "historical-identity-continuity-v0.1"
    ):
        raise RuntimeError("identity bridge policy mismatch")
    claimed_bridge_hash = bridge.get("bridge_sha256")
    bridge_without_hash = {
        key: value for key, value in bridge.items() if key != "bridge_sha256"
    }
    if json_fingerprint(bridge_without_hash) != claimed_bridge_hash:
        raise RuntimeError("identity bridge fingerprint mismatch")
    return manifest, bridge


def validate_expected_audit_result(
    expected: dict[str, Any],
    identity_manifest: dict[str, Any],
    bridge: dict[str, Any],
) -> None:
    """Pin a live rebuild to the previously reviewed provider result."""

    if expected.get("audit_id") != identity_manifest.get("audit_id"):
        raise RuntimeError("expected audit result uses a different audit contract")
    if expected.get("final_artifact", {}).get("audit_content_sha256") != (
        identity_manifest.get("content_sha256")
    ):
        raise RuntimeError("live identity audit differs from frozen audit content")
    if expected.get("results", {}).get("cross_date_bridge", {}).get(
        "bridge_sha256"
    ) != bridge.get("bridge_sha256"):
        raise RuntimeError("live identity bridge differs from frozen result")
    if expected.get("identity_contract", {}).get(
        "snapshot_feature_lookback_days"
    ) != identity_manifest.get("scope", {}).get(
        "corporate_action_lookback_days"
    ):
        raise RuntimeError("frozen result and live identity lookback disagree")

    expected_sources = expected.get("results", {}).get(
        "source_provisional_universe", {}
    )
    if expected_sources != identity_manifest.get("source_artifacts"):
        raise RuntimeError("live provisional source differs from frozen result")

    bridge_status = bridge.get("date_identity_status", {})
    expected_quarantine = expected.get("results", {}).get(
        "explicit_identity_quarantine", {}
    )
    for value in identity_manifest.get("scope", {}).get("dates", []):
        status = bridge_status.get(value, {})
        accepted = status.get("accepted", [])
        quarantined = status.get("quarantined", [])
        expected_date = expected_quarantine.get(value, {})
        if expected_date.get("accepted_after_quarantine") != len(accepted):
            raise RuntimeError("live accepted count differs from frozen result")
        if expected_date.get("provisional_before_quarantine") != (
            len(accepted) + len(quarantined)
        ):
            raise RuntimeError("live provisional count differs from frozen result")
        if expected_date.get("quarantined_tickers") != sorted(
            str(row["ticker"]) for row in quarantined
        ):
            raise RuntimeError("live quarantine differs from frozen result")


def build_date_payload(
    *,
    trading_date: str,
    provisional_payload: dict[str, Any],
    accepted_statuses: list[dict[str, object]],
    quarantined_statuses: list[dict[str, object]],
    identity_manifest: dict[str, Any],
    bridge: dict[str, Any],
    expected_source_policy_fingerprint: str | None = None,
    expected_source_membership_sha256: str | None = None,
) -> dict[str, object]:
    rows = provisional_payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("provisional included artifact must contain rows")
    if provisional_payload.get("trading_date") != trading_date:
        raise RuntimeError("provisional included artifact date mismatch")
    source = identity_manifest.get("source_artifacts", {}).get(trading_date, {})
    source_policy = source.get("policy_fingerprint")
    source_membership = source.get("included_membership_sha256")
    expected_policy = expected_source_policy_fingerprint or source_policy
    expected_membership = (
        expected_source_membership_sha256 or source_membership
    )
    if not isinstance(expected_policy, str) or not expected_policy:
        raise RuntimeError("identity resolution lacks source policy provenance")
    if not isinstance(expected_membership, str) or not expected_membership:
        raise RuntimeError("identity resolution lacks source membership provenance")
    if source and (
        source_policy != expected_policy or source_membership != expected_membership
    ):
        raise RuntimeError("identity audit and provisional source disagree")
    if provisional_payload.get("policy_fingerprint") != expected_policy:
        raise RuntimeError("identity audit source policy fingerprint mismatch")
    if provisional_payload.get("membership_sha256") != expected_membership:
        raise RuntimeError("identity audit source membership fingerprint mismatch")
    if provisional_membership_fingerprint(rows) != provisional_payload.get(
        "membership_sha256"
    ):
        raise RuntimeError("provisional included membership fingerprint mismatch")

    resolved = resolve_identity_membership(
        rows,
        accepted_statuses,
        quarantined_statuses,
    )
    quarantined_tickers = sorted(str(row["ticker"]) for row in quarantined_statuses)
    membership_hash = identity_resolved_membership_fingerprint(resolved)
    return {
        "schema_version": 1,
        "artifact_id": IDENTITY_RESOLVED_UNIVERSE_POLICY_ID,
        "trading_date": trading_date,
        "policy_fingerprint": identity_resolved_universe_v0_1_manifest()[
            "fingerprint"
        ],
        "source_artifacts": {
            "provisional_policy_fingerprint": provisional_payload[
                "policy_fingerprint"
            ],
            "provisional_membership_sha256": provisional_payload[
                "membership_sha256"
            ],
            "identity_audit_id": identity_manifest["audit_id"],
            "identity_audit_content_sha256": identity_manifest["content_sha256"],
            "identity_bridge_sha256": bridge["bridge_sha256"],
        },
        "summary": {
            "provisional_ticker_count": len(rows),
            "identity_accepted_ticker_count": len(resolved),
            "identity_quarantine_count": len(quarantined_tickers),
            "identity_quarantine_tickers": quarantined_tickers,
            "membership_sha256": membership_hash,
        },
        "eligibility": {
            "complete_relative_to_provisional_membership": (
                len(resolved) + len(quarantined_tickers) == len(rows)
            ),
            "identity_gate_pass": True,
            "full_feature_snapshot_candidate": True,
            "universe_complete": False,
            "full_walk_forward_eligible": False,
            "policy_promotion_eligible": False,
        },
        "knowledge_policy": {
            "uses_benchmark_labels": False,
            "uses_future_market_outcomes": False,
            "membership_change": "explicit_identity_quarantine_only",
        },
        "rows": resolved,
    }


def build_panel_identity_statuses(
    provisional_payloads: dict[str, dict[str, Any]],
    *,
    audit_dates: list[str],
    bridge: dict[str, Any],
) -> dict[str, dict[str, list[dict[str, str]]]]:
    """Resolve every panel date and bind the audited endpoint decisions."""

    dates = list(provisional_payloads)
    if len(dates) < 2 or dates != sorted(set(dates)):
        raise RuntimeError("identity panel dates must be unique and ordered")
    if audit_dates != [dates[0], dates[-1]]:
        raise RuntimeError("identity audit must span the panel endpoints")
    bridge_status = bridge.get("date_identity_status")
    if not isinstance(bridge_status, dict):
        raise RuntimeError("identity bridge lacks endpoint statuses")

    statuses: dict[str, dict[str, list[dict[str, str]]]] = {}
    for value, payload in provisional_payloads.items():
        rows = payload.get("rows")
        if not isinstance(rows, list):
            raise RuntimeError(f"provisional identity rows are invalid for {value}")
        status = build_date_identity_statuses(rows)
        if value in audit_dates and status != bridge_status.get(value):
            raise RuntimeError(
                f"independent identity status disagrees with audit for {value}"
            )
        statuses[value] = status
    return statuses


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--census-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expected-audit-result", type=Path)
    args = parser.parse_args(argv)

    provisional_root = args.census_root / "provisional-universe-v0.1"
    provisional_manifest = _load_json(provisional_root / "manifest.json")
    expected_source_policy = historical_universe_v0_1_manifest()
    if provisional_manifest.get("universe_policy", {}).get("fingerprint") != (
        expected_source_policy["fingerprint"]
    ):
        raise RuntimeError("provisional universe policy fingerprint mismatch")
    if provisional_manifest.get("complete_relative_to_census") is not True:
        raise RuntimeError("provisional universe is not complete relative to census")
    if provisional_manifest.get("universe_complete") is not False:
        raise RuntimeError("provisional universe must remain non-promotable")

    identity_root = args.census_root / "identity-continuity-v0.1"
    identity_manifest, bridge = validate_identity_audit_bundle(identity_root)
    if args.expected_audit_result is not None:
        validate_expected_audit_result(
            _load_json(args.expected_audit_result),
            identity_manifest,
            bridge,
        )
    audit_dates = identity_manifest.get("scope", {}).get("dates")
    if not isinstance(audit_dates, list) or len(audit_dates) != 2:
        raise RuntimeError("identity audit must declare exactly two snapshot dates")
    if audit_dates != [bridge.get("earlier_date"), bridge.get("later_date")]:
        raise RuntimeError("identity bridge dates do not match audit scope")
    dates = provisional_manifest.get("dates")
    if (
        not isinstance(dates, list)
        or len(dates) < 2
        or dates != sorted(set(dates))
    ):
        raise RuntimeError("provisional identity panel dates are invalid")
    if audit_dates != [dates[0], dates[-1]]:
        raise RuntimeError("identity audit must span the provisional panel")

    source_date_manifests = provisional_manifest.get("date_manifests")
    if not isinstance(source_date_manifests, list):
        raise RuntimeError("provisional universe lacks date manifests")
    source_by_date = {
        str(row.get("trading_date")): row
        for row in source_date_manifests
        if isinstance(row, dict)
    }
    if set(source_by_date) != set(dates):
        raise RuntimeError("provisional date manifests do not cover the panel")
    provisional_payloads = {
        value: _load_json(provisional_root / f"{value}-included.json")
        for value in dates
    }
    date_status = build_panel_identity_statuses(
        provisional_payloads,
        audit_dates=audit_dates,
        bridge=bridge,
    )

    output_root = args.output or args.census_root / IDENTITY_RESOLVED_UNIVERSE_POLICY_ID
    output_root.mkdir(parents=True, exist_ok=False)
    date_payloads: list[dict[str, object]] = []
    for value in dates:
        status = date_status.get(value, {})
        accepted = status.get("accepted")
        quarantined = status.get("quarantined")
        if not isinstance(accepted, list) or not isinstance(quarantined, list):
            raise RuntimeError(f"identity bridge lacks complete status for {value}")
        provisional_payload = provisional_payloads[value]
        source_manifest = source_by_date[value]
        source_summary = source_manifest.get("summary", {})
        payload = build_date_payload(
            trading_date=value,
            provisional_payload=provisional_payload,
            accepted_statuses=accepted,
            quarantined_statuses=quarantined,
            identity_manifest=identity_manifest,
            bridge=bridge,
            expected_source_policy_fingerprint=expected_source_policy[
                "fingerprint"
            ],
            expected_source_membership_sha256=source_summary.get(
                "included_membership_sha256"
            ),
        )
        if value in audit_dates:
            prefix = "earlier" if value == audit_dates[0] else "later"
            summary = identity_manifest.get("summary", {})
            if payload["summary"]["identity_quarantine_tickers"] != summary.get(
                f"{prefix}_identity_quarantine_tickers"
            ):
                raise RuntimeError(
                    "identity quarantine disagrees with audit manifest"
                )
            if payload["summary"]["identity_accepted_ticker_count"] != summary.get(
                f"{prefix}_identity_accepted_count"
            ):
                raise RuntimeError(
                    "identity accepted count disagrees with audit manifest"
                )
        _write_json(output_root / f"{value}-included.json", payload)
        date_payloads.append(payload)

    root_manifest = {
        "schema_version": 1,
        "artifact_id": IDENTITY_RESOLVED_UNIVERSE_POLICY_ID,
        "dates": dates,
        "universe_policy": identity_resolved_universe_v0_1_manifest(),
        "source_artifacts": {
            "provisional_universe_policy_fingerprint": expected_source_policy[
                "fingerprint"
            ],
            "provisional_membership_sha256_by_date": {
                str(payload["trading_date"]): payload["source_artifacts"][
                    "provisional_membership_sha256"
                ]
                for payload in date_payloads
            },
            "identity_audit_id": identity_manifest["audit_id"],
            "identity_audit_content_sha256": identity_manifest["content_sha256"],
            "identity_bridge_sha256": bridge["bridge_sha256"],
            "identity_audit_scope_dates": audit_dates,
        },
        "date_summaries": {
            str(payload["trading_date"]): payload["summary"]
            for payload in date_payloads
        },
        "eligibility": {
            "complete_relative_to_provisional_membership": all(
                bool(
                    payload["eligibility"][
                        "complete_relative_to_provisional_membership"
                    ]
                )
                for payload in date_payloads
            ),
            "identity_gate_pass": True,
            "full_feature_snapshot_candidate": True,
            "universe_complete": False,
            "full_walk_forward_eligible": False,
            "policy_promotion_eligible": False,
            "remaining_gates": [
                "build point-in-time float and publication-timed news",
                "build complete causal daily premarket and intraday features",
                "repeat the contract across a representative walk-forward panel",
            ],
        },
        "knowledge_policy": {
            "uses_benchmark_labels": False,
            "uses_future_market_outcomes": False,
            "membership_change": "explicit_identity_quarantine_only",
            "identity_status_rule_applied_independently_to_every_date": True,
            "cross_date_alias_audit_scope": "first_and_last_panel_dates",
        },
    }
    root_manifest["content_sha256"] = json_fingerprint(
        {
            "universe_policy": root_manifest["universe_policy"],
            "source_artifacts": root_manifest["source_artifacts"],
            "date_payloads": date_payloads,
        }
    )
    _write_json(output_root / "manifest.json", root_manifest)
    print(
        json.dumps(
            {
                "artifact_id": IDENTITY_RESOLVED_UNIVERSE_POLICY_ID,
                "dates": dates,
                "accepted_ticker_counts": {
                    str(payload["trading_date"]): payload["summary"][
                        "identity_accepted_ticker_count"
                    ]
                    for payload in date_payloads
                },
                "quarantine_ticker_counts": {
                    str(payload["trading_date"]): payload["summary"][
                        "identity_quarantine_count"
                    ]
                    for payload in date_payloads
                },
                "universe_complete": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
