from __future__ import annotations

from copy import deepcopy
import unittest

from momentumbot.research import sealed_historical_source_authorization_v13 as auth


class AuthorizationV13Tests(unittest.TestCase):
    def test_frozen_child_and_every_registered_file_validate(self) -> None:
        payload = auth.load_authorization(auth.ROOT / auth.AUTHORIZATION_PATH)
        self.assertEqual(payload["authorization_id"], auth.AUTHORIZATION_ID)
        self.assertEqual(payload["failed_execution"]["workflow_run_id"], 33929860053)
        self.assertEqual(payload["failed_parent"]["provider_checkpoint_artifact_id"], 9877181150)
        self.assertFalse(auth.validate_registration_bundle()["launch_allowed"])

    def test_provider_policy_and_parent_ledger_remain_frozen(self) -> None:
        payload = auth.load_authorization(auth.ROOT / auth.AUTHORIZATION_PATH)
        for key in ("authority_boundary", "causal_boundary", "cost_ceiling", "downstream_contract", "request_accounting", "one_shot_contract", "provider_free_contract", "recovery_contract"):
            self.assertEqual(payload[key], auth.parent.load_authorization(auth.ROOT / auth.parent.AUTHORIZATION_PATH)[key])
        self.assertEqual(payload["request_accounting"]["frozen_total_attempts"], 30522)
        self.assertEqual(payload["provider_free_contract"]["provider_calls_authorized"], 0)

    def test_changed_or_rehashed_authorization_cannot_add_authority(self) -> None:
        payload = auth.load_authorization(auth.ROOT / auth.AUTHORIZATION_PATH)
        changed = deepcopy(payload)
        changed["provider_free_contract"]["provider_calls_authorized"] = 1
        for rehash in (False, True):
            if rehash:
                changed["content_sha256"] = auth.canonical_fingerprint({k: v for k, v in changed.items() if k != "content_sha256"})
            with self.assertRaisesRegex(ValueError, "content hash changed"):
                auth.validate_authorization(changed)


if __name__ == "__main__":
    unittest.main()
