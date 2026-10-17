import hashlib
import json
from pathlib import Path
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'docs/agent-workflow/runs/source-preservation-daily-2026-10-17/source-preservation.json'


class PreservationInventoryTests(unittest.TestCase):
    def test_all_recorded_proof_references_have_recovery_locations(self):
        value = json.loads(MANIFEST.read_text()); refs = value['references']
        self.assertEqual(len(refs), 14)
        self.assertEqual(len({r['artifact_id'] for r in refs}), 14)
        self.assertEqual(len({r['proof'] for r in refs}), 7)
        external = [r for r in refs if r['preservation'] == 'saved_original_archive']
        self.assertEqual(len(external), value['saved_archive_count'])
        self.assertEqual(sum(r['bytes'] for r in external), value['saved_archive_bytes'])
        for r in refs:
            with self.subTest(artifact=r['artifact_id']), zipfile.ZipFile(ROOT / r['proof']) as z:
                original = json.loads(z.read(r['proof_member']))
                self.assertEqual((r['artifact_id'], r['bytes'], r['sha256']),
                                 (original['id'], original['size_in_bytes'], original['digest'][7:]))
                self.assertEqual(r['source_commit'], original['workflow_run']['head_sha'])
            if r['preservation'] == 'git':
                data = (ROOT / r['git_path']).read_bytes()
                self.assertEqual((len(data), hashlib.sha256(data).hexdigest()), (r['bytes'], r['sha256']))
            else:
                self.assertEqual(r['saved_filename'], f"momentumbot-{r['artifact_id']}-original.zip")
        # This test checks the inventory and Git bytes; remote durability is an
        # observed upload receipt, not something offline CI can re-prove.


if __name__ == '__main__': unittest.main()
