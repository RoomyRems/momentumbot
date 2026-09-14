"""Build the fixed census reference bridge without network, market data or labels."""
import argparse
import gzip
import json
from pathlib import Path
import sys

from run_offline_python_v13 import deny_external_io

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('freeze', 'validate', 'build'))
    parser.add_argument('--census-zip', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    sys.addaudithook(deny_external_io)
    from momentumbot.research import census_scanner_bridge as m
    if args.mode == 'freeze':
        with (ROOT / m.CONTRACT_PATH).open('xb') as handle: handle.write(m.render(m.registration(ROOT)))
    contract = m.validate_registration(ROOT)
    if args.mode != 'build':
        print(json.dumps({'registration_sha256': contract['content_sha256']}))
        return
    m.require(args.census_zip is not None and args.output is not None, 'source ZIP and new output required')
    m.require(not args.output.exists() and not any(p.is_symlink() for p in (args.output, *args.output.parents)),
        'fresh regular output directory required')
    panel = m.build_panel(args.census_zip, ROOT, progress=lambda row: print(json.dumps(row), flush=True))
    raw = gzip.compress(m.render(panel), mtime=0)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'reference-panel.json.gz').write_bytes(raw)
    summary = m.seal({'contract_id': m.ID, 'registration_sha256': contract['content_sha256'],
        'panel_sha256': panel['content_sha256'], 'panel_file': {'bytes': len(raw), 'sha256': m.sha(raw)},
        'dates': [{k: day[k] for k in ('trading_date', 'source_row_count', 'ticker_count',
            'reason_counts', 'reference_identity_counts', 'identity_quarantine_count', 'reference_exceptions')}
            | {'coverage_symbol_count': len(day['coverage_symbols']),
               'identity_quarantined': day['reference_identity_statuses']['quarantined']}
            for day in panel['days']], 'initial_request_count': panel['initial_request_count'],
        'provider_requests': 0, 'hosted_protocol_replay_reused': True, **m.BOUNDARY})
    (args.output / 'summary.json').write_bytes(m.render(summary))
    print(json.dumps({'panel_sha256': panel['content_sha256'], 'initial_requests': panel['initial_request_count'],
        'output': str(args.output), 'provider_requests': 0}))


if __name__ == '__main__': main()
