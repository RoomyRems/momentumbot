import unittest

from momentumbot.micro_policy import micro_v0_1_manifest, micro_v0_1_policy
from momentumbot.micro_setup import canonical_micro_setup_policy


class FrozenMicroPolicyTests(unittest.TestCase):
    def test_micro_v0_1_exact_contract(self):
        policy = micro_v0_1_policy()
        canonical = canonical_micro_setup_policy()
        self.assertEqual(policy.policy_id, "micro-v0.1")
        self.assertEqual(policy.status, "frozen_research_baseline")
        self.assertEqual(policy.micro_bar_interval_seconds, 10)
        self.assertEqual(
            policy.trigger_mode,
            "first_new_high_over_previous_completed_micro_bar",
        )
        self.assertEqual(policy.stop_mode, "pullback_low")
        self.assertEqual(policy.support_availability, "completed_minute_only")
        self.assertEqual(policy.setup, canonical)
        self.assertEqual(policy.setup.max_pullback_bars, 5)
        self.assertEqual(policy.setup.impulse_lookback_bars, 5)
        self.assertEqual(policy.setup.max_retrace_fraction, 0.50)
        self.assertEqual(policy.setup.max_peak_upper_wick_fraction, 0.50)
        self.assertTrue(policy.setup.require_lower_pullback_volume)
        self.assertTrue(policy.setup.require_vwap_support)
        self.assertTrue(policy.setup.require_ema9_support)
        self.assertEqual(policy.setup.tick_size, 0.01)

    def test_manifest_is_stable_and_fingerprinted(self):
        first = micro_v0_1_manifest()
        second = micro_v0_1_manifest()
        self.assertEqual(first, second)
        self.assertEqual(len(first["fingerprint"]), 64)
        self.assertEqual(first["policy_id"], "micro-v0.1")
        self.assertEqual(first["setup"]["name"], "canonical-micro-current-2026")


if __name__ == "__main__":
    unittest.main()
