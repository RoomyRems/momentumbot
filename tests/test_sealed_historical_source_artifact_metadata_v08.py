from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from momentumbot.research import sealed_historical_source_artifact_metadata_v08 as metadata


ROOT = Path(__file__).resolve().parents[1]


def _payload() -> dict[str, object]:
    return {
        "id": metadata.ARTIFACT_ID,
        "name": metadata.ARTIFACT_NAME,
        "digest": metadata.ARTIFACT_DIGEST,
        "size_in_bytes": metadata.ARTIFACT_SIZE_BYTES,
        "expired": False,
        "workflow_run": {"id": metadata.PARENT_RUN_ID},
        "created_at": "ignored-but-allowed",
    }


class SealedHistoricalSourceArtifactMetadataV08Tests(unittest.TestCase):
    def test_exact_metadata_builds_hash_bound_provider_free_receipt(self) -> None:
        receipt = metadata.validate_parent_artifact_metadata_v08(_payload())
        body = dict(receipt)
        claimed = body.pop("content_sha256")
        self.assertEqual(claimed, metadata.canonical_fingerprint(body))
        self.assertEqual(receipt["provider_calls"], 0)
        self.assertTrue(receipt["metadata_fetched_once"])

    def test_each_security_relevant_field_fails_with_field_only_diagnostic(self) -> None:
        cases = {
            "id": 1,
            "name": "wrong",
            "digest": "sha256:" + "0" * 64,
            "size_in_bytes": 1,
            "expired": True,
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                changed = deepcopy(_payload())
                changed[field] = value
                with self.assertRaisesRegex(ValueError, rf"field {field} changed") as ctx:
                    metadata.validate_parent_artifact_metadata_v08(changed)
                self.assertNotIn(str(value), str(ctx.exception))

        changed = deepcopy(_payload())
        changed["workflow_run"] = {"id": 1}
        with self.assertRaisesRegex(ValueError, r"field workflow_run\.id changed"):
            metadata.validate_parent_artifact_metadata_v08(changed)

    def test_type_confusion_duplicate_keys_nonfinite_and_symlink_fail_closed(self) -> None:
        for field, value in (("id", True), ("size_in_bytes", True), ("expired", 0)):
            with self.subTest(field=field):
                changed = deepcopy(_payload())
                changed[field] = value
                with self.assertRaises(ValueError):
                    metadata.validate_parent_artifact_metadata_v08(changed)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            duplicate = root / "duplicate.json"
            duplicate.write_text('{"id":1,"id":2}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                metadata.load_and_validate_parent_artifact_metadata_v08(duplicate)
            nonfinite = root / "nonfinite.json"
            nonfinite.write_text('{"id":NaN}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-finite JSON"):
                metadata.load_and_validate_parent_artifact_metadata_v08(nonfinite)
            valid = root / "valid.json"
            valid.write_text(json.dumps(_payload()), encoding="utf-8")
            link = root / "link.json"
            link.symlink_to(valid)
            with self.assertRaisesRegex(ValueError, "regular file"):
                metadata.load_and_validate_parent_artifact_metadata_v08(link)

    def test_direct_entrypoint_succeeds_and_writes_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "metadata.json"
            output = root / "receipt.json"
            source.write_text(json.dumps(_payload()), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/validate_parent_artifact_metadata_v08.py",
                    "--metadata-json",
                    str(source),
                    "--receipt-output",
                    str(output),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            receipt = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(receipt["artifact"]["id"], metadata.ARTIFACT_ID)

    def test_direct_entrypoint_sanitizes_observed_values_and_structural_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "metadata.json"
            output = root / "receipt.json"
            changed = _payload()
            changed["name"] = "DO_NOT_EXPOSE_THIS_VALUE"
            source.write_text(json.dumps(changed), encoding="utf-8")
            command = [
                sys.executable,
                "scripts/validate_parent_artifact_metadata_v08.py",
                "--metadata-json",
                str(source),
                "--receipt-output",
                str(output),
            ]
            completed = subprocess.run(
                command,
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 1)
            self.assertIn("field name changed", completed.stderr)
            self.assertNotIn("DO_NOT_EXPOSE_THIS_VALUE", completed.stderr)

            source.write_text(
                '{"DO_NOT_EXPOSE_THIS_KEY":1,"DO_NOT_EXPOSE_THIS_KEY":2}',
                encoding="utf-8",
            )
            completed = subprocess.run(
                command,
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 1)
            self.assertIn("document is malformed", completed.stderr)
            self.assertNotIn("DO_NOT_EXPOSE_THIS_KEY", completed.stderr)


if __name__ == "__main__":
    unittest.main()
