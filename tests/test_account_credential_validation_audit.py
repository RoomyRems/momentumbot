import json
import unittest
from pathlib import Path

from momentumbot.research.microstructure_contract import canonical_fingerprint


ROOT = Path(__file__).resolve().parents[1]
CREDENTIAL_SUCCESS_AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "account-credential-validation-v0.1-run-32318197220-success-2026-08-20.json"
)


class AccountCredentialValidationAuditTests(unittest.TestCase):
    def test_permanent_success_audit_is_sanitized_and_hash_bound(self):
        audit = json.loads(CREDENTIAL_SUCCESS_AUDIT.read_text(encoding="utf-8"))
        claimed = audit["content_sha256"]
        unsigned = {
            key: value for key, value in audit.items() if key != "content_sha256"
        }
        self.assertEqual(canonical_fingerprint(unsigned), claimed)
        self.assertEqual(audit["github_source"]["workflow_run_id"], "32318197220")
        self.assertEqual(audit["artifact"]["artifact_id"], "9388847244")
        self.assertEqual(
            audit["artifact"]["zip_sha256"],
            "25d9e07f3820611c8aed5dd4cc88b3497b97ad1839d23f51c8d7b8c7031712d3",
        )
        self.assertTrue(audit["decision"]["paper_account_credential_gate_passed"])
        self.assertFalse(audit["decision"]["registered_session_snapshot_created"])
        rendered = json.dumps(audit, sort_keys=True)
        for prohibited in (
            "APCA-API-KEY-ID",
            "APCA-API-SECRET-KEY",
            "alpaca-paper-sha256:",
        ):
            self.assertNotIn(prohibited, rendered)


if __name__ == "__main__":
    unittest.main()
