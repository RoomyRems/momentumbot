"""Shared hosted source lifecycle; scanner modules supply their own protocol."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from run_coverage_continuation import gh, checkout_facts
from run_offline_python_v13 import deny_external_io

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REPO = 'RoomyRems/momentumbot'


def main(m):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('freeze', 'validate', 'consume', 'fetch', 'capture', 'verify'))
    parser.add_argument('--for-verification', action='store_true')
    args = parser.parse_args()
    facts = checkout_facts() if args.mode not in ('freeze', 'validate') else None
    if args.mode in ('freeze', 'validate', 'verify'): sys.addaudithook(deny_external_io)
    gate = m.gate
    env = {k: os.environ.get(k, '') for k in gate.ENV_KEYS}
    now = datetime.now(timezone.utc)
    read = lambda path: m.parse(Path(path).read_bytes())
    if args.mode == 'freeze': gate.d.base.write_once(ROOT / m.CONTRACT_PATH, m.registration(ROOT))
    contract = m.validate_registration(ROOT)
    if facts: gate.check_launch(contract, env, facts, now)
    runtime = gate.d.previous.runtime_facts() if facts else None
    def output(pin):
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as h: h.write('inventory_sha256=' + pin + '\n')
    if args.mode in ('freeze', 'validate'):
        print(json.dumps({'registration_sha256': contract['content_sha256'], 'roots': len(contract['requests']), 'provider_requests': 0}))
    elif args.mode == 'consume':
        path = Path('source-preflight')
        path.mkdir(exist_ok=False)
        # CI is triggered by the same push and is already present after runtime setup.
        runs = json.loads(gh('run', 'list', '--repo', REPO, '--workflow', 'ci.yml', '--commit', env['GITHUB_SHA'],
            '--event', 'push', '--json', 'databaseId'))
        m.require(len(runs) == 1, 'one exact-code CI run required')
        ci_id = str(runs[0]['databaseId'])
        gh('run', 'watch', ci_id, '--repo', REPO, '--exit-status', '--interval', '15', timeout=900)
        gh('api', f'repos/{REPO}/actions/runs/{ci_id}', output=path / 'ci.json')
        gh('api', f'repos/{REPO}/actions/runs/{ci_id}/jobs?per_page=100', output=path / 'ci-jobs.json')
        gate.d.check_ci(read(path / 'ci.json'), read(path / 'ci-jobs.json'), env)
        gh('api', '--method', 'POST', f'repos/{REPO}/git/refs', '-f', 'ref=' + m.REF,
            '-f', 'sha=' + env['GITHUB_SHA'], output=path / 'consumed-ref.json')
        output(gate.prepare(path, contract, env, runtime))
    elif args.mode == 'fetch':
        gh('api', f'repos/{REPO}/git/ref/' + m.REF.removeprefix('refs/'), output='source-current-ref.json')
        roles = [('consumption', 'PREFLIGHT_ARTIFACT_ID', 'preflight', gate.d.previous.PREFLIGHT_LIMIT)]
        if args.for_verification: roles.append(('capture', 'CAPTURE_ARTIFACT_ID', 'capture', m.MAX_TOTAL))
        for role, key, name, ceiling in roles:
            identity = env[key]
            m.require(identity.isdecimal(), 'artifact identity required')
            metadata = f'source-{name}-artifact.json'
            gh('api', f'repos/{REPO}/actions/artifacts/{identity}', output=metadata)
            gate.check_artifact(read(metadata), contract, env, role, identity, ceiling)
            gh('api', f'repos/{REPO}/actions/artifacts/{identity}/zip', output=f'source-{name}.zip', timeout=900)
        if args.for_verification:
            gh('api', f'repos/{REPO}/actions/runs/{env["GITHUB_RUN_ID"]}/jobs?per_page=100', output='source-jobs.json')
    else:
        inputs = (ROOT, env, facts, now, runtime, Path('source-preflight.zip'),
            read('source-preflight-artifact.json'), read('source-current-ref.json'))
        if args.mode == 'capture':
            try:
                result = m.capture(*inputs, output=Path('source-capture'),
                    credential_loader=lambda: {k: os.environ.get(k, '') for k in m.KEYS}, transport=m.Transport(),
                    progress=lambda v: print(json.dumps(v), flush=True))
            finally:
                path = Path('source-capture/inventory.json')
                if path.is_file(): output(m.sha(path.read_bytes()))
            print(json.dumps({k: result[k] for k in ('protocol_complete', 'attempt_count', 'failure')}))
            return 0 if result['protocol_complete'] else 2
        result = m.verify(*inputs, Path('source-capture.zip'), read('source-capture-artifact.json'), read('source-jobs.json'))
        out = Path('source-verification')
        out.mkdir(exist_ok=False)
        gate.d.base.write_once(out / 'hosted-verification.json', result)
        for name in ('source-preflight-artifact.json', 'source-capture-artifact.json', 'source-current-ref.json', 'source-jobs.json'):
            (out / name).write_bytes(Path(name).read_bytes())
        print(json.dumps({'verification_sha256': result['content_sha256'],
            **{k: result['archive_verification'][k] for k in ('attempt_count', 'bar_count', 'symbol_dates', 'empty_symbol_dates')},
            'provider_requests': 0}))
    return 0
