"""Gated continuation: exact retained prefix, no-retry suffix, original-ZIP replay."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from run_early_pullback_census_hosted_v02 import checkout_facts
from run_offline_python_v13 import deny_external_io

ROOT = Path(__file__).resolve().parents[1]
REPO = 'RoomyRems/momentumbot'


def gh(*args, output=None, timeout=120):
    if output is not None:
        with Path(output).open('xb') as handle:
            subprocess.run(['gh', *args], stdout=handle, check=True, timeout=timeout)
        return None
    return subprocess.check_output(['gh', *args], text=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('freeze', 'validate', 'consume', 'fetch', 'capture', 'verify'))
    parser.add_argument('--for-verification', action='store_true')
    args = parser.parse_args()
    facts = checkout_facts() if args.mode not in ('freeze', 'validate') else None
    if args.mode in ('freeze', 'validate', 'verify'): sys.addaudithook(deny_external_io)
    from momentumbot.research import coverage_continuation_hosted as m
    c, gate = m.c, m.gate
    env = {key: os.environ.get(key, '') for key in gate.ENV_KEYS}
    now = datetime.now(timezone.utc)
    if args.mode == 'freeze': gate.d.base.write_once(ROOT / m.CONTRACT_PATH, m.registration(ROOT))
    contract = m.validate_registration(ROOT)
    if facts: gate.check_launch(contract, env, facts, now)
    runtime = gate.d.previous.runtime_facts() if facts else None
    read = lambda path: c.parse(Path(path).read_bytes())
    def output(pin):
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as handle: handle.write('inventory_sha256=' + pin + '\n')
    if args.mode in ('freeze', 'validate'):
        print(json.dumps({'registration_sha256': contract['content_sha256'], 'provider_requests': 0}))
    elif args.mode == 'consume':
        path = Path('source-preflight')
        path.mkdir(exist_ok=False)
        ci_id = None
        for _ in range(20):
            runs = json.loads(gh('run', 'list', '--repo', REPO, '--workflow', 'ci.yml', '--commit', env['GITHUB_SHA'],
                '--event', 'push', '--json', 'databaseId'))
            if runs:
                ci_id = str(runs[0]['databaseId'])
                break
            time.sleep(3)
        c.require(ci_id is not None, 'exact-code CI missing')
        gh('run', 'watch', ci_id, '--repo', REPO, '--exit-status', '--interval', '15', timeout=900)
        gh('api', f'repos/{REPO}/actions/runs/{ci_id}', output=path / 'ci.json')
        gh('api', f'repos/{REPO}/actions/runs/{ci_id}/jobs?per_page=100', output=path / 'ci-jobs.json')
        gate.d.check_ci(read(path / 'ci.json'), read(path / 'ci-jobs.json'), env)
        gh('api', '--method', 'POST', f'repos/{REPO}/git/refs', '-f', 'ref=' + m.REF,
            '-f', 'sha=' + env['GITHUB_SHA'], output=path / 'consumed-ref.json')
        output(gate.prepare(path, contract, env, runtime))
    elif args.mode == 'fetch':
        gh('api', f'repos/{REPO}/git/ref/' + m.REF.removeprefix('refs/'), output='source-current-ref.json')
        identity = env['PREFLIGHT_ARTIFACT_ID']
        c.require(identity.isdecimal(), 'preflight artifact ID required')
        gh('api', f'repos/{REPO}/actions/artifacts/{identity}', output='source-preflight-artifact.json')
        gate.check_artifact(read('source-preflight-artifact.json'), contract, env, 'consumption', identity, gate.d.previous.PREFLIGHT_LIMIT)
        gh('api', f'repos/{REPO}/actions/artifacts/{identity}/zip', output='source-preflight.zip')
        if args.for_verification:
            identity = env['CAPTURE_ARTIFACT_ID']
            c.require(identity.isdecimal(), 'capture artifact ID required')
            gh('api', f'repos/{REPO}/actions/artifacts/{identity}', output='source-capture-artifact.json')
            gate.check_artifact(read('source-capture-artifact.json'), contract, env, 'capture', identity, c.old.MAX_TOTAL)
            gh('api', f'repos/{REPO}/actions/artifacts/{identity}/zip', output='source-capture.zip', timeout=600)
            gh('api', f'repos/{REPO}/actions/runs/{env["GITHUB_RUN_ID"]}/jobs?per_page=100', output='source-jobs.json')
        else:
            gh('api', f'repos/{REPO}/actions/artifacts/{c.PREFIX_PIN["artifact_id"]}', output='source-prefix-artifact.json')
            m.check_prefix_artifact(read('source-prefix-artifact.json'))
    elif args.mode == 'capture':
        try:
            result = m.capture(ROOT, env, facts, now, runtime, Path('source-preflight.zip'),
                read('source-preflight-artifact.json'), read('source-current-ref.json'),
                ROOT / c.PREFIX_PATH, read('source-prefix-artifact.json'), output=Path('source-capture'),
                credential_loader=lambda: {key: os.environ.get(key, '') for key in c.old.KEYS}, transport=c.old.DirectHTTPS(),
                progress=lambda value: print(json.dumps(value), flush=True))
        finally:
            path = Path('source-capture/inventory.json')
            if path.is_file(): output(c.sha(path.read_bytes()))
        print(json.dumps({k: result[k] for k in ('protocol_complete', 'new_attempt_count', 'reused_attempt_count', 'failure')}))
        return 0 if result['protocol_complete'] else 2
    else:
        result = m.verify(ROOT, env, facts, now, runtime, Path('source-preflight.zip'),
            read('source-preflight-artifact.json'), read('source-current-ref.json'), Path('source-capture.zip'),
            read('source-capture-artifact.json'), read('source-jobs.json'), Path('source-verified-prefix.zip'))
        out = Path('source-verification')
        out.mkdir(exist_ok=False)
        gate.d.base.write_once(out / 'hosted-verification.json', result)
        for name in ('source-preflight-artifact.json', 'source-capture-artifact.json', 'source-current-ref.json', 'source-jobs.json'):
            (out / name).write_bytes(Path(name).read_bytes())
        print(json.dumps({'verification_sha256': result['content_sha256'], 'provider_requests': 0}))
    return 0


if __name__ == '__main__':
    try: sys.exit(main())
    except Exception:
        print('Continuation gate or capture failed; safe evidence retained when available; no retry.', file=sys.stderr)
        sys.exit(2)
