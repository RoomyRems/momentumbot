"""Diagnose sealed withheld RVOL histories using saved sources only."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse
import gzip

from momentumbot.research import candidate_rvol_basis_diagnostic as m
from run_offline_python_v13 import deny_external_io


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exact-capture', required=True)
    parser.add_argument('--coarse-capture', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = Path(args.output)
    m.require(not output.exists() and not any(p.is_symlink() for p in (output, *output.parents)),
              'fresh regular output required')
    output.mkdir(parents=True)
    sys.addaudithook(deny_external_io)
    cases = []
    with m.parent.CandidateExactArchive(root, args.exact_capture) as exact_source, \
            m.parent.capture.source.CandidateCoarseArchive(root, args.coarse_capture) as coarse_source:
        for case in m.withheld_cases(root):
            target, symbol = case['trading_date'], case['symbol']
            one = m.read_symbol_history(exact_source, target, symbol)
            fifteen = m.read_symbol_history(coarse_source, target, symbol)
            result = m.diagnose_case(case, one, fifteen)
            cases.append(result)
            print(target, symbol, 'volume sessions', result['volume_differing_sessions'],
                  'price sessions', result['price_differing_sessions'],
                  'volume buckets', result['volume_differing_buckets'],
                  'price buckets', result['price_differing_buckets'], flush=True)
        report = m.seal({'contract_id': m.ID, 'parent_integration_sha256': m.PARENT_SEAL,
            'accepted_exact_proof_sha256': m.parent.PROOF_SEAL,
            'accepted_coarse_proof_sha256': m.parent.capture.source.PROOF_SEAL,
            'original_exact_capture_pin': m.parent.CAPTURE_PIN,
            'original_coarse_capture_metadata': coarse_source.result['archive_metadata'],
            'cases': cases, 'withheld_cases': len(cases),
            'prior_sessions_compared': sum(c['prior_session_count'] for c in cases),
            'case_selection': 'all and only sealed parent source_disagreement cases',
            'comparison_role': 'descriptive OHLC rollup; no guarantee of vendor timeframe equivalence',
            'source_root_cause_proven': False, 'basis_correction_proven': False, **m.BOUNDARY})
    encoded = gzip.compress(m.parent.capture.render(report), mtime=0)
    (output / 'basis-diagnostic.json.gz').write_bytes(encoded)
    print('report', report['content_sha256'], 'bytes', len(encoded), 'sha256', m.sha(encoded), flush=True)


if __name__ == '__main__':
    main()
