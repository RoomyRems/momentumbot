"""CLI wiring tests; real-data E2E is a separate mandatory launch gate.

Only expensive source acquisition/replay I/O is substituted here. The CLI,
argument parsing, file existence checks, external ledger checks, real report
builder, complete source-summary validator and serialized report validator run.
"""

from __future__ import annotations

from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import check_recovery_entrypoints_v13 as names
from scripts import run_offline_python_v13 as offline
from scripts import run_sealed_historical_source_acquisition_v13 as runner
from momentumbot.research import sealed_historical_source_acquisition_v13 as report
from momentumbot.research import sealed_historical_source_authorization_v13 as auth
from momentumbot.research import sealed_historical_source_checkpoint_v01 as inventory_contract
from tests.test_sealed_historical_source_acquisition_v12 import _binding, _preflight, _environment
from tests.test_sealed_historical_source_acquisition_v04 import _valid_summary


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _rehash(payload: dict[str, object]) -> None:
    payload.pop("content_sha256", None)
    payload["content_sha256"] = report.canonical_fingerprint(payload)


def _synthetic_source(root: Path) -> dict[str, object]:
    """Real filesystem inventory, explicitly not market-data replay evidence."""
    directories = (
        set(inventory_contract.EXPECTED_DATES)
        | {relative for _, relative, _ in inventory_contract.EXPECTED_STAGE_ROOTS if relative != "."}
        | set(inventory_contract.EXPECTED_AUXILIARY_CENSUS_ROOTS)
        | {inventory_contract.EXPECTED_SCANNER_SNAPSHOT_ROOT}
    )
    for directory in directories:
        (root / directory).mkdir(parents=True, exist_ok=True)
    _write(root / "manifest.json", {"synthetic_fixture": True})
    _write(root / inventory_contract.MASSIVE_TICKER_TYPES_FILE, {"synthetic_fixture": True})
    scanner = {
        "artifact_id": "causal-scanner-snapshot-v0.3",
        "dates": list(report.EXPECTED_DATES),
        "eligibility": {"provider_free_replay_exact": True},
    }
    _rehash(scanner)
    _write(root / "causal-scanner-snapshot-v0.3/manifest.json", scanner)
    for number in range(764):
        _write(root / report.EXPECTED_DATES[0] / f"fixture-{number:03d}.json", {"synthetic_fixture": number})
    return report.inventory_source_tree(root, allow_scanner_snapshot_addition=True)


def _bind_inventory(binding: dict[str, object], inventory: dict[str, object]) -> None:
    binding["post_scanner_tree_content_sha256"] = inventory["tree_content_sha256"]
    binding["post_scanner_retained_file_bytes"] = sum(row["size_bytes"] for row in inventory["files"])
    _rehash(binding)


class RunnerV13Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.output = self.root / "recovery-report.json"
        self.binding = _binding()
        self.binding["post_scanner_retained_file_bytes"] = 1_000_000
        self.binding["content_sha256"] = report.canonical_fingerprint({k: v for k, v in self.binding.items() if k != "content_sha256"})
        self.summary = _valid_summary()
        self.environment = _environment()
        self.preflight = _preflight()
        self.paths = {
            "source-checkpoint": self.root / "provider-checkpoint/source-checkpoint.json",
            "parent-recovery-receipt": self.root / "provider-checkpoint/parent-recovery-receipt.json",
            "normalization-diagnostics": self.root / "provider-checkpoint/float-normalization-rejections.json",
            "request-budget": self.root / "provider-checkpoint/request-budget.json",
            "blocked-attempt-ledger": self.root / "provider-checkpoint/blocked-attempts.json",
            "parent-environment-freeze": self.root / "provider-checkpoint/environment/pip-freeze.txt",
            "child-environment-freeze": self.root / "child/environment/pip-freeze.txt",
            "requirements": self.root / "provider-checkpoint/environment/requirements-sealed-source-v04.txt",
            "intermediate-checkpoint": self.root / "intermediate-checkpoint.json",
        }
        for path in self.paths.values():
            _write(path, {})
        _write(self.paths["source-checkpoint"], {
            "request_budget": self.binding["request_budget"],
            "blocked_attempts": self.binding["blocked_attempts"],
        })
        _write(self.paths["request-budget"], report.PARENT_REQUEST_BUDGET)
        _write(self.paths["blocked-attempt-ledger"], self.binding["blocked_attempts"])
        self.arguments = [
            "--authorization", str(auth.ROOT / auth.AUTHORIZATION_PATH),
            "--source-root", str(self.source),
            "--output", str(self.output),
            "--repository", "RoomyRems/momentumbot",
            "--authorization-commit-sha", "c" * 40,
            "--authorization-tree-sha", "d" * 40,
            "--dispatcher-workflow-sha", "e" * 40,
            "--dispatcher-workflow-ref", auth.EXPECTED_DISPATCHER_WORKFLOW_REF,
            "--workflow-run-id", "33990000000",
            "--workflow-run-attempt", "1",
        ]
        for name, path in self.paths.items():
            self.arguments.extend(["--" + name, str(path)])

    def _wiring_fixtures(self) -> ExitStack:
        stack = ExitStack()
        stack.enter_context(patch.object(runner, "PARENT_CHECKPOINT_FILE_SHA256", report.file_sha256(self.paths["source-checkpoint"])))
        stack.enter_context(patch.object(runner, "validate_recovery_environment_pair_v13", return_value=self.environment))
        stack.enter_context(patch.object(runner, "build_post_scanner_checkpoint_binding_v10", return_value=self.binding))
        stack.enter_context(patch.object(runner, "summarize_source_root_identity_compatible_v11", return_value=(self.summary, self.preflight)))
        stack.enter_context(patch.object(runner, "retained_tree_bytes", return_value=1_000_000))
        stack.enter_context(patch.object(runner, "validate_intermediate_checkpoint_v13"))
        stack.enter_context(redirect_stdout(io.StringIO()))
        return stack

    def _argument(self, name: str, value: str) -> None:
        self.arguments[self.arguments.index(name) + 1] = value

    def test_actual_cli_success_writes_and_validates_real_report(self) -> None:
        with self._wiring_fixtures():
            self.assertEqual(runner.main(self.arguments), 0)
        result = json.loads(self.output.read_text())
        report.validate_recovery_report_v13(result)
        self.assertTrue(result["source_acquisition_gate_passed"])
        self.assertEqual(result["request_budget"]["total_attempts"], 30522)

    def test_invalid_external_ledger_fails_before_replay(self) -> None:
        changed = deepcopy(report.PARENT_REQUEST_BUDGET)
        changed["total_attempts"] += 1
        changed["by_host"]["data.alpaca.markets"] += 1
        _write(self.paths["request-budget"], changed)
        with self._wiring_fixtures(), self.assertRaisesRegex(ValueError, "frozen v0.10 ledger"):
            runner.main(self.arguments)
        self.assertFalse(self.output.exists())

    def test_preflight_cli_checks_checkpoint_and_identity_without_final_replay(self) -> None:
        with self._wiring_fixtures(), \
                patch.object(runner, "validate_source_checkpoint_v10") as checkpoint_gate, \
                patch.object(runner, "build_final_identity_preflight_receipt", return_value=self.preflight) as identities, \
                patch.object(runner, "summarize_source_root_identity_compatible_v11") as replay, \
                patch.object(runner, "build_post_scanner_checkpoint_binding_v10") as final_binding:
            self.assertEqual(runner.main(self.arguments + ["--preflight-only"]), 0)
            checkpoint_gate.assert_called_once()
            identities.assert_called_once_with(self.source)
            replay.assert_not_called()
            final_binding.assert_not_called()
        result = json.loads(self.output.read_text())
        self.assertFalse(result["source_acquisition_gate_passed"])
        self.assertEqual(result["request_budget"], report.PARENT_REQUEST_BUDGET)
        self.assertEqual(result["identity_preflight"]["candidate_count"], 946)

    def test_intermediate_cli_binds_real_inventory_without_final_replay(self) -> None:
        _bind_inventory(self.binding, _synthetic_source(self.source))
        with self._wiring_fixtures(), \
                patch.object(runner, "build_final_identity_preflight_receipt", return_value=self.preflight), \
                patch.object(runner, "summarize_source_root_identity_compatible_v11") as replay:
            self.assertEqual(runner.main(self.arguments + ["--write-intermediate"]), 0)
            replay.assert_not_called()
        result = json.loads(self.output.read_text())
        report.validate_intermediate_checkpoint_v13(
            result, source_root=self.source, binding=self.binding,
            environment_comparison=self.environment, provenance=result["workflow_provenance"],
        )
        self.assertFalse(result["backtest_eligible"])
        self.assertEqual(result["source_inventory"]["file_count"], 767)

    def test_nonzero_blocked_ledger_fails_before_replay(self) -> None:
        changed = deepcopy(self.binding["blocked_attempts"])
        changed["total_blocked_attempts"] = 1
        changed["by_category"]["socket"] = 1
        _write(self.paths["blocked-attempt-ledger"], changed)
        with self._wiring_fixtures(), self.assertRaises(ValueError):
            runner.main(self.arguments)
        self.assertFalse(self.output.exists())

    def test_cli_requires_intermediate_and_cannot_overwrite(self) -> None:
        self.paths["intermediate-checkpoint"].unlink()
        with self._wiring_fixtures(), self.assertRaisesRegex(ValueError, "intermediate checkpoint"):
            runner.main(self.arguments)
        _write(self.output, {"preserve": True})
        with self.assertRaisesRegex(ValueError, "overwrite is forbidden"):
            runner.main(self.arguments)
        self.assertEqual(json.loads(self.output.read_text()), {"preserve": True})

    def test_cli_missing_argument_and_attempt_two_fail_closed(self) -> None:
        self._argument("--workflow-run-attempt", "2")
        with self.assertRaisesRegex(ValueError, "attempt 1"):
            runner.main(self.arguments)
        self._argument("--workflow-run-attempt", "1")
        index = self.arguments.index("--request-budget")
        del self.arguments[index:index + 2]
        with self.assertRaisesRegex(SystemExit, "request budget is required"):
            runner.main(self.arguments)

    def test_local_verification_does_not_claim_github_or_open_final_gate(self) -> None:
        self.arguments.extend(["--execution-mode", "local_verification"])
        for key in ("--dispatcher-workflow-ref", "--dispatcher-workflow-sha", "--workflow-run-id"):
            self._argument(key, "")
        self._argument("--workflow-run-attempt", "0")
        with self._wiring_fixtures():
            self.assertEqual(runner.main(self.arguments), 0)
        result = json.loads(self.output.read_text())
        report.validate_recovery_report_v13(result)
        self.assertFalse(result["source_acquisition_gate_passed"])
        self.assertEqual(result["workflow_provenance"]["execution_mode"], "local_verification")
        self.assertEqual(result["workflow_provenance"]["workflow_run_id"], "")

    def test_local_verification_cannot_forge_a_github_identity(self) -> None:
        self.arguments.extend(["--execution-mode", "local_verification"])
        with self.assertRaisesRegex(ValueError, "must not claim GitHub"):
            runner.main(self.arguments)

    def test_hosted_prelaunch_verification_records_real_run_but_not_final_gate(self) -> None:
        self.arguments.extend(["--execution-mode", "prelaunch_verification"])
        self._argument("--dispatcher-workflow-sha", "c" * 40)
        self._argument("--dispatcher-workflow-ref", "RoomyRems/momentumbot/.github/workflows/sealed-historical-source-recovery-v13-e2e.yml@refs/heads/phase-3-historical-snapshot")
        with self._wiring_fixtures():
            self.assertEqual(runner.main(self.arguments), 0)
        result = json.loads(self.output.read_text())
        report.validate_recovery_report_v13(result)
        self.assertFalse(result["source_acquisition_gate_passed"])
        self.assertEqual(result["workflow_provenance"]["workflow_run_id"], "33990000000")
        self.assertEqual(result["workflow_provenance"]["execution_mode"], "prelaunch_verification")

    def test_real_summary_validator_is_not_mocked(self) -> None:
        self.summary["provider_free_replay_exact_by_date"][report.EXPECTED_DATES[0]] = False
        with self._wiring_fixtures(), self.assertRaises(ValueError):
            runner.main(self.arguments)
        self.assertFalse(self.output.exists())

    def test_safe_failure_uses_actual_cli_and_is_sanitized(self) -> None:
        with redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(self.arguments + ["--write-safe-failure"]), 0)
        failure = json.loads(self.output.read_text())
        self.assertEqual(failure["failed_execution_parent"]["workflow_run_id"], 33929860053)
        self.assertFalse(failure["progress"]["final_report_completed"])
        self.assertEqual(failure["causal_attestation"]["provider_calls"], 0)
        body = dict(failure)
        digest = body.pop("content_sha256")
        self.assertEqual(digest, auth.canonical_fingerprint(body))


class IntermediateV13Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name) / "source"
        self.binding = _binding()
        _bind_inventory(self.binding, _synthetic_source(self.source))
        self.environment = _environment()
        self.provenance = report._workflow_provenance_v13(
            repository=report.EXPECTED_REPOSITORY,
            authorization_commit_sha="c" * 40,
            authorization_tree_sha="d" * 40,
            dispatcher_workflow_sha="",
            dispatcher_workflow_ref="",
            workflow_run_id="",
            workflow_run_attempt=0,
            execution_mode="local_verification",
        )
        self.payload = report.build_intermediate_checkpoint_v13(
            source_root=self.source, binding=self.binding,
            identity_preflight=_preflight(), environment_comparison=self.environment,
            provenance=self.provenance,
        )

    def _validate(self, payload: dict[str, object] | None = None) -> None:
        report.validate_intermediate_checkpoint_v13(
            self.payload if payload is None else payload,
            source_root=self.source, binding=self.binding,
            environment_comparison=self.environment, provenance=self.provenance,
        )

    def test_real_inventory_round_trip_stays_non_final(self) -> None:
        self._validate()
        self.assertEqual(len(self.payload["source_inventory"]["files"]), 767)
        self.assertFalse(self.payload["source_acquisition_gate_passed"])
        self.assertFalse(self.payload["backtest_eligible"])
        self.assertEqual(self.payload["status"], "intermediate_final_deep_replay_pending")

    def test_rehashed_final_eligibility_and_provider_claims_are_rejected(self) -> None:
        for key, value in (("backtest_eligible", True), ("source_acquisition_gate_passed", True), ("provider_calls", 1)):
            changed = deepcopy(self.payload)
            changed[key] = value
            _rehash(changed)
            with self.subTest(field=key), self.assertRaisesRegex(ValueError, "checkpoint changed"):
                self._validate(changed)

    def test_modified_file_bytes_are_rejected_even_with_unchanged_count(self) -> None:
        _write(self.source / report.EXPECTED_DATES[0] / "fixture-000.json", {"changed": True})
        with self.assertRaisesRegex(ValueError, "inventory differs"):
            self._validate()

    def test_directory_change_is_part_of_the_source_commitment(self) -> None:
        (self.source / report.EXPECTED_DATES[0] / "extra-directory").mkdir()
        with self.assertRaisesRegex(ValueError, "inventory differs"):
            self._validate()

    def test_incomplete_scanner_manifest_is_rejected_even_if_rehashed(self) -> None:
        path = self.source / "causal-scanner-snapshot-v0.3/manifest.json"
        scanner = json.loads(path.read_text())
        scanner["eligibility"]["provider_free_replay_exact"] = False
        _rehash(scanner)
        _write(path, scanner)
        _bind_inventory(self.binding, report.inventory_source_tree(self.source, allow_scanner_snapshot_addition=True))
        with self.assertRaisesRegex(ValueError, "scanner completion manifest"):
            self._validate()

    def test_rehashed_identity_count_and_parent_ledger_changes_are_rejected(self) -> None:
        changed = deepcopy(self.payload)
        changed["identity_preflight"]["candidate_count"] = 945
        _rehash(changed["identity_preflight"])
        _rehash(changed)
        with self.assertRaises(ValueError):
            self._validate(changed)
        self.binding["request_budget"]["total_attempts"] += 1
        _rehash(self.binding)
        with self.assertRaises(ValueError):
            self._validate()


class OfflineAndStaticV13Tests(unittest.TestCase):
    def test_gate_detects_the_exact_unmodified_v12_failure(self) -> None:
        old = (auth.ROOT / "scripts/run_sealed_historical_source_acquisition_v12.py").read_text()
        self.assertIn("PARENT_REQUEST_BUDGET", names.undefined_globals(old))
        for relative in names.ACTIVE_FILES:
            with self.subTest(path=relative):
                self.assertEqual(names.undefined_globals((auth.ROOT / relative).read_text()), set())

    def test_gate_detects_nested_scopes_and_accepts_bound_names(self) -> None:
        self.assertEqual(names.undefined_globals("def outer():\n def inner():\n  return MISSING\n return inner\n"), {"MISSING"})
        self.assertEqual(names.undefined_globals("import json\nVALUE = 1\ndef f():\n return json.dumps(VALUE)\n"), set())
        with self.assertRaises(ValueError):
            names.undefined_globals("from math import *")

    def test_guard_rejects_acquisition_and_arbitrary_scripts(self) -> None:
        for arguments in (["scripts/build_causal_scanner_snapshot_v10.py", "--phase", "acquire-source-inputs"], ["scripts/unknown.py"]):
            with self.assertRaises(SystemExit):
                offline.main(arguments)

    def test_guard_blocks_real_socket_and_process_creation_in_subprocess(self) -> None:
        for statement in ("socket.socket()", "subprocess.run([sys.executable, '-c', 'pass'])"):
            code = (
                "import socket, subprocess, sys\n"
                "from scripts.run_offline_python_v13 import deny_external_io\n"
                "sys.addaudithook(deny_external_io)\n" + statement
            )
            completed = subprocess.run([sys.executable, "-c", code], cwd=auth.ROOT, capture_output=True, text=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("forbids network/process I/O", completed.stderr)


if __name__ == "__main__":
    unittest.main()
