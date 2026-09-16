"""Bounded raw candidate minutes; full-day selection stays acquisition-only."""
import gzip
from pathlib import Path
import sys

from momentumbot.research import scanner_minute_continuation as parent
from momentumbot.research.minute_archive_verifier import verify_minute_archive

old, c, daily, gate = parent.old, parent.c, parent.daily, parent.gate
require, exact, seal, sha, render, parse = parent.require, parent.exact, parent.seal, parent.sha, parent.render, parent.parse
ID = 'early-pullback-candidate-raw-minutes-v0.1'
BASE = 'research/data-audits/' + ID
CONTRACT_PATH = 'research/strategy/' + ID + '.json'
WORKFLOW = '.github/workflows/candidate-raw-minutes.yml'
PARENT = '73e91a22cd913469c50ce61e9bd14d4b554478cb'
REF = 'refs/tags/' + ID + '-consumed'
KEYS = parent.KEYS
MAX_ATTEMPTS = 600
MAX_PAYLOAD, MAX_METADATA = c.MAX_PAYLOAD, c.MAX_METADATA
MAX_TOTAL = MAX_PAYLOAD + MAX_METADATA
SUPERSET_PATH = old.BASE + '/saved-daily-acquisition-superset.json.gz'
SUPERSET_SEAL = '92c9616b3a9c88f24aece25d181e858faeb9b5c703e53e2b4695309f61cda4ac'
FILES = ('src/momentumbot/research/candidate_raw_minutes.py',
    'src/momentumbot/research/minute_archive_verifier.py',
    'scripts/hosted_scanner_source_cli.py', 'scripts/run_candidate_raw_minutes.py',
    'tests/test_candidate_raw_minutes.py', WORKFLOW, SUPERSET_PATH,
    '.github/actions/source-runtime/action.yml', '.github/workflows/ci.yml',
    'requirements-sealed-source-v04.txt')


def roots_for_day(day, candidates):
    """Only symbols cross the acquisition boundary; no highs or profile scores."""
    require(type(candidates) is list and candidates and candidates == sorted(set(candidates)),
        'nonempty sorted unique candidates required')
    require(set(candidates) <= set(day['membership_symbols']), 'candidate outside dated membership')
    selected = {**day, 'membership_symbols': candidates,
        'previous_close_by_symbol': {s: day['previous_close_by_symbol'][s] for s in candidates}}
    roots = old.roots_for_day(selected)
    return [seal({**{k: v for k, v in root.items() if k != 'content_sha256'},
        'params': {**root['params'], 'adjustment': 'raw'}}) for root in roots]


def request_plan(root):
    source = old.saved_daily(root)
    path = Path(root) / SUPERSET_PATH
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)),
        'regular saved acquisition superset required')
    selected = parse(gzip.decompress(path.read_bytes()))
    c.d.base.verify_seal(selected)
    require(selected['content_sha256'] == SUPERSET_SEAL
        and selected['scanner_daily_sha256'] == source['content_sha256']
        and selected['acquisition_only_full_day_data_forbidden_in_runtime'] is True,
        'original acquisition-only superset required')
    exact([d['trading_date'] for d in selected['days']],
        [d['trading_date'] for d in source['days']], 'candidate date population differs')
    roots = []
    for day, subset in zip(source['days'], selected['days'], strict=True):
        symbols = [row['symbol'] for row in subset['candidates']]
        require(subset['candidate_count'] == len(symbols), 'candidate count differs')
        roots.extend(roots_for_day(day, symbols))
    require(len(roots) == 30 and sum(len(r['params']['symbols'].split(',')) for r in roots) == 4018,
        'fixed candidate population differs')
    return roots


def registration(root):
    inherited = parent.validate_registration(root)
    return seal({'contract_id': ID, 'contract_path': CONTRACT_PATH, 'workflow': WORKFLOW,
        'parent_commit': PARENT, 'parent_registration_sha256': inherited['content_sha256'],
        'acquisition_superset_sha256': SUPERSET_SEAL, 'requests': request_plan(root),
        'file_bindings': {n: {'bytes': (Path(root) / n).stat().st_size,
            'sha256': sha((Path(root) / n).read_bytes())} for n in FILES},
        'authorization': {**inherited['authorization'], 'user_message': 'Great you may continue development; Continue',
            'scope': 'one raw 1Min SIP capture for the existing 4018 candidate symbol/date cases; same 30 dates, 04:00 through 10:00 ET; no subscription or product changes'},
        'limits': {**inherited['limits'], 'maximum_attempts': MAX_ATTEMPTS,
            'maximum_payload_bytes': MAX_PAYLOAD, 'maximum_metadata_bytes': MAX_METADATA},
        'runtime': inherited['runtime'], 'consumption_ref': REF, 'credential_names': list(KEYS),
        'receipt_and_report_schema': c.ID,
        'timestamp_semantics': 'bar start; usable only at start plus one minute',
        'source_role': 'raw candidate price and volume; never rank or split RVOL history',
        'acquisition_filter_values_allowed_in_runtime': False,
        'daily_minute_share_basis_verified': False,
        'exact_same_time_rvol_complete': False, **old.parent.parent.BOUNDARY})


def validate_registration(root):
    value = parse((Path(root) / CONTRACT_PATH).read_bytes())
    exact(value, registration(root), 'candidate raw registration differs')
    return value


State = parent.State


class Capture(old.Capture):
    def __init__(self, contract, **kwargs):
        super().__init__(contract, **kwargs)
        self.state = State(contract['requests'])

    def once(self, request):
        require(self.attempts < MAX_ATTEMPTS, 'candidate raw attempt ceiling')
        return super().once(request)


Transport = old.Transport


def verify_archive(path, metadata, inventory_sha256, contract):
    return verify_minute_archive(path, metadata, inventory_sha256, contract,
        protocol=sys.modules[__name__])


def preflight(root, env, facts, now, runtime, path, metadata, live_ref):
    contract = validate_registration(root)
    gate.check_launch(contract, env, facts, now)
    gate.verify_preflight(old.parent.read_archive(path, metadata['size_in_bytes'], metadata['digest'][7:]),
        contract, env, runtime, live_ref, metadata)
    return contract


def capture(root, env, facts, now, runtime, path, metadata, live_ref, *, output, credential_loader, transport, progress):
    contract = preflight(root, env, facts, now, runtime, path, metadata, live_ref)
    require(not Path(output).exists() and not any(p.is_symlink() for p in (Path(output), *Path(output).parents)),
        'fresh output required')
    return Capture(contract, output=output, keys=credential_loader(), transport=transport, progress=progress).run()


def verify(root, env, facts, now, runtime, path, metadata, live_ref, capture_path, capture_metadata, jobs):
    contract = preflight(root, env, facts, now, runtime, path, metadata, live_ref)
    gate.check_jobs(jobs, env)
    gate.check_artifact(capture_metadata, contract, env, 'capture', env['CAPTURE_ARTIFACT_ID'], MAX_TOTAL)
    result = verify_archive(capture_path, capture_metadata, env['CAPTURE_INVENTORY_SHA256'], contract)
    return seal({'contract_id': ID, 'code_commit': env['GITHUB_SHA'], 'run_id': env['GITHUB_RUN_ID'],
        'archive_verification': result, 'hosted_capture_provenance_verified': True,
        'consumption_ref': REF, 'provider_requests_during_verification': 0,
        'daily_minute_share_basis_verified': False, 'exact_same_time_rvol_complete': False,
        **old.parent.parent.BOUNDARY})
