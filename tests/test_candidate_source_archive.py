from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from momentumbot.research import candidate_source_archive as m
from tests.test_scanner_minutes import day,bar,reply
from tests import test_scanner_source_archive as split_tests

ROOT=Path(__file__).resolve().parents[1]


class CandidateSourceTests(unittest.TestCase):
    def test_project_original_raw_fields_and_empty_members(self):
        root=m.capture.roots_for_day(day(),['AAA','BBB'])[0]
        p=m.capture.parent.MinutePages(root);q=p.request();body=reply({'AAA':[bar()]})
        p.accept(q,body);result=p.result()
        values=m.project_raw_root(root,[(q,body['body'])],result)
        self.assertEqual(values['AAA'].iloc[0].to_dict(),{'open':2,'high':3,'low':1,'close':2.5,'volume':100})
        self.assertTrue(values['BBB'].empty)
        self.assertEqual(str(values['AAA'].index.tz),'UTC')
        changed=deepcopy(result);changed['bar_count']+=1
        with self.assertRaises(ValueError):m.project_raw_root(root,[(q,body['body'])],changed)
        with self.assertRaises(ValueError):m.project_raw_root(root,[],result)

    def test_split_values_cannot_enter_raw_projection(self):
        root=m.capture.old.roots_for_day(day())[0]
        with self.assertRaises(ValueError):m.project_raw_root(root,[],{})

    def test_accepted_proof_and_wrong_original_capture(self):
        self.assertEqual(m.accepted_proof(ROOT)['archive_verification']['bar_count'],233576)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'fake.zip';path.write_bytes(b'fake')
            with self.assertRaises(ValueError):m.CandidateMinuteArchive(ROOT,path)

    def test_selected_split_sources_keep_original_times_and_empty(self):
        fixture=split_tests.SourceArchiveTests();source=fixture.fixture()
        self.addCleanup(fixture.doCleanups)
        frames=m.selected_split_closes(source,'2026-03-04',['A000','A001','A250'])
        self.assertEqual(len(frames),3);self.assertTrue(frames['A001'].empty)
        self.assertEqual(frames['A250'].index[0].isoformat(),'2026-03-04T15:00:00+00:00')
        with self.assertRaises(ValueError):m.selected_split_closes(source,'2026-03-04',['OTHER'])
        source.summaries[source.roots[-1]['content_sha256']]['symbol_bar_counts']['A250']=0
        with self.assertRaises(ValueError):m.selected_split_closes(source,'2026-03-04',['A250'])

    def frame(self,values):
        return pd.DataFrame({'close':values},index=pd.date_range('2026-03-04T09:00Z',periods=len(values),freq='min'))

    def test_scale_diagnostic_does_not_promote_source(self):
        raw=self.frame([2,3]);split=self.frame([20,30])
        result=m.compare_price_basis(raw,split,saved_daily_factor=10)
        self.assertEqual(result['mismatched_prices_at_relative_tolerance_1e9'],0)
        self.assertFalse(result['daily_minute_share_basis_verified'])
        result=m.compare_price_basis(raw,split,saved_daily_factor=1)
        self.assertEqual(result['mismatched_prices_at_relative_tolerance_1e9'],2)
        self.assertEqual(result['maximum_relative_residual'],9)

    def test_empty_nonpositive_missing_and_invalid_prices_stay_explicit(self):
        self.assertEqual(m.compare_price_basis(self.frame([]),self.frame([]),saved_daily_factor=1)['status'],'empty_pair')
        self.assertEqual(m.compare_price_basis(self.frame([0]),self.frame([1]),saved_daily_factor=1)['status'],'nonpositive_price')
        self.assertEqual(m.compare_price_basis(self.frame([1]),self.frame([]),saved_daily_factor=1)['status'],'timestamp_mismatch')
        for value in [float('nan'),float('inf'),-1]:
            with self.assertRaises(ValueError):m.compare_price_basis(self.frame([value]),self.frame([1]),saved_daily_factor=1)
        with self.assertRaises(ValueError):m.compare_price_basis(self.frame([1]),self.frame([1]),saved_daily_factor=0)


if __name__=='__main__':unittest.main()
