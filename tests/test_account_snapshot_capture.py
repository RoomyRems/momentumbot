from __future__ import annotations

import copy
import hashlib
import json
import unittest
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from momentumbot.research.account_snapshot_capture import (
    CONTRACT_CONTENT_SHA256,
    AccountCredentials,
    AlpacaPaperAccountClient,
    canonical_fingerprint,
    capture_dual_account_bundle,
    load_capture_contract,
    validate_bundle,
    validate_capture_contract,
    validate_snapshot_artifact,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "account-session-snapshot.yml"
CONTRACT = ROOT / "research" / "strategy" / "account-session-snapshot-capture-v0.1.json"
AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "account-session-snapshot-capture-v0.1-2026-08-19.json"
)


def _clock(start: datetime):
    values = iter(start + timedelta(seconds=offset) for offset in range(20))
    return lambda: next(values)


def _responder(
    *,
    account_id: str,
    equity: str,
    buying_power: str,
    positions: list[object] | None = None,
    orders: list[object] | None = None,
):
    observed_headers: list[dict[str, str]] = []

    def request(url: str, **kwargs: object) -> object:
        headers = dict(kwargs.get("headers", {}))
        observed_headers.append(headers)
        if url.endswith("/v2/account"):
            return {
                "id": account_id,
                "status": "ACTIVE",
                "currency": "USD",
                "equity": equity,
                "buying_power": buying_power,
                "cash": equity,
                "account_blocked": False,
                "trading_blocked": False,
                "transfers_blocked": False,
                "account_number": "RAW-NUMBER-MUST-NOT-PERSIST",
            }
        if url.endswith("/v2/positions"):
            return list(positions or [])
        if "/v2/orders?" in url:
            return list(orders or [])
        raise AssertionError(f"unexpected test URL {url}")

    return request, observed_headers


def _client(
    account_class: str,
    *,
    account_id: str,
    equity: str,
    buying_power: str,
    positions: list[object] | None = None,
    orders: list[object] | None = None,
) -> tuple[AlpacaPaperAccountClient, list[dict[str, str]]]:
    request, observed = _responder(
        account_id=account_id,
        equity=equity,
        buying_power=buying_power,
        positions=positions,
        orders=orders,
    )
    credentials = AccountCredentials(
        account_class=account_class,
        api_key=f"{account_class}-api-key-secret-value",
        api_secret=f"{account_class}-api-secret-value",
        expected_equity=Decimal("30000" if account_class == "main" else "2000"),
    )
    return (
        AlpacaPaperAccountClient(credentials, request_json=request),
        observed,
    )


def _clients(**overrides: object):
    main, main_headers = _client(
        "main",
        account_id=str(overrides.get("main_id", "provider-main-id")),
        equity=str(overrides.get("main_equity", "30000.00")),
        buying_power="120000.00",
        positions=overrides.get("main_positions"),
        orders=overrides.get("main_orders"),
    )
    small, small_headers = _client(
        "small",
        account_id=str(overrides.get("small_id", "provider-small-id")),
        equity=str(overrides.get("small_equity", "2000.00")),
        buying_power="4000.00",
        positions=overrides.get("small_positions"),
        orders=overrides.get("small_orders"),
    )
    return {"main": main, "small": small}, {
        "main": main_headers,
        "small": small_headers,
    }


class AccountSnapshotCaptureTests(unittest.TestCase):
    def test_registration_audit_binds_contract_code_workflow_and_tests(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        claimed = audit.pop("content_sha256")
        self.assertEqual(canonical_fingerprint(audit), claimed)
        self.assertEqual(audit["contract_content_sha256"], CONTRACT_CONTENT_SHA256)
        for row in audit["files"].values():
            raw = (ROOT / row["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), row["file_sha256"])
        self.assertEqual(audit["execution_status"]["registered_capture_count"], 0)
        self.assertFalse(audit["portfolio_backtest_eligible"])

    def test_frozen_capture_contract_binds_accounts_schedule_and_parent(self):
        payload = load_capture_contract(CONTRACT)
        self.assertEqual(canonical_fingerprint(payload), CONTRACT_CONTENT_SHA256)
        self.assertEqual(
            [
                row["expected_initial_equity"]
                for row in payload["registered_account_setup"]
            ],
            ["30000", "2000"],
        )
        changed = copy.deepcopy(payload)
        changed["capture_schedule"]["strategy_start_deadline"] = "07:01:00"
        with self.assertRaisesRegex(ValueError, "strategy_start_deadline changed"):
            validate_capture_contract(changed)

    def test_validation_is_clean_distinct_and_secret_safe(self):
        clients, observed_headers = _clients()
        manifest, snapshots = capture_dual_account_bundle(
            clients,
            mode="validate",
            clock=_clock(datetime(2026, 8, 20, 15, 0, tzinfo=UTC)),
            run_context={
                "workflow_run_id": "123",
                "workflow_run_attempt": "1",
                "workflow_event_name": "push",
                "head_sha": "a" * 40,
            },
        )
        validate_bundle(manifest, snapshots)
        self.assertEqual(snapshots, {})
        self.assertEqual(manifest["mode"], "validate")
        self.assertIsNone(manifest["session_date"])
        self.assertTrue(manifest["accounts_are_distinct"])
        self.assertIsNone(manifest["account_snapshot_content_sha256"])
        self.assertEqual(manifest["account_source_records"]["main"]["equity"], "30000")
        self.assertEqual(manifest["account_source_records"]["small"]["equity"], "2000")
        self.assertEqual(sum(len(rows) for rows in observed_headers.values()), 6)
        self.assertEqual(
            observed_headers["main"][0]["APCA-API-KEY-ID"],
            "main-api-key-secret-value",
        )
        self.assertEqual(
            observed_headers["small"][0]["APCA-API-SECRET-KEY"],
            "small-api-secret-value",
        )
        rendered = json.dumps(manifest, sort_keys=True)
        for secret in (
            "main-api-key-secret-value",
            "main-api-secret-value",
            "small-api-key-secret-value",
            "small-api-secret-value",
            "provider-main-id",
            "provider-small-id",
            "RAW-NUMBER-MUST-NOT-PERSIST",
        ):
            self.assertNotIn(secret, rendered)

    def test_registered_capture_produces_integration_compatible_snapshots(self):
        clients, _headers = _clients()
        manifest, snapshots = capture_dual_account_bundle(
            clients,
            mode="capture",
            clock=_clock(datetime(2026, 8, 24, 9, 15, tzinfo=UTC)),
            requested_session_date=date(2026, 8, 24),
            run_context={"head_sha": "b" * 40},
        )
        validate_bundle(manifest, snapshots)
        self.assertEqual(manifest["session_date"], "2026-08-24")
        self.assertIsNone(manifest["account_source_records"])
        main = validate_snapshot_artifact(snapshots["main"])
        small = validate_snapshot_artifact(snapshots["small"])
        self.assertEqual(main.starting_equity, 30_000.0)
        self.assertEqual(main.starting_buying_power, 120_000.0)
        self.assertEqual(small.starting_equity, 2_000.0)
        self.assertEqual(small.starting_buying_power, 4_000.0)
        self.assertNotEqual(main.account_id, small.account_id)
        self.assertEqual(main.session_date, date(2026, 8, 24))

    def test_capture_rejects_unregistered_or_wrong_local_date(self):
        clients, _headers = _clients()
        with self.assertRaisesRegex(ValueError, "not in the registered"):
            capture_dual_account_bundle(
                clients,
                mode="capture",
                clock=_clock(datetime(2026, 8, 23, 9, 15, tzinfo=UTC)),
                requested_session_date=date(2026, 8, 23),
            )
        with self.assertRaisesRegex(ValueError, "requested New York session date"):
            capture_dual_account_bundle(
                clients,
                mode="capture",
                clock=_clock(datetime(2026, 8, 24, 9, 15, tzinfo=UTC)),
                requested_session_date=date(2026, 8, 25),
            )

    def test_capture_rejects_start_or_completion_after_deadline(self):
        clients, _headers = _clients()
        with self.assertRaisesRegex(ValueError, "started after"):
            capture_dual_account_bundle(
                clients,
                mode="capture",
                clock=_clock(datetime(2026, 8, 24, 11, 0, 1, tzinfo=UTC)),
                requested_session_date=date(2026, 8, 24),
            )

        times = iter(
            [
                datetime(2026, 8, 24, 10, 59, 54, tzinfo=UTC),
                datetime(2026, 8, 24, 10, 59, 55, tzinfo=UTC),
                datetime(2026, 8, 24, 10, 59, 56, tzinfo=UTC),
                datetime(2026, 8, 24, 10, 59, 57, tzinfo=UTC),
                datetime(2026, 8, 24, 10, 59, 58, tzinfo=UTC),
                datetime(2026, 8, 24, 11, 0, 1, tzinfo=UTC),
            ]
        )
        with self.assertRaisesRegex(ValueError, "completed after"):
            capture_dual_account_bundle(
                clients,
                mode="capture",
                clock=lambda: next(times),
                requested_session_date=date(2026, 8, 24),
            )

    def test_swapped_equity_and_duplicate_accounts_fail_closed(self):
        swapped, _headers = _clients(main_equity="2000", small_equity="30000")
        with self.assertRaisesRegex(ValueError, "main equity differs"):
            capture_dual_account_bundle(
                swapped,
                mode="validate",
                clock=_clock(datetime(2026, 8, 20, 15, 0, tzinfo=UTC)),
            )
        duplicate, _headers = _clients(
            main_id="same-provider-id", small_id="same-provider-id"
        )
        with self.assertRaisesRegex(ValueError, "same paper account"):
            capture_dual_account_bundle(
                duplicate,
                mode="validate",
                clock=_clock(datetime(2026, 8, 20, 15, 0, tzinfo=UTC)),
            )

    def test_open_positions_or_orders_fail_closed(self):
        positions, _headers = _clients(main_positions=[{"symbol": "TEST"}])
        with self.assertRaisesRegex(
            ValueError, "main paper account has open positions"
        ):
            capture_dual_account_bundle(
                positions,
                mode="validate",
                clock=_clock(datetime(2026, 8, 20, 15, 0, tzinfo=UTC)),
            )
        orders, _headers = _clients(small_orders=[{"id": "order"}])
        with self.assertRaisesRegex(ValueError, "small paper account has open orders"):
            capture_dual_account_bundle(
                orders,
                mode="validate",
                clock=_clock(datetime(2026, 8, 20, 15, 0, tzinfo=UTC)),
            )

    def test_live_endpoint_and_provider_error_details_are_rejected(self):
        client, _headers = _client(
            "main",
            account_id="main",
            equity="30000",
            buying_power="120000",
        )
        with self.assertRaisesRegex(ValueError, "official Alpaca paper endpoint"):
            AlpacaPaperAccountClient(
                client.credentials,
                endpoint="https://api.alpaca.markets",
            )

        def failing_request(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("provider body with sensitive diagnostics")

        safe = AlpacaPaperAccountClient(
            client.credentials,
            request_json=failing_request,
        )
        with self.assertRaises(RuntimeError) as raised:
            safe.account()
        self.assertNotIn("sensitive diagnostics", str(raised.exception))
        self.assertIn("/v2/account", str(raised.exception))

    def test_tampering_breaks_source_snapshot_and_manifest_hashes(self):
        clients, _headers = _clients()
        manifest, snapshots = capture_dual_account_bundle(
            clients,
            mode="capture",
            clock=_clock(datetime(2026, 8, 24, 9, 15, tzinfo=UTC)),
            requested_session_date=date(2026, 8, 24),
        )
        changed = copy.deepcopy(snapshots)
        changed["main"]["starting_equity"] = "99999"
        with self.assertRaisesRegex(ValueError, "content hash mismatch"):
            validate_snapshot_artifact(changed["main"])

        changed = copy.deepcopy(snapshots)
        changed["main"]["source_record"]["cash"] = "1"
        changed["main"]["content_sha256"] = snapshots["main"]["content_sha256"]
        with self.assertRaises(ValueError):
            validate_snapshot_artifact(changed["main"])

        changed_manifest = copy.deepcopy(manifest)
        changed_manifest["accounts_are_distinct"] = False
        with self.assertRaisesRegex(ValueError, "bundle content hash mismatch"):
            validate_bundle(changed_manifest, snapshots)

    def test_workflow_is_scoped_to_paper_capture_and_has_manual_fallback(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("ALPACA_MAIN_API_KEY", text)
        self.assertIn("ALPACA_SMALL_API_SECRET", text)
        self.assertIn("15 9 24-28,31 8 *", text)
        self.assertIn("15 9 1-4 9 *", text)
        self.assertIn("workflow_dispatch", text)
        self.assertIn("mode", text)
        self.assertIn("phase-3-historical-snapshot' || github.sha", text)
        self.assertIn("workflow-source-sha", text)
        self.assertIn("permissions:\n  contents: read", text)
        self.assertNotIn("pull-requests: write", text)
        self.assertNotIn("contents: write", text)


if __name__ == "__main__":
    unittest.main()
