from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from momentumbot.research.sealed_historical_scanner_micro_runtime_v02 import (
    EXPECTED_DATES,
    MISSING_MICRO_INPUTS,
    build_scanner_activation_manifest,
    materialize_scanner_activation_plan,
    validate_contract,
    validate_frozen_policies,
    validate_registration,
)
from momentumbot.research.sealed_historical_source_checkpoint_v01 import (
    canonical_fingerprint,
    load_json_object,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research/strategy/sealed-historical-scanner-micro-runtime-v0.2.json"
REGISTRATION = (
    ROOT
    / "research/data-audits"
    / "sealed-historical-scanner-micro-runtime-v0.2-registration-2026-09-06.json"
)
SCRIPT = ROOT / "scripts/prepare_sealed_historical_scanner_micro_runtime_v02.py"


def _rehash(payload: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(payload)
    result.pop("content_sha256", None)
    result["content_sha256"] = canonical_fingerprint(result)
    return result


class SealedHistoricalScannerMicroRuntimeV02Tests(unittest.TestCase):
    def test_explicit_materialization_reports_started_without_claiming_micro_execution(self) -> None:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src")
        code = (
            "import runpy, sys\n"
            f"sys.path.insert(0, {str(ROOT / 'scripts')!r})\n"
            f"g = runpy.run_path({str(SCRIPT)!r})['main'].__globals__\n"
            "g['validate_final_snapshot'] = lambda root: {'synthetic_fixture': True}\n"
            "g['materialize_scanner_activation_plan'] = lambda **kwargs: {'synthetic_fixture': True}\n"
            f"sys.argv = [{str(SCRIPT)!r}, '--snapshot-root', 'synthetic-source', "
            "'--materialize-scanner-activations', 'synthetic-output']\n"
            "g['main']()\n"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code], cwd=ROOT, env=env,
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["runtime_started"])
        self.assertTrue(payload["scanner_activation_materialization_started"])
        self.assertFalse(payload["micro_runtime_started"])
        self.assertFalse(payload["runtime_execution_authorized"])
        self.assertEqual(payload["scanner_activation_plan"], {"synthetic_fixture": True})

    def test_output_cannot_modify_the_source_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = root / "snapshot"
            snapshot.mkdir()
            alias = root / "source-alias"
            alias.symlink_to(snapshot, target_is_directory=True)
            with patch(
                "momentumbot.research.sealed_historical_scanner_micro_runtime_v02."
                "validate_final_snapshot"
            ) as validate_source:
                for output in (snapshot, snapshot / "new-output", alias / "new-output"):
                    with self.subTest(output=str(output)):
                        with self.assertRaisesRegex(ValueError, "outside the immutable source"):
                            materialize_scanner_activation_plan(
                                snapshot_root=snapshot, output_root=output
                            )
                validate_source.assert_not_called()
            self.assertEqual(list(snapshot.iterdir()), [])

    def test_rehashed_contract_cannot_change_unchecked_execution_boundaries(self) -> None:
        contract = load_json_object(CONTRACT)
        changes = [
            ('input_readiness', 'substitute_one_minute_bars_for_micro_allowed', True),
            ('input_readiness', 'zero_trigger_interpretation_allowed_without_micro_inputs', True),
            ('output_contract', 'fills_or_exits_simulated', True),
            ('output_contract', 'retrospective_labels_loaded', True),
            ('authority_boundary', 'runtime_execution_authorized', None),
        ]
        for section, field, value in changes:
            with self.subTest(section=section, field=field):
                changed = copy.deepcopy(contract)
                changed[section][field] = value
                with self.assertRaises(ValueError):
                    validate_contract(_rehash(changed))
        changed = copy.deepcopy(contract)
        changed['execution_order'] = list(reversed(changed['execution_order']))
        with self.assertRaises(ValueError):
            validate_contract(_rehash(changed))

    def test_rehashed_registration_cannot_claim_different_source_or_started_runtime(self) -> None:
        registration = load_json_object(REGISTRATION)
        for section, field, value in [
            ('source_receipt', 'workflow_run_id', '34007768483'),
            ('source_receipt', 'artifact_zip_sha256', '0' * 64),
            ('causal_attestation', 'micro_runtime_started', True),
        ]:
            with self.subTest(section=section, field=field):
                changed = copy.deepcopy(registration)
                changed[section][field] = value
                with self.assertRaises(ValueError):
                    validate_registration(_rehash(changed), contract_path=CONTRACT)

    def test_validation_cli_denies_network_and_child_processes(self) -> None:
        env = dict(os.environ)
        env['PYTHONPATH'] = str(ROOT / 'src')
        for expression in ['socket.socket()', 'subprocess.Popen([sys.executable, "-c", "pass"])']:
            with self.subTest(operation=expression):
                code = (
                    'import runpy, socket, subprocess, sys\n'
                    f'sys.path.insert(0, {str(ROOT / "scripts")!r})\n'
                    f'g = runpy.run_path({str(SCRIPT)!r})\n'
                    f'g["main"].__globals__["validate_contract"] = lambda payload: {expression}\n'
                    f'sys.argv = [{str(SCRIPT)!r}]\n'
                    'g["main"]()\n'
                )
                completed = subprocess.run(
                    [sys.executable, '-c', code], cwd=ROOT, env=env,
                    capture_output=True, text=True, timeout=30,
                )
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn('provider-free recovery forbids network/process I/O', completed.stderr)

    def test_synthetic_scanner_activation_plan_reapplies_frozen_profiles(self) -> None:
        rows = [
            {
                "decision_time": "2025-05-30T11:00:00+00:00",
                "symbol": "TEST",
                "candidate_completed_bar_present": True,
                "price": 3.0,
                "percent_gain": 30.0,
                "exact_same_time_rvol": 6.0,
                "estimated_float_shares": 5_000_000,
                "has_provider_news_as_of": True,
                "top_gainer_rank": 2,
            },
            {
                "decision_time": "2025-05-30T11:01:00+00:00",
                "symbol": "TEST",
                "candidate_completed_bar_present": True,
                "price": 3.1,
                "percent_gain": 31.0,
                "exact_same_time_rvol": 6.2,
                "estimated_float_shares": 5_000_000,
                "has_provider_news_as_of": True,
                "top_gainer_rank": 2,
            },
        ]
        from momentumbot.causal_scanner_snapshot import ordered_snapshot_records_fingerprint

        snapshot = {
            "schema_version": 2,
            "artifact_id": "causal-scanner-snapshot-v0.3",
            "trading_date": "2025-05-30",
            "row_count": len(rows),
            "ordered_records_sha256": ordered_snapshot_records_fingerprint(rows),
            "rows": rows,
        }
        snapshot["content_sha256"] = canonical_fingerprint(snapshot)
        result = build_scanner_activation_manifest(
            snapshot, trading_date="2025-05-30"
        )
        self.assertEqual(result["activation_count"], 1)
        self.assertEqual(
            result["activations"][0]["eligible_strategy_profile_ids"],
            ["current-general-2026", "current-small-account-2026"],
        )
        self.assertEqual(result["micro_input_request_count"], 1)
        self.assertFalse(result["micro_runtime_complete"])
        self.assertEqual(result["provider_calls"], 0)

    def test_contract_is_exact_unarmed_and_policy_bound(self) -> None:
        contract = load_json_object(CONTRACT)
        validate_contract(contract)
        validate_frozen_policies()
        self.assertEqual(contract["selected_dates"], list(EXPECTED_DATES))
        self.assertFalse(contract["authority_boundary"]["runtime_execution_authorized"])
        self.assertFalse(contract["authority_boundary"]["backtesting_authorized"])
        self.assertFalse(contract["execution_status"]["scanner_activation_materialization_started"])

    def test_micro_gap_is_explicit_and_cannot_be_rehashed_away(self) -> None:
        contract = load_json_object(CONTRACT)
        readiness = contract["input_readiness"]
        self.assertFalse(readiness["micro_v0_1_runtime_ready"])
        self.assertEqual(tuple(readiness["missing_required_inputs"]), MISSING_MICRO_INPUTS)
        self.assertFalse(readiness["substitute_one_minute_bars_for_micro_allowed"])
        changed = copy.deepcopy(contract)
        changed["input_readiness"]["micro_v0_1_runtime_ready"] = True
        changed = _rehash(changed)
        with self.assertRaisesRegex(ValueError, "must not claim Micro-v0.1"):
            validate_contract(changed)

    def test_rehashed_authority_escalation_fails(self) -> None:
        contract = load_json_object(CONTRACT)
        changed = copy.deepcopy(contract)
        changed["authority_boundary"]["runtime_execution_authorized"] = True
        changed = _rehash(changed)
        with self.assertRaisesRegex(ValueError, "grants authority"):
            validate_contract(changed)

    def test_registration_binds_exact_contract_file(self) -> None:
        registration = load_json_object(REGISTRATION)
        validate_registration(registration, contract_path=CONTRACT)
        receipt = registration["contract"]
        self.assertEqual(receipt["file_sha256"], hashlib.sha256(CONTRACT.read_bytes()).hexdigest())

    def test_validation_cli_is_provider_free_and_does_not_start_runtime(self) -> None:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src")
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["registration_valid"])
        self.assertFalse(payload["runtime_execution_authorized"])
        self.assertFalse(payload["runtime_started"])

    def test_preparation_does_not_reference_retrospective_files(self) -> None:
        paths = (CONTRACT, REGISTRATION, SCRIPT)
        rendered = "\n".join(path.read_text(encoding="utf-8") for path in paths).lower()
        for forbidden in ("dataset_daytradewarrior", "ross-label", "brokerage_endpoint"):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
