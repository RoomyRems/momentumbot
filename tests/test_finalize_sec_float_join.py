import importlib.util
import unittest
from pathlib import Path

import pandas as pd

spec = importlib.util.spec_from_file_location(
    "finalize_sec_float_join", Path("scripts/finalize_sec_float_join.py")
)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

apply_manual_overrides = module.apply_manual_overrides


class FinalizeSecFloatJoinTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame(
            [
                {
                    "symbol": "PASS",
                    "method": "unknown_missing_public_float",
                    "estimated_float_shares": None,
                    "current_outstanding_target_basis": 20_000_000,
                    "float_pillar_pass": None,
                    "notes": "base note",
                },
                {
                    "symbol": "FAIL",
                    "method": "unknown_missing_public_float",
                    "estimated_float_shares": None,
                    "current_outstanding_target_basis": None,
                    "float_pillar_pass": None,
                    "notes": "",
                },
                {
                    "symbol": "UNKNOWN",
                    "method": "unknown_missing_public_float",
                    "estimated_float_shares": None,
                    "current_outstanding_target_basis": None,
                    "float_pillar_pass": None,
                    "notes": "",
                },
            ]
        )
        self.compact = {
            "candidates": [
                {"symbol": "PASS", "current_outstanding": {"available_at": "2026-05-01T00:00:00+00:00"}},
                {"symbol": "FAIL"},
                {"symbol": "UNKNOWN"},
            ]
        }

    def test_manual_bounds_produce_deterministic_pass_fail_and_unknown(self):
        manual = {
            "overrides": {
                "PASS": {
                    "float_pillar_pass": True,
                    "bound_type": "upper",
                    "bound_shares": 1_000_000,
                    "method": "manual_pass",
                    "available_at": "2026-06-01T00:00:00+00:00",
                    "notes": "manual pass note",
                },
                "FAIL": {
                    "float_pillar_pass": False,
                    "bound_type": "lower",
                    "bound_shares": 20_000_000,
                    "method": "manual_fail",
                    "available_at": "2026-06-02T00:00:00+00:00",
                    "notes": "manual fail note",
                },
                "UNKNOWN": {
                    "float_pillar_pass": None,
                    "bound_type": None,
                    "bound_shares": None,
                    "method": "manual_unknown",
                    "available_at": "2026-06-03T00:00:00+00:00",
                    "notes": "manual unknown note",
                },
            }
        }
        result = apply_manual_overrides(self.frame, compact=self.compact, manual=manual).set_index("symbol")
        self.assertEqual(int(result.loc["PASS", "estimated_float_shares"]), 1_000_000)
        self.assertEqual(result.loc["PASS", "float_pillar_pass"], True)
        self.assertEqual(result.loc["FAIL", "float_pillar_pass"], False)
        self.assertTrue(pd.isna(result.loc["UNKNOWN", "float_pillar_pass"]))
        self.assertIn("manual pass note", result.loc["PASS", "notes"])

    def test_invalid_manual_pass_bound_is_rejected(self):
        manual = {
            "overrides": {
                "PASS": {
                    "float_pillar_pass": True,
                    "bound_type": "upper",
                    "bound_shares": 10_000_000,
                    "method": "bad",
                }
            }
        }
        with self.assertRaisesRegex(ValueError, "upper bound below 10M"):
            apply_manual_overrides(self.frame, compact=self.compact, manual=manual)


if __name__ == "__main__":
    unittest.main()
