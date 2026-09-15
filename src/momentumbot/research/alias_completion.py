"""Bounded alias completion and dated scanner daily inputs; no policy promotion."""
from copy import deepcopy
from datetime import date, datetime, timezone
import gzip
import hashlib
import math
from pathlib import Path
import re
import stat
import time
import zipfile

from momentumbot.research import identity_coverage as parent
from momentumbot.research import hosted_source_gate as gate
from momentumbot.research.census_payload_evidence import read_archive

c = parent.capture.old
daily = c.daily
require, exact, seal, sha, render, parse = c.require, c.exact, c.seal, c.sha, c.render, c.parse
ID = 'early-pullback-alias-completion-v0.1'
BASE = 'research/data-audits/' + ID
CONTRACT_PATH = 'research/strategy/' + ID + '.json'
WORKFLOW = '.github/workflows/alias-completion.yml'
PARENT = '3397cf7051410d0e39a4a7ba367eb9eef5748768'
REF = 'refs/tags/' + ID + '-consumed'
PANEL_PATH = parent.BASE + '/identity-coverage-panel.json.gz'
PANEL_PIN = {'bytes': 8411562, 'sha256': 'a6bf4689377372db81272d67acc91ea736e173f3b94128e994b24c10af30acf9'}
PANEL_SEAL = 'ea3dc07f5ca5ed03a467691f5f38632cdc1e351807c8fb44e4549215108b30d9'
CONFLICT_PATH = BASE + '/conflict-source-views.json'
SCANNER_PATH = BASE + '/saved-scanner-daily.json.gz'
KEYS = ('ALPACA_API_KEY', 'ALPACA_API_SECRET')
MAX_ATTEMPTS = 170
MAX_PAYLOAD = 48 * 1024 * 1024
MAX_METADATA = 16 * 1024 * 1024
MAX_TOTAL = MAX_PAYLOAD + MAX_METADATA
MAX_DURATION_NS = 15 * 60 * 1_000_000_000
FILES = ('src/momentumbot/research/alias_completion.py', 'scripts/run_alias_completion.py',
    'tests/test_alias_completion.py', WORKFLOW, CONFLICT_PATH, SCANNER_PATH,
    '.github/actions/source-runtime/action.yml', '.github/workflows/ci.yml',
    'requirements-sealed-source-v04.txt', 'scripts/build_causal_scanner_snapshot_v03.py')


def load_panel(root):
    parent.validate_registration(root)
    path = parent._pinned_file(Path(root) / PANEL_PATH, PANEL_PIN)
    value = parse(gzip.decompress(path.read_bytes()))
    c.d.base.verify_seal(value)
    require(value['content_sha256'] == PANEL_SEAL, 'accepted identity panel differs')
    return value


def previous_close(rows, day):
    """Same latest-prior-session rule as the frozen scanner daily adapter."""
    stamps = [daily._stamp(r['t']) for r in rows]
    require(all(a < b for a, b in zip(stamps, stamps[1:])), 'ordered unique daily timestamps required')
    eligible = [r for r in rows if daily._stamp(r['t']).astimezone(daily.ET).date() < date.fromisoformat(day)]
    if not eligible: return None
    latest = max(eligible, key=lambda r: daily._stamp(r['t']))
    value = latest['c']
    return {'timestamp': latest['t'], 'close': float(value)} if type(value) in (int, float) and math.isfinite(value) and value > 0 else None


def prepare_sources(root, capture_zip, progress=lambda _: None):
    """Read original bytes once; retain dated previous closes and conflict views."""
    panel = load_panel(root)
    days, conflicts = [], []
    with parent.CoverageArchive(capture_zip, root) as source:
        for day in panel['days']:
            target = day['trading_date']
            symbols = {r['ticker'] for r in day['membership']}
            rows = {s: [] for s in symbols}
            lineage = {}
            for result in source.daily[target]['roots']:
                entries = source.locations[result['root_sha256']]
                if entries[0][2]['params']['adjustment'] != 'split': continue
                for segment, prefix, request in entries:
                    raw = source.read(segment, prefix + '.body.json')
                    key = sha(raw)
                    lineage[key] = {'segment': segment, 'body_member': prefix + '.body.json',
                        'body_sha256': key, 'root_sha256': request['root_sha256'], 'request_sha256': request['content_sha256']}
                    for symbol, bars in (parse(raw)['bars'] or {}).items():
                        if symbol in rows: rows[symbol].extend({**bar, 'source_body_sha256': key} for bar in bars)
            witnesses = {}
            for symbol, bars in rows.items():
                value = previous_close(bars, target)
                if value is not None:
                    bar = next(r for r in bars if r['t'] == value['timestamp'])
                    witnesses[symbol] = {**value, 'source_body_sha256': bar['source_body_sha256']}
            days.append(seal({'trading_date': target, 'membership_sha256': day['content_sha256'],
                'membership_symbols': sorted(symbols), 'previous_close_by_symbol': {s: v['close'] for s, v in sorted(witnesses.items())},
                'previous_close_witnesses': dict(sorted(witnesses.items())), 'source_members': lineage,
                'unavailable_previous_close_symbols': sorted(symbols - set(witnesses)),
                'adjustment': 'split', 'asof': target, 'source_lookback_calendar_days': 14,
                'scanner_lookback_calendar_days': 21,
                'reuse_basis': 'exhausted 14-day prefix contains latest prior bar; older seven days cannot change that latest observation',
                **parent.BOUNDARY}))
            progress({'date': target, 'previous_closes': len(witnesses), 'missing': len(symbols - set(witnesses))})
        for pair in panel['continuity_pairs']:
            before, after = pair['earlier_date'], pair['later_date']
            for conflict in pair['same_ticker_different_figi']:
                symbol = conflict['ticker']
                transition = {'earlier_ticker': symbol, 'later_ticker': symbol,
                    'identifier_kind': 'distinct_composite_figis',
                    'identifier': conflict['earlier_composite_figi'] + '/' + conflict['later_composite_figi']}
                action_rows = []
                for provider, evidence in panel['actions_by_date'][after].items():
                    for index in evidence['membership_action_row_indices'].get(symbol, []):
                        row = evidence['rows'][index]
                        event_day = row.get('process_date', row.get('execution_date', ''))
                        if before < event_day <= after:
                            action_rows.append({'provider': provider, 'row_index': index,
                                'evidence_sha256': evidence['content_sha256'], 'row': row})
                conflicts.append(seal({'earlier_date': before, 'later_date': after,
                    'conflict': conflict, 'alias_checks': [parent.alias_views(transition, before, after, source.raw_daily_view)],
                    'actions_within_interval': action_rows, 'cross_identifier_merge_permitted': False,
                    'action_match_proves_identity_equivalence': False, **parent.BOUNDARY}))
    return seal({'parent_panel_sha256': PANEL_SEAL, 'source_capture_pin': parent.CAPTURE_PIN,
        'days': days, 'provider_requests': 0, **parent.BOUNDARY}), seal({
        'parent_panel_sha256': PANEL_SEAL, 'source_capture_pin': parent.CAPTURE_PIN,
        'conflicts': conflicts, 'provider_requests': 0, **parent.BOUNDARY})


def request_plan(root):
    original = parse((Path(root) / parent.BASE / 'remaining-alias-plan.json').read_bytes())
    require(sha((Path(root) / parent.BASE / 'remaining-alias-plan.json').read_bytes()) ==
        'a00ce8fc5676149679e766e4f21fae3a5ce5e396179cd84c11212620dbafa512', 'original alias plan differs')
    supplement = parse((Path(root) / CONFLICT_PATH).read_bytes())
    c.d.base.verify_seal(supplement)
    require(supplement['parent_panel_sha256'] == PANEL_SEAL and len(supplement['conflicts']) == 4,
        'fixed conflict supplement required')
    extra = parent.remaining_alias_requests(supplement['conflicts'])
    groups = {}
    for plan in (original, extra):
        for item in plan['roots']:
            key = (item['params']['asof'], item['comparison_date'])
            if key not in groups: groups[key] = deepcopy(item)
            else:
                groups[key]['params']['symbols'] = ','.join(sorted(set(groups[key]['params']['symbols'].split(',')) | set(item['params']['symbols'].split(','))))
    roots = [seal({**{k: v for k, v in value.items() if k != 'content_sha256'},
        'trading_date': value['comparison_date']}) for _, value in sorted(groups.items())]
    require(len(roots) == 17 and sum(len(r['params']['symbols'].split(',')) for r in roots) == 35,
        'fixed 17-root/35-view union differs')
    return roots


def registration(root):
    inherited = parent.validate_registration(root)
    return seal({'contract_id': ID, 'contract_path': CONTRACT_PATH, 'workflow': WORKFLOW,
        'parent_commit': PARENT, 'parent_registration_sha256': inherited['content_sha256'],
        'parent_panel_pin': PANEL_PIN, 'parent_panel_sha256': PANEL_SEAL, 'requests': request_plan(root),
        'file_bindings': {name: {'bytes': (Path(root) / name).stat().st_size, 'sha256': sha((Path(root) / name).read_bytes())} for name in FILES},
        'limits': {'maximum_attempts': MAX_ATTEMPTS, 'maximum_pages_per_root': daily.MAX_PAGES,
            'maximum_body_bytes': daily.MAX_BODY, 'maximum_duration_ns': MAX_DURATION_NS,
            'maximum_payload_bytes': MAX_PAYLOAD, 'maximum_metadata_bytes': MAX_METADATA,
            'minimum_interval_ns': c.INTERVAL_NS['alpaca'], 'retries': 0, 'redirects': 0},
        'authorization': {'user_message': 'Okay go ahead', 'observed_date': '2026-09-15',
            'starts_at': '2026-09-15T00:00:00Z', 'expires_at': '2026-09-22T00:00:00Z',
            'scope': 'one fixed 17-root Alpaca daily capture covering 31 aliases and four diagnosed FIGI view conflicts after exact-code CI',
            'estimated_incremental_api_cost_usd': '0.00', 'maximum_incremental_cost_usd': '10.00',
            'billing_cap_provider_enforced': False, 'metered_purchase_authorized': False,
            'subscription_changes_authorized': False},
        'consumption_ref': REF, 'runtime': gate.d.previous.RUNTIME, 'credential_names': list(KEYS),
        'receipt_and_report_schema': c.ID, 'automatic_original_archive_verification': True,
        'strategy_or_membership_changes': False, **parent.BOUNDARY})


def validate_registration(root):
    value = parse((Path(root) / CONTRACT_PATH).read_bytes())
    exact(value, registration(root), 'alias completion registration differs')
    return value


class AliasPages(daily.DailyPages):
    """Reuse all original daily schema/order/window/cursor guards."""
    def __init__(self, root):
        self._root = deepcopy(root)
        self._symbols = root['params']['symbols'].split(',')
        self._dates = {s: set() for s in self._symbols}
        self._token, self._last = None, None
        self._seen_tokens, self._pages = set(), []
        self._complete = self._failed = False
        self.targets = {}

    def _accept(self, request, response):
        witness = super()._accept(request, response)
        for symbol, bars in (parse(response['body'])['bars'] or {}).items():
            for row in bars:
                if daily._stamp(row['t']).astimezone(daily.ET).date().isoformat() == self._root['trading_date']:
                    self.targets[symbol] = {k: row[k] for k in parent.BAR_FIELDS}
        return witness

    def result(self):
        original = super().result()
        return seal({'root_sha256': self._root['content_sha256'], 'pages': original['pages'],
            'views': [{'symbol': s, 'asof': self._root['params']['asof'], 'target_date': self._root['trading_date'],
                'status': 'captured_bar' if s in self.targets else 'captured_empty', 'bar': self.targets.get(s),
                'source_members': [{'body_sha256': p['body_sha256'], 'request_sha256': p['request_sha256']} for p in self._pages]}
                for s in self._symbols], **parent.BOUNDARY})


class State:
    def __init__(self, roots):
        self.tasks, self.results, self.current, self.failed = deepcopy(roots), [], None, False

    def request(self):
        require(not self.failed, 'alias state failed')
        if len(self.results) == len(self.tasks): return None
        if self.current is None: self.current = AliasPages(self.tasks[len(self.results)])
        return self.current.request()

    def accept(self, request, reply):
        try:
            exact(request, self.request(), 'alias request differs')
            self.current.accept(request, reply)
            if self.current._complete:
                self.results.append(self.current.result())
                self.current = None
        except Exception:
            self.failed = True
            raise


class Store(c.Store):
    def write(self, name, raw, *, payload=False):
        require((self.payload if payload else self.metadata) + len(raw) <= (MAX_PAYLOAD if payload else MAX_METADATA),
            'alias retention ceiling')
        return super().write(name, raw, payload=payload)


class Transport(c.DirectHTTPS):
    def __call__(self, request, keys):
        require(request['provider'] == 'alpaca' and request['url'] == 'https://data.alpaca.markets/v2/stocks/bars',
            'Alpaca daily endpoint only')
        return super().__call__(request, keys)


class Capture(c.Capture):
    def __init__(self, contract, *, output, transport, keys, clock_ns=time.monotonic_ns,
            sleeper=time.sleep, utc_now=lambda: datetime.now(timezone.utc).isoformat(), progress=lambda _: None):
        require(type(keys) is dict and set(keys) == set(KEYS), 'only two Alpaca credentials required')
        # Public unused placeholder satisfies the frozen transport's three-field
        # envelope. No Massive credential is read and its endpoint is forbidden.
        keys = {**keys, 'MASSIVE_API_KEY': 'UNUSED_ALPACA_ONLY'}
        c.validate_keys(keys)
        self.store = Store(output)
        self.store.write('contract.json', render(contract))
        self.state, self.transport, self.keys = State(contract['requests']), transport, keys
        self.clock, self.sleep, self.now, self.progress = clock_ns, sleeper, utc_now, progress
        self.attempts, self.finished, self.last = 0, False, {}
        self.started_ns = self.clock()

    def once(self, request):
        exact(request, self.state.request(), 'fixed next alias request required before transport')
        require(self.attempts < MAX_ATTEMPTS and self.clock() - self.started_ns < MAX_DURATION_NS, 'alias capture budget exhausted')
        require(self.store.payload + daily.MAX_BODY + 1024 * 1024 <= MAX_PAYLOAD
            and self.store.metadata + 1024 * 1024 <= MAX_METADATA, 'alias report reserve exhausted')
        return super().once(request)


def verify_archive(path, metadata, inventory_sha256, contract):
    parent._pinned_file(path, {'bytes': metadata['size_in_bytes'], 'sha256': metadata['digest'][7:]})
    require(0 < metadata['size_in_bytes'] <= MAX_TOTAL, 'bounded capture archive required')
    state, count, last = State(contract['requests']), 0, None
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = {i.filename for i in infos}
        require(len(names) == len(infos) <= MAX_ATTEMPTS * 3 + 3
            and sum(i.file_size for i in infos) <= MAX_TOTAL, 'bounded unique capture members required')
        payload_size = sum(i.file_size for i in infos if i.filename.endswith('.body.json') or i.filename == 'report.json')
        require(payload_size <= MAX_PAYLOAD and sum(i.file_size for i in infos) - payload_size <= MAX_METADATA,
            'capture payload/metadata ceiling')
        for info in infos:
            require(re.fullmatch(r'(?:contract|inventory|report)\.json|[0-9]{5}\.(?:intent|receipt|body)\.json', info.filename)
                and not info.is_dir() and stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG)
                and info.file_size <= (daily.MAX_BODY if info.filename.endswith('.body.json') else MAX_METADATA), 'unsafe capture member')
        raw = archive.read('inventory.json')
        require(sha(raw) == inventory_sha256, 'independent capture inventory differs')
        inventory = parse(raw)
        exact(inventory, seal({'contract_id': c.ID, 'files': {n: {'bytes': len(archive.read(n)), 'sha256': sha(archive.read(n))}
            for n in sorted(names - {'inventory.json'})}}), 'capture inventory differs')
        exact(parse(archive.read('contract.json')), contract, 'captured contract differs')
        while (request := state.request()) is not None:
            require(count < MAX_ATTEMPTS, 'alias archive attempt ceiling')
            prefix = f'{count:05d}'
            intent, receipt = (parse(archive.read(prefix + '.' + k + '.json')) for k in ('intent', 'receipt'))
            started = intent['started_monotonic_ns']
            require(type(started) is int and started >= 0 and (last is None or started - last >= c.INTERVAL_NS['alpaca']), 'archive pacing differs')
            if last is None: first = started
            require(started - first < MAX_DURATION_NS, 'archive duration ceiling')
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
        exact(parse(archive.read('report.json')), c.report(state, count, None), 'original replay report differs')
    return seal({'contract_id': ID, 'protocol_complete': True, 'attempt_count': count,
        'archive_metadata': metadata, 'inventory_sha256': inventory_sha256,
        'views': [v for r in state.results for v in r['views']], 'verified_member_count': len(names), **parent.BOUNDARY})


def preflight(root, env, facts, now, runtime, path, metadata, live_ref):
    contract = validate_registration(root)
    gate.check_launch(contract, env, facts, now)
    gate.check_artifact(metadata, contract, env, 'consumption', env.get('PREFLIGHT_ARTIFACT_ID'), gate.d.previous.PREFLIGHT_LIMIT)
    gate.verify_preflight(read_archive(path, metadata['size_in_bytes'], metadata['digest'][7:]), contract, env, runtime, live_ref, metadata)
    return contract


def capture(root, env, facts, now, runtime, path, metadata, live_ref, *, output, credential_loader, transport, progress):
    contract = preflight(root, env, facts, now, runtime, path, metadata, live_ref)
    require(not Path(output).exists() and not any(p.is_symlink() for p in (Path(output), *Path(output).parents)), 'fresh capture output required')
    return Capture(contract, output=output, keys=credential_loader(), transport=transport, progress=progress).run()


def verify(root, env, facts, now, runtime, path, metadata, live_ref, capture_path, capture_metadata, jobs):
    contract = preflight(root, env, facts, now, runtime, path, metadata, live_ref)
    gate.check_jobs(jobs, env)
    gate.check_artifact(capture_metadata, contract, env, 'capture', env.get('CAPTURE_ARTIFACT_ID'), MAX_TOTAL)
    result = verify_archive(capture_path, capture_metadata, env['CAPTURE_INVENTORY_SHA256'], contract)
    return seal({'contract_id': ID, 'code_commit': env['GITHUB_SHA'], 'run_id': env['GITHUB_RUN_ID'],
        'archive_verification': result, 'hosted_capture_provenance_verified': True,
        'consumption_ref': REF, 'provider_requests_during_verification': 0, **parent.BOUNDARY})


def complete_checks(pairs, new_views):
    """Provider-neutral exact missing-view join; cannot replace saved evidence."""
    missing = {(v['symbol'], v['asof'], v['target_date']) for p in pairs for c0 in p['alias_checks']
        for v in c0['views'] if v['status'] == 'request_not_captured'}
    supplied = {}
    for view in new_views:
        parent.validate_view(view)
        require(view['status'] != 'request_not_captured', 'completed observation required')
        key = (view['symbol'], view['asof'], view['target_date'])
        require(key not in supplied, 'duplicate completed alias view')
        supplied[key] = view
    require(set(supplied) == missing, 'exact missing-view union required')
    out = []
    for pair in pairs:
        c.d.base.verify_seal(pair)
        checks = []
        for check in pair['alias_checks']:
            old = {(v['symbol'], v['asof'], v['target_date']): v for v in check['views']}
            def lookup(symbol, asof, target):
                key = (symbol, asof, target)
                return deepcopy(supplied[key] if old[key]['status'] == 'request_not_captured' else old[key])
            checks.append(parent.alias_views(check, pair['earlier_date'], pair['later_date'], lookup))
        out.append(seal({'earlier_date': pair['earlier_date'], 'later_date': pair['later_date'],
            'source_pair_sha256': pair['content_sha256'], 'alias_checks': checks,
            'all_bidirectional_matches': all(x['bidirectional_match'] for x in checks), **parent.BOUNDARY}))
    return out


def completion(root, verification):
    contract = validate_registration(root)
    c.d.base.verify_seal(verification)
    require(verification['contract_id'] == ID and verification['hosted_capture_provenance_verified'] is True,
        'hosted verification required by composer')
    panel = load_panel(root)
    supplement = parse((Path(root) / CONFLICT_PATH).read_bytes())
    scanner = parse(gzip.decompress((Path(root) / SCANNER_PATH).read_bytes()))
    c.d.base.verify_seal(scanner)
    exact([d['trading_date'] for d in scanner['days']], list(parent.DATES), 'scanner date union differs')
    for original, saved in zip(panel['days'], scanner['days']):
        require(saved['membership_sha256'] == original['content_sha256'], 'scanner dated membership differs')
        exact(saved['membership_symbols'], sorted(r['ticker'] for r in original['membership']), 'scanner membership population differs')
    checks = complete_checks(panel['continuity_pairs'] + supplement['conflicts'], verification['archive_verification']['views'])
    aliases, conflicts = checks[:len(panel['continuity_pairs'])], checks[len(panel['continuity_pairs']):]
    return seal({'contract_id': ID, 'registration_sha256': contract['content_sha256'],
        'hosted_verification_sha256': verification['content_sha256'], 'parent_panel_sha256': PANEL_SEAL,
        'completed_alias_pairs': aliases, 'completed_figi_view_checks': conflicts,
        'alias_mapping_checks_complete': all(p['all_bidirectional_matches'] for p in aliases),
        'distinct_figi_asof_views_consistent': all(p['all_bidirectional_matches'] for p in conflicts),
        'distinct_figis_merged': False, 'membership_changed': False,
        'identity_disposition': 'retain each dated FIGI; cross-identifier history joins are not authorized by bar equality',
        'scanner_daily_file': {'path': SCANNER_PATH, **contract['file_bindings'][SCANNER_PATH]},
        'scanner_previous_closes': sum(len(d['previous_close_by_symbol']) for d in scanner['days']),
        'scanner_missing_previous_closes': {d['trading_date']: d['unavailable_previous_close_symbols'] for d in scanner['days'] if d['unavailable_previous_close_symbols']},
        'remaining_scanner_inputs': ['full-membership split minute rank bars', 'candidate raw minute bars and exact same-time RVOL history',
            'point-in-time SEC float and publication-timed news'],
        'provider_requests_during_composition': 0, **parent.BOUNDARY})
