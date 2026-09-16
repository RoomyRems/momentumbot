from copy import deepcopy
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from momentumbot.research import scanner_source_archive as m
from tests.test_scanner_minutes import day, bar, reply

ROOT = Path(__file__).resolve().parents[1]


class SourceArchiveTests(unittest.TestCase):
    def pages(self, root, payloads):
        state = m.capture.MinutePages(root)
        pages = []
        for rows, token in payloads:
            request, response = state.request(), reply(rows, token)
            state.accept(request, response)
            pages.append((request, response['body']))
        return pages, state.result()

    def fixture(self):
        source = m.ScannerMinuteArchive.__new__(m.ScannerMinuteArchive)
        d = day(symbols=tuple(f'A{i:03d}' for i in range(251)))
        d['content_sha256'] = 'd' * 64
        source.days = {d['trading_date']: d}
        source.roots = m.capture.old.roots_for_day(d)
        source.summaries, source.locations, source.archives, source.inventories = {}, {}, {}, {}
        source.proof = {'content_sha256': 'a' * 64, 'archive_verification': {'archive_metadata': {'digest': 'sha256:' + 'b' * 64}}}
        for segment, root, rows in zip(('prefix', 'continuation'), source.roots,
                                      ({'A000': [bar()]}, {'A250': [bar('2026-03-04T15:00:00Z')]})):
            pages, summary = self.pages(root, [(rows, None)])
            request, body = pages[0]
            raw = io.BytesIO()
            with zipfile.ZipFile(raw, 'w') as z: z.writestr('00000.body.json', body)
            source.archives[segment] = zipfile.ZipFile(io.BytesIO(raw.getvalue()))
            source.inventories[segment] = {'00000.body.json': {'bytes': len(body), 'sha256': m.sha(body)}}
            key = root['content_sha256']
            source.summaries[key] = summary
            source.locations[key] = [(segment, '00000', request)]
        self.addCleanup(source.close)
        return source

    def test_both_segments_complete_membership_and_empty_symbols(self):
        source = self.fixture()
        value = source.read_day('2026-03-04')
        frames, p = value['rank_split_minute_bars_by_symbol'], value['provenance']
        self.assertEqual(len(frames), 251)
        self.assertEqual(p['bar_count'], 2)
        self.assertEqual(p['empty_member_count'], 249)
        self.assertEqual({r['segment'] for r in p['source_pages']}, {'prefix', 'continuation'})
        self.assertEqual(frames['A250'].index[0].isoformat(), '2026-03-04T15:00:00+00:00')
        self.assertEqual(list(frames['A000'].columns), ['close'])
        self.assertFalse(p['daily_minute_share_basis_verified'])
        self.assertFalse(p['historical_scanner_enabled'])
        value['previous_close_by_symbol']['A000'] = 9
        self.assertEqual(source.days['2026-03-04']['previous_close_by_symbol']['A000'], 2)

    def test_unknown_date_and_missing_root_do_not_become_empty(self):
        source = self.fixture()
        with self.assertRaises(ValueError): source.read_day('2026-03-05')
        source.roots.pop()
        with self.assertRaises(ValueError): source.read_day('2026-03-04')

    def test_changed_source_member_is_rejected(self):
        source = self.fixture()
        source.inventories['continuation']['00000.body.json']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'member bytes'): source.read_day('2026-03-04')

    def test_changed_dated_membership_or_previous_close_population_fails(self):
        for field in ('membership_symbols', 'previous_close_by_symbol'):
            source = self.fixture()
            d = source.days['2026-03-04']
            if field == 'membership_symbols': d[field].pop()
            else: d[field].pop('A000')
            with self.assertRaises(ValueError): source.read_day('2026-03-04')

    def test_projection_accepts_provider_symbol_reordering_but_not_time_regression(self):
        root = m.capture.old.roots_for_day(day())[0]
        pages, expected = self.pages(root, [({'BBB': [bar()]}, 'next'), ({'AAA': [bar()]}, None)])
        self.assertEqual(set(m.project_root(root, pages, expected)), {'AAA', 'BBB'})
        with self.assertRaises(ValueError): m.project_root(root, pages[:-1], expected)
        forged = deepcopy(expected);forged['bar_count'] += 1
        with self.assertRaises(ValueError): m.project_root(root, pages, forged)
        pages, expected = self.pages(root, [({'AAA': [bar()]}, 'next'), ({'AAA': [bar('2026-03-04T09:01:00Z')]}, None)])
        pages[-1] = (pages[-1][0], reply({'AAA': [bar()]})['body'])
        with self.assertRaises(ValueError): m.project_root(root, pages, expected)

    def test_accepted_proof_is_fixed_original_archive(self):
        p = ROOT / m.BASE / 'verification.zip'
        proof = m.accepted_proof(p)
        self.assertEqual(proof['total_bar_count'], 5230052)
        self.assertEqual(proof['total_attempts'], 703)
        with tempfile.TemporaryDirectory() as td:
            changed = Path(td) / 'changed.zip';changed.write_bytes(p.read_bytes() + b'changed')
            with self.assertRaises(ValueError): m.accepted_proof(changed)

    def test_constructor_rejects_unpinned_capture_and_closes_on_failure(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'fake.zip';path.write_bytes(b'not the accepted capture')
            with self.assertRaises(ValueError): m.ScannerMinuteArchive(ROOT, path)

    def test_close_is_idempotent(self):
        source = self.fixture();archives = list(source.archives.values())
        source.close();source.close()
        self.assertFalse(source.archives)
        self.assertTrue(all(z.fp is None for z in archives))

    def test_original_archive_parts_preserve_bytes_and_reject_truncation(self):
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, 'w') as z: z.writestr('example', 'source bytes')
        data = raw.getvalue();pin = {'bytes': len(data), 'sha256': m.sha(data)}
        with tempfile.TemporaryDirectory() as td:
            a, b = Path(td) / 'part0', Path(td) / 'part1'
            a.write_bytes(data[:30]);b.write_bytes(data[30:])
            with m.open_capture([a, b], pin) as archive:
                a.write_bytes(b'changed')
                self.assertEqual(archive.read('example'), b'source bytes')
            a.write_bytes(data[:30])
            for parts in ([a], [b, a], [a, a], []):
                with self.assertRaises(ValueError): m.open_capture(parts, pin)
            b.write_bytes(b.read_bytes()[:-1] + b'x')
            with self.assertRaises(ValueError): m.open_capture([a, b], pin)

    def test_cli_imports_with_documented_pythonpath(self):
        import os
        import subprocess
        import sys
        result = subprocess.run([sys.executable, 'scripts/verify_scanner_source_archive.py', '--help'],
            cwd=ROOT, env={**os.environ, 'PYTHONPATH': 'src:scripts'}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--capture-zip', result.stdout)


if __name__ == '__main__': unittest.main()
