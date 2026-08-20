import copy
import hashlib
import json
import unittest
from pathlib import Path

from momentumbot.research.rulebook import load_rulebook
from momentumbot.research.strategy_coverage import (
    MATRIX_ID,
    canonical_fingerprint,
    load_strategy_coverage,
    validate_strategy_coverage,
)


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "research" / "strategy" / "strategy-discretion-coverage-v0.1.json"
AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "strategy-discretion-coverage-v0.1-2026-08-19.json"
)
RULEBOOK = ROOT / "research" / "rules" / "current_rules.json"
EXPECTED_CONTENT_SHA256 = (
    "3507642f70bbb8f4551238bc09242dd8c31474b463bf9a4e88f03a7894d97fe3"
)


class StrategyCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = load_rulebook(RULEBOOK)
        cls.payload = json.loads(MATRIX.read_text(encoding="utf-8"))

    def test_matrix_is_hash_bound_and_covers_every_promoted_rule_once(self):
        loaded = load_strategy_coverage(
            MATRIX,
            rules=self.rules,
            repository_root=ROOT,
        )
        self.assertEqual(loaded["matrix_id"], MATRIX_ID)
        claimed = loaded["content_sha256"]
        unsigned = {key: value for key, value in loaded.items() if key != "content_sha256"}
        self.assertEqual(claimed, EXPECTED_CONTENT_SHA256)
        self.assertEqual(canonical_fingerprint(unsigned), EXPECTED_CONTENT_SHA256)
        cited = [
            rule_id
            for domain in loaded["domains"]
            for rule_id in domain["evidence_rule_ids"]
        ]
        self.assertEqual(len(cited), 36)
        self.assertEqual(len(cited), len(set(cited)))

    def test_unknown_rule_and_overclaim_fail_closed(self):
        changed = copy.deepcopy(self.payload)
        changed["domains"][0]["evidence_rule_ids"].append("MB-FAKE-999")
        changed["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in changed.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "coverage rule mapping mismatch"):
            validate_strategy_coverage(changed, rules=self.rules, repository_root=ROOT)

        changed = copy.deepcopy(self.payload)
        changed["exact_ross_replication_claim_eligible"] = True
        changed["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in changed.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "must be false"):
            validate_strategy_coverage(changed, rules=self.rules, repository_root=ROOT)

    def test_missing_implementation_artifact_fails_closed(self):
        changed = copy.deepcopy(self.payload)
        changed["domains"][0]["implemented_artifacts"].append("missing/path.py")
        changed["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in changed.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "does not exist"):
            validate_strategy_coverage(changed, rules=self.rules, repository_root=ROOT)

    def test_permanent_audit_binds_coverage_deliverables(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        claimed = audit["content_sha256"]
        unsigned = {key: value for key, value in audit.items() if key != "content_sha256"}
        self.assertEqual(canonical_fingerprint(unsigned), claimed)
        self.assertEqual(audit["matrix"]["content_sha256"], EXPECTED_CONTENT_SHA256)
        for item in audit["bound_files"]:
            self.assertEqual(
                hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest(),
                item["file_sha256"],
            )


if __name__ == "__main__":
    unittest.main()
