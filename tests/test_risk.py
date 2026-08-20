from __future__ import annotations

import unittest

from momentumbot.models import paper_safe_risk
from momentumbot.risk import SessionRiskState


class RiskTests(unittest.TestCase):
    def test_half_profit_giveback_locks_session(self):
        state = SessionRiskState(100_000, paper_safe_risk())
        state.record_realized(1_000)
        state.record_realized(-500)
        self.assertTrue(state.locked)
        self.assertEqual(state.lock_reason, "profit giveback")

    def test_daily_max_loss_locks_session(self):
        state = SessionRiskState(100_000, paper_safe_risk())
        state.record_realized(-1_000)
        self.assertTrue(state.locked)
        self.assertEqual(state.lock_reason, "daily max loss")

    def test_lock_is_terminal(self):
        state = SessionRiskState(100_000, paper_safe_risk())
        state.lock("manual walk-away")
        state.record_realized(10_000)
        self.assertTrue(state.locked)
        self.assertEqual(state.lock_reason, "manual walk-away")


if __name__ == "__main__":
    unittest.main()
