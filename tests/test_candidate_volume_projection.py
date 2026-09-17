from copy import deepcopy
import unittest
import pandas as pd

from momentumbot.research import candidate_volume_projection as m
from tests.test_candidate_rvol_coarse import plan
from tests.test_scanner_minutes import bar, reply
from tests import test_scanner_source_archive as split_tests


class CandidateVolumeProjectionTests(unittest.TestCase):
    def frame(self, times, volumes):
        return pd.DataFrame({'volume':volumes},index=pd.to_datetime(times,utc=True))

    def test_projection_preserves_original_volume_and_exhaustion(self):
        root=plan()['requests'][-1];parser=m.capture.CoarsePages(root)
        request=parser.request();body=reply({'AAA':[bar('2026-03-09T08:00:00Z')]})
        parser.accept(request,body);expected=parser.result()
        frames=m.project_coarse_root(root,[(request,body['body'])],expected)
        self.assertEqual(frames['AAA'].iloc[0]['volume'],100)
        with self.assertRaises(ValueError):m.project_coarse_root(root,[],expected)
        changed=deepcopy(expected);changed['bar_count']+=1
        with self.assertRaises(ValueError):m.project_coarse_root(root,[(request,body['body'])],changed)
        parser=m.capture.CoarsePages(root);request=parser.request();body=reply({})
        parser.accept(request,body)
        self.assertTrue(m.project_coarse_root(root,[(request,body['body'])],parser.result())['AAA'].empty)

    def test_selected_volume_is_read_from_original_member(self):
        fixture=split_tests.SourceArchiveTests();source=fixture.fixture();self.addCleanup(fixture.doCleanups)
        frames=m.selected_split_volumes(source,'2026-03-04',['A000','A001','A250'])
        self.assertEqual(frames['A250'].iloc[0]['volume'],100);self.assertTrue(frames['A001'].empty)
        source.summaries[source.roots[-1]['content_sha256']]['symbol_bar_counts']['A250']=0
        with self.assertRaises(ValueError):m.selected_split_volumes(source,'2026-03-04',['A250'])

    def test_exact_decimal_sums_and_completed_window(self):
        minute=self.frame(['2026-03-09T08:00Z','2026-03-09T08:14Z','2026-03-09T14:00Z'],[0.1,0.2,1000])
        coarse=self.frame(['2026-03-09T08:00Z'],[0.3])
        result=m.compare_completed_bucket_volumes(minute,coarse,'2026-03-09')
        self.assertEqual(result['status'],'target_buckets_match')
        self.assertFalse(result['acquisition_pruning_authorized'])
        self.assertFalse(result['prior_session_volume_basis_verified'])
        coarse.iloc[0,0]=0.301
        result=m.compare_completed_bucket_volumes(minute,coarse,'2026-03-09')
        self.assertEqual(result['mismatched_buckets'],1)
        self.assertEqual(result['differences'][0]['coarse_minus_minute'],'1/1000')

    def test_empty_sources_are_explicit(self):
        empty=self.frame([],[])
        result=m.compare_completed_bucket_volumes(empty,empty,'2026-03-09')
        self.assertTrue(result['both_sources_empty'])
        one=self.frame(['2026-03-09T08:00Z'],[1])
        self.assertEqual(m.compare_completed_bucket_volumes(empty,one,'2026-03-09')['mismatched_buckets'],1)

    def test_bad_grid_session_duplicate_and_volume_rejected(self):
        empty=self.frame([],[])
        for stamp in ['2026-03-09T08:01Z','2026-03-09T14:00Z','2026-03-08T08:00Z','2026-03-09T08:00:00.000000001Z']:
            with self.subTest(stamp=stamp),self.assertRaises(ValueError):m.compare_completed_bucket_volumes(empty,self.frame([stamp],[1]),'2026-03-09')
        for value in [-1,True,float('nan'),float('inf')]:
            with self.subTest(value=value),self.assertRaises(ValueError):m.compare_completed_bucket_volumes(empty,self.frame(['2026-03-09T08:00Z'],[value]),'2026-03-09')
        with self.assertRaises(ValueError):m.compare_completed_bucket_volumes(empty,self.frame(['2026-03-09T08:00Z']*2,[1,1]),'2026-03-09')


if __name__=='__main__':unittest.main()
