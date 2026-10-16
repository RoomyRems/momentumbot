"""Integrate byte-pinned exact RVOL sources offline; no new provider requests."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse
from collections import Counter
import gzip

from momentumbot.research import candidate_rvol_exact_source as m
from momentumbot.research.candidate_source_archive import CandidateMinuteArchive
from momentumbot.research.candidate_volume_projection import selected_split_volumes
from run_offline_python_v13 import deny_external_io


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exact-capture', required=True)
    parser.add_argument('--coarse-capture', required=True)
    parser.add_argument('--raw-capture', required=True)
    parser.add_argument('--split-capture', nargs='+', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = Path(args.output)
    m.require(not output.exists() and not any(p.is_symlink() for p in (output, *output.parents)),
              'fresh regular output required')
    output.mkdir(parents=True)
    sys.addaudithook(deny_external_io)
    days = []
    with m.CandidateExactArchive(root, args.exact_capture) as source, \
            m.capture.source.CandidateCoarseArchive(root, args.coarse_capture) as coarse, \
            CandidateMinuteArchive(root, args.raw_capture) as raw, \
            m.split_source.ScannerMinuteArchive(root, args.split_capture) as split:
        for selection in source.selection['days']:
            target = selection['trading_date']
            result = source.read_day(target)
            symbols = sorted(result['sessions_by_symbol'])
            saved = selected_split_volumes(split, target, symbols)
            native = raw.read_day(target)['candidate_raw_minute_bars_by_symbol']
            coarse_day = coarse.read_day(target)
            cases, curves = [], {}
            for symbol, history in sorted(result['sessions_by_symbol'].items()):
                curve, audit = m.integrate_case(target=target, raw=native[symbol], saved_split=saved[symbol],
                    history=history, coarse_history=coarse_day['sessions_by_symbol'][symbol],
                    refresh=result['target_refresh_by_symbol'].get(symbol))
                cases.append({'symbol': symbol, **audit})
                if curve is not None:
                    curves[symbol] = m.encode_curve(curve)
            value = m.seal({'contract_id': m.ID, 'trading_date': target,
                'exact_source_provenance': result['provenance'],
                'coarse_source_provenance': coarse_day['provenance'],
                'accepted_raw_proof_sha256': raw.proof['content_sha256'],
                'accepted_split_proof_sha256': split.proof['content_sha256'],
                'cases': cases, 'candidate_exact_rvol_by_symbol': curves,
                'timestamp_semantics': 'bar start; available at bar start plus one minute',
                'source_window_et': '04:00 through 09:59 bar starts',
                'daily_minute_share_basis_verified': False, 'provider_requests': 0,
                **m.capture.old.parent.parent.BOUNDARY})
            encoded = gzip.compress(m.capture.render(value), mtime=0)
            name = target + '.json.gz'
            (output / name).write_bytes(encoded)
            counts = dict(Counter(c['status'] for c in cases))
            days.append({'trading_date': target, 'file': name, 'bytes': len(encoded), 'sha256': m.sha(encoded),
                'content_sha256': value['content_sha256'], 'candidate_count': len(cases), 'counts': counts,
                'rvol_observations': sum(c.get('rvol_observations', 0) for c in cases),
                'history_bar_count': result['provenance']['history_bar_count'],
                'refresh_bar_count': result['provenance']['refresh_bar_count'],
                'empty_prior_sessions': sum(c['empty_prior_sessions'] for c in cases),
                'prior_session_comparisons': sum(c['prior_comparison_count'] for c in cases),
                'prior_session_disagreements': sum(len(c['prior_session_differences']) for c in cases),
                'refreshes': [c for c in cases if c['target_volume_source'] == 'registered_exact_refresh']})
            print(target, counts, 'history disagreements', days[-1]['prior_session_disagreements'], flush=True)
        count = sum(d['candidate_count'] for d in days)
        m.require(count == source.selection['retained_cases'] == 2103, 'retained population differs')
        m.require(sum(d['history_bar_count'] + d['refresh_bar_count'] for d in days)
                  == source.result['bar_count'], 'exact archive bar total differs')
        refreshes = [c for d in days for c in d['refreshes']]
        m.require(len(refreshes) == 8, 'registered refresh total differs')
        totals = Counter()
        for day in days:
            totals.update(day['counts'])
        report = m.seal({'contract_id': m.ID, 'source_code_commit': m.SOURCE_COMMIT,
            'accepted_exact_proof_sha256': m.PROOF_SEAL, 'original_capture_pin': m.CAPTURE_PIN,
            'acquisition_diagnostic_sha256': m.capture.AUDIT_SEAL, 'days': days, 'counts': dict(totals),
            'candidate_cases': count, 'coarse_excluded_cases_unchanged': 1675,
            'empty_or_short_history_exclusions_unchanged': 240,
            'prior_session_comparisons': sum(d['prior_session_comparisons'] for d in days),
            'prior_session_disagreements': sum(d['prior_session_disagreements'] for d in days),
            'refreshes_reconciled': sum(c['refresh_resolves_original_difference'] for c in refreshes),
            'rvol_observations': sum(d['rvol_observations'] for d in days),
            'empty_prior_sessions': sum(d['empty_prior_sessions'] for d in days),
            'exact_same_time_rvol_complete_for_retained_cases': totals['exact_rvol_ready'] == count,
            'daily_minute_share_basis_verified': False, 'provider_requests': 0,
            **m.capture.old.parent.parent.BOUNDARY})
    (output / 'integration-report.json').write_bytes(m.capture.render(report))
    print(report['content_sha256'], dict(totals), 'refreshes', report['refreshes_reconciled'], flush=True)


if __name__ == '__main__':
    main()
