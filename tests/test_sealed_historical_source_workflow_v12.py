from __future__ import annotations

from pathlib import Path
import unittest

import yaml
from yaml.constructor import ConstructorError


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/sealed-historical-source-acquisition-v12.yml"


class UniqueKeyLoader(yaml.BaseLoader):
    pass


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


class SealedHistoricalSourceWorkflowV12Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.workflow = yaml.load(cls.text, Loader=UniqueKeyLoader)
        cls.jobs = cls.workflow["jobs"]

    def _steps(self, job: str) -> list[dict[str, object]]:
        return self.jobs[job]["steps"]

    def _step(self, job: str, name: str) -> dict[str, object]:
        values = [row for row in self._steps(job) if row.get("name") == name]
        self.assertEqual(len(values), 1)
        return values[0]

    def test_push_runs_validation_only_and_manual_freeze_is_attempt_one(self) -> None:
        self.assertEqual(set(self.workflow["on"]), {"push", "workflow_dispatch"})
        self.assertEqual(set(self.jobs), {"validate", "freeze"})
        self.assertEqual(
            self.jobs["freeze"]["if"],
            "github.event_name == 'workflow_dispatch' && github.run_attempt == 1",
        )
        self.assertEqual(self.jobs["freeze"]["needs"], "validate")
        self.assertEqual(self.jobs["freeze"]["permissions"]["contents"], "read")

    def test_no_provider_credentials_or_provider_entrypoint_exists(self) -> None:
        for forbidden in (
            "ALPACA_API_KEY",
            "ALPACA_API_SECRET",
            "MASSIVE_API_KEY",
            "SEC_USER_AGENT",
            "run_provider_entrypoint",
            "build_causal_news_enrichment",
            "build_causal_float_enrichment",
            "phase acquire-source-inputs",
        ):
            self.assertNotIn(forbidden, self.text)
        self.assertNotIn("contents: write", self.text)

    def test_exact_parent_checkpoint_is_fetched_once_and_deeply_validated(self) -> None:
        metadata = self._step(
            "freeze", "Verify exact retained v0.10 provider checkpoint metadata"
        )["run"]
        self.assertEqual(str(metadata).count("gh api"), 1)
        self.assertIn("actions/artifacts/9877181150", str(metadata))
        download = self._step(
            "freeze", "Download exact v0.10 provider checkpoint"
        )["with"]
        self.assertEqual(download["run-id"], "33706372901")
        self.assertEqual(
            download["name"],
            "sealed-historical-source-acquisition-v10-provider-checkpoint-33706372901-1",
        )
        replay = self._step(
            "freeze", "Rehash and deeply validate exact 706-file provider checkpoint"
        )["run"]
        self.assertIn("--validate-existing", replay)
        self.assertIn("source-checkpoint.json", replay)

    def test_scanner_freeze_precedes_identity_compatible_final_replay(self) -> None:
        names = [row.get("name") for row in self._steps("freeze")]
        self.assertLess(
            names.index("Freeze scanner snapshots from canonical inputs without credentials"),
            names.index(
                "Build identity-compatible strict final deep replay without credentials"
            ),
        )
        final = self._step(
            "freeze", "Build identity-compatible strict final deep replay without credentials"
        )["run"]
        self.assertIn("run_sealed_historical_source_acquisition_v12.py", final)
        self.assertIn("--source-checkpoint", final)

    def test_same_step_environment_comparison_uses_explicit_venv_python(self) -> None:
        environment = str(
            self._step(
                "freeze", "Recreate and compare exact provider-free environment"
            )["run"]
        )
        self.assertIn(
            '"$GITHUB_WORKSPACE/.venv-v12/bin/python" - <<\'PY\'',
            environment,
        )
        self.assertNotIn("\npython - <<'PY'", environment)
        self.assertLess(
            environment.index("--no-build-isolation -e ."),
            environment.index(
                "from momentumbot.research."
                "sealed_historical_source_acquisition_v12 import"
            ),
        )

    def test_action_revisions_are_pinned(self) -> None:
        for uses in (
            "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",
            "actions/setup-python@42375524e23c412d93fb67b49958b491fce71c38",
            "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093",
            "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
        ):
            self.assertIn(uses, self.text)


if __name__ == "__main__":
    unittest.main()
