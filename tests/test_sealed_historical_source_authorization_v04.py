from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import momentumbot.research.sealed_historical_source_authorization_v04 as auth_v04
from momentumbot.research.sealed_historical_source_acquisition_v03 import (
    expected_authorization_body as expected_v03_authorization_body,
)
from momentumbot.research.sealed_historical_walk_forward import (
    canonical_fingerprint,
    load_json_object,
)


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = (
    ROOT / "research/strategy/sealed-historical-source-acquisition-v0.4.json"
)
DOCUMENT = ROOT / "docs/research/sealed_historical_source_acquisition_v04.md"


class SealedHistoricalSourceAuthorizationV04Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.authorization = auth_v04.load_authorization(AUTHORIZATION)

    def test_authorization_hash_id_and_required_api_are_frozen(self) -> None:
        body = dict(self.authorization)
        claimed = body.pop("content_sha256")
        self.assertEqual(claimed, auth_v04.AUTHORIZATION_CONTENT_SHA256)
        self.assertEqual(claimed, canonical_fingerprint(body))
        self.assertEqual(
            self.authorization["authorization_id"],
            auth_v04.AUTHORIZATION_ID,
        )
        self.assertEqual(body, auth_v04.expected_authorization_body())
        self.assertEqual(
            list(inspect.signature(auth_v04.validate_parent_bundle).parameters),
            [],
        )

    def test_child_preserves_v03_dates_authority_cost_and_hard_ceilings(self) -> None:
        child = auth_v04.expected_authorization_body()
        parent = expected_v03_authorization_body()
        for key in (
            "authority_boundary",
            "causal_boundary",
            "cost_ceiling",
            "credential_routing",
        ):
            self.assertEqual(child[key], parent[key])
        self.assertEqual(
            child["frozen_parent"]["selected_dates"],
            parent["frozen_parent"]["selected_dates"],
        )
        self.assertEqual(
            child["request_budget"][
                "maximum_total_http_attempts_including_retries"
            ],
            40_000,
        )
        self.assertEqual(
            child["request_budget"]["allowed_hosts"],
            parent["request_budget"]["allowed_hosts"],
        )
        self.assertEqual(
            child["retention_budget"]["maximum_retained_bytes"],
            1_500_000_000,
        )
        self.assertFalse(
            child["retention_budget"]["raw_provider_http_responses_persisted"]
        )
        self.assertEqual(
            child["cost_ceiling"],
            {
                "incremental_provider_cost_usd": "0",
                "databento_calls_authorized": 0,
                "paid_acquisition_authorized": False,
            },
        )

        reconstructed_request = copy.deepcopy(child["request_budget"])
        reconstructed_request.pop("candidate_operational_ceiling")
        reconstructed_request.pop("provider_routes")
        reconstructed_request["sec"]["maximum_candidates_per_date"] = 50
        reconstructed_request["news"]["maximum_candidates_per_date"] = 50
        self.assertEqual(reconstructed_request, parent["request_budget"])

        reconstructed_retention = copy.deepcopy(child["retention_budget"])
        reconstructed_retention.pop("pre_scanner_source_checkpoint_persisted")
        reconstructed_retention.pop(
            "upstream_progress_artifact_persisted_before_canonical_source_inputs"
        )
        reconstructed_retention.pop("pinned_requirements_persisted")
        reconstructed_retention.pop("pip_freeze_persisted")
        self.assertEqual(reconstructed_retention, parent["retention_budget"])

    def test_repair_contract_is_explicit_and_does_not_change_profiles(self) -> None:
        child = auth_v04.expected_authorization_body()
        normalization = child["normalization_contract"]
        scanner = normalization["scanner_policy"]
        self.assertEqual(scanner["displayed_price_validation_source"], "raw_target_close")
        self.assertEqual(scanner["cumulative_volume_validation_source"], "raw_target_volume")
        self.assertEqual(
            scanner["percent_gain_validation_source"],
            "split_target_close_over_split_previous_close",
        )
        self.assertEqual(
            scanner["cross_sectional_rank_source"],
            "split_target_close_over_split_previous_close",
        )
        self.assertTrue(
            normalization["validator_gain_compared_with_split_target_price"]
        )
        self.assertFalse(
            normalization["validator_gain_compared_with_raw_display_price"]
        )

        profile_union = child["acquisition_profile_union_contract"]
        profile = profile_union["acquisition_profile"]
        self.assertEqual(profile["min_price"], 1.5)
        self.assertEqual(profile["max_price"], 20.0)
        self.assertEqual(profile["min_percent_gain"], 10.0)
        self.assertEqual(profile["min_relative_volume"], 5.0)
        self.assertTrue(all(profile_union["coverage"].values()))
        self.assertFalse(profile_union["general_strategy_profile_changed"])
        self.assertFalse(profile_union["small_account_strategy_profile_changed"])

        cap = child["request_budget"]["candidate_operational_ceiling"]
        self.assertEqual(cap["parent_maximum_candidates_per_date"], 50)
        self.assertEqual(cap["maximum_candidates_per_date"], 100)
        self.assertFalse(cap["silent_truncation_allowed"])
        self.assertFalse(cap["strategy_threshold_changed"])

        float_contract = child["float_normalization_contract"]
        self.assertEqual(
            float_contract["measure_to_target_share_factor"],
            "A_measure_div_A_target",
        )
        self.assertEqual(
            float_contract["target_pair_source"],
            "exact_market_qualification_minute_raw_and_split_close",
        )
        self.assertFalse(float_contract["later_target_session_price_allowed"])

    def test_one_shot_provider_checkpoint_and_environment_boundaries(self) -> None:
        child = auth_v04.expected_authorization_body()
        one_shot = child["one_shot_contract"]
        self.assertEqual(one_shot["workflow_run_attempt_required"], 1)
        self.assertTrue(one_shot["manual_workflow_dispatch_required"])
        self.assertFalse(one_shot["automatic_rerun_allowed"])
        self.assertFalse(one_shot["push_or_schedule_provider_access_allowed"])
        self.assertEqual(
            one_shot["prior_authorization_reruns_allowed"],
            {"v0.1": False, "v0.2": False, "v0.3": False},
        )
        self.assertFalse(one_shot["provider_substitution_allowed"])

        wrapper = child["provider_entrypoint_contract"]
        self.assertTrue(wrapper["disallowed_host_fails_before_network_access"])
        self.assertFalse(wrapper["redirects_allowed"])
        self.assertTrue(
            wrapper["redirects_rejected_before_follow_up_network_access"]
        )
        self.assertFalse(wrapper["ambient_proxy_use_allowed"])
        self.assertTrue(wrapper["direct_https_transport_only"])
        self.assertFalse(wrapper["direct_socket_or_process_escape_allowed"])
        self.assertTrue(wrapper["blocked_attempt_ledger_sanitized"])
        self.assertTrue(
            wrapper["blocked_request_budget_attempts_define_ceiling_exhaustion"]
        )
        self.assertTrue(
            wrapper["successful_provider_checkpoint_requires_zero_blocked_attempts"]
        )
        self.assertFalse(wrapper["provider_substitution_allowed"])
        self.assertEqual(
            wrapper["allowed_hosts"],
            child["request_budget"]["allowed_hosts"],
        )

        checkpoint = child["pre_scanner_checkpoint_contract"]
        self.assertTrue(checkpoint["upload_completed_before_scanner_loader_or_validator"])
        self.assertFalse(checkpoint["contains_scanner_snapshots"])
        self.assertFalse(checkpoint["checkpoint_builder_provider_calls_allowed"])
        environment = child["reproducibility_environment_contract"]
        self.assertEqual(
            environment["requirements_path"],
            "requirements-sealed-source-v04.txt",
        )
        self.assertTrue(environment["pip_freeze_captured_before_provider_access"])
        self.assertTrue(environment["clean_virtual_environment_required_per_job"])
        self.assertTrue(environment["requirements_hashes_required"])
        self.assertTrue(environment["binary_wheels_only"])
        self.assertFalse(environment["source_distributions_allowed"])
        self.assertTrue(environment["pip_check_required"])
        self.assertFalse(environment["environment_reuse_after_checkpoint_required"])
        self.assertTrue(
            environment["provider_free_freeze_environment_must_byte_match_checkpoint"]
        )
        self.assertEqual(environment["runner_image"], "ubuntu-24.04")
        self.assertEqual(environment["python_version"], "3.12")
        dispatcher = child["dispatcher_contract"]
        self.assertEqual(
            dispatcher["workflow_ref"], auth_v04.EXPECTED_DISPATCHER_WORKFLOW_REF
        )
        self.assertTrue(dispatcher["provider_free_freeze_is_separate_job"])
        self.assertEqual(dispatcher["canonical_source_step_timeout_minutes"], 150)
        self.assertFalse(
            dispatcher["provider_credentials_allowed_in_consume_or_freeze_job"]
        )
        self.assertTrue(dispatcher["contents_write_allowed_only_in_consumption_job"])
        self.assertTrue(
            one_shot[
                "repository_consumption_tag_created_atomically_before_provider_access"
            ]
        )
        self.assertEqual(
            one_shot["repository_consumption_tag_prefix"],
            auth_v04.CONSUMPTION_TAG_PREFIX,
        )
        self.assertFalse(one_shot["repository_consumption_tag_deletion_allowed"])
        self.assertLess(
            child["execution_order_contract"].index(
                "build_and_upload_pre_scanner_source_checkpoint"
            ),
            child["execution_order_contract"].index(
                "load_validate_and_freeze_label_blind_scanner_outputs_provider_free"
            ),
        )
        self.assertLess(
            child["execution_order_contract"].index(
                "atomically_create_repository_consumption_tag_before_provider_access"
            ),
            child["execution_order_contract"].index(
                "acquire_exact_frozen_provider_routes_through_pre_network_wrapper"
            ),
        )
        self.assertLess(
            child["execution_order_contract"].index(
                "build_and_upload_pre_scanner_source_checkpoint"
            ),
            child["execution_order_contract"].index(
                "download_checkpoint_in_separate_provider_free_freeze_job"
            ),
        )
        self.assertLess(
            child["execution_order_contract"].index(
                "load_validate_and_freeze_label_blind_scanner_outputs_provider_free"
            ),
            child["execution_order_contract"].index(
                "deep_validate_and_exactly_replay_completed_bundle_provider_free"
            ),
        )

    def test_parent_bundle_loads_repo_files_and_rejects_tampering(self) -> None:
        parents = auth_v04.validate_parent_bundle()
        self.assertEqual(
            set(parents),
            {
                "v0_3_authorization",
                "v0_3_failure_audit",
                "v0_2_success_audit",
            },
        )
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            for relative in (
                auth_v04.V03_AUTHORIZATION_PATH,
                auth_v04.V03_FAILURE_AUDIT_PATH,
                auth_v04.V02_SUCCESS_AUDIT_PATH,
            ):
                destination = temporary_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, destination)
            with patch.object(auth_v04, "ROOT", temporary_root):
                auth_v04.validate_parent_bundle()
                failure_path = temporary_root / auth_v04.V03_FAILURE_AUDIT_PATH
                changed = json.loads(failure_path.read_text(encoding="utf-8"))
                changed["workflow"]["attempt"] = 2
                failure_path.write_text(
                    json.dumps(changed, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ValueError, "failure audit content hash"):
                    auth_v04.validate_parent_bundle()

    def test_registration_binds_exact_provider_free_artifact_census(self) -> None:
        audit = auth_v04.validate_registration_bundle()
        self.assertEqual(
            set(audit["artifacts"]), set(auth_v04.REGISTRATION_ARTIFACT_PATHS)
        )
        self.assertEqual(
            audit["authorization_content_sha256"],
            auth_v04.AUTHORIZATION_CONTENT_SHA256,
        )
        self.assertEqual(audit["causal_attestation"]["provider_calls"], 0)
        self.assertFalse(audit["causal_attestation"]["runtime_started"])

        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            files = {
                auth_v04.REGISTRATION_AUDIT_PATH,
                *auth_v04.REGISTRATION_ARTIFACT_PATHS.values(),
            }
            for relative in files:
                destination = temporary_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, destination)
            target = (
                temporary_root
                / auth_v04.REGISTRATION_ARTIFACT_PATHS["provider_wrapper"]
            )
            target.write_bytes(target.read_bytes() + b"\n")
            with patch.object(auth_v04, "ROOT", temporary_root):
                with self.assertRaisesRegex(
                    ValueError, "provider_wrapper hash changed"
                ):
                    auth_v04.validate_registration_bundle()

    def test_authorization_tamper_and_documented_hashes_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            changed = copy.deepcopy(self.authorization)
            changed["one_shot_contract"]["automatic_rerun_allowed"] = True
            path = Path(temporary) / "authorization.json"
            path.write_text(
                json.dumps(changed, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "authorization hash mismatch"):
                auth_v04.load_authorization(path)

            path.write_text(
                AUTHORIZATION.read_text(encoding="utf-8").replace(
                    '  "authorization_id":',
                    '  "authorization_id": "shadow",\n  "authorization_id":',
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                auth_v04.load_authorization(path)

        text = DOCUMENT.read_text(encoding="utf-8")
        for value in (
            auth_v04.AUTHORIZATION_CONTENT_SHA256,
            auth_v04.V03_AUTHORIZATION_CONTENT_SHA256,
            auth_v04.V03_FAILURE_AUDIT_CONTENT_SHA256,
            auth_v04.V03_FAILURE_ZIP_SHA256,
            auth_v04.V03_CONSUMPTION_MARKER_ZIP_SHA256,
            auth_v04.V02_SUCCESS_AUDIT_CONTENT_SHA256,
            auth_v04.V02_SUCCESS_ZIP_SHA256,
        ):
            self.assertIn(value, text)
        self.assertIn("Run 33449815223", text)
        self.assertIn("scanner loader, deep validation", text)
        self.assertNotIn("automatic rerun may", text.lower())


if __name__ == "__main__":
    unittest.main()
