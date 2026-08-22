import copy
import hashlib
import json
import unittest
from pathlib import Path

from momentumbot.research.microstructure_behavioral_comparison import (
    PROTOCOL_CONTENT_SHA256,
    build_behavioral_comparison,
    load_and_validate_behavioral_registration,
    validate_behavioral_registration,
)
from momentumbot.research.microstructure_contract import canonical_fingerprint
from momentumbot.research.microstructure_features import (
    FEATURE_SET_ID,
    REGISTERED_WINDOWS_NS,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "research"
    / "strategy"
    / "microstructure-behavioral-comparison-v0.1.json"
)
REGISTRATION_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "microstructure-behavioral-comparison-v0.1-registration-2026-08-21.json"
)
ANCHOR = 20_000_000_000
BREAKOUT = 10_000_000_000


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def feature_snapshot(
    as_of: int,
    *,
    value_offset: int = 0,
    scope_symbol: str = "TEST",
    tape_available: bool = True,
) -> dict[str, object]:
    windows = []
    for horizon in REGISTERED_WINDOWS_NS:
        windows.append(
            {
                "window_ns": horizon,
                "start_exclusive_ts_recv_ns": as_of - horizon,
                "end_inclusive_ts_recv_ns": as_of,
                "book_flow": {
                    "available": True,
                    "bid": {"canceled_shares": 20 + value_offset},
                    "ask": {"canceled_shares": 30 + value_offset},
                },
                "displayed_replenishment": {
                    "available": True,
                    "bid": {"replenished_after_fill_shares": 40 + value_offset},
                    "ask": {"replenished_after_fill_shares": 50 + value_offset},
                },
                "signed_trade_velocity": {
                    "available": tape_available,
                    "net_buy_minus_sell_shares": 10 + value_offset,
                },
                "execution_price_impact": {
                    "available": tape_available,
                    "buy_executed_shares": 100 + value_offset,
                    "sell_executed_shares": 90 + value_offset,
                    "buy_positive_progress_nanos": 1_000_000 + value_offset,
                },
                "breakout_progress_context": {
                    "available": tape_available,
                    "breakout_level_nanos": BREAKOUT,
                    "buy_shares_at_or_above": 70 + value_offset,
                    "post_cross_sell_shares_below_breakout": 15 + value_offset,
                },
            }
        )
    payload: dict[str, object] = {
        "schema_version": 1,
        "feature_set_id": FEATURE_SET_ID,
        "as_of_ts_recv_ns": as_of,
        "source_scope": {
            "provider": "databento",
            "venue": "XNAS",
            "symbol": scope_symbol,
            "instrument_id": 123,
            "consolidated_national_depth": False,
        },
        "registered_windows_ns": list(REGISTERED_WINDOWS_NS),
        "book": {
            "available": True,
            "depth_imbalance_numerator": 100 + value_offset,
            "depth_imbalance_denominator": 400,
            "spread_bps_numerator": 20_000 + value_offset,
            "spread_bps_denominator": 2_000_000,
        },
        "windows": windows,
        "depth_constrained_slippage": [
            {
                "available": True,
                "requested_quantity": 100,
                "direction": "buy",
                "displayed_filled_quantity": 90 + value_offset,
                "displayed_unfilled_quantity": 10 - value_offset,
                "worst_price_nanos": 10_010_000_000 + value_offset,
                "notional_price_nanos_shares": 900_000_000_000 + value_offset,
            },
            {
                "available": True,
                "requested_quantity": 100,
                "direction": "sell",
                "displayed_filled_quantity": 90 + value_offset,
                "displayed_unfilled_quantity": 10 - value_offset,
                "worst_price_nanos": 9_990_000_000 - value_offset,
                "notional_price_nanos_shares": 899_000_000_000 - value_offset,
            },
        ],
        "thresholds_applied": False,
        "retrospective_labels_loaded": False,
        "runtime_authority": "none_shadow_only",
    }
    payload["content_sha256"] = canonical_fingerprint(payload)
    return payload


def post_snapshots(*, tape_available: bool = True) -> dict[int, dict[str, object]]:
    return {
        horizon: feature_snapshot(
            ANCHOR + horizon,
            value_offset=10,
            tape_available=tape_available,
        )
        for horizon in REGISTERED_WINDOWS_NS
    }


class MicrostructureBehavioralComparisonTests(unittest.TestCase):
    def test_registration_is_hash_bound_unarmed_and_preoutcome(self):
        contract = load_and_validate_behavioral_registration(CONTRACT)
        self.assertEqual(contract["content_sha256"], PROTOCOL_CONTENT_SHA256)
        self.assertFalse(contract["provider_request_authorized"])
        self.assertFalse(contract["feature_threshold_selection_permitted"])
        self.assertFalse(contract["horizon_selection_permitted"])
        self.assertEqual(
            contract["future_cohort_gate"]["databento_request_count"],
            0,
        )
        self.assertEqual(
            contract["future_cohort_gate"]["databento_cost_authorized_usd"],
            "0",
        )

    def test_exact_disjoint_pre_post_comparison_reports_every_horizon(self):
        result = build_behavioral_comparison(
            opportunity_id="opportunity-1",
            anchor_recv_ts_ns=ANCHOR,
            breakout_level_nanos=BREAKOUT,
            pre_snapshot=feature_snapshot(ANCHOR),
            post_snapshots_by_horizon=post_snapshots(),
        )
        self.assertEqual(
            [row["horizon_ns"] for row in result["horizons"]],
            list(REGISTERED_WINDOWS_NS),
        )
        for row in result["horizons"]:
            self.assertEqual(
                row["pre_interval"]["end_inclusive_ts_recv_ns"],
                ANCHOR,
            )
            self.assertEqual(
                row["post_interval"]["start_exclusive_ts_recv_ns"],
                ANCHOR,
            )
            metrics = {metric["metric_id"]: metric for metric in row["metrics"]}
            imbalance = metrics["book.depth-imbalance"]
            self.assertEqual(imbalance["post_minus_pre_numerator"], 1)
            self.assertEqual(imbalance["post_minus_pre_denominator"], 40)
            self.assertEqual(imbalance["direction"], "increase")
            tape = metrics["tape.net-buy-minus-sell-shares"]
            self.assertEqual(tape["post_minus_pre"], 10)
            self.assertEqual(tape["direction"], "increase")
            buy_walk = next(
                walk for walk in row["depth_walk"] if walk["direction"] == "buy"
            )
            unfilled = next(
                field
                for field in buy_walk["fields"]
                if field["field"] == "displayed_unfilled_quantity"
            )
            self.assertEqual(unfilled["post_minus_pre"], -10)
            self.assertEqual(unfilled["direction"], "decrease")
        self.assertFalse(result["thresholds_applied"])
        self.assertIsNone(result["confirmation_or_adverse_classification"])
        self.assertIsNone(result["hidden_buyer_or_seller_classification"])
        claimed = result.pop("content_sha256")
        self.assertEqual(canonical_fingerprint(result), claimed)

    def test_unavailable_tape_families_fail_closed_without_book_loss(self):
        result = build_behavioral_comparison(
            opportunity_id="opportunity-2",
            anchor_recv_ts_ns=ANCHOR,
            breakout_level_nanos=BREAKOUT,
            pre_snapshot=feature_snapshot(ANCHOR),
            post_snapshots_by_horizon=post_snapshots(tape_available=False),
        )
        metrics = {
            metric["metric_id"]: metric
            for metric in result["horizons"][0]["metrics"]
        }
        self.assertFalse(metrics["tape.buy-executed-shares"]["available"])
        self.assertEqual(
            metrics["tape.buy-executed-shares"]["direction"],
            "unavailable",
        )
        self.assertTrue(metrics["book.depth-imbalance"]["available"])

    def test_snapshot_tamper_labels_thresholds_and_authority_fail_closed(self):
        for field, value in (
            ("retrospective_labels_loaded", True),
            ("thresholds_applied", True),
            ("runtime_authority", "trade"),
        ):
            pre = feature_snapshot(ANCHOR)
            pre[field] = value
            pre["content_sha256"] = canonical_fingerprint(
                {key: item for key, item in pre.items() if key != "content_sha256"}
            )
            with self.assertRaises(ValueError):
                build_behavioral_comparison(
                    opportunity_id="blocked",
                    anchor_recv_ts_ns=ANCHOR,
                    breakout_level_nanos=BREAKOUT,
                    pre_snapshot=pre,
                    post_snapshots_by_horizon=post_snapshots(),
                )

        tampered = feature_snapshot(ANCHOR)
        tampered["book"]["depth_imbalance_numerator"] = 999
        with self.assertRaises(ValueError):
            build_behavioral_comparison(
                opportunity_id="tampered",
                anchor_recv_ts_ns=ANCHOR,
                breakout_level_nanos=BREAKOUT,
                pre_snapshot=tampered,
                post_snapshots_by_horizon=post_snapshots(),
            )

    def test_scope_anchor_breakout_and_horizon_drift_fail_closed(self):
        wrong_scope = post_snapshots()
        wrong_scope[REGISTERED_WINDOWS_NS[0]] = feature_snapshot(
            ANCHOR + REGISTERED_WINDOWS_NS[0],
            value_offset=10,
            scope_symbol="OTHER",
        )
        with self.assertRaises(ValueError):
            build_behavioral_comparison(
                opportunity_id="scope-drift",
                anchor_recv_ts_ns=ANCHOR,
                breakout_level_nanos=BREAKOUT,
                pre_snapshot=feature_snapshot(ANCHOR),
                post_snapshots_by_horizon=wrong_scope,
            )

        missing_horizon = post_snapshots()
        missing_horizon.pop(REGISTERED_WINDOWS_NS[0])
        with self.assertRaises(ValueError):
            build_behavioral_comparison(
                opportunity_id="horizon-drift",
                anchor_recv_ts_ns=ANCHOR,
                breakout_level_nanos=BREAKOUT,
                pre_snapshot=feature_snapshot(ANCHOR),
                post_snapshots_by_horizon=missing_horizon,
            )

        wrong_breakout = post_snapshots()
        first = wrong_breakout[REGISTERED_WINDOWS_NS[0]]
        first["windows"][0]["breakout_progress_context"][
            "breakout_level_nanos"
        ] += 1
        first["content_sha256"] = canonical_fingerprint(
            {key: item for key, item in first.items() if key != "content_sha256"}
        )
        with self.assertRaises(ValueError):
            build_behavioral_comparison(
                opportunity_id="breakout-drift",
                anchor_recv_ts_ns=ANCHOR,
                breakout_level_nanos=BREAKOUT,
                pre_snapshot=feature_snapshot(ANCHOR),
                post_snapshots_by_horizon=wrong_breakout,
            )

    def test_contract_overclaim_or_provider_authority_fails_closed(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        for field in (
            "provider_request_authorized",
            "feature_threshold_selection_permitted",
            "horizon_selection_permitted",
            "profitability_claim_eligible",
        ):
            changed = copy.deepcopy(contract)
            changed[field] = True
            unsigned = {
                key: value for key, value in changed.items() if key != "content_sha256"
            }
            changed["content_sha256"] = canonical_fingerprint(unsigned)
            with self.assertRaises(ValueError):
                validate_behavioral_registration(changed)

    def test_registration_audit_binds_the_unarmed_bundle(self):
        audit = json.loads(REGISTRATION_AUDIT.read_text(encoding="utf-8"))
        claimed = audit["content_sha256"]
        unsigned = {
            key: value for key, value in audit.items() if key != "content_sha256"
        }
        self.assertEqual(canonical_fingerprint(unsigned), claimed)
        self.assertEqual(audit["protocol_content_sha256"], PROTOCOL_CONTENT_SHA256)
        self.assertFalse(audit["provider_request_made"])
        self.assertFalse(audit["databento_credit_used"])
        self.assertFalse(audit["runtime_authority_created"])
        for item in audit["bound_files"]:
            self.assertEqual(file_sha256(ROOT / item["path"]), item["file_sha256"])


if __name__ == "__main__":
    unittest.main()
