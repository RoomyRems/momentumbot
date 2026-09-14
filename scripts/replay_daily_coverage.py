"""Offline frozen-day coverage replay. Local hashes are not vendor provenance.

Input is a fresh capture's ordered request/transport envelopes, with body_utf8
replacing body. Original archive verification and hosted capture are separate.
No network, environment credentials, transcript inputs, or retry path.
"""
import argparse
import json
from pathlib import Path
import sys

from run_offline_python_v13 import deny_external_io

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('freeze', 'validate', 'replay'))
    parser.add_argument('--date')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    sys.addaudithook(deny_external_io)
    from momentumbot.research import daily_coverage as m
    if args.mode == 'freeze':
        with (ROOT / m.CONTRACT_PATH).open('xb') as handle:
            handle.write(m.bridge.render(m.registration(ROOT)))
    contract = m.validate_registration(ROOT)
    if args.mode != 'replay':
        print(json.dumps({'registration_sha256': contract['content_sha256'], 'provider_requests': 0}))
        return
    m.require(args.date in m.bridge.DATES and args.input is not None and args.output is not None,
        'fixed date, ordered input and fresh output required')
    for path in (args.input, args.output):
        m.require(not any(p.is_symlink() for p in (path, *path.parents)), 'regular paths required')
    m.require(not args.output.exists(), 'fresh output required')
    panel = m.load_panel(ROOT)
    projected = next(d for d in panel['days'] if d['trading_date'] == args.date)
    state = m.DailyCoverage(projected)
    attempts = 0
    with args.input.open('rb') as handle:
        while True:
            line = handle.readline(m.MAX_BODY * 6 + 65536)
            if not line:
                break
            m.require(line.endswith(b'\n'), 'bounded complete JSON line required')
            attempts += 1
            m.require(attempts <= len(m.bridge.coverage_requests(projected)) * m.MAX_PAGES,
                'date attempt ceiling')
            event = m.bridge.parse(line)
            m.require(set(event) == {'request', 'response'}, 'exact replay event required')
            response = event['response']
            m.require(type(response) is dict and set(response) == {'status', 'body_utf8', 'complete', 'encoding'}
                and type(response['body_utf8']) is str, 'exact text-body envelope required')
            response['body'] = response.pop('body_utf8').encode('utf-8')
            state.accept(event['request'], response)
    result = state.result()
    with args.output.open('xb') as handle:
        handle.write(m.bridge.render(result))
    print(json.dumps({'content_sha256': result['content_sha256'],
        'replayed_attempts': attempts, 'provider_requests': 0, 'provider_origin_authenticated': False}))


if __name__ == '__main__': main()
