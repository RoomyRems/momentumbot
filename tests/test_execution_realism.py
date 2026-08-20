import copy
import hashlib
import json
import unittest
from decimal import Decimal
from pathlib import Path

from momentumbot.research.execution_realism import (
    BASELINE_CONSERVATIVE_POLICY,
    BASELINE_LIMIT_OFFSET_TICKS,
    CONTRACT_CONTENT_SHA256,
    SELECTED_MANAGEMENT_CELL,
    STRESS_LIMIT_OFFSET_TICKS,
    STRESS_POLICY,
    EquityFeeSchedule,
    ExecutedEquityTrade,
    ExecutionStatus,
    MarketableLimitOrder,
    OrderSide,
    TopOfBookEvent,
    aggregate_daily_equity_fees,
    load_prospective_execution_contract,
    marketable_limit_price,
    simulate_marketable_limit_order,
    validate_prospective_execution_contract,
)
from momentumbot.research.microstructure_contract import canonical_fingerprint


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research" / "strategy" / "prospective-management-execution-v0.1.json"
AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "prospective-management-execution-v0.1-2026-08-20.json"
)
DECISION = 1_800_000_000_000_000_000
ARRIVAL = DECISION + 100_000_000


def quote(
    timestamp: int,
    *,
    sequence: int = 1,
    bid: str = "4.98",
    bid_size: int = 1000,
    ask: str = "5.00",
    ask_size: int = 1000,
    halted: bool = False,
) -> TopOfBookEvent:
    return TopOfBookEvent(
        symbol="ROSS",
        ts_recv_ns=timestamp,
        sequence=sequence,
        bid_price=Decimal(bid),
        bid_size=bid_size,
        ask_price=Decimal(ask),
        ask_size=ask_size,
        halted=halted,
    )


def order(
    *,
    side: OrderSide = OrderSide.BUY,
    quantity: int = 100,
    limit: str = "5.05",
) -> MarketableLimitOrder:
    return MarketableLimitOrder(
        order_id="research-order-1",
        symbol="ROSS",
        side=side,
        quantity=quantity,
        decision_ts_ns=DECISION,
        limit_price=Decimal(limit),
    )


class ProspectiveExecutionContractTests(unittest.TestCase):
    def test_contract_is_hash_bound_source_selected_and_non_authoritative(self):
        payload = load_prospective_execution_contract(CONTRACT)
        self.assertEqual(payload["content_sha256"], CONTRACT_CONTENT_SHA256)
        self.assertEqual(SELECTED_MANAGEMENT_CELL, "half-2r-breakeven-first-red-1m")
        management = payload["management_rule"]
        self.assertFalse(management["selection_used_july_pnl"])
        self.assertIn("not being the least-negative July", management["selection_basis"][2])
        self.assertFalse(payload["best_scenario_selection_allowed"])
        self.assertFalse(payload["authority_boundary"]["paper_orders_submitted"])
        self.assertFalse(payload["authority_boundary"]["portfolio_backtest_completed"])

    def test_contract_mutation_fails_closed(self):
        payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
        changed = copy.deepcopy(payload)
        changed["management_rule"]["selected_cell_id"] = "best-july-cell"
        with self.assertRaisesRegex(ValueError, "content hash"):
            validate_prospective_execution_contract(changed)

        changed = copy.deepcopy(payload)
        changed["content_sha256"] = CONTRACT_CONTENT_SHA256
        changed["execution_scenarios"][0]["decision_to_arrival_ms"] = 0
        with self.assertRaisesRegex(ValueError, "content hash"):
            validate_prospective_execution_contract(changed)

    def test_fixed_scenarios_are_conservative_and_stress_not_candidates(self):
        self.assertEqual(BASELINE_CONSERVATIVE_POLICY.decision_to_arrival_ms, 100)
        self.assertEqual(BASELINE_CONSERVATIVE_POLICY.displayed_size_participation, Decimal("0.25"))
        self.assertEqual(BASELINE_LIMIT_OFFSET_TICKS, 5)
        self.assertEqual(STRESS_POLICY.decision_to_arrival_ms, 250)
        self.assertEqual(STRESS_POLICY.displayed_size_participation, Decimal("0.10"))
        self.assertEqual(STRESS_LIMIT_OFFSET_TICKS, 2)

    def test_registration_audit_binds_child_without_runtime_authority(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
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
        self.assertFalse(audit["authority_boundary"]["market_runtime_created"])
        self.assertFalse(audit["authority_boundary"]["databento_download_performed"])
        self.assertFalse(audit["authority_boundary"]["broker_order_submitted"])


class MarketableLimitExecutionTests(unittest.TestCase):
    def test_fresh_arrival_quote_fills_buy_at_ask_and_records_spread(self):
        outcome = simulate_marketable_limit_order(
            order(),
            [quote(ARRIVAL - 50_000_000)],
            BASELINE_CONSERVATIVE_POLICY,
        )
        self.assertEqual(outcome.status, ExecutionStatus.FILLED)
        self.assertEqual(outcome.filled_quantity, 100)
        self.assertEqual(outcome.fill_ts_ns, ARRIVAL)
        self.assertEqual(outcome.fill_price, Decimal("5.00"))
        self.assertEqual(outcome.spread, Decimal("0.02"))
        self.assertEqual(outcome.displayed_contra_size, 1000)

    def test_partial_fill_haircuts_first_state_once_and_cancels_remainder(self):
        outcome = simulate_marketable_limit_order(
            order(quantity=100),
            [
                quote(ARRIVAL - 10_000_000, ask_size=200),
                quote(
                    ARRIVAL + 10_000_000,
                    sequence=2,
                    ask_size=10_000,
                ),
            ],
            BASELINE_CONSERVATIVE_POLICY,
        )
        self.assertEqual(outcome.status, ExecutionStatus.PARTIALLY_FILLED_CANCELLED)
        self.assertEqual(outcome.filled_quantity, 50)
        self.assertEqual(outcome.unfilled_quantity, 50)
        self.assertEqual(outcome.quote_ts_recv_ns, ARRIVAL - 10_000_000)

    def test_stale_quote_fails_unavailable_instead_of_inventing_fill(self):
        outcome = simulate_marketable_limit_order(
            order(),
            [quote(ARRIVAL - 100_000_001)],
            BASELINE_CONSERVATIVE_POLICY,
        )
        self.assertEqual(outcome.status, ExecutionStatus.UNAVAILABLE_NO_FRESH_QUOTE)
        self.assertEqual(outcome.filled_quantity, 0)
        self.assertIsNone(outcome.fill_price)

    def test_non_marketable_limit_cancels_and_halt_can_resume_before_ack(self):
        cancelled = simulate_marketable_limit_order(
            order(limit="4.99"),
            [quote(ARRIVAL - 1)],
            BASELINE_CONSERVATIVE_POLICY,
        )
        self.assertEqual(cancelled.status, ExecutionStatus.CANCELLED_UNFILLED)

        halted = simulate_marketable_limit_order(
            order(),
            [quote(ARRIVAL - 1, halted=True)],
            BASELINE_CONSERVATIVE_POLICY,
        )
        self.assertEqual(halted.status, ExecutionStatus.HALTED_CANCELLED)

        resumed = simulate_marketable_limit_order(
            order(),
            [
                quote(ARRIVAL - 1, halted=True),
                quote(ARRIVAL + 1, sequence=2, halted=False),
            ],
            BASELINE_CONSERVATIVE_POLICY,
        )
        self.assertEqual(resumed.status, ExecutionStatus.FILLED)
        self.assertEqual(resumed.fill_ts_ns, ARRIVAL + 1)

    def test_sell_crosses_bid_and_limit_offset_is_directional(self):
        sell = order(side=OrderSide.SELL, quantity=20, limit="4.95")
        outcome = simulate_marketable_limit_order(
            sell,
            [quote(ARRIVAL - 1, bid_size=100)],
            BASELINE_CONSERVATIVE_POLICY,
        )
        self.assertEqual(outcome.status, ExecutionStatus.FILLED)
        self.assertEqual(outcome.fill_price, Decimal("4.98"))
        self.assertEqual(
            marketable_limit_price(
                Decimal("5.00"),
                side=OrderSide.BUY,
                offset_ticks=5,
            ),
            Decimal("5.05"),
        )
        self.assertEqual(
            marketable_limit_price(
                Decimal("4.98"),
                side=OrderSide.SELL,
                offset_ticks=2,
            ),
            Decimal("4.96"),
        )

    def test_invalid_book_or_out_of_order_stream_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "non-crossed"):
            quote(ARRIVAL, bid="5.00", ask="5.00")
        with self.assertRaisesRegex(ValueError, "strictly ordered"):
            simulate_marketable_limit_order(
                order(),
                [quote(ARRIVAL, sequence=2), quote(ARRIVAL, sequence=1)],
                BASELINE_CONSERVATIVE_POLICY,
            )
        with self.assertRaisesRegex(ValueError, "side must be buy or sell"):
            MarketableLimitOrder(
                order_id="invalid-side",
                symbol="ROSS",
                side="hold",  # type: ignore[arg-type]
                quantity=1,
                decision_ts_ns=DECISION,
                limit_price=Decimal("5"),
            )


class EquityFeeTests(unittest.TestCase):
    def test_fee_types_aggregate_daily_then_round_up_separately(self):
        fees = aggregate_daily_equity_fees(
            [
                ExecutedEquityTrade(OrderSide.BUY, 100, Decimal("10")),
                ExecutedEquityTrade(OrderSide.SELL, 100, Decimal("10")),
            ]
        )
        self.assertEqual(fees.sec_exact, Decimal("0.0206000"))
        self.assertEqual(fees.taf_exact, Decimal("0.019500"))
        self.assertEqual(fees.cat_exact, Decimal("0.000600"))
        self.assertEqual(fees.sec_charged, Decimal("0.03"))
        self.assertEqual(fees.taf_charged, Decimal("0.02"))
        self.assertEqual(fees.cat_charged, Decimal("0.01"))
        self.assertEqual(fees.total_charged, Decimal("0.06"))

    def test_taf_cap_is_per_sell_trade_before_daily_aggregation(self):
        fees = aggregate_daily_equity_fees(
            [
                ExecutedEquityTrade(OrderSide.SELL, 100_000, Decimal("1")),
                ExecutedEquityTrade(OrderSide.SELL, 100, Decimal("1")),
            ],
            EquityFeeSchedule(),
        )
        self.assertEqual(fees.taf_exact, Decimal("9.809500"))
        self.assertEqual(fees.taf_charged, Decimal("9.81"))
        self.assertEqual(fees.commission_charged, Decimal("0.00"))

        with self.assertRaisesRegex(ValueError, "side must be buy or sell"):
            ExecutedEquityTrade("short", 1, Decimal("1"))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
