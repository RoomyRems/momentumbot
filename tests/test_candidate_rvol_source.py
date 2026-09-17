from pathlib import Path
import io
import unittest
import zipfile
import pandas as pd

from momentumbot.research import candidate_rvol_source as m
from tests.test_candidate_rvol_coarse import plan
from tests.test_scanner_minutes import bar,reply


class CoarseSourceTests(unittest.TestCase):
    def fixture(self):
        source=m.CandidateCoarseArchive.__new__(m.CandidateCoarseArchive)
        source.contract={'requests':plan()['requests']};source.locations={};source.summaries={};source.inventory={}
        blob=io.BytesIO()
        with zipfile.ZipFile(blob,'w') as z:
            for i,root in enumerate(source.contract['requests']):
                parser=m.capture.CoarsePages(root);request=parser.request()
                response=reply({'AAA':[bar(root['params']['start'])]}) if i==0 else reply({})
                parser.accept(request,response);key=root['content_sha256'];member=f'{i:05d}'
                source.locations[key]=[(member,request)];source.summaries[key]=parser.result()
                name=member+'.body.json';body=response['body'];z.writestr(name,body)
                source.inventory[name]={'bytes':len(body),'sha256':m.sha(body)}
        source.archive=zipfile.ZipFile(io.BytesIO(blob.getvalue()));self.addCleanup(source.close)
        return source

    def test_complete_history_preserves_empty_sessions_and_volume(self):
        result=self.fixture().read_day('2026-03-09');history=result['sessions_by_symbol']['AAA']
        self.assertEqual(len(history),51);self.assertEqual(sum(len(f) for f in history.values()),1)
        self.assertEqual(history[min(history)].iloc[0]['volume'],100)
        self.assertTrue(history['2026-03-09'].empty);self.assertFalse(result['provenance']['historical_scanner_enabled'])

    def test_missing_session_or_tampered_member_is_rejected(self):
        source=self.fixture();source.contract['requests'].pop()
        with self.assertRaises(ValueError):source.read_day('2026-03-09')
        source=self.fixture();source.inventory['00000.body.json']['sha256']='0'*64
        with self.assertRaises(ValueError):source.read_day('2026-03-09')
        with self.assertRaises(ValueError):source.read_day('2026-04-01')

    def test_raw_price_and_availability_window_match_scanner(self):
        f=pd.DataFrame({'close':[1.5,1.5,20,20,1.4999,20.0001]},index=pd.to_datetime([
            '2026-03-09T10:58Z','2026-03-09T10:59Z','2026-03-09T13:58Z',
            '2026-03-09T13:59Z','2026-03-09T14:00Z','2026-03-09T14:01Z'],utc=True))
        self.assertEqual(m.eligible_raw_price_minutes(f),2)
        from momentumbot.historical_data_v03 import _scan_values
        from momentumbot.historical_profile_union_v01 import historical_profile_union_v0_1
        mask=_scan_values(f,previous_close=1,rvol_curve=pd.Series(10,index=f.index),profile=historical_profile_union_v0_1())[-1]
        self.assertEqual(int(mask.sum()),2)
        f.iloc[0,0]=float('nan')
        with self.assertRaises(ValueError):m.eligible_raw_price_minutes(f)

    def upper_fixture(self,volume=50):
        target='2026-03-09'
        raw=pd.DataFrame({'close':[2]},index=pd.to_datetime(['2026-03-09T11:00Z'],utc=True))
        minute=pd.DataFrame({'volume':[volume]},index=raw.index)
        history={}
        for day in pd.bdate_range(end='2026-03-06',periods=50):
            stamp=pd.Timestamp(day.date()).tz_localize(m.capture.daily.ET)+pd.Timedelta(hours=4)
            history[day.date().isoformat()]=pd.DataFrame({'volume':[10]},index=pd.DatetimeIndex([stamp.tz_convert('UTC')]))
        history[target]=minute.copy()
        return raw,minute,history,target

    def test_exact_five_x_boundary_and_zero_denominator(self):
        args=self.upper_fixture();self.assertTrue(m.possible_rvol_minutes(*args)['retain_for_exact'])
        args=self.upper_fixture(49);self.assertFalse(m.possible_rvol_minutes(*args)['retain_for_exact'])
        for session,frame in args[2].items():
            if session!=args[3]:frame['volume']=0
        self.assertTrue(m.possible_rvol_minutes(*args)['retain_for_exact'])
        args[1]['volume']=0;args[2][args[3]]['volume']=0
        self.assertFalse(m.possible_rvol_minutes(*args)['retain_for_exact'])

    def test_unresolved_overlap_retained_and_incomplete_history_rejected(self):
        args=self.upper_fixture(1);args[2][args[3]]['volume']=100
        self.assertEqual(m.possible_rvol_minutes(*args)['reason'],'unresolved_target_volume_difference')
        args[2].pop(min(args[2]))
        with self.assertRaises(ValueError):m.possible_rvol_minutes(*args)

    def test_current_historical_bucket_does_not_cause_false_negative(self):
        args=self.upper_fixture(1)
        for session,frame in args[2].items():
            if session!=args[3]:
                frame.index=frame.index+pd.Timedelta(hours=3);frame['volume']=1000000
        self.assertTrue(m.possible_rvol_minutes(*args)['retain_for_exact'])

    def test_request_plan_covers_fifty_sessions_and_retains_uncertainty(self):
        roots=plan()['requests']
        days=[{'trading_date':'2026-03-09','cases':[{'symbol':'AAA','mismatched_buckets':1,'acquisition_filter':{'retain_for_exact':True}}]}]
        requests=m.exact_requests(roots,days)
        self.assertEqual(len(requests),50)
        self.assertTrue(all(r['observation_date']<'2026-03-09' and r['params']['timeframe']=='1Min' for r in requests))
        self.assertTrue(all(m.capture.daily._stamp(r['params']['end']).astimezone(m.capture.daily.ET).time().isoformat()=='09:59:00' for r in requests))
        days[0]['cases'][0]['acquisition_filter']['retain_for_exact']=False
        with self.assertRaises(ValueError):m.exact_requests(roots,days)
        days[0]['cases'][0]['mismatched_buckets']=0
        self.assertEqual(m.exact_requests(roots,days),[])


if __name__=='__main__':unittest.main()
