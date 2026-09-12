"""One bounded repaired census with same-code CI and automatic offline verification."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from run_early_pullback_census_hosted_v02 import checkout_facts
from run_offline_python_v13 import deny_external_io

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('freeze', 'validate', 'prepare', 'capture', 'verify'))
    parser.add_argument('--check-launch', action='store_true')
    args = parser.parse_args()
    facts = checkout_facts() if args.check_launch or args.mode in ('prepare', 'capture', 'verify') else None
    if args.mode != 'capture': sys.addaudithook(deny_external_io)
    from momentumbot.research import census_capture_hosted as m
    env = {key: os.environ.get(key, '') for key in (*m.d.previous.ENV_KEYS,
        'CENSUS_LAUNCH_ARTIFACT_ID', 'CENSUS_CAPTURE_ARTIFACT_ID', 'CENSUS_CAPTURE_INVENTORY_SHA256')}
    now = datetime.now(timezone.utc)
    if args.mode == 'freeze': m.d.base.write_once(ROOT / m.CONTRACT_PATH, m.registration(ROOT))
    contract = m.validate_registration(ROOT)
    if facts: m.check_launch(contract, env, facts, now)
    if args.mode in ('freeze', 'validate'):
        print(json.dumps({'registration_sha256': contract['content_sha256'], 'provider_requests': 0}))
    elif args.mode == 'prepare':
        pin = m.prepare(Path('census-preflight'), contract, env, m.d.previous.runtime_facts())
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as handle: handle.write('inventory_sha256=' + pin + '\n')
    elif args.mode == 'capture':
        from momentumbot.research.early_pullback_census_http_v01 import DirectHTTPS
        def session(contract, **kwargs):
            return m.capture_engine.CaptureSession(contract, **kwargs, progress=lambda value: print(json.dumps(value), flush=True))
        try:
            result = m.capture(root=ROOT, output=Path('census-capture'), launch_output=Path('census-launch'),
                preflight=m.d.read_files(Path('census-preflight'), m.d.PREFLIGHT_FILES), env=env, facts=facts, now=now,
                runtime=m.d.previous.runtime_facts(), live_ref=m.d.base.json_object(Path('census-current-ref.json').read_bytes()),
                artifact=m.d.base.json_object(Path('census-preflight-artifact.json').read_bytes()),
                credential_loader=lambda: os.environ.get('MASSIVE_API_KEY', ''), transport=DirectHTTPS(), session_factory=session)
        finally:
            path = Path('census-capture/inventory.json')
            if path.is_file():
                with Path(os.environ['GITHUB_OUTPUT']).open('a') as handle: handle.write('inventory_sha256=' + m.sha(path.read_bytes()) + '\n')
        print(json.dumps({'protocol_complete': result['protocol_complete'], 'attempts': result['attempt_count'], 'failure': result['failure']}))
        return 0 if result['protocol_complete'] else 2
    else:
        read = lambda name: m.d.base.json_object(Path(name).read_bytes())
        result = m.verify_hosted(root=ROOT, env=env, facts=facts, now=now, runtime=m.d.previous.runtime_facts(),
            live_ref=read('census-current-ref.json'), preflight_artifact=read('census-preflight-artifact.json'),
            launch_artifact=read('census-launch-artifact.json'), capture_artifact=read('census-capture-artifact.json'),
            jobs=read('census-jobs.json'), launch_zip=Path('census-launch.zip'), capture_zip=Path('census-capture.zip'))
        out = Path('census-verification')
        out.mkdir(exist_ok=False)
        m.d.base.write_once(out / 'hosted-verification.json', result)
        for name in ('census-current-ref.json', 'census-preflight-artifact.json', 'census-launch-artifact.json',
                'census-capture-artifact.json', 'census-jobs.json'):
            (out / name).write_bytes(Path(name).read_bytes())
        print(json.dumps({'verification_sha256': result['content_sha256'],
            'attempts': result['archive_verification']['attempt_count'], 'dates_verified': len(result['archive_verification']['dates']),
            'provider_requests': 0}))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        print('Census gate or capture failed; evidence retained when available; no retry.', file=sys.stderr)
        sys.exit(2)
