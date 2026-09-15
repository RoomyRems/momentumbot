"""Batched full-membership rank minutes, preserving the frozen scanner basis."""
from copy import deepcopy
from datetime import date, datetime, time as daytime, timezone
import gzip
import math
from pathlib import Path
import re
import stat
import time
import zipfile

from momentumbot.research import alias_completion as parent

c, daily, gate = parent.c, parent.daily, parent.gate
require, exact, seal, sha, render, parse = parent.require, parent.exact, parent.seal, parent.sha, parent.render, parent.parse
ID = 'early-pullback-scanner-minutes-v0.1'
BASE = 'research/data-audits/' + ID
CONTRACT_PATH = 'research/strategy/' + ID + '.json'
WORKFLOW = '.github/workflows/scanner-minutes.yml'
PARENT = '51232cf6be74b3cea7a79d446a3c129d4dbe61f4'
REF = 'refs/tags/' + ID + '-consumed'
KEYS = parent.KEYS
MAX_PAGES = 20
MAX_ATTEMPTS = 13800
MAX_TOTAL = c.MAX_TOTAL
FILES = ('src/momentumbot/research/scanner_minutes.py', 'scripts/run_hosted_scanner_source.py',
    'tests/test_scanner_minutes.py', WORKFLOW, '.github/actions/source-runtime/action.yml',
    '.github/workflows/ci.yml', 'requirements-sealed-source-v04.txt')
COMPLETION_SEAL = '9f430be2348cd424187dcfc10356e9db65120da0c36745335191e298abbd484a'


def saved_daily(root):
    contract = parent.validate_registration(root)
    path = Path(root) / parent.SCANNER_PATH
    parent.parent._pinned_file(path, contract['file_bindings'][parent.SCANNER_PATH])
    value = parse(gzip.decompress(path.read_bytes()))
    c.d.base.verify_seal(value)
    completion = parse((Path(root) / parent.BASE / 'completion.json').read_bytes())
    c.d.base.verify_seal(completion)
    require(completion['content_sha256'] == COMPLETION_SEAL and completion['alias_mapping_checks_complete']
        and completion['distinct_figi_asof_views_consistent'] and not completion['membership_changed'],
        'completed dated mapping source required')
    exact([d['trading_date'] for d in value['days']], list(parent.parent.DATES), 'dated daily union differs')
    return value


def roots_for_day(day):
    """No candidate pruning: every frozen member participates in ranking."""
    symbols = day['membership_symbols']
    require(symbols and symbols == sorted(set(symbols)), 'sorted unique dated membership required')
    require(set(day['previous_close_by_symbol']) == set(symbols), 'complete previous closes required')
    target = date.fromisoformat(day['trading_date'])
    start = datetime.combine(target, daytime(4), daily.ET).astimezone(timezone.utc).isoformat()
    end = datetime.combine(target, daytime(10), daily.ET).astimezone(timezone.utc).isoformat()
    return [seal({'provider': 'alpaca', 'method': 'GET', 'url': 'https://data.alpaca.markets/v2/stocks/bars',
        'trading_date': target.isoformat(), 'membership_sha256': day['membership_sha256'],
        'params': {'symbols': ','.join(symbols[i:i + 250]), 'timeframe': '1Min', 'start': start, 'end': end,
            'adjustment': 'split', 'asof': target.isoformat(), 'feed': 'sip', 'sort': 'asc', 'limit': 10000}})
        for i in range(0, len(symbols), 250)]


def request_plan(root):
    value = saved_daily(root)
    roots = [r for d in value['days'] for r in roots_for_day(d)]
    require(len(roots) == 690 and sum(len(r['params']['symbols'].split(',')) for r in roots) == 165694,
        'fixed full-membership request population differs')
    return roots


def registration(root):
    inherited = parent.validate_registration(root)
    return seal({'contract_id': ID, 'contract_path': CONTRACT_PATH, 'workflow': WORKFLOW,
        'parent_commit': PARENT, 'parent_registration_sha256': inherited['content_sha256'],
        'completed_alias_sha256': COMPLETION_SEAL, 'requests': request_plan(root),
        'file_bindings': {n: {'bytes': (Path(root) / n).stat().st_size, 'sha256': sha((Path(root) / n).read_bytes())} for n in FILES},
        'authorization': {'user_message': 'You may proceed. Lets try to get this finished up as quickly as we can so we can implement the discretionary part.',
            'starts_at': '2026-09-15T00:00:00Z', 'expires_at': '2026-09-22T00:00:00Z',
            'scope': 'one batched split-minute capture for all 165694 frozen ticker/date memberships on the existing 30 dates',
            'estimated_incremental_api_cost_usd': '0.00', 'subscription_changes_authorized': False,
            'new_data_products_authorized': False, 'metered_purchase_authorized': False},
        'limits': {'maximum_attempts': MAX_ATTEMPTS, 'maximum_pages_per_root': MAX_PAGES,
            'maximum_payload_bytes': c.MAX_PAYLOAD, 'maximum_metadata_bytes': c.MAX_METADATA,
            'maximum_duration_ns': c.MAX_DURATION_NS, 'maximum_body_bytes': daily.MAX_BODY,
            'minimum_interval_ns': c.INTERVAL_NS['alpaca'], 'retries': 0, 'redirects': 0},
        'runtime': gate.d.previous.RUNTIME, 'consumption_ref': REF, 'credential_names': list(KEYS),
        'receipt_and_report_schema': c.ID, 'timestamp_semantics': 'bar start; usable only at start plus one minute',
        'rank_basis': 'split minute close / saved split previous close; raw price and volume remain separate',
        **parent.parent.BOUNDARY})


def validate_registration(root):
    value = parse((Path(root) / CONTRACT_PATH).read_bytes())
    exact(value, registration(root), 'scanner minute registration differs')
    return value


class MinutePages:
    """Transactional symbol/time pagination with exhausted empty evidence."""
    def __init__(self, root):
        self.root = deepcopy(root)
        self.symbols = root['params']['symbols'].split(',')
        self.token, self.last = None, None
        self.tokens, self.pages = set(), []
        self.counts = dict.fromkeys(self.symbols, 0)
        self.complete = self.failed = False

    def request(self):
        require(not self.complete and not self.failed and len(self.pages) < MAX_PAGES, 'minute root terminal')
        params = dict(self.root['params'])
        if self.token is not None: params['page_token'] = self.token
        return seal({**{k: v for k, v in self.root.items() if k != 'content_sha256'}, 'params': params,
            'root_sha256': self.root['content_sha256'], 'page': len(self.pages) + 1})

    def accept(self, request, reply):
        try: return self._accept(request, reply)
        except Exception:
            self.failed = True
            raise

    def _accept(self, request, reply):
        exact(request, self.request(), 'minute request/cursor differs')
        c.validate_reply(reply)
        require(reply['status'] == 200 and reply['complete'] is True and reply['encoding'] == 'identity'
            and 0 < len(reply['body']) <= daily.MAX_BODY, 'complete bounded HTTP 200 required')
        payload = parse(reply['body'])
        require(set(payload) == {'bars', 'next_page_token'}, 'exact minute envelope required')
        bars, token = payload['bars'], daily._token(payload['next_page_token'])
        require(bars is None or type(bars) is dict, 'minute symbol mapping required')
        bars = {} if bars is None else bars
        require(set(bars) <= set(self.symbols), 'unrequested minute symbol')
        require(token is None or token not in self.tokens, 'repeated minute cursor')
        counts, last, count = dict(self.counts), self.last, 0
        start, end = (daily._stamp(self.root['params'][k]) for k in ('start', 'end'))
        for symbol, rows in sorted(bars.items()):
            require(type(rows) is list, 'minute bar list required')
            for row in rows:
                require(type(row) is dict and set(row) == {'t', 'o', 'h', 'l', 'c', 'v', 'n', 'vw'}, 'exact minute fields required')
                stamp = daily._stamp(row['t'])
                require(start <= stamp <= end and stamp.second == stamp.microsecond == 0, 'minute timestamp outside grid/window')
                key = (symbol, stamp)
                require(last is None or key > last, 'duplicate or regressing minute')
                for field in ('o', 'h', 'l', 'c', 'v', 'vw'):
                    require(type(row[field]) in (int, float) and math.isfinite(row[field]) and row[field] >= 0,
                        'finite nonnegative minute number required')
                require(type(row['n']) is int and row['n'] >= 0, 'integer trade count required')
                require(row['l'] <= min(row['o'], row['c']) <= max(row['o'], row['c']) <= row['h'], 'minute OHLC bounds')
                last, count = key, count + 1
                counts[symbol] += 1
        require(count <= self.root['params']['limit'] and (token is None or count > 0), 'minute page progress/limit')
        require(token is None or len(self.pages) + 1 < MAX_PAGES, 'minute page ceiling reached')
        witness = {'request_sha256': request['content_sha256'], 'body_sha256': sha(reply['body']),
            'body_bytes': len(reply['body']), 'bar_count': count, 'terminal': token is None}
        self.counts, self.last = counts, last
        self.pages.append(witness)
        self.token, self.complete = token, token is None
        if token is not None: self.tokens.add(token)
        return deepcopy(witness)

    def result(self):
        require(self.complete and not self.failed, 'exhausted minute root required')
        return seal({'root_sha256': self.root['content_sha256'], 'trading_date': self.root['trading_date'],
            'membership_sha256': self.root['membership_sha256'], 'pages': deepcopy(self.pages),
            'symbol_bar_counts': dict(self.counts), 'bar_count': sum(self.counts.values()),
            'empty_symbols': [s for s, n in self.counts.items() if n == 0], **parent.parent.BOUNDARY})


class State(parent.State):
    def request(self):
        require(not self.failed, 'minute state failed')
        if len(self.results) == len(self.tasks): return None
        if self.current is None: self.current = MinutePages(self.tasks[len(self.results)])
        return self.current.request()

    def accept(self, request, reply):
        try:
            exact(request, self.request(), 'fixed next minute page required')
            self.current.accept(request, reply)
            if self.current.complete:
                self.results.append(self.current.result())
                self.current = None
        except Exception:
            self.failed = True
            raise


class Capture(c.Capture):
    def __init__(self, contract, *, output, transport, keys, clock_ns=time.monotonic_ns,
            sleeper=time.sleep, utc_now=lambda: datetime.now(timezone.utc).isoformat(), progress=lambda _: None):
        require(type(keys) is dict and set(keys) == set(KEYS), 'only two Alpaca credentials required')
        keys = {**keys, 'MASSIVE_API_KEY': 'UNUSED_ALPACA_ONLY'}
        c.validate_keys(keys)
        self.store = c.Store(output)
        self.store.write('contract.json', render(contract))
        self.state, self.transport, self.keys = State(contract['requests']), transport, keys
        self.clock, self.sleep, self.now, self.progress = clock_ns, sleeper, utc_now, progress
        self.attempts, self.finished, self.last = 0, False, {}
        self.started_ns = self.clock()

    def once(self, request):
        exact(request, self.state.request(), 'registered next minute request required')
        require(self.attempts < MAX_ATTEMPTS, 'minute attempt ceiling')
        return super().once(request)


Transport = parent.Transport


def preflight(root, env, facts, now, runtime, path, metadata, live_ref):
    contract = validate_registration(root)
    gate.check_launch(contract, env, facts, now)
    gate.verify_preflight(parent.read_archive(path, metadata['size_in_bytes'], metadata['digest'][7:]),
        contract, env, runtime, live_ref, metadata)
    return contract


def capture(root, env, facts, now, runtime, path, metadata, live_ref, *, output, credential_loader, transport, progress):
    contract = preflight(root, env, facts, now, runtime, path, metadata, live_ref)
    require(not Path(output).exists() and not any(p.is_symlink() for p in (Path(output), *Path(output).parents)), 'fresh output required')
    return Capture(contract, output=output, keys=credential_loader(), transport=transport, progress=progress).run()


def verify_archive(path, metadata, inventory_sha256, contract):
    """Stream original members through the minute parser; never retain all bars."""
    parent.parent._pinned_file(path, {'bytes': metadata['size_in_bytes'], 'sha256': metadata['digest'][7:]})
    require(0 < metadata['size_in_bytes'] <= MAX_TOTAL, 'bounded original archive required')
    state, count, last, first = State(contract['requests']), 0, None, None
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = {i.filename for i in infos}
        require(len(names) == len(infos) <= MAX_ATTEMPTS * 3 + 3 and sum(i.file_size for i in infos) <= MAX_TOTAL,
            'bounded unique archive members required')
        payload_bytes = sum(i.file_size for i in infos if i.filename.endswith('.body.json') or i.filename == 'report.json')
        require(payload_bytes <= c.MAX_PAYLOAD and sum(i.file_size for i in infos) - payload_bytes <= c.MAX_METADATA,
            'archive retention ceilings')
        for info in infos:
            require(re.fullmatch(r'(?:contract|inventory|report)\.json|[0-9]{5}\.(?:intent|receipt|body)\.json', info.filename)
                and not info.is_dir() and stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG)
                and info.file_size <= (daily.MAX_BODY if info.filename.endswith('.body.json') else
                    c.REPORT_RESERVE if info.filename == 'report.json' else c.MAX_METADATA), 'unsafe archive member')
        raw = archive.read('inventory.json')
        require(sha(raw) == inventory_sha256, 'independent inventory differs')
        inventory = parse(raw)
        c.d.base.verify_seal(inventory)
        require(set(inventory) == {'contract_id', 'files', 'content_sha256'} and inventory['contract_id'] == c.ID
            and set(inventory['files']) == names - {'inventory.json'}, 'inventory population differs')
        for name, spec in inventory['files'].items():
            raw = archive.read(name)
            exact(spec, {'bytes': len(raw), 'sha256': sha(raw)}, 'original member differs')
        exact(parse(archive.read('contract.json')), contract, 'captured contract differs')
        while (request := state.request()) is not None:
            require(count < MAX_ATTEMPTS, 'archive attempt ceiling')
            prefix = f'{count:05d}'
            intent, receipt = (parse(archive.read(prefix + '.' + k + '.json')) for k in ('intent', 'receipt'))
            started = intent['started_monotonic_ns']
            require(type(started) is int and started >= 0 and (last is None or started - last >= c.INTERVAL_NS['alpaca']),
                'archive pacing differs')
            if first is None: first = started
            require(started - first < c.MAX_DURATION_NS, 'archive duration ceiling')
            last = started
            begin, end = (datetime.fromisoformat(v) for v in (intent['started_at'], receipt['finished_at']))
            require(begin.tzinfo is not None and end.tzinfo is not None and begin <= end, 'archive clocks differ')
            exact(intent, seal({'contract_id': c.ID, 'ordinal': count, 'request': request,
                'started_at': intent['started_at'], 'started_monotonic_ns': started}), 'intent differs')
            body = archive.read(prefix + '.body.json')
            exact(receipt, seal({'contract_id': c.ID, 'ordinal': count, 'intent_sha256': intent['content_sha256'],
                'finished_at': receipt['finished_at'], 'status': 200, 'complete': True, 'body_bytes': len(body),
                'body_sha256': sha(body), 'body_retained': True, 'error': None}), 'receipt differs')
            state.accept(request, {'status': 200, 'body': body, 'complete': True, 'encoding': 'identity'})
            count += 1
        require(len(names) == count * 3 + 3, 'extra or missing capture members')
        exact(parse(archive.read('report.json')), c.report(state, count, None), 'original report replay differs')
    return seal({'contract_id': ID, 'archive_metadata': metadata, 'inventory_sha256': inventory_sha256,
        'protocol_complete': True, 'attempt_count': count, 'verified_member_count': len(names),
        'requests_complete': len(state.results), 'bar_count': sum(r['bar_count'] for r in state.results),
        'symbol_dates': sum(len(r['symbol_bar_counts']) for r in state.results),
        'empty_symbol_dates': sum(len(r['empty_symbols']) for r in state.results),
        'root_summaries': state.results, 'provider_requests': 0, **parent.parent.BOUNDARY})


def verify(root, env, facts, now, runtime, path, metadata, live_ref, capture_path, capture_metadata, jobs):
    contract = preflight(root, env, facts, now, runtime, path, metadata, live_ref)
    gate.check_jobs(jobs, env)
    gate.check_artifact(capture_metadata, contract, env, 'capture', env['CAPTURE_ARTIFACT_ID'], MAX_TOTAL)
    result = verify_archive(capture_path, capture_metadata, env['CAPTURE_INVENTORY_SHA256'], contract)
    return seal({'contract_id': ID, 'code_commit': env['GITHUB_SHA'], 'run_id': env['GITHUB_RUN_ID'],
        'archive_verification': result, 'hosted_capture_provenance_verified': True,
        'consumption_ref': REF, 'provider_requests_during_verification': 0, **parent.parent.BOUNDARY})


def read_rank_day(path, verification, contract, day):
    """Source adapter after independent archive verification, with bar-start labels.

    The caller supplies the accepted verification record. This reader checks
    bytes and lineage; it does not authenticate a caller-created proof.
    """
    import pandas as pd
    c.d.base.verify_seal(verification)
    require(verification['contract_id'] == ID and verification['protocol_complete'] is True,
        'completed minute verification required')
    metadata = verification['archive_metadata']
    parent.parent._pinned_file(path, {'bytes': metadata['size_in_bytes'], 'sha256': metadata['digest'][7:]})
    roots = {r['content_sha256']: r for r in contract['requests'] if r['trading_date'] == day['trading_date']}
    exact(list(roots.values()), roots_for_day(day), 'dated root membership differs')
    rows = {s: [] for s in day['membership_symbols']}
    with zipfile.ZipFile(path) as archive:
        exact(parse(archive.read('contract.json')), contract, 'reader contract differs from original capture')
        for ordinal in range(verification['attempt_count']):
            prefix = f'{ordinal:05d}'
            request = parse(archive.read(prefix + '.intent.json'))['request']
            if request['root_sha256'] not in roots: continue
            body = parse(archive.read(prefix + '.body.json'))
            for symbol, bars in (body['bars'] or {}).items():
                rows[symbol].extend((r['t'], r['c']) for r in bars)
    frames = {}
    for symbol, bars in rows.items():
        frame = pd.DataFrame(bars, columns=['timestamp', 'close'])
        frame.index = pd.to_datetime(frame.pop('timestamp'), utc=True)
        frames[symbol] = frame
    return dict(day['previous_close_by_symbol']), frames
