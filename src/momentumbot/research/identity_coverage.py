"""Bind accepted census/coverage bytes to dated identity and scanner inputs.

Corporate actions are normalization evidence, never an as-known news feed.
Later snapshots can diagnose aliases but cannot mutate an earlier membership.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import io
import math
from pathlib import Path
import zipfile

from momentumbot.identity_continuity import build_cross_date_identity_bridge
from momentumbot.research import coverage_continuation as capture
from momentumbot.research import coverage_continuation_hosted as hosted
from scripts.audit_historical_identity_continuity import (
    extract_symbol_values, resolve_name_change_paths,
)

b = capture.old.b
require, exact, seal, sha, render, parse = b.require, b.exact, b.seal, b.sha, b.render, b.parse
fingerprint = b.fingerprint
ID = 'early-pullback-identity-coverage-v0.1'
BASE = 'research/data-audits/' + ID
CONTRACT_PATH = 'research/strategy/' + ID + '.json'
PARENT = '9dec40ea1b9a2dd77b86faddba08f1fbcfdf5eb1'
DATES = b.DATES
CAPTURE_PIN = {'bytes': 104141996,
    'sha256': '6c694f18857697993ec61caed247cc7cf6f597f604a2ba38373db5cde96156ae',
    'inventory_sha256': '9e53cc5694289306a5cb2e45f5703bdbd6136f9091de488a41822317730e263e'}
HOSTED_SEAL = '5164702cbd6d4f006d9ce0e919a3ab7036b9cb6a169702d3409eb682ffe20903'
COMPLETION_SEAL = '4d57027dc9dde35756dfafbe38b457f6cacae29c41c5e4bba4ce856faf4a555e'
VERIFICATION_PATH = 'research/data-audits/' + capture.ID + '/original-hosted-verification.zip'
VERIFICATION_PIN = {'bytes': 3831,
    'sha256': '7569d2fcaec116af9f4ea974526cf33be41e2a2ee4a2f4251da739ccd3745947'}
COMPLETION_PATH = 'research/data-audits/' + capture.ID + '/completion-verification.json'
BAR_FIELDS = ('o', 'h', 'l', 'c', 'v', 'n', 'vw')
ALIAS_MAX_PAGES = 10
BOUNDARY = {**b.BOUNDARY, 'corporate_actions_are_runtime_news': False,
    'later_identity_evidence_changes_earlier_membership': False}
FILES = ('src/momentumbot/research/identity_coverage.py',
    'scripts/build_identity_coverage.py', 'tests/test_identity_coverage.py',
    'scripts/audit_historical_identity_continuity.py', COMPLETION_PATH, VERIFICATION_PATH)


def _pinned_file(path, pin):
    path = Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)),
        'regular original source required')
    require(path.stat().st_size == pin['bytes'], 'original source size differs')
    with path.open('rb') as handle:
        require(hashlib.file_digest(handle, 'sha256').hexdigest() == pin['sha256'],
            'original source SHA differs')
    return path


class CoverageArchive:
    """Read only the exact independently replayed capture, including its prefix.

    The full hosted protocol replay is reused. Newly consumed members are checked
    against their original inventory; action rows are reconstituted and compared
    with the already verified normalized row commitments.
    """
    def __init__(self, path, root):
        self.closed = False
        self.archives = {}
        self.inventories = {}
        self.locations = defaultdict(list)
        self.action_cache = {}
        self.root = Path(root)
        hosted.validate_registration(root)
        proof = parse((self.root / COMPLETION_PATH).read_bytes())
        capture.old.d.base.verify_seal(proof)
        require(proof['content_sha256'] == COMPLETION_SEAL, 'accepted completion differs')
        p = _pinned_file(self.root / VERIFICATION_PATH, VERIFICATION_PIN)
        with zipfile.ZipFile(p) as z:
            verification = parse(z.read('hosted-verification.json'))
        capture.old.d.base.verify_seal(verification)
        require(verification['content_sha256'] == HOSTED_SEAL
            and verification['hosted_capture_provenance_verified'] is True,
            'accepted hosted verification differs')
        _pinned_file(path, CAPTURE_PIN)
        try:
            outer = zipfile.ZipFile(path)
            self._admit('suffix', outer, CAPTURE_PIN['inventory_sha256'], 4273)
            raw = self.read('suffix', 'prefix.zip')
            exact({'bytes': len(raw), 'sha256': sha(raw)},
                {k: capture.PREFIX_PIN[k] for k in ('bytes', 'sha256')}, 'embedded original prefix differs')
            self._admit('prefix', zipfile.ZipFile(io.BytesIO(raw)), capture.PREFIX_PIN['inventory_sha256'], 144)
            exact(parse(self.read('suffix', 'contract.json')), hosted.validate_registration(root), 'captured contract differs')
            self.report = parse(self.read('suffix', 'report.json'))
            capture.old.d.base.verify_seal(self.report)
            require(self.report['content_sha256'] == proof['report_content_sha256']
                and self.report['protocol_complete'] is True and self.report['failure'] is None,
                'complete original report required')
            expected_tasks = [(day, kind) for day in DATES for kind in ('daily', 'identity', 'identity')]
            exact([(r['date'], r['kind']) for r in self.report['results']], expected_tasks, 'exact dated task union required')
            self.daily = {r['date']: r['result'] for r in self.report['results'] if r['kind'] == 'daily'}
            self.identities = {r['result']['root_sha256']: r['result'] for r in self.report['results'] if r['kind'] == 'identity'}
            require(len(self.daily) == 30 and len(self.identities) == 60, 'duplicate or missing source task')
            for segment, count in (('prefix', 47), ('suffix', 1423)):
                for ordinal in range(count):
                    prefix = f'{ordinal:05d}'
                    intent = parse(self.read(segment, prefix + '.intent.json'))
                    request = intent['request']
                    self.locations[request['root_sha256']].append((segment, prefix, request))
            expected_roots = set(self.identities)
            for result in self.daily.values():
                capture.old.d.base.verify_seal(result)
                exact(fingerprint(result['coverage']), result['coverage_sha256'], 'original coverage seal differs')
                expected_roots.update(r['root_sha256'] for r in result['roots'])
            require(set(self.locations) == expected_roots, 'source root population differs')
        except BaseException:
            self.close()
            raise

    def _admit(self, segment, archive, expected_inventory, count):
        self.archives[segment] = archive
        names = archive.namelist()
        require(len(names) == len(set(names)) == count, 'original archive population differs')
        raw = archive.read('inventory.json')
        require(sha(raw) == expected_inventory, 'original inventory differs')
        inventory = parse(raw)
        capture.old.d.base.verify_seal(inventory)
        require(set(inventory['files']) == set(names) - {'inventory.json'}, 'inventory members differ')
        self.inventories[segment] = inventory['files']

    def read(self, segment, name):
        require(not self.closed, 'source archive closed')
        raw = self.archives[segment].read(name)
        exact(self.inventories[segment][name], {'bytes': len(raw), 'sha256': sha(raw)}, 'original member differs')
        return raw

    def actions(self, day, provider):
        require(day in DATES and provider in ('alpaca', 'massive'), 'fixed action source required')
        root = capture.old.daily.identity_requests(day)[0 if provider == 'alpaca' else 1]
        key = root['content_sha256']
        if key not in self.action_cache:
            state = capture.ActionPages(root)
            lineage = []
            for segment, prefix, request in self.locations[key]:
                raw = self.read(segment, prefix + '.body.json')
                state.accept(request, {'status': 200, 'body': raw, 'complete': True, 'encoding': 'identity'})
                lineage.append({'segment': segment, 'body_member': prefix + '.body.json',
                    'body_sha256': sha(raw), 'request_sha256': request['content_sha256'], 'page': request['page']})
            result = state.result()
            rows = result.pop('rows')
            result.pop('content_sha256')
            exact(seal({**result, 'row_count': len(rows), 'rows_sha256': fingerprint(rows)}),
                self.identities[key], 'normalized action source differs')
            self.action_cache[key] = {'root': root, 'rows': rows, 'lineage': lineage,
                'source_result': deepcopy(self.identities[key])}
        return deepcopy(self.action_cache[key])

    def raw_daily_view(self, symbol, asof, target):
        """Source lookup, not a synthetic bar or a provider request.

        A captured empty observation is terminal evidence. Only an uncaptured
        query scope becomes a remaining request. An asof view cannot be relabeled.
        """
        require(asof in DATES and target in DATES and type(symbol) is str and bool(symbol), 'fixed alias view required')
        matching = []
        for result in self.daily[asof]['roots']:
            entries = self.locations[result['root_sha256']]
            request = entries[0][2]
            params = request['params']
            if params['adjustment'] == 'raw' and symbol in params['symbols'].split(','):
                # Existing 14-day requests end after their target session. Future
                # comparison dates cannot be claimed from that earlier request.
                begin = date.fromisoformat(params['start'][:10])
                if begin <= date.fromisoformat(target) <= date.fromisoformat(asof):
                    matching.append(entries)
        require(len(matching) <= 1, 'ambiguous captured alias source')
        base = {'symbol': symbol, 'asof': asof, 'target_date': target}
        if not matching:
            return {**base, 'status': 'request_not_captured', 'bar': None, 'source_members': []}
        bars, lineage = [], []
        for segment, prefix, request in matching[0]:
            raw = self.read(segment, prefix + '.body.json')
            payload = parse(raw)
            for row in (payload['bars'] or {}).get(symbol, []):
                if capture.old.daily._stamp(row['t']).astimezone(capture.old.daily.ET).date().isoformat() == target:
                    bars.append({k: row[k] for k in BAR_FIELDS})
            lineage.append({'segment': segment, 'body_member': prefix + '.body.json',
                'body_sha256': sha(raw), 'request_sha256': request['content_sha256']})
        require(len(bars) <= 1, 'multiple alias comparison bars')
        return {**base, 'status': 'captured_bar' if bars else 'captured_empty',
            'bar': bars[0] if bars else None, 'source_members': lineage}

    def close(self):
        for archive in self.archives.values(): archive.close()
        self.closed = True

    def __enter__(self): return self
    def __exit__(self, *args): self.close()


def action_evidence(source, membership, day):
    """Preserve all rows and link relevance without asserting issuer continuity."""
    require(day in DATES, 'fixed action date required')
    root = source['root']
    require(root in capture.old.daily.identity_requests(day), 'wrong action window or provider')
    result = source['source_result']
    capture.old.d.base.verify_seal(result)
    exact(result['root_sha256'], root['content_sha256'], 'action root commitment differs')
    exact(result['rows_sha256'], fingerprint(source['rows']), 'action rows commitment differs')
    require(result['row_count'] == len(source['rows']), 'action row population differs')
    exact([(p['body_sha256'], p['request_sha256']) for p in result['pages']],
        [(p['body_sha256'], p['request_sha256']) for p in source['lineage']], 'action lineage differs')
    symbols = {row['ticker'] for row in membership}
    matches = defaultdict(list)
    unresolved = []
    for index, row in enumerate(source['rows']):
        found = extract_symbol_values(row)
        for symbol in sorted({s['symbol'] for s in found} & symbols): matches[symbol].append(index)
        if not found: unresolved.append(index)
    return seal({'trading_date': day, 'provider': root['provider'],
        'source_result_sha256': result['content_sha256'], 'root': deepcopy(root),
        'rows': deepcopy(source['rows']), 'lineage': deepcopy(source['lineage']),
        'membership_action_row_indices': dict(sorted(matches.items())),
        'rows_without_parsable_symbol': unresolved, 'as_known_historical_feed': False,
        'historical_adjustment_factor_applied': False, 'symbol_match_proves_same_security': False})


def bind_day(rows, day, coverage):
    """Run the existing metadata/coverage/identity rules; no new exclusions."""
    capture.old.d.base.verify_seal(coverage)
    result = b.bind_coverage(rows, day, coverage['coverage'], expected_coverage_sha256=coverage['coverage_sha256'])
    provisional = [r for r in result['decisions'] if r['included']]
    identifiers = defaultdict(list)
    for row in result['membership']:
        identifiers[(row['identity_identifier_kind'], row['identity_identifier'])].append(row['ticker'])
    collisions = [{'kind': key[0], 'identifier': key[1], 'tickers': tickers}
        for key, tickers in sorted(identifiers.items()) if len(tickers) > 1]
    return seal({'contract_id': ID, 'trading_date': day,
        'reference_sha256': result['reference_sha256'], 'coverage_result_sha256': coverage['content_sha256'],
        'coverage_sha256': result['coverage_sha256'], 'original_bridge_result_sha256': result['content_sha256'],
        'reference_row_count': len(rows), 'ticker_disposition_count': len(result['decisions']),
        'disposition_counts': dict(sorted(Counter(r['reason'] for r in result['decisions']).items())),
        'provisional_membership': provisional, 'membership': result['membership'],
        'identity_quarantine': result['identity_statuses']['quarantined'],
        'identity_kind_counts': dict(sorted(Counter(r['identifier_kind'] for r in result['identity_statuses']['accepted']).items())),
        'duplicate_identifier_groups': collisions,
        'coverage_failures': {s: r for s, r in coverage['coverage']['records'].items() if not r['coverage_pass']},
        'same_date_membership_recomputed': True, **BOUNDARY})


def validate_view(view):
    require(type(view) is dict and set(view) == {'symbol', 'asof', 'target_date', 'status', 'bar', 'source_members'},
        'exact alias view schema required')
    require(type(view['symbol']) is str and 0 < len(view['symbol']) <= 64
        and ',' not in view['symbol'] and not any(c.isspace() for c in view['symbol'])
        and view['asof'] in DATES and view['target_date'] in DATES, 'fixed alias view scope required')
    require(view['status'] in ('request_not_captured', 'captured_empty', 'captured_bar')
        and type(view['source_members']) is list, 'explicit alias source status required')
    require(bool(view['source_members']) == (view['status'] != 'request_not_captured'), 'alias source lineage required')
    if view['status'] != 'captured_bar':
        require(view['bar'] is None, 'absent alias observation cannot carry a bar')
        return
    require(type(view['bar']) is dict and set(view['bar']) == set(BAR_FIELDS), 'exact captured daily comparison fields required')
    for key in BAR_FIELDS:
        value = view['bar'][key]
        require(type(value) in (int, float) and math.isfinite(value) and value >= 0, 'finite nonnegative alias bar fields required')


def compare_views(first, second):
    for view in (first, second): validate_view(view)
    require(first['target_date'] == second['target_date'], 'alias comparison target differs')
    if any(v['status'] == 'request_not_captured' for v in (first, second)):
        return {'match': False, 'status': 'missing_source_query'}
    if any(v['status'] == 'captured_empty' for v in (first, second)):
        return {'match': False, 'status': 'captured_empty_bar'}
    for key in BAR_FIELDS:
        a, c = first['bar'][key], second['bar'][key]
        if not math.isclose(a, c, rel_tol=1e-12, abs_tol=1e-12):
            return {'match': False, 'status': key + '_mismatch'}
    return {'match': True, 'status': 'exact_bar_match'}


def alias_views(transition, earlier, later, lookup):
    require(earlier in DATES and later in DATES and earlier < later, 'ordered fixed alias dates required')
    old, new = transition['earlier_ticker'], transition['later_ticker']
    queries = ((old, earlier, earlier), (new, later, earlier), (old, earlier, later), (new, later, later))
    views = []
    for symbol, asof, target in queries:
        view = lookup(symbol, asof, target)
        require(view['symbol'] == symbol and view['asof'] == asof and view['target_date'] == target,
            'alias view scope changed')
        views.append(view)
    early, late = compare_views(*views[:2]), compare_views(*views[2:])
    return {'identifier_kind': transition['identifier_kind'], 'identifier': transition['identifier'],
        'earlier_ticker': old, 'later_ticker': new, 'views': views,
        'earlier_date_comparison': early, 'later_date_comparison': late,
        'bidirectional_match': early['match'] and late['match']}


def continuity_pair(earlier, later, actions, lookup):
    for packet in (earlier, later, actions): capture.old.d.base.verify_seal(packet)
    before, after = earlier['trading_date'], later['trading_date']
    require(before in DATES and after in DATES and DATES.index(after) == DATES.index(before) + 1,
        'adjacent registered source dates required')
    require(earlier['contract_id'] == later['contract_id'] == ID
        and actions['trading_date'] == after and actions['provider'] == 'alpaca'
        and actions['root'] == capture.old.daily.identity_requests(after)[0], 'dated continuity inputs differ')
    bridge = build_cross_date_identity_bridge(earlier['provisional_membership'], later['provisional_membership'],
        earlier_date=before, later_date=after)
    changed = [r for r in bridge['transitions'] if r['ticker_changed']]
    aliases = [alias_views(t, before, after, lookup) for t in changed]
    paths = resolve_name_change_paths(changed, actions['rows'], earlier_date=date.fromisoformat(before),
        later_date=date.fromisoformat(after), lookback_days=120, alias_records=aliases)
    return seal({'earlier_date': before, 'later_date': after,
        'earlier_membership_sha256': earlier['content_sha256'], 'later_membership_sha256': later['content_sha256'],
        'action_evidence_sha256': actions['content_sha256'],
        'original_bridge_sha256': bridge['bridge_sha256'], 'summary': bridge['summary'],
        'changed_transitions': changed, 'same_ticker_different_figi': bridge['same_ticker_different_figi'],
        'alias_checks': aliases, 'name_change_resolution': paths,
        'retrospective_normalization_evidence_only': True, **BOUNDARY})


def remaining_alias_requests(pairs):
    """Only uncaptured views, grouped without changing symbol/asof semantics."""
    groups = defaultdict(set)
    for pair in pairs:
        capture.old.d.base.verify_seal(pair)
        require(pair['earlier_date'] in DATES and pair['later_date'] in DATES
            and DATES.index(pair['later_date']) == DATES.index(pair['earlier_date']) + 1,
            'adjacent registered alias plan dates required')
        for check in pair['alias_checks']:
            expected = alias_views(check, pair['earlier_date'], pair['later_date'],
                lambda symbol, asof, target: next(v for v in check['views']
                    if (v['symbol'], v['asof'], v['target_date']) == (symbol, asof, target)))
            exact(check, expected, 'alias plan evidence differs')
            for view in check['views']:
                if view['status'] == 'request_not_captured':
                    groups[(view['asof'], view['target_date'])].add(view['symbol'])
    roots = []
    stamp = lambda d: datetime.combine(d, time(), timezone.utc).isoformat()
    for (asof, target), symbols in sorted(groups.items()):
        ordered = sorted(symbols)
        day = date.fromisoformat(target)
        for offset in range(0, len(ordered), 250):
            roots.append(seal({'provider': 'alpaca', 'method': 'GET',
                'url': 'https://data.alpaca.markets/v2/stocks/bars', 'kind': 'identity_alias_daily_view',
                'comparison_date': target, 'params': {'symbols': ','.join(ordered[offset:offset + 250]),
                    'timeframe': '1Day', 'start': stamp(day - timedelta(days=7)),
                    'end': stamp(day + timedelta(days=1)), 'feed': 'sip', 'adjustment': 'raw',
                    'asof': asof, 'limit': 10000, 'sort': 'asc'}}))
    return seal({'contract_id': ID, 'roots': roots, 'initial_request_count': len(roots),
        'maximum_pages_per_root': ALIAS_MAX_PAGES,
        'maximum_requests_if_separately_captured': len(roots) * ALIAS_MAX_PAGES,
        'missing_view_count': sum(len(v) for v in groups.values()),
        'captured_empty_or_mismatched_views_not_retried': True,
        'authorized_provider_calls_now': 0, 'automatic_retry': False, **BOUNDARY})


def registration(root):
    inherited = hosted.validate_registration(root)
    return seal({'contract_id': ID, 'parent_commit': PARENT,
        'question': 'Bind complete captured daily coverage and dated identity/action evidence into the unchanged scanner-source handoff.',
        'parent_registration_sha256': inherited['content_sha256'],
        'selected_dates': list(DATES), 'capture_pin': CAPTURE_PIN, 'census_pin': b.ARCHIVE_PIN,
        'hosted_verification_sha256': HOSTED_SEAL, 'completion_verification_sha256': COMPLETION_SEAL,
        'file_bindings': {p: {'bytes': (Path(root) / p).stat().st_size,
            'sha256': sha((Path(root) / p).read_bytes())} for p in FILES},
        'same_date_rule': 'unchanged classifier, then post-coverage FIGI/unique-CIK resolution; retain exact quarantine',
        'cross_date_rule': 'adjacent fixed dates; unchanged identity bridge and name-change resolver; four original raw/asof alias views',
        'alias_comparison': {'fields': list(BAR_FIELDS), 'relative_tolerance': 1e-12, 'absolute_tolerance': 1e-12},
        'source_reuse': 'exact hosted-replayed ZIPs; no repeat full daily protocol replay',
        'changes_strategy_or_risk': False, **BOUNDARY})


def validate_registration(root):
    value = parse((Path(root) / CONTRACT_PATH).read_bytes())
    exact(value, registration(root), 'identity/coverage registration differs')
    return value


def build_panel(census_path, capture_path, root, progress=lambda _: None):
    contract = validate_registration(root)
    days, actions, pairs = [], {}, []
    with b.CensusArchive(census_path, root) as census, CoverageArchive(capture_path, root) as source:
        for day in DATES:
            result = bind_day(census.day(day), day, source.daily[day])
            sources = {provider: action_evidence(source.actions(day, provider), result['membership'], day)
                for provider in ('alpaca', 'massive')}
            days.append(result)
            actions[day] = sources
            if len(days) > 1:
                pairs.append(continuity_pair(days[-2], result, sources['alpaca'], source.raw_daily_view))
            progress({'date': day, 'membership': len(result['membership']),
                'identity_quarantine': len(result['identity_quarantine']), 'coverage_failures': len(result['coverage_failures'])})
    plan = remaining_alias_requests(pairs)
    return seal({'contract_id': ID, 'registration_sha256': contract['content_sha256'],
        'source_bindings': {'census': b.ARCHIVE_PIN, 'coverage_capture': CAPTURE_PIN,
            'hosted_verification_sha256': HOSTED_SEAL},
        'selected_dates': list(DATES), 'days': days, 'actions_by_date': actions,
        'continuity_pairs': pairs, 'remaining_alias_plan': plan,
        'same_date_membership_and_coverage_bound': True, 'provider_requests': 0,
        'remaining_scanner_inputs': ['remaining alias views and explicit identity conflicts',
            'split previous closes and full-membership split minute rank bars',
            'candidate raw minutes and exact same-time RVOL history',
            'point-in-time SEC float and publication-timed news'], **BOUNDARY})


def summary(panel):
    capture.old.d.base.verify_seal(panel)
    days, pairs = panel['days'], panel['continuity_pairs']
    totals = {'source_dates': len(days), 'membership_ticker_date_records': sum(len(d['membership']) for d in days),
        'identity_quarantines': sum(len(d['identity_quarantine']) for d in days),
        'coverage_failures': sum(len(d['coverage_failures']) for d in days),
        'changed_ticker_transitions': sum(len(p['changed_transitions']) for p in pairs),
        'same_ticker_different_figi': sum(len(p['same_ticker_different_figi']) for p in pairs),
        'duplicate_identifier_groups': sum(len(d['duplicate_identifier_groups']) for d in days),
        'reused_alias_views': sum(v['status'] != 'request_not_captured' for p in pairs for c in p['alias_checks'] for v in c['views']),
        'bidirectional_alias_matches': sum(c['bidirectional_match'] for p in pairs for c in p['alias_checks']),
        'remaining_alias_views': panel['remaining_alias_plan']['missing_view_count'],
        'remaining_alias_request_roots': panel['remaining_alias_plan']['initial_request_count']}
    return seal({'contract_id': ID, 'panel_sha256': panel['content_sha256'],
        'registration_sha256': panel['registration_sha256'], 'totals': totals,
        'dates': [{'date': d['trading_date'], 'membership': len(d['membership']),
            'identity_kind_counts': d['identity_kind_counts'], 'identity_quarantine': d['identity_quarantine'],
            'coverage_failures': d['coverage_failures']} for d in days],
        'next_task': panel['remaining_scanner_inputs'], 'provider_requests': 0, **BOUNDARY})


def verify_saved(panel, census_path, capture_path, root, progress=lambda _: None):
    exact(panel, build_panel(census_path, capture_path, root, progress), 'source-derived panel differs')
    return summary(panel)
