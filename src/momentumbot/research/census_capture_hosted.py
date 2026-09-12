"""Same-code CI, independent consumption and hosted verification for one census."""
from datetime import datetime, timezone
from pathlib import Path
import re

from momentumbot.research import census_capture as capture_engine
from momentumbot.research.census_payload_evidence import read_archive

protocol, legacy = capture_engine.protocol, capture_engine.legacy
d = protocol.diagnostic
require, exact, seal, sha = d.require, d.exact, d.seal, d.sha
ID = capture_engine.ID
CONTRACT_PATH = f'research/strategy/{ID}.json'
BASE = f'research/data-audits/{ID}'
WORKFLOW = '.github/workflows/census-repaired-capture.yml'
REF = f'refs/tags/{ID}-consumed'
PARENT = 'b0eb4cdd926edee99974d81040fd6b968b7d71a2'
RUNTIME = d.previous.RUNTIME
OWN_FILES = ('src/momentumbot/research/census_capture.py',
    'src/momentumbot/research/census_capture_hosted.py', 'scripts/run_census_capture.py',
    'tests/test_census_capture.py', 'tests/test_census_capture_hosted.py', WORKFLOW,
    '.github/workflows/ci.yml', 'requirements-sealed-source-v04.txt')


def registration(root):
    inherited = protocol.validate_registration(root)
    require(inherited['content_sha256'] == '260dc6825151d090cb3589fc36c1cfe0cfdfd41c6eaae3e80dbf711bda21d6f4',
        'frozen order repair differs')
    paths = set(inherited['file_bindings']) | set(OWN_FILES) | {protocol.CONTRACT_PATH,
        protocol.BASE + '/hosted-ci-verification.json', d.previous.APPROVAL_SOURCE_PATH, d.previous.PRICING_PATH}
    bindings = {}
    for name in sorted(paths):
        path = root / name
        require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), 'regular bound file required')
        raw = path.read_bytes()
        bindings[name] = {'bytes': len(raw), 'sha256': sha(raw)}
    return seal({'contract_id': ID, 'parent_commit': PARENT,
        'parent_registration_sha256': inherited['content_sha256'], 'file_bindings': bindings,
        'selected_dates': list(legacy.DATES), 'limits': legacy.limits(), 'runtime': RUNTIME,
        'authorization': {'latest_user_message': 'You may continue', 'observed_date': '2026-09-12',
            'prior_owner_message': d.previous.OWNER_MESSAGE,
            'scope': 'one repaired bounded 30-date census after same-code CI, with automatic independent archive verification',
            'expires_at': '2026-09-19T00:00:00Z', 'maximum_requests': 601,
            'estimated_incremental_api_cost_usd': '0.00', 'maximum_incremental_cost_usd': '10.00',
            'account_entitlement_verified': False, 'billing_cap_provider_enforced': False,
            'credit_provider_identified': False, 'credit_balance_verified': False,
            'metered_purchase_authorized': False, 'subscription_changes_authorized': False},
        'consumption_ref': REF, 'credential_name': 'MASSIVE_API_KEY', 'credential_fallback': False,
        'hypothesis': 'the repaired provider-order protocol can exhaust the fixed census and reproduce every raw page independently',
        'safe_rejected_json_retained': True, 'automatic_archive_verification': True,
        'old_consumed_authorizations_reused': False, **legacy.BOUNDARY})


def validate_registration(root):
    saved = d.base.frozen(root / CONTRACT_PATH)
    exact(saved, registration(root), 'repaired capture registration differs')
    return saved


def check_launch(contract, env, facts, now):
    require(d.previous.stamp('2026-09-12T00:00:00Z') <= now < d.previous.stamp(contract['authorization']['expires_at']),
        'capture authorization expired or future')
    require(facts['clean'] is True and facts['head'] == env.get('GITHUB_SHA')
        and facts['parents'] == [PARENT] and facts['parent_commit'] == PARENT
        and 'A\t' + CONTRACT_PATH in facts['changed_files'], 'exact clean new code child required')
    require(env.get('GITHUB_REPOSITORY') == 'RoomyRems/momentumbot'
        and env.get('GITHUB_REF') == 'refs/heads/phase-3-historical-snapshot'
        and env.get('GITHUB_EVENT_NAME') == 'push' and env.get('GITHUB_RUN_ATTEMPT') == '1'
        and env.get('GITHUB_WORKFLOW_SHA') == facts['head']
        and env.get('GITHUB_WORKFLOW_REF') == 'RoomyRems/momentumbot/' + WORKFLOW + '@refs/heads/phase-3-historical-snapshot'
        and re.fullmatch(r'[1-9][0-9]*', env.get('GITHUB_RUN_ID', '')), 'exact first-attempt workflow required')


def check_ref(value, env):
    require(value.get('ref') == REF and value.get('object', {}).get('type') == 'commit'
        and value['object'].get('sha') == env['GITHUB_SHA'], 'permanent capture consumption differs')


def launch_record(contract, env, runtime):
    exact(runtime, RUNTIME, 'frozen runtime differs')
    return seal({'contract_id': ID, 'contract_sha256': contract['content_sha256'],
        'code_commit': env['GITHUB_SHA'], 'run_id': env['GITHUB_RUN_ID'], 'run_attempt': 1,
        'consumption_ref': REF, 'runtime': runtime})


def inventory(files):
    return seal({'contract_id': ID, 'files': {n: {'bytes': len(b), 'sha256': sha(b)} for n, b in sorted(files.items())}})


def prepare(path, contract, env, runtime):
    files = d.read_files(path, d.PREFLIGHT_INPUTS)
    d.check_ci(d.base.json_object(files['ci.json']), d.base.json_object(files['ci-jobs.json']), env)
    check_ref(d.base.json_object(files['consumed-ref.json']), env)
    for name, value in (('contract.json', contract), ('launch.json', launch_record(contract, env, runtime))):
        files[name] = legacy.render(value)
        with (path / name).open('xb') as handle: handle.write(files[name])
    raw = legacy.render(inventory(files))
    with (path / 'inventory.json').open('xb') as handle: handle.write(raw)
    return sha(raw)


def check_artifact(artifact, env, role, identity, maximum_bytes):
    require(type(artifact.get('id')) is int and str(artifact['id']) == identity
        and artifact.get('name') == f'{ID}-{role}-{env["GITHUB_RUN_ID"]}-1'
        and artifact.get('expired') is False and artifact.get('workflow_run', {}).get('head_sha') == env['GITHUB_SHA']
        and str(artifact['workflow_run'].get('id')) == env['GITHUB_RUN_ID']
        and artifact['workflow_run'].get('head_branch') == 'phase-3-historical-snapshot'
        and type(artifact.get('size_in_bytes')) is int and 0 < artifact['size_in_bytes'] <= maximum_bytes
        and re.fullmatch(r'sha256:[0-9a-f]{64}', artifact.get('digest', '')), 'independent artifact identity differs')


def verify_preflight(files, contract, env, runtime, live_ref, artifact):
    require(set(files) == d.PREFLIGHT_FILES and sum(map(len, files.values())) <= d.previous.PREFLIGHT_LIMIT, 'bounded exact preflight required')
    require(sha(files['inventory.json']) == env.get('CENSUS_PREFLIGHT_SHA256'), 'independent preflight pin differs')
    exact(d.base.json_object(files['inventory.json']), inventory({n: b for n, b in files.items() if n != 'inventory.json'}),
        'preflight byte hashes differ')
    exact(d.base.json_object(files['contract.json']), contract, 'preflight contract differs')
    exact(d.base.json_object(files['launch.json']), launch_record(contract, env, runtime), 'preflight launch differs')
    d.check_ci(d.base.json_object(files['ci.json']), d.base.json_object(files['ci-jobs.json']), env)
    check_ref(d.base.json_object(files['consumed-ref.json']), env)
    check_ref(live_ref, env)
    check_artifact(artifact, env, 'consumption', env.get('CENSUS_PREFLIGHT_ARTIFACT_ID'), d.previous.PREFLIGHT_LIMIT)


def capture(*, root, output, launch_output, preflight, env, facts, now, runtime, live_ref, artifact,
        credential_loader, transport, session_factory=capture_engine.CaptureSession):
    contract = validate_registration(root)
    check_launch(contract, env, facts, now)
    verify_preflight(preflight, contract, env, runtime, live_ref, artifact)
    output = Path(output)
    require(not output.exists() and not any(p.is_symlink() for p in (output, *output.parents)), 'fresh capture output required')
    launch = legacy.RetainedFiles(launch_output)
    for name, raw in preflight.items(): launch.write('preflight-' + name, raw)
    launch.write('live-ref.json', legacy.render(live_ref))
    launch.write('artifact-metadata.json', legacy.render(artifact))
    result, failure = None, 'interrupted'
    try:
        key = credential_loader()
        runner = session_factory(contract, output=output, transport=transport, credential=key)
        result = runner.run()
        failure = None if result['protocol_complete'] else 'capture_failed'
        return result
    except Exception:
        failure = 'launch_or_capture_error'
        raise
    finally:
        links = {}
        for name in ('report.json', 'inventory.json'):
            path = output / name
            links[name] = {'bytes': path.stat().st_size, 'sha256': sha(path.read_bytes())} if path.is_file() else None
        launch.write('capture-link.json', legacy.render(seal({'contract_id': ID,
            'code_commit': env['GITHUB_SHA'], 'run_id': env['GITHUB_RUN_ID'],
            'preflight_inventory_sha256': env['CENSUS_PREFLIGHT_SHA256'], 'capture_files': links,
            'failure': failure, 'protocol_complete': result is not None and result['protocol_complete']})))


def verify_hosted(*, root, env, facts, now, runtime, live_ref, preflight_artifact,
        launch_artifact, capture_artifact, jobs, launch_zip, capture_zip):
    contract = validate_registration(root)
    check_launch(contract, env, facts, now)
    check_artifact(launch_artifact, env, 'launch', env.get('CENSUS_LAUNCH_ARTIFACT_ID'), d.previous.PREFLIGHT_LIMIT)
    check_artifact(capture_artifact, env, 'capture', env.get('CENSUS_CAPTURE_ARTIFACT_ID'), legacy.MAX_TOTAL)
    launch = read_archive(launch_zip, launch_artifact['size_in_bytes'], launch_artifact['digest'][7:])
    require(set(launch) == {'preflight-' + n for n in d.PREFLIGHT_FILES}
        | {'live-ref.json', 'artifact-metadata.json', 'capture-link.json'}, 'launch artifact population differs')
    preflight = {n: launch['preflight-' + n] for n in d.PREFLIGHT_FILES}
    verify_preflight(preflight, contract, env, runtime, live_ref, preflight_artifact)
    check_ref(d.base.json_object(launch['live-ref.json']), env)
    observed = d.base.json_object(launch['artifact-metadata.json'])
    for key in ('id', 'name', 'digest', 'size_in_bytes', 'workflow_run'):
        exact(observed[key], preflight_artifact[key], 'capture preflight artifact observation differs')
    require(jobs.get('total_count') == 3 and len(jobs.get('jobs', [])) == 3
        and {j['name'] for j in jobs['jobs']} == {'consume', 'capture', 'verify'}, 'hosted job inventory differs')
    for job in jobs['jobs']:
        require(str(job.get('run_id')) == env['GITHUB_RUN_ID'] and job.get('head_sha') == env['GITHUB_SHA'], 'job code/run differs')
        if job['name'] != 'verify':
            require(job['status'] == 'completed' and job['conclusion'] == 'success' and job['steps']
                and all(s['status'] == 'completed' and s['conclusion'] == 'success' for s in job['steps']),
                'capture or consumption did not fully succeed')
    result = capture_engine.verify_archive(capture_zip, expected_bytes=capture_artifact['size_in_bytes'],
        expected_sha256=capture_artifact['digest'][7:], expected_inventory_sha256=env.get('CENSUS_CAPTURE_INVENTORY_SHA256'),
        contract=contract)
    link = d.base.json_object(launch['capture-link.json'])
    d.base.verify_seal(link)
    import zipfile
    with zipfile.ZipFile(capture_zip) as archive:
        links = {n: {'bytes': len(archive.read(n)), 'sha256': sha(archive.read(n))} for n in ('report.json', 'inventory.json')}
    exact(link, seal({'contract_id': ID, 'code_commit': env['GITHUB_SHA'], 'run_id': env['GITHUB_RUN_ID'],
        'preflight_inventory_sha256': env['CENSUS_PREFLIGHT_SHA256'], 'capture_files': links,
        'failure': None, 'protocol_complete': True}), 'independent capture linkage differs')
    return seal({'contract_id': ID, 'code_commit': env['GITHUB_SHA'], 'run_id': env['GITHUB_RUN_ID'],
        'archive_verification': result, 'hosted_capture_provenance_verified': True,
        'consumption_ref': REF, 'capture_artifact_id': capture_artifact['id'],
        'launch_artifact_id': launch_artifact['id'], 'preflight_artifact_id': preflight_artifact['id'],
        'provider_requests_during_verification': 0, **legacy.BOUNDARY})
