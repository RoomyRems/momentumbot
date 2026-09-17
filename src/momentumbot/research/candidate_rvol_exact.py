"""Exact-minute history bound to the successful hosted coarse-source audit."""
from pathlib import Path
from datetime import timedelta
import gzip
import zipfile
import sys
from momentumbot.research import candidate_rvol_coarse as parent
from momentumbot.research import candidate_rvol_source as source
from momentumbot.research.minute_archive_verifier import verify_minute_archive

old,c,daily,gate = parent.old,parent.c,parent.daily,parent.gate
require,exact,seal,sha,render,parse = parent.require,parent.exact,parent.seal,parent.sha,parent.render,parent.parse
ID = 'early-pullback-candidate-rvol-exact-v0.1'
BASE = 'research/data-audits/' + ID
CONTRACT_PATH = 'research/strategy/' + ID + '.json'
WORKFLOW = '.github/workflows/candidate-rvol-exact.yml'
PARENT = 'b7494ecaec02a3ea33182ea97048bb22403c3d7e'
REF = 'refs/tags/' + ID + '-consumed'
KEYS = parent.KEYS
MAX_ATTEMPTS = 9000
MAX_PAYLOAD, MAX_METADATA = c.MAX_PAYLOAD,c.MAX_METADATA
MAX_TOTAL = MAX_PAYLOAD + MAX_METADATA
AUDIT_PATH = source.BASE + '/original-integration.zip'
AUDIT_PIN = {'bytes': 312667, 'sha256': 'd84c6c08be1c0dd0e85fa5ffbfb996a4f70a707c33d87f1e0b2e662fb58dcbaa'}
AUDIT_SEAL = '203811a87136c8a2dd1768519eb57b5452ed81578de45a84f45ee7e4e0a4be14'
FILES = ('src/momentumbot/research/candidate_rvol_exact.py',
    'src/momentumbot/research/candidate_rvol_source.py',
    'src/momentumbot/research/candidate_volume_projection.py',
    'src/momentumbot/historical_profile_union_v01.py',
    'src/momentumbot/research/minute_archive_verifier.py',
    'scripts/hosted_scanner_source_cli.py','scripts/run_candidate_rvol_exact.py',
    'scripts/audit_candidate_rvol_source.py','tests/test_candidate_rvol_exact.py',
    'tests/test_candidate_rvol_source.py',WORKFLOW,AUDIT_PATH,
    '.github/actions/source-runtime/action.yml','.github/workflows/ci.yml',
    'requirements-sealed-source-v04.txt')


def accepted_selection(root):
    path=Path(root)/AUDIT_PATH
    require(AUDIT_PIN is not None and AUDIT_SEAL is not None,'accepted integration required')
    old.parent.parent._pinned_file(path,AUDIT_PIN)
    with zipfile.ZipFile(path) as archive:
        value=parse(gzip.decompress(archive.read('acquisition-diagnostic.json.gz')))
        metadata=parse(archive.read('original-artifacts.json'))
    c.d.base.verify_seal(value)
    require(value['content_sha256']==AUDIT_SEAL and value['accepted_coarse_proof_sha256']==source.PROOF_SEAL,
        'original source acquisition diagnostic differs')
    require(metadata['code_commit']==PARENT and metadata['run_id']=='35169713629','hosted integration provenance differs')
    return value


def target_rechecks(roots, days):
    """Refresh only the eight unresolved target volumes in the same capture."""
    requested=[]
    for day in days:
        target=day['trading_date']
        symbols={c['symbol'] for c in day['cases'] if c['mismatched_buckets']}
        covered=set()
        for root in roots:
            if root['trading_date']!=target or root['observation_date']!=target:continue
            selected=sorted(symbols.intersection(root['params']['symbols'].split(',')))
            if not selected:continue
            require(not covered.intersection(selected),'duplicate target recheck')
            params={**root['params'],'symbols':','.join(selected),'timeframe':'1Min',
                'end':(daily._stamp(root['params']['end'])+timedelta(minutes=14)).isoformat()}
            requested.append(seal({**{k:v for k,v in root.items() if k!='content_sha256'},'params':params}))
            covered.update(selected)
        exact(sorted(covered),sorted(symbols),'unresolved target coverage differs')
    return requested


def registration(root):
    inherited=parent.validate_registration(root);audit=accepted_selection(root)
    requests=source.exact_requests(inherited['requests'],audit['days'])
    exact(requests,audit['prepared_exact_requests'],'prepared requests differ')
    require(requests,'nonempty exact acquisition required')
    rechecks=target_rechecks(inherited['requests'],audit['days'])
    return seal({'contract_id':ID,'contract_path':CONTRACT_PATH,'workflow':WORKFLOW,'parent_commit':PARENT,
        'parent_registration_sha256':inherited['content_sha256'],'acquisition_diagnostic_sha256':AUDIT_SEAL,
        'accepted_coarse_proof_sha256':source.PROOF_SEAL,'requests':requests+rechecks,
        'prior_history_roots':len(requests),'unresolved_target_recheck_roots':len(rechecks),
        'file_bindings':{n:{'bytes':(Path(root)/n).stat().st_size,'sha256':sha((Path(root)/n).read_bytes())} for n in FILES},
        'authorization':{**inherited['authorization'],'user_message':'Identify the next step and continue development',
            'scope':'one exact split 1Min SIP capture for fifty prior observed sessions of retained existing candidate/date cases, plus matching target mornings for the eight unresolved volume cases; same thirty target dates and existing subscription'},
        'limits':{**inherited['limits'],'maximum_attempts':MAX_ATTEMPTS,'maximum_payload_bytes':MAX_PAYLOAD,'maximum_metadata_bytes':MAX_METADATA},
        'runtime':inherited['runtime'],'consumption_ref':REF,'credential_names':list(KEYS),'receipt_and_report_schema':c.ID,
        'source_role':'exact same-time RVOL history; target split minute bars reused from accepted scanner source',
        'acquisition_filter_values_allowed_in_runtime':False,'daily_minute_share_basis_verified':False,
        'exact_same_time_rvol_complete':False,**old.parent.parent.BOUNDARY})


def validate_registration(root):
    value=parse((Path(root)/CONTRACT_PATH).read_bytes())
    exact(value,registration(root),'exact RVOL registration differs')
    return value


class ExactPages(parent.parent.parent.parent.MinutePages):
    def __init__(self, root):
        super().__init__(root)
        require(root['params']['timeframe'] == '1Min' and root['params']['adjustment'] == 'split',
            'split one-minute root required')

    def _accept(self, request, reply):
        for rows in (parse(reply['body']).get('bars') or {}).values():
            for row in rows:
                stamp = daily._stamp(row['t']).astimezone(daily.ET)
                require(stamp.date().isoformat() == self.root['observation_date'],
                    'exact session differs')
        return super()._accept(request, reply)


class State(parent.parent.State):
    def request(self):
        require(not self.failed, 'exact state failed')
        if len(self.results) == len(self.tasks): return None
        if self.current is None: self.current = ExactPages(self.tasks[len(self.results)])
        return self.current.request()


class Capture(old.Capture):
    def __init__(self, contract, **kwargs):
        super().__init__(contract, **kwargs)
        self.state = State(contract['requests'])

    def once(self, request):
        require(self.attempts < MAX_ATTEMPTS, 'exact RVOL attempt ceiling')
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
