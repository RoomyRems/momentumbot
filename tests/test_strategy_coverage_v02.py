from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from momentumbot.research.rulebook import load_rulebook
from momentumbot.research.strategy_coverage import canonical_fingerprint
from momentumbot.research.strategy_coverage_v02 import (
    ALLOWED_DOMAIN_UPDATES,
    CONTENT_SHA256,
    MATRIX_ID,
    load_strategy_coverage_v02_delta,
    resolve_strategy_coverage_v02,
    validate_strategy_coverage_v02_delta,
)


ROOT = Path(__file__).resolve().parents[1]
DELTA = ROOT / "research" / "strategy" / "strategy-discretion-coverage-v0.2.json"
PARENT = ROOT / "research" / "strategy" / "strategy-discretion-coverage-v0.1.json"
RULEBOOK = ROOT / "research" / "rules" / "current_rules.json"
AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "strategy-discretion-coverage-v0.2-2026-08-21.json"
)


class StrategyCoverageV02Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rules = load_rulebook(RULEBOOK)
        cls.delta = load_strategy_coverage_v02_delta(DELTA)
        cls.resolved = resolve_strategy_coverage_v02(
            cls.delta,
            parent_path=PARENT,
            rules=cls.rules,
            repository_root=ROOT,
        )

    def test_delta_is_hash_bound_and_runtime_inert(self):
        self.assertEqual(self.delta["content_sha256"], CONTENT_SHA256)
        unsigned = {
            key: value for key, value in self.delta.items() if key != "content_sha256"
        }
        self.assertEqual(canonical_fingerprint(unsigned), CONTENT_SHA256)
        self.assertEqual(self.delta["runtime_strategy_effect"], "none")
        self.assertFalse(self.delta["policy_promotion_eligible"])
        self.assertFalse(self.delta["profitability_claim_eligible"])

    def test_only_registered_domains_change_from_frozen_parent(self):
        parent = json.loads(PARENT.read_text(encoding="utf-8"))
        parent_by_id = {row["domain_id"]: row for row in parent["domains"]}
        resolved_by_id = {row["domain_id"]: row for row in self.resolved["domains"]}
        changed = {
            domain_id
            for domain_id in parent_by_id
            if parent_by_id[domain_id] != resolved_by_id[domain_id]
        }
        self.assertEqual(changed, ALLOWED_DOMAIN_UPDATES)
        self.assertEqual(len(self.resolved["domains"]), 25)
        cited = [
            rule_id
            for domain in self.resolved["domains"]
            for rule_id in domain["evidence_rule_ids"]
        ]
        self.assertEqual(len(cited), 36)
        self.assertEqual(len(cited), len(set(cited)))

    def test_engineering_progress_is_partial_and_research_only(self):
        by_id = {row["domain_id"]: row for row in self.resolved["domains"]}
        for domain_id in (
            "setup.hidden-buyer-anticipation",
            "microstructure.hidden-seller",
            "execution.realistic-broker",
            "data.level2-and-tape",
        ):
            self.assertEqual(by_id[domain_id]["coverage_status"], "partial_deterministic")
            self.assertEqual(by_id[domain_id]["current_authority"], "research_only")
        self.assertIn(
            "consolidated multi-venue depth",
            by_id["data.level2-and-tape"]["missing_capabilities"],
        )
        self.assertIn(
            "runtime authority",
            by_id["setup.hidden-buyer-anticipation"]["claim_boundary"],
        )

    def test_resolved_summary_recomputes_without_overclaim(self):
        self.assertEqual(self.resolved["matrix_id"], MATRIX_ID)
        self.assertEqual(
            self.resolved["coverage_summary"]["status_counts"],
            {
                "implemented_frozen": 1,
                "implemented_unrun": 4,
                "missing": 2,
                "partial_deterministic": 10,
                "partial_shadow": 7,
                "research_guard": 1,
            },
        )

    def test_unregistered_domain_or_authority_overclaim_fails_closed(self):
        changed = copy.deepcopy(self.delta)
        changed["domain_updates"][0]["domain_id"] = "setup.micro-pullback"
        changed["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in changed.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "content hash|unregistered domain"):
            validate_strategy_coverage_v02_delta(changed)

        changed = copy.deepcopy(self.delta)
        changed["exact_ross_replication_claim_eligible"] = True
        changed["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in changed.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "exact_ross"):
            validate_strategy_coverage_v02_delta(changed)

    def test_audit_binds_delta_and_supporting_files(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        claimed = audit["content_sha256"]
        unsigned = {
            key: value for key, value in audit.items() if key != "content_sha256"
        }
        self.assertEqual(canonical_fingerprint(unsigned), claimed)
        self.assertEqual(audit["delta"]["content_sha256"], CONTENT_SHA256)
        self.assertEqual(
            audit["resolved_matrix"]["content_sha256"],
            self.resolved["content_sha256"],
        )
        for row in audit["bound_files"]:
            self.assertEqual(
                hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest(),
                row["file_sha256"],
            )


if __name__ == "__main__":
    unittest.main()
