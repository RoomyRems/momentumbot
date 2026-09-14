"""Bounded raw-page replay for the frozen census daily coverage handoff.

No network or launch authority. Hashes describe bytes, not provider provenance.
Current corporate-action history is not an as-known historical announcement feed.
"""
from copy import deepcopy
from datetime import date, datetime, timedelta
import gzip
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from momentumbot.research import census_scanner_bridge as bridge

require, exact, seal, sha = bridge.require, bridge.exact, bridge.seal, bridge.sha
ID = 'early-pullback-daily-coverage-v0.1'
CONTRACT_PATH = 'research/strategy/' + ID + '.json'
OWN_FILES = ('src/momentumbot/research/daily_coverage.py',
    'scripts/replay_daily_coverage.py', 'tests/test_daily_coverage.py')
MAX_BODY = 16 * 1024 * 1024
MAX_PAGES = 10
PANEL_BYTES = 6644041
PANEL_SHA = '73ae62ae6ea1172566fcb7be5484b7a37a179b38ad9452130197fd0262907da2'
PANEL_SEAL = '307c42e4fbfe63967cba943796f13aaa0f836fd7f7fc35f1ef1e925df4c8dcc8'
ET = ZoneInfo('America/New_York')
ACTION_TYPES = ('forward_split', 'reverse_split', 'unit_split', 'stock_dividend',
    'spin_off', 'cash_merger', 'stock_merger', 'stock_and_cash_merger',
    'redemption', 'name_change', 'worthless_removal', 'rights_distribution',
    'partial_call', 'reorganization')


def registration(root):
    parent = bridge.validate_registration(root)
    return seal({'contract_id': ID, 'parent_commit': '8387c43e9fe899b2e1f1951b0127afa62aee46ca',
        'parent_registration_sha256': parent['content_sha256'],
        'file_bindings': {name: {'bytes': (Path(root) / name).stat().st_size,
            'sha256': sha((Path(root) / name).read_bytes())} for name in OWN_FILES},
        'panel_bytes': PANEL_BYTES, 'panel_file_sha256': PANEL_SHA, 'panel_sha256': PANEL_SEAL,
        'selected_dates': list(bridge.DATES), 'daily_roots': 1380,
        'daily_pages_per_root_maximum': MAX_PAGES, 'daily_http_attempt_ceiling': 1380 * MAX_PAGES,
        'response_body_byte_ceiling': MAX_BODY, 'identity_initial_roots': 60,
        'identity_http_attempt_ceiling': None, 'capture_authorized': False,
        'identity_requests': [r for day in bridge.DATES for r in identity_requests(day)],
        'hypothesis': 'exhausted raw pages yield complete dated coverage without partial-data exclusions',
        **bridge.BOUNDARY})


def validate_registration(root):
    saved = bridge.parse((Path(root) / CONTRACT_PATH).read_bytes())
    exact(saved, registration(root), 'daily coverage registration differs')
    return saved


def load_panel(root):
    """Only the already published, byte-pinned reference panel is admissible."""
    path = Path(root) / bridge.BASE / 'reference-panel.json.gz'
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)),
        'regular pinned panel required')
    require(path.stat().st_size == PANEL_BYTES, 'panel size differs')
    raw = path.read_bytes()
    require(sha(raw) == PANEL_SHA, 'panel bytes differ')
    panel = bridge.parse(gzip.decompress(raw))
    bridge.parent.d.base.verify_seal(panel)
    require(panel['content_sha256'] == PANEL_SEAL, 'panel seal differs')
    exact([d['trading_date'] for d in panel['days']], list(bridge.DATES), 'panel dates differ')
    return panel


def identity_requests(day):
    """Unarmed source roots matching the existing 120-day identity audit scope."""
    require(day in bridge.DATES, 'date outside fixed panel')
    start = (date.fromisoformat(day) - timedelta(days=120)).isoformat()
    return [seal({'provider': 'alpaca', 'method': 'GET',
        'url': 'https://data.alpaca.markets/v1/corporate-actions', 'trading_date': day,
        'params': {'start': start, 'end': day, 'region': 'us', 'data_quality': 'complete',
            'types': ','.join(ACTION_TYPES), 'limit': 1000, 'sort': 'asc'}}),
        seal({'provider': 'massive', 'method': 'GET',
        'url': 'https://api.massive.com/stocks/v1/splits', 'trading_date': day,
        'params': {'execution_date.gte': start, 'execution_date.lte': day,
            'limit': 5000, 'sort': 'execution_date.asc,ticker.asc'}})]


def _stamp(value):
    require(type(value) is str and 'T' in value, 'RFC3339 timestamp required')
    try:
        out = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('invalid bar timestamp') from None
    require(out.tzinfo is not None and out.utcoffset() is not None, 'aware bar timestamp required')
    return out


def _token(value):
    require(value is None or (type(value) is str and 1 <= len(value) <= 4096
        and value.isascii() and all(32 < ord(c) < 127 for c in value)), 'invalid page token')
    return value


class DailyPages:
    """One immutable root; transactional pages; exhausted emptiness is explicit.

    An HTTP failure is unavailable evidence, never an invalid-symbol inference.
    A caller may replay retained bytes, but this class does not authenticate them.
    """
    def __init__(self, projected, root):
        roots = bridge.coverage_requests(projected)
        require(any(root == r for r in roots), 'root differs from frozen coverage union')
        self._root = deepcopy(root)
        self._symbols = root['params']['symbols'].split(',')
        self._dates = {symbol: set() for symbol in self._symbols}
        self._token = None
        self._seen_tokens = set()
        self._last = None
        self._pages = []
        self._complete = False
        self._failed = False

    def request(self):
        require(not self._complete and not self._failed, 'root already terminal')
        require(len(self._pages) < MAX_PAGES, 'page ceiling reached')
        request = deepcopy(self._root)
        request.pop('content_sha256')
        if self._token is not None:
            request['params']['page_token'] = self._token
        request['root_sha256'] = self._root['content_sha256']
        request['page'] = len(self._pages) + 1
        return seal(request)

    def accept(self, request, response):
        """Any rejected attempt permanently closes this instance; no retries."""
        try:
            return self._accept(request, response)
        except Exception:
            self._failed = True
            raise

    def _accept(self, request, response):
        exact(request, self.request(), 'unexpected request or cursor')
        require(type(response) is dict and set(response) == {'status', 'body', 'complete', 'encoding'},
            'exact transport envelope required')
        require(type(response['status']) is int and response['status'] == 200
            and response['complete'] is True and response['encoding'] == 'identity',
            'complete uncompressed HTTP 200 required')
        raw = response['body']
        require(type(raw) is bytes and 0 < len(raw) <= MAX_BODY, 'body byte ceiling')
        payload = bridge.parse(raw)
        require(set(payload) == {'bars', 'next_page_token'}, 'exact bars envelope required')
        token = _token(payload['next_page_token'])
        require(token is None or token not in self._seen_tokens, 'repeated page token')
        bars = payload['bars']
        require(bars is None or type(bars) is dict, 'bars mapping required')
        bars = {} if bars is None else bars
        require(set(bars) <= set(self._symbols), 'unrequested symbol returned')
        observed, last, count = deepcopy(self._dates), self._last, 0
        start, end = (_stamp(self._root['params'][key]) for key in ('start', 'end'))
        target = date.fromisoformat(self._root['trading_date'])
        # JSON object key order has no semantics. Sort symbols, preserve each bar list.
        for symbol in sorted(bars):
            require(type(bars[symbol]) is list, 'bar list required')
            for bar in bars[symbol]:
                require(type(bar) is dict and set(bar) == {'t', 'o', 'h', 'l', 'c', 'v', 'n', 'vw'},
                    'exact daily bar schema required')
                stamp = _stamp(bar['t'])
                local_date = stamp.astimezone(ET).date()
                require(start <= stamp <= end and local_date <= target, 'bar outside causal request window')
                key = (symbol, stamp)
                require(last is None or key > last, 'duplicate or regressing bar order')
                require(local_date not in observed[symbol], 'duplicate daily session')
                for field in ('o', 'h', 'l', 'c', 'v', 'vw'):
                    value = bar[field]
                    require(type(value) in (int, float) and math.isfinite(value)
                        and value >= 0, 'finite nonnegative bar number required')
                require(type(bar['n']) is int and bar['n'] >= 0, 'nonnegative trade count required')
                require(bar['l'] <= min(bar['o'], bar['c']) <= max(bar['o'], bar['c']) <= bar['h'],
                    'inconsistent OHLC bounds')
                observed[symbol].add(local_date)
                last, count = key, count + 1
        require(count <= self._root['params']['limit'], 'page row limit exceeded')
        require(token is None or count > 0, 'nonterminal page made no progress')
        require(token is None or len(self._pages) + 1 < MAX_PAGES, 'nonterminal page at ceiling')
        witness = {'request_sha256': request['content_sha256'], 'body_sha256': sha(raw),
            'body_bytes': len(raw), 'bar_count': count, 'terminal': token is None}
        self._dates, self._last = observed, last
        self._pages.append(witness)
        self._token, self._complete = token, token is None
        if token is not None:
            self._seen_tokens.add(token)
        return deepcopy(witness)

    def result(self):
        require(self._complete and not self._failed, 'exhausted successful root required')
        target = date.fromisoformat(self._root['trading_date'])
        return seal({'contract_id': ID, 'root_sha256': self._root['content_sha256'],
            'pages': deepcopy(self._pages), 'observations': {symbol: {
                'prior_session_present': any(day < target for day in dates),
                'target_session_present': target in dates} for symbol, dates in self._dates.items()},
            'provider_origin_authenticated': False, **bridge.BOUNDARY})


class DailyCoverage:
    """Replay every root for one reference day before emitting adapter input."""
    def __init__(self, projected):
        self._projected = deepcopy(projected)
        self._roots = bridge.coverage_requests(projected)
        self._results = []
        self._current = None
        self._failed = False

    def request(self):
        require(not self._failed and len(self._results) < len(self._roots), 'coverage terminal')
        if self._current is None:
            self._current = DailyPages(self._projected, self._roots[len(self._results)])
        return self._current.request()

    def accept(self, request, response):
        try:
            exact(request, self.request(), 'coverage request differs')
            witness = self._current.accept(request, response)
            if witness['terminal']:
                self._results.append(self._current.result())
                self._current = None
            return witness
        except Exception:
            self._failed = True
            raise

    def result(self):
        require(not self._failed and self._current is None and len(self._results) == len(self._roots),
            'all raw and split roots must exhaust successfully')
        records = {symbol: {'invalid_symbol': False} for symbol in self._projected['coverage_symbols']}
        for root, result in zip(self._roots, self._results):
            for symbol, observations in result['observations'].items():
                for key, value in observations.items():
                    records[symbol][root['params']['adjustment'] + '_' + key] = value
        for record in records.values():
            record['coverage_pass'] = all(v for k, v in record.items() if k != 'invalid_symbol')
        coverage = {'trading_date': self._projected['trading_date'],
            'reference_sha256': self._projected['content_sha256'], 'records': records}
        return seal({'contract_id': ID, 'coverage': coverage,
            'coverage_sha256': bridge.fingerprint(coverage), 'roots': deepcopy(self._results),
            'provider_origin_authenticated': False, **bridge.BOUNDARY})
