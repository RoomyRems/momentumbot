"""Frozen diagnostic acceptance without a provider call or archive replay."""
import gzip
from pathlib import Path
import unittest

from momentumbot.research import candidate_rvol_basis_diagnostic as m

ROOT = Path(__file__).resolve().parents[1]
REPORT_SEAL = 'cfe4fa96d7685754effe5539030ac3257cb0045fbaf6aacecde71d09e8526d89'


class BasisEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = (ROOT / m.BASE / 'diagnostic/basis-diagnostic.json.gz').read_bytes()
        cls.report = m.parse(gzip.decompress(cls.body))

    def test_pinned_report_does_not_promote_or_correct_any_case(self):
        value = self.report
        self.assertEqual(len(self.body), 70889)
        self.assertEqual(m.sha(self.body), 'ec532567c2ea6fb7148c787072020326c96d281192f150f138de82dc18cdbb2b')
        m.parent.capture.c.d.base.verify_seal(value)
        self.assertEqual(value['content_sha256'], REPORT_SEAL)
        self.assertEqual(value['parent_integration_sha256'], m.PARENT_SEAL)
        self.assertEqual(value['original_exact_capture_pin'], m.parent.CAPTURE_PIN)
        self.assertEqual(value['accepted_coarse_proof_sha256'], m.parent.capture.source.PROOF_SEAL)
        self.assertEqual(value['prior_sessions_compared'], 100)
        self.assertEqual(value['withheld_cases'], 2)
        for item in [value, *value['cases']]:
            for key, expected in m.BOUNDARY.items():
                self.assertEqual(item[key], expected)
            self.assertFalse(item['basis_correction_proven'])

    def test_every_parent_failure_is_traced_with_matching_presence_and_trade_counts(self):
        cases = self.report['cases']
        self.assertEqual([(c['trading_date'], c['symbol'], c['volume_differing_sessions'],
                           c['volume_differing_buckets']) for c in cases],
                         [('2026-03-25', 'MGN', 48, 193), ('2026-05-19', 'RUBI', 50, 663)])
        parents = {(c['trading_date'], c['symbol']): c for c in m.withheld_cases(ROOT)}
        for case in cases:
            parent = parents[case['trading_date'], case['symbol']]
            self.assertEqual(case['parent_day_sha256'], parent['parent_day_sha256'])
            self.assertEqual(case['parent_target_comparison'], parent['target_comparison'])
            self.assertEqual(case['status'], 'withheld_unresolved_basis')
            self.assertFalse(case['exact_same_time_rvol_complete'])
            self.assertFalse(case['provider_root_cause_proven'])
            self.assertEqual(len(case['sessions']), 50)
            self.assertEqual(len({s['observation_date'] for s in case['sessions']}), 50)
            self.assertEqual(case['price_differing_sessions'], case['volume_differing_sessions'])
            self.assertEqual(case['price_differing_buckets'], case['volume_differing_buckets'])
            self.assertEqual(case['trade_count_differing_buckets'], 0)
            self.assertEqual(case['presence_differing_buckets'], 0)
            expected = {s['observation_date']: s for s in parent['prior_session_differences']}
            for session in case['sessions']:
                self.assertLess(session['observation_date'], case['trading_date'])
                self.assertEqual(session['compared_buckets'], 24)
                self.assertTrue(session['compatible_requests'])
                self.assertFalse(session['adjustment_vintage_verified'])
                self.assertFalse(session['asof_establishes_adjustment_cutoff'])
                self.assertEqual(session['volume_differing_buckets'],
                                 expected.get(session['observation_date'], {}).get('mismatched_buckets', 0))
                self.assertEqual(session['price_differing_buckets'], session['volume_differing_buckets'])
                for field in ('exact_source', 'coarse_source'):
                    source = session[field]
                    m.parent.capture.c.d.base.verify_seal(source['root'])
                    self.assertEqual(source['root']['observation_date'], session['observation_date'])
                    self.assertTrue(source['pages'])
                    for page in source['pages']:
                        self.assertRegex(page['body_sha256'], r'^[a-f0-9]{64}$')
                        self.assertLessEqual(page['started_at'], page['finished_at'])


if __name__ == '__main__':
    unittest.main()
