from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from momentumbot.research import candidate_daily_history as m
from tests.test_scanner_minutes import day, bar, Clock, KEYS, reply

ROOT = Path(__file__).resolve().parents[1]


def root():
    return m.history_root(m.parent.roots_for_day(day('2026-03-09'), ['AAA', 'BBB'])[0])


def history(count=60):
    days = [date(2026, 3, 8) - timedelta(days=i) for i in range(110)]
    days = sorted(d for d in days if d.weekday() < 5)[-count:]
    return [bar(datetime.combine(d, time(), m.daily.ET).astimezone(timezone.utc).isoformat(), v=i+1)
            for i, d in enumerate(days)]


class DailyHistoryTests(unittest.TestCase):
    def test_exact_population_and_prior_window_with_dst(self):
        r = root()
        self.assertEqual(r['params']['start'], '2025-11-09T05:00:00+00:00')
        self.assertEqual(r['params']['end'], '2026-03-09T03:59:59+00:00')
        self.assertEqual((r['params']['asof'],r['params']['timeframe'],r['params']['adjustment']),
            ('2026-03-09', '1Day', 'split'))
        self.assertEqual(r['params']['symbols'], 'AAA,BBB')

    def test_last_50_observed_sessions_and_original_average(self):
        r=root();p=m.DailyPages(r);q=p.request();body=reply({'AAA':history()})['body']
        p.accept(q, {'status':200,'complete':True,'encoding':'identity','body':body})
        expected=p.result();values=m.project_history_root(r, [(q,body)], expected)
        self.assertEqual(values['AAA']['average_daily_volume_50'], 35.5)
        self.assertEqual(len(values['AAA']['prior_sessions']),50)
        self.assertTrue(values['AAA']['sufficient_history'])
        self.assertEqual(values['BBB']['prior_sessions'],[])
        self.assertIsNone(values['BBB']['average_daily_volume_50'])
        self.assertEqual(expected['insufficient_history_symbols'],['BBB'])
        self.assertEqual(len(values['AAA']['daily_bars']),60)

    def test_short_history_never_padded(self):
        r=root();p=m.DailyPages(r);q=p.request();b=reply({'AAA':history(49)})
        p.accept(q,b);value=m.project_history_root(r,[(q,b['body'])],p.result())['AAA']
        self.assertEqual(len(value['prior_sessions']),49)
        self.assertIsNone(value['average_daily_volume_50'])
        self.assertFalse(value['sufficient_history'])

    def test_target_future_duplicate_and_outside_window_fail_closed(self):
        for rows in [[bar('2026-03-09T04:00:00Z')], [bar('2026-03-10T04:00:00Z')],
                     [bar('2025-11-08T05:00:00Z')], [bar('2026-03-06T05:00:00Z'),bar('2026-03-06T06:00:00Z')]]:
            p=m.DailyPages(root())
            with self.subTest(rows=rows),self.assertRaises(ValueError):p.accept(p.request(),reply({'AAA':rows}))
            with self.assertRaises(ValueError):p.result()

    def test_cross_page_session_duplicate_and_symbol_reorder(self):
        p=m.DailyPages(root());p.accept(p.request(),reply({'BBB':history(1)},'next'))
        p.accept(p.request(),reply({'AAA':history(1)}));self.assertEqual(p.result()['bar_count'],2)
        p=m.DailyPages(root());p.accept(p.request(),reply({'AAA':[bar('2026-03-06T05:00:00Z')]},'next'))
        with self.assertRaises(ValueError):p.accept(p.request(),reply({'AAA':[bar('2026-03-06T06:00:00Z')]}))

    def test_zero_volume_is_not_positive_average(self):
        r=root();p=m.DailyPages(r);q=p.request();b=reply({'AAA':[{**x,'v':0} for x in history()]})
        p.accept(q,b);value=m.project_history_root(r,[(q,b['body'])],p.result())['AAA']
        self.assertTrue(value['sufficient_history']);self.assertIsNone(value['average_daily_volume_50'])

    def test_original_archive_replay_and_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'capture';clock=Clock();contract={'requests':[root()]}
            capture=m.Capture(contract,output=path,transport=lambda r,k:reply({'AAA':history()}),keys=KEYS,
                clock_ns=clock.read,sleeper=clock.sleep,utc_now=lambda:datetime(2026,9,16,tzinfo=timezone.utc).isoformat())
            self.assertTrue(capture.run()['protocol_complete'])
            archive=Path(td)/'original.zip'
            def pack():
                with zipfile.ZipFile(archive,'w') as z:
                    for p in path.iterdir():z.write(p,p.name)
                return {'size_in_bytes':archive.stat().st_size,'digest':'sha256:'+m.sha(archive.read_bytes())}
            metadata=pack();pin=m.sha((path/'inventory.json').read_bytes())
            result=m.verify_archive(archive,metadata,pin,contract)
            self.assertEqual(result['bar_count'],60)
            self.assertEqual(len(result['root_summaries'][0]['prior_sessions_by_symbol']['AAA']),50)
            (path/'00000.body.json').write_bytes(reply({'AAA':history(49)})['body'])
            with self.assertRaises(ValueError):m.verify_archive(archive,pack(),pin,contract)

    def test_bad_preflight_never_loads_credentials(self):
        calls=[]
        with patch.object(m,'preflight',side_effect=ValueError('gate')),self.assertRaises(ValueError):
            m.capture(None,None,None,None,None,None,None,None,output='unused',credential_loader=lambda:calls.append(1),transport=None,progress=None)
        self.assertEqual(calls,[])

    def test_registration_preserves_exact_4018_cases_and_no_runtime_authority(self):
        import yaml
        value=m.validate_registration(ROOT);raw=m.parent.validate_registration(ROOT)
        self.assertEqual(len(value['requests']),30)
        self.assertEqual([(r['trading_date'],r['params']['symbols'],r['membership_sha256']) for r in value['requests']],
            [(r['trading_date'],r['params']['symbols'],r['membership_sha256']) for r in raw['requests']])
        self.assertFalse(value['historical_scanner_enabled']);self.assertFalse(value['exact_same_time_rvol_complete'])
        w=yaml.safe_load((ROOT/m.WORKFLOW).read_text())
        self.assertEqual(set(w['jobs']),{'consume','capture','verify'})
        for j in w['jobs'].values():self.assertEqual(j['if'],'github.run_attempt == 1')

    def test_cli_validation(self):
        p=subprocess.run([sys.executable,'scripts/run_candidate_daily_history.py','validate'],cwd=ROOT,
            env={**os.environ,'PYTHONPATH':'src:scripts'},capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr);self.assertIn('"roots": 30',p.stdout)


if __name__=='__main__':unittest.main()
