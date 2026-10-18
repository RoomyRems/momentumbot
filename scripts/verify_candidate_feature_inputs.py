"""Verify the accepted daily/RVOL join across the entire saved panel."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse
from collections import Counter

from momentumbot.research import candidate_feature_inputs as m
from run_offline_python_v13 import deny_external_io


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    sys.addaudithook(deny_external_io)
    source = m.CandidateFeatureInputs(Path(__file__).resolve().parents[1])
    days, counts = [], Counter()
    for target in source.dates:
        day = source.read_day(target); features = day['features_by_symbol']
        states = Counter(c['exact_rvol_status'] for c in features.values()); counts.update(states)
        value = {'trading_date': target, 'candidate_count': len(features), 'counts': dict(states),
            'daily_and_rvol_present': sum(c['previous_close'] is not None and
                c['average_daily_volume_50'] is not None and s in day['candidate_exact_rvol_by_symbol']
                for s, c in features.items()),
            'rvol_observations': sum(len(c) for c in day['candidate_exact_rvol_by_symbol'].values()),
            'provenance': day['provenance']}
        days.append(value); print(target, dict(states), flush=True)
    report = m.seal({'contract_id': m.ID, 'days': days, 'counts': dict(counts),
        'candidate_cases': sum(d['candidate_count'] for d in days),
        'daily_and_rvol_present': sum(d['daily_and_rvol_present'] for d in days),
        'rvol_observations': sum(d['rvol_observations'] for d in days),
        'full_scanner_inputs_complete': False, 'float_news_integrated': False, **m.daily.BOUNDARY})
    m.exact(report['candidate_cases'], 4018, 'candidate total differs')
    m.exact(report['counts'], {'exact_rvol_ready': 2101, 'source_disagreement': 2,
                             'not_retained_for_exact_capture': 1915}, 'RVOL status totals differ')
    m.exact(report['rvol_observations'], 159079, 'RVOL total differs')
    m.daily.capture.gate.d.base.write_once(Path(args.output), report)
    print(report['content_sha256'], report['daily_and_rvol_present'], 'joined daily/RVOL cases', flush=True)


if __name__ == '__main__': main()
