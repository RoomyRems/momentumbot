from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from momentumbot.research import sealed_historical_source_acquisition_v05 as acquisition
from momentumbot.research import sealed_historical_source_checkpoint_v05 as checkpoint
from momentumbot.research.sealed_historical_source_recovery_v05 import (
    ARTIFACT_ID as RECOVERY_ARTIFACT_ID,
    PARENT_REQUEST_BUDGET,
)


AUTHORIZATION_SHA = "d" * 64


def _budget() -> dict[str, object]:
    return {
        "schema_version": 1,
        "total_attempts": 14_530,
        "by_host": {
            "api.massive.com": 363,
            "data.alpaca.markets": 14_159,
            "data.sec.gov": 8,
        },
    }


def _provenance() -> dict[str, object]:
    return {
        "repository": "RoomyRems/momentumbot",
        "authorization_commit_sha": "a" * 40,
        "authorization_tree_sha": "b" * 40,
        "dispatcher_workflow_sha": "c" * 40,
        "dispatcher_workflow_ref": checkpoint.EXPECTED_WORKFLOW_REF,
        "workflow_run_id": "33470000000",
        "workflow_run_attempt": 1,
    }


def _binding() -> dict[str, object]:
    budget = checkpoint.normalize_composite_request_budget(_budget())
    provenance = _provenance()
    payload: dict[str, object] = {
        "schema_version": 1,
        "binding_type": checkpoint.POST_SCANNER_BINDING_TYPE,
        "checkpoint_artifact_id": checkpoint.ARTIFACT_ID,
        "checkpoint_content_sha256": "1" * 64,
        "checkpoint_file_sha256": "2" * 64,
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
        "provenance": provenance,
        "authorization": {
            "authorization_id": checkpoint.AUTHORIZATION_ID,
            "authorization_content_sha256": AUTHORIZATION_SHA,
        },
        "recovery": {
            "artifact_id": RECOVERY_ARTIFACT_ID,
            "receipt_path": checkpoint.RECOVERY_RECEIPT_BASENAME,
            "receipt_size_bytes": 20,
            "receipt_file_sha256": "7" * 64,
            "receipt_content_sha256": checkpoint.RECOVERY_RECEIPT_CONTENT_SHA256,
            "parent_request_budget_seed": PARENT_REQUEST_BUDGET,
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


def _build() -> dict[str, object]:
    with patch.object(
        acquisition,
        "_frozen_authorization_content_sha256",
        return_value=AUTHORIZATION_SHA,
    ), patch.object(acquisition, "validate_source_summary_v04"):
        return acquisition.build_acquisition_report_v05(
            authorization_id=checkpoint.AUTHORIZATION_ID,
            authorization_content_sha256=AUTHORIZATION_SHA,
            source_checkpoint_binding=_binding(),
            source_summary=_summary(),
            request_budget=_budget(),
            retained_bytes=1_100,
            **_provenance(),
        )


class SealedHistoricalSourceAcquisitionV05Tests(unittest.TestCase):
    def test_report_cross_binds_parent_diagnostic_budget_and_final_tree(self) -> None:
        report = _build()
        self.assertTrue(report["source_acquisition_gate_passed"])
        self.assertEqual(report["request_budget"]["parent_total_attempts"], 14_524)
        self.assertEqual(report["request_budget"]["child_attempts"], 6)
        self.assertEqual(report["parent_recovery"], report["source_checkpoint"]["recovery"])
        self.assertEqual(
            report["normalization_diagnostics"],
            report["source_checkpoint"]["normalization_diagnostics"],
        )

    def test_report_rejects_checkpoint_tree_budget_and_recovery_mismatch(self) -> None:
        for field, value, pattern in (
            ("source_summary", {**_summary(), "source_retained_file_bytes": 1_101}, "final tree"),
            ("request_budget", {**_budget(), "total_attempts": 14_531}, "inconsistent|differs"),
        ):
            kwargs = {
                "authorization_id": checkpoint.AUTHORIZATION_ID,
                "authorization_content_sha256": AUTHORIZATION_SHA,
                "source_checkpoint_binding": _binding(),
                "source_summary": _summary(),
                "request_budget": _budget(),
                "retained_bytes": 1_100,
                **_provenance(),
            }
            kwargs[field] = value
            with patch.object(
                acquisition,
                "_frozen_authorization_content_sha256",
                return_value=AUTHORIZATION_SHA,
            ), patch.object(acquisition, "validate_source_summary_v04"), self.subTest(
                field=field
            ), self.assertRaisesRegex(ValueError, pattern):
                acquisition.build_acquisition_report_v05(**kwargs)

    def test_self_hash_and_causal_attestation_are_fail_closed(self) -> None:
        report = _build()
        changed = copy.deepcopy(report)
        changed["causal_attestation"]["transcript_record_values_read"] = True
        with patch.object(
            acquisition,
            "_frozen_authorization_content_sha256",
            return_value=AUTHORIZATION_SHA,
        ), patch.object(acquisition, "validate_source_summary_v04"), self.assertRaisesRegex(
            ValueError, "hash mismatch"
        ):
            acquisition.validate_acquisition_report_v05(changed)

        changed["content_sha256"] = checkpoint.canonical_fingerprint(
            {key: value for key, value in changed.items() if key != "content_sha256"}
        )
        with patch.object(
            acquisition,
            "_frozen_authorization_content_sha256",
            return_value=AUTHORIZATION_SHA,
        ), patch.object(acquisition, "validate_source_summary_v04"), self.assertRaisesRegex(
            ValueError, "causal attestation"
        ):
            acquisition.validate_acquisition_report_v05(changed)


if __name__ == "__main__":
    unittest.main()
