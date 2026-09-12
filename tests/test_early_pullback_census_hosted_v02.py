from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml
from momentumbot.research import early_pullback_census_hosted_v02 as m
from tests.test_early_pullback_census_v01 import Clock, synthetic_reply

ROOT = Path(__file__).resolve().parents[1]
CODE, TREE, EXECUTION = "a" * 40, "b" * 40, "c" * 40
NOW = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)


def approval():
    return {"approved_at": "2026-09-12T00:00:00Z", "expires_at": "2026-09-13T00:00:00Z",
        "approval_record_sha256": m.sha(m.adapter.render(m.authorization_source())),
        "pricing_record_sha256": m.sha(m.adapter.render(m.pricing_observation())),
        "approved_by": "repository_owner", "statement": m.APPROVAL_TEXT,
        "entitlement_basis": "public_documented_basic_plan_inclusion", "entitlement_is_provider_verified": False,
        "subscription_coverage_owner_attested": False, "credit_balance_provider_verified": False,
        "provider": "Massive", "credential_name": "MASSIVE_API_KEY",
        "routes": [m.adapter.parent.CENSUS_ROUTE, m.adapter.type_request()["url"]],
        "selected_dates": list(m.adapter.DATES), "maximum_requests": 601,
        "maximum_authorized_incremental_cost_usd": "10.00", "estimated_incremental_api_cost_usd": "0.00",
        "provider_billing_cap_enforced": False, "metered_purchase_authorized": False,
        "subscription_changes_authorized": False}


def fixtures(contract):
    execution = m.execution_payload(contract, code_commit=CODE, code_tree=TREE,
                                   ci_run_id="987654", approval=approval(), now=NOW)
    env = {"GITHUB_SHA": EXECUTION, "GITHUB_RUN_ID": "123456", "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_REPOSITORY": "RoomyRems/momentumbot", "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": "refs/heads/phase-3-historical-snapshot", "GITHUB_WORKFLOW_SHA": EXECUTION,
        "GITHUB_WORKFLOW_REF": "RoomyRems/momentumbot/" + m.WORKFLOW_PATH + "@refs/heads/phase-3-historical-snapshot"}
    facts = {"head": EXECUTION, "parent_commit": CODE, "parent_tree": TREE,
             "parents": [CODE], "changed_files": ["A\t" + m.EXECUTION_PATH], "clean": True}
    ci = {"id": 987654, "head_sha": CODE, "path": ".github/workflows/ci.yml", "event": "push",
          "status": "completed", "conclusion": "success", "repository": {"full_name": "RoomyRems/momentumbot"}}
    jobs = {"total_count": 1, "jobs": [{"run_id": 987654, "head_sha": CODE, "name": "test",
        "status": "completed", "conclusion": "success", "steps": [
            {"name": name, "status": "completed", "conclusion": "success"} for name in ("Install package", "Run tests", "Compile")]}]}
    ref = {"ref": m.CONSUMPTION_REF, "object": {"type": "commit", "sha": EXECUTION}}
    return execution, env, facts, ci, jobs, ref


class HostedCensusV02Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = m.validate_registration(ROOT)
        cls.adapter_contract = m.adapter.validate_registration(ROOT)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.execution, self.env, self.facts, self.ci, self.jobs, self.ref = fixtures(self.contract)

    def prepare(self):
        directory = self.root / "preflight"
        directory.mkdir()
        for name, value in (("parent-ci.json", self.ci), ("parent-ci-jobs.json", self.jobs), ("consumption-ref.json", self.ref)):
            m.base.write_once(directory / name, value)
        self.env["CENSUS_PREFLIGHT_SHA256"] = m.prepare(directory, self.contract, self.adapter_contract,
            self.execution, self.env, m.RUNTIME)
        self.env["CENSUS_PREFLIGHT_ARTIFACT_ID"] = "888"
        self.artifact = {"id": 888, "name": "early-pullback-census-hosted-v02-consumption-123456-1",
            "expired": False, "digest": "sha256:" + "f" * 64, "size_in_bytes": 123456,
            "workflow_run": {"id": 123456, "head_sha": EXECUTION, "head_branch": "phase-3-historical-snapshot"}}
        return m.read_preflight(directory, complete=True)

    def verify(self, files, **changes):
        args = dict(files=files, contract=self.contract, adapter_contract=self.adapter_contract,
                    execution=self.execution, env=self.env, runtime=m.RUNTIME, live_ref=self.ref, artifact=self.artifact)
        args.update(changes)
        return m.verify_preflight(**args)

    def run_capture(self, files, *, loader=None, transport=None, env=None, runtime=None):
        path = self.root / m.EXECUTION_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            m.base.write_once(path, self.execution)
        clock = Clock()
        def factory(*args, **kwargs):
            return m.adapter.CaptureSession(*args, **kwargs, clock_ns=clock.read,
                sleeper=clock.sleep, utc_now=lambda: NOW.isoformat())
        with patch.object(m, "validate_registration", return_value=self.contract), \
             patch.object(m.adapter, "validate_registration", return_value=self.adapter_contract):
            return m.capture(root=self.root, output=self.root / "result", preflight=files,
                env=env or self.env, facts=self.facts, now=NOW, runtime=runtime or m.RUNTIME,
                live_ref=self.ref, artifact=self.artifact,
                credential_loader=loader or (lambda: "SYNTHETIC_SECRET"),
                transport_factory=lambda: transport or synthetic_reply, session_factory=factory)

    def test_frozen_registration_and_ancestors_unchanged(self):
        self.assertEqual(self.contract["parent_registration_sha256"], m.HOSTED_PARENT_SHA)
        self.assertEqual(self.contract["selected_dates"], list(m.adapter.DATES))
        self.assertNotIn(m.EXECUTION_PATH, self.contract["file_bindings"])
        for key, value in m.adapter.BOUNDARY.items():
            self.assertEqual(self.contract[key], value)

    def test_exact_first_attempt_execution_is_valid(self):
        self.assertEqual(m.validate_execution(self.execution, self.contract, self.env, self.facts, NOW), self.execution)

    def test_changed_parent_tree_extra_file_merge_and_dirty_checkout_rejected(self):
        for key, value in (("parent_commit", "0" * 40), ("parent_tree", "0" * 40),
                           ("changed_files", ["A\t" + m.EXECUTION_PATH, "M\tsrc/changed.py"]),
                           ("parents", [CODE, TREE]), ("clean", False), ("head", CODE)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.validate_execution(self.execution, self.contract, self.env, dict(self.facts, **{key: value}), NOW)

    def test_rerun_dispatch_wrong_branch_repo_or_workflow_rejected(self):
        for key, value in (("GITHUB_RUN_ATTEMPT", "2"), ("GITHUB_EVENT_NAME", "workflow_dispatch"),
                           ("GITHUB_REF", "refs/heads/main"), ("GITHUB_REPOSITORY", "other/repo"),
                           ("GITHUB_WORKFLOW_SHA", CODE), ("GITHUB_WORKFLOW_REF", "wrong"), ("GITHUB_RUN_ID", "0")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.validate_execution(self.execution, self.contract, dict(self.env, **{key: value}), self.facts, NOW)

    def test_missing_or_placeholder_approval_and_entitlement_rejected(self):
        for value in (None, {}, dict(approval(), approval_record_sha256="0" * 64),
                      dict(approval(), pricing_record_sha256="0" * 64)):
            with self.assertRaises(ValueError):
                m.validate_approval(value, NOW)

    def test_expired_future_overlong_naive_approval_rejected(self):
        for changes in ({"expires_at": NOW.isoformat()}, {"approved_at": "2026-09-12T13:00:00Z"},
                        {"expires_at": "2026-09-30T00:00:00Z"}, {"approved_at": "2026-09-12T00:00:00"}):
            with self.assertRaises(ValueError):
                m.validate_approval(dict(approval(), **changes), NOW)

    def test_cost_upgrade_date_route_and_entitlement_proof_changes_rejected(self):
        for key, value in (("maximum_authorized_incremental_cost_usd", "11.00"), ("subscription_changes_authorized", True),
                           ("selected_dates", [m.adapter.DATES[0]]), ("routes", []),
                           ("entitlement_is_provider_verified", True), ("maximum_requests", 602),
                           ("credential_name", "POLYGON_API_KEY")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.validate_approval(dict(approval(), **{key: value}), NOW)

    def test_truthful_approval_rejects_invented_entitlement_balance_and_billing_guarantee(self):
        for key in ("subscription_coverage_owner_attested", "entitlement_is_provider_verified",
                    "credit_balance_provider_verified", "provider_billing_cap_enforced", "metered_purchase_authorized"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.validate_approval(dict(approval(), **{key: True}), NOW)
        with self.assertRaises(ValueError):
            m.validate_approval(dict(approval(), entitlement_basis="owner_attested_existing_subscription"), NOW)

    def test_source_hashes_and_expected_zero_cost_are_exact(self):
        for changes in ({"approval_record_sha256": "d" * 64}, {"pricing_record_sha256": "e" * 64},
                        {"estimated_incremental_api_cost_usd": "1.00"}):
            with self.assertRaises(ValueError):
                m.validate_approval(dict(approval(), **changes), NOW)

    def test_stale_public_pricing_is_rejected_even_with_fresh_approval(self):
        value = dict(approval(), approved_at="2026-09-20T00:00:00Z", expires_at="2026-09-21T00:00:00Z")
        with self.assertRaises(ValueError):
            m.validate_approval(value, datetime(2026, 9, 20, 12, tzinfo=timezone.utc))

    def test_owner_message_records_uncertainty_without_credit_provider_inference(self):
        source = m.authorization_source()
        self.assertIn("not sure", source["message"])
        self.assertFalse(source["subscription_coverage_owner_attested"])
        self.assertFalse(source["credit_balance_provider_verified"])
        self.assertFalse(source["credit_provider_identified"])
        self.assertIsNone(m.pricing_observation()["actual_billed_cost_usd"])
        self.assertEqual(m.previous.validate_registration(ROOT)["content_sha256"], m.HOSTED_PARENT_SHA)

    def test_resealed_execution_scope_change_rejected(self):
        changed = dict(self.execution)
        changed.pop("content_sha256")
        changed["limits"] = dict(changed["limits"], maximum_http_attempts=602)
        with self.assertRaises(ValueError):
            m.validate_execution(m.seal(changed), self.contract, self.env, self.facts, NOW)

    def test_exact_parent_ci_and_all_steps_required(self):
        m.validate_ci(self.ci, self.jobs, self.execution)
        for key, value in (("head_sha", TREE), ("status", "in_progress"), ("conclusion", "failure")):
            with self.assertRaises(ValueError):
                m.validate_ci(dict(self.ci, **{key: value}), self.jobs, self.execution)

    def test_green_workflow_cannot_hide_failed_skipped_or_missing_ci_steps(self):
        for mutation in ("failed", "skipped", "missing", "extra_job", "wrong_job_sha"):
            jobs = deepcopy(self.jobs)
            if mutation in ("failed", "skipped"):
                jobs["jobs"][0]["steps"][-1]["conclusion"] = mutation
            elif mutation == "missing":
                jobs["jobs"][0]["steps"].pop()
            elif mutation == "extra_job":
                jobs["total_count"] = 2
            else:
                jobs["jobs"][0]["head_sha"] = TREE
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                m.validate_ci(self.ci, jobs, self.execution)

    def test_preflight_roundtrip_exact_artifact_and_runtime(self):
        files = self.prepare()
        self.assertEqual(len(files), 9)
        self.assertEqual(self.verify(files), m.consumption(self.execution, self.env))

    def test_preparation_cannot_reuse_directory(self):
        self.prepare()
        with self.assertRaises(ValueError):
            m.prepare(self.root / "preflight", self.contract, self.adapter_contract, self.execution, self.env, m.RUNTIME)

    def test_preparation_rejects_bad_ci_before_creating_marker(self):
        self.jobs["jobs"][0]["steps"].pop()
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse((self.root / "preflight" / "consumption.json").exists())

    def test_preflight_byte_tampering_missing_extra_and_wrong_pin_rejected(self):
        original = self.prepare()
        for mutation in ("bytes", "missing", "extra", "pin"):
            files, env = dict(original), dict(self.env)
            if mutation == "bytes": files["runtime.json"] += b" "
            elif mutation == "missing": files.pop("runtime.json")
            elif mutation == "extra": files["extra.json"] = b"{}"
            else: env["CENSUS_PREFLIGHT_SHA256"] = "0" * 64
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.verify(files, env=env)

    def test_rehashed_preflight_cannot_change_runtime_or_approval(self):
        files = self.prepare()
        value = json.loads(files["runtime.json"])
        value["pandas"] = "3.0.5"
        files["runtime.json"] = m.adapter.render(value)
        inventory = m.seal({"contract_id": m.ID, "files": {name: {"bytes": len(raw), "sha256": m.sha(raw)} for name, raw in sorted(files.items()) if name != "preflight-inventory.json"}})
        files["preflight-inventory.json"] = m.adapter.render(inventory)
        self.env["CENSUS_PREFLIGHT_SHA256"] = m.sha(files["preflight-inventory.json"])
        with self.assertRaises(ValueError): self.verify(files)

    def test_live_ref_drift_or_tag_object_rejected(self):
        files = self.prepare()
        for ref in ({"ref": m.CONSUMPTION_REF, "object": {"type": "commit", "sha": CODE}},
                    {"ref": m.CONSUMPTION_REF, "object": {"type": "tag", "sha": EXECUTION}}):
            with self.assertRaises(ValueError): self.verify(files, live_ref=ref)

    def test_artifact_id_run_branch_expiry_size_digest_and_name_required(self):
        files = self.prepare()
        for key, value in (("id", 889), ("expired", True), ("digest", None), ("size_in_bytes", 0),
                           ("name", "other"), ("workflow_run", {"id": 123457, "head_sha": EXECUTION})):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.verify(files, artifact=dict(self.artifact, **{key: value}))

    def test_actual_runtime_must_match_frozen_runtime(self):
        files = self.prepare()
        for key, value in (("python", "3.13.0"), ("pandas", "3.0.5"), ("machine", "aarch64")):
            with self.assertRaises(ValueError): self.verify(files, runtime=dict(m.RUNTIME, **{key: value}))

    def test_symlink_and_oversize_preflight_rejected_before_read(self):
        self.prepare()
        directory = self.root / "preflight"
        (self.root / "link").symlink_to(directory, target_is_directory=True)
        with self.assertRaises(ValueError): m.read_preflight(self.root / "link", complete=True)
        with patch.object(m, "PREFLIGHT_LIMIT", 1), self.assertRaises(ValueError):
            m.read_preflight(directory, complete=True)

    def test_full_synthetic_launch_keeps_all_origin_runtime_gates_closed(self):
        files = self.prepare()
        calls = []
        def loader():
            self.assertTrue((self.root / "result" / "launch" / "consumption.json").is_file())
            calls.append("credential")
            return "SYNTHETIC_SECRET"
        result = self.run_capture(files, loader=loader)
        self.assertTrue(result["protocol_complete"])
        self.assertEqual(result["attempt_count"], 31)
        self.assertEqual(calls, ["credential"])
        link = m.base.frozen(self.root / "result" / "launch" / "capture-link.json")
        self.assertIsNone(link["failure"])
        self.assertFalse(link["provider_origin_independently_verified"])
        self.assertFalse(link["historical_replay_enabled"])
        raw = (self.root / "result" / "capture" / "inventory.json").read_bytes()
        self.assertEqual(link["capture_files"]["inventory.json"]["sha256"], m.sha(raw))
        self.assertFalse(any(b"SYNTHETIC_SECRET" in p.read_bytes() for p in (self.root / "result").rglob("*.json")))

    def test_bad_preflight_never_reads_credential_or_starts_transport(self):
        files = self.prepare()
        self.env["CENSUS_PREFLIGHT_SHA256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.run_capture(files, loader=lambda: self.fail("credential read before validation"))
        self.assertFalse((self.root / "result").exists())

    def test_rerun_never_reads_credential(self):
        files = self.prepare()
        with self.assertRaises(ValueError):
            self.run_capture(files, env=dict(self.env, GITHUB_RUN_ATTEMPT="2"), loader=lambda: self.fail("credential read"))

    def test_bad_runtime_never_reads_credential(self):
        files = self.prepare()
        with self.assertRaises(ValueError):
            self.run_capture(files, runtime=dict(m.RUNTIME, pandas="3.0.5"), loader=lambda: self.fail("credential read"))

    def test_missing_credential_retains_launch_failure_without_request(self):
        files = self.prepare()
        with self.assertRaises(ValueError): self.run_capture(files, loader=lambda: "")
        link = m.base.frozen(self.root / "result" / "launch" / "capture-link.json")
        self.assertEqual(link["failure"], "launch_failed")
        self.assertEqual(link["capture_files"], {"report.json": None, "inventory.json": None})

    def test_provider_failure_is_retained_without_retry(self):
        files = self.prepare()
        calls = []
        def transport(request, credential):
            calls.append(request)
            return dict(synthetic_reply(request, credential), status=429)
        result = self.run_capture(files, transport=transport)
        self.assertFalse(result["protocol_complete"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(m.base.frozen(self.root / "result" / "launch" / "capture-link.json")["failure"], "capture_failed")

    def test_output_reuse_blocked_before_second_credential_read(self):
        files = self.prepare()
        self.run_capture(files)
        with self.assertRaises(FileExistsError):
            self.run_capture(files, loader=lambda: self.fail("credential reread"))

    def test_cli_has_provider_free_registration_validation(self):
        result = subprocess.run([sys.executable, "scripts/run_early_pullback_census_hosted_v02.py", "--validate-only"],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["actual_provider_requests"], 0)

    def test_workflow_only_separate_execution_path_can_trigger(self):
        workflow = yaml.safe_load((ROOT / m.WORKFLOW_PATH).read_text())
        triggers = workflow.get("on", workflow.get(True))
        self.assertEqual(triggers, {"push": {"branches": ["phase-3-historical-snapshot"], "paths": [m.EXECUTION_PATH]}})
        self.assertFalse(workflow["concurrency"]["cancel-in-progress"])
        for job in workflow["jobs"].values(): self.assertEqual(job["if"], "github.run_attempt == 1")

    def test_workflow_consumes_atomically_before_upload_and_secrets(self):
        workflow = yaml.safe_load((ROOT / m.WORKFLOW_PATH).read_text())
        consume = workflow["jobs"]["consume"]
        capture = workflow["jobs"]["capture"]
        self.assertEqual(capture["needs"], "consume")
        self.assertNotIn("secrets.", json.dumps(consume))
        prepared = next(i for i, s in enumerate(consume["steps"]) if s.get("id") == "prepare")
        preserved = next(i for i, s in enumerate(consume["steps"]) if s.get("id") == "preserve")
        self.assertLess(prepared, preserved)
        command = consume["steps"][prepared]["run"]
        self.assertIn("--method POST", command)
        self.assertNotIn("--method PATCH", command)
        self.assertIn("ref=" + m.CONSUMPTION_REF, command)
        secrets = [s for s in capture["steps"] if "secrets." in json.dumps(s)]
        self.assertEqual(len(secrets), 1)
        self.assertEqual(set(secrets[0]["env"]), {"MASSIVE_API_KEY"})
        uploads = [s for s in capture["steps"] if "actions/upload-artifact@" in s.get("uses", "")]
        self.assertEqual(len(uploads), 2)
        self.assertTrue(all(s["if"] == "always()" for s in uploads))

    def test_workflow_actions_pinned_and_no_credential_checkout_persistence(self):
        workflow = yaml.safe_load((ROOT / m.WORKFLOW_PATH).read_text())
        for job in workflow["jobs"].values():
            for step in job["steps"]:
                if "uses" in step: self.assertRegex(step["uses"], r"@[0-9a-f]{40}$")
                if step.get("uses", "").startswith("actions/checkout@"):
                    self.assertFalse(step["with"]["persist-credentials"])
        script = (ROOT / "scripts/run_early_pullback_census_hosted_v02.py").read_text()
        self.assertNotIn("dict(os.environ)", script)
        self.assertEqual(script.count('os.environ.get("MASSIVE_API_KEY"'), 1)


if __name__ == "__main__":
    unittest.main()
