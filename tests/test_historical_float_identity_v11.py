from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from momentumbot import historical_float_v04 as float_parent
from momentumbot.historical_float_identity_v06 import candidate_identity_v06
from momentumbot import historical_float_identity_v11 as identity


def _fallback_candidate() -> dict[str, object]:
    return {
        "symbol": "CHEB",
        "selected_cik": "0002016420",
        "selected_composite_figi": "",
        "identity_identifier_kind": "unique_cik_fallback",
        "identity_identifier": "0002016420",
    }


def _legacy_receipt() -> dict[str, object]:
    return {
        "candidate_count": identity.EXPECTED_CANDIDATE_COUNT,
        "float_record_count": identity.EXPECTED_FLOAT_RECORD_COUNT,
        "identity_kind_counts": identity.EXPECTED_KIND_COUNTS,
        "accepted_identity_kinds": list(identity.EXPECTED_KIND_COUNTS),
        "source_market_root_content_sha256": (
            identity.EXPECTED_MARKET_ROOT_CONTENT_SHA256
        ),
        "source_float_root_content_sha256": (
            identity.EXPECTED_FLOAT_ROOT_CONTENT_SHA256
        ),
        "content_sha256": "a" * 64,
    }


class HistoricalFloatIdentityV11Tests(unittest.TestCase):
    def test_legacy_failure_is_reproduced_and_scope_restores_parent(self) -> None:
        candidate = _fallback_candidate()
        original = float_parent._candidate_identity
        with self.assertRaisesRegex(ValueError, "kind is unsupported"):
            original(candidate)
        with identity.authoritative_float_identity_v11():
            self.assertIs(float_parent._candidate_identity, candidate_identity_v06)
            self.assertEqual(float_parent._candidate_identity(candidate), candidate)
        self.assertIs(float_parent._candidate_identity, original)

    def test_scope_restores_parent_after_exception(self) -> None:
        original = float_parent._candidate_identity
        with self.assertRaisesRegex(RuntimeError, "stop"):
            with identity.authoritative_float_identity_v11():
                raise RuntimeError("stop")
        self.assertIs(float_parent._candidate_identity, original)

    def test_final_preflight_preserves_full_authoritative_census(self) -> None:
        with patch.object(
            identity,
            "build_downstream_identity_preflight_receipt",
            return_value=_legacy_receipt(),
        ):
            receipt = identity.build_final_identity_preflight_receipt(Path("source"))
        self.assertEqual(receipt["candidate_count"], 946)
        self.assertEqual(
            receipt["identity_kind_counts"],
            {"composite_figi": 737, "unique_cik_fallback": 209},
        )
        self.assertEqual(
            identity.validate_final_identity_preflight_receipt(receipt), receipt
        )

    def test_final_summarizer_is_the_only_protected_loader(self) -> None:
        original = float_parent._candidate_identity
        receipt = {"content_sha256": "b" * 64}

        def summarize(*_args: object, **_kwargs: object) -> dict[str, object]:
            self.assertIs(float_parent._candidate_identity, candidate_identity_v06)
            return {"status": "ok"}

        with patch.object(
            identity,
            "build_final_identity_preflight_receipt",
            return_value=receipt,
        ), patch.object(identity, "summarize_source_root_v04", side_effect=summarize):
            summary, observed = identity.summarize_source_root_identity_compatible_v11(
                "source", profile=object()  # type: ignore[arg-type]
            )
        self.assertEqual(summary, {"status": "ok"})
        self.assertIs(observed, receipt)
        self.assertIs(float_parent._candidate_identity, original)

    def test_final_summarizer_restores_identity_after_failure(self) -> None:
        original = float_parent._candidate_identity
        with patch.object(
            identity,
            "build_final_identity_preflight_receipt",
            return_value={"content_sha256": "b" * 64},
        ), patch.object(
            identity,
            "summarize_source_root_v04",
            side_effect=RuntimeError("stop"),
        ), self.assertRaisesRegex(RuntimeError, "stop"):
            identity.summarize_source_root_identity_compatible_v11(
                "source", profile=object()  # type: ignore[arg-type]
            )
        self.assertIs(float_parent._candidate_identity, original)


if __name__ == "__main__":
    unittest.main()
