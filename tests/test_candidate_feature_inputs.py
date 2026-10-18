import math
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from momentumbot.research import candidate_feature_inputs as m

ROOT = Path(__file__).resolve().parents[1]


class CandidateFeatureInputTests(unittest.TestCase):
    def test_decode_preserves_undefined_infinity_and_zero(self):
        rows = [['2026-03-09T08:00:00Z', None], ['2026-03-09T08:01:00Z', 'positive_infinity'],
                ['2026-03-09T08:02:00Z', 0], ['2026-03-09T08:03:00Z', 2.5]]
        values = m.decode_curve(rows, '2026-03-09')
        self.assertTrue(math.isnan(values.iloc[0]))
        self.assertEqual(values.iloc[1:].tolist(), [math.inf, 0, 2.5])

    def test_rejects_wrong_date_off_grid_future_window_and_duplicates(self):
        for stamp in ['2026-03-09T08:00:01Z', '2026-03-09T08:00:00.000000001Z',
                      '2026-03-10T08:00:00Z', '2026-03-09T14:00:00Z', '2026-03-09T04:00:00']:
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                m.decode_curve([[stamp, 1]], '2026-03-09')
        for stamps in [['2026-03-09T08:00Z'] * 2,
                       ['2026-03-09T08:01Z', '2026-03-09T08:00Z']]:
            with self.subTest(stamps=stamps), self.assertRaises(ValueError):
                m.decode_curve([[s, 1] for s in stamps], '2026-03-09')

    def test_rejects_invalid_numbers(self):
        for value in [True, -1, float('nan'), float('inf'), '2', 'negative_infinity']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                m.decode_curve([['2026-03-09T08:00:00Z', value]], '2026-03-09')

    def test_completed_minute_boundary_and_dst(self):
        curve = m.decode_curve([['2026-03-09T08:00Z', 1], ['2026-03-09T08:01Z', 999]], '2026-03-09')
        self.assertTrue(m.completed_curve(curve, '2026-03-09T04:00:59-04:00').empty)
        self.assertEqual(m.completed_curve(curve, '2026-03-09T04:01:00-04:00').tolist(), [1])
        self.assertEqual(m.completed_curve(curve, '2026-03-09T04:02:00-04:00').tolist(), [1, 999])
        with self.assertRaises(ValueError): m.completed_curve(curve, '2026-03-09T04:02:00')
        copied = m.completed_curve(curve, '2026-03-09T04:02:00-04:00'); copied.iloc[0] = 200
        self.assertEqual(curve.iloc[0], 1)

    def test_duplicate_keys_and_changed_bytes_fail(self):
        with self.assertRaises(ValueError): m.indexed([{'symbol': 'A'}, {'symbol': 'A'}], 'symbol')
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'bad.json'; path.write_bytes(b'{}')
            with self.assertRaises(ValueError): m.read_pinned(path, m.RVOL_PIN)

    def test_real_source_union_keeps_withheld_cases(self):
        source = m.CandidateFeatureInputs(ROOT)
        self.assertEqual(len(source.dates), 30)
        for target, withheld in [('2026-03-25', 'MGN'), ('2026-05-19', 'RUBI')]:
            day = source.read_day(target)
            self.assertEqual(day['features_by_symbol'][withheld]['exact_rvol_status'], 'source_disagreement')
            self.assertNotIn(withheld, day['candidate_exact_rvol_by_symbol'])
            self.assertFalse(day['provenance']['full_scanner_inputs_complete'])
            self.assertFalse(day['provenance']['daily_minute_share_basis_verified'])
            self.assertFalse(day['provenance']['float_news_integrated'])
        with self.assertRaises(ValueError): source.read_day('2026-03-01')


if __name__ == '__main__': unittest.main()
