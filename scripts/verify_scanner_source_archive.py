"""Project every accepted date offline, retaining counts and source lineage."""
import argparse
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from momentumbot.research.scanner_source_archive import ScannerMinuteArchive, ID, PARENT, seal
from run_offline_python_v13 import deny_external_io


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture-zip', type=Path, nargs='+', required=True,
                   help='Original ZIP or its byte-exact parts in order')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    sys.addaudithook(deny_external_io)
    days = []
    with ScannerMinuteArchive(ROOT, args.capture_zip) as source:
        for target in source.days:
            result = source.read_day(target)
            days.append(result['provenance'])
            print(json.dumps({k: result['provenance'][k] for k in ('trading_date', 'member_count', 'bar_count', 'empty_member_count')}), flush=True)
        report = seal({'contract_id': ID, 'parent_commit': PARENT, 'accepted_hosted_proof_sha256': source.proof['content_sha256'],
            'days': days, 'bar_count': sum(d['bar_count'] for d in days),
            'member_dates': sum(d['member_count'] for d in days), 'provider_requests': 0,
            'daily_minute_share_basis_verified': False, 'historical_scanner_enabled': False,
            'financial_evaluation_enabled': False, 'discretionary_strategy_integrated': False})
    with args.output.open('x') as f: json.dump(report, f, sort_keys=True, separators=(',', ':'));f.write('\n')
    print(json.dumps({'content_sha256': report['content_sha256'], 'dates': len(days), 'bar_count': report['bar_count']}))


if __name__ == '__main__': main()
