from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from momentumbot.research import sealed_historical_source_recovery_v06 as recovery


class SealedHistoricalSourceRecoveryV06Tests(unittest.TestCase):
    def test_environment_pair_separates_dependencies_from_checkout_commit(self) -> None:
        parent_commit = recovery.PARENT_AUTHORIZATION_COMMIT_SHA
        child_commit = "b" * 40
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
                recovery,
                "PARENT_ENVIRONMENT_FREEZE_SHA256",
                recovery.file_sha256(parent),
            ):
                result = recovery.validate_recovery_environment_pair(
                    parent_environment_freeze_path=parent,
                    child_environment_freeze_path=child,
                    expected_child_commit_sha=child_commit,
                )
                self.assertEqual(result["child_project_commit_sha"], child_commit)
                child.write_text(
                    child.read_text(encoding="utf-8").replace(
                        "numpy==2.3.5", "numpy==2.3.4"
                    ),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ValueError, "differs from parent"):
                    recovery.validate_recovery_environment_pair(
                        parent_environment_freeze_path=parent,
                        child_environment_freeze_path=child,
                        expected_child_commit_sha=child_commit,
                    )

    def _parent(self, root: Path) -> None:
        (root / "provider-checkpoint/environment").mkdir(parents=True)
        (root / "source").mkdir()
        for relative in (
            "provider-checkpoint/environment/pip-freeze.txt",
            "provider-checkpoint/environment/requirements-sealed-source-v04.txt",
        ):
            (root / relative).write_text("fixture\n", encoding="utf-8")
        (root / "safe-failure.json").write_text("{}\n", encoding="utf-8")
        (root / "consumption.json").write_text("{}\n", encoding="utf-8")

    def test_materialization_copies_only_validated_source_and_seeds_budget(self) -> None:
        receipt = {
            "artifact_id": recovery.ARTIFACT_ID,
            "source_commitment": {
                "tree_content_sha256": "a" * 64,
                "file_count": 1,
                "directory_count": 0,
                "retained_file_bytes": 3,
            },
            "content_sha256": "b" * 64,
        }
        commitment = {
            "tree_content_sha256": "a" * 64,
            "file_count": 1,
            "directory_count": 0,
            "retained_file_bytes": 3,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = root / "parent"
            parent.mkdir()
            (parent / "source").mkdir()
            (parent / "source/file").write_text("abc", encoding="utf-8")
            output = root / "output"
            receipt_path = root / "recovery.json"
            budget = root / "budget.json"
            blocked = root / "blocked.json"
            with patch.object(
                recovery,
                "validate_parent_failure_checkpoint",
                return_value=receipt,
            ), patch.object(
                recovery,
                "_source_tree_commitment",
                return_value=commitment,
            ):
                observed = recovery.materialize_parent_recovery(
                    parent,
                    source_output=output,
                    recovery_receipt_output=receipt_path,
                    request_budget_output=budget,
                    blocked_attempt_output=blocked,
                )
            self.assertEqual(observed, receipt)
            self.assertEqual((output / "file").read_text(encoding="utf-8"), "abc")
            self.assertEqual(
                json.loads(budget.read_text(encoding="utf-8")),
                recovery.PARENT_REQUEST_BUDGET,
            )
            self.assertEqual(
                json.loads(blocked.read_text(encoding="utf-8"))[
                    "total_blocked_attempts"
                ],
                0,
            )

    def test_existing_output_prevents_recovery_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = root / "parent"
            parent.mkdir()
            (parent / "source").mkdir()
            output = root / "output"
            output.mkdir()
            with patch.object(
                recovery,
                "validate_parent_failure_checkpoint",
                return_value={"source_commitment": {}},
            ):
                with self.assertRaisesRegex(FileExistsError, "already exists"):
                    recovery.materialize_parent_recovery(
                        parent,
                        source_output=output,
                        recovery_receipt_output=root / "recovery.json",
                        request_budget_output=root / "budget.json",
                        blocked_attempt_output=root / "blocked.json",
                    )

    def test_self_hash_rejects_tampering_and_duplicate_json_keys(self) -> None:
        payload = {"value": 1}
        payload["content_sha256"] = recovery.canonical_fingerprint(payload)
        recovery._validate_self_hash(payload, label="fixture")
        tampered = deepcopy(payload)
        tampered["value"] = 2
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            recovery._validate_self_hash(tampered, label="fixture")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                recovery.load_json_object(path)


if __name__ == "__main__":
    unittest.main()
