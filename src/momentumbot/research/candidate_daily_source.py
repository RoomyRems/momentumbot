"""Pinned prior daily input; no claim of daily/minute share-basis agreement."""
from datetime import date
from fractions import Fraction
import math

import pandas as pd

from momentumbot.research import candidate_daily_history as capture
from momentumbot.research import candidate_rvol_coarse as coarse
from momentumbot.research.candidate_source_archive import CandidateMinuteArchive
from momentumbot.research.scanner_source_archive import open_capture

require, exact, seal, sha, parse = capture.require, capture.exact, capture.seal, capture.sha, capture.parse
ID = 'early-pullback-candidate-daily-source-v0.1'
BASE = 'research/data-audits/' + ID
CAPTURE_PIN = {'bytes': 8054137, 'sha256': '9dd8f4f8a3deea55f865ff7117f6da86c7a165f51c354648600ec23e01389fbf'}
BOUNDARY = {**capture.old.parent.parent.BOUNDARY, 'daily_minute_share_basis_verified': False,
            'runtime_normalization_authorized': False, 'provider_requests': 0}


class CandidateDailyArchive(CandidateMinuteArchive):
    """Reuse the pinned member-read and lifetime protocol; validate daily inputs."""
    def __init__(self, root, capture_zip):
        self.archive = None
        try:
            self.contract = capture.validate_registration(root)
            self.proof = coarse.accepted_daily_proof(root)
            self.result = self.proof['archive_verification']
            capture.c.d.base.verify_seal(self.result)
            require(self.result['protocol_complete'] is True and self.result['contract_id'] == capture.ID,
                    'complete original daily capture required')
            meta = self.result['archive_metadata']
            exact({'bytes': meta['size_in_bytes'], 'sha256': meta['digest'][7:]}, CAPTURE_PIN,
                  'original daily archive pin differs')
            self.archive = open_capture(capture_zip, CAPTURE_PIN)
            inventory = self.archive.read('inventory.json')
            require(sha(inventory) == self.result['inventory_sha256'], 'daily inventory differs')
            value = parse(inventory); capture.c.d.base.verify_seal(value)
            self.inventory = value['files']
            names = self.archive.namelist()
            require(len(names) == len(set(names)) == self.result['attempt_count'] * 3 + 3 and
                    set(self.inventory) == set(names) - {'inventory.json'}, 'daily member population differs')
            exact(parse(self._read('contract.json')), self.contract, 'daily contract differs')
            self.locations = {}
            for ordinal in range(self.result['attempt_count']):
                member = f'{ordinal:05d}'
                request = parse(self._read(member + '.intent.json'))['request']
                self.locations.setdefault(request['root_sha256'], []).append((member, request))
            exact(list(self.locations), [r['content_sha256'] for r in self.contract['requests']],
                  'daily root order differs')
            summaries = self.result['root_summaries']
            self.summaries = {s['root_sha256']: s for s in summaries}
            require(len(summaries) == len(self.summaries), 'duplicate daily root summary')
            exact(list(self.summaries), list(self.locations), 'daily summary union differs')
        except BaseException:
            self.close()
            raise

    def read_day(self, target):
        roots = [r for r in self.contract['requests'] if r['trading_date'] == target]
        require(roots, 'date outside daily panel')
        values, lineage = {}, []
        for root in roots:
            pages = []
            for member, request in self.locations[root['content_sha256']]:
                body = self._read(member + '.body.json'); pages.append((request, body))
                lineage.append({'member': member + '.body.json', 'body_sha256': sha(body),
                                'request_sha256': request['content_sha256']})
            projected = capture.project_history_root(root, pages, self.summaries[root['content_sha256']])
            require(not set(values).intersection(projected), 'duplicate daily candidate')
            values.update(projected)
        expected = sorted(s for r in roots for s in r['params']['symbols'].split(','))
        exact(sorted(values), expected, 'daily candidate union differs')
        return {'trading_date': target, 'history_by_symbol': values,
                'provenance': seal({'contract_id': ID, 'accepted_daily_proof_sha256': coarse.PROOF_SEAL,
                    'source_pages': lineage, 'candidate_count': len(values),
                    'bar_count': sum(len(v['daily_bars']) for v in values.values()), **BOUNDARY})}


def compare_previous_close(history, witness, target):
    """Compare the same prior session, never use the target day's daily high.

Caller supplies authenticated history and a pinned saved scanner witness.
Agreement concerns one daily close only, not minute prices, volume or ranking.
"""
    index = history.index
    require(isinstance(index, pd.DatetimeIndex) and index.tz is not None and
            index.is_unique and index.is_monotonic_increasing, 'ordered aware daily history required')
    dates = index.tz_convert(capture.daily.ET).date
    require(len(set(dates)) == len(dates) and all(d < date.fromisoformat(target) for d in dates),
            'unique prior daily sessions required')
    for value in history['close']:
        require(not isinstance(value, bool) and isinstance(value, (int, float)) and
                math.isfinite(value) and value > 0, 'positive finite daily close required')
    if witness is None:
        return {'status': 'saved_previous_close_unavailable', **BOUNDARY}
    stamp = pd.Timestamp(witness['timestamp'])
    require(stamp.tzinfo is not None, 'aware previous-close timestamp required')
    session = stamp.tz_convert(capture.daily.ET).date()
    require(session < date.fromisoformat(target), 'prior previous-close witness required')
    old = witness['close']
    require(type(old) in (int, float) and math.isfinite(old) and old > 0, 'positive finite saved close required')
    positions = [i for i, d in enumerate(dates) if d == session]
    detail = {'witness_session': session.isoformat(), 'saved_close': str(Fraction(str(old))),
              'saved_source_body_sha256': witness['source_body_sha256'], **BOUNDARY}
    if not positions:
        return {'status': 'witness_session_unavailable', **detail}
    current = Fraction(str(history.iloc[positions[0]]['close']))
    difference = current - Fraction(str(old))
    return {'status': 'previous_close_matches' if difference == 0 else 'previous_close_differs',
            'history_close': str(current), 'history_minus_saved': str(difference),
            'witness_is_latest_history_session': session == dates[-1], **detail}
