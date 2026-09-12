"""Offline diagnostic verification and frozen order-repair registration."""
import argparse
import json
from pathlib import Path
import sys

from run_offline_python_v13 import deny_external_io


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', action='store_true')
    args = parser.parse_args()
    sys.addaudithook(deny_external_io)
    from momentumbot.research import census_order_repair as m
    from momentumbot.research.census_payload_evidence import verify
    root = Path(__file__).resolve().parents[1]
    audit, raw = verify(root)
    projected = m.project_body(m.diagnostic.request(), raw)
    m.require(projected['raw_row_count'] == audit['rows'] == 1000, 'repaired raw row count differs')
    m.exact(projected['rows'], list(m.legacy.normalize_reference_tickers(
        m.legacy.parse_json(raw)['results'])), 'normalization changed')
    audit_path = root / m.BASE / 'diagnostic-verification.json'
    if args.freeze:
        m.diagnostic.base.write_once(audit_path, audit)
        m.diagnostic.base.write_once(root / m.CONTRACT_PATH, m.registration(root))
    m.exact(m.diagnostic.base.frozen(audit_path), audit, 'diagnostic audit differs')
    contract = m.validate_registration(root)
    print(json.dumps({'diagnostic_verification_sha256': audit['content_sha256'],
        'registration_sha256': contract['content_sha256'], 'rows_repaired_offline': 1000,
        'provider_requests': 0, **m.legacy.BOUNDARY}, sort_keys=True))


if __name__ == '__main__':
    main()
