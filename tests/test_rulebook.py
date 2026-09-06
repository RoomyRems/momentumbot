import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from momentumbot.research.corpus import load_jsonl
from momentumbot.research.rulebook import (
    load_rulebook,
    rules_as_of,
    validate_evidence_against_corpus,
)


class RulebookTests(unittest.TestCase):
    def _sample(self):
        return [
            {
                "rule_id": "MB-SEL-001",
                "title": "Example",
                "category": "stock_selection",
                "statement": "Example rule",
                "observation_type": "rule",
                "decision_role": "deterministic",
                "confidence": 0.9,
                "status": "active",
                "applies_from": "2025-01-01",
                "implementation_notes": [],
                "contradictions_or_exceptions": [],
                "evidence": [
                    {
                        "video_id": "abc",
                        "title": "Video",
                        "published_at": "2025-01-01",
                        "mode": "normative_teaching",
                        "note": "Paraphrased evidence.",
                    }
                ],
            }
        ]

    def test_load_and_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.json"
            path.write_text(json.dumps(self._sample()), encoding="utf-8")
            rules = load_rulebook(path)
            self.assertEqual(len(rules), 1)
            self.assertEqual(rules_as_of(rules, date(2024, 12, 31)), [])
            self.assertEqual(len(rules_as_of(rules, date(2025, 1, 1))), 1)

    def test_duplicate_rule_ids_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.json"
            path.write_text(json.dumps(self._sample() * 2), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_rulebook(path)

    def test_manifest_loads_rule_bundles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "current").mkdir()
            bundle = root / "current" / "selection.json"
            bundle.write_text(json.dumps(self._sample()), encoding="utf-8")
            manifest = root / "current_rules.json"
            manifest.write_text(
                json.dumps({"schema_version": 1, "rule_files": ["current/selection.json"]}),
                encoding="utf-8",
            )
            self.assertEqual(len(load_rulebook(manifest)), 1)

    def test_evidence_registry_checks_title_and_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules_path = root / "rules.json"
            rules_path.write_text(json.dumps(self._sample()), encoding="utf-8")
            corpus_path = root / "corpus.jsonl"
            corpus_record = {
                "videoId": "abc",
                "title": "Video",
                "channelName": "Ross",
                "channelID": "c",
                "dateText": "Jan 1, 2025",
                "relativeDateText": None,
                "thumbnailUrl": None,
                "captions": "text",
                "status": "OK",
                "reason": None,
            }
            corpus_path.write_text(json.dumps(corpus_record), encoding="utf-8")
            problems = validate_evidence_against_corpus(
                load_rulebook(rules_path), load_jsonl([corpus_path])
            )
            self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
