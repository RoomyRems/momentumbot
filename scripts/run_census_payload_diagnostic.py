"""Same-commit CI-gated one-request payload diagnostic; no retries."""
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
    parser.add_argument('mode', choices=['register', 'validate', 'prepare', 'capture'])
    parser.add_argument('--check-launch', action='store_true')
    args = parser.parse_args()
    facts = checkout_facts() if args.check_launch or args.mode in ('prepare', 'capture') else None
    if args.mode != 'capture':
        sys.addaudithook(deny_external_io)
    from momentumbot.research import census_payload_diagnostic as m
    env = {key: os.environ.get(key, '') for key in (*m.previous.ENV_KEYS,
        'DIAGNOSTIC_PREFLIGHT_SHA256', 'DIAGNOSTIC_PREFLIGHT_ARTIFACT_ID')}
    now = datetime.now(timezone.utc)
    if args.mode == 'register':
        m.base.write_once(ROOT / m.CONTRACT_PATH, m.registration(ROOT))
    contract = m.validate_registration(ROOT)
    if facts:
        m.check_launch(contract, env, facts, now)
    if args.mode in ('register', 'validate'):
        print(json.dumps({'registration_sha256': contract['content_sha256'], 'provider_requests': 0}))
    elif args.mode == 'prepare':
        pin = m.prepare(Path('diagnostic-preflight'), contract, env, m.previous.runtime_facts())
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as handle:
            handle.write('inventory_sha256=' + pin + '\n')
    else:
        from momentumbot.research.early_pullback_census_http_v01 import DirectHTTPS
        result = m.capture(root=ROOT, output=Path('diagnostic-result'),
            preflight=m.read_files(Path('diagnostic-preflight'), m.PREFLIGHT_FILES),
            env=env, facts=facts, now=now, runtime=m.previous.runtime_facts(),
            live_ref=m.base.json_object(Path('diagnostic-current-ref.json').read_bytes()),
            artifact=m.base.json_object(Path('diagnostic-artifact.json').read_bytes()),
            credential_loader=lambda: os.environ.get('MASSIVE_API_KEY', ''), transport=DirectHTTPS())
        print(json.dumps({'attempts': result['attempts'], 'failure': result['failure'], 'diagnosis': result['diagnosis']}))
        return 0 if result['failure'] is None else 2
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        print('Diagnostic gate failed; no fallback or retry.', file=sys.stderr)
        sys.exit(2)
