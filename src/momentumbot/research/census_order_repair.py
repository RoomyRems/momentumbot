"""Provider-native ordering, separate from unchanged canonical membership identity.

Pure protocol extension only: no transport, credential discovery or launch authority.
The frozen v0.1 capture/parser and its failed evidence remain unchanged.
"""
from collections import Counter

from momentumbot.research import census_payload_diagnostic as diagnostic

legacy = diagnostic.adapter
require, exact, seal, sha = legacy.require, legacy.exact, legacy.seal, legacy.sha
ID = 'early-pullback-census-order-repair-v0.1'
CONTRACT_PATH = f'research/strategy/{ID}.json'
BASE = f'research/data-audits/{ID}'
PARENT = '7bba0854cbfbf58dbe79ce3f0fd8b6f3ac02ee17'
OWN_FILES = ('src/momentumbot/research/census_order_repair.py',
    'src/momentumbot/research/census_payload_evidence.py',
    'scripts/verify_census_order_repair.py', 'tests/test_census_order_repair.py')


def project_body(request, raw):
    """Check untouched provider order, then reuse every other frozen validation.

    A separate canonical-sorted validation view lets the legacy parser enforce
    its schema, count, metadata, filter and cursor checks without its defective
    order predicate. The raw response is never rewritten or used as that view's
    hash. Normalized rows are unchanged; exact provider symbols travel separately.
    """
    legacy.validate_request(request)
    if request['kind'] == 'current_type_dictionary':
        return legacy.project_body(request, raw)
    require(type(raw) is bytes and 0 < len(raw) <= legacy.MAX_BODY, 'bounded complete body required')
    value = legacy.parse_json(raw)
    rows = value.get('results')
    require(type(rows) is list and len(rows) <= legacy.parent.PAGE_LIMIT
        and all(type(row) is dict for row in rows), 'bounded result list required')
    for row in rows:
        legacy._text(row.get('ticker'), required=True)
    provider_tickers = [row['ticker'] for row in rows]
    require(provider_tickers == sorted(provider_tickers), 'provider page order regressed')
    validation_view = dict(value, results=sorted(rows, key=lambda row: row['ticker'].strip().upper()))
    projected = legacy.project_body(request, legacy.render(validation_view))
    return dict(projected, provider_tickers=provider_tickers)


class CensusState(legacy.CensusState):
    """Keep raw lexical boundaries across empty pages; identities stay canonical."""
    def __init__(self):
        super().__init__()
        self.last_provider_ticker = {day: None for day in legacy.DATES}

    def accept(self, request, raw_sha, projection):
        exact(request, self.next_request(), 'request sequence differs')
        diagnostic.base.hash_value(raw_sha)
        if request['kind'] == 'current_type_dictionary':
            return super().accept(request, raw_sha, projection)
        day, rows = request['trading_date'], projection['rows']
        provider_tickers = projection.get('provider_tickers')
        require(type(provider_tickers) is list and len(provider_tickers) == len(rows)
            and type(projection['raw_row_count']) is int
            and len(rows) == projection['raw_row_count'], 'provider order witness differs')
        for ticker in provider_tickers:
            legacy._text(ticker, required=True)
        require(provider_tickers == sorted(provider_tickers), 'provider page order regressed')
        tickers = [row['ticker'] for row in rows]
        require(Counter(t.strip().upper() for t in provider_tickers) == Counter(tickers),
            'provider/canonical ticker population differs')
        if provider_tickers and self.last_provider_ticker[day] is not None:
            require(provider_tickers[0] >= self.last_provider_ticker[day], 'cross-page ordering regression')
        identities = [legacy.reference_membership_identity(row) for row in rows]
        require(len(set(identities)) == len(identities)
            and not self.identities[day].intersection(identities), 'duplicate membership identity')
        page = {'request': request, 'response_sha256': raw_sha,
            'row_count': projection['raw_row_count'], 'next_url': projection['next_url']}
        proposed = [*self.pages[day], page]
        following = legacy.parent.next_census_request(day, proposed)
        chain = legacy.fingerprint({'previous': self.chains[day], 'page': projection, 'response_sha256': raw_sha})
        # All validation precedes every mutation, including the raw-order boundary.
        self.pages[day] = proposed
        self.identities[day].update(identities)
        self.tickers[day].update(tickers)
        for row in rows:
            for key in ('cik', 'composite_figi', 'share_class_figi', 'primary_exchange', 'type'):
                if not row[key]:
                    self.missing[day][key] += 1
            if row['type'] not in self.types:
                self.unknown[day].add(row['type'])
        self.chains[day] = chain
        if provider_tickers:
            self.last_provider_ticker[day] = provider_tickers[-1]
        if following is None:
            self.exhausted.add(day)


def registration(root):
    inherited = diagnostic.validate_registration(root)
    paths = (*OWN_FILES, diagnostic.CONTRACT_PATH, diagnostic.BASE + '/hosted-result.zip',
        diagnostic.BASE + '/hosted-preflight.zip', BASE + '/diagnostic-verification.json')
    bindings = {}
    for name in paths:
        path = root / name
        require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), 'regular bound file required')
        raw = path.read_bytes()
        bindings[name] = {'bytes': len(raw), 'sha256': sha(raw)}
    return seal({'contract_id': ID, 'parent_commit': PARENT,
        'parent_registration_sha256': inherited['content_sha256'], 'file_bindings': bindings,
        'hypothesis': 'provider-native lexical order must be checked before canonical ticker normalization, within and across pages',
        'selected_dates': list(legacy.DATES), 'limits': legacy.limits(),
        'normalization': 'unchanged normalize_reference_tickers and reference_membership_identity',
        'scope': 'offline protocol repair; no transport or launcher; diagnostic remains quarantined',
        **legacy.BOUNDARY})


def validate_registration(root):
    saved = diagnostic.base.frozen(root / CONTRACT_PATH)
    exact(saved, registration(root), 'order repair registration differs')
    return saved
