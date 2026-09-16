"""Pinned candidate raw sources and offline raw/split consistency diagnostics."""
from pathlib import Path
import math
import zipfile

import pandas as pd

from momentumbot.research import candidate_raw_minutes as capture
from momentumbot.research import scanner_source_archive as split_source

require, exact, seal, sha, parse = capture.require, capture.exact, capture.seal, capture.sha, capture.parse
ID = 'early-pullback-candidate-source-v0.1'
BASE = 'research/data-audits/' + ID
PROOF_PIN = {'bytes':33434,'sha256':'bcb7029a432c2be403c7453d8d20f39576e0f0d34236f0fcda56aaea7a8e1dbf'}
PROOF_SEAL = 'd500ba1a19f1374add765d0c6e39e38c5c12e84f5b0aa8af900dc22265fe7baa'


def accepted_proof(root):
    path = Path(root) / capture.BASE / 'original-verification.zip'
    capture.old.parent.parent._pinned_file(path, PROOF_PIN)
    with zipfile.ZipFile(path) as z:
        proof = parse(z.read('hosted-verification.json'))
    capture.c.d.base.verify_seal(proof)
    require(proof['content_sha256'] == PROOF_SEAL
        and proof['code_commit'] == '54ba261fe9ed6f003f39812932d3812c0a6dd6d2'
        and proof['run_id'] == '35134553351' and proof['hosted_capture_provenance_verified'] is True,
        'accepted raw capture proof differs')
    return proof


def project_raw_root(root, pages, expected):
    """Pure byte projection; provider origin must be established by the caller."""
    require(root['params']['adjustment'] == 'raw' and root['params']['timeframe'] == '1Min',
        'raw candidate minute root required')
    state = capture.parent.MinutePages(root)
    rows = {s: [] for s in root['params']['symbols'].split(',')}
    for request, body in pages:
        state.accept(request, {'status':200,'complete':True,'encoding':'identity','body':body})
        for symbol, bars in (parse(body)['bars'] or {}).items():
            rows[symbol].extend((b['t'],b['o'],b['h'],b['l'],b['c'],b['v']) for b in bars)
    exact(state.result(), expected, 'accepted raw root differs')
    frames = {}
    for symbol, values in rows.items():
        f = pd.DataFrame(values,columns=['timestamp','open','high','low','close','volume'])
        f.index = pd.to_datetime(f.pop('timestamp'),utc=True)
        frames[symbol] = f
    return frames


class CandidateMinuteArchive:
    def __init__(self, root, capture_zip):
        self.archive = None
        try:
            self.contract = capture.validate_registration(root)
            self.proof = accepted_proof(root)
            self.result = self.proof['archive_verification']
            metadata = self.result['archive_metadata']
            self.archive = split_source.open_capture(capture_zip,
                {'bytes':metadata['size_in_bytes'],'sha256':metadata['digest'][7:]})
            inventory = self.archive.read('inventory.json')
            require(sha(inventory) == self.result['inventory_sha256'], 'raw inventory differs')
            self.inventory = parse(inventory)['files']
            names = self.archive.namelist()
            require(len(names) == len(set(names)) == self.result['attempt_count'] * 3 + 3
                and set(self.inventory) == set(names) - {'inventory.json'}, 'raw member population differs')
            exact(parse(self._read('contract.json')), self.contract, 'raw source contract differs')
            self.locations = {}
            for i in range(self.result['attempt_count']):
                member = f'{i:05d}'
                request = parse(self._read(member + '.intent.json'))['request']
                self.locations.setdefault(request['root_sha256'],[]).append((member,request))
            exact(list(self.locations),[r['content_sha256'] for r in self.contract['requests']], 'raw source root order differs')
            self.summaries = {s['root_sha256']:s for s in self.result['root_summaries']}
            exact(list(self.summaries),list(self.locations),'raw accepted summary union differs')
        except BaseException:
            self.close()
            raise

    def _read(self, name):
        body = self.archive.read(name)
        exact({'bytes':len(body),'sha256':sha(body)},self.inventory[name],'raw source member differs')
        return body

    def read_day(self, target):
        roots = [r for r in self.contract['requests'] if r['trading_date'] == target]
        require(roots,'date outside candidate source panel')
        frames, lineage = {}, []
        for root in roots:
            pages = []
            for member, request in self.locations[root['content_sha256']]:
                body = self._read(member + '.body.json');pages.append((request,body))
                lineage.append({'member':member+'.body.json','body_sha256':sha(body),'request_sha256':request['content_sha256']})
            values = project_raw_root(root,pages,self.summaries[root['content_sha256']])
            require(not set(frames).intersection(values),'duplicate raw dated symbol')
            frames.update(values)
        return {'trading_date':target,'candidate_raw_minute_bars_by_symbol':frames,
            'provenance':seal({'contract_id':ID,'accepted_raw_proof_sha256':PROOF_SEAL,'source_pages':lineage,
                'adjustment':'raw','timestamp_semantics':'bar start; usable at start plus one minute',
                'candidate_count':len(frames),'bar_count':sum(len(f) for f in frames.values()),
                'provider_requests':0,**capture.old.parent.parent.BOUNDARY})}

    def close(self):
        if self.archive is not None:self.archive.close();self.archive = None
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


def selected_split_closes(source, target, symbols):
    """Select from already byte-pinned full-membership archives, with no pruning of ranks."""
    require(target in source.days,'date outside split source panel')
    require(symbols == sorted(set(symbols)) and set(symbols) <= set(source.days[target]['membership_symbols']),
        'unique dated candidate subset required')
    rows = {s:[] for s in symbols};selected = set(symbols)
    covered = set()
    for root in source.roots:
        if root['trading_date'] != target:continue
        needed = selected.intersection(root['params']['symbols'].split(','))
        if not needed:continue
        require(not covered.intersection(needed),'duplicate split symbol root')
        key = root['content_sha256']
        for segment,member,request in source.locations[key]:
            require(request['root_sha256'] == key,'split root pointer differs')
            body = parse(source._read(segment,member+'.body.json'))
            for symbol in needed:
                rows[symbol].extend((b['t'],b['c']) for b in (body['bars'] or {}).get(symbol,[]))
        for symbol in needed:
            require(len(rows[symbol]) == source.summaries[key]['symbol_bar_counts'][symbol], 'selected split count differs')
        covered.update(needed)
    exact(sorted(covered),sorted(selected),'missing selected split source')
    frames = {}
    for symbol, values in rows.items():
        f = pd.DataFrame(values,columns=['timestamp','close']);f.index=pd.to_datetime(f.pop('timestamp'),utc=True)
        require(f.index.is_unique and f.index.is_monotonic_increasing,'selected split time order differs')
        frames[symbol]=f
    return frames


def compare_price_basis(raw, split, *, saved_daily_factor):
    """Source diagnostic only: full-day evidence never becomes a runtime feature."""
    require(type(saved_daily_factor) in (int,float) and math.isfinite(saved_daily_factor)
        and saved_daily_factor > 0,'positive saved daily factor required')
    for frame in (raw,split):
        require(frame.index.tz is not None and frame.index.is_unique
            and frame.index.is_monotonic_increasing,'unique ordered aware source times required')
        require(all(type(x) is not bool and math.isfinite(float(x)) and x >= 0 for x in frame['close']),
            'finite nonnegative source prices required')
    same = raw.index.equals(split.index)
    if not same:return {'status':'timestamp_mismatch','raw_bars':len(raw),'split_bars':len(split)}
    if raw.empty:return {'status':'empty_pair','raw_bars':0,'split_bars':0}
    if (raw['close'] <= 0).any() or (split['close'] <= 0).any():return {'status':'nonpositive_price','raw_bars':len(raw),'split_bars':len(split)}
    ratios = split['close'].to_numpy(dtype=float) / raw['close'].to_numpy(dtype=float)
    residuals = [abs(float(x)/saved_daily_factor-1) for x in ratios]
    return {'status':'compared','raw_bars':len(raw),'split_bars':len(split),
        'mismatched_prices_at_relative_tolerance_1e9':sum(x > 1e-9 for x in residuals),
        'maximum_relative_residual':max(residuals),
        'daily_minute_share_basis_verified':False}
