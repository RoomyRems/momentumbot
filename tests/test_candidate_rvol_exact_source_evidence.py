"""Validate the frozen integration outputs without repeating market-data replay."""
from collections import Counter
import gzip
import math
from pathlib import Path
import unittest

import pandas as pd

from momentumbot.research import candidate_rvol_exact_source as m

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / m.BASE / 'integration'
REPORT_SEAL = '0a65a01ff43fa5e7c8b72d02bc6f960dc99dd1daae1e92bf17c7430e71bff2a0'


class ExactSourceEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = m.parse((BASE / 'integration-report.json').read_bytes())

    def test_frozen_report_preserves_selection_and_unresolved_sources(self):
        value = self.report
        m.capture.c.d.base.verify_seal(value)
        self.assertEqual(value['content_sha256'], REPORT_SEAL)
        self.assertEqual(value['accepted_exact_proof_sha256'], m.PROOF_SEAL)
        self.assertEqual(value['original_capture_pin'], m.CAPTURE_PIN)
        self.assertEqual(value['candidate_cases'], 2103)
        self.assertEqual(value['coarse_excluded_cases_unchanged'], 1675)
        self.assertEqual(value['empty_or_short_history_exclusions_unchanged'], 240)
        self.assertEqual(value['prior_session_comparisons'], 105150)
        self.assertEqual(value['refreshes_reconciled'], 8)
        self.assertEqual(len(value['days']), 30)
        self.assertEqual(sum(d['history_bar_count'] + d['refresh_bar_count'] for d in value['days']), 3309900)
        self.assertEqual(value['provider_requests'], 0)
        for key in ['historical_scanner_enabled', 'financial_evaluation_enabled',
                    'brokerage_orders_enabled', 'policy_promotion_eligible', 'transcript_records_read',
                    'daily_minute_share_basis_verified']:
            self.assertIs(value[key], False)
        self.assertEqual(value['exact_same_time_rvol_complete_for_retained_cases'],
                         value['counts'].get('exact_rvol_ready', 0) == value['candidate_cases'])

    def test_each_frozen_curve_is_bound_ordered_and_only_from_accepted_cases(self):
        counts = Counter(); observations = 0; unavailable = []
        for day in self.report['days']:
            path = BASE / day['file']; body = path.read_bytes()
            self.assertEqual(path.name, day['trading_date'] + '.json.gz')
            self.assertEqual(len(body), day['bytes'])
            self.assertEqual(m.sha(body), day['sha256'])
            value = m.parse(gzip.decompress(body)); m.capture.c.d.base.verify_seal(value)
            self.assertEqual(value['content_sha256'], day['content_sha256'])
            cases = {c['symbol']: c for c in value['cases']}
            self.assertEqual(len(cases), len(value['cases']))
            expected = {s for s, c in cases.items() if c['status'] == 'exact_rvol_ready'}
            self.assertEqual(set(value['candidate_exact_rvol_by_symbol']), expected)
            counts.update(c['status'] for c in cases.values())
            unavailable.extend((day['trading_date'], s) for s in cases if s not in expected)
            for symbol, rows in value['candidate_exact_rvol_by_symbol'].items():
                self.assertEqual(len(rows), cases[symbol]['rvol_observations'])
                times = pd.to_datetime([r[0] for r in rows], utc=True)
                self.assertTrue(times.is_unique and times.is_monotonic_increasing)
                local = times.tz_convert(m.capture.daily.ET)
                self.assertTrue(all(d.isoformat() == day['trading_date'] for d in local.date))
                self.assertTrue(all(4 <= t.hour < 10 and t.second == 0 for t in local))
                for _, number in rows:
                    self.assertTrue(number is None or number == 'positive_infinity' or
                                    type(number) in (int, float) and math.isfinite(number) and number >= 0)
                observations += len(rows)
        self.assertEqual(dict(counts), self.report['counts'])
        self.assertEqual(observations, self.report['rvol_observations'])
        self.assertEqual(unavailable, [('2026-03-25', 'MGN'), ('2026-05-19', 'RUBI')])


if __name__ == '__main__':
    unittest.main()
