from __future__ import annotations

import json
from pathlib import Path
import unittest

from momentumbot.causal_scanner_snapshot import (
    RANK_MINUTE_ADJUSTMENT,
    RANK_PREVIOUS_CLOSE_ADJUSTMENT,
)
from momentumbot.identity_resolved_universe import json_fingerprint


ROOT = Path(__file__).resolve().parents[1]
SUCCESS = ROOT / "research/data-audits/sealed-historical-source-acquisition-v0.2-run-33389380992-success-2026-08-31.json"
FAILURE = ROOT / "research/data-audits/sealed-historical-scanner-runtime-v0.1-normalization-failure-2026-08-31.json"


def _load(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    claimed = payload.pop("content_sha256")
    if claimed != json_fingerprint(payload):
        raise AssertionError(f"audit fingerprint mismatch: {path}")
    payload["content_sha256"] = claimed
    return payload


class SealedHistoricalScannerRuntimeFailureTests(unittest.TestCase):
    def test_source_success_is_exact_but_does_not_claim_runtime_validity(self):
        payload = _load(SUCCESS)
        self.assertTrue(payload["result"]["source_acquisition_gate_passed"])
        self.assertFalse(
            payload["authority_boundary"]["historical_runtime_validity_established"]
        )
        self.assertEqual(payload["workflow"]["run_id"], 33389380992)
        self.assertEqual(payload["independent_verification"]["artifact_file_count"], 738)

    def test_runtime_failure_preserves_zero_as_invalid_not_strategy_evidence(self):
        payload = _load(FAILURE)
        result = payload["diagnostic_result"]
        self.assertEqual(result["selected_session_count"], 30)
        self.assertEqual(result["scanner_row_count"], 66902)
        self.assertEqual(result["small_account_rank_qualified_activation_count"], 0)
        self.assertEqual(result["small_account_non_rank_pillar_pass_session_count"], 25)
        interpretation = payload["failure_interpretation"]
        self.assertFalse(interpretation["small_account_zero_is_a_valid_zero_opportunity_result"])
        self.assertFalse(interpretation["provisional_activations_frozen_for_downstream_use"])
        self.assertFalse(payload["next_gate"]["candidate_bound_micro_acquisition_allowed"])

    def test_failure_parent_records_the_exact_mixed_adjustment_basis(self):
        self.assertEqual(RANK_PREVIOUS_CLOSE_ADJUSTMENT, "split")
        self.assertEqual(RANK_MINUTE_ADJUSTMENT, "raw")
        payload = _load(FAILURE)
        evidence = payload["mixed_basis_evidence"]
        self.assertEqual(evidence["frozen_previous_close_adjustment"], "split")
        self.assertEqual(evidence["frozen_intraday_adjustment"], "raw")
        ratios = {row["symbol"]: row["ratio"] for row in evidence["representative_first_raw_close_to_stored_previous_close_ratios"]}
        self.assertAlmostEqual(ratios["NFLX"], 10.0, delta=0.02)
        self.assertAlmostEqual(ratios["ORLY"], 15.0, delta=0.3)
        self.assertAlmostEqual(ratios["BKNG"], 25.0, delta=0.3)


if __name__ == "__main__":
    unittest.main()
