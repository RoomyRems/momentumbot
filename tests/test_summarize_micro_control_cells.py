import json
import tempfile
import unittest
from pathlib import Path

from scripts.summarize_micro_control_cells import build_control_comparison


class MicroControlSummaryTests(unittest.TestCase):
    def _score(self, cell: str) -> dict[str, object]:
        payload: dict[str, object] = {
            "knowledge_policy": "post_replay_retrospective_evaluation_only",
            "benchmark_id": "ross-yolo-2025-09-09-micro-boundary-01",
            "symbol": "YOLO",
            "case_role": "boundary_context_only",
            "upstream_runtime_available": True,
            "runtime_status": "replayed",
            "runtime_plan_count": 1,
            "runtime_filled_count": 0,
            "runtime_filled_pullback_numbers": [],
            "matching_dimensions": 0,
            "comparable_dimensions": 0,
            "scored_dimensions": {},
            "exact_human_trade_identity_scored": False,
            "price_references_descriptive_only": {
                "first_runtime_fill_price": None,
            },
        }
        identities = {
            "baseline": ("frozen_policy_id", "micro-v0.1"),
            "context_only": (
                "ablation_id",
                "micro-v0.2a-prequalification-context",
            ),
            "volume_only": (
                "ablation_id",
                "micro-v0.2c-no-hard-volume-gate",
            ),
            "context_plus_volume": (
                "ablation_id",
                "micro-v0.2d-context-no-hard-volume-gate",
            ),
        }
        key, value = identities[cell]
        payload[key] = value
        if key == "frozen_policy_id":
            payload["frozen_policy_fingerprint"] = "a" * 64
        else:
            payload["ablation_fingerprint"] = "b" * 64
            payload["parent_frozen_policy_id"] = "micro-v0.1"
            payload["parent_frozen_policy_fingerprint"] = "a" * 64
        return payload

    def _write_scores(self, root: Path) -> None:
        for cell in (
            "baseline",
            "context_only",
            "volume_only",
            "context_plus_volume",
        ):
            path = root / cell / "case-score.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(self._score(cell)), encoding="utf-8")

    def test_builds_boundary_control_without_inventing_scored_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_scores(root)
            artifact = build_control_comparison(root)

        self.assertEqual(artifact["schema_version"], 2)
        self.assertEqual(artifact["case_role"], "boundary_context_only")
        self.assertEqual(artifact["manifest_scored_dimensions"], [])
        self.assertTrue(artifact["upstream_runtime_available"])
        self.assertEqual(
            set(artifact["cells"]),
            {"baseline", "context_only", "volume_only", "context_plus_volume"},
        )
        self.assertEqual(
            artifact["cells"]["context_plus_volume"]["policy_id"],
            "micro-v0.2d-context-no-hard-volume-gate",
        )

    def test_rejects_mixed_control_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_scores(root)
            path = root / "volume_only" / "case-score.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["symbol"] = "WRONG"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "different benchmark control"):
                build_control_comparison(root)


if __name__ == "__main__":
    unittest.main()
