"""One-pass daily/identity source capture and independent original-byte replay."""
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import http.client
import math
import os
from pathlib import Path
import re
import stat
import time
from urllib.parse import parse_qsl, urlencode, urlsplit
import zipfile

from momentumbot.research import daily_coverage as daily

b = daily.bridge
d = b.parent.d
require, exact, seal, sha, render, parse = b.require, b.exact, b.seal, b.sha, b.render, b.parse
ID = 'early-pullback-coverage-capture-v0.1'
ACTION_PAGES = 20
MAX_ATTEMPTS = 15000
MAX_DURATION_NS = 150 * 60 * 1_000_000_000
MAX_PAYLOAD = 1_500_000_000
MAX_METADATA = 80_000_000
REPORT_RESERVE = 200_000_000
MAX_TOTAL = MAX_PAYLOAD + MAX_METADATA
INTERVAL_NS = {'alpaca': 350_000_000, 'massive': 12_500_000_000}
KEYS = ('ALPACA_API_KEY', 'ALPACA_API_SECRET', 'MASSIVE_API_KEY')


def iso_day(value):
    require(type(value) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value), 'ISO date required')
    return date.fromisoformat(value)


class ActionPages:
    """Source validation only: no event implies verified security continuity."""
    def __init__(self, root):
        require(root in daily.identity_requests(root.get('trading_date')), 'fixed identity root required')
        self.root = deepcopy(root)
        self.params = dict(root['params'])
        self.pages, self.rows, self.tokens = [], [], set()
        self.identities, self.last = set(), {}
        self.complete = self.failed = False

    def request(self):
        require(not self.complete and not self.failed and len(self.pages) < ACTION_PAGES, 'identity root terminal')
        return seal({**{k: v for k, v in self.root.items() if k != 'content_sha256'},
            'params': dict(self.params), 'root_sha256': self.root['content_sha256'], 'page': len(self.pages) + 1})

    def accept(self, request, reply):
        try:
            return self._accept(request, reply)
        except Exception:
            self.failed = True
            raise

    def _accept(self, request, reply):
        exact(request, self.request(), 'identity request differs')
        validate_reply(reply)
        require(reply['status'] == 200 and reply['complete'] is True and reply['encoding'] == 'identity',
            'successful identity response required')
        raw = reply['body']
        require(len(raw) <= daily.MAX_BODY, 'identity body ceiling')
        payload = parse(raw)
        rows, identities, last = [], set(self.identities), dict(self.last)
        params = dict(self.root['params'])
        if self.root['provider'] == 'alpaca':
            require(set(payload) == {'corporate_actions', 'next_page_token'}
                and type(payload['corporate_actions']) is dict, 'grouped corporate actions required')
            token = daily._token(payload['next_page_token'])
            start, end = params['start'], params['end']
            groups = payload['corporate_actions']
            require(set(groups) <= {t + 's' for t in daily.ACTION_TYPES}, 'unrequested action group')
            for kind, events in sorted(groups.items()):
                require(type(events) is list, 'action list required')
                for event in events:
                    require(type(event) is dict and 'action_type' not in event, 'original action object required')
                    identity = event.get('id')
                    require(type(identity) is str and 0 < len(identity) <= 256, 'action ID required')
                    process = event.get('process_date')
                    iso_day(process)
                    require(start <= process <= end, 'action process date outside window')
                    require(kind not in last or process >= last[kind], 'action date regression')
                    require(identity not in identities, 'duplicate action ID')
                    identities.add(identity)
                    last[kind] = process
                    rows.append({**event, 'action_type': kind})
            if token is not None: params['page_token'] = token
        else:
            require({'results', 'status'} <= set(payload) <= {'results', 'status', 'next_url', 'request_id'}
                and payload['status'] == 'OK' and type(payload['results']) is list, 'split response schema')
            rows = deepcopy(payload['results'])
            token = None
            following = payload.get('next_url')
            if following is not None:
                require(type(following) is str and 0 < len(following) <= 8192, 'bounded next URL required')
                parsed = urlsplit(following)
                require(parsed.scheme == 'https' and parsed.netloc == 'api.massive.com'
                    and parsed.path == '/stocks/v1/splits' and not parsed.fragment,
                    'split pagination origin/path differs')
                pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
                require(len(pairs) == len(dict(pairs)), 'duplicate pagination parameter')
                query = dict(pairs)
                require('cursor' in query and set(query) <= set(params) | {'cursor'}, 'unregistered pagination parameter')
                for key in set(query) - {'cursor'}:
                    require(query[key] == str(params[key]), 'pagination changed root query')
                token = daily._token(query['cursor'])
                params = query
            for event in rows:
                require(type(event) is dict and {'id', 'ticker', 'execution_date', 'split_from', 'split_to', 'adjustment_type'} <= set(event)
                    <= {'id', 'ticker', 'execution_date', 'split_from', 'split_to', 'adjustment_type', 'historical_adjustment_factor'},
                    'split event schema')
                require(type(event['id']) is str and 0 < len(event['id']) <= 256
                    and type(event['ticker']) is str and 0 < len(event['ticker']) <= 64, 'split identity required')
                iso_day(event['execution_date'])
                require(self.root['params']['execution_date.gte'] <= event['execution_date']
                    <= self.root['params']['execution_date.lte'], 'split outside window')
                require(event['adjustment_type'] in ('forward_split', 'reverse_split', 'stock_dividend'), 'split type differs')
                for key in ('split_from', 'split_to', 'historical_adjustment_factor'):
                    if key in event:
                        value = event[key]
                        require(type(value) in (int, float) and math.isfinite(value) and value > 0, 'positive split factor required')
                order = (event['execution_date'], event['ticker'])
                require('split' not in last or order >= last['split'], 'split date/ticker regression')
                require(event['id'] not in identities, 'duplicate split ID')
                identities.add(event['id'])
                last['split'] = order
        require(len(rows) <= self.root['params']['limit'], 'action row ceiling')
        require(token is None or (rows and token not in self.tokens and len(self.pages) + 1 < ACTION_PAGES),
            'identity cursor repeated, empty or beyond ceiling')
        witness = {'request_sha256': request['content_sha256'], 'body_sha256': sha(raw),
            'body_bytes': len(raw), 'row_count': len(rows), 'terminal': token is None}
        self.pages.append(witness)
        self.rows.extend(rows)
        self.identities, self.last, self.params = identities, last, params
        self.complete = token is None
        if token is not None: self.tokens.add(token)
        return deepcopy(witness)

    def result(self):
        require(self.complete and not self.failed, 'exhausted identity root required')
        return seal({'root_sha256': self.root['content_sha256'], 'rows': deepcopy(self.rows),
            'pages': deepcopy(self.pages), 'as_known_historical_feed': False, **b.BOUNDARY})


class PanelState:
    def __init__(self, panel):
        self.days = deepcopy(panel['days'])
        self.tasks = [(kind, day, root) for day in self.days for kind, root in
            [('daily', None), *[('identity', r) for r in daily.identity_requests(day['trading_date'])]]]
        self.current = None
        self.results = []
        self.failed = False

    def request(self):
        require(not self.failed, 'panel failed')
        if len(self.results) == len(self.tasks): return None
        if self.current is None:
            kind, day, root = self.tasks[len(self.results)]
            self.current = daily.DailyCoverage(day) if kind == 'daily' else ActionPages(root)
        return self.current.request()

    def accept(self, request, reply):
        try:
            exact(request, self.request(), 'panel request differs')
            self.current.accept(request, reply)
            # DailyCoverage has several roots; terminality is checked from its fixed root count.
            complete = (len(self.current._results) == len(self.current._roots)) if isinstance(
                self.current, daily.DailyCoverage) else self.current.complete
            if complete:
                kind, day, root = self.tasks[len(self.results)]
                result = self.current.result()
                if kind == 'identity':
                    rows = result.pop('rows')
                    result.pop('content_sha256')
                    result = seal({**result, 'rows_sha256': b.fingerprint(rows), 'row_count': len(rows)})
                self.results.append({'kind': kind, 'date': day['trading_date'], 'result': result})
                self.current = None
        except Exception:
            self.failed = True
            raise


def validate_reply(reply):
    require(type(reply) is dict and set(reply) == {'status', 'body', 'complete', 'encoding'}, 'transport envelope differs')
    require(type(reply['status']) is int and 100 <= reply['status'] <= 599 and type(reply['body']) is bytes
        and len(reply['body']) <= daily.MAX_BODY + 1 and type(reply['complete']) is bool
        and type(reply['encoding']) is str and len(reply['encoding']) <= 64, 'invalid transport observation')


def validate_keys(keys):
    require(type(keys) is dict and set(keys) == set(KEYS), 'exact credential names required')
    require(all(type(v) is str and 8 <= len(v) <= 1024 and v.isascii()
        and all(32 < ord(c) < 127 for c in v) for v in keys.values()), 'bounded credential format required')


class DirectHTTPS:
    """Fixed data hosts only; explicit credentials; no redirects, proxies or retry."""
    def __init__(self, *, connection_factory=http.client.HTTPSConnection, clock=time.monotonic):
        self.factory, self.clock = connection_factory, clock

    def __call__(self, request, keys):
        validate_keys(keys)
        host = urlsplit(request['url'])
        require(request['method'] == 'GET' and (request['provider'], request['url']) in {
            ('alpaca', 'https://data.alpaca.markets/v2/stocks/bars'),
            ('alpaca', 'https://data.alpaca.markets/v1/corporate-actions'),
            ('massive', 'https://api.massive.com/stocks/v1/splits')}, 'fixed data endpoint required')
        params = dict(request['params'])
        require(not set(params) & {'apiKey', 'api_key', 'token'}, 'credential query injection')
        headers = {'Accept': 'application/json', 'Accept-Encoding': 'identity', 'User-Agent': 'MomentumBot ' + ID}
        if request['provider'] == 'alpaca':
            headers.update({'APCA-API-KEY-ID': keys['ALPACA_API_KEY'], 'APCA-API-SECRET-KEY': keys['ALPACA_API_SECRET']})
        else:
            params['apiKey'] = keys['MASSIVE_API_KEY']
        connection = self.factory(host.netloc, timeout=30)
        started, body, status, encoding = self.clock(), bytearray(), None, 'identity'
        try:
            connection.request('GET', host.path + '?' + urlencode(params), headers=headers)
            response = connection.getresponse()
            status, encoding = response.status, response.getheader('Content-Encoding', 'identity').lower()
            length = response.getheader('Content-Length')
            if length is not None:
                require(length.isascii() and length.isdecimal(), 'invalid content length')
                length = int(length)
            while len(body) <= daily.MAX_BODY and self.clock() - started < 30:
                chunk = response.read1(min(65536, daily.MAX_BODY + 1 - len(body)))
                if not chunk:
                    return {'status': status, 'body': bytes(body), 'complete': length is None or length == len(body), 'encoding': encoding}
                body.extend(chunk)
            return {'status': status, 'body': bytes(body), 'complete': False, 'encoding': encoding}
        except (OSError, http.client.IncompleteRead):
            if status is None: raise
            return {'status': status, 'body': bytes(body), 'complete': False, 'encoding': encoding}
        finally:
            connection.close()


class Store:
    def __init__(self, path):
        self.path = Path(path)
        require(not any(p.is_symlink() for p in (self.path, *self.path.parents)), 'regular output path required')
        self.path.mkdir(parents=True, exist_ok=False)
        self.payload = self.metadata = 0
        self.files = {}

    def write(self, name, raw, *, payload=False):
        require(re.fullmatch(r'[A-Za-z0-9.-]+', name) and type(raw) is bytes, 'flat byte file required')
        require((self.payload if payload else self.metadata) + len(raw) <= (MAX_PAYLOAD if payload else MAX_METADATA),
            'retention ceiling')
        with (self.path / name).open('xb') as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        self.files[name] = {'bytes': len(raw), 'sha256': sha(raw)}
        if payload: self.payload += len(raw)
        else: self.metadata += len(raw)


def report(state, attempts, failure):
    return seal({'contract_id': ID, 'protocol_complete': failure is None and len(state.results) == len(state.tasks),
        'attempt_count': attempts, 'failure': failure, 'results': deepcopy(state.results), **b.BOUNDARY})


class Capture:
    def __init__(self, contract, panel, *, output, transport, keys, clock_ns=time.monotonic_ns,
            sleeper=time.sleep, utc_now=lambda: datetime.now(timezone.utc).isoformat(), progress=lambda _: None):
        validate_keys(keys)
        self.store = Store(output)
        self.store.write('contract.json', render(contract))
        self.state, self.transport, self.keys = PanelState(panel), transport, keys
        self.clock, self.sleep, self.now, self.progress = clock_ns, sleeper, utc_now, progress
        self.attempts, self.finished, self.last = 0, False, {}
        self.started_ns = self.clock()

    def once(self, request):
        require(self.attempts < MAX_ATTEMPTS, 'capture attempt ceiling')
        require(self.clock() - self.started_ns < MAX_DURATION_NS, 'capture time ceiling')
        require(self.store.payload + daily.MAX_BODY + REPORT_RESERVE <= MAX_PAYLOAD, 'reserve final report space')
        require(self.store.metadata + 10_000_000 <= MAX_METADATA, 'reserve receipt and inventory space')
        provider = request['provider']
        if provider in self.last:
            remaining = self.last[provider] + INTERVAL_NS[provider] - self.clock()
            if remaining > 0: self.sleep(remaining / 1e9)
        started = self.clock()
        require(type(started) is int and started >= 0 and (provider not in self.last
            or started - self.last[provider] >= INTERVAL_NS[provider]), 'request pacing failed')
        prefix = f'{self.attempts:05d}'
        intent = seal({'contract_id': ID, 'ordinal': self.attempts, 'request': request,
            'started_at': self.now(), 'started_monotonic_ns': started})
        self.store.write(prefix + '.intent.json', render(intent))
        self.attempts += 1
        self.last[provider] = started
        reply, error, retained = None, None, False
        try:
            reply = self.transport(request, self.keys)
            validate_reply(reply)
            # Inspect ALL credentials, including decoded duplicate-key strings, before retaining.
            if len(reply['body']) > daily.MAX_BODY:
                error = 'response_too_large'
            elif reply['encoding'] != 'identity':
                error = 'content_encoding'
            elif not all(d.safe_to_retain(reply['body'], key)[0] for key in self.keys.values()):
                error = 'unsafe_or_uninspectable_body'
            else:
                self.store.write(prefix + '.body.json', reply['body'], payload=True)
                retained = True
                if reply['status'] != 200: error = 'http_error'
                elif reply['complete'] is not True: error = 'incomplete_body'
                else:
                    try: self.state.accept(request, reply)
                    except Exception: error = 'invalid_payload_or_chain'
        except Exception:
            error = 'transport_or_retention_error'
            reply = None
        receipt = seal({'contract_id': ID, 'ordinal': self.attempts - 1,
            'intent_sha256': intent['content_sha256'], 'finished_at': self.now(),
            'status': reply['status'] if reply else None, 'complete': reply['complete'] if reply else False,
            'body_bytes': len(reply['body']) if reply else None, 'body_sha256': sha(reply['body']) if reply else None,
            'body_retained': retained, 'error': error})
        self.store.write(prefix + '.receipt.json', render(receipt))
        self.progress({'attempts': self.attempts, 'date': request['trading_date'], 'provider': provider,
            'completed_tasks': len(self.state.results), 'error': error})
        return error

    def run(self):
        require(not self.finished and self.attempts == 0, 'capture cannot restart')
        failure = None
        try:
            while (request := self.state.request()) is not None:
                failure = self.once(request)
                if failure: break
        except BaseException:
            failure = 'interrupted'
            raise
        finally:
            self.finished = True
            result = report(self.state, self.attempts, failure)
            raw_report = render(result)
            require(len(raw_report) <= REPORT_RESERVE, 'bounded final report required')
            self.store.write('report.json', raw_report, payload=True)
            self.store.write('inventory.json', render(seal({'contract_id': ID, 'files': dict(self.store.files)})))
        return result


def verify_archive(path, *, expected_bytes, expected_sha256, expected_inventory_sha256, contract, panel):
    path = Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents))
        and type(expected_bytes) is int and 0 < expected_bytes <= MAX_TOTAL and path.stat().st_size == expected_bytes,
        'original archive size/path differs')
    with path.open('rb') as handle:
        require(hashlib.file_digest(handle, 'sha256').hexdigest() == expected_sha256, 'original archive hash differs')
    state, last, count = PanelState(panel), {}, 0
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = {i.filename for i in infos}
        require(len(names) == len(infos) and len(names) <= MAX_ATTEMPTS * 3 + 3
            and sum(i.file_size for i in infos) <= MAX_TOTAL, 'archive population/byte ceiling')
        payload_bytes = sum(i.file_size for i in infos if i.filename == 'report.json' or i.filename.endswith('.body.json'))
        require(payload_bytes <= MAX_PAYLOAD and sum(i.file_size for i in infos) - payload_bytes <= MAX_METADATA,
            'archive payload/metadata ceiling')
        for info in infos:
            require(re.fullmatch(r'(?:contract|inventory|report)\.json|[0-9]{5}\.(?:intent|receipt|body)\.json', info.filename)
                and not info.is_dir() and stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG)
                and info.file_size <= (REPORT_RESERVE if info.filename == 'report.json' else
                    daily.MAX_BODY if info.filename.endswith('.body.json') else MAX_METADATA), 'unsafe archive member')
        raw = archive.read('inventory.json')
        require(sha(raw) == expected_inventory_sha256, 'independent inventory hash differs')
        inventory = parse(raw)
        d.base.verify_seal(inventory)
        require(set(inventory) == {'contract_id', 'files', 'content_sha256'} and inventory['contract_id'] == ID
            and set(inventory['files']) == names - {'inventory.json'}, 'inventory population differs')
        for name, spec in inventory['files'].items():
            raw = archive.read(name)
            exact(spec, {'bytes': len(raw), 'sha256': sha(raw)}, 'original member bytes differ')
        exact(parse(archive.read('contract.json')), contract, 'capture contract differs')
        while (request := state.request()) is not None:
            require(count < MAX_ATTEMPTS, 'archive attempt ceiling')
            prefix = f'{count:05d}'
            intent, receipt = (parse(archive.read(prefix + '.' + k + '.json')) for k in ('intent', 'receipt'))
            started, provider = intent['started_monotonic_ns'], request['provider']
            require(type(started) is int and started >= 0 and (provider not in last
                or started - last[provider] >= INTERVAL_NS[provider]), 'archive pacing differs')
            last[provider] = started
            begin, end = (datetime.fromisoformat(v) for v in (intent['started_at'], receipt['finished_at']))
            require(begin.tzinfo is not None and end.tzinfo is not None and begin <= end, 'archive clock differs')
            exact(intent, seal({'contract_id': ID, 'ordinal': count, 'request': request,
                'started_at': intent['started_at'], 'started_monotonic_ns': started}), 'archive intent differs')
            raw = archive.read(prefix + '.body.json')
            exact(receipt, seal({'contract_id': ID, 'ordinal': count, 'intent_sha256': intent['content_sha256'],
                'finished_at': receipt['finished_at'], 'status': 200, 'complete': True,
                'body_bytes': len(raw), 'body_sha256': sha(raw), 'body_retained': True, 'error': None}), 'receipt differs')
            state.accept(request, {'status': 200, 'body': raw, 'complete': True, 'encoding': 'identity'})
            count += 1
        require(len(names) == count * 3 + 3, 'extra files after exhaustion')
        exact(parse(archive.read('report.json')), report(state, count, None), 'raw replay report differs')
    return seal({'contract_id': ID, 'protocol_complete': True, 'attempt_count': count,
        'archive_bytes': expected_bytes, 'archive_sha256': expected_sha256,
        'inventory_file_sha256': expected_inventory_sha256, 'completed_tasks': len(state.results),
        'verified_member_count': len(names), **b.BOUNDARY})
