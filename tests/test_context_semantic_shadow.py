import copy
import hashlib
import json
import unittest
from collections import Counter
from pathlib import Path

from momentumbot.identity_resolved_universe import json_fingerprint
from momentumbot.research.context_assessment import SEMANTIC_AXES, canonical_fingerprint
from momentumbot.research.context_heldout_panel import REGISTERED_DATES
from momentumbot.research.context_semantic_shadow import (
    ARTIFACT_ID,
    FROZEN_PARENT_RUNTIME_CONTENT_SHA256,
    FROZEN_PARENT_ZIP_SHA256,
    FROZEN_SNAPSHOT_RUNTIME_CONTENT_SHA256,
    MODEL_ID,
    RUBRIC_ID,
    compiled_rubric_content_sha256,
    load_compiled_rubric,
    validate_compiled_rubric,
    validate_semantic_date_payload,
    validate_semantic_root_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
RUBRIC = (
    ROOT
    / "research"
    / "strategy"
    / "context-semantic-shadow-compiled-rubric-v0.1.json"
)
ARTIFACT = ROOT / "research" / "frozen" / "context-semantic-shadow-runtime-v0.1"
AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "context-semantic-shadow-v0.1-2026-08-19.json"
)
EXPECTED_RUBRIC_CONTENT_SHA256 = (
    "959256aedcc7ed89c8120b19cd1640547a63eb24fcca359c476117ba679f13d3"
)
EXPECTED_ARTIFACT_CONTENT_SHA256 = (
    "9b3be7a17f29e638b0e1da14b4d050762503bab17c74c3f97e62b99489f25cd4"
)


class ContextSemanticShadowTests(unittest.TestCase):
    def test_rubric_is_frozen_label_blind_and_transparent_about_generation(self):
        rubric = load_compiled_rubric(RUBRIC)
        self.assertEqual(rubric["rubric_id"], RUBRIC_ID)
        self.assertEqual(
            compiled_rubric_content_sha256(rubric),
            EXPECTED_RUBRIC_CONTENT_SHA256,
        )
        generation = rubric["generation_mode"]
        self.assertEqual(generation["authoring_model"], "gpt-5.6-sol-work-mode")
        self.assertFalse(generation["external_model_api_call_per_record"])
        boundary = rubric["knowledge_boundary"]
        self.assertTrue(boundary["uses_only_frozen_snapshot_evidence"])
        for field in (
            "uses_raw_transcripts",
            "uses_recap_inventory",
            "uses_ross_actions",
            "uses_retrospective_labels",
            "uses_trade_outcomes",
            "uses_later_prices",
            "uses_excluded_pilot_to_fit_rubric",
        ):
            self.assertFalse(boundary[field])

    def test_rubric_tamper_cannot_add_authority_or_change_parent(self):
        rubric = load_compiled_rubric(RUBRIC)
        changed = copy.deepcopy(rubric)
        changed["authority"]["order_action"] = "buy"
        with self.assertRaisesRegex(ValueError, "prohibited order_action"):
            validate_compiled_rubric(changed)

        changed = copy.deepcopy(rubric)
        changed["frozen_parent"]["zip_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "ZIP parent changed"):
            validate_compiled_rubric(changed)

    def test_frozen_semantic_artifact_recomputes_and_preserves_boundaries(self):
        manifest = json.loads(
            (ARTIFACT / "manifest.json").read_text(encoding="utf-8")
        )
        validate_semantic_root_manifest(manifest)
        self.assertEqual(manifest["artifact_id"], ARTIFACT_ID)
        self.assertEqual(manifest["content_sha256"], EXPECTED_ARTIFACT_CONTENT_SHA256)
        self.assertEqual(manifest["rubric_content_sha256"], EXPECTED_RUBRIC_CONTENT_SHA256)
        self.assertEqual(manifest["model_id"], MODEL_ID)
        self.assertEqual(manifest["record_count"], 314)
        parent = manifest["source_parent"]
        self.assertEqual(parent["zip_sha256"], FROZEN_PARENT_ZIP_SHA256)
        self.assertEqual(
            parent["runtime_manifest_content_sha256"],
            FROZEN_PARENT_RUNTIME_CONTENT_SHA256,
        )
        self.assertEqual(
            parent["snapshot_runtime_content_sha256"],
            FROZEN_SNAPSHOT_RUNTIME_CONTENT_SHA256,
        )

        total = 0
        state_counts = {axis: Counter() for axis in SEMANTIC_AXES}
        source_snapshots = set()
        for trading_date in REGISTERED_DATES:
            payload = json.loads(
                (ARTIFACT / "dates" / f"{trading_date}.json").read_text(
                    encoding="utf-8"
                )
            )
            validate_semantic_date_payload(payload)
            self.assertEqual(
                payload["content_sha256"],
                manifest["date_content_sha256s"][trading_date],
            )
            total += payload["record_count"]
            for record in payload["records"]:
                claimed = record["assessment_content_sha256"]
                unsigned = {
                    key: value
                    for key, value in record.items()
                    if key != "assessment_content_sha256"
                }
                self.assertEqual(canonical_fingerprint(unsigned), claimed)
                self.assertEqual(record["assessment_origin"], "shadow_ai")
                self.assertEqual(record["runtime_strategy_effect"], "none")
                self.assertEqual(
                    record["model_provenance"]["prompt_content_sha256"],
                    EXPECTED_RUBRIC_CONTENT_SHA256,
                )
                self.assertEqual(
                    record["model_provenance"]["model_id"], MODEL_ID
                )
                self.assertEqual(set(record["axes"]), set(SEMANTIC_AXES))
                self.assertTrue(
                    all(value is None for value in record["prohibited_outputs"].values())
                )
                source_snapshots.add(record["source_snapshot_content_sha256"])
                for axis in SEMANTIC_AXES:
                    row = record["axes"][axis]
                    state_counts[axis][row["state"]] += 1
                    cited = set(row["evidence_ids"])
                    claim_citations = {
                        evidence_id
                        for claim in row["observed_facts"] + row["inferences"]
                        for evidence_id in claim["evidence_ids"]
                    }
                    self.assertEqual(cited, claim_citations)
        self.assertEqual(total, 314)
        self.assertEqual(len(source_snapshots), 314)
        self.assertEqual(
            state_counts["catalyst_substance_specificity"],
            Counter({"assessed": 314}),
        )
        self.assertEqual(
            state_counts["catalyst_credibility_repetition"],
            Counter({"abstained": 314}),
        )
        self.assertEqual(
            state_counts["theme_fit_no_news_acceptance"],
            Counter({"abstained": 314}),
        )
        self.assertEqual(
            state_counts["chart_context_cleanliness"],
            Counter({"assessed": 285, "abstained": 29}),
        )

    def test_manifest_tamper_cannot_enable_promotion(self):
        manifest = json.loads(
            (ARTIFACT / "manifest.json").read_text(encoding="utf-8")
        )
        changed = copy.deepcopy(manifest)
        changed["eligibility"]["policy_promotion_eligible"] = True
        changed["content_sha256"] = json_fingerprint(
            {key: value for key, value in changed.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "policy_promotion_eligible"):
            validate_semantic_root_manifest(changed)

    def test_permanent_audit_binds_frozen_artifact_and_allows_labels_only_after_freeze(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(
            audit["source_checkpoint"]["commit_sha"],
            "a6cde99155583eb0f943a3c5d409fb694d09a22d",
        )
        self.assertEqual(
            audit["frozen_parent"]["zip_sha256"], FROZEN_PARENT_ZIP_SHA256
        )
        self.assertEqual(
            audit["artifact"]["manifest_content_sha256"],
            EXPECTED_ARTIFACT_CONTENT_SHA256,
        )
        self.assertEqual(audit["artifact"]["record_count"], 314)
        self.assertTrue(
            audit["eligibility"][
                "retrospective_source_inventory_may_start_after_this_freeze"
            ]
        )
        self.assertFalse(audit["eligibility"]["policy_promotion_eligible"])
        self.assertFalse(audit["causal_boundary"]["uses_raw_transcripts"])
        self.assertFalse(audit["causal_boundary"]["uses_recap_inventory"])
        self.assertEqual(audit["causal_boundary"]["runtime_strategy_effect"], "none")

    def test_builder_has_no_uploaded_transcript_or_recap_source_path(self):
        script = (ROOT / "scripts" / "build_context_semantic_shadow.py").read_text(
            encoding="utf-8"
        )
        for prohibited in (
            "dataset_daytradewarrior",
            "project_sources",
            "data/transcripts",
            ".jsonl",
        ):
            self.assertNotIn(prohibited, script)

    def test_frozen_files_have_stable_file_hashes(self):
        self.assertEqual(
            hashlib.sha256(RUBRIC.read_bytes()).hexdigest(),
            "cd8308c6e94f1e7425086b07758a676bf69db254c28c7d3700c10e653f2b3da1",
        )
        self.assertEqual(
            hashlib.sha256((ARTIFACT / "manifest.json").read_bytes()).hexdigest(),
            "6efbb111018451d9b9a366c5e6a8d5f34e6f7dc76a0c60937e62f111cd5fc31e",
        )


if __name__ == "__main__":
    unittest.main()
