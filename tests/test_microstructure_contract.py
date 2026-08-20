import copy
import gzip
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from momentumbot.research.microstructure_contract import (
    CONTRACT_ID,
    canonical_fingerprint,
    file_sha256,
    inspect_filled_micro_symbol_dates,
    load_level2_registration,
    select_activity_spread_smoke_cohort,
    validate_depth_stream,
    validate_level2_registration,
    validate_tape_stream,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRATION = ROOT / "research" / "strategy" / "level2-tape-feasibility-v0.1.json"
AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "level2-tape-feasibility-v0.1-2026-08-19.json"
)
EXPECTED_CONTENT_SHA256 = (
    "6d3a41d6bde3844900bc880632d8bc9d6c5f7b787edd5f0c302a709dcb9c1bf1"
)


def depth_event(
    event_id,
    *,
    action,
    side="none",
    price_nanos=None,
    size=0,
    order_id=None,
    ts_event_ns=100,
    ts_recv_ns=110,
    sequence=0,
    is_snapshot=False,
    is_last=False,
    bad_ts_recv=False,
):
    return {
        "event_id": event_id,
        "provider": "fixture",
        "dataset": "TEST.DEPTH",
        "venue": "TEST",
        "symbol": "ROSS",
        "instrument_id": "1",
        "publisher_id": 1,
        "channel_id": 0,
        "ts_event_ns": ts_event_ns,
        "ts_recv_ns": ts_recv_ns,
        "sequence": sequence,
        "action": action,
        "side": side,
        "price_nanos": price_nanos,
        "size": size,
        "order_id": order_id,
        "is_snapshot": is_snapshot,
        "is_last": is_last,
        "bad_ts_recv": bad_ts_recv,
    }


class MicrostructureContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registration = json.loads(REGISTRATION.read_text(encoding="utf-8"))

    def test_registration_is_hash_bound_and_keeps_single_venue_scope_explicit(self):
        loaded = load_level2_registration(REGISTRATION)
        self.assertEqual(loaded["contract_id"], CONTRACT_ID)
        self.assertEqual(loaded["content_sha256"], EXPECTED_CONTENT_SHA256)
        unsigned = {key: value for key, value in loaded.items() if key != "content_sha256"}
        self.assertEqual(canonical_fingerprint(unsigned), EXPECTED_CONTENT_SHA256)
        self.assertEqual(loaded["engineering_cohort"]["symbol_date_count"], 36)
        self.assertEqual(
            [row["symbol"] for row in loaded["engineering_cohort"]["smoke_symbol_dates"]],
            ["INTJ", "EQPT", "AMC", "GMM"],
        )

    def test_purchase_or_consolidated_depth_overclaim_fails_closed(self):
        changed = copy.deepcopy(self.registration)
        changed["data_purchase_authorized"] = True
        changed["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in changed.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "must be false"):
            validate_level2_registration(changed)

        changed = copy.deepcopy(self.registration)
        changed["provider_capability_candidates"][0]["venue_scope"] = (
            "consolidated_national_depth"
        )
        changed["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in changed.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "scope must remain explicit"):
            validate_level2_registration(changed)

    def test_complete_snapshot_then_live_event_is_valid(self):
        rows = [
            depth_event("clear", action="clear", is_snapshot=True),
            depth_event(
                "snapshot-add",
                action="add",
                side="ask",
                price_nanos=5_000_000_000,
                size=100,
                order_id=1,
                ts_event_ns=101,
                ts_recv_ns=110,
                is_snapshot=True,
                is_last=True,
            ),
            depth_event(
                "live-add",
                action="add",
                side="bid",
                price_nanos=4_990_000_000,
                size=50,
                order_id=2,
                ts_event_ns=120,
                ts_recv_ns=125,
                sequence=10,
            ),
        ]
        events = validate_depth_stream(rows, require_complete_initial_state=True)
        self.assertEqual(len(events), 3)
        self.assertEqual(events[-1].sequence, 10)

    def test_missing_clear_incomplete_snapshot_and_bad_clock_fail_closed(self):
        live_add = depth_event(
            "live-add",
            action="add",
            side="bid",
            price_nanos=4_990_000_000,
            size=50,
            order_id=2,
            sequence=10,
        )
        with self.assertRaisesRegex(ValueError, "before an initial clear"):
            validate_depth_stream([live_add], require_complete_initial_state=True)

        with self.assertRaisesRegex(ValueError, "snapshot is incomplete"):
            validate_depth_stream(
                [depth_event("clear", action="clear", is_snapshot=True)],
                require_complete_initial_state=True,
            )

        inverted = {**live_add, "ts_event_ns": 200, "ts_recv_ns": 100}
        with self.assertRaisesRegex(ValueError, "precedes event timestamp"):
            validate_depth_stream([inverted], require_complete_initial_state=False)

    def test_tape_preserves_unknown_aggressor_and_rejects_duplicate_ids(self):
        row = {
            "event_id": "trade-1",
            "provider": "fixture",
            "dataset": "TEST.TRADES",
            "venue": "TEST",
            "symbol": "ROSS",
            "instrument_id": "1",
            "ts_event_ns": 100,
            "ts_recv_ns": 110,
            "sequence": 1,
            "price_nanos": 5_000_000_000,
            "size": 100,
            "aggressor_side": "unknown",
            "correction_or_cancel": False,
        }
        events = validate_tape_stream([row])
        self.assertEqual(events[0].aggressor_side.value, "unknown")
        with self.assertRaisesRegex(ValueError, "must be unique"):
            validate_tape_stream([row, row])

    def test_activity_spread_selection_rejects_outcomes(self):
        rows = [
            {
                "trading_date": "2026-01-01",
                "symbol": f"A{index}",
                "trade_row_count": index + 1,
                "plan_count": 1,
                "filled_count": 1,
            }
            for index in range(7)
        ]
        selected = select_activity_spread_smoke_cohort(rows, sample_count=4)
        self.assertEqual(
            [row["activity_rank_zero_based"] for row in selected],
            [0, 2, 4, 6],
        )
        rows[0]["pnl"] = 1000
        with self.assertRaisesRegex(ValueError, "prohibited keys"):
            select_activity_spread_smoke_cohort(rows, sample_count=4)

    def test_frozen_zip_inspector_uses_only_label_blind_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "micro.zip"
            replay = {
                "trading_date": "2026-01-02",
                "symbol": "ROSS",
                "plan_count": 2,
                "filled_count": 1,
                "retrospective_behavior_labels_loaded": False,
            }
            trades = gzip.compress(b"timestamp,price,size\n1,5.0,100\n2,5.1,50\n")
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("dates/2026-01-02/ROSS/runtime-replay.json", json.dumps(replay))
                archive.writestr("dates/2026-01-02/ROSS/trades.csv.gz", trades)
            rows = inspect_filled_micro_symbol_dates(
                path,
                expected_zip_sha256=file_sha256(path),
            )
        self.assertEqual(
            rows,
            [
                {
                    "trading_date": "2026-01-02",
                    "symbol": "ROSS",
                    "trade_row_count": 2,
                    "plan_count": 2,
                    "filled_count": 1,
                }
            ],
        )

    def test_permanent_audit_binds_feasibility_deliverables(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        claimed = audit["content_sha256"]
        unsigned = {key: value for key, value in audit.items() if key != "content_sha256"}
        self.assertEqual(canonical_fingerprint(unsigned), claimed)
        self.assertEqual(audit["registration"]["content_sha256"], EXPECTED_CONTENT_SHA256)
        for item in audit["bound_files"]:
            self.assertEqual(
                hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest(),
                item["file_sha256"],
            )


if __name__ == "__main__":
    unittest.main()
