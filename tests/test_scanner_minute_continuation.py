from pathlib import Path
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from unittest.mock import patch

from momentumbot.research import scanner_minute_continuation as m
from tests.test_scanner_minutes import day, bar, reply, KEYS
from tests.test_early_pullback_census_v01 import Clock

ROOT = Path(__file__).resolve().parents[1]


class ContinuationTests(unittest.TestCase):
    def state(self): return m.MinutePages(m.old.roots_for_day(day())[0])

    def test_mapped_symbol_can_arrive_on_later_page(self):
        s = self.state();s.accept(s.request(), reply({'BBB': [bar()]}, 'next'))
        s.accept(s.request(), reply({'AAA': [bar()]}))
        self.assertEqual(s.result()['symbol_bar_counts'], {'AAA': 1, 'BBB': 1})
        old = m.old.MinutePages(m.old.roots_for_day(day())[0])
        old.accept(old.request(), reply({'BBB': [bar()]}, 'next'))
        with self.assertRaisesRegex(ValueError, 'regressing minute'): old.accept(old.request(), reply({'AAA': [bar()]}))

    def test_symbol_time_cannot_regress_when_other_symbols_intervene(self):
        for stamp in ['2026-03-04T09:00:00Z', '2026-03-04T09:01:00Z']:
            s = self.state();s.accept(s.request(), reply({'AAA': [bar('2026-03-04T09:01:00Z')]}, 'one'))
            s.accept(s.request(), reply({'BBB': [bar()]}, 'two'))
            with self.assertRaises(ValueError): s.accept(s.request(), reply({'AAA': [bar(stamp)]}))
            with self.assertRaises(ValueError): s.request()

    def test_schema_window_and_order_guards_remain(self):
        bad = [{'AAA': [bar(n=True)]}, {'AAA': [bar('2026-03-04T15:01:00Z')]},
            {'AAA': [bar(), bar()]}, {'AAA': [bar('2026-03-04T09:02:00Z'), bar()]},
            {'NOPE': [bar()]}, {'AAA': [bar(ross_fill=4)]}]
        for rows in bad:
            s = self.state()
            with self.assertRaises(ValueError): s.accept(s.request(), reply(rows))
            with self.assertRaises(ValueError): s.result()

    def test_empty_failure_cursor_and_page_limits_remain(self):
        s = self.state()
        with self.assertRaises(ValueError): s.accept(s.request(), reply({}, 'next'))
        s = self.state();s.accept(s.request(), reply({'BBB': [bar()]}, 'same'))
        with self.assertRaises(ValueError): s.accept(s.request(), reply({'AAA': [bar()]}, 'same'))
        s = self.state()
        with self.assertRaises(ValueError): s.accept(s.request(), {**reply({}), 'status': 429})
        s = self.state()
        with patch.object(m.old, 'MAX_PAGES', 1), self.assertRaises(ValueError): s.accept(s.request(), reply({'AAA': [bar()]}, 'next'))

    def test_original_failure_repaired_without_repeating_requests(self):
        state = m.replay_prefix(ROOT)
        self.assertEqual(len(state.results), 86)
        self.assertEqual(state.request()['root_sha256'], state.tasks[86]['content_sha256'])
        self.assertEqual(state.request()['page'], 1)
        self.assertEqual(state.results[-1]['symbol_bar_counts']['R'], 20)

    def test_remaining_contract_and_cli(self):
        import os, subprocess, sys
        contract = m.validate_registration(ROOT)
        self.assertEqual(len(contract['requests']), 604)
        self.assertEqual(contract['requests'], m.old.validate_registration(ROOT)['requests'][86:])
        self.assertEqual(contract['limits']['maximum_attempts'] + 87, m.old.MAX_ATTEMPTS)
        r = subprocess.run([sys.executable, 'scripts/run_scanner_minute_continuation.py', 'validate'],
            cwd=ROOT, env={**os.environ, 'PYTHONPATH': 'src:scripts'}, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"roots": 604', r.stdout)

    def test_capture_archive_roundtrip_with_symbol_page_reordering(self):
        clock = Clock();contract = {'requests': m.old.roots_for_day(day())}
        with tempfile.TemporaryDirectory() as td:
            output=Path(td)/'source'
            def transport(r, k): return reply({'BBB': [bar()]}, 'next') if r['page']==1 else reply({'AAA': [bar()]})
            capture=m.Capture(contract, output=output, transport=transport, keys=KEYS,
                clock_ns=clock.read, sleeper=clock.sleep, utc_now=lambda: datetime(2026,9,15,tzinfo=timezone.utc).isoformat())
            report=capture.run();self.assertTrue(report['protocol_complete'])
            archive=Path(td)/'original.zip'
            with zipfile.ZipFile(archive,'w') as z:
                for p in output.iterdir():z.write(p,p.name)
            metadata={'size_in_bytes':archive.stat().st_size,'digest':'sha256:'+m.sha(archive.read_bytes())}
            result=m.verify_archive(archive,metadata,m.sha((output/'inventory.json').read_bytes()),contract)
            self.assertEqual(result['attempt_count'],2)
            self.assertEqual(result['bar_count'],2)
            with self.assertRaises(ValueError):m.verify_archive(archive,metadata,'a'*64,contract)


if __name__ == '__main__':unittest.main()
