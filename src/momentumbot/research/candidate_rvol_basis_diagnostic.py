"""Offline evidence about withheld RVOL sources; never a basis correction.

OHLC rollups are descriptive comparisons, not an assertion that vendor bars at
different timeframes must be identical. Matching requests (including ``asof``)
do not establish a shared adjustment vintage. No ratios are fitted or applied.
"""
from collections import Counter
from datetime import date, datetime, time
from fractions import Fraction
import gzip
import math
from pathlib import Path

import pandas as pd

from momentumbot.research import candidate_rvol_exact_source as parent
from momentumbot.research.candidate_volume_projection import compare_completed_bucket_volumes

require, exact, seal, sha, parse = parent.require, parent.exact, parent.seal, parent.sha, parent.parse
ID = 'early-pullback-candidate-rvol-basis-diagnostic-v0.1'
BASE = 'research/data-audits/' + ID
PARENT_SEAL = '0a65a01ff43fa5e7c8b72d02bc6f960dc99dd1daae1e92bf17c7430e71bff2a0'
FIELDS = ('o', 'h', 'l', 'c', 'v', 'n')
BOUNDARY = {**parent.capture.old.parent.parent.BOUNDARY,
            'daily_minute_share_basis_verified': False,
            'correction_authorized': False, 'provider_requests': 0}


def withheld_cases(root):
    """Select only sealed parent failures, without ticker/outcome predicates."""
    base = Path(root) / parent.BASE / 'integration'
    report = parse((base / 'integration-report.json').read_bytes())
    parent.capture.c.d.base.verify_seal(report)
    exact(report['content_sha256'], PARENT_SEAL, 'accepted integration report differs')
    cases = []
    for day in report['days']:
        exact(day['file'], day['trading_date'] + '.json.gz', 'integration path differs')
        body = (base / day['file']).read_bytes()
        exact({'bytes': len(body), 'sha256': sha(body)},
              {k: day[k] for k in ('bytes', 'sha256')}, 'integration day bytes differ')
        value = parse(gzip.decompress(body))
        parent.capture.c.d.base.verify_seal(value)
        exact(value['content_sha256'], day['content_sha256'], 'integration day seal differs')
        exact(value['trading_date'], day['trading_date'], 'integration date differs')
        for case in value['cases']:
            if case['status'] == 'exact_rvol_ready':
                continue
            require(case['status'] == 'source_disagreement' and
                    case['symbol'] not in value['candidate_exact_rvol_by_symbol'],
                    'explicit withheld case required')
            cases.append({'trading_date': day['trading_date'], 'parent_day_sha256': day['content_sha256'],
                          **case})
    exact(len(cases), report['counts']['source_disagreement'], 'withheld population differs')
    return cases


def read_symbol_history(source, target, symbol):
    """Revalidate all pages of each selected root from an already pinned reader."""
    sessions = {}
    for root in source.contract['requests']:
        if (root['trading_date'] != target or root['observation_date'] >= target or
                symbol not in root['params']['symbols'].split(',')):
            continue
        session, key = root['observation_date'], root['content_sha256']
        require(session not in sessions, 'duplicate selected history root')
        timeframe = root['params']['timeframe']
        require(timeframe in ('1Min', '15Min'), 'unsupported history timeframe')
        parser = (parent.capture.ExactPages(root) if timeframe == '1Min'
                  else parent.capture.parent.CoarsePages(root))
        rows, lineage = [], []
        for member, request in source.locations[key]:
            body = source._read(member + '.body.json')
            intent = parse(source._read(member + '.intent.json'))
            receipt = parse(source._read(member + '.receipt.json'))
            exact(intent['request'], request, 'history intent differs')
            exact(receipt['body_sha256'], sha(body), 'history receipt body differs')
            parser.accept(request, {'status': 200, 'complete': True, 'encoding': 'identity', 'body': body})
            rows.extend((parse(body)['bars'] or {}).get(symbol, []))
            lineage.append({'member': member, 'request_sha256': request['content_sha256'],
                            'body_sha256': sha(body), 'started_at': intent['started_at'],
                            'finished_at': receipt['finished_at']})
        exact(parser.result(), source.summaries[key], 'history root summary differs')
        sessions[session] = {'rows': rows, 'root': root, 'pages': lineage}
    require(len(sessions) == 50, 'fifty selected prior sessions required')
    return sessions


def compatible_requests(one, fifteen, symbol):
    """Check lineage and aligned windows, not the provider's adjustment vintage."""
    for key in ('provider', 'method', 'url', 'trading_date', 'observation_date', 'membership_sha256'):
        exact(one[key], fifteen[key], 'history request identity differs: ' + key)
    a, b = one['params'], fifteen['params']
    require(symbol in a['symbols'].split(',') and symbol in b['symbols'].split(','),
            'requested history symbol absent')
    exact(a['timeframe'], '1Min', 'exact timeframe differs')
    exact(b['timeframe'], '15Min', 'coarse timeframe differs')
    ignored = {'timeframe', 'symbols', 'end'}
    exact({k: v for k, v in a.items() if k not in ignored},
          {k: v for k, v in b.items() if k not in ignored}, 'history request params differ')
    require(a['feed'] == 'sip' and a['adjustment'] == 'split' and a['asof'] == one['trading_date'],
            'registered split SIP identity required')
    require(one['observation_date'] < one['trading_date'], 'prior observation required')
    start = pd.Timestamp(datetime.combine(date.fromisoformat(one['observation_date']),
                                         time(4), parent.capture.daily.ET)).tz_convert('UTC')
    require(pd.Timestamp(a['start']) == start, 'history start differs')
    require(pd.Timestamp(a['end']) == start + pd.Timedelta(minutes=359), 'exact history end differs')
    require(pd.Timestamp(b['end']) == start + pd.Timedelta(minutes=345), 'coarse history end differs')
    return {'compatible_requests': True, 'adjustment_vintage_verified': False,
            'asof_establishes_adjustment_cutoff': False}


def _buckets(rows, session, step):
    start = pd.Timestamp(datetime.combine(date.fromisoformat(session), time(4),
                                         parent.capture.daily.ET)).tz_convert('UTC')
    buckets, previous = {}, None
    for row in rows:
        stamp = pd.Timestamp(row['t'])
        require(stamp.tzinfo is not None and (previous is None or stamp > previous),
                'unique ordered aware history times required')
        require(start <= stamp < start + pd.Timedelta(hours=6) and
                stamp.second == stamp.microsecond == stamp.nanosecond == 0 and
                stamp.minute % step == 0, 'history time window/grid differs')
        previous = stamp
        values = {}
        for key in FIELDS:
            value = row[key]
            require(type(value) in (int, float) and math.isfinite(value) and
                    (value >= 0 if key in ('v', 'n') else value > 0),
                    'finite valid history value required')
            require(key != 'n' or type(value) is int, 'integer trade count required')
            values[key] = Fraction(str(value))
        require(values['l'] <= min(values['o'], values['c']) <=
                max(values['o'], values['c']) <= values['h'], 'invalid history OHLC')
        bucket = int((stamp - start).total_seconds()) // 900
        if bucket not in buckets:
            buckets[bucket] = values
        else:
            old = buckets[bucket]
            old.update({'h': max(old['h'], values['h']), 'l': min(old['l'], values['l']),
                        'c': values['c'], 'v': old['v'] + values['v'], 'n': old['n'] + values['n']})
    return start, buckets


def compare_history_buckets(minute, coarse, session):
    """Exact descriptive OHLC/V/N rollup, without a fitted scale or tolerance."""
    start, a = _buckets(minute, session, 1)
    _, b = _buckets(coarse, session, 15)
    differences, counts = [], Counter()
    for bucket in range(24):
        one, fifteen = a.get(bucket), b.get(bucket)
        missing = (one is None) != (fifteen is None)
        fields = [key for key in FIELDS if
                  (one or {}).get(key, Fraction(0) if key in ('v', 'n') else None) !=
                  (fifteen or {}).get(key, Fraction(0) if key in ('v', 'n') else None)]
        counts.update(fields)
        if missing or fields:
            differences.append({'bucket_start': (start + pd.Timedelta(minutes=15 * bucket)).isoformat(),
                'presence_differs': missing, 'differing_fields': fields,
                'minute_rollup': None if one is None else {k: str(v) for k, v in one.items()},
                'coarse_bar': None if fifteen is None else {k: str(v) for k, v in fifteen.items()}})
    return {'compared_buckets': 24, 'minute_bars': len(minute), 'coarse_bars': len(coarse),
            'both_sources_empty': not minute and not coarse,
            'volume_differing_buckets': counts['v'], 'trade_count_differing_buckets': counts['n'],
            'price_differing_buckets': sum(any(k in d['differing_fields'] for k in ('o', 'h', 'l', 'c'))
                                           for d in differences),
            'presence_differing_buckets': sum(d['presence_differs'] for d in differences),
            'differing_field_counts': dict(sorted(counts.items())), 'differences': differences,
            'basis_correction_proven': False}


def _volumes(rows):
    return pd.DataFrame({'volume': [r['v'] for r in rows]},
                        index=pd.to_datetime([r['t'] for r in rows], utc=True))


def diagnose_case(case, minute, coarse):
    """Reproduce the parent diagnostic before attaching richer evidence."""
    target, symbol = case['trading_date'], case['symbol']
    require(len(minute) == 50 and all(d < target for d in minute), 'fifty prior sessions required')
    exact(sorted(minute), sorted(coarse), 'history session union differs')
    sessions, volume_differences = [], []
    for session in sorted(minute):
        a, b = minute[session], coarse[session]
        for source in (a, b):
            exact(source['root']['observation_date'], session, 'root observation differs')
            exact(source['root']['trading_date'], target, 'root target differs')
        compatibility = compatible_requests(a['root'], b['root'], symbol)
        detail = compare_history_buckets(a['rows'], b['rows'], session)
        comparison = compare_completed_bucket_volumes(_volumes(a['rows']), _volumes(b['rows']), session)
        exact(detail['volume_differing_buckets'], comparison['mismatched_buckets'], 'volume rollup differs')
        if comparison['mismatched_buckets']:
            volume_differences.append({'observation_date': session, **comparison})
        sessions.append({'observation_date': session, **compatibility, **detail,
            'exact_source': {k: a[k] for k in ('root', 'pages')},
            'coarse_source': {k: b[k] for k in ('root', 'pages')}})
    exact(volume_differences, case['prior_session_differences'], 'parent volume disagreements differ')
    return {'trading_date': target, 'symbol': symbol, 'parent_day_sha256': case['parent_day_sha256'],
            'status': 'withheld_unresolved_basis', 'prior_session_count': len(sessions),
            'volume_differing_sessions': len(volume_differences),
            'price_differing_sessions': sum(s['price_differing_buckets'] > 0 for s in sessions),
            'volume_differing_buckets': sum(s['volume_differing_buckets'] for s in sessions),
            'price_differing_buckets': sum(s['price_differing_buckets'] for s in sessions),
            'trade_count_differing_buckets': sum(s['trade_count_differing_buckets'] for s in sessions),
            'presence_differing_buckets': sum(s['presence_differing_buckets'] for s in sessions),
            'parent_target_comparison': case['target_comparison'], 'sessions': sessions,
            'provider_root_cause_proven': False, 'basis_correction_proven': False,
            'exact_same_time_rvol_complete': False, **BOUNDARY}
