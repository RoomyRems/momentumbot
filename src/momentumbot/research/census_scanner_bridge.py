"""Frozen census -> reference/coverage handoff, without market or outcome inputs.

Reuse the accepted hosted protocol replay by requiring its exact ZIP bytes.
Reference identity is provisional; coverage and 120-day continuity are separate.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
import hashlib
from pathlib import Path
import zipfile

from momentumbot.historical_universe import classify_ticker_group, historical_universe_v0_1_manifest
from momentumbot.identity_continuity import build_date_identity_statuses
from momentumbot.identity_resolved_universe import resolve_identity_membership
from momentumbot.providers.massive import normalize_reference_tickers, reference_membership_identity
from momentumbot.research import census_capture_hosted as parent

ID = 'early-pullback-census-scanner-bridge-v0.1'
PARENT = '21af3cd11134f9cd581d1200d8a2fe697adaa589'
BASE = 'research/data-audits/' + ID
CONTRACT_PATH = 'research/strategy/' + ID + '.json'
DATES = parent.legacy.DATES
require, exact, seal, sha = parent.require, parent.exact, parent.seal, parent.sha
fingerprint, render, parse = parent.legacy.fingerprint, parent.legacy.render, parent.legacy.parse_json
BOUNDARY = {**parent.legacy.BOUNDARY, 'historical_scanner_enabled': False,
    'market_coverage_verified': False, 'identity_continuity_verified': False,
    'reference_identity_is_provisional': True}
ARCHIVE_PIN = {'bytes': 30807928,
    'sha256': '38d772b2017c159050c4cef2a678a79af1fd61f243e8131f5112d1ef25b09ded',
    'inventory_sha256': '493e15337421d777f1fa210716478d88f0ca9765d1c526719575435c6434d05b'}
HOSTED_SEAL = 'ce60ba0657ac1f0706afea4476f2ecbf48e08a99414dd30997e3e49ae8dbab07'
OWN_FILES = ('src/momentumbot/research/census_scanner_bridge.py',
    'scripts/build_census_scanner_bridge.py', 'tests/test_census_scanner_bridge.py',
    'src/momentumbot/historical_universe.py', 'src/momentumbot/instrument_metadata.py',
    'src/momentumbot/identity_continuity.py', 'src/momentumbot/identity_resolved_universe.py',
    'src/momentumbot/providers/massive.py')
COVERAGE_FIELDS = {'invalid_symbol', 'raw_prior_session_present', 'raw_target_session_present',
    'split_prior_session_present', 'split_target_session_present', 'coverage_pass'}


class CensusArchive:
    """Accept only the exact completed source; no caller-supplied provenance flag."""
    def __init__(self, path, root):
        self.path, self.root = Path(path), Path(root)
        require(self.path.is_file() and not any(p.is_symlink() for p in (self.path, *self.path.parents)),
            'regular original census ZIP required')
        require(self.path.stat().st_size == ARCHIVE_PIN['bytes'], 'original ZIP size differs')
        with self.path.open('rb') as handle:
            digest = hashlib.file_digest(handle, 'sha256').hexdigest()
        require(digest == ARCHIVE_PIN['sha256'], 'original ZIP digest differs')
        evidence = parse((self.root / parent.BASE / 'hosted-verification.json').read_bytes())
        parent.d.base.verify_seal(evidence)
        require(evidence['content_sha256'] == HOSTED_SEAL and evidence['hosted_capture_provenance_verified'] is True,
            'accepted hosted evidence differs')
        verification = evidence['archive_verification']
        require(verification['archive_sha256'] == digest and verification['protocol_complete'] is True
            and verification['inventory_file_sha256'] == ARCHIVE_PIN['inventory_sha256'],
            'hosted source binding differs')
        self.pages = {day: [] for day in DATES}
        self.zip = zipfile.ZipFile(self.path)
        try:
            names = self.zip.namelist()
            require(len(names) == len(set(names)) == verification['verified_member_count'], 'source population differs')
            inventory_raw = self.zip.read('inventory.json')
            require(sha(inventory_raw) == ARCHIVE_PIN['inventory_sha256'], 'source inventory differs')
            self.inventory = parse(inventory_raw)['files']
            require(set(self.inventory) == set(names) - {'inventory.json'}, 'source file set differs')
            for name in self.inventory:
                raw = self.read(name)
                if name.endswith('.intent.json'):
                    intent = parse(raw)
                    request = intent['request']
                    if request['kind'] == 'pit_membership_page':
                        self.pages[request['trading_date']].append((request['page'], name[:4]))
            report = parse(self.read('report.json'))
            require(report['protocol_complete'] is True and report['failure'] is None, 'complete capture required')
            exact([d['date'] for d in report['dates']], list(DATES), 'fixed source dates differ')
            self.summaries = {d['date']: d for d in report['dates']}
            for day, pages in self.pages.items():
                pages.sort()
                exact([p[0] for p in pages], list(range(1, self.summaries[day]['accepted_pages'] + 1)),
                    'source page sequence differs')
        except BaseException:
            self.zip.close()
            raise

    def read(self, name):
        raw = self.zip.read(name)
        exact(self.inventory[name], {'bytes': len(raw), 'sha256': sha(raw)}, 'original member differs')
        return raw

    def day(self, day):
        require(day in DATES, 'date outside fixed panel')
        rows = []
        for _, prefix in self.pages[day]:
            rows.extend(parse(self.read(prefix + '.normalized.json'))['rows'])
        require(len(rows) == self.summaries[day]['accepted_rows'], 'source date total differs')
        return rows

    def close(self):
        self.zip.close()

    def __enter__(self): return self
    def __exit__(self, *args): self.close()


def _groups(rows):
    require(type(rows) is list and bool(rows), 'nonempty complete reference rows required')
    # Normalized provider metadata only. In particular no price, outcome or label fields.
    fields = set(normalize_reference_tickers([{'ticker': 'SCHEMA'}])[0])
    for row in rows:
        require(type(row) is dict and set(row) == fields, 'exact normalized reference schema required')
        require(row['active'] is True and row['market'] == 'stocks' and row['locale'] == 'us',
            'fixed active US stock census scope required')
        require(all(type(value) is str for key, value in row.items() if key != 'active'),
            'normalized reference strings required')
    normalized = normalize_reference_tickers(rows)
    identities = [reference_membership_identity(row) for row in normalized]
    require(len(set(identities)) == len(identities), 'duplicate reference identity')
    groups = defaultdict(list)
    for row in normalized: groups[row['ticker']].append(row)
    return dict(sorted(groups.items()))


def project_date(rows, day):
    """Classify with absent coverage; never invent a passing market observation."""
    require(day in DATES, 'date outside fixed panel')
    groups = _groups(rows)
    decisions = [classify_ticker_group(group, None).payload() for group in groups.values()]
    candidates = [r for r in decisions if r['reason'] == 'coverage_record_missing']
    # The identity helper allows provisional reference rows without an `included`
    # assertion. It must not receive fake coverage-approved membership here.
    statuses = build_date_identity_statuses([{k: v for k, v in row.items() if k != 'included'}
        for row in candidates])
    exceptions = [{'ticker': ticker, 'records': group,
        'missing_type': any(not r['type'] for r in group),
        'canonical_collision': len(group) > 1}
        for ticker, group in groups.items() if len(group) > 1 or any(not r['type'] for r in group)]
    return seal({'contract_id': ID, 'trading_date': day, 'source_rows_sha256': fingerprint(rows),
        'source_row_count': len(rows), 'ticker_count': len(groups), 'decisions': decisions,
        'reference_identity_statuses': statuses, 'reference_exceptions': exceptions,
        'coverage_symbols': [r['ticker'] for r in candidates],
        'reason_counts': dict(sorted(Counter(r['reason'] for r in decisions).items())),
        'reference_identity_counts': dict(sorted(Counter(r['identifier_kind'] for r in statuses['accepted']).items())),
        'identity_quarantine_count': len(statuses['quarantined']), **BOUNDARY})


def bind_coverage(rows, day, coverage, *, expected_coverage_sha256):
    """Provider-neutral adapter for later byte-verified coverage projections.

    Does not authenticate provider origin. Historical use additionally requires
    the collector's raw-source proof and continuity/corporate-action evidence.
    The caller hash alone cannot enable the historical scanner.
    """
    reference = project_date(rows, day)
    require(type(coverage) is dict and fingerprint(coverage) == expected_coverage_sha256,
        'external coverage commitment differs')
    require(set(coverage) == {'trading_date', 'reference_sha256', 'records'}
        and coverage['trading_date'] == day and coverage['reference_sha256'] == reference['content_sha256'],
        'coverage date/reference binding differs')
    records = coverage['records']
    require(type(records) is dict and set(records) == set(reference['coverage_symbols']),
        'complete exact coverage population required')
    for record in records.values():
        require(type(record) is dict and set(record) == COVERAGE_FIELDS
            and all(type(v) is bool for v in record.values()), 'strict coverage observations required')
        passed = not record['invalid_symbol'] and all(record[k] for k in COVERAGE_FIELDS
            - {'invalid_symbol', 'coverage_pass'})
        require(record['coverage_pass'] == passed, 'coverage pass contradicts observations')
    groups = _groups(rows)
    decisions = [classify_ticker_group(group, records.get(ticker)).payload() for ticker, group in groups.items()]
    provisional = [row for row in decisions if row['included']]
    # Recompute uniqueness AFTER coverage; never reuse precoverage CIK counts.
    statuses = build_date_identity_statuses(provisional)
    resolved = resolve_identity_membership(provisional, statuses['accepted'], statuses['quarantined'])
    return seal({'contract_id': ID, 'trading_date': day,
        'reference_sha256': reference['content_sha256'], 'coverage_sha256': expected_coverage_sha256,
        'decisions': decisions, 'identity_statuses': statuses, 'membership': resolved,
        'membership_symbols': [row['ticker'] for row in resolved],
        'provider_coverage_origin_authenticated': False, **BOUNDARY})


def coverage_requests(projected):
    """Unarmed roots for the existing raw/split 14-day daily coverage contract.

    Pre-filter only metadata failures whose frozen decisions ignore coverage.
    Identity quarantine is not a coverage filter: CIK uniqueness can change.
    Pagination/transport budgets and capture authority are not supplied here.
    """
    parent.d.base.verify_seal(projected)
    day = projected['trading_date']
    symbols = projected['coverage_symbols']
    require(day in DATES and symbols == sorted(set(symbols)), 'ordered fixed-date coverage symbols required')
    target = date.fromisoformat(day)
    stamp = lambda d: datetime.combine(d, time(), timezone.utc).isoformat()
    roots = []
    for adjustment in ('raw', 'split'):
        for start in range(0, len(symbols), 250):
            roots.append(seal({'provider': 'alpaca', 'method': 'GET',
                'url': 'https://data.alpaca.markets/v2/stocks/bars', 'trading_date': day,
                'reference_sha256': projected['content_sha256'],
                'params': {'symbols': ','.join(symbols[start:start + 250]), 'timeframe': '1Day',
                    'start': stamp(target - timedelta(days=14)), 'end': stamp(target + timedelta(days=1)),
                    'feed': 'sip', 'adjustment': adjustment, 'asof': day, 'limit': 10000, 'sort': 'asc'}}))
    return roots


def registration(root):
    inherited = parent.validate_registration(root)
    names = set(inherited['file_bindings']) | set(OWN_FILES) | {parent.CONTRACT_PATH,
        parent.BASE + '/hosted-verification.json', parent.BASE + '/completion-verification.json'}
    bindings = {}
    for name in sorted(names):
        path = Path(root) / name
        require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), 'regular bound file required')
        raw = path.read_bytes()
        bindings[name] = {'bytes': len(raw), 'sha256': sha(raw)}
    return seal({'contract_id': ID, 'parent_commit': PARENT, 'selected_dates': list(DATES),
        'parent_registration_sha256': inherited['content_sha256'], 'file_bindings': bindings,
        'archive_pin': ARCHIVE_PIN, 'hosted_verification_sha256': HOSTED_SEAL,
        'universe_policy': historical_universe_v0_1_manifest(),
        'hypothesis': 'fixed census metadata maps to complete frozen reference decisions and coverage handoff without fabricated identity or market evidence',
        'identity_scope': 'same-date provisional FIGI/unique-CIK; recompute after real coverage; 120-day actions/continuity remains required',
        'coverage_plan': 'raw/split daily SIP, target asof, inherited UTC 14-day lookback, 250 symbols per initial request; metadata-only prefilter',
        **BOUNDARY})


def validate_registration(root):
    saved = parse((Path(root) / CONTRACT_PATH).read_bytes())
    exact(saved, registration(root), 'bridge registration differs')
    return saved


def build_panel(path, root, *, progress=lambda _: None):
    contract = validate_registration(root)
    days, requests = [], []
    with CensusArchive(path, root) as archive:
        for day in DATES:
            projected = project_date(archive.day(day), day)
            days.append(projected)
            requests.extend(coverage_requests(projected))
            progress({'date': day, 'tickers': projected['ticker_count'],
                'coverage_symbols': len(projected['coverage_symbols']),
                'identity_quarantine': projected['identity_quarantine_count']})
    return seal({'contract_id': ID, 'registration_sha256': contract['content_sha256'],
        'archive_pin': ARCHIVE_PIN, 'hosted_verification_sha256': HOSTED_SEAL,
        'hosted_protocol_replay_reused': True, 'original_members_checked': 1567,
        'days': days, 'coverage_initial_requests': requests, 'initial_request_count': len(requests),
        'request_count_is_total_http_ceiling': False, 'capture_authorized': False,
        'remaining_sources': ['raw/split daily coverage with exhausted request receipts',
            '120-day ticker-change/split/identity evidence', 'complete cross-sectional scanner bars and exact RVOL',
            'candidate SEC float and publication-timed news', 'SIP/warmup and execution/management inputs'],
        **BOUNDARY})
