"""Same-code CI-gated fixed coverage capture, with independent offline replay."""
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
    from momentumbot.research import coverage_capture_hosted as m
    env = {key: os.environ.get(key, '') for key in m.ENV_KEYS}
    now = datetime.now(timezone.utc)
    if args.mode == 'freeze': m.d.base.write_once(ROOT / m.CONTRACT_PATH, m.registration(ROOT))
    contract = m.validate_registration(ROOT)
    if facts: m.check_launch(contract, env, facts, now)
    runtime = m.d.previous.runtime_facts() if facts else None
    read = lambda name: m.parse(Path(name).read_bytes())
    def output(pin):
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as handle:
            handle.write('inventory_sha256=' + pin + '\n')
    if args.mode in ('freeze', 'validate'):
        print(json.dumps({'registration_sha256': contract['content_sha256'], 'provider_requests': 0}))
    elif args.mode == 'prepare':
        output(m.prepare(Path('coverage-preflight'), contract, env, runtime))
    elif args.mode == 'capture':
        try:
            result = m.capture(ROOT, env, facts, now, runtime,
                m.d.read_files(Path('coverage-preflight'), m.d.PREFLIGHT_FILES),
                read('coverage-current-ref.json'), read('coverage-preflight-artifact.json'),
                output=Path('coverage-capture'), credential_loader=lambda: {k: os.environ.get(k, '') for k in m.c.KEYS},
                transport=m.c.DirectHTTPS(), progress=lambda r: print(json.dumps(r), flush=True))
        finally:
            path = Path('coverage-capture/inventory.json')
            if path.is_file(): output(m.sha(path.read_bytes()))
        print(json.dumps({k: result[k] for k in ('protocol_complete', 'attempt_count', 'failure')}))
        return 0 if result['protocol_complete'] else 2
    else:
        result = m.verify(ROOT, env, facts, now, runtime, read('coverage-current-ref.json'),
            read('coverage-preflight-artifact.json'), read('coverage-capture-artifact.json'),
            read('coverage-jobs.json'), Path('coverage-preflight.zip'), Path('coverage-capture.zip'))
        out = Path('coverage-verification')
        out.mkdir(exist_ok=False)
        m.d.base.write_once(out / 'hosted-verification.json', result)
        for name in ('coverage-current-ref.json', 'coverage-preflight-artifact.json', 'coverage-capture-artifact.json', 'coverage-jobs.json'):
            (out / name).write_bytes(Path(name).read_bytes())
        print(json.dumps({'verification_sha256': result['content_sha256'], 'provider_requests': 0}))
    return 0


if __name__ == '__main__':
    try: sys.exit(main())
    except Exception:
        print('Coverage gate or capture failed; safe evidence retained when available; no retry.', file=sys.stderr)
        sys.exit(2)
