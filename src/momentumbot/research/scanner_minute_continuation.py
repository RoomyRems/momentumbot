"""Per-symbol minute ordering repair and saved-response continuation."""
from copy import deepcopy
from pathlib import Path
from datetime import datetime
import io
import re
import stat
import zipfile

from momentumbot.research import scanner_minutes as old

c, daily, gate = old.c, old.daily, old.gate
require, exact, seal, sha, render, parse = old.require, old.exact, old.seal, old.sha, old.render, old.parse
ID = 'early-pullback-scanner-minutes-v0.2'
BASE = 'research/data-audits/' + ID
CONTRACT_PATH = 'research/strategy/' + ID + '.json'
WORKFLOW = '.github/workflows/scanner-minute-continuation.yml'
PARENT = 'd8c9e768bf13939b321bfc2ef81be7458ae239c9'
REF = 'refs/tags/' + ID + '-consumed'
PREFIX_PATH = BASE + '/original-prefix.zip'
PREFIX_PARTS = (PREFIX_PATH + '.part000', PREFIX_PATH + '.part001')
PREFIX_PIN = {'bytes': 13788429, 'sha256': '6f18fbeff5f329b26c1eff6cb7dc188ceb5c7340abec200047456f53350fb2ba'}
PREFIX_INVENTORY = '5f7d94fd40b8b0d9431567d8aba91c05e6e9de570124276d3d1751a81b948481'
PREFIX_ATTEMPTS = 87
PREFIX_ROOTS = 86
MAX_ATTEMPTS = old.MAX_ATTEMPTS - PREFIX_ATTEMPTS
MAX_PAYLOAD = c.MAX_PAYLOAD - 64181498
MAX_METADATA = c.MAX_METADATA - 1337643
MAX_TOTAL, KEYS = MAX_PAYLOAD + MAX_METADATA, old.KEYS
FILES = ('src/momentumbot/research/scanner_minute_continuation.py', 'scripts/hosted_scanner_source_cli.py',
    'scripts/run_scanner_minute_continuation.py', 'tests/test_scanner_minute_continuation.py', WORKFLOW,
    *PREFIX_PARTS, old.BASE + '/hosted-terminal-metadata.json', '.github/actions/source-runtime/action.yml',
    '.github/workflows/ci.yml', 'requirements-sealed-source-v04.txt')


class MinutePages(old.MinutePages):
    """Mapping may reorder symbols between pages; each symbol stays monotonic."""
    def __init__(self, root):
        super().__init__(root)
        self.symbol_last = {}

    def _accept(self, request, reply):
        # Do not relax within-symbol order, duplicates, schema, windows, cursor
        # exhaustion, requested population, transport or byte/page limits.
        previous = dict(self.symbol_last)
        last = self.last
        self.last = None  # JSON symbol keys do not define a cross-page timeline.
        try:
            bars = parse(reply['body']).get('bars') or {}
            for symbol, rows in bars.items():
                if rows and symbol in previous:
                    require(daily._stamp(rows[0]['t']) > previous[symbol], 'duplicate or regressing minute for symbol')
            witness = super()._accept(request, reply)
            self.symbol_last.update({s: daily._stamp(rows[-1]['t']) for s, rows in bars.items() if rows})
            return witness
        except Exception:
            self.last = last
            raise


class State(old.State):
    def request(self):
        require(not self.failed, 'minute continuation state failed')
        if len(self.results) == len(self.tasks): return None
        if self.current is None: self.current = MinutePages(self.tasks[len(self.results)])
        return self.current.request()


def replay_prefix(root):
    """Exact original failure, then repaired replay; no repeated provider calls."""
    contract = old.validate_registration(root)
    metadata = parse((Path(root) / old.BASE / 'hosted-terminal-metadata.json').read_bytes())
    require(metadata['run']['id'] == 34980869608 and metadata['run']['head_sha'] == PARENT
        and metadata['run']['conclusion'] == 'failure', 'original failed run differs')
    gate.d.check_ci(metadata['ci'], metadata['ci_jobs'], {'GITHUB_SHA': PARENT})
    gate.check_ref(metadata['consumed_ref'], contract, {'GITHUB_SHA': PARENT})
    artifact = next(a for a in metadata['artifacts'] if a['id'] == 10401713219)
    gate.check_artifact(artifact, contract, {'GITHUB_SHA': PARENT, 'GITHUB_RUN_ID': '34980869608'},
        'capture', '10401713219', MAX_TOTAL)
    exact({'bytes': artifact['size_in_bytes'], 'sha256': artifact['digest'][7:]}, PREFIX_PIN, 'prefix provenance differs')
    parts = [Path(root) / name for name in PREFIX_PARTS]
    require(all(p.is_file() and not any(x.is_symlink() for x in (p, *p.parents)) for p in parts), 'regular prefix parts required')
    raw_prefix = b''.join(p.read_bytes() for p in parts)
    exact({'bytes': len(raw_prefix), 'sha256': sha(raw_prefix)}, PREFIX_PIN, 'reassembled original ZIP differs')
    original, repaired = old.State(contract['requests']), State(contract['requests'])
    with zipfile.ZipFile(io.BytesIO(raw_prefix)) as z:
        require(len(z.namelist()) == len(set(z.namelist())) == 264, 'prefix population differs')
        raw = z.read('inventory.json')
        require(sha(raw) == PREFIX_INVENTORY, 'prefix inventory differs')
        exact(parse(raw), seal({'contract_id': c.ID, 'files': {n: {'bytes': len(z.read(n)), 'sha256': sha(z.read(n))}
            for n in sorted(z.namelist()) if n != 'inventory.json'}}), 'prefix member bytes differ')
        exact(parse(z.read('contract.json')), contract, 'original prefix contract differs')
        last = None
        for i in range(PREFIX_ATTEMPTS):
            prefix = f'{i:05d}'
            intent, receipt = (parse(z.read(prefix + '.' + k + '.json')) for k in ('intent', 'receipt'))
            request = repaired.request()
            exact(intent['request'], request, 'prefix request sequence differs')
            c.d.base.verify_seal(intent)
            started = intent['started_monotonic_ns']
            require(type(started) is int and started >= 0 and (last is None or started-last >= c.INTERVAL_NS['alpaca']), 'prefix pacing differs')
            last = started
            body = z.read(prefix + '.body.json')
            exact(receipt, seal({'contract_id': c.ID, 'ordinal': i, 'intent_sha256': intent['content_sha256'],
                'finished_at': receipt['finished_at'], 'status': 200, 'complete': True, 'body_bytes': len(body),
                'body_sha256': sha(body), 'body_retained': True, 'error': 'invalid_payload_or_chain' if i == 86 else None}),
                'prefix receipt differs')
            response = {'status': 200, 'body': body, 'complete': True, 'encoding': 'identity'}
            if i < 86: original.accept(request, response)
            else:
                try: original.accept(request, response)
                except ValueError as error: require(str(error) == 'duplicate or regressing minute', 'different original failure')
                else: raise ValueError('original rejection not reproduced')
            repaired.accept(request, response)
        exact(parse(z.read('report.json')), c.report(original, 87, 'invalid_payload_or_chain'), 'original failure report differs')
        exact(repaired.results[:85], original.results, 'completed prefix changed')
        require(len(repaired.results) == PREFIX_ROOTS and repaired.current is None, 'repaired continuation point differs')
    return repaired


def registration(root):
    inherited = old.validate_registration(root)
    return seal({'contract_id': ID, 'contract_path': CONTRACT_PATH, 'workflow': WORKFLOW, 'parent_commit': PARENT,
        'parent_registration_sha256': inherited['content_sha256'], 'prefix_pin': PREFIX_PIN,
        'reused_attempts': PREFIX_ATTEMPTS, 'reused_completed_roots': PREFIX_ROOTS,
        'requests': inherited['requests'][PREFIX_ROOTS:], 'combined_maximum_attempts': old.MAX_ATTEMPTS,
        'limits': {**inherited['limits'], 'maximum_attempts': MAX_ATTEMPTS,
            'maximum_payload_bytes': MAX_PAYLOAD, 'maximum_metadata_bytes': MAX_METADATA},
        'file_bindings': {n: {'bytes': (Path(root) / n).stat().st_size, 'sha256': sha((Path(root) / n).read_bytes())} for n in FILES},
        'authorization': {**inherited['authorization'], 'scope': 'reuse all 87 original responses and capture only the remaining 604 fixed roots; no retry of original requests'},
        'runtime': inherited['runtime'], 'consumption_ref': REF, 'credential_names': list(KEYS),
        'receipt_and_report_schema': c.ID, 'ordering_change': 'strict time order per requested symbol across pages; no global cross-symbol order assumption',
        **old.parent.parent.BOUNDARY})


def validate_registration(root):
    value = parse((Path(root) / CONTRACT_PATH).read_bytes())
    exact(value, registration(root), 'minute continuation registration differs')
    return value


class Capture(old.Capture):
    def __init__(self, contract, **kwargs):
        super().__init__(contract, **kwargs)
        self.state = State(contract['requests'])

    def once(self, request):
        require(self.attempts < MAX_ATTEMPTS, 'combined remaining attempt ceiling')
        require(self.store.payload + daily.MAX_BODY + c.REPORT_RESERVE <= MAX_PAYLOAD
            and self.store.metadata + 10000000 <= MAX_METADATA, 'combined retention reserve')
        return super().once(request)


Transport = old.Transport

def verify_archive(path, metadata, inventory_sha256, contract):
    """Stream original members through the minute parser; never retain all bars."""
    old.parent.parent._pinned_file(path, {'bytes': metadata['size_in_bytes'], 'sha256': metadata['digest'][7:]})
    require(0 < metadata['size_in_bytes'] <= MAX_TOTAL, 'bounded original archive required')
    state, count, last, first = State(contract['requests']), 0, None, None
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = {i.filename for i in infos}
        require(len(names) == len(infos) <= MAX_ATTEMPTS * 3 + 3 and sum(i.file_size for i in infos) <= MAX_TOTAL,
            'bounded unique archive members required')
        payload_bytes = sum(i.file_size for i in infos if i.filename.endswith('.body.json') or i.filename == 'report.json')
        require(payload_bytes <= MAX_PAYLOAD and sum(i.file_size for i in infos) - payload_bytes <= MAX_METADATA,
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
        'root_summaries': state.results, 'provider_requests': 0, **old.parent.parent.BOUNDARY})


def preflight(root, env, facts, now, runtime, path, metadata, live_ref):
    contract = validate_registration(root)
    gate.check_launch(contract, env, facts, now)
    gate.verify_preflight(old.parent.read_archive(path, metadata['size_in_bytes'], metadata['digest'][7:]),
        contract, env, runtime, live_ref, metadata)
    return contract


def capture(root, env, facts, now, runtime, path, metadata, live_ref, *, output, credential_loader, transport, progress):
    contract = preflight(root, env, facts, now, runtime, path, metadata, live_ref)
    replay_prefix(root)
    require(not Path(output).exists() and not any(p.is_symlink() for p in (Path(output), *Path(output).parents)), 'fresh output required')
    return Capture(contract, output=output, keys=credential_loader(), transport=transport, progress=progress).run()


def verify(root, env, facts, now, runtime, path, metadata, live_ref, capture_path, capture_metadata, jobs):
    contract = preflight(root, env, facts, now, runtime, path, metadata, live_ref)
    gate.check_jobs(jobs, env)
    gate.check_artifact(capture_metadata, contract, env, 'capture', env['CAPTURE_ARTIFACT_ID'], MAX_TOTAL)
    prefix = replay_prefix(root)
    result = verify_archive(capture_path, capture_metadata, env['CAPTURE_INVENTORY_SHA256'], contract)
    roots = prefix.results + result['root_summaries']
    exact([r['root_sha256'] for r in roots], [r['content_sha256'] for r in old.validate_registration(root)['requests']],
        'combined original root union differs')
    return seal({'contract_id': ID, 'code_commit': env['GITHUB_SHA'], 'run_id': env['GITHUB_RUN_ID'],
        'archive_verification': result, 'hosted_capture_provenance_verified': True, 'prefix_pin': PREFIX_PIN,
        'reused_attempts': PREFIX_ATTEMPTS, 'total_attempts': PREFIX_ATTEMPTS + result['attempt_count'],
        'completed_roots': len(roots), 'total_bar_count': sum(r['bar_count'] for r in roots),
        'total_symbol_dates': sum(len(r['symbol_bar_counts']) for r in roots),
        'consumption_ref': REF, 'provider_requests_during_verification': 0, **old.parent.parent.BOUNDARY})
