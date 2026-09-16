from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from momentumbot.research import candidate_raw_minutes as m
from tests.test_scanner_minutes import day, bar, Clock, KEYS, reply

ROOT = Path(__file__).resolve().parents[1]


class CandidateRawTests(unittest.TestCase):
    def test_raw_only_symbols_cross_selection_boundary_and_dst(self):
        source = day('2026-03-09')
        before = deepcopy(source)
        roots = m.roots_for_day(source, ['AAA'])
        self.assertEqual(source, before)
        self.assertEqual(roots[0]['params']['adjustment'], 'raw')
        self.assertEqual(roots[0]['params']['symbols'], 'AAA')
        self.assertEqual(roots[0]['params']['start'], '2026-03-09T08:00:00+00:00')
        self.assertEqual(roots[0]['params']['end'], '2026-03-09T14:00:00+00:00')
        self.assertEqual(set(roots[0]), {'provider', 'method', 'url', 'trading_date',
            'membership_sha256', 'params', 'content_sha256'})
        for bad in [[], ['BBB', 'AAA'], ['AAA', 'AAA'], ['OTHER']]:
            with self.subTest(bad=bad), self.assertRaises(ValueError): m.roots_for_day(source, bad)

    def test_reordered_symbols_preserve_strict_per_symbol_time(self):
        state = m.State(m.roots_for_day(day(), ['AAA', 'BBB']))
        state.accept(state.request(), reply({'BBB': [bar()]}, 'next'))
        state.accept(state.request(), reply({'AAA': [bar()]}))
        self.assertTrue(state.results)
        state = m.State(m.roots_for_day(day(), ['AAA', 'BBB']))
        state.accept(state.request(), reply({'BBB': [bar()]}, 'next'))
        with self.assertRaises(ValueError): state.accept(state.request(), reply({'BBB': [bar()]}))
        with self.assertRaises(ValueError): state.request()

    def create_capture(self, output, transport):
        clock = Clock()
        contract = {'requests': m.roots_for_day(day(), ['AAA', 'BBB'])}
        capture = m.Capture(contract, output=output, transport=transport, keys=KEYS,
            clock_ns=clock.read, sleeper=clock.sleep,
            utc_now=lambda: datetime(2026, 9, 16, tzinfo=timezone.utc).isoformat())
        return capture, contract

    def test_original_archive_round_trip_empty_members_and_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / 'capture'
            capture, contract = self.create_capture(output, lambda r, k: reply({'AAA': [bar()]}))
            self.assertTrue(capture.run()['protocol_complete'])
            archive = Path(td) / 'source.zip'
            def pack():
                with zipfile.ZipFile(archive, 'w') as z:
                    for p in output.iterdir(): z.write(p, p.name)
                return {'size_in_bytes': archive.stat().st_size, 'digest': 'sha256:' + m.sha(archive.read_bytes())}
            metadata = pack()
            pin = m.sha((output / 'inventory.json').read_bytes())
            result = m.verify_archive(archive, metadata, pin, contract)
            self.assertEqual((result['bar_count'], result['symbol_dates'], result['empty_symbol_dates']), (1, 2, 1))
            self.assertEqual(result['contract_id'], m.ID)
            self.assertFalse(result['historical_scanner_enabled'])
            with self.assertRaises(ValueError): m.verify_archive(archive, metadata, 'f' * 64, contract)
            changed = deepcopy(contract); changed['requests'][0]['params']['adjustment'] = 'split'
            with self.assertRaises(ValueError): m.verify_archive(archive, metadata, pin, changed)
            (output / '00000.body.json').write_bytes(reply({'AAA': [bar(c=2.6)]})['body'])
            with self.assertRaises(ValueError): m.verify_archive(archive, pack(), pin, contract)

    def test_failed_http_retained_without_retry_or_empty_success(self):
        with tempfile.TemporaryDirectory() as td:
            calls = []
            def transport(request, keys):
                calls.append(request)
                return {**reply({}), 'status': 429}
            output = Path(td) / 'capture'
            capture, _ = self.create_capture(output, transport)
            self.assertFalse(capture.run()['protocol_complete'])
            self.assertEqual(len(calls), 1)
            self.assertTrue((output / '00000.body.json').exists())

    def test_attempt_ceiling_stops_before_transport(self):
        with tempfile.TemporaryDirectory() as td:
            calls = []
            capture, _ = self.create_capture(Path(td) / 'capture', lambda r, k: calls.append(r))
            with patch.object(m, 'MAX_ATTEMPTS', 0), self.assertRaises(ValueError):
                capture.run()
            saved = m.parse((Path(td) / 'capture' / 'report.json').read_bytes())
            self.assertFalse(saved['protocol_complete'])
            self.assertEqual(saved['failure'], 'interrupted')
            self.assertEqual(calls, [])

    def test_bad_preflight_does_not_read_credentials(self):
        calls = []
        with patch.object(m, 'preflight', side_effect=ValueError('gate')):
            with self.assertRaises(ValueError):
                m.capture(None, None, None, None, None, None, None, None, output='unused',
                    credential_loader=lambda: calls.append(True), transport=None, progress=None)
        self.assertEqual(calls, [])

    def test_real_saved_population_and_workflow(self):
        import yaml
        value = m.validate_registration(ROOT)
        self.assertEqual(len(value['requests']), 30)
        self.assertEqual(sum(len(r['params']['symbols'].split(',')) for r in value['requests']), 4018)
        self.assertEqual({r['params']['adjustment'] for r in value['requests']}, {'raw'})
        self.assertFalse(value['daily_minute_share_basis_verified'])
        self.assertFalse(value['exact_same_time_rvol_complete'])
        self.assertFalse(value['acquisition_filter_values_allowed_in_runtime'])
        self.assertLess(len(m.render(value)), m.gate.d.previous.PREFLIGHT_LIMIT - 100000)
        source = (ROOT / m.WORKFLOW).read_text()
        self.assertEqual(source.count('secrets.'), 2)
        workflow = yaml.safe_load(source)
        self.assertEqual(set(workflow['jobs']), {'consume', 'capture', 'verify'})
        for job in workflow['jobs'].values(): self.assertEqual(job['if'], 'github.run_attempt == 1')
        self.assertIn('same 30 dates', value['authorization']['scope'])

    def test_cli_validation_hosted_import_path(self):
        result = subprocess.run([sys.executable, 'scripts/run_candidate_raw_minutes.py', 'validate'],
            cwd=ROOT, env={**os.environ, 'PYTHONPATH': 'src:scripts'}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"roots": 30', result.stdout)


if __name__ == '__main__': unittest.main()
