"""Pure coarse-volume projection and exact overlapping-bucket diagnostics.

Provider provenance belongs to the accepted archive reader. These helpers do
not authorize acquisition pruning or promote coarse RVOL to runtime values.
"""
from datetime import date, datetime, time
from fractions import Fraction
import math
from numbers import Real

import pandas as pd

from momentumbot.research import candidate_rvol_coarse as capture

require, exact, parse = capture.require, capture.exact, capture.parse


def project_coarse_root(root, pages, expected):
    parser = capture.CoarsePages(root)
    rows = {s: [] for s in root['params']['symbols'].split(',')}
    for request, body in pages:
        parser.accept(request, {'status':200,'complete':True,'encoding':'identity','body':body})
        for symbol, bars in (parse(body)['bars'] or {}).items():
            rows[symbol].extend((b['t'],b['v']) for b in bars)
    exact(parser.result(), expected, 'accepted coarse root differs')
    frames = {}
    for symbol, values in rows.items():
        frame = pd.DataFrame(values, columns=['timestamp','volume'])
        frame.index = pd.to_datetime(frame.pop('timestamp'), utc=True)
        frames[symbol] = frame
    return frames


def selected_split_volumes(source, target, symbols):
    """Select volume fields from an already pinned full-membership archive."""
    require(target in source.days, 'date outside split source panel')
    require(symbols == sorted(set(symbols)) and set(symbols) <= set(source.days[target]['membership_symbols']),
        'unique dated candidate subset required')
    rows = {s:[] for s in symbols}; selected = set(symbols); covered = set()
    for root in source.roots:
        if root['trading_date'] != target: continue
        needed = selected.intersection(root['params']['symbols'].split(','))
        if not needed: continue
        require(not covered.intersection(needed), 'duplicate split symbol root')
        key = root['content_sha256']
        for segment, member, request in source.locations[key]:
            require(request['root_sha256'] == key, 'split root pointer differs')
            body = parse(source._read(segment, member + '.body.json'))
            for symbol in needed:
                rows[symbol].extend((b['t'],b['v']) for b in (body['bars'] or {}).get(symbol,[]))
        for symbol in needed:
            require(len(rows[symbol]) == source.summaries[key]['symbol_bar_counts'][symbol], 'selected split count differs')
        covered.update(needed)
    exact(sorted(covered), symbols, 'missing selected split source')
    frames = {}
    for symbol, values in rows.items():
        frame = pd.DataFrame(values, columns=['timestamp','volume'])
        frame.index = pd.to_datetime(frame.pop('timestamp'), utc=True)
        require(frame.index.is_unique and frame.index.is_monotonic_increasing, 'selected split time order differs')
        frames[symbol] = frame
    return frames


def compare_completed_bucket_volumes(minute, coarse, target):
    """Compare 04:00–10:00 ET sums exactly, with no fitted volume tolerance.

    Missing bars count as zero only after callers establish exhausted source
    pages. A match concerns this target morning, not unobserved prior sessions.
    """
    day = date.fromisoformat(target)
    start = pd.Timestamp(datetime.combine(day,time(4),capture.daily.ET)).tz_convert('UTC')
    end = pd.Timestamp(datetime.combine(day,time(10),capture.daily.ET)).tz_convert('UTC')
    totals = []
    for frame, step in ((minute,1),(coarse,15)):
        require(frame.index.tz is not None and frame.index.is_unique and frame.index.is_monotonic_increasing,
            'unique ordered aware volume times required')
        buckets = [Fraction(0)] * 24
        for stamp, volume in zip(frame.index,frame['volume'],strict=True):
            require(stamp.tz_convert(capture.daily.ET).date() == day, 'volume session differs')
            require(stamp.second == stamp.microsecond == stamp.nanosecond == 0 and stamp.minute % step == 0,
                'volume grid differs')
            require(isinstance(volume,Real) and not isinstance(volume,bool) and math.isfinite(float(volume)) and volume >= 0,
                'finite nonnegative volume required')
            if step == 15: require(start <= stamp < end, 'coarse volume outside captured window')
            if start <= stamp < end:
                buckets[int((stamp-start).total_seconds())//900] += Fraction(str(volume))
        totals.append(buckets)
    differences = []
    for i,(one,fifteen) in enumerate(zip(*totals,strict=True)):
        if one != fifteen:
            delta = fifteen-one
            differences.append({'bucket_start':(start+pd.Timedelta(minutes=i*15)).isoformat(),
                'minute_sum':str(one),'coarse_volume':str(fifteen),'coarse_minus_minute':str(delta)})
    return {'status':'target_buckets_differ' if differences else 'target_buckets_match',
        'compared_buckets':24, 'both_sources_empty':minute.empty and coarse.empty,
        'mismatched_buckets':len(differences),'differences':differences,
        'prior_session_volume_basis_verified':False,'acquisition_pruning_authorized':False,
        'exact_same_time_rvol_complete':False}
