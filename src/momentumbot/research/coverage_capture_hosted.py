"""Same-code CI and independent single-use authority for coverage/identity capture."""
from datetime import datetime, timezone
from pathlib import Path
import re

from momentumbot.research import coverage_capture as c
from momentumbot.research.census_payload_evidence import read_archive

ID, d = c.ID, c.d
require, exact, seal, sha, render, parse = c.require, c.exact, c.seal, c.sha, c.render, c.parse
CONTRACT_PATH = 'research/strategy/' + ID + '.json'
WORKFLOW = '.github/workflows/coverage-capture.yml'
REF = 'refs/tags/' + ID + '-consumed'
PARENT = 'e23fbe16432e863c1c8b6b9c6778129ac60bf3f6'
ENV_KEYS = ('GITHUB_SHA', 'GITHUB_REPOSITORY', 'GITHUB_REF', 'GITHUB_EVENT_NAME',
    'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_WORKFLOW_SHA', 'GITHUB_WORKFLOW_REF',
    'PREFLIGHT_SHA256', 'PREFLIGHT_ARTIFACT_ID', 'CAPTURE_ARTIFACT_ID', 'CAPTURE_INVENTORY_SHA256')
FILES = ('src/momentumbot/research/coverage_capture.py',
    'src/momentumbot/research/coverage_capture_hosted.py', 'scripts/run_coverage_capture.py',
    'tests/test_coverage_capture.py', WORKFLOW, '.github/workflows/ci.yml', 'requirements-sealed-source-v04.txt')


def registration(root):
    parent = c.daily.validate_registration(root)
    return seal({'contract_id': ID, 'parent_commit': PARENT,
        'parent_registration_sha256': parent['content_sha256'],
        'file_bindings': {name: {'bytes': (Path(root) / name).stat().st_size,
            'sha256': sha((Path(root) / name).read_bytes())} for name in FILES},
        'selected_dates': list(c.b.DATES), 'panel_sha256': c.daily.PANEL_SEAL,
        'limits': {'maximum_attempts': c.MAX_ATTEMPTS, 'maximum_body_bytes': c.daily.MAX_BODY,
            'maximum_capture_duration_ns': c.MAX_DURATION_NS, 'report_reserve_bytes': c.REPORT_RESERVE,
            'maximum_payload_bytes': c.MAX_PAYLOAD, 'maximum_metadata_bytes': c.MAX_METADATA,
            'daily_pages_per_root': c.daily.MAX_PAGES, 'identity_pages_per_root': c.ACTION_PAGES,
            'provider_start_interval_ns': c.INTERVAL_NS, 'retries': 0, 'redirects': 0},
        'authorization': {'user_message': 'You may proceed with development', 'observed_date': '2026-09-14',
            'scope': 'one bounded fixed 30-date daily coverage and 120-day corporate-action capture after exact-code CI',
            'expires_at': '2026-09-21T00:00:00Z', 'estimated_incremental_api_cost_usd': '0.00',
            'maximum_incremental_cost_usd': '10.00', 'billing_cap_provider_enforced': False,
            'account_entitlement_verified': False, 'credit_balance_verified': False,
            'metered_purchase_authorized': False, 'subscription_changes_authorized': False},
        'consumption_ref': REF, 'runtime': d.previous.RUNTIME,
        'credential_names': list(c.KEYS), 'credential_fallback': False,
        'automatic_original_archive_verification': True, **c.b.BOUNDARY})


def validate_registration(root):
    saved = parse((Path(root) / CONTRACT_PATH).read_bytes())
    exact(saved, registration(root), 'coverage capture registration differs')
    return saved


def check_launch(contract, env, facts, now):
    require(datetime(2026, 9, 14, tzinfo=timezone.utc) <= now
        < datetime.fromisoformat(contract['authorization']['expires_at'].replace('Z', '+00:00')), 'authorization window differs')
    require(facts['clean'] is True and facts['head'] == env.get('GITHUB_SHA') and facts['parents'] == [PARENT]
        and facts['parent_commit'] == PARENT and 'A\t' + CONTRACT_PATH in facts['changed_files'], 'exact clean new child required')
    require(env.get('GITHUB_REPOSITORY') == 'RoomyRems/momentumbot'
        and env.get('GITHUB_REF') == 'refs/heads/phase-3-historical-snapshot'
        and env.get('GITHUB_EVENT_NAME') == 'push' and env.get('GITHUB_RUN_ATTEMPT') == '1'
        and env.get('GITHUB_WORKFLOW_SHA') == facts['head']
        and env.get('GITHUB_WORKFLOW_REF') == 'RoomyRems/momentumbot/' + WORKFLOW + '@refs/heads/phase-3-historical-snapshot'
        and re.fullmatch(r'[1-9][0-9]*', env.get('GITHUB_RUN_ID', '')), 'first-attempt exact workflow required')


def check_ref(value, env):
    require(value.get('ref') == REF and value.get('object', {}).get('type') == 'commit'
        and value['object'].get('sha') == env['GITHUB_SHA'], 'permanent consumption differs')


def inventory(files):
    return seal({'contract_id': ID, 'files': {name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in sorted(files.items())}})


def launch(contract, env, runtime):
    exact(runtime, d.previous.RUNTIME, 'runtime differs')
    return seal({'contract_id': ID, 'contract_sha256': contract['content_sha256'],
        'code_commit': env['GITHUB_SHA'], 'run_id': env['GITHUB_RUN_ID'], 'run_attempt': 1,
        'consumption_ref': REF, 'runtime': runtime})


def prepare(path, contract, env, runtime):
    files = d.read_files(path, d.PREFLIGHT_INPUTS)
    d.check_ci(parse(files['ci.json']), parse(files['ci-jobs.json']), env)
    check_ref(parse(files['consumed-ref.json']), env)
    for name, value in (('contract.json', contract), ('launch.json', launch(contract, env, runtime))):
        files[name] = render(value)
        with (path / name).open('xb') as handle: handle.write(files[name])
    raw = render(inventory(files))
    with (path / 'inventory.json').open('xb') as handle: handle.write(raw)
    return sha(raw)


def check_artifact(value, env, role, identity, ceiling):
    require(type(value.get('id')) is int and str(value['id']) == identity
        and value.get('name') == f'{ID}-{role}-{env["GITHUB_RUN_ID"]}-1' and value.get('expired') is False
        and value.get('workflow_run', {}).get('head_sha') == env['GITHUB_SHA']
        and str(value['workflow_run'].get('id')) == env['GITHUB_RUN_ID']
        and value['workflow_run'].get('head_branch') == 'phase-3-historical-snapshot'
        and type(value.get('size_in_bytes')) is int and 0 < value['size_in_bytes'] <= ceiling
        and re.fullmatch(r'sha256:[0-9a-f]{64}', value.get('digest', '')), 'artifact identity differs')


def verify_preflight(files, contract, env, runtime, live_ref, artifact):
    require(set(files) == d.PREFLIGHT_FILES and sum(map(len, files.values())) <= d.previous.PREFLIGHT_LIMIT,
        'bounded exact preflight required')
    require(sha(files['inventory.json']) == env.get('PREFLIGHT_SHA256'), 'independent preflight pin differs')
    exact(parse(files['inventory.json']), inventory({n: r for n, r in files.items() if n != 'inventory.json'}), 'preflight bytes differ')
    exact(parse(files['contract.json']), contract, 'preflight contract differs')
    exact(parse(files['launch.json']), launch(contract, env, runtime), 'preflight launch differs')
    d.check_ci(parse(files['ci.json']), parse(files['ci-jobs.json']), env)
    check_ref(parse(files['consumed-ref.json']), env)
    check_ref(live_ref, env)
    check_artifact(artifact, env, 'consumption', env.get('PREFLIGHT_ARTIFACT_ID'), d.previous.PREFLIGHT_LIMIT)


def capture(root, env, facts, now, runtime, preflight, live_ref, artifact, *, output, credential_loader, transport, progress):
    contract = validate_registration(root)
    check_launch(contract, env, facts, now)
    verify_preflight(preflight, contract, env, runtime, live_ref, artifact)
    output = Path(output)
    require(not output.exists() and not any(p.is_symlink() for p in (output, *output.parents)), 'fresh capture output required')
    panel = c.daily.load_panel(root)
    # Credential loader is deliberately last, after all external authority and source checks.
    runner = c.Capture(contract, panel, output=output, keys=credential_loader(), transport=transport, progress=progress)
    return runner.run()


def verify(root, env, facts, now, runtime, live_ref, preflight_artifact, capture_artifact, jobs, preflight_zip, capture_zip):
    contract = validate_registration(root)
    check_launch(contract, env, facts, now)
    check_artifact(preflight_artifact, env, 'consumption', env.get('PREFLIGHT_ARTIFACT_ID'), d.previous.PREFLIGHT_LIMIT)
    files = read_archive(preflight_zip, preflight_artifact['size_in_bytes'], preflight_artifact['digest'][7:])
    verify_preflight(files, contract, env, runtime, live_ref, preflight_artifact)
    check_artifact(capture_artifact, env, 'capture', env.get('CAPTURE_ARTIFACT_ID'), c.MAX_TOTAL)
    require(jobs.get('total_count') == len(jobs.get('jobs', [])) == 3
        and {j['name'] for j in jobs['jobs']} == {'consume', 'capture', 'verify'}, 'hosted jobs differ')
    for job in jobs['jobs']:
        require(str(job.get('run_id')) == env['GITHUB_RUN_ID'] and job.get('head_sha') == env['GITHUB_SHA'], 'job code/run differs')
        if job['name'] != 'verify':
            require(job['status'] == 'completed' and job['conclusion'] == 'success' and job['steps']
                and all(s['status'] == 'completed' and s['conclusion'] == 'success' for s in job['steps']), 'job/step failed')
    result = c.verify_archive(capture_zip, expected_bytes=capture_artifact['size_in_bytes'],
        expected_sha256=capture_artifact['digest'][7:], expected_inventory_sha256=env.get('CAPTURE_INVENTORY_SHA256'),
        contract=contract, panel=c.daily.load_panel(root))
    return seal({'contract_id': ID, 'code_commit': env['GITHUB_SHA'], 'run_id': env['GITHUB_RUN_ID'],
        'archive_verification': result, 'hosted_capture_provenance_verified': True,
        'consumption_ref': REF, 'capture_artifact_id': capture_artifact['id'],
        'preflight_artifact_id': preflight_artifact['id'], 'provider_requests_during_verification': 0, **c.b.BOUNDARY})
