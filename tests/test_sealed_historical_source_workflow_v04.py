from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from scripts.run_sealed_historical_source_acquisition_v04 import (
    _safe_budget,
    _strict_provenance,
    build_consumption_marker,
    build_safe_failure,
)
from momentumbot.research.sealed_historical_source_checkpoint_v01 import (
    canonical_fingerprint,
)
from momentumbot.research.sealed_historical_source_authorization_v04 import (
    AUTHORIZATION_CONTENT_SHA256,
)


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/sealed-historical-source-acquisition-v04.yml"
RUNNER = ROOT / "scripts/run_sealed_historical_source_acquisition_v04.py"
V03_WORKFLOW = ROOT / ".github/workflows/sealed-historical-source-acquisition-v03.yml"
V03_RUNNER = ROOT / "scripts/run_sealed_historical_source_acquisition_v03.py"
V03_REGISTRATION = (
    ROOT
    / "research/data-audits/"
    "sealed-historical-source-acquisition-v0.3-registration-2026-08-31.json"
)

EXPECTED_DATES = (
    "2025-05-30",
    "2025-06-02",
    "2025-06-03",
    "2025-06-04",
    "2025-06-05",
    "2025-06-06",
    "2025-06-09",
    "2025-06-10",
    "2025-06-11",
    "2025-06-12",
    "2025-06-13",
    "2025-06-16",
    "2025-06-17",
    "2025-06-18",
    "2025-06-20",
    "2025-06-23",
    "2025-06-24",
    "2025-06-25",
    "2025-06-26",
    "2025-06-27",
    "2025-07-01",
    "2025-07-02",
    "2025-07-07",
    "2025-07-08",
    "2025-07-10",
    "2025-07-11",
    "2025-07-14",
    "2025-07-15",
    "2025-07-16",
    "2025-07-17",
)

PROVIDER_SECRET_STEPS = {
    "Acquire point-in-time Massive membership",
    "Freeze SIP daily coverage",
    "Freeze panel identity and corporate-action normalization",
    "Acquire split-consistent profile-union market inputs",
    "Acquire target-date-basis causal float inputs",
    "Acquire publication-timed causal news inputs",
    "Acquire canonical split-rank scanner source inputs",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SealedHistoricalSourceWorkflowV04Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        payload = yaml.load(cls.text, Loader=yaml.BaseLoader)
        if not isinstance(payload, dict):
            raise AssertionError("workflow must parse as a YAML mapping")
        cls.workflow = payload
        jobs = payload.get("jobs")
        if not isinstance(jobs, dict):
            raise AssertionError("workflow jobs must be a mapping")
        cls.jobs = jobs

    def _steps(self, job_name: str) -> list[dict[str, object]]:
        job = self.jobs[job_name]
        self.assertIsInstance(job, dict)
        steps = job.get("steps")
        self.assertIsInstance(steps, list)
        self.assertTrue(all(isinstance(step, dict) for step in steps))
        return steps  # type: ignore[return-value]

    def _step(self, job_name: str, name: str) -> dict[str, object]:
        matches = [step for step in self._steps(job_name) if step.get("name") == name]
        self.assertEqual(len(matches), 1, f"expected one workflow step named {name}")
        return matches[0]

    def _run(self, job_name: str, name: str) -> str:
        run = self._step(job_name, name).get("run")
        self.assertIsInstance(run, str)
        return run

    def test_yaml_trigger_is_push_validation_plus_manual_one_shot_only(self) -> None:
        triggers = self.workflow.get("on")
        self.assertIsInstance(triggers, dict)
        self.assertEqual(set(triggers), {"push", "workflow_dispatch"})
        self.assertNotIn("schedule", triggers)
        dispatch = triggers["workflow_dispatch"]
        self.assertIsInstance(dispatch, dict)
        inputs = dispatch.get("inputs")
        self.assertIsInstance(inputs, dict)
        self.assertEqual(
            set(inputs),
            {"authorization_commit_sha", "authorization_tree_sha", "authorization_path"},
        )
        self.assertEqual(
            inputs["authorization_path"]["default"],
            "research/strategy/sealed-historical-source-acquisition-v0.4.json",
        )
        for job_name in ("consume", "acquire", "freeze"):
            self.assertEqual(
                self.jobs[job_name].get("if"),
                "github.event_name == 'workflow_dispatch' && github.run_attempt == 1",
            )
        self.assertEqual(self.jobs["consume"].get("needs"), "validate")
        self.assertEqual(self.jobs["acquire"].get("needs"), "consume")
        self.assertEqual(self.jobs["freeze"].get("needs"), ["consume", "acquire"])
        self.assertEqual(self.jobs["consume"]["permissions"]["contents"], "write")
        for job_name in ("acquire", "freeze"):
            self.assertEqual(self.jobs[job_name]["permissions"]["contents"], "read")
        concurrency = self.workflow.get("concurrency")
        self.assertIsInstance(concurrency, dict)
        self.assertEqual(concurrency.get("cancel-in-progress"), "false")

    def test_exact_30_dates_and_frozen_budgets_are_semantic_values(self) -> None:
        environment = self.workflow.get("env")
        self.assertIsInstance(environment, dict)
        dates = str(environment.get("PANEL_DATES") or "").split()
        self.assertEqual(tuple(dates), EXPECTED_DATES)
        self.assertEqual(len(dates), len(set(dates)))
        self.assertEqual(
            environment.get("MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_LIMIT"),
            "40000",
        )
        self.assertEqual(
            environment.get("MOMENTUMBOT_PROVIDER_BLOCKED_ATTEMPT_FILE"),
            "/tmp/momentumbot-sealed-historical-source-v04-blocked-attempts.json",
        )
        runner_text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("MAX_HTTP_ATTEMPTS = 40_000", runner_text)
        self.assertIn("MAX_RETAINED_BYTES = 1_500_000_000", runner_text)
        for job_name, name in (
            ("acquire", "Acquire target-date-basis causal float inputs"),
            ("acquire", "Acquire publication-timed causal news inputs"),
            ("acquire", "Acquire canonical split-rank scanner source inputs"),
            ("freeze", "Freeze scanner snapshots from canonical inputs without credentials"),
        ):
            self.assertIn("--max-candidates-per-date 100", self._run(job_name, name))

    def test_checkout_gate_binds_repository_branch_path_commit_tree_and_dispatcher(self) -> None:
        run = self._run(
            "acquire", "Verify exact immutable authorization checkout and dispatcher"
        )
        for required in (
            'test "$GITHUB_REPOSITORY" = "RoomyRems/momentumbot"',
            'test "$GITHUB_REF" = "refs/heads/main"',
            "research/strategy/sealed-historical-source-acquisition-v0.4.json",
            "git rev-parse HEAD)",
            "git rev-parse HEAD^{tree})",
            "git rev-parse origin/phase-3-historical-snapshot)",
            'test "$GITHUB_SHA" = "$DISPATCHER_WORKFLOW_SHA"',
            "dispatcher_blob=",
            "authorized_blob=",
            'test "$dispatcher_blob" = "$authorized_blob"',
        ):
            self.assertIn(required, run)
        step = self._step(
            "acquire", "Verify exact immutable authorization checkout and dispatcher"
        )
        environment = step.get("env")
        self.assertIsInstance(environment, dict)
        self.assertEqual(environment.get("DISPATCHER_WORKFLOW_SHA"), "${{ github.workflow_sha }}")
        self.assertEqual(environment.get("DISPATCHER_WORKFLOW_REF"), "${{ github.workflow_ref }}")

    def test_pinned_install_and_environment_freeze_precede_provider_access(self) -> None:
        for job_name, step_name in (
            ("validate", "Install pinned provider-free environment"),
            (
                "acquire",
                "Install exact acquisition environment without provider credentials",
            ),
        ):
            run = self._run(job_name, step_name)
            self.assertIn('test ! -e "$GITHUB_WORKSPACE/.venv-v04"', run)
            self.assertIn('python -m venv "$GITHUB_WORKSPACE/.venv-v04"', run)
            self.assertIn("--require-hashes --only-binary=:all: --no-deps -r requirements-sealed-source-v04.txt", run)
            self.assertIn("--no-deps --no-build-isolation -e .", run)
            self.assertIn(
                'echo "$GITHUB_WORKSPACE/.venv-v04/bin" >> "$GITHUB_PATH"',
                run,
            )
            self.assertLess(run.index("--require-hashes"), run.index("GITHUB_PATH"))
            self.assertLess(run.index("GITHUB_PATH"), run.index("-e ."))
            self.assertNotIn("python -m pip install", run)
        acquire_install = self._run(
            "acquire", "Install exact acquisition environment without provider credentials"
        )
        self.assertIn(
            '"$GITHUB_WORKSPACE/.venv-v04/bin/python" -m pip freeze --all',
            acquire_install,
        )
        self.assertIn("environment/pip-freeze.txt", acquire_install)
        self.assertIn("environment/requirements-sealed-source-v04.txt", acquire_install)
        preflight = self._run(
            "validate", "Run provider-free v0.4 preflight and adversarial gates"
        )
        self.assertIn(
            "tests.test_sealed_historical_source_authorization_v04",
            preflight,
        )
        push_paths = self.workflow["on"]["push"]["paths"]
        self.assertIn(
            "tests/test_sealed_historical_source_authorization_v04.py",
            push_paths,
        )

    def test_provider_secrets_are_step_scoped_and_only_wrapped_steps_receive_them(self) -> None:
        top_environment = self.workflow.get("env")
        self.assertIsInstance(top_environment, dict)
        self.assertNotIn("secrets.", repr(top_environment))
        acquire = self.jobs["acquire"]
        self.assertNotIn("env", acquire)
        seen_secret_steps: set[str] = set()
        for step in self._steps("acquire"):
            name = str(step.get("name") or "")
            environment = step.get("env")
            rendered = repr(environment)
            has_provider_secret = any(
                token in rendered
                for token in (
                    "ALPACA_MAIN_API_KEY",
                    "ALPACA_MAIN_API_SECRET",
                    "MASSIVE_API_KEY",
                    "SEC_USER_AGENT",
                )
            )
            if has_provider_secret:
                seen_secret_steps.add(name)
                run = step.get("run")
                self.assertIsInstance(run, str)
                self.assertIn("scripts/run_provider_entrypoint_v04.py", run)
        self.assertEqual(seen_secret_steps, PROVIDER_SECRET_STEPS)
        for job_name, name in (
            ("acquire", "Install exact acquisition environment without provider credentials"),
            ("acquire", "Revalidate authority marker and durable ref before provider access"),
            ("acquire", "Build hash-inventoried provider checkpoint without credentials"),
            ("acquire", "Build sanitized failure accounting without credentials"),
            ("consume", "Create provenance-bound write-once consumption marker"),
            ("freeze", "Freeze scanner snapshots from canonical inputs without credentials"),
            ("freeze", "Build strict deep-replay acquisition report without credentials"),
        ):
            self.assertNotIn("secrets.", repr(self._step(job_name, name).get("env")))
        self.assertNotIn("secrets.", repr(self.jobs["consume"]))
        self.assertNotIn("secrets.", repr(self.jobs["freeze"]))
        self.assertNotIn("DATABENTO_API_KEY", self.text)

    def test_durable_marker_is_consumed_before_every_provider_step(self) -> None:
        consume_names = [str(step.get("name") or "") for step in self._steps("consume")]
        acquire_names = [str(step.get("name") or "") for step in self._steps("acquire")]
        marker_build_index = consume_names.index(
            "Create provenance-bound write-once consumption marker"
        )
        marker_index = consume_names.index("Atomically consume authorization in durable Git ref")
        upload_index = consume_names.index("Preserve consumed authorization marker")
        self.assertLess(marker_build_index, marker_index)
        self.assertLess(marker_index, upload_index)
        self.assertLess(
            acquire_names.index("Revalidate authority marker and durable ref before provider access"),
            acquire_names.index("Acquire point-in-time Massive membership"),
        )
        marker_run = self._run(
            "consume", "Create provenance-bound write-once consumption marker"
        )
        for context in (
            "inputs.authorization_commit_sha",
            "inputs.authorization_tree_sha",
            "github.workflow_sha",
            "github.workflow_ref",
        ):
            self.assertIn(context, marker_run)
        create_ref = self._run("consume", "Atomically consume authorization in durable Git ref")
        self.assertIn("gh api --method POST", create_ref)
        self.assertIn("git/refs", create_ref)
        self.assertNotIn("--method DELETE", create_ref)

    def test_failure_accounting_preserves_blocked_hosts_and_budget_overrun(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "budget.json"
            for payload, expected_hosts, ceiling_exceeded in (
                (
                    {
                        "schema_version": 1,
                        "total_attempts": 1,
                        "by_host": {"example.com": 1},
                    },
                    ["example.com"],
                    False,
                ),
                (
                    {
                        "schema_version": 1,
                        "total_attempts": 40_001,
                        "by_host": {"data.alpaca.markets": 40_001},
                    },
                    [],
                    True,
                ),
            ):
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.subTest(payload=payload):
                    observed = _safe_budget(path)
                    self.assertEqual(
                        observed["unauthorized_hosts_detected"], expected_hosts
                    )
                    self.assertIs(
                        observed["request_ceiling_exceeded"], ceiling_exceeded
                    )

    def test_exact_provider_phase_order_checkpoint_then_provider_free_freeze(self) -> None:
        acquire_names = [str(step.get("name") or "") for step in self._steps("acquire")]
        provider_order = (
            "Acquire point-in-time Massive membership",
            "Freeze instrument semantics",
            "Freeze SIP daily coverage",
            "Freeze panel identity and corporate-action normalization",
            "Acquire split-consistent profile-union market inputs",
            "Acquire target-date-basis causal float inputs",
            "Acquire publication-timed causal news inputs",
            "Upload reusable upstream progress before long canonical acquisition",
            "Acquire canonical split-rank scanner source inputs",
            "Build hash-inventoried provider checkpoint without credentials",
            "Upload label-blind provider checkpoint before scanner freeze",
        )
        indices = [acquire_names.index(name) for name in provider_order]
        self.assertEqual(indices, sorted(indices))
        freeze_names = [str(step.get("name") or "") for step in self._steps("freeze")]
        freeze_order = (
            "Download exact provider checkpoint",
            "Rehash and validate downloaded provider checkpoint before scanner loading",
            "Freeze scanner snapshots from canonical inputs without credentials",
            "Build strict deep-replay acquisition report without credentials",
            "Upload completed normalized canonical and audited source bundle",
        )
        freeze_indices = [freeze_names.index(name) for name in freeze_order]
        self.assertEqual(freeze_indices, sorted(freeze_indices))
        acquire_source = self._run(
            "acquire", "Acquire canonical split-rank scanner source inputs"
        )
        freeze = self._run(
            "freeze", "Freeze scanner snapshots from canonical inputs without credentials"
        )
        self.assertIn("--phase acquire-source-inputs", acquire_source)
        self.assertIn("scripts/run_provider_entrypoint_v04.py", acquire_source)
        self.assertIn("--phase freeze-snapshots", freeze)
        self.assertNotIn("scripts/run_provider_entrypoint_v04.py", freeze)

    def test_checkpoint_and_report_bind_environment_and_dispatcher_provenance(self) -> None:
        checkpoint = self._run(
            "acquire", "Build hash-inventoried provider checkpoint without credentials"
        )
        report = self._run(
            "freeze", "Build strict deep-replay acquisition report without credentials"
        )
        for run in (checkpoint, report):
            for required in (
                "--authorization-commit-sha",
                "--authorization-tree-sha",
                "--dispatcher-workflow-sha",
                "--dispatcher-workflow-ref",
                "environment/pip-freeze.txt",
                "environment/requirements-sealed-source-v04.txt",
            ):
                self.assertIn(required, run)
        self.assertIn("--source-checkpoint", report)
        self.assertIn("--blocked-attempt-ledger", checkpoint)

    def test_progress_boundary_and_canonical_timeout_leave_cleanup_reserve(self) -> None:
        names = [str(step.get("name") or "") for step in self._steps("acquire")]
        news = names.index("Acquire publication-timed causal news inputs")
        progress = names.index(
            "Upload reusable upstream progress before long canonical acquisition"
        )
        canonical = names.index("Acquire canonical split-rank scanner source inputs")
        self.assertLess(news, progress)
        self.assertLess(progress, canonical)
        canonical_step = self._step(
            "acquire", "Acquire canonical split-rank scanner source inputs"
        )
        self.assertEqual(canonical_step.get("timeout-minutes"), "150")
        progress_step = self._step(
            "acquire", "Upload reusable upstream progress before long canonical acquisition"
        )
        self.assertEqual(progress_step["with"]["retention-days"], "90")
        self.assertIn("upstream-progress-${{ github.run_id }}-${{ github.run_attempt }}", progress_step["with"]["name"])

    def test_failure_path_retains_accounting_and_missing_checkpoint_without_secrets(self) -> None:
        accounting = self._step(
            "acquire", "Build sanitized failure accounting without credentials"
        )
        check = self._step(
            "acquire", "Check whether the provider checkpoint is already retained"
        )
        fallback = self._step(
            "acquire",
            "Preserve current source and checkpoint when no checkpoint artifact exists",
        )
        sanitized = self._step("acquire", "Preserve sanitized failure accounting")
        self.assertEqual(accounting.get("if"), "failure() || cancelled()")
        self.assertEqual(check.get("if"), "failure() || cancelled()")
        self.assertEqual(
            fallback.get("if"),
            "(failure() || cancelled()) && env.UPLOAD_FAILURE_SOURCE == 'true'",
        )
        self.assertEqual(sanitized.get("if"), "failure() || cancelled()")
        check_run = check.get("run")
        self.assertIsInstance(check_run, str)
        self.assertLess(
            check_run.index("UPLOAD_FAILURE_SOURCE=true"),
            check_run.index("gh api"),
        )
        for step in (accounting, check, fallback, sanitized):
            self.assertNotIn("ALPACA_MAIN", repr(step))
            self.assertNotIn("MASSIVE_API_KEY", repr(step))
            self.assertNotIn("SEC_USER_AGENT", repr(step))

    def test_no_transcript_databento_account_or_order_path_is_present(self) -> None:
        lowered = self.text.lower()
        for forbidden in (
            "databento_api_key",
            "transcript-record",
            "ross-label",
            "submit_order",
            "account endpoint",
            "order endpoint",
        ):
            self.assertNotIn(forbidden, lowered)

    def test_v03_hash_bound_entry_points_remain_byte_identical(self) -> None:
        self.assertEqual(
            _sha256(V03_WORKFLOW),
            "f527c900877f30a56cf4b6a6b86bcb48af1840f449e50bfb7411a2f1e5e9d7ab",
        )
        self.assertEqual(
            _sha256(V03_RUNNER),
            "997652617eae5034b4a0e18d90ee4f7dd1563c6cba7d2d246323d4c695da4107",
        )
        registration = json.loads(V03_REGISTRATION.read_text(encoding="utf-8"))
        artifacts = registration.get("artifacts")
        self.assertIsInstance(artifacts, dict)
        self.assertGreaterEqual(len(artifacts), 10)
        for label, row in artifacts.items():
            with self.subTest(v03_artifact=label):
                self.assertIsInstance(row, dict)
                self.assertEqual(_sha256(ROOT / row["path"]), row["file_sha256"])

    def test_consumption_marker_binds_exact_context_before_provider_access(self) -> None:
        provenance = _strict_provenance(
            repository="RoomyRems/momentumbot",
            authorization_commit_sha="a" * 40,
            authorization_tree_sha="b" * 40,
            dispatcher_workflow_sha="c" * 40,
            dispatcher_workflow_ref=(
                "RoomyRems/momentumbot/.github/workflows/"
                "sealed-historical-source-acquisition-v04.yml@refs/heads/main"
            ),
            workflow_run_id="123",
            workflow_run_attempt=1,
        )
        marker = build_consumption_marker(
            authorization_id="sealed-historical-source-acquisition-v0.4",
            authorization_content_sha256=AUTHORIZATION_CONTENT_SHA256,
            provenance=provenance,
            consumption_ref_name=(
                "refs/tags/sealed-historical-source-acquisition-v04-consumed-"
                f"{AUTHORIZATION_CONTENT_SHA256}"
            ),
            consumption_ref_target_sha="a" * 40,
        )
        claimed = marker["content_sha256"]
        unsigned = {key: value for key, value in marker.items() if key != "content_sha256"}
        self.assertEqual(claimed, canonical_fingerprint(unsigned))
        self.assertIs(
            marker["one_shot_attestation"]["provider_call_made_before_marker"],
            False,
        )
        self.assertEqual(
            marker["workflow_provenance"]["authorization_tree_sha"], "b" * 40
        )
        self.assertEqual(
            marker["workflow_provenance"]["dispatcher_workflow_sha"], "c" * 40
        )
        self.assertNotIn("credential", json.dumps(marker).lower())
        with self.assertRaisesRegex(ValueError, "frozen v0.4 child"):
            build_consumption_marker(
                authorization_id="sealed-historical-source-acquisition-v0.4",
                authorization_content_sha256="0" * 64,
                provenance=provenance,
                consumption_ref_name=(
                    "refs/tags/sealed-historical-source-acquisition-v04-consumed-"
                    + ("0" * 64)
                ),
                consumption_ref_target_sha="a" * 40,
            )
        with self.assertRaisesRegex(ValueError, "not canonical"):
            build_consumption_marker(
                authorization_id="sealed-historical-source-acquisition-v0.4",
                authorization_content_sha256=AUTHORIZATION_CONTENT_SHA256,
                provenance={**provenance, "extra": True},
                consumption_ref_name=(
                    "refs/tags/sealed-historical-source-acquisition-v04-consumed-"
                    f"{AUTHORIZATION_CONTENT_SHA256}"
                ),
                consumption_ref_target_sha="a" * 40,
            )

    def test_runner_provenance_rejects_rerun_and_unbound_dispatcher(self) -> None:
        values = {
            "repository": "RoomyRems/momentumbot",
            "authorization_commit_sha": "a" * 40,
            "authorization_tree_sha": "b" * 40,
            "dispatcher_workflow_sha": "c" * 40,
            "dispatcher_workflow_ref": (
                "RoomyRems/momentumbot/.github/workflows/"
                "sealed-historical-source-acquisition-v04.yml@refs/heads/main"
            ),
            "workflow_run_id": "123",
            "workflow_run_attempt": 1,
        }
        with self.assertRaisesRegex(ValueError, "attempt 1"):
            _strict_provenance(**{**values, "workflow_run_attempt": 2})
        with self.assertRaisesRegex(ValueError, "workflow ref"):
            _strict_provenance(
                **{**values, "dispatcher_workflow_ref": "unbound.yml@refs/heads/main"}
            )
        with self.assertRaisesRegex(ValueError, "Git SHA"):
            _strict_provenance(
                **{**values, "authorization_commit_sha": 123}  # type: ignore[arg-type]
            )

    def test_safe_failure_records_only_sanitized_counts_hashes_and_dates(self) -> None:
        provenance = _strict_provenance(
            repository="RoomyRems/momentumbot",
            authorization_commit_sha="a" * 40,
            authorization_tree_sha="b" * 40,
            dispatcher_workflow_sha="c" * 40,
            dispatcher_workflow_ref=(
                "RoomyRems/momentumbot/.github/workflows/"
                "sealed-historical-source-acquisition-v04.yml@refs/heads/main"
            ),
            workflow_run_id="123",
            workflow_run_attempt=1,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            completed = source / "causal-market-discovery-v0.3" / EXPECTED_DATES[0]
            completed.mkdir(parents=True)
            (completed / "manifest.json").write_text("{}\n", encoding="utf-8")
            budget = root / "budget.json"
            budget.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "total_attempts": 3,
                        "by_host": {"data.alpaca.markets": 3},
                    }
                ),
                encoding="utf-8",
            )
            environment = root / "pip-freeze.txt"
            environment.write_text("package==1\n", encoding="utf-8")
            blocked = root / "blocked.json"
            blocked.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "total_blocked_attempts": 1,
                        "by_category": {
                            "hostname": 0,
                            "https_transport": 0,
                            "redirect": 0,
                            "request_budget": 1,
                            "socket": 0,
                            "subprocess": 0,
                        },
                        "by_host": {"data.alpaca.markets": 1},
                    }
                ),
                encoding="utf-8",
            )
            failure = build_safe_failure(
                authorization_id="sealed-historical-source-acquisition-v0.4",
                authorization_content_sha256=AUTHORIZATION_CONTENT_SHA256,
                provenance=provenance,
                source_root=source,
                request_budget_path=budget,
                checkpoint_path=None,
                environment_freeze_path=environment,
                requirements_path=None,
                blocked_attempt_ledger_path=blocked,
            )
        self.assertEqual(
            failure["completed_dates_by_stage"]["market_discovery"],
            [EXPECTED_DATES[0]],
        )
        self.assertEqual(failure["request_budget"]["total_attempts"], 3)
        self.assertIs(failure["request_budget"]["request_ceiling_exceeded"], True)
        self.assertEqual(failure["blocked_attempts"]["total_blocked_attempts"], 1)
        self.assertEqual(
            failure["retained_lineage_files"]["environment_freeze"]["sha256"],
            hashlib.sha256(b"package==1\n").hexdigest(),
        )
        unsigned = {
            key: value for key, value in failure.items() if key != "content_sha256"
        }
        self.assertEqual(failure["content_sha256"], canonical_fingerprint(unsigned))


if __name__ == "__main__":
    unittest.main()
