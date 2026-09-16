"""Prior-session 15-minute volume capture for the frozen RVOL acquisition filter."""
from collections import defaultdict
from datetime import date, datetime, time, timezone
import zipfile
from pathlib import Path
import sys

from momentumbot.research import candidate_daily_history as parent
from momentumbot.research.minute_archive_verifier import verify_minute_archive

old, c, daily, gate = parent.old, parent.c, parent.daily, parent.gate
require, exact, seal, sha, render, parse = parent.require, parent.exact, parent.seal, parent.sha, parent.render, parent.parse
ID = 'early-pullback-candidate-rvol-coarse-v0.1'
BASE = 'research/data-audits/' + ID
CONTRACT_PATH = 'research/strategy/' + ID + '.json'
WORKFLOW = '.github/workflows/candidate-rvol-coarse.yml'
PARENT = '17f8561b5dd147029d4c4810dc6b8592a7139f5b'
REF = 'refs/tags/' + ID + '-consumed'
KEYS = parent.KEYS
MAX_ATTEMPTS = 9000
MAX_PAYLOAD, MAX_METADATA = c.MAX_PAYLOAD, c.MAX_METADATA
MAX_TOTAL = MAX_PAYLOAD + MAX_METADATA
SUPERSET_PATH = parent.parent.SUPERSET_PATH
PROOF_PATH = parent.BASE + '/original-verification.zip'
PROOF_PIN = {'bytes':99691,'sha256':'a832e64a8e78b2b296657f37c65a5bff26f446eadb5f816f66116eba87cb969e'}
PROOF_SEAL = 'f2aa4f68f9de5356aeffd9e6474e3581d95f9bbc32e344e28b49b09e623f4784'
SUPERSET_SEAL = '92c9616b3a9c88f24aece25d181e858faeb9b5c703e53e2b4695309f61cda4ac'
FILES = ('src/momentumbot/research/candidate_rvol_coarse.py',
    'src/momentumbot/research/minute_archive_verifier.py',
    'scripts/hosted_scanner_source_cli.py', 'scripts/run_candidate_rvol_coarse.py',
    'tests/test_candidate_rvol_coarse.py', WORKFLOW, SUPERSET_PATH, PROOF_PATH,
    'src/momentumbot/research/candidate_source_archive.py',
    '.github/actions/source-runtime/action.yml', '.github/workflows/ci.yml',
    'requirements-sealed-source-v04.txt')


def accepted_daily_proof(root):
    path = Path(root) / PROOF_PATH
    old.parent.parent._pinned_file(path, PROOF_PIN)
    with zipfile.ZipFile(path) as z: proof = parse(z.read('hosted-verification.json'))
    c.d.base.verify_seal(proof)
    require(proof['content_sha256'] == PROOF_SEAL and proof['code_commit'] == PARENT
        and proof['run_id'] == '35163240481' and proof['hosted_capture_provenance_verified'] is True,
        'accepted daily history proof required')
    return proof


def plan_day(root, daily_summary, raw_summary):
    """No price/outcome pruning: require observed raw bars and 50 prior sessions."""
    symbols = root['params']['symbols'].split(',')
    exact(sorted(daily_summary['prior_sessions_by_symbol']),symbols,'daily candidate population differs')
    exact(sorted(raw_summary['symbol_bar_counts']),symbols,'raw candidate population differs')
    target = root['trading_date']; batches = defaultdict(list); excluded = []
    for symbol in symbols:
        sessions = daily_summary['prior_sessions_by_symbol'][symbol]
        require(sessions == sorted(set(sessions)) and len(sessions) <= 50
            and all(date.fromisoformat(d) < date.fromisoformat(target) for d in sessions),
            'unique prior sessions required')
        count = raw_summary['symbol_bar_counts'][symbol]
        require(type(count) is int and count >= 0,'raw count required')
        reasons = []
        if len(sessions) < 50: reasons.append('insufficient_prior_sessions')
        if count == 0: reasons.append('exhausted_empty_raw_minutes')
        if reasons:
            excluded.append({'symbol':symbol,'reasons':reasons});continue
        # Target coarse volumes permit a separate same-period basis comparison.
        for session in [*sessions,target]: batches[session].append(symbol)
    requests = []
    for session, selected in sorted(batches.items()):
        for i in range(0,len(selected),250):
            start = datetime.combine(date.fromisoformat(session),time(4),daily.ET)
            end = datetime.combine(date.fromisoformat(session),time(9,45),daily.ET)
            requests.append(seal({'provider':'alpaca','method':'GET','url':root['url'],
                'trading_date':target,'observation_date':session,'membership_sha256':root['membership_sha256'],
                'params':{'symbols':','.join(selected[i:i+250]),'timeframe':'15Min','adjustment':'split',
                    'start':start.astimezone(timezone.utc).isoformat(),'end':end.astimezone(timezone.utc).isoformat(),
                    'asof':target,'feed':'sip','sort':'asc','limit':10000}}))
    return {'trading_date':target,'requests':requests,'excluded':excluded}


def source_plan(root):
    from momentumbot.research.candidate_source_archive import accepted_proof
    daily_proof = accepted_daily_proof(root)['archive_verification']
    raw_proof = accepted_proof(root)['archive_verification']
    roots = parent.validate_registration(root)['requests']
    raw_roots = parent.parent.validate_registration(root)['requests']
    daily_summaries = daily_proof['root_summaries'];raw_summaries = raw_proof['root_summaries']
    exact([r['content_sha256'] for r in roots],[r['root_sha256'] for r in daily_summaries],'daily root union differs')
    exact([r['content_sha256'] for r in raw_roots],[r['root_sha256'] for r in raw_summaries],'raw root union differs')
    return [plan_day(r,d,s) for r,d,s in zip(roots,daily_summaries,raw_summaries,strict=True)]


def request_plan(root):
    return [r for day in source_plan(root) for r in day['requests']]


def registration(root):
    inherited = parent.validate_registration(root)
    return seal({'contract_id': ID, 'contract_path': CONTRACT_PATH, 'workflow': WORKFLOW,
        'parent_commit': PARENT, 'parent_registration_sha256': inherited['content_sha256'],
        'acquisition_superset_sha256': SUPERSET_SEAL, 'daily_proof_sha256': PROOF_SEAL,
        'requests': request_plan(root), 'excluded_cases': [{k:v for k,v in d.items() if k != 'requests'} for d in source_plan(root)],
        'file_bindings': {n: {'bytes': (Path(root) / n).stat().st_size,
            'sha256': sha((Path(root) / n).read_bytes())} for n in FILES},
        'authorization': {**inherited['authorization'], 'user_message': 'Great you may continue development; Continue',
            'scope': 'one split 15Min SIP volume capture for verified 50-session histories plus matching target mornings of the existing candidate cases; fixed 30 target dates; existing subscription only'},
        'limits': {**inherited['limits'], 'maximum_attempts': MAX_ATTEMPTS,
            'maximum_payload_bytes': MAX_PAYLOAD, 'maximum_metadata_bytes': MAX_METADATA},
        'runtime': inherited['runtime'], 'consumption_ref': REF, 'credential_names': list(KEYS),
        'receipt_and_report_schema': c.ID,
        'timestamp_semantics': '15-minute bar start; completed at start plus 15 minutes',
        'source_role': 'completed 15Min volume upper bound for downloads only; exact 1Min RVOL still required',
        'acquisition_filter_values_allowed_in_runtime': False,
        'daily_minute_share_basis_verified': False,
        'exact_same_time_rvol_complete': False, **old.parent.parent.BOUNDARY})


def validate_registration(root):
    value = parse((Path(root) / CONTRACT_PATH).read_bytes())
    exact(value, registration(root), 'coarse RVOL registration differs')
    return value


class CoarsePages(parent.parent.parent.MinutePages):
    def __init__(self, root):
        super().__init__(root)
        require(root['params']['timeframe'] == '15Min' and root['params']['adjustment'] == 'split',
            'split 15-minute root required')

    def _accept(self, request, reply):
        for rows in (parse(reply['body']).get('bars') or {}).values():
            for row in rows:
                stamp = daily._stamp(row['t']).astimezone(daily.ET)
                require(stamp.minute % 15 == 0 and stamp.date().isoformat() == self.root['observation_date'],
                    'coarse grid/session differs')
        return super()._accept(request, reply)


class State(parent.parent.State):
    def request(self):
        require(not self.failed, 'coarse state failed')
        if len(self.results) == len(self.tasks): return None
        if self.current is None: self.current = CoarsePages(self.tasks[len(self.results)])
        return self.current.request()


class Capture(old.Capture):
    def __init__(self, contract, **kwargs):
        super().__init__(contract, **kwargs)
        self.state = State(contract['requests'])

    def once(self, request):
        require(self.attempts < MAX_ATTEMPTS, 'coarse RVOL attempt ceiling')
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
