import copy
import hashlib
import json
import unittest
from datetime import UTC, datetime
from pathlib import Path

from momentumbot.research.account_chronological_integration import PANEL_ID
from momentumbot.research.microstructure_contract import canonical_fingerprint
from momentumbot.research.prospective_market_input_capture import (
    ACCOUNT_CAPTURE_CONTENT_SHA256,
    BRIDGE_CHECKPOINT_SHA,
    BRIDGE_CONTRACT_CONTENT_SHA256,
    CONTRACT_CONTENT_SHA256,
    CONTRACT_ID,
    POST_DECISION_CAPTURE_NS,
    PRE_DECISION_QUOTE_NS,
    PROSPECTIVE_EXECUTION_CONTENT_SHA256,
    UNDEF_PRICE,
    build_market_input_capture,
    build_request_manifest,
    load_capture_contract,
    top_of_book_events,
    validate_capture_contract,
    validate_market_input_capture,
    validate_opportunity_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "prospective-market-input-capture-v0.1.json"
)
REGISTRATION_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "prospective-market-input-capture-v0.1-registration-2026-08-22.json"
)


def _ns(value: str) -> int:
    return int(datetime.fromisoformat(value).astimezone(UTC).timestamp() * 1_000_000_000)


def _fingerprinted(payload: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(payload)
    result["content_sha256"] = canonical_fingerprint(result)
    return result


def _opportunity_manifest() -> dict[str, object]:
    return _fingerprinted(
        {
            "schema_version": 1,
            "artifact_id": "prospective-opportunities-2026-08-24",
            "artifact_type": "frozen_label_blind_prospective_opportunities",
            "panel_id": PANEL_ID,
            "opportunities": [
                {
                    "opportunity_id": "2026-08-24-TEST-01",
                    "trading_date": "2026-08-24",
                    "symbol": "TEST",
                    "decision_ts_ns": _ns("2026-08-24T11:30:00+00:00"),
                    "runtime_content_sha256": "a" * 64,
                }
            ],
            "retrospective_labels_loaded": False,
            "later_prices_or_pnl_loaded": False,
        }
    )


def _request_evidence(
    request_manifest: dict[str, object],
    *,
    quote_count: int = 3,
    status_count: int = 3,
) -> dict[str, object]:
    return {
        "requests": [
            {
                "request_id": row["request_id"],
                "dataset": row["dataset"],
                "schema": row["schema"],
                "metadata_matches": True,
                "request_completed": True,
                "record_count": (
                    quote_count if row["schema"] == "mbp-1" else status_count
                ),
            }
            for row in request_manifest["requests"]
        ]
    }


class ProspectiveMarketInputCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load_capture_contract(CONTRACT)
        cls.opportunities = _opportunity_manifest()
        cls.request_manifest = build_request_manifest(
            cls.contract,
            cls.opportunities,
        )
        cls.decision = cls.opportunities["opportunities"][0]["decision_ts_ns"]

    def test_contract_binds_parents_and_authorizes_zero_calls(self):
        self.assertEqual(self.contract["content_sha256"], CONTRACT_CONTENT_SHA256)
        parents = self.contract["frozen_parents"]
        self.assertEqual(
            parents["behavioral_execution_bridge_content_sha256"],
            BRIDGE_CONTRACT_CONTENT_SHA256,
        )
        self.assertEqual(
            parents["behavioral_execution_bridge_checkpoint_sha"],
            BRIDGE_CHECKPOINT_SHA,
        )
        self.assertEqual(
            parents["prospective_execution_contract_content_sha256"],
            PROSPECTIVE_EXECUTION_CONTENT_SHA256,
        )
        self.assertEqual(
            parents["account_capture_contract_content_sha256"],
            ACCOUNT_CAPTURE_CONTENT_SHA256,
        )
        authority = self.contract["authority_boundary"]
        self.assertFalse(authority["provider_metadata_quote_authorized"])
        self.assertFalse(authority["provider_request_authorized"])
        self.assertEqual(authority["databento_credit_authorized_usd"], "0")
        self.assertFalse(authority["broker_order_authorized"])
        self.assertFalse(authority["runtime_authority_created"])

    def test_request_manifest_is_exact_offline_and_label_blind(self):
        report = self.request_manifest
        self.assertEqual(report["contract_id"], CONTRACT_ID)
        self.assertEqual(report["opportunity_count"], 1)
        self.assertEqual(report["request_count"], 2)
        by_schema = {row["schema"]: row for row in report["requests"]}
        self.assertEqual(set(by_schema), {"mbp-1", "status"})
        self.assertEqual(by_schema["mbp-1"]["symbols"], ["TEST"])
        self.assertEqual(
            by_schema["mbp-1"]["start_ns"],
            self.decision - PRE_DECISION_QUOTE_NS,
        )
        self.assertEqual(
            by_schema["mbp-1"]["end_ns"],
            self.decision + POST_DECISION_CAPTURE_NS + 1,
        )
        self.assertEqual(
            by_schema["status"]["start_ns"],
            _ns("2026-08-24T00:00:00+00:00"),
        )
        self.assertFalse(report["provider_metadata_quote_made"])
        self.assertFalse(report["provider_timeseries_request_made"])
        claimed = report["content_sha256"]
        unsigned = {key: value for key, value in report.items() if key != "content_sha256"}
        self.assertEqual(canonical_fingerprint(unsigned), claimed)

    def test_complete_capture_preserves_receive_time_quotes_and_halts(self):
        status_records = [
            {
                "symbol": "TEST",
                "ts_recv_ns": self.decision - 500_000_000,
                "action": 7,
                "is_trading": "Y",
            },
            {
                "symbol": "TEST",
                "ts_recv_ns": self.decision + 200_000_000,
                "action": 8,
                "is_trading": "N",
            },
            {
                "symbol": "TEST",
                "ts_recv_ns": self.decision + 400_000_000,
                "action": 7,
                "is_trading": "Y",
            },
        ]
        quote_records = [
            {
                "symbol": "TEST",
                "ts_recv_ns": self.decision - 50_000_000,
                "sequence": 1,
                "bid_px_nanos": 10_000_000_000,
                "bid_size": 100,
                "ask_px_nanos": 10_010_000_000,
                "ask_size": 200,
            },
            {
                "symbol": "TEST",
                "ts_recv_ns": self.decision + 250_000_000,
                "sequence": 2,
                "bid_px_nanos": 10_020_000_000,
                "bid_size": 150,
                "ask_px_nanos": 10_030_000_000,
                "ask_size": 250,
            },
            {
                "symbol": "TEST",
                "ts_recv_ns": self.decision + 450_000_000,
                "sequence": 3,
                "bid_px_nanos": 10_040_000_000,
                "bid_size": 175,
                "ask_px_nanos": 10_050_000_000,
                "ask_size": 275,
            },
        ]
        capture = build_market_input_capture(
            self.contract,
            self.opportunities,
            self.request_manifest,
            _request_evidence(self.request_manifest),
            quote_records,
            status_records,
        )
        validate_market_input_capture(capture)
        row = capture["captures"][0]
        self.assertEqual(row["capture_status"], "complete")
        self.assertTrue(row["status_coverage_complete"])
        self.assertEqual(row["usable_quote_count"], 3)
        events = top_of_book_events(capture, "2026-08-24-TEST-01")
        self.assertEqual(len(events), 3)
        self.assertEqual([event.halted for event in events], [False, True, False])
        self.assertEqual(str(events[0].bid_price), "10")
        self.assertEqual(str(events[0].ask_price), "10.01")
        self.assertEqual(events[0].ask_size, 200)
        self.assertFalse(capture["execution_outcomes_computed"])
        self.assertFalse(capture["horizon_or_scenario_selected"])

    def test_missing_or_unknown_status_fails_closed(self):
        quote_records = [
            {
                "symbol": "TEST",
                "ts_recv_ns": self.decision,
                "sequence": 1,
                "bid_px_nanos": 10_000_000_000,
                "bid_size": 100,
                "ask_px_nanos": 10_010_000_000,
                "ask_size": 100,
            }
        ]
        for status_records in (
            [],
            [
                {
                    "symbol": "TEST",
                    "ts_recv_ns": self.decision - 500_000_000,
                    "action": 0,
                    "is_trading": "~",
                }
            ],
        ):
            capture = build_market_input_capture(
                self.contract,
                self.opportunities,
                self.request_manifest,
                _request_evidence(
                    self.request_manifest,
                    quote_count=1,
                    status_count=len(status_records),
                ),
                quote_records,
                status_records,
            )
            row = capture["captures"][0]
            self.assertEqual(
                row["capture_status"],
                "unavailable_status_not_causally_known",
            )
            self.assertFalse(row["status_coverage_complete"])
            self.assertEqual(
                top_of_book_events(capture, "2026-08-24-TEST-01"),
                (),
            )

    def test_request_evidence_must_reconcile_counts_and_ranges(self):
        status_records = [
            {
                "symbol": "TEST",
                "ts_recv_ns": self.decision - 500_000_000,
                "action": 7,
                "is_trading": "Y",
            }
        ]
        quote = {
            "symbol": "TEST",
            "ts_recv_ns": self.decision,
            "sequence": 1,
            "bid_px_nanos": 10_000_000_000,
            "bid_size": 100,
            "ask_px_nanos": 10_010_000_000,
            "ask_size": 100,
        }
        with self.assertRaisesRegex(ValueError, "record count does not reconcile"):
            build_market_input_capture(
                self.contract,
                self.opportunities,
                self.request_manifest,
                _request_evidence(
                    self.request_manifest,
                    quote_count=0,
                    status_count=1,
                ),
                [quote],
                status_records,
            )

        outside = copy.deepcopy(quote)
        outside["ts_recv_ns"] = (
            self.decision + POST_DECISION_CAPTURE_NS + 1
        )
        with self.assertRaisesRegex(ValueError, "exactly one frozen request"):
            build_market_input_capture(
                self.contract,
                self.opportunities,
                self.request_manifest,
                _request_evidence(
                    self.request_manifest,
                    quote_count=1,
                    status_count=1,
                ),
                [outside],
                status_records,
            )

    def test_locked_undefined_and_equal_status_time_quotes_are_unusable(self):
        tie_ts = self.decision + 2
        status_records = [
            {
                "symbol": "TEST",
                "ts_recv_ns": self.decision - 500_000_000,
                "action": 7,
                "is_trading": "Y",
            },
            {
                "symbol": "TEST",
                "ts_recv_ns": tie_ts,
                "action": 8,
                "is_trading": "N",
            },
        ]
        quote_records = [
            {
                "symbol": "TEST",
                "ts_recv_ns": self.decision,
                "sequence": 1,
                "bid_px_nanos": 10_000_000_000,
                "bid_size": 100,
                "ask_px_nanos": 10_000_000_000,
                "ask_size": 100,
            },
            {
                "symbol": "TEST",
                "ts_recv_ns": self.decision + 1,
                "sequence": 2,
                "bid_px_nanos": UNDEF_PRICE,
                "bid_size": 100,
                "ask_px_nanos": 10_010_000_000,
                "ask_size": 100,
            },
            {
                "symbol": "TEST",
                "ts_recv_ns": tie_ts,
                "sequence": 3,
                "bid_px_nanos": 10_000_000_000,
                "bid_size": 100,
                "ask_px_nanos": 10_010_000_000,
                "ask_size": 100,
            },
        ]
        capture = build_market_input_capture(
            self.contract,
            self.opportunities,
            self.request_manifest,
            _request_evidence(
                self.request_manifest,
                quote_count=3,
                status_count=2,
            ),
            quote_records,
            status_records,
        )
        row = capture["captures"][0]
        self.assertEqual(row["capture_status"], "complete")
        self.assertEqual(row["usable_quote_count"], 0)
        self.assertEqual(row["unusable_or_status_unknown_quote_count"], 3)
        self.assertEqual(top_of_book_events(capture, row["opportunity_id"]), ())

    def test_status_is_isolated_to_the_same_registered_symbol_date(self):
        second_decision = _ns("2026-08-25T11:30:00+00:00")
        opportunities = _fingerprinted(
            {
                "schema_version": 1,
                "artifact_id": "prospective-opportunities-two-dates",
                "artifact_type": "frozen_label_blind_prospective_opportunities",
                "panel_id": PANEL_ID,
                "opportunities": [
                    {
                        "opportunity_id": "2026-08-24-TEST-01",
                        "trading_date": "2026-08-24",
                        "symbol": "TEST",
                        "decision_ts_ns": self.decision,
                        "runtime_content_sha256": "a" * 64,
                    },
                    {
                        "opportunity_id": "2026-08-25-TEST-01",
                        "trading_date": "2026-08-25",
                        "symbol": "TEST",
                        "decision_ts_ns": second_decision,
                        "runtime_content_sha256": "b" * 64,
                    },
                ],
                "retrospective_labels_loaded": False,
                "later_prices_or_pnl_loaded": False,
            }
        )
        request_manifest = build_request_manifest(self.contract, opportunities)
        evidence = {
            "requests": [
                {
                    "request_id": row["request_id"],
                    "dataset": row["dataset"],
                    "schema": row["schema"],
                    "metadata_matches": True,
                    "request_completed": True,
                    "record_count": int(
                        (row["schema"] == "status" and row["trading_date"] == "2026-08-24")
                        or (row["schema"] == "mbp-1" and row["trading_date"] == "2026-08-25")
                    ),
                }
                for row in request_manifest["requests"]
            ]
        }
        capture = build_market_input_capture(
            self.contract,
            opportunities,
            request_manifest,
            evidence,
            [
                {
                    "symbol": "TEST",
                    "ts_recv_ns": second_decision,
                    "sequence": 1,
                    "bid_px_nanos": 10_000_000_000,
                    "bid_size": 100,
                    "ask_px_nanos": 10_010_000_000,
                    "ask_size": 100,
                }
            ],
            [
                {
                    "symbol": "TEST",
                    "ts_recv_ns": self.decision - 500_000_000,
                    "action": 7,
                    "is_trading": "Y",
                }
            ],
        )
        by_id = {row["opportunity_id"]: row for row in capture["captures"]}
        second = by_id["2026-08-25-TEST-01"]
        self.assertEqual(
            second["capture_status"],
            "unavailable_status_not_causally_known",
        )
        self.assertIsNone(second["initial_status"])
        self.assertEqual(second["quotes"], [])
        self.assertEqual(second["unusable_or_status_unknown_quote_count"], 1)

    def test_rehashed_capture_cannot_tamper_with_halt_or_runtime_authority(self):
        capture = build_market_input_capture(
            self.contract,
            self.opportunities,
            self.request_manifest,
            _request_evidence(
                self.request_manifest,
                quote_count=1,
                status_count=1,
            ),
            [
                {
                    "symbol": "TEST",
                    "ts_recv_ns": self.decision,
                    "sequence": 1,
                    "bid_px_nanos": 10_000_000_000,
                    "bid_size": 100,
                    "ask_px_nanos": 10_010_000_000,
                    "ask_size": 100,
                }
            ],
            [
                {
                    "symbol": "TEST",
                    "ts_recv_ns": self.decision - 500_000_000,
                    "action": 7,
                    "is_trading": "Y",
                }
            ],
        )
        changed = copy.deepcopy(capture)
        changed["captures"][0]["quotes"][0]["halted"] = True
        changed["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in changed.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "halt state changed"):
            validate_market_input_capture(changed)

        changed = copy.deepcopy(capture)
        changed["runtime_authority"] = "paper_orders"
        changed["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in changed.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "runtime authority changed"):
            validate_market_input_capture(changed)

    def test_future_or_retrospective_fields_cannot_enter_manifest(self):
        for field, value in (
            ("outcome", "winner"),
            ("pnl", "100"),
            ("ross_label", "trade"),
            ("selected_scenario", "stress"),
        ):
            changed = copy.deepcopy(self.opportunities)
            changed[field] = value
            unsigned = {
                key: item for key, item in changed.items() if key != "content_sha256"
            }
            changed["content_sha256"] = canonical_fingerprint(unsigned)
            with self.assertRaisesRegex(
                ValueError,
                "manifest fields changed|forbidden keys",
            ):
                validate_opportunity_manifest(changed)

    def test_contract_mutations_cannot_add_scope_or_authority(self):
        raw = json.loads(CONTRACT.read_text(encoding="utf-8"))
        mutations = (
            ("source_scope", "consolidated_nbbo_claim", True),
            ("capture_semantics", "sip_print_proxy_fallback_allowed", True),
            ("authority_boundary", "provider_request_authorized", True),
            ("authority_boundary", "paper_order_authorized", True),
            ("authority_boundary", "policy_promotion_eligible", True),
        )
        for section, field, value in mutations:
            changed = copy.deepcopy(raw)
            changed[section][field] = value
            unsigned = {
                key: item for key, item in changed.items() if key != "content_sha256"
            }
            changed["content_sha256"] = canonical_fingerprint(unsigned)
            with self.assertRaises(ValueError):
                validate_capture_contract(changed)

    def test_registration_audit_is_hash_bound_and_unarmed(self):
        audit = json.loads(REGISTRATION_AUDIT.read_text(encoding="utf-8"))
        claimed = audit["content_sha256"]
        unsigned = {
            key: value for key, value in audit.items() if key != "content_sha256"
        }
        self.assertEqual(canonical_fingerprint(unsigned), claimed)
        self.assertEqual(audit["contract"]["content_sha256"], CONTRACT_CONTENT_SHA256)
        for row in audit["bound_files"]:
            self.assertEqual(
                hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest(),
                row["file_sha256"],
            )
        authority = audit["authority_boundary"]
        self.assertFalse(authority["provider_call_run"])
        self.assertFalse(authority["provider_quote_run"])
        self.assertEqual(authority["databento_credit_used_usd"], "0")
        self.assertFalse(authority["broker_order_submitted"])
        self.assertFalse(authority["runtime_authority_created"])


if __name__ == "__main__":
    unittest.main()
