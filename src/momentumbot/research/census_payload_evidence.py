"""Offline verification of the original one-request GitHub diagnostic artifacts."""
from datetime import datetime
from pathlib import Path
import re
import stat
import zipfile

from momentumbot.research import census_payload_diagnostic as d

CODE = '7bba0854cbfbf58dbe79ce3f0fd8b6f3ac02ee17'
RUN = 34715001958
CI_RUN = 34715001971
PREFLIGHT_PIN = 'f3680d6f8e10d7eb0329bf39d02f5d9497b376bc4467596a3ea344cb7a1f2581'
BODY_PIN = '2b1a70f94e0275606fda03c7d30b3da88fc7c86a93adb054a39b29264c0b82dd'
ARTIFACTS = {
    'hosted-preflight.zip': (10304832381, 24766, '327576093c14785d651487372c20897fba9c380fc1b0d0836467a79987f7de51'),
    'hosted-result.zip': (10304886525, 65103, '3ae062d9dd610873c3f50e568b5b61026d6dd47fb1417374ec72ac8ab46bc6e4')}


def read_archive(path, expected_bytes, expected_sha256):
    path = Path(path)
    d.require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents))
        and path.stat().st_size == expected_bytes, 'original archive size/path differs')
    d.require(d.sha(path.read_bytes()) == expected_sha256, 'original archive digest differs')
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        d.require(len(infos) == len({i.filename for i in infos})
            and sum(i.file_size for i in infos) <= d.previous.PREFLIGHT_LIMIT, 'bounded unique archive required')
        for i in infos:
            d.require(re.fullmatch(r'[A-Za-z0-9.-]+', i.filename) and not i.is_dir()
                and stat.S_IFMT(i.external_attr >> 16) in (0, stat.S_IFREG), 'unsafe archive member')
        return {i.filename: archive.read(i) for i in infos}


def verify(root):
    base = root / d.BASE
    read = lambda name: d.base.json_object((base / name).read_bytes())
    env = {'GITHUB_SHA': CODE, 'GITHUB_RUN_ID': str(RUN),
        'DIAGNOSTIC_PREFLIGHT_SHA256': PREFLIGHT_PIN, 'DIAGNOSTIC_PREFLIGHT_ARTIFACT_ID': '10304832381'}
    contract = d.validate_registration(root)
    ci, ci_jobs, run, jobs = (read(n) for n in ('ci-run.json', 'ci-jobs.json', 'hosted-run.json', 'hosted-jobs.json'))
    d.check_ci(ci, ci_jobs, env)
    d.require(ci['id'] == CI_RUN and run['id'] == RUN and run['head_sha'] == CODE
        and run['path'] == d.WORKFLOW_PATH and run['event'] == 'push' and run['run_attempt'] == 1
        and run['head_branch'] == 'phase-3-historical-snapshot'
        and run['repository']['full_name'] == 'RoomyRems/momentumbot'
        and run['status'] == 'completed' and run['conclusion'] == 'success', 'successful exact diagnostic required')
    d.require(jobs['total_count'] == len(jobs['jobs']) == 2
        and {j['name'] for j in jobs['jobs']} == {'consume', 'diagnose'}, 'diagnostic jobs differ')
    for job in jobs['jobs']:
        d.require(job['run_id'] == RUN and job['head_sha'] == CODE
            and job['status'] == 'completed' and job['conclusion'] == 'success'
            and job['steps'] and all(s['status'] == 'completed' and s['conclusion'] == 'success'
                for s in job['steps']), 'diagnostic job/step did not succeed')
    log = (base / 'ci.log').read_text()
    d.require(re.search(r'Ran 2750 tests in [0-9.]+s', log) and 'OK (skipped=73)' in log,
        'original complete test count differs')
    d.require('DIAGNOSTIC_PREFLIGHT_SHA256: ' + PREFLIGHT_PIN in (base / 'diagnose.log').read_text(),
        'independent consumer preflight pin differs')
    metadata = read('hosted-artifacts.json')
    d.require(metadata['total_count'] == len(metadata['artifacts']) == 2, 'artifact inventory differs')
    artifacts = {a['id']: a for a in metadata['artifacts']}
    archives = {}
    for name, (identity, size, digest) in ARTIFACTS.items():
        a = artifacts[identity]
        suffix = 'consumption' if name == 'hosted-preflight.zip' else 'result'
        d.require(a['size_in_bytes'] == size and a['digest'] == 'sha256:' + digest
            and a['name'] == f'{d.ID}-{suffix}-{RUN}-1' and a['expired'] is False
            and a['workflow_run']['id'] == RUN and a['workflow_run']['head_sha'] == CODE
            and a['workflow_run']['head_branch'] == 'phase-3-historical-snapshot', 'original artifact metadata differs')
        archives[name] = read_archive(base / name, size, digest)
    preflight, result = archives['hosted-preflight.zip'], archives['hosted-result.zip']
    d.verify_preflight(preflight, contract, env, d.previous.RUNTIME, read('consumed-ref.json'), artifacts[10304832381])
    expected = {'preflight-' + n for n in d.PREFLIGHT_FILES} | {
        'artifact-metadata.json', 'live-ref.json', 'intent.json', 'response.body.json', 'report.json', 'inventory.json'}
    d.require(set(result) == expected, 'diagnostic result population differs')
    for name, raw in preflight.items():
        d.require(result['preflight-' + name] == raw, 'preflight retention differs')
    d.exact(d.base.json_object(result['inventory.json']),
        d.inventory({n: b for n, b in result.items() if n != 'inventory.json'}), 'result byte inventory differs')
    d.check_ref(d.base.json_object(result['live-ref.json']), env)
    observed_artifact = d.base.json_object(result['artifact-metadata.json'])
    for key in ('id', 'name', 'digest', 'size_in_bytes', 'workflow_run'):
        d.exact(observed_artifact[key], artifacts[10304832381][key], 'consumer artifact identity differs')
    intent, report = (d.base.json_object(result[n]) for n in ('intent.json', 'report.json'))
    for value in (intent, report):
        d.base.verify_seal(value)
    d.exact(intent, d.seal({'contract_id': d.ID, 'request': d.request(), 'started_at': intent['started_at']}), 'exact one-request intent differs')
    raw = result['response.body.json']
    d.require(len(raw) == 293790 and d.sha(raw) == BODY_PIN, 'retained body differs')
    d.exact(report, d.seal({'contract_id': d.ID, 'attempts': 1, 'status': 200, 'body_complete': True,
        'body_bytes': len(raw), 'body_sha256': BODY_PIN, 'body_retained': True,
        'diagnosis': d.diagnose(raw), 'failure': None, 'finished_at': report['finished_at'],
        'diagnostic_only': True, **d.adapter.BOUNDARY}), 'diagnostic report differs')
    started, finished = (datetime.fromisoformat(v) for v in (intent['started_at'], report['finished_at']))
    d.require(started.tzinfo is not None and finished.tzinfo is not None and finished >= started,
        'diagnostic chronology differs')
    tickers = [r['ticker'] for r in d.base.json_object(raw)['results']]
    canonical = [t.strip().upper() for t in tickers]
    regressions = [{'index': i, 'previous': tickers[i - 1], 'current': tickers[i]}
        for i in range(1, len(tickers)) if canonical[i] < canonical[i - 1]]
    d.require(tickers == sorted(tickers) and len(regressions) == 11
        and report['diagnosis']['reason'] == 'provider page order regressed', 'observed ordering fault differs')
    return d.seal({'artifact_type': 'verified_quarantined_census_order_diagnostic',
        'code_commit': CODE, 'ci_run_id': CI_RUN, 'diagnostic_run_id': RUN, 'attempts': 1,
        'status': 200, 'body_sha256': BODY_PIN, 'body_bytes': len(raw), 'rows': len(tickers),
        'provider_native_ordered': True, 'uppercase_ordered': False, 'false_regressions': regressions,
        'preflight_inventory_file_sha256': PREFLIGHT_PIN,
        'verified_zip_sha256': {n: spec[2] for n, spec in ARTIFACTS.items()},
        'old_rejected_body_available': False, 'old_rejected_body_byte_identical_claim': False,
        'billing_verified': False, 'runtime_use_authorized': False, **d.adapter.BOUNDARY}), raw
