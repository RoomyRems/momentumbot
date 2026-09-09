"""Synthetic reproduction receipts, exact-byte gates and immutable parents."""
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import reproduce_sealed_historical_account_residual_exit_v01 as m

ROOT = Path(__file__).resolve().parents[1]


def synthetic_contract(base):
    source = base / "synthetic-source.zip"
    source.write_bytes(b"synthetic-source")
    documents = {name: m.seal({"synthetic_document": name}) for name in m.ORIGINAL_FILES}
    documents.update({"verification/" + name: m.seal({"synthetic_document": name})
        for name in ("attempt.json", "freeze-manifest.json")})
    documents["verification/verification.json"] = m.seal({"verification_passed": True,
        "runtime_content_sha256": "synthetic-runtime", "totals": {"sessions": 1}})
    expected = {}
    for name, doc in documents.items():
        raw = m.encoded(doc)
        expected[name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "content_sha256": doc["content_sha256"]}
    contract = m.seal({"expected_runtime_content_sha256": "synthetic-runtime",
        "expected_documents": expected, "source_archives": {"synthetic": m.file_spec(source)},
        "required_incomplete_states": {"synthetic": 1}})
    return contract, {"synthetic": source}, documents


def write_documents(output, documents, verification):
    for name, doc in documents.items():
        if name.startswith("verification/") != verification:
            continue
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        m.write_new(path, doc)


class ReproductionRegistrationTests(unittest.TestCase):
    def test_metadata_registration_preserves_original_producer_and_verifier(self):
        expected = m.read(m.freeze_path(ROOT))["content_sha256"]
        with patch.object(m, "replay_original", side_effect=AssertionError("metadata only")), \
             patch.object(m, "verify_reproduced", side_effect=AssertionError("metadata only")):
            contract, _ = m.check_registration(ROOT, expected)
        self.assertEqual(contract["original_registration_freeze_content_sha256"], m.verifier.ORIGINAL_REGISTRATION)
        self.assertEqual(contract["verifier_registration_freeze_content_sha256"], m.VERIFIER_REGISTRATION)
        self.assertEqual(contract["expected_runtime_file_sha256"], m.verifier.RUNTIME_FILE)
        self.assertEqual(len(contract["source_archives"]), 7)
        self.assertEqual(len(contract["expected_documents"]), 6)
        self.assertEqual(contract["attempts_per_environment"], 1)
        self.assertEqual(contract["timeout_minutes"], 120)
        self.assertTrue(all(contract[key] is False for key in m.BOUNDARIES))

    def test_wrong_external_commitment_or_changed_orchestrator_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "external reproduction"):
            m.check_registration(ROOT, "0" * 64)
        expected = m.read(m.freeze_path(ROOT))["content_sha256"]
        original = m.file_spec
        with patch.object(m, "file_spec", side_effect=lambda path:
                {"bytes": 0, "sha256": "0" * 64} if path == ROOT / m.OWN_FILES[0] else original(path)):
            with self.assertRaises(ValueError):
                m.check_registration(ROOT, expected)

    def test_metadata_cli_succeeds_under_offline_guard(self):
        result = subprocess.run([sys.executable, str(ROOT / m.OWN_FILES[0]), "--check-registration"],
            cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"registration_verified": true', result.stdout)

    def test_original_cli_receives_exact_registration_and_restores_arguments(self):
        import build_sealed_historical_account_residual_exit_v01 as original
        paths = {key: Path("synthetic") / key for key in
            ("scanner", "management", "exit", "entry_result", "entry_consumption")}
        previous = sys.argv
        received = []
        def main():
            received.extend(sys.argv)
            return 0
        with patch.object(original, "main", side_effect=main):
            m.replay_original(Path("output"), paths)
        self.assertIs(sys.argv, previous)
        self.assertEqual(received[1:6], ["--replay", "--expected-registration-sha256",
            m.verifier.ORIGINAL_REGISTRATION, "--output-root", "output/account-replay"])
        self.assertEqual(received[-2:], ["--entry-consumption-zip", "synthetic/entry_consumption"])
        with patch.object(original, "main", side_effect=ValueError("synthetic original failure")):
            with self.assertRaises(ValueError):
                m.replay_original(Path("output"), paths)
        self.assertIs(sys.argv, previous)


class ReproductionAttemptTests(unittest.TestCase):
    def test_receipt_precedes_sources_and_success_requires_six_exact_components(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            contract, paths, documents = synthetic_contract(base)
            output = base / "attempt"
            calls = []
            def replay(out, inputs):
                self.assertTrue((out / "reproduction-attempt.json").is_file())
                self.assertEqual(inputs, paths)
                calls.append("original_replay")
                write_documents(out, documents, False)
            def verify(root, out, inputs, specs):
                self.assertEqual(calls, ["original_replay"])
                calls.append("frozen_verification")
                write_documents(out, documents, True)
            with patch.object(m, "check_registration", return_value=(contract, {})), \
                 patch.object(m, "replay_original", side_effect=replay), \
                 patch.object(m, "verify_reproduced", side_effect=verify), redirect_stdout(io.StringIO()):
                report = m.run_reproduction(ROOT, output, paths, "synthetic-freeze")
            self.assertEqual(calls, ["original_replay", "frozen_verification"])
            self.assertTrue(report["runtime_reproduction_verified"])
            self.assertTrue(all(report[key] is False for key in m.BOUNDARIES))
            freeze = m.read(output / "reproduction-freeze.json")
            self.assertEqual(len(freeze["file_inventory"]), 8)
            self.assertEqual(len(list(output.rglob("*.json"))), 9)
            for name, spec in freeze["file_inventory"].items():
                self.assertEqual(m.file_spec(output / name), spec)

    def test_source_mismatch_retains_receipt_and_failure_without_entering_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            contract, paths, _ = synthetic_contract(base)
            paths["synthetic"].write_bytes(b"changed")
            output = base / "attempt"
            with patch.object(m, "check_registration", return_value=(contract, {})), \
                 patch.object(m, "replay_original", side_effect=AssertionError("must not replay")), redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, "archive bytes differ"):
                    m.run_reproduction(ROOT, output, paths, "synthetic-freeze")
            failure = m.read(output / "reproduction-failure.json")
            self.assertEqual(failure["stage"], "source_archive_validation")
            self.assertFalse(failure["runtime_reproduction_verified"])
            self.assertTrue((output / "reproduction-attempt.json").exists())

    def test_original_failure_and_partial_output_survive_and_retry_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            contract, paths, documents = synthetic_contract(base)
            output = base / "attempt"
            def fail(out, inputs):
                write_documents(out, documents, False)
                raise ValueError("synthetic original failure")
            with patch.object(m, "check_registration", return_value=(contract, {})), \
                 patch.object(m, "replay_original", side_effect=fail), redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, "synthetic original failure"):
                    m.run_reproduction(ROOT, output, paths, "synthetic-freeze")
                original = {p.relative_to(output).as_posix(): p.read_bytes() for p in output.rglob("*") if p.is_file()}
                with self.assertRaises(FileExistsError):
                    m.run_reproduction(ROOT, output, paths, "synthetic-freeze")
                self.assertEqual(original, {p.relative_to(output).as_posix(): p.read_bytes()
                    for p in output.rglob("*") if p.is_file()})
            self.assertEqual(m.read(output / "reproduction-failure.json")["stage"], "original_account_replay")

    def test_verifier_failure_is_separately_retained_after_original_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            contract, paths, documents = synthetic_contract(base)
            output = base / "attempt"
            with patch.object(m, "check_registration", return_value=(contract, {})), \
                 patch.object(m, "replay_original", side_effect=lambda out, inputs: write_documents(out, documents, False)), \
                 patch.object(m, "verify_reproduced", side_effect=ValueError("synthetic checker failure")), redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, "synthetic checker failure"):
                    m.run_reproduction(ROOT, output, paths, "synthetic-freeze")
            self.assertEqual(m.read(output / "reproduction-failure.json")["stage"], "frozen_corrected_verification")
            self.assertTrue((output / "account-replay/account-replay.json").is_file())
            self.assertFalse((output / "reproduction-verification.json").exists())

    def test_changed_reproduced_byte_cannot_be_accepted_after_mocked_verifier_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            contract, paths, documents = synthetic_contract(base)
            output = base / "attempt"
            def altered(root, out, inputs, specs):
                write_documents(out, documents, True)
                with (out / "account-replay/account-replay.json").open("ab") as handle:
                    handle.write(b" ")
            with patch.object(m, "check_registration", return_value=(contract, {})), \
                 patch.object(m, "replay_original", side_effect=lambda out, inputs: write_documents(out, documents, False)), \
                 patch.object(m, "verify_reproduced", side_effect=altered), redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, "reproduced bytes differ"):
                    m.run_reproduction(ROOT, output, paths, "synthetic-freeze")
            self.assertEqual(m.read(output / "reproduction-failure.json")["stage"], "exact_byte_comparison")
            self.assertFalse((output / "reproduction-freeze.json").exists())

    def test_extra_output_and_mutated_receipt_are_rejected(self):
        for mode in ("extra", "receipt"):
            with tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                contract, _, documents = synthetic_contract(base)
                output = base / "attempt"
                receipt = m.begin_attempt(ROOT, output, contract, "synthetic-freeze")
                write_documents(output, documents, False)
                write_documents(output, documents, True)
                if mode == "extra":
                    (output / "unregistered.json").write_text("{}")
                else:
                    (output / "reproduction-attempt.json").write_bytes(m.encoded(m.seal({"mutated": True})))
                with self.assertRaises(ValueError):
                    m.finish_attempt(output, contract, receipt, "synthetic-freeze")

    def test_bad_authority_or_internal_output_never_starts_an_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "attempt"
            with patch.object(m, "check_registration", side_effect=ValueError("wrong registration")):
                with self.assertRaisesRegex(ValueError, "wrong registration"):
                    m.run_reproduction(ROOT, output, {}, "bad")
            self.assertFalse(output.exists())
            with self.assertRaisesRegex(ValueError, "external nonsymlink"):
                m.begin_attempt(ROOT, ROOT / "forbidden-test-reproduction", {}, "pin")

    def test_symlink_output_is_rejected_without_touching_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "existing"
            destination.mkdir()
            link = root / "link"
            link.symlink_to(destination, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "nonsymlink"):
                m.begin_attempt(ROOT, link, {}, "pin")
            self.assertEqual(list(destination.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
