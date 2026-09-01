from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from momentumbot import historical_float_v04 as float_parent
from momentumbot.historical_float_identity_v06 import candidate_identity_v06
from momentumbot.historical_float_identity_v07 import (
    ARTIFACT_ID,
    EXPECTED_CANDIDATE_COUNT,
    EXPECTED_DATES,
    EXPECTED_FLOAT_RECORD_COUNT,
    EXPECTED_FLOAT_ROOT_CONTENT_SHA256,
    EXPECTED_KIND_COUNTS,
    EXPECTED_MARKET_ROOT_CONTENT_SHA256,
    authoritative_float_identity_v07,
    canonical_fingerprint,
    validate_downstream_identity_preflight_receipt,
)
from scripts import build_causal_news_enrichment_v07 as news_adapter
from scripts import build_causal_scanner_snapshot_v07 as scanner_adapter


def _fallback_candidate() -> dict[str, object]:
    return {
        "symbol": "CHEB",
        "selected_cik": "0002016420",
        "selected_composite_figi": "",
        "identity_identifier_kind": "unique_cik_fallback",
        "identity_identifier": "0002016420",
    }


def _receipt() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "artifact_id": ARTIFACT_ID,
        "dates": list(EXPECTED_DATES),
        "candidate_count": EXPECTED_CANDIDATE_COUNT,
        "float_record_count": EXPECTED_FLOAT_RECORD_COUNT,
        "identity_kind_counts": EXPECTED_KIND_COUNTS,
        "accepted_identity_kinds": list(EXPECTED_KIND_COUNTS),
        "source_market_root_content_sha256": EXPECTED_MARKET_ROOT_CONTENT_SHA256,
        "source_float_root_content_sha256": EXPECTED_FLOAT_ROOT_CONTENT_SHA256,
        "downstream_loaders": [
            "publication_timed_news",
            "canonical_scanner_source_inputs",
        ],
        "causal_boundary": {
            "float_records_rewritten": False,
            "identity_values_rewritten": False,
            "provider_calls_performed": False,
            "strategy_or_float_threshold_changed": False,
            "transcript_or_label_values_read": False,
        },
    }
    payload["content_sha256"] = canonical_fingerprint(payload)
    return payload


class DownstreamIdentityV07Tests(unittest.TestCase):
    def test_legacy_failure_is_reproduced_and_scope_restores_parent(self) -> None:
        candidate = _fallback_candidate()
        original = float_parent._candidate_identity
        with self.assertRaisesRegex(ValueError, "kind is unsupported"):
            original(candidate)
        with authoritative_float_identity_v07():
            self.assertIs(float_parent._candidate_identity, candidate_identity_v06)
            self.assertEqual(float_parent._candidate_identity(candidate), candidate)
        self.assertIs(float_parent._candidate_identity, original)

    def test_scope_restores_parent_after_exception(self) -> None:
        original = float_parent._candidate_identity
        with self.assertRaisesRegex(RuntimeError, "stop"):
            with authoritative_float_identity_v07():
                raise RuntimeError("stop")
        self.assertIs(float_parent._candidate_identity, original)

    def test_receipt_is_exact_and_tamper_evident(self) -> None:
        receipt = _receipt()
        self.assertEqual(validate_downstream_identity_preflight_receipt(receipt), receipt)
        changed = dict(receipt)
        changed["float_record_count"] = 945
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            validate_downstream_identity_preflight_receipt(changed)

    def test_news_and_scanner_adapters_preflight_before_parent(self) -> None:
        for adapter in (news_adapter, scanner_adapter):
            calls: list[str] = []

            def parent_main(arguments: list[str]) -> int:
                calls.append("parent")
                self.assertIs(float_parent._candidate_identity, candidate_identity_v06)
                self.assertIn("--census-root", arguments)
                return 0

            with self.subTest(adapter=adapter.__name__), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                with patch.object(
                    adapter,
                    "build_downstream_identity_preflight_receipt",
                    side_effect=lambda _root: calls.append("preflight") or _receipt(),
                ), patch.object(adapter.parent, "main", side_effect=parent_main):
                    self.assertEqual(
                        adapter.main(["--census-root", str(root), "--dates", "2025-05-30"]),
                        0,
                    )
            self.assertEqual(calls, ["preflight", "parent"])

    def test_adapter_restores_identity_after_parent_failure(self) -> None:
        original = float_parent._candidate_identity
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            news_adapter,
            "build_downstream_identity_preflight_receipt",
            return_value=_receipt(),
        ), patch.object(
            news_adapter.parent,
            "main",
            side_effect=RuntimeError("stop"),
        ):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                news_adapter.main(["--census-root", temporary])
        self.assertIs(float_parent._candidate_identity, original)


if __name__ == "__main__":
    unittest.main()
