from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from momentumbot.research import sealed_historical_source_authorization_v05 as auth
from momentumbot.research.sealed_historical_source_checkpoint_v05 import (
    canonical_fingerprint,
)
from scripts.run_sealed_historical_source_acquisition_v05 import (
    _safe_budget,
    _safe_blocked_attempts,
    _strict_provenance,
    build_consumption_marker_v05,
)


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = ROOT / auth.AUTHORIZATION_PATH


class SealedHistoricalSourceAuthorizationV05Tests(unittest.TestCase):
    def test_authorization_hash_identity_and_recovery_boundary_are_frozen(self) -> None:
        payload = auth.load_authorization(AUTHORIZATION)
        body = dict(payload)
        claimed = body.pop("content_sha256")
        self.assertEqual(claimed, auth.AUTHORIZATION_CONTENT_SHA256)
        self.assertEqual(claimed, canonical_fingerprint(body))
        self.assertEqual(body, auth.expected_authorization_body())
        self.assertEqual(payload["authorization_id"], auth.AUTHORIZATION_ID)
        self.assertEqual(
            payload["recovery_contract"]["resume_stage"],
            "target_date_basis_causal_float_inputs",
        )
        self.assertTrue(
            payload["recovery_contract"]["normalized_parent_source_reused_exactly"]
        )
        self.assertFalse(
            payload["recovery_contract"][
                "parent_identity_or_market_provider_requests_repeated"
            ]
        )

    def test_composite_budget_and_candidate_repair_do_not_change_strategy(self) -> None:
        payload = auth.load_authorization(AUTHORIZATION)
        budget = payload["request_budget"]
        self.assertEqual(budget["composite_parent_total_attempts"], 14_524)
        self.assertEqual(
            budget["composite_parent_attempts_by_host"],
            {
                "api.massive.com": 363,
                "data.alpaca.markets": 14_155,
                "data.sec.gov": 6,
            },
        )
        self.assertEqual(
            budget["maximum_total_http_attempts_including_parent_and_child_retries"],
            40_000,
        )
        self.assertEqual(budget["child_massive_calls_authorized"], 0)
        repair = payload["repair_boundary"]
        self.assertEqual(repair["candidate_data_exception_classes"], ["TypeError", "ValueError"])
        self.assertEqual(
            repair["candidate_data_exception_disposition"],
            "unknown_fail_closed_missing_measure_pair",
        )
        self.assertTrue(
            repair[
                "transport_http_pagination_budget_authorization_or_artifact_error_remains_fatal"
            ]
        )
        self.assertFalse(payload["downstream_contract"]["strategy_profiles_or_thresholds_changed"])
        self.assertFalse(payload["causal_boundary"]["strategy_threshold_or_setup_changes_allowed"])
        self.assertEqual(
            payload["provider_entrypoint_contract"]["child_network_hosts"],
            ["data.alpaca.markets", "data.sec.gov"],
        )

    def test_one_shot_dispatcher_and_prior_authorizations_are_closed(self) -> None:
        payload = auth.load_authorization(AUTHORIZATION)
        one_shot = payload["one_shot_contract"]
        self.assertEqual(one_shot["workflow_run_attempt_required"], 1)
        self.assertFalse(one_shot["automatic_rerun_allowed"])
        self.assertFalse(one_shot["push_or_schedule_provider_access_allowed"])
        self.assertEqual(
            one_shot["prior_authorization_reruns_allowed"],
            {"v0.1": False, "v0.2": False, "v0.3": False, "v0.4": False},
        )
        self.assertEqual(
            one_shot["repository_consumption_tag_prefix"],
            auth.CONSUMPTION_TAG_PREFIX,
        )
        self.assertEqual(
            payload["dispatcher_contract"]["workflow_ref"],
            auth.EXPECTED_DISPATCHER_WORKFLOW_REF,
        )
        environment = payload["reproducibility_environment_contract"]
        self.assertTrue(
            environment["parent_artifact_full_replay_required_before_consumption"]
        )
        self.assertTrue(
            environment["parent_third_party_environment_freeze_must_match"]
        )
        self.assertTrue(
            environment[
                "editable_project_lines_must_match_respective_authorized_commits"
            ]
        )

    def test_parent_failure_and_registration_bundles_validate_exact_files(self) -> None:
        parent = auth.validate_parent_bundle()
        self.assertEqual(
            parent["v0_4_failure_audit"]["content_sha256"],
            auth.PARENT_FAILURE_AUDIT_CONTENT_SHA256,
        )
        registration = auth.validate_registration_bundle()
        self.assertEqual(
            set(registration["artifacts"]), set(auth.REGISTRATION_ARTIFACT_PATHS)
        )
        self.assertEqual(
            registration["authorization_content_sha256"],
            auth.AUTHORIZATION_CONTENT_SHA256,
        )

    def test_authorization_duplicate_key_and_tamper_fail_closed(self) -> None:
        payload = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))
        changed = copy.deepcopy(payload)
        changed["request_budget"]["child_massive_calls_authorized"] = 1
        changed["content_sha256"] = canonical_fingerprint(
            {key: value for key, value in changed.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "composite request boundary|frozen hash"):
            auth.validate_authorization(changed)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                auth._load_json_object(path)

    def test_registration_detects_one_bound_file_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = {auth.REGISTRATION_AUDIT_PATH, *auth.REGISTRATION_ARTIFACT_PATHS.values()}
            for relative in paths:
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, target)
            target = root / auth.REGISTRATION_ARTIFACT_PATHS["float_adapter"]
            target.write_bytes(target.read_bytes() + b"\n")
            with patch.object(auth, "ROOT", root), self.assertRaisesRegex(
                ValueError, "float_adapter hash changed"
            ):
                auth.validate_registration_bundle()

    def test_safe_failure_rejects_unsanitized_blocked_hosts(self) -> None:
        categories = {
            name: 0
            for name in (
                "hostname",
                "https_transport",
                "redirect",
                "request_budget",
                "socket",
                "subprocess",
            )
        }
        categories["hostname"] = 1
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "blocked.json"
            for host in ("bad..host", ".bad.host", "bad_host", "café.example"):
                path.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "total_blocked_attempts": 1,
                            "by_category": categories,
                            "by_host": {host: 1},
                        }
                    ),
                    encoding="utf-8",
                )
                with self.subTest(host=host), self.assertRaisesRegex(
                    ValueError, "host count is invalid"
                ):
                    _safe_blocked_attempts(path)

            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "total_blocked_attempts": 1,
                        "by_category": categories,
                        "by_host": {"blocked.example": 1},
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                _safe_blocked_attempts(path)["by_host"], {"blocked.example": 1}
            )

    def test_safe_failure_preserves_ceiling_and_unauthorized_host_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "budget.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "total_attempts": 40_000,
                        "by_host": {
                            "api.massive.com": 363,
                            "data.alpaca.markets": 39_630,
                            "data.sec.gov": 6,
                            "bad..host": 1,
                        },
                    }
                ),
                encoding="utf-8",
            )
            observed = _safe_budget(path)
            self.assertTrue(observed["request_ceiling_exhausted"])
            self.assertEqual(observed["unauthorized_hosts_detected"], ["<invalid>"])
            self.assertEqual(observed["by_host"]["<invalid>"], 1)

    def test_consumption_marker_binds_exact_tag_target_and_attempt(self) -> None:
        provenance = _strict_provenance(
            repository="RoomyRems/momentumbot",
            authorization_commit_sha="a" * 40,
            authorization_tree_sha="b" * 40,
            dispatcher_workflow_sha="c" * 40,
            dispatcher_workflow_ref=auth.EXPECTED_DISPATCHER_WORKFLOW_REF,
            workflow_run_id="33470000000",
            workflow_run_attempt=1,
        )
        ref = f"{auth.CONSUMPTION_TAG_PREFIX}{auth.AUTHORIZATION_CONTENT_SHA256}"
        marker = build_consumption_marker_v05(
            authorization_id=auth.AUTHORIZATION_ID,
            authorization_content_sha256=auth.AUTHORIZATION_CONTENT_SHA256,
            provenance=provenance,
            consumption_ref_name=ref,
            consumption_ref_target_sha="a" * 40,
        )
        self.assertEqual(marker["consumption_ref"]["name"], ref)
        self.assertEqual(
            marker["content_sha256"],
            canonical_fingerprint(
                {key: value for key, value in marker.items() if key != "content_sha256"}
            ),
        )
        with self.assertRaisesRegex(ValueError, "ref target"):
            build_consumption_marker_v05(
                authorization_id=auth.AUTHORIZATION_ID,
                authorization_content_sha256=auth.AUTHORIZATION_CONTENT_SHA256,
                provenance=provenance,
                consumption_ref_name=ref,
                consumption_ref_target_sha="d" * 40,
            )


if __name__ == "__main__":
    unittest.main()
