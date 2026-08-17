import copy
import json
import tempfile
import unittest
from pathlib import Path

from momentumbot.research.discretion_context import load_discretion_context_contract
from momentumbot.research.discretion_evidence import (
    evidence_counts,
    load_discretion_evidence_audit,
    validate_discretion_evidence_audit,
)


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "research" / "data-audits" / "discretion-evidence-coverage-v0.1.json"
CONTRACT = ROOT / "research" / "strategy" / "discretion-context-v0.1.json"
BENCHMARK_ROOT = ROOT / "research" / "benchmarks"


class DiscretionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.contract = load_discretion_context_contract(CONTRACT)
        required_benchmarks = [
            "2025-04-03-tivc.json",
            "2025-04-21-upxi.json",
            "2025-09-09-mma.json",
            "2025-09-09-youl.json",
            "2026-03-27-artl.json",
            "2026-04-22-agpu.json",
            "2026-05-18-labt.json",
            "2026-06-10-dsy.json",
            "2026-06-26-zevai.json",
            "2026-07-09-vrax.json",
        ]
        benchmark_root = (
            BENCHMARK_ROOT
            if all((BENCHMARK_ROOT / filename).exists() for filename in required_benchmarks)
            else None
        )
        self.payload = load_discretion_evidence_audit(
            AUDIT,
            benchmark_root=benchmark_root,
            context_contract=self.contract,
        )

    def test_frozen_audit_uses_all_context_domains_and_ten_benchmarks(self):
        self.assertEqual(
            evidence_counts(self.payload),
            {
                "technical_setup_and_trigger": 6,
                "catalyst_substance": 4,
                "attention_leadership": 2,
                "daily_chart_context": 4,
                "market_regime_and_theme": 2,
                "liquidity_and_fill_quality": 2,
                "level2_and_tape": 2,
                "session_state_and_aggression": 2,
            },
        )

    def test_artl_correction_and_zevai_catalyst_evidence_are_bound(self):
        domains = {domain["domain_id"]: domain for domain in self.payload["domains"]}
        technical_artl = next(
            row
            for row in domains["technical_setup_and_trigger"]["evidence_rows"]
            if row["symbol"] == "ARTL"
        )
        self.assertIn(
            "/corrected_observed_human_behavior/setup_type",
            technical_artl["evidence_paths"],
        )
        catalyst_symbols = {
            row["symbol"] for row in domains["catalyst_substance"]["evidence_rows"]
        }
        self.assertTrue({"ARTL", "ZEVAI"}.issubset(catalyst_symbols))
        request = next(
            row
            for row in self.payload["targeted_source_requests"]
            if row["request_id"] == "catalyst-substance-segments"
        )
        self.assertEqual(request["status"], "fulfilled_2026-08-17")
        self.assertEqual(len(self.payload["source_scope"]["benchmark_files"]), 10)
        self.assertTrue(
            all(
                domain["sufficiency"]["pre_entry_timestamp_verified_count"] == 0
                for domain in self.payload["domains"]
            )
        )

    def test_runtime_or_policy_use_fails_closed(self):
        changed = copy.deepcopy(self.payload)
        changed["runtime_strategy_effect"] = "candidate_filter"
        with self.assertRaisesRegex(ValueError, "must not affect runtime"):
            validate_discretion_evidence_audit(changed)

    def test_claimed_complete_alternative_set_is_rejected(self):
        changed = copy.deepcopy(self.payload)
        changed["domains"][0]["evidence_rows"][0]["alternative_candidate_set_complete"] = True
        with self.assertRaisesRegex(ValueError, "do not contain complete alternative"):
            validate_discretion_evidence_audit(changed)

    def test_context_domain_order_is_bound_to_contract(self):
        changed = copy.deepcopy(self.payload)
        changed["domains"][0], changed["domains"][1] = changed["domains"][1], changed["domains"][0]
        with self.assertRaisesRegex(ValueError, "must match contract order"):
            validate_discretion_evidence_audit(changed, context_contract=self.contract)

    def test_benchmark_identity_and_evidence_paths_are_verified(self):
        benchmark = {
            "benchmark_id": "b1",
            "symbol": "AAA",
            "source": {"video_id": "v1", "evidence_type": "recap"},
            "observed_human_behavior": {"reason": True},
        }
        minimal_contract = {
            "contract_id": "c1",
            "domains": [{"domain_id": "d1"}],
        }
        minimal = {
            "schema_version": 1,
            "audit_id": "ross-discretion-evidence-coverage-v0.1",
            "artifact_type": "retrospective_discretion_evidence_coverage_audit",
            "context_contract_id": "c1",
            "runtime_strategy_effect": "none",
            "runtime_eligible": False,
            "policy_promotion_eligible": False,
            "full_imitation_claim_eligible": False,
            "source_scope": {"benchmark_files": ["b.json"]},
            "domains": [
                {
                    "domain_id": "d1",
                    "runtime_gate_enabled": False,
                    "evidence_rows": [
                        {
                            "benchmark_file": "b.json",
                            "benchmark_id": "b1",
                            "symbol": "AAA",
                            "source_video_id": "v1",
                            "source_evidence_type": "recap",
                            "context_class": "explicit_retrospective_reason",
                            "runtime_eligible": False,
                            "pre_entry_timestamp_verified": False,
                            "alternative_candidate_set_complete": False,
                            "evidence_paths": ["/observed_human_behavior/reason"],
                            "summary": "Reason recorded.",
                            "limit": "Retrospective only.",
                        }
                    ],
                    "sufficiency": {
                        "evidence_row_count": 1,
                        "explicit_retrospective_reason_count": 1,
                        "pre_entry_timestamp_verified_count": 0,
                        "complete_alternative_candidate_set_count": 0,
                    },
                    "conclusion": "Insufficient.",
                }
            ],
            "targeted_source_requests": [
                {
                    "request_id": "r1",
                    "video_ids": ["v1"],
                    "domain_ids": ["d1"],
                    "needed_segment": "Decision context.",
                    "request_only_if_existing_evidence_is_insufficient": True,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b.json").write_text(json.dumps(benchmark), encoding="utf-8")
            validate_discretion_evidence_audit(
                minimal,
                benchmark_root=root,
                context_contract=minimal_contract,
            )
            changed = copy.deepcopy(minimal)
            changed["domains"][0]["evidence_rows"][0]["evidence_paths"] = [
                "/observed_human_behavior/missing"
            ]
            with self.assertRaisesRegex(ValueError, "evidence path does not exist"):
                validate_discretion_evidence_audit(
                    changed,
                    benchmark_root=root,
                    context_contract=minimal_contract,
                )


if __name__ == "__main__":
    unittest.main()
