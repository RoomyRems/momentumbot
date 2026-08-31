from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from momentumbot.research.sealed_historical_walk_forward import (
    BLOCK_SIZE,
    CONTRACT_ID,
    EXPECTED_CORPUS_RECORDS,
    MICRO_POLICY_FINGERPRINT,
    PARENT_RESEARCH_COMMIT,
    TOTAL_SESSION_CELL_COUNT,
    bounded_full_sessions,
    build_corpus_manifest,
    canonical_fingerprint,
    load_json_object,
    scan_prior_research_dates,
    select_registered_dates,
    validate_contract,
    validate_corpus_manifest,
    validate_exclusion_manifest,
    write_json_once,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research/strategy/sealed-historical-walk-forward-v0.1.json"
CORPUS = ROOT / "research/data-audits/sealed-transcript-corpus-v0.1.json"
EXCLUSIONS = (
    ROOT / "research/data-audits/sealed-historical-date-exclusions-v0.1.json"
)
REGISTRATION = (
    ROOT
    / "research/data-audits"
    / "sealed-historical-walk-forward-v0.1-registration-2026-08-31.json"
)
CLOSURE = (
    ROOT
    / "research/data-audits"
    / "prospective-panel-v0.1-closure-2026-08-31.json"
)
VALIDATION_AUDIT = (
    ROOT
    / "research/data-audits"
    / "sealed-historical-walk-forward-v0.1-validation-2026-08-31.json"
)
SCRIPT = ROOT / "scripts/register_sealed_historical_walk_forward.py"


def _rehash(payload: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(payload)
    result.pop("content_sha256", None)
    result["content_sha256"] = canonical_fingerprint(result)
    return result


class SealedHistoricalWalkForwardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load_json_object(CONTRACT)
        cls.corpus = load_json_object(CORPUS)
        cls.exclusions = load_json_object(EXCLUSIONS)

    def test_registered_bundle_is_valid_and_parent_bound(self) -> None:
        validate_contract(self.contract, self.corpus, self.exclusions)
        self.assertEqual(self.contract["contract_id"], CONTRACT_ID)
        self.assertEqual(
            self.contract["frozen_parents"]["research_commit"],
            PARENT_RESEARCH_COMMIT,
        )
        self.assertEqual(
            self.contract["frozen_parents"]["micro_policy_fingerprint"],
            MICRO_POLICY_FINGERPRINT,
        )

    def test_selection_is_exactly_30_full_unseen_sessions(self) -> None:
        selection = self.contract["sampling_contract"]
        selected = selection["selected_dates"]
        excluded = {row["date"] for row in self.exclusions["excluded_dates"]}
        self.assertEqual(len(selected), BLOCK_SIZE)
        self.assertEqual(len(selected), len(set(selected)))
        self.assertTrue(set(selected).isdisjoint(excluded))
        self.assertTrue(set(selected).issubset(set(bounded_full_sessions())))
        self.assertEqual(selected, sorted(selected))
        self.assertFalse(selection["date_replacement_allowed"])
        self.assertFalse(selection["selection_uses_transcript_record_values"])

    def test_selection_is_recomputed_from_only_frozen_inputs(self) -> None:
        self.assertEqual(
            self.contract["sampling_contract"],
            select_registered_dates(self.corpus, self.exclusions),
        )
        seed_inputs = self.contract["sampling_contract"]["seed_inputs"]
        self.assertEqual(set(seed_inputs), {
            "calendar_id",
            "contract_id",
            "corpus_manifest_content_sha256",
            "exclusion_manifest_content_sha256",
            "micro_policy_fingerprint",
        })

    def test_runtime_registers_all_360_cells_without_best_cell_selection(self) -> None:
        runtime = self.contract["runtime_panel"]
        self.assertEqual(runtime["total_session_cell_count"], TOTAL_SESSION_CELL_COUNT)
        self.assertEqual(TOTAL_SESSION_CELL_COUNT, 360)
        self.assertFalse(runtime["account_reset_between_dates"])
        self.assertFalse(runtime["cells_may_be_selected_or_ranked"])
        self.assertFalse(
            self.contract["evaluation_contract"]["best_cell_selection_allowed"]
        )

    def test_corpus_manifest_commits_to_all_records_without_leaking_values(self) -> None:
        validate_corpus_manifest(self.corpus)
        self.assertEqual(self.corpus["part_count"], 8)
        self.assertEqual(self.corpus["record_count"], EXPECTED_CORPUS_RECORDS)
        serialized = json.dumps(self.corpus)
        for forbidden_value in ("SECRET TITLE", "SECRET CAPTION", "ROSS TRADE"):
            self.assertNotIn(forbidden_value, serialized)
        self.assertFalse(self.corpus["record_values_decoded"])
        self.assertFalse(self.corpus["record_values_persisted"])

    def test_structural_manifest_builder_never_emits_record_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "dataset-part-1.json"
            second = root / "dataset-part-2.jsonl"
            first.write_text(
                '[{"title":"SECRET TITLE","captions":"SECRET CAPTION"}]\n',
                encoding="utf-8",
            )
            second.write_text(
                '{"title":"ROSS TRADE","captions":"VALUE { WITH } BRACES"}\n'
                '{"title":"SECOND","captions":"escaped \\\" quote"}',
                encoding="utf-8",
            )
            manifest = build_corpus_manifest(
                [second, first], expected_parts=(1, 2), expected_records=3
            )
            serialized = json.dumps(manifest)
            self.assertNotIn("SECRET TITLE", serialized)
            self.assertNotIn("SECRET CAPTION", serialized)
            self.assertNotIn("ROSS TRADE", serialized)
            self.assertEqual(manifest["record_count"], 3)

    def test_prior_date_scan_is_broad_and_content_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in ("research", "docs/research", "docs/project"):
                (root / relative).mkdir(parents=True)
            (root / "research/a.json").write_text(
                '{"date":"2025-03-04","later":"2028-01-01"}', encoding="utf-8"
            )
            (root / "docs/research/a.md").write_text(
                "Prior case: 2025-03-04 and 2025-05-06.", encoding="utf-8"
            )
            (root / "docs/project/a.md").write_text("No date here.", encoding="utf-8")
            manifest = scan_prior_research_dates(root)
            rows = {row["date"]: row["source_paths"] for row in manifest["excluded_dates"]}
            self.assertEqual(set(rows), {"2025-03-04", "2025-05-06"})
            self.assertEqual(len(rows["2025-03-04"]), 2)
            self.assertEqual(manifest["scanned_file_count"], 3)

    def test_known_seed_and_diagnostic_dates_are_excluded(self) -> None:
        validate_exclusion_manifest(self.exclusions)
        values = {row["date"] for row in self.exclusions["excluded_dates"]}
        self.assertTrue(
            {"2025-04-03", "2025-04-21", "2025-09-09", "2026-06-10"}
            <= values
        )

    def test_rehashed_date_substitution_still_fails(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["sampling_contract"]["selected_dates"][-1] = "2026-06-30"
        changed = _rehash(changed)
        with self.assertRaisesRegex(ValueError, "selected date block differs"):
            validate_contract(changed, self.corpus, self.exclusions)

    def test_rehashed_retrospective_key_still_fails(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["sampling_contract"]["ross_action"] = "participated"
        changed = _rehash(changed)
        with self.assertRaisesRegex(ValueError, "retrospective keys"):
            validate_contract(changed, self.corpus, self.exclusions)

    def test_corpus_or_exclusion_tamper_breaks_parent_binding(self) -> None:
        changed_corpus = copy.deepcopy(self.corpus)
        changed_corpus["parts"][0]["raw_sha256"] = "0" * 64
        changed_corpus = _rehash(changed_corpus)
        with self.assertRaisesRegex(ValueError, "sealed fingerprint"):
            validate_contract(self.contract, changed_corpus, self.exclusions)

        changed_exclusions = copy.deepcopy(self.exclusions)
        changed_exclusions["excluded_dates"][0]["source_paths"].append("research/new.json")
        changed_exclusions["excluded_dates"][0]["source_paths"].sort()
        changed_exclusions = _rehash(changed_exclusions)
        with self.assertRaisesRegex(ValueError, "sealed fingerprint"):
            validate_contract(self.contract, self.corpus, changed_exclusions)

    def test_registration_audit_binds_exact_files_and_zero_authority(self) -> None:
        audit = load_json_object(REGISTRATION)
        body = dict(audit)
        observed = body.pop("content_sha256")
        self.assertEqual(observed, canonical_fingerprint(body))
        for key, path in (
            ("contract", CONTRACT),
            ("corpus_manifest", CORPUS),
            ("exclusion_manifest", EXCLUSIONS),
        ):
            self.assertEqual(
                audit["artifacts"][key]["file_sha256"],
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        self.assertEqual(audit["causal_attestation"]["provider_calls"], 0)
        self.assertEqual(audit["causal_attestation"]["orders"], 0)
        self.assertFalse(audit["authority_boundary"]["provider_call_authorized"])

    def test_prospective_panel_is_terminally_closed_without_false_zeroes(self) -> None:
        closure = load_json_object(CLOSURE)
        body = dict(closure)
        observed = body.pop("content_sha256")
        self.assertEqual(observed, canonical_fingerprint(body))
        self.assertEqual(
            observed,
            "1760d8d05ec0bf10a4f88fa9c2b3ab677fceec44c2151ce1b110c52dbd40a997",
        )
        self.assertEqual(closure["overall_status"], "closed_no_evaluable_sessions")
        self.assertTrue(closure["closure"]["scheduled_wakeups_removed"])
        self.assertTrue(closure["closure"]["validation_only"])
        self.assertEqual(closure["evidence_boundary"]["zero_opportunity_dates_recorded"], 0)
        self.assertEqual(closure["evidence_boundary"]["opportunity_freezes"], 0)
        self.assertEqual(closure["evidence_boundary"]["orders"], 0)
        self.assertEqual(len(closure["dates"]), 5)
        self.assertEqual(len(closure["closure"]["withdrawn_unstarted_dates"]), 5)

    def test_remote_validation_audit_is_exact_and_provider_free(self) -> None:
        audit = load_json_object(VALIDATION_AUDIT)
        body = dict(audit)
        observed = body.pop("content_sha256")
        self.assertEqual(observed, canonical_fingerprint(body))
        self.assertEqual(
            observed,
            "2322eb17ec5ca44f76a2e4fe9551d0b429a3c69d27993fa87ac1c1ddffafdf59",
        )
        self.assertEqual(
            audit["github"]["commit"],
            "81dbb63bc7e797818d586a24801b8a11bb5d394f",
        )
        self.assertEqual(audit["github"]["general_ci"]["conclusion"], "success")
        self.assertEqual(audit["github"]["sealed_validation"]["conclusion"], "success")
        self.assertEqual(audit["local_validation"]["full_tests_passed"], 897)
        self.assertEqual(audit["provider_calls"], 0)
        self.assertFalse(audit["authority_boundary"]["provider_call_authorized"])

    def test_validation_cli_is_provider_free(self) -> None:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src")
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--validate-only"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_write_once_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.json"
            write_json_once(path, {"value": 1})
            with self.assertRaises(FileExistsError):
                write_json_once(path, {"value": 2})

    def test_raw_transcript_files_are_not_committed(self) -> None:
        self.assertEqual(list(ROOT.rglob("dataset_daytradewarrior*")), [])


if __name__ == "__main__":
    unittest.main()
