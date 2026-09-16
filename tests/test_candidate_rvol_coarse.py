from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

from momentumbot.research import candidate_rvol_coarse as m
from tests.test_candidate_daily_history import root,history
from tests.test_scanner_minutes import bar,reply,Clock,KEYS

ROOT=Path(__file__).resolve().parents[1]


def plan():
    sessions=[m.daily._stamp(r['t']).astimezone(m.daily.ET).date().isoformat() for r in history(50)]
    return m.plan_day(root(),{'prior_sessions_by_symbol':{'AAA':sessions,'BBB':sessions[:-1]}},
        {'symbol_bar_counts':{'AAA':5,'BBB':3}})


class CoarseRvolTests(unittest.TestCase):
    def test_exact_sessions_and_target_basis_batch(self):
        p=plan();self.assertEqual(len(p['requests']),51)
        self.assertEqual(p['excluded'],[{'symbol':'BBB','reasons':['insufficient_prior_sessions']}])
        for r in p['requests']:
            self.assertEqual(r['params']['symbols'],'AAA')
            self.assertEqual(r['params']['timeframe'],'15Min')
            self.assertEqual(r['params']['asof'],'2026-03-09')
            self.assertEqual(m.daily._stamp(r['params']['end']).astimezone(m.daily.ET).time().isoformat(),'09:45:00')
        self.assertEqual(p['requests'][-1]['observation_date'],'2026-03-09')

    def test_missing_duplicate_future_sessions_and_bad_counts_fail(self):
        dates=['2026-03-06']
        for sessions in [dates*2,['2026-03-09'],['not-a-date']]:
            with self.assertRaises(ValueError):m.plan_day(root(),{'prior_sessions_by_symbol':{'AAA':sessions,'BBB':[]}}, {'symbol_bar_counts':{'AAA':1,'BBB':0}})
        with self.assertRaises(ValueError):m.plan_day(root(),{'prior_sessions_by_symbol':{'AAA':[]}}, {'symbol_bar_counts':{'AAA':1,'BBB':0}})
        with self.assertRaises(ValueError):m.plan_day(root(),{'prior_sessions_by_symbol':{'AAA':[],'BBB':[]}}, {'symbol_bar_counts':{'AAA':True,'BBB':0}})

    def test_empty_raw_is_explicit_without_fetch(self):
        sessions=[m.daily._stamp(r['t']).astimezone(m.daily.ET).date().isoformat() for r in history(50)]
        p=m.plan_day(root(),{'prior_sessions_by_symbol':dict.fromkeys(['AAA','BBB'],sessions)}, {'symbol_bar_counts':{'AAA':0,'BBB':0}})
        self.assertEqual(p['requests'],[]);self.assertEqual(len(p['excluded']),2)

    def test_coarse_grid_and_window_are_enforced(self):
        r=plan()['requests'][-1]
        for stamp in ['2026-03-09T08:01:00Z','2026-03-09T14:00:00Z','2026-03-08T08:00:00Z']:
            p=m.CoarsePages(r)
            with self.assertRaises(ValueError):p.accept(p.request(),reply({'AAA':[bar(stamp)]}))
            with self.assertRaises(ValueError):p.result()
        p=m.CoarsePages(r);p.accept(p.request(),reply({'AAA':[bar('2026-03-09T13:45:00Z')]}))
        self.assertEqual(p.result()['bar_count'],1)

    def test_capture_original_archive_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            output=Path(td)/'capture';clock=Clock();contract={'requests':[plan()['requests'][-1]]}
            cap=m.Capture(contract,output=output,transport=lambda r,k:reply({'AAA':[bar('2026-03-09T08:00:00Z')]}),keys=KEYS,
                clock_ns=clock.read,sleeper=clock.sleep,utc_now=lambda:datetime(2026,9,16,tzinfo=timezone.utc).isoformat())
            self.assertTrue(cap.run()['protocol_complete']);archive=Path(td)/'source.zip'
            with zipfile.ZipFile(archive,'w') as z:
                for p in output.iterdir():z.write(p,p.name)
            meta={'size_in_bytes':archive.stat().st_size,'digest':'sha256:'+m.sha(archive.read_bytes())}
            proof=m.verify_archive(archive,meta,m.sha((output/'inventory.json').read_bytes()),contract)
            self.assertEqual(proof['bar_count'],1);self.assertFalse(proof['historical_scanner_enabled'])

    def test_fixed_plan_original_proofs_and_preflight_size(self):
        import yaml
        v=m.validate_registration(ROOT)
        self.assertEqual(len(v['requests']),1530)
        self.assertEqual(sum(len(r['params']['symbols'].split(',')) for r in v['requests']),192678)
        self.assertEqual(sum(len(d['excluded']) for d in v['excluded_cases']),240)
        self.assertLess(len(m.render(v))*2+100000,m.gate.d.previous.PREFLIGHT_LIMIT)
        self.assertFalse(v['exact_same_time_rvol_complete']);self.assertFalse(v['historical_scanner_enabled'])
        w=yaml.safe_load((ROOT/m.WORKFLOW).read_text());self.assertEqual(set(w['jobs']),{'consume','capture','verify'})
        for j in w['jobs'].values():self.assertEqual(j['if'],'github.run_attempt == 1')

    def test_cli_uses_hosted_import_path(self):
        p=subprocess.run([sys.executable,'scripts/run_candidate_rvol_coarse.py','validate'],cwd=ROOT,
            env={**os.environ,'PYTHONPATH':'src:scripts'},capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr);self.assertIn('"roots": 1530',p.stdout)


if __name__=='__main__':unittest.main()
