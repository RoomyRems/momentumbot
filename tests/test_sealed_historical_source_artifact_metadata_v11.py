from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from momentumbot.research import sealed_historical_source_artifact_metadata_v11 as metadata


def _payload() -> dict[str, object]:
    return {
        "id": metadata.ARTIFACT_ID,
        "name": metadata.ARTIFACT_NAME,
        "digest": metadata.ARTIFACT_DIGEST,
        "size_in_bytes": metadata.ARTIFACT_SIZE_BYTES,
        "expired": False,
        "workflow_run": {
            "id": metadata.PARENT_RUN_ID,
            "head_sha": metadata.PARENT_HEAD_SHA,
        },
    }


class SealedHistoricalSourceArtifactMetadataV11Tests(unittest.TestCase):
    def test_exact_metadata_returns_hash_bound_receipt(self) -> None:
        receipt = metadata.validate_parent_artifact_metadata_v11(_payload())
        self.assertEqual(receipt["artifact"]["id"], metadata.ARTIFACT_ID)
        self.assertTrue(receipt["metadata_fetched_once"])
        self.assertEqual(receipt["provider_calls"], 0)

    def test_each_identity_field_is_exact(self) -> None:
        changes = {
            "id": metadata.ARTIFACT_ID + 1,
            "name": metadata.ARTIFACT_NAME + "-changed",
            "digest": "sha256:" + "0" * 64,
            "size_in_bytes": metadata.ARTIFACT_SIZE_BYTES + 1,
            "expired": True,
        }
        for field, value in changes.items():
            payload = _payload()
            payload[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                ValueError, field
            ):
                metadata.validate_parent_artifact_metadata_v11(payload)

    def test_parent_run_and_head_are_exact(self) -> None:
        for field, value in (
            ("id", metadata.PARENT_RUN_ID + 1),
            ("head_sha", "0" * 40),
        ):
            payload = _payload()
            payload["workflow_run"][field] = value  # type: ignore[index]
            with self.subTest(field=field), self.assertRaisesRegex(
                ValueError, f"workflow_run.{field}"
            ):
                metadata.validate_parent_artifact_metadata_v11(payload)

    def test_loader_rejects_duplicate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "metadata.json"
            path.write_text('{"id":1,"id":2}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                metadata.load_and_validate_parent_artifact_metadata_v11(path)

    def test_frozen_fixture_validates(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "research/data-audits/"
            "sealed-historical-source-acquisition-v0.11-parent-artifact-"
            "metadata-2026-09-04.json"
        )
        receipt = metadata.load_and_validate_parent_artifact_metadata_v11(path)
        self.assertEqual(receipt["artifact"]["digest"], metadata.ARTIFACT_DIGEST)


if __name__ == "__main__":
    unittest.main()
