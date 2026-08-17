import copy
import unittest
from pathlib import Path

from momentumbot.research.discretion_context import (
    CONTRACT_ID,
    canonical_fingerprint,
    coverage_summary,
    load_discretion_context_contract,
    validate_discretion_context_contract,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research" / "strategy" / "discretion-context-v0.1.json"
KNOWN_RULE_IDS = {
    "MB-CAT-001",
    "MB-ENT-001",
    "MB-ENT-002",
    "MB-ENT-004",
    "MB-ENT-005",
    "MB-ENT-006",
    "MB-EXE-001",
    "MB-EXT-002",
    "MB-MIC-001",
    "MB-POS-001",
    "MB-REG-001",
    "MB-REG-002",
    "MB-RSK-003",
    "MB-RSK-004",
    "MB-RSK-005",
    "MB-SEL-005",
    "MB-SEL-006",
    "MB-SEL-007",
    "MB-SEL-008",
}


def _known_rule_ids():
    manifest = ROOT / "research" / "rules" / "current_rules.json"
    if not manifest.exists():
        return KNOWN_RULE_IDS
    from momentumbot.research.rulebook import load_rulebook

    return {rule.rule_id for rule in load_rulebook(manifest)}


class DiscretionContextTests(unittest.TestCase):
    def setUp(self):
        self.payload = load_discretion_context_contract(
            CONTRACT,
            known_rule_ids=_known_rule_ids(),
        )

    def test_frozen_contract_inventories_the_full_decision_chain(self):
        self.assertEqual(self.payload["contract_id"], CONTRACT_ID)
        self.assertEqual(
            self.payload["parent_policies"]["micro_policy_fingerprint"],
            "49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa",
        )
        self.assertEqual(
            self.payload["parent_policies"]["scanner_policy_fingerprint"],
            "ed21becad10855b4a085b6e05b6feac8f21e4ce511a100b2381522154818f42a",
        )
        self.assertEqual(
            [row["domain_id"] for row in self.payload["domains"]],
            [
                "technical_setup_and_trigger",
                "catalyst_substance",
                "attention_leadership",
                "daily_chart_context",
                "market_regime_and_theme",
                "liquidity_and_fill_quality",
                "level2_and_tape",
                "session_state_and_aggression",
            ],
        )
        self.assertEqual(
            coverage_summary(self.payload),
            {
                "deferred_missing_historical_data": 1,
                "implemented_frozen": 1,
                "not_implemented": 1,
                "partial_feature_only": 1,
                "partial_not_end_to_end": 1,
                "partial_proxy": 3,
            },
        )

    def test_incomplete_context_cannot_be_enabled_as_a_strategy_gate(self):
        changed = copy.deepcopy(self.payload)
        changed["domains"][1]["full_domain_strategy_gate_enabled"] = True
        with self.assertRaisesRegex(ValueError, "must remain fail-closed"):
            validate_discretion_context_contract(changed)

    def test_retrospective_behavior_cannot_enter_runtime_inputs(self):
        changed = copy.deepcopy(self.payload)
        changed["domains"][1]["causal_runtime_inputs"].append("reported fill")
        with self.assertRaisesRegex(ValueError, "retrospective runtime inputs"):
            validate_discretion_context_contract(changed)

    def test_contextual_ai_must_remain_shadow_only(self):
        changed = copy.deepcopy(self.payload)
        changed["domains"][1]["ai_mode"] = "strategy_gate"
        with self.assertRaisesRegex(ValueError, "AI shadow-only"):
            validate_discretion_context_contract(changed)

    def test_unknown_rule_link_fails_closed(self):
        changed = copy.deepcopy(self.payload)
        changed["domains"][0]["linked_rule_ids"].append("MB-ENT-999")
        with self.assertRaisesRegex(ValueError, "unknown rule IDs"):
            validate_discretion_context_contract(changed, known_rule_ids=_known_rule_ids())

    def test_canonical_fingerprint_is_order_independent(self):
        forward = {"b": 2, "a": {"d": 4, "c": 3}}
        reversed_order = {"a": {"c": 3, "d": 4}, "b": 2}
        self.assertEqual(
            canonical_fingerprint(forward),
            canonical_fingerprint(reversed_order),
        )


if __name__ == "__main__":
    unittest.main()
