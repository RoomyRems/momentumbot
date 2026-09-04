from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from momentumbot.research import sealed_historical_source_authorization_v12 as authorization


ROOT = Path(__file__).resolve().parents[1]


class SealedHistoricalSourceAuthorizationV12Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = json.loads(
            (ROOT / authorization.AUTHORIZATION_PATH).read_text(encoding="utf-8")
        )

    def test_frozen_authorization_and_parent_bundle_validate(self) -> None:
        authorization.validate_authorization(self.payload)
        parent = authorization.validate_parent_bundle()
        self.assertEqual(
            parent["v0_10_failure_audit"]["conclusion"],
            "fail_closed_final_summarizer_identity_scope_mismatch",
        )
        self.assertEqual(
            parent["v0_11_failure_audit"]["conclusion"],
            "fail_closed_same_step_virtualenv_interpreter_scope_mismatch",
        )
        self.assertEqual(
            parent["v0_11_failure_audit"]["failure_artifact"]["artifact_id"],
            9_957_636_441,
        )

    def test_provider_authority_is_exactly_zero(self) -> None:
        provider = self.payload["provider_free_contract"]
        self.assertEqual(provider["allowed_provider_entrypoints"], [])
        self.assertEqual(provider["credential_environment_variables_allowed"], [])
        self.assertEqual(provider["provider_calls_authorized"], 0)
        self.assertEqual(
            self.payload["request_accounting"][
                "additional_provider_http_attempts_authorized"
            ],
            0,
        )
        self.assertTrue(
            self.payload["repair_boundary"][
                "same_step_environment_comparison_uses_explicit_v0_12_interpreter"
            ]
        )
        self.assertEqual(self.payload["failed_execution"]["provider_calls"], 0)

    def test_authorization_tampering_fails_before_semantic_checks(self) -> None:
        changed = deepcopy(self.payload)
        changed["provider_free_contract"]["provider_calls_authorized"] = 1
        with self.assertRaisesRegex(ValueError, "content hash changed"):
            authorization.validate_authorization(changed)

    def test_registration_is_hash_bound_to_every_declared_artifact(self) -> None:
        audit = authorization.validate_registration_bundle()
        self.assertEqual(
            set(audit["artifacts"]),
            set(authorization.REGISTRATION_ARTIFACT_PATHS),
        )

    def test_full_loader_closes_authorization_parent_and_registration(self) -> None:
        observed = authorization.load_authorization(
            ROOT / authorization.AUTHORIZATION_PATH
        )
        self.assertEqual(
            observed["content_sha256"],
            authorization.AUTHORIZATION_CONTENT_SHA256,
        )


if __name__ == "__main__":
    unittest.main()
