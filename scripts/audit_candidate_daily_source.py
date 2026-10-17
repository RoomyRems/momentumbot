"""Project accepted prior daily histories and compare saved daily close witnesses."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse
from collections import Counter
import gzip
import math

from momentumbot.research import candidate_daily_source as m
from momentumbot.research import scanner_minutes
from run_offline_python_v13 import deny_external_io


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--daily-capture', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(); root = Path(__file__).resolve().parents[1]; output = Path(args.output)
    m.require(not output.exists() and not any(p.is_symlink() for p in (output, *output.parents)),
              'fresh regular output required')
    output.mkdir(parents=True); sys.addaudithook(deny_external_io)
    saved = scanner_minutes.saved_daily(root)
    saved_days = {d['trading_date']: d for d in saved['days']}
    days, counts = [], Counter()
    with m.CandidateDailyArchive(root, args.daily_capture) as source:
        targets = sorted({r['trading_date'] for r in source.contract['requests']})
        m.exact(targets, sorted(saved_days), 'saved daily target union differs')
        for target in targets:
            result = source.read_day(target); prior = saved_days[target]; cases = []
            for symbol, item in sorted(result['history_by_symbol'].items()):
                m.require(symbol in prior['membership_symbols'], 'candidate outside saved membership')
                witness = prior['previous_close_witnesses'].get(symbol)
                if witness is not None:
                    m.exact(witness['close'], prior['previous_close_by_symbol'][symbol], 'saved witness close differs')
                comparison = m.compare_previous_close(item['daily_bars'], witness, target)
                average = item['average_daily_volume_50']
                available = average is not None and math.isfinite(average) and average > 0
                cases.append({'symbol': symbol, 'history_bar_count': len(item['daily_bars']),
                    'prior_sessions': item['prior_sessions'], 'sufficient_history': item['sufficient_history'],
                    'average_daily_volume_50': float(average) if available else None,
                    'average_volume_available': available, 'previous_close_comparison': comparison})
            day_counts = dict(Counter(c['previous_close_comparison']['status'] for c in cases)); counts.update(day_counts)
            days.append({'trading_date': target, 'source_provenance': result['provenance'],
                         'saved_scanner_daily_sha256': prior['content_sha256'], 'cases': cases})
            print(target, len(cases), day_counts, flush=True)
        case_count = sum(len(d['cases']) for d in days)
        bars = sum(d['source_provenance']['bar_count'] for d in days)
        m.require(case_count == 4018 and len(days) == 30, 'registered daily population differs')
        m.exact(bars, source.result['bar_count'], 'daily archive bar count differs')
        report = m.seal({'contract_id': m.ID, 'accepted_daily_proof_sha256': m.coarse.PROOF_SEAL,
            'original_capture_pin': m.CAPTURE_PIN, 'saved_scanner_daily_sha256': saved['content_sha256'],
            'candidate_cases': case_count, 'daily_bars': bars, 'counts': dict(counts), 'days': days,
            'sufficient_history_cases': sum(c['sufficient_history'] for d in days for c in d['cases']),
            'available_average_volume_cases': sum(c['average_volume_available'] for d in days for c in d['cases']),
            'full_ranking_population_verified': False, **m.BOUNDARY})
    encoded = gzip.compress(m.capture.render(report), mtime=0)
    (output / 'daily-source-audit.json.gz').write_bytes(encoded)
    print(report['content_sha256'], bars, case_count, dict(counts), flush=True)


if __name__ == '__main__': main()
