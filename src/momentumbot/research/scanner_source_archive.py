"""Read the two accepted scanner-minute segments without provider access.

This is a partial scanner source: raw candidate bars, exact RVOL, float, news
and daily/minute adjustment-basis agreement remain separate requirements.
"""
from copy import deepcopy
import hashlib
import io
from pathlib import Path
import zipfile

import pandas as pd

from momentumbot.research import scanner_minute_continuation as capture

require, exact, parse, sha, seal = capture.require, capture.exact, capture.parse, capture.sha, capture.seal
ID = 'early-pullback-scanner-source-v0.1'
BASE = 'research/data-audits/' + ID
PARENT = 'cefb30e3d006e41634f510236c08dafe4a46f170'
PROOF_PIN = {'bytes': 835236, 'sha256': '2ab06cfed437c485d988eeab86158b94c030fbd5de84ac76c40fad024c5b8c04'}
PROOF_SEAL = 'a8db408cd6cb178e80211e0dabe0015c4fd68043e9348680f87b7d4e6a348649'
PROOF_NAMES = {'hosted-verification.json', 'source-capture-artifact.json', 'source-current-ref.json',
               'source-jobs.json', 'source-preflight-artifact.json'}


def accepted_proof(path):
    """Trust the exact independently hosted proof, not a self-rehashed claim."""
    capture.old.parent.parent._pinned_file(Path(path), PROOF_PIN)
    with zipfile.ZipFile(path) as archive:
        require(set(archive.namelist()) == PROOF_NAMES and len(archive.namelist()) == len(PROOF_NAMES),
                'exact hosted proof archive required')
        proof = parse(archive.read('hosted-verification.json'))
    capture.c.d.base.verify_seal(proof)
    require(proof['content_sha256'] == PROOF_SEAL and proof['code_commit'] == PARENT
            and proof['run_id'] == '35105447180' and proof['hosted_capture_provenance_verified'] is True,
            'accepted hosted proof differs')
    return proof


def project_root(root, pages, expected):
    """Validate original page bytes and project close-only, bar-start frames."""
    parser = capture.MinutePages(root)
    rows = {s: [] for s in root['params']['symbols'].split(',')}
    for request, body in pages:
        parser.accept(request, {'status': 200, 'complete': True, 'encoding': 'identity', 'body': body})
        for symbol, bars in (parse(body)['bars'] or {}).items():
            rows[symbol].extend((r['t'], r['c']) for r in bars)
    exact(parser.result(), expected, 'accepted root projection differs')
    frames = {}
    for symbol, values in rows.items():
        frame = pd.DataFrame(values, columns=['timestamp', 'close'])
        frame.index = pd.to_datetime(frame.pop('timestamp'), utc=True)
        frames[symbol] = frame
    return frames


def open_capture(parts, pin):
    """Accept a ZIP or ordered byte-exact parts, with one original archive pin."""
    paths = [Path(parts)] if isinstance(parts, (str, Path)) else [Path(p) for p in parts]
    require(paths and len(paths) == len(set(paths)), 'unique ordered source parts required')
    require(all(p.is_file() and not any(q.is_symlink() for q in (p, *p.parents)) for p in paths),
            'regular source parts required')
    require(sum(p.stat().st_size for p in paths) == pin['bytes'], 'original source size differs')
    # Keep the verified bytes in memory so later filesystem changes cannot
    # replace the opened archive between validation and reading a day.
    data = io.BytesIO()
    digest = hashlib.sha256()
    for path in paths:
        with path.open('rb') as handle:
            while block := handle.read(1024 * 1024):
                require(data.tell() + len(block) <= pin['bytes'], 'source size changed during read')
                digest.update(block);data.write(block)
    require(data.tell() == pin['bytes'] and digest.hexdigest() == pin['sha256'], 'original source SHA differs')
    data.seek(0)
    return zipfile.ZipFile(data)


class ScannerMinuteArchive:
    """Indexed, bounded reader for every member of all 30 accepted dates."""
    def __init__(self, root, capture_zip):
        self.archives = {}
        try:
            self._open(Path(root), capture_zip)
        except BaseException:
            self.close()
            raise

    def _open(self, root, capture_zip):
        self.contract = capture.validate_registration(root)
        self.proof = accepted_proof(root / BASE / 'verification.zip')
        suffix = self.proof['archive_verification']
        capture.c.d.base.verify_seal(suffix)
        require(suffix['protocol_complete'] is True and suffix['contract_id'] == capture.ID,
                'complete continuation required')
        exact(self.proof['prefix_pin'], capture.PREFIX_PIN, 'original prefix differs')
        meta = suffix['archive_metadata']
        self.archives['continuation'] = open_capture(capture_zip, {'bytes': meta['size_in_bytes'], 'sha256': meta['digest'][7:]})
        prefix = capture.replay_prefix(root)
        raw = b''.join((root / name).read_bytes() for name in capture.PREFIX_PARTS)
        exact({'bytes': len(raw), 'sha256': sha(raw)}, capture.PREFIX_PIN, 'prefix bytes changed')
        self.archives['prefix'] = zipfile.ZipFile(io.BytesIO(raw))
        self.days = {d['trading_date']: d for d in capture.old.saved_daily(root)['days']}
        self.roots = prefix.tasks
        summaries = prefix.results + suffix['root_summaries']
        exact([r['root_sha256'] for r in summaries], [r['content_sha256'] for r in self.roots],
              'exact combined root union required')
        require(len(summaries) == self.proof['completed_roots'] == 690
                and sum(r['bar_count'] for r in summaries) == self.proof['total_bar_count']
                and sum(len(r['symbol_bar_counts']) for r in summaries) == self.proof['total_symbol_dates'],
                'combined source totals differ')
        self.summaries = {r['root_sha256']: r for r in summaries}
        self.inventories, self.locations = {}, {}
        segments = [('prefix', capture.PREFIX_ATTEMPTS, capture.PREFIX_INVENTORY, self.roots[:capture.PREFIX_ROOTS]),
                    ('continuation', suffix['attempt_count'], suffix['inventory_sha256'], self.contract['requests'])]
        for segment, attempts, inventory_pin, roots in segments:
            archive = self.archives[segment]
            inventory_raw = archive.read('inventory.json')
            require(sha(inventory_raw) == inventory_pin, 'source inventory differs')
            inventory = parse(inventory_raw)
            capture.c.d.base.verify_seal(inventory)
            require(len(archive.namelist()) == len(set(archive.namelist())) == attempts * 3 + 3
                    and set(inventory['files']) == set(archive.namelist()) - {'inventory.json'}, 'source members differ')
            self.inventories[segment] = inventory['files']
            contract = parse(self._read(segment, 'contract.json'))
            exact(contract['requests'], self.roots if segment == 'prefix' else self.contract['requests'],
                  'source request contract differs')
            ordered = []
            for ordinal in range(attempts):
                member = f'{ordinal:05d}'
                request = parse(self._read(segment, member + '.intent.json'))['request']
                key = request['root_sha256']
                if not ordered or ordered[-1] != key: ordered.append(key)
                self.locations.setdefault(key, []).append((segment, member, request))
            exact(ordered, [r['content_sha256'] for r in roots], 'segment root order differs')
        exact(list(self.locations), [r['content_sha256'] for r in self.roots], 'complete source index required')

    def _read(self, segment, name):
        raw = self.archives[segment].read(name)
        exact({'bytes': len(raw), 'sha256': sha(raw)}, self.inventories[segment][name], 'source member bytes differ')
        return raw

    def read_day(self, trading_date):
        require(trading_date in self.days, 'date outside fixed scanner panel')
        day = self.days[trading_date]
        roots = [r for r in self.roots if r['trading_date'] == trading_date]
        exact(roots, capture.old.roots_for_day(day), 'dated membership roots differ')
        frames, lineage = {}, []
        for root in roots:
            key = root['content_sha256']
            pages = []
            for segment, member, request in self.locations[key]:
                raw = self._read(segment, member + '.body.json')
                pages.append((request, raw))
                lineage.append({'segment': segment, 'body_member': member + '.body.json',
                                'body_sha256': sha(raw), 'root_sha256': key, 'request_sha256': request['content_sha256']})
            values = project_root(root, pages, self.summaries[key])
            require(not set(values).intersection(frames), 'duplicate dated membership')
            frames.update(values)
        exact(sorted(frames), day['membership_symbols'], 'complete dated member frames required')
        provenance = seal({'contract_id': ID, 'trading_date': trading_date,
            'membership_sha256': day['membership_sha256'], 'saved_daily_sha256': day['content_sha256'],
            'accepted_hosted_proof_sha256': self.proof['content_sha256'],
            'prefix_archive_sha256': capture.PREFIX_PIN['sha256'],
            'continuation_archive_sha256': self.proof['archive_verification']['archive_metadata']['digest'][7:],
            'source_pages': lineage, 'member_count': len(frames), 'bar_count': sum(len(f) for f in frames.values()),
            'empty_member_count': sum(f.empty for f in frames.values()), 'timestamp_semantics': 'bar start',
            'adjustment': 'split', 'daily_minute_share_basis_verified': False,
            'provider_requests': 0, **capture.old.parent.parent.BOUNDARY})
        return {'trading_date': trading_date, 'previous_close_by_symbol': deepcopy(day['previous_close_by_symbol']),
                'rank_split_minute_bars_by_symbol': frames, 'provenance': provenance}

    def close(self):
        for archive in self.archives.values(): archive.close()
        self.archives.clear()

    def __enter__(self): return self

    def __exit__(self, *args): self.close()
