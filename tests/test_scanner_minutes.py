from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from momentumbot.research import scanner_minutes as m
from tests.test_early_pullback_census_v01 import Clock
from tests.test_alias_completion import KEYS, reply

ROOT = Path(__file__).resolve().parents[1]


def day(target='2026-03-04', symbols=('AAA', 'BBB')):
    return {'trading_date': target, 'membership_symbols': list(symbols),
        'membership_sha256': 'a' * 64, 'previous_close_by_symbol': dict.fromkeys(symbols, 2)}


def bar(stamp='2026-03-04T09:00:00Z', **changes):
    return {'t': stamp, 'o': 2, 'h': 3, 'l': 1, 'c': 2.5, 'v': 100, 'n': 3, 'vw': 2.2, **changes}


class MinuteTests(unittest.TestCase):
    def state(self): return m.MinutePages(m.roots_for_day(day())[0])

    def test_membership_batches_include_every_symbol_and_keep_dst(self):
        symbols = tuple(f'A{i:04}' for i in range(501))
        roots = m.roots_for_day(day(symbols=symbols))
        self.assertEqual([len(r['params']['symbols'].split(',')) for r in roots], [250, 250, 1])
        self.assertEqual([s for r in roots for s in r['params']['symbols'].split(',')], list(symbols))
        self.assertTrue(all(r['params']['adjustment'] == 'split' and r['params']['asof'] == '2026-03-04' for r in roots))
        self.assertEqual(roots[0]['params']['start'], '2026-03-04T09:00:00+00:00')
        after = m.roots_for_day(day('2026-03-10'))[0]
        self.assertEqual(after['params']['start'], '2026-03-10T08:00:00+00:00')
        self.assertEqual(after['params']['end'], '2026-03-10T14:00:00+00:00')

    def test_missing_close_and_duplicate_members_fail(self):
        for value in [day(symbols=('AAA', 'AAA')), {**day(), 'previous_close_by_symbol': {'AAA': 2}}]:
            with self.assertRaises(ValueError): m.roots_for_day(value)

    def test_multiple_minutes_same_day_are_valid(self):
        s = self.state()
        s.accept(s.request(), reply({'AAA': [bar(), bar('2026-03-04T09:01:00Z')]}))
        self.assertEqual(s.result()['symbol_bar_counts'], {'AAA': 2, 'BBB': 0})
        self.assertEqual(s.result()['empty_symbols'], ['BBB'])

    def test_cursor_progress_does_not_infer_omitted_symbol_empty(self):
        s = self.state()
        s.accept(s.request(), reply({'AAA': [bar()]}, 'next'))
        with self.assertRaises(ValueError): s.result()
        self.assertEqual(s.request()['params']['page_token'], 'next')
        s.accept(s.request(), reply({'BBB': [bar()]}))
        self.assertEqual(s.result()['bar_count'], 2)
        self.assertEqual(s.result()['empty_symbols'], [])

    def test_terminal_empty_requires_success(self):
        for payload in [None, {}]:
            s = self.state();s.accept(s.request(), reply(payload))
            self.assertEqual(s.result()['empty_symbols'], ['AAA', 'BBB'])
            with self.assertRaises(ValueError): s.request()

    def test_invalid_rows_close_state_permanently(self):
        bad = [{'AAA': [bar(n=True)]}, {'AAA': [bar(c=True)]}, {'AAA': [bar(h=1)]},
            {'AAA': [bar('2026-03-04T08:59:00Z')]}, {'AAA': [bar('2026-03-04T15:01:00Z')]},
            {'AAA': [bar('2026-03-04T09:00:01Z')]}, {'AAA': [bar('2026-03-04T09:00:00')]},
            {'AAA': [bar(ross_fill=7)]}, {'OTHER': [bar()]}, {'AAA': [bar(), bar()]}]
        for rows in bad:
            s = self.state()
            with self.subTest(rows=rows), self.assertRaises(ValueError): s.accept(s.request(), reply(rows))
            with self.assertRaises(ValueError): s.request()

    def test_repeated_cursor_and_cross_page_order_fail(self):
        for rows, token in [({'AAA': [bar('2026-03-04T09:01:00Z')]}, 'next'), ({'AAA': [bar()]}, None)]:
            s = self.state();s.accept(s.request(), reply({'AAA': [bar()]}, 'next'))
            with self.assertRaises(ValueError): s.accept(s.request(), reply(rows, token))

    def test_nonterminal_empty_and_page_ceiling_fail(self):
        s = self.state()
        with self.assertRaises(ValueError): s.accept(s.request(), reply({}, 'next'))
        s = self.state()
        with patch.object(m, 'MAX_PAGES', 1), self.assertRaises(ValueError):
            s.accept(s.request(), reply({'AAA': [bar()]}, 'next'))

    def test_http_failure_is_not_empty(self):
        s = self.state()
        with self.assertRaises(ValueError): s.accept(s.request(), {**reply({}), 'status': 429})
        with self.assertRaises(ValueError): s.result()

    def test_exact_next_request_required(self):
        s = self.state();r = s.request();r['params']['adjustment'] = 'raw'
        with self.assertRaises(ValueError): s.accept(r, reply({}))

    def test_inclusive_provider_cutoff_kept_as_bar_start(self):
        s = self.state();s.accept(s.request(), reply({'AAA': [bar('2026-03-04T15:00:00Z')]}))
        self.assertEqual(s.result()['bar_count'], 1)
        # Frozen downstream feature builder applies start + 1 minute, so this
        # boundary bar cannot affect the 10:00 decision.

    def capture(self, directory, transport):
        clock = Clock()
        contract = {'requests': m.roots_for_day(day())}
        capture = m.Capture(contract, output=directory, transport=transport, keys=KEYS,
            clock_ns=clock.read, sleeper=clock.sleep, utc_now=lambda: datetime(2026, 9, 15, tzinfo=timezone.utc).isoformat())
        return capture, contract

    def test_synthetic_capture_original_archive_replay_and_tampering(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / 'capture'
            capture, contract = self.capture(output, lambda r, k: reply({'AAA': [bar()]}))
            report = capture.run()
            self.assertTrue(report['protocol_complete'])
            archive = Path(td) / 'source.zip'
            def pack():
                with zipfile.ZipFile(archive, 'w') as z:
                    for p in output.iterdir(): z.write(p, p.name)
                return {'size_in_bytes': archive.stat().st_size, 'digest': 'sha256:' + m.sha(archive.read_bytes())}
            metadata = pack();pin = m.sha((output / 'inventory.json').read_bytes())
            result = m.verify_archive(archive, metadata, pin, contract)
            self.assertEqual((result['bar_count'], result['symbol_dates'], result['empty_symbol_dates']), (1, 2, 1))
            self.assertEqual(result['provider_requests'], 0)
            previous, frames = m.read_rank_day(archive, result, contract, day())
            self.assertEqual(previous, {'AAA': 2, 'BBB': 2})
            self.assertEqual(frames['AAA'].iloc[0]['close'], 2.5)
            self.assertEqual(frames['AAA'].index[0].isoformat(), '2026-03-04T09:00:00+00:00')
            self.assertTrue(frames['BBB'].empty)
            with self.assertRaises(ValueError): m.read_rank_day(archive, result, contract, day(symbols=('AAA',)))
            with self.assertRaises(ValueError): m.verify_archive(archive, metadata, 'f' * 64, contract)
            (output / '00000.body.json').write_bytes(reply({'AAA': [bar(c=2.6)]})['body'])
            metadata = pack()
            with self.assertRaises(ValueError): m.verify_archive(archive, metadata, pin, contract)
            with self.assertRaises(ValueError): capture.run()

    def test_failed_response_retained_once(self):
        with tempfile.TemporaryDirectory() as td:
            calls = []
            def transport(request, keys):
                calls.append(request)
                return {**reply({}), 'status': 429}
            capture, _ = self.capture(Path(td) / 'capture', transport)
            self.assertFalse(capture.run()['protocol_complete'])
            self.assertEqual(len(calls), 1)
            self.assertTrue((Path(td) / 'capture' / '00000.body.json').exists())

    def test_preflight_failure_does_not_read_credentials(self):
        credentials = []
        with patch.object(m, 'preflight', side_effect=ValueError('gate')):
            with self.assertRaises(ValueError):
                m.capture(None, None, None, None, None, None, None, None, output='unused',
                    credential_loader=lambda: credentials.append(True), transport=None, progress=None)
        self.assertEqual(credentials, [])

    def test_full_source_plan_and_workflow_are_bound(self):
        import yaml
        contract = m.registration(ROOT)
        roots = contract['requests']
        self.assertEqual(len(roots), 690)
        self.assertEqual(sum(len(r['params']['symbols'].split(',')) for r in roots), 165694)
        self.assertEqual(len(set(r['trading_date'] for r in roots)), 30)
        self.assertLess(len(m.render(contract)), m.gate.d.previous.PREFLIGHT_LIMIT - 100000)
        workflow = yaml.safe_load((ROOT / m.WORKFLOW).read_text())
        self.assertEqual(set(workflow['jobs']), {'consume', 'capture', 'verify'})
        for job in workflow['jobs'].values(): self.assertEqual(job['if'], 'github.run_attempt == 1')
        source = (ROOT / m.WORKFLOW).read_text()
        self.assertNotIn('MASSIVE_MAIN_API_KEY', source)
        self.assertEqual(source.count('secrets.'), 2)

    def test_cli_validates_with_hosted_import_path(self):
        import os
        import subprocess
        import sys
        result = subprocess.run([sys.executable, 'scripts/run_hosted_scanner_source.py', 'validate'],
            cwd=ROOT, env={**os.environ, 'PYTHONPATH': 'src:scripts'}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"roots": 690', result.stdout)


if __name__ == '__main__': unittest.main()
