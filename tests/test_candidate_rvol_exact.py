from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile
import unittest
import zipfile

from momentumbot.research import candidate_rvol_exact as m
from tests.test_candidate_rvol_coarse import plan
from tests.test_scanner_minutes import bar,reply,Clock,KEYS

ROOT=Path(__file__).resolve().parents[1]


def root():
    days=[{'trading_date':'2026-03-09','cases':[{'symbol':'AAA','mismatched_buckets':0,
        'acquisition_filter':{'retain_for_exact':True}}]}]
    return m.source.exact_requests(plan()['requests'],days)[0]


class ExactRvolTests(unittest.TestCase):
    def test_exact_parser_allows_minute_grid_and_rejects_wrong_session(self):
        r=root();p=m.ExactPages(r)
        stamp=(m.daily._stamp(r['params']['start'])+timedelta(minutes=1)).isoformat()
        p.accept(p.request(),reply({'AAA':[bar(stamp)]}));self.assertEqual(p.result()['bar_count'],1)
        p=m.ExactPages(r)
        with self.assertRaises(ValueError):p.accept(p.request(),reply({'AAA':[bar('2026-03-09T08:00Z')]}))
        with self.assertRaises(ValueError):p.result()
        r['params']['timeframe']='15Min'
        with self.assertRaises(ValueError):m.ExactPages(r)

    def test_exact_capture_original_archive_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            output=Path(td)/'capture';clock=Clock();r=root();contract={'requests':[r]}
            cap=m.Capture(contract,output=output,transport=lambda r,k:reply({'AAA':[bar(r['params']['start'])]}),keys=KEYS,
                clock_ns=clock.read,sleeper=clock.sleep,utc_now=lambda:datetime(2026,9,17,tzinfo=timezone.utc).isoformat())
            self.assertTrue(cap.run()['protocol_complete']);archive=Path(td)/'source.zip'
            with zipfile.ZipFile(archive,'w') as z:
                for p in output.iterdir():z.write(p,p.name)
            meta={'size_in_bytes':archive.stat().st_size,'digest':'sha256:'+m.sha(archive.read_bytes())}
            proof=m.verify_archive(archive,meta,m.sha((output/'inventory.json').read_bytes()),contract)
            self.assertEqual(proof['bar_count'],1);self.assertFalse(proof['historical_scanner_enabled'])

    def test_accepted_plan_registration_and_preflight_size(self):
        v=m.validate_registration(ROOT);audit=m.accepted_selection(ROOT)
        self.assertEqual(v['requests'][:v['prior_history_roots']],audit['prepared_exact_requests'])
        self.assertEqual(v['unresolved_target_recheck_roots'],8)
        self.assertLessEqual(len(v['requests']),1508)
        self.assertGreater(len(v['requests']),0)
        self.assertTrue(all(r['observation_date']<r['trading_date'] for r in v['requests'][:v['prior_history_roots']]))
        self.assertTrue(all(r['observation_date']==r['trading_date'] for r in v['requests'][v['prior_history_roots']:]))
        self.assertLess(len(m.render(v))*2+100000,m.gate.d.previous.PREFLIGHT_LIMIT)
        self.assertFalse(v['exact_same_time_rvol_complete'])

    def test_changed_integration_archive_cannot_authorize_capture(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/m.AUDIT_PATH;p.parent.mkdir(parents=True)
            p.write_bytes(b'forged integration')
            with self.assertRaises(ValueError):m.accepted_selection(td)

    def test_target_refresh_only_covers_unresolved_cases(self):
        roots=plan()['requests']
        days=[{'trading_date':'2026-03-09','cases':[{'symbol':'AAA','mismatched_buckets':1}]}]
        rechecks=m.target_rechecks(roots,days)
        self.assertEqual(len(rechecks),1);self.assertEqual(rechecks[0]['observation_date'],'2026-03-09')
        days[0]['cases'][0]['mismatched_buckets']=0
        self.assertEqual(m.target_rechecks(roots,days),[])


if __name__=='__main__':unittest.main()
