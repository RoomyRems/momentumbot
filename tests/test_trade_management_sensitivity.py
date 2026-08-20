import copy
import json
import unittest
from pathlib import Path

from momentumbot.research.trade_management_shadow import (
    CONTRACT_CONTENT_SHA256,
    EVIDENCE_AUDIT_CONTENT_SHA256,
)
from momentumbot.research.trade_management_sensitivity import (
    canonical_fingerprint,
    validate_trade_management_registration,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRATION = ROOT / "research" / "strategy" / "trade-management-shadow-v0.1.json"
EVIDENCE = (
    ROOT / "research" / "data-audits" / "trade-management-evidence-v0.1-2026-08-19.json"
)


class TradeManagementSensitivityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registration = json.loads(REGISTRATION.read_text(encoding="utf-8"))
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_registration_and_evidence_are_hash_bound(self):
        self.assertEqual(canonical_fingerprint(self.registration), CONTRACT_CONTENT_SHA256)
        self.assertEqual(
            canonical_fingerprint(self.evidence),
            EVIDENCE_AUDIT_CONTENT_SHA256,
        )
        validate_trade_management_registration(self.registration, self.evidence)

    def test_result_driven_cell_or_status_change_fails_closed(self):
        changed = copy.deepcopy(self.registration)
        changed["registered_cells"][0]["cell_id"] = "july-best-cell"
        with self.assertRaisesRegex(ValueError, "registration content"):
            validate_trade_management_registration(changed, self.evidence)

        changed = copy.deepcopy(self.registration)
        changed["execution_status"]["management_path_execution"] = "completed"
        with self.assertRaisesRegex(ValueError, "registration content"):
            validate_trade_management_registration(changed, self.evidence)


if __name__ == "__main__":
    unittest.main()
