from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from momentumbot import historical_float_v04 as float_parent
from momentumbot.historical_float_identity_v06 import (
    ARTIFACT_ID,
    candidate_identity_v06,
    validate_identity_preflight_receipt,
)
from scripts import build_causal_float_enrichment_v06 as adapter


def _candidate(*, kind: str, identifier: str, cik: str, figi: str) -> dict[str, object]:
    return {
        "symbol": "CHEB",
        "selected_cik": cik,
        "selected_composite_figi": figi,
        "identity_identifier_kind": kind,
        "identity_identifier": identifier,
    }


class BuildCausalFloatEnrichmentV06Tests(unittest.TestCase):
    def test_authoritative_identity_kinds_are_accepted_without_rewriting(self) -> None:
        figi = _candidate(
            kind="composite_figi",
            identifier="BBG001Y26LK0",
            cik="0001498403",
            figi="BBG001Y26LK0",
        )
        fallback = _candidate(
            kind="unique_cik_fallback",
            identifier="0002016420",
            cik="0002016420",
            figi="",
        )
        self.assertEqual(candidate_identity_v06(figi), figi)
        self.assertEqual(candidate_identity_v06(fallback), fallback)

    def test_obsolete_or_ambiguous_identity_kind_fails_closed(self) -> None:
        invalid = (
            _candidate(kind="cik", identifier="1", cik="1", figi=""),
            _candidate(
                kind="unique_cik_fallback",
                identifier="1",
                cik="1",
                figi="BBG-AMBIGUOUS",
            ),
            _candidate(
                kind="unique_cik_fallback",
                identifier="2",
                cik="1",
                figi="",
            ),
            _candidate(
                kind="composite_figi",
                identifier="BBG-A",
                cik="1",
                figi="BBG-B",
            ),
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    candidate_identity_v06(value)

    def test_adapter_preflights_before_parent_and_restores_legacy_function(self) -> None:
        original = float_parent._candidate_identity
        receipt = {
            "schema_version": 1,
            "artifact_id": ARTIFACT_ID,
            "dates": [],
            "candidate_count": 0,
            "identity_kind_counts": {},
            "accepted_identity_kinds": [],
            "source_market_root_content_sha256": "a" * 64,
            "causal_boundary": {},
            "content_sha256": "b" * 64,
        }
        calls: list[str] = []

        def parent_main(arguments: list[str]) -> int:
            calls.append("parent")
            self.assertIs(float_parent._candidate_identity, candidate_identity_v06)
            self.assertIn("--census-root", arguments)
            return 0

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            with patch.object(
                adapter,
                "build_identity_preflight_receipt",
                side_effect=lambda _root: calls.append("preflight") or receipt,
            ), patch.object(adapter.parent, "main", side_effect=parent_main):
                self.assertEqual(
                    adapter.main(
                        [
                            "--census-root",
                            str(source),
                            "--dates",
                            "2025-05-30",
                        ]
                    ),
                    0,
                )
        self.assertEqual(calls, ["preflight", "parent"])
        self.assertIs(float_parent._candidate_identity, original)

    def test_adapter_restores_legacy_function_after_parent_failure(self) -> None:
        original = float_parent._candidate_identity
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            adapter,
            "build_identity_preflight_receipt",
            return_value={},
        ), patch.object(
            adapter.parent,
            "main",
            side_effect=RuntimeError("stop"),
        ):
            root = Path(temporary)
            root.mkdir(exist_ok=True)
            with self.assertRaisesRegex(RuntimeError, "stop"):
                adapter.main(
                    [
                        "--census-root",
                        str(root),
                    ]
                )
        self.assertIs(float_parent._candidate_identity, original)

    def test_preflight_tampering_is_rejected(self) -> None:
        payload = {
            "schema_version": 1,
            "artifact_id": ARTIFACT_ID,
            "dates": [],
            "candidate_count": 0,
            "identity_kind_counts": {},
            "accepted_identity_kinds": [],
            "source_market_root_content_sha256": "a" * 64,
            "causal_boundary": {},
            "content_sha256": "b" * 64,
        }
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            validate_identity_preflight_receipt(payload)


if __name__ == "__main__":
    unittest.main()
