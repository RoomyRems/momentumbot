import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_NAME = "build_sec_float_join"
spec = importlib.util.spec_from_file_location(
    MODULE_NAME, Path("scripts/build_sec_float_join.py")
)
module = importlib.util.module_from_spec(spec)
sys.modules[MODULE_NAME] = module
assert spec.loader is not None
spec.loader.exec_module(module)

BasisObservation = module.BasisObservation
_normalize_shares = module._normalize_shares
_estimate_row = module._estimate_row


class SecFloatJoinTests(unittest.TestCase):
    def test_reverse_split_share_basis_normalization(self):
        basis = BasisObservation("2026-05-13", "2026-05-13", 0.12, 7.20, 1 / 60)
        self.assertEqual(_normalize_shares(590_254_769, basis), 9_837_580)

    def test_missing_public_float_can_pass_only_from_outstanding_upper_bound(self):
        candidate = {
            "symbol": "TEST",
            "cik": "0000000001",
            "first_market_qualified_at": "2026-07-09T11:00:00+00:00",
            "public_float": None,
            "anchor_outstanding": None,
            "current_outstanding": {
                "measure_date": "2026-05-01",
                "shares": 900_000,
                "accession": "x",
            },
        }
        basis = BasisObservation("2026-05-01", "2026-05-01", 1.0, 1.0, 1.0)
        row = _estimate_row(candidate, {"current:2026-05-01": basis})
        self.assertTrue(row.float_pillar_pass)
        self.assertEqual(row.method, "sec_outstanding_shares_upper_bound")

    def test_outstanding_above_limit_without_public_float_remains_unknown(self):
        candidate = {
            "symbol": "TEST",
            "cik": "0000000001",
            "first_market_qualified_at": "2026-07-09T11:00:00+00:00",
            "public_float": None,
            "anchor_outstanding": None,
            "current_outstanding": {
                "measure_date": "2026-05-01",
                "shares": 20_000_000,
                "accession": "x",
            },
        }
        basis = BasisObservation("2026-05-01", "2026-05-01", 1.0, 1.0, 1.0)
        row = _estimate_row(candidate, {"current:2026-05-01": basis})
        self.assertIsNone(row.float_pillar_pass)


if __name__ == "__main__":
    unittest.main()
