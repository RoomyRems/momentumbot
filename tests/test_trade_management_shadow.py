import unittest

import pandas as pd

from momentumbot.micro_execution import MicroEntryPlan
from momentumbot.research.trade_management_shadow import (
    CONTRACT_ID,
    ManagementExitReason,
    REGISTERED_CELLS,
    management_cell,
    simulate_trade_management,
)


def trade_frame(rows):
    copied = [dict(row) for row in rows]
    index = pd.to_datetime(
        [row.pop("timestamp") for row in copied],
        utc=True,
        format="mixed",
    )
    return pd.DataFrame(copied, index=index)


def bar_frame(rows):
    copied = [dict(row) for row in rows]
    index = pd.to_datetime(
        [row.pop("timestamp") for row in copied],
        utc=True,
        format="mixed",
    )
    return pd.DataFrame(copied, index=index)


def plan():
    return MicroEntryPlan(
        symbol="ROSS",
        source_bar_start=pd.Timestamp("2026-07-10T12:00:00Z"),
        armed_at=pd.Timestamp("2026-07-10T12:00:10Z"),
        expires_at=pd.Timestamp("2026-07-10T12:00:20Z"),
        breakout_level=4.99,
        minimum_new_high_price=5.00,
        stop_price=4.90,
    )


def base_fill_and_future(*future):
    return trade_frame(
        [
            {
                "timestamp": "2026-07-10T12:00:11Z",
                "price": 5.00,
                "size": 100,
                "conditions": ("@",),
                "tape": "C",
            },
            *future,
        ]
    )


class TradeManagementShadowTests(unittest.TestCase):
    def test_registered_cells_are_exact_and_unknown_cell_fails_closed(self):
        self.assertEqual(CONTRACT_ID, "trade-management-shadow-v0.1")
        self.assertEqual(
            [cell.cell_id for cell in REGISTERED_CELLS],
            [
                "full-first-red-10s",
                "half-2r-breakeven-first-red-10s",
                "full-first-red-1m",
                "half-2r-breakeven-first-red-1m",
            ],
        )
        with self.assertRaisesRegex(ValueError, "unregistered"):
            management_cell("best-july-result")

    def test_initial_stop_precedes_later_red_signal(self):
        bars = bar_frame(
            [
                {
                    "timestamp": "2026-07-10T12:00:10Z",
                    "open": 5.00,
                    "close": 4.95,
                }
            ]
        )
        trades = base_fill_and_future(
            {
                "timestamp": "2026-07-10T12:00:15Z",
                "price": 4.89,
                "size": 100,
                "conditions": ("@",),
                "tape": "C",
            },
            {
                "timestamp": "2026-07-10T12:00:20.100Z",
                "price": 4.95,
                "size": 100,
                "conditions": ("@",),
                "tape": "C",
            },
        )
        outcome = simulate_trade_management(
            plan(),
            fill_time=pd.Timestamp("2026-07-10T12:00:11Z"),
            fill_price=5.00,
            bars=bars,
            trades=trades,
            cell="full-first-red-10s",
        )
        self.assertEqual(outcome.status, "closed")
        self.assertEqual(outcome.legs[0].reason, ManagementExitReason.INITIAL_STOP)
        self.assertEqual(outcome.legs[0].exit_time, pd.Timestamp("2026-07-10T12:00:15Z"))
        self.assertAlmostEqual(outcome.weighted_realized_r, -1.1)

    def test_red_candle_is_usable_only_after_bar_completion(self):
        bars = bar_frame(
            [
                {
                    "timestamp": "2026-07-10T12:00:10Z",
                    "open": 5.00,
                    "close": 4.98,
                }
            ]
        )
        trades = base_fill_and_future(
            {
                "timestamp": "2026-07-10T12:00:19.900Z",
                "price": 5.15,
                "size": 100,
                "conditions": ("@",),
                "tape": "C",
            },
            {
                "timestamp": "2026-07-10T12:00:20.100Z",
                "price": 5.12,
                "size": 100,
                "conditions": ("@",),
                "tape": "C",
            },
        )
        outcome = simulate_trade_management(
            plan(),
            fill_time=pd.Timestamp("2026-07-10T12:00:11Z"),
            fill_price=5.00,
            bars=bars,
            trades=trades,
            cell="full-first-red-10s",
        )
        self.assertEqual(outcome.first_red_signal_at, pd.Timestamp("2026-07-10T12:00:20Z"))
        self.assertEqual(outcome.legs[0].reason, ManagementExitReason.FIRST_RED_CANDLE)
        self.assertEqual(outcome.legs[0].exit_time, pd.Timestamp("2026-07-10T12:00:20.100Z"))
        self.assertEqual(outcome.legs[0].exit_price, 5.12)

    def test_half_at_two_r_moves_only_remainder_stop_to_actual_fill(self):
        bars = bar_frame(
            [
                {
                    "timestamp": "2026-07-10T12:00:10Z",
                    "open": 5.00,
                    "close": 5.10,
                },
                {
                    "timestamp": "2026-07-10T12:00:20Z",
                    "open": 5.10,
                    "close": 5.08,
                },
            ]
        )
        trades = base_fill_and_future(
            {
                "timestamp": "2026-07-10T12:00:18Z",
                "price": 5.21,
                "size": 100,
                "conditions": ("@",),
                "tape": "C",
            },
            {
                "timestamp": "2026-07-10T12:00:22Z",
                "price": 4.99,
                "size": 100,
                "conditions": ("@",),
                "tape": "C",
            },
        )
        outcome = simulate_trade_management(
            plan(),
            fill_time=pd.Timestamp("2026-07-10T12:00:11Z"),
            fill_price=5.00,
            bars=bars,
            trades=trades,
            cell="half-2r-breakeven-first-red-10s",
        )
        self.assertEqual(outcome.first_target_price, 5.20)
        self.assertTrue(outcome.target_touched)
        self.assertTrue(outcome.stop_moved_to_breakeven)
        self.assertEqual([leg.reason for leg in outcome.legs], [
            ManagementExitReason.FIRST_TARGET,
            ManagementExitReason.BREAKEVEN_STOP,
        ])
        self.assertEqual([leg.quantity_fraction for leg in outcome.legs], [0.5, 0.5])
        self.assertAlmostEqual(outcome.weighted_realized_r, 0.95)

    def test_completed_red_signal_has_priority_over_target_on_same_print(self):
        bars = bar_frame(
            [
                {
                    "timestamp": "2026-07-10T12:00:10Z",
                    "open": 5.10,
                    "close": 5.05,
                }
            ]
        )
        trades = base_fill_and_future(
            {
                "timestamp": "2026-07-10T12:00:20.100Z",
                "price": 5.21,
                "size": 100,
                "conditions": ("@",),
                "tape": "C",
            }
        )
        outcome = simulate_trade_management(
            plan(),
            fill_time=pd.Timestamp("2026-07-10T12:00:11Z"),
            fill_price=5.00,
            bars=bars,
            trades=trades,
            cell="half-2r-breakeven-first-red-10s",
        )
        self.assertFalse(outcome.target_touched)
        self.assertEqual(len(outcome.legs), 1)
        self.assertEqual(outcome.legs[0].quantity_fraction, 1.0)
        self.assertEqual(outcome.legs[0].reason, ManagementExitReason.FIRST_RED_CANDLE)

    def test_unresolved_runner_is_not_liquidated_at_end_of_data(self):
        bars = bar_frame(
            [
                {
                    "timestamp": "2026-07-10T12:00:00Z",
                    "open": 4.95,
                    "close": 5.00,
                },
                {
                    "timestamp": "2026-07-10T12:01:00Z",
                    "open": 5.00,
                    "close": 5.10,
                },
            ]
        )
        trades = base_fill_and_future(
            {
                "timestamp": "2026-07-10T12:00:30Z",
                "price": 5.15,
                "size": 100,
                "conditions": ("@",),
                "tape": "C",
            }
        )
        outcome = simulate_trade_management(
            plan(),
            fill_time=pd.Timestamp("2026-07-10T12:00:11Z"),
            fill_price=5.00,
            bars=bars,
            trades=trades,
            cell="full-first-red-1m",
        )
        self.assertEqual(outcome.status, "filled_open")
        self.assertEqual(outcome.remaining_fraction, 1.0)
        self.assertEqual(outcome.legs, ())

    def test_frozen_fill_must_be_present_in_execution_path(self):
        bars = bar_frame(
            [{"timestamp": "2026-07-10T12:00:10Z", "open": 5.0, "close": 5.1}]
        )
        trades = trade_frame(
            [
                {
                    "timestamp": "2026-07-10T12:00:12Z",
                    "price": 5.01,
                    "size": 100,
                    "conditions": ("@",),
                    "tape": "C",
                }
            ]
        )
        with self.assertRaisesRegex(ValueError, "fill timestamp"):
            simulate_trade_management(
                plan(),
                fill_time=pd.Timestamp("2026-07-10T12:00:11Z"),
                fill_price=5.00,
                bars=bars,
                trades=trades,
                cell="full-first-red-10s",
            )


if __name__ == "__main__":
    unittest.main()
