"""Offline exact-minute RVOL integration of the independently verified capture.

This is a source adapter, not a scanner or a policy promotion. Original captures
stay immutable. Only the eight registered target refreshes may replace RVOL
volume inputs; raw prices and raw execution volume never change.
"""
from datetime import date, time
from pathlib import Path
import math
import zipfile

import pandas as pd

from momentumbot.rvol import same_time_rvol
from momentumbot.scanner_rvol_alignment_v10 import align_exact_rvol_to_raw_bar_indexes_v10
from momentumbot.research import candidate_rvol_exact as capture
from momentumbot.research import scanner_source_archive as split_source
from momentumbot.research.candidate_volume_projection import compare_completed_bucket_volumes

require, exact, seal, sha, parse = capture.require, capture.exact, capture.seal, capture.sha, capture.parse
ID = 'early-pullback-candidate-rvol-exact-source-v0.1'
BASE = 'research/data-audits/' + ID
PROOF_PIN = {'bytes': 643187, 'sha256': '28abe4f51d6f30bef687fb348d549b8283e78934bfc949f9ec14be1bb5da661a'}
PROOF_SEAL = '0afe76dc958b0cf2f03ba48efcbf3a3f6b15a6a735f531558de87acc223e48f7'
CAPTURE_PIN = {'bytes': 63526941, 'sha256': '1c8f6358bdf684e796ed1006ed4d6da49af491523d9b38227a4a2565aad4fc17'}
SOURCE_COMMIT = '53989a5f1637e759a3922980b40f24cbfbaab5fb'


def accepted_proof(root):
    path = Path(root) / BASE / 'original-verification.zip'
    with split_source.open_capture(path, PROOF_PIN) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) and set(names) == split_source.PROOF_NAMES,
                'exact original verification members required')
        proof = parse(archive.read('hosted-verification.json'))
    capture.c.d.base.verify_seal(proof)
    require(proof['content_sha256'] == PROOF_SEAL and proof['code_commit'] == SOURCE_COMMIT
            and proof['run_id'] == '35408612330' and proof['contract_id'] == capture.ID
            and proof['hosted_capture_provenance_verified'] is True,
            'accepted exact hosted proof differs')
    result = proof['archive_verification']
    capture.c.d.base.verify_seal(result)
    require(result['protocol_complete'] is True and result['contract_id'] == capture.ID,
            'complete exact capture required')
    meta = result['archive_metadata']
    exact({'bytes': meta['size_in_bytes'], 'sha256': meta['digest'][7:]}, CAPTURE_PIN,
          'accepted exact capture pin differs')
    return proof


def project_exact_root(root, pages, expected):
    """Revalidate original pages before projecting their minute volumes."""
    parser = capture.ExactPages(root)
    rows = {symbol: [] for symbol in root['params']['symbols'].split(',')}
    for request, body in pages:
        parser.accept(request, {'status': 200, 'complete': True, 'encoding': 'identity', 'body': body})
        for symbol, bars in (parse(body)['bars'] or {}).items():
            rows[symbol].extend((bar['t'], bar['v']) for bar in bars)
    exact(parser.result(), expected, 'accepted exact root differs')
    frames = {}
    for symbol, values in rows.items():
        frame = pd.DataFrame(values, columns=['timestamp', 'volume'])
        frame.index = pd.to_datetime(frame.pop('timestamp'), utc=True)
        frames[symbol] = frame
    return frames


class CandidateExactArchive:
    def __init__(self, root, capture_zip):
        self.archive = None
        try:
            self.contract = capture.validate_registration(root)
            self.selection = capture.accepted_selection(root)
            self.proof = accepted_proof(root)
            self.result = self.proof['archive_verification']
            self.archive = split_source.open_capture(capture_zip, CAPTURE_PIN)
            inventory = self.archive.read('inventory.json')
            require(sha(inventory) == self.result['inventory_sha256'], 'exact inventory differs')
            value = parse(inventory)
            capture.c.d.base.verify_seal(value)
            self.inventory = value['files']
            names = self.archive.namelist()
            require(len(names) == len(set(names)) == self.result['attempt_count'] * 3 + 3
                    and set(self.inventory) == set(names) - {'inventory.json'}, 'exact member population differs')
            exact(parse(self._read('contract.json')), self.contract, 'exact source contract differs')
            self.locations = {}
            for ordinal in range(self.result['attempt_count']):
                member = f'{ordinal:05d}'
                request = parse(self._read(member + '.intent.json'))['request']
                self.locations.setdefault(request['root_sha256'], []).append((member, request))
            exact(list(self.locations), [r['content_sha256'] for r in self.contract['requests']],
                  'exact source root order differs')
            summaries = self.result['root_summaries']
            self.summaries = {s['root_sha256']: s for s in summaries}
            require(len(self.summaries) == len(summaries), 'duplicate exact root summary')
            exact(list(self.summaries), list(self.locations), 'exact summary union differs')
        except BaseException:
            self.close()
            raise

    def _read(self, name):
        body = self.archive.read(name)
        exact({'bytes': len(body), 'sha256': sha(body)}, self.inventory[name], 'exact member bytes differ')
        return body

    def read_day(self, target):
        days = [d for d in self.selection['days'] if d['trading_date'] == target]
        require(len(days) == 1, 'date outside exact source panel')
        selected = {c['symbol']: c for c in days[0]['cases'] if c['acquisition_filter']['retain_for_exact']}
        sessions, refreshes, lineage = {}, {}, []
        for root in self.contract['requests']:
            if root['trading_date'] != target:
                continue
            key = root['content_sha256']
            pages = []
            for member, request in self.locations[key]:
                body = self._read(member + '.body.json')
                pages.append((request, body))
                lineage.append({'member': member + '.body.json', 'body_sha256': sha(body),
                                'request_sha256': request['content_sha256']})
            frames = project_exact_root(root, pages, self.summaries[key])
            session = root['observation_date']
            require(session <= target, 'future session in exact source')
            for symbol, frame in frames.items():
                require(symbol in selected, 'unselected exact symbol')
                if session == target:
                    require(symbol not in refreshes, 'duplicate exact target refresh')
                    refreshes[symbol] = frame
                else:
                    require(session not in sessions.setdefault(symbol, {}), 'duplicate exact prior session')
                    sessions[symbol][session] = frame
        exact(sorted(sessions), sorted(selected), 'exact candidate union differs')
        exact(sorted(refreshes), sorted(s for s, c in selected.items() if c['mismatched_buckets']),
              'exact target refresh union differs')
        for symbol, history in sessions.items():
            exact(sorted(history), selected[symbol]['prior_sessions'], 'frozen prior sessions differ')
            require(len(history) == 50, 'fifty exact prior sessions required')
        return {'trading_date': target, 'sessions_by_symbol': sessions, 'target_refresh_by_symbol': refreshes,
                'provenance': seal({'contract_id': ID, 'accepted_exact_proof_sha256': PROOF_SEAL,
                    'source_pages': lineage, 'candidate_count': len(sessions),
                    'history_bar_count': sum(len(f) for h in sessions.values() for f in h.values()),
                    'refresh_bar_count': sum(len(f) for f in refreshes.values()),
                    'provider_requests': 0, **capture.old.parent.parent.BOUNDARY})}

    def close(self):
        if self.archive is not None:
            self.archive.close()
            self.archive = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def morning(frame, target):
    """04:00–09:59 bar starts only; the 10:00 bar lacks matching history."""
    index = frame.index
    require(isinstance(index, pd.DatetimeIndex) and index.tz is not None
            and index.is_unique and index.is_monotonic_increasing, 'unique ordered aware times required')
    local = index.tz_convert(capture.daily.ET)
    require(all(d.isoformat() == target for d in local.date), 'target date differs')
    return frame.loc[(local.time >= time(4)) & (local.time < time(10))].copy()


def integrate_case(*, target, raw, saved_split, history, coarse_history, refresh=None):
    """Return an aligned exact curve only if every source comparison agrees.

    Empty exhausted histories stay zero-volume sessions. Missing sessions are
    rejected. Numerical disagreement is recorded and withholds the whole case;
    no fitted tolerance, split multiplier or replacement value is invented.
    """
    prior = sorted(history)
    require(len(prior) == 50 and all(d < target for d in prior), 'fifty unique prior dates required')
    exact(sorted(coarse_history), sorted(prior + [target]), 'coarse/exact session union differs')
    raw = morning(raw, target)
    saved_split = morning(saved_split, target)
    current = saved_split if refresh is None else morning(refresh, target)
    # Existing volume checker also rejects nonfinite/negative/off-grid volumes.
    target_check = compare_completed_bucket_volumes(current, coarse_history[target], target)
    history_differences = []
    for session in prior:
        frame = history[session]
        # Reject out-of-window exact bars instead of silently discarding them.
        require(len(morning(frame, session)) == len(frame), 'history outside captured morning')
        comparison = compare_completed_bucket_volumes(frame, coarse_history[session], session)
        if comparison['mismatched_buckets']:
            history_differences.append({'observation_date': session, **comparison})
    same_times = raw.index.equals(saved_split.index) and raw.index.equals(current.index)
    accepted = same_times and not target_check['mismatched_buckets'] and not history_differences
    audit = {'status': 'exact_rvol_ready' if accepted else 'source_disagreement',
             'target_volume_source': 'registered_exact_refresh' if refresh is not None else 'accepted_split_minutes',
             'raw_split_refresh_timestamps_match': same_times, 'target_comparison': target_check,
             'prior_session_count': len(prior), 'prior_comparison_count': len(prior),
             'prior_session_differences': history_differences,
             'empty_prior_sessions': sum(frame.empty for frame in history.values()),
             'exact_same_time_rvol_complete': accepted, 'daily_minute_share_basis_verified': False}
    if refresh is not None:
        old = compare_completed_bucket_volumes(saved_split, coarse_history[target], target)
        audit['original_target_comparison'] = old
        audit['refresh_resolves_original_difference'] = bool(old['mismatched_buckets']) and accepted
    if not accepted:
        return None, audit
    bars = pd.concat([history[d] for d in prior] + [current])
    curve = same_time_rvol(bars, trading_date=date.fromisoformat(target),
                           session_dates=[date.fromisoformat(d) for d in prior], end_time=time(9, 59))
    aligned = align_exact_rvol_to_raw_bar_indexes_v10(
        candidate_raw_minute_bars_by_symbol={'candidate': raw},
        candidate_exact_rvol_by_symbol={'candidate': curve.values})['candidate']
    audit.update({'rvol_method': curve.method, 'rvol_observations': len(aligned),
                  'undefined_observations': int(aligned.isna().sum()),
                  'positive_infinite_observations': sum(math.isinf(v) and v > 0 for v in aligned)})
    return aligned, audit


def encode_curve(series):
    """Portable JSON values retain undefined and positive-infinite RVOL."""
    return [[stamp.isoformat(), None if math.isnan(value) else
             'positive_infinity' if value == math.inf else float(value)]
            for stamp, value in series.items()]
