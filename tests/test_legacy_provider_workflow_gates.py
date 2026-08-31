from __future__ import annotations

import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
LEGACY_PROVIDER_WORKFLOWS = (
    ROOT / ".github/workflows/massive-historical-census.yml",
    ROOT / ".github/workflows/causal-scanner-frozen-source.yml",
)


class LegacyProviderWorkflowGateTests(unittest.TestCase):
    def test_legacy_provider_workflows_are_manual_only(self) -> None:
        for path in LEGACY_PROVIDER_WORKFLOWS:
            with self.subTest(workflow=path.name):
                workflow = yaml.load(
                    path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader
                )
                self.assertEqual(set(workflow["on"]), {"workflow_dispatch"})
                self.assertNotIn("push", workflow["on"])
                self.assertNotIn("schedule", workflow["on"])
                self.assertIn("jobs", workflow)
                self.assertTrue(workflow["jobs"])
                for job in workflow["jobs"].values():
                    self.assertEqual(
                        job["if"], "github.event_name == 'workflow_dispatch'"
                    )


if __name__ == "__main__":
    unittest.main()
