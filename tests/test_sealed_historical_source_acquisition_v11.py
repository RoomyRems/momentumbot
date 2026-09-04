from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from momentumbot import historical_float_identity_v11 as identity
from momentumbot.research import sealed_historical_source_acquisition_v11 as acquisition
from momentumbot.research import sealed_historical_source_checkpoint_v10 as checkpoint


def _binding() -> dict[str, object]:
    budget = checkpoint.normalize_composite_request_budget(
        acquisition.PARENT_REQUEST_BUDGET
    )
    payload: dict[str, object] = {
        "schema_version": 1,
        "binding_type": checkpoint.POST_SCANNER_BINDING_TYPE,
        "checkpoint_artifact_id": checkpoint.ARTIFACT_ID,
        "checkpoint_content_sha256": acquisition.PARENT_CHECKPOINT_CONTENT_SHA256,
        "checkpoint_file_sha256": acquisition.PARENT_CHECKPOINT_FILE_SHA256,
        "pre_scanner_tree_content_sha256": "3" * 64,
        "pre_scanner_file_count": 706,
        "pre_scanner_retained_file_bytes": 1_000,
        "post_scanner_tree_content_sha256": "4" * 64,
        "post_scanner_file_count": 767,
        "post_scanner_retained_file_bytes": 1_100,
        "environment": {
            "freeze_path": "environment/pip-freeze.txt",
            "freeze_size_bytes": 10,
            "freeze_sha256": "5" * 64,
            "requirements_path": "environment/requirements-sealed-source-v04.txt",
            "requirements_size_bytes": 20,
            "requirements_sha256": "6" * 64,
        },
        "request_budget": budget,
        "blocked_attempts": {
            "schema_version": 1,
            "total_blocked_attempts": 0,
            "by_category": {
                name: 0
                for name in (
                    "hostname",
                    "https_transport",
                    "redirect",
                    "request_budget",
                    "socket",
                    "subprocess",
                )
            },
            "by_host": {},
        },
        "provenance": acquisition.PARENT_PROVENANCE,
        "authorization": {
            "authorization_id": checkpoint.AUTHORIZATION_ID,
            "authorization_content_sha256": (
                "a6519754147c39273a25b2ea818b1906dfa93ea5018edac831e2a0a7052463c7"
            ),
        },
        "recovery": {
            "artifact_id": checkpoint.RECOVERY_ARTIFACT_ID,
            "receipt_path": checkpoint.RECOVERY_RECEIPT_BASENAME,
            "receipt_size_bytes": 20,
            "receipt_file_sha256": "7" * 64,
            "receipt_content_sha256": checkpoint.RECOVERY_RECEIPT_CONTENT_SHA256,
            "parent_request_budget_seed": checkpoint.PARENT_REQUEST_BUDGET,
        },
        "normalization_diagnostics": {
            "artifact_id": checkpoint.NORMALIZATION_DIAGNOSTIC_ARTIFACT_ID,
            "path": checkpoint.NORMALIZATION_DIAGNOSTIC_BASENAME,
            "size_bytes": 20,
            "file_sha256": "8" * 64,
            "content_sha256": "9" * 64,
            "candidate_rejection_count": 1,
        },
        "sole_permitted_addition_id": checkpoint.EXPECTED_SCANNER_ADDITION_ID,
    }
    payload["content_sha256"] = checkpoint.canonical_fingerprint(payload)
    return payload


def _summary() -> dict[str, object]:
    return {
        "source_tree_content_sha256": "4" * 64,
        "source_file_count": 767,
        "source_retained_file_bytes": 1_100,
    }


def _preflight() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "artifact_id": identity.ARTIFACT_ID,
        "dates": list(identity.EXPECTED_DATES),
        "candidate_count": identity.EXPECTED_CANDIDATE_COUNT,
        "float_record_count": identity.EXPECTED_FLOAT_RECORD_COUNT,
        "identity_kind_counts": identity.EXPECTED_KIND_COUNTS,
        "accepted_identity_kinds": list(identity.EXPECTED_KIND_COUNTS),
        "source_market_root_content_sha256": (
            identity.EXPECTED_MARKET_ROOT_CONTENT_SHA256
        ),
        "source_float_root_content_sha256": (
            identity.EXPECTED_FLOAT_ROOT_CONTENT_SHA256
        ),
        "legacy_downstream_preflight_content_sha256": "a" * 64,
        "protected_loader": "final_source_deep_replay_summarizer",
        "causal_boundary": {
            "float_records_rewritten": False,
            "identity_values_rewritten": False,
            "provider_calls_performed": False,
            "strategy_or_float_threshold_changed": False,
            "transcript_or_label_values_read": False,
        },
    }
    payload["content_sha256"] = identity.canonical_fingerprint(payload)
    return payload


def _environment() -> dict[str, object]:
    return {
        "schema_version": 1,
        "parent_environment_freeze_sha256": (
            acquisition.PARENT_ENVIRONMENT_FREEZE_SHA256
        ),
        "child_environment_freeze_sha256": "b" * 64,
        "parent_project_commit_sha": acquisition.PARENT_PROJECT_COMMIT_SHA,
        "child_project_commit_sha": "c" * 40,
        "third_party_environment_sha256": "d" * 64,
    }


def _provenance() -> dict[str, object]:
    return {
        "repository": acquisition.EXPECTED_REPOSITORY,
        "authorization_commit_sha": "c" * 40,
        "authorization_tree_sha": "d" * 40,
        "dispatcher_workflow_sha": "e" * 40,
        "dispatcher_workflow_ref": (
            "RoomyRems/momentumbot/.github/workflows/"
            "sealed-historical-source-acquisition-v11.yml@refs/heads/main"
        ),
        "workflow_run_id": "33710000000",
        "workflow_run_attempt": 1,
    }


class SealedHistoricalSourceAcquisitionV11Tests(unittest.TestCase):
    def _build(self) -> dict[str, object]:
        with patch.object(acquisition, "validate_source_summary_v04"):
            return acquisition.build_recovery_report_v11(
                authorization_id=acquisition.AUTHORIZATION_ID,
                authorization_content_sha256=(
                    acquisition.AUTHORIZATION_CONTENT_SHA256
                ),
                parent_checkpoint_binding=_binding(),
                source_summary=_summary(),
                identity_preflight=_preflight(),
                environment_comparison=_environment(),
                retained_bytes=1_100,
                **_provenance(),
            )

    def test_report_cross_binds_checkpoint_identity_and_zero_requests(self) -> None:
        report = self._build()
        self.assertTrue(report["source_acquisition_gate_passed"])
        self.assertEqual(report["request_budget"]["total_attempts"], 30_522)
        self.assertEqual(report["cost"]["provider_calls"], 0)
        self.assertEqual(
            report["final_identity_preflight"]["identity_kind_counts"],
            {"composite_figi": 737, "unique_cik_fallback": 209},
        )

    def test_report_rejects_parent_checkpoint_or_final_tree_change(self) -> None:
        binding = _binding()
        binding["checkpoint_file_sha256"] = "0" * 64
        binding["content_sha256"] = checkpoint.canonical_fingerprint(
            {key: value for key, value in binding.items() if key != "content_sha256"}
        )
        with patch.object(
            acquisition, "validate_source_summary_v04"
        ), self.assertRaisesRegex(ValueError, "parent checkpoint"):
            acquisition.build_recovery_report_v11(
                authorization_id=acquisition.AUTHORIZATION_ID,
                authorization_content_sha256=acquisition.AUTHORIZATION_CONTENT_SHA256,
                parent_checkpoint_binding=binding,
                source_summary=_summary(),
                identity_preflight=_preflight(),
                environment_comparison=_environment(),
                retained_bytes=1_100,
                **_provenance(),
            )

    def test_report_self_hash_and_causal_attestation_fail_closed(self) -> None:
        report = self._build()
        changed = copy.deepcopy(report)
        changed["causal_attestation"]["provider_requests_repeated"] = True
        with patch.object(
            acquisition, "validate_source_summary_v04"
        ), self.assertRaisesRegex(ValueError, "hash mismatch"):
            acquisition.validate_recovery_report_v11(changed)

    def test_environment_comparison_ignores_only_editable_commit(self) -> None:
        parent_commit = acquisition.PARENT_PROJECT_COMMIT_SHA
        child_commit = "c" * 40
        dependencies = "PyYAML==6.0.3\nnumpy==2.3.5\n"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = root / "parent.txt"
            child = root / "child.txt"
            parent.write_text(
                "-e git+https://github.com/RoomyRems/momentumbot@"
                f"{parent_commit}#egg=momentumbot\n{dependencies}",
                encoding="utf-8",
            )
            child.write_text(
                "-e git+https://github.com/RoomyRems/momentumbot.git@"
                f"{child_commit}#egg=momentumbot\n{dependencies}",
                encoding="utf-8",
            )
            with patch.object(
                acquisition,
                "PARENT_ENVIRONMENT_FREEZE_SHA256",
                acquisition.file_sha256(parent),
            ):
                result = acquisition.validate_recovery_environment_pair_v11(
                    parent_environment_freeze_path=parent,
                    child_environment_freeze_path=child,
                    expected_child_commit_sha=child_commit,
                )
                self.assertEqual(result["child_project_commit_sha"], child_commit)
                child.write_text(
                    child.read_text().replace("numpy==2.3.5", "numpy==2.3.4"),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ValueError, "differs from v0.10"):
                    acquisition.validate_recovery_environment_pair_v11(
                        parent_environment_freeze_path=parent,
                        child_environment_freeze_path=child,
                        expected_child_commit_sha=child_commit,
                    )


if __name__ == "__main__":
    unittest.main()
