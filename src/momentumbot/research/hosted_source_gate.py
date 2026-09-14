"""Reusable exact-code CI, durable consumption, and artifact provenance gates."""
from datetime import datetime, timezone
from pathlib import Path
import re

from momentumbot.research import census_payload_diagnostic as d

require, exact, seal, sha = d.require, d.exact, d.seal, d.sha
render, parse = d.adapter.render, d.base.json_object
ENV_KEYS = ('GITHUB_SHA', 'GITHUB_REPOSITORY', 'GITHUB_REF', 'GITHUB_EVENT_NAME',
    'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_WORKFLOW_SHA', 'GITHUB_WORKFLOW_REF',
    'PREFLIGHT_SHA256', 'PREFLIGHT_ARTIFACT_ID', 'CAPTURE_ARTIFACT_ID', 'CAPTURE_INVENTORY_SHA256')


def check_launch(contract, env, facts, now):
    require(d.previous.stamp(contract['authorization']['starts_at']) <= now
        < d.previous.stamp(contract['authorization']['expires_at']), 'authorization window differs')
    require(facts['clean'] is True and facts['head'] == env.get('GITHUB_SHA')
        and facts['parents'] == [contract['parent_commit']] and facts['parent_commit'] == contract['parent_commit']
        and 'A\t' + contract['contract_path'] in facts['changed_files'], 'exact clean new child required')
    require(env.get('GITHUB_REPOSITORY') == 'RoomyRems/momentumbot'
        and env.get('GITHUB_REF') == 'refs/heads/phase-3-historical-snapshot'
        and env.get('GITHUB_EVENT_NAME') == 'push' and env.get('GITHUB_RUN_ATTEMPT') == '1'
        and env.get('GITHUB_WORKFLOW_SHA') == facts['head']
        and env.get('GITHUB_WORKFLOW_REF') == 'RoomyRems/momentumbot/' + contract['workflow'] + '@refs/heads/phase-3-historical-snapshot'
        and re.fullmatch(r'[1-9][0-9]*', env.get('GITHUB_RUN_ID', '')), 'first-attempt exact workflow required')


def check_ref(value, contract, env):
    require(value.get('ref') == contract['consumption_ref'] and value.get('object', {}).get('type') == 'commit'
        and value['object'].get('sha') == env['GITHUB_SHA'], 'permanent consumption differs')


def inventory(files, contract):
    return seal({'contract_id': contract['contract_id'], 'files': {
        name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in sorted(files.items())}})


def launch(contract, env, runtime):
    exact(runtime, contract['runtime'], 'runtime differs')
    return seal({'contract_id': contract['contract_id'], 'contract_sha256': contract['content_sha256'],
        'code_commit': env['GITHUB_SHA'], 'run_id': env['GITHUB_RUN_ID'], 'run_attempt': 1,
        'consumption_ref': contract['consumption_ref'], 'runtime': runtime})


def prepare(path, contract, env, runtime):
    files = d.read_files(path, d.PREFLIGHT_INPUTS)
    d.check_ci(parse(files['ci.json']), parse(files['ci-jobs.json']), env)
    check_ref(parse(files['consumed-ref.json']), contract, env)
    for name, value in (('contract.json', contract), ('launch.json', launch(contract, env, runtime))):
        files[name] = render(value)
        with (path / name).open('xb') as handle: handle.write(files[name])
    raw = render(inventory(files, contract))
    with (path / 'inventory.json').open('xb') as handle: handle.write(raw)
    return sha(raw)


def check_artifact(value, contract, env, role, identity, ceiling):
    require(type(value.get('id')) is int and str(value['id']) == identity
        and value.get('name') == f'{contract["contract_id"]}-{role}-{env["GITHUB_RUN_ID"]}-1'
        and value.get('expired') is False and value.get('workflow_run', {}).get('head_sha') == env['GITHUB_SHA']
        and str(value['workflow_run'].get('id')) == env['GITHUB_RUN_ID']
        and value['workflow_run'].get('head_branch') == 'phase-3-historical-snapshot'
        and type(value.get('size_in_bytes')) is int and 0 < value['size_in_bytes'] <= ceiling
        and re.fullmatch(r'sha256:[0-9a-f]{64}', value.get('digest', '')), 'artifact identity differs')


def verify_preflight(files, contract, env, runtime, live_ref, artifact):
    require(set(files) == d.PREFLIGHT_FILES and sum(map(len, files.values())) <= d.previous.PREFLIGHT_LIMIT,
        'bounded exact preflight required')
    require(sha(files['inventory.json']) == env.get('PREFLIGHT_SHA256'), 'independent preflight pin differs')
    exact(parse(files['inventory.json']), inventory({n: r for n, r in files.items() if n != 'inventory.json'}, contract), 'preflight bytes differ')
    exact(parse(files['contract.json']), contract, 'preflight contract differs')
    exact(parse(files['launch.json']), launch(contract, env, runtime), 'preflight launch differs')
    d.check_ci(parse(files['ci.json']), parse(files['ci-jobs.json']), env)
    check_ref(parse(files['consumed-ref.json']), contract, env)
    check_ref(live_ref, contract, env)
    check_artifact(artifact, contract, env, 'consumption', env.get('PREFLIGHT_ARTIFACT_ID'), d.previous.PREFLIGHT_LIMIT)


def check_jobs(jobs, env):
    require(jobs.get('total_count') == len(jobs.get('jobs', [])) == 3
        and {j['name'] for j in jobs['jobs']} == {'consume', 'capture', 'verify'}, 'hosted jobs differ')
    for job in jobs['jobs']:
        require(str(job.get('run_id')) == env['GITHUB_RUN_ID'] and job.get('head_sha') == env['GITHUB_SHA'], 'job code/run differs')
        if job['name'] != 'verify':
            require(job['status'] == 'completed' and job['conclusion'] == 'success' and job['steps']
                and all(s['status'] == 'completed' and s['conclusion'] == 'success' for s in job['steps']), 'job/step failed')
