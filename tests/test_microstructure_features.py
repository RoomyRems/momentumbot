import copy
import json
import unittest
from pathlib import Path

from momentumbot.research.microstructure_contract import (
    CanonicalDepthEvent,
    CanonicalTapeEvent,
    canonical_fingerprint,
    file_sha256,
)
from momentumbot.research.microstructure_features import (
    FEATURE_SET_CONTENT_SHA256,
    FEATURE_SET_ID,
    REGISTERED_WINDOWS_NS,
    V03_SUCCESS_AUDIT_CONTENT_SHA256,
    CausalMicrostructureFeatureEngine,
    load_feature_registration,
    validate_feature_registration,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRATION = (
    ROOT / "research" / "strategy" / "microstructure-feature-mechanics-v0.1.json"
)
V03_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "databento-microstructure-replication-v0.3-run-32437696613-success-2026-08-20.json"
)
FEATURE_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "microstructure-feature-mechanics-v0.1-2026-08-20.json"
)
BASE = 1_800_000_000_000_000_000


def depth_event(
    event_id,
    *,
    action,
    ts_offset,
    side="none",
    price_nanos=None,
    size=0,
    order_id=None,
    is_snapshot=False,
    is_last=True,
    symbol="ROSS",
):
    return CanonicalDepthEvent.from_mapping(
        {
            "event_id": event_id,
            "provider": "fixture",
            "dataset": "TEST.MBO",
            "venue": "XNAS",
            "symbol": symbol,
            "instrument_id": "1",
            "publisher_id": 1,
            "channel_id": 0,
            "ts_event_ns": BASE + ts_offset - 10,
            "ts_recv_ns": BASE + ts_offset,
            "sequence": ts_offset,
            "action": action,
            "side": side,
            "price_nanos": price_nanos,
            "size": size,
            "order_id": order_id,
            "is_snapshot": is_snapshot,
            "is_last": is_last,
            "bad_ts_recv": False,
        }
    )


def tape_event(
    event_id,
    *,
    ts_offset,
    price_nanos,
    size,
    aggressor_side,
    correction_or_cancel=False,
    symbol="ROSS",
):
    return CanonicalTapeEvent.from_mapping(
        {
            "event_id": event_id,
            "provider": "fixture",
            "dataset": "TEST.MBO",
            "venue": "XNAS",
            "symbol": symbol,
            "instrument_id": "1",
            "ts_event_ns": BASE + ts_offset - 10,
            "ts_recv_ns": BASE + ts_offset,
            "sequence": ts_offset,
            "price_nanos": price_nanos,
            "size": size,
            "aggressor_side": aggressor_side,
            "correction_or_cancel": correction_or_cancel,
        }
    )


def ready_engine():
    engine = CausalMicrostructureFeatureEngine()
    engine.ingest_depth(depth_event("clear", action="clear", ts_offset=100))
    return engine


class MicrostructureFeatureMechanicsTests(unittest.TestCase):
    def test_registration_is_hash_bound_threshold_free_and_unspendable(self):
        registration = load_feature_registration(REGISTRATION)
        self.assertEqual(registration["feature_set_id"], FEATURE_SET_ID)
        self.assertEqual(registration["content_sha256"], FEATURE_SET_CONTENT_SHA256)
        self.assertEqual(
            registration["engineering_horizons"]["receive_time_windows_ns"],
            list(REGISTERED_WINDOWS_NS),
        )
        self.assertTrue(
            all(item["threshold"] is None for item in registration["feature_mechanics"])
        )
        self.assertFalse(registration["next_bounded_real_data_candidate"]["authorized"])

        changed = copy.deepcopy(registration)
        changed["feature_mechanics"][0]["threshold"] = 1
        changed["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in changed.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "content hash changed|threshold"):
            validate_feature_registration(changed)

        audit = json.loads(FEATURE_AUDIT.read_text(encoding="utf-8"))
        audit_claimed = audit.pop("content_sha256")
        self.assertEqual(canonical_fingerprint(audit), audit_claimed)
        for item in audit["bound_files"]:
            self.assertEqual(
                file_sha256(ROOT / item["path"]),
                item["file_sha256"],
            )

    def test_v03_success_audit_is_permanently_hash_bound(self):
        audit = json.loads(V03_AUDIT.read_text(encoding="utf-8"))
        claimed = audit.pop("content_sha256")
        self.assertEqual(claimed, V03_SUCCESS_AUDIT_CONTENT_SHA256)
        self.assertEqual(canonical_fingerprint(audit), claimed)
        self.assertEqual(
            audit["combined_engineering_evidence"]["four_case_exact_samples"],
            612,
        )
        self.assertFalse(audit["claim_boundary"]["profitability_claim_supported"])

    def test_top_depth_imbalance_and_depth_walk_are_exact_rationals(self):
        engine = ready_engine()
        engine.ingest_depth(
            depth_event(
                "bid-1",
                action="add",
                ts_offset=200,
                side="bid",
                price_nanos=9_990_000_000,
                size=600,
                order_id=1,
            )
        )
        engine.ingest_depth(
            depth_event(
                "bid-2",
                action="add",
                ts_offset=300,
                side="bid",
                price_nanos=9_980_000_000,
                size=400,
                order_id=2,
            )
        )
        engine.ingest_depth(
            depth_event(
                "ask-1",
                action="add",
                ts_offset=400,
                side="ask",
                price_nanos=10_010_000_000,
                size=300,
                order_id=3,
            )
        )
        engine.ingest_depth(
            depth_event(
                "ask-2",
                action="add",
                ts_offset=500,
                side="ask",
                price_nanos=10_020_000_000,
                size=700,
                order_id=4,
            )
        )

        snapshot = engine.snapshot(hypothetical_order_sizes=[500])
        book = snapshot["book"]
        self.assertEqual(book["spread_nanos"], 20_000_000)
        self.assertEqual(book["bid_depth_shares"], 1000)
        self.assertEqual(book["ask_depth_shares"], 1000)
        self.assertEqual(book["depth_imbalance_numerator"], 0)
        self.assertEqual(book["depth_imbalance_denominator"], 2000)

        buy = next(
            row
            for row in snapshot["depth_constrained_slippage"]
            if row["direction"] == "buy"
        )
        self.assertEqual(buy["displayed_filled_quantity"], 500)
        self.assertEqual(buy["displayed_unfilled_quantity"], 0)
        self.assertEqual(buy["worst_price_nanos"], 10_020_000_000)
        self.assertEqual(
            buy["notional_price_nanos_shares"],
            300 * 10_010_000_000 + 200 * 10_020_000_000,
        )
        self.assertFalse(buy["queue_position_resolved"])
        self.assertFalse(buy["hidden_liquidity_assumed"])

    def test_replenishment_matches_same_price_depletion_fifo(self):
        engine = ready_engine()
        engine.ingest_depth(
            depth_event(
                "ask-resting",
                action="add",
                ts_offset=200,
                side="ask",
                price_nanos=10_000_000_000,
                size=1000,
                order_id=1,
            )
        )
        engine.ingest_depth(
            depth_event(
                "fill-100",
                action="fill",
                ts_offset=300,
                side="ask",
                price_nanos=10_000_000_000,
                size=100,
                order_id=1,
            )
        )
        engine.ingest_depth(
            depth_event(
                "refresh-after-fill",
                action="add",
                ts_offset=400,
                side="ask",
                price_nanos=10_000_000_000,
                size=100,
                order_id=2,
            )
        )
        engine.ingest_depth(
            depth_event(
                "cancel-200",
                action="cancel",
                ts_offset=500,
                side="ask",
                price_nanos=10_000_000_000,
                size=200,
                order_id=1,
            )
        )
        engine.ingest_depth(
            depth_event(
                "refresh-after-cancel",
                action="add",
                ts_offset=600,
                side="ask",
                price_nanos=10_000_000_000,
                size=50,
                order_id=3,
            )
        )

        one_second = engine.snapshot()["windows"][0]
        replenishment = one_second["displayed_replenishment"]["ask"]
        self.assertEqual(replenishment["replenishment_event_count"], 2)
        self.assertEqual(replenishment["replenished_shares"], 150)
        self.assertEqual(replenishment["replenished_after_fill_shares"], 100)
        self.assertEqual(
            replenishment["replenished_after_nonexecution_removal_shares"],
            50,
        )
        flow = one_second["book_flow"]["ask"]
        self.assertEqual(flow["filled_shares"], 100)
        self.assertEqual(flow["canceled_shares"], 200)

    def test_signed_tape_preserves_unknown_and_emits_breakout_context(self):
        engine = ready_engine()
        engine.ingest_tape(
            tape_event(
                "buy-1",
                ts_offset=100_000_000,
                price_nanos=10_000_000_000,
                size=100,
                aggressor_side="buy",
            )
        )
        engine.ingest_tape(
            tape_event(
                "buy-2",
                ts_offset=200_000_000,
                price_nanos=10_020_000_000,
                size=200,
                aggressor_side="buy",
            )
        )
        engine.ingest_tape(
            tape_event(
                "unknown",
                ts_offset=300_000_000,
                price_nanos=10_010_000_000,
                size=25,
                aggressor_side="unknown",
            )
        )
        engine.ingest_tape(
            tape_event(
                "sell-below",
                ts_offset=400_000_000,
                price_nanos=9_990_000_000,
                size=50,
                aggressor_side="sell",
            )
        )

        one_second = engine.snapshot(
            breakout_level_nanos=10_000_000_000
        )["windows"][0]
        tape = one_second["signed_trade_velocity"]
        self.assertTrue(tape["available"])
        self.assertEqual(tape["by_aggressor_side"]["buy"]["shares"], 300)
        self.assertEqual(tape["by_aggressor_side"]["sell"]["shares"], 50)
        self.assertEqual(tape["by_aggressor_side"]["unknown"]["shares"], 25)
        self.assertEqual(tape["net_buy_minus_sell_shares"], 250)
        self.assertEqual(
            one_second["observed_trade_price_sweep"]["buy_distinct_trade_price_count"],
            2,
        )
        self.assertFalse(
            one_second["observed_trade_price_sweep"]["consumed_book_levels_claimed"]
        )
        breakout = one_second["breakout_progress_context"]
        self.assertEqual(breakout["buy_shares_at_or_above"], 300)
        self.assertEqual(breakout["post_cross_sell_shares_below_breakout"], 50)

    def test_tape_correction_fails_affected_families_closed(self):
        engine = ready_engine()
        engine.ingest_tape(
            tape_event(
                "trade",
                ts_offset=1000,
                price_nanos=10_000_000_000,
                size=100,
                aggressor_side="buy",
            )
        )
        engine.ingest_tape(
            tape_event(
                "correction",
                ts_offset=2000,
                price_nanos=10_000_000_000,
                size=100,
                aggressor_side="buy",
                correction_or_cancel=True,
            )
        )
        window = engine.snapshot(breakout_level_nanos=10_000_000_000)["windows"][0]
        self.assertFalse(window["signed_trade_velocity"]["available"])
        self.assertEqual(
            window["signed_trade_velocity"]["unavailable_reason"],
            "correction_or_cancel_in_window",
        )
        self.assertFalse(window["execution_price_impact"]["available"])
        self.assertFalse(window["breakout_progress_context"]["available"])

    def test_registered_windows_are_start_exclusive_and_history_is_bounded(self):
        engine = ready_engine()
        engine.ingest_tape(
            tape_event(
                "boundary",
                ts_offset=1_000,
                price_nanos=10_000_000_000,
                size=100,
                aggressor_side="buy",
            )
        )
        engine.ingest_tape(
            tape_event(
                "latest",
                ts_offset=1_000_001_000,
                price_nanos=10_010_000_000,
                size=50,
                aggressor_side="buy",
            )
        )
        one_second = engine.snapshot()["windows"][0]["signed_trade_velocity"]
        self.assertEqual(one_second["by_aggressor_side"]["buy"]["event_count"], 1)
        self.assertEqual(one_second["by_aggressor_side"]["buy"]["shares"], 50)

    def test_reset_incomplete_state_scope_and_time_fail_closed(self):
        engine = CausalMicrostructureFeatureEngine()
        engine.ingest_depth(
            depth_event(
                "open-clear",
                action="clear",
                ts_offset=100,
                is_snapshot=True,
                is_last=False,
            )
        )
        unavailable = engine.snapshot(hypothetical_order_sizes=[100])
        self.assertFalse(unavailable["book"]["available"])
        self.assertEqual(unavailable["book"]["unavailable_reason"], "book_not_ready")
        self.assertFalse(unavailable["depth_constrained_slippage"][0]["available"])

        engine.ingest_depth(
            depth_event(
                "snapshot-bid",
                action="add",
                ts_offset=200,
                side="bid",
                price_nanos=9_990_000_000,
                size=100,
                order_id=1,
                is_snapshot=True,
                is_last=False,
            )
        )
        engine.ingest_depth(
            depth_event(
                "snapshot-ask",
                action="add",
                ts_offset=300,
                side="ask",
                price_nanos=10_010_000_000,
                size=100,
                order_id=2,
                is_snapshot=True,
                is_last=True,
            )
        )
        ready = engine.snapshot()
        self.assertTrue(ready["book"]["available"])
        self.assertEqual(ready["windows"][0]["book_flow"]["bid"]["added_shares"], 0)

        with self.assertRaisesRegex(ValueError, "scope changed"):
            engine.ingest_tape(
                tape_event(
                    "wrong-symbol",
                    ts_offset=400,
                    price_nanos=10_000_000_000,
                    size=1,
                    aggressor_side="unknown",
                    symbol="OTHER",
                )
            )
        with self.assertRaisesRegex(ValueError, "receive-time ordered"):
            engine.ingest_tape(
                tape_event(
                    "out-of-order",
                    ts_offset=250,
                    price_nanos=10_000_000_000,
                    size=1,
                    aggressor_side="unknown",
                )
            )

    def test_snapshot_fingerprint_is_reproducible_and_has_no_authority(self):
        engine = ready_engine()
        first = engine.snapshot(as_of_ts_recv_ns=BASE + 1000)
        second = engine.snapshot(as_of_ts_recv_ns=BASE + 1000)
        self.assertEqual(first, second)
        claimed = first["content_sha256"]
        unsigned = {key: value for key, value in first.items() if key != "content_sha256"}
        self.assertEqual(canonical_fingerprint(unsigned), claimed)
        self.assertFalse(first["thresholds_applied"])
        self.assertFalse(first["retrospective_labels_loaded"])
        self.assertEqual(first["runtime_authority"], "none_shadow_only")


if __name__ == "__main__":
    unittest.main()
