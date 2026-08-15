import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from momentumbot.research.rulebook import load_rulebook, rules_as_of


class RulebookTests(unittest.TestCase):
    def _sample(self):
        return [{"rule_id":"MB-SEL-001","title":"Example","category":"stock_selection","statement":"Example rule","observation_type":"rule","decision_role":"deterministic","confidence":0.9,"status":"active","applies_from":"2025-01-01","implementation_notes":[],"contradictions_or_exceptions":[],"evidence":[{"video_id":"abc","title":"Video","published_at":"2025-01-01","mode":"normative_teaching","note":"Paraphrased evidence."}]}]

    def test_load_and_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.json"; path.write_text(json.dumps(self._sample()), encoding="utf-8")
            rules = load_rulebook(path)
            self.assertEqual(len(rules), 1)
            self.assertEqual(rules_as_of(rules, date(2024, 12, 31)), [])
            self.assertEqual(len(rules_as_of(rules, date(2025, 1, 1))), 1)

    def test_duplicate_rule_ids_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.json"; path.write_text(json.dumps(self._sample() * 2), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_rulebook(path)


if __name__ == "__main__":
    unittest.main()
