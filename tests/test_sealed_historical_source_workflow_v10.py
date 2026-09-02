from __future__ import annotations

from pathlib import Path
import unittest

import yaml
from yaml.constructor import ConstructorError

from momentumbot.research.sealed_historical_source_authorization_v10 import (
    REGISTRATION_ARTIFACT_PATHS,
)


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/sealed-historical-source-acquisition-v10.yml"


class UniqueKeyLoader(yaml.BaseLoader):
    """Keep GitHub workflow tests from silently accepting duplicate YAML keys."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


class SealedHistoricalSourceWorkflowV10Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        payload = yaml.load(cls.text, Loader=UniqueKeyLoader)
        if not isinstance(payload, dict):
            raise AssertionError("workflow must parse as a YAML mapping")
        cls.workflow = payload
        cls.jobs = payload["jobs"]

    def _steps(self, job: str) -> list[dict[str, object]]:
        value = self.jobs[job]["steps"]
        self.assertIsInstance(value, list)
        return value  # type: ignore[return-value]

    def _step(self, job: str, name: str) -> dict[str, object]:
        values = [row for row in self._steps(job) if row.get("name") == name]
        self.assertEqual(len(values), 1, name)
        return values[0]

    def _run(self, job: str, name: str) -> str:
        value = self._step(job, name).get("run")
        self.assertIsInstance(value, str)
        return value

    def test_push_is_provider_free_and_manual_dispatch_is_attempt_one_only(self) -> None:
        triggers = self.workflow["on"]
        self.assertEqual(set(triggers), {"push", "workflow_dispatch"})
        self.assertNotIn("schedule", triggers)
        for job in ("consume", "acquire", "freeze"):
            self.assertEqual(
                self.jobs[job]["if"],
                "github.event_name == 'workflow_dispatch' && github.run_attempt == 1",
            )
        self.assertEqual(self.jobs["consume"]["needs"], "validate")
        self.assertEqual(self.jobs["acquire"]["needs"], ["validate", "consume"])
        self.assertEqual(
            self.jobs["freeze"]["needs"], ["validate", "consume", "acquire"]
        )
        self.assertEqual(self.jobs["consume"]["permissions"]["contents"], "write")
        self.assertEqual(self.jobs["acquire"]["permissions"]["contents"], "read")
        self.assertEqual(self.jobs["freeze"]["permissions"]["contents"], "read")

    def test_inputs_are_trimmed_then_bound_to_exact_commit_tree_and_path(self) -> None:
        canonical = self._run("validate", "Canonicalize and strictly validate manual inputs")
        self.assertIn('.strip()', canonical)
        self.assertIn('re.fullmatch(r"[0-9a-f]{40}"', canonical)
        self.assertIn(
            "research/strategy/sealed-historical-source-acquisition-v0.10.json",
            canonical,
        )
        consume = self._run(
            "consume", "Verify exact immutable authorization checkout and dispatcher"
        )
        for value in (
            "git rev-parse HEAD)",
            "git rev-parse HEAD^{tree})",
            "git rev-parse origin/phase-3-historical-snapshot)",
            "GITHUB_SHA",
            "dispatcher_blob",
            "authorized_blob",
        ):
            self.assertIn(value, consume)

    def test_parent_artifact_is_exact_and_recovery_precedes_provider_access(self) -> None:
        self.assertEqual(
            self.text.count(
                'gh api "repos/${GITHUB_REPOSITORY}/actions/artifacts/9827444933"'
            ),
            2,
        )
        preflight = self._run(
            "validate",
            "Preflight replay retained parent and environment before consumption",
        )
        self.assertIn("--validate-only", preflight)
        self.assertIn("--child-environment-freeze", preflight)
        self.assertIn("--expected-child-commit-sha", preflight)
        preflight_download = self._step(
            "validate",
            "Preflight download exact retained parent artifact before consumption",
        )
        self.assertEqual(preflight_download["if"], "github.event_name == 'workflow_dispatch'")
        self.assertEqual(preflight_download["with"]["run-id"], "33577895166")
        preflight_metadata = self._run(
            "validate", "Preflight exact retained parent artifact metadata before consumption"
        )
        self.assertEqual(preflight_metadata.count("gh api"), 1)
        self.assertNotIn("--jq", preflight_metadata)
        self.assertNotIn('test "$(gh api', preflight_metadata)
        self.assertIn("validate_parent_artifact_metadata_v10.py", preflight_metadata)
        self.assertIn("--metadata-json", preflight_metadata)
        self.assertIn("--receipt-output", preflight_metadata)
        verify = self._run(
            "acquire", "Verify exact retained v0.9 failure artifact metadata"
        )
        self.assertEqual(verify.count("gh api"), 1)
        self.assertIn("actions/artifacts/9827444933", verify)
        self.assertIn("validate_parent_artifact_metadata_v10.py", verify)
        self.assertNotIn("--jq", verify)
        download = self._step(
            "acquire", "Download exact v0.9 failure checkpoint from parent run"
        )["with"]
        self.assertEqual(download["run-id"], "33577895166")
        self.assertEqual(download["repository"], "RoomyRems/momentumbot")
        names = [row.get("name") for row in self._steps("acquire")]
        recovery_index = names.index(
            "Validate and materialize exact parent checkpoint without credentials"
        )
        first_provider_index = names.index(
            "Acquire canonical split-rank scanner source inputs"
        )
        self.assertLess(recovery_index, first_provider_index)
        recovery = self._run(
            "acquire", "Validate and materialize exact parent checkpoint without credentials"
        )
        self.assertIn("--request-budget-output", recovery)
        self.assertIn("--blocked-attempt-output", recovery)
        self.assertIn("--child-environment-freeze", recovery)
        self.assertIn("--expected-child-commit-sha", recovery)
        self.assertIn("requirements-sealed-source-v04.txt", recovery)
        self.assertIn("float-normalization-rejections.json", recovery)
        self.assertIn("historical_source_recovery_v10", self.text)

    def test_only_scanner_provider_stage_can_run(self) -> None:
        forbidden = (
            "build_massive_historical_census.py",
            "audit_massive_instrument_metadata.py",
            "audit_massive_alpaca_market_coverage.py",
            "audit_historical_identity_continuity.py",
            "build_identity_resolved_market_discovery_v04.py",
            "SEC_USER_AGENT",
            "MASSIVE_API_KEY",
            "build_causal_news_enrichment_v10.py",
            "Acquire publication-timed causal news inputs",
        )
        for value in forbidden:
            self.assertNotIn(value, self.text)
        provider_steps = [
            self._run("acquire", "Acquire canonical split-rank scanner source inputs"),
        ]
        self.assertTrue(
            all("scripts/run_provider_entrypoint_v10.py" in run for run in provider_steps)
        )
        self.assertIn("build_causal_scanner_snapshot_v10.py", provider_steps[0])
        self.assertNotIn("build_causal_float_enrichment", "\n".join(provider_steps))

    def test_checkpoint_is_uploaded_before_separate_provider_free_freeze(self) -> None:
        acquire_names = [row.get("name") for row in self._steps("acquire")]
        self.assertLess(
            acquire_names.index("Build hash-inventoried recovery checkpoint without credentials"),
            acquire_names.index("Upload label-blind provider checkpoint before scanner freeze"),
        )
        freeze_text = "\n".join(
            str(row.get("run", "")) + str(row.get("env", ""))
            for row in self._steps("freeze")
        )
        for secret in (
            "ALPACA_API_KEY",
            "ALPACA_API_SECRET",
            "SEC_USER_AGENT",
            "MASSIVE_API_KEY",
        ):
            self.assertNotIn(secret, freeze_text)
        self.assertIn("--validate-existing", freeze_text)
        self.assertIn("--phase freeze-snapshots", freeze_text)
        self.assertIn("build_causal_scanner_snapshot_v10.py", freeze_text)
        self.assertIn("run_sealed_historical_source_acquisition_v10.py", freeze_text)

    def test_action_revisions_and_environment_are_pinned(self) -> None:
        for uses in (
            "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",
            "actions/setup-python@42375524e23c412d93fb67b49958b491fce71c38",
            "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093",
            "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
        ):
            self.assertIn(uses, self.text)
        for job, name in (
            ("validate", "Install pinned provider-free environment"),
            ("acquire", "Install exact acquisition environment without provider credentials"),
            ("freeze", "Recreate and verify exact provider-free environment"),
        ):
            run = self._run(job, name)
            self.assertIn("--require-hashes --only-binary=:all: --no-deps", run)
            self.assertIn("-m pip check", run)
        self.assertIn("MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_LIMIT: \"40000\"", self.text)
        optimized = self._run(
            "validate", "Repeat v0.10 safety gates under optimized Python"
        )
        self.assertIn("python -O -m unittest", optimized)

    def test_every_registered_runtime_artifact_triggers_push_validation(self) -> None:
        paths = set(self.workflow["on"]["push"]["paths"])
        expected = {path.as_posix() for path in REGISTRATION_ARTIFACT_PATHS.values()}
        self.assertEqual(expected - paths, set())

    def test_transcripts_databento_accounts_and_orders_are_absent(self) -> None:
        lowered = self.text.lower()
        for forbidden in ("transcript", "databento", "brokerage", "submit_order"):
            self.assertNotIn(forbidden, lowered)


if __name__ == "__main__":
    unittest.main()
