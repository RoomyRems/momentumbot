"""Fixed alias capture using the existing hosted CI/consumption gate."""
import argparse
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import sys
import time

from run_coverage_continuation import gh, checkout_facts
from run_offline_python_v13 import deny_external_io

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REPO = 'RoomyRems/momentumbot'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare-sources', 'freeze', 'validate', 'consume', 'fetch', 'capture', 'verify'))
    parser.add_argument('--for-verification', action='store_true')
    parser.add_argument('--coverage-zip', type=Path)
    args = parser.parse_args()
    facts = checkout_facts() if args.mode in ('consume', 'fetch', 'capture', 'verify') else None
    if args.mode in ('prepare-sources', 'freeze', 'validate', 'verify'): sys.addaudithook(deny_external_io)
    from momentumbot.research import alias_completion as m
    gate = m.gate
    env = {k: os.environ.get(k, '') for k in gate.ENV_KEYS}
    now = datetime.now(timezone.utc)
    read = lambda name: m.parse(Path(name).read_bytes())
    if args.mode == 'prepare-sources':
        m.require(args.coverage_zip is not None, 'original coverage ZIP required')
        scanner, conflicts = m.prepare_sources(ROOT, args.coverage_zip, lambda value: print(json.dumps(value), flush=True))
        (ROOT / m.BASE).mkdir(exist_ok=False)
        with (ROOT / m.SCANNER_PATH).open('xb') as h: h.write(gzip.compress(m.render(scanner), mtime=0))
        gate.d.base.write_once(ROOT / m.CONFLICT_PATH, conflicts)
        print(json.dumps({'scanner_daily_sha256': scanner['content_sha256'], 'conflict_sha256': conflicts['content_sha256'], 'provider_requests': 0}))
        return 0
    if args.mode == 'freeze': gate.d.base.write_once(ROOT / m.CONTRACT_PATH, m.registration(ROOT))
    contract = m.validate_registration(ROOT)
    if facts: gate.check_launch(contract, env, facts, now)
    runtime = gate.d.previous.runtime_facts() if facts else None
    def output(pin):
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as h: h.write('inventory_sha256=' + pin + '\n')
    if args.mode in ('freeze', 'validate'):
        print(json.dumps({'registration_sha256': contract['content_sha256'], 'provider_requests': 0}))
    elif args.mode == 'consume':
        path = Path('source-preflight')
        path.mkdir(exist_ok=False)
        ci_id = None
        for _ in range(20):
            runs = json.loads(gh('run', 'list', '--repo', REPO, '--workflow', 'ci.yml', '--commit', env['GITHUB_SHA'], '--event', 'push', '--json', 'databaseId'))
            if runs:
                ci_id = str(runs[0]['databaseId'])
                break
            time.sleep(3)
        m.require(ci_id is not None, 'exact-code CI missing')
        gh('run', 'watch', ci_id, '--repo', REPO, '--exit-status', '--interval', '15', timeout=900)
        gh('api', f'repos/{REPO}/actions/runs/{ci_id}', output=path / 'ci.json')
        gh('api', f'repos/{REPO}/actions/runs/{ci_id}/jobs?per_page=100', output=path / 'ci-jobs.json')
        gate.d.check_ci(read(path / 'ci.json'), read(path / 'ci-jobs.json'), env)
        gh('api', '--method', 'POST', f'repos/{REPO}/git/refs', '-f', 'ref=' + m.REF, '-f', 'sha=' + env['GITHUB_SHA'], output=path / 'consumed-ref.json')
        output(gate.prepare(path, contract, env, runtime))
    elif args.mode == 'fetch':
        gh('api', f'repos/{REPO}/git/ref/' + m.REF.removeprefix('refs/'), output='source-current-ref.json')
        identity = env['PREFLIGHT_ARTIFACT_ID']
        m.require(identity.isdecimal(), 'preflight artifact ID required')
        gh('api', f'repos/{REPO}/actions/artifacts/{identity}', output='source-preflight-artifact.json')
        gate.check_artifact(read('source-preflight-artifact.json'), contract, env, 'consumption', identity, gate.d.previous.PREFLIGHT_LIMIT)
        gh('api', f'repos/{REPO}/actions/artifacts/{identity}/zip', output='source-preflight.zip')
        if args.for_verification:
            identity = env['CAPTURE_ARTIFACT_ID']
            m.require(identity.isdecimal(), 'capture artifact ID required')
            gh('api', f'repos/{REPO}/actions/artifacts/{identity}', output='source-capture-artifact.json')
            gate.check_artifact(read('source-capture-artifact.json'), contract, env, 'capture', identity, m.MAX_TOTAL)
            gh('api', f'repos/{REPO}/actions/artifacts/{identity}/zip', output='source-capture.zip')
            gh('api', f'repos/{REPO}/actions/runs/{env["GITHUB_RUN_ID"]}/jobs?per_page=100', output='source-jobs.json')
    elif args.mode == 'capture':
        try:
            result = m.capture(ROOT, env, facts, now, runtime, Path('source-preflight.zip'),
                read('source-preflight-artifact.json'), read('source-current-ref.json'), output=Path('source-capture'),
                credential_loader=lambda: {k: os.environ.get(k, '') for k in m.KEYS}, transport=m.Transport(),
                progress=lambda value: print(json.dumps(value), flush=True))
        finally:
            path = Path('source-capture/inventory.json')
            if path.is_file(): output(m.sha(path.read_bytes()))
        print(json.dumps({k: result[k] for k in ('protocol_complete', 'attempt_count', 'failure')}))
        return 0 if result['protocol_complete'] else 2
    else:
        result = m.verify(ROOT, env, facts, now, runtime, Path('source-preflight.zip'),
            read('source-preflight-artifact.json'), read('source-current-ref.json'), Path('source-capture.zip'),
            read('source-capture-artifact.json'), read('source-jobs.json'))
        completed = m.completion(ROOT, result)
        out = Path('source-verification')
        out.mkdir(exist_ok=False)
        gate.d.base.write_once(out / 'hosted-verification.json', result)
        gate.d.base.write_once(out / 'completion.json', completed)
        for name in ('source-preflight-artifact.json', 'source-capture-artifact.json', 'source-current-ref.json', 'source-jobs.json'):
            (out / name).write_bytes(Path(name).read_bytes())
        print(json.dumps({'verification_sha256': result['content_sha256'], 'completion_sha256': completed['content_sha256'],
            'aliases_match': completed['alias_mapping_checks_complete'], 'figi_views_consistent': completed['distinct_figi_asof_views_consistent'],
            'scanner_previous_closes': completed['scanner_previous_closes'], 'provider_requests': 0}))
    return 0


if __name__ == '__main__':
    try: sys.exit(main())
    except Exception:
        print('Alias gate or capture failed; safe evidence retained when available; no retry.', file=sys.stderr)
        sys.exit(2)
