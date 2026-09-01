from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from momentumbot.research import sealed_historical_source_checkpoint_v08 as checkpoint
from momentumbot.research.sealed_historical_source_recovery_v08 import (
    ARTIFACT_ID as RECOVERY_ARTIFACT_ID,
    PARENT_REQUEST_BUDGET,
)
from tests.test_sealed_historical_source_checkpoint_v01 import (
    _build_scanner_snapshot_root,
    _build_source_root,
    _environment_files,
    _write_json,
)
from scripts import build_sealed_historical_source_checkpoint_v08 as checkpoint_cli


def _blocked() -> dict[str, object]:
    return {
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
    }


def _budget() -> dict[str, object]:
    return {
        "schema_version": 1,
        "total_attempts": 17_546,
        "by_host": {
            "api.massive.com": 363,
            "data.alpaca.markets": 15_855,
            "data.sec.gov": 1_328,
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


def _authorization(receipt_hash: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "authorization_id": checkpoint.AUTHORIZATION_ID,
        "authority_boundary": {
            "historical_source_recovery_authorized": True,
            "live_order_authorized": False,
            "paper_order_authorized": False,
        },
        "causal_boundary": {
            "ross_actions_fills_skips_or_outcomes_may_be_read": False,
            "transcript_record_values_may_be_read": False,
        },
        "one_shot_contract": {
            "automatic_rerun_allowed": False,
            "workflow_run_attempt_required": 1,
        },
        "request_budget": {
            "allowed_hosts": list(checkpoint.EXPECTED_ALLOWED_HOSTS),
            "composite_parent_attempts_by_host": PARENT_REQUEST_BUDGET["by_host"],
            "composite_parent_total_attempts": 17_540,
            "maximum_total_http_attempts_including_parent_and_child_retries": 40_000,
            "child_massive_calls_authorized": 0,
        },
        "retention_budget": {
            "maximum_retained_bytes": 1_500_000_000,
            "raw_provider_http_responses_persisted": False,
        },
        "recovery_contract": {
            "parent_source_recovery_receipt_content_sha256": receipt_hash,
            "parent_identity_or_market_provider_requests_repeated": False,
        },
    }
    payload["content_sha256"] = checkpoint.canonical_fingerprint(payload)
    return payload


def _receipt() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "artifact_id": RECOVERY_ARTIFACT_ID,
        "request_budget_seed": PARENT_REQUEST_BUDGET,
    }
    payload["content_sha256"] = checkpoint.canonical_fingerprint(payload)
    return payload


def _diagnostic() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "artifact_id": checkpoint.NORMALIZATION_DIAGNOSTIC_ARTIFACT_ID,
        "candidate_rejection_count": 0,
        "candidate_rejections": [],
        "causal_boundary": {
            "candidate_scope_only": True,
            "exception_messages_persisted": False,
            "raw_provider_http_responses_persisted": False,
            "strategy_thresholds_changed": False,
            "transcript_or_label_values_read": False,
        },
    }
    payload["content_sha256"] = checkpoint.canonical_fingerprint(payload)
    return payload


class SealedHistoricalSourceCheckpointV08Tests(unittest.TestCase):
    def _fixture(self, temporary: str) -> dict[str, object]:
        root = Path(temporary) / "source"
        _build_source_root(root)
        observed = sum(path.is_file() for path in root.rglob("*"))
        for index in range(checkpoint.EXPECTED_PRE_SCANNER_FILE_COUNT - observed):
            (root / checkpoint.EXPECTED_DATES[0] / f"fixture-{index:04d}.bin").write_bytes(
                b"fixture"
            )
        freeze, requirements, output = _environment_files(root)
        receipt = _receipt()
        receipt_path = output.parent / checkpoint.RECOVERY_RECEIPT_BASENAME
        diagnostic_path = output.parent / checkpoint.NORMALIZATION_DIAGNOSTIC_BASENAME
        _write_json(receipt_path, receipt)
        _write_json(diagnostic_path, _diagnostic())
        return {
            "root": root,
            "freeze": freeze,
            "requirements": requirements,
            "output": output,
            "receipt": receipt,
            "receipt_path": receipt_path,
            "diagnostic_path": diagnostic_path,
        }

    def _build(self, fixture: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
        receipt = fixture["receipt"]
        assert isinstance(receipt, dict)
        receipt_hash = str(receipt["content_sha256"])
        authorization = _authorization(receipt_hash)
        with patch.object(
            checkpoint, "RECOVERY_RECEIPT_CONTENT_SHA256", receipt_hash
        ):
            result = checkpoint.build_source_checkpoint_v08(
                source_root=fixture["root"],
                authorization=authorization,
                recovery_receipt_path=fixture["receipt_path"],
                normalization_diagnostic_path=fixture["diagnostic_path"],
                request_budget=_budget(),
                blocked_attempt_ledger=_blocked(),
                environment_freeze_path=fixture["freeze"],
                requirements_path=fixture["requirements"],
                checkpoint_output_path=fixture["output"],
                **_provenance(),
            )
        return result, authorization

    def test_round_trip_binds_recovery_diagnostics_and_composite_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(temporary)
            result, authorization = self._build(fixture)
            receipt = fixture["receipt"]
            assert isinstance(receipt, dict)
            self.assertEqual(result["inventory"]["file_count"], 706)
            self.assertEqual(result["request_budget"]["parent_total_attempts"], 17_540)
            self.assertEqual(result["request_budget"]["child_attempts"], 6)
            self.assertEqual(result["normalization_diagnostics"]["candidate_rejection_count"], 0)
            with patch.object(
                checkpoint,
                "RECOVERY_RECEIPT_CONTENT_SHA256",
                receipt["content_sha256"],
            ):
                observed = checkpoint.validate_source_checkpoint_v08(
                    copy.deepcopy(result),
                    recovery_receipt_path=fixture["receipt_path"],
                    normalization_diagnostic_path=fixture["diagnostic_path"],
                    environment_freeze_path=fixture["freeze"],
                    requirements_path=fixture["requirements"],
                    source_root=fixture["root"],
                    authorization=authorization,
                    expected_provenance=result["provenance"],
                )
            self.assertEqual(observed, result)

    def test_composite_budget_cannot_repeat_massive_sec_or_drop_parent_attempts(self) -> None:
        repeated = _budget()
        repeated["by_host"]["api.massive.com"] = 364
        repeated["total_attempts"] = 17_547
        with self.assertRaisesRegex(ValueError, "Massive"):
            checkpoint.normalize_composite_request_budget(repeated)
        repeated_sec = _budget()
        repeated_sec["by_host"]["data.sec.gov"] = 1_329
        repeated_sec["total_attempts"] = 17_547
        with self.assertRaisesRegex(ValueError, "data.sec.gov"):
            checkpoint.normalize_composite_request_budget(repeated_sec)
        below = _budget()
        below["by_host"]["data.sec.gov"] = 1_327
        below["total_attempts"] = 17_545
        with self.assertRaisesRegex(ValueError, "below its parent seed"):
            checkpoint.normalize_composite_request_budget(below)

    def test_success_checkpoint_rejects_any_external_blocked_attempt(self) -> None:
        blocked = _blocked()
        blocked["total_blocked_attempts"] = 1
        blocked["by_category"]["hostname"] = 1
        blocked["by_host"] = {"blocked.example": 1}
        with self.assertRaisesRegex(ValueError, "blocked provider attempt"):
            checkpoint.normalize_blocked_attempt_ledger(blocked, require_zero=True)

    def test_diagnostic_message_or_file_tamper_fails_rehash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(temporary)
            result, _ = self._build(fixture)
            diagnostic = _diagnostic()
            diagnostic["candidate_rejections"] = [
                {
                    "trading_date": checkpoint.EXPECTED_DATES[0],
                    "symbol": "TEST",
                    "stage": "measure_basis_provider_data_normalization",
                    "exception_class": "ValueError",
                    "disposition": "unknown_fail_closed_missing_measure_pair",
                    "message": "raw provider value",
                }
            ]
            diagnostic["candidate_rejection_count"] = 1
            diagnostic["content_sha256"] = checkpoint.canonical_fingerprint(
                {key: value for key, value in diagnostic.items() if key != "content_sha256"}
            )
            _write_json(fixture["diagnostic_path"], diagnostic)
            receipt = fixture["receipt"]
            assert isinstance(receipt, dict)
            with patch.object(
                checkpoint,
                "RECOVERY_RECEIPT_CONTENT_SHA256",
                receipt["content_sha256"],
            ), self.assertRaisesRegex(ValueError, "diagnostic payload fields|row"):
                checkpoint.validate_source_checkpoint_v08(
                    result,
                    recovery_receipt_path=fixture["receipt_path"],
                    normalization_diagnostic_path=fixture["diagnostic_path"],
                    environment_freeze_path=fixture["freeze"],
                    requirements_path=fixture["requirements"],
                    source_root=fixture["root"],
                )

    def test_post_scanner_binding_allows_only_exact_scanner_addition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(temporary)
            result, authorization = self._build(fixture)
            output = fixture["output"]
            assert isinstance(output, Path)
            _write_json(output, result)
            _build_scanner_snapshot_root(fixture["root"])
            receipt = fixture["receipt"]
            assert isinstance(receipt, dict)
            with patch.object(
                checkpoint,
                "RECOVERY_RECEIPT_CONTENT_SHA256",
                receipt["content_sha256"],
            ):
                binding = checkpoint.build_post_scanner_checkpoint_binding_v08(
                    result,
                    checkpoint_file_sha256=checkpoint._file_sha256(output),
                    checkpoint_output_path=output,
                    source_root=fixture["root"],
                    authorization=authorization,
                    recovery_receipt_path=fixture["receipt_path"],
                    normalization_diagnostic_path=fixture["diagnostic_path"],
                    expected_provenance=result["provenance"],
                    environment_freeze_path=fixture["freeze"],
                    requirements_path=fixture["requirements"],
                )
            self.assertEqual(binding["pre_scanner_file_count"], 706)
            self.assertEqual(binding["post_scanner_file_count"], 767)

    def test_exact_checkpoint_cli_builds_revalidates_and_cross_checks_ledgers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(temporary)
            receipt = fixture["receipt"]
            assert isinstance(receipt, dict)
            authorization = _authorization(str(receipt["content_sha256"]))
            artifact_root = Path(temporary) / "provider-checkpoint"
            authorization_path = artifact_root / "authorization.json"
            budget_path = artifact_root / "request-budget.json"
            blocked_path = artifact_root / "blocked-attempts.json"
            _write_json(authorization_path, authorization)
            _write_json(budget_path, _budget())
            _write_json(blocked_path, _blocked())
            arguments = [
                "--source-root",
                str(fixture["root"]),
                "--parent-recovery-receipt",
                str(fixture["receipt_path"]),
                "--normalization-diagnostics",
                str(fixture["diagnostic_path"]),
                "--request-budget",
                str(budget_path),
                "--blocked-attempt-ledger",
                str(blocked_path),
                "--environment-freeze",
                str(fixture["freeze"]),
                "--requirements",
                str(fixture["requirements"]),
                "--authorization",
                str(authorization_path),
                "--authorization-commit-sha",
                "a" * 40,
                "--authorization-tree-sha",
                "b" * 40,
                "--dispatcher-workflow-sha",
                "c" * 40,
                "--dispatcher-workflow-ref",
                checkpoint.EXPECTED_WORKFLOW_REF,
                "--repository",
                "RoomyRems/momentumbot",
                "--workflow-run-id",
                "33470000000",
                "--workflow-run-attempt",
                "1",
                "--output",
                str(fixture["output"]),
            ]
            with patch.object(
                checkpoint,
                "RECOVERY_RECEIPT_CONTENT_SHA256",
                receipt["content_sha256"],
            ):
                self.assertEqual(checkpoint_cli.main(arguments), 0)
                self.assertEqual(
                    checkpoint_cli.main(["--validate-existing", *arguments]), 0
                )
                blocked = _blocked()
                blocked["total_blocked_attempts"] = 1
                blocked["by_category"]["hostname"] = 1
                blocked["by_host"] = {"blocked.example": 1}
                _write_json(blocked_path, blocked)
                with self.assertRaisesRegex(ValueError, "blocked provider attempt"):
                    checkpoint_cli.main(["--validate-existing", *arguments])


if __name__ == "__main__":
    unittest.main()
