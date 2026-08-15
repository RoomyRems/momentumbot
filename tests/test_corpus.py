import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from momentumbot.research.corpus import audit_corpus, load_jsonl, normalize_captions, parse_publication_date, split_as_of


class CorpusTests(unittest.TestCase):
    def test_normalizes_html_and_whitespace(self):
        self.assertEqual(normalize_captions("A&amp;B\n  C\u00a0D"), "A&B C D")

    def test_parse_publication_date(self):
        self.assertEqual(parse_publication_date("Aug 14, 2026"), date(2026, 8, 14))
        self.assertIsNone(parse_publication_date(None))

    def _write_records(self, rows):
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "sample.jsonl"
        path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
        return tmp, path

    def test_as_of_quarantines_future_and_unknown_dates(self):
        base = {"channelName":"Ross Cameron - Warrior Trading","channelID":"channel","relativeDateText":None,"thumbnailUrl":None,"status":"OK","reason":None}
        rows = [
            dict(base, videoId="past", title="Past", dateText="Jan 1, 2025", captions="first pullback"),
            dict(base, videoId="future", title="Future", dateText="Jan 1, 2027", captions="hidden seller"),
            dict(base, videoId="unknown", title="Unknown", dateText=None, captions="relative volume"),
        ]
        tmp, path = self._write_records(rows); self.addCleanup(tmp.cleanup)
        eligible, future, undated = split_as_of(load_jsonl([path]), date(2026, 1, 1))
        self.assertEqual([r.video_id for r in eligible], ["past"])
        self.assertEqual([r.video_id for r in future], ["future"])
        self.assertEqual([r.video_id for r in undated], ["unknown"])

    def test_audit_detects_duplicate_ids(self):
        base = {"channelName":"Ross Cameron - Warrior Trading","channelID":"channel","dateText":"Jan 1, 2025","relativeDateText":None,"thumbnailUrl":None,"captions":"five pillars relative volume","status":"OK","reason":None}
        rows = [dict(base, videoId="same", title="A"), dict(base, videoId="same", title="B")]
        tmp, path = self._write_records(rows); self.addCleanup(tmp.cleanup)
        audit = audit_corpus(load_jsonl([path]))
        self.assertEqual(audit.records, 2)
        self.assertEqual(audit.unique_video_ids, 1)
        self.assertEqual(audit.duplicate_video_ids, 1)


if __name__ == "__main__":
    unittest.main()
