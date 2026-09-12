"""One bounded, quarantined response diagnostic; same-commit CI gates transport."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import quote, quote_plus

from momentumbot.research import early_pullback_census_hosted_v02 as previous

adapter, base = previous.adapter, previous.base
require, exact, seal, sha = previous.require, previous.exact, previous.seal, previous.sha
ID = 'early-pullback-census-diagnostic-v0.1'
CONTRACT_PATH = f'research/strategy/{ID}.json'
BASE = f'research/data-audits/{ID}'
WORKFLOW_PATH = '.github/workflows/census-payload-diagnostic.yml'
REF = f'refs/tags/{ID}-consumed'
PARENT = '7e405354a5f24a0005cc7628a542acc0c23a29d6'
PARENT_REGISTRATION = '44f61029f59bce5fbf5d5b6555aed954ffbdd801bcd91362c78ac7632d9dadab'
USER_MESSAGE = 'Please continue. Also, this project is taking much much longer than it should. We need to expedite the project completion by cutting out unreasonable processes where necessary. I will leave you to determine that but do not sacrifice quality. You may proceed.'
OWN_FILES = ('src/momentumbot/research/census_payload_diagnostic.py',
    'scripts/run_census_payload_diagnostic.py', 'tests/test_census_payload_diagnostic.py',
    WORKFLOW_PATH, '.github/workflows/ci.yml')
PREFLIGHT_INPUTS = {'ci.json', 'ci-jobs.json', 'consumed-ref.json'}
PREFLIGHT_FILES = PREFLIGHT_INPUTS | {'contract.json', 'launch.json', 'inventory.json'}
SAFE_ERRORS = frozenset({
    'duplicate JSON key', 'non-finite JSON value', 'JSON object required',
    'provider response schema/status differs', 'bounded result list required', 'reported count differs',
    'metadata strings cannot be coerced', 'invalid metadata text', 'required metadata string missing',
    'unknown ticker metadata field', 'membership filter mismatch', 'provider page order regressed',
    'invalid bounded next URL', 'pagination origin or path differs', 'duplicate pagination parameter',
    'unregistered pagination parameter or embedded credential', 'pagination changed root query',
    'invalid opaque cursor', 'Massive reference ticker row is missing ticker'})


def request():
    return adapter.parent.census_request(adapter.DATES[0])


def registration(root):
    inherited = base.frozen(root / previous.CONTRACT_PATH)
    require(inherited['content_sha256'] == PARENT_REGISTRATION, 'immutable parent registration differs')
    paths = set(inherited['file_bindings']) | set(OWN_FILES) | {previous.CONTRACT_PATH,
        previous.BASE + '/hosted-failure-verification.json', previous.BASE + '/hosted-capture.zip'}
    bindings = {}
    for name in sorted(paths):
        path = root / name
        require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), 'regular bound file required')
        raw = path.read_bytes()
        bindings[name] = {'bytes': len(raw), 'sha256': sha(raw)}
        if name in inherited['file_bindings']:
            exact(bindings[name], inherited['file_bindings'][name], 'immutable ancestor bytes differ')
    return seal({'contract_id': ID, 'parent_commit': PARENT, 'parent_registration_sha256': PARENT_REGISTRATION,
        'file_bindings': bindings, 'requests': [request()], 'maximum_requests': 1,
        'maximum_response_bytes': adapter.MAX_BODY, 'retries': 0, 'pagination': False,
        'redirects': False, 'credential_name': 'MASSIVE_API_KEY', 'credential_fallback': False,
        'authorization': {'user_message': USER_MESSAGE, 'scope': 'one diagnostic of the first rejected membership envelope after same-commit full CI',
            'observed_date': '2026-09-12', 'expires_at': '2026-09-19T00:00:00Z',
            'estimated_incremental_api_cost_usd': '0.00', 'maximum_incremental_cost_usd': '10.00',
            'metered_purchase_authorized': False, 'subscription_changes_authorized': False,
            'account_entitlement_verified': False, 'credit_balance_verified': False,
            'pricing_source': 'https://massive.com/docs/rest/stocks/tickers/all-tickers'},
        'runtime': previous.RUNTIME, 'consumption_ref': REF,
        'hypothesis': 'retain credential-safe raw JSON and a fixed validation reason to diagnose, not relax, the frozen rejection',
        'diagnostic_data_quarantined': True, **adapter.BOUNDARY})


def validate_registration(root):
    saved = base.frozen(root / CONTRACT_PATH)
    exact(saved, registration(root), 'diagnostic registration differs')
    return saved


def check_launch(contract, env, facts, now):
    require(previous.stamp('2026-09-12T00:00:00Z') <= now < previous.stamp(contract['authorization']['expires_at']), 'diagnostic authorization expired or future')
    require(facts['clean'] is True and facts['head'] == env.get('GITHUB_SHA')
        and facts['parents'] == [PARENT] and facts['parent_commit'] == PARENT,
        'clean exact first code child required')
    require('A\t' + CONTRACT_PATH in facts['changed_files'], 'new explicit diagnostic registration required')
    require(env.get('GITHUB_REPOSITORY') == 'RoomyRems/momentumbot'
        and env.get('GITHUB_REF') == 'refs/heads/phase-3-historical-snapshot'
        and env.get('GITHUB_EVENT_NAME') == 'push' and env.get('GITHUB_RUN_ATTEMPT') == '1'
        and env.get('GITHUB_WORKFLOW_SHA') == facts['head']
        and env.get('GITHUB_WORKFLOW_REF') == 'RoomyRems/momentumbot/' + WORKFLOW_PATH + '@refs/heads/phase-3-historical-snapshot'
        and re.fullmatch(r'[1-9][0-9]*', env.get('GITHUB_RUN_ID', '')), 'exact first-attempt workflow push required')


def check_ci(ci, jobs, env):
    require(ci.get('run_attempt') == 1 and ci.get('head_branch') == 'phase-3-historical-snapshot', 'first-attempt branch CI required')
    previous.validate_ci(ci, jobs, {'code_commit_sha': env['GITHUB_SHA'], 'successful_code_ci_run_id': str(ci.get('id'))})


def check_ref(value, env):
    require(value.get('ref') == REF and value.get('object', {}).get('type') == 'commit'
        and value['object'].get('sha') == env['GITHUB_SHA'], 'create-only diagnostic consumption differs')


def launch_record(contract, env, runtime):
    exact(runtime, previous.RUNTIME, 'runtime differs')
    return seal({'contract_id': ID, 'contract_sha256': contract['content_sha256'],
        'code_commit': env['GITHUB_SHA'], 'run_id': env['GITHUB_RUN_ID'], 'run_attempt': 1,
        'consumption_ref': REF, 'runtime': runtime})


def read_files(path, expected):
    path = Path(path)
    require(path.is_dir() and not any(p.is_symlink() for p in (path, *path.parents)), 'regular preflight required')
    files = list(path.iterdir())
    require({p.name for p in files} == expected and all(p.is_file() and not p.is_symlink() for p in files), 'preflight population differs')
    require(sum(p.stat().st_size for p in files) <= previous.PREFLIGHT_LIMIT, 'preflight ceiling')
    return {p.name: p.read_bytes() for p in files}


def inventory(files):
    return seal({'contract_id': ID, 'files': {n: {'bytes': len(b), 'sha256': sha(b)} for n, b in sorted(files.items())}})


def prepare(path, contract, env, runtime):
    files = read_files(path, PREFLIGHT_INPUTS)
    check_ci(base.json_object(files['ci.json']), base.json_object(files['ci-jobs.json']), env)
    check_ref(base.json_object(files['consumed-ref.json']), env)
    for name, value in (('contract.json', contract), ('launch.json', launch_record(contract, env, runtime))):
        files[name] = adapter.render(value)
        with (path / name).open('xb') as handle:
            handle.write(files[name])
    raw = adapter.render(inventory(files))
    with (path / 'inventory.json').open('xb') as handle:
        handle.write(raw)
    return sha(raw)


def verify_preflight(files, contract, env, runtime, live_ref, artifact):
    require(set(files) == PREFLIGHT_FILES and sum(map(len, files.values())) <= previous.PREFLIGHT_LIMIT, 'bounded exact preflight required')
    require(sha(files['inventory.json']) == env.get('DIAGNOSTIC_PREFLIGHT_SHA256'), 'independent preflight pin differs')
    exact(base.json_object(files['inventory.json']), inventory({n: b for n, b in files.items() if n != 'inventory.json'}), 'preflight byte hashes differ')
    exact(base.json_object(files['contract.json']), contract, 'preflight contract differs')
    exact(base.json_object(files['launch.json']), launch_record(contract, env, runtime), 'preflight launch differs')
    check_ci(base.json_object(files['ci.json']), base.json_object(files['ci-jobs.json']), env)
    check_ref(base.json_object(files['consumed-ref.json']), env)
    check_ref(live_ref, env)
    require(type(artifact.get('id')) is int and str(artifact['id']) == env.get('DIAGNOSTIC_PREFLIGHT_ARTIFACT_ID')
        and artifact.get('name') == ID + '-consumption-' + env['GITHUB_RUN_ID'] + '-1'
        and artifact.get('expired') is False and artifact.get('workflow_run', {}).get('head_sha') == env['GITHUB_SHA']
        and str(artifact['workflow_run'].get('id')) == env['GITHUB_RUN_ID']
        and artifact['workflow_run'].get('head_branch') == 'phase-3-historical-snapshot'
        and type(artifact.get('size_in_bytes')) is int and 0 < artifact['size_in_bytes'] <= previous.PREFLIGHT_LIMIT
        and re.fullmatch(r'sha256:[0-9a-f]{64}', artifact.get('digest', '')), 'durable artifact differs')


def safe_to_retain(raw, credential):
    """Scan raw bytes AND every decoded string, retaining duplicate-key values."""
    needles = {credential, quote(credential, safe=''), quote_plus(credential), json.dumps(credential)[1:-1]}
    if any(n.encode() in raw for n in needles):
        return False, 'credential_echo'
    try:
        decoded = json.loads(raw, object_pairs_hook=list)
        stack = [decoded]
        while stack:
            value = stack.pop()
            if type(value) is str and any(n in value for n in needles):
                return False, 'credential_echo'
            if isinstance(value, (list, tuple)):
                stack.extend(value)
    except (ValueError, UnicodeError, RecursionError):
        return False, 'uninspectable_json'
    return True, None


def diagnose(raw):
    try:
        value = adapter.project_body(request(), raw)
    except Exception as error:
        label = str(error)
        return {'legacy_accepted': False, 'reason': label if label in SAFE_ERRORS else 'unclassified_validation_error',
                'rows_projected': None}
    return {'legacy_accepted': True, 'reason': None, 'rows_projected': value['raw_row_count']}


def capture(*, root, output, preflight, env, facts, now, runtime, live_ref, artifact, credential_loader, transport):
    contract = validate_registration(root)
    check_launch(contract, env, facts, now)
    verify_preflight(preflight, contract, env, runtime, live_ref, artifact)
    store = adapter.RetainedFiles(output)
    for name, raw in preflight.items():
        store.write('preflight-' + name, raw)
    store.write('live-ref.json', adapter.render(live_ref))
    store.write('artifact-metadata.json', adapter.render(artifact))
    result = {'attempts': 0, 'status': None, 'body_complete': False, 'body_bytes': None,
        'body_sha256': None, 'body_retained': False, 'diagnosis': None, 'failure': 'interrupted'}
    try:
        key = credential_loader()
        require(type(key) is str and 8 <= len(key) <= 1024 and key.isascii()
            and all(32 < ord(c) < 127 for c in key), 'invalid credential')
        intent = seal({'contract_id': ID, 'request': request(), 'started_at': datetime.now(timezone.utc).isoformat()})
        store.write('intent.json', adapter.render(intent))
        result['attempts'] = 1
        reply = transport(request(), key)
        require(type(reply) is dict and set(reply) == {'status', 'body', 'complete', 'encoding'}, 'transport observation differs')
        status, raw, complete = reply['status'], reply['body'], reply['complete']
        require(type(status) is int and 100 <= status <= 599 and type(raw) is bytes
            and len(raw) <= adapter.MAX_BODY + 1 and type(complete) is bool, 'bounded transport observation required')
        result.update(status=status, body_complete=complete, body_bytes=len(raw), body_sha256=sha(raw))
        if len(raw) > adapter.MAX_BODY:
            result['failure'] = 'response_too_large'
        elif not complete:
            result['failure'] = 'incomplete_body'
        elif reply['encoding'] not in ('', 'identity'):
            result['failure'] = 'content_encoding'
        elif status != 200:
            result['failure'] = 'http_error'
        else:
            safe, error = safe_to_retain(raw, key)
            result['failure'] = error
            if safe:
                store.write('response.body.json', raw, payload=True)
                result.update(body_retained=True, diagnosis=diagnose(raw))
    except Exception:
        result['failure'] = 'launch_or_transport_error'
    finally:
        report = seal({'contract_id': ID, **result, 'finished_at': datetime.now(timezone.utc).isoformat(),
            'diagnostic_only': True, **adapter.BOUNDARY})
        store.write('report.json', adapter.render(report))
        store.write('inventory.json', adapter.render(seal({'contract_id': ID, 'files': store.inventory()['files']})))
    return report
