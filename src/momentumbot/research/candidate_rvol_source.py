"""Pinned coarse RVOL sources and conservative exact-minute acquisition selection."""
from pathlib import Path
from fractions import Fraction
from datetime import date, datetime, time, timedelta
import math
import zipfile
import pandas as pd

from momentumbot.historical_profile_union_v01 import historical_profile_union_v0_1
from momentumbot.research import candidate_rvol_coarse as capture
from momentumbot.research import scanner_source_archive as split_source
from momentumbot.research.candidate_volume_projection import project_coarse_root, compare_completed_bucket_volumes

require,exact,seal,sha,parse = capture.require,capture.exact,capture.seal,capture.sha,capture.parse
ID = 'early-pullback-candidate-rvol-source-v0.1'
BASE = 'research/data-audits/' + ID
PROOF_PIN = {'bytes':796826,'sha256':'8ac9bae226bdfc723fad418a8e9ba7bb9483be3ea07d8bd1a2d5e5921b0200f4'}
PROOF_SEAL = '5c6e6f3e9f3c2f16ba513f186d4c6041bfa0939d754195c26a811b8e58f3b7e5'


def accepted_coarse_proof(root):
    path = Path(root) / capture.BASE / 'original-verification.zip'
    capture.old.parent.parent._pinned_file(path,PROOF_PIN)
    with zipfile.ZipFile(path) as archive: proof = parse(archive.read('hosted-verification.json'))
    capture.c.d.base.verify_seal(proof)
    require(proof['content_sha256'] == PROOF_SEAL and proof['code_commit'] == 'de5ec099fc189114900fc545167ca79da271eb29'
        and proof['run_id'] == '35164380485' and proof['hosted_capture_provenance_verified'] is True,
        'accepted hosted coarse proof differs')
    require(proof['archive_verification']['protocol_complete'] is True, 'complete coarse capture required')
    return proof


def eligible_raw_price_minutes(frame):
    profile = historical_profile_union_v0_1()
    require(frame.index.tz is not None and frame.index.is_unique and frame.index.is_monotonic_increasing,
        'unique ordered aware raw times required')
    require(all(not isinstance(x,bool) and math.isfinite(float(x)) and x > 0 for x in frame['close']),
        'finite positive raw prices required')
    times = (frame.index + pd.Timedelta(minutes=1)).tz_convert(capture.daily.ET).time
    prices = frame['close'].between(profile.min_price,profile.max_price)
    return sum(bool(price) and profile.session_start <= stamp < profile.no_new_entries_after
        for price,stamp in zip(prices,times,strict=True))


def possible_rvol_minutes(raw, minute, history, target):
    """Exact arithmetic form of the frozen completed-bucket acquisition bound.

    Target overlap differences retain the case. Accepted historical split
    aggregates supply completed-bucket volumes; no coarse value enters runtime.
    The raw price/time predicate is necessary only; gain/rank/context are ignored.
    """
    profile=historical_profile_union_v0_1()
    require(len(history)==51 and target in history and all(d<=target for d in history), 'exact history required')
    require(raw.index.equals(minute.index),'raw/split source timestamps differ')
    eligible=eligible_raw_price_minutes(raw)
    overlap=compare_completed_bucket_volumes(minute,history[target],target)
    if overlap['mismatched_buckets']:
        return {'retain_for_exact':True,'reason':'unresolved_target_volume_difference','possible_minutes':None}
    start=pd.Timestamp(datetime.combine(date.fromisoformat(target),time(4),capture.daily.ET)).tz_convert('UTC')
    buckets=[Fraction(0)]*24
    for session,frame in history.items():
        if session==target:continue
        compare_completed_bucket_volumes(frame.iloc[:0],frame,session)
        for stamp,volume in zip(frame.index,frame['volume'],strict=True):
            local=stamp.tz_convert(capture.daily.ET)
            buckets[(local.hour*60+local.minute-240)//15]+=Fraction(str(volume))
    cumulative=[Fraction(0)]
    for value in buckets:cumulative.append(cumulative[-1]+value)
    current=Fraction(0);possible=0
    for stamp,volume,price in zip(minute.index,minute['volume'],raw['close'],strict=True):
        if stamp < start:continue
        current+=Fraction(str(volume))
        decision=(stamp+pd.Timedelta(minutes=1)).tz_convert(capture.daily.ET).time()
        if not (profile.session_start<=decision<profile.no_new_entries_after and profile.min_price<=price<=profile.max_price):continue
        offset=int((stamp-start).total_seconds())//60
        denominator=cumulative[offset//15]
        if current>0 and current*50 >= Fraction(str(profile.min_relative_volume))*denominator:possible+=1
    return {'retain_for_exact':possible>0,'possible_minutes':possible,
        'reason':'possible_frozen_rvol' if possible else 'no_possible_frozen_price_time_rvol',
        'eligible_raw_price_minutes':eligible}


def exact_requests(roots, days):
    """Prepare requests only. This does not authorize or perform a new capture."""
    require(len({d['trading_date'] for d in days})==len(days), 'unique selection dates required')
    exact([d['trading_date'] for d in days],sorted({r['trading_date'] for r in roots}), 'selection date union differs')
    selected={}
    for day in days:
        target=day['trading_date'];cases=day['cases']
        expected=sorted({s for r in roots if r['trading_date']==target for s in r['params']['symbols'].split(',')})
        exact(sorted(c['symbol'] for c in cases),expected,'candidate selection union differs')
        for case in cases:
            f=case['acquisition_filter']
            require(type(f['retain_for_exact']) is bool,'explicit retention required')
            require(case['mismatched_buckets']==0 or f['retain_for_exact'], 'unresolved volume case must be retained')
        selected[target]={c['symbol'] for c in cases if c['acquisition_filter']['retain_for_exact']}
    requests=[]
    for root in roots:
        target=root['trading_date']
        if root['observation_date']==target:continue
        symbols=sorted(selected[target].intersection(root['params']['symbols'].split(',')))
        if not symbols:continue
        params={**root['params'],'symbols':','.join(symbols),'timeframe':'1Min',
            'end':(capture.daily._stamp(root['params']['end'])+timedelta(minutes=14)).isoformat()}
        requests.append(seal({**{k:v for k,v in root.items() if k!='content_sha256'},'params':params}))
    for target,symbols in selected.items():
        for symbol in symbols:
            sessions=[r['observation_date'] for r in requests if r['trading_date']==target and symbol in r['params']['symbols'].split(',')]
            require(len(sessions)==len(set(sessions))==50 and all(d<target for d in sessions),'exact fifty prior sessions required')
    return requests


class CandidateCoarseArchive:
    def __init__(self, root, capture_zip):
        self.archive = None
        try:
            self.contract = capture.validate_registration(root)
            self.proof = accepted_coarse_proof(root)
            self.result = self.proof['archive_verification']
            metadata = self.result['archive_metadata']
            self.archive = split_source.open_capture(capture_zip,
                {'bytes':metadata['size_in_bytes'],'sha256':metadata['digest'][7:]})
            inventory = self.archive.read('inventory.json')
            require(sha(inventory) == self.result['inventory_sha256'], 'coarse inventory differs')
            self.inventory = parse(inventory)['files']
            names = self.archive.namelist()
            require(len(names) == len(set(names)) == self.result['attempt_count'] * 3 + 3
                and set(self.inventory) == set(names) - {'inventory.json'}, 'coarse member population differs')
            exact(parse(self._read('contract.json')), self.contract, 'coarse source contract differs')
            self.locations = {}
            for i in range(self.result['attempt_count']):
                member = f'{i:05d}'
                request = parse(self._read(member + '.intent.json'))['request']
                self.locations.setdefault(request['root_sha256'],[]).append((member,request))
            exact(list(self.locations),[r['content_sha256'] for r in self.contract['requests']], 'coarse source root order differs')
            self.summaries = {s['root_sha256']:s for s in self.result['root_summaries']}
            exact(list(self.summaries),list(self.locations),'coarse accepted summary union differs')
        except BaseException:
            self.close()
            raise

    def _read(self, name):
        body = self.archive.read(name)
        exact({'bytes':len(body),'sha256':sha(body)},self.inventory[name],'coarse source member differs')
        return body

    def read_day(self, target):
        roots = [r for r in self.contract['requests'] if r['trading_date'] == target]
        require(roots, 'date outside coarse source panel')
        sessions, lineage = {}, []
        for root in roots:
            key = root['content_sha256']; pages = []
            for member, request in self.locations[key]:
                body = self._read(member + '.body.json'); pages.append((request,body))
                lineage.append({'member':member+'.body.json','body_sha256':sha(body),'request_sha256':request['content_sha256']})
            frames = project_coarse_root(root,pages,self.summaries[key])
            session = root['observation_date']
            for symbol, frame in frames.items():
                require(session not in sessions.setdefault(symbol,{}), 'duplicate symbol/session')
                sessions[symbol][session] = frame
        for history in sessions.values():
            require(len(history) == 51 and target in history and all(d <= target for d in history),
                '50 prior sessions and target required')
        return {'trading_date':target,'sessions_by_symbol':sessions,
            'provenance':seal({'contract_id':ID,'accepted_coarse_proof_sha256':PROOF_SEAL,'source_pages':lineage,
                'candidate_count':len(sessions),'bar_count':sum(len(f) for h in sessions.values() for f in h.values()),
                'provider_requests':0,**capture.old.parent.parent.BOUNDARY})}

    def close(self):
        if self.archive is not None:self.archive.close();self.archive = None
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

